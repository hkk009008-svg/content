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
| B-002 | director-seat (cycle-7 F1 cite-fix push attempt; force-with-lease recovery at `6e1deb0`) | 2026-05-25 | **Fix `.claude/hooks/update-state.sh` to amend ONLY when an actual new commit landed via `git commit`, NOT on every HEAD change.** Current behavior: the marker-vs-HEAD check (`CURRENT != LAST`) treats `git reset`, `git checkout`, `git pull --rebase`, and other HEAD-moving operations as "new commit happened" and amends accordingly. This re-amends already-pushed commits (rewriting their SHAs from origin's view) and produces non-fast-forward divergence on the next push attempt. Recovery requires force-with-lease (see cycle-7 `6e1deb0` body for the recovery pattern). **Suggested fix:** inspect `git reflog -1 --format=%gs` for the reflog message — if it starts with `commit: ` or `commit (initial): `, proceed with amend; if it starts with `reset:`, `checkout:`, `rebase:`, `pull:`, etc., skip. Alternative: stash current marker before HEAD-moving ops and restore after. Estimate: ~30-45 min Lane A in main context (script edit + test by intentionally triggering each operation type + verifying no spurious amend). | director-seat (tooling work) OR operator-seat (Lane D-style hooks work) | medium-high — actively blocks rapid commit+push workflows; cycle-7 hit this twice and needed force-with-lease recovery. Worth fixing before any next director-seat session that ships multiple consecutive commits |

---

## Recently graduated to POST-ROADMAP

| ID | Description | Promoted at SHA |
|---|---|---|

_(None yet.)_

---

## Recently completed

| ID | Description | Completion SHA |
|---|---|---|
| B-001 | Added unhappy-path test recipe to `docs/MIGRATION-PATTERN-pydantic-caller.md` §"Unhappy-path test recipe" (one template-level section covers all P1-3 migrations) + 2 example tests in `tests/unit/test_project_models.py::TestMigratedCaller` (`test_project_model_validate_raises_on_missing_id`, `test_project_model_validate_raises_on_malformed_scenes`) pinning the `ValidationError`-at-boundary contract. Closes operator-seat Lane V #3 F2 advisory. | _(this commit)_ |
