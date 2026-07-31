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

import pytest


@pytest.fixture
def client():
    import web_server

    web_server.app.config["TESTING"] = True
    web_server._running_pipelines.clear()
    with web_server.app.test_client() as test_client:
        yield test_client
    web_server._running_pipelines.clear()


def _make_project(tmp_path, monkeypatch, name: str = "lang-defaults-contract") -> str:
    from domain import project_manager

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    return project_manager.create_project(name)["id"]


def _load(pid):
    from domain import project_manager

    return project_manager.load_project(pid)


def test_fresh_project_applies_english_defaults_and_reports_changed_fields(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.post(f"/api/projects/{pid}/apply-language-defaults", json={"language": "English"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["language"] == "English"
    # A fresh project has none of these keys yet -> every applied field
    # (plus "language" itself) shows up as changed.
    assert set(body["changed_fields"]) == {
        "tts_provider", "dialogue_mode_enabled", "forced_alignment_enabled",
        "lipsync_engine_priority", "lipsync_quality_validation",
        "lipsync_validation_threshold", "language",
    }
    assert body["applied_defaults"]["tts_provider"] == "ELEVENLABS_V3"

    persisted = _load(pid)
    assert persisted["global_settings"]["tts_provider"] == "ELEVENLABS_V3"
    assert persisted["global_settings"]["language"] == "English"


def test_korean_applies_korean_tuned_defaults_and_recommended_voices(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)

    resp = client.post(f"/api/projects/{pid}/apply-language-defaults", json={"language": "Korean"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["applied_defaults"]["lipsync_validation_threshold"] == 0.70
    assert body["applied_defaults"]["lipsync_engine_priority"][0] == "SYNC_SO_V3"
    assert body["recommended_voices"]["male"] == "1W00IGEmNmwmsDeYy7ag"  # Junho
    assert body["recommended_voices"]["female"] == "uyVNoMrnUku1dZyVEXwD"  # Anna

    persisted = _load(pid)
    assert persisted["global_settings"]["lipsync_validation_threshold"] == 0.70


def test_customized_field_is_not_overwritten_by_default(client, tmp_path, monkeypatch):
    """Non-destructive by default: a field the operator already set (e.g. an
    explicit Cartesia TTS choice) survives applying a different language's
    defaults -- only genuinely-unset fields get seeded.

    Uses the legacy whole-object PUT (VoiceSection.tsx's actual write path
    via SettingsInspector's `update()`) rather than the new strict PATCH --
    `tts_provider` is not yet in PATCH's `_SETTINGS_KEY_VALIDATORS` table
    (see the comment above that table: extending it for VoiceSection's
    fields is out of this slice's `web_server.py` pathspec, which is
    scoped to the language-defaults route only).
    """
    pid = _make_project(tmp_path, monkeypatch)
    put_resp = client.put(
        f"/api/projects/{pid}",
        json={"global_settings": {"tts_provider": "CARTESIA_SONIC_2"}},
    )
    assert put_resp.status_code == 200

    resp = client.post(f"/api/projects/{pid}/apply-language-defaults", json={"language": "Korean"})

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
        json={"language": "Korean", "overwrite_existing": True},
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

    resp = client.post(f"/api/projects/{pid}/apply-language-defaults", json={})

    assert resp.status_code == 200
    assert resp.get_json()["language"] == "Japanese"


def test_unknown_project_404s(client):
    resp = client.post("/api/projects/does-not-exist/apply-language-defaults", json={"language": "English"})
    assert resp.status_code == 404
