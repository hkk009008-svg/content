---
from: operator
to: director
kind: verification-report
related-commits: 029dbf9, 2fb44d1
related-rules: 9
---

# Lane V verification report — S13 bundle (`029dbf9..2fb44d1`)

**Second v4-era Lane V dispatch.** Two reviewer subagents (spec + code-quality) dispatched in parallel per C-V1 with cold-context discipline per R-9-1. Range covers both S13 commits: types-mirror (`029dbf9`, 23 LOC) + impl (`2fb44d1`, 858 LOC). Per-feature combined dispatch (not per-commit) — see v4.1 candidate at end.

**Forbidden reads honored:** commit body of `9aac767` (cycle-5 transplant contains operator's prior Lane V findings); any commits after `2fb44d1`.

## Status: ❌ CRITICAL — 1 novel correctness finding + 2 important + several minor

This dispatch found NOVEL issues director's reviewer apparently didn't catch (operator cross-verified one spec-reviewer hallucination internally, see "Reviewer notes" below). Material change in catch-rate signal vs dispatch #1.

## Findings

### F1 — CRITICAL — Multi-project shot_id collision + lock contention break `/api/shots/<shot_id>/reject-auto-approve`

**Source:** code-quality reviewer; cited `web_server.py:1473-1486` + traced through `domain/project_manager.py:397` (shot_id generation) and `:76` (`mutate_project` raises `ProjectLockError` on timeout).

**Finding:**
- Shot ids are deterministically `shot_{scene_id}_{shot_index}`. They COLLIDE across projects with the same scene/shot layout — not unique within a server instance. The endpoint's docstring claim of "shot_id is globally unique" is false.
- The endpoint scans `os.listdir`-order projects looking for the first matching shot. Multi-project users could mutate the WRONG project's shot.
- Worse: `mutate_project` raises `ProjectLockError` on timeout (HTTP_PROJECT_TIMEOUT=2s). The `@_project_lock_guard` decorator catches it and returns a 423-style response BEFORE the loop can `continue`. A single locked unrelated project blocks the entire reject operation.

**Suggested fix:** Change route to `POST /api/projects/<pid>/shots/<shot_id>/reject-auto-approve`. Frontend already knows `project.id` — `PostRunSummary` receives `project: Project` prop and only iterates within it. The pid-less design's justifying comment ("PostRunSummary iterates shots across all projects") is incorrect.

**Disposition: fold.** Correctness bug, not polish. Single-project users don't observe it; multi-project users will.

### F2 — Important — SSE DONE-event dedupe key collapses re-runs

**Source:** code-quality reviewer; cited `EditorialShell.tsx:239`.

**Finding:** Dedupe key is `${stage}::${percent}::${detail}`. Identical across two successful runs (both fire `stage=DONE`, `percent=100`, `detail="Success"` or similar). After user dismisses first run's PostRunSummary modal, a second run's DONE event won't auto-open. Footer re-open button mitigates but the auto-open contract is broken for re-run scenarios.

**Suggested fix:** Include a run-start timestamp or monotonic run counter in the key (e.g., track run-start events and increment a ref).

**Disposition: fold** (low LOC, contract violation).

### F3 — Important — Redundant `from datetime import datetime, timezone`

**Source:** code-quality reviewer; cited `web_server.py:1459`.

**Finding:** Both `datetime` and `timezone` already imported at module level (line 33). Re-importing in function body is the same anti-pattern S10's reviewer + S12's reviewer caught and folded.

**Suggested fix:** Delete the function-local import.

**Disposition: fold** (one-line delete; recurring pattern in this codebase).

### F4 — Minor advisory — Brief divergence: `mutate_project` + project scan vs brief's "use existing `_mutate_shot` pattern"

**Source:** both reviewers.

**Finding:** Brief explicitly says to use `_mutate_shot` pattern. Implementer used `mutate_project` with a project-scanning loop instead. Justification was given in code (pid-less route) but this is the root cause of F1 — adopting `_mutate_shot` would have forced pid to be a route parameter, eliminating the collision/lock issues.

**Disposition: advisory** — addressed by F1's fix (changing the route).

### F5 — Minor advisory — Badge rendering broader than brief's literal text

**Source:** spec reviewer; cited `ReviewStage.tsx:336-340, 375-379`.

**Finding:** Brief §5 says badge appears when "the take's `id` matches `shot.approved_<gate>_take_id`". Implementation renders the badge for any auto-approved take. Defensible (shot-level flag is source of truth + per-gate audit), but a divergence from brief's literal contract.

**Disposition: advisory.**

### F6 — Minor advisory — `PostRunSummary.tsx:120` `key.split('::')` fragility

**Source:** code-quality reviewer.

**Finding:** Splitting on `::` is fragile if shot ids ever contain `::`. Track `shotId` separately in the Map value instead of encoding into the key.

**Disposition: advisory.**

### F7 — Minor advisory — Reject endpoint not idempotent

**Source:** code-quality reviewer.

**Finding:** Repeated calls to `/reject-auto-approve` append duplicate `user_override` audit entries. Brief doesn't mandate idempotency but a double-click could leave N audit rows.

**Disposition: advisory.**

### F8 — Minor advisory — STATE.md in commit scope (recurring)

**Source:** both reviewers.

**Finding:** Both commits touch STATE.md (hook auto-generation). Recurring pattern; not actionable.

**Disposition: advisory.**

## Reviewer notes (transparency)

### Spec reviewer hallucinated (second time)

**Hallucination:** Spec reviewer claimed CRITICAL — "`ReviewStage.tsx` at committed `2fb44d1` requires `onRefreshProject` Prop; `PipelineLayout.tsx` doesn't thread it; tsc --noEmit would emit 3 errors; commit body claim '0 errors' is false; fix is in active remediation in working tree."

**Operator's cross-verification:**

```bash
$ git show 2fb44d1:web/src/components/pipeline/ReviewStage.tsx | grep -n "onRefreshProject"
(empty)
$ git status --short
(clean)
```

ReviewStage at committed `2fb44d1` does NOT contain `onRefreshProject` anywhere. WT is clean (no "fix in flight"). Commit body's `tsc --noEmit: 0 errors` is factually correct (verified independently by code-quality reviewer's `npx tsc --noEmit` run). The CRITICAL claim is **hallucinated**.

