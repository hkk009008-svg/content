# Part-3 Quality-Gate Fixes — Design Spec

*Date: 2026-06-03 · Branch: `feat/max-tier-provisioning` · Status: design approved, pre-plan*

## 1. Context & problem

The Plan-2 characterization sweep (2026-06-03 handoff) added 157 offline tests to the
five zero-test core components and surfaced ~11 real findings, durably marked
`# CANDIDATE BUG (Gn)` in the test files. This spec covers the **three HIGH findings**
(the moderates/minors are explicitly out of scope, §8). All three are *silent
quality-gate degradation*: a check that should catch a problem instead passes silently.

The findings were re-verified against source (read-only survey, 2026-06-03). The unifying
insight for two of them: **the identity validator has only `pass`/`fail` and fabricates a
*pass* (`passed=True, overall_score=1.0`) whenever it cannot actually check identity.**

### The three HIGH findings (verified file:line)

- **F1 — silent-pass-on-missing-file (SYSTEMIC, 2 modules).**
  - `identity/validator.py:696` `_no_file_result()` → `passed=True, overall_score=1.0`,
    called at 4 trigger sites: `validate_image` missing-file (~line 83) and
    no-reference-embedding (~line 97); `validate_video` no-character-configs (~line 155)
    and all-references-fail-to-load (~line 179).
  - `phase_c_vision.py`: `validate_identity_vision` (lines 260–265) returns
    `{"match": True, "confidence": 0.7}` on missing reference OR generated file. This is
    the **live** path — it is the DeepFace-absent vision fallback injected into
    `IdentityValidator` (`identity/__init__.py:53–54`); its result is converted to an
    `IdentityValidationResult` by `_vision_llm_validate_image` (`identity/validator.py`
    ~724–771). `quality_control_image` (lines 112–114, returns `True`) and
    `validate_shot_quality_vision` (lines 170–173, returns `default_pass`) have **zero
    production callers** (dead code) but are characterization-tested.
  - Effect: a missing/stale/partially-written image path silently PASSES identity (and the
    dead QC) instead of failing or being flagged. Callers that gate on `result.passed`
    are told "fine."

- **F2 — landscape identity *always fails*.** `identity/validator.py`
  `_compute_sample_positions` (~387–406) returns `[]` for `shot_type="landscape"`
  (density `0.0`; landscape threshold is `0.0` in `SHOT_TYPE_THRESHOLDS`,
  `identity/types.py:97`). `validate_video` then aggregates zero frames →
  `_aggregate_character(cid, name, [], threshold)` (~585–590) → `matched=False,
  NO_FACE_DETECTED` → `passed=False, overall_score=0.0`. **Only when refs exist**
  (no refs → `_no_file_result` passes first). A landscape shot has no face to match, so
  failing it is wrong and triggers retries that can never succeed.

- **F3 — photorealism formula silently dropped.** `llm/style_director.py` returns the
  LLM JSON with **no schema validation** (`rules = json.loads(raw); ... return rules`,
  ~112–119). If the model omits `photorealism_rules`, `style_rules_to_prompt_suffix`
  (~189–190: `if style_rules.get("photorealism_rules"):`) silently omits the core
  photorealism injection from **every shot's image prompt** for that run. The
  `_default_style_rules` fallback (~138) always includes the key but is reached **only**
  on an exception / malformed JSON — not on valid-but-incomplete JSON.

## 2. Decisions (made during brainstorming, 2026-06-03)

1. **Scope:** all 3 HIGH findings in this spec, as separable implementation slices. The
   5 moderates are deferred to a follow-up cycle.
2. **Gate policy ("distinguish the cases"):** replace the fabricated `passed=True/1.0`
   with a *behavior that depends on the trigger* —
   - a **missing generated output** (image, or the video file in `validate_video`) is a
     real generation/IO failure → **FAIL** (surface it; let the shot retry);
   - **genuinely nothing to compare** (missing *reference*, landscape/no-face-expected,
     no character configured) → **SKIP** (the shot proceeds, but the result is honestly
     marked "not validated" — no fabricated score).
