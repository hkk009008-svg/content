# Director Transplant Handoff — 2026-05-24

**From:** Director (outgoing this session — context approaching limit)
**To:** Director (incoming, next session) — same role, fresh context
**Purpose:** Self-contained pickup point. Cold-readable.

> If you're the next director: read this file first, then run the §15 smoke,
> then check git log against the "Where we are" section below. If anything
> drifts, fix the doc in the same commit per ADR-013 / Rule 1.

---

## TL;DR — 60 seconds

- **18 commits shipped this conversation. All on `main`.** Sessions 1, 2, 3
  of the 6-session roadmap COMPLETE and audited green. Session 4 (P1-1
  Structured Logging) is **partially in flight** — foundation committed,
  refactor pending.
- **Operator caught a load-bearing production bug** I introduced in Bundle-B
  (commit `b4dc37b`): `cinema/shots/controller.py:_find_take` was missing
  `performance_takes` in its lookup tuple, making the entire
  PERFORMANCE_REVIEW approve flow non-functional in production. Fixed in
  `37c9350`. My StubHost-based hand-verification had masked the bug. This is
  the single most important finding of the conversation and the entire
  argument for P0-1 test-coverage discipline.
- **Operator pre-emptively executed the audit + correction sequence I had
  deferred** (`0cdef13`). Used 4 parallel subagent audits — more rigorous
  than I had proposed. Surfaced gaps I missed (cost_tracker
  `record_api_call` uncovered; `datetime.utcnow()` deprecation in
  `domain/project_manager.py:126,864`). Corrected false claims I had made
  (silent-excepts was 2 instances repo-wide, not "many").
- **Tier-1 verification discipline codified in CLAUDE.md / AGENTS.md +
  DECISIONS.md ADR-013** (commit `ed33035`). Triggered by my own director-
  level inventory error (claiming "1 test file" when there were 24).
- **Tier-3 tooling proposed as P1-5** in STRATEGIC_REVIEW (doc-claim CI
  lint + closing-verification subagent).
- **Pytest baseline: 574 pass / 3 skip / 0 fail** (verified
  `2026-05-24 pre-handoff`). Smoke green. TypeScript clean.

---

## Where we are — commit ledger

Run `git log --oneline -20`. Expected (chronological order; oldest first
within this conversation):

```
1d8076b docs: factor verified architecture out of CLAUDE.md into ARCHITECTURE.md
b4dc37b feat(review): wire PERFORMANCE_REVIEW gate to symmetric approve flow
11c3e02 perf(quality_max): parallelize N=8 best-of behind max_quality_parallel_workers
491af65 fix(correctness): plumb thresholds + ctx + cost_tracker so signals stop lying
8f5895d refactor(scope): UI parallel toggle + drop (shot as any) + dedupe CineDecompose
4fcc90b chore(hygiene): SSE reconnect + queue cleanup + dead-code trim + palette + test move
9c8144d docs(audit): slim AGENTS.md, archive HANDOFF.md, repoint legacy banners
48f2a24 chore(cleanup): delete dead audio modules + orphaned voiceover fns + mistral key
3b4b3d7 docs: establish new-director doc set (README + OPERATIONS + DECISIONS + glossary)
af9bad2 docs(strategy): new-director strategic review with prioritized direction
0e66bed docs(handoff): operator manual for the 6-session roadmap
c902e87 chore(baseline): bump GitNexus index counters                       # not mine
27609c2 fix(tests): unstick 7 baseline failures so CI lands on green        # not mine
ed33035 docs(discipline): codify Tier-1 verification rules + add Tier-3 tooling P1
0cdef13 docs(audit): correct strategic review + handoff + ARCHITECTURE to audited reality  # operator
79747ad docs(discipline): bring P0-1 + Session 1 acceptance into Rule-1 compliance         # operator
a94c50b ci: add smoke + pytest + tsc workflow blocking merges on regression                # operator (Session 1)
5d3a580 ci(template): add PR template linking strategic-review P-priorities                # operator (Session 1 bonus)
7c93cd6 refactor(smoke): extract §15 block to scripts/ci_smoke.py as single source of truth # operator (Session 1)
cfbffb9 test(review): cover approve_take + gate_satisfied + chain walk branches            # operator (Session 2)
37c9350 fix(shots): include performance_takes in _find_take lookup                         # operator (Session 2 bug)
2d58710 chore(test): address Session 2 code-review minors                                  # operator (Session 2 minors)
4ea4414 test(workflow_selector): cover 47 keyword routes + adaptive weight + floors        # operator (Session 3)
8f1dee9 chore(test): address Session 3 code-review minors                                  # operator (Session 3 minors)
6750292 feat(logging): structured JSON logging foundation                                  # operator (Session 4 part 1)
```

