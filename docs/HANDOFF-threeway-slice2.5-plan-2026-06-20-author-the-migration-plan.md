# HANDOFF — Cross-Provider Seat Topology, Slice 2.5: AUTHOR THE PLAN (2026-06-20)

**Read this first if you were prompted "continue from plan slice 2.5."** Companion docs:
the tracking stub `docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md`
(the scope source of truth — read it in full); the Slice-2 plan
`docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.md` (its **D-B section** holds the
exact edit-site inventory); spec §8.7/§8.8 + §11; ADR-030 (Slice 1) + ADR-031 (Slice 2) in `DECISIONS.md`;
the `threeway/` subsystem section in `ARCHITECTURE.md` (§13A).

## TL;DR — what "continue from plan slice 2.5" means now

Slice 2 is **DONE + MERGED** to `main` (its §11 gate is green), so the spec §11 boundary that gated Slice 2.5
is now satisfied. **"Continue from plan slice 2.5" = AUTHOR the Slice 2.5 implementation plan** — turn the
tracking *stub* into a full TDD plan via `superpowers:brainstorming` → `superpowers:writing-plans`, written to
`docs/superpowers/plans/`. This is a **PLANNING** task. Do **NOT** execute the migration yet, do **NOT** re-do
Slice 2, do **NOT** re-author the Slice 2 plan.

## Exact state — verify with git, trust git not this prose

