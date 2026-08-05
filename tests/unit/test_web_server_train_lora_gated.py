"""Fail-closed HTTP contract for dormant per-character LoRA."""

from __future__ import annotations

import builtins
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

import prep.lora_quality
import prep.lora_training
from web_server import app


PID = "proj-dormant"
CID = "char-dormant"
TRAIN_PATH = f"/api/projects/{PID}/characters/{CID}/train-lora"
EXPECTED_TRAINING_DENIAL = {
    "error": "Per-character LoRA training is dormant",
    "code": "lora_training_dormant",
    "started": False,
    "retryable": False,
    "consumer_status": "dormant",
}


def _bomb(*_args, **_kwargs):
    raise AssertionError("dormant endpoint crossed an operational boundary")


@pytest.fixture(autouse=True)
def configure_app():
    app.config["TESTING"] = True
    yield


@pytest.mark.parametrize(
    "body,suffix",
    [
        ({}, ""),
        ({"config_overrides": {"steps": 1}}, ""),
        ({"enabled": True, "consumer_available": True}, "?enable_lora=1"),
    ],
)
def test_train_lora_returns_exact_409_before_any_operation(body, suffix):
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name in {"prep.lora_quality", "prep.lora_training"}:
            raise AssertionError(f"dormant endpoint imported {name}")
        return real_import(name, *args, **kwargs)

    with (
        patch("web_server.load_project", side_effect=_bomb),
        patch("web_server.get_project_dir", side_effect=_bomb),
        patch("web_server.mutate_project", side_effect=_bomb),
        patch("web_server.threading.Thread", side_effect=_bomb),
        patch.object(prep.lora_quality, "train_character_lora_gated", side_effect=_bomb),
        patch.object(prep.lora_training, "record_lora_verdict", side_effect=_bomb),
        patch.object(prep.lora_training, "_write_status", side_effect=_bomb),
        patch("builtins.__import__", side_effect=guarded_import),
    ):
        with app.test_client() as client:
            response = client.post(TRAIN_PATH + suffix, json=body)

    assert response.status_code == 409
    assert response.get_json() == EXPECTED_TRAINING_DENIAL


def test_repeated_and_concurrent_attempts_never_insert_a_thread():
    def attempt():
        with app.test_client() as client:
            response = client.post(
                TRAIN_PATH,
                json={"config_overrides": {"rank": 1}, "force": True},
            )
            return response.status_code, response.get_json()

    with (
        patch("web_server.load_project", side_effect=_bomb),
        patch("web_server.get_project_dir", side_effect=_bomb),
        patch("web_server.mutate_project", side_effect=_bomb),
    ):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _index: attempt(), range(24)))

    assert results == [(409, EXPECTED_TRAINING_DENIAL)] * 24


def test_lora_status_preserves_history_and_projects_dormant_availability():
    historical = {
        "char_id": CID,
        "status": "done",
        "progress_percent": 100.0,
        "lora_path": "/legacy/char.safetensors",
        "quality_score": 0.72,
    }
    with (
        patch("web_server.get_project_dir", return_value="/project"),
        patch.object(prep.lora_training, "get_lora_status", return_value=historical),
    ):
        with app.test_client() as client:
            response = client.get(
                f"/api/projects/{PID}/characters/{CID}/lora-status"
            )

    assert response.status_code == 200
    assert response.get_json() == {
        **historical,
        "training_available": False,
        "registration_available": False,
        "consumer_available": False,
        "policy": "dormant",
    }
