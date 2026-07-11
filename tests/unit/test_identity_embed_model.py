"""Pins for the identity-embedding chokepoint (P5, 2026-07-11).

The DeepFace ``model_name`` string was hardcoded at three production sites
(identity/validator, domain/character_manager, domain/continuity_engine) —
the same label-vs-literal drift class as the "Kling 3.0" client that ran
kling-v1-6 (docs claimed "ArcFace embeddings"; the code ran GhostFaceNet).
Now ``identity.validator.EMBED_MODEL`` is the single write-site, fed by the
``IDENTITY_EMBED_MODEL`` env (default GhostFaceNet).

IMPORTANT calibration invariant pinned here: every identity threshold in the
repo is calibrated on GhostFaceNet score distributions — a non-default model
must trigger the structural warning until a pod re-calibration pass exists
(P5 in docs/RESEARCH-2026-07-10-component-upgrades.md).
"""
from __future__ import annotations

import warnings

import pytest


class TestEmbedModelChokepoint:
    def test_default_is_ghostfacenet(self):
        from config.settings import settings
        from identity.validator import EMBED_MODEL
        assert settings.identity_embed_model == "GhostFaceNet"
        assert EMBED_MODEL == "GhostFaceNet"

    def test_no_hardcoded_model_strings_remain(self):
        """The three production represent sites must use the shared constant."""
        import pathlib
        repo = pathlib.Path(__file__).resolve().parents[2]
        for rel in (
            "identity/validator.py",
            "domain/character_manager.py",
            "domain/continuity_engine.py",
        ):
            src = (repo / rel).read_text()
            assert 'model_name="GhostFaceNet"' not in src, (
                f"{rel} regained a hardcoded embedding model string — use "
                f"identity.validator.EMBED_MODEL (single write-site)"
            )
            assert "model_name=EMBED_MODEL" in src, (
                f"{rel} no longer routes through the EMBED_MODEL chokepoint"
            )

    def test_non_default_model_fires_structural_warning(self, monkeypatch):
        """Selecting a non-GhostFaceNet model must warn that the calibrated
        thresholds are invalid for it (the gates would silently mis-gate)."""
        import sys
        import identity.validator as v
        # config/__init__ re-exports the instance as `config.settings`,
        # shadowing the submodule on attribute access — go via sys.modules.
        settings_mod = sys.modules["config.settings"]

        class _S:
            identity_embed_model = "Buffalo_L"

        monkeypatch.setattr(settings_mod, "settings", _S())
        with pytest.warns(UserWarning, match="UNCALIBRATED"):
            model = v._resolve_embed_model()
        assert model == "Buffalo_L"

    def test_default_model_is_silent(self, monkeypatch):
        import sys
        import identity.validator as v
        settings_mod = sys.modules["config.settings"]

        class _S:
            identity_embed_model = "GhostFaceNet"

        monkeypatch.setattr(settings_mod, "settings", _S())
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert v._resolve_embed_model() == "GhostFaceNet"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
