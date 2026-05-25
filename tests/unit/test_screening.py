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
    NEEDS_REASSEMBLY_KEY,
    SCREENING_APPROVED_KEY,
    SCREENING_STAGE_NAME,
    _build_timeline_manifest,
    _screening_stage_enabled,
    _take_duration_seconds,
    clear_needs_reassembly,
    estimate_reassembly_cost,
    get_needs_reassembly,
    is_screening_approved,
    mark_screening_approved,
    mark_shot_needs_reassembly,
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


class TestBuildTimelineManifestVerifyFiles:
    """Code-quality reviewer S19 IMPORTANT: verify_files=True locks the strict
    mirror of _build_scene_packages's filesystem-existence check.

    Without this filter, a shot whose take_id is set but whose mp4 was deleted
    between assembly and screening would appear in the manifest at a stale
    start_s/end_s while NOT being in the assembled video — operator scrubber
    would land on a phantom shot.

    See cinema/screening.py:_build_timeline_manifest verify_files docstring +
    cinema_pipeline.py:544-548 (the mirrored rule).
    """

    def test_verify_files_false_includes_shot_without_path(self):
        """Default (verify_files=False) preserves the original behavior — no
        filesystem dependency, tests stay filesystem-free."""
        project = {
            "scenes": [
                _scene("s1", [_shot("shot_1_0", approved="take_a")], duration=4.0),
            ]
        }
        manifest = _build_timeline_manifest(project)  # default False
        assert len(manifest) == 1

    def test_verify_files_true_excludes_missing_path(self, tmp_path):
        """verify_files=True excludes shots whose approved-take path is missing."""
        # Build a shot whose take has a path pointing to a NONEXISTENT file
        missing = tmp_path / "nonexistent.mp4"
        shot = {
            "id": "shot_1_0",
            "approved_final_take_id": "take_a",
            "motion_takes": [{"id": "take_a", "kind": "motion", "path": str(missing)}],
        }
        project = {"scenes": [_scene("s1", [shot], duration=4.0)]}
        manifest = _build_timeline_manifest(project, verify_files=True)
        assert manifest == [], "Shot with missing mp4 should be excluded"

    def test_verify_files_true_excludes_empty_path(self):
        """A take with an empty `path` field is also excluded (corruption signal)."""
        shot = {
            "id": "shot_1_0",
            "approved_final_take_id": "take_a",
            "motion_takes": [{"id": "take_a", "kind": "motion", "path": ""}],
        }
        project = {"scenes": [_scene("s1", [shot], duration=4.0)]}
        manifest = _build_timeline_manifest(project, verify_files=True)
        assert manifest == []

    def test_verify_files_true_includes_existing_file(self, tmp_path):
        """verify_files=True keeps shots whose mp4 actually exists on disk."""
        real_mp4 = tmp_path / "real.mp4"
        real_mp4.write_bytes(b"\x00" * 16)  # tiny stub file
        shot = {
            "id": "shot_1_0",
            "approved_final_take_id": "take_a",
            "motion_takes": [{"id": "take_a", "kind": "motion", "path": str(real_mp4)}],
        }
        project = {"scenes": [_scene("s1", [shot], duration=4.0)]}
        manifest = _build_timeline_manifest(project, verify_files=True)
        assert len(manifest) == 1
        assert manifest[0]["shot_id"] == "shot_1_0"
        assert manifest[0]["start_s"] == 0.0
        assert manifest[0]["end_s"] == 4.0

    def test_verify_files_true_cumulates_only_present_files(self, tmp_path):
        """When some files exist and others don't, cumulative timing reflects
        only the present-file shots — start_s for shot_3 starts at shot_1's
        end (not shot_1's end + shot_2's missing duration)."""
        real_a = tmp_path / "shot_a.mp4"
        real_a.write_bytes(b"\x00" * 16)
        real_c = tmp_path / "shot_c.mp4"
        real_c.write_bytes(b"\x00" * 16)
        missing_b = tmp_path / "shot_b_deleted.mp4"  # not written
        shots = [
            {
                "id": "shot_a",
                "approved_final_take_id": "take_a",
                "motion_takes": [{"id": "take_a", "kind": "motion", "path": str(real_a)}],
            },
            {
                "id": "shot_b",
                "approved_final_take_id": "take_b",
                "motion_takes": [{"id": "take_b", "kind": "motion", "path": str(missing_b)}],
            },
            {
                "id": "shot_c",
                "approved_final_take_id": "take_c",
                "motion_takes": [{"id": "take_c", "kind": "motion", "path": str(real_c)}],
            },
        ]
        project = {"scenes": [_scene("s1", shots, duration=3.0)]}
        manifest = _build_timeline_manifest(project, verify_files=True)
        assert [e["shot_id"] for e in manifest] == ["shot_a", "shot_c"]
        # shot_b's 3.0s gap is NOT added — cursor advances only on included shots.
        assert manifest[0]["start_s"] == 0.0
        assert manifest[0]["end_s"] == 3.0
        assert manifest[1]["start_s"] == 3.0
        assert manifest[1]["end_s"] == 6.0


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


