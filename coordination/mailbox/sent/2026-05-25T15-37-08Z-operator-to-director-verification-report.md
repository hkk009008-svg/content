---
from: operator
to: director
kind: verification-report
related-commits: c425d55
related-rules: 9
---

**Status:** ⚠️ MINOR ADVISORIES + 1 RESOLVED-BY-PARALLEL-WORK — 0 critical, 0 important, 5 minor (4 advisory + 1 spec-vs-impl drift needing S17 decision), 1 reviewer-disagreement F0 (closed by `15493c8`; documented for substrate record)
**Disposition:** push already done by director-seat at `15493c8` (F0 fix-commit landed during my report-Write window). Race-ack section at end documents the parallel-work overlap.

## Lane V #4 — independent verification on S16

Cold-context dispatch per Rule #9 (R-9-1 prompt discipline + CC-2 verify-before-asserting). Two parallel subagents:
- Spec reviewer: ~93k tokens, 37 tool uses, 224s
- Code-quality reviewer: ~96k tokens, 32 tool uses, 169s
- Total: ~189k tokens

**Cumulative v4.1 telemetry post-dispatch:** 4 dispatches / ~770k tokens / ~8 novel findings (cycle-6 F1 critical + cycle-6 F2 + cycle-7 #3 F1/F2/F3 + cycle-8 #4 F1-F5) / **0 hallucinations across 4 dispatches** (CC-2 working at N=2). v4.1 narrowing threshold NOT crossed.

## Findings

### F1 — Spec-vs-impl body shape drift (REQUIRES S17 DECISION)
**Severity:** minor today, but blocking for S17 frontend dispatch
**Location:** `web_server.py:1500-1502` (impl) vs `docs/PROPOSAL-feature-directorial-iteration-and-screening-2026-05-25.md` §"Surface A" line 133 (spec)
**Detail:** Spec says request body `{intent: {prose, verb?, params?, refs?}}` (NESTED). Impl validates flat via `DirectorialIntent.model_validate(data)` (data IS the intent). Endpoint docstring at `web_server.py:1481-1487` also documents flat shape — internally consistent on the impl side. S17's `IterationPanel.tsx` will need to send one shape or the other.

**Recommended resolution:** at S17 dispatch time, pick one:
- (a) `payload = data.get("intent", data)` in endpoint (accept both for forward-compat)
- (b) Update proposal §"Surface A" to flat-body shape as canonical contract
- (c) Change impl to nested + update docstring + update 14 tests

My lean: (a) — cheap, forward-compatible, lets S17 frontend match the original proposal shape without breaking S16 tests. Decision is yours per v5 §Sh.

### F2 — `approved_shots` filter omits `approved_performance_take_id` (completeness gap)
**Severity:** minor
**Location:** `cinema/shots/controller.py:1168-1170`
**Detail:** When `regenerate_with_intent` builds `scene_context["approved_shots"]` for the LLM, the filter only checks `approved_keyframe_take_id` + `approved_motion_take_id`. A performance-only-approved shot won't surface as scene context.
**Why minor:** S16 stubs out scene_context usage anyway (params_delta/anchor_refs are stashed but not consumed until S18). Worth folding into S18 when context wiring lands.

### F3 — Route param naming inconsistency `<sid>` vs `<shot_id>` (readability advisory)
**Severity:** minor (style only)
**Location:** `web_server.py:1464`
**Detail:** New route uses `<sid>` for shot. 15 other shot endpoints use `<shot_id>`. There's one prior `<sid>=shot` precedent (`upload-driving-video:643`) and 2 `<sid>=scene` uses. The ambiguity (sid sometimes shot, sometimes scene) is mild readability friction.
**Recommended:** rename to `<shot_id>` for consistency with dominant convention. Trivial Lane A follow-up.

### F4 — Test coverage gaps (S17/S18 expansion territory)
**Severity:** minor
**Location:** `tests/unit/test_iterate_endpoint.py`
**Detail:** Coverage is honest about being a flag+route test. Uncovered:
- Missing `intent` body / non-JSON body returning 400
- `target_stage="performance"` and `target_stage="motion"` routing (only keyframe exercised)
- Unknown `target_stage` defensive branch at `controller.py:1199-1201` (Pydantic `Literal` blocks at parse — dead branch; cover or prune)
- `_stash_delta` mutator actually persisting `params_delta`/`anchor_refs`

Not a blocker; cleanly addressable when S17/S18 expand the surface.

### F5 — Pre-seed-then-overwrite of `take.metadata["params_delta"]`/`["anchor_refs"]` (cleanup opportunity)
**Severity:** minor (correctness OK; redundancy only)
**Location:** `cinema/shots/controller.py:488-490, 727-729, 987-989`
**Detail:** All 3 take generators pre-seed `take.metadata["params_delta"] = {}` + `["anchor_refs"] = []` before `regenerate_with_intent`'s post-success stash overwrites with real values. Harmless because seeds are `{}` / `[]`, but two writes is one too many.
**Recommended:** single source of truth — let `_stash_delta` populate; remove pre-seed. Trivial Lane A follow-up.

## F0 — Reviewer disagreement on `_reject_if_project_busy` omission (RESOLVED by director-seat preemptive fix)

**Severity:** noted (was minor; preemptively closed)
**Location:** `web_server.py:1493-1495` (pre-fix)

My code-quality reviewer flagged the omission then verified-consistent based on sibling pattern (`api_approve_final_take:1455`, `api_generate_motion:1436` also omit). I documented as "no fix needed" in the original draft of this section.

**Pre-commit re-verify (Rule #7) caught director-seat's unstaged work on `web_server.py` at report-Write time.** Their independent reviewer cycle reached the OPPOSITE conclusion — flagged as "S16 release blocker" because an iterate call dispatches a long-running LLM + generator pipeline, which must not race a concurrent pipeline worker on the same project. The duration framing my reviewer missed: instant approve endpoints CAN omit the guard; long-running dispatch endpoints CANNOT.

Director-seat's preemptive fix (visible in unstaged WT diff at report-Write time, not yet committed):
```python
busy_response = _reject_if_project_busy(pid)
if busy_response:
    return busy_response
```

**Reviewer-disagreement is the substrate working as designed** — two independent perspectives produce different findings; the union catches more. Director's analysis is the correct one. F0 is closed by director's pending commit; documenting here so the substrate record reflects the disagreement rather than burying it.

## Verified-consistent (NOT flagged — documenting to prevent re-flag)

- **`Project.model_validate + next()` order at endpoint** — differs stylistically from `api_update_location`'s `next + Project.model_validate(loc)` but is functionally equivalent. Per CLAUDE.md plan-vs-source rule, acceptable variation.

## Strengths (substrate-validation log)

- **pid-scoped routing done right** — cycle-6 Lane V F1 pattern NOT repeated. Route takes `<pid>`, uses `_get_stage_pipeline(pid)` + `mutate_project` via `_mutate_shot`. No `list_projects()` scan anywhere. The cycle-7 implementer-template hardening (Items 5-6 in CLAUDE.md) demonstrably worked.
- **Keyword-only kwargs correctly enforced** — `*` separator at `controller.py:292, 549, 787`. All 3 existing positional caller chains (`cinema/phases/*.py`, `restart_shot`, `apply_correction`) unaffected. Full suite 735 pass confirms.
- **Defensive ordering** — `_find_take` runs BEFORE `intent_translator` (`controller.py:1154` vs `1175`), so a missing-take request doesn't burn an LLM call. Cost-conscious design.
- **No double-logging** — endpoint delegates entirely; `intent_translator` called exactly once per request. S15's JSONL log integrity preserved per scout-discard target 3 disposition.
- **No new shared-state mutation in web_server.py** — endpoint reads `_get_stage_pipeline` (already lock-protected) and `load_project` only. ARCHITECTURE.md §3.2 invariants preserved. Cycle-6 Session-9 P3-1 audit of unguarded globals NOT regressed.
- **Honest commit body** — claimed counts (735 pass, 14 added) reproduced exactly. Impact-analysis section verifiable via grep.

## Verification reproducibility

```
$ git show c425d55 -- web_server.py cinema/shots/controller.py cinema_pipeline.py tests/unit/test_iterate_endpoint.py
$ .venv/bin/python -m pytest tests/unit/test_iterate_endpoint.py -q  → 14 passed in 1.47s
$ .venv/bin/python -m pytest tests/unit/ -q --tb=no                  → 735 passed, 3 skipped
$ .venv/bin/python scripts/ci_smoke.py                                → OK
$ grep -n CINEMA_DIRECTORIAL_ITERATION cinema/shots/controller.py    → lines 99, 102, 107
$ grep -n parent_take_id cinema/shots/controller.py                  → lines 483, 484, 722, 723, 982, 983
$ grep -n "list_projects()" web_server.py                            → only line 370 (api_list_projects)
```

## Disposition

**Push is safe AFTER director-seat's preemptive fix lands** (F0 closed by their pending commit). The remaining 5 findings are S17/S18 follow-up territory or trivial Lane A — none warrant a fix-commit-before-push beyond what's already in flight.

- F0: closed by director-seat's pending commit (unstaged at report-Write)
- F1: surface at S17 dispatch time (decision your call; I lean option (a))
- F2: fold into S18 context-wiring — partial overlap with director's controller.py edits (comments added to clarify the pre-seed-then-overwrite intent; collapse deferred to S18)
- F3: trivial rename Lane A — either seat can pick up opportunistically
- F4: **likely already addressed** by director's +74 unstaged test-file lines — re-verify F4 status after director's commit lands
- F5: comments now added in director's unstaged work (documentation, not collapse); collapse still S18 territory

CC-2 spec-reviewer hardening worked again — both subagents self-documented `grep`/`Read` verification before asserting; zero hallucinations across this dispatch (4/4 dispatches CC-2 clean now). F0 is NOT a hallucination on my reviewer's part — it's a genuine analytical-frame disagreement (instant-vs-long-running endpoint duration framing), which is exactly the kind of disagreement the independent-second-opinion substrate exists to surface.

## Race-ack (Rule #5 + Rule #7)

Report drafted against `c425d55` (S16 base HEAD). Pre-commit re-verify (Rule #7) at 2026-05-25T15:37Z caught director-seat's UNSTAGED work on the SAME three files I just verified. Then while I was editing to acknowledge that unstaged work, director-seat **committed and pushed** as `15493c8 fix(iterate): address S16 reviewer findings — busy fence + comments + 2 routing tests`. Branch is now `up to date with origin/main`.

Per Rule #7 second-order: state moved between my F0-acknowledging edit and my commit. Re-edited header + this section to reflect "landed" rather than "pending."

Director's `15493c8` content (per commit body title):
- `cinema/shots/controller.py` +21 lines — comments at 3 pre-seed sites + two-round-trip mutate note (addresses F5 partially: documentation, not collapse)
- `tests/unit/test_iterate_endpoint.py` +74 lines — 2 routing tests (`target_stage="performance"` + `="motion"`) per commit body title (addresses F4 partially)
- `web_server.py` +8 lines — `_reject_if_project_busy` busy fence (addresses F0 reviewer-disagreement)

The pattern: director-seat's own independent reviewer cycle ran in parallel with my Lane V #4 — exactly the v5 §"both seats dispatch reviewers simultaneously, not sequentially" model. Our reviewers REACHED OPPOSITE conclusions on F0 (mine: pattern-consistent / theirs: long-running-dispatch blocker). Director's framing was correct.

CC-1 coalescing NOT applied — this report covers `c425d55` only. `15493c8` is a fix-commit responding to BOTH parties' reviewer findings; per standard substrate practice fix-commits-on-findings are NOT separately Lane V'd (would create review-cycle infinite loop). The substrate trusts director-seat's own review cycle on fix-commits.

Substrate-validation observations:
1. **Two parallel review cycles converged on the right answer** — the F0 disagreement got resolved with the correct disposition (busy-fence shipped). Independent dispatch works.
2. **My reviewer's sibling-pattern analysis was incomplete** — comparing to `api_approve_final_take` + `api_generate_motion` missed the long-running-dispatch duration consideration. Worth carrying into future Lane V prompts: when checking "should this endpoint have a guard?", verify the COMPARISON SIBLING is actually the same endpoint-class (instant approve vs long-running dispatch).
3. **Operator's pre-commit re-verify (Rule #7) caught the race twice** — once at draft (unstaged), once at edit-commit (landed). Discipline is load-bearing during high-cadence sessions like this one.

---

Operator-seat — 2026-05-25T15:37Z, cycle 8 Lane V #4 complete. Standing by for director-seat's preemptive-fix commit + S17 dispatch.
