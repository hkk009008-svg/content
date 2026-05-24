# Post-Roadmap Assessment — 2026-05-24

**From:** Director (this session, post-6-session reassessment)
**To:** Next director (incoming, future session)
**Source plan:** [docs/STRATEGIC_REVIEW-2026-05-24.md](STRATEGIC_REVIEW-2026-05-24.md)
**Roadmap manual:** [docs/HANDOFF-roadmap-2026-05-24.md](HANDOFF-roadmap-2026-05-24.md)
**Companion (operator-execution):** [docs/HANDOFF-operator-transplant-2026-05-24.md](HANDOFF-operator-transplant-2026-05-24.md)

> The 6-session roadmap is complete. This doc maps STRATEGIC_REVIEW
> P-priorities to shipped work and dispositions everything that
> remains, so the next director can start without a re-discovery
> phase. Read this first; then `git log --oneline -30` and run the
> §15 smoke per [CLAUDE.md](../CLAUDE.md) session-start protocol.

---

## TL;DR — top 3 for next director (in priority order)

1. **face_validator_gate test coverage** — three functions
   (`should_halt`, `score_candidate`, `needs_regenerate`) gate every
   shot's halt/regenerate/approve decision. Zero direct tests in
   `tests/unit/` today. STRATEGIC_REVIEW §P0-1 Pri 3 named this as the
   strongest follow-up after the 6 sessions. Effort: M (~22 cases).

2. **Pydantic schema validation on `project.json` (P1-3)** — the
   highest-leverage reliability change remaining. Raw-dict mutations
   currently silently break gate predicates when a key typo lands.
   Effort: L (2-3 sessions; touches every `domain/` caller).

3. **`Monitor.tsx` cascadeMetadata wiring (Session 6 deferred)** —
   `TakeStrip` accepts `cascadeMetadata` (b25da2e) but `Monitor.tsx:43`
   never populates it. The fallback badge renders in `ReviewStage`
   but NOT in the live-run console — exactly where the operator most
   needs the warning. Effort: S (~5 LOC if `ShotState.take_id`
   resolves cleanly against `keyframe_takes`/`motion_takes`/
   `performance_takes`).

---

## What shipped

6 sessions + Session 5/6 minors + the verification-discipline ADR.
Full commit ledger:

| Session | P-priority | Shipped via |
|---|---|---|
| 1 | P0-2 CI | `a94c50b`, `5d3a580`, `7c93cd6` |
| 2 | P0-1.1 ReviewController coverage | `cfbffb9`, `37c9350` (P0 bug fix inline), `2d58710` |
| 3 | P0-1.2 workflow_selector coverage | `4ea4414`, `8f1dee9` |
| 4 | P1-1a Structured logging | `6750292`, `656f0f2`, `4665a2d`, `c0b1ed0`, `6485f22` |
| 5 | P0-3 Cost-tracker + try/except sweep | `bdeeee5`, `ed01c09` |
| 6 | P1-4 + P2-3 Frontend + cascade visibility | `d516d2a`, `b25da2e`, `c6eaefb` |
| — | ADR-013 Verification discipline (Tier-1) | `ed33035` |

Plus `chore(baseline)` counter syncs + multiple `docs(handoff)`
commits during the two transplants (director: `eceb9a2`; operator:
`66659b0`, `24a1618`).

Baseline at HEAD (`c6eaefb`): **590 pytest pass / 3 skip / 0 fail**;
smoke OK; tsc clean. Whole-suite delta from the transplant baseline
(574) is +16 — Session 5's net additions. Sessions 2 (+26 from 10 to
36) and 3 (+70 from 34 to 104) shipped before the transplant
snapshot was taken and were already counted in the 574.

---

## STRATEGIC_REVIEW coverage matrix

| Item | Status | Disposition | Notes |
|---|---|---|---|
| P0-1.1 ReviewController coverage | SHIPPED | done | Session 2 + bonus P0 `_find_take` fix |
| P0-1.2 workflow_selector coverage | SHIPPED | done | Session 3; brief said 48 keywords, actual was 47 |
| P0-2 CI | SHIPPED | done | Session 1 + bonus `scripts/ci_smoke.py` single-source-of-truth extraction |
| P0-3 Cost-tracker + silent-except sweep | SHIPPED | done | Session 5; silent-except count was 2 (test cleanup, ACCEPTABLE) |
| P1-1 Observability (print → logger) | SHIPPED | done | Session 4; 36 prints in 2 files converted |
| P1-2 Pipeline orchestrator monolithic | OPEN | important-deferred | `cinema_pipeline.py` still ~1011 LOC; refactor liability, not bug |
| P1-3 Project JSON no schema validation | OPEN | **critical-pickup** | Top-3 for next director |
| P1-4 Frontend error boundaries | SHIPPED | done | Session 6 commit 1 |
| P1-5 Doc-claim verification tooling | OPEN | important-deferred | ADR-013 rules shipped; `scripts/lint_doc_claims.py` did NOT |
| P2-1 `competitive_generation=True` default | OPEN | important-deferred | One-line default flip + UI label; product call is the blocker |
| P2-2 RunPod pod idle billing | OPEN | low-priority | Manual stop already documented in OPERATIONS.md §10 |
| P2-3 Lipsync cascade silent fallthrough | SHIPPED | done | Session 6 commit 2 (cascade_metadata field) |
| P3-1 Concurrency hygiene | OPEN | important-deferred | Unaudited module-globals (`_running_pipelines`, `_progress_queues`) |
| P3-2 `_default_progress` in pipeline | PARTIAL | low-priority | Session 4 converted to `logger.debug` but method not deleted |
| P3-3 scene_decomposer duplicate validators | OPEN | low-priority | Single-pass audit, ~1 session tidy |
| P3-4 Root-level Python files unclear purpose | OPEN | low-priority | Grep-and-delete + 3 ARCHITECTURE.md entries |
| P4-1 Vendor sprawl | OPEN | low-priority | Product decision, not engineering |
| P4-2 Single-process architecture | NOT-DOING | drop | Explicit per STRATEGIC_REVIEW line 534 |
| P4-3 4-gate review fatigue | OPEN | important-deferred | Most operator-visible UX gap remaining |
| P4-4 No A/B testing | OPEN | low-priority | Needs operator volume data first |
| P4-5 Director's Console underdeveloped | PARTIAL | important-deferred | Session 6 added cascade badges to `ReviewStage`; Console still missing |

