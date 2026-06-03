# Design — `validate_lora_quality` + auto-retrain quality gate (T1)

*Status: APPROVED (user, 2026-06-03) — pending spec-review loop + user spec review.*
*Author: operator-seat. Branch `feat/max-tier-provisioning` @ `1fcaaaa` (refs verified at `547f7e7`, re-confirmed at `1fcaaaa`; intervening T8/T11 commits touch neither the LoRA files nor the threading hops).*
*Source ticket: T1 (HIGH) in `docs/superpowers/2026-06-03-part3-noop-audit-tickets.md`.*
*Program context: Test/Audit program Part-3 fix-list; PROGRAM-MANUAL §5 (capability-maximization).*

> **All file:line refs verified at HEAD `1fcaaaa` (2026-06-03)** per ADR-013. The
> survey that seeded this design was wrong on one detail (it named
> `score_candidate(..., reference_path=)`; the real param is `face_anchor`) — corrected
> below from direct reads.

---

## 1. Context & problem

`validate_lora_quality(lora_path, character) -> float` (`prep/lora_training.py:515`) is an
unconditional `-1.0` stub (`LORA_VALIDATION_SKIPPED`, `:512`). Its caller
`train_character_lora` (`:480-493`) maps the sentinel to `status.quality_score = None`
("not validated" in the UI). **No real check runs.**

Per the manual, a per-character trained LoRA is *the single biggest identity-quality lever*
(module docstring `prep/lora_training.py:10-16`). Two consequences of the missing gate:

1. **Silent degradation.** A LoRA that fails to learn identity (bad/insufficient dataset,
   under/over-training) is registered and used for every shot of that character with no
   signal that identity quality dropped.
2. **The 1.0-over-bake gap.** Production bakes every char-LoRA at **strength 1.0** — the tier
   default in `workflow_selector.py:154-155`, applied at `quality_max.py:466-467`. But the
   project's own realism finding (memory `realism_production_plus_char_lora`) is that **0.55
   beats 1.0** (1.0 over-bakes into "painterly"). That finding was validated only in throwaway
   scripts (`scripts/_fal_lora_production.py:46`) and **never wired into production**;
   `char_lora_paths` stores paths only, no per-character strength.

A working prototype of the intended validation already exists:
`scripts/_fal_lora_production.py:95-113` generates sample images from a trained LoRA and scores
each with `score_candidate(...).arc_score`. This design productionizes that proven flow and adds
an auto-retrain control loop + per-character strength persistence.

## 2. Goals / non-goals

**Goals**
- Replace the stub with a real ArcFace-based identity validation of a trained char-LoRA.
- **Gate + auto-retrain:** on a low identity score, escalate-retrain (bounded); keep the best
  result; reject only if it is net-negative vs. no-LoRA.
- **Strength sweep + persist:** find the best LoRA strength per character and persist it into
  production (closing the 1.0-over-bake gap).
- Every decision unit unit-testable **without a GPU** (CI has no ComfyUI).
- Never crash training when validation can't run (graceful skip preserves today's behavior).

**Non-goals**
- Live calibration of threshold/strength values (needs a GPU pod → deferred to a spend-gated
  Phase-B pass; this offline session ships design + boundary tests only).
