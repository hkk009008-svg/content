# Capability Test Suite — Gates / Auto-Approve Orchestration (offline) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `gates_orchestration` offline capability dimension to `tests/capability/` — covering the genuine offline blind spots in the auto-approve veto machinery (`cinema/auto_approve.py`), the gate-enforcement lifecycle trap (`cinema/lifecycle.py`), and the ChiefDirector's own veto-decision composition (`llm/chief_director.py`) — filling the "orchestration core" gap the spec (§7) names as the highest-leverage untested machinery after Identity.

**Architecture:** A new dimension folder `tests/capability/gates_orchestration/` built on the *exact* Plan-1 pattern: no `__init__.py` (collected by path; `_ledger`/`_scorecard` import as top-level via the conftest `sys.path` shim), `@pytest.mark.offline` on every test, each test ends with `capability_record(claim_id=..., passed=True)`, and the dimension ends with a ledger-drift guard. Every assertion is grounded in a verified source `file:line` and was classified **assert-new** (no existing test) by a source map — behaviors already covered in `tests/unit/` are **cross-linked** in the ledger, not re-asserted. The existing suite (3375 tests) is untouched and purely additive.

**Tech Stack:** Python 3, pytest (markers via the existing `tests/capability/conftest.py`). No torch/DeepFace/network/GPU/spend — all targets construct from plain dicts + dataclass defaults. Always run via the project venv: `.venv/bin/python -m pytest`.

**Spec:** `docs/superpowers/specs/2026-06-01-comprehensive-capability-test-suite-design.md` (§4 Gates/Headless row, §8.2 priority order, §6 stub/gap policy). This plan is the **Plan 2** named in `docs/superpowers/plans/2026-06-01-capability-suite-foundation-identity.md` "Follow-on plans".

**Source-map provenance:** every assert-new claim below was produced by a parallel reader sweep (workflow `wf_d209fa56-7c2`) that pasted source evidence + grepped `tests/` to confirm "no existing test", then spot-verified in main against `cinema/auto_approve.py`, `cinema/lifecycle.py`, `llm/chief_director.py` at HEAD `41dee2dd`.

**Branch note:** The shared working tree is on `main`. Do NOT switch branches (live peers per the four-seat protocol). Commit additively via explicit pathspec (`git commit -- <paths>` with `-m` BEFORE `--`) — the shared index may hold a peer's staged files. Subagents prefix all git with `env -u GIT_INDEX_FILE`.

---

## File Structure

| File | Responsibility |
|---|---|
| `tests/capability/_ledger.py` | **Modify** — append the `gates_orchestration` dimension claims (`GATE-01..15`, `CD-01..06`, one `INTENDED_NOT_WIRED`, three cross-links); fix the two stale Identity anchors (`ID-03`, `ID-04`) the map exposed. |
| `tests/capability/gates_orchestration/test_gate_predicates.py` | **Create** — offline tests for `cinema/auto_approve.py` veto machinery (rule-absence branches, pure scoring helpers, motion/final firing, `record_director_review_on_shots`) + the `cinema/lifecycle.py` NullLifecycle always-True trap. Ends with the ledger-drift guard. |
| `tests/capability/gates_orchestration/test_chief_director_veto.py` | **Create** — offline tests for `llm/chief_director.py` veto-decision composition (no-client branches, except-fallback `mutation_level` tiering, `validate_shot_prompts` passthrough, `_strip_json_fences`, `get_diagnostic_summary`). |

> **No `__init__.py` anywhere under `tests/capability/`** — the dimension folder is collected by path; `capability_record` infers `dimension="gates_orchestration"` from the path position (`tests/capability/<dimension>/...`), so the scorecard rolls these up under `gates_orchestration` with no manual dimension argument.

> **Construction-trap note (verified, load-bearing):** `AutoApproveConfig()` (direct dataclass) has `image_min_composite=0.97`; **`AutoApproveConfig.from_project({})` returns `0.60`** because `quality_tier` defaults to `"production"` (`cinema/auto_approve.py:137`). These tests therefore pass `config=AutoApproveConfig(...)` **explicitly** to `check_gate` / the rule builders and never rely on `from_project` defaults, so motion/final thresholds are the class defaults (`motion_min_motion_score=0.7`, `motion_min_identity=0.85`, `final_min_lipsync=0.8`).

---

## Chunk 1: Gate / auto-approve + lifecycle machinery

