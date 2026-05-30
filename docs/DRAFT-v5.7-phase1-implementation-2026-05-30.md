# DRAFT — Protocol Bundle v5.7 Phase-1 implementation (ready to apply; NOT shipped)

> **STATUS: DRAFT. No live behavior is changed by this file.** It is a docs
> artifact holding ready-to-apply Phase-1 code so it can ship the moment the
> operator REPLY lands (after folding any REPLY refinements). Companion to
> [PROPOSAL-protocol-bundle-v5.7-2026-05-30.md](PROPOSAL-protocol-bundle-v5.7-2026-05-30.md).
> Do **not** apply before the REPLY cycle completes (user direction:
> proposal-first). HEAD at draft: `ec8946b`.

## Phase-1 scope (per proposal Q5)

`M1` presence files · `M3` role marker · `M2` unread-count fix · Rule #19/#20
text. **Deferred to Phase 2/3:** STATE.md peer block + refresh-cadence (P2);
topology declaration / per-seat worktree-or-index isolation (P3, **user-adjudicated** per Q4).

One refinement vs the proposal: presence files use **flat `key: value` lines**
(not YAML frontmatter) so the hook can `sed`-bump freshness fields without a YAML
parser. Flagged for operator REPLY.

---

## 1. `M2` — fix the unread-count logic in `.claude/hooks/update-state.sh`

