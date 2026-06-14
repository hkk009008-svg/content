# HANDOFF — operator2 (Pair-B), 2026-06-15

**READ FIRST as operator2.** This session authored ONE binding verification: Lane V on
`web_research-uncounted` `f5a95ec` → **NITS** (committed `77b97b9`, verification-report
`18-44-02Z-operator2-to-all`). Then `handoff` — a 3-deep verify queue is **CARRIED, not worked**.

> Trust git, not this prose. `env -u GIT_INDEX_FILE git log -1` + `git rev-list --count origin/main..HEAD`.
> HEAD moved **5×** under me this session — re-anchor before EVERY commit.

## What I shipped (the one verification)

**`web_research-uncounted` `f5a95ec` → NITS** — impl=director2 ≠ verifier=operator2.
Lane V `wf_03568e29-31b` (cold `lane-v-verifier` + `money-gate-reviewer` + isolated
non-vacuity mutation; all model=sonnet) + my own grep/ci_smoke/regression on the live tree.

- **GO-quality core:** `run_with_tools` routes both `log_llm` sites onto the caller tracker;
  **Rule #12 gate-connection CONFIRMED** — `CinemaPipeline.cost_tracker` (`cinema_pipeline.py:150`)
  → `_core.cost_tracker` (sole instance, `cinema/core.py:113`) == the gate-read instance
  (`spent_usd` `cost_tracker.py:454/470`; write `:306`). **Non-vacuous (mutation-proven):**
  revert `web_research.py` → test RED. Deferral (`web_server.py` 1438/1479/1520 → `W2-web_server.py.lock`)
  legitimate/disclosed. ci_smoke RC=0; suite 2498p/3s/25xf.
- **NIT-1 [BLOCKING, in-scope, one line]:** `domain/scene_decomposer.py:844` — the `except`-handler
  fallback `return decompose_scene(...)` is **missing `cost_tracker=cost_tracker`**. The fix threaded
  the sibling fallbacks `:776`/`:809` but missed this third one → competitive-FAILURE path leaks. My
  sibling-call scope-match caught it; **neither cold reviewer did.**
- **NEW ROW [blocks reconcile-to-verified, NOT the commit] — candidate-CRITICAL:**
  `LLMEnsemble.competitive_generate` primary-path leak. `llm/ensemble.py` has **zero** cost tracking
  (`_generate_anthropic:266`/`_generate_openai:307`/`_generate_gemini:329`/`_judge:364`). The PRIMARY
  competitive path (DEFAULT `competitive_generation=True`, `cinema_pipeline.py:1017`; `scene_decomposer.py:760`)
  = **~3 LLM calls/scene invisible to the gate**, scaling with scene count. Separate module, pre-existing,
  **NOT created/worsened by `f5a95ec`** → file as a new Wave-2 row (money-gate=CRITICAL, lane-v=MAJOR →
  **candidate-CRITICAL** for R-VERIFY-TIER triage). No pin exists. Fix opt (b): post-call `log_llm` on the
  result `usage` (carried at `_generate_anthropic:285`) — no interface change. **`web_research-uncounted`
  must NOT reconcile as "planning spend gated" while this is open** (it would mask the default-path leak).
- **Reviewer split adjudication:** lane-v=NITS, money-gate=FAIL → **I synthesized NITS** on scope (the FAIL
  rests entirely on the separate-module LLMEnsemble CRITICAL; failing the commit would wrongly imply
  revert). money-gate substance fully honored = the new row carries the CRITICAL candidacy, not dropped.
- **§6c:** on the NIT-1 diff I re-read the actual `git show` and issue GO. No lock (pure Pair-B, stub-spec §2).

## OWED by operator2 (CARRIED — not worked this session)

1. **Lane V `lipsync-syncnet-nan` `1d30581`** (verify-request 18:34Z) — silent-gate NaN family; cold
   `lane-v-verifier`, mutation-test the finite-guard fires.
2. **Lane V `audio-remux-notimeout` `f108565`** (verify-request 18:38Z) — io/timeout; bound + `TimeoutExpired`.
3. **`charmgr-cost-fresh-instance` provisional-CRITICAL ratification** (R-VERIFY-TIER) — coordinator flagged
   MAJOR→CRITICAL (18:19Z event), "awaiting lane-operator ratification"; it's one of my 3 pins + same money
   family → mine to ratify or contest. Evidence in `logs/discovery-wf_f57f0d89-bc2.json`.
