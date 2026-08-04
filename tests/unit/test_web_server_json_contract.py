"""Strict HTTP JSON contracts for public project/setup routes."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from web_server import app


@pytest.mark.parametrize("payload", [[], ["project"], "text", 7, True])
def test_project_create_rejects_non_object_json(payload):
    with app.test_client() as client, patch("web_server.create_project") as create:
        response = client.post("/api/projects", json=payload)

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON object required"}
    create.assert_not_called()


def test_project_create_rejects_malformed_json():
    with app.test_client() as client, patch("web_server.create_project") as create:
        response = client.post(
            "/api/projects",
            data=b'{"name":',
            content_type="application/json",
        )

    assert response.status_code == 400
    create.assert_not_called()


def test_project_create_rejects_json_null():
    with app.test_client() as client, patch("web_server.create_project") as create:
        response = client.post(
            "/api/projects",
            data=b"null",
            content_type="application/json",
        )

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON object required"}
    create.assert_not_called()


def test_project_create_accepts_object_json():
    project = {"id": "p1", "name": "Fresh"}
    with app.test_client() as client, patch(
        "web_server.create_project", return_value=project
    ) as create:
        response = client.post("/api/projects", json={"name": "Fresh"})

    assert response.status_code == 201
    assert response.get_json() == project
    create.assert_called_once_with("Fresh")


@pytest.mark.parametrize(
    "name",
    [
        None,
        "",
        "   \t\n",
        7,
        True,
        [],
        {},
        "x" * 201,
        "unsafe\x00title",
        "\u200b",
    ],
)
def test_project_create_rejects_invalid_name_without_persisting(
    name,
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
    payload = {} if name is None else {"name": name}

    with app.test_client() as client:
        response = client.post("/api/projects", json=payload)

    assert response.status_code == 400
    assert response.get_json() == {
        "code": "invalid_project_create",
        "error": "Invalid project create request",
        "invalid_keys": {
            "name": "must be a nonblank string of at most 200 characters",
        },
        "retryable": False,
    }
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Fresh", "scenes": []},
        {"name": "Fresh", "global_settings": {}},
        {"name": "Fresh", "metadata": {"nested": ["value"]}},
    ],
)
def test_project_create_rejects_unknown_structured_fields_without_persisting(
    payload,
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

    with app.test_client() as client:
        response = client.post("/api/projects", json=payload)

    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "invalid_project_create"
    assert body["error"] == "Invalid project create request"
    assert body["retryable"] is False
    assert body["unknown_keys"] == sorted(set(payload) - {"name"})
    assert "invalid_keys" not in body
    assert list(tmp_path.iterdir()) == []


def test_project_create_normalizes_valid_bounded_name():
    project = {"id": "p1", "name": "Fresh"}
    with app.test_client() as client, patch(
        "web_server.create_project", return_value=project
    ) as create:
        response = client.post("/api/projects", json={"name": "  Fresh  "})

    assert response.status_code == 201
    assert response.get_json() == project
    create.assert_called_once_with("Fresh")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("shot_count", "60", "must be an integer between 1 and 120"),
        ("shot_count", True, "must be an integer between 1 and 120"),
        ("shot_count", 1.5, "must be an integer between 1 and 120"),
        ("shot_count", 0, "must be an integer between 1 and 120"),
        ("shot_count", 121, "must be an integer between 1 and 120"),
        ("has_dialogue", 1, "must be a boolean"),
        ("has_dialogue", "true", "must be a boolean"),
        ("has_dialogue", None, "must be a boolean"),
        ("dialogue_shot_ratio", "0.5", "must be a finite number between 0 and 1"),
        ("dialogue_shot_ratio", True, "must be a finite number between 0 and 1"),
        ("dialogue_shot_ratio", -0.01, "must be a finite number between 0 and 1"),
        ("dialogue_shot_ratio", 1.01, "must be a finite number between 0 and 1"),
        ("candidate_count", "1", "must be an integer between 1 and 16"),
        ("candidate_count", False, "must be an integer between 1 and 16"),
        ("candidate_count", 0, "must be an integer between 1 and 16"),
        ("candidate_count", 17, "must be an integer between 1 and 16"),
        ("quality_tier", "max", "must be 'production'"),
        ("quality_tier", {}, "must be 'production'"),
    ],
)
def test_cost_estimate_rejects_malformed_or_out_of_range_fields(
    field,
    value,
    message,
):
    with app.test_client() as client, patch(
        "web_server.estimate_short_cost"
    ) as estimate:
        response = client.post("/api/cost-estimate", json={field: value})

    assert response.status_code == 400
    assert response.get_json() == {
        "code": "invalid_cost_estimate",
        "error": "Invalid cost estimate request",
        "invalid_keys": {field: message},
        "retryable": False,
    }
    estimate.assert_not_called()


def test_cost_estimate_rejects_unknown_fields_deterministically():
    with app.test_client() as client, patch(
        "web_server.estimate_short_cost"
    ) as estimate:
        response = client.post(
            "/api/cost-estimate",
            json={"duration_seconds": -1, "nested": {"value": []}},
        )

    assert response.status_code == 400
    assert response.get_json() == {
        "code": "invalid_cost_estimate",
        "error": "Invalid cost estimate request",
        "retryable": False,
        "unknown_keys": ["duration_seconds", "nested"],
    }
    estimate.assert_not_called()


@pytest.mark.parametrize(
    "request_kwargs, expected_error",
    [
        ({"data": "shot_count=60", "content_type": "text/plain"}, "JSON body required"),
        ({"data": "null", "content_type": "application/json"}, "JSON object required"),
        ({"json": []}, "JSON object required"),
    ],
)
def test_cost_estimate_requires_json_object(request_kwargs, expected_error):
    with app.test_client() as client, patch(
        "web_server.estimate_short_cost"
    ) as estimate:
        response = client.post("/api/cost-estimate", **request_kwargs)

    assert response.status_code == 400
    assert response.get_json() == {"error": expected_error}
    estimate.assert_not_called()


def test_cost_estimate_accepts_defaults_and_strict_valid_values():
    estimate_payload = {"totals": {"grand_total": 1.23}}
    with app.test_client() as client, patch(
        "web_server.estimate_short_cost", return_value=estimate_payload
    ) as estimate:
        default_response = client.post("/api/cost-estimate", json={})
        explicit_response = client.post(
            "/api/cost-estimate",
            json={
                "shot_count": 120,
                "has_dialogue": False,
                "dialogue_shot_ratio": 1,
                "quality_tier": "production",
                "candidate_count": 16,
            },
        )

    assert default_response.status_code == 200
    assert default_response.get_json() == estimate_payload
    assert explicit_response.status_code == 200
    assert explicit_response.get_json() == estimate_payload
    assert estimate.call_args_list[0].kwargs == {
        "shot_count": 60,
        "has_dialogue": True,
        "dialogue_shot_ratio": 0.5,
        "quality_tier": "production",
        "candidate_count": 1,
    }
    assert estimate.call_args_list[1].kwargs == {
        "shot_count": 120,
        "has_dialogue": False,
        "dialogue_shot_ratio": 1.0,
        "quality_tier": "production",
        "candidate_count": 16,
    }
