# HANDOFF - Operator2 (Pair-B), 2026-06-15 - lipsync costkey Lane V owed

READ FIRST AS operator2. Trust git and mailbox artifacts over this prose if
they diverge. This handoff wraps a Codex live-operator session. Operator2 did
not author production code, did not run Lane V, did not emit a
verification-report, and did not push. A Pair-B verification request landed
during handoff; the next operator2 action is Lane V on `aeb1a2b7`.

## State At Stop

- Seat marker used: `CODEX_SEAT=operator2`.
- Seat index marker: `.git/index-codex-operator2`.
- HEAD at wrap evidence refresh: `aa6f00f9 coord(verify): request lipsync costkey Lane V`.
- Branch relation from final seat status: `main`, `84 ahead`, `0 behind`.
- Operator2 mailbox cursor after final self-addendum consume: `2026-06-15T11:35:35Z`.
- Operator2 unread count after handoff consume: `0`.
- Pair-B Lane V is owed next for `aeb1a2b7 fix(lipsync): price postprocess cost key`.

Recent git evidence:

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
aa6f00f9 coord(verify): request lipsync costkey Lane V
82c6a2a1 coord(protocol): adopt subagent workflow per seat
aeb1a2b7 fix(lipsync): price postprocess cost key
b366ae0d coord(director): publish product-oracle guidance
1e816f3e coord(status): operator ready after product-oracle guidance
```

Live operator2 status before consuming the last unread event:

```text
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator2 --wave 2
HEAD: b366ae0d coord(director): publish product-oracle guidance
vs origin/main: 81 ahead, 0 behind
cursor: 2026-06-15T11:23:24Z
UNREAD: 1
  - 2026-06-15T11-26-36Z-operator-to-all-status.md
Wave 2 gate: UNMET counts={'verified': 16, 'open': 14}
```

Cursor consume evidence:

```text
$ coordination/bin/consume-events operator2
cursor operator2: 2026-06-15T11:23:24Z -> 2026-06-15T11:26:36Z; unread now: 0 (staged; fold into your next substantive commit)

$ coordination/bin/consume-events operator2
cursor operator2: 2026-06-15T11:26:36Z -> 2026-06-15T11:32:23Z; unread now: 0 (staged; fold into your next substantive commit)

$ coordination/bin/consume-events operator2
cursor operator2: 2026-06-15T11:32:23Z -> 2026-06-15T11:33:22Z; unread now: 0 (staged; fold into your next substantive commit)

$ coordination/bin/consume-events operator2
cursor operator2: 2026-06-15T11:33:22Z -> 2026-06-15T11:35:35Z; unread now: 0 (staged; fold into your next substantive commit)
```

## Mail Read This Session

Consumed during this handoff:

- `coordination/mailbox/sent/2026-06-15T11-26-36Z-operator-to-all-status.md`
  - Pair-A operator status after product-oracle guidance.
  - No Pair-B Lane V routing.
  - Confirms no product-oracle artifact was available to Pair-A operator yet.

Read for context:

- `coordination/mailbox/sent/2026-06-15T11-23-24Z-director-to-all-coordination.md`
  - Pair-A director product-oracle identity review guidance.
  - This is guidance for the owed Wave-2 product-oracle artifact, not a
    verification-report and not a Pair-B Lane V substitute.
  - Director2 remains the implementation lead if a product-oracle measurement
    script or artifact is authored as Pair-B product-execution work.
  - Operator2 remains the verifier for any Pair-B shipping diff.

Late-arriving verification route, consumed/read during handoff:

- `coordination/mailbox/sent/2026-06-15T11-31-19Z-director2-to-operator2-verify-request.md`
  - Requests operator2 Lane V on
    `aeb1a2b7 fix(lipsync): price postprocess cost key`.
  - Scope says `cinema/shots/controller.py` adds `_lipsync_cost_api_key()`,
    routes motion F1b and postprocess lip-sync cost records through it, and
    adds a live `apply_correction("lip_sync")` regression.
  - Suggested checks: actual diff only; non-vacuity of the apply-correction
    regression; default engine maps to `LIPSYNC_DEFAULT`; `wave_gate_check.py`
    includes the new selector and no longer uses the obsolete direct
    `record_api_call("syncsov3")` pin.
- `coordination/mailbox/sent/2026-06-15T11-32-27Z-coordinator-to-all-coordination.md`
  - Coordinator confirms operator2 owes Lane V on `aeb1a2b7`.
  - Coordinator should reconcile `lipsync-postproc-costkey` only after a real
    operator2 GO.
- `coordination/mailbox/sent/2026-06-15T11-33-22Z-director2-to-all-status.md`
  - Director2 handoff confirms `aeb1a2b7` landed and `aa6f00f9` requested Lane V.

Landed diff summary for the owed Lane V:

```text
$ env -u GIT_INDEX_FILE git show --stat --oneline --no-renames aeb1a2b7 aa6f00f9
aeb1a2b7 fix(lipsync): price postprocess cost key
 ARCHITECTURE.md                                  |  4 +-
 cinema/shots/controller.py                       | 18 +++++--
 coordination/mailbox/seen/director2.txt          |  2 +-
 docs/REMEDIATION-INVENTORY.md                    |  2 +-
 tests/unit/test_discovery_cost_xfail.py          | 67 +++++-------------------
 tests/unit/test_postprocess_audio_propagation.py | 30 +++++++++++
 6 files changed, 61 insertions(+), 62 deletions(-)
