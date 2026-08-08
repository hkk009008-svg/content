"""The previous shot's approved keyframe, reaching a hosted provider at last.

`continuity_reference` is documented as "Approved previous keyframe, when
present" and is threaded from the controller into `generate_ai_broll`. Inside
`phase_c_assembly` the name appeared exactly three times — the parameter, that
docstring, and one `allocate_flux2_references` call whose result feeds only the
local FLUX.2 worker. Neither hosted route could even ACCEPT it:

    _fal_flux_fallback:            prompt, output_filename, seed, character_image,
                                   multi_angle_refs, identity_anchor, aspect_ratio,
                                   secondary_char_refs, cost_tracker, ...
    GeminiImageAPI.generate_image: prompt, output_path, character_image,
                                   multi_angle_refs, secondary_char_refs, ...

The default backend is `gemini_multiref`. So on the default configuration,
shot-to-shot continuity WITHIN a scene rode on the prompt and the seed alone —
every shot re-invented the room's lighting and set dressing from prose.

The anchor is shot N-1 of the SAME scene (`_resolve_previous_approved_keyframe`),
so it carries that scene's rendered lighting, palette, set and wardrobe, and it
is the one image in the set that must NOT be reproduced: adjacent shots differ
in framing by definition.
"""

from __future__ import annotations

import dataclasses
import os
import sys
from unittest.mock import MagicMock

import pytest

import phase_c_assembly as pca
from phase_c_assembly import (
    CONTINUITY_SLOT_BUDGET,
    _MULTICHAR_REF_CAP,
    _continuity_prompt_block,
    _fal_flux_fallback,
)


@pytest.fixture
def fal_capture(monkeypatch):
    """Capture the Kontext subscribe arguments. Mirrors test_kontext_multichar."""

    captured: dict = {}
    fake = MagicMock()
    fake.upload_file.side_effect = lambda path: f"url://{os.path.basename(str(path))}"

    def _subscribe(endpoint, **kwargs):
        captured["endpoint"] = endpoint
        captured["arguments"] = kwargs.get("arguments", {})
        return {"images": [{"url": "https://fake/image.jpg"}]}

    fake.subscribe.side_effect = _subscribe
    monkeypatch.setitem(sys.modules, "fal_client", fake)
    monkeypatch.setattr(
        pca, "settings", dataclasses.replace(pca.settings, fal_key="test-key")
    )

    def _fake_download(url, filename):
        with open(filename, "wb") as fh:
            fh.write(b"jpeg-bytes")
        return filename

    monkeypatch.setattr(pca, "_download_generated_jpeg", _fake_download)
    return captured


def _refs(tmp_path, count, prefix="face"):
    paths = []
    for index in range(count):
        path = tmp_path / f"{prefix}_{index}.jpg"
        path.write_bytes(b"\xff\xd8\xff\xe0jpeg")
        paths.append(str(path))
    return paths


def _anchor(tmp_path):
    path = tmp_path / "prev_shot.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0jpeg")
    return str(path)


# ---------------------------------------------------------------------------
# The prompt block — the thing that separates "carry it forward" from "repeat it"
# ---------------------------------------------------------------------------

def test_the_block_names_the_slot_and_forbids_copying_the_framing() -> None:
    """Kontext is an EDITING model. An unlabelled extra image is something it
    may try to reproduce, and the previous shot is the one image that must not
    be reproduced. Both halves have to be said."""

    block = _continuity_prompt_block(6)
    assert "@Image6" in block
    assert "PREVIOUS SHOT" in block
    # Match the look...
    assert "lighting" in block and "palette" in block
    # ...not the layout.
    assert "Do NOT copy its framing" in block


# ---------------------------------------------------------------------------
# Single-character Kontext — the one place a face slot is given up
# ---------------------------------------------------------------------------

