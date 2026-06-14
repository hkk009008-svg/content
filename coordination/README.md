# Coordination Directory

Inter-session coordination scaffold for the director-operator parallel-Claude
protocol. See [CLAUDE.md](../CLAUDE.md) / [AGENTS.md](../AGENTS.md) `# Director-Operator Concurrent Operation`
for the full discipline (Rules 1–20).

## Layout

- `mailbox/sent/` — Authoritative inter-session events. Each event is a markdown
  file; the v6.0 envelope is an H1 (`# <From> → <To>: <subject>`) followed by a
  `**When:** <ISO-UTC> · **From:** <seat>` line whose timestamp must match the
  filename (linted). Pre-v6.0 events used YAML frontmatter (`from`, `to`,
  `kind`, …) and are grandfathered. Written directly by sender (Tier-1
  auto-send; no approval gate) — preferably via `bin/send-event`.
- `mailbox/seen/director.txt`, `mailbox/seen/operator.txt` — Per-role
  consumed-up-to timestamp; the SINGLE cursor truth (v6.0 — do not restate the
  cursor in commit messages or event prose; the 2026-06-10 three-way divergence
  is why). Advanced via `bin/consume-events`; content is a single UTC ISO-8601
  timestamp (e.g., `2026-05-24T13:42:00Z`).
- `bin/send-event <from> <to> <kind> <subject…>` (body on stdin) — writes a
  convention-conforming event + envelope, appends an automatic
  `Cursor at send:` line read from the sender's seen file, and STAGES the file
  (explicit pathspec; never commits).
