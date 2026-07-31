"""Tests for domain/performance.py — pure routing logic.

The routing matrix (handoff §3) has ~30 branches across shot_type strings,
dialogue presence, character presence, and budget mode. This file locks
each branch with a one-line shot dict + asserted engine string.
"""
from __future__ import annotations

import pytest

from domain.performance import (
    ENGINE_ACT_ONE, ENGINE_LIVE_PORTRAIT, ENGINE_VIGGLE, ENGINE_SKIP,
    route_performance_engine,
    should_capture,
    shot_needs_driving_video,
    driving_video_source,
    precondition_error,
)


def _shot(**overrides) -> dict:
    """Default character-bearing dialogue shot, overridable per test."""
    base = {
        "shot_type": "medium",
        "characters_in_frame": ["alice"],
        "dialogue": "Hello world.",
        "performance_budget_mode": "",
        "driving_video_path": "",
    }
    base.update(overrides)
    return base


class TestSkipRules:
    def test_no_characters_returns_skip(self):
        assert route_performance_engine(_shot(characters_in_frame=[]), None) == ENGINE_SKIP

    def test_landscape_returns_skip(self):
        assert route_performance_engine(_shot(shot_type="landscape"), None) == ENGINE_SKIP

    def test_wide_no_dialogue_returns_skip(self):
        assert route_performance_engine(_shot(shot_type="wide", dialogue=""), None) == ENGINE_SKIP



class TestActOneRouting:
    @pytest.mark.parametrize("shot_type", [
        "portrait", "medium", "close-up", "closeup", "close_up", "ecu",
        "PORTRAIT",  # case-insensitivity guard
    ])
    def test_dialogue_plus_face_framing_routes_act_one(self, shot_type):
        assert route_performance_engine(_shot(shot_type=shot_type), None) == ENGINE_ACT_ONE

    def test_dialogue_in_other_framing_falls_through_to_act_one(self):
        # Rule 4 in route_performance_engine: dialogue in any framing → ACT_ONE
        assert route_performance_engine(_shot(shot_type="over_shoulder"), None) == ENGINE_ACT_ONE

    def test_empty_shot_type_with_characters_falls_through(self):
        # Empty shot_type with characters + dialogue hits rule 4 (dialogue → ACT_ONE),
        # not SKIP. Lock this so future changes don't silently route empty types away.
        assert route_performance_engine(
            _shot(shot_type="", dialogue="hi"), None
        ) == ENGINE_ACT_ONE

    def test_dialogue_as_list_routes_act_one(self):
        dlg = [{"text": "Hi"}, {"text": "There"}]
        assert route_performance_engine(_shot(dialogue=dlg), None) == ENGINE_ACT_ONE


class TestLivePortraitRouting:
    @pytest.mark.parametrize("mode", ["budget", "cheap", "Budget", "CHEAP"])
    def test_budget_mode_swaps_act_one_for_live_portrait(self, mode):
        shot = _shot(shot_type="portrait", performance_budget_mode=mode)
        assert route_performance_engine(shot, None) == ENGINE_LIVE_PORTRAIT


class TestViggleRouting:
    def test_action_no_dialogue_routes_viggle(self):
        shot = _shot(shot_type="action", dialogue="")
        assert route_performance_engine(shot, None) == ENGINE_VIGGLE

    def test_action_with_dialogue_routes_act_one(self):
        shot = _shot(shot_type="action", dialogue="Charge!")
        assert route_performance_engine(shot, None) == ENGINE_ACT_ONE


class TestShouldCapture:
    def test_no_characters_false(self):
        assert should_capture(_shot(characters_in_frame=[]), None) is False

    def test_landscape_false(self):
        assert should_capture(_shot(shot_type="landscape"), None) is False

    def test_dialogue_medium_true(self):
        assert should_capture(_shot(), None) is True


class TestShotNeedsDrivingVideo:
    def test_act_one_needs_driving_video(self):
        # ACT_ONE now routes to Runway Act-Two (performance/act_two.py),
        # which has no audio-only generation mode — unlike the retired
        # Act-One, it always needs an actual driving video (Mode-B synth or
        # a direct upload) by dispatch time.
        assert shot_needs_driving_video(_shot(shot_type="portrait")) is True

    def test_live_portrait_needs_driving_video(self):
        shot = _shot(shot_type="portrait", performance_budget_mode="cheap")
        assert shot_needs_driving_video(shot) is True

    def test_viggle_needs_driving_video(self):
        shot = _shot(shot_type="action", dialogue="")
        assert shot_needs_driving_video(shot) is True

    def test_skip_does_not_need_driving_video(self):
        assert shot_needs_driving_video(_shot(characters_in_frame=[])) is False


class TestDrivingVideoSource:
    def test_uploaded_wins(self):
        shot = _shot(driving_video_path="/tmp/uploaded.mp4")
        assert driving_video_source(shot) == "upload"

    def test_dialogue_no_upload_is_tts_auto(self):
        assert driving_video_source(_shot()) == "tts_auto"

    def test_no_dialogue_no_action_is_none(self):
        # No dialogue + non-action + non-landscape shot type → rule 5 fall-through
        # in route_performance_engine returns SKIP → driving_video_source returns "none"
        assert driving_video_source(_shot(dialogue="", shot_type="medium")) == "none"


class TestPreconditionErrorActOne:
    """ACT_ONE now routes to Runway Act-Two (performance/act_two.py), which
    has no audio-only mode. precondition_error runs BEFORE controller.py's
    Mode-B synth step (cinema/shots/controller.py), so audio_path alone
    must still satisfy the pre-check — it is what lets Mode-B produce a
    driving video before the actual engine call. Only "neither present" is
    a real, unrecoverable precondition failure."""

    def test_neither_audio_nor_driving_video_fails_and_names_driving_video(self):
        err = precondition_error(ENGINE_ACT_ONE, audio_path="", driving_video_path="")
        assert err is not None
        assert "driving video" in err.lower()

    def test_none_inputs_also_fail(self):
        assert precondition_error(ENGINE_ACT_ONE, audio_path=None, driving_video_path=None) is not None

    def test_audio_only_passes_because_mode_b_can_still_synthesize(self):
        # Audio alone is not a valid Act-Two dispatch input, but it IS
        # sufficient for this pre-check, since Mode-B hasn't run yet.
        assert precondition_error(ENGINE_ACT_ONE, audio_path="/tmp/a.wav", driving_video_path="") is None

    def test_driving_video_only_passes(self):
        # Fixes the old Act-One-shaped bug: a shot with an uploaded driving
        # video but no dialogue/audio used to be incorrectly rejected here,
        # even though Act-Two never needed audio at all.
        assert precondition_error(ENGINE_ACT_ONE, audio_path="", driving_video_path="/tmp/d.mp4") is None

    def test_both_present_passes(self):
        assert precondition_error(
            ENGINE_ACT_ONE, audio_path="/tmp/a.wav", driving_video_path="/tmp/d.mp4"
        ) is None


class TestPreconditionErrorOtherEngines:
    def test_live_portrait_requires_driving_video_regardless_of_audio(self):
        err = precondition_error(ENGINE_LIVE_PORTRAIT, audio_path="/tmp/a.wav", driving_video_path="")
        assert err is not None and "driving" in err.lower()

    def test_viggle_requires_driving_video(self):
        err = precondition_error(ENGINE_VIGGLE, audio_path="", driving_video_path="")
        assert err is not None and "driving" in err.lower()

    def test_skip_never_fails(self):
        assert precondition_error(ENGINE_SKIP, audio_path="", driving_video_path="") is None
