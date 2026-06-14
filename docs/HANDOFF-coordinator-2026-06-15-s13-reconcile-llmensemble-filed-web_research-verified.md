# HANDOFF — Coordinator Session-13 (continues S12)

**Read first as the next coordinator (on-demand §10).** Succeeds
`HANDOFF-coordinator-2026-06-15-s12-rca-adr027-gate-circularity-wave2-progress.md`.

## TL;DR
Pure session-start reconcile boundary (§6f trigger a). No production code (coordinator
prohibition). Four commits, all path-mode (default index is phantom-polluted — see Sharp):
- `316b212` reconcile: 4 landed-but-`open` rows → `fixed`.
- `d46102d` route: idgate Tier-A co-sign broadcast.
- `0ad7973` file NEW CRITICAL `llmensemble-cost-uncounted` + R-VERIFY-TIER(B) pin + discovery log.
- `9ead0df` reconcile: `web_research-uncounted` `fixed` → `verified`.

Gate: **UNMET** `{fixed:4, open:22, verified:3}` (R-EVIDENCE `scripts/wave_gate_check.py 2`).
ci_smoke **OK** (advisory drift only). **3 open CRITICALs:** `idgate-failopen`,
`llmensemble-cost-uncounted`, `charmgr-cost-fresh-instance`.

## What I did
1. **Reconcile (open→fixed), 4 rows** — real fix commits proven via `git show --stat`,
   left `open` by the landing directors (inventory is coordinator-owned): `has-char-lora-hole`
   + `secondary-lora-hole` (`23c99e3`), `lipsync-syncnet-nan` (`1d30581`),
   `audio-remux-notimeout` (`f108565`). Status `fixed` NOT `verified` (operator Lane V owed).
   **Completeness-checked:** every recent `fix(` commit maps to a `fixed`/`verified` row — no
   other drift.
2. **`web_research-uncounted` fixed→verified** (`9ead0df`) — operator2 GO (report
   `2026-06-14T20-16-05Z`, commit `823f36a`: core GO + NIT-1 GO; all 3 competitive fallbacks
   `:776/:809/:844` threaded). operator2 had **gated** the `verified` transition on filing the
   DISTINCT LLMEnsemble leak first — satisfied by `0ad7973`. (Caught by re-anchor: `823f36a`
   landed under me between orientation and my commits — Rule #7.)
3. **NEW CRITICAL `llmensemble-cost-uncounted`** (`0ad7973`) — `competitive_decompose_scene`
   drops the gate-connected `cost_tracker` on its SUCCESS path → bare `LLMEnsemble()`
   (`scene_decomposer.py:759`); `LLMEnsemble` has zero cost-tracking. DEFAULT competitive path
   (`competitive_generation` default True, `cinema_pipeline.py:1017`), ~3 LLM/scene, scales w/
   scenes, invisible to the budget gate (write `cost_tracker.py:306` / read `:472`).
   money-loss gate-source-mismatch family (byte-identical to `costtracker-perf-uncounted` W1
   CRIT + `charmgr-cost-fresh-instance` W2). **CONFIRMED** by `wf_fb8c0c61-b18`
   (`logs/discovery-wf_fb8c0c61-b18.json`): money-gate-reviewer + lane-v reachability +
   adversarial refuter all CONFIRM/CRITICAL, refuter failed to refute (resolves operator2's
   earlier money-gate=CRIT/lane-v=MAJOR split → unanimous CRIT on fresh evidence).
   **Pin `tests/unit/test_llmensemble_cost_uncounted_xfail.py` EXECUTED non-vacuous:** 1 xfailed
   (normal) / 1 FAILED (`--runxfail`, `init=None,gen=None`, leaky success path exercised).
   Shape = **structural threading** (decoupled from the undecided recording site — avoids the
   `lipsync-postproc-costkey` mis-shape trap; in-ensemble recording verified at Lane V).
   **SECONDARY leak DISPUTED (Rule #13, lane to confirm):** `prompt_optimizer` via
   `controller.py:709-718` → `prompt_optimizer.py:402` builds a 3rd fresh LLMEnsemble — agents
   split on `prompt_optimizer_enabled` default (money-gate/refuter: False⇒MAJOR; lane-v: True).
   I did NOT resolve it.
4. **idgate routed** (`d46102d`) then **re-anchored**: director-1 `233435f` records director2
   **WRAPPED**, co-sign carried as its **#1 next-task** (not ghosted). My routing event's
   "director2 online" premise was a stale heartbeat — the accurate state is co-sign CARRIED.
   director-1's rule: next director checks for the verification-report, **escalate only if
   stale-unanswered** on resume. Pod stopped → pod-off trip-wire already satisfied. No escalation
   warranted yet.

## OWED next coordinator (ALL lane-owned — track, do NOT author)
- **operator-1 Lane V:** `has-char-lora-hole`/`secondary-lora-hole` (`23c99e3`) — owed+UNSTARTED
  (`09b7674`; key = node-700 reachability + mutation, cite `--runxfail` per ADR-027).
- **operator2 Lane V:** `lipsync-syncnet-nan` (`1d30581`) + `audio-remux-notimeout` (`f108565`)
  — carried (`20-16-05Z`). On GOs → reconcile those 4 `fixed` rows → `verified`.
- **operator2 ratify:** `charmgr-cost-fresh-instance` provisional-CRITICAL (R-VERIFY-TIER).
- **director2 (on resume):** `idgate-failopen` Tier-A co-sign (#1 carried) → director-1
  dispatches fail-closed → operator-1 Lane V.
- **Pair-B director:** ADR-027 **FIX-1/2/4** (no pickup yet; FIX-1 will honestly re-grade
  Wave-1 "MET") + **brief `llmensemble-cost-uncounted`** (fix option b = post-call `log_llm`
  on the `usage` read at `_generate_anthropic:285`, no interface change; OR thread tracker into
  ctor — must cover the Rule #13 `prompt_optimizer` sibling).

## State
HEAD `9ead0df`, **11 ahead of origin, NOT pushed** (push user-gated). Pod STOPPED (billing closed).
Wave-2 `{fixed:4, open:22, verified:3}`. All 4 peers were heartbeating at orientation but
director2 has since wrapped (per `233435f`).

## Sharp edges
- **HEAD moved under me** — 3 peer commits (`823f36a`/`09b7674`/`233435f`) landed between my
  orientation snapshot (`32d5549`) and my first commit; Rule #7 re-anchor caught the new
  operator GO + director2-wrapped status. **Re-anchor (`git log -3`) before EVERY action.**
- **Default index phantom-polluted** — `git diff --cached` showed 1357 deletions that would
  revert the campaign; working tree == HEAD. **Path-mode commits only** (`git commit -m … --
  <paths>`); `git add` new files first. NEVER a bare `git commit`.
- **Pin shape vs undecided fix** — for a money leak whose recording SITE isn't decided, a
  spend-assert pin is shape-coupled to the unwritten fix (`lipsync-postproc-costkey` trap). Pin
  the **structural precondition that's provably false today** (tracker reaches the leaky object)
  and `--runxfail`-verify non-vacuity instead.
- **ADR-027 still holds** — cite the EXECUTED pin (`--runxfail` RED→GREEN) / operator GO, never
  the `wave_gate_check` status tally, as a correctness claim.
