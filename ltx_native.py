"""LTX Video 2.3 image-to-video client.

Native mode uses LTX's production ``api.ltx.io`` contract: signed input
upload, asynchronous v2 submission, a durable local job record, bounded
polling, and validated atomic MP4 publication.  FAL remains a pre-submission
fallback when native LTX is unavailable; an accepted native job is never
duplicated through the FAL path.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from typing import Callable
from urllib.parse import urlparse

import requests
from filelock import FileLock

from config.settings import settings
from cinema.fal_limits import FAL_TIMEOUT_VIDEO_S
from performance._net import safe_download, validate_video_artifact

try:
    import fal_client
    FAL_AVAILABLE = True
except ImportError:
    FAL_AVAILABLE = False


class LTXContractViolation(ValueError):
    """A locally detected request violation, always found before provider I/O.

    Public duration violations surface to the caller. Native input format and
    size violations are logged as a local failure. Neither is rerouted through
    FAL: a malformed request must not appear to succeed after being coerced by
    a different provider contract.
    """


class LTXJobPending(RuntimeError):
    """Accepted or submission-ambiguous LTX work must not enter a cascade.

    ``status`` is the caller-facing disposition (``pending`` or
    ``recovery_required``); ``provider_status`` is the last durable/provider
    state when one is known.  The exception deliberately carries only local
    recovery identifiers, never signed upload/output URLs.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str = "job_pending",
        status: str = "pending",
        job_id: str | None = None,
        state_path: str | None = None,
        request_fingerprint: str | None = None,
        provider_status: str | None = None,
        duration_s: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.status = status
        self.job_id = job_id
        self.state_path = state_path
        self.request_fingerprint = request_fingerprint
        self.provider_status = provider_status
        self.duration_s = duration_s

    def attach_context(
        self,
        *,
        job_id: str | None,
        state_path: str | None,
        request_fingerprint: str | None,
        provider_status: str | None,
        duration_s: int | None,
    ) -> "LTXJobPending":
        """Fill context omitted by the lower-level polling helper."""
        if self.job_id is None:
            self.job_id = job_id
        if self.state_path is None:
            self.state_path = state_path
        if self.request_fingerprint is None:
            self.request_fingerprint = request_fingerprint
        if self.provider_status is None:
            self.provider_status = provider_status
        if self.duration_s is None:
            self.duration_s = duration_s
        return self


