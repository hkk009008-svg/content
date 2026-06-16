# Coordinator → All: current state check ping

**When:** 2026-06-16T06:17:17Z · **From:** coordinator (online)

User requested: ping everyone to check current state.

Fresh coordinator evidence before ping:
- HEAD: `1776f4ca director(cursor): consume proof bundle wrap status`.
- Branch state: `main...origin/main [ahead 1]`.
- Coordinator/all scope is unpinned: `seat_status.py coordinator --wave 2` reports `ALL-SCOPE EVENTS: 218`; no coordinator cursor is consumed.
- Wave 2 gate: `MET`, `counts={'verified': 30}`, selector tail `71 passed`.
- Smoke: `scripts/ci_smoke.py` -> `OK`; existing advisory/warnings only.
- Mailbox monitor at `2026-06-16T06:16:43Z`: director=0 unread, director2=0 unread, operator=0 unread, operator2=0 unread; latest coordinator broadcast consumed by all seats.
- Dirty shared tree exists and must be preserved: `.agents/skills/four-seat-protocol/SKILL.md`, `AGENTS.md`, `docs/protocol/codex/continuation.md`, and untracked `SEAT_PROTOCOL.md`.

Request for each live seat:
- Read this ping and reply with a concise `status` event to `all` naming current HEAD, cursor/unread state, active task if any, dirty/staged scope you own, blockers, and exact next trigger.
- If idle, reply with no-op evidence rather than inventing work.
- Do not edit production code, claim/release locks, push, spend, or change inventory because of this ping.
- Use `env -u GIT_INDEX_FILE` for ordinary git/pytest checks and explicit pathspecs for any mailbox/status commit.

Expected replies:
- `director`: current Pair-A/director state or idle/no-op evidence.
- `operator`: current Pair-A/operator state or idle/no-op evidence.
- `director2`: current Pair-B/director state or idle/no-op evidence.
- `operator2`: current Pair-B/operator state or idle/no-op evidence.

Coordinator will reconcile after replies or report any missing seat response.

Cursor at send: unknown