def test_the_anchor_reaches_kontext_as_the_last_reference(tmp_path, fal_capture) -> None:
    faces = _refs(tmp_path, 2)
    anchor = _anchor(tmp_path)

    _fal_flux_fallback(
        "a prompt", str(tmp_path / "out.jpg"),
        character_image=faces[0], multi_angle_refs=faces,
        continuity_reference=anchor,
    )
    urls = fal_capture["arguments"]["image_urls"]
    assert urls[-1] == "url://prev_shot.jpg"
    # And every face kept its slot: 2 faces + 1 anchor, nothing displaced.
    assert len(urls) == len(faces) + 1


def test_the_prompt_names_the_slot_the_anchor_actually_landed_in(
    tmp_path, fal_capture
) -> None:
    """A block naming @Image7 while the anchor sits at slot 3 is worse than no
    block: it points the model at a face and calls it the previous shot."""

    faces = _refs(tmp_path, 2)
    _fal_flux_fallback(
        "a prompt", str(tmp_path / "out.jpg"),
        character_image=faces[0], multi_angle_refs=faces,
        continuity_reference=_anchor(tmp_path),
    )
    urls = fal_capture["arguments"]["image_urls"]
    prompt = fal_capture["arguments"]["prompt"]
    # The slot named by the prompt must HOLD the anchor. Asserting only that
    # the number matches `len(urls)` passes even when the anchor was never
    # uploaded — confirmed by reverting the append and watching this test
    # survive, which is why the assertion is on the contents.
    assert prompt.count("is the PREVIOUS SHOT") == 1
    slot = int(prompt.split("CONTINUITY: @Image", 1)[1].split(" ", 1)[0])
    assert urls[slot - 1] == "url://prev_shot.jpg"
    # The identity block still leads and still addresses slot 1, which is a face.
    assert prompt.index("PRESERVE IDENTITY") < prompt.index("CONTINUITY:")
    assert urls[0] != "url://prev_shot.jpg"


def test_a_saturated_face_set_gives_up_exactly_one_slot(tmp_path, fal_capture) -> None:
    """The only displacement in the whole reference programme, and it is bounded.

    Identity already has coverage-ordered references, a scorer, a sheet and a
    lab; scene continuity had NO delivery on this route at all. Zero-to-one
    beats six-to-five. Position six is also the weakest face slot by
    construction — order_for_coverage spends the early slots on the canonical
    and one reference per unseen facet, so the tail is the least differentiated.
    """

    faces = _refs(tmp_path, 10)
    _fal_flux_fallback(
        "a prompt", str(tmp_path / "out.jpg"),
        character_image=faces[0], multi_angle_refs=faces,
        continuity_reference=_anchor(tmp_path),
    )
    urls = fal_capture["arguments"]["image_urls"]
    assert len(urls) == _MULTICHAR_REF_CAP
    assert urls[-1] == "url://prev_shot.jpg"
    # Exactly one face gave way, not two.
    assert len(urls) - 1 == _MULTICHAR_REF_CAP - CONTINUITY_SLOT_BUDGET


def test_without_an_anchor_the_face_budget_is_untouched(tmp_path, fal_capture) -> None:
    """Control for the test above — the displacement must be able to be absent.

    Also the backward-compatibility pin: a project with no approved previous
    keyframe (every scene's first shot) sees byte-identical behaviour.
    """

    faces = _refs(tmp_path, 10)
    _fal_flux_fallback(
        "a prompt", str(tmp_path / "out.jpg"),
        character_image=faces[0], multi_angle_refs=faces,
    )
    urls = fal_capture["arguments"]["image_urls"]
    assert len(urls) == _MULTICHAR_REF_CAP
    assert all(url != "url://prev_shot.jpg" for url in urls)
    assert "PREVIOUS SHOT" not in fal_capture["arguments"]["prompt"]


