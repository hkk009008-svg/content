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
   .venv/bin/python -c "<paste ARCHITECTURE.md §15 smoke block>"
   .venv/bin/python -m pytest tests/unit/ --tb=no -q
   cd web && npx tsc --noEmit && cd ..
   ```
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
   - Acceptance: 6 pass + 3 skip is the current correct outcome
     (matches the 3 pre-existing failures in
     `test_project_persistence.py` documented as `@unittest.skip`).
     If the count is different, your session uncovered something.
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

## SESSION 2 — P0-1.1: ReviewController unit tests

**Why this matters.** `cinema/review/controller.py` carries the gate
predicates that decide when the pipeline can advance. PERFORMANCE_REVIEW
was just wired up (commit `b4dc37b`); the verification was a Python
script in conversation, not a test. That means the next refactor of the
gate machinery has no safety net.

Beyond the new gate: this file owns `approve_take` (the take-approval
state machine, three approval kinds, source_take_id chain walking for
postprocess variants) and `_project_gate_status` (which the UI consumes
for live progress). All untested.

**Pre-work:**

1. Read [cinema/review/controller.py](../cinema/review/controller.py)
   end-to-end. 333 LOC; readable in 10 minutes.
2. Read [ARCHITECTURE.md §6](../ARCHITECTURE.md#6-gate-mechanism--predicate-poll)
   for the gate model context.
3. Read [tests/unit/test_project_persistence.py](../tests/unit/test_project_persistence.py)
   for the existing test style. Match it (unittest.TestCase + the
   tempfile-per-test pattern). Don't introduce pytest fixtures unless
   you have a strong reason.

**Scope:**

| IN | OUT |
|---|---|
| `_gate_satisfied(gate, project)` × 4 gates × ≥3 cases each | Integration with real ShotController |
| `approve_take(shot_id, take_id, approval_kind)` × 3 kinds | Integration with `_wait_for_gate` loop |
| `_project_gate_status` counts (all 5 fields) | Integration with `lifecycle.wait_for_gate` (lifecycle has its own test seam) |
| `_candidate_take` resolution (4 cases) | `proceed_to_assembly` flow (e2e territory) |
| `_resolve_motion_source` chain walking for final approval | `_rebuild_review_clips` (separate concern) |

**Approach (specific):**

1. Create `tests/unit/test_review_controller.py`.
2. Use the StubHost pattern from the session above:
   ```python
   class StubHost:
       def __init__(self):
           self.find_take_returns = None  # tests override
           self.mutate_shot_calls = []     # for assertions
       def _refresh_project_snapshot(self, timeout=10):
           return None
       def _find_take(self, shot, take_id):
           return self.find_take_returns or (None, None)
       def _mutate_shot(self, shot_id, mutator, timeout=10):
           # Tests provide a shot dict via setUp; mutator runs on it
           return mutator({}, self.shot_state).value
       def resume(self):
           self.resume_called = True
   ```
3. Use `PipelineCore.__new__(PipelineCore)` to construct a core without
   going through `build_pipeline_core` (no disk I/O).
4. **Test cases (minimum set):**

   **`_gate_satisfied`:**
   - `gate=PLAN_REVIEW` × empty project → False
   - `gate=PLAN_REVIEW` × all `plan_status=approved` → True
   - `gate=PLAN_REVIEW` × one not approved → False
   - `gate=KEYFRAME_REVIEW` × all have `approved_keyframe_take_id` → True
   - `gate=KEYFRAME_REVIEW` × one missing → False
   - `gate=PERFORMANCE_REVIEW` × empty → False (no shots)
   - `gate=PERFORMANCE_REVIEW` × all SKIP → True
   - `gate=PERFORMANCE_REVIEW` × all approved → True
   - `gate=PERFORMANCE_REVIEW` × mix (SKIP + approved + no-keyframe) → True
   - `gate=PERFORMANCE_REVIEW` × one needs but unapproved → False
   - `gate=REVIEW` × all `approved_final_take_id` → True
   - `gate=REVIEW` × one missing → False
   - `gate=UNKNOWN_NAME` → False (default branch)

   **`approve_take`:**
   - `approval_kind=keyframe` × take in `keyframe_takes` → sets `approved_keyframe_take_id`
   - `approval_kind=keyframe` × take in `motion_takes` → error "not a keyframe"
   - `approval_kind=performance` × take in `performance_takes` → sets `approved_performance_take_id`
   - `approval_kind=performance` × take in `keyframe_takes` → error "not a performance"
   - `approval_kind=final` × take in `motion_takes` → sets BOTH `approved_motion_take_id` AND `approved_final_take_id`
   - `approval_kind=final` × take in `postprocess_variants` with valid `source_take_id` chain → walks back, sets motion + final
   - `approval_kind=final` × take in `keyframe_takes` → error "keyframes cannot be approved as final"
   - `approval_kind=unknown` → error "unsupported approval kind"
   - shot_id not found → error "Shot not found"
   - take_id not found → error "Take not found"

   **`_project_gate_status`:**
   - All 5 counts present and correct for a known fixture
   - Empty project → all zero

5. Run with: `.venv/bin/python -m pytest tests/unit/test_review_controller.py -v`

**Acceptance criteria:**

- [ ] ≥20 test cases, all passing
- [ ] Every branch of `_gate_satisfied` exercised
- [ ] Every branch of `approve_take`'s mutator exercised
- [ ] Postprocess-variant `source_take_id` chain walk is tested with a
      multi-hop chain (variant → variant → motion)
- [ ] Runs in < 5 seconds
- [ ] CI from Session 1 picks up the new tests and goes green

**Pitfalls:**

- **`_find_take` is on the HOST**, not on ReviewController. Your
  StubHost must implement it correctly. Note the return shape:
  `(collection_name: Optional[str], take: Optional[dict])`.
- **`_mutate_shot` returns the mutator's `MutationResult.value`**, not
  the dict. Read [cinema/review/controller.py:280](../cinema/review/controller.py)
  to see the pattern.
- **`approval_kind="performance"` is the new branch** from
  commit `b4dc37b`. Make sure your test covers the validation that the
  take must live in `performance_takes`, not just any collection.
- **The chain walk in `_resolve_motion_source`** has visited-set
  protection against infinite loops. Test that too (synthetic loop in
  source_take_id pointers should not hang).
- **Don't import `cinema_pipeline`** in the test. ReviewController is
  composable independently per [ADR-009](../DECISIONS.md). Importing
  the orchestrator drags in heavy deps and defeats the test seam.

**Verification:**

```bash
.venv/bin/python -m pytest tests/unit/test_review_controller.py -v
# Expect: ≥20 tests, all passing, < 5 seconds.

