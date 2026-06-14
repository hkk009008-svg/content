# Handoff — coordinator — 2026-06-14 (Session-9)  [wrapped ~2026-06-15 00:0xZ]

**READ FIRST AS COORDINATOR.** On-demand 5th oversight seat (UNPINNED; owns no lane;
read-only on PRODUCTION code; commits ONLY test-only/inventory/docs/logs + coordination
via explicit pathspec). Predecessor: `docs/HANDOFF-coordinator-2026-06-14-s8-wave1-7of8-verified-4-seat-skills-shipped.md`
(Session-8; superseded). **This session DROVE WAVE-1 TO GATE-MET (8/8) AND PUSHED IT, then
seeded Wave-2.** Trust git, not this prose.

## State at wrap — TRUST GIT (this tree is LIVE; run `git log -1` + `git rev-list --count origin/main..HEAD`)
- **At final wrap: HEAD = origin/main = `5a4eb49`, 0 ahead / 0 behind — the FULL milestone + every wrap doc is PUSHED.**
  (The Wave-1-MET milestone first landed at `8b13310`; the team then pushed all wrap docs + 2 more commits to `5a4eb49`.)
  Push-state churned fast during wrap — **trust git, not these SHAs.** Once this handoff edit commits it will be 1 ahead until pushed.
- **The tree was LIVE with another coordinator-actor during wrap** — commit **`d2c7066`** (NOT mine) cleared the
  stale `aa-budget-nan-veto` "ratify-owed" inventory note (director-1-flagged `16:19:09Z`; director2 ACK `11:27:30Z`
  discharged → T3 §6c co-sign loop CLOSED both sides). The inventory is clean on that point. If you resume as coordinator,
  re-confirm there isn't a second coordinator-actor live before writing the inventory.
- **Wave-1 gate = MET** (`scripts/wave_gate_check.py 1` → `counts={verified: 8}`). Precise: **the 8 PLANNED Wave-1
  CRITICAL rows are verified — NOT "all money-loss closed."**
