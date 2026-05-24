"""Tests for cinema/auto_approve.py — P4-3 auto-approve veto rules.

Coverage:
  - TestVetoRules     : per-rule positive (fires) + negative (passes) cases
  - TestCheckGatePerGate : happy-path check_gate for each of the 4 gates
  - TestConfigFromProject: defaults + custom overrides
  - TestDisabledShortCircuit: config.enabled=False
  - TestAuditAppend   : audit entry shape + accumulation; integration with
                        ReviewController's _run_auto_approve_pass (mocked host)
"""
from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock

import pytest

from cinema.auto_approve import (
    AutoApproveConfig,
    AutoApproveDecision,
    VetoRule,
    check_gate,
    pick_best_take_by_composite,
    pick_best_take_for_final,
    summarize_audit,
    _rules_for_plan,
    _rules_for_image,
    _rules_for_motion,
    _rules_for_final,
    _best_take_lipsync,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_shot(
    *,
    plan_status: str = "approved",
    director_review: Optional[dict] = None,
    keyframe_takes: Optional[list] = None,
    motion_takes: Optional[list] = None,
    postprocess_variants: Optional[list] = None,
    spent_usd: float = 0.0,
    auto_approve_audit: Optional[list] = None,
    **extra,
) -> dict:
    shot = {
        "id": "shot_test_001",
        "prompt": "A test shot",
        "plan_status": plan_status,
        "director_review": director_review or {"decision": "APPROVED", "violations": []},
        "keyframe_takes": keyframe_takes if keyframe_takes is not None else [],
        "motion_takes": motion_takes if motion_takes is not None else [],
        "postprocess_variants": postprocess_variants if postprocess_variants is not None else [],
        "spent_usd": spent_usd,
        "auto_approve_audit": auto_approve_audit if auto_approve_audit is not None else [],
    }
    shot.update(extra)
    return shot


def _make_keyframe_take(composite: float = 0.98, fallback: bool = False) -> dict:
    return {
        "id": "take_kf_001",
        "kind": "keyframe",
        "path": "/tmp/kf.jpg",
        "metadata": {"composite": composite},
        "cascade_metadata": {"fallback": fallback, "engine": "runpod"},
    }


def _make_motion_take(
    identity_score: float = 0.90,
    motion_score: float = 0.80,
    fallback: bool = False,
) -> dict:
    return {
        "id": "take_mt_001",
        "kind": "motion",
        "path": "/tmp/mt.mp4",
        "metadata": {
            "identity_score": identity_score,
            "motion_fidelity": motion_score,
        },
        "cascade_metadata": {"fallback": fallback},
    }


def _make_final_take(lipsync_score: Optional[float] = None) -> dict:
    metadata: dict = {}
    if lipsync_score is not None:
        metadata["lipsync_score"] = lipsync_score
    return {
        "id": "take_final_001",
        "kind": "postprocess",
        "path": "/tmp/final.mp4",
        "metadata": metadata,
        "cascade_metadata": None,
    }


def _make_project(budget_limit_usd: float = 0.0, auto_approve_cfg: Optional[dict] = None) -> dict:
    return {
        "id": "proj_test_001",
        "name": "Test Project",
        "scenes": [{"shots": []}],
        "global_settings": {
            "budget_limit_usd": budget_limit_usd,
            "auto_approve": auto_approve_cfg or AutoApproveConfig().to_dict(),
        },
    }


# ---------------------------------------------------------------------------
# 1. TestVetoRules — one per major rule, positive + negative
# ---------------------------------------------------------------------------


class TestVetoRules:
    """Tests for individual VetoRule predicates via _rules_for_* builders."""

    # ---- Plan rules ----

    def test_plan_decision_not_approved_fires_on_modified(self):
        config = AutoApproveConfig()
        rules = _rules_for_plan(config)
        assert rules, "expected at least one plan rule"
        # Find the decision rule
        decision_rule = next(r for r in rules if r.name == "plan_decision_not_approved")
        shot = _make_shot(director_review={"decision": "MODIFIED", "violations": []})
        ctx = {"shot_state": shot, "project": _make_project(), "takes": []}
        assert decision_rule.predicate(ctx) is True, "MODIFIED decision should fire"

    def test_plan_decision_not_approved_passes_on_approved(self):
        config = AutoApproveConfig()
        rules = _rules_for_plan(config)
        decision_rule = next(r for r in rules if r.name == "plan_decision_not_approved")
        shot = _make_shot(director_review={"decision": "APPROVED", "violations": []})
        ctx = {"shot_state": shot, "project": _make_project(), "takes": []}
        assert decision_rule.predicate(ctx) is False, "APPROVED decision should not fire"

    def test_plan_violations_fires_when_violations_present(self):
        config = AutoApproveConfig()
        rules = _rules_for_plan(config)
        violations_rule = next(r for r in rules if r.name == "plan_has_violations")
        shot = _make_shot(
            director_review={"decision": "APPROVED", "violations": ["too bright"]}
        )
        ctx = {"shot_state": shot, "project": _make_project(), "takes": []}
        assert violations_rule.predicate(ctx) is True

    def test_plan_violations_passes_on_empty_violations(self):
        config = AutoApproveConfig()
        rules = _rules_for_plan(config)
        violations_rule = next(r for r in rules if r.name == "plan_has_violations")
        shot = _make_shot(director_review={"decision": "APPROVED", "violations": []})
        ctx = {"shot_state": shot, "project": _make_project(), "takes": []}
        assert violations_rule.predicate(ctx) is False

    # ---- Image rules ----

    def test_image_composite_fires_below_threshold(self):
        config = AutoApproveConfig(image_min_composite=0.97)
        rules = _rules_for_image(config)
        composite_rule = next(r for r in rules if r.name == "image_composite_below_threshold")
        low_take = _make_keyframe_take(composite=0.90)
        ctx = {"shot_state": _make_shot(), "project": _make_project(), "takes": [low_take]}
        assert composite_rule.predicate(ctx) is True

    def test_image_composite_passes_above_threshold(self):
        config = AutoApproveConfig(image_min_composite=0.97)
        rules = _rules_for_image(config)
        composite_rule = next(r for r in rules if r.name == "image_composite_below_threshold")
        good_take = _make_keyframe_take(composite=0.98)
        ctx = {"shot_state": _make_shot(), "project": _make_project(), "takes": [good_take]}
        assert composite_rule.predicate(ctx) is False

    def test_image_fallback_fires_when_cascade_fallback_true(self):
        config = AutoApproveConfig(image_veto_on_fallback=True)
        rules = _rules_for_image(config)
        fallback_rule = next(r for r in rules if r.name == "image_cascade_fallback")
        fallback_take = _make_keyframe_take(fallback=True)
        ctx = {
            "shot_state": _make_shot(),
            "project": _make_project(),
            "takes": [fallback_take],
        }
        assert fallback_rule.predicate(ctx) is True

    # ---- Motion rules ----

    def test_motion_identity_fires_below_threshold(self):
        config = AutoApproveConfig(motion_min_identity=0.85)
        rules = _rules_for_motion(config)
        id_rule = next(r for r in rules if r.name == "motion_identity_below_threshold")
        low_take = _make_motion_take(identity_score=0.70)
        ctx = {"shot_state": _make_shot(), "project": _make_project(), "takes": [low_take]}
        assert id_rule.predicate(ctx) is True

    def test_motion_identity_passes_at_threshold(self):
        config = AutoApproveConfig(motion_min_identity=0.85)
        rules = _rules_for_motion(config)
        id_rule = next(r for r in rules if r.name == "motion_identity_below_threshold")
        good_take = _make_motion_take(identity_score=0.90)
        ctx = {"shot_state": _make_shot(), "project": _make_project(), "takes": [good_take]}
        assert id_rule.predicate(ctx) is False


# ---------------------------------------------------------------------------
# 2. TestCheckGatePerGate — happy path for each gate
# ---------------------------------------------------------------------------


class TestCheckGatePerGate:
    """Full check_gate call for each gate; asserts auto_approved=True on ideal input."""

    def _default_config(self) -> AutoApproveConfig:
        return AutoApproveConfig()

    def test_plan_gate_approves_clean_shot(self):
        shot = _make_shot(
            director_review={"decision": "APPROVED", "violations": []}
        )
        project = _make_project()
        decision = check_gate(
            "plan",
            shot_state=shot,
            project=project,
            takes=[],
            config=self._default_config(),
        )
        assert decision.auto_approved is True
        assert decision.vetoes == []

    def test_image_gate_approves_high_composite_take(self):
        take = _make_keyframe_take(composite=0.99, fallback=False)
        shot = _make_shot(keyframe_takes=[take])
        project = _make_project()
        decision = check_gate(
            "image",
            shot_state=shot,
            project=project,
            takes=[take],
            config=self._default_config(),
        )
        assert decision.auto_approved is True
        assert decision.vetoes == []

    def test_motion_gate_approves_high_scores(self):
        take = _make_motion_take(identity_score=0.92, motion_score=0.88, fallback=False)
        shot = _make_shot(motion_takes=[take])
        project = _make_project()
        decision = check_gate(
            "motion",
            shot_state=shot,
            project=project,
            takes=[take],
            config=self._default_config(),
        )
        assert decision.auto_approved is True
        assert decision.vetoes == []

    def test_final_gate_approves_when_no_upstream_auto_and_good_lipsync(self):
        # No upstream gate was auto-approved → final_require_human_if_upstream_auto
        # doesn't fire. No lipsync_score set → lipsync rule doesn't fire.
        take = _make_final_take(lipsync_score=None)  # no lipsync → treated as N/A
        shot = _make_shot(postprocess_variants=[take])
        # Ensure NO upstream auto-approved flags
        assert "plan_auto_approved" not in shot
        assert "image_auto_approved" not in shot
        project = _make_project()
        decision = check_gate(
            "final",
            shot_state=shot,
            project=project,
            takes=[take],
            config=self._default_config(),
        )
        assert decision.auto_approved is True
        assert decision.vetoes == []


# ---------------------------------------------------------------------------
# 3. TestConfigFromProject — reading config from project dict
# ---------------------------------------------------------------------------


class TestConfigFromProject:
    def test_empty_project_returns_defaults(self):
        project: dict = {"id": "proj_empty", "global_settings": {}}
        config = AutoApproveConfig.from_project(project)
        defaults = AutoApproveConfig()
        assert config.enabled == defaults.enabled
        assert config.image_min_composite == defaults.image_min_composite
        assert config.motion_min_identity == defaults.motion_min_identity
        assert config.final_min_lipsync == defaults.final_min_lipsync

    def test_partial_override_merges_with_defaults(self):
        project: dict = {
            "id": "proj_override",
            "global_settings": {
                "auto_approve": {
                    "image_min_composite": 0.95,
                    "motion_min_identity": 0.80,
                }
            },
        }
        config = AutoApproveConfig.from_project(project)
        assert config.image_min_composite == pytest.approx(0.95)
        assert config.motion_min_identity == pytest.approx(0.80)
        # Other fields stay at defaults
        defaults = AutoApproveConfig()
        assert config.final_min_lipsync == defaults.final_min_lipsync
        assert config.enabled == defaults.enabled

    def test_to_dict_round_trips_through_from_project(self):
        original = AutoApproveConfig(image_min_composite=0.95, enabled=False)
        project = {
            "id": "proj_rt",
            "global_settings": {"auto_approve": original.to_dict()},
        }
        recovered = AutoApproveConfig.from_project(project)
        assert recovered.image_min_composite == pytest.approx(0.95)
        assert recovered.enabled is False


# ---------------------------------------------------------------------------
# 4. TestDisabledShortCircuit
# ---------------------------------------------------------------------------


class TestDisabledShortCircuit:
    def test_disabled_config_returns_false_with_disabled_veto(self):
        config = AutoApproveConfig(enabled=False)
        shot = _make_shot(
            director_review={"decision": "APPROVED", "violations": []}
        )
        project = _make_project()
        decision = check_gate(
            "plan",
            shot_state=shot,
            project=project,
            takes=[],
            config=config,
        )
        assert decision.auto_approved is False
        assert "disabled" in decision.vetoes
        assert "disabled" in decision.rule_names

    def test_disabled_via_project_setting(self):
        project = _make_project(auto_approve_cfg={"enabled": False})
        shot = _make_shot()
        decision = check_gate(
            "plan",
            shot_state=shot,
            project=project,
            takes=[],
            # config=None → reads from project
        )
        assert decision.auto_approved is False
        assert "disabled" in decision.vetoes


# ---------------------------------------------------------------------------
# 5. TestAuditAppend — audit log shape + accumulation
# ---------------------------------------------------------------------------


class TestAuditAppend:
    def test_audit_entry_shape_on_veto(self):
        """A vetoed gate call produces a correctly-shaped audit entry when the
        caller appends it (as ReviewController._run_auto_approve_pass does).
        This test simulates that append directly."""
        config = AutoApproveConfig(plan_require_approved=True)
        shot = _make_shot(
            director_review={"decision": "MODIFIED", "violations": []}
        )
        project = _make_project()
        decision = check_gate(
            "plan",
            shot_state=shot,
            project=project,
            takes=[],
            config=config,
        )
        assert decision.auto_approved is False
        assert len(decision.vetoes) > 0

        from datetime import datetime, timezone

        entry = {
            "gate": "plan",
            "auto_approved": decision.auto_approved,
            "vetoes": decision.vetoes,
            "rule_names": decision.rule_names,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        shot["auto_approve_audit"].append(entry)

        assert len(shot["auto_approve_audit"]) == 1
        e = shot["auto_approve_audit"][0]
        assert e["gate"] == "plan"
        assert e["auto_approved"] is False
        assert isinstance(e["vetoes"], list) and len(e["vetoes"]) > 0
        assert isinstance(e["rule_names"], list)
        assert "T" in e["timestamp"]  # ISO-8601 timestamp

    def test_audit_entries_accumulate_across_gates(self):
        """Successive check_gate calls on different gates accumulate in the
        audit list (mirrors _run_auto_approve_pass behaviour)."""
        from datetime import datetime, timezone

        shot = _make_shot()
        project = _make_project()

        for gate, takes in [
            ("plan", []),
            ("image", [_make_keyframe_take(composite=0.99)]),
        ]:
            decision = check_gate(
                gate,  # type: ignore[arg-type]
                shot_state=shot,
                project=project,
                takes=takes,
            )
            shot.setdefault("auto_approve_audit", []).append(
                {
                    "gate": gate,
                    "auto_approved": decision.auto_approved,
                    "vetoes": decision.vetoes,
                    "rule_names": decision.rule_names,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

        assert len(shot["auto_approve_audit"]) == 2
        gates_seen = {e["gate"] for e in shot["auto_approve_audit"]}
        assert "plan" in gates_seen
        assert "image" in gates_seen

    def test_summarize_audit_counts_correctly(self):
        """summarize_audit correctly aggregates approved vs vetoed gates."""
        shot = _make_shot()
        shot["auto_approve_audit"] = [
            {
                "gate": "plan",
                "auto_approved": True,
                "vetoes": [],
                "rule_names": [],
                "timestamp": "2026-05-24T00:00:00+00:00",
            },
            {
                "gate": "image",
                "auto_approved": False,
                "vetoes": ["composite below threshold"],
                "rule_names": ["image_composite_below_threshold"],
                "timestamp": "2026-05-24T00:01:00+00:00",
            },
        ]
        summary = summarize_audit(shot)
        assert summary["auto_approved_gates"] == ["plan"]
        assert summary["vetoed_gates"] == ["image"]
        assert summary["total_vetoes"] == 1
        assert summary["per_rule_fire_counts"]["image_composite_below_threshold"] == 1

    def test_review_controller_run_auto_approve_pass_plan_gate(self):
        """Integration: _run_auto_approve_pass with PLAN_REVIEW pre-approves a
        shot that passes all plan veto rules.  Uses a stub ReviewControllerHost
        and a NullLifecycle."""
        from cinema.review.controller import ReviewController
        from cinema.lifecycle import NullLifecycle
        from cinema.runstate import RunState

        # Build a minimal project with one scene containing one shot.
        shot = _make_shot(
            plan_status="",  # not yet approved
            director_review={"decision": "APPROVED", "violations": []},
        )
        project = _make_project()
        project["scenes"] = [{"id": "scene_001", "shots": [shot]}]

        # Track mutations.
        mutations: list[dict] = []

        class StubHost:
            def _refresh_project_snapshot(self, timeout=10):
                return project

            def _find_take(self, s, take_id):
                for coll in ("keyframe_takes", "motion_takes", "postprocess_variants"):
                    for t in (s.get(coll) or []):
                        if t.get("id") == take_id:
                            return coll, t
                return None, None

            def _mutate_shot(self, shot_id, mutator, timeout=10):
                for scene in project.get("scenes", []):
                    for s in scene.get("shots", []):
                        if s.get("id") == shot_id:
                            result = mutator(scene, s)
                            mutations.append({"shot_id": shot_id, "result": result})
                            return result.value if result else None
                return None

            def resume(self):
                pass

        core = MagicMock()
        core.project = project
        lifecycle = NullLifecycle()
        runstate = RunState()
        host = StubHost()

        ctrl = ReviewController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
        ctrl._run_auto_approve_pass("PLAN_REVIEW")

        # After the pass, the shot should be plan-approved.
        updated_shot = project["scenes"][0]["shots"][0]
        assert updated_shot.get("plan_status") == "approved", (
            "plan_status should be 'approved' after auto-approve pass"
        )
        assert updated_shot.get("plan_auto_approved") is True
        assert len(updated_shot.get("auto_approve_audit", [])) == 1
        audit = updated_shot["auto_approve_audit"][0]
        assert audit["gate"] == "plan"
        assert audit["auto_approved"] is True


# ---------------------------------------------------------------------------
# TestV11Fixes — regression tests for Session 11 code-review findings.
#
# Three bugs fixed in the v1.1 chore commit:
#   1. _best_take_lipsync returned FIRST take's score instead of MAX.
#   2. Controller picked keyframe_takes[-1] for the image gate, ignoring the
#      veto rule's "best = max(composite)" semantics — could approve a worse
#      take than the rule evaluated.
#   3. Controller picked final_candidates[-1] for the final gate, ignoring
#      fallback status — could approve a fallback take when non-fallback
#      options existed.
# ---------------------------------------------------------------------------


class TestV11Fixes:
    """Regression tests for Session 11 review's "best-take semantics" fixes."""

    def test_best_take_lipsync_returns_max_not_first(self):
        """Bug: returned FIRST take's score; expected MAX across takes."""
        takes = [
            {"id": "t1", "metadata": {"lipsync_score": 0.7}},
            {"id": "t2", "metadata": {"lipsync_score": 0.95}},
        ]
        # Old (buggy) behavior: returned 0.7 (first take). With threshold 0.8
        # the rule would VETO despite t2 being well above threshold.
        # Fixed behavior: returns 0.95 (max), rule PASSES.
        assert _best_take_lipsync(takes) == pytest.approx(0.95)

    def test_best_take_lipsync_no_score_defaults_to_one(self):
        """N/A behavior preserved: shots with no dialogue (no lipsync score) → 1.0."""
        takes = [
            {"id": "t1", "metadata": {}},
            {"id": "t2", "metadata": {"other_score": 0.5}},  # unrelated metric
        ]
        assert _best_take_lipsync(takes) == pytest.approx(1.0)

    def test_pick_best_take_by_composite_picks_highest_score(self):
        """Image gate: helper should pick the take with max composite, not last."""
        takes = [
            {"id": "t_low", "metadata": {"composite": 0.85}},
            {"id": "t_high", "metadata": {"composite": 0.99}},
            {"id": "t_mid", "metadata": {"composite": 0.92}},  # last by position
        ]
        # Old (buggy) controller: keyframe_takes[-1] → t_mid (0.92).
        # Fixed helper: t_high (0.99).
        best = pick_best_take_by_composite(takes)
        assert best is not None
        assert best["id"] == "t_high"

    def test_pick_best_take_by_composite_falls_back_to_last_when_no_score(self):
        """When no take carries a composite metric, return the most recent."""
        takes = [
            {"id": "t1", "metadata": {}},
            {"id": "t2", "metadata": {}},
        ]
        best = pick_best_take_by_composite(takes)
        assert best is not None
        assert best["id"] == "t2"  # fallback to last
        assert pick_best_take_by_composite([]) is None

    def test_pick_best_take_for_final_prefers_non_fallback(self):
        """Final gate: non-fallback takes preferred over fallback even if
        fallback has higher composite — the audit log should say "approved
        without fallback" when possible."""
        candidates = [
            {"id": "fallback_hi", "metadata": {"composite": 0.95},
             "cascade_metadata": {"fallback": True}},
            {"id": "primary_lo", "metadata": {"composite": 0.88},
             "cascade_metadata": {"fallback": False}},
        ]
        best = pick_best_take_for_final(candidates)
        assert best is not None
        assert best["id"] == "primary_lo", (
            "non-fallback take must win even with lower composite"
        )

    def test_pick_best_take_for_final_all_fallback_picks_best_anyway(self):
        """When ALL candidates are fallback, return the best by composite
        (graceful degradation; the upstream non-fallback veto would have
        prevented this gate from auto-approving in the first place)."""
        candidates = [
            {"id": "fb_lo", "metadata": {"composite": 0.82},
             "cascade_metadata": {"fallback": True}},
            {"id": "fb_hi", "metadata": {"composite": 0.91},
             "cascade_metadata": {"fallback": True}},
        ]
        best = pick_best_take_for_final(candidates)
        assert best is not None
        assert best["id"] == "fb_hi"


# ---------------------------------------------------------------------------
# TestMotionGateFlag — unit tests for the is_motion_gate_enabled() helper.
# ---------------------------------------------------------------------------


class TestMotionGateFlag:
    """Tests for cinema.auto_approve.is_motion_gate_enabled()."""

    def test_is_motion_gate_enabled_default_off(self, monkeypatch):
        """No env var set → helper returns False (v1 default preserved)."""
        from cinema.auto_approve import is_motion_gate_enabled

        monkeypatch.delenv("CINEMA_AUTO_APPROVE_MOTION", raising=False)
        assert is_motion_gate_enabled() is False

    @pytest.mark.parametrize(
        "value",
        ["1", "true", "TRUE", "True", "yes", "YES", "Yes", "  1  "],
    )
    def test_is_motion_gate_enabled_truthy_values(self, monkeypatch, value):
        """All documented truthy forms (case-insensitive, whitespace-tolerant)
        must return True — closes the case-sensitivity papercut S10's code
        reviewer flagged on CINEMA_STRICT_SCHEMA."""
        from cinema.auto_approve import is_motion_gate_enabled

        monkeypatch.setenv("CINEMA_AUTO_APPROVE_MOTION", value)
        assert is_motion_gate_enabled() is True, (
            f"expected True for env value {value!r}"
        )

    @pytest.mark.parametrize(
        "value",
        ["", "0", "false", "False", "no", "NO", "random", "off"],
    )
    def test_is_motion_gate_enabled_falsy_values(self, monkeypatch, value):
        """Non-truthy env values (including empty string) → False."""
        from cinema.auto_approve import is_motion_gate_enabled

        monkeypatch.setenv("CINEMA_AUTO_APPROVE_MOTION", value)
        assert is_motion_gate_enabled() is False, (
            f"expected False for env value {value!r}"
        )


# ---------------------------------------------------------------------------
# TestMotionGateIntegration — controller integration tests.
#
# Each test follows the StubHost pattern from
# test_review_controller_run_auto_approve_pass_plan_gate (line 469):
#   build project → instantiate controller → call _run_auto_approve_pass
#   with monkeypatched env → assert mutations.
# ---------------------------------------------------------------------------


class TestMotionGateIntegration:
    """Integration tests for motion gate wiring through ReviewController."""

    def _make_ctrl_and_project(self, motion_takes=None, extra_shot_fields=None):
        """Shared helper: returns (ctrl, project, mutations_list) ready to call
        _run_auto_approve_pass("PERFORMANCE_REVIEW") on."""
        from cinema.review.controller import ReviewController
        from cinema.lifecycle import NullLifecycle
        from cinema.runstate import RunState

        shot = _make_shot(
            motion_takes=motion_takes if motion_takes is not None else [],
            **(extra_shot_fields or {}),
        )
        project = _make_project()
        project["scenes"] = [{"id": "scene_001", "shots": [shot]}]

        mutations: list[dict] = []

        class StubHost:
            def _refresh_project_snapshot(self, timeout=10):
                return project

            def _find_take(self, s, take_id):
                for coll in ("keyframe_takes", "motion_takes", "postprocess_variants"):
                    for t in (s.get(coll) or []):
                        if t.get("id") == take_id:
                            return coll, t
                return None, None

            def _mutate_shot(self, shot_id, mutator, timeout=10):
                for scene in project.get("scenes", []):
                    for s in scene.get("shots", []):
                        if s.get("id") == shot_id:
                            result = mutator(scene, s)
                            mutations.append({"shot_id": shot_id, "result": result})
                            return result.value if result else None
                return None

            def resume(self):
                pass

        core = MagicMock()
        core.project = project
        lifecycle = NullLifecycle()
        runstate = RunState()
        host = StubHost()
        ctrl = ReviewController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
        return ctrl, project, mutations

    def test_motion_gate_off_by_default_skips_performance_review(self, monkeypatch):
        """With flag unset, PERFORMANCE_REVIEW → early return; no mutation, no audit."""
        monkeypatch.delenv("CINEMA_AUTO_APPROVE_MOTION", raising=False)

        take = _make_motion_take(identity_score=0.95, motion_score=0.90)
        ctrl, project, mutations = self._make_ctrl_and_project(motion_takes=[take])

        ctrl._run_auto_approve_pass("PERFORMANCE_REVIEW")

        shot = project["scenes"][0]["shots"][0]
        assert shot.get("approved_motion_take_id") is None, (
            "flag off: approved_motion_take_id must not be set"
        )
        assert shot.get("motion_auto_approved") is None, (
            "flag off: motion_auto_approved must not be set"
        )
        assert shot.get("auto_approve_audit", []) == [], (
            "flag off: no audit entry expected"
        )
        assert mutations == [], "flag off: no mutations expected"

    def test_motion_gate_on_approves_high_scoring_take(self, monkeypatch):
        """With flag set + high-scoring take → approved_motion_take_id set,
        motion_auto_approved=True, audit entry appended."""
        monkeypatch.setenv("CINEMA_AUTO_APPROVE_MOTION", "1")

        # identity=0.95 > 0.85 threshold, motion_fidelity=0.85 > 0.7 threshold,
        # fallback=False → all 3 veto rules pass.
        take = _make_motion_take(identity_score=0.95, motion_score=0.85)
        ctrl, project, mutations = self._make_ctrl_and_project(motion_takes=[take])

        ctrl._run_auto_approve_pass("PERFORMANCE_REVIEW")

        shot = project["scenes"][0]["shots"][0]
        assert shot.get("approved_motion_take_id") == take["id"], (
            "approved_motion_take_id should be set to the best take's id"
        )
        assert shot.get("motion_auto_approved") is True
        audit = shot.get("auto_approve_audit", [])
        assert len(audit) == 1
        assert audit[0]["gate"] == "motion"
        assert audit[0]["auto_approved"] is True

    def test_motion_gate_on_vetoes_low_identity(self, monkeypatch):
        """Flag set + identity below threshold → vetoed; no approved_motion_take_id;
        audit entry recorded with auto_approved=False."""
        monkeypatch.setenv("CINEMA_AUTO_APPROVE_MOTION", "1")

        # identity=0.60 < 0.85 default threshold → motion_identity_below_threshold fires.
        take = _make_motion_take(identity_score=0.60, motion_score=0.85)
        ctrl, project, mutations = self._make_ctrl_and_project(motion_takes=[take])

        ctrl._run_auto_approve_pass("PERFORMANCE_REVIEW")

        shot = project["scenes"][0]["shots"][0]
        assert shot.get("approved_motion_take_id") is None, (
            "vetoed: approved_motion_take_id must not be set"
        )
        assert shot.get("motion_auto_approved") is None, (
            "vetoed: motion_auto_approved must not be set"
        )
        audit = shot.get("auto_approve_audit", [])
        assert len(audit) == 1
        assert audit[0]["gate"] == "motion"
        assert audit[0]["auto_approved"] is False
        assert any("identity" in r for r in audit[0].get("vetoes", [])), (
            "veto reason should mention identity"
        )

    def test_motion_mutator_picks_best_take_by_motion_fidelity(self, monkeypatch):
        """When two takes exist, mutator picks by motion_fidelity (primary key),
        not identity_score or list order."""
        monkeypatch.setenv("CINEMA_AUTO_APPROVE_MOTION", "1")

        # take_a: higher motion_fidelity, lower identity_score.
        # take_b: lower motion_fidelity, higher identity_score.
        # mutator MUST pick take_a (motion_fidelity is primary).
        take_a = {
            "id": "take_a",
            "kind": "motion",
            "path": "/tmp/a.mp4",
            "metadata": {"motion_fidelity": 0.92, "identity_score": 0.87},
            "cascade_metadata": {"fallback": False},
        }
        take_b = {
            "id": "take_b",
            "kind": "motion",
            "path": "/tmp/b.mp4",
            "metadata": {"motion_fidelity": 0.75, "identity_score": 0.96},
            "cascade_metadata": {"fallback": False},
        }
        ctrl, project, mutations = self._make_ctrl_and_project(
            motion_takes=[take_a, take_b]
        )

        ctrl._run_auto_approve_pass("PERFORMANCE_REVIEW")

        shot = project["scenes"][0]["shots"][0]
        assert shot.get("approved_motion_take_id") == "take_a", (
            "mutator must pick take_a (higher motion_fidelity=0.92 > 0.75), "
            f"got: {shot.get('approved_motion_take_id')!r}"
        )
