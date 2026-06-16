# Handoff - director - 2026-06-17 harness best-version Lane V pending

READ FIRST AS `director`. Current git, mailbox bodies, and live gate evidence
override this prose if they diverge.

Generated: `2026-06-16T20:24:55Z` (`2026-06-17T05:24:55+0900`)
Seat: `director`
Repo: `/Users/hyungkoookkim/Content`

## Refresh First

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 3
env -u GIT_INDEX_FILE git log --oneline -12
env -u GIT_INDEX_FILE git status --short --branch
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3 --validate-route coordination/mailbox/sent/2026-06-16T20-00-52Z-coordinator-to-all-coordination.md
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Use `env -u GIT_INDEX_FILE` for ordinary git/pytest commands. Push, lock
claim/release, pod/API spend, dependency edits, production generation, and
inventory transitions remain user-gated.

## Current Durable State

Latest committed HEAD while writing this handoff:

```text
9c9b1fac docs(handoff): operator2 mailbox cli NITS standby
3d141d5c operator(verify): FAIL git-index guard quote-aware
5412cb65 operator2(verify): NITS mailbox cli Lane V
00fc17fc docs(handoff): coordinator harness lanev pending
ad17317b docs(handoff): director2 mailbox cli Lane V pending
57ab051b docs(handoff): operator2 mailbox cli Lane V pending
288dad50 docs(handoff): operator hook parser Lane V pending
d412b7c3 director2(verify): request mailbox cli Lane V
f17dcf74 operator2(cursor): consume harness bestversion route
1dbeca53 fix(protocol): harden mailbox cli parsing
14525ee4 fix(codex): make git-index guard quote-aware
552960b6 operator(cursor): consume harness bestversion route
d99df6f6 coord(route): close handoff traversal and route harness tasks
bd9bdf20 coord(cursor): director consume handoff traversal GO
667556fa docs(handoff): operator handoff traversal GO standby
eacdbc47 operator(verify): GO handoff traversal evidence gate
```

Branch state:

```text
main...origin/main [ahead 29, behind 0]
```

Director mailbox at refresh:

```text
cursor: 2026-06-16T20:22:20Z
UNREAD: 0
```

Mailbox monitor at refresh:

```text
generated_at: 2026-06-16T20:24:55Z
latest coordinator broadcast: 2026-06-16T20-00-52Z-coordinator-to-all-coordination.md
receipt split: consumed=4 unread=0 unknown=0
director unread=0 cursor=2026-06-16T20:22:20Z
director2 unread=0 cursor=2026-06-16T20:21:55Z
operator unread=0 cursor=2026-06-16T20:08:24Z
operator2 unread=0 cursor=2026-06-16T20:11:48Z
```

## What Director Did

Director consumed the committed coordinator route:

```text
coordination/mailbox/sent/2026-06-16T20-00-52Z-coordinator-to-all-coordination.md
```

Director implemented Wave 3 harness best-version Task 1:

```text
14525ee4 fix(codex): make git-index guard quote-aware
```

Scope:

```text
.codex/hooks/guard-git-index.sh
tests/unit/test_codex_guard_git_index.py
coordination/mailbox/seen/director.txt  # route-consumption cursor only
```

Behavior:

- quoted shell metacharacters inside an `rg` pattern, for example
  `rg -n 'git|pytest|GIT_INDEX_FILE' ...`, are not treated as top-level shell
  pipes;
- bare pytest remains blocked under a seat `GIT_INDEX_FILE`;
- bare mutating git, such as `git add`, remains blocked under a seat
  `GIT_INDEX_FILE`;
- `env -u GIT_INDEX_FILE git add ...` remains allowed.

Director sent the required verify-request to `operator`:

```text
coordination/mailbox/sent/2026-06-16T20-08-24Z-director-to-operator-verify-request.md
target: 14525ee4 fix(codex): make git-index guard quote-aware
```

Important scope caveat: the verify-request artifact was accidentally committed
inside `1dbeca53 fix(protocol): harden mailbox cli parsing` during a concurrent
shared-index race. It is still durable and addressed to `operator`; operator
status now shows unread `0`, so the body has been consumed by that seat.

No cross-cutting lock applies: Task 1 did not touch `auto_approve.py`,
`cinema/context.py`, `core.py`, or `web_server.py`.

## Operator Verdict Consumed

Director read and consumed the committed operator report:

```text
3d141d5c operator(verify): FAIL git-index guard quote-aware
coordination/mailbox/sent/2026-06-16T20-22-20Z-operator-to-director-verification-report.md
VERDICT: FAIL for 14525ee4
coordination/mailbox/seen/director.txt -> 2026-06-16T20:22:20Z
```

Binding finding:

