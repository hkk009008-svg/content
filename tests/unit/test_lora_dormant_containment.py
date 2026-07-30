"""Cross-entrypoint containment tests for dormant per-character LoRA."""

from __future__ import annotations

import builtins
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import domain.project_manager as project_manager
import prep.lora_policy as policy
import scripts._fal_lora_train as fal_lora
import scripts._fal_man_lora_train as fal_man_lora
import scripts._register_aria_lora as register_lora
import web_server


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TRAINING_DENIAL = {
    "error": "Per-character LoRA training is dormant",
    "code": "lora_training_dormant",
    "started": False,
    "retryable": False,
    "consumer_status": "dormant",
}


def _bomb(*_args, **_kwargs):
    raise AssertionError("dormant path crossed a protected boundary")


def test_policy_detects_only_new_or_changed_protected_fields():
    current = {
        "char_lora_paths": {"c1": "/legacy.safetensors"},
        "char_lora_strengths": {"c1": 0.55},
        "unrelated": "old",
    }
    incoming = {
        "char_lora_paths": {"c1": "/legacy.safetensors"},
        "char_lora_strengths": {"c1": 0.7},
        "char_lora_triggers": {},
        "unrelated": "new",
    }

    assert policy.changed_protected_lora_fields(current, incoming) == [
        "char_lora_strengths",
        "char_lora_triggers",
    ]
    assert policy.changed_protected_lora_fields(
        current,
        {"char_lora_paths": {"c1": "/legacy.safetensors"}},
    ) == []


@pytest.fixture()
def persisted_project(tmp_path, monkeypatch):
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path))
    project = project_manager.create_project("Dormant LoRA")

    def seed_legacy(latest):
        latest["global_settings"].update({
            "char_lora_paths": {"c1": "/legacy.safetensors"},
            "char_lora_strengths": {"c1": 0.55},
        })

    project_manager.mutate_project(project["id"], seed_legacy)
    web_server.app.config["TESTING"] = True
    web_server._running_pipelines.pop(project["id"], None)
    return project


def test_project_put_allows_unchanged_legacy_lora_round_trip(persisted_project):
    pid = persisted_project["id"]
    with web_server.app.test_client() as client:
        response = client.put(
            f"/api/projects/{pid}",
            json={
                "name": "Renamed safely",
                "global_settings": {
                    "char_lora_paths": {"c1": "/legacy.safetensors"},
                    "char_lora_strengths": {"c1": 0.55},
                    "music_mood": "hopeful",
                },
            },
        )

    assert response.status_code == 200
    latest = project_manager.load_project(pid)
    assert latest["name"] == "Renamed safely"
    assert latest["global_settings"]["music_mood"] == "hopeful"
    assert latest["global_settings"]["char_lora_paths"] == {
        "c1": "/legacy.safetensors"
    }


def test_project_put_rejects_changed_and_new_lora_fields_atomically(
    persisted_project,
):
    pid = persisted_project["id"]
    project_path = Path(project_manager.PROJECTS_DIR) / pid / "project.json"
    before = project_path.read_bytes()

    with web_server.app.test_client() as client:
        response = client.put(
            f"/api/projects/{pid}",
            json={
                "name": "Must not land",
                "global_settings": {
                    "music_mood": "must-not-land",
                    "char_lora_triggers": {"c1": "TOKnew"},
                    "char_lora_paths": {"c1": "/changed.safetensors"},
                    "char_lora_strengths": {"c1": 0.55},
                },
            },
        )

    assert response.status_code == 409
    assert response.get_json() == {
        "error": "Per-character LoRA activation is dormant",
        "code": "lora_activation_dormant",
        "fields": ["char_lora_paths", "char_lora_triggers"],
        "retryable": False,
    }
    assert project_path.read_bytes() == before


def test_public_script_mains_exit_two_before_paid_or_registry_work(capsys):
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in {"fal_client", "domain.project_manager"}:
            raise AssertionError(f"dormant script imported {name}")
        return real_import(name, *args, **kwargs)

    with (
        patch("builtins.open", side_effect=_bomb),
        patch("builtins.__import__", side_effect=guarded_import),
        patch.object(fal_lora.requests, "get", side_effect=_bomb),
        patch.object(fal_man_lora, "_load_fal_client", side_effect=_bomb),
        patch.object(register_lora.os.path, "exists", side_effect=_bomb),
    ):
        assert fal_lora.main() == 2
        assert fal_man_lora.main() == 2
        assert register_lora.main() == 2

    payloads = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]
    assert payloads[:2] == [EXPECTED_TRAINING_DENIAL] * 2
    assert payloads[2] == {
        "error": "Per-character LoRA activation is dormant",
        "code": "lora_activation_dormant",
        "fields": list(policy.PROTECTED_LORA_FIELDS),
        "retryable": False,
    }


def test_generate_refs_is_independently_denied_before_provider_or_files():
    with (
        patch.object(fal_man_lora, "_load_fal_client", side_effect=_bomb),
        patch.object(fal_man_lora.os, "makedirs", side_effect=_bomb),
    ):
        with pytest.raises(policy.LoraTrainingDormantError) as exc_info:
            fal_man_lora.generate_refs()

    assert exc_info.value.payload == EXPECTED_TRAINING_DENIAL


@pytest.mark.parametrize(
    "command,expected_code",
    [
        ([sys.executable, "-m", "prep.lora_training"], "lora_training_dormant"),
        ([sys.executable, "scripts/_fal_lora_train.py"], "lora_training_dormant"),
        ([sys.executable, "scripts/_fal_man_lora_train.py"], "lora_training_dormant"),
        ([sys.executable, "scripts/_register_aria_lora.py"], "lora_activation_dormant"),
    ],
)
def test_cli_entrypoints_exit_two_with_structured_failure(command, expected_code):
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )

    assert completed.returncode == 2, completed.stderr
    payload = json.loads(completed.stdout.strip())
    assert payload["code"] == expected_code
    assert payload["retryable"] is False
