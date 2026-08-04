"""
Veo Native API Client — Direct Google Veo 3.1 integration via google-genai SDK.
Bypasses fal.ai proxy for native access to Veo's first+last frame control,
reference image character preservation, and synced audio generation.
"""
from __future__ import annotations

import os
import time
from functools import lru_cache
from typing import Callable

from google import genai
from google.genai import types
from config.settings import settings
from performance._net import atomic_publish_bytes, validate_video_artifact


@lru_cache(maxsize=1)
def google_adc_available() -> bool:
    """Resolve ADC once, only at the provider-construction boundary.

    Catalog and routing reads stay non-dispatching and never probe metadata.
    """

    try:
        import google.auth

        credentials, _ = google.auth.default()
    except Exception:
        return False
    return credentials is not None


def veo_native_audio_available() -> bool:
    """Return whether the configured Veo path is ADC-backed Vertex AI."""

    return bool(settings.google_cloud_project and google_adc_available())

VEO_RESOLUTIONS = {
    "720p": "720p",
    "1080p": "1080p",
    "4k": "2160p",
    "2160p": "2160p",
}
# Server-valid output durations (seconds) for the image_to_video feature.
# 5s is REJECTED with INVALID_ARGUMENT for image_to_video despite older docs
# (captured server error: "supported durations are [8,4,6] for feature
# image_to_video"). text_to_video may differ, but this client only ever does
# image_to_video — it always supplies a start `image`.
VEO_IMAGE_TO_VIDEO_DURATIONS = (4, 6, 8)