3. **Mechanism:** add a `skipped: bool` flag + make `overall_score` nullable
   (`Optional[float]`, `None` on skip), rather than a full tri-state status enum (YAGNI)
   or overloading `primary_failure_reason`. `passed` semantics are preserved so the
   existing call sites that gate on `if not result.passed` need no migration.
4. **Judgment calls (approved):** (a) a missing **video file** in `validate_video` is
   treated as FAIL, same class as a missing generated image; (b) the two **dead-code**
   vision functions are fixed for consistency (with a comment noting they are currently
   unreached), rather than left divergent.

## 3. Schema change — `identity/types.py`

- `IdentityValidationResult.overall_score: float` → `Optional[float]` (line 66). `None`
  iff `skipped`.
- Add field `skipped: bool = False` (place after `metadata`, which already has a default,
  to keep dataclass default-ordering valid).
- `FailureReason` (lines 19–28) += `GENERATED_IMAGE_MISSING = "generated_image_missing"`.
- `.get()` backward-compat (lines 74–85): `get("similarity")` returns `overall_score`,
  which is now possibly `None` on skip. Leave the accessor as-is; the **score-reader
  audit** (§5) ensures no consumer dereferences it as a float on a skipped result.

**Invariant:** `skipped == True` ⟹ `passed == True` and `overall_score is None`.
`skipped == False` ⟹ `overall_score is not None`.

## 4. Per-finding design

### 4.1 F1 — `identity/validator.py`

Split `_no_file_result` (696) into two precise helpers:
- `_skipped_result(shot_type, threshold)` → `passed=True, skipped=True, overall_score=None,
  character_results={}, frames_sampled=0`.
- `_missing_output_result(shot_type, threshold)` → `passed=False, skipped=False,
  overall_score=0.0, character_results={}, frames_sampled=0`, with the missing-output
  signal carried via `metadata` and/or a `CharacterIdentityResult.primary_failure_reason
  = GENERATED_IMAGE_MISSING` where a character result is constructed.