def test_needs_reassembly_key_constant():
    assert NEEDS_REASSEMBLY_KEY == "needs_reassembly"


# ---------------------------------------------------------------------------
# S21 (cycle-9 Surface B): needs_reassembly accessors + mutators
# ---------------------------------------------------------------------------


class TestGetNeedsReassembly:
    """get_needs_reassembly reads the field defensively."""

    def test_empty_project_returns_empty_list(self):
        assert get_needs_reassembly({}) == []

    def test_missing_key_returns_empty_list(self):
        assert get_needs_reassembly({"id": "p1"}) == []

    def test_explicit_empty_list(self):
        assert get_needs_reassembly({NEEDS_REASSEMBLY_KEY: []}) == []

    def test_populated_list_returned_in_order(self):
        project = {NEEDS_REASSEMBLY_KEY: ["shot_1_0", "shot_1_1", "shot_2_0"]}
        assert get_needs_reassembly(project) == ["shot_1_0", "shot_1_1", "shot_2_0"]

    def test_non_list_value_returns_empty(self):
        # Defensive: a corrupted project.json round-trip could land here.
        assert get_needs_reassembly({NEEDS_REASSEMBLY_KEY: "not-a-list"}) == []
        assert get_needs_reassembly({NEEDS_REASSEMBLY_KEY: 42}) == []
        assert get_needs_reassembly({NEEDS_REASSEMBLY_KEY: None}) == []

    def test_non_dict_project_returns_empty(self):
        assert get_needs_reassembly(None) == []  # type: ignore[arg-type]
        assert get_needs_reassembly("not-a-project") == []  # type: ignore[arg-type]

    def test_filters_non_string_entries(self):
        # Mixed garbage shouldn't poison the list.
        project = {NEEDS_REASSEMBLY_KEY: ["shot_a", 42, None, "shot_b", {"k": "v"}]}
        assert get_needs_reassembly(project) == ["shot_a", "shot_b"]


class TestMarkShotNeedsReassembly:
    """mark_shot_needs_reassembly idempotently adds a shot_id."""

    def test_adds_to_empty_list(self):
        project_state: dict = {"id": "p1"}

        def fake_mutate(pid, mutator_fn, timeout=10, snapshot=None):
            result = mutator_fn(project_state)
            from project_manager import MutationResult
            if isinstance(result, MutationResult):
                return result.value
            return result

        with patch("project_manager.mutate_project", side_effect=fake_mutate):
            result = mark_shot_needs_reassembly("p1", "shot_1_0")

        assert result["success"] is True
        assert result["needs_reassembly"] == ["shot_1_0"]
        assert project_state[NEEDS_REASSEMBLY_KEY] == ["shot_1_0"]

    def test_idempotent_add_same_shot(self):
        project_state: dict = {"id": "p1", NEEDS_REASSEMBLY_KEY: ["shot_1_0"]}

        def fake_mutate(pid, mutator_fn, timeout=10, snapshot=None):
            result = mutator_fn(project_state)
            from project_manager import MutationResult
            if isinstance(result, MutationResult):
                return result.value
            return result

        with patch("project_manager.mutate_project", side_effect=fake_mutate):
            result = mark_shot_needs_reassembly("p1", "shot_1_0")

        # Re-adding the same shot is a no-op — no duplicates.
        assert result["needs_reassembly"] == ["shot_1_0"]
        assert project_state[NEEDS_REASSEMBLY_KEY] == ["shot_1_0"]

    def test_appends_new_shot_preserving_order(self):
        project_state: dict = {"id": "p1", NEEDS_REASSEMBLY_KEY: ["shot_1_0", "shot_2_0"]}

        def fake_mutate(pid, mutator_fn, timeout=10, snapshot=None):
            result = mutator_fn(project_state)
            from project_manager import MutationResult
            if isinstance(result, MutationResult):
                return result.value
            return result

        with patch("project_manager.mutate_project", side_effect=fake_mutate):
            mark_shot_needs_reassembly("p1", "shot_3_0")

        # Insertion order preserved.
        assert project_state[NEEDS_REASSEMBLY_KEY] == ["shot_1_0", "shot_2_0", "shot_3_0"]

    def test_empty_shot_id_returns_failure(self):
        # Defensive: don't write empty strings into the dirty list.
        result = mark_shot_needs_reassembly("p1", "")
        assert result["success"] is False

    def test_corrupted_field_replaced(self):
        # If the field is corrupted (not a list), the mutator resets it.
        project_state: dict = {"id": "p1", NEEDS_REASSEMBLY_KEY: "not-a-list"}

        def fake_mutate(pid, mutator_fn, timeout=10, snapshot=None):
            result = mutator_fn(project_state)
            from project_manager import MutationResult
            if isinstance(result, MutationResult):
                return result.value
            return result

        with patch("project_manager.mutate_project", side_effect=fake_mutate):
            mark_shot_needs_reassembly("p1", "shot_1_0")

        assert project_state[NEEDS_REASSEMBLY_KEY] == ["shot_1_0"]

    def test_project_not_found_returns_failure_not_raise(self):
        # mark_shot_needs_reassembly is best-effort -- it returns failure
        # instead of raising so iterate's controller can swallow it without
        # disturbing the iteration response shape.
        with patch("project_manager.mutate_project", return_value=None):
            result = mark_shot_needs_reassembly("missing-pid", "shot_1_0")
        assert result["success"] is False
        assert "not found" in result["error"]


