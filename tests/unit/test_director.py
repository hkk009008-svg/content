"""
tests/unit/test_director.py — CinemaDirector v1.0 substrate tests (S15) + verb DSL (S18).

Covers llm/director.py — the operator-driven creative iteration translator
distinct from ChiefDirector's pre-gen HC1-HC8 enforcement.

Per S15 acceptance (director-seat REPLY,
coordination/mailbox/archive/2026-05-25T14-56-42Z-director-to-operator-decision.md):
- 2 unit tests: happy-path + structured-output parse failure → graceful fallback

Per S18: 5 additional tests cover the verb DSL prefix-injection path and the
unknown-verb fallback contract. Tests assert on the user_prompt forwarded to
_call_llm (we mock the LLM call itself) so verb wiring is checked without
requiring API keys.

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


# ─── S18: verb DSL prefix-injection tests ───────────────────────────────

def _captured_user_prompt(director: CinemaDirector) -> str:
    """Pull the user-prompt string forwarded to the mocked Anthropic client.

    Mirrors the Anthropic call signature used in CinemaDirector._call_llm:
    ``client.messages.create(messages=[{role: user, content: <prompt>}], ...)``
    """
    call_kwargs = director.client.messages.create.call_args.kwargs
    messages = call_kwargs["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    return messages[0]["content"]


def _canned_response() -> str:
    """A well-formed canned response — verb tests focus on the user prompt,
    not on the LLM's output schema (which the S15 happy-path test covers)."""
    return json.dumps({
        "revised_prompt": "translated",
        "params_delta": {},
        "anchor_refs": [],
        "reasoning": "verb test",
    })


class TestCinemaDirectorVerbDSL:
    """S18: structured verb DSL — verb-specific user-prompt prefix injection."""

    def test_tighten_framing_injects_verb_prefix_with_degree(self, tmp_path):
        """verb=tighten_framing with degree=moderate → user_prompt carries the verb block."""
        director = _make_director_with_mock_client(_canned_response(), tmp_path)
        intent = DirectorialIntent(
            prose="closer in on the face",
            verb="tighten_framing",
            params={"degree": "moderate"},
            target_stage="keyframe",
        )
        result = director.translate_intent(
            intent,
            {"id": "take_abc", "kind": "keyframe", "prompt": "wide shot of character"},
            {"id": "scene_001", "approved_shots": []},
        )
        # Result still parses cleanly (verb routing doesn't break parsing).
        assert result["revised_prompt"] == "translated"

        prompt = _captured_user_prompt(director)
        assert 'verb="tighten_framing"' in prompt
        assert "moderate" in prompt
        # The verb prefix sits BEFORE the JSON payload (per-call injection,
        # not system-prompt append — preserves cache surface for freeform).
        assert prompt.index("<VERB_GUIDANCE") < prompt.index('"task":')

    def test_match_shot_with_valid_ref_pulls_reference_attributes(self, tmp_path):
        """verb=match_shot with ref_shot_id in approved_shots → ref summary embedded in prefix."""
        director = _make_director_with_mock_client(_canned_response(), tmp_path)
        intent = DirectorialIntent(
            prose="match the lighting from the earlier shot",
            verb="match_shot",
            params={"ref_shot_id": "shot_1_2", "attributes": ["lighting", "mood"]},
            target_stage="keyframe",
        )
        scene_context = {
            "id": "scene_001",
            "approved_shots": [
                {
                    "id": "shot_1_2",
                    "prompt": "moody warm-amber close-up under tungsten",
                    "camera": "close-up",
                    "continuity_constraints": "warm-amber tungsten",
                    "visual_effect": "",
                }
            ],
        }
        director.translate_intent(
            intent,
            {"id": "take_abc", "kind": "keyframe", "prompt": "neutral mid-shot"},
            scene_context,
        )
        prompt = _captured_user_prompt(director)
        assert 'verb="match_shot"' in prompt
        assert "shot_1_2" in prompt
        assert "lighting" in prompt and "mood" in prompt
        # Reference shot's attribute language flowed into the prefix
        assert "warm-amber" in prompt
        # status="ref_not_found" must NOT be set — the ref was found
        assert "ref_not_found" not in prompt

    def test_match_shot_with_missing_ref_emits_ref_not_found_marker(self, tmp_path):
        """verb=match_shot with ref_shot_id NOT in approved_shots → graceful degrade prefix."""
        director = _make_director_with_mock_client(_canned_response(), tmp_path)
        intent = DirectorialIntent(
            prose="match a shot we never approved",
            verb="match_shot",
            params={"ref_shot_id": "shot_NONEXISTENT", "attributes": ["lighting"]},
            target_stage="keyframe",
        )
        scene_context = {
            "id": "scene_001",
            "approved_shots": [{"id": "shot_other_id", "prompt": "..."}],
        }
        result = director.translate_intent(
            intent,
            {"id": "take_abc", "kind": "keyframe", "prompt": "mid-shot"},
            scene_context,
        )
        # Still returns the three-key shape — graceful degrade, not raise
        assert "revised_prompt" in result

        prompt = _captured_user_prompt(director)
        assert 'verb="match_shot"' in prompt
        assert "ref_not_found" in prompt
        assert "shot_NONEXISTENT" in prompt
        # Do NOT invent matching details — the LLM must be told to fall back to prose
        assert "do not invent" in prompt.lower()

    def test_shift_emotion_injects_direction_and_target(self, tmp_path):
        """verb=shift_emotion with direction+target → prefix carries both axes."""
        director = _make_director_with_mock_client(_canned_response(), tmp_path)
        intent = DirectorialIntent(
            prose="more intensity in this moment",
            verb="shift_emotion",
            params={"direction": "intensify", "target": "noticeable"},
            target_stage="performance",
        )
        director.translate_intent(
            intent,
            {"id": "take_abc", "kind": "performance", "prompt": "neutral expression"},
            {"id": "scene_001", "approved_shots": []},
        )
        prompt = _captured_user_prompt(director)
        assert 'verb="shift_emotion"' in prompt
        assert "intensify" in prompt
        assert "noticeable" in prompt
        # Direction-specific axis hint flowed in (intensify → sharper)
        assert "sharper" in prompt or "more intense" in prompt

    def test_unknown_verb_falls_back_to_freeform_with_no_prefix(self, tmp_path, capsys):
        """verb='alien_verb' → log line emitted, no <VERB_GUIDANCE> block in prompt."""
        director = _make_director_with_mock_client(_canned_response(), tmp_path)
        intent = DirectorialIntent(
            prose="just regular freeform prose",
            verb="alien_verb",  # not in KNOWN_VERBS
            params={"foo": "bar"},
            target_stage="keyframe",
        )
        result = director.translate_intent(
            intent,
            {"id": "take_abc", "kind": "keyframe", "prompt": "x"},
            {"id": "scene_001", "approved_shots": []},
        )
        assert "revised_prompt" in result

        prompt = _captured_user_prompt(director)
        # No verb block injected — falls back to freeform user prompt
        assert "<VERB_GUIDANCE" not in prompt
        # The fallback path emitted the unknown-verb log line
        captured = capsys.readouterr()
        assert "unknown verb 'alien_verb'" in captured.out
        # Lane V #6 F3 lock: the unknown verb is ALSO stripped from the LLM's
        # view of `intent` so the payload doesn't carry an orphan verb key
        # without an accompanying VERB_GUIDANCE block.
        assert "alien_verb" not in prompt
