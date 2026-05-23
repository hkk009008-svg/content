# Strategic Review — 2026-05-24

**Author:** Incoming leadership, end of first walk-through
**Audience:** Engineering team + future directors
**Status:** Active. Decisions become ADRs as they land in
[`DECISIONS.md`](../DECISIONS.md).

---

## Executive verdict

The codebase is **structurally sound but operationally immature**. The
post-pivot architecture (single web entry, predicate-poll gates,
ARCHITECTURE.md truth file) is the work of prior directors I will keep
and build on. The work I will not keep: silent failure patterns,
ad-hoc observability, untested critical paths, and a vendor surface
that's grown by accretion rather than by deliberate choice.

This review is precise and direct. Where I disagree with prior
direction, I say so by name. Where prior direction was right, I name
that too — credit and critique are both useful signal.

---

## What's working — keep

These are decisions I am explicitly NOT reversing. The reasoning matters
because the next set of changes shouldn't break them.

| Decision | Why I keep it |
|---|---|
| **Single web entry point** | Eliminated 3000 LOC of CLI duplication. Simpler mental model. ADR-001. |
| **Predicate-poll gates** | Operator approvals survive crashes and SSE disconnects because state lives on disk, not in event channels. This is the single best architectural choice in the codebase. ADR-002. |
| **ARCHITECTURE.md as truth source** | Three preambles drifting against each other was a real pathology. The truth-vs-process split is correct. ADR-008. |
| **Identity singleton via 4-way alias** | One model load, shared rolling-stats across contexts. The lazy import keeping `phase_c_vision` out of the import graph is elegant. ADR-004. |
| **PipelineContext implements dict API** | Pragmatic. Legacy code keeps working while new code gets type hints. ADR-003. |
| **Parallel quorum LLM (not fallback)** | Quality > speed for creative LLM calls. Worth the 2× cost. ADR-005. |
| **PuLID + identity firewall (HC1)** | Forcing the LLM to never describe faces is the right separation of concerns — identity from refs, not from words. |
| **Operator review gates (concept)** | The four gates exist for a reason. Quality is non-negotiable in this domain. (UX is a different matter — see below.) |

---

## What needs to change — prioritized

### P0 — Ship-blocking risks

#### P0-1 — Test coverage is uneven, with two real load-bearing gaps

**Director-correction (2026-05-24):** My initial draft of this section
claimed "only one test file at unit level" and "zero unit tests" for
several modules. That was wrong — I trusted session memory of one
file's pytest output instead of running `ls tests/unit/`. I committed
the exact failure mode this handoff is written to prevent. Ownership:
mine. What follows is the audited reality.

**Current state (verified):** `tests/unit/` contains 24 test files.
Baseline is **478 pass / 3 skip / 0 fail** after the `fix(tests):`
baseline-hygiene commit. The 3 skips are documented `@unittest.skip`
in `test_project_persistence.py` (mock drift, not behavior bugs).

**Audited status of the original priority list:**

