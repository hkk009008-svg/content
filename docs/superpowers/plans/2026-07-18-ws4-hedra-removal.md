# WS4 — Hedra Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the dead Hedra Character-3 engine (lapsed subscription, dead key) from both cascades and delete its client, so dialogue lipsync and Mode-B driving-video fall cleanly to their next engines without burning failed HTTP round-trips.

**Architecture:** Hedra sits at ATTEMPT 0 of two independent cascades — the lipsync *generation* cascade (`lip_sync.py`) and the performance Mode-B driving-video synth (`performance/driving_video.py`). Sever each consumer, then delete the now-unreferenced `hedra_native.py` client, its cost rows, and the dead env key. The next engines (OmniHuman v1.5 / Kling for lipsync; SadTalker for Mode-B) already exist in-cascade and become the effective ATTEMPT 0.

**Tech Stack:** Python 3, pytest, `fal_client`, `requests`, structured logging (`logger.*` with `extra=`).

## Global Constraints

- Subagents prefix all git with `env -u GIT_INDEX_FILE` (seat-index corruption vector).
- `.venv/bin/python -m pytest` is the test runner; run from repo root.
- `ci_smoke` (`.venv/bin/python scripts/ci_smoke.py`) must stay green after every task.
- No behavior change to the surviving engines — only Hedra is removed.
- Same-commit doc staleness discipline: fix `ARCHITECTURE.md` / `OPERATIONS.md` Hedra claims in the task that makes them stale.
- Money-lane: the cost-row deletions (Task 3) go through the `money-gate-reviewer` agent.

---

### Task 1: Sever Hedra from the lipsync generation cascade

**Files:**
- Modify: `lip_sync.py` (remove import L44; remove `_hedra_aspect_ratio_from_image` L753-~778; remove ATTEMPT 0 block ~L879-905)
- Test: `tests/unit/test_f1b_dialogue_lipsync.py`, `tests/unit/test_lip_sync_logging.py`, `tests/unit/test_lip_sync_best_of_failed.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `generate_lip_sync_video` / the generation cascade with OmniHuman v1.5 (`fal-ai/bytedance/omnihuman/v1.5`) and Kling as the effective first engines; no `hedra_native` import remains in `lip_sync.py`.

- [ ] **Step 1: Write the failing test** — assert Hedra is gone from the generation path.

```python
# tests/unit/test_f1b_dialogue_lipsync.py  (add)
import lip_sync

