"""
Tests for the Provider-1.5 mouth-energy scorer added to validate_lipsync_quality.

RED first: all 4 tests must FAIL before implementation.
"""
import logging
import types
import numpy as np
import pytest


# ─────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────

def _make_fake_capture(n_frames=24, width=320, height=240):
    """Return a fake cv2.VideoCapture-like object that yields n_frames."""
    class FakeCap:
        def __init__(self):
            self._idx = 0
            self._total = n_frames
            self._width = width
            self._height = height

        def isOpened(self):
            return True

        def get(self, prop_id):
            import cv2
            if prop_id == cv2.CAP_PROP_FRAME_COUNT:
                return float(self._total)
            if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
                return float(self._width)
            if prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
                return float(self._height)
            return 0.0

        def set(self, prop_id, value):
            import cv2
            if prop_id == cv2.CAP_PROP_POS_FRAMES:
                self._idx = int(value)
            return True

        def read(self):
            if self._idx >= self._total:
                return False, None
            # Lower-third brightness varies with frame index so correlation exists
            frame = np.zeros((self._height, self._width, 3), dtype=np.uint8)
            # Vary the bottom third brightness
            brightness = int(50 + (self._idx / self._total) * 150)
            frame[self._height // 2 :, :] = brightness
            self._idx += 1
            return True, frame

        def release(self):
            pass

    return FakeCap()


def _make_fake_ffprobe_run(energies, n_frames=24):
    """Return a subprocess.run stub that returns astats energy data."""
    import subprocess, json

    original_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)
        if "astats" in cmd_str:
            frames_data = [
                {"tags": {"lavfi.astats.Overall.RMS_level": str(energies[i % n_frames])}}
                for i in range(n_frames)
            ]
            return types.SimpleNamespace(
                stdout=json.dumps({"frames": frames_data}),
                stderr="",
                returncode=0,
            )
        if "show_entries" in cmd_str and "duration" in cmd_str:
            return types.SimpleNamespace(
                stdout=json.dumps({"format": {"duration": "2.0"}}),
                stderr="",
                returncode=0,
            )
        return original_run(cmd, *args, **kwargs)

    return fake_run


# ─────────────────────────────────────────────────────────────
# test (a) — real float returned when everything works
# ─────────────────────────────────────────────────────────────

def test_mouth_energy_scorer_returns_real_float_in_range(monkeypatch, tmp_path):
    """Provider-1.5 should compute a real score, not the neutral 1.0."""
    import lip_sync, subprocess

    # Create dummy files so os.path.exists passes
    video_file = tmp_path / "fake.mp4"
    audio_file = tmp_path / "fake.wav"
    video_file.write_bytes(b"fake")
    audio_file.write_bytes(b"fake")

    fake_cap = _make_fake_capture(n_frames=24)

    import cv2
    monkeypatch.setattr(cv2, "VideoCapture", lambda path: fake_cap)

    class FakeClassifier:
        def detectMultiScale(self, gray, **kwargs):
            # Return a single [x, y, w, h] box in the lower third
            return np.array([[10, 150, 80, 30]])

    monkeypatch.setattr(cv2, "CascadeClassifier", lambda path: FakeClassifier())

    def _fake_cvt(frame, code):
        return frame[:, :, 0]
    monkeypatch.setattr(cv2, "cvtColor", _fake_cvt)

    n_frames = 24
    energies = [float(30 + i * 5) for i in range(n_frames)]
    monkeypatch.setattr(subprocess, "run", _make_fake_ffprobe_run(energies, n_frames))

    result = lip_sync.validate_lipsync_quality(
        str(video_file),
        str(audio_file),
        _generation=True,
    )

    assert isinstance(result, float), f"expected float, got {type(result)}"
    assert 0.0 <= result <= 1.0, f"score out of range: {result}"
    assert result != 1.0, (
        "Provider-1.5 should return a real score, not the neutral 1.0 fallback. "
        f"Got {result}. This means the scorer was skipped or failed silently."
    )
    # Also confirm it's not 0.0 (which would indicate early-exit, not a real score)
    assert result > 0.0, (
        f"Provider-1.5 returned 0.0 — the scorer probably short-circuited (os.path.exists?). Got {result}"
    )