| Pri | Module | Audited status | Action |
|---|---|---|---|
| 1 | `cinema/review/controller.py` (`approve_take`, `_gate_satisfied`, `_project_gate_status`, `_resolve_motion_source` chain walk) | `test_cross_controller.py` (10 tests, all green) covers cross-controller wiring + `_candidate_take` 1 of 4 branches + `_gate_satisfied` 5 of 13 cases partially. **`approve_take` (all 10 branches), `_project_gate_status` (2 cases), the PERFORMANCE_REVIEW gate predicate (5 branches), and `_resolve_motion_source` visited-set protection are entirely untested.** | **EXTEND** `test_cross_controller.py` in place (preserve plain-functions + `_TESTS` registry convention). ~26 new tests. HANDOFF Session 2 reframed Create → Audit+Extend. |
| 2 | `workflow_selector.classify_shot_type` + `WORKFLOW_TEMPLATES` + `MOTION_FIDELITY_FLOORS` + `get_adaptive_pulid_weight` | `test_workflow_selector.py` (34 tests, all green) covers shape + defaults + ranges + **4 of 48 keywords (8%)**. `get_adaptive_pulid_weight` and `MOTION_FIDELITY_FLOORS` subset check entirely untested. | **EXTEND** with ~63 new cases (parametrized 48-keyword sweep + 4 boost paths + subset check + target_api validity). HANDOFF Session 3 reframed. |
| 3 | `face_validator_gate.should_halt` + `score_candidate` + `needs_regenerate` | **Strategic review claim correct — uncovered.** Cross-grep across all of `tests/` returns zero hits for any of the three functions. `test_quality_max_overlay.py` tests adjacent territory (overlay schema validation), not the halt rule. | **NEW FILE** `tests/unit/test_face_validator_gate.py` with ~22 cases (`should_halt` 9 cases, `score_candidate` 8 cases, `needs_regenerate` 5 cases). **Not currently in the 6-session plan** — this is the strongest follow-up candidate after the 6 sessions land. |
| 4 | `domain.scene_decomposer._coerce_to_valid_keys` + schema validation | Not audited in this pass. | Audit before next strategic-review cycle. |
| 5 | `lip_sync._sync_gate_settings` + cascade decision logic | Not audited in this pass. | Audit before next strategic-review cycle. |

**Additional gap surfaced during audit (not in original priority list):**

| Module | Audited status | Action |
|---|---|---|
| `cost_tracker.CostTracker.record_api_call` + budget gate (`would_exceed`, `is_over_budget`, `spent_usd` accumulator) | `test_cost_tracker.py` exists at 458 LOC with 33 passing tests — but `record_api_call` itself is **never directly tested**; existing tests cover `log_llm`, `get_summary`, pricing tables instead. Budget gate entirely untested. | **EXTEND** with ~11 cases (`TestRecordAPICall` + `TestBudgetGate`). HANDOFF Session 5 reframed (silent-except sweep also turned out tiny — 2 instances repo-wide vs the implied "many"). |

**Positive findings worth recording:**

- `cost_tracker.py` has **zero** silent-except patterns. Repo-wide
  silent-except count is **2** (vs the "many" the original P0-3 review
  implied). The pattern that hid the Bundle-A 1.3 cost-tracker bug is
  largely already cleaned up.
- All 4 audited test files use SQLite tempdirs / monkeypatching cleanly;
  no write-contention risk.
- Existing tests follow consistent conventions (`pytest.approx` for
  floats, parametrized cross-products, descriptive class names) — a
  scaffold worth preserving and extending rather than re-inventing.

**Target:** Reframed Sessions 2 + 3 + 5 (Audit+Extend) close the
highest-leverage gaps without duplicating existing coverage. Priority 3
(`face_validator_gate`) is the largest remaining single uncovered gap
and should be the first follow-up after the 6 sessions land.

#### P0-2 — No CI / no automated verification

**Current state:** No `.github/workflows/`. Pytest + `tsc --noEmit` exist
as commands but only run when manually invoked. Bundle commits this
session were verified by hand each time.

**Risk:** Doc drift (which we just spent days fixing) was preventable
with an automated smoke check. So is the next equivalent.

**Action:** Add `.github/workflows/ci.yml` with three jobs:

1. **Smoke:** runs ARCHITECTURE.md §15 smoke block. Fails fast if singletons or `get_project_setting` break.
2. **Pytest unit:** `tests/unit/` with `-q --tb=short`. Skip integration tests (no credentials).
3. **TypeScript:** `cd web && npx tsc --noEmit`.

Run on every push + pull request. Block merges on failure.

**Add to OPERATIONS.md §7 once CI exists.**

#### P0-3 — Cost tracking remains fragile

**Bundle A 1.3 fixed one silent failure** (`ShotController.cost_tracker`
AttributeError swallowed). But the pattern that hid it — `try/except
AttributeError: pass` around cost-tracking calls — is a code smell I do
not accept.

