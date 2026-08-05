"""Production PuLID live-contract smoke.

Exercises the repository's real ``pulid.json`` through ``generate_ai_broll``
against the pinned production ComfyUI endpoint. The generated face fixture is
synthetic; the assertion is transport/workflow/artifact validity, not quality.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from config.settings import settings


SELECTED = (
    os.environ.get("LIVE_CONTRACT_CANARY_TARGET", "")
    == "runpod-pulid-production"
)
HAS_COMFYUI = bool(settings.comfyui_server_url and settings.comfyui_api_key)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not SELECTED or not HAS_COMFYUI,
        reason="production PuLID RunPod target was not selected or configured",
    ),
]


def _make_face_reference(path: str) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (512, 512), (54, 58, 68))
    draw = ImageDraw.Draw(image)
    draw.ellipse((132, 82, 380, 430), fill=(205, 174, 150))
    draw.ellipse((200, 220, 230, 250), fill=(35, 30, 30))
    draw.ellipse((282, 220, 312, 250), fill=(35, 30, 30))
    draw.arc((205, 270, 308, 350), 15, 165, fill=(75, 45, 45), width=6)
    image.save(path, "JPEG", quality=90)


def test_production_pulid_round_trip(monkeypatch):
    """The pinned production graph queues and publishes a valid JPEG."""
    from PIL import Image

    from cinema.context import PipelineContext
    import phase_c_assembly

    def reject_fallback(*_args, **_kwargs):
        pytest.fail("production PuLID canary attempted a fallback provider")

    monkeypatch.setattr(phase_c_assembly, "_fal_flux_fallback", reject_fallback)

    with tempfile.TemporaryDirectory() as directory:
        character = os.path.join(directory, "character.jpg")
        output = os.path.join(directory, "pulid-canary.jpg")
        _make_face_reference(character)

        result = phase_c_assembly.generate_ai_broll(
            "close-up cinematic portrait of a person, neutral expression, studio light",
            output,
            seed=1729,
            character_image=character,
            ctx=PipelineContext(
                global_settings={
                    "identity_backend": "pod",
                    "aspect_ratio": "16:9",
                }
            ),
        )
        if result is None:
            pytest.fail("configured production PuLID RunPod returned no result")
        assert result.api_name == "COMFYUI_PULID"
        assert result.path == output
        assert os.path.getsize(output) > 1024
        with Image.open(output) as image:
            image.load()
            assert image.format == "JPEG"
            assert image.size == (2688, 1536)