class TestClearNeedsReassembly:
    """clear_needs_reassembly empties the list."""

    def test_clears_populated_list(self):
        project_state: dict = {"id": "p1", NEEDS_REASSEMBLY_KEY: ["shot_a", "shot_b"]}

        def fake_mutate(pid, mutator_fn, timeout=10, snapshot=None):
            result = mutator_fn(project_state)
            from project_manager import MutationResult
            if isinstance(result, MutationResult):
                return result.value
            return result

        with patch("project_manager.mutate_project", side_effect=fake_mutate):
            result = clear_needs_reassembly("p1")

        assert result["success"] is True
        assert result["needs_reassembly"] == []
        assert project_state[NEEDS_REASSEMBLY_KEY] == []

    def test_clears_already_empty_list_idempotent(self):
        project_state: dict = {"id": "p1", NEEDS_REASSEMBLY_KEY: []}

        def fake_mutate(pid, mutator_fn, timeout=10, snapshot=None):
            result = mutator_fn(project_state)
            from project_manager import MutationResult
            if isinstance(result, MutationResult):
                return result.value
            return result

        with patch("project_manager.mutate_project", side_effect=fake_mutate):
            clear_needs_reassembly("p1")

        assert project_state[NEEDS_REASSEMBLY_KEY] == []

    def test_raises_when_project_missing(self):
        with patch("project_manager.mutate_project", return_value=None):
            with pytest.raises(ValueError, match="not found"):
                clear_needs_reassembly("missing-pid")


class TestEstimateReassemblyCost:
    """estimate_reassembly_cost returns reasonable values for known shapes."""

    def test_empty_project_returns_floor(self):
        result = estimate_reassembly_cost({})
        # Floor (5s) catches single-shot/empty cases.
        assert result["seconds"] == 5.0
        assert result["shot_count"] == 0
        assert result["total_source_duration_s"] == 0.0

    def test_non_dict_returns_floor(self):
        result = estimate_reassembly_cost(None)  # type: ignore[arg-type]
        assert result["seconds"] == 5.0
        assert "breakdown" in result

    def test_breakdown_includes_normalize_and_duration_bound(self):
        result = estimate_reassembly_cost({})
        breakdown = result["breakdown"]
        assert "normalize_s" in breakdown
        assert "duration_bound_s" in breakdown
        assert "floor_s" in breakdown

    def test_30_shot_project_scales_linearly(self):
        # 30 shots × 5s each. Expected: 30 * 0.5 (normalize) + 150 * 0.09 (duration)
        # = 15 + 13.5 = 28.5s. Well within the "ship full rerun" budget.
        shots = []
        for i in range(30):
            shots.append({
                "id": f"shot_1_{i}",
                "approved_final_take_id": f"take_{i}",
                "motion_takes": [
                    {"id": f"take_{i}", "kind": "motion",
                     "metadata": {"duration_s": 5.0}},
                ],
            })
        project = {"scenes": [{"id": "s1", "shots": shots, "duration_seconds": 5.0}]}
        result = estimate_reassembly_cost(project)
        assert result["shot_count"] == 30
        assert result["total_source_duration_s"] == 150.0
        # 15 + 13.5 = 28.5
        assert 28.0 <= result["seconds"] <= 29.0

    def test_unapproved_shots_excluded(self):
        # Shots without approved_final_take_id don't count toward cost.
        shots = [
            {"id": "shot_a", "approved_final_take_id": "take_a",
             "motion_takes": [{"id": "take_a", "kind": "motion",
                               "metadata": {"duration_s": 5.0}}]},
            {"id": "shot_b", "approved_final_take_id": ""},  # not approved
        ]
        project = {"scenes": [{"id": "s1", "shots": shots, "duration_seconds": 5.0}]}
        result = estimate_reassembly_cost(project)
        assert result["shot_count"] == 1
        assert result["total_source_duration_s"] == 5.0

    def test_duration_falls_back_to_scene_then_default(self):
        # Take has no duration_s metadata; scene has duration_seconds=4.0.
        shots = [
            {"id": "shot_a", "approved_final_take_id": "take_a",
             "motion_takes": [{"id": "take_a", "kind": "motion"}]},
        ]
        project = {"scenes": [{"id": "s1", "shots": shots, "duration_seconds": 4.0}]}
        result = estimate_reassembly_cost(project)
        assert result["total_source_duration_s"] == 4.0

    def test_seconds_is_a_float(self):
        result = estimate_reassembly_cost({})
        assert isinstance(result["seconds"], float)
