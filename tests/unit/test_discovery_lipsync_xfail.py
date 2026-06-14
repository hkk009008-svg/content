"""Strict-xfail CI pins for 2 defects confirmed by the Phase-0 discovery bug-hunt
(logs/discovery-wf_13f9d2f6-f93.json, confirmed[2] and confirmed[9]).

BUG CLASS: silent/fabricated quality scores that mislead the pipeline operator.

CATALOG:
  - lip_sync.py:659  validate_lipsync_quality  (W2:MAJOR:lipsync-syncnet-nan)
    SyncNet returns NaN confidence -> max(0.0, min(1.0, nan/10.0)) = 1.0 because
    Python's min(1.0, nan) evaluates to 1.0 (NaN comparison semantics). A fabricated
    perfect lipsync score bypasses the gate silently.

  - lip_sync.py:1069-1082  _restore_audio_track  (W2:MAJOR:audio-remux-notimeout)
    subprocess.run(['ffmpeg', ...], check=True, capture_output=True) has NO timeout=
    argument, unlike every other peer subprocess.run call in the file. A hanging
    ffmpeg process blocks the pipeline thread indefinitely.

When a site is fixed its xfail xpasses (strict=True) -> delete that pin.
"""
import math
import subprocess
import types

import pytest


# ---------------------------------------------------------------------------
# confirmed[2] — lipsync-syncnet-nan  (lip_sync.py:659)
# ---------------------------------------------------------------------------

def test_syncnet_nan_confidence_does_not_produce_passing_score(monkeypatch, tmp_path):
    """Regression (was strict-xfail pin, lipsync-syncnet-nan): a NaN SyncNet
    confidence must map to 0.0, not the fabricated 1.0 that min(1.0, nan) produced.
    FIXED at lip_sync.py:659 — finite-guard conf via _finite_or before the clamp + WARN."""
    import lip_sync

    # Create a minimal video-like file so the early path-exists guard passes.
    fake_video = tmp_path / "test.mp4"
    fake_video.write_bytes(b"\x00" * 8)

    # Inject a SyncNetInstance whose evaluate() returns NaN confidence.
    _NAN = float("nan")

    class _FakeSyncNetInstance:
        def evaluate(self, opts, video_path):
            # Returns (offset, confidence, dists) as syncnet_python does.
            return (0, _NAN, [])

    fake_module = types.ModuleType("SyncNetInstance")
    fake_module.SyncNetInstance = _FakeSyncNetInstance

    # Patch the importlib machinery so the `from SyncNetInstance import ...` inside
    # validate_lipsync_quality resolves to our fake.
    import sys
    monkeypatch.setitem(sys.modules, "SyncNetInstance", fake_module)

    # torch is also imported in the same try-block — stub it out if absent.
    if "torch" not in sys.modules:
        monkeypatch.setitem(sys.modules, "torch", types.ModuleType("torch"))

    score = lip_sync.validate_lipsync_quality(str(fake_video))

    # Current (broken) behaviour: score == 1.0, a fabricated perfect grade.
    # Fixed behaviour: score must be 0.0 (NaN treated as zero confidence) or at
    # minimum NOT equal to 1.0 and must be a finite number.
    assert math.isfinite(score), (
        "validate_lipsync_quality must return a finite score even when SyncNet "
        f"returns NaN confidence; got {score!r}"
    )
    assert score == 0.0, (
        "a NaN SyncNet confidence must map to 0.0 (no signal), not a fabricated "
        f"passing score; got {score!r}"
    )


# ---------------------------------------------------------------------------
# confirmed[9] — audio-remux-notimeout  (lip_sync.py:1069-1082)
# ---------------------------------------------------------------------------

def test_restore_audio_track_subprocess_run_has_timeout(monkeypatch):
    """Regression (was strict-xfail pin, audio-remux-notimeout): _restore_audio_track's
    ffmpeg subprocess.run must pass timeout= so a stalled remux can't hang the pipeline.
    FIXED at lip_sync.py:1083 — timeout=30 + TimeoutExpired added to the except."""
    import lip_sync

    captured_kwargs: list = []

    def _fake_run(cmd, **kwargs):
        captured_kwargs.append(kwargs)
        # Return a completed-process-like object so the function proceeds normally.
        result = subprocess.CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")
        return result

    monkeypatch.setattr(lip_sync.subprocess, "run", _fake_run)

    # os.path.exists is called on output_path after the run; patch it to avoid
    # needing real files on disk.
    monkeypatch.setattr(lip_sync.os.path, "exists", lambda p: p == "/out/output.mp4")

    lip_sync._restore_audio_track(
        video_path="/fake/video.mp4",
        audio_source_path="/fake/audio.mp4",
        output_path="/out/output.mp4",
        engine="rife",
    )

    assert captured_kwargs, "_restore_audio_track must invoke subprocess.run"
    call_kwargs = captured_kwargs[0]

    # Fixed behaviour: a timeout= kwarg must be present (any positive value).
    assert "timeout" in call_kwargs, (
        "_restore_audio_track subprocess.run must pass timeout= to prevent indefinite "
        "pipeline hangs on a stalled ffmpeg process; no timeout kwarg was found in "
        f"the captured call: {call_kwargs!r}"
    )