- **Slice 2 is merged.** As of this handoff, `origin/main` @ `2a932ac0` contains the Slice-2 ref-bus
  (`threeway/refstore.py`, `gitcas.py` plumbing, Pair B, the §11 race gate) + **ADR-031** (Slice 2) and the
  Slice 2.5 stub. The §11 Slice 2 DoD is MET: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest
  tests/unit/test_threeway_*.py -q` → **152 passed**; `scripts/ci_smoke.py` OK; `scripts/check_no_ceremony.py`
  clean. (The world moves fast on this repo — re-anchor: `git fetch origin && git log --oneline origin/main -5`
  and confirm `git merge-base --is-ancestor 4344b17f origin/main`.)
- **ADR numbering:** `ADR-031` = Slice 2 (taken). A concurrent seat already merged `ADR-032` (verification
  dispatch). **Your next ADR for Slice 2.5 is ADR-033** — grep `DECISIONS.md` for the current max before
  assigning.
- **The Slice 2.5 stub** (`…-slice2.5-legacy-bus-migration.md`, identifier `threeway-slice2.5-legacy-bus-migration`)
  is on `main`. It is the scope source: read it first.

## What to plan (from the stub — the full edit-site inventory is verified there)

Slice 2.5 migrates the **live 4-seat campaign mailbox** (`coordination/`) onto the Slice-2 `refs/threeway/events`
substrate. Three scope pillars (all in the stub §Scope; exact line refs verified there + in the Slice-2 D-B section):

1. **Make `coordinator`/`coordinator2` first-class *receiving* seats** (today `coordinator` is send-only,
   `coordinator2` does not exist) across **the seat-list copies** — verified current line refs (re-grep before editing):
   - `scripts/protocol_mailbox.py:11` `SEATS = ("director", "director2", "operator", "operator2")` — the canonical
     ROOT that propagates to `RECIPIENTS` / `check_coordination.py ROLES`. **Spec §8.7's "four files" OMITS this —
     treat it as the 5th sync target (the real root).**
   - `coordination/bin/send-event` (FROM/TO whitelists), `coordination/bin/consume-events` (ROLE whitelist +
     usage), `scripts/check_coordination.py` (hardcoded seat regexes + the cursor regex), `scripts/status.py:126`
     `_MAILBOX_SEATS` (an independent copy) + its argparse help (used at `scripts/status.py:232`).
   - This is a **Rule #13 symmetric-audit** problem: the seat list lives in ~6 independent copies; the plan must
     update **every** copy or the bus silently breaks for the new seat.
2. **Cursor backfill** ISO-timestamp → scalar `seq` for the `seen/<seat>.txt` files (4 → 6) + per-seat
   `refs/threeway/cursors/<seat>` refs (the Slice-2 cursor primitive); update `check_coordination.py`'s cursor
   regex (`_CURSOR_RE`, ISO-only today → fatal on a scalar). Must be **byte-reversible** (archive the ISO values).
3. **Shadow → single-writer cutover** (staged, NOT big-bang): `events/`+`index/` runs as a **read-only
   projection** alongside `mailbox/sent/` first (legacy mailbox stays authoritative), ≥1 full campaign cycle with
   a divergence-check showing zero drift, canary one pair, then a single-writer authority cutover. **NO
   dual-write authority at any point.** Define the reverse-projection (post-cutover rollback) before cutover.

**Acceptance gate the plan must encode** (stub §Acceptance gate): legacy checkers (`check_coordination.py`,
`status.py`) stay green across the seat additions; `coordinator`/`coordinator2` send AND receive; cursor backfill
byte-reversible + the ISO→seq map reproducible from `sent/`; no event lost/duplicated across the shadow→authority
cutover (a reconciliation count); no dual-write-authority window (audited). Reuse `preflight_bus_init` (Slice-2
Task 3c) so the migration init is fail-closed/non-destructive.

## How to proceed (the planning procedure)

1. `git fetch origin`; re-anchor on `origin/main`; re-read the stub + the Slice-2 D-B section + spec §8.7/§8.8.
2. `superpowers:brainstorming` — pin intent + the migration shape (shadow→canary→cutover; the reverse-projection;
   the divergence-check instrument). **Surface tradeoffs to the user** (this touches the live bus — see Risk).
3. `superpowers:writing-plans` — author `docs/superpowers/plans/2026-06-20-cross-provider-seat-topology-slice2.5-…md`
   as TDD tasks (one commit per task; per-task spec + code-quality review on execution). Encode the acceptance gate
   as mutation-proven, non-vacuous tests (ADR-028: zero ceremony). Mirror the Slice-2 plan's chunk structure +
   conventions (the `env -u GIT_INDEX_FILE` test prefix, explicit-pathspec commits, Co-Authored-By trailer).
4. Get the user's sign-off on the plan (and on any surfaced decisions) **before** any execution. Execution is a
   SEPARATE later step (subagent-driven-development, Opus) — **not** part of this handoff.

## ⚠ The central risk — this touches the LIVE campaign bus while seats are ACTIVE

Unlike Slice 2 (an additive, isolated `threeway/` package), Slice 2.5 edits the `coordination/` mailbox the
**live 4-seat campaign uses right now**. At the time of this handoff the shared working tree was **busy**:
a peer seat was mid-work on `feat/reviewer-result-consumer` (uncommitted changes), plus many `.codex/worktrees`
and `.claude/worktrees`. Implications for the PLAN (and especially for the eventual execution):
- **Shadow-first is mandatory** (stub §Shadow/canary) — no big-bang, no dual-write authority. The legacy
  `mailbox/sent/` stays authoritative until a verified, zero-divergence cutover.
- **Timing:** the eventual *execution* should run when bus activity is quiet, or be structured so the seat-list
  additions are backward-compatible (additive) and can't break an in-flight seat's send/consume.
- **Shared-tree discipline:** re-anchor on git refs before every action; **do NOT switch the checkout while a peer
  has uncommitted work**; `env -u GIT_INDEX_FILE` on every git-touching test (per-seat index pollution); expect
  `git status`/`diff` to lie under peer activity — verify against `git show HEAD:<path>` / refs.

## What NOT to do

- Do NOT execute the migration in this session — **author the plan only** (the user said "continue from PLAN").
- Do NOT re-do Slice 2 or re-author the Slice 2 plan (both done + merged).
- Do NOT create a dual-write-authority window on the bus at any point.
- Do NOT big-bang the cutover — shadow → canary → single-writer, with a reconciliation count.
- Do NOT touch the live mailbox without the shadow-first design + a defined reverse-projection.
- Do NOT switch the shared checkout or commit on a peer's branch while a peer has uncommitted work.
- Do NOT reuse `ADR-031`/`ADR-032` — your Slice 2.5 ADR is the next free number (grep `DECISIONS.md`).

## Subagent model = OPUS (standing user directive). Planning subagents + eventual implementers all Opus.

## After the plan is green
Per spec §11, Slice 2.5 is sequenced **before/with Slice 3** (strategic loop: make `co_sign_satisfied`
(`threeway/tier.py`) return True for T2 = other-pair operator `co_sign`, T3 = `re_verify` + two `human_approval`).
Plan Slice 3 only after Slice 2.5's gate is green.

---
*Authored 2026-06-20 from an isolated worktree off `origin/main @ 2a932ac0` (the shared checkout was held by an
active peer seat). Slice 2 shipped via PR #16 (rebase-linear). This handoff scopes the PLANNING of Slice 2.5; the
stub holds the verified edit-site inventory; the Slice-2 plan's D-B section is the companion.*
