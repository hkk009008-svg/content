"""Gemini Omni Flash Native API Client — Direct Gemini Developer API integration via google-genai SDK."""
from __future__ import annotations

import base64
import os
import time
from typing import Callable

from google import genai
from google.genai import types
from config.settings import settings

# Gemini Omni Flash (Preview) interaction terminal states. Distinct SDK surface
# from Veo's Operation (`operation.done` / `operation.error`) — interactions
# report a `.status` string instead. "budget_exceeded" is this API's own
# quota-exhaustion vocabulary (mirrored into phase_c_ffmpeg.py's cooldown
# string-match alongside Veo's "429"/"quota"/"exhausted").
_TERMINAL_INTERACTION_STATUSES = frozenset({
    "completed", "failed", "cancelled", "incomplete", "budget_exceeded",
})


def _encode_image_b64(image_path: str) -> str:
    """Read `image_path` and return its base64-encoded contents (ascii str)."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


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
                even when that retrieval fails and this method still returns
                None (money-gate 2026-07-11 class, extended to the native
                adapters in slice M2). Exceptions raised by the callback are
                logged and swallowed — a broken accounting hook must never
                abort a generation that would otherwise succeed.

        Returns:
            output_path on success, None on failure (graceful — lets the
            cascade fall through to the next engine) — either pre-billing
            (non-completed terminal status) or post-billing (the interaction
            completed but video retrieval/write failed).
        """
        if not os.path.exists(image_path):
            print(f"[GEMINI-OMNI] Start frame not found: {image_path}")
            return None

        try:
            refs = reference_images or []
            print(f"[GEMINI-OMNI] Generating video — aspect_ratio={aspect_ratio}, "
                  f"refs={len(refs)}")
            print(f"[GEMINI-OMNI] Prompt: {prompt[:120]}...")

            input_items = [
                {"type": "image", "data": _encode_image_b64(image_path), "mime_type": "image/jpeg"},
            ]
            for ref_path in refs:
                input_items.append({
                    "type": "image",
                    "data": _encode_image_b64(ref_path),
                    "mime_type": "image/jpeg",
                })
            input_items.append({"type": "text", "text": prompt})

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
            print("[GEMINI-OMNI] Interaction submitted, polling for completion...")

            # Poll until a terminal status (max 20 minutes to avoid indefinite hangs).
            poll_count = 0
            max_polls = 120  # 120 * 10s = 1200s = 20 minutes
            while interaction.status not in _TERMINAL_INTERACTION_STATUSES:
                if poll_count >= max_polls:
                    raise TimeoutError(f"GEMINI-OMNI interaction timed out after {poll_count * 10}s")
                time.sleep(10)
                poll_count += 1
                interaction = self.client.interactions.get(interaction.id)
                if poll_count % 6 == 0:
                    print(f"[GEMINI-OMNI] Still generating... ({poll_count * 10}s elapsed)")

            if interaction.status != "completed":
                print(f"[GEMINI-OMNI] Generation ended with status={interaction.status!r}")
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

            video = interaction.output_video
            # `is not None` (not truthiness) — mirrors veo_native._extract_video_bytes:
            # an empty-but-present inline payload (b"") must still count as inline.
            if video.data is not None:
                video_data = video.data
            elif getattr(video, "uri", None):
                file_obj = self.client.files.get(name=video.uri)
                file_poll_count = 0
                while getattr(file_obj, "state", None) != "ACTIVE":
                    if file_poll_count >= max_polls:
                        raise TimeoutError(
                            f"GEMINI-OMNI file activation timed out after {file_poll_count * 10}s"
                        )
                    time.sleep(10)
                    file_poll_count += 1
                    file_obj = self.client.files.get(name=video.uri)
                video_data = self.client.files.download(file=file_obj)
            else:
                print("[GEMINI-OMNI] No video data or uri on completed interaction")
                return None

            with open(output_path, "wb") as f:
                f.write(video_data)

            file_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[GEMINI-OMNI] Video saved: {output_path} ({file_size:.1f} MB)")
            return output_path

        except Exception as e:
            print(f"[GEMINI-OMNI] Generation failed: {e}")
            return None
