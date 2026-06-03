# Part-3 Deferred Moderate/Minor Fixes — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (subagents available) to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. **Spec:** `docs/superpowers/specs/2026-06-03-part3-moderate-minor-fixes-design.md` (read it first — it carries the grounded adjudication + the G1 design decision).

**Goal:** Clear the entire Part-3 deferred ledger (13 findings) — 6 real-bug fixes (2 capability wins), 3 cleanups, 3 document-only, 1 leave — in one design-first TDD cycle, ending with zero `# CANDIDATE BUG` markers and a green suite.

**Architecture:** One implementer subagent per component (5 Lane-B tasks + 1 Lane-A annotation task), each a self-contained TDD cycle (flip the characterization-test marker → watch fail → minimal fix → watch pass → run module → commit). Components are independent; tasks are dispatched sequentially (one implementer at a time) with spec + code-quality review per task.

**Tech Stack:** Python 3, pytest (offline, all external deps mocked), `.venv/bin/python -m pytest`. Frozen `config/settings.py` (use `dataclasses.replace` + `monkeypatch.setattr`, never field monkeypatch).

---

## Conventions every implementer MUST follow (per CLAUDE.md)

1. **Plan-vs-source rule:** every line number below is **approximate (as-of `26d9b1e`)**. Before editing, `grep -n <symbol> <file>` to find the real location; match the file's existing style. If a landmark doesn't match (symbol renamed, structure differs), **report the divergence in your status before implementing** — do not force the sketch.
2. **TDD, non-negotiable:** flip/write the test FIRST, run it, watch it FAIL against current code (for FIX items), then implement the minimal change, watch it PASS. **Never weaken a test to make it pass.** A test that won't fail-then-pass means you misunderstood the code — stop and report.
3. **Marker-resolution:** FIX → the `# CANDIDATE BUG` marker's test flips to assert the *fixed* behavior and the marker comment is deleted/rewritten to describe the passing assertion. DOCUMENT/LEAVE → behavior is unchanged; rewrite the marker comment from `# CANDIDATE BUG (...)` to `# DOCUMENTED-INTENTIONAL: <reason>` (or `# DEAD-CODE (intentional): <reason>`) so the test still passes and `grep -rn "CANDIDATE BUG" tests/unit/` no longer matches it.
4. **`sys.modules` stub shadowing:** `test_sora_native.py` / `test_ltx_native.py` inject empty `ModuleType` stubs; a test importing the REAL module needs `sys.modules.pop("<mod>", None)` first (follow the file's existing pattern).
5. **Commit discipline (shared index / D-a):** stage ONLY your files (`git add <explicit paths>`; never `git add -A`), then `git commit -m "..." -- <explicit paths>`. One commit per task. Run `.venv/bin/python scripts/ci_smoke.py` and `.venv/bin/python scripts/check_doc_claims.py` BEFORE committing (anchor drift → ci_smoke exit 1; `--fix` then re-commit in the same pathspec if needed).
6. **Verification per task:** `.venv/bin/python -m pytest tests/unit/<module test> -v` (your component, all green) AND `.venv/bin/python -m pytest tests/unit/ -q` (full suite, no regression vs baseline **1499 passed / 3 skipped / 0 failed**).
7. **Report format:** Status (DONE / DONE_WITH_CONCERNS / BLOCKED), blast-radius findings (grep callers), files changed, verification output, commit SHA (from `git commit` stdout), self-review.
8. **Boilerplate docstring lines (done-signal trap):** four test modules carry a `# CANDIDATE BUG tags.` phrase in their **module docstring** (`test_sora_native.py:4`, `test_ltx_native.py:4`, `test_phase_c_vision.py:8`, `test_identity_validator.py:7`) — these ALSO match the done-signal grep. When your task touches one of these files, reword that docstring phrase (e.g. `# DOCUMENTED-INTENTIONAL tags.`) or drop it, so `grep -rn "CANDIDATE BUG" tests/unit/` truly returns empty. Zero extra cost — you're editing the file anyway.

---

## Chunk 1: Capability fixes + sora / ltx / style

### Task 1: `sora_native` — unlock 1080p + dead-code cleanup + convention doc

**Files:**
- Modify: `sora_native.py` (RESOLUTION_MAP + wire `size`/`img.resize`; delete dead `download_url` loop + `urllib` import; docstring note)
- Modify: `phase_c_ffmpeg.py` (~`:249-262`, the Sora call — pass `resolution="1080p"`)
- Test: `tests/unit/test_sora_native.py`

**Context:** `generate_video(resolution="1080p", ...)` accepts the param (~`:49`) but hardcodes `size="1280x720"` (~`:116`) and `img.resize((1280,720))` (~`:97`). Sora-2 API `size` accepts `1920x1080`. Caller never passes `resolution=`. Also a dead `download_url` attr-sniff loop (~`:133-142`) + `import urllib.request` (~`:14`) used only by it (real download is `client.videos.download_content(video.id)` ~`:146`). G(sora)1 (empty key → `EnvironmentError` ~`:25-29`) is **intentional** (matches `veo_native`; caller catches it) → document only.

- [ ] **Step 1 (G(sora)2 — write failing test):** flip the `# CANDIDATE BUG (G(sora)2)` test (~`:180`). Assert `size` honors `resolution`; parametrize:

```python
@pytest.mark.parametrize("resolution,expected_size", [
    ("1080p", "1920x1080"),
    ("720p", "1280x720"),
    ("480p", "480x270"),
])
def test_resolution_maps_to_size(resolution, expected_size):
    # ... existing harness that captures the size= kwarg passed to create_and_poll ...
    assert actual_size == expected_size
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/unit/test_sora_native.py -k resolution -v` → expect FAIL (1080p got "1280x720").
- [ ] **Step 3 (implement):** add a module-level `RESOLUTION_MAP = {"480p": "480x270", "720p": "1280x720", "1080p": "1920x1080"}` (mirror `ltx_native.RESOLUTION_MAP` shape). In `generate_video`, derive `size = RESOLUTION_MAP.get(resolution, "1280x720")` and use it for BOTH the `size=` kwarg and the `img.resize(...)` (parse the WxH). Verify against actual source.
- [ ] **Step 4:** Run the same test → expect PASS. Run `.venv/bin/python -m pytest tests/unit/test_sora_native.py -v` → all green.
- [ ] **Step 5 (caller):** in `phase_c_ffmpeg.py` Sora call (~`:249`), pass `resolution="1080p"`. `grep -n "resolution\|1280x720\|sora" phase_c_ffmpeg.py` to confirm the exact call. (Capability-max default; no shot-tier branching this cycle.)
- [ ] **Step 6 (dead-code cleanup):** delete the `download_url` loop (~`:133-142`) and `import urllib.request` (~`:14`) — first `grep -n urllib sora_native.py` to confirm NO other use. No behavior change; existing tests stay green.
- [ ] **Step 7 (G(sora)1 document):** rewrite the marker (~`:95`) to `# DOCUMENTED-INTENTIONAL: raise-on-init matches veo_native; caller (phase_c_ffmpeg) catches -> try_next_api`. Add a one-line class-docstring note. Behavior unchanged; the test (asserting `EnvironmentError` raised) stays green.
- [ ] **Step 8:** `.venv/bin/python -m pytest tests/unit/test_sora_native.py -v` (green) + `.venv/bin/python -m pytest tests/unit/ -q` (1499→+subtests, 0 fail) + `ci_smoke.py` + `check_doc_claims.py`.
- [ ] **Step 9 (commit):**

```bash
git add sora_native.py phase_c_ffmpeg.py tests/unit/test_sora_native.py
git commit -m "fix(sora): honor resolution param (unlock 1080p) + drop dead download_url; doc empty-key convention" -- sora_native.py phase_c_ffmpeg.py tests/unit/test_sora_native.py
```

---

### Task 2: `ltx_native` — 5xx → FAL fallback + local-error guard + resolution doc

**Files:**
- Modify: `ltx_native.py` (`_native_generate` except block ~`:262-271`)
- Test: `tests/unit/test_ltx_native.py`

**Context:** `_native_generate` catches `urllib.request.HTTPError` WITHOUT FAL fallback (→ implicit `None`), but a generic `Exception` DOES fall back to FAL — so transient 5xx silently drops the shot, and a local bug wrongly burns a FAL call. Live path: `phase_c_ffmpeg.py:~318 → generate_video → _native_generate` (caller handles `None` via `try_next_api`). DORMANT `_native_transition`/`_native_request`/`_download_native_result` — DO NOT touch. G(ltx)3 (`RESOLUTION_MAP["720p"]`→1080p, ~`:36`) is intentional (LTX has no true 720p; zero live 720p callers) → document only.

- [ ] **Step 1 (write failing tests):** flip both markers. `:~317` → a 5xx `HTTPError` triggers the FAL fallback:

```python
def test_http_5xx_falls_back_to_fal(monkeypatch, tmp_path):
    monkeypatch.setattr(ltx_native, "FAL_AVAILABLE", True)
    api = _make_api(ltx_key="ltx-key", fal_key="fal-key")
    # make the native request raise HTTPError(code=503); stub _fal_generate to a sentinel
    # assert _fal_generate was called AND its result returned (not None)
```
`:~359` → a local `OSError` does NOT fall back (returns `None`, `_fal_generate` NOT called).

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/unit/test_ltx_native.py -k "fal or fallback or http" -v` → expect FAIL (5xx returns None; OSError falls back).
- [ ] **Step 3 (implement, Option A):** restructure the except in `_native_generate` (verify exact text first):

```python
except urllib.request.HTTPError as e:
    body = e.read().decode("utf-8", "replace")[:500] if hasattr(e, "read") else str(e)
    if getattr(e, "code", 0) >= 500 and self.fal_key and FAL_AVAILABLE:
        print(f"[LTX] Native {e.code}; falling back to FAL")
        return self._fal_generate(...)   # match the existing _fal_generate call signature
    print(f"[LTX] Native failed ({getattr(e,'code','?')}): {body}")
    return None
except (OSError, json.JSONDecodeError) as e:   # local errors — no fallback (don't mask bugs)
    print(f"[LTX] Local error (no fallback): {e}")
    return None
except Exception as e:
    print(f"[LTX] Native generation failed: {e}")
    if self.fal_key and FAL_AVAILABLE:
        return self._fal_generate(...)
    return None
```
Ensure `json` is imported (it is used elsewhere — confirm). Keep `FileNotFoundError` covered (subclass of `OSError`).

- [ ] **Step 4:** Run the tests → PASS. Run `.venv/bin/python -m pytest tests/unit/test_ltx_native.py -v` → all green.
- [ ] **Step 5 (G(ltx)3 document):** rewrite the marker (~`:123`/`:152`) to `# DOCUMENTED-INTENTIONAL: LTX has no true 720p; "720p" upgraded to 1080p (capability-positive); zero live 720p callers`. Behavior unchanged.
- [ ] **Step 6:** module test green + full suite (0 fail) + `ci_smoke` + `check_doc_claims`.
- [ ] **Step 7 (commit):**

```bash
git add ltx_native.py tests/unit/test_ltx_native.py
git commit -m "fix(ltx): native 5xx -> FAL fallback; guard local errors from over-broad fallback; doc 720p upgrade" -- ltx_native.py tests/unit/test_ltx_native.py
```

---

### Task 3: `style_director` — honor `use_web_research` + OpenAI client in try

**Files:**
- Modify: `llm/style_director.py` (research gating ~`:46-54`; `use_web_research` default ~`:19`; OpenAI client ~`:42` → inside `try` ~`:92`)
- Modify: `web_server.py` (~`:1427`, `.get("use_web_research", ...)` default → `True`)
- Test: `tests/unit/test_style_director.py`

**Context (G1 — DECISION (c) from spec §3.3, user-approved):** the primary `research_cinematography` call (~`:46-54`) is unconditional; the secondary `_research_aesthetic` (~`:57`) IS gated by `use_web_research` (default `False`). Resolution: **gate BOTH consistently behind `use_web_research`, and flip its default to `True`** — research stays on by default (capability preserved), the contract bug is fixed, the operator knob works. **G3:** `client = openai.OpenAI(api_key=...)` (~`:42`) is outside the `try` (~`:92`) whose `except` returns `_default_style_rules` → construction failure isn't caught.

- [ ] **Step 1 (G1 — write failing test):** flip the marker (~`:275`/`:298`):

```python
def test_research_honors_use_web_research_false():
    # use_web_research=False -> research_cinematography NOT called
    assert mock_rc.call_count == 0

def test_research_default_is_true():
    # generate_style_rules signature default for use_web_research is True
    import inspect
    assert inspect.signature(generate_style_rules).parameters["use_web_research"].default is True
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/unit/test_style_director.py -k web_research -v` → FAIL (called unconditionally; default False).
- [ ] **Step 3 (implement G1):** wrap the `research_cinematography` block in `if use_web_research:`; flip the signature default to `True`; in `web_server.py` change the body read to `.get("use_web_research", True)`. `grep -n use_web_research llm/style_director.py web_server.py` to confirm both sites.
- [ ] **Step 4:** tests → PASS.
- [ ] **Step 5 (G3 — write failing test):** flip the marker (~`:343`/`:367`):

```python
def test_openai_construction_failure_falls_back_to_defaults(monkeypatch):
    # patch sora? no — patch openai.OpenAI to raise; assert result == _default_style_rules(...) shape
    monkeypatch.setattr("llm.style_director.openai.OpenAI", _raise)
    rules = generate_style_rules(...)   # with a valid key so it gets past the key guard
    assert rules == _default_style_rules(...)   # or assert the default-rules sentinel
```

- [ ] **Step 6:** Run → FAIL (exception propagates, no fallback).
- [ ] **Step 7 (implement G3):** move `client = openai.OpenAI(api_key=api_key)` from ~`:42` to inside the `try` at ~`:92` (the one whose `except` returns `_default_style_rules`). The key-guard early-return (~`:39`) stays. Verify the try at `:92` is the right one.
- [ ] **Step 8:** Run → PASS. Full module green.
- [ ] **Step 9:** full suite (0 fail) + `ci_smoke` + `check_doc_claims`.
- [ ] **Step 10 (commit):**

```bash
git add llm/style_director.py web_server.py tests/unit/test_style_director.py
git commit -m "fix(style): gate both research calls on use_web_research (default True); construct OpenAI client inside try for default-rules fallback" -- llm/style_director.py web_server.py tests/unit/test_style_director.py
```

---

## Chunk 2: identity / vision / chief_director

### Task 4: `identity/validator` — threshold=0.0 override + total_frames==0 metadata + dead-enum note

**Files:**
- Modify: `identity/validator.py` (`validate_video` threshold ~`:155`/`:166-167`; `_vision_llm_validate_video` total_frames==0 ~`:822-828` + the parallel site ~`:194-200`)
- Test: `tests/unit/test_identity_validator.py`

**Context (G4):** `th = threshold or get_threshold_for_shot(...)` (~`:155`) + `if threshold is None: threshold = ...` (~`:166`) make `th` and `threshold` diverge when `threshold=0.0` (0.0 falsy); the gate `matched = similarity >= threshold` (~`:506`) then passes everything. Latent (no prod caller passes 0.0; `continuity_engine.py:~616` passes through non-zero). **validator:822 nit:** `total_frames==0` returns an inline `passed=False/0.0` with no `failure_reason`, unlike `_missing_output_result` (~`:714`). **G3(identity):** `MULTIPLE_FACES_AMBIGUOUS` (`identity/types.py`) never returned by `_classify_failure` — genuinely dead → leave + note.

- [ ] **Step 1 (G4 — write failing test):** flip the marker (~`:876`):

```python
def test_threshold_zero_is_honored_as_real_override():
    # threshold=0.0 should be used as the actual gate (so a real override is possible),
    # NOT diverge from th. Assert threshold_used == 0.0 in the result AND that a
    # below-shot-threshold similarity passes ONLY because 0.0 was explicitly chosen.
    # (Pin: single variable, no th/threshold split.)
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/unit/test_identity_validator.py -k threshold -v` → FAIL against current divergence.
- [ ] **Step 3 (implement G4, Option A):** replace `th = threshold or get_threshold_for_shot(...)` with `threshold = threshold if threshold is not None else get_threshold_for_shot(...)`; delete the `:166-167` re-assignment; replace remaining `th` uses with `threshold`. `grep -n "\bth\b" identity/validator.py` to catch every `th` use in scope. Does NOT touch `overall_score: Optional[float]`.
- [ ] **Step 4:** Run → PASS. Full module green.
- [ ] **Step 5 (validator:822 nit):** route BOTH `total_frames==0` sites (~`:822` and the `validate_video` parallel ~`:194`) through `_missing_output_result(shot_type, threshold)`. Add/adjust a test asserting the zero-frame result carries `failure_reason == FailureReason.GENERATED_IMAGE_MISSING.value`. `passed=False` unchanged.
- [ ] **Step 6 (G3 leave):** the `CANDIDATE BUG (G3)` marker at ~`:638` is **inside an f-string assertion message** (`f"CANDIDATE BUG (G3): ..."`), not a comment — so change the **string text** itself to no longer contain "CANDIDATE BUG" (e.g. `f"DEAD-ENUM (intentional, G3): MULTIPLE_FACES_AMBIGUOUS reserved in enum; no _classify_failure path returns it — {args}"`). Behavior unchanged (it's an assert-message string); the test still passes.
- [ ] **Step 7:** module green + full suite (0 fail) + `ci_smoke` + `check_doc_claims`.
- [ ] **Step 8 (commit):**

```bash
git add identity/validator.py tests/unit/test_identity_validator.py
git commit -m "fix(identity): honor threshold=0.0 as real override (no th divergence); route zero-frame result via _missing_output_result; note dead enum" -- identity/validator.py tests/unit/test_identity_validator.py
```

---

### Task 5: `phase_c_vision` + `controller` — surface FaceFusion skip + advisory-threshold doc

**Files:**
- Modify: `cinema/shots/controller.py` (~`:1939-1941`, the operator `face_swap` action — surface a reason when `result is None`)
- Modify: `phase_c_vision.py` (comment on `validate_identity_vision` `match` key)
- Test: `tests/unit/test_phase_c_vision.py` (function-level pins) + the controller test home (see note)

**Context (G2):** `face_swap_video_frames` (~`:52-104`) is a best-effort cascade; rc0+missing-output → `return None` (intentional skip). The ONLY caller is the manual operator action `controller.py:~1939`: `if result: variant["path"] = result` → on `None` the action silently no-ops and reports success. Fix is **caller-side**: surface a reason. **G5 (survey-corrected):** `validate_identity_vision`'s hardcoded-`0.7` `match` key is **advisory** — `IdentityValidator` re-thresholds on the prod path (`validator.py:~754`); not a live gate. Document; do NOT remove the key.

- [ ] **Step 1 (G2 — re-pin the function test):** the function test (~`:248`/`:259`) keeps asserting `face_swap_video_frames(...) is None` on rc0+missing — rewrite its marker to `# DOCUMENTED-INTENTIONAL: cascade skip (fal->facefusion->None); caller surfaces the reason`. (Behavior of the function is correct.)
- [ ] **Step 2 (G2 — write the failing caller test):** add a test that the operator `face_swap` action surfaces a reason when the swap can't apply. The caller is the `apply_correction` method in `cinema/shots/controller.py` (~`:1939`). **Test home:** `test_cross_controller.py` exists but does NOT cover `apply_correction`, and building a `ShotController` via the `CinemaPipelineHost` harness is ~200 LOC of setup — so **prefer adding the focused test to `tests/unit/test_phase_c_vision.py`** (the face-swap function tests already live there), patching `face_swap_video_frames` → `None` and asserting the action's returned dict carries a warning/reason. **Report the chosen home.** If even the lightweight controller construction proves impractical, BLOCK and report rather than over-mock.
- [ ] **Step 3:** Run the caller test → FAIL (current code silently no-ops, no reason surfaced).
- [ ] **Step 4 (implement G2):** at `controller.py:~1939`, when `result is None`, attach an explicit reason (e.g. `variant["warning"] = "face_swap could not be applied (no swapper succeeded)"`, or include it in the action's return) without changing the cascade. Match the surrounding return-shape convention (look at how the `lip_sync` branch ~`:1959` and other operator actions report partial outcomes).
- [ ] **Step 5:** Run → PASS.
- [ ] **Step 6 (G5 document):** add a comment to `validate_identity_vision` ("`match` is advisory (hardcoded 0.7); production callers re-threshold via IdentityValidator") and rewrite the markers (~`:516`/`:529`/`:544`) to `# DOCUMENTED-INTENTIONAL: advisory match key; prod gate re-thresholds (validator re-computes matched)`. Behavior unchanged.
- [ ] **Step 7:** module green + full suite (0 fail) + `ci_smoke` + `check_doc_claims`.
- [ ] **Step 8 (commit):**

```bash
git add cinema/shots/controller.py phase_c_vision.py tests/unit/test_phase_c_vision.py
git commit -m "fix(vision): surface reason when operator face_swap cannot apply; doc advisory vision-threshold match key" -- cinema/shots/controller.py phase_c_vision.py tests/unit/test_phase_c_vision.py
```

---

### Task 6: `chief_director` annotation (Lane A — verify-first)

**Files:**
- Modify: `llm/chief_director.py` (~`:341`)

**Context:** Director Lane V nit — stale `identity_score: float = 0.0` annotation; runtime can be `Optional[float]` post-Part-3. **Unverified by adjudication** → confirm before editing.

- [ ] **Step 1 (verify):** `grep -n "identity_score" llm/chief_director.py`. Confirm a `identity_score: float` annotation exists at ~`:341` AND that the value can be `None` at runtime (trace the assignment). If it can't be `None`, **report and skip** (the nit is moot).
- [ ] **Step 2 (implement):** change the annotation to `Optional[float]` (ensure `Optional` is imported — `grep -n "from typing import" llm/chief_director.py`). Annotation-only; no runtime/behavior change, no test needed.
- [ ] **Step 3:** `.venv/bin/python -m pytest tests/unit/ -q` (0 fail) + `ci_smoke` + `check_doc_claims`.
- [ ] **Step 4 (commit):**

```bash
git add llm/chief_director.py
git commit -m "chore(chief-director): widen identity_score annotation to Optional[float] (post-Part-3)" -- llm/chief_director.py
```

---

## Done-signal (after all 6 tasks)

- [ ] `grep -rn "CANDIDATE BUG" tests/unit/` → **empty** (every marker resolved: FIX flipped, DOCUMENT/LEAVE re-worded).
- [ ] `.venv/bin/python -m pytest tests/unit/ -q` → **green**, ≥ baseline 1499 passed / 3 skipped / 0 failed (+ new subtests), 0 regressions.
- [ ] `.venv/bin/python scripts/ci_smoke.py` → `OK`; `.venv/bin/python scripts/check_doc_claims.py` → no drift.
- [ ] Final cross-cutting review (BASE = `26d9b1e`, HEAD = last task commit) then `superpowers:finishing-a-development-branch`.

## Out of scope (do NOT touch)
DORMANT LTX levers; `research_cinematography` callers other than `style_director`; removing the `match` key or `MULTIPLE_FACES_AMBIGUOUS` enum; the LTX `"720p"` default-arg rename; Part 4 (UI) / Part 5 B-C; live wired-E2E.
