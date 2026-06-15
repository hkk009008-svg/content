# Director Handoff — Codex Protocol Codified

**When:** 2026-06-15T19:17:17Z / 2026-06-16T04:17:17+0900  
**Seat:** director  
**HEAD:** `4d077c9c coord(protocol): document codex mailbox index guard`

## Summary

User requested protocol rules be turned into codified state. That is now
durable in git:

- `ab8beb4c coord(protocol): codify codex live rules`
- `fa11b793 coord(protocol): clarify mail consumption rule`
- `4d077c9c coord(protocol): document codex mailbox index guard`

The codified rules cover live-seat mailbox-first behavior, coordinator
all-scope read/no cursor, Codex seat-index HEAD-drift/staged-scope guard,
coordinator task-board receipt checks, no-lock routing while push/spend is not
authorized, narrow `handoff`, and durable protocol-learning capture.

## Current Seat State

Director mail has been read/consumed. Current director cursor:
`2026-06-15T18:58:49Z`; unread: `0`.

Current board from live seat-status:

| seat | unread | state |
|---|---:|---|
| director | 0 | active standby after protocol codification |
| director2 | 0 | routed to Pair-B checkpoint cluster work by coordinator task board |
| operator | 3 | should consume/read `18:42:44`, `18:45:12`, `18:58:49` events before any Pair-A decision |
| operator2 | 0 | standby for director2 checkpoint Lane V |

All peer heartbeats were online on the final refresh.

## Wave Gate

Wave 2 remains **UNMET**:

- counts: `{'verified': 20, 'open': 10}`
- blocker: missing committed `logs/product-oracle-*.json` artifact with
  `artifact_kind=product-oracle`, `wave=2`, finite `arcface.arc_score`, and
  finite `lipsync.offset_frames`
- pytest tail is still unrelated open clusters, including
  `test_postprocess_audio_siblings_xfail.py`,
  `test_discovery_web_server_xfail.py`, and
  `test_discovery_checkpoint_xfail.py`

No push, paid API/pod spend, or lock claim is authorized by this handoff.

## Evidence

```text
$ CODEX_SEAT=director GIT_INDEX_FILE=.git/index-codex-director .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2
HEAD 4d077c9c coord(protocol): document codex mailbox index guard
UNREAD: 0
Wave 2 gate: UNMET counts={'verified': 20, 'open': 10}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact ...

$ env -u GIT_INDEX_FILE git log --oneline -5
4d077c9c coord(protocol): document codex mailbox index guard
fa11b793 coord(protocol): clarify mail consumption rule
ab8beb4c coord(protocol): codify codex live rules
e6205050 coord(route): notify wave2 seat tasks
8da10dc2 coord(handoff): verify mode-b budget gate

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected — every relied-on green is backed by execution.
OK

$ GIT_INDEX_FILE=.git/index-codex-director git diff --cached --name-status
# no output before writing this handoff
```

## Next Action

Director should remain on active standby for:

- product-oracle identity/ArcFace review if an artifact lands
- Tier-A co-sign requests
- explicit Pair-A work
- coordinator-directed support that does not cross seat authority

Do not duplicate Pair-B checkpoint implementation or operator2 Lane V.
