"""POST /api/projects/<pid>/apply-language-defaults (slice 9c).

The route (web_server.py:api_apply_language_defaults) and its backing
domain/language_defaults.py contract (merge_language_defaults_into_settings)
had zero test coverage before this slice, despite being fully built and
exactly the contract VoiceSection.tsx's language-change effect now calls.
These tests pin the contract this slice's frontend wiring depends on:
non-destructive merge by default, changed-fields reporting, persistence,
and the overwrite_existing opt-in.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def client():
    import web_server

    web_server.app.config["TESTING"] = True
    with web_server._pipelines_lock:
        web_server._running_pipelines.clear()
        web_server._project_admin_in_flight.clear()
    with web_server._cores_lock:
        web_server._running_cores.clear()
    with web_server.app.test_client() as test_client:
        yield test_client
    with web_server._pipelines_lock:
        web_server._running_pipelines.clear()
        web_server._project_admin_in_flight.clear()
    with web_server._cores_lock:
        web_server._running_cores.clear()


def _make_project(tmp_path, monkeypatch, name: str = "lang-defaults-contract") -> str:
    from domain import project_manager

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    return project_manager.create_project(name)["id"]


def _load(pid):
    from domain import project_manager

    return project_manager.load_project(pid)


def test_fresh_project_applies_english_defaults_and_reports_changed_fields(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.post(
        f"/api/projects/{pid}/apply-language-defaults",
        json={"language": "English", "expected_revision": 0},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["language"] == "English"
    # A fresh project has none of these keys yet -> every applied field
    # (plus "language" itself) shows up as changed.
    assert set(body["changed_fields"]) == {
        "tts_provider", "dialogue_mode_enabled", "forced_alignment_enabled",
        "lipsync_quality_validation", "lipsync_validation_threshold", "language",
    }
    assert body["applied_defaults"]["tts_provider"] == "ELEVENLABS_V3"
    assert "lipsync_engine_priority" not in body["applied_defaults"]
    assert "dialogue_video_api" not in body["applied_defaults"]

    persisted = _load(pid)
    assert persisted["global_settings"]["tts_provider"] == "ELEVENLABS_V3"
    assert persisted["global_settings"]["language"] == "English"
    assert persisted["global_settings"]["revision"] == 1


def test_korean_applies_korean_tuned_defaults_and_recommended_voices(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.post(
        f"/api/projects/{pid}/apply-language-defaults",
        json={"language": "Korean", "expected_revision": 0},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["applied_defaults"]["lipsync_validation_threshold"] == 0.70
    assert "lipsync_engine_priority" not in body["applied_defaults"]
    assert "dialogue_video_api" not in body["applied_defaults"]
    assert body["recommended_voices"]["male"] == "1W00IGEmNmwmsDeYy7ag"  # Junho
    assert body["recommended_voices"]["female"] == "uyVNoMrnUku1dZyVEXwD"  # Anna

    persisted = _load(pid)
    assert persisted["global_settings"]["lipsync_validation_threshold"] == 0.70


def test_customized_field_is_not_overwritten_by_default(client, tmp_path, monkeypatch):
    """Non-destructive by default: a field the operator already set (e.g. an
    explicit Cartesia TTS choice) survives applying a different language's
    defaults -- only genuinely-unset fields get seeded.

    Seeds that field through the legacy whole-object PUT because that is
    VoiceSection.tsx's actual write path (SettingsInspector's `update()`
    PUTs the merged `global_settings`), so the pre-existing value arrives
    the way the UI really writes it. The strict PATCH would accept
    `tts_provider` too now -- a later slice added it, and the rest of
    VoiceSection's fields, to `_SETTINGS_KEY_VALIDATORS` -- but PATCH
    unconditionally demands a `revision` echo, while this brand-new fixture
    project has none established yet and so takes PUT's one-time bootstrap
    accept-and-stamp (`_settings_revision_established`).
    """
    pid = _make_project(tmp_path, monkeypatch)
    put_resp = client.put(
        f"/api/projects/{pid}",
        json={"global_settings": {"tts_provider": "CARTESIA_SONIC_2"}},
    )
    assert put_resp.status_code == 200

    resp = client.post(
        f"/api/projects/{pid}/apply-language-defaults",
        json={"language": "Korean", "expected_revision": 1},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert "tts_provider" not in body["changed_fields"]

    persisted = _load(pid)
    assert persisted["global_settings"]["tts_provider"] == "CARTESIA_SONIC_2"
    # Other, still-unset fields are seeded regardless.
    assert persisted["global_settings"]["lipsync_validation_threshold"] == 0.70


def test_overwrite_existing_true_replaces_a_customized_field(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)
    put_resp = client.put(
        f"/api/projects/{pid}",
        json={"global_settings": {"tts_provider": "CARTESIA_SONIC_2"}},
    )
    assert put_resp.status_code == 200

    resp = client.post(
        f"/api/projects/{pid}/apply-language-defaults",
        json={
            "language": "Korean",
            "overwrite_existing": True,
            "expected_revision": 1,
        },
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert "tts_provider" in body["changed_fields"]

    persisted = _load(pid)
    assert persisted["global_settings"]["tts_provider"] == "ELEVENLABS_V3"


def test_missing_language_in_body_falls_back_to_project_language(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)
    client.patch(
        f"/api/projects/{pid}",
        json={"global_settings": {"revision": 0, "language": "Japanese"}},
    )

    resp = client.post(
        f"/api/projects/{pid}/apply-language-defaults",
        json={"expected_revision": 1},
    )

    assert resp.status_code == 200
    assert resp.get_json()["language"] == "Japanese"


def test_unknown_project_404s(client):
    resp = client.post(
        "/api/projects/does-not-exist/apply-language-defaults",
        json={"language": "English", "expected_revision": 0},
    )
    assert resp.status_code == 404


def test_success_evicts_settings_bound_idle_core(client, tmp_path, monkeypatch):
    import web_server

    pid = _make_project(tmp_path, monkeypatch)
    cached_core = MagicMock()
    with web_server._cores_lock:
        web_server._running_cores[pid] = cached_core

    response = client.post(
        f"/api/projects/{pid}/apply-language-defaults",
        json={"language": "English", "expected_revision": 0},
    )

    assert response.status_code == 200
    assert pid not in web_server._running_cores
    cached_core.cost_tracker.close.assert_called_once_with()


def test_stale_revision_rejects_without_mutation_or_cache_eviction(
    client, tmp_path, monkeypatch
):
    import web_server

    pid = _make_project(tmp_path, monkeypatch)
    first = client.post(
        f"/api/projects/{pid}/apply-language-defaults",
        json={"language": "English", "expected_revision": 0},
    )
    assert first.status_code == 200

    cached_core = MagicMock()
    with web_server._cores_lock:
        web_server._running_cores[pid] = cached_core

    stale = client.post(
        f"/api/projects/{pid}/apply-language-defaults",
        json={"language": "Korean", "expected_revision": 0},
    )

    assert stale.status_code == 409
    body = stale.get_json()
    assert body["code"] == "settings_revision_conflict"
    assert body["current_revision"] == 1
    persisted = _load(pid)
    assert persisted["global_settings"]["language"] == "English"
    assert persisted["global_settings"]["revision"] == 1
    assert web_server._running_cores[pid] is cached_core
    cached_core.cost_tracker.close.assert_not_called()


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"language": "English"}, "revision_required"),
        ({"language": "English", "expected_revision": True}, "invalid_revision"),
        ({"language": "English", "expected_revision": "0"}, "invalid_revision"),
    ],
)
def test_expected_revision_is_required_and_must_be_an_integer(
    client, tmp_path, monkeypatch, payload, code
):
    pid = _make_project(tmp_path, monkeypatch)

    response = client.post(
        f"/api/projects/{pid}/apply-language-defaults",
        json=payload,
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == code
