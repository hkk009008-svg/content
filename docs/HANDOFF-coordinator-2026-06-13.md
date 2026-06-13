# Handoff — coordinator (read-only oversight seat) — 2026-06-13

**READ FIRST AS COORDINATOR.** You are the **5th seat**: read-only cross-pair
oversight for the user-principal. NOT in Pair A/B; you own **no lane**
(Rule #23-inert). Two pairs do the work — **Pair A** (`director`+`operator` =
image-gen/identity/realism), **Pair B** (`director2`+`operator2` =
video/assembly/delivery). You watch, surface collisions/stalls/cost-flags,
answer the principal, and (since this session) can **notify** via mailbox.

## What this seat is + how to operate it
- **UNPINNED**: `CLAUDE_SEAT` + `GIT_INDEX_FILE` unset. Default posture = read-only.
- **Watch** via: `coordination/presence/*.md` + `*-heartbeat.ts` (liveness),
  `coordination/mailbox/sent/` (authority > presence, Rule #8), `git log`
  (tiebreaker). **Trust `git diff --quiet HEAD -- <f>`, NOT `git status`** —
  an unpinned `git status` reads the stale default index and shows committed
  files as phantom `MM`.
- **Mailbox (SEND-ONLY)**: `coordinator` is a registered send-only pseudo-seat
  (vocab `fd334d3`) — a valid `<from>` only, never a `<to>`, no cursor (the
  mirror of `all`, which is `<to>`-only). Send with:
  `GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-coordinator" coordination/bin/send-event coordinator <to> <kind> "<subj>" <<'EOF' … EOF`
  then commit the staged event pathspec-scoped. You **never consume** (no
  `seen/coordinator.txt`). Reach the coordinator via the principal, not send-event.
- **Commits (ONLY under explicit user direction)**: seed `.git/index-coordinator`
  (`GIT_INDEX_FILE=… git read-tree HEAD`), edit the worktree, then
  `GIT_INDEX_FILE=… git commit -m "…" -- <pathspec>` (partial commit — cannot
  sweep peers even if HEAD moves). **Push stays USER-gated; never push.**

## What this session did (2026-06-13, ~09:00–10:48Z)
1. **Onboarded** + announced the seat (director-1 durably announced me at
   `e38b9fb`; later self-announced via mailbox once send-capable).
2. **Align audit** (read-only Workflow `wf_ed13f2b4-0de`, 10 agents,
   investigate→adversarial-verify) across both lanes:
   - Pair-B forced-alignment: **PARTIAL/BUILT_BUT_DEAD** — module correct, but
     `whisperx` absent (CPU-whisper only), gate opt-in, and the sidecar is
     WRITE-ONLY (`load_alignment_json` zero callers; `lip_sync.py` no alignment
     imports; `audio/srt.py` deleted).
   - Pair-B SyncNet gate: **WIRED_BROKEN** — pkg absent → ffprobe duration
     heuristic → falsely-green 0.8 final gate (`auto_approve.py:495` →
     `review/controller.py:324`).
   - Pair-A determinism routing: **WIRED_WORKING** — all DeepFace align sites
     routed (the "unrouted siblings" memory note was STALE; `970015b` fixed it).
   - Pair-A determinism correctness: **PARTIAL** — guard correct on both
     backends; Linux/TBB pod re-confirm of man-0.870 still OPEN (pod-bound).
3. **Shipped (user-directed; all ci_smoke-green, pathspec, UNPUSHED)**:
   `fe8e7c6` (alignment.py docstring → write-only reality),
   `ed24add` (ARCHITECTURE.md §11.1 → siblings ROUTED `970015b`),
   `fd334d3` (coordinator send-only vocab + 5 regression tests, 11 pass),
   `84aef13` (4 mailbox events).
4. **Mailbox (84aef13)**: →all (seat live), →director (§11.1 done → skip),
   →operator (§11.1 Lane-D done → skip), →director2 (lip_sync loud-gate HELD +
   dead-chain map).

## Open items for the next coordinator
- **Rule #23 object-window** on `fd334d3` (added the coordinator sender under
  user-override = cross-cutting). If any seat objects → `git revert fd334d3`.
  No objection seen as of wrap.
- **Did the seats consume the events?** director/operator/director2 have unread
  `coordinator` events (`84aef13`); operator2 has the `all`. Confirm they
  processed (esp. director/operator skip §11.1; director2 picks up the loud-gate).
- **HELD for director2** (NOT shipped — code in their lane): `lip_sync.py`
  loud-gate (WARNING on absent `SyncNetInstance` at `lip_sync.py:408`) — a
  falsely-green lip-sync gate. Plus the Pair-B forced-alignment capability
  build (W1/W2: install whisperx/syncnet on the pod, wire `load_alignment_json`,
  rebuild subtitles).
- **Pair A**: Task-4 GO landed (`6aad3b2`, pod acceptance gate passed) +
  ADR-025. The Linux/TBB determinism re-confirm (A2) was still OPEN at wrap;
  pod is now STOPPED (`b123632`) so it's deferred-on-restart.
- **Everything UNPUSHED** (push USER-gated).

## Sharp edges (held)
- **MM phantom**: unpinned `git status` reads the stale default index → shows
  committed files as `MM`. Verify with `git diff --quiet HEAD -- <f>`; reseed
  the default index with `git read-tree HEAD` to clear.
- **Seeded-index commits**: always `GIT_INDEX_FILE=.../index-coordinator` +
  pathspec partial commit. A bare `git commit` from the unpinned default index
  could sweep peers / phantom-delete.
- **Send-only model**: coordinator is from-only (mirror of `all` being to-only)
  — that's why the vocab change was 2 lines + no cursor. Do NOT add coordinator
  to `ROLES` (would demand a `seen/coordinator.txt`).
- **HEAD moves fast** (4+ live seats): `git log -1` before every commit;
  partial pathspec commits are the safety boundary.

HEAD at wrap: `b123632`. Pod STOPPED ($0 billing). ci_smoke OK. All coordinator
artifacts clean vs HEAD.
