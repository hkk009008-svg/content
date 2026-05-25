"""tests/unit/test_screening.py -- S19 SCREENING scaffolding helpers.

Covers the pure-function pieces of cinema/screening.py:

1. ``_screening_stage_enabled()`` env-flag truthy/falsy values.
2. ``_build_timeline_manifest(project)`` for the canonical shapes:
   - empty project -> []
   - one scene / one shot with approved take -> single entry
   - one scene / two shots -> cumulative start/end timing
   - shots without approved_final_take_id are skipped
   - duration source precedence (take.metadata.duration_s >
     scene.duration_seconds > 5.0)
3. ``is_screening_approved(project)`` / ``mark_screening_approved(pid)``.

Tests do NOT touch the filesystem (except the mark_screening_approved
test which uses a patched ``mutate_project``). No live LLM / pipeline /
ffmpeg required.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from cinema.screening import (
    SCREENING_APPROVED_KEY,
    SCREENING_STAGE_NAME,
    _build_timeline_manifest,
    _screening_stage_enabled,
    _take_duration_seconds,
    is_screening_approved,
    mark_screening_approved,
)


# ---------------------------------------------------------------------------
# Feature flag tests -- mirrors test_iterate_endpoint.py:TestDirectorialIterationFlag
# ---------------------------------------------------------------------------


class TestScreeningStageFlag:
    """_screening_stage_enabled() respects CINEMA_SCREENING_STAGE env."""

    def test_flag_off_by_default(self):
        env = {k: v for k, v in os.environ.items() if k != "CINEMA_SCREENING_STAGE"}
        with patch.dict(os.environ, env, clear=True):
            assert _screening_stage_enabled() is False

    @pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "YES"])
    def test_flag_on_truthy_values(self, value):
        with patch.dict(os.environ, {"CINEMA_SCREENING_STAGE": value}):
            assert _screening_stage_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "", "off", "True ", " 1"])
    def test_flag_off_falsy_or_unrecognised_values(self, value):
        # Trailing whitespace is stripped by the helper; leading
        # whitespace is also stripped. " 1" / "True " ARE truthy because
        # of the .strip() -- include them in the truthy-args param if
        # the helper-shape semantics change.
        with patch.dict(os.environ, {"CINEMA_SCREENING_STAGE": value}):
            if value.strip().lower() in {"1", "true", "yes"}:
                # whitespace-tolerated values should still parse as on
                assert _screening_stage_enabled() is True
            else:
                assert _screening_stage_enabled() is False


# ---------------------------------------------------------------------------
# _take_duration_seconds unit tests
# ---------------------------------------------------------------------------


class TestTakeDurationSeconds:
    """Verifies the duration-extraction precedence."""

    def test_take_metadata_duration_used_when_present(self):
        take = {"id": "t1", "metadata": {"duration_s": 7.5}}
        assert _take_duration_seconds(take, fallback=5.0) == 7.5

    def test_fallback_used_when_metadata_absent(self):
        take = {"id": "t1", "metadata": {}}
        assert _take_duration_seconds(take, fallback=6.0) == 6.0

    def test_fallback_used_when_take_has_no_metadata_key(self):
        take = {"id": "t1"}
        assert _take_duration_seconds(take, fallback=4.5) == 4.5

    def test_fallback_used_for_non_numeric_duration(self):
        take = {"id": "t1", "metadata": {"duration_s": "not-a-number"}}
        assert _take_duration_seconds(take, fallback=3.0) == 3.0

    def test_fallback_used_for_non_dict_take(self):
        assert _take_duration_seconds("not-a-dict", fallback=5.0) == 5.0  # type: ignore[arg-type]
        assert _take_duration_seconds(None, fallback=5.0) == 5.0  # type: ignore[arg-type]

    def test_integer_duration_coerced_to_float(self):
        take = {"id": "t1", "metadata": {"duration_s": 5}}
        result = _take_duration_seconds(take, fallback=5.0)
        assert result == 5.0
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# _build_timeline_manifest tests
# ---------------------------------------------------------------------------


def _shot(shot_id: str, approved: str = "", *, takes: dict | None = None) -> dict:
    """Build a minimal shot dict for manifest tests.

    ``takes`` maps collection name -> list[take_dict]. If omitted and
    ``approved`` is set, the approved take is auto-inserted into
    ``motion_takes`` (the most common storage location for the approved
    final take).
    """
    if takes is None and approved:
        takes = {"motion_takes": [{"id": approved, "kind": "motion"}]}
    shot: dict = {
        "id": shot_id,
        "approved_final_take_id": approved,
    }
    if takes:
        shot.update(takes)
    return shot


def _scene(scene_id: str, shots: list[dict], duration: float | None = None) -> dict:
    scene: dict = {"id": scene_id, "shots": shots}
    if duration is not None:
        scene["duration_seconds"] = duration
    return scene


class TestBuildTimelineManifest:
    """_build_timeline_manifest walks scenes/shots and produces per-shot timing."""

    def test_empty_project_returns_empty_list(self):
        assert _build_timeline_manifest({}) == []
        assert _build_timeline_manifest({"scenes": []}) == []
        assert _build_timeline_manifest({"scenes": [{"id": "s1", "shots": []}]}) == []

    def test_single_shot_uses_scene_duration_as_fallback(self):
        project = {
            "scenes": [
                _scene("s1", [_shot("shot_1_0", approved="take_a")], duration=6.0),
            ]
        }
        manifest = _build_timeline_manifest(project)
        assert len(manifest) == 1
        entry = manifest[0]
        assert entry["shot_id"] == "shot_1_0"
        assert entry["scene_id"] == "s1"
        assert entry["start_s"] == 0.0
        assert entry["end_s"] == 6.0
        assert entry["approved_take_id"] == "take_a"
        assert entry["take_count"] == 1

    def test_two_shots_cumulative_timing(self):
        project = {
            "scenes": [
                _scene("s1", [
                    _shot("shot_1_0", approved="take_a"),
                    _shot("shot_1_1", approved="take_b"),
                ], duration=4.0),
            ]
        }
        manifest = _build_timeline_manifest(project)
        assert len(manifest) == 2
        assert manifest[0]["start_s"] == 0.0
        assert manifest[0]["end_s"] == 4.0
        assert manifest[1]["start_s"] == 4.0
        assert manifest[1]["end_s"] == 8.0

    def test_shots_without_approved_take_are_skipped(self):
        project = {
            "scenes": [
                _scene("s1", [
                    _shot("shot_1_0", approved="take_a"),
                    _shot("shot_1_1", approved=""),  # not approved -> skipped
                    _shot("shot_1_2", approved="take_c"),
                ], duration=3.0),
            ]
        }
        manifest = _build_timeline_manifest(project)
        assert [e["shot_id"] for e in manifest] == ["shot_1_0", "shot_1_2"]
        # shot_1_1 is omitted, so shot_1_2 starts where shot_1_0 ended.
        assert manifest[1]["start_s"] == 3.0
        assert manifest[1]["end_s"] == 6.0

    def test_take_metadata_duration_overrides_scene_fallback(self):
        # The approved take has metadata.duration_s=2.5, which should win
        # over the scene's duration_seconds=10.0.
        project = {
            "scenes": [
                _scene("s1", [
                    _shot("shot_1_0", approved="take_a", takes={
                        "motion_takes": [
                            {"id": "take_a", "kind": "motion",
                             "metadata": {"duration_s": 2.5}},
                        ],
                    }),
                ], duration=10.0),
            ]
        }
        manifest = _build_timeline_manifest(project)
        assert len(manifest) == 1
        assert manifest[0]["end_s"] == 2.5

    def test_fallback_5_when_no_scene_duration_and_no_take_metadata(self):
        project = {
            "scenes": [
                _scene("s1", [_shot("shot_1_0", approved="take_a")]),
                # no duration_seconds key
            ]
        }
        manifest = _build_timeline_manifest(project)
        assert manifest[0]["end_s"] == 5.0

    def test_take_count_counts_all_take_kinds(self):
        # take_count is the sum across motion_takes + postprocess_variants
        # + performance_takes + keyframe_takes -- the operator's iteration
        # history depth at this shot.
        project = {
            "scenes": [
                _scene("s1", [
                    _shot("shot_1_0", approved="take_a", takes={
                        "motion_takes": [
                            {"id": "take_a", "kind": "motion"},
                            {"id": "take_a2", "kind": "motion"},
                        ],
                        "keyframe_takes": [
                            {"id": "take_kf1", "kind": "keyframe"},
                            {"id": "take_kf2", "kind": "keyframe"},
                            {"id": "take_kf3", "kind": "keyframe"},
                        ],
                        "postprocess_variants": [
                            {"id": "take_pp1", "kind": "postprocess"},
                        ],
                    }),
                ], duration=5.0),
            ]
        }
        manifest = _build_timeline_manifest(project)
        assert manifest[0]["take_count"] == 6  # 2 motion + 3 keyframe + 1 postprocess

    def test_approved_take_can_live_in_postprocess_variants(self):
        # The approved take's duration is read from wherever it's stored;
        # mirror the wide-search behaviour of cinema_pipeline._resolve_take_path.
        project = {
            "scenes": [
                _scene("s1", [
                    _shot("shot_1_0", approved="take_pp", takes={
                        "motion_takes": [{"id": "take_m1", "kind": "motion"}],
                        "postprocess_variants": [
                            {"id": "take_pp", "kind": "postprocess",
                             "metadata": {"duration_s": 8.0}},
                        ],
                    }),
                ], duration=5.0),
            ]
        }
        manifest = _build_timeline_manifest(project)
        # postprocess take's duration_s wins over scene fallback.
        assert manifest[0]["end_s"] == 8.0

    def test_multi_scene_cumulative_timing(self):
        project = {
            "scenes": [
                _scene("s1", [
                    _shot("shot_1_0", approved="t1"),
                ], duration=3.0),
                _scene("s2", [
                    _shot("shot_2_0", approved="t2"),
                    _shot("shot_2_1", approved="t3"),
                ], duration=4.0),
            ]
        }
        manifest = _build_timeline_manifest(project)
        assert [e["scene_id"] for e in manifest] == ["s1", "s2", "s2"]
        assert manifest[0]["start_s"] == 0.0
        assert manifest[0]["end_s"] == 3.0
        assert manifest[1]["start_s"] == 3.0
        assert manifest[1]["end_s"] == 7.0
        assert manifest[2]["start_s"] == 7.0
        assert manifest[2]["end_s"] == 11.0

    def test_defensive_against_non_dict_scene_or_shot(self):
        # Defensive: a corrupted project shouldn't crash manifest construction.
        project = {
            "scenes": [
                None,
                "not-a-scene",
                _scene("s1", [
                    None,
                    "not-a-shot",
                    _shot("shot_1_0", approved="take_a"),
                ], duration=3.0),
            ]
        }
        manifest = _build_timeline_manifest(project)
        assert len(manifest) == 1
        assert manifest[0]["shot_id"] == "shot_1_0"


# ---------------------------------------------------------------------------
# Gate accessor / mutator tests
# ---------------------------------------------------------------------------


class TestScreeningApprovedAccessors:
    """is_screening_approved + mark_screening_approved behave as documented."""

    def test_is_screening_approved_false_when_missing(self):
        assert is_screening_approved({"id": "p1"}) is False

    def test_is_screening_approved_false_when_explicit_false(self):
        assert is_screening_approved({SCREENING_APPROVED_KEY: False}) is False

    def test_is_screening_approved_true_when_truthy(self):
        assert is_screening_approved({SCREENING_APPROVED_KEY: True}) is True

    def test_is_screening_approved_handles_non_dict(self):
        assert is_screening_approved(None) is False  # type: ignore[arg-type]
        assert is_screening_approved("not-a-project") is False  # type: ignore[arg-type]

    def test_mark_screening_approved_sets_flag_and_persists(self):
        # Use a fake mutate_project that exercises the mutator like the
        # real one does (load -> apply -> save).
        recorded: dict = {"calls": []}
        project_state = {"id": "p1"}

        def fake_mutate(pid, mutator_fn, timeout=10, snapshot=None):
            recorded["calls"].append(pid)
            result = mutator_fn(project_state)
            from project_manager import MutationResult
            if isinstance(result, MutationResult):
                return result.value
            return result

        with patch("project_manager.mutate_project", side_effect=fake_mutate):
            result = mark_screening_approved("p1")

        assert recorded["calls"] == ["p1"]
        assert project_state.get(SCREENING_APPROVED_KEY) is True
        assert result["success"] is True
        assert result["screening_approved"] is True

    def test_mark_screening_approved_raises_when_project_missing(self):
        # Real mutate_project returns None when the project file is absent;
        # mark_screening_approved should surface this as ValueError.
        with patch("project_manager.mutate_project", return_value=None):
            with pytest.raises(ValueError, match="not found"):
                mark_screening_approved("missing-pid")


# ---------------------------------------------------------------------------
# Module-level constant sanity (catches accidental rename)
# ---------------------------------------------------------------------------


def test_stage_name_constant():
    assert SCREENING_STAGE_NAME == "SCREENING"


def test_approved_key_constant():
    assert SCREENING_APPROVED_KEY == "screening_approved"