### Task 1: Ledger claims for `gates_orchestration` + fix stale Identity anchors

**Files:**
- Modify: `tests/capability/_ledger.py`

- [ ] **Step 1: Verify the two stale Identity anchors against source before editing**

Run:
```bash
.venv/bin/python - <<'PY'
import subprocess
for pat in ["def score_candidate", "score.composite =", "def should_halt"]:
    print(pat, "->")
    print(subprocess.run(["grep","-nE",pat,"face_validator_gate.py"],capture_output=True,text=True).stdout)
PY
```
Expected: the composite arithmetic (`score.composite = ...`) is at `face_validator_gate.py:213` and `def should_halt` at `:228` — confirming the ledger's `ID-03` anchor `:165` and `ID-04` anchor `:225` are stale. (Both line numbers were verified at HEAD `41dee2dd`; if a peer commit shifted them, use the line numbers the grep prints — source wins.) Record the corrected line numbers in the commit body.

- [ ] **Step 2: Fix the `ID-03` and `ID-04` `manual_section` anchors in `LEDGER`**

In `tests/capability/_ledger.py`, change the `ID-03` claim's `manual_section` from `"manual §4 Stage2 / face_validator_gate.py:165"` to `"manual §4 Stage2 / face_validator_gate.py:213"`, and the `ID-04` claim's from `"manual §4 Stage2 / face_validator_gate.py:225"` to `"manual §4 Stage2 / face_validator_gate.py:228"` (use the Step-1-verified line numbers). Do NOT touch the `claim_id`, `tier`, `status`, or `description` fields.

- [ ] **Step 3: Append the `gates_orchestration` claims to the `LEDGER` list**

Append these `Claim(...)` entries to the `LEDGER` list in `tests/capability/_ledger.py` (after the existing Identity entries, before the closing `]`):

