# HANDOFF - Operator-1 (Pair-A), 2026-06-15 - product-oracle guidance consumed, idle

READ FIRST AS operator-1. Trust git and mailbox artifacts over this prose if
they diverge. This handoff wraps the Codex operator cycle after the
coordinator Wave-2 resync, Pair-A director product-oracle guidance, and a
new Pair-B lipsync fix that has been routed to operator2 for Lane V.

## State At Stop

- Seat marker: `CODEX_SEAT=operator`.
- Git index marker: `.git/index-codex-operator`; use
  `env -u GIT_INDEX_FILE` for git/pytest evidence unless explicitly
  maintaining a seat index.
- Current HEAD:

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
2b5fdf0d coord(cursor): director2 consume final wrap addenda
50f49419 coord(cursor): director2 consume handoff statuses
cc2b3f61 docs(handoff): director2 lipsync costkey Lane V pending
aa6f00f9 coord(verify): request lipsync costkey Lane V
82c6a2a1 coord(protocol): adopt subagent workflow per seat
```

- This handoff commit folds the operator mailbox cursor through
  `2026-06-15T11:37:38Z`.

```text
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2
branch main
2b5fdf0d  coord(cursor): director2 consume final wrap addenda
vs origin/main: 87 ahead, 0 behind
cursor: 2026-06-15T11:35:35Z
UNREAD: 1
  • 2026-06-15T11-37-38Z-coordinator-to-all-coordination.md
```

```text
$ env -u GIT_INDEX_FILE coordination/bin/consume-events operator
cursor operator: 2026-06-15T11:32:23Z -> 2026-06-15T11:33:22Z; unread now: 0 (staged; fold into your next substantive commit)
```

The final consume reads the coordinator handoff/status event:
`coordination/mailbox/sent/2026-06-15T11-34-40Z-coordinator-to-all-coordination.md`.

```text
$ env -u GIT_INDEX_FILE coordination/bin/consume-events operator
cursor operator: 2026-06-15T11:33:22Z -> 2026-06-15T11:34:40Z; unread now: 0 (staged; fold into your next substantive commit)
```

One more all-seat status arrived during wrap, and this handoff also folds it:

```text
$ env -u GIT_INDEX_FILE coordination/bin/consume-events operator
cursor operator: 2026-06-15T11:34:40Z -> 2026-06-15T11:35:35Z; unread now: 0 (staged; fold into your next substantive commit)
```

The final coordinator handoff event was read and consumed too:

```text
$ env -u GIT_INDEX_FILE coordination/bin/consume-events operator
cursor operator: 2026-06-15T11:35:35Z -> 2026-06-15T11:37:38Z; unread now: 0 (staged; fold into your next substantive commit)
```

- Fresh smoke at this HEAD is OK with existing advisory warnings only.

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Advisories in that smoke: PROGRAM-MANUAL doc-anchor drift, the two historical
`verify-readiness` mailbox unknown-kind warnings, and the existing R2
invisible-green warnings.

## What This Operator Cycle Did

1. Read and consumed the coordinator Wave-2 routing event:
   `coordination/mailbox/sent/2026-06-15T11-01-23Z-coordinator-to-all-coordination.md`.
2. Published operator readiness:
   `coordination/mailbox/sent/2026-06-15T11-26-36Z-operator-to-all-status.md`.
3. Read the Pair-A director product-oracle identity guidance, now committed in
   `b366ae0d`:
   `coordination/mailbox/sent/2026-06-15T11-23-24Z-director-to-all-coordination.md`.
4. Observed Pair-B commit `aeb1a2b7 fix(lipsync): price postprocess cost key`
   after the first handoff draft. Its stat scope is:

```text
$ env -u GIT_INDEX_FILE git show --stat --oneline --decorate --no-renames aeb1a2b7
aeb1a2b7 fix(lipsync): price postprocess cost key
 ARCHITECTURE.md                                  |  4 +-
 cinema/shots/controller.py                       | 18 +++++--
 coordination/mailbox/seen/director2.txt          |  2 +-
 docs/REMEDIATION-INVENTORY.md                    |  2 +-
 tests/unit/test_discovery_cost_xfail.py          | 67 +++++-------------------
 tests/unit/test_postprocess_audio_propagation.py | 30 +++++++++++
 6 files changed, 61 insertions(+), 62 deletions(-)
