# HANDOFF — operator2 (Pair B), 2026-06-14 — Wave-1: budget-nan GO→verified + money-loss sweep (2 NEW CRITICALs) — READ FIRST AS OPERATOR2

**Seat:** `operator2` = Pair-B **operator** (independent verification + sibling-sweep + mailbox). Lane = VIDEO/ASSEMBLY/DELIVERY + the Pair-B **money lane** (`cost_tracker.py`, budget gate). Pair lead = **director2** (LIVE). Coordinator LIVE (Session-8, owns inventory + wave gate).

---

## ⭐ SESSION OUTCOME — discharged the owed budget-nan verify + delivered the money-loss family

Resumed mid-**Wave-1** of the program-hardening campaign. Two deliverables, both landed + ACK'd by both directors and the coordinator.

### My commit (local; push USER-gated — do NOT push)
- **`e3c9045`** — `coord(wave1)`: budget-nan GO verification-report (→director2) + money-loss `findings` (→all) + cursor→10:40:54Z. Clean 3-file partial commit (explicit pathspec; no phantom-index sweep). **NB I refreshed the cursor again to 11:14:02Z + presence at wrap — see commit below.**

### 1. budget-nan (Wave-1 Task 6) verify = **GO** → coordinator advanced to **`verified`** (`7aa1bd9`)
Independent post-commit verify of director2's `bc55733` (NaN/inf budget cap → fail-safe BLOCK, ADR-026; sole `cost_tracker.py:224` chokepoint). All 6 criteria PASS (report `10:49:39Z`): sole-write-site grep; block behavior (nan/inf/garbage→`-1.0` sentinel→both gates True); regressions (None/0/0.0 unlimited, finite enforced, negatives still block); **mutation in a detached worktree** (revert guard → nan/+inf/garbage/not-stored cases RED — the `-inf` case stays green because it blocks anyway via the pre-existing negatives-path; the guard only neutralizes the two *escapers* NaN/+inf, so the `[nan,inf,-inf]` parametrize spread is what keeps the regression honest); pin→live-regression hygiene; full suite **0 failed**. director2 ACK'd `10:56:38Z`, no NITS.

### 2. Money-loss SIBLING SWEEP (`wf_6b3659c5-fec`, 6 lenses + refute-first, Sonnet) → **2 NEW CRITICAL Wave-1 gate-blockers** + 15 siblings
21 confirmed / 17 novel / 3 correctly refuted. The brief was a list of 2 (budget-nan, costtracker); the family is larger. `findings`→all `10:50:45Z`. **Both CRITICALs independently re-confirmed by my own grep** before escalating (not just the subagent's word). Disposition (all ACK'd):
- **C-1 `shot-spent-usd-never-written`** (`auto_approve.py:594`) — the per-shot veto is **DEAD CODE** (grep: ZERO writes of `spent_usd` into any shot dict). Made Pair-A's in-flight T3 `aa-budget-nan-veto` **correct-but-insufficient** (hardens a veto that never fires). **director2 OWNS the bridge** (Pair-B/money lane): `CostTracker.get_shot_spent(shot_id)` = SQLite `SUM(cost_usd) WHERE shot_id=?`, injected into the gate loop before `check_gate`. Awaiting coordinator C3 ratification → assign to Pair-B.
- **C-2 `spent-usd-reset-on-resume`** (`checkpoint.py`) — resumed run's gate starts at $0 vs the same cap (accumulator never rehydrated). **DESIGN-OPEN + cross-lane** (checkpoint+core); direction pick needed before a pin (mirrors budget-nan's design-Q). I deliberately did NOT pin (no fix-agnostic unit seam; would over-constrain). director2 can co-sign/own the Pair-B portion.
- **Pair-A siblings `aa-nan-budget-total` (:587) + `aa-inf-multiplier` (:595)** → **ALREADY CLOSED** by Pair-A's landed **T3 `baac518`** (budget_total guard) + **T1 `5ef3605`** (`_get` chokepoint coerces inf/NaN multiplier→1.5). Independent discovery corroborated their co-sign. Coordinator: NO separate rows.
- **Performance fresh-instance siblings** (perf-liveportrait/viggle/drivingvideo + perf-phase-no-gate + charmgr + webresearch) = the **manifestation set** of Task-7 Option B (below). + cascade-winner-wrong-key (8× undercount), keyframe/rife/tts precheck-gaps (Pair-B MAJ/MED).
- **3 refuted:** `audio/foley.py:185`, `audio/music.py:248` (shared tracker threaded in the only prod caller — latent footgun, not active loss), `scripts/_fal_man_lora_train.py:73` (outside the pipeline gate).

---

## CARRIES (next operator2 — OWED verifies, impl≠verifier)

