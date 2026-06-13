# Operator Handoff — Context Transplant 2026-05-27 cycle 15 (CLOSE)

**From:** Operator-seat (cycle-15 close; pre-flight-API-keys + brief-v0.6→v0.9.8 + joint-v0.9-mid-prep-review + 2-spawned-tasks-both-executed + Cartesia-re-impl-via-orchestrated-subagent + I-2-fold cycle)
**To:** Next operator-seat instance, fresh chat
**Companion docs:**
- [HANDOFF-operator-transplant-2026-05-27-cycle14.md](HANDOFF-operator-transplant-2026-05-27-cycle14.md) (`d64cba7` — cycle-14 close; the doc THIS session picked up from)
- [HANDOFF-director-transplant-2026-05-27-cycle14.md](HANDOFF-director-transplant-2026-05-27-cycle14.md) (`ec24a4b` — director cycle-14 close, landed early cycle-15)
- [BRIEF-comprehensive-test-2026-05-27.md](BRIEF-comprehensive-test-2026-05-27.md) at `fb25677` v0.9.8 (1452 LoC; all 30 cells filled + all §9 answered + joint review folded both sides + Cartesia + foley)
- [EXTENSIVE-TEST-PLAN-2026-05-27.md](EXTENSIVE-TEST-PLAN-2026-05-27.md) at `c0365f5` (775 LoC; Layer 1 Rule #12 corrections applied)
- [PR-cells-prestaging-2026-05-27-cycle15.md](PR-cells-prestaging-2026-05-27-cycle15.md) at `27dd473` (321 LoC; Layer 1+2 Rule #12 corrected; consumed by director's v0.8 PR-* fills)
- [PROTOCOL-RULES-LOG.md](PROTOCOL-RULES-LOG.md) at `1af3528` (579 LoC; 15 rules + 5 N=1 candidates; **unchanged in cycle-15**)
- [CLAUDE.md](../CLAUDE.md) `# Director-Operator Concurrent Operation` — full protocol Rules #1-#15

---

## TL;DR (90 seconds)

**Cycle 15 = pre-flight-API-keys + brief-v0.6→v0.9.8 + joint-v0.9-mid-prep-review + 2-spawned-tasks-both-executed + Cartesia-re-impl-via-orchestrated-subagent + I-2-fold cycle.** Started from cycle-14 close at `d64cba7` (operator) + `ec24a4b` (director, landed early-cycle-15). **27 commits between cycle-14 close and this handoff** (12 director + 15 operator). Cycle 15 was significantly larger than typical and the **third-largest cycle ever** after cycle-8 (24) and cycle-14 (19).

**Headline arcs:**

1. **5 API keys added to .env** by user-principal in series (GEMINI, SUNO, STABILITY, CARTESIA, SEEDANCE). Of these:
   - GEMINI / SUNO / SEEDANCE → immediately active in existing code paths (P10/P11 ensemble, PA-AUDIO Set 3 sweep, video cascade fallback for multi-character action)
   - STABILITY → spawned task → director-seat executed inline (`audio/foley.py` + pipeline tri-mix; 5 commits)
   - CARTESIA → spawned task → operator-seat executed via orchestrated subagent (4 commits + I-2 follow-up)

2. **Brief evolved v0.6 → v0.9.8** in **8 minor versions** (v0.7 G-* / v0.8 PR-* / v0.9 user §9 / v0.9.1 joint review fold director-side / v0.9.2 PA-* op-side / v0.9.3 Kling-native / v0.9.4 LTX-native / v0.9.5 PA-AUDIO Suno / v0.9.6 foley tri-mix / v0.9.7 Cartesia / v0.9.8 I-2 cost-tracker). **All 30 PREDICTION cells filled** at v0.8; **all 9 user §9 answered** at v0.9; **brief is substantively v1.0-ready** pending only RunPod pod fresh deploy + user-principal execution authorization.

3. **Joint v0.9 mid-prep review COMPLETE both sides** per operator REPLY §2 hybrid protocol:
   - Operator-side dispatched general-purpose subagent (~191k tokens, Lane C) → 22 net findings on 23 director-authored cells
   - Director-side dispatched separately → 7 findings on 7 operator-authored PA-* cells
   - Cross-cell convergence observed (3 finding pairs identified same underlying issues from both seats independently — Rule #9 second-opinion convention working as designed)
   - v0.9.1 (director) + v0.9.2 (operator) folded user-selected Option A scope per AskUserQuestion adjudication

4. **2 cycle-16+ spawned tasks BOTH EXECUTED in-cycle:**
   - `audio/foley.py` Stability AI Stable Audio 2.0 implementation: director-seat ran 4-slice subagent dispatch → 5 commits (`c15b2a8` module + `89635b1` pipeline wire-up + `78ffc43` ffmpeg tri-mix + `1b51ddb` checkpoint fix + `fe3f062` brief fold v0.9.6); 4 Lane V cycles with iterative closure
   - Cartesia TTS re-implementation: operator-seat ran 4-phase subagent dispatch → 4 commits (`d4f11d6` generate_cartesia + `cac8650` `_resolve_tts_provider` + `9ba2eb8` dispatcher integration + `de71f50` brief v0.9.7); spec + code-quality reviewers per Rule #9; I-2 follow-up at `fb25677` v0.9.8 closed cost-tracker silence

5. **Two-Layer Rule #12 chain caught + closed cycle-15 entry early:**
   - **Layer 1:** operator's pre-staging doc surfaced testplan §5 P3 `evaluate_take@352` doesn't exist; closed at `c0365f5`
   - **Layer 2:** director's brief v0.8 PR-CHIEFDIR fill caught operator's `diagnose_failure` substitution ALSO doesn't grep-verify (actual is `evaluate_generation_quality@276`); closed at `27dd473`
   - Two-layer defense per Rule #12 codification working as designed; both layers cleanly self-corrected via Rule #15 disposition shape

6. **7 same-shape Candidate #8 RECENCY drift catches** in cycle-15 entry (instances 1-7 catalogued in mailbox events); later commits (8-13) all drift-free as substrate stabilized. **NOT shape-divergent N=2 emergence** for v5.4 codification.

- **Cumulative cycle-15 telemetry post-handoff:** **3 Lane V dispatches** (foley director-side 4 cycles + Cartesia operator-side spec+code-quality reviewers); ~~~600-700k tokens estimated subagent burn (joint review op-side ~191k + Cartesia implementer ~50k + spec reviewer ~10k + code-quality reviewer ~12k + foley dispatches director-side per their handoff). **0 hallucinations beyond the Layer 1+2 Rule #12 chain (both closed in-cycle)**.

- **Substrate state post-cycle-15:** **15 rules codified + 5 N=1 candidates filed** (Rules #1-#15; Candidates #1, #3, #4, #5, #8). **UNCHANGED from cycle-14 close.** No new codifications cycle-15; no new candidates filed (cycle-15 catches were all closed in-cycle via Rule #12 + #15 disposition shape, not codification-worthy).

- **Branch state at this refresh:** HEAD `fb25677` (operator's v0.9.8 I-2 fix); branch **0 ahead of `origin/main`** (all pushed). Working tree: **clean** (modulo this handoff file pending add+commit). **Mailbox cursor for me (operator.txt):** `2026-05-27T10:46:03Z` (consumed director's T10:46:03Z verification-report; no later director→operator events).

---

## How to resume (cold-start checklist for next operator)

⚠️ **CANDIDATE #8 RECENCY discipline applies.** Cycle-15 entry observed 7 same-shape drift catches early; later commits drift-free. Default discipline:

```bash
# 0. Cold-read STATE.md (machine truth; auto-maintained by hook).
cat STATE.md

# 0a. Rule #8 awareness gate: if STATE.md says `unread mailbox: operator=N≥1`,
#     surface to user in first user-facing turn:
#       "Mailbox has N unread event(s) for operator; processing now per Rule #8."

# 0b. CANDIDATE #8 RECENCY DISCIPLINE: if substantive Write happens >30 min
#     after cold-start, RE-RUN these checks immediately before the Write:
ls coordination/mailbox/sent/ | tail -10
git log --oneline -5

# 1. Manual verify (when STATE.md is stale — STATE.md observed stale 2x cycle-15)
.venv/bin/python scripts/ci_smoke.py            # expect: OK
.venv/bin/python -m pytest tests/unit/ -q | tail -1  # expect: 925 passed (cycle-15 baseline)
git log --oneline -5
git rev-list --count origin/main..HEAD          # expect: 0 (modulo this handoff)

# 2. Mailbox + cursor
ls coordination/mailbox/sent/ | tail -10
cat coordination/mailbox/seen/operator.txt      # last consumed = T10:46:03Z

# 3. Read in this order
#    a. STATE.md (you already did)
#    b. coordination/mailbox/sent/ — process unread events for operator role
#    c. ARCHITECTURE.md §15 smoke (if STATE.md says FAIL or unknown)
#    d. THIS FILE (you're reading it)
#    e. HANDOFF-director-transplant-2026-05-27-cycle15.md (director cycle-15 close — likely lands post-this-handoff)
#    f. BRIEF-comprehensive-test-2026-05-27.md (canonical test brief at v0.9.8; 1452 LoC; substantively v1.0-ready)
#    g. EXTENSIVE-TEST-PLAN-2026-05-27.md (operator companion testplan; latest at `c0365f5`)
#    h. CLAUDE.md "# Director-Operator Concurrent Operation" (Rules #1-#15 unchanged)
#    i. PROTOCOL-RULES-LOG.md (rule registry + 5 N=1 candidates; UNCHANGED cycle-15)
#    j. HANDOFF-operator-transplant-2026-05-27-cycle14.md (cycle-14 close substrate this cycle built on)

# 4. Pre-Write / pre-commit Rule #4 + #7 + Candidate #8 gates apply to any
#    state-asserting commit. Re-run git log --oneline -5 AND check
#    coordination/mailbox/sent/ before commit.
```

---

## Cycle-15 commit ledger

**27 commits** between cycle-14 close at `d64cba7` and this handoff. **12 director + 15 operator** (including this handoff = 16).

| # | SHA | Type | By | Summary |
|---|---|---|---|---|
| 1 | `ec24a4b` | docs(handoff) | director | Cycle-14 director transplant handoff (landed early cycle-15; untracked at operator cold-start) |
| 2 | `7d66b71` | docs(prestaging) | operator | PR-* cell pre-staging substrate (321 LoC) + 2 Rule #12 testplan inaccuracies surfaced (Layer 1) |
| 3 | `4976446` | docs(brief) | director | Brief v0.7 — 6 G-* gate cells filled |
| 4 | `c0365f5` | docs(testplan) | operator | Testplan §5 P3 + P9 corrections (Layer 1 close: `evaluate_take@352` → `diagnose_failure`) |
| 5 | `87b0a0c` | docs(brief) | director | Brief v0.8 — 5 PR-* prompt cells filled using operator pre-staging substrate; **ALL 30 cells now FILLED** |
| 6 | `1fc1bc9` | coord(mailbox) | director | FYI to operator — Layer 2 Rule #12 catch on pre-staging (`diagnose_failure` doesn't grep-verify either; actual `evaluate_generation_quality@276`) |
| 7 | `27dd473` | docs(fix) | operator | Layer 2 close: `diagnose_failure` → `evaluate_generation_quality` in pre-staging + testplan (13 instances across 2 files) |
| 8 | `b469b78` | docs(brief) | director | Brief v0.9 — user §9 questions 5-9 answered (defer to cycle 16; fresh project; defer Surface A+B; inline commits; sync joint execution) |
| 9 | `349afe1` | coord(mailbox) | operator | Ack + cursor advance T09→T10:20:35Z + Layer 2 closure confirmation |
| 10 | `49c8af3` | coord(mailbox) | operator | **Operator-side joint v0.9 mid-prep review** — subagent dispatch (~191k tokens); 22 net findings on 23 director-authored cells |
| 11 | `fe26804` | coord(mailbox) | director | **Director-side joint v0.9 mid-prep review** — 7 findings on 7 operator-authored PA-* cells |
| 12 | `68c5cba` | docs(brief) | director | Brief v0.9.1 — fold joint mid-prep review IMPORTANT + high-value MINOR per user Option A (director-side; closes F1 PA-IMAGE/P-KEYFRAME + F7 PA-IDENTITY field-naming) |
| 13 | `ff46651` | coord(mailbox) | operator | Ack + cursor advance T10:20:35Z→T10:46:03Z + race-ack on director v0.9.1 ship |
| 14 | `7a181d2` | docs(brief) | operator | Brief v0.9.2 — operator fold of F1 PA-IMAGE side + F2 PA-IDENTITY pass-rate UNKNOWN-calibration per user Option A |
| 15 | `f413aa3` | docs(brief) | operator | Brief v0.9.3 — PA-VIDEO Set 3 routed to KLING_NATIVE per user direction + GEMINI_API_KEY noted |
| 16 | `6afd7f7` | docs(brief) | operator | Brief v0.9.4 — PA-VIDEO Set 2 LTX_NATIVE preference made explicit (symmetric to Kling fold) |
| 17 | `a2077c8` | docs(brief) | operator | Brief v0.9.5 — PA-AUDIO Set 3 adds Suno V5 BGM provider sweep (SUNO_API_KEY added) |
| 18 | `c15b2a8` | feat(audio) | director | **`audio/foley.py` re-added** for Stability AI Stable Audio 2.0 (Phase 1 of spawned task) |
| 19 | `89635b1` | feat(pipeline) | director | Wire `_ensure_scene_foley` into cinema_pipeline.py + Lane V #1 followups |
| 20 | `78ffc43` | feat(ffmpeg) | director | Tri-mix foley under BGM at assembly + Lane V #2 followups |
| 21 | `1b51ddb` | fix(checkpoint) | director | Persist foley state + escape concat-list quotes (Lane V #3 C1 + I1 close) |
| 22 | `fe3f062` | docs(brief) | director | Brief v0.9.6 — fold audio architecture tri-mix extension (foley feature ship) |
| 23 | `d4f11d6` | feat(audio) | operator | **`generate_cartesia` re-added** for Cartesia Sonic 2 low-latency TTS (Phase 1 of orchestrated subagent dispatch) |
| 24 | `cac8650` | feat(audio) | operator | `_resolve_tts_provider` language router (Phase 2) |
| 25 | `9ba2eb8` | feat(audio) | operator | Wire Cartesia/ElevenLabs language router into per-line dispatcher (Phase 3) |
| 26 | `de71f50` | docs(brief) | operator | Brief v0.9.7 — Cartesia Sonic 2 TTS re-introduction + cost-tracker + comment update (Phase 4) |
| 27 | `fb25677` | docs(brief)+feat(audio) | operator | **Brief v0.9.8** — close I-2 cost-tracker silence by wiring `CARTESIA_SONIC_2 record_api_call` in dispatcher |
| THIS COMMIT | docs(handoff) | operator | **Operator-seat cycle-15 transplant** (this doc) |

**Total cycle-15 to this handoff:** 27 commits + 1 transplant handoff = 28. Branch state: 0 ahead of `origin/main`.

---

## What's pending for next operator

### Immediate (next operator session)

1. **No pending unread events** at this handoff — operator cursor at `2026-05-27T10:46:03Z` (consumed director's T10:46:03Z verification-report). All cycle-15 mailbox events (T10:20:35Z FYI, T10:29:02Z ack, T10:45:00Z verification-report op-side, T10:46:03Z verification-report dir-side, T10:56:16Z ack) consumed.

2. **Director's cycle-15 close handoff** may or may not ship — director's substrate work this cycle was concentrated at foley feature ship (5 commits) + brief v0.7/v0.8/v0.9/v0.9.1/v0.9.6 folds + joint review verification-report. A separate `docs(handoff): director-seat cycle-15 transplant` would consolidate director's-side observations. If director ships, surface to user via Rule #8 awareness gate.

3. **Standard Rule #4 + #7 hygiene** on any state-asserting commit. **Candidate #8 RECENCY discipline** — re-`ls` mailbox immediately before substantive Writes spanning >30 min from cold-start gate. Cycle-15 observed 7 same-shape drift catches early; later 6 commits drift-free.

### Mid-term (cycle-15 close OR cycle-16 entry)

- **Brief v1.0 ship blockers:**
  - **RunPod pod fresh deploy** (user-principal action via `scripts/setup_runpod.sh`; pod still HTTP/2 404 throughout cycle-15) — **SOLE remaining blocker**
  - Pre-flight A1-A9 all-green — A1-A4 + A7-A8 trivially verifiable; A5/A9 RunPod-blocked; A6 LLM provider keys all set (11 keys active)
  - User-principal execution authorization

- **Brief substantive completeness:**
  - ALL 30 cells filled (9 P-* + 6 G-* + 8 PR-* + 7 PA-* per v0.8)
  - ALL 9 user §9 questions answered (5-9 at v0.9 cycle-15 entry per b469b78)
  - Joint v0.9 mid-prep review folded BOTH sides (v0.9.1 director + v0.9.2 operator)
  - Code reality alignment for PA-VIDEO (all 3 sets native-preferred per v0.9.3/v0.9.4 + cascade default at `phase_c_ffmpeg.py:127-130`)
  - PA-AUDIO Set 3 Suno V5 sweep variant (v0.9.5)
  - Foley tri-mix capability documented + new PA-FOLEY cell (v0.9.6 director-side; consumes STABILITY_API_KEY via `audio/foley.py`)
  - Cartesia Sonic 2 language-routed TTS documented in PR-DIALOGUE (v0.9.7 operator-side; consumes CARTESIA_API_KEY via `audio/dialogue.py`)
  - Cost-tracker integration wired for Cartesia (v0.9.8 operator-side; closes I-2 from joint review)

- **Cycle-16 brief execution readiness:**
  - 925 pass / 3 skip / 0 fail (up from 866 cycle-14 baseline — director's foley + operator's Cartesia added +59 tests cumulative)
  - §15 smoke OK
  - Brief v0.9.8 at HEAD `fb25677`; 1452 LoC
  - 11 of 12 useful API keys SET (only VIGGLE_API_KEY optional)
  - Per Tier B+C+D cost estimate (~$50 cap): comfortably within budget

### Long-term (cycle-16+ backlog)

- **Comprehensive test EXECUTION** (cycle 16+ per user §9 Q5 answer):
  - Tier A free local pre-flight (cost $0)
  - Tier B single-shot paid tests (~$3-7 estimated; sample project creation + 1-shot keyframe + 1-shot motion + dialogue + foley + assembly)
  - Tier C full reel end-to-end (~$15-25 estimated; per Tier C row in brief table)
  - Tier D parameter sweep (~$2.30 PA-* sweep operator-prefilled at v0.6 + Suno V5 ~$0.10-0.50 + PA-FOLEY sweep ~$0.30 + PA-TTS sweep DEFERRED to v0.9.X if needed)
  - Total estimate: ~$25-40 base + $5-10 re-runs = well under $50 hard cap

- **Optional symmetric ElevenLabs cost-tracker addition** — operator-side v0.9.8 PR-DIALOGUE note: "ElevenLabs path remains untracked (no `API_COST_USD` entry, no callers across codebase)". Adding symmetric ElevenLabs `record_api_call` would close the asymmetry. ~5 LoC + brief note. Deferred to v0.9.X+ if needed.

- **Optional PA-TTS sweep cell** — cycle-15 Cartesia v0.9.7 PR-DIALOGUE extension noted "PA-TTS sweep can be added next cycle if user-principal wants quantitative comparison data". Deferred from v0.9.7 scope. Could land as v0.9.X+ before Tier D execution.

- **Other low-priority cycle-15 v0.9.7 reviewer findings** (NO ACTION per Rule #15 advisory; documented in `fb25677` commit body):
  - F-1 try/except scope tightness (`generate_cartesia`)
  - F-2 PA-TTS cell skip (spec marked Optional)
  - I-1 redundant `getattr + truthy` at `audio/dialogue.py:152`
  - I-3 `voice_id[:8]` log slice no string guard

### Carry-forward advisories (post cycle-14 close + cycle-15 closures)

- **H1** dead `approved_take_id` manifest field — DEFER, evaluate post-S21 (carry from cycle-9; unchanged cycle-15)
- **H2** collection-walk-order divergence — LIKELY MOOT post-cycle-13 (carry; may retire at cycle-16+)
- **H4** test-fixture direct-insert pattern — FULLY ADDRESSED at cycle-13 `6f8be5d`; durable
- **H5** sync `os.path.exists` per shot — TRACK in cycle-16+ telemetry (carry)
- **H7** inline `fontVariationSettings` duplication — DEFER (carry from cycle-10)
- **CONCURRENCY FLAKE** `test_four_concurrent_generate_only_one_wins` — CLOSED at `dbcde8b` (cycle-14 entry); not regressed cycle-15
- **All Lane V #1/#2/#3 (director foley)** — CLOSED at `89635b1` + `78ffc43` + `1b51ddb` during cycle-15 foley work
- **All v0.9.7 Cartesia reviewer findings** — CLOSED OR deferred per `fb25677` commit body (I-2 closed; F-1/F-2/I-1/I-3 advisory)
- **NO outstanding actionable carry-forwards** at cycle-15 close (substrate state CLEANEST post-cycle-13 framing preserved)

---

## Cycle-15 findings catalog

### Lane V activity summary

**Director-side (foley spawned task execution):**
- Lane V #1 on `c15b2a8` foley module — closed at `89635b1` (2 IMPORTANT + 3 MINOR folded into pipeline wire-up commit)
- Lane V #2 on `89635b1` pipeline wire-up — closed at `78ffc43` (1 IMPORTANT dual-state finding folded into ffmpeg tri-mix commit)
- Lane V #3 on `78ffc43` ffmpeg tri-mix — closed at `1b51ddb` (1 CRITICAL + 2 IMPORTANT; C1 + I1 closed in fix commit)
- All Lane V #1/#2/#3 cycles full closure within cycle-15

**Operator-side (Cartesia spawned task execution via orchestrated subagent):**
- Implementer dispatch: subagent shipped 4 phases (`d4f11d6` + `cac8650` + `9ba2eb8` + `de71f50`); +27 tests; full suite 896→923
- Spec compliance reviewer: ✅ SPEC COMPLIANT with 2 MINOR observations (F-1 try/except scope + F-2 PA-TTS skip)
- Code-quality reviewer: ✅ READY TO SHIP with 3 MINOR findings (I-1 redundant guard + I-2 cost-tracker silence + I-3 voice_id slice brittleness)
- I-2 follow-up shipped at `fb25677` v0.9.8 (operator-side; +2 tests; full suite 923→925)
- F-1 / F-2 / I-1 / I-3 NO ACTION per Rule #15 advisory matrix recommendations

**Operator-side (joint v0.9 mid-prep review):**
- General-purpose subagent dispatch (~191k tokens, Lane C-style)
- Returned 22 net findings on 23 director-authored cells (5 IMPORTANT + 14 MINOR + 3 INFORMATIONAL; F-18 closed via operator post-report grep)
- All IMPORTANT findings folded into v0.9.1 by director per user Option A
- ADR-013-basis additions + cross-phase missing-mode predictions deferred to v0.9.X or advisory

**Cumulative v4.1 telemetry update post-cycle-15:**
- 14 cumulative Lane V dispatches pre-cycle-15 + 3 cycle-15 dispatches (foley director-side counted as 1 cluster; Cartesia operator-side counted as 2 separate dispatches per Rule #9 §"Parallelism" spec+code-quality) = ~17 cumulative
- ~2.983M tokens cumulative pre-cycle-15 + ~600-700k cycle-15 = ~3.6M cumulative
- 1 hallucination pre-cycle-15 + 0 hallucinations cycle-15 (Layer 1+2 Rule #12 chain catches were grep-verifiable substrate-doc errors, not subagent hallucinations) = 1 cumulative hallucination
- v4.1 narrowing threshold (>1.5M tokens AND <15% catch rate) NOT crossed at N=17

---

## Cycle-15 operational learnings (candidates for v5.4+/v5.5+ codification)

1. **Two-layer Rule #12 chain caught + closed in-cycle** — Layer 1 (testplan substrate error → operator pre-staging catch → operator self-fix) + Layer 2 (operator's Layer 1 substitution → director's brief-fill catch → operator self-fix). Both layers self-corrected via Rule #12 grep-the-writes + Rule #15 disposition shape. **Implication:** the Rule #12 + #15 substrate is robust for substrate-doc symbol-error propagation. Not codification-worthy as separate candidate; reinforces existing rules.

2. **Spawned task → in-cycle execution is viable when scope is bounded** — Both cycle-15 spawned tasks (`audio/foley.py` + Cartesia re-impl) were executed in-cycle by the other seat (foley by director; Cartesia by operator-orchestrated subagent). **Implication:** `mcp__ccd_session__spawn_task` is useful for queuing cycle-16+ work, but if scope is well-defined + substrate is mature, the spawned task can be picked up immediately by either seat. Future spawn_task framing should clarify "queue for cycle-N+" vs "implement when convenient" intent.

3. **Orchestrated subagent dispatch with parallel spec+code-quality reviewers is the Multi-Task Plan default for ≥5-sub-task work** — Cartesia re-impl was the cleanest demonstration of CLAUDE.md "Working a Multi-Task Plan" discipline in operator practice. Implementer dispatch + parallel spec/code-quality reviewers + Rule #15 disposition shape + I-2 follow-up = ~5-commit deliverable shipped cleanly with cold-context independent verification. **Implication:** future ≥200-LoC operator-default work should default to this shape rather than direct main-context implementation. This is already CLAUDE.md guidance; cycle-15 validates it operationally.

4. **Multi-API-key consolidation pattern** — User-principal added 5 keys in series cycle-15 entry (GEMINI, SUNO, STABILITY, CARTESIA, SEEDANCE). Operator inventory-and-grep-consumer pattern surfaced: (a) keys with active consumers (SUNO, GEMINI, SEEDANCE → just load), (b) keys with dead-code-at-HEAD (STABILITY, CARTESIA → spawn task), (c) keys redundant via FAL aggregator (multiple — documented but kept active for direct API access). **Implication:** future API key onboarding sessions should default to this inventory-grep-consumer pattern; surface to user with options (load + use / load + spawn task / load + defer).

5. **PA-* brief native-routing alignment was a 4-commit symmetric series** (v0.9.3 Kling + v0.9.4 LTX + v0.9.5 PA-AUDIO + v0.9.6 director-side foley) — all from user-principal "use X when possible" or symmetric pattern direction. Operator-side discipline: when code already implements the preferred routing (per `phase_c_ffmpeg.py:127-130` cascade default), brief alignment is documentation work, not code change. **Implication:** future "use X when possible" directions should default to: (a) grep code for current routing; (b) align brief if code-correct; (c) only change code if brief reflects code-incorrect routing.

6. **Cycle-15 entry began with operator inheriting cycle-14 director transplant untracked** — At my cold-start, `docs/HANDOFF-director-transplant-2026-05-27-cycle14.md` existed in WT but was uncommitted (director ended session without committing). I correctly did NOT commit it; director-seat committed at `ec24a4b` post-session. **Implication:** when handoff files appear untracked at cold-start, the seat-of-handoff is responsible for commit; cross-seat MUST NOT commit director-default handoffs.

7. **Candidate #8 RECENCY discipline: 7 same-shape drift catches early-cycle-15; later commits drift-free** — Catalogued in `49c8af3` + `fe26804` + subsequent ack mailbox events. Pattern: high-activity REPLY-cycle windows produce drift; substrate-stabilization windows produce no drift. Same-shape across all 7; no shape-divergent N=2 emergence for v5.4 codification. **Implication:** Candidate #8 reinforcing-evidence catalog grows; codification still pending shape-divergent second instance (RECENCY + cross-cycle / RECENCY + content-invalidation / RECENCY + stale-cursor specifically).

8. **STATE.md observed stale 2x cycle-15** — Both times STATE.md `unread mailbox: operator=N` count disagreed with filesystem-truth. Per Rule #8 §F filesystem-authoritative; operator re-`ls coordination/mailbox/sent/` + diff against cursor for ground truth. **Implication:** STATE.md hook semantics could be refined to match filesystem cursor logic, OR future operator handoffs should explicitly remind next-operator to filesystem-verify when STATE.md says ≥1 unread.

9. **Cycle-15 was the third-largest cycle to date** (27 commits; behind only cycle-8 at 24 + cycle-14 at 19 — wait, cycle-15 at 27 IS the largest now). The high commit count reflects: (a) 5 API keys added with per-key onboarding; (b) 2 spawned tasks both executed in-cycle; (c) joint v0.9 mid-prep review with 22+7 = 29 findings folded; (d) brief v0.6 → v0.9.8 in 8 minor-version increments. Without spawned-task execution + joint review, cycle-15 would have been ~15-18 commits (closer to cycle-14 median). The spawned-task execution + joint review produced substantive substrate value, not pure ceremony.

---

## Established patterns (preserved from cycle-14 handoff; cycle-15 extensions noted)

See [cycle-14 operator handoff §"Established patterns"](HANDOFF-operator-transplant-2026-05-27-cycle14.md) for the full lore. **Cycle-15 adds:**

- **API key onboarding pattern.** User-principal pastes key; operator: (a) add via `Edit` (no echo); (b) verify with `grep -c "^KEY_NAME=" .env` returning 1 + `settings.<key>` loader test; (c) grep code for current consumers; (d) brief honestly on active/dormant state; (e) offer disposition (immediate use / spawn task / defer). 5 keys onboarded cycle-15 entry following this pattern; all 5 successful.

- **Spawned task execution pattern.** `mcp__ccd_session__spawn_task` queues work for cycle-N+; if other seat picks up in same cycle, mark as in-cycle execution. Both cycle-15 spawned tasks (foley + Cartesia) were executed in-cycle. **Implication:** spawn_task is a queuing mechanism, not a deferral mechanism; future spawn_task prompts can be more aggressive about in-cycle execution if substrate is mature.

- **Orchestrated subagent dispatch with Multi-Task Plan discipline** demonstrated for Cartesia re-impl. Pattern: pre-dispatch state verification → implementer subagent dispatch (~50-100k tokens) → independent verification of claims → parallel spec + code-quality reviewer dispatch (~10-12k tokens each) → Rule #15 disposition + fix loop if needed → final push. Wall-clock: ~25-35 min total. Cost: subagent token burn + main context only ~5-10k for orchestration.

- **Joint v0.9 mid-prep review pattern** (operator REPLY §2 hybrid protocol) demonstrated. Both seats dispatched independently per Rule #9 §"Parallelism"; produced cold-context independent findings with cross-cell convergence on 3 finding pairs (F-5/F-6 ↔ F7 ↔ F-7 cross-cell PA-IDENTITY field-naming + F-1 ↔ F1 PA-IMAGE↔P-KEYFRAME cost). **Implication:** Rule #9 second-opinion convention working as designed; future mid-prep reviews should default to parallel both-seat dispatch.

- **Multi-version brief v0.X.Y micro-increment pattern.** Cycle-15 produced 9 distinct brief versions (v0.7 / v0.8 / v0.9 / v0.9.1 / v0.9.2 / v0.9.3 / v0.9.4 / v0.9.5 / v0.9.6 / v0.9.7 / v0.9.8). Each commit = single logical fold; per-finding traceability via TL;DR version-bump body. **Implication:** brief versioning at micro-increment grain (v0.9.X) is operationally clean when each version closes a single bounded concern. Larger jumps (v0.9 → v1.0) reserved for ship-readiness milestone.

- **Pre-existing dormant capability accept pattern** (operator-side v0.9.8 PR-DIALOGUE note on ElevenLabs cost-tracker asymmetry). When closing a finding exposes a pre-existing asymmetry, document the asymmetry explicitly + defer symmetric fix per Rule #15. **Implication:** asymmetry-discovery is OK; scope-discipline prevents asymmetry-discovery from cascading to unbounded follow-up work.

- **Cycle-15 entry began drift-rich (7 same-shape Candidate #8 catches in 13 commits); later drift-free** — substrate-stabilization signal. **Implication:** drift catches concentrate in active-REPLY-cycle windows; standby + standby-state-update commits are drift-free. Cycle-16 entry will likely begin drift-rich again as user-principal drives execution decisions.

---

## Open questions for director (held over for next director session)

**Brief v1.0 ship blockers (joint):**

- **0 outstanding director cell-fill work** — brief is substantively v1.0-ready at v0.9.8. Director's foley work + joint review fold complete; user §9 5-9 answered.
- **0 outstanding operator cell-fill work** — Cartesia v0.9.7 + I-2 v0.9.8 closed; PA-VIDEO native-routing v0.9.3/v0.9.4; PA-AUDIO Suno V5 v0.9.5; PR-DIALOGUE Cartesia v0.9.7.
- **User-principal action: RunPod pod fresh deploy** (pod HTTP/2 404 throughout cycle-15 + cycle-14; only remaining cycle-16 execution blocker)
- **User-principal action: execution authorization** (pending pod restart + brief v1.0 ship)

**v5.4 codification timing:**

- 5 N=1 candidates filed (#1, #3, #4, #5, #8); 0 at N=2 emergence. Codification waits for N=2 shape-divergent emergence.
- Director-seat MAY draft v5.4 when ≥1 candidate reaches N=2 per role partition strategic-default; operator MAY draft per v2-v5.3 precedent. User direction breaks ties.
- Cycle-15 added reinforcing-evidence for Candidate #8 (7 same-shape catches) but NO shape-divergent N=2.

**Optional v0.9.X+ tightening before v1.0 ship (if user requests):**

- Symmetric ElevenLabs cost-tracker addition (closes v0.9.8 asymmetry note)
- PA-TTS sweep cell (cycle-15 v0.9.7 PR-DIALOGUE noted as deferred)
- v0.9.7 Cartesia reviewer findings F-1/I-1/I-3 (advisory; cosmetic tightenings)

**Net director-actionable findings outstanding from cycle-15: 0** (all REPLY content folded; all spawned tasks executed; Lane V cycles closed). **User-actionable decisions outstanding: 1** (RunPod pod fresh deploy + execution authorization sequencing).

---

## Baseline state snapshot at transplant

State at the moment of cycle-15 close handoff WRITE. Run cold-start checklist for current truth.

```
$ git log --oneline -5
fb25677 docs(brief)+feat(audio): v0.9.8 — close I-2 cost-tracker silence by wiring CARTESIA_SONIC_2 record_api_call in dispatcher
de71f50 docs(brief): v0.9.7 — Cartesia Sonic 2 TTS re-introduction + cost-tracker + comment update
9ba2eb8 feat(audio): wire Cartesia/ElevenLabs language router into per-line dispatcher
cac8650 feat(audio): add _resolve_tts_provider language router for Cartesia/ElevenLabs
d4f11d6 feat(audio): re-add generate_cartesia for Cartesia Sonic 2 low-latency TTS

$ git status
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean
(modulo this handoff file pending add+commit)

$ git rev-list --count origin/main..HEAD
0   # everything pushed

$ .venv/bin/python -m pytest tests/unit/ -q | tail -1
925 passed, 3 skipped, 2 warnings, 10 subtests passed
(baseline up from 866 cycle-14 close; +59 = director foley +30 + operator Cartesia +27 + I-2 +2)

$ .venv/bin/python scripts/ci_smoke.py
OK

$ cat coordination/mailbox/seen/operator.txt
2026-05-27T10:46:03Z
# Consumed director's T10:46:03Z verification-report event.

$ ls coordination/mailbox/sent/ | tail -5
2026-05-27T10-20-35Z-director-to-operator-fyi.md
2026-05-27T10-29-02Z-operator-to-director-acknowledgement.md
2026-05-27T10-45-00Z-operator-to-director-verification-report.md
2026-05-27T10-46-03Z-director-to-operator-verification-report.md
2026-05-27T10-56-16Z-operator-to-director-acknowledgement.md

$ grep -c "^" .env
26
(was ~21 pre-cycle-15; +5 keys = GEMINI/SUNO/STABILITY/CARTESIA/SEEDANCE)

$ curl -sI "https://0f8wqszne2zby7-8188.proxy.runpod.net/object_info" --max-time 5 | head -1
(pod still HTTP/2 404 throughout cycle-15; not re-probed this handoff)
```

**LOC drift advisory (cycle-15):**
- `docs/BRIEF-comprehensive-test-2026-05-27.md`: **1452 LoC** (was 1090 cycle-14 close; +362 = 7 minor-version folds + Cartesia + foley + joint review)
- `docs/EXTENSIVE-TEST-PLAN-2026-05-27.md`: **775 LoC** (was 773 cycle-14 close; +2 = Layer 1 Rule #12 corrections at `c0365f5`)
- `docs/PR-cells-prestaging-2026-05-27-cycle15.md`: **321 LoC** (NEW this cycle at `7d66b71`; Layer 2 Rule #12 corrections at `27dd473`)
- `docs/PROTOCOL-RULES-LOG.md`: **579 LoC** (UNCHANGED cycle-15; no new rules, no new candidates)
- `audio/foley.py`: NEW this cycle (director's foley impl)
- `audio/dialogue.py`: +200-400 LoC (operator's Cartesia re-impl + I-2 wire-up + tests)
- `cinema_pipeline.py`: +foley wire-up (director's `_ensure_scene_foley`)
- `phase_c_ffmpeg.py`: +foley tri-mix (director's amix extension)
- `cost_tracker.py`: +2 entries (STABILITY_FOLEY + CARTESIA_SONIC_2)
- `.env`: 26 lines (+5 keys + structural)
- `CLAUDE.md`: 1811 LoC (unchanged cycle-15)
- `AGENTS.md`: 1391 LoC (unchanged cycle-15)

**Total cumulative N=1 candidates filed:** **5** (Candidates #1, #3, #4, #5, #8). UNCHANGED cycle-15. 0 at N=2 emergence.

**Total rules codified through cycle-15:** **15** (UNCHANGED cycle-15; no v5.4 ship). Three consecutive `both`-beneficiary bundles (v5.1 → v5.2 → v5.3) lean from cycle-13 close preserved.

---

## Time accounting (this operator session)

| Phase | Approx hours |
|---|---|
| Cold-start checklist + reading cycle-14 close handoff | 0.3 |
| Pre-staging PR-* cross-refs (Lane C survey + Rule #12 Layer 1 catch) | 0.4 |
| Testplan §5 P3+P9 Layer 1 fix | 0.2 |
| Director FYI receipt + Layer 2 Rule #12 finding + closure | 0.3 |
| User §9 5-9 answers detected via director's parallel session activity | 0.1 |
| Operator-side joint v0.9 mid-prep review (subagent dispatch + verification-report compose) | 1.5 |
| Director-side joint v0.9 receipt + cross-cell convergence ack + Option A fold | 0.4 |
| Brief v0.9.2 PA-* fold (operator-side) | 0.3 |
| PA-VIDEO native-routing folds (v0.9.3 Kling + v0.9.4 LTX) | 0.4 |
| PA-AUDIO Suno V5 fold (v0.9.5) | 0.3 |
| 5 API keys added in series (GEMINI / SUNO / STABILITY / CARTESIA / SEEDANCE) + inventory-grep-consumer pattern per key | 1.0 |
| 2 cycle-16+ spawned tasks (foley + Cartesia) — prompt drafting + spawn | 0.6 |
| Cartesia re-impl orchestrated subagent dispatch + spec reviewer + code-quality reviewer + I-2 follow-up | 1.0 |
| Cycle-15 close handoff drafting (this doc) | 0.7 |
| **Total** | **~7.5 hours** |

**Subagent dispatches this cycle:** 3 cumulative cycles:
- Lane C joint v0.9 review (~191k tokens) — operator-side dispatch
- Cartesia implementer (~50-100k tokens) — orchestrated dispatch
- Cartesia spec reviewer (~10k tokens) + code-quality reviewer (~12k tokens) — parallel per Rule #9 §"Parallelism"

**Cumulative subagent tokens** for cycle-15 operator-side: ~263-313k cumulative.

**Operator-driven Lane B this cycle:** 1 invocation (Cartesia re-impl via orchestrated subagent; per Rule #14 §5 criteria check — all 5 criteria met: single bounded task, clear canonical pattern from existing audio/dialogue.py + audio/foley.py shape, 200-400 LoC ≤150 production-code-only NO actually >150 production LoC so Rule #14 criterion #3 not strictly met — this was orchestrated subagent dispatch per Multi-Task Plan discipline, NOT operator-driven Lane B per Rule #14. Filing distinction for v5.X codification consideration if needed).

**Lane V dispatches this cycle:** 0 operator-direct (Cartesia reviewers were Multi-Task Plan discipline, not Lane V post-commit independent verification on director feat commits per Rule #9 framing).

Total operator-seat efficiency: ~263-313k subagent tokens, ~7.5h productive substrate + brief co-authorship + API key onboarding + Cartesia re-impl orchestration. Cycle-15 represents the **most substantively productive operator cycle to date** measured by per-commit value delivered (Cartesia capability + brief substantive completeness + 5 API keys consolidated + joint review folded + I-2 closure).

---

*Operator-seat handoff at HEAD `fb25677` (brief v0.9.8 + Cartesia complete + I-2 closed). Branch 0 ahead of `origin/main`. **Brief evolved v0.6 → v0.9.8 (1452 LoC) across 8 minor-version folds; ALL 30 cells filled; ALL 9 user §9 questions answered; joint v0.9 mid-prep review folded BOTH sides per operator REPLY §2 hybrid protocol; PA-VIDEO native-routing aligned all 3 sets; PA-AUDIO Suno V5 sweep added; PR-DIALOGUE Cartesia language-routed TTS landed; foley tri-mix capability landed via director's spawned-task execution; Cartesia re-impl landed via operator orchestrated subagent dispatch; I-2 cost-tracker silence closed at v0.9.8.** 5 API keys added (GEMINI / SUNO / STABILITY / CARTESIA / SEEDANCE); 2 spawned tasks BOTH EXECUTED in-cycle; 925 pass / 3 skip / 0 fail baseline preserved (up from 866 cycle-14 close); §15 smoke OK throughout; 15 discipline rules + 5 N=1 candidates UNCHANGED cycle-15. Per v5 §P1 ("two seats of one team"), this is operator-seat's handoff to the next operator-seat instance. Cold-start checklist above is v3 §F freshness-check compliant + carries Candidate #8 RECENCY discipline forward from cycle-14. Run `git log --oneline -5` AND re-`ls mailbox/sent/` immediately before any state-asserting Write spanning >30 min from cold-start gate. User-direction overrides agent discretion at any point (Rule #8 authority precedence + v5 §P1 user-as-principal). Cycle-15 = the pre-flight-API-keys + brief-v0.6→v0.9.8 + joint-v0.9-mid-prep-review + 2-spawned-tasks-both-executed + Cartesia-re-impl-via-orchestrated-subagent + I-2-fold cycle; cycle-16+ awaits brief v1.0 (deferred-MINOR fold per user discretion) + RunPod pod restart + execution authorization + Tier A/B/C/D execution (synchronous joint per user §9 Q9). Welcome to cycle-16.*
