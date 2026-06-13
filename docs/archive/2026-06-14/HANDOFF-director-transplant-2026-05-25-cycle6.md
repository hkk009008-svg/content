# Director-Seat Transplant Handoff — 2026-05-25 (cycle 6)

**From:** Director-seat (outgoing this session — natural cycle-close after v5 ship + S13 P4-3 frontend + first Lane D dogfood + 2 Lane V dispatches)
**To:** Director-seat (incoming, next session) — same seat, fresh context
**Companion (operator-seat-side):** [docs/HANDOFF-operator-transplant-2026-05-24.md](HANDOFF-operator-transplant-2026-05-24.md) (operator-seat refreshes their own)
**Predecessor (cycle 5):** [docs/HANDOFF-director-transplant-2026-05-25-cycle5.md](HANDOFF-director-transplant-2026-05-25-cycle5.md) — read for the cycle-5 pickup; this doc carries what's NEW since cycle 5 closed at `9aac767`
**Post-roadmap reassessment:** [docs/POST-ROADMAP-2026-05-24.md](POST-ROADMAP-2026-05-24.md) (last refreshed at `d4b398b` for cycle-6 P4-3 SHIPPED milestone)
**Purpose:** Self-contained pickup point. Cold-readable.

> **For cycle 7 (under v5 "two seats of one team" framing):** read `STATE.md`
> FIRST per cold-start step 0a (Protocol Bundle v3 §F freshness check). **All
> 11 discipline rules are active** — Rule #10 (Joint-team mode) and Rule #11
> (Codification bias check) shipped this cycle with v5. If `STATE.md`'s
> `unread mailbox` field shows N ≥ 1 events for director-seat, surface to
> user per Rule #8 BEFORE processing. Operator-seat may now also send
> `memory-candidate` events (v5 §M) — handle via existing memory-write
> workflow.

---

## TL;DR — 60 seconds

**Cycle 6 is the densest cycle in project history.** 12 commits (all pushed):

