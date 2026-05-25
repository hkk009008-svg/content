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
| B-001 | operator-seat (Lane V #3 on `e1b72ca`, F2 advisory) | 2026-05-25 | **Add unhappy-path test recipe to `docs/MIGRATION-PATTERN-pydantic-caller.md`** covering `Project.model_validate()` raising `ValidationError` on a malformed project dict. The recipe-level gap is inherited by ALL P1-3 part-N migrations (currently S10 + parts 3 + 4 lack the regression test). Closing this at the template level — rather than per-migration — fixes the gap for all current AND future migrations in one stroke. Estimate: ~30-45 min Lane A in main context (template edit + one example test that future parts copy). | director-seat (template authorship) OR operator-seat (Lane D-style docs work) | medium — addresses a real coverage gap but template-derived (not a per-migration omission), so no urgency |

---

## Recently graduated to POST-ROADMAP

| ID | Description | Promoted at SHA |
|---|---|---|

_(None yet.)_

---

## Recently completed

| ID | Description | Completion SHA |
|---|---|---|

_(None yet.)_
