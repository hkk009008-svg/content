"""Validated project-settings write contract (plan slice 9a).

Covers the strict, revision-guarded partial write (``PATCH
/api/projects/<pid>``) and the compat whole-object route's (``PUT``)
fail-closed revision check. The defect this closes: the UI writes whole
stale ``global_settings`` snapshots on every keystroke (see
web/src/components/setup/SettingsInspector.tsx / ShotInspector.tsx
``update()``), so a concurrent or out-of-order write can silently clobber
newer state. PATCH fixes this for new callers with a strict per-key
validated, revision-checked contract. PUT gets the SAME guard, fail-closed:
once global_settings carries an established revision, every PUT MUST echo
a matching one or 409s (see ``_settings_revision_established`` in
web_server.py) — omitting the field is no longer a silent bypass. Only a
project whose settings have never been stamped gets a one-time,
unconditional accept-and-stamp (the sole legacy compat window; it closes
the moment that first write lands).
"""

from __future__ import annotations

import json
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


def test_patch_race_exactly_one_writer_succeeds_via_injected_competing_write(
    client, tmp_path, monkeypatch
):
    """Deterministic replacement for a threading.Barrier-based real-thread
    race (flaky-by-construction: OS scheduling decides which thread's lock
    acquire actually wins, so the outcome depends on timing this test
    doesn't control). Exercises the SAME property -- exactly one writer
    wins per revision, the loser gets 409 with zero mutation -- without any
    real concurrency: monkeypatch the same project read mutate_project
    performs UNDER the project file lock so a fully-committed competing
    write lands between this request's own locked read and its own write.
    That forces the exact interleaving a real race only sometimes produces,
    every run, with no threads and no timing dependence."""
    from domain import project_manager

    pid = _make_project(tmp_path, monkeypatch)
    project_file = _project_file(tmp_path, pid)
    original_loader = project_manager._load_expected_project_unlocked
    calls = {"n": 0}
    after_competing_write: dict = {}

    def _inject_competing_write_under_lock(project_id):
        calls["n"] += 1
        # mutate_project calls _load_expected_project_unlocked twice per
        # invocation: an unlocked existence preflight, then the
        # authoritative read taken UNDER the project file lock. Firing on
        # the 2nd call lands the competing write strictly between this
        # request's own locked read and its own (about-to-be-attempted)
        # write -- exactly the window a genuine second thread would need
        # to win the race.
        if project_id == pid and calls["n"] == 2:
            competing = original_loader(project_id)
            competing["global_settings"]["revision"] = 1
            competing["global_settings"]["music_mood"] = "other-tab-won"
            project_manager._save_project_unlocked(competing)
            after_competing_write["bytes"] = project_file.read_bytes()
        return original_loader(project_id)

    monkeypatch.setattr(
        project_manager,
        "_load_expected_project_unlocked",
        _inject_competing_write_under_lock,
    )

    resp = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 0, "music_mood": "late-writer"}},
    )

    assert resp.status_code == 409
    body = resp.get_json()
    assert body["code"] == "settings_revision_conflict"
    assert body["current_revision"] == 1
    assert body["global_settings"]["music_mood"] == "other-tab-won"

    # Zero mutation from the loser: the file is byte-identical to what the
    # competing write alone produced.
    assert project_file.read_bytes() == after_competing_write["bytes"]
    persisted = _load(pid)
    assert persisted["global_settings"]["revision"] == 1
    assert persisted["global_settings"]["music_mood"] == "other-tab-won"

    # The "loser" isn't stranded -- retrying with the revision the
    # competing write actually produced succeeds normally. The lock
    # serialized the two writers; it didn't strand either of them.
    retry = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 1, "music_mood": "late-writer"}},
    )
    assert retry.status_code == 200
    assert retry.get_json()["global_settings"]["revision"] == 2
    assert _load(pid)["global_settings"]["music_mood"] == "late-writer"


# ---------------------------------------------------------------------------
# Whole-object PUT -- fail-closed revision check (compat window closes
# permanently after the first write establishes a revision)
# ---------------------------------------------------------------------------


def test_put_without_revision_key_accepted_once_before_any_revision_exists(
    client, tmp_path, monkeypatch
):
    """The ONLY compat window: a caller that never echoes "revision" still
    succeeds on a project whose settings have never been stamped -- and
    that first write is exactly what ESTABLISHES the counter, closing the
    window for every write after it (see the sibling fail-closed test
    below)."""
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.put(
        f"/api/projects/{pid}", json={"global_settings": {"music_mood": "hopeful"}}
    )

    assert resp.status_code == 200
    persisted = _load(pid)
    assert persisted["global_settings"]["music_mood"] == "hopeful"
    # Bumped even though this caller never looked at the field -- a future
    # revision-aware caller (PATCH, or this same route once established)
    # can now detect that state changed underneath it.
    assert persisted["global_settings"]["revision"] == 1


