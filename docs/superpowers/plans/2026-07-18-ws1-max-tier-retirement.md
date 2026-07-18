# WS1 — Max Image-Gen Tier Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Retire the `quality_tier=="max"` image-generation tier — the 60-node `pulid_max.json` graph, its `quality_max.py` driver, `MAX_QUALITY_TEMPLATES`, and all `quality_tier=="max"` forks — while preserving the per-character LoRA-training subsystem (`prep/`) DORMANT for the future FLUX.2 A/B. ADR-024 proved the max graph over-cooks structurally; production (`pulid.json`) is the validated survivor.

**Architecture:** Sever every `quality_tier=="max"` consumer first (so nothing imports `quality_max`), then delete the driver + graph + templates + max-only tests. `prep/` LoRA training stays; only its docstrings that point at the deleted max tier are updated. Production image gen (`generate_ai_broll` → ComfyUI `pulid.json`, ADR-025 OFF 0.62→ON 0.88) is untouched and becomes the only tier.

**Tech Stack:** Python 3, pytest, ComfyUI (production `pulid.json` only after this).

## Global Constraints

- Subagents prefix all git with `env -u GIT_INDEX_FILE`; commit with explicit pathspecs (pre-existing dirty files — `.claude/settings.json`, scratch dirs — stay untouched).
- `.venv/bin/python -m pytest`; `.venv/bin/python scripts/ci_smoke.py` MUST stay green after every task.
- **PRESERVE dormant, do NOT delete:** `prep/lora_training.py`, `prep/lora_quality.py`, `prep/__init__.py`, `web_server.api_train_lora`, the `char_lora_paths` write path, and tests `test_lora_quality.py`, `test_lora_training_singletrain.py`, `test_web_server_train_lora_gated.py`. Their max-tier *docstring references* get updated; their logic does not.
- **Keep `generate_ai_broll`'s signature params** (`char_lora_path/strength/trigger`, `secondary_chars`, `style_reference`, `shot_hint`, `pulid_weight_override`) even though the production path won't consume them post-severance — mark them `# reserved: dormant until the FLUX.2 A/B (WS3) rewires`. Removing them would force stripping the controller threading (out of scope). This is deliberate, NOT dead-code to flag.
- Production identity is UNAFFECTED: `pulid.json` runs `ApplyPulidFlux`; the `fidelity` tag changes from `"pulid"` (max) to `"reference"` for all shots, but the actual mechanism (production PuLID graph) is unchanged.
- Money-lane: Task 4 removes max cost rows → route through `money-gate-reviewer`.
- Same-commit doc staleness: ARCHITECTURE.md / DECISIONS.md / skills fixed in the task that exposes them.

---

### Task 1: Sever the max fork in the image-gen entry (`phase_c_assembly.py`)

**Files:** Modify `phase_c_assembly.py` (delete the `if quality_tier == "max":` try/except block ~L152-189). Test: `tests/unit/test_phase_c_assembly_img2img_denoise.py`.

**Interfaces:** Produces `generate_ai_broll(...)` that always runs the production path (never imports `quality_max`); signature unchanged (dormant params retained).

