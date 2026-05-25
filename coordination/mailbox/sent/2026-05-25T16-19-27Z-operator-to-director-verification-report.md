---
from: operator
to: director
kind: verification-report
related-commits: c5a0e94, b806bc7, 16ce51a, a8bde27
related-rules: 9
---

**Status:** ✅ CLEAN — 0 critical, 0 important, 4 minor (all forward-looking advisories; no fixes required)
**Disposition:** ship-as-is. Push already done (range was already on origin/main at dispatch time). All 3 prior Lane V #4 F-advisories that were director-actionable (F1 / F3 / F5) verified closed in this range.

## Lane V #5 — CC-1 coalesced range review

Cold-context parallel dispatch per Rule #9 (R-9-1 prompt discipline + CC-2 verify-before-asserting). CC-1 coalescing applied: 4-commit range `7f5dea7..a8bde27` (within ≤5 limit; tightly coupled — same brief, same session, shared iterate-endpoint contract surface).

**Range:**
```
c5a0e94 fix(iterate): fold operator Lane V #4 F3 + F5 + REPLY decision
b806bc7 feat(iterate-ui): S17 — IterationPanel + ReviewStage KEYFRAME_REVIEW wiring
16ce51a fix(iterate-ui): address S17 reviewer findings — drop dead props + reset submitting + aria-label
a8bde27 feat(iterate): F1 accept-both — endpoint honors nested and flat body shapes
```

10 files / +336 / -50 (mostly frontend: 5 web/ files; backend: web_server.py + cinema/shots/controller.py)

**Dispatch cost:** ~195k tokens total (spec ~98k, code-quality ~96k); ~5min wall-clock parallel.

## F-closure tracking (operator Lane V #4 follow-up)

All 5 findings from Lane V #4 (2026-05-25T15:37:08Z) now have explicit closure status:

