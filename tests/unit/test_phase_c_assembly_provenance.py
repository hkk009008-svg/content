"""Provenance threading for image-generation backends (phase_c_assembly).

Keyframe cost attribution requires knowing which backend actually produced an
image — the ComfyUI/PuLID pod vs a FAL fallback (and which FAL model). These
tests pin the `api_name` each branch reports via `ImageGenResult`, so cost_log
can distinguish "ran on the pod" from "fell back to FAL".

Offline: fal_client and the image download are stubbed; no GPU, no pod, no
network, no API calls.
"""

from __future__ import annotations

import dataclasses
import sys
import urllib.request
from unittest.mock import MagicMock

import pytest

import phase_c_assembly as pca


@pytest.fixture
def stub_fal(monkeypatch):
    """Stub the lazily-imported `fal_client` + the image download so
    `_fal_flux_fallback` runs offline and deterministically succeeds."""
    fake = MagicMock()
    fake.upload_file.return_value = "https://fake/upload"
    fake.subscribe.return_value = {"images": [{"url": "https://fake/image.jpg"}]}
    monkeypatch.setitem(sys.modules, "fal_client", fake)
    # settings is a frozen dataclass — replace the whole object (preserving
    # every other field) rather than setattr-ing a field.
    monkeypatch.setattr(pca, "settings", dataclasses.replace(pca.settings, fal_key="test-key"))

    def _fake_retrieve(url, filename):
        with open(filename, "wb") as fh:
            fh.write(b"jpeg-bytes")

    monkeypatch.setattr(urllib.request, "urlretrieve", _fake_retrieve)
    return fake


class TestFalFallbackProvenance:
    """`_fal_flux_fallback` reports which FAL model produced the image."""

    def test_kontext_branch_reports_flux_kontext(self, stub_fal, tmp_path):
        # A character reference engages Kontext Max Multi (identity-preserving).
        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")

        res = pca._fal_flux_fallback("a prompt", out, seed=7, character_image=str(char))

        assert isinstance(res, pca.ImageGenResult)
        assert res.path == out
        assert res.api_name == "FLUX_KONTEXT"

    def test_fluxpro_branch_reports_flux_pro(self, stub_fal, tmp_path):
        # No character reference → skip Kontext, run FLUX-Pro (no face-lock).
        out = str(tmp_path / "out.jpg")

        res = pca._fal_flux_fallback("a prompt", out, seed=7, character_image=None)

        assert isinstance(res, pca.ImageGenResult)
        assert res.api_name == "FLUX_PRO"

    def test_schnell_branch_reports_flux_schnell(self, stub_fal, tmp_path):
        # FLUX-Pro fails, FLUX-schnell succeeds → FLUX_SCHNELL.
        stub_fal.subscribe.side_effect = [
            RuntimeError("flux-pro down"),                      # 1st call: FLUX-Pro
            {"images": [{"url": "https://fake/schnell.jpg"}]},  # 2nd call: schnell
        ]
        out = str(tmp_path / "out.jpg")

        res = pca._fal_flux_fallback("a prompt", out, seed=7, character_image=None)

        assert isinstance(res, pca.ImageGenResult)
        assert res.api_name == "FLUX_SCHNELL"

    def test_pollinations_branch_reports_pollinations(self, stub_fal, tmp_path, monkeypatch):
        # FLUX-Pro AND schnell fail; the free Pollinations fallback returns
        # enough bytes → POLLINATIONS.
        stub_fal.subscribe.side_effect = RuntimeError("fal down")

        class _Resp:
            def read(self_inner):
                return b"x" * 6000  # > 5000-byte floor in _fal_flux_fallback

        monkeypatch.setattr(urllib.request, "urlopen", lambda url: _Resp())
        out = str(tmp_path / "out.jpg")

        res = pca._fal_flux_fallback("a prompt", out, seed=7, character_image=None)

        assert isinstance(res, pca.ImageGenResult)
        assert res.api_name == "POLLINATIONS"

    def test_no_fal_key_returns_none(self, monkeypatch, tmp_path):
        # No FAL key → None (failure), so the caller's `if not result` guard
        # still trips and the keyframe is reported as failed.
        monkeypatch.setattr(pca, "settings", dataclasses.replace(pca.settings, fal_key=""))
        res = pca._fal_flux_fallback("p", str(tmp_path / "o.jpg"), character_image=None)
        assert res is None


class TestImageGenResultShape:
    """`ImageGenResult` is a lightweight, backward-compatible carrier."""

    def test_is_truthy_and_carries_fields(self):
        r = pca.ImageGenResult("/tmp/x.jpg", "COMFYUI_PULID")
        assert r  # truthy on success (the caller's `if not result` guard)
        assert r.path == "/tmp/x.jpg"
        assert r.api_name == "COMFYUI_PULID"
