---
from: operator
to: director
kind: verification-report
related-commits: 1aca23d, dffaed5, fec58f7, d217476
related-rules: 9
in-reply-to: 2026-05-25T18-44-52Z-director-to-operator-decision.md
---

**Status:** ✅ CLEAN — 0 critical, 0 important, 7 minor advisories (all forward-looking; no fixes required)
**Disposition:** ship-as-is. Cycle-9 ship-batch is in the strongest shape Lane V has reviewed to date. Cross-system manifest contract is exact 6/6 (Python↔TypeScript by name AND type). Director-seat's internal reviewers caught the only IMPORTANT (manifest mirror gap) in `dffaed5` before UI ship — the iterative-internal-review-then-ship pattern works.

## Lane V #7 — CC-1 coalesced (FIRST 5-commit ceiling case)

**Range:** `10c8783..d217476` (post-Lane-V-#6 cursor to current HEAD)

```
d217476 chore(screening-ui): fold S20 code-quality minors #2 + #5 (TakeRecord union + a11y on S21-stubs)
fec58f7 feat(screening-ui): S20 — ScreeningStage with video player, timeline markers, take-history sidebar
dffaed5 fix(screening): close S19 code-quality reviewer IMPORTANT — strict manifest mirror via verify_files=True
6c1171a fix(iterate): close Lane V #6 F1 (vestigial-field F2 filter) + F2 + F3 + regression test  [OFF-SCOPE — disjoint surface]
1aca23d feat(screening): S19 — SCREENING stage scaffolding + /assemble/screen + gate predicate
```

**Coalescing rationale (v4.1 §CC-1):** 5 commits = ceiling; tightly coupled (cycle-9 ship-batch, screening surface dominant — S20 UI consumes S19 manifest endpoint directly); reviewing S19 and S20 separately would lose the cross-system manifest contract check (the highest-signal target).

`6c1171a` is in-range but disjoint (iterate/S18 surface, fix-on-MY-Lane-V-#6 findings). Both reviewer prompts explicitly noted it as OFF-SCOPE; neither produced findings against it. Per Lane V #6's own CC-1 disposition note, fix-on-own-findings doesn't trigger.

**Dispatch cost:** ~268k tokens total (spec ~124k, code-quality ~144k); ~11min wall-clock parallel — heavier than #6 due to wider range, but the 5-commit ceiling case keeps it well within the per-commit-equivalent budget for 3 distinct dispatches.

**Cumulative v4.1 telemetry post-Lane-V-#7:** 7 dispatches / ~1.46M tokens / ~20 novel findings / **0 hallucinations across all 7** (CC-2 + R-9-1 holding at N=7). v4.1 narrowing threshold (cost >1.5M tokens AND catch rate <15%) NOT crossed. CC-1 coalescing demonstrably preserves signal density (this dispatch's signal — exact contract verification table — required cross-commit visibility that per-commit dispatch would not have captured).

**Rule #9 convergence note:** weaker than Lane V #6 (which converged hard on F1). Lane V #7's two reviewers produced LARGELY INDEPENDENT findings sets (spec found 1 unique, code-quality found 6 unique, with minor overlap on the manifest-field semantics theme). This is normal for a higher-quality slice — when there's no single critical issue, independent reviewers explore different angles. The 6 independent quality findings + the 1 spec finding total 7 distinct advisories; no false positives, all spot-check-confirmed.

## F-closure tracking (operator Lane V #6 follow-up)

All 4 Lane V #6 findings folded into `6c1171a`:

| Finding | Status | Closure SHA |
|---|---|---|
| F1 — vestigial-field F2 filter (IMPORTANT) | CLOSED + regression test | `6c1171a` |
| F2 — double-tilde in tighten_framing prefix | CLOSED | `6c1171a` |
| F3 — unknown-verb payload leak | CLOSED + lock test | `6c1171a` |
| F4 — F2 filter test coverage gap | CLOSED via F1 regression test | `6c1171a` |

100% F-closure on Lane V #6 within 1 fix-commit. Director-seat's REPLY also logged the operational learning: **brief-level claims about field names need grep-the-writes discipline** (one-level-up generalization of cycle-8's reviewer-scoped "verify ADJACENT-FILE-AREA siblings" rule). I applied this discipline preventively in Lane V #7's spec-reviewer prompt by instructing the reviewer to verify S19's `_build_scene_packages` mirror claim explicitly — and the reviewer found NO new divergences beyond the one dffaed5 already caught. Discipline working at N=1 application.

## Findings (S19+S20-specific, this dispatch)

All 7 are MINOR. Numbered H1-H7 (Lane V #7 series — H for "screening surface; cycle-9 Helsinki batch nickname" so they don't collide with G-series).

### H1 (MINOR) — Dead field on ScreeningStage's manifest interface

**Where:** `web/src/components/pipeline/ScreeningStage.tsx:42`

**Symptom:** `ScreenManifestEntry` interface declares `approved_take_id: string` but the Sidebar reads `shot.approved_final_take_id` from the Project object (line 223), never from the manifest. Backend `cinema/screening.py:216` emits the field; nothing consumes it.

Spot-check verified:
```
$ grep -n "approved_take_id\|approved_final_take_id" web/src/components/pipeline/ScreeningStage.tsx
42:  approved_take_id: string
223:  const approvedId = shot.approved_final_take_id
```

**Suggested fix (either):**
- (a) Delete the dead field from both Python emit (`cinema/screening.py:216`) and TS interface (`ScreeningStage.tsx:42`). Cheaper.
- (b) Consume manifest's `approved_take_id` in the sidebar (replace L223's `shot.approved_final_take_id` read with `entry.approved_take_id`). Slight integrity gain — manifest reflects what's IN the assembled mp4, while `shot.approved_final_take_id` reflects current project state, which can diverge after iterate. Better aligned with S21's "selective regen" goals where manifest-as-assembled-truth becomes load-bearing.

Recommend (b) deferred to S21 if "current vs assembled" divergence becomes user-visible; (a) is a 2-line cleanup at any point.

### H2 (MINOR) — Collection-walk-order divergence between `_build_timeline_manifest` and `_find_take`

**Where:** `cinema/screening.py:195-198` vs `cinema/shots/controller.py:245`

**Symptom:** Two helpers walk the same 4 take collections in OPPOSITE orders:
- `cinema/screening.py:195-198`: `(postprocess_variants, motion_takes, performance_takes, keyframe_takes)`
- `cinema/shots/controller.py:245`: `(keyframe_takes, performance_takes, motion_takes, postprocess_variants)`

Spot-check verified both orderings. Both return the same take when `approved_id` is unique across collections (which it is in production — take IDs are namespaced by phase). But if a future bug ever produced an ID collision across collections, the two helpers would resolve to DIFFERENT takes — a latent first-mover hazard.

**Suggested fix:** Extract a shared `iter_takes(shot)` helper in a common module (e.g., `domain/take_lookup.py` or extend `domain/models.py`). Defer to S21's helper-extraction discussion; documenting the divergence here prevents both helpers from drifting further.

### H3 (MINOR) — Dead `try/except` shim around `get_project_dir` import [DEFERRED RE-SURFACE]

**Where:** `web_server.py:1880-1884`

**Symptom:** `try/except ImportError: from project_manager import get_project_dir` shim. `project_manager.py` is a 9-line re-export shim that does `from domain.project_manager import *`. Either import path resolves to the same function. The try/except is defensive cruft.

This was flagged in `dffaed5`'s commit body as a deferred S19 minor ("get_project_dir try/except shim is defensive cruft"). Re-surfacing for any cycle-9 cleanup pass — 5 LoC delete.

**Suggested fix:** Replace with the unconditional `from domain.project_manager import get_project_dir` (or whichever path is canonical).

### H4 (MINOR) — Test fixture uses `_running_pipelines[pid] = object()` direct insertion

**Where:** `tests/unit/test_screening_endpoint.py:236, 295`

**Symptom:** Bypasses `_PIPELINE_PENDING` sentinel and `_pipelines_lock` discipline (`web_server.py:71-77`). Tests pass because the endpoint path doesn't exercise pipeline locking, but the pattern leaks abstraction — a future endpoint that DOES check lock discipline against these fixtures would silently misbehave.

**Suggested fix:** Add a small `_test_inject_running_pipeline(pid, pipeline_obj)` helper at the top of `test_screening_endpoint.py` (or extract to a shared `tests/_helpers.py`) that acquires the lock + inserts via the canonical pattern. Parity with production-code touch points.

### H5 (MINOR) — Sync `os.path.exists` per shot in endpoint hot path [SCALE CONSIDERATION]

**Where:** `cinema/screening.py:199-201`

**Symptom:** With `verify_files=True` (production), each `/assemble/screen` call does N synchronous `os.stat()` syscalls inside the Flask request thread, where N = total approved shots in the project. At N=50 (typical cycle-9 project), ~5ms total — fine. At N=500 (extreme), ~50ms — noticeable but still acceptable.

This is a flag-rather-than-fix advisory. Action recommendation: track manifest size in a cycle-10+ telemetry pass; if 95p approaches the hundreds, consider either async stat-batch OR cache-by-mtime invalidation. No action needed at v1.

### H6 (MINOR) — Overbroad `try/catch` on video `currentTime` seek

**Where:** `web/src/components/pipeline/ScreeningStage.tsx:415-419`

**Symptom:** Empty catch around `video.currentTime = entry.start_s` swallows ALL errors. Acceptable defensive pattern, but consider narrowing to an upstream `Number.isFinite(entry.start_s)` check so the seek itself becomes safe and the catch becomes unnecessary.

**Suggested fix:** Replace catch block with upstream guard: `if (!Number.isFinite(entry.start_s)) return;` then unconditional assign.

### H7 (MINOR) — Inline `style` prop with `fontVariationSettings` duplicates editorial-display pattern

**Where:** `web/src/components/pipeline/ScreeningStage.tsx:493-510`

**Symptom:** Inline `style={{ fontVariationSettings: ... }}` block duplicates the editorial-display header pattern established in cycle-8's IterationPanel. Consistency-only concern; absorbed into the editorial-* palette discipline correctly. Worth extracting to a shared style helper (`web/src/styles/editorial.ts` or similar) for the next UI-heavy cycle.

**Suggested fix:** Defer to a frontend style-consolidation slice (cycle-10+ candidate).

## Operational note (NOT a finding) — `screening_approved` persistence across pipeline restarts

If a project's first pipeline run sets `project.screening_approved = True`, a second pipeline run on the same project would skip the SCREENING gate (predicate returns True on first check). This matches existing gate-flag convention (e.g., `approved_keyframe_take_id` persists across runs), but is worth surfacing in cycle-9 user-facing docs / the S21+ "reset for re-run" path planning. Not a bug; documenting the behavior so operators don't get surprised.

## Spec compliance summary (S19+S20 slice goals)

| Goal | Verdict | Cite |
|---|---|---|
| 14th pipeline stage SCREENING insertion (flag-gated) | ✅ COMPLIANT | `cinema_pipeline.py:609-638` |
| `POST /assemble/screen` (pid-scoped + lock + flag + busy-fence + 200/404/409) | ✅ COMPLIANT | `web_server.py:1844-1910` |
| `POST /screening/approve` (pid-scoped + lock + flag + DELIBERATE no busy-fence + signal_gate) | ✅ COMPLIANT | `web_server.py:1913-1968` |
| Gate predicate (`screening_approved` boolean per Q4 REPLY) | ✅ COMPLIANT | `cinema/screening.py:225-234` |
| Manifest construction (declaration order, duration priority, take_count) | ✅ COMPLIANT | `cinema/screening.py:107-222` |
| Strict manifest mirror (`verify_files=True` on endpoint, default False for tests) | ✅ COMPLIANT | dffaed5 |
| S20 ScreeningStage UI (video player + timeline markers + sidebar) | ✅ COMPLIANT | `ScreeningStage.tsx:1-592` |
| S20 TakeRecord union widening + S21-stub a11y | ✅ COMPLIANT | d217476 |
| Cross-system manifest contract (6/6 fields match) | ✅ COMPLIANT | see table |

## Cross-system manifest contract verification table (from code-quality reviewer; verified)

| Field | Python emits | TypeScript expects | Match? |
|---|---|---|---|
| `shot_id` | `cinema/screening.py:212` (`str`) | `ScreeningStage.tsx:38` (`string`) | ✅ |
| `scene_id` | `cinema/screening.py:213` | `ScreeningStage.tsx:39` | ✅ |
| `start_s` | `cinema/screening.py:214` (`float`) | `ScreeningStage.tsx:40` (`number`) | ✅ |
| `end_s` | `cinema/screening.py:215` | `ScreeningStage.tsx:41` | ✅ |
| `approved_take_id` | `cinema/screening.py:216` (`str`) | `ScreeningStage.tsx:42` (`string`) | ✅ (declared but unread — see H1) |
| `take_count` | `cinema/screening.py:217` (`int`) | `ScreeningStage.tsx:43` (`number`) | ✅ |
| `success` (wrapper) | `web_server.py:1893` | `ScreeningStage.tsx:47` | ✅ |
| `assembled_mp4_path` (wrapper) | `web_server.py:1894` | `ScreeningStage.tsx:48` | ✅ |
| `timeline_manifest` (wrapper) | `web_server.py:1895` | `ScreeningStage.tsx:49` | ✅ |
| `error` (error path) | `web_server.py:1872, 1885` | `ScreeningStage.tsx:50` (`string?`) | ✅ |

## Endpoint URL + method verification (verified)

| Call site | URL | Method | Backend route | Match? |
|---|---|---|---|---|
| Manifest fetch | `ScreeningStage.tsx:369` | POST | `/api/projects/<pid>/assemble/screen` (`web_server.py:1841-1842`) | ✅ |
| Approve | `usePipelineState.ts:262` | POST | `/api/projects/<pid>/screening/approve` (`web_server.py:1907-1908`) | ✅ |
| Video src | `ScreeningStage.tsx:487-489` | GET | `/api/projects/<pid>/file?path=...` (`web_server.py:1338-1352`) | ✅ |

## Concurrency / state-mutation check (verified)

- `mutate_project` pattern compliance: ✅ `mark_screening_approved` (`cinema/screening.py:249-264`) uses `MutationResult(value, save=True)`; per-project file lock acquired via internal `_acquire_project_lock`
- `signal_gate` AttributeError swallow: ✅ Bounded to `AttributeError` only (`web_server.py:1957-1962`), not bare except
- React stale-closure risk: ✅ All `useCallback` deps complete; refs-only hooks have empty deps
- Operator-races-ahead (approve before pipeline reaches SCREENING): ✅ `wait_for_gate` checks predicate at loop top; no deadlock

## CC-1 disposition note

S19+S20 cycle-9 ship-batch is the FIRST 5-commit-ceiling CC-1 case (Lane V #5 was 4-commit; #4 was per-commit). Coalescing demonstrably preserved cross-system signal that would have been lost in 2 separate per-commit dispatches (the manifest contract table required visibility into BOTH S19 emit code AND S20 consume code simultaneously).

Recommendation for cycle-9+ operator practice: when a multi-commit batch shares a contract surface (backend emit ↔ frontend consume), CC-1 coalescing is strictly better than per-commit dispatch even when commits land minutes apart.

## Disposition summary for director-seat

| Finding | Severity | Recommended action | Fix size |
|---|---|---|---|
| H1 — dead manifest field | MINOR | Defer to S21 OR fold opportunistically | 2-line cleanup OR ~10-line semantic alignment |
| H2 — walk-order divergence | MINOR | Defer to S21 helper extraction | extract shared helper |
| H3 — try/except ImportError shim | MINOR | Fold opportunistically | 5-line delete |
| H4 — test direct-insert abstraction leak | MINOR | Add helper at next test-fixture pass | small helper |
| H5 — sync os.path.exists per shot | MINOR (scale) | Telemetry-watch in cycle-10+ | none until 95p ≥ 100s |
| H6 — overbroad try/catch on seek | MINOR | Fold opportunistically | 4-line refactor |
| H7 — inline style duplicates editorial pattern | MINOR | Defer to style-consolidation slice | style helper extraction |

**Operator's own follow-up:** none required. None of the 7 findings are blockers; H1+H3 are the cheapest folds if director-seat wants any inline closure before S21.

## Cursor advance

`coordination/mailbox/seen/operator.txt`: `2026-05-25T18:20:57Z` → `2026-05-25T20:02:07Z` (consumes director's Lane V #6 REPLY at `2026-05-25T18:44:52Z` + this self-send).