1. **[HEADLINE] Verify Task 7 `costtracker-perf-uncounted`** when director2 lands it (last open Pair-B Wave-1 CRITICAL; director2 R-BRIEF `10:54:23Z` / `3cfe950`; **status=open**). Design = **Option B (inject the pipeline's shared `cost_tracker`)**, Option A (video_id SQLite SUM) REJECTED (regresses audio which logs `video_id=""`). Verify scope:
   - **(a) double-count check:** the fix moves `self.spent_usd += cost` into `log_api`/`log_llm` AND must **REMOVE the now-duplicate `:407` in `record_api_call`** (which delegates to log_api). Confirm `record_api_call` nets `+cost` exactly ONCE (no regression in `test_cost_tracker.py` spent_usd assertions).
   - **(b)+(c) scope-match BEYOND the pin:** the `(a)`-only pin-minimal fix flips `test_discovery_cost_xfail.py` GREEN but leaves the fresh-instance holes OPEN. **Manually confirm the shared tracker is threaded** to act_one/live_portrait/viggle `_cost_log` (via `_router.dispatch` + `controller.py:1076`) + driving_video's caller. This is exactly [[feedback_operator_scopematch_beyond_pin_and_literal]] — scope = intent, not the pin/snippet.
   - **Awaiting coordinator's web_research SPLIT ruling** (director2 leans SPLIT: web_research bounded planning-LLM cost → own row; Task 7 = (a)+performance to drain the *unbounded* per-shot CRITICAL). character_manager + perf-phase-no-gate also split.
2. **Verify C-1 bridge** when director2 lands it (`CostTracker.get_shot_spent` SQLite SUM injected before `check_gate`; the veto must actually fire on real per-shot spend).
3. **Verify C-2** after coordinator + director2 pick the backfill direction + pin it.
4. **Coordinator owes C3 ratification** of C-1, C-2, + the split siblings (web_research/character_manager/perf-phase-no-gate) into the inventory — track that they land as rows (don't let the gate pass without them).

## WAVE-1 GATE STATE @ wrap (trust git)
7 of the 8 original CRITICAL rows **verified**: Pair-A T1–T5 (`5ef3605`/`b8e3d72`/`baac518`/`4eca599`/`af03eeb`, operator-1 GO + `W1-auto_approve.py.lock` released `a3d8a9b`; adversarial `wf_955f2b6c-16e` CLEAN) + budget-nan (`bc55733`, my GO) + ws-reorder-deletes. **Only Task 7 (costtracker) remains open**, plus the **2 new mid-wave CRITICALs (C-1, C-2)** which per **C3 block the gate** until ratified+drained. HEAD `a3d8a9b`, **17 ahead** of origin, push USER-gated. ci_smoke OK. No locks on disk. Pod STOPPED ($0).

## SHARP EDGES (this session)
- **Phantom skip-worktree index again** — `git status` showed 91 "dirty" paths (staged-`D` on files present on disk); `git diff HEAD` ALSO lied (skip-worktree makes it skip the working file). Only `git diff --no-index <(git show HEAD:path) path` reads real bytes. Tree was == HEAD throughout. [[project_da_skip_worktree_workflow_pollution]]
- **zsh does NOT word-split unquoted vars** — `RM="env -u GIT_INDEX_FILE git"; $RM worktree …` → "command not found". Write the command literally each time (don't stuff a multi-word command in a var).
- **`git commit -- <explicit pathspec>`** does a partial commit of working-tree state for *only* those paths, bypassing the polluted index entirely → clean 3-file commit despite ~90 phantom paths. Verify with `git show --stat`.
- **Coordinator is a send-only pseudo-seat** (`KNOWN_KINDS`/`_EVENT_NAME_RE` in `check_coordination.py`): it can be `<from>` but never `<to>`, has no seen cursor. Address findings-for-ratification to `all` (coordinator reads all).
- **`coordination/presence/` is gitignored** — write it (peers read off the filesystem), don't try to commit it.
- **Mutation-test in a detached `/tmp` worktree** (`git worktree add --detach`, copy `.env`, run with the main `.venv` + `PYTHONPATH=<wt>` + `env -u GIT_INDEX_FILE`) — never mutate the live shared tree.

## COORDINATION STATE @ wrap
My events: `e3c9045` (GO report `10:49:39Z` + findings `10:50:45Z`) + this handoff + cursor→11:14:02Z. budget-nan = verified. director2/director-1/operator-1/coordinator all LIVE. Pair-A Wave-1 DONE. director2 ready to implement Task 7 on the coordinator's web_research ruling — **I'm the verifier; stand by.** [[money_loss_gate_source_mismatch_bug_class]]
