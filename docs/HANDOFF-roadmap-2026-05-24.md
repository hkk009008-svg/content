# Operator Handoff — 6-Session Roadmap

**From:** Director (incoming, 2026-05-24)
**To:** Operators (engineering sessions / AI agents executing the roadmap)
**Source plan:** [docs/STRATEGIC_REVIEW-2026-05-24.md](STRATEGIC_REVIEW-2026-05-24.md)
**Status:** Active — execute in order unless you're told otherwise

This document is the manual. It tells you **what** to do, **why** it
matters, **how** to do it well, and **what done looks like**. Read the
preface once. Then jump to your assigned session.

---

## Preface — How to read this handoff

You are receiving this handoff because you are about to execute one of
six sessions on the post-pivot Content cinema pipeline. Each session
has a numbered brief below — find yours and stay there.

**Before any session work:**

1. Run the §15 smoke block in [ARCHITECTURE.md](../ARCHITECTURE.md). If
   it fails, stop and surface to the director — your baseline is broken,
   no session work is appropriate until it's restored.
2. Read [docs/STRATEGIC_REVIEW-2026-05-24.md](STRATEGIC_REVIEW-2026-05-24.md)
   §"What's working — keep" and the section for your session's P-level.
   This gives you the *why* in director voice.
3. Read the relevant ARCHITECTURE.md sections referenced in your brief.
4. Open this file and re-read YOUR session's brief in full. Do not skim.

**While working:**

- One commit per logical slice (see [CLAUDE.md](../CLAUDE.md) §"When you change something").
- If you find a stale claim in ARCHITECTURE.md or this handoff, fix it
  **in the same commit** that exposes the staleness. This is non-negotiable.
- Don't combine concerns. A test isn't a refactor isn't a feature.
- If your change touches a subsystem documented in ARCHITECTURE.md,
  update the relevant section in the same PR.

**When finished:**

- Report status in the format documented in §"Status report" below.
- Move to the next session in the roadmap, or stop if you've hit the
  session boundary your assignment specified.

**If you're stuck:**

- See §"How to handle blockers" below. Don't grind in silence — escalate.

---

## General operating principles

These apply to every session. They're director-level expectations.

### 1. Verify before you assert

Don't claim something works because you wrote it; claim it works because
you ran it. Every PR must include verification output (test pass count,
manual-run logs, screenshot of UI behavior). "It should work" is not
acceptable.

### 2. Test the negative case

For every assertion test, write a "this would have failed before"
counterpart. If your test would still pass when the underlying behavior
is broken, the test is decorative, not protective.

### 3. Smaller is better

A 30-line commit is easier to review than a 300-line commit, and
1/10th as likely to roll back. If your session naturally produces a
large diff, split it. Use the multi-commit pattern in
[CLAUDE.md](../CLAUDE.md) §"Commit discipline for reviewability".

### 4. Touch what you need to touch

Drive-by refactors are forbidden. If you notice a related issue while
working, file it in the strategic review or skip it. The commit you're
making is for the assigned task only.

### 5. Documentation is part of the deliverable

Code without a documented contract is half a deliverable. Docstrings on
new public functions. Comments on non-obvious decisions. ARCHITECTURE.md
update when subsystems shift. This isn't optional.

### 6. Honor what previous directors did

The architecture has clear shape (single entry, predicate-poll gates,
identity singleton, etc.). Don't redesign these unless your session
explicitly says to. If you think a foundation needs changing, raise it
via the strategic review process — don't rewrite it in your session.

### 7. Director's voice on conflict

When the strategic review and your judgment conflict on **what** to do,
the strategic review wins until overturned. When this handoff and the
strategic review conflict on **how** to do it, this handoff wins (more
specific). When this handoff and the actual code conflict on what's
true, the **code wins** — and you fix the handoff.

---

## Decision authority matrix

What you can decide on your own vs. what needs escalation.

| Decision | You decide | Director decides |
|---|---|---|
| Test naming, fixture structure, parametrize vs. separate tests | ✅ | |
| Function/variable names that follow existing conventions | ✅ | |
| Adding a comment to explain a non-obvious choice | ✅ | |
| Splitting your one task into two commits | ✅ | |
| Choice of mock library (unittest.mock vs. pytest mocks) | ✅ | |
| Cache key naming, lock placement (when adding to existing pattern) | ✅ | |
| Adding a NEW public API surface | | ❌ Escalate |
| Removing or renaming an EXISTING public API | | ❌ Escalate |
| Changing the dependency graph (new pip/npm packages) | | ❌ Escalate |
| Changing behavior of a documented gate / endpoint / setting | | ❌ Escalate |
| Skipping a test instead of fixing it | | ❌ Escalate |
| Marking a pre-existing failure xfail (vs. fixing) | | ⚠ Document why, then decide |
| Postponing work to a future session | | ❌ Escalate |
| The 6-session order itself | | ❌ Director only |

When in doubt: **ask before acting on anything that survives your session.**
Reversibility is your friend; irreversible-without-effort decisions need
director approval.

---

## Status report — required at session close

Every session ends with a status report. Format:

```
SESSION: <number + name>
STATUS: DONE | DONE_WITH_CONCERNS | BLOCKED | PARTIAL

What shipped
============
- <Commit SHA>: <one-line summary>
- <Commit SHA>: <one-line summary>

Acceptance criteria
===================
- [✓ / ✗] Criterion 1 from the brief
- [✓ / ✗] Criterion 2
- [✓ / ✗] Criterion 3
...

Verification output
===================
<Paste the actual test / smoke / CI output here. Not "tests pass" —
the actual lines. If too long, attach a file path.>

Findings
========
<Anything you noticed that wasn't in scope but seems important. Don't
fix it; just record it. Director adds to strategic review next time.>

Open questions for director
===========================
<Decisions you need confirmation on before next session, if any.>

Time spent
==========
<Hours of focused work.>
```

This report goes into the commit message of the session's final commit
OR is attached to the PR description if working in a branch. It's the
director's audit trail.

---

## How to handle blockers

You will get stuck. The discipline isn't "don't get stuck" — it's
"surface fast, surface honest."

**5-minute stuck:** keep going, search docs/code.

**15-minute stuck:** stop. Write down what you've tried and what you
expected vs. observed. This often unblocks you (rubber-duck effect).

**30-minute stuck on the same thing:** escalate. Report BLOCKED in your
status, name the specific dependency or knowledge gap, request input.
Do NOT keep grinding — your time is more valuable than any single
sub-task.

**Cross-session blocker:** if your session's work depends on something
the prior session didn't ship, STOP. Don't try to finish the prior
session's work. Report the dependency and wait for direction.

**Common blocker patterns and resolutions:**

| Blocker | First action |
|---|---|
| Test fails on a branch that ARCHITECTURE.md says should work | Run §15 smoke — is the doc stale or is your branch broken? |
| Import error / circular import | grep for the symbol; the lazy-import pattern in `identity/__init__.py` is a model |
| TypeScript "any" cast you can't remove | Add to "Findings" — don't force the type change in scope |
| API rate limit / quota | Wait or switch to mock; never silently disable a check |
| Pod unavailable | Use a mock or test against `phase_c_ffmpeg`'s cascade-fallthrough behavior; don't skip the test |
| Pre-existing test failure unrelated to your work | Document in Findings + leave `@unittest.skip` if already marked; don't grind on it |

---

# Session briefs

The six sessions, in order. Execute one per assignment.

---

## SESSION 1 — P0-2: CI workflow (`.github/workflows/ci.yml`)