```text
.codex/hooks/guard-git-index.sh exits early when the raw command string
contains `env -u GIT_INDEX_FILE` anywhere, before segment parsing. A safe first
segment can mask a later unsafe bare mutating segment:
`env -u GIT_INDEX_FILE git status; git add scripts/protocol_capacity.py`
returns 0 instead of blocking.
```

Operator added a strict xfail pin in `tests/unit/test_codex_guard_git_index.py`
for the deferred bypass:

```text
test_env_u_prefix_only_allows_its_own_segment
normal focused run: 4 passed, 1 xfailed
--runxfail: fails on the correct assertion
```

Director has not repaired this FAIL yet.

## Verification Evidence

Director-side TDD evidence, not operator GO:

```text
RED:
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py -q
-> F...; failing test test_quoted_pipe_regex_does_not_look_like_shell_pipe;
   hook returned 2 with offending segment `pytest` from inside the quoted rg pattern.

GREEN:
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py -q
-> 4 passed in 0.15s on current HEAD
```

Gate/capacity/smoke refresh while writing this handoff:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
-> valid: true
-> coordinator status=active
-> director status=active
-> director2 status=active
-> operator status=blocked
-> operator2 status=blocked
-> BLOCKING ISSUES - none

env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3 --validate-route coordination/mailbox/sent/2026-06-16T20-00-52Z-coordinator-to-all-coordination.md
-> route valid: true
-> BLOCKING ISSUES - none

env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK
-> known historical verify-addendum advisory and R2 invisible-green warnings only
```

Wave 3 gate from `seat_status.py director --wave 3`:

```text
Wave 3 gate: MET counts={'verified': 3}
PRODUCT ORACLE: logs/product-oracle-wave3.json
```

Do not treat Wave 3 gate state alone as protocol closure. The harness
best-version route remains open until operator and operator2 Lane V are
resolved and coordinator closes the cycle.

## Current Peer State

Operator latest handoff:

```text
docs/HANDOFF-operator-2026-06-17-hook-parser-lanev-pending.md
```

Operator status at refresh:

```text
HEAD 3d141d5c
operator cursor 2026-06-16T20:08:24Z
operator unread 0
```

Operator2 latest handoff:

```text
docs/HANDOFF-operator2-2026-06-17-mailbox-cli-lanev-pending.md
```

Operator2 status at refresh:

```text
HEAD 9c9b1fac
operator2 cursor 2026-06-16T20:11:48Z
operator2 unread 0
```

Director2 latest handoff:

```text
docs/HANDOFF-director2-2026-06-17-mailbox-cli-lanev-pending.md
```

## Dirty / Staged Caveats

Dirty shared-tree state at handoff refresh:

```text
M  coordination/mailbox/seen/director.txt
 M coordination/mailbox/seen/director2.txt
?? coordination/mailbox/sent/2026-06-16T20-25-32Z-director2-to-operator2-coordination.md
?? docs/HANDOFF-coordinator-2026-06-17-handoff-traversal-fail.md
?? docs/HANDOFF-director2-2026-06-17-mailbox-cli-nits-response.md
```

`coordination/mailbox/seen/director.txt` is director-owned and should be folded
into this handoff commit. The director2 cursor and coordinator handoff WIP are
not director-owned; preserve them unless acting as the owning seat or
coordinator. This director handoff should commit only:

```text
coordination/mailbox/seen/director.txt
docs/HANDOFF-director-2026-06-17-harness-bestversion-lanev-pending.md
```

Task 2 peer-lane caveat:

```text
9c9b1fac docs(handoff): operator2 mailbox cli NITS standby
5412cb65 operator2(verify): NITS mailbox cli Lane V
coordination/mailbox/sent/2026-06-16T20-21-55Z-operator2-to-director2-verification-report.md
```

That report is committed and addressed to `director2`, not `director`.
Director2/coordinator need to resolve the Task 2 process nit before clean route
closure.

## Exact Next Trigger

Primary next protocol action:

```text
continue as director
```

Director should repair the committed operator FAIL for `14525ee4` using:

```text
coordination/mailbox/sent/2026-06-16T20-22-20Z-operator-to-director-verification-report.md
```

The repair should address the raw `env -u GIT_INDEX_FILE` substring bypass and
preferably fold the `&` / `|&` parser gaps if in scope. After repair, send a
fresh `director -> operator` verify-request naming the exact commit.

Peer-lane next action:

```text
continue as director2
```

Director2/coordinator should resolve the committed Task 2 NITS from:

```text
coordination/mailbox/sent/2026-06-16T20-21-55Z-operator2-to-director2-verification-report.md
```

Coordinator should reconcile/close only after both operator verdicts land.

No push, lock claim/release, pod/API spend, dependency edit, production
generation, or inventory transition is authorized by this handoff.
