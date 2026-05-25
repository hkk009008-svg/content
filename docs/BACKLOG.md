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
| B-003 | director-seat (cycle-8 P1-3 part 6 push; force-with-lease recovery at `b28b8b4`) | 2026-05-25 | **Compound `git commit && git push` in a single Bash tool call still produces hook-induced divergence after B-002's fix.** The PostToolUse hook fires AFTER the entire Bash tool call (not between commands in `&&`), so push goes out with the pre-amend SHA and the hook then amends STATE.md locally → local-ahead/origin-behind divergence requiring force-with-lease recovery. **Workaround in effect:** separate-Bash-call discipline (commit in one Bash call, push in another). **Exploration complete (2026-05-26):** see `docs/B-003-design-exploration.md` for 5-option analysis. Director-seat lean: **Option E (gitignore STATE.md, remove amend logic) — eliminates both B-003 divergence AND B-002 stale-by-one at the architectural level.** Decision required before implementation; user-principal sign-off needed for the shift from "STATE.md as commit artifact" to "STATE.md as purely-local file." | director-seat (tooling) OR operator-seat (Lane D-style hooks work) | medium — workaround functional; exploration writeup done; ship decision is the next gate |

---

## Recently graduated to POST-ROADMAP

| ID | Description | Promoted at SHA |
|---|---|---|

_(None yet.)_

---

## Recently completed

| ID | Description | Completion SHA |
|---|---|---|
| B-002 | Added reflog gate to `.claude/hooks/update-state.sh` between the staged-set check and HEAD_SHA capture. The hook now inspects `git reflog -1 --format='%gs'` and proceeds with the STATE.md regen + amend only when the most recent reflog action matches `commit:*` or `commit (*` (covers `commit:`, `commit (initial):`, `commit (amend):`, `commit (merge):`, `commit (cherry-pick):`). Non-commit HEAD moves (`reset:`, `checkout:`, `rebase ...:`, `pull:`, `merge ...:`, etc.) now silently re-anchor the marker to the new HEAD and exit clean — no spurious amend, no SHA-rewrite of already-pushed commits, no force-with-lease recovery needed. Closes the cycle-7 surface scenario at `6e1deb0`. **Note (corrected post-ship):** the commit body's claim "compound `git commit && git push` is safe again" was wrong — see B-003 for the remaining failure mode. | `f19d4d3` |
| B-001 | Added unhappy-path test recipe to `docs/MIGRATION-PATTERN-pydantic-caller.md` §"Unhappy-path test recipe" (one template-level section covers all P1-3 migrations) + 2 example tests in `tests/unit/test_project_models.py::TestMigratedCaller` (`test_project_model_validate_raises_on_missing_id`, `test_project_model_validate_raises_on_malformed_scenes`) pinning the `ValidationError`-at-boundary contract. Closes operator-seat Lane V #3 F2 advisory. | `b1d36d2` |