def test_an_anchor_missing_from_disk_is_ignored_silently(tmp_path, fal_capture) -> None:
    """A stale path must not cost a face slot NOR add a prompt block pointing at
    an image that was never sent."""

    faces = _refs(tmp_path, 10)
    _fal_flux_fallback(
        "a prompt", str(tmp_path / "out.jpg"),
        character_image=faces[0], multi_angle_refs=faces,
        continuity_reference=str(tmp_path / "gone.jpg"),
    )
    urls = fal_capture["arguments"]["image_urls"]
    assert len(urls) == _MULTICHAR_REF_CAP
    assert "PREVIOUS SHOT" not in fal_capture["arguments"]["prompt"]


def test_the_result_reports_whether_the_anchor_was_actually_sent(
    tmp_path, fal_capture
) -> None:
    """Recorded, not assumed. A continuity regression has to be traceable to
    "the anchor was not sent" rather than argued about from the frame."""

    faces = _refs(tmp_path, 2)
    delivered = _fal_flux_fallback(
        "a prompt", str(tmp_path / "out.jpg"),
        character_image=faces[0], multi_angle_refs=faces,
        continuity_reference=_anchor(tmp_path),
    )
    assert delivered.continuity_delivered is True

    withheld = _fal_flux_fallback(
        "a prompt", str(tmp_path / "out2.jpg"),
        character_image=faces[0], multi_angle_refs=faces,
    )
    assert withheld.continuity_delivered is False


# ---------------------------------------------------------------------------
# Multi-character Kontext — spare capacity only, no face ever displaced
# ---------------------------------------------------------------------------

def _secondary(tmp_path, char_id, count=1):
    paths = _refs(tmp_path, count, prefix=f"{char_id}_face")
    return {
        "char_id": char_id,
        "reference": paths[0],
        "multi_angle_refs": paths[1:],
        "identity_anchor": char_id.title(),
    }


def test_two_characters_now_fill_the_budget_and_the_anchor_yields(
    tmp_path, fal_capture
) -> None:
    """The no-contest rule, re-measured against the REAL ceiling.

    This test previously asserted the opposite, and it was right at the time:
    with the old cap of six, primary 3 + secondary 2 left a spare slot for the
    anchor. Measurement moved the ceiling to FOUR (ADR-100), so two characters
    now consume the whole budget and the anchor yields rather than displacing a
    face. The rule is unchanged; the arithmetic under it moved.
    """

    primary = _refs(tmp_path, 3, prefix="a_face")
    _fal_flux_fallback(
        "a prompt", str(tmp_path / "out.jpg"),
        character_image=primary[0], multi_angle_refs=primary,
        identity_anchor="Alice",
        secondary_char_refs=[_secondary(tmp_path, "char_b", 2)],
        continuity_reference=_anchor(tmp_path),
    )
    urls = fal_capture["arguments"]["image_urls"]
    assert len(urls) == _MULTICHAR_REF_CAP
    assert all(url != "url://prev_shot.jpg" for url in urls)
    prompt = fal_capture["arguments"]["prompt"]
    assert "PREVIOUS SHOT" not in prompt
    # Both faces still addressed — a person is never dropped for the anchor.
    assert "The person from @Image1 is Alice" in prompt
    assert "@Image4 is Char_B" in prompt


def test_three_characters_fill_the_budget_and_keep_every_face(
    tmp_path, fal_capture
) -> None:
    """3+2+1 reaches the ceiling. A crowded shot carries no anchor rather than
    dropping a person — the no-contest rule, applied where it bites."""

    primary = _refs(tmp_path, 3, prefix="a_face")
    _fal_flux_fallback(
        "a prompt", str(tmp_path / "out.jpg"),
        character_image=primary[0], multi_angle_refs=primary,
        identity_anchor="Alice",
        secondary_char_refs=[
            _secondary(tmp_path, "char_b", 2),
            _secondary(tmp_path, "char_c", 1),
        ],
        continuity_reference=_anchor(tmp_path),
    )
    urls = fal_capture["arguments"]["image_urls"]
    assert len(urls) == _MULTICHAR_REF_CAP
    assert all(url != "url://prev_shot.jpg" for url in urls)
    assert "PREVIOUS SHOT" not in fal_capture["arguments"]["prompt"]