```python
    # --- gates_orchestration dimension (Plan 2) ---
    # auto-approve veto machinery (cinema/auto_approve.py) — assert-new offline
    Claim("GATE-01", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:218", "offline", "asserted",
          "_rules_for_plan omits plan_decision_not_approved when plan_require_approved=False"),
    Claim("GATE-02", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:230", "offline", "asserted",
          "_rules_for_plan omits plan_has_violations when plan_reject_on_violations=False"),
    Claim("GATE-03", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:298", "offline", "asserted",
          "_rules_for_image omits image_composite_below_threshold when image_min_composite<=0"),
    Claim("GATE-04", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:326", "offline", "asserted",
          "_rules_for_image omits image_cascade_fallback when image_veto_on_fallback=False"),
    Claim("GATE-05", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:337", "offline", "asserted",
          "_rules_for_image omits image_over_budget when image_max_spent_multiplier<=0"),
    Claim("GATE-06", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:413", "offline", "asserted",
          "_rules_for_final omits final_upstream_was_auto_approved when final_require_human_if_upstream_auto=False"),
    Claim("GATE-07", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:600", "offline", "asserted",
          "_any_take_has_fallback True only for dict cascade_metadata with fallback is True"),
    Claim("GATE-08", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:458", "offline", "asserted",
          "_best_take_identity max finite identity_score; 0.0 for empty/non-finite-only"),
    Claim("GATE-09", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:471", "offline", "asserted",
          "_best_take_motion_score prefers motion_fidelity over motion_score; 0.0 for empty"),
    Claim("GATE-10", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:525", "offline", "asserted",
          "_best_take_lipsync non-finite score fails closed -> 0.0 (not 1.0 N/A)"),
    Claim("GATE-11", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:618", "offline", "asserted",
          "_shot_over_budget: NaN budget->True; 0 budget->False; 0 total_shots->False; over-cap->True"),
    Claim("GATE-12", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:374", "offline", "asserted",
          "check_gate('motion') fires motion_score_below_threshold when best motion_fidelity<0.7"),
    Claim("GATE-13", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:416", "offline", "asserted",
          "check_gate('final') fires final_upstream_was_auto_approved when an upstream auto-approve flag is set"),
    Claim("GATE-14", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:283", "offline", "asserted",
          "record_director_review_on_shots skips non-dict shot items without raising"),
    Claim("GATE-15", "gates_orchestration", "spec §4 Headless / cinema/lifecycle.py:89", "offline", "asserted",
          "NullLifecycle.wait_for_gate returns True regardless of predicate (always-True trap)"),
    # ChiefDirector veto-decision composition (llm/chief_director.py) — assert-new offline
    Claim("CD-01", "gates_orchestration", "spec §4 Gates / llm/chief_director.py:459", "offline", "asserted",
          "evaluate_generation_quality no-client + identity fail -> RETRY mutation_level=1"),
    Claim("CD-02", "gates_orchestration", "spec §4 Gates / llm/chief_director.py:461", "offline", "asserted",
          "evaluate_generation_quality no-client + coherence-only fail (identity passed) -> ACCEPT"),
    Claim("CD-03", "gates_orchestration", "spec §4 Gates / llm/chief_director.py:650", "offline", "asserted",
          "except-fallback mutation_level tiering: >0.55->1, >0.40->2, else->3; None->1"),
    Claim("CD-04", "gates_orchestration", "spec §4 Gates / llm/chief_director.py:305", "offline", "asserted",
          "validate_shot_prompts no-client -> APPROVED passthrough (no violations)"),
    Claim("CD-05", "gates_orchestration", "spec §4 Gates / llm/chief_director.py:27", "offline", "asserted",
          "_strip_json_fences strips ```json/``` fences; passthrough when no fence"),
    Claim("CD-06", "gates_orchestration", "spec §4 Gates / llm/chief_director.py:653", "offline", "asserted",
          "get_diagnostic_summary empty sentinel + per-entry [stage] decision (score=) line"),
    # INTENDED_NOT_WIRED stub (spec §6) — already pinned; documented in the ledger as a gap
    Claim("GATE-NW-01", "gates_orchestration", "spec §6 / face_validator_gate.py:303", "offline", "INTENDED_NOT_WIRED",
          "should_halt budget_only falls back to composite_only (never-early-halt deferred); "
          "pinned by tests/unit/test_should_halt_conjunctive.py::TestBudgetOnlyModeDeferred"),
    # cross-links — already covered in tests/unit; mapped here so the ledger is a complete picture
    Claim("GATE-XL-01", "gates_orchestration", "spec §4 Headless / cinema/review/controller.py:558", "offline", "cross-linked",
          "headless _wait_for_gate raises GateNotSatisfiedError when gate unsatisfied "
          "(tests/unit/test_cross_controller.py::test_wait_for_gate_headless_raises_when_unsatisfied)"),
    Claim("GATE-XL-02", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:278", "offline", "cross-linked",
          "record_director_review_on_shots MODIFIED->APPROVED normalization "
          "(tests/unit/test_auto_approve.py::TestRecordDirectorReview)"),
    Claim("GATE-XL-03", "gates_orchestration", "spec §4 Gates / cinema/auto_approve.py:728", "offline", "cross-linked",
          "check_gate predicate-exception -> deferred decision "
          "(tests/unit/test_auto_approve.py::TestDeferredDecision)"),
```

- [ ] **Step 4: Run the ledger's own invariants to verify no duplicate / bad-field claim**

Run: `.venv/bin/python -m pytest tests/capability/test_framework_smoke.py -v`
Expected: PASS — `test_ledger_claim_ids_are_unique` and the existing ledger tests stay green (every new `tier` is `offline`, every `status` ∈ {asserted, cross-linked, INTENDED_NOT_WIRED}, so `Claim.__post_init__` does not raise and `assert_unique()` passes).

- [ ] **Step 5: Commit**

```bash
git add tests/capability/_ledger.py
git commit -- tests/capability/_ledger.py \
  -m "test(capability): seed gates_orchestration ledger claims + fix stale ID-03/04 anchors"
```

---

### Task 2: `test_gate_predicates.py` — rule-absence branches + pure scoring helpers (GATE-01..11)

**Files:**
- Create: `tests/capability/gates_orchestration/test_gate_predicates.py`

- [ ] **Step 1: Write the tests** (`tests/capability/gates_orchestration/test_gate_predicates.py`)

