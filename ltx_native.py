"""
LTX Video 2.3 API Client
Native LTX API when key is available, FAL.ai proxy otherwise.
Supports: image-to-video, keyframe transition, 4K generation.
"""
from __future__ import annotations

import os
import json
import base64
import urllib.request
import time
from typing import Callable
from config.settings import settings
from cinema.fal_limits import FAL_TIMEOUT_VIDEO_S

try:
    import fal_client
    FAL_AVAILABLE = True
except ImportError:
    FAL_AVAILABLE = False


class LTXContractViolation(ValueError):
    """A locally-detected violation of the LTX request contract (e.g. an
    out-of-enum ``duration`` for the ltx-2-3-pro profile — see
    https://docs.ltx.io/models).

    Raised BEFORE any network call, from :meth:`LTXVideoAPI.generate_video`
    directly — never from inside ``_native_generate``'s try/except, so it can
    never be swept up by the native→FAL fallback logic there. That fallback
    exists for PROVIDER-side failures (5xx, timeouts, transient network
    errors); silently rerouting a malformed request WE built to FAL would
    "succeed" on a different (coerced) request and conceal the bug in our
    own request construction (audited 2026-07-30).
    """


class LTXVideoAPI:
    """
    LTX Video 2.3 client.
    Checks LTX_API_KEY (native) first, falls back to FAL_KEY (proxy via fal.ai).
    Designed for easy swap to native endpoint when key arrives.
    """

    # LTX-2.3 (bumped 2026-07-11 from fal-ai/ltx-2; schema from fal's OpenAPI
    # spec): params are image_url + string resolution + int duration enum
    # {6,8,10}; NO num_frames/width/height, NO camera_motion param (prompt-text
    # only), NO negative_prompt; generate_audio defaults true (+~$0.02/s
    # apparent surcharge — we send False; assembly owns audio). Fast tier
    # (fal-ai/ltx-2.3/image-to-video/fast) unlocks 12-20s at 25fps/1080p only.
    FAL_MODEL_ID = "fal-ai/ltx-2.3/image-to-video"

    # Native LTX Video API — https://docs.ltx.video
    NATIVE_BASE_URL = "https://api.ltx.video/v1"

    RESOLUTION_MAP = {
        "480p": {"width": 854, "height": 480},
        "720p": {"width": 1920, "height": 1080},  # DOCUMENTED-INTENTIONAL: LTX has no true 720p; "720p" upgraded to 1080p (capability-positive); zero live 720p callers
        "1080p": {"width": 1920, "height": 1080},
        "4k": {"width": 3840, "height": 2160},
        "4K": {"width": 3840, "height": 2160},
    }

    # fal-ai/ltx-2.3 resolution enum is 1080p/1440p/2160p (strings). Map from
    # the native width/height dicts; 1080p is the floor (same capability-
    # positive upgrade as RESOLUTION_MAP's 720p row).
    _FAL_RESOLUTION_BY_HEIGHT = {2160: "2160p", 1440: "1440p"}

    @classmethod
    def _fal_resolution(cls, resolution: dict) -> str:
        return cls._FAL_RESOLUTION_BY_HEIGHT.get(resolution.get("height"), "1080p")

    @staticmethod
    def _fal_duration(num_frames: int) -> int:
        """Snap a frame count to the fal-ai/ltx-2.3 duration enum {6, 8, 10}s."""
        seconds = max(1, num_frames // 24)
        if seconds <= 6:
            return 6
        if seconds <= 8:
            return 8
        return 10

    @classmethod
    def nearest_supported_duration(cls, seconds: int) -> int:
        """Snap an arbitrary requested duration (seconds) UP to the nearest
        value in :attr:`DURATION_SECONDS` — the same snap-up bias as
        ``_fal_duration``, just seconds-in rather than frames-in.

        Call sites (the dispatcher) use this to convert a shot's configured
        duration into a value :meth:`generate_video` is guaranteed to accept,
        so the contract lives in exactly one place.
        """
        for allowed in cls.DURATION_SECONDS:
            if seconds <= allowed:
                return allowed
        return cls.DURATION_SECONDS[-1]

    CAMERA_MOTIONS = [
        "dolly_in", "dolly_out", "jib_up", "jib_down",
        "pan_left", "pan_right", "tilt_up", "tilt_down",
        "zoom_in", "zoom_out", "crane_up", "crane_down",
        "truck_left", "truck_right", "static",
    ]

    # ltx-2-3-pro duration enum (seconds) — https://docs.ltx.io/models,
    # confirmed against https://docs.ltx.io/api-documentation/api-reference/
    # video-generation/image-to-video (2026-07-30 audit). Both the native
    # api.ltx.video endpoint (model="ltx-2-3-pro") and the FAL proxy
    # (FAL_MODEL_ID, same pro-equivalent schema per the class comment above)
    # accept ONLY these three values at every resolution. The ltx-2-3-fast
    # profile supports up to 20s at 1080p — a DIFFERENT contract this
    # adapter does not select; do not conflate the two enums.
    DURATION_SECONDS = (6, 8, 10)
    DEFAULT_DURATION_SECONDS = 6

    def __init__(self):
        self.ltx_key = settings.ltx_api_key
        self.fal_key = settings.fal_key
        self.mode = None

        if self.ltx_key:
            # Prefer native LTX API — direct, no proxy
            self.mode = "native"
            print("[LTX] Using native LTX Video API (api.ltx.video)")
        elif self.fal_key and FAL_AVAILABLE:
            self.mode = "fal"
            print("[LTX] Using FAL.ai proxy (fal-ai/ltx-2.3/image-to-video)")
        else:
            print("[LTX] WARNING: No LTX_API_KEY or FAL_KEY found. Video generation disabled.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_video(
        self,
        image_path: str,
        prompt: str,
        output_path: str,
        duration: int = DEFAULT_DURATION_SECONDS,
        resolution: str = "720p",
        camera_motion: str | None = None,
        on_billed: Callable[[], None] | None = None,
    ) -> str | None:
        """
        Generate a video from a single image + prompt.
        Returns output_path on success, None on failure.

        Raises:
            LTXContractViolation: ``duration`` is not one of
                :attr:`DURATION_SECONDS` (6, 8, 10) — raised BEFORE any
                network call, in either mode. This is deliberately NOT caught
                internally: a malformed request WE built must surface as a
                distinguishable error, not silently reroute through the
                native→FAL fallback (which would conceal the bug).

        Args:
            on_billed: Optional zero-arg callback invoked exactly once, the
                moment the provider has confirmed billable video output — a
                video URL for the fal path (``_fal_generate``), or the video
                bytes themselves for the native path (``_native_generate``,
                which returns bytes directly with no separate URL step) —
                the repo's billed bar (see phase_c_ffmpeg._note_billed_attempt).
                Fires BEFORE the download/write that follows so a caller can
                record the spend even when that download/write fails and
                this method still returns None (money-gate 2026-07-11 class,
                extended to the native adapters in slice M2). Threaded
                through the native→fal fallback so exactly one path fires it.
                Exceptions raised by the callback are logged and swallowed.
        """
        if duration not in self.DURATION_SECONDS:
            raise LTXContractViolation(
                f"LTX duration must be one of {self.DURATION_SECONDS} seconds "
                f"(the ltx-2-3-pro profile enum — https://docs.ltx.io/models); "
                f"got {duration!r}. Snap the caller's requested duration via "
                f"LTXVideoAPI.nearest_supported_duration() before calling "
                f"generate_video()."
            )

        if not self.mode:
            print("[LTX] Skipped — no API key configured")
            return None

        num_frames = duration * 24
        res = self.RESOLUTION_MAP.get(resolution, self.RESOLUTION_MAP["720p"])

        print(f"[LTX] Generating {duration}s video @ {resolution} ({num_frames} frames)")
        print(f"[LTX] Prompt: {prompt[:80]}...")

        if self.mode == "native":
            return self._native_generate(
                image_path=image_path,
                prompt=prompt,
                output_path=output_path,
                num_frames=num_frames,
                resolution=res,
                camera_motion=camera_motion,
                on_billed=on_billed,
            )
        else:
            return self._fal_generate(
                image_path=image_path,
                prompt=prompt,
                output_path=output_path,
                num_frames=num_frames,
                resolution=res,
                camera_motion=camera_motion,
                on_billed=on_billed,
            )

    def _upload_to_fal(self, file_path: str) -> str:
        """Upload a local file to FAL and return the hosted URL."""
        return fal_client.upload_file(file_path)

    def _fal_generate(
        self,
        image_path: str,
        prompt: str,
        output_path: str,
        num_frames: int,
        resolution: dict,
        camera_motion: str | None = None,
        on_billed: Callable[[], None] | None = None,
    ) -> str | None:
        try:
            image_url = self._upload_to_fal(image_path)

            # ltx-2.3 has no camera_motion param — fold valid motions into
            # the prompt text (the model steers camera from language now).
            if camera_motion and camera_motion in self.CAMERA_MOTIONS:
                prompt = f"{prompt}. Camera: {camera_motion.replace('_', ' ')}."
                print(f"[LTX] Camera motion (prompt-folded): {camera_motion}")

            arguments = {
                "prompt": prompt,
                "image_url": image_url,
                "duration": self._fal_duration(num_frames),
                "resolution": self._fal_resolution(resolution),
                # Assembly owns audio (TTS/BGM/foley); default true carries an
                # apparent ~$0.02/s surcharge on the playground rates.
                "generate_audio": False,
            }

            result = fal_client.subscribe(
                self.FAL_MODEL_ID,
                arguments=arguments,
                with_logs=True,
                client_timeout=FAL_TIMEOUT_VIDEO_S,
            )

            video_url = result.get("video", {}).get("url")
            if not video_url:
                print("[LTX] ERROR: No video URL in response")
                return None

            # Provider returned a playable video URL — billed regardless of
            # what happens next. Notify the caller BEFORE the download
            # attempt so a subsequent download failure below still reaches
            # the caller's spend accounting, even though this call goes on
            # to return None.
            if on_billed is not None:
                try:
                    on_billed()
                except Exception as callback_exc:
                    print(f"[LTX] Warning: on_billed callback raised: {callback_exc}")

            urllib.request.urlretrieve(video_url, output_path)
            print(f"[LTX] Video saved: {output_path}")
            return output_path

        except Exception as e:
            print(f"[LTX] FAL generation failed: {e}")
            return None

    def _fal_transition(
        self,
        start_frame_path: str,
        end_frame_path: str,
        prompt: str,
        output_path: str,
        num_frames: int,
    ) -> str | None:
        try:
            start_url = self._upload_to_fal(start_frame_path)
            end_url = self._upload_to_fal(end_frame_path)

            # Same fal-ai/ltx-2.3 endpoint handles first+last-frame
            # transitions (image_url + end_image_url together).
            arguments = {
                "prompt": prompt,
                "image_url": start_url,
                "end_image_url": end_url,
                "duration": self._fal_duration(num_frames),
                "resolution": "1080p",
                "generate_audio": False,
            }

            result = fal_client.subscribe(
                self.FAL_MODEL_ID,
                arguments=arguments,
                with_logs=True,
                client_timeout=FAL_TIMEOUT_VIDEO_S,
            )

            video_url = result.get("video", {}).get("url")
            if not video_url:
                print("[LTX-TRANSITION] ERROR: No video URL in response")
                return None

            urllib.request.urlretrieve(video_url, output_path)
            print(f"[LTX-TRANSITION] Transition saved: {output_path}")
            return output_path

        except Exception as e:
            print(f"[LTX-TRANSITION] FAL transition failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Native LTX API implementation (placeholder — activate when key arrives)
    # ------------------------------------------------------------------

    def _native_generate(
        self,
        image_path: str,
        prompt: str,
        output_path: str,
        num_frames: int,
        resolution: dict,
        camera_motion: str | None = None,
        on_billed: Callable[[], None] | None = None,
    ) -> str | None:
        """
        Native LTX Video API — image-to-video generation.
        API returns video bytes directly (no polling needed).
        Docs: https://docs.ltx.video/quickstart
        """
        try:
            # LTX native API needs image_uri as a URL, not base64
            # Upload to FAL for a hosted URL if fal_client is available
            image_url = None
            if FAL_AVAILABLE:
                image_url = fal_client.upload_file(image_path)
            else:
                # Fallback: base64 data URI
                with open(image_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode("utf-8")
                image_url = f"data:image/jpeg;base64,{img_b64}"

            res_str = f"{resolution['width']}x{resolution['height']}"
            duration = max(1, num_frames // 24)

            payload = {
                "image_uri": image_url,
                "prompt": prompt,
                "model": "ltx-2-3-pro",
                "duration": duration,
                "resolution": res_str,
                # Assembly owns audio (TTS/BGM/foley); the product feeds this
                # as silent motion input. Same field name + default-true
                # surcharge as the FAL proxy's generate_audio (audited
                # 2026-07-30 against https://docs.ltx.io/api-documentation/
                # api-reference/video-generation/image-to-video) — this was
                # previously omitted entirely, so native requests carried the
                # provider's default (true) and generated audio we discard.
                "generate_audio": False,
            }

            print(f"[LTX] Native API: {res_str}, {duration}s, model=ltx-2-3-pro")

            # LTX returns video bytes directly as MP4
            url = f"{self.NATIVE_BASE_URL}/image-to-video"
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Authorization": f"Bearer {self.ltx_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=600) as resp:
                video_data = resp.read()
                # An empty 200 body would otherwise be written as a 0-byte file
                # and returned as output_path (a false success the caller treats
                # as a real clip). Raise so the except-chain routes to FAL / None
                # (→ caller cascades) instead of accepting the empty result.
                if not video_data:
                    raise RuntimeError("LTX native returned empty 200 body")
                # Video bytes confirmed non-empty — billed regardless of what
                # happens next (this single response IS the delivery; there is
                # no separate URL step). Notify the caller BEFORE the disk
                # write so a subsequent write failure still reaches the
                # caller's spend accounting.
                if on_billed is not None:
                    try:
                        on_billed()
                    except Exception as callback_exc:
                        print(f"[LTX] Warning: on_billed callback raised: {callback_exc}")
                with open(output_path, "wb") as f:
                    f.write(video_data)

            file_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[LTX] Native video saved: {output_path} ({file_size:.1f} MB)")
            return output_path

        except urllib.request.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500] if hasattr(e, "read") else str(e)
            if getattr(e, "code", 0) >= 500 and self.fal_key and FAL_AVAILABLE:
                print(f"[LTX] Native {e.code}; falling back to FAL")
                return self._fal_generate(image_path, prompt, output_path, num_frames, resolution, camera_motion, on_billed=on_billed)
            print(f"[LTX] Native failed ({getattr(e, 'code', '?')}): {body}")
            return None
        except (urllib.request.URLError, TimeoutError, ConnectionError) as e:
            # Transient network errors (DNS, timeout, connection refused) — recover via FAL, like 5xx
            if self.fal_key and FAL_AVAILABLE:
                print(f"[LTX] Native network error ({e}); falling back to FAL")
                return self._fal_generate(image_path, prompt, output_path, num_frames, resolution, camera_motion, on_billed=on_billed)
            print(f"[LTX] Native network error (no fallback): {e}")
            return None
        except (OSError, json.JSONDecodeError) as e:
            # Local file-I/O / decode errors — no fallback (FAL can't fix disk/permission issues)
            print(f"[LTX] Local error (no fallback): {e}")
            return None
        except Exception as e:
            print(f"[LTX] Native generation failed: {e}")
            # Fall back to FAL if native fails
            if self.fal_key and FAL_AVAILABLE:
                print(f"[LTX] Falling back to FAL proxy...")
                return self._fal_generate(image_path, prompt, output_path, num_frames, resolution, camera_motion, on_billed=on_billed)
            return None

    def _native_transition(
        self,
        start_frame_path: str,
        end_frame_path: str,
        prompt: str,
        output_path: str,
        num_frames: int,
    ) -> str | None:
        """Native LTX Video API — keyframe transition."""
        try:
            with open(start_frame_path, "rb") as f:
                start_b64 = base64.b64encode(f.read()).decode("utf-8")
            with open(end_frame_path, "rb") as f:
                end_b64 = base64.b64encode(f.read()).decode("utf-8")

            payload = {
                "prompt": prompt,
                "start_image": start_b64,
                "end_image": end_b64,
                "num_frames": num_frames,
                "width": 1280,
                "height": 720,
            }

            result = self._native_request("/transition", payload)
            if not result:
                return None

            return self._download_native_result(result, output_path)

        except Exception as e:
            print(f"[LTX-TRANSITION] Native transition failed: {e}")
            return None

    def _native_request(self, endpoint: str, payload: dict) -> dict | None:
        """Send a request to the native LTX API."""
        url = f"{self.NATIVE_BASE_URL}{endpoint}"
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.ltx_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[LTX] Native API request failed: {e}")
            return None

    def _download_native_result(self, result: dict, output_path: str) -> str | None:
        """Download a video from a native API result."""
        video_url = result.get("video_url") or result.get("url")
        if not video_url:
            print("[LTX] ERROR: No video URL in native response")
            return None

        urllib.request.urlretrieve(video_url, output_path)
        print(f"[LTX] Video saved: {output_path}")
        return output_path


# ------------------------------------------------------------------
# Convenience function
# ------------------------------------------------------------------

_ltx_instance = None


def get_ltx_client() -> LTXVideoAPI:
    """Singleton accessor for the LTX Video client."""
    global _ltx_instance
    if _ltx_instance is None:
        _ltx_instance = LTXVideoAPI()
    return _ltx_instance


if __name__ == "__main__":
    client = LTXVideoAPI()
    print(f"LTX mode: {client.mode}")