**Score:** 7 of 21 P-items shipped (P0-1.1, P0-1.2, P0-2, P0-3, P1-1, P1-4,
P2-3), 2 partial (P3-2, P4-5), 1 explicit not-doing (P4-2), 11 open.
All P0 items closed.

---

## Carry-forward & deferred items

| Item | Status | Disposition |
|---|---|---|
| `datetime.utcnow()` at `domain/project_manager.py:126,864` | OPEN (2 occurrences, verified) | low-priority — mechanical 2-line swap to `datetime.now(timezone.utc)` |
| `cost_tracker.record_api_call` coverage gap | **RESOLVED** by Session 5 (`bdeeee5`) | — |
| `face_validator_gate` × 3 functions uncovered | OPEN (zero hits in `tests/unit/`) | **critical-pickup** (see TL;DR) |
| `scene_decomposer` + `lip_sync` coverage gaps | OPEN | important-deferred — audit before scoping new test files |
| Session 6: `Monitor.tsx` wiring gap | OPEN | important-deferred (see TL;DR; ~5 LOC) |
| Session 6: ErrorBoundary per-shell palette | OPEN | low-priority — cosmetic (editorial-curtain inside console shell) |
| Session 6: ErrorBoundary `componentStack` telemetry | OPEN | low-priority — needs `POST /api/client-error` endpoint |

---

## Recommendation for next director

After this roadmap, the project's **architectural ambition is now matched
by its operational maturity at P0**. Three concrete pickup candidates
sit above the rest: (1) `face_validator_gate` tests, because the
halt/regenerate/approve fork is the load-bearing gate every shot hits
and currently has zero direct coverage; (2) Pydantic schema validation
on `project.json`, because gate-by-typo is the largest remaining
silent-failure surface; (3) Monitor.tsx cascade wiring, a 5-LOC quick
win that delivers Session 6's promised visibility in the place it most
matters (live runs, not post-hoc review).

Below those, **P4-3 (review fatigue / auto-approve path)** is the
highest-impact UX gap and the right next product conversation — the
data Session 5 now captures (`spent_usd` per-shot, `record_api_call`
traces) provides a basis for "auto-approve when confidence is high"
heuristics. **P3-1 (concurrency audit)**, **P1-2 (orchestrator
extraction)**, and **P2-1 (competitive_generation default)** are all
S-to-M effort and can be sequenced opportunistically into single
sessions when an operator has bandwidth.

**P4 except P4-3 is correctly deferred or not-doing.** Do not
re-litigate P4-2 (microservices) — STRATEGIC_REVIEW line 534 settled
it. P4-4 (A/B testing) becomes worth doing only after 6+ months of
operator volume data exists.

---

## Process notes

- The verification discipline (ADR-013 / Rules 1–3) held across all
  6 sessions. The one Rule-1 violation that slipped through
  (`656f0f2` commit body said "40 prints" when actual was 36) was
  caught by code-review and noted in `c6eaefb`'s deferred-minors
  list. Rule-1 enforcement should be the floor going forward.
- The **multi-agent operator pattern** (parallel director + operator
  Claude sessions, both transplanting via handoff at context-limit)
  shipped 18+ commits per active conversation. See
  [memory/project_operator_is_parallel_claude.md](../../.claude/projects/-Users-hyungkoookkim-Content/memory/project_operator_is_parallel_claude.md)
  for the orchestration pattern.
- **`docs/HANDOFF-operator-transplant-2026-05-24.md`** captures
  execution-discipline patterns (commit-shape rules, file-convention
  preservation, per-session orchestration loop) — read it for HOW;
  read THIS doc for WHAT.

---

*Verified at HEAD `c6eaefb` (2026-05-24): `pytest tests/unit/ -q | tail -1`
→ `590 passed, 3 skipped, 11 warnings, 10 subtests passed`;
`scripts/ci_smoke.py` → `OK`; `(cd web && npx tsc --noEmit)` → exit 0.*
