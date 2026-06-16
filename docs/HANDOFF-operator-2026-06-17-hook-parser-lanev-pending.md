# Handoff - operator - 2026-06-17 hook parser Lane V pending

READ FIRST AS `operator`. Trust current git, mailbox bodies, and live gate
evidence over this prose if they diverge.

Generated: `2026-06-16T20:13:25Z` (`2026-06-17T05:13:25+0900`)
Seat: `operator`
Repo: `/Users/hyungkoookkim/Content`

## Refresh First

```bash
env -u GIT_INDEX_FILE .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 3
env -u GIT_INDEX_FILE git log --oneline -8
env -u GIT_INDEX_FILE git status --short
sed -n '1,280p' coordination/mailbox/sent/2026-06-16T20-08-24Z-director-to-operator-verify-request.md
```

Use `env -u GIT_INDEX_FILE` for ordinary git/pytest commands. Push, lock
claim/release, pod/API spend, dependency edits, production generation, and
inventory transitions remain user-gated.

## Current Durable State

Latest committed HEAD at handoff:

```text
d412b7c3 director2(verify): request mailbox cli Lane V
f17dcf74 operator2(cursor): consume harness bestversion route
1dbeca53 fix(protocol): harden mailbox cli parsing
14525ee4 fix(codex): make git-index guard quote-aware
552960b6 operator(cursor): consume harness bestversion route
d99df6f6 coord(route): close handoff traversal and route harness tasks
bd9bdf20 coord(cursor): director consume handoff traversal GO
667556fa docs(handoff): operator handoff traversal GO standby
```

Branch state from `seat_status.py operator --wave 3`:

```text
main...origin/main [ahead 22, behind 0]
```

Operator mailbox:

```text
operator cursor: 2026-06-16T20:00:52Z
operator UNREAD: 1
unread event: coordination/mailbox/sent/2026-06-16T20-08-24Z-director-to-operator-verify-request.md
```

The unread event is intentionally not consumed by this handoff. It is the real
Lane V trigger for the next operator turn.

Dirty tree caveat at handoff:

```text
 M coordination/mailbox/seen/operator2.txt
?? docs/HANDOFF-coordinator-2026-06-17-handoff-traversal-fail.md
```

Those are not operator-owned for this handoff. Do not absorb, stage, delete, or
commit them from the operator Lane V unless fresh evidence proves they became
part of the operator-owned scope.

## Active Route And Mail

Coordinator route:

```text
coordination/mailbox/sent/2026-06-16T20-00-52Z-coordinator-to-all-coordination.md
```

The route closed the handoff-traversal cycle and opened the Wave 3 harness
best-version task board:

- `director`: Task 1 hook-parser implementation.
- `operator`: Lane V on the Task 1 hook-parser commit after director verify-request.
- `director2`: Task 2 mailbox CLI implementation.
- `operator2`: Lane V on Task 2 after director2 verify-request.

Operator's unread verify-request:

```text
coordination/mailbox/sent/2026-06-16T20-08-24Z-director-to-operator-verify-request.md
target: 14525ee4 fix(codex): make git-index guard quote-aware
```

Scope named by director:

- `.codex/hooks/guard-git-index.sh`
- `tests/unit/test_codex_guard_git_index.py`
- `coordination/mailbox/seen/director.txt` only as director route consumption.

Behavior to verify:

- quoted shell metacharacters inside an `rg` pattern, for example
  `rg -n 'git|pytest|GIT_INDEX_FILE' ...`, are not treated as top-level shell
  pipes;
- bare pytest remains blocked under a seat `GIT_INDEX_FILE`;
- bare mutating git, such as `git add`, remains blocked under a seat
  `GIT_INDEX_FILE`;
- `env -u GIT_INDEX_FILE git add ...` remains allowed.

No cross-cutting lock applies: the target diff does not touch
`auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`.

## Fresh Evidence At Handoff

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 3
-> Wave 3 gate: MET counts={'verified': 3}; PRODUCT ORACLE: logs/product-oracle-wave3.json

env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
-> valid: true; operator packet wave3-harness-bestversion-operator-hook-lanev status=blocked; BLOCKING ISSUES - none

env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once
-> generated_at 2026-06-16T20:13:15Z; operator unread=1 latest=2026-06-16T20-08-24Z-director-to-operator-verify-request.md; operator2 unread=0; coordinator broadcast receipt split consumed=4 unread=0 unknown=0

env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; known historical verify-addendum advisory and R2 invisible-green warnings only
```

Non-repo memory maintenance immediately before this handoff:

```text
/Users/hyungkoookkim/.codex/memories/extensions/ad_hoc/notes/2026-06-16T20-09-49Z-proven-memory-prune.md
```

That note requested proven-only memory pruning. `MEMORY.md` itself was not
edited directly.

## Exact Next Trigger

Use `continue as operator` to run independent Lane V on `14525ee4`.

Recommended next operator steps:

1. Refresh `seat_status.py operator --wave 3`, `git log --oneline -8`, and
   `git status --short`.
2. Read the unread verify-request body above.
3. Intentionally consume operator mail only after reading the body.
4. Read the actual target diff with:
   `env -u GIT_INDEX_FILE git show --no-ext-diff --unified=80 14525ee4 -- .codex/hooks/guard-git-index.sh tests/unit/test_codex_guard_git_index.py coordination/mailbox/seen/director.txt`.
5. Run focused verification for `tests/unit/test_codex_guard_git_index.py` and
   any mutation/non-vacuity probe needed to prove the quote-aware parser guard
   is load-bearing.
6. Emit a mailbox `verification-report` with GO, NITS, or FAIL for `14525ee4`
   only.

Do not verify `1dbeca53`; that is operator2's Lane V lane. Do not push, claim
or release locks, spend API/pod budget, edit dependencies, generate production
artifacts, or transition inventory from this handoff alone.
