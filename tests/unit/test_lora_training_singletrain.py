"""Guard-first tests for the preserved dormant local LoRA trainer."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import prep.lora_training as lt
from prep.lora_policy import LoraTrainingDormantError


EXPECTED_TRAINING_DENIAL = {
    "error": "Per-character LoRA training is dormant",
    "code": "lora_training_dormant",
    "started": False,
    "retryable": False,
    "consumer_status": "dormant",
}


def _bomb(*_args, **_kwargs):
    raise AssertionError("dormant trainer crossed an operational boundary")


def test_train_character_lora_denies_before_status_dataset_or_trainer():
    character = {"id": "char-never-read"}
    with (
        patch.object(lt, "_character_lora_dir", side_effect=_bomb),
        patch.object(lt, "_write_status", side_effect=_bomb),
        patch.object(lt, "prepare_character_lora_dataset", side_effect=_bomb),
        patch.object(lt, "_detect_trainer", side_effect=_bomb),
        patch.object(lt, "_write_ai_toolkit_config", side_effect=_bomb),
        patch.object(lt, "_run_ai_toolkit", side_effect=_bomb),
    ):
        result = lt.train_character_lora(
            "/project",
            character,
            config_overrides={"steps": 1, "enabled": True},
        )

    assert result == EXPECTED_TRAINING_DENIAL


def test_run_ai_toolkit_denies_before_log_or_subprocess():
    with (
        patch("builtins.open", side_effect=_bomb),
        patch.object(lt.subprocess, "run", side_effect=_bomb),
    ):
        with pytest.raises(LoraTrainingDormantError) as exc_info:
            lt._run_ai_toolkit("/config.yaml", "/train.log")

    assert exc_info.value.payload == EXPECTED_TRAINING_DENIAL


def test_train_character_lora_no_validate_stub_defined():
    assert not hasattr(lt, "validate_lora_quality")
    assert not hasattr(lt, "LORA_VALIDATION_SKIPPED")
