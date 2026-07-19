"""Unit tests for dialogue pace control (dialogue_target_wpm -> atempo).

Covers the load-bearing arithmetic (`_pace_factor`), the atempo-chain builder,
and the `_apply_target_pace` no-op/guard path — all without invoking ffmpeg.
"""
import pytest

from audio.dialogue import _apply_target_pace, _atempo_chain, _pace_factor


class TestPaceFactor:
    def test_slows_a_fast_line(self):
        # 15 words in 4.56s == ~197 wpm; target 145 -> factor ~0.735 (slow down)
        f = _pace_factor(15, 4.56, 145)
        assert f is not None
        assert 0.72 < f < 0.75

    def test_deadband_skips_near_target(self):
        # 15 words in ~6.2s ~= 145 wpm -> within +/-3% deadband -> skip
        assert _pace_factor(15, 6.2, 145) is None

    def test_disabled_when_target_zero(self):
        assert _pace_factor(15, 4.56, 0) is None
        assert _pace_factor(15, 4.56, -1) is None

    def test_guards_unmeasurable_inputs(self):
        assert _pace_factor(0, 4.56, 145) is None      # no words
        assert _pace_factor(15, 0.0, 145) is None       # no duration

    def test_clamps_extreme_slowdown(self):
        # 15 words in 2.0s == 450 wpm; target 145 -> 0.322, clamped to lo=0.6
        assert _pace_factor(15, 2.0, 145) == pytest.approx(0.6)

    def test_clamps_extreme_speedup(self):
        # 15 words in 20s == 45 wpm; target 145 -> 3.22, clamped to hi=1.6
        assert _pace_factor(15, 20.0, 145) == pytest.approx(1.6)

    def test_factor_direction_is_target_over_actual(self):
        # A slower target than the natural rate must yield factor < 1.
        fast = _pace_factor(20, 4.0, 120)   # actual 300 wpm -> want much slower
        assert fast is not None and fast < 1.0
        # A faster target than the natural rate must yield factor > 1.
        slow = _pace_factor(10, 10.0, 100)  # actual 60 wpm -> want faster
        assert slow is not None and slow > 1.0


class TestAtempoChain:
    def test_single_pass_for_in_range_factor(self):
        assert _atempo_chain(0.75) == "atempo=0.7500"

    def test_chains_below_half(self):
        # 0.3 < 0.5 -> one 0.5 pass then 0.6 remainder
        assert _atempo_chain(0.3) == "atempo=0.5,atempo=0.6000"

    def test_chains_above_two(self):
        # 3.0 > 2.0 -> one 2.0 pass then 1.5 remainder
        assert _atempo_chain(3.0) == "atempo=2.0,atempo=1.5000"


class TestApplyTargetPaceNoOp:
    def test_noop_on_missing_file_returns_path_unchanged(self):
        # Unmeasurable duration -> factor None -> returns input path, no ffmpeg,
        # no crash.
        p = "/nonexistent/dialogue.mp3"
        assert _apply_target_pace(p, "one two three", 145) == p

    def test_noop_when_disabled(self, tmp_path):
        f = tmp_path / "d.mp3"
        f.write_bytes(b"not really audio")
        # target 0 disables pacing before any probe/ffmpeg call.
        assert _apply_target_pace(str(f), "one two three", 0) == str(f)
