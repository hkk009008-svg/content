"""
llm/image_encoding.py — shared image-encoding helper for all LLM vision paths.

Extracted from llm/chief_director.py (_encode_image_for_llm, a4cb076) and promoted
to a shared module so phase_c_vision and chief_director both use the proven JPEG
re-encode policy: PIL open → convert("RGB") → aspect-preserving downscale when long
edge >1568 (LANCZOS) → JPEG quality=90 → b64 ascii → None on any failure.

Two failure modes closed by this encoder:
  (1) Production keyframes can be up to 4K; the raw-b64 path produced ≤20.28 MB strings
      exceeding the Anthropic 10 MB/image API limit → 400 errors.
  (2) Artifact extensions lie repo-wide (.jpg files contain PNG bytes); the old
      extension-derived media_type was frequently wrong.

Media type is ``image/jpeg`` BY CONSTRUCTION after passing through this encoder —
callers hardcode ``image/jpeg`` in all provider payloads.
"""

import base64
from typing import Optional


def encode_image_for_llm(path: str) -> Optional[str]:
    """Downscale + re-encode image to JPEG b64 for LLM vision calls.

    Policy:
    - Opens via PIL (handles any format regardless of file extension).
    - Converts to RGB (strips alpha; normalises palette modes).
    - Aspect-preserving downscale only when long edge > 1568 px (Anthropic
      native resolution for claude-sonnet-4; keeps detail within API limits).
    - Encodes as JPEG quality=90 → base64 ASCII string.
    - Returns None on any failure (caller follows its own on-failure contract).

    Provenance: extracted from ``llm.chief_director._encode_image_for_llm``
    (commit a4cb076) to share with ``phase_c_vision`` and any future LLM
    vision caller.
    """
    try:
        import io
        from PIL import Image
        img = Image.open(path).convert("RGB")          # PNG/RGBA/P all -> RGB
        w, h = img.size
        if max(w, h) > 1568:                            # Anthropic native res for sonnet-4 gen
            s = 1568 / max(w, h)
            img = img.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        print(f"   [IMAGE-ENCODING] image encode failed for {path}: {e}")
        return None
