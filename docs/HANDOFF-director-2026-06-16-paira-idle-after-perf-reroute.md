# HANDOFF - Director (Pair-A), 2026-06-16 - idle after perf reroute

READ FIRST AS NEXT PAIR-A DIRECTOR. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Wrap

- Seat: `director` / Pair-A image, identity, realism.
- Write timestamp: `2026-06-15T18:04:42Z` (`2026-06-16T03:04:42+0900`
  Asia/Seoul).
- Current HEAD at final pre-commit orientation:
  `acc7db4a docs(handoff): director2 perf lanev standby`.
- Branch relation at final pre-commit orientation: `main`, 15 ahead / 0 behind
  origin.
- Director unread at orientation: 1 event,
  `2026-06-15T17-52-06Z-coordinator-to-all-coordination.md`.
- Director cursor after consuming that event: `2026-06-15T17:52:06Z`;
  unread then 0.
- While this handoff was being written, peer status events landed at
  `18:05:18Z`, `18:05:33Z`, and `18:08:22Z`. Director read those all-seat
  status events and the final staged cursor is `2026-06-15T18:08:22Z`;
  expected final director unread is 0 against the present sent-mailbox tree.
- A transient `18:05:41Z` operator status event was visible and read during the
  handoff window, but it was missing at final pre-commit. This commit does not
  advance the durable director cursor past that missing event.
- Active locks: `coordination/locks/.gitkeep` only.
- Wave 2 remains `UNMET`: `verified=19`, `open=11`, executable selectors `23`.
- The prior `perf-phase-no-gate` no-selector blocker is gone, but the row is
  still open until operator2 formal Lane V lands.
- No committed `logs/product-oracle-*.json` artifact exists.
- Smoke returned `OK` with existing advisories only: 176
  `docs/PROGRAM-MANUAL.md` doc-anchor drifts and two R2 invisible-green
  warnings.
- No production code, remediation inventory row, or lock was edited by this
  director handoff.
- Push remains user-gated.

## Evidence

```text
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2
HEAD cfcd755f coord(route): reroute perf phase verification
vs origin/main: 11 ahead, 0 behind
mailbox cursor: 2026-06-15T17:29:15Z
UNREAD: 1
  - 2026-06-15T17-52-06Z-coordinator-to-all-coordination.md
Wave 2 gate: UNMET counts={'verified': 19, 'open': 11}
gate rows: 21; executable selectors: 23
PRODUCT ORACLE BLOCKER: missing Wave 2 product-oracle artifact
PYTEST summary: 15 failed, 55 passed

$ CODEX_SEAT=director GIT_INDEX_FILE=.git/index-codex-director coordination/bin/consume-events director
cursor director: 2026-06-15T17:29:15Z -> 2026-06-15T17:52:06Z; unread now: 0 (staged; fold into your next substantive commit)

$ env -u GIT_INDEX_FILE git log --oneline -5
acc7db4a docs(handoff): director2 perf lanev standby
f9616565 docs(handoff): update coordinator perf lanev wrap
5df710d8 docs(handoff): operator2 perf lanev pending
9d7828ca docs(handoff): coordinator perf lanev wrap
cfcd755f coord(route): reroute perf phase verification

$ env -u GIT_INDEX_FILE git rev-list --left-right --count origin/main...HEAD
0       15

$ CODEX_SEAT=director GIT_INDEX_FILE=.git/index-codex-director coordination/bin/consume-events director
cursor director: 2026-06-15T17:52:06Z -> 2026-06-15T18:05:33Z; unread now: 0 (staged; fold into your next substantive commit)

$ test -f coordination/mailbox/sent/2026-06-15T18-05-41Z-operator-to-all-status.md && echo present || echo missing
missing

$ CODEX_SEAT=director GIT_INDEX_FILE=.git/index-codex-director coordination/bin/consume-events director
cursor director: 2026-06-15T18:05:33Z -> 2026-06-15T18:08:22Z; unread now: 0 (staged; fold into your next substantive commit)

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
WARNING: 176 doc-anchor drift(s) in docs/PROGRAM-MANUAL.md
R1 xfail-strictness ....... PASS
R2 invisible-green ........ WARN
R3 gate-executes-pins ..... PASS
R4 ci-runs-runxfail ....... PASS
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 19, 'open': 11}
gate rows: 21; executable selectors: 23
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact with artifact_kind=product-oracle, wave=2, finite arcface.arc_score, and finite lipsync.offset_frames
PYTEST summary: 15 failed, 55 passed

$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output

$ GIT_INDEX_FILE=.git/index-codex-director git diff --cached --name-status
M       coordination/mailbox/seen/director.txt
A       coordination/mailbox/sent/2026-06-15T18-04-42Z-director-to-all-status.md
A       docs/HANDOFF-director-2026-06-16-paira-idle-after-perf-reroute.md
```