**Action:** Audit every `record_api_call` site in the codebase. Replace
silent try/except with explicit None checks + `logger.warning` (cost
tracking is best-effort, but invisibility is not best-effort, it's
broken). Then audit other instances of the `try/except: pass` pattern.

```bash
# starter audit
grep -rn "except.*:\s*pass" --include="*.py" /Users/hyungkoookkim/Content
```

Any match that isn't documented as intentional should be reviewed.

---

### P1 — Quality risks

#### P1-1 — Observability is `print()` and nothing else

Every error path emits `print(f"[ENGINE] something happened: {e}")`. No
structured logging, no metrics, no correlation IDs across the
multi-minute pipeline runs. Debugging a stuck shot means scrolling
stdout and hoping the operator captured it.

For a pipeline with:
- 17 cloud API providers
- 9-engine video cascade
- 4-engine lipsync cascades (× 2 modes)
- 3-path performance capture autopilot
- Per-shot retry / regenerate / restart / correct workflows

Print-based observability is below the threshold of "operable in
production."

**Action (P1.1a):** Replace `print(...)` with Python `logging` calls.
Single JSON formatter (one log line per event, tagged with `pid`,
`scene_id`, `shot_id`, `engine`, `latency_ms`, `cost_usd`). Configure
to file + stdout. ~3 sessions of work for the full repo; can be done
gradually.

**Action (P1.1b):** Emit per-shot timing + cost metrics as a parsed
event the UI can render. Today the operator sees "Generating motion…"
for 8 minutes with no indication of which engine is being tried or why.

#### P1-2 — Pipeline orchestrator is still monolithic

`cinema_pipeline.py` is 1011 LOC, one class. Prior directors did
substantial extraction work (ShotController, ReviewController,
CheckpointStore, ThreadedLifecycle — all good). What's left:

- `_assemble_final` (the stitch/color-grade/loudnorm/mix path)
- `_ensure_scene_audio` + `_ensure_bgm`
- `_rebuild_review_clips`
- The big `generate()` method itself (~220 LOC)

**Action:** Continue the extraction. `assembly/` package with
`final_assembler.py` (stitch + color + loudnorm + mix) and
`scene_audio.py` (ensure-scene-audio + BGM). `generate()` becomes a
12-step list of named phase calls + gate calls. Estimate: 2 sessions.

This is **not urgent** but it removes a refactor liability — if anyone
needs to swap stitch logic, find it in the 1011-line file is painful.

#### P1-3 — Project JSON has no schema validation

The Python side reads `project.json` as a raw `dict`. TypeScript
defines `Shot`, `Scene`, `Project` types in `web/src/types/project.ts`
but Python doesn't enforce them. A typo in `approved_keyframe_take_id`
during a mutation silently breaks the gate predicate and the operator
sees "REVIEW gate stuck" with no explanation.

**Action:** Add Pydantic models for `Shot`, `Scene`, `Project`,
`GlobalSettings`. Validate on `load_project` and `mutate_project`.
This is a meaningful refactor (touches every domain/ caller) but pays
back permanently:

- Type-checked field access (no more `(shot as any)`).
- Migration path on schema changes is explicit (Pydantic validators).
- The Python types become the source of truth; TypeScript can generate
  from Pydantic JSON Schema export.

**Estimate:** 2-3 sessions. Worth it.

#### P1-4 — Frontend has no error boundaries

Single throw in `usePipelineState` event router crashes the entire UI.
After a 20-minute run.

**Action:** React error boundaries at `EditorialShell`, `PipelineLayout`,
`DirectorsConsole`. ~30 LOC each, ~1 hour total. Should have happened
already.

#### P1-5 — Doc-claim verification tooling

**Context.** ADR-013 (codified 2026-05-24 after this director shipped
a load-bearing inventory error into this very strategic review)
introduces three mechanical rules for verifying factual claims in
docs: no inventory claim without producing command; scoped output
stays scoped; pre-commit trip-wire on strategic docs. Those rules
close most of the surface. Two structural gaps remain that need tooling.

**Action.**

