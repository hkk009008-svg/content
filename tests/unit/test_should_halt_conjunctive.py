"""TDD tests for T4: conjunctive identity-floor halt mode.

should_halt() gains a halt_rule param:
  - 'conjunctive': QUALITY halt requires composite >= threshold AND arc >= threshold.
  - 'composite_only' (default): QUALITY halt requires composite >= threshold only
    (existing behavior preserved).
  - 'budget_only': deferred — falls back to composite_only behavior (not a new
    never-halt policy; just deferred per user decision).

Budget halt (n >= halt_max_n) is UNCHANGED for ALL modes.

quality_max.generate_ai_broll_max must extract halt_rule from params and pass
it to should_halt.
"""
from __future__ import annotations

import pytest

from face_validator_gate import CandidateScore, HaltDecision, should_halt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score(composite: float, arc: float = 0.5) -> CandidateScore:
    return CandidateScore(
        image_path="/fake/img.jpg",
        seed=0,
        arc_score=arc,
        composite=composite,
        has_arc=True,
    )


def _n_scores(n: int, composite: float = 0.95, arc: float = 0.90) -> list:
    return [_score(composite, arc) for _ in range(n)]


# Common thresholds used across tests
COMP_T = 0.92
ARC_T = 0.85
MIN_N = 4
MAX_N = 8


# ---------------------------------------------------------------------------
# 1. Conjunctive mode — both composite AND arc required to halt
# ---------------------------------------------------------------------------

class TestConjunctiveMode:
    def test_high_composite_low_arc_does_not_halt(self):
        """conjunctive: composite passes but arc below threshold → no halt."""
        scores = _n_scores(MIN_N, composite=0.95, arc=0.70)  # arc < 0.85
        decision = should_halt(
            scores,
            halt_threshold_composite=COMP_T,
            halt_threshold_arc=ARC_T,
            halt_min_n=MIN_N,
            halt_max_n=MAX_N,
            halt_rule="conjunctive",
        )
        assert decision.halt is False

    def test_high_composite_high_arc_halts(self):
        """conjunctive: composite >= threshold AND arc >= threshold → halt."""
        scores = _n_scores(MIN_N, composite=0.95, arc=0.90)  # both pass
        decision = should_halt(
            scores,
            halt_threshold_composite=COMP_T,
            halt_threshold_arc=ARC_T,
            halt_min_n=MIN_N,
            halt_max_n=MAX_N,
            halt_rule="conjunctive",
        )
        assert decision.halt is True

    def test_low_composite_high_arc_does_not_halt(self):
        """conjunctive: arc passes but composite below threshold → no halt."""
        scores = _n_scores(MIN_N, composite=0.80, arc=0.95)  # composite < 0.92
        decision = should_halt(
            scores,
            halt_threshold_composite=COMP_T,
            halt_threshold_arc=ARC_T,
            halt_min_n=MIN_N,
            halt_max_n=MAX_N,
            halt_rule="conjunctive",
        )
        assert decision.halt is False

    def test_both_at_exact_threshold_halts(self):
        """conjunctive: both exactly at threshold → halt (boundary inclusive)."""
        scores = _n_scores(MIN_N, composite=COMP_T, arc=ARC_T)
        decision = should_halt(
            scores,
            halt_threshold_composite=COMP_T,
            halt_threshold_arc=ARC_T,
            halt_min_n=MIN_N,
            halt_max_n=MAX_N,
            halt_rule="conjunctive",
        )
        assert decision.halt is True

    def test_reason_mentions_conjunctive(self):
        """conjunctive: halt reason string references the active mode."""
        scores = _n_scores(MIN_N, composite=0.95, arc=0.90)
        decision = should_halt(
            scores,
            halt_threshold_composite=COMP_T,
            halt_threshold_arc=ARC_T,
            halt_min_n=MIN_N,
            halt_max_n=MAX_N,
            halt_rule="conjunctive",
        )
        assert "conjunctive" in decision.reason

    def test_reason_mentions_conjunctive_on_no_halt(self):
        """conjunctive no-halt reason also mentions the active mode."""
        scores = _n_scores(MIN_N, composite=0.95, arc=0.70)  # arc fails
        decision = should_halt(
            scores,
            halt_threshold_composite=COMP_T,
            halt_threshold_arc=ARC_T,
            halt_min_n=MIN_N,
            halt_max_n=MAX_N,
            halt_rule="conjunctive",
        )
        assert "conjunctive" in decision.reason

    def test_below_min_n_no_halt_regardless(self):
        """conjunctive: below halt_min_n → no halt even with excellent scores."""
        scores = _n_scores(MIN_N - 1, composite=0.99, arc=0.99)
        decision = should_halt(
            scores,
            halt_threshold_composite=COMP_T,
            halt_threshold_arc=ARC_T,
            halt_min_n=MIN_N,
            halt_max_n=MAX_N,
            halt_rule="conjunctive",
        )
        assert decision.halt is False


# ---------------------------------------------------------------------------
# 2. composite_only mode — arc NOT enforced (existing behavior preserved)
# ---------------------------------------------------------------------------

