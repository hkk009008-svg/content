# HANDOFF - Coordinator, 2026-06-15 - Codex idle pass; Wave 2 still unmet

READ FIRST AS COORDINATOR. Trust git and mailbox artifacts over this prose if
they diverge. This handoff was written after the user requested `handoff` and
after the user corrected the coordinator process: always read all mail before
declaring a no-op.

## State At Wrap

- Write timestamp: `2026-06-15T10:35:38Z`.
- HEAD at evidence refresh: `c740f95c coord(cursor): operator2 consume own codex idle status`.
- Branch state from coordinator seat status: `main`, `71 ahead`, `0 behind`.
- Active seat index: `.git/index-codex-coordinator`.
- Coordinator is unpinned: no `seen/coordinator.txt`; no cursor consumed.
- Coordinator/all mailbox count from
  `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2`:
  `UNREAD: 118` all-time `-to-coordinator-` / `-to-all-` events.
- Peer heartbeat snapshot: all four peer seats online; only `operator2` had moved
  to HEAD `c740f95c` during this pass.
- No push performed. Push remains user-gated.

Recent git evidence:

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
c740f95c coord(cursor): operator2 consume own codex idle status
5507582e coord(status): operator2 idle after codex resume
6632746e coord(protocol): default Codex seat subagent cycle
32b3025a verify(pairB): go audioflag inherit
9689e569 coord(verify): request audioflag inherit Lane V
```

## Mailbox Audit

The coordinator/all list was enumerated and the newest event was read:

- `coordination/mailbox/sent/2026-06-15T10-32-13Z-operator2-to-all-status.md`

That event says operator2 consumed the two live Codex-launch unread events:

- `2026-06-15T10-14-54Z-operator2-to-all-verification-report.md`:
  operator2 GO for `audioflag-inherit` on `665427db`.
- `2026-06-15T10-22-41Z-coordinator-to-all-coordination.md`:
  coordinator resume under the Codex subagent-cycle default.

Operator2's phase read: no unread verify request remains for operator2; the
latest visible Pair-B fix already has operator2 GO; no Lane V was invented.

Direct-only tail was also checked. The newest direct route in the current tail is
`coordination/mailbox/sent/2026-06-15T10-10-16Z-director2-to-operator2-verify-request.md`,
which was satisfied by the operator2 GO above. No later direct-only request
changes routing.

## Gate Proof

`scripts/ci_smoke.py` is clean:

```text
$ .venv/bin/python scripts/ci_smoke.py
OK
```

Known advisories remain: `docs/PROGRAM-MANUAL.md` doc-anchor drift, two legacy
mailbox-kind warnings, and two R2 invisible-green warnings.

Wave 2 remains red:

```text
$ .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 16, 'open': 14}
BLOCKER [MAJOR/open] spent-usd-reset-on-resume ... no executable xfail-pin selector
BLOCKER [MAJOR/open] perf-phase-no-gate ... no executable xfail-pin selector
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact ...
17 failed, 44 passed, 1 warning
```

Product-oracle artifact check:

```text
$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
```

No output: the real Wave-2 R-MEASURE product-oracle artifact is still owed.

Active lock check:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep
```

No cross-cutting lock is currently active. If the next selected row needs
`coordination/bin/claim-lock`, remember that lock claiming fetches/pushes, and
push remains user-gated.

## Current Inventory Shape

Current active Wave-2 open rows from `docs/REMEDIATION-INVENTORY.md`:

- `lipsync-veto` - Pair-B, `cinema/auto_approve.py`, cross-cutting lock row.
- `lipsync-postproc-costkey` - Pair-B, postprocess lipsync cost key.
- `lipsync-precheck-cascade-gap` - Pair-B, test-infeasible precheck gap.
- `download-urllib-notimeout` - Pair-B, seven `urlretrieve` sites.
- `http-clearperf-silent200` - Pair-B, `web_server.py`, cross-cutting lock row.
- `http-drivingvid-orphan` - Pair-B, `web_server.py`, cross-cutting lock row.
- `http-addchar-float-unguarded` - Pair-B, `web_server.py`, cross-cutting lock row.
- `http-null-json-body` - Pair-B, `web_server.py`, cross-cutting lock row.
- `http-styleboard-false201` - Pair-B, `web_server.py`, cross-cutting lock row.
- `ckpt-sceneidx-dead` - Pair-B checkpoint row.
- `ckpt-shotaudio-loss` - Pair-B checkpoint row.
- `ckpt-projectid-nocrosscheck` - Pair-B checkpoint row.
- `spent-usd-reset-on-resume` - Pair-B checkpoint/cost design-open row.
- `perf-phase-no-gate` - Pair-B pre-spend gate row.

Deferred open rows are present but not part of the active Wave-2 gate count:
`ckpt-nan-json-token`, `ckpt-sceneclips-dead`, `ckpt-stage-notrestored`, and
`identity-arcface-embselect`.

Verified since the previous coordinator handoff:

- `audioflag-inherit`: verified by operator2 GO
  `coordination/mailbox/sent/2026-06-15T10-14-54Z-operator2-to-all-verification-report.md`
  and recorded in the inventory.

## Current Routing

- Pair-A director/operator are idle unless a new Pair-A row or Tier-A co-sign
  request arrives. The latest Pair-A all-seat state still says no active
  non-deferred Wave-2 Pair-A row remains.
- Pair-B owns the remaining active Wave-2 work visible in the inventory.
- Operator2 currently has no unread verify request after the Codex resume idle
  pass.
- Coordinator should not write another inventory transition until a new operator
  `verification-report` GO/NITS/FAIL or a director gate request lands.
- Do not mark any wave green from inventory status alone. The gate is executable
  and still red.

## Dirty Worktree To Preserve

There is substantial pre-existing dirty state across the shared tree. In the
coordinator index, `git status --short` showed protocol/transplant edits and
several untracked handoffs/mailbox artifacts. In the default index,
`env -u GIT_INDEX_FILE git status --short` also showed staged-delete plus
untracked twin mailbox/brief files and production-file dirt from other seats.

Do not normalize, delete, or broad-stage that state from the coordinator seat.
Use explicit pathspecs. This handoff intentionally adds only:

- `docs/HANDOFF-coordinator-2026-06-15-wave2-codex-idle-unmet.md`
- `coordination/mailbox/sent/2026-06-15T10-35-38Z-coordinator-to-all-coordination.md`

No production code was edited by the coordinator.
