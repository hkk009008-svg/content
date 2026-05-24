# Coordination Directory

Inter-session coordination scaffold for the director-operator parallel-Claude
protocol. See [CLAUDE.md](../CLAUDE.md) / [AGENTS.md](../AGENTS.md) `# Director-Operator Concurrent Operation`
for the full discipline (Rules 1–8).

## Layout

- `mailbox/sent/` — Authoritative inter-session events. Each event is a markdown
  file with YAML frontmatter (`from`, `to`, `kind`, `related-commits`,
  `related-rules`). Written directly by sender (Tier-1 auto-send; no approval
  gate in v1).
- `mailbox/seen/director.txt`, `mailbox/seen/operator.txt` — Per-role
  consumed-up-to timestamp. Updated by the consuming session after processing
  events. Filenames are intentionally short; content is a single UTC ISO-8601
  timestamp (e.g., `2026-05-24T13:42:00Z`).
- `mailbox/archive/` — Old events moved out of `sent/` for log hygiene (manual
  move by operator).

## Authority (Rule #8)

A sent mailbox event obligates the receiving role to act per its content, with
authority equal to a user-relayed signal. **User direct instructions override
mailbox events; mailbox events override default behavior.**

### Session-bootstrap awareness gate (Rule #8 sub-clause)

On session start, if `STATE.md`'s `unread mailbox` field shows N ≥ 1 events
for your role, you MUST surface the count to the user in your first
user-facing turn BEFORE processing events:

> "Mailbox has N unread event(s) for {role}; processing now per Rule #8."

The role then processes the queue with full Tier-1 authority. This is a
**one-time-per-session signal**, not a per-event gate. Steady-state events
during the session require no user-surface — Tier-1 throughput preserved.

## Polling cadence (consuming session)

1. **Session start** — Cold-start checklist reads `STATE.md`'s `unread mailbox`
   field; if non-zero, surface to user per the bootstrap gate above and then
   process the queue.
2. **Before any shared-task action** — Pairs with Rule #4 (pre-Write check)
   and Rule #7 (pre-commit check). A mailbox event between your pre-Write
   check and your commit can invalidate the assertion.
3. **After every commit** — STATE.md's hook auto-update surfaces new unread
   count (passive notification).
4. **On receipt of any user direct instruction** that may interact with
   pending events.

## Event format

```markdown
---
from: operator
to: director
kind: dispatch-claim | findings | decision | query | status | fold-notice |
      verify-request | verification-report | doc-sync-notice |
      scout-request | scout-report
related-commits: <sha>, <sha>
related-rules: <rule numbers, if any>
---

<free prose body — the message itself>
```

**Kind enum (v4 update):**

- **v2 (original):** `dispatch-claim` | `findings` | `decision` | `query` |
  `status` | `fold-notice`
- **v4 additions:** `verify-request` | `verification-report` |
  `doc-sync-notice` (Lanes V + D active) | `scout-request` |
  `scout-report` (Lane S scaffolded, active in v5+)

`verification-report` event format (per Rule #9 Lane V):

```markdown
---
from: operator
to: director
kind: verification-report
related-commits: <SHA being reviewed>
related-rules: 9
---

**Status:** ✅ clean / ⚠️ minor / ❌ critical
**Disposition:** fold / advisory

**Findings:**
- <file:line> — <finding>
- ...

<optional narrative body>
```

**Filename convention:** `<UTC-ISO-timestamp>-<from>-to-<to>-<kind>.md`.
Timestamp ensures lexicographic ordering matches chronological. Example:
`2026-05-24T13-42-00Z-operator-to-director-status.md`.

## Stale-event cleanup

Manual for v1. Operator-only task: periodically move events older than ~N
sessions from `sent/` to `archive/`. Stale-event surfacing automation
deferred to v2 if it becomes painful.

## Known limitations (v2.1)

**STATE.md HEAD field is one SHA stale immediately after a commit.** The
hook captures `HEAD_SHA` BEFORE the `git commit --amend` that folds
STATE.md into the commit; the amend changes HEAD, but STATE.md inside the
new commit references the pre-amend SHA. Other STATE.md fields (smoke,
pytest, mailbox unread, working tree, branch ahead/behind) are post-amend-
accurate because they don't depend on the amend.

**For cold-starters:** Trust STATE.md's smoke / pytest / mailbox / tree
fields. For exact current HEAD, verify with `git rev-parse HEAD`. The
HEAD field in STATE.md is the previous (pre-amend) version of the
current commit.

**Fixing cleanly** requires a double-amend (gen → amend → regen with new
SHA → amend again). Costs an extra amend per commit. The v2.1 fix-up
accepts the stale-by-one as the simpler default; revisit if it causes
real confusion in practice.

## Per-clone setup

The hook that auto-maintains `STATE.md` (and thus the `unread mailbox` field)
lives at `.claude/hooks/update-state.sh` (committed). Hook **registration**
lives in `.claude/settings.local.json` (per-clone, gitignored). Each
developer/role must add the following to their own `.claude/settings.local.json`
under the top-level `hooks` key:

```json
"hooks": {
  "PostToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "command",
          "command": "bash /absolute/path/to/Content/.claude/hooks/update-state.sh"
        }
      ]
    }
  ]
}
```

Without registration, `STATE.md` becomes stale after each commit (the cold-
start checklist will still work but the read will be out-of-date).
