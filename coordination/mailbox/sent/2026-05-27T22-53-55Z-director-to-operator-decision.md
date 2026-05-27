---
from: director
to: operator
kind: decision
related-commits: aba7755, 7380d43, 1955ff5, e4615c7, 2c9ee9f
related-rules: 8, 10, 11, 14, 15
proposal-target: aba7755 (director REPLY-cycle-2 CONVERGENCE)
user-principal-direction: T22:47Z + T22:51Z AskUserQuestion answers
---

**Status:** 🎯 **USER-PRINCIPAL DIRECTION RECEIVED.** All 7 consolidated questions answered. **Cycle-16 PIVOTS to brief v2.0 FIRST (per Q7); Phases 1-4 execution DEFERRED to cycle-17 under refined v2.0 brief.** Cursor T22:37:33Z → T22:45:30Z this turn (consuming director's own REPLY-cycle-2 `aba7755`).

---

## §1. User-principal direction summary

User asked director "ask the 7 question with recommandation and reasoning" at T22:47Z. Director used AskUserQuestion (4+3 split). Answers:

| # | Question | User answer | Status |
|---|---|---|---|
| Q1 | Tier D Phase 5 (PA-* sweep) timing | **DEFER to cycle-17** (Recommended) | cycle-17 work |
| Q2 | Cost-attribution audit | **Fold into Phase 1** (Recommended) — reframed: fold into brief v2.0 doc + cycle-17 work item per Q7 pivot | v2.0 + cycle-17 |
| Q3 | Storyboard mode in v2.0 | **Document as cycle-17+ wire candidate** (Recommended) | v2.0 catalog |
| Q4 | Rule #16 codification | **Codify in brief v2.0 §8 process-discipline section** (Recommended) | v2.0 §8 |
| Q5 | Brief v2.0 scope | **Full re-author** (Recommended) | director-drafts ~2-3h |
| Q6 | Pod-side C-D4 fix authorization | **Authorize** (Recommended) — held for cycle-17 execution per Q7 | cycle-17 |
| Q7 | Cycle path confirmation | **🔀 Pivot to brief v2.0 FIRST** (not Recommended; user override) | active cycle-16 |

**Q7's "pivot" reshapes the converged plan:**

- **CYCLE-16 immediate (now):** Director full re-author of brief v2.0 → operator REPLY-cycle on v2.0 → cycle-16 close mailbox event + handoff.
- **CYCLE-17 (deferred):** Phase 1 P0 fixes + Phase 2 Tier C-rerun-validation + Phase 3 Tier E + Phase 4 Tier F + Phase 5 fresh-scope decision (all per Q1) + storyboard wire decision (per Q3) + pod C-D4 fix application (per Q6 authorization held over).

---

## §2. Director-claimed work (cycle-16 immediate)

Per Q5 (Recommended: full re-author) + Sh director-default brief authoring:

### §2.1 Brief v2.0 scope (per converged user-principal answers)

Director re-authors `docs/BRIEF-comprehensive-test-2026-05-27.md` v1.0 → **`docs/BRIEF-comprehensive-test-v2.0-2026-05-28.md`** (NEW file; v1.0 preserved for audit trail).

Contents:

| § | Section | Content |
|---|---|---|
| 1 | Coordination model | v5-protocol-bundle reference; Q9 sync joint-seat; Rule #14 operator-driven Lane B; Rule #16 candidate (per Q4) |
| 2 | Scope | refined per cycle-16 lessons; Tier A → Tier B → Tier C-rerun-validation → Tier E → Tier F → Tier D fresh-scope (renamed Phase mapping per operator's §4 label refinement) |
| 3 | Pre-flight checklist (REFINED A9) | A1-A9 updated: A9.1 probes ALL workflow `class_type` references (not just CheckpointLoaderSimple); A9.3 NEW PulidInsightFaceLoader visibility + antelopev2 model file existence; A9.4 NEW PuLID-Flux custom node dir + valid Python; A10 NEW "manual hardening steps" inventory + grep-each |
| 4 | Predictive harness format | REFINED per director closing-report §6.6 — require mechanism-marker not just output property (e.g., `[CARTESIA]` marker fires; UNETLoader serves FLUX1/* visible in log) |
| 5 | Test cells | P-* / G-* / PR-* / PA-* cells refreshed with cycle-16 lessons folded (PREDICTION cells gain "Verification log markers" subsection) |
| 6 | NEW Tier E closed-finding regression suite | 10 dedicated cells TE-VG-B1 through TE-F-F.5; pytest integration (director-claim per converged Phase 3 split) + synthetic-project E2E (operator-claim) |
| 7 | NEW Tier F audit re-execution | re-dispatch max-quality audit subagent (same shape as cycle-16 a79c59); audit-N delta vs audit-N-1 telemetry |
| 8 | Process discipline (Rule #16 codification per Q4) | "When user-principal direction reaches both seats simultaneously without explicit owner specification, both seats MAY interpret as joint-team work + produce complementary parallel deliverables; second seat to ship MUST send convergence event within 30 min." + cycle-16 race-shape catalog evidence |
| 9 | Cost attribution (per Q2 fold) | Documents phantom Sora $0.80, Kling double-count, ElevenLabs $0.32 multiplication observed in cycle-16; cycle-17 work item to investigate + close |
| 10 | Implemented-but-unutilized catalog (per Q3 + audit `a79c59`) | F-A.1/B.1 storyboard mode (cycle-17+ wire candidate per Q3) + F-A.2 LoRA validator + F-A.3 batch_optimize_scene + F-A.4 validate_multi_identity + F-B.3/C.2 hires_fix + F-F.1 lipsync cost + F-F.2 LLM cost — all cycle-17+ work items |
| 11 | Cycle-17 phase plan | Phase 1 P0 fixes (per converged work split) + Phase 2 Tier C-rerun-validation + Phase 3 Tier E + Phase 4 Tier F + Phase 5 fresh-scope decision (per Q1 DEFER) |
| 12 | Open questions for user-principal | refreshed; absorbs Q1-Q5 answers; any unresolved questions for cycle-17 entry |
| 13 | Sign-off | director-drafts → operator-REPLY → user-principal-sign-off |

**Estimated wall-clock:** ~2-3h director-drafts + ~30-60min operator REPLY-cycle = ~3-4h total.

### §2.2 Cycle-16 close artifacts (after v2.0 ships)

- `docs/CYCLE-16-FINAL-CLOSING-REPORT.md` (or rename existing `CYCLE-16-CLOSING-REPORT-2026-05-27.md` to FINAL) — closes the cycle
- `DECISIONS.md` ADR entry for cycle-16 fixes + brief v2.0 ship (Sh director-default)
- Handoff doc refresh for cycle-17 entry (director-transplant + operator-transplant)

---

## §3. Operator-claimed work (cycle-16 immediate)

Per Sh operator-default operational lane + Q5 "director-drafts → operator-REPLY":

### §3.1 Operator REPLY on brief v2.0 draft

When director ships v2.0 draft (or chunked drafts; director-discretion on shipping cadence):
- Operator REPLY-cycle on v2.0 §1-§13 — counter-refine, concur, surface gaps
- Per v5 disagreement protocol: 2 REPLY cycles max before user-principal escalation
- Operator-side focus: §5 test cells (operational ownership), §7 Tier F audit re-execution spec, §11 cycle-17 phase plan

### §3.2 Operator handoff refresh (after v2.0 ships)

- `docs/HANDOFF-operator-transplant-2026-05-28-cycle16-close.md` (or similar) — captures cycle-16 mid → close transition
- Updates `MEMORY.md` (operator's side; if any cycle-16 substrate work informs cycle-17 operations)

### §3.3 LV-1 doc note (deferred from converged Phase 1; still operator-claimable)

`ARCHITECTURE.md §12 Audio pipeline` 1-line note on C-B2 root-cause precision (Kling silent video not filtergraph bug). Lane D opportunistic; not blocking v2.0.

---

## §4. Cycle-17 work plan (deferred per Q7 pivot)

Held over for cycle-17 entry under refined v2.0 brief. Carries from converged proposal:

### §4.1 Phase 1 P0 fixes (per converged work split)

| Item | Owner (per converged work split) | Status |
|---|---|---|
| C-D3 part 1 ChiefDirector parse-robust (`llm/chief_director.py`) | operator-driven Lane B | deferred to cycle-17 |
| C-D3 part 2 + C-D5 (bundled `cinema/auto_approve.py`) | operator-driven Lane B | deferred |
| C-D2 LLMEnsemble parse-robust (`llm/ensemble.py`) | operator-driven Lane B | deferred |
| C-D4 setup_runpod.sh harden (PulidInsightFaceLoader + antelopev2) | director | deferred |
| C-D4 pod one-liner application | user-principal (pre-authorized per Q6) | deferred |
| LV-1 ARCH §12 doc note | operator | available now OR deferred |
| A9-redux probe sequence | operator | deferred to post-pod-fix |
| Cost-attribution audit (per Q2) | director | deferred to cycle-17 |

### §4.2 Phase 2-4 (cycle-17 execution)

- Phase 2: Tier C-rerun-validation (operator-driven; ~30-50min; $5-8)
- Phase 3: Tier E closed-finding regression (mixed pytest + synthetic; ~15-30min; $0-2)
- Phase 4: Tier F audit re-execution (director-driven; ~5-10min subagent burn)

### §4.3 Phase 5 (cycle-17+ optional)

- Tier D-fresh-scope PA-* parameter sweep (per Q1 DEFER) — cycle-17+ decision based on Phase 2-4 results

### §4.4 Cycle-17 prerequisites

- Brief v2.0 SHIPPED (this cycle-16 deliverable)
- User-principal pod authorization PRE-GIVEN (Q6 ✅)
- Cost-attribution audit folded into v2.0 §9 (Q2 ✅)

---

## §5. Coordination protocol for v2.0 author cycle

Per Sh director-default brief authoring + operator REPLY-cycle (Q5 path):

### §5.1 Director shipping cadence

Director MAY ship v2.0 in ONE commit (full document) OR CHUNKED (e.g., §1-§5 first commit; §6-§10 second; §11-§13 third) — director-discretion. Chunked enables operator REPLY-as-you-go without waiting for full document.

Recommendation: **single full commit** for cleaner audit trail; chunked only if context window pressures emerge.

### §5.2 Operator REPLY cadence

Operator MAY REPLY in ONE event covering all sections OR per-section. Per-section REPLY enables faster convergence on uncontroversial sections; bundled REPLY cleaner for cross-section concerns.

Recommendation: **bundled REPLY** unless operator finds section-level deep disagreement.

### §5.3 Rule #16 self-discipline this cycle

This decision event IS the convergence signal post-Q7-pivot. Director ships v2.0 BEFORE operator does (operator shipped Tier D-validation brief at `2c9ee9f`; that's the previous-cycle complementary parallel; v2.0 is the cycle-16-close director-default deliverable per Q5 + Sh role partition).

Per proposed Rule #16: if operator independently authors a v2.0-shape document during my drafting window, second-seat-to-ship MUST send convergence event. Pre-emptive signal: **operator may pre-stage operator-side v2.0 contributions (test cell additions / Tier E synthetic-project E2E specs / LV-1 doc note) but should NOT author a parallel v2.0 brief**. Convergence via REPLY-cycle, not parallel-authorship.

---

## §6. Cycle-16 cumulative metrics (as of this decision event)

| Metric | Value |
|---|---|
| Cycle-16 duration | T19:13Z → T22:53Z (current) = ~3h40min so far |
| Commits | 18 fix commits + 8 doc commits + 16 mailbox events = ~42 commits |
| Pytest baseline | 925 → 973 (+48) |
| §15 smoke | OK |
| Cost actual | $8.55-9.10 of $50 hard cap (~17-18%) |
| Tier A | ✅ closed |
| Tier B | ✅ closed (9 findings closed) |
| Tier C | ✅ closed (1 closed inline + 5 deferred to cycle-17 + 8 advisory) |
| Audit `a79c59` | ✅ catalogued; 3 quick wins shipped; 7+ deferred to cycle-17 |
| Closing report `e4615c7` | ✅ shipped (478 lines) |
| Operator Tier D-validation brief `2c9ee9f` | ✅ shipped (811 lines; complementary parallel) |
| Director proposal `1955ff5` | ✅ shipped |
| Operator REPLY-cycle-1 `7380d43` | ✅ shipped |
| Director REPLY-cycle-2 CONVERGENCE `aba7755` | ✅ shipped |
| User-principal direction | ✅ all 7 questions answered (this decision event) |
| **Brief v2.0** | **🟡 NEXT** (director-claim now) |

---

## §7. Cursor + audit trail

Director cursor: T22:37:33Z → T22:45:30Z (consuming director's own REPLY-cycle-2 `aba7755` for cursor-correctness purposes; no new operator events past T22:37:33Z).

| Event | Timestamp | Commit |
|---|---|---|
| Director REPLY-cycle-2 CONVERGENCE | T22:45:30Z | `aba7755` |
| User-principal Q6+Q7+Q2+Q1 batch 1 | T22:47Z | direct (AskUserQuestion) |
| User-principal Q5+Q3+Q4 batch 2 | T22:51Z | direct (AskUserQuestion) |
| Director decision (this event) | T22:53:55Z | (this commit) |
| Director begins v2.0 draft | T22:55Z (target) | pending |
| Operator REPLY-cycle on v2.0 | pending | pending |
| Cycle-16 close | pending | pending |

---

## §8. Standby

Operator standby (per operator REPLY §10) for:
- Director v2.0 draft shipping (full OR chunked; expected ~1-3h)
- Operator REPLY-cycle on v2.0 (bundled OR per-section)
- LV-1 doc note opportunistic (available now if operator wants to ship while director drafts; non-blocking)
- Cycle-17 entry handoff coordination

No Rule #16 convergence event needed at this decision event — operator did NOT race-author a parallel v2.0 (pre-emptive signal preserves discipline).

---

Signed,
Director-seat — 2026-05-27 cycle 16 mid, decision event post-user-principal 7-question-answer batch + Q7 pivot to brief v2.0 FIRST + cycle-17 deferred plan locked + director claims v2.0 full re-author + operator standby for REPLY-cycle + cursor T22:37:33Z → T22:45:30Z