- [ ] **Step 1: Failing test** — assert no max path remains:
```python
# tests/unit/test_phase_c_assembly_img2img_denoise.py (add)
def test_generate_ai_broll_has_no_max_tier_branch():
    import inspect, phase_c_assembly
    src = inspect.getsource(phase_c_assembly)
    assert "generate_ai_broll_max" not in src
    assert 'quality_tier == "max"' not in src
```
- [ ] **Step 2: Run → FAIL** (`generate_ai_broll_max` import + max branch present).
- [ ] **Step 3:** Delete the whole `if quality_tier == "max":` block (L152 through the closing `except Exception:` traceback print ~L189). Leave the `quality_tier` parameter in the signature (now only informational) and the dormant params with the reserved-comment note. The code that follows (`mode = "img2img" if init_image ...`) becomes the immediate body.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/unit/test_phase_c_assembly_img2img_denoise.py -v` → PASS.
- [ ] **Step 5: Commit** `fix(image): WS1 — remove max-tier branch from generate_ai_broll (production is the only tier)`.

### Task 2: Remove max templates + the config/scorecard forks

**Files:** Modify `workflow_selector.py` (delete `MAX_QUALITY_TEMPLATES` + `get_max_quality_template`/accessor + any `quality_tier=="max"` branch), `domain/scene_decomposer.py` (delete `is_max` + `candidate_count>1` best-of-N logic, the `quality_tier='max'` docstrings), `cinema/auto_approve.py` (L137 → `composite_default = 0.60`, update comment), `cinema/capability_scorecard.py` (remove max branches; `tier` collapses to production), `cinema/context.py` (max-tier references). Tests: `test_max_quality_templates.py` (DELETE), `test_auto_approve.py`, `test_capability_scorecard.py`, `test_identity_strategy_router.py`, `test_hidream_image_routing.py`.

**Interfaces:** Produces a single-tier `workflow_selector` (`WORKFLOW_TEMPLATES` only); `AutoApproveConfig.composite_default == 0.60` always.

- [ ] **Step 1: Failing test** — `assert not hasattr(workflow_selector, "MAX_QUALITY_TEMPLATES")` and `AutoApproveConfig.from_project({"global_settings":{"quality_tier":"max"}}).<composite field>` equals the 0.60-derived value.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3:** Apply the deletions above. For `auto_approve.py`: `composite_default = 0.60` unconditionally (the max branch is gone), rewrite the comment to state production is the only tier. For `capability_scorecard.py`/`context.py`: remove `quality_tier=="max"` conditionals, keeping the production path. Delete `tests/unit/test_max_quality_templates.py`.
- [ ] **Step 4: Run** the named tests + `ci_smoke` → PASS/green. Update assertions that expected max behavior.
- [ ] **Step 5: Commit** `fix(config): WS1 — drop MAX_QUALITY_TEMPLATES + max-tier config/scorecard forks`.

### Task 3: Sever the identity-strategy MAX_TIER fork (`controller.py` + `strategy.py`)

**Files:** Modify `cinema/shots/controller.py` (`_resolve_identity_strategy` — remove the `if quality_tier == "max":` block that sets `fidelity="pulid"` + `MAX_TIER_MULTI_LORA`; all shots get `fidelity="reference"`), `cinema/shots/strategy.py` (remove `MAX_TIER_PRIMARY_ONLY`, `MAX_TIER_MULTI_LORA` tag constants, or mark reserved). Test: `tests/unit/test_identity_strategy_router.py`, `test_char_lora_strength_thread.py`.

**Interfaces:** Produces `_resolve_identity_strategy(...)` returning `fidelity="reference"` for every shot; `char_lora_*` still threaded (dormant). NOTE (Rule #13 sibling): WS3 will edit this SAME function to add a `gemini_multiref` path — this task must leave it in a clean single-branch state so WS3 rebases cleanly.

- [ ] **Step 1: Failing test** — `_resolve_identity_strategy(shot, "max", settings, cc).conditioned[0].fidelity == "reference"` (no more `"pulid"` branch).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3:** Remove the `quality_tier == "max"` block; unconditionally build `fidelity="reference"` specs. Repoint `test_char_lora_strength_thread.py` to assert `char_lora_*` is STORED/threaded (not consumed by a max path).
- [ ] **Step 4: Run** the named tests → PASS.
- [ ] **Step 5: Commit** `fix(identity): WS1 — collapse identity-strategy to single reference tier (max fork removed)`.

### Task 4: Delete the driver, graph, max tests, cost rows, harness scripts (teardown)

**Files:** DELETE `quality_max.py`, `pulid_max.json`, `scripts/run_max_harness.py`, `scripts/_max_*.py`, and max test files `test_quality_max_{multichar,nan_gate,overlay,portrait,prune}.py`, `test_max_wide_pulid_startat_gap.py`, `test_hires_fix_pass2.py`. Modify `cost_tracker.py` (remove `QUALITY_MAX` provider entry + any max cost rows), `prep/lora_training.py` + `prep/lora_quality.py` (update docstrings that say "picked up by the maxed-quality pipeline / see quality_max" → "registered in char_lora_paths for the future FLUX.2 A/B; consumer currently dormant"). Also `scripts/check_doc_claims.py` if it hard-codes a max reference.

**Interfaces:** Produces a tree where `grep -rn 'quality_max\|pulid_max\|MAX_QUALITY_TEMPLATES\|generate_ai_broll_max' --include='*.py' .` returns only intentional historical/test-absence references.

- [ ] **Step 1: Failing test** — add `test_max_tier_fully_removed` asserting `import importlib; importlib.util.find_spec("quality_max") is None` and `not os.path.exists("pulid_max.json")`.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3:** `env -u GIT_INDEX_FILE git rm` the driver/graph/scripts/tests; edit `cost_tracker.py` + `prep/` docstrings.
- [ ] **Step 4: Run** full suite + `ci_smoke` → green. Residue grep must be clean.
- [ ] **Step 5: Commit** `chore(cleanup): WS1 — delete quality_max driver, pulid_max graph, max tests + harness`. (money-gate-reviewer on the cost-row change.)

### Task 5: Docs — ADR + ARCHITECTURE + skills

**Files:** `DECISIONS.md` (append new ADR: "Max image-gen tier retired — ADR-024 over-cook + 2026-07 research; production is the only tier; LoRA training kept dormant"), `ARCHITECTURE.md` (two-tier → one-tier: remove `pulid_max.json`/`quality_max`/`MAX_QUALITY_TEMPLATES` topology claims), `.claude/skills/comfyui-mastery/SKILL.md` + `.agents` twin (remove the 60-node `pulid_max.json` max-tier description; keep the 22-node production graph), `.claude/skills/ai-video-gen/*` twins if they name the max tier.

- [ ] **Step 1:** Write the ADR (never edit prior entries — append).
- [ ] **Step 2:** Update ARCHITECTURE.md + skills; keep `.claude`/`.agents` twins byte-identical.
- [ ] **Step 3: Run** `ci_smoke` → green (doc-claim gate).
- [ ] **Step 4: Commit** `docs(overhaul): WS1 — record max-tier retirement (ADR) + sync ARCHITECTURE + skills`.

---

## Self-Review

- **Spec coverage:** WS1 spec ("delete quality_max/pulid_max/MAX_QUALITY_TEMPLATES + max forks; preserve prep/ dormant; production identity intact; ci_smoke green") → Task 1 (entry fork), Task 2 (templates+config forks), Task 3 (identity-strategy fork), Task 4 (teardown+prep docstrings), Task 5 (docs). ✓
- **Placeholder scan:** none — exact files/lines/target states given.
- **Dependency order:** Tasks 1-3 sever all `quality_max` importers → Task 4 safely deletes it (same discipline as WS4). Task 5 docs last.
- **Type consistency:** `MAX_TIER_MULTI_LORA`/`MAX_TIER_PRIMARY_ONLY` removed in Task 3; `MAX_QUALITY_TEMPLATES`/`generate_ai_broll_max`/`quality_max` removed by Task 4's residue grep. `fidelity` value `"pulid"`→`"reference"` consistent across Task 3.
- **Rule #13 note:** Task 3 leaves `_resolve_identity_strategy` single-branch so WS3's `gemini_multiref` edit composes.
