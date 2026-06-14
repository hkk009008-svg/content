# Handoff — coordinator — 2026-06-14

**READ FIRST AS COORDINATOR.** 5th read-only cross-pair oversight seat (UNPINNED;
owns no lane; Rule #23-inert; send-only mailbox via `index-coordinator`). Predecessor:
`docs/HANDOFF-coordinator-2026-06-13.md` (Sessions 1–2). This doc = Session-3 (the
protocol capacity audit + its full execution). Filename carries no verdicts per the
new handoff-hygiene rule (`core.md` → "Session-wrap & handoff hygiene", lever #2).

## What this session did (user-driven, principal = user)

Resumed as coordinator → ran a **protocol capacity audit** → executed the entire
backlog it produced, in two waves.

### Audit (workflow `wf_6be2ee18-f4b`)
21 agents; 12 capacity levers, each steelman-tested. Headline: **80% of recent
commits were coordination/doc meta-work vs 20% production**; every lever's verdict
was `modify` (earned safety, never pruned — prune, don't raze).

### Wave 1 — Tier-1 (merged earlier this session, already on origin via push `2faac83`)
- MEMORY.md compacted 34.4KB→11.4KB (was silently truncating).
- `7c855ef` handoff-filename hygiene + standing "Git-tooling sharp edges" in `core.md`.
- `ee726fb` **R-VERIFY-TIER** (corpus's first verification-DEPTH cap).
- `9962aa3` committed a seat's orphaned 2→4-seat protocol WIP (user-authorized).

### Wave 2 — Tier-2 + Category-B (merged to main `9e2d20d`, **LOCAL-ONLY / UNPUSHED**)
Designed via `wf_a079da9e-87b` (specs grounded vs current code + adversarial #6 review),
then executed TDD, ci_smoke-green between each, on an isolated worktree, ff-merged:
- **Cat-B (deliverable):** `89e386d` budget-gate (SEEDANCE/FAL_SVD priced) · `530f176`
  forced-alignment write-only warning · `c8f931d` Suno V5 BGM router wired + cost_tracker
  + api_base fix · `f1addd3` **SyncNet** real mouth-energy Provider-1.5 scorer (Sonnet
  subagent, diff-reviewed + re-verified; 4 new + 60 regression green).
- **Protocol:** `91d47a5` #7 Rule-23 Tier-A/B co-sign classifier · `d31d42c` #8
  coordinator on-demand (§10) · `fb09270` #5 cursor-commit lint (opt-in `--git-root`).
- **#6 worktrees:** `9e2d20d` = a **DEFERRED migration plan**
  (`docs/superpowers/plans/2026-06-14-worktree-migration.md`), NOT merged code — the
  adversarial pass proved the naive cutover silently blinds seats to peer liveness;
  it mandates a read-path fix + a full-session validation between Step 1 and Step 2.
- `befc76c` committed a seat's orphaned `four-seat-extension.md` coordinator-formalization
  WIP (user-authorized), reconciled with #8's on-demand §10.

## Carry-forwards (status)

1. **PUSH main to origin — OWED, USER-gated.** `origin/main` is behind `9e2d20d` by the
   whole Wave-2 stack + orphan commits. User chose "handoff" before authorizing this push.
   `git log -1` + `git rev-list --count origin/main..main` to see the gap; push on user GO.
2. **#6 worktree cutover — DEFERRED to a cutover window.** Execute
   `docs/superpowers/plans/2026-06-14-worktree-migration.md` ONLY all-seats-quiesced;
   Step 2 is gated on the read-path fix (absolute `PRESENCE_DIR`) + Step-1-live-one-session.
   This is the highest-value remaining structural lever (kills the shared-tree sharp-edge class).
3. **Backfill `_TBD_` SHAs** in PROTOCOL-RULES-LOG Rules #21/#22/#23 (orphan `9962aa3`) +
   the new R-23-async + R-VERIFY-TIER addenda — a protocol-author seat.
4. **Orphan-author notice:** `9962aa3` (CLAUDE.md/rules-log) + `befc76c`
   (four-seat-extension.md) committed seats' orphaned protocol WIP — surfaced in those
   commit bodies; a `coordinator → all` fyi was OFFERED but not sent (user handoff'd first).
5. **#5 lint is opt-in:** run `scripts/check_coordination.py --git-root .` to flag
   standalone cursor-only commits (deliberately NOT wired into ci_smoke — no noise).

## Sharp edges (this session) — see also `core.md` "Git-tooling sharp edges (standing)"
- **Shared-tree collisions hit 3×** (orphaned CLAUDE.md WIP, a stale-default-index
  phantom, orphaned four-seat-extension.md WIP). Each resolved without sweeping peer
  work via: reseed default index (`git read-tree HEAD`) before merges; commit orphans
  pathspec-scoped; rebase + resolve. This IS lever #6's thesis — the fix is the plan in (2).
- **`| tail` masks git exit codes** — a ff-merge "Aborting" was hidden behind a piped
  `tail` reporting `0` (it was tail's exit). Capture `$?` un-piped for git gates.
- **Design-agent file:line drift:** the design workflow's anchors had ~3 hallucinated
  locations (Rule #23 in director-operator.md, #8's anchors). ALWAYS grep-verify an
  anchor before editing; never trust a spec's line numbers blind.
- **Committing peer content to instruction files trips the auto-mode guardrail** —
  needs explicit per-content user review (show the diff, get "yes") before it'll commit.

HEAD at wrap: **`9e2d20d`** (local; origin behind — push owed). ci_smoke OK. All seats
stopped at wrap. Coordinator offline until re-spawned (now on-demand per lever #8 §10).
