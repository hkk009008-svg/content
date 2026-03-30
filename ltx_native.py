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

try:
    import fal_client
    FAL_AVAILABLE = True
except ImportError:
    FAL_AVAILABLE = False


class LTXVideoAPI:
    """
    LTX Video 2.3 client.
    Checks LTX_API_KEY (native) first, falls back to FAL_KEY (proxy via fal.ai).
    Designed for easy swap to native endpoint when key arrives.
    """

    FAL_MODEL_ID = "fal-ai/ltx-2/image-to-video"

    # Native LTX Video API — https://docs.ltx.video
    NATIVE_BASE_URL = "https://api.ltx.video/v1"

    RESOLUTION_MAP = {
        "480p": {"width": 854, "height": 480},
        "720p": {"width": 1920, "height": 1080},  # LTX native doesn't support 720p — use 1080p
        "1080p": {"width": 1920, "height": 1080},
        "4k": {"width": 3840, "height": 2160},
        "4K": {"width": 3840, "height": 2160},
    }

    CAMERA_MOTIONS = [
        "dolly_in", "dolly_out", "jib_up", "jib_down",
        "pan_left", "pan_right", "tilt_up", "tilt_down",
        "zoom_in", "zoom_out", "crane_up", "crane_down",
        "truck_left", "truck_right", "static",
    ]

    def __init__(self):
        self.ltx_key = os.getenv("LTX_API_KEY")
        self.fal_key = os.getenv("FAL_KEY")
        self.mode = None

        if self.ltx_key:
            # Prefer native LTX API — direct, no proxy
            self.mode = "native"
            print("[LTX] Using native LTX Video API (api.ltx.video)")
        elif self.fal_key and FAL_AVAILABLE:
            self.mode = "fal"
            print("[LTX] Using FAL.ai proxy (fal-ai/ltx-2/image-to-video)")
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
        duration: int = 4,
        resolution: str = "720p",
        camera_motion: str | None = None,
    ) -> str | None:
        """
        Generate a video from a single image + prompt.
        Returns output_path on success, None on failure.
        """
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
            )
        else:
            return self._fal_generate(
                image_path=image_path,
                prompt=prompt,
                output_path=output_path,
                num_frames=num_frames,
                resolution=res,
                camera_motion=camera_motion,
            )

    def generate_transition(
        self,
        start_frame_path: str,
        end_frame_path: str,
        prompt: str,
        output_path: str,
        duration: int = 4,
    ) -> str | None:
        """
        LTX keyframe interpolation: smooth transition from start to end frame.
        Returns output_path on success, None on failure.
        """
        if not self.mode:
            print("[LTX-TRANSITION] Skipped — no API key configured")
            return None

        num_frames = duration * 24
        print(f"[LTX-TRANSITION] Generating {duration}s transition ({num_frames} frames)")
        print(f"[LTX-TRANSITION] Prompt: {prompt[:80]}...")

        if self.mode == "native":
            return self._native_transition(
                start_frame_path=start_frame_path,
                end_frame_path=end_frame_path,
                prompt=prompt,
                output_path=output_path,
                num_frames=num_frames,
            )
        else:
            return self._fal_transition(
                start_frame_path=start_frame_path,
                end_frame_path=end_frame_path,
                prompt=prompt,
                output_path=output_path,
                num_frames=num_frames,
            )

    def generate_4k(
        self,
        image_path: str,
        prompt: str,
        output_path: str,
        duration: int = 4,
    ) -> str | None:
        """
        Generate a 4K video — best for wide/landscape shots.
        Returns output_path on success, None on failure.
        """
        print(f"[LTX-4K] Forcing 4K resolution for landscape shot")
        return self.generate_video(
            image_path=image_path,
            prompt=prompt,
            output_path=output_path,
            duration=duration,
            resolution="4K",
            camera_motion=None,
        )

    # ------------------------------------------------------------------
    # FAL.ai proxy implementation
    # ------------------------------------------------------------------

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
    ) -> str | None:
        try:
            image_url = self._upload_to_fal(image_path)

            arguments = {
                "prompt": prompt,
                "image_url": image_url,
                "num_frames": num_frames,
                "width": resolution["width"],
                "height": resolution["height"],
            }

            if camera_motion and camera_motion in self.CAMERA_MOTIONS:
                arguments["camera_motion"] = camera_motion
                print(f"[LTX] Camera motion: {camera_motion}")

            result = fal_client.subscribe(
                self.FAL_MODEL_ID,
                arguments=arguments,
                with_logs=True,
            )

            video_url = result.get("video", {}).get("url")
            if not video_url:
                print("[LTX] ERROR: No video URL in response")
                return None

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

            arguments = {
                "prompt": prompt,
                "image_url": start_url,
                "end_image_url": end_url,
                "num_frames": num_frames,
                "width": 1280,
                "height": 720,
            }

            result = fal_client.subscribe(
                self.FAL_MODEL_ID,
                arguments=arguments,
                with_logs=True,
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
                with open(output_path, "wb") as f:
                    f.write(video_data)

            file_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[LTX] Native video saved: {output_path} ({file_size:.1f} MB)")
            return output_path

        except urllib.request.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
            print(f"[LTX] Native generation failed: {e} — {error_body[:500]}")
        except Exception as e:
            print(f"[LTX] Native generation failed: {e}")
            # Fall back to FAL if native fails
            if self.fal_key and FAL_AVAILABLE:
                print(f"[LTX] Falling back to FAL proxy...")
                return self._fal_generate(image_path, prompt, output_path, num_frames, resolution, camera_motion)
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