```python
"""Offline capability tests for cinema/auto_approve.py veto machinery.

All targets construct from plain dicts + AutoApproveConfig dataclass defaults —
no torch/DeepFace/network. We pass `config=AutoApproveConfig(...)` explicitly so
the from_project tier-aware default (production -> 0.60) never confuses a
threshold assertion (cinema/auto_approve.py:137).
"""
import math

import pytest

from cinema.auto_approve import (
    AutoApproveConfig,
    _rules_for_plan,
    _rules_for_image,
    _rules_for_final,
    _any_take_has_fallback,
    _best_take_identity,
    _best_take_motion_score,
    _best_take_lipsync,
    _shot_over_budget,
)


def _rule_names(rules):
    return {r.name for r in rules}


# --- rule-absence branches: a config flag removes a veto rule (GATE-01..06) ---

@pytest.mark.offline
def test_plan_rule_absent_when_require_approved_false(capability_record):
    assert "plan_decision_not_approved" in _rule_names(_rules_for_plan(AutoApproveConfig()))
    assert "plan_decision_not_approved" not in _rule_names(
        _rules_for_plan(AutoApproveConfig(plan_require_approved=False)))
    capability_record(claim_id="GATE-01", passed=True)


@pytest.mark.offline
def test_plan_violations_rule_absent_when_reject_on_violations_false(capability_record):
    assert "plan_has_violations" in _rule_names(_rules_for_plan(AutoApproveConfig()))
    assert "plan_has_violations" not in _rule_names(
        _rules_for_plan(AutoApproveConfig(plan_reject_on_violations=False)))
    capability_record(claim_id="GATE-02", passed=True)


@pytest.mark.offline
def test_image_composite_rule_absent_when_min_composite_zero(capability_record):
    assert "image_composite_below_threshold" in _rule_names(_rules_for_image(AutoApproveConfig()))
    assert "image_composite_below_threshold" not in _rule_names(
        _rules_for_image(AutoApproveConfig(image_min_composite=0)))
    capability_record(claim_id="GATE-03", passed=True)


@pytest.mark.offline
def test_image_fallback_rule_absent_when_veto_on_fallback_false(capability_record):
    assert "image_cascade_fallback" in _rule_names(_rules_for_image(AutoApproveConfig()))
    assert "image_cascade_fallback" not in _rule_names(
        _rules_for_image(AutoApproveConfig(image_veto_on_fallback=False)))
    capability_record(claim_id="GATE-04", passed=True)


@pytest.mark.offline
def test_image_budget_rule_absent_when_multiplier_zero(capability_record):
    assert "image_over_budget" in _rule_names(_rules_for_image(AutoApproveConfig()))
    assert "image_over_budget" not in _rule_names(
        _rules_for_image(AutoApproveConfig(image_max_spent_multiplier=0)))
    capability_record(claim_id="GATE-05", passed=True)


@pytest.mark.offline
def test_final_upstream_rule_absent_when_require_human_false(capability_record):
    assert "final_upstream_was_auto_approved" in _rule_names(_rules_for_final(AutoApproveConfig()))
    assert "final_upstream_was_auto_approved" not in _rule_names(
        _rules_for_final(AutoApproveConfig(final_require_human_if_upstream_auto=False)))
    capability_record(claim_id="GATE-06", passed=True)


# --- pure scoring helpers (GATE-07..11) ---

@pytest.mark.offline
def test_any_take_has_fallback_only_for_dict_fallback_true(capability_record):
    assert _any_take_has_fallback([{"cascade_metadata": {"fallback": True}}]) is True
    assert _any_take_has_fallback([{"cascade_metadata": {"fallback": False}}]) is False
    assert _any_take_has_fallback([{"cascade_metadata": None}]) is False
    assert _any_take_has_fallback([{"cascade_metadata": "notadict"}]) is False
    assert _any_take_has_fallback([{}]) is False
    assert _any_take_has_fallback([]) is False
    capability_record(claim_id="GATE-07", passed=True)


@pytest.mark.offline
def test_best_take_identity_max_finite_else_zero(capability_record):
    assert _best_take_identity(
        [{"metadata": {"identity_score": 0.7}}, {"metadata": {"identity_score": 0.9}}]) == pytest.approx(0.9)
    assert _best_take_identity([{"metadata": {"identity_score": float("inf")}}]) == 0.0
    assert _best_take_identity([]) == 0.0
    capability_record(claim_id="GATE-08", passed=True)


@pytest.mark.offline
def test_best_take_motion_score_prefers_motion_fidelity(capability_record):
    # motion_fidelity wins over motion_score within a take
    assert _best_take_motion_score(
        [{"metadata": {"motion_fidelity": 0.8, "motion_score": 0.5}}]) == pytest.approx(0.8)
    # falls back to motion_score when motion_fidelity absent
    assert _best_take_motion_score([{"metadata": {"motion_score": 0.6}}]) == pytest.approx(0.6)
    assert _best_take_motion_score([]) == 0.0
    capability_record(claim_id="GATE-09", passed=True)


@pytest.mark.offline
def test_best_take_lipsync_nonfinite_fails_closed(capability_record):
    # any_score_present is set BEFORE the isfinite check (cinema/auto_approve.py:515/525),
    # so a take whose only lipsync_score is inf/nan yields 0.0, NOT the 1.0 N/A default.
    assert _best_take_lipsync([{"metadata": {"lipsync_score": float("inf")}}]) == 0.0
    assert _best_take_lipsync([{"metadata": {"lipsync_score": float("nan")}}]) == 0.0
    # sanity: no dialogue/score at all -> 1.0 N/A pass
    assert _best_take_lipsync([{"metadata": {}}]) == pytest.approx(1.0)
    capability_record(claim_id="GATE-10", passed=True)


@pytest.mark.offline
def test_shot_over_budget_edges(capability_record):
    def proj(budget, n_shots):
        return {"global_settings": {"budget_limit_usd": budget},
                "scenes": [{"shots": [{}] * n_shots}] if n_shots else []}
    # NaN budget cap -> fail-closed veto fires
    assert _shot_over_budget({"spent_usd": 1.0}, proj(float("nan"), 1), 1.5) is True
    # zero budget -> no cap -> False
    assert _shot_over_budget({"spent_usd": 9999.0}, proj(0, 1), 1.5) is False
    # zero total_shots -> cannot compute per-shot cap -> False
    assert _shot_over_budget({"spent_usd": 999.0}, proj(10, 0), 1.5) is False
    # over the multiplier*per-shot cap -> True  (per_shot=10, 1.5*10=15, spent 100>15)
    assert _shot_over_budget({"spent_usd": 100.0}, proj(10, 1), 1.5) is True
    capability_record(claim_id="GATE-11", passed=True)
```

