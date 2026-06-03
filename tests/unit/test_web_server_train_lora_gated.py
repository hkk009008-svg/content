"""
tests/unit/test_web_server_train_lora_gated.py — TDD tests for Task 6.

Verifies that api_train_lora uses train_character_lora_gated (not the bare
train_character_lora), gates registration on not-rejected, and persists
char_lora_strengths alongside char_lora_paths.

Two core cases:
  1. Accept — gated returns success + rejected=False
     → char_lora_paths[cid] written, char_lora_strengths[cid] written
  2. Reject — gated returns success + rejected=True
     → char_lora_paths NOT written (no registration at all)
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch, call

import pytest

from web_server import app, _lora_training_threads, _lora_training_lock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_lora_state():
    """Clear _lora_training_threads before and after each test."""
    with _lora_training_lock:
        _lora_training_threads.clear()
    yield
    with _lora_training_lock:
        _lora_training_threads.clear()


@pytest.fixture()
def client():
    """Flask test client with testing mode enabled."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PID = "proj-t6"
_CID = "char-t6"
_KEY = f"{_PID}:{_CID}"


def _make_project(cid: str = _CID) -> dict:
    """Minimal project dict with one character having >=15 reference images."""
    return {
        "id": _PID,
        "name": "Test T6",
        "characters": [
            {
                "id": cid,
                "name": "Alice",
                "reference_images": [f"img_{i}.jpg" for i in range(20)],
            }
        ],
        "global_settings": {},
    }


def _post_train(client, pid=_PID, cid=_CID):
    """POST to train-lora endpoint and return the response."""
    return client.post(
        f"/api/projects/{pid}/characters/{cid}/train-lora",
        content_type="application/json",
        json={},
    )


def _wait_for_runner(key=_KEY, timeout=5.0):
    """Wait until the background thread for the given key finishes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with _lora_training_lock:
            t = _lora_training_threads.get(key)
        if t is None:
            return  # runner completed and popped itself
        if not t.is_alive():
            return
        time.sleep(0.02)
    raise TimeoutError(f"Runner thread for {key!r} did not finish within {timeout}s")


# ---------------------------------------------------------------------------
# Test 1 — Accept path: registration + strength written
# ---------------------------------------------------------------------------

def test_accept_writes_path_and_strength(client):
    """
    gated returns success + rejected=False + best_strength=0.55
    → char_lora_paths[cid] written AND char_lora_strengths[cid]=0.55
    """
    project = _make_project()
    mutated: list[dict] = []

    def fake_gated(project_dir, char, *, config_overrides=None):
        return {
            "success": True,
            "lora_path": "/l/c1.safetensors",
            "best_strength": 0.55,
            "rejected": False,
            "quality_warning": False,
            "quality_score": 0.74,
            "skipped": False,
            "attempts": 1,
        }

    def fake_mutate(pid, mutator_fn, timeout=None):
        # Invoke the mutator with a copy of the project (as real mutate_project does)
        result = mutator_fn(project)
        mutated.append({"pid": pid, "result": result})
        return result

    with (
        patch("web_server.load_project", return_value=project),
        patch("web_server.get_project_dir", return_value="/proj/t6"),
        patch("web_server.mutate_project", side_effect=fake_mutate),
        patch("prep.lora_quality.train_character_lora_gated", side_effect=fake_gated),
    ):
        resp = _post_train(client)

    assert resp.status_code == 202, resp.data
    data = resp.get_json()
    assert data.get("started") is True

    _wait_for_runner()

    # Both path and strength must be written
    settings = project.get("global_settings", {})
    paths = settings.get("char_lora_paths", {})
    strengths = settings.get("char_lora_strengths", {})

    assert paths.get(_CID) == "/l/c1.safetensors", (
        f"char_lora_paths[{_CID!r}] not written; settings={settings!r}"
    )
    assert strengths.get(_CID) == 0.55, (
        f"char_lora_strengths[{_CID!r}] not written; settings={settings!r}"
    )
    # mutate_project was called once
    assert len(mutated) == 1
    assert mutated[0]["pid"] == _PID


# ---------------------------------------------------------------------------
# Test 2 — Reject path: NO registration at all
# ---------------------------------------------------------------------------

def test_reject_skips_registration(client):
    """
    gated returns success + rejected=True
    → char_lora_paths NOT written (rejected LoRA must not be registered)
    """
    project = _make_project()
    mutate_calls: list = []

    def fake_gated(project_dir, char, *, config_overrides=None):
        return {
            "success": True,
            "lora_path": "/l/c1.safetensors",
            "best_strength": 0.40,
            "rejected": True,
            "quality_warning": True,
            "quality_score": 0.40,
            "skipped": False,
            "attempts": 3,
        }

    def fake_mutate(pid, mutator_fn, timeout=None):
        mutate_calls.append(pid)
        return mutator_fn(project)

    with (
        patch("web_server.load_project", return_value=project),
        patch("web_server.get_project_dir", return_value="/proj/t6"),
        patch("web_server.mutate_project", side_effect=fake_mutate),
        patch("prep.lora_quality.train_character_lora_gated", side_effect=fake_gated),
    ):
        resp = _post_train(client)

    assert resp.status_code == 202, resp.data

    _wait_for_runner()

    # mutate_project must NOT have been called
    assert mutate_calls == [], (
        f"mutate_project should not be called on reject; got calls={mutate_calls!r}"
    )
    settings = project.get("global_settings", {})
    assert "char_lora_paths" not in settings or _CID not in settings.get("char_lora_paths", {}), (
        f"char_lora_paths[{_CID!r}] must not be written on reject; settings={settings!r}"
    )
