# Director2 Handoff - Real Artifact FAIL Standby

Generated: `2026-06-16T19:02:10Z` (`2026-06-17T04:02:40+0900` KST)
Repo: `/Users/hyungkoookkim/Content`
Seat: `director2`

Trust live git, mailbox, gate, and filesystem state over this snapshot if they
diverge.

## Refresh First

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 3
env -u GIT_INDEX_FILE git log --oneline -5
env -u GIT_INDEX_FILE git status --short --branch
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

## Current State

HEAD while drafting this handoff:

```text
30e5ab83 coord(cursor): operator consume real artifact FAIL
```

Recent live history:

```text
30e5ab83 coord(cursor): operator consume real artifact FAIL
4f3d7147 operator(verify): FAIL real handoff artifact gate
69a54d88 docs(handoff): director real artifact Lane V pending
db2c1657 coord(verify): request real handoff artifact Lane V
6744b018 fix(protocol): require real handoff artifacts
```

`env -u GIT_INDEX_FILE git status --short --branch` before this handoff file was
added reported:

```text
## main...origin/main [ahead 4]
M  coordination/mailbox/seen/director.txt
M  coordination/mailbox/seen/director2.txt
?? docs/HANDOFF-coordinator-2026-06-17-real-artifact-fail.md
```

The `director.txt` cursor and coordinator handoff are not director2-owned scope
for this handoff and were left untouched.

Live `seat_status.py` after the director2 cursor receipt:

```text
branch main
30e5ab83 coord(cursor): operator consume real artifact FAIL
vs origin/main: 4 ahead, 0 behind
director2 cursor: 2026-06-16T18:59:42Z
director2 unread: 0
Wave 3 gate: MET counts={'verified': 3}
PRODUCT ORACLE: logs/product-oracle-wave3.json
```

Peer heartbeats were online for `director`, `operator`, and `operator2`.

## Gate And Smoke

`env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 3`:

```text
Wave 3 gate: MET  counts={'verified': 3}
  gate rows: 0; executable selectors: 0
  PRODUCT ORACLE: logs/product-oracle-wave3.json
```

`env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3`:

```text
# Protocol Capacity Board
wave: 3
valid: true

ACTORS
coordinator packets=- status=-
director    packets=- status=-
director2   packets=- status=-
operator    packets=- status=-
operator2   packets=- status=-

BLOCKING ISSUES
- none
```

`env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` reported `OK`.
It also reported the known `verify-addendum` mailbox-kind advisory and R2
invisible-green warnings.

## Mail Consumed

Read and consumed for director2:

```text
coordination/mailbox/sent/2026-06-16T18-59-42Z-operator-to-all-verification-report.md
```

The event is an operator-to-all Lane V `FAIL` for:

```text
6744b018 fix(protocol): require real handoff artifacts
```

Key finding: `_has_handoff_artifact()` rejects missing handoff files but still
accepts a normalized traversal path such as
`docs/HANDOFF-decoy/../PROGRAM-MANUAL.md` when it resolves to an existing
non-handoff file. Operator pinned the deferred bypass with strict xfail
`test_closed_standby_cycle_rejects_normalized_non_handoff_file`.

The report explicitly covers no lock release, push, lock claim, pod/API spend,
dependency edit, production generation, or inventory transition.

## Director2 Disposition

Director2 has no active Pair-B implementation, lock, co-sign, or verification
target.

The current protocol FAIL is awareness for director2, not a director2-owned
assignment. Do not self-fix it as director2 unless the coordinator/user routes
that work to this seat or requests a specific co-sign/support action.

Do not self-verify Wave 3 product-oracle as director2.

## Exact Next Trigger

- `push` if the user-principal wants the local protocol/cursor commits
  published. Push remains user-gated.
- `continue as director2` only if the coordinator/user routes a new Pair-B row,
  asks for Pair-B support/co-sign on the protocol gate, or requests another
  director2 handoff refresh.
- A new coordinator/user route is required before opening Pair-B capability/pod
  work, Wave 4 planning, or unrelated product-oracle/identity rows.