- **Wave-2 gate = UNMET. Open inventory = 32 total: 28 Wave-2 rows + 4 `defer` rows** (`ckpt-nan-json-token`,
  `ckpt-sceneclips-dead`, `ckpt-stage-notrestored`, `identity-arcface-embselect` — out of the Wave-2 gate). NOT opened (carry #1).
- `ci_smoke.py` OK. No locks held. Pod last-known STOPPED (untouched this session).

## What Session-9 did (user-driven; principal = user)

### A. Resumed + evidence-backed the web_research ruling (read-only fan-out)
- Session-start reconcile: gate UNMET 7/8, sole blocker `costtracker-perf-uncounted`. Phantom
  per-seat index verified (files exist + match HEAD) → tree clean; used explicit-pathspec all session.
- **Read-only verify fan-out `wf_e370ed39-bca`** (11 Explore/sonnet agents; `logs/discovery-wf_e370ed39-bca.json`):
  10/11 premises confirmed, **P1 (web_research "bounded") REFUTED** — `run_with_tools` is called
  **once-per-scene** by `scene_decomposer`/`dialogue_writer` (only `style_director` is 1/project) →
  spend scales with scene count. The SPLIT survived but its **severity premise flipped**.

### B. The ruling (user-blessed "proceed with recommendation")
- **web_research SPLIT** out of Task 7 → own row, severity **MAJOR** (not the MEDIUM "bounded" assumed;
  justified by P6 blast-radius isolation). **Wave-1 closes on its planned 8-row scope** (no-infinite-wave
  discipline — do NOT expand the gate for mid-wave sweep finds). **Task-7 scope** = `(a)` log increment +
  remove `record_api_call:407` dup + thread shared tracker thru 4 perf phases (Option-B audio-T5; Option-A
  SQLite-SUM REJECTED). **pure Pair-B, no lock/co-sign.** `aa-nan-budget-total` = NO row (subsumed `baac518`).
  Inventory `e00f6c2`; decision event `2d02716` released Task-7 to director2.

### C. Task-7 landed + verified → Wave-1 MET
- director2 implemented `10c1566` (placed `(a)` at the `log()` chokepoint — a **disclosed same-policy
  refinement** vs the ruling's "log_api AND log_llm"; tracked, not coordinator's to rule).
- **operator2 GO** (`5272065` report, beyond-pin: M1/M2/M3 RED non-vacuous, escape_paths=[], suite 2487p/0f,
  Lane V `wf_07b27cf2-cea`, impl≠verifier). **log()-refinement RATIFIED** (op2 grep-confirmed no production
  `log()` direct-caller — the concern I tracked). Reconciled `→ verified` (`f163145`) → **gate MET 8/8**.
  Milestone event `5bacf42`; **pushed `8b13310`** (user "push").

### D. Two NEW findings surfaced → verified → filed Wave-2 (nothing dropped)
- **`cost-spent-nan-poison` (CRITICAL, Wave-2)** — operator2-found + coordinator R-EVIDENCE. NaN-gate family
  **spend-side** sibling: `would_exceed`(:431)/`is_over_budget`(:440) read `spent_usd` with no isfinite guard,
  ASYMMETRIC to the `_finite_budget_or_block`-guarded `budget_usd`(:223). op2 demo: $100/$10 cap → gate dead.
  Fix = coerce non-finite cost→0 + WARN at `log()` (keep accumulator gate ALIVE; mirror-opposite of budget-nan's block).
- **`cost-conn-crossthread-drop` (MAJOR, Wave-2)** — director2-flagged + coordinator-verified `wf_fb9ff2f2-562`
  (`logs/discovery-wf_fb9ff2f2-562.json`): X1+X2 hold (real cross-thread sqlite + ProgrammingError fires),
  **X3 REFUTED = NOT silent** (logged WARNING+exc_info). Real-but-conditional+observable money-loss; PRE-EXISTING,
  out of Task-7 scope. Fix = `check_same_thread=False` + Lock. (The binary disposition_hint said "file only if all
  3 hold" — coordinator OVERRODE it: X3 refutes SILENT, not the DEFECT.)

### E. operator2 discharged R-VERIFY-TIER(B); inventory synced
- operator2 landed 5 strict-xfail pins (`21e8a5d`, non-vacuous + flip-correct). I flipped the 5 "pin owed"
  cells → real `tests/unit/test_*_xfail.py` paths (`84b176a`). Labeled-exempt: `spent-usd-reset-on-resume`
  (design-open), `perf-phase-no-gate` (test-infeasible).

## Carry-forwards (for the next coordinator)
1. **Wave-2 is NOT open.** Owe the **stub-contract spec BEFORE opening** (spec §7; predecessor carry #5).
   Then **director2 leads with C-1** `shot-spent-usd-never-written` (the `get_shot_spent` bridge — pinned, ready;
   director2 holding on "go"), with `cost-spent-nan-poison` (CRITICAL) close behind. Every Wave-2 money row
   already has a CI pin (operator2) — coverage is honest.
2. **Push-state is git-truth, not this prose.** At final wrap everything was pushed (HEAD=origin=`5a4eb49`, 0 ahead);
   the tree churned fast (full-team wrap + `d2c7066` note-clearance all pushed within the window). This handoff edit
   sits 1-ahead until pushed — **push user-gated**. Always `git rev-list --count origin/main..HEAD` before assuming.
3. **Open inventory = 32 total: 28 Wave-2 rows + 4 `defer` rows** (money / identity / silent-gate / checkpoint / http);
   2 new CRITICALs (C-1, cost-spent-nan-poison). The 4 `defer` (`ckpt-nan-json-token`, `ckpt-sceneclips-dead`,
   `ckpt-stage-notrestored`, `identity-arcface-embselect`) are out of the Wave-2 gate. spec §11 residuals still open
   (measure_lipsync_offset, conftest policy, over-cook proxy).
4. **Milestone-claim discipline:** any future "gate MET" must be PRECISE ("the N planned rows", never "all X closed").
5. **Fix directions recorded in the rows:** cost-spent-nan-poison = coerce+WARN (NOT block); cost-conn-crossthread-drop
   = check_same_thread=False + Lock; C-1 = get_shot_spent SQLite-SUM injected into the gate loop (integration test-infeasible).
6. **STRATEGIC FORK — open USER decision before Wave-2 *Pair-A* starts** (surfaced by director-1 `16:19:09Z`):
   **(A)** drive the Wave-2 Pair-A hardening rows (`has-char-lora-hole`/`secondary-lora-hole` share the `has_character`
   root · `idgate-failopen` [CROSS-LANE Tier-A co-sign; potential CRITICAL gate-bypass] · `coherence-silent` ·
   `identity-nan-arc-bypass`) **OR (C)** pivot to the pod-realism burn (ADR-024 dual-LoRA graft + ADR-025 max-wide
   re-measure — needs pod START + user auth). Surface to the user when Wave-2 opens; do not assume (A).
7. **Tech-debt carried (not lost):** T4 import-swap dedup deferred — operator-1 kept a local `_finite_or` byte-identical
   to `cinema.context._finite_or` (quality_max.py); fold into a Wave-2 cleanup. **PROGRAM-MANUAL.md has 83 advisory
   anchor-drifts** (director-1, this session) — fix-on-touch, **NOT gated by ci_smoke** (only ARCHITECTURE.md anchors
   are hard-gated; see [[doc_checker_same_line_blindspot]]).

## Sharp edges / lessons (this session)
- **Verify the PREMISE of a decision, not just the fix.** The web_research SPLIT rested on "bounded"; the fan-out
  refuted it → severity corrected MAJOR-not-MEDIUM. A ruling-from-prose would have under-prioritized a real money-loss.
- **A workflow's binary disposition_hint can mislead** — X3(silent) refuted ≠ defect refuted. Read the *reasoning*, not the booleans.
- **Phantom index ALL session** — every commit used `git commit -m "..." -- <path>` (`-m` before `--`); `git show --stat`
  confirmed 1–2 intended files each time; trust `git diff HEAD` not `git status`. A bare commit would have swept ~35 phantom paths.
- **`logs/` negation:** only `!logs/discovery-*.json` is tracked — name read-only verify artifacts `logs/discovery-<runid>.json`
  (a `ruling-verify-*.json` is gitignored). presence files are gitignored (on-disk edit IS the signal; no commit).
- **Verify-then-push:** held director2's unverified `10c1566` until operator2's GO, pushed the verified stack (mirrors S8 `c8c1645`).
- **Coordinator authored ZERO production code** — ruled, reconciled, gated, verified read-only; all fixes in-lane (director2) + verified (operator2).
- **A handoff is a SNAPSHOT of a LIVE tree — make state claims git-relative.** A read-only handoff-audit (`wf_1dbed6c2-05d`)
  caught this doc going stale *while it was being written*: the team re-activated, pushed everything to `5a4eb49`, and
  another coordinator-actor landed `d2c7066` (note-clearance) — all after the first draft's hard SHAs. Lesson: at wrap,
  re-run `git log -1`/`git rev-list --count` and fold the delta; don't hard-code `origin=X, N ahead` as if frozen.
- **Watch for a second coordinator-actor.** `d2c7066` is a `coord(inventory)` commit this session did NOT author —
  on a live tree the coordinator role can be picked up elsewhere. Confirm sole-coordinator before writing the inventory (§6f).

At final wrap: HEAD = origin = `5a4eb49` (0 ahead — full team wrapped AND pushed; this handoff edit is +1 until pushed,
user-gated). Trust `git log`, not these SHAs. Full-team wrap — all 4 seats + coordinator OFFLINE.
