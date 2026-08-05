"""Tests for domain/performance.py — pure routing logic.

The routing matrix (handoff §3) has ~30 branches across shot_type strings,
dialogue presence, character presence, and budget mode. This file locks
each branch with a one-line shot dict + asserted engine string.
"""
from __future__ import annotations

import pytest

from domain.performance import (
    ENGINE_ACT_ONE, ENGINE_LIVE_PORTRAIT, ENGINE_VIGGLE, ENGINE_SKIP,
    has_current_performance_skip,
    project_performance_review_can_skip,
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


class TestCurrentSkipAuthority:
    @staticmethod
    def _routing_decision(path: str = "") -> dict:
        return {
            "id": "skip-1",
            "action": "skip",
            "reason": "routing",
            "decision_source": "routing",
            "created_at": "2026-08-05T00:00:00+00:00",
            "routed_engine": "SKIP",
            "driving_video_path": path,
        }

    def test_bare_persisted_engine_is_not_skip_authority(self):
        shot = _shot(
            characters_in_frame=[],
            performance_engine="SKIP",
            approved_keyframe_take_id="kf-1",
        )
        assert has_current_performance_skip(shot) is False
        assert project_performance_review_can_skip({
            "scenes": [{"shots": [shot]}],
        }) is False

    def test_current_routing_decision_can_skip_pipeline_review(self):
        shot = _shot(
            characters_in_frame=[],
            performance_engine="SKIP",
            performance_skip=self._routing_decision(),
            approved_keyframe_take_id="kf-1",
        )
        assert has_current_performance_skip(shot) is True
        assert project_performance_review_can_skip({
            "scenes": [{"shots": [shot]}],
        }) is True

    def test_changed_driving_revision_invalidates_skip_and_pipeline_bypass(self):
        shot = _shot(
            characters_in_frame=[],
            performance_engine="SKIP",
            performance_skip=self._routing_decision("old.mp4"),
            driving_video_path="new.mp4",
            approved_keyframe_take_id="kf-1",
        )
        assert has_current_performance_skip(shot) is False
        assert project_performance_review_can_skip({
            "scenes": [{"shots": [shot]}],
        }) is False



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
        # Uncontained 2026-08-01 (ADR-082). This assertion was the Slice-6c
        # containment pin (== ENGINE_SKIP) and is now the live-routing pin.
        shot = _shot(shot_type="action", dialogue="")
        assert route_performance_engine(shot, None) == ENGINE_VIGGLE

    def test_viggle_catalog_entry_agrees_with_the_route(self):
        # The containment was a SEVEN-file agreement, and two of those files
        # (this router and the catalog) are hand-maintained in parallel rather
        # than derived from each other — so nothing but a test stops them
        # drifting back into contradiction. KNOWN_BROKEN here while rule 3
        # returns ENGINE_VIGGLE is exactly the state ADR-082 closed.
        from domain.provider_catalog import CATALOG, ProductSupport
        assert CATALOG["VIGGLE"].product_support is ProductSupport.LIMITED, (
            "catalog says VIGGLE is "
            f"{CATALOG['VIGGLE'].product_support}, but domain/performance.py "
            "rule 3 routes action/no-dialogue shots to it"
        )

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
        # Act-One, it always needs an operator-uploaded driving video.
        assert shot_needs_driving_video(_shot(shot_type="portrait")) is True

    def test_live_portrait_needs_driving_video(self):
        shot = _shot(shot_type="portrait", performance_budget_mode="cheap")
        assert shot_needs_driving_video(shot) is True

    def test_viggle_route_needs_a_driving_video(self):
        # Uncontained 2026-08-01 (ADR-082). While contained this asserted
        # False, because SKIP needs no driving video. Now the route selects
        # ENGINE_VIGGLE, which has always required an operator upload.
        shot = _shot(shot_type="action", dialogue="")
        assert shot_needs_driving_video(shot) is True

    def test_skip_does_not_need_driving_video(self):
        assert shot_needs_driving_video(_shot(characters_in_frame=[])) is False


class TestDrivingVideoSource:
    def test_uploaded_wins(self):
        shot = _shot(driving_video_path="/tmp/uploaded.mp4")
        assert driving_video_source(shot) == "upload"

    def test_dialogue_no_upload_is_none(self):
        assert driving_video_source(_shot()) == "none"

    def test_no_dialogue_no_action_is_none(self):
        # No dialogue + non-action + non-landscape shot type → rule 5 fall-through
        # in route_performance_engine returns SKIP → driving_video_source returns "none"
        assert driving_video_source(_shot(dialogue="", shot_type="medium")) == "none"


class TestPreconditionErrorActOne:
    """ACT_ONE now routes to Runway Act-Two (performance/act_two.py), which
    has no audio-only mode. Dialogue audio never replaces a driving video."""

    def test_neither_audio_nor_driving_video_fails_and_names_driving_video(self):
        err = precondition_error(ENGINE_ACT_ONE, audio_path="", driving_video_path="")
        assert err is not None
        assert "driving video" in err.lower()

    def test_none_inputs_also_fail(self):
        assert precondition_error(ENGINE_ACT_ONE, audio_path=None, driving_video_path=None) is not None

    def test_audio_only_fails(self):
        assert precondition_error(
            ENGINE_ACT_ONE,
            audio_path="/tmp/a.wav",
            driving_video_path="",
        ) is not None

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