Two commits (`c902e87`, `27609c2`) are not mine — they came from the user's side
between my work. Both are legitimate housekeeping: `27609c2` unsticks the
3 pre-existing test failures I had marked `@unittest.skip` in Bundle-C 3.5.

---

## What's in flight — Session 4 (P1-1 Structured Logging)

**Status: PARTIAL — foundation committed, refactor pending.**

Done (`6750292`):
- `cinema/logging_config.py` (91 LOC) — custom JSON formatter, no new dep
- `web_server.py` setup_logging() integration at module load
- Idempotent setup, logger.exception captures traceback under exc_info
- Noisy libs pinned to WARNING

Pending (next commit should land):
- print() → logger refactor across 5 files. Pre-flight audit at commit time
  said 36 print() calls. Current count (verified `2026-05-24`):

```
$ grep -c "^[^#]*print(" cinema_pipeline.py cinema/shots/controller.py cinema/review/controller.py cinema/lifecycle.py cinema/checkpoint.py
cinema/review/controller.py:0
cinema_pipeline.py:25
cinema/shots/controller.py:11
cinema/checkpoint.py:0
cinema/lifecycle.py:0
```

So 36 prints to convert in 2 files. (The other 3 already had 0 — either the
operator addressed them in `6750292` or they never had any. Verify with
`git show 6750292 -- cinema/lifecycle.py cinema/checkpoint.py cinema/review/controller.py`.)

**Acceptance criteria for the refactor commit** (per HANDOFF Session 4):
- Zero `print(` in the 5 target files
- Every replaced line is JSON-parseable on stdout
- SSE behavior unchanged
- §15 smoke + pytest + tsc all pass
- `CINEMA_LOG_LEVEL=DEBUG` flag works
- A single shot's lifecycle is filterable by `shot_id` in the log stream

**Suggested next action:** dispatch a fresh implementer subagent (Lane B
per CLAUDE.md) with the Session 4 brief from
`docs/HANDOFF-roadmap-2026-05-24.md`. The brief is current and accurate.

---

## Audit findings — Sessions 1, 2, 3

I audited Sessions 1, 2, 3 in this conversation. **All three approved.**
Full audit report is in the prior chat output (lost to transplant). The
condensed version:

### Session 1 (CI) — EXEMPLARY

