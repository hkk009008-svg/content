# HANDOFF - Operator-1 (Pair-A), 2026-06-15 - Codex launch idle, stale seat index warning

READ FIRST AS operator-1. Trust git and mailbox artifacts over this prose if
they diverge.

This handoff wraps a short live Codex operator orientation. Operator-1 did not
author production code, did not run Lane V, did not release a lock, and did not
emit a verification-report because no Pair-A shipping diff, NITS reread, or
verify-request was pending.

## State At Stop

- Seat marker requested by launch: `CODEX_SEAT=operator`.
- Seat index requested by launch: `.git/index-codex-operator`.
- Do not use `.git/index-codex-operator` for commits until it is explicitly
  refreshed or inspected. It existed before this handoff and its cached status
  showed large stale staged deletions unrelated to this operator wrap.
- Use `env -u GIT_INDEX_FILE` for git/pytest evidence unless intentionally
  maintaining the per-seat index.
- No push performed. Push remains user-gated.

Recent git evidence:

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
cefd2971 docs(handoff): director subagent workflow wrap
72a2d83c docs(handoff): operator consume director wrap
04912467 docs(handoff): operator consume late statuses
afb483d4 docs(handoff): operator2 lipsync costkey idle
f721c989 docs(handoff): operator multi-subagent idle
```

Fresh operator orientation:

```text
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2
branch main
cefd2971  docs(handoff): director subagent workflow wrap
vs origin/main: 99 ahead, 0 behind
cursor: 2026-06-15T12:10:22Z
UNREAD: 0
Wave 2 gate: UNMET counts={'verified': 17, 'open': 13}
BLOCKER [MAJOR/open] spent-usd-reset-on-resume ... no executable xfail-pin selector
BLOCKER [MAJOR/open] perf-phase-no-gate ... no executable xfail-pin selector
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact ...
PYTEST: 15 failed, 46 passed
```

## Mailbox Status

No pre-existing unread operator mail was present at launch. For cross-seat
visibility this handoff sent one lightweight status event:

- `coordination/mailbox/sent/2026-06-15T12-26-29Z-operator-to-all-status.md`

The operator cursor was then advanced through that self-broadcast:

```text
$ env -u GIT_INDEX_FILE coordination/bin/consume-events operator
cursor operator: 2026-06-15T12:10:22Z -> 2026-06-15T12:26:29Z; unread now: 0 (staged; fold into your next substantive commit)
```

One late all-seat status event landed before commit and was consumed into this
handoff:

- `coordination/mailbox/sent/2026-06-15T12-26-43Z-director2-to-all-status.md`
  - Pair-B/director2 handoff; no production code edited by that pass; Wave 2
    still unmet; Pair-B priority remains `download-urllib-notimeout`; no
    Pair-A/operator Lane V or lock action created.

```text
$ env -u GIT_INDEX_FILE coordination/bin/consume-events operator
cursor operator: 2026-06-15T12:26:29Z -> 2026-06-15T12:26:43Z; unread now: 0 (staged; fold into your next substantive commit)
```

One more late all-seat status event landed during the final freshness check and
was also consumed:

- `coordination/mailbox/sent/2026-06-15T12-28-00Z-operator2-to-all-status.md`
  - operator2 handoff; no Lane V, NITS reread, or operator2 verification task
    owed; Wave 2 still unmet; no Pair-A/operator action created.

```text
$ env -u GIT_INDEX_FILE coordination/bin/consume-events operator
cursor operator: 2026-06-15T12:26:43Z -> 2026-06-15T12:28:00Z; unread now: 0 (staged; fold into your next substantive commit)
```

## Phase Read

No Pair-A/operator action is currently owed.

- Latest HEAD commits are `docs(handoff)` / `coord(...)` style, not a new
  Pair-A `fix`, `feat`, or `refactor` commit.
- No operator unread mail existed at orientation.
- The only durable event this session produced is a status handoff, not a
  verification-report.
- Wave 2 remains unmet, but `scripts/wave_gate_check.py` / seat status is
  process state, not a correctness proof.

Stay idle unless one of these fires:

1. Pair-A director lands a new Pair-A shipping commit and sends or implies a
   verify request.
2. Coordinator routes a Pair-A NITS/FAIL reread or Tier-A co-sign request.
3. A new product-oracle artifact lands and explicitly needs Pair-A identity /
   ArcFace semantic review.

## Stale Seat Index Evidence

The per-seat index exists but is not safe as the active write index without
cleanup. Evidence from this session:

```text
$ CODEX_SEAT=operator GIT_INDEX_FILE=/Users/hyungkoookkim/Content/.git/index-codex-operator git diff --cached --stat --
134 files changed, 324 insertions(+), 9292 deletions(-)
```

The cached path list included staged deletions of Codex protocol files, seat
skills, handoff docs, mailbox events, and tests. This handoff intentionally uses
the normal index with explicit pathspecs instead of that stale seat index.

## Verification

No full smoke was rerun during this tiny wrap. Session-start smoke had already
been reported OK by the Codex hook/developer context before this handoff work.
The fresh read-only seat-status command above executed the Wave 2 selector set
and reported the existing expected red gate:

```text
15 failed, 46 passed in 2.54s
```

No production files were edited by operator-1 in this handoff.