def test_put_without_revision_key_fails_closed_once_established(
    client, tmp_path, monkeypatch
):
    """IMPORTANT (the live-probed data-loss defect this slice closes): once
    ANY write has stamped a revision, a PUT that omits "revision" entirely
    must NOT silently clobber it. Before this fix, only an EXPLICIT wrong
    value was rejected (see test_put_opt_in_revision_check_rejects_stale_write);
    simply never mentioning the field bypassed the guard completely instead
    of being held to it -- reproduces the brief's repro shape (a PATCH
    establishes revision 1; a second, revision-naive PUT must 409, not
    200, and must not touch the file)."""
    pid = _make_project(tmp_path, monkeypatch)
    first = client.put(
        f"/api/projects/{pid}", json={"global_settings": {"music_mood": "hopeful"}}
    )
    assert first.status_code == 200
    assert first.get_json()["global_settings"]["revision"] == 1
    before = _project_file(tmp_path, pid).read_bytes()

    stale_put = client.put(
        f"/api/projects/{pid}",
        json={"global_settings": {"color_palette": "cold blue"}},
    )

    assert stale_put.status_code == 409
    body = stale_put.get_json()
    assert body["code"] == "settings_revision_conflict"
    assert body["current_revision"] == 1
    assert body["retryable"] is True
    assert _project_file(tmp_path, pid).read_bytes() == before
    persisted = _load(pid)
    assert persisted["global_settings"].get("color_palette", "") != "cold blue"
    assert persisted["global_settings"]["music_mood"] == "hopeful"

    # The caller isn't stuck -- retrying WITH the now-current revision
    # succeeds, exactly like the sequential-simulation test below.
    retry = client.put(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 1, "color_palette": "cold blue"}},
    )
    assert retry.status_code == 200
    assert retry.get_json()["global_settings"]["revision"] == 2
    final = _load(pid)
    assert final["global_settings"]["color_palette"] == "cold blue"
    assert final["global_settings"]["music_mood"] == "hopeful"


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


# ---------------------------------------------------------------------------
# PATCH -- VoiceSection.tsx / VideoSection.tsx settings (9a<->9c integration
# gap: slice 9c wired both components into the Setup page before
# _SETTINGS_KEY_VALIDATORS caught up, so the new strict PATCH 400ed on
# every key either section writes). One test per key family.
# ---------------------------------------------------------------------------


def test_patch_accepts_voice_provider_settings_voicesection_family(client, tmp_path, monkeypatch):
    """VoiceSection.tsx's TTS-provider + default-voice selects."""
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.patch(
        f"/api/projects/{pid}",
        json={
            "global_settings": {
                "revision": 0,
                "tts_provider": "CARTESIA_SONIC_2",
                "default_male_voice": "1W00IGEmNmwmsDeYy7ag",
                "default_female_voice": "uyVNoMrnUku1dZyVEXwD",
            }
        },
    )

    assert resp.status_code == 200
    settings = resp.get_json()["global_settings"]
    assert settings["tts_provider"] == "CARTESIA_SONIC_2"
    assert settings["default_male_voice"] == "1W00IGEmNmwmsDeYy7ag"
    assert settings["default_female_voice"] == "uyVNoMrnUku1dZyVEXwD"


def test_patch_accepts_dialogue_toggle_settings_voicesection_family(client, tmp_path, monkeypatch):
    """VoiceSection.tsx's dialogue-quality toggles."""
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.patch(
        f"/api/projects/{pid}",
        json={
            "global_settings": {
                "revision": 0,
                "dialogue_mode_enabled": False,
                "forced_alignment_enabled": False,
            }
        },
    )

    assert resp.status_code == 200
    settings = resp.get_json()["global_settings"]
    assert settings["dialogue_mode_enabled"] is False
    assert settings["forced_alignment_enabled"] is False

    invalid = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 1, "dialogue_mode_enabled": "yes"}},
    )
    assert invalid.status_code == 400
    assert "dialogue_mode_enabled" in invalid.get_json()["invalid_keys"]


