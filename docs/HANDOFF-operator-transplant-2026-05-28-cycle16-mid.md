# Operator Handoff — Context Transplant 2026-05-28 cycle 16 MID (operator-pre-v2.0-REPLY)

**From:** Operator-seat (cycle-16 mid; post-Tier-C + post-debate-convergence + post-user-Q7-pivot + Race-N=5-handled)
**To:** Next operator-seat instance, fresh chat
**State at handoff:** HEAD `4522515` (operator fyi convergence-on-Race-N=5); cycle-16 NOT yet closed; director's v2.0 draft pending; operator REPLY-cycle on v2.0 pending
**Companion docs:**
- [HANDOFF-operator-transplant-2026-05-27-cycle16.md](HANDOFF-operator-transplant-2026-05-27-cycle16.md) — cycle-16 entry close (prior; `f9f3c1a`); the doc THIS session picked up from
- [HANDOFF-director-transplant-2026-05-27-cycle15.md](HANDOFF-director-transplant-2026-05-27-cycle15.md) — director cycle-15 close (still relevant)
- [HANDOFF-execution-begin-2026-05-27.md](HANDOFF-execution-begin-2026-05-27.md) — execution-kickoff guide
- [BRIEF-comprehensive-test-2026-05-27.md](BRIEF-comprehensive-test-2026-05-27.md) — brief v1.0 (still active until v2.0 ships)
- [CYCLE-16-CLOSING-REPORT-2026-05-27.md](CYCLE-16-CLOSING-REPORT-2026-05-27.md) — director's 478-line cycle-16 comprehensive synthesis
- [BRIEF-tier-d-validation-2026-05-28.md](BRIEF-tier-d-validation-2026-05-28.md) — operator's 811-line Tier D-validation brief (forward-looking)
- [docs/test-cells/C-2026-05-27T21-13-27Z.md](test-cells/C-2026-05-27T21-13-27Z.md) — Tier C cheongsam reel tier-end artifact
- [PROTOCOL-RULES-LOG.md](PROTOCOL-RULES-LOG.md) — rule registry (15 rules + Rule #16 candidate emerging)
- [CLAUDE.md](../CLAUDE.md) `# Director-Operator Concurrent Operation` — full protocol Rules #1-#15

---

## TL;DR (90 seconds)

**Cycle 16 mid = post-Tier-C-complete + post-debate-converged + post-user-Q7-pivot + Race-N=5-resolved.** Picked up from cycle-16 entry close at `f9f3c1a`. **22 commits between cycle-16 entry close and this mid handoff** (operator: 9; director: 13). User-principal direction shifted at T22:53Z: pivoted from "Phase 1 fix execution → Phase 2 validation" to **"Brief v2.0 FIRST → Phase 1-4 deferred to cycle-17"** per Q7.

**Headline arcs:**

1. **Tier C cheongsam reel COMPLETE** (operator-driven; `bf1a4e9e8a9a`; 50min wall-clock; $6.45 actual within $5-10 envelope; 25.5s 1920×1080 final mp4 with AAC tri-mix audio). **8 Tier B closures end-to-end re-validated:** VG-B1 + I-B1 + I-B2 + M-B1 + M-B2 + M-B3 + C-B1 partial + C-B2. **6 NEW findings filed:** 2 CRITICAL (C-D3 ChiefDirector parse + auto-approve VETO-ALL; C-D4 PuLID-Flux infra incomplete — C-B1 fix was scope-incomplete) + 2 IMPORTANT (C-D2 LLMEnsemble judge crash; C-D5 KEYFRAME composite threshold too strict) + 1 IMPORTANT-closed-inline (C-D6 `_ensure_scene_audio` signature drift at `024723d`) + 1 INFO (C-D1 `num_shots` ignored by competitive_decompose). **Plus 8 advisory findings** (3 cost-attribution + C-D-coord-1 director side-channel + doc drift + dialogue persist + P-PERFORMANCE unexercised + Kling-side identity carry insight).

2. **Director shipped cycle-16 comprehensive closing report** (`e4615c7` 478 lines) in parallel to operator's Tier D-validation brief (`2c9ee9f` 811 lines). Both responded to user-principal "gather all the information you learned..." direction at T22:12Z. **Race-N=3 of "user-direction reaches both seats without owner spec" shape.** Resolution: complementary-coverage (both shipped; convergent ~85%). Director closing-report catalogs 32 findings (3 Tier A + 13 Tier B + 14 Tier C + 10+ audit findings).

3. **Both seats authored parallel proposals + 1 REPLY cycle** to converge on cycle-16 closeout action plan. Director's `1955ff5` proposal (with 4 debate axes A-D + ownership matrix) → operator's `7380d43` REPLY-cycle-1 (counter on work split per Rule #14 + label refinement) → director's `aba7755` REPLY-cycle-2 CONVERGENCE (concurred on all operator counters). **Race-N=3 second-instance occurred during proposal cycle (operator's parallel proposal at T22:35Z; discarded pre-commit; replaced by REPLY).**

4. **User-principal answered 7 consolidated questions at T22:47Z + T22:51Z via AskUserQuestion:** Q1 DEFER Tier D-sweep; Q2 fold cost-audit into Phase 1; Q3 storyboard cycle-17+; Q4 codify Rule #16 in v2.0 §8; Q5 full re-author v2.0; Q6 authorize pod-side C-D4; **Q7 PIVOT to brief v2.0 FIRST (Phase 1-4 deferred to cycle-17).**

5. **Director shipped decision event `e65fb0c` claiming v2.0 full re-author** per Q5 + Q7. **Director begins v2.0 draft ~T22:55Z; expected ~2-3h drafting.**

6. **Race-N=5 detected** (this mid-cycle): operator drafted 829-line brief v2.0 SCAFFOLD on disk (`docs/BRIEF-comprehensive-test-v2-SCAFFOLD-2026-05-28.md`) concurrent with director's decision shipping. **Operator applied Rule #16 candidate self-discipline: did NOT commit; scaffold remains on disk uncommitted as REPLY-cycle input for director's reference.** Operator shipped convergence fyi event `4522515` at T22:59Z documenting Race-N=5 + offering scaffold content + race-ack telemetry.

- **Cumulative cycle-16-entry → mid telemetry:** 22 commits + 5 mailbox events this session (in addition to entry-cycle 21+1=22; cumulative cycle-16 = ~44 commits). 17 findings closed; ~10-15 open (depending on what counts). 4 race-shape catalog entries; Race-N=1 underlying shape now at **N=3 cumulative emergence** (Rule #16 codification material).

- **Substrate state post-cycle-16-mid:** **15 rules codified + Rule #16 candidate STRONG** (per Q4 will codify in v2.0 §8). 5 N=1 substrate candidates unchanged from cycle-16-entry. Race-N=3 (pre-write re-verify gap) now at N=2 cumulative — but already covered by Rule #4 + #7 + Candidate #8 RECENCY discipline; no new rule needed; operator-side adherence re-tightened.

- **Branch state at this refresh:** HEAD `4522515` (operator's Race-N=5 convergence fyi); branch **0 ahead of `origin/main`** (all pushed). Working tree: **modified** — `?? docs/BRIEF-comprehensive-test-v2-SCAFFOLD-2026-05-28.md` (operator scaffold on disk uncommitted; available for director's reference) + `?? logs/` (background-task log dir from Tier C run; not relevant). **Mailbox cursor for me (operator.txt):** `2026-05-27T22:53:55Z` (consumed director's `e65fb0c` decision event at T22:53:55Z).

---

## How to resume (cold-start checklist for next operator)

⚠️ **CANDIDATE #8 RECENCY discipline applies + Rule #16 STRONG-CANDIDATE applies.** Cycle-16-mid observed 3 N=1+ instances of Race-N=1 underlying shape (concurrent-claim race; user-direction reaches both seats without owner spec). Per Rule #11 R11 + Candidate #8: codification material; user-principal authorized for brief v2.0 §8 per Q4.

⚠️ **OPERATOR-SIDE PRE-WRITE GATE TIGHTENING.** Race-N=3 (pre-write re-verify gap) repeated this cycle — operator started scaffolding for "prepare for brief 2.0" without re-running `git log --oneline -5`. Already covered by existing rules; cycle-16-mid acknowledged + re-tightened. Next operator: ALWAYS run `git log --oneline -5` AND `ls coordination/mailbox/sent/ | sort | tail -3` immediately before any substantive Write (>50 LoC OR doc authoring OR mailbox event).

```bash
# 0. Cold-read STATE.md (machine truth; auto-maintained by hook)
cat STATE.md

# 0a. Rule #8 awareness gate: if STATE.md says `unread mailbox: operator=N≥1`,
#     surface to user in first user-facing turn:
#       "Mailbox has N unread event(s) for operator; processing now per Rule #8."

# 0b. CANDIDATE #8 RECENCY DISCIPLINE: if substantive Write happens >30 min
#     after cold-start, RE-RUN these checks immediately before the Write:
ls coordination/mailbox/sent/ | sort | tail -10
git log --oneline -5

# 0c. RACE-N=3 / N=5 DISCIPLINE: BEFORE any doc authoring, brief drafting,
#     or any Write >50 LoC, ALWAYS check for parallel work:
#       1. git log --oneline -5 — confirm HEAD; check for director commits
#       2. ls coordination/mailbox/sent/ | sort | tail -5 — check for new mailbox events
#       3. If director claimed similar work in last 30 min, STOP authoring;
#          ship convergence event instead per Rule #16 candidate

# 1. Manual verify (when STATE.md is stale — observed stale 1x cycle-16-mid)
.venv/bin/python scripts/ci_smoke.py            # expect: OK
.venv/bin/python -m pytest tests/unit/ -q --tb=no | tail -1  # expect: 973 passed, 3 skipped
git log --oneline -5
git rev-list --count origin/main..HEAD          # expect: 0 (modulo this handoff)

# 2. Mailbox + cursor
ls coordination/mailbox/sent/ | sort | tail -10
cat coordination/mailbox/seen/operator.txt      # last consumed = T22:53:55Z

# 3. Read in this order
#    a. STATE.md (you already did)
#    b. coordination/mailbox/sent/ — process unread events for operator role
#    c. ARCHITECTURE.md §15 smoke (if STATE.md says FAIL or unknown)
#    d. THIS FILE (you're reading it)
#    e. coordination/mailbox/sent/2026-05-27T22-53-55Z-director-to-operator-decision.md
#       (director's Q7 pivot decision; key cycle direction)
#    f. coordination/mailbox/sent/2026-05-27T22-59-47Z-operator-to-director-fyi.md
#       (operator's Race-N=5 convergence; scaffold content offered)
#    g. CYCLE-16-CLOSING-REPORT-2026-05-27.md (director comprehensive synthesis)
#    h. BRIEF-tier-d-validation-2026-05-28.md (operator's Tier D-validation brief)
#    i. docs/BRIEF-comprehensive-test-v2-SCAFFOLD-2026-05-28.md (operator scaffold ON DISK UNCOMMITTED;
#       available as REPLY-cycle reference for director's pending v2.0 draft)
#    j. BRIEF-comprehensive-test-2026-05-27.md (brief v1.0; still active until v2.0 supersedes)
#    k. docs/test-cells/C-2026-05-27T21-13-27Z.md (Tier C tier-end artifact)
#    l. CLAUDE.md "# Director-Operator Concurrent Operation" (Rules #1-#15 + Rule #16 candidate via §10)
#    m. PROTOCOL-RULES-LOG.md (rule registry + 5 N=1 candidates + Rule #16 emerging)
#    n. HANDOFF-operator-transplant-2026-05-27-cycle16.md (cycle-16 entry close substrate)

# 4. Director's v2.0 draft is pending. Wait for director ship signal (commit OR mailbox event).
#    When director ships v2.0 draft, operator REPLY-cycle on §1-§13 per v5 disagreement protocol.

# 5. Pre-Write / pre-commit Rule #4 + #7 + Candidate #8 + Race-N=3/5 gates
#    ALL apply to any state-asserting commit. Re-run git log --oneline -5 AND check
#    coordination/mailbox/sent/ before commit.
```

---

## What this session shipped (cycle-16 entry → mid)

### Tier C cheongsam reel execution (operator-driven; commits + artifacts)

| Commit | What | Notes |
|---|---|---|
| `d13fba1` | operator Tier C dispatch-claim mailbox + cursor T20:13:38Z → T20:59:30Z | per converged Tier C scope |
| `024723d` | **fix(perf): C-D6 close inline** — `_ensure_scene_audio` signature drift at `cinema/shots/controller.py:638` | shipped mid-pipeline-execution; future runs benefit |
| `515e2ff` | Tier C tier-end artifact + verification-report + cursor T20:59:30Z → T21:23:49Z + scripts/run_tier_c.py | comprehensive; final mp4 25.5s |

### Cycle-16 synthesis docs (BOTH SEATS in parallel; complementary)

| Commit | Author | What |
|---|---|---|
| `2c9ee9f` | operator | `docs/BRIEF-tier-d-validation-2026-05-28.md` (811 LoC; forward-looking) |
| `e4615c7` | director | `docs/CYCLE-16-CLOSING-REPORT-2026-05-27.md` (478 LoC; retrospective synthesis) |

**Race-N=3 of "user-direction without owner spec" shape.** Both shipped; complementary-coverage value.

### Cycle-16 debate convergence (proposal + REPLY-cycle)

| Commit | Author | What |
|---|---|---|
| `1955ff5` | director | proposal `1955ff5` — unified action plan + 4 debate axes A-D + ownership matrix |
| `7380d43` | operator | REPLY-cycle-1 — counter on work split (claim 4 P0 fixes per Rule #14) + label refinement + concur on axes |
| `aba7755` | director | REPLY-cycle-2 CONVERGENCE — concurred on all operator counters; 7 questions surfaced to user-principal |

**Race-N=3 second-instance occurred during proposal cycle.** Operator's T22:35Z parallel proposal discarded pre-commit; replaced by REPLY.

### Cycle-16 user-principal pivot

| Commit | What |
|---|---|
| `e65fb0c` | director decision post-user-principal 7-question-answer batch — **Q7 PIVOT to brief v2.0 FIRST; Phase 1-4 deferred to cycle-17** |
| `4522515` | operator fyi convergence-on-Race-N=5 — Rule #16 candidate self-discipline applied; scaffold on disk uncommitted |

### Director's parallel cycle-16-mid audit fixes (during operator Tier C run)

| Commit | What | Mailbox? |
|---|---|---|
| `2c41d02` | fix(defaults): F-B.2 prompt_optimizer_enabled default True | ❌ no fyi signal (Race-N=4) |
| `74c920e` | fix(cost): F-D.1/MR-C0 FLUX_KONTEXT tracking | ❌ no fyi signal |
| `669e5cd` | fix(cost): F-F.5 log_llm at web_research.py | ❌ no fyi signal |

**Race-N=4 (director side-channel inline-fix without mailbox signal during operator's tier execution).** Director acknowledged in closing-report §8.1 self-discipline ack.

---

## What's PENDING (cycle-16 close not yet reached)

### Director-claimed work (pending; expected this cycle)

1. **Brief v2.0 full re-author** per Q5 + Q7 — director-drafts ~2-3h; chunked or single commit per director-discretion
   - File: `docs/BRIEF-comprehensive-test-v2.0-2026-05-28.md` (NEW; supersedes v1.0)
   - 13 sections per director's decision §2.1 outline
   - Folds: Rule #16 codification (§8); cost attribution audit (§9); implemented-but-unutilized catalog (§10); cycle-17 phase plan (§11)
2. **Cycle-16 final closing report** (rename existing or NEW) — captures cycle-16 close
3. **`DECISIONS.md` ADR entry** for cycle-16 fixes + v2.0 ship
4. **Director-transplant handoff refresh** (director-side analogous to this doc)

### Operator-claimable work (pending)

1. **REPLY-cycle on director's v2.0 draft** — when shipped (bundled OR per-section)
   - Per v5 disagreement protocol: 2 REPLY cycles max before user-principal escalation
   - Operator-side focus per director's §3.1: §5 test cells (operational ownership) + §7 Tier F audit re-execution spec + §11 cycle-17 phase plan
2. **LV-1 ARCH §12 doc note** — Lane D opportunistic (NON-BLOCKING; can ship while director drafts v2.0; just 1-line note on C-B2 root-cause precision)
3. **Operator handoff refresh** (THIS DOC) ✅ DONE
4. **MEMORY.md update** — refresh transplant pointer ✅ pending (will do this commit)

---

## Cycle-17 deferred work plan (per Q7 pivot + Q1 DEFER)

Held for cycle-17 entry under refined v2.0 brief. From converged proposal:

### Phase 1: P0 fixes (per converged work split)

| Item | Owner | Status |
|---|---|---|
| C-D3 part 1 ChiefDirector parse-robust (`llm/chief_director.py`) | **operator-driven Lane B** | deferred to cycle-17 |
| C-D3 part 2 + C-D5 (bundled `cinema/auto_approve.py`) | **operator-driven Lane B** | deferred |
| C-D2 LLMEnsemble parse-robust (`llm/ensemble.py`) | **operator-driven Lane B** | deferred |
| C-D4 setup_runpod.sh harden (PulidInsightFaceLoader + antelopev2) | director | deferred |
| C-D4 pod one-liner application | user-principal (pre-authorized per Q6) | deferred |
| LV-1 ARCH §12 doc note | operator | available now OR deferred |
| A9-redux probe sequence | operator | deferred to post-pod-fix |
| Cost-attribution audit (per Q2) | director | folded into v2.0 §9 + cycle-17 work |

### Phase 2: Tier C-rerun-validation (cycle-17)

- Operator-driven; ~30-50min; ~$5-8
- Per operator brief v1.0 §5.4 per-finding acceptance criteria (PASS/DEGRADED/FAIL per C-D finding)
- Director Lane V coalesced range at tier-end

### Phase 3: Tier E closed-finding regression (cycle-17)

- Mixed pytest + synthetic-project E2E per converged Axis B
- 10 dedicated cells: TE-VG-B1 / TE-I-B1 / TE-I-B2 / TE-M-B1 / TE-M-B2 / TE-M-B3 / TE-LV-2 / TE-F-B.2 / TE-F-D.1 / TE-F-F.5
- Plus NEW TE cells post-Phase-1: TE-C-D2 / TE-C-D3-1 / TE-C-D3-2 / TE-C-D5 / TE-C-D6
- ~$0-2; ~15-30min

### Phase 4: Tier F audit re-execution (cycle-17)

- Director-driven; ~10min subagent burn; $0 paid
- Re-dispatch max-quality audit subagent on cycle-16-fixed HEAD; delta vs `a79c59`

### Phase 5: Tier D-fresh-scope PA-* sweep (cycle-17 OPTIONAL per Q1)

- DEFER decision based on Phase 2-4 results
- ~$15-25; ~4-8h
- PA-IDENTITY / PA-MOTION / PA-IMAGE / PA-VIDEO / PA-SAMPLING / PA-LIPSYNC / PA-AUDIO sweep cells
- Requires PuLID actually working (post-C-D4 pod fix)

---

## Operator-side artifacts (UNCOMMITTED; on disk)

**1. `docs/BRIEF-comprehensive-test-v2-SCAFFOLD-2026-05-28.md` (829 lines)**

Operator-drafted brief v2.0 scaffold during Race-N=5; NOT committed per Rule #16 candidate self-discipline. Available on disk as REPLY-cycle input for director's pending v2.0 draft.

**Phase-1-4-independent sections fully drafted** (director may adopt or reference):
- §0 Front matter + tier-structure table + v2.0 vs v1.0 deltas
- §1 Executive summary + cycle-17 framing
- §2 Tier A refined pre-flight (A9.1-A9.5 workflow class probes + A10 manual hardening inventory)
- §6 NEW Tier E closed-finding regression (10+5 cells; pytest + synthetic E2E)
- §7 NEW Tier F audit re-execution (delta-vs-cycle-16 protocol)
- §8 PREDICTION discipline v2 (marker-verification requirement; per-cell marker table)
- §9 Pipeline upgrade roadmap (P0/P1/P2/P3; ~30 items)
- §10 Process discipline (race-shape catalog + Rule #16 framing + Q9 clarification)
- §11 Acceptance criteria framework (PASS/DEGRADED/FAIL per cell)
- §12 Open questions cycle-17+
- §13 Race-ack telemetry summary cumulative
- §15 §15 smoke test block updated for cycle-16-mid HEAD
- §16 Brief v2.0 SCAFFOLD changelog

**Phase-N-dependent sections placeholdered:**
- §3 Tier B regression markers
- §4 Tier C-rerun-validation results
- §5 Tier D PA-* parameter sweep
- §6 TE-C-D2/3/5 cell additions
- §7 Tier F audit delta report
- §10 Rule #16 codification commit ref
- §13 Cumulative telemetry final
- §14 Promotion-to-final checklist

**Next operator: this file may be useful as REPLY-cycle input or director may have already absorbed/discarded its content by v2.0 ship time. Read it AFTER reading director's v2.0 draft to see what's still valuable to surface via REPLY.**

**2. `logs/` directory (background-task output)**

Tier C pipeline execution log (`logs/tier_c_2026-05-27T21-13-08Z.log` and similar). Not gitignored; available for audit. Not material to handoff; safe to ignore unless investigating Tier C details.

---

## Race-ack catalog cumulative (cycle-16 entry → mid)

| Race # | Shape | Instances cycle-16 | Codification status |
|---|---|---|---|
| **N=1** | **Concurrent-claim race (user-direction → both seats without owner spec)** | **3 cumulative** (entry T19:19Z dispatch + mid T22:25Z synthesis-doc/proposal + mid T22:53Z brief-scaffold) | **Rule #16 STRONG-CANDIDATE; user Q4 authorized v2.0 §8 codification** |
| N=2 | Stale-mailbox-content assertion | 1 (operator `2426f59` item #1) | watch |
| N=3 | Pre-write re-verify gap | 2 cumulative (entry T19:31Z + mid T22:53Z operator scaffold pre-write skip) | covered by Rule #4 + #7 + Candidate #8 RECENCY; operator-side adherence re-tightened |
| N=4 | Director side-channel inline-fix without mailbox signal during operator tier execution | 1 (director `a79c59` audit + 3 fixes during operator Tier C) | director §8.1 self-discipline ack |
| N=5 | (alias for Race-N=1 instance #3; brief-scaffold race) | (counted under N=1) | (counted under N=1) |

**Rule #16 candidate framing** (per Q4 authorization for v2.0 §8; codification target):

> When user-principal direction reaches both seats simultaneously without
> explicit owner specification, both seats MAY interpret as joint-team
> work and produce complementary parallel deliverables. The second seat
> to ship (by git timestamp) MUST send a follow-up coordination event
> within 30 minutes of the second commit landing, acknowledging the
> parallel deliverable + proposing convergence path (REPLY-cycle / merge
> / delegation / further parallelism). VARIANT for Race-N=5 pattern: if
> receiving seat has not yet committed but detects the conflict via Rule
> #7 pre-commit gate, MAY discard pre-commit + send convergence event
> offering content as REPLY-cycle input (preserves work value without
> committing parallel doc). Silent ship of second deliverable without
> coordination event = Rule #2 §"Signaling" violation.

---

## Open coordination items

### Mailbox state at this handoff

| Cursor | Value | Means |
|---|---|---|
| operator.txt | T22:53:55Z | consumed director's `e65fb0c` Q7 pivot decision |
| director.txt | T22:37:33Z (or post-`aba7755`) | director has consumed operator's REPLY-cycle-1 |

**Latest mailbox events (sorted):**
- T22:33:30Z director-to-operator-proposal `1955ff5`
- T22:37:33Z operator-to-director-reply `7380d43`
- T22:45:30Z director-to-operator-reply `aba7755`
- T22:53:55Z director-to-operator-decision `e65fb0c`
- T22:59:47Z operator-to-director-fyi `4522515` (this session's last commit)

### Pending director events (expected this cycle)

1. Director v2.0 draft ship (single OR chunked commit)
2. Cycle-16 final closing report (rename or NEW)
3. ADR entry in `DECISIONS.md`
4. Director-transplant handoff refresh
5. Possible silent-accept fyi to operator's `4522515` Race-N=5 convergence event (optional; not REPLY-required)

### Pending operator events (this cycle OR cycle-17)

1. **REPLY-cycle on director's v2.0 draft** — bundled OR per-section
2. **LV-1 ARCH §12 doc note** — opportunistic ship (non-blocking; while director drafts)
3. **MEMORY.md transplant pointer refresh** (this commit will do it)

---

## Substrate state post-cycle-16-mid

### Rules codified (15 + Rule #16 candidate STRONG)

15 rules from cycle-15 close + cycle-16-entry unchanged:
- Rule #1: TaskCreate plan-then-execute discipline
- Rule #2: Signaling — narrate before acting on shared tasks
- Rule #3: Lane heuristics (A=direct, B=fresh-subagent, C=read-only-survey)
- Rule #4: State-asserting writes gate on `git log --oneline -5` pre-Write
- Rule #5: Race-acknowledging commit bodies
- Rule #6: Counter-bump dispositions (fold-then-surface during concurrent ops)
- Rule #7: Pre-commit re-verify (matching pre-Write Rule #4)
- Rule #8: Mailbox event authority equal to user-relayed signals
- Rule #9: Independent reviewer convention (parallelism + CC-1 coalesced + CRITICAL exception + CC-2 spec-reviewer prompt discipline)
- Rule #10: Joint-team mode (operator/director are two seats of one team; v5 disagreement protocol)
- Rule #11: Codification bias check (R11 — name the primary beneficiary)
- Rule #12: Brief-level grep-the-writes discipline
- Rule #13: Symmetric-endpoint audit discipline
- Rule #14: Operator-driven Lane B template + 5 selection criteria
- Rule #15: Cross-seat fix-on-received-findings convention

**Rule #16 candidate STRONG (user-direction without owner spec):**
- N=3 cumulative; per Q4 user-principal authorized v2.0 §8 codification
- Operator-suggested framing (see "Race-ack catalog cumulative" above)
- Beneficiary: `both` seats (symmetric)
- Codification commit pending (in director's v2.0 draft OR standalone proposal cycle)

### 5 N=1 substrate candidates (unchanged from cycle-16-entry)

| Candidate | Shape | N | Status |
|---|---|---|---|
| #1 | (cycle-15+ era; specific to that cycle) | 1 | watch |
| #3 | (cycle-15+ era) | 1 | watch |
| #4 | (cycle-15+ era) | 1 | watch |
| #5 | (cycle-15+ era) | 1 | watch |
| **#8 RECENCY** | Pre-write re-verify discipline (substantive Write requires fresh `git log` AND `ls coordination/mailbox/sent/`) | 1 → effectively N=2 cycle-16 cumulative; covered by existing rules | continuous |

---

## Cumulative metrics

### Cost cumulative (cycle-15-entry → cycle-16-mid)

| Cycle / phase | Cost |
|---|---|
| Cycle-15 entry | $0 |
| Cycle-16 entry pre-flight + Tier A | $0 |
| Cycle-16 Tier B Korean dialogue probe | ~$2.10-2.65 |
| Cycle-16 Tier C cheongsam reel | $6.4508 |
| Cycle-16-mid Phase 1 (deferred) | $0 (deferred) |
| **CUMULATIVE** | **~$8.55-9.10 of $50 hard cap (17-18%)** |
| **Headroom for Tier D + future cycles** | **~$40-41** |

### Pytest baseline progression

```
Cycle-15 baseline:           866/3/0
Cycle-15 entry post-audio:   925/3/0
Cycle-16 post-VG-B1+LV-2:   945/3/0
Cycle-16 post-I-B2+M-B1:    963/3/0
Cycle-16 post-M-B2:         973/3/0
Cycle-16-mid (current):     973/3/0 (no new test additions this mid-cycle; deferred to cycle-17 Phase 1)
Cycle-17 entry expected:    ~1000-1030 (Phase 1 P0 fix tests)
```

### Wall-clock cumulative

| Cycle | Wall-clock |
|---|---|
| Cycle-15 entry brief + Tier A scaffolding | ~6h |
| Cycle-16 entry → mid (this session) | ~5h |
| Cycle-16-mid synthesis + debate + handoff (this session continues) | ~3h |
| **CUMULATIVE cycle-15-entry → cycle-16-mid** | **~14h** |

---

## RunPod pod operational state

- Pod: `525nb9d5cc0p3y` ([https://525nb9d5cc0p3y-8188.proxy.runpod.net](https://525nb9d5cc0p3y-8188.proxy.runpod.net))
- HTTP/2 200 ✅ (cycle-16-mid pre-flight T21:05:15Z)
- UNETLoader serves: `FLUX1/flux1-dev-fp8.safetensors` ✅ (C-B1 closure persisted)
- **PulidInsightFaceLoader: MISSING** ❌ (C-D4; needs Phase 1 user-principal pod-side install)
- antelopev2 InsightFace model: presumably MISSING (correlates with C-D4)

Phase 2 Tier C-rerun-validation (cycle-17) requires PulidInsightFaceLoader fix before PuLID path can be validated.

---

## What to do RIGHT NOW (cold-start next operator instance)

### Immediate

1. **Read this handoff in full** (~10-15 min)
2. **Check mailbox + git for new director events** since `4522515` — director may have shipped v2.0 draft OR cycle-16 close artifacts OR director-transplant handoff
3. **Read operator's offered scaffold** at `docs/BRIEF-comprehensive-test-v2-SCAFFOLD-2026-05-28.md` (uncommitted on disk) AFTER reading director's v2.0 draft (compare content; surface REPLY-cycle content from scaffold if not covered)

### If director v2.0 draft has shipped

- **Author REPLY-cycle on v2.0 draft** per director's `e65fb0c` §3 + Q5 path
- Counter-refine, concur, surface gaps
- Use operator scaffold as reference (do NOT commit scaffold as parallel doc; cite content in REPLY event if useful)
- Per v5 disagreement protocol: 2 REPLY cycles max

### If director v2.0 draft has NOT yet shipped

- **Standby** — director's draft expected ~2-3h post-`e65fb0c` (T22:53:55Z); could land anytime
- **Opportunistic LV-1 ARCH §12 doc note ship** — non-blocking; ~5 LoC doc change to `ARCHITECTURE.md §12 Audio pipeline` noting C-B2 root-cause precision (Kling silent video NOT filtergraph bug)
- **Do NOT race-author parallel v2.0** — per Rule #16 candidate self-discipline; scaffold already exists on disk for REPLY-cycle use

### If user-principal redirects

- User overrides per Rule #8 authority precedence
- Per Q7 pivot, current path is brief v2.0 → cycle-16 close → cycle-17 entry under v2.0 brief

---

## Audit trail (full session timeline)

| Event | Timestamp | Commit |
|---|---|---|
| Session start; orient + pre-flight | T21:00Z | — |
| Operator Tier C dispatch-claim | T21:08:00Z | `d13fba1` |
| Tier C pipeline start (script `scripts/run_tier_c.py` background) | T21:13:09Z | (no commit; bg `bj4ypl9er`) |
| Director Tier C silent-accept | T21:23:49Z | `73dabd7` |
| Operator C-D6 inline fix during pipeline run | T21:43Z | `024723d` |
| Director parallel audit fixes (Race-N=4) | T21:51-54Z | `2c41d02` + `74c920e` + `669e5cd` |
| Tier C pipeline end + tier-end artifact | T22:03-08Z | `515e2ff` |
| User-principal "gather all..." direction | T22:12Z | direct chat |
| Operator Tier D-validation brief | T22:18-22Z | `2c9ee9f` |
| Director cycle-16 closing-report (Race-N=3 parallel) | T22:25-26Z | `e4615c7` |
| User-principal "plan debate toast" direction | T22:32Z | direct chat |
| Director proposal (Race-N=3 second instance) | T22:33:30Z | `1955ff5` |
| Operator REPLY-cycle-1 (parallel proposal discarded pre-commit) | T22:37:33Z | `7380d43` |
| Director REPLY-cycle-2 CONVERGENCE | T22:45:30Z | `aba7755` |
| User-principal Q1-Q7 batch (via director's AskUserQuestion) | T22:47Z + T22:51Z | direct |
| User-principal "prepare for brief 2.0" direction | T22:52Z | direct (operator session) |
| Operator scaffold drafting (Race-N=5) | T22:52-55Z | (on disk uncommitted) |
| Director decision Q7 pivot | T22:53:55Z | `e65fb0c` |
| Operator detects Race-N=5 via Rule #7 gate; ships convergence fyi | T22:59:47Z | `4522515` |
| User-principal "handoff" direction | T23:0XZ | direct (operator session) |
| **Operator transplant handoff (this doc)** | **T23:0XZ** | (this commit; pending) |
| Director v2.0 draft (pending) | TBD | TBD |
| Operator REPLY-cycle on v2.0 (pending) | TBD | TBD |
| Cycle-16 close (pending) | TBD | TBD |

---

Signed,
Operator-seat — 2026-05-28 cycle 16 mid, transplant handoff at HEAD `4522515` post-Tier-C-complete + post-debate-converged + post-user-Q7-pivot + Race-N=5-resolved + standby for director v2.0 draft
