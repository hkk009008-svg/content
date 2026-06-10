"""Tests for multi-character Kontext branch wired into _fal_flux_fallback (Task 8).

Pure-helper tests (Tasks 6/7): _allocate_ref_slots + _build_multichar_kontext_prompt.
Integration tests (Task 8): _fal_flux_fallback multi-char branch + byte-identity guard.
"""
from __future__ import annotations

import dataclasses
import os
import sys
import urllib.request
from unittest.mock import MagicMock

import pytest

import phase_c_assembly as pca
from phase_c_assembly import _allocate_ref_slots, _build_multichar_kontext_prompt
from tests.unit.test_kontext_prompt_snapshot import GOLDEN_SINGLE_CHAR_PROMPT


# ---------------------------------------------------------------------------
# Fixture — captures the Kontext subscribe call's arguments dict.
# Local copy so pytest fixture resolution does not cross module boundaries.
# ---------------------------------------------------------------------------

@pytest.fixture
def fal_capture(monkeypatch, tmp_path):
    """Stub fal_client and return a dict that is populated with the Kontext
    subscribe endpoint + arguments on the first call.
    Mirrors the fixture shape from test_kontext_prompt_snapshot.py (R-BRIEF).
    """
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
        pca, "settings",
        dataclasses.replace(pca.settings, fal_key="test-key"),
    )

    def _fake_retrieve(url, filename):
        with open(filename, "wb") as fh:
            fh.write(b"jpeg-bytes")

    monkeypatch.setattr(urllib.request, "urlretrieve", _fake_retrieve)
    return captured


def test_two_char_allocation_3_2():
    paths, slot_map = _allocate_ref_slots(
        primary_refs=["/a/1.jpg", "/a/2.jpg", "/a/3.jpg", "/a/4.jpg"],
        secondary_chars=[{"char_id": "char_b", "reference": "/b/c.jpg",
                          "multi_angle_refs": ["/b/1.jpg", "/b/2.jpg"]}],
    )
    assert paths == ["/a/1.jpg", "/a/2.jpg", "/a/3.jpg", "/b/c.jpg", "/b/1.jpg"]
    assert slot_map == {"primary": [1, 2, 3], "char_b": [4, 5]}


def test_three_char_allocation_3_2_1_and_six_cap():
    paths, slot_map = _allocate_ref_slots(
        primary_refs=["/a/1.jpg", "/a/2.jpg", "/a/3.jpg"],
        secondary_chars=[
            {"char_id": "char_b", "reference": "/b/c.jpg",
             "multi_angle_refs": ["/b/1.jpg"]},
            {"char_id": "char_c", "reference": "/c/c.jpg",
             "multi_angle_refs": ["/c/1.jpg", "/c/2.jpg"]},
        ],
    )
    assert len(paths) == 6
    assert slot_map == {"primary": [1, 2, 3], "char_b": [4, 5], "char_c": [6]}


def test_thin_secondary_does_not_inflate_primary():
    """Slots are CONTIGUOUS and shares are FIXED (primary 3 / sec-1 2 / sec-2 1):
    a thin secondary leaves the cap unfilled rather than reordering slots."""
    paths, slot_map = _allocate_ref_slots(
        primary_refs=["/a/1.jpg", "/a/2.jpg", "/a/3.jpg", "/a/4.jpg", "/a/5.jpg"],
        secondary_chars=[{"char_id": "char_b", "reference": "/b/c.jpg",
                          "multi_angle_refs": []}],
    )
    assert slot_map["primary"] == [1, 2, 3]   # fixed at 3 when secondaries exist
    assert slot_map["char_b"] == [4]          # canonical only — nothing to fill with
    assert len(paths) == 4                    # cap is a ceiling, not a quota


def test_single_char_alone_keeps_all_six():
    paths, slot_map = _allocate_ref_slots(
        primary_refs=[f"/a/{i}.jpg" for i in range(8)], secondary_chars=[],
    )
    assert slot_map == {"primary": [1, 2, 3, 4, 5, 6]}
    assert len(paths) == 6


def test_multichar_prompt_addresses_each_slot():
    prompt = _build_multichar_kontext_prompt(
        {"SCENE": "a rooftop cafe", "ACTION": "talking", "OUTFIT": "",
         "SHOT": "Medium two-shot"},
        char_blocks=[(1, "a woman with auburn hair"), (4, "a man with a grey beard")],
    )
    assert "@Image1 is a woman with auburn hair" in prompt
    assert "@Image4 is a man with a grey beard" in prompt
    assert "Do NOT blend or average" in prompt
    assert "Do NOT transfer clothing" in prompt   # S1 wardrobe cross-bleed pin
    assert "CHANGE BACKGROUND: a rooftop cafe." in prompt
    assert prompt.count("PRESERVE IDENTITY") == 2


# ---------------------------------------------------------------------------
# Integration tests — _fal_flux_fallback multi-char branch (Task 8)
# ---------------------------------------------------------------------------

def test_multichar_branch_sends_both_chars_refs_and_blocks(fal_capture, tmp_path):
    """Multi-char branch uploads both character refs, addresses each with @ImageN,
    and includes two PRESERVE IDENTITY blocks in the Kontext prompt."""
    a = tmp_path / "a.jpg"
    a.write_bytes(b"j")
    b = tmp_path / "b.jpg"
    b.write_bytes(b"j")
    out = tmp_path / "out.jpg"

    result = pca._fal_flux_fallback(
        "A rooftop cafe",
        str(out),
        character_image=str(a),
        identity_anchor="a woman with auburn hair",
        secondary_char_refs=[{
            "char_id": "char_b",
            "reference": str(b),
            "multi_angle_refs": [],
            "identity_anchor": "a man with a grey beard",
        }],
    )

    assert result is not None
    assert result.api_name == "FLUX_KONTEXT"
    args = fal_capture["arguments"]
    assert len(args["image_urls"]) == 2
    assert "@Image2 is a man with a grey beard" in args["prompt"]
    assert args["prompt"].count("PRESERVE IDENTITY") == 2


def test_empty_secondary_refs_is_byte_identical_to_single_char(fal_capture, tmp_path):
    """Early return: secondary_char_refs=[] takes the old single-char path and
    produces the exact GOLDEN_SINGLE_CHAR_PROMPT (byte-for-byte)."""
    ref = tmp_path / "aria.jpg"
    ref.write_bytes(b"jpg")
    out = tmp_path / "out.jpg"

    result = pca._fal_flux_fallback(
        "A quiet rooftop at dusk",
        str(out),
        character_image=str(ref),
        identity_anchor="a woman with auburn hair and green eyes",
        secondary_char_refs=[],
    )

    assert result is not None
    assert result.api_name == "FLUX_KONTEXT"
    args = fal_capture["arguments"]
    assert args["prompt"] == GOLDEN_SINGLE_CHAR_PROMPT, (
        f"Single-char path drifted with empty secondary_char_refs.\n"
        f"Expected:\n{GOLDEN_SINGLE_CHAR_PROMPT}\n\nGot:\n{args['prompt']}"
    )