## Consumed Mailbox Event

The consumed coordinator route is:

- `coordination/mailbox/sent/2026-06-15T17-52-06Z-coordinator-to-all-coordination.md`

Important routing from that event:

- `operator2` is active on formal Lane V for
  `6e8da868 fix(performance): gate capture before budget spend`.
- `director2` stands by for the operator2 GO/NITS/FAIL result and should not
  start `lipsync-veto`, `web_server.py`, or checkpoint rows yet.
- `director` remains implementation-idle. Stay ready for product-oracle
  identity/ArcFace review, Tier-A co-signs, or explicit Pair-A work.
- `operator` remains no-op/standby and should not verify Pair-B diffs.
- Product-oracle remains mandatory for Wave 2 close, but no pod or paid API
  spend is authorized by this route.
- Do not claim `W2-auto_approve.py.lock` or `W2-web_server.py.lock`; lock
  claiming and push remain user-gated.

Late status events read during handoff:

- `coordination/mailbox/sent/2026-06-15T18-05-18Z-operator2-to-all-status.md`
  - operator2 handoff/status only; formal Lane V remains pending.
- `coordination/mailbox/sent/2026-06-15T18-05-33Z-director2-to-all-status.md`
  - director2 standby only; no new lane pickup.
- `coordination/mailbox/sent/2026-06-15T18-08-22Z-operator-to-all-status.md`
  - Pair-A operator no-op/standby; no Pair-A verification active.
- A transient `coordination/mailbox/sent/2026-06-15T18-05-41Z-operator-to-all-status.md`
  was read but is missing from the final sent tree; the staged cursor is left at
  the latest durable operator status, `2026-06-15T18:08:22Z`.

## Current Pair-A Routing

Pair-A director remains idle/readiness-only unless one of these arrives:

- Product-oracle artifact needing identity / GhostFaceNet / ArcFace-result
  review.
- Tier-A co-sign request from Pair-B/director2 or coordinator.
- New or reactivated Pair-A row.
- User-principal direct instruction changing seat ownership.

Without a committed product-oracle artifact or user-authorized paid/pod
measurement, prepare only no-spend artifact-validation criteria.

Do not take Pair-B implementation work from this seat. Do not verify the
Pair-B performance diff; `operator2` owns that Lane V.

## Current Wave 2 Blockers

Wave 2 cannot close yet:

- `perf-phase-no-gate` is landed but still open pending operator2 formal GO.
- The committed Wave 2 product-oracle artifact is missing.
- Executable red pins remain in postprocess lipsync sibling coverage,
  web-server HTTP cluster, and checkpoint cluster.

Do not declare the wave green from status-column movement alone.

## Dirty Tree Notes

The default index currently shows concurrent-seat churn across production,
tests, docs, mailbox, and cursor files. Use the director per-seat index and
explicit pathspecs. Do not clean up or normalize artifacts this Pair-A director
does not own.

This handoff should commit only:

- `docs/HANDOFF-director-2026-06-16-paira-idle-after-perf-reroute.md`
- `coordination/mailbox/sent/2026-06-15T18-04-42Z-director-to-all-status.md`
- `coordination/mailbox/seen/director.txt`
