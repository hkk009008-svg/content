# Coordination Directory

Inter-session coordination scaffold for the director-operator parallel-Claude
protocol. See [CLAUDE.md](../CLAUDE.md) / [AGENTS.md](../AGENTS.md) `# Director-Operator Concurrent Operation`
for the full discipline (Rules 1–20).

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
- `presence/director.md`, `presence/operator.md` — (v5.7, Rule #19) per-seat
  **live presence**: flat `key: value` (`seat`, `status`, `current_task`,
  `head_at_write`, `updated`). Gitignored + per-clone; the hook bumps
  `updated`/`head_at_write` every tool call, the agent owns `current_task`. The
  peer reads the other file for liveness (fresh `updated` < T = active),
  replacing the old "no commit in 10 min = offline" inference.

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

**Kind enum (v5 update):**

- **v2 (original):** `dispatch-claim` | `findings` | `decision` | `query` |
  `status` | `fold-notice`
- **v4 additions:** `verify-request` | `verification-report` |
  `doc-sync-notice` (Lanes V + D active) | `scout-request` |
  `scout-report` (Lane S scaffolded in v4, **active in v5**)
- **v5 addition:** `memory-candidate` — operator-seat surfaces
  memory-worthy observations (recurring failure modes, tool quirks,
  project-specific gotchas) for director-seat to write or decline
  via `decision`. Closes the latency on operator-observed memory
  candidates without changing memory write authority.

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

## STATE.md model (current — post B-003 Option E + v5.7)

STATE.md is **gitignored, per-clone, regenerated on disk** by
`.claude/hooks/update-state.sh` on each HEAD move. B-003 Option E (cycle 8)
retired the prior `git commit --amend` STATE.md-fold model — the hook **never
touches git history**. STATE.md is an informational cache, NOT a coordination
channel (it is not shared between seats).

**Unread-count accuracy (Rule #20, v5.7).** The hook counts events
`*-to-<role>-*` whose filename-timestamp is newer than the cursor's **content**
timestamp — replacing the pre-v5.7 `find -newer <cursor-mtime>` that counted
both directions AND compared file mtime (the source of the observed
`director=4`-vs-1). The Rule #8 awareness gate **recomputes unread live**
regardless; STATE.md's field is a convenience cache. For exact current HEAD,
`git rev-parse HEAD` (git > STATE.md per the authority precedence).

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
      "matcher": "Bash|Write|Edit",
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
start checklist will still work but the read will be out-of-date). The matcher
is `Bash|Write|Edit` (v5.7): presence freshness (Rule #19) must update through
long edit stretches with no Bash call, not just on commits.

## Per-seat launch (D-a, v5.7)

The two seats run as concurrent Claude Code sessions in **one shared working
tree** (shared object store, shared HEAD on `main`). Per Q4 (user-adjudicated
**D-a**), each seat isolates only its **git index** so one seat's `git add` can
no longer sweep the other's staged WIP (the `2c5ca05` /
`feedback_shared_index_sweep_use_pathspec` class). Launch each session with its
own `GIT_INDEX_FILE` + role marker:

```bash
# director session
export CLAUDE_SEAT=director
export GIT_INDEX_FILE="$(git rev-parse --git-dir)/index-director"
# operator session
export CLAUDE_SEAT=operator
export GIT_INDEX_FILE="$(git rev-parse --git-dir)/index-operator"
```

`CLAUDE_SEAT` (Rule #19) tells the hook which presence file to stamp and lets a
session self-identify its role. `GIT_INDEX_FILE` gives per-seat staging on the
**shared** tree, so presence / STATE.md / `coordination/` stay peer-visible
(gitignored files in the same working dir) — which separate **worktrees** would
break (they force separate branches + separate working dirs → gitignored
presence becomes peer-invisible; rejected per operator REPLY `ab9925d`). With
this live, the `git commit -- <pathspec>` discipline becomes
belt-and-suspenders rather than mandatory.
