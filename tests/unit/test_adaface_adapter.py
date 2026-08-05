"""AdaFace embedding adapter (P5 item 1) — behavior pins.

AdaFace is NOT a DeepFace built-in: it is vendored (identity/adaface_net.py,
MIT, github.com/mk-minchul/AdaFace) and selected via IDENTITY_EMBED_MODEL=
AdaFace. The dispatch seam is identity.validator.represent_deterministic —
the single represent chokepoint ALL identity-QC embedding reads route
through (validator internals + domain/character_manager +
domain/continuity_engine).

Pins the two known sharp edges from the P5 research row
(docs/RESEARCH-2026-07-10-component-upgrades.md):
  1. Input convention is 112x112 **BGR** mean=0.5/std=0.5 — opposite channel
     order from the DeepFace stack. A silent RGB feed would produce valid-
     looking but degraded embeddings (no crash, wrong scores).
  2. AdaFace is UNCALIBRATED until the production-host paired-measurement pass (P5 item
     2): selecting it must still fire the structural warning, and a missing
     checkpoint must fail LOUDLY at resolve time — never degrade to the
     silent skip path (_get_embedding swallows per-call exceptions and
     validate_* then returns passed=True/skipped=True: the silent-gate-
     degradation class).
"""
from __future__ import annotations

import contextlib
import os

import numpy as np
import pytest
import torch


# ---------------------------------------------------------------------------
# Preprocessing: the BGR mean=0.5/std=0.5 convention (official inference.py)
# ---------------------------------------------------------------------------


class TestPreprocess:
    def test_channel_flip_and_normalization_float01(self):
        """RGB float [0,1] input (DeepFace extract_faces output convention):
        channels must land BGR-ordered, scaled (x - 0.5) / 0.5."""
        from identity.adaface import preprocess_face

        face = np.zeros((112, 112, 3), dtype=np.float64)
        face[:, :, 0] = 1.0   # R
        face[:, :, 1] = 0.5   # G
        face[:, :, 2] = 0.0   # B

        tensor = preprocess_face(face)

        assert tensor.shape == (1, 3, 112, 112)
        assert tensor.dtype == torch.float32
        # BGR order: channel 0 = B = (0.0-0.5)/0.5 = -1, channel 2 = R = +1
        assert torch.allclose(tensor[0, 0], torch.full((112, 112), -1.0))
        assert torch.allclose(tensor[0, 1], torch.full((112, 112), 0.0))
        assert torch.allclose(tensor[0, 2], torch.full((112, 112), 1.0))

    def test_uint8_input_scaled_to_same_range(self):
        """uint8 [0,255] input must divide by 255 before the mean/std map."""
        from identity.adaface import preprocess_face

        face = np.zeros((112, 112, 3), dtype=np.uint8)
        face[:, :, 0] = 255  # R
        face[:, :, 2] = 0    # B

        tensor = preprocess_face(face)
        assert torch.allclose(tensor[0, 0], torch.full((112, 112), -1.0))
        assert torch.allclose(tensor[0, 2], torch.full((112, 112), 1.0))

    def test_non_112_input_resized(self):
        from identity.adaface import preprocess_face

        face = np.random.default_rng(0).random((80, 50, 3))
        tensor = preprocess_face(face)
        assert tensor.shape == (1, 3, 112, 112)


# ---------------------------------------------------------------------------
# Vendored net: builds and emits L2-normalized 512-d embeddings
# ---------------------------------------------------------------------------


class TestVendoredNet:
    def test_build_forward_512_l2_normalized(self):
        """ir_18 (smallest build_model arch) forward: (1,512) embedding,
        L2-normalized (official Backbone.forward divides by the norm)."""
        from identity.adaface_net import build_model

        model = build_model("ir_18")
        model.eval()
        with torch.no_grad():
            emb, norm = model(torch.randn(1, 3, 112, 112))
        assert emb.shape == (1, 512)
        assert norm.shape == (1, 1)
        assert torch.allclose(emb.norm(dim=1), torch.ones(1), atol=1e-4)


# ---------------------------------------------------------------------------
# represent(): DeepFace-shaped output from the shared detection stack
# ---------------------------------------------------------------------------


class _FakeNet:
    """Stands in for the loaded AdaFace net: returns a fixed embedding."""

    def __call__(self, tensor):
        emb = torch.ones(tensor.shape[0], 512)
        return emb / emb.norm(dim=1, keepdim=True), torch.ones(tensor.shape[0], 1)


class TestRepresent:
    def test_output_mimics_deepface_represent_shape(self, monkeypatch):
        """represent() must return DeepFace.represent-shaped entries —
        embedding + facial_area + face_confidence — so downstream selection
        (_classify_face_detection / _largest_ok_embedding) works unchanged."""
        import identity.adaface as af

        monkeypatch.setattr(af, "_load_model", lambda: _FakeNet())

        fa = {"x": 4, "y": 5, "w": 40, "h": 50}
        def fake_extract(img_path, enforce_detection, align=True):
            return [{
                "face": np.random.default_rng(1).random((60, 60, 3)),
                "facial_area": dict(fa),
                "confidence": 0.97,
            }]
        monkeypatch.setattr(af, "_extract_faces", fake_extract)

        out = af.represent(img_path="whatever.jpg", enforce_detection=False)

        assert isinstance(out, list) and len(out) == 1
        entry = out[0]
        assert len(entry["embedding"]) == 512
        assert entry["facial_area"] == fa
        assert entry["face_confidence"] == 0.97


