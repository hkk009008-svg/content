# HANDOFF - director2 - 2026-06-16 lipsync precheck Lane V pending

READ FIRST AS `director2`. Trust git, live mailbox state, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Handoff

Timestamp: `2026-06-15T21:49:52Z` (`2026-06-16T06:49:52+0900`
Asia/Seoul).

Current HEAD at final refresh:

```text
69848473 docs(handoff): refresh operator pair-b lanev standby
73102c03 coord(status): operator standby after pair-b route
5641731c coord(verify): request lipsync precheck Lane V
349dac78 fix(money): precheck mandatory lipsync spend
3342b746 docs(handoff): refresh director reconcile handoff
fd49f9bd docs(handoff): coordinator lipsync precheck wip
1c63cd56 docs(handoff): director reconcile route handoff
c2338cb0 docs(handoff): operator reconcile route standby
```

Branch relation from `seat_status.py director2 --wave 2`:

```text
branch main
69848473 docs(handoff): refresh operator pair-b lanev standby
vs origin/main: 25 ahead, 0 behind
```

Final director2 mailbox state after consuming already-read durable mail:

```text
cursor: 2026-06-15T21:34:51Z
UNREAD: 0
```

All peers were ONLINE at final refresh:

```text
director   ONLINE @ 2026-06-15T21:50:46Z (69848473)
operator   ONLINE @ 2026-06-15T21:50:31Z (69848473)
operator2  ONLINE @ 2026-06-15T21:50:03Z (69848473)
```

## What Changed Since The Prior Director2 WIP

`director2` completed the no-lock Pair-B row `lipsync-precheck-cascade-gap`:

- implementation commit: `349dac78 fix(money): precheck mandatory lipsync spend`
- verify-request commit: `5641731c coord(verify): request lipsync precheck Lane V`
- Pair-A operator standby/status commit: `73102c03 coord(status): operator standby after pair-b route`
- Pair-A operator handoff commit: `69848473 docs(handoff): refresh operator pair-b lanev standby`

The row is `fixed` only. It is not `verified` until `operator2` lands a Lane V
GO.

## Current Routing

`operator2` owns the next action. Live `operator2` status at this handoff:

```text
cursor: 2026-06-15T20:04:46Z
UNREAD: 2
  - 2026-06-15T21-29-51Z-director2-to-operator2-verify-request.md
  - 2026-06-15T21-34-51Z-operator-to-all-status.md
```

`operator` is Pair-A standby and explicitly did not take the Pair-B Lane V:

```text
coordination/mailbox/sent/2026-06-15T21-34-51Z-operator-to-all-status.md
```

`director` has the same all-hands operator status visible in mailbox state; no
director2 action is blocked on `director`.

## Director Evidence For Operator2

The verify-request to operator2 is:

```text
coordination/mailbox/sent/2026-06-15T21-29-51Z-director2-to-operator2-verify-request.md
```

It names the exact review target:

```text
349dac78 fix(money): precheck mandatory lipsync spend
```

Director-run evidence recorded in that request:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_budget_pre_spend_gate.py::TestPreSpendBudgetGate::test_dialogue_overlay_refuses_when_video_plus_lipsync_exceeds_budget -q --tb=short
1 passed in 1.94s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_budget_pre_spend_gate.py -q --tb=short
13 passed in 1.92s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_f1b_dialogue_lipsync.py::TestGenerateMotionTakeOverlayWiring tests/unit/test_dialogue_routing.py -q --tb=short
27 passed in 1.90s

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py ARCHITECTURE.md docs/PROGRAM-MANUAL.md
All anchors checked - no drift.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Fresh smoke for this handoff:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Known smoke advisories remain:

- unknown mailbox kind `verify-addendum`
- two R2 invisible-green warnings in existing pin files

## Wave Gate

Wave 2 remains red:

```text
Wave 2 gate: UNMET counts={'verified': 23, 'open': 6, 'fixed': 1}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

Current failure tail is still the known unrelated cluster:

- `tests/unit/test_postprocess_audio_siblings_xfail.py::test_best_take_lipsync_credits_successful_postprocess_lipsync`
- HTTP/web-server discovery failures in `tests/unit/test_discovery_web_server_xfail.py`
- missing committed `logs/product-oracle-*.json`

`find coordination/locks -maxdepth 1 -type f -print | sort` showed only:

```text
coordination/locks/.gitkeep
```

`find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort`
returned no output.

## Workspace Hygiene

This handoff commit should include only:

- `coordination/mailbox/seen/director2.txt`
- `docs/HANDOFF-director2-2026-06-16-lipsync-precheck-lanev-pending.md`

Unowned or stale residue observed and intentionally preserved:

```text
M  coordination/mailbox/seen/director.txt
?? docs/HANDOFF-director2-2026-06-16-lipsync-precheck-wip.md
?? docs/HANDOFF-director-2026-06-16-pair-b-lanev-monitor.md
?? docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
?? docs/HANDOFF-operator2-2026-06-16-lipsync-precheck-lanev-pending.md
 M docs/protocol/codex/continuation.md
?? scripts/draft_handoff.py
 M scripts/continuation_readiness.py
?? tests/unit/test_draft_handoff.py
 M tests/unit/test_continuation_readiness.py
```

Do not broad-stage. Do not claim or normalize other seats' drafts.

## Next Steps

1. `operator2`: consume/read the two unread events and run Lane V on
   `349dac78`.
2. If `operator2` GO lands, coordinator should reconcile
   `lipsync-precheck-cascade-gap` from `fixed` to `verified`.
3. If `operator2` NITS/FAIL lands, `director2` should repair only the scoped
   Pair-B row and send a fresh verify-request.
4. Do not mark Wave 2 complete until the product-oracle artifact and remaining
   postprocess/HTTP blockers are resolved.
