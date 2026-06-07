# Portrait / aspect-aware delivery — Phase 1 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make output dimensions aspect-ratio-aware end-to-end at the *container* level — one resolver feeds assembly + scorecard, and a single gate (`SUPPORTED_ASPECT_RATIOS`) keeps `9:16` unselectable until Phase 3, while fixing the latent bug where the UI offers aspect ratios that do nothing.

**Architecture:** New pure module `cinema/aspect.py` is the single source of truth (`resolve_output_dimensions`, `SUPPORTED_ASPECT_RATIOS`). Assembly (`cinema_pipeline.py`), the scorecard (`cinema/capability_scorecard.py`), and the UI/API gates (`web_server.py`, `ProductionSection.tsx`) all import from it. 16:9 behavior stays byte-identical; `9:16` is exercised by tests but gated out of user selection.

**Tech Stack:** Python 3.13 (stdlib only for `cinema/aspect.py`), pytest, Flask (`web_server.py`), React/TS (`web/`), ffmpeg (assembly).

**Spec:** `docs/superpowers/specs/2026-06-07-portrait-aspect-delivery-design.md`

**Conventions (per CLAUDE.md / repo):**
- Run pytest as `env -u GIT_INDEX_FILE .venv/bin/python -m pytest ...` (D-a: bare runs false-fail `test_check_doc_claims.py` via temp-repo git).
- Before each `git commit`: `git read-tree HEAD` (clears a phantom per-seat index entry that aborts commits). Commit with explicit pathspec; `-m "..."` BEFORE `-- <paths>`.
- §15 smoke: `.venv/bin/python scripts/ci_smoke.py`. FE gate: `cd web && npx tsc --noEmit && npm run build`.
- Co-Authored-By trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `cinema/aspect.py` | Create | Single source of truth: aspect→dims resolver + supported-ratio gate + `is_portrait`/`is_supported` |
| `tests/unit/test_cinema_aspect.py` | Create | Unit tests for the resolver, gate, and the assembly `_normalize_filter` golden string |
| `cinema_pipeline.py` | Modify (`_assemble_final`: insert ~1329, swap `-vf` at 1337) | `_normalize_filter(w,h)` helper + derive (W,H) from `settings["aspect_ratio"]` |
| `cinema/capability_scorecard.py` | Modify (`_build_media_block` ~90-94) | Derive expected dims from project `aspect_ratio` instead of `EXPECTED_RESOLUTION` |
| `tests/unit/test_u3_media_conformance.py` | Modify | Scorecard `format.pass` per aspect ratio |
| `web_server.py` | Modify (`/api/config` :319; PUT ~:514-518) | Gate the dropdown list + reject unsupported aspect on PUT |
| `tests/unit/test_web_server_aspect_validation.py` | Create | `/api/config` list + PUT 400/200/backward-compat |
| `web/src/components/settings/ProductionSection.tsx` | Modify (:148) | Close the FE fallback gate hole |

---

## Chunk 1: Phase 1 Foundation

### Task 1: `cinema/aspect.py` — single source of truth

**Files:**
- Create: `cinema/aspect.py`
- Test: `tests/unit/test_cinema_aspect.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_cinema_aspect.py`:

```python
"""Phase 1 — cinema/aspect.py: aspect→dims resolver + supported-ratio gate."""
from cinema.aspect import (
    resolve_output_dimensions, is_portrait, is_supported,
    ASPECT_DIMENSIONS, DEFAULT_ASPECT_RATIO, SUPPORTED_ASPECT_RATIOS,
)


def test_resolve_landscape():
    assert resolve_output_dimensions("16:9") == (1920, 1080)


def test_resolve_portrait():
    assert resolve_output_dimensions("9:16") == (1080, 1920)


def test_resolve_unknown_empty_none_default_to_landscape():
    # never raises; unknown/empty/None → DEFAULT dims
    assert resolve_output_dimensions("4:3") == (1920, 1080)
    assert resolve_output_dimensions("") == (1920, 1080)
    assert resolve_output_dimensions(None) == (1920, 1080)


def test_is_portrait():
    assert is_portrait("9:16") is True
    assert is_portrait("16:9") is False
    assert is_portrait(None) is False  # default is landscape


def test_is_supported_gate_excludes_9_16_until_phase3():
    assert is_supported("16:9") is True
    assert is_supported("9:16") is False   # gated until Phase 3 flips the constant
    assert is_supported("4:3") is False


def test_default_ratio_is_supported_and_known():
    assert DEFAULT_ASPECT_RATIO in SUPPORTED_ASPECT_RATIOS
    assert DEFAULT_ASPECT_RATIO in ASPECT_DIMENSIONS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cinema_aspect.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'cinema.aspect'`

