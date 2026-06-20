# Slice 2.5 — Legacy `coordination/` Mailbox Migration (TRACKING STUB)

> **Status: SUPERSEDED.** The full design + TDD plan now live in
> `docs/superpowers/specs/2026-06-20-threeway-slice2.5-legacy-bus-migration-design.md` and
> `docs/superpowers/plans/2026-06-20-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md`
> (this stub's edit-site inventory was ~3× undercounted; see the design spec §4). Retained for history.
> This was the separately-tracked deferral artifact for spec
> §8.7/§8.8 (audit Issue 8 / Decision D-B). It is a *tracking stub*, not an implementation plan —
> the full TDD plan is authored only after the **Slice 2 gate is green** (spec §11 boundary rule).
> Identifier: **`threeway-slice2.5-legacy-bus-migration`**.

**Owner:** unassigned (assign a Pair-B director when Slice 2's gate passes).
**Relationship:** sequenced **after** Slice 2 (needs the `refs/threeway/events` substrate + cursor refs)
and **before/with** Slice 3. Does not block Slice 2. Companion: the Slice 2 plan
`2026-06-19-cross-provider-seat-topology-slice2.md` (its D-B section holds the exact edit-site inventory).

## Why deferred (not dropped)

The §11 Slice 2 gate tests only the new ref-bus's race-safety; the legacy-mailbox migration is **not
gated** and touches the **live 4-seat campaign bus** (`coordination/`) with seat-list state in **six
independent copies**. Migrating it mid-Slice-2 is risk with no gate payoff. It is tracked here so it is
never silently lost.

## Scope

1. **Make `coordinator`/`coordinator2` first-class *receiving* seats** (today `coordinator` is send-only,
   `coordinator2` does not exist). Edit sites (all verified in the Slice-1 understand pass):
   - `scripts/protocol_mailbox.py:11` `SEATS` — the canonical root (propagates to `RECIPIENTS`,
     `check_coordination.py ROLES`); **§8.7's "four files" omits this — treat it as the 5th sync target.**
   - `coordination/bin/send-event:29-30` (FROM/TO whitelists); `coordination/bin/consume-events:27`
     (ROLE whitelist + usage strings); `scripts/check_coordination.py:58-59,:85` (hardcoded seat regexes)
     + the `:51-55` comment; `scripts/status.py:126` `_MAILBOX_SEATS` (an independent copy) + argparse help.
2. **Cursor backfill** ISO-timestamp → scalar `seq` for the 4 (→6) `seen/<seat>.txt` files + per-seat
   `refs/threeway/cursors/<seat>` refs; update `check_coordination.py:63 _CURSOR_RE` (ISO-only today,
   fatal on a scalar).
3. **Shadow → single-writer cutover** (the broader migration guidance favors staged shadow + canary,
   NOT a big-bang): `events/`+`index/` runs as a **read-only projection** alongside `mailbox/sent/`
   first; the legacy mailbox becomes a derived view; then a single-writer authority cutover. **No
   dual-write authority at any point.**

## Non-goals

- No change to the *event vocabulary* (`kinds.txt`) beyond what receiving seats require.
- No change to Slice 2's `threeway/` package internals (this slice consumes them).
- Not Slice 3 (strategic loop / tiered co-sign).

## Prerequisites

- Slice 2 gate green (ref bus + race + serial re-stage + the 3 findings).
- `preflight_bus_init` (Slice 2 Task 3c) available, so the migration's init is fail-closed.

## Migration & rollback policy

- **Fail-closed init:** reuse `preflight_bus_init` — abort if any prior `refs/threeway/*` state exists
  without an explicit migration acknowledgement; never delete events/cursors.
- **Reversible cursor backfill:** keep the original `seen/<seat>.txt` ISO values (archived) so a backfill
  can be undone; the scalar cursors are additive until cutover.
- **Rollback:** while shadowing, the legacy `mailbox/sent/` remains authoritative and untouched, so
  rollback = stop reading the projection. Post-cutover rollback requires a documented reverse-projection
  (define before cutover).

## Shadow / canary requirements

- Run `events/`+`index/` as a read-only projection for ≥1 full campaign cycle with zero divergence from
  `mailbox/sent/` (a divergence check script) before any authority cutover.
- Canary one seat pair on the new cursors before all four.

## Acceptance gate (to be expanded into the real plan)

- The legacy-bus checkers (`scripts/check_coordination.py`, `scripts/status.py`) stay green across the
  seat additions; `coordinator`/`coordinator2` send AND receive.
- Cursor backfill is byte-reversible; the ISO→seq map is reproducible from `sent/`.
- No event lost or duplicated across the shadow→authority cutover (a reconciliation count).
- No dual-write-authority window exists at any point (audited).

---
*Created 2026-06-19 as the Slice 2.5 deferral tracker (audit Issue 8). Not an implementation plan;
authored into one after Slice 2's gate is green.*
