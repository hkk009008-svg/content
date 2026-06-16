# Handoff - director - 2026-06-17 Wave-3 product-oracle Lane V pending

READ FIRST AS `director`. Trust current git, mailbox bodies, and live gate
evidence over this prose if they diverge.

## State At Wrap

Generated: `2026-06-16T17:08:20Z` (`2026-06-17T02:08:20+0900 KST`).
Seat: `director`.
Repo: `/Users/hyungkoookkim/Content`.

Latest live status before this handoff:

```text
HEAD: bed49c5e coord(verify): request operator wave3 product oracle
Branch: main, 17 ahead / 0 behind origin/main
director cursor: 2026-06-16T17:01:05Z
director unread: 0
Wave 3 gate: MET counts={'verified': 3}
PRODUCT ORACLE: logs/product-oracle-wave3.json
```

Recent commits:

```text
bed49c5e coord(verify): request operator wave3 product oracle
012d28d0 fix(product-oracle): add wave3 artifact
b7a3e8c1 docs(handoff): director2 checkpoint wave3 standby
b226d470 docs(handoff): coordinator wave3 product oracle route
f7564d77 coord(route): reconcile wave3 checkpoint GO
```

## Mail Read And Consumed

Director read and consumed the binding route:

- `coordination/mailbox/sent/2026-06-16T17-01-05Z-coordinator-to-all-coordination.md`

Cursor commit:

- `012d28d0 fix(product-oracle): add wave3 artifact`
- `coordination/mailbox/seen/director.txt`: `2026-06-16T16:26:42Z` ->
  `2026-06-16T17:01:05Z`

No newer director mail was unread at wrap.

## Product-Oracle Artifact

Implementation commit:

- `012d28d0 fix(product-oracle): add wave3 artifact`

Changed files:

- `logs/product-oracle-wave3.json`
- `scripts/measure_product_oracle.py`
- `tests/unit/test_measure_product_oracle.py`
- `coordination/mailbox/seen/director.txt`

Why the script changed:

- The recorded script-path command failed before the artifact could be
  reproduced because `python scripts/measure_product_oracle.py` put
  `scripts/` on `sys.path` without the repo root.
- The fix bootstraps `_REPO_ROOT` into `sys.path`.
- The regression test proved RED first with `ModuleNotFoundError: No module
  named 'identity'`, then GREEN after the bootstrap.

Measurement command:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/measure_product_oracle.py --wave 3 --video logs/lipsync_gen_v2studio.mp4 --reference-image logs/ref_lighting.jpg --output logs/product-oracle-wave3.json
```

Measurement output:

```text
wrote logs/product-oracle-wave3.json
arcface.arc_score=0.606526 lipsync.offset_frames=-1.000 lipsync.correlation=0.370732
```

No pod/API spend, dependency edit, production generation, lock claim/release,
or push happened.

## Verification Already Run

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_measure_product_oracle.py -q
-> 4 passed
```

```text
.venv/bin/python scripts/wave_gate_check.py 3
-> Wave 3 gate: MET counts={'verified': 3}
-> PRODUCT ORACLE: logs/product-oracle-wave3.json
```

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> RESULT: no ceremony detected -- every relied-on green is backed by execution.
-> OK
```

Known smoke advisories only: historical `verify-addendum` mailbox kind plus R2
invisible-green warnings.

## Operator Lane V Pending

Verify-request commit:

- `bed49c5e coord(verify): request operator wave3 product oracle`

Verify-request body:

- `coordination/mailbox/sent/2026-06-16T17-07-44Z-director-to-operator-verify-request.md`

Operator status at wrap:

```text
operator unread: 2
  - 2026-06-16T17-01-05Z-coordinator-to-all-coordination.md
  - 2026-06-16T17-07-44Z-director-to-operator-verify-request.md
Wave 3 gate: MET counts={'verified': 3}
```

Do not call Wave 3 protocol-closed from the director side alone; operator must
issue GO/NITS/FAIL on the product-oracle artifact.

## Exact Next Trigger

For `director`, remain standby unless operator returns NITS or coordinator/user
routes new Pair-A/product-oracle work.

The next protocol trigger is:

```text
continue as operator
```

Operator should consume/read the two unread events above, verify `012d28d0`
against the request, and send GO/NITS/FAIL. Push remains user-gated.
