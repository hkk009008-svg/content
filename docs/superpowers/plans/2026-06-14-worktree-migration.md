# Per-Seat Git Worktree Migration — Implementation Plan (Lever #6)

> **For agentic workers:** REQUIRES superpowers:executing-plans. **STATUS: DEFERRED — execute in a CUTOVER WINDOW only.** This is the one capacity lever that CANNOT be safely completed in a normal session: the adversarial safety review (workflow `wf_a079da9e-87b`) found that Step 2 silently blinds seats to peer liveness unless a read-path fix lands first, and it mandates a full multi-seat validation session *between* Step 1 and Step 2. Do not execute Step 2 outside a deliberate, all-seats-quiesced cutover.

**Goal:** Replace the shared working tree + per-seat `GIT_INDEX_FILE` model with proper per-seat `git worktree add --detach`, eliminating an entire recurring sharp-edge class (phantom/stale index, skip-worktree pollution, pathspec-or-sweep discipline, case-rename landmines) and retiring ~2,118 LOC of index-management tests.

**Why (audit wf_6be2ee18-f4b, lever #6):** the shared tree generated 6 distinct recurring failure classes; this session alone hit two of them live (a merge blocked twice by index/WIP hazards). Worktrees give each seat its own index *by construction* — the failure class disappears rather than being mitigated each session.

**Provenance:** design spec + adversarial safety verdict in workflow `wf_a079da9e-87b` (the `lever6-worktrees` spec + `verify:#6-migration` verdict, `safe_as_written=false`).

---

## ⚠ Adversarial safety verdict — REQUIRED before Step 2 (do not skip)

`safe_as_written: false`. The naive "relocate artifacts → switch to worktrees" sequence **silently blinds every seat to peer liveness**:

> Every protocol doc instructs seats to read peer heartbeats via the RELATIVE path `coordination/presence/<seat>-heartbeat.ts`. `coordination/presence/` is gitignored, so it does **not exist** in a linked worktree's working tree. A seat in a linked worktree reading the relative path gets "file not found" — no error, just absent/stale liveness. This is the original `ab9925d` rejection reason, restated for the **read** side. Step 1 fixes only the WRITE side.

**Required before Step 2 (gates):**
1. **Read-path fix.** Seats in linked worktrees must read peer heartbeats via an ABSOLUTE path. Provide it at launch: `export PRESENCE_DIR="$(cd "$(dirname "$(git rev-parse --git-common-dir)")" && pwd)/coordination/presence"`; update every protocol doc that says "read the peer heartbeat" to use `$PRESENCE_DIR/<seat>-heartbeat.ts`. (Alternative: per-worktree symlink `ln -s /abs/Content/coordination/presence <wt>/.claude/presence-link`.)
2. **`_sync_seat_index` removal is gated** on ALL seats being off `GIT_INDEX_FILE` first (else a still-D-a seat's index drifts → phantom mass-deletions return). Confirm `env | grep GIT_INDEX_FILE` is empty in every terminal before removing it; otherwise keep it as a no-op (it already returns early when `GIT_INDEX_FILE` is unset).
3. **Do NOT cut the `env -u GIT_INDEX_FILE` subagent rule** until worktrees are confirmed stable over a full session (the skip-worktree pollution root cause is still unidentified — hook comment line ~112).
4. **Step 1 must be live for ≥1 full multi-seat session** with confirmed heartbeat writes to the main tree from a linked worktree, before Step 2.

---

## Step 1 — Hook write-path portability (SAFE; no-op in single-tree; prerequisite)

**File:** `.claude/hooks/update-state.sh` (active copy is the MAIN-tree one, invoked by absolute path in `.claude/settings.local.json:75,85`).

Current writer (`_stamp_presence`, ~lines 55–66): after `cd "$(git rev-parse --show-toplevel)"` (line 38 — the *per-seat* worktree root), it `mkdir -p coordination/presence` and writes `coordination/presence/${seat}-heartbeat.ts` **relative** → in a linked worktree this silently lands in the wrong (gitignored, peer-invisible) dir.

- [ ] **Step 1a — RED test** in `tests/unit/test_presence_heartbeat_split.py`: `test_writes_heartbeat_to_main_tree_via_git_common_dir`. `git init` a tmp repo; `git worktree add --detach <tmp>/seat-wt`; awk-slice `_stamp_presence` (same pattern as the existing tests); run it with `cwd=<tmp>/seat-wt`, `CLAUDE_SEAT=director`; assert the heartbeat appears at `<tmp>/coordination/presence/director-heartbeat.ts` (the MAIN tree), NOT `<tmp>/seat-wt/coordination/presence/`. Fails before 1b.
- [ ] **Step 1b — implement.** In `_stamp_presence`, compute a shared base from git-common-dir's parent and write there (inline so the awk-slice test still captures one function):
  ```sh
  local base
  base="$(git rev-parse --git-common-dir 2>/dev/null || echo .)"
  base="$(cd "$(dirname "$base")" 2>/dev/null && pwd || echo .)"
  mkdir -p "$base/coordination/presence"
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$(git rev-parse --short HEAD 2>/dev/null || echo '?')" \
    > "$base/coordination/presence/${seat}-heartbeat.ts"
  ```
  In the single main-worktree (and non-git pytest tmp) cases this resolves to the same path as today → behavior-identical; only linked worktrees differ.
- [ ] **Step 1c — same treatment for STATE.md** if/where the hook writes it relative (verify; STATE.md is informational + gitignored, lower-stakes, but relocate for consistency so cross-seat status is shared).
- [ ] **Step 1d — verify.** Existing `test_presence_heartbeat_split.py` + `test_index_autosync.py` + `test_skip_worktree_clear.py` all green (non-git tmp → fallback path unchanged); new test green; `ci_smoke` OK. Then manually exercise: run a tool call from a linked worktree, confirm `cat /abs/Content/coordination/presence/<seat>-heartbeat.ts` updated.
- [ ] **Step 1e — commit** (pathspec: hook + the two/three test files).

**Caveat (why Step 1 is deferred-with-Step-2, not landed eagerly):** Step 1 is a no-op in the current single-tree world and stays production-unexercised until worktrees exist. Land it AT the cutover (immediately before Step 2) so the portability path is exercised by real linked-worktree usage right away — not dormant + untested-in-prod in the hook that runs on every tool call.

## Step 2 — Adopt `git worktree add --detach` per seat (CUTOVER WINDOW ONLY)

- [ ] Gates 1–4 above satisfied (read-path fix landed; index rule intact; Step 1 validated ≥1 session).
- [ ] Per-seat launch block: `git worktree add --detach <path>/<seat>` (`--detach` sidesteps the "worktrees force a branch" objection — verified: detached HEAD shares `main`'s commit, no branch needed). Each worktree needs its own `.claude/settings.local.json` copy so the hook fires.
- [ ] Launch each seat with `PRESENCE_DIR` exported (read-path fix) and **without** `GIT_INDEX_FILE` (worktrees isolate the index by construction).
- [ ] Once all seats are confirmed on worktrees (no `GIT_INDEX_FILE` anywhere): reduce/remove `_sync_seat_index()` and `_clear_skip_worktree()` in the hook; retire the now-moot index-management tests (`test_index_autosync.py`, `test_skip_worktree_clear.py`, and the index portions of `test_four_seat_coordination.py` — ~2,118 LOC across the named files).
- [ ] Update `docs/protocol/claude/four-seat-extension.md` §8 cutover + `director-operator.md` git-mechanics + `coordination/README.md` to the worktree model; update MEMORY.md's `[[operational_sharp_edges_git_tooling]]` (the retired sharp edges).

## Rollback

Step 1 is behavior-identical in single-tree — revert is a no-op. Step 2: stop launching seats in worktrees, re-export `GIT_INDEX_FILE`, `git worktree remove` each; the shared-tree model is untouched underneath.

---

**Net:** all of #6's design (incl. the adversary's critical read-path finding and the validation gates) is captured and ready. Execution is intentionally gated on a cutover window because the safety verdict requires an inter-step validation session — it is not safely completable in a normal working session.