# ---------------------------------------------------------------------------
# Dispatch: EMBED_MODEL=AdaFace routes the chokepoint to the adapter,
# strictly inside the cv2 single-thread guard
# ---------------------------------------------------------------------------


def _spy_guard(events):
    @contextlib.contextmanager
    def guard():
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")
    return guard


class TestDispatch:
    def test_adaface_routes_to_adapter_inside_guard(self, monkeypatch):
        import identity.validator as v
        import identity.adaface as af

        events = []
        monkeypatch.setattr(v, "EMBED_MODEL", "AdaFace")
        monkeypatch.setattr(v, "_cv2_single_thread", _spy_guard(events))

        sentinel = [{"embedding": [0.0] * 512}]
        def fake_represent(img_path, enforce_detection):
            events.append("adaface")
            return sentinel
        monkeypatch.setattr(af, "represent", fake_represent)
        monkeypatch.setattr(
            v.DeepFace, "represent",
            lambda *a, **k: pytest.fail("DeepFace.represent must NOT be called for AdaFace"),
        )

        out = v.represent_deterministic("x.jpg")
        assert out is sentinel
        assert events == ["enter", "adaface", "exit"], events

    def test_default_routes_to_deepface_with_embed_model(self, monkeypatch):
        import identity.validator as v

        events = []
        monkeypatch.setattr(v, "EMBED_MODEL", "GhostFaceNet")
        monkeypatch.setattr(v, "_cv2_single_thread", _spy_guard(events))

        captured = {}
        def fake_represent(img_path, model_name, enforce_detection):
            events.append("deepface")
            captured["model_name"] = model_name
            return [{"embedding": [0.1] * 512}]
        monkeypatch.setattr(v.DeepFace, "represent", fake_represent)

        v.represent_deterministic("x.jpg")
        assert captured["model_name"] == "GhostFaceNet"
        assert events == ["enter", "deepface", "exit"], events

    def test_private_alias_preserved(self):
        """Internal validator call sites use _represent_deterministic; it must
        be the same function as the public chokepoint."""
        import identity.validator as v
        assert v._represent_deterministic is v.represent_deterministic


# ---------------------------------------------------------------------------
# Resolve-time safety: fail LOUD on missing checkpoint, keep the structural
# warning firing (AdaFace stays uncalibrated until P5 item 2)
# ---------------------------------------------------------------------------


class TestResolveEmbedModel:
    def _patch_settings(self, monkeypatch, model, ckpt="", arch="ir_101"):
        import sys
        settings_mod = sys.modules["config.settings"]

        class _S:
            identity_embed_model = model
            identity_adaface_ckpt = ckpt
            identity_adaface_arch = arch

        monkeypatch.setattr(settings_mod, "settings", _S())

    def test_adaface_missing_checkpoint_raises_actionable(self, monkeypatch, tmp_path):
        """No checkpoint → RuntimeError at resolve time naming the download
        script. NEVER defer to per-call failure: _get_embedding swallows
        exceptions and validate_* would silently skip (passed=True)."""
        import identity.validator as v
        import identity.adaface as af

        self._patch_settings(
            monkeypatch, "AdaFace", ckpt=str(tmp_path / "absent.ckpt")
        )
        with pytest.warns(UserWarning, match="UNCALIBRATED"):
            with pytest.raises(RuntimeError, match="download_adaface_ckpt"):
                v._resolve_embed_model()

    def test_adaface_ready_still_warns_uncalibrated(self, monkeypatch):
        """The brief's hard requirement: the structural warning must keep
        firing for AdaFace until the production-host calibration pass lands."""
        import identity.validator as v
        import identity.adaface as af

        self._patch_settings(monkeypatch, "AdaFace")
        monkeypatch.setattr(af, "assert_ready", lambda: None)
        with pytest.warns(UserWarning, match="UNCALIBRATED"):
            assert v._resolve_embed_model() == "AdaFace"


# ---------------------------------------------------------------------------
# Disk-cache keying: embeddings from different backbones must never collide
# ---------------------------------------------------------------------------


class TestDiskCacheKeying:
    def test_non_default_model_gets_suffixed_cache_file(self, monkeypatch, tmp_path):
        """A warm GhostFaceNet emb_*.npy cache must not be served to an
        AdaFace run (cross-model cosine is meaningless — and silent)."""
        import identity.validator as v

        validator = v.IdentityValidator(cache_dir=str(tmp_path))
        monkeypatch.setattr(v, "EMBED_MODEL", "AdaFace")
        path = validator._disk_cache_path("ref1")
        assert path is not None and path.endswith("emb_ref1__AdaFace.npy")

    def test_default_model_keeps_legacy_cache_name(self, monkeypatch, tmp_path):
        """GhostFaceNet keeps the historical emb_<key>.npy name so existing
        caches stay valid."""
        import identity.validator as v

        validator = v.IdentityValidator(cache_dir=str(tmp_path))
        monkeypatch.setattr(v, "EMBED_MODEL", "GhostFaceNet")
        path = validator._disk_cache_path("ref1")
        assert path is not None and path.endswith("emb_ref1.npy")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
