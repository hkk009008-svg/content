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


class TestKontextFailureProvenance:
    """V-1 pin (spec AC6 / Lane-V V-6): Kontext failure with secondaries falls
    back with the ORIGINAL prompt — the multi-char rewrite must never escape the
    Kontext try-block (phase_c_assembly passes `prompt`, not `kontext_prompt`,
    to the FLUX-Pro fallback)."""

    def test_kontext_failure_with_secondaries_falls_back_with_original_prompt(
        self, monkeypatch, tmp_path
    ):
        """When the Kontext subscribe raises and secondary_char_refs were passed,
        the FLUX-Pro fallback receives the ORIGINAL prompt (no @Image in it)
        and result.api_name == FLUX_PRO."""
        fake = MagicMock()
        fake.upload_file.return_value = "https://fake/upload"
        # 1st subscribe call → Kontext endpoint raises; 2nd → FLUX-Pro succeeds
        flux_pro_captured: dict = {}

        def _subscribe(endpoint, **kwargs):
            if "kontext" in endpoint:
                raise RuntimeError("kontext down for test")
            flux_pro_captured["endpoint"] = endpoint
            flux_pro_captured["arguments"] = kwargs.get("arguments", {})
            return {"images": [{"url": "https://fake/fluxpro.jpg"}]}

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

        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        secondary = tmp_path / "secondary.jpg"
        secondary.write_bytes(b"sec")
        out = str(tmp_path / "out.jpg")
        original_prompt = "A rooftop scene at golden hour"

        result = pca._fal_flux_fallback(
            original_prompt,
            out,
            character_image=str(char),
            identity_anchor="a woman with auburn hair",
            secondary_char_refs=[{
                "char_id": "char_b",
                "reference": str(secondary),
                "multi_angle_refs": [],
                "identity_anchor": "a man with a grey beard",
            }],
        )

        assert result is not None
        assert result.api_name == "FLUX_PRO"
        # V-1 invariant: FLUX-Pro received the ORIGINAL prompt, not the @ImageN rewrite
        captured_prompt = flux_pro_captured["arguments"]["prompt"]
        assert captured_prompt == original_prompt, (
            f"V-1 VIOLATED: FLUX-Pro received rewritten prompt.\n"
            f"Expected: {original_prompt!r}\nGot: {captured_prompt!r}"
        )
        assert "@Image" not in captured_prompt, (
            f"V-1 VIOLATED: @ImageN token escaped the Kontext try-block: {captured_prompt!r}"
        )


class TestImageGenResultShape:
    """`ImageGenResult` is a lightweight, backward-compatible carrier."""

    def test_is_truthy_and_carries_fields(self):
        r = pca.ImageGenResult("/tmp/x.jpg", "COMFYUI_PULID")
        assert r  # truthy on success (the caller's `if not result` guard)
        assert r.path == "/tmp/x.jpg"
        assert r.api_name == "COMFYUI_PULID"
