"""Regression for deterministic reference-face embedding selection.

Providers may return detections in arbitrary order. Identity validation must
choose the largest acceptable face instead of trusting the first result.
"""
import numpy as np
import pytest

# The DeepFace detector can return multiple faces in arbitrary
# order, but the reference embedding should match the binding instrument's
# largest-OK selection rather than emb_list[0].
def test_get_embedding_uses_largest_ok_face_not_first_detection(monkeypatch):
    import identity.validator as validator_module

    first_small = np.array([1.0, 0.0, 0.0])
    second_largest_ok = np.array([0.0, 1.0, 0.0])
    detections = [
        {
            "embedding": first_small.tolist(),
            "facial_area": {"x": 5, "y": 5, "w": 80, "h": 80},
            "face_confidence": 0.99,
        },
        {
            "embedding": second_largest_ok.tolist(),
            "facial_area": {"x": 20, "y": 20, "w": 160, "h": 160},
            "face_confidence": 0.99,
        },
    ]

    class FakeImage:
        size = (400, 400)

    class FakePILImage:
        @staticmethod
        def open(_path):
            return FakeImage()

    monkeypatch.setattr(validator_module, "DEEPFACE_AVAILABLE", True)
    monkeypatch.setattr(validator_module, "_PIL_AVAILABLE", True)
    monkeypatch.setattr(validator_module, "_PILImage", FakePILImage)
    monkeypatch.setattr(
        validator_module,
        "_represent_deterministic",
        lambda _path: detections,
    )

    validator = validator_module.IdentityValidator()

    embedding = validator._get_embedding("/ref-with-two-faces.jpg", "char_ref")

    assert np.array_equal(embedding, second_largest_ok), (
        "_get_embedding must select the largest OK detection for reference images "
        "instead of trusting arbitrary DeepFace detection order"
    )
