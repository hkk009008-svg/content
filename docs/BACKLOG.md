# Backlog — Cross-cycle ideas, observations, candidates

**Established:** Protocol Bundle v5 (ship at this commit), per the
"two seats of one team" reframe.

This is a shared-visible workspace for "interesting but not cycle-N"
items. Either seat (director-seat or operator-seat) can add a row;
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

_(None active — B-002 closed at this commit.)_

---

## Recently graduated to POST-ROADMAP

| ID | Description | Promoted at SHA |
|---|---|---|

_(None yet.)_

---

## Recently completed

| ID | Description | Completion SHA |
|---|---|---|
| B-002 | Added reflog gate to `.claude/hooks/update-state.sh` between the staged-set check and HEAD_SHA capture. The hook now inspects `git reflog -1 --format='%gs'` and proceeds with the STATE.md regen + amend only when the most recent reflog action matches `commit:*` or `commit (*` (covers `commit:`, `commit (initial):`, `commit (amend):`, `commit (merge):`, `commit (cherry-pick):`). Non-commit HEAD moves (`reset:`, `checkout:`, `rebase ...:`, `pull:`, `merge ...:`, etc.) now silently re-anchor the marker to the new HEAD and exit clean — no spurious amend, no SHA-rewrite of already-pushed commits, no force-with-lease recovery needed. Closes the cycle-7 surface scenario at `6e1deb0`. | _(this commit)_ |
| B-001 | Added unhappy-path test recipe to `docs/MIGRATION-PATTERN-pydantic-caller.md` §"Unhappy-path test recipe" (one template-level section covers all P1-3 migrations) + 2 example tests in `tests/unit/test_project_models.py::TestMigratedCaller` (`test_project_model_validate_raises_on_missing_id`, `test_project_model_validate_raises_on_malformed_scenes`) pinning the `ValidationError`-at-boundary contract. Closes operator-seat Lane V #3 F2 advisory. | `b1d36d2` |
