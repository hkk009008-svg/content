# R-BRIEF: llmensemble-cost-uncounted - thread competitive LLM spend into the budget gate

PRIORITY: CRITICAL        LANE: B (video/assembly/audio)
CROSS-CUTTING: no (does not touch auto_approve.py, cinema/context.py, core.py, or web_server.py)
LOCK: none
CO-SIGN: none

## The Defect

`competitive_decompose_scene(..., cost_tracker=self.cost_tracker)` receives the
pipeline's gate-connected tracker from `cinema_pipeline.py`, but its success path
constructs a bare `LLMEnsemble()` and calls `competitive_generate()` without the
tracker. `LLMEnsemble` then performs candidate and judge LLM calls without writing
to `CostTracker.log_llm`, so planning spend is invisible to the in-process
`spent_usd` accumulator used by the budget gate.

The sibling prompt-optimizer path is also default-on for new projects and constructs
its own `LLMEnsemble(global_settings)` without a tracker.

## Rule #12 - Grep The Writes

TARGET SYMBOL: `CostTracker.spent_usd`, the in-process accumulator the budget gate reads.

```text
$ rg -n "self\.spent_usd\s*=|self\.spent_usd\s*\+=" cost_tracker.py
cost_tracker.py:306:        self.spent_usd += cost_usd
```

Runtime write evidence: LLM spend must reach `CostTracker.log_llm()` because
`log_llm()` delegates to `log()`, and `log()` is the sole runtime write that
increments `self.spent_usd`.

```text
$ rg -n "prompt_optimizer_enabled|optimize_shot_prompt\(|LLMEnsemble\(|competitive_generate\(|cost_tracker=self\.cost_tracker|def competitive_decompose_scene|cost_tracker=None|self\.spent_usd\s*\+=" cinema/shots/controller.py domain/project_manager.py domain/scene_decomposer.py llm/prompt_optimizer.py llm/ensemble.py cinema/core.py cinema_pipeline.py cost_tracker.py
cost_tracker.py:306:        self.spent_usd += cost_usd
domain/project_manager.py:338:            "prompt_optimizer_enabled": True,
cinema/core.py:114:        ensemble=LLMEnsemble(settings=settings),
llm/ensemble.py:146:    def competitive_generate(
llm/prompt_optimizer.py:355:def optimize_shot_prompt(
llm/prompt_optimizer.py:402:            ensemble = LLMEnsemble(global_settings)
llm/prompt_optimizer.py:451:        result = ensemble.competitive_generate(
llm/prompt_optimizer.py:497:        spec = optimize_shot_prompt(
domain/scene_decomposer.py:442:    cost_tracker=None,
domain/scene_decomposer.py:626:def competitive_decompose_scene(
domain/scene_decomposer.py:632:    cost_tracker=None,
domain/scene_decomposer.py:759:        ensemble = LLMEnsemble()
domain/scene_decomposer.py:760:        result = ensemble.competitive_generate(
cinema_pipeline.py:967:                cost_tracker=self.cost_tracker,  # T5: gate planning LLM spend on pipeline budget
cinema_pipeline.py:1020:                        shots = competitive_decompose_scene(scene, chars_in_scene, location, settings, style_rules, cost_tracker=self.cost_tracker)
cinema_pipeline.py:1026:                        shots = decompose_scene(scene, chars_in_scene, location, settings, style_rules, cost_tracker=self.cost_tracker)
cinema_pipeline.py:1028:                    shots = decompose_scene(scene, chars_in_scene, location, settings, style_rules, cost_tracker=self.cost_tracker)
cinema_pipeline.py:1048:                    shots = decompose_scene(scene, chars_in_scene, location, settings, style_rules, cost_tracker=self.cost_tracker)
cinema/shots/controller.py:684:        opt_enabled = settings.get("prompt_optimizer_enabled", False)
cinema/shots/controller.py:709:                    opt_spec = optimize_shot_prompt(
```

The source call at `cinema_pipeline.py:1020` already supplies the shared tracker.
The defect is the dropped tracker inside `domain/scene_decomposer.py:759` and the
same-family prompt-optimizer construction at `llm/prompt_optimizer.py:402`.

## Rule #13 - Symmetric / Sibling Audit

SHARED STATE: planning-LLM spend visibility through the shared pipeline `CostTracker`.

```text
$ rg -n "LLMEnsemble\(" . --glob '*.py'
./domain/scene_decomposer.py:759:        ensemble = LLMEnsemble()
./llm/prompt_optimizer.py:402:            ensemble = LLMEnsemble(global_settings)
./cinema/core.py:114:        ensemble=LLMEnsemble(settings=settings),
```

Disposition:
- Fold `domain/scene_decomposer.py:759`: pass the gate-connected tracker into the
  ensemble used by competitive decomposition.
- Fold `llm/prompt_optimizer.py:402` plus its caller
  `cinema/shots/controller.py:709`: add an optional `cost_tracker` parameter and
  pass `self.cost_tracker` from the default-on prompt optimizer path.
- Preserve `cinema/core.py:114`: keep the existing `LLMEnsemble(settings=...)`
  call shape valid by making the new tracker parameter optional.

## Full-Shape Pattern Reference

MIRROR: the existing T5/audio planning pattern of accepting `cost_tracker=None`,
threading the caller's shared tracker through the call boundary, and recording
successful spend through `CostTracker.log_llm()`.

Relevant existing shapes:
- `domain/scene_decomposer.py:442` has `cost_tracker=None` and the non-competitive
  decomposer receives `cost_tracker=self.cost_tracker` from `cinema_pipeline.py`.
- `cost_tracker.py:319` defines `log_llm(model, operation, input_tokens, output_tokens, ...)`.
- `CostTracker.log()` is fail-soft on non-finite cost and increments `spent_usd`
  only after the SQLite write succeeds.

## The Fix

Bounded files:
- `llm/ensemble.py`: add optional `cost_tracker` storage; log candidate and judge
  usage from Anthropic, OpenAI, and Gemini responses via `CostTracker.log_llm()`;
  preserve all existing constructor and `competitive_generate()` call shapes.
- `domain/scene_decomposer.py`: construct `LLMEnsemble(cost_tracker=cost_tracker)`
  on the competitive success path.
- `llm/prompt_optimizer.py`: accept optional `cost_tracker`, pass it to the
  internally constructed ensemble, and thread it through `batch_optimize_scene()`.
- `cinema/shots/controller.py`: pass `self.cost_tracker` into `optimize_shot_prompt()`.
- `tests/unit/test_llmensemble_cost_uncounted_xfail.py`: convert the strict-xfail
  pin to a live regression and add focused usage-logging coverage.

Do not edit cross-cutting modules. Do not widen into `charmgr-cost-fresh-instance`.

## Verification The Operator/CI Will Run

Expected local verification:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_llmensemble_cost_uncounted_xfail.py -q
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_prompt_optimizer.py tests/unit/test_ensemble_judge_parse.py tests/unit/test_llm_caching.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Operator2 Lane V should include the `money-gate-reviewer` lens and confirm:
- the former strict-xfail pin is now a live regression;
- the shared tracker reaches the competitive decomposition ensemble;
- actual nonzero usage records through `CostTracker.log_llm()` into `spent_usd`;
- the prompt-optimizer sibling is folded or explicitly equivalent;
- no cross-cutting lock was needed.