1. **Doc-claim CI lint.** A script (`scripts/lint_doc_claims.py`)
   that scans strategic docs (ARCHITECTURE.md, STRATEGIC_REVIEW-*.md,
   HANDOFF-*.md, README.md, DECISIONS.md, OPERATIONS.md) for
   inventory-shaped patterns ("N test files," "X LOC," "Y functions,"
   "Z routes") and validates each against current code state. Wired
   into the Session-1 CI workflow. A doc that says "N test files"
   must reconcile against `ls tests/unit/ | wc -l`; a doc that says
   "X.py is N lines" must reconcile against `wc -l X.py`. Mismatches
   fail the CI job. Estimate: 1-2 sessions; start with a
   pattern-based MVP, expand later.

2. **Closing-verification subagent.** Before any
   strategic-voice doc lands on `main`, dispatch a fresh subagent
   whose only job is to read the committed file and falsify every
   factual claim against current code. The subagent has no
   conversation context — it walks the doc cold, runs verifying
   commands for each claim, and reports MATCHES / DRIFT. ~5 minute
   cost per doc commit; catches exactly the class of error that
   ADR-013 was written for. Estimate: 1 session to write the
   subagent prompt template + integrate into the doc-commit
   workflow.

**Why.** The 2026-05-24 inventory error (claiming "1 test file" when
there were 24) survived into both STRATEGIC_REVIEW and HANDOFF
because neither tool existed. The mechanical rules in ADR-013 are
the *floor* — they make the failure visible to the author at commit
time. This tooling is the *ceiling* — it catches the failures the
author missed despite the rules. Both layers are needed; humans
forget rules under writing-momentum.

**Decision authority.** Engineering can build both unilaterally.
Recommend pairing Tool 1 (doc-claim lint) with Session 1 (CI
workflow) so it lands in the same `.github/workflows/ci.yml`. Tool 2
(closing-verification subagent) can ride alongside or come later.

---

### P2 — Cost / efficiency

#### P2-1 — `competitive_generation: True` default doubles LLM cost invisibly

Per ADR-005, parallel quorum LLM calls run all configured providers in
parallel. With `competitive_generation: True` as the default in
`make_project()`, every LLM call costs ~2× because both Anthropic and
OpenAI run. Operators rarely realize this.

**Options:**

| Choice | Impact |
|---|---|
| **A. Default to False.** Single-model fast path. Operators opt into competitive mode for quality. | Cost drops, but creative output gets more variable. May not be the right default for a max-quality tool. |
| **B. Keep True, surface cost prominently in UI.** Show "you're running competitive mode — this is doubling LLM cost" in MaxQualityTierSection. | No behavior change, informed consent. |
| **C. Default to False for Production tier, True for Max tier.** Aligned with operator's existing tier intent. | Most pragmatic. Recommended. |

**Decision authority:** product call. I lean C. Either way, this should
not be invisible.

#### P2-2 — RunPod pod idle billing has no guardrails

Pod is billed per second. The pipeline assumes the pod is reachable; it
does not start/stop pods. An operator who forgets to stop their pod
after a session pays for idle time.

**Action:** Document explicitly in OPERATIONS.md §5 (now done) +
consider adding a `POST /api/pod/sleep` endpoint that calls RunPod's
API to stop the pod after `_running_pipelines` is empty for N minutes.

Lower priority; pod operations are the operator's responsibility, but
the system can be more helpful.

#### P2-3 — Lipsync cascade silently falls through to "best of bad"

When all 4 lipsync overlay engines score below the SyncNet threshold,
the cascade restores the highest-scored stash and returns it as the
final output. The operator sees a lipsync result and doesn't know it
failed every engine.

**Action:** Surface the cascade outcome in the take's metadata —
`{engine: "musetalk", syncnet_score: 0.58, fallback: true}`. UI shows
"⚠ Fallback (score 0.58 below 0.65 threshold)" instead of presenting
the take as approved-quality. Same pattern applies to the video
generation cascade (which engine fired, what was the cost, was a
fallback hit).

