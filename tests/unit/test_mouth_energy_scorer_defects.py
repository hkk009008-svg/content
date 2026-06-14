"""f1addd3 mouth-energy scorer (Provider 1.5) — director2 verify findings (wf_46f1d3ec-145).

director2's Pair-B authoritative verify of f1addd3 found material defects the
coordinator's single-subagent diff-review missed. This file began as the
R-VERIFY-TIER(B) pin for the one cleanly-testable defect (D1) while lip_sync.py
was locked by a peer's live §4 WIP, and documents the test-infeasible ones.

  D1 OBSERVABILITY (major) — **FIXED** (operator2, this session; renamed off the
     `_xfail` pin once green). _score_mouth_energy's outer ``except Exception:
     return None`` swallowed a cv2 ImportError with no log at any level, so in the
     common opencv-absent container the scorer silently returned None ->
     validate_lipsync_quality fell through to the Provider-2 duration heuristic (or
     neutral 1.0), exactly re-creating the "everything passes -> random best-of"
     bug f1addd3 claims to fix — invisibly. Fix splits the catch-all into an
     ``except ImportError`` (dependency absent -> WARNING) and ``except Exception``
     (unexpected failure -> WARNING), both preserving the fail-open None; the
     companion occlusion fail-open was bumped INFO -> WARNING. The three tests
     below now run LIVE (no xfail) and assert: fail-open None preserved AND the
     degradation is observable at a production WARNING floor, on all three paths.

STILL-OPEN DEFECTS (documented; out of scope for the D1 observability fix):
  D2 DETECTOR CHOICE (major, test-infeasible here — needs real cv2 + a
     neutral-speech clip): the scorer uses haarcascade_smile.xml (the SMILE
     cascade), which underdetects a neutral speaking mouth -> the >50% occlusion
     branch fail-opens on well-synced neutral-speech takes (now a LOUD WARNING
     after the D1 fix, but the detector choice itself is unfixed).
  D4 TEST GAP (major, test-infeasible here — needs real cv2 + crafted clips):
     the cv2-mocked tests never exercise the real Haar/astats path, and there is
     NO anti-synced discriminator test proving a desynced clip scores LOW.

UNPROVEN HYPOTHESIS (needs a calibration experiment, NOT a unit test):
  D3 SCALE (major-if-true): passing the auto_approve final_min_lipsync=0.8 bar
     requires raw Pearson >= 0.6; real mouth-brightness vs audio-RMS correlation
     may sit well below that, so well-synced generation takes could be
     systematically REJECTED (the opposite pathology to the old neutral-1.0). This
     needs an empirical run of _score_mouth_energy on real synced vs desynced clips
     before it can back any NO-GO (R-MEASURE). Pod / real-clip gated.
"""
import sys

import pytest

import lip_sync


def test_mouth_energy_scorer_warns_when_cv2_absent(monkeypatch, caplog):
    """cv2 absent must emit a WARNING so an operator knows the sync gate is degraded.

    The fail-open *return value* (None) is correct and preserved — the defect is the
    SILENCE around it. This asserts both: fail-open holds AND it is observable.
    """
    # sys.modules[name] = None makes the lazy ``import cv2`` inside the scorer raise
    # ImportError — the exact production "opencv absent" condition.
    monkeypatch.setitem(sys.modules, "cv2", None)

    with caplog.at_level("WARNING"):
        result = lip_sync._score_mouth_energy("/nonexistent/video.mp4", "/nonexistent/audio.wav")

    assert result is None, "fail-open contract: cv2-absent must return None, never block"
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, (
        "expected a WARNING when cv2 is absent so the degraded sync gate is observable "
        "(silent-degradation defect D1) — none was logged"
    )


def test_mouth_energy_scorer_warns_on_unexpected_failure(monkeypatch, caplog):
    """An unexpected (non-ImportError) failure must also fail open LOUDLY, not silently.

    cv2 imports fine, but a downstream call blows up (here: VideoCapture raises). The
    old outer ``except Exception: return None`` swallowed this with no log too — an
    invisible scorer crash is the same silent-gate-degradation bug class as D1. The
    fix must emit a WARNING while preserving the fail-open None.
    """
    cv2 = pytest.importorskip("cv2")  # generic-path test needs a real cv2 to get past import
    monkeypatch.setattr(
        cv2, "VideoCapture", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    with caplog.at_level("WARNING"):
        result = lip_sync._score_mouth_energy("/nonexistent/video.mp4", "/nonexistent/audio.wav")

    assert result is None, "fail-open contract: unexpected failure must return None, never block"
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, (
        "expected a WARNING when the scorer hits an unexpected failure so the degraded "
        "sync gate is observable — none was logged (silent swallow)"
    )


def test_mouth_energy_scorer_warns_on_high_occlusion(monkeypatch, caplog):
    """A clip whose mouth can't be detected in >50% of frames fails open — but LOUDLY.

    Provider-1.5 only runs on dialogue/generation shots, where a mostly-undetectable
    mouth means the lip-sync overlay is probably bad. The fail-open None is correct;
    the silent INFO-level log was the companion defect (invisible at a production
    WARNING floor), the same observability bug class as D1.
    """
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    class _FakeCap:
        def isOpened(self):
            return True

        def get(self, prop):
            return 24.0 if prop == cv2.CAP_PROP_FRAME_COUNT else 0.0

        def set(self, *a, **k):
            return True

        def read(self):
            return True, np.zeros((240, 320, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: _FakeCap())

    class _NoDetect:  # finds NO mouth in any frame -> 100% occlusion
        def detectMultiScale(self, *a, **k):
            return np.empty((0, 4))

    monkeypatch.setattr(cv2, "CascadeClassifier", lambda *a, **k: _NoDetect())
    monkeypatch.setattr(cv2, "cvtColor", lambda frame, code: frame[:, :, 0])

    with caplog.at_level("WARNING"):
        result = lip_sync._score_mouth_energy("/nonexistent/video.mp4", "/nonexistent/audio.wav")

    assert result is None, "fail-open contract: high occlusion must return None"
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, (
        "expected a WARNING when >50% of frames are occluded so the fail-open is "
        "observable at a production log threshold — none was logged"
    )