# ─────────────────────────────────────────────────────────────
# test (b) — occlusion → fail-open (return 1.0)
# ─────────────────────────────────────────────────────────────

def test_mouth_energy_scorer_occlusion_fails_open(monkeypatch, tmp_path):
    """When >50% of frames have no detected mouth, scorer returns 1.0 (fail-open)."""
    import lip_sync, subprocess

    # Create dummy files so os.path.exists passes
    video_file = tmp_path / "fake.mp4"
    audio_file = tmp_path / "fake.wav"
    video_file.write_bytes(b"fake")
    audio_file.write_bytes(b"fake")

    import cv2

    fake_cap = _make_fake_capture(n_frames=24)
    monkeypatch.setattr(cv2, "VideoCapture", lambda path: fake_cap)

    class EmptyClassifier:
        def detectMultiScale(self, gray, **kwargs):
            return np.array([])  # no mouth detected

    monkeypatch.setattr(cv2, "CascadeClassifier", lambda path: EmptyClassifier())

    def _fake_cvt(frame, code):
        return frame[:, :, 0]
    monkeypatch.setattr(cv2, "cvtColor", _fake_cvt)

    # Stub ffprobe duration to avoid real subprocess calls in Provider 2
    import subprocess as sp, json
    original_run = sp.run

    def fake_run_dur(cmd, *args, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)
        if "show_entries" in cmd_str and "duration" in cmd_str:
            return types.SimpleNamespace(
                stdout=json.dumps({"format": {"duration": "2.0"}}),
                stderr="",
                returncode=0,
            )
        return original_run(cmd, *args, **kwargs)

    monkeypatch.setattr(sp, "run", fake_run_dur)

    result = lip_sync.validate_lipsync_quality(
        str(video_file),
        str(audio_file),
        _generation=True,
    )

    # When mouth scoring fails open (occlusion), _score_mouth_energy returns None.
    # Provider 2 (duration heuristic) then runs; both files are 2.0s → ratio=0 → score=1.0
    assert result == 1.0, (
        f"Occlusion-fail-open should return 1.0 (via Provider 2 duration heuristic), got {result}"
    )


# ─────────────────────────────────────────────────────────────
# test (c) — overlay path does NOT invoke cv2
# ─────────────────────────────────────────────────────────────

def test_scorer_not_run_on_overlay_path(monkeypatch, tmp_path):
    """Provider-1.5 must be skipped when _generation=False (overlay path)."""
    import lip_sync
    import cv2, subprocess as sp, json

    # Create dummy files
    video_file = tmp_path / "fake.mp4"
    audio_file = tmp_path / "fake.wav"
    video_file.write_bytes(b"fake")
    audio_file.write_bytes(b"fake")

    def _raise_if_called(path):
        raise AssertionError("cv2.VideoCapture must NOT be called on the overlay path")

    monkeypatch.setattr(cv2, "VideoCapture", _raise_if_called)

    original_run = sp.run

    def fake_run(cmd, *args, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)
        if "show_entries" in cmd_str and "duration" in cmd_str:
            return types.SimpleNamespace(
                stdout=json.dumps({"format": {"duration": "2.0"}}),
                stderr="",
                returncode=0,
            )
        return original_run(cmd, *args, **kwargs)

    monkeypatch.setattr(sp, "run", fake_run)

    # Should NOT raise AssertionError from cv2.VideoCapture
    result = lip_sync.validate_lipsync_quality(
        str(video_file),
        str(audio_file),
        # _generation defaults to False — overlay path
    )

    assert isinstance(result, float), f"expected float, got {type(result)}"


# ─────────────────────────────────────────────────────────────
# test (d) — INFO log carries mouth_detect_rate
# ─────────────────────────────────────────────────────────────