---

### P3 — Code health

#### P3-1 — Concurrency hygiene is inconsistent

Some module-global mutable dicts have locks (`_cores_lock`,
`_lora_training_lock`, `_WORKFLOW_LOCK`, `_NODE_AVAILABILITY_LOCK`).
Others don't (`_running_pipelines`, `_progress_queues`). The latter
rely on GIL atomicity of single dict ops — which is true, but only for
single ops, not for compound check-then-set patterns.

**Action:** Audit all module-global dicts. Either add a lock or
document why GIL-atomic is sufficient (in a comment, not in tribal
knowledge). Pattern: `# safe: only read by /api/cancel, only written
once by run_pipeline, no compound check-then-set anywhere.`

#### P3-2 — `_default_progress` is still in `cinema_pipeline.py` despite no CLI

The CLI is gone (ADR-001). `_default_progress` (`cinema_pipeline.py:334-338`)
exists to print to stdout when no callback is set — that was the CLI's
path. Today every caller passes a callback. The fallback is dead code
in the strict sense.

**Action:** Delete or repurpose as a debug helper. Low priority.

#### P3-3 — `domain/scene_decomposer.py` has duplicate validators

`decompose_scene` and `competitive_decompose_scene` share a system
prompt (extracted in Bundle B 2.3) but the per-shot output sanitizer
(`_coerce_to_valid_keys` etc.) is also called twice with subtly
different shapes. Worth one careful audit pass to confirm the
sanitizers match.

#### P3-4 — Some root-level Python files have unclear purpose

| File | Purpose | Action |
|---|---|---|
| `cleanup.py` | Cleans up project temp files | Confirm called from web_server; otherwise audit |
| `reporter.py` | 2.1k unknown | Audit — if dead, delete |
| `generate_characters.py` | 2.7k | Confirm a live tool, otherwise delete |
| `web_research.py`, `research_engine.py` | Live (used by scene_decomposer + style_director) | Document in ARCHITECTURE.md package layout |
| `web_services.py` | Live (used by web_server.py) | Same |
| `coherence_analyzer.py` | Live (used by ShotController.diagnose_clip) | Same |

---

### P4 — Strategic / open questions

#### P4-1 — Vendor sprawl

The codebase touches: Anthropic, OpenAI, Gemini, Mistral (just removed),
FAL (many sub-providers), Kling, Sora, Veo, LTX, Runway, Seedance,
Hedra, Viggle, ElevenLabs, Cartesia, Suno, Stability, Tavily,
Firecrawl, Pexels, RunPod, plus DeepFace/GhostFaceNet model artifacts.

**~22 distinct API surfaces.** Each is:
- A failure mode
- An auth credential to manage
- A billing line item
- A potential API-deprecation event

The cascade pattern papers over vendor risk by routing around outages,
but it doesn't solve cost variance or the operational burden of 22
relationships.

**Open question for product:** what's the minimum viable vendor set?
Can we get to ≤10 by accepting:
- One LLM family (Anthropic) + one fallback (OpenAI) — drop Gemini/Mistral
- Two video providers (Kling Native + one premium fallback like Runway)
- One TTS (ElevenLabs)
- One BGM (FAL Stable Audio)
- One performance capture (Act-One or LivePortrait, not all three)
- One lipsync (Hedra for generation OR sync.so for overlay, not all 8 engines)

This is a **product question**, not an engineering question. Engineering
can implement either world. The current world is "every provider
available" — that has development cost (each adapter is ~150 LOC of
maintenance liability).

#### P4-2 — Single-process, single-operator architecture

`web_server.py` holds in-memory state. One project at a time per worker
thread. No horizontal scaling. For a 10+ minute pipeline, this means
one operator drives one project at a time.

**If this is the deliberate product shape, fine** — it's a power tool
for a small operator team, not a SaaS. Document this clearly in README.

**If multi-user is anticipated**, this is a redesign:
- State out of memory into Redis or a database
- Worker pool with queue
- Project locking via Redis instead of filelock
- Distinct pod-pool sizing per workload class

