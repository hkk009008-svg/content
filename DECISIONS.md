# Architecture Decisions

A log of significant decisions, with rationale, status, and consequences.
Each entry is **dated and immutable** — supersession is tracked via the
`Status` field, never by editing old entries.

> Format: lightweight ADR. New decisions append at the bottom. When a
> decision is overturned, mark the original `Status: Superseded by <N>`
> and write a new entry that references it.

---

## ADR-001 — Single web entry point; CLI deleted

- **Date:** 2026-05-23
- **Status:** Accepted
- **Context:** Project began as a YouTube Shorts generator with a CLI
  (`main.py`) running an autonomous batch pipeline. Operator review was
  added incrementally for quality control; eventually the interactive
  flow became the only path actually used. Maintaining two orchestrators
  meant double the bug surface, duplicated phase wrappers, and
  documentation drift.
- **Decision:** Delete `main.py`, all CLI-only phase wrappers
  (`cinema/phases/{blueprint,generation,audio,assembly,vision}.py`),
  `phase_a_generator.py`, `llm/blueprint_director.py`, `vbench_evaluator.py`,
  `comfyui_workflow_gen.py`, related test artifacts. Make `web_server.py`
  the sole entry; route all paths through `cinema_pipeline.py:CinemaPipeline`.
- **Consequences:**
  - +: ~3000 LOC removed. One mental model. No path-fork bugs.
  - +: Operator review becomes a first-class concept (4 gates).
  - −: No headless mode. Automation = scripted curl calls.
  - −: Some pre-pivot docs (REFACTOR_HANDOFF.md §13, CINEMA_PIPELINE_MIGRATION_DESIGN.md)
       describe migration plans that are now moot.

---

## ADR-002 — Predicate-poll gate model (not event-driven)

- **Date:** 2026-04 (approx, during refactor Phase 2)
- **Status:** Accepted
- **Context:** Original gate implementation used `pipeline.pause()` +
  `_check_pause()` to block the worker thread. This coupled gate state
  with pause state and required explicit `resume()` from the operator.
- **Decision:** `LifecycleService.wait_for_gate(name, predicate, poll_interval=0.5)`.
  The worker thread polls every 500ms by re-reading project JSON from
  disk and evaluating the predicate. `threading.Event` is only a
  wake-up optimization.
- **Consequences:**
  - +: Operator approvals auto-resolve gates without explicit Resume click.
  - +: SSE disconnects don't lose approval state — state lives on disk.
  - +: Crash recovery is automatic via the checkpoint.
  - −: 500ms bounded latency between approval and resume (acceptable for
       human-paced review).
  - −: Polling burns ~2 syscalls/second per project. Negligible at 1 project.
