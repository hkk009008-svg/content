"""Shared optimizer-cache contract for public writes and historical reads.

Public replacement payloads must match the producer's known JSON field types.
Historical project files remain loadable, but malformed known values are
filtered before they can influence prompt or engine routing.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final


FieldType = type | tuple[type, ...]

OPTIMIZER_CACHE_FIELD_TYPES: Final[Mapping[str, FieldType]] = MappingProxyType({
    "source_prompt": str,
})

OPTIMIZER_SPEC_FIELD_TYPES: Final[Mapping[str, FieldType]] = MappingProxyType({
    "image_prompt": str,
    "video_prompt": str,
    "purpose": str,
    "shot_type": str,
    "suggested_video_api": str,
    "suggested_lipsync": (str, type(None)),
    "negative_constraints": str,
    "identity_anchor": str,
    "camera": str,
    "lighting": str,
    "color_palette": str,
    "reasoning": str,
})


def optimizer_cache_is_valid(value: object) -> bool:
    """Return whether a public cache has the known producer field types."""

    if not isinstance(value, Mapping):
        return False
    if not _known_fields_are_valid(value, OPTIMIZER_CACHE_FIELD_TYPES):
        return False
    if "spec" not in value:
        return True
    spec = value["spec"]
    return (
        isinstance(spec, Mapping)
        and _known_fields_are_valid(spec, OPTIMIZER_SPEC_FIELD_TYPES)
    )


def sanitize_optimizer_cache(value: object) -> dict[str, Any]:
    """Copy a historical cache while dropping malformed known fields.

    Unknown fields are retained for forward compatibility. They are not read by
    typed consumers. A malformed outer cache becomes empty; a malformed
    ``spec`` is omitted; malformed known child fields are removed individually.
    """

    if not isinstance(value, Mapping):
        return {}

    sanitized = _sanitize_known_fields(value, OPTIMIZER_CACHE_FIELD_TYPES)
    if "spec" not in value:
        return sanitized

    spec = value["spec"]
    if isinstance(spec, Mapping):
        sanitized["spec"] = _sanitize_known_fields(
            spec,
            OPTIMIZER_SPEC_FIELD_TYPES,
        )
    else:
        sanitized.pop("spec", None)
    return sanitized


def sanitize_optimizer_spec(value: object) -> dict[str, Any]:
    """Copy one optimizer spec while dropping malformed known fields."""

    if not isinstance(value, Mapping):
        return {}
    return _sanitize_known_fields(value, OPTIMIZER_SPEC_FIELD_TYPES)


def _known_fields_are_valid(
    value: Mapping[str, object],
    field_types: Mapping[str, FieldType],
) -> bool:
    return all(
        field not in value or isinstance(value[field], expected_type)
        for field, expected_type in field_types.items()
    )


def _sanitize_known_fields(
    value: Mapping[str, Any],
    field_types: Mapping[str, FieldType],
) -> dict[str, Any]:
    return {
        field: item
        for field, item in value.items()
        if (
            field not in field_types
            or isinstance(item, field_types[field])
        )
    }
