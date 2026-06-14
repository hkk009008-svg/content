# Four-seat coordination — protocol extension

**Status:** TOOLING LANDED 2026-06-13 (user-authorized "proceed now") ·
operator-authored per user directive ("scale 2→4 seats for speed"). The
backward-compatible tooling cutover (§8) is **applied + verified** — `ci_smoke`
green, regression test `tests/unit/test_four_seat_coordination.py` (6 cases:
Pair-B + `all` lint clean, `count_unread` broadcast, bin round-trip). `director2`
/`operator2` are LIVE (launched 2026-06-13T08:50Z; both heartbeating, indexes
seeded). **Lanes FINAL** (PRINCIPAL-CONFIRMED 2026-06-13): Pair A = image-gen +
identity/realism, Pair B = video + assembly + delivery (§1 table + §6). Status:
**ACCEPTED.**

**Principle: additive + backward-compatible.** No existing seat is renamed. The
two current seats keep their exact identifiers, indexes, cursors, presence files,
and launch. The change is purely additive — two new seats plus a wider event
vocabulary. Every intermediate state of the cutover keeps `ci_smoke` green so the
live `director` session is never broken.

---

## 1. Seat model

Canonical seat IDs become a 4-set: **`director`, `director2`, `operator`,
`operator2`** — where `director`/`operator` ARE seat-1 (unchanged). A `coordinator` broadcast role also exists for cross-seat signaling. Two **pairs**:

| Pair | Director | Operator | Lane (PRINCIPAL-CONFIRMED 2026-06-13, FINAL) |
|------|----------|----------|------|
| **A** | `director`  | `operator`  | **Image-generation + identity/realism** — `pulid*.json`, `quality_max.py`, `workflow_selector` image params, `identity/validator.py` + the arc scorer, and the data-integrity lane (production PuLID SDXL→FLUX fix + the unrouted siblings `continuity_engine.py:181`, `character_manager.py:396`). |
| **B** | `director2` | `operator2` | **Video + assembly + delivery** — `phase_c_ffmpeg.py`/`phase_c_assembly.py` video paths, video-API selection (Veo/Kling/LTX/Sora/Runway), lip-sync, dialogue/TTS, `cinema/shots` sequence-level continuity, `web_server`/`cinema_pipeline` orchestration. |

**Shared seams** (`phase_c_assembly`, `workflow_selector` touch both image + video):
owner = whoever's specific change-lane the edit is in, with a `-to-all-` heads-up
first per Rule #23.

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
| `coordination/bin/send-event` | `FROM` enum → `director\|director2\|operator\|operator2\|coordinator`; `TO` enum → same **+ `all`** |
| `coordination/bin/consume-events` | `ROLE` enum → 4 seats + coordinator; `addressed()` grep → `-to-(${ROLE}\|all)-` |
| `scripts/check_coordination.py` | `ROLES` → 5-tuple; `_EVENT_NAME_RE` `frm`→5 roles, `to`→5 roles **+ `all`**; orphan check `m.group("to") in (role, "all")` (line 116) |
| `scripts/status.py` | `_EVENT_RE` `to`→5 roles + `all`; `count_unread` line 81 → `if event_to != seat and event_to != "all": continue` |

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

- **Pair lanes (FINAL — see the §1 table).** Pair A = **image-generation +
  identity/realism**; Pair B = **video + assembly + delivery**. Each pair's
  director briefs, its operator independently verifies — the current loop, run
  twice in parallel. Disjoint by construction; shared seams handled per Rule #23.
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
- **Co-sign tiers (Lever #7, audit `wf_6be2ee18-f4b`).** The cross-director
  co-sign is **tiered** so an awareness heads-up does not serialize behind a full
  session. Classifier: *would the co-signer's own verification change which files /
  sites the implementation touches?*
  - **Tier A — implementation-scope-determining** (yes): the co-signing director
    MUST run an independent verification (e.g. a downstream string-consumer audit
    the brief's caller-grep can't see — the landscape co-sign caught a 4K-drop +
    silent-audio regression this way) and land a mailbox `verification-report`
    **before dispatch**. This is fulfillable **async** via a workflow + mailbox
    report — NO session restart required; it just must precede the implementer
    dispatch.
  - **Tier B — awareness-only** (no): a `-to-all-` or direct heads-up with a
    **48h proceed-if-no-objection** default (already the de-facto practice — e.g.
    the determinism-siblings ACK round-tripped in <10 min).
  When unsure which tier, treat it as Tier A (the safe default).

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

## 10. Coordinator — on-demand policy (Lever #8, audit `wf_6be2ee18-f4b`)

The `coordinator` is a 5th, read-only, cross-pair oversight pseudo-seat — **NOT a
standing concurrent seat**. Standing-concurrent operation consumes the working
seats' attention and duplicates findings already queued; the value is the
cross-pair view, not the constant presence. (This is the on-demand framing of the
`coordinator` broadcast role mentioned in §1.)

- **Trigger.** Spawn on demand at a **multi-pair-wrap boundary** (both pairs
  wrapped the same day) when the user or a director wants a cross-pair audit — the
  high-collision regime where cross-pair stale-state accumulates fastest.
- **Posture.** UNPINNED: no `CLAUDE_SEAT`, no `GIT_INDEX_FILE`. Read-only by
  default; owns no lane (Rule #23-inert).
- **Output.** Land findings as a **single** findings/doc commit (or one mailbox
  event) — not a stream of per-finding events. The send-only `coordinator` mailbox
  vocab (`fd334d3`) stays valid for this but is used sparingly.
- **Commits.** "Read-only" means read-only on **production code** — never authors a
  behavior-changing fix. The coordinator **MAY** commit (explicit pathspec, via a
  seeded `.git/index-coordinator`) the **spec §6a "may commit" scope**: test-only
  artifacts (xfail pins, fixtures, stubs), the inventory, docs, `logs/`, and
  coordination tooling — these do NOT each need per-commit user direction. A
  permitted commit must NOT change a gate's PASS/FAIL outcome or write a
  suppressive/vacuous xfail (that is a behavior-changing fix in disguise — equally
  forbidden). **Push stays USER-gated** in all cases.
