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

> **Cycle 4 update (2026-05-25):** Sessions 9, 10, 11 all SHIPPED
> this cycle (concurrency hardening, P1-3 first migration template +
> strict-mode flag, P4-3 backend auto-approve + v1.1 minors). Plus
> Session 12 brief (motion-gate wiring backend) authored; the
> motion-gate product question was resolved as the feature-flag
> default-off pattern (mirrors S10's `CINEMA_STRICT_SCHEMA`). Picks
> rotate again — the remaining top-3 are mostly brief-ready (S12)
> or brief-blocked (S13 frontend), plus one architecture-docs gap.
>
> **Cycle 3 update (2026-05-24, late, historical):** Sessions 7, 8,
> Monitor.tsx wiring, P3-1 audit, Session 9 brief — all shipped.
> Recorded in the "What shipped" matrix below.

1. **Session 12 — motion-gate auto-approve as opt-in env flag
   (CINEMA_AUTO_APPROVE_MOTION)** — wires `cinema/auto_approve.py`'s
   already-built motion rule builders to production via opt-in env
   flag (default off). Helper `is_motion_gate_enabled()` + conditional
   `_gate_map["PERFORMANCE_REVIEW"] = "motion"` in
   `cinema/review/controller.py` + motion mutator branch + ADR-014 +
   ≥4 tests. Brief shipped at `docs/HANDOFF-roadmap-2026-05-24.md`
   §SESSION 12 (`3373ff0`/`4e70db7` pre-amend). Effort: S-to-M (~45-75
   min). **Ready to dispatch.** Lane B Sonnet.

2. **Session 13 — P4-3 frontend (AutoApproveBadge + PostRunSummary +
   rejection-with-reason)** — was originally scoped as Session 12 in
   cycle 3; renumbered to make room for the motion-gate backend
   wiring. Consumes Session 11's audit-log shape + Session 12's motion
   entries (when flag-on). Effort: M (~2 hr). **Brief not yet written.**
   Author after Session 12 closes — implementer needs S12's audit-log
   keys to display correctly.

3. **ARCHITECTURE.md backfill — Pydantic boundary + opt-in escalation
   pattern** — discovered during cycle 4 orientation: ARCHITECTURE.md
   §7 documents `project_manager.py` defaults but not (a) Session 8's
   `_validate_project` Pydantic boundary, (b) Session 10's
   `CINEMA_STRICT_SCHEMA` escalation, (c) Session 12's
   `CINEMA_AUTO_APPROVE_MOTION` escalation (when it lands). The
   escalation pattern is now a recognized convention — should be
   documented in the truth file. ~50 LOC. **OPERATOR-CLAIMED under
   Protocol Bundle v4 Lane D** (post-v4 ship; see
   `docs/REPLY-protocol-bundle-v4-director.md` §"Director's
   commitment alongside v4 ship" #1, and `docs/PROPOSAL-protocol-
   bundle-v4-2026-05-24.md` §"Dogfood claim — cycle-5 pick #3 as
   first Lane D invocation"). Operator picks this up as standalone
   `docs(arch-sync)` commit after v4 ships. If director ships
   cycle-5 first before operator claims, the dogfood shifts to the
   next subsystem-touching commit — no harm.

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
| P1-3 Project JSON no schema validation | PARTIAL | follow-up | Cycle 3 / Session 8 shipped boundary validation (warn-only); Cycle 4 / Session 10 shipped strict-mode env flag + first caller migration template; remaining: domain/* migrations module-by-module (Sessions 14+) |
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

**Score (cycle 6 close):** 9 of 21 P-items shipped (P0-1.1, P0-1.2, P0-2,
P0-3, P1-1, P1-4, P2-3, P3-1, **P4-3 NEW**), 3 partial (P3-2, P4-5,
P1-3 part-2 template shipped — additional callers pending), 1 explicit
not-doing (P4-2), 8 open. All P0 closed; only P1-2 + P1-5 + P2-1 +
P3-3 + P3-4 + P4-1 + P4-4 + P4-5-console-only remain unstarted.
Cycle-6 delta: +1 shipped (P4-3 promoted from PARTIAL via S13 frontend).

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
| ARCHITECTURE.md gap: Pydantic boundary + opt-in escalation pattern | OPERATOR-CLAIMED (Lane D) | important — discovered cycle 4 orientation; Sessions 8/10/12 escalations live but undocumented in truth file. Reframed under Protocol Bundle v4 Lane D as operator-claimed; operator commits as standalone `docs(arch-sync)` after v4 ships. |
| `scene_decomposer` + `lip_sync` coverage gaps | OPEN | important-deferred — audit before scoping new test files |
| Session 6: `Monitor.tsx` wiring gap | **RESOLVED** by `a6e3ff1` (cycle 3 director-claimed) | — |
| Session 6: ErrorBoundary per-shell palette | OPEN | low-priority — cosmetic (editorial-curtain inside console shell) |
| Session 6: ErrorBoundary `componentStack` telemetry | OPEN | low-priority — needs `POST /api/client-error` endpoint |

---

## Recommendation for next director

**Cycle 4 close (2026-05-25):** Sessions 9, 10, 11 all SHIPPED;
Session 12 brief authored. P3-1 fully closed; P1-3 has its first
migration template + strict-mode flag; P4-3 backend done with
auto-approve veto rules + ShotState integration + per-gate config.
The motion-gate product question was resolved (feature-flag pattern).
The remaining P4-3 work is the frontend (Session 13) + Session 12
implementer dispatch for motion-gate backend wiring.

Cycle 5 director's top picks:

1. **Session 12 implementer dispatch** (motion-gate backend) —
   brief-ready at `docs/HANDOFF-roadmap-2026-05-24.md` §SESSION 12.
   Lane B Sonnet, ~45-75 min. Closes the documented v1 carve-out via
   opt-in env flag (`CINEMA_AUTO_APPROVE_MOTION`). The escalation
   pattern is now formalized — second instance after S10's
   `CINEMA_STRICT_SCHEMA`.

2. **Session 13 brief (P4-3 frontend) + dispatch** — brief-blocked
   on Session 12 closing. Once S12 lands, author the frontend brief
   covering `AutoApproveBadge`, `PostRunSummary` modal, and
   rejection-with-reason modal. Consumes S11's audit-log shape +
   S12's motion entries. Effort: M (~2 hr). After S13 ships, P4-3
   converts from PARTIAL to fully SHIPPED.

3. **ARCHITECTURE.md backfill** — Lane A director docs work in main
   context. ~50 LOC §7.x subsection covering: Session 8's Pydantic
   boundary at `_validate_project`, the warn-only contract, the
   `CINEMA_STRICT_SCHEMA` + `CINEMA_AUTO_APPROVE_MOTION` opt-in
   escalation pattern as project convention, and the boundary
   between typed-attribute access (post-S10) and dict access
   (pre-migration sites). Land before or alongside Session 12 ship
   so motion-flag gets an architectural home.

Below those:

- **P1-3 part 3+** (additional `domain/*` caller migrations) — uses
  S10's template; ~1-2 sessions per module. Opportunistic, not urgent.
- **P1-2 orchestrator extraction** — `cinema_pipeline.py` still
  ~1113 LOC (up from 1011 at cycle 3; net +102 from S10/S11 changes).
  S-to-M opportunistic refactor.
- **P2-1 `competitive_generation=True` default** — one-line flip;
  product call still the blocker.

**Still deferred / not-doing (unchanged):** P1-5 doc-claim lint tool,
P2-2 RunPod idle billing, P3-3 + P3-4 + P4-1, P4-2 (explicitly
not-doing), P4-4 (needs volume data). Re-read the "Score" section
above for the count.

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

*Verified at HEAD `a6e3ff1` (2026-05-24, post-Monitor-wiring):
`pytest tests/unit/ -q | tail -1` → `629 passed, 3 skipped, 11 warnings,
10 subtests passed`; `scripts/ci_smoke.py` → `OK`; `(cd web && npx tsc
--noEmit)` → exit 0.*