**Open question for product.** I lean toward "stay single-user" until
demand changes. The complexity cost of multi-user is large.

#### P4-3 — 4-gate review fatigue

For a 20-shot project, the operator decides:
- 20× plan approvals
- 20× keyframe approvals (× retries when rejected)
- ≤20× performance approvals (skipped when shots route to SKIP)
- 20× final approvals

That's 60–80+ decisions per project. The same workflow that protects
quality also creates review fatigue.

**Options:**

| Choice | Impact |
|---|---|
| **A. Add "auto-approve when confidence ≥ X"** path. ChiefDirector signals confidence in MODIFIED → still requires review; APPROVED + high identity score → auto-advances. | Removes friction on the easy 80%, focuses operator attention on the hard 20%. |
| **B. Add bulk-approve UI** — "approve all plans with no Chief Director violations." | UI work, no semantic change. |
| **C. Keep current model** — every shot reviewed individually. | Highest quality discipline, worst UX. |

**Decision authority:** product call. I lean A + B.

#### P4-4 — No A/B testing / experiment tracking

The codebase has ~25 tunable quality knobs (FreeU b1/b2/s1/s2, SLG
scale + layers, DetailDaemon amount, SUPIR steps, PuLID weight + delta,
halt thresholds × 3, regenerate floor, motion floor per shot type ×
6, identity strictness, etc.). There is no way to measure what works.

An operator could spend a week tuning settings without an empirical
basis for whether the changes helped.

**Action:** A light experiment-tracking layer. SQLite table:
`experiments(timestamp, project_id, shot_id, knob_overrides_json,
output_path, ratings_json)`. Operator rates output 1-5. Over time, fit
which knob combinations correlate with high ratings.

**Not P0/P1.** This is the kind of thing that pays off after 6 months
of use; doesn't make sense to build until there's enough operator
volume.

#### P4-5 — The "Director's Console" mode is underdeveloped

The codebase has THREE UI shells: setup (EditorialShell), pipeline
(PipelineLayout), console (DirectorsConsole). The console mode appears
designed for live observation during runs but doesn't currently match
the polish of the editorial + pipeline shells. Some palette leakage
was just fixed in Bundle C 3.4.

**Open question for product:** is the console mode a kept feature?
If so, it deserves more investment. If not, delete it — the editorial
shell can absorb the "during run" view.

---

## What needs to be removed

These are not P-prioritized; they're cleanup-on-confidence calls.

| Item | Status | Action |
|---|---|---|
| `cleanup.py`, `reporter.py`, `generate_characters.py` at repo root | Unaudited purpose | Audit; delete if dead |
| `docs/REFACTOR_HANDOFF.md` `§0-5` setup sections | Pre-pivot, banner says "skip these" | Could trim in-place; low priority |
| `cinema/pipeline.py` (the generic driver, zero callers) | Preserved as primitive | Keep; ADR-001 chose this. May reconsider in a future review. |
| The `_VEO_QUOTA_EXHAUSTED_UNTIL` sticky module global | Process-only state | Acceptable for single-process design. Reconsider if multi-process is ever wanted. |
| `domain/projects/*` test artifacts that accumulate over time | Disk fills with old project dirs | Add a cron/CLI to prune projects older than N days. |
| The 3 skipped tests in `tests/unit/test_project_persistence.py` | Mock-drift, not behavior bugs | Fix the mocks (1 session). They're documented as "pre-existing" but they shouldn't be permanently skipped. |

---

## What needs to be upgraded

