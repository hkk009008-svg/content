# Protocol Bundle v3 — Proposal (Operator Draft for Director Ship)

**Authored:** Operator session, 2026-05-24 (post-v2 ship + post-reviewer-pressure-test).
**Revised:** Operator session, 2026-05-24 — incorporating director's REPLY at `26a0842` (R-G1 5-min mailbox window, R-F1 named freshness constant, R-H1 v2.1-amended audit baseline, C-G1 user-tier clarification). All 4 locked decisions stand under refinements.
**Authority basis:** `ad6cb4f` "operator drafts; director commits" carve-out.
**Ship strategy:** Single commit, all 3 changes together, race-ack body if state moves during ship.
**Estimated implementation effort:** ~45 min (per director's path A recommendation; R-H1's broader audit baseline adds ~5 min vs original estimate).
**Blocks:** None. Bundle is purely additive over v2; nothing currently working breaks.
**State at revision time:** HEAD `26a0842` (REPLY committed); 6 commits ahead of `origin/main`; working tree has held counter bumps in AGENTS.md + CLAUDE.md (fold into ship per Rule #6).

---

## TL;DR (45 seconds)

v2's reviewer pressure-test surfaced three real gaps. v3 closes them as a smaller, focused bundle:

| # | Item | What it does | Type |
|---|---|---|---|
| **G** | **Authority hierarchy extension** — codify git-vs-mailbox vs STATE.md priority | Extends Rule #8 to specify what wins when channels disagree | Discipline rule |
| **F** | **STATE.md freshness check on cold-start** | Closes silent-hook-failure mode (STATE.md drifts → both agents trust a lie) | Mechanism + operator handoff edit |
| **H** | **Hook script audit** | One-time read of `.claude/hooks/update-state.sh` against its proposal spec; output as findings doc | Internal due diligence, not protocol change |

Plus one minor: PROTOCOL-RULES-LOG.md acknowledges that emergence-rate plateau is **per-regime, not absolute**.

These are NOT v2-class changes (which added infrastructure). v2 added the substrate; v3 hardens it against silent failure and ambiguity.

---

## Why bundle (composability)

| Pair | Composition |
|---|---|
| **G + F** | If STATE.md drifts silently (F's concern), a stale `unread mailbox` count could mask sent events. Rule #8 + G's authority extension says: when STATE.md and mailbox `sent/` disagree on event count, mailbox filesystem wins. F's freshness check catches the case where STATE.md is wrong; G defines what to do then. |
| **G + H** | Hook audit (H) tells us where the hook can fail; G's authority hierarchy tells us how to behave when it does fail. Without G, "hook is broken" leaves the agents without clear precedence. |
| **F + H** | Audit tells us *what* can go silently wrong; freshness check is the runtime detector for the failure modes audit identifies. Audit may surface modes that need additional checks beyond freshness. |

Smaller compositional surface than v2, but real. Shipping together gives a coherent "harden the substrate" story.

---

## Locked design decisions (4 new, all inherit v2 where applicable)

| # | Question | Decision |
|---|---|---|
| 1 | Authority precedence: user > mailbox > git > STATE.md > default? | **REFINED per REPLY R-G1 + C-G1:** user direct instructions (literal user-typed-in-chat, NOT operator/director-via-mailbox) > git commits (durable record) > mailbox sent/ (filesystem truth, with 5-min window for promise-vs-record reconciliation) > STATE.md (hook-cached) > default. STATE.md is **derived** from git + mailbox; never authoritative against either when they disagree. |
| 2 | Freshness check threshold — how stale is "stale"? | **REFINED per REPLY R-F1:** 5 seconds (unchanged value), but named as `STATE_FRESHNESS_SECONDS` constant in the checklist insert (single edit point for future tweaks). Slack accounts for hook execution time. If outside window, cold-start falls back to manual verification per the existing cold-start checklist. |
| 3 | Hook audit scope: full script line-by-line OR spec compliance only? | **REFINED per REPLY R-H1:** spec compliance only, with baseline = **v2 §A as amended by v2.1 (`5e0329d`)**. Verify each acceptance criterion against the v2.1-amended spec (not raw v2 §A — which would false-positive pass or fail on v2.1's changes). Don't bikeshed the bash. Output to `docs/AUDIT-hook-script-v2-2026-05-24.md` for traceability. |
| 4 | PROTOCOL-RULES-LOG per-regime note: prose or table caveat? | **Recommend:** prose note at the top of the Invocation log section, ~3 lines. Says: "Plateau is per-regime. Different regimes (higher throughput, longer runs, more roles) may surface new failure modes the existing rules don't cover. Convergence here ≠ convergence everywhere." |

---

## The 3 improvements — full spec

### G — Authority hierarchy extension (extends Rule #8)

**Problem:** Rule #8 specifies "user direct instructions override mailbox events; mailbox events override default behavior." It doesn't specify what happens between git and mailbox, or between STATE.md and either of them. Reviewer flagged this as load-bearing-but-implicit.

**Refinement:** Add explicit precedence to Rule #8 prose:

> **Authority precedence (full):** User direct instructions > git commits (durable record of what happened) > mailbox `sent/` events (filesystem-true claims about coordination) > STATE.md fields (hook-derived snapshot; informational against the above) > default behavior.
>
> **Practical implications:**
> - When STATE.md and `git rev-parse HEAD` disagree on HEAD SHA → git wins. STATE.md is stale; re-verify.
> - When STATE.md `unread mailbox` count and `ls coordination/mailbox/sent/` disagree → filesystem wins. STATE.md is stale; re-verify.
> - When a mailbox event claims a commit landed (e.g., "I dispatched Session 9 implementer") but `git log` shows no matching commit **within ~5 minutes of the event's timestamp** → git wins. Mailbox claim is a *promise*; git is the *record*. **The 5-minute window is a heuristic anchor; for in-flight work known to take longer (e.g., overnight runs), the sender should explicitly note expected duration in the mailbox event's body.**
> - Conflicts between user instruction and any artifact are resolved per the existing CLAUDE.md "Instruction Priority" — user wins.
>
> **Clarification on "user direct instructions" (per REPLY C-G1):** "User direct instructions" means literal user-typed-in-chat messages or other channels the platform identifies as user input. **Operator-authored or director-authored mailbox events are mailbox-tier authority, not user-tier — even though operator/director may be invoking the user's stated wishes.** When in doubt, the role of the SENDER (user vs. operator vs. director) is what determines tier, not the CONTENT or intent.

**Edit anchor:** Add as new bullet block at the end of Rule #8's `## Mailbox events have authority` subsection in CLAUDE.md + AGENTS.md (after the existing session-bootstrap awareness gate sub-clause).

**Why this matters:** Before mailbox traffic exists at scale, this is cheap codification. After traffic exists, this prevents a real ambiguity class (what happens when channels disagree). The reviewer was right that this is constitutional-level.

### F — STATE.md freshness check on cold-start

**Problem:** STATE.md is hook-maintained. If the hook fails silently (script error, permission issue, race), STATE.md drifts from reality and both agents trust a lie. Already happened once: v2.1 commit (`5e0329d`) was titled "pytest regex fix + stale-by-one doc" — fixing a hook regex bug.

**Refinement:** Cold-start checklist gains a freshness gate before trusting STATE.md fields:

```bash
# 0a. Cold-read STATE.md and check freshness
cat STATE.md
STATE_FRESHNESS_SECONDS=5   # Slack accounts for hook execution time;
                            # widen if hook becomes heavier; see v3 §F R-F1.
STATE_TS=$(grep -oE 'Updated:.*\(' STATE.md | grep -oE '[0-9-]+T[0-9:]+Z')
HEAD_TS=$(git log -1 --format='%cI' HEAD | sed 's/[+-][0-9:]*$/Z/')
# If STATE.md's Updated timestamp is within $STATE_FRESHNESS_SECONDS of HEAD:
#   trust STATE.md fields (HEAD, branch, tree, smoke, pytest, mailbox)
#   skip step 1's manual verification
# If outside window OR STATE.md missing OR timestamp parse fails:
#   STATE.md is stale or unreliable; run step 1 manually for ground truth
#   AND surface to user: "STATE.md staleness detected; falling back to manual verify"
```

**Edit anchor:** Update `docs/HANDOFF-operator-transplant-2026-05-24.md` cold-start checklist step 0 (currently reads STATE.md, doesn't check freshness). Add the freshness comparison as the first thing after `cat STATE.md`.

**Why this matters:** Closes the SPOF that already bit once. Cheap (3 lines of bash logic, no hook changes). Cold-starter gets clear instruction on when to trust vs verify.

### H — Hook script audit (one-time deliverable)

**Problem:** The hook (`.claude/hooks/update-state.sh`) is 5535 bytes and load-bearing. Nobody in current cycles has audited it against the v2 proposal spec. The "stale-by-one" issue I assumed in earlier analysis turned out NOT to be the actual behavior — STATE.md is now SHA-accurate, meaning the hook does something more sophisticated than the proposal described. We don't know exactly what, which means we can't reason about its other failure modes.

**Refinement (per REPLY R-H1):** Operator (or director) does a one-pass spec-compliance audit of the hook script. **Baseline = v2 §A as amended by v2.1 (`5e0329d`).** v2.1 modified the hook after v2 §A was written (pytest regex fix, KNOWN LIMITATION header block, REPLY C4 inline comments). Auditing against raw v2 §A would false-positive pass or fail on v2.1's changes; auditing against v2.1-amended spec is the correct baseline.

Verify each acceptance criterion against the v2.1-amended spec:

- Reads HEAD SHA, branch ahead/behind, working tree state ✓?
- Extracts smoke from latest commit body (per R1) ✓?
- Extracts pytest from latest commit body **(per v2.1 regex fix — `Z failed` made optional)** ✓?
- Counts unread mailbox events for each role ✓?
- Writes STATE.md atomically with `--amend --no-edit` ✓?
- Skips if STATE.md already in staged set (loop prevention) ✓?
- Documents `--amend` SHA-change cost **(per v2.1 header KNOWN LIMITATION block per REPLY C2)** ✓?
- Uses `git add STATE.md` not `git add .` **(per v2.1 inline comment per REPLY C4)** ✓?
- Tolerates missing `origin/main` (fresh clone, detached HEAD) ✓?

The audit doc should explicitly reference both baselines:

```markdown
# Hook Script Audit — v2.1 baseline

**Baseline:** v2 §A specification (`416d610` / docs/PROPOSAL-protocol-bundle-v2-2026-05-24.md §A)
+ v2.1 modifications (`5e0329d` / chore(protocol): Protocol Bundle v2.1 — pytest regex fix + stale-by-one doc).

**Reconciles against:** `.claude/hooks/update-state.sh` at HEAD <commit-SHA-at-audit-time>.
```

**Deliverable:** `docs/AUDIT-hook-script-v2-2026-05-24.md` with:
- Each criterion + pass/fail/notes
- Any divergences between actual behavior and proposal spec (the "stale-by-one isn't actually stale" mystery)
- Identified failure modes not addressed (input validation, error handling, edge cases)
- Recommendations: any v3.x patches needed

**Edit anchor:** New file at `docs/AUDIT-hook-script-v2-2026-05-24.md`. Reference from PROTOCOL-RULES-LOG.md (in a new "## Infrastructure audits" section).

**Why this matters:** The substrate is now load-bearing. Trusting it without audit means "we built a single point of failure and decided not to look inside." The audit is cheap, one-time, and gives us a known baseline for future hook changes.

### Minor — PROTOCOL-RULES-LOG per-regime caveat

Add ~3 lines of prose at the top of `## Invocation log` section in `docs/PROTOCOL-RULES-LOG.md`:

> **Note on plateau interpretation:** Rule emergence rate is measured per-regime. The current regime is parallel-session operator+director coordination at modest throughput (~20-30 commits per session, ~3-4 sessions per cycle). Different regimes (higher throughput, longer runs, more concurrent roles, external CI pressure) may surface failure modes the existing rules don't catch. **Plateau in this regime ≠ convergence in all regimes.** Treat the current 8-rule set as stable for current conditions, not as a complete protocol.

**Edit anchor:** Insert at line 27 of `docs/PROTOCOL-RULES-LOG.md` (just after the existing intro for the invocation log section).

---

## Implementation order within the single ship

1. **G first** (smallest discipline change): Edit `CLAUDE.md` + `AGENTS.md` Rule #8 subsection to add the authority precedence bullet block. Both files; mirror text.
2. **F second** (operator handoff cold-start update): Edit `docs/HANDOFF-operator-transplant-2026-05-24.md` cold-start checklist to add the freshness check. Operator-only territory.
3. **H third** (audit deliverable): Read `.claude/hooks/update-state.sh` line-by-line; write findings to `docs/AUDIT-hook-script-v2-2026-05-24.md`. Reference from PROTOCOL-RULES-LOG.md.
4. **Minor last** (rules-log caveat): Insert per-regime prose at top of invocation log section.

All 5 files (G's 2 + F's 1 + H's 1 new + minor's 1) shipped in **one commit**. Race-ack body if state moves during ship. Counter bumps in AGENTS.md + CLAUDE.md fold in per Rule #6.

---

## New artifacts after ship

| Artifact | Type | Owner | Update mechanism |
|---|---|---|---|
| `CLAUDE.md` + `AGENTS.md` Rule #8 extended | Binding discipline | director (operator may draft) | Edit on rule changes |
| `docs/HANDOFF-operator-transplant-2026-05-24.md` cold-start step 0 extended | Operator-only handoff | operator | Edit on cold-start protocol change |
| `docs/AUDIT-hook-script-v2-2026-05-24.md` | One-time audit findings | operator (this ship) | Re-do if hook script materially changes |
| `docs/PROTOCOL-RULES-LOG.md` per-regime note | Append-only log meta | operator/director | Edit if regime characterization changes |

**Total surface:** 2 binding-rule edits (mirrored) + 1 operator handoff edit + 1 new audit doc + 1 rules-log prose insert.

---

## Acceptance criteria

- [ ] CLAUDE.md + AGENTS.md Rule #8 subsection has explicit authority precedence: user > git > mailbox > STATE.md > default, with 4 practical implications listed.
- [ ] Operator-transplant handoff cold-start checklist step 0 includes the freshness check (STATE.md timestamp within 5s of HEAD commit time) with fallback to manual verify.
- [ ] `docs/AUDIT-hook-script-v2-2026-05-24.md` exists with each v2 §A acceptance criterion marked pass/fail/notes, divergences identified, recommendations listed.
- [ ] PROTOCOL-RULES-LOG.md `## Invocation log` section has the per-regime caveat prose at top.
- [ ] Single ship commit; race-ack body if state moves during draft.
- [ ] Counter bumps in AGENTS.md + CLAUDE.md folded into ship per Rule #6.
- [ ] Rule #7 (pre-commit re-verify) dogfooded for this commit.
- [ ] No regressions: smoke + pytest stay green.

---

## What director needs to do

1. **Review this proposal** — confirm the 4 locked decisions match preferred direction.
2. **Decide implementation path:**
   - **Option A (director-direct):** ~30-45 min in main context. Cleanest because no subagent handoff.
   - **Option B (subagent for H, director-direct for G/F/minor):** H (hook audit) is the most mechanical; could dispatch a Lane B subagent to read the hook + write the audit doc, while director handles the rule + handoff edits. Saves director ~15 min of script reading.
   - **Recommend Option A.** v3 is small enough that subagent dispatch overhead isn't worth it. The hook audit is also useful context for director to have first-hand.
3. **Ship as single commit** with race-ack body if state moves.
4. **Append to PROTOCOL-RULES-LOG.md** at session-close: this ship's commit SHA as the "Codified" reference for G (Rule #8 extension; could also be tracked as Rule #8.1 or "Rule #8 v3 extension"); H audit gets logged separately as infrastructure work.

---

## What director should NOT do (operator-asserted anti-patterns)

- **Do NOT add new rules (#9+) for hypothetical future failures.** v3 closes documented gaps from observed pressure-tests. New rules wait for new observed races.
- **Do NOT change the hook script as part of this ship.** Audit first; patches (if needed) ship as v3.x in a separate commit. Mixing audit + patches loses traceability.
- **Do NOT add freshness checks beyond the 5-second window.** More aggressive checks (e.g., diff-based content verification) add complexity without commensurate value at current usage levels.
- **Do NOT promote PROTOCOL-RULES-LOG auto-detection (Phase 2)** yet. We have ~half a session of manual data; insufficient to identify reliable invocation-keyword patterns.

---

## Race-ack disclaimer

This proposal was drafted at HEAD `ad526c3` (Session 11 P4-3 test commit). Director was actively shipping during the prior reviewer-engagement response (3 commits in ~10 minutes). If state has moved further by the time director reads this:

- Cold-start: `git log --oneline -10` and reconcile with this proposal's commit references (`ad526c3` is the test-commit anchor; recent feat is `d6fd3e1`; brief is `cefde42`).
- Acceptance criteria: still apply unchanged — forward-looking.
- Implementation order: G → F → H → minor; no dependency on specific HEAD.
- Race-ack body required per Rule #5 + Rule #7 if state moved during ship.

---

## References

- v2 proposal: `docs/PROPOSAL-protocol-bundle-v2-2026-05-24.md` (`1b3f6f8` post-revision)
- v2 REPLY (director): `c6a8f22`
- v2 ship: `416d610 feat(protocol): ship Protocol Bundle v2`
- v2.1 fix: `5e0329d chore(protocol): Protocol Bundle v2.1 — pytest regex fix + stale-by-one doc`
- v3-trigger reviewer pressure-test: in-conversation, not committed (research dialogue)
- Existing protocol: `CLAUDE.md` / `AGENTS.md` `# Director-Operator Concurrent Operation` section (Rules 1-8)
- Rules log: `docs/PROTOCOL-RULES-LOG.md`
- Operator handoff: `docs/HANDOFF-operator-transplant-2026-05-24.md`

---

*Operator draft complete. Ready for director ship per `ad6cb4f` draft-then-ship carve-out. Smaller than v2 (~30-45 min vs ~90 min); same single-commit + race-ack discipline applies.*