**Why this matters.** This codebase has shipped 10 commits in the last
24 hours without a single automated check beyond manual smoke. The
threshold=0.0 ML signal bug, the dead `__main__` block, the
PERFORMANCE_REVIEW half-wired gate, the lipsync_validation_threshold
setting being dead — every one of these would have been caught earlier
by a basic CI sweep. Doc drift was preventable. So is the next equivalent.

CI is the multiplier that lets every subsequent session land safely.
That's why it's Session 1.

**Pre-work (do these in order):**

1. Confirm `.github/` doesn't already exist: `ls -la .github/ 2>&1`. If
   it does, audit before adding.
2. Run all three local checks manually and capture output:
   ```bash
   .venv/bin/python scripts/ci_smoke.py
   .venv/bin/python -m pytest tests/unit/ --tb=no -q
   cd web && npx tsc --noEmit && cd ..
   ```
   The smoke script is the single source of truth for the §15 invariants
   (see [scripts/ci_smoke.py](../scripts/ci_smoke.py)). CI runs the same
   script — they cannot drift.
   All three must pass locally before you touch CI. If any fails, the
   problem is the codebase, not the CI — fix the underlying issue first
   (likely a stale smoke claim or a regression a previous session
   introduced).
3. Read [`.github/workflows/`](.github/workflows/) on a similar Python+React
   project (any reference you trust) to understand the shape. Don't
   blind-copy; understand.

**Scope:**

| IN | OUT |
|---|---|
| `.github/workflows/ci.yml` with 3 jobs: smoke / pytest / tsc | Linting (ruff, eslint) |
| Trigger on push to `main` + all `pull_request` | Deployment workflows |
| Python 3.13 + Node 20 | Auto-publish, releases, changelogs |
| Pip + npm caching | Code coverage reporting |
| README.md status badge (optional) | Custom GitHub Actions |

**Approach (specific):**

1. **Single workflow file.** `name: CI`. Three jobs that can run in
   parallel (no dependencies between smoke, pytest, tsc).
2. **Smoke job:**
   - `ubuntu-latest` runner
   - `actions/setup-python@v5` with `python-version: '3.13'` and `cache: 'pip'`
   - Install deps: `pip install -r requirements.txt`. Set `PIP_DISABLE_PIP_VERSION_CHECK=1` to skip the chatter.
   - Run a single inline `python -c "..."` with the §15 smoke block.
   - **Watch for:** DeepFace tries to download GhostFaceNet weights at
     first import. Either accept the ~700MB download in CI (slow but
     real) OR mock `from deepface import DeepFace` (risky — hides
     legitimate import bugs). Director recommendation: **let it download.**
     Cache the model weights between runs via `actions/cache@v4` on
     `~/.deepface/`. First CI run is slow, subsequent runs are fast.
3. **Pytest job:**
   - Same Python setup.
   - `pytest tests/unit/ --tb=short -q` — note the `tests/unit/` path,
     not just `tests/`. Integration tests (`tests/integration/`)
     require credentials and must NOT run in CI.
   - Acceptance: **478 pass + 3 skip + 0 fail** is the current
     baseline, verified via `$ .venv/bin/python -m pytest tests/unit/ -q`
     on 2026-05-24 (post `fix(tests):` baseline-hygiene commit). The 3
     skips are documented `@unittest.skip` in
     `test_project_persistence.py:139,197,221`. If your CI run shows a
     different count, your session uncovered something — investigate
     before proceeding. Sessions 2 / 3 / 5 will grow this count as
     they extend existing test files.
4. **TSC job:**
   - `actions/setup-node@v4` with `node-version: '20'` and `cache: 'npm'`.
   - `cache-dependency-path: web/package-lock.json`.
   - `cd web && npm ci && npx tsc --noEmit`.
   - Acceptance: silent exit.
5. **Concurrency:** add a `concurrency` block so multiple pushes to the
   same branch cancel the older runs (saves minutes).

**Acceptance criteria:**

- [ ] `.github/workflows/ci.yml` exists and is syntactically valid.
- [ ] Pushed to a test branch, all three jobs go green.
- [ ] An intentional break (e.g., temporarily rename a function the
      smoke imports) is detected by CI and turns it red. **You must
      verify this manually** — a CI that doesn't catch breakage isn't a
      CI.
- [ ] CI runtime is < 5 minutes end-to-end on a cold cache, < 2 minutes
      on warm cache.
- [ ] README.md mentions CI (badge is optional; a sentence is required).

**Pitfalls:**

- **Pedalboard install on Linux.** Pedalboard wheels exist for Linux
  x86_64 — should be fine on `ubuntu-latest`. If it fails, switch to
  `pip install pedalboard==<latest>` with explicit version.
- **`brew` doesn't exist on Linux runners.** Anything in your CI that
  references `brew` is a copy-paste from local docs and must be removed.
- **macOS-only audio paths** (AU plugins in `audio/effects.py`) — those
  are gated by feature detection at runtime; they don't break CI.
- **GitHub's free tier minutes.** Caching is non-negotiable for the
  pip + npm steps; without it you'll burn the budget fast.
- **Don't add `--no-deps` to pip install.** The transitive resolution
  is what makes our `requirements.txt` direct-deps approach work
  (per ADR notes in `requirements.txt`).

**Verification:**

```bash
# Local sanity (no act required):
git push origin <test-branch>
# Watch https://github.com/<user>/Content/actions
# Expect 3 green checks, ~2-5 min total.
```

**Commit shape:**

```
ci: add smoke + pytest + tsc workflow blocking merges on regression

Catches what manual verification missed across the last 10 commits
(threshold=0.0 ML bug, dead __main__ block, dead settings field).
Three independent jobs run in parallel; all must pass.

- Smoke: ARCHITECTURE.md §15 invariants
- Pytest: tests/unit/ (skips integration which need credentials)
- TSC: web/tsc --noEmit

Total CI time: ~2 min warm / ~5 min cold (DeepFace weights cached).
```

**Estimated effort:** 1-2 hours of focused work, mostly on getting the
caching right.

**Decision authority:** Lane A — you decide caching strategy, matrix
size (default to single Python 3.13 / single Node 20; don't matrix
unless someone asks), runner OS (`ubuntu-latest`). Escalate before:
adding eslint/ruff/coverage; adding deployment steps; changing
`requirements.txt`.

**If you finish early:** Add a status badge to README.md, add a
`pull_request_template.md` linking the strategic review's P-priorities,
and **do not start Session 2** — that's a separate assignment.

---

## SESSION 2 — P0-1.1: ReviewController coverage via test_cross_controller.py extension

**Status reframe (2026-05-24).** Original brief said "Create
`tests/unit/test_review_controller.py`". Audit revealed that
`tests/unit/test_cross_controller.py` already exists (10 passing tests
covering cross-controller wiring + `_candidate_take` 1 of 4 branches +
`_gate_satisfied` 5 of 13 cases partially). Creating a parallel file
would split coverage and lose the existing wiring tests that protect
Slice 2 regression. Reframed: **extend test_cross_controller.py in
place.**

**Why this matters.** `cinema/review/controller.py` (349 LOC) carries
the gate predicates that decide when the pipeline can advance.
PERFORMANCE_REVIEW was just wired up (commit `b4dc37b`) with ad-hoc
test verification. Audited gaps: `approve_take` (all 10 branches),
`_project_gate_status` (2 cases), the PERFORMANCE_REVIEW gate
satisfaction predicate (5 branches), `_candidate_take` 3 of 4 branches,
and `_resolve_motion_source` visited-set protection are entirely
untested. The existing 10 tests in `test_cross_controller.py` are
load-bearing for the V1.1 #1 cross-controller wiring contract — you
must NOT break them.

