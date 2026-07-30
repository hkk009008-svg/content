"""Hard containment policy for dormant per-character LoRA.

This module is intentionally dependency-free and contains no enable switch.
Reactivation requires a separately reviewed code change and superseding ADR.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite


LORA_POLICY = "dormant"
LORA_TRAINING_DORMANT = "lora_training_dormant"
LORA_ACTIVATION_DORMANT = "lora_activation_dormant"
PROTECTED_LORA_FIELDS = (
    "char_lora_paths",
    "char_lora_strengths",
    "char_lora_triggers",
)


def lora_training_dormant_error() -> dict[str, object]:
    """Return the stable machine-readable training denial."""
    return {
        "error": "Per-character LoRA training is dormant",
        "code": LORA_TRAINING_DORMANT,
        "started": False,
        "retryable": False,
        "consumer_status": LORA_POLICY,
    }


def lora_activation_dormant_error(fields: Sequence[str]) -> dict[str, object]:
    """Return the stable machine-readable registry/update denial."""
    return {
        "error": "Per-character LoRA activation is dormant",
        "code": LORA_ACTIVATION_DORMANT,
        "fields": sorted(set(fields)),
        "retryable": False,
    }


def lora_dormant_status_fields() -> dict[str, object]:
    """Availability projection added to backward-compatible status payloads."""
    return {
        "training_available": False,
        "registration_available": False,
        "consumer_available": False,
        "policy": LORA_POLICY,
    }


def _json_values_equal_strict(current: object, incoming: object) -> bool:
    """Recursively compare JSON values by their JSON type semantics."""
    current_is_number = type(current) in (int, float)
    incoming_is_number = type(incoming) in (int, float)
    if current_is_number or incoming_is_number:
        return (
            current_is_number
            and incoming_is_number
            and (type(current) is not float or isfinite(current))
            and (type(incoming) is not float or isfinite(incoming))
            and current == incoming
        )
    if type(current) is not type(incoming):
        return False
    if isinstance(current, Mapping):
        return (
            len(current) == len(incoming)
            and all(
                key in incoming
                and _json_values_equal_strict(current[key], incoming[key])
                for key in current
            )
        )
    if isinstance(current, list):
        return len(current) == len(incoming) and all(
            _json_values_equal_strict(current_item, incoming_item)
            for current_item, incoming_item in zip(current, incoming)
        )
    return current == incoming


def changed_protected_lora_fields(
    current_settings: object,
    incoming_settings: object,
) -> list[str]:
    """Return protected keys whose incoming values differ from latest state.

    Only explicitly supplied protected keys participate. A legacy value may
    therefore round-trip unchanged, while adding a previously absent key
    (including an empty value) is still treated as an activation change.
    """
    if not isinstance(incoming_settings, Mapping):
        return []
    current = current_settings if isinstance(current_settings, Mapping) else {}
    return sorted(
        key
        for key in PROTECTED_LORA_FIELDS
        if key in incoming_settings
        and (
            key not in current
            or not _json_values_equal_strict(current[key], incoming_settings[key])
        )
    )


class LoraTrainingDormantError(RuntimeError):
    """Guard-first exception for internal raw-training entry points."""

    def __init__(self) -> None:
        self.payload = lora_training_dormant_error()
        super().__init__(self.payload["error"])


class LoraActivationDormantError(RuntimeError):
    """Abort a locked project mutation without saving any partial update."""

    def __init__(self, fields: Sequence[str]) -> None:
        self.fields = sorted(set(fields))
        self.payload = lora_activation_dormant_error(self.fields)
        super().__init__(self.payload["error"])
