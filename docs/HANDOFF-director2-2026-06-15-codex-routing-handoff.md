# HANDOFF - Director2 (Pair-B), 2026-06-15 - routing handoff

READ FIRST AS NEXT PAIR-B DIRECTOR. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Wrap

- Seat: `director2` / Pair-B video, assembly, audio, cost.
- Write timestamp: `2026-06-15T12:26:43Z`; final cursor observed after later
  peer idle status: `2026-06-15T12:28:00Z`.
- Durable HEAD observed before this handoff commit:
  `51078e5d docs(handoff): operator2 idle at cefd2971`.
- Branch from live seat status: `main`, 101 ahead / 0 behind origin.
- Director2 mailbox cursor is `2026-06-15T12:28:00Z`; unread is 0.
- Active locks: `coordination/locks/.gitkeep` only.
- Wave 2 remains `UNMET`: `verified=17`, `open=13`.
- No committed `logs/product-oracle-*.json` artifact exists.
- Smoke was re-run in this handoff pass and returned `OK` with existing
  advisories only.
- No production code, remediation inventory row, lock file, or existing WIP
  file was edited by this handoff pass.
- Push and lock claiming remain user-gated.

Evidence:

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
51078e5d docs(handoff): operator2 idle at cefd2971
ef92b666 docs(handoff): operator codex idle stale index
cefd2971 docs(handoff): director subagent workflow wrap
72a2d83c docs(handoff): operator consume director wrap
04912467 docs(handoff): operator consume late statuses

$ CODEX_SEAT=director2 GIT_INDEX_FILE=/Users/hyungkoookkim/Content/.git/index-codex-director2 .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 2
HEAD 51078e5d docs(handoff): operator2 idle at cefd2971
vs origin/main: 101 ahead, 0 behind
mailbox cursor: 2026-06-15T12:28:00Z
UNREAD: 0
Wave 2 gate: UNMET counts={'verified': 17, 'open': 13}

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected -- every relied-on green is backed by execution.
OK

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 17, 'open': 13}
15 failed, 46 passed

$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

Known smoke advisories remain: `docs/PROGRAM-MANUAL.md` doc-anchor drift, two
historical mailbox unknown-kind warnings, and two R2 invisible-green warnings.

## Mail Processed

At handoff start, `director2` had already consumed the coordinator routing
notice through `2026-06-15T12:10:22Z` and `seat_status.py director2 --wave 2`
reported unread 0.

While writing this handoff, the following status events appeared and were
processed through the director2 cursor:

- `coordination/mailbox/sent/2026-06-15T12-26-05Z-director-to-all-status.md`
  - Pair-A director idle after the 12:10 coordinator routing; no active Pair-A
  implementation row.
- `coordination/mailbox/sent/2026-06-15T12-26-29Z-operator-to-all-status.md`
  - Pair-A operator idle; no Pair-A Lane V/NITS/lock action owed.
- `coordination/mailbox/sent/2026-06-15T12-26-43Z-director2-to-all-status.md`
  - this director2 status broadcast.
- `coordination/mailbox/sent/2026-06-15T12-28-00Z-operator2-to-all-status.md`
  - operator2 idle; no Lane V, NITS re-read, or operator2 verification task
  owed by latest observable state.

Cursor evidence:

```text
$ CODEX_SEAT=director2 GIT_INDEX_FILE=/Users/hyungkoookkim/Content/.git/index-codex-director2 coordination/bin/consume-events director2
fatal: Unable to create '/Users/hyungkoookkim/Content/.git/index-codex-director2.lock': Operation not permitted

$ CODEX_SEAT=director2 GIT_INDEX_FILE=/Users/hyungkoookkim/Content/.git/index-codex-director2 coordination/bin/consume-events director2
cursor director2: already at 2026-06-15T12:26:43Z (no-op)

$ CODEX_SEAT=director2 GIT_INDEX_FILE=/Users/hyungkoookkim/Content/.git/index-codex-director2 coordination/bin/consume-events director2
cursor director2: 2026-06-15T12:26:43Z -> 2026-06-15T12:28:00Z; unread now: 0 (staged; fold into your next substantive commit)

$ sed -n '1,40p' coordination/mailbox/seen/director2.txt
2026-06-15T12:28:00Z
```

The first consume hit the expected sandbox block while staging the per-seat git
index after the cursor file had advanced. The escalated retry confirmed the
cursor state, then the final consume processed the later operator2 idle status.

## Current Pair-B Routing

Follow the coordinator's `2026-06-15T12:10:22Z` cycle directions:

- Immediate Pair-B priority is `download-urllib-notimeout`.
- Existing local WIP for that row is still present in the shared tree and was
  not authored or modified by this pass.
- Commit or otherwise resolve the scoped download WIP, then request operator2
  Lane V if the row remains pending.
- If choosing a next no-lock implementation after that, prefer
  `spent-usd-reset-on-resume`, then `perf-phase-no-gate`.
- Stop before any row requiring `coordination/bin/claim-lock`; lock claiming
  fetches/pushes and remains user-gated.

Inventory evidence:

```text
$ rg -n "\\| 2 \\| open \\||download-urllib-notimeout|spent-usd-reset-on-resume|perf-phase-no-gate|product-oracle" docs/REMEDIATION-INVENTORY.md
line 43 lipsync-veto: wave=2 status=open lock=W2-auto_approve.py.lock
line 53 lipsync-precheck-cascade-gap: wave=2 status=open
line 54 download-urllib-notimeout: wave=2 status=open, implemented pending operator2 Lane V
line 56-61 web_server.py HTTP rows: wave=2 status=open lock=W2-web_server.py.lock
line 62-64 checkpoint rows: wave=2 status=open
line 73 spent-usd-reset-on-resume: wave=2 status=open, design-open/no selector
line 75 perf-phase-no-gate: wave=2 status=open, test-infeasible/no selector
```

## Dirty Tree Notes

The shared tree remains broadly dirty from other seats and protocol work. This
handoff intentionally preserves all of it.

Existing Pair-B download WIP still visible in this per-seat view:

```text
$ CODEX_SEAT=director2 GIT_INDEX_FILE=/Users/hyungkoookkim/Content/.git/index-codex-director2 git status --short
 M ARCHITECTURE.md
 M docs/REMEDIATION-INVENTORY.md
 M phase_c_ffmpeg.py
 M tests/unit/test_discovery_io_xfail.py
?? docs/HANDOFF-director2-2026-06-15-download-urllib-notimeout-uncommitted.md
?? docs/superpowers/briefs/2026-06-15-download-urllib-timeout.md
```

There is also unrelated protocol/transplant dirt in `.agents/`, `.codex/`,
`coordination/`, docs, scripts, requirements, and tests. Do not broad-stage,
normalize, or revert it.

This handoff pass wrote the director2 status event at:

- `coordination/mailbox/sent/2026-06-15T12-26-43Z-director2-to-all-status.md`

That status event is already tracked at matching content in the current HEAD
view. The final staged commit for this handoff should contain only:

- `docs/HANDOFF-director2-2026-06-15-codex-routing-handoff.md`
- `coordination/mailbox/seen/director2.txt` advanced to `2026-06-15T12:28:00Z`
