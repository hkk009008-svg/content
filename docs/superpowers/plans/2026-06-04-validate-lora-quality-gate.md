# validate_lora_quality + auto-retrain quality gate — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (subagents available) to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `validate_lora_quality` `-1.0` stub with real ArcFace identity validation wrapped in a bounded train→validate→retrain control loop that also sweeps + persists the best per-character LoRA strength.

**Architecture:** New module `prep/lora_quality.py` holds four units — a pure decision function (`_next_lora_action`), a single-shot generation helper (`_generate_with_lora`), a scoring oracle (`validate_lora_quality`), and an orchestrator (`train_character_lora_gated`). `train_character_lora` becomes pure single-train; `web_server.api_train_lora` calls the gated orchestrator and persists `char_lora_strengths`; the shot pipeline threads `char_lora_strength` beside `char_lora_path` to the ComfyUI injection point. Every unit is boundary-mocked so the full suite runs with **no GPU/ComfyUI in CI**.

**Tech Stack:** Python 3.13, pytest (`.venv/bin/python -m pytest`), existing ComfyUI primitives in `quality_max.py`, ArcFace scoring via `face_validator_gate.score_candidate`.

**Spec (read first):** `docs/superpowers/specs/2026-06-03-validate-lora-quality-design.md` — design rationale, the 4 user-approved decisions, the verified call-graph, and the deferred-to-Phase-B live-calibration note. This plan is the bite-sized TDD execution of that spec.

