# Handoff - director - 2026-06-17 Wave-3 checkpoint route standby

READ FIRST AS `director`. Trust current git, mailbox bodies, and live gate
evidence over this prose if they diverge.

## State At Wrap

Generated: `2026-06-16T16:28:22Z` (`2026-06-17T01:28:22+0900 KST`).
Seat: `director`.
Repo: `/Users/hyungkoookkim/Content`.

Latest live status before this handoff:

```text
HEAD: fbc2455c coord(cursor): director consume wave3 checkpoint route
Branch: main, 6 ahead / 0 behind origin/main
director cursor: 2026-06-16T16:26:42Z
director unread: 0
Wave 2 gate: MET counts={'verified': 30}
selector tail: 71 passed
```

Recent commits at wrap:

```text
fbc2455c coord(cursor): director consume wave3 checkpoint route
2b3f9439 coord(cursor): operator consume wave3 route
c9f6697a coord(route): open checkpoint wave3 implementation
e564fccc operator2(readiness): GO checkpoint stub contract
b76b4c1e coord(cursor): director consume checkpoint status
f33d6b28 coord(cursor): operator consume checkpoint status
```

Smoke evidence from this turn:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

That smoke run happened before the later unrelated checkpoint implementation
WIP appeared in the shared tree. It was not rerun after that WIP appeared.

## Mail Read And Consumed

Consumed for concrete `director`:

- `coordination/mailbox/sent/2026-06-16T16-20-29Z-director2-to-all-status.md`
  via `b76b4c1e coord(cursor): director consume checkpoint status`.
- `coordination/mailbox/sent/2026-06-16T16-26-42Z-coordinator-to-all-coordination.md`
  via `fbc2455c coord(cursor): director consume wave3 checkpoint route`.

Also read for freshness:

- `coordination/mailbox/sent/2026-06-16T16-25-24Z-operator2-to-director2-verify-readiness.md`
  before the first cursor commit. It was Pair-B planning readiness only and
  did not bind `director`.

Current director unread after refresh is `0`.

## Director Routing Decision

No Pair-A implementation, Tier-A co-sign, pod spend, paid API spend, lock
claim/release, push, product-oracle artifact, inventory transition, or
operator Lane V task is opened for `director`.

The binding coordinator route opens the offline Wave-3 checkpoint
implementation mini-batch for `director2`, not for `director`.

Checkpoint route summary:

- `director2` may implement the three Pair-B checkpoint rows:
  `ckpt-nan-json-token`, `ckpt-stage-notrestored`, and
  `ckpt-sceneclips-dead`.
- Expected targets stay in `cinema/checkpoint.py`, `cinema_pipeline.py`, and
  checkpoint/cross-controller tests.
- `operator2` waits for a landed diff plus explicit `director2` verify-request
  before Lane V.
- Push remains user-gated.

## Workspace Caveat

At wrap, the shared worktree has unrelated Pair-B checkpoint implementation WIP:

```text
 M cinema/checkpoint.py
 M cinema_pipeline.py
 M tests/unit/test_discovery_checkpoint_xfail.py
```

This is not director-owned for this handoff. Preserve it unless ownership is
explicitly transferred.

## Exact Next Trigger

For `director`, remain standby for one of:

- a concrete Pair-A route,
- a Tier-A co-sign request,
- an identity/ArcFace/product-oracle design-review request,
- a coordinator route that explicitly opens Pair-A Wave-3 realism or
  dual-character work.

For the active checkpoint mini-batch, the next protocol trigger is
`continue as director2` while implementation is open, then `continue as
operator2` only after `director2` lands a diff and sends a verify-request.