aa6f00f9 coord(verify): request lipsync costkey Lane V
 ...31-19Z-director2-to-operator2-verify-request.md | 26 ++++++++++++++++++++++
 1 file changed, 26 insertions(+)
```

Coordinator routing still in force:

- `coordination/mailbox/sent/2026-06-15T11-01-23Z-coordinator-to-all-coordination.md`
  - Operator2 is Pair-B verification lead.
  - For each director2 shipping commit, run Lane V on the actual landed diff,
    verify xfail-pin flip/non-vacuity where applicable, run focused tests plus
    `scripts/ci_smoke.py`, and send one `verification-report` GO/NITS/FAIL.
  - Do not implement the fix you verify.

## Verification And Gate Evidence

Fresh smoke is OK:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Known smoke advisories at this stop:

- `136` doc-anchor drift warnings in `docs/PROGRAM-MANUAL.md`.
- Two legacy mailbox-kind advisories for `verify-readiness` events.
- R2 invisible-green warnings for `tests/unit/test_discovery_identity_xfail.py`
  and `tests/unit/test_lane_silent_gate_siblings_xfail.py`.

Wave 2 remains red:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 16, 'open': 14}
BLOCKER [MAJOR/open] spent-usd-reset-on-resume (cinema/checkpoint.py:163): no executable xfail-pin selector
BLOCKER [MAJOR/open] perf-phase-no-gate (cinema/shots/controller.py:1076): no executable xfail-pin selector
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact with artifact_kind=product-oracle, wave=2, finite arcface.arc_score, and finite lipsync.offset_frames
16 failed, 45 passed
```

The failing Wave-2 executable-pin suite is expected process state, not a new
operator2 verdict.

## Operator2 Phase Read

Pair-B Lane V is currently owed to operator2.

- Owed target: `aeb1a2b7 fix(lipsync): price postprocess cost key`.
- Routing event: `coordination/mailbox/sent/2026-06-15T11-31-19Z-director2-to-operator2-verify-request.md`.
- Coordination event: `coordination/mailbox/sent/2026-06-15T11-32-27Z-coordinator-to-all-coordination.md`.
- This handoff stops before starting Lane V because the user requested
  `handoff`; the next operator2 should start there.
- Dirty working-tree edits still exist. Verify the landed commit diff, not
  unrelated uncommitted state.

Start the next session with seat status, then run Lane V on `aeb1a2b7` unless a
newer user/coordinator instruction supersedes it.

## Next Operator2 Focus

Likely upcoming Pair-B verification rows remain:

- `lipsync-postproc-costkey`
- `download-urllib-notimeout`
- checkpoint cluster:
  `ckpt-sceneidx-dead`, `ckpt-shotaudio-loss`,
  `ckpt-projectid-nocrosscheck`
- design/blocker rows:
  `spent-usd-reset-on-resume`, `perf-phase-no-gate`
- product-oracle artifact once an instrument and committed
  `logs/product-oracle-*.json` artifact land

For `aeb1a2b7`, verify actual diff scope first, then focused tests, then
`scripts/ci_smoke.py`. Use `scripts/wave_gate_check.py 2` as process state
only; it is not by itself a correctness proof.

## Dirty Worktree Caveat

The shared tree and active seat index remain dirty from other seats and
protocol work. Operator2 did not revert or normalize any of it. Use explicit
pathspecs.

Active seat-index staged scope before this handoff included unrelated changes:

```text
$ git diff --cached --stat
16 files changed, 65 insertions(+), 608 deletions(-)
```

Representative staged paths included:

- `ARCHITECTURE.md`
- `cinema/shots/controller.py`
- `docs/REMEDIATION-INVENTORY.md`
- `tests/unit/test_discovery_cost_xfail.py`
- `tests/unit/test_postprocess_audio_propagation.py`
- multiple mailbox cursor/event delete entries

Working-tree status also showed broad unrelated modifications in protocol
skills, Codex agent configs, docs, tests, and mailbox delete/untracked twins.
Do not assume operator2 owns those changes without checking the relevant diff
and mailbox/git history.

This handoff intentionally adds only this document, emits status mailbox events
`coordination/mailbox/sent/2026-06-15T11-32-23Z-operator2-to-all-status.md` and
`coordination/mailbox/sent/2026-06-15T11-35-35Z-operator2-to-all-status.md`,
consumes the operator2 mailbox cursor through the addendum self-status event at
`2026-06-15T11:35:35Z`, and leaves the owed Lane V for the next operator2 turn.
