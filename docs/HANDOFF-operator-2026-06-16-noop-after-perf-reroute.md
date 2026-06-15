# HANDOFF - Operator-1, 2026-06-16 - no-op after perf reroute

READ FIRST AS operator-1. Trust git and mailbox artifacts over this prose if
they diverge.

## State At Wrap

- Seat: `operator` / Pair-A verification.
- Final observed HEAD before this handoff commit:
  `ccb344b5 docs(handoff): director perf reroute standby`.
- Branch relation from live seat status: `main` is `16 ahead / 0 behind` origin.
- Operator cursor after final self-consume: `2026-06-15T18:08:22Z`.
- Operator unread after final self-consume: `0`.
- Wave 2 remains `UNMET`: `verified=19`, `open=11`; executable selectors `23`.
- Remaining gate blocker called out by the gate: missing Wave 2
  `logs/product-oracle-*.json` artifact with finite ArcFace and lipsync values.
- Open-row selector suite remains red: `15 failed, 55 passed`.
- `scripts/ci_smoke.py` returned `OK` with existing advisory doc-anchor and
  invisible-green warnings only.
- No production code, inventory row, lock, or verification-report was authored
  by operator-1 in this handoff.

Recent git evidence:

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
ccb344b5 docs(handoff): director perf reroute standby
acc7db4a docs(handoff): director2 perf lanev standby
f9616565 docs(handoff): update coordinator perf lanev wrap
5df710d8 docs(handoff): operator2 perf lanev pending
9d7828ca docs(handoff): coordinator perf lanev wrap
```

Fresh operator status after final consume:

```text
$ CODEX_SEAT=operator GIT_INDEX_FILE=.git/index-codex-operator \
  .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2
HEAD ccb344b5 docs(handoff): director perf reroute standby
vs origin/main: 16 ahead, 0 behind
mailbox cursor: 2026-06-15T18:08:22Z
UNREAD: 0
Wave 2 gate: UNMET counts={'verified': 19, 'open': 11}
```

Gate and smoke evidence:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 19, 'open': 11}
gate rows: 21; executable selectors: 23
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
15 failed, 55 passed

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

## Mail Processed

Initial operator orientation in this handoff saw `UNREAD: 1` at cursor
`2026-06-15T17:29:15Z`. That event was read and consumed:

- `coordination/mailbox/sent/2026-06-15T17-52-06Z-coordinator-to-all-coordination.md`
  - Coordinator rerouted after the perf-phase landing.
  - `operator2` is active on formal Lane V for
    `6e8da868 fix(performance): gate capture before budget spend`.
  - `director2` is standing by for the operator2 result.
  - `operator` remains Pair-A no-op/standby.
  - Do not verify Pair-B diffs.
  - No product-oracle paid/pod spend is authorized by the route.

After concurrent handoff commits landed, operator saw `UNREAD: 3` at cursor
`2026-06-15T17:52:06Z`. Those events were read and consumed:

- `coordination/mailbox/sent/2026-06-15T18-04-42Z-director-to-all-status.md`
  - Pair-A/director remains idle and should not take Pair-B rows.
- `coordination/mailbox/sent/2026-06-15T18-05-18Z-operator2-to-all-status.md`
  - `operator2` has not yet issued GO/NITS/FAIL; formal Lane V remains pending.
- `coordination/mailbox/sent/2026-06-15T18-05-33Z-director2-to-all-status.md`
  - `director2` is standby-only until the operator2 verdict lands.

Operator then sent and self-consumed this status event:

- `coordination/mailbox/sent/2026-06-15T18-08-22Z-operator-to-all-status.md`

Cursor evidence:

```text
$ CODEX_SEAT=operator GIT_INDEX_FILE=.git/index-codex-operator \
  coordination/bin/consume-events operator
cursor operator: 2026-06-15T17:29:15Z -> 2026-06-15T17:52:06Z; unread now: 0 (staged; fold into your next substantive commit)

$ CODEX_SEAT=operator GIT_INDEX_FILE=.git/index-codex-operator \
  coordination/bin/consume-events operator
cursor operator: 2026-06-15T17:52:06Z -> 2026-06-15T18:05:33Z; unread now: 0 (staged; fold into your next substantive commit)

$ CODEX_SEAT=operator GIT_INDEX_FILE=.git/index-codex-operator \
  coordination/bin/consume-events operator
cursor operator: 2026-06-15T18:05:33Z -> 2026-06-15T18:08:22Z; unread now: 0 (staged; fold into your next substantive commit)
```

## Current Routing

Operator-1 / Pair-A is idle.

Resume operator-1 only if one of these lands:

1. Pair-A director lands a Pair-A shipping diff and requests Lane V.
2. Coordinator routes product-oracle identity / ArcFace review to Pair-A.
3. A Tier-A co-sign, NITS reread, or user-principal instruction explicitly
   names operator-1.

Do not verify Pair-B diffs by default. Current Pair-B route is:
`operator2` verifies `6e8da868`; `director2` waits for that verdict before any
new Pair-B lane pickup.

## Dirty Tree Notes

The shared worktree/default index still has other-seat cursor and handoff churn.
Preserve it and use the operator per-seat index plus explicit pathspecs.

This operator handoff should commit only:

- `coordination/mailbox/seen/operator.txt`
- `coordination/mailbox/sent/2026-06-15T18-08-22Z-operator-to-all-status.md`
- `docs/HANDOFF-operator-2026-06-16-noop-after-perf-reroute.md`