- **Cross-ref:** [ARCHITECTURE.md §6](ARCHITECTURE.md#6-gate-mechanism--predicate-poll)

---

## ADR-003 — `PipelineContext` implements dict API

- **Date:** 2026-05-22
- **Status:** Accepted
- **Context:** A multi-month silent-failure bug: code patterns like
  `getattr(settings, "tts_provider", default)` always returned `default`
  because the `config.settings.Settings` frozen dataclass carries
  env-derived keys only — UI knobs aren't on it. ~8 sites had this bug.
  The fix needed a typed home for per-project UI settings without
  breaking the legacy `def f(ctx: dict)` signature.
- **Decision:** `PipelineContext` is a `@dataclass` that ALSO implements
  the dict API (`__getitem__`, `__setitem__`, `get`, `update`, `keys`,
  `items`, `values`, `__contains__`, `__iter__`, `as_dict`). Add
  `get_project_setting(ctx, key, default)` helper as the canonical
  per-project knob reader. Make `config.settings.Settings` strictly
  env-only and `frozen=True`.
- **Consequences:**
  - +: Legacy functions taking `ctx: dict` keep working when passed a
       `PipelineContext`.
  - +: New code can rely on `ctx.lifecycle`, `ctx.audio_path`, etc., with
       type hints.
  - −: Mixed-mode usage (e.g. `audio/voiceover.py:generate_voiceover`
       using both `ctx.get(...)` and `get_project_setting(ctx, ...)`)
       persisted until that function was deleted in Bundle-D 4.3.
- **Cross-ref:** [ARCHITECTURE.md §4.2](ARCHITECTURE.md#42-pipelinecontext-cinemacontextpy)

---

## ADR-004 — IdentityValidator as process singleton via 4-way alias

- **Date:** 2026-05-22 (commit `cc34870`)
- **Status:** Accepted
- **Context:** Three independent contexts needed ArcFace identity
  scoring: keyframe validation, N=8 best-of grading, performance gate
  scoring. Each was loading its own copy of the GhostFaceNet (DeepFace)
  model — ~700MB of weights × 3 = wasted RAM. Worse, the rolling-stats
  history was per-instance, so the adaptive PuLID weight system couldn't
  see signal accumulated across contexts.
- **Decision:** Process-singleton in `identity/__init__.py` via
  double-checked locking. Provide 4 backward-compat access paths that
  all return `is`-identical instances:
  - `identity.get_shared_validator()` (canonical)
  - `phase_c_vision._get_shared_validator()` (legacy alias)
  - `face_validator_gate._get_validator()` (best-of)
  - `performance.identity_gate._get_validator()` (performance gate)
- **Consequences:**
  - +: Model loads once per process. Rolling stats accumulate from all
       contexts.
  - +: Lazy import of `phase_c_vision` (LLM vision fallback) deferred to
       first construction; `import identity.validator` doesn't pull the
       LLM module into the graph.
  - −: Naming bug propagates: every docstring + comment says "ArcFace"
       but the actual DeepFace model is `GhostFaceNet`. ArcFace is the
       loss function it was trained with. Cosmetic only; semantics are
       correct.
- **Cross-ref:** [ARCHITECTURE.md §11](ARCHITECTURE.md#11-identity-validation--ghostfacenet-singleton)

---

## ADR-005 — LLM ensemble: parallel quorum + judge (not fallback)

- **Date:** Pre-refactor (predates the ARCHITECTURE.md verification)
- **Status:** Accepted
- **Context:** Single-model creative LLMs occasionally produce
  off-template output (HC1 IDENTITY_FIREWALL violations, schema breaks,
  shot count mismatches). Sequential fallback (Anthropic → OpenAI on
  error) wastes time when Anthropic succeeds-but-poorly.
- **Decision:** `LLMEnsemble.competitive_generate(task_type, ...)` runs
  ALL configured models in parallel via `ThreadPoolExecutor`, then a
  judge model scores candidates and picks a winner. Dead providers
  degrade gracefully (filtered, not crash-on-fail).
- **Consequences:**
  - +: Best-of-multiple-models quality.
  - +: Provider failure surface is forgiving.
  - −: **2× LLM cost when `competitive_generation=True`** (default).
       Operators rarely realize this. Surfacing cost in UI is a strategic
       open item — see [docs/STRATEGIC_REVIEW-2026-05-24.md](docs/STRATEGIC_REVIEW-2026-05-24.md).
  - −: Gemini is wired but opt-in (not in default rosters). Default
       rosters are Anthropic + OpenAI.

---

## ADR-006 — ComfyUI workflow JSONs at repo root

- **Date:** Pre-refactor
- **Status:** Accepted
- **Context:** PuLID workflows are operator-editable; they're effectively
  "source code" of the image generation behavior. Putting them under
  `workflows/` would feel proper, but inflates the import path and adds
  a directory traversal step in `_load_max_workflow`.
- **Decision:** `pulid.json` and `pulid_max.json` live at the repo root.
  Module-level cache + `_WORKFLOW_LOCK` prevent double-load. Each call
  deep-copies the cached JSON before injecting per-shot values.
- **Consequences:**
  - +: One step to find and edit the workflow.
  - +: Simple import: `os.path.join(os.path.dirname(__file__), "pulid_max.json")`.
  - −: Mixed-content repo root (Python + JSON). Visual noise but minor.
  - −: If we ever support N templates per shot type, we'd want a
       `workflows/` directory. Defer.

---

## ADR-007 — Pedalboard as a hard dependency

- **Date:** Pre-refactor
- **Status:** Accepted
- **Context:** `audio/effects.py` uses Spotify's Pedalboard for voice/music
  DSP (reverb, compressor, EQ, distortion). Earlier code had a
  `try/except ImportError` around the import to make pedalboard
  conditional.
- **Decision:** Remove the guard. Import unconditionally.
- **Consequences:**
  - +: Effects always work — no silent degradation when pedalboard
       isn't installed.
  - +: Setup is one fewer optional path.
  - −: `pip install -r requirements.txt` always installs pedalboard
       (~30MB native lib). Acceptable.

---

## ADR-008 — `ARCHITECTURE.md` as single source of truth

- **Date:** 2026-05-24
- **Status:** Accepted
- **Context:** CLAUDE.md, AGENTS.md, and HANDOFF.md all carried duplicate
  Architecture Preambles. Each session refresher had to verify three
  preambles against code, then fix drift in each. At least 14 stale
  claims were documented post-pivot:
  - "ArcFace" (it's GhostFaceNet)
  - "no Gemini in LLMEnsemble" (Gemini is wired opt-in)
  - "`_VEO_QUOTA_EXHAUSTED` has no reset" (now TTL-based)
  - "`get_adaptive_pulid_weight` returns None" (three explicit returns)
  - Dead-code claims about functions that were already excised
  - LOC counts off by 5-50 lines per file
- **Decision:** Extract a single `ARCHITECTURE.md` at repo root as the
  *truth layer*. CLAUDE.md and AGENTS.md remain the *process layer*
  (session discipline + multi-task orchestration). Archive `HANDOFF.md`
  to `docs/archive/`. Update legacy `docs/REFACTOR_HANDOFF.md` +
  `docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md` banners to point at
  ARCHITECTURE.md. Add §15 smoke block + standing rule: any session
  finding stale claims fixes them in the same commit.
- **Consequences:**
  - +: One file to verify per session. One file to fix on drift.
  - +: Cross-references between sections all link to file:line
       (clickable in markdown renderers).
  - −: Long file (1200+ lines). Mitigated by §1 TOC + heavy table usage.
  - −: Adding new docs in the future requires the same discipline —
       every new .md needs a distinct "what question does this answer"
       justification.

---

## ADR-009 — PERFORMANCE_REVIEW gate symmetric with other 3 gates

- **Date:** 2026-05-24
- **Status:** Accepted
- **Context:** PLAN_REVIEW, KEYFRAME_REVIEW, and REVIEW had matching
  predicates in `ReviewController._gate_satisfied` + matching REST
  approve endpoints. PERFORMANCE_REVIEW had no predicate clause (returned
  `False` always) and no `/performance/approve` endpoint. The orchestrator
  bypassed via an inline `all_skipped` check at
  `cinema_pipeline.py:768-773`. Operator unblock = edit driving video or
  delete take. Asymmetric, confusing, undocumented.
- **Decision:** Wire the gate properly: add `_gate_satisfied`
  PERFORMANCE_REVIEW clause (satisfied iff every shot is SKIP, or has
  no approved keyframe, or has `approved_performance_take_id`); add
  `POST /api/projects/<pid>/shots/<sid>/performance/<take_id>/approve`;
  add `approve_take(..., "performance")` branch; add UI button in
  ReviewStage.tsx Performance Capture section; thread
  `onApprovePerformance` prop through App → PipelineLayout → ReviewStage
  → ClipCard.
- **Consequences:**
  - +: Four-gate review model is uniform — same predicate shape,
       same endpoint shape, same UI affordance.
  - +: Orchestrator `all_skipped` check is now redundant for correctness
       but kept for the explicit `PERFORMANCE_SKIPPED_GATE` UX event.
  - +: New operator-visible artifact: `performance_approved` count in
       `_project_gate_status` for UI / live cost dashboards.
- **Cross-ref:** [ARCHITECTURE.md §6.1](ARCHITECTURE.md#61-_gate_satisfied-predicates-cinemareviewcontrollerpy201-212)

---

## ADR-010 — N=8 best-of parallelism behind a project setting

- **Date:** 2026-05-24
- **Status:** Accepted
- **Context:** `quality_max.py`'s N=8 candidate loop ran sequentially
  despite a docstring claim of parallelism. On a 4-candidate batch,
  each candidate's submit→poll→download→score serialized — measured
  ~200ms for a mock workload that should parallelize in ~50ms.
- **Decision:** Add `global_settings.max_quality_parallel_workers`
  (default 1, clamp [1, 4]). Wrap the batch loop in
  `ThreadPoolExecutor.map` so workers=1 stays byte-identical to the
  prior sequential behavior. Pre-compute seeds + paths before the
  parallel block to avoid races on `len(scores)`. Surface in
  MaxQualityTierSection.tsx as a 3-choice toggle
  (Sequential / 2 workers / 4 workers).
- **Consequences:**
  - +: Operator opt-in to ~3.9× speedup (measured).
  - +: Default behavior unchanged (no pod-overload risk for existing
       projects).
  - +: ComfyUI still serializes GPU work per pod — gain is overlapping
       I/O + scoring with next-candidate generation.
  - −: At workers=4, a 4-candidate batch runs all 4 even if halt would
       have triggered after candidate 1. Operators trading wall-clock
       for total compute.
- **Cross-ref:** [ARCHITECTURE.md §8.3](ARCHITECTURE.md#83-max-tier--quality_maxpy-n8-adaptive-best-of)

---

## ADR-011 — `threshold=0.0` in identity reads was a silent ML signal bug

- **Date:** 2026-05-24
- **Status:** Accepted (fix landed)
- **Context:** `face_validator_gate._arcface_score` and
  `performance/identity_gate._arcface_score` both called
  `IdentityValidator.validate_image(..., threshold=0.0)` to get the
  similarity score. But `validate_image` writes `passed=(score >= threshold)`
  into the rolling-history entry. With `threshold=0.0`, every read counted
  as `passed=True` — polluting `get_rolling_stats(...).success_rate` toward
  optimism, which then fed `workflow_selector.get_adaptive_pulid_weight`
  and made the adaptive weight system push PuLID down when it should
  push it up.
- **Decision:** Add a `threshold` parameter to both `_arcface_score`
  helpers and to `score_candidate`. `quality_max` reads
  `identity_strictness` from ctx (default 0.60) and passes it through.
  `validate_performance_take` passes its previously-ignored `floor`
  parameter as the threshold.
- **Consequences:**
  - +: `mean_similarity` is unchanged (real signal).
  - +: `success_rate` becomes meaningful — fraction of generations that
       would have been accepted as final shots.
  - +: Adaptive PuLID weight feedback loop has honest input.
  - −: Existing rolling-history entries (pre-fix) are polluted. Reset
       behavior on the validator's `history` list happens per-process,
       so a server restart clears the bad data.

---

## ADR-012 — Document structure: README → ARCHITECTURE → OPERATIONS → DECISIONS

- **Date:** 2026-05-24
- **Status:** Accepted
- **Context:** Post-pivot the repo had three overlapping "where do I
  start" docs (CLAUDE.md, AGENTS.md, HANDOFF.md) plus an extracted
  ARCHITECTURE.md. New contributors couldn't tell which to read first.
- **Decision:** Establish a four-doc surface at the repo root:
  - **README.md** — front door (what/who/quick-start/pointers)
  - **ARCHITECTURE.md** — truth layer (verified facts about the code)
  - **OPERATIONS.md** — runtime guide (env, run, pod setup, troubleshooting)
  - **DECISIONS.md** — this file (ADR log with rationale)
  - **CLAUDE.md / AGENTS.md** — process discipline for AI agents
  - **docs/STRATEGIC_REVIEW-<date>.md** — open critique + forward direction
  - **docs/archive/** — past handoffs as historical record
  - **docs/REFACTOR_HANDOFF.md** + **docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md** — preserved at top-of-docs/ for code-comment references; clearly banner-marked as historical.
- **Consequences:**
  - +: Each file answers one question.
  - +: README.md is the conventional front door (pyproject's `readme`
       pointer also moves here).
  - −: More files, more drift potential. Discipline: new docs require
       a "what unique question does this answer" justification.

---

## ADR-013 — Verification discipline for factual claims

- **Date:** 2026-05-24
- **Status:** Accepted
- **Context:** The new-director STRATEGIC_REVIEW (commit `af9bad2`) and the
  derived operator HANDOFF (commit `0e66bed`) both contained a load-bearing
  factual error: the claim that `tests/unit/` had "only one test file"
  when there were 24. The error survived into the handoff because that
  doc was written from the same anchored mental model without independent
  verification, and inherited the false claim into specific session
  instructions ("Create `tests/unit/test_workflow_selector.py`" and
  "Create `tests/unit/test_cost_tracker.py`" — both files already existed).
  Root-cause analysis identified five contributing factors:
    1. Anchoring on the first observation (Bundle-C 3.5 touched
       `test_project_persistence.py` early; that file became the mental
       model of "the test suite").
    2. Scope-narrow pytest output (`pytest tests/unit/test_project_persistence.py`)
       reported as scope-wide unit suite state.
    3. Confirmation bias on a narrative ("operational immaturity"
       supported by "thin test coverage" → didn't push to falsify).
    4. Session memory trusted over filesystem (`ls tests/unit/` is 200ms
       and was never run).
    5. Writing momentum override of sanity-check pauses (director-voice
       authority created false confidence in the factual substrate).
  Critically: the same authoring session produced the rule "Verify before
  you assert" (HANDOFF principle #1) and broke it. The class of error is
  fully preventable with mechanical rules.
- **Decision:** Codify three mechanical rules in CLAUDE.md and AGENTS.md
  under a new top-level "Verification discipline for factual claims"
  section:
  1. No inventory claim without verification output in the same change.
  2. Scoped output stays scoped (no generalizing from a narrow command).
  3. Pre-commit trip-wire on strategic / authority-voice docs (paste
     verifying command output in the commit message).
  Plus an honesty clause: when the verifying command cannot be run,
  flag the claim as unverified explicitly. Never apply authority-voice
  over an unverified factual claim.
  The rule's scope: specific factual claims (counts, file presence,
  function existence). Qualitative directional claims are out of scope —
  judgment + uncertainty flagging suffice.
- **Consequences:**
  - +: Specific class of error (factual inventory claims unverified
       against filesystem) becomes mechanically caught at author-time.
  - +: Commit messages carry their own verification trail; future
       directors can re-run the same commands to detect drift.
  - +: Director-voice authority is now tied to verification effort,
       which is the right alignment — authority earned by checking,
       not asserted by tone.
  - −: Slight friction on doc-writing flow (re-run command, paste
       output). Cheap (seconds) but real.
  - −: Doesn't catch bias-driven errors that survive verification
       (e.g., confirmation bias on the framing of a question that is
       then verified within its own framing). Tier-3 tooling
       (doc-claim CI lint + closing-verification subagent) addresses
       that level; tracked as P1-5 in STRATEGIC_REVIEW-2026-05-24.md.
- **Cross-ref:** [CLAUDE.md](../CLAUDE.md) /
  [AGENTS.md](../AGENTS.md) "Verification discipline for factual claims"
  section. [STRATEGIC_REVIEW-2026-05-24.md](docs/STRATEGIC_REVIEW-2026-05-24.md)
  P1-5 for the tooling follow-on.

---

## ADR-014 — Motion-gate auto-approve as opt-in env flag (CINEMA_AUTO_APPROVE_MOTION)

- **Date:** 2026-05-25
- **Status:** Accepted
- **Context:** Session 11 (`d6fd3e1` / `ad526c3`) shipped per-gate auto-approve
  infrastructure including motion-rule builders (`_rules_for_motion` in
  `cinema/auto_approve.py`) with 3 veto rules: identity threshold, motion-score
  threshold, and cascade-fallback veto. However, `cinema/review/controller.py`'s
  `_gate_map` deliberately omitted `PERFORMANCE_REVIEW → "motion"`, with a docstring
  carve-out: *"PERFORMANCE_REVIEW has no auto-approve path in v1."* Result: motion
  rules were unit-tested but dead in production. Session 11's spec reviewer flagged
  the divergence between tested and reachable behavior. Director surfaced this to
  user 2026-05-25; user chose the feature-flag default-off pattern.
- **Decision:** Wire motion-gate as an opt-in env flag (`CINEMA_AUTO_APPROVE_MOTION=1`),
  default off. Mirrors Session 10's `CINEMA_STRICT_SCHEMA` pattern — an opt-in
  escalation that lets operators promote tested behavior to production at their
  discretion without changing v1 defaults. The helper `is_motion_gate_enabled()` lives
  in `cinema/auto_approve.py` (co-located with the rules; directly testable without
  instantiating the controller). Parser uses `.strip().lower()` to accept `"True"`,
  `"YES"`, etc. — closes the case-sensitivity papercut that S10's code-quality reviewer
  flagged on `CINEMA_STRICT_SCHEMA`. The "opt-in escalation pattern" is now formalized
  (used twice: `CINEMA_STRICT_SCHEMA`, `CINEMA_AUTO_APPROVE_MOTION`); future gates that
  ship tested-but-dead code follow this pattern by default.
- **Consequences:**
  - v1 default behavior is preserved (motion auto-approve remains off unless env flag
    is explicitly set).
  - Operators can enable motion auto-approve in production when they have validated
    the rules' thresholds against their content.
  - Frontend (Session 13's scope) must handle motion entries in the audit log
    gracefully when the flag is on, but treat their absence as the v1 default.
  - The `.lower()` parse form is preferred over S10's literal-case tuple for future
    env-flag helpers; a future cleanup may unify the two parsers.
- **Alternatives considered:**
  - Wire on by default: rejected — too risky without calibration data on real content.
  - Mark motion as test-only-for-v1: rejected — wastes the working infrastructure
    and risks orphaning the code over time.
- **Tracking:** Session 12 implementation; commit refs filled in at ship time.
- **Cross-ref:** `cinema/auto_approve.py::is_motion_gate_enabled`,
  `cinema/review/controller.py::_run_auto_approve_pass`.

---

*To add a new decision: copy the template below, increment the ADR
number, fill in Context / Decision / Consequences, and append at the
bottom. Do not edit prior entries — supersede via Status field instead.*

```
## ADR-NNN — <Short imperative title>

- **Date:** YYYY-MM-DD
- **Status:** Proposed | Accepted | Superseded by ADR-XXX | Rejected
- **Context:** What's the problem, what existed before, what triggered the discussion.
- **Decision:** What was decided. Be specific — names of types/functions, file paths.
- **Consequences:**
  - +: Wins
  - −: Tradeoffs accepted
- **Cross-ref:** Link to ARCHITECTURE.md section if applicable.
```
