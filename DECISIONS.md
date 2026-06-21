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

## ADR-015 — Cycle-16 close: brief v2.0, insight-achievement reframe, Rule #16

- **Date:** 2026-05-28
- **Status:** Accepted
- **Context:** Cycle-16 ran the v1.0 4-tier predictive-harness gauntlet (Tier A
  pre-flight + Tier B Korean dialogue probe + Tier C cheongsam reel + max-quality
  audit `a79c59`) end-to-end. Outcome: 17 findings closed (9 Tier-B + 1 Tier-C
  inline `024723d` + 3 audit quick-wins + others), 5 deferred to cycle-17 (2
  CRITICAL C-D3/C-D4 + 2 IMPORTANT C-D2/C-D5 + 1 INFO), 6 advisory open, 10+
  implemented-but-unutilized features catalogued, 3 cost-attribution bugs found.
  Pytest 925→973/3/0. Cost $8.55-9.10 of $50. Two strategic inputs reshaped the
  close: (a) user-principal Q7 **pivoted to brief v2.0 FIRST** (Phases 1-4
  execution → cycle-17); (b) a user-principal design advisory
  (`docs/brief-2.0-advisory.md`) reframed the test toward **insight-achievement
  over pass/fail**. The advisory reached BOTH seats without owner-spec — a
  Shape-A race (see Rule #16).
- **Decision:**
  1. **Brief v2.0 full re-author** (`docs/BRIEF-comprehensive-test-v2.0-2026-05-28.md`,
     `c360952`; supersedes v1.0, preserved). 6 tiers (added Tier E closed-finding
     regression + Tier F audit re-execution); A9 refined to probe ACTUAL workflow
     `class_type` (closes the C-B1/C-D4 misleading-PASS root); mechanism-MARKER
     discipline with PASS/DEGRADED/FAIL (closes the PuLID compensating-mechanism
     illusion); validation-first sequencing.
  2. **Insight-achievement reframe** (advisory-integrated, `110aff6`): the test's
     *product* is a **located divergence-point** (where the brief failed to
     transmit intent), not a pass/fail verdict — PASS/DEGRADED/FAIL is the
     *detector*. The metric is **prediction-match rate, not rationale-volume**
     (the explicit failure mode to refuse). Mechanism = intent-encoding (INTENT
     field at dispatch level) + purpose-verification (folded into Lane V, not a
     new lane) + divergence-logging (INTENT-GAP | REAL-BUG | PREDICTION-ERROR
     classification; only INTENT-GAP feeds brief-enrichment). All three are
     **candidates (N=0)**, piloted on cycle-17 Phase-1 Lane B per the N=2
     discipline. The director-vs-self-understanding distinction is explicit:
     agent rationale-text is plausible reconstruction, useful as signal, NOT
     introspective truth.
  3. **Rule #16 codified** (`7773502`; brief §8.2 is the design home, CLAUDE.md
     is the binding mirror). Beneficiary: both. Both seats independently designed
     the same insight-achievement mechanism from the same advisory (five-for-five
     convergence) — the Shape-A net-positive that motivates the rule.
  4. **Cost-attribution audit (§9) + implemented-but-unutilized catalog (§10)**
     documented in the brief and deferred to cycle-17 as P1/P2 work items (per
     user Q2 fold + Q3); not blockers for cycle-17 entry but cost-attribution
     MUST close before any Tier D scale execution.
- **Consequences:**
  - +: The brief now catches the failure class v1.0's own execution exposed
    (probe-vs-workflow divergence; compensating-mechanism illusion; no regression
    guard; no quality-debt trend).
  - +: A measurable insight engine (divergence-frequency ↓ across cycles) that is
    falsifiable — if it produces rationale-talk without behavioral effect, the
    metric exposes it and the mechanism is reverted.
  - −: Three new candidate conventions to pilot + track (intent-field,
    purpose-verification, divergence-ledger); deliberately scoped to one dispatch
    type first to avoid rationale-talk bloat.
  - −: Cycle-17 inherits a substantial deferred backlog (5 P0 findings + P1/P2
    catalog); ownership is pre-assigned in brief §11.1.
- **Alternatives considered:**
  - Incremental brief v1.1 instead of full re-author: rejected per user Q5.
  - Defer the advisory to cycle-17: rejected — it arrived pre-sign-off and is
    additive to the §4 marker discipline; folding now avoided a v2.1 churn.
  - Wholesale protocol restructuring per the advisory: rejected — the advisory
    itself prescribes incremental pilot-first; honored.
