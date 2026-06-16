# Handoff - director - 2026-06-17 env-u repair Lane V pending

READ FIRST AS `director`. Current git, mailbox bodies, and live gate evidence
override this prose if they diverge.

Generated: `2026-06-16T20:39:55Z` (`2026-06-17T05:39:55+0900`)
Seat: `director`
Repo: `/Users/hyungkoookkim/Content`

## Refresh First

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 3
env -u GIT_INDEX_FILE git log --oneline -8
env -u GIT_INDEX_FILE git status --short --branch
.venv/bin/python scripts/mailbox_monitor.py --once
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3 --validate-route coordination/mailbox/sent/2026-06-16T20-28-41Z-coordinator-to-all-coordination.md
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Use `env -u GIT_INDEX_FILE` for ordinary git/pytest. Push, lock side effects,
pod/API spend, dependency edits, production generation, and inventory
transitions remain user-gated.

## Current Durable State

HEAD at handoff refresh:

```text
551b9b56 operator2(verify): GO mailbox cli NITS resolution
4632359e docs(handoff): director2 standby after env-u route
80ed3704 coord(director): request env-u repair Lane V
421fc358 fix(codex): block env-u segment bypass
2d98f279 docs(handoff): operator2 NITS reread pending
79ebaf4a docs(handoff): operator hook repair standby
281170aa coord(route): reroute harness bestversion repairs
a76908da docs(handoff): director2 standby after route
```

Branch state:

```text
main...origin/main [ahead 40]
```

Director mailbox at refresh:

```text
cursor: 2026-06-16T20:28:41Z
UNREAD: 0
```

Mailbox monitor at refresh:

```text
generated_at: 2026-06-16T20:39:55Z
latest coordinator broadcast: 2026-06-16T20-28-41Z-coordinator-to-all-coordination.md
receipt split: consumed=4 unread=0 unknown=0
director unread=0 cursor=2026-06-16T20:28:41Z
director2 unread=0 cursor=2026-06-16T20:38:53Z
operator unread=0 cursor=2026-06-16T20:34:59Z
operator2 unread=0 cursor=2026-06-16T20:28:41Z
ALERTS: none
```

## What Director Did

Director consumed the Wave 3 repair route:

```text
coordination/mailbox/sent/2026-06-16T20-28-41Z-coordinator-to-all-coordination.md
coordination/mailbox/seen/director.txt -> 2026-06-16T20:28:41Z
```

Director repaired Task 1:

```text
421fc358 fix(codex): block env-u segment bypass
```

Scope:

```text
.codex/hooks/guard-git-index.sh
tests/unit/test_codex_guard_git_index.py
coordination/mailbox/seen/director.txt  # route-consumption cursor only
```

Behavior now covered:

- `env -u GIT_INDEX_FILE` is safe only for the shell segment it prefixes;
- a safe first segment cannot mask a later bare mutating git segment after `;`,
  `&`, or `|&`;
- quoted shell metacharacters inside an `rg` pattern, such as
  `rg -n 'git|pytest|GIT_INDEX_FILE' ...`, are not treated as top-level shell
  pipes;
- bare pytest and bare mutating git remain blocked under a seat
  `GIT_INDEX_FILE`;
- `env -u GIT_INDEX_FILE git add ...` remains allowed.

No cross-cutting lock applies: the diff did not touch `auto_approve.py`,
`cinema/context.py`, `core.py`, or `web_server.py`.

Director sent the fresh verify-request:

```text
80ed3704 coord(director): request env-u repair Lane V
coordination/mailbox/sent/2026-06-16T20-34-59Z-director-to-operator-verify-request.md
target: 421fc358 fix(codex): block env-u segment bypass
```

At refresh, `operator` has consumed that verify-request:

```text
operator cursor: 2026-06-16T20:34:59Z
operator unread: 0
```

No `operator -> director` Lane V verdict for `421fc358` was durable at this
handoff refresh.

## Verification Evidence

Director-side evidence, not operator GO:

```text
RED:
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py -q
-> 3 failed, 4 passed; the three env-u segment cases returned 0 instead of
   blocking the later `git add`.

GREEN:
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py -q
-> 7 passed in 0.18s

RUNXFAIL:
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py --runxfail -q
-> 7 passed in 0.18s
```

Route / gate / smoke refresh:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
-> valid: true
-> coordinator status=active
-> director status=active
-> director2 status=blocked
-> operator status=blocked
-> operator2 status=active
-> BLOCKING ISSUES - none

env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3 --validate-route coordination/mailbox/sent/2026-06-16T20-28-41Z-coordinator-to-all-coordination.md
-> route valid: true
-> BLOCKING ISSUES - none

env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 3
-> Wave 3 gate: MET counts={'verified': 3}
-> PRODUCT ORACLE: logs/product-oracle-wave3.json

env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK
-> known historical verify-addendum advisory and R2 invisible-green warnings only
```

Do not treat Wave 3 gate state alone as protocol closure. The harness
best-version route remains open until the Pair-A operator Lane V verdict for
`421fc358` lands and coordinator closes or reroutes the cycle.

## Peer State

Pair-B Task 2 NITS resolution is now durable GO:

```text
551b9b56 operator2(verify): GO mailbox cli NITS resolution
coordination/mailbox/sent/2026-06-16T20-38-53Z-operator2-to-director2-verification-report.md
VERDICT: GO
```

Latest peer handoffs observed:

```text
docs/HANDOFF-director2-2026-06-17-standby-after-envu-repair-route.md
docs/HANDOFF-operator-2026-06-17-hook-env-bypass-fail-standby.md
docs/HANDOFF-operator2-2026-06-17-nits-resolution-reread-pending.md
```

The operator handoff predates `80ed3704`; trust mailbox cursor/body state over
that stale operator handoff. Operator has consumed the `421fc358`
verify-request but has not yet landed a verdict.

## Dirty / Staged Caveats

Dirty shared-tree state at refresh:

```text
 M coordination/mailbox/seen/director2.txt
 M coordination/mailbox/seen/operator.txt
?? docs/HANDOFF-coordinator-2026-06-17-handoff-traversal-fail.md
```

These are not director-owned for this handoff. Preserve them unless operating
as `director2`, `operator`, or `coordinator`. This director handoff should
commit only:

```text
docs/HANDOFF-director-2026-06-17-envu-repair-lanev-pending.md
```

## Exact Next Trigger

```text
continue as operator
```

Operator should finish independent Lane V on `421fc358` using
`coordination/mailbox/sent/2026-06-16T20-34-59Z-director-to-operator-verify-request.md`,
then emit a durable `operator -> director` GO, NITS, or FAIL.

After the Pair-A operator verdict lands, use:

```text
continue as coordinator
```

Coordinator can then reconcile Pair-A verdict plus Pair-B GO and either close
the Wave 3 harness best-version cycle or route any remaining NITS/FAIL.