**The bug (current `:72-82`):** `find sent/ -newer seen/<role>.txt` counts events
in **both directions** (no `to:` filter → includes the role's own outgoing sends)
and compares each file's **mtime** against the cursor **file's mtime**, not the
cursor's ISO **content**. This is why session-start showed `director=4` when the
actionable count was 1.

**Validated regression (controlled data, ran 2026-05-30):** cursor content
`08:00` (file mtime forced to `07:00`); events `09:00 op→dir`, `09:30 dir→op`,
`07:00 op→dir`. Old logic = **3** (wrong: counts the own-send + the before-cursor
event); new logic = **1** (correct). A real version of this becomes the C2 unit
test.

**Replacement for lines 72–82** (drop-in):

```bash
# Mailbox unread counts (v5.7 M2): count events ADDRESSED to <role> whose
# filename-timestamp is strictly newer than the role cursor's CONTENT timestamp.
# Replaces the prior `find -newer <cursor-mtime>` which (a) counted BOTH
# directions (no to: filter) and (b) compared file mtime, not the cursor's ISO
# content. Filenames are `<UTC-ISO>-<from>-to-<to>-<kind>.md` (README convention);
# the leading token is a fixed-width 20-char `YYYY-MM-DDTHH-MM-SSZ`.
_unread_for() {                       # $1 = role (director|operator)
  local role="$1" cf cur curkey count=0 f ts
  cf="coordination/mailbox/seen/${role}.txt"
  [ -f "$cf" ] || { echo 0; return; }
  cur=$(tr -d '[:space:]' < "$cf")            # 2026-05-30T00:37:53Z
  curkey=$(printf '%s' "$cur" | tr ':' '-')   # -> 2026-05-30T00-37-53Z (match filename token form)
  for f in coordination/mailbox/sent/*-to-"${role}"-*.md; do
    [ -e "$f" ] || continue
    ts=$(basename "$f"); ts=${ts:0:20}
    # LC_ALL=C: byte-order compare of fixed-width ISO == chronological.
    [ "$(LC_ALL=C; [[ "$ts" > "$curkey" ]] && echo 1)" = 1 ] && count=$((count+1))
  done
  echo "$count"
}
UNREAD_DIR=0; UNREAD_OP=0
if [ -d "coordination/mailbox/sent" ]; then
  UNREAD_DIR=$(_unread_for director)
  UNREAD_OP=$(_unread_for operator)
fi
```

(Simpler inline form if the subshell-`LC_ALL` reads awkwardly: prefix the whole
hook with `export LC_ALL=C` near `set -euo pipefail`, then use a bare
`[[ "$ts" > "$curkey" ]]`.)

## 1b. `M1` auto-freshness — presence stamp in the same hook

The presence file must refresh **even when HEAD does not move** (the whole point
is liveness during non-committing work). The current hook early-exits on a static
HEAD (`:40-42`), so the presence stamp must run **before** that skip-gate.

**Insert immediately after the `cd … || exit 0` (≈`:30`), before the skip-perf gate:**

```bash
# Presence auto-freshness (v5.7 M1): stamp this seat's presence file every Bash
# call (NOT HEAD-gated — liveness must update during non-committing work). The
# agent owns `status` + `current_task` (Rule #19); the hook only bumps freshness.
if [ -n "${CLAUDE_SEAT:-}" ]; then
  mkdir -p coordination/presence
  _PF="coordination/presence/${CLAUDE_SEAT}.md"
  _NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  _H=$(git rev-parse --short HEAD 2>/dev/null || echo "?")
  if [ -f "$_PF" ]; then
    _t=$(mktemp)
    sed -e "s|^head_at_write:.*|head_at_write: ${_H}|" \
        -e "s|^updated:.*|updated: ${_NOW}|" "$_PF" > "$_t" && mv "$_t" "$_PF"
  else
    printf 'seat: %s\nstatus: active\ncurrent_task: (set me when your focus changes)\nhead_at_write: %s\nupdated: %s\n' \
      "$CLAUDE_SEAT" "$_H" "$_NOW" > "$_PF"
  fi
fi
```

**Also (Phase-1 settings, per-clone `.claude/settings.local.json`):** extend the
PostToolUse matcher from `"Bash"` to also fire on `Write|Edit`, so presence stays
fresh through long edit stretches with no Bash call:

```json
"PostToolUse": [
  { "matcher": "Bash|Write|Edit",
    "hooks": [ { "type": "command",
      "command": "bash /Users/hyungkoookkim/Content/.claude/hooks/update-state.sh" } ] } ]
```

(The skip-perf gate keeps the heavy STATE.md regen HEAD-gated; only the cheap
presence stamp runs every call.)

## 2. `M1` — presence files + gitignore

New `coordination/presence/director.md` and `operator.md` (flat key:value;
**gitignored** — real-time, would churn history; the durable record stays in the
mailbox + git log). Template:

```
seat: director
status: active            # active | wrapping | away
current_task: (one line — what you're doing right now)
head_at_write: ec8946b
updated: 2026-05-30T00:00:00Z
```

**Append to `.gitignore`:**

```
# v5.7 M1 — real-time presence signals (per-clone, like STATE.md; not source)
coordination/presence/
```

The peer reads the *other* file at gates (+ whenever it wants liveness). Liveness
= `updated` freshness AND/OR file mtime < threshold T (Rule #19).

## 3. `M3` — role marker

Each session exports its seat before launch (or in the per-clone shell rc):

```bash
export CLAUDE_SEAT=director     # or: operator
```

Effects: (a) the hook (§1b) stamps the correct presence file; (b) a session
self-identifies its role without relying on the user's opening phrasing; (c) the
Rule #8 gate can assert "I am ${CLAUDE_SEAT}" deterministically. If `CLAUDE_SEAT`
is unset, the hook simply skips the presence stamp (graceful no-op) — surface
"role unset" to the user.

## 4. Rule #19 + #20 — codification text (for CLAUDE.md / AGENTS.md / PROTOCOL-RULES-LOG.md)

Paste the two rule blocks from the proposal §"Proposed rules" verbatim (Rule #19
Live-presence-over-inferred-idle; Rule #20 Shared-state-accuracy), each with its
`Beneficiary (per R11): both` line and a `Codified SHA:` placeholder
(`_Protocol Bundle v5.7 ship_`, filled next session-close per the chicken-and-egg
precedent). Add two rows to `docs/PROTOCOL-RULES-LOG.md`:

| # | Rule | Codified | Race that triggered |
|---|---|---|---|
| 19 | Live-presence-over-inferred-idle (presence files; liveness=freshness not commit-recency; bind via artifacts not chat) | `_v5.7 ship_` | User-reported 2026-05-30 mutual-offline/unaware failure; RC1/RC2 (no presence primitive + chat peer-invisible) |
| 20 | Shared-state-accuracy (awareness gate recomputes unread `to:`-filtered + content-ts; per-event acks) | `_v5.7 ship_` | Same; RC3/RC4 (STATE.md `director=4`-vs-1 + cursor lag, this session) |

Also reconcile the Rule #2 §Signaling wording (narration is a user-facing
courtesy, not a peer channel — superseded by Rule #19.3) and update
`coordination/README.md` (Rules 1–8 → 20; delete the retired `--amend` "Known
limitations v2.1" section — that's RC7, a Lane-D doc fix).

## 5. Apply checklist (post-REPLY only)

1. Fold any operator-REPLY refinements (Q1–Q6) into the blocks above.
2. Edit `.claude/hooks/update-state.sh`: insert §1b presence stamp before the
   skip-gate; replace `:72-82` with §1 unread logic.
3. Add a real unit/smoke test mirroring the validated regression (old=3/new=1).
   Run it; expect pass.
4. Create `coordination/presence/{director,operator}.md` from the §2 template;
   append the `.gitignore` block.
5. Extend the PostToolUse matcher (§1b) in each clone's `settings.local.json`.
6. Codify Rule #19/#20 into CLAUDE.md + AGENTS.md + PROTOCOL-RULES-LOG.md (§4);
   fix `coordination/README.md` (RC7).
7. Run §15 smoke (expect OK) + full unit suite (expect 1265/3 + the new test).
8. Commit per-concern (`feat(coord):` hook+presence; `docs(protocol):` rules);
   pathspec-scoped (shared index). Operator Lane V.

## 6. Deliberately NOT in Phase 1

- STATE.md "Peer" block + off-commit-cadence refresh (Phase 2 — needs M1 live first).
- Per-event ack list for cursors (Rule #20.3 full form; Phase 1 keeps single-
  timestamp cursors but the count is now correct).
- Topology decision D-a/D-b + per-seat worktree/index isolation (Phase 3 —
  **user-adjudicated**, Q4).

---

*Drafted by director-seat 2026-05-30 at user direction ("draft") so Phase-1 is
ship-ready the moment the operator REPLY lands. Nothing here is live; applying it
is gated on the REPLY + folding refinements.*