- [ ] **Step 3: Write minimal implementation**

Create `cinema/aspect.py`:

```python
"""Single source of truth for output aspect ratio → delivery dimensions.

Phase 1 of portrait/aspect-aware delivery
(docs/superpowers/specs/2026-06-07-portrait-aspect-delivery-design.md).
Pure module, stdlib only. Every surface that fixes a delivery dimension
(assembly, scorecard) and every gate (UI /api/config, settings PUT) imports
from here so dimensions + the supported-ratio set live in ONE place.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

ASPECT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
}
DEFAULT_ASPECT_RATIO = "16:9"

# The GATE. Phase 3's final task appends "9:16" once native generation lands.
# Everything that offers/validates aspect ratios to the client reads this list.
SUPPORTED_ASPECT_RATIOS: list[str] = ["16:9"]


def resolve_output_dimensions(aspect_ratio: Optional[str]) -> tuple[int, int]:
    """Return (width, height) for ``aspect_ratio``.

    Unknown / empty / None → DEFAULT dims. Never raises — assembly and the
    scorecard must not crash on a bad or absent setting.
    """
    dims = ASPECT_DIMENSIONS.get(aspect_ratio or "")
    if dims is None:
        logger.debug("unknown aspect_ratio %r → default %s",
                     aspect_ratio, DEFAULT_ASPECT_RATIO)
        return ASPECT_DIMENSIONS[DEFAULT_ASPECT_RATIO]
    return dims


def is_portrait(aspect_ratio: Optional[str]) -> bool:
    """True when the resolved dimensions are taller than wide."""
    w, h = resolve_output_dimensions(aspect_ratio)
    return h > w


def is_supported(aspect_ratio: Optional[str]) -> bool:
    """True when ``aspect_ratio`` is a currently-offered ratio (the gate)."""
    return aspect_ratio in SUPPORTED_ASPECT_RATIOS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cinema_aspect.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git read-tree HEAD
git commit -m "feat(aspect): cinema/aspect.py — single source of truth for aspect→dims + gate

Phase 1 of portrait delivery. resolve_output_dimensions / is_portrait /
is_supported + SUPPORTED_ASPECT_RATIOS gate (['16:9'] until Phase 3).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- cinema/aspect.py tests/unit/test_cinema_aspect.py
```

---

### Task 2: assembly — `_normalize_filter` + derive dims from `aspect_ratio`

**Files:**
- Modify: `cinema_pipeline.py` (add `_normalize_filter`; `_assemble_final` ~1334-1341)
- Test: `tests/unit/test_cinema_aspect.py` (append)

> **Placement (resolved, plan-review):** `_normalize_filter` lives in `cinema_pipeline.py` as a **module-level pure function** (not a method). Importing `cinema_pipeline` in a unit test is safe and idiomatic — 8 existing unit tests already do it (e.g. `tests/unit/test_u3_media_conformance.py`), so `from cinema_pipeline import _normalize_filter` is fine. Do NOT move it to `aspect.py`.