| Area | Current | Upgrade to |
|---|---|---|
| Logging | `print()` | `logging` with JSON formatter, correlation IDs, per-shot event stream |
| Tests | 6 unit tests in 1 file | ≥80 unit tests covering all 5 P0-1 critical modules + CI runs them |
| CI | None | `.github/workflows/ci.yml` with smoke + pytest + tsc |
| Types | Raw dicts in Python | Pydantic models for Project / Scene / Shot / GlobalSettings |
| Frontend errors | No error boundaries | React boundaries at every shell + ErrorBoundary fallback UI |
| Lipsync visibility | Silent cascade | Per-take metadata showing engine + score + fallback flag |
| Video cascade visibility | Silent cascade | Same — show which engine fired, cost, retry count |
| Settings exposure | Hidden behind JSON edits | UI controls for every documented knob (currently we have ~half) |
| Pod lifecycle | Manual stop/start | `POST /api/pod/sleep` endpoint hooked to RunPod API; auto-sleep after idle N minutes (opt-in) |
| Experiment tracking | None | SQLite layer for knob A/B + operator ratings (long-term) |

---

## Roadmap (next 6 sessions if I'm running engineering)

> **Per-session operator briefs with why + how + acceptance criteria
> + pitfalls + commit shape live in
> [HANDOFF-roadmap-2026-05-24.md](HANDOFF-roadmap-2026-05-24.md).**
> The table below is the index; that file is the manual.


| Session | Focus | Deliverable |
|---|---|---|
| 1 | **P0-2 CI** | `.github/workflows/ci.yml` running smoke + pytest + tsc on every push. |
| 2 | **P0-1.1 Tests for ReviewController** | Unit tests for `_gate_satisfied` (all 4 gates) + `approve_take` (all 3 kinds + error cases). |
| 3 | **P0-1.2 Tests for workflow_selector** | `classify_shot_type` × every keyword in `SHOT_TYPE_KEYWORDS` + `WORKFLOW_TEMPLATES` shape + `MOTION_FIDELITY_FLOORS` × shot_type alignment. |
| 4 | **P1-1a Structured logging** | Replace `print(...)` across `cinema_pipeline.py`, `cinema/shots/controller.py`, `cinema/review/controller.py`. JSON formatter + correlation IDs. |
| 5 | **P0-3 Cost-tracking audit** | Find all `try/except.*pass` patterns; replace with explicit handling. Confirm all `record_api_call` sites are live and observable. |
| 6 | **P1-4 Frontend error boundaries** + **P2-3 Cascade visibility** | One frontend session covering both. |

After 6 sessions: re-assess against this strategic review. Items that
remain open get re-prioritized or accepted as not-doing.

---

## What I will NOT do (and why)

- **Rewrite the orchestrator from scratch.** The slicing work prior
  directors did (ShotController, ReviewController, CheckpointStore,
  ThreadedLifecycle) is good. The remaining monolith in
  `cinema_pipeline.py` is finishable in a couple sessions, not a
  rewrite.

- **Migrate to a microservice architecture.** Single-operator single-process
  is the right shape for the current product. Multi-user is a product
  decision, not an engineering one.

- **Replace ComfyUI with a different backend.** ComfyUI's node graph IS
  the workflow source code. Replacing it would lose the operator's
  ability to edit `pulid.json` / `pulid_max.json`. The 24GB-VRAM pod
  requirement is the actual cost, not the ComfyUI choice.

- **Add a database.** SQLite for the cost tracker is sufficient. Adding
  Postgres/MySQL adds operational complexity for a single-operator tool.
  Reconsider if/when state-out-of-memory becomes necessary (P4-2).

- **Aggressively unify cascades.** The video/lipsync/performance cascades
  look similar but encode real differences (semaphores, quality gates,
  sticky 429s). Premature unification hurts more than it helps. (See
  prior strategic-review item 4.5.)

---

## How to use this document

This is a snapshot of leadership direction on 2026-05-24. As decisions
land they migrate to `DECISIONS.md` with the ADR format. Future
directors should write their own strategic review (e.g.,
`STRATEGIC_REVIEW-2027-01-15.md`) rather than editing this one — the
lineage of leadership direction has value as a historical record.

If an item here remains in this file in 6 months without a corresponding
ADR or session, that's a signal worth investigating: either it wasn't
important, or it was important and got dropped. Both are worth knowing.

---

*New director, signing on.*