def test_patch_accepts_lipsync_cluster_settings_voicesection_family(client, tmp_path, monkeypatch):
    """VoiceSection.tsx's lipsync cascade cluster -- includes
    lipsync_engine_priority, the first PATCH-covered setting shaped as an
    array rather than a scalar/object."""
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.patch(
        f"/api/projects/{pid}",
        json={
            "global_settings": {
                "revision": 0,
                "lip_sync_mode": "generation",
                "lipsync_engine_priority": ["SYNC_SO_V3", "MUSETALK"],
                "lipsync_quality_validation": False,
                "lipsync_validation_threshold": 0.7,
            }
        },
    )

    assert resp.status_code == 200
    settings = resp.get_json()["global_settings"]
    assert settings["lip_sync_mode"] == "generation"
    assert settings["lipsync_engine_priority"] == ["SYNC_SO_V3", "MUSETALK"]
    assert settings["lipsync_quality_validation"] is False
    assert settings["lipsync_validation_threshold"] == 0.7


@pytest.mark.parametrize(
    "bad_priority",
    ["SYNC_SO_V3", {"0": "SYNC_SO_V3"}, ["SYNC_SO_V3", 7], [None]],
    ids=["bare-string", "object", "list-with-int", "list-with-none"],
)
def test_patch_rejects_non_string_list_lipsync_engine_priority(client, tmp_path, monkeypatch, bad_priority):
    """The new list-of-strings validator must fail closed on a non-list,
    and on a list containing a non-string item -- not just accept anything
    JSON-serializable the way _validate_object_setting would."""
    pid = _make_project(tmp_path, monkeypatch)
    before = _project_file(tmp_path, pid).read_bytes()

    resp = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 0, "lipsync_engine_priority": bad_priority}},
    )

    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "invalid_setting_key"
    assert "lipsync_engine_priority" in body["invalid_keys"]
    assert _project_file(tmp_path, pid).read_bytes() == before


def test_patch_accepts_dialogue_pace_and_mix_settings_voicesection_family(client, tmp_path, monkeypatch):
    """VoiceSection.tsx's dialogue pace (target WPM) + music mastering."""
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.patch(
        f"/api/projects/{pid}",
        json={
            "global_settings": {
                "revision": 0,
                "dialogue_target_wpm": 0,  # "0 disables pacing" per the control's own hint
                "music_mastering": "lo_fi",
            }
        },
    )

    assert resp.status_code == 200
    settings = resp.get_json()["global_settings"]
    assert settings["dialogue_target_wpm"] == 0
    assert settings["music_mastering"] == "lo_fi"

    invalid = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 1, "dialogue_target_wpm": -5}},
    )
    assert invalid.status_code == 400
    assert "dialogue_target_wpm" in invalid.get_json()["invalid_keys"]


def test_patch_accepts_video_cascade_settings_videosection_family(client, tmp_path, monkeypatch):
    """VideoSection.tsx's cascade retry limit + native-dialogue-voice toggle."""
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.patch(
        f"/api/projects/{pid}",
        json={
            "global_settings": {
                "revision": 0,
                "cascade_retry_limit": 3,
                "dialogue_voice_mode": "native",
            }
        },
    )

    assert resp.status_code == 200
    settings = resp.get_json()["global_settings"]
    assert settings["cascade_retry_limit"] == 3
    assert settings["dialogue_voice_mode"] == "native"

    invalid = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 1, "cascade_retry_limit": 2.5}},
    )
    assert invalid.status_code == 400
    assert "cascade_retry_limit" in invalid.get_json()["invalid_keys"]


def test_patch_accepts_postprocess_color_settings_videosection_family(client, tmp_path, monkeypatch):
    """VideoSection.tsx's post-processing / color-grade cluster."""
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.patch(
        f"/api/projects/{pid}",
        json={
            "global_settings": {
                "revision": 0,
                "color_grade_preset": "cool_noir",
                "motion_quality_threshold": 0.6,
                "scene_transitions": True,
                "transition_duration": 1.5,
                "face_swap_enabled": True,
            }
        },
    )

    assert resp.status_code == 200
    settings = resp.get_json()["global_settings"]
    assert settings["color_grade_preset"] == "cool_noir"
    assert settings["motion_quality_threshold"] == 0.6
    assert settings["scene_transitions"] is True
    assert settings["transition_duration"] == 1.5
    assert settings["face_swap_enabled"] is True

    invalid = client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 1, "transition_duration": -0.1}},
    )
    assert invalid.status_code == 400
    assert "transition_duration" in invalid.get_json()["invalid_keys"]