- [ ] **Step 2: Run to verify it passes against current source**

Run: `.venv/bin/python -m pytest tests/capability/gates_orchestration/test_gate_predicates.py -v`
Expected: PASS. If any value differs from source (e.g. a default changed), **correct the test to the source value** and note the divergence in the Task-3 commit body (plan-vs-source rule). The first run also proves the no-`__init__.py` path-collection + conftest `sys.path` shim resolve for this new subdir.

- [ ] **Step 3: Commit**

```bash
git add tests/capability/gates_orchestration/test_gate_predicates.py
git commit -- tests/capability/gates_orchestration/test_gate_predicates.py \
  -m "test(capability): gates_orchestration — rule-absence branches + scoring helpers (GATE-01..11)"
```

---

### Task 3: `test_gate_predicates.py` — gate firing + record-review + lifecycle trap (GATE-12..15)

**Files:**
- Modify: `tests/capability/gates_orchestration/test_gate_predicates.py`

- [ ] **Step 1: Extend the imports, then append the tests**

First **extend the existing top-of-file import block** (do NOT add a duplicate `from cinema.auto_approve import` statement): add `check_gate` and `record_director_review_on_shots` to the Task-2 `from cinema.auto_approve import (...)` block, and add a new line `from cinema.lifecycle import NullLifecycle` beside it. Then append the test functions below to the end of the file:

```python
@pytest.mark.offline
def test_motion_gate_fires_on_low_motion_fidelity(capability_record):
    # identity_score high (0.99 >= 0.85 passes the identity rule) isolates the motion rule;
    # motion_fidelity 0.5 < 0.7 fires motion_score_below_threshold.
    dec = check_gate(
        "motion",
        shot_state={},
        project={},
        takes=[{"metadata": {"identity_score": 0.99, "motion_fidelity": 0.5}}],
        config=AutoApproveConfig(),
    )
    assert dec.auto_approved is False
    assert "motion_score_below_threshold" in dec.rule_names
    capability_record(claim_id="GATE-12", passed=True)


@pytest.mark.offline
def test_final_gate_fires_on_upstream_auto_approval(capability_record):
    # lipsync_score 1.0 passes the lipsync rule (1.0 >= 0.8) so the only veto is the
    # safety-net: an upstream gate auto-approved this shot -> require a human at final.
    dec = check_gate(
        "final",
        shot_state={"plan_auto_approved": True},
        project={},
        takes=[{"metadata": {"lipsync_score": 1.0}}],
        config=AutoApproveConfig(),
    )
    assert dec.auto_approved is False
    assert "final_upstream_was_auto_approved" in dec.rule_names
    capability_record(claim_id="GATE-13", passed=True)


@pytest.mark.offline
def test_record_director_review_skips_non_dict_items(capability_record):
    shots = [None, {"id": "a"}, 42]
    record_director_review_on_shots(shots, {"decision": "APPROVED", "violations": []})
    assert shots[0] is None and shots[2] == 42        # non-dicts untouched
    assert shots[1]["director_review"]["decision"] == "APPROVED"
    capability_record(claim_id="GATE-14", passed=True)


@pytest.mark.offline
def test_nulllifecycle_wait_for_gate_always_true(capability_record):
    # The always-True trap: NullLifecycle.wait_for_gate returns True regardless of the
    # predicate (cinema/lifecycle.py:89) — so using it OUTSIDE a test/headless context
    # silently skips gate enforcement. This isolates that contract (no ReviewController stack).
    lc = NullLifecycle()
    assert lc.wait_for_gate("PLAN_REVIEW", lambda: False) is True
    assert lc.wait_for_gate("PLAN_REVIEW", lambda: True) is True
    capability_record(claim_id="GATE-15", passed=True)
```