# Also check CI:
git push origin <branch>
# Session 1's CI runs the full tests/unit/ — should still be green.
```

**Commit shape:**

```
test(review): unit tests for _gate_satisfied + approve_take + status

22 test cases covering every branch of the gate predicate (incl. the
new PERFORMANCE_REVIEW clause from b4dc37b) and approve_take's three
approval_kind branches incl. the source_take_id chain walk for
postprocess variants.

StubHost pattern (no disk I/O, no real lifecycle); PipelineCore
constructed via __new__ to avoid build_pipeline_core's heavy deps.
Matches the existing tests/unit/ style (unittest.TestCase).

Verified: 22 pass in 0.8s; CI green.
```

**Estimated effort:** 2-3 hours.

**Decision authority:** Lane A on test structure. Escalate before:
- Adding pytest fixtures or `conftest.py` (the existing style is
  unittest.TestCase — match it).
- Modifying anything in `cinema/review/controller.py` itself except
  comments. If your tests reveal a bug, document it in Findings and
  STOP — director decides whether to fix in this session or a follow-up.

**If you finish early:** Audit `_rebuild_review_clips` and add a few
tests for it. Don't add tests for `proceed_to_assembly` — that needs
real lifecycle setup and belongs in a separate session.

---

## SESSION 3 — P0-1.2: workflow_selector unit tests

**Why this matters.** `workflow_selector.classify_shot_type` is the
keyword-driven router that decides which video API cascade a shot will
hit. A typo in `SHOT_TYPE_KEYWORDS` silently changes routing for every
shot matching that keyword. `WORKFLOW_TEMPLATES` MUST have exactly 5
keys aligned with `MOTION_FIDELITY_FLOORS` and `domain/shot_types.py` —
drift between these is a real risk during refactors.

The strategic review flagged this as P0-1.2 because the cost of a
silent routing bug is hours of wrong-engine generations (Sora when you
wanted Kling) before an operator notices.

**Pre-work:**

1. Read [workflow_selector.py](../workflow_selector.py) — focus on
   `WORKFLOW_TEMPLATES`, `SHOT_TYPE_KEYWORDS`, `classify_shot_type`,
   `get_adaptive_pulid_weight`, and `MOTION_FIDELITY_FLOORS`.
2. Read [domain/shot_types.py](../domain/shot_types.py) for the
   canonical shot type set and `normalize_shot_type`.
3. Read [ARCHITECTURE.md §9](../ARCHITECTURE.md#9-video-routing--5-templates--11-engines)
   for the routing context.

**Scope:**

| IN | OUT |
|---|---|
| `classify_shot_type` × every keyword in `SHOT_TYPE_KEYWORDS` | `MAX_QUALITY_TEMPLATES` tests (separate session) |
| `classify_shot_type` × empty `characters_in_frame` → landscape | `get_max_quality_params` (separate session) |
| `classify_shot_type` × no matching keyword → medium (default) | `_validate_overlay_value` (already partly tested via Step 3 smoke) |
| `classify_shot_type` priority — `[SHOT]` section before full prompt | `_swap_to_hidream` (max-tier territory) |
| `WORKFLOW_TEMPLATES` shape (5 keys, valid target_api + fallbacks) | Anything in `quality_max.py` |
| `MOTION_FIDELITY_FLOORS` keys ⊆ `domain/shot_types.py` canonical set | |
| `get_adaptive_pulid_weight` × multiple rolling-stats scenarios | |

**Approach:**

1. Create `tests/unit/test_workflow_selector.py`.
2. Parametrize the keyword tests. For each keyword in
   `SHOT_TYPE_KEYWORDS[shot_type]`, build a shot dict where the
   keyword appears in `prompt` and assert `classify_shot_type` returns
   `shot_type`.
3. For the `[SHOT]`-section priority: build a shot with `[SHOT]
   tracking dolly...` in prompt — verify it returns `action` (matched
   by [SHOT] section) even if a later keyword would match a different
   bucket.
4. For `get_adaptive_pulid_weight`: build a stub IdentityValidator
   exposing `get_rolling_stats(character_id, window=10) -> dict`. Test
   the four boost paths:
   - No samples → returns base_weight unchanged
   - success<0.5 → +0.10
   - success<0.8 → +0.05
   - perfect AND mean>0.80 → -0.05
   - clamped to [0.0, 1.0]
5. For `WORKFLOW_TEMPLATES`: assert keys exactly = `{portrait, medium,
   wide, action, landscape}`; for each, assert `target_api` is in
   `TARGET_APIS` (or `None`), `video_fallbacks` is a list of valid
   engine strings or `None`.
6. For `MOTION_FIDELITY_FLOORS`: assert `set(FLOORS.keys()) <= set(domain.shot_types.SHOT_TYPES)` — this catches the kind of drift the strategic review documented.

**Acceptance criteria:**

- [ ] ≥30 test cases (every keyword × one shot per keyword + edge cases)
- [ ] All keyword routes verified
- [ ] `WORKFLOW_TEMPLATES` shape locked
- [ ] `MOTION_FIDELITY_FLOORS` alignment with `domain/shot_types.py` enforced
- [ ] `get_adaptive_pulid_weight` covered for all four boost paths + clamping
- [ ] Runs in < 3 seconds
- [ ] Session 1's CI green

**Pitfalls:**

- **"macro" is a portrait keyword**, not a shot type. Test that a shot
  with "macro" in the prompt routes to `portrait`, NOT to any imaginary
  "macro" bucket.
- **`MOTION_FIDELITY_FLOORS` has `close_up`** but `classify_shot_type`
  never returns `close_up`. That's intentional — `normalize_shot_type`
  in `domain/shot_types.py` handles `close_up` as an alias. Your alignment
  test should subset-check, not equality-check.
- **`classify_shot_type` searches case-insensitively** via lowercased
  match. Don't rely on case for your test inputs.
- **First-match-wins in keyword order.** A prompt with multiple
  matching keywords routes to the FIRST shot type declared in
  `SHOT_TYPE_KEYWORDS`. Test order sensitivity.
- **Empty `characters_in_frame` always returns landscape**, regardless
  of prompt. That's the special-case early return.

**Verification:**

```bash
.venv/bin/python -m pytest tests/unit/test_workflow_selector.py -v
# Expect ≥30 tests, all passing, < 3s
```

**Commit shape:**

```
test(workflow_selector): keyword routing + template shape + floor alignment

