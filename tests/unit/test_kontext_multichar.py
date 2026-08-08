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
from phase_c_assembly import (
    _MULTICHAR_REF_CAP,
    _allocate_ref_slots,
    _build_multichar_kontext_prompt,
)
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

    def _fake_download(url, filename):
        with open(filename, "wb") as fh:
            fh.write(b"jpeg-bytes")
        return filename

    monkeypatch.setattr(pca, "_download_generated_jpeg", _fake_download)
    return captured


def test_two_char_allocation_fits_the_provider_ceiling():
    """Was `test_two_char_allocation_3_2`, and it pinned an IMPOSSIBLE request.

    MEASURED 2026-08-09: fal-ai/flux-pro/kontext/max/multi returns 422,
    "Value error, image_urls must be between 1 and 4". The old fixed shares
    (primary 3 / first secondary 2 / second 1) total SIX. This test asserted
    five and its sibling asserted six, so both encoded payloads the provider
    rejects — and they passed for months, because they checked the allocator's
    arithmetic and never that the result could be sent.
    """
    paths, slot_map = _allocate_ref_slots(
        primary_refs=["/a/1.jpg", "/a/2.jpg", "/a/3.jpg", "/a/4.jpg"],
        secondary_chars=[{"char_id": "char_b", "reference": "/b/c.jpg",
                          "multi_angle_refs": ["/b/1.jpg", "/b/2.jpg"]}],
    )
    assert len(paths) <= _MULTICHAR_REF_CAP
    assert slot_map == {"primary": [1, 2, 3], "char_b": [4]}
    assert paths == ["/a/1.jpg", "/a/2.jpg", "/a/3.jpg", "/b/c.jpg"]


def test_three_char_allocation_still_gives_everyone_a_slot():
    """The ceiling is four and there are three people; nobody may be dropped.

    A character silently allocated zero references would be generated from the
    prompt alone while the prompt claims @ImageN is them.
    """
    paths, slot_map = _allocate_ref_slots(
        primary_refs=["/a/1.jpg", "/a/2.jpg", "/a/3.jpg"],
        secondary_chars=[
            {"char_id": "char_b", "reference": "/b/c.jpg",
             "multi_angle_refs": ["/b/1.jpg"]},
            {"char_id": "char_c", "reference": "/c/c.jpg",
             "multi_angle_refs": ["/c/1.jpg", "/c/2.jpg"]},
        ],
    )
    assert len(paths) == _MULTICHAR_REF_CAP
    assert slot_map == {"primary": [1, 2], "char_b": [3], "char_c": [4]}


def test_thin_secondary_does_not_inflate_primary():
    """Slots are CONTIGUOUS and shares are FIXED (primary 3 / sec-1 2 / sec-2 1):
    a thin secondary leaves the cap unfilled rather than reordering slots."""
    paths, slot_map = _allocate_ref_slots(
        primary_refs=["/a/1.jpg", "/a/2.jpg", "/a/3.jpg", "/a/4.jpg", "/a/5.jpg"],
        secondary_chars=[{"char_id": "char_b", "reference": "/b/c.jpg",
                          "multi_angle_refs": []}],
    )
    assert slot_map["primary"] == [1, 2, 3]   # cap(4) minus one reserved secondary
    assert slot_map["char_b"] == [4]          # canonical only — nothing to fill with
    assert len(paths) == 4                    # cap is a ceiling, not a quota


def test_single_char_alone_keeps_the_whole_reachable_budget():
    """Was `test_single_char_alone_keeps_all_six`. Six is not sendable.

    This is the case that broke real work: a single character with more than
    four references produced a 422, the cascade fell past Kontext into
    FLUX_PRO/FLUX_SCHNELL — text-to-image with NO reference conditioning — and
    the keyframe came back as a stranger. The failure SCALED WITH REFERENCE
    COUNT, so adding good photographs of the subject is what broke it.
    """
    paths, slot_map = _allocate_ref_slots(
        primary_refs=[f"/a/{i}.jpg" for i in range(8)], secondary_chars=[],
    )
    assert slot_map == {"primary": [1, 2, 3, 4]}
    assert len(paths) == _MULTICHAR_REF_CAP


def test_no_allocation_can_exceed_the_measured_ceiling():
    """The property the old fixed shares had no way to guarantee."""
    for n_sec in range(4):
        paths, slot_map = _allocate_ref_slots(
            primary_refs=[f"/a/{i}.jpg" for i in range(9)],
            secondary_chars=[
                {"char_id": f"c{j}", "reference": f"/c{j}/0.jpg",
                 "multi_angle_refs": [f"/c{j}/{k}.jpg" for k in range(1, 4)]}
                for j in range(n_sec)
            ],
        )
        assert len(paths) <= _MULTICHAR_REF_CAP, (n_sec, paths)
        assert all(slot_map[key] for key in slot_map), (n_sec, slot_map)


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


@pytest.mark.parametrize("empty_refs", [None, []], ids=["none", "empty-list"])
def test_empty_secondary_refs_is_byte_identical_to_single_char(
        fal_capture, tmp_path, empty_refs):
    """Early return: secondary_char_refs=None and =[] BOTH take the old
    single-char path (spec §3a) and produce the exact GOLDEN_SINGLE_CHAR_PROMPT
    (byte-for-byte). The None case pins against an 'is not None' refactor."""
    ref = tmp_path / "aria.jpg"
    ref.write_bytes(b"jpg")
    out = tmp_path / "out.jpg"

    result = pca._fal_flux_fallback(
        "A quiet rooftop at dusk",
        str(out),
        character_image=str(ref),
        identity_anchor="a woman with auburn hair and green eyes",
        secondary_char_refs=empty_refs,
    )

    assert result is not None
    assert result.api_name == "FLUX_KONTEXT"
    args = fal_capture["arguments"]
    assert args["prompt"] == GOLDEN_SINGLE_CHAR_PROMPT, (
        f"Single-char path drifted with empty secondary_char_refs.\n"
        f"Expected:\n{GOLDEN_SINGLE_CHAR_PROMPT}\n\nGot:\n{args['prompt']}"
    )


