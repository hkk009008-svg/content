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
import types

import pytest

import lip_sync


def _install_fake_cv2(monkeypatch, *, video_capture=None, detects=True):
    """Inject a minimal fake ``cv2`` so these tests exercise the scorer in a cv2-ABSENT
    environment — the exact CI posture defect D1 targets (director2 test-gap, 05:29Z;
    the old ``importorskip('cv2')`` SKIPPED in precisely that env).

    detects=False makes the cascade find no mouth (drives the >50% occlusion branch);
    video_capture overrides cv2.VideoCapture (e.g. to raise).
    """
    import numpy as np

    fake = types.ModuleType("cv2")
    fake.CAP_PROP_FRAME_COUNT = 7
    fake.CAP_PROP_POS_FRAMES = 1
    fake.COLOR_BGR2GRAY = 6
    fake.data = types.SimpleNamespace(haarcascades="/fake/haarcascades/")

    class _Cap:
        def isOpened(self):
            return True

        def get(self, prop):
            return 24.0 if prop == fake.CAP_PROP_FRAME_COUNT else 0.0

        def set(self, *a, **k):
            return True

        def read(self):
            return True, np.zeros((240, 320, 3), dtype=np.uint8)

        def release(self):
            pass

    fake.VideoCapture = video_capture or (lambda *a, **k: _Cap())

    class _Clf:
        def detectMultiScale(self, *a, **k):
            return np.array([[10, 150, 80, 30]]) if detects else np.empty((0, 4))

    fake.CascadeClassifier = lambda *a, **k: _Clf()
    fake.cvtColor = lambda frame, code: frame[:, :, 0]
    monkeypatch.setitem(sys.modules, "cv2", fake)
    return fake


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

    cv2 imports fine (fake module), but VideoCapture blows up. The old outer
    ``except Exception: return None`` swallowed this with no log — an invisible scorer
    crash is the same silent-gate-degradation class as D1. Runs cv2-FREE so it executes
    in the cv2-absent CI env D1 targets (was importorskip -> skipped there).
    """
    _install_fake_cv2(
        monkeypatch,
        video_capture=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with caplog.at_level("WARNING"):
        result = lip_sync._score_mouth_energy("/nonexistent/video.mp4", "/nonexistent/audio.wav")

    assert result is None, "fail-open contract: unexpected failure must return None, never block"
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, "unexpected failure must be observable (WARNING) — none was logged"
    assert any("unexpected failure" in r.getMessage().lower() for r in warnings)


def test_mouth_energy_scorer_logs_occlusion_at_info_not_warning(monkeypatch, caplog):
    """High occlusion is a PER-CLIP unscorable input, not a structural degradation.

    The scorer ran correctly and concluded it can't score THIS clip (e.g. a wide /
    profile framing where the Haar cascade finds no mouth). Observable at INFO (with
    mouth_detect_rate) but NOT a WARNING — WARNING is reserved for true scorer
    degradation (cv2 absent / crash / ffprobe absent) so the loud signal stays
    meaningful instead of spamming on legitimate cinematography.
    """
    _install_fake_cv2(monkeypatch, detects=False)  # cascade finds no mouth -> 100% occlusion

    with caplog.at_level("INFO"):
        result = lip_sync._score_mouth_energy("/nonexistent/video.mp4", "/nonexistent/audio.wav")

    assert result is None, "fail-open contract: high occlusion must return None"
    info_logs = [r for r in caplog.records if hasattr(r, "mouth_detect_rate")]
    assert info_logs, "occlusion fail-open must remain observable (an INFO log w/ mouth_detect_rate)"
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert not warnings, (
        "occlusion is a per-clip unscorable input, NOT structural degradation — it must "
        f"NOT emit a WARNING (would spam on legitimate framing). Got: {[r.getMessage() for r in warnings]}"
    )


def test_mouth_energy_scorer_partial_install_routes_to_unexpected_not_unavailable(monkeypatch, caplog):
    """A partial OpenCV install (import cv2 OK, a C-extension load fails later with
    ImportError) must NOT be mislabelled 'dependency unavailable'.

    The `except ImportError` guards ONLY the lazy import statements, so a downstream
    ImportError falls through to the generic 'unexpected failure' handler.
    """
    _install_fake_cv2(
        monkeypatch,
        video_capture=lambda *a, **k: (_ for _ in ()).throw(
            ImportError("libGL.so.1: cannot open shared object file")
        ),
    )

    with caplog.at_level("WARNING"):
        result = lip_sync._score_mouth_energy("/nonexistent/video.mp4", "/nonexistent/audio.wav")

    assert result is None, "fail-open contract preserved on a partial-install ImportError"
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, "a downstream ImportError must still be observable (WARNING)"
    msgs = " ".join(r.getMessage().lower() for r in warnings)
    assert "unexpected failure" in msgs, (
        "a downstream ImportError (import cv2 already succeeded) must route to the generic "
        f"'unexpected failure' handler, not the 'dependency unavailable' message. Got: {msgs!r}"
    )


def test_mouth_energy_scorer_warns_when_ffprobe_absent(monkeypatch, caplog):
    """ffprobe absent (FileNotFoundError) is a STRUCTURAL degradation on the audio-energy
    side — the mirror of cv2-absent — and must WARN, not silently return None.

    Sweep finding + director2 convergence (the inner ffprobe except). Runs cv2-FREE: the
    fake cv2 yields frames with a detected mouth so the scorer reaches the ffprobe astats
    block, where ffprobe is then made 'absent'.
    """
    import subprocess

    _install_fake_cv2(monkeypatch, detects=True)  # mouths detected -> past occlusion -> ffprobe block

    def _no_ffprobe(*a, **k):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(subprocess, "run", _no_ffprobe)

    with caplog.at_level("WARNING"):
        result = lip_sync._score_mouth_energy("/nonexistent/video.mp4", "/nonexistent/audio.wav")

    assert result is None, "fail-open contract: ffprobe-absent must return None, never block"
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, "ffprobe-absent (structural) must WARN — none was logged (silent swallow)"
    assert any("ffprobe" in r.getMessage().lower() for r in warnings)
