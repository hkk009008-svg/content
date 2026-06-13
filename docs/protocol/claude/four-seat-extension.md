# Four-seat coordination — protocol extension (DRAFT for director ACK)

**Status:** DRAFT · operator-authored 2026-06-13 per user directive ("scale 2→4
seats for speed"). Gated on **director ACK before the tooling cutover lands**
(the coordination tooling + working tree are shared and live).

**Principle: additive + backward-compatible.** No existing seat is renamed. The
two current seats keep their exact identifiers, indexes, cursors, presence files,
and launch. The change is purely additive — two new seats plus a wider event
vocabulary. Every intermediate state of the cutover keeps `ci_smoke` green so the
live `director` session is never broken.

---

## 1. Seat model

Canonical seat IDs become a 4-set: **`director`, `director2`, `operator`,
`operator2`** — where `director`/`operator` ARE seat-1 (unchanged). Two **pairs**:

| Pair | Director | Operator | Owns |
|------|----------|----------|------|
| **A** | `director`  | `operator`  | lane A (a subsystem stream) |
| **B** | `director2` | `operator2` | lane B (a disjoint subsystem stream) |

The director↔operator relationship (strategy/briefs vs independent verification)
is **unchanged within each pair** — we duplicate the proven two-seat unit, we do
not invent a new role. "Two seats of one team" becomes "four seats / two pairs of
one team"; user is still principal; **git is still the tiebreaker** (first commit
to land wins) at any boundary.

## 2. Launch (additive — README §"Per-seat launch" gets two more stanzas)

```bash
# director2 session (new terminal, SAME shared tree)
cd /Users/hyungkoookkim/Content
export CLAUDE_SEAT=director2
export GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-director2"
[ -f "$GIT_INDEX_FILE" ] || git read-tree HEAD   # seed per-seat index from HEAD
claude

# operator2 session (new terminal, SAME shared tree)
cd /Users/hyungkoookkim/Content
export CLAUDE_SEAT=operator2
export GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-operator2"
[ -f "$GIT_INDEX_FILE" ] || git read-tree HEAD
claude
```

## 3. Presence / heartbeat / index — **NO hook change required**

`.claude/hooks/update-state.sh` is already seat-generic:
- `_stamp_presence()` stamps `coordination/presence/${CLAUDE_SEAT}-heartbeat.ts`
  for *any* seat → `director2`/`operator2` auto-stamp on launch.
- `_sync_seat_index()` / `_clear_skip_worktree()` key off `$GIT_INDEX_FILE` →
  `index-director2`/`index-operator2` are maintained automatically.

The ONLY hook touch is **cosmetic**: the STATE.md unread report
(`_unread_for director`/`operator`, lines 207–211) should list all four seats.
Not load-bearing (each seat reads its own cursor via `consume-events`).

## 4. Mailbox addressing — point-to-point **+ a broadcast target**

Any seat may address any other seat directly (`<from>-to-<to>-<kind>.md`). A new
pseudo-target **`all`** lets a seat announce to everyone (lane claims, "I'm
online", cutover notices) without sending N copies. `all` is a valid `to` only —
never a `from`, never a real cursor/seen file.

**The seat vocabulary lives in FOUR code spots — they MUST change together:**

| File | What changes |
|------|--------------|
| `coordination/bin/send-event` | `FROM` enum → `director\|director2\|operator\|operator2`; `TO` enum → same **+ `all`** |
| `coordination/bin/consume-events` | `ROLE` enum → 4 seats; `addressed()` grep → `-to-(${ROLE}\|all)-` |
| `scripts/check_coordination.py` | `ROLES` → 4-tuple; `_EVENT_NAME_RE` `frm`→4 seats, `to`→4 seats **+ `all`**; orphan check `m.group("to") in (role, "all")` (line 116) |
| `scripts/status.py` | `_EVENT_RE` `to`→4 seats + `all`; `count_unread` line 81 → `if event_to != seat and event_to != "all": continue` |

(`all` is NOT added to `ROLES` — there is no `seen/all.txt`; it is only a `to`
target that every real seat counts as addressed-to-it.)

## 5. Cursors

Create two new watermark files, seeded with a safe past timestamp so the linter's
`cursor_missing` (FATAL) and `cursor_orphan` (ADVISORY) both pass for a seat with
zero events yet (`addressed` is empty → orphan check is skipped):

```
coordination/mailbox/seen/director2.txt   <- 2026-06-13T00:00:00Z
coordination/mailbox/seen/operator2.txt   <- 2026-06-13T00:00:00Z
```

## 6. Work partitioning (the actual speed lever)

- **Pair lanes.** Pair A and Pair B each own a **disjoint subsystem lane**; the
  paired director briefs, the paired operator independently verifies — exactly
  the current loop, run twice in parallel.
- **Tiebreaker unchanged.** `git log --oneline -3` before acting on a shared
  task; first commit to land wins. With four seats the per-seat `GIT_INDEX_FILE`
  already isolates staging; commits serialize on git's ref lock.
- **Lane discipline (NEW Rule).** A seat does substantive work only in its lane.
  Cross-lane edits require a `-to-all-` heads-up first (or a direct dispatch-claim
  to the owning pair). Pathspec-scoped commits remain load-bearing.
- **Architectural decisions (NEW Rule).** A lane-local ADR is owned by that
  lane's director. A **cross-cutting / cross-lane ADR needs BOTH directors'
  sign-off** (a `director-to-director2` proposal + `proposal-reply` ack), or
  escalate to the user. Prevents two directors landing conflicting architecture.

## 7. Rules deltas (docs/protocol/claude/director-operator.md)

Most of #7–#22 scale unchanged (they are per-seat). Touch points:
- Framing: "two seats" → "four seats / two pairs"; user still principal.
- Rule #8 (mailbox binds receiving seat): now per-seat across 4 + `all` events
  bind every seat.
- Rules #19/#20 (presence): four presence + four heartbeat files.
- **NEW Rule #23 — lane ownership** (§6 lane discipline + cross-director ADR).

## 8. Cutover sequence (safe-ordered — keeps ci_smoke green at every step)

The working tree is SHARED, so each edit is live for the peer the instant it is
written. Order the cutover so no intermediate state can FATAL the peer's smoke:

1. **Create the two `seen/*.txt` cursors** (harmless — unreferenced until ROLES
   widens).
2. **Widen the four vocabulary spots together** (send-event, consume-events,
   check_coordination, status.py) + the cosmetic hook unread.
3. **Add a regression test** (`tests/unit/test_four_seat_coordination.py`):
   a `director2→operator2` event + an `all` broadcast lint clean, `count_unread`
   counts `all` for every seat, and `consume-events operator2` advances.
4. **Run `scripts/ci_smoke.py`** → must stay green (it runs check_coordination).
   Round-trip a real `director2→operator2` test event through send/consume.
5. **README launch stanzas + this doc** flipped to ACCEPTED.
6. **Commit** the whole cutover via explicit pathspec, one commit.

## 9. Rollback

`git revert` the cutover commit. Backward-compatibility means the 2-seat world is
untouched by the extension, so a rollback is clean and the live `director`/
`operator` seats are unaffected either way.

---

**Director ACK requested on:** (a) the seat IDs (`director2`/`operator2` vs a
different scheme), (b) the `all` broadcast target (include now vs defer to v2),
(c) the pair-lane partition + the cross-director ADR rule, (d) any constraint on
WHEN the (backward-compatible) tooling swap lands. On ACK I apply §8 and notify
with launch instructions; nothing live moves before then.
