"""Unit tests for the HiDream-I1 image-engine routing wire.

Context: the prompt optimizer emits `suggested_image_api` (FLUX_DEV |
HIDREAM_I1 | SD3_5_LARGE; llm/prompt_optimizer.py). The controller forwards
it into `shot_hint["image_api"]` (cinema/shots/controller.py::
generate_keyframe_take). The HiDream-swap consumer end of this wire lived in
quality_max.py's `_swap_to_hidream` (retired WS1 Task 4, no production
replacement); these tests cover the (still-live) forward + its M-2 guard.

Offline — no GPU, no pod, no API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _build_keyframe_controller():
    """A minimal ShotController that can run generate_keyframe_take up to the
    generate_ai_broll seam (mirrors test_iterate_endpoint._build_controller).

    The keyframe shot is plan-approved so the method proceeds; the image write is
    short-circuited by a non-existent img_path (os.path.exists -> False) so the
    method returns right after the seam without touching identity validation,
    cost tracking, or the project mutation."""
    from cinema.shots.controller import ShotController

    shot = {
        "id": "shot_1_0",
        "plan_status": "approved",
        "characters_in_frame": [],
        "camera": "zoom_in_slow",
        "target_api": "AUTO",
    }
    scene = {"id": "scene_1", "title": "T", "action": "A", "location_id": None, "shots": [shot]}
    project = {
        "id": "proj_1",
        "scenes": [scene],
        "characters": [],
        "objects": [],
        "locations": [],
        "global_settings": {},
    }

    host = MagicMock()
    host._refresh_project_snapshot.return_value = project
    lifecycle = MagicMock()
    runstate = MagicMock()
    runstate.shot_results = {}
    core = MagicMock()
    core.project = project
    core.project_dir = "/tmp/fake_project"
    core.continuity.enhance_shot_prompt.return_value = {"prompt": "base prompt", "continuity_config": {}}
    core.cost_tracker = MagicMock()
    # Pre-spend budget gate (FOLLOW-UP (a)): an unconfigured MagicMock's
    # would_exceed(...) return value is itself a truthy MagicMock, which
    # would spuriously trip the gate before this helper's seam is reached.
    core.cost_tracker.would_exceed.return_value = False

    ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
    ctrl._take_output_path = MagicMock(return_value="/nonexistent/keyframe.jpg")
    ctrl._resolve_previous_approved_keyframe = MagicMock(return_value="")
    ctrl._mutate_shot = MagicMock()
    # Immutable artifact persistence is covered by test_artifact_indexing.py.
    # Keep this routing fixture at its intended seam while honoring the current
    # controller contract: finalization returns (stored_take, artifact_error).
    ctrl._finalize_take_artifact_version = MagicMock(
        side_effect=lambda _shot_id, _kind, stored_take: (stored_take, None)
    )
    return ctrl, project


class TestSuggestedImageApiForwarding:
    """The controller seam feeding quality_max's HiDream gate. After Lane V #20
    M-2 (d73eebb), generate_keyframe_take resolves shot_hint["image_api"] with a
    guard: a user-pinned shot["image_api"] wins, else the optimizer's
    suggested_image_api, else None. The consumer (_swap_to_hidream) is covered
    above; these cover the (previously-untested) forward + its M-2 guard."""

    def test_user_pinned_image_api_wins_over_suggestion(self):
        # M-2 guard: a user pin on shot["image_api"] must beat the optimizer's
        # suggestion (mirrors the video-routing target_api AUTO guard).
        ctrl, project = _build_keyframe_controller()
        project["global_settings"]["prompt_optimizer_enabled"] = True
        project["scenes"][0]["shots"][0]["image_api"] = "FLUX_DEV"
        opt_spec = {"suggested_image_api": "HIDREAM_I1", "image_prompt": "optimized prompt"}

        with patch("cinema.shots.controller.generate_ai_broll") as mock_broll, \
             patch("llm.prompt_optimizer.optimize_shot_prompt", return_value=opt_spec):
            ctrl.generate_keyframe_take("scene_1", "shot_1_0", positive_prompt="a test prompt")

        mock_broll.assert_called_once()
        shot_hint = mock_broll.call_args.kwargs["shot_hint"]
        assert shot_hint["image_api"] == "FLUX_DEV"

    def test_forwards_suggested_image_api_into_shot_hint(self):
        ctrl, project = _build_keyframe_controller()
        project["global_settings"]["prompt_optimizer_enabled"] = True
        opt_spec = {"suggested_image_api": "HIDREAM_I1", "image_prompt": "optimized prompt"}

        with patch("cinema.shots.controller.generate_ai_broll") as mock_broll, \
             patch("llm.prompt_optimizer.optimize_shot_prompt", return_value=opt_spec):
            ctrl.generate_keyframe_take("scene_1", "shot_1_0", positive_prompt="a test prompt")

        mock_broll.assert_called_once()
        shot_hint = mock_broll.call_args.kwargs["shot_hint"]
        assert shot_hint["image_api"] == "HIDREAM_I1"

    def test_shot_hint_image_api_none_when_optimizer_disabled(self):
        # prompt_optimizer_enabled defaults off -> opt_spec stays None -> the
        # gate reads None and HiDream never fires (stays on FLUX).
        ctrl, project = _build_keyframe_controller()

        with patch("cinema.shots.controller.generate_ai_broll") as mock_broll:
            ctrl.generate_keyframe_take("scene_1", "shot_1_0", positive_prompt="a test prompt")

        mock_broll.assert_called_once()
        shot_hint = mock_broll.call_args.kwargs["shot_hint"]
        assert shot_hint["image_api"] is None


class TestCanonicalIdentityAnchorPrecedence:
    """Slice 7 defect 2: the user-approved canonical identity_anchor (built by
    domain.character_manager.build_identity_anchor — the character's
    immutable 'DNA', wired into continuity_config["identity_anchor"] via
    get_identity_anchor) must win over the prompt optimizer's own invented
    identity_anchor (llm/prompt_optimizer.py's LLM guess at face/hair/build,
    or an object-specific anchor). The optimizer's identity_anchor stays
    advisory: only used when the shot carries no canonical identity at all."""

    def test_canonical_identity_anchor_wins_over_optimizer_invented_one(self):
        ctrl, project = _build_keyframe_controller()
        project["global_settings"]["prompt_optimizer_enabled"] = True
        canonical = "Alice: straight blonde hair, round wire-rimmed glasses, slim build"
        ctrl._core.continuity.enhance_shot_prompt.return_value = {
            "prompt": "base prompt",
            "continuity_config": {"identity_anchor": canonical},
        }
        opt_spec = {
            "image_prompt": "optimized prompt",
            # Optimizer-invented and WRONG relative to the canonical record —
            # must never reach generate_ai_broll.
            "identity_anchor": "a woman with short curly red hair",
        }

        with patch("cinema.shots.controller.generate_ai_broll") as mock_broll, \
             patch("llm.prompt_optimizer.optimize_shot_prompt", return_value=opt_spec):
            ctrl.generate_keyframe_take("scene_1", "shot_1_0", positive_prompt="a test prompt")

        mock_broll.assert_called_once()
        assert mock_broll.call_args.kwargs["identity_anchor"] == canonical

    def test_optimizer_identity_anchor_used_when_no_canonical_identity(self):
        """Advisory/object-specific fallback: with no canonical identity on
        the shot (e.g. no registered primary character), the optimizer's
        identity_anchor is the only signal available and must still reach
        generate_ai_broll."""
        ctrl, project = _build_keyframe_controller()
        project["global_settings"]["prompt_optimizer_enabled"] = True
        # helper default continuity_config has no "identity_anchor" key
        opt_spec = {
            "image_prompt": "optimized prompt",
            "identity_anchor": "brand logo: red circle, chrome finish",
        }

        with patch("cinema.shots.controller.generate_ai_broll") as mock_broll, \
             patch("llm.prompt_optimizer.optimize_shot_prompt", return_value=opt_spec):
            ctrl.generate_keyframe_take("scene_1", "shot_1_0", positive_prompt="a test prompt")

        mock_broll.assert_called_once()
        assert mock_broll.call_args.kwargs["identity_anchor"] == "brand logo: red circle, chrome finish"

    def test_optimizer_disabled_keeps_canonical_identity_anchor(self):
        """Control: with the optimizer off, the canonical anchor from
        continuity_config is what reaches generate_ai_broll — unaffected."""
        ctrl, project = _build_keyframe_controller()
        canonical = "Alice: straight blonde hair, round wire-rimmed glasses, slim build"
        ctrl._core.continuity.enhance_shot_prompt.return_value = {
            "prompt": "base prompt",
            "continuity_config": {"identity_anchor": canonical},
        }

        with patch("cinema.shots.controller.generate_ai_broll") as mock_broll:
            ctrl.generate_keyframe_take("scene_1", "shot_1_0", positive_prompt="a test prompt")

        mock_broll.assert_called_once()
        assert mock_broll.call_args.kwargs["identity_anchor"] == canonical


class TestKeyframeCostProvenance:
    """The keyframe cost is recorded under the backend that ACTUALLY ran
    (threaded out of generate_ai_broll via ImageGenResult), not a tier-based
    hardcoded guess. Before this fix the cost site computed
    `"QUALITY_MAX" if quality_tier == "max" else "FLUX_KONTEXT"`, so a pod-PuLID
    generation logged provider='fal', model='FLUX_KONTEXT' — indistinguishable
    from a real FAL fallback (cycle-17 live test: cost_log row 1065 logged
    'fal' for a generation the pod /history confirmed ran via ApplyPulid)."""

    def test_records_threaded_backend_not_hardcoded(self, tmp_path):
        from phase_c_assembly import ImageGenResult

        ctrl, project = _build_keyframe_controller()
        # Make the output path real so os.path.exists(img_path) is True and the
        # method flows past the seam to the cost-recording site.
        real_path = str(tmp_path / "kf.jpg")
        ctrl._take_output_path = MagicMock(return_value=real_path)

        def _fake_broll(*args, **kwargs):
            # Simulate the pod-PuLID branch: write the artifact and report that
            # it ran on the ComfyUI pod, not FAL.
            with open(real_path, "wb") as fh:
                fh.write(b"img")
            return ImageGenResult(real_path, "COMFYUI_PULID")

        with patch("cinema.shots.controller.generate_ai_broll", side_effect=_fake_broll):
            ctrl.generate_keyframe_take("scene_1", "shot_1_0", positive_prompt="a test prompt")

        ctrl.cost_tracker.record_api_call.assert_called_once()
        call = ctrl.cost_tracker.record_api_call.call_args
        assert call.args[0] == "COMFYUI_PULID", (
            f"expected the threaded backend, got {call.args[0]!r} "
            "(tier-based hardcoded-guess regression)"
        )
        assert call.kwargs["operation"] == "keyframe_generation"


class TestRemediationAdvisoryOnFailedKeyframe:
    """T6: when the identity gate fails, generate_keyframe_take appends
    take.metadata.remediation_advisory (built by build_remediation_advisory)
    alongside the existing identity_failure_reason + suggested_pulid_adjustment.

    We drive the method through to the identity-validation branch by:
    1. Setting primary_reference in continuity_config so primary_ref is set.
    2. Mocking _get_shared_validator to return a failed IdentityValidationResult.
    3. Mocking generate_ai_broll to write the fake image so the method proceeds.

    Advisory-only: the method must still return success=True; the advisory
    is purely informational metadata on the take."""

    def test_advisory_appended_on_identity_gate_failure(self, tmp_path):
        from identity.types import (
            CharacterIdentityResult,
            FailureReason,
            IdentityValidationResult,
        )
        from phase_c_assembly import ImageGenResult

        ctrl, project = _build_keyframe_controller()
        real_path = str(tmp_path / "kf.jpg")
        ctrl._take_output_path = MagicMock(return_value=real_path)

        # Provide a primary_reference so identity validation runs
        ctrl._core.continuity.enhance_shot_prompt.return_value = {
            "prompt": "base prompt",
            "continuity_config": {"primary_reference": "/fake/ref.jpg"},
        }

        # Build a failed identity result with a known failure reason
        char_diag = CharacterIdentityResult(
            character_id="char_1",
            character_name="Alice",
            best_similarity=0.40,
            mean_similarity=0.35,
            min_similarity=0.30,
            frame_results=[],
            matched=False,
            primary_failure_reason=FailureReason.WRONG_PERSON,
            suggested_pulid_adjustment=0.05,
        )
        failed_id_result = IdentityValidationResult(
            passed=False,
            overall_score=0.40,
            character_results={"char_1": char_diag},
            frames_sampled=1,
            video_duration_seconds=0.0,
            shot_type="medium",
            threshold_used=0.70,
        )

        def _fake_broll(*args, **kwargs):
            with open(real_path, "wb") as fh:
                fh.write(b"img")
            return ImageGenResult(real_path, "COMFYUI_PULID")

        mock_validator = MagicMock()
        mock_validator.validate_image.return_value = failed_id_result

        # Intercept _mutate_shot to extract the 'take' dict the mutator closes over.
        captured_take = {}
        mutation_shot = {}

        def _capture_mutator(shot_id_arg, mutator_fn):
            # Generation now performs a durable reservation mutation before
            # the final take append. Preserve one stub across both mutations
            # and capture only when the take-registration mutation runs.
            result = mutator_fn({}, mutation_shot)
            if mutation_shot.get("keyframe_takes"):
                captured_take.update(mutation_shot["keyframe_takes"][0])
            return result.value

        ctrl._mutate_shot = _capture_mutator

        with patch("cinema.shots.controller.generate_ai_broll", side_effect=_fake_broll), \
             patch("phase_c_vision._get_shared_validator", return_value=mock_validator):
            # We need the shot to have a primary_character so primary_char_id is set
            project["scenes"][0]["shots"][0]["primary_character"] = "char_1"
            result = ctrl.generate_keyframe_take(
                "scene_1", "shot_1_0", positive_prompt="a test prompt"
            )

        assert result.get("success") is True, f"expected success, got {result}"
        # Existing diagnostics (pre-T6) must still be present
        assert captured_take["metadata"]["identity_failure_reason"] == "wrong_person"
        assert captured_take["metadata"]["suggested_pulid_adjustment"] == 0.05
        # T6: remediation_advisory must now be populated
        assert "remediation_advisory" in captured_take["metadata"], (
            "T6 wire missing: remediation_advisory not set on failed-identity take"
        )
        adv = captured_take["metadata"]["remediation_advisory"]
        assert adv["failure_reason"] == "wrong_person", f"got {adv!r}"
        assert adv["source"] == "deterministic", f"got {adv!r}"

    def test_no_advisory_when_identity_passes(self, tmp_path):
        """Passing identity gate must NOT set remediation_advisory."""
        from identity.types import (
            CharacterIdentityResult,
            FailureReason,
            IdentityValidationResult,
        )
        from phase_c_assembly import ImageGenResult

        ctrl, project = _build_keyframe_controller()
        real_path = str(tmp_path / "kf.jpg")
        ctrl._take_output_path = MagicMock(return_value=real_path)

        ctrl._core.continuity.enhance_shot_prompt.return_value = {
            "prompt": "base prompt",
            "continuity_config": {"primary_reference": "/fake/ref.jpg"},
        }

        char_diag = CharacterIdentityResult(
            character_id="char_1",
            character_name="Alice",
            best_similarity=0.85,
            mean_similarity=0.80,
            min_similarity=0.75,
            frame_results=[],
            matched=True,
            primary_failure_reason=FailureReason.PASSED,
            suggested_pulid_adjustment=0.0,
        )
        passed_id_result = IdentityValidationResult(
            passed=True,
            overall_score=0.85,
            character_results={"char_1": char_diag},
            frames_sampled=1,
            video_duration_seconds=0.0,
            shot_type="medium",
            threshold_used=0.70,
        )

        def _fake_broll(*args, **kwargs):
            with open(real_path, "wb") as fh:
                fh.write(b"img")
            return ImageGenResult(real_path, "COMFYUI_PULID")

        mock_validator = MagicMock()
        mock_validator.validate_image.return_value = passed_id_result

        captured_take = {}
        mutation_shot = {}

        def _capture_mutator(shot_id_arg, mutator_fn):
            result = mutator_fn({}, mutation_shot)
            if mutation_shot.get("keyframe_takes"):
                captured_take.update(mutation_shot["keyframe_takes"][0])
            return result.value

        ctrl._mutate_shot = _capture_mutator

        with patch("cinema.shots.controller.generate_ai_broll", side_effect=_fake_broll), \
             patch("phase_c_vision._get_shared_validator", return_value=mock_validator):
            project["scenes"][0]["shots"][0]["primary_character"] = "char_1"
            result = ctrl.generate_keyframe_take(
                "scene_1", "shot_1_0", positive_prompt="a test prompt"
            )

        assert result.get("success") is True
        assert "remediation_advisory" not in captured_take["metadata"], (
            "advisory must NOT be set when identity passes"
        )
