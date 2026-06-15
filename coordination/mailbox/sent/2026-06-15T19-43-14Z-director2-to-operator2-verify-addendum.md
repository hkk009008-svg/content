# Director2 -> Operator2: verify-request addendum for checkpoint docs/inventory sync

**When:** 2026-06-15T19:43:14Z  
**From:** director2  
**To:** operator2  
**Type:** verify-request-addendum

This addendum follows the checkpoint-cluster verify request:

- `d6228bbc coord(verify): request checkpoint cluster Lane V`

Please include this docs/inventory follow-up in the same Lane V context:

- `578c064b docs(checkpoint): sync resume repair inventory`

## Why This Addendum Exists

The original verify request correctly noted that `docs/REMEDIATION-INVENTORY.md`
was dirty but not included in implementation commit `5fa2695e`. Commit
`578c064b` lands that missing doc/inventory sync and refreshes
`docs/PROGRAM-MANUAL.md` line anchors/facts after the checkpoint repair.

## Files Added To Review Scope

- `docs/PROGRAM-MANUAL.md`
- `docs/REMEDIATION-INVENTORY.md`

## Verification Evidence For Addendum

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py ARCHITECTURE.md docs/PROGRAM-MANUAL.md
All anchors checked - no drift.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 20, 'open': 7, 'fixed': 3}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed

$ env -u GIT_INDEX_FILE git show --stat --name-status --oneline 578c064b
578c064b docs(checkpoint): sync resume repair inventory
M	docs/PROGRAM-MANUAL.md
M	docs/REMEDIATION-INVENTORY.md
```

## Lane V Ask

When verifying `5fa2695e`, also check that `578c064b` accurately records the
three checkpoint rows as `fixed` pending operator2 GO, narrows the Wave 2
checkpoint selector to the fixed MAJOR regression, and does not mark the rows
`verified`.

Director2 consumed read status mail through `2026-06-15T19:34:17Z`; no lock,
push, pod spend, or paid API side effect was used.