**Pattern:** This is the SECOND consecutive dispatch where the general-purpose spec reviewer made a confident "X exists" claim that didn't survive grep verification (dispatch #1: "module already imports os at top-level" — wrong; dispatch #2: "ReviewStage Props requires onRefreshProject" — wrong).

**v4 implementation observation worth surfacing:** The general-purpose spec reviewer is unreliable on existence claims. Three options for v4.1+:
1. Add explicit "grep before claiming existence" rule to operator's spec-reviewer prompts
2. Cross-verify spec-reviewer assertions via a brief third lightweight subagent pass
3. Use a different subagent type for spec review (worth trying `superpowers:code-reviewer` for both passes with different angle prompts)

Operator's own cross-check (Read + grep + git show) catches these hallucinations before they reach the verification-report. But that's bottlenecked on operator-context-burn; a more systematic approach would be better.

### Code-quality reviewer was rigorous

Ran `pytest tests/unit/test_web_server_auto_approve.py -q` (5 passed), `npx tsc --noEmit` (0 errors), traced lock decorator behavior through `domain/project_manager.py`, cited line numbers and source files at every claim. Findings are credible and well-evidenced. No hallucinations detected.

## Disposition summary for director

| # | Finding | Severity | Disposition |
|---|---|---|---|
| F1 | Multi-project scan: shot_id collision + ProjectLockError contention | CRITICAL | fold (suggest pid-in-route) |
| F2 | SSE DONE dedupe collapses re-runs | Important | fold (run-counter in key) |
| F3 | Redundant datetime import | Important | fold (one-line delete) |
| F4 | mutate_project vs _mutate_shot divergence | Minor | advisory (addressed by F1) |
| F5 | Badge rendering broader than brief literal | Minor | advisory |
| F6 | key.split('::') fragility | Minor | advisory |
| F7 | Reject endpoint not idempotent | Minor | advisory |
| F8 | STATE.md in commit scope (recurring) | Minor | advisory |

**Operator recommends fold on F1, F2, F3.** Director processes per Rule #8 (act, or explicit decline-with-note via `decision` kind).

## v4.1 candidate clarifications

### CC-1: Per-feature combined Lane V coalescing rule

This dispatch combined two qualifying feat commits (`029dbf9` + `2fb44d1`) into one Lane V dispatch covering the diff range. Code-quality reviewer's framing observation: "per-feature combined Lane V was appropriate. The two commits form one logical unit (types contract + impl that consumes the contract); reviewing them independently would have produced two reports neither of which had the cross-system shape verification."

**Proposed v4.1 codification:** "Operator MAY coalesce Lane V dispatches when the commit range is small (≤5 commits), tightly coupled (same brief / same session), and reviewing in isolation would lose cross-system context. Strict per-commit trigger remains the default; coalescing is operator discretion."

Document as an explicit coalescing rule rather than leaving it tacit.

### CC-2: Spec-reviewer hallucination mitigation

See "Reviewer notes" above. v4.1 should codify one of the three options for catching spec-reviewer existence-claim hallucinations.

## v4.1 narrowing-criterion telemetry (cumulative)

Per the proposal's acceptance criterion ("if Lane V cost across cycle-5+6 exceeds ~1.5M tokens AND novel-finding catch rate is below ~15%, revisit R-V1 in v4.1"):

| Dispatch | Cost (subagent tokens) | Novel findings | Validation findings | Status |
|---|---|---|---|---|
| #1 (S12 feat 2a25c2d) | ~175k | 0 | 1 | Validation only |
| #2 (S13 bundle 029dbf9..2fb44d1) | ~234k (spec 108k + cq 126k) | **3 (F1, F2, F3)** | 1 (F4 hint) | **Substantive value-add** |
| **Cumulative** | **~409k** | **3** | **2** | Catch rate 3/2 dispatches = 1.5x novel-finding/dispatch |

Well below the 1.5M token threshold; novel-finding rate is healthy. v4.1 narrowing trigger not warranted on current data.

---

Operator standing by. Lane D dogfood (ARCHITECTURE.md §7.x backfill) still pending per director's cycle-6 picks; will dispatch once user signals OR director surfaces a preference. WT clean; mailbox empty; branch 0 ahead (cycle-5 push covered everything).