- Hyperparameter sweeps beyond the fixed escalation ladder (steps → rank).
- Multi-character / distributed training (out of scope per the module's stated non-goals).
- A new UI surface (the score already flows to `status.quality_score`; richer surfacing is
  Part-4 UI work, separate).

## 3. Decisions (user-approved) & rationale

| # | Decision | Rationale |
|---|---|---|
| D1 | **Gate + auto-retrain** (not warn-only / reject-only / informational) | Max-capability per PROGRAM-MANUAL §5; actively recovers a bad LoRA instead of only reporting it. |
| D2 | **Strength sweep + persist per-character strength** | Cheapest rescue path (no retrain) AND the mechanism to finally wire the 0.55 finding into production. |
| D3 | **≤2 retrains; keep best; reject if net-negative** | Bounds GPU cost (≤3 trains); never ships a LoRA worse than PuLID-only; always keeps a net-positive one. |
| D4 | **Architecture B** — extracted orchestrator + pure decision fn + scoring oracle + thin gen helper | Each unit independently testable; the pure decision fn proves the policy in CI with no GPU; keeps files focused. |

## 4. Architecture

New module **`prep/lora_quality.py`** (keeps `prep/lora_training.py` — already 555 lines —
focused on "train once"). Five units:

| Unit | Responsibility | IO |
|---|---|---|
| `_generate_with_lora(lora_path, prompt, strength, seed, out_path) -> Optional[str]` | One honest ComfyUI generation: load the max workflow, inject the LoRA at node 700 at `strength`, set prompt+seed, submit, poll, return image path. **No N=8 best-of, no ArcFace gating.** Mirrors `scripts/_fal_lora_production.py:42-56`. | ComfyUI |
| `validate_lora_quality(lora_path, character, *, strengths, prompts, comfyui_url) -> LoraQualityResult` | Scoring oracle: sweep `strengths` × `prompts`, score each generation, pick best strength. | via gen + scoring |
| `_next_lora_action(attempt, best_score, *, threshold, baseline, budget) -> LoraAction` | **Pure** policy fn → `ACCEPT \| RETRY_MORE_STEPS \| RETRY_HIGHER_RANK \| REJECT`. Zero IO. | none |
| `train_character_lora_gated(project_dir, character, *, config_overrides) -> dict` | Orchestrator: loop train → validate → decide; persist best (path+strength); return score + `quality_warning` + `rejected`. | via train + oracle |
| `LoraQualityResult`, `LoraAction` (dataclass / enum) | Return/decision types. | — |

`prep/lora_training.py` change: `train_character_lora` loses its internal validate call
(`:480-493`) → becomes pure single-train returning `{success, lora_path, status}`.
`web_server.api_train_lora` (`web_server.py:712`) calls `train_character_lora_gated` instead.

## 5. Data structures

```python
# prep/lora_quality.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

@dataclass
class StrengthScore:
    strength: float
    mean_arc: Optional[float]          # mean arc_score across prompts at this strength; None if all skipped
    per_prompt: list                   # [(prompt_label, arc_score|None), ...] for diagnostics

@dataclass
class LoraQualityResult:
    best_score: Optional[float]        # mean_arc at the best strength; None if skipped
    best_strength: Optional[float]     # argmax strength; None if skipped
    sweep: list                        # list[StrengthScore]
    skipped: bool                      # True when no generation/scoring could run (no GPU/ComfyUI/anchor)
    skip_reason: str = ""              # e.g. "comfyui_unreachable", "no_canonical_reference"

class LoraAction(Enum):
    ACCEPT = "accept"                  # register best (caller sets quality_warning if best < threshold)
    RETRY_MORE_STEPS = "retry_more_steps"
    RETRY_HIGHER_RANK = "retry_higher_rank"
    REJECT = "reject"                  # do NOT register; PuLID-only fallback
```

## 6. Component design

### 6.1 `_generate_with_lora` — honest single-shot generation

- Reuse the existing max-workflow primitives from `quality_max` (the LoraLoader node 700 +
  `_inject_identity` injection point at `quality_max.py:458-467`). Build a **minimal** workflow:
  inject the LoRA with `strength_model = strength_clip = strength`, set the positive prompt +
  `seed`, submit to `comfyui_url` (default `settings.comfyui_server_url`, env
  `COMFYUI_SERVER_URL`, default `http://127.0.0.1:8188`), poll `/history/<id>`, save & return the
  image path. Single deterministic generation — **no best-of loop, no ArcFace selection** (that
  would inflate the measured score).
- Implementation note: prefer reusing `quality_max`'s workflow-load + node-injection helpers over
  hand-rolling JSON, so the validation path tracks the production node graph. If a clean reuse
  isn't exposed, mirror `scripts/_fal_lora_production.py:42-56` and file a follow-up to factor a
  shared helper (do not silently fork the graph).
- Returns `None` on: ComfyUI unreachable, submit/poll error, or no image produced. Never raises to
  the caller for infra failure (the oracle converts `None` → skip).

### 6.2 `validate_lora_quality` — scoring oracle

```python
def validate_lora_quality(lora_path, character, *, strengths=DEFAULT_STRENGTH_SWEEP,
                          prompts=None, comfyui_url=None) -> LoraQualityResult:
```
- Resolve the reference: `anchor = character.get("canonical_reference") or ""`. If empty or
  missing on disk → `LoraQualityResult(skipped=True, skip_reason="no_canonical_reference")`
  (verified: set at `domain/character_manager.py:150`, may be `""`).
- Resolve the trigger token: `character.get("trigger_token") or f"<{character['id']}>"`
  (verified default scheme: `prep/lora_training.py:111,192-193`).
- `prompts` default = `DEFAULT_VALIDATION_PROMPTS` — 3 varied templates, each formatted with the
  trigger token, each with a fixed seed (reproducibility):
  - `"{trigger} photo, professional headshot, soft natural light"`
  - `"{trigger} photo, full body, daylight, casual outfit"`
  - `"{trigger} portrait, side profile, indoor window light"`
  (first two mirror the dataset caption style at `prep/lora_training.py:342-343`.)
- For each `strength` in `strengths`: for each prompt → `_generate_with_lora(...)` →
  `score_candidate(image_path, anchor, threshold=0.0)` (verified signature
  `face_validator_gate.py:170` — second param is the **`face_anchor`** positional;
  `CandidateScore.arc_score` ∈ [0,1] at `:159`). **Read `score.arc_score` only when
  `score.has_arc` is True**; otherwise that sample is a skip (the anchor wasn't usable). A
  strength's `mean_arc` = mean of the non-skipped sample scores (None if all skipped).
- `best_strength` = argmax `mean_arc`; `best_score` = that `mean_arc`. If every strength is None →
  `skipped=True, skip_reason="generation_or_scoring_unavailable"`.

### 6.3 `_next_lora_action` — pure decision (the CI-testable core)

```python
def _next_lora_action(attempt, best_score, *, threshold, baseline, budget) -> LoraAction:
    # attempt is 0-based index of the train just validated; budget = max trains (default 3)
    if best_score is None:            # validation skipped — caller handles as "register unvalidated"
        return LoraAction.ACCEPT
    if best_score >= threshold:
        return LoraAction.ACCEPT
    if attempt + 1 >= budget:          # retrain budget exhausted
        return LoraAction.ACCEPT if best_score >= baseline else LoraAction.REJECT
    return LoraAction.RETRY_MORE_STEPS if attempt == 0 else LoraAction.RETRY_HIGHER_RANK
```
- Encodes D3 exactly. No IO → exhaustively unit-testable. The caller (orchestrator) is
  responsible for mapping `ACCEPT` with `best_score < threshold` → set `quality_warning=True`.

### 6.4 `train_character_lora_gated` — orchestrator

```
best = None   # (score, strength, lora_path)
config = dict(config_overrides or {})
for attempt in range(MAX_LORA_TRAIN_ATTEMPTS):          # default 3
    train = train_character_lora(project_dir, character, config_overrides=config)
    if not train["success"]:
        return train                                     # infra/train error → surface, NO retrain
    result = validate_lora_quality(train["lora_path"], character)
    if result.skipped:
        # can't gate without GPU/anchor → register unvalidated at default strength (today's behavior)
        return _result(train, score=None, strength=None, warning=False, rejected=False,
                       skipped=True, skip_reason=result.skip_reason)
    best = _max_by_score(best, (result.best_score, result.best_strength, train["lora_path"]))
    action = _next_lora_action(attempt, best[0], threshold=PASS_THRESHOLD,
                               baseline=NET_NEGATIVE_BASELINE, budget=MAX_LORA_TRAIN_ATTEMPTS)
    if action is LoraAction.ACCEPT:
        return _result(train, score=best[0], strength=best[1], lora_path=best[2],
                       warning=best[0] < PASS_THRESHOLD, rejected=False)
    if action is LoraAction.REJECT:
        return _result(train, score=best[0], strength=best[1], lora_path=best[2],
                       warning=True, rejected=True)      # caller must NOT register; PuLID-only
    config = _escalate_config(config, action)            # RETRY_* → bump steps or rank
```
- `_escalate_config`: `RETRY_MORE_STEPS` → `steps = int(steps * 1.5)` (default `3000→4500`, base
  `DEFAULT_TRAIN_CONFIG["steps"]=3000` at `prep/lora_training.py:103`); `RETRY_HIGHER_RANK` →
  `rank = 64, alpha = 64` (base `rank=alpha=32` at `:100-101`) and keep the bumped steps.
- Only a **low quality score** drives retrain. A train/infra failure returns immediately (no
  point retraining a broken environment).
- Returns a dict superset of today's `train_character_lora` result plus:
  `quality_score` (float|None), `best_strength` (float|None), `quality_warning` (bool),
  `rejected` (bool), `attempts` (int), `sweep` (diagnostics).

## 7. Production wiring — per-character strength

- **Settings:** add `char_lora_strengths: dict  # {char_id: float}`, parallel to
  `char_lora_paths`. Written by `api_train_lora` on a non-rejected result **inside the existing
  `_mutate` mutator** (`web_server.py:725-737`), beside the existing `char_lora_paths`
  `setdefault` — `settings.setdefault("char_lora_strengths", {})[cid] = best_strength`.
  **No Pydantic schema change needed** (verified): `domain/models.py` models are
  `ConfigDict(extra="allow")` (`:9,29,173`) and `global_settings` is a free-form dict —
  `char_lora_paths` itself is not a declared field, just a dict key, so the inner
  `Project.model_validate(latest)` race-guard tolerates the new key. (A spec-review flagged a
  possible schema-rejection; verification showed the schema is permissive — folded here as a
  positive note so the implementer doesn't add a spurious no-op schema edit.) Keep the existing
  background-thread exception handling as-is (pre-existing swallow; out of scope per
  `336403d`/B-006-broad-B history).
- **Context:** add `char_lora_strengths: dict = field(default_factory=dict)` to
  `cinema/context.py` (beside `char_lora_paths` at `:103`, mirroring its comment at `:102`).
- **Consumption:** thread a `char_lora_strength: Optional[float]` beside `char_lora_path` at every
  existing hop (verified threading path):
  - `cinema/shots/controller.py` — read `char_lora_strengths.get(primary_char_id)` near `:521-527`;
    pass at the `generate_ai_broll(...)` call (`:633`).
  - `phase_c_assembly.generate_ai_broll` — add param (`:72,76`); forward to
    `generate_ai_broll_max` (`:132`).
  - `quality_max.generate_ai_broll_max` — add param (`:649,662`); pass to `_inject_identity`
    (`:818,:920`).
  - `quality_max._inject_identity` (`:458`) — when `char_lora_strength is not None`, override
    `strength_model`/`strength_clip` (currently `params.get("lora_strength_model", 1.0)` at
    `:466-467`); else keep the tier-param default.
- **Backward compat:** absent `char_lora_strengths` entry → `None` → tier default (1.0/0.9)
  unchanged. Existing projects are unaffected.

## 8. Contract changes (safe — `validate_lora_quality` has **zero external callers**; verified by repo-wide grep)

- `validate_lora_quality` returns `LoraQualityResult`, not `float`. `LORA_VALIDATION_SKIPPED`
  (`prep/lora_training.py:512`) retired in favor of `LoraQualityResult.skipped`.
- `train_character_lora` no longer validates internally (`:480-493` removed); returns
  `{success, lora_path, status}` (its `status.quality_score` stays `None` — the orchestrator owns
  quality now).
- `web_server.api_train_lora` calls `train_character_lora_gated`; persists `char_lora_paths` +
  `char_lora_strengths` on accept; on `rejected` does **not** register the path (status reflects
  `rejected` + reason). `get_lora_status` (`web_server.py:768`) gains the new fields via status.
- The CLI `__main__` block (`prep/lora_training.py:540-554`) currently calls
  `train_character_lora(pd, char)` **positionally** (no `config_overrides`). Update it to call the
  gated orchestrator (or leave on single-train with a comment) — plan-time call; either way the
  call site must be touched since signatures/return shape change.

## 9. Configuration & defaults

| Constant (module-level, overridable) | Default | Notes |
|---|---|---|
| `PASS_THRESHOLD` | `0.6` | char-LoRA reaches 0.6–0.79 (memory); 0.6 = meaningfully > PuLID. |
| `NET_NEGATIVE_BASELINE` | `0.45` | PuLID-only floor; below this a LoRA is worse than no-LoRA. |
| `DEFAULT_STRENGTH_SWEEP` | `[0.45, 0.55, 0.7, 1.0]` | brackets the 0.55 finding + current 1.0 default. |
| `DEFAULT_VALIDATION_PROMPTS` | 3 varied templates | §6.2; trigger-token-formatted, fixed seeds. |
| `MAX_LORA_TRAIN_ATTEMPTS` | `3` | 1 base + ≤2 retrains. |
| escalation | steps×1.5 (`3000→4500`), then rank `32→64` | base from `DEFAULT_TRAIN_CONFIG`. |

All are design defaults; **live calibration is a deferred Phase-B pod task.**

## 10. Error handling / graceful skip

- ComfyUI unreachable, generation `None`, or unusable/empty `canonical_reference` → `skipped=True`
  → orchestrator registers the first trained LoRA **unvalidated** at default strength
  (`quality_score=None`) — preserves today's non-fatal behavior; never crashes training.
- Train subprocess failure → returned immediately (distinct from a quality failure; no retrain).
- Scoring backend (DeepFace) unavailable → `score_candidate` yields `has_arc=False` per sample →
  treated as per-sample skip; all-skipped → `skipped=True`.

## 11. Testing strategy (all boundary-mocked; no GPU in CI)

New `tests/unit/test_lora_quality.py`:
1. **`_next_lora_action` (pure, no mocks):** pass-on-first; low→escalate-steps→escalate-rank→pass;
   exhaust→ACCEPT-best (best ≥ baseline, < threshold); exhaust→REJECT (best < baseline);
   `best_score=None`→ACCEPT.
2. **`train_character_lora_gated`:** monkeypatch `train_character_lora` (scripted fake paths) +
   `validate_lora_quality` (scripted `LoraQualityResult`s) → assert loop count, `_escalate_config`
   transitions (steps then rank), best-strength persistence, `quality_warning`/`rejected` flags,
   skip→register-unvalidated, train-failure→immediate-return-no-retrain.
3. **`validate_lora_quality`:** monkeypatch `_generate_with_lora` (fixture image paths) +
   `score_candidate` (scripted `CandidateScore`s incl. `has_arc=False`) → assert sweep picks
   argmax strength, mean math ignores skipped samples, empty `canonical_reference`→skipped.
4. **`_generate_with_lora`:** monkeypatch the ComfyUI HTTP boundary → assert LoRA node-700
   injection + strength set + single generation (no best-of); unreachable→`None`. Reuse patterns
   from `tests/unit/test_quality_max_prune.py`.
5. **Wiring:** controller forwards `char_lora_strength` (mock `generate_ai_broll`, assert kwarg);
   `_inject_identity` strength override honored when set, tier default when `None`.
- Done-signal: full unit suite green (current baseline **1512/3/0**), `ci_smoke` OK, anchors clean.

## 12. File-by-file change list

| File | Change | ~LOC |
|---|---|---|
| `prep/lora_quality.py` (new) | the 5 units + constants | ~220 |
| `prep/lora_training.py` | remove internal validate (`:480-493`); retire stub+sentinel; CLI tweak | ~−25 |
| `web_server.py` | `api_train_lora`→gated orchestrator; persist `char_lora_strengths` in the existing `_mutate` mutator beside `char_lora_paths` (`:725-737`); no schema change | ~+20 |
| `cinema/context.py` | add `char_lora_strengths` field (`~:103`) | ~+2 |
| `cinema/shots/controller.py` | read strength + pass at `generate_ai_broll` (`~:521-527,633`) | ~+5 |
| `phase_c_assembly.py` | add+forward `char_lora_strength` (`:72,76,132`) | ~+4 |
| `quality_max.py` | add+forward param; override in `_inject_identity` (`:458-467,649-662,818,920`) | ~+10 |
| `tests/unit/test_lora_quality.py` (new) | the 5 test groups | ~300 |

~5–6 production files + 1 new module + tests → executed as a **writing-plans plan via
subagent-driven-development** (TDD + 2-stage review per task), not a single edit.

## 13. Scope / risk / deferred

- **Multi-task** (≥5 files) → orchestrated, not done inline.
- **Live calibration deferred** (no GPU this session): threshold/baseline/strengths/prompts are
  design defaults to be tuned in a spend-gated Phase-B pod pass. The design is
  correct-by-construction + boundary-tested; the pure decision fn fully proves the policy.
- **Cost (when it does run live):** up to 3 trains + (4 strengths × 3 prompts) gens per validation
  pass. Counts are configurable; the strength-sweep-before-retrain ordering minimizes retrains.
- **Workflow reuse risk:** `_generate_with_lora` must reuse `quality_max`'s node graph, not fork
  it, or the validation path drifts from production. Flagged in §6.1.
- **Backward compatibility:** preserved — absent strength → tier default; skip → today's behavior.

## 14. Open questions

- None blocking. The only judgment deferred is live calibration (Phase-B). The CLI `__main__`
  entry's exact behavior (gated vs single-train) is a minor plan-time call (§8).