- **P4-3 fully SHIPPED.** Session 13 P4-3 frontend (`029dbf9` types + `2fb44d1` impl + `f7d7a19` chore) closed the multi-cycle deliverable that S11 (backend) + S12 (motion-gate opt-in) started. AutoApproveBadge + PostRunSummary modal + RejectAutoApproveModal + reject endpoint operational. P-priority score advanced 8→9.
- **Operator-seat's first Lane D dogfood** (`1e29610`) — ARCHITECTURE.md §7.7 Pydantic boundary + opt-in escalation pattern backfill (~89 LOC, operator-direct, ~0 subagent cost). v4 Lane D dogfood-pending → COMPLETE.
- **Operator-seat's 2 Lane V dispatches** — dispatch #1 (cycle 5, S12 commits) was validation-only; dispatch #2 (this cycle, S13 commits `029dbf9..2fb44d1`) caught **F1 CRITICAL** — multi-project shot_id collision in `/api/shots/<shot_id>/reject-auto-approve`. Director-seat shipped fix at `9e24323` (pid-scoped route + new endpoint test for project-not-found path).
- **P1-3 part 3 shipped** (`e1b72ca`) — second canonical migration applying S10's template to `api_decompose_scene`. Template re-use validated across two endpoints; future P1-3 migrations are mechanical.
- **Protocol Bundle v4.1 SHIPPED** (`509db7c`) — codified CC-1 (Lane V coalescing rule) + CC-2 (spec-reviewer hallucination mitigation via prompt-construction discipline). v4.1 telemetry-driven from operator's Lane V dispatch data.
- **Protocol Bundle v5 SHIPPED** (`d66690f`) — **the largest protocol-substrate evolution to date.** Philosophical reframe (P1 "two seats of one team") + Rule #10 (Joint-team mode) + Rule #11 (Codification bias check) + Disagreement protocol (D, 2-cycle limit + R-V1-style resolution paths) + Emergency handling protocol (E, 4-criteria definition + cross-seat-temporary-authority) + NEW `docs/BACKLOG.md` (shared-visible workspace) + NEW `docs/INCIDENT-LOG.md` (post-incident review log) + `memory-candidate` mailbox kind (M) + Lane S activation (S) + Sh codification (implementer dispatch as Strategic-seat-default).
- v5 negotiation cycle was the **CLEANEST cycle to date** (0 counter-refinements, 1 round: proposal → REPLY → revise → ship).
- **Baseline at this handoff:** `pytest tests/unit/` → **711 pass / 3 skip / 0 fail** (was 703 at cycle-5 close: +8 from S13's 5 + P1-3 part 3's 2 + F1 fix's 1). Smoke OK. STATE.md fresh modulo documented stale-by-one.

---

## Where we are — commit ledger (cycle-6 session)

12 commits since cycle-5 close at `9aac767`. All pushed to `origin/main`.

```
d66690f feat(protocol): ship Protocol Bundle v5 (two-seat team model + Rules #10/#11 + D/E/B/M/S/Sh)  # mine
8a4148a docs(proposal): revise Protocol Bundle v5 per director REPLY 642250d                          # operator
642250d docs(reply): director response to operator's Protocol Bundle v5 proposal                       # mine
2e06fe1 docs(proposal): draft Protocol Bundle v5 — director-operator as one team                       # operator
509db7c chore(protocol): Protocol Bundle v4.1 — Lane V coalescing rule + spec-reviewer hallucination mitigation  # mine
9e24323 fix(web): address S13 Lane V F1 (CRITICAL) + F2 — pid-scoped reject route + monotonic-run dedup  # mine
e1b72ca feat(schema): P1-3 part 3 — migrate api_decompose_scene to Project.model_validate              # mine
1e29610 docs(arch-sync): backfill §7.7 Pydantic boundary + opt-in escalation pattern                   # operator (first Lane D dogfood)
d4b398b docs(roadmap): rotate POST-ROADMAP for cycle-6 close — P4-3 SHIPPED                            # mine
f7d7a19 chore(web): address Session 13 code-review findings                                            # mine
2fb44d1 feat(web): AutoApproveBadge + PostRunSummary + RejectAutoApproveModal + reject endpoint        # S13 implementer (mine; via subagent)
029dbf9 feat(types): mirror S11+S12 auto-approve fields in TypeScript                                  # S13 implementer (mine; via subagent)
```

**Total: 12 commits** (8 director-seat + 3 operator-seat + S13 implementer's 2 attributed to director-seat dispatch). Cycle-6 close handoff will be commit #13.

---

## What's in flight (open at handoff time)

| Item | Owner (v5 framing) | What needs to happen |
|---|---|---|
| **Post-v5 reindex counter bumps** | Either seat (Rule #6) | AGENTS.md + CLAUDE.md counter deltas from post-v5-ship reindex (4234 symbols / 23439 relationships). Held in WT; fold into next natural commit. |
| **Cycle-7 director queue** | **Director-seat (cycle 7)** | See "What I would do next" section below. |
| **Operator-seat's Lane D continuation** | **Operator-seat** | Lane D continues to fire on subsystem-touching director commits per v4 spec. No specific item queued. |
| **Lane S first invocation opportunities** | **Director-seat (cycle 7)** | v5 activated Lane S (was scaffolded in v4). Cycle-7 director can opt-in to `scout-request` for the first time before any Lane B dispatch. |
| **`memory-candidate` first event opportunity** | **Operator-seat** | v5 added the mailbox kind (M). Operator-seat surfaces memory-worthy observations at their discretion. |
| **BACKLOG.md first row** | Either seat | v5 created `docs/BACKLOG.md` (empty template at ship). First row to be added by either seat as opportunities surface. |
| **Operator-transplant handoff refresh** | **Operator-seat** | They refresh their own; director-seat shouldn't touch. |

---

## State changes since cycle 5 (what's NEW since `9aac767`)

### Code + tests (S13 + P1-3 part 3 + F1+F2 fixes)

| Change | File(s) | Commit |
|---|---|---|
| TypeScript type sync (AutoApproveAuditEntry + 5 optional Shot fields) | `web/src/types/project.ts` | `029dbf9` |
| 3 new React components (AutoApproveBadge + PostRunSummary + RejectAutoApproveModal) + reject endpoint + ReviewStage/EditorialShell wire-ins + 5 endpoint tests | `web/src/components/console/AutoApproveBadge.tsx` (NEW), `PostRunSummary.tsx` (NEW), `RejectAutoApproveModal.tsx` (NEW), `web/src/components/pipeline/ReviewStage.tsx`, `web/src/components/EditorialShell.tsx`, `web_server.py`, `tests/unit/test_web_server_auto_approve.py` (NEW, 5 tests) | `2fb44d1` |
| S13 code-review chore (top-level Project import, refresh on rejection, etc.) | `web_server.py`, `web/src/App.tsx`, `web/src/components/EditorialShell.tsx`, `web/src/components/pipeline/PipelineLayout.tsx`, `web/src/components/pipeline/ReviewStage.tsx` | `f7d7a19` |
| P1-3 part 3 migration (api_decompose_scene + 2 new tests) | `web_server.py`, `tests/unit/test_project_models.py` | `e1b72ca` |
| F1 CRITICAL + F2 Important fixes (pid-scoped reject route + monotonic-run dedup) | `web_server.py`, `web/src/components/EditorialShell.tsx`, `web/src/components/console/RejectAutoApproveModal.tsx`, `web/src/components/console/PostRunSummary.tsx`, `web/src/components/pipeline/ReviewStage.tsx`, `tests/unit/test_web_server_auto_approve.py` | `9e24323` |

Test count progression: cycle-5 close 703 → S13 +5 (endpoint) = 708 → P1-3 part 3 +2 (location lookup regression) = 710 → F1 fix +1 (project-not-found path) = **711** (verified `pytest tests/unit/ --tb=no -q | tail -1`).

### Docs + protocol (POST-ROADMAP + ARCHITECTURE backfill + v4.1 + v5)

| Change | File(s) | Commit |
|---|---|---|
| POST-ROADMAP rotation: P4-3 PARTIAL → SHIPPED | `docs/POST-ROADMAP-2026-05-24.md`, `AGENTS.md`, `CLAUDE.md` (counter bumps folded) | `d4b398b` |
| **First v4-era Lane D dogfood** — ARCHITECTURE.md §7.7 Pydantic boundary + opt-in escalation pattern backfill | `ARCHITECTURE.md` (+~89 LOC) | `1e29610` |
| **Protocol Bundle v4.1** (CC-1 Lane V coalescing + CC-2 spec-reviewer hallucination mitigation) | `CLAUDE.md`, `AGENTS.md`, `docs/PROTOCOL-RULES-LOG.md`, `docs/PROPOSAL-protocol-bundle-v4-2026-05-24.md` (footer) | `509db7c` |
| **Protocol Bundle v5** — philosophical reframe + Rules #10/#11 + D/E/B/M/S/Sh | `CLAUDE.md`, `AGENTS.md`, `docs/PROTOCOL-RULES-LOG.md` (Rules #10/#11 + Beneficiary distribution snapshot), `coordination/README.md` (memory-candidate mailbox kind), `docs/BACKLOG.md` (NEW), `docs/INCIDENT-LOG.md` (NEW), `docs/PROPOSAL-protocol-bundle-v5-2026-05-25.md` (footer) | `d66690f` |

### Coordination + mailbox

| Change | File(s) | Commit |
|---|---|---|
| Archived operator's S12 Lane V verification-report (first dispatch — validation finding) | `coordination/mailbox/archive/2026-05-24T16-54-04Z-...verification-report.md` | (cycle 5 close `9aac767`) |
| Archived operator's S13 Lane V verification-report (second dispatch — CRITICAL finding F1 + F2 + advisories) | `coordination/mailbox/archive/2026-05-24T17-24-52Z-...verification-report.md` | `e1b72ca` |
| Archived operator's Lane D doc-sync-notice (ARCHITECTURE §7.7 backfill announcement) | `coordination/mailbox/archive/2026-05-24T17-31-26Z-...doc-sync-notice.md` | `e1b72ca` |
| Director's `seen/director.txt` cursor advanced to `2026-05-24T17:31:26Z` | `coordination/mailbox/seen/director.txt` | `e1b72ca` |
| NEW mailbox enum kind: `memory-candidate` (v5) | `coordination/README.md` | `d66690f` |

### Memory + index

- Memory file `director_transplant_handoff.md` updated in this handoff commit to point at cycle-6 doc.
- `MEMORY.md` index entry updated similarly.
- GitNexus index reindexed 4× this cycle (post-each-substantive-commit). Counter bumps folded per Rule #6 in director-seat commits; zero standalone `chore(baseline)` from director-seat. Operator-seat shipped one chore-baseline equivalent (`c487171` post-v4-proposal-reindex, pre-cycle-6).

---

## What I would do next, if I had the context

**Top 3 priorities for cycle 7 (in order):**

1. **Implementer prompt template upgrade** — Lane A in main context (director-seat docs work). Cycle-5 + cycle-6 surfaced 3 lessons worth carrying forward in the implementer prompt template:
   - **(SHA discipline, cycle 5)** "Capture commit SHAs from `git log --oneline -3` AFTER hook activity settles" — already deployed in cycle-5 S12 + cycle-6 S13 prompts; codify in the template so future dispatches inherit it.
   - **(Brief-pattern-deviation, cycle 6)** "When deviating from a brief-specified pattern, implementer MUST escalate the deviation reason and let director-seat (or operator-seat's Lane V) accept it explicitly. Silent substitutions cascade — S13 implementer silently substituted `mutate_project + project-scan` for the brief's `_mutate_shot` pattern, causing F1 CRITICAL." Add to "Project conventions you MUST follow" section.
   - **(pid-scope-check on new routes, cycle 6)** "When wiring a new endpoint into a route shape, verify the pid scope by checking similar existing endpoints in the same file." Lightweight check; would have caught F1 at design time.

2. **Opportunistic P1-3 part 4** — apply S10 migration template to a third caller. S10's template is now proven across `api_generate_dialogue` + `api_decompose_scene` (cycle 4 + cycle 6 sibling endpoints). Candidates remain: `web_server.py:1507/1546/1614/1646` (scene iteration loops), `cinema/review/controller.py:536` (target_api read), `cinema/shots/controller.py:1303` (scene lookup). Pick one; ~30-45 min Lane A in main context.

3. **v5 dogfood opportunities** — Lane S `scout-request` opt-in trial (try before any cycle-7 Lane B dispatch); `memory-candidate` first event (operator-seat surfaces; director-seat writes or declines); BACKLOG.md first row entry; (optional) emergency drill to test §E if no organic emergency occurs naturally.

**Other cycle-7 considerations:**

- **Cycle-6 protocol-substrate evolution is at maturity.** v5 reached "specialization-without-hierarchy" framing. Future bundles likely smaller (v5.1 refinements as data accumulates, not v6 reframes). Don't optimize for protocol-substrate churn; optimize for substrate USE.
- **Operator-seat's Lane V is now well-calibrated** — 2 dispatches, 1 validation + 1 novel CRITICAL catch, ~409k cumulative tokens. Within v4.1 narrowing-criterion budget (~1.5M target). Continue per-feat trigger; revisit only if cost runs hot or catch rate collapses.
- **P-priority queue is opportunistic.** No critical-path items remaining. P1-2 (orchestrator extraction) is gradually-mounting (cinema_pipeline.py ~1113 LOC); could be queued for cycle-7+ if scope-creep tolerance fits.

---

## Important context the next director-seat needs

### Discipline rules in effect (all 11)

- **Rules #1-#3**: codified `ad6cb4f` (cycle 3); reframed under v5's two-seat model but lane assignments unchanged
- **Rules #4-#6**: codified `ea97d0a` (cycle 3); team disciplines (apply to both seats per Rule #10)
- **Rule #7**: codified `416d610` (cycle 3, Protocol Bundle v2); pre-commit re-verify
- **Rule #8**: codified `416d610` (cycle 3, mailbox authority + session-bootstrap awareness gate)
- **Rule #9**: codified `d61bdc8` (cycle 5, Protocol Bundle v4); operator-side reviewer independence + cold-context prompt-construction discipline (v4.1 R-9-1)
- **Rule #10**: **NEW this cycle**, codified `d66690f` (Protocol Bundle v5); Joint-team mode (two seats of one team; co-agent subtitle). Operator-seat updates the SHA placeholder `_Protocol Bundle v5 ship_` in PROTOCOL-RULES-LOG.md at next session-close per chicken-and-egg precedent.
- **Rule #11**: **NEW this cycle**, codified `d66690f` (Protocol Bundle v5); Codification bias check (per-rule beneficiary flagging + non-beneficiary veto). Retroactive snapshot of Rules 1-9 (4 both / 1 user / 3 operator-seat / 0 director-seat) lives in `docs/PROTOCOL-RULES-LOG.md`'s new "Beneficiary distribution snapshot" subsection. v5 self-application passed (7 both / 1 user / 1 operator-seat / 0 director-seat).

### Protocol Bundle v5 substrate is now live

**Philosophical reframe (P1):** Director-seat and operator-seat are **two seats of one team**, not senior/junior. Both serve the user-principal. Specialization is cognitive-load distribution, not hierarchy.

**Role partition relabeled** (lane assignments unchanged):
- "Director-only" → "**Strategic-seat-default**" (brief authoring, ADR, push, memory writes, codification)
- "Operator-only" → "**Operational-seat-default**" (counter-bump dispositions, Lane V, Lane D, Lane S, transplant-handoff refresh, mailbox event authoring)
- "Shared" → "**Cross-cutting**" (verification gates, applying review minors via chore commits, closing-report drafting)
- **NEW** "Strategic-seat-default (Lane B)" — implementer dispatch (Lane B) is now formally director-seat (Sh codification; was "Shared" in v1-v4 but practice-vs-spec divergence existed)

**v5 mechanisms added:**
- **D (Disagreement protocol)**: 2-cycle limit then escalate to user. Counting clarification per C-D-1: 2 cycles = director's REPLYs after the initial proposal, not operator's revisions. Total 5 documents before escalation.
- **E (Emergency handling)**: 4-criteria definition for what triggers §E (production/data-integrity, security-critical, active-bleed-rate, external-time-pressure). Cross-seat-temporary-authority during transplant. Post-incident review in `docs/INCIDENT-LOG.md`.
- **B (Backlog partition)**: NEW `docs/BACKLOG.md` as shared-visible workspace. Either-seat-add, director-seat-curates, operator-seat-claims Lane-D-style items.
- **M (Memory-candidate mailbox kind)**: operator-seat surfaces memory-worthy observations; director-seat writes or declines via `decision` event.
- **S (Lane S activation)**: was scaffolded in v4; now active. Director-seat sends `scout-request` BEFORE Lane B dispatch; operator-seat conducts Lane C-style survey; sends `scout-report`. Opt-in.
- **Sh (Implementer dispatch as director-seat-default)**: codifies de facto practice.

### Cycle-6 protocol learnings (worth carrying forward)

- **v5 negotiation was the cleanest cycle to date.** 0 counter-refinements, 1 round. The substrate has matured enough that operator's first drafts converge with director's first REPLY refinements without needing the disputed-item escalation paths v5 itself codifies. v5's D + E protocols are insurance — built but not yet fired. Correct order: build the protocol, dogfood it, refine.
- **R11 self-application is the cleanest meta-rule introduction.** v5 introduces Rule #11 AND immediately applies it to v5 itself (7 both / 1 user / 1 operator-seat / 0 director-seat). If R11 had failed on its introducing bundle, the rule would have been self-falsified. Cycle-7+ rule additions should follow the same pattern.
- **Lane V is well-calibrated, not yet self-validating.** Dispatch #1 (S12) was validation-only; dispatch #2 (S13) caught novel CRITICAL F1. Cumulative ~409k tokens, 3 novel findings = 1.5 novel/dispatch. Well above v4.1 narrowing-criterion (<15% novel-rate threshold). Cycle-7+ should continue per-feat trigger; revisit only on telemetry change.
- **Lane D's cost profile is markedly cheaper than Lane V** (~0 subagent burn for ~89 LOC backfill vs ~234k tokens for cross-system spec+code review). Different tools for different jobs; both valuable.
- **Brief-pattern silent-substitution is a real failure mode.** S13 implementer silently substituted `mutate_project + project-scan` for the brief's `_mutate_shot` pattern. Lane V caught F1 CRITICAL downstream. Cycle-7 implementer prompt should require explicit escalation of brief-pattern deviations (see priority #1 above).

### Known limitations the next director-seat should be aware of

- **Hook script's stale-by-one** is still real (documented v2.1 + v3 §H audit). STATE.md HEAD field is 1 SHA off from `git rev-parse HEAD` immediately after each commit.
- **Implementer subagent SHA reports are reliable** after the cycle-5 prompt-template fix (capture from `git log` after hook settles), but the underlying hook-amend pattern persists. Keep the guidance in cycle-7+ prompts.
- **`cinema_pipeline.py` is ~1113 LOC** (P1-2 orchestrator extraction deferred; gradually mounting).
- **`web_server.py` is ~1750+ LOC** (post-S13 endpoint + cycle-6 fixes; growing as P4-3 frontend backend support accumulates).
- **GitNexus mutex_lock teardown crash** continues on every `analyze --embeddings` (benign post-completion; functionally inert).
- **No frontend test framework** in the project (project convention: `tsc --noEmit` + manual smoke). S13's verification gate was operator's Lane V finding the F1+F2 issues; cycle-7+ may want to revisit (e.g., add vitest if regression cost mounts).
- **Spec-reviewer hallucinations** — observed 2/2 v4-era dispatches; v4.1 §CC-2 mitigation (prompt-construction discipline requiring grep before existence claims) is now codified. If hallucinations persist in cycle-7+ dispatches, v5.1 should consider operator's CC-2 options 2 (third lightweight verifier) or 3 (different subagent type).

### Verification before this handoff lands

```
$ git log --oneline 9aac767..HEAD | wc -l
12 (cycle-6 commits since cycle-5 close, all pushed; this handoff makes 13)

$ git rev-list --count origin/main..HEAD
0 (pre-handoff; will be 1 after handoff commit lands)

$ .venv/bin/python -m pytest tests/unit/ --tb=no -q | tail -1
711 passed, 3 skipped, 11 warnings, 10 subtests passed

$ .venv/bin/python scripts/ci_smoke.py
OK

$ ls coordination/mailbox/sent/
.gitkeep
(empty — no pending events for cycle 7)

$ git rev-parse HEAD
d66690f98c31b1a7eab42fe05ff9d9364b4aa2bb (v5 ship, post-amend)
```

---

## Sign-off

Outgoing director-seat (cycle 6, prepared at natural session-close):
- Session 13 P4-3 frontend fully shipped + audited + Lane V CRITICAL fix landed.
- P1-3 part 3 migration (second canonical example of S10 template) shipped.
- Protocol Bundle v4.1 SHIPPED (Lane V coalescing + spec-reviewer hallucination mitigation).
- Protocol Bundle v5 SHIPPED (philosophical reframe + Rules #10/#11 + D/E/B/M/S/Sh — the largest protocol-substrate evolution to date).
- Operator-seat's first Lane D dogfood landed (ARCHITECTURE.md §7.7 backfill).
- Operator-seat's 2 Lane V dispatches both processed (validation + CRITICAL catch + advisory findings).
- All 12 cycle-6 commits pushed to `origin/main` pre-handoff; this handoff makes 13.

Incoming director-seat (cycle 7): start with **STATE.md cold-read + freshness check** (v3 §F step 0a). Then read this handoff. Then check mailbox for any operator events that arrived since (cycle-7 may see first `memory-candidate` or first BACKLOG.md entry). Then choose between: implementer prompt template upgrade (Lane A, quick) / opportunistic P1-3 part 4 (Lane A, 30-45 min) / v5 dogfood opportunities (variable).

*The work is in excellent shape. P4-3 is fully shipped (the cycle-3-spanning deliverable). v5's "two seats of one team" framing is the stable end-state for the role partition's philosophical layer; future bundles will be smaller refinements. The substrate has now reached "production maturity" — built, dogfooded, refined, and used. Cycle 7+ optimizes for substrate USE, not substrate evolution.*

Signed,
Director-seat — 2026-05-25 (cycle 6, end of session, post-v5-ship)