35 cases covering every keyword in SHOT_TYPE_KEYWORDS routing to its
correct shot_type, plus the [SHOT]-section-first priority, plus
empty-characters → landscape, plus get_adaptive_pulid_weight's four
adjustment paths and clamping.

Also locks the WORKFLOW_TEMPLATES shape (5 keys exact) and the
MOTION_FIDELITY_FLOORS ⊆ domain.shot_types.SHOT_TYPES subset
invariant — refactors that drift these now fail fast in CI.

Verified: 35 pass in 0.4s; CI green.
```

**Estimated effort:** 2 hours.

**Decision authority:** Lane A on test structure. Escalate before:
modifying `workflow_selector.py` itself; changing `SHOT_TYPE_KEYWORDS`
ordering or values; touching `domain/shot_types.py`.

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

## SESSION 5 — P0-3: Cost-tracking + try/except audit

**Why this matters.** Bundle-A 1.3 (commit `491af65`) fixed a silent
`AttributeError` in `ShotController.cost_tracker` that had been
swallowing cost-tracking writes. Cost data was being silently dropped.
The PATTERN that hid the bug (`try/except AttributeError: pass`) is
unacceptable as a codebase convention — every instance is a potential
hidden bug.

The strategic review flagged this as P0-3 because cost is the operator's
real-money concern, and invisible cost-tracking gaps mean we can't
diagnose budget overruns when they happen.

**Pre-work:**

1. Enumerate every silent-except in the codebase:
   ```bash
   grep -rn "except.*:\s*pass" --include="*.py" . | grep -v "/.claude/" | grep -v "__pycache__"
   ```
2. Categorize each hit:
   - **Defensive (acceptable)**: catching ImportError for optional packages, catching specific expected errors with intent.
   - **Hiding bugs (unacceptable)**: catching broad exceptions to "keep going" — these need explicit handling.
3. Audit every `record_api_call` call site:
   ```bash
   grep -rn "record_api_call\|cost_tracker\." --include="*.py" .
   ```

**Scope:**

| IN | OUT |
|---|---|
| Every `try/except: pass` decided ACCEPTABLE or REPLACED | Refactor of `cost_tracker.py` itself |
| Every `record_api_call` site verified reachable | New cost-tracking sites (separate session) |
| `cost_tracker.py` test for the basic record + retrieve cycle | UI changes for cost display |
| OPERATIONS.md §10 (cost table) updated with current measured numbers if available | Cost reporting/aggregation features |

**Approach:**

1. **For each silent-except, two-pass triage.**
   - Pass 1: Categorize (10-20 minutes). Don't fix yet — just decide
     ACCEPTABLE / NEEDS_FIX for each. Surface the count in your
     status report.
   - Pass 2: Fix the NEEDS_FIX cases. Each becomes one of:
     - `except Exception as e: logger.warning(f"<context>: {e}")` (best-effort
       operation, e.g., cost tracking)
     - `except SpecificError: <real handling>` (the exception was load-bearing)
     - Remove the try/except entirely (the exception can't actually happen)
2. **Cost-tracker audit:**
   - For each `record_api_call` site, verify:
     - The call would succeed if `self.cost_tracker` is a real instance.
     - The error path (if any) doesn't silently drop data.
     - The arguments are correct (api_name, cost_usd, latency_ms, etc.).
   - Add a basic unit test for `CostTracker.record_api_call` → in-memory query → totals add up.

**Acceptance criteria:**

- [ ] All `try/except: pass` audited (count + decision documented in
      status report)
- [ ] All NEEDS_FIX cases either replaced with explicit handling or
      moved to "Findings" with a director note
- [ ] All `record_api_call` sites verified live (manually traced)
- [ ] `tests/unit/test_cost_tracker.py` exists with at least 5 tests
- [ ] §15 smoke still passes; CI green
- [ ] A test run of `web_server.py` with a real project shows
      non-empty `SELECT * FROM api_calls` in the SQLite DB

**Pitfalls:**

- **`try/except ImportError: pass` for optional deps** is acceptable
  (e.g., `try: from optional_pkg import X; X_AVAILABLE = True; except
  ImportError: X_AVAILABLE = False`) — don't replace these.
- **`try/except Exception: pass` inside a polling loop** might be
  legitimate (transient network errors that should be retried). Read
  the surrounding context before changing.
- **Don't break the test in
  `tests/unit/test_project_persistence.py`** — its 3 skipped tests are
  documented separately. Your audit should not touch them.
- **`cost_tracker.py` may have its own internal try/except patterns.**
  Audit it too; it's the load-bearing module.
- **SQLite write contention.** If your test runs in parallel with a
  real server, you can hit lock errors. Use a tempdir for test DBs.

**Verification:**

```bash
# 1. Audit count
grep -rn "except.*:\s*pass" --include="*.py" . | grep -v "/.claude/" | grep -v "__pycache__" | wc -l
# Before: <N>. After your changes: <M>. M should be ≤ N, every remaining is documented as ACCEPTABLE.

