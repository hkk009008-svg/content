"""
tests/unit/test_regenerate_shot_negative_prompt.py

Threading negative_prompt through the legacy /regenerate path
(api_regenerate_shot -> ShotController.regenerate_shot -> generate_keyframe_take).

Context: the /regenerate docstring formerly claimed negative_prompt support the
code did not implement (the frontend's regenerateShot helper puts negative_prompt
in the POST body at web/src/hooks/usePipelineState.ts:149). This wires it through
for the keyframe branch. negative_prompt is a keyframe-image-generation concept;
the motion branch (when a keyframe is already approved) does NOT receive it —
generate_motion_take has no negative_prompt parameter and derives any negative
from shot["negative_constraints"]. These tests lock both halves of that contract.

The full-restart path (POST /restart -> restart_shot) already honored
negative_prompt; this aligns the lighter /regenerate path for the keyframe case.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(approved_keyframe_take_id: str = "", scene_id: str = "scene_1",
                  shot_id: str = "shot_1_0") -> dict:
    """Minimal project with one scene + one shot.

    approved_keyframe_take_id="" -> regenerate_shot takes the KEYFRAME branch.
    A non-empty value         -> regenerate_shot takes the MOTION branch.
    """
    shot: dict = {
        "id": shot_id,
        "prompt": "Wide shot of the protagonist",
        "plan_status": "approved",
    }
    if approved_keyframe_take_id:
        shot["approved_keyframe_take_id"] = approved_keyframe_take_id
        shot["keyframe_takes"] = [{"id": approved_keyframe_take_id, "kind": "keyframe"}]
    return {
        "id": "proj_test",
        "scenes": [
            {"id": scene_id, "title": "Test Scene", "action": "A.", "shots": [shot]}
        ],
        "global_settings": {},
    }


def _build_controller(project: dict):
    """Build a minimal ShotController with stubbed host + dependencies.

    Mirrors tests/unit/test_iterate_endpoint.py::_build_controller.
    """
    from cinema.shots.controller import ShotController

    host = MagicMock()
    host._refresh_project_snapshot.return_value = project
    host._rebuild_review_clips.return_value = None
    host._save_checkpoint.return_value = None
    host._resolve_take_path.return_value = "/fake/path.jpg"

    lifecycle = MagicMock()
    runstate = MagicMock()
    runstate.shot_results = {}

    core = MagicMock()
    core.project = project
    core.project_dir = "/tmp/fake_project"
    core.continuity = MagicMock()
    mock_cost_tracker = MagicMock()
    mock_cost_tracker.is_over_budget.return_value = False
    core.cost_tracker = mock_cost_tracker

    return ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)


# ---------------------------------------------------------------------------
# Controller-level: regenerate_shot threads negative_prompt
# ---------------------------------------------------------------------------

def test_regenerate_shot_keyframe_branch_threads_negative_prompt():
    """No approved keyframe -> keyframe branch -> generate_keyframe_take receives negative_prompt."""
    project = _make_project(approved_keyframe_take_id="")
    ctrl = _build_controller(project)
    ctrl.generate_keyframe_take = MagicMock(return_value={"success": True, "take": {"id": "k1"}})
    ctrl.generate_motion_take = MagicMock()

    result = ctrl.regenerate_shot(
        "scene_1", "shot_1_0", negative_prompt="blurry, lowres, extra fingers"
    )

    assert result["success"] is True
    ctrl.generate_keyframe_take.assert_called_once()
    assert ctrl.generate_keyframe_take.call_args.kwargs.get("negative_prompt") == \
        "blurry, lowres, extra fingers"
    ctrl.generate_motion_take.assert_not_called()


def test_regenerate_shot_motion_branch_does_not_pass_negative_prompt():
    """Approved keyframe -> motion branch -> generate_motion_take does NOT receive negative_prompt.

    Locks the honest partial-support contract: negative_prompt is a keyframe-image
    concept; generate_motion_take has no such parameter.
    """
    project = _make_project(approved_keyframe_take_id="take_parent")
    ctrl = _build_controller(project)
    ctrl.generate_keyframe_take = MagicMock()
    ctrl.generate_motion_take = MagicMock(return_value={"success": True, "take": {"id": "m1"}})

    result = ctrl.regenerate_shot("scene_1", "shot_1_0", negative_prompt="blurry")

    assert result["success"] is True
    ctrl.generate_motion_take.assert_called_once()
    assert "negative_prompt" not in ctrl.generate_motion_take.call_args.kwargs
    ctrl.generate_keyframe_take.assert_not_called()


# ---------------------------------------------------------------------------
# Endpoint-level: POST /regenerate forwards negative_prompt to the pipeline
# ---------------------------------------------------------------------------

def test_regenerate_endpoint_forwards_negative_prompt(inject_pipeline):
    """POST /regenerate with {negative_prompt} -> pipeline.regenerate_shot(..., negative_prompt=...)."""
    from web_server import app

    app.config["TESTING"] = True
    pid = "proj-regen-neg"

    pipeline = MagicMock()
    pipeline.regenerate_shot.return_value = {"success": True, "take": {"id": "k1"}}
    inject_pipeline(pid, pipeline)

    with app.test_client() as client, \
            patch("web_server.mutate_project", return_value="scene_1"):
        resp = client.post(
            f"/api/projects/{pid}/shots/shot_1_0/regenerate",
            json={"negative_prompt": "blurry, lowres"},
        )

    assert resp.status_code == 200, f"got {resp.status_code} body={resp.get_json()}"
    pipeline.regenerate_shot.assert_called_once_with(
        "scene_1", "shot_1_0", negative_prompt="blurry, lowres"
    )