- **Tracking:** `c360952` (v2.0) + `110aff6` (advisory integration + operator
  REPLY-1 folds) + `7773502` (Rule #16) + `e86dd55` (convergence). Cycle-16 fix
  bundle: `0ecda24`…`669e5cd` (15 fixes). Q-V2-1 (Tier-C/D timing) user-confirmed
  2026-05-28: resumes under the insight frame, Phase-1 = pilot.
- **Cross-ref:** `docs/BRIEF-comprehensive-test-v2.0-2026-05-28.md` §2.6 + §8.6;
  `docs/CYCLE-16-CLOSING-REPORT-2026-05-27.md`; CLAUDE.md Rule #16;
  `docs/brief-2.0-advisory.md`.

---

## ADR-016 — GitNexus mandate was a phantom rule; removed in favor of grep/Read

- **Date:** 2026-05-28
- **Status:** Accepted
- **Context:** `CLAUDE.md` and `AGENTS.md` opened with a 101-line auto-generated
  block (`<!-- gitnexus:start -->`…`<!-- gitnexus:end -->`) mandating GitNexus
  MCP tools as the REQUIRED method for impact analysis, refactoring, and
  pre-commit scope checks ("MUST run `gitnexus_impact` before editing any
  symbol"; "NEVER edit a function … without first running `gitnexus_impact`").
  A user-prompted audit (operator proposal, 2026-05-28; ADR-013-compliant) found
  the mandate was never wired to reality; the director independently re-verified
  every claim at HEAD `7bded26`:
  - **0 GitNexus tool calls across 67 session transcripts** (calibrated against
    `"name":"Bash"` = 4482 in the same corpus).
  - **Never configured:** no `.mcp.json`, no `gitnexus` in `.claude/settings*.json`,
    not a dependency. The `gitnexus_*` tools were *absent* from every session's
    runtime, not merely "unreachable."
  - **Second phantom:** CLAUDE.md claimed "A PostToolUse hook handles [index
    refresh] automatically after git commit and git merge." No such hook exists
    (`grep -rl gitnexus .claude/hooks/` → empty).
  - The on-disk index proved it: `.gitnexus/meta.json` `lastCommit` = `eeea93f`,
    **251 commits behind HEAD**, 77 MB, never refreshed.
  - The block is **auto-injected by the `npx gitnexus` CLI itself** (the
    `gitnexus:start/end` markers), so the tool wrote its own "MUST use me"
    mandate into our protocol while its server was never set up.
  - **grep/Read carried all 67 sessions.** This is the §10 unwired-feature
    pattern in the protocol layer, caught by turning ADR-013 / Rule #12 inward.
- **Decision:** Remove the GitNexus integration; codify the de-facto method.
  1. Delete the auto-gen blocks from `CLAUDE.md` and `AGENTS.md` (markers
     inclusive) and stop running `npx gitnexus analyze` (the auto-refresh hook is
     phantom, so removal sticks — nothing regenerates the block).
  2. Delete the stale `.gitnexus/` index (gitignored — local cleanup) and the
     `.claude/skills/gitnexus/` skills (6 files; they only document dead tools).
  3. Replace the mandate with a hand-authored "Impact analysis before editing"
     note (grep callers + Read call sites + grep imports; report blast radius;
     `git show --stat` / `git diff` to confirm scope before commit).
  4. Rewrite every in-body dead-tool reference (implementer-prompt template,
     report-format, background-work bullet, failure-mode list) to the grep/Read
     method.
  5. **Excise the counter-bump sub-protocol.** "Counter-bump dispositions"
     existed solely to fold the auto-gen block's symbol/edge/flow count edits
     into commits. With the block gone and `analyze` stopped, counter-bumps can
     never occur again; the sub-protocol is now dead and is removed (role
     partition, the dedicated section, the phase-taxonomy "hold counter bumps"
     rows).
- **Consequences:**
  - +: No agent is instructed to use a non-existent tool and silently fall back;
    the protocol now matches 67 sessions of actual practice. Beneficiary: both
    seats + user (honesty).
  - +: One fewer sub-protocol (counter-bumps) and a large block of dead
    governance text removed across the two root files.
  - +: `mcp__server__tool` call-naming makes tool usage fully grep-auditable —
    periodic documented-vs-actual audits can catch this class of drift.
  - −: Lose the *option* of a real call-graph tool. If graph-based impact
    analysis is wanted later, it must be wired for real (`.mcp.json` + a genuine
    refresh hook + a fresh index) — see the rejected alternative.
- **Alternatives considered:**
  - **B — wire GitNexus for real** (configure the MCP server, refresh the
    251-commit-stale index, build the real auto-refresh hook): rejected for now —
    no evidence grep/Read missed a blast-radius in 67 sessions; bigger lift with
    no demonstrated need.
  - **C — rewrite the mandate text in place:** rejected as unstable — the block
    is CLI-auto-generated and regenerates on the next `analyze`, so C collapses
    into A unless `analyze` is also stopped (at which point A is the honest form).
- **Cross-ref:** operator proposal
  `coordination/mailbox/sent/2026-05-28T10-02-08Z-operator-to-director-proposal.md`;
  ADR-013 (verification discipline); CLAUDE.md Rule #12 (grep-the-writes).

---

## ADR-017 — Storyboard B-integrate: batched Kling generation behind a default-off flag

- **Date:** 2026-05-28
- **Status:** Accepted
- **Context:** Motion rendering generated one Kling take per shot, independently.
  "Storyboard mode" (brief item B-integrate / F-A.1) instead generates a whole
  scene's shots in a single batched `KlingNativeAPI.generate_storyboard` call —
  anchored on the first shot's keyframe, with the other shots' keyframes passed as
  `image_references` — for cross-shot character/style consistency, then splits the
  combined video back into per-shot segments. The hazard of a second render path
  is silent divergence from the proven per-shot path: cost double-counting,
  dropped shots on partial failure, cross-project output collisions, or broken
  lock discipline. The integration therefore had to be additive and reversible.
- **Decision:** Ship storyboard mode behind a default-OFF `storyboard_mode` flag
  (`cinema/phases/motion_render.py`), gated before the per-shot loop. Pipeline:
  1. Batch-generate via `generate_storyboard` (anchor = first keyframe; the rest as
     `image_references`).
  2. Record **exactly one** batch cost (`cost_tracker.record_api_call("KLING_NATIVE",
     operation="storyboard_generation")`) for the whole scene — this also closes
     Tier F NEW-2 (kling_native previously had no call-site cost tracking).
  3. `split_video_into_segments` on the combined output, by per-shot duration.
  4. `_finalize_motion_take(record_cost=False)` per segment — reuses the per-shot
     take machinery but suppresses cost (already recorded once at step 2).
  5. **Partial-finalize retry is per-shot and finite:** only a failed segment is
     retried via `generate_motion_take`; no loop.
  6. **Fall-through is safe:** None return / split raises / wrong segment count all
     return `batch_handled=False`, so the untouched per-shot loop runs. Flag off OR
     any batch failure ⇒ behavior identical to the legacy per-shot path.
  7. All project-state writes go through `_mutate_shot → mutate_project` (FileLock);
     no new bare mutations.
  - **Cost-on-split-failure policy (Lane V #19 F2b-1):** if `generate_storyboard`
    succeeds but the split then fails, the batch cost from step 2 is **retained**
    and the per-shot fallback records its own per-shot costs on top. This is
    intentional and accurate — the storyboard call genuinely ran and genuinely
    incurred Kling spend *before* the split, so recording it is not a leak; moving
    the record after the split-count check (the reviewer's first idea) would
    *under-count real money spent*. The retry path's per-shot costs are likewise
    real (separate generations). Accepted as correct billing, documented here per
    the operator's recommended disposition.
- **Consequences:**
  - +: Cross-shot consistency from one batched generation; fully reversible (flag
    off = legacy path); cost-accurate; no dropped shots on partial failure;
    lock-safe.
  - −: A second motion-render path to maintain. Storyboard *quality* is GPU-gated
    and unvalidated at ship time — the real Kling coherence plus 3 known tuning
    items (anchor = first-keyframe vs. others-as-references; split uses REQUESTED
    durations so the last segment absorbs drift vs. actual Kling output length;
    the batch motion prompt is thinner than per-shot) wait on the pod (tracked in
    the cycle-17 GPU-validation task).
  - −: On split failure the scene is billed for both the (real) batch call and the
    per-shot fallback — correct, but costlier than a clean per-shot run.
- **Alternatives considered:**
  - Generate batch + per-shot and keep the better: rejected — doubles cost with no
    automated quality signal yet.
  - Default storyboard mode ON: rejected — unvalidated on GPU; default-off is the
    safe additive ship.
  - Record the cost after the split-count check: rejected — under-counts real Kling
    spend when the split fails (see the policy above).
- **Tracking:** `51e6886` (F2a: split + reusable finalize helper, no behavior
  change) · `f9af2de` (F2b: wire batch mode behind the flag; closes F-A.1) ·
  `8354c9a` (F2b Lane V fix: partial-finalize retry-per-shot + per-shot classify) ·
  `ca9f090` (Lane V #19 F2b-2: project-scope the `/tmp` fallback path). Operator
  Lane V #19 verification-report
  `coordination/mailbox/sent/2026-05-28T10-24-58Z-operator-to-director-verification-report.md`
  (⚠️ minor, F2b sound, 0 blocking).
- **Cross-ref:** `cinema/phases/motion_render.py`; brief item B-integrate / F-A.1.

## ADR-018 — Dynamic Workflows adopted for read-analysis lanes; implementation stays subagent-driven

- **Date:** 2026-05-29
- **Status:** Accepted
- **Context:** Claude Code shipped "Dynamic Workflows" (`/workflows`, v2.1.154,
  2026-05-28) — background orchestration of tens–hundreds of agents that returns
  one synthesized report per run. Two doc lookups established the load-bearing
  mechanics: agents' intermediate results stay in script variables; there is **no**
  documented branch/PR/per-task-commit landing, no per-unit review gate, no custom
  agent types, and the edit-isolation/file-conflict mechanism is undocumented. So it
  is a **fan-out→synthesize-a-report engine, not a parallel-commit-with-review
  engine**. The question was where it fits the director-operator protocol's existing
  workflow layers without weakening the per-task-commit + two-stage-review + race-ack
  discipline.
- **Decision:** Adopt `/workflows` (Rule #17, Protocol Bundle v5.5) as the scaled
  execution engine for **read-only, report-producing analysis lanes** — Lane C/S,
  Rule #12 grep-the-writes, Rule #13 symmetric-endpoint audits, blast-radius/impact
  analysis, doc-truth sweeps — under five guardrails: (1) read-only/report-only, no
  implementation; (2) evidence captured + cited **+ the launching seat spot-checks a
  sample of citations post-run** (folds operator R-OP-1, extending CC-2 to
  workflow-synthesized reports; prefer calling `scripts/check_doc_claims.py` for
  anchor/symbol claims = un-hallucinatable by construction); (3) output re-enters the
  normal protocol (workflow agents emit no mailbox events; committed code → Lane V/D,
  Rule #9 independent review intact); (4) inspect-before-launch; (5) hard gate
  ≥ 2.1.154, read-only until edit-isolation is documented. **Implementation stays on
  `subagent-driven-development`.**
- **Consequences:**
  - +: Scales read-analysis disciplines the protocol already runs by hand (Lane C/S,
    Rule #12/#13 audits, impact analysis) without touching the implementation
    discipline; beneficiary=both; reversible (an opt-in engine for existing lanes).
  - −: Forward-looking — the feature is unavailable in the current runtime
    (2.1.74 / 2.1.149 < 2.1.154), so the rule ratifies a *shape* with no dogfood
    datapoint yet (first at v5.6 / C4 after env update).
  - −: Per-agent cost is not exposed (only run-total) — coarser than the protocol's
    context-hygiene instinct; noted, not blocking.
- **Alternatives considered:**
  - Use `/workflows` for parallel *implementation* (the original over-optimistic
    framing): rejected — no reviewable per-task commit, no per-unit Lane V gate,
    undocumented edit-isolation; would break the per-task-commit + two-stage-review
    discipline. Implementation stays subagent-driven.
  - Require citations in the report but no post-run spot-check: rejected via R-OP-1 —
    citations close the asserting half but not the fabrication half (CC-2 precedent).
  - Wait until the env updates to ≥ 2.1.154 before codifying: rejected — ratifying the
    shape now (with the hard gate) means the guardrails are agreed *before* first use,
    not improvised under it.
- **Tracking:** proposal
  `coordination/mailbox/sent/2026-05-29T01-19-08Z-director-to-operator-proposal.md`
  (director-originated, per user direction) · operator CONSENT + R-OP-1 `afb2c75`
  (`2026-05-29T01-26-32Z-operator-to-director-proposal-reply.md`) · Rule #17 codified
  at `52658eb` (Bundle v5.5).
- **Cross-ref:** CLAUDE.md Rule #17; Rules #9 (CC-2), #12, #13, #14, Lane C/S;
  ADR-013 (verification discipline). Composition note: `scripts/check_doc_claims.py`
  + `docs/pipeline_status.toml` (operator Increment-2) supply machine-verified
  evidence a doc-truth-sweep workflow should call.

## ADR-019 — Doc-maintenance run as a verifier-scoped dispatch pattern; persistence earned; scope bounded to the Guard-1 line

- **Date:** 2026-05-29
- **Status:** Accepted
- **Context:** Documentation drift (stale anchors, superseded refs, unpruned memory
  ~36.6k, doc-vs-code divergence) is a recurring cross-cutting cost split across both
  seats as a side-duty (operator's Lane D + ad-hoc). A three-way triangulation (advisor
  proposal + independent operator + director reads) considered adding a persistent
  doc-junior. Both seniors INDEPENDENTLY corrected the advisor's central justification:
  persistence-as-context-accumulation contradicts truth-in-files (ADR-013) — the doc
  ecosystem already lives in machine-checkable artifacts (the verifier, the manifest,
  gate-enforced conventions); the durable value is loop-ownership, not memory. Live
  exhibit during the cycle: the proposal's own provenance cited a closed F1 (`561ad6b`)
  as open — a prose/status claim the verifier-as-built can't catch, caught only by a
  senior (the 3rd Guard-1 exhibit this session, with the GitNexus phantom and a wrong
  Lane V #24 fix-rec).
- **Decision:** Adopt **Rule #18 (Bundle v5.6)** — doc-maintenance as a **verifier-scoped
  dispatch pattern**, NOT a standing junior on day one. Scope = the Guard-1 boundary = the
  carve-out boundary (one line): the role writes the **mechanical/verifier-confirmed slice**
  directly (anchor-fix, formatting, cross-ref, manifest, pruning); **prose/claim-changing
  edits → role prepares a diff, a senior verifies and lands it** (spawning seat owns the
  review). This bounds the carve-out of operator's Lane D — only the mechanical half moves;
  prose-truth sync stays a senior duty (operator's Rule #11 gating consent is to this
  bounded carve-out). Guards: (1) prose-truth leash + cite-or-don't-claim; (2) extended
  race-ack, NOT exclusive ownership (seniors keep inline fixes). Invest **C** — a **bridge**
  (role and verifier-buildout are partial substitutes; value declines as the verifier
  matures) with a **sunset review** at each verifier-buildout milestone. Graduation to a
  standing role requires ALL of: residual > ephemeral-sized (post-automation baseline),
  N≥3 dispatches re-discovering the same structure, prose-stays-true via R-OP-1 spot-check.
  Launch surface = line-anchors + manifest symbol-existence + mechanical only.
- **Consequences:**
  - +: Offloads a real recurring side-duty to a safe (verifier-checkable) executor; frees
    operator's Lane D mechanical half; composes with the verifier (un-hallucinatable
    evidence) and Rule #17; beneficiary both; reversible (a bridge, not a hire).
  - −: Forward-looking — no dogfood yet; the graduation metrics are the first data.
    Per-dispatch cost folds into session cost (not separately exposed).
  - −: May self-obsolete by design as the verifier-buildout proceeds — a feature of the
    honest framing, not a flaw.
- **Alternatives considered:**
  - Persistent doc-junior on day one (advisor's original): rejected — persistence-as-memory
    contradicts truth-in-files; persistence must be earned, not granted.
  - Extract ALL of Lane D to the role: rejected (operator's §B) — incoherent, since Lane D
    includes prose-truth sync the Guard-1 leash bars the role from owning.
  - Exclusive doc-ownership to the role: rejected — grants persistence's privileges before
    earned; seniors lose inline fixes. Extended race-ack instead.
  - Verifier-buildout only, no role (invest A): viable but leaves the partial-verifier
    residual unhandled now; the sequenced bridge (C) handles it while the verifier matures.
- **Tracking:** principal synthesis `PROPOSAL-doc-maintenance-role-v1.md` (user-mediated) ·
  operator REPLY `d385bb2` (bounded carve-out consent) · director REPLY `d5f3bb6` (consent +
  F1 provenance fix + spawning-seat reviewer) · Rule #18 codified at `4eecb72`.
- **Cross-ref:** CLAUDE.md Rule #18; Rules #9 (CC-2 / R-OP-1), #12, #13, #14, #17, Lane C/D/S;
  ADR-013 (verification discipline), ADR-016 (GitNexus phantom), ADR-018 (Rule #17).
  `scripts/check_doc_claims.py` + `docs/pipeline_status.toml` are the role's instruments.

## ADR-020 — Prune 5 confirmed-dead modules/symbols (327 LOC); keep dormant quality levers + preserved primitives

- **Date:** 2026-06-03
- **Status:** Accepted
- **Context:** The Test/Audit program (Part 2) flagged suspected dead code; the original
  max-tier director handoff §4a recommended a quality-neutral prune set. Before deletion, each
  candidate was re-grepped at HEAD incl. tests + dynamic/string refs (operator cold audit, per the
  `feedback_re-verify-before-destructive-commits` discipline). The user-principal approved pruning
  the confirmed-zero-reference set and keeping the nuance items; director independently re-verified
  0 production callers for every removed symbol before merge.
- **Decision:** Removed the confirmed-dead set, one `chore(prune)` commit each on
  `feat/max-tier-provisioning`:
  - `reporter.py` (52 LOC, true orphan per ARCHITECTURE §17) — `b4a03c8`
  - `generate_characters.py` (68 LOC, superseded by `character_manager.create_character_with_images`) — `e31d6a2`
  - `domain/dialogue_writer.py::{format_dialogue_for_voiceover, dialogue_to_narration_text}`
    (28 LOC, absorbed into `generate_dialogue_voiceover`) — `45c2299`
  - `domain/continuity_engine.py::{record_shot_generated, reset_scene}` (7 LOC, dead
    `last_generated_image` write path; `last_generated_image` itself retained — still live) — `6e8ce34`
  - `scripts/run_tier_c.py` (172 LOC, 0 importers; never a real unattended harness) — `8a5d425`
  - ARCHITECTURE.md doc-synced (dropped stale `record_shot_generated` + `reporter.py` refs) — `51f1826`.
    Total **327 LOC**.
- **Kept (explicitly NOT pruned):**
  - `cinema/pipeline.py::CinemaPipeline` — **reclassified from prune-candidate to KEEP.** Not dead
    code: ARCHITECTURE §4.8 documents it a "preserved primitive," §15.9 is a deliberate zero-callers
    GUARD invariant, and `cinema/phases/` references it as the future phase-scaffold orchestrator.
    Pruning it would delete a documented design artifact + a §15 truth-doc invariant.
  - `continuity_engine.validate_multi_identity` (multi-character Tier-D lever) and
    `auto_approve.summarize_audit` (tested) — user kept.
  - All dormant QUALITY levers (`negative_prompts.py`, `evaluate_generation_quality`,
    `validate_lora_quality`, ltx keyframe transitions) — pruning these trades against the program's
    full-capability intent (PROGRAM-MANUAL §5).
- **Consequences:**
  - +: −327 LOC maintenance surface; the dead-vs-dormant boundary is now recorded.
  - +: Zero behavior change — every removed symbol had 0 production callers (re-grepped at HEAD by
    operator's cold audit and director pre-merge); suite **1512/3/0 unchanged**, §15 smoke OK.
  - −: The `CinemaPipeline` keep means §15.9's zero-callers guard remains a (deliberate) maintenance item.
- **Cross-ref:** ARCHITECTURE.md §17 (dead code), §4.8 + §15.9 (CinemaPipeline preserved primitive),
  PROGRAM-MANUAL §5 (capability levers kept); precedent ADR-016 (GitNexus removal);
  `feedback_re-verify-before-destructive-commits`. Tracking: operator coordination
  `2026-06-03T09-11-52Z`; prune commits `b4a03c8`..`51f1826`.

---

## ADR-021 — Aspect backstop `_accept_or_reject` fails OPEN on probe failure

- **Date:** 2026-06-10
- **Status:** Accepted (records the in-force behavior shipped with the portrait
  backstop arc incl. the lip_sync fence `dd78208`; an explicit ADR was requested
  by the cycle-18 reassessment `wf_198f53fe-7aa` because fail-open on a gate
  looked accidental without a recorded rationale)
- **Context:** Portrait delivery added a post-generation orientation backstop —
  `_accept_or_reject` (phase_c_ffmpeg.py, used by the video cascade and the
  lip_sync FAL paths): probe the produced clip's real dimensions; wrong
  orientation → reject → cascade to the next provider. The probe itself
  (`probe_final_media` → ffprobe) can fail for environmental reasons: missing
  binary, truncated file, codec quirks. Decision point: on probe failure,
  accept the clip (fail-open) or reject it (fail-closed)?
- **Decision:** **Fail OPEN** — accept with a printed
  `[ASPECT-BACKSTOP] … accepting (probe unavailable)` warning when dimensions
  cannot be read. Layered-defense reasoning: the PRIMARY portrait defense is
  upstream (the `PORTRAIT_CAPABLE` filter, per-provider native 9:16 request
  args, and the pre-dispatch guard on the initial target); the backstop is a
  net for the residual case of a portrait-capable provider returning landscape
  anyway. A fail-closed backstop converts probe flakiness into SYSTEMATIC
  rejection — every provider's output rejected for the same environmental
  reason — cascade exhaustion, and the run dies on an environment issue, not a
  content issue. The worst case of fail-open is one wrong-orientation clip
  reaching operator review: visible, recoverable per-shot.
- **Consequences:**
  - +: Probe flakiness cannot strand a run; landscape byte-identity preserved
    (`is_portrait` False short-circuits before any probe).
  - −: When ffprobe is genuinely unavailable, orientation enforcement degrades
    to upstream-only; each occurrence is marked by the warning line.
  - −: Fail-open on a gate is an exception to the repo's general fail-fast
    posture. Scope-bounded HERE (environmental probe of orientation only) —
    NOT precedent for identity/quality gates, which gate on computed scores,
    not environment probes.
- **Cross-ref:** ARCHITECTURE.md §9 (video cascade + FAL timeout policy),
  §8.2/8.3 (portrait); `_accept_or_reject` docstring (caller contract);
  lip_sync orientation fence `dd78208`; pre-dispatch guard `46e3b87`.

---

## ADR-022 — Wire `would_exceed` as the pre-spend motion budget gate (not delete)

- **Date:** 2026-06-10
- **Status:** Accepted
- **Context:** STRATEGIC_REVIEW-2026-06-10 P0-2 found `would_exceed`
  documented-but-dead: the cost_tracker module docstring has promised "call
  `would_exceed(api_name)` before an API call" since the module was written,
  but only the post-fact `is_over_budget()` sibling (controller
  `_finalize_motion_take` step 9) was ever wired. The review required
  wire-or-delete — don't keep a documented-but-dead safety API. The same
  change fixed NF-2 (falsy `budget_usd` coerced to None at construction; 0
  is the project-settings sentinel for "unlimited", and default projects
  were pausing with BUDGET_EXCEEDED after their first motion cost record).
- **Decision:** Wire it. `generate_motion_take`
  (`cinema/shots/controller.py:1393`) now refuses to launch a generation
  when `would_exceed(target_api)` — emits BUDGET_EXCEEDED, sets the
  lifecycle pause flag, and returns a structured refusal
  (`error_kind: "budget"`) BEFORE any video API call. All PER-TAKE motion
  spend routes through this function (web endpoint, phase loop,
  regenerate, iterate, retry). *Amended same session, pre-push, per
  adversarial review `wf_4e0e2a6f` (the original entry overstated):* the
  F2b storyboard BATCH launch does NOT route through it — it is gated
  separately at the top of `_run_storyboard_scene`
  (`cinema/phases/motion_render.py`), refusing before `KlingNativeAPI` is
  constructed and falling through to the per-shot path; and the motion
  phase loop ABORTS on the structured refusal (`PhaseResult(ok=False)`)
  instead of marching through remaining shots. Note `lifecycle.pause()`
  only sets a flag — `check_pause()` has zero production call sites, so
  the loop abort, not the pause, is what actually stops the phase (wiring
  `check_pause` into phase loops is a named follow-up, NOT this change).
- **Consequences:**
  - +: The cap binds BEFORE money is spent — overshoot drops from one
    take's cost to ~zero; the documented API contract is honored instead of
    the capability being deleted.
  - −: `API_COST_USD` estimates are ±30%, so the gate can refuse a call
    that would not actually have exceeded (or admit one that does); a
    fallback-cascade winner can also cost several times the admitted
    primary estimate. It is a soft cap either way; the operator resumes
    after raising the budget.
  - −: Tests that mock `cost_tracker` must configure
    `would_exceed.return_value` — a bare MagicMock is truthy and fires the
    gate (two fixtures updated in this change).
- **Cross-ref:** docs/STRATEGIC_REVIEW-2026-06-10.md NF-2/P0-2;
  tests/unit/test_budget_pre_spend_gate.py; ADR-013 (evidence discipline).

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

---

## ADR-023 — Per-shot-class halt_rule defaults in MAX_QUALITY_TEMPLATES

- **Date:** 2026-06-11
- **Status:** Accepted
- **Context:** Operator Lane V (event 01:30:23Z) surfaced a latent gap riding
  the Pass-A landscape misclassification (`945d022`): NO MAX template carried
  `halt_rule`, so `quality_max.py` always fell back to `composite_only` —
  leaving every template's `halt_threshold_arc` (e.g. portrait/medium 0.83)
  DEAD as a halt criterion unless the per-project `max_halt_rule` UI knob was
  set. The `conjunctive` mode already existed in `face_validator_gate.should_halt`
  with the right semantics (identity floor at halt time; auto-satisfied for
  non-character shots/candidates without an arc score).
- **Decision:** Templates now declare halt_rule explicitly, per shot class:
  `portrait`/`medium` → `conjunctive` (faces dominate the frame; arc is a
  reliable halt gate); `action`/`wide`/`landscape` → `composite_only` (motion
  blur / distant faces / no identity stack make arc unreliable or absent).
  The `max_halt_rule` UI overlay still overrides per project. The
  `regenerate_floor_arc` PuLID-boost retry remains the post-hoc identity
  backstop for ALL classes, independent of halting.
- **Consequences:**
  - +: The arc thresholds the templates always carried now actually bind for
    the classes where they're meaningful; an early-halted portrait/medium
    best-of-N can no longer ship a low-identity winner purely on aesthetics.
  - −: Character shots that struggle on identity render more candidates
    before halting (bounded by the unconditional `halt_max_n` budget cap) —
    accepted as aligned with the tier's "ignore cost, max quality" charter.
- **Cross-ref:** tests/unit/test_max_quality_templates.py (pins);
  workflow_selector.py:143-375; face_validator_gate.py:234-296 (rule
  semantics); spec §S2/§6 record.

---

## ADR-024 — Production-tier identity GRAFT for realism + binding (reject tier-unification and post-pass toggling)

- **Date:** 2026-06-13
- **Status:** Accepted (architecture); empirical validation pending the first
  N=1 burn of the graft driver.
- **Context:** The realism goal needs ONE config that is both photorealistic
  AND holds two distinct character identities (aria + the man). Neither shipped
  tier delivers both, and the 2026-06-13 investigation closed off the easy
  hybrids:
  - **The over-cook is STRUCTURAL to the max base graph**, proven by three
    independent probes (all over-cooked): Design-D (max + dual PuLID + man-LoRA
    + SUPIR-on); Design-A (max + dual + no-LoRA + SUPIR-on); Design-E
    (`_max_passBe_quality_lora_pulid.py`, SUPIR-off **and** FaceDetailer-off).
    No post-pass toggle clears it ⇒ the "selectively disable post-passes"
    hybrid is **refuted by experiment**. Root cause (design workflow
    `wf_963a4a8a` Lens C, RANK 1): the max base's **hires-fix re-diffusion**
    (node 901 — a 2nd sampler pass @denoise 0.40 on a 1.5× upscaled latent) +
    the heavier OptimalStepsScheduler/28-step sampler. The fix is the SAMPLER
    CHAIN, not removing passes.
  - **The production graph (`pulid.json`) ships photoreal** because its sampler
    chain is clean: BasicScheduler + dpmpp_2m + sgm_uniform + 20 steps + PAG +
    RealESRGAN, with NO hires-fix / SUPIR / FaceDetailer.
  - **But production cannot bind identity as-shipped:** `pulid.json` has NO
    `LoraLoader` node, and its PuLID stack is the **SDXL-era** nodes
    (`PulidModelLoader` 99 / `ApplyPulid` 100 / `PulidEvaClipLoader` 101) on a
    FLUX UNet [CONFIRMED by direct JSON inspection + audit `wf_3b4ddaf1` Lens 1].
    `ApplyPulid` patches U-Net cross-attention layers FLUX's DiT lacks, so it
    applies ~zero face lock [HIGH-CONFIDENCE CODE INFERENCE, NOT yet
    pod-confirmed]. `workflow_selector.py:512` tunes params for that no-op node.
    See the DATA-INTEGRITY follow-up below.
  - **Full tier-unification is blocked** by node-ID class collisions across the
    two graphs (100 `ApplyPulid` vs `ApplyPulidFlux`; 17 scheduler class; 500/
    501/502 RealESRGAN vs SUPIR at the SAME IDs) + an `ays_steps` vs `steps`
    param-key mismatch (operator dialectic `wf_f353d3ad`, director concurrence).
- **Decision:** Build a **production-tier hybrid driver**
  (`scripts/_prod_dual_lora_pulid.py`, `build_prod_dual_lora`) that GRAFTS the
  proven identity stack onto the clean production sampler:
  - KEEP `pulid.json`'s sampler chain UNTOUCHED (the realism source).
  - GRAFT the max identity stack by deep-copying nodes 99/100/101/700 VERBATIM
    from `pulid_max.json` (node IDs are identical across graphs, so links
    resolve with no remapping): the FLUX PuLID loader trio
    (`PulidFluxModelLoader`/`PulidFluxEvaClipLoader`/`PulidInsightFaceLoader`),
    `ApplyPulidFlux` (100=aria), and `LoraLoader` (700, `char_lora_man_v1`@0.55).
    Splice a 2nd `ApplyPulidFlux` (103=man, `103.model=['100',0]`), prepend
    `TOKman`, route `122.clip→['700',1]` so the LoRA CLIP patch reaches the
    prompt, rewire PAG (301) to 103. Inherits the proven `start_at=0.0` (NOT the
    SDXL-era `start_at=0.3` that would miss the coarse-identity window).
  - **COLLISION-SAFE BY CONSTRUCTION:** the driver loads `pulid.json` directly +
    deep-copies the 4 identity nodes; it NEVER calls
    `quality_max._inject_post_passes` / `_prune_unavailable`, so the RealESRGAN
    500/501/502 chain is untouched (a max post-pass injection would write SUPIR
    params into the same node IDs and corrupt the prod save chain).
  - **Reject** both (a) full tier-unification and (b) the toggle-post-passes
    hybrid, per the Context findings.
- **Consequences:**
  - +: One config that should give realism (clean sampler) AND binding (grafted
    FLUX identity stack). $0 offline dry-build + an independent adversarial
    pre-burn audit (`wf_3b4ddaf1`, 4 lenses) both PASS: all 25 links resolve,
    correct slot indices, FLUX nodes replace SDXL, LoRA in the model path,
    over-cook nodes absent; verdict GO, 0 blockers.
  - +: Collision-safe; money-path = `render_leg` unchanged (operator-SAFE) +
    pure offline graph assembly guarded by 6 pre-submit asserts ⇒ malformed
    graph fails $0 before `/prompt`.
  - −: **Empirically unvalidated** — the identity stack bound man 0.870 on the
    MAX sampler; whether binding survives the lighter 20-step production sampler
    is an open empirical question the first N=1 burn resolves. GO read: arc man
    LEFT ≥~0.75 + VISUAL photoreal (primary) + two distinct faces.
  - −: It is a **separate experiment-tier driver** (`scripts/_*`), NOT folded
    into the shipping production tier (`phase_c_assembly`/`workflow_selector`).
    Productionizing it is future work.
  - −: **Placement** (man renders LEFT, aria RIGHT — not the intended slots)
    remains an open COMPOSITION axis; masking was proven placement-inert for a
    bound identity (`48ad08b`), so the levers are prompt-order / seed /
    PuLID-node-swap, re-measured on a clean render.
  - −: **DATA-INTEGRITY follow-up (carried, separate thread):** the shipping
    production path renders `COMFYUI_PULID` portraits through the SDXL-on-FLUX
    no-op PuLID. If the functional no-op is pod-confirmed, production-default
    portraits carry little/no reference-face identity — a real latent defect to
    fix (upgrade `pulid.json` 99/100/101 to FLUX-native + adjust
    `workflow_selector` PuLID params). Needs empirical confirmation FIRST.
- **Cross-ref:** scripts/_prod_dual_lora_pulid.py (the graft);
  pulid.json / pulid_max.json (the two tiers); quality_max.py:237
  (`_inject_post_passes` rewire — deliberately NOT called);
  workflow_selector.py:512 (production PuLID param tuning, no-op target);
  phase_c_assembly.py:204,413 (shipping production render path);
  docs/HANDOFF-director-transplant-2026-06-13-overcook-structural-prod-hybrid-driver-built.md.

## ADR-025 — Production PuLID SDXL→FLUX correctness fix (shipping default; Task-4 pod-validated)

- **Date:** 2026-06-13
- **Status:** Accepted + **VALIDATED** — shipping production default (push USER-gated).
  (Distinct from ADR-024, whose dual-identity GRAFT experiment remains empirically
  pending its own N=1 burn — that status is unchanged.)
- **Context:** The default production image tier renders portraits via the ComfyUI
  graph `pulid.json` on a FLUX UNet (node 112 = `flux1-dev-fp8.safetensors`). It
  shipped with the **SDXL-era** PuLID node set — `PulidModelLoader` (99) /
  `ApplyPulid` (100) / `PulidEvaClipLoader` (101) loading
  `ip-adapter_pulid_sdxl_fp16.safetensors`. `ApplyPulid` patches U-Net
  cross-attention layers that FLUX's DiT architecture lacks, so it applied **~zero
  face lock** — a structural no-op. Production-default `COMFYUI_PULID` portraits
  therefore carried little/no reference-face identity, while cost/provenance were
  tagged as if PuLID ran. This was the **DATA-INTEGRITY follow-up carried in ADR-024**
  (its Consequences bullet, "Needs empirical confirmation FIRST"). The bug was
  **test-dark** — no test asserted the node classes, so it shipped silently.
- **Decision:** Correct the single production PuLID to the FLUX-native node set, with
  no other behavior change (LoRA / dual-identity stay out — that is the separate
  ADR-024 experiment track):
  - `pulid.json` nodes 99/100/101 → `PulidFluxModelLoader` / `ApplyPulidFlux` /
    `PulidFluxEvaClipLoader` (`pulid_flux_v0.9.1.safetensors`). Node 100 wired
    `pulid_flux`/`fusion`/`use_gray`, `start_at=0.0`, `model=["112",0]` direct from the
    UNETLoader (no LoRA node 700).
  - `workflow_selector.WORKFLOW_TEMPLATES` `pulid_start_at` → `0.0` for
    portrait/medium/wide/action (**the crux:** `apply_workflow_params` writes
    `start_at` onto node 100 at runtime; the SDXL-era 0.2–0.35 would overwrite the
    graph's new 0.0 every render and re-suppress the coarse-identity window, making the
    node swap net-zero). Landscape stays `pulid_weight=0.0` (PuLID off).
  - Regression test `tests/unit/test_pulid_production_flux.py` pins the FLUX node
    classes + `start_at=0.0` (closes the test-dark gap).
  - **Commits:** `a1103bd` (graph) / `f05c83b` (templates + docstring) / `c5199de`
    (test) / `a924055` (case-landmine `Pulid.json`→`pulid.json` git mv + case-pin
    test) / `7b54af9` (advisory folds).
- **Validation — Task-4 pod acceptance gate (R-MEASURE):** instrument
  `scripts/_prod_pulid_acceptance.py` (`a43358f`); artifact
  `logs/prod_pulid_acceptance_20260613.json` (logs/ gitignored, reproducible). A/B on
  a fixed reference + seed 990011: **PuLID-OFF arc 0.6205 → PuLID-ON arc 0.8779
  (+0.257)**, peak VRAM 18.2 GiB. All four Step-4 GO criteria met: material lift ✓;
  **FaceDetailer-free binding** (figure read, no NO_FACE) ✓; **fp8 compatibility** —
  node 112 `flux1-dev-fp8` bound to 0.8779, retiring the fp8-vs-fp16 escalation ✓;
  **visually photoreal** (both renders viewed) ✓. Operator-run (user-directed),
  director Step-5 GO call.
- **Independent verification (operator report `77eb334`, Sonnet find→adversarial-refute,
  $0):** the determinism siblings routed in PM4 (`970015b`/`099a1ea`) =
  CONFIRMED-SOLID + complete set (5 production DeepFace sites guarded, zero unrouted,
  not test-dark, 5/5 spy tests pass); the SDXL-on-FLUX no-op equivalence + the
  scope-exemption claim (below) HELD under adversarial attack.
- **Consequences:**
  - +: Production-default portraits now carry genuine reference-face identity on the
    shipping fp8 graph. The fix **is** the shipping default.
  - +: **Resolves ADR-024's carried DATA-INTEGRITY follow-up** — the no-op is
    pod-confirmed (the OFF baseline = no lock) and fixed. ADR-024's *main* decision
    (the dual-identity GRAFT driver `scripts/_prod_dual_lora_pulid.py`) is untouched
    and **still pending its own N=1 burn**.
  - − **SCOPE EXEMPTION (director2 Rule #23 + operator severity correction).** The
    Task-4 gate validated PuLID-*engaged* shot-classes. It did **not** cover
    char-bearing-**landscape** shots: `classify_shot_type` mis-routes them to
    `landscape`, and — corrected by the operator — the production tier does not merely
    write `pulid_weight=0.0`; it **early-returns at `phase_c_assembly.py:224`** to
    `_fal_flux_fallback(..., character_image=None, ...)`, skipping ComfyUI and
    **dropping the character reference entirely** → pure text2img, zero identity
    (strictly *worse* than weight 0.0). This is **orthogonal** to this fix (it decides
    *whether* identity engages, not *whether PuLID binds when it runs* — confirmed by
    the operator). It is a **separate routing/fallback bug**, `fix_with_brief` + joint
    director+director2 sign-off, targeting `phase_c_assembly.py:224` +
    `classify_shot_type` + an **untraced MAX-tier sibling** (`quality_max.py` landscape
    template, also `pulid_weight=0.0`). **NOT** landing in this change.
    - − **RESOLVED 2026-06-13 (`cf32ca3`, operator2 impl; director2 verifies):** the scope
      exemption is now **closed**. `classify_shot_type` routes a char-bearing landscape to
      `wide` (3-site fix: seam + `phase_c_ffmpeg:416` LTX-4K + `:375` guarded-broaden Veo
      audio), re-engaging PuLID at `pulid_weight=0.65` in both tiers and preserving the
      production reference (the `phase_c_assembly:224` early-return no longer fires). Joint
      Rule #23 brief `27d1323` + Pair-A co-sign `ef5c4c6`; ARCHITECTURE.md §8.5 marked FIXED.
      **Still owed (pod-gated debt, not a blocker):** a char-aerial binding re-validation on
      the Linux/TBB pod (pod STOPPED; R-MEASURE — no binding number asserted unmeasured).
  - −: Historical `COMFYUI_PULID` renders logged **before** this fix carried ~zero
    identity (provenance caveat for old takes).
  - −: Residual — the macOS-pinned binding numbers owe a Linux/TBB pod-portability
    re-confirm (the existing portability gate); not a blocker for this single-PuLID GO.
- **Cross-refs:** `pulid.json`; `workflow_selector.py:21-109,506-542`;
  `tests/unit/test_pulid_production_flux.py`; `phase_c_assembly.py:224` (the exemption
  seam); `docs/superpowers/specs/2026-06-13-production-pulid-flux-fix-design.md` +
  `docs/superpowers/plans/2026-06-13-production-pulid-flux-fix.md`;
  `logs/prod_pulid_acceptance_20260613.json`; ADR-024 (DATA-INTEGRITY follow-up
  resolved here); operator verification-report `77eb334`.

## ADR-026 — A non-finite budget cap fails SAFE (blocks spend), it is not "unlimited"

- **Date:** 2026-06-14
- **Status:** Accepted — user-endorsed (Session-8, program-hardening Wave-1 Task 6
  `budget-nan`). Shipping default; FIX push USER-gated.
- **Context:** `CostTracker(budget_usd=N)` is the program's spend gate. The storage
  idiom `self.budget_usd = budget_usd if budget_usd else None` (cost_tracker.py)
  encodes a deliberate fail-safe philosophy: falsy (`0` / `0.0` / `None`) = NO cap
  (the project-settings "unlimited" sentinel, NF-2), while **negative caps are KEPT
  on purpose because they block all spend** (`spent > -1` is always True). A
  **non-finite** budget defeated this: `bool(NaN) is True` so a NaN was KEPT, but
  `would_exceed`/`is_over_budget` compare against it (`(spent+cost) > NaN`,
  `spent > NaN`) and **every comparison against NaN is False** — so a NaN cap
  **silently disabled all spend enforcement for the whole session while
  `budget_usd is not None` masqueraded as a set cap** (money-loss; the reason the row
  was reclassified MAJOR→CRITICAL). `+inf` is the same shape (reads as limitless).
  `float(NaN)`/`float("inf")` succeed, so the upstream `try/except` at `cinema/core.py:101`
  does not catch it. The open design question was: a NaN cap → (a) fail-safe BLOCK, or
  (b) coerce to `None` = unlimited? These diverge, so it was surfaced, not silently decided.
- **Decision:** **(a) fail-safe BLOCK.** A non-finite (NaN/inf) or non-coercible budget
  cap is **data corruption, not a deliberate "unlimited"** — silently allowing unbounded
  spend on a corrupt value is exactly the money-loss this gate exists to prevent, and it
  contradicts the kept-negatives-block philosophy already in the code. Implementation
  **maps corruption onto that existing block mechanism** at the **single storage
  chokepoint** `cost_tracker.py` (`CostTracker.__init__`, the SOLE write site for
  `self.budget_usd` — all construction paths funnel through it): a local guard
  `_finite_budget_or_block(value)` coerces a non-finite/non-coercible cap to a blocking
  sentinel (`-1.0`) so the gate fires. `None`/`0`/`0.0` still mean no cap; finite values
  (incl. negatives) are unchanged.
- **Scope (pure Pair-B lane, not cross-cutting):** the inventory anchored the row at
  `cinema/core.py:101` (the upstream read), but impact analysis showed the fix belongs at
  the `cost_tracker.py` storage chokepoint — a `core.py` guard would be **redundant, not
  defense-in-depth** (it covers nothing the chokepoint misses and would duplicate the
  sentinel logic across two files). So the fix touches **no cross-cutting module**
  (`W1-core.py.lock`/Tier-A co-sign do not fire). A **complementary** sibling — a NaN
  `budget_limit_usd` read **directly** at `auto_approve.py:586` (`_shot_over_budget`,
  the per-shot veto, a path the `cost_tracker` chokepoint never reaches) — is closed
  **fail-closed in Pair-A's `aa-budget-nan-veto` fix** (director2 Tier-A co-sign,
  10:35:37Z), so the NaN-budget class is closed across both gate paths.
- **Local guard, not an `import cinema.context._finite_or`:** the import is circular-safe
  (verified — `cinema.lifecycle` is a leaf), but `cost_tracker.py` is a low-level root
  util and importing the larger `cinema.context` inverts the layering + drags its dep
  tree into a foundational module; a small local guard is the lower-blast-radius choice,
  consistent with the documented-temporary local-copy precedent at `quality_max:191`.
  Consolidation onto `_finite_or` is deferred to the dedicated import-swap pass.
- **Consequences:**
  - +: A corrupt budget cap now **blocks** spend (fail-safe) instead of silently allowing
    unbounded spend — the money-loss CRITICAL is closed at the chokepoint that covers
    every CostTracker construction path (direct, `core.py:113`, Task-7 fresh instances).
  - +: The bare pin (`test_budget_nan_gate_xfail.py`, "not stored as NaN") was
    fix-agnostic (it would have passed a policy-VIOLATING None=unlimited coercion); it is
    now a live regression that asserts the **block behavior** (NaN/inf → `would_exceed`
    + `is_over_budget` True), locking in this policy.
  - −: A corrupt cap renders as `$-1.00` in the controller "Pausing" message
    (`controller.py:1506/1660`) — cosmetically odd, but that message fires **only when
    the gate trips**, i.e. the fail-safe block working (vs. today's silent unlimited).
    Corruption-only path; acceptable.
- **Cross-refs:** `cost_tracker.py` (`_finite_budget_or_block` + `__init__` chokepoint);
  `tests/unit/test_budget_nan_gate_xfail.py` (pin → live regression); `cinema/core.py:99-104`
  (upstream read, unchanged); `cinema/auto_approve.py:586` (complementary sibling, Pair-A);
  `docs/superpowers/plans/2026-06-14-program-hardening-wave1.md` (Task 6);
  `docs/REMEDIATION-INVENTORY.md` (`budget-nan` row); director2 scope-surface 10:28:08Z +
  Tier-A co-sign 10:35:37Z. Origin: director2's §4 verify (`a812ee4`, `wf_99bc3ff7-fe4`).

## ADR-027 — Wave verification must EXECUTE the oracle, not READ the attestation (closing the gate-circularity)

- **Status:** Diagnosis ADOPTED; coordinator-doctrine prevention ADOPTED (seat-coordinator
  skill). FIX-1/FIX-2/FIX-4/FIX-5 are implemented in the gate/tooling surface
  (`scripts/wave_gate_check.py`, `scripts/pin_reconciler.py`, `.github/workflows/ci.yml`,
  `scripts/ci_smoke.py`, `.gitignore`). Product-oracle wave-close is gate-enforced
  for Wave 2+ by requiring a committed `logs/product-oracle-*.json` artifact with
  finite ArcFace and lip-sync measurements for the requested wave. Evidence:
  `logs/discovery-wf_26a5abf2-3bb.json` (read-only RCA, 8 agents,
  adversarially stressed; verdict "partially-just-so").
  Implementation evidence (director2 local, 2026-06-15): `env -u GIT_INDEX_FILE
  .venv/bin/python scripts/check_no_ceremony.py` -> exit 0, R3/R4 PASS;
  `env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 1` -> exit 1,
  `counts={'verified': 8}`, pytest exit 1 from broad selectors pulling open pins;
  `env -u GIT_INDEX_FILE .venv/bin/python scripts/pin_reconciler.py` -> exit 0,
  verified rows=13, issues=2 (`costtracker-perf-uncounted`, `ws-reorder-deletes`).
- **Context (the failure mode, user-principal critique 2026-06-15 — "an elaborate machine
  for feeling confident"):** investigation confirmed the mechanism AND corrected its overreach.
  - `wave_gate_check.py` derives "GATE MET" by reading the inventory `status` string — it
    executes zero tests (verified: 2-commit history, no subprocess). The strict-xfail pins
    (the behavioral oracle) were designed as a SEPARATE CI tripwire, but **only the gate
    script is automated**; the operator-GO / xfail-green / `ci_smoke` conditions are socially
    enforced. Net: "GATE MET" carries the rhetorical weight of "tests pass" while
    mechanically meaning "the coordinator wrote `verified` (after an operator GO that did run
    pytest)."
  - "verified" was redefined DOWN (behavioral-fixed → unit-pin-flips → status-cell) — e.g.
    `shot-spent-usd-never-written` is `verified` while its own pin cell reads "gate-loop
    integration test-infeasible."
  - ~20–25% of production gates are external-oracle; **6 product dimensions** (realism,
    coherence, motion, audio, prompt adherence, narrative) have ZERO reachable oracle; 2
    vision oracles are dead code; cloud-prod identity degrades to the `idgate-failopen`
    fail-open. 98% of campaign commits are structural; ~2:1 coordination:implementation.
  - **Corrections (adversarial stress):** the "structural" fixes DID fix real defects (the
    narrow valid claim is: *no commit improved a user-observable output-quality dimension*);
    the product deferral was USER-authorization/pod-gated resource asymmetry, not campaign
    displacement (and product work runs off-git); the loop has a real operator-GO evidential
    chain (no CODE enforces it, but it is not "from nothing"); `face_validator` does not
    itself fall back to Claude-Vision.
- **Decision:**
  1. **"Done" is mechanically-checkable, oracle-backed — not status-string-backed.** A wave
     is MET when the gate EXECUTES the wave's pins (`pytest --runxfail`, XPASS-clean), not
     when a status column reads "verified" (FIX-1; director — changes gate PASS/FAIL).
  2. **"verified" stays tied to a live test** via a committed `pin_reconciler.py` (re-runs
     verified-row pins, flags regressions), CI-wired (FIX-4/FIX-2; director).
  3. **≥1 committed product-oracle artifact** (`logs/` ArcFace arc + lipsync offset baseline)
     is a HARD wave-close blocker from Wave-2 (already a spec §7 exit deliverable; not yet
     gate-enforced) (FIX-5; user-policy + director; depends on FIX-1).
  4. **Rows with no behavioral oracle are `attested`, not `verified`**, and need an explicit
     user-principal exemption to pass a gate (inventory vocabulary; coordinator-doc).
  5. **Anti-rhetoric (coordinator doctrine, ADOPTED now):** milestone language states what was
     mechanically checked; a status-tally "GATE MET" is not cited as evidence of correctness.
- **Consequences:**
  - +: after FIX-1 a coordinator writing "verified" produces zero gate effect; the verdict
    comes from execution. The status-tally can no longer be laundered into a correctness claim.
  - +: `pin_reconciler` closes the "verified survives a silent regression" hole (11 verified
    rows currently have no continuous check). A product oracle becomes mandatory at wave-close.
  - −: **FIX-1 will likely flip the current "Wave-1 MET 8/8" → UNMET** for any test-infeasible
    or non-XPASS-clean row — an honest re-grade, but a real, visible regression in reported
    state. MUST be surfaced to the user before FIX-1 lands.
  - −: two gaps remain UNCLOSED (recorded so they are not forgotten): (a) operator-GO
    impl≠verifier (Rule #9) is still not gate-enforced; (b) unregistered defects (e.g. the
    `coherence-silent` caller-side MAJOR half) cannot be caught by a gate that reads only
    registered rows.
  - −: FIX-7 (nightly oracle on committed fixtures) is DEFERRED until the `_ARC_AVAILABLE=False`
    CI-vacuity is fixed — wiring it first would be a vacuous green (the silent-gate bug it is
    meant to prevent).
- **Cross-refs:** `logs/discovery-wf_26a5abf2-3bb.json`; `scripts/wave_gate_check.py` (FIX-1/FIX-5);
  `scripts/pin_reconciler.py` (FIX-4); `.github/workflows/ci.yml` + `scripts/ci_smoke.py`
  (FIX-2/ADR-028 hard wiring); `face_validator_gate.py` + `performance/identity_gate.py`
  (the real product oracles); `docs/superpowers/specs/2026-06-14-program-hardening-roadmap-design.md`
  §5/§7 (acceptance bar + the spec↔implementation gap); `docs/REMEDIATION-INVENTORY.md`.
  Origin: user-principal critique 2026-06-15 → coordinator Session-12 RCA `wf_26a5abf2-3bb`.
  Product-oracle gate enforcement landed via
  `docs/superpowers/briefs/2026-06-15-product-oracle-wave-gate.md`.

## ADR-028 — Ceremony is forbidden from the verification core, and a detector enforces it

- **Status:** ACCEPTED (coordinator Session-13, 2026-06-15). Direct user-principal directive:
  "check thoroughly for ceremony of any kind and forbid it from the core." Extends ADR-027.
- **Definition — "ceremony":** anything that produces the APPEARANCE of verification,
  enforcement, or assurance WITHOUT the substance — a relied-on green/PASS/`verified`/score/
  verdict that is NOT backed by actually executing the check it claims to perform. ADR-027's
  gate-circularity is the archetype; the family also includes vacuous/soft xfail pins,
  fail-open gates, dead oracles, and doc verdicts asserted without cited evidence.
- **Context — the S13 ceremony hunt** (`logs/discovery-wf_73983b84-d46.json`, read-only 5-lens
  fan-out + adversarial verify; 42 deduped → 33 confirmed / 9 refuted): every CRITICAL ceremony
  was already-tracked (the status-read gate, `idgate-failopen`, `llmensemble-cost-uncounted`,
  `charmgr-cost-fresh-instance`). The NEW yield is **meta-ceremony** — the verification
  apparatus itself does not execute: `wave_gate_check.py` reads the `status` column (R3) and CI
  never runs `--runxfail` (R4, `.github/workflows/ci.yml:124`), so the 70+ strict-xfail pins are
  never run as a gate; and ≥3 individual pins are vacuous/mis-shaped (`secondary-lora` passes on
  REVERTED production code; `ckpt-sceneidx` can never xpass; `lipsync-postproc-costkey` +
  `idgate-observability` pin only the wrong half).
- **Decision:**
  1. **Ceremony is forbidden from the verification + enforcement core.** Doctrine prose alone is
     insufficient — ADR-027 proved ceremony lived in the gate DESPITE the rules. Enforcement is
     therefore **mechanical**: `scripts/check_no_ceremony.py` (committed S13) hard-fails (exit 1)
     on detectable ceremony — R1 xfail-strictness (`strict=True`+`reason=`, AST), R2 invisible-
     green (importorskip/skip in pin files that would silently skip), R3 gate-executes-pins, R4
     ci-runs-`--runxfail`. It only ADDS signal; it never relaxes a gate or suppresses a defect.
  2. **Sequencing (so enforcement is not itself ceremony, and does not red-light peers mid-wave):**
     the detector started as a standalone gate that hard-failed R3/R4 honestly. ADR-027
     **FIX-1** now makes R3 pass (gate executes the pins); **FIX-2** now makes R4 pass
     (CI runs `--runxfail`). `ci_smoke.py` and CI invoke `check_no_ceremony.py` as a
     HARD gate so it cannot be skipped.
  3. **Pin vacuity is only partly mechanizable.** `--runxfail` in CI (FIX-2) catches XPASS (a
     landed fix that should have flipped a pin), but it does NOT catch a pin that passes on
     reverted/broken code (the `secondary-lora` failure mode). That requires the per-pin operator
     mutation-RED discipline (Rule #9) and stays a lane responsibility; the detector cannot
     replace it.
- **Consequences:**
  - +: new ceremony (a soft xfail, an invisible-green skip, a status-only gate, a CI without
    `--runxfail`) cannot land silently — the detector goes red.
  - +: the detector is green on hard rules after FIX-1/FIX-2 (R1 strictness passes; R2 remains a
    warning for latent invisible-green risks), so it is respected, not ignored.
  - −: R3/R4 were red before FIX-1/FIX-2. They are now wired into `ci_smoke.py` and CI, but
    the executable wave gates are honestly red while broad selectors/open pins remain.
  - −: vacuity detection is incomplete (see decision 3); ≥3 existing vacuous pins are routed to
    lanes to re-shape, NOT fixed by this ADR.
- **Routing:** FIX-1 + FIX-2 → Pair-B director (implemented in gate/CI tooling; operator2
  verification still owed). Vacuous-pin re-shape (`secondary-lora`, `ckpt-sceneidx`,
  `lipsync-postproc-costkey`, `idgate-observability`) → owning lanes. New row
  `coherence-caller-valid-ignored` filed in the inventory. **User ratification of the
  hard-wiring policy RATIFIED (user-principal, 2026-06-15): ci_smoke + CI now run
  `check_no_ceremony.py` as a HARD gate.**
- **Cross-refs:** `scripts/check_no_ceremony.py`; `logs/discovery-wf_73983b84-d46.json`;
  ADR-027 (FIX-1/FIX-2); `docs/REMEDIATION-INVENTORY.md`. Origin: user-principal directive
  2026-06-15 → coordinator Session-13 ceremony hunt.

## ADR-029 — Identity vision fallback fails closed when the oracle cannot run

- **Status:** ACCEPTED (director-1, 2026-06-15; director2 Tier-A co-sign GO at
  `d832850`; operator-1 Lane V verification owed).
- **Decision:** `validate_identity_vision` no longer fabricates a passing
  `confidence=0.7` when Anthropic config is missing, image encoding fails, or the provider
  call fails. Those cases now return an explicit `error=True` marker with
  `confidence=0.0`; `IdentityValidator` maps that marker to an `identity_unverified`
  non-pass for both image and video vision-fallback paths.
- **Rationale:** when DeepFace is unavailable, the vision fallback is the production identity
  oracle. Treating an unavailable oracle as a passing score is ceremony: it makes the gate
  look executed while allowing the wrong identity to pass.
- **Evidence:** `rg -n "missing ANTHROPIC_API_KEY" phase_c_vision.py` -> lines 274/277;
  `rg -n "image encode failed" phase_c_vision.py` -> lines 295/302;
  `rg -n "failing closed" phase_c_vision.py` -> line 388;
  `rg -n "if result.get(\"error\")" identity/validator.py` -> lines 1404/1533.
  Focused verification:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_phase_c_vision.py tests/unit/test_identity_validator.py tests/unit/test_identity_types.py tests/unit/test_negative_prompts.py tests/unit/test_lane_silent_gate_siblings_xfail.py -q`
  -> `205 passed, 2 xfailed in 2.74s`.
- **Cross-refs:** `docs/superpowers/briefs/2026-06-15-idgate-failopen.md`;
  `docs/REMEDIATION-INVENTORY.md` row `idgate-failopen`; ADR-028.

## ADR-030 — Cross-provider seat topology Slice 1: signed-JSON event store, single-writer, gate-recomputed merge to a TEST ref

- **Status:** ACCEPTED (Slice 1 implemented on branch `threeway-slice1`; spec §11 Slice 1
  gate MET — adversarial suite green). Slice 2 (ref-topology) and Slice 3 (strategic loop +
  T2/T3 co-sign) deferred.
- **Context:** the spec
  (`docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md`) and plan
  (`docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice1.md`) define a
  cross-provider seat topology where a builder (one provider) and its primary verifier
  (a different provider) cannot collude, enforced by a mechanical merge-gate over signed
  facts. Slice 1 proves the gate end-to-end at the smallest honest scope: one pair,
  single-writer, promoting to a protected TEST ref.
- **Decisions:**
  1. **Separate signed-JSON event store, NOT the markdown bus (§6.2).** Slice 1 runs on its
     own append-only store under `coordination/threeway/` (`threeway.store.EventStore`), with
     a private kind vocabulary (`threeway.__init__.THREEWAY_KINDS`) distinct from the markdown
     bus's `coordination/mailbox/kinds.txt`. The existing "four files to keep in sync" coupling
     of the markdown coordination layer is therefore UNTOUCHED — the new topology does not
     widen it.
  2. **Single-writer monotonic `seq` for Slice 1; append-CAS ref topology deferred to Slice 2
     (§8).** The store assigns `seq = max(existing) + 1` and names files `<seq:08d>-<id>.json`
     so lexical order is seq order. The multi-writer hardening (one git commit per event on
     `refs/threeway/events` + index ref + expected-old-OID append-CAS push loop) is Slice 2;
     the public read/iter API is intended to stay stable across that swap.
  3. **Ed25519 (`cryptography`) public-key signatures + RFC 8785 JCS canonicalization for the
     signed byte image (§6.2).** Public keys are the committed trust root
     (`coordination/threeway/keys/<seat>.pub`); private keys live OUTSIDE the repo in a
     keystore (`THREEWAY_KEYSTORE`). Public-key (not HMAC) signing is mandatory so the
     signature *verifier* — the merge-gate — cannot forge a *signer*. The signature binds a
     fixed 12-field subset (`envelope._signed_view`) over canonical bytes, so a timed-out retry
     of the same logical fact re-signs to identical bytes.
  4. **`co_sign_satisfied` returns `False` for T2/T3 (deferred to Slice 3).** Slice 1 implements
     the T0/T1 co-sign clauses only; for an escalated effective tier the predicate's co-sign
     clause is unsatisfiable, so an escalated change SAFELY cannot promote yet (returning
     `False` is fail-safe, not fail-open). T2 (other-pair operator co_sign) and T3 (new-session
     re_verify + two human_approval) land in Slice 3, which needs Pair B / the human relay.
  5. **The gate recomputes the merge and CAS-writes a protected TEST ref, never executing
     candidate code (§6.3/§6.4).** On MERGEABLE the gate RECOMPUTES the trusted merge from the
     signed `staging_base_sha`/`branch_sha` (never trusting the candidate's `integration_sha`),
     requires the recompute to equal the attested `integration_sha`, then does an exact-SHA
     compare-and-swap on `refs/threeway/test-main` (write only if the ref still equals
     `staging_base`). At-most-once is doubly guaranteed (idempotency check + CAS expected-old).
     `threeway.gitcas` never checks out a working tree, never reads candidate workflow files,
     never runs candidate code — it is object-store plumbing only.
- **Evidence:** rework circuit-breaker (`feat(threeway): ≤2 rework circuit-breaker (§9)`) +
  the spec §11 adversarial gate suite (`tests/unit/test_threeway_gate_adversarial.py`, 12
  scenarios: clean-merge COMPLETED + 10 single-fact mutations that must NOT advance the ref +
  crash-recovery idempotency).
  Full focused verification:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q`
  -> `93 passed`. `scripts/ci_smoke.py` -> OK (no ceremony detected).
- **Cross-refs:** spec
  `docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md` §11/§6.2/§6.3/§6.4/§8/§9;
  plan `docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice1.md`;
  `threeway/` package (`__init__`, `canon`, `keys`, `envelope`, `store`, `reducer`, `policy`,
  `tier`, `gitcas`, `predicate`, `gate`, `loop`, `rework`, `keys_bootstrap`).

## ADR-031 — Cross-provider seat topology Slice 2: `refs/threeway/events` one-commit-per-event bus, dual-mode CAS append, verifying idempotency, validated per-seat cursors

- **Status:** ACCEPTED (Slice 2 implemented on branch `feat/threeway-slice2-exec`; spec §8/§13
  Slice 2 scope — multi-writer ref topology + Pair B + two-pair concurrency). Builds directly
  on **ADR-030** (Slice 1), which deferred the ref-topology and Pair B to this slice. The two
  design questions D-A (`brief_version` signed) and D-B (legacy mailbox migration deferred)
  were **user-APPROVED 2026-06-19**. Slice 3 (strategic loop + T2/T3 co-sign for an escalated
  effective tier) remains deferred per ADR-030.
- **Context:** ADR-030 §2 promised the multi-writer hardening — "one git commit per event on
  `refs/threeway/events` + index ref + expected-old-OID append-CAS push loop" — behind a stable
  read/iter API. Slice 2 delivers that, plus Pair B (a second builder/verifier pair) and the
  two-pair concurrency the gate must survive. The slice was **externally audited before
  execution**: the audit surfaced three correctness blockers (a thread-as-gate that did not
  exercise a real second process, a key-match-only idempotency that a forged event could exploit,
  an unvalidated cursor that could silently reset to 0) and five hardening items, all ADOPTED
  into the plan and re-reviewed.
- **Decisions:**
  1. **`refs/threeway/events` is one git commit per event (`RefEventStore`), replacing the
     Slice-1 file `EventStore` behind the same `append`/`iter_events`/`all_events` interface
     (§8).** Each event is written as `events/<brief_id>/<id>.json` plus an `index/<seq:08d>`
     entry in the same commit, so a single ref walk recovers total seq order without reading the
     working tree. The Slice-1 public read/iter API promised in ADR-030 §2 is preserved exactly,
     so callers (predicate, gate, reducer) are agnostic to the storage swap.
  2. **Dual-mode CAS append — authoritative remote push-CAS, local update-ref CAS for
     co-located/gate use.** The authoritative path is `git push --force-with-lease` to a bare
     bus ref; on a lease rejection the appender RE-FETCHES the authoritative head, RE-SEQs to
     `max(seq)+1`, and **RE-SIGNS** — because `seq` is a *signed* field (envelope `_signed_view`),
     a re-sequenced event whose signature was not regenerated would fail verification, so the
     retry loop must re-sign, not just re-number. The local `cas_update_ref` mode (no remote)
     serves co-located single-host runs and the gate's own recompute path.
  3. **Effectively-once idempotency that VERIFIES, not just key-matches.** On a candidate whose
     `idempotency_key` collides with a stored event, the store does NOT trust the key: it
     RECOMPUTES the key from the stored event's fields, VERIFIES the candidate's signature
     against the *appender's own* registered pubkey (so a forged event signed by an attacker
     cannot suppress a legitimate later append), and compares an **actor-scoped canonical request
     fingerprint**. Match → return the stored event (true at-most-once); key-collision with a
     *different* request → raise **`IdempotencyKeyReused`** (`threeway/refstore.py:55`) rather
     than silently dropping or overwriting. This closes the audit's "a forged duplicate can
     censor a real fact" hole.
  4. **Bounded retries with jitter + stable typed contention errors.** Both the append loop and
     the cursor loop retry a bounded number of times with jittered backoff (injectable sleeper
     for deterministic tests), then raise a *stable typed* `AppendContentionExceeded` /
     `CursorContentionExceeded` (`threeway/refstore.py:51`/`:59`) — never an opaque git error and
     never an unbounded spin. Typed errors let callers distinguish "lost the race, retry later"
     from a real fault.
  5. **Validated monotonic-CAS per-seat cursors (`refs/threeway/cursors/<seat>`).** A cursor
     advance is rejected if it is negative, beyond the current head seq, or names a seq with no
     index entry; a malformed cursor blob raises **`CursorCorruptionError`** rather than silently
     reading as 0 (the audit's "cursor silently resets, seat re-processes from the start" hole).
     **Cursor design BOUNDARY (carried from review):** the cursor write uses the LOCAL
     `cas_create_or_update_ref` (`threeway/gitcas.py:171`), NOT the remote push-CAS path that
     `append` uses — cursors are per-seat *local* progress by design; remote/multi-host cursor
     publishing is explicitly DEFERRED to a future slice (spec §13). And **owner-only
     enforcement** (spec §8: a cursor is "writable only by that seat") is a deployment ref-ACL
     concern — **test-infeasible** in a single local repo, so it is documented as a deployment
     requirement rather than asserted by the suite.
  6. **`brief_version` signed (D-A) + a signed `signature_version` discriminator + fail-closed
     non-destructive `preflight_bus_init`.** Including `brief_version` in the signed set closes a
     post-sign authorization-redirection vector (an unsigned brief pointer could be swapped after
     signing). The signed profile is now **14 fields** (`_signed_view` in
     `threeway/envelope.py:73`), discriminated by a new **signed** `signature_version =
     "threeway-sign/2"` so a future profile change is detectable inside the signed bytes;
     `schema_version` stays the wire-format version and is independent. Bus bring-up runs through
     a **fail-closed, NON-DESTRUCTIVE** `preflight_bus_init` (`threeway/gitcas.py:231`) that
     ABORTS if any local or remote `refs/threeway/*` already exists (it never deletes) and
     fails closed on any git error — so a half-initialized or pre-existing bus can never be
     silently clobbered or partially trusted.
  7. **F1/F2 gate hardening.** The scope check is now path-segment-boundary aware (a candidate
     touching `foo_evil/x` no longer passes a `foo/`-scoped check by prefix); and a nonexistent
     attested SHA REJECTS via both a predicate guard and a gate-level try/except backstop, so
     `run_gate` (`threeway/gate.py:95`) stays a TOTAL function (every input yields an explicit
     decision, never an uncaught exception that strands the bus).
  8. **Legacy `coordination/` markdown mailbox migration DEFERRED (D-B).** Slice 2's Pair B needs
     only the new threeway keystore seats; migrating the existing four-files-to-sync markdown bus
     onto `refs/threeway/events` is tracked as the **Slice 2.5 stub**
     (`docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md`).
     This keeps Slice 2 honest-scoped and leaves the markdown coordination layer UNTOUCHED, as in
     ADR-030.
  9. **Pair B + two-pair concurrency.** The candidate builder is pair-parametrized and emits
     per-candidate (and per-attestation-sub-kind) event ids, so two pairs running concurrently do
     NOT collide on the `events/<brief_id>/<id>.json` tree path. The serial merge-queue re-stages
     a stale loser (the second pair to reach the gate re-derives against the advanced base); a
     genuine merge conflict aborts the candidate → rework, never a silent or forced overwrite.
- **Consequences:** the bus is now multi-writer and host-distributable for *events* (cursors and
  the legacy markdown bus are not yet, by the boundaries above). The signed profile widened 12 →
  14 fields, so Slice-1 events do not verify under Slice-2 keys without the `signature_version`
  discriminator — intended, and the reason the discriminator is itself signed. The "verify, don't
  key-match" idempotency and the typed bounded-retry contract make the contention paths testable
  with an injected sleeper and a real second process rather than a thread standing in for a
  process.
- **Evidence:**
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q`
  -> `152 passed` (the §11 Slice-2 suite: genuine 2-process append-contention gate, verifying
  idempotency, validated-cursor corruption/bounds, F1/F2 scope + nonexistent-SHA, two-pair
  no-collide + serial-merge-queue re-stage + abort-on-conflict rework). `scripts/ci_smoke.py`
  -> OK (no ceremony; ARCHITECTURE.md doc-anchor gate green).
- **Cross-refs:** **ADR-030** (Slice 1 — this slice fulfills its §2 deferral); spec
  `docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md` §8/§13;
  plan `docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.md`;
  Slice 2.5 stub `docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md`;
  ARCHITECTURE.md §13A (threeway/ subsystem);
  `threeway/` package (`refstore`, `gitcas`, `envelope`, `keys`, `predicate`, `gate`).

## ADR-032 — The verification dispatch is a self-executing, fail-aware, machine-consumable contract

- **Status:** ACCEPTED (implemented on branch `feat/harden-verification-dispatch`:
  `docs/templates/claude/reviewer.md` rewrite, `director-operator.md` + `implementer.md` both
  trees, `scripts/check_no_ceremony.py` R5). Plan
  `docs/superpowers/plans/2026-06-19-harden-verification-dispatch.md`. DEFERRED: the `scripts/`
  JSON consumer + fabrication-detection re-run + R6. (Originally drafted as ADR-031; renumbered
  to 032 on merge because Slice-2's ADR-031 landed on `main` first — git is the tiebreaker.)
- **Context:** an external "Level 4 of 5" assessment of the live Slice-2 verification dispatch
  named 5 weaknesses (prose-only output; over-anchoring to expected impl details; weak evidence
  capture; under-specified trailer; absent failure-handling). An adversarial design pass
  (`wf_b89b9c6c-128`: 5 per-weakness designers + 2 cross-cutting critics) confirmed all five AND
  found the keystone the assessment MISSED: in a repo whose anti-ceremony doctrine (ADR-027/028)
  turns on EXECUTING strict-xfail pins with `--runxfail`, the reviewer was never required to
  re-run the implementer's pins — so a machine-readable schema of *pasted* evidence would
  relocate ceremony into JSON, not remove it.
- **Decisions:**
  1. **One canonical verdict enum:** `pass | issues | unable_to_verify`. Emoji (✅/⚠️/❌/⛔) and
     seat `GO/NITS/FAIL` are HUMAN RENDER of it via a documented 1:1 map — no fifth vocabulary.
     Severity is a SEPARATE axis (`issues[].severity`); a single reviewer's verdict is binary,
     the operator synthesis derives the minor/critical band.
  2. **`reviewer-result/1` machine-readable schema**, emitted as the LAST thing in every reviewer
     reply (MANDATORY at the subagent level; word-cap exempt). The mailbox-level merged block
     stays OPTIONAL until a `scripts/` consumer exists — a schema no instrument executes is itself
     ceremony.
  3. **An Evidence preamble the reviewer RUNS, not asserts:** `rev-parse HEAD` == reviewed SHA,
     `status --short` empty, base availability, file provenance via `git show <SHA>:<path>`, the
     literal pytest summary + exit code, and — the keystone — **re-run each named pin with
     `--runxfail` + a one-fact mutation non-vacuity check.** Every command records its `exit_code`
     (operationalizes R-EVIDENCE / R-MEASURE). `implementer.md` (both trees) now emits the pin
     selectors so the reviewer has the handle.
  4. **`unable_to_verify` (U1–U5: no venv / tests-can't-run / dirty tree / HEAD≠SHA /
     base-unavailable) is a distinct disposition from a NO-GO** — the run did not conclude, the
     code is unjudged. It propagates to the reviewer verdict, the operator `verification-report`
     status (both trees), and the disposition matrix as **RE-DISPATCH** (cap 2 then escalate to
     the user-principal; persistent UTV → R-VERIFY-TIER(B) `test-infeasible`; fail-closed wave
     gate). W4: the reviewer NAMES the existing `Co-Authored-By` trailer; **no `Verified-by`
     trailer** is introduced (the reviewer is read-only/cold; a verification trailer would be
     status-without-evidence ceremony, and the mailbox `verification-report` already records
     who-verified-what).
  5. **Mechanical guard now, consumer later.** `check_no_ceremony.py` **R5** forbids
     `unable_to_verify` as an inventory row `status` (else it bypasses `wave_gate_check`'s
     severity/provisional-only blocking — an ADR-027 hole) and runs inside `ci_smoke` (ADR-028
     hard-wiring). DEFERRED to a tracked follow-up: a `scripts/` consumer that parses
     `reviewer-result/1`, RE-RUNS the reported pytest to detect a fabricated summary, maps
     reviewer-severity→inventory-severity, and adds **R6** (a `pass` report cites an executed
     `--runxfail` run). R6 ships WITH the consumer, not before.
  6. **Also folded (found by the completeness critic, not in the assessment):** M-COLD-CONTEXT
     (Rule #9 independence + CC-2 verify-before-asserting + "dispatch on Opus" are now
     verbatim-include blocks in the template the subagent actually reads); M-DISAGREE
     (reviewer-conflict resolution: conservative dominates, `unable_to_verify` dominates both,
     genuine contradiction escalates); M-FLAKY-PARTIAL (a non-reproducible run is a finding,
     never retried-to-green).
- **Evidence:** plan `docs/superpowers/plans/2026-06-19-harden-verification-dispatch.md`; design
  pass `wf_b89b9c6c-128`. R5 non-vacuity: a crafted UTV status row → 1 violation at the status
  cell, real inventory clean. `.venv/bin/python scripts/check_no_ceremony.py` → R1/R5 PASS (R3/R4
  also PASS — FIX-1/FIX-2 have since landed); `scripts/ci_smoke.py` → OK.
- **Cross-refs:** ADR-027 (execute the oracle), ADR-028 (ceremony forbidden + detector);
  `docs/templates/claude/reviewer.md`; `docs/protocol/{claude,agents}/director-operator.md`;
  `docs/templates/{claude,agents}/implementer.md`; `scripts/check_no_ceremony.py` (R5);
  CLAUDE.md R-EVIDENCE / R-MEASURE / R-VERIFY-TIER. Reciprocal upstream: the live Slice-2
  dispatch's one-line review contract shows plan-authoring guidance should require a NAMED
  reviewer output contract — folded into the deferred follow-up.

## ADR-033 — Reviewer-result consumer + R6 built; ADR-032's deferred follow-up discharged

- **Status:** ACCEPTED (implemented on branch `feat/reviewer-result-consumer`, off `main`
  @ `2a932ac0`). Discharges the DEFERRED follow-up of ADR-032 Decision 5 ("R6 ships WITH the
  consumer, not before"). New: `scripts/consume_reviewer_result.py` (+ `tests/unit/`
  `test_consume_reviewer_result.py`, `test_check_no_ceremony_r6.py`); modified:
  `scripts/check_no_ceremony.py` (R6), `scripts/ci_smoke.py` (smoke wiring).
- **Context:** ADR-032 shipped the `reviewer-result/1` schema MANDATORY at the subagent level
  but kept the mailbox-level block OPTIONAL because nothing parsed it — an unconsumed schema is
  ceremony (ADR-028). This builds the instrument that consumes it, so the schema now has an
  executing reader.
- **Decisions:**
  1. **`scripts/consume_reviewer_result.py`** parses the LAST `reviewer-result/1` json block from
     a `*verification-report*.md` event (or stdin), validates the invariants (pass⇒issues empty;
     issues⇒≥1; unable_to_verify⇒issues empty + `unverifiable_reason`∈U1..U5 + `blocked` non-null;
     `reviewed_head`==`reviewed_commit` unless UTV; `working_tree_clean=false` only with UTV),
     maps reviewer-severity→inventory-severity (critical→CRITICAL, important→MAJOR, minor→MEDIUM),
     and PROPOSES (never applies) `REMEDIATION-INVENTORY.md` status transitions for rows that cite
     the reviewed commit.
  2. **Fabrication detection is the central value.** The CLI RE-RUNS each pytest command the
     reviewer claims it ran and diffs the *normalized* summary (counts only — the `in <duration>s`
     tail and `warning` counts are ignored so honest runs never false-alarm) plus the exit code
     against the reported values. A mismatch is a HARD FAIL: a reviewer can otherwise paste a fake
     "N passed" it never executed. The re-runner is shell-injection-safe — it executes ONLY a
     vetted pytest argv (no shell, refuses `;&|<>$(){}` and backticks); non-pytest commands are
     skipped, never run.
  3. **`check_no_ceremony.py` R6 (`report-cites-executed-pin`)** — a `pass` verification-report
     MUST cite an executed `--runxfail` pin run in `commands[]`; a GO with no pin re-execution is
     ceremony. High-precision (fires only on a present block with verdict `pass`); inert until
     reviewers emit blocks (today's mailbox has zero). Parsing is delegated to the consumer so
     there is ONE parser. Wired into `main()` alongside R5.
  4. **`ci_smoke` runs the SCHEMA-VALIDATION half only, never the re-run.** Re-running a historical
     event's pins against today's HEAD would false-alarm (wrong tree), so `smoke_check()` only
     schema-validates present blocks; the fabrication re-run is the on-demand
     `consume_reviewer_result.py <event>` CLI (tree at the reviewed commit). Zero blocks → silent 0.
  5. **The mailbox-level JSON block STAYS OPTIONAL.** Even though a consumer now exists, promoting
     the merged block to MANDATORY is a SEPARATE future decision — deferred until reviewers emit
     blocks in practice and the consumer has been exercised on real events. Subagent-level emit
     remains MANDATORY (unchanged from ADR-032).
  6. **The re-runner is the security boundary, hardened by adversarial review.** It executes
     command strings from an UNTRUSTED mailbox, so three independent Lane-V / code-quality passes
     (Opus) attacked it and an arbitrary-code-execution CLASS was found and closed in four layers:
     (a) pytest must be EXECUTED — `<python> -m pytest …` or a `pytest` console script — not merely
     present as a token (`python evil.py pytest` is refused); (b) the `env` prefix may carry only
     `-u NAME` unsets, never a `NAME=value` assignment (`env PATH=/tmp/evil pytest` injection
     refused); (c) the launcher must carry a path separator and resolve to an in-repo path or
     `sys.executable` — a bare PATH-resolved name (the PATH-redirection vector) and an absolute
     out-of-repo path (`/tmp/evil/pytest`) are both refused; (d) targets are confined to
     repo_root (out-of-repo `conftest.py` refused). Never `shell=True`. Residual vectors all
     require the attacker to also plant a file on the operator's disk (documented; the re-run is
     only as trusted as the tree at the reviewed commit). The review also caught an efficacy
     regression (the launcher guard initially mis-skipped the repo's own
     `env -u GIT_INDEX_FILE .venv/bin/python -m pytest` idiom) — fixed + pinned.
- **Evidence:** TDD red→green throughout (incl. RED-first pins for every security finding).
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_consume_reviewer_result.py
  tests/unit/test_check_no_ceremony_r6.py -q` → `87 passed` (79 consumer incl. 2 real-pytest
  fabrication integration tests + the security regression pins, + 8 R6).
  `.venv/bin/python scripts/check_no_ceremony.py` → R6 PASS (inert), exit 0; R6 non-vacuity proven
  — a crafted `pass` report with no `--runxfail` command → `rule_report_cites_executed_pin` FAIL.
  `.venv/bin/python scripts/ci_smoke.py` → OK. Neighboring suites
  (`test_check_doc_claims`/`test_check_coordination`/`test_coordination_bin`/`test_four_seat_coordination`)
  → `204 passed`.
- **Cross-refs:** ADR-032 (the schema this consumes), ADR-027 (execute the oracle), ADR-028
  (ceremony forbidden + detector); `docs/templates/claude/reviewer.md` (the `reviewer-result/1`
  contract); plan `docs/superpowers/plans/2026-06-19-harden-verification-dispatch.md` (Deferred
  follow-up, now discharged).

## ADR-034 — Cross-provider seat topology Slice 2.5: legacy `coordination/` mailbox migrated onto `refs/threeway/events` as carrier events, in-memory shadow, single authority-flip cutover; coordinator + coordinator2 become receiving seats

- **Status:** ACCEPTED (Slice 2.5 implemented per the design spec
  `docs/superpowers/specs/2026-06-20-threeway-slice2.5-legacy-bus-migration-design.md` and the plan
  `docs/superpowers/plans/2026-06-20-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md`).
  Discharges **ADR-031 Decision 8** (the D-B deferral of the legacy-mailbox migration). The §11 boundary
  to plan/execute this was satisfied by Slice 2's green gate (`152 passed`, merged at `2a932ac0`).
  Slice 3 (`co_sign_satisfied` true for T2/T3 — `threeway/tier.py:32-43`) remains deferred.
- **Context:** ADR-030/031 shipped the additive `threeway/` ref-bus but left the LIVE human-operated
  markdown mailbox (`coordination/`, the `send-event`/`consume-events`/`check_coordination.py`/`status.py`
  bus the 4-seat campaign runs on — 768 `sent/*.md` events) on the old substrate. The legacy vocabulary
  (`coordination/mailbox/kinds.txt`, 25 human-coordination kinds) is 100% disjoint from the threeway
  governance kinds, so `reduce()` (`threeway/reducer.py`, no `else`) would silently drop every legacy
  event if folded through it. The migration also had to make `coordinator` (today send-only) and a new
  `coordinator2` first-class RECEIVING seats without ever opening a dual-write-authority window on a bus
  with seats actively running.
- **Decisions:**
  1. **Carrier-event model — legacy events ride the existing non-load-bearing `event_sent` kind, never
     `reduce()`.** Each `sent/*.md` is projected to a `threeway.envelope.Event` with `kind="event_sent"`
     (already in `THREEWAY_KINDS`, `threeway/__init__.py`); the original legacy kind, subject, `When:`,
     `Cursor at send:`, recipient, and full body bytes go into `payload`. No new kinds, no `kinds.txt`
     change, no governance semantics. Because `event_sent` is NOT in `LOAD_BEARING_KINDS`, the gate's
     `verify_and_reduce` (`threeway/gate.py:38`) never reads a carrier's signer — the migration-importer
     identity needs no `PublicKeyRegistry` entry, and a carrier structurally cannot masquerade as a
     governance attestation.
  2. **`subject_sha = sha256(source_filename)` to keep idempotency INJECTIVE.** `idempotency_key`
     (`threeway/envelope.py`) is `sha256(sender:kind:subj:payload_digest)`; without a per-file subject the
     ~125 byte-identical same-`(sender,kind)` `status`/`ack` events would collide and the cutover would
     drop one. Filenames are unique even within a same-second group, so this is the single shared
     load-bearing invariant under both injectivity and the §6 total order. `brief_id="legacy-import"`
     namespaces all 768 carriers under `events/legacy-import/`.
  3. **"Shadow" is an IN-MEMORY projection (D2) — zero `refs/threeway/events` writes until cutover.** The
     projector (`threeway/legacy_projector.py`) is a pure read-only function; the divergence-check
     (`threeway/divergence.py`) compares the projected event SET against the live mailbox on the RAW set
     (never `reduce()`/`EffectiveState`). "No dual-write authority" is therefore STRUCTURAL, not merely
     policy — pinned observable: a full shadow leaves `gitcas.rev_parse(repo, EVENTS_REF)` unchanged
     (design §8 clause #6).
  4. **Single authority-flip cutover (D2/§5c).** After ≥1 zero-divergence shadow cycle + a one-pair canary:
     fail-closed `preflight_bus_init(force=False)` (`threeway/gitcas.py:231`) → 768 sequential
     `RefEventStore.append()` carrier appends in the `(filename ts, full filename)` total order → 6
     cursor backfills → ONE explicit authority-flip act. The 768 appends are non-atomic CAS, so a failure
     tears down the partial `refs/threeway/events` prefix (no reader sees a half-backfilled bus). Before
     the flip, legacy `sent/` is authoritative; after it, the ref-bus is, and `sent/` is RETAINED
     read-only as the rollback source (the forward projector is lossy w.r.t. markdown framing, so rollback
     re-designates the retained tree + restores the cursor manifest — no byte-regeneration claim).
  5. **ISO → scalar `seq` cursors, reversible via a committed manifest (D4).** Each seat's ISO high-water
     `seen/<seat>.txt` maps to the highest `seq` whose event ts ≤ the ISO cursor under the total order;
     `advance_cursor` (`threeway/refstore.py:222`) materializes `refs/threeway/cursors/<seat>`. `_CURSOR_RE`
     (`scripts/check_coordination.py:68`) and the other cursor parsers loosen to accept the scalar in
     lockstep, ATOMICALLY in Phase C (no intermediate commit ever has a scalar cursor under an ISO-only
     regex). `coordination/mailbox/.migration/cursor-backfill.json` archives the original ISO values +
     the ISO→seq map, so restoring it rewrites `seen/*.txt` byte-for-byte.
  6. **coordinator + coordinator2 become RECEIVING seats; the ~12-copy roster consolidates to one root
     (D1).** `scripts/protocol_mailbox.py` is the single Python roster root (`RECEIVING_SEATS`); every
     Python copy imports it; the 4 shell whitelist sites stay hand-synced but are guarded by a
     token-extraction test asserting shell-list == Python root. The send-only special-casing for
     coordinator is removed in lockstep with the prose (D5: prose-matches-code is a repo invariant).
     coordinator2's cursor seeds at the bus head (zero spurious backlog); `self`-address stays refused.
     **Option B roster decouple (execution-surfaced, user-approved):** `SEAT_ORDER` (`scripts/protocol_capacity.py`)
     is the standing capacity COVERAGE actor set (coordinator + the 4 pair seats — drives the G1/G2
     capacity gates), kept DISTINCT from a NEW `VALID_OWNERS` (= the `protocol_mailbox` receiving root incl
     coordinator2), the owner/recipient ACCEPTANCE whitelist. coordinator2 is therefore an
     accepted-but-OPTIONAL owner, NOT a mandatory per-cycle scheduling actor — a roster refactor must not
     silently impose new mandatory staffing. **Coordinators are pair-seat-EXCLUDED for heartbeats +
     capacity coverage, but full RECEIVERS for mail/cursors:** `seat_status.heartbeats()` and the
     `mailbox_monitor` heartbeat snapshot iterate `protocol_mailbox.SEATS` (the 4 pair seats —
     coordinators have no presence heartbeat), while receipt/cursor/unread iterate `RECEIVING_SEATS` (6).
- **Consequences:** the live campaign bus is now event-sourced on the same substrate as the governance
  bus, with `coordinator`/`coordinator2` addressable both ways. There is no dual-write window at any
  phase (Phase A purely additive; shadow read-only in-memory; cutover a single post-success flip).
  Rollback is the retained read-only `sent/` + the reversible cursor manifest. The four new modules are
  ADDITIVE and import the Slice-2 API without ever editing `refstore`/`gitcas`/`envelope`/`reducer`/
  `gate`/`tier`: `legacy_projector` and `divergence` are pure read-only projection/compare;
  `cursor_backfill` rewrites the legacy `seen/*.txt` cursors + the reversible manifest (no refs touched);
  and `cutover` is the single gated WRITER — the one authoritative authority-flip append to
  `refs/threeway/events` — NOT read-only. Slice 3 is now the only remaining slice. **The LIVE cutover is a SEPARATE
  post-merge operational act:** this plan ships the tested cutover MACHINERY (`threeway/cutover.py`) but
  does NOT flip the live bus. `run_cutover` returns `CutoverResult(ready_to_flip=True)`; the authority-flip
  marker commit is the operator's deliberate act, run on a quiet bus. **OPERATIONAL note:** the live
  cutover append loop is O(n²) (`RefEventStore` re-verifies all priors per append) — ~50 min for 768
  events with no progress output; this is expected, NOT a hang.
- **Evidence:**
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q` → `191 passed`
  (Slice 1 + Slice 2 + the Slice-2.5 roster/projector/divergence/cursor-backfill/cutover suites).
  `scripts/ci_smoke.py` → OK (no ceremony; §13A doc-anchor gate green; non-vacuity proven —
  `legacy_projector.py:9999` → `DOC-ANCHOR DRIFT` / `out_of_bounds`, reverted to `:63`).
  `scripts/check_no_ceremony.py` → clean (zero xfail/skip/importorskip introduced).
- **Cross-refs:** **ADR-031** (Slice 2 — this slice discharges its Decision 8 / D-B deferral); design spec
  `docs/superpowers/specs/2026-06-20-threeway-slice2.5-legacy-bus-migration-design.md`; plan
  `docs/superpowers/plans/2026-06-20-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md`;
  the now-SUPERSEDED tracking stub
  `docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md`;
  ARCHITECTURE.md §13A.5 (legacy-bus projection); `threeway/legacy_projector.py`, `threeway/divergence.py`.

## ADR-035 — Cross-provider seat topology Slice 3: tiered co-sign `co_sign_satisfied` enforces T2/T3, with all identity grounded on overseer-signed assignment facts + the key-bound seat token, never the unsigned `signer` string

- **Status:** ACCEPTED (Slice 3 implements the merge-gate tier machinery — scope (a) — for the
  cross-provider spec §11; the §11 boundary to plan/execute this was satisfied by Slice 2.5's green
  gate, ADR-034). This is the LAST of the originally-deferred slices; the residual work below is
  scope (b), a separate future slice.
- **Context:** ADR-030/031/034 shipped the `threeway/` signed event-store, gate, and the live-bus
  migration, but left `threeway.tier.co_sign_satisfied` a Slice-2.5 stub (always-false for the
  escalated tiers). With the bus event-sourced, escalated-tier promotion (§7.2) needed a real,
  fail-safe T2/T3 predicate so cross-family approvals can actually gate a merge.
- **Root cause that shaped the design:** the `signer` string carries a provider/session tail that is
  EXCLUDED from the 14-field signed view (`envelope.py:67`), so provider and session are spoofable —
  a predicate must never read them for identity. Trustworthy identity therefore comes only from the
  overseer-signed `assignment` facts (who plays which seat in which pair) plus the key-bound seat
  TOKEN that verifies the event signature.
- **Decision:**
  1. **T2 — mirror-pair operator `co_sign`, fail-closed on ambiguity.** `_mirror_pair_verifier_seat`
     resolves, from the signed `assignment` facts, the unique pair != candidate-pair whose providers
     are the D3 role-swap of the candidate pair (`builder_provider == our verifier_provider` AND
     `primary_verifier_provider == our builder_provider`), then matches that pair's `primary_verifier`
     seat via the key-bound `state.co_sign(candidate_id, seat)`. A `co_sign` GO bound to the
     `integration_sha` is required. **Zero or >1 resolved mirror → PENDING (fail-closed)** — never a
     silent pass.
  2. **T3 — cross-provider re_verify + two SHA-bound overseer human_approvals.** T3 adds a `re_verify`
     GO from the candidate pair's OWN `primary_verifier` seat (the cross-provider operator), bound to
     the `integration_sha`, behind a defense-in-depth independence guard; plus two DISTINCT,
     SHA-bound, affirmative (`decision == "approve"`) `human_approval` facts signed by the `overseer`.
  3. **All effective accessors are revocation-aware** (co_sign / re_verify / human_approvals /
     assignments drop events superseded by `attestation_revoked`); security params are keyword-only;
     and the predicate is fail-SAFE end to end — any insufficiency or missing artifact → PENDING.
- **Deferred to scope (b)** (filed in `docs/REMEDIATION-INVENTORY.md`): (i) the re_verify "new
  session" freshness is NOT enforced because session is unsigned (`threeway-signer-unsigned-session`,
  MAJOR); (ii) "two distinct human_approval" is two overseer-asserted labels, not two independent
  human signatures (`threeway-human-approval-overseer-asserted`, MINOR); (iii) assignments have no
  dedicated supersede fact — same-pair re-assignment is last-write-wins, revoke via
  `attestation_revoked`.
- **Consequences:** escalated tiers can now promote once the cross-family approvals exist, gated on
  SIGNED identity only. Scope (b) remains a separate future slice: dual-chief approval apps, overseer
  brief distribution, the LIVE emission of `co_sign`/`re_verify`/`human_approval` facts, the re_verify
  freshness challenge (an overseer-issued nonce in the signed payload), and per-approver human auth
  (allowed-approver roster / dual-chief relay keys).
- **Evidence:**
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q` → `226 passed`
  (Slice 1 + Slice 2 + Slice 2.5 + the Slice-3 T2/T3 + provider-spoof + self-mirror-guard suites).
  `scripts/ci_smoke.py` → OK; `scripts/check_no_ceremony.py` → clean.
- **Cross-refs:** **ADR-034** (Slice 2.5 — this slice satisfies its §11 boundary and discharges the
  final deferral); ARCHITECTURE.md §13A.6 (tiered co-sign); `threeway/tier.py`;
  `threeway/envelope.py:67-90` (the unsigned `signer` exclusion);
  `docs/REMEDIATION-INVENTORY.md` (`threeway-signer-unsigned-session`,
  `threeway-human-approval-overseer-asserted`).

## ADR-036 — Revocation authority: an `attestation_revoked` takes effect only from the `overseer` or the target's own signer seat (closes the Slice-3 forged-revoke promotion/DoS)

- **Status:** ACCEPTED. Closes a CRITICAL surfaced by the Slice-3 whole-implementation
  adversarial review (independently reproduced end-to-end against HEAD).
- **Context / root cause:** `revokes_event_id` is EXCLUDED from the 14-field signed view
  (`envelope.py:67`), and `reduce()` previously honored EVERY `attestation_revoked` —
  `st._revoked_event_ids.add(ev.revokes_event_id)` — with no authority check. Because
  `attestation_revoked` is a `LOAD_BEARING_KIND` the gate verifies its signature, but ANY
  registered insider seat can mint its OWN validly-signed revoke and re-point its (unsigned)
  `revokes_event_id` at ANY target without breaking the signature.
- **Why Slice 3 made it CRITICAL:** ADR-035's `co_sign_satisfied` made assignment resolution
  revocation-aware (`assignments()` / singular `assignment()`), as spec §6.1 requires (the
  predicate must read only EFFECTIVE facts). That correct change converted the latent revoke
  gap into a forged-PROMOTION primitive: with ≥2 swap-eligible mirror pairs the gate fails
  closed (PENDING), but a forged non-overseer revoke of a RIVAL mirror's overseer-signed
  assignment collapses the ambiguity onto a seat the attacker controls → MERGEABLE. It also
  enables a 2-pair merge-gate DoS (revoke the only legit mirror → PENDING). This defeats the
  Slice-3 acceptance promise "ambiguity yields PENDING, never an erroneous MERGEABLE".
- **Decision:** in `reduce()`, honor a revoke iff the revoker seat is authorized for the
  target — `_revoke_authorized(revoker_seat, target_seats)` returns true only when
  `revoker == "overseer"` (control-plane override) OR the revoked id belongs unambiguously to
  the revoker (`target_seats == {revoker}`, self-revocation). The target's seat set is resolved
  from a one-pass `id -> {seats}` index so the check is order-independent AND collision-aware
  (see Follow-up). Both seats are gate-authenticated, so the unsigned
  `revokes_event_id` link is no longer exploitable: pointing a revoke at a fact you do not own
  is simply IGNORED. NO envelope/spec change — `revokes_event_id` stays unsigned; the
  cryptographic binding (an overseer-issued challenge in the SIGNED payload) remains scope (b).
- **Also hardened (same review, defense-in-depth; not attacker-reachable in the signed 2-pair
  topology but restoring fail-closed symmetry):** (i) `co_sign_satisfied` rejects escalated
  tiers when `verifier_provider == builder_provider` (was only checked in the T3 helper);
  (ii) `_mirror_pair_verifier_seat` counts swap-eligible PAIRS, not non-null seats, so a
  second eligible-but-seatless pair still registers as ambiguity; (iii) `_t3_cross_provider_
  re_verify` fail-closes on an empty `primary_verifier` seat (symmetric with the T2 guard).
- **Consequences:** revocation is now an authenticated authority channel like every other
  control-plane fact (`predicate.py`'s overseer/ci seat checks). Legitimate self-revocation
  (an operator revoking its own attestation) and overseer revocation are preserved; only
  cross-seat forged revokes are rejected. One existing test that encoded the loose behavior
  (`test_revoked_assignment_is_pending` — non-overseer revoking an overseer assignment) was
  re-pointed to the overseer (authorized) path; four accessor tests had their revokes made
  overseer-signed.
- **Follow-up (same session, caught by the fix's own adversarial re-verification):** the first
  cut resolved the target seat via a SCALAR `id→seat` last-write-wins index. Because event `id`
  is signed-but-not-globally-unique, an insider could append a validly-self-signed DECOY re-using
  a victim fact's id at a higher seq, poisoning the index to its own seat and re-forging the
  "self-revocation" (re-opening both CRITICALs). Independently reproduced, then closed: the index
  now maps `id → SET of signer seats`, and `_revoke_authorized` treats a CONTESTED id (>1 seat) as
  NOT self-revocable (overseer-only). This makes the reducer self-defending regardless of the gate.
  This closes the revoke channel ONLY; the underlying event-`id` non-uniqueness independently
  enables a store/gate integrity vector (a colliding id shadowing another seat's stored fact) —
  filed separately as `threeway-event-id-not-unique` (root fix: enforce id-uniqueness in
  `verify_and_reduce` + refuse colliding appends in `refstore`).
- **Evidence:** new RED→GREEN pins — reducer `test_unauthorized_seat_revoke_is_ignored`,
  `test_id_collision_cannot_forge_self_revocation`, `test_overseer_can_revoke_contested_id`;
  predicate `test_forged_nonoverseer_revoke_cannot_collapse_t2_mirror_ambiguity` +
  `test_forged_nonoverseer_revoke_cannot_deny_legit_mirror`; tier
  `test_t2_rejects_same_provider_builder_verifier`,
  `test_t2_fail_closed_when_two_eligible_pairs_one_seatless`,
  `test_t3_rejects_empty_primary_verifier_seat`. Both the seat-string and id-collision exploits
  reproduced end-to-end pre-fix and fail-closed post-fix.
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q` → `240 passed`.
- **Cross-refs:** **ADR-035** (the slice that surfaced this); `threeway/reducer.py`
  (`_revoke_authorized` + `reduce`); `threeway/tier.py` (the three hardening guards);
  `docs/REMEDIATION-INVENTORY.md` (`threeway-revoke-authority-unsigned`, `threeway-event-id-not-unique`).

## ADR-037 — Event ids are globally unique: the gate rejects duplicate ids and the store refuses a colliding-id append

- **Status:** ACCEPTED. Closes `threeway-event-id-not-unique`, the foundational root cause behind
  the ADR-036 follow-up (the revoke index was poisonable because event ids aren't unique).
- **Context / root cause:** event `id` IS in the 14-field signed view (envelope.py:78) — so each
  event commits to its id — but uniqueness is enforced NOWHERE. `gate.verify_and_reduce` verified
  each signature independently with no dup-id check; `refstore.append` dedups by `idempotency_key`
  (subject_sha/brief_version) scoped to the appender's OWN key, never by id, and `build_tree_with`
  overwrites `events/<brief_id>/<id>.json` with no path-existence check. So an insider holding ONE
  seat could append a validly-self-signed event RE-USING another seat's `(brief_id,id)`: in the
  `refstore` it OVERWRITES the victim's stored blob (the victim's fact silently vanishes); in the
  Slice-1 `store` (`<seq>-<id>.json`, both persist) it yields two events with one id. Either way
  this re-opens forged-promotion / merge-DoS WITHOUT any revoke (e.g. shadow a rival mirror
  assignment or a release attestation) — the same class ADR-036 set out to close, one layer down.
- **Decision (defense in depth, two layers):**
  1. **Read side — `gate.verify_and_reduce` rejects a duplicate id** across the load-bearing set
     (`raise GateError`), fail-closed, mirroring its existing bad-sig / bus-mismatch / unknown-seat
     rejections. Catches the Slice-1 store's both-copies-persist case and any read-path duplicate.
  2. **Write side — `refstore.append` refuses a colliding append.** After the idempotency check
     (which already returns OUR idempotent re-append), a pre-existing `events/<brief_id>/<id>.json`
     at the synced tip is a genuine collision → `raise EventIdCollision` instead of overwriting.
     The check is re-evaluated each CAS attempt (concurrency-safe) and kind-agnostic (also protects
     against a non-load-bearing carrier shadowing a load-bearing blob).
- **Consequences:** event-id uniqueness is now an enforced invariant, not an assumption. Combined
  with ADR-036's collision-aware reducer (which stays as in-process defense-in-depth, since `reduce`
  is callable without the gate), the forged-promotion / merge-DoS class is closed at the store, the
  gate, and the reducer. The live-bus cutover is unaffected: carrier ids are the unique source
  filename (`legacy_projector.py` `id=p.name`), so no legitimate collision exists. A duplicate id
  now fails LOUD (was silent overwrite/ambiguity).
- **Refinement (same session, the fix's own re-verification found 3 completeness gaps):** the
  first cut enforced uniqueness only on the consumer side and per-(brief_id,id). Closed: (1)
  `refstore.append` now scans by id ACROSS all briefs/kinds (brief_id is attacker-chosen, so the
  per-(brief_id,id) path check was bypassable); (2) the Slice-1 `store.py` got the SAME id-uniqueness
  guard (Rule #13 — `EventStore.append` raises `EventIdCollision`), so a dup id can't enter via that
  substrate and wedge the gate's dup-id reject into a whole-bus DoS; (3) the reducer builds
  `seat_by_id` from LOAD-BEARING events ONLY — a revoke target is always a load-bearing fact, so a
  non-load-bearing carrier (which the gate does not de-dup) can no longer CONTEST a victim's id to
  block its legitimate self-revocation. The forged-promotion class itself was confirmed already
  closed across the re-verifications (signatures hold; overseer authority intact); these three were
  DoS / integrity-assist completeness gaps.
- **Evidence:** RED→GREEN pins — `test_verify_and_reduce_rejects_duplicate_event_id` (gate),
  `test_append_refuses_colliding_event_id_from_another_seat` +
  `test_append_refuses_same_id_under_different_brief` (refstore),
  `test_append_refuses_duplicate_event_id` (store.py),
  `test_non_load_bearing_event_cannot_contest_id_to_block_self_revoke` (reducer); the store-overwrite
  + the 3 completeness gaps were reproduced end-to-end pre-fix and fail-closed post-fix.
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q` → `245 passed`.
- **Cross-refs:** **ADR-036** (the revoke-authority fix whose re-verification surfaced this);
  `threeway/gate.py` (`verify_and_reduce` dup-id reject); `threeway/refstore.py` + `threeway/store.py`
  (`EventIdCollision` + the by-id append guard); `threeway/reducer.py` (LOAD-BEARING-scoped
  `seat_by_id`); `docs/REMEDIATION-INVENTORY.md` (`threeway-event-id-not-unique`).

## ADR-038 — Round-5 hardening: reserved merge-id integrity + `brief_superseded` authority (Rule #13 siblings)

- **Status:** ACCEPTED. Closes two MAJOR defects surfaced by the ADR-037 convergence check — one a
  regression ADR-037 itself introduced, one a Rule #13 sibling ADR-036 missed.
- **Defect 1 (regression introduced by ADR-037) — `gate.run_gate` reserved merge-id.** The gate
  mints its completion fact with the PREDICTABLE id `f"merge-{candidate_id}"`. An insider can
  pre-append a validly-self-signed event (any kind) carrying that id; step-2 idempotency
  (`state.merge_completed(cid) is None`) does not catch it, the predicate can still reach MERGEABLE,
  step-5 performs the IRREVERSIBLE main-ref CAS merge, and then step-6's `merge_completed` append hits
  the NEW ADR-037 `EventIdCollision`. `run_gate`'s `try/except` caught only `CalledProcessError`, so
  the exception escaped UNCAUGHT after main already moved (pre-ADR-037 it was a benign overwrite).
  **Fix:** a reserved-id integrity check (step 2b) — if `merge-{cid}` is already present on the bus,
  REJECT BEFORE the irreversible merge. Converts crash-after-merge into a fail-safe reject-before-merge.
  **Known residual (lesser):** an insider can still claim a known candidate's reserved id to DoS that
  candidate's merge (targeted availability). A full fix reserves the `merge-*` id namespace to the
  gate seat at ingestion — deferred (filed `threeway-reserved-merge-id-dos`).
- **Defect 2 (Rule #13 sibling of ADR-036) — `brief_superseded` authority.** `supersedes_event_id`
  is the OTHER unsigned reference field (listed beside `revokes_event_id`, envelope.py:67-69), and the
  reducer applied it UNCONDITIONALLY, so a forged non-overseer `brief_superseded` silently rolled back
  the latest brief version. ADR-036 fixed the revoke channel but did not audit this sibling. **Fix:**
  gate `brief_superseded` through the SAME `_revoke_authorized` rule (overseer, or the superseded
  brief's own seat), unifying the two unsigned-reference channels under one authority check.
- **Consequences:** the merge gate no longer crashes post-merge on a poisoned reserved id, and both
  unsigned reference fields (`revokes_event_id`, `supersedes_event_id`) are now authority-gated. The
  forged-promotion / merge-DoS CLASS was already closed (ADR-036/037, confirmed across the
  re-verifications); these were an integrity regression + an integrity sibling.
- **Evidence:** RED→GREEN pins — `test_run_gate_rejects_poisoned_reserved_merge_id` (gate),
  `test_forged_nonoverseer_brief_supersede_is_ignored` + `test_overseer_brief_supersede_is_honored`
  (reducer). `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q` → `248 passed`.
- **Cross-refs:** **ADR-036** (revoke authority — this extends it to the supersede sibling), **ADR-037**
  (event-id uniqueness — this fixes its run_gate regression); `threeway/gate.py` (step 2b),
  `threeway/reducer.py` (`brief_superseded` authority); `docs/REMEDIATION-INVENTORY.md`
  (`threeway-brief-supersede-authority`, `threeway-reserved-merge-id-dos`).

## ADR-039 — Availability hardening: authority-aware reducer, self-consistent candidate resolution, and a TOTAL run_gate (closes the insider availability/DoS class)

**Context.** The forgery/forged-promotion class is closed (ADR-036/037/038). A round-6
adversarial sweep (`wf_8002d3e7-e7e`) found a distinct **availability/DoS** class: a single
registered insider seat can *block a legitimate merge* (not forge one). One systematic root:
`reduce()` recorded control-plane singletons via **unauthenticated last-write-wins**, with
authority checked only at *read* time — so a higher-seq event from a non-authorized seat
displaces the authoritative fact before the predicate ever reads it. Threat model: one insider
seat (validly signs as that seat); `overseer`/`ci`/gate seat trusted; cannot forge another
seat's signature.

**Decision 1 — record-time authority filter for static singletons (reducer).** `reduce()`
folds each of the six static control-plane singletons into its map ONLY if the event's
signer-seat is the authorized seat: `assignment`/`brief`/`cycle_go`/`release_order` →
`overseer`, `ci_result` → `ci`, `merge_completed` → the gate seat (`GATE_SEAT="merge-gate"`,
threaded as a `reduce(events, *, gate_seat=...)` keyword so a non-default gate seat is honored).
A non-authorized event of these kinds is DROPPED (never enters the slot), so a shadow cannot
displace first. This is consistent with the predicate's existing read-time seat checks — it
moves the guarantee earlier. *Refinement (§11):* because a wrong-seat singleton is now IGNORED
rather than seen-then-rejected, a forged-only singleton yields PENDING (awaiting the legit fact)
instead of REJECTED — a strictly STRONGER §11 realization (the forged fact has zero effect; the
merge still cannot happen) and the more-available outcome (a forged release_order can no longer
poison a candidate into a permanent REJECTED dead-state). The predicate's read-time wrong-seat
REJECTs are retained as defense-in-depth.

**Decision 2 — self-consistent candidate authority (reducer + predicate).** `_candidates` is
re-keyed `(candidate_id, signer-seat)`; `candidate(cid, seat=None)` returns a specific seat's
candidate or (seat=None) the latest-across-seats locate-only read; and a new
`EffectiveState.authoritative_candidate(cid)` returns the candidate whose signer-seat equals the
`executing_coordinator` of the *overseer-signed assignment for the pair THAT candidate declares*
(self-consistent). The predicate and `run_gate` both resolve the candidate via
`authoritative_candidate`, so they can never disagree about which candidate is effective.
*Deviation from the slice plan's literal design 2(a):* the plan said "read `pair` from the latest
candidate of any seat to locate the assignment." That is insufficient — `pair` is
attacker-controlled, so a higher-seq shadow candidate with a BOGUS pair derails assignment
resolution (→ `assignment(bogus)`=None → PENDING) and still blocks the legit candidate, and it
creates a forgery hazard if `run_gate` merges the shadow's base/branch. The self-consistency rule
closes both: a bogus-pair or non-coordinator shadow is never self-consistent and is ignored. Also
folds in the gate_seat threading from Decision 1's filter (a non-default gate seat's own
`merge_completed` would otherwise be dropped, breaking idempotency).

**Decision 3 — TOTAL, recoverable run_gate + reserved `merge-*` namespace (gate).** (a)
`verify_and_reduce` DROPS (ignores, does NOT raise) a load-bearing event whose id is in the
reserved `merge-` namespace from a non-gate seat — *deviation from the plan's literal "raise at
ingestion," which would let one forged `merge-*` event brick verify_and_reduce for EVERY candidate
(a self-inflicted total DoS).* (b) Main-state idempotency: `run_gate` returns COMPLETED when main
is already at the authoritative candidate's `integration_sha`, so a post-CAS recording failure is
recoverable on re-run, never a permanent `stale` REJECT. (c) Totality: the post-CAS
`merge_completed` append is wrapped so NO exception escapes after the irreversible CAS — a post-CAS
append failure yields a degraded `COMPLETED("merged; completion-fact append degraded: …")`; the
PRE-CAS recompute stays under `except CalledProcessError → REJECTED` (fail-closed, main unmoved).
The ADR-038 step-2b pre-CAS reserved-id REJECT is REMOVED — subsumed by (a)+(b)+(c), which are
strictly MORE available (a squatted reserved id no longer blocks the legit merge; the post-CAS
collision degrades instead of crashing).

**Decision 4 — fail-safe invariant.** Every change only ever DROPS a non-authoritative/shadow
event or makes the gate fail-safe; none widens what can promote. The forgery class
(ADR-036/037/038) is untouched and stays green. Verified: each guard mutation-tested non-vacuous
(RED when reverted) in the per-task spec reviews; the degraded-COMPLETED path is reachable only
after the CAS verified `merge_commit == attested integration_sha` AND `main == staging_base`, so
it can never merge an unauthorized SHA.

**Residuals (flagged for the whole-implementation adversarial review; NOT closed here).** (i) An
attacker who is a *legitimate executing_coordinator of another active pair* AND reuses the exact
`candidate_id` could still present a self-consistent shadow — a `candidate_id`↔pair-binding issue
beyond the shadow class. (ii) When an insider squats `merge-{cid}`, the merge still completes but
the `merge_completed` FACT is permanently un-writable (id taken); recovery relies on main-state
idempotency. Full closure of (ii) would need a store-level id-namespace reservation (reject a
non-gate `merge-*` append at the source), out of this slice's scope.

**Evidence.** Commits `3f7c6a6b`, `fea57c6b`, `f8003b3b`; `tests/unit/test_threeway_*.py` → 266
passed; `scripts/ci_smoke.py` OK; `scripts/check_no_ceremony.py` clean. Acceptance→test map:
shadow-displacement (all 6 static kinds) → `test_threeway_reducer.py` shadow tests; candidate
shadow (same-pair + bogus-pair) stays MERGEABLE →
`test_threeway_predicate.py::test_same_pair_candidate_shadow_does_not_displace` /
`::test_bogus_pair_candidate_shadow_does_not_block`; gate-only merge_completed + reserved-namespace
drop → `test_threeway_gate.py::test_run_gate_drops_nongate_reserved_id_event` /
`::test_run_gate_survives_poisoned_reserved_merge_id`; run_gate total →
`::test_run_gate_total_under_post_cas_append_failure`; main-state idempotency →
`::test_run_gate_main_state_idempotency_without_fact`; forgery class unaffected → existing
ADR-036/037/038 pins stay green.

---

## ADR-040 — Complete `run_gate` totality: verify-phase drop-not-raise + pre-CAS exception guard (ADR-039 follow-up)

**Context.** ADR-039 claimed "a TOTAL `run_gate` closes the insider availability/DoS class." The
slice's mandated whole-implementation adversarial review (`wf_30e51cdf-f6b`, 13 agents, every
exploit reproduced end-to-end through the live gate) found the claim was not yet met: `run_gate` had
two non-total paths an insider could trigger. The forgery/integrity class (ADR-036/037/038) was
re-confirmed CLOSED (every non-fail-safe outcome was availability-only, never a forged promotion).

**Finding 1 (CRITICAL) — verify-phase total-bus brick.** `verify_and_reduce` RAISED `GateError` on
four read-side checks — `bus_id` mismatch, unaccepted `signature_version`, unknown signer seat,
invalid signature — and that call sits OUTSIDE `run_gate`'s try-block. The stores do NO
`bus_id`/`signature_version`/registry validation at append (only id-collision), so one
insider-appended, validly-self-signed load-bearing event with any of those poisons made
`verify_and_reduce` raise on every `run_gate` invocation — an uncaught crash that permanently bricked
the gate for EVERY candidate on the bus. This is the SAME shape ADR-039 Decision 3(a) recognized for
the reserved-`merge-` id check and fixed with drop-not-raise — but that fix was applied only to the
reserved-id line, leaving its three structural siblings raising (a Rule #13 symmetric-check miss).

**Finding 2 (MAJOR) — pre-CAS crash.** A validly-signed authoritative candidate with a missing
required payload key (`staging_base_sha`/`branch_sha`/`integration_sha`) raised an uncaught
`KeyError` in `evaluate()` that escaped `run_gate`'s narrow `except subprocess.CalledProcessError` (a
targeted per-candidate DoS; fail-closed — main unmoved).

**Decision.** (1) In `verify_and_reduce`, convert the four reachable brick-raises to a DROP (the
event is excluded from reduction and from `seen_ids`) plus a `logger.warning` for observability — so
a poison event is IGNORED and the legit events still reduce, the legit merge proceeds, and OTHER
candidates are unaffected. Generalizes ADR-039 Decision 3(a)'s drop-not-raise to all four sibling
ingestion checks. (2) The duplicate-id check STAYS `raise GateError`: it is
store-guarded-UNREACHABLE (the stores' ADR-037 `EventIdCollision` guard rejects a colliding append,
so two same-id events can never both be stored), and keeping it raise preserves ADR-037's
fail-closed-on-ambiguity for a hypothetical store bypass — the principled dichotomy is
*reachable-brick → drop, store-guarded-unreachable → raise*. (3) Broaden `run_gate`'s outer (pre-CAS)
except from `subprocess.CalledProcessError` to `except Exception → REJECTED` (the entire pre-CAS
region is before any ref move → fail-closed, main unmoved); the post-CAS nested `try → degraded
COMPLETED` is unchanged.

**Fail-safe invariant (verified).** Dropping can only ever REMOVE an event from reduction; it can
never admit a forged event or make anything newly MERGEABLE. A legitimate blocking fact
(`candidate_aborted`/`attestation_revoked`) is correctly-signed, right-bus, registered-seat → it
passes all four checks and is never dropped (still blocks); only an unauthenticated event drops, and
it had zero authority anyway. The forgery class stays green; each guard mutation-tested non-vacuous
(RED when reverted) in the Task-5 spec review.

**Residual filed (NOT closed here).** The adversarial review confirmed end-to-end the ADR-039
Residual (i) cross-pair `candidate_id` reuse DoS: an attacker who is the LEGITIMATE
executing_coordinator of another overseer-assigned pair can reuse a victim's `candidate_id`, declare
their own pair at a higher seq, capture `authoritative_candidate`, and stall the victim's merge at a
non-merge outcome — availability-only (the attacker cannot forge the other pair's verifier
attestations, so it never promotes). Filed as inventory row
`threeway-candidate-id-pair-binding-dos` (MAJOR, open) with a strict-xfail pin
`test_cross_pair_candidate_id_reuse_dos_residual`; scoped to a follow-up `candidate_id`<->pair-binding
slice (pair-namespaced candidate ids or first-writer-wins). The reserved-id-squat residual (ii, fact
un-writable under a squat) remains MINOR/observability-only.

**Evidence.** Commit `1f3e65a4`; `tests/unit/test_threeway_*.py` → 271 passed, 1 xfailed (the
residual); `scripts/ci_smoke.py` OK; `scripts/check_no_ceremony.py` clean. Adversarial review run
`wf_30e51cdf-f6b`.

---

## ADR-041 — Make `run_gate` step 1 TOTAL: a `well_formed(ev)` envelope guard + reducer fold/skip guards (ADR-040 follow-up, completes the availability class)

**Context.** ADR-040 made `run_gate`'s VERIFY-phase four explicit `raise` checks and its pre-CAS
region total. Its mandated whole-implementation adversarial review (`wf_30e51cdf-f6b`) plus a chain
of fresh-eyes certifications then found that `run_gate` STEP 1 (`verify_and_reduce` → `reduce`,
which runs OUTSIDE `run_gate`'s try) dereferences many INSIDER-CONTROLLED fields in ways that raise
UNCAUGHT — a sequence of single-insider total-bus brick layers, each surfaced only after the prior
was fixed (the campaign's "each fix reveals the next layer" pattern):
- `reduce()` used insider fields as dict/set keys → `TypeError: unhashable type` on a list-valued
  `candidate_id` / `payload["kind"]` / `payload["approver_identity"]`, and on a non-int `seq` (sort
  key) / non-str `id`/`signer`.
- `EffectiveState.authoritative_candidate` (run_gate step 2a, outside the try) used
  `candidate.payload["pair"]` as an `assignment` key → `TypeError` on a list pair.
- `verify_and_reduce` dereferenced `id` (`.startswith`), `signer` (`_seat` split), and
  `signature_version` (set membership) — and `signer` is UNSIGNED, so a validly-self-signed event
  with a list signer crashes it.
- `if ev.kind in LOAD_BEARING_KINDS:` (the membership test that GATES the per-event block, in both
  `verify_and_reduce` and `reduce`) → `TypeError` on an unhashable `kind`, firing BEFORE any inner
  guard.
All are availability/DoS only (graceful, fail-closed pre-CAS — main never moves; no forged
promotion). Reachable via a validly-self-signed event (unsigned `signer`) and via the at-rest JSON
path (`from_json_obj` does NO type validation), and `reduce()` is also a public function callable
directly with no signature check.

**Decision.** Apply the ADR-040 drop-not-raise discipline to STEP 1, systematically rather than
per-field:
1. **`well_formed(ev) -> bool` (`threeway/envelope.py`)** — true iff every structurally-dereferenced
   envelope field is the expected type: `kind`/`id`/`signer`/`signature_version`/`bus_id` are `str`,
   `seq` is `int`, `payload` is `dict`, and
   `candidate_id`/`subject_sha`/`brief_id`/`revokes_event_id`/`supersedes_event_id` are `str`-or-`None`,
   `brief_version` `int`-or-`None`.
2. **Applied at the TOP of `verify_and_reduce`'s loop** (before the `kind` membership test) and as
   **`reduce()`'s up-front filter** — a malformed event is DROPPED with a WARNING (it has no
   authority). This makes the `kind` membership test, the sort, `seat_by_id`, every envelope-keyed
   fold branch, and `authoritative_candidate`'s `.get` all type-safe, and CONSOLIDATES the earlier
   narrow per-field guards into one structural check.
3. **Payload-VALUE keys** (`payload["kind"]`, `payload["candidate_id"]`,
   `payload["approver_identity"]`, `payload["pair"]`, …) — kind-specific and not covered by
   `well_formed` — stay guarded by `reduce()`'s fold-loop `try/except (TypeError, AttributeError,
   ValueError) → drop+warn` and `authoritative_candidate`'s `isinstance(pair, str)` skip-in-loop.

**Fail-safe invariant (verified).** Every guard only ever DROPS a structurally-malformed event
(which has no authority); a legit event passes and is never dropped (valid `event_sent` carriers
pass too — cutover unaffected). Nothing newly MERGEABLE; the forgery class (ADR-036/037/038) and
ADR-039/040 stay green. Each guard mutation-tested non-vacuous (RED when reverted).

**Evidence.** Commits `eb0b1000` (reduce up-front filter + fold try/except), `584e9f8c`
(authoritative_candidate pair skip), `600e50e6` (verify-phase id/signer/sig_version), `be9c04f0`
(the comprehensive `well_formed`, closing the `kind`/`payload` bricks and consolidating). Closing
certification re-ran the full brick catalogue (35 envelope-field poisons + 15 payload-value probes +
the predicate-internal probes) end-to-end through live `run_gate` — all fail-closed or
drop-then-complete, zero uncaught raises — and re-confirmed the forgery class closed.
`tests/unit/test_threeway_*.py` → 307 passed, 1 xfailed; `scripts/ci_smoke.py` OK;
`scripts/check_no_ceremony.py` clean.

**Residual (NOT closed; tracked).** `threeway-candidate-id-pair-binding-dos` (MAJOR, open,
strict-xfail `test_cross_pair_candidate_id_reuse_dos_residual`): a legitimate executing_coordinator
of another overseer-assigned pair can reuse a victim's `candidate_id` to capture
`authoritative_candidate` and stall the victim's merge — availability-only (never promotes), scoped
to a follow-up `candidate_id`↔pair-binding slice. **CLOSED by ADR-042.**

## ADR-042 — Close `threeway-candidate-id-pair-binding-dos`: structural pair-namespaced candidate ids (ADR-039 Residual (i))

**Context.** ADR-041 left ONE tracked residual: `candidate_id` is a free-form, globally-shared
namespace, so TWO different overseer-assigned pairs (A and B) could each be **self-consistent** for
the SAME `candidate_id` (self-consistency = the candidate's signer-seat equals the
`executing_coordinator` the overseer assigned to the pair the candidate declares). A LEGITIMATE
executing_coordinator of pair B could thus reuse a victim's `candidate_id`, declare pair B, capture
`authoritative_candidate`, and stall the victim's pair-A merge. Availability-only (it can never forge
pair A's verifier attestations, so it never promotes — the integrity class ADR-036/037/038 is
unaffected), but a real per-candidate insider DoS via the normal append path.

**First attempt (first-writer-wins) — REJECTED by adversarial re-verification.** The initial fix bound
a `candidate_id` to the pair of its FIRST self-consistent declaration (earliest `seq`, tracked in a
`_candidate_first_seq` map), reasoning that `append()` reassigns `seq` monotonically before signing
(`store.py:45`/`refstore.py:149`) so an insider can never out-rank an already-declared candidate. The
plan's mandated whole-implementation adversarial review (workflow `wf_01844a2a-03a`, 5 Opus attack
dimensions, each reproduced end-to-end through the real Ed25519 gate) **CONFIRMED a MAJOR flaw: it only
INVERTED the race.** It closed the attacker-declares-LATER case but reopened the symmetric
attacker-declares-EARLIER case — a legit pair-B coordinator who declares the victim's `candidate_id`
for pair B BEFORE the victim wins the lowest `first_seq`, captures authority, and stalls the victim
(reproduced; availability-only). **An order-based tiebreak cannot close a shared-namespace collision —
whoever controls the order wins.** (Integrity and totality were verified solid in that same review and
are orthogonal to the tiebreak.)

**Decision (the complete, order-INDEPENDENT fix).** Bind `candidate_id` to exactly ONE pair
**structurally** by pair-namespacing the id:
1. Candidate ids are `"<pair>:<local>"` (e.g. `"A:c1"`). `threeway/loop.py::build_candidate_events`
   auto-namespaces a bare local id by its pair; emitters/callers drive the gate with the full id.
2. `EffectiveState.authoritative_candidate` (`threeway/reducer.py`) adds an eligibility clause: a
   candidate is authoritative only if its DECLARED `payload["pair"]` equals the candidate_id's
   **namespace** (`_pair_namespace(cid)` = the prefix before the first `":"`; a non-str/un-namespaced
   id → None → no candidate is authoritative). Combined with the existing self-consistency check, this
   means a `candidate_id` can only be claimed by the pair named in its own namespace — a coordinator of
   ANY other pair declares a non-matching pair and is ineligible, **regardless of declare order**. The
   `_candidate_first_seq` machinery is removed (the `(seq, seat)` pick is now only a defensive
   deterministic tiebreak; within one namespace pair exactly one seat is self-consistent).

**Why this closes the CLASS, not the instance.** The binding is a pure function of the victim's own
id (its namespace prefix), which the attacker cannot change for the victim's id. So neither declare
order helps: the attacker's reused-id candidate must declare its own pair, which never matches the
victim's namespace. assignment() is overseer-only (record-time filter), so an attacker cannot forge a
pair-A assignment naming itself; declaring pair A while signing as another seat fails self-consistency.

**Fail-safe / no-widening invariant (verified).** The namespace clause only ever NARROWS eligibility
(it can REMOVE a candidate from authority, never add one), so nothing newly promotes; the integrity
class (ADR-036/037/038) and ADR-039/040/041 stay green. `run_gate` stays TOTAL — `authoritative_candidate`
runs at `gate.py:175` outside `run_gate`'s try, and the ADR-041 `isinstance(pair, str)` skip plus the
`_pair_namespace` None-guard keep it raise-free on malformed/at-rest-planted candidates.

**Evidence.** Reducer + emitter change with the `_candidate_first_seq` attempt fully removed; the
strict-xfail residual pin replaced by two positive regression tests pinning BOTH declare orders
(`test_cross_pair_namespace_blocks_reuse_attacker_declares_earlier` / `_later`). Mutation-proof
(executed): removing the `if pair != ns` clause turns the attacker-EARLIER test RED (`REJECTED`) while
the later test stays green — proving the namespace clause is the specific mechanism closing the
attacker-earlier direction. `tests/unit/test_threeway_*.py` → 309 passed, 0 xfailed; `scripts/ci_smoke.py`
OK; `scripts/check_no_ceremony.py` clean. Re-certification: workflow `wf_28567ca6-c41` (4 Opus attack
dimensions — namespace-bypass both directions, namespace edge cases, integrity, totality+regression —
each reproduced through the real gate). META-LESSON (continuing ADR-039/040/041): adversarially
re-verify your OWN security fix end-to-end through the real gate — the first-writer-wins attempt LOOKED
correct (its xfail flipped, mutation-proofs passed) yet only moved the race; the multi-agent attack is
what surfaced the inverted-race layer.

## ADR-043 — Close the two scope-(b) T3 deferrals: re_verify freshness challenge + per-approver key-bound human_approval

**Context.** Slice 3 (ADR-035) shipped the T2/T3 tiered co-sign with two KNOWN, tracked deferrals
(both `open (deferred to scope (b))` in the inventory):
- `threeway-signer-unsigned-session` (MAJOR): the T3 `re_verify` "new session" freshness was only
  asserted via the UNSIGNED signer-string session (`signer` is excluded from the 14-field signed view,
  envelope.py:67), so a stale/replayed re_verify GO was indistinguishable from a fresh one at the
  crypto layer.
- `threeway-human-approval-overseer-asserted` (MINOR): T3 "two distinct human_approval" was two
  overseer-asserted `approver_identity` LABELS signed by a SINGLE overseer relay key — a
  compromised/mistaken overseer could assert two labels for one human; distinctness was not key-bound.

These are the SECURITY core of scope (b); their fixes are self-contained protocol changes that do NOT
require the external dual-chief app / live-emission layer (which stays deferred with the live cutover).

**Decision.** Two additive overseer-authority event kinds + new T3 predicate clauses, with NO change to
the 14-field signed view (the payload is already bound via the signed `payload_digest`, so data placed
in a payload is cryptographically committed):

1. **Freshness challenge.** New kind `re_verify_challenge` (overseer-signed) carries an unguessable
   `nonce` bound to the candidate + `integration_sha`. `tier._t3_cross_provider_re_verify` now requires
   the overseer's challenge to exist, be bound to this sha, and the re_verify's payload `challenge_nonce`
   to equal the challenge nonce. The nonce lives in the re_verify's OWN payload (bound by
   `payload_digest`), so the verifier cannot forge/alter it; a replayed stale re_verify carries an old
   nonce and fails the current challenge. Freshness is now verifiable from SIGNED facts.

2. **Per-approver key-bound auth.** New kind `approver_roster` (overseer-signed) lists allowed approver
   SEATS. `reducer` now keys `_human_approval` by `(candidate_id, signer-SEAT)` — the key-bound identity
   — not the attacker-influenceable `approver_identity` label, so two approvals from one keyholder
   collapse. `tier._two_distinct_human_approvals` now requires ≥2 distinct roster SEATS (was ≥2
   overseer-relayed labels). A compromised overseer can no longer assert two humans for one keyholder:
   it can designate the roster but it does NOT hold the chiefs' private keys, so two distinct approvals
   require two distinct keyholders to actually sign.

Both new kinds fold **overseer-only at record time** (reducer `_AUTHORIZED_SINGLETON_SEAT`, ADR-039
pattern) and are in `LOAD_BEARING_KINDS`. Plus a §5 totality one-liner: `run_gate` rejects a non-str
`candidate_id` ARGUMENT (driver/caller misuse — the `merge_completed` lookup is outside its try) — closes
the ADR-042 §5 INFO loose thread.

**Why this closes the rows (and only NARROWS).** Both clauses ADD fail-closed requirements on top of the
prior T3 path (which required NO challenge and NO roster), so the new path is strictly narrower —
anything that promoted before AND lacks a fresh challenge / key-bound roster now FAILS; nothing newly
promotes. The forgery/integrity class (ADR-036/037/038) and the availability/totality class
(ADR-039/040/041/042) stay green. `run_gate` stays TOTAL: the new payload-value derefs (nonce/approvers/
challenge_nonce) live only in the tier functions, which run inside `run_gate`'s broad pre-CAS except, and
read via `.get()` + `isinstance` (never as dict/set keys); `well_formed` already guards the new kinds'
envelope-field derefs at step 1.

**Evidence.** 4 source files (`__init__.py` kinds, `reducer.py` state+fold+accessors, `tier.py` 2 clauses,
`gate.py` §5 guard) + 3 migrated test files + 2 new real-gate tests. **Executed mutation-proofs:** (A)
removing the nonce-echo check reddens `test_t3_rejects_re_verify_with_stale_nonce`/`_missing_nonce`; (C)
disabling the roster-membership gate reddens `test_t3_rejects_human_approval_not_on_roster`; (D) disabling
the challenge authority filter reddens `test_t3_rejects_forged_nonoverseer_challenge`. (B) confirmed the
per-approver fix is defense-in-depth: the reducer's per-seat keying collapses same-seat approvals even if
the tier layer is mutated. `tests/unit/test_threeway_*.py` → 321 passed; `scripts/ci_smoke.py` OK;
`scripts/check_no_ceremony.py` clean. **Re-certification** (`wf_d3c80806-ad9`, 5 Opus adversarial
dimensions + independent verifiers, each driving the REAL signed gate): **0 confirmed bypasses,
no_new_promotion=true and regression GREEN across all dimensions.**

**Re-cert findings (all addressed, none a bypass).**
- MAJOR (operational, fail-closed): per-approver auth introduces a NEW liveness precondition — each
  chief approver seat needs its OWN committed registry key (`coordination/threeway/keys/<chief>.pub`),
  or `verify_and_reduce` DROPS its approval as an unknown signer seat (ADR-040) and the T3 candidate is
  stuck PENDING. This NEVER widens promotion (it only fails closed), but the operational layer (scope-(b)
  dual-chief apps) MUST provision chief keys or all T3 promotions brick. ADDRESSED: two real-gate tests
  (`test_run_gate_completes_full_t3_through_signed_gate` proves the COMPLETED path with chiefs registered;
  `test_run_gate_t3_pending_when_chief_keys_unregistered` locks the requirement as a regression guard) +
  this note. The chief seats must be added to the production registry as part of the scope-(b) cutover.
- INFO: the freshness guarantee is challenge-response, so it rests on the overseer issuing fresh,
  unguessable, non-reused nonces — the gate enforces the binding, not the overseer's nonce-rotation
  discipline (the gate cannot generate entropy). Docstring corrected to not overstate it as
  unconditionally cryptographic; fresh-nonce emission is a scope-(b) emitter responsibility.
- INFO: the roster authorizes any overseer-named seat — "distinctness" is KEY-distinctness, not
  human-vs-machine. That is the correct, irreducible trust floor (two distinct keyholders); whether the
  rostered seats are dedicated human approvers is an overseer policy concern, not a gate property.

**Still deferred (unchanged).** The scope-(b) strategic loop's OPERATIONAL layer (dual-chief apps, live
emission of co_sign/re_verify/human_approval + the overseer nonce/roster emitter) and the live cutover
onto `refs/threeway/events`. This ADR closes the two SECURITY rows; it does not wire the live driver.

## ADR-044 — Cutover-substrate hardening: non-atomic `_teardown` (half-flip + masked cause) + refstore dedup dropping a distinct-target revoke/supersede

**Context.** After the two scope-(b) SECURITY rows closed (ADR-043) and the whole assembled control plane
passed a holistic cross-ADR *composition* audit (`wf_2ca48247-f19`, 0 emergent forged-promotion/merge-DoS
gaps), a follow-up *cutover-substrate correctness* audit (`wf_ce0bba9f-0ac`, 6 recovery lenses driving the
REAL `cutover`/`divergence`/`backfill`/`refstore` machinery with injected failures) surfaced two confirmed
MAJOR defects the per-fix passes never looked for — one in the flip's recovery path, one in the store's
dedup layer the composition audit (which tested at the gate/reducer layer) could not see.

**Decision 1 — `_teardown` best-effort-per-ref + chain-not-mask (`threeway/cutover.py`).**
`_teardown` was a bare loop restoring each snapshot ref (EVENTS_REF first) with `check=True`. A single
restore failure — realistically a concurrent writer holding `refs/threeway/events.lock` during the
~50-min cutover window (`run_cutover` docstring warns of it) — raised `CalledProcessError` that (A) aborted
the loop, leaving every later cursor ref un-restored (half-torn-down `refs/threeway/*`), and (B) propagated
out of the except-handler's `_teardown(...); raise`, MASKING the original cutover failure. Now `_teardown`
catches each ref's `CalledProcessError`, CONTINUES restoring the rest, and AGGREGATEs failures into a new
`TeardownError` raised CHAINED from the original cause (`raise TeardownError(...) from original`); a fully
clean teardown stays silent so the caller's bare `raise` re-raises the original unchanged. The two callers
now bind `except Exception as original` and pass it. Recoverable harm only (the authority-flip marker is
the caller's separate commit, so legacy `sent/` stays authoritative throughout; a `force=True` re-run after
the lock clears completes idempotently, dup-free) — MAJOR, not CRITICAL.

**Decision 2 — dedup keys include the load-bearing reference ids (`threeway/envelope.py` + `refstore.py`).**
`idempotency_key` and `_request_fingerprint` both OMITTED `revokes_event_id`/`supersedes_event_id` (top-level
Event fields OUTSIDE the payload, envelope.py:67-69, so `payload_digest` does not cover them). Two overseer
revokes of DIFFERENT targets, identical in sender/kind/payload/candidate, produced the SAME key + fingerprint,
so `RefEventStore.append` deduped the second to the first — it never landed, and its target's attestation
stayed effective toward quorum (identical twin hole for `brief_superseded`). Now both `revokes_event_id` and
`supersedes_event_id` are in BOTH the `idempotency_key` formula and the `_request_fingerprint` view, so a
revoke/supersede of a different target is a DISTINCT request that always lands. Both fields are `None` for
every non-revoke/supersede event, so those events' dedup identity is unchanged and a genuine same-target retry
still dedups. The `_request_fingerprint` half is two-layer defense-in-depth (once `idempotency_key`
distinguishes the target, the fingerprint path is not reached for this case — not independently reddenable,
same shape as ADR-043's two-layer note). Cousin of `threeway-event-id-not-unique` (ADR-037, the id-collision
dedup) and `threeway-brief-supersede-authority` (ADR-038, the authority half of the same unsigned-reference
channels). Pre-flip is the ideal window: the bus is not live, so no persisted at-rest `idempotency_key` (a
DERIVED field, always recomputed and never trusted — refstore.py:102) is invalidated.

**Why safe.** Decision 1 only ADDS recovery robustness (best-effort restore strictly restores ≥ as many refs
as before; chaining preserves, never hides, the original); the happy-path teardown contract is unchanged
(`test_teardown_restores_preexisting_bus_on_failure_under_force` stays green). Decision 2 only NARROWS dedup
(more distinct requests land, never fewer), is `None`-inert for all non-revoke/supersede events, and touches
no signed view — `revokes/supersedes_event_id` remain unsigned (their crypto binding is a separate scope-(b)
concern). Neither touches `run_gate` totality or the 14-field signed set.

**Verification.** TDD red→green: 5 new tests (`test_threeway_cutover.py` ::test_teardown_best_effort_continues_and_chains_original_cause
/ ::test_teardown_clean_restore_stays_silent; `test_threeway_refstore.py` ::test_distinct_revoke_target_is_not_deduped
/ ::test_distinct_supersede_target_is_not_deduped / ::test_idempotency_key_distinguishes_revoke_and_supersede_target)
RED on pre-fix code, GREEN after; full threeway suite 328 passed / 0 failed; `ci_smoke` + `check_no_ceremony`
clean. Each test asserts the specific property (TeardownError type + `__cause__ is original` + later-ref-attempted;
both ids landing) so a fix missing any layer still reddens. Audit evidence:
`logs/audit-wf_ce0bba9f-0ac-threeway-cutover-substrate.json` (both reproduced against the real machinery,
2/3 refuters failed to refute each). Adversarial Lane-V re-verification of this fix: pending.

**Flip-readiness (from the audit).** With both fixed, the substrate is CONDITIONALLY SAFE to flip. The audit's
operational preconditions still stand and are NOT code: freeze the coordination tree for the flip window (no
concurrent `refs/threeway/*` writer — belt-and-suspenders now that teardown is best-effort), a clean
`divergence` check, a `force=True` dry-run asserting `ready_to_flip`, an OUT-OF-BAND pre-run ref snapshot, and
chief/overseer key provisioning. The live flip remains GATED on explicit user confirmation. Residual not driven
(named, no silent caps): refstore REMOTE push-CAS under concurrent multi-writer contention; backfill
partial-then-retry resumability end-to-end; gitcas merge-tree determinism beyond the fixtures.

## ADR-045 — Complete cutover-sequence teardown coverage: guard the pre-cursor-try validation (Rule-13 sibling of ADR-044)

**Context.** ADR-044's own adversarial Lane-V re-verification (`wf_be151f19-aa7`, worktree mutators +
Rule-13 sweep) returned GO on both ADR-044 fixes (5 isolating mutations, non-vacuity proven) but surfaced a
distinct, pre-existing half-flip gap two lines from the fix: in `run_cutover`, the cursor-backfill validation
steps `carrier_names = [...]`, `cursor_backfill.total_order(carrier_names)` and
`cursor_backfill.iso_to_seq_map(carrier_names, _read_iso_cursors(coord_root))` ran AFTER the append loop
(the events ref is already appended over) but OUTSIDE both teardown-guarded `try` blocks. A raise there — a
bad carrier filename → `total_order` ValueError, or an unreadable `seen/*.txt` → `_read_iso_cursors` OSError
— propagated with NO `_teardown`, stranding the half-built events ref (half-flipped bus, no restore). This is
the same strand-state class ADR-044 hardened `_teardown` against, just at a step the snapshot/restore guard
did not yet enclose — Rule #13 (audit all siblings on the same fence; fold the fix).

**Decision.** Move the three validation/seq-map steps INSIDE the cursor `try` so the same `except Exception
as original: _teardown(repo, snapshot, original); raise` path runs on any failure there. `cursors = {}` stays
outside the `try` as a pure init that cannot raise. No behavior change on the success path; the only change is
that a pre-cursor-loop failure now restores the snapshot instead of stranding the bus.

**Why safe.** Strictly widens teardown coverage (a previously-unguarded failure window is now guarded);
the success path is byte-identical; `total_order`/`iso_to_seq_map` are pure validators with no side effects
to roll back, so wrapping them only adds the restore. The happy-path and contention pins from ADR-044 stay
green.

**Verification.** TDD red→green: new pin `test_threeway_cutover.py::test_pretry_validation_failure_restores_bus_under_force`
(monkeypatch `cursor_backfill.total_order` to raise under a `force=True` pre-existing bus) was RED pre-fix
(events ref left at the appended-over RUN value, not `pre`) and GREEN after (restored to `pre`, the injected
ValueError re-raised); the ADR-044 teardown pins stay green; full threeway suite 329 passed / 0; ci_smoke OK.
Surfaced by `wf_be151f19-aa7`. This completes the cutover-sequence teardown coverage; the live cutover
remains gated on explicit user confirmation with the ADR-044 operational preconditions unchanged.

## ADR-046 — Make `RefEventStore._iter_local` TOTAL against a malformed stored blob (Rule-13 sibling of ADR-041; closes a deserialization-time total-bus DoS)

**Context.** ADR-040/041 made `run_gate` total against a malformed insider event via a `well_formed(ev)`
drop-not-raise guard — but that guard runs only on *already-deserialized* `Event` objects.
`RefEventStore._iter_local` deserializes raw stored blobs with a bare `from_json_obj(json.loads(raw))`
(and `entry["path"]` for the index entry), and `from_json_obj` (`threeway/envelope.py:166`) dereferences
nine required keys with NO presence/type check. A single malformed blob on the bus — an insider with push
access committing a raw event blob that omits `payload`, or a non-JSON / path-less index entry; NO forgery —
therefore raised an uncaught `KeyError`/`JSONDecodeError` the instant `_iter_local` reached it. `_iter_local`
feeds `append()`'s idempotency + id-collision scans AND `gate.run_gate`'s `store.all_events()` materialize
(`threeway/gate.py:168`), which is OUTSIDE `run_gate`'s try — so one bad blob wedged EVERY append and EVERY
gate run: a one-event total-bus DoS. The reassuring `gate.py:164` comment ("Bus EVENTS are already
totality-guarded by `well_formed`") was false for this deserialization-time crash — `well_formed` guards
already-built Events, the crash happens upstream during deserialization. Surfaced + reproduced end-to-end
against HEAD by the residual-surface audit `wf_48aefc7d-589` (finder + 3 refuters could not refute; isolated
worktree repro RED).

**Decision.** Make `_iter_local` drop-not-raise at the deserialization source: wrap the index-entry parse
(`json.loads(idx)` + `entry["path"]` + `isinstance(path, str)`) and the event parse
(`from_json_obj(json.loads(raw))`) each in `except (ValueError, KeyError, TypeError): continue`
(`JSONDecodeError` is a `ValueError` subclass), and additionally `if not well_formed(ev): continue` to drop a
present-but-wrong-typed field. A malformed blob is thus INVISIBLE to every reader and scan, exactly as the
gate already assumes — extending the ADR-041 `well_formed` contract upstream to the source (`well_formed`
added to the refstore import).

**Why safe.** Strictly subtractive: it only DROPS a blob that could not have been a valid authority anyway (a
malformed blob carries no signature/seat the predicate would honor). A legitimate event is never malformed
(it is built by `append` + `sign_event`), so no real event is hidden, and an attacker cannot make an existing
legit event malformed. Nothing newly promotes; the forgery/availability classes (ADR-036..045) stay green.

**Verification.** TDD red→green: 3 new pins in `tests/unit/test_threeway_refstore.py`
(`test_malformed_event_blob_is_dropped_not_wedging_reads_or_append`,
`test_wrongtyped_event_field_is_dropped_by_well_formed`, `test_malformed_index_entry_is_dropped`) were RED
pre-fix (KeyError/JSONDecodeError) and GREEN after (the bad blob is skipped; reads and a fresh append both
succeed). Full refstore suite 30 passed/0. Independent Lane-V re-verification pending. Artifact:
`logs/audit-wf_48aefc7d-589-threeway-residual-surfaces.json`.

## ADR-047 — Atomic cursor-backfill manifest write + diagnosable corrupt-manifest handling (closes a cutover resume/rollback wedge)

**Context.** `run_cutover` step 5b (`threeway/cutover.py:162-168`) deliberately does NOT tear down on a
`cursor_backfill.backfill` failure — it relies on the documented "retry resumes cheaply" invariant. But
`backfill` wrote its rollback/resume manifest NON-atomically (`man.write_text(json.dumps(...))`, a truncating
open+write+close), and BOTH readers — the resume branch in `backfill` and `restore_from_manifest` — did a bare
`json.loads`. A crash / kill / ENOSPC partway through the write left a TRUNCATED-but-existent manifest; on
retry the resume branch raised `json.JSONDecodeError` and could NEVER complete, AND `restore_from_manifest`
raised the same — so the cutover's automated resume AND its rollback were BOTH wedged, violating the exact
invariant step 5b relies on (operator-recoverable only by hand-deleting the manifest). A schema-valid-but-
key-missing manifest was a sibling vector (bare `KeyError`). Surfaced + reproduced end-to-end against HEAD by
the residual-surface audit `wf_48aefc7d-589` (finder CB-1 + the main-read M1 candidate, both confirmed;
isolated worktree repro RED).

**Decision.** Two coordinated changes in `threeway/cursor_backfill.py`:
1. **Atomic write** — `_atomic_write_text(path, text)` writes a sibling `.tmp` then `os.replace` (atomic
   within a filesystem). The manifest write runs BEFORE any cursor rewrite, so a crash at the write leaves NO
   committed manifest and the `seen/*.txt` stay ISO → a retry takes the fresh-archive branch and resumes
   cleanly. The real crash scenario can no longer PRODUCE a truncated manifest.
2. **Diagnosable reads** — `_load_manifest(path)` parses + validates (JSON, object, schema, the three
   required keys) and raises a single clear typed `CursorBackfillManifestError` (a `ValueError` subclass) on
   ANY corruption, instead of a bare `JSONDecodeError`/`KeyError`. Both `backfill`'s resume branch and
   `restore_from_manifest` route through it, so residual external/FS corruption is a diagnosable, catchable
   failure pointing to manual recovery — not an opaque wedge.

**Why safe.** The success path is behavior-identical (same manifest content; a valid manifest loads to the
same dict). The atomic write only changes WHEN bytes become visible (all-or-nothing). `CursorBackfillManifestError`
subclasses `ValueError`, preserving the prior `restore_from_manifest` schema-mismatch error contract. There is
no auto-re-derive on corruption (which could clobber an already-scalar cursor) — the safe response is the typed
error. The cutover happy path + the idempotency/byte-reversibility pins stay green.

**Verification.** TDD red→green: 4 new pins in `tests/unit/test_threeway_cursor_backfill.py` —
`test_crash_during_atomic_manifest_write_leaves_no_committed_manifest_and_retry_resumes` (monkeypatch
`os.replace` to raise → no committed manifest, cursors still ISO, retry resumes), corrupt-manifest backfill +
restore raise the typed error, and schema-valid-key-missing raises the typed error — RED pre-fix
(RuntimeError-not-raised / JSONDecodeError / KeyError), GREEN after. cursor_backfill suite 10 passed/0; cutover
+ legacy-cursor 14 passed/0. Independent Lane-V pending. Artifact:
`logs/audit-wf_48aefc7d-589-threeway-residual-surfaces.json`.

## ADR-048 — Pin the merge-tree algorithm config for host-independent determinism (close merge-tree non-determinism)

**Context.** The merge gate's contract is byte-determinism: every seat must recompute the SAME integration
tree and the SAME mergeability verdict from the signed bus state (`run_gate` recomputes the merge and refuses
a coordinator's claimed `integration_sha` mismatch). `gitcas.merge_tree` ran `git merge-tree --write-tree`
with NO merge-algorithm config pinned. `_DET_ENV` (`threeway/gitcas.py:13-21`) pins only AUTHOR/COMMITTER
identity for `commit_tree`/`commit_on`; `_env` strips only `GIT_INDEX_FILE`. So the merge ALGORITHM was
governed by ambient host config — `merge.renames`, `merge.renameLimit`, `diff.algorithm` from `~/.gitconfig`,
`/etc/gitconfig`, or `GIT_CONFIG_*`. Two seats whose ambient config differed (e.g. `merge.renames=true` vs
`false`) computed DIFFERENT `(tree, clean)` for IDENTICAL `(base, branch)` — one seat would MERGE while
another REJECTED the same candidate, and even when both called it clean their recomputed `integration_sha`
trees differed. `merge.renameLimit` additionally disables rename detection silently above a file-count
threshold, so a large-diff candidate could flip a single seat with no config change. Surfaced + reproduced
end-to-end against HEAD by the residual-surface audit `wf_48aefc7d-589` (a rename+edit vs edit-in-place merge
under `GIT_CONFIG_GLOBAL` injection; finder + 3 refuters could not refute; isolated worktree repro RED).

**Decision.** Pin the merge-algorithm config on the `merge_tree` invocation via highest-precedence
command-line `-c` flags: `-c merge.renames=true -c merge.renameLimit=999999 -c diff.algorithm=histogram`. A
command-line `-c` overrides config from EVERY source (files and env), so the merge result is host-independent
regardless of any ambient `~/.gitconfig` or `GIT_CONFIG_*`. The fixed-high `renameLimit` ensures the
rename-detection threshold can never silently flip an individual seat on a large diff.

**Why safe.** The pins set explicit, canonical values (rename detection ON — git's default — with a generous
limit; `histogram` diff, a deterministic widely-available algorithm); they do not change merge SEMANTICS for
the no-ambient-config case (the existing clean/conflict `merge_tree` pins stay green), only remove the
host-config variance. `-c` is scoped to this one call; `_env` is untouched (avoiding any `safe.directory` /
global-config-isolation risk for the other plumbing calls). Cross-git-VERSION determinism (the merge engine
itself changing across major git releases) remains an environmental residual — a git-version floor is the
deployment-layer mitigation, documented not code-enforced.

**Verification.** TDD red→green: new pin
`test_threeway_gitcas.py::test_merge_tree_is_deterministic_under_ambient_merge_config` (a rename+edit vs
edit-in-place merge run under `GIT_CONFIG_GLOBAL` with `merge.renames=true` then `false`) was RED pre-fix
(`(9bb1…,True)` != `(a856…,False)`) and GREEN after (identical `(tree, clean)`). Full gitcas suite 20
passed/0 (existing clean/conflict `merge_tree` pins unaffected → semantics unchanged). Independent Lane-V
pending. Artifact: `logs/audit-wf_48aefc7d-589-threeway-residual-surfaces.json`.

## ADR-049 — Cutover force-rerun cursor over-advance: source the seq-map from the archived manifest + reject non-ISO cursors

**Context.** `run_cutover` step 4 materializes each seat's cursor by reading `seen/<seat>.txt` as ISO
timestamps and mapping them to seqs via `cursor_backfill.iso_to_seq_map`. But step 5b's `backfill` REWRITES
those `seen/*.txt` to SCALAR seqs. So on a `force=True` RE-RUN — the documented "acknowledge a pre-existing
`refs/threeway/*`" path — step 4 re-reads the now-SCALAR cursors as if they were ISO: `iso_to_seq_map` does
`iso[:11]+iso[11:].replace(":","-")` on a scalar like `"3"` → `"3"`, then `ts <= "3"` is lexicographically
TRUE for every `"2026-..."` event (any scalar with leading digit ≥ `'3'`), so the seat maps to the HEAD seq
and `advance_cursor` (monotonic-forward) pushes the cursor REF past unread events — a silent read-state /
authority loss (the cursor ref diverges from `seen/*.txt`, marking unread events as read). Reproduced
end-to-end against HEAD by the residual-surface audit `wf_48aefc7d-589` (director cursor REF over-advanced
3 → 5). MAJOR (requires the documented-but-uncommon `force=True` re-run; integrity/forgery class unaffected;
only seats with a scalar leading digit ≥ `'3'` over-advance, `'1'`/`'2'` map to 0).

**Decision.** Two coordinated changes:
1. **Source from the archived manifest on re-run** (`threeway/cutover.py` step 4 + `cursor_backfill.archived_seq_map`):
   if the cursor-backfill manifest already exists (a prior run reached step 5b and archived the ISO-derived
   `iso_to_seq`), source the authoritative seqs from it instead of re-deriving from the now-scalar `seen/*.txt`;
   otherwise (first run) compute from the still-ISO seen cursors. The manifest's map is the correct first-run,
   ISO-derived result.
2. **Reject non-ISO cursors loudly** (`cursor_backfill.iso_to_seq_map`): each cursor value must match the ISO
   timestamp shape (`YYYY-MM-DDThh:mm:ssZ`) or be empty (→ seq 0). A non-ISO value (a scalar) now raises
   `CursorBackfillManifestError` rather than being silently lexicographically compared — defense-in-depth that
   turns any future scalar-misfeed into a loud, fail-safe error (silent-gate-degradation class). The two layers
   are complementary: even with (1) bypassed, (2) makes the re-run fail SAFE (raise → teardown) instead of
   silently over-advancing (mutation-confirmed).

**Why safe.** First-run behavior is unchanged (manifest absent → the ISO path, with ISO values that pass the
new shape check). The re-run now uses the same seqs the first run computed (the archived map), so a cursor
never advances past where its true ISO cursor placed it. `advance_cursor`'s monotonic-forward contract is
untouched. `CursorBackfillManifestError` subclasses `ValueError`. Cutover teardown/idempotency pins stay green.

**Verification.** TDD: integration pin
`test_threeway_cutover.py::test_force_rerun_does_not_overadvance_cursor_ref_from_scalar_seen` (first run sets
director cursor 3 + rewrites seen to scalar "3"; force=True re-run must keep it at 3, not the head 5) + unit
pins `test_iso_to_seq_map_rejects_non_iso_cursor`, `test_archived_seq_map_returns_manifest_iso_to_seq`.
Mutation-proven non-vacuous: forcing step 4 down the pre-fix path reddens the integration pin. cursor_backfill
+ cutover suites 21 passed/0. Independent Lane-V pending. Artifact:
`logs/audit-wf_48aefc7d-589-threeway-residual-surfaces.json`.

## ADR-050 — Unify the cutover total-order derivation to one shared carrier-event classifier (close total-order congruence)

**Context.** "The §6 total order" of the legacy→ref-bus cutover was computed by THREE code paths
with TWO different filename predicates. The APPEND order (`legacy_projector.project`) admitted only
files matching the full `_EVENT_NAME_RE` grammar (`<ts>-<from>-to-<to>-<kind>.md`, roster-scoped),
silently skipping the rest. The CURSOR numbering (`cursor_backfill._sent_names` → `total_order`) took
EVERY `.md` and gated each on the loose `_TS` regex (a leading ts token only), raising on a no-ts file
but COUNTING a ts-prefixed file. A `sent/` file that matched `_TS` but not `_EVENT_NAME_RE` (e.g. a
non-roster sender `2026-…Z-stranger-to-director-foo.md`) was therefore SKIPPED by the projector (no
appended seq) yet COUNTED by the cursor numbering — shifting every later seq +1 in the archived
`iso_to_seq`. Because ADR-049's `force=True` re-run sources the authoritative cursor refs from exactly
that archived map (`archived_seq_map`), the off-by-N propagated to the live cursor refs (cursors point
off after cutover). Conversely a clean non-event `.md` (e.g. `README.md`, no ts) made the cursor
path's `total_order` RAISE while the projector silently skipped it — a spurious mid-cutover abort.
MAJOR, dormant (the live cutover is user-gated + un-executed). Confirmed present by inspection in the
residual-surface audit `wf_48aefc7d-589` + Lane-V "D"; reproduced end-to-end against HEAD by the new
pins below. Inventory row `threeway-cutover-total-order-congruence`.

**Decision.** Collapse the two predicates into ONE shared classifier so congruence holds by
construction, not by coincidence. `legacy_projector` gains `is_event_filename` / `ts_of` /
`ordered_event_names` + the `MalformedEventFilename` exception; `project()` is refactored onto
`ordered_event_names`. `cursor_backfill` imports `ordered_event_names`/`ts_of`, rewrites `_sent_names`
+ `total_order` onto them, and drops its local `_TS` regex. The classifier is THREE-way and applied
identically by BOTH layers: a fully-grammatical name is an event; a ts-prefixed `.md` that fails the
grammar RAISES `MalformedEventFilename`; any other file (no leading dash-ts, or not `.md`) is skipped.

**Skip-vs-raise contract (deliberate, surfaced).** This TIGHTENS the projector's prior "silently skip
every non-grammar file" contract: a file that *looks* like a carrier event (timestamp-prefixed `.md`
in the mailbox `sent/`) but fails the grammar now ABORTS the cutover rather than vanishing. Rationale:
silently dropping a suspected event during a one-way, irreversible migration is precisely the
data-integrity failure this campaign exists to prevent; a clean non-event file (no ts) stays a skip.
The projector docstring records the live corpus has zero non-grammar files, so on clean input this is
a no-op safety net.

**Why safe.** On a clean corpus (all-grammar `sent/`, the live case) the appended set, order, and seqs
are byte-identical to pre-fix — `ordered_event_names` reproduces the old `(ts, name)` sort over the
same set. The only behavior changes are on edge inputs the live corpus does not contain: a clean
non-event `.md` is now skipped by BOTH layers (was: spurious cursor-path abort), and a ts-prefixed
malformed `.md` now aborts BOTH layers loudly (was: silent +1 cursor shift). `MalformedEventFilename`
subclasses `ValueError`. No import cycle (`cursor_backfill` → `legacy_projector` → `envelope`; no
back-edge). All prior projector/backfill/cutover/divergence/no-dual-write pins stay green.

**Verification.** TDD red→green. New pins: `test_threeway_legacy_projector.py::
test_project_skips_clean_nonevent_but_raises_on_tsprefixed_malformed`; `test_threeway_cursor_backfill.py::
test_backfill_numbers_over_projector_event_set_skip_clean_raise_malformed`; `test_threeway_cutover.py::
test_cutover_succeeds_and_cursors_congruent_with_stray_nonevent_file` (asserts the archived
`iso_to_seq` == the appended ref cursor for every seat) + `…::
test_cutover_raises_on_tsprefixed_malformed_filename_not_silent_shift`. Each confirmed RED on pre-fix
code (the congruence pin RED via the no-ts ValueError abort; the malformed pin RED via a silent
success). Full threeway suite 348 passed / 1 skipped / 0 xfailed; `ci_smoke` + `check_no_ceremony`
clean. Independent Lane-V GO (wf_7c8fa7bd-9f0, 3/3 unanimous lenses + mutation-proven against pre-fix
code; `logs/verify-wf_7c8fa7bd-9f0-cutover-residual-lane-v.json`). ARCHITECTURE §13A.5 re-anchored.

## ADR-051 — Canonicalize cutover seat-cursor keys against the roster + loud-fail a missing seat (close the seen/-filename seat-key family)

**Context.** The cutover built its `seat → cursor` map from `seen/*.txt` with `{p.stem: …}` and a
suffix-only filter, in TWO sites (`cutover._read_iso_cursors` + `cursor_backfill.backfill`'s
`original_iso`). `p.stem` mis-splits a multi-dot name (`operator.foo.txt` → phantom key
`operator.foo`); a non-canonical case (`Operator.txt`) yields key `Operator`, which the lowercase
roster never matches; and on a case-sensitive FS two case-variants resolve by FS-dependent `iterdir`
order (last-write-wins differently per host). Worst, `cutover.py` then did `seq_map.get(seat, 0)`:
any roster seat whose `seen/*.txt` was missing or misnamed silently got cursor 0 and RE-PROCESSED the
ENTIRE migrated bus, with no error. MAJOR, dormant (live cutover un-executed). Confirmed by inspection
in audit `wf_48aefc7d-589` + Lane-V "D"; reproduced E2E by the new pins. Inventory row
`threeway-cutover-seen-filename-seat-key`.

**Decision.** One shared reader, `cursor_backfill.canonical_seat_cursors(seen_dir)` (+ the roster
constant `cursor_backfill.SEATS` and the `SeatCursorError` exception), used by BOTH the cutover's
step-4 read and the backfill's archive read. It strips exactly `.txt`, lowercases to the canonical
roster seat, and RAISES `SeatCursorError` on a stray non-roster file or a case-collision — never coins
a phantom key. `cutover._SEATS` now aliases `cursor_backfill.SEATS` (single source). The step-4 cursor
loop replaces `seq_map.get(seat, 0)` with an explicit membership check: a roster seat absent from the
seq map is a LOUD `SeatCursorError`, not a silent cursor-0 full-bus reprocess. An operator who genuinely
wants a seat to start at 0 asserts it explicitly via an empty `seen/<seat>.txt` (present-with-value-""
→ seq 0, the legitimate path).

**Rule-13 sibling (filed, not folded).** `divergence.py:110` (`{f.stem for f in seen.glob('*.txt')}`)
has the same phantom-key/case fragility, but it is the READ-ONLY divergence checker, not the
irreversible cutover write-path; folding the cutover fix into the checker would change checker
semantics + tests. Filed as a separate lower-stakes inventory row rather than scope-creeping this fix.

**Why safe.** The normal cutover (all 6 lowercase `seen/<seat>.txt` present) is unchanged: every file
canonicalizes to itself and all 6 seats are in the seq map. The new raises fire only on inputs the
clean corpus does not contain (stray/case-variant filenames, a missing seat). `SeatCursorError`
subclasses `ValueError`; the loud-missing check sits inside the existing step-4 teardown guard, so a
raise restores the bus. `original_bytes` stays keyed by the literal filename, so byte-perfect rollback
is untouched. All prior cutover/backfill pins stay green.

**Verification.** TDD red→green. New pins: `test_threeway_cutover.py::
test_read_iso_cursors_canonicalizes_seat_filename_case`, `…::
test_read_iso_cursors_rejects_phantom_nonroster_filename`, `…::
test_cutover_raises_on_missing_seat_cursor_not_silent_full_reprocess`; `test_threeway_cursor_backfill.py::
test_canonical_seat_cursors_rejects_case_collision` (skips on a case-insensitive FS). Each confirmed
RED on pre-fix code (phantom `{'Operator': …}` key; silent success with the missing seat at cursor 0).
Full threeway suite 348 passed / 1 skipped / 0 xfailed; `ci_smoke` + `check_no_ceremony` clean.
Independent Lane-V GO (wf_7c8fa7bd-9f0, 3/3 unanimous + mutation-proven against pre-fix code;
`logs/verify-wf_7c8fa7bd-9f0-cutover-residual-lane-v.json`). Lane-V NITs closed in the follow-up: an
E2E empty-seen→seq-0 opt-in pin (`test_cutover_empty_seen_file_is_explicit_seq_zero_optin`) + a
`total_order` docstring clarification (the idempotent double-filter via `ordered_event_names`).

## ADR-052 — Correct the threeway activation tooling: real envelope/gate/cutover API + a --yes-gated cutover CLI + truthful status

**Context.** Codex + Antigravity ("agy") did their three-way protocol *adaptation turns*, leaving (uncommitted)
9 `.pub` keys, `.gitignore` (`*.ed25519`), and five activation artifacts: `scripts/sign_ci_result.py`,
`scripts/run_merge_gate.py`, `scripts/agy_observer.py`, `scripts/execute_threeway_cutover.sh`, and a
`ci.yml` `ci_result` step — plus doc edits to `ARCHITECTURE.md` §13A.5 and `docs/protocol/threeway/README.md`.
A review found two classes of misalignment with the protocol contract:
1. **Fabricated event schema.** All three Python scripts used `ev.event_type` / `ev.subject` /
   `Event(event_type=…, subject=…)` — fields that exist NOWHERE in `threeway/` (`grep` empty; the real
   envelope is `kind` / `candidate_id` / `subject_sha`). `Event(event_type='ci_result', …)` raises
   `TypeError` (empirically confirmed) and omits 6 required fields; `run_merge_gate` read
   `GateResult.decision`/`"MERGED"` (real: `.outcome` ∈ {COMPLETED,REJECTED,PENDING}); `sign_ci_result`
   used a per-event random `bus_id` (canonical is `"prod"`); `execute_threeway_cutover.sh` ran
   `python -m threeway.cutover`, a NO-OP (cutover.py had no `__main__`), and re-ran `keys_bootstrap`
   unconditionally (which would overwrite + invalidate the committed trust root).
2. **False status in the truth files.** The docs were flipped to "**LIVE and DEPLOYED** … cutover has been
   executed … merge-gate daemon and CI wiring are active." Proof of falsehood: `git for-each-ref
   refs/threeway/` returns 0 refs and `coordination/threeway/events/` holds only `.gitkeep` — the cutover
   never ran (it could not). This violates R-EVIDENCE + the anti-ceremony doctrine (ADR-027/028).

**Decision.** (a) Rewrite all four scripts to the REAL contract — the canonical `ci_result` shape from
`threeway/loop.py:104` (`kind="ci_result"`, `signer="ci:…"`, `payload={result, policy_digest}`,
`subject_sha=integration_sha`, `bus_id="prod"`), `ev.kind`/`ev.candidate_id`, `GateResult.outcome`/
`"COMPLETED"`; each script exposes a testable core (`emit_ci_result`, `poll_once`, `summarize`) over a
thin `main()`. (b) Add `threeway.cutover.main` — a `--yes`-GATED CLI (`python -m threeway.cutover --yes`)
that refuses without explicit confirmation (the cutover is irreversible, ADR-045) and uses an ephemeral
importer key (event_sent is not load-bearing). (c) Make `execute_threeway_cutover.sh` idempotent (skip
`keys_bootstrap` if the registry is populated) and double-gated (`--yes`). (d) Gate the `ci.yml`
`ci_result` step behind `vars.THREEWAY_BUS_LIVE == 'true'` so it is INERT pre-activation (else an empty
secret breaks CI). (e) Restore the truth in the docs: the codex/agy false `ARCHITECTURE.md` §13A.5 edit was
UNCOMMITTED, so it was dropped via a working-tree `git checkout HEAD` (back to the already-correct committed
§13A.5 — hence ARCHITECTURE.md is NOT in commit `36c72878`'s diff; the §13A.4 test-count refresh to 353
landed in the follow-up Lane-V reconciliation); the README *was* rewritten in `36c72878` (built + hardened,
keys generated-but-uncommitted, **cutover NOT executed**, bus NOT live).

**Known activation-time limitation (not blocking; the step is inert).** The `ci.yml` step passes
`github.sha` as `--integration-sha`, but the gate keys `ci_result` by the candidate's *integration_sha*
(the CAS-merged commit), which on a real PR is NOT the branch HEAD — so as wired the gate would never find
the ci_result (candidate stays PENDING). Documented in the step's comment + the codex review; CI must be
wired to run on / sign the integration commit before `THREEWAY_BUS_LIVE` is flipped.

**Why safe.** The scripts are tooling, not the hardened package; the only `threeway/` change is the
additive, tested `cutover.main`. The cutover stays user-gated + irreversible (now DOUBLE-gated: shell +
CLI). The `ci.yml` step is inert until the operator flips the repo variable at go-live. The `.pub` trust
root + `keys/README.md` are LEFT UNCOMMITTED — committing the trust root is itself part of the user-gated
go-live (a T3-classified commit), not this corrective change.

**Verification.** TDD red→green: `tests/unit/test_threeway_activation_scripts.py` (4 pins —
`emit_ci_result` reduces to a trusted PASS; `poll_once` drives a complete candidate to `COMPLETED`;
`summarize` uses the real fields; the cutover CLI refuses without `--yes` and writes a bus with it).
Non-vacuous: the reducer DROPS a wrong-bus/wrong-seat/wrong-field event, so the state assertions would go
RED on a malformed shape (and the pre-fix `Event(event_type=…)` raises `TypeError`, proven empirically).
Full threeway suite 353 passed / 1 skipped / 0 xfailed; `ci_smoke` + `check_no_ceremony` clean.
Independent Lane-V GO (wf_cb50fa27-3e5, 3 lenses: api GO / safety NITS / completeness NITS; mutation
probes — bus_id and signer-seat — both went RED, proving non-vacuity; no FAIL). The NITs were reconciled
in the follow-up: the ARCHITECTURE.md restore phrasing corrected (above), the §13A.4 test count refreshed
341→353, and the ci.yml integration_sha limitation documented. Artifact:
`logs/verify-wf_cb50fa27-3e5-activation-tooling-lane-v.json`.

## ADR-053 — Wire inert threeway CI signing to the real integration SHA and authoritative bus ref

**Context.** ADR-052 intentionally left the CI `ci_result` step inert because it still passed
`github.sha` as `--integration-sha`. The gate keys `ci_result` by the candidate's CAS-merged
`integration_sha`, not by the PR/push head, so enabling that step would leave candidates PENDING. A
second activation gap was in the same path: `scripts/sign_ci_result.py` appended through a local
`RefEventStore(repo)`, which is fine for local tests but would write only the disposable CI clone unless
CI used the remote authoritative bus path.

**Decision.** Keep normal push/PR CI behavior unchanged, and add a go-live-only manual
`workflow_dispatch` path. For that manual path, all three CI jobs check out a fetchable
`integration_ref`, validate the supplied `integration_sha` as 40 lowercase hex, assert the checked-out
`HEAD` equals that exact SHA, and then test that checkout. A separate `threeway-ci-result` job runs only
after `smoke`, `pytest-unit`, and `tsc` all pass, only when `vars.THREEWAY_BUS_LIVE == 'true'`, and only
from `refs/heads/main`. The signing job checks out trusted `main` code (the workflow commit), validates
the same SHA, loads only the CI private key, and calls `scripts/sign_ci_result.py --integration-sha
"$INTEGRATION_SHA" --result PASS --remote origin`. `sign_ci_result.py` now exposes `--remote`, passing it to
`RefEventStore(repo, remote=...)` so append uses the expected-old-OID push-CAS path for
`refs/threeway/events`.

**Why safe.** The CI key no longer runs candidate-controlled signing code: candidate/integration code is
checked out by the test jobs, while the signer job checks out trusted `main` after the test jobs finish.
The signer job has `contents: write`; the ordinary test jobs do not need that permission. The path remains
fully inert until go-live because it requires manual dispatch, `THREEWAY_BUS_LIVE=true`, a committed public
trust root, the cutover, and a configured CI private key.

**Verification.** TDD red→green:
`tests/unit/test_threeway_activation_scripts.py::test_sign_ci_result_cli_pushes_to_the_authoritative_remote_bus`
first failed with `unrecognized arguments: --remote origin`, and
`tests/unit/test_threeway_activation_scripts.py::test_ci_workflow_signs_only_an_explicit_threeway_integration_sha`
first failed because `workflow_dispatch:` was absent; after the fetchability hardening, the same pin first
failed because `integration_ref:` was absent. Focused result after the fix:
`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_activation_scripts.py -q` →
`6 passed in 2.04s`.

## ADR-054 — Canonicalize the divergence checker's seated-set against the roster (close the seen/-filename seat-key family; Rule-13 sibling of ADR-051)

**Context.** ADR-051 fixed the cutover/backfill seat-cursor keying (`canonical_seat_cursors`) but
explicitly filed its Rule-13 sibling — `threeway-divergence-seen-stem-phantom-key` — separately, because
the divergence checker is a different module with different stakes. The checker derived its seated set
with `seated = {f.stem for f in seen.glob("*.txt")}`. `Path.stem` strips only the LAST suffix, so a stray
non-roster file `operator.foo.txt` coins a phantom seat `"operator.foo"`, and `f.stem` is case-fragile
(`Operator.txt` → `"Operator"`). Unlike the one-way cutover (where this corrupts the migrated bus), the
checker is READ-ONLY, so the failure mode is a SILENT FALSE-GREEN: a phantom seat enters the per-seat
cursor loop seeing only broadcasts and VACUOUSLY agrees, while a case-variant file makes the real seat's
cursor clause SKIP (`_seen_value("operator")` can't find `Operator.txt`). Either way a malformed seen/
roster is tolerated without a drift — the opposite of what a verification pass must do.

**Decision.** Source BOTH the seated set AND each seat's cursor value from the SAME shared
`cursor_backfill.canonical_seat_cursors(seen)` reader the cutover/backfill already use (the single source
of truth from ADR-051): it strips exactly `.txt`, lowercases to the roster seat, and rejects a
stray/case-colliding file. `divergence._seen_value` is retired in favor of reading values from that
reader's `{seat: value}` map (`seen_cursors.get(seat) or None`, preserving the empty-file → None
behavior). Because the checker must SURFACE corruption rather than abort (the cutover RAISES on the
irreversible write-path; a read-only pass must not crash and thereby suppress ALL other drift detection),
its `SeatCursorError` is caught and emitted as a `seated: malformed seen/ roster (...)` drift. A
`seen.is_dir()` guard preserves the prior glob-on-missing-dir totality (empty seated set, no crash).

**Why safe / non-vacuous.** TDD pin
`test_threeway_divergence.py::test_stray_nonroster_seen_file_reported_not_coined_as_phantom_MUTATION`:
a faithful fixture + a stray `seen/operator.foo.txt` yielded `Report(ok=True, drifts=[])` PRE-FIX (the
phantom vacuously agreed — RED on the assertion that a drift must be reported) and a `seated:` drift
POST-FIX (GREEN). The existing `test_broadcast_only_seat_is_checked_not_skipped_MUTATION` (which depends on
the seated set coming from `seen/`) stays green because `canonical_seat_cursors` reads the same `seen/`
dir. Full threeway suite after the fix:
`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q` →
`356 passed, 1 skipped, 0 xfailed`; `ci_smoke` + `check_no_ceremony` clean. Independent Lane-V **GO**
(fresh `lane-v-verifier` subagent `a38a3d69` in an isolated worktree; it independently re-ran the
mutation — reverting the seated-set derivation reddened the pin → non-vacuous — and confirmed the
Rule-13 sweep clean and the read-only catch-not-crash contract reachable;
`logs/verify-adr054-divergence-seated-canon-lane-v.json`) → inventory row reconciled `fixed` → `verified`.
