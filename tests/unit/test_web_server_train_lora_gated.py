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

        # Wait inside the patch context so mutate_project remains mocked while
        # the background thread executes record_lora_verdict then mutate_project.
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


# ---------------------------------------------------------------------------
# Test 3 — Verdict visible via get_lora_status (rejected / quality_warning /
#          quality_score / best_strength all surfaced on the polling path)
# ---------------------------------------------------------------------------

def test_verdict_visible_via_get_lora_status(client, tmp_path):
    """
    After a gated run that returns rejected=True, quality_warning=True,
    quality_score=0.40, best_strength=0.55, calling get_lora_status for
    the same char must return those fields in its dict so a polling client
    can see the verdict.

    This test exercises the gap identified in the Task 6 code review:
    train_character_lora_gated returned a verdict dict but the background
    _runner never wrote it to the on-disk status file.
    """
    import json
    import os
    from prep.lora_training import get_lora_status

    project_dir = str(tmp_path)
    project = _make_project()
    project["id"] = _PID

    # Pre-seed a minimal status file as the real gated orchestrator would have
    # written via train_character_lora (the mock bypasses that).
    status_dir = os.path.join(project_dir, "loras", _CID)
    os.makedirs(status_dir, exist_ok=True)
    initial_status = {
        "char_id": _CID,
        "status": "done",
        "progress_percent": 100.0,
        "started_at": "2026-06-04T00:00:00Z",
        "finished_at": "2026-06-04T00:01:00Z",
        "lora_path": "/l/c1.safetensors",
        "quality_score": None,
        "image_count": 20,
        "config": None,
        "error": None,
        "log_tail": None,
        "rejected": False,
        "quality_warning": False,
        "best_strength": None,
    }
    with open(os.path.join(status_dir, "status.json"), "w") as f:
        json.dump(initial_status, f)

    def fake_gated(proj_dir, char, *, config_overrides=None):
        return {
            "success": True,
            "lora_path": "/l/c1.safetensors",
            "rejected": True,
            "quality_warning": True,
            "quality_score": 0.40,
            "best_strength": 0.55,
            "skipped": False,
            "attempts": 3,
        }

    with (
        patch("web_server.load_project", return_value=project),
        patch("web_server.get_project_dir", return_value=project_dir),
        patch("web_server.mutate_project"),  # should not be called but don't crash
        patch("prep.lora_quality.train_character_lora_gated", side_effect=fake_gated),
    ):
        resp = _post_train(client)

    assert resp.status_code == 202, resp.data
    _wait_for_runner()

    status = get_lora_status(project_dir, _CID)

    assert status.get("rejected") is True, (
        f"expected rejected=True in status; got {status!r}"
    )
    assert status.get("quality_warning") is True, (
        f"expected quality_warning=True in status; got {status!r}"
    )
    assert status.get("quality_score") == pytest.approx(0.40), (
        f"expected quality_score=0.40 in status; got {status!r}"
    )
    assert status.get("best_strength") == pytest.approx(0.55), (
        f"expected best_strength=0.55 in status; got {status!r}"
    )


# ---------------------------------------------------------------------------
# Test 4 — skip-retrain (best_strength=None) drops a stale strength (M-6)
# ---------------------------------------------------------------------------

