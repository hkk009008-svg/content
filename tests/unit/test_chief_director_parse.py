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
from identity.types import IdentityValidationResult


def _skip_result():
    """An IdentityValidationResult with overall_score=None (skipped state, Part-3 T1 schema)."""
    return IdentityValidationResult(
        passed=True,
        overall_score=None,
        character_results={},
        frames_sampled=0,
        video_duration_seconds=0.0,
        shot_type="medium",
        threshold_used=0.7,
        skipped=True,
    )


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


# ─── (d) valid-but-non-dict JSON → flagged fallback, no crash ────────────────

class TestNonDictParseDoesNotCrash:
    """Valid JSON that is NOT an object (array / bare string) must degrade to the
    flagged fallback, not crash.

    Regression for the Lane V #15 CRITICAL on 57f63d6: narrowing the except to
    json.loads alone let a valid-but-wrong-type result reach ``result.get()``,
    raising AttributeError that propagates uncaught to the cinema_pipeline.py:907
    caller and crashes the per-scene loop. The OpenAI path is protected by
    response_format=json_object; the Anthropic path (used here) is NOT, so a
    model that emits a top-level array is the live exposure. The
    ``isinstance(result, dict)`` guard degrades to the flagged fallback instead.
    """

    def test_json_array_does_not_crash_returns_fallback(self, capsys):
        cd = _make_chief_director()  # provider="anthropic" — the unguarded path
        # Valid JSON, but a list (not an object). Parse SUCCEEDS, so no retry;
        # the type guard — not the JSONDecodeError path — must catch it.
        with patch.object(cd, "_call_llm", return_value='["APPROVED", "x"]') as mock_llm:
            result = cd.validate_shot_prompts(_minimal_shots(), _minimal_scene())

        # No exception raised; contract keys intact.
        assert result["decision"] == "APPROVED"
        assert "violations" in result
        assert "shots" in result
        # Parse succeeded on attempt 0 → no retry triggered.
        assert mock_llm.call_count == 1
        out = capsys.readouterr().out
        assert "parse-fallback" in out
        assert "Evaluation parse error" not in out

    def test_json_bare_string_does_not_crash(self, capsys):
        cd = _make_chief_director()
        with patch.object(cd, "_call_llm", return_value='"just a quoted string"'):
            result = cd.validate_shot_prompts(_minimal_shots(), _minimal_scene())

        assert result["decision"] == "APPROVED"
        assert "shots" in result
        out = capsys.readouterr().out
        assert "parse-fallback" in out


# ─── (e) MODIFIED with violations but no modifications → downgrade to REJECTED ──

class TestModifiedWithoutModificationsDowngrades:
    """M-A guard: a MODIFIED verdict that flags violations but supplies an empty
    ``modifications`` list is degenerate.

    The gate-side normalizer (cinema/auto_approve.py:record_director_review_on_shots)
    auto-clears MODIFIED → gate-APPROVED on the assumption that the corrections
    flagged were applied in-place (its own comment: "the corrections ARE the
    resolution"). With empty ``modifications`` nothing was corrected, so the
    auto-clear would ship a plan the ChiefDirector flagged with open violations
    straight through the headless PLAN gate — uncorrected.

    The producer is the only layer that can see ``modifications`` is empty (its
    return dict is just {decision, violations, shots} — the normalizer never sees
    ``modifications``), so the guard lives here: downgrade to REJECTED so the gate
    fails fast (GateNotSatisfiedError headless) instead of silently approving.
    """

    def _modified_no_mods_json(self) -> str:
        return json.dumps({
            "decision": "MODIFIED",
            "violations": ["HC2: shot 0 describes blue eyes"],
            "modifications": [],
            "quality_score": 0.4,
            "reasoning": "flagged a violation but produced no corrections",
        })

    def test_modified_with_violations_no_mods_downgrades_to_rejected(self, capsys):
        cd = _make_chief_director()
        with patch.object(cd, "_call_llm", return_value=self._modified_no_mods_json()):
            result = cd.validate_shot_prompts(_minimal_shots(), _minimal_scene())

        # Downgraded so the normalizer won't auto-clear an uncorrected plan.
        assert result["decision"] == "REJECTED"
        # Violations preserved for the gate / audit trail.
        assert len(result["violations"]) == 1
        assert "shots" in result

        out = capsys.readouterr().out
        assert "downgrading to REJECTED" in out

    def test_modified_with_modifications_is_not_downgraded(self, capsys):
        """The normal MODIFIED path (corrections supplied) must be untouched:
        decision stays MODIFIED and the correction is applied in-place."""
        cd = _make_chief_director()
        modified_with_mods = json.dumps({
            "decision": "MODIFIED",
            "violations": ["HC2: shot 0 describes blue eyes"],
            "modifications": [
                {"shot_index": 0, "field": "prompt", "corrected": "[SHOT]close-up brown eyes"}
            ],
            "quality_score": 0.6,
            "reasoning": "fixed in place",
        })
        shots = _minimal_shots()
        with patch.object(cd, "_call_llm", return_value=modified_with_mods):
            result = cd.validate_shot_prompts(shots, _minimal_scene())

        assert result["decision"] == "MODIFIED"
        # Correction applied in-place — the existing MODIFIED contract is intact.
        assert shots[0]["prompt"] == "[SHOT]close-up brown eyes"
        out = capsys.readouterr().out
        assert "downgrading to REJECTED" not in out

    def test_modified_empty_violations_and_mods_is_not_downgraded(self):
        """Boundary: MODIFIED with neither violations nor modifications is NOT the
        degenerate case the guard targets — there are no open violations to ship
        uncorrected, so auto-clearing to APPROVED is harmless. Leave it unchanged."""
        cd = _make_chief_director()
        modified_empty = json.dumps({
            "decision": "MODIFIED",
            "violations": [],
            "modifications": [],
            "quality_score": 0.8,
            "reasoning": "nominal",
        })
        with patch.object(cd, "_call_llm", return_value=modified_empty):
            result = cd.validate_shot_prompts(_minimal_shots(), _minimal_scene())

        # No violations → not the uncorrected-plan risk → not downgraded.
        assert result["decision"] == "MODIFIED"