- [ ] **Step 2: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/capability/gates_orchestration/test_gate_predicates.py -v`
Expected: PASS (all 15 GATE tests). If `dec.rule_names` / `dec.auto_approved` attribute names differ, inspect `AutoApproveDecision` (`cinema/auto_approve.py`) and correct; if `NullLifecycle.wait_for_gate` requires extra args, read `cinema/lifecycle.py:89` and match the signature (source wins).

- [ ] **Step 3: Commit**

```bash
git add tests/capability/gates_orchestration/test_gate_predicates.py
git commit -- tests/capability/gates_orchestration/test_gate_predicates.py \
  -m "test(capability): gates_orchestration — motion/final firing + record-review + NullLifecycle trap (GATE-12..15)"
```

---

## Chunk 2: ChiefDirector veto-decision composition

### Task 4: `test_chief_director_veto.py` — the LLM-layer decision logic (CD-01..06)

**Files:**
- Create: `tests/capability/gates_orchestration/test_chief_director_veto.py`

> **Construction note (verified against source):** `ChiefDirector(project={})` runs `_init_client()`, which returns `None` when no API key is present — so `cd.client is None` in CI and the **no-client decision branches are reachable with zero mocking**. For the except-fallback tiering (CD-03), set `cd.client` to a truthy sentinel and monkeypatch `cd._call_llm` to raise, which forces the `except` path that computes `mutation_level`. **`evaluate_generation_quality` (`llm/chief_director.py:406`) has signature `(self, image_path, reference_path, identity_result=None, identity_score=0.0, shot_prompt="", scene_context="", coherence_result=None, reference_paths=None)` — `image_path` AND `reference_path` are both required positionals, so every call below passes `image_path=None, reference_path=None`.** `identity_score` is a real kwarg (default `0.0`): passing it with `identity_result=None` drives `identity_passed = identity_score >= threshold` (default threshold `0.70`); coherence is supplied via a small object exposing `.overall_coherence_score`.

- [ ] **Step 1: Write the tests** (read `evaluate_generation_quality`'s signature at `llm/chief_director.py:406` first and match the argument names)

```python
"""Offline capability tests for llm/chief_director.py veto-decision composition.

These exercise the ChiefDirector's OWN decision logic (the spec §7 blind spot) —
NOT the parse paths (test_chief_director_parse.py) or the gate's consumption
(test_auto_approve.py). No real LLM call: the no-client branches need zero mocking;
the except-fallback tiering monkeypatches _call_llm to raise.
"""
import types

import pytest

from llm.chief_director import ChiefDirector, _strip_json_fences


def _coherence(score):
    return types.SimpleNamespace(overall_coherence_score=score)


def _cd():
    cd = ChiefDirector(project={})
    cd.client = None  # ensure the no-client path even if a key leaks into the env
    return cd


@pytest.mark.offline
def test_no_client_identity_fail_retries_level_one(capability_record):
    cd = _cd()
    # identity below the 0.70 default threshold, coherence passing -> not the ACCEPT
    # short-circuit; no client -> RETRY mutation_level=1.
    out = cd.evaluate_generation_quality(
        image_path=None, reference_path=None, identity_result=None,
        coherence_result=_coherence(0.9), identity_score=0.50,
    )
    assert out["decision"] == "RETRY"
    assert out["mutation_level"] == 1
    capability_record(claim_id="CD-01", passed=True)


