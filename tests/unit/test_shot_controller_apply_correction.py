from pathlib import Path
from unittest.mock import MagicMock, patch


def _touch(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"test-media")
    return str(path)


def _make_controller(tmp_path, *, settings=None, in_frame=None, scene_chars=None):
    from cinema.shots.controller import ShotController

    base_path = _touch(tmp_path / "base.mp4")
    base_take = {
        "id": "take_base",
        "kind": "motion",
        "path": base_path,
        "metadata": {},
    }
    shot = {
        "id": "shot_1_0",
        "plan_status": "approved",
        "characters_in_frame": list(in_frame or ["char_frame"]),
        "motion_takes": [base_take],
        "approved_motion_take_id": "take_base",
        "approved_final_take_id": "take_base",
        "postprocess_variants": [],
    }
    scene = {
        "id": "scene_1",
        "title": "Scene",
        "action": "Action",
        "location_id": "loc_1",
        "characters_present": list(scene_chars or ["char_scene"]),
        "shots": [shot],
    }
    project = {
        "id": "proj_apply",
        "scenes": [scene],
        "characters": [
            {"id": "char_frame", "name": "Framed Actor"},
            {"id": "char_scene", "name": "Scene Actor"},
        ],
        "objects": [],
        "locations": [],
        "global_settings": {"face_swap_enabled": True, **(settings or {})},
    }

    host = MagicMock()
    host._refresh_project_snapshot.return_value = project
    host._candidate_take.return_value = base_take

    lifecycle = MagicMock()
    runstate = MagicMock()
    runstate.shot_results = {}

    core = MagicMock()
    core.project = project
    core.project_dir = str(tmp_path)
    core.continuity = MagicMock()
    core.cost_tracker = MagicMock()

    controller = ShotController(
        core=core,
        lifecycle=lifecycle,
        host=host,
        runstate=runstate,
    )
    controller._take_output_path = MagicMock(
        side_effect=lambda _sid, take_id, ext: str(tmp_path / f"{take_id}{ext}")
    )

    captured = {}

    def _capture_mutate(shot_id, mutator):
        fake_shot = {"postprocess_variants": []}
        result = mutator({}, fake_shot)
        captured["shot_id"] = shot_id
        captured["mutation_result"] = result
        captured["variant"] = fake_shot["postprocess_variants"][-1]
        return captured["variant"]

    controller._mutate_shot = MagicMock(side_effect=_capture_mutate)
    return controller, project, base_take, captured


def test_regenerate_image_dispatches_prompts_to_keyframe_generation(tmp_path):
    controller, _project, _base_take, _captured = _make_controller(tmp_path)
    controller.generate_keyframe_take = MagicMock(return_value={"success": True, "take": {"id": "kf"}})
    controller.generate_motion_take = MagicMock()

    result = controller.apply_correction(
        "shot_1_0",
        "regenerate_image",
        params={"positive_prompt": "closer framing", "negative_prompt": "no blur"},
        take_id="take_base",
    )

    assert result == {"success": True, "take": {"id": "kf"}}
    controller.generate_keyframe_take.assert_called_once_with(
        "scene_1",
        "shot_1_0",
        positive_prompt="closer framing",
        negative_prompt="no blur",
    )
    controller.generate_motion_take.assert_not_called()
    controller._mutate_shot.assert_not_called()


def test_regenerate_video_dispatches_to_motion_generation(tmp_path):
    controller, _project, _base_take, _captured = _make_controller(tmp_path)
    controller.generate_keyframe_take = MagicMock()
    controller.generate_motion_take = MagicMock(return_value={"success": True, "take": {"id": "motion"}})

    result = controller.apply_correction("shot_1_0", "regenerate_video", take_id="take_base")

    assert result == {"success": True, "take": {"id": "motion"}}
    controller.generate_motion_take.assert_called_once_with("scene_1", "shot_1_0")
    controller.generate_keyframe_take.assert_not_called()
    controller._mutate_shot.assert_not_called()


def test_face_swap_success_uses_in_frame_character_and_records_postprocess_variant(tmp_path):
    controller, project, base_take, captured = _make_controller(
        tmp_path,
        in_frame=["char_frame"],
        scene_chars=["char_scene"],
    )
    ref_path = _touch(tmp_path / "frame-ref.jpg")

    def _fake_ref(project_arg, character_id):
        assert project_arg is project
        assert character_id == "char_frame"
        return ref_path

    def _fake_face_swap(video_path, primary_ref, out_path):
        assert video_path == base_take["path"]
        assert primary_ref == ref_path
        return _touch(Path(out_path))

    with patch("cinema.shots.controller.get_reference_image", side_effect=_fake_ref) as mock_ref, \
         patch("cinema.shots.controller.face_swap_video_frames", side_effect=_fake_face_swap) as mock_swap:
        result = controller.apply_correction(
            "shot_1_0",
            "face_swap",
            params={"strength": 0.8},
            take_id="take_base",
        )

    assert result["success"] is True, result
    assert captured["shot_id"] == "shot_1_0"
    assert result["take"] is captured["variant"]
    assert result["take"]["kind"] == "postprocess"
    assert result["take"]["source_take_id"] == "take_base"
    assert result["take"]["metadata"] == {"action": "face_swap", "params": {"strength": 0.8}}
    assert result["video"] == result["take"]["path"]
    assert Path(result["video"]).exists()
    assert captured["mutation_result"].save is True
    assert captured["mutation_result"].value is result["take"]

    mock_ref.assert_called_once()
    mock_swap.assert_called_once()
    controller._host._rebuild_review_clips.assert_called_once_with()
    controller._host._save_checkpoint.assert_called_once_with()

    progress_stages = [call.args[0] for call in controller._lifecycle.report_progress.call_args_list]
    assert progress_stages == ["CORRECTING", "POSTPROCESS_READY"]
    ready_kwargs = controller._lifecycle.report_progress.call_args_list[-1].kwargs
    assert ready_kwargs["scene_id"] == "scene_1"
    assert ready_kwargs["shot_id"] == "shot_1_0"
    assert ready_kwargs["take_id"] == result["take"]["id"]
    assert ready_kwargs["take_kind"] == "postprocess"
