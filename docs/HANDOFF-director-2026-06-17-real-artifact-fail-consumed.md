# Handoff - director - 2026-06-17 real artifact FAIL consumed

READ FIRST AS `director`. Current git, mailbox bodies, and live gate evidence
override this prose if they diverge.

## State At Wrap

Seat: `director`.
Repo: `/Users/hyungkoookkim/Content`.

Current HEAD before this handoff commit:

```text
30e5ab83 coord(cursor): operator consume real artifact FAIL
4f3d7147 operator(verify): FAIL real handoff artifact gate
69a54d88 docs(handoff): director real artifact Lane V pending
db2c1657 coord(verify): request real handoff artifact Lane V
6744b018 fix(protocol): require real handoff artifacts
```

Branch state before this handoff commit: `main`, `4 ahead / 0 behind
origin/main`. Push remains user-gated.

## Mail And Gate State

Director live refresh before writing this handoff:

```text
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 3
-> director cursor 2026-06-16T18:41:18Z
-> director unread 1
-> unread event: 2026-06-16T18-59-42Z-operator-to-all-verification-report.md
-> Wave 3 gate: MET counts={'verified': 3}
```

Director consumed that report:

```text
coordination/bin/consume-events director --to 2026-06-16T18:59:42Z
-> cursor director: 2026-06-16T18:41:18Z -> 2026-06-16T18:59:42Z; unread now: 0
```

## What Changed Since Prior Director Handoff

The previous director handoff,
`docs/HANDOFF-director-2026-06-17-real-handoff-artifact-lanev-pending.md`,
is stale. Operator has now answered the Lane V request.

Binding mailbox report:

```text
coordination/mailbox/sent/2026-06-16T18-59-42Z-operator-to-all-verification-report.md
VERDICT: FAIL
```

Operator verified `6744b018 fix(protocol): require real handoff artifacts`.
The ordinary nonexistent-artifact bypass was fixed, but a normalized traversal
path can still satisfy the gate:

```text
docs/HANDOFF-decoy/../PROGRAM-MANUAL.md
```

Operator finding:

```text
scripts/protocol_capacity.py:675-678
```

The current `_has_handoff_artifact()` checks whether `(root / match.group(0))`
is a file. It does not reject traversal or prove that the resolved file is an
actual top-level `docs/HANDOFF-*.md` artifact.

## Deferred Defect Pin

Operator added a strict xfail pin in:

```text
tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_rejects_normalized_non_handoff_file
```

Evidence observed in this handoff pass:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q
-> 22 passed, 1 xfailed in 0.05s

env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; known verify-addendum advisory and R2 invisible-green warnings only

env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
-> valid: true; BLOCKING ISSUES - none
```

## Dirty / Staged Caveat

Before this handoff commit, unrelated shared-tree state existed and was not
owned by this director handoff:

```text
M  coordination/mailbox/seen/director2.txt
D  docs/HANDOFF-coordinator-2026-06-17-real-artifact-fail.md
A  docs/HANDOFF-director2-2026-06-17-real-artifact-fail-standby.md
AM docs/HANDOFF-operator-2026-06-17-real-handoff-artifact-fail-standby.md
?? docs/HANDOFF-coordinator-2026-06-17-real-artifact-fail.md
```

Preserve those unless the owning seat/coordinator routes them. This director
handoff should commit only:

```text
coordination/mailbox/seen/director.txt
docs/HANDOFF-director-2026-06-17-real-artifact-fail-consumed.md
```

## Exact Next Trigger

Next `director` action is to address the operator FAIL in
`coordination/mailbox/sent/2026-06-16T18-59-42Z-operator-to-all-verification-report.md`.

Narrow target:

```text
scripts/protocol_capacity.py
tests/unit/test_protocol_capacity_board.py
```

Expected implementation shape: reject traversal/normalization escapes and
accept only real root-relative top-level `docs/HANDOFF-*.md` artifacts. Then
flip the strict xfail to an ordinary passing test and send a new Lane V
verify-request to `operator`.

No push, lock claim/release, pod/API spend, dependency edit, production
generation, or inventory transition is authorized by this handoff.
