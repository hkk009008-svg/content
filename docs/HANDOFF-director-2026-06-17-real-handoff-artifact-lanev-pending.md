# Handoff - director - 2026-06-17 real handoff artifact Lane V pending

READ FIRST AS `director`. This is a snapshot; current git, mailbox bodies, and
live gate evidence override this prose if they diverge.

## State At Wrap

Seat: `director`.
Repo: `/Users/hyungkoookkim/Content`.

Current HEAD before this handoff commit:

```text
db2c1657 coord(verify): request real handoff artifact Lane V
6744b018 fix(protocol): require real handoff artifacts
bb58b2f4 coord(cursor): consume handoff artifact FAIL
316673fa operator(verify): FAIL handoff artifact gate
10c703ab docs(protocol): prepare harness hardening handoff
```

Branch state before this handoff commit: `main`, `1 ahead / 0 behind
origin/main`. Push remains user-gated.

## Mail And Gate State

Director live refresh after the verify-request:

```text
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 3
-> director cursor 2026-06-16T18:41:18Z
-> director unread 0
-> Wave 3 gate: MET counts={'verified': 3}
-> PRODUCT ORACLE: logs/product-oracle-wave3.json
```

Operator live refresh after the verify-request:

```text
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 3
-> operator cursor 2026-06-16T18:41:18Z
-> operator unread 1
-> unread event: 2026-06-16T18-51-26Z-director-to-operator-verify-request.md
```

## Action Taken

Director consumed the operator FAIL on the prior handoff-artifact gate:

```text
coordination/mailbox/sent/2026-06-16T18-41-18Z-operator-to-all-verification-report.md
```

The FAIL was correct: `scripts/protocol_capacity.py` accepted a
`docs/HANDOFF-*.md` citation string without checking that the artifact existed
under the capacity report root.

Director-side fix landed:

```text
6744b018 fix(protocol): require real handoff artifacts
```

Scope:

```text
scripts/protocol_capacity.py
tests/unit/test_protocol_capacity_board.py
```

The fix threads the capacity report root into the join gate and accepts a
closed-cycle standby/idle/closeout handoff citation only when the cited
`docs/HANDOFF-*.md` exists under that root. The test suite now has both missing
and existing artifact cases.

Director then sent a new Lane V request:

```text
coordination/mailbox/sent/2026-06-16T18-51-26Z-director-to-operator-verify-request.md
db2c1657 coord(verify): request real handoff artifact Lane V
```

## Director-Side Verification Already Run

RED before the fix:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_rejects_missing_handoff_artifact -q
-> failed with AssertionError: assert 'handoff artifact' in ''
```

GREEN and regression:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q
-> 22 passed in 0.04s

env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py tests/unit/test_check_coordination.py -q
-> 64 passed in 0.40s

env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; only the existing verify-addendum advisory and R2 invisible-green warnings

env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 2
-> valid: true; BLOCKING ISSUES - none

env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
-> valid: true; BLOCKING ISSUES - none
```

Director preflight is not an operator GO.

## Exact Next Trigger

`operator` should consume and run Lane V on `6744b018` using:

```text
coordination/mailbox/sent/2026-06-16T18-51-26Z-director-to-operator-verify-request.md
```

Director is waiting for the operator GO/NITS/FAIL. No push, lock claim/release,
pod/API spend, dependency edit, production generation, or inventory transition
is authorized by this handoff.
