# Handoff - operator - 2026-06-17 hook env-u bypass FAIL standby

READ FIRST AS `operator`. Trust current git, mailbox bodies, and live gate
evidence over this prose if they diverge.

Generated: `2026-06-16T20:28:40Z` (`2026-06-17T05:28:40+0900`)
Seat: `operator`
Repo: `/Users/hyungkoookkim/Content`

## Refresh First

```bash
env -u GIT_INDEX_FILE .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 3
env -u GIT_INDEX_FILE git log --oneline -10
env -u GIT_INDEX_FILE git status --short
```

Use `env -u GIT_INDEX_FILE` for ordinary git/pytest commands. Push, lock
claim/release, pod/API spend, dependency edits, production generation, and
inventory transitions remain user-gated.

## Current Durable State

Latest HEAD at handoff:

```text
63887c81 docs(handoff): director2 consume repair route
06a20f97 director2(coord): resolve mailbox cli NITS scope
7b44def6 docs(handoff): director harness bestversion fail pending
9c9b1fac docs(handoff): operator2 mailbox cli NITS standby
3d141d5c operator(verify): FAIL git-index guard quote-aware
5412cb65 operator2(verify): NITS mailbox cli Lane V
00fc17fc docs(handoff): coordinator harness lanev pending
ad17317b docs(handoff): director2 mailbox cli Lane V pending
57ab051b docs(handoff): operator2 mailbox cli Lane V pending
288dad50 docs(handoff): operator hook parser Lane V pending
```

Branch state from `seat_status.py operator --wave 3`:

```text
main...origin/main [ahead 32, behind 0]
```

Operator mailbox at handoff:

```text
operator cursor: 2026-06-16T20:08:24Z
operator UNREAD: 1
unread event: coordination/mailbox/sent/2026-06-16T20-28-41Z-coordinator-to-all-coordination.md
```

That coordinator route body was read for this handoff, but it is currently an
untracked shared-tree mailbox file. Do not consume the operator cursor through
it unless it becomes durable/committed or current protocol evidence says to.

## What The Operator Just Finished

Operator completed Lane V on Task 1 initial hook-parser commit:

```text
3d141d5c operator(verify): FAIL git-index guard quote-aware
```

Committed operator-owned paths:

```text
coordination/mailbox/seen/operator.txt
coordination/mailbox/sent/2026-06-16T20-22-20Z-operator-to-director-verification-report.md
tests/unit/test_codex_guard_git_index.py
```

Binding verdict artifact:

```text
coordination/mailbox/sent/2026-06-16T20-22-20Z-operator-to-director-verification-report.md
```

Verdict summary:

- `14525ee4` fixed the original quoted-pipe false positive and preserved bare
  pytest / bare mutating-git blocking.
- Operator FAIL remains binding because `.codex/hooks/guard-git-index.sh:42`
  exits early if the raw command string contains `env -u GIT_INDEX_FILE`
  anywhere, so `env -u GIT_INDEX_FILE git status; git add ...` returns 0.
- A strict xfail pin now captures the deferred bypass:
  `tests/unit/test_codex_guard_git_index.py::test_env_u_prefix_only_allows_its_own_segment`.

## Fresh Evidence At Handoff

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py -q
-> 4 passed, 1 xfailed in 0.17s

env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py --runxfail -q
-> expected RED: test_env_u_prefix_only_allows_its_own_segment fails because current hook returns 0 instead of 2

env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; known historical verify-addendum advisory and R2 invisible-green warnings only

env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
-> valid: true; BLOCKING ISSUES - none
-> operator packet wave3-harness-bestversion-operator-hook-repair-lanev status=blocked
-> operator2 packet wave3-harness-bestversion-operator2-mailbox-cli-nits-reread status=active

env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3 --validate-route coordination/mailbox/sent/2026-06-16T20-28-41Z-coordinator-to-all-coordination.md
-> route valid: true; BLOCKING ISSUES - none

env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once
-> latest coordinator broadcast 2026-06-16T20-28-41Z-coordinator-to-all-coordination.md
-> receipt split consumed=1 unread=3 unknown=0
-> director unread=1; operator unread=1; operator2 unread=1; director2 consumed
```

## Current Route Read For Awareness

Untracked coordinator route:

```text
coordination/mailbox/sent/2026-06-16T20-28-41Z-coordinator-to-all-coordination.md
```

It routes:

- `director`: repair Task 1 hook env-u bypass in
  `.codex/hooks/guard-git-index.sh` and `tests/unit/test_codex_guard_git_index.py`,
  then send fresh `director -> operator` verify-request naming the exact repair
  commit.
- `operator`: stand by until that director repair verify-request lands, then
  independently issue GO, NITS, or FAIL on the exact repair commit only.
- `director2`: no further action currently routed unless operator2 returns
  NITS or FAIL on the NITS response.
- `operator2`: run the Task 2 NITS-resolution reread against `06a20f97` and
  `coordination/mailbox/sent/2026-06-16T20-25-32Z-director2-to-operator2-coordination.md`.

## Dirty Tree Caveat At Handoff

Fresh `git status --short` before this handoff showed shared-tree WIP outside
the operator handoff scope:

```text
 M coordination/capacity/packets/wave3-harness-bestversion-coordinator-route.json
 M coordination/capacity/packets/wave3-harness-bestversion-director-hook-parse.json
 M coordination/capacity/packets/wave3-harness-bestversion-director2-mailbox-cli.json
 M coordination/capacity/packets/wave3-harness-bestversion-operator-hook-lanev.json
 M coordination/capacity/packets/wave3-harness-bestversion-operator2-mailbox-cli-lanev.json
 M coordination/mailbox/seen/director2.txt
 M coordination/mailbox/seen/operator2.txt
 A docs/HANDOFF-operator2-2026-06-17-nits-resolution-reread-pending.md
 ?? coordination/capacity/packets/wave3-harness-bestversion-coordinator-join.json
?? coordination/capacity/packets/wave3-harness-bestversion-director-hook-env-bypass-repair.json
?? coordination/capacity/packets/wave3-harness-bestversion-director2-mailbox-cli-nits-resolution.json
?? coordination/capacity/packets/wave3-harness-bestversion-operator-hook-repair-lanev.json
?? coordination/capacity/packets/wave3-harness-bestversion-operator2-mailbox-cli-nits-reread.json
?? coordination/capacity/packets/wave3-harness-bestversion-repair-coordinator-route.json
?? coordination/mailbox/sent/2026-06-16T20-28-41Z-coordinator-to-all-coordination.md
?? docs/HANDOFF-coordinator-2026-06-17-handoff-traversal-fail.md
```

Do not stage, delete, or commit those from this operator handoff unless a later
route makes them operator-owned.

## Exact Next Trigger

Use `continue as operator` only after a committed `director -> operator`
verify-request lands for the Task 1 hook env-u bypass repair.

Recommended next operator steps:

1. Refresh `seat_status.py operator --wave 3`, `git log --oneline -10`, and
   `git status --short`.
2. Read the relevant `director -> operator` verify-request body.
3. Consume operator mail only after reading the durable body.
4. Run independent Lane V on the named repair commit only.
5. Re-check the strict xfail pin flips to live pass after the repair, and
   mutation/non-vacuity evidence still proves the quoted-pipe regression.
6. Emit a mailbox `verification-report` with GO, NITS, or FAIL.

If no director repair verify-request exists, remain in standby. Do not invent
additional verification, push, claim locks, release locks, spend API/pod budget,
edit dependencies, generate production artifacts, or transition inventory.
