# Handoff - operator2 - 2026-06-17 mailbox CLI NITS standby

READ FIRST AS `operator2`. Trust current git, mailbox bodies, and live gate
evidence over this prose if they diverge.

Generated: `2026-06-16T20:24:29Z` (`2026-06-17T05:24:29+0900` KST)
Seat: `operator2`
Repo: `/Users/hyungkoookkim/Content`

## Refresh First

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator2 --wave 3
env -u GIT_INDEX_FILE git log --oneline -12
env -u GIT_INDEX_FILE git status --short --branch
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3 --validate-route coordination/mailbox/sent/2026-06-16T20-00-52Z-coordinator-to-all-coordination.md
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Use `env -u GIT_INDEX_FILE` for ordinary git/pytest commands. Push, lock
claim/release, pod/API spend, dependency edits, production generation, and
inventory transitions remain user-gated.

## Live State At Handoff

Latest refreshed status before this handoff:

```text
HEAD: 3d141d5c operator(verify): FAIL git-index guard quote-aware
branch: main
vs origin/main: 28 ahead, 0 behind
operator2 cursor: 2026-06-16T20:11:48Z
operator2 unread: 0
Wave 3 gate: MET counts={'verified': 3}
PRODUCT ORACLE: logs/product-oracle-wave3.json
```

Recent history at refresh:

```text
3d141d5c operator(verify): FAIL git-index guard quote-aware
5412cb65 operator2(verify): NITS mailbox cli Lane V
00fc17fc docs(handoff): coordinator harness lanev pending
ad17317b docs(handoff): director2 mailbox cli Lane V pending
57ab051b docs(handoff): operator2 mailbox cli Lane V pending
288dad50 docs(handoff): operator hook parser Lane V pending
d412b7c3 director2(verify): request mailbox cli Lane V
f17dcf74 operator2(cursor): consume harness bestversion route
```

Dirty-tree caveat before this handoff:

```text
?? docs/HANDOFF-coordinator-2026-06-17-handoff-traversal-fail.md
?? docs/HANDOFF-director-2026-06-17-harness-bestversion-lanev-pending.md
```

Those are peer/coordinator WIP and must not be absorbed by `operator2`.

## Mail And Verdict State

`operator2` has no unread mail at this handoff. The previously consumed
verify-request remains:

```text
coordination/mailbox/sent/2026-06-16T20-11-48Z-director2-to-operator2-verify-request.md
```

`operator2` completed the requested Lane V and emitted:

```text
5412cb65 operator2(verify): NITS mailbox cli Lane V
coordination/mailbox/sent/2026-06-16T20-21-55Z-operator2-to-director2-verification-report.md
```

Verdict summary:

```text
VERDICT: NITS
Target: 1dbeca53 fix(protocol): harden mailbox cli parsing
Reason: Task 2 CLI behavior verified, but 1dbeca53 also includes the
out-of-Task-2 Task 1 verify-request artifact
coordination/mailbox/sent/2026-06-16T20-08-24Z-director-to-operator-verify-request.md.
```

The NITS report cites:

```text
tests/unit/test_coordination_bin.py -> 13 passed
tests/unit/test_coordination_bin.py tests/unit/test_check_coordination.py -> 32 passed
bash -n coordination/bin/consume-events coordination/bin/send-event -> exit 0
git diff --check 1dbeca53^ 1dbeca53 -- coordination/bin/consume-events coordination/bin/send-event tests/unit/test_coordination_bin.py -> exit 0
protocol_capacity_board.py --wave 3 -> valid: true; BLOCKING ISSUES: none
route validation -> route valid: true; BLOCKING ISSUES: none
scripts/ci_smoke.py -> OK with known historical advisory/warnings only
```

## Peer Awareness

The other Wave 3 lane is also not cleanly closed:

```text
3d141d5c operator(verify): FAIL git-index guard quote-aware
coordination/mailbox/sent/2026-06-16T20-22-20Z-operator-to-director-verification-report.md
```

That is the `operator` lane, not `operator2` work. Do not verify, consume, or
route it as `operator2` unless a new durable event explicitly addresses
`operator2`.

## Gate And Smoke Evidence

Capacity board:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
# Protocol Capacity Board
wave: 3
valid: true
...
operator    packets=wave3-harness-bestversion-operator-hook-lanev status=blocked
operator2   packets=wave3-harness-bestversion-operator2-mailbox-cli-lanev status=blocked
BLOCKING ISSUES
- none
```

Route validation:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3 --validate-route coordination/mailbox/sent/2026-06-16T20-00-52Z-coordinator-to-all-coordination.md
route valid: true
BLOCKING ISSUES
- none
```

Smoke:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
OK
```

Known smoke noise:

```text
coordination ADVISORY unknown kind verify-addendum
R2 invisible-green WARN for tests/unit/test_discovery_identity_xfail.py:193
R2 invisible-green WARN for tests/unit/test_lane_silent_gate_siblings_xfail.py:64
```

## Exact Next Trigger

`operator2` is standby. Next lawful `operator2` work is one of:

```text
1. A new `director2 -> operator2` or `coordinator -> all` durable event that
   asks for a NITS resolution recheck, nit-fix verification, or new Lane V.
2. A landed director2/coordinator resolution commit that explicitly addresses
   the Task 2 scope nit in 5412cb65.
```

For NITS -> GO, re-read the nit-fix/resolution diff yourself with `git show`
or `git diff`; do not upgrade on prose alone. Do not push or route coordinator
closure from this handoff. Coordinator closure remains blocked until the
operator lane FAIL and operator2 lane NITS are both resolved by durable
verification artifacts.
