# HANDOFF - operator2 - 2026-06-16 Wave 2 route standby

READ FIRST AS `operator2`. Trust git, live mailbox state, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Handoff

Timestamp: `2026-06-15T23:10:48Z` (`2026-06-16T08:10:48+0900`
Asia/Seoul).

User requested a bare `handoff`; this file is a narrow state-transfer artifact,
not a Lane V pass, cursor consume, route, inventory edit, or verification
verdict.

Current HEAD at evidence refresh:

```text
f68a0d7b docs(handoff): refresh director authorized route
d7e98a46 docs(handoff): director protocol notices consumed
875c1ab2 coord(route): authorized wave2 product oracle and locks
148a81df coord(cursor): director consume protocol notice
ef1c56b8 coord(status): operator fold self-broadcast cursor
d029a00a coord(cursor): operator2 consume standby notices
bb53e0d5 coord(cursor): director2 consume protocol notice
b20bc811 coord(status): operator standby after protocol notice
28cb3a38 coord(notify): protocol effectiveness report awareness
508d3710 docs(spec): protocol effectiveness loop design
9d7589e4 docs(handoff): coordinator lipsync precheck reconciled
2b55d7ca docs(handoff): operator2 lipsync reconciled standby
```

Branch relation from live `operator2` status:

```text
branch main
f68a0d7b docs(handoff): refresh director authorized route
vs origin/main: 22 ahead, 8 behind
```

Operator2 live mailbox before this handoff:

```text
cursor: 2026-06-15T22:59:40Z
UNREAD: 1
- 2026-06-15T23-07-16Z-coordinator-to-all-coordination.md
```

The unread coordinator route was read for this handoff. I did **not** consume
the `operator2` cursor, because the user asked for handoff only. The next
`operator2` should still surface this unread count first, re-read the route,
and consume intentionally only if continuing live-seat work.

## Binding Route To Preserve

Unread route:

```text
coordination/mailbox/sent/2026-06-15T23-07-16Z-coordinator-to-all-coordination.md
```

The coordinator recorded user authorization for:

- lock-claim/push side effects for Wave 2 Pair-B locks;
- product-oracle artifact write / pod / paid API spend as needed;
- `director2` as Pair-B implementation owner;
- `operator2` as Pair-B Lane V verifier.

This route is **not** an operator GO and does **not** itself create a Lane V
target. Operator2 should verify only real landed `director2` implementation
commits and direct verify-request(s).

## Operator2 Decision

Operator2 is routed to standby for future Pair-B verify-request(s).

Current expected `operator2` action after resume:

1. Refresh live state with `seat_status.py operator2 --wave 2`.
2. Surface `operator2` unread count before processing mail.
3. Re-read the coordinator route and then decide whether to consume
   `operator2` mail.
4. Stand by for `director2` verify-request(s) for `lipsync-veto` and/or the
   HTTP cluster.
5. Run Lane V only after a real landed implementation commit and verify-request
   exist.

Pair-B routes named by coordinator:

- `lipsync-veto`: `cinema/auto_approve.py`,
  `tests/unit/test_postprocess_audio_siblings_xfail.py`, brief/docs/inventory
  as needed, and a verify-request to `operator2`.
- HTTP cluster: `web_server.py`,
  `tests/unit/test_discovery_web_server_xfail.py`, brief/docs/inventory as
  needed, and a verify-request to `operator2`.

Expected `operator2` write set on GO/NITS/FAIL:

- verification-report mailbox event;
- `operator2` cursor if intentionally consumed;
- same-commit lock deletion on GO only.

Important lock rule: on GO, manually stage the relevant lock deletion in the
same commit as the verification-report. Do **not** use
`coordination/bin/release-lock` for the GO path, because it creates a separate
unlock commit. On FAIL, retain the lock.

## Live Seat Board

- `director`: online at `f68a0d7b`, unread `1`
  (`2026-06-15T23-07-16Z-coordinator-to-all-coordination.md`). Product-oracle
  route owner per coordinator event.
- `operator`: online at `f68a0d7b`, unread `1`
  (`2026-06-15T23-07-16Z-coordinator-to-all-coordination.md`). Product-oracle
  checker / Pair-A standby after artifact lands.
- `director2`: online at `f68a0d7b`, unread `1`
  (`2026-06-15T23-07-16Z-coordinator-to-all-coordination.md`). Pair-B
  implementation owner once it safely handles dirty-tree and lock-claim
  hazards.
- `operator2`: online at `f68a0d7b`, unread `1`
  (`2026-06-15T23-07-16Z-coordinator-to-all-coordination.md`). Pair-B Lane V
  standby; no current implementation commit or verify-request is pending.

All four seat statuses showed Wave 2 still UNMET with
`counts={'verified': 24, 'open': 6}`.

## Gate / Smoke / Locks

Smoke:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
WARNING: coordination ADVISORY [unknown_kind] mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md - kind 'verify-addendum' not in KNOWN_KINDS
R1 xfail-strictness ....... PASS  12 xfail markers; all strict=True+reason
R2 invisible-green ........ WARN
R3 gate-executes-pins ..... PASS  wave_gate_check.py executes the pins
R4 ci-runs-runxfail ....... PASS  a CI workflow runs --runxfail
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Wave 2 gate:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 24, 'open': 6}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

Locks and product-oracle artifact:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

No push, lock claim, pod spend, paid API spend, production code edit, inventory
edit, mailbox cursor consume, lock release, or verification verdict was
performed by operator2 during this handoff.

## Workspace Hygiene

The handoff intentionally preserves unrelated shared-tree residue already
present in the worktree:

```text
 M .agents/skills/four-seat-protocol/SKILL.md
 M docs/HANDOFF-director-2026-06-16-protocol-notices-consumed-active-monitor.md
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

Do not revert or claim those paths from `operator2` unless the user explicitly
changes ownership.

## Resume Checklist

1. Run
   `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator2 --wave 2`
   and `env -u GIT_INDEX_FILE git log --oneline -8`.
2. Surface the live unread count before reading/consuming mail.
3. Re-read
   `coordination/mailbox/sent/2026-06-15T23-07-16Z-coordinator-to-all-coordination.md`.
4. If continuing, consume `operator2` intentionally and inspect staged scope.
5. Stand by until `director2` lands implementation commit(s) plus
   verify-request(s).
6. For GO/NITS/FAIL, read the actual diff, run focused tests, send one
   `verification-report`, and release locks only with same-commit GO handling.
