"""
tests/unit/test_director.py — CinemaDirector v1.0 substrate tests (S15).

Covers llm/director.py — the operator-driven creative iteration translator
distinct from ChiefDirector's pre-gen HC1-HC8 enforcement.

Per S15 acceptance (director-seat REPLY,
coordination/mailbox/archive/2026-05-25T14-56-42Z-director-to-operator-decision.md):
- 2 unit tests: happy-path + structured-output parse failure → graceful fallback

Tests monkey-patch ``_log_root`` to a tmp_path so they don't pollute
``data/intent_log/`` on CI / local runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from domain.models import DirectorialIntent
from llm.director import CinemaDirector


def _make_director_with_mock_client(
    canned_response: str, tmp_path: Path
) -> CinemaDirector:
    """Build a CinemaDirector with a mocked Anthropic client.

    Bypasses _init_client (which needs API keys); injects the mock directly.
    Redirects intent log writes to tmp_path so unit tests don't touch
    the real data/intent_log/ directory.
    """
    director = CinemaDirector(project=None)
    director.provider = "anthropic"
    mock_block = MagicMock()
    mock_block.text = canned_response
    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    director.client = mock_client
    director._log_root = tmp_path  # redirect JSONL logging out of data/
    return director


class TestCinemaDirectorHappyPath:
    """Well-formed LLM response → properly-structured 3-key output."""

    def test_translate_intent_returns_three_required_keys_on_well_formed_response(
        self, tmp_path
    ):
        canned = json.dumps(
            {
                "revised_prompt": "softer, more intimate framing of the character",
                "params_delta": {"denoise_strength": 0.45},
                "anchor_refs": [
                    {
                        "shot_id": "shot_002",
                        "take_id": "take_xyz",
                        "attribute": "lighting",
                    }
                ],
                "reasoning": (
                    "operator wants soft intimacy; pulled lighting "
                    "ref from approved neighbor"
                ),
            }
        )
        director = _make_director_with_mock_client(canned, tmp_path)
        intent = DirectorialIntent(
            prose="make it feel softer and more intimate",
            target_stage="keyframe",
        )
        take_context = {
            "id": "take_abc",
            "kind": "keyframe",
            "prompt": "tight close-up of character",
        }
        scene_context = {"id": "scene_001", "approved_shots": ["shot_002"]}

        result = director.translate_intent(intent, take_context, scene_context)

        # All three required keys present
        assert "revised_prompt" in result
        assert "params_delta" in result
        assert "anchor_refs" in result

        # Values flowed through from canned LLM response
        assert result["revised_prompt"] == (
            "softer, more intimate framing of the character"
        )
        assert result["params_delta"] == {"denoise_strength": 0.45}
        assert len(result["anchor_refs"]) == 1
        assert result["anchor_refs"][0]["shot_id"] == "shot_002"

        # JSONL log line was written to the tmp_path
        log_files = list(tmp_path.rglob("*.jsonl"))
        assert len(log_files) == 1, "expected exactly one JSONL log file written"
        log_line = log_files[0].read_text(encoding="utf-8").strip()
        entry = json.loads(log_line)
        assert entry["intent"]["prose"] == "make it feel softer and more intimate"
        assert entry["output"]["revised_prompt"] == (
            "softer, more intimate framing of the character"
        )
        assert entry.get("note", "") == ""  # happy-path → no error note


class TestCinemaDirectorParseFailureFallback:
    """Malformed LLM response → graceful fallback, no raise, prose passthrough."""

    def test_translate_intent_falls_back_on_malformed_json(self, tmp_path):
        director = _make_director_with_mock_client(
            "this is not json at all, just a sentence the LLM emitted", tmp_path
        )
        intent = DirectorialIntent(
            prose="some operator intent text",
            target_stage="keyframe",
        )
        take_context = {
            "id": "take_abc",
            "kind": "keyframe",
            "prompt": "original prompt body",
        }
        scene_context = {}

        # Must NOT raise — fallback must be silent + non-fatal
        result = director.translate_intent(intent, take_context, scene_context)

        # Fallback shape: intent.prose passthrough as revised_prompt + empty deltas
        assert result["revised_prompt"] == "some operator intent text"
        assert result["params_delta"] == {}
        assert result["anchor_refs"] == []

        # Parse failure was logged with explanatory note
        log_files = list(tmp_path.rglob("*.jsonl"))
        assert len(log_files) == 1
        entry = json.loads(log_files[0].read_text(encoding="utf-8").strip())
        assert entry["note"].startswith("parse_error:")
        # Raw LLM response captured for post-mortem debugging
        assert "not json" in entry["raw_llm_response"]