4. **Re-verify `web_research` NIT-1 `:844` nit-fix diff** when director2 lands it (§6c) → then GO.

Cursor LEFT at **2026-06-14T18:19:13Z** (deliberately — keeps the 2 verify-requests unread/visible as the
owed queue; my own `18-44` report + the Pair-A `18-45` broadcast also show unread, triage them).

## Live state at wrap (verify against git)

- HEAD `77b97b9` (my verification commit) on Pair-A's `23c99e3`; **6 ahead of origin, unpushed** (user-gated).
- director (Pair-A) ONLINE @ `77b97b9`; director2 (Pair-B, my partner) ONLINE @ `5244005`, awaiting my next
  verdicts; operator (Pair-A) STALE.
- Wave-2 gate UNMET. Pair-B fixes landing fast (web_research/lipsync/remux); Pair-A landed `has-char-lora`
  decouple `23c99e3` (A1) + has a fresh 18:45Z coordination broadcast (unread — Pair-A content).
- 2 provisional open CRITICAL campaign-wide (`idgate-failopen` cross-lane Tier-A = director2's co-sign;
  `charmgr-cost-fresh-instance` = my owed ratification #3).

## Sharp edges (this session)

- **HEAD moved 5× under me** (`dd6377a`→`47f2797`→`5244005`→`23c99e3`→`77b97b9`). Re-anchor (`git log`) before
  EVERY commit — caught each move; my orientation snapshot was stale within minutes (Rule #7).
- **Phantom `index-operator2` pollution** (D/?? pairs on committed files). Worktree is clean-at-HEAD —
  verify via `git diff --stat HEAD` + per-file `git diff --no-index <(git show HEAD:path) path`, NOT `git status`.
- **Commit gotcha (new):** `send-event` stages the new report into `index-operator2`, but
  `env -u GIT_INDEX_FILE git commit -- <newfile>` FAILS ("pathspec did not match") — the new file isn't in the
  DEFAULT index. Fix: `env -u GIT_INDEX_FILE git add -- <paths>` FIRST, THEN explicit-pathspec commit
  (`--only` = HEAD-tree + named paths; pollution + Pair-A's uncommitted work can't leak in). The guard hook
  forces `env -u`; the staging-index mismatch is the trap.
- **Pair-A live-edited `quality_max.py`** (108 lines uncommitted, later committed `23c99e3`) → explicit-pathspec
  isolates my 2 files. ci_smoke "RED" the coordinator warned of = **advisory PROGRAM-MANUAL.md drift, not the
  hard gate** (ARCHITECTURE.md green, RC=0).
- **Lane-V lesson (refines money-loss bug class):** a money fix that threads `cost_tracker` into a function whose
  PRIMARY path uses a DIFFERENT cost subsystem (`LLMEnsemble`) creates **false completeness** — the threaded
  fallbacks look fixed while the default primary path leaks. Verify the primary path's subsystem, not just the
  threaded forwards. Scope-match beyond the pin caught BOTH `:844` and the LLMEnsemble row.

## WRAP ADDENDUM — NIT-1 discharged (§6c GO), same session

After the wrap commit `b5158f1`, director2 landed the NIT-1 fix `612ed25` (one-line `:844`
`cost_tracker=cost_tracker`) and re-requested verify (`20:00:36Z`). I discharged the §6c
re-verify: read the actual `git show 612ed25` (cosmetically scoped — no new logic/files/contract),
`scene_decomposer.py` parses, web_research regression GREEN, **all 3 fallbacks `:776`/`:809`/`:844`
now thread the tracker** → **NIT-1 GO** (verification-report `20-16-05Z`). The `run_with_tools`
fix is now operator-VERIFIED (core GO + NIT-1 GO). director2 ACK'd the LLMEnsemble row gates the
reconcile and carried it to the coordinator.

**⚠ web_research-uncounted reconcile STILL GATED:** coordinator must NOT mark it `verified` until
the `LLMEnsemble.competitive_generate` candidate-CRITICAL row is **filed as an open inventory row**
(else the DEFAULT-path leak is masked). NOT operator2's to file (director2/coordinator).

**Still CARRIED (unchanged):** Lane V `lipsync-syncnet-nan` `1d30581` + `audio-remux-notimeout`
`f108565`; ratify `charmgr-cost-fresh-instance` provisional-CRITICAL. Owed item #4 (the `:844`
re-verify) is now **DONE**. Cursor advanced to `20:16:05Z` (all seen). All peers (director-1,
director2, coordinator) WRAPPED — operator2 is the last active seat at this wrap.
