# Part 4 — Capability Dashboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the pipeline's quality/health signal in a new "Capability" dashboard — a per-project capability scorecard (measured-vs-bar), per-shot quality scores, and cascade provenance — so operators can see whether a run hit its bars and which engine actually produced each shot.

**Architecture:** Hybrid. A new read-only Python endpoint `GET /api/projects/<pid>/capability-scorecard` computes the scorecard (dimension bars, gate rollup, LoRA summary, component status, routing) server-side — the single source of truth, pytest-tested. A new 4th React app mode `'capability'` renders that JSON plus per-shot tables read directly from the existing `/api/projects/<pid>` project JSON. No new persistence is required for the core feature (data already on takes); coherence persistence is an independent enhancement.

**Tech Stack:** Python 3.13 + Flask (`web_server.py`); pytest (`.venv/bin/python -m pytest`). React 19 + TypeScript 5.7 + Vite 6 + Tailwind 3.4 (`web/`). No router (state-driven modes). No frontend test runner — `tsc --noEmit` + `npm run build` are the frontend gate.

**Spec:** `docs/superpowers/specs/2026-06-04-part4-ui-surfacing-design.md`

---

## Critical context (verified at HEAD `534abc9`, 2026-06-04) — read before any task

The implementer has zero session context. These facts were grep-verified; **re-verify line numbers at your HEAD** (they drift), but the shapes hold:

- **Read-only endpoint pattern** = `api_get_project` (`web_server.py:480-485`): `@app.route("/api/projects/<pid>", methods=["GET"])`, `project = load_project(pid)`, `if not project: return jsonify({"error": "Project not found"}), 404`, else `return jsonify(...)`. **Mirror THIS (GET), not the POST mutators** — no `@_project_lock_guard`, no `_reject_if_project_busy`. `load_project`, `jsonify`, `request`, `app` are already imported in `web_server.py`.
- **`load_project(pid)` returns a plain `dict` or `None`** (`domain/project_manager.py:679`). Shots/takes are **dicts** at runtime (Pydantic models in `domain/models.py` are validation-only, all `extra="allow"`). Read with `.get()`.
- **Project has NO top-level `shots`.** Shots are `project["scenes"][i]["shots"][j]`. Iterate: `[sh for sc in project.get("scenes", []) for sh in sc.get("shots", [])]`.
- **Take shape** (dict): `take["metadata"]` (dict: `identity_score`, `motion_fidelity`, `lipsync_score`, `lipsync_cascade`, …), `take["cascade_metadata"]` (dict: `engine`, `score?`, `threshold?`, `fallback?`, `attempts?`). Read: `take.get("cascade_metadata", {}).get("engine", "")`.
- **Take lists on a shot:** `keyframe_takes`, `motion_takes`, `postprocess_variants`, `performance_takes` (+ `approved_*_take_id`). `auto_approve_audit` is a list of `{gate, auto_approved, vetoes, rule_names, timestamp}` (an `extra` key; read `shot.get("auto_approve_audit") or []`).
- **coherence_score is NOT on take.metadata** (grep-confirmed). It lands in `shot["diagnostics"][*]["scores"]["coherence"]` (written by `diagnose_clip`, `cinema/shots/controller.py:1867`) and the live SSE (`web_services.py:82`). **The scorecard reads coherence defensively** (see Task 2); Task 1 optionally persists it.
- **Quality bars are distributed (NOT in `config/settings.py`):**
  - Gate bars: `AutoApproveConfig.from_project(project)` (`cinema/auto_approve.py`) — tier-aware resolved values (`motion_min_identity=0.85`, `motion_min_motion_score=0.7`, `final_min_lipsync=0.8`, image composite default `0.97` max / `0.60` production). **Use `.from_project(project)` — it applies tier + project overrides.**
  - Coherence floor `0.6` and lipsync gate `0.65` are inline `global_settings.get("coherence_threshold", 0.6)` / `.get("lipsync_validation_threshold", 0.65)` literals.
  - LoRA: `prep/lora_quality.py` module consts `PASS_THRESHOLD=0.6`, `NET_NEGATIVE_BASELINE=0.45`.