@pytest.mark.offline
def test_no_client_coherence_only_fail_accepts(capability_record):
    cd = _cd()
    # identity passes (0.90 >= 0.70), coherence fails (0.30 < 0.6); no client -> ACCEPT
    # (the coherence-only failure is not actioned without an LLM).
    out = cd.evaluate_generation_quality(
        image_path=None, reference_path=None, identity_result=None,
        coherence_result=_coherence(0.30), identity_score=0.90,
    )
    assert out["decision"] == "ACCEPT"
    capability_record(claim_id="CD-02", passed=True)


@pytest.mark.offline
def test_except_fallback_mutation_level_tiering(capability_record):
    # The except-fallback (llm/chief_director.py:603-651) wraps json.loads of the LLM
    # reply — NOT the _call_llm call itself. So we make _call_llm RETURN unparseable
    # text; json.loads then raises and the except tiers the retry by identity_score:
    # >0.55->1, >0.40->2, else->3 (strict >). None->1.
    def _bad_json(*a, **k):
        return "}{ not valid json"

    def _level(identity_score, coherence_result):
        cd = ChiefDirector(project={})
        cd.client = object()        # truthy -> skip the no-client early return
        cd._call_llm = _bad_json    # returns garbage -> json.loads raises -> except-fallback
        out = cd.evaluate_generation_quality(
            image_path=None, reference_path=None, identity_result=None,
            coherence_result=coherence_result, identity_score=identity_score,
        )
        assert out["decision"] == "RETRY", out
        return out["mutation_level"]

    # numeric tiering: identity < 0.70 fails -> identity_passed=False -> no ACCEPT
    # short-circuit; coherence_result=None skips the prompt-builder's coherence_info
    # block (reads color_drift/lighting_consistency, llm/chief_director.py:517-524).
    assert _level(0.60, None) == 1
    assert _level(0.45, None) == 2
    assert _level(0.30, None) == 3
    # None identity (skipped): identity_passed=True, so coherent must be False to avoid
    # the ACCEPT short-circuit — hence a FULL coherence mock the prompt-builder can read.
    full_coherence = types.SimpleNamespace(
        overall_coherence_score=0.30, color_drift=0.10,
        lighting_consistency=0.90, recommendations=[])
    assert _level(None, full_coherence) == 1
    capability_record(claim_id="CD-03", passed=True)


@pytest.mark.offline
def test_validate_shot_prompts_no_client_passthrough(capability_record):
    cd = _cd()
    shots = [{"prompt": "a wide shot"}]
    out = cd.validate_shot_prompts(shots, {"id": "scene_1"})
    assert out["decision"] == "APPROVED"
    assert out["violations"] == []
    assert out["shots"] is shots
    capability_record(claim_id="CD-04", passed=True)


@pytest.mark.offline
def test_strip_json_fences(capability_record):
    assert _strip_json_fences('```json\n{"a":1}\n```') == '{"a":1}'
    assert _strip_json_fences('```\n{"a":1}\n```') == '{"a":1}'
    assert _strip_json_fences('{"a":1}') == '{"a":1}'
    capability_record(claim_id="CD-05", passed=True)


@pytest.mark.offline
def test_get_diagnostic_summary_empty_and_populated(capability_record):
    cd = _cd()
    assert cd.get_diagnostic_summary() == "No diagnostic data collected."
    cd.diagnostic_log.append(
        {"stage": "shot_validation", "decision": "APPROVED", "score": 0.9})
    summary = cd.get_diagnostic_summary()
    assert "shot_validation" in summary and "APPROVED" in summary and "0.9" in summary
    capability_record(claim_id="CD-06", passed=True)
```

- [ ] **Step 2: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/capability/gates_orchestration/test_chief_director_veto.py -v`
Expected: PASS (6 CD tests). The most likely correction is the `evaluate_generation_quality` keyword names — match them to `llm/chief_director.py:406` exactly (e.g. `identity_result` vs `identity_score`; if the method derives `identity_score` from `identity_result.overall_score`, build a `types.SimpleNamespace(overall_score=..., threshold_used=0.70)` and pass it as `identity_result`). Correct to source; note any divergence in the commit body.

- [ ] **Step 3: Commit**

```bash
git add tests/capability/gates_orchestration/test_chief_director_veto.py
git commit -- tests/capability/gates_orchestration/test_chief_director_veto.py \
  -m "test(capability): gates_orchestration — ChiefDirector veto-decision composition (CD-01..06)"
```

