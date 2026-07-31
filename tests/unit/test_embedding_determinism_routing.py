"""Regression guard: domain/ face-embedding call sites route through the shared
cv2 single-thread determinism guard.

The OpenCV align step races under multithreading (~1/20 — operator d48b58b:
cos-dist 0.456, binding score 0.870->0.762). identity/validator.py already guards
its own represent/extract_faces sites via `_cv2_single_thread`; these tests pin the
previously-UNROUTED siblings in domain/character_manager.py + domain/continuity_engine.py
so the race can't bake a non-deterministic value into a continuity comparison or the
persisted embedding.npy.

Spy-guard strategy (backend-independent): replace identity.validator.cv2_single_thread
with a context manager that records enter/exit, replace the DeepFace call with one that
records "call", and assert the call happens strictly INSIDE the guard context. This
proves the structural routing without depending on cv2's build-specific thread counts
(setNumThreads(1) serializes on TBB/pthreads but is a no-op on macOS GCD).
"""
import contextlib

import numpy as np
import pytest


def _spy_guard(events):
    @contextlib.contextmanager
    def guard():
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")
    return guard


def test_public_guard_alias_exported():
    """identity.validator exposes a public cv2_single_thread alias (the shared guard)
    so domain/ call sites import a public name, not a private."""
    from identity.validator import cv2_single_thread, _cv2_single_thread
    assert cv2_single_thread is _cv2_single_thread


def test_compute_face_embedding_routes_through_shared_chokepoint(monkeypatch):
    """character_manager.compute_face_embedding (persists embedding.npy) must
    route through identity.validator.represent_deterministic — the shared
    chokepoint that owns BOTH the single-thread guard and the EMBED_MODEL
    dispatch (a direct DeepFace.represent would bypass the guard AND crash
    under IDENTITY_EMBED_MODEL=AdaFace). Guard-inside-chokepoint is pinned
    separately in tests/unit/test_adaface_adapter.py::TestDispatch."""
    import identity.validator as v
    import domain.character_manager as cm
    events = []
    monkeypatch.setattr(cm, "DEEPFACE_AVAILABLE", True)

    def fake_chokepoint(image_path):
        events.append("chokepoint")
        return [{"embedding": [0.1] * 512}]
    monkeypatch.setattr(v, "represent_deterministic", fake_chokepoint)
    monkeypatch.setattr(
        cm.DeepFace, "represent",
        lambda *a, **k: pytest.fail("direct DeepFace.represent bypasses the chokepoint"),
    )

    out = cm.compute_face_embedding("x.jpg")
    assert events == ["chokepoint"], events
    assert isinstance(out, np.ndarray)


def test_count_faces_routes_extract_through_guard(monkeypatch):
    """character_manager._count_faces must run DeepFace.extract_faces inside the guard."""
    import identity.validator as v
    import domain.character_manager as cm
    events = []
    monkeypatch.setattr(cm, "DEEPFACE_AVAILABLE", True)
    monkeypatch.setattr(v, "cv2_single_thread", _spy_guard(events))

    def fake_extract(*a, **k):
        events.append("call")
        return [{"face": None}, {"face": None}]
    monkeypatch.setattr(cm.DeepFace, "extract_faces", fake_extract)

    assert cm._count_faces("x.jpg") == 2
    assert events == ["enter", "call", "exit"], events


def test_has_detectable_face_routes_extract_through_guard(monkeypatch):
    """character_manager._has_detectable_face must run extract_faces inside the guard."""
    import identity.validator as v
    import domain.character_manager as cm
    events = []
    monkeypatch.setattr(cm, "DEEPFACE_AVAILABLE", True)
    monkeypatch.setattr(v, "cv2_single_thread", _spy_guard(events))

    def fake_extract(*a, **k):
        events.append("call")
        return [{"face": None}]
    monkeypatch.setattr(cm.DeepFace, "extract_faces", fake_extract)

    assert cm._has_detectable_face("x.jpg") is True
    assert events == ["enter", "call", "exit"], events


def test_continuity_validate_routes_both_face_calls_deterministically(monkeypatch):
    """continuity_engine.CharacterContinuityTracker.validate_multi_identity must run
    extract_faces inside the guard AND its per-face represent through the shared
    represent_deterministic chokepoint (which owns guard + EMBED_MODEL dispatch —
    pinned in tests/unit/test_adaface_adapter.py::TestDispatch). Without the
    routing the events would be bare ['call'] (un-routed) — this closes the
    silent-strip gap the determinism-fix verifier flagged for the continuity
    siblings."""
    import cv2
    import numpy as np
    import identity.validator as v
    import domain.continuity_engine as ce

    events = []
    monkeypatch.setattr(ce, "DEEPFACE_AVAILABLE", True)
    monkeypatch.setattr(v, "cv2_single_thread", _spy_guard(events))
    monkeypatch.setattr(cv2, "imwrite", lambda *a, **k: True)

    class _FakeCap:
        def __init__(self, *a):
            self._read = 0

        def get(self, *a):
            return 9  # total frames

        def set(self, *a):
            pass

        def read(self):
            self._read += 1
            if self._read == 1:
                return True, np.zeros((32, 32, 3), dtype=np.uint8)
            return False, None  # only one frame, rest of the positions short-circuit

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", _FakeCap)

    def _spy_call(ret):
        def _f(*a, **k):
            events.append("call")
            return ret
        return _f

    monkeypatch.setattr(ce.DeepFace, "extract_faces",
                        _spy_call([{"face": np.zeros((16, 16, 3), dtype=np.uint8)}]))

    def fake_chokepoint(image_path):
        events.append("chokepoint")
        return [{"embedding": [0.1] * 512}]
    monkeypatch.setattr(v, "represent_deterministic", fake_chokepoint)
    monkeypatch.setattr(
        ce.DeepFace, "represent",
        lambda *a, **k: pytest.fail("direct DeepFace.represent bypasses the chokepoint"),
    )

    tracker = object.__new__(ce.CharacterContinuityTracker)  # bypass the heavy project ctor
    tracker.embeddings = {}
    tracker.characters = {}
    tracker.validate_multi_identity("v.mp4", ["c1"])

    # extract_faces guarded locally, then represent via the shared chokepoint.
    assert events == ["enter", "call", "exit", "chokepoint"], events