# ─── (f) evaluate_generation_quality with skipped identity result ────────────


class TestEvaluateGenerationQualitySkipGuard:
    """Regression: evaluate_generation_quality must not crash when identity_result
    has overall_score=None (skipped state).

    Before the guard (chief_director.py line ~365):
        identity_score = None  →  None >= threshold  →  TypeError crash.

    After the guard:
        identity_passed = True  (skip = non-blocking, treat as pass).
    """

    def test_skip_identity_result_does_not_raise(self):
        """evaluate_generation_quality with a skip result must not raise TypeError."""
        cd = _make_chief_director()

        # Should not raise — before the guard this throws TypeError on None >= threshold.
        result = cd.evaluate_generation_quality(
            image_path="/fake/img.jpg",
            reference_path="/fake/ref.jpg",
            identity_result=_skip_result(),
        )

        # Skip result is non-blocking: identity_passed should be True so the method
        # does not drive an identity mutation decision off a non-score.
        assert isinstance(result, dict), "result must be a dict"
        assert "decision" in result, f"result keys: {list(result.keys())}"

    def test_skip_identity_result_treated_as_non_blocking(self):
        """A skipped identity (overall_score=None) must be treated as passing:
        if coherence is also nominal the decision should be ACCEPT (not a mutation path)."""
        cd = _make_chief_director()

        result = cd.evaluate_generation_quality(
            image_path="/fake/img.jpg",
            reference_path="/fake/ref.jpg",
            identity_result=_skip_result(),
        )

        # With skip + no coherence issue, identity is non-blocking → ACCEPT.
        assert result.get("decision") == "ACCEPT", (
            f"Expected ACCEPT for skipped identity, got {result.get('decision')}"
        )

    def test_skip_identity_does_not_crash_in_llm_except_fallback(self):
        """Skip identity (overall_score=None) + incoherence + an LLM parse failure
        must not crash at the except-fallback (chief_director.py ~:510, which does
        `identity_score > 0.55`). identity_passed=True (skip) but coherent=False
        bypasses the ACCEPT short-circuit and reaches the LLM path; a garbage
        response makes parsing raise → the except fallback runs with score=None."""
        cd = _make_chief_director()

        class _FakeCoherence:
            overall_coherence_score = 0.3   # < 0.6 -> coherent=False
            color_drift = 0.1
            lighting_consistency = 0.9
            recommendations = []

        with patch.object(cd, "_call_llm", return_value="}{ not json {"):
            result = cd.evaluate_generation_quality(
                image_path="/fake/img.jpg",
                reference_path="/fake/ref.jpg",
                identity_result=_skip_result(),
                coherence_result=_FakeCoherence(),
            )

        # Before the guard: TypeError (None > 0.55). After: a valid RETRY fallback.
        assert result.get("decision") == "RETRY"
        assert result.get("mutation_level") in (1, 2, 3)