**Baseline:** branch `feat/max-tier-provisioning`. Spec committed at `082edb5`. (HEAD advances as the director clears parallel no-op tickets on the same branch — all disjoint from T1's files. Use pathspec commits only; never `git add -A`/`git commit -a` — the working tree is shared and the director has live WIP.)

**Project conventions every task MUST follow** (from `CLAUDE.md`):
1. Before editing an existing symbol, `grep -rn 'symbolName' --include='*.py' .` for callers/importers and Read them; report blast radius.
2. After edits, `git diff --cached --name-only` then `git commit -m "..." -- <explicit paths>` (shared index — pathspec is mandatory; bare commit sweeps the director's WIP).
3. Use `.venv/bin/python` (not system `python3`) for pytest/scripts.
4. Brief-pattern references are specs: when this plan says "mirror X at file:line," verify X's full shape before deviating; report divergences instead of silently adapting.
5. Plan-vs-source divergence rule: where this plan's sketched line numbers/values differ from actual source at execution time, use the source and report the divergence.

**Done-signal for the whole plan:** new `tests/unit/test_lora_quality.py` green; full suite still **1512/3/0** (baseline) or higher with 0 failures; `.venv/bin/python scripts/ci_smoke.py` → `OK`; `.venv/bin/python scripts/check_doc_claims.py` → no drift.

---

## Chunk 1: New module `prep/lora_quality.py` (pure + boundary-mocked units)

All four units land in one new file `prep/lora_quality.py` and one new test file `tests/unit/test_lora_quality.py`. Tasks 1→4 build bottom-up; each is independently testable.

### Task 1: Types + pure decision function `_next_lora_action`

**Files:**
- Create: `prep/lora_quality.py`
- Test: `tests/unit/test_lora_quality.py`

- [ ] **Step 1: Write the failing tests** (pure fn — no mocks; covers every branch of the ≤3-train / keep-best / reject-if-net-negative policy)

```python
# tests/unit/test_lora_quality.py
"""Offline tests for the LoRA quality gate (no GPU/ComfyUI — all boundaries mocked)."""
import pytest
from prep.lora_quality import _next_lora_action, LoraAction

THRESH, BASE, BUDGET = 0.6, 0.45, 3


@pytest.mark.parametrize("attempt,score,expected", [
    (0, 0.72, LoraAction.ACCEPT),            # meets threshold on first train
    (0, None, LoraAction.ACCEPT),            # validation skipped -> accept (register unvalidated)
    (0, 0.50, LoraAction.RETRY_MORE_STEPS),  # 1st low score -> escalate steps
    (1, 0.55, LoraAction.RETRY_HIGHER_RANK), # 2nd low score -> escalate rank
    (2, 0.50, LoraAction.ACCEPT),            # budget exhausted, best >= baseline -> keep best
    (2, 0.40, LoraAction.REJECT),            # budget exhausted, best < baseline -> reject (PuLID-only)
    (2, 0.60, LoraAction.ACCEPT),            # exactly at threshold on final -> accept
])
def test_next_lora_action(attempt, score, expected):
    assert _next_lora_action(attempt, score, threshold=THRESH, baseline=BASE, budget=BUDGET) is expected
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_lora_quality.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'prep.lora_quality'`.

- [ ] **Step 3: Write the minimal implementation**

```python
# prep/lora_quality.py
"""LoRA quality gate + auto-retrain control loop.

See docs/superpowers/specs/2026-06-03-validate-lora-quality-design.md for design + rationale.

Units:
  _next_lora_action(...)        -> pure policy decision (no IO)
  _generate_with_lora(...)      -> one honest ComfyUI generation (no N=8 best-of)
  validate_lora_quality(...)    -> scoring oracle: sweep strengths, ArcFace-score vs reference
  train_character_lora_gated(.) -> orchestrator: train -> validate -> decide -> persist best
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LoraAction(Enum):
    ACCEPT = "accept"                   # register best (caller warns if best < threshold)
    RETRY_MORE_STEPS = "retry_more_steps"
    RETRY_HIGHER_RANK = "retry_higher_rank"
    REJECT = "reject"                   # do NOT register; PuLID-only fallback


@dataclass
class StrengthScore:
    strength: float
    mean_arc: Optional[float]           # mean arc_score across prompts; None if all samples skipped
    per_prompt: list = field(default_factory=list)  # [(label, arc_score|None), ...]


@dataclass
class LoraQualityResult:
    best_score: Optional[float]         # mean_arc at best strength; None if skipped
    best_strength: Optional[float]      # argmax strength; None if skipped
    sweep: list = field(default_factory=list)        # list[StrengthScore]
    skipped: bool = False
    skip_reason: str = ""


def _next_lora_action(attempt: int, best_score: Optional[float], *,
                      threshold: float, baseline: float, budget: int) -> LoraAction:
    """Pure policy. `attempt` is the 0-based index of the train just validated;
    `budget` is the max number of trains. Implements decision D3 (spec §3/§6.3)."""
    if best_score is None:                      # validation skipped -> register unvalidated
        return LoraAction.ACCEPT
    if best_score >= threshold:
        return LoraAction.ACCEPT
    if attempt + 1 >= budget:                   # retrain budget exhausted
        return LoraAction.ACCEPT if best_score >= baseline else LoraAction.REJECT
    return LoraAction.RETRY_MORE_STEPS if attempt == 0 else LoraAction.RETRY_HIGHER_RANK
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_lora_quality.py -q`
Expected: PASS (7 parametrized cases).

- [ ] **Step 5: Commit** (pathspec)

```bash
git diff --cached --name-only   # confirm empty / only your files before staging
git add prep/lora_quality.py tests/unit/test_lora_quality.py
git commit -m "feat(lora): pure _next_lora_action decision fn + LoRA quality types (T1 task 1)" -- prep/lora_quality.py tests/unit/test_lora_quality.py
```

---

### Task 2: `_generate_with_lora` — honest single-shot generation

**Files:**
- Modify: `prep/lora_quality.py`
- Test: `tests/unit/test_lora_quality.py`

**Reuse (verified primitives — do NOT fork a script):** `quality_max._load_max_workflow()` (`:185`), `quality_max._inject_identity(workflow, char_lora, face_anchor_remote, params, has_character)` (`:458`, sets node-700 `strength_model`/`strength_clip` from `params` at `:466-467`), `quality_max._inject_conditioning(...)` (`:494`), `quality_max._inject_sampling(workflow, params)` (`:528`), and `quality_max._run_one_candidate(comfy, workflow, output_filename, ...)` (`:604` — the SINGLE-candidate runner that calls `comfy.queue_prompt`; the N=8 best-of is just the loop in `generate_ai_broll_max` that calls this repeatedly — we call it **once**). ComfyUI client + URL: `RunPodComfyUI` + `settings.comfyui_server_url` (`:675`).

- [ ] **Step 0: Confirm the reuse surface**

Run: `grep -n 'def _run_one_candidate\|def _load_max_workflow\|class RunPodComfyUI\|RunPodComfyUI(' quality_max.py`
Read `quality_max.py:604-648` (`_run_one_candidate`) and `:649-720` (`generate_ai_broll_max` — copy its assembly order: load → inject identity → conditioning → sampling → run). Match that order in `_generate_with_lora`, but inject the **per-call strength** into `params` and call `_run_one_candidate` exactly once (no best-of loop). Report any signature divergence from the lines above.

- [ ] **Step 1: Write the failing test** (mock the ComfyUI boundary — assert single generation, strength injected, unreachable→None)

```python
# add to tests/unit/test_lora_quality.py
from unittest.mock import patch, MagicMock
import prep.lora_quality as lq


def test_generate_with_lora_injects_strength_and_runs_once(tmp_path, monkeypatch):
    calls = {"run": 0}
    fake_wf = {"700": {"inputs": {}}}
    monkeypatch.setattr(lq, "_qm_load_max_workflow", lambda: dict(fake_wf), raising=False)
    captured = {}

    def fake_inject_identity(wf, char_lora, face_anchor_remote, params, has_character):
        captured["lora"] = char_lora
        captured["strength_model"] = params.get("lora_strength_model")
        captured["strength_clip"] = params.get("lora_strength_clip")

    def fake_run_one(comfy, wf, output_filename, *a, **k):
        calls["run"] += 1
        return str(tmp_path / output_filename)

    monkeypatch.setattr(lq, "_qm_inject_identity", fake_inject_identity, raising=False)
    monkeypatch.setattr(lq, "_qm_inject_conditioning", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(lq, "_qm_inject_sampling", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(lq, "_qm_run_one_candidate", fake_run_one, raising=False)
    monkeypatch.setattr(lq, "_make_comfy", lambda url: MagicMock(), raising=False)

    out = lq._generate_with_lora("/loras/mara_v1.safetensors", "<mara> headshot",
                                 strength=0.55, seed=7, out_path=str(tmp_path / "g0.png"),
                                 comfyui_url="http://x:8188")
    assert out is not None
    assert calls["run"] == 1                          # single generation, no best-of
    assert captured["lora"] == "/loras/mara_v1.safetensors"
    assert captured["strength_model"] == 0.55 and captured["strength_clip"] == 0.55


def test_generate_with_lora_returns_none_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(lq, "_qm_load_max_workflow", lambda: {}, raising=False)
    monkeypatch.setattr(lq, "_qm_inject_identity", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(lq, "_qm_inject_conditioning", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(lq, "_qm_inject_sampling", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(lq, "_make_comfy", lambda url: (_ for _ in ()).throw(OSError("unreachable")), raising=False)
    out = lq._generate_with_lora("/loras/x.safetensors", "<x>", strength=1.0, seed=1,
                                 out_path=str(tmp_path / "g.png"), comfyui_url="http://x:8188")
    assert out is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_lora_quality.py -k generate_with_lora -q`
Expected: FAIL — `_generate_with_lora` not defined.

- [ ] **Step 3: Write the implementation** (import the quality_max primitives under stable aliases so tests can monkeypatch them on `prep.lora_quality`; wrap in try/except → None)

```python
# add to prep/lora_quality.py (imports near top — lazy inside the function to avoid
# importing the heavy ComfyUI stack at module import time / in pure-fn CI):

def _qm_load_max_workflow():
    from quality_max import _load_max_workflow
    return _load_max_workflow()

def _qm_inject_identity(*a, **k):
    from quality_max import _inject_identity
    return _inject_identity(*a, **k)

def _qm_inject_conditioning(*a, **k):
    from quality_max import _inject_conditioning
    return _inject_conditioning(*a, **k)

def _qm_inject_sampling(*a, **k):
    from quality_max import _inject_sampling
    return _inject_sampling(*a, **k)

def _qm_run_one_candidate(*a, **k):
    from quality_max import _run_one_candidate
    return _run_one_candidate(*a, **k)

def _make_comfy(url):
    from quality_max import RunPodComfyUI
    return RunPodComfyUI(url)


def _default_max_params(shot_type: str = "portrait") -> dict:
    """Tier params baseline — the SAME source generate_ai_broll_max uses
    (`params = get_max_quality_params(shot_type)` at quality_max.py ~:689). Do NOT return {}
    — the _inject_* helpers expect real tier keys (sampler/steps/cfg/lora_strength_*/…)."""
    from quality_max import get_max_quality_params   # if import fails, grep its defining module
    return dict(get_max_quality_params(shot_type))


def _generate_with_lora(lora_path: str, prompt: str, *, strength: float, seed: int,
                        out_path: str, comfyui_url: str) -> Optional[str]:
    """ONE honest ComfyUI generation with `lora_path` at `strength`. No best-of, no
    ArcFace gating (that would inflate the measured score). Returns image path or None
    on any infra failure (never raises)."""
    try:
        wf = _qm_load_max_workflow()
        params = {**_default_max_params(),
                  "lora_strength_model": strength, "lora_strength_clip": strength, "seed": seed}
        _qm_inject_identity(wf, lora_path, None, params, True)
        # 6-arg (verified): (workflow, prompt, prev_shot_remote, style_remote, params, has_character)
        _qm_inject_conditioning(wf, prompt, None, None, params, True)
        _qm_inject_sampling(wf, params)
        comfy = _make_comfy(comfyui_url)
        return _qm_run_one_candidate(comfy, wf, out_path)
    except Exception as e:                                        # infra failure -> skip, never crash
        print(f"[lora_quality] generation failed ({e}); treating as skip")
        return None
```

> **Plan-vs-source divergence note for the implementer:** the exact argument lists of `_inject_conditioning`/`_inject_sampling`/`_run_one_candidate` and the `params` keys must be taken from `quality_max.py` at execution time (Step 0). The aliasing wrappers exist so tests monkeypatch `prep.lora_quality._qm_*`; keep them.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_lora_quality.py -k generate_with_lora -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add prep/lora_quality.py tests/unit/test_lora_quality.py
git commit -m "feat(lora): _generate_with_lora honest single-shot via quality_max primitives (T1 task 2)" -- prep/lora_quality.py tests/unit/test_lora_quality.py
```

---

### Task 3: `validate_lora_quality` — scoring oracle (sweep + score)

**Files:**
- Modify: `prep/lora_quality.py`
- Test: `tests/unit/test_lora_quality.py`

**Reuse (verified):** `face_validator_gate.score_candidate(image_path, face_anchor, weights=None, threshold=0.0) -> CandidateScore` (`face_validator_gate.py:170`). Read `score.arc_score` (`:159`, ∈[0,1]) **only when `score.has_arc` is True** — otherwise that sample is a skip. Character fields: `character["canonical_reference"]` (may be `""`; `domain/character_manager.py:150`), trigger = `character.get("trigger_token") or f"<{character['id']}>"` (`prep/lora_training.py:111,192`).

- [ ] **Step 1: Write the failing tests** (mock `_generate_with_lora` + `score_candidate`; assert argmax sweep, mean ignores `has_arc=False`, empty `canonical_reference`→skip)

```python
# add to tests/unit/test_lora_quality.py
from types import SimpleNamespace


def _cs(arc, has_arc=True):
    return SimpleNamespace(arc_score=arc, has_arc=has_arc)


def test_validate_picks_best_strength(monkeypatch, tmp_path):
    # score depends on strength: 0.55 is best, 1.0 over-bakes
    scores_by_strength = {0.45: 0.50, 0.55: 0.74, 0.7: 0.66, 1.0: 0.58}
    cur = {"score": 0.0}   # side-channel: gen() sets the score the next score_candidate returns

    def gen(lora_path, prompt, *, strength, seed, out_path, comfyui_url):
        cur["score"] = scores_by_strength[strength]
        return out_path
    monkeypatch.setattr(lq, "_generate_with_lora", gen)
    monkeypatch.setattr(lq, "_score_candidate", lambda img, anchor: _cs(cur["score"]))

    (tmp_path / "ref.png").write_bytes(b"x")
    char = {"id": "c1", "name": "Mara", "canonical_reference": str(tmp_path / "ref.png")}
    res = lq.validate_lora_quality("/loras/c1.safetensors", char,
                                   strengths=[0.45, 0.55, 0.7, 1.0], comfyui_url="http://x:8188")
    assert not res.skipped
    assert res.best_strength == 0.55
    assert abs(res.best_score - 0.74) < 1e-6


def test_validate_skips_when_no_canonical_reference(monkeypatch):
    res = lq.validate_lora_quality("/loras/c1.safetensors", {"id": "c1", "canonical_reference": ""},
                                   comfyui_url="http://x:8188")
    assert res.skipped and res.skip_reason == "no_canonical_reference"


def test_validate_skips_when_all_generations_fail(monkeypatch, tmp_path):
    (tmp_path / "ref.png").write_bytes(b"x")
    monkeypatch.setattr(lq, "_generate_with_lora", lambda *a, **k: None)  # all gens fail
    res = lq.validate_lora_quality("/loras/c1.safetensors",
                                   {"id": "c1", "canonical_reference": str(tmp_path / "ref.png")},
                                   strengths=[0.55, 1.0], comfyui_url="http://x:8188")
    assert res.skipped


def test_validate_mean_ignores_has_arc_false(monkeypatch, tmp_path):
    (tmp_path / "ref.png").write_bytes(b"x")
    monkeypatch.setattr(lq, "_generate_with_lora", lambda *a, **k: "g.png")
    seq = iter([_cs(0.7), _cs(0.0, has_arc=False), _cs(0.5)])  # middle sample is a skip
    monkeypatch.setattr(lq, "_score_candidate", lambda img, anchor: next(seq))
    res = lq.validate_lora_quality("/loras/c1.safetensors",
                                   {"id": "c1", "canonical_reference": str(tmp_path / "ref.png")},
                                   strengths=[0.55], prompts=["a", "b", "c"], comfyui_url="http://x:8188")
    # mean of 0.7 and 0.5 (skip the has_arc=False sample) = 0.6
    assert abs(res.best_score - 0.6) < 1e-6
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_lora_quality.py -k validate -q`
Expected: FAIL — `validate_lora_quality` not defined.

- [ ] **Step 3: Write the implementation**

```python
# add to prep/lora_quality.py
import os

DEFAULT_STRENGTH_SWEEP = [0.45, 0.55, 0.7, 1.0]
DEFAULT_VALIDATION_PROMPTS = [
    "{trigger} photo, professional headshot, soft natural light",
    "{trigger} photo, full body, daylight, casual outfit",
    "{trigger} portrait, side profile, indoor window light",
]
_VALIDATION_SEEDS = [101, 202, 303]   # fixed per-prompt seeds for reproducibility


def _score_candidate(image_path, anchor):
    from face_validator_gate import score_candidate
    return score_candidate(image_path, anchor)   # threshold=0.0 default -> just scores


def _resolve_comfyui_url(comfyui_url: Optional[str]) -> str:
    if comfyui_url:
        return comfyui_url
    from config.settings import get_settings   # adjust to the project's settings accessor
    return get_settings().comfyui_server_url


def validate_lora_quality(lora_path, character, *, strengths=None, prompts=None,
                          comfyui_url=None) -> LoraQualityResult:
    """Scoring oracle: sweep strengths x prompts, ArcFace-score each generation vs the
    character's canonical_reference, pick the best strength. See spec §6.2."""
    anchor = (character.get("canonical_reference") or "")
    if not anchor or not os.path.exists(anchor):
        return LoraQualityResult(None, None, skipped=True, skip_reason="no_canonical_reference")

    trigger = character.get("trigger_token") or f"<{character['id']}>"
    strengths = strengths or DEFAULT_STRENGTH_SWEEP
    prompt_tmpls = prompts or DEFAULT_VALIDATION_PROMPTS
    url = _resolve_comfyui_url(comfyui_url)

    sweep = []
    for strength in strengths:
        sample_scores = []
        per_prompt = []
        for i, tmpl in enumerate(prompt_tmpls):
            prompt = tmpl.format(trigger=trigger) if "{trigger}" in tmpl else f"{trigger} {tmpl}"
            seed = _VALIDATION_SEEDS[i % len(_VALIDATION_SEEDS)]
            img = _generate_with_lora(lora_path, prompt, strength=strength, seed=seed,
                                      out_path=f"_loraval_{character['id']}_{strength}_{i}.png",
                                      comfyui_url=url)
            arc = None
            if img:
                sc = _score_candidate(img, anchor)
                if getattr(sc, "has_arc", False):
                    arc = sc.arc_score
            if arc is not None:
                sample_scores.append(arc)
            per_prompt.append((tmpl, arc))
        mean_arc = (sum(sample_scores) / len(sample_scores)) if sample_scores else None
        sweep.append(StrengthScore(strength=strength, mean_arc=mean_arc, per_prompt=per_prompt))

    scored = [s for s in sweep if s.mean_arc is not None]
    if not scored:
        return LoraQualityResult(None, None, sweep=sweep, skipped=True,
                                 skip_reason="generation_or_scoring_unavailable")
    best = max(scored, key=lambda s: s.mean_arc)
    return LoraQualityResult(best_score=best.mean_arc, best_strength=best.strength, sweep=sweep)
```

> **Divergence note:** the settings accessor in `_resolve_comfyui_url` must match the project's real API (`config/settings.py`; the survey saw `settings.comfyui_server_url`). Grep `comfyui_server_url` and use the real accessor; report it.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_lora_quality.py -k validate -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add prep/lora_quality.py tests/unit/test_lora_quality.py
git commit -m "feat(lora): validate_lora_quality scoring oracle — strength sweep + ArcFace (T1 task 3)" -- prep/lora_quality.py tests/unit/test_lora_quality.py
```

---

### Task 4: `train_character_lora_gated` orchestrator + `_escalate_config`

**Files:**
- Modify: `prep/lora_quality.py`
- Test: `tests/unit/test_lora_quality.py`

- [ ] **Step 1: Write the failing tests** (mock `train_character_lora` + `validate_lora_quality`; assert loop count, escalation order, best-strength persistence, warning/reject, skip→register-unvalidated, train-fail→no-retrain)

```python
# add to tests/unit/test_lora_quality.py
def _qr(score, strength, skipped=False, reason=""):
    return lq.LoraQualityResult(best_score=score, best_strength=strength,
                                skipped=skipped, skip_reason=reason)


def test_gated_accepts_on_first_pass(monkeypatch):
    trains = {"n": 0}
    monkeypatch.setattr(lq, "_train_character_lora",
                        lambda pd, ch, **k: (trains.__setitem__("n", trains["n"] + 1)
                                             or {"success": True, "lora_path": "/l/c1.safetensors"}))
    monkeypatch.setattr(lq, "validate_lora_quality", lambda lp, ch, **k: _qr(0.74, 0.55))
    out = lq.train_character_lora_gated("/proj", {"id": "c1"})
    assert trains["n"] == 1
    assert out["rejected"] is False and out["quality_warning"] is False
    assert out["quality_score"] == 0.74 and out["best_strength"] == 0.55


def test_gated_escalates_then_keeps_best(monkeypatch):
    configs = []
    def fake_train(pd, ch, *, config_overrides=None, **k):
        configs.append(dict(config_overrides or {}))
        return {"success": True, "lora_path": f"/l/c1_{len(configs)}.safetensors"}
    seq = iter([_qr(0.50, 0.55), _qr(0.55, 0.7), _qr(0.58, 0.55)])  # never reaches 0.6
    monkeypatch.setattr(lq, "_train_character_lora", fake_train)
    monkeypatch.setattr(lq, "validate_lora_quality", lambda lp, ch, **k: next(seq))
    out = lq.train_character_lora_gated("/proj", {"id": "c1"})
    assert len(configs) == 3                              # 1 base + 2 retrains
    assert configs[1].get("steps") == 4500                # +50% of 3000
    assert configs[2].get("rank") == 64 and configs[2].get("alpha") == 64
    assert out["rejected"] is False and out["quality_warning"] is True   # best 0.58 < 0.6, >= 0.45
    assert out["quality_score"] == 0.58 and out["best_strength"] == 0.55  # best across attempts


def test_gated_rejects_when_net_negative(monkeypatch):
    monkeypatch.setattr(lq, "_train_character_lora",
                        lambda pd, ch, **k: {"success": True, "lora_path": "/l/c1.safetensors"})
    monkeypatch.setattr(lq, "validate_lora_quality", lambda lp, ch, **k: _qr(0.40, 0.55))  # always < baseline
    out = lq.train_character_lora_gated("/proj", {"id": "c1"})
    assert out["rejected"] is True and out["quality_warning"] is True


def test_gated_skip_registers_unvalidated(monkeypatch):
    trains = {"n": 0}
    monkeypatch.setattr(lq, "_train_character_lora",
                        lambda pd, ch, **k: (trains.__setitem__("n", trains["n"] + 1)
                                             or {"success": True, "lora_path": "/l/c1.safetensors"}))
    monkeypatch.setattr(lq, "validate_lora_quality",
                        lambda lp, ch, **k: _qr(None, None, skipped=True, reason="comfyui_unreachable"))
    out = lq.train_character_lora_gated("/proj", {"id": "c1"})
    assert trains["n"] == 1                               # no retrain on skip
    assert out["rejected"] is False and out["quality_score"] is None and out["skipped"] is True


def test_gated_train_failure_returns_immediately_no_retrain(monkeypatch):
    trains = {"n": 0}
    def fail_train(pd, ch, **k):
        trains["n"] += 1
        return {"success": False, "error": "trainer crashed"}
    monkeypatch.setattr(lq, "_train_character_lora", fail_train)
    out = lq.train_character_lora_gated("/proj", {"id": "c1"})
    assert trains["n"] == 1 and out["success"] is False   # infra failure -> no retrain
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_lora_quality.py -k gated -q`
Expected: FAIL — `train_character_lora_gated` not defined.

- [ ] **Step 3: Write the implementation**

```python
# add to prep/lora_quality.py
PASS_THRESHOLD = 0.6
NET_NEGATIVE_BASELINE = 0.45
MAX_LORA_TRAIN_ATTEMPTS = 3
_BASE_STEPS = 3000      # mirror DEFAULT_TRAIN_CONFIG["steps"] (prep/lora_training.py:103)
_HIGHER_RANK = 64       # escalate from base 32 (prep/lora_training.py:100)


def _train_character_lora(project_dir, character, *, config_overrides=None):
    from prep.lora_training import train_character_lora
    return train_character_lora(project_dir, character, config_overrides=config_overrides)


def _escalate_config(config: dict, action: LoraAction) -> dict:
    nxt = dict(config)
    if action is LoraAction.RETRY_MORE_STEPS:
        nxt["steps"] = int(nxt.get("steps", _BASE_STEPS) * 1.5)
    elif action is LoraAction.RETRY_HIGHER_RANK:
        nxt["rank"] = _HIGHER_RANK
        nxt["alpha"] = _HIGHER_RANK
    return nxt


def _gated_result(train: dict, *, score, strength, lora_path, warning, rejected,
                  skipped=False, skip_reason="", attempts=1):
    out = dict(train)
    out.update(lora_path=lora_path, quality_score=score, best_strength=strength,
               quality_warning=warning, rejected=rejected, skipped=skipped,
               skip_reason=skip_reason, attempts=attempts)
    return out


def train_character_lora_gated(project_dir, character, *, config_overrides=None) -> dict:
    """Train -> validate -> decide loop (spec §6.4). Persists nothing itself; returns the
    best result + quality_warning + rejected for the caller (api_train_lora) to register."""
    best = None   # (score, strength, lora_path)
    config = dict(config_overrides or {})
    for attempt in range(MAX_LORA_TRAIN_ATTEMPTS):
        train = _train_character_lora(project_dir, character, config_overrides=config)
        if not train.get("success"):
            return train                                  # infra/train error -> surface, NO retrain
        result = validate_lora_quality(train["lora_path"], character)
        if result.skipped:                                # no GPU/anchor -> register unvalidated
            return _gated_result(train, score=None, strength=None, lora_path=train["lora_path"],
                                 warning=False, rejected=False, skipped=True,
                                 skip_reason=result.skip_reason, attempts=attempt + 1)
        if best is None or result.best_score > best[0]:
            best = (result.best_score, result.best_strength, train["lora_path"])
        action = _next_lora_action(attempt, best[0], threshold=PASS_THRESHOLD,
                                   baseline=NET_NEGATIVE_BASELINE, budget=MAX_LORA_TRAIN_ATTEMPTS)
        if action is LoraAction.ACCEPT:
            return _gated_result(train, score=best[0], strength=best[1], lora_path=best[2],
                                 warning=best[0] < PASS_THRESHOLD, rejected=False, attempts=attempt + 1)
        if action is LoraAction.REJECT:
            return _gated_result(train, score=best[0], strength=best[1], lora_path=best[2],
                                 warning=True, rejected=True, attempts=attempt + 1)
        config = _escalate_config(config, action)
    # Unreachable (the budget-exhausted branch in _next_lora_action always ACCEPT/REJECTs), but be safe:
    return _gated_result(train, score=best[0], strength=best[1], lora_path=best[2],
                         warning=best[0] < PASS_THRESHOLD, rejected=best[0] < NET_NEGATIVE_BASELINE,
                         attempts=MAX_LORA_TRAIN_ATTEMPTS)
```

- [ ] **Step 4: Run to verify it passes + full module**

Run: `.venv/bin/python -m pytest tests/unit/test_lora_quality.py -q`
Expected: PASS (all tasks 1-4 tests).

- [ ] **Step 5: Commit**

```bash
git add prep/lora_quality.py tests/unit/test_lora_quality.py
git commit -m "feat(lora): train_character_lora_gated orchestrator + _escalate_config (T1 task 4)" -- prep/lora_quality.py tests/unit/test_lora_quality.py
```

---

## Chunk 2: Integration into existing code

Wire the new module into the production paths. Each task touches existing files — grep callers first (convention #1).

### Task 5: Make `train_character_lora` pure single-train

**Files:**
- Modify: `prep/lora_training.py:476-505` (remove the validate call), `:508-533` (retire the stub + `LORA_VALIDATION_SKIPPED`), `:540-554` (CLI)

- [ ] **Step 1: Blast-radius grep**

Run: `grep -rn 'validate_lora_quality\|LORA_VALIDATION_SKIPPED' --include='*.py' . | grep -v '.venv' | grep -v worktrees`
Expected: only `prep/lora_training.py` (self) + the `tests/unit/test_check_doc_claims.py` doc-anchor fixture (not a real caller). Confirm zero production importers before removing.
Also `grep -rn 'validate_lora_quality' --include='*.md' docs/ *.md` — `PROGRAM-MANUAL.md`/`-digests.md`/`DECISIONS.md` mention it as prose; if any use a `path:line` **anchor** at the stub, removing it shifts lines → `check_doc_claims.py` (in the done-signal) will flag drift. Fix the anchor or update the prose in the same task.

- [ ] **Step 2: Update the existing train test (or add one) asserting single-train returns a path with `quality_score` no longer set by this function**

```python
# In the appropriate existing test module for lora_training (or a new tests/unit/test_lora_training_singletrain.py):
# Assert: a successful train returns {"success": True, "lora_path": ...} and does NOT call
# validate_lora_quality (it's gone). Mock the subprocess/_run_ai_toolkit boundary as the existing
# tests do; if no existing test mocks training, add a minimal one around the post-train branch.
```
> If `prep/lora_training.py` has no existing unit test that exercises the post-train branch, add a focused one that monkeypatches the trainer subprocess + the `.safetensors` discovery to assert the return shape — keep it boundary-mocked.

- [ ] **Step 3: Run to verify the new/updated assertion fails** against current code (current code still calls the stub).

- [ ] **Step 4: Implementation — remove the validate block + stub**

Delete the `# 5. Validate` block at `prep/lora_training.py:475-493` (the `try: quality = validate_lora_quality(...)` ... `status.quality_score = ...`), leaving the LoRA registered without an internal quality step:
```python
    # (validation now lives in prep.lora_quality.train_character_lora_gated; this function
    #  trains once and returns the path. quality_score stays None here.)
    status.status = "done"
    status.progress_percent = 100.0
    status.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_status(project_dir, status)
    return {"success": True, "lora_path": lora_path, "quality_score": None, "status": asdict(status)}
```
Remove the `LORA_VALIDATION_SKIPPED` constant + the `validate_lora_quality` stub def (`:508-533`). Update the API docstring catalog (`:38`) to drop `validate_lora_quality` (now in `prep.lora_quality`). Leave the CLI `__main__` `train_character_lora(pd, char)` call as-is (single-train still valid) OR point it at the gated orchestrator — implementer's call; if changed, update the import.

- [ ] **Step 5: Run tests + regression**

Run: `.venv/bin/python -m pytest tests/unit/test_lora_quality.py tests/unit/test_check_doc_claims.py -q && .venv/bin/python -m pytest tests/unit/ -q`
Expected: target tests PASS; full suite 0 failures (the doc-anchor fixture test still passes — it uses a synthetic file, not the real symbol).

- [ ] **Step 6: Commit**

```bash
git add prep/lora_training.py tests/unit/   # only the lora_training test files you touched
git commit -m "refactor(lora): train_character_lora is single-train; retire validate stub -> prep.lora_quality (T1 task 5)" -- prep/lora_training.py <explicit test paths>
```

---

### Task 6: `web_server.api_train_lora` → gated orchestrator + persist `char_lora_strengths`

**Files:**
- Modify: `web_server.py:712-742` (the `try`/`_mutate` block)
- Test: `tests/unit/` (mock the orchestrator; assert both keys persisted on accept, no path register on reject)

- [ ] **Step 1: Blast-radius grep + read**

Run: `grep -n 'train_character_lora\|char_lora_paths\|_mutate\|mutate_project' web_server.py` and read `:710-745`. Confirm the `_mutate` mutator shape (the `Project.model_validate(latest)` race-guard + `settings.setdefault("char_lora_paths", {})`).

- [ ] **Step 2: Write the failing test** (mock `train_character_lora_gated` + `mutate_project`; assert persistence)

```python
# tests/unit/test_api_train_lora_persist.py (boundary-mock the web layer per existing web tests)
# - Accept case: gated returns {"success": True, "lora_path": "/l/c1.safetensors",
#   "best_strength": 0.55, "rejected": False}. Capture the mutator's effect on a fake `latest`
#   dict -> assert latest["global_settings"]["char_lora_paths"]["c1"] == "/l/c1.safetensors"
#   AND ["char_lora_strengths"]["c1"] == 0.55.
# - Reject case: gated returns {"rejected": True, ...} -> assert char_lora_paths NOT written.
# Follow the existing web-test harness (Flask test client or direct endpoint-fn call) used by
# the project's other web_server tests; grep tests/unit for 'train-lora' / 'api_train_lora'.
```

- [ ] **Step 3: Run to verify it fails.**

- [ ] **Step 4: Implementation** — call the gated orchestrator + persist both keys inside the existing `_mutate`:

```python
# web_server.py — in api_train_lora's runner:
from prep.lora_quality import train_character_lora_gated
result = train_character_lora_gated(project_dir, char, config_overrides=config_overrides)
if result.get("success") and result.get("lora_path") and not result.get("rejected"):
    def _mutate(latest):
        Project.model_validate(latest)                       # unchanged race-guard
        settings = latest.setdefault("global_settings", {})
        settings.setdefault("char_lora_paths", {})[cid] = result["lora_path"]
        if result.get("best_strength") is not None:          # persist validated strength (no schema change)
            settings.setdefault("char_lora_strengths", {})[cid] = result["best_strength"]
        return MutationResult(True, save=True)
    try:
        mutate_project(pid, _mutate, timeout=HTTP_PROJECT_TIMEOUT)
    except Exception:
        ...   # keep existing handling
# rejected result: do NOT register (PuLID-only); surface result["rejected"]/quality_warning in status.
```
> Keep the existing background-thread exception handling unchanged (pre-existing swallow; out of scope per `336403d`).

- [ ] **Step 5: Run tests + regression** (`.venv/bin/python -m pytest tests/unit/ -q` → 0 failures).

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(web): api_train_lora uses gated orchestrator + persists char_lora_strengths (T1 task 6)" -- web_server.py <explicit test path>
```

---

### Task 7: Production consumption — thread `char_lora_strength` to the injection point

**Files:**
- Modify: `cinema/context.py:103` (add field), `cinema/shots/controller.py:521-527,633` (read + pass), `phase_c_assembly.py:72,76,132` (param + forward), `quality_max.py:649-662,818,920` (param + forward) + `quality_max._inject_identity:458,466-467` (override)
- Test: `tests/unit/` (controller forwards strength; `_inject_identity` honors override)

- [ ] **Step 1: Blast-radius grep** — `grep -rn 'char_lora_path' --include='*.py' . | grep -v .venv | grep -v worktrees` and confirm the 4-hop chain (controller `:633` → phase_c_assembly `:76,132` → quality_max `:662,818,920` → `_inject_identity`). Strength must travel beside path at each hop.

- [ ] **Step 2: Write failing tests**

```python
# (a) _inject_identity override:
def test_inject_identity_honors_char_lora_strength(...):
    wf = {"700": {"class_type": "LoraLoader", "inputs": {}}}
    params = {"lora_strength_model": 1.0, "lora_strength_clip": 1.0}
    quality_max._inject_identity(wf, "mara.safetensors", None, params, True, char_lora_strength=0.55)
    assert wf["700"]["inputs"]["strength_model"] == 0.55
    assert wf["700"]["inputs"]["strength_clip"] == 0.55

def test_inject_identity_uses_tier_default_when_strength_none(...):
    wf = {"700": {"class_type": "LoraLoader", "inputs": {}}}
    params = {"lora_strength_model": 1.0, "lora_strength_clip": 1.0}
    quality_max._inject_identity(wf, "mara.safetensors", None, params, True, char_lora_strength=None)
    assert wf["700"]["inputs"]["strength_model"] == 1.0
# (mirror the existing tests/unit/test_quality_max_prune.py::_inject_identity patterns)

# (b) controller forwards strength:
def test_controller_forwards_char_lora_strength(monkeypatch):
    # settings has char_lora_strengths={"c1":0.55}; mock generate_ai_broll; assert it was called
    # with char_lora_strength=0.55 for a shot whose primary_character is c1.
```

- [ ] **Step 3: Run to verify they fail** (param doesn't exist yet).

- [ ] **Step 4: Implementation (4 hops + override)**

  - `cinema/context.py`: add `char_lora_strengths: dict = field(default_factory=dict)` beside `char_lora_paths` (`:103`).
  - `cinema/shots/controller.py` (~`:527`): `char_lora_strength = (settings.get("char_lora_strengths", {}) or {}).get(primary_char_id)`; pass `char_lora_strength=char_lora_strength` at the `generate_ai_broll(...)` call (`:633`).
  - `phase_c_assembly.generate_ai_broll` (`:72`): add `char_lora_strength=None` param; forward to `generate_ai_broll_max(..., char_lora_strength=char_lora_strength)` (`:132`).
  - `quality_max.generate_ai_broll_max` (`:649`): add `char_lora_strength: Optional[float] = None` (`:662`); pass to both `_inject_identity(...)` calls (`:818,:920`).
  - `quality_max._inject_identity` (`:458`): add `char_lora_strength: Optional[float] = None`; inside the has-LoRA branch (`:466-467`), `s = char_lora_strength if char_lora_strength is not None else params.get("lora_strength_model", 1.0)` and set both `strength_model`/`strength_clip = s`.

- [ ] **Step 5: Run tests + full regression + smoke**

Run: `.venv/bin/python -m pytest tests/unit/ -q && .venv/bin/python scripts/ci_smoke.py && .venv/bin/python scripts/check_doc_claims.py`
Expected: 0 failures; smoke `OK`; anchors no drift.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(pipeline): thread per-character char_lora_strength to ComfyUI injection (T1 task 7)" -- cinema/context.py cinema/shots/controller.py phase_c_assembly.py quality_max.py <explicit test paths>
```

---

## After all tasks

- Dispatch a final cross-cutting code-quality reviewer (BASE = `082edb5`, HEAD = final commit) per `superpowers:subagent-driven-development`. Emphasize: the loop's `best`-tracking correctness, the `has_arc` skip semantics, the 4-hop strength threading (no missed hop = silent no-op), and that no production path now hard-crashes when validation is skipped.
- Update `ARCHITECTURE.md` if the LoRA-training subsystem is documented there (grep `lora_training` / `validate_lora_quality`); Lane D doc-sync convention applies.
- This offline plan ships **design + boundary tests only**. The real loop (generation + ArcFace + retrain) requires a GPU pod → a follow-up spend-gated Phase-B pass calibrates `PASS_THRESHOLD` / `NET_NEGATIVE_BASELINE` / `DEFAULT_STRENGTH_SWEEP` against live scores and exercises an end-to-end train→validate→persist run.

## Notes for the executor
- **Shared working tree:** the director is clearing parallel no-op tickets on this branch. ALWAYS `git diff --cached --name-only` before staging and commit with explicit pathspec. Never `-a`/`add -A`.
- **No GPU in CI:** every test here mocks the ComfyUI + scoring + training boundaries. If a test needs a real generation, it's in the wrong layer — push the seam to a `_qm_*` / `_generate_with_lora` / `validate_lora_quality` boundary and mock there.
- **Plan-vs-source:** exact arg lists for the `quality_max._inject_*`/`_run_one_candidate` helpers and the settings accessor must be confirmed from source at execution time (Tasks 2-3 flag the specific spots). Use source over this plan's sketch and report divergences.
