"""Direct unit pins for the shared optimizer-cache contract.

`tests/unit/test_optimizer_cache_boundary.py` proves both real controller
consumers survive historical malformed caches; `test_web_server_video_targets`
proves the public HTTP boundary rejects malformed replacements. This module
pins the shared helpers themselves — especially the sanitize semantics that
the inline predecessors did not have: malformed KNOWN fields are dropped
individually while unknown fields survive for forward compatibility.
"""

from __future__ import annotations

import pytest

from domain.optimizer_cache import (
    OPTIMIZER_SPEC_FIELD_TYPES,
    optimizer_cache_is_valid,
    sanitize_optimizer_cache,
    sanitize_optimizer_spec,
)


class TestOptimizerCacheIsValid:
    def test_accepts_well_typed_cache_with_spec(self):
        assert optimizer_cache_is_valid(
            {
                "source_prompt": "a prompt",
                "spec": {
                    "image_prompt": "p",
                    "suggested_lipsync": None,
                    "unknown_future_field": [1, 2],
                },
            },
        )

    def test_accepts_cache_without_spec(self):
        assert optimizer_cache_is_valid({"source_prompt": "a prompt"})

    @pytest.mark.parametrize(
        "malformed",
        [
            None,
            "text",
            ["list"],
            {"source_prompt": 7},
            {"spec": "not-a-mapping"},
            {"spec": ["not-a-mapping"]},
            {"spec": None},
            {"spec": {"image_prompt": 7}},
            {"spec": {"suggested_lipsync": 3.5}},
        ],
    )
    def test_rejects_malformed_shapes(self, malformed):
        assert not optimizer_cache_is_valid(malformed)


class TestSanitizeOptimizerCache:
    def test_non_mapping_becomes_empty(self):
        assert sanitize_optimizer_cache("legacy-string") == {}
        assert sanitize_optimizer_cache(None) == {}
        assert sanitize_optimizer_cache(["legacy"]) == {}

    def test_malformed_known_outer_field_is_dropped_individually(self):
        out = sanitize_optimizer_cache(
            {"source_prompt": 7, "unknown": "kept"},
        )
        assert out == {"unknown": "kept"}

    def test_non_mapping_spec_is_removed(self):
        out = sanitize_optimizer_cache(
            {"source_prompt": "p", "spec": ["not-a-mapping"]},
        )
        assert out == {"source_prompt": "p"}

    def test_malformed_known_spec_children_are_dropped_individually(self):
        out = sanitize_optimizer_cache(
            {
                "source_prompt": "p",
                "spec": {
                    "image_prompt": 7,
                    "video_prompt": "kept",
                    "suggested_lipsync": None,
                    "unknown_child": {"kept": True},
                },
            },
        )
        assert out == {
            "source_prompt": "p",
            "spec": {
                "video_prompt": "kept",
                "suggested_lipsync": None,
                "unknown_child": {"kept": True},
            },
        }

    def test_result_is_a_fresh_dict_not_the_input(self):
        source = {"source_prompt": "p", "spec": {"image_prompt": "x"}}
        out = sanitize_optimizer_cache(source)
        assert out == source
        assert out is not source
        assert out["spec"] is not source["spec"]


class TestSanitizeOptimizerSpec:
    def test_non_mapping_becomes_empty(self):
        assert sanitize_optimizer_spec(None) == {}
        assert sanitize_optimizer_spec("text") == {}

    def test_every_known_field_type_is_enforced(self):
        malformed = {field: object() for field in OPTIMIZER_SPEC_FIELD_TYPES}
        assert sanitize_optimizer_spec(malformed) == {}

    def test_valid_fields_and_unknown_fields_survive(self):
        spec = {
            "purpose": "dialogue_close_up",
            "suggested_lipsync": None,
            "future_field": 3,
        }
        assert sanitize_optimizer_spec(spec) == spec
