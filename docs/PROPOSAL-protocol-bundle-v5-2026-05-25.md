# Protocol Bundle v5 — Proposal (Operator Draft for Director Ship)

**Authored:** Operator session, 2026-05-25 — drafted at user direction with explicit "director and operator as one team" framing. Comes after a substantive user-level structural critique of the v1-v4 role partition (preserved inline in this proposal's §"Why v5: the user critique" section).
**Revised:** Operator session, 2026-05-25 — incorporating director's REPLY at `642250d`: accepting R-E-1 (emergency criteria definition) and C-D-1 (2-cycle counting clarification), plus 8 of 8 open-question answers. No counter-refinements; all 8 locked decisions stand under sharpening.
**Authority basis:** `ad6cb4f` "operator drafts; director commits" carve-out (same lineage as v2 `1b3f6f8` revise → `416d610` ship; v3 `ec1e64e` revise → `3340d1f` ship; v4 `4fdcc01` revise → `d61bdc8` ship; v4.1 `509db7c` ship).
**Ship strategy:** Single commit, all components together. Race-ack body if state moves during ship.
**Estimated implementation effort:** ~45-60 min (larger than v4 due to philosophical reframe + 7 new components; mostly markdown across CLAUDE.md, AGENTS.md, PROTOCOL-RULES-LOG.md, coordination/README.md + 2 new doc files).
**Blocks:** None. v5 is additive over v2/v3/v4/v4.1 — nothing currently working breaks; existing role partition is REFRAMED, not deleted.
**State at draft time:** HEAD `509db7c` (v4.1 ship). Recent cycle-6 commits include `9e24323` fix-web (director addressing operator's S13 Lane V F1+F2 findings — empirical one-team dynamic), `e1b72ca` Session 14 feat-schema, and operator's `1e29610` Lane D §7.7 backfill. Working tree clean; mailbox empty both directions.
**State at revision time:** HEAD `642250d` (director's REPLY commit). Branch 2 ahead of `origin/main` (operator's `2e06fe1` proposal + director's `642250d` REPLY, both unpushed per cycle precedent). Working tree clean; mailbox empty both directions.

---

## TL;DR (60 seconds)

User direction (2026-05-25): **"director and operator as one team — optimize and focus on that framing."** Comes after a structured critique of the role partition that surfaced several gaps:

| User-surfaced concern | v5 component |
|---|---|
| "Shared category is large; partition does less than the structure suggests" | **Sh** — codify de facto practice (implementer dispatch = director's lane) |
| "Director-load asymmetry creates bottleneck when transplant cycles hit" | **E** — emergency handling protocol with seat-temporary-authority |
| "Operator drafts blind; doesn't know what's been considered/rejected" | **R11** — codification bias check at REPLY time + **B** — backlog as shared visible workspace |
| "Memory writes director-only creates latency for operator-observed memory candidates" | **M** — `memory-candidate` mailbox kind |
| "No protocol for substantive disagreement" | **D** — codify the v4 R-V1 counter precedent + user-escalation path |
| "Codification meta-bias: director makes rules that bind themselves" | **R11** — per-rule "primary beneficiary" check at REPLY time |
| "Missing partition: out-of-scope work backlog" | **B** — backlog partition |

Plus the philosophical reframe driving all the above:

| # | Item | What it does | Type |
|---|---|---|---|
| **P1** | **Philosophical reframe**: director + operator are TWO SEATS of ONE TEAM with different specializations, both serving the user-principal. Asymmetry is cognitive-load distribution, not senior/junior hierarchy. | Foundation |
| **R10** | **Rule #10: Joint-team mode** — codifies the philosophy as discipline. Both seats equal in authority within their specialization; user is the only superior. | Discipline rule |
| **R11** | **Rule #11: Codification bias check** — when codifying a new rule, codifier flags "primary beneficiary" (director-seat / operator-seat / both); the non-beneficiary seat has explicit review-veto in REPLY cycle. | Discipline rule |
| **D** | **Disagreement protocol** — generalizes v4's R-V1 counter precedent. Operator-counter-refinement is a first-class REPLY response; if disagreement persists after 2 cycles, escalate to user (the principal). | Mechanism |
| **E** | **Emergency handling protocol** — first-noticer claims initial response; if normal-seat unavailable (transplant, context exhaustion), other seat has temporary authority on emergencies. Triage discipline: stop-the-bleed first, attribution later. | Mechanism |
| **B** | **Backlog partition** — `docs/BACKLOG.md` (NEW) as shared-visible workspace for "interesting but not cycle-N" items. Either seat can add; director typically curates but operator can claim items per Lane D-style discretion. | Mechanism |
| **M** | **Memory-candidate mailbox kind** — operator surfaces memory-worthy observations via mailbox; user makes final write decision (memory persists across sessions; user is principal). Closes the latency concern without changing write authority. | Mailbox extension |
| **S** | **Lane S activation** (was scaffolded in v4 for v5+) — pre-dispatch scout: operator surveys named targets when director sends `scout-request`, returns `scout-report` with intel director can paste into implementer prompts. | Mechanism (activate scaffold) |
| **Minor** | Codify de facto practice: implementer dispatch (Lane B) = **director-seat-only**, not "Shared". Matches 12+ sessions of observed ownership. Reduces label/practice gap. | Convention update |

---

## Why v5: the user critique (preserved inline)

The user's 2026-05-25 critique of the role partition is the foundation for v5. Key claims, with operator's evidence-grounded response in italics:

1. **"The Shared category is large and includes high-frequency operations. Each shared operation requires the coordination rules to fire. Protocol overhead is paid per shared operation."**
   *Agree, with nuance: most "Shared" operations have de facto ownership (director claims every Lane B; operator claims every Lane V). The partition is over-permissive; practice converges on owners. v5 codifies what's already true.*

2. **"Director-only includes strategic + operational; Operator-only is mostly operational maintenance. This creates a bottleneck if Director is in transplant."**
   *Agree. The emergency handling gap (E) is real and observed: in a transplant moment, if a bug hits prod, the operator currently has no protocol to act on it without director authorization.*

3. **"Memory writes Director-only adds latency for operator-observed knowledge capture."**
   *Agree. The memory system in this project is user-authorized; operator can suggest but not write. v5's `memory-candidate` mailbox kind (M) closes the latency without changing write authority.*

4. **"Operator may draft, Director ships — the drafting Operator may not know what's already been considered and rejected; they spend cycles on rules that won't ship."**
   *Partially agree. Empirically: v2/v3/v4/v4.1 all shipped operator drafts (100% ship rate to date). But the user's point about silent self-suppression (operator only drafts what they think will pass) is untestable from inside and may be real. v5's backlog (B) and codification bias check (R11) make the visible state of "considered" larger, reducing blind drafting.*

5. **"If both roles can run verification gates, who's responsible when a verification gate is skipped?"**
   *Hasn't surfaced empirically but the structural concern stands. v5 doesn't directly address this — leaves it for v5.1+ once data accumulates. Marked as v5-acknowledged not-codified.*

6. **"Two instances generating closing reports in parallel waste tokens regardless of who wins the commit."**
   *Empirically closing reports are partitioned by document (director-transplant vs operator-transplant). The "Shared" label is wrong; practice is partitioned. v5 minor (Sh) corrects the label.*

7. **"Director codifies rules that bind themselves. This creates selection bias."**
   *Empirically Rules 4/6/8/9 lean operator-friendly; the bias hypothesis isn't borne out in the data. BUT the user noted this is hard to test from inside (silent self-suppression). v5's R11 (codification bias check) makes the bias EXPLICITLY assessable per-rule.*

8. **"Missing: emergency handling, out-of-scope work backlog, substantive disagreement resolution."**
   *Agree on all three. E (emergency), B (backlog), D (disagreement) target each in turn.*

The user's closing framing — "the partition isn't optimal in the sense of zero friction, but it's reasonable given the constraint of running two instances of the same model with asymmetric authority" — is correct. v5 doesn't claim to eliminate the friction; it shifts the framing so the friction is between specializations, not between hierarchy tiers.

---

## P1 — Philosophical reframe (foundation)

**Current framing (v1-v4):** Director-only / Operator-only / Shared. Implicit senior/junior asymmetry — director gets strategic + operational; operator gets operational maintenance.

**v5 framing:** Director and operator are **two seats of one team**, with different specializations. Both serve the user-principal. Neither is senior to the other; both are co-agents.

**Specialization rationale:**

| Seat | Specializes in | Why this seat? |
|---|---|---|
| **Director-seat** | Strategic synthesis: brief authoring, ADR composition, push decisions, post-roadmap reassessment, cross-cycle planning, codifying discipline | Strategic work requires synthesizing cross-cycle context; director's session context preserves cycle-spanning state |
| **Operator-seat** | Operational verification: post-commit Lane V reviewer dispatch, Lane D doc-sync, transplant-handoff refresh, counter-bump dispositions, mailbox event authoring | Operational work requires cold-context independence (Rule #9); operator's session is naturally orthogonal to director's |

**Both seats are equal in authority within their specialization.** Within Lane V/D/S, operator-seat acts unilaterally (mailbox events bind director per Rule #8). Within strategic work (briefs, ADRs, push), director-seat acts unilaterally (operator-seat acknowledges via mailbox or commit body). Cross-cutting decisions (protocol changes themselves, role-partition adjustments) go through the proposal cycle.

**User is the principal.** Both seats serve the user; neither is the boss of the other. When agents disagree, escalate to user (per D below). When user direction is given, it overrides any agent's discretion (per existing CLAUDE.md "Instruction Priority").

**What this REPLACES from prior partitions:** the "senior/junior" implication. Operator is NOT junior; operator is specialized. The "Director-only / Operator-only / Shared" labels stay but are reframed as "Strategic-seat-default / Operational-seat-default / Cross-cutting (proposal cycle)."

**What stays the same:** specific lane assignments (Lane V/D/S = operator-seat; brief authoring = director-seat); the proposal cycle for protocol changes; user as principal.

**Edit anchor:** New subsection `## Director-operator: two-seat team model (v5)` at the top of CLAUDE.md / AGENTS.md `# Director-Operator Concurrent Operation`, BEFORE the existing role-partition table. Updates role partition table labels in-place.

---

## R10 — Rule #10: Joint-team mode

Add to PROTOCOL-RULES-LOG.md rule registry and CLAUDE.md/AGENTS.md `# Director-Operator Concurrent Operation`:

> **Rule #10: Joint-team mode.** Director-seat and operator-seat are two seats of one team. Both serve the user-principal. Neither is senior to the other; specialization is cognitive-load distribution, not hierarchy.
>
> **Practical implications:**
> - Within their specialization lane, each seat acts unilaterally (no cross-seat approval needed for in-lane work).
> - Cross-cutting decisions (protocol changes, role-partition adjustments) go through the proposal cycle.
> - When agents disagree on a cross-cutting decision after 2 REPLY cycles, escalate to the user (per Rule #12 / D below).
> - When user direction is given, it overrides agent discretion (per existing CLAUDE.md "Instruction Priority").
> - Both seats use the same commit-body etiquette + Rule #7 pre-commit re-verify + Rule #5 race-ack — these are TEAM disciplines, not seat-specific.
>
> **Why this matters:** the v1-v4 partition implied senior/junior asymmetry. Empirically, operator-seat's verification work (Lane V S13 finding F1 CRITICAL) directly influenced director-seat's fix (`9e24323`). The team dynamic was already real; v5 codifies the framing.

**Codified SHA placeholder:** `_Protocol Bundle v5 ship_` until v5 ships; then operator updates per chicken-and-egg pattern.

---

## R11 — Rule #11: Codification bias check

When proposing a new rule (in any protocol bundle), the codifier MUST flag the rule's **primary beneficiary** in the proposal:

- `beneficiary: director-seat` — rule primarily reduces director-seat's friction or expands director-seat's authority
- `beneficiary: operator-seat` — rule primarily reduces operator-seat's friction or expands operator-seat's authority
- `beneficiary: both` — rule is symmetric (e.g., Rule #2 signaling applies to both)
- `beneficiary: user` — rule primarily benefits the user-principal (e.g., Rule #8 mailbox authority closes user-as-relay bottleneck)

**REPLY-cycle implication:** if `beneficiary` is asymmetric (director-seat or operator-seat alone), the OTHER seat has explicit veto in the REPLY cycle. If the non-beneficiary seat declines to consent, the rule is downgraded to "advisory" status or revised until both seats consent.

**Retroactive analysis** (operator-conducted; surfaced for v5 audit):

| Rule | Primary beneficiary | Reasoning |
|---|---|---|
| 1 (Role partition) | both | partitions work for both seats |
| 2 (Signaling) | both | both narrate |
| 3 (Git tiebreaker) | both | resolves races for both |
| 4 (State-asserting writes precondition) | operator-seat | catches stale handoff writes (operator-only territory) |
| 5 (Race-acknowledging commit body) | both | both write commits |
| 6 (Counter-bump fold-and-surface) | operator-seat | counter bumps are operator-only |
| 7 (Pre-commit re-verify) | both | both commit |
| 8 (Mailbox authority) | user | closes user-as-relay bottleneck for both seats' inter-session signals |
| 9 (Operator-side reviewer is independent) | operator-seat | enables operator-seat's Lane V |

**Observed distribution:** 4 both, 1 user, 3 operator-seat, 0 director-seat. Bias hypothesis from user's critique not borne out — codification has been operator-friendly because operator-seat surfaces races (they're in the operational layer where races occur). R11 makes this explicit and per-future-rule auditable.

**Edit anchor:** Add the `beneficiary:` field to v5's proposal frontmatter (and all future proposals); add Rule #11 to rule registry; add a "Beneficiary distribution snapshot" subsection to PROTOCOL-RULES-LOG.md's invocation log.

---

## D — Disagreement protocol

Generalizes v4's R-V1 counter precedent. When operator-seat disagrees with a director REPLY refinement (or vice versa), the disagreeing seat:

1. **States the disagreement explicitly** in the next-cycle revision with reasoning (operator: v4 §"Operator counter-refinement to R-V1" was the precedent; director: equivalent section in next REPLY)
2. **Provides project-data-grounded evidence** (the R-V1 counter cited Session 10's 36-LOC feat as data; ungrounded "I don't like it" is not sufficient)
3. **Proposes one of three resolutions:**
   - **Counter-refinement** — adjust the disputed item per the data
   - **Defer to v(N+1)** — ship without the disputed item; revisit with more data
   - **Acceptance criterion** — ship with disputed item but log a measurable criterion for revisiting (R-V1's "if cost >1.5M tokens AND catch rate <15%" model)

**Resolution paths:**

- **Silent-accept:** other seat ships without re-replying on the disputed item (precedent: v4 R-V1 counter was silent-shipped by director). Equivalent to "accept the counter."
- **Re-REPLY:** other seat objects in writing with their own counter. Triggers another revision cycle.
- **2-cycle limit:** if disagreement persists after 2 REPLY cycles, escalate to user. **The agents do not argue indefinitely.** User is principal; agents serve user direction.

**Counting clarification (per C-D-1 from REPLY `642250d`):** The 2-cycle count refers to **director's REPLYs after the initial proposal**, not operator's revisions. Flow: `proposal → director REPLY (cycle 1) → operator revise → director REPLY (cycle 2) → operator revise → escalate to user`. Total: **1 proposal + 2 director REPLYs + 2 operator revises = 5 documents before escalation.** This matches the "don't argue indefinitely" intent — 5 documents is plenty of revision; if disagreement persists, user adjudicates.

**Why 2 cycles, not N:** each cycle costs tokens + delays ship. After 2 cycles of revision without convergence, the disagreement is substantive enough to need user adjudication. Empirically v4's R-V1 cycle resolved in 1 cycle (operator counter → director silent-ship). Two-cycle limit is conservative.

**Edit anchor:** Add `## Disagreement protocol (v5)` subsection to CLAUDE.md / AGENTS.md `# Director-Operator Concurrent Operation` after Rule #10.

---

## E — Emergency handling protocol

**Scope (per R-E-1 from REPLY `642250d`):** something breaks unexpectedly mid-session in one of four categories: (a) **production-affecting OR user-data-integrity issue** (live behavior broken, data lost / corrupted, users blocked); (b) **security-critical** (unauthorized access, secrets leak, active-exploit CVE); (c) **active bleed-rate** (cost / resource / token burn accumulating per minute of delay); (d) **external time-pressure** (deploy window, scheduled demo, regulatory deadline at risk without mitigation in N minutes). Events outside these criteria are NOT emergencies — they use normal role partition + proposal cycle, **even if urgent-feeling**. Current protocol is silent on this distinction; v5 §E codifies it.

**Why the criteria definition matters (per R-E-1 rationale):** without explicit criteria, two seats could reach different conclusions about whether a given event triggers §E. Specifically: a stale test, a UX bug discovered post-merge, a refactor regression — each could be argued as emergency or as normal-work-with-priority. The four-criteria gate keeps the §E carve-out tight; normal urgent work still uses proposal cycle.

**v5 protocol:**

1. **First-noticer claims initial response.** Whichever seat observes the emergency narrates in chat (Rule #2) AND sends a `dispatch-claim`-kind mailbox event with `urgency: emergency` flag. This signals the other seat to defer.

2. **Triage discipline: stop-the-bleed first.** The responding seat focuses on minimal-viable mitigation (revert, hotfix, feature-flag-off) rather than full root-cause analysis. Attribution and learnings happen post-incident.

3. **Cross-seat-temporary-authority during transplant:** if the normally-authoritative seat is in transplant or context-exhausted, the other seat has TEMPORARY authority on emergency response. The temporary seat:
   - Acts on emergency (commit + push if needed for stop-the-bleed)
   - Explicitly notes "acting under v5 §E temporary authority" in commit body
   - Defers all non-emergency decisions until normal seat returns

4. **Post-incident review.** Within 1 session of the emergency resolution:
   - Whichever seat handled the emergency writes an incident note (NEW: `docs/INCIDENT-LOG.md` or appended to DECISIONS.md)
   - Both seats review for protocol gaps that allowed the emergency
   - If protocol gap surfaces, draft rule for next bundle's REPLY cycle

**Why this matters:** emergencies don't honor cycle boundaries. The protocol must allow either seat to act without waiting for the other. The temporary-authority carve-out prevents transplant cycles from blocking critical response.

**Edit anchor:** Add `## Emergency handling protocol (v5)` subsection to CLAUDE.md / AGENTS.md after `## Disagreement protocol`. New file `docs/INCIDENT-LOG.md` (initially empty with header) for post-incident notes.

---

## B — Backlog partition (operator-claimable surface)

**Problem:** out-of-scope work currently has no visible workspace. POST-ROADMAP-2026-05-24.md is director-authored; operator can surface candidates but not curate. Operator's session-local "interesting but not cycle-N" observations get lost between transplants.

**v5 mechanism:** NEW file `docs/BACKLOG.md` as a shared-visible workspace.

**Structure:**

```markdown
# Backlog — Cross-cycle ideas, observations, candidates

Items either seat can add. Director typically curates (moves to
POST-ROADMAP picks); operator can claim Lane-D-style items
(documentation, refactors, doc-sync candidates) per cycle discretion.

## Active candidates

| ID | Surfaced by | Date | Description | Suggested seat | Priority hint |
|---|---|---|---|---|---|
| B-001 | operator | 2026-05-25 | <description> | operator-seat (Lane D) | M |

## Recently graduated to POST-ROADMAP

| ID | Description | Promoted at SHA |

## Recently completed

| ID | Description | Completion SHA |
```

**Either-seat write rules:**
- Adding an item: low-friction. Just append a row. No approval gate.
- Moving an item to POST-ROADMAP picks: director-seat (strategic decision).
- Claiming an item for execution: either seat, with mailbox-event narration.

**Why this addresses user's critique:** the user's "operator drafts blind" concern is partly about lack of visibility into what's been considered. BACKLOG.md makes the considered-but-not-prioritized space visible. Operator can scan before drafting.

**Edit anchor:** NEW file `docs/BACKLOG.md`. Reference from CLAUDE.md / AGENTS.md role-partition section.

---

## M — Memory-candidate mailbox kind

**Problem:** memory writes are director-seat-only (in this project's specific setup, user-authorized via auto-memory system). Operator observes memory-worthy patterns (recurring failure modes, tool quirks, project-specific gotchas) but cannot write directly. Currently surfaces via verbose mailbox events or commit-body prose — high friction for one-line observations.

**v5 mechanism:** new mailbox `kind: memory-candidate`.

**Event shape:**

```markdown
---
from: operator
to: director
kind: memory-candidate
related-commits: <SHA if relevant>
related-rules: 
suggested-memory-type: feedback | project | reference | user
---

# <memory candidate title>

<one-paragraph observation>

**Suggested memory file:** `<kebab-case-slug>.md`
**Why save:** <one sentence on why this is non-obvious or worth remembering>
**Use-case:** <when would future-Claude need this?>
```

**Processing:**
- Director-seat reviews on next session-start (via mailbox awareness gate per Rule #8)
- If director-seat agrees: writes the memory file directly (per existing auto-memory system)
- If director-seat declines: sends `decision`-kind event back with reasoning (the candidate is logged in archive but not memorialized)
- User can override at any time (principal authority)

**Edit anchor:** Update mailbox enum in `coordination/README.md`. v5 enum: existing + `memory-candidate`.

---

## S — Lane S activation (was scaffolded in v4 for v5+)

**v4 scaffold recap:** v4 introduced Lane S (pre-dispatch scout) as scaffolded-but-not-active. Mailbox kinds `scout-request` and `scout-report` were added but no behavior was codified.

**v5 activation:**

**Trigger:** Director-seat sends `scout-request` mailbox event BEFORE dispatching an implementer subagent (Lane B). The event names:
- Target files / symbols / modules the implementer will touch
- Brief reference (e.g., HANDOFF-roadmap §SESSION N line M)
- Specific intel needed (e.g., "convention conflicts," "gotchas," "plan-vs-source divergences")

**Operator-seat action upon receiving `scout-request`:**
1. Conduct Lane C-style read-only survey (no edits) of the named targets
2. Identify: convention conflicts, gotchas, related-file footprint, plan-vs-source divergences, ambiguous spec interpretations
3. Send `scout-report` mailbox event with findings; director-seat pastes relevant intel into implementer prompt

**Effort target:** ~10-20 minutes operator-context-burn per scout (much lighter than Lane V's subagent dispatch). Pure read; no subagent.

**Phase-detection:**
- If `scout-request` event present in mailbox sent/ and not yet processed: operator-seat is in "pre-dispatch scout" phase
- After `scout-report` sent: operator-seat returns to standby until director's implementer commit lands (then Lane V phase)

**Why operator-seat for scouts:** operator-seat has the orthogonal-context advantage. Director-seat has the spec/brief in working memory; operator-seat reads it cold and notices what director-seat may have normalized.

**v5 doesn't mandate scout-request:** director-seat can dispatch implementers without scouting (current behavior). Lane S activation just opens the channel; adoption is opportunistic.

**Edit anchor:** Update Lane S subsection in CLAUDE.md / AGENTS.md role-partition section from "scaffolded, v5+" to "active." Behavior spec from this section.

---

## Sh (Minor) — Codify implementer dispatch as director-seat-only

**Observation:** v1-v4's role partition listed "implementer dispatch" as Shared. Empirically, in 12+ sessions across cycles 1-6, director-seat has claimed every implementer dispatch (Lane B). Operator-seat has never dispatched an implementer.

**v5 codification:** rewrite "Shared: implementer dispatch" to "**Director-seat-default: implementer dispatch (Lane B)** — operator-seat does not dispatch implementers in the current configuration." Reflects de facto practice; eliminates the misleading Shared label.

**Why not "Director-only" strict:** future v5.1+ may want operator-seat dispatching small Lane B work (per the user's "implementer dispatch partitioned by domain" suggestion). v5 uses "default" to leave that door open while codifying current reality.

**Edit anchor:** Update role-partition table in CLAUDE.md / AGENTS.md. Move "implementer dispatch" row from "Shared" to "Director-seat-default."

---

## Locked design decisions (8 new)

| # | Question | Decision |
|---|---|---|
| 1 | Philosophical framing — "complementary specializations" or "two seats one team" | **"Two seats of one team"** (P1). Stronger reframe per user direction. Both seats equal in authority within specialization; user is principal. |
| 2 | Rule #10 wording — "joint-team mode" or "co-agent mode" | **"Joint-team mode"** as rule line; "co-agent" as subtitle. "Joint" emphasizes collective work; "co-agent" emphasizes peer relationship to user. |
| 3 | Rule #11 retroactive bias analysis — preserve in proposal only, or migrate to PROTOCOL-RULES-LOG.md | **Migrate to PROTOCOL-RULES-LOG.md** as a new "Beneficiary distribution snapshot" subsection. Allows future audits over time. |
| 4 | Disagreement cycle limit — 1, 2, or N | **2 cycles**, then escalate to user. Empirically v4 R-V1 resolved in 1; 2 is conservative. |
| 5 | Emergency authority — fully cross-seat or only-when-transplant? | **Only when normal seat is unavailable** (transplant, context-exhaustion, or explicit handoff). Default: normal seat owns emergency. |
| 6 | BACKLOG.md curation — operator-add-only or either-seat | **Either-seat can add; director-seat curates (moves to POST-ROADMAP); operator-seat can CLAIM Lane-D-style items for execution.** Mirrors v4's Lane D scope (docs work). |
| 7 | Lane S activation — opt-in or mandatory for all Lane B dispatches | **Opt-in.** Director-seat chooses when to send `scout-request`. Mandatory would create unwanted friction for routine dispatches. |
| 8 | Memory-candidate processing — silent-write by director, or always-acknowledged | **Always-acknowledged.** Director-seat sends `decision` event back even for acceptance (one-line "memory written at \<file\>") for audit trail. |

---

## Composability with prior bundles

| Pair | Composition |
|---|---|
| **v1-v4 partition + v5 reframe** | P1 reframes labels without breaking specific lane assignments. All existing lane work (V/D/S/B + director-strategic) preserved; framing updated. |
| **v4 Lane V + v5 R11 beneficiary check** | Lane V was beneficiary:operator-seat (per the retroactive snapshot in R11). v5 doesn't change Lane V; R11 makes the bias explicit for future rule additions. |
| **v4.1 CC-1 coalescing + v5 D disagreement** | CC-1 was an operator-surfaced + director-shipped refinement that fits D's "data-grounded counter" pattern. D generalizes the precedent. |
| **v4.1 CC-2 hallucination mitigation + v5 R11** | CC-2 was operator-seat surfaced; v5's R11 would have flagged "beneficiary: operator-seat" → director-seat consents → ships. Cleaner audit trail. |
| **v3 §G authority precedence + v5 P1** | v3 §G said user > git > mailbox > STATE.md. v5 P1 says user is principal; agents are peer. Compatible: P1 strengthens the user-tier framing without changing precedence. |
| **v2 mailbox + v5 M memory-candidate** | M is a new mailbox kind; rides v2's substrate. No new infrastructure. |
| **v2 mailbox + v5 S scout activation** | S activates v4-scaffolded mailbox kinds (`scout-request`, `scout-report`). No new infrastructure. |
| **v5 E emergency + Rule #1 role partition** | E provides a CARVE-OUT from role partition for emergency cases. Rule #1 still governs normal operation. |

---

## Open questions — resolved per REPLY `642250d`

All 8 questions resolved by director's REPLY. None required structural rewrites; all aligned with operator's lean.

| # | Question | Resolution |
|---|---|---|
| 1 | P1 framing — "two seats of one team" or alternative? | **"Two seats of one team" lands.** Matches user direction explicitly. Alternative phrasings ("complementary co-agents") are weaker because "team" carries the unified-purpose connotation user wanted. |
| 2 | R11 retroactive snapshot — PROTOCOL-RULES-LOG.md or separate file? | **PROTOCOL-RULES-LOG.md** per operator's lean. The snapshot IS rule metadata; splitting would fragment audit. New "Beneficiary distribution snapshot" subsection in the rules-log. |
| 3 | D 2-cycle limit — 1, 2, or N? | **2 cycles**, per C-D-1's counting clarification. 1 is too aggressive (treats normal refinement as escalation); N is too lax (could spiral). v4 R-V1 resolved in 1 cycle, so 2 is genuinely conservative. |
| 4 | E temporary-authority carve-out — additional gating needed? | **Commit-body narration is sufficient.** Adding user-notification-within-N-minutes is overkill for the carve-out. The audit trail (commit body + git log) is already inspectable; user can review at next session-start. R-E-1's criteria definition closes the larger ambiguity about when §E even applies. |
| 5 | B backlog — Lane-D-only or Lane V claims? | **Lane-D-style only for v5.** Lane V expansion premature — operator's Lane V is just-validated dogfood (2 dispatches, second one a CRITICAL catch). Don't broaden claim surface until pattern is more established. v5.1+ may expand based on data. |
| 6 | M memory-candidate — director-mediated or user-direct? | **Director-mediated for v5** per operator's lean. Consistent with existing memory write authority (auto-memory system is user-authorized via director session). User-direct path would expand v5's scope beyond protocol-substrate edits. v5.1+ could shift if director-mediated bottlenecks. |
| 7 | S Lane S — opt-in or mandate above N LOC? | **Fully opt-in for v5.** Mandating creates friction for routine dispatches; opt-in lets pattern emerge organically. Collect data on which dispatches benefit from scout-request; codify mandate criteria in v5.1+ if patterns emerge. |
| 8 | Sh implementer dispatch — "default" or "only"? | **"Director-seat-default"** per operator's lean. "Only" closes the door on future operator-seat Lane B work prematurely. User's "implementer dispatch partitioned by domain" critique implies future-expansion is plausible; "default" preserves optionality. |

**Director's additional observations (REPLY §"What I find particularly well-done in v5"):**

- **R11 self-application is decisive.** Operator applied R11's beneficiary check to v5 itself (7 both / 1 user / 1 operator-seat / 0 director-seat). If R11 had failed on its introducing bundle, the rule would have been falsified at introduction. Passing is the cleanest possible introduction. Combined with the retroactive analysis (Rules 1-9: 4 both / 1 user / 3 operator-seat / 0 director-seat), empirically disproves the bias hypothesis user surfaced.
- **User-critique-preserved-inline** section makes the proposal cold-readable for future operators. Cycle-9+ pickup can see exactly which user observations drove which components — structural-traceability discipline the protocol has been building toward.
- **D's three resolution paths** (counter-refinement / defer-to-v(N+1) / acceptance-criterion) are well-engineered. The third path is what v4's R-V1 actually used (the >1.5M-token + <15%-catch-rate trigger). Codifying as first-class means future disagreements have a structured ship-anyway-with-monitoring option.

---

## Trade-offs and risks

| Risk | Mitigation |
|---|---|
| **Philosophical reframe sounds like "no asymmetry"** when in fact lane assignments are unchanged | P1 explicit: specialization-vs-hierarchy distinction; lane assignments preserved |
| **Disagreement protocol's 2-cycle limit creates pressure to silent-accept** rather than counter-propose | The default is silent-accept (per v4 precedent); the 2-cycle limit only triggers if disagreement is explicit. Healthy disagreement is encouraged, not penalized. |
| **Emergency carve-out creates ambiguity about when each seat's authority applies** | Explicit gating: "normal seat unavailable" = transplant, context-exhaustion, or explicit handoff. Default is normal-seat-owns-emergency. |
| **BACKLOG.md becomes a dumping ground** | Either-seat-can-add but director-seat-curates. Stale items aged out per future v5.1+ retirement criterion. |
| **R11 beneficiary check adds REPLY-cycle overhead** | Lightweight: one frontmatter field. Even if neglected, doesn't break the proposal. The audit trail value compounds over time. |
| **Lane S activation creates operator-side context burn for scouts** | Scout cost ~10-20 min context (lighter than Lane V's subagent dispatch). Director-seat chooses when scout is worth it. |
| **Memory-candidate channel pollutes mailbox** | Decision-back-acknowledgment provides audit trail. Stale candidates archive cleanly. |
| **"One team" framing could blur the productive friction** between seats that drives second-opinion catches (Rule #9) | Specialization-preserving language: "two seats of one team" not "one undifferentiated agent." R10 explicit about equal-but-different. |

---

## What v5 does NOT do

- Does NOT eliminate the asymmetry between specializations (operator-seat doesn't gain push authority; director-seat doesn't gain Lane V dispatch authority)
- Does NOT change the proposal/REPLY/revise/ship cycle for protocol changes
- Does NOT add automation (Phase 2 territory remains deferred)
- Does NOT change existing lane assignments (V/D/S stay operator-seat; brief authoring + ADR + push stay director-seat)
- Does NOT introduce new TypeScript/Python code changes — pure protocol/docs
- Does NOT mandate scout-request for any specific commit type
- Does NOT change memory write authority (still director-seat for direct writes; operator-seat suggests via M)
- Does NOT eliminate "Operator drafts, Director ships" — that pattern stays; R11 reduces its friction

---

## Dogfood / acceptance

**v5 is "shipped" when:**
1. CLAUDE.md / AGENTS.md `# Director-Operator Concurrent Operation` reframed with P1 + R10 + R11 + D + E + Lane S activation + Sh codification
2. Rule #10 + Rule #11 added to PROTOCOL-RULES-LOG.md rule registry; "Beneficiary distribution snapshot" subsection added
3. Mailbox enum updated in `coordination/README.md` (memory-candidate added)
4. NEW: `docs/BACKLOG.md` created with template structure
5. NEW: `docs/INCIDENT-LOG.md` created with template structure
6. This proposal's footer updated post-ship per Rule #6/#7 ship discipline
7. STATE.md reflects the ship
8. Rules #10 + #11 ship with `_Protocol Bundle v5 ship_` placeholder; operator updates next session-close

**v5 is "working" when (within next 2-4 sessions):**
- ≥1 R11 beneficiary check fires during a v5.1+ proposal cycle
- ≥1 emergency case (or simulated drill) tests v5 §E
- ≥1 BACKLOG.md item added by operator-seat
- ≥1 `memory-candidate` mailbox event fires
- ≥1 `scout-request` from director-seat (opportunistic)
- ZERO cross-seat confusion about specialization scope
- ZERO unresolved disagreements escalated to user (target: 0; if 1+, that's signal D is well-utilized)

**v5 rollback trigger:** if "working" criteria fail OR director-seat reports friction with the philosophical reframe within 3 sessions, roll back via v5.1 (analogous to v2.1, v4.1 patterns).

---

## v5 beneficiary check (per R11, applied to v5 itself)

| Component | Beneficiary | Notes |
|---|---|---|
| P1 (reframe) | both | both seats clarified |
| R10 (joint-team mode) | both | discipline for both |
| R11 (codification bias check) | user | reduces bias; serves principal's interest |
| D (disagreement protocol) | both | both seats use |
| E (emergency handling) | both | both seats can act |
| B (backlog partition) | both | shared workspace |
| M (memory-candidate) | operator-seat | operator surfaces memory; director writes |
| S (Lane S activation) | both | director gets scout intel; operator gets defined operational role |
| Sh (implementer dispatch labeling) | both | codifies existing reality for both |

**Distribution:** 7 both, 1 user, 1 operator-seat, 0 director-seat. v5 itself passes R11 with strong both-seat balance.

---

## Ship strategy

Bundle as single commit. Race-ack body per Rule #5 if state moves during ship.

Estimated implementation effort: ~45-60 min. Larger than v4 (~30-45 min) due to P1 philosophical edits across CLAUDE.md/AGENTS.md + 7 new components.

**Files touched at ship:**
1. `CLAUDE.md` — P1 reframe at top of role-partition section; Rule #10 + #11 in rule registry; D + E + S activation + Sh subsections
2. `AGENTS.md` — mirror of CLAUDE.md
3. `docs/PROTOCOL-RULES-LOG.md` — Rule #10 + #11 in rule registry; "Beneficiary distribution snapshot" subsection
4. `coordination/README.md` — mailbox enum update (memory-candidate)
5. **NEW** `docs/BACKLOG.md` — template structure
6. **NEW** `docs/INCIDENT-LOG.md` — template structure
7. This proposal file — footer state update post-ship

**SHA placeholder pattern:** Rules #10 + #11 ship with `_Protocol Bundle v5 ship_`; operator updates to actual ship SHA in follow-up commit per chicken-and-egg precedent (`3e57ddf` v2; `d8f2407` v3; `d90036b` v4; `_Protocol Bundle v4.1 ship_` placeholder in v4.1 row also pending fill).

**Blocks:** None. v5 is additive over v2/v3/v4/v4.1 — nothing currently working breaks; existing partition is reframed, not deleted.

---

## What this proposal explicitly answers for the user

User said: "draft v5 according to how you see fit for the protocol which you and the director will be working under so optimize and focus on director and operator being one team."

This proposal:

1. **Reframes** the role partition as one-team-two-seats (P1, R10)
2. **Addresses** the user's structural critique point-by-point (preserved in §"Why v5: the user critique")
3. **Adds** the missing partitions the critique flagged (E emergency, B backlog, D disagreement)
4. **Closes** the meta-bias loop with R11 (per-rule beneficiary check)
5. **Activates** the v4-scaffolded Lane S (was deferred to v5+)
6. **Codifies** de facto practice the critique called out (Sh implementer dispatch labeling)

If any of this misses the user's intent, the disagreement protocol (D) now exists as the channel — counter-refinement in next REPLY cycle. The "two seats one team" framing means user-direction overrides agent discretion; v5 is designed to be revised before ship if it doesn't land.

---

*Operator-draft proposal authored 2026-05-25; **revised 2026-05-25** incorporating director's REPLY at `642250d`. Refinements applied: **R-E-1** (emergency criteria definition in §E) and **C-D-1** (2-cycle counting clarification in §D). All 8 open questions resolved per REPLY; all 8 locked decisions stand. No counter-refinements (clean REPLY cycle, contrast with v4 R-V1). State at revision-commit per Rule #7: HEAD `642250d`; branch 2 ahead of `origin/main`; working tree clean. Awaits director ship per cycle precedent (v2: `416d610`, v3: `3340d1f`, v4: `d61bdc8`, v4.1: `509db7c`). User direction can override at any point per existing CLAUDE.md "Instruction Priority" and v5 §P1.*

**R11 beneficiary check on this revision (per Rule #11 self-application discipline):** R-E-1 = `beneficiary: both` (emergency definition serves both seats — director-seat for ADR/strategic carve-out clarity, operator-seat for action-during-transplant clarity). C-D-1 = `beneficiary: both` (counting clarification serves both — disambiguates the cycle-limit semantics symmetrically). No new R11 considerations.

***SHIPPED 2026-05-25** by director (`d66690f`; SHA filled post-ship by operator per chicken-and-egg precedent — `3e57ddf` v2 / `d8f2407` v3 / `d90036b` v4 / `509db7c` v4.1 also filled this session). Files modified at ship: `CLAUDE.md` (P1 reframe + role partition relabeling + Rule #10 + Rule #11 + Disagreement + Emergency sections + Lane S activation + Sh codification), `AGENTS.md` (mirror of CLAUDE.md), `docs/PROTOCOL-RULES-LOG.md` (Rules #10 + #11 + Beneficiary distribution snapshot subsection), `coordination/README.md` (memory-candidate mailbox kind), `docs/BACKLOG.md` (NEW), `docs/INCIDENT-LOG.md` (NEW), this file (footer). Branch ahead-count at ship: 4 commits post-revision (`2e06fe1` proposal + `642250d` REPLY + `8a4148a` revision + this ship); push as batch per cycle precedent (v2/v3/v4).*
