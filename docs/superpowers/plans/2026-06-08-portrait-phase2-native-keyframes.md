# Portrait Phase 2 — Native 9:16 Image Keyframes Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make image-keyframe generation emit true native 9:16 (portrait) when a project's `aspect_ratio="9:16"`, across the ComfyUI primary path (production + max tiers) and the FAL/Pollinations fallbacks — while the user-facing gate stays closed until Phase 3.

**Architecture:** All aspect geometry stays in `cinema/aspect.py` (Phase-1's single source of truth). A pure `portrait_swap(w,h,aspect)` transposes each tier's *already-validated* landscape latent when portrait; a `fal_image_size(aspect)` maps to FAL's named enum. `aspect_ratio` is read from the `ctx` (`PipelineContext.global_settings`) **already threaded** into both generation entry points via the existing `get_project_setting(ctx, …)` convention — so no new function parameter and no `controller.py` edit. The gate constant `SUPPORTED_ASPECT_RATIOS` is NOT modified (Phase 3 un-gates).

**Tech Stack:** Python 3, pytest, ComfyUI (RunPod) workflow JSON, FLUX/PuLID, fal_client, Pollinations.

**Spec:** [docs/superpowers/specs/2026-06-08-portrait-phase2-native-keyframes-design.md](../specs/2026-06-08-portrait-phase2-native-keyframes-design.md)

**Latent dimensions (D5 — transpose the tier's validated landscape latent):**
| Tier / path | Landscape (today) | Portrait (9:16) |
|---|---|---|
| Production ComfyUI node 102 | 1344×768 | **768×1344** |
| Max ComfyUI node 102 | 1024×576 | **576×1024** |
| Max node 950 `final_resolution` | (3840, 2160) | **(2160, 3840)** |
| Pollinations URL | width=1344&height=768 | **width=768&height=1344** |
| FAL `aspect_ratio` (Kontext `:515`, Pro `:534`) | `"16:9"` | `"9:16"` |
| FAL `image_size` (schnell `:555`) | `"landscape_16_9"` | `"portrait_16_9"` |

**Project conventions (every task):**
- Run tests with `env -u GIT_INDEX_FILE .venv/bin/python -m pytest …` (the D-a `GIT_INDEX_FILE` export breaks tests that build temp git repos; unsetting it is required — see CLAUDE.md memory).
- Before editing a symbol, `grep -rn 'symbolName' --include='*.py' .` for callers; after edits `git diff --stat` to confirm scope.
- Commit with pathspec under D-a: `git add <paths>` then `git commit -- <paths>`. End messages with the `Co-Authored-By:` trailer.
- **Re-verify HEAD before starting** — the operator-seat is shipping a parallel deferred-minors batch. This plan does NOT touch `controller.py` (their item-B file), so no overlap is expected, but `phase_c_assembly.py`/`quality_max.py` should be re-grepped at the cited lines (they drift if the operator touches them).

---

## Chunk 1: Phase 2 native 9:16 keyframes

### Task 1: `cinema/aspect.py` — pure helpers `portrait_swap` + `fal_image_size`

**Files:**
- Modify: `cinema/aspect.py` (after `is_supported`, ~`:48`)
- Test: `tests/unit/test_cinema_aspect.py` (extend the existing file)

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_cinema_aspect.py`, matching its plain-function style)

```python
from cinema.aspect import portrait_swap, fal_image_size  # add to existing imports


def test_portrait_swap_landscape_is_noop():
    assert portrait_swap(1344, 768, "16:9") == (1344, 768)
    assert portrait_swap(1024, 576, "16:9") == (1024, 576)
    assert portrait_swap(3840, 2160, "16:9") == (3840, 2160)


def test_portrait_swap_portrait_transposes():
    assert portrait_swap(1344, 768, "9:16") == (768, 1344)
    assert portrait_swap(1024, 576, "9:16") == (576, 1024)
    assert portrait_swap(3840, 2160, "9:16") == (2160, 3840)


def test_portrait_swap_unknown_and_none_are_noop():
    # unknown/None resolve to the default (16:9) → landscape → no transpose
    assert portrait_swap(1344, 768, None) == (1344, 768)
    assert portrait_swap(1344, 768, "") == (1344, 768)
    assert portrait_swap(1344, 768, "21:9") == (1344, 768)


def test_fal_image_size_maps_orientation():
    assert fal_image_size("16:9") == "landscape_16_9"
    assert fal_image_size("9:16") == "portrait_16_9"
    assert fal_image_size(None) == "landscape_16_9"
    assert fal_image_size("4:3") == "landscape_16_9"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cinema_aspect.py -v`
Expected: FAIL — `ImportError: cannot import name 'portrait_swap'`.

- [ ] **Step 3: Implement the helpers** (append to `cinema/aspect.py`, after `is_supported`)

```python
# FAL image_size is a named bucket, not pixel dims — map by orientation.
FAL_IMAGE_SIZE: dict[str, str] = {"16:9": "landscape_16_9", "9:16": "portrait_16_9"}


def portrait_swap(w: int, h: int, aspect_ratio: Optional[str]) -> tuple[int, int]:
    """Transpose (w, h) → (h, w) when ``aspect_ratio`` resolves to portrait.

    Lets each generation path keep its own tuned pixel budget, just rotated.
    Unknown / None / landscape → unchanged. Never raises (delegates to
    is_portrait → resolve_output_dimensions, which defaults to 16:9).
    """
    return (h, w) if is_portrait(aspect_ratio) else (w, h)


def fal_image_size(aspect_ratio: Optional[str]) -> str:
    """FAL's named image_size enum for the given aspect ratio (landscape default)."""
    return FAL_IMAGE_SIZE.get(aspect_ratio or "", "landscape_16_9")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cinema_aspect.py -v`
Expected: PASS (all, including the pre-existing aspect tests).

- [ ] **Step 5: Commit**

```bash
git add cinema/aspect.py tests/unit/test_cinema_aspect.py
git commit -- cinema/aspect.py tests/unit/test_cinema_aspect.py -m "feat(aspect): portrait_swap + fal_image_size helpers (Phase 2)

Pure transpose helper + FAL enum map; geometry stays in cinema/aspect.py.
Gate untouched. Per docs/superpowers/specs/2026-06-08-portrait-phase2-...

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Production ComfyUI — read aspect from ctx + transpose node 102

**Files:**
- Modify: `phase_c_assembly.py` — add the aspect read near the existing ctx read (~`:189`); node 102 mutation (`:212-213`)
- Test: `tests/unit/test_phase_c_assembly_portrait.py` (new)

> **Production-code change (exact):**
> Near `phase_c_assembly.py:189` (where `ctx.global_settings` is already consulted), add:
> ```python
> from cinema.aspect import portrait_swap, fal_image_size, DEFAULT_ASPECT_RATIO
> from cinema.context import get_project_setting
> aspect_ratio = get_project_setting(ctx, "aspect_ratio", DEFAULT_ASPECT_RATIO)
> ```
> Then replace the node-102 mutation (`:212-213`):
> ```python
> _w, _h = portrait_swap(1344, 768, aspect_ratio)
> workflow["102"]["inputs"]["width"]  = _w
> workflow["102"]["inputs"]["height"] = _h
> ```
> (Confirm the existing import block / `get_project_setting` availability; `aspect_ratio` must be in scope at `:212`.)

- [ ] **Step 1: Write the failing test** — intercept the workflow dict at `queue_prompt`

```python
import dataclasses
import pytest
from cinema.context import PipelineContext

def _portrait_capture(monkeypatch):
    """Mock RunPodComfyUI so generate_ai_broll reaches the submit and we capture
    the workflow. Returns the dict that will be populated at queue_prompt time."""
    import phase_c_assembly as pca
    captured = {}
    def _queue(self, wf):
        captured.update(wf)
        return "fake-prompt-id"
    monkeypatch.setattr(pca.RunPodComfyUI, "queue_prompt", _queue, raising=True)
    monkeypatch.setattr(pca.RunPodComfyUI, "get_history", lambda self, pid: {}, raising=True)
    return captured

def test_production_node102_portrait_transposes(tmp_path, monkeypatch):
    captured = _portrait_capture(monkeypatch)
    ctx = PipelineContext(global_settings={"aspect_ratio": "9:16"})
    # server_url present + pulid.json present → primary ComfyUI path
    monkeypatch.setattr("phase_c_assembly.settings",
                        dataclasses.replace(__import__("phase_c_assembly").settings,
                                            comfyui_server_url="http://fake"), raising=False)
    from phase_c_assembly import generate_ai_broll
    generate_ai_broll("a person", str(tmp_path / "out.jpg"),
                      ctx=ctx, quality_tier="production")
    assert captured.get("102", {}).get("inputs", {}).get("width") == 768
    assert captured["102"]["inputs"]["height"] == 1344

def test_production_node102_landscape_unchanged(tmp_path, monkeypatch):
    captured = _portrait_capture(monkeypatch)
    ctx = PipelineContext(global_settings={"aspect_ratio": "16:9"})
    monkeypatch.setattr("phase_c_assembly.settings",
                        dataclasses.replace(__import__("phase_c_assembly").settings,
                                            comfyui_server_url="http://fake"), raising=False)
    from phase_c_assembly import generate_ai_broll
    generate_ai_broll("a person", str(tmp_path / "out.jpg"),
                      ctx=ctx, quality_tier="production")
    assert captured["102"]["inputs"]["width"] == 1344
    assert captured["102"]["inputs"]["height"] == 768
```

> **Implementer note:** `generate_ai_broll` does substantial work between loading `pulid.json` and `queue_prompt` (PuLID/character-ref handling). When you run the failing test, it may error *before* reaching `queue_prompt` (e.g. needing a character image). Adapt the mock plumbing (mock the minimal additional surface — image download/validation — so execution reaches `:363`) WITHOUT changing the assertion. The assertion (node 102 = 768×1344) is the spec contract; the mocking is yours to make reach the seam. If reaching the seam proves disproportionately fragile, extract the 3-line node-102 mutation into a tiny tested helper `_set_latent_dims(workflow, base_w, base_h, aspect_ratio)` and unit-test that directly — note the deviation in your report.

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_phase_c_assembly_portrait.py -v`
Expected: FAIL — node 102 is 1344×768 (not yet transposed).

- [ ] **Step 3: Implement** the production-code change above (ctx read + node-102 transpose).

- [ ] **Step 4: Run test to verify it passes**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_phase_c_assembly_portrait.py -v`
Expected: PASS.

- [ ] **Step 5: Commit** (`git add phase_c_assembly.py tests/unit/test_phase_c_assembly_portrait.py && git commit -- … -m "feat(keyframe): production ComfyUI native 9:16 latent (Phase 2)…"`)

---

### Task 3: FAL + Pollinations fallbacks → portrait

**Files:**
- Modify: `phase_c_assembly.py:515, :534, :555, :570`
- Test: `tests/unit/test_phase_c_assembly_portrait.py` (extend)

> **Production-code change (exact):** `aspect_ratio` is already in scope from Task 2.
> - `:515` and `:534`: `"aspect_ratio": "16:9",` → `"aspect_ratio": aspect_ratio,`
> - `:555`: `"image_size": "landscape_16_9",` → `"image_size": fal_image_size(aspect_ratio),`
> - `:570`: `?width=1344&height=768…` → compute `_pw, _ph = portrait_swap(1344, 768, aspect_ratio)` just above, then `?width={_pw}&height={_ph}…`

- [ ] **Step 1: Write failing tests** — follow the existing `test_phase_c_assembly_provenance.py` precedent (mock `fal_client` via `monkeypatch.setitem(sys.modules, "fal_client", MagicMock())`, capture the `subscribe(..., arguments=…)` kwargs). Force the FAL/Pollinations path by leaving `comfyui_server_url` unset / `pulid.json` unavailable so the primary path is skipped.

```python
# Pattern (adapt to the actual fallback entry the provenance test uses):
def test_fal_fallback_portrait_args(tmp_path, monkeypatch):
    import sys
    from unittest.mock import MagicMock
    fake = MagicMock()
    captured = {}
    def _subscribe(model, arguments=None, **kw):
        captured["model"] = model; captured["args"] = arguments
        return {"images": [{"url": "http://x/y.png"}]}
    fake.subscribe.side_effect = _subscribe
    monkeypatch.setitem(sys.modules, "fal_client", fake)
    # ... drive the FAL path with aspect_ratio="9:16" (see provenance test for the entry) ...
    # assert captured["args"]["aspect_ratio"] == "9:16"   (Kontext/Pro)
    # assert captured["args"]["image_size"] == "portrait_16_9"  (schnell)
```

```python
def test_pollinations_url_portrait(monkeypatch):
    # exercise the Pollinations branch with aspect_ratio="9:16";
    # stub the HTTP fetch — Pollinations uses urllib (NOT fal_client):
    #   monkeypatch.setattr("urllib.request.urlopen", <fake returning bytes>)
    #   (and urlretrieve if the branch downloads via that, per the provenance test)
    # capture/inspect the constructed URL string; assert it contains
    # "width=768&height=1344".
    ...
```

> **Implementer note:** The fallback entry is `_fal_flux_fallback` (`phase_c_assembly.py:417`) — a **standalone, directly-callable** function. `test_phase_c_assembly_provenance.py` already calls it directly with a `stub_fal` fixture (`monkeypatch.setitem(sys.modules, "fal_client", fake)` + `dataclasses.replace(pca.settings, …)` + a `urlretrieve` stub). Reuse that exact fixture: pass `ctx=PipelineContext(global_settings={"aspect_ratio":"9:16"})` and drive each model — Kontext (`fal-ai/flux-pro/kontext/max/multi`, needs `character_image`), Pro (`fal-ai/flux-pro/v1.1-ultra`, `character_image=None`), schnell (`fal-ai/flux/schnell`, reached by a Pro-failure `side_effect`) — asserting `arguments["aspect_ratio"]=="9:16"` (Kontext/Pro) and `arguments["image_size"]=="portrait_16_9"` (schnell). Pollinations is the urllib branch (different stub, as above).

- [ ] **Step 2: Run → FAIL** (`"16:9"` / `"landscape_16_9"` / `width=1344`).
- [ ] **Step 3: Implement** the four edits above.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** (`feat(keyframe): FAL + Pollinations fallbacks emit 9:16 (Phase 2)`).

---

### Task 4: Max tier — node 102 override + node 950 transpose + ctx read (`quality_max.py`)

**Files:**
- Modify: `quality_max.py` — read aspect from ctx; node 950 (`:607-610`); add node-102 portrait override
- Test: `tests/unit/test_quality_max_portrait.py` (new) — follow `test_quality_max_prune.py`'s pure-workflow-dict-inspection style

> **Production-code change (exact):**
> 1. Read aspect where ctx is consulted: `aspect_ratio = get_project_setting(ctx, "aspect_ratio", DEFAULT_ASPECT_RATIO)` (imports as Task 2).
> 2. Node 950 (`:607-610`):
>    ```python
>    if "950" in workflow:
>        _w, _h = portrait_swap(*params.get("final_resolution", (3840, 2160)), aspect_ratio)
>        workflow["950"]["inputs"]["width"]  = _w
>        workflow["950"]["inputs"]["height"] = _h
>    ```
> 3. Node 102 override (quality_max does NOT set it today — add near where the workflow dict is prepared, e.g. alongside `_inject_latent_source`):
>    ```python
>    if is_portrait(aspect_ratio) and "102" in workflow:
>        _lw, _lh = portrait_swap(1024, 576, aspect_ratio)   # → 576×1024
>        workflow["102"]["inputs"]["width"]  = _lw
>        workflow["102"]["inputs"]["height"] = _lh
>    ```
>    (Confirm 1024×576 is the `pulid_max.json` node-102 default at runtime, or read it from the loaded template before swapping — plan-time §7 open item.)

- [ ] **Step 1: Write failing tests** — load the max workflow via the same helper `test_quality_max_prune.py` uses (`_load_max_workflow()`), call the injection function(s) you placed the overrides in with `aspect_ratio="9:16"`, assert node 102 = (576,1024) and node 950 = (2160,3840); with `"16:9"` assert node 102 unchanged from template + node 950 = (3840,2160). If the overrides aren't reachable as isolated helpers, fall back to the `queue_prompt`-capture integration approach from Task 2 (mock `quality_max`'s `RunPodComfyUI.queue_prompt` at `:631`).

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the three changes above.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** (`feat(keyframe): max-tier native 9:16 latent + 4K portrait final (Phase 2)`).

---

### Task 5: Full-suite + smoke verification

- [ ] **Step 1: Run the full unit suite**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q`
Expected: all pass, no NEW failures vs the green baseline (`c28f9e6` = 1764/0). Note any pre-existing failures separately — do not fix in this slice.

- [ ] **Step 2: Run the §15 smoke**

Run: `.venv/bin/python scripts/ci_smoke.py`
Expected: `OK`.

- [ ] **Step 3: Confirm the gate is still closed** (no accidental Phase-3 leak)

Run: `grep -n 'SUPPORTED_ASPECT_RATIOS' cinema/aspect.py`
Expected: still `["16:9"]` — Phase 2 must NOT have appended `"9:16"`.

- [ ] **Step 4: No commit** (verification only) — or a `chore` commit if any test-tolerance tweak was needed.

---

## On-pod validation (manual, post-merge — NOT an automated task)

The unit tests prove the **plumbing** (aspect read → transpose → applied at each site). They do NOT prove the 9:16 keyframes *look right* — that's the empirical claim in D5 (768×1344 / 576×1024 being *good* FLUX latents, not just valid ones). When the GPU pod is up:
- Generate one **production** + one **max** keyframe with `aspect_ratio="9:16"` (via a dev harness passing the setting directly — the user gate is still closed).
- Confirm: true portrait pixels, photoreal quality, no squish/letterbox.
- If a tier's transpose looks wrong, the fix is a tier-specific latent value in §4.x — re-validate.

## Definition of done (Phase 2)

- [ ] Tasks 1-4 committed; Task 5 green (full suite + smoke).
- [ ] `SUPPORTED_ASPECT_RATIOS` unchanged (gate closed).
- [ ] Backward-compatible (16:9 / ctx-less = no-op) proven by tests.
- [ ] On-pod validation scheduled/done when the pod is available.
- [ ] Phase 3 (video + un-gate) remains a separate spec.
