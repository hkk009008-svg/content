"""
tests/unit/test_web_server_auto_approve.py — Tests for the
POST /api/shots/<shot_id>/reject-auto-approve endpoint (Session 13).

Covers:
  1. Happy path: valid gate + reason → 200 {"status": "ok"}
  2. Invalid gate → 400 {"error": "invalid gate"}
  3. Missing reason → 400 {"error": "reason required"}
  4. Non-JSON body → 400 {"error": "JSON body required"}
  5. Shot not found (no matching shot_id in any project) → 404

Uses Flask's test_client() with patched project_manager functions so
no filesystem access is required.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, call

import pytest

from web_server import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """Flask test client with testing mode enabled."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _make_project(shot_id: str = "shot-abc", gate_approved: bool = True) -> dict:
    """Return a minimal project dict containing one scene with one shot."""
    shot: dict = {
        "id": shot_id,
        "prompt": "test prompt",
        "plan_status": "approved",
        "keyframe_takes": [],
        "motion_takes": [],
        "postprocess_variants": [],
        "diagnostics": [],
        "auto_approve_audit": [
            {
                "gate": "plan",
                "auto_approved": gate_approved,
                "vetoes": [],
                "rule_names": ["no_plan_rejection_reason"],
                "timestamp": "2026-05-25T00:00:00+00:00",
            }
        ],
        "plan_auto_approved": gate_approved,
    }
    return {
        "id": "proj-test",
        "name": "Test Project",
        "scenes": [{"id": "scene-1", "shots": [shot]}],
    }


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _post(client, shot_id: str, body: dict | None, content_type: str = "application/json", pid: str = "proj-test"):
    """POST to the reject-auto-approve endpoint.

    Per cycle-6 Lane V F1 fix: route now includes /projects/<pid>/.
    """
    if body is None:
        return client.post(
            f"/api/projects/{pid}/shots/{shot_id}/reject-auto-approve",
            content_type="text/plain",
            data="not json",
        )
    return client.post(
        f"/api/projects/{pid}/shots/{shot_id}/reject-auto-approve",
        content_type=content_type,
        data=json.dumps(body),
    )


# ---------------------------------------------------------------------------
# Test 1 — Happy path: valid gate + reason → 200
# ---------------------------------------------------------------------------

def test_reject_auto_approve_happy_path(client):
    """Valid gate + non-empty reason → 200 {"status": "ok"}."""
    project = _make_project(shot_id="shot-happy")

    mutate_calls: list[dict] = []

    def fake_mutate(pid, mutator_fn, timeout=None, snapshot=None):
        # Call the mutator with our test project to exercise the mutation logic.
        result = mutator_fn(project)
        mutate_calls.append({"pid": pid, "result": result})
        return result

    with patch("web_server.mutate_project", side_effect=fake_mutate):
        resp = _post(client, "shot-happy", {"gate": "plan", "reason": "Colours are off"})

    assert resp.status_code == 200, resp.data
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["shot_id"] == "shot-happy"
    assert data["gate"] == "plan"

    # Verify mutate_project was called with the route's pid (cycle-6 F1 fix).
    assert mutate_calls[0]["pid"] == "proj-test"

    # Verify the mutation was applied: flag cleared, audit entry appended.
    shot = project["scenes"][0]["shots"][0]
    assert shot.get("plan_auto_approved") is False
    audit = shot.get("auto_approve_audit", [])
    user_entry = next(
        (e for e in audit if "user_override" in e.get("rule_names", [])), None
    )
    assert user_entry is not None, "user_override audit entry not appended"
    assert user_entry["auto_approved"] is False
    assert user_entry["vetoes"] == ["Colours are off"]
    assert user_entry["gate"] == "plan"


# ---------------------------------------------------------------------------
# Test 2 — Invalid gate → 400
# ---------------------------------------------------------------------------

def test_reject_auto_approve_invalid_gate(client):
    """gate='invalid' → 400 {"error": "invalid gate"}."""
    resp = _post(client, "shot-xyz", {"gate": "invalid", "reason": "bad framing"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "invalid gate"


# ---------------------------------------------------------------------------
# Test 3 — Missing reason → 400
# ---------------------------------------------------------------------------

def test_reject_auto_approve_missing_reason(client):
    """Omitted reason → 400 {"error": "reason required"}."""
    resp = _post(client, "shot-xyz", {"gate": "plan"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "reason required"


# ---------------------------------------------------------------------------
# Test 4 — Non-JSON body → 400
# ---------------------------------------------------------------------------

def test_reject_auto_approve_non_json_body(client):
    """Non-JSON content-type → 400 {"error": "JSON body required"}."""
    resp = _post(client, "shot-xyz", body=None)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "JSON body required"


# ---------------------------------------------------------------------------
# Test 5 — Shot not found → 404
# ---------------------------------------------------------------------------

def test_reject_auto_approve_shot_not_found(client):
    """Shot not found in the named project → 404 "Shot not found"."""
    # Per cycle-6 F1 fix, mutate_project returns the mutator's value directly
    # (no list_projects scan). When the shot isn't in the project, the mutator
    # returns MutationResult(False, save=False); real mutate_project surfaces
    # that as falsy → endpoint returns 404 "Shot not found".
    with patch("web_server.mutate_project", return_value=False):
        resp = _post(client, "shot-missing", {"gate": "final", "reason": "wrong take approved"})

    assert resp.status_code == 404
    data = resp.get_json()
    assert data["error"] == "Shot not found"


# ---------------------------------------------------------------------------
# Test 6 — Project not found → 404 "Project not found" (cycle-6 F1 NEW path)
# ---------------------------------------------------------------------------

def test_reject_auto_approve_project_not_found(client):
    """Unknown pid → mutate_project returns None → 404 "Project not found"."""
    with patch("web_server.mutate_project", return_value=None):
        resp = _post(client, "shot-xyz", {"gate": "plan", "reason": "test"}, pid="proj-missing")

    assert resp.status_code == 404
    data = resp.get_json()
    assert data["error"] == "Project not found"
