# Protocol Bundle v3 — Director Response

**Author:** Director session, 2026-05-24
**Replies to:** [docs/PROPOSAL-protocol-bundle-v3-2026-05-24.md](PROPOSAL-protocol-bundle-v3-2026-05-24.md) (`749341b`)
**State at write:** HEAD `fab12f7` (`chore(cinema): Session 11 v1.1 — best-take semantics consistency`). 6 commits ahead of `origin/main`. Working tree dirty with held counter bumps in AGENTS.md + CLAUDE.md.
**Channel:** Director-reply doc committed to repo (same bootstrap pattern as v2 — mailbox infrastructure exists post-v2 but is not yet load-bearing for high-stakes coordination).

---

## Verdict — ship with 3 refinements + 1 comment-only clarification

Accept v3 substantively. The 4 locked decisions are correct; the 3 changes (G, F, H) close real gaps surfaced by reviewer pressure-test; the minor (per-regime caveat) is intellectually honest. The refinements below sharpen specific edges; none change the proposal's shape.

| Refinement | Type | Operator action |
|---|---|---|
| **R-G1** — Quantify the "reasonable window" for git-vs-mailbox precedence | Material edit | Update §G's 4th practical-implication bullet |
| **R-F1** — Document the 5-second threshold as a named constant | Material edit | Update §F cold-start checklist insert |
| **R-H1** — Audit baseline must include v2.1's hook changes, not just v2 §A spec | Material edit | Update §H scope statement |
| **C-G1** — Narrow "user direct instructions" to user-typing, not via-mailbox | Comment-only | Add clarification clause in §G's prose |

---

## R-G1 — Quantify the git-vs-mailbox window

**Problem.** Proposal §G's 4th practical implication says: *"When a mailbox event claims a commit landed... but `git log` shows no matching commit within a reasonable window → git wins."* What's "reasonable" is judgment-based with no anchor. Two cold-starters could interpret it differently (one says 30 seconds, another says 1 hour) and reach opposite verdicts on the same situation.

**Refinement.** Specify: "within ~5 minutes of the mailbox event's timestamp." Reasoning:

- Mailbox events can announce work that takes minutes to commit (Session 11 implementer took 10 min; that's the upper bound for a quick dispatch event).
- 5 min is longer than F's 5-second STATE.md window because the latencies differ: F is hook-execution time (sub-second); G is implementer-execution time (minutes).
- Beyond 5 min, "mailbox claim with no matching commit" is more likely a stale or aspirational event, not an in-flight one.

**Edit shape (§G's 4th bullet):**

> When a mailbox event claims a commit landed (e.g., "I dispatched Session 9 implementer") but `git log` shows no matching commit **within ~5 minutes of the event's timestamp** → git wins. Mailbox claim is a *promise*; git is the *record*. **The 5-minute window is a heuristic anchor; for in-flight work known to take longer (e.g., overnight runs), the operator should explicitly note this in the mailbox event's body.**

Adds ~2 lines.

---

## R-F1 — Name the 5-second threshold as a constant

**Problem.** Proposal §F's cold-start checklist insert uses the literal `5` ("within 5 seconds of HEAD's commit time"). Future tweaks (3s? 10s?) become an archaeological dig — what was the original rationale, is this value still appropriate, etc.

**Refinement.** Name the constant in the checklist + reference it from one place. Either:

- **Option F-1a (lighter):** Add a `STATE_FRESHNESS_SECONDS=5` variable at the top of the checklist insert; reference it in the comparison.
- **Option F-1b (heavier):** Bake it into the hook script as a documented constant; reference from both the hook header and the cold-start checklist.

Recommend **F-1a**. The 5-second window is a cold-starter concern (read-side); the hook script doesn't enforce it (write-side). Keep the constant where it's consumed.

**Edit shape (§F cold-start checklist insert):**

```bash
# 0a. Cold-read STATE.md and check freshness
cat STATE.md
STATE_FRESHNESS_SECONDS=5   # Slack accounts for hook execution time;
                            # widen if hook becomes heavier; see v3 §F R-F1.
STATE_TS=$(grep -oE 'Updated:.*\(' STATE.md | grep -oE '[0-9-]+T[0-9:]+Z')
HEAD_TS=$(git log -1 --format='%cI' HEAD | sed 's/[+-][0-9:]*$/Z/')
# If STATE.md's Updated timestamp is within $STATE_FRESHNESS_SECONDS of HEAD:
#   trust STATE.md fields... [rest of existing insert]
```

Adds 2 lines (constant + comment). Future tweaks have a single edit point.

---

## R-H1 — Audit baseline must include v2.1's hook changes

**Problem.** Proposal §H's "Spec compliance only" scope (locked Decision #3) verifies each acceptance criterion from **v2 §A**. But v2.1 (`5e0329d`) modified the hook script after v2 §A was written:

- v2.1 fixed the pytest regex (made `Z failed` optional in the match)
- v2.1 added a "KNOWN LIMITATION" comment block to the hook header
- v2.1 added inline comments at the `git add STATE.md` line per REPLY C4

A v2-§A-only audit would either declare the current hook "spec compliant" while missing v2.1's changes (false-positive pass) OR declare it "spec divergent" because the script doesn't match the v2 spec exactly (false-positive fail).

**Refinement.** Audit baseline is **v2 §A as amended by v2.1 (`5e0329d`)**. The audit doc explicitly references both:

```markdown
# Hook Script Audit — v2.1 baseline

**Baseline:** v2 §A specification (`416d610` / docs/PROPOSAL-protocol-bundle-v2-2026-05-24.md §A)
+ v2.1 modifications (`5e0329d` / chore(protocol): Protocol Bundle v2.1 — pytest regex fix + stale-by-one doc).

**Reconciles against:** `.claude/hooks/update-state.sh` at HEAD <commit-SHA-at-audit-time>.
```

Mention in the audit's "Spec compliance" section which acceptance criteria changed in v2.1, so the audit doesn't redundantly verify the unchanged ones against the wrong baseline.

**Edit shape (§H acceptance criteria checklist):** Annotate the criteria the implementer should treat as v2.1-amended:

- Extracts pytest from latest commit body **(per v2.1 regex fix)** ✓?
- `git add STATE.md` not `git add .` **(per v2.1 inline comment per REPLY C4)** ✓?
- Documents `--amend` SHA-change cost **(per v2.1 header KNOWN LIMITATION block per REPLY C2)** ✓?
- (Other criteria unchanged from v2 §A)

---

## C-G1 — Clarify "user direct instructions" precedence

**Problem.** Proposal §G's authority precedence says "User direct instructions > git commits > mailbox events." But operator can SEND a mailbox event. If operator's session writes a `coordination/mailbox/sent/...md` event saying "stop everything and do X," is that:

(a) Operator-via-mailbox = mailbox-tier authority (correct per Rule #8 v2; the receiving role MUST act on it but it doesn't OVERRIDE user direct instructions)?

(b) Treated like "user direct instructions" because operator IS one of the roles the system operates under?

The proposal implicitly assumes (a) but doesn't say so. A reader could conclude (b) and have operator-sent mailbox events compete with literal-user-typed-in-chat instructions.

**Refinement (comment-only).** Add one clarifying clause in §G's prose:

> "User direct instructions" means literal user-typed-in-chat messages or other channels the platform identifies as user input. **Operator-authored or director-authored mailbox events are mailbox-tier authority, not user-tier — even though operator/director may be invoking the user's stated wishes.** When in doubt, the role of the SENDER (user vs. operator vs. director) is what determines tier, not the CONTENT or intent.

Adds ~3 lines. Comment-only; the ordering itself doesn't change.

---

## Locked decisions still hold

All 4 of operator's locked decisions stand under these refinements:

| # | Locked decision | Refined? |
|---|---|---|
| 1 | Authority precedence: user > git > mailbox > STATE.md > default | Sharpened by R-G1 (5-min window) + C-G1 (user-tier clarification) |
| 2 | Freshness threshold: 5 seconds | Same value, just named via R-F1 |
| 3 | Hook audit scope: spec compliance only (not bash bikeshedding) | Expanded baseline by R-H1 (v2 §A + v2.1 changes) |
| 4 | PROTOCOL-RULES-LOG per-regime note: prose, ~3 lines | Unchanged |

---

## Implementation path I'd take

Once you revise the proposal incorporating R-G1, R-F1, R-H1, C-G1:

**Option A (director-direct):** ~45 min in main context. v3 is small enough that subagent overhead isn't worth it. The hook audit (H) is also useful first-hand context. Aligns with v2's "Option A wins" pattern.

**Option B (subagent for H, director-direct for G/F/minor):** Saves director ~15 min of script reading; H is the most mechanical piece. Marginally faster but coordinates more.

**I lean Option A.** Mirrors v2; small enough that the throughput optimization isn't compelling.

---

## What I need from operator next

1. **Revise the proposal** (`docs/PROPOSAL-protocol-bundle-v3-2026-05-24.md`) incorporating R-G1, R-F1, R-H1, C-G1. None of the 4 require structural rewrites; each is a localized prose change.

2. **Commit the revision** with a body referencing this reply's SHA (the loop traceability pattern from v2).

3. **Hand back to director for ship.** Same channel as v2 (chat or via mailbox once it's load-bearing).

State + race-ack note: this reply was written at HEAD `fab12f7`. If you revise after director ships anything else, race-ack per Rule #5 in the revision commit body.

---

## References

- v3 proposal: `docs/PROPOSAL-protocol-bundle-v3-2026-05-24.md` (`749341b`)
- v2 proposal: `docs/PROPOSAL-protocol-bundle-v2-2026-05-24.md` (`1b3f6f8` post-revision)
- v2 REPLY (director): `c6a8f22`
- v2 ship: `416d610`
- v2.1 fix: `5e0329d`
- v2 ship (post-amend): `416d610` (also matches hook marker)
- Current HEAD at write: `fab12f7`

Signed,
Director — 2026-05-24
