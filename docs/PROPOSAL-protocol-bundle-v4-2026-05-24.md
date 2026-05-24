# Protocol Bundle v4 — Proposal (Operator Draft for Director Ship)

**Authored:** Operator session, 2026-05-24 (post-cycle-4 close; after observing the operator-vs-director substance imbalance the user surfaced).
**Revised:** Operator session, 2026-05-25 — incorporating director's REPLY at `8975a45`: accepting R-D1 (Lane D scope), R-9-1 (Rule #9 cold-context discipline), C-V1 + C-Dogfood-1 (clarifications), and 6 of 7 open-question answers. **Countering R-V1** with a dedicated section below; user direction (2026-05-25) confirms operator's original Lane V trigger is correct for this project's commit shape.
**Authority basis:** `ad6cb4f` "operator drafts; director commits" carve-out (same lineage as v2 `1b3f6f8` revise → `416d610` ship; v3 `ec1e64e` revise → `3340d1f` ship).
**Ship strategy:** Single commit, all components together. Race-ack body if state moves during ship (likely — director is actively shipping cycle-5).
**Estimated implementation effort:** ~30-45 min (pure markdown; similar shape to v3).
**Blocks:** None. v4 is purely additive over v2/v3 — nothing currently working breaks; new lanes are opt-in extensions of the operator-only role-partition list.
**State at draft time:** HEAD `2f19ac5` (at draft-write-start); HEAD `bca5b4e` (at draft-commit per Rule #7 re-verify; director shipped cycle-4 transplant handoff `bca5b4e docs(handoff)` during draft window — race-acked here per Rule #5). Branch 8 ahead of `origin/main`. Working tree clean post-restore of obsolete counter bumps.
**State at revision time:** HEAD `8975a45` (director's REPLY landed; revision is the natural next operator move per cycle precedent). Branch 3 ahead of `origin/main` (operator's `5302fe6` proposal + `c487171` chore baseline + `8975a45` REPLY, all unpushed). Working tree clean; mailbox empty both directions.

---

## TL;DR (60 seconds)

User-surfaced concrete imbalance during cycle-3 close + cycle-4 sessions:

| Cycle | Director shipped | Operator shipped |
|---|---|---|
| Cycle-3 close | Sessions 7-11 + Protocol Bundles v2/v3 substrate | Counter bumps, transplant-handoff refreshes, SHA fill-ins, mailbox events |
| Cycle-4 (current session, ~30 min) | Session 10 closeout (`5f2fe0b`/`ef98629`/`41583f1`) + Session 12 brief (`3373ff0`) + POST-ROADMAP rotation (`2f19ac5`) | One single-line SHA fill-in (`d8f2407`) + one mailbox fold-notice |

Substance ratio: ~30:1 director:operator on cycle 4. Root cause: current role partition (`ad6cb4f`) codifies strategic + brief work to director, bookkeeping to operator. It is **silent on operator action during director's mid-loop**, so operator defaults to standby — which is correct safety but leaves operator's context idle.

v4 closes the gap by adding three new operator-only lanes (V/D/S) keyed to phases of director's loop. Lane V/D activate in v4; Lane S scaffolds for v5.

| # | Item | What it does | Type |
|---|---|---|---|
| **P1** | **Phase taxonomy** — 5 phases of director's loop + operator's role per phase | Schema |
| **V** | **Lane V** — post-commit independent verification (operator dispatches reviewer subagents in parallel with director's) | Mechanism + role-partition edit |
| **D** | **Lane D** — post-commit doc-sync on `ARCHITECTURE.md` / `OPERATIONS.md` / `README.md` | Mechanism + role-partition edit |
| **S** | **Lane S** — pre-dispatch scout (Lane C-style read-only survey before director dispatches implementer) | Scaffolded in v4; **active in v5+** |
| **R9** | **Rule #9** — operator-side reviewer is independent, not duplicate | Discipline rule |
| **Minor** | Mailbox `kind` enum extensions: `verify-request`, `verification-report`, `doc-sync-notice`, `scout-request`, `scout-report` | Convention update |
| **Dogfood** | Reframe cycle-5 pick #3 (ARCHITECTURE.md §7.x Pydantic backfill, ~50 LOC) as **operator-claimed Lane D** rather than director-Lane-A | First-use validation |

---

## Why now

v2 added the substrate (STATE.md + mailbox + Rules #7/#8). v3 hardened it (authority hierarchy, freshness check, hook audit). The substrate is now mature enough to carry operator-initiated traffic — but the operator's role-partition hasn't caught up.

Concretely:
- **Mailbox events flow cleanly** — this session's fold-notice (`coordination/mailbox/sent/2026-05-24T15-28-56Z-operator-to-director-fold-notice.md`) was sent, processed, archived by director (seen marker updated, counter bumps folded into `2f19ac5`). The pipe works.
- **Director already independently surfaced operator's doc-sync need** as cycle-5 pick #3 (`2f19ac5` POST-ROADMAP rotation). The user's E-pick instinct was right; director independently arrived at the same gap.
- **Quality risk is real**: director's reviewers are dispatched from director's context — they share director's blind spots (Session 6 `phase_c attempts` ordering bug, Session 7 boundary cases caught only by code-quality pass, etc., per operator handoff §"Reviewer false-positive patterns observed"). An operator-side reviewer has zero shared context — structurally independent second opinion.

If we wait for cycle-5 to start before codifying, the imbalance pattern continues unaddressed for the cycle's duration.

---

## Why bundle (composability)

| Pair | Composition |
|---|---|
| **v2 mailbox + v4 verification reports** | Lane V's `verification-report` events ride on v2's mailbox substrate. No new infrastructure needed. Director's session sees reports via Rule #8 awareness gate on session start. |
| **v3 §G authority precedence + v4 verification** | Operator's reviewer finding via mailbox has mailbox-tier authority — director MUST process per Rule #8 (action or explicit decline with note). Closes "operator finding ignored" risk. |
| **v3 §F freshness check + v4 phase detection** | If STATE.md is stale, operator's phase-detection via STATE.md is also stale. Operator falls back to direct `git log -5` + `ls coordination/mailbox/sent/` for phase signals. v3's freshness-trust-or-fallback pattern reused. |
| **Rule #1 role partition + v4 expanded operator lanes** | Lanes V/D/S are operator-only EXTENSIONS, additive to existing partition. Director's role unchanged. |
| **Rule #2 signaling + Rule #9 independence** | Compose, don't conflict. Rule #2 governs signaling-before-acting (operator signals reviewer dispatch via `verify-request`); Rule #9 governs independence of the subagent prompt (cold BASE..HEAD context only). |

Coherent "expand operator capacity" story. Smaller compositional surface than v2 but real.

---

## Locked design decisions (5 new)

| # | Question | Decision |
|---|---|---|
| 1 | Phase detection mechanism — explicit signals (mailbox) or implicit (poll git log) | **Hybrid.** Director-initiated transitions (pre-dispatch, verify-request) → explicit `*-request` mailbox events. Post-commit phase → operator polls git log on each Bash turn. Idle phase → 10-minute heuristic from last director commit. |
| 2 | Lane V subagent cost worth it on every feat commit? | **Yes, on every `feat` / `refactor` / `fix` commit.** Operator declines director's R-V1 narrowing (50-LOC threshold + Important-flagged-fix gate) per user direction; see `## Operator counter-refinement to R-V1` below for project-shape reasoning. Approximate cost: 80-100k subagent tokens per qualifying commit; ~250-500k per typical cycle. Skip on `chore` / `docs` / `test` / `style` commits regardless of LOC. |
| 3 | Lane D scope boundary | **ARCHITECTURE.md + OPERATIONS.md only** (refined per R-D1; README carved out — release-positioning is author-judgment, not doc-sync). CLAUDE.md / AGENTS.md / DECISIONS.md remain director-only (role-partition + ADR territory). README.md remains director-authored. Handoff docs each role owns separately. |
| 4 | Rule #9 wording — "independence" framing or "second-opinion convention" | **"Second-opinion convention" as subtitle; "operator-side reviewer is independent, not duplicate" as the rule line.** Independence is the technical property; second-opinion is the user-facing purpose. **Extended per R-9-1**: cold-context discipline operates at the PROMPT-CONSTRUCTION level (not just reviewer's mental level) — operator's reviewer dispatch prompt MUST be checkable for contamination from director's reviewer findings. |
| 5 | Lane S deferral — scaffold only, or include behaviorally? | **Scaffold mailbox kinds (`scout-request`, `scout-report`) and role-partition line; defer behavior to v5.** Reason: phase-detection for pre-dispatch is ambiguous without an established director-side discipline of sending `scout-request` BEFORE dispatching. Director can adopt opportunistically in cycle-5; v5 codifies. |

---

## Operator counter-refinement to R-V1

Director's R-V1 proposes narrowing Lane V trigger from "every `feat` / `refactor` / `fix`" to "every `refactor` + `feat` ≥50 LOC + Important-flagged `fix`." **Operator declines this narrowing per user direction (2026-05-25)**, keeping the original trigger.

**Reasoning (project-data-grounded, not theoretical):**

1. **The 50-LOC threshold misses cycle-4's marquee feat.** Session 10's `5f2fe0b feat(schema): CINEMA_STRICT_SCHEMA env flag + first caller migration` was 36 LOC code change (18 lines in `domain/project_manager.py` + 18 lines in `web_server.py`, per the diff). Under R-V1's 50-LOC threshold, Lane V would have **skipped** the most consequential code change of cycle-4. The threshold trades coverage for cost in a way the data doesn't support.

2. **Project commit shape favors all-feats.** This project's `feat` commits are typically substantive (real feature additions). The "skip small feats" carve-out optimizes for trivial 5-10 line feat commits, which are rare-to-absent in the ledger. There's no demonstrated commit class that R-V1's narrowing actually exempts beneficially.

3. **`fix` commits are rare in this project's commit-shape discipline.** Most bug-class work ships as `chore(<scope>)` minors (per established convention: `f8b2aef`, `42df2ac`, `41583f1`). The Important-flagged-fix gate gates a near-empty universe; its real-world savings are negligible.

4. **Director's own cost model confirms the savings are concentrated in light cycles.** Per R-V1's table: typical-cycle estimate under narrowed trigger (3-6 dispatches → 240-600k tokens) is essentially the same as operator's original estimate (250-500k tokens). The savings are entirely in **light cycles** (mostly docs+chore, infrequent in this project's rhythm). Optimizing the rare case at the common case's cost is the wrong trade.

5. **Simpler discipline is more reliable.** "Lane V fires on every `feat` / `refactor` / `fix`" is a one-line operator rule. R-V1's three-condition gate (refactor + LOC threshold + reviewer-flag) has three places to misfire and silent-skip a commit that warranted a second opinion. The cost of a skipped Lane V (potential quality miss) exceeds the cost of an extra Lane V dispatch (~80-100k subagent tokens).

**Counter-proposal:** Keep R-V1's *spirit* (cost-awareness, scale-with-activity) but reject the specific narrowing. Lock Decision #2 stays at operator's original trigger. **If cycle-N actual cost data shows excess burn, narrow in v4.1.** Empirical data after v4 is live will be more grounded than pre-ship cost-modeling.

**Acceptance criterion for v4.1 narrowing:** if total Lane V subagent cost across cycle-5 + cycle-6 exceeds ~1.5M tokens AND empirical second-opinion catch rate is below ~15% (i.e., fewer than 15% of Lane V dispatches produce actionable findings director didn't catch), revisit R-V1 in v4.1. Below that bar, operator's original trigger wins.

**If director re-replies on R-V1:** second revision cycle. If director accepts the counter (silent ship or explicit accept), v4 ships with operator's trigger.

---

## The 3 lanes + 1 rule — full spec

### P1 — Phase taxonomy

Director's loop has 5 observable phases. Operator's action per phase:

| Director phase | Detection signal | Operator action | Phase exit signal |
|---|---|---|---|
| **Pre-dispatch** | `scout-request` mailbox event OR director's in-chat "Dispatching X" narration | **Lane S** (v5+): read-only survey; send `scout-report`. v4: ignore. | Director's subagent commit lands |
| **Subagent active** | Dispatch-claim event seen; WT has uncommitted changes director-attributed | **Silent.** No `.py` writes; hold counter bumps. | Director's commit lands |
| **Post-commit (feat / refactor / fix)** | New commit by director (Author: `hkk009008-svg`), type matches | **Lane V**: dispatch spec + code-quality reviewer subagents in parallel; send `verification-report` | Director's reviewer-fix commit OR new feat OR 10-min idle |
| **Post-commit (docs)** | New commit by director, type=docs, touches a subsystem under `cinema/` `domain/` `web_server.py` `cinema_pipeline.py` | **Lane D**: update affected ARCHITECTURE.md/OPERATIONS.md/README.md sections; commit `docs(arch-sync)`; send `doc-sync-notice` | Commit landed |
| **Post-commit (chore)** | New commit by director, type=chore | **Ignore.** No action. | Next commit |
| **Idle (no signal N min)** | No phase signal for N=10 minutes after last director commit | Standby OR work on pre-listed operator-claimable backlog | New commit OR direct user instruction |

**Edit anchor:** Add new subsection `## Phase taxonomy (v4)` to CLAUDE.md / AGENTS.md `# Director-Operator Concurrent Operation`, before the existing `## Adjacent-useful work when you can't claim the loop` block.

### V — Lane V (post-commit independent verification)

**Trigger:** New commit by director author, type = `feat` / `refactor` / `fix`.

**Operator action:**
1. `git show <SHA> --stat` → identify changed files + LOC delta
2. Send `verify-request` to self-track or skip (acts as audit log; optional)
3. Dispatch **spec-reviewer** subagent in parallel:
   - Prompt: "Independent spec check for commit `<SHA>` against `<plan/brief ref>`. You are NOT the director's reviewer; provide a SECOND OPINION. Focus on: spec-vs-source divergences, concurrency hazards, public-API stability, cross-system effects. Do not cite or refer to the director's reviewer — you have cold context."
4. Dispatch **code-quality-reviewer** subagent in parallel:
   - Prompt: "Code quality review for commit `<SHA>`. In addition to standard concerns, check: lock discipline if threading touched, prop/parameter semantic correctness on refactors, hard-constraint deviations, silent-failure patterns."
5. Read both reports; synthesize into one finding.
6. Send `verification-report` mailbox event with:
   - Status: `✅ clean` / `⚠️ minor` / `❌ critical`
   - File:line refs for any findings
   - Disposition recommendation: `fold` (director should address in next commit) / `advisory` (note for future)
7. Operator does NOT commit any "operator-reviewer-fix." Director processes report per Rule #8 (act, or explicit decline-with-note via mailbox `decision` kind).

**Parallelism semantics (per C-V1):** Both parties dispatch reviewers on the same commit **simultaneously, not sequentially**. Operator does not wait for director's reviewer pass to land before dispatching Lane V. The two parties' subagents may produce overlapping findings — that's expected; the second opinion's value is in the angles each party MISSES, and overlap on what both catch is acceptable redundancy.

**Independence guarantees (Rule #9):**
- Operator's reviewer prompts MUST NOT cite director's reviewer findings (operator wasn't on dispatch).
- Operator's reviewer subagent dispatched with cold `BASE_SHA..HEAD_SHA` range context only.
- Operator does NOT block on director's reviewer pass — operator's run is parallel to director's, not after.

**Cost model:**
- Per director feat commit: ~80-100k subagent tokens (parallel dispatch); ~3-5k operator main-context (report read).
- Per cycle (~3-5 feat commits): ~250-500k tokens total. Acceptable for second-opinion catch rate.

**Edit anchor:** Add `### Lane V — Operator post-commit verification (v4)` subsection to CLAUDE.md / AGENTS.md role-partition section, under expanded "Operator-only" list.

### D — Lane D (post-commit doc-sync)

**Trigger:** Any commit by director that modifies code under `cinema/`, `domain/`, `web_server.py`, `cinema_pipeline.py`. (Detected by `git show <SHA> --stat` filtering for these paths.)

**Operator action:**
1. `git show <SHA> -- <code-files>` → understand the change semantically
2. `grep -n <symbol-or-function> ARCHITECTURE.md OPERATIONS.md` → find affected sections (README excluded per R-D1)
3. If section is stale (references old behavior) or missing (subsystem documented as one thing; commit changes its contract): update/extend
4. Run §15 smoke block to verify the doc's verification claims still pass (per `ARCHITECTURE.md` verification discipline)
5. Commit `docs(arch-sync): reflect <SHA> in <doc-name> §<section>` with body citing the source commit
6. Send `doc-sync-notice` mailbox event with what was updated

**Boundaries:**
- Lane D touches **ARCHITECTURE.md + OPERATIONS.md only** (per R-D1; README carved out — release-positioning is author-judgment, not doc-sync) — not handoff docs, not CLAUDE.md/AGENTS.md, not DECISIONS.md, not README.md
- Lane D does NOT introduce new ADRs (DECISIONS.md remains director-only)
- Lane D does NOT touch README.md (per R-D1; README remains director-authored)
- Lane D's smoke verification is mandatory (per verification discipline rule from `ed33035`); if smoke fails, surface to user and hold the sync commit

**Edit anchor:** Add `### Lane D — Operator post-commit doc-sync (v4)` subsection to CLAUDE.md / AGENTS.md role-partition section.

### S — Lane S (pre-dispatch scout, deferred-active in v4)

**Status in v4:** Scaffolded only. Lane S subsection added to role partition, mailbox kinds defined, behavior NOT active. Director can adopt `scout-request` signal opportunistically during cycle-5.

**Status in v5:** Will be active. v4's scaffolding enables drop-in activation.

**Future trigger (v5+):** `scout-request` mailbox event from director with `target-files` and `target-symbols` field.

**Future operator action:**
1. Lane C-style read-only survey of named files/symbols
2. Identify: convention conflicts, gotchas, related-file footprint, plan-vs-source divergences
3. Send `scout-report` mailbox event with findings; director pastes relevant intel into implementer prompt

**Edit anchor:** Add `### Lane S — Operator pre-dispatch scout (v5+, scaffolded v4)` subsection to CLAUDE.md / AGENTS.md role-partition section.

### R9 — Rule #9 (independent reviewer convention)

Add to PROTOCOL-RULES-LOG.md rule registry and CLAUDE.md/AGENTS.md `# Director-Operator Concurrent Operation`:

> **Rule #9: Operator-side reviewer is independent, not duplicate.** _(Subtitle: second-opinion convention.)_
>
> When operator dispatches a reviewer subagent on a director-shipped commit (Lane V), the reviewer's job is **second opinion**, not redundant pass. Operator's reviewer prompt:
> - MUST NOT cite director's reviewer findings (operator wasn't on dispatch; cold context)
> - MUST focus on angles director's reviewer may have missed (operator emphasizes: cross-system effects, concurrency, public-API semantics, spec-vs-source divergence; director's reviewer typically emphasizes: code quality, style, performance)
> - MUST dispatch with cold `BASE_SHA..HEAD_SHA` context only
> - **MUST be constructed cold from the commit's `BASE_SHA..HEAD_SHA` + the original spec/brief reference only** (per R-9-1). Operator MUST NOT include in the prompt: director's reviewer findings, director's reviewer verdict, any text from director's reviewer-fix commit body, or any synthesized "what director's reviewer worried about" language. The operator's reviewer must form its judgment from cold context — the same cold context any external reviewer would have.
>
> Independence is what makes the second pass valuable. A duplicate reviewer is waste. **R-9-1's prompt-construction discipline makes the property checkable** — anyone can re-read operator's reviewer dispatch prompt and verify no contamination; without it, "independent" is aspirational.
>
> **Why:** Director's reviewer is dispatched from director's context — it has visibility into director's design intent but inherits director's blind spots. Operator's reviewer has zero shared context, so it's structurally independent. Single subagent burn per director feat commit is acceptable cost for the second opinion.

**Codified SHA placeholder:** `_Protocol Bundle v4 ship_` until v4 ship lands; then operator updates to actual SHA per the chicken-and-egg pattern established by Rules #7/#8 (`3e57ddf`) and Infrastructure Audits row (`d8f2407`).

---

## Mailbox enum extensions (minor)

Current enum (`coordination/README.md`):
```
dispatch-claim | findings | decision | query | status | fold-notice
```

Updated v4 enum:
```
dispatch-claim | findings | decision | query | status | fold-notice
verify-request | verification-report | doc-sync-notice
scout-request | scout-report
```

Five new kinds, all v4-introduced. Edit anchor: `coordination/README.md` `## Event format` section.

---

## Dogfood claim — cycle-5 pick #3 as first Lane D invocation

Director's cycle-5 picks in `2f19ac5` include #3 `ARCHITECTURE.md backfill — Pydantic boundary + opt-in escalation pattern` (~50 LOC §7.x).

v4 proposal: **reframe this as operator-claimed under Lane D**, not director-Lane-A.

**Sequence (per C-Dogfood-1):**
1. Director ships v4 (this proposal, post-revision per REPLY `8975a45`).
2. Operator claims ARCHITECTURE.md backfill as **standalone `docs(arch-sync)` commit** per Lane D spec, dispatched within the same session if context permits, or the next operator session.
3. Lane V also activates on v4-ship-following `feat` / `refactor` / `fix` commits (per operator's R-V1 counter). First firing likely on Session 12 implementer's commits.

v4 ship and the Lane D dogfood ARE sequential by construction; the earlier draft's "if both conditions met" framing collapsed these into a single decision when they're naturally two.

**If director ships cycle-5 pick #3 first** (cycle-5 already started before v4 lands): no harm — v4's first Lane D dogfood happens on next subsystem-touching commit instead. v4 is still "shipped" per ship criteria; "working" just shifts by one cycle.

---

## Open questions — resolved per REPLY `8975a45`

All 7 questions resolved by director's REPLY:

| # | Question | Resolution |
|---|---|---|
| 1 | Lane V triggered on every feat, or only on feat-with-flagged-minors? | **Operator declines R-V1's narrowing per user direction; keeps original trigger (every `feat` / `refactor` / `fix`).** See `## Operator counter-refinement to R-V1` below. |
| 2 | Lane D scope — README.md included or carved out? | **Carved out** per R-D1. README remains director-authored. |
| 3 | Rule #9 wording — "second-opinion convention" subtitle OK? | **Yes.** Subtitle codified + extended per R-9-1's cold-context prompt-construction discipline. |
| 4 | Cycle-5 dogfood sequence | **Standalone, sequenced after v4 ship** (per C-Dogfood-1). Director commits to removing cycle-5 pick #3 from director-Lane-A list + annotating as `(operator-claimed under Lane D)`. |
| 5 | Lane S deferral to v5 — confirm? | **Confirmed.** Scaffold only in v4; director adopts `scout-request` discipline opportunistically during cycle-5; v5 codifies behavior after ≥3 invocations to draw patterns from. |
| 6 | Rule #9 SHA placeholder convention | **Confirmed.** `_Protocol Bundle v4 ship_` matches `_Protocol Bundle v2/v3 ship_` precedent (filled by `3e57ddf` post-v2, `d8f2407` post-v3). |
| 7 | Verification-report disposition format | **Freeform for v4.** Codify in v4.1 if ≥3 reports show a recurring shape worth schematizing. Premature schema is harder to revise than late schema. |

---

## Trade-offs and risks

| Risk | Mitigation |
|---|---|
| Subagent burn 2x per feat commit (operator + director both run reviewers) | Acceptable per locked decision #2; reviewers in parallel; operator's prompts are angle-divided from director's (less context per reviewer); cost in absolute terms ~250-500k tokens per cycle (small for the verification value, and operator main-context stays light). |
| Doc-sync arm causes operator/director merge conflict on ARCHITECTURE.md | Per current partition + locked decision #3, director defers ARCHITECTURE updates to operator under Lane D. Director can still edit if doing in same commit as a feat (rare); operator yields if director claims. |
| Phase detection failure (operator mis-identifies phase) | Default to inaction (silent). Director can override via explicit `verify-request` event. v3 §F's "fallback to manual" pattern reused. |
| Lane V reviewer reports go unanswered by director | Per Rule #8 (mailbox authority) + v3 §G (authority precedence), director MUST process. If director declines a finding, that's a `decision` kind event back to operator. |
| Race between operator's Lane V dispatch and director's next commit | Operator's reviewer is bounded to specific `BASE_SHA..HEAD_SHA` range. New commits don't invalidate report; report is for that range, not "current HEAD." |
| v4 adds protocol surface area; operator discipline cost increases | Lane V/D activation is OPT-IN — operator may stand down to standby behavior if context is exhausted. Phase-aware is not a hard mandate; it's an extension of available behaviors. The Phase taxonomy table is the authoritative spec; consult on each turn. |
| Counter bump pattern conflicts with Lane D commits | Lane D commits are subsystem-touching docs; counter bumps after gitnexus reindex on subsystem changes get folded per Rule #6 into the same Lane D commit (since it's the "next natural commit" by operator). No new conflict surface. |

---

## What v4 does NOT do

- Does NOT change director's loop or commit shape
- Does NOT add automation (Phase 2 territory — auto-detection deferred per existing roadmap)
- Does NOT replace the existing role partition; only EXTENDS the operator-only list
- Does NOT mandate Lane S adoption in v4 (deferred to v5)
- Does NOT introduce new TS/PY code — pure protocol/docs
- Does NOT force director to send `verify-request` for every commit (Lane V triggers on commit-landed signal, not on explicit request)

---

## Dogfood / acceptance

**v4 is "shipped" when:**
1. CLAUDE.md / AGENTS.md role-partition section extended with Lanes V/D/S (P1 phase taxonomy table inline OR linked)
2. Rule #9 added to PROTOCOL-RULES-LOG.md rule registry
3. Mailbox enum updated in `coordination/README.md`
4. This proposal file's "State at draft time" footer updated post-ship per Rule #6/#7 ship discipline
5. `STATE.md` reflects the ship (auto via hook)
6. Rule #9 row in PROTOCOL-RULES-LOG.md has `_Protocol Bundle v4 ship_` placeholder, scheduled for operator follow-up (mirror of `3e57ddf` post-v2, `d8f2407` post-v3)

**v4 is "working" when (within next 1-3 sessions):**
- ≥1 Lane V `verification-report` mailbox event dispatched and surfaced
- ≥1 Lane D `docs(arch-sync)` commit lands (likely cycle-5 pick #3 dogfood)
- No double-edit conflicts on ARCHITECTURE.md / OPERATIONS.md
- Director surfaces NO complaints about operator stepping on shared-task toes
- Operator main-context stays under ~50% of prior cycles (verification: subagent burn is in subagents, not main)

**v4 rollback trigger:** If "working" criteria fail within 3 sessions, v4 is rolled back via v4.1 (analogous to v2 → v2.1 pytest-regex fix).

---

## Ship strategy

Bundle as single commit. Race-ack body if state moves during ship (likely — director is actively shipping cycle-5).

Estimated implementation effort: ~30-45 min (similar to v3; mostly markdown across 3 files: CLAUDE.md, AGENTS.md, PROTOCOL-RULES-LOG.md, coordination/README.md).

**Files touched at ship:**
1. `CLAUDE.md` — add P1 phase taxonomy + Lane V/D/S subsections + Rule #9 line in rule registry
2. `AGENTS.md` — mirror of CLAUDE.md for non-Claude tools
3. `docs/PROTOCOL-RULES-LOG.md` — Rule #9 row in registry (with placeholder); invocation log section may gain v4 columns
4. `coordination/README.md` — mailbox enum extension
5. This proposal file — footer state update post-ship

**SHA placeholder pattern:** Rule #9 row in PROTOCOL-RULES-LOG.md ships with `_Protocol Bundle v4 ship_`; operator updates to actual ship SHA in follow-up commit per chicken-and-egg precedent (`3e57ddf` for v2 Rules #7+#8; `d8f2407` for v3 Infrastructure Audits row).

**Blocks:** None. v4 is purely additive over v2/v3 — nothing currently working breaks; lanes are opt-in extensions of operator-only role-partition list.

---

*Operator-draft proposal authored 2026-05-24; **revised 2026-05-25** incorporating director's REPLY at `8975a45` (R-D1, R-9-1, C-V1, C-Dogfood-1 accepted; **R-V1 countered** per user direction with project-data reasoning above). State at revision-commit per Rule #7: HEAD `8975a45`; branch 3 ahead of `origin/main`; working tree clean post-revision.*

***SHIPPED 2026-05-25** by director (`_Protocol Bundle v4 ship_` SHA placeholder; updated post-ship per chicken-and-egg precedent). Director accepted operator's R-V1 counter (silent ship per cycle precedent — see ship commit body for accept reasoning citing internal R-V1 / R-9-1 inconsistency + S10 36-LOC empirical counterexample). Files modified at ship: CLAUDE.md, AGENTS.md, docs/PROTOCOL-RULES-LOG.md, coordination/README.md, docs/POST-ROADMAP-2026-05-24.md (cycle-5 pick #3 reframed as operator-claimed Lane D), this file (footer). Branch ahead-count at ship: 4 commits post-revision (`5302fe6` + `c487171` + `8975a45` + `4fdcc01` + ship); push as batch following operator's cycle-precedent (v2/v3) hold-and-batch pattern.*