- [ ] **Step 1: Write the failing test** — append to `tests/unit/test_cinema_aspect.py`. *(The `from cinema_pipeline import _normalize_filter` is intentionally **function-local**, not module-top, so Task 1's 6 tests keep collecting/passing until `_normalize_filter` lands in this task. All tests in this file are module-level functions — 8 total after this step.)*

```python
# --- assembly normalize filter (byte-identical 16:9 regression guard) ---
GOLDEN_16x9 = ("scale=1920:1080:force_original_aspect_ratio=decrease,"
               "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30")


def test_normalize_filter_16x9_is_byte_identical():
    from cinema_pipeline import _normalize_filter
    assert _normalize_filter(1920, 1080) == GOLDEN_16x9


def test_normalize_filter_portrait():
    from cinema_pipeline import _normalize_filter
    assert _normalize_filter(1080, 1920) == (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,fps=30"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cinema_aspect.py -q`
Expected: FAIL — `ImportError: cannot import name '_normalize_filter'`

- [ ] **Step 3: Write minimal implementation**

In `cinema_pipeline.py`, add the import with the other cinema imports at **lines 24-32** (after `from cinema.shots.controller import ShotController` at :32):

```python
from cinema.aspect import resolve_output_dimensions, DEFAULT_ASPECT_RATIO
```

Add the pure helper at module level (near the other module-level helpers, above the pipeline class):

```python
def _normalize_filter(w: int, h: int) -> str:
    """ffmpeg -vf for clip normalization at (w,h): fit-inside + pad + 30fps.

    16:9 (1920,1080) reproduces the historical literal byte-for-byte.
    """
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps=30")
```

Then in `_assemble_final` replace the hard-coded `-vf` value (current lines ~1336-1337):

```python
                # Normalize resolution + fps without forcing duration or stripping audio
                cmd = [
                    "ffmpeg", "-y", "-i", clip_path,
                    "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30",
```

with (derive dims once, before the loop — `settings` is already a param of `_assemble_final`):

```python
        # Phase 1: container dims from the project aspect_ratio (default 16:9).
        out_w, out_h = resolve_output_dimensions(
            settings.get("aspect_ratio", DEFAULT_ASPECT_RATIO))
        norm_vf = _normalize_filter(out_w, out_h)
```
…and in the loop:
```python
                    "-vf", norm_vf,
```

> **Exact placement (verified):** insert the two derive-dims lines immediately after `all_normalized = []` (line **1329**) and before `for clip_path in all_clips:` (line **1330**). Then replace ONLY the `-vf` literal currently at line **1337** with `"-vf", norm_vf,`. Do NOT change any other line of the command. (`scene_transitions` at :1294 is far above — no confusion.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cinema_aspect.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git read-tree HEAD
git commit -m "feat(assembly): derive normalize dims from aspect_ratio via resolver (16:9 byte-identical)

_normalize_filter pure helper + _assemble_final reads settings.aspect_ratio.
16:9 output unchanged (golden-string asserted).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- cinema_pipeline.py tests/unit/test_cinema_aspect.py
```

---

### Task 3: scorecard — derive expected dims from `aspect_ratio`

**Files:**
- Modify: `cinema/capability_scorecard.py` (`_build_media_block`, ~90-94; add import)
- Test: `tests/unit/test_u3_media_conformance.py` (append)

- [ ] **Step 1: Write the failing test** — append a class to `tests/unit/test_u3_media_conformance.py`:

```python
class TestMediaBlockAspectAware:
    """Phase 1: format.pass derives expected dims from project aspect_ratio."""

    def _report(self, w, h):
        return {"format": {"width": w, "height": h, "vcodec": "h264", "acodec": "aac"},
                "measured_at": "2026-06-07T00:00:00Z"}

    def test_landscape_project_1920x1080_passes(self):
        from cinema.capability_scorecard import _build_media_block
        proj = {"global_settings": {"aspect_ratio": "16:9"}, "media_report": self._report(1920, 1080)}
        blk = _build_media_block(proj)
        assert blk["format"]["pass"] is True

    def test_portrait_project_1080x1920_passes(self):
        from cinema.capability_scorecard import _build_media_block
        proj = {"global_settings": {"aspect_ratio": "9:16"}, "media_report": self._report(1080, 1920)}
        blk = _build_media_block(proj)
        assert blk["format"]["pass"] is True

    def test_portrait_project_landscape_file_fails(self):
        from cinema.capability_scorecard import _build_media_block
        proj = {"global_settings": {"aspect_ratio": "9:16"}, "media_report": self._report(1920, 1080)}
        blk = _build_media_block(proj)
        assert blk["format"]["pass"] is False

    def test_missing_aspect_defaults_to_landscape(self):
        from cinema.capability_scorecard import _build_media_block
        proj = {"global_settings": {}, "media_report": self._report(1920, 1080)}
        blk = _build_media_block(proj)
        assert blk["format"]["pass"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_u3_media_conformance.py::TestMediaBlockAspectAware -q`
Expected: FAIL — `test_portrait_project_1080x1920_passes` fails (expected dims still hard-coded 1920×1080)

- [ ] **Step 3: Write minimal implementation**

In `cinema/capability_scorecard.py`, add the import at the top (near the existing `from cinema.media_probe import probe_media` or the other imports):

```python
from cinema.aspect import resolve_output_dimensions, DEFAULT_ASPECT_RATIO
```

In `_build_media_block`, replace the constant comparison at ~:94. Current:
```python
            resolution_ok = (w, h) == EXPECTED_RESOLUTION
```
with (derive from the project's aspect; `project` is in scope):
```python
            gs = project.get("global_settings", {}) or {}
            expected_res = resolve_output_dimensions(
                gs.get("aspect_ratio") or DEFAULT_ASPECT_RATIO)
            resolution_ok = (w, h) == expected_res
```

> Leave `EXPECTED_RESOLUTION` defined (it documents the default and may be referenced elsewhere — grep first: `grep -n EXPECTED_RESOLUTION cinema/ -r`). Only the *comparison* changes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_u3_media_conformance.py -q`
Expected: PASS (all U3 tests incl. the 4 new ones)

- [ ] **Step 5: Commit**

```bash
git read-tree HEAD
git commit -m "feat(scorecard): derive format.pass expected dims from aspect_ratio (closes F4 at scorecard)

_build_media_block uses resolve_output_dimensions(project aspect) instead of the
fixed EXPECTED_RESOLUTION, so a 9:16 project is scored against 1080x1920.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- cinema/capability_scorecard.py tests/unit/test_u3_media_conformance.py
```

---

### Task 4: `/api/config` — source the dropdown from the gate

**Files:**
- Modify: `web_server.py` (`/api/config` :319; add import)
- Test: `tests/unit/test_web_server_aspect_validation.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_web_server_aspect_validation.py`:

```python
"""Phase 1 — /api/config gate + PUT aspect validation."""
import json
import pytest

from cinema.aspect import SUPPORTED_ASPECT_RATIOS


@pytest.fixture
def client():
    import web_server
    web_server.app.config["TESTING"] = True
    with web_server.app.test_client() as c:
        yield c


def test_config_aspect_ratios_is_gated(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["aspect_ratios"] == SUPPORTED_ASPECT_RATIOS  # ["16:9"] until Phase 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_web_server_aspect_validation.py::test_config_aspect_ratios_is_gated -q`
Expected: FAIL — `aspect_ratios` is the hard-coded 5-list, not `["16:9"]`

- [ ] **Step 3: Write minimal implementation**

In `web_server.py`, add the import next to the existing cinema imports at **lines 55-57** (`from cinema_pipeline import CinemaPipeline` etc.):
```python
from cinema.aspect import SUPPORTED_ASPECT_RATIOS, is_supported
```
*(`jsonify` is already imported at `web_server.py:37` — Task 5's 400 response needs no new import.)*

Replace `/api/config` line 319:
```python
        "aspect_ratios": ["16:9", "9:16", "1:1", "21:9", "4:3"],
```
with:
```python
        "aspect_ratios": SUPPORTED_ASPECT_RATIOS,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_web_server_aspect_validation.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git read-tree HEAD
git commit -m "feat(web): gate /api/config aspect_ratios to SUPPORTED_ASPECT_RATIOS (fixes latent bug)

UI dropdown sourced from the gate; stops offering 9:16/1:1/21:9/4:3 that never
worked. Until Phase 3 this is ['16:9'].

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- web_server.py tests/unit/test_web_server_aspect_validation.py
```

---

### Task 5: PUT `/api/projects/<pid>` — reject unsupported aspect_ratio (API gate)

**Files:**
- Modify: `web_server.py` (the `_mutate_project` closure inside `api_update_project`, ~:514-518)
- Test: `tests/unit/test_web_server_aspect_validation.py` (append)

> **Verified context (spec §4.5):** the closure runs `Project.model_validate(project)` then `project["global_settings"].update(...)`. The model is `extra="allow"` → it will NOT reject a bad `aspect_ratio`. A **bespoke** check is required, placed BEFORE the `.update()`, and only when `aspect_ratio` is present (partial updates must stay valid — e.g. editing `language` on a project whose stored aspect is a now-removed `1:1`).

- [ ] **Step 1: Write the failing test** — append (reuses the `client` fixture from Task 4 already in this file):

```python
def _make_project(tmp_path, monkeypatch) -> str:
    """Create a real persisted project under tmp_path; return its pid.

    Verified: domain.project_manager.create_project(name) -> dict (always),
    pid = dict["id"] (project_manager.py:605-617). _project_dir / _project_file
    read the module-global PROJECTS_DIR at call time (project_manager.py:48-52),
    and web_server uses domain.project_manager.mutate_project (same module), so
    patching PROJECTS_DIR on domain.project_manager is resolved consistently.
    """
    from domain import project_manager
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    return project_manager.create_project("aspect-test")["id"]


def test_put_rejects_unsupported_aspect_ratio(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)
    resp = client.put(f"/api/projects/{pid}",
                      json={"global_settings": {"aspect_ratio": "9:16"}})
    assert resp.status_code == 400
    body = json.loads(resp.data)
    assert "aspect_ratio" in (body.get("error", "") + str(body))
    assert body.get("supported") == SUPPORTED_ASPECT_RATIOS


def test_put_accepts_supported_aspect_ratio(client, tmp_path, monkeypatch):
    pid = _make_project(tmp_path, monkeypatch)
    resp = client.put(f"/api/projects/{pid}",
                      json={"global_settings": {"aspect_ratio": "16:9"}})
    assert resp.status_code == 200


def test_put_without_aspect_ratio_is_unaffected(client, tmp_path, monkeypatch):
    # Backward-compat: editing an unrelated field must NOT trip the aspect gate,
    # even if the project's stored aspect is a now-unsupported value.
    pid = _make_project(tmp_path, monkeypatch)
    resp = client.put(f"/api/projects/{pid}",
                      json={"global_settings": {"language": "Korean"}})
    assert resp.status_code == 200
```

> **Verified fixture (plan-review):** `create_project(name)` always returns a dict (`project_manager.py:617`); `["id"]` is the pid. The `monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path))` form works because `_project_dir`/`_project_file`/`mutate_project` resolve `PROJECTS_DIR` from `domain.project_manager` at call time. (Codebase-idiomatic alternative: patch-based mocking with no filesystem, per `tests/unit/test_web_server_auto_approve.py:30-50` — either is acceptable.)

- [ ] **Step 2: Run test to verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_web_server_aspect_validation.py -q`
Expected: FAIL — `test_put_rejects_unsupported_aspect_ratio` returns 200 (no validation yet)

- [ ] **Step 3: Write minimal implementation**

In `web_server.py` `api_update_project` (verified structure: `@_project_lock_guard`; busy-check at `:501-503`; `data = request.json or {}` at `:505`; `_mutate_project` closure defined `:507`, called `:521`; 404 returned `:522-523` when `mutate_project` returns `None`). There is **no** explicit project-exists check. Add the guard **immediately after `data = request.json or {}` (line 505) and before the `_mutate_project` closure (line 507)**:

```python
        incoming_gs = data.get("global_settings") or {}
        if "aspect_ratio" in incoming_gs and not is_supported(incoming_gs["aspect_ratio"]):
            return jsonify({
                "error": "unsupported aspect_ratio",
                "value": incoming_gs["aspect_ratio"],
                "supported": SUPPORTED_ASPECT_RATIOS,
            }), 400
```

> A bad `pid` still 404s: the guard only rejects when `aspect_ratio` is present-and-unsupported; otherwise the request falls through to `mutate_project`, which returns `None` → 404 at `:522-523`. So `test_put_without_aspect_ratio_is_unaffected` (valid pid, no aspect) reaches mutate normally. Only checks when `aspect_ratio` is present (partial updates stay valid).

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_web_server_aspect_validation.py -q`
Expected: PASS (all 4)

- [ ] **Step 5: Commit**

```bash
git read-tree HEAD
git commit -m "feat(web): reject unsupported aspect_ratio on PUT /api/projects/<pid> (API gate)

Bespoke check before global_settings.update (model is extra='allow' so
model_validate won't reject). Only when aspect_ratio present; 400 + supported list.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- web_server.py tests/unit/test_web_server_aspect_validation.py
```

---

### Task 6: FE — close the `ProductionSection.tsx` fallback gate hole

**Files:**
- Modify: `web/src/components/settings/ProductionSection.tsx:148`

> No FE test runner exists; the gate is `tsc --noEmit` + `npm run build`.

- [ ] **Step 1: Make the change**

At line 148, change the hard-coded fallback so a null/missing config can't reintroduce gated ratios. Current:
```tsx
          {(config?.aspect_ratios || ['16:9', '9:16', '1:1']).map((ar) => (
```
to:
```tsx
          {(config?.aspect_ratios || ['16:9']).map((ar) => (
```

> Rationale: when `/api/config` hasn't loaded, fall back to the safe default only. The server is the source of truth; this fallback must never offer a ratio the server gates out.

- [ ] **Step 2: Verify the FE gate** *(run `npm install` first if `web/node_modules` is absent)*

Run (from repo root): `cd web && npx tsc --noEmit && npm run build`
Expected: tsc clean (0 errors); build succeeds.

- [ ] **Step 3: Commit**

```bash
git read-tree HEAD
git commit -m "fix(web): ProductionSection aspect fallback -> ['16:9'] (close gate hole)

The hard-coded ['16:9','9:16','1:1'] fallback bypassed the /api/config gate when
config was null. Safe default only.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- web/src/components/settings/ProductionSection.tsx
```

---

### Task 7: Full regression gate

**Files:** none (verification only)

- [ ] **Step 1: Full unit suite**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q`
Expected: **1682 baseline + 16 new = 1698 passed; 0 failures** (new: 6 Task1 + 2 Task2 + 4 Task3 + 1 Task4 + 3 Task5; baseline verified 2026-06-07 via `pytest tests/unit --co -q` → 1682). Confirm no existing test regressed — especially `_assemble_final`/U3 tests.

- [ ] **Step 2: §15 smoke**

Run: `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py`
Expected: `OK`

- [ ] **Step 3: FE gate**

Run (from repo root): `cd web && npx tsc --noEmit && npm run build`
Expected: clean.

- [ ] **Step 4: Manual confirmation of the gate property**

Confirm `9:16` is NOT user-selectable: `/api/config` returns `["16:9"]`; PUT `9:16` → 400. The resolver/assembly/scorecard *can* handle `9:16` (unit-tested) but it is gated out of selection until Phase 3.

---

## Phase 1 acceptance

- `cinema/aspect.py` is the only place dimensions + supported ratios are defined; assembly + scorecard + both gates import from it.
- 16:9 output byte-identical (golden-string asserted); all prior tests green.
- `9:16` exercised by unit tests but unselectable (UI list + API 400).
- Latent bug fixed: UI no longer offers non-functional ratios.
- Out of scope (Phases 2/3): native image/video generation; un-gating `9:16`.
