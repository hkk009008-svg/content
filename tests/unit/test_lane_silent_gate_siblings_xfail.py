"""R-VERIFY-TIER(B) pins — silent-gate-degradation siblings found by the operator2
completeness sweep (wf_5bb228ae-0f8, 7 area-sweepers + per-finding adversarial verify).

BUG CLASS (same as f1addd3 D1): a quality/safety/delivery GATE that SILENTLY degrades
to a no-op (or a permissive/neutral fallback) when a dependency is absent, an exception
is swallowed, or an input can't be read — with NO log at a production WARNING floor. Fail-
open is often correct policy; the defect is fail-SILENT — an operator can't tell the gate
stopped gating.

These were CONFIRMED by the sweep's refute-first verifier (finalVerdict=CONFIRMED,
production-reachable). lip_sync.py:668 (gate neutral-1.0) and the inner ffprobe except —
two other CONFIRMED siblings — were FIXED this session (e8694e3); these four are left for
director2's cross-lane hardening epic and pinned here so CI, not the next session, re-
verifies. When a site is fixed, its xfail xpasses (strict) -> delete that pin.

CATALOG / lane ownership:
  - cinema/shots/controller.py:241 `_inherit_audio_flags_from_base` (MAJOR, Pair-B/mine):
    fixed 2026-06-15 by emitting a WARNING when phase_c_ffmpeg._has_audio_stream
    raises before conservatively skipping audio-flag inheritance; live regression below.
  - coherence_analyzer.py:202 `_invalid_coherence` (minor, shared; caller is Pair-B):
    fixed 2026-06-15 by emitting a WARNING when an unreadable image produces
    `valid=False`; the caller-side `.valid` ignore is tracked separately as
    `coherence-caller-valid-ignored`.
  - phase_c_vision.py:351 `validate_identity_vision` (Pair-A identity lane):
    fixed 2026-06-15 by promoting the old observability-only xfail below into a live
    fail-closed regression; API/JSON errors now return an explicit non-pass marker.
  - cinema_pipeline.py:1599 `_assemble_final` (minor, Pair-B/mine) — TEST-INFEASIBLE here
    (large assembly method, needs a full stitched/dialogue/foley/bgm fixture). When BGM
    generation fails, the `else` branch drops the prepared dialogue+foley tracks and copies
    `stitched` as-is; for non-embedding engines (Kling/LTX) the final cut is MUTE, but it
    logs only INFO "...no BGM" (misleading — can be "no audio at all"). Documented for the
    epic; no pin (infeasible).
"""
import types

import pytest


def test_inherit_audio_flags_warns_when_has_audio_stream_raises(monkeypatch, caplog):
    import phase_c_ffmpeg
    from cinema.shots import controller

    def _raise(*a, **k):
        raise RuntimeError("phase_c_ffmpeg._has_audio_stream unavailable")

    monkeypatch.setattr(phase_c_ffmpeg, "_has_audio_stream", _raise, raising=False)

    base_take = {"metadata": {"audio_embedded": True, "dialogue_audio_in_clip": True}}
    variant = {"path": "/some/variant.mp4", "metadata": {}}

    with caplog.at_level("WARNING"):
        controller._inherit_audio_flags_from_base(base_take, variant)

    # Current behaviour: flags are silently NOT inherited (the bug consequence).
    assert "audio_embedded" not in variant["metadata"]
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, (
        "a swallowed _has_audio_stream failure that drops audio flags (-> voice-loss) "
        "must be observable (WARNING) — none was logged"
    )


def test_assess_coherence_warns_when_image_unreadable(caplog):
    pytest.importorskip("cv2")  # assess_coherence uses cv2.imread; module needs cv2 to load
    import coherence_analyzer

    with caplog.at_level("WARNING"):
        result = coherence_analyzer.assess_coherence(
            "/nonexistent/current.png", "/nonexistent/previous.png"
        )

    assert result.valid is False, "unreadable inputs must mark the result invalid"
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, (
        "an unreadable image that silently zeroes color_drift (suppressing the color_grade "
        "gate) must be observable (WARNING) — none was logged"
    )


def test_validate_identity_vision_fails_closed_on_api_failure(monkeypatch, tmp_path, caplog):
    import phase_c_vision

    ref = tmp_path / "ref.jpg"
    gen = tmp_path / "gen.jpg"
    ref.write_bytes(b"x")
    gen.write_bytes(b"x")

    # Only `settings.anthropic_api_key` is read on this path; a SimpleNamespace avoids the
    # frozen-dataclass setattr restriction.
    monkeypatch.setattr(phase_c_vision, "settings", types.SimpleNamespace(anthropic_api_key="k"))
    monkeypatch.setattr(phase_c_vision, "encode_image_for_llm", lambda p: "b64", raising=False)
    monkeypatch.setattr(phase_c_vision, "_IDENTITY_API_RETRY_BACKOFF_SECONDS", 0)

    import anthropic

    class _Msgs:
        def create(self, **k):
            raise RuntimeError("anthropic API down")

    class _FakeAnthropic:
        def __init__(self, **k):
            self.messages = _Msgs()

    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropic)

    with caplog.at_level("WARNING"):
        result = phase_c_vision.validate_identity_vision(str(ref), str(gen))

    assert result.get("error") is True
    assert result.get("error_reason") == "provider_error"
    assert result.get("confidence") == 0.0
    assert result.get("match") is False
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, (
        "the identity gate failing closed on an API error must be observable in the "
        "log stream (WARNING), not just a stdout print - none was logged"
    )
