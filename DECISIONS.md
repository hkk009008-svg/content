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
  skill). The structural gate change (gate executes pins) + the product-oracle wave-close
  requirement are RECOMMENDED — routed to a Pair-B director (gate/CI scripts are not
  coordinator-authorable) and PENDING user-principal ratification of the policy parts.
  Evidence: `logs/discovery-wf_26a5abf2-3bb.json` (read-only RCA, 8 agents, adversarially
  stressed; verdict "partially-just-so").
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
- **Cross-refs:** `logs/discovery-wf_26a5abf2-3bb.json`; `scripts/wave_gate_check.py` (FIX-1
  target); `scripts/ci_smoke.py`; `face_validator_gate.py` + `performance/identity_gate.py`
  (the real product oracles); `docs/superpowers/specs/2026-06-14-program-hardening-roadmap-design.md`
  §5/§7 (acceptance bar + the spec↔implementation gap); `docs/REMEDIATION-INVENTORY.md`.
  Origin: user-principal critique 2026-06-15 → coordinator Session-12 RCA `wf_26a5abf2-3bb`.
  Implementation routing + policy ratification PENDING.