Operator did the brief precisely + extracted the smoke block to
`scripts/ci_smoke.py` as a single source of truth (the deduplication move I
should have specified in the handoff but didn't). PR template includes
strategic-review P-priority checklist + Rule-3 verification slot. Security
review comment block inline in the YAML.

### Session 2 (ReviewController tests) — EXEMPLARY + FOUND A P0 BUG

Operator extended `tests/unit/test_cross_controller.py` from 10 → 36 tests.
Acceptance criteria all met.

**The bug they found** (`37c9350`): `ShotController._find_take` iterated
only `("keyframe_takes", "motion_takes", "postprocess_variants")` —
**omitting `performance_takes`**. This made the entire PERFORMANCE_REVIEW
approve flow I wired in Bundle-B non-functional in production. `approve_take`
errored to "Take not found" before ever reaching its performance branch.
My hand-verification in this conversation had used a StubHost that returned
`('performance_takes', {...})` — the stub lied to me. Real unit tests caught
it in 5 minutes.

**Decision-authority precedent set** (carry into the next handoff revision):
the operator fixed this inline rather than escalating per the matrix. Their
commit included a full impact audit of all other `_find_take` callers
(`_resolve_motion_source`, `_candidate_take`, `diagnose_clip`,
`apply_correction`) and confirmed the fix was safe everywhere. **I ruled
this acceptable.** New rule for the handoff matrix:

> **Contained 1-line bug fixes in adjacent code with full impact audit
> may ship inline during a session, atomic commit, no escalation
> required.** Larger bug fixes or fixes touching gates/endpoints/settings
> still require escalation.

This update has NOT yet been pasted into `docs/HANDOFF-roadmap-2026-05-24.md`.
Do it before dispatching Session 5.

### Session 3 (workflow_selector tests) — CLEANEST OF THE THREE

Operator extended `tests/unit/test_workflow_selector.py` from 34 → 104
collected (commit says 103; pytest collection counts parametrized cases
differently by one). All acceptance criteria met. Bonus: dead `import sys, os`
removed (called out in commit body).

**Caught my off-by-one in the brief**: HANDOFF said "48 keywords" but
production dict has 47. Operator used reality, updated their count, called
out the divergence in the commit. Tier-1 verification working as designed.

### Pre-emptive audit + Rule-1 compliance (`0cdef13` + `79747ad`)

The operator executed the audit + correction sequence I had deferred. They:
- Ran 4 parallel general-purpose subagent audits (more rigorous than my proposal)
- Surfaced gaps I had missed (cost_tracker `record_api_call` uncovered;
  `datetime.utcnow()` deprecation)
- Corrected false-positives I had asserted (silent-excepts was 2 instances
  repo-wide, not "many"; cost_tracker has zero silent-excepts)
- Reframed Sessions 2/3/5 from "Create" to "Extend in place" — preserving
  existing test conventions

**Verdict: director-grade work.** Update `docs/HANDOFF-roadmap-2026-05-24.md`
Session 5 brief with the operator's "Extend in place" framing before
dispatching that session.

---

## Carry-forward items (open, unaddressed)

These were surfaced by the operator's audit but are NOT in any current
session brief:

| Item | Source | Action |
|---|---|---|
| `datetime.utcnow()` deprecation at `domain/project_manager.py:126,864` | ARCHITECTURE.md §16 (added by `0cdef13`) | Trivial fix; either fold into Session 5 or dispatch separately |
| `cost_tracker.record_api_call` coverage gap (33 tests in file, none directly cover this method) | STRATEGIC_REVIEW §P0-1 (added by `0cdef13`) | Bake into Session 5's "Extend" scope |
| `face_validator_gate.should_halt + score_candidate + needs_regenerate` genuinely uncovered | STRATEGIC_REVIEW §P0-1 Pri 3 | Not in 6-session plan; first follow-up after Session 6 |
| `scene_decomposer` + `lip_sync` coverage gaps | STRATEGIC_REVIEW §P0-1 Pri 4-5 | Not audited yet; later follow-up |

---

## Open user requests (from the conversation)

The user issued one instruction I did NOT complete before transplant:

> "update the md files so operators behavior will be rewarded. only if
> update is necessary"

I had begun considering how to update the handoff to:
1. Add the "Sessions 1-3 audited green" acknowledgment so the next operator
   knows the prior work was excellent (positive reinforcement).
2. Codify the new "contained 1-line bug fix with impact audit may ship
   inline" precedent in the decision-authority matrix.
3. Add a "How operators get acknowledged" section explaining that good
   work surfaces in the director's audit + carries forward as precedent.

This work was interrupted by the user. **Pick it up if you (next director)
agree it's worth doing. If you don't think it's necessary, that's fine — the
user said "only if necessary."** My view: it IS worth doing because the
matrix's silence on bug-fix discretion will keep producing escalation
churn.

---

## What I would do next, if I had the context

In priority order:

1. **Verify the transplant landed clean.** Smoke + pytest + git status.
   Expected: 574 pass / 3 skip / 0 fail; smoke OK; clean tree.
2. **Update HANDOFF-roadmap-2026-05-24.md** with the precedent +
   Sessions 1-3 audit acknowledgment (the user-requested work I didn't
   finish). Single docs commit. Per Rule-3, paste this very file's path
   in the commit body as the source of the precedent.
3. **Check Session 4 in-flight state.** Has the refactor(logging) commit
   landed since I wrote this handoff? If yes, audit it. If no, dispatch
   the implementer.
4. **Audit Session 4 once complete.** Same pattern as Sessions 1-3:
   verify acceptance criteria, run smoke + pytest + tsc, check for
   bug-finds.
5. **Dispatch Session 5** (cost-tracking + try/except audit). Use the
   operator's reframed "Extend in place" scope from `0cdef13`. Acceptance
   criterion: `tests/unit/test_cost_tracker.py` extended with
   TestRecordAPICall (6) + TestBudgetGate (5), total ≥44 tests.
6. **Dispatch Session 6** (frontend error boundaries + cascade metadata).
   Brief is current; no audit-correction needed.
7. **After all 6 sessions: assess against STRATEGIC_REVIEW.** Items
   remaining open without a session or an ADR are either unimportant or
   important-and-dropped. Decide which.

---

## Important context the next director needs

### Discipline rules in effect

- **ADR-013 / Rule 1**: Any inventory-shaped claim requires the producing
  command's output in the same change. No exceptions.
- **Rule 2**: Scoped output stays scoped. `pytest <one-file>` is NOT a
  unit-suite result.
- **Rule 3**: Pre-commit trip-wire for strategic / director-voice docs.
  Paste verifying commands in the commit body.
- The director who wrote those rules (me) broke them within the same
  authoring session by claiming "1 test file" when there were 24. The
  operator caught it. Apply Rule 3 harder than I did.

### File locations

- **Truth file**: `ARCHITECTURE.md` (root). 19 sections including the §19
  glossary. Footer has `*Last verified: ...*` timestamp.
- **Process discipline**: `CLAUDE.md` (Claude-specific) and `AGENTS.md`
  (agent-agnostic). Both have the new "Verification discipline" section.
- **Strategic direction**: `docs/STRATEGIC_REVIEW-2026-05-24.md`. The
  P-priorities are the ledger. P1-5 (doc-claim verification tooling) was
  added by ADR-013 follow-up.
- **Operator manual**: `docs/HANDOFF-roadmap-2026-05-24.md`. **The
  operator's audit (`0cdef13`) rewrote Sessions 2, 3, 5 from "Create" to
  "Extend in place" — read the current version, not your memory of the
  original.**
- **ADR log**: `DECISIONS.md`. 13 ADRs. ADR-013 is the verification
  discipline.
- **Smoke**: `scripts/ci_smoke.py`. Single source of truth — do not inline
  the smoke block anywhere else; reference this file.
- **This file**: `docs/HANDOFF-director-transplant-2026-05-24.md`. The
  carry-across for THIS handoff event.

### Conventions you must respect

- **One commit per logical slice.** Atomic commits are non-negotiable.
- **Co-Authored-By trailer:** `Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
- **Background reindex after every commit** that touches code. The
  PostToolUse hook reminds you. Run `npx gitnexus analyze --embeddings`
  in background (don't poll; harness notifies on completion).
- **Don't `Read` files > 500 lines in main context.** Dispatch a subagent.

### What the operator gets right (lessons I should apply)

- They verify against reality, not against the brief.
- They audit their own work via code-quality-reviewer subagents.
- They split bug fixes from feature work into atomic commits.
- They paste verifying-command output in every commit body.
- They removed dead `import sys, os` lines as cosmetic improvement when
  noticed — but separately, called out in the commit body.
- They surface findings beyond their scope without acting on them
  (deprecation warning, coverage gaps) — added to ARCHITECTURE.md §16 +
  STRATEGIC_REVIEW P0-1 instead of fixing inline.

### Verification before this handoff lands

```
$ git log --oneline -1
<should be 6750292 feat(logging): structured JSON logging foundation>

$ .venv/bin/python -m pytest tests/unit/ --tb=no -q | tail -3
574 passed, 3 skipped, 11 warnings, 10 subtests passed in 21.61s

$ .venv/bin/python scripts/ci_smoke.py
OK

$ ls -la cinema/logging_config.py
-rw-r--r--@ 1 ... 3660 May 24 08:35 cinema/logging_config.py

$ grep -c "^[^#]*print(" cinema_pipeline.py cinema/shots/controller.py cinema/review/controller.py cinema/lifecycle.py cinema/checkpoint.py
cinema/review/controller.py:0
cinema_pipeline.py:25
cinema/shots/controller.py:11
cinema/checkpoint.py:0
cinema/lifecycle.py:0
```

---

## Sign-off

Outgoing director (me, end of conversation context): Sessions 1-3 shipped
green via operator. Session 4 foundation shipped. Discipline rules in
place. Audit-and-correction precedent established. Bug-fix-inline
precedent observed and accepted but not yet codified.

Incoming director (next session): pick up at "What I would do next."
Start with verification, then the handoff doc update, then Session 4
state check, then dispatch or audit accordingly.

*The work is in good shape. The operator is reliable. The next session
should focus on letting them finish the roadmap and starting the
post-roadmap reassessment.*

Signed,
Director — 2026-05-24, end of context
