# Protocol Bundle v2 — Proposal (Operator Draft for Director Ship)

**Authored:** Operator session, 2026-05-24
**Revised:** Operator session, 2026-05-24 — incorporating director's REPLY at `c6a8f22` (R1 smoke-from-commit-body, R3 Rule #7 standalone, R5 session-bootstrap awareness gate, C2 SHA-change cost comment, C4 explicit single-file git-add comment). User's locked Decision #8 (Tier-1 auto-send) preserved; R5 is a session-start signal, not a per-event gate.
**Authority basis:** `ad6cb4f` "operator drafts; director commits" carve-out (memory + discipline rules).
**Ship strategy:** Single commit, all 4 improvements together, race-ack body if state moves during ship.
**Estimated implementation effort:** ~90 min (director-direct, Option A per REPLY) — was ~2-3hr; R1 dropping smoke from hook trims runtime cost.
**Blocks:** None. Bundle is purely additive over current discipline; nothing currently working breaks.
**State at draft time:** HEAD `c6a8f22` (REPLY committed); 1 commit ahead of `origin/main` at revision time; working tree dirty with held counter bumps in AGENTS.md + CLAUDE.md + this proposal untracked (folds into the ship per Rule #6).

---

## TL;DR (60 seconds)

Four coordinated improvements to the `# Director-Operator Concurrent Operation` protocol, designed and pressure-tested in operator session. Ship as **one atomic commit** because the four pieces compose:

| # | Improvement | What it changes |
|---|---|---|
| **A** | `STATE.md` machine-written truth file (PostToolUse hook) | Cold-start latency: ~2-3 min → ~30 sec |
| **C** | `docs/PROTOCOL-RULES-LOG.md` rule emergence + invocation tracker | Measurable protocol stability; data for rule retirement |
| **D** | Pre-commit re-verify (extends Rule #4) | Closes the "state-moved-between-Write-and-commit" hole (`a6e3ff1` mid-handoff race class) |
| **F** | `coordination/mailbox/` inter-session bus, Tier-1 auto-send | Eliminates user-as-transcriber bottleneck; user remains supervisor via retroactive audit |

The four together create a **measurement-action loop**: STATE.md is the fast-read primitive, D protects writes against drift, F adds a new communication channel, C measures whether any of it is load-bearing.

---

## Why bundle (composability properties)

| Pair | Composition |
|---|---|
| **F + A** | STATE.md surfaces `unread mailbox: N events` per role. Cold-start sees it, routes to mailbox queue first. Without A, F's events would only be discovered by manual polling. |
| **F + D** | Pre-commit re-verify also reads `coordination/mailbox/sent/` for events newer than your Write-start time. If a sent event invalidates your assertion, re-edit or abort. |
| **F + C** | Rule #8 (mailbox authority) joins the log. Invocation count = events sent + consumed per session. Tells us if mailbox is actually used or just exists. |
| **A + D** | STATE.md is updated by hook after every commit, so the pre-commit re-verify in D sees consistent truth (not a stale snapshot from before some intermediate state). |
| **C + everything** | Rules log measures: how often cold-starts trust STATE.md (A), how often D catches real drift, how many mailbox events flow (F). All three become falsifiable from day 1. |

Shipping separately loses the measurement loop and requires N coordination cycles instead of 1.

---

## Locked design decisions (10 questions, user-confirmed)

| # | Question | Decision |
|---|---|---|
| 1 | STATE.md committed or gitignored? | **Committed**, with `--amend --no-edit` in the hook to fold into the triggering commit (no log noise from STATE.md updates appearing as separate commits). |
| 2 | Hook scope: commit, merge, checkout, pull? | **Commit + merge only** for v1. Checkout/pull edge cases (detached HEAD, etc.) deferred. |
| 3 | D rule numbering: extend Rule #4 or new Rule #7? | **REFINED per REPLY R3: Independent Rule #7, with cross-reference to Rule #4 in both directions.** Rule #4 stays as-is (pre-Write `git log -5`); Rule #7 is the new pre-commit re-verify. Separately invocable, separately measurable, separately retire-able. CLAUDE.md/AGENTS.md gets a NEW subsection (not an extension of the existing one). |
| 4 | Rules log: manual logging or auto-detect from commit-body keywords? | **Manual for v1.** Auto-detect heuristics deferred to v2 once we have manual data. |
| 5 | Hook re-runs smoke? | **REFINED per REPLY R1: NO.** Hook does NOT re-run smoke. Smoke is extracted from the latest commit body (same regex pattern as pytest). When not in commit body, label as `unknown (not in commit body; re-run manually)`. Saves ~3s × every commit. |
| 6 | Pytest count source: re-run pytest or extract from latest commit body? | **Extract from latest commit body** via regex. Mark as "(per commit body, may be stale)" so cold-starter knows when to re-run. |
| 7 | Mailbox location: repo or `~/.claude/`? | **Repo (`coordination/`)**. Visible in git history; survives clean clone; auditable. Trade-off: adds log noise; mitigated by `seen/` and `archive/` subdirs moving events out of active view. |
| 8 | Mailbox tier model: Tier-1 (auto-send) or Tier-2 (gated) for v1? | **Tier-1 auto-send.** User is supervisor via retroactive audit of `coordination/mailbox/sent/`. Approval bottleneck eliminated; user remains in loop by reading sent events. **(USER-OVERRIDE: this differs from operator's original recommendation of Tier-2-only-v1; user chose Tier-1 for faster throughput.)** |
| 9 | Mailbox polling cadence: when does each session check? | **REFINED per REPLY R5: 4 points.** (1) Session start — surface unread count to user BEFORE processing queue (session-bootstrap awareness gate; one-time signal per session, not a per-event gate); (2) before any shared-task action; (3) via PostToolUse hook surfacing unread count after every commit (STATE.md passive notification); (4) on receipt of any user direct instruction that may interact with pending events. |
| 10 | Authority conflict: user direct instruction vs sent mailbox event? | **User direct instructions override mailbox events; mailbox events override default behavior.** Add clarifying clause to Rule #8. Existing CLAUDE.md "Instruction Priority" still binds. |

---

## The 4 improvements — full spec

### A — `STATE.md` (cold-start oracle)

**Location:** Repo root.

**Format** (auto-generated; do not hand-edit):

```markdown
<!-- AUTO-GENERATED by .claude/hooks/update-state.sh — DO NOT HAND-EDIT -->
# Repository State Snapshot

- **HEAD:** `<sha>` (`<subject>`)
- **Branch:** main, <N> ahead / <M> behind `origin/main`
- **Working tree:** clean | dirty (first 5 modified files)
- **Smoke:** OK | FAIL | unknown (last run `<timestamp>`)
- **Pytest:** <N> passed / <M> skipped / <K> failed (per commit body, may be stale)
- **Unread mailbox:** director=<N>, operator=<M>
- **Updated:** `<timestamp>` (after commit `<sha>`)
```

**Update mechanism:** PostToolUse hook fires after `git commit` and `git merge` events. Hook script: `.claude/hooks/update-state.sh`.

**Trust model:**
- HEAD + branch + working tree state: machine-authoritative (just observed).
- Smoke: **informational** (extracted from latest commit body per REPLY R1; cold-starter re-runs if stale or commit body lacks the smoke line).
- Pytest count: informational (extracted from latest commit body; cold-starter may re-run if stale).
- Unread mailbox: machine-authoritative (just counted).

**Read pattern:** First thing in cold-start checklist. Cold-starter trusts STATE.md unless commit-time timestamp is significantly older than HEAD's commit time (indicating hook didn't fire), in which case re-run the full cold-start manually.

### C — `docs/PROTOCOL-RULES-LOG.md` (rule emergence + invocation tracker)

**Location:** `docs/PROTOCOL-RULES-LOG.md`.

**Initial content** (populated at ship time):

```markdown
# Protocol Rules — Emergence + Invocation Log

Tracks each codified rule's introduction (codification SHA + race that triggered it)
and per-session invocation count. Updated manually at session-close by operator
(or director, whoever wraps the session).

## Rule registry

| # | Rule | Codified | Race that triggered |
|---|---|---|---|
| 1 | Role partition (director-only / operator-only / shared) | `ad6cb4f` | Session 6 phase_c pre-locate race |
| 2 | Signaling narration (announce shared-task intent in chat) | `ad6cb4f` | Same race |
| 3 | Git tiebreaker (first commit to land wins) | `ad6cb4f` | Hypothetical; documented preemptively |
| 4 | State-asserting writes precondition (`git log -5` before Write) | `ea97d0a` | Stale handoff doc race (843c102 pre-write) |
| 5 | Race-acknowledging commit body (name what shifted during work) | `ea97d0a` | Same |
| 6 | Counter-bump fold-and-surface (during concurrent ops) | `ea97d0a` | Standalone chore(baseline) pollution risk |
| 7 | Pre-commit re-verify (state changes between Write and commit) | `<this ship's SHA>` | `a6e3ff1` mid-handoff race (Monitor.tsx shipped during operator handoff Write) |
| 8 | Mailbox authority (sent events bind equal to user-relayed signals) | `<this ship's SHA>` | User-as-relay bottleneck observed across cycles 1-3 |

## Invocation log

### Session 2026-05-24-cycle-3 (this conversation)

| Rule | Invocations | Notes |
|---|---|---|
| 1 | 8+ | Role partition consciously consulted every shared-task decision |
| 2 | 4 | Director narrated dispatches; operator narrated handoff-doc-write claim |
| 3 | 0 | No dispatch races landed |
| 4 | 6 | Pre-Write `git log -5` performed before each state-asserting commit |
| 5 | 3 | `843c102`, `1541a69`, and at least one director commit used race-ack body |
| 6 | 4 | Counter-bump held + folded into 4 different commits |
| 7 | n/a | New rule, not yet invocable |
| 8 | n/a | New rule, not yet invocable |

(Future sessions append new tables.)

## Retirement criteria

A rule unused for 5 consecutive sessions → flagged for review.
If still unused after 3 more sessions → retired (moved to "## Retired rules"
section below with retirement-SHA + reason).
```

**Update mechanism:** Manual. Operator/director appends an invocation table at session-close. Phase 2 (deferred): auto-detection via grep on commit bodies for rule-keyword markers.

**Read pattern:** Periodic (every 5+ sessions), at strategic-review time, to assess protocol maturity and flag stale rules.

### D — Pre-commit re-verify (Rule #7, NEW standalone — paired with Rule #4)

**REFINED per REPLY R3.** Originally framed as "extends Rule #4." Director's refinement: this is its own rule (#7), not an extension. Rule #4 (pre-Write `git log -5`) stays unchanged. Rule #7 is the new pre-commit re-verify. They pair to close the Write-and-commit hole but are separately invocable, measurable, and retire-able.

**No new files.** Edits to `CLAUDE.md` and `AGENTS.md` `# Director-Operator Concurrent Operation` → NEW `## Pre-commit re-verify (Rule #7)` subsection (inserted AFTER `## Counter-bump dispositions during concurrent operation` and BEFORE the new Rule #8 mailbox subsection).

**Prose for the new subsection:**

> ## Pre-commit re-verify (Rule #7)
>
> Rule #4 above requires `git log --oneline -5` *before* a state-asserting Write/Edit (pre-Write gate). Rule #7 is the matching *pre-commit* gate. Together they close the hole where state can move between your Write and your commit — observed in `a6e3ff1` mid-handoff race.
>
> Immediately before `git commit` for any state-asserting commit, run `git log --oneline -5` AND read `coordination/mailbox/sent/` for events newer than your Write-start time. Compare to the pre-Write check (Rule #4). If observed HEAD or unread mailbox events changed:
>
> - **Drift below your concern threshold** (counter bump, unrelated commit, informational mailbox event): commit normally; mention "rebased mentally on `<new HEAD>`" in body.
> - **Drift that contradicts your content** (HEAD shipped something your doc says is pending; mailbox event invalidates your assertion): re-edit affected sections + race-ack body per Rule #5.
> - **Drift that makes your work redundant** (your fix was just shipped by other party; mailbox dispatch claimed your work): abort the commit; surface the duplicate to user.
>
> Cross-reference: see Rule #4 for the pre-Write gate.

**Cost:** One extra `git log -5` + one `ls coordination/mailbox/sent/` per state-asserting commit. ~100ms.

### F — `coordination/mailbox/` (inter-session bus, Tier-1 auto-send)

**Location:** `coordination/mailbox/` (new directory tree at repo root).

**Structure:**

```
coordination/
├── README.md                       ← protocol description for cold readers
└── mailbox/
    ├── sent/                       ← authoritative events (each session reads here)
    │   └── 2026-05-24T11-29-02Z-director-to-operator-dispatch-claim.md
    ├── seen/
    │   ├── director.txt            ← last-consumed timestamp per role
    │   └── operator.txt
    └── archive/                    ← consumed events older than current session (manual move)
```

**Note:** No `drafts/` directory in v1 per locked decision #8 (Tier-1 auto-send only). Add `drafts/` in a future v2 if Tier-2 gating becomes useful.

**Event format** (each file in `sent/`):

```markdown
---
from: operator
to: director
kind: dispatch-claim | findings | decision | query | status | fold-notice
related-commits: <sha>, <sha>
related-rules: <rule numbers, if any>
---

<free prose body — the message itself>
```

**Filename convention:** `<UTC-ISO-timestamp>-<from>-to-<to>-<kind>.md`. Timestamp ensures lexicographic ordering matches chronological.

**Send mechanism (Tier-1 auto-send):** Sender writes directly to `coordination/mailbox/sent/{filename}.md`. No approval gate. Visible to user retroactively via `ls coordination/mailbox/sent/`.

**Polling mechanism:** Receiving role reads `coordination/mailbox/sent/` files newer than its `seen/{role}.txt` timestamp at:
1. **Session start** — surface unread count to user BEFORE processing queue (session-bootstrap awareness gate per REPLY R5; one-time per session, not a per-event gate).
2. Before any shared-task action (pairs with Rule #4 pre-Write check and Rule #7 pre-commit check).
3. After every commit (via STATE.md `unread mailbox` field surfaced by hook).
4. On receipt of any user direct instruction that may interact with pending events.

**Consumed marker:** After processing an event, session updates `seen/{role}.txt` to the latest timestamp it consumed. Hook re-reads on next update.

**Archive mechanism:** Manual. Operator-only task: periodically `mv coordination/mailbox/sent/<old>.md coordination/mailbox/archive/<old>.md` for events more than N sessions old. Stale-event surfacing left to v2 if it becomes painful.

**New Rule #8 prose** (add after existing Rule #6 in CLAUDE.md + AGENTS.md):

> **Rule #8 — Mailbox events have authority equal to user-relayed signals.** A sent mailbox event (file in `coordination/mailbox/sent/`) obligates the receiving role to act per its content. Ignoring or deferring a sent mailbox event requires the same justification as ignoring a direct user instruction.
>
> **Authority conflict resolution:** User direct instructions override mailbox events; mailbox events override default behavior. (Mirrors and extends the existing CLAUDE.md "Instruction Priority" hierarchy.)
>
> **v1 is Tier-1 auto-send** (no user-approval gate on sends). User remains supervisor via retroactive audit of `coordination/mailbox/sent/`. If a sent event should not have been sent, user signals via direct instruction (which by the above priority overrides the mailbox event).
>
> **Session-bootstrap awareness gate (per REPLY R5).** On session start, if STATE.md's `unread mailbox` field shows N ≥ 1 events for your role, you MUST surface the count to the user in your first user-facing turn BEFORE processing events:
>
> > "Mailbox has N unread event(s) for {role}; processing now per Rule #8."
>
> The role then processes the queue with full Tier-1 authority. This is a **one-time-per-session signal**, not a per-event gate. Steady-state events during the session require no user-surface — Tier-1 throughput preserved.

---

## Implementation order within the single ship

Even though shipped atomically, write in this dependency order:

1. **D first** (smallest surface, no new files): Edit `CLAUDE.md` + `AGENTS.md` `# Director-Operator Concurrent Operation` section to add the NEW Rule #7 standalone subsection (`## Pre-commit re-verify (Rule #7)`) AND the NEW Rule #8 standalone subsection (`## Mailbox events have authority equal to user-relayed signals`). Both inserted between `## Counter-bump dispositions during concurrent operation` and `## Git is the tiebreaker`. Rule #4 stays unchanged (per REPLY R3).
2. **C second** (new file, populated with historical data): Create `docs/PROTOCOL-RULES-LOG.md` with the 8 rule entries + this session's retroactive invocation counts.
3. **A third** (new files + hook):
   - Write `.claude/hooks/update-state.sh` (see "Implementer guidance" below for example).
   - Update `.claude/settings.local.json` (or equivalent) to register the hook on PostToolUse for commit + merge.
   - Run the hook once manually to generate initial `STATE.md`.
4. **F fourth** (new directory + protocol scaffold):
   - Create `coordination/mailbox/{sent,seen,archive}/` directories (with `.gitkeep` files for empty dirs).
   - Create `coordination/README.md` describing the mailbox protocol for cold readers.
   - Initialize `coordination/mailbox/seen/{director,operator}.txt` to ship-time UTC timestamp.

All five files (+ updated CLAUDE.md, AGENTS.md, settings) staged + committed in **one commit**. Race-ack body if state moves during draft (Rule #5).

---

## New artifacts after ship (summary table)

| Artifact | Type | Owner | Update mechanism |
|---|---|---|---|
| `STATE.md` (repo root) | Machine-written truth | hook | PostToolUse after commit/merge |
| `.claude/hooks/update-state.sh` | Hook script | manual | Edit if hook logic changes |
| `.claude/settings.local.json` (updated) | Hook registration | manual | Edit when adding/removing hooks |
| `docs/PROTOCOL-RULES-LOG.md` | Append-only log | operator/director | Manual at session-close |
| `CLAUDE.md` + `AGENTS.md` (Rule #4 extended + Rule #8 added) | Binding discipline | director (operator may draft) | Edit on rule changes |
| `coordination/README.md` | Protocol description for mailbox | manual | Edit when mailbox protocol changes |
| `coordination/mailbox/sent/` | Authoritative event store | both roles | Per-event writes (Tier-1 auto-send) |
| `coordination/mailbox/seen/{role}.txt` | Per-role consumed marker | each role | Updated after polling consumed events |
| `coordination/mailbox/archive/` | Old events (manual move) | operator | Manual periodic cleanup |

**Total surface:** 3 new top-level files + 1 hook script + 1 settings update + 2 binding-rule sections edited + 1 new directory tree (coordination/) with subdirs + 1 README + 2 seen markers.

---

## Implementer guidance

### Example hook script (`.claude/hooks/update-state.sh`)

```bash
#!/usr/bin/env bash
# .claude/hooks/update-state.sh
# PostToolUse hook: regenerates STATE.md after git commit/merge.
# Folds into the triggering commit via git commit --amend --no-edit.
#
# Failure modes handled:
# - Skips if invoked during the amend itself (avoids infinite loop).
# - Skips if not in a git repo (defensive).
# - Tolerates missing origin/main (e.g., fresh clone, detached HEAD).
#
# IMPORTANT (per REPLY C2): This hook amends the just-made commit via
# `git commit --amend --no-edit`. That changes the commit SHA. Reviewers
# and briefs that cite SHAs from chat output may see a different SHA when
# they `git show` after the hook fires. Historical commits are NEVER
# touched; only the just-made one.

set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

# Skip if STATE.md is already in the staged set (we're in the amend loop)
if git diff --cached --name-only 2>/dev/null | grep -qx 'STATE.md'; then
  exit 0
fi

HEAD_SHA=$(git rev-parse HEAD)
HEAD_SUBJECT=$(git log -1 --format='%s' HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
AHEAD=$(git rev-list --count "origin/${BRANCH}..HEAD" 2>/dev/null || echo "?")
BEHIND=$(git rev-list --count "HEAD..origin/${BRANCH}" 2>/dev/null || echo "?")

WT_LINES=$(git status --porcelain 2>/dev/null | head -5)
if [ -z "$WT_LINES" ]; then
  WT_STATE="clean"
else
  WT_STATE=$(printf "dirty:\n%s" "$WT_LINES")
fi

# Smoke (per REPLY R1: extracted from latest commit body; not re-run)
# Trade-off: hook stays ~100ms (vs ~3s if smoke ran). Cold-starter
# re-runs scripts/ci_smoke.py manually if STATE.md says "unknown" or
# the commit-body smoke line is stale relative to current code.
SMOKE_LINE=$(git log -1 --format='%B' HEAD | grep -E "ci_smoke\.py" -A1 | tail -1 || true)
if echo "$SMOKE_LINE" | grep -q "OK"; then
  SMOKE_RESULT="OK (per commit body)"
elif echo "$SMOKE_LINE" | grep -qE "FAIL|error"; then
  SMOKE_RESULT="FAIL (per commit body)"
else
  SMOKE_RESULT="unknown (not in commit body; re-run manually)"
fi

# Pytest count from latest commit body (regex)
PYTEST_LINE=$(git log -1 --format='%B' HEAD | grep -Eo '[0-9]+ passed[^,]*, [0-9]+ skipped[^,]*, [0-9]+ failed' | head -1 || true)
[ -z "$PYTEST_LINE" ] && PYTEST_LINE="(not in commit body; re-run manually for ground truth)"

# Mailbox unread counts
UNREAD_DIR=0
UNREAD_OP=0
if [ -d "coordination/mailbox/sent" ]; then
  if [ -f "coordination/mailbox/seen/director.txt" ]; then
    UNREAD_DIR=$(find coordination/mailbox/sent -type f -name '*.md' -newer coordination/mailbox/seen/director.txt 2>/dev/null | wc -l | tr -d ' ')
  fi
  if [ -f "coordination/mailbox/seen/operator.txt" ]; then
    UNREAD_OP=$(find coordination/mailbox/sent -type f -name '*.md' -newer coordination/mailbox/seen/operator.txt 2>/dev/null | wc -l | tr -d ' ')
  fi
fi

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

cat > STATE.md <<EOF
<!-- AUTO-GENERATED by .claude/hooks/update-state.sh — DO NOT HAND-EDIT -->
# Repository State Snapshot

- **HEAD:** \`${HEAD_SHA}\` (${HEAD_SUBJECT})
- **Branch:** ${BRANCH}, ${AHEAD} ahead / ${BEHIND} behind \`origin/${BRANCH}\`
- **Working tree:** ${WT_STATE}
- **Smoke:** ${SMOKE_RESULT} (last run ${TIMESTAMP})
- **Pytest:** ${PYTEST_LINE}
- **Unread mailbox:** director=${UNREAD_DIR}, operator=${UNREAD_OP}
- **Updated:** ${TIMESTAMP} (after commit \`${HEAD_SHA}\`)
EOF

# Fold into the just-made commit (no new commit appears in log)
# DELIBERATE (per REPLY C4): ONLY STATE.md is staged. Never use `git add -A`
# or `git add .` — counter-bumps in AGENTS.md/CLAUDE.md must remain in working
# tree per Rule #6 (operator territory; fold-and-surface, not auto-absorb).
git add STATE.md
git commit --amend --no-edit --no-verify
```

Refine as needed; this is a working starting point. The `--no-verify` on the amend is necessary to avoid re-firing pre-commit hooks (and re-firing this hook itself).

### Example `coordination/README.md`

```markdown
# Coordination Directory

Inter-session coordination scaffold for the director-operator parallel-Claude
protocol. See CLAUDE.md / AGENTS.md `# Director-Operator Concurrent Operation`
for the full discipline.

## Layout

- `mailbox/sent/` — Authoritative inter-session events. Each event is a markdown
  file with YAML frontmatter (from, to, kind, related-commits, related-rules).
  Written directly by sender (Tier-1 auto-send; no approval gate in v1).
- `mailbox/seen/{director,operator}.txt` — Per-role consumed-up-to timestamp.
  Updated by the consuming session after processing events.
- `mailbox/archive/` — Old events moved out of `sent/` for log hygiene
  (manual move by operator).

## Authority (Rule #8)

A sent mailbox event obligates the receiving role to act per its content,
with authority equal to a user-relayed signal. User direct instructions
override mailbox events; mailbox events override default behavior.

## Polling cadence (consuming session)

1. Session start (cold-start checklist reads `STATE.md`'s `unread mailbox`
   field, processes queue if non-zero).
2. Before any shared-task action (Rule #4 extension).
3. After every commit (STATE.md auto-update surfaces new unread count).

## Stale-event cleanup

Manual for v1. Operator-only task: periodically move events older than
~N sessions from `sent/` to `archive/`.
```

### CLAUDE.md / AGENTS.md edit anchors

**REVISED per REPLY R3: two NEW standalone subsections, not an extension of an existing subsection.**

For `CLAUDE.md`:
- Insert NEW `## Pre-commit re-verify (Rule #7)` subsection AFTER `## Counter-bump dispositions during concurrent operation` (anchor: just before the new Rule #8 subsection below). Use the Rule #7 prose from §D above.
- Insert NEW `## Mailbox events have authority equal to user-relayed signals` subsection AFTER the new Rule #7 subsection and BEFORE `## Git is the tiebreaker`. Use the Rule #8 prose from §F above (including the session-bootstrap awareness gate sub-clause per R5).
- Leave the existing `## State-asserting writes: gate on \`git log --oneline -5\`` subsection (Rule #4) UNCHANGED — only the Rule #7 cross-reference points back to it.
- Add `Rule #7 (Pre-commit re-verify)` and `Rule #8 (Mailbox authority)` to any role-partition or rules-summary reference if Rule numbering is enumerated elsewhere.

Mirror to `AGENTS.md` with lowercase universal phrasing (Write/Edit → write/edit).

---

## Acceptance criteria

Ship is complete when ALL of the following hold:

- [ ] `STATE.md` exists at repo root with all 7 required fields populated; matches current observed state (HEAD, branch, tree, smoke, pytest, mailbox, timestamp).
- [ ] `.claude/hooks/update-state.sh` exists, is executable, and is registered in `.claude/settings.local.json` for PostToolUse on commit + merge events.
- [ ] Hook fires successfully on a test commit; STATE.md updates atomically (amended into the test commit; no separate STATE.md commit appears in `git log`).
- [ ] `docs/PROTOCOL-RULES-LOG.md` exists with 8 rule entries + this session's retroactive invocation table.
- [ ] `CLAUDE.md` + `AGENTS.md` `# Director-Operator Concurrent Operation` section has (per REPLY R3 + R5):
  - NEW Rule #7 subsection (`## Pre-commit re-verify (Rule #7)`) after `## Counter-bump dispositions during concurrent operation`, ~18 lines.
  - NEW Rule #8 subsection (`## Mailbox events have authority equal to user-relayed signals`) after Rule #7 and before `## Git is the tiebreaker`, ~20 lines (includes session-bootstrap awareness gate sub-clause per R5).
  - Existing Rule #4 subsection (`## State-asserting writes`) UNCHANGED — Rule #7's prose only adds a back-reference.
- [ ] `coordination/mailbox/{sent,seen,archive}/` directories exist with `.gitkeep` or seed files.
- [ ] `coordination/README.md` describes the mailbox protocol.
- [ ] `coordination/mailbox/seen/{director,operator}.txt` initialized to ship-time UTC timestamp.
- [ ] Operator-transplant handoff (`docs/HANDOFF-operator-transplant-2026-05-24.md`) cold-start checklist updated to read STATE.md first.
- [ ] Smoke + pytest + tsc all still pass at ship commit (no regression from bundle).
- [ ] Single commit (per locked decision); race-ack body if state moves during ship.
- [ ] Counter bumps in AGENTS.md + CLAUDE.md folded into the ship commit per Rule #6 (currently held in working tree at this proposal's draft time).

---

## What director needs to do

1. **Review this proposal** — read end-to-end. Confirm the 10 locked design decisions match your understanding, especially the user's Tier-1 override for question #8.
2. **Decide implementation path:**
   - **Option A:** Director implements all 4 directly (uses Edit/Write tools in own context; ~2-3 hours of focused work). Cleaner because no subagent handoff; director maintains full control.
   - **Option B:** Director dispatches a Lane-B implementer subagent with this proposal as the brief. Subagent does the file creation + edits; director audits + commits. Higher throughput; subagent absorbs the mechanical work.
   - **Recommend Option B** for the hook script + mailbox scaffold (mechanical), Option A for the CLAUDE.md/AGENTS.md edits (you're authoritative here per "director ships discipline").
3. **Ship as single commit** (per locked decision + acceptance criteria) with race-ack body if state moves during work.
4. **Update `docs/HANDOFF-operator-transplant-2026-05-24.md`** cold-start checklist to read STATE.md first (this is operator-only per role partition, but if you're shipping the bundle you'll be in the file anyway — fold the change in).
5. **Append to PROTOCOL-RULES-LOG.md** at session-close: this ship's commit SHA in the Rule #7 + Rule #8 codification column.

---

## What director should NOT do (operator-asserted anti-patterns)

- **Do NOT add Tier-2 (drafts/ + approval gate) to F yet** — user explicitly chose Tier-1-only for v1. Tier-2 stays deferred until we observe whether retroactive supervision is sufficient.
- **Do NOT auto-detect rule invocations** in C's log — manual logging in v1; mechanize only after we have data.
- **Do NOT eliminate counter-bumps** by moving counters to non-prose files — counter-bumps are the simplest example of "operator absorbs noise so director can ship clean"; their existence is load-bearing for role asymmetry.
- **Do NOT auto-generate race-ack commit bodies** from a hook — ship the manual version first; mechanize only if humans/LLMs prove unreliable at it.
- **Do NOT add hooks for `git push`** — push policy is still open (separate Tier-2 improvement, deferred). Don't constrain push timing via hooks yet.
- **Do NOT bundle additional improvements** (mailbox stale-event cleanup automation, role-swap challenge protocol, etc.) into this ship — keep the surface tight; these are separate Tier-2/3 considerations.

---

## Race-ack disclaimer

This proposal was drafted at HEAD `f8b2aef` (Session 9 minors). Between draft and ship, director was actively shipping at high cadence (~5 commits in the 30 minutes preceding this draft). If state has moved significantly by the time you read this:

- Cold-start: re-run `git log --oneline -10` and reconcile with this proposal's commit ledger references (Session 9 SHIPPED via `607348d`/`bfa60bf`/`a97573e`/`f8b2aef`; P4-3 design surfaced via `e8b5ebc`).
- Acceptance criteria: still apply unchanged — they're forward-looking.
- Implementation order: still applies unchanged — D/C/A/F has no dependency on specific commits.
- Race-ack body: required per Rule #5 if state moved during your implementation work.

---

## References

- `ad6cb4f docs(discipline): codify director-operator concurrent-operation protocol` — original codification (Rules 1-6).
- `ea97d0a docs(discipline): codify state-assertion, race-ack, counter-bump rules` — extension (Rules 4-6 codified there; precedent for "operator drafts, director ships" carve-out).
- `docs/HANDOFF-operator-transplant-2026-05-24.md` — operator-side handoff with all current rules and patterns referenced.
- `docs/HANDOFF-director-transplant-2026-05-24-cycle2.md` — director's cycle-2 transplant.
- `docs/POST-ROADMAP-2026-05-24.md` — current roadmap status (cycle-3 picks); last refreshed at `64c7571`.
- `~/.claude/projects/-Users-hyungkoookkim-Content/memory/feedback_pre-locate-after-git-log.md` — operator memory file capturing the precondition rule from session experience.

---

*Operator draft complete. Ready for director ship per `ad6cb4f` draft-then-ship carve-out. Single commit; race-ack body if state moves. Acceptance criteria are the gate; the four pieces compose as a unit.*