# ---------------------------------------------------------------------------
# Partial-upload alignment (operator Lane-V disposition, 2026-06-11):
# uploads happen BEFORE slot allocation so @ImageN labels track survivors.
# ---------------------------------------------------------------------------

def test_partial_upload_failure_keeps_imageN_aligned(fal_capture, tmp_path):
    """A silent mid-list upload failure used to left-shift every later image
    while the prompt's @ImageN labels stayed put — the prompt then addressed
    the WRONG reference (old code allocated slots pre-upload)."""
    a1, a2, a3 = (tmp_path / n for n in ("a1.jpg", "a2.jpg", "a3.jpg"))
    bc, b1 = tmp_path / "bc.jpg", tmp_path / "b1.jpg"
    for f in (a1, a2, a3, bc, b1):
        f.write_bytes(b"j")
    out = tmp_path / "out.jpg"
    fal = sys.modules["fal_client"]

    def _upload(path):
        if os.path.basename(str(path)) == "a2.jpg":
            raise RuntimeError("CDN hiccup")
        return f"url://{os.path.basename(str(path))}"

    fal.upload_file.side_effect = _upload
    result = pca._fal_flux_fallback(
        "A rooftop cafe", str(out),
        character_image=str(a1),
        multi_angle_refs=[str(a1), str(a2), str(a3)],
        identity_anchor="a woman with auburn hair",
        secondary_char_refs=[{"char_id": "char_b", "reference": str(bc),
                              "multi_angle_refs": [str(b1)],
                              "identity_anchor": "a man with a grey beard"}],
    )
    assert result.api_name == "FLUX_KONTEXT"
    args = fal_capture["arguments"]
    # survivors only, in slot order: primary [a1, a3] then char_b [bc, b1]
    assert args["image_urls"] == [
        "url://a1.jpg", "url://a3.jpg", "url://bc.jpg", "url://b1.jpg"]
    # char_b's first slot is 3 — right after the 2 SURVIVING primary refs
    # (the old desync labelled it @Image4 against a 4-image list)
    assert "@Image3 is a man with a grey beard" in args["prompt"]


def test_secondary_canonical_upload_failure_drops_its_block(fal_capture, tmp_path):
    """A secondary whose canonical fails to upload is dropped entirely — no
    PRESERVE block addressing a slot that does not exist; the primary
    reclaims the full budget (allocator sees a single-char allocation)."""
    a1, bc = tmp_path / "a1.jpg", tmp_path / "bc.jpg"
    a1.write_bytes(b"j")
    bc.write_bytes(b"j")
    out = tmp_path / "out.jpg"
    fal = sys.modules["fal_client"]

    def _upload(path):
        if os.path.basename(str(path)) == "bc.jpg":
            raise RuntimeError("CDN hiccup")
        return f"url://{os.path.basename(str(path))}"

    fal.upload_file.side_effect = _upload
    result = pca._fal_flux_fallback(
        "A rooftop cafe", str(out),
        character_image=str(a1),
        identity_anchor="a woman with auburn hair",
        secondary_char_refs=[{"char_id": "char_b", "reference": str(bc),
                              "multi_angle_refs": [],
                              "identity_anchor": "a man with a grey beard"}],
    )
    assert result.api_name == "FLUX_KONTEXT"
    args = fal_capture["arguments"]
    assert args["image_urls"] == ["url://a1.jpg"]
    assert args["prompt"].count("PRESERVE IDENTITY") == 1
    assert "a man with a grey beard" not in args["prompt"]


def test_all_primary_uploads_fail_degrades_single_char(fal_capture, tmp_path):
    """Every PRIMARY upload failing forces the single-char degradation guard
    even when a secondary uploaded fine — @ImageN can never address a
    primary that is not in image_urls."""
    a1, a2, c, bc = (tmp_path / n for n in ("a1.jpg", "a2.jpg", "c.jpg", "bc.jpg"))
    for f in (a1, a2, c, bc):
        f.write_bytes(b"j")
    out = tmp_path / "out.jpg"
    fal = sys.modules["fal_client"]

    def _upload(path):
        if os.path.basename(str(path)) in ("a1.jpg", "a2.jpg"):
            raise RuntimeError("CDN hiccup")
        return f"url://{os.path.basename(str(path))}"

    fal.upload_file.side_effect = _upload
    result = pca._fal_flux_fallback(
        "A rooftop cafe", str(out),
        character_image=str(c),
        multi_angle_refs=[str(a1), str(a2)],
        identity_anchor="a woman with auburn hair",
        secondary_char_refs=[{"char_id": "char_b", "reference": str(bc),
                              "multi_angle_refs": [],
                              "identity_anchor": "a man with a grey beard"}],
    )
    assert result.api_name == "FLUX_KONTEXT"
    args = fal_capture["arguments"]
    assert args["image_urls"] == ["url://c.jpg"]
    assert args["prompt"].count("PRESERVE IDENTITY") == 1
