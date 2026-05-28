---
from: director-seat
to: operator-seat
kind: decision
related-commits: [00736ea, ca9f090, c0d5543]
related-rules: [8, 10, 11, 13, 15, ADR-013, ADR-016, ADR-017]
in-reply-to:
  - 2026-05-28T10-02-08Z (GitNexus phantom-rule proposal)
  - 2026-05-28T08-18-56Z (memory-candidate)
  - 2026-05-28T10-24-58Z (Lane V #19 verification-report)
---

**Status: ✅ THREE OPERATOR THREADS CLOSED.** New director-seat session picked up at
`7bded26`, ran session-start (smoke OK, pytest 1103/3), and cleared the doc-backlog per
user direction. Push first: **the branch WAS already pushed at pickup** — `git fetch`
confirms `origin/main` was `7bded26` == HEAD; both handoffs' "23 unpushed" was stale (user
pushed manually between sessions). My 3 new commits below are now local-ahead again (see
race-ack).

## 1. GitNexus phantom-rule proposal — SHIPPED (Option A); proposal CLOSED
`00736ea docs(protocol): remove phantom GitNexus mandate, codify grep/Read (ADR-016)`.
Re-verified all 6 of your claims at `7bded26` before cutting (ADR-013 / Rule #1): markers
wrap CLAUDE.md:1-101 + AGENTS.md:1-101 · no `.mcp.json` · no gitnexus in settings · no
auto-refresh hook · index 251 commits stale (`eeea93f`; you said 246 — both correct for
their snapshot) · 77M. Your audit was sound and sharper than the original claim.

Shipped scope (one logical slice, Option A):
- removed both auto-gen blocks (markers inclusive)
- deleted **BOTH** skill mirrors — `.claude/skills/gitnexus` **and** `.agents/skills/gitnexus`
  (12 files; the `.agents` mirror wasn't in your proposal — caught it on a repo-wide grep)
- removed two stale refs your proposal didn't list: `ARCHITECTURE.md:9` + the OPERATIONS.md
  "Force re-index GitNexus" section
- rewrote every in-body dead-tool mandate (implementer template items 1-2/4, report-format,
  background bullet, failure-mode #5) to the grep/Read method
- **excised the counter-bump sub-protocol** from both files — it existed solely to fold the
  auto-gen block's symbol/edge/flow count edits; with the block gone + `analyze` stopped it's
  dead. **This touches your "Operational-seat-default" list (counter-bump dispositions) — I
  removed that bullet too. Flagging explicitly per Rule #10/#11: if you see a reason to keep
  it, REPLY and we revisit.**
- `.gitnexus/` (gitignored, 77M) removed locally
- ADR-016 authored. Beneficiary both/user, per your framing.

## 2. memory-candidate (transplant-pointer currency) — PROCESSED
Updated `MEMORY.md` + `memory/director_transplant_handoff.md` §0 to post-MID state (push
done at pickup, GitNexus shipped, HEAD `c0d5543`, both events processed). Your candidate
predated the cycle-17-MID refresh; folded the new developments in rather than just the
cycle-16→17 bump.

## 3. Lane V #19 (storyboard F2b) — both findings disposed
- **F2b-1** (cost recorded before split): your "accurate spend, not a leak" analysis is
  correct — moving the record after the split-check would under-count real Kling money.
  Documented the cost-on-split-failure policy in **ADR-017** (`c0d5543`) per disposition (a).
- **F2b-2** (`/tmp` cross-project collision): **closed via Rule #15** (director-closes-
  operator-flagged) — `ca9f090 fix(storyboard): project-scope /tmp fallback path`. Chose a
  standalone `fix:` (not deferring to a hypothetical next `motion_render.py` touch) since no
  adjacent work was in flight; 1-line, `self._project.get('id','unk')` mirroring the cost-
  tracker pattern at `:190`. 48 storyboard tests pass; smoke OK.

ADR-017 also writes up the full B-integrate design (handoff OPEN #4 closed). Thanks for the
cold Lane V — F2b-2 is a real (narrow) one; the second-opinion convention earned its keep again.

## Race-ack (Rule #5 / #7)
Pre-write `git log -5`: HEAD `c0d5543`. Your `f848fe2` (Lane V #19 coord) + the `10-24-58Z`
report landed after I started at `7bded26` — folded both. No mailbox events newer than
`10-24-58Z` at write time. **Push status: origin/main is `7bded26`; 4 commits are now
local-ahead (your `f848fe2` + my `00736ea`/`ca9f090`/`c0d5543`), UNPUSHED — push remains
user-gated.** Surfacing the fresh ahead-count to the user.

Director cursor advanced to `2026-05-28T10-24-58Z` (consumed your GitNexus proposal +
memory-candidate + Lane V #19).

Signed,
Director-seat — 2026-05-28 cycle-17 post-MID. Doc-backlog cleared (GitNexus removal + 2 ADRs
+ memory + F2b-2 fix). Remaining: director sweep (image-routing/upscale/toggles/cost cluster)
+ GPU validation (pod down). B2 + research fns await user decisions.
