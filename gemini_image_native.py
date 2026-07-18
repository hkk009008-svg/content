"""Nano Banana (Gemini 2.5 Flash Image) Native API Client — Direct Gemini
Developer API integration via google-genai SDK.

Generates an identity-conditioned still image from a text prompt plus up to
GEMINI_MULTIREF_MAX_REFS reference images (primary character + multi-angle
refs + secondary-character refs) in a single generate_content call. Sibling
to veo_native.py / gemini_omni_native.py; this is the WS3 image-side client
(Google-first overhaul).
"""
from __future__ import annotations

import os

from google import genai
from google.genai import types
from config.settings import settings
from cinema.aspect import fal_aspect_ratio

# Combined reference-image budget (character_image + multi_angle_refs +
# secondary_char_refs) threaded into a single generate_content call. The
# "~20" figure floated during discovery is UNVERIFIED (flagged by discovery
# itself as not tested against the live API) — ship conservative and revisit
# only after a live-API empirical probe recorded as a logs/ artifact per
# R-MEASURE (CLAUDE.md).
GEMINI_MULTIREF_MAX_REFS = 8


def _load_image_bytes(image_path: str) -> bytes:
    """Read `image_path` and return its raw bytes."""
    with open(image_path, "rb") as f:
        return f.read()


class GeminiImageAPI:
    """Native Gemini 2.5 Flash Image (Nano Banana) client using the
    google-genai SDK.

    Gemini Developer API only — Nano Banana has no Vertex AI surface today
    (unlike Veo 3.1; cf. veo_native.py's Vertex-first / Gemini-fallback
    cascade), so this client never attempts a Vertex client. Mirrors
    gemini_omni_native.GeminiOmniAPI's single-path __init__ contract.
    """

    def __init__(self):
        api_key = settings.google_api_key or settings.gemini_api_key
        if not api_key:
            raise EnvironmentError(
                "[GEMINI-IMAGE] Neither GOOGLE_API_KEY nor GEMINI_API_KEY available."
            )
        self.client = genai.Client(api_key=api_key)
        self._model = "gemini-2.5-flash-image"

    def generate_image(
        self,
        prompt: str,
        output_path: str,
        character_image: str = None,
        multi_angle_refs: list = None,
        secondary_char_refs: list = None,
        aspect_ratio: str = "16:9",
        negative_prompt: str = "",
    ) -> str | None:
        """
        Generate a cinematic still image conditioned on `prompt` plus up to
        GEMINI_MULTIREF_MAX_REFS reference images.

        Args:
            prompt: Image generation prompt (already continuity/style enhanced
                by the caller).
            output_path: Where to save the generated image.
            character_image: Primary character reference image path.
            multi_angle_refs: Optional list of additional angle reference
                image paths for the primary character.
            secondary_char_refs: Optional list of secondary-character
                reference image paths (multi-character shots).
            aspect_ratio: Output aspect ratio (e.g. "16:9", "9:16") — mapped
                through cinema.aspect.fal_aspect_ratio's is_portrait logic so
                every backend shares one orientation source of truth.
            negative_prompt: Optional negative constraints appended to the
                prompt (Nano Banana has no structured negative-prompt kwarg).

        Returns:
            output_path on success, None on failure (graceful — lets the
            image-gen cascade fall through to the next backend). No exception
            escapes this method.
        """
        try:
            ref_paths = []
            if character_image:
                ref_paths.append(character_image)
            ref_paths.extend(multi_angle_refs or [])
            ref_paths.extend(secondary_char_refs or [])
            # Drop refs missing on disk rather than letting a stale/missing
            # path raise mid-encode — a stale ref must not sink the call.
            ref_paths = [p for p in ref_paths if p and os.path.exists(p)]

            if len(ref_paths) > GEMINI_MULTIREF_MAX_REFS:
                print(
                    f"[GEMINI-IMAGE] WARNING: {len(ref_paths)} reference images exceed "
                    f"the {GEMINI_MULTIREF_MAX_REFS}-image budget; truncating."
                )
                ref_paths = ref_paths[:GEMINI_MULTIREF_MAX_REFS]

            full_prompt = prompt
            if negative_prompt:
                full_prompt = f"{prompt}\n\nAvoid: {negative_prompt}"

            print(
                f"[GEMINI-IMAGE] Generating image — {len(ref_paths)} ref(s), "
                f"aspect_ratio={aspect_ratio}"
            )
            print(f"[GEMINI-IMAGE] Prompt: {prompt[:120]}...")

            # Flat contents list: prompt text + one Part per reference image.
            # Mirrors phase_c_vision.py:437-449's proven
            # genai.types.Part.from_bytes(data=..., mime_type="image/jpeg")
            # encoding path — reusing it rather than inventing a new one.
            contents = [full_prompt]
            for ref_path in ref_paths:
                contents.append(
                    types.Part.from_bytes(
                        data=_load_image_bytes(ref_path),
                        mime_type="image/jpeg",
                    )
                )

            response = self.client.models.generate_content(
                model=self._model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio=fal_aspect_ratio(aspect_ratio),
                        image_size="1K",
                    ),
                ),
            )

            image_bytes = None
            parts = response.candidates[0].content.parts if response.candidates else []
            for part in parts:
                inline = getattr(part, "inline_data", None)
                data = getattr(inline, "data", None) if inline is not None else None
                if data is not None:
                    image_bytes = data
                    break

            if image_bytes is None:
                print("[GEMINI-IMAGE] No image data in response")
                return None

            with open(output_path, "wb") as f:
                f.write(image_bytes)

            file_size = os.path.getsize(output_path) / 1024
            print(f"[GEMINI-IMAGE] Image saved: {output_path} ({file_size:.1f} KB)")
            return output_path

        except Exception as e:
            print(f"[GEMINI-IMAGE] Generation failed: {e}")
            return None
