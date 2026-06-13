# Backlog — Cross-cycle ideas, observations, candidates

**Established:** Protocol Bundle v5 (ship at this commit), per the
"two seats of one team" reframe.

This is a shared-visible workspace for "interesting but not cycle-N"
items. Any seat (any of the four — directors or operators) can add a row;
director-seat typically curates (moves promising items to
`POST-ROADMAP-2026-05-24.md` picks); operator-seat can claim
Lane-D-style items (documentation, refactors, doc-sync candidates)
for execution per Lane D discretion.

**Either-seat write rules:**
- Adding an item: low-friction. Just append a row. No approval gate.
- Moving an item to POST-ROADMAP picks: director-seat (strategic
  decision).
- Claiming an item for execution: either seat, with mailbox-event
  narration (per Rule #2 signaling).

**Retirement criteria (operator-managed):** items not touched in 3+
cycles may be moved to a future "Stale candidates" section (not
deleted; deprioritized). Formal retirement criteria TBD in v5.1+
once data accumulates.

---

## Active candidates

| ID | Surfaced by | Date | Description | Suggested seat | Priority hint |
|---|---|---|---|---|---|
| B-004 | operator (Lane V #5 G4) | 2026-05-26 | IterationPanel UI polish — two items deferred with rationale in director-seat's own S17 review (commit body of `16ce51a`): **m2** Escape-key dismissal for the panel drawer (currently only closes on Cancel / Generate-success / explicit X); **m3** Non-JSON 502 status context surfacing (current behavior: 502 with HTML body throws and IterationPanel's catch block shows a generic "Network error" — should preserve the HTTP status code + best-effort body extract for operator debugging). Both are accessibility / UX polish; neither blocks Surface A functional use. Cleanest fold: bundle with the next IterationPanel touch (S18 verb DSL UI extension OR S17 follow-up). | either seat (small Lane A) | low — pure UX polish; no functional blocker. Pick up opportunistically when adjacent UI work is in flight. |

---

## Recently graduated to POST-ROADMAP

| ID | Description | Promoted at SHA |
|---|---|---|

_(None yet.)_

---

## Recently completed

| ID | Description | Completion SHA |
|---|---|---|
| B-003 | **Shipped Option E** (gitignore STATE.md + remove amend logic) per `docs/B-003-design-exploration.md`. STATE.md added to `.gitignore`; `git rm --cached STATE.md`; `.claude/hooks/update-state.sh` simplified from 148 → 102 LoC (removed: staged-set check, reflog gate, `git add` + `git commit --amend` lines, marker-loop-prevention comment block). Hook now: detects HEAD move via the existing marker file, regenerates STATE.md on disk, exits. No git history modification. Eliminates BOTH the B-003 compound-call divergence AND the B-002 stale-by-one cosmetic. Compound `git commit && git push` is now genuinely safe. The historical STATE.md content in pre-cutover commits is left in place (inert artifact). Decision authorized by user-principal via AskUserQuestion at 2026-05-26 cycle 8 close. | _(this commit)_ |
| B-002 | _(Superseded by B-003 Option E.)_ Original fix added a reflog gate to `.claude/hooks/update-state.sh` to skip the amend on non-commit HEAD moves (reset / checkout / rebase / pull). That fix correctly addressed its named scope but didn't address the compound `commit && push` timing window — B-003 surfaced that gap. Option E removes the amend entirely, making both B-002's reflog gate and the timing-window problem moot. The B-002 reflog gate is gone in the simplified hook. | `f19d4d3` (original) → superseded by B-003 |
| B-001 | Added unhappy-path test recipe to `docs/MIGRATION-PATTERN-pydantic-caller.md` §"Unhappy-path test recipe" (one template-level section covers all P1-3 migrations) + 2 example tests in `tests/unit/test_project_models.py::TestMigratedCaller` (`test_project_model_validate_raises_on_missing_id`, `test_project_model_validate_raises_on_malformed_scenes`) pinning the `ValidationError`-at-boundary contract. Closes operator-seat Lane V #3 F2 advisory. | `b1d36d2` |
