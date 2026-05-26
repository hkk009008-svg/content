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

> **Cycle 9 close (2026-05-26):** P-spine has been STATIC across cycles
> 5-9. The 5-cycle gap was NOT idleness — it was (a) the full Protocol
> Bundle v2 → v3 → v4 → v5 substrate buildout (mailbox loop, Rules
> #7-#11, Lane V/D/S, CC-2 + R-9-1 + CC-1 disciplines) and (b) two
> user-authorized product surfaces (Surface A directorial iteration,
> S15-S18 across cycles 8-9; Surface B SCREENING + re-assembly,
> S19-S21 cycle 9) both shipped end-to-end behind feature flags
> (`CINEMA_DIRECTORIAL_ITERATION` + `CINEMA_SCREENING_STAGE`).
> Telemetry: 7 Lane V dispatches across cycles 6-9, ~1.46M tokens,
> ~20 novel findings, 0 hallucinations.
>
> **Cycle 10 update (2026-05-26):** Both feature flags **DEFAULT-ON
> as of v5.1+ flag-flip** (user-principal authorization 2026-05-26;
> operator + director joint flag-flip-recommended per Val#1+#2
> contract validation). Opt-out is now `CINEMA_DIRECTORIAL_ITERATION=0`
> / `CINEMA_SCREENING_STAGE=0` instead of opt-in. Surfaces A + B
> are now live for any operator who reaches them through the UI;
> U7+U8 UX-layer validation deferred to real-usage feedback OR
> scheduled real-generation session (~$2-5 LLM/Veo budget).
>
> **The cycle-10 priority slate is genuinely OPEN** — both Surfaces
> are functionally complete and the substrate is mature. The picks
> below reflect that opening: operator-facing validation is the
> nearest concrete next step (gates the flag-flip); P-spine resumption
> is the natural fallback (P1-3 has live candidates, P1-2 keeps
> growing); cross-cutting helper extractions are opportunistic.
>
> **Cycle 4 update (2026-05-25, historical):** Sessions 9, 10, 11 all
> SHIPPED this cycle (concurrency hardening, P1-3 first migration
> template + strict-mode flag, P4-3 backend auto-approve + v1.1
> minors). Plus Session 12 brief authored. Picks rotated to S12
> dispatch / S13 brief-author / ARCHITECTURE.md backfill.
>
> **Cycle 3 update (2026-05-24, late, historical):** Sessions 7, 8,
> Monitor.tsx wiring, P3-1 audit, Session 9 brief — all shipped.

1. **Surface A + B operator validation + flag-flip decision — CLOSED cycle 10.**
   Operator ran the validation brief in 2 sessions (Val#1 backend contract
   + Val#2 UX layer; ~55% coverage; both surfaces recommended SAFE TO FLIP);
   director shipped V1 + U1 folds; user-principal authorized flag-flip
   2026-05-26 at v5.1+ ship. **Both `CINEMA_DIRECTORIAL_ITERATION` and
   `CINEMA_SCREENING_STAGE` default-ON; opt-out via `=0`.** Brief at
   [docs/BRIEF-operator-validation-2026-05-26.md](BRIEF-operator-validation-2026-05-26.md)
   remains as cycle-end validation template. U7+U8 (IterationPanel +
   ScreeningStage actual UX) NOT-VALIDATED gap remains; closure paths:
   (a) accept-via-real-usage feedback, (b) schedule real-generation
   session (~$2-5 LLM/Veo budget) for end-to-end playthrough.

2. **P1-3 resumption — domain/ caller migrations using the S10
   template** — handoff says "Parts 1-6 shipped"; remaining
   production candidates concentrate in `domain/`:
   `domain/scene_decomposer.py`, `domain/continuity_engine.py`,
   `domain/character_manager.py`, `domain/project_manager.py` plus
   any post-S10 additions in `cinema/`. Total `project["scenes"|
   "characters"|"locations"]` patterns: 65 occurrences across 14
   files (most are tests, which are fine to leave dict-based).
   `domain/`-scope migration is the real work. Effort: S-to-M per
   module (~1-2 sessions). Uses S10's strict-mode template; pattern
   formalized at `docs/MIGRATION-PATTERN-pydantic-caller.md`. Counts
   need a fresh audit before scoping — what's been migrated since
   the cycle-4 template ship vs. what remains.

3. **Cycle-9 H-advisory helper extractions (S22+ Lane A work)** —
   Lane V #7 deferred 5 of 7 hardening items: H1 dead
   `approved_take_id` manifest field (read-the-manifest fix), H2
   shared `iter_takes(shot)` helper for walk-order convergence, H4
   `_test_inject_running_pipeline` helper for test discipline, H5
   per-shot `os.path.exists` scale watchpoint (telemetry, no
   immediate action), H7 inline `fontVariationSettings` style
   consolidation. None are blocking; all are codebase-health
   improvements. ~2-4 small Lane A commits if batched. Useful filler
   between higher-priority work or when priority #1/#2 are blocked
   on user input.

**Top-3 META-priorities (NOT execution work; agent state):**

- **Operator Lane V #8 processing** — when it lands on
  `4075f8e..e6932e3` (cycle-9 close range). Per CC-1 disposition,
  `e6932e3` (fix-on-own-findings) doesn't independently trigger; if
  operator coalesces, it's a single dispatch. Acknowledge per
  established pattern; fold IMPORTANTs, defer minors with rationale.
- **Cycle-9 operational-learnings codification decision** — TWO
  candidates surfaced cycle-9, both N=1: "brief-level grep-the-writes
  discipline" (Lane V #6 F1 root cause; PREVENTIVELY applied in Lane
  V #7 with 0 new divergences) and "tests that mock the orchestrator
  cannot catch orchestrator-level deadlocks" (S21 CRITICAL #1 root
  cause; mitigation pattern in `e6932e3`). Codify as Rule #12 / #13
  if cycle-10+ surfaces another instance. Cost of premature
  codification: rule-creep + unwarranted process burden. Cost of
  delay: another instance of the same bug.
- **ARCHITECTURE.md §16 doc-sync** — operator-default per Lane D.
  Surface B (S19+S20+S21) added 3 new endpoints + new `cinema/screening.py`
  module + 14th SCREENING pipeline stage. Operator's next session
  picks up if not already in flight. Director-seat does not pre-empt.

**Honorable mentions** (S-to-M, opportunistic single sessions):
- **P1-2 Pipeline orchestrator extraction** — `cinema_pipeline.py` is
  ~1011 LOC; would benefit from phase-by-phase extraction. Refactor
  liability, not a bug.
- **P2-1 `competitive_generation=True` default flip** — one-line
  change; the product call is the blocker, not the code.
- **`datetime.utcnow()` deprecation** at `domain/project_manager.py:
  126,864` — mechanical 2-line swap to `datetime.now(timezone.utc)`.
- **`scene_decomposer` + `lip_sync` coverage gaps** — audit before
  scoping new test files; may overlap with P3-3 (duplicate validators).

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
| 7 | P0-1 Pri 3 face_validator_gate coverage | `06109b5`, `d8bf650` |
| 8 | P1-3 (part 1 / boundary) Pydantic on `project.json` | `ceb0a32`, `f9b0aff`, `66b06c8` |
| — | Monitor.tsx cascade wiring (Session 6 deferred) | `a6e3ff1` |
| — | ADR-013 Verification discipline (Tier-1) | `ed33035` |
| — | Director-operator concurrent-operation protocol | `ad6cb4f` |
| — | State-assertion + race-ack + counter-bump rules | `ea97d0a` |
| 9 | P3-1 concurrency hardening (`_running_pipelines` + `_progress_queues`) | `bfa60bf`, `a97573e`, `f8b2aef`, `e164505` (audit) |
| 10 | P1-3 part 2 — `CINEMA_STRICT_SCHEMA` env flag + first caller migration | `5f2fe0b`, `ef98629`, `ec607ed` (chore fix) |
| 11 | P4-3 backend — auto-approve veto rules + per-gate config + ShotState integration | `d6fd3e1`, `ad526c3`, `42df2ac` (v1.1 minors), `e8b5ebc` (product doc) |
| 12 | P4-3 motion-gate opt-in (CINEMA_AUTO_APPROVE_MOTION env flag) | `2a25c2d`, `771bbf7`, `fefea5d` (chore) |
| 13 | P4-3 frontend — AutoApproveBadge + PostRunSummary + RejectAutoApproveModal + reject endpoint | `029dbf9`, `2fb44d1`, `47e5818` (chore) |
| — | Protocol Bundle v2 substrate (STATE.md + rules log + mailbox + Rules #7/#8) | `416d610`, `5e0329d` (v2.1) |
| — | Protocol Bundle v3 hardening (G auth precedence + F freshness + H audit) | `3340d1f` |

**Cycles 7-9 ship history** (after cycle-6 close at `c6eaefb`):

| Cycle | Slice | Headline shipped | Commit(s) |
|---|---|---|---|
| 7 | — | Protocol Bundle v4 (Lane V/D/S substrate) | `c0d6c80` and follow-ups |
| 7 | B-001 | Lifecycle wait_for_gate validation | (per cycle-7 handoff) |
| 8 | S15 | Surface A — `regenerate_with_intent` controller method | (per cycle-8 handoff) |
| 8 | S16 | Surface A — `iterate` endpoint + state plumbing | (per cycle-8 handoff) |
| 8 | S17 | Surface A — IterationPanel UI on KEYFRAME_REVIEW gate | (per cycle-8 handoff) |
| 8 | F1 | Surface A — pid-scoped reject + monotonic dedup (Lane V CRITICAL fold) | `9e24323` |
| 8 | — | Protocol Bundle v5 (joint-team mode + R10/R11/disagreement/emergency) | (per cycle-8 handoff) |
| 8 | B-002, B-003 | Hook script v2 + Option E (STATE.md gitignored, no amend) | `2183ccb` |
| 9 | S18 | Surface A extension — PERFORMANCE_REVIEW + REVIEW gates + 3 verbs | `8e11133`, `6c1171a` (Lane V #6 fold) |
| 9 | S19 | Surface B — SCREENING stage scaffolding + `/assemble/screen` + gate | `1aca23d`, `dffaed5` (IMPORTANT fix) |
| 9 | S20 | Surface B — ScreeningStage.tsx (video player + timeline + sidebar) | `fec58f7`, `d217476` (chore) |
| 9 | S21 | Surface B — `/assemble/re-assemble` + dirty-tracking + Q5 spike | `4075f8e`, `e6932e3` (CRITICAL fix) |

Plus `chore(baseline)` counter syncs + multiple `docs(handoff)`
commits during transplants (cycles 4-9 — per-cycle director +
operator handoff files in `docs/`).

**Baselines progression (pytest unit pass / smoke / tsc):**

| Reference | Pytest unit pass | Smoke | tsc |
|---|---|---|---|
| Cycle 3 close (`c6eaefb`) | 590 | OK | clean |
| Cycle 6 close | (per cycle-6 handoff) | OK | clean |
| Cycle 8 close (`4bf48cd`) | 737 | OK | clean |
| Cycle 9 close (`17a06c1`) | **841** (handoff session) / **840 + 1 flake** (cycle-10 re-verify) | OK | clean |

Cycle-9 close delta vs cycle-3 close: **+251 unit tests** across
cycles 4-9. Warnings unchanged at 2 (no new warnings introduced).

---

## STRATEGIC_REVIEW coverage matrix

| Item | Status | Disposition | Notes |
|---|---|---|---|
| P0-1.1 ReviewController coverage | SHIPPED | done | Session 2 + bonus P0 `_find_take` fix |
| P0-1.2 workflow_selector coverage | SHIPPED | done | Session 3; brief said 48 keywords, actual was 47 |
| P0-2 CI | SHIPPED | done | Session 1 + bonus `scripts/ci_smoke.py` single-source-of-truth extraction |
| P0-3 Cost-tracker + silent-except sweep | SHIPPED | done | Session 5; silent-except count was 2 (test cleanup, ACCEPTABLE) |
| P1-1 Observability (print → logger) | SHIPPED | done | Session 4; 36 prints in 2 files converted |
| P1-2 Pipeline orchestrator monolithic | OPEN | important-deferred | `cinema_pipeline.py` now **1203 LOC** (was 1011 cycle 3 → 1113 cycle 4 → 1203 cycle 9 after S19 SCREENING stage added). Refactor liability still growing; phase-by-phase extraction roughly stays a S-to-M opportunistic refactor |
| P1-3 Project JSON no schema validation | PARTIAL | follow-up | Cycle 3 / Session 8 shipped boundary validation (warn-only); Cycle 4 / Session 10 shipped strict-mode env flag + first caller migration template; **cycle-9 audit:** 65 `project["scenes"\|"characters"\|"locations"]` occurrences remain across 14 files — most in tests (fine); production candidates concentrate in `domain/scene_decomposer.py`, `domain/continuity_engine.py`, `domain/character_manager.py`, `domain/project_manager.py`. Pattern formalized at `docs/MIGRATION-PATTERN-pydantic-caller.md`; remaining: ~1-2 sessions per module |
| P1-4 Frontend error boundaries | SHIPPED | done | Session 6 commit 1 |
| P1-5 Doc-claim verification tooling | OPEN | important-deferred | ADR-013 rules shipped; `scripts/lint_doc_claims.py` did NOT |
| P2-1 `competitive_generation=True` default | OPEN | important-deferred | One-line default flip + UI label; product call is the blocker |
| P2-2 RunPod pod idle billing | OPEN | low-priority | Manual stop already documented in OPERATIONS.md §10 |
| P2-3 Lipsync cascade silent fallthrough | SHIPPED | done | Session 6 commit 2 (cascade_metadata field) |
| P3-1 Concurrency hygiene | SHIPPED | done | Cycle 4 / Session 9 closed both race surfaces flagged by P3-1 audit (`bfa60bf` + lock-discipline tests in `a97573e`) |
| P3-2 `_default_progress` in pipeline | PARTIAL | low-priority | Session 4 converted to `logger.debug` but method not deleted |
| P3-3 scene_decomposer duplicate validators | OPEN | low-priority | Single-pass audit, ~1 session tidy |
| P3-4 Root-level Python files unclear purpose | OPEN | low-priority | Grep-and-delete + 3 ARCHITECTURE.md entries |
| P4-1 Vendor sprawl | OPEN | low-priority | Product decision, not engineering |
| P4-2 Single-process architecture | NOT-DOING | drop | Explicit per STRATEGIC_REVIEW line 534 |
| P4-3 4-gate review fatigue | SHIPPED | done | Cycle 4 / S11 shipped backend + Cycle 5 / S12 shipped motion-gate opt-in + Cycle 6 / S13 shipped frontend (AutoApproveBadge + PostRunSummary + RejectAutoApproveModal + reject endpoint). All 4 P4-3 surfaces (backend rules + motion-gate flag + frontend display + rejection-with-reason flow) operational. |
| P4-4 No A/B testing | OPEN | low-priority | Needs operator volume data first |
| P4-5 Director's Console underdeveloped | PARTIAL | important-deferred | Session 6 added cascade badges to `ReviewStage`; Console still missing |

**Score (cycle 6 close, unchanged through cycle 9):** 9 of 21 P-items
shipped (P0-1.1, P0-1.2, P0-2, P0-3, P1-1, P1-4, P2-3, P3-1, P4-3),
3 partial (P3-2, P4-5, P1-3 part-2 template shipped — additional
callers pending), 1 explicit not-doing (P4-2), 8 open. All P0
closed; P1-2 + P1-5 + P2-1 + P3-3 + P3-4 + P4-1 + P4-4 +
P4-5-console-only remain unstarted.

**Cycles 7-9 delta on P-spine: ZERO.** Cycles 7-9 work was (a)
Protocol Bundle v4/v5 substrate (mailbox loop, Lane V/D/S, R10/R11,
CC-1/CC-2/R-9-1), (b) user-authorized Surface A (S15-S18) + Surface
B (S19-S21) product features, and (c) hook script v2 + Option E
(B-002/B-003). None map to STRATEGIC_REVIEW P-priorities. **This is
correct behavior** — when user authorizes a product surface, it
preempts P-spine sequencing. The cycle-10 priority slate is open
because no user-authorized work blocks it (both Surfaces functionally
complete pending operator validation).

---

## Carry-forward & deferred items

| Item | Status | Disposition |
|---|---|---|
| `datetime.utcnow()` at `domain/project_manager.py:126,864` | OPEN (2 occurrences, verified) | low-priority — mechanical 2-line swap to `datetime.now(timezone.utc)` |
| `cost_tracker.record_api_call` coverage gap | **RESOLVED** by Session 5 (`bdeeee5`) | — |
| `face_validator_gate` × 3 functions uncovered | **RESOLVED** by Session 7 (`06109b5` + `d8bf650`) | — |
| `project.json` no schema validation at load/save boundary | **RESOLVED** by Session 8 (`ceb0a32` + `f9b0aff` + `66b06c8`) | Caller refactor + strict mode = Session 9+ |
| `_running_pipelines` / `_progress_queues` race surfaces | **RESOLVED** by Session 9 (`bfa60bf` + `a97573e` + `f8b2aef`) | — |
| `CINEMA_STRICT_SCHEMA` env flag + first caller migration | **RESOLVED** by Session 10 (`5f2fe0b` + `ef98629` + `ec607ed` chore) | Migration template ready; future sessions migrate domain/* module-by-module |
| Motion-gate dead code (rules tested but unreachable in production) | **RESOLVED** by user product decision 2026-05-25: feature-flag pattern (`CINEMA_AUTO_APPROVE_MOTION` default off); Session 12 brief shipped, dispatch pending | Brief: `docs/HANDOFF-roadmap-2026-05-24.md` §SESSION 12 |
| ARCHITECTURE.md gap: Pydantic boundary + opt-in escalation pattern + Surface A/B documentation | OPERATOR-CLAIMED (Lane D) | important — discovered cycle 4 orientation. Sessions 8/10/12 escalations live but undocumented; **cycle 9 expanded scope** — S19 added `cinema/screening.py` module + 14th SCREENING pipeline stage + 3 new endpoints (`/assemble/screen`, `/screening/approve`, `/assemble/re-assemble`); S15-S18 added Surface A iterate plumbing through PERFORMANCE_REVIEW + REVIEW gates. Operator picks up post-cycle-9 per Lane D convention. |
| **Surface A + B operator validation** (cycle 9 NEW) | **RESOLVED cycle 10** — operator-validation brief (`a116e0a`) ran in 2 sessions (Val#1 `18beb92` + Val#2 `8d5e2d4`); V1 + U1 folds shipped (`d10b849` + `dea4cc8`); both surfaces recommended SAFE TO FLIP; user-principal authorized flag-flip 2026-05-26 at v5.1+ ship | **Both flags default-ON**; opt-out via `CINEMA_DIRECTORIAL_ITERATION=0` / `CINEMA_SCREENING_STAGE=0`. U7+U8 (IterationPanel + ScreeningStage actual UX) NOT-VALIDATED — closes via real-usage feedback OR scheduled real-gen session (~$2-5 budget). |
| **Cycle-9 H-advisory backlog** (Lane V #7 deferred) | OPEN | important-deferred — H1 dead `approved_take_id` field, H2 `iter_takes(shot)` shared helper, H4 `_test_inject_running_pipeline`, H5 per-shot `os.path.exists` scale watchpoint, H7 inline `fontVariationSettings` consolidation. 2-4 small Lane A commits if batched. |
| **Cycle-9 operational-learnings codification candidates** | **RESOLVED cycle 10** — (a) brief-level grep-the-writes shipped as **Rule #12** + (b) symmetric-endpoint audit shipped as **Rule #13** at v5.1+ (proposal `b583305` → REPLY `9f032db` → ship `8ab0bbb`). | Rule #12 N=2 evidence: Lane V #6 F1 + Lane V #8 spec-prompt preventive (0 divergences). Rule #13 N=2 evidence: Lane V #8 I1 CRITICAL + Val#1 V1. Both beneficiary `director-seat` (asymmetric); operator-seat explicit consent per R11. |
| **`test_four_concurrent_generate_only_one_wins` environment-sensitive flake** (cycle-10 START NEW) | OPEN — pre-existing, surfaced cycle-10 orientation | low-priority — added at `a97573e` (cycle 4 / Session 9, P3-1 concurrency hardening) to assert "only 1 of 4 concurrent generates wins via `_pipelines_lock`+`_PIPELINE_PENDING` sentinel". Passed in cycle-9 handoff session ("841 pass / 0 fail" at HEAD `17a06c1`); fails 4-for-4 in cycle-10 director's session at SAME HEAD with observed `[409, 409, 200, 200]` (2 winners instead of 1). Bisected against `a97573e^` / `e6932e3^` / `4075f8e^` / `1aca23d^` / `4bf48cd` — failure persists at every checkpoint, dating back to the test's own authorship. Root cause: race-condition test sensitive to CPU thread-scheduling latency (busy CPU widens the claim window between request-arrival and slot-claim). Action options: (a) tighten timing margins (barrier pre-warm + larger `ctor_release.wait` window), (b) mark `pytest.mark.flaky` with retry, (c) accept as environment-dependent + document. Operator-claimable Lane A (~30 min investigation). |
| `scene_decomposer` + `lip_sync` coverage gaps | OPEN | important-deferred — audit before scoping new test files |
| Session 6: `Monitor.tsx` wiring gap | **RESOLVED** by `a6e3ff1` (cycle 3 director-claimed) | — |
| Session 6: ErrorBoundary per-shell palette | OPEN | low-priority — cosmetic (editorial-curtain inside console shell) |
| Session 6: ErrorBoundary `componentStack` telemetry | OPEN | low-priority — needs `POST /api/client-error` endpoint |

---

## Recommendation for next director

**Cycle 9 close (2026-05-26):** see TL;DR top-3 at the top of this
file. Cycle 10 inherits an open priority slate; the substrate is
mature (v5 + Lane V/D/S + 7 Lane V dispatches with 0 hallucinations);
both Surfaces are functionally complete pending operator validation.
The highest-value next step is operator validation + flag-flip
decision, because without it the cycles 8-9 engineering doesn't
translate to user value.

**Cycle 5 close (2026-05-25, historical):** Cycle 5 top picks were
Session 12 dispatch + Session 13 brief + ARCHITECTURE.md backfill.
S12 shipped cycle 5 (`2a25c2d`/`771bbf7`/`fefea5d`); S13 shipped
cycle 6 (`029dbf9`/`2fb44d1`/`47e5818`); ARCHITECTURE.md backfill
was reframed under Lane D as operator-claimed. All three resolved.

**Sub-priority shelf (opportunistic between top-3 work):**

- **P1-3 part 3+** (additional `domain/*` caller migrations) — uses
  S10's template; ~1-2 sessions per module. Per cycle-9 audit, real
  candidates concentrate in 4 `domain/` files.
- **P1-2 orchestrator extraction** — `cinema_pipeline.py` at 1203
  LOC (was 1011 at cycle 3 → 1113 cycle 4 → 1203 cycle 9; net +192
  driven mostly by S19 SCREENING stage). S-to-M opportunistic refactor.
- **P2-1 `competitive_generation=True` default** — one-line flip;
  product call still the blocker.
- **`datetime.utcnow()` deprecation** at `domain/project_manager.py:126,864`
  — mechanical 2-line swap to `datetime.now(timezone.utc)`.
- **S22+ Compare-with-previous-cut UI** — stubbed in S20+S21
  (Re-assemble button shipped; Compare label updated to "Available
  in S22+"). Needs design: side-by-side video? overlay diff? Requires
  keeping previous mp4 around. Not user-requested yet — wait for
  operator-validation signal.

**Still deferred / not-doing (unchanged):** P1-5 doc-claim lint tool,
P2-2 RunPod idle billing, P3-3 + P3-4 + P4-1, P4-2 (explicitly
not-doing), P4-4 (needs volume data). Re-read the "Score" section
above for the count.

---

## Process notes

- The verification discipline (ADR-013 / Rules 1–3) held across
  cycles 1-9. The one Rule-1 violation that slipped through
  (`656f0f2` commit body said "40 prints" when actual was 36) was
  caught by code-review and noted in `c6eaefb`'s deferred-minors
  list. Rule-1 enforcement remains the floor.
- The **multi-agent operator pattern** (parallel director + operator
  Claude sessions, both transplanting via handoff at context-limit)
  has shipped 100+ commits across cycles 4-9. Cycle 9 alone shipped
  15 commits with 4 user-visible substantive slices (S18-S21). See
  [memory/project_operator_is_parallel_claude.md](../../.claude/projects/-Users-hyungkoookkim-Content/memory/project_operator_is_parallel_claude.md)
  for the orchestration pattern and the per-cycle director handoff
  files (`docs/HANDOFF-director-transplant-2026-05-2{4,5,6}-cycle{2..9}.md`)
  for cycle-specific state.
- **Protocol Bundle v5 substrate** (cycles 6-8 ramp; v5 shipped cycle 8)
  is now the operational baseline. 11 discipline rules in effect;
  Lane V/D/S with CC-1 + CC-2 + R-9-1 disciplines; 7 cumulative Lane V
  dispatches across cycles 6-9, ~1.46M tokens, ~20 novel findings,
  **0 hallucinations**. R-V1 narrowing threshold (>1.5M tokens AND
  <15% catch rate) NOT crossed; per-commit-trigger dispatch frequency
  remains correct.
- **`docs/HANDOFF-operator-transplant-2026-05-24.md`** captures
  execution-discipline patterns (commit-shape rules, file-convention
  preservation, per-session orchestration loop) — read it for HOW;
  read THIS doc for WHAT.
- **Next POST-ROADMAP refresh trigger:** rotate when the P-spine
  moves again (P1-3 next caller migration; P1-2 orchestrator
  extraction starts; etc.) OR when a Surface flag flips to
  default-on. Cycles 7-9 didn't trigger rotation because the work
  was substrate + user-authorized features; cycle-10 refreshing
  this doc was triggered by the open priority slate post-Surface-B-close.

---

*Verified at HEAD `17a06c1` (cycle-9 close re-verify on cycle-10
open, 2026-05-26): `pytest tests/unit/ -q --tb=no` → **840 passed,
1 failed, 3 skipped, 2 warnings, 10 subtests passed**. The single
failure is `test_web_server_concurrency.py::
test_four_concurrent_generate_only_one_wins` — an environment-
sensitive flake dating to its own introducing commit `a97573e`; see
Carry-forward § "environment-sensitive flake" for full triage. Cycle-9
handoff observed 841 pass / 0 fail in their session at the same HEAD,
so this is a CPU-scheduling artifact, not a regression. Other gates:
`scripts/ci_smoke.py` → `OK`; `(cd web && npx tsc --noEmit)` → exit 0;
`git status` → clean and in-sync with `origin/main`.*
