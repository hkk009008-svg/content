"""Gemini Omni Flash Native API Client — Direct Gemini Developer API integration via google-genai SDK."""
from __future__ import annotations

import base64
import os
import time
from typing import Callable

from google import genai
from google.genai import types
from config.settings import settings
from gemini_image_native import _load_reference_image as _load_bounded_image
from performance._net import atomic_publish_bytes, validate_video_artifact

# Gemini Omni Flash (Preview) interaction terminal states. Distinct SDK surface
# from Veo's Operation (`operation.done` / `operation.error`) — interactions
# report a `.status` string instead. "budget_exceeded" is this API's own
# quota-exhaustion vocabulary (mirrored into phase_c_ffmpeg.py's cooldown
# string-match alongside Veo's "429"/"quota"/"exhausted").
_TERMINAL_INTERACTION_STATUSES = frozenset({
    "completed", "failed", "cancelled", "incomplete", "budget_exceeded",
})


def _safe_interaction_id(value: object) -> str | None:
    """Return a bounded, log/persistence-safe Google interaction ID."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if (
        not value
        or len(value) > 512
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


class GeminiOmniJobDeferred(RuntimeError):
    """Submission-ambiguous or accepted Omni work must not cascade.

    The exception carries only a bounded interaction identifier and coarse
    state.  It intentionally excludes prompts, image data, output URIs, and
    underlying transport details so a caller can persist/surface it safely.
    """

    engine = "GEMINI_OMNI"

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        status: str,
        job_id: str | None = None,
        provider_status: str | None = None,
        billed: bool = False,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.status = status
        self.job_id = _safe_interaction_id(job_id)
        self.provider_status = _safe_provider_status(provider_status)
        self.billed = bool(billed)


def _encode_image_input(image_path: str) -> tuple[str, str]:
    """Return bounded, decoded-magic-verified base64 data and its MIME type."""
    try:
        payload, mime_type = _load_bounded_image(image_path)
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"unsupported or malformed Gemini Omni input image: {image_path!r}"
        ) from exc
    return base64.b64encode(payload).decode("ascii"), mime_type


def _encode_image_b64(image_path: str) -> str:
    """Compatibility helper returning verified input bytes as base64 text."""
    encoded, _mime_type = _encode_image_input(image_path)
    return encoded


class GeminiOmniAPI:
    """Native Gemini Omni Flash (Preview) client using the google-genai SDK.

    Gemini Developer API only — Omni Flash has no Vertex AI surface today
    (unlike Veo 3.1; cf. veo_native.py's Vertex-first / Gemini-fallback
    cascade), so this client never attempts a Vertex client.
    """

    def __init__(self):
        api_key = settings.google_api_key or settings.gemini_api_key
        if not api_key:
            raise EnvironmentError(
                "[GEMINI-OMNI] Neither GOOGLE_API_KEY nor GEMINI_API_KEY available."
            )
        self.client = genai.Client(api_key=api_key)
        self._model = "gemini-omni-flash-preview"
        self.last_job_id: str | None = None

    def generate_video(
        self,
        image_path: str,
        prompt: str,
        output_path: str,
        reference_images: list = None,
        aspect_ratio: str = "16:9",
        on_billed: Callable[[], None] | None = None,
    ) -> str | None:
        """
        Generate video from a start frame image + text prompt using Gemini
        Omni Flash (Preview).

        Args:
            image_path: Path to the start frame image.
            prompt: Cinematic text prompt describing the desired motion/scene.
                Duration, resolution, and audio intent are prompt-inferred on
                this API (no structured kwargs) — the caller must encode that
                intent into the prompt text itself.
            output_path: Where to save the generated video.
            reference_images: Optional list of additional image paths for
                subject/character preservation. When present, the interaction
                task is "reference_to_video"; otherwise "image_to_video".
            aspect_ratio: Output aspect ratio (e.g. "16:9", "9:16").
            on_billed: Optional zero-arg callback invoked exactly once, the
                moment the interaction reaches the "completed" terminal
                status — the repo's billed bar (a provider that finished the
                interaction is billed regardless of what happens next; see
                phase_c_ffmpeg._note_billed_attempt). Fires BEFORE the video
                bytes/file are retrieved so a caller can record the spend
                even when retrieval later raises GeminiOmniJobDeferred
                (money-gate 2026-07-11 class, extended to the native adapters
                in slice M2). Exceptions raised by the callback are logged and
                swallowed — a broken accounting hook must never abort a
                generation that would otherwise succeed.

        Returns:
            output_path on success, or None when failure is known to be
            terminal/pre-submission and a provider cascade is safe.

        Raises:
            GeminiOmniJobDeferred: Submission acknowledgement was lost, an
                accepted interaction is still pending, or completed output
                could not be recovered/published.  Callers must not cascade.
        """
        if not os.path.exists(image_path):
            print(f"[GEMINI-OMNI] Start frame not found: {image_path}")
            return None

        self.last_job_id = None
        submission_started = False
        interaction_accepted = False
        interaction_id: str | None = None
        provider_status: str | None = None
        billed = False
        try:
            refs = reference_images or []
            print(f"[GEMINI-OMNI] Generating video — aspect_ratio={aspect_ratio}, "
                  f"refs={len(refs)}")
            print(f"[GEMINI-OMNI] Prompt: {prompt[:120]}...")

            start_data, start_mime = _encode_image_input(image_path)
            input_items = [
                {"type": "image", "data": start_data, "mime_type": start_mime},
            ]
            for ref_path in refs:
                ref_data, ref_mime = _encode_image_input(ref_path)
                input_items.append({
                    "type": "image",
                    "data": ref_data,
                    "mime_type": ref_mime,
                })
            input_items.append({"type": "text", "text": prompt})

            # Once this call starts, a raised transport/protocol error cannot
            # prove that the service did not accept a paid interaction.  The
            # caller must stop the provider cascade on that ambiguity.
            submission_started = True
            interaction = self.client.interactions.create(
                model=self._model,
                input=input_items,
                generation_config={
                    "video_config": {
                        "task": "reference_to_video" if reference_images else "image_to_video",
                    },
                },
                response_format={
                    "type": "video",
                    "aspect_ratio": aspect_ratio,
                    "delivery": "uri",
                },
            )
            interaction_accepted = True
            interaction_id = _safe_interaction_id(getattr(interaction, "id", None))
            self.last_job_id = interaction_id
            print("[GEMINI-OMNI] Interaction submitted, polling for completion...")

            # Poll until a terminal status (max 20 minutes to avoid indefinite hangs).
            poll_count = 0
            max_polls = 120  # 120 * 10s = 1200s = 20 minutes
            provider_status = str(getattr(interaction, "status", "unknown"))
            while provider_status not in _TERMINAL_INTERACTION_STATUSES:
                if poll_count >= max_polls:
                    raise GeminiOmniJobDeferred(
                        "Gemini Omni interaction is still non-terminal; recovery is required",
                        reason="accepted_job_poll_timeout",
                        status="pending",
                        job_id=interaction_id,
                        provider_status=provider_status,
                    )
                if interaction_id is None:
                    raise GeminiOmniJobDeferred(
                        "Gemini Omni accepted an interaction without a recoverable ID",
                        reason="accepted_job_id_missing",
                        status="recovery_required",
                        provider_status=provider_status,
                    )
                time.sleep(10)
                poll_count += 1
                interaction = self.client.interactions.get(interaction_id)
                provider_status = str(getattr(interaction, "status", "unknown"))
                if poll_count % 6 == 0:
                    print(f"[GEMINI-OMNI] Still generating... ({poll_count * 10}s elapsed)")

            if provider_status != "completed":
                # The interaction is explicitly terminal.  No accepted job is
                # left running, so a later provider may be selected safely.
                print(f"[GEMINI-OMNI] Generation ended with status={provider_status!r}")
                return None

            # Interaction completed — billed regardless of what happens next.
            # Notify the caller BEFORE video retrieval/write so a subsequent
            # failure below still reaches the caller's spend accounting, even
            # though this call goes on to return None.
            if on_billed is not None:
                try:
                    on_billed()
                except Exception as callback_exc:
                    print(
                        f"[GEMINI-OMNI] Warning: on_billed callback raised: {callback_exc}"
                    )
            billed = True

            # A "completed" interaction can still carry no video content step
            # at all (empty output) — classify this explicitly rather than
            # crashing through an unhandled AttributeError on video.data.
            video = interaction.output_video
            if video is None:
                raise GeminiOmniJobDeferred(
                    "Gemini Omni completed interaction has empty output",
                    reason="completed_output_missing",
                    status="recovery_required",
                    job_id=interaction_id,
                    provider_status="completed",
                    billed=True,
                )

            # `is not None` (not truthiness) — mirrors veo_native._extract_video_bytes:
            # an empty-but-present inline payload (b"") must still count as inline.
            if video.data is not None:
                # Inline delivery: per the google.genai VideoContent contract,
                # `data` is base64 TEXT (Optional[str]), never raw bytes —
                # decode before writing to a binary file handle.
                video_data = base64.b64decode(video.data)
            elif getattr(video, "uri", None):
                file_obj = self.client.files.get(name=video.uri)
                file_poll_count = 0
                while True:
                    state = getattr(file_obj, "state", None)
                    if state == "ACTIVE":
                        break
                    if state == "FAILED":
                        print(
                            f"[GEMINI-OMNI] File processing failed for uri={video.uri!r}"
                        )
                        return None
                    if file_poll_count >= max_polls:
                        raise GeminiOmniJobDeferred(
                            "Gemini Omni output file is still processing",
                            reason="completed_output_pending",
                            status="pending",
                            job_id=interaction_id,
                            provider_status="completed",
                            billed=True,
                        )
                    time.sleep(10)
                    file_poll_count += 1
                    file_obj = self.client.files.get(name=video.uri)

                # Download the RETURNED output URI from the polled file
                # resource (not the original video.uri) — mirrors the SDK's
                # own documented client.files.download(file=file.download_uri)
                # usage and lets an ACTIVE-but-not-downloadable file be
                # classified explicitly instead of raising from inside
                # files.download().
                download_uri = getattr(file_obj, "download_uri", None)
                if not download_uri:
                    raise GeminiOmniJobDeferred(
                        "Gemini Omni completed output has no downloadable URI",
                        reason="completed_output_unavailable",
                        status="recovery_required",
                        job_id=interaction_id,
                        provider_status="completed",
                        billed=True,
                    )
                video_data = self.client.files.download(file=download_uri)
            else:
                raise GeminiOmniJobDeferred(
                    "Gemini Omni completed output has no inline data or file URI",
                    reason="completed_output_missing",
                    status="recovery_required",
                    job_id=interaction_id,
                    provider_status="completed",
                    billed=True,
                )

            if atomic_publish_bytes(
                video_data,
                output_path,
                max_bytes=1024 * 1024 * 1024,
                content_validator=validate_video_artifact,
            ) is None:
                raise GeminiOmniJobDeferred(
                    "Gemini Omni completed output failed publication or validation",
                    reason="completed_output_invalid",
                    status="recovery_required",
                    job_id=interaction_id,
                    provider_status="completed",
                    billed=True,
                )

            file_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[GEMINI-OMNI] Video saved: {output_path} ({file_size:.1f} MB)")
            return output_path

        except GeminiOmniJobDeferred:
            raise
        except Exception as e:
            if submission_started:
                if billed:
                    reason = "completed_output_unavailable"
                    status = "recovery_required"
                elif interaction_accepted:
                    reason = "accepted_job_poll_error"
                    status = "pending" if interaction_id else "recovery_required"
                else:
                    reason = "submit_outcome_unknown"
                    status = "recovery_required"
                print(
                    "[GEMINI-OMNI] Remote work may have been accepted; "
                    "caller must defer instead of cascading"
                )
                raise GeminiOmniJobDeferred(
                    "Gemini Omni work may have been accepted; recovery is required",
                    reason=reason,
                    status=status,
                    job_id=interaction_id,
                    provider_status=(
                        provider_status
                        or ("submitted" if interaction_accepted else "submission_unknown")
                    ),
                    billed=billed,
                ) from e
            print(f"[GEMINI-OMNI] Generation failed: {e}")
            return None