# ---------------------------------------------------------------------------
# Gemini — the DEFAULT backend, and the one where the anchor mattered most
# ---------------------------------------------------------------------------

class TestGeminiCarriesTheAnchor:
    """`gemini_multiref` is the default `identity_backend`, so this route is
    where "scene continuity rides on the prompt and the seed alone" was true
    for most users.

    Harness mirrors TestGeminiImagePrimaryRoute in
    tests/unit/test_phase_c_assembly_provenance.py.
    """

    @pytest.fixture
    def gemini(self, monkeypatch, tmp_path):
        import dataclasses as dc
        import types as _types

        monkeypatch.setattr(
            pca, "settings",
            dc.replace(pca.settings, google_api_key="test-google-key", fal_key=""),
        )
        calls: dict = {}

        class _FakeGeminiImageAPI:
            def generate_image(self, prompt, output_path, **kwargs):
                calls["prompt"] = prompt
                calls["kwargs"] = kwargs
                with open(output_path, "wb") as fh:
                    fh.write(b"gemini-image-bytes")
                return output_path

        module = _types.ModuleType("gemini_image_native")
        module.GeminiImageAPI = _FakeGeminiImageAPI
        module.GEMINI_MULTIREF_MAX_REFS = 8
        monkeypatch.setitem(sys.modules, "gemini_image_native", module)

        class _Result:
            overall_score = 0.85
            passed = True
            threshold_used = 0.65
            character_results: dict = {}

        class _Validator:
            def validate_image(self, *args, **kwargs):
                return _Result()

        monkeypatch.setattr(
            "phase_c_vision._get_shared_validator", lambda: _Validator()
        )
        from cinema.context import PipelineContext
        return calls, PipelineContext(
            global_settings={"identity_backend": "gemini_multiref"}
        )

    def test_the_anchor_rides_at_the_tail_of_the_reference_list(
        self, gemini, tmp_path
    ) -> None:
        """Gemini truncates its combined budget from the FRONT, so the tail is
        the first thing dropped when a shot is crowded. A face is never dropped
        for the anchor."""

        calls, ctx = gemini
        face = _refs(tmp_path, 1)[0]
        anchor = _anchor(tmp_path)

        result = pca.generate_ai_broll(
            "a prompt", str(tmp_path / "out.jpg"),
            character_image=face,
            continuity_reference=anchor,
            ctx=ctx,
        )
        assert result.api_name == "GEMINI_IMAGE"
        assert calls["kwargs"]["secondary_char_refs"][-1] == anchor
        assert result.continuity_delivered is True

    def test_the_prompt_explains_the_extra_image(self, gemini, tmp_path) -> None:
        """Gemini's references carry no slot labels, so an unexplained frame of
        the previous shot is an invitation to render the previous shot again."""

        calls, ctx = gemini
        pca.generate_ai_broll(
            "a prompt", str(tmp_path / "out.jpg"),
            character_image=_refs(tmp_path, 1)[0],
            continuity_reference=_anchor(tmp_path),
            ctx=ctx,
        )
        assert "CONTINUITY" in calls["prompt"]
        assert "FINAL reference image" in calls["prompt"]
        assert "not copy its framing" in calls["prompt"]

    def test_without_an_anchor_the_prompt_and_refs_are_untouched(
        self, gemini, tmp_path
    ) -> None:
        """Control: every scene's FIRST shot has no approved predecessor, and
        must reach Gemini exactly as it did before this change."""

        calls, ctx = gemini
        result = pca.generate_ai_broll(
            "a prompt", str(tmp_path / "out.jpg"),
            character_image=_refs(tmp_path, 1)[0],
            ctx=ctx,
        )
        assert calls["prompt"] == "a prompt"
        assert calls["kwargs"]["secondary_char_refs"] == []
        assert result.continuity_delivered is False