---

## Chunk 3: Ledger-drift guard + full-suite green

### Task 5: Dimension drift guard + suite/collection verification

**Files:**
- Modify: `tests/capability/gates_orchestration/test_gate_predicates.py` (append the guard)

- [ ] **Step 1: Append the ledger-drift guard** (mirrors `test_identity_offline_claims_are_exercised`, which carries `@pytest.mark.offline` — the marker is REQUIRED so the guard is not silently skipped under CI's `pytest tests/capability -m offline` filter)

```python
@pytest.mark.offline
def test_gates_offline_claims_are_exercised():
    """Guard against silent ledger drift: the set of offline 'asserted' claims in the
    gates_orchestration dimension must equal exactly the claims these test files record."""
    import _ledger  # top-level via conftest sys.path shim
    offline_asserted = {c.claim_id for c in _ledger.by_dimension("gates_orchestration")
                        if c.tier == "offline" and c.status == "asserted"}
    expected = {f"GATE-{i:02d}" for i in range(1, 16)} | {f"CD-{i:02d}" for i in range(1, 7)}
    assert offline_asserted == expected
```

- [ ] **Step 2: Run the whole capability suite — must be green and emit a gates_orchestration scorecard section**

Run: `.venv/bin/python -m pytest tests/capability/ -v`
Expected: PASS; the terminal "CAPABILITY SCORECARD" section now shows a `gates_orchestration` block alongside `identity` (21 pass / 0 fail for the dimension).

- [ ] **Step 3: Confirm no regression to the existing suite (collection only)**

Run: `.venv/bin/python -m pytest --collect-only -q 2>/dev/null | tail -1`
Expected: collected count = prior baseline (3375) + the new capability tests (21 GATE/CD + the guard = 22), no collection errors. If the baseline has moved (peer commits), the delta — not the absolute — must be +22.

- [ ] **Step 4: Run the §15 smoke to confirm the truth-layer invariants still hold**

Run: `.venv/bin/python scripts/ci_smoke.py`
Expected: OK (the ledger anchor fixes in Task 1 keep `ID-03`/`ID-04` truthful; no ARCHITECTURE.md claim is touched).

- [ ] **Step 5: Commit**

```bash
git add tests/capability/gates_orchestration/test_gate_predicates.py
git commit -- tests/capability/gates_orchestration/test_gate_predicates.py \
  -m "test(capability): gates_orchestration ledger-drift guard + full-suite green"
```

---

## Done criteria (Plan 2)

- `.venv/bin/python -m pytest tests/capability/ -v` is green and prints a capability scorecard with **both** an `identity` and a `gates_orchestration` section.
- The auto-approve orchestration core has offline coverage for its previously-untested branches: rule-absence config flags (`GATE-01..06`), pure scoring helpers incl. the fail-closed `_best_take_lipsync`/`_shot_over_budget` guards (`GATE-07..11`), motion/final gate *firing* (`GATE-12/13`), `record_director_review_on_shots` non-dict skip (`GATE-14`), and the `NullLifecycle` always-True trap (`GATE-15`).
- The ChiefDirector veto-decision composition has offline coverage (`CD-01..06`) — the spec §7 blind spot.
- The two stale Identity ledger anchors (`ID-03`, `ID-04`) are corrected; the `budget_only` INTENDED_NOT_WIRED stub is recorded in the ledger (cross-linked to its existing pin).
- Existing 3375-test suite still collects clean (+22, no regressions); §15 smoke green.

## Follow-on plans (not in scope here)

- **Plan 3** — remaining offline core: `domain/scene_decomposer.py` (`decompose`/`_fallback_decompose`), `style_director.py`, `lip_sync.py` routing, coherence/motion math, the cascade error/retry-classification paths. Same pattern.
- **Deferred from this plan (need prompt-capture; brittle, later):** the ChiefDirector `mutation_context` 2×2 matrix (`identity_only`/`style_only`/`aggressive`, `llm/chief_director.py:526`) and the coherence `>= 0.6` boundary as an *observable* — both require inspecting what is sent to the LLM (`_call_llm` args) rather than a return value; defer until a stable prompt-capture seam exists.
- **Plan 4** — thin-area offline (audio/loudness, format/assembly, cost) + the `stubs_and_gaps` dimension. **Plan 5** — live-component tier. **Plan 6** — golden E2E (built, never run without explicit user spend authorization).
