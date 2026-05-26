"""Regression tests for ``CinemaPipeline._refresh_project_snapshot``.

Specifically covers the I-1 partial-state corruption window flagged by
operator Lane V #9 (cycle 11; verification-report at
``coordination/mailbox/sent/2026-05-26T13-31-29Z-operator-to-director-verification-report.md``).

I-1 root cause (pre-fix): the method did
``self.project.clear() → update(latest) → model_validate(self.project)``.
If ``model_validate`` raised ``ValidationError`` on a malformed ``latest``,
``self.project`` was already swapped to the malformed state but the
tracker indices (``self.continuity.character_tracker.characters`` +
``self.continuity.location_persistence.locations``) never rebuilt — leaving
a partial-reload state where the tracker indices keyed against the prior
state's IDs but ``self.project`` held the new (malformed) dict.

I-1 fix (post-fix): validate FIRST on the loaded dict; only swap
``self.project`` if validation passes. If validation raises, the
``self.project`` mutation never happens — caller sees ValidationError
with the prior state intact.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import ValidationError

import cinema_pipeline


def _make_minimal_pipeline_stub(initial_project: dict) -> SimpleNamespace:
    """Build a minimal pipeline-like stub with the attributes
    ``_refresh_project_snapshot`` touches.

    SimpleNamespace gives us mutable attribute access without the
    heavyweight CinemaPipeline construction (which would require
    on-disk project, lifecycle, runstate, etc.).
    """
    return SimpleNamespace(
        project=initial_project,
        continuity=SimpleNamespace(
            project=None,
            character_tracker=SimpleNamespace(
                project=None,
                characters={"snapshot-marker": {"name": "initial"}},
            ),
            location_persistence=SimpleNamespace(
                project=None,
                locations={"snapshot-marker": {"name": "initial"}},
            ),
        ),
        director=SimpleNamespace(project=None),
    )


def _minimal_valid_project() -> dict:
    """A schema-valid minimal Project dict.

    Includes the required ``id`` field plus empty lists for
    ``scenes`` / ``characters`` / ``locations`` so Pydantic's
    list-field validation passes.
    """
    return {
        "id": "test-project",
        "name": "Test Project",
        "scenes": [],
        "characters": [],
        "locations": [],
    }


class TestPartialStateOnValidateError:
    """The I-1 regression: validation failure must NOT mutate state."""

    def test_state_preserved_when_validation_raises(self):
        """Malformed ``latest`` dict raises ValidationError; ``self.project``
        and tracker indices stay intact."""
        initial = _minimal_valid_project()
        initial["name"] = "Initial Marker"  # distinctive value for the assertion
        stub = _make_minimal_pipeline_stub(initial)

        # Malformed: ``scenes`` must be a list per Project.scenes: List[Scene]
        malformed = {
            "id": "test-project",
            "name": "Should Not Land",
            "scenes": "not-a-list",
            "characters": [],
            "locations": [],
        }

        with patch.object(cinema_pipeline, "load_project", return_value=malformed):
            with pytest.raises(ValidationError):
                cinema_pipeline.CinemaPipeline._refresh_project_snapshot(stub)

        # I-1 regression: state preserved.
        assert stub.project["name"] == "Initial Marker"
        assert stub.project["scenes"] == []
        assert stub.continuity.character_tracker.characters == {
            "snapshot-marker": {"name": "initial"}
        }
        assert stub.continuity.location_persistence.locations == {
            "snapshot-marker": {"name": "initial"}
        }
        # The cross-attribute project-pointer also stays at the initial
        # value (None per the stub) because the .project = self.project
        # rebind happens AFTER validation in the fixed code.
        assert stub.continuity.project is None
        assert stub.director.project is None

    def test_state_updated_on_successful_validation(self):
        """Sanity-pair to the regression: valid ``latest`` correctly
        updates state and rebuilds tracker indices."""
        initial = _minimal_valid_project()
        initial["name"] = "Initial Marker"
        stub = _make_minimal_pipeline_stub(initial)

        new = _minimal_valid_project()
        new["name"] = "Updated Marker"
        new["characters"] = [
            {"id": "char_a", "name": "Alice", "voice_id": "voice_alice"},
        ]
        new["locations"] = [
            {"id": "loc_a", "name": "Park"},
        ]

        with patch.object(cinema_pipeline, "load_project", return_value=new):
            result = cinema_pipeline.CinemaPipeline._refresh_project_snapshot(stub)

        # Method returns the swapped self.project on success.
        assert result is stub.project
        assert stub.project["name"] == "Updated Marker"
        # Tracker indices rebuilt against new project's IDs.
        assert "char_a" in stub.continuity.character_tracker.characters
        assert "snapshot-marker" not in stub.continuity.character_tracker.characters
        assert "loc_a" in stub.continuity.location_persistence.locations
        # Value-preserving variant: indexed values ARE the raw dict
        # references from self.project["characters"] / ["locations"],
        # not Pydantic model_dump output (per part-10 pattern variant).
        assert stub.continuity.character_tracker.characters["char_a"] is stub.project["characters"][0]
        assert stub.continuity.location_persistence.locations["loc_a"] is stub.project["locations"][0]
        # Project pointer re-bound on the cross-class attributes.
        assert stub.continuity.project is stub.project
        assert stub.director.project is stub.project

    def test_returns_none_when_load_project_returns_none(self):
        """``load_project`` returning ``None`` (project deleted /
        timeout / etc.) returns early without mutating state."""
        initial = _minimal_valid_project()
        initial["name"] = "Initial Marker"
        stub = _make_minimal_pipeline_stub(initial)

        with patch.object(cinema_pipeline, "load_project", return_value=None):
            result = cinema_pipeline.CinemaPipeline._refresh_project_snapshot(stub)

        assert result is None
        # State unchanged.
        assert stub.project["name"] == "Initial Marker"
        assert stub.continuity.character_tracker.characters == {
            "snapshot-marker": {"name": "initial"}
        }