def test_generation_cascade_has_no_hedra_attempt():
    src = __import__("inspect").getsource(lip_sync)
    assert "hedra" not in src.lower(), "Hedra must be fully removed from lip_sync.py"
    assert "_HedraAPI" not in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_f1b_dialogue_lipsync.py::test_generation_cascade_has_no_hedra_attempt -v`
Expected: FAIL — `hedra` still present (import L44, ATTEMPT 0 block, aspect helper).

- [ ] **Step 3: Remove the three Hedra sites in `lip_sync.py`**

Delete exactly:
1. Line 44 `from hedra_native import HedraAPI as _HedraAPI`
2. The whole `def _hedra_aspect_ratio_from_image(...)` helper (starts L753; delete through its return + trailing blank line).
3. The `# ATTEMPT 0: Hedra Character-3` block (starts ~L879 at the comment, through the `except Exception as e:` ... `logger.warning("Hedra Character-3 failed", ...)` at ~L905). The block below it (`# ATTEMPT 1: Kling native lip sync`) is now the first attempt — renumber its comment to `# ATTEMPT 0: Kling native lip sync` and the Omnihuman/Aurora comments accordingly. Do NOT change their code.

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/unit/test_f1b_dialogue_lipsync.py tests/unit/test_lip_sync_logging.py tests/unit/test_lip_sync_best_of_failed.py -v`
Expected: PASS. If `test_lip_sync_logging.py` asserted a `{"engine": "hedra"}` log line, update that assertion to the new first engine (`kling`/`omnihuman`) — the log sequence no longer emits `hedra`.

- [ ] **Step 5: Commit**

```bash
env -u GIT_INDEX_FILE git add lip_sync.py tests/unit/test_f1b_dialogue_lipsync.py tests/unit/test_lip_sync_logging.py tests/unit/test_lip_sync_best_of_failed.py
env -u GIT_INDEX_FILE git commit -m "fix(lipsync): WS4 — remove dead Hedra Character-3 from the generation cascade"
```

---

### Task 2: Sever Hedra from the performance Mode-B driving-video synth

**Files:**
- Modify: `performance/driving_video.py` (remove `_synth_via_hedra` L69-138; remove `"hedra"` keys in the two cost dicts L38-39; remove the hedra branch in `synth_driving_face_from_audio` ~L290; update the `engine` param options L248 and docstring L271)
- Test: `tests/unit/test_driving_video_provider.py`, `tests/unit/test_performance_cache.py`

**Interfaces:**
- Consumes: nothing from Task 1 (independent file).
- Produces: `synth_driving_face_from_audio(engine ∈ {"auto","sadtalker"})` whose auto path goes straight to SadTalker; provider set is `{"sadtalker","cache"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_driving_video_provider.py  (add)
import performance.driving_video as dv

def test_modeb_has_no_hedra():
    src = __import__("inspect").getsource(dv)
    assert "_synth_via_hedra" not in src
    assert "hedra" not in dv._DRIVING_FACE_BASE_COST_USD
    assert "hedra" not in dv._DRIVING_FACE_COST_PER_SECOND_USD
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_driving_video_provider.py::test_modeb_has_no_hedra -v`
Expected: FAIL — `_synth_via_hedra` and the `"hedra"` cost keys still present.

- [ ] **Step 3: Remove the Hedra sites in `driving_video.py`**

1. Delete `_synth_via_hedra` (L69 `def` through its final `return None` ~L138).
2. In `_DRIVING_FACE_BASE_COST_USD` and `_DRIVING_FACE_COST_PER_SECOND_USD`, drop the `"hedra": …` entries; keep `"sadtalker"`.
3. In `synth_driving_face_from_audio`: delete the `if engine in ("auto","hedra"): r = _synth_via_hedra(...)` branch (~L288-296) so `auto` goes directly to `_synth_via_sadtalker`. Change the `engine` param default comment (L248) to `'auto' | 'sadtalker'` and update the provider-set docstring (L271) to `{"sadtalker","cache"}`.

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/unit/test_driving_video_provider.py tests/unit/test_performance_cache.py -v`
Expected: PASS. Update any assertion expecting a `"hedra"` provider to `"sadtalker"`.

- [ ] **Step 5: Commit**

```bash
env -u GIT_INDEX_FILE git add performance/driving_video.py tests/unit/test_driving_video_provider.py tests/unit/test_performance_cache.py
env -u GIT_INDEX_FILE git commit -m "fix(performance): WS4 — remove dead Hedra from Mode-B driving-video synth"
```

---

### Task 3: Delete the Hedra client, cost rows, env key, and docs (teardown)

**Files:**
- Delete: `hedra_native.py`, `tests/unit/test_hedra_native.py`, `tests/unit/test_hedra_dispatch.py`, `scripts/_hedra_test.py` (if present)
- Modify: `cost_tracker.py` (remove L67 `PERFORMANCE_DRIVING_HEDRA`, L98 `LIPSYNC_HEDRA`), `.env` (remove `HEDRA_API_KEY`), `config/settings.py` (remove `hedra_api_key` field if present), `ARCHITECTURE.md` (Hedra rows §perf + lipsync cascade), `OPERATIONS.md` (L121 `HEDRA_API_KEY` row + L518 cost row)
- Test: `tests/unit/test_cost_tracker.py`, `tests/unit/test_costtracker_perf_uncounted_regression.py`, `tests/unit/test_budget_pre_spend_gate.py`

**Interfaces:**
- Consumes: Task 1 removed the only `hedra_native` importer; Task 2 removed the last Mode-B reference. `hedra_native.py` is now unreferenced and safe to delete.
- Produces: no `HEDRA` symbol anywhere in a live path; `grep -rni hedra --include='*.py'` returns nothing outside deleted-in-this-task files.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cost_tracker.py  (add)
import cost_tracker

def test_no_hedra_cost_rows():
    keys = set(cost_tracker.__dict__.get("COST_TABLE", {}).keys()) if hasattr(cost_tracker, "COST_TABLE") else set()
    # fall back to scanning the module source if the table name differs
    src = __import__("inspect").getsource(cost_tracker)
    assert "HEDRA" not in src, "Hedra cost rows must be removed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_cost_tracker.py::test_no_hedra_cost_rows -v`
Expected: FAIL — `PERFORMANCE_DRIVING_HEDRA` / `LIPSYNC_HEDRA` still present.

- [ ] **Step 3: Delete the client + rows + key + docs**

```bash
env -u GIT_INDEX_FILE git rm hedra_native.py tests/unit/test_hedra_native.py tests/unit/test_hedra_dispatch.py
# scripts/_hedra_test.py only if it exists:
test -f scripts/_hedra_test.py && env -u GIT_INDEX_FILE git rm scripts/_hedra_test.py || true
```

Then edit: remove `cost_tracker.py` L67 + L98; remove `HEDRA_API_KEY=...` from `.env`; remove the `hedra_api_key` field from `config/settings.py` if it exists; delete the Hedra rows in `ARCHITECTURE.md` (the driving §perf table row + the lipsync ATTEMPT-0 line + the §1246/1304-style rows) and `OPERATIONS.md` L121 + L518. Replace the ARCHITECTURE lipsync-cascade "ATTEMPT 0 Hedra" description with "ATTEMPT 0: Kling / OmniHuman v1.5".

- [ ] **Step 4: Run the full suite + smoke**

Run: `.venv/bin/python -m pytest tests/unit/test_cost_tracker.py tests/unit/test_costtracker_perf_uncounted_regression.py tests/unit/test_budget_pre_spend_gate.py -v && .venv/bin/python scripts/ci_smoke.py`
Expected: PASS + smoke green. Update any budget/costtracker test that referenced a Hedra key to the surviving engine keys.

- [ ] **Step 5: Verify no residue, then commit**

Run: `grep -rni 'hedra' --include='*.py' . | grep -v '/.git/'`
Expected: no output (all Python references gone).

```bash
env -u GIT_INDEX_FILE git add -A
env -u GIT_INDEX_FILE git commit -m "chore(cleanup): WS4 — delete hedra_native client, cost rows, dead key, and docs"
```

---

## Self-Review

- **Spec coverage:** WS4 acceptance criteria ("no HEDRA symbol in a live cascade path; dialogue lipsync still produces output via OmniHuman/Kling; ci_smoke green") → covered by Task 1 (lipsync sever), Task 2 (Mode-B sever), Task 3 (residue grep + smoke). ✓
- **Placeholder scan:** none — every step names exact files/lines and shows the edit.
- **Type consistency:** `_synth_via_hedra`, `_HedraAPI`, `_hedra_aspect_ratio_from_image`, `PERFORMANCE_DRIVING_HEDRA`, `LIPSYNC_HEDRA` — all referenced consistently across tasks and all removed by Task 3's residue grep.
- **Dependency order locked:** Task 1 removes the only `hedra_native` importer → Task 3 can delete `hedra_native.py`. Tasks 1 and 2 are independent and may run in either order; Task 3 must be last.
