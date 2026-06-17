# Wave 4 Product-Oracle Route Evidence Bundle

Generated from coordinator reconciliation on `2026-06-17T07:54:34Z`.

This folder preserves the packet snapshots and evidence used to close the first
Wave 4 bug/error cleanup cycle and open the narrower Wave 4 product-oracle
route.

Future packet/evidence snapshots for this route should stay in this bundle.
For new coordinator cycles, use the parent convention in
`docs/archive/coordination-evidence/README.md`.

## Contents

- `packets/` - copied capacity packet JSON files for the closed
  `2026-06-17-wave4-bug-error-cleanup-a` cycle and the active
  `2026-06-17-wave4-product-oracle-a` cycle.
- `mailbox/` - copied coordinator route plus operator/operator2 GO reports.
- `handoffs/` - copied handoff snapshots that pointed back to coordinator
  reconciliation.
- `evidence/REMEDIATION-INVENTORY.snapshot.md` - inventory snapshot after the
  `identity-arcface-embselect` row was reconciled to verified.
- `evidence/command-evidence.md` - command outputs used by coordinator before
  committing the route.

## Decision Captured

- Operator GO closed `identity-arcface-embselect`.
- Operator2 GO closed the mailbox-kind cleanup.
- Wave 4 did not close because `logs/product-oracle-wave4.json` is still
  missing.
- Coordinator opened one consolidated route for the Wave 4 product-oracle
  artifact and verification path.

## Exact Next Trigger

`continue as director`
