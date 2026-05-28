"""
tests/unit/test_ensemble_judge_parse.py — TE-C-D2

Regression tests for LLMEnsemble._judge JSON-robustness (Dispatch 3, C-D2).

Covers four parse-path scenarios:
  (a) fenced valid JSON → real winner returned + [Ensemble] Judge: marker printed
  (b) garbage on attempt-1 + valid JSON on attempt-2 → retry fires (judge called
      twice) → real winner
  (c) garbage on both attempts → first-valid fallback (no crash, [LLMEnsemble]
      Judging failed path)
  (d) THE DP-01 REGRESSION GUARD: judge returns valid JSON that is the WRONG
      SHAPE (top-level array OR dict missing "scores"/"winner") → must NOT crash;
      must fall through to the first-valid fallback via the preserved broad except.

Mocking style mirrors tests/unit/test_chief_director_parse.py:
  - Instantiate LLMEnsemble, inject stub clients to bypass API key checks.
  - Patch _judge's nested _call_judge via the relevant _generate_* method.
  - capsys for log-line assertions.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from llm.ensemble import LLMEnsemble


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_ensemble() -> LLMEnsemble:
    """Build an LLMEnsemble with stub clients — no API keys needed."""
    ens = LLMEnsemble.__new__(LLMEnsemble)
    ens.anthropic_client = MagicMock()
    ens.openai_client = MagicMock()
    ens.gemini_client = None
    ens.competitive_enabled = True
    ens.judge_model_override = None
    return ens


def _valid_judge_json(winner: int = 0) -> str:
    """Return a well-formed judge JSON response."""
    return json.dumps({
        "scores": [8.5, 6.0],
        "winner": winner,
        "reasoning": "candidate 0 is better",
    })


# Two dummy candidates (models A and B).
_CANDIDATES = ["output from model A", "output from model B"]
_MODELS = ["claude-sonnet-4-20250514", "gpt-4o"]
_SYSTEM = "You are a cinema director."
_JUDGE_MODEL = "claude-sonnet-4-20250514"


def _call_judge(ens: LLMEnsemble, raw_sequence: list):
    """Drive _judge with a pre-baked sequence of raw responses.

    Patches _generate_anthropic (the path taken by the default claude judge)
    to yield successive responses from raw_sequence.  Returns the _judge
    result tuple and the mock object (for call-count assertions).
    """
    return_values = [("claude-sonnet-4-20250514", r) for r in raw_sequence]
    with patch.object(
        ens, "_generate_anthropic", side_effect=return_values
    ) as mock_gen:
        result = ens._judge(_CANDIDATES, _MODELS, _SYSTEM, judge_model=_JUDGE_MODEL)
    return result, mock_gen


# ─── (a) fenced valid JSON → real winner returned + success marker ───────────

class TestFencedJsonParsesToRealWinner:
    """LLM wraps response in ```json fences → fence-tolerant parse succeeds."""

    def test_fenced_response_returns_correct_winner(self, capsys):
        ens = _make_ensemble()
        fenced = f"```json\n{_valid_judge_json(winner=0)}\n```"

        result, mock_gen = _call_judge(ens, [fenced])

        winner_idx, full_scores, reasoning = result
        assert winner_idx == 0
        assert full_scores[0] == pytest.approx(8.5)
        assert "better" in reasoning
        assert mock_gen.call_count == 1

        out = capsys.readouterr().out
        # Success marker MUST be present.
        assert "[Ensemble] Judge:" in out
        assert "claude-sonnet-4-20250514" in out
        assert "picked candidate 0" in out
        # No failure path triggered.
        assert "[LLMEnsemble] Judging failed" not in out

    def test_fenced_response_winner_1_maps_correctly(self, capsys):
        ens = _make_ensemble()
        fenced = f"```json\n{_valid_judge_json(winner=1)}\n```"

        result, mock_gen = _call_judge(ens, [fenced])

        winner_idx, full_scores, _ = result
        assert winner_idx == 1
        assert full_scores[1] == pytest.approx(6.0)
        assert mock_gen.call_count == 1

        out = capsys.readouterr().out
        assert "[Ensemble] Judge:" in out
        assert "picked candidate 1" in out

    def test_unfenced_valid_json_also_parses(self, capsys):
        ens = _make_ensemble()
        result, mock_gen = _call_judge(ens, [_valid_judge_json(winner=0)])

        winner_idx, full_scores, _ = result
        assert winner_idx == 0
        assert mock_gen.call_count == 1

        out = capsys.readouterr().out
        assert "[Ensemble] Judge:" in out


# ─── (b) garbage attempt-1, valid JSON attempt-2 → retry fires ──────────────

class TestRetryPathFiresOnFirstParseFailure:
    """First judge call returns garbage; second returns valid JSON → retry."""

    def test_retry_fires_and_returns_real_winner(self, capsys):
        ens = _make_ensemble()

        result, mock_gen = _call_judge(
            ens,
            ["this is not json at all <<>>", _valid_judge_json(winner=0)],
        )

        # Judge called twice (original + retry-with-correction).
        assert mock_gen.call_count == 2

        # The correction string must appear in the second call's user_prompt arg.
        _model, _system, retry_user_prompt = mock_gen.call_args_list[1].args
        assert "not valid JSON" in retry_user_prompt

        winner_idx, full_scores, _ = result
        assert winner_idx == 0
        assert full_scores[0] == pytest.approx(8.5)

        out = capsys.readouterr().out
        assert "[Ensemble] Judge:" in out
        assert "[LLMEnsemble] Judging failed" not in out

    def test_fenced_garbage_attempt1_valid_attempt2(self, capsys):
        ens = _make_ensemble()

        result, mock_gen = _call_judge(
            ens,
            ["```not-json{{{", _valid_judge_json(winner=1)],
        )

        assert mock_gen.call_count == 2
        winner_idx, full_scores, _ = result
        assert winner_idx == 1

        out = capsys.readouterr().out
        assert "[Ensemble] Judge:" in out
        assert "[LLMEnsemble] Judging failed" not in out


# ─── (c) garbage on both attempts → first-valid fallback ─────────────────────

class TestFallbackAfterBothAttemptsFail:
    """Both attempts return unparseable JSON → first-valid-candidate fallback."""

    def test_fallback_fires_no_crash(self, capsys):
        ens = _make_ensemble()
        garbage = "nope, still not JSON {unterminated"

        result, mock_gen = _call_judge(ens, [garbage, garbage])

        # Both attempts made.
        assert mock_gen.call_count == 2

        winner_idx, scores, reasoning = result
        # Fallback: first valid candidate (index 0).
        assert winner_idx == 0
        assert scores[0] == pytest.approx(5.0)
        assert "Judging failed" in reasoning

        out = capsys.readouterr().out
        assert "[LLMEnsemble] Judging failed" in out
        # Success marker must NOT appear.
        assert "[Ensemble] Judge:" not in out

    def test_single_garbage_response_falls_back(self, capsys):
        """Single garbage response: retry fires, second also garbage, fallback."""
        ens = _make_ensemble()

        result, mock_gen = _call_judge(ens, ["}{bad json}{", "still bad}{"])

        assert mock_gen.call_count == 2
        winner_idx, scores, _ = result
        assert winner_idx == 0
        assert scores[0] == pytest.approx(5.0)

        out = capsys.readouterr().out
        assert "[LLMEnsemble] Judging failed" in out


# ─── (d) DP-01 REGRESSION GUARD: valid-but-wrong-shape JSON ──────────────────

class TestWrongShapeJsonDoesNotCrash:
    """Valid JSON that is NOT the expected shape must degrade to first-valid
    fallback, NOT crash.

    This is the DP-01 fold-forward: chief_director.py's Lane V CRITICAL found
    that narrowing the outer broad-except to guard only json.loads lets a
    valid-but-wrong-shape result reach downstream extraction code and raise an
    uncaught AttributeError/KeyError.  The preserved outer broad except absorbs
    these cases.
    """

    def test_json_array_does_not_crash_returns_fallback(self, capsys):
        ens = _make_ensemble()
        # Valid JSON, but a top-level list (not a dict). Parse succeeds → no
        # retry. The outer broad except must catch the subsequent KeyError/TypeError.
        result, mock_gen = _call_judge(ens, ['[1, 2, 3]'])

        assert mock_gen.call_count == 1  # no retry (parse succeeded)
        winner_idx, scores, reasoning = result
        assert winner_idx == 0
        assert scores[0] == pytest.approx(5.0)
        assert "Judging failed" in reasoning

        out = capsys.readouterr().out
        assert "[LLMEnsemble] Judging failed" in out
        assert "[Ensemble] Judge:" not in out

    def test_dict_missing_scores_key_returns_fallback(self, capsys):
        ens = _make_ensemble()
        # Valid dict, but missing "scores" key → KeyError.
        missing_scores = json.dumps({"winner": 0, "reasoning": "missing scores key"})

        result, mock_gen = _call_judge(ens, [missing_scores])

        assert mock_gen.call_count == 1
        winner_idx, scores, _ = result
        assert winner_idx == 0
        assert scores[0] == pytest.approx(5.0)

        out = capsys.readouterr().out
        assert "[LLMEnsemble] Judging failed" in out

    def test_dict_missing_winner_key_returns_fallback(self, capsys):
        ens = _make_ensemble()
        missing_winner = json.dumps({"scores": [8.0, 6.0], "reasoning": "no winner key"})

        result, mock_gen = _call_judge(ens, [missing_winner])

        assert mock_gen.call_count == 1
        winner_idx, scores, _ = result
        assert winner_idx == 0
        assert scores[0] == pytest.approx(5.0)

        out = capsys.readouterr().out
        assert "[LLMEnsemble] Judging failed" in out

    def test_json_bare_string_does_not_crash(self, capsys):
        ens = _make_ensemble()
        result, mock_gen = _call_judge(ens, ['"just a quoted string"'])

        assert mock_gen.call_count == 1
        winner_idx, scores, _ = result
        assert winner_idx == 0
        assert scores[0] == pytest.approx(5.0)

        out = capsys.readouterr().out
        assert "[LLMEnsemble] Judging failed" in out
