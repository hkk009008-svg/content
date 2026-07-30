"""Project-aware video-target discovery and public write fences."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
from unittest.mock import MagicMock

import pytest

from domain.provider_catalog import CATALOG, Modality, RuntimeSnapshot


_POLICY_DATE = date(2026, 9, 23)
_ROW_FIELDS = {
    "key",
    "label",
    "can_select",
    "reason",
    "configured_enabled",
    "can_configure",
    "in_use",
    "historical",
}


def _fal_runtime() -> RuntimeSnapshot:
    return RuntimeSnapshot(
        credentials={"fal_key"},
        modules={"fal_client"},
    )


@pytest.fixture
def client(monkeypatch):
    import web_server

    web_server.app.config["TESTING"] = True
    monkeypatch.setattr(web_server, "_running_pipelines", {})
    monkeypatch.setattr(
        web_server,
        "_video_policy_runtime_snapshot",
        _fal_runtime,
    )
    monkeypatch.setattr(
        web_server,
        "_video_policy_current_date",
        lambda: _POLICY_DATE,
    )
    with web_server.app.test_client() as test_client:
        yield test_client


def _persist_project(
    tmp_path,
    monkeypatch,
    *,
    targets=("AUTO",),
    shot_ids=None,
    api_engines=None,
):
    from domain import project_manager

    monkeypatch.setattr(
        project_manager,
        "PROJECTS_DIR",
        str(tmp_path),
        raising=False,
    )
    project = project_manager.create_project("video-target-policy")
    scene = project_manager.make_scene("Scene")
    resolved_ids = list(shot_ids or ())
    shots = []
    for index, target in enumerate(targets):
        shot_id = (
            resolved_ids[index]
            if index < len(resolved_ids)
            else f"shot_policy_{index}"
        )
        shots.append(
            project_manager.make_shot(
                f"Prompt {index}",
                target_api=target,
                shot_id=shot_id,
            )
        )
    scene["shots"] = shots
    scene["num_shots"] = len(shots)

    def _mutate(latest):
        latest["scenes"] = [scene]
        if api_engines is not None:
            latest["global_settings"]["api_engines"] = api_engines
        return True

    project_manager.mutate_project(project["id"], _mutate, timeout=5)
    return project["id"], scene["id"], [shot["id"] for shot in shots]


def _load_project(pid):
    from domain import project_manager

    return project_manager.load_project(pid)


def _find_shot(project, shot_id):
    return next(
        shot
        for scene in project["scenes"]
        for shot in scene["shots"]
        if shot["id"] == shot_id
    )


def test_legacy_config_surface_is_unchanged_without_project(client):
    response = client.get("/api/config")

    assert response.status_code == 200
    body = response.get_json()
    assert "target_apis" in body
    assert "api_registry" in body
    assert "video_engines" not in body


def test_project_config_returns_404_for_missing_project(client):
    response = client.get("/api/config?project_id=does-not-exist")

    assert response.status_code == 404
    assert response.get_json() == {"error": "Project not found"}


def test_project_config_exposes_typed_rows_and_in_use_legacy_target(
    client,
    tmp_path,
    monkeypatch,
):
    pid, _scene_id, _shot_ids = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("SORA_2", "LEGACY_VIDEO_X", "KLING_3_0"),
        api_engines={
            "KLING_3_0": {"enabled": False},
            "LEGACY_VIDEO_X": {"enabled": False},
        },
    )

    response = client.get(f"/api/config?project_id={pid}")

    assert response.status_code == 200
    body = response.get_json()
    assert "target_apis" in body
    assert "api_registry" in body
    rows = body["video_engines"]
    assert rows[0]["key"] == "AUTO"
    assert all(set(row) == _ROW_FIELDS for row in rows)

    typed_video_keys = [
        key
        for key, entry in CATALOG.items()
        if entry.modality is Modality.VIDEO
    ]
    assert [row["key"] for row in rows[:len(typed_video_keys)]] == (
        typed_video_keys
    )
    assert [row["key"] for row in rows[len(typed_video_keys):]] == [
        "LEGACY_VIDEO_X",
    ]

    by_key = {row["key"]: row for row in rows}
    assert by_key["AUTO"] == {
        "key": "AUTO",
        "label": CATALOG["AUTO"].label,
        "can_select": True,
        "reason": None,
        "configured_enabled": True,
        "can_configure": False,
        "in_use": False,
        "historical": False,
    }
    assert by_key["KLING_3_0"]["can_select"] is True
    assert by_key["KLING_3_0"]["reason"] is None
    assert by_key["KLING_3_0"]["configured_enabled"] is False
    assert by_key["KLING_3_0"]["can_configure"] is True
    assert by_key["KLING_3_0"]["in_use"] is True
    assert by_key["KLING_3_0"]["historical"] is False

    assert by_key["SORA_2"]["can_select"] is False
    assert by_key["SORA_2"]["reason"] == "retired"
    assert by_key["SORA_2"]["in_use"] is True
    assert by_key["SORA_2"]["historical"] is True

    legacy = by_key["LEGACY_VIDEO_X"]
    assert legacy == {
        "key": "LEGACY_VIDEO_X",
        "label": "LEGACY_VIDEO_X",
        "can_select": False,
        "reason": "unknown",
        "configured_enabled": False,
        "can_configure": True,
        "in_use": True,
        "historical": True,
    }
    serialized_rows = json.dumps(rows)
    assert "fal_key" not in serialized_rows
    assert "fal_client" not in serialized_rows
    assert "credentials" not in serialized_rows
    assert "modules" not in serialized_rows
    assert "runtime_options" not in serialized_rows


def test_direct_shot_write_accepts_current_selectable_target(
    client,
    tmp_path,
    monkeypatch,
):
    pid, _scene_id, (shot_id,) = _persist_project(
        tmp_path,
        monkeypatch,
    )

    response = client.put(
        f"/api/projects/{pid}/shots/{shot_id}",
        json={"target_api": "KLING_3_0"},
    )

    assert response.status_code == 200
    assert _find_shot(_load_project(pid), shot_id)["target_api"] == "KLING_3_0"


def test_direct_shot_policy_rejection_has_stable_409_shape(
    client,
    tmp_path,
    monkeypatch,
):
    pid, _scene_id, (shot_id,) = _persist_project(
        tmp_path,
        monkeypatch,
    )

    response = client.put(
        f"/api/projects/{pid}/shots/{shot_id}",
        json={"target_api": "SORA_2"},
    )

    assert response.status_code == 409
    body = response.get_json()
    assert body == {
        "error": "Target video engine is unavailable",
        "error_kind": "target_api_policy",
        "code": "target_api_unavailable",
        "target": "SORA_2",
        "reason": "retired",
        "retryable": False,
        "shot_id": shot_id,
    }
    assert _find_shot(_load_project(pid), shot_id)["target_api"] == "AUTO"


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"target_api": 7},
    ],
)
def test_direct_shot_malformed_payload_stays_400(
    client,
    tmp_path,
    monkeypatch,
    payload,
):
    pid, _scene_id, (shot_id,) = _persist_project(
        tmp_path,
        monkeypatch,
    )
    if payload is None:
        response = client.put(
            f"/api/projects/{pid}/shots/{shot_id}",
            data=b"null",
            content_type="application/json",
        )
    else:
        response = client.put(
            f"/api/projects/{pid}/shots/{shot_id}",
            json=payload,
        )

    assert response.status_code == 400
    assert _find_shot(_load_project(pid), shot_id)["target_api"] == "AUTO"


def test_direct_shot_write_grandfathers_exact_unchanged_historical_target(
    client,
    tmp_path,
    monkeypatch,
):
    pid, _scene_id, (shot_id,) = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("SORA_2",),
    )

    response = client.put(
        f"/api/projects/{pid}/shots/{shot_id}",
        json={
            "target_api": "SORA_2",
            "prompt": "Historical target, edited prompt",
        },
    )

    assert response.status_code == 200
    shot = _find_shot(_load_project(pid), shot_id)
    assert shot["target_api"] == "SORA_2"
    assert shot["prompt"] == "Historical target, edited prompt"


def test_direct_duplicate_id_cannot_clone_historical_grandfather(
    client,
    monkeypatch,
):
    import web_server

    latest = {
        "id": "duplicate-project",
        "name": "duplicate-project",
        "characters": [],
        "locations": [],
        "scenes": [
            {
                "id": "scene_a",
                "shots": [{
                    "id": "duplicate-shot",
                    "target_api": "SORA_2",
                }],
            },
            {
                "id": "scene_b",
                "shots": [{
                    "id": "duplicate-shot",
                    "target_api": "SORA_2",
                }],
            },
        ],
    }

    def _mutate_without_normalizing(_pid, mutator, **_kwargs):
        return mutator(latest)

    monkeypatch.setattr(
        web_server,
        "mutate_project",
        _mutate_without_normalizing,
    )
    response = client.put(
        "/api/projects/duplicate-project/shots/duplicate-shot",
        json={"target_api": "SORA_2"},
    )

    assert response.status_code == 409
    assert response.get_json()["reason"] == "retired"
    assert all(
        shot["target_api"] == "SORA_2"
        for scene in latest["scenes"]
        for shot in scene["shots"]
    )


def test_nested_scene_target_rejection_is_atomic(
    client,
    tmp_path,
    monkeypatch,
):
    pid, scene_id, shot_ids = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("AUTO", "AUTO"),
    )
    before = _load_project(pid)
    scene = before["scenes"][0]
    proposed = deepcopy(scene["shots"])
    proposed[0]["prompt"] = "must not partially persist"
    proposed[1]["target_api"] = "SORA_2"

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"title": "must not persist", "shots": proposed},
    )

    assert response.status_code == 409
    assert response.get_json()["shot_id"] == shot_ids[1]
    after = _load_project(pid)["scenes"][0]
    assert after["title"] == scene["title"]
    assert after["shots"][0]["prompt"] == scene["shots"][0]["prompt"]
    assert after["shots"][1]["target_api"] == "AUTO"


def test_nested_scene_round_trips_one_unique_historical_target(
    client,
    tmp_path,
    monkeypatch,
):
    pid, scene_id, (shot_id,) = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("SORA_2",),
    )
    proposed = deepcopy(_load_project(pid)["scenes"][0]["shots"])
    proposed[0]["prompt"] = "updated historical shot"

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"shots": proposed},
    )

    assert response.status_code == 200
    shot = _find_shot(_load_project(pid), shot_id)
    assert shot["target_api"] == "SORA_2"
    assert shot["prompt"] == "updated historical shot"


def test_nested_duplicate_payload_cannot_clone_historical_grandfather(
    client,
    tmp_path,
    monkeypatch,
):
    pid, scene_id, (shot_id,) = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("SORA_2",),
    )
    original = deepcopy(_load_project(pid)["scenes"][0]["shots"][0])
    duplicate = deepcopy(original)
    duplicate["prompt"] = "clone"

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"shots": [original, duplicate]},
    )

    assert response.status_code == 409
    assert response.get_json()["shot_id"] == shot_id
    persisted = _load_project(pid)["scenes"][0]["shots"]
    assert len(persisted) == 1
    assert persisted[0]["target_api"] == "SORA_2"


def test_project_setting_changes_do_not_rewrite_historical_targets(
    client,
    tmp_path,
    monkeypatch,
):
    pid, _scene_id, (shot_id,) = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("SORA_2",),
    )

    response = client.put(
        f"/api/projects/{pid}",
        json={
            "global_settings": {
                "aspect_ratio": "9:16",
                "api_engines": {"SORA_2": {"enabled": False}},
            },
        },
    )

    assert response.status_code == 200
    persisted = _load_project(pid)
    assert persisted["global_settings"]["aspect_ratio"] == "9:16"
    assert (
        persisted["global_settings"]["api_engines"]["SORA_2"]["enabled"]
        is False
    )
    assert _find_shot(persisted, shot_id)["target_api"] == "SORA_2"


def test_missing_project_and_shot_remain_404(
    client,
    tmp_path,
    monkeypatch,
):
    pid, _scene_id, _shot_ids = _persist_project(
        tmp_path,
        monkeypatch,
    )

    missing_shot = client.put(
        f"/api/projects/{pid}/shots/not-there",
        json={"target_api": "AUTO"},
    )
    missing_project = client.put(
        "/api/projects/not-there/shots/not-there",
        json={"target_api": "AUTO"},
    )

    assert missing_shot.status_code == 404
    assert missing_project.status_code == 404


def test_generated_shot_validation_calls_the_same_policy_evaluator(
    monkeypatch,
):
    import domain.scene_decomposer as scene_decomposer
    from domain.video_engine_policy import (
        VideoPolicyReason,
        VideoTargetDecision,
    )

    evaluator = MagicMock(
        return_value=VideoTargetDecision(
            requested="LEGACY_GENERATED",
            target="AUTO",
            accepted=False,
            reason=VideoPolicyReason.UNKNOWN,
        )
    )
    monkeypatch.setattr(
        scene_decomposer,
        "evaluate_shot_target",
        evaluator,
    )
    raw = {
        "prompt": (
            "[SHOT] test [SCENE] room [ACTION] walk "
            "[OUTFIT] coat [QUALITY] film"
        ),
        "camera": scene_decomposer.CAMERA_MOTIONS[0],
        "visual_effect": scene_decomposer.VISUAL_EFFECTS[0],
        "target_api": "LEGACY_GENERATED",
        "scene_foley": "room tone",
        "characters_in_frame": ["char_a"],
        "action_context": "walking",
    }

    validated = scene_decomposer._validate_raw_shot(
        raw,
        index=0,
        snapshot=_fal_runtime(),
        on_date=_POLICY_DATE,
    )

    evaluator.assert_called_once_with(
        "LEGACY_GENERATED",
        snapshot=_fal_runtime(),
        on_date=_POLICY_DATE,
    )
    assert validated["target_api"] == "AUTO"
    assert validated["_target_api_policy_reason"] == "unknown"