- `bin/consume-events <role> [--to <ts>]` — advances `seen/<role>.txt` to the
  newest event addressed to the role (or the explicit target), refusing
  regressions and nonexistent targets, and STAGES the cursor file. **Cursor
  folding (v6.0):** the staged advance rides the seat's next substantive
  commit; standalone cursor-only commits are deprecated (idle-consume exempt).
  A commit whose **entire** changeset is `seen/*.txt` (no `sent/` event, no
  code/doc) is a standalone cursor-only commit; `check_coordination.py --git-root <repo>`
  ADVISORY-flags these (lever #5, capacity audit `wf_6be2ee18-f4b`). Intentional
  idle-consume advances are exempt — prefix the subject `coord(cursor):` to signal it.
  **ACKs:** an `acknowledgement` event that carries substantive body (role
  resolution, retraction, findings) stays a `sent/` event file; a bare "received"
  ACK that adds nothing beyond the cursor should be a cursor advance only.
- `scripts/check_coordination.py` (repo root) — lints all of the above (cursor
  parseable/non-future/non-orphan, filename convention, envelope, kind enum,
  unread report). Wired into `scripts/ci_smoke.py`: FATAL hard-fails locally,
  warns in CI; ADVISORY warns; INFO silent.
- `mailbox/archive/` — Old events moved out of `sent/` for log hygiene (manual
  move by operator).
- `presence/<seat>-heartbeat.ts` — (v6.0 Tier 2) HOOK-OWNED liveness: a single
  line `<ISO-UTC> <short-head>` atomically overwritten on every tool call.
  Read the peer's heartbeat for liveness (fresh < T = active).
- `presence/director.md`, `presence/operator.md` — (v5.7 Rule #19, narrowed by
  v6.0 Tier 2) per-seat **agent-owned intent**: flat `key: value` (`seat`,
  `status`, `current_task`, …). The hook NEVER touches these anymore (the
  pre-split hook sed livelocked the seat's own Write-tool edits and let
  hook-stamped `updated:` mask stale prose). Gitignored + per-clone.
  Transition: a session predating the split has no heartbeat file — fall back
  to its .md `updated:` until the first heartbeat appears.

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

**v6.0 envelope (current — write THIS on new events; the YAML form above is
the grandfathered pre-v6.0 format).** Generated by `bin/send-event`:

```markdown
# Operator → Director: <subject>

**When:** 2026-06-11T10:00:00Z · **From:** operator (online)

<free prose body — the message itself>

Cursor at send: 2026-06-11T09:00:00Z
```

The `**When:**` timestamp must match the filename timestamp (linted by
`scripts/check_coordination.py`). The kind lives in the FILENAME position;
the linter accepts the enum below PLUS the observed-in-practice additions:
`coordination` | `proposal` | `proposal-reply` | `acknowledgement` | `reply` |
`fyi` | `discussion` | `convergence` | `measurement-report` | `wrap`.

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
# director session (run in the shared tree, BEFORE launching `claude`)
cd /Users/hyungkoookkim/Content
export CLAUDE_SEAT=director
export GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-director"
[ -f "$GIT_INDEX_FILE" ] || git read-tree HEAD   # seed a fresh per-seat index from HEAD
claude

# operator session (separate terminal, same tree)
cd /Users/hyungkoookkim/Content
export CLAUDE_SEAT=operator
export GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-operator"
[ -f "$GIT_INDEX_FILE" ] || git read-tree HEAD
claude

# --- Pair B (4-seat protocol; see docs/protocol/claude/four-seat-extension.md) ---
# director2 session (separate terminal, SAME tree)
cd /Users/hyungkoookkim/Content
export CLAUDE_SEAT=director2
export GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-director2"
[ -f "$GIT_INDEX_FILE" ] || git read-tree HEAD
claude

# operator2 session (separate terminal, SAME tree)
cd /Users/hyungkoookkim/Content
export CLAUDE_SEAT=operator2
export GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-operator2"
[ -f "$GIT_INDEX_FILE" ] || git read-tree HEAD
claude
```

**Seats** are `director`, `director2`, `operator`, `operator2` — two
director↔operator **pairs** (A = `director`+`operator`, B = `director2`+`operator2`).
The heartbeat hook (`.claude/hooks/update-state.sh`) is seat-generic, so presence /
heartbeat / per-seat index isolation work for all four with no hook change. Mailbox
events address any seat directly, or `all` to broadcast (`send-event <from> all <kind>`).

The `git read-tree HEAD` seed is **required**: a fresh `GIT_INDEX_FILE` is an
empty index, so without it `git status` reports every tracked file as a phantom
deletion (verified: 555 phantoms vs 0 after seeding). It writes only the new
per-seat index — the working tree and the shared index are untouched. On
relaunch the index already exists, so the seed is skipped.

`CLAUDE_SEAT` (Rule #19) tells the hook which presence file to stamp and lets a
session self-identify its role. `GIT_INDEX_FILE` gives per-seat staging on the
**shared** tree, so presence / STATE.md / `coordination/` stay peer-visible
(gitignored files in the same working dir) — which separate **worktrees** would
break (they force separate branches + separate working dirs → gitignored
presence becomes peer-invisible; rejected per operator REPLY `ab9925d`). With
this live, the `git commit -- <pathspec>` discipline remains **load-bearing
for commit SCOPE**: a wholesale `git add . && git commit` can still sweep the
peer's in-tree changes, so always commit via pathspec (`git commit -- <files>`).

**Index freshness is now hook-maintained (v5.8).** `update-state.sh`
auto-fast-forwards a seat's stale `GIT_INDEX_FILE` index to HEAD on
peer-commit staleness — and only then; staged work is never touched (decision
table in the hook; the manual `git read-tree HEAD` workaround is retired for
this case). The one case left manual is **mixed** state (you have staged work
AND the peer moved HEAD): the hook deliberately abstains, so resolve it with
`git read-tree -m`. The launch seed above (`[ -f … ] || git read-tree HEAD`)
still stands — the hook needs an existing index to maintain.

**Skip-worktree pollution is also hook-cleared (v5.9).** Harness child
processes (Workflow/subagent runs) have twice left skip-worktree bits in the
active index (N=4; N=767/844 on 2026-06-10), which hides the seat's own edits
from `git status` and breaks add/rm with phantom "sparse-checkout" errors.
`update-state.sh` now clears any flagged entry per-path
(`git update-index --no-skip-worktree` — flag-only, staged work untouched)
on every hook fire, and appends one line per event to the gitignored
`.claude/hooks/.skip-worktree-cleared.log` (the evidence trail toward the
still-unidentified trigger op). The manual per-path / `read-tree HEAD`
workarounds are retired for this case.
