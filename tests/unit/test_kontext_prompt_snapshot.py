"""Golden snapshot of the single-character Kontext prompt.

P1-1 slice 1 adds a multi-character branch to _fal_flux_fallback behind an
early-return. This snapshot pins the single-char prompt so the branch cannot
drift it by a byte. Captured from phase_c_assembly.py:493-529 at dcb4064.
"""
from __future__ import annotations

import dataclasses
import sys
import urllib.request
from unittest.mock import MagicMock

import pytest

import phase_c_assembly as pca


# MODULE-LEVEL constant — later tasks import this to assert multi-char branch
# leaves single-char path untouched.
GOLDEN_SINGLE_CHAR_PROMPT = (
    "PRESERVE IDENTITY: The person from @Image1 is a woman with auburn hair and green eyes. "
    "Keep this EXACT face, hair, glasses, eye color, skin tone unchanged. "
    "CHANGE BACKGROUND: A quiet rooftop at dusk. "
    "SET POSE: facing the camera. "
    "SET CAMERA: Medium shot, 85mm lens. "
    "CONSTRAINTS: Do NOT alter facial features, hairstyle, glasses, or skin. "
    "Do NOT generate a different person. "
    "The face in the output MUST match @Image1 exactly. "
    "QUALITY: Photorealistic, visible skin pores and subsurface scattering, "
    "shallow depth of field with circular bokeh, natural film grain ISO 400, "
    "volumetric atmospheric lighting, micro-detail in fabric texture, "
    "no AI artifacts, no smooth plastic skin, no over-saturated colors."
)


@pytest.fixture
def fal_capture(monkeypatch, tmp_path):
    """Stub the lazily-imported fal_client (sys.modules pattern — mirrors the
    sibling test_phase_c_assembly_provenance.py) and capture Kontext arguments.
    """
    fake = MagicMock()
    fake.upload_file.side_effect = lambda path: f"url://{path.split('/')[-1]}"
    fake.subscribe.return_value = {"images": [{"url": "https://fake/image.jpg"}]}
    monkeypatch.setitem(sys.modules, "fal_client", fake)

    monkeypatch.setattr(
        pca, "settings",
        dataclasses.replace(pca.settings, fal_key="test-key"),
    )

    def _fake_retrieve(url, filename):
        with open(filename, "wb") as fh:
            fh.write(b"jpeg-bytes")

    monkeypatch.setattr(urllib.request, "urlretrieve", _fake_retrieve)
    return fake


def test_single_char_kontext_prompt_snapshot(fal_capture, tmp_path):
    """Pin the exact Kontext prompt produced for a single-character call.

    multi-char branch (P1-1) must not shift this by a byte when character_image
    is given without multi_angle_refs.
    """
    ref = tmp_path / "aria.jpg"
    ref.write_bytes(b"jpg")
    out = tmp_path / "out.jpg"

    result = pca._fal_flux_fallback(
        "A quiet rooftop at dusk",
        str(out),
        character_image=str(ref),
        identity_anchor="a woman with auburn hair and green eyes",
    )

    assert result is not None and result.api_name == "FLUX_KONTEXT"

    # Verify the FAL endpoint
    call_args = fal_capture.subscribe.call_args
    assert call_args is not None, "fal_client.subscribe was never called"
    endpoint = call_args.args[0] if call_args.args else call_args.kwargs.get("endpoint")
    assert endpoint == "fal-ai/flux-pro/kontext/max/multi"

    # Verify the image_urls (single ref, basename matches the fixture file)
    arguments = call_args.kwargs.get("arguments") or (
        call_args.args[1] if len(call_args.args) > 1 else None
    )
    assert arguments is not None, "subscribe 'arguments' kwarg missing"
    assert arguments["image_urls"] == [f"url://aria.jpg"]

    # THE GOLDEN ASSERTION — this is what P1-1 multi-char branch must not touch
    assert arguments["prompt"] == GOLDEN_SINGLE_CHAR_PROMPT, (
        f"Single-char Kontext prompt drifted.\nExpected:\n{GOLDEN_SINGLE_CHAR_PROMPT}\n\nGot:\n{arguments['prompt']}"
    )
