"""Project-aware video-target discovery and public write fences."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from domain.models import Shot
from domain.project_manager import MAX_PROJECT_ID_LENGTH
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
    aspect_ratio=None,
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
        if aspect_ratio is not None:
            latest["global_settings"]["aspect_ratio"] = aspect_ratio
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


def _corrupt_stored_project_id(tmp_path, route_id, stored_id):
    project_path = tmp_path / route_id / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project["id"] = stored_id
    project_path.write_text(
        json.dumps(project, indent=2),
        encoding="utf-8",
    )
    return project_path


def test_legacy_config_surface_is_unchanged_without_project(client):
    response = client.get("/api/config")

    assert response.status_code == 200
    body = response.get_json()
    assert "target_apis" in body
    assert "api_registry" in body
    assert "video_engines" not in body


def test_project_config_returns_404_for_missing_project(
    client,
    tmp_path,
    monkeypatch,
):
    from domain import project_manager
    import web_server

    monkeypatch.setattr(
        project_manager,
        "PROJECTS_DIR",
        str(tmp_path),
        raising=False,
    )
    load_bomb = MagicMock(
        side_effect=AssertionError("normalizing loader reached"),
    )
    create_bomb = MagicMock(
        side_effect=AssertionError("project creator reached"),
    )
    lock_bomb = MagicMock(
        side_effect=AssertionError("project lock reached"),
    )
    ensure_bomb = MagicMock(
        side_effect=AssertionError("project directory creation reached"),
    )
    write_bomb = MagicMock(
        side_effect=AssertionError("project write reached"),
    )
    monkeypatch.setattr(web_server, "load_project", load_bomb)
    monkeypatch.setattr(web_server, "create_project", create_bomb)
    monkeypatch.setattr(project_manager, "_acquire_project_lock", lock_bomb)
    monkeypatch.setattr(project_manager, "_ensure_project_dir", ensure_bomb)
    monkeypatch.setattr(project_manager, "_save_project_unlocked", write_bomb)

    response = client.get("/api/config?project_id=does-not-exist")

    assert response.status_code == 404
    assert response.get_json() == {"error": "Project not found"}
    assert list(tmp_path.iterdir()) == []
    load_bomb.assert_not_called()
    create_bomb.assert_not_called()
    lock_bomb.assert_not_called()
    ensure_bomb.assert_not_called()
    write_bomb.assert_not_called()


def test_project_config_missing_project_disappearance_race_stays_read_only(
    client,
    tmp_path,
    monkeypatch,
):
    from domain import project_manager

    monkeypatch.setattr(
        project_manager,
        "PROJECTS_DIR",
        str(tmp_path),
        raising=False,
    )
    monkeypatch.setattr(
        project_manager,
        "_load_project_unlocked",
        MagicMock(side_effect=FileNotFoundError("deleted during read")),
    )
    lock_bomb = MagicMock(
        side_effect=AssertionError("disappearance retried through lock"),
    )
    write_bomb = MagicMock(
        side_effect=AssertionError("disappearance triggered a write"),
    )
    monkeypatch.setattr(project_manager, "_acquire_project_lock", lock_bomb)
    monkeypatch.setattr(project_manager, "_save_project_unlocked", write_bomb)

    response = client.get("/api/config?project_id=race-project")

    assert response.status_code == 404
    assert response.get_json() == {"error": "Project not found"}
    assert list(tmp_path.iterdir()) == []
    lock_bomb.assert_not_called()
    write_bomb.assert_not_called()


@pytest.mark.parametrize(
    "project_id",
    [
        "",
        ".",
        "..",
        "../outside",
        "nested/outside",
        r"nested\outside",
        "/tmp/outside",
        " ",
        "\t",
        "\n",
        "project id",
        "project\x00id",
        "project\x1f",
        "-leading-hyphen",
        "_leading-underscore",
        "project.name",
        "prøject",
    ],
)
def test_project_config_rejects_uncontained_id_before_load(
    client,
    monkeypatch,
    project_id,
):
    """A query ID is fenced before load can read, lock, normalize, or write."""
    import web_server

    load_bomb = MagicMock(
        side_effect=AssertionError("uncontained project_id reached load"),
    )
    monkeypatch.setattr(web_server, "load_project", load_bomb)

    response = client.get(
        "/api/config",
        query_string={"project_id": project_id},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid project_id"}
    load_bomb.assert_not_called()


@pytest.mark.parametrize(
    "project_id",
    [
        "A" * (MAX_PROJECT_ID_LENGTH + 1),
        "A" * 255,
        "A" * 256,
        "A" * 4096,
    ],
)
def test_project_config_rejects_overlong_id_before_any_loader(
    client,
    monkeypatch,
    project_id,
):
    """The explicit length bound prevents OS-dependent path errors."""
    import web_server

    read_bomb = MagicMock(
        side_effect=AssertionError("overlong project_id reached storage"),
    )
    monkeypatch.setattr(
        web_server,
        "load_existing_project_readonly",
        read_bomb,
    )

    response = client.get(
        "/api/config",
        query_string={"project_id": project_id},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid project_id"}
    read_bomb.assert_not_called()


def test_project_config_accepts_maximum_project_id_without_artifacts(
    client,
    tmp_path,
    monkeypatch,
):
    from domain import project_manager

    project_id = "A" + ("b" * (MAX_PROJECT_ID_LENGTH - 1))
    monkeypatch.setattr(
        project_manager,
        "PROJECTS_DIR",
        str(tmp_path),
        raising=False,
    )

    response = client.get(
        "/api/config",
        query_string={"project_id": project_id},
    )

    assert response.status_code == 404
    assert response.get_json() == {"error": "Project not found"}
    assert list(tmp_path.iterdir()) == []


def test_project_route_rejects_overlong_id_before_endpoint_storage(
    client,
    monkeypatch,
):
    import web_server

    project_id = "A" * (MAX_PROJECT_ID_LENGTH + 1)
    load_bomb = MagicMock(
        side_effect=AssertionError("route reached project load"),
    )
    mutate_bomb = MagicMock(
        side_effect=AssertionError("route reached project mutation"),
    )
    monkeypatch.setattr(web_server, "load_project", load_bomb)
    monkeypatch.setattr(web_server, "mutate_project", mutate_bomb)

    response = client.put(
        f"/api/projects/{project_id}/shots/shot_a",
        json={"target_api": "AUTO"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid project_id"}
    load_bomb.assert_not_called()
    mutate_bomb.assert_not_called()


@pytest.mark.parametrize(
    "project_id",
    [" ", "\t", "\n", "project\x00id", "project\x1fid"],
)
def test_project_config_noncanonical_id_creates_no_lock_artifact(
    client,
    tmp_path,
    monkeypatch,
    project_id,
):
    """Rejected whitespace/control IDs never reach the lock-backed loader."""
    from domain import project_manager

    monkeypatch.setattr(
        project_manager,
        "PROJECTS_DIR",
        str(tmp_path),
        raising=False,
    )

    response = client.get(
        "/api/config",
        query_string={"project_id": project_id},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid project_id"}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "project_id",
    ["a", "0bf9d0608eab", "does-not-exist", "proj_1", "Project-2"],
)
def test_project_config_valid_slug_reaches_missing_project_404(
    client,
    tmp_path,
    monkeypatch,
    project_id,
):
    """Existing ID shapes remain valid even when the project is absent."""
    from domain import project_manager

    monkeypatch.setattr(
        project_manager,
        "PROJECTS_DIR",
        str(tmp_path),
        raising=False,
    )

    response = client.get(
        "/api/config",
        query_string={"project_id": project_id},
    )

    assert response.status_code == 404
    assert response.get_json() == {"error": "Project not found"}


@pytest.mark.parametrize(
    ("request_kwargs", "expected_error"),
    [
        ({"json": []}, "JSON object required"),
        ({"json": "scalar"}, "JSON object required"),
        ({"json": 7}, "JSON object required"),
        (
            {"data": "null", "content_type": "application/json"},
            "JSON object required",
        ),
        (
            {"data": "name=ignored", "content_type": "text/plain"},
            "JSON body required",
        ),
    ],
)
def test_project_update_requires_json_object_without_write(
    client,
    tmp_path,
    monkeypatch,
    request_kwargs,
    expected_error,
):
    pid, _scene_id, _shot_ids = _persist_project(tmp_path, monkeypatch)
    project_path = tmp_path / pid / "project.json"
    before = project_path.read_bytes()

    response = client.put(
        f"/api/projects/{pid}",
        **request_kwargs,
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": expected_error}
    assert project_path.read_bytes() == before


@pytest.mark.parametrize("include_equal_id", [False, True])
def test_project_update_accepts_absent_or_equal_body_id(
    client,
    tmp_path,
    monkeypatch,
    include_equal_id,
):
    pid, _scene_id, _shot_ids = _persist_project(tmp_path, monkeypatch)
    payload = {"name": "Updated project"}
    if include_equal_id:
        payload["id"] = pid

    response = client.put(f"/api/projects/{pid}", json=payload)

    assert response.status_code == 200
    persisted = _load_project(pid)
    assert persisted["id"] == pid
    assert persisted["name"] == "Updated project"


def test_project_update_missing_pid_returns_404_without_artifacts(
    client,
    tmp_path,
    monkeypatch,
):
    from domain import project_manager

    monkeypatch.setattr(
        project_manager,
        "PROJECTS_DIR",
        str(tmp_path),
        raising=False,
    )

    response = client.put(
        "/api/projects/valid-missing",
        json={"name": "must not create"},
    )

    assert response.status_code == 404
    assert response.get_json() == {"error": "Project not found"}
    assert list(tmp_path.iterdir()) == []


def test_project_update_rejects_mismatched_body_id_before_collision(
    client,
    tmp_path,
    monkeypatch,
):
    from domain import project_manager
    import web_server

    pid, _scene_id, _shot_ids = _persist_project(tmp_path, monkeypatch)
    other = project_manager.create_project("Other project")
    route_path = tmp_path / pid / "project.json"
    other_path = tmp_path / other["id"] / "project.json"
    route_before = route_path.read_bytes()
    other_before = other_path.read_bytes()
    mutate_bomb = MagicMock(
        side_effect=AssertionError("mismatched id reached mutation"),
    )
    monkeypatch.setattr(web_server, "mutate_project", mutate_bomb)

    response = client.put(
        f"/api/projects/{pid}",
        json={"id": other["id"], "name": "must not persist"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "Body id must match route id",
        "route_id": pid,
    }
    mutate_bomb.assert_not_called()
    assert route_path.read_bytes() == route_before
    assert other_path.read_bytes() == other_before


@pytest.mark.parametrize(
    "boundary",
    ["config", "project_get", "project_put", "scene_put", "target_put"],
)
def test_stored_project_id_mismatch_fails_q3_boundaries_without_cross_write(
    client,
    tmp_path,
    monkeypatch,
    boundary,
):
    pid, scene_id, (shot_id,) = _persist_project(tmp_path, monkeypatch)
    stored_id = "other-project"
    project_path = _corrupt_stored_project_id(
        tmp_path,
        pid,
        stored_id,
    )
    before = project_path.read_bytes()
    from domain.project_manager import _project_lock_path

    # The production sibling lock path — not a hardcoded copy, so this pin
    # cannot silently go vacuous if the lock location moves again.
    lock_path = Path(_project_lock_path(pid))
    lock_path.unlink(missing_ok=True)

    if boundary == "config":
        response = client.get(f"/api/config?project_id={pid}")
    elif boundary == "project_get":
        response = client.get(f"/api/projects/{pid}")
    elif boundary == "project_put":
        response = client.put(
            f"/api/projects/{pid}",
            json={"id": pid, "name": "must not persist"},
        )
    elif boundary == "scene_put":
        response = client.put(
            f"/api/projects/{pid}/scenes/{scene_id}",
            json={"id": scene_id, "title": "must not persist"},
        )
    else:
        response = client.put(
            f"/api/projects/{pid}/shots/{shot_id}",
            json={"target_api": "AUTO"},
        )

    assert response.status_code == 404
    assert response.get_json() == {"error": "Project not found"}
    assert project_path.read_bytes() == before
    assert not lock_path.exists()
    assert not (tmp_path / stored_id).exists()


def test_project_config_external_path_preserves_outside_sentinel(
    client,
    tmp_path,
    monkeypatch,
):
    """An absolute external project path is neither read nor normalized."""
    import web_server

    outside = tmp_path / "outside-project"
    outside.mkdir()
    sentinel = outside / "project.json"
    before = b'{"id":"outside","target_api":"SORA_2"}'
    sentinel.write_bytes(before)
    load_bomb = MagicMock(
        side_effect=AssertionError("outside project was read"),
    )
    monkeypatch.setattr(web_server, "load_project", load_bomb)

    response = client.get(
        "/api/config",
        query_string={"project_id": str(outside)},
    )

    assert response.status_code == 400
    load_bomb.assert_not_called()
    assert sentinel.read_bytes() == before


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
    assert by_key["KLING_3_0"]["can_select"] is False
    assert by_key["KLING_3_0"]["reason"] == "project_disabled"
    assert by_key["KLING_3_0"]["configured_enabled"] is False
    assert by_key["KLING_3_0"]["can_configure"] is True
    assert by_key["KLING_3_0"]["in_use"] is True
    assert by_key["KLING_3_0"]["historical"] is True

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


def test_project_config_applies_project_aspect_policy(
    client,
    tmp_path,
    monkeypatch,
):
    import domain.video_engine_policy as video_engine_policy

    monkeypatch.setattr(
        video_engine_policy,
        "is_video_aspect_compatible",
        lambda _key, aspect: aspect != "9:16",
    )
    pid, _scene_id, _shot_ids = _persist_project(
        tmp_path,
        monkeypatch,
        aspect_ratio="9:16",
    )

    response = client.get(f"/api/config?project_id={pid}")

    assert response.status_code == 200
    by_key = {
        row["key"]: row
        for row in response.get_json()["video_engines"]
    }
    assert by_key["KLING_3_0"]["can_select"] is False
    assert by_key["KLING_3_0"]["reason"] == "aspect_incompatible"


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


@pytest.mark.parametrize(
    ("api_engines", "aspect_ratio", "target", "reason"),
    [
        (
            {"KLING_3_0": {"enabled": False}},
            "16:9",
            "KLING_3_0",
            "project_disabled",
        ),
    ],
)
def test_direct_shot_write_applies_latest_project_policy(
    client,
    tmp_path,
    monkeypatch,
    api_engines,
    aspect_ratio,
    target,
    reason,
):
    pid, _scene_id, (shot_id,) = _persist_project(
        tmp_path,
        monkeypatch,
        api_engines=api_engines,
        aspect_ratio=aspect_ratio,
    )

    response = client.put(
        f"/api/projects/{pid}/shots/{shot_id}",
        json={"target_api": target},
    )

    assert response.status_code == 409
    assert response.get_json()["reason"] == reason
    assert _find_shot(_load_project(pid), shot_id)["target_api"] == "AUTO"


def test_direct_shot_write_applies_project_aspect_policy(
    client,
    tmp_path,
    monkeypatch,
):
    import domain.video_engine_policy as video_engine_policy

    monkeypatch.setattr(
        video_engine_policy,
        "is_video_aspect_compatible",
        lambda _key, aspect: aspect != "9:16",
    )
    pid, _scene_id, (shot_id,) = _persist_project(
        tmp_path,
        monkeypatch,
        aspect_ratio="9:16",
    )

    response = client.put(
        f"/api/projects/{pid}/shots/{shot_id}",
        json={"target_api": "KLING_3_0"},
    )

    assert response.status_code == 409
    assert response.get_json()["reason"] == "aspect_incompatible"
    assert _find_shot(_load_project(pid), shot_id)["target_api"] == "AUTO"


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
        "target_api": "SORA_2",
        "reason": "retired",
        "retryable": False,
        "shot_id": shot_id,
    }
    assert _find_shot(_load_project(pid), shot_id)["target_api"] == "AUTO"


@pytest.mark.parametrize("nested", [False, True])
def test_target_policy_observation_occurs_inside_latest_project_lock(
    client,
    tmp_path,
    monkeypatch,
    nested,
):
    """A pre-lock ready snapshot cannot authorize a target after readiness changes."""
    import web_server
    from domain.provider_catalog import RuntimeSnapshot

    pid, scene_id, (shot_id,) = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("AUTO",),
    )
    real_mutate_project = web_server.mutate_project
    inside_mutator = {"value": False}

    def guarded_mutate(project_id, mutator, **kwargs):
        def under_lock(latest):
            inside_mutator["value"] = True
            try:
                return mutator(latest)
            finally:
                inside_mutator["value"] = False

        return real_mutate_project(project_id, under_lock, **kwargs)

    def unavailable_runtime():
        assert inside_mutator["value"] is True
        return RuntimeSnapshot()

    def current_date():
        assert inside_mutator["value"] is True
        return _POLICY_DATE

    monkeypatch.setattr(web_server, "mutate_project", guarded_mutate)
    monkeypatch.setattr(
        web_server,
        "_video_policy_runtime_snapshot",
        unavailable_runtime,
    )
    monkeypatch.setattr(
        web_server,
        "_video_policy_current_date",
        current_date,
    )

    if nested:
        proposed = deepcopy(_load_project(pid)["scenes"][0]["shots"])
        proposed[0]["target_api"] = "KLING_3_0"
        response = client.put(
            f"/api/projects/{pid}/scenes/{scene_id}",
            json={"shots": proposed},
        )
    else:
        response = client.put(
            f"/api/projects/{pid}/shots/{shot_id}",
            json={"target_api": "KLING_3_0"},
        )

    assert response.status_code == 409
    assert response.get_json()["reason"] == "runtime_unavailable"
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


@pytest.mark.parametrize("include_equal_id", [False, True])
def test_nested_scene_accepts_absent_or_equal_body_id(
    client,
    tmp_path,
    monkeypatch,
    include_equal_id,
):
    pid, scene_id, _shot_ids = _persist_project(tmp_path, monkeypatch)
    payload = {"title": "Updated scene"}
    if include_equal_id:
        payload["id"] = scene_id

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json=payload,
    )

    assert response.status_code == 200
    persisted = _load_project(pid)["scenes"][0]
    assert persisted["id"] == scene_id
    assert persisted["title"] == "Updated scene"


def test_nested_scene_rejects_mismatched_body_id_atomically(
    client,
    tmp_path,
    monkeypatch,
):
    from domain import project_manager
    import web_server

    pid, scene_id, _shot_ids = _persist_project(tmp_path, monkeypatch)
    other_scene = project_manager.make_scene("Other scene")

    def _append_other(latest):
        latest["scenes"].append(other_scene)
        return True

    project_manager.mutate_project(pid, _append_other)
    before = deepcopy(_load_project(pid))
    load_bomb = MagicMock(
        side_effect=AssertionError("mismatched id reached project load"),
    )
    mutate_bomb = MagicMock(
        side_effect=AssertionError("mismatched id reached mutation"),
    )
    monkeypatch.setattr(web_server, "load_project", load_bomb)
    monkeypatch.setattr(web_server, "mutate_project", mutate_bomb)

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={
            "id": other_scene["id"],
            "title": "must not persist",
            "shots": [],
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "Body id must match route id",
        "route_id": scene_id,
    }
    load_bomb.assert_not_called()
    mutate_bomb.assert_not_called()
    assert _load_project(pid) == before


def test_nested_scene_duplicate_path_identity_is_ambiguous_and_atomic(
    client,
    tmp_path,
    monkeypatch,
):
    from domain import project_manager

    pid, scene_id, _shot_ids = _persist_project(tmp_path, monkeypatch)
    duplicate = project_manager.make_scene("Duplicate")
    duplicate["id"] = scene_id

    def _append_duplicate(latest):
        latest["scenes"].append(duplicate)
        return True

    project_manager.mutate_project(pid, _append_duplicate)
    before = deepcopy(_load_project(pid))

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"id": scene_id, "title": "must not persist"},
    )

    assert response.status_code == 404
    assert response.get_json() == {"error": "Scene not found"}
    assert _load_project(pid) == before


def test_nested_scene_empty_shots_clears_atomically(
    client,
    tmp_path,
    monkeypatch,
):
    pid, scene_id, _shot_ids = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("AUTO", "AUTO"),
    )

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"shots": []},
    )

    assert response.status_code == 200
    persisted_scene = _load_project(pid)["scenes"][0]
    assert persisted_scene["shots"] == []
    assert persisted_scene["num_shots"] == 0


def test_nested_scene_null_shots_is_400_without_write(
    client,
    tmp_path,
    monkeypatch,
):
    pid, scene_id, _shot_ids = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("AUTO",),
    )
    before = deepcopy(_load_project(pid)["scenes"][0])

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"title": "must not persist", "shots": None},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "shots must be a JSON array"}
    assert _load_project(pid)["scenes"][0] == before


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
    assert response.get_json() == {
        "error": "Target video engine is unavailable",
        "error_kind": "target_api_policy",
        "code": "target_api_unavailable",
        "target_api": "SORA_2",
        "reason": "retired",
        "retryable": False,
        "shot_id": shot_ids[1],
    }
    after = _load_project(pid)["scenes"][0]
    assert after["title"] == scene["title"]
    assert after["shots"][0]["prompt"] == scene["shots"][0]["prompt"]
    assert after["shots"][1]["target_api"] == "AUTO"


_STRICT_INVALID_SHOT_VALUES = [
    ("id", 7),
    ("prompt", []),
    ("camera", []),
    ("visual_effect", []),
    ("target_api", []),
    ("scene_foley", []),
    ("characters_in_frame", "char_a"),
    ("primary_character", []),
    ("objects_in_frame", "object_a"),
    ("primary_object", []),
    ("location_id", []),
    ("action_context", []),
    ("generated_image", []),
    ("generated_video", []),
    ("plan_status", []),
    ("plan_rejection_reason", []),
    ("keyframe_takes", {}),
    ("approved_keyframe_take_id", []),
    ("motion_takes", {}),
    ("approved_motion_take_id", []),
    ("postprocess_variants", {}),
    ("approved_final_take_id", []),
    ("performance_takes", {}),
    ("approved_performance_take_id", []),
    ("performance_take_id", []),
    ("performance_engine", []),
    ("driving_video_path", []),
    ("diagnostics", {}),
    ("intent_notes", []),
    ("negative_constraints", []),
    ("continuity_constraints", []),
    ("optimizer_cache", []),
    ("image_api", []),
    ("dialogue", 7),
    ("duration", "5"),
    ("motion_description", []),
    ("shot_type", []),
    ("shot_class", []),
    ("performance_budget_mode", []),
    ("target_api_policy_reason", []),
    ("ensemble_winner", []),
    ("ensemble_scores", {}),
    ("director_review", []),
    ("auto_approve_audit", {}),
    ("plan_auto_approved", 1),
    ("image_auto_approved", 1),
    ("motion_auto_approved", 1),
    ("final_auto_approved", 1),
    ("approved", "true"),
]


def test_strict_invalid_cases_cover_every_canonical_shot_field():
    assert {
        field
        for field, _invalid_value in _STRICT_INVALID_SHOT_VALUES
    } == set(Shot.model_fields)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    _STRICT_INVALID_SHOT_VALUES,
)
def test_nested_scene_rejects_schema_invalid_shot_atomically(
    client,
    tmp_path,
    monkeypatch,
    field,
    invalid_value,
):
    pid, scene_id, _shot_ids = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("AUTO",),
    )
    before = deepcopy(_load_project(pid)["scenes"][0])
    malformed = deepcopy(before["shots"][0])
    malformed[field] = invalid_value

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"title": "must not persist", "shots": [malformed]},
    )

    assert response.status_code == 400
    expected_error = (
        "shots[0].target_api must be a string"
        if field == "target_api"
        else "shots[0] does not match the shot schema"
    )
    assert response.get_json() == {"error": expected_error}
    assert _load_project(pid)["scenes"][0] == before


def test_nested_scene_rejects_unknown_extension_before_mutation(
    client,
    tmp_path,
    monkeypatch,
):
    import web_server

    pid, scene_id, _shot_ids = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("AUTO",),
    )
    before = deepcopy(_load_project(pid)["scenes"][0])
    malformed = deepcopy(before["shots"][0])
    malformed["totally_unknown_field"] = {"value": "must not persist"}
    mutate_bomb = MagicMock(
        side_effect=AssertionError("unknown extension reached mutation"),
    )
    monkeypatch.setattr(web_server, "mutate_project", mutate_bomb)

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"title": "must not persist", "shots": [malformed]},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": (
            "shots[0] contains unsupported fields: "
            "totally_unknown_field"
        ),
    }
    mutate_bomb.assert_not_called()
    assert _load_project(pid)["scenes"][0] == before


@pytest.mark.parametrize("invalid_cache", [[], "cached", None])
def test_nested_scene_rejects_non_mapping_optimizer_cache_atomically(
    client,
    tmp_path,
    monkeypatch,
    invalid_cache,
):
    pid, scene_id, _shot_ids = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("AUTO",),
    )
    before = deepcopy(_load_project(pid)["scenes"][0])
    malformed = deepcopy(before["shots"][0])
    malformed["optimizer_cache"] = invalid_cache

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"title": "must not persist", "shots": [malformed]},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "shots[0] does not match the shot schema",
    }
    assert _load_project(pid)["scenes"][0] == before


@pytest.mark.parametrize("invalid_spec", [[], ["not-a-mapping"], "cached", None])
def test_nested_scene_rejects_non_mapping_optimizer_spec_atomically(
    client,
    tmp_path,
    monkeypatch,
    invalid_spec,
):
    pid, scene_id, _shot_ids = _persist_project(tmp_path, monkeypatch)
    before = deepcopy(_load_project(pid)["scenes"][0])
    malformed = deepcopy(before["shots"][0])
    malformed["optimizer_cache"] = {
        "source_prompt": malformed["prompt"],
        "spec": invalid_spec,
    }

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"title": "must not persist", "shots": [malformed]},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "shots[0] does not match the shot schema",
    }
    assert _load_project(pid)["scenes"][0] == before


_OPTIMIZER_SPEC_FIELDS = {
    "image_prompt",
    "video_prompt",
    "purpose",
    "shot_type",
    "suggested_image_api",
    "suggested_video_api",
    "suggested_lipsync",
    "negative_constraints",
    "identity_anchor",
    "camera",
    "lighting",
    "color_palette",
    "reasoning",
}


def test_optimizer_spec_type_cases_cover_every_public_consumer_field():
    from domain.optimizer_cache import OPTIMIZER_SPEC_FIELD_TYPES

    assert _OPTIMIZER_SPEC_FIELDS == set(OPTIMIZER_SPEC_FIELD_TYPES)


@pytest.mark.parametrize("field", sorted(_OPTIMIZER_SPEC_FIELDS))
def test_nested_scene_rejects_malformed_known_optimizer_spec_value(
    client,
    tmp_path,
    monkeypatch,
    field,
):
    pid, scene_id, _shot_ids = _persist_project(tmp_path, monkeypatch)
    before = deepcopy(_load_project(pid)["scenes"][0])
    malformed = deepcopy(before["shots"][0])
    malformed["optimizer_cache"] = {
        "source_prompt": malformed["prompt"],
        "spec": {field: ["not-the-declared-scalar"]},
    }

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"title": "must not persist", "shots": [malformed]},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "shots[0] does not match the shot schema",
    }
    assert _load_project(pid)["scenes"][0] == before


def test_nested_scene_rejects_non_string_optimizer_source_prompt(
    client,
    tmp_path,
    monkeypatch,
):
    pid, scene_id, _shot_ids = _persist_project(tmp_path, monkeypatch)
    before = deepcopy(_load_project(pid)["scenes"][0])
    malformed = deepcopy(before["shots"][0])
    malformed["optimizer_cache"] = {
        "source_prompt": ["not-a-string"],
        "spec": {},
    }

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"title": "must not persist", "shots": [malformed]},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "shots[0] does not match the shot schema",
    }
    assert _load_project(pid)["scenes"][0] == before


_VALID_OPTIMIZER_SPEC = {
    "image_prompt": "image prompt",
    "video_prompt": "video prompt",
    "purpose": "action_motion",
    "shot_type": "medium",
    "suggested_image_api": "FLUX_DEV",
    "suggested_video_api": "SORA_NATIVE",
    "suggested_lipsync": None,
    "negative_constraints": "blur",
    "identity_anchor": "identity",
    "camera": "static",
    "lighting": "soft",
    "color_palette": "neutral",
    "reasoning": "validated",
}


def test_nested_scene_round_trips_complete_optimizer_consumer_shape(
    client,
    tmp_path,
    monkeypatch,
):
    pid, scene_id, (shot_id,) = _persist_project(tmp_path, monkeypatch)
    proposed = deepcopy(_load_project(pid)["scenes"][0]["shots"])
    proposed[0]["optimizer_cache"] = {
        "source_prompt": proposed[0]["prompt"],
        "spec": _VALID_OPTIMIZER_SPEC,
    }

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"shots": proposed},
    )

    assert response.status_code == 200
    assert _find_shot(_load_project(pid), shot_id)["optimizer_cache"] == {
        "source_prompt": proposed[0]["prompt"],
        "spec": _VALID_OPTIMIZER_SPEC,
    }


_ACTIVE_SHOT_EXTENSIONS = [
    ("objects_in_frame", ["object_a"]),
    ("primary_object", "object_a"),
    ("location_id", "location_a"),
    (
        "optimizer_cache",
        {
            "source_prompt": "prompt",
            "spec": {"purpose": "talking_head_full"},
        },
    ),
    ("approved_performance_take_id", "take_performance"),
    ("performance_engine", "SKIP"),
    ("driving_video_path", "/tmp/driving.mp4"),
    ("image_api", "AUTO"),
    ("dialogue", [{"text": "Hello"}]),
    ("duration", 4.5),
    ("motion_description", "subtle head turn"),
    ("shot_type", "medium"),
    ("shot_class", "portrait"),
    ("performance_budget_mode", "budget"),
    ("target_api_policy_reason", "runtime_unavailable"),
    ("ensemble_winner", "claude-sonnet-4-6"),
    ("ensemble_scores", [0.9, 0.8]),
    (
        "director_review",
        {"decision": "APPROVED", "violations": []},
    ),
    ("auto_approve_audit", [{"gate": "plan"}]),
    ("plan_auto_approved", True),
    ("image_auto_approved", True),
    ("motion_auto_approved", True),
    ("final_auto_approved", True),
    ("approved", None),
]


_ORIGINAL_DECLARED_SHOT_FIELDS = {
    "id",
    "prompt",
    "camera",
    "visual_effect",
    "target_api",
    "scene_foley",
    "characters_in_frame",
    "primary_character",
    "action_context",
    "generated_image",
    "generated_video",
    "plan_status",
    "plan_rejection_reason",
    "keyframe_takes",
    "approved_keyframe_take_id",
    "motion_takes",
    "approved_motion_take_id",
    "postprocess_variants",
    "approved_final_take_id",
    "performance_takes",
    "performance_take_id",
    "diagnostics",
    "intent_notes",
    "negative_constraints",
    "continuity_constraints",
}


def test_active_extension_cases_cover_every_new_canonical_shot_field():
    assert {
        field
        for field, _valid_value in _ACTIVE_SHOT_EXTENSIONS
    } == set(Shot.model_fields).difference(_ORIGINAL_DECLARED_SHOT_FIELDS)


@pytest.mark.parametrize(("field", "valid_value"), _ACTIVE_SHOT_EXTENSIONS)
def test_nested_scene_round_trips_each_active_shot_extension(
    client,
    tmp_path,
    monkeypatch,
    field,
    valid_value,
):
    pid, scene_id, (shot_id,) = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("AUTO",),
    )
    proposed = deepcopy(_load_project(pid)["scenes"][0]["shots"])
    proposed[0][field] = valid_value

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"shots": proposed},
    )

    assert response.status_code == 200
    persisted = _find_shot(_load_project(pid), shot_id)
    assert persisted[field] == valid_value


_OBSERVED_SHOT_COMPATIBILITY_FIELDS = [
    (
        "plan_review",
        {
            "decision": "APPROVED",
            "reason": "",
            "source": "historical",
            "violations": [],
        },
    ),
    (
        "keyframe_review",
        {
            "approved_take_id": "take_keyframe",
            "decision": "APPROVED",
            "reason": "",
            "source": "historical",
        },
    ),
    ("scene_location", "studio"),
]


def test_observed_compatibility_cases_cover_boundary_allowlist():
    import web_server

    assert {
        field
        for field, _value in _OBSERVED_SHOT_COMPATIBILITY_FIELDS
    } == set(web_server._PUBLIC_SHOT_COMPATIBILITY_TYPES)


@pytest.mark.parametrize(
    ("field", "valid_value"),
    _OBSERVED_SHOT_COMPATIBILITY_FIELDS,
)
def test_nested_scene_round_trips_observed_compatibility_field(
    client,
    tmp_path,
    monkeypatch,
    field,
    valid_value,
):
    pid, scene_id, (shot_id,) = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("AUTO",),
    )
    proposed = deepcopy(_load_project(pid)["scenes"][0]["shots"])
    proposed[0][field] = valid_value

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"shots": proposed},
    )

    assert response.status_code == 200
    assert _find_shot(_load_project(pid), shot_id)[field] == valid_value


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("plan_review", []),
        ("keyframe_review", None),
        ("scene_location", {}),
    ],
)
def test_nested_scene_rejects_invalid_compatibility_field_atomically(
    client,
    tmp_path,
    monkeypatch,
    field,
    invalid_value,
):
    pid, scene_id, _shot_ids = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("AUTO",),
    )
    before = deepcopy(_load_project(pid)["scenes"][0])
    malformed = deepcopy(before["shots"][0])
    malformed[field] = invalid_value

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"title": "must not persist", "shots": [malformed]},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "shots[0] does not match the shot schema",
    }
    assert _load_project(pid)["scenes"][0] == before


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


def test_nested_scene_write_applies_project_disabled_policy(
    client,
    tmp_path,
    monkeypatch,
):
    pid, scene_id, (shot_id,) = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("AUTO",),
        api_engines={"KLING_3_0": {"enabled": False}},
    )
    proposed = deepcopy(_load_project(pid)["scenes"][0]["shots"])
    proposed[0]["target_api"] = "KLING_3_0"

    response = client.put(
        f"/api/projects/{pid}/scenes/{scene_id}",
        json={"shots": proposed},
    )

    assert response.status_code == 409
    assert response.get_json()["reason"] == "project_disabled"
    assert _find_shot(_load_project(pid), shot_id)["target_api"] == "AUTO"


def test_duplicate_scene_route_cannot_borrow_historical_grandfather(
    client,
    monkeypatch,
):
    """Even one matching shot is ambiguous when the route scene ID repeats."""
    import web_server

    latest = {
        "id": "duplicate-scene-project",
        "name": "duplicate-scene-project",
        "characters": [],
        "locations": [],
        "scenes": [
            {
                "id": "duplicate-scene",
                "shots": [{
                    "id": "historical-shot",
                    "target_api": "SORA_2",
                    "prompt": "original",
                }],
            },
            {
                "id": "duplicate-scene",
                "shots": [],
            },
        ],
    }
    proposed = deepcopy(latest["scenes"][0]["shots"])
    proposed[0]["prompt"] = "must not persist"

    def _mutate_without_normalizing(_pid, mutator, **_kwargs):
        return mutator(latest)

    monkeypatch.setattr(web_server, "load_project", lambda *_a, **_k: latest)
    monkeypatch.setattr(
        web_server,
        "mutate_project",
        _mutate_without_normalizing,
    )

    response = client.put(
        "/api/projects/duplicate-scene-project/scenes/duplicate-scene",
        json={"shots": proposed},
    )

    assert response.status_code == 409
    assert response.get_json()["reason"] == "retired"
    assert latest["scenes"][0]["shots"][0]["prompt"] == "original"


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


def test_terminal_generated_writer_rejects_latest_project_disabled_target(
    tmp_path,
    monkeypatch,
):
    """Final generated shots are fenced atomically at the lock-held writer."""
    import domain.scene_decomposer as scene_decomposer
    from domain import project_manager
    from domain.video_engine_policy import VideoTargetPolicyError

    pid, scene_id, (shot_id,) = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("AUTO",),
        api_engines={"KLING_3_0": {"enabled": False}},
    )
    project = _load_project(pid)
    generated = deepcopy(project["scenes"][0]["shots"])
    generated[0]["target_api"] = "KLING_3_0"
    real_mutate_project = project_manager.mutate_project
    inside_mutator = {"value": False}

    def guarded_mutate(project_id, mutator, **kwargs):
        def under_lock(latest):
            inside_mutator["value"] = True
            try:
                return mutator(latest)
            finally:
                inside_mutator["value"] = False

        return real_mutate_project(project_id, under_lock, **kwargs)

    def runtime_snapshot():
        assert inside_mutator["value"] is True
        return _fal_runtime()

    def policy_date():
        assert inside_mutator["value"] is True
        return _POLICY_DATE

    monkeypatch.setattr(project_manager, "mutate_project", guarded_mutate)
    monkeypatch.setattr(
        scene_decomposer,
        "_terminal_video_policy_runtime_snapshot",
        runtime_snapshot,
    )
    monkeypatch.setattr(
        scene_decomposer,
        "_terminal_video_policy_current_date",
        policy_date,
    )

    with pytest.raises(VideoTargetPolicyError) as exc_info:
        scene_decomposer.update_scene_shots(
            project,
            scene_id,
            generated,
        )

    assert exc_info.value.target == "KLING_3_0"
    assert exc_info.value.reason == "project_disabled"
    assert exc_info.value.shot_id == shot_id
    assert _find_shot(_load_project(pid), shot_id)["target_api"] == "AUTO"


def test_decompose_http_maps_post_reviewer_target_rejection_atomically(
    client,
    tmp_path,
    monkeypatch,
):
    """A ChiefDirector-style terminal mutation cannot bypass the HTTP fence."""
    import domain.scene_decomposer as scene_decomposer
    import web_server

    pid, scene_id, (existing_shot_id,) = _persist_project(
        tmp_path,
        monkeypatch,
        targets=("AUTO",),
    )
    before = deepcopy(_load_project(pid)["scenes"][0]["shots"])
    post_reviewer_shots = [{
        "id": "chief-modified-shot",
        "target_api": "SORA_2",
    }]
    monkeypatch.setattr(
        web_server,
        "decompose_scene",
        lambda *_args, **_kwargs: post_reviewer_shots,
    )
    monkeypatch.setattr(
        scene_decomposer,
        "_terminal_video_policy_runtime_snapshot",
        _fal_runtime,
    )
    monkeypatch.setattr(
        scene_decomposer,
        "_terminal_video_policy_current_date",
        lambda: _POLICY_DATE,
    )

    response = client.post(
        f"/api/projects/{pid}/scenes/{scene_id}/decompose",
        json={},
    )

    assert response.status_code == 409
    assert response.get_json() == {
        "error": "Target video engine is unavailable",
        "error_kind": "target_api_policy",
        "code": "target_api_unavailable",
        "target_api": "SORA_2",
        "reason": "retired",
        "retryable": False,
        "shot_id": "chief-modified-shot",
    }
    assert _load_project(pid)["scenes"][0]["shots"] == before
    assert _find_shot(_load_project(pid), existing_shot_id)["target_api"] == "AUTO"


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
        # R1: the authoring boundary now threads engine/aspect state exactly
        # like the terminal update_scene_shots boundary; None here because no
        # global_settings context is supplied in this direct call.
        api_engines=None,
        aspect_ratio=None,
    )
    assert validated["target_api"] == "AUTO"
    assert validated["_target_api_policy_reason"] == "unknown"


# ---------------------------------------------------------------------------
# ADR-080 — the per-engine settings schema declares only what the program reads
# ---------------------------------------------------------------------------

# The only keys any reader in the program takes off an api_engines entry. Each
# is proven live by executing its real reader below, so this set cannot quietly
# decay into a list of things nothing reads — the exact defect ADR-080 closed
# (5 inert sub-fields survived 2026-05-28 → 2026-07-31 because only prose said
# they were dead, and prose does not fail a build).
_LIVE_API_ENGINE_KEYS = {"enabled", "storyboard_mode"}


def test_api_engine_defaults_declares_no_unread_subfields():
    """Every declared per-engine key must be one the program actually reads.

    Re-adding a decorative field (duration / resolution / generate_audio /
    face_consistency / camera_motion_native) fails here. To make one
    legitimate: wire a reader first, prove it in the companion test, then
    widen ``_LIVE_API_ENGINE_KEYS`` — in that order.
    """
    import web_server

    declared = {
        key
        for config in web_server._API_ENGINE_DEFAULTS.values()
        for key in config
    }
    unread = sorted(declared - _LIVE_API_ENGINE_KEYS)
    assert not unread, (
        f"per-engine sub-field(s) declared but read by nothing: {unread}. "
        f"Wire a reader or drop the field — see ADR-080."
    )

    # ...and every engine keeps the toggle, or the UI loses its only control.
    missing = sorted(
        engine
        for engine, config in web_server._API_ENGINE_DEFAULTS.items()
        if "enabled" not in config
    )
    assert not missing, f"engine(s) missing the enabled toggle: {missing}"


def test_api_engine_defaults_allowed_keys_are_each_live():
    """Execute the real reader for every allowed key so the pin can't go vacuous.

    Guards the opposite direction from the test above: if a reader is deleted
    or stops responding to its key, the key is no longer live and must leave
    both ``_LIVE_API_ENGINE_KEYS`` and the defaults catalog.
    """
    from cinema.phases.motion_render import _get_storyboard_mode
    from domain.video_engine_policy import _is_project_disabled

    # `enabled` — the single funnel every api_engines consumer routes through.
    assert _is_project_disabled("LTX", {"LTX": {"enabled": False}}) is True
    assert _is_project_disabled("LTX", {"LTX": {"enabled": True}}) is False

    # `storyboard_mode` — KLING_NATIVE only.
    def _project(mode: bool) -> dict:
        return {
            "global_settings": {
                "api_engines": {"KLING_NATIVE": {"storyboard_mode": mode}},
            },
        }

    assert _get_storyboard_mode(_project(True)) is True
    assert _get_storyboard_mode(_project(False)) is False
