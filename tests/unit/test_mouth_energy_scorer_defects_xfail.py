"""f1addd3 mouth-energy scorer (Provider 1.5) — director2 verify findings (wf_46f1d3ec-145).

director2's Pair-B authoritative verify of f1addd3 found material defects the
coordinator's single-subagent diff-review missed. lip_sync.py is locked by a
peer's live §4 WIP this session, so the production fix is deferred; this file
ships the R-VERIFY-TIER(B) pin for the one cleanly-testable defect so CI — not
the next session's agents — re-verifies, and labels the test-infeasible ones.

CONFIRMED DEFECTS (code-read, high confidence):
  D1 OBSERVABILITY (major, PINNED below): _score_mouth_energy's outer
     ``except Exception: return None`` (lip_sync.py:568-570) silently swallows a
     cv2 ImportError with no log at any level. In the common container where
     opencv is absent, the scorer silently returns None -> validate_lipsync_quality
     falls through to the Provider-2 duration heuristic (or neutral 1.0), exactly
     re-creating the "everything passes -> random best-of" bug f1addd3 claims to
     fix — invisibly. (Companion nit: the one logged fail-open, occlusion, is INFO
     not WARNING, so it too is invisible at a production WARNING log threshold.)
  D2 DETECTOR CHOICE (major, test-infeasible this turn — needs real cv2 + a
     neutral-speech clip): the scorer uses haarcascade_smile.xml (lip_sync.py:457),
     the SMILE cascade, which underdetects a neutral speaking mouth -> the >50%
     occlusion branch fail-opens on well-synced neutral-speech takes.
  D4 TEST GAP (major, test-infeasible this turn — needs real cv2 + crafted clips):
     the 4 existing tests (test_validate_lipsync_scorer.py) mock cv2 entirely, so
     the real Haar/astats path is never exercised, and there is NO anti-synced
     discriminator test proving a desynced clip scores LOW.

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


@pytest.mark.xfail(
    strict=True,
    reason="f1addd3 D1 (major): _score_mouth_energy's outer except (lip_sync.py:568-570) "
    "swallows a cv2 ImportError with no log, so the lip-sync gate degrades SILENTLY in the "
    "common opencv-absent container (re-creating the random-best-of bug f1addd3 claims to "
    "fix). Fix = emit a logger.warning on the cv2-absent / total-fail-open path; the test "
    "then xpasses (strict) and this pin must be removed.",
)
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
