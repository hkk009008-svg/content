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


def test_compute_face_embedding_routes_represent_through_guard(monkeypatch):
    """character_manager.compute_face_embedding (persists embedding.npy) must run
    DeepFace.represent strictly inside the single-thread guard."""
    import identity.validator as v
    import domain.character_manager as cm
    events = []
    monkeypatch.setattr(cm, "DEEPFACE_AVAILABLE", True)
    monkeypatch.setattr(v, "cv2_single_thread", _spy_guard(events))

    def fake_represent(*a, **k):
        events.append("call")
        return [{"embedding": [0.1] * 512}]
    monkeypatch.setattr(cm.DeepFace, "represent", fake_represent)

    out = cm.compute_face_embedding("x.jpg")
    assert events == ["enter", "call", "exit"], events
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