# 2. Cost test:
.venv/bin/python -m pytest tests/unit/test_cost_tracker.py -v

# 3. Manual smoke:
.venv/bin/python -c "
from cost_tracker import CostTracker
ct = CostTracker(budget_usd=10.0)
ct.record_api_call('test_api', cost_usd=0.05, latency_ms=100)
# inspect DB
"
```

**Commit shape:**

```
fix(cost): audit silent-except patterns + verify record_api_call sites

Found <N> try/except:pass instances. Categorization:
  <X> ACCEPTABLE — optional import guards, idiomatic in this codebase
  <Y> REPLACED with explicit logger.warning/exception (this commit)
  <Z> moved to Findings for director review (out of scope for fix)

Every record_api_call site traced and verified reachable via
cost_tracker proxy (Bundle-A 1.3 set this up). Added
tests/unit/test_cost_tracker.py with 7 tests covering record + query
+ aggregation.

Verified: 7/7 cost tests pass; smoke OK; CI green.

Side finding: <anything noteworthy>.
```

**Estimated effort:** 3 hours.

**Decision authority:** Lane A on categorization of individual
try/except patterns. Escalate when ambiguous or when the fix would
change behavior beyond logging.

**If you finish early:** Audit one of the deferred subsystems (audio/,
performance/, llm/) — same triage pattern, same fix shape. Get the
codebase to "no silent excepts anywhere."

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