class LTXVideoAPI:
    """
    LTX Video 2.3 client.
    Checks LTX_API_KEY (native) first, falls back to FAL_KEY (proxy via fal.ai).
    """

    # LTX-2.3 (bumped 2026-07-11 from fal-ai/ltx-2; schema from fal's OpenAPI
    # spec): params are image_url + string resolution + int duration enum
    # {6,8,10}; NO num_frames/width/height, NO camera_motion param (prompt-text
    # only), NO negative_prompt; generate_audio defaults true (+~$0.02/s
    # apparent surcharge — we send False; assembly owns audio). Fast tier
    # (fal-ai/ltx-2.3/image-to-video/fast) unlocks 12-20s at 25fps/1080p only.
    FAL_MODEL_ID = "fal-ai/ltx-2.3/image-to-video"

    # Native LTX production API — https://docs.ltx.io/async-jobs
    NATIVE_BASE_URL = "https://api.ltx.io"
    NATIVE_UPLOAD_PATH = "/v1/upload"
    NATIVE_ASYNC_PATH = "/v2/image-to-video"
    NATIVE_POLL_INTERVAL_S = 5
    NATIVE_MAX_POLLS = max(1, FAL_TIMEOUT_VIDEO_S // NATIVE_POLL_INTERVAL_S)
    NATIVE_POLL_TIMEOUT_S = FAL_TIMEOUT_VIDEO_S
    NATIVE_API_TIMEOUT = (20, 60)
    NATIVE_UPLOAD_TIMEOUT = (20, 300)
    INPUT_IMAGE_MAX_BYTES = 15 * 1024 * 1024
    JOB_STATE_SCHEMA_VERSION = 1
    _JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    _REQUEST_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")

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
    # video-generation/image-to-video (2026-08-04 audit). Both the native
    # api.ltx.io async-v2 endpoint (model="ltx-2-3-pro") and the FAL proxy
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
        # Per-call recovery/billing metadata.  These stay additive to the
        # historical ``str | None`` return contract.
        self.last_job_id: str | None = None
        self.last_request_fingerprint: str | None = None
        self.last_duration_s: int | None = None

        if self.ltx_key:
            # Prefer native LTX API — direct, no proxy
            self.mode = "native"
            print("[LTX] Using native LTX Video API (api.ltx.io async v2)")
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
        *,
        expected_job_id: str | None = None,
        expected_request_fingerprint: str | None = None,
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
            LTXJobPending: Native submission may have been accepted, or an
                accepted job/output needs recovery. Callers must surface this
                state and must not dispatch another provider for the shot.

        Args:
            on_billed: Optional zero-arg callback invoked exactly once, the
                moment the provider has confirmed billable video output — a
                video URL for the fal path (``_fal_generate``), or the
                completed job's ``result.video_url`` for the native path
                (``_native_generate``) —
                the repo's billed bar (see phase_c_ffmpeg._note_billed_attempt).
                Fires BEFORE the download/write that follows so a caller can
                record the spend even when that download/write fails and
                this method still returns None (money-gate 2026-07-11 class,
                extended to the native adapters in slice M2). Threaded
                through the native→fal fallback so exactly one path fires it.
                Exceptions raised by the callback are logged and swallowed.
            expected_job_id: Optional opaque native job binding supplied by a
                recovery caller. When present, an existing matching sidecar is
                required and a fresh provider submission is forbidden.
            expected_request_fingerprint: Optional SHA-256 request binding.
                A mismatch with the current image/prompt/duration/resolution
                raises ``LTXJobPending(reason="request_changed")`` before upload.
        """
        self.last_job_id = None
        self.last_request_fingerprint = None
        self.last_duration_s = None
        if duration not in self.DURATION_SECONDS:
            raise LTXContractViolation(
                f"LTX duration must be one of {self.DURATION_SECONDS} seconds "
                f"(the ltx-2-3-pro profile enum — https://docs.ltx.io/models); "
                f"got {duration!r}. Snap the caller's requested duration via "
                f"LTXVideoAPI.nearest_supported_duration() before calling "
                f"generate_video()."
            )
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 5000:
            raise LTXContractViolation(
                "LTX prompt must be a non-empty string of at most 5000 characters"
            )
        self.last_duration_s = duration

        expected_binding = (
            expected_job_id is not None
            or expected_request_fingerprint is not None
        )
        if expected_binding and self.mode != "native":
            raise LTXJobPending(
                "The persisted LTX job cannot be resumed without native LTX mode",
                reason="job_binding_unavailable",
                status="recovery_required",
                job_id=(expected_job_id if isinstance(expected_job_id, str) else None),
                request_fingerprint=(
                    expected_request_fingerprint
                    if isinstance(expected_request_fingerprint, str)
                    else None
                ),
                provider_status="unknown",
                duration_s=duration,
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
                expected_job_id=expected_job_id,
                expected_request_fingerprint=expected_request_fingerprint,
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

    @classmethod
    def _prompt_with_camera_motion(
        cls,
        prompt: str,
        camera_motion: str | None,
    ) -> str:
        """Fold the repo's broader camera vocabulary into prompt language.

        LTX's direct ``camera_motion`` enum is narrower than this adapter's
        historical vocabulary, so prompt folding preserves existing behavior
        without putting an unsupported enum value on the wire.
        """
        if camera_motion and camera_motion in cls.CAMERA_MOTIONS:
            return f"{prompt}. Camera: {camera_motion.replace('_', ' ')}."
        return prompt

    @classmethod
    def _download_video(cls, video_url: str, output_path: str) -> str | None:
        """Download and publish only a MIME-true, ffprobe-valid MP4 video."""
        return safe_download(
            video_url,
            output_path,
            allowed_content_types=("video/mp4",),
            content_validator=validate_video_artifact,
        )

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

            folded_prompt = self._prompt_with_camera_motion(prompt, camera_motion)
            if folded_prompt != prompt:
                print(f"[LTX] Camera motion (prompt-folded): {camera_motion}")

            arguments = {
                "prompt": folded_prompt,
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

            if self._download_video(video_url, output_path) is None:
                print("[LTX] ERROR: FAL output failed MP4 download validation")
                return None
            print(f"[LTX] Video saved: {output_path}")
            return output_path

        except Exception as e:
            print(f"[LTX] FAL generation failed: {e}")
            return None


    # ------------------------------------------------------------------
    # Native LTX API implementation — signed upload + async v2 job
    # ------------------------------------------------------------------

    @staticmethod
    def _json_object(response: requests.Response, operation: str) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"LTX {operation} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"LTX {operation} returned non-object JSON")
        return payload

    @staticmethod
    def _image_mime_type(image_path: str) -> str:
        with open(image_path, "rb") as source:
            header = source.read(16)
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if header.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
            return "image/webp"
        raise LTXContractViolation(
            "LTX input image must be a MIME-true PNG, JPEG, or WebP file"
        )

    @classmethod
    def _image_sha256(cls, image_path: str) -> str:
        try:
            size = os.path.getsize(image_path)
        except OSError as exc:
            raise LTXContractViolation(
                f"LTX input image is not readable: {image_path}"
            ) from exc
        if size <= 0:
            raise LTXContractViolation("LTX input image must not be empty")
        if size > cls.INPUT_IMAGE_MAX_BYTES:
            raise LTXContractViolation(
                "LTX image-to-video input exceeds the 15 MB endpoint limit"
            )

        digest = hashlib.sha256()
        with open(image_path, "rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _request_fingerprint(cls, image_path: str, request: dict) -> str:
        descriptor = {
            "endpoint": "image-to-video",
            "image_sha256": cls._image_sha256(image_path),
            "request": request,
        }
        canonical = json.dumps(
            descriptor,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @classmethod
    def _job_state_path(cls, output_path: str, fingerprint: str) -> str:
        output_dir = os.path.dirname(output_path) or "."
        return os.path.join(
            output_dir,
            f".ltx-image-to-video-{fingerprint[:24]}.job.json",
        )

    @classmethod
    def _write_job_state(cls, state_path: str, state: dict) -> None:
        """Persist a job record atomically before polling can begin."""
        state_dir = os.path.dirname(state_path) or "."
        os.makedirs(state_dir, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(state_path)}.",
            suffix=".tmp",
            dir=state_dir,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as target:
                json.dump(state, target, sort_keys=True, separators=(",", ":"))
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())
            os.replace(temp_path, state_path)
            temp_path = ""
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except FileNotFoundError:
                    pass

    @classmethod
    def _claim_submission_state(
        cls,
        state_path: str,
        fingerprint: str,
        duration_s: int,
    ) -> dict:
        """Exclusively claim one provider submission for a fingerprint.

        The claim is the job-state file itself and is created with ``O_EXCL``.
        Therefore two processes cannot both cross this boundary, and a crash
        anywhere after it (including after the POST but before its response is
        persisted) leaves a durable fail-closed recovery marker.

        A provider-confirmed ``failed``/``expired`` state is the sole exception:
        it no longer represents live or ambiguous work, so it may be replaced by
        one fresh exclusive claim.  The adjacent lock serializes the terminal
        compare/remove/create transition; without it, two retrying processes
        could both observe the terminal file and delete each other's new claim.
        """
        state_dir = os.path.dirname(state_path) or "."
        os.makedirs(state_dir, exist_ok=True)
        lock_path = f"{state_path}.lock"
        # Contention blocks only on this short local file transition. FileLock's
        # OS lock is released if a claimant process exits, while a timeout here
        # could be mistaken upstream for a safe pre-submit failure and cascade.
        with FileLock(lock_path):
            try:
                fd = os.open(
                    state_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
            except FileExistsError:
                if not cls._terminal_state_is_supersedable(
                    state_path,
                    fingerprint,
                ):
                    raise
                os.remove(state_path)
                fd = os.open(
                    state_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )

            now = time.time()
            state = {
                "schema_version": cls.JOB_STATE_SCHEMA_VERSION,
                "provider": "ltx",
                "endpoint": "image-to-video",
                "request_fingerprint": fingerprint,
                "duration_s": duration_s,
                "status": "submission_claimed",
                "claimed_at": now,
                "updated_at": now,
            }
            with os.fdopen(fd, "w", encoding="utf-8") as target:
                json.dump(state, target, sort_keys=True, separators=(",", ":"))
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())

            # Make the directory entry durable as well as the file contents.
            # Some platforms do not expose O_DIRECTORY; a regular read-only
            # directory descriptor is sufficient there.
            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            try:
                directory_fd = os.open(state_dir, directory_flags)
            except OSError:
                directory_fd = None
            if directory_fd is not None:
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            return state

    @classmethod
    def _terminal_state_is_supersedable(
        cls,
        state_path: str,
        fingerprint: str,
    ) -> bool:
        """Return whether an exact, provider-terminal sidecar may be replaced."""

        try:
            with open(state_path, "r", encoding="utf-8") as source:
                state = json.load(source)
        except (OSError, json.JSONDecodeError):
            return False
        return bool(
            isinstance(state, dict)
            and state.get("schema_version") == cls.JOB_STATE_SCHEMA_VERSION
            and state.get("provider") == "ltx"
            and state.get("endpoint") == "image-to-video"
            and state.get("request_fingerprint") == fingerprint
            and state.get("status") in {"failed", "expired"}
            and isinstance(state.get("job_id"), str)
            and cls._JOB_ID_PATTERN.fullmatch(state["job_id"]) is not None
        )

    @classmethod
    def _load_resumable_job(
        cls,
        state_path: str,
        fingerprint: str,
        expected_job_id: str | None = None,
    ) -> dict | None:
        try:
            with open(state_path, "r", encoding="utf-8") as source:
                state = json.load(source)
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise LTXJobPending(
                f"LTX job state is unreadable: {state_path}",
                reason="job_state_unreadable",
                status="recovery_required",
                state_path=state_path,
                request_fingerprint=fingerprint,
                provider_status="unknown",
            ) from exc

        if not isinstance(state, dict):
            raise LTXJobPending(
                f"LTX job state is not an object: {state_path}",
                reason="job_state_invalid",
                status="recovery_required",
                state_path=state_path,
                request_fingerprint=fingerprint,
                provider_status="unknown",
            )
        if state.get("schema_version") != cls.JOB_STATE_SCHEMA_VERSION:
            raise LTXJobPending(
                f"LTX job state schema is unsupported: {state_path}",
                reason="job_state_invalid",
                status="recovery_required",
                state_path=state_path,
                request_fingerprint=fingerprint,
                provider_status=str(state.get("status") or "unknown"),
            )
        if state.get("request_fingerprint") != fingerprint:
            raise LTXJobPending(
                f"LTX job state fingerprint does not match its path: {state_path}",
                reason="job_state_invalid",
                status="recovery_required",
                state_path=state_path,
                request_fingerprint=fingerprint,
                provider_status=str(state.get("status") or "unknown"),
            )
        if state.get("endpoint") != "image-to-video":
            raise LTXJobPending(
                f"LTX job state endpoint is invalid: {state_path}",
                reason="job_state_invalid",
                status="recovery_required",
                state_path=state_path,
                request_fingerprint=fingerprint,
                provider_status=str(state.get("status") or "unknown"),
            )
        provider_status = state.get("status")
        if provider_status in {"failed", "expired"}:
            return None
        if (
            provider_status == "submission_claimed"
            and isinstance(expected_job_id, str)
            and cls._JOB_ID_PATTERN.fullmatch(expected_job_id) is not None
        ):
            # The generation POST returned an exact job ID, but persisting the
            # accepted state may have failed.  A controller that durably kept
            # that opaque ID can bind it back to this exact-fingerprint claim
            # and poll it without another submission.  The default/no-binding
            # path below remains fail closed.
            return {
                **state,
                "job_id": expected_job_id,
                "status": "submitted",
                "recovered_from": "submission_claimed",
            }
        if provider_status in {"submission_claimed", "submission_unknown"}:
            raise LTXJobPending(
                "A prior LTX submit outcome is unknown; operator recovery is required",
                reason="submit_outcome_unknown",
                status="recovery_required",
                state_path=state_path,
                request_fingerprint=fingerprint,
                provider_status=str(provider_status),
                duration_s=(
                    state.get("duration_s")
                    if isinstance(state.get("duration_s"), int)
                    else None
                ),
            )
        if (
            not isinstance(state.get("job_id"), str)
            or cls._JOB_ID_PATTERN.fullmatch(state["job_id"]) is None
        ):
            raise LTXJobPending(
                f"LTX accepted-job state has no valid job ID: {state_path}",
                reason="job_state_invalid",
                status="recovery_required",
                state_path=state_path,
                request_fingerprint=fingerprint,
                provider_status=str(provider_status or "unknown"),
            )
        if provider_status not in {"submitted", "pending", "processing", "completed"}:
            raise LTXJobPending(
                f"LTX accepted-job state has an invalid status: {state_path}",
                reason="job_state_invalid",
                status="recovery_required",
                job_id=state["job_id"],
                state_path=state_path,
                request_fingerprint=fingerprint,
                provider_status=str(provider_status or "unknown"),
            )
        return state

    @classmethod
    def _write_submission_unknown_state(
        cls,
        state_path: str,
        fingerprint: str,
        duration_s: int,
    ) -> None:
        """Durably block automatic resubmission when POST outcome was lost."""
        cls._write_job_state(
            state_path,
            {
                "schema_version": cls.JOB_STATE_SCHEMA_VERSION,
                "provider": "ltx",
                "endpoint": "image-to-video",
                "request_fingerprint": fingerprint,
                "duration_s": duration_s,
                "status": "submission_unknown",
                "updated_at": time.time(),
            },
        )

    def _native_upload(self, image_path: str) -> str:
        """Upload an input image through LTX's signed ``/v1/upload`` flow."""
        image_mime = self._image_mime_type(image_path)
        upload_response = requests.post(
            f"{self.NATIVE_BASE_URL}{self.NATIVE_UPLOAD_PATH}",
            headers={"Authorization": f"Bearer {self.ltx_key}"},
            timeout=self.NATIVE_API_TIMEOUT,
            allow_redirects=False,
        )
        upload_response.raise_for_status()
        if upload_response.status_code != 200:
            raise RuntimeError(
                f"LTX upload-ticket returned unexpected HTTP {upload_response.status_code}"
            )
        ticket = self._json_object(upload_response, "upload-ticket request")
        upload_url = ticket.get("upload_url")
        storage_uri = ticket.get("storage_uri")
        required_headers = ticket.get("required_headers", {})

        parsed_upload = urlparse(upload_url) if isinstance(upload_url, str) else None
        if (
            parsed_upload is None
            or parsed_upload.scheme.lower() != "https"
            or not parsed_upload.netloc
        ):
            raise RuntimeError("LTX upload-ticket returned an invalid HTTPS upload_url")
        if not isinstance(storage_uri, str) or not storage_uri.startswith("ltx://"):
            raise RuntimeError("LTX upload-ticket returned an invalid storage_uri")
        if not isinstance(required_headers, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in required_headers.items()
        ):
            raise RuntimeError("LTX upload-ticket returned invalid required_headers")

        content_type_keys = {
            key.lower(): key for key in required_headers if isinstance(key, str)
        }
        existing_content_type_key = content_type_keys.get("content-type")
        if existing_content_type_key is not None:
            required_content_type = required_headers[existing_content_type_key]
            if required_content_type.split(";", 1)[0].strip().lower() != image_mime:
                raise RuntimeError(
                    "LTX upload-ticket Content-Type disagrees with the input bytes"
                )
        else:
            required_headers["Content-Type"] = image_mime

        with open(image_path, "rb") as source:
            put_response = requests.put(
                upload_url,
                data=source,
                headers=required_headers,
                timeout=self.NATIVE_UPLOAD_TIMEOUT,
                allow_redirects=False,
            )
        put_response.raise_for_status()
        if put_response.status_code not in {200, 201, 204}:
            raise RuntimeError(
                f"LTX signed upload returned unexpected HTTP {put_response.status_code}"
            )
        return storage_uri

    def _submit_native_job(self, payload: dict) -> tuple[str, str | None]:
        response = requests.post(
            f"{self.NATIVE_BASE_URL}{self.NATIVE_ASYNC_PATH}",
            headers={
                "Authorization": f"Bearer {self.ltx_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.NATIVE_API_TIMEOUT,
            allow_redirects=False,
        )
        response.raise_for_status()
        if response.status_code != 202:
            raise RuntimeError(
                f"LTX async submit returned unexpected HTTP {response.status_code}"
            )
        submitted = self._json_object(response, "async submit")
        job_id = submitted.get("id")
        if (
            not isinstance(job_id, str)
            or self._JOB_ID_PATTERN.fullmatch(job_id) is None
        ):
            raise RuntimeError("LTX async submit returned an invalid job id")
        created_at = submitted.get("created_at")
        return job_id, created_at if isinstance(created_at, str) else None

    def _poll_native_job(
        self,
        job_id: str,
        state_path: str,
        state: dict,
    ) -> dict:
        status_url = (
            f"{self.NATIVE_BASE_URL}{self.NATIVE_ASYNC_PATH}/{job_id}"
        )
        deadline = time.monotonic() + self.NATIVE_POLL_TIMEOUT_S

        def bounded_sleep(requested_delay: float) -> None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LTXJobPending(
                    f"LTX job {job_id} exceeded the "
                    f"{self.NATIVE_POLL_TIMEOUT_S}s polling deadline",
                    reason="poll_deadline_exceeded",
                    provider_status=str(state.get("status") or "pending"),
                )
            time.sleep(min(requested_delay, remaining))

        for poll_index in range(self.NATIVE_MAX_POLLS):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LTXJobPending(
                    f"LTX job {job_id} exceeded the "
                    f"{self.NATIVE_POLL_TIMEOUT_S}s polling deadline",
                    reason="poll_deadline_exceeded",
                    provider_status=str(state.get("status") or "pending"),
                )
            phase_timeout = max(
                0.001,
                min(
                    float(self.NATIVE_API_TIMEOUT[0]),
                    float(self.NATIVE_API_TIMEOUT[1]),
                    remaining / 2,
                ),
            )
            try:
                response = requests.get(
                    status_url,
                    headers={"Authorization": f"Bearer {self.ltx_key}"},
                    timeout=(phase_timeout, phase_timeout),
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                if poll_index + 1 >= self.NATIVE_MAX_POLLS:
                    raise LTXJobPending(
                        f"LTX job {job_id} polling remained unavailable",
                        reason="poll_unavailable",
                        provider_status=str(state.get("status") or "pending"),
                    ) from exc
                print(f"[LTX] Transient job-poll network error: {exc}")
                bounded_sleep(float(self.NATIVE_POLL_INTERVAL_S))
                continue

            # A 404 is ambiguous: it can be eventual consistency immediately
            # after acceptance, and the public contract provides no safe
            # idempotent resubmit key. Preserve/retry the accepted job instead
            # of marking it expired and risking duplicate paid generation.
            if response.status_code in {404, 429, 500, 503, 529}:
                if poll_index + 1 >= self.NATIVE_MAX_POLLS:
                    raise LTXJobPending(
                        f"LTX job {job_id} polling remained HTTP "
                        f"{response.status_code}",
                        reason="poll_http_unavailable",
                        provider_status=str(state.get("status") or "pending"),
                    )
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = max(0.0, min(float(retry_after), 30.0))
                except (TypeError, ValueError):
                    delay = float(self.NATIVE_POLL_INTERVAL_S)
                print(
                    f"[LTX] Ambiguous/transient job-poll HTTP "
                    f"{response.status_code}; "
                    f"retrying in {delay:g}s"
                )
                bounded_sleep(delay)
                continue
            response.raise_for_status()
            if response.status_code != 200:
                raise RuntimeError(
                    f"LTX job poll returned unexpected HTTP {response.status_code}"
                )

            payload = self._json_object(response, "job poll")
            response_job_id = payload.get("id")
            if response_job_id is not None and response_job_id != job_id:
                raise RuntimeError("LTX job poll returned a mismatched job id")
            status = payload.get("status")
            if status not in {"pending", "processing", "completed", "failed"}:
                raise RuntimeError(f"LTX job returned unknown status {status!r}")

            state = {**state, "status": status, "updated_at": time.time()}
            if status == "failed":
                error = payload.get("error")
                if isinstance(error, dict):
                    state["error"] = {
                        key: str(error[key])[:500]
                        for key in ("type", "message")
                        if key in error
                    }
            try:
                self._write_job_state(state_path, state)
            except OSError as exc:
                # The accepted job ID was durably written before polling. A
                # status-update write failure does not erase that recovery
                # anchor, and an explicit provider terminal failure must still
                # remain terminal for this invocation.
                print(f"[LTX] Warning: could not update job state: {exc}")
            if status in {"completed", "failed"}:
                return payload
            if poll_index + 1 < self.NATIVE_MAX_POLLS:
                bounded_sleep(float(self.NATIVE_POLL_INTERVAL_S))

        raise LTXJobPending(
            f"LTX job {job_id} is still running after "
            f"{self.NATIVE_MAX_POLLS} polls",
            reason="poll_window_exhausted",
            provider_status=str(state.get("status") or "pending"),
        )

    def _native_generate(
        self,
        image_path: str,
        prompt: str,
        output_path: str,
        num_frames: int,
        resolution: dict,
        camera_motion: str | None = None,
        on_billed: Callable[[], None] | None = None,
        expected_job_id: str | None = None,
        expected_request_fingerprint: str | None = None,
    ) -> str | None:
        """Generate through LTX async v2, resuming an identical accepted job."""
        job_accepted = False
        submission_started = False
        submission_claimed = False
        job_id: str | None = None
        state_path: str | None = None
        fingerprint: str | None = None
        state: dict | None = None
        duration: int | None = None
        try:
            res_str = f"{resolution['width']}x{resolution['height']}"
            duration = max(1, num_frames // 24)
            self.last_duration_s = duration
            folded_prompt = self._prompt_with_camera_motion(prompt, camera_motion)
            request_without_image = {
                "prompt": folded_prompt,
                "model": "ltx-2-3-pro",
                "duration": duration,
                "resolution": res_str,
                "generate_audio": False,
            }
            fingerprint = self._request_fingerprint(
                image_path,
                request_without_image,
            )
            self.last_request_fingerprint = fingerprint

            binding_required = (
                expected_job_id is not None
                or expected_request_fingerprint is not None
            )
            if (
                expected_job_id is not None
                and (
                    not isinstance(expected_job_id, str)
                    or self._JOB_ID_PATTERN.fullmatch(expected_job_id) is None
                )
            ):
                raise LTXJobPending(
                    "The expected LTX job ID is invalid",
                    reason="job_binding_invalid",
                    status="recovery_required",
                    state_path=self._job_state_path(output_path, fingerprint),
                    request_fingerprint=fingerprint,
                    provider_status="unknown",
                    duration_s=duration,
                )
            if (
                expected_request_fingerprint is not None
                and (
                    not isinstance(expected_request_fingerprint, str)
                    or self._REQUEST_FINGERPRINT_PATTERN.fullmatch(
                        expected_request_fingerprint
                    )
                    is None
                )
            ):
                raise LTXJobPending(
                    "The expected LTX request fingerprint is invalid",
                    reason="job_binding_invalid",
                    status="recovery_required",
                    job_id=expected_job_id,
                    state_path=self._job_state_path(output_path, fingerprint),
                    request_fingerprint=fingerprint,
                    provider_status="unknown",
                    duration_s=duration,
                )
            if expected_job_id is not None:
                job_id = expected_job_id
                self.last_job_id = expected_job_id
            if (
                expected_request_fingerprint is not None
                and expected_request_fingerprint != fingerprint
            ):
                raise LTXJobPending(
                    "The current LTX request differs from the persisted job binding",
                    reason="request_changed",
                    status="recovery_required",
                    job_id=expected_job_id,
                    state_path=self._job_state_path(output_path, fingerprint),
                    request_fingerprint=expected_request_fingerprint,
                    provider_status="unknown",
                    duration_s=duration,
                )

            state_path = self._job_state_path(output_path, fingerprint)
            state = self._load_resumable_job(
                state_path,
                fingerprint,
                expected_job_id=expected_job_id,
            )

            if binding_required and state is None:
                raise LTXJobPending(
                    "The persisted LTX job state is missing or terminal",
                    reason="job_state_missing",
                    status="recovery_required",
                    job_id=expected_job_id,
                    state_path=state_path,
                    request_fingerprint=fingerprint,
                    provider_status="unknown",
                    duration_s=duration,
                )

            if state is not None:
                if (
                    expected_job_id is not None
                    and state["job_id"] != expected_job_id
                ):
                    raise LTXJobPending(
                        "The persisted LTX state belongs to a different job ID",
                        reason="job_id_mismatch",
                        status="recovery_required",
                        job_id=expected_job_id,
                        state_path=state_path,
                        request_fingerprint=fingerprint,
                        provider_status=str(state.get("status") or "unknown"),
                        duration_s=duration,
                    )
                job_id = state["job_id"]
                self.last_job_id = job_id
                job_accepted = True
                print(f"[LTX] Resuming native async job {job_id}")
            else:
                storage_uri = self._native_upload(image_path)
                payload = {"image_uri": storage_uri, **request_without_image}
                print(
                    f"[LTX] Native async API: {res_str}, {duration}s, "
                    "model=ltx-2-3-pro"
                )
                # The exclusive state-file claim is the one-way safety fence.
                # It is durable before POST, so concurrent callers and a crash
                # between provider acceptance and local ID persistence cannot
                # create a second paid job for the same fingerprint.
                submission_claimed = False
                claim_owned = False
                try:
                    state = self._claim_submission_state(
                        state_path,
                        fingerprint,
                        duration,
                    )
                    submission_claimed = True
                    claim_owned = True
                except FileExistsError:
                    state = self._load_resumable_job(state_path, fingerprint)
                    if state is None:
                        raise LTXJobPending(
                            "An existing LTX state blocks a duplicate submission",
                            reason="job_state_conflict",
                            status="recovery_required",
                            state_path=state_path,
                            request_fingerprint=fingerprint,
                            provider_status="terminal",
                            duration_s=duration,
                        )
                except OSError:
                    # An O_EXCL claim can exist even when its write/fsync then
                    # fails. Preserve fail-closed handling only when a sidecar
                    # is actually present; a pre-claim filesystem error did not
                    # cross the provider-submission boundary.
                    submission_claimed = os.path.exists(state_path)
                    raise

                if not claim_owned:
                    job_id = state["job_id"]
                    self.last_job_id = job_id
                    job_accepted = True
                    print(f"[LTX] Resuming concurrently claimed job {job_id}")
                else:
                    # Once this POST starts, a lost response is ambiguous: the
                    # provider may have accepted a paid job. Never duplicate
                    # that uncertainty through FAL in this invocation.
                    submission_started = True
                    job_id, created_at = self._submit_native_job(payload)
                    self.last_job_id = job_id
                    job_accepted = True
                    state = {
                        "schema_version": self.JOB_STATE_SCHEMA_VERSION,
                        "provider": "ltx",
                        "endpoint": "image-to-video",
                        "job_id": job_id,
                        "request_fingerprint": fingerprint,
                        "duration_s": duration,
                        "status": "submitted",
                        "created_at": created_at,
                        "updated_at": time.time(),
                    }
                    # The durable ID is committed before the first status request.
                    self._write_job_state(state_path, state)

            terminal = self._poll_native_job(job_id, state_path, state)
            if terminal.get("status") == "failed":
                error = terminal.get("error")
                message = error.get("message") if isinstance(error, dict) else error
                print(f"[LTX] Native job {job_id} failed: {message or 'unknown error'}")
                return None

            result = terminal.get("result")
            video_url = result.get("video_url") if isinstance(result, dict) else None
            if not isinstance(video_url, str) or not video_url:
                raise LTXJobPending(
                    f"LTX completed job {job_id} returned no video_url",
                    reason="completed_output_missing",
                    status="recovery_required",
                    job_id=job_id,
                    state_path=state_path,
                    request_fingerprint=fingerprint,
                    provider_status="completed",
                )

            # Completed output is the provider's billing boundary. Notify
            # before download so an invalid/failed publication still records
            # the accepted spend in the caller.
            if on_billed is not None:
                try:
                    on_billed()
                except Exception as callback_exc:
                    print(f"[LTX] Warning: on_billed callback raised: {callback_exc}")

            if self._download_video(video_url, output_path) is None:
                raise LTXJobPending(
                    f"LTX job {job_id} output failed download or MP4 validation",
                    reason="completed_output_invalid",
                    status="recovery_required",
                    job_id=job_id,
                    state_path=state_path,
                    request_fingerprint=fingerprint,
                    provider_status="completed",
                )
            file_size = os.path.getsize(output_path) / (1024 * 1024)
            print(
                f"[LTX] Native video saved: {output_path} "
                f"({file_size:.1f} MB, job={job_id})"
            )
            return output_path

        except LTXContractViolation as exc:
            print(f"[LTX] Local contract violation (no fallback): {exc}")
            return None
        except LTXJobPending as exc:
            provider_status = (
                str(state.get("status"))
                if isinstance(state, dict) and state.get("status")
                else None
            )
            exc.attach_context(
                job_id=job_id,
                state_path=state_path,
                request_fingerprint=fingerprint,
                provider_status=provider_status,
                duration_s=duration,
            )
            print(f"[LTX] {exc}; caller must defer instead of cascading")
            raise
        except requests.RequestException as exc:
            print(f"[LTX] Native network failure: {exc}")
            if job_accepted or submission_started or submission_claimed:
                reason = (
                    "accepted_job_network_error"
                    if job_accepted
                    else "submit_outcome_unknown"
                )
                provider_status = (
                    str(state.get("status"))
                    if isinstance(state, dict) and state.get("status")
                    else "submission_unknown"
                )
                if not job_accepted and state_path and fingerprint and duration:
                    try:
                        self._write_submission_unknown_state(
                            state_path,
                            fingerprint,
                            duration,
                        )
                    except OSError as state_exc:
                        print(
                            "[LTX] Warning: could not persist ambiguous-submit "
                            f"marker: {state_exc}"
                        )
                raise LTXJobPending(
                    "LTX native work may have been accepted; recovery is required",
                    reason=reason,
                    status="recovery_required",
                    job_id=job_id,
                    state_path=state_path,
                    request_fingerprint=fingerprint,
                    provider_status=provider_status,
                    duration_s=duration,
                ) from exc
            if (
                self.fal_key
                and FAL_AVAILABLE
            ):
                print("[LTX] Pre-submission failure; falling back to FAL proxy")
                return self._fal_generate(
                    image_path,
                    prompt,
                    output_path,
                    num_frames,
                    resolution,
                    camera_motion,
                    on_billed=on_billed,
                )
            return None
        except OSError as exc:
            if job_accepted or submission_started or submission_claimed:
                raise LTXJobPending(
                    "LTX accepted work hit a local persistence/output error",
                    reason="accepted_job_local_error",
                    status="recovery_required",
                    job_id=job_id,
                    state_path=state_path,
                    request_fingerprint=fingerprint,
                    provider_status=(
                        str(state.get("status"))
                        if isinstance(state, dict) and state.get("status")
                        else "submission_unknown"
                    ),
                    duration_s=duration,
                ) from exc
            print(f"[LTX] Local error (no fallback): {exc}")
            return None
        except Exception as exc:
            print(f"[LTX] Native generation failed: {exc}")
            # Signed-upload failures happen before generation and are safe to
            # route through the configured proxy. Once async submission starts
            # (or a prior job is resumed), doing so could create duplicate paid
            # work and is deliberately refused.
            if job_accepted or submission_started or submission_claimed:
                if not job_accepted and state_path and fingerprint and duration:
                    try:
                        self._write_submission_unknown_state(
                            state_path,
                            fingerprint,
                            duration,
                        )
                    except OSError as state_exc:
                        print(
                            "[LTX] Warning: could not persist ambiguous-submit "
                            f"marker: {state_exc}"
                        )
                raise LTXJobPending(
                    "LTX native work may have been accepted; recovery is required",
                    reason=(
                        "accepted_job_error"
                        if job_accepted
                        else "submit_outcome_unknown"
                    ),
                    status="recovery_required",
                    job_id=job_id,
                    state_path=state_path,
                    request_fingerprint=fingerprint,
                    provider_status=(
                        str(state.get("status"))
                        if isinstance(state, dict) and state.get("status")
                        else "submission_unknown"
                    ),
                    duration_s=duration,
                ) from exc
            if self.fal_key and FAL_AVAILABLE:
                print("[LTX] Pre-submission failure; falling back to FAL proxy")
                return self._fal_generate(
                    image_path,
                    prompt,
                    output_path,
                    num_frames,
                    resolution,
                    camera_motion,
                    on_billed=on_billed,
                )
            return None




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