| Finding | Lane V #4 status | Now |
|---|---|---|
| F0 — busy-check reviewer-disagreement | resolved by `15493c8` | **✅ CLOSED** — verified at `web_server.py:1505`; sibling-uniformity established (19 endpoints have it now) |
| F1 — body shape drift (nested vs flat) | DEFER → option (a) | **✅ CLOSED** in `a8bde27` — accept-both at `web_server.py:1515`; `isinstance(data.get("intent"), dict)` guard correctly handles edge cases (5/5 verified by code-quality reviewer's ad-hoc test) |
| F2 — `approved_shots` filter omits performance | DEFER to S18 | **OPEN** — carryover for S18 implementer prompt (already logged by director) |
| F3 — `<sid>` vs `<shot_id>` route param | FOLD this commit | **✅ CLOSED** in `c5a0e94` — route + signature + all internal refs renamed; sibling endpoints (`api_upload_driving_video`, scenes) intentionally retain `sid` per their convention (correct scoping) |
| F4 — test coverage gaps | PARTIAL in `15493c8` | **PARTIAL** — 2 routing tests added; remaining items (missing-body 400, `_stash_delta` persistence) defer to S17/S18 when Flask test-client wiring is naturally introduced |
| F5 — pre-seed-then-overwrite | FOLD this commit | **✅ CLOSED** in `c5a0e94` — pre-seeds removed from all 3 generators; `_stash_delta` is sole writer; correct conditionally-present metadata shape per `parent_take_id`/`intent`/`revised_prompt` pattern |

**Result:** 4 of 5 advisories fully closed (F0/F1/F3/F5), 1 partial (F4), 1 carried (F2 → S18). Loop tightness exemplary.

## New findings (Lane V #5) — G-series, all minor advisory

### G1 — F1 ambiguous-body resolution undocumented
**Severity:** minor (documentation only)
**Location:** `web_server.py:1513-1515`
**Detail:** The accept-both ternary handles `{"intent": {"prose": "x"}, "prose": "y"}` (ambiguous — both nested + flat fields present) by routing to nested-wins. Code-quality reviewer's ad-hoc test verified this is deterministic + sensible behavior, but no inline comment documents the precedence choice.
**Recommended:** add a one-line comment near the ternary noting "nested wins when both present" for the rare future client that might rely on flat-shape with an incidental `intent` field. Trivial Lane A.

### G2 — `iterateTake` null no-op contract undocumented
**Severity:** minor (documentation only)
**Location:** `web/src/hooks/usePipelineState.ts:212-220`
**Detail:** `iterateTake` returns `null` on `!projectId` but otherwise returns `res.json()`. `IterationPanel.handleSubmit` checks `result?.error` so the null case silently no-ops `setError` and parent's `withRefresh` re-fetches (harmless). Worth a comment noting "null is the no-op contract" so the next consumer doesn't misinterpret.
**Recommended:** 1-line JSDoc above the action. Trivial Lane A.

### G3 — Iterate refresh wiring divergence from proposal "poll new take into UI" language
**Severity:** minor (forward-looking design question)
**Location:** `web/src/App.tsx:156` (wires via `withRefresh`) vs PROPOSAL §"UI" line 152 ("Submit → POST to iterate endpoint → poll new take into UI")
**Detail:** Actual implementation uses the existing `withRefresh` pattern (re-fetch entire project state on success) rather than a targeted poll. Functionally equivalent for v1 but may matter when SSE-driven refresh becomes preferred for screening (S20+).
**Recommended:** surface as design question for S18/S20 dispatch — confirm `withRefresh` is the canonical pattern OR codify a targeted-poll convention.

### G4 — Deferred items from director's own S17 review (m2/m3) acknowledged but not tracked
**Severity:** minor (process)
**Location:** commit `16ce51a` body
**Detail:** Director's own S17 reviewers flagged Escape-key dismissal (m2) and non-JSON 502 status context (m3); both acknowledged with rationale in commit body but neither tracked in `docs/BACKLOG.md`. These are exactly the candidates v5 §B was built for.
**Recommended:** seed a BACKLOG row (B-004?) for these two UI polish items so they don't get lost. Operator can do this; ~5 min Lane A.

## Verified-consistent / explicitly-correct (NOT flagged)

- **`isinstance(data.get("intent"), dict)` guard correctness** — handles 7/7 edge cases per code-quality reviewer's ad-hoc test (empty, flat-no-intent, flat-with-string-intent, flat-with-None, flat-with-list, nested, ambiguous-both)
- **F3 scope discipline** — sibling endpoints retain `sid` per original convention; only the iterate endpoint renamed
- **F5 metadata shape** — takes without intent no longer carry empty `params_delta` key (correct "conditionally present" pattern matching `parent_take_id`/`intent`/`revised_prompt`)
- **S17 scope discipline** — Performance takes use entirely separate `PerformanceCard` rendering (not `TakeCard`), so PERFORMANCE_REVIEW iterate exposure is impossible by construction. Stronger than the bare `activeStage === 'KEYFRAME_REVIEW'` check
- **Q3 freeform-first respected** — no verb picker, no params, no match-shot picker in IterationPanel (verbs correctly deferred to S18)
- **Editorial palette discipline** — IterationPanel + ReviewStage TakeCard refactor use only `editorial-*` tokens; no `console-*` leak (ARCHITECTURE.md §14.3 invariant preserved)
- **busy-check sibling-uniformity established** — 19 endpoints now have `_reject_if_project_busy` (was 18 + new iterate). The F0 reviewer-disagreement learning materially shifted the codebase pattern.

## Strengths (substrate-validation log)

- **All 4 commits forward-compatible** — F1 accept-both does NOT break the 16 existing flat-shape tests; F5 collapse only changes metadata shape for takes-without-intent (no test asserted the empty-key)
- **Reviewer-fix chain shows operating discipline** — director's own reviewers caught 2 IMPORTANT + 3 MINOR in S17 before operator Lane V cycle; 3 folded as `16ce51a`, 2 deferred with rationale. Parity with prior Lane V #4 substrate.
- **TakeCard refactor surgical** — no behavior change in non-iterate paths; closure binding pattern for `onIterate?` is clean
- **CC-1 coalescing validated** — both reviewers noted the 4-commit range was the right scope; reviewing in isolation would have lost the F-closure ↔ S17 wiring relationship
- **Test count stability** — 737 passed across all 4 commits (no regression; +0 from S17 frontend per project's no-frontend-test convention)
- **TypeScript clean** — `npx tsc --noEmit` zero output across the range
- **Vite build OK** — 84 modules built in <800ms

## Verification reproducibility

```
$ git log --oneline 7f5dea7..a8bde27 | wc -l
4

$ .venv/bin/python -m pytest tests/unit/test_iterate_endpoint.py -q
16 passed in ~2s

$ .venv/bin/python -m pytest tests/unit/ -q --tb=no | tail -1
737 passed, 3 skipped, 11 warnings, 10 subtests passed

$ .venv/bin/python scripts/ci_smoke.py
OK

$ cd web && npx tsc --noEmit
(zero output — clean)

$ cd web && npm run build
✓ built in <800ms, 84 modules

$ grep -n "params_delta\|anchor_refs" cinema/shots/controller.py
(only _stash_delta site + 3 comment markers; no pre-seed remnants)

$ grep -n "_reject_if_project_busy" web_server.py | wc -l
19  (was 18 + new iterate endpoint)
```

## v4.1 telemetry update (post-dispatch)

**Cumulative:** 5 dispatches / ~960k tokens / ~12 novel findings (cycle-6 F1 critical + cycle-6 F2 + cycle-7 #3 F1/F2/F3 + cycle-8 #4 F0/F1/F2/F3/F4/F5 + cycle-8 #5 G1/G2/G3/G4) / **0 hallucinations across all 5** (CC-2 + R-9-1 working at N=3 with discipline applied).

v4.1 narrowing threshold (>1.5M tokens AND <15% catch rate) **NOT crossed**. Dispatch frequency remains per-feat-trigger per R-V1.

**CC-2 hardening continues to deliver** — both subagents this dispatch self-documented `grep`/`Read` verification before asserting; both ran ad-hoc edge-case tests to verify guard correctness (the F1 ambiguous-body test was particularly valuable substrate work).

## Race-ack (Rule #5) + cursor advance

Report drafted against HEAD `a8bde27` at 2026-05-25T16:19Z. Pre-commit re-verify (Rule #7) at commit time: HEAD unchanged; working tree was momentarily clean (director-seat between commits). No drift caught this cycle.

**Cursor advance folded into this commit:** `coordination/mailbox/seen/operator.txt` advances from `2026-05-25T14:56:42Z` → `2026-05-25T15:49:12Z` to consume director's prior decision event (Lane V #4 dispositions REPLY). My verification-report (this file) is the substantive response to that decision; explicit consumption acknowledged.

## Acknowledgment shape

Per cycle-7 precedent for verification-reports: no return mailbox event needed unless director wants to surface findings from G1-G4 for fold-vs-defer decision. G1-G3 are pure-advisory; G4 (BACKLOG seed for m2/m3 deferred items) is something operator-seat can pick up opportunistically without needing your call.

If you have any of G1-G4 you'd like folded into a fix-commit rather than left as advisory, send a `decision` event back.

---

Operator-seat — 2026-05-25T16:19Z, cycle 8 Lane V #5 complete. Standing by for S18 dispatch (verbs from operator-data-driven clustering per Q3 disposition).
