"""Validated project-settings write contract (plan slice 9a).

Covers the strict, revision-guarded partial write (``PATCH
/api/projects/<pid>``) and the compat whole-object route's (``PUT``) new
opt-in revision check. The defect this closes: the UI writes whole stale
``global_settings`` snapshots on every keystroke (see
web/src/components/setup/SettingsInspector.tsx / ShotInspector.tsx
``update()``), so a concurrent or out-of-order write can silently clobber
newer state. PATCH fixes this for new callers with a strict per-key
validated, revision-checked contract; PUT gains the same guard as an
opt-in so existing callers are unaffected unless they echo a revision.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from domain.project_manager import ProjectLockError, _project_lock_path


@pytest.fixture
def client():
    import web_server

    web_server.app.config["TESTING"] = True
    web_server._running_pipelines.clear()
    with web_server.app.test_client() as test_client:
        yield test_client
    web_server._running_pipelines.clear()


def _make_project(tmp_path, monkeypatch, name: str = "settings-contract") -> str:
    from domain import project_manager

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    return project_manager.create_project(name)["id"]


def _load(pid):
    from domain import project_manager

    return project_manager.load_project(pid)


def _project_file(tmp_path, pid) -> Path:
    return tmp_path / pid / "project.json"


# ---------------------------------------------------------------------------
# PATCH — partial apply (only sent keys change)
# ---------------------------------------------------------------------------


def test_patch_applies_only_sent_keys(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 0, "aspect_ratio": "9:16"}},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["global_settings"]["aspect_ratio"] == "9:16"
    assert body["global_settings"]["music_mood"] == "suspense"  # untouched default
    assert body["global_settings"]["revision"] == 1

    resp2 = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 1, "music_mood": "hopeful"}},
    )

    assert resp2.status_code == 200
    body2 = resp2.get_json()
    # aspect_ratio from the FIRST patch survives -- proves partial apply
    # (merge), not a full-object replace.
    assert body2["global_settings"]["aspect_ratio"] == "9:16"
    assert body2["global_settings"]["music_mood"] == "hopeful"
    assert body2["global_settings"]["revision"] == 2

    persisted = _load(pid)
    assert persisted["global_settings"]["aspect_ratio"] == "9:16"
    assert persisted["global_settings"]["music_mood"] == "hopeful"
    assert persisted["global_settings"]["revision"] == 2


# ---------------------------------------------------------------------------
# PATCH — stale revision -> 409, no mutation
# ---------------------------------------------------------------------------


def test_patch_stale_revision_returns_409_without_mutation(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)
    before = _project_file(tmp_path, pid).read_bytes()

    resp = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 1, "music_mood": "hopeful"}},
    )

    assert resp.status_code == 409
    body = resp.get_json()
    assert body["code"] == "settings_revision_conflict"
    assert body["current_revision"] == 0
    assert body["retryable"] is True
    assert _project_file(tmp_path, pid).read_bytes() == before
    assert _load(pid)["global_settings"].get("music_mood") == "suspense"


def test_patch_requires_revision_field(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)
    before = _project_file(tmp_path, pid).read_bytes()

    resp = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"aspect_ratio": "9:16"}},
    )

    assert resp.status_code == 400
    assert resp.get_json()["code"] == "revision_required"
    assert _project_file(tmp_path, pid).read_bytes() == before


@pytest.mark.parametrize("bad_revision", ["0", 1.5, True, None, [0]])
def test_patch_rejects_non_integer_revision(client, tmp_path, monkeypatch, bad_revision):
    pid = _make_project(tmp_path, monkeypatch)
    before = _project_file(tmp_path, pid).read_bytes()

    resp = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": bad_revision, "aspect_ratio": "9:16"}},
    )

    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_revision"
    assert _project_file(tmp_path, pid).read_bytes() == before


# ---------------------------------------------------------------------------
# PATCH — unknown/invalid keys fail closed, no mutation
# ---------------------------------------------------------------------------


def test_patch_unknown_key_returns_400_without_mutation(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)
    before = _project_file(tmp_path, pid).read_bytes()

    resp = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 0, "not_a_real_setting": "x"}},
    )

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "invalid_setting_key"
    assert body["unknown_keys"] == ["not_a_real_setting"]
    assert "invalid_keys" not in body
    assert _project_file(tmp_path, pid).read_bytes() == before
    assert "revision" not in _load(pid)["global_settings"]


def test_patch_invalid_value_returns_400_without_mutation(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)
    before = _project_file(tmp_path, pid).read_bytes()

    resp = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 0, "budget_limit_usd": -5}},
    )

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "invalid_setting_key"
    assert "budget_limit_usd" in body["invalid_keys"]
    assert _project_file(tmp_path, pid).read_bytes() == before


def test_patch_reports_unknown_and_invalid_keys_together(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.patch(
        f"/api/projects/{pid}",
        json={
            "global_settings": {
                "revision": 0,
                "not_real": "x",
                "identity_strictness": 5.0,
            }
        },
    )

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["unknown_keys"] == ["not_real"]
    assert "identity_strictness" in body["invalid_keys"]


def test_patch_rejects_protected_lora_fields_as_unknown(client, tmp_path, monkeypatch):
    """The dormant-LoRA containment (ADR-065) stays enforced on its one
    existing checked path (the PUT route); PATCH simply never offers these
    fields at all, so there is no second policy copy to keep in sync."""
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.patch(
        f"/api/projects/{pid}",
        json={
            "global_settings": {
                "revision": 0,
                "char_lora_paths": {"c1": "/new.safetensors"},
            }
        },
    )

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "invalid_setting_key"
    assert "char_lora_paths" in body["unknown_keys"]


def test_patch_global_settings_must_be_object(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.patch(f"/api/projects/{pid}", json={"global_settings": ["nope"]})

    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_global_settings"


# ---------------------------------------------------------------------------
# PATCH -- identity/lock/busy fences mirror the sibling PUT route
# ---------------------------------------------------------------------------


def test_patch_missing_project_returns_404_without_artifacts(client, tmp_path, monkeypatch):
    from domain import project_manager

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)

    resp = client.patch(
        "/api/projects/valid-missing",
        json={"global_settings": {"revision": 0, "aspect_ratio": "9:16"}},
    )

    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Project not found"}
    assert list(tmp_path.iterdir()) == []


def test_patch_stored_id_mismatch_returns_404_without_cross_write(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)
    project_path = _project_file(tmp_path, pid)
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project["id"] = "other-project"
    project_path.write_text(json.dumps(project, indent=2), encoding="utf-8")
    before = project_path.read_bytes()
    lock_path = Path(_project_lock_path(pid))
    lock_path.unlink(missing_ok=True)

    resp = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 0, "aspect_ratio": "9:16"}},
    )

    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Project not found"}
    assert project_path.read_bytes() == before
    assert not lock_path.exists()
    assert not (tmp_path / "other-project").exists()


def test_patch_rejects_mismatched_body_id_before_collision(client, tmp_path, monkeypatch):
    from domain import project_manager

    pid = _make_project(tmp_path, monkeypatch)
    other_id = project_manager.create_project("Other project")["id"]
    route_before = _project_file(tmp_path, pid).read_bytes()
    other_before = _project_file(tmp_path, other_id).read_bytes()

    resp = client.patch(
        f"/api/projects/{pid}",
        json={"id": other_id, "global_settings": {"revision": 0, "aspect_ratio": "9:16"}},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Body id must match route id", "route_id": pid}
    assert _project_file(tmp_path, pid).read_bytes() == route_before
    assert _project_file(tmp_path, other_id).read_bytes() == other_before


def test_patch_busy_returns_409_project_busy(client, tmp_path, monkeypatch):
    import web_server

    pid = _make_project(tmp_path, monkeypatch)
    monkeypatch.setitem(web_server._running_pipelines, pid, object())

    resp = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 0, "aspect_ratio": "9:16"}},
    )

    assert resp.status_code == 409
    body = resp.get_json()
    assert body["code"] == "project_busy"
    assert body["retryable"] is True


def test_patch_locked_returns_409_project_locked(client, tmp_path, monkeypatch):
    import web_server

    pid = _make_project(tmp_path, monkeypatch)
    monkeypatch.setattr(
        web_server,
        "mutate_project",
        MagicMock(side_effect=ProjectLockError(pid, 0.05)),
    )

    resp = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 0, "aspect_ratio": "9:16"}},
    )

    assert resp.status_code == 409
    body = resp.get_json()
    assert body["code"] == "project_locked"
    assert body["retryable"] is True


# ---------------------------------------------------------------------------
# Concurrent-write simulation -- last writer WITH the correct revision wins
# ---------------------------------------------------------------------------


def test_concurrent_write_simulation_last_writer_with_correct_revision_wins(
    client, tmp_path, monkeypatch
):
    pid = _make_project(tmp_path, monkeypatch)

    # Two "tabs" both fetched global_settings at revision 0.
    tab_a_patch = {"global_settings": {"revision": 0, "music_mood": "hopeful"}}
    tab_b_stale_patch = {"global_settings": {"revision": 0, "color_palette": "cold blue"}}

    resp_a = client.patch(f"/api/projects/{pid}", json=tab_a_patch)
    assert resp_a.status_code == 200
    assert resp_a.get_json()["global_settings"]["revision"] == 1

    # Tab B is still holding the now-stale revision 0 -- rejected atomically;
    # tab A's write is not clobbered or lost.
    resp_b_stale = client.patch(f"/api/projects/{pid}", json=tab_b_stale_patch)
    assert resp_b_stale.status_code == 409
    assert resp_b_stale.get_json()["current_revision"] == 1
    mid = _load(pid)
    assert mid["global_settings"]["music_mood"] == "hopeful"
    assert mid["global_settings"].get("color_palette", "") != "cold blue"

    # Tab B refetches (as its client would on a non-2xx response), sees
    # revision 1, and retries with the CORRECT revision -- now wins.
    resp_b_retry = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 1, "color_palette": "cold blue"}},
    )
    assert resp_b_retry.status_code == 200
    assert resp_b_retry.get_json()["global_settings"]["revision"] == 2

    final = _load(pid)
    assert final["global_settings"]["music_mood"] == "hopeful"
    assert final["global_settings"]["color_palette"] == "cold blue"


def test_concurrent_patch_race_exactly_one_writer_succeeds_per_revision(
    client, tmp_path, monkeypatch
):
    """Real thread race (not just sequential simulation): two racing PATCHes
    both claiming revision 0 must resolve to exactly one 200 and one 409 --
    the project file lock (mutate_project) is the serialization point."""
    import web_server

    pid = _make_project(tmp_path, monkeypatch)
    barrier = threading.Barrier(2)
    statuses: dict[str, int] = {}
    errors: list[Exception] = []

    def _attempt(label: str):
        try:
            barrier.wait(timeout=5)
            with web_server.app.test_client() as thread_client:
                resp = thread_client.patch(
                    f"/api/projects/{pid}",
                    json={"global_settings": {"revision": 0, "music_mood": label}},
                )
            statuses[label] = resp.status_code
        except Exception as exc:  # pragma: no cover - failure surfaced via errors
            errors.append(exc)

    threads = [
        threading.Thread(target=_attempt, args=("alice",)),
        threading.Thread(target=_attempt, args=("bob",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert errors == []
    assert sorted(statuses.values()) == [200, 409]

    persisted = _load(pid)
    assert persisted["global_settings"]["revision"] == 1
    assert persisted["global_settings"]["music_mood"] in ("alice", "bob")
    winner = persisted["global_settings"]["music_mood"]
    assert statuses[winner] == 200
    loser = "bob" if winner == "alice" else "alice"
    assert statuses[loser] == 409


# ---------------------------------------------------------------------------
# Whole-object PUT -- opt-in revision check (compat)
# ---------------------------------------------------------------------------


def test_put_without_revision_key_is_unaffected_compat(client, tmp_path, monkeypatch):
    """A caller that never echoes revision behaves exactly as before this
    slice: no conflict is possible to raise, out-of-order writes just apply
    in the order the server receives them."""
    pid = _make_project(tmp_path, monkeypatch)

    resp1 = client.put(
        f"/api/projects/{pid}", json={"global_settings": {"music_mood": "hopeful"}}
    )
    resp2 = client.put(
        f"/api/projects/{pid}", json={"global_settings": {"color_palette": "cold blue"}}
    )

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    persisted = _load(pid)
    assert persisted["global_settings"]["music_mood"] == "hopeful"
    assert persisted["global_settings"]["color_palette"] == "cold blue"
    # Still bumped on every successful settings write, even though neither
    # caller checked it -- a future revision-aware caller (PATCH) can detect
    # that state changed underneath it.
    assert persisted["global_settings"]["revision"] == 2


def test_put_opt_in_revision_check_rejects_stale_write(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)
    before = _project_file(tmp_path, pid).read_bytes()

    resp = client.put(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 5, "music_mood": "hopeful"}},
    )

    assert resp.status_code == 409
    body = resp.get_json()
    assert body["code"] == "settings_revision_conflict"
    assert body["current_revision"] == 0
    assert _project_file(tmp_path, pid).read_bytes() == before


def test_put_opt_in_revision_check_accepts_matching_write_and_bumps(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.put(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 0, "music_mood": "hopeful"}},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["global_settings"]["music_mood"] == "hopeful"
    assert body["global_settings"]["revision"] == 1


def test_put_client_supplied_revision_cannot_skip_the_counter_ahead(client, tmp_path, monkeypatch):
    """A caller cannot jump the counter by simply claiming a higher
    revision -- only a value matching the server's current state is
    honored; anything else is treated as a (safe) conflict."""
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.put(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 999999, "music_mood": "hopeful"}},
    )

    assert resp.status_code == 409
    assert resp.get_json()["current_revision"] == 0
    persisted = _load(pid)
    assert persisted["global_settings"].get("music_mood", "") != "hopeful"
    assert persisted["global_settings"].get("revision", 0) == 0


def test_put_and_patch_share_the_same_revision_counter(client, tmp_path, monkeypatch):
    """PUT and PATCH guard the identical global_settings.revision -- a
    PATCH sees a revision PUT bumped, and vice versa."""
    pid = _make_project(tmp_path, monkeypatch)

    put_resp = client.put(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 0, "music_mood": "hopeful"}},
    )
    assert put_resp.status_code == 200
    assert put_resp.get_json()["global_settings"]["revision"] == 1

    # A PATCH still claiming revision 0 (as if it never saw the PUT) is
    # correctly rejected as stale.
    stale_patch = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 0, "aspect_ratio": "9:16"}},
    )
    assert stale_patch.status_code == 409
    assert stale_patch.get_json()["current_revision"] == 1

    # With the revision the PUT actually produced, the PATCH succeeds.
    ok_patch = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 1, "aspect_ratio": "9:16"}},
    )
    assert ok_patch.status_code == 200
    assert ok_patch.get_json()["global_settings"]["revision"] == 2
    assert ok_patch.get_json()["global_settings"]["music_mood"] == "hopeful"