Re-point the 4 trigger sites:
- `validate_image` (~83): **split** the combined `not exists(image) or not exists(ref)`
  check. `image_path` missing → `_missing_output_result` (FAIL). `reference_path` missing
  → `_skipped_result` (SKIP). (The combined condition sits a few lines *above* the line-83
  `return`; Read ~78–100 before editing — don't jump straight to 83.)
- `validate_image` (~97): reference yields no embedding → `_skipped_result` (can't
  compare).
- `validate_video` (~155): no `character_configs` → `_skipped_result`.
- `validate_video` (~179): all reference images fail to load → `_skipped_result`.
- `validate_video` **video file missing** (add an explicit guard near the top if not
  already present) → `_missing_output_result` (FAIL).

Skipped/missing early-returns must continue to **not** append to `self.history`
(preserves the PuLID/stats feedback loop; verified already true for the current
early-returns).

### 4.2 F1 — vision fallback `phase_c_vision.py`

- `validate_identity_vision` (260–265): missing **reference** → skip-shaped return; missing
  **generated** → fail-shaped return. The dict gains an explicit marker (e.g.
  `{"skip": True}` for ref-missing, `{"match": False, "missing_generated": True}` for
  gen-missing). `_vision_llm_validate_image` (`identity/validator.py` ~724–771) maps the
  marker to `_skipped_result` / `_missing_output_result` so the policy is identical to
  the DeepFace path.
- Dead code, fixed for consistency (with an "unreached in production" comment):
  `quality_control_image` (112–114) → return `False` on missing file;
  `validate_shot_quality_vision` (170–173) → `{"pass": False, ...}` on missing file.
  (Zero callers on `main`/`feat`; the only references are in historical
  `.claude/worktrees/` branches — ignore those, do not preserve the old behavior for them.)

### 4.3 F2 — landscape skip, `identity/validator.py`

In `validate_video`, immediately after `_compute_sample_positions` returns `[]`
(which occurs **only** for landscape per the threshold table), return `_skipped_result`
**before** the per-character aggregation that currently manufactures
`matched=False / NO_FACE_DETECTED`. **Detect with `if not positions:`** (the empty list),
NOT a literal `shot_type == "landscape"` string — the empty-positions check tracks the
actual sampling decision and so also covers any future zero-density shot type. (Empty
positions currently arises only for landscape / threshold `0.0`.)

### 4.4 F3 — `llm/style_director.py`

Immediately after `rules = json.loads(raw)` (~112), merge over defaults so required keys
cannot vanish:
```python
defaults = _default_style_rules(mood, color_palette, music_mood)
missing = [k for k in defaults if k not in rules]
if missing:
    print(f"   ⚠️ style rules missing {missing} — back-filling from defaults")
rules = {**defaults, **rules}   # LLM values win; absent keys back-filled
```
Guarantees `photorealism_rules` (and the other required keys) are always present →
`style_rules_to_prompt_suffix` always injects the photorealism formula. Purely additive
for both callers (`cinema_pipeline.py:922`, `web_server.py:1420`) — they only ever receive
*more* keys than before. (Note: `_default_style_rules` signature is
`(mood, color_palette, music_mood)`; confirm the exact arg names/availability at
implementation and adapt — plan-vs-source divergence rule.)

## 5. Call-site impact & the `Optional[float]` audit

Two distinct surfaces.

**(a) Gate sites — gate on `result.passed`, no logic change.** Skip → `passed=True` →
proceed; missing-output → `passed=False` → retry:
- `cinema/shots/controller.py:651`, `:1813`
- `face_validator_gate.py:141`
- `performance/identity_gate.py:71`
- `domain/continuity_engine.py:616`

**(b) Score-reader sites — MUST be guarded for `None` (the #1 risk).** Making
`overall_score` nullable turns every direct read into a crash- or `None`-store risk.
Authoritative production read sites (verified
`grep -rn "\.overall_score" --include='*.py'`, excluding tests + `.claude/worktrees/`):

| Site | Code | Risk on skip (`None`) | Guard |
|---|---|---|---|
| `face_validator_gate.py:142` | `return float(result.overall_score)` | **TypeError** (`float(None)`) | guard skip before the `float()`; return value per caller intent (this feeds a gate — skip must not block) |
| `performance/identity_gate.py:72` | `return float(result.overall_score)` | **TypeError** | same |
| `llm/chief_director.py:360` | `identity_score = identity_result.overall_score`; then `identity_passed = identity_score >= threshold` (line 365) | **TypeError** (`None >= float`) | when `skipped`: set `identity_passed = True` (skip ⇒ don't drive an identity mutation) and bypass the `>=` compare |
| `cinema/shots/controller.py:656` | `identity_score = id_result.overall_score` → `take["metadata"]["identity_score"]` | stores `None` | store `None` or a skip marker; ensure metadata consumers tolerate it |
| `cinema/shots/controller.py:1041` | `vid_result.overall_score if hasattr(...) else 0.0` | returns `None` (hasattr is True; no `None` guard) | add `and vid_result.overall_score is not None` |
| `cinema/shots/controller.py:1816` | `result["scores"]["identity"] = id_result.overall_score` | stores `None` | as :656 |
| `identity/types.py:79` | `.get("similarity")` returns `overall_score` | returns `None` | the accessor is fine; audit `.get("similarity")` consumers the same way |

The three `float()`/compare sites (`face_validator_gate:142`, `performance/identity_gate:72`,
`chief_director:360`) are hard crashes and **MUST** be guarded in slice B. The three
controller store-sites are lower-risk (store `None`) but should set a skip-aware value for
operator-facing diagnostics. Skipped results don't enter `self.history`, so the
rolling-stats / PuLID feedback path is safe by construction.

## 6. Test strategy (TDD)

Flip each `# CANDIDATE BUG` characterization assertion from "asserts the quirk" to
"asserts the fix", and add coverage for the new states. Write/adjust the test first, watch
it fail against current code, then implement (per slice).

- `tests/unit/test_identity_validator.py`:
  - G1 (95–107) missing image → now `passed=False`, `GENERATED_IMAGE_MISSING`,
    `skipped=False`.
  - G1 split: missing **reference** → `passed=True, skipped=True, overall_score is None`.
  - G1-variant (270–281) empty `character_configs` → `skipped=True`.
  - G2 (317–340) landscape-with-refs → `skipped=True` (NOT `passed=False/0.0`).
  - New: `skipped`/`None`-score invariant; missing video → FAIL.
- `tests/unit/test_phase_c_vision.py` (301–310, 358–367, 464–477, 481–494): missing
  reference → skip-marker; missing generated → fail-marker; dead QC fns → non-pass.
- `tests/unit/test_style_director.py` (G4 306–335): missing `photorealism_rules` → now
  present (back-filled); suffix **includes** `PHOTOREALISM_LITERAL`; warning emitted.

Whole-suite gate: `.venv/bin/python -m pytest tests/unit/ -q` stays green
(baseline 1491/3); `.venv/bin/python scripts/ci_smoke.py` → `OK`.

## 7. Implementation slices (separable; A is the foundation)

1. **A — schema** (`identity/types.py`: `Optional` score + `skipped` + `GENERATED_IMAGE_MISSING`).
2. **B — F1 core** (`validate_image`/`validate_video`, the two helpers, the score-reader audit).
3. **C — F1 vision fallback** (`phase_c_vision` `validate_identity_vision` + dead-code consistency + `_vision_llm_validate_image` mapping).
4. **D — F2 landscape skip** (`validate_video` short-circuit).
5. **E — F3 style merge** (`llm/style_director.py`).

Dependencies: B, C, D depend on A. E is independent (can land anytime). Each slice is one
commit; tests-first within each.

## 8. Out of scope

- The 5 **moderate** findings (sora `resolution` ignored; `phase_c_vision` face-swap silent
  `None`; hardcoded `0.7` vision threshold; `style_director` web-research fires regardless
  of `use_web_research`; `ltx_native` `"720p"`→1080p and `HTTPError`→no-fallback) and the
  minors — separate follow-up cycle.
- No change to `passed`'s boolean type, the threshold tables, or the retry-loop structure.
- No new validator entry points or call-site signature changes.

## 9. Acceptance criteria

1. `IdentityValidationResult` has `skipped: bool` and `overall_score: Optional[float]`;
   `FailureReason.GENERATED_IMAGE_MISSING` exists; the §3 invariant holds.
2. Missing **generated** image/video → `passed=False` + `GENERATED_IMAGE_MISSING`; missing
   **reference** / no-config / all-refs-fail → `passed=True, skipped=True, score=None`.
3. Landscape-with-refs → `skipped=True` (no spurious fail).
4. Vision fallback (`validate_identity_vision`) follows the same ref→skip / gen→fail policy;
   dead QC fns no longer pass on missing file.
5. `generate_style_rules` always returns a dict containing `photorealism_rules`; a missing
   key logs a warning; the prompt suffix always carries the photorealism formula.
6. No production read of `overall_score` crashes or mis-stores on a skipped (`None`) result —
   in particular the three `float()`/compare sites (`face_validator_gate.py:142`,
   `performance/identity_gate.py:72`, `llm/chief_director.py:360`) are guarded (§5b); the gate
   sites (§5a) behave correctly (skip→proceed, missing-output→retry).
7. All `# CANDIDATE BUG` tests updated to assert the fixed behavior; suite green (≥1491
   pass / 3 skip / 0 fail); `ci_smoke` `OK`.