```

5. Did not run Lane V. The only shipping fix observed is Pair-B-owned and
   should be verified by `operator2` unless coordinator explicitly routes a
   cross-lane read-only review.
6. Consumed the operator2 broadcast
   `coordination/mailbox/sent/2026-06-15T11-32-23Z-operator2-to-all-status.md`.
   It was already superseded by the later targeted Lane V request.
7. Read for context the targeted Pair-B Lane V request:
   `coordination/mailbox/sent/2026-06-15T11-31-19Z-director2-to-operator2-verify-request.md`.
   It requests operator2 Lane V on `aeb1a2b7`; it is not addressed to operator1.
8. Consumed the director2 all-seat handoff/status:
   `coordination/mailbox/sent/2026-06-15T11-33-22Z-director2-to-all-status.md`.
   It confirms operator2 remains verifier for `aeb1a2b7`, the row stays open
   pending operator2 GO and coordinator reconciliation, and no push was performed.
9. Consumed the coordinator all-seat handoff/status:
   `coordination/mailbox/sent/2026-06-15T11-34-40Z-coordinator-to-all-coordination.md`.
   It confirms operator2 owes Lane V on `aeb1a2b7`, Pair-A stays available for
   Tier-A co-signs and product-oracle/identity review, active locks are only
   `.gitkeep`, no product-oracle artifact exists, and push remains user-gated.
10. Consumed the director all-seat handoff/status:
   `coordination/mailbox/sent/2026-06-15T11-35-32Z-director-to-all-status.md`.
   It confirms Pair-A director remains readiness-only, no Pair-A production
   row is active except deferred/open/test-infeasible
   `identity-arcface-embselect`, and operator2 owns Lane V for `aeb1a2b7`.
11. Consumed the operator2 addendum:
   `coordination/mailbox/sent/2026-06-15T11-35-35Z-operator2-to-all-status.md`.
   It says the earlier operator2 idle status was superseded, `aeb1a2b7` Lane V
   is owed, no verification-report was emitted, and `lipsync-postproc-costkey`
   must not be reconciled until a real operator2 GO exists. It also references
   a coordinator confirmation at `2026-06-15T11-32-27Z`, but that exact event
   path is not present in the current tree, so this handoff cites the operator2
   addendum itself.
12. Observed latest director2 cursor addendum `2b5fdf0d`, which only updates
    director2 cursor/handoff documentation; it does not change operator1
    routing.
13. Consumed the coordinator final handoff:
    `coordination/mailbox/sent/2026-06-15T11-37-38Z-coordinator-to-all-coordination.md`.
    It repeats that operator2 owes Lane V on `aeb1a2b7`, coordinator reconciles
    only after a real operator2 GO, Pair-B owns remaining active Wave-2 rows,
    Pair-A stays available for co-sign/product-oracle/identity review, push
    remains user-gated, and no product-oracle artifact exists.
14. Did not author production code.

## Current Routing

- Pair-B remains implementation lead for active Wave-2 production rows.
- `operator2` remains Pair-B verifier.
- `aeb1a2b7 fix(lipsync): price postprocess cost key` is Pair-B shipping work;
  director2 has requested operator2 Lane V in `aa6f00f9`, and `cc2b3f61`
  records the director2 handoff while that Lane V is pending.
- This `operator` seat stays ready for Pair-A verification, Tier-A co-sign
  evidence, product-oracle identity/ArcFace review, or coordinator-routed
  read-only checks.
- Do not verify Pair-B work unless the coordinator explicitly routes a
  cross-lane read-only review.

## Product-Oracle State

No committed Wave-2 product-oracle artifact exists yet:

```text
$ env -u GIT_INDEX_FILE git ls-tree -r --name-only HEAD -- logs | rg '^logs/product-oracle-.*\.json$'
<no output; exit 1>
```

The director guidance says the eventual artifact should include the committed
instrument path/command, source video/reference/audio paths, ArcFace scorer
semantics, frame policy, lip-sync method/timebase, and explicit degraded or
inconclusive markers. The gate currently enforces only the minimum shape:
`artifact_kind=product-oracle`, `wave=2`, finite `arcface.arc_score`, and
finite `lipsync.offset_frames`.

## Wave 2 Gate

Wave 2 is still unmet:

```text
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2
Wave 2 gate: UNMET counts={'verified': 16, 'open': 14}
BLOCKER [MAJOR/open] spent-usd-reset-on-resume (cinema/checkpoint.py:163): no executable xfail-pin selector
BLOCKER [MAJOR/open] perf-phase-no-gate (cinema/shots/controller.py:1076): no executable xfail-pin selector
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact with artifact_kind=product-oracle, wave=2, finite arcface.arc_score, and finite lipsync.offset_frames
PYTEST: 16 failed, 45 passed
```

## Next Operator-1 Entry

1. Run:

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2
env -u GIT_INDEX_FILE git log --oneline -5
```

2. Surface the live unread count before consuming mail.
3. Consume only if unread is nonzero:

```bash
env -u GIT_INDEX_FILE coordination/bin/consume-events operator
```

4. If a Pair-A production `fix` / `feat` / `refactor` landed, run Lane V and
   emit a mailbox `verification-report`.
5. If a product-oracle artifact lands, review identity/ArcFace semantics from
   the Pair-A side; the artifact being finite is not by itself enough to prove
   identity quality.
6. Keep commits explicit-pathspec only. The shared worktree has unrelated dirty
   and staged state from other seats.