**Pre-work:**

1. Read [cinema/review/controller.py](../cinema/review/controller.py)
   end-to-end. 349 LOC.
2. Read [tests/unit/test_cross_controller.py](../tests/unit/test_cross_controller.py)
   end-to-end. **You are extending this file, not creating a new one.**
   Conventions to preserve:
   - **Plain functions, no pytest classes.**
   - `_make_setup()` helper builds fixtures per test (tmpdir per test).
   - `WiredHost` is the test seam against `ShotController._mutate_shot`.
   - `_TESTS` registry at the bottom — every new test name MUST be added
     so the standalone runner (`python tests/unit/test_cross_controller.py`)
     still works.
3. Read [ARCHITECTURE.md §6](../ARCHITECTURE.md#6-gate-mechanism--predicate-poll)
   for the gate model.
4. Run baseline: `.venv/bin/python -m pytest tests/unit/test_cross_controller.py -v`
   → expect 10 pass / 0 fail.

**Scope:**

| IN | OUT |
|---|---|
| `_gate_satisfied(gate, project)` × 4 gates × ≥3 cases each (full branch coverage of the predicate) | Integration with real ShotController (already covered) |
| `approve_take(shot_id, take_id, approval_kind)` × 3 kinds + error cases (10 branches) | Integration with `_wait_for_gate` loop (already covered) |
| `_project_gate_status` counts (all 5 fields) | Integration with `lifecycle.wait_for_gate` (lifecycle has its own test seam) |
| `_candidate_take` — the 3 of 4 cases not yet covered | `proceed_to_assembly` (e2e territory) |
| `_resolve_motion_source` chain walking + visited-set protection (synthetic loop) | `_rebuild_review_clips` (already covered) |
| Fixture extension: add `_richer_project()` helper with `performance_takes` + `postprocess_variants` chain | Do NOT mutate existing `_sample_project()` (would break existing tests) |

**Approach:**

1. **Add `_richer_project()` helper** alongside `_sample_project()`.
   Keep `_sample_project()` unchanged. The richer fixture should have:
   - 2 scenes × 2-3 shots
   - One shot with `performance_takes` array
   - One shot with `postprocess_variants` chain (motion → postprocess
     → postprocess pointing back to motion via `source_take_id`)
   - One shot with `approved_keyframe_take_id` (for PERFORMANCE_REVIEW
     gate predicate)
   - One shot with `performance_engine="SKIP"` (PERFORMANCE_REVIEW
     skip-routing path)
2. **Verify** `WiredHost._mutate_shot` persistence semantics before
   writing `approve_take` tests. Read [cinema/shots/controller.py](../cinema/shots/controller.py)
   `_mutate_shot` — if it persists to disk via `mutate_project`, the
   new tests need tempdir isolation; if the WiredHost stub keeps state
   in memory only, no cleanup needed.
3. **Add the 26 new test functions** enumerated in the commit body
   below. Each follows the `def test_X():` convention. **Each must be
   appended to the `_TESTS` registry** at the bottom of the file.
4. **Do not import `cinema_pipeline`** — the existing tests prove
   ReviewController is composable independently (ADR-009).
5. Run: `.venv/bin/python -m pytest tests/unit/test_cross_controller.py -v`
   and the standalone runner: `.venv/bin/python tests/unit/test_cross_controller.py`

**Acceptance criteria:**

- [ ] ≥36 test cases (10 existing + ≥26 new), all passing
- [ ] Every branch of `_gate_satisfied` exercised (13 cases)
- [ ] Every branch of `approve_take` exercised (10 cases)
- [ ] Postprocess-variant `source_take_id` chain walk tested with both
      a valid multi-hop chain AND a synthetic loop (visited-set
      protection — no hang)
- [ ] `_project_gate_status` 5 counts verified for richer fixture AND
      empty project
- [ ] `_candidate_take` 4 branches all covered
- [ ] Standalone runner still works (`python tests/unit/test_cross_controller.py`)
- [ ] Runs in < 5 seconds
- [ ] Whole-suite CI (Session 1) stays green: `pytest tests/unit/ -q` →
      ≥497 pass / 3 skip / 0 fail

**Pitfalls:**

- **`_find_take` is on the HOST**, not on ReviewController. `WiredHost`
  already provides this; new tests can extend the host stub's
  `find_take_returns` if needed. Return shape:
  `(collection_name: Optional[str], take: Optional[dict])`.
- **`_mutate_shot` returns the mutator's `MutationResult.value`**, not
  the dict. Read [cinema/review/controller.py:280](../cinema/review/controller.py)
  to see the pattern.
- **`approval_kind="performance"` is the new branch** from commit
  `b4dc37b`. Verify the take MUST live in `performance_takes`, not just
  any collection.
- **Chain walk visited-set protection.** Build a synthetic loop
  (variant A → variant B → variant A). The `_resolve_motion_source`
  call must return without hanging; `approved_motion_take_id` must NOT
  be set.
- **Convention enforcement:** plain functions, no pytest classes, no
  conftest fixtures. Adding pytest classes or conftest would break the
  standalone runner the file docstring promises.

**Verification:**

```bash
.venv/bin/python -m pytest tests/unit/test_cross_controller.py -v
# Expect: ≥36 tests, all passing, < 5 seconds.

.venv/bin/python tests/unit/test_cross_controller.py
# Standalone runner: all green.

.venv/bin/python -m pytest tests/unit/ -q
# Whole-suite check: ≥497 pass / 3 skip / 0 fail.
```

**Commit shape:**

```
test(review): cover approve_take + gate_satisfied + chain walk branches

Extends tests/unit/test_cross_controller.py with 26 new test functions
covering previously uncovered branches of cinema/review/controller.py:

  _gate_satisfied (10 new):
    - empty project across all 4 gates
    - PLAN_REVIEW all-approved / one-unapproved
    - PERFORMANCE_REVIEW 5 branches (empty, all-SKIP, all-approved,
      mixed, one-needs-but-unapproved)
    - REVIEW all-approved
    - UNKNOWN gate default-False

  approve_take (10 new):
    - keyframe in keyframe_takes (sets field)
    - keyframe in motion_takes (error: not a keyframe)
    - performance in performance_takes (sets field)
    - performance in keyframe_takes (error: not a performance)
    - final in motion_takes (sets motion + final)
    - final in postprocess_variants (walks chain → motion + final)
    - final in keyframe_takes (error)
    - unknown approval_kind (error)
    - unknown shot_id (Shot not found)
    - unknown take_id (Take not found)

  _project_gate_status (2 new):
    - all 5 counts for richer fixture
    - empty project → all zero

  _candidate_take (3 new):
    - returns approved_final_take when set
    - falls through to postprocess_variants
    - falls through to keyframe when no motion

  _resolve_motion_source (1 new):
    - visited-set breaks synthetic loop (no hang)

Convention: plain functions, no pytest classes; _TESTS registry
extended. Standalone runner still works. Existing 10 wiring tests
untouched. New _richer_project() fixture; _sample_project() unchanged.

Verified: 36+ pass in <5s; standalone runner OK; whole-suite
≥497 pass / 3 skip / 0 fail; §15 smoke OK; Session 1 CI green.
```

**Estimated effort:** 2-3 hours.

**Decision authority:** Lane A on test structure within existing
conventions. Escalate before:
- Converting plain-functions to pytest classes (breaks standalone runner).
- Modifying `cinema/review/controller.py` itself except comments. If
  tests reveal a bug, document in Findings and STOP — director decides
  whether to fix in this session or follow-up.
- Adding conftest fixtures.

**If you finish early:** Audit `_rebuild_review_clips` for edge cases
beyond what `test_review_rebuild_review_clips_full_chain` covers.
Don't add tests for `proceed_to_assembly` — needs real lifecycle setup,
belongs in a separate session.

---

## SESSION 3 — P0-1.2: workflow_selector coverage via test_workflow_selector.py extension

**Status reframe (2026-05-24).** Original brief said "Create
`tests/unit/test_workflow_selector.py`". File already exists at 145
LOC with 34 passing tests covering shape + defaults + ranges. Audited
gap: only **4 of 48 keyword-routes are tested (8%)**, and
`get_adaptive_pulid_weight` + `MOTION_FIDELITY_FLOORS` subset check are
entirely untested. Reframed: **extend in place.**

**Why this matters.** `workflow_selector.classify_shot_type` is the
keyword-driven router that decides which video API cascade a shot will
hit. A typo in `SHOT_TYPE_KEYWORDS` silently changes routing for every
shot matching that keyword — Sora when you wanted Kling. The cost of a
silent routing bug is hours of wrong-engine generations before an
operator notices. Existing tests verify the API surface; gaps are in
the keyword matrix and the adaptive feedback loop.

**Pre-work:**

1. Read [workflow_selector.py](../workflow_selector.py) — focus on
   `WORKFLOW_TEMPLATES` (5 keys), `SHOT_TYPE_KEYWORDS` (48 keywords
   across 5 buckets), `classify_shot_type`, `get_adaptive_pulid_weight`,
   `MOTION_FIDELITY_FLOORS`.
2. Read [tests/unit/test_workflow_selector.py](../tests/unit/test_workflow_selector.py)
   end-to-end. **You are extending this file.** Conventions:
   - Class-based grouping (`TestClassifyShotType`, etc.)
   - `pytest.mark.parametrize` for cross-product coverage
   - No conftest fixtures
   - `pytest.approx` for float comparisons
3. Read [domain/shot_types.py](../domain/shot_types.py) for the
   canonical shot-type set. **Important:** no `SHOT_TYPES` literal
   exists — the canonical set must be assembled from the 6
   `SHOT_TYPE_*` constants:
   ```python
   from domain.shot_types import (
       SHOT_TYPE_CLOSE, SHOT_TYPE_PORTRAIT, SHOT_TYPE_MEDIUM,
       SHOT_TYPE_WIDE, SHOT_TYPE_LANDSCAPE, SHOT_TYPE_ACTION,
   )
   CANONICAL = {SHOT_TYPE_CLOSE, SHOT_TYPE_PORTRAIT, SHOT_TYPE_MEDIUM,
                SHOT_TYPE_WIDE, SHOT_TYPE_LANDSCAPE, SHOT_TYPE_ACTION}
   ```
4. Read [ARCHITECTURE.md §9](../ARCHITECTURE.md#9-video-routing--5-templates--11-engines)
   for the routing context.
5. Run baseline: `.venv/bin/python -m pytest tests/unit/test_workflow_selector.py -v`
   → expect 34 pass / 0 fail.

**Scope:**

| IN | OUT |
|---|---|
| `classify_shot_type` × every keyword in `SHOT_TYPE_KEYWORDS` (48 cases, parametrized) | `MAX_QUALITY_TEMPLATES` tests (separate session) |
| `classify_shot_type` × `[SHOT]`-section-wins-over-full-prompt explicit case | `get_max_quality_params` (separate session) |
| `WORKFLOW_TEMPLATES` shape: exactly 5 keys + valid `target_api` per entry + non-empty `video_fallbacks` of valid api strings | `_swap_to_hidream` (max-tier territory) |
| `MOTION_FIDELITY_FLOORS` keys ⊆ canonical shot types (subset check, not equality) | Anything in `quality_max.py` |
| `get_adaptive_pulid_weight` × 4 boost paths + clamp + face-failure suppression | |

**Approach:**

1. **`TestClassifyShotTypeKeywords`** (single parametrized test, 48 cases):
   ```python
   @pytest.mark.parametrize(
       "kw,expected_bucket",
       [(kw, b) for b, kws in workflow_selector.SHOT_TYPE_KEYWORDS.items() for kw in kws],
   )
   def test_keyword_routes_to_bucket(self, kw, expected_bucket):
       # NB: for landscape keywords, pass characters_in_frame=["c1"]
       #     so the no-characters short-circuit doesn't pre-empt the keyword check.
       shot = {"prompt": f"a {kw} of something", "camera": "",
               "characters_in_frame": ["c1"]}
       assert workflow_selector.classify_shot_type(shot) == expected_bucket
   ```

2. **`TestClassifyShotTypePriority`** (1 test) — assert `[SHOT]`
   section wins when full prompt has a conflicting keyword:
   ```python
   def test_shot_section_wins_over_full_prompt(self):
       shot = {"prompt": "[SHOT] portrait headshot [SCENE] wide angle landscape vista",
               "camera": "", "characters_in_frame": ["c1"]}
       assert workflow_selector.classify_shot_type(shot) == "portrait"
   ```

3. **`TestWorkflowTemplatesShape`** (3 tests):
   - `test_exactly_five_shot_types` — `set(WORKFLOW_TEMPLATES.keys()) == {"portrait","medium","wide","action","landscape"}`
   - `test_target_api_is_valid` (parametrized) — `target_api ∈ {"KLING_NATIVE","LTX","SORA_NATIVE","RUNWAY_GEN4","VEO_NATIVE","KLING_3_0","SEEDANCE"}`
   - `test_video_fallbacks_nonempty_and_valid` (parametrized) — list, each entry in the valid api set

4. **`TestMotionFidelityFloors`** (2 tests):
   - `test_keys_subset_of_canonical_shot_types` — `set(MOTION_FIDELITY_FLOORS.keys()) <= CANONICAL`
   - `test_landscape_floor_is_none` — explicit `None` assertion (sentinel)

5. **`TestGetAdaptivePulidWeight`** (8 tests) — stub validator with
   controlled `get_rolling_stats` and `common_failure`:
   - `test_returns_base_when_validator_none`
   - `test_no_samples_returns_base` (`sample_count=0`)
   - `test_failure_boost_plus_010` (delta=+0.10)
   - `test_near_pass_boost_plus_005` (delta=+0.05)
   - `test_overperform_reduces_minus_005` (delta=-0.05)
   - `test_clamped_to_unit_interval` (both upper and lower clamp)
   - `test_face_angle_extreme_zeros_positive_delta`
   - `test_small_face_region_zeros_delta`

**Acceptance criteria:**

- [ ] ≥97 test cases (34 existing + ≥63 new), all passing
- [ ] All 48 `SHOT_TYPE_KEYWORDS` routes verified
- [ ] `WORKFLOW_TEMPLATES` shape locked (5 keys exact + `target_api` + `video_fallbacks` valid)
- [ ] `MOTION_FIDELITY_FLOORS` subset check enforced (not equality — `close_up` is canonical but unreachable from this function)
- [ ] `get_adaptive_pulid_weight` covered for 4 boost paths + clamping + face-failure suppression
- [ ] `[SHOT]`-section-wins priority explicit
- [ ] Runs in < 3 seconds
- [ ] Whole-suite CI green: `pytest tests/unit/ -q` → ≥560 pass / 3 skip / 0 fail (post-Session-2 + this session)

**Pitfalls:**

- **"macro" is a portrait keyword**, not a shot type. Test that a shot
  with "macro" routes to `portrait`, NOT to any "macro" bucket.
- **`MOTION_FIDELITY_FLOORS` has `close_up`** but `classify_shot_type`
  never returns `close_up`. Subset check, not equality — `close_up`
  is canonical (via `normalize_shot_type`) but unreachable from this
  function.
- **`classify_shot_type` searches case-insensitively** via lowercased
  match. Don't rely on case for test inputs.
- **First-match-wins in keyword order.** A prompt with multiple
  matching keywords routes to the FIRST shot type declared in
  `SHOT_TYPE_KEYWORDS` (dict insertion order = portrait → action →
  wide → landscape → medium).
- **Empty `characters_in_frame` always returns landscape**, regardless
  of prompt. For landscape-keyword tests, pass non-empty characters.
- **No `domain.shot_types.SHOT_TYPES` literal exists** — assemble the
  canonical set from the 6 `SHOT_TYPE_*` constants. Add a comment
  pointing at `domain/shot_types.py` for future readers.
- **Dead imports in test file:** lines 1 `import sys, os` are unused.
  Optional cleanup while extending.

**Verification:**

```bash
.venv/bin/python -m pytest tests/unit/test_workflow_selector.py -v
# Expect ≥97 tests, all passing, < 3s.

.venv/bin/python -m pytest tests/unit/ -q
# Whole-suite: ≥560 pass / 3 skip / 0 fail.
```

**Commit shape:**

```
test(workflow_selector): cover 48 keyword routes + adaptive weight + floors

Extends tests/unit/test_workflow_selector.py from 34 to ~97 cases:

  TestClassifyShotTypeKeywords (1 parametrized × 48):
    Every entry in SHOT_TYPE_KEYWORDS routes to its declared bucket.
    Landscape keywords pass characters_in_frame to bypass the
    no-characters short-circuit.

  TestClassifyShotTypePriority (1):
    [SHOT] section wins over conflicting keyword in full prompt.

  TestWorkflowTemplatesShape (3):
    - exactly 5 keys: portrait, medium, wide, action, landscape
    - target_api validity (parametrized × 5)
    - video_fallbacks non-empty + valid api strings (parametrized × 5)

  TestMotionFidelityFloors (2):
    - keys ⊆ canonical shot types (assembled from domain.shot_types
      constants — no SHOT_TYPES literal exists)
    - landscape floor is None (sentinel)

  TestGetAdaptivePulidWeight (8):
    - validator None → base
    - no_samples → base
    - failure_boost +0.10
    - near_pass_boost +0.05
    - overperform -0.05
    - clamp to [0.0, 1.0] (both bounds)
    - face_angle_extreme zeros positive delta
    - small_face_region zeros delta

The subset check on MOTION_FIDELITY_FLOORS catches the kind of drift
the strategic review documented (close_up is a canonical key but
unreachable from classify_shot_type — must be subset, not equality).

Existing 34 tests unchanged. Convention: class-based grouping +
pytest.mark.parametrize, no conftest. Dead `import sys, os` removed.

Verified: ≥97 pass in <3s; whole-suite ≥560 pass / 3 skip / 0 fail;
CI green.
```

**Estimated effort:** 2 hours.

**Decision authority:** Lane A on test structure within existing
conventions. Escalate before:
- Modifying `workflow_selector.py` itself.
- Changing `SHOT_TYPE_KEYWORDS` ordering or values.
- Touching `domain/shot_types.py`.

**If you finish early:** Spot-check `_VEO_QUOTA_EXHAUSTED_UNTIL`
behavior in `phase_c_ffmpeg.py:22-28` — write a 5-test mini-suite for
the TTL reset, save in `tests/unit/test_phase_c_ffmpeg.py`. Quick win,
useful coverage.

---

## SESSION 4 — P1-1: Structured logging

**Why this matters.** Every error path in the codebase uses
`print(f"[ENGINE] something happened: {e}")`. For a pipeline that:
- Runs 10+ minutes per generation
- Touches 17 cloud API providers
- Has 9-engine video cascade, 4-engine lipsync cascades, 3-path
  performance autopilot
- Spawns daemon threads with no log correlation

…debugging from stdout is below the floor of "operable in production."
Structured logging is the foundation that makes per-shot tracing, cost
attribution, and engine-selection forensics possible. Subsequent
sessions (e.g., P2-3 cascade visibility) depend on this.

**Pre-work:**

1. Enumerate every `print(` call in the target files:
   ```bash
   grep -n "^[^#]*print(" cinema_pipeline.py cinema/shots/controller.py cinema/review/controller.py cinema/lifecycle.py cinema/checkpoint.py | wc -l
   ```
2. Read the existing format conventions — most use `[STAGE-LIKE-TAG] message`. Decide whether to preserve that tag as a logger name or as a field.
3. Pick a JSON formatter. **Director recommendation:** add
   `python-json-logger` to requirements.txt (battle-tested, ~200 LOC of
   dependency). If you don't want the new dep, write a 30-LOC custom
   formatter — both are acceptable.

**Scope:**

| IN | OUT |
|---|---|
| `cinema_pipeline.py` `print()` → `logger` | `audio/` submodules |
| `cinema/shots/controller.py` `print()` → `logger` | `performance/` submodules |
| `cinema/review/controller.py` `print()` → `logger` | `llm/` submodules |
| `cinema/lifecycle.py` `print()` → `logger` | `phase_c_*` files (separate sessions, large) |
| `cinema/checkpoint.py` `print()` → `logger` | `quality_max.py`, `lip_sync.py` |
| Single `cinema/logging_config.py` with JSON formatter | Web frontend logging (frontend already uses console) |
| Per-shot correlation IDs via `logging.LoggerAdapter` or `extra=` | Log aggregation / external sinks |

**Approach:**

1. Create `cinema/logging_config.py`:
   ```python
   """Structured JSON logging for the cinema pipeline.

   One log line per event, JSON-formatted on stdout. Per-shot correlation
   via `extra={"pid": ..., "scene_id": ..., "shot_id": ..., "engine": ...}`.

   Call `setup_logging()` once at process start (web_server.py does this
   for the server; CLI tools call it explicitly). Subsequent
   `logging.getLogger(__name__)` calls in modules inherit the config.
   """
   import logging
   import os
   import sys
   from pythonjsonlogger import jsonlogger  # or write a 30-LOC custom formatter

   def setup_logging():
       level = os.environ.get("CINEMA_LOG_LEVEL", "INFO").upper()
       fmt = jsonlogger.JsonFormatter(
           "%(asctime)s %(levelname)s %(name)s %(message)s",
           rename_fields={"asctime": "ts", "levelname": "level"},
       )
       handler = logging.StreamHandler(sys.stdout)
       handler.setFormatter(fmt)
       root = logging.getLogger()
       root.handlers.clear()
       root.addHandler(handler)
       root.setLevel(level)
   ```
2. Call `setup_logging()` at the top of `web_server.py` (before any
   `cinema_pipeline` import). Call it conditionally in `cinema_pipeline.py`
   itself if it might be imported as a library (idempotent setup).
3. In each target file:
   ```python
   import logging
   logger = logging.getLogger(__name__)

   # before:
   print(f"[KEYFRAME] {shot_id}: generated take {take_id}")
   # after:
   logger.info("keyframe.generated", extra={"shot_id": shot_id, "take_id": take_id})
   ```
4. **For try/except:** use `logger.exception(...)` inside the except
   block — it captures the traceback automatically.
5. **Don't change the SSE progress callback.** It's a separate channel
   for the UI. The new structured log is for backend forensics.
   Optionally, mirror progress events to the logger as well (one log
   line per SSE event) so you have a unified backend trail.

**Acceptance criteria:**

- [ ] Zero `print(` calls in the 5 target files (verified by grep)
- [ ] Every replaced line is JSON-parseable on stdout
- [ ] A single shot's lifecycle (PLAN_REVIEW → KEYFRAME → MOTION →
      REVIEW) is filterable by `shot_id` field in the log stream
- [ ] SSE behavior unchanged (UI receives the same progress events)
- [ ] §15 smoke still passes
- [ ] CI green
- [ ] `CINEMA_LOG_LEVEL=DEBUG` works as expected (emits more)
- [ ] Default is INFO — operators don't get flooded with debug noise

**Pitfalls:**

- **Don't strip context.** Replacing `print(f"[X] thing {var}")` with
  `logger.info("thing")` loses the variable. Use the `extra=` dict.
- **The `lifecycle.progress` callback** is not a print — leave it
  alone. The progress event is the SSE payload + (optionally) a mirrored
  log line.
- **Don't introduce a logging dependency between cinema modules.**
  Each module imports `logging` and gets its own logger via
  `getLogger(__name__)`. They share the root config, not module-to-module
  coupling.
- **DeepFace and other deps emit their own logs.** Set their loggers
  to WARNING level in `setup_logging` to avoid noise:
  ```python
  for noisy in ("DeepFace", "tensorflow", "matplotlib"):
      logging.getLogger(noisy).setLevel(logging.WARNING)
  ```
- **`logger.exception(...)` MUST be inside an except block.** Outside
  it, it errors silently (no traceback available).

**Verification:**

```bash
# 1. No prints left:
grep -n "^[^#]*print(" cinema_pipeline.py cinema/shots/controller.py cinema/review/controller.py cinema/lifecycle.py cinema/checkpoint.py
# Expected: zero matches (excluding string literals inside f-strings)

# 2. Smoke:
.venv/bin/python -c "<§15 smoke block>"

# 3. Real run:
.venv/bin/python web_server.py 2>&1 | head -20
# Expected: JSON lines on stdout, one per event

# 4. Tests:
.venv/bin/python -m pytest tests/unit/ -q
```

**Commit shape (split into 2):**

Commit 1:
```
feat(logging): structured JSON logging foundation

cinema/logging_config.py — single setup_logging() call configures
JSON formatter + correlation field convention (pid, scene_id, shot_id,
engine). Wired into web_server.py at module load. CINEMA_LOG_LEVEL env
var controls verbosity (default INFO).

Adds python-json-logger to requirements.txt. (Alternative custom
30-LOC formatter was rejected — battle-tested dep is cheaper than
maintenance.)

Verified: smoke OK; web_server starts and emits JSON; SSE unchanged.
```

Commit 2:
```
refactor(logging): cinema_pipeline + controllers + lifecycle print → logger

Mechanical replacement of every print() in the 5 core orchestrator
files with logger.info/warning/error. Each call gets the right
correlation fields (shot_id, scene_id, engine, etc.) via extra=.
try/except blocks use logger.exception for traceback capture.

48 print() calls replaced. 0 remaining in the target files (verified
via grep).

Verified: smoke OK; pytest OK; CI green; a sample shot run produces
filter-by-shot_id-able log stream.
```

**Estimated effort:** 3-4 hours.

**Decision authority:** Lane A on log level choices, field naming
within `extra=`. Escalate before:
- Adding a log aggregation sink (Sentry, Loki, etc.).
- Changing the SSE protocol.
- Removing the print() in other files outside scope.

**If you finish early:** Convert one of the audio/ or performance/
modules as a follow-up. Pick the smallest first (`performance/_router.py`
is 117 LOC).

---

## SESSION 5 — P0-3: record_api_call coverage + silent-except sweep

**Status reframe (2026-05-24).** Original brief said "Add
`tests/unit/test_cost_tracker.py` with at least 5 tests" and implied a
large silent-except cleanup. File already exists at 458 LOC with 33
passing tests — but **none directly test `record_api_call`** (the
explicit Session 5 demand). And the silent-except sweep audit found
only **2 instances repo-wide** (vs the implied "many"). Reframe scope:
smaller and more focused.

**Why this matters.** Bundle-A 1.3 (commit `491af65`) fixed a silent
`AttributeError` in `ShotController.cost_tracker` that had been
swallowing cost-tracking writes. `record_api_call` is the ONLY way cost
data enters the SQLite DB — if it silently broke again, the operator
would notice only when the budget gate fails to fire or summary stays
at $0. The budget gate (`would_exceed`, `is_over_budget`, `spent_usd`
accumulator) is also entirely untested.

**Positive findings worth carrying forward:**

- `cost_tracker.py` itself has **zero** silent-except patterns. Every
  error path emits `warnings.warn` + visible banner — the silent-$0.00
  bug is explicitly called out in the module docstring.
- Repo-wide silent-except count is **2**. The "pattern that needs
  auditing" was largely already cleaned up.

**Pre-work:**

1. Read [cost_tracker.py](../cost_tracker.py) end-to-end (518 LOC).
   Focus on `CostTracker.__init__`, `record_api_call`, `log_llm`,
   `_default_cost`, `_pricing_for`, `would_exceed`, `is_over_budget`,
   `spent_usd`.
2. Read [tests/unit/test_cost_tracker.py](../tests/unit/test_cost_tracker.py)
   in full (458 LOC). Conventions:
   - `db_path` fixture uses `tempfile.NamedTemporaryFile(delete=False)`
     for isolated SQLite per test (Windows-safe pattern with manual
     unlink in teardown).
   - `pytest.approx` for float comparisons.
   - Substring-match for `get_summary` formatted output.
3. Run baseline: `.venv/bin/python -m pytest tests/unit/test_cost_tracker.py -v`
   → expect 33 pass / 0 fail.
4. Enumerate the 2 silent-except instances:
   ```bash
   grep -rn "except.*:\s*pass" --include="*.py" /Users/hyungkoookkim/Content \
     | grep -v "/.claude/" | grep -v "__pycache__" | grep -v "/.venv/" \
     | grep -v "/node_modules/"
   ```
   Categorize each: ACCEPTABLE (intentional — document with comment)
   or REPLACE (explicit `except SpecificError:` or
   `except Exception as e: warnings.warn(...)`).

**Scope:**

| IN | OUT |
|---|---|
| `TestRecordAPICall` × ~6 cases | Refactor of `cost_tracker.py` itself |
| `TestBudgetGate` × ~5 cases | UI changes for cost display |
| 2 silent-except instances: triage + replace where appropriate | Cost reporting/aggregation features |
| `record_api_call` call-site audit (manual grep + trace; document live sites) | New cost-tracking sites (separate session) |
| OPERATIONS.md §10 (cost table) updated with measured numbers if available | Refactor of `warnings.warn` → `logger.warning` (Session 4's job, not yours) |

**Approach:**

1. **Extend test_cost_tracker.py:**

   **`TestRecordAPICall`** (~6 tests):
   - `test_record_api_call_known_api_uses_table` — `record_api_call("KLING_NATIVE")` returns 0.50, persists row with `cost_usd=0.50`, `provider="kling"`
   - `test_record_api_call_explicit_override` — `cost_usd=0.99` overrides table
   - `test_record_api_call_unknown_warns_and_zero` — `pytest.warns(UserWarning)`, recorded cost is 0.0
   - `test_record_api_call_updates_spent_usd` — accumulator starts at 0, two $0.50 calls → `tracker.spent_usd == 1.00`
   - `test_record_api_call_provider_derivation` — parametrize:
     SORA_2→openai, VEO→google, FLUX_PULID→fal, RUNWAY_GEN4→runway,
     unknown prefix→"unknown"
   - `test_record_api_call_returns_cost` — return value equals what
     was recorded

   **`TestBudgetGate`** (~5 tests):
   - `test_would_exceed_with_no_budget_returns_false` — `budget_usd=None`
   - `test_would_exceed_under_budget` — budget=1.00, spent=0.30,
     would_exceed("KLING_NATIVE") (0.50) → False
   - `test_would_exceed_over_budget` — budget=1.00, spent=0.80,
     would_exceed("KLING_NATIVE") (0.50) → True
   - `test_is_over_budget_no_cap` — `budget_usd=None` → False
   - `test_is_over_budget_post_record` — record calls until accumulator
     exceeds, assert True

2. **Silent-except triage (2 instances):**
   For each, decide ACCEPTABLE (document with comment + cite reason)
   or REPLACE (`except SpecificError:` + explicit handling OR
   `except Exception as e: warnings.warn(f"<context>: {e}")`). If
   unsure, surface in Findings — don't change behavior beyond
   surfacing.

3. **`record_api_call` call-site audit:**
   ```bash
   grep -rn "record_api_call\|cost_tracker\." --include="*.py" /Users/hyungkoookkim/Content \
     | grep -v "__pycache__" | grep -v "/.venv/"
   ```
   For each site, verify:
   - Reachable (not dead code)
   - Error path (if any) doesn't silently drop data
   - Arguments correct (api_name, cost_usd, latency_ms, etc.)
   - Document live sites in commit body or Findings.

**Acceptance criteria:**

- [ ] `tests/unit/test_cost_tracker.py` has ≥44 tests (33 existing +
      ≥11 new), all passing
- [ ] `record_api_call` directly covered (table lookup, explicit
      override, unknown warns, accumulator updates, provider
      derivation, return value)
- [ ] Budget gate covered (`would_exceed`, `is_over_budget`)
- [ ] 2 silent-except instances triaged (count + decision documented)
- [ ] All `record_api_call` call sites traced and documented in
      commit body
- [ ] §15 smoke still passes; CI green
- [ ] Whole-suite: `pytest tests/unit/ -q` → ≥571 pass / 3 skip / 0 fail

**Pitfalls:**

- **`try/except ImportError: pass` for optional deps** is acceptable
  (`try: from optional_pkg import X; X_AVAILABLE = True; except
  ImportError: X_AVAILABLE = False`) — don't replace these.
- **`try/except Exception: pass` inside a polling loop** might be
  legitimate (transient network errors that should be retried). Read
  the surrounding context before changing.
- **`cost_tracker.py` already uses `warnings.warn` discipline.** Don't
  replace with `logger.warning` in this session — Session 4
  (structured logging) is the right place for that transition.
- **`db_path` fixture uses `NamedTemporaryFile(delete=False)`.** New
  tests must use this fixture (or compatible tempdir) — never the
  default DB path, which would write to the real `EXPERIMENTS_DB_PATH`.
- **The 33 existing tests must keep passing unchanged.**

**Verification:**

```bash
.venv/bin/python -m pytest tests/unit/test_cost_tracker.py -v
# Expect ≥44 pass / 0 fail.

grep -rn "except.*:\s*pass" --include="*.py" /Users/hyungkoookkim/Content \
  | grep -v "/.claude/" | grep -v "__pycache__" | grep -v "/.venv/" \
  | grep -v "/node_modules/"
# Should be 0-2 instances; any remaining must have ACCEPTABLE comment.

.venv/bin/python -c "
from cost_tracker import CostTracker
import tempfile
with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
    ct = CostTracker(budget_usd=10.0, db_path=f.name)
    ct.record_api_call('KLING_NATIVE')
    assert ct.spent_usd > 0
    print('OK')
"
```

**Commit shape:**

```
fix(cost): cover record_api_call + budget gate + sweep silent-excepts

Extends tests/unit/test_cost_tracker.py from 33 to ~44 tests:

  TestRecordAPICall (6):
    - known_api_uses_table
    - explicit_override
    - unknown_warns_and_zero (pytest.warns(UserWarning))
    - updates_spent_usd accumulator
    - provider_derivation (sora→openai, veo→google, flux→fal,
      runway→runway, unknown→unknown)
    - returns_cost matches recorded

  TestBudgetGate (5):
    - would_exceed: no_budget / under / over
    - is_over_budget: no_cap / post_record

Silent-except sweep: <N> instances found repo-wide. Triage:
  <X> ACCEPTABLE — optional import guards / transient retry loops
  <Y> REPLACED with explicit handling (this commit)

record_api_call call sites traced: <list>. All reachable via
cost_tracker proxy (Bundle-A 1.3 set this up); no silently-dropped
writes.

Positive: cost_tracker.py itself has zero silent-except patterns —
the strategic review's implied "many instances" was overstated. The
repo-wide sweep is tiny because the pattern was largely already
cleaned up.

Verified: ≥44/44 cost tests pass; whole-suite ≥571 pass / 3 skip / 0
fail; smoke OK; CI green.
```

**Estimated effort:** 1.5 hours (was 3 — most work already done).

**Decision authority:** Lane A on categorization of individual
try/except patterns. Escalate when ambiguous or when the fix would
change behavior beyond logging.

**If you finish early:** Audit one of the deferred subsystems (audio/,
performance/, llm/) — same triage pattern. With repo-wide
silent-except count this low, you may finish a full repo sweep in
one extra hour.

---

## SESSION 6 — P1-4 + P2-3: Frontend resilience + cascade visibility

**Why this matters.** Two related issues paired because they're
both about operator-visible state. P1-4: a single throw in
`usePipelineState`'s event router can crash the UI after a 20-minute
run. P2-3: when the lipsync or video cascade fails through all engines
and we restore "best of bad," the operator sees a take that LOOKS
approved-quality but actually failed the SyncNet bar. Trust degrades
silently.

Both fix the same operator pain: "I don't know what just happened, and
the UI doesn't tell me."

**Pre-work:**

1. Read [web/src/App.tsx](../web/src/App.tsx) — note the three shells.
2. Read [web/src/hooks/usePipelineState.ts](../web/src/hooks/usePipelineState.ts) —
   the event router is at lines 33-101; this is where most throws
   would happen.
3. Read [lip_sync.py](../lip_sync.py) lines 208-222 (SyncNet gate
   stash-and-restore logic) and lines 312-327 (restoration).
4. Read [phase_c_ffmpeg.py](../phase_c_ffmpeg.py) lines 106-161 (the
   `try_next_api` cascade closure) — where engine selection happens.

**Scope:**

| IN | OUT |
|---|---|
| `web/src/components/ui/ErrorBoundary.tsx` (new) | Sentry / external error reporting |
| Wrap EditorialShell + PipelineLayout + DirectorsConsole | Frontend logging service |
| Add `cascade_metadata?: { engine, score, fallback }` to TakeRecord type | Backend refactor of cascade logic |
| Populate cascade_metadata in lip_sync.py overlay + generation | UI redesigns beyond the metadata badge |
| Populate cascade_metadata in phase_c_ffmpeg.py video cascade | |
| Render cascade_metadata as a badge + tooltip in TakeStrip and ReviewStage | |

**Approach:**

1. **ErrorBoundary** (15-25 LOC):
   ```tsx
   // web/src/components/ui/ErrorBoundary.tsx
   import { Component, ReactNode } from 'react'
   interface Props { children: ReactNode; fallback?: ReactNode }
   interface State { hasError: boolean; error: Error | null }
   export class ErrorBoundary extends Component<Props, State> {
     state: State = { hasError: false, error: null }
     static getDerivedStateFromError(error: Error): State {
       return { hasError: true, error }
     }
     componentDidCatch(error: Error, info: { componentStack: string }) {
       console.error('[ErrorBoundary]', error, info.componentStack)
     }
     render() {
       if (this.state.hasError) {
         return this.props.fallback ?? (
           <div className="editorial-curtain p-6 text-editorial-ivory">
             <h2 className="text-lg font-semibold mb-2">Something broke.</h2>
             <pre className="text-eyebrow font-mono">{String(this.state.error)}</pre>
             <button onClick={() => window.location.reload()}
               className="mt-4 rounded border border-editorial-ivory px-3 py-1.5">
               Reload
             </button>
           </div>
         )
       }
       return this.props.children
     }
   }
   ```
2. **Wrap shells in App.tsx:**
   ```tsx
   // Each top-level shell branch:
   if (mode === 'console' && project) {
     return <ErrorBoundary><DirectorsConsole ... /></ErrorBoundary>
   }
   // etc.
   ```
3. **TakeRecord type extension** (in `web/src/types/project.ts`):
   ```ts
   export interface TakeRecord {
     id: string
     kind: TakeKind
     path: string
     // ...existing...
     /** Cascade decision metadata — added Bundle-N. */
     cascade_metadata?: {
       engine: string           // which engine actually produced this take
       score?: number           // quality gate score (SyncNet for lipsync, motion fidelity for video)
       threshold?: number       // the bar that was checked
       fallback?: boolean       // true if this was restored from stash after no engine cleared the threshold
       attempts?: string[]      // engines tried in order (oldest first)
     }
   }
   ```
4. **Populate in lip_sync.py** (both overlay and generation paths):
   - On successful gate-pass: `cascade_metadata = {engine: <name>, score: <score>, threshold: <threshold>, fallback: false, attempts: [<engines tried>]}`
   - On restored stash: `cascade_metadata = {engine: <best_stash_engine>, score: <best_score>, threshold: <threshold>, fallback: True, attempts: [...]}`
   - **This requires touching the Python code.** Keep changes minimal —
     attach the dict to the returned take metadata, don't refactor the
     cascade structure.
5. **Populate in phase_c_ffmpeg.py** (the `try_next_api` closure):
   - Track which engines were tried.
   - On success, attach `cascade_metadata` to the returned take.
   - On final fallback (all engines failed), the function already
     returns None — no take to annotate; the operator sees "Motion
     Failed" instead.
6. **UI rendering** — add a small badge in:
   - `web/src/components/console/TakeStrip.tsx`: below the existing take info, show "via {engine}" + score color-coded; if `fallback`, show ⚠ FALLBACK chip.
   - `web/src/components/pipeline/ReviewStage.tsx`: in the take card, same pattern.

**Acceptance criteria:**

- [ ] ErrorBoundary exists, renders fallback UI on a controlled throw
- [ ] All three shells wrapped (EditorialShell, PipelineLayout, DirectorsConsole)
- [ ] TakeRecord type includes optional `cascade_metadata`
- [ ] At least one lipsync run produces a take with populated metadata
      that the UI renders correctly
- [ ] At least one video cascade run produces a take with populated
      metadata
- [ ] TypeScript clean (`tsc --noEmit` silent)
- [ ] CI green
- [ ] Pytest still green

**Pitfalls:**

- **ErrorBoundary catches render errors, NOT async errors.** An async
  throw in a useEffect won't be caught. That's a separate concern;
  scope-out for this session.
- **Don't break existing UI** for takes WITHOUT cascade_metadata (every
  existing take). The field is optional; consumers must check
  `take.cascade_metadata?.engine ?? 'unknown'`.
- **Don't restructure the cascade closures** in `phase_c_ffmpeg.py`.
  Touch the return path only — track attempts in a local list, attach
  to the result dict.
- **Lipsync cascade has 4 overlay + 4 generation paths.** Make sure
  both paths populate metadata; the `_gate_or_stash` closure has the
  state you need.
- **Palette discipline:** the new UI elements in `console/TakeStrip.tsx`
  must use `console-*` classes only (we just fixed a leak there in
  Bundle-C 3.4 — don't reintroduce). For `pipeline/ReviewStage.tsx`,
  use `editorial-*` only.

**Verification:**

```bash
# 1. TypeScript:
cd web && npx tsc --noEmit

# 2. Tests:
.venv/bin/python -m pytest tests/unit/ -q

# 3. Manual UI test:
#    a) Temporarily add `throw new Error("test")` in usePipelineState.processEvent
#    b) Reload UI — confirm ErrorBoundary fallback shows
#    c) Revert the throw
#
# 4. End-to-end (if pod available):
#    a) Run a generation
#    b) Inspect a take's JSON — confirm cascade_metadata present
#    c) Inspect UI — confirm "via X" badge renders + fallback ⚠ shows when appropriate

# 5. CI:
git push origin <branch>
# All 3 jobs green.
```

**Commit shape (split into 2 or 3):**

Commit 1:
```
feat(ui): ErrorBoundary at every shell

ErrorBoundary component in web/src/components/ui/. Wraps EditorialShell,
PipelineLayout, DirectorsConsole. Catches React render errors that
previously crashed the entire UI after long pipeline runs. Fallback UI
shows the error + reload button (no auto-recovery — operator decides).

Verified: temporarily threw in usePipelineState; fallback rendered;
clean recovery on reload.
```

Commit 2:
```
feat(takes): cascade_metadata field on TakeRecord

Optional field surfaces which engine produced a take, what score it
got against its quality gate, and whether the cascade fell through
to a stash-restored "best of bad" result.

Populated in:
  - lip_sync.lipsync_overlay (4-engine SyncNet cascade)
  - lip_sync.lipsync_generation (4-engine SyncNet cascade)
  - phase_c_ffmpeg.generate_ai_video (9-engine video cascade)

Renders as a "via {engine}" chip + ⚠ FALLBACK badge in TakeStrip
(console palette) and ReviewStage (editorial palette).

Operators now see when a take is a fallback, with what score and
threshold. Previously this was silent.

Verified: TypeScript clean; pytest clean; manual run on a forced
all-engines-fail scenario shows the fallback badge correctly.
```

**Estimated effort:** 3 hours.

**Decision authority:** Lane A on the badge styling, fallback UI copy,
log emission format. Escalate before:
- Adding a third-party error tracker (Sentry, Bugsnag).
- Restructuring the cascade closures (touch return paths only).
- Adding fields to TakeRecord beyond `cascade_metadata`.

**If you finish early:** Add cascade_metadata population to the
performance capture path in `cinema/shots/controller.py`'s
`generate_performance_take` — same shape, different cascade.

---

# Closing — director's note

I am giving you these six sessions because the codebase has earned a
quality investment. Not because the work that's been done is bad — the
prior directors made the right architectural calls. But because the
operational maturity hasn't caught up to the architectural ambition.

Sessions 1-3 give us safety: CI + tests for the load-bearing modules.
Sessions 4-5 give us visibility: structured logging + honest cost
tracking. Session 6 gives the operator visibility into things that
were previously silent.

Six sessions. Pick yours, do it well, surface what you find, hand off.
The next director will read your status reports as their handoff.

Status reports go in your final commit message. ARCHITECTURE.md updates
are part of your deliverable. Anything you defer goes to "Findings."
Anything that blocks you gets escalated within 30 minutes.

Don't grind. Don't ship hot. Don't combine concerns. Don't drift
documentation. Don't reinvent what already exists in this repo's
patterns (StubHost, predicate-poll, content-hash cache, etc.).

Execute. Verify. Report. Move.

Signed,
The Director, 2026-05-24
