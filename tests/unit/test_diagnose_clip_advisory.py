"""Unit tests for Task 4 (T6): diagnose_clip enriches its result with
a structured remediation_advisory and folds the suggested negative prompt
into the regenerate recommendation when identity validation fails.

Offline — no GPU, no pod, no API calls.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from cinema.shots.controller import ShotController


def _build_diagnose_controller(tmp_path):
    """Minimal ShotController that can run diagnose_clip up to the identity-
    validation seam.  We wire a single-scene/single-shot project with one
    character ('char_1') and a real image file so os.path.exists returns True.
    """
    img_path = str(tmp_path / "keyframe.jpg")
    with open(img_path, "wb") as fh:
        fh.write(b"img")

    shot = {
        "id": "shot_1_0",
        "plan_status": "approved",
        "characters_in_frame": [],
        "camera": "medium",
        "target_api": "AUTO",
        "approved_keyframe_take_id": "take_k1",
        "keyframe_takes": [{"id": "take_k1", "kind": "keyframe", "path": img_path}],
    }
    scene = {
        "id": "scene_1",
        "title": "T",
        "action": "A",
        "location_id": "loc_1",
        "shots": [shot],
        "characters_present": ["char_1"],
    }
    project = {
        "id": "proj_1",
        "scenes": [scene],
        "characters": [{"id": "char_1", "name": "Alice"}],
        "objects": [],
        "locations": [],
        "global_settings": {},
    }

    host = MagicMock()
    host._refresh_project_snapshot.return_value = project
    # _candidate_take returns the keyframe take dict
    host._candidate_take.return_value = {
        "id": "take_k1",
        "kind": "keyframe",
        "path": img_path,
    }
    # _resolve_take_path also returns the image path for the approved keyframe
    host._resolve_take_path.return_value = img_path
    host._latest_take.return_value = {"path": img_path}

    lifecycle = MagicMock()
    runstate = MagicMock()
    runstate.shot_results = {}
    core = MagicMock()
    core.project = project
    core.project_dir = "/tmp/fake_project"

    ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
    return ctrl, project, img_path


def _build_failed_id_result(char_id: str = "char_1"):
    """Build a failed IdentityValidationResult for the given character."""
    from identity.types import (
        CharacterIdentityResult,
        FailureReason,
        IdentityValidationResult,
    )

    char_diag = CharacterIdentityResult(
        character_id=char_id,
        character_name="Alice",
        best_similarity=0.40,
        mean_similarity=0.35,
        min_similarity=0.30,
        frame_results=[],
        matched=False,
        primary_failure_reason=FailureReason.WRONG_PERSON,
        suggested_pulid_adjustment=0.05,
    )
    return IdentityValidationResult(
        passed=False,
        overall_score=0.40,
        character_results={char_id: char_diag},
        frames_sampled=1,
        video_duration_seconds=0.0,
        shot_type="medium",
        threshold_used=0.70,
    )


class TestDiagnoseClipAdvisory:
    """T6 Task 4: diagnose_clip attaches remediation_advisory + enriches
    regenerate recommendation when identity gate fails."""

    def test_advisory_and_negative_prompt_on_identity_failure(self, tmp_path):
        ctrl, project, img_path = _build_diagnose_controller(tmp_path)
        failed_id_result = _build_failed_id_result("char_1")

        mock_validator = MagicMock()
        mock_validator.validate_image.return_value = failed_id_result

        with (
            patch("cinema.shots.controller.get_reference_image", return_value="/fake/ref.jpg"),
            patch("phase_c_vision._get_shared_validator", return_value=mock_validator),
        ):
            result = ctrl.diagnose_clip("shot_1_0")

        # Basic shape
        assert "error" not in result, f"unexpected error: {result.get('error')}"
        assert result["shot_id"] == "shot_1_0"

        # T6: structured advisory must be present
        assert "remediation_advisory" in result, (
            "T6 Task 4 wire missing: 'remediation_advisory' not in diagnose_clip result"
        )
        adv = result["remediation_advisory"]
        assert adv["failure_reason"] == "wrong_person", f"got {adv!r}"
        assert adv["source"] == "deterministic", f"got {adv!r}"
        assert adv["suggested_negative_prompt"], (
            "suggested_negative_prompt should be non-empty for 'wrong_person'"
        )

        # T6: regenerate recommendation reason must mention negative prompt
        regen_recs = [r for r in result["recommendations"] if r.get("tool") == "regenerate"]
        assert regen_recs, "expected at least one 'regenerate' recommendation"
        assert "negative prompt" in regen_recs[0]["reason"], (
            f"Expected 'negative prompt' in reason, got: {regen_recs[0]['reason']!r}"
        )

        # Existing pre-T6 recommendations still present (exactly once each)
        face_swap_recs = [r for r in result["recommendations"] if r.get("tool") == "face_swap"]
        assert len(face_swap_recs) == 1, "expected exactly one face_swap recommendation"
        assert len(regen_recs) == 1, "expected exactly one regenerate recommendation"

    def test_no_advisory_when_identity_passes(self, tmp_path):
        """A passing identity result must NOT add remediation_advisory."""
        from identity.types import (
            CharacterIdentityResult,
            FailureReason,
            IdentityValidationResult,
        )

        ctrl, project, img_path = _build_diagnose_controller(tmp_path)

        char_diag = CharacterIdentityResult(
            character_id="char_1",
            character_name="Alice",
            best_similarity=0.85,
            mean_similarity=0.82,
            min_similarity=0.78,
            frame_results=[],
            matched=True,
            primary_failure_reason=FailureReason.PASSED,
            suggested_pulid_adjustment=0.0,
        )
        passing_id_result = IdentityValidationResult(
            passed=True,
            overall_score=0.85,
            character_results={"char_1": char_diag},
            frames_sampled=1,
            video_duration_seconds=0.0,
            shot_type="medium",
            threshold_used=0.70,
        )

        mock_validator = MagicMock()
        mock_validator.validate_image.return_value = passing_id_result

        with (
            patch("cinema.shots.controller.get_reference_image", return_value="/fake/ref.jpg"),
            patch("phase_c_vision._get_shared_validator", return_value=mock_validator),
        ):
            result = ctrl.diagnose_clip("shot_1_0")

        assert "error" not in result
        assert "remediation_advisory" not in result, (
            "remediation_advisory must NOT be set when identity passes"
        )
        assert not any(r.get("tool") == "face_swap" for r in result["recommendations"]), (
            "face_swap must not appear when identity passes"
        )
