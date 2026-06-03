# Part-3 Quality-Gate Fixes Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the identity/quality gates from silently passing (or wrongly failing) when they can't actually validate — by adding an honest SKIP state, failing real missing-output, fixing landscape, and guaranteeing the photorealism formula is always injected.

**Architecture:** One schema change to `IdentityValidationResult` (`overall_score → Optional[float]`, add `skipped: bool`, add `FailureReason.GENERATED_IMAGE_MISSING`) underpins the validator changes. Missing *generated* output → FAIL; genuinely-nothing-to-compare (missing reference, landscape, no character) → SKIP (`passed=True, skipped=True, overall_score=None`); the 5 gate sites keep gating on `.passed` unchanged, and the score-reader sites are guarded for `None`. `style_director` merges LLM output over defaults so required keys can't vanish. Each task keeps the unit suite green (`1491/3` baseline) and `ci_smoke` `OK`.

**Tech Stack:** Python 3.13, pytest, `.venv/bin/python`. Spec: `docs/superpowers/specs/2026-06-03-part3-quality-gate-fixes-design.md`.

**Slice→task mapping (the plan refines the spec's slices for clean commits + a green-per-commit order):** spec slice A → Task 1; the spec's "score-reader audit" (part of slice B) is pulled *forward* into Task 2 (guards land before skip exists); spec slice B `validate_image` → Task 3; spec slice B `validate_video` + spec slice D landscape → Task 4 (one task owns `validate_video`); spec slice C vision → Task 5; spec slice E style → Task 6; final verification → Task 7.

**Standing instruction to every implementer (CLAUDE.md):** before editing a symbol, `grep -rn 'symbol' --include='*.py' .` and Read the call sites; after edits `git diff --stat`; commit with **explicit pathspec** (`git commit -- <paths>`, never `git add -A` — the working tree has an intentional uncommitted SUPIR bake + scratch that must stay uncommitted). The spec's file:line refs are approximate — where the plan's value matches the source, use it; where they differ, use the source and report the divergence. Run `.venv/bin/python scripts/ci_smoke.py` before each commit (line-shifting edits can drift doc anchors → `def_drift`; if so, `.venv/bin/python scripts/check_doc_claims.py --fix`, confirm `OK`, include the anchor repair in the same commit's pathspec).

---

## Chunk 1: Schema + defensive score-reader guards

### Task 1: Schema change — `IdentityValidationResult` + `FailureReason`

**Files:**
- Modify: `identity/types.py` (FailureReason enum ~19-28; IdentityValidationResult ~59-72)
- Test: `tests/unit/test_identity_validator.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_identity_validator.py`; match the file's existing imports — `from identity.types import IdentityValidationResult, FailureReason`)

```python
def test_skipped_result_schema():
    r = IdentityValidationResult(
        passed=True, overall_score=None, character_results={},
        frames_sampled=0, video_duration_seconds=0.0,
        shot_type="medium", threshold_used=0.7, skipped=True,
    )
    assert r.skipped is True
    assert r.overall_score is None
    assert r.passed is True

def test_skipped_defaults_false():
    r = IdentityValidationResult(
        passed=True, overall_score=0.8, character_results={},
        frames_sampled=1, video_duration_seconds=0.0,
        shot_type="medium", threshold_used=0.7,
    )
    assert r.skipped is False
    assert r.overall_score == 0.8

def test_generated_image_missing_reason_exists():
    assert FailureReason.GENERATED_IMAGE_MISSING.value == "generated_image_missing"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_identity_validator.py::test_skipped_result_schema tests/unit/test_identity_validator.py::test_generated_image_missing_reason_exists -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'skipped'` and `AttributeError: GENERATED_IMAGE_MISSING`.

- [ ] **Step 3: Implement the schema change** (`identity/types.py`)

In `FailureReason` (after `PASSED = "passed"`):
```python
    GENERATED_IMAGE_MISSING = "generated_image_missing"
```
In `IdentityValidationResult`: change `overall_score: float` → `overall_score: Optional[float]`, and add a `skipped` field **after** `metadata` (both have defaults — ordering stays valid):
```python
    metadata: Dict = field(default_factory=dict)
    skipped: bool = False
```
(`Optional` is already imported at line 15.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_identity_validator.py -q`
Expected: PASS (no regressions in the file).

- [ ] **Step 5: Full suite + smoke**

Run: `.venv/bin/python scripts/ci_smoke.py && .venv/bin/python -m pytest tests/unit/ -q`
Expected: `OK`; `1494 passed / 3 skipped` (1491 + 3 new).

- [ ] **Step 6: Commit**

```bash
.venv/bin/python scripts/ci_smoke.py   # confirm OK first
git commit -- identity/types.py tests/unit/test_identity_validator.py \
  -m "feat(identity): add skipped state + GENERATED_IMAGE_MISSING (Part-3 schema)

overall_score -> Optional[float]; add skipped:bool (default False); add
FailureReason.GENERATED_IMAGE_MISSING. Invariant: skipped => passed=True &
score=None. Foundation for Part-3 F1/F2. Spec: docs/superpowers/specs/
2026-06-03-part3-quality-gate-fixes-design.md.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Defensive score-reader guards (land before skip exists)

Guard every production read of `.overall_score` for `None` **now**, so when Tasks 3-4 start returning `None` scores the suite stays green. Per spec §5b.

**Files:**
- Modify: `face_validator_gate.py:142`, `performance/identity_gate.py:72`, `llm/chief_director.py:358-365`, `cinema/shots/controller.py:1041` (and review `:656`, `:1816`)
- Test: `tests/unit/test_face_validator_gate.py` (or the nearest existing test for each; create a small new test if none)

- [ ] **Step 1: Write failing guard tests.** For `face_validator_gate` and `performance/identity_gate`, mock `validate_image`/the validator to return a skip result (`IdentityValidationResult(passed=True, overall_score=None, ..., skipped=True)`) and assert the scorer returns `None` (not a crash). For `chief_director.evaluate*`, pass an `identity_result` with `overall_score=None` and assert it does not raise and treats identity as non-blocking. Example shape (adapt imports/fixtures to each file's existing pattern — Read the test file first):

```python
def test_arcface_score_returns_none_on_skipped(monkeypatch):
    skip = IdentityValidationResult(passed=True, overall_score=None,
        character_results={}, frames_sampled=0, video_duration_seconds=0.0,
        shot_type="medium", threshold_used=0.7, skipped=True)
    # monkeypatch the module's validator so validate_image returns `skip`
    ...
    assert _arcface_score(gen, ref) is None
```

- [ ] **Step 2: Run to verify they fail** (TypeError on `float(None)` / `None >= float`).

Run: `.venv/bin/python -m pytest <new tests> -v` → Expected: FAIL.

- [ ] **Step 3: Implement the guards.**

`face_validator_gate.py` (~141, inside the `try`, before `return float(...)`):
```python
        result = validator.validate_image(image_path, reference_path, threshold=threshold)
        if result.overall_score is None:        # skipped: no comparable face
            return None
        return float(result.overall_score)
```
`performance/identity_gate.py` (~71, same pattern):
```python
        result = v.validate_image(frame_path, anchor_path, threshold=threshold)
        if result.overall_score is None:        # skipped: no comparable face
            return None
        return float(result.overall_score)
```
`llm/chief_director.py` (~360-365): after the `if identity_result is not None: identity_score = identity_result.overall_score ... else: threshold = 0.70` block, replace the bare compare:
```python
        # A skipped identity result has overall_score=None (couldn't be checked):
        # treat as non-blocking — don't drive an identity mutation off a non-score.
        if identity_score is None:
            identity_passed = True
        else:
            identity_passed = identity_score >= threshold
```
`cinema/shots/controller.py:1041`:
```python
            identity_score = (vid_result.overall_score
                              if hasattr(vid_result, "overall_score") and vid_result.overall_score is not None
                              else 0.0)
```
`cinema/shots/controller.py:656` and `:1816` store `id_result.overall_score` into a metadata/scores dict — storing `None` is acceptable (means "not scored"). **Grep first** (`grep -rn 'identity_score\|scores"\]\["identity' cinema/ web_server.py`) for any consumer that formats/compares those values as floats; if found, guard it. Otherwise leave + add a `# None on skip = not scored` comment.

- [ ] **Step 4: Run guard tests to verify they pass.** Expected: PASS.

- [ ] **Step 5: Full suite + smoke.** `.venv/bin/python scripts/ci_smoke.py && .venv/bin/python -m pytest tests/unit/ -q` → Expected: `OK`; suite green (still no skip results in production yet, so no behavior change).

- [ ] **Step 6: Commit.** Use an **explicit pathspec naming every file you touched** (never `git add -A`):
```bash
git commit -- face_validator_gate.py performance/identity_gate.py \
  llm/chief_director.py cinema/shots/controller.py <the test file(s) you added> \
  -m "fix(identity): guard overall_score readers for None (Part-3 pre-skip)"
```
Commit message body:
```
fix(identity): guard overall_score readers for None (Part-3 pre-skip)

Defensive None-handling before the validator starts returning skip results
(score=None). The two ArcFace scorers return None (their documented
"no face" value); chief_director treats a None score as non-blocking;
controller:1041 falls back to 0.0. Keeps the suite green per commit. Spec §5b.
```

---

## Chunk 2: F1 validate_image + validate_video/landscape

### Task 3: F1 — `validate_image` split + skip helpers

**Files:**
- Modify: `identity/validator.py` (`_no_file_result` ~696; `validate_image` ~82-97)
- Test: `tests/unit/test_identity_validator.py`

- [ ] **Step 1: Add the two helpers** (`identity/validator.py`, replacing `_no_file_result` — first `grep -rn '_no_file_result' --include='*.py' .` to find ALL callers; the 4 in `validate_image`/`validate_video` get re-pointed in Tasks 3-4):

```python
    @staticmethod
    def _skipped_result(shot_type: str, threshold: float) -> IdentityValidationResult:
        """SKIP: identity genuinely cannot be checked (missing reference, no
        character configured, no face expected). Shot proceeds; not a failure."""
        return IdentityValidationResult(
            passed=True, overall_score=None, character_results={},
            frames_sampled=0, video_duration_seconds=0.0,
            shot_type=shot_type, threshold_used=threshold, skipped=True,
        )

    @staticmethod
    def _missing_output_result(shot_type: str, threshold: float) -> IdentityValidationResult:
        """FAIL: the generated output (image/video) is missing — a real
        generation/IO failure that must surface, not silently pass."""
        return IdentityValidationResult(
            passed=False, overall_score=0.0, character_results={},
            frames_sampled=0, video_duration_seconds=0.0,
            shot_type=shot_type, threshold_used=threshold, skipped=False,
            metadata={"failure_reason": FailureReason.GENERATED_IMAGE_MISSING.value},
        )
```

- [ ] **Step 2: Write/flip the failing tests** in `tests/unit/test_identity_validator.py`. The existing `# CANDIDATE BUG (G1)` test `test_missing_image_returns_passed_true_score_1` (~95-107) asserts the OLD quirk — **replace** it with two tests asserting the fix (reuse its fixture pattern — Read ~90-110 for how it builds paths):

```python
def test_missing_generated_image_fails():
    # FIXED (was CANDIDATE BUG G1): missing GENERATED image -> FAIL
    v = _make_validator()  # match existing fixture
    result = v.validate_image("/nonexistent/gen.png", <existing_ref_path>, shot_type="medium")
    assert result.passed is False
    assert result.skipped is False
    assert result.metadata.get("failure_reason") == "generated_image_missing"

def test_missing_reference_skips():
    # FIXED: missing REFERENCE -> SKIP (cannot compare; not a failure)
    v = _make_validator()
    result = v.validate_image(<existing_gen_path>, "/nonexistent/ref.png", shot_type="medium")
    assert result.passed is True
    assert result.skipped is True
    assert result.overall_score is None
```

- [ ] **Step 3: Run to verify they fail.** Expected: FAIL (current code returns `passed=True, 1.0` for both).

- [ ] **Step 4: Implement the split** (`identity/validator.py` ~82-83). Replace the combined check:
```python
        if not os.path.exists(image_path):
            return self._missing_output_result(shot_type, threshold or 0.70)
        if not os.path.exists(reference_path):
            return self._skipped_result(shot_type, threshold or 0.70)
```
And the no-embedding return (~97): `return self._skipped_result(shot_type, threshold)`.

- [ ] **Step 5: Run to verify pass.** Expected: PASS.

- [ ] **Step 6: Full suite + smoke + commit** (pathspec: `identity/validator.py tests/unit/test_identity_validator.py`).
```
fix(identity): validate_image missing-generated FAILs, missing-ref SKIPs (Part-3 F1)
```

---

### Task 4: F1 `validate_video` + F2 landscape skip

**Files:**
- Modify: `identity/validator.py` (`validate_video` ~150-240; the missing-video guard near the `cv2.VideoCapture` open ~182; the post-`_compute_sample_positions` empty-positions branch)
- Test: `tests/unit/test_identity_validator.py`

- [ ] **Step 1: Flip/add the failing tests.** (a) The empty-`character_configs` test `test_empty_configs_passes_silently` (class `TestValidateVideoEmptyCharacterConfigs`, ~271): assert `skipped is True` (was `overall_score == 1.0`). (b) The `# CANDIDATE BUG (G2)` test `test_landscape_zero_frames_sampled_fails_when_ref_exists` (~317-340): **rename/flip** to assert landscape-with-refs → `skipped is True`, `passed is True`, `overall_score is None` (was `passed=False, 0.0`). (c) New: missing video file → `passed is False`, `metadata["failure_reason"] == "generated_image_missing"`. (d) New: all-refs-fail-to-load → `skipped is True`.

- [ ] **Step 2: Run to verify they fail.** Expected: FAIL.

- [ ] **Step 3: Implement** (`identity/validator.py validate_video`). Read the whole method first. Changes:
  - Missing video guard (before `cv2.VideoCapture`, ~182): `if not os.path.exists(video_path): return self._missing_output_result(shot_type, threshold or get_threshold_for_shot(shot_type))`.
  - No `character_configs` (~155) → `return self._skipped_result(...)`.
  - All references fail to load / empty `ref_embeddings` (~179) → `return self._skipped_result(...)`.
  - **F2 landscape:** immediately after `positions = self._compute_sample_positions(...)` returns, add: `if not positions: return self._skipped_result(shot_type, threshold)` — BEFORE the per-character aggregation. Use `if not positions:` (the empty list), NOT a literal `shot_type == "landscape"`.

- [ ] **Step 4: Run to verify pass.** Expected: PASS.

- [ ] **Step 5: Full suite + smoke + commit** (`identity/validator.py tests/unit/test_identity_validator.py`).
```
fix(identity): validate_video skip no-ref/landscape, fail missing-video (Part-3 F1+F2)
```

---

## Chunk 3: Vision fallback + style + verification

### Task 5: F1 — vision fallback + dead QC code (`phase_c_vision.py`)

**Files:**
- Modify: `phase_c_vision.py` (`validate_identity_vision` ~260-265; `quality_control_image` ~112-114; `validate_shot_quality_vision` ~170-173)
- Modify: `identity/validator.py` (`_vision_llm_validate_image` ~724-771 — map the skip/missing marker)
- Test: `tests/unit/test_phase_c_vision.py`

- [ ] **Step 1: Flip the failing tests** in `tests/unit/test_phase_c_vision.py`. The four `# CANDIDATE BUG (G1)` tests: missing-reference (~464-477) → assert the skip marker; missing-generated (~481-494) → assert the fail marker; `quality_control_image` missing (~301-310) → assert `result is False`; `validate_shot_quality_vision` missing (~358-367) → assert `result["pass"] is False`.

- [ ] **Step 2: Run to verify they fail.** Expected: FAIL.

- [ ] **Step 3: Implement.**
  - `validate_identity_vision` (~260-265): missing **reference** → `return {"match": True, "skip": True, "confidence": None, "issues": [], "source": "default"}`; missing **generated** → `return {"match": False, "missing_generated": True, "confidence": 0.0, "issues": ["generated image missing"], "source": "default"}`.
  - `_vision_llm_validate_image` (`identity/validator.py` ~724-771): after it calls the vision fallback, map the marker → if `vision.get("skip")`: `return self._skipped_result(shot_type, threshold)`; if `vision.get("missing_generated")`: `return self._missing_output_result(shot_type, threshold)`. (Read the function to place the mapping right after the fallback call, before the normal `match→IdentityValidationResult` construction.)
  - Dead code (add `# Unreached in production (zero callers on main/feat); fixed for consistency.`): `quality_control_image` (~112) → `return False` on missing; `validate_shot_quality_vision` (~170) → `{"pass": False, "score": 0, "issues": ["image missing"], "suggestions": [], "source": "default"}` on missing.

- [ ] **Step 4: Run to verify pass.** Expected: PASS.

- [ ] **Step 5: Full suite + smoke + commit** (`phase_c_vision.py identity/validator.py tests/unit/test_phase_c_vision.py`).
```
fix(vision): validate_identity_vision ref->skip/gen->fail; dead QC fns no-pass on missing (Part-3 F1)
```

---

### Task 6: F3 — `style_director` merge defaults

**Files:**
- Modify: `llm/style_director.py` (after `rules = json.loads(raw)` ~112; confirm `_default_style_rules` signature ~122)
- Test: `tests/unit/test_style_director.py`

- [ ] **Step 1: Flip the failing test.** The `# CANDIDATE BUG (G4)` test `test_g4_missing_photorealism_rules_silently_omitted` (~306-335): flip the two asserts to `"photorealism_rules" in result` (back-filled) and `PHOTOREALISM_LITERAL in suffix`. Optionally assert a warning was printed (capture stdout).

- [ ] **Step 2: Run to verify it fails.** Expected: FAIL (key currently absent; literal currently missing).

- [ ] **Step 3: Implement** (`llm/style_director.py`, right after `rules = json.loads(raw)`; confirm `_default_style_rules`'s exact args by Reading ~122 and pass the matching local vars):

```python
        rules = json.loads(raw)
        defaults = _default_style_rules(mood, color_palette, music_mood)
        missing = [k for k in defaults if k not in rules]
        if missing:
            print(f"   ⚠️ style rules missing {missing} — back-filling from defaults")
        rules = {**defaults, **rules}   # LLM values win; absent keys back-filled
```

- [ ] **Step 4: Run to verify pass.** Expected: PASS.

- [ ] **Step 5: Full suite + smoke + commit** (`llm/style_director.py tests/unit/test_style_director.py`).
```
fix(style): merge LLM style rules over defaults so photorealism_rules can't vanish (Part-3 F3)
```

---

### Task 7: Final verification + acceptance check

**Files:** none (verification only).

- [ ] **Step 1: Whole suite.** `.venv/bin/python -m pytest tests/unit/ -q` → Expected: all green, count ≥ `1494 passed / 3 skipped / 0 failed` (1491 baseline + new tests; note exact final count).
- [ ] **Step 2: Smoke.** `.venv/bin/python scripts/ci_smoke.py` → Expected: `OK`.
- [ ] **Step 3: Anchors.** `.venv/bin/python scripts/check_doc_claims.py` → Expected: `OK` (no `def_drift`; if drift, `--fix` + commit the repair).
- [ ] **Step 4: Acceptance checklist** — verify each spec §9 criterion is met (grep the new behaviors); confirm no `# CANDIDATE BUG (G1/G2/G4)` marker still asserts the old quirk (`grep -rn 'CANDIDATE BUG' tests/unit/`), and that any remaining markers are the deferred moderates only.
- [ ] **Step 5:** Report final suite count + any deviations from the spec discovered during implementation.

---

## Out of scope (deferred — do NOT implement here)
The 5 moderate findings (sora `resolution`, face-swap silent `None`, hardcoded `0.7` vision threshold, web-research-fires-regardless, ltx `720p`/`HTTPError`-fallback) and the minors. Leave their `# CANDIDATE BUG` markers intact.
