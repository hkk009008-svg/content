"""Nano Banana 2 (Gemini 3.1 Flash Image) Native API Client — Direct Gemini
Developer API integration via google-genai SDK.

Migrated off gemini-2.5-flash-image (shutdown deadline 2026-10-02; Slice 6b) —
successor confirmed at https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-image
(2026-07-31 WebFetch): image output supported, no documented reference-image-
count cap (GEMINI_MULTIREF_MAX_REFS=8 below is unaffected).

Generates an identity-conditioned still image from a text prompt plus up to
GEMINI_MULTIREF_MAX_REFS reference images (primary character + multi-angle
refs + secondary-character refs) in a single generate_content call. Sibling
to veo_native.py / gemini_omni_native.py; this is the WS3 image-side client
(Google-first overhaul).
"""
from __future__ import annotations

from io import BytesIO
import os

from google import genai
from google.genai import types
from PIL import Image
from config.settings import settings
from cinema.aspect import fal_aspect_ratio
from performance._net import atomic_publish_bytes, validate_image_artifact

# Combined reference-image budget (character_image + multi_angle_refs +
# secondary_char_refs) threaded into a single generate_content call. The
# "~20" figure floated during discovery is UNVERIFIED (flagged by discovery
# itself as not tested against the live API) — ship conservative and revisit
# only after a live-API empirical probe recorded as a logs/ artifact per
# R-MEASURE (CLAUDE.md).
# LIVE RISK, opened 2026-08-08: a character's reference set now really can
# exceed this. It previously could not — the record held 2 paths, so the budget
# never bound and the truncation warning below never printed.
#
# Vendor documentation for the pinned tier states FOUR character reference
# images (ai.google.dev/gemini-api/docs/image-generation, read 2026-08-08),
# while gemini-3-pro-image documents five. This constant is 8. If the provider
# REJECTS rather than truncates above its ceiling, generation now fails where it
# used to pass.
#
# NOT changed here. The comment above is explicit that this number moves only
# after a live-API probe recorded as a logs/ artifact (R-MEASURE), and a
# documentation page is not a probe. Route by model ID when the probe happens —
# cost_tracker.py:89 calls the flash tier "Nano Banana 2", so marketing aliases
# cannot be trusted to identify the tier. Tracked in
# docs/PLAN-reference-sets-2026-08-08.md.
GEMINI_MULTIREF_MAX_REFS = 8
_IMAGE_MIME_FORMATS = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
_IMAGE_FORMAT_MIMES = {image_format: mime for mime, image_format in _IMAGE_MIME_FORMATS.items()}
_IMAGE_SUFFIX_FORMATS = {
    ".jpg": ("JPEG", "image/jpeg"),
    ".jpeg": ("JPEG", "image/jpeg"),
    ".png": ("PNG", "image/png"),
    ".webp": ("WEBP", "image/webp"),
}


def _load_image_bytes(image_path: str) -> bytes:
    """Read `image_path` and return its raw bytes."""
    with open(image_path, "rb") as f:
        return f.read()


def _load_reference_image(image_path: str) -> tuple[bytes, str]:
    """Load a bounded reference image and derive MIME from decoded magic."""
    payload = _load_image_bytes(image_path)
    if not payload or len(payload) > 64 * 1024 * 1024:
        raise ValueError("reference image is empty or exceeds 64 MiB")
    with Image.open(BytesIO(payload)) as image:
        image_format = (image.format or "").upper()
        width, height = image.size
        image.verify()
    mime_type = _IMAGE_FORMAT_MIMES.get(image_format)
    if mime_type is None:
        raise ValueError(f"unsupported reference image format {image_format!r}")
    if width <= 0 or height <= 0 or width * height > 100_000_000:
        raise ValueError(f"invalid reference image dimensions {(width, height)!r}")
    return payload, mime_type


def _publish_generated_image(
    payload: bytes,
    mime_type: str,
    output_path: str,
) -> str | None:
    """Verify provider MIME/magic, normalize to the requested suffix, publish atomically."""
    normalized_mime = (mime_type or "").split(";", 1)[0].strip().lower()
    source_format = _IMAGE_MIME_FORMATS.get(normalized_mime)
    target = _IMAGE_SUFFIX_FORMATS.get(os.path.splitext(output_path)[1].lower())
    if source_format is None or target is None:
        print(
            "[GEMINI-IMAGE] Unsupported response MIME or output extension: "
            f"mime={normalized_mime or '<missing>'!r}, path={output_path!r}"
        )
        return None
    if not isinstance(payload, bytes) or not payload or len(payload) > 64 * 1024 * 1024:
        print("[GEMINI-IMAGE] Image response is empty, non-bytes, or oversized")
        return None

    target_format, target_mime = target
    try:
        with Image.open(BytesIO(payload)) as image:
            actual_format = (image.format or "").upper()
            if actual_format != source_format:
                print(
                    "[GEMINI-IMAGE] Response MIME/magic mismatch: "
                    f"mime={normalized_mime!r}, magic={actual_format!r}"
                )
                return None
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > 100_000_000:
                print(f"[GEMINI-IMAGE] Invalid image dimensions: {image.size!r}")
                return None
            image.load()
            if actual_format != target_format:
                converted = BytesIO()
                normalized_image = image.convert("RGB") if target_format == "JPEG" else image
                normalized_image.save(converted, format=target_format, quality=95)
                payload = converted.getvalue()
    except Exception as exc:
        print(f"[GEMINI-IMAGE] Image decode failed: {exc}")
        return None

    return atomic_publish_bytes(
        payload,
        output_path,
        max_bytes=64 * 1024 * 1024,
        content_type=target_mime,
        allowed_content_types=(target_mime,),
        content_validator=lambda path: validate_image_artifact(
            path,
            expected_formats=(target_format,),
        ),
    )


class GeminiImageAPI:
    """Native Gemini 3.1 Flash Image (Nano Banana 2) client using the
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
        self._model = "gemini-3.1-flash-image"

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
                try:
                    ref_payload, ref_mime_type = _load_reference_image(ref_path)
                except (OSError, ValueError) as exc:
                    print(f"[GEMINI-IMAGE] Skipping invalid reference {ref_path!r}: {exc}")
                    continue
                contents.append(
                    types.Part.from_bytes(data=ref_payload, mime_type=ref_mime_type)
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
            image_mime_type = ""
            parts = response.candidates[0].content.parts if response.candidates else []
            for part in parts:
                inline = getattr(part, "inline_data", None)
                data = getattr(inline, "data", None) if inline is not None else None
                if data is not None:
                    image_bytes = data
                    image_mime_type = getattr(inline, "mime_type", "") or ""
                    break

            if image_bytes is None:
                print("[GEMINI-IMAGE] No image data in response")
                return None

            if _publish_generated_image(
                image_bytes,
                image_mime_type,
                output_path,
            ) is None:
                return None

            file_size = os.path.getsize(output_path) / 1024
            print(f"[GEMINI-IMAGE] Image saved: {output_path} ({file_size:.1f} KB)")
            return output_path

        except Exception as e:
            print(f"[GEMINI-IMAGE] Generation failed: {e}")
            return None
