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

## Session 2 — PM (2026-06-13, ~11:00–11:22Z) — LATEST, read this first

Re-onboarded as coordinator (user re-activated the seat after the Session-1 wrap),
ran a full dependency-ordered oversight pass, then **pushed the stack on explicit
principal direction**.

1. **3-task oversight, ordered upstream→downstream** via a read-only Workflow
   (`wf_5d39bbe3`, 7 Sonnet agents, adversarial-verify gating each phase):
   - **Sweep** — all 4 working seats WRAPPED/converged, **zero stalls, zero
     collisions**. Pair-B ran a fresh **PM2 session DURING the audit** (landed
     `65e9b88` auto-RIFE default-on) and director-1 formalized the §8.5 co-sign
     (`1b94dd7`) mid-audit — HEAD churned ~5× in 20 min; re-synced each step.
   - **Defect** — §8.5 char-landscape note is **landed + co-signed**; the
     "one `classify_shot_type` seam fix resolves both tiers" claim **HOLDS, high
     confidence** (independently re-derived; convergent with `1b94dd7`).
   - **Push-readiness** — stack coherent, ci_smoke green; verdict
     *ready-with-caveats* (the auto-RIFE caveat below).
2. **Surfaced (durable, pushed):**
   - `b922aa9` — `coordinator → all` **findings**: the char-landscape fix's
     **FULL blast radius = 5 `classify_shot_type` callers** (controller.py
     video_fallbacks +RUNWAY_GEN4 [Pair-B]; continuity_engine identity_threshold
     0.0→0.55 [Pair-A]; performance.py take-gating [Pair-A]; motion_render floor
     None→0.65 [Pair-B]; calibrate CSV) — §8.5 only nods to "video-API selection".
     Scope intel for the deferred joint routing brief, + 2 edge caveats.
   - `4c3b64f` — `coordinator → all` **fyi**: origin/main pushed; "nothing
     pushed" prose now stale.
3. **PUSH (principal-directed; OVERRODE the never-push invariant):** the standing
   all-seat USER-gate was lifted by an explicit user "push". Pushed
   `5c508d4..b922aa9` (53 commits) then `b922aa9..4c3b64f` — two **clean
   fast-forwards**. **origin/main is now CURRENT at `4c3b64f`, 0 ahead.**
   ⚠ This was a **one-time principal exception** — the seat's default remains
   **never push**; do NOT infer a standing push mandate.

## What Session 1 did (2026-06-13, ~09:00–10:48Z)
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

**Post Session-2 (LATEST):**
- **auto-RIFE `65e9b88` verify owed ON A PUSHED COMMIT** — default-on auto-RIFE
  (W1 §5.2) is public, principal-authorized + TDD-green (8 new + 70 regression),
  but operator2 wrapped PM2 flagging it **peer-WIP, not CONFIRMED**. The formal
  operator2 cross-verify is the one real carry-forward; watch Pair-B's next resume.
- **Char-landscape joint routing brief — still to author** (deferred to next
  Pair-B). Owners: director2 (author) + director (Rule #23 co-sign) + operator2
  (implement). The 5-caller blast radius + 2 caveats are in `b922aa9` — the brief
  must scope those, not just the §8.5 production/max mechanisms.
- **Stale "nothing pushed" prose everywhere** — all seat handoffs + presence +
  MEMORY.md still say "push USER-gated, N ahead, nothing pushed". FALSE now
  (origin/main == main == `4c3b64f`). Trust git, not the prose; fix-on-touch.
- **Session-1 items below are now mostly CLOSED:** §8.5 placed (`547cf12`) +
  co-signed (`1b94dd7`); director2 consumed the lip_sync/forced-alignment action
  events in PM2 (cursor 11:13:40Z); Rule #23 object-window on `fd334d3` closed
  (no objection). director2's lip_sync loud-gate + forced-alignment build remain
  **Pair-B lane work** (W1/W2), not coordinator items.

**Session-1 (historical):**
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
- ~~**Everything UNPUSHED** (push USER-gated)~~ → **PUSHED in Session-2** (see
  top): origin/main == main == `4c3b64f`, 0 ahead. Default stays never-push.

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
- **Session-2 lesson — HEAD churns mid-audit:** during a long read-only audit on
  a live 4-seat tree, HEAD moved ~5×. `git diff --stat HEAD` can show ~500 phantom
  "deletions" when the default index predates recent commits; **`git read-tree
  HEAD` clears it**, but if HEAD moves again right after, `--stat` lies again until
  you re-reseed. Definitive truth = `git cat-file -p HEAD:<f>` / `git diff HEAD
  -- <f>` (empty = clean) / `git log -1` re-checked between steps. Workflow agents
  on an unpinned seat inherit the same stale-index trap — tell them to avoid
  `git status`.

HEAD at Session-1 wrap: `b123632`.

**HEAD at Session-2 wrap: `4c3b64f` — origin/main CURRENT (0 ahead, two
fast-forwards this session). Pod STOPPED ($0 billing). ci_smoke OK. coordination
clean (4 INFO). Coordinator events `b922aa9` (findings) + `4c3b64f` (fyi) pushed;
this handoff doc is the only local artifact committed at wrap (presence is
gitignored, updated locally).**