def _safe_operation_name(value: object) -> str | None:
    """Return a bounded, log/persistence-safe Google operation name."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if (
        not value
        or len(value) > 1024
        or any(ord(char) < 32 for char in value)
        or "://" in value
        or any(char in value for char in "?#&")
    ):
        return None
    return value


def _safe_provider_status(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    if not value or len(value) > 64:
        return "unknown"
    if not all(char.isalnum() or char in "_-" for char in value):
        return "unknown"
    return value


class VeoNativeJobDeferred(RuntimeError):
    """Submission-ambiguous or accepted Veo work must not cascade.

    Only the server operation name and coarse state cross this boundary.  The
    exception never carries prompts, image content, output handles, or raw
    transport errors, making it suitable for a bounded durable recovery record.
    """

    engine = "VEO_NATIVE"

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        status: str,
        job_id: str | None = None,
        provider_status: str | None = None,
        billed: bool = False,
        duration_s: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.status = status
        self.job_id = _safe_operation_name(job_id)
        self.provider_status = _safe_provider_status(provider_status)
        self.billed = bool(billed)
        self.duration_s = (
            duration_s
            if isinstance(duration_s, int) and not isinstance(duration_s, bool)
            and 0 < duration_s <= 60
            else None
        )


def _parse_duration_seconds(duration, default: int = 8) -> int:
    """'8s' -> 8. Returns `default` on any malformed input — a formatting edge
    must not fail the whole generation."""
    try:
        return int(str(duration).strip().lower().rstrip("s"))
    except (ValueError, TypeError, AttributeError):
        return default


def _clamp_image_to_video_duration(seconds: int) -> int:
    """Snap `seconds` to the nearest server-valid image_to_video duration
    (``VEO_IMAGE_TO_VIDEO_DURATIONS``). Ties round UP so we never truncate the
    requested content (5 -> 6, 7 -> 8). The Veo server rejects any other value
    (e.g. 5s) with INVALID_ARGUMENT, so this MUST run before the config is built.
    """
    if seconds in VEO_IMAGE_TO_VIDEO_DURATIONS:
        return seconds
    # Nearest valid; on a tie prefer the larger (minimise (distance, -value)).
    return min(VEO_IMAGE_TO_VIDEO_DURATIONS, key=lambda v: (abs(v - seconds), -v))


def _build_generate_videos_config(
    *,
    generate_audio: bool,
    duration: str,
    resolution: str,
    reference_images=None,
    person_generation: str = "allow_adult",
    aspect_ratio: str = "16:9",
):
    """Pure: map generate_video() params -> GenerateVideosConfig. No I/O.

    `reference_images` is a list of already-loaded ``types.Image`` (or None); each
    is wrapped in a ``VideoGenerationReferenceImage`` (reference_type=ASSET — the
    config's required type for subject/character preservation). The previous code
    passed raw Images as a top-level ``generate_videos`` kwarg, which the SDK
    rejects (TypeError); and never set audio/duration/resolution at all.
    """
    kwargs = dict(
        person_generation=person_generation,
        aspect_ratio=aspect_ratio,
        generate_audio=generate_audio,
        duration_seconds=_clamp_image_to_video_duration(_parse_duration_seconds(duration)),
        resolution=resolution,
    )
    if reference_images:
        kwargs["reference_images"] = [
            types.VideoGenerationReferenceImage(
                image=img,
                reference_type=types.VideoGenerationReferenceType.ASSET,
            )
            for img in reference_images
        ]
    return types.GenerateVideosConfig(**kwargs)


def _extract_video_bytes(client, generated_video):
    """Return raw video bytes from a completed ``generated_video``.

    Vertex AI (the only audio-capable backend) returns the bytes INLINE on
    ``generated_video.video.video_bytes`` and ``client.files.download`` raises
    there ("This method is only supported in the Gemini Developer client"). The
    Gemini Developer backend instead returns a Files handle that must be
    downloaded. So prefer inline bytes; only fall back to download when absent.
    """
    video_obj = generated_video.video
    inline = getattr(video_obj, "video_bytes", None)
    # `is not None` (not truthiness) on purpose: an empty-but-present payload
    # (b"") must still count as inline. Falling through to files.download on
    # Vertex RAISES ("only supported in the Gemini Developer client"), which
    # would turn a degenerate-empty into a hard crash.
    if inline is not None:
        return inline
    return client.files.download(file=video_obj)


class VeoNativeAPI:
    """Native Google Veo 3.1 client using the google-genai SDK.

    Uses Vertex AI only when an explicit project is configured; otherwise uses
    the Gemini Developer API when an API key is configured.
    """

    def __init__(self):
        gcp_project = settings.google_cloud_project
        adc_ready = bool(gcp_project) and google_adc_available()
        if gcp_project and adc_ready:
            gcp_location = settings.google_cloud_location
            self.client = genai.Client(
                vertexai=True,
                project=gcp_project,
                location=gcp_location,
            )
            self._backend = "vertex"
            self.supports_native_audio = True
            print(f"[VEO-NATIVE] Vertex AI client initialized (project={gcp_project}, location={gcp_location})")
        elif settings.google_api_key:
            api_key = settings.google_api_key
            self.client = genai.Client(api_key=api_key)
            self._backend = "gemini"
            self.supports_native_audio = False
            print("[VEO-NATIVE] Gemini API client initialized (no audio generation)")
        elif gcp_project:
            raise EnvironmentError(
                "[VEO-NATIVE] GOOGLE_CLOUD_PROJECT requires resolvable "
                "Application Default Credentials, or configure GOOGLE_API_KEY "
                "for the Gemini Developer API."
            )
        else:
            raise EnvironmentError(
                "[VEO-NATIVE] Configure GOOGLE_CLOUD_PROJECT for Vertex AI "
                "or GOOGLE_API_KEY for the Gemini Developer API."
            )

        # Vertex AI uses stable model names; Gemini API uses -preview suffix
        self._model = "veo-3.1-generate-001" if self._backend == "vertex" else "veo-3.1-generate-preview"
        self.last_job_id: str | None = None
        self.last_duration_s: int | None = None

    def generate_video(
        self,
        image_path: str,
        prompt: str,
        output_path: str,
        reference_images: list = None,
        duration: str = "8s",
        resolution: str = "720p",
        generate_audio: bool = False,
        driving_video_path: str = "",
        aspect_ratio: str = "16:9",
        on_billed: Callable[[], None] | None = None,
    ) -> str | None:
        """
        Generate video from a start frame image + text prompt using Veo 3.1.

        Args:
            image_path: Path to the start frame image.
            prompt: Cinematic text prompt describing the desired motion/scene.
            output_path: Where to save the generated video.
            reference_images: Optional list of image paths. NOT applied on this
                              image-to-video path: config `reference_images` are
                              mutually exclusive with the start `image` we always
                              supply (Vertex: "Image and reference images cannot
                              be both set."), so identity comes from the start
                              frame (generated upstream from the character's refs).
                              Accepted for interface stability. (Bug #4; cf. the
                              driving_video_path note below + f6d6995.)
            duration: Requested video duration. Snapped to the nearest
                server-valid image_to_video value (4/6/8s) — e.g. "5s" -> 6s —
                since Veo rejects other values with INVALID_ARGUMENT.
            resolution: Output resolution — "720p" or "1080p".
            generate_audio: If True, Veo generates synced audio (use for dialogue scenes).
            driving_video_path: Optional path to a performance-capture clip.
                NOT currently applied. The SDK's video input (`video=` /
                `source.video`) is for video *extension* and is mutually
                exclusive with the start `image` we always supply ("Not allowed
                if image is provided"), so a driving clip cannot condition an
                image-to-video call here. Accepted for interface stability;
                wiring motion conditioning needs a separate GenerateVideosSource
                design (spec §4.2). Currently image-only.
            on_billed: Optional zero-arg callback invoked exactly once, the
                moment the operation's response reports a generated video —
                the repo's billed bar (a provider that RETURNED a video is
                billed regardless of what happens next; see
                phase_c_ffmpeg._note_billed_attempt). Fires BEFORE the bytes
                are retrieved/written so a caller can record the spend even
                when retrieval/write later raises VeoNativeJobDeferred
                (money-gate 2026-07-11 class, extended to the native adapters
                in slice M2). Exceptions raised by the callback are logged and
                swallowed — a broken accounting hook must never abort a
                generation that would otherwise succeed.

        Returns:
            output_path on success, or None when failure is known to be
            terminal/pre-submission and a provider cascade is safe.

        Raises:
            VeoNativeJobDeferred: Submission acknowledgement was lost, an
                accepted operation is still pending, or completed output could
                not be recovered/published.  Callers must not cascade.
        """
        if not os.path.exists(image_path):
            print(f"[VEO-NATIVE] Start frame not found: {image_path}")
            return None

        self.last_job_id = None
        submission_started = False
        operation_accepted = False
        operation_name: str | None = None
        provider_status: str | None = None
        billed = False
        dispatched_duration_s: int | None = None
        try:
            print(f"[VEO-NATIVE] Generating video — {duration}, {resolution}, audio={generate_audio}")
            print(f"[VEO-NATIVE] Prompt: {prompt[:120]}...")

            # Upload start frame — from_file requires keyword arg 'location'
            start_image = types.Image.from_file(location=image_path)

            # Veo image-to-video derives BOTH composition and character identity
            # from the start frame (the keyframe is generated upstream from the
            # character's references). The config-level `reference_images` are
            # MUTUALLY EXCLUSIVE with the start `image` we always supply — Vertex
            # rejects "Image and reference images cannot be both set." (code 3).
            # A start frame is present here by construction (guarded above), so
            # reference_images cannot ride along: accept the param for interface
            # stability but proceed image-only. Mirrors the driving-video handling
            # below and the image/video exclusion fixed in f6d6995. (Bug #4.)
            if reference_images:
                print(f"[VEO-NATIVE] {len(reference_images)} reference image(s) provided but "
                      f"not applied on the image-to-video path (image/reference_images are "
                      f"mutually exclusive); identity comes from the start frame.")

            # Thread caller-intent params into the config (audio/duration/
            # resolution). reference_images is intentionally NOT threaded (see above).
            config = _build_generate_videos_config(
                generate_audio=generate_audio,
                duration=duration,
                resolution=resolution,
                reference_images=None,
                aspect_ratio=aspect_ratio,
            )
            dispatched_duration_s = config.duration_seconds
            self.last_duration_s = dispatched_duration_s

            generate_kwargs = {
                "model": self._model,
                "prompt": prompt,
                "image": start_image,
                "config": config,
            }

            # NOTE: driving-video motion conditioning is NOT wired on this path.
            # The SDK's only video input (`video=` / `source.video`) is for video
            # *extension* and is mutually exclusive with `image=` (SDK: "Not
            # allowed if image is provided"). Since we always supply a start
            # image, a driving clip cannot ride along an image-to-video call here.
            # Applying motion conditioning needs a separate GenerateVideosSource
            # design (spec §4.2). Until then the param is accepted for interface
            # stability but the call is image-only — we must NOT add `video=`
            # alongside `image=`, or the whole generation fails server-side.
            if driving_video_path and os.path.exists(driving_video_path):
                print(f"[VEO-NATIVE] Driving video provided but not wired on the "
                      f"image-to-video path (SDK image/video are mutually exclusive); "
                      f"proceeding image-only: {os.path.basename(driving_video_path)}")

            # Once this call starts, a raised transport/protocol error cannot
            # prove that the service did not accept a paid operation.  The
            # caller must stop the provider cascade on that ambiguity.
            submission_started = True
            operation = self.client.models.generate_videos(**generate_kwargs)
            operation_accepted = True
            operation_name = _safe_operation_name(getattr(operation, "name", None))
            self.last_job_id = operation_name
            print(f"[VEO-NATIVE] Operation submitted, polling for completion...")

            # Poll until done (max 20 minutes to avoid indefinite hangs)
            poll_count = 0
            max_polls = 120  # 120 * 10s = 1200s = 20 minutes
            provider_status = "completed" if getattr(operation, "done", False) else "pending"
            while not getattr(operation, "done", False):
                if poll_count >= max_polls:
                    raise VeoNativeJobDeferred(
                        "Veo operation is still non-terminal; recovery is required",
                        reason="accepted_job_poll_timeout",
                        status="pending",
                        job_id=operation_name,
                        provider_status=provider_status,
                        duration_s=dispatched_duration_s,
                    )
                time.sleep(10)
                poll_count += 1
                operation = self.client.operations.get(operation)
                refreshed_name = _safe_operation_name(getattr(operation, "name", None))
                if refreshed_name is not None:
                    operation_name = refreshed_name
                    self.last_job_id = refreshed_name
                provider_status = (
                    "completed" if getattr(operation, "done", False) else "pending"
                )
                if poll_count % 6 == 0:
                    print(f"[VEO-NATIVE] Still generating... ({poll_count * 10}s elapsed)")

            # Surface a deterministic operation error (e.g. INVALID_ARGUMENT for
            # an unsupported duration) instead of letting it fall through to the
            # generic "empty response" branch — the error carries the real reason.
            op_error = getattr(operation, "error", None)
            if op_error:
                provider_status = "failed"
                print(f"[VEO-NATIVE] Generation error: {op_error}")
                return None

            # Check for RAI content filter rejection / empty response.
            resp = operation.response
            if not resp or not resp.generated_videos:
                provider_status = "failed"
                rai_reasons = getattr(resp, "rai_media_filtered_reasons", []) if resp else []
                rai_count = getattr(resp, "rai_media_filtered_count", 0) if resp else 0
                if rai_reasons:
                    print(f"[VEO-NATIVE] RAI filter ({rai_count} filtered): {rai_reasons[0][:120]}")
                else:
                    print(f"[VEO-NATIVE] No video generated (empty response)")
                return None

            # Provider returned a generated video — billed regardless of what
            # happens next. Notify the caller BEFORE bytes retrieval/write so
            # a subsequent failure below still reaches the caller's spend
            # accounting before this call raises its deferred-job signal.
            generated_video = resp.generated_videos[0]
            if on_billed is not None:
                try:
                    on_billed()
                except Exception as callback_exc:
                    print(
                        f"[VEO-NATIVE] Warning: on_billed callback raised: {callback_exc}"
                    )
            billed = True

            # Retrieve bytes — Vertex returns them inline; only the Gemini
            # backend needs a Files API download (which raises on Vertex).
            video_data = _extract_video_bytes(self.client, generated_video)
            if atomic_publish_bytes(
                video_data,
                output_path,
                max_bytes=1024 * 1024 * 1024,
                content_validator=validate_video_artifact,
            ) is None:
                raise VeoNativeJobDeferred(
                    "Veo completed output failed publication or validation",
                    reason="completed_output_invalid",
                    status="recovery_required",
                    job_id=operation_name,
                    provider_status="completed",
                    billed=True,
                    duration_s=dispatched_duration_s,
                )

            file_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[VEO-NATIVE] Video saved: {output_path} ({file_size:.1f} MB)")
            return output_path

        except VeoNativeJobDeferred:
            raise
        except Exception as e:
            if submission_started:
                if billed:
                    reason = "completed_output_unavailable"
                    status = "recovery_required"
                elif operation_accepted:
                    reason = "accepted_job_poll_error"
                    status = "pending" if operation_name else "recovery_required"
                else:
                    reason = "submit_outcome_unknown"
                    status = "recovery_required"
                print(
                    "[VEO-NATIVE] Remote work may have been accepted; "
                    "caller must defer instead of cascading"
                )
                raise VeoNativeJobDeferred(
                    "Veo work may have been accepted; recovery is required",
                    reason=reason,
                    status=status,
                    job_id=operation_name,
                    provider_status=(
                        provider_status
                        or ("submitted" if operation_accepted else "submission_unknown")
                    ),
                    billed=billed,
                    duration_s=dispatched_duration_s,
                ) from e
            print(f"[VEO-NATIVE] Generation failed: {e}")
            return None