def test_logs_frame_detection_rate(monkeypatch, tmp_path, caplog):
    """validate_lipsync_quality(_generation=True) must log mouth_detect_rate."""
    import lip_sync, subprocess

    # Create dummy files
    video_file = tmp_path / "fake.mp4"
    audio_file = tmp_path / "fake.wav"
    video_file.write_bytes(b"fake")
    audio_file.write_bytes(b"fake")

    import cv2

    fake_cap = _make_fake_capture(n_frames=24)
    monkeypatch.setattr(cv2, "VideoCapture", lambda path: fake_cap)

    class FakeClassifier:
        def detectMultiScale(self, gray, **kwargs):
            return np.array([[10, 150, 80, 30]])

    monkeypatch.setattr(cv2, "CascadeClassifier", lambda path: FakeClassifier())

    def _fake_cvt(frame, code):
        return frame[:, :, 0]
    monkeypatch.setattr(cv2, "cvtColor", _fake_cvt)

    n_frames = 24
    energies = [float(30 + i * 5) for i in range(n_frames)]
    monkeypatch.setattr(subprocess, "run", _make_fake_ffprobe_run(energies, n_frames))

    # Use propagate=True and capture at root to handle log propagation
    with caplog.at_level(logging.INFO):
        lip_sync.validate_lipsync_quality(
            str(video_file),
            str(audio_file),
            _generation=True,
        )

    # Find a log record that has mouth_detect_rate as an extra attribute
    matching = [
        r for r in caplog.records
        if hasattr(r, "mouth_detect_rate")
    ]
    assert matching, (
        "Expected an INFO log record with 'mouth_detect_rate' extra key. "
        f"Records found: {[(r.name, r.getMessage(), vars(r)) for r in caplog.records]}"
    )


# ─────────────────────────────────────────────────────────────
# GATE-LEVEL observability — the neutral-1.0 fall-through (sweep finding lip_sync.py:668)
# validate_lipsync_quality returns 1.0 = "perfect OR unmeasurable". When it is the
# latter (no scorer could measure), the gate PASSES every shot without validating.
# That degradation must be observable (WARNING), same bug class as scorer D1.
# ─────────────────────────────────────────────────────────────

def test_gate_warns_when_no_scorer_available(monkeypatch, tmp_path, caplog):
    """Every provider unavailable -> neutral 1.0 (gate no-op) MUST emit a WARNING."""
    import lip_sync, subprocess

    video_file = tmp_path / "fake.mp4"
    audio_file = tmp_path / "fake.wav"
    video_file.write_bytes(b"fake")
    audio_file.write_bytes(b"fake")

    # Provider 1 (syncnet) is not installed in the test env -> skipped naturally.
    # _generation defaults False -> Provider 1.5 skipped.
    # Provider 2 (ffprobe duration heuristic): make the ffprobe binary "absent".
    def _no_ffprobe(*a, **k):
        raise FileNotFoundError("ffprobe")
    monkeypatch.setattr(subprocess, "run", _no_ffprobe)

    with caplog.at_level("WARNING"):
        result = lip_sync.validate_lipsync_quality(str(video_file), str(audio_file))

    assert result == 1.0, "neutral fallback preserved when no scorer is available"
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, (
        "the sync gate returning neutral 1.0 (passing without validating) must WARN so an "
        "operator knows sync is UNVALIDATED — none was logged"
    )


def test_gate_warns_when_video_unprobeable(monkeypatch, tmp_path, caplog):
    """ffprobe reports 0 duration (corrupt/empty video) -> neutral 1.0 MUST WARN."""
    import lip_sync, subprocess, json, types

    video_file = tmp_path / "fake.mp4"
    audio_file = tmp_path / "fake.wav"
    video_file.write_bytes(b"fake")
    audio_file.write_bytes(b"fake")

    def _zero_dur(cmd, *a, **k):
        return types.SimpleNamespace(
            stdout=json.dumps({"format": {"duration": "0.0"}}), stderr="", returncode=0
        )
    monkeypatch.setattr(subprocess, "run", _zero_dur)

    with caplog.at_level("WARNING"):
        result = lip_sync.validate_lipsync_quality(str(video_file), str(audio_file))

    assert result == 1.0, "neutral fallback preserved when the video can't be probed"
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, (
        "an unprobeable video falling through to neutral 1.0 (gate passed without "
        "validating) must WARN — none was logged"
    )
