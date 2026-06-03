# Part-3 No-Op Audit — triaged tickets (HEAD `fb8d628`, 2026-06-03)

Output of the Test/Audit program **Part 5, Phase-A item 3**: re-verified every Part-3 fix-list item
(spec `docs/superpowers/specs/2026-06-02-program-test-audit-plan-design.md` §Part 3) against HEAD.
The 2026-06-02 fix list had drifted — **2 items were already DONE, 1 stale-doc was shipped this pass**,
leaving the open tickets below. Each is HEAD-verified (file:line current).

## Closed this audit (no longer open)
- **#2 Dialogue routing → Veo→overlay** — **DONE.** `cinema/shots/controller.py:128` `_dialogue_voice_mode` defaults to `"overlay"`; overlay wired as pipeline default (`:1278–1346`); `dialogue_voice_mode="native"` escape hatch.
- **#10 hedra_native ARCHITECTURE §10.6** — **DONE.** `ARCHITECTURE.md:1088–1100` already documents the `hedra_native.HedraAPI` direct path (wired `cb31207`).
- **#9 storyboard_mode stale-doc** — **FIXED** this pass (`fb8d628`): un-stubbed in `PROGRAM-MANUAL-digests.md` (last current-truth stale site; `pipeline_status.toml` + `PROGRAM-MANUAL.md §D-12` were already correct).

## Open tickets (triaged by severity)

| ID | Severity | Item | HEAD evidence | Recommended action |
|---|---|---|---|---|
| **T1** | **HIGH** | `validate_lora_quality` is an unconditional `-1.0` stub | `prep/lora_training.py:515,532` — returns `LORA_VALIDATION_SKIPPED` sentinel, no real check | **Implement** real LoRA quality validation. LoRA is the #1 identity lever; a bad LoRA silently degrades identity (see Part-4 U4). Design-first (brainstorm→spec→plan→TDD). |
| **T3** | **MED** | `hires_fix` "always pruned" claim appears **stale** | `quality_max.py:739–740` maps `hires_fix_enabled`/`hires_fix_denoise` into overlay params; `workflow_selector.py:174–177` generates per-tier | **Verify** the values actually reach the ComfyUI workflow nodes (the original "nodes 900-902 pruned" claim). If confirmed wired → close + update `pipeline_status.toml`. If still dead → wire or remove. |
| **T4** | **MED** | `max_halt_rule` accepts 3 modes; `should_halt` implements composite-only | `face_validator_gate.py:227–278` (`should_halt` has no `halt_rule` branch); schema accepts `composite_only`/`conjunctive`/`budget_only` (`quality_max.py:131`), mapped at `:705` | Implement `conjunctive`/`budget_only`, OR document the limit + reject the unsupported modes at config-validate time. |
| **T5** | **MED** | Budget gate: audio costs recorded but **not gated**; `spent_usd` resets per-process | `audio/{dialogue,music,foley}.py` call `record_api_call` (tracked), but each builds its own `CostTracker()` with no shared `budget_usd` ref; `cost_tracker.py:141–149` per-process db | Share one budget-aware `CostTracker` across audio paths (cap audio) + persist `spent_usd` across processes. |
| **T6** | **MED** | `evaluate_generation_quality` + `negative_prompts` auto-diagnose loop has **no caller** | `llm/chief_director.py:336` sole def; no production caller (grep clean, excl. tests) | **Wire** the retry/remediate loop into generation (dormant *quality* lever — wiring it raises capability; see PROGRAM-MANUAL §5). Design-first. |
| **T7** | **LOW** | `EXPERIMENTS_DB_PATH` read but never wired to `CostTracker` | `config/settings.py:128` reads `experiments_db_path`; no site passes it to a `CostTracker(...)` (`cost_tracker.py` uses its own `data/experiments.db` default) | Wire `settings.experiments_db_path` into `CostTracker` construction, OR remove the unused setting. |
| **T8** | **LOW/DOC** | `pipeline_context.md` lip-sync guidance contradicts current routing | `config/prompts/pipeline_context.md:34` ("NATIVE lip-sync … NOT overlay") + `:44` ("Veo OPT-IN ONLY") vs the now-default overlay route + `PURPOSE_API_RANKING` (`scene_decomposer.py:121`) which includes overlay engines | **Reconcile** — this is an LLM **prompt-context** file, so changing it affects routing guidance: update it to reflect the overlay-default dialogue decision. Care: behavior-adjacent, not a pure doc edit. |
| **T11** | **LOW** | 3 `@unittest.skip` in `test_project_persistence.py` | `:139` (lock mock no longer intercepts post-refactor), `:203` + `:232` (asset-commit cleanup needs updated mocks) | Fix the mocks + un-skip, OR delete the tests if the behavior is covered elsewhere. |

## Notes
- **T1 + T6** are the capability-relevant ones (PROGRAM-MANUAL §5 intent): both wire/implement dormant levers that raise identity/quality. Worth a design-first cycle each.
- **T3** is likely already done (claim stale) — cheapest close: a 10-min injection trace.
- **T8** is "doc" by spec severity but touches an LLM prompt file → treat as behavior-adjacent.
- `batch_scene_optimize` + `validate_multi_identity` (also "zero callers" in the digests) were **out of this audit's scope** (not on the Part-3 fix list); `validate_multi_identity` was a prune-KEEP decision this session.

*Method: cold-context re-verification agent, HEAD `fb8d628`, all file:line current as of 2026-06-03. Re-verify at HEAD before acting (point-in-time).*
