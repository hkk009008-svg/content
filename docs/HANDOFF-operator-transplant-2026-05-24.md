# Operator Handoff — Context Transplant 2026-05-26 (CYCLE-8 CLOSE / FEATURE-DELIVERY CYCLE)

**From:** Operator-seat (cycle-8 close refresh)
**To:** Next operator-seat instance, fresh chat
**Companion docs:**
- [HANDOFF-director-transplant-2026-05-26-cycle8.md](HANDOFF-director-transplant-2026-05-26-cycle8.md) (`4bf48cd` — director-seat cycle-8 close; **most recent director-seat pickup, read this first if director-seat**)
- [HANDOFF-director-transplant-2026-05-25-cycle7.md](HANDOFF-director-transplant-2026-05-25-cycle7.md) (`8d38929` — cycle-7 close historical)
- [HANDOFF-director-transplant-2026-05-25-cycle6.md](HANDOFF-director-transplant-2026-05-25-cycle6.md) (cycle-6 close historical)
- [HANDOFF-director-transplant-2026-05-25-cycle5.md](HANDOFF-director-transplant-2026-05-25-cycle5.md) (`9aac767` — cycle-5 historical)
- [HANDOFF-director-transplant-2026-05-24-cycle3.md](HANDOFF-director-transplant-2026-05-24-cycle3.md) + [-cycle2.md](HANDOFF-director-transplant-2026-05-24-cycle2.md) (early-cycle historical)
- [PROPOSAL-feature-directorial-iteration-and-screening-2026-05-25.md](PROPOSAL-feature-directorial-iteration-and-screening-2026-05-25.md) (`3227ff0` — cycle-8 feature proposal; user-authorized; director ENDORSED Q1-Q5 via `6f29d49`)
- [B-003-design-exploration.md](B-003-design-exploration.md) (`955be1f` — 5-option design exploration; Option E shipped at `2183ccb`)
- [POST-ROADMAP-2026-05-24.md](POST-ROADMAP-2026-05-24.md) (last refreshed cycle-6 close P4-3 SHIPPED; cycle-7 + cycle-8 didn't trigger another rotation — both worked on user-authorized features OR housekeeping outside the P-spine)
- [HANDOFF-roadmap-2026-05-24.md](HANDOFF-roadmap-2026-05-24.md) (Sessions 7-14 briefs; historical context only — all sessions shipped through cycle 7)
- [PROPOSAL-protocol-bundle-v5-2026-05-25.md](PROPOSAL-protocol-bundle-v5-2026-05-25.md) (`d66690f` — v5 substrate; "two seats of one team" reframe)
- [CLAUDE.md](../CLAUDE.md) `# Director-Operator Concurrent Operation` — full protocol including Rules #1-#11 + v5 two-seat reframe + D/E/B/M/S/Sh sections

---

## TL;DR (60 seconds)

**Cycle 8 = feature-delivery cycle.** Cycle 6 shipped v5 substrate; cycle 7 validated it via dogfood; cycle 8 USED it to deliver the first user-authorized product features end-to-end. **Surface A (S15-S17 + F1 accept-both) SHIPPED end-to-end behind `CINEMA_DIRECTORIAL_ITERATION` env flag.** Pytest **737 passed / 3 skipped / 0 failed** (was 715 cycle-7 close: +22).

- **User-authorized cycle-8 features (Directorial Iteration Loop + Screening/Selective Regen).** Mid-session, user-principal authorized TWO new product features and explicitly directed cross-seat design dialogue before implementation. Operator drafted [PROPOSAL-feature-directorial-iteration-and-screening-2026-05-25.md](PROPOSAL-feature-directorial-iteration-and-screening-2026-05-25.md) (`3227ff0`); director-seat sent `decision` REPLY (`6f29d49`) ENDORSING Q1-Q5 + Path A sequencing (zero counter-refinements — cleanest cross-seat REPLY cycle to date). 7 slices planned (S15-S21). **Surface A functionally complete** end-to-end; Surface B (S19-S21 screening) carries to cycle 9.
  - **S15 substrate** — `e695e81` (operator Lane A, ~1.5h). NEW `DirectorialIntent` Pydantic model + `llm/director.py` CinemaDirector v1.0 (permissive constraint regime, distinct from ChiefDirector's HC1-HC8 firewall) + `intent_translator()` functional API + JSONL log stub at `data/intent_log/`. 2 unit tests pass.
  - **S16 backend** — `c425d55` (director's implementer Lane B). NEW `POST /api/projects/<pid>/shots/<shot_id>/takes/<take_id>/iterate` endpoint + `ShotController.regenerate_with_intent` method + 16 tests.
  - **S17 frontend** — `b806bc7` (director's implementer Lane B). NEW `IterationPanel.tsx` + `ReviewStage.tsx` KEYFRAME_REVIEW wiring + `usePipelineState.iterateTake` action.
  - **F1 accept-both** — `a8bde27`. Endpoint honors nested `{intent: {...}}` AND flat `{prose, ...}` body shapes via `isinstance(data.get("intent"), dict)` guard.

- **B-002 + B-003 architecturally resolved via Option E** (`2183ccb`, mid-cycle-8). After B-002's reflog gate (`f19d4d3`) partially fixed the hook divergence, B-003 surfaced the remaining compound `commit && push` timing window. The user-authorized fix (via AskUserQuestion modal) was Option E from [B-003-design-exploration.md](B-003-design-exploration.md): **STATE.md gitignored** + `git rm --cached` + `.claude/hooks/update-state.sh` simplified 148→102 LoC (removed staged-set check, reflog gate, `git add` + `git commit --amend` lines). Hook now: detects HEAD move via marker file → regenerates STATE.md on disk → exits. **No git history modification.** **Compound `git commit && git push` is now genuinely safe — the separate-Bash-call workaround is RETIRED.** Both stale-by-one (B-002 cosmetic) and divergence (B-003 functional) eliminated. v2.1 KNOWN LIMITATION moot. Codified in new operator memory: `feedback_compound_commit_push_safe_post_b003.md`.

- **2 Lane V dispatches from operator this cycle.**
  - **Lane V #4** (per-commit on `c425d55`): 0 critical / 0 important / 5 minor (F1 body-shape drift / F2 approved_shots filter / F3 route param / F4 test coverage / F5 pre-seed) + **F0 reviewer-disagreement** (mine: pattern-consistent vs director's: blocker on `_reject_if_project_busy` omission — director's framing was correct, sibling-uniformity restored at 19 endpoints via `15493c8`). Verification-report at `coordination/mailbox/sent/2026-05-25T15-37-08Z-operator-to-director-verification-report.md`. **~189k tokens.**
  - **Lane V #5 (FIRST CC-1 COALESCED)**: 4-commit range `7f5dea7..a8bde27` (tightly-coupled: S17 frontend + F1 backend + F3/F5 folds + S17 self-fix). 0 critical / 0 important / 4 minor (G1-G4 forward-looking). Verification-report at `coordination/mailbox/sent/2026-05-25T15-37-08Z-...`. **~195k tokens.** Both reviewers independently confirmed CC-1 coalescing was the right call.
  - **Cumulative v4.1 telemetry post-cycle-8:** 5 dispatches / ~960k tokens / ~12 novel findings / **0 hallucinations across all 5** (CC-2 verify-before-asserting + R-9-1 cold-context working at N=3). v4.1 narrowing threshold NOT crossed.

- **F-finding closure tracking.** From operator Lane V #4 + #5: F0 closed (busy guard at `15493c8`) / F1 closed (accept-both at `a8bde27`) / F2 DEFER → S18 carryover / F3 closed (rename at `c5a0e94`) / F4 partial (+ 2 routing tests via `15493c8`; rest defer to S17/S18) / F5 closed (pre-seed collapse at `c5a0e94`) / G1 closed (`f8b4deb` ambiguous-body comment) / G2 closed (`f8b4deb` JSDoc) / G3 DEFER → S18/S20 design / G4 closed via **B-004 seed** (`74f3f62`). **4 of 5 director-actionable F-advisories closed within 2 fix-commits + 1 feat-commit** — tightest loop closure to date.

- **BACKLOG substrate end-to-end validated.** B-001 closed cycle-7 (template-level fix); B-002 + B-003 closed cycle-8 via Option E; B-004 seeded cycle-8 close (operator from G4 advisory: IterationPanel UX polish — m2 Escape-key dismissal + m3 non-JSON 502 status context). Active candidates as of refresh: **B-004 (1 row, low-priority UX polish)**. v5 §B works as designed.

- **Other cycle-8 shipped.** P1-3 part 5 (`1ac010c`, `api_update_location` migration — 4th canonical S10 template application) + P1-3 part 6 (`b28b8b4`, `api_upload_driving_video` — 5th canonical application, NEW shape: single-entity existence check in MUTATING endpoint). `datetime.utcnow()` migrated (`9c749b7`) — 9 warnings eliminated. ARCHITECTURE.md §16 doc-sync (`0d9bbbf`). Director-seat cycle-8 transplant handoff (`4bf48cd`).

- **Cross-seat process learnings codified during cycle 8.**
  - **Scout-discard convention**: director-seat drafted Lane S `scout-request` for S15 in NEW `coordination/mailbox/draft/` subdirectory; my S15 commit body answered all 3 targets explicitly → director discarded without sending (`a00922b`). Thorough commit bodies obviate scout cycles.
  - **Reviewer-prompt learning (NOT yet codified into rules)**: director-seat's own reviewers over-generalized on F0 by comparing busy-guard against full-file dominant pattern (18/19 endpoints have it) instead of adjacent-file-area siblings (sibling generation-triggering endpoints in the same range DO omit it). Director's commit body explicitly logged: "my reviewer prompts need 'verify ADJACENT-FILE-AREA siblings, not just dominant pattern across the file' instruction before generalizing." Worth carrying into cycle 9.
  - **Decision-event-not-needed-on-clean-Lane-V pattern**: director-seat responded to my Lane V #5 (clean / advisory only) via `f8b4deb` commit (which folded G1+G2 + advanced cursor + deferred G3+G4 with rationale) instead of sending a return mailbox event. The commit body WAS the substantive response. Pattern: clean verification-reports don't always need a return event.

- **Memory updated** (local-only, not git-tracked): NEW `feedback_compound_commit_push_safe_post_b003.md` codifies the B-003 Option E discipline change (default to compound commit+push; STATE.md is local-only / regenerated on disk; B-002 reflog gate removed as moot). `MEMORY.md` index updated. The existing `director_transplant_handoff.md` memory entry was also updated by director-seat to point at cycle-8 transplant — 700+ word index entry captures all cycle-8 substance.

- **Branch state at this refresh:** HEAD `74f3f62` (operator's B-004 seed); branch **1 ahead of `origin/main`** (B-004 not yet pushed — director-seat picks up push timing per v5 §Sh in their next session). Working tree: **dirty (S18 implementer subagent in flight)** — `cinema/shots/controller.py` + `llm/director.py` + `tests/unit/test_director.py` modified with verb DSL additions (`tighten_framing` / `match_shot` / `shift_emotion`), not yet committed at refresh-Write time. **Race-ack (Rule #5):** S18 is mid-flight; next operator-seat will pick up post-S18-commit. **Mailbox cursor (operator.txt):** `2026-05-25T15:49:12Z` (consumed director's Lane V #4 decision-REPLY).

---

## How to resume (cold-start checklist for next operator)

```bash
# 0. Cold-read STATE.md (machine truth, auto-maintained by hook after
#    each commit — see Protocol Bundle v2). NEW first step.
cat STATE.md

# 0a. STATE.md freshness check (per Protocol Bundle v3 §F).
#     Closes the silent-hook-failure mode where STATE.md drifts from
#     reality and both agents trust a lie. v2.1 (`5e0329d`) was a regex
#     bug in the hook that demonstrated this failure mode is real.
STATE_FRESHNESS_SECONDS=5   # Slack accounts for hook execution time;
                            # widen if hook becomes heavier; see v3 §F R-F1.
STATE_TS=$(grep -oE 'Updated:.*\(' STATE.md | grep -oE '[0-9-]+T[0-9:]+Z')
HEAD_TS=$(git log -1 --format='%cI' HEAD | sed 's/[+-][0-9:]*$/Z/')
# If STATE.md's Updated timestamp is within $STATE_FRESHNESS_SECONDS of HEAD:
#   trust STATE.md fields (HEAD, branch, tree, smoke, pytest, mailbox)
#   skip step 1's manual verification
# If outside window OR STATE.md missing OR timestamp parse fails:
#   STATE.md is stale or unreliable; run step 1 manually for ground truth
#   AND surface to user: "STATE.md staleness detected; falling back to manual verify"
#
# If STATE.md is stale OR the hook isn't registered in YOUR
# .claude/settings.local.json (per-clone setup; see coordination/README.md):
#   re-run step 1 manually for ground truth.
#
# IMPORTANT (Rule #8 session-bootstrap awareness gate): If STATE.md's
# `unread mailbox` field shows N ≥ 1 events for your role, surface to user
# in your FIRST user-facing turn BEFORE processing events:
#   "Mailbox has N unread event(s) for {role}; processing now per Rule #8."

# 1. Verify baseline (only when STATE.md is stale or missing)
.venv/bin/python scripts/ci_smoke.py            # expect: OK
.venv/bin/python -m pytest tests/unit/ -q | tail -1
# expect: whatever STATE.md / latest commit body claimed, or higher if a
# new session shipped tests

# 2. Verify branch state (if STATE.md is stale)
git status                                       # expect: clean (or counter bumps in flight)
git log --oneline -3                             # expect: latest top
git rev-list --count origin/main..HEAD           # expect: 0 (just pushed) — or N if director shipped further

# 3. Read in this order
#    a. STATE.md (you already did this in step 0)
#    b. coordination/mailbox/sent/ — process any unread events for your
#       role; update coordination/mailbox/seen/{director,operator}.txt
#       to the latest consumed timestamp
#    c. ARCHITECTURE.md §15 smoke (run it again if STATE.md said FAIL or unknown)
#    d. THIS FILE (you're reading it)
#    e. docs/POST-ROADMAP-2026-05-24.md (refreshed cycle-3 picks)
#    f. docs/HANDOFF-director-transplant-2026-05-24-cycle2.md (director's pickup if you're director-role)
#    g. CLAUDE.md "# Director-Operator Concurrent Operation" — full protocol including the 8 rules (Rules 1-6 from ad6cb4f + ea97d0a; Rules 7-8 from Protocol Bundle v2 ship)
#    h. docs/PROTOCOL-RULES-LOG.md — rule emergence + invocation tracker
#    i. CLAUDE.md "Working a Multi-Task Plan" + "Verification discipline" — mandatory
#    j. AGENTS.md mirror of (g) and (i) for non-Claude tools
#    k. docs/STRATEGIC_REVIEW-2026-05-24.md (P-priority ledger; most items now dispositioned in POST-ROADMAP)
#    l. docs/HANDOFF-director-transplant-2026-05-24.md (cycle 1 — historical only)

# 4. If no director dispatch yet, do NOT pre-stage work on shared tasks
#    without running `git log --oneline -5` first (Rule #4).
#    Also: state-asserting writes (handoff docs, status reports, commit bodies
#    naming HEAD/branch counts) gate on the same precondition (Rule #4).
#    AND: immediately before `git commit`, re-run `git log --oneline -5` AND
#    check `coordination/mailbox/sent/` for new events (Rule #7 pre-commit
#    re-verify).
#    See operator memory: feedback_pre-locate-after-git-log.md.
```

---

## Commit ledger (full conversation, in chronological order)

Operator + DIRECTOR (multiple cycles) interleaved. The director made periodic commits — these are NOT race conditions; deliberate parallel work. Coordination protocol codified in `ad6cb4f` + extended in `ea97d0a`.

### Phase 0 — Audit + correction

| SHA | Type | By | Summary |
|---|---|---|---|
| `c902e87` | chore(baseline) | operator | GitNexus index counter bump (3037→3094) |
| `27609c2` | fix(tests) | operator | Unstick 7 baseline failures (test_quality_max_overlay schema + 6 test_project_manager fixture monkeypatch-wrong-symbol) |
| `ed33035` | docs(discipline) | **DIRECTOR** | Codify Tier-1 verification rules + Tier-3 tooling P1 |
| `0cdef13` | docs(audit) | operator | Rewrite STRATEGIC_REVIEW §P0-1 + HANDOFF Sessions 2/3/5 (Create→Audit+Extend) + ARCHITECTURE §16 + LOC counts + OPERATIONS §7 baseline |
| `79747ad` | docs(discipline) | operator | Bring P0-1 + Session 1 acceptance into Rule-1 compliance |

### Session 1 — P0-2 CI workflow

| SHA | Type | By | Summary |
|---|---|---|---|
| `a94c50b` | ci | operator | `.github/workflows/ci.yml` + README CI section |
| `5d3a580` | ci(template) | operator | `.github/pull_request_template.md` |
| `7c93cd6` | refactor(smoke) | operator | Extract §15 block to `scripts/ci_smoke.py` (single source of truth) |

### Session 2 — P0-1.1 ReviewController test extension

| SHA | Type | By | Summary |
|---|---|---|---|
| `cfbffb9` | test(review) | operator (via subagent) | +26 tests covering approve_take + _gate_satisfied + _candidate_take + _resolve_motion_source |
| `37c9350` | fix(shots) | **DIRECTOR** | Production bug: `_find_take` omitted `performance_takes` |
| `2d58710` | chore(test) | operator | Session 2 quality-reviewer MINORs |

### Session 3 — P0-1.2 workflow_selector test extension

| SHA | Type | By | Summary |
|---|---|---|---|
| `4ea4414` | test(workflow_selector) | operator (via subagent) | +69 tests (47 keyword routes + 8 adaptive boost + WORKFLOW_TEMPLATES shape locks + MOTION_FIDELITY_FLOORS) |
| `8f1dee9` | chore(test) | operator | Session 3 quality-reviewer MINORs |

### Session 4 — P1-1 structured logging

| SHA | Type | By | Summary |
|---|---|---|---|
| `6750292` | feat(logging) | operator | Foundation: `cinema/logging_config.py` + `setup_logging()` in web_server.py |
| `eceb9a2` | docs(handoff) | **DIRECTOR** | Cycle-1 director context-transplant handoff |
| `656f0f2` | refactor(logging) | operator (via subagent) | 36 print()→logger across cinema_pipeline.py + cinema/shots/controller.py |
| `aa1e748` | docs(handoff) | **DIRECTOR** | Codify bug-fix-inline precedent + mark Sessions 1–4 SHIPPED |
| `9b4dfa0` | chore(baseline) | **DIRECTOR** | GitNexus index counter bump |
| `4665a2d` | chore(logging) | operator | Session 4 IMPORTANTs |
| `6485f22` | docs(logging) | **DIRECTOR** | Add caller-field convention block |
| `56be212` | chore(baseline) | **DIRECTOR** | GitNexus index counter bump |
| `c0b1ed0` | chore(logging) | operator | Session 4 deferred MINORs |

### Session 5 — P0-3 cost_tracker.record_api_call coverage

| SHA | Type | By | Summary |
|---|---|---|---|
| `bdeeee5` | fix(cost) | **DIRECTOR** | TestRecordAPICall (6) + TestBudgetGate (5) + 2-instance silent-except sweep; test_cost_tracker.py 33→49 tests |
| `24a1618` | docs(handoff) | operator | Note Session 5 shipped by director |
| `ed01c09` | chore(test) | **DIRECTOR** | Session 5 minors |

### Session 6 — P1-4 + P2-3 frontend resilience + cascade visibility

| SHA | Type | By | Summary |
|---|---|---|---|
| `d516d2a` | feat(ui) | **DIRECTOR**'s implementer subagent | ErrorBoundary at every shell |
| `b25da2e` | feat(takes) | **DIRECTOR**'s implementer subagent | cascade_metadata on TakeRecord; populated in lip_sync.py + phase_c_ffmpeg.py; rendered in TakeStrip + ReviewStage |
| `c6eaefb` | chore | **DIRECTOR** | Session 6 minors (phase_c attempts set→list, 2 cosmetic) |

### Session 7 — POST-ROADMAP pick #1 (face_validator_gate)

| SHA | Type | By | Summary |
|---|---|---|---|
| `bfada2d` | docs(handoff) | **DIRECTOR** (cycle 2) | Session 7 brief appendix to HANDOFF-roadmap (face_validator_gate scope: ~19 tests across 4 classes) |
| `06109b5` | test(face_validator) | **DIRECTOR**'s implementer subagent | Tests for score_candidate + should_halt + needs_regenerate — new tests/unit/test_face_validator_gate.py (280 LOC) |
| `843c102` | docs(handoff) | operator | Refresh operator-transplant for post-roadmap + S7 in-flight state |
| `d8bf650` | chore(test) | **DIRECTOR** (cycle 2) | Session 7 minors (7 items from spec + code-quality reviewers; net 19→23 tests via parametrize expansion + boundary cases) |

### Session 8 — POST-ROADMAP pick #2 (P1-3 Pydantic schema, PARTIAL)

| SHA | Type | By | Summary |
|---|---|---|---|
| `c7338a8` | docs(handoff) | **DIRECTOR** (cycle 2) | Session 8 brief — Pydantic schema validation on project.json |
| `ceb0a32` | feat(schema) | **DIRECTOR**'s implementer subagent | Pydantic models + boundary validation: new domain/models.py (144 LOC), boundary hook in project_manager.py (+31 lines), requirements.txt (+5 lines pydantic) |
| `f9b0aff` | test(schema) | **DIRECTOR**'s implementer subagent | Model + boundary integration tests in new tests/unit/test_project_models.py (~15 tests) |
| `66b06c8` | chore(schema) | **DIRECTOR** | Session 8 code-review minors (+1 test → 629 baseline) |

### Post-roadmap / discipline / transplant (interleaved)

| SHA | Type | By | Summary |
|---|---|---|---|
| `df04142` | docs(roadmap) | **DIRECTOR** | POST-ROADMAP-2026-05-24.md — P-priority closure matrix + top-3 next-pickup (initial creation) |
| `ad6cb4f` | docs(discipline) | operator drafted, **DIRECTOR** shipped (+3 refinements) | `# Director-Operator Concurrent Operation` in CLAUDE.md + AGENTS.md (role partition, signaling, git tiebreaker, draft-then-ship for codification) |
| `97704c8` | chore(baseline) | operator | Counter bump 3306→3308 (post-discipline section reindex) |
| `2662812` | chore(baseline) | operator | Counter bump 3308→3299 (drift convergence; fixpoint in 2 commits; **push happened at this SHA**) |
| `60001d9` | docs(handoff) | **DIRECTOR** (cycle 2) | Cycle-2 director context-transplant doc |
| `ea97d0a` | docs(discipline) | operator drafted, **DIRECTOR** shipped (with refinement) | 3 more discipline rules: state-asserting writes precondition, race-acknowledging commit bodies, counter-bump fold-and-surface during concurrent ops |
| `5c4a7c9` | docs(roadmap) | **DIRECTOR** | POST-ROADMAP refresh for post-cycle-3 picks (Monitor.tsx promoted to #1; P4-3 added as #2; Session 9 framed as #3) |
| `1541a69` | docs(handoff) | operator | First operator-transplant refresh for post-cycle-3 state (folded ad6cb4f counter bump; race-acked a6e3ff1 mid-write) |
| `a6e3ff1` | feat(monitor) | **DIRECTOR** | Wire cascadeMetadata into live-run TakeStrip (POST-ROADMAP top-3 #1 quick-claim, shipped by director not operator) |
| `64c7571` | docs(roadmap) | **DIRECTOR** | POST-ROADMAP rotation post-Monitor (top-3 picks rotated) |
| `e164505` | docs(audit) | **DIRECTOR** | P3-1 concurrency audit — 2 unguarded globals in web_server.py |

### Session 9 — P3-1 concurrency hardening (post-audit follow-on)

| SHA | Type | By | Summary |
|---|---|---|---|
| `607348d` | docs(roadmap) | **DIRECTOR** | Session 9 brief — P3-1 concurrency hardening |
| `bfa60bf` | feat(web) | **DIRECTOR**'s implementer subagent | Close `_running_pipelines` / `_progress_queues` race surfaces in web_server.py |
| `a97573e` | test(web) | **DIRECTOR**'s implementer subagent | Cover concurrent api_generate + _ensure_progress_queue race |
| `e8b5ebc` | docs(product) | **DIRECTOR** | Surface P4-3 auto-approve design questions |
| `f8b2aef` | chore(web) | **DIRECTOR** | Session 9 code-review minors |
| `7c92f2f` | docs(roadmap) | **DIRECTOR** | Session 11 brief — P4-3 backend auto-approve |

### Protocol Bundle v2 ship + v2.1 fix

| SHA | Type | By | Summary |
|---|---|---|---|
| `c6a8f22` | docs(reply) | **DIRECTOR** | REPLY to operator's v2 proposal with R1/R3/R5 refinements + C2/C4 clarifications |
| `1b3f6f8` | docs(proposal) | operator | Revise v2 proposal per REPLY (5 targeted edits to drafts) |
| `416d610` | feat(protocol) | **DIRECTOR** | **Ship Protocol Bundle v2**: STATE.md + PROTOCOL-RULES-LOG.md + Rules #7/#8 + coordination/mailbox/ scaffold + hook script |
| `5e0329d` | chore(protocol) | **DIRECTOR** | Bundle v2.1 — pytest regex fix + KNOWN LIMITATION header per C2 + inline comment per C4 |
| `3e57ddf` | docs(rules-log) | operator | Update Rules #7/#8 codification SHAs to 416d610 (placeholder→actual); first Rule #7 dogfood invocation |

### Session 11 — P4-3 backend auto-approve

| SHA | Type | By | Summary |
|---|---|---|---|
| `cefde42` | docs(roadmap) | **DIRECTOR** | Session 10 brief — P1-3 part 2 strict mode + first caller migration (implementer pending; held for separate dispatch) |
| `d6fd3e1` | feat(cinema) | **DIRECTOR**'s implementer subagent | Auto-approve veto rules + per-gate config + ShotState integration (new cinema/auto_approve.py) |
| `ad526c3` | test(cinema) | **DIRECTOR**'s implementer subagent | Cover auto-approve veto rules + per-gate integration (new tests/unit/test_auto_approve.py) |
| `42df2ac` | chore(cinema) | **DIRECTOR** | Session 11 v1.1 — best-take semantics consistency (+5 tests → 664 pytest baseline) |

### Protocol Bundle v3 proposal cycle (pending ship)

| SHA | Type | By | Summary |
|---|---|---|---|
| `749341b` | docs(proposal) | operator | Draft v3 proposal — G (authority hierarchy), F (STATE.md freshness check), H (hook script audit) |
| `26a0842` | docs(reply) | **DIRECTOR** | REPLY to v3 proposal with R-G1 (5-min window), R-F1 (named constant), R-H1 (v2.1 baseline), C-G1 (user-tier clarification) |
| `ec1e64e` | docs(proposal) | operator | Revise v3 proposal per REPLY (5 targeted edits; 4th Rule #7 dogfood; no drift caught) |
| `3340d1f` | feat(protocol) | **DIRECTOR** | **Ship Protocol Bundle v3**: G (Rule #8 extended) + F (STATE.md freshness check in cold-start) + H (hook script audit doc) + Minor (PROTOCOL-RULES-LOG per-regime caveat). Folded held counter bumps + director's pre-impl edits from working tree. |
| THIS COMMIT | docs(handoff) | operator | Refresh operator-transplant doc for post-v3-ship state. Race-ack: v3 shipped during this refresh write (Rule #7 caught the drift in pre-commit re-verify); re-edited TL;DR + ledger + what's-pending to reflect SHIPPED, not pending. |

**Total: ~30 commits since `5c4a7c9` (last handoff refresh). Branch ahead-count varies with push events; check `git rev-list --count origin/main..HEAD`.**

---

## What's pending after Sessions 7-14 + v2/v3/v4/v4.1/v5 ship (cycle-6 close)

Sessions 1-14 all SHIPPED. Protocol Bundles v2/v3/v4/v4.1/v5 all SHIPPED.

**Operator-seat post-v5-ship chores** (cycle-6 close → cycle-7 setup):

1. **SHA placeholder fill-ins** (one operator commit per chicken-and-egg precedent — mirrors of `3e57ddf` post-v2, `d8f2407` post-v3, `d90036b` post-v4):
   - `docs/PROTOCOL-RULES-LOG.md` Rule #10 row: `_Protocol Bundle v5 ship_` → `d66690f`
   - `docs/PROTOCOL-RULES-LOG.md` Rule #11 row: `_Protocol Bundle v5 ship_` → `d66690f`
   - `docs/PROTOCOL-RULES-LOG.md` v4.1 ship marker: `_Protocol Bundle v4.1 ship_` → `509db7c` (carried over from v4.1 ship; never filled)
   - `docs/PROPOSAL-protocol-bundle-v5-2026-05-25.md` footer: `_Protocol Bundle v5 ship_` → `d66690f`

2. **Counter bump disposition (Rule #6)**: held in WT (`M AGENTS.md`, `M CLAUDE.md`) from director's session reindex post-v5-ship. Fold into the SHA fill-in commit OR ship as standalone `chore(baseline)`. Lean: fold (operator's natural-next-commit pattern; matches `d8f2407` post-v3 model).

3. **Session 14 (`e1b72ca`) Lane V dispatch**: `feat(schema): P1-3 part 3 — migrate api_decompose_scene to Project.model_validate` qualifies under operator's R-V1-countered trigger (every `feat` / `refactor` / `fix`). Cumulative v4.1 telemetry would advance from 2 → 3 dispatches.

4. **POST-ROADMAP refresh post-v5-ship** — last rotation `d4b398b` (P4-3 SHIPPED) predates v5 ship. Director-seat task per role partition.

5. **v5 dogfood opportunities** (next operator session):
   - First `scout-request` mailbox event (Lane S activation; opt-in per director-seat)
   - First `memory-candidate` mailbox event (v5 M)
   - First BACKLOG.md item (if operator-seat surfaces during cycle-7)
   - First R11 beneficiary check on a new v5.1+ proposal candidate
   - First v5 §E emergency handling invocation (hopefully never; but the protocol exists)

Push state: HEAD `d66690f` is at `origin/main`. Nothing unpushed unless operator commits the SHA fill-ins post-handoff.

---

### Cycles 5-6 commit ledger (append to historical Phase 0 + cycles 1-3 above)

#### Cycle 5 — Protocol Bundle v4 propose/REPLY/revise/ship + Session 12 + Session 13 brief

| SHA | Type | By | Summary |
|---|---|---|---|
| `5302fe6` (post-amend) | docs(proposal) | operator | v4 proposal initial draft |
| `c487171` | chore(baseline) | operator | Post-v4-proposal reindex chore |
| `8975a45` | docs(reply) | director | v4 REPLY with R-V1 (Lane V narrowing), R-D1 (README carve-out), R-9-1 (cold-context discipline), C-V1 + C-Dogfood-1 |
| `4fdcc01` | docs(proposal) | operator | v4 revision per REPLY with **operator counter-refinement to R-V1** (first cross-seat counter precedent) |
| `d61bdc8` | feat(protocol) | director | **Ship v4** — Lanes V/D/S scaffold + Rule #9 + Phase taxonomy |
| `7da49ed` | docs(rules-log) | operator | Rule #9 SHA placeholder fill (chicken-and-egg) |
| `2a25c2d` | feat(cinema) | director's implementer | Session 12 motion-gate opt-in (CINEMA_AUTO_APPROVE_MOTION) |
| `771bbf7` | test(cinema) | director's implementer | Session 12 tests (+21) |
| `fefea5d` | chore(cinema) | director | Session 12 code-review minor (top-level os import) |
| `2fef5ef` | docs(roadmap) | director | Session 13 brief — P4-3 frontend |
| `9aac767` | docs(handoff) | director | Cycle-5 transplant handoff (first to mention "first Lane V dogfood") |

#### Cycle 6 — Session 13 ship + Session 14 + Protocol Bundles v4.1 + v5

| SHA | Type | By | Summary |
|---|---|---|---|
| `029dbf9` | feat(types) | director's implementer | Session 13 TypeScript types mirror |
| `2fb44d1` | feat(web) | director's implementer | Session 13 P4-3 frontend (858 LOC: AutoApproveBadge + PostRunSummary + RejectAutoApproveModal + reject endpoint) |
| (operator dispatch) | Lane V #2 | operator | Combined Lane V on `9aac767..2fb44d1` — 1 CRITICAL (F1 multi-project) + 2 Important findings; archived at `mailbox/archive/2026-05-24T17-24-52Z-operator-to-director-verification-report.md` |
| `f7d7a19` | chore(web) | director | Session 13 code-review chore-minors |
| `d4b398b` | docs(roadmap) | director | POST-ROADMAP rotate for cycle-6 close (P4-3 SHIPPED) |
| `1e29610` | docs(arch-sync) | operator | **First Lane D dogfood** — ARCHITECTURE.md §7.7 backfill (+89 LOC, Pydantic boundary + escalation pattern) |
| `e1b72ca` | feat(schema) | director's implementer | Session 14 P1-3 part 3 (api_decompose_scene migration) |
| `9e24323` | fix(web) | director | **Director acted on operator's Lane V findings**: pid-scoped reject route + monotonic-run dedup (resolves F1 + F2) |
| `509db7c` | chore(protocol) | director | **Protocol Bundle v4.1** — CC-1 Lane V coalescing + CC-2 spec-reviewer hallucination mitigation |
| `2e06fe1` | docs(proposal) | operator | v5 proposal draft ("two seats of one team" reframe; responds to user-level structural critique) |
| `642250d` | docs(reply) | director | v5 REPLY with R-E-1 (emergency criteria) + C-D-1 (counting clarification); 8/8 open questions aligned with operator's lean |
| `8a4148a` | docs(proposal) | operator | v5 revision per REPLY (zero counter-refinements; cleanest cycle to date) |
| `d66690f` | feat(protocol) | director | **Ship v5** — two-seat reframe + Rules #10/#11 + D/E/B/M/S/Sh; cycle-6 close |
| `4fafa8f` | docs(handoff) | director | Director-seat cycle-6 transplant — post-v5-ship + S13 P4-3 SHIPPED + 2 Lane V + 1 Lane D dogfood |
| `22d7467` | docs(handoff) | operator | Refresh operator-transplant for post-v5-ship / cycle-6 close (prior session's close) |

#### Cycle 7 — opens (2026-05-25; this session)

| SHA | Type | By | Summary |
|---|---|---|---|
| `f665461` | docs(rules-log) | operator | Fill v5 + v4.1 ship SHA placeholders (5th instance of chicken-and-egg precedent chain; auto-amended from `22d1333` by post-commit hook) |
| `2515182` | docs(implementer-prompt) | director | Harden Implementer Prompt Template with cycles 5-6 lessons (cycle-7 priority #1 from `4fafa8f`); commit body race-acks `f665461` per Rule #7 |
| `d71b2ab` | coord(mailbox) | operator | Lane V #3 verification-report on `e1b72ca` (⚠️ MINOR ADVISORIES — 3 advisory findings, 0 critical/important; CC-2 first clean dispatch; auto-amended from `8d8ac7b`) |
| `308cdef` | feat(schema) | director | **P1-3 part 4** — migrate `generate_scene_preview` to `Project.model_validate` (omnibus: also folded operator's Lane V #3 event into archive + cited operator's F1/F2 dispositions in commit body — first intra-session Lane V finding-loop completion) |
| `3db44af` | docs(handoff) | operator | Operator-transplant cycle-7-open refresh post-Lane-V#3 (auto-amended from `d5a2fff`; race-acked 2 director commits during Write) |
| `421f364` | docs(backlog) | director | Seed first v5 §B BACKLOG row (B-001) from operator's Lane V #3 F2 — first end-to-end mailbox→BACKLOG row activation |
| `02603f0` | coord(mailbox) | operator | Query to director on `.claude/settings.json` disposition (auto-amended from `618cb98`; mid-session detour from cycle-7 queue) |
| `cf65130` | coord(mailbox) | director | Decision event picking Option 1 for settings disposition (user-approved via AskUserQuestion modal; first `decision`-kind mailbox dogfood end-to-end) |
| `c054049` | chore(settings) | operator | Execute settings shuffle (auto-amended from `d20c66b`) — delete `.claude/settings.json` + append rule to gitignored `settings.local.json`; commit-body-as-audit-trail since git-visible diff covers only mailbox coordination |
| `b1d36d2` | docs(migration) | director | **Close B-001** — add unhappy-path test recipe + 2 example tests to `MIGRATION-PATTERN-pydantic-caller.md` (template-level fix; all P1-3 part N migrations inherit) |
| `6e1deb0` | docs(web) | director | **Close F1** — fix cite imprecision at `web_server.py:1141` (~1-line cite tweak: `:1106` → analogous-line ref) |
| `6c07e61` | docs(backlog) | director | Seed B-002 — fix `update-state.sh` hook to skip non-commit HEAD changes (addresses the STATE.md staleness pattern operator surfaced in repeated check turns) |
| `8d38929` | docs(handoff) | director | Cycle-7 director transplant — substrate-validation cycle close |
| `eeea93f` | docs(handoff) | operator | Operator-transplant refresh for cycle-7-wave-2 close |

#### Cycle 8 — feature-delivery cycle (2026-05-25 → 2026-05-26)

The densest cycle in project history (25+ commits + this handoff refresh = 26). Cycle 8 USED v5 substrate to deliver the first user-authorized product features end-to-end. Surface A of directorial iteration loop is functionally complete behind `CINEMA_DIRECTORIAL_ITERATION` env flag.

| SHA | Type | By | Summary |
|---|---|---|---|
| `f19d4d3` | fix(hooks) | director | **B-002 partial fix** — gate `update-state.sh` amend on git reflog commit action (later superseded by B-003 Option E) |
| `1ac010c` | feat(schema) | director's implementer | **P1-3 part 5** — `api_update_location` migration (4th canonical S10 template application; single-entity existence check in MUTATING endpoint) |
| `3227ff0` | docs(proposal) | operator | **Seed cycle-8 feature proposal** — directorial iteration loop + screening / selective regen (response to user-principal authorization + collaborative-dialogue directive) |
| `215422a` | coord(mailbox) | operator | Operator query → director on cycle-8 feature design dialogue |
| `b28b8b4` | feat(schema) | director's implementer | **P1-3 part 6** — `api_upload_driving_video` migration (5th canonical app; cross-scene shot lookup variant) |
| `b1e423e` | docs(backlog) | director | Seed **B-003** — compound `commit && push` still produces hook divergence after B-002 (reflog gate doesn't cover the timing window between commit return and push start) |
| `6f29d49` | coord(mailbox) | director | **Decision REPLY** to operator cycle-8 feature proposal — Q1-Q5 + Path A sequencing ENDORSED (zero counter-refinements; cleanest cross-seat REPLY cycle to date) |
| `e695e81` | **feat(director)** | **operator** | **S15 — CinemaDirector v1.0 substrate skeleton** (Lane A, ~1.5h). NEW `DirectorialIntent` Pydantic model + `llm/director.py` module + `intent_translator()` functional API + JSONL log stub. 2 unit tests pass; 737 → 737 total. |
| `3370eda` | coord(mailbox) | director | **Lane S first-fire: draft scout-request** for S15 held under NEW `coordination/mailbox/draft/` subdirectory (extends sent/seen/archive convention) |
| `a00922b` | chore(mailbox) | director | **Scout-discard pattern** — S15 commit body resolved all 3 scout targets; draft archived without sending. Thorough commit bodies obviate scout cycles. |
| `c425d55` | feat(iterate) | director's implementer | **S16 — directorial iteration endpoint** + `ShotController.regenerate_with_intent` method + 14 tests (12 flag matrix + happy-path + missing-take) |
| `15493c8` | fix(iterate) | director | Address S16 reviewer findings — `_reject_if_project_busy` busy fence + comments + 2 routing tests (target_stage=performance/motion paths) |
| `7f5dea7` | coord(mailbox) | operator | **Lane V #4 verification-report on `c425d55`** — 0 critical / 0 important / 5 minor (F1-F5) + **F0 reviewer-disagreement** on busy-guard omission (mine: pattern-consistent / director's: blocker; director's framing correct). ~189k subagent tokens. |
| `c5a0e94` | fix(iterate) | director | Fold operator Lane V #4 F3 (route param `<sid>` → `<shot_id>`) + F5 (pre-seed-then-overwrite collapse) + REPLY decision file |
| `b806bc7` | feat(iterate-ui) | director's implementer | **S17 — IterationPanel + ReviewStage KEYFRAME_REVIEW wiring** (`CINEMA_DIRECTORIAL_ITERATION` server-side flag). NEW `IterationPanel.tsx` (93 LOC) + `usePipelineState.iterateTake` action |
| `16ce51a` | fix(iterate-ui) | director | Address S17 reviewer findings (director's own internal review cycle) — drop dead props + reset submitting + aria-label |
| `a8bde27` | feat(iterate) | director | **F1 accept-both** — endpoint honors nested `{intent: {...}}` AND flat `{prose, ...}` body shapes via `isinstance(data.get("intent"), dict)` guard. Closes operator Lane V #4 F1. |
| `9c749b7` | chore(domain) | director | Migrate `datetime.utcnow()` → `datetime.now(timezone.utc)` in `project_manager.py` (eliminates 9 deprecation warnings; addresses ARCHITECTURE §16 cosmetic) |
| `0d9bbbf` | docs(arch) | director | Close stale ARCHITECTURE.md §16 entries — datetime cleanup + test count refresh |
| `0862545` | coord(mailbox) | operator | **Lane V #5 — FIRST CC-1 COALESCED** on `7f5dea7..a8bde27` (4-commit range: S17 + F1/F3/F5 folds). 0 critical / 0 important / 4 minor (G1-G4 forward-looking). All Lane V #4 F-advisories verified closed. ~195k tokens. |
| `955be1f` | docs(b-003) | director | **B-003 design exploration** — 5-option analysis (A-E); Option E (gitignore STATE.md + remove amend logic) recommended; M-2 endpoint comment added in iterate handler |
| `f8b4deb` | chore(iterate) | director | **Fold operator Lane V #5 G1+G2** (1-line comments) + advance director seen-cursor (consumed Lane V #5 report); G3 deferred to S18/S20 design, G4 left to operator |
| `2183ccb` | chore(hooks) | director | **B-003 Option E SHIPPED** — gitignore STATE.md + `git rm --cached` + simplify `update-state.sh` 148→102 LoC (remove staged-set check / reflog gate / amend lines). **Closes B-002 + B-003.** Compound `git commit && git push` now genuinely safe; separate-Bash-call workaround RETIRED. v2.1 stale-by-one KNOWN LIMITATION moot. User-authorized via AskUserQuestion modal. |
| `4bf48cd` | docs(handoff) | director | Director-seat cycle-8 transplant — feature-delivery cycle close |
| `74f3f62` | **docs(backlog)** | **operator** | **Seed B-004** — IterationPanel UX polish (m2 Escape-key dismissal + m3 non-JSON 502 status context) from director's own S17 review deferred items; closes operator Lane V #5 G4 commitment |
| THIS COMMIT | docs(handoff) | operator | Cycle-8 operator transplant refresh — Race-ack: S18 implementer subagent in flight at refresh-Write time (unstaged: `cinema/shots/controller.py` + `llm/director.py` + `tests/unit/test_director.py` with verb DSL additions — `tighten_framing` / `match_shot` / `shift_emotion`). Next operator-seat will pick up post-S18-commit. |

(For Cycle 3 ledger entries, see historical section below; cycle 4 was operator's Lane D + S13 Lane V dispatches above.)

---

## (Original historical "What's pending" section follows — preserved for cycle-3-era context but superseded by post-v5-ship queue above)

Sessions 1, 2, 3, 4, 5, 6, 7, 8, 9, 11 all SHIPPED. Session 10 brief shipped (`cefde42`) but implementer not yet dispatched (held for separate Session 10 dispatch by director).

Protocol Bundle v2 SHIPPED (`416d610` + `5e0329d` v2.1). Protocol Bundle v3 SHIPPED (`3340d1f`) — proposal cycle: `749341b` → REPLY `26a0842` → revision `ec1e64e` → ship `3340d1f`. v3 ship folded all working-tree pre-impl edits + held counter bumps.

The canonical "what's next" doc is still `docs/POST-ROADMAP-2026-05-24.md` (last refreshed at `64c7571` post-Monitor; will need re-refresh post-Session-11 + post-v3-ship to surface cycle-4 picks).

This operator handoff covers **HOW** (execution-discipline patterns, accumulated lore). POST-ROADMAP covers **WHAT**.

Cycle-3 immediate queue post-v3-ship:
1. **Session 10 dispatch** — brief at `cefde42`; implementer pending. Director-owned dispatch.
2. **POST-ROADMAP re-refresh** — needed to surface cycle-4 picks (last refresh `64c7571` predates Sessions 9, 11, v2 ship, v3 ship).
3. **PROTOCOL-RULES-LOG SHA update** — operator chore; update any v3-ship placeholder rows (Infrastructure Audits, possibly Rules 9/10) from `_Protocol Bundle v3 ship_` to `3340d1f` per the chicken-and-egg pattern established post-v2.

Open items at this transplant:

- **Push status** — recent pushes have happened; ahead-count varies. Check `git rev-list --count origin/main..HEAD` for exact unpushed.
- **v3 PROTOCOL-RULES-LOG SHA placeholder update** — operator chore; cheap follow-up after v3 ship lands (mirrors `3e57ddf`'s post-v2 SHA update for Rules #7/#8).
- **Next-session dispatch beyond Session 10** — director-owned. No operator-quick-claim candidates currently surfaced (POST-ROADMAP needs re-refresh first).

---

## Established patterns (proven across Sessions 1-8)

### Per-session loop (the orchestration discipline that works)

1. **mark_chapter** with title + summary
2. **TaskCreate × 4** — implementer / spec reviewer / quality reviewer / fix loop
3. **Mark implementer in_progress**
4. **Dispatch implementer subagent** in foreground (Lane B per AGENTS.md)
5. Trust-but-verify the commit (`git log`, `git show --stat`, brief test run)
6. **Dispatch spec reviewer + quality reviewer in parallel** (independent)
7. **Apply IMPORTANT findings** as chore commit (Sessions 2-8 all did this)
8. **Skip MINOR findings** unless trivial OR explicitly worth doing now
9. Background reindex (PostToolUse hook handles this automatically after git commit)
10. Final status report including findings, open items

### Director-operator concurrent operation (codified `ad6cb4f` + extended `ea97d0a`)

**Read first:** `CLAUDE.md` / `AGENTS.md` `# Director-Operator Concurrent Operation`.

Quick summary for operators:

- **Role partition.** Strategic + brief authoring + ADR + push-to-origin + memory writes + codifying discipline rules = director-only (operator may DRAFT discipline + memory, director SHIPS). Counter bumps + transplant handoff updates = operator-only. Implementer dispatch + reviewer dispatch + verification gates + applying minors + closing reports = shared.
- **Signaling.** Narrate before acting on shared tasks: "Dispatching X...". The other party defers when they see the announcement.
- **`git log --oneline -5` precondition.** Run before pre-locating ANY work on shared tasks AND before any state-asserting Write/Edit (handoff docs, status reports, commit bodies). Director may have shipped. Codified twice: rule #1 in `ad6cb4f` (shared-task pre-locating), extended in `ea97d0a` rule #1 (state-asserting writes).
- **Race-acknowledging commit bodies.** When state moves during your work, name the shift in the body. Codified in `ea97d0a` rule #2; examples: `843c102` (state-moved-during-write), `d8bf650` (role-deferral).
- **Counter-bump fold-and-surface.** During active concurrent operation, hold counter bumps for the other party's next natural commit + announce in conversation. Standalone `chore(baseline)` only when truly isolated. Codified in `ea97d0a` rule #3.
- **Git tiebreaker.** If dispatches race, first commit to land wins. Cost: one wasted subagent context.

### Commit shape rules (proven, low-friction)

- Each session: 1-2 main commits (feat + test split for Session 8) + 1 chore-fix commit (if IMPORTANTs)
- Foundation work split when structurally distinct (Session 4: foundation + conversion; Session 6: ErrorBoundary + cascade_metadata; Session 8: feat + test)
- Director parallel commits: appear interleaved; don't coordinate, just notice
- **AGENTS.md/CLAUDE.md auto-counter bumps:** fold-and-surface (rule above)
- **Always include verification output in commit body** (Rule 3 from `ed33035`)
- **Subagent commits:** subagents can stage but not always commit (auto-mode permission gate). Workaround: prompt subagent to `git add` only; main context commits after spot-check.

### File-convention preservation (critical for review-ability)

- **test_cross_controller.py**: plain functions, no pytest classes, `_TESTS` registry at bottom, no conftest fixtures, `_make_*_setup()` helpers, standalone runner support
- **test_workflow_selector.py**: class-based grouping, `pytest.mark.parametrize` for cross-products, no conftest, `pytest.approx` for floats
- **test_cost_tracker.py**: `db_path` fixture uses `tempfile.NamedTemporaryFile(delete=False)`, `pytest.approx` for floats, class-based grouping
- **test_face_validator_gate.py** (Session 7): 4 test classes (TestScoreCandidate, TestShouldHalt, TestNeedsRegenerate, TestSelectBest); parametrized weight cases; boundary asserts via `decision.best.composite`
- **test_project_models.py** (Session 8): mirrors Pydantic model boundary; tests at load/save edge of project_manager.py

### Counter-bump fixpoint (Sessions 5+ observation)

`chore(baseline)` reindexes reach fixpoint in at most 2 commits — see operator-side observation. Don't predict 0-delta from chore-then-reindex; treat each reindex output as new truth.

---

## All findings discovered (the durable knowledge)

### Production bugs fixed during this conversation
1. **`_find_take` omitted `performance_takes`** at `cinema/shots/controller.py:230-235` — broke PERFORMANCE_REVIEW gate (added in `b4dc37b`, ADR-009). Director fixed in `37c9350`.

### Spec-vs-production divergences caught by reviewers
1. **Session 6 `phase_c_ffmpeg.py:96` `attempts` field** — implementer used `sorted(attempted_apis)` (alphabetical) instead of insertion-order (chronological). Root cause: `attempted_apis: set` forces lossy serialization. Director fixed in `c6eaefb` (set → list with dedup-on-append at 5 sites).
2. **Session 7 brief said ~19 tests; implementer landed 19; minors expanded to 23** via parametrize + missing boundary cases (`d8bf650`).
3. **Session 8 `domain/models.py` `extra="allow"` choice** — flagged in `5c4a7c9` POST-ROADMAP refresh as "Session 9 can tighten this" (P1-3 PARTIAL: boundary done, strict mode pending).

### Doc drift fixed during this conversation
1-8. (see prior versions of this handoff; all stable now; ARCHITECTURE.md still needs an LOC sync at next doc-touch session)

### Test fixture bugs fixed
1. **`test_quality_max_overlay::test_schema_covers_comfycontrols_and_halt_knobs`** — missing `max_quality_parallel_workers` after ADR-010.
2. **6 `test_project_manager.py` failures** — `tmp_projects_dir` autouse fixture monkey-patched root-level `project_manager` shim instead of `domain.project_manager.PROJECTS_DIR`.

### Findings dispositioned in POST-ROADMAP-2026-05-24.md (5c4a7c9 refresh)

- `face_validator_gate.{should_halt, score_candidate, needs_regenerate}` — **RESOLVED** (Session 7).
- Pydantic on project.json — **PARTIAL** (Session 8 boundary; Session 9+ for caller refactor + strict mode).
- Monitor.tsx cascade_metadata wiring — top-3 #1 for cycle-3.
- P4-3 four-gate review fatigue — top-3 #2 for cycle-3.
- `domain.scene_decomposer._coerce_to_valid_keys` — important-deferred.
- `lip_sync._sync_gate_settings` — important-deferred.
- `datetime.utcnow()` at `domain/project_manager.py:126,864` — low-priority (still warning).
- `workflow_selector.py:400` `close_up` doc drift — low-priority.
- Remaining `print()` sites (`audio/`, `performance/`, `llm/`, `phase_c_*`, `quality_max.py`, `lip_sync.py`, `web_server.py` startup banner).
- Logging deferred MINORs: `clip` vs `stitched_path` field naming — **semantically different**; do NOT unify.

### Reviewer false-positive patterns observed
1. **Session 2 spec reviewer** — claimed "uncommitted `_find_take` fix exists" (conflating HEAD post-`37c9350` with cfbffb9 state).
2. **Session 4 spec reviewer** — claimed 40 prints; actual 36.
3. **Session 6 spec reviewer** — wiring-gap framing implied "missed prop" but was structural (`ShotState` doesn't carry `cascade_metadata`, only `TakeRecord` does).
4. **Operator self-citation in draft #2** — initially cited `d8bf650` as canonical "state-moved-during-write" example, but verification showed it's actually "role-deferral-named" (different sub-pattern). Caught by operator's own application of rule #1 before director ship. Director refined both cites to distinguish patterns.

### Subagent environment caveats (KNOWN GOTCHAS)
1. **GitNexus MCP not reachable in subagent env** — fall back to grep + Read per CLAUDE.md guidance.
2. **`git commit` blocked by auto-mode permission classifier** in some subagents — workaround: subagent stages via `git add` only; main context commits after spot-check.

### Director-side patterns observed
- Director shipped 20+ parallel commits across this conversation (bugs/drifts, rule codification, handoff updates, counter bumps, full session dispatches in Sessions 5-8, two transplant docs).
- `aa1e748` codified bug-fix-inline pattern from `37c9350` as Lane A authority.
- `ad6cb4f` codified multi-agent coordination protocol AFTER an in-session race demonstrated the need (both director + operator pre-located Session 6 `phase_c` fix simultaneously).
- `ea97d0a` extended `ad6cb4f` with state-asserting writes precondition + race-acknowledging commit bodies + counter-bump fold-and-surface — operator drafted, director shipped with 1 cite-distinction refinement.
- Director cycle-2 transplant `60001d9` was prepared as a context warning but director kept shipping past it (Sessions 7 minors + 8 full + discipline ship + POST-ROADMAP refresh + push). Expect this pattern: transplants are insurance, not hard exits.

---

## Open questions for director (held over)

1. ~~**Push commits to `origin/main`?**~~ RESOLVED — pushed at `5c4a7c9` moment.
2. **Next dispatches (cycle-3):**
   - Monitor.tsx cascadeMetadata wiring (POST-ROADMAP top-3 #1, operator-quick-claim)
   - P4-3 four-gate review fatigue (POST-ROADMAP top-3 #2)
   - Session 9 caller refactor + strict mode (POST-ROADMAP top-3 #3)

---

## Baseline state snapshot at transplant

State at the moment of cycle-8 close handoff WRITE. Director-seat's S18 implementer subagent is in flight (unstaged changes — see Race-ack in TL;DR). Always re-run the cold-start checklist for current truth.

```
$ git log --oneline -3
74f3f62 docs(backlog): seed B-004 — IterationPanel UX polish (m2 Escape-key + m3 non-JSON status context) from S17 reviewer-deferred items
4bf48cd docs(handoff): director-seat cycle-8 transplant — feature-delivery cycle close
2183ccb chore(hooks): B-003 Option E — gitignore STATE.md + simplify update-state.sh; close B-002+B-003

$ git status
On branch main
Your branch is ahead of 'origin/main' by 1 commit.   # B-004 seed not yet pushed (director-seat picks up next session per v5 §Sh)
Changes not staged for commit:
  modified: cinema/shots/controller.py    # director's S18 implementer in flight (verb DSL — tighten_framing / match_shot / shift_emotion)
  modified: llm/director.py               # same
  modified: tests/unit/test_director.py   # same

$ .venv/bin/python -m pytest tests/unit/ -q | tail -1
737 passed, 3 skipped, 11 warnings, 10 subtests passed
(per cycle-8 close commit body — pre-S18; +0 from S15 +14 from S16 +0 from S17-frontend = 715 → 737)

$ .venv/bin/python scripts/ci_smoke.py
OK

$ cat coordination/mailbox/seen/operator.txt
2026-05-25T15:49:12Z   # consumed director's Lane V #4 decision-REPLY at 2026-05-25T15-49-12Z

$ ls coordination/mailbox/sent/
2026-05-25T14-42-02Z-operator-to-director-query.md             # cycle-8 feature proposal query
2026-05-25T14-56-42Z-director-to-operator-decision.md          # Q1-Q5 + Path A ENDORSED
2026-05-25T15-37-08Z-operator-to-director-verification-report.md  # Lane V #4
2026-05-25T15-49-12Z-director-to-operator-decision.md          # Lane V #4 dispositions REPLY
2026-05-25T16-19-27Z-operator-to-director-verification-report.md  # Lane V #5 CC-1 coalesced
```

**STATE.md note:** as of B-003 Option E (`2183ccb`), STATE.md is gitignored (local-only artifact regenerated on disk by hook after HEAD moves; no amend). The v2.1 KNOWN LIMITATION (HEAD field stale by one SHA) is moot. Hook is now 102 LoC (was 148). Compound `git commit && git push` is genuinely safe; separate-Bash-call workaround retired (see new operator memory: `feedback_compound_commit_push_safe_post_b003.md`).

**S18 in-flight tail:** when S18 lands as a feat commit, it triggers operator Lane V #6 per Rule #9 + R-V1. Recommended approach: read S18's commit body for scope; CC-1 coalesce only if other tightly-coupled commits land in the same window (e.g., S18 self-fix-on-own-findings); otherwise per-commit dispatch. Director-seat said in cycle-8 handoff "scout-request opt-in (no scout this dispatch — substrate is well-defined)" so no pre-S18 scout.

LOC drift advisory: `web_server.py` (~1770+ LOC post-S16 + F1 + F3 rename), `cinema_pipeline.py` (~1113 LOC, P1-2 orchestrator extraction still deferred), `cinema/shots/controller.py` (~1290+ LOC post-S16 `regenerate_with_intent`), `domain/project_manager.py` (datetime migration cleaned). ARCHITECTURE.md was synced in `0d9bbbf` — current.

---

## Time accounting (this conversation)

| Phase | Approx hours |
|---|---|
| Orientation + audit (Phase 0) | 2.5 |
| Session 1 (CI) | 1.5 |
| Session 2 (ReviewController tests) | 1.5 |
| Session 3 (workflow_selector tests) | 1.5 |
| Session 4 (logging) | 2.5 |
| Session 5 (cost tracker) | 1.0 (director-shipped; operator audit) |
| Session 6 (frontend resilience + cascade) | 1.5 (director-driven; operator pre-locate + memory + handoff) |
| Post-roadmap part 1 (discipline section #1, fixpoint, handoff refresh) | 1.0 |
| Session 7 (face_validator_gate; director cycle-2) | 1.5 (director-driven; operator audit + handoff stale-fix mid-flight) |
| Discipline section #2 (state-asserting + race-ack + fold-and-surface) | 1.0 (operator draft → director ship + refine) |
| Session 8 (Pydantic schema; director cycle-2) | 1.5 (director-driven; operator standby) |
| Post-cycle-3 handoff refresh (this commit) | 0.5 |
| **Total** | **~17 hours** |

Subagent dispatch saved an estimated 7-10 hours across Sessions 2-8.

---

*Operator-seat handoff refreshed at HEAD `d66690f` (v5 ship; cycle-6 close). Branch 0 ahead of `origin/main` (push fully caught up). Sessions 1-14 + Protocol Bundles v2/v3/v4/v4.1/v5 ALL SHIPPED. Per v5 §P1 ("two seats of one team"), this is operator-seat's handoff to the next operator-seat instance; director-seat picks up from `HANDOFF-director-transplant-2026-05-25-cycle6.md` (post-v5-ship cycle-6 close; **race-acked per Rule #5: director-seat authored their cycle-6 handoff during this operator-seat handoff's Write window — both refresh files are post-v5-ship; cycle-5 director handoff is now historical**). Cold-start checklist above is fully v3 §F freshness-check compliant. Run `git log --oneline -5` before any pre-locating on shared-task work AND before any state-asserting write (Rule #4); immediately before commit, re-run + check mailbox (Rule #7). User-direction overrides agent discretion at any point (Rule #8 authority precedence + v5 P1 user-as-principal). Welcome to one-team mode.*