class TestCompositeOnlyMode:
    def test_high_composite_low_arc_still_halts(self):
        """composite_only: high composite + LOW arc → halt (arc is informational)."""
        scores = _n_scores(MIN_N, composite=0.95, arc=0.60)  # arc well below 0.85
        decision = should_halt(
            scores,
            halt_threshold_composite=COMP_T,
            halt_threshold_arc=ARC_T,
            halt_min_n=MIN_N,
            halt_max_n=MAX_N,
            halt_rule="composite_only",
        )
        assert decision.halt is True

    def test_default_halt_rule_is_composite_only(self):
        """Omitting halt_rule → same as 'composite_only' (default param)."""
        scores = _n_scores(MIN_N, composite=0.95, arc=0.60)
        decision_explicit = should_halt(
            scores,
            halt_threshold_composite=COMP_T,
            halt_threshold_arc=ARC_T,
            halt_min_n=MIN_N,
            halt_max_n=MAX_N,
            halt_rule="composite_only",
        )
        decision_default = should_halt(
            scores,
            halt_threshold_composite=COMP_T,
            halt_threshold_arc=ARC_T,
            halt_min_n=MIN_N,
            halt_max_n=MAX_N,
            # halt_rule not passed
        )
        assert decision_explicit.halt == decision_default.halt

    def test_unknown_rule_falls_back_to_composite_only(self):
        """Unknown halt_rule string falls back to composite_only behavior."""
        scores = _n_scores(MIN_N, composite=0.95, arc=0.60)
        decision = should_halt(
            scores,
            halt_threshold_composite=COMP_T,
            halt_threshold_arc=ARC_T,
            halt_min_n=MIN_N,
            halt_max_n=MAX_N,
            halt_rule="totally_unknown_rule",
        )
        assert decision.halt is True  # composite passes; arc not enforced


# ---------------------------------------------------------------------------
# 3. budget_only mode — deferred; falls back to composite_only behavior
# ---------------------------------------------------------------------------

class TestBudgetOnlyModeDeferred:
    def test_high_composite_low_arc_halts_same_as_composite_only(self):
        """budget_only is DEFERRED — high composite + low arc halts (like composite_only).

        budget_only does NOT implement a 'never-halt-early' policy.
        It is explicitly left as composite_only fallback per user decision.
        """
        scores = _n_scores(MIN_N, composite=0.95, arc=0.60)
        decision = should_halt(
            scores,
            halt_threshold_composite=COMP_T,
            halt_threshold_arc=ARC_T,
            halt_min_n=MIN_N,
            halt_max_n=MAX_N,
            halt_rule="budget_only",
        )
        assert decision.halt is True  # same as composite_only

    def test_budget_only_below_n_max_can_still_halt_early(self):
        """budget_only: early halt IS possible (falls back to composite_only)."""
        scores = _n_scores(MIN_N, composite=0.95, arc=0.50)
        decision = should_halt(
            scores,
            halt_threshold_composite=COMP_T,
            halt_threshold_arc=ARC_T,
            halt_min_n=MIN_N,
            halt_max_n=MAX_N,
            halt_rule="budget_only",
        )
        # Falls back to composite_only → halts on composite alone
        assert decision.halt is True


# ---------------------------------------------------------------------------
# 4. Budget exhaustion (n >= halt_max_n) — ALL modes always halt
# ---------------------------------------------------------------------------

class TestBudgetExhaustedAllModes:
    @pytest.mark.parametrize("halt_rule", ["composite_only", "conjunctive", "budget_only"])
    def test_budget_exhausted_always_halts(self, halt_rule):
        """n >= halt_max_n → halt=True for every mode, regardless of scores."""
        scores = _n_scores(MAX_N, composite=0.10, arc=0.10)  # terrible scores
        decision = should_halt(
            scores,
            halt_threshold_composite=COMP_T,
            halt_threshold_arc=ARC_T,
            halt_min_n=MIN_N,
            halt_max_n=MAX_N,
            halt_rule=halt_rule,
        )
        assert decision.halt is True
        assert "budget" in decision.reason or "n=" in decision.reason

    @pytest.mark.parametrize("halt_rule", ["composite_only", "conjunctive", "budget_only"])
    def test_budget_exhausted_returns_best(self, halt_rule):
        """Budget halt returns decision.best."""
        scores = _n_scores(MAX_N, composite=0.10, arc=0.10)
        decision = should_halt(
            scores,
            halt_max_n=MAX_N,
            halt_rule=halt_rule,
        )
        assert decision.best is not None


# ---------------------------------------------------------------------------
# 5. quality_max extracts halt_rule from params and passes it to should_halt
# ---------------------------------------------------------------------------

class TestQualityMaxExtractsHaltRule:
    def test_halt_rule_extracted_from_params(self):
        """quality_max.generate_ai_broll_max passes halt_rule from params to should_halt.

        We verify this by inspecting the source of the function — it must
        contain:
          - extraction of halt_rule from params (params.get("halt_rule", ...))
          - passing halt_rule= to should_halt(...)
        This is a structural test that catches the 'written-never-read' dead
        code path without requiring a full GPU pipeline run.
        """
        import inspect
        import quality_max

        src = inspect.getsource(quality_max.generate_ai_broll_max)
        assert 'params.get("halt_rule"' in src, (
            "generate_ai_broll_max must extract halt_rule from params via params.get()"
        )
        assert "halt_rule=halt_rule" in src, (
            "generate_ai_broll_max must pass halt_rule=halt_rule to should_halt()"
        )
