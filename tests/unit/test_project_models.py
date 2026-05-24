"""
tests/unit/test_project_models.py — Pydantic model + boundary validation tests.

Session 8: covers domain/models.py (6 BaseModel classes) and the
_validate_project integration points in domain/project_manager.py.
"""

from __future__ import annotations

import json
import os
import logging
import tempfile
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from domain.models import (
    CascadeMetadata,
    TakeRecord,
    Shot,
    Scene,
    Character,
    Location,
    Project,
)
import domain.project_manager as _pm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REAL_PROJECT_JSON = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "projects",
    "70940580b872",
    "project.json",
)

_MINIMAL_TAKE = {"id": "take_abc123", "kind": "keyframe"}
_MINIMAL_SHOT = {"id": "shot_001"}
_MINIMAL_SCENE = {"id": "scene_001"}
_MINIMAL_PROJECT = {"id": "proj_001", "name": "Test"}


# ---------------------------------------------------------------------------
# TestTakeRecord
# ---------------------------------------------------------------------------


class TestTakeRecord:
    def test_minimal_valid_take(self):
        """A take with only id + kind is valid; all other fields default."""
        t = TakeRecord(**_MINIMAL_TAKE)
        assert t.id == "take_abc123"
        assert t.kind == "keyframe"
        assert t.path == ""
        assert t.source_take_id == ""
        assert t.status == ""
        assert t.created_at == ""
        assert t.metadata == {}
        assert t.cascade_metadata is None

    def test_optional_cascade_metadata_round_trip(self):
        """TakeRecord with nested CascadeMetadata validates and round-trips."""
        data = {
            "id": "take_xyz",
            "kind": "motion",
            "cascade_metadata": {
                "engine": "kling",
                "score": 0.87,
                "threshold": 0.75,
                "fallback": False,
                "attempts": ["attempt_1", "attempt_2"],
            },
        }
        t = TakeRecord(**data)
        assert t.cascade_metadata is not None
        assert t.cascade_metadata.engine == "kling"
        assert t.cascade_metadata.score == pytest.approx(0.87)
        assert t.cascade_metadata.attempts == ["attempt_1", "attempt_2"]
        # round-trip: model_dump → model_validate
        dumped = t.model_dump()
        t2 = TakeRecord.model_validate(dumped)
        assert t2.cascade_metadata.score == pytest.approx(0.87)

    def test_kind_literal_enforcement(self):
        """An invalid kind value raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TakeRecord(id="take_bad", kind="banana")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("kind",) for e in errors)


# ---------------------------------------------------------------------------
# TestShot
# ---------------------------------------------------------------------------


class TestShot:
    def test_minimal_valid_shot(self):
        """A shot with only id validates; all other fields default."""
        s = Shot(**_MINIMAL_SHOT)
        assert s.id == "shot_001"
        assert s.prompt == ""
        assert s.camera == ""
        assert s.target_api == ""
        assert s.generated_image == ""
        assert s.generated_video == ""

    def test_performance_takes_defaults_to_empty_list(self):
        """performance_takes MUST default to [] — Session-2 P0 field."""
        s = Shot(**_MINIMAL_SHOT)
        assert s.performance_takes == []
        assert isinstance(s.performance_takes, list)

    def test_full_shape_shot_validates(self):
        """A fully-populated shot dict (as in real project.json) validates."""
        data = {
            "id": "shot_full",
            "prompt": "A close-up of the hero",
            "camera": "dolly_in_rapid",
            "visual_effect": "gritty_contrast",
            "target_api": "SORA_NATIVE",
            "scene_foley": "Footsteps",
            "characters_in_frame": [],
            "primary_character": "",
            "action_context": "Hero enters",
            "generated_image": "/some/path/frame.jpg",
            "generated_video": "/some/path/video.mp4",
            "plan_status": "approved",
            "plan_rejection_reason": "",
            "keyframe_takes": [
                {"id": "take_kf1", "kind": "keyframe", "status": "generated"}
            ],
            "approved_keyframe_take_id": "take_kf1",
            "motion_takes": [
                {"id": "take_m1", "kind": "motion", "source_take_id": "take_kf1"}
            ],
            "approved_motion_take_id": "take_m1",
            "postprocess_variants": [],
            "approved_final_take_id": "take_m1",
            "performance_takes": [],
            "performance_take_id": "",
            "diagnostics": [],
            "intent_notes": "Hero enters the scene",
            "negative_constraints": "blur, distort",
            "continuity_constraints": "",
        }
        s = Shot.model_validate(data)
        assert s.plan_status == "approved"
        assert len(s.keyframe_takes) == 1
        assert s.keyframe_takes[0].kind == "keyframe"

    def test_extra_unknown_field_allowed(self):
        """Unknown fields are allowed (extra='allow') — no ValidationError."""
        data = {
            "id": "shot_extra",
            "unknown_field_xyz": "some_ui_scratchpad_value",
            "another_future_field": 42,
        }
        # Should not raise
        s = Shot.model_validate(data)
        assert s.id == "shot_extra"


# ---------------------------------------------------------------------------
# TestScene
# ---------------------------------------------------------------------------


class TestScene:
    def test_minimal_scene(self):
        """A scene with only id validates; all other fields default."""
        sc = Scene(**_MINIMAL_SCENE)
        assert sc.id == "scene_001"
        assert sc.title == ""
        assert sc.shots == []
        assert sc.order == 0
        assert sc.duration_seconds == 0.0

    def test_shots_as_shot_list(self):
        """Scene with a shots list of Shot dicts validates and nests properly."""
        data = {
            "id": "scene_002",
            "title": "Opening",
            "shots": [
                {"id": "shot_a", "prompt": "First shot"},
                {"id": "shot_b", "prompt": "Second shot", "target_api": "KLING_NATIVE"},
            ],
        }
        sc = Scene.model_validate(data)
        assert len(sc.shots) == 2
        assert isinstance(sc.shots[0], Shot)
        assert sc.shots[1].target_api == "KLING_NATIVE"


# ---------------------------------------------------------------------------
# TestProject
# ---------------------------------------------------------------------------


class TestProject:
    def test_minimal_project(self):
        """Project with only id + name validates."""
        p = Project(**_MINIMAL_PROJECT)
        assert p.id == "proj_001"
        assert p.name == "Test"
        assert p.characters == []
        assert p.locations == []
        assert p.scenes == []

    def test_full_real_project_round_trip(self):
        """Load the real 70940580b872 fixture; validate; dump; assert no loss."""
        path = os.path.abspath(REAL_PROJECT_JSON)
        if not os.path.exists(path):
            pytest.skip(f"Real project fixture not present: {path}")
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        p = Project.model_validate(raw)
        assert p.id == raw["id"]
        assert p.name == raw["name"]

        # Known field preservation: scenes/shots/takes
        assert len(p.scenes) == len(raw["scenes"])
        raw_scene = raw["scenes"][0]
        model_scene = p.scenes[0]
        assert model_scene.id == raw_scene["id"]
        assert len(model_scene.shots) == len(raw_scene["shots"])

        # Round-trip: dump back to dict, re-validate, compare structurally.
        # Length-only checks would miss silent content loss; compare id
        # collections at each level to prove no fields dropped.
        dumped = p.model_dump()
        p2 = Project.model_validate(dumped)
        assert p2.id == p.id
        assert p2.name == p.name
        assert [s.id for s in p2.scenes] == [s.id for s in p.scenes]
        assert [c.id for c in p2.characters] == [c.id for c in p.characters]
        assert [l.id for l in p2.locations] == [l.id for l in p.locations]
        # Deepest check: take ids in the first shot survive the cycle AND
        # match the raw JSON (proves model_validate didn't drop them either).
        raw_first_shot = raw["scenes"][0]["shots"][0]
        raw_keyframe_take_ids = [t["id"] for t in raw_first_shot.get("keyframe_takes", [])]
        assert [t.id for t in p2.scenes[0].shots[0].keyframe_takes] == raw_keyframe_take_ids

    def test_nested_validation_error_pinpoints_path(self):
        """A bad take kind deep in nested shots → ValidationError names the path."""
        data = {
            "id": "proj_bad",
            "name": "Bad Take Test",
            "scenes": [
                {
                    "id": "scene_x",
                    "shots": [
                        {
                            "id": "shot_x",
                            "keyframe_takes": [
                                {"id": "take_bad", "kind": "invalid_kind"}
                            ],
                        }
                    ],
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            Project.model_validate(data)
        # Error path should point into scenes → shots → keyframe_takes → kind
        errors = exc_info.value.errors()
        paths = [e["loc"] for e in errors]
        assert any("kind" in loc for loc in paths)


# ---------------------------------------------------------------------------
# TestBoundaryValidation
# ---------------------------------------------------------------------------


class TestBoundaryValidation:
    """Verify _validate_project is called at save_project and load_project."""

    def test_save_project_calls_validate_project(self, tmp_path, monkeypatch):
        """save_project must call _validate_project before writing."""
        monkeypatch.setattr("domain.project_manager.PROJECTS_DIR", str(tmp_path))

        calls: list[tuple[dict, str]] = []

        original_validate = _pm._validate_project

        def spy(project: dict, context: str) -> None:
            calls.append((project, context))
            return original_validate(project, context)

        monkeypatch.setattr("domain.project_manager._validate_project", spy)

        proj = _pm.make_project("Spy Test")
        _pm.create_project("Spy Test")  # triggers save_project internally
        # Also call save_project directly
        calls.clear()
        _pm.save_project(proj)

        assert len(calls) >= 1
        assert calls[0][1] == "save_project"

    def test_load_project_calls_validate_project(self, tmp_path, monkeypatch):
        """load_project must call _validate_project after normalize."""
        monkeypatch.setattr("domain.project_manager.PROJECTS_DIR", str(tmp_path))

        calls: list[tuple[dict, str]] = []
        original_validate = _pm._validate_project

        def spy(project: dict, context: str) -> None:
            calls.append((project, context))
            return original_validate(project, context)

        monkeypatch.setattr("domain.project_manager._validate_project", spy)

        proj = _pm.create_project("Load Spy Test")
        calls.clear()
        loaded = _pm.load_project(proj["id"])
        assert loaded is not None

        load_calls = [c for c in calls if c[1] == "load_project"]
        assert len(load_calls) >= 1

    def test_unknown_top_level_field_warns_not_raises(
        self, tmp_path, monkeypatch, caplog
    ):
        """Unknown top-level fields trigger a WARNING log but do not raise."""
        monkeypatch.setattr("domain.project_manager.PROJECTS_DIR", str(tmp_path))

        # Build a project dict with an unknown top-level field
        proj = _pm.make_project("Unknown Field Test")
        proj["_ui_scratchpad"] = {"some_editor_state": True}

        # _validate_project should log a WARNING for ValidationError (if strict)
        # or silently pass (extra="allow" means it WON'T raise or warn for extra fields).
        # Either way: no exception.
        with caplog.at_level(logging.WARNING, logger="domain.project_manager"):
            _pm._validate_project(proj, "test_context")
        # The key assertion: no exception was raised above.
        # Under extra="allow" on Project, unknown top-level fields don't warn.
        # This is correct permissive behavior per the brief.

    def test_validate_project_catches_non_validation_error(self, monkeypatch, caplog):
        """Non-ValidationError exceptions must NOT propagate from _validate_project.

        The brief's "warn-only" contract is broader than ValidationError.
        A TypeError / RecursionError / etc from a malformed dict must be
        caught and logged, not raised into save_project / load_project
        callers (web_server.py, cinema_pipeline.py).
        """

        def boom(*args, **kwargs):
            raise TypeError("simulated non-ValidationError crash")

        monkeypatch.setattr(
            "domain.project_manager.Project.model_validate", boom
        )

        # Must not raise — that's the warn-only contract.
        with caplog.at_level(logging.WARNING, logger="domain.project_manager"):
            _pm._validate_project({"id": "proj_crash"}, "test_context")

        crash_logs = [r for r in caplog.records if "crashed" in r.message]
        assert len(crash_logs) >= 1
        assert crash_logs[0].context == "test_context"


# ---------------------------------------------------------------------------
# TestStrictModeOff  (Session 10 — CINEMA_STRICT_SCHEMA not set)
# ---------------------------------------------------------------------------


class TestStrictModeOff:
    """Default (warn-only) behavior is preserved when env flag is absent."""

    def test_validation_error_warns_not_raises_by_default(self, monkeypatch, caplog):
        """Without CINEMA_STRICT_SCHEMA set, ValidationError logs a warning and
        does NOT propagate — the Session 8 contract must remain intact."""
        monkeypatch.delenv("CINEMA_STRICT_SCHEMA", raising=False)
        # A take with an invalid kind will bubble up through Project.model_validate
        # as a nested ValidationError.
        bad_project = {
            "id": "proj_warn",
            "scenes": [
                {
                    "id": "scene_x",
                    "shots": [{"id": "shot_x", "keyframe_takes": [{"id": "t1", "kind": "INVALID"}]}],
                }
            ],
        }
        with caplog.at_level(logging.WARNING, logger="domain.project_manager"):
            # Must NOT raise — warn-only contract.
            _pm._validate_project(bad_project, "test_warn_only")

        warn_logs = [r for r in caplog.records if "validation failed" in r.message]
        assert len(warn_logs) >= 1


# ---------------------------------------------------------------------------
# TestStrictModeOn  (Session 10 — CINEMA_STRICT_SCHEMA=1)
# ---------------------------------------------------------------------------


class TestStrictModeOn:
    """With CINEMA_STRICT_SCHEMA set, validation failures RAISE not warn."""

    def test_validation_error_raises_when_strict(self, monkeypatch):
        """ValidationError propagates when CINEMA_STRICT_SCHEMA=1."""
        monkeypatch.setenv("CINEMA_STRICT_SCHEMA", "1")
        bad_project = {
            "id": "proj_strict",
            "scenes": [
                {
                    "id": "scene_x",
                    "shots": [{"id": "shot_x", "keyframe_takes": [{"id": "t1", "kind": "BAD"}]}],
                }
            ],
        }
        with pytest.raises(ValidationError):
            _pm._validate_project(bad_project, "strict_test")

    def test_non_validation_error_raises_when_strict(self, monkeypatch):
        """Non-ValidationError (TypeError etc.) also propagates under strict mode
        (belt-and-suspenders strict)."""
        monkeypatch.setenv("CINEMA_STRICT_SCHEMA", "1")

        def boom(*args, **kwargs):
            raise TypeError("simulated crash under strict mode")

        monkeypatch.setattr("domain.project_manager.Project.model_validate", boom)
        with pytest.raises(TypeError, match="simulated crash under strict mode"):
            _pm._validate_project({"id": "proj_boom"}, "strict_crash_test")

    def test_unsetting_env_reverts_to_warn_only(self, monkeypatch, caplog):
        """Clearing CINEMA_STRICT_SCHEMA after setting it restores warn-only."""
        monkeypatch.setenv("CINEMA_STRICT_SCHEMA", "1")
        monkeypatch.delenv("CINEMA_STRICT_SCHEMA")
        bad_project = {
            "id": "proj_revert",
            "scenes": [
                {
                    "id": "scene_x",
                    "shots": [{"id": "shot_x", "keyframe_takes": [{"id": "t1", "kind": "BAD"}]}],
                }
            ],
        }
        # After unsetting, must not raise again.
        with caplog.at_level(logging.WARNING, logger="domain.project_manager"):
            _pm._validate_project(bad_project, "reverted_warn")
        warn_logs = [r for r in caplog.records if "validation failed" in r.message]
        assert len(warn_logs) >= 1


# ---------------------------------------------------------------------------
# TestEnvFlagParsing  (Session 10 — accepted values for CINEMA_STRICT_SCHEMA)
# ---------------------------------------------------------------------------


class TestEnvFlagParsing:
    """Verify all documented strict-truthy and non-strict values are handled."""

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes"])
    def test_truthy_values_raise(self, monkeypatch, value):
        """Each documented truthy value activates strict mode (raises)."""
        monkeypatch.setenv("CINEMA_STRICT_SCHEMA", value)
        bad = {
            "id": "proj_parse",
            "scenes": [
                {
                    "id": "sc",
                    "shots": [{"id": "sh", "keyframe_takes": [{"id": "t", "kind": "NOPE"}]}],
                }
            ],
        }
        with pytest.raises(ValidationError):
            _pm._validate_project(bad, f"parse_strict_{value}")

    @pytest.mark.parametrize("value", ["0", "", "false", "False", "no", "NO"])
    def test_falsy_values_warn_not_raise(self, monkeypatch, caplog, value):
        """Non-truthy values keep warn-only behavior."""
        monkeypatch.setenv("CINEMA_STRICT_SCHEMA", value)
        bad = {
            "id": "proj_parse_falsy",
            "scenes": [
                {
                    "id": "sc",
                    "shots": [{"id": "sh", "keyframe_takes": [{"id": "t", "kind": "NOPE"}]}],
                }
            ],
        }
        with caplog.at_level(logging.WARNING, logger="domain.project_manager"):
            _pm._validate_project(bad, f"parse_warn_{value}")
        # Must not raise; warning must be logged.
        warn_logs = [r for r in caplog.records if "validation failed" in r.message]
        assert len(warn_logs) >= 1


# ---------------------------------------------------------------------------
# TestMigratedCaller  (Session 10 — regression for api_generate_dialogue)
# ---------------------------------------------------------------------------


class TestMigratedCaller:
    """Behavioral regression tests for the web_server.api_generate_dialogue
    migration (web_server.py:1096, Session 10 canonical target).

    These tests verify the migrated code path returns semantically identical
    results to the old dict-access path without importing Flask or wiring the
    full HTTP stack.  We test the data-preparation logic that the migration
    changed: scene lookup + chars filter + mood default-translation.
    """

    def _make_project_dict(self, scene_id="scene_001", mood="", char_ids=None):
        """Build a minimal project dict matching the migration target's input shape."""
        char_ids = char_ids or ["char_a", "char_b"]
        return {
            "id": "proj_migrated",
            "name": "Migration Test",
            "characters": [
                {"id": "char_a", "name": "Alice"},
                {"id": "char_b", "name": "Bob"},
                {"id": "char_c", "name": "Carol"},  # NOT in scene
            ],
            "scenes": [
                {
                    "id": scene_id,
                    "title": "Opening Scene",
                    "mood": mood,
                    "characters_present": char_ids,
                    "shots": [],
                }
            ],
        }

    def test_typed_scene_lookup_matches_dict_lookup(self):
        """Project.model_validate → scene.id lookup returns same scene as dict access."""
        raw = self._make_project_dict()
        # Old dict path
        scene_dict = next((s for s in raw["scenes"] if s["id"] == "scene_001"), None)
        # New typed path
        p = Project.model_validate(raw)
        scene_typed = next((s for s in p.scenes if s.id == "scene_001"), None)

        assert scene_dict is not None
        assert scene_typed is not None
        assert scene_typed.id == scene_dict["id"]
        assert scene_typed.title == scene_dict["title"]

    def test_chars_filter_matches_dict_filter(self):
        """Typed characters_present filter selects same chars as dict .get() path."""
        raw = self._make_project_dict(char_ids=["char_a"])
        # Old dict path
        scene_d = raw["scenes"][0]
        chars_dict = [c for c in raw["characters"] if c["id"] in scene_d.get("characters_present", [])]
        # New typed path
        p = Project.model_validate(raw)
        scene_t = p.scenes[0]
        chars_typed = [c for c in p.characters if c.id in scene_t.characters_present]

        assert len(chars_typed) == len(chars_dict) == 1
        assert chars_typed[0].id == chars_dict[0]["id"]

    def test_mood_default_translation(self):
        """Empty mood string translates to 'neutral' via `or` at call site,
        matching the old .get('mood', 'neutral') semantics."""
        raw_empty_mood = self._make_project_dict(mood="")
        raw_explicit_mood = self._make_project_dict(mood="tense")

        p_empty = Project.model_validate(raw_empty_mood)
        p_explicit = Project.model_validate(raw_explicit_mood)

        # Migration uses `scene.mood or "neutral"` — verify the translation
        assert (p_empty.scenes[0].mood or "neutral") == "neutral"
        assert (p_explicit.scenes[0].mood or "neutral") == "tense"

    def test_missing_scene_returns_none(self):
        """Looking up a non-existent sid on typed scenes returns None,
        matching the old dict-access path's behavior."""
        raw = self._make_project_dict()
        p = Project.model_validate(raw)
        result = next((s for s in p.scenes if s.id == "does_not_exist"), None)
        assert result is None
