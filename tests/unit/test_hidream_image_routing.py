"""Unit tests for the HiDream-I1 image-engine routing wire.

Context: the prompt optimizer emits `suggested_image_api` (FLUX_DEV |
HIDREAM_I1 | SD3_5_LARGE; llm/prompt_optimizer.py). The controller now forwards
it into the max-tier `shot_hint["image_api"]`
(cinema/shots/controller.py::generate_keyframe_take). quality_max's gate
(`requested_image_api == "HIDREAM_I1"`) then calls `_swap_to_hidream`, which
swaps the FLUX UNet loader for HiDream's — but ONLY when the pod actually has
the custom node installed (self-guard); otherwise it no-ops and stays on FLUX.

These tests cover that self-guarding swap, the *consumer* end of the wire. The
optimizer's producer logic is covered by test_prompt_optimizer.py; the 1-line
controller forward is the seam between. The real HiDream firing is GPU-gated
(needs the pod node) — see the cycle-17 GPU-validation task.

Offline — no GPU, no pod, no API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from quality_max import _swap_to_hidream


def _flux_workflow_with_pulid() -> dict:
    """A minimal max-tier workflow stub: FLUX UNet at node 112, a PuLID-Flux
    chain (97/99/100/101/93), a sampler (200) consuming the PuLID-applied model
    output (node 100), and a LoRA loader at node 700."""
    return {
        "112": {"class_type": "UNETLoader",
                "inputs": {"unet_name": "flux1-dev.safetensors", "weight_dtype": "fp8_e4m3fn"}},
        "97": {"class_type": "PulidFluxModelLoader", "inputs": {}},
        "99": {"class_type": "PulidFluxInsightFaceLoader", "inputs": {}},
        "100": {"class_type": "ApplyPulidFlux", "inputs": {"model": ["112", 0]}},
        "101": {"class_type": "PulidFluxEvaClipLoader", "inputs": {}},
        "93": {"class_type": "LoadImage", "inputs": {}},
        "700": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["112", 0]}},
        "200": {"class_type": "KSampler", "inputs": {"model": ["100", 0], "seed": 1}},
    }


class TestSwapToHidream:
    def test_swaps_when_node_available(self):
        wf = _flux_workflow_with_pulid()
        ok = _swap_to_hidream(wf, {"HiDreamModelLoader"})
        assert ok is True
        assert wf["112"]["class_type"] == "HiDreamModelLoader"
        assert wf["112"]["inputs"]["model_name"] == "HiDream-I1-Full.safetensors"

    def test_accepts_any_known_loader_class_name(self):
        # The swap probes three community wrapper names in order.
        for cls in ("HiDreamModelLoader", "HiDreamI1Loader", "HiDreamLoader"):
            wf = _flux_workflow_with_pulid()
            assert _swap_to_hidream(wf, {cls}) is True
            assert wf["112"]["class_type"] == cls

    def test_strips_pulid_nodes_on_swap(self):
        wf = _flux_workflow_with_pulid()
        _swap_to_hidream(wf, {"HiDreamI1Loader"})
        for nid in ("97", "99", "100", "101", "93"):
            assert nid not in wf, f"PuLID node {nid} should be stripped (HiDream has no PuLID)"
        assert "700" in wf, "LoRA chain must survive the swap"

    def test_rewires_pulid_consumers_to_lora(self):
        wf = _flux_workflow_with_pulid()
        _swap_to_hidream(wf, {"HiDreamLoader"})
        # The sampler that consumed node 100 (ApplyPulidFlux) is rewired to LoRA (700).
        assert wf["200"]["inputs"]["model"] == ["700", 0]

    def test_noop_when_node_unavailable(self):
        wf = _flux_workflow_with_pulid()
        before = dict(wf["112"])
        ok = _swap_to_hidream(wf, set())
        assert ok is False
        assert wf["112"] == before, "no swap when no HiDream loader class is on the pod"
        assert "100" in wf, "PuLID chain must be untouched on a no-op (stays on FLUX)"

    def test_noop_when_no_unet_node(self):
        wf = {"700": {"class_type": "LoraLoaderModelOnly", "inputs": {}}}
        assert _swap_to_hidream(wf, {"HiDreamModelLoader"}) is False


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

    ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
    ctrl._take_output_path = MagicMock(return_value="/nonexistent/keyframe.jpg")
    ctrl._resolve_previous_approved_keyframe = MagicMock(return_value="")
    ctrl._mutate_shot = MagicMock()
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

        def _capture_mutator(shot_id_arg, mutator_fn):
            # Call the mutator on a stub; the mutator appends the local `take` dict
            # to fake_shot["keyframe_takes"] — capture it from there.
            fake_shot = {}
            mutator_fn({}, fake_shot)
            # take was appended to fake_shot["keyframe_takes"][0]
            captured_take.update(fake_shot["keyframe_takes"][0])
            return MagicMock()

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

        def _capture_mutator(shot_id_arg, mutator_fn):
            fake_shot = {}
            mutator_fn({}, fake_shot)
            captured_take.update(fake_shot["keyframe_takes"][0])
            return MagicMock()

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
