"""
tests/unit/test_chief_director_parse.py — TE-C-D3-1

Regression tests for ChiefDirector JSON-robustness (Dispatch 1, C-D3 pt1).

Covers three parse-path scenarios for validate_shot_prompts:
  (a) fenced JSON → real decision reached, no parse-error logged
  (b) garbage on attempt-1 + valid JSON on attempt-2 → retry fires, real decision
  (c) garbage on both attempts → flagged deterministic fallback, contract keys present

Mocking style mirrors tests/unit/test_director.py:
  - Inject mock client directly (bypass _init_client / API keys)
  - Mock _call_llm as the public boundary (avoids deep Anthropic SDK wiring)
  - capsys for log-line assertions
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from llm.chief_director import ChiefDirector


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_chief_director() -> ChiefDirector:
    """Build a ChiefDirector with a stub project — no API keys needed."""
    cd = ChiefDirector(project={})
    # Prevent _init_client from trying real API keys
    cd.client = MagicMock()
    cd.provider = "anthropic"
    return cd


def _minimal_shots() -> list:
    return [{"prompt": "[SHOT]close-up[SCENE]office[ACTION]facing camera[OUTFIT]wool suit[QUALITY]photorealistic"}]


def _minimal_scene() -> dict:
    return {"title": "test_scene", "action": "", "location_id": "office_01", "characters_present": []}


def _approved_json() -> str:
    return json.dumps({
        "decision": "APPROVED",
        "violations": [],
        "modifications": [],
        "quality_score": 0.9,
        "reasoning": "all checks passed",
    })


def _blocked_json() -> str:
    return json.dumps({
        "decision": "BLOCKED",
        "violations": ["HC2: describes blue eyes"],
        "modifications": [],
        "quality_score": 0.2,
        "reasoning": "identity firewall triggered",
    })


# ─── (a) fenced JSON → real decision, no parse-error log ────────────────────

class TestFencedJsonParsesToRealDecision:
    """LLM wraps response in ```json fences → fence-tolerant parse extracts real decision."""

    def test_fenced_approved_returns_approved_decision(self, capsys):
        cd = _make_chief_director()
        fenced = f"```json\n{_approved_json()}\n```"

        with patch.object(cd, "_call_llm", return_value=fenced):
            result = cd.validate_shot_prompts(_minimal_shots(), _minimal_scene())

        assert result["decision"] == "APPROVED"
        assert "violations" in result
        assert "shots" in result

        out = capsys.readouterr().out
        # The observable success marker: decision= line present
        assert "decision=APPROVED" in out
        # No parse-error line (the repairable path)
        assert "parse error" not in out.lower()
        assert "Evaluation parse error" not in out

    def test_fenced_blocked_returns_blocked_decision(self, capsys):
        cd = _make_chief_director()
        fenced = f"```json\n{_blocked_json()}\n```"

        with patch.object(cd, "_call_llm", return_value=fenced):
            result = cd.validate_shot_prompts(_minimal_shots(), _minimal_scene())

        assert result["decision"] == "BLOCKED"
        assert len(result["violations"]) == 1
        assert "shots" in result

        out = capsys.readouterr().out
        assert "decision=BLOCKED" in out
        assert "Evaluation parse error" not in out


# ─── (b) garbage attempt-1, valid JSON attempt-2 → retry fires ──────────────

class TestRetryPathFiresOnFirstParseFailure:
    """First LLM call returns garbage; second returns valid JSON → retry path."""

    def test_retry_fires_and_returns_real_decision(self, capsys):
        cd = _make_chief_director()
        call_sequence = iter(["this is not json at all <<>>", _approved_json()])

        with patch.object(cd, "_call_llm", side_effect=call_sequence) as mock_llm:
            result = cd.validate_shot_prompts(_minimal_shots(), _minimal_scene())

        # LLM was called twice (original + retry-with-correction)
        assert mock_llm.call_count == 2

        # The correction string must have been appended to the second call's user_prompt
        _system, retry_user_prompt = mock_llm.call_args_list[1].args
        assert "not valid JSON" in retry_user_prompt

        # Real decision reached from the second call
        assert result["decision"] == "APPROVED"
        assert "violations" in result
        assert "shots" in result

        out = capsys.readouterr().out
        # Real decision logged — NOT the fallback marker
        assert "decision=APPROVED" in out
        assert "parse-fallback" not in out
        assert "Evaluation parse error" not in out

    def test_retry_with_blocked_second_response(self, capsys):
        cd = _make_chief_director()
        call_sequence = iter(["```not-json{{{", _blocked_json()])

        with patch.object(cd, "_call_llm", side_effect=call_sequence) as mock_llm:
            result = cd.validate_shot_prompts(_minimal_shots(), _minimal_scene())

        assert mock_llm.call_count == 2
        assert result["decision"] == "BLOCKED"
        out = capsys.readouterr().out
        assert "decision=BLOCKED" in out
        assert "parse-fallback" not in out


# ─── (c) garbage on both attempts → flagged deterministic fallback ───────────

class TestFallbackAfterBothAttemptsFail:
    """Both LLM calls return unparseable content → flagged deterministic fallback."""

    def test_fallback_returns_contract_keys_and_emits_observable_log(self, capsys):
        cd = _make_chief_director()
        garbage = "nope, still not JSON {unterminated"

        with patch.object(cd, "_call_llm", side_effect=[garbage, garbage]) as mock_llm:
            result = cd.validate_shot_prompts(_minimal_shots(), _minimal_scene())

        # LLM called exactly twice (original + one retry-with-correction)
        assert mock_llm.call_count == 2

        # Contract keys present
        assert "decision" in result
        assert "violations" in result
        assert "shots" in result

        # Fallback decision is deterministic (APPROVED for throughput fail-safe)
        assert result["decision"] == "APPROVED"

        # Observable flagged log line — NOT the old silent "Evaluation parse error"
        out = capsys.readouterr().out
        assert "parse-fallback after retry" in out
        assert "Evaluation parse error" not in out

    def test_fallback_decision_is_approved_not_silent(self, capsys):
        """Confirm the fallback is APPROVED-but-flagged (throughput fail-safe)."""
        cd = _make_chief_director()

        with patch.object(cd, "_call_llm", return_value="}{bad json}{"):
            result = cd.validate_shot_prompts(_minimal_shots(), _minimal_scene())

        assert result["decision"] == "APPROVED"
        # The fallback marker must be visible in output — distinguishable from
        # a genuine LLM APPROVED decision
        out = capsys.readouterr().out
        assert "parse-fallback" in out
