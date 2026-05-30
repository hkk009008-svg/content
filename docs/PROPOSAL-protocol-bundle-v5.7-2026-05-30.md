# Protocol Bundle v5.7 — Proposal (Director Draft for Operator REPLY-Cycle)

**Subject:** Live-presence + shared-state-accuracy subsystem — closing the
"both seats keep seeing each other offline / unaware of current state" failure
the user-principal reported.

**Authored:** Director session, 2026-05-30, at explicit user-principal direction
("research what is the bottleneck and the cause and list the modifications
necessary for the protocol to achieve better communication, awareness of current
state, and better task split for prevention" → "formalize as a proposal doc,
routed through the operator REPLY cycle before any code changes"). HEAD `7eebb41`.

**Authority basis:** Cross-cutting protocol change → proposal cycle (Rule #10 +
disagreement protocol). Director-drafted at user direction (inverts the usual
operator-drafts default exactly as v5/v5.1/v5.2 did; user direction authorizes
per the Instruction-Priority hierarchy). R11 beneficiary resolves to `both` for
both proposed rules → no asymmetric-veto path; operator explicit consent
customary.

**Scope:** LARGER than the incremental v5.1–v5.3 (which each codified one
N=2 discipline rule). v5.7 is systemic — it introduces new *mechanisms*
(presence files, hook changes) + a *topology decision*, closer in character to
v4 (Lanes V/D/S) or v5 (joint-team reframe). Therefore **phased**: low-risk
Phase-1 mechanisms can ship fast post-REPLY; structural Phase-3 items
(per-seat index/worktree isolation, topology declaration) are gated on REPLY
AND possibly user adjudication.

**Ship strategy:** Phased (see §"Ship plan"). **No code changes until the
REPLY cycle completes** (per user direction). This proposal + its routing
mailbox event are the only artifacts produced now.

**Estimated effort:** Phase 1 ~30–45 min (one hook edit + presence-file scaffold
+ 2 rule codifications + registry). Phases 2–3 separately scoped at REPLY time.

**Blocks:** None additive over v5.6; the existing 18 rules are preserved. The
Phase-3 topology change is opt-in + reversible (it formalizes isolation the repo
already has machinery for in `.claude/worktrees/`).

**State at draft time:** HEAD `7eebb41` — the operator's coalesced Lane V
(READY TO SHIP on the director's Bug #4 fix `67a4096` + `138d7c7`), which landed
*during this very investigation*. That is itself a live coordination datapoint
(see §"Evidence"). `origin == HEAD`, 0 ahead / 0 behind. Operator concurrently
active. pytest **1265 passed / 3 skipped**, §15 smoke **OK**, doc anchors clean.

---

## TL;DR (90 seconds)

**The bottleneck: there is no live, shared, agent-observable presence channel.**
Each seat reconstructs "is my peer here, and what are they doing?" only at
discrete gates (session-start, pre-action, post-commit), from artifacts that are
stale-between-commits, manually-lagging, semantically-broken, local-only, or —
in the case of chat narration — *completely invisible to the other agent*
(separate session contexts; only the user sees both terminals). So **"offline"
is merely "no commit in the last 10 minutes,"** and any seat doing real
non-committing work — reading, TDD, review, thinking — trips it.

v5.7 fixes this with three mechanisms + two discipline rules:

| Goal (user's words) | Mechanism | Rule |
|---|---|---|
| Better communication | **M1** presence files (the shared FS becomes the signal bus); chat demoted to user-only | **#19** Live-presence-over-inferred-idle |
| Awareness of current state | **M2** state-accuracy fixes (unread count `to:`-filtered + content-timestamp; refresh off commit cadence; peer block in STATE.md) | **#20** Shared-state-accuracy discipline |
| Better task split / prevention | **M3** role marker + **D** topology declaration + per-seat index/worktree isolation + stale-doc reconciliation | (#19/#20 compose; D is a decision) |

**Beneficiary (R11): `both`** for #19 and #20 — symmetric obligations.

---

## Evidence (the diagnosis — every claim grounded in source, per ADR-013)

### The seven root causes

**RC1 — No presence primitive.** "Offline" is inferred from a *10-minute idle
since last commit* heuristic (`AGENTS.md:1239`, phase taxonomy "Idle" row; the
"When the other party is offline" section at `AGENTS.md:1218`). Non-committing
work is the *majority* of real work; all of it reads as idle. There is no
heartbeat / presence / liveness file anywhere (`find coordination/` → only
`README.md` + the two cursor files).

**RC2 — The primary signal channel (chat) is peer-invisible.** The signaling
rule "whoever is active first claims a shared task by stating the action in
conversation" (`CLAUDE.md`/`AGENTS.md:618`) routes through a channel **only the
human can see** — the two seats are separate processes with separate
conversation contexts. The mailbox (commit-gated, async) is the *only* real
agent-to-agent channel. So "I'm doing X" reaches the peer only if committed.

**RC3 — STATE.md is a broken awareness source** (and it is what the Rule #8
awareness gate reads):
- It is **gitignored / local-only** (`.gitignore:74`) — never shared between
  seats; each seat sees only its own hook's output.
- It refreshes **only on a HEAD move** (`update-state.sh:40-42` skip-perf gate)
  and **only after a Bash call** (`settings.local.json` PostToolUse matcher is
  `"Bash"`). A long Read/Edit/Write stretch never refreshes it.
- Its unread count is **semantically wrong**: `find sent/ -newer
  seen/<role>.txt` (`update-state.sh:77,80`) counts **both directions** (no
  `to:` filter — it includes the role's *own outgoing* events) and compares
  against the cursor **file's mtime**, not the cursor's ISO-timestamp content.
- **Observed this session:** STATE.md reported `director=4` unread when the
  genuinely-actionable count was **1** (the 4 = 3 operator→director events the
  cursor had lagged past + 1 of the director's *own* sends counted by the
  no-`to:`-filter bug).

**RC4 — Cursors lag and can't represent partial processing.** `seen/*.txt` is a
single, **manually-updated** "consumed-up-to" timestamp (`coordination/README.md:13-16`).
This session `director.txt` read `T10:23:57Z` while the prior director had
actually processed through `T11:52:06Z+`; the operator's own POST-MID-9 handoff
asserted a *third*, different value. A lagged cursor looks to the peer like
"they never saw my message."

**RC5 — Topology incoherence.** The artifacts indicate **two concurrent sessions
in one shared working tree**: a documented shared-index sweep (an 8-file director
change swept into the operator's `2c5ca05` — recorded in memory
`feedback_shared_index_sweep_use_pathspec`), a single `main` worktree
(`git worktree list`), and a single shared `settings.local.json`. Yet the rules
are written for **separate clones synced via origin** ("operator reads origin,"
"push so operator sees it," `coordination/README.md:130` "Per-clone setup").
**Rules designed for the wrong physical model are ambiguous and partly inert** —
e.g., the entire `git commit -- <pathspec>` workaround exists *only* because of
the shared index that the "separate clones" model says shouldn't exist.

**RC6 — No persistent role identity.** A session knows it is "director" only
because the user typed it (this session began "...as director to continue"). No
env var or marker file establishes role (grep across `.claude/` found none).
Risk: both seats default to the same role, or a cold session acts role-less.

**RC7 — The coordination docs are themselves stale.** `coordination/README.md`
still says "Rules 1–8" (`:5,:20`; we are at #18) and its "Known limitations
(v2.1)" section (`:111-128`) describes the `git commit --amend` STATE.md-fold
model that **B-003 Option E retired** (`update-state.sh:5-14` explicitly: "the
hook never touches git history" now). The how-to-coordinate reference misleads.

### The live counter-datapoint (intellectual honesty)

While this investigation was in progress, the operator picked up the director's
Bug #4 fix (`67a4096`) *from origin*, ran a coalesced Lane V, and pushed
`7eebb41` (READY TO SHIP) — a clean, correct coordination loop. **The loop works
on the happy path** (both seats commit + push + pull + check the mailbox at the
right gates). The user's reported "offline" failures are therefore not "the loop
never works" — they are the **gaps**: the stretches where one seat is working
without committing (RC1), reading a frozen/local STATE.md (RC3), trusting a
lagged cursor (RC4), or relying on chat the peer can't see (RC2). v5.7 targets
the gaps, not the happy path.

---

## Proposed mechanisms (specs — NOT implemented in this proposal)

### M1 — Presence files (new shared artifact)

New directory `coordination/presence/` with `director.md` and `operator.md`.
Each is small and rewritten by its owning seat frequently (every turn / tool
batch):

```markdown
---
seat: director
status: active            # active | wrapping | away
current_task: "drafting v5.7 proposal; no shared-file writes in flight"
head_at_write: 7eebb41
updated: 2026-05-30T00:45:00Z
---
(optional one-line free text)
```

The peer reads the *other* file to answer "alive? doing what? against which
HEAD?" in one read — replacing inference from commit recency + mailbox
archaeology. **These files are NOT committed** (they are real-time, local to the
shared tree, and would otherwise churn history); they are `.gitignore`d like
STATE.md. Freshness = file mtime.

### M2 — State-accuracy fixes (`update-state.sh`)

1. **Correct the unread count:** filter sent events by `to: <role>` (frontmatter
   parse) AND compare the sent file's **filename-timestamp** to the cursor's
   **content** ISO-timestamp (drop the `-newer` mtime hack). This alone
   eliminates the `director=4`-vs-1 class.
2. **Refresh off the commit cadence:** fire the hook on `Write|Edit` too (not
   only `Bash`), OR have the Rule #8 gate **recompute unread live** rather than
   trust the frozen snapshot.
3. **Add a "Peer" block** to STATE.md sourced from M1 (peer status +
   current_task + freshness), turning STATE.md from a local-git snapshot into a
   genuine situational board.

### M3 — Role marker

A `CLAUDE_SEAT=director|operator` env (per-session) and/or presence-file
existence (M1) so a session establishes its role without the user's opening
phrasing. Cold sessions self-identify; "both seats think they're director" is
prevented structurally.

### D — Topology declaration + doc reconciliation (Phase 3, gated)

Declare the **actual** topology and align every rule to it. Two coherent options:
- **D-a (recommended): shared tree + per-seat isolation.** Keep the shared
  object store but give each seat its own **git worktree** (machinery already in
  `.claude/worktrees/`) or its own `GIT_INDEX_FILE`. This **eliminates the
  shared-index sweep class and the STATE.md clobber** while preserving a shared
  history, and makes the "reads origin / push so peer sees" language *correct*.
- **D-b: fully shared tree.** Keep one index but delete the separate-clone
  language and lean entirely on `git commit -- <pathspec>` + per-seat state
  files.

Plus: fix `coordination/README.md` (Rules 1–8 → current; delete the retired
`--amend` "Known limitations v2.1" section). This is doc work, owned per Lane D.

---

## Proposed rules

### Rule #19 — Live-presence-over-inferred-idle
*(Subtitle: read the peer's presence, don't guess from commit silence; bind via artifacts, not chat.)*

1. Each seat maintains its `coordination/presence/<seat>.md` (M1), updated at
   least once per turn it is active.
2. **Liveness is read from presence-file freshness + `current_task`**, NOT from
   the 10-minute commit-idle heuristic. "Offline" = presence stale > a threshold
   T (proposed default 10 min of *no presence update*, not *no commit*).
3. **Any binding cross-seat signal MUST be an artifact** (a mailbox event or a
   presence-file update), never chat narration alone — chat is for the
   user-principal, who is the only party that can see both. (This supersedes the
   implicit "narrate in conversation" reliance in Rule #2 §Signaling; Rule #2's
   narration is retained as a *user-facing* courtesy, not a peer channel.)

**Beneficiary (R11): `both`** — symmetric. Both seats gain accurate peer-liveness;
both owe presence-file maintenance.

### Rule #20 — Shared-state-accuracy discipline
*(Subtitle: the awareness gate computes truth, it doesn't trust a stale snapshot.)*

1. The Rule #8 session-bootstrap awareness gate (and any mid-session unread
   check) **recomputes the unread count live** — `to: <me>`-filtered,
   content-timestamp-compared — rather than trusting STATE.md's possibly-frozen
   field. STATE.md remains a convenience cache; the gate verifies.
2. The unread mechanism (M2) is the canonical implementation; until it ships,
   seats **reconcile STATE.md against the filesystem** before acting on its
   count (this is already Rule #8 §F "filesystem wins," here made a positive
   step, not a fallback).
3. Cursors support **per-event acknowledgment** (an acked-list or `ack:` marker),
   so "processed A, deferred B" is representable and the single-timestamp lag
   (RC4) cannot recur. Cursor advance is part of *processing* an event, verified
   at session-wrap.

**Beneficiary (R11): `both`** — symmetric.

---

## Working criteria (dogfood for v5.8 retro)

- **C1** — any v5.7 artifact (presence file, hook change, rule edit) cites
  "v5.7" / "Rule #19" / "Rule #20" so adoption is grep-auditable.
- **C2** — after M2 ships, a deliberately-lagged cursor + a self-addressed event
  produce a *correct* unread count (regression test for the `to:`-filter +
  content-timestamp fix). Measurable.
- **C3** — "offline" misfires drop: over a cycle, count instances where a seat
  declared the peer offline/idle while the peer's presence file was fresh < T.
  Target: → 0 after Rule #19.
- **C4** — no shared-index sweep recurs after D-a (per-seat index/worktree).
  Measurable by absence of `git commit -- <pathspec>` *rescues* in commit bodies.

---

## Open questions for the operator REPLY-cycle (with director's recommended answers)

**Q1 (presence cadence vs. cost).** Every-turn presence rewrites add a small
per-turn write. Acceptable, or throttle (e.g., only on status/current_task
*change*)? **Rec:** rewrite on change OR every-Bash via the existing hook (near-zero
marginal cost since the hook already runs on Bash).

**Q2 (presence committed or not).** I propose presence files are gitignored
(real-time, would churn history). Counter-view: committing them gives a durable
audit of "who was doing what when." **Rec:** gitignored for the live signal;
the durable record already lives in the mailbox + git log. Operator may counter.

**Q3 (liveness threshold T).** 10 min of no *presence update* (vs the current 10
min of no *commit*). Right value? **Rec:** 10 min to start; tune empirically.

**Q4 (topology decision D-a vs D-b).** This is the consequential one and may
warrant **user adjudication** rather than seat-only consent. Per-seat worktrees
(D-a) is the higher-leverage fix but the bigger operational change. **Rec:** D-a,
but flag to the user-principal before implementing (it changes how both sessions
are launched).

**Q5 (phasing).** I propose Phase-1 = M1 + M3 + M2(unread-count) + Rule #19/#20
text; Phase-2 = M2(peer block + refresh-cadence); Phase-3 = D + doc
reconciliation. Agree, or re-bucket? **Rec:** as stated; Phase 1 is low-risk and
directly kills the reported symptom.

**Q6 (who implements).** Phase 1 touches `update-state.sh` + new files + 2 rule
edits across CLAUDE.md/AGENTS.md — a ≥3-file change spanning a hook + the
protocol docs. Director-driven (Lane B) or operator-driven-eligible (Rule #14)?
**Rec:** director-driven given it touches the protocol-doc truth surface; operator
runs Lane V. Operator may claim Phase-1 hook work under Rule #14 if it fits the 5
criteria.

---

## Ship plan (phased; nothing ships before REPLY)

1. **This commit:** v5.7 proposal doc + routing mailbox event. No code.
2. **Operator REPLY** (their next active window): address Q1–Q6, R11 `both`
   consent or counter, per the disagreement protocol (≤2 cycles then user
   adjudicates).
3. **Phase 1 ship** (post-REPLY): M1 + M3 + M2(unread-count) + Rule #19/#20 into
   CLAUDE.md / AGENTS.md / PROTOCOL-RULES-LOG.md + presence scaffold. Operator
   Lane V.
4. **Phase 2/3:** as scoped at REPLY; D gated on user adjudication (Q4).

---

## Race-ack (Rule #5 + #7)

**State at write-start:** HEAD `7eebb41` — and that commit is itself the proof
the Rule #4 pre-Write gate works: it caught the operator's Lane V landing
(`81fd623 → 7eebb41`) *during* this investigation, before I wrote a word of this
file. origin == HEAD, 0/0. The operator is concurrently active; further operator
commits during the REPLY window are expected and concurrent-safe (proposal docs
+ REPLY events don't contend). **Pre-commit Rule #7 gate:** re-verify
`git log --oneline -5` immediately before the proposal commit; race-ack body if
HEAD moved.

## Cursor advance

`coordination/mailbox/seen/director.txt`: advances `T14:45:34Z → T00:37:53Z`
(consumes the operator's `7eebb41` Lane V verification-report; dispositions:
M-B NO ACTION, M-A DEFER with (b)-guard recommendation). Handled in the routing
commit, not here.

## Next actions

1. Director: commit this proposal + route to operator (one `proposal` mailbox
   event that also acks Lane V `7eebb41`) + advance cursor.
2. Operator: REPLY (Q1–Q6 + R11 consent).
3. Both: Phase-1 ship post-REPLY; D gated on user (Q4).

---

## Sign-off

Director-seat, 2026-05-30, at user-principal direction. The reported failure —
"both seats keep seeing each other offline and unaware of current state" — is
real and has a single deepest cause (**no live, shared, agent-observable
presence channel**) plus six compounding ones, all grounded in source above.
v5.7 proposes the minimum that closes the gaps: a presence subsystem (Rule #19),
a state-accuracy discipline (Rule #20), a role marker, and a topology
declaration that ends the shared-tree-vs-separate-clone incoherence. Phase 1 is
low-risk and directly addresses the symptom; the structural topology change is
flagged for user adjudication. Beneficiary `both` for both rules — symmetric,
no veto path; operator consent customary. Routed for operator REPLY before any
code changes, per user direction.

Signed,
Director-seat — 2026-05-30 (v5.7 proposal drafted per user direction).