def test_skip_retrain_pops_stale_strength(client):
    """
    A re-train that SKIPS validation (skipped=True, best_strength=None) still registers
    the new path (not rejected), but must DROP any previously-stored
    char_lora_strengths[cid] so a stale strength doesn't apply to the
    re-trained-but-unvalidated LoRA — keeps the two dicts in lockstep (review M-6).
    """
    project = _make_project()
    # Pre-seed a stale strength + path from an earlier validated train
    project["global_settings"]["char_lora_strengths"] = {_CID: 0.7}
    project["global_settings"]["char_lora_paths"] = {_CID: "/l/old.safetensors"}

    def fake_gated(project_dir, char, *, config_overrides=None):
        return {
            "success": True,
            "lora_path": "/l/new.safetensors",
            "best_strength": None,      # validation skipped (no GPU/anchor)
            "rejected": False,
            "quality_warning": False,
            "quality_score": None,
            "skipped": True,
            "attempts": 1,
        }

    def fake_mutate(pid, mutator_fn, timeout=None):
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

    settings = project.get("global_settings", {})
    # Path updated (registered — not rejected)
    assert settings.get("char_lora_paths", {}).get(_CID) == "/l/new.safetensors"
    # Stale strength dropped (best_strength None -> pop)
    assert _CID not in settings.get("char_lora_strengths", {}), (
        f"stale char_lora_strengths[{_CID!r}] must be popped on skip-retrain; "
        f"got {settings.get('char_lora_strengths')!r}"
    )


# ---------------------------------------------------------------------------
# Task 3 — char_lora_triggers persistence (spec §3(b) prerequisite)
# ---------------------------------------------------------------------------

def test_accept_with_trigger_writes_trigger(client):
    """
    A result carrying trigger_token="TOKx" lands in
    global_settings.char_lora_triggers[cid] (in lockstep with paths/strengths).
    """
    project = _make_project()

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
            "trigger_token": "TOKx",
        }

    def fake_mutate(pid, mutator_fn, timeout=None):
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

    settings = project.get("global_settings", {})
    triggers = settings.get("char_lora_triggers", {})
    assert triggers.get(_CID) == "TOKx", (
        f"char_lora_triggers[{_CID!r}] expected 'TOKx'; settings={settings!r}"
    )


def test_accept_without_trigger_pops_stale_trigger(client):
    """
    A result WITHOUT trigger_token must pop any stale char_lora_triggers[cid]
    entry — lockstep with the strengths pattern.
    """
    project = _make_project()
    # Pre-seed a stale trigger from an earlier train
    project["global_settings"]["char_lora_triggers"] = {_CID: "TOKold"}

    def fake_gated(project_dir, char, *, config_overrides=None):
        return {
            "success": True,
            "lora_path": "/l/c2.safetensors",
            "best_strength": 0.60,
            "rejected": False,
            "quality_warning": False,
            "quality_score": 0.80,
            "skipped": False,
            "attempts": 1,
            # No trigger_token key
        }

    def fake_mutate(pid, mutator_fn, timeout=None):
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

    settings = project.get("global_settings", {})
    assert _CID not in settings.get("char_lora_triggers", {}), (
        f"stale char_lora_triggers[{_CID!r}] must be popped when result has no trigger_token; "
        f"got {settings.get('char_lora_triggers')!r}"
    )


def test_accept_with_empty_trigger_pops_stale_trigger(client):
    """PIN (F2): a result with trigger_token="" (empty string) must also pop any stale
    char_lora_triggers[cid] entry.
    The truthiness gate treats "" as absent (commit 574118e declared this intentional);
    the existing test only covered the key-absent case.
    """
    project = _make_project()
    # Pre-seed a stale trigger from an earlier train
    project["global_settings"]["char_lora_triggers"] = {_CID: "TOKold"}

    def fake_gated(project_dir, char, *, config_overrides=None):
        return {
            "success": True,
            "lora_path": "/l/c3.safetensors",
            "best_strength": 0.58,
            "rejected": False,
            "quality_warning": False,
            "quality_score": 0.77,
            "skipped": False,
            "attempts": 1,
            "trigger_token": "",   # empty string — falsy, treated as absent
        }

    def fake_mutate(pid, mutator_fn, timeout=None):
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

    settings = project.get("global_settings", {})
    assert _CID not in settings.get("char_lora_triggers", {}), (
        f"stale char_lora_triggers[{_CID!r}] must be popped when trigger_token=''; "
        f"got {settings.get('char_lora_triggers')!r}"
    )
