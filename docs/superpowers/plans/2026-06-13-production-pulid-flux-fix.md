# Production PuLID SDXL→FLUX Fix Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make the default production image tier's single PuLID actually lock the reference face on FLUX by replacing the SDXL-era PuLID nodes in `pulid.json` with the FLUX-native node set, and aligning the runtime `start_at` so the swap binds.

**Architecture:** Two-file static change to a ComfyUI graph + its parameter table, guarded by a new regression test (the bug was test-dark) and a pod before/after acceptance gate. No Python control-flow changes — `generate_ai_broll` / `apply_workflow_params` write node 100 by ID, which is class-agnostic. See the design spec: `docs/superpowers/specs/2026-06-13-production-pulid-flux-fix-design.md` and ADR-024.

**Tech Stack:** Python 3, pytest, ComfyUI API-format JSON graphs (`pulid.json`), a self-hosted FLUX ComfyUI pod (validation only).

**Pre-flight (read before starting):**
- Run from the repo root. Tests run via `.venv/bin/python -m pytest`. In the director/operator two-seat setup, prefix git with `env -u GIT_INDEX_FILE` and commit with **explicit pathspec** (never bare `git commit`/`git add -A` — it can sweep the peer's WIP).
- The FLUX PuLID assets (`pulid_flux_v0.9.1.safetensors`, the FLUX eva-clip) are already on the pod — the max tier (`pulid_max.json`) loads them.
- Scope is the **single** production PuLID only. Do NOT add a LoRA node (700) or a second identity — that is the separate ADR-024 experiment track.

---

## Chunk 1: Offline code fix + regression guard

### Task 1: FLUX-native production PuLID graph

**Files:**
- Create: `tests/unit/test_pulid_production_flux.py`
- Modify: `pulid.json` (nodes 99, 100, 101)

- [x] **Step 1: Write the failing test**

Create `tests/unit/test_pulid_production_flux.py`:

```python
"""Regression guard: the production pulid.json must use the FLUX-native PuLID nodes.

The shipping production tier renders via pulid.json on a FLUX UNet (node 112 =
flux1-dev-fp8). The SDXL-era PuLID nodes (PulidModelLoader / ApplyPulid /
PulidEvaClipLoader) patch U-Net cross-attention layers FLUX's DiT lacks -> zero
face lock (a silent no-op). This test pins the FLUX-native node set so the
misconfiguration can never silently regress.

See ADR-024 + docs/superpowers/specs/2026-06-13-production-pulid-flux-fix-design.md.
"""
import json
from pathlib import Path

import pytest

PULID = Path(__file__).resolve().parents[2] / "pulid.json"


@pytest.fixture(scope="module")
def graph():
    data = json.loads(PULID.read_text())
    data.pop("_metadata", None)
    return data


def test_pulid_loader_is_flux_native(graph):
    assert graph["99"]["class_type"] == "PulidFluxModelLoader"
    assert graph["99"]["inputs"]["pulid_file"] == "pulid_flux_v0.9.1.safetensors"


def test_eva_clip_loader_is_flux_native(graph):
    assert graph["101"]["class_type"] == "PulidFluxEvaClipLoader"


def test_apply_pulid_is_flux_native(graph):
    node = graph["100"]
    assert node["class_type"] == "ApplyPulidFlux"
    inputs = node["inputs"]
    # FLUX node uses pulid_flux, not the SDXL 'pulid' key
    assert "pulid_flux" in inputs
    assert "pulid" not in inputs
    # SDXL-only 'method' key must be gone (unknown to ApplyPulidFlux)
    assert "method" not in inputs
    # model feeds direct from the UNETLoader (no LoRA node 700 in production)
    assert inputs["model"] == ["112", 0]
    # coarse-identity window must start at 0.0
    assert inputs["start_at"] == 0.0
    # a FLUX-specific fusion param is present
    assert inputs["fusion"] == "mean"


def test_no_sdxl_pulid_nodes_remain(graph):
    classes = {n.get("class_type") for n in graph.values() if isinstance(n, dict)}
    assert "ApplyPulid" not in classes
    assert "PulidModelLoader" not in classes
    assert "PulidEvaClipLoader" not in classes
```

- [x] **Step 2: Run the test to verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_pulid_production_flux.py -v`
Expected: FAIL — `pulid.json` node 99 is still `PulidModelLoader`, node 100 `ApplyPulid`, etc.

- [x] **Step 3: Edit `pulid.json` — replace nodes 99, 100, 101**

Replace node `"99"` with:

```json
    "99": {
        "inputs": {
            "pulid_file": "pulid_flux_v0.9.1.safetensors"
        },
        "class_type": "PulidFluxModelLoader",
        "_meta": {
            "title": "Load PuLID Flux Model"
        }
    }
```

Replace node `"100"` with (keep `model: ["112",0]` — do NOT use max's `["700",0]`):

```json
    "100": {
        "inputs": {
            "weight": 1,
            "start_at": 0.0,
            "end_at": 1,
            "fusion": "mean",
            "fusion_weight_max": 1.0,
            "fusion_weight_min": 0.0,
            "train_step": 1000,
            "use_gray": true,
            "model": ["112", 0],
            "pulid_flux": ["99", 0],
            "eva_clip": ["101", 0],
            "face_analysis": ["97", 0],
            "image": ["93", 0]
        },
        "class_type": "ApplyPulidFlux",
        "_meta": {
            "title": "Apply PuLID Flux"
        }
    }
```

Replace node `"101"` with:

```json
    "101": {
        "inputs": {},
        "class_type": "PulidFluxEvaClipLoader",
        "_meta": {
            "title": "Load Eva Clip (PuLID Flux)"
        }
    }
```

Leave every other node untouched (97, 112, the sampler chain, RealESRGAN 500/501/502, PAG 301). Match the file's existing indentation. Verify it stays valid JSON:
`env -u GIT_INDEX_FILE .venv/bin/python -c "import json; json.load(open('pulid.json')); print('valid json')"`

- [x] **Step 4: Run the test to verify it passes**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_pulid_production_flux.py -v`
Expected: PASS (4 tests).

- [x] **Step 5: Commit**

```bash
env -u GIT_INDEX_FILE git add -- pulid.json tests/unit/test_pulid_production_flux.py
env -u GIT_INDEX_FILE git commit -m "fix(prod-pulid): FLUX-native PuLID in pulid.json (SDXL ApplyPulid was a FLUX no-op)

Nodes 99/100/101 -> PulidFluxModelLoader/ApplyPulidFlux/PulidFluxEvaClipLoader
(pulid_flux_v0.9.1, start_at=0.0, model=[112,0] direct — no LoRA). Closes the
data-integrity no-op (ADR-024). Regression test pins the FLUX classes." -- pulid.json tests/unit/test_pulid_production_flux.py
```

---

### Task 2: Align `workflow_selector` start_at + fix the stale docstring

**Files:**
- Modify: `workflow_selector.py` (`WORKFLOW_TEMPLATES` `pulid_start_at`; docstring line 512)
- Test: `tests/unit/test_pulid_production_flux.py` (add the template assertion)

**Why:** `apply_workflow_params` writes `params["pulid_start_at"]` onto node 100 at runtime (`workflow_selector.py:520`). If the templates keep the SDXL-era values (0.2–0.35), they overwrite the JSON's new `0.0` on every render and re-suppress the coarse-identity window — making Task 1 net-zero.

- [x] **Step 1: Add the failing test**

Append to `tests/unit/test_pulid_production_flux.py`:

```python
def test_production_pulid_start_at_is_flux_zero():
    """Character-bearing classes must start PuLID at 0.0 (FLUX coarse-identity
    window). Otherwise apply_workflow_params overwrites the graph default and
    re-suppresses the swap. landscape has pulid_weight 0.0 (PuLID off) so its
    start_at is irrelevant."""
    import workflow_selector as ws
    for cls in ("portrait", "medium", "wide", "action"):
        assert ws.WORKFLOW_TEMPLATES[cls]["pulid_start_at"] == 0.0, cls
```

- [x] **Step 2: Run to verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_pulid_production_flux.py::test_production_pulid_start_at_is_flux_zero -v`
Expected: FAIL — portrait is currently 0.2.

- [x] **Step 3: Edit `workflow_selector.py`**

In `WORKFLOW_TEMPLATES`, set `pulid_start_at` to `0.0` for these four classes (find each by its current value):
- portrait: `"pulid_start_at": 0.2` → `"pulid_start_at": 0.0`
- medium: `"pulid_start_at": 0.25` → `"pulid_start_at": 0.0`
- wide: `"pulid_start_at": 0.35` → `"pulid_start_at": 0.0`
- action: `"pulid_start_at": 0.3` → `"pulid_start_at": 0.0`
- landscape: leave as-is (`0.0`, PuLID off).

Fix the stale docstring at `workflow_selector.py:512`:
- from: `    - Node 100 (ApplyPulid): weight, start_at, end_at, method`
- to:   `    - Node 100 (ApplyPulidFlux): weight, start_at, end_at, fusion`

(Optional consistency tweak, not required: the fallback default in `apply_workflow_params` is `params.get("pulid_start_at", 0.3)` — a latent SDXL value. Every template supplies the key, so it is dead, but you may lower it to `0.0` to match. The spec scoped this out; leave it unless trivial.)

- [x] **Step 4: Run to verify it passes**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_pulid_production_flux.py -v`
Expected: PASS (5 tests).

- [x] **Step 5: Commit**

```bash
env -u GIT_INDEX_FILE git add -- workflow_selector.py tests/unit/test_pulid_production_flux.py
env -u GIT_INDEX_FILE git commit -m "fix(prod-pulid): pulid_start_at 0.0 for FLUX + fix stale ApplyPulid docstring

apply_workflow_params writes start_at onto node 100 at runtime; SDXL-era
0.2-0.35 would re-suppress the FLUX coarse-identity window. Test pins 0.0." -- workflow_selector.py tests/unit/test_pulid_production_flux.py
```

---

### Task 3: Full-suite + smoke regression gate

**Files:** none (verification only).

- [x] **Step 1: Run the smoke block**

Run: `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py`
Expected: ends with `OK` (the ~55 PROGRAM-MANUAL doc-anchor drifts are advisory).

- [x] **Step 2: Run the full suite**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest -q`
Expected: PASS (baseline this session was 2244 passed / 2 skipped; expect 2244+5 new − overlaps, no failures). No test pins `pulid_start_at` (verified), so the template change should not break anything. If a workflow_selector test fails on a structural assumption, read it and update it to reflect the new value — do NOT revert the fix.

- [x] **Step 3: Commit only if Step 2 required a test update**

```bash
env -u GIT_INDEX_FILE git add -- tests/<the-updated-test>.py
env -u GIT_INDEX_FILE git commit -m "test(prod-pulid): update <test> for FLUX-native start_at=0.0" -- tests/<the-updated-test>.py
```

---

## Chunk 2: Pod acceptance gate — COMPLETE ✅ (PASSED 2026-06-13)

> **GO.** Pod acceptance gate PASSED 2026-06-13 (operator-run, user-directed). PuLID-OFF arc **0.6205** → PuLID-ON arc **0.8779** (Δ +0.257), seed 990011, peak VRAM 18.2 GiB, fp8 (node 112 `flux1-dev-fp8`) + FaceDetailer-free + visually photoreal. All four Step-4 GO criteria met (material lift / FaceDetailer-free binding / fp8 compat / visual photoreal). Artifact: `logs/prod_pulid_acceptance_20260613.json` (logs/ gitignored; reproduce via the committed instrument `scripts/_prod_pulid_acceptance.py`, `a43358f`). **The FLUX-native production PuLID fix is the shipping default.** Decision record: ADR-025 (DECISIONS.md). Original "BLOCKED" gate text preserved in git history.

### Task 4: Pod before/after identity validation

**Goal:** prove (a) the fix restores identity on the FLUX fp8 production graph, and (b) it does so without FaceDetailer.

**Procedure (controlled A/B on the same prompt + seed + reference face):**

- [x] **Step 1 — PuLID-OFF baseline (no identity):** render the production graph with the PuLID nodes bypassed (the existing no-character path pops 93/97/99/100/101, rewires PAG 301 → `["112",0]`). Do this as a direct pod `/prompt` submit of the modified graph JSON — a small standalone script mirroring the experiment driver's `render_leg` (`scripts/_max_passBa_masked_pulid.py`) — NOT via a full `generate_ai_broll` pipeline call. Arc-score the face identity against the reference. Expected: low (plain FLUX txt2img, no lock).

- [x] **Step 2 — PuLID-ON (fixed graph):** render the fixed production `pulid.json` with the reference face on node 93, same prompt + seed. Arc-score against the same reference.

- [x] **Step 3 — Read with the deterministic scorer** (post `d48b58b`, the OpenCV thread-race fix): use `scripts/_arc_score_session.py` single-artifact. Show both renders in Preview.

- [x] **Step 4 — GO/NO-GO:**
  - GO if PuLID-ON identity rises materially over the PuLID-OFF baseline (target toward ~0.87 for a single clean face) AND the render is visually photoreal AND a face is detectable (no NO_FACE — confirms FaceDetailer-free binding).
  - If NO_FACE / weak: the design's follow-up is to add FaceDetailer (node 600) — a NEW spec/ADR, not this plan.
  - If the lock is weak in a way consistent with fp8 truncation: escalate the fp16-UNet decision (follow-up ADR; no fp16 asset is in scope).

- [x] **Step 5 — Record the measurement** per R-MEASURE: persist the two arc scores + render md5s to a `logs/` artifact and cite them in the GO/NO-GO note. Only then is the fix cleared to be the shipping default.

---

## Out of scope (do not implement here)
- LoRA / dual-identity production support (ADR-024 experiment driver `scripts/_prod_dual_lora_pulid.py`).
- `COMFYUI_PULID` provenance tag split (SDXL vs FLUX).
- Per-class FLUX re-tuning of `pulid_weight` / `pulid_end_at` / `fusion`.
- The `continuity_engine` / `character_manager` sibling data-integrity surfaces (separate lane).
- SDXL `ip-adapter_pulid_sdxl_fp16.safetensors` pod-disk reclamation.
