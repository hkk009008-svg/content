# Director Handoff - authorized route pending, product-oracle next

READ FIRST AS `director`. Trust current git/filesystem, live mailbox state, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Handoff

Timestamp: `2026-06-15T23:08:10Z` (`2026-06-16T08:08:10+0900 KST`).

Seat: `director`

Current HEAD at evidence refresh:

```text
d7e98a46 docs(handoff): director protocol notices consumed
875c1ab2 coord(route): authorized wave2 product oracle and locks
148a81df coord(cursor): director consume protocol notice
ef1c56b8 coord(status): operator fold self-broadcast cursor
d029a00a coord(cursor): operator2 consume standby notices
bb53e0d5 coord(cursor): director2 consume protocol notice
b20bc811 coord(status): operator standby after protocol notice
28cb3a38 coord(notify): protocol effectiveness report awareness
```

Branch relation from live status:

```text
main vs origin/main: 21 ahead, 8 behind
```

## Director Mail

Fresh director status before this handoff update:

```text
cursor: 2026-06-15T22:59:40Z
UNREAD: 1
- 2026-06-15T23-07-16Z-coordinator-to-all-coordination.md
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

New unread route read for this handoff but intentionally not consumed:

- `2026-06-15T23-07-16Z-coordinator-to-all-coordination.md`:
  coordinator records user-principal authorization (`authorized.`) for the side
  effects named in the route: product-oracle artifact write/pod/paid-API spend
  as needed, plus Pair-B lock-claim/push side effects for `lipsync-veto` and
  the HTTP rows. This route assigns `director` to product-oracle artifact work.

No mailbox event was sent by this director handoff.

## Seat Board

Fresh live seat snapshots before writing this handoff:

```text
director:  cursor 2026-06-15T22:59:40Z, unread 1, online
operator:  cursor 2026-06-15T22:59:40Z, unread 1, online
director2: cursor 2026-06-15T22:59:40Z, unread 1, online
operator2: cursor 2026-06-15T22:59:40Z, unread 1, online
```

Interpretation:

- `director`: actionable route now pending. Advance the Wave 2 product-oracle
  blocker with committed/reproducible R-MEASURE instrumentation and
  `logs/product-oracle-*.json`, or report the exact missing input/service.
- `operator`: product-oracle checker after director lands the artifact; no
  Pair-B Lane V duplication.
- `director2`: Pair-B implementation owner for the lock-authorized
  `lipsync-veto` and HTTP rows. Must protect dirty WIP before using lock
  helpers.
- `operator2`: Pair-B Lane V verifier for director2 verify-request(s).

All seats still need to consume/read the `2026-06-15T23-07-16Z` coordinator
route on pickup. Receipt evidence here means only that the route exists and was
seen by this handoff writer, not that the seats have acted on it.

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

The `2026-06-15T23-07-16Z` coordinator route records user authorization for
product-oracle write/pod/paid-API spend as needed and Pair-B lock-claim/push
side effects. This director route allows `logs/product-oracle-*.json`,
measurement helper/script/test/docs if needed, and mailbox status/route
artifacts; it does not authorize production-code edits from the director seat.

The Pair-B lock helpers are still dangerous in the current dirty shared tree:
the route explicitly warns that `coordination/bin/claim-lock` can
`git reset --hard @{u}` on push rejection. Protect dirty WIP before any seat
runs lock helpers.

## Workspace Hygiene

Status before writing this handoff:

```text
## main...origin/main [ahead 21, behind 8]
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

A transient stale shared-index `D/??` pair appeared for
`coordination/mailbox/sent/2026-06-15T23-07-16Z-coordinator-to-all-coordination.md`
after the coordinator route landed during the first handoff commit window. It
was refreshed with:

```text
$ env -u GIT_INDEX_FILE git reset -q -- coordination/mailbox/sent/2026-06-15T23-07-16Z-coordinator-to-all-coordination.md
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
3. Read `2026-06-15T23-07-16Z-coordinator-to-all-coordination.md` first. It is
   the binding route for this handoff.
4. For director work, advance the product-oracle blocker only: create/commit a
   valid `logs/product-oracle-*.json` with `artifact_kind="product-oracle"`,
   `wave=2`, finite `arcface.arc_score`, and finite `lipsync.offset_frames`,
   produced by committed/reproducible R-MEASURE instrumentation. If baseline
   media or services are missing, report the exact blocker and do not fabricate
   values.
5. Route the completed artifact to `operator` for independent check.
6. Do not duplicate operator2's Pair-B lipsync-precheck GO and do not verify
   director-authored work; impl != verifier.
7. Do not edit production code from this director route. Pair-B lock/code work
   belongs to `director2`/`operator2`.