- **LoRA status:** `get_lora_status(project_dir, char_id) -> dict` (`prep/lora_training.py:251`) with keys `status`, `quality_score`, `best_strength`, `rejected`, `quality_warning`, `lora_path`. **Takes a project DIR**, resolve via `get_project_dir(pid)` (`domain/project_manager.py:1066`). `validate_lora_quality` returns a `LoraQualityResult` dataclass (use `dataclasses.asdict`).
- **pipeline_status.toml** uses `[[component]]` tables with `id`/`title`/`status`/`anchor`/`note` (`status` ∈ live|wired|stubbed|parked|dead). Parse with stdlib `tomllib` (raw rows — no anchor validation needed for the UI).
- **pytest convention** (`tests/unit/test_reassemble_endpoint.py`): `from web_server import app`; `client` fixture sets `app.config["TESTING"]=True`, yields `app.test_client()`; **patch `web_server.load_project`** (where it's used); class-grouped tests; local `_make_project(...)` dict-builder. Runner: `.venv/bin/python -m pytest`.
- **Frontend has NO test runner** (no vitest/jest/testing-library, zero `*.test.tsx`). Frontend verification = `cd web && npx tsc --noEmit` + `npm run build`. Do NOT stand up a test harness (scope creep).
- **Frontend nav** = `useState<'setup'|'pipeline'|'console'>` in `App.tsx:18` + early-`return` guards; no router. Mode views get the full `project` object as a prop and derive `projectId = project?.id`.
- **Console palette ≠ editorial palette.** Console components (`Telemetry`, `DirectorsConsole`) hand-roll labels: `text-eyebrow-lg uppercase tracking-wider text-console-ink-mute font-console-mono`. They do NOT use `ui/Eyebrow` or `ui/Button` (those are `editorial-*` themed). **CapabilityConsole mirrors the raw console className idiom.**
- **Shared-tree discipline:** the director is live on this branch. Every commit uses an explicit pathspec (`git commit -- <paths>`), never `git add -A`/`commit -a`. Run `git log --oneline -1` immediately before each commit (Rule #7).

---

## File structure

**Backend (Python):**
- Modify: `web_server.py` — add `api_capability_scorecard(pid)` (read-only GET) near the other project GETs.
- Create: `cinema/capability_scorecard.py` — the pure aggregation function `build_capability_scorecard(project, *, project_dir) -> dict` (keeps `web_server.py` thin + makes it unit-testable without Flask).
- Modify (Task 1, optional enhancement): `cinema/shots/controller.py` — persist `coherence_score` onto the take via `_mutate_shot`.
- Create: `tests/unit/test_capability_scorecard.py` — pytest for the builder + the endpoint.

**Frontend (TypeScript/React):**
- Modify: `web/src/types/project.ts` — add the `CapabilityScorecard` response interface.
- Modify: `web/src/App.tsx` — add `'capability'` mode + guard + import.
- Modify: `web/src/components/EditorialShell.tsx` — add `onOpenCapability` nav button.
- Create: `web/src/components/console/CapabilityConsole.tsx` — the dashboard view (shell + fetch + sections).

Each file has one responsibility; the aggregation logic is isolated in `cinema/capability_scorecard.py` so it is testable independent of Flask.

---

## Chunk 1: Backend — scorecard builder + endpoint (+ optional coherence persistence)

### Task 1: Coherence persistence (enhancement — de-risked, scorecard does not hard-depend on it)

**Goal:** make `coherence_score` available on a take's metadata so the scorecard reads it uniformly. **Discovery-gated:** coherence is currently computed in `diagnose_clip` and emitted live, but not persisted to takes. If a clean main-run persistence site exists, add it; otherwise document that coherence is diagnostics-sourced and STOP (Task 2 reads `shot.diagnostics` as fallback).

**Files:**
- Modify: `cinema/shots/controller.py` (the coherence computation site)
- Test: `tests/unit/test_capability_scorecard.py` (the persistence assertion)

- [ ] **Step 1: Locate the canonical coherence write.** Run `grep -rn "coherence" cinema/shots/controller.py web_services.py` and find where `coherence_score` reaches the progress callback during a NORMAL run (not only `diagnose_clip`). Report findings. If coherence is computed only in `diagnose_clip` (`:1867`, writes `result["scores"]["coherence"]` → `shot["diagnostics"]`), record that and **skip to Task 2** (the scorecard reads `shot.diagnostics`); mark this task DONE_WITH_CONCERNS noting "coherence is diagnostics-sourced; no take-metadata persistence added."

- [ ] **Step 2 (only if a main-run site exists): Write the failing test.** In `tests/unit/test_capability_scorecard.py`:

```python
def test_coherence_persisted_to_take_metadata():
    """After the coherence step, the approved take carries metadata.coherence_score."""
    # build a controller/shot fixture per the discovered site; assert
    # take["metadata"]["coherence_score"] is set to the computed value.
    ...  # shape per the discovered call site
```

- [ ] **Step 3: Run it, verify FAIL.** `.venv/bin/python -m pytest tests/unit/test_capability_scorecard.py::test_coherence_persisted_to_take_metadata -v` → FAIL.

- [ ] **Step 4: Persist via `_mutate_shot`.** At the discovered site, write the value onto the take and persist (mirror `_finalize_motion_take`'s `take["metadata"]["motion_fidelity"] = ...` at `:1055`, then the `_mutate_shot(shot_id, _mutator)` save at `:1124`). Example shape:

```python
def _mutator(_scene: dict, shot: dict):
    for t in shot.get("<take_list>", []):
        if t.get("id") == take_id:
            t.setdefault("metadata", {})["coherence_score"] = coherence_value
    return MutationResult(None, save=True)
self._mutate_shot(shot_id, _mutator)
```

- [ ] **Step 5: Run, verify PASS.** Same pytest command → PASS.

- [ ] **Step 6: Commit.**

```bash
git log --oneline -1   # Rule #7 pre-commit re-verify
git commit -- cinema/shots/controller.py tests/unit/test_capability_scorecard.py \
  -m "feat(pipeline): persist coherence_score to take metadata for the capability scorecard"
```

> **Note:** If Step 1 found no clean site, this task ships zero code; the scorecard's defensive read (Task 2) covers coherence from `shot.diagnostics`. Report the divergence.

---

### Task 2: Capability-scorecard builder + endpoint

**Files:**
- Create: `cinema/capability_scorecard.py`
- Modify: `web_server.py` (add the route)
- Test: `tests/unit/test_capability_scorecard.py`

- [ ] **Step 1: Write the failing test for the builder.**

```python
# tests/unit/test_capability_scorecard.py
from cinema.capability_scorecard import build_capability_scorecard

def _make_project(**over):
    """Minimal project dict with one scene + shots/takes."""
    shot = {
        "id": "s1_01", "primary_character": "char_alex",
        "keyframe_takes": [{"id": "k1", "kind": "keyframe",
            "metadata": {"identity_score": 0.74},
            "cascade_metadata": {"engine": "KLING_NATIVE", "fallback": False, "attempts": ["KLING_NATIVE"]}}],
        "motion_takes": [{"id": "m1", "kind": "motion",
            "metadata": {"motion_fidelity": 0.82, "lipsync_score": 0.72}}],
        "approved_motion_take_id": "m1", "approved_keyframe_take_id": "k1",
        "diagnostics": [{"take_id": "k1", "scores": {"coherence": 0.64}}],
        "auto_approve_audit": [{"gate": "image", "auto_approved": True, "vetoes": [], "rule_names": ["composite_ok"], "timestamp": "2026-06-04T00:00:00Z"}],
    }
    p = {"id": "p1", "name": "neon_alley", "characters": [{"id": "char_alex"}],
         "scenes": [{"shots": [shot]}], "global_settings": {"quality_tier": "max"}}
    p.update(over); return p

class TestScorecardBuilder:
    def test_summary_and_dimensions(self):
        sc = build_capability_scorecard(_make_project(), project_dir="/tmp/nonexistent")
        assert sc["project_id"] == "p1"
        assert sc["tier"] == "max"
        assert sc["summary"]["shots_total"] == 1
        ids = {d["key"] for d in sc["dimensions"]}
        assert {"identity", "coherence", "motion", "lipsync"} <= ids
        identity = next(d for d in sc["dimensions"] if d["key"] == "identity")
        assert identity["value"] == 0.74 and identity["bar"] is not None

    def test_coherence_falls_back_to_diagnostics(self):
        sc = build_capability_scorecard(_make_project(), project_dir="/tmp/nonexistent")
        coh = next(d for d in sc["dimensions"] if d["key"] == "coherence")
        assert coh["value"] == 0.64  # sourced from shot.diagnostics when not on take.metadata
        assert coh["n_measured"] == 1

    def test_empty_project_no_fake_zeros(self):
        sc = build_capability_scorecard({"id": "e", "name": "empty", "characters": [], "scenes": [], "global_settings": {}}, project_dir="/tmp/x")
        assert sc["summary"]["shots_total"] == 0
        for d in sc["dimensions"]:
            assert d["value"] is None and d["n_measured"] == 0  # never a fabricated 0

    def test_routing_counts_fallbacks(self):
        sc = build_capability_scorecard(_make_project(), project_dir="/tmp/x")
        assert sc["routing"]["first_try"] >= 1
```

- [ ] **Step 2: Run, verify FAIL** (`ModuleNotFoundError: cinema.capability_scorecard`). `.venv/bin/python -m pytest tests/unit/test_capability_scorecard.py::TestScorecardBuilder -v`.

- [ ] **Step 3: Implement `cinema/capability_scorecard.py`.** A pure function — no Flask, no disk writes. Complete reference implementation:

```python
"""Build the capability scorecard (Part 4 / U1+U2+U8) from a project dict.

Pure aggregation: reads the already-persisted project + per-character LoRA
status; computes per-dimension measured-vs-bar, gate rollup, cascade routing,
and component-wiring status. No mutation, no Flask.
"""
from __future__ import annotations
import tomllib
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent


def _all_shots(project: dict) -> list[dict]:
    return [sh for sc in project.get("scenes", []) for sh in sc.get("shots", [])]


def _approved_take(shot: dict, list_key: str, approved_key: str) -> Optional[dict]:
    takes = shot.get(list_key) or []
    aid = shot.get(approved_key)
    if aid:
        for t in takes:
            if t.get("id") == aid:
                return t
    return takes[-1] if takes else None


def _coherence_for(shot: dict, take: Optional[dict]) -> Optional[float]:
    # Prefer persisted take.metadata; fall back to the latest diagnostic (Task 1 may not run).
    if take and isinstance(take.get("metadata"), dict) and take["metadata"].get("coherence_score") is not None:
        return take["metadata"]["coherence_score"]
    diags = [d for d in (shot.get("diagnostics") or []) if isinstance(d.get("scores"), dict) and d["scores"].get("coherence") is not None]
    return diags[-1]["scores"]["coherence"] if diags else None


def _dimension(key: str, label: str, values: list[float], bar: Optional[float]) -> dict:
    measured = [v for v in values if v is not None]
    value = round(mean(measured), 3) if measured else None
    passed = None if value is None else (True if bar is None else value >= bar)
    return {"key": key, "label": label, "value": value, "bar": bar, "pass": passed, "n_measured": len(measured)}


def build_capability_scorecard(project: dict, *, project_dir: str) -> dict:
    shots = _all_shots(project)
    gs = project.get("global_settings", {}) or {}
    tier = gs.get("quality_tier", "production")

    # --- bars (sourced from named config; see plan "Critical context") ---
    try:
        from cinema.auto_approve import AutoApproveConfig
        cfg = AutoApproveConfig.from_project(project)
        identity_bar = getattr(cfg, "motion_min_identity", 0.6)
        lipsync_bar = float(gs.get("lipsync_validation_threshold", 0.65))
    except Exception:
        identity_bar, lipsync_bar = 0.6, 0.65
    coherence_bar = float(gs.get("coherence_threshold", 0.6))

    ident_v, coh_v, motion_v, lip_v = [], [], [], []
    per_shot, provenance = [], []
    routing = Counter()

    for shot in shots:
        kf = _approved_take(shot, "keyframe_takes", "approved_keyframe_take_id")
        mo = _approved_take(shot, "motion_takes", "approved_motion_take_id")
        idv = (kf or {}).get("metadata", {}).get("identity_score") if kf else None
        cov = _coherence_for(shot, kf)
        mov = (mo or {}).get("metadata", {}).get("motion_fidelity") if mo else None
        liv = (mo or {}).get("metadata", {}).get("lipsync_score") if mo else None
        ident_v.append(idv); coh_v.append(cov); motion_v.append(mov); lip_v.append(liv)

        # per-source: prefer the motion take's cascade, else the keyframe's (don't lose the
        # keyframe engine when the motion take lacks cascade_metadata). Handles empty-string engine.
        cas = (mo or {}).get("cascade_metadata") or (kf or {}).get("cascade_metadata") or {}
        engine = (cas.get("engine") or shot.get("target_api") or "").upper()
        attempts = cas.get("attempts") or []
        silent = bool(cas.get("fallback")) or (len(attempts) > 1)
        if silent: routing["fallback"] += 1
        else: routing["first_try"] += 1
        if cas.get("fallback"): routing["silent_fallback"] += 1

        per_shot.append({"shot_id": shot.get("id"), "identity": idv, "coherence": cov,
                         "motion": mov, "lipsync": liv, "engine": engine})
        provenance.append({"shot_id": shot.get("id"), "engine": engine,
                           "attempts": attempts, "fallback": bool(cas.get("fallback"))})

    dimensions = [
        _dimension("identity", "Identity · ArcFace", ident_v, identity_bar),
        _dimension("coherence", "Coherence", coh_v, coherence_bar),
        _dimension("motion", "Motion fidelity", motion_v, None),
        _dimension("lipsync", "Lipsync · SyncNet", lip_v, lipsync_bar),
    ]
    return {
        "project_id": project.get("id"),
        "tier": tier,
        "summary": {"shots_total": len(shots), "shots_clearing_all_bars": _shots_clearing(shots, dimensions, ident_v, coh_v, motion_v, lip_v, identity_bar, coherence_bar, lipsync_bar)},
        "dimensions": dimensions,
        "routing": {"first_try": routing["first_try"], "fallback": routing["fallback"], "silent_fallback": routing["silent_fallback"]},
        "gates": _gate_rollup(shots),
        "lora": _lora_summary(project, project_dir),
        "components": _components(),
        "per_shot": per_shot,
        "provenance": provenance,
        "future_dimensions": ["audio_lufs", "format_codec", "pod_health", "budget"],
    }


def _shots_clearing(shots, dimensions, ident_v, coh_v, motion_v, lip_v, ib, cb, lb) -> int:
    n = 0
    for i in range(len(shots)):
        ok = True
        for v, bar in ((ident_v[i], ib), (coh_v[i], cb), (lip_v[i], lb)):
            if v is not None and v < bar:
                ok = False
        n += 1 if ok else 0
    return n


def _gate_rollup(shots: list[dict]) -> dict:
    out = {g: {"approved": 0, "vetoed": 0, "top_vetoes": []} for g in ("plan", "image", "motion", "final")}
    veto_ctr = {g: Counter() for g in out}
    for shot in shots:
        for e in (shot.get("auto_approve_audit") or []):
            g = e.get("gate")
            if g not in out:
                continue
            if e.get("auto_approved"):
                out[g]["approved"] += 1
            else:
                out[g]["vetoed"] += 1
            for v in (e.get("vetoes") or []):
                veto_ctr[g][v] += 1
    for g in out:
        out[g]["top_vetoes"] = veto_ctr[g].most_common(3)
    return out


def _lora_summary(project: dict, project_dir: str) -> list[dict]:
    try:
        from prep.lora_training import get_lora_status
    except Exception:
        return []
    rows = []
    for ch in project.get("characters", []):
        cid = ch.get("id")
        if not cid:
            continue
        try:
            st = get_lora_status(project_dir, cid)
        except Exception:
            continue
        if st.get("status") in (None, "idle") and st.get("quality_score") is None:
            continue
        verdict = "rejected" if st.get("rejected") else ("warning" if st.get("quality_warning") else "ok")
        rows.append({"char_id": cid, "strength": st.get("best_strength"),
                     "score": st.get("quality_score"), "verdict": verdict})
    return rows


def _components() -> list[dict]:
    path = REPO_ROOT / "docs" / "pipeline_status.toml"
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return []
    return [{"id": c.get("id"), "title": c.get("title"), "status": c.get("status"), "note": c.get("note")}
            for c in data.get("component", [])]
```

> **Step 3a note:** before running tests, `.venv/bin/python -c "import cinema.capability_scorecard"` must succeed (no syntax/import error). Verify the load-bearing symbols by grep before relying on them and report any divergence: `AutoApproveConfig.from_project` (`cinema/auto_approve.py`), `get_lora_status` (`prep/lora_training.py`), `get_project_dir` (`domain/project_manager.py`).

- [ ] **Step 4: Run builder tests, verify PASS.** `.venv/bin/python -m pytest tests/unit/test_capability_scorecard.py::TestScorecardBuilder -v` → PASS. Fix any bar-sourcing mismatch (verify `AutoApproveConfig.from_project` exists + the field name via `grep -n "def from_project\|motion_min_identity" cinema/auto_approve.py`).

- [ ] **Step 5: Write the failing endpoint test.**

```python
class TestScorecardEndpoint:
    def _client(self):
        from web_server import app
        app.config["TESTING"] = True
        return app.test_client()

    def test_404_when_project_absent(self):
        from unittest.mock import patch
        with patch("web_server.load_project", return_value=None):
            r = self._client().get("/api/projects/missing/capability-scorecard")
        assert r.status_code == 404
        assert r.get_json()["error"] == "Project not found"

    def test_200_returns_scorecard(self):
        from unittest.mock import patch
        with patch("web_server.load_project", return_value=_make_project()):
            r = self._client().get("/api/projects/p1/capability-scorecard")
        assert r.status_code == 200
        body = r.get_json()
        assert body["project_id"] == "p1" and "dimensions" in body
```

- [ ] **Step 6: Run, verify FAIL** (404 route not found → 404 but wrong body, or 500). 

- [ ] **Step 7: Add the endpoint to `web_server.py`** (near `api_get_project`, ~line 485). Mirror the GET pattern exactly:

```python
@app.route("/api/projects/<pid>/capability-scorecard", methods=["GET"])
def api_capability_scorecard(pid):
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    from cinema.capability_scorecard import build_capability_scorecard
    from domain.project_manager import get_project_dir
    scorecard = build_capability_scorecard(project, project_dir=get_project_dir(pid))
    return jsonify(scorecard)
```

> Verify `get_project_dir` exists + signature: `grep -n "def get_project_dir" domain/project_manager.py`. If it differs, use the actual project-dir resolver and report the divergence.

- [ ] **Step 8: Run endpoint tests, verify PASS.** `.venv/bin/python -m pytest tests/unit/test_capability_scorecard.py -v` → all PASS.

- [ ] **Step 9: Smoke + commit.**

```bash
.venv/bin/python scripts/ci_smoke.py        # expect: OK
git log --oneline -1                          # Rule #7
git commit -- cinema/capability_scorecard.py web_server.py tests/unit/test_capability_scorecard.py \
  -m "feat(web): capability-scorecard endpoint + pure builder (Part 4 U1/U2/U8)"
```

---

## Chunk 2: Frontend foundation — types, mode wiring, view shell

> **Frontend verification (every task):** `cd web && npx tsc --noEmit` (no type errors) then `npm run build` (succeeds). There is NO component-test runner — do not add one.

### Task 3: Scorecard response type + mode wiring

**Files:**
- Modify: `web/src/types/project.ts`
- Modify: `web/src/App.tsx`
- Modify: `web/src/components/EditorialShell.tsx`

- [ ] **Step 1: Add the response type** to `web/src/types/project.ts` (mirror the endpoint JSON exactly):

```tsx
export interface CapabilityDimension {
  key: string; label: string;
  value: number | null; bar: number | null; pass: boolean | null; n_measured: number;
}
export interface CapabilityScorecard {
  project_id: string; tier: string;
  summary: { shots_total: number; shots_clearing_all_bars: number };
  dimensions: CapabilityDimension[];
  routing: { first_try: number; fallback: number; silent_fallback: number };
  gates: Record<'plan'|'image'|'motion'|'final', { approved: number; vetoed: number; top_vetoes: [string, number][] }>;
  lora: { char_id: string; strength: number | null; score: number | null; verdict: 'ok'|'warning'|'rejected' }[];
  components: { id: string; title: string; status: string; note: string }[];
  per_shot: { shot_id: string; identity: number|null; coherence: number|null; motion: number|null; lipsync: number|null; engine: string }[];
  provenance: { shot_id: string; engine: string; attempts: string[]; fallback: boolean }[];
  future_dimensions: string[];
}
```

- [ ] **Step 2: Wire the mode in `App.tsx`.** (a) widen the union at line ~18 to include `'capability'`; (b) add the import next to the other component imports: `import CapabilityConsole from './components/console/CapabilityConsole'`; (c) add the guard mirroring the `console` guard:

```tsx
  if (mode === 'capability' && project) {
    return <ErrorBoundary><CapabilityConsole project={project} onBack={() => setMode('setup')} /></ErrorBoundary>
  }
```

(d) pass `onOpenCapability={() => setMode('capability')}` into the `<EditorialShell ... />` render block (alongside `onOpenConsole`).

- [ ] **Step 3: Add the nav button** in `web/src/components/EditorialShell.tsx`: add `onOpenCapability?: () => void` to the props interface, destructure it, and render next to the "Director's Console →" button (mirror its className exactly):

```tsx
          {onOpenCapability && (
            <button onClick={onOpenCapability}
              className="font-mono text-eyebrow-lg text-editorial-brass tracking-wide-eyebrow uppercase hover:text-editorial-brass-deep link-editorial"
              title="Open the Capability dashboard — pipeline scorecard">
              Capability →
            </button>
          )}
```

- [ ] **Step 4: Create a stub `CapabilityConsole`** so `tsc` passes (filled in Task 4):

```tsx
// web/src/components/console/CapabilityConsole.tsx
import type { Project } from '../../types/project'
interface Props { project: Project | null; onBack: () => void }
export default function CapabilityConsole({ project, onBack }: Props) {
  return <div className="min-h-screen bg-console-bg text-console-ink p-6">
    <button onClick={onBack} className="text-console-gold">← Back</button>
    <div>Capability — {project?.name}</div>
  </div>
}
```

- [ ] **Step 5: Verify + commit.**

```bash
cd web && npx tsc --noEmit && npm run build && cd ..
git log --oneline -1
git commit -- web/src/types/project.ts web/src/App.tsx web/src/components/EditorialShell.tsx web/src/components/console/CapabilityConsole.tsx \
  -m "feat(web): add 'capability' app mode + nav + scorecard response type"
```

### Task 4: CapabilityConsole shell + data fetch + states

**Files:** Modify `web/src/components/console/CapabilityConsole.tsx`

- [ ] **Step 1: Implement the shell + fetch.** Mirror `DirectorsConsole`'s masthead + `bg-console-bg` shell and Telemetry's fetch idiom. Fetch the scorecard endpoint on mount; render loading / empty / error states.

```tsx
import { useEffect, useState } from 'react'
import type { Project, CapabilityScorecard } from '../../types/project'

interface Props { project: Project | null; onBack: () => void }

export default function CapabilityConsole({ project, onBack }: Props) {
  const projectId = project?.id || null
  const [sc, setSc] = useState<CapabilityScorecard | null>(null)
  const [state, setState] = useState<'loading'|'ready'|'empty'|'error'>('loading')

  const load = () => {
    if (!projectId) { setState('empty'); return }
    setState('loading')
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`/api/projects/${projectId}/capability-scorecard`)
        if (!res.ok) throw new Error(String(res.status))
        const data: CapabilityScorecard = await res.json()
        if (cancelled) return
        setSc(data)
        setState(data.summary.shots_total === 0 ? 'empty' : 'ready')
      } catch { if (!cancelled) setState('error') }
    })()
    return () => { cancelled = true }
  }
  useEffect(load, [projectId])  // eslint-disable-line react-hooks/exhaustive-deps

  const Label = ({ children }: { children: React.ReactNode }) =>
    <div className="text-eyebrow-lg uppercase tracking-wider text-console-ink-mute font-console-mono">{children}</div>

  return (
    <div className="min-h-screen bg-console-bg text-console-ink">
      <header className="border-b border-console-rule px-6 py-4 flex items-center justify-between">
        <div>
          <button onClick={onBack} className="text-eyebrow-lg uppercase tracking-wider text-console-ink-mute hover:text-console-gold font-console-mono">← Back to setup</button>
          <h1 className="mt-1 text-2xl font-display text-console-gold">
            {project?.name || 'No project'}<span className="ml-2 text-sm font-normal text-console-ink-dim font-console-mono">· Capability</span>
          </h1>
        </div>
        <div className="text-right text-xs font-console-mono text-console-ink-dim">
          {sc && <span><span className="bg-console-gold text-black px-2 rounded">{sc.tier.toUpperCase()}</span> · {sc.summary.shots_clearing_all_bars}/{sc.summary.shots_total} clear all bars</span>}
          <button onClick={load} className="ml-3 text-console-ink-mute hover:text-console-gold">↻ refresh</button>
        </div>
      </header>

      {state === 'loading' && <div className="p-8 text-console-ink-mute font-console-mono">Loading capability data…</div>}
      {state === 'error' && <div className="p-8 text-console-accent font-console-mono">Could not load the scorecard. <button onClick={load} className="underline">Retry</button></div>}
      {state === 'empty' && <div className="p-8 text-console-ink-mute font-console-mono">No capability data yet — run the pipeline to populate scores.</div>}
      {state === 'ready' && sc && (
        <div className="px-6 py-6 space-y-6">
          {/* sections added in Chunk 3; pass `sc` down */}
          <Label>Capability scorecard</Label>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify + commit.**

```bash
cd web && npx tsc --noEmit && npm run build && cd ..
git log --oneline -1
git commit -- web/src/components/console/CapabilityConsole.tsx \
  -m "feat(web): CapabilityConsole shell + scorecard fetch + loading/empty/error states"
```

---

## Chunk 3: Frontend sections — render the scorecard

> Each section is a small presentational block inside `CapabilityConsole`'s `state === 'ready'` container, reading from `sc`. Use the raw console className idiom (NOT `ui/Eyebrow`/`ui/Button`). Helper color: pass = `text-[#7fd17f]` (or a `console-gold`-adjacent green), fail = `text-console-accent`, warn = `text-[#e0b94e]`, mute = `text-console-ink-mute`. Define a small `scoreClass(value, bar)` helper.

### Task 5: Header summary + scorecard dimension grid

- [ ] **Step 1:** Add a `<ScorecardGrid sc={sc} />` block (inline component or a local function) rendering `sc.dimensions` as tiles (label, value `/ bar`, a mini bar `width: value*100%`, pass/fail color) in a `grid grid-cols-4 gap-2`, plus a greyed row from `sc.future_dimensions`. Tiles with `value === null` show "— not measured". Use `border border-console-rule rounded p-2`.
- [ ] **Step 2:** `cd web && npx tsc --noEmit && npm run build`.
- [ ] **Step 3:** Commit `-- web/src/components/console/CapabilityConsole.tsx -m "feat(web): scorecard dimension grid (U1)"`.

### Task 6: Per-shot scores table (U2) + cascade provenance (U8)

- [ ] **Step 1:** Render `sc.per_shot` as a `<table>`: cols Shot / Identity / Coherence / Motion / Lipsync / Engine; each numeric cell colored via `scoreClass` against the matching dimension's `bar`; `null` → "—". Then render `sc.provenance`: per row `shot_id · engine`, and when `fallback || attempts.length > 1` show the attempts chain + a `bg-[#3a1212] text-[#e88]` "silent fallback" chip (mirror `TakeStrip`'s engine-chip styling).
- [ ] **Step 2:** `cd web && npx tsc --noEmit && npm run build`.
- [ ] **Step 3:** Commit `-- web/src/components/console/CapabilityConsole.tsx -m "feat(web): per-shot scores table + cascade provenance (U2/U8)"`.

### Task 7: Gate audit + LoRA + component status

- [ ] **Step 1:** Two-column block. Left: `sc.gates` — for each of plan/image/motion/final show `approved/vetoed` + `top_vetoes[0]` if present. Right: `sc.lora` rows (`char_id · str {strength} · {score} {verdict}` colored by verdict) + `sc.components` as inline `id ●status` pills colored by status (live/wired=green, stubbed/parked=warn, dead=mute).
- [ ] **Step 2:** `cd web && npx tsc --noEmit && npm run build`.
- [ ] **Step 3:** Commit `-- web/src/components/console/CapabilityConsole.tsx -m "feat(web): gate audit + LoRA + component status sections (U1)"`.

---

## Final verification + handoff

- [ ] Backend: `.venv/bin/python -m pytest tests/unit/test_capability_scorecard.py -v` → all PASS; `.venv/bin/python scripts/ci_smoke.py` → OK.
- [ ] Frontend: `cd web && npx tsc --noEmit && npm run build` → clean.
- [ ] Manual: launch the app (`run`/`web_server.py`), open a project with takes, click **Capability →**, confirm the scorecard, per-shot table, and provenance render with real data; confirm empty-state on a never-run project.
- [ ] Lane D: if any of `cinema/`, `web_server.py`, `domain/` changed in a way that affects `ARCHITECTURE.md`, sync §-appropriately (operator Lane D).
- [ ] `superpowers:requesting-code-review` on the full branch range, then `superpowers:finishing-a-development-branch`.

## Out of scope / future (do not build now)
- U3 (audio LUFS / format probe) — the designated next increment.
- U5 (pod health), U6 (budget caveats), U7 (headless-readiness).
- Live SSE auto-refresh of the dashboard during a run (v1 is load + manual refresh).
- LoRA strength-sweep visualization (only verdict/score/strength rendered).
- A frontend component-test harness (vitest) — net-new infra; needs explicit buy-in.
