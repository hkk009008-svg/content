# Director Handoff - protocol notices consumed, active monitor

READ FIRST AS `director`. Trust current git/filesystem, live mailbox state, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Handoff

Timestamp: `2026-06-15T23:06:11Z` (`2026-06-16T08:06:11+0900 KST`).

Seat: `director`

Current HEAD at evidence refresh:

```text
148a81df coord(cursor): director consume protocol notice
ef1c56b8 coord(status): operator fold self-broadcast cursor
d029a00a coord(cursor): operator2 consume standby notices
bb53e0d5 coord(cursor): director2 consume protocol notice
b20bc811 coord(status): operator standby after protocol notice
28cb3a38 coord(notify): protocol effectiveness report awareness
508d3710 docs(spec): protocol effectiveness loop design
9d7589e4 docs(handoff): coordinator lipsync precheck reconciled
```

Branch relation from live status:

```text
main vs origin/main: 19 ahead, 8 behind
```

## Director Mail

Fresh director status before writing this handoff:

```text
cursor: 2026-06-15T22:59:40Z
UNREAD: 0
```

The current director cursor was committed in:

```text
148a81df coord(cursor): director consume protocol notice
```

Mail read/absorbed before that cursor:

- `2026-06-15T22-10-55Z-operator2-to-all-verification-report.md`:
  operator2 GO for Pair-B row `lipsync-precheck-cascade-gap`.
- `2026-06-15T22-14-55Z-coordinator-to-all-coordination.md`:
  coordinator reconciled that Pair-B row to `verified`; Wave 2 remains UNMET.
- `2026-06-15T22-54-10Z-coordinator-to-all-coordination.md`:
  protocol-effectiveness report awareness. Treat the helper as planning input
  only, not a gate, GO, inventory authority, or routing automation.
- `2026-06-15T22-59-40Z-operator-to-all-status.md`:
  operator resumed, consumed the same protocol notices, and reported no Pair-A
  Lane V pending.

No mailbox event was sent by this director handoff.

## Seat Board

Fresh live seat snapshots before writing this handoff:

```text
director:  cursor 2026-06-15T22:59:40Z, unread 0, online
operator:  cursor 2026-06-15T22:59:40Z, unread 0, online
director2: cursor 2026-06-15T22:59:40Z, unread 0, online
operator2: cursor 2026-06-15T22:59:40Z, unread 0, online
```

Interpretation:

- `director`: no active Pair-A implementation, verify request, Tier-A co-sign,
  or product-oracle review request. Active monitor only.
- `operator`: Pair-A Lane V standby; no fresh verify request.
- `director2`: Pair-B lipsync-precheck row is reconciled/verified; no unread
  route remains.
- `operator2`: Pair-B Lane V standby; no unread route remains.

All seats are caught up on the latest coordinator/operator protocol notices as
of this handoff evidence.

## Gate / Smoke / Locks

Smoke:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Known smoke advisories:

- `verify-addendum` mailbox kind is not in `KNOWN_KINDS`;
- `tests/unit/test_discovery_identity_xfail.py:193` has a `skip()` in a pin
  file;
- `tests/unit/test_lane_silent_gate_siblings_xfail.py:64` uses
  `importorskip('cv2')`, and the dependency is present.

Wave 2 gate:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 24, 'open': 6}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

Remaining Wave 2 open rows from `docs/REMEDIATION-INVENTORY.md`:

- `lipsync-veto` in `cinema/auto_approve.py` - Pair-B, cross-cutting,
  requires `W2-auto_approve.py.lock`.
- Five HTTP rows in `web_server.py` - Pair-B, cross-cutting, require
  `W2-web_server.py.lock`:
  `http-clearperf-silent200`, `http-drivingvid-orphan`,
  `http-addchar-float-unguarded`, `http-null-json-body`,
  `http-styleboard-false201`.
- Deferred/test-infeasible rows remain open and are not director-active Wave 2
  implementation targets: `ckpt-nan-json-token`, `ckpt-sceneclips-dead`,
  `ckpt-stage-notrestored`, `identity-arcface-embselect`.

Locks and product-oracle artifact:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

Push, lock-claim/push side effects, pod spend, and paid API spend remain
unauthorized. Do not claim `W2-auto_approve.py.lock` or
`W2-web_server.py.lock` from this director seat without explicit user/coordinator
authorization because the lock helper performs fetch/push side effects.

## Workspace Hygiene

Status before writing this handoff:

```text
## main...origin/main [ahead 19, behind 8]
 M .agents/skills/four-seat-protocol/SKILL.md
 M docs/protocol/codex/continuation.md
 M scripts/continuation_readiness.py
 M tests/unit/test_codex_protocol_artifacts.py
 M tests/unit/test_continuation_readiness.py
?? docs/HANDOFF-coordinator-2026-06-16-automated-handoff-tool-transplant.md
?? docs/HANDOFF-director-2026-06-16-lipsync-reconciled-product-oracle-open.md
?? docs/HANDOFF-director2-2026-06-16-lipsync-precheck-wip.md
?? docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
?? docs/HANDOFF-operator-2026-06-16-lipsync-precheck-reconciled.md
?? scripts/draft_handoff.py
?? scripts/protocol_effectiveness_report.py
?? tests/unit/test_draft_handoff.py
?? tests/unit/test_protocol_effectiveness_report.py
```

There was no staged shared-index scope before writing:

```text
$ env -u GIT_INDEX_FILE git diff --cached --name-status
# no output
```

Do not stage, delete, revert, or "clean up" the listed WIP from a future
director pickup unless ownership is explicitly transferred. Those paths appear
to be Codex-protocol transplant, coordinator, director2, and operator artifacts.

## Next Director

1. Start with:
   `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2`
   and `env -u GIT_INDEX_FILE git log --oneline -5`.
2. Read any new director/all mail before making a routing, handoff, inventory,
   gate, or status claim. Consume only if intentionally advancing live director
   state.
3. Remain active monitor for product-oracle identity/ArcFace review, Tier-A
   co-signs, explicit Pair-A work, or coordinator-directed support.
4. Do not duplicate operator2's Pair-B lipsync-precheck GO and do not verify
   director-authored work; impl != verifier.
5. Do not claim locks, push, use pods, or trigger paid APIs without explicit
   user-principal authorization.
