# T6 — Remediation Advisory Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (subagents available) to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. **One implementer subagent per task, sequential, never parallel** (tasks share `cinema/shots/controller.py`). Two-stage review (spec + code-quality) per task per CLAUDE.md.

**Goal:** Surface a concrete remediation advisory (failure reason + suggested negative-prompt + PuLID nudge, with an opt-in LLM "deep diagnosis") on keyframe takes that fail their identity gate, wiring the two dormant levers `negative_prompts` + `evaluate_generation_quality` into the *existing* diagnose flow.

**Architecture:** Deterministic core (a pure builder used inline at generation + inside `diagnose_clip`) plus an opt-in LLM path on `diagnose_clip(deep=True)`. No new endpoint, no autonomous retry. Operator-assist only.

**Tech Stack:** Python 3 (Flask backend, `.venv/bin/python`), React/TS frontend (`web/`, no test runner — gate is `tsc --noEmit && npm run build`).

---

## Context & conventions (read before any task)

- **Spec (authoritative):** `docs/superpowers/specs/2026-06-06-t6-remediation-advisory-design.md`. Where this plan and the spec/source disagree, prefer the source; report the divergence.
- **Project conventions (CLAUDE.md):** before editing a symbol, `grep -rn 'symbolName' --include='*.py' .` for callers and read them; after edits `git diff --stat`. **Shared git tree** — director may be live; ALWAYS `git commit -- <pathspec>`, never `git add -A` / `commit -a`. Run `git log --oneline -1` immediately before each commit (Rule #7).
- **Tooling:** use `.venv/bin/python -m pytest ...` and `.venv/bin/python scripts/ci_smoke.py` (system `python3` lacks deps). Frontend: `cd web && npx tsc --noEmit && npm run build`. **Do NOT add a frontend test runner.**
- **Commit messages:** `<type>(<scope>): <subject>` + the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.
- **Out of scope (do NOT touch):** the `api_regenerate_shot` negative_prompt/docstring defect (spec §9) — a separate background task owns it.

## File structure

| File | Responsibility | Action |
|---|---|---|
| `llm/negative_prompts.py` | Pure deterministic advisory builder (Task 1) | Modify (+ `build_remediation_advisory`) |
| `cinema/auto_approve.py` | `AdvisoryConfig` (`enabled`, `deep_enabled`) mirroring `AutoApproveConfig` (Task 2) | Modify |
| `cinema/shots/controller.py` | Inline advisory in `generate_keyframe_take` (Task 3); deterministic enrichment + opt-in LLM `deep` path in `diagnose_clip` (Tasks 4-5) | Modify |
| `web_server.py` | `api_diagnose_shot` reads/threads `deep` (Task 6) | Modify |
| `web/src/hooks/usePipelineState.ts`, `web/src/App.tsx`, `web/src/components/pipeline/PipelineLayout.tsx`, `web/src/components/pipeline/ReviewStage.tsx` | Thread `deep`; render advisory + Deep-diagnose button + apply-negative-prompt prefill (Task 7) | Modify |
| `tests/unit/test_negative_prompts.py`, `tests/unit/test_advisory_config.py`, diagnose_clip test (Tasks 1,2,4,5) | Tests | Modify/Create |

---

## Chunk 1: T6 Remediation Advisory

### Task 1: Pure deterministic advisory builder

**Files:**
- Modify: `llm/negative_prompts.py` (append after `get_negative_prompt_for_failure`, ~`:49`)
- Test: `tests/unit/test_negative_prompts.py` (existing)

- [ ] **Step 1: Write failing tests** — append to `tests/unit/test_negative_prompts.py`:

```python
from llm.negative_prompts import build_remediation_advisory


def test_advisory_none_when_no_failure_reason():
    assert build_remediation_advisory(None) is None
    assert build_remediation_advisory("") is None


def test_advisory_known_reason_has_negative_prompt():
    adv = build_remediation_advisory("wrong_person", 0.05)
    assert adv == {
        "failure_reason": "wrong_person",
        "suggested_negative_prompt": "wrong person, different face, identity drift, mismatched features",
        "suggested_pulid_adjustment": 0.05,
        "source": "deterministic",
    }


def test_advisory_unknown_reason_empty_negative_prompt():
    adv = build_remediation_advisory("low_identity", 0.0)
    assert adv["failure_reason"] == "low_identity"
    assert adv["suggested_negative_prompt"] == ""   # not in the map → opt-in empty
    assert adv["source"] == "deterministic"
```

- [ ] **Step 2: Run, verify fail** — `.venv/bin/python -m pytest tests/unit/test_negative_prompts.py -q` → FAIL (`ImportError: cannot import name 'build_remediation_advisory'`).

- [ ] **Step 3: Implement** — append to `llm/negative_prompts.py`:

```python
def build_remediation_advisory(
    failure_reason: Optional[str],
    suggested_pulid_adjustment: float = 0.0,
) -> Optional[dict]:
    """Deterministic remediation advice for a failed take.

    Returns None when there is no failure_reason (take passed, or identity
    skipped). Otherwise a structured advisory the review UI renders and the
    operator can act on. Pure — no LLM, no I/O.
    """
    if not failure_reason:
        return None
    return {
        "failure_reason": failure_reason,
        "suggested_negative_prompt": get_negative_prompt_for_failure(failure_reason),
        "suggested_pulid_adjustment": round(float(suggested_pulid_adjustment or 0.0), 3),
        "source": "deterministic",
    }
```

- [ ] **Step 4: Run, verify pass** — `.venv/bin/python -m pytest tests/unit/test_negative_prompts.py -q` → PASS.

- [ ] **Step 5: Commit** — `git commit -- llm/negative_prompts.py tests/unit/test_negative_prompts.py -m "feat(advisory): build_remediation_advisory — deterministic remediation advice"`

---

### Task 2: `AdvisoryConfig` (project-scoped flags)

**Files:**
- Modify: `cinema/auto_approve.py` (add next to `AutoApproveConfig`; mirror its `@dataclass` + `from_project`)
- Test: `tests/unit/test_advisory_config.py` (create)

- [ ] **Step 1: Write failing tests** — create `tests/unit/test_advisory_config.py`:

```python
from cinema.auto_approve import AdvisoryConfig


def test_defaults():
    cfg = AdvisoryConfig.from_project({})
    assert cfg.enabled is True
    assert cfg.deep_enabled is True


def test_overrides_from_global_settings():
    project = {"global_settings": {"advisory": {"enabled": False, "deep_enabled": False}}}
    cfg = AdvisoryConfig.from_project(project)
    assert cfg.enabled is False
    assert cfg.deep_enabled is False


def test_unknown_subkeys_ignored():
    project = {"global_settings": {"advisory": {"enabled": False, "bogus": 1}}}
    cfg = AdvisoryConfig.from_project(project)
    assert cfg.enabled is False
    assert cfg.deep_enabled is True   # missing → default
```

- [ ] **Step 2: Run, verify fail** — `.venv/bin/python -m pytest tests/unit/test_advisory_config.py -q` → FAIL (ImportError).

- [ ] **Step 3: Implement** — in `cinema/auto_approve.py`, add (match the existing `@dataclass`/import style; place after `AutoApproveConfig`):

```python
@dataclass
class AdvisoryConfig:
    """Project-scoped flags for the T6 remediation advisory.

    Read from project.json.global_settings.advisory. Unknown sub-keys are
    silently ignored; missing sub-keys fall back to the defaults.
    """
    enabled: bool = True        # gate inline persistence + diagnose enrichment
    deep_enabled: bool = True   # operator toggle for the opt-in LLM deep diagnosis

    @classmethod
    def from_project(cls, project: dict) -> "AdvisoryConfig":
        gs: dict = project.get("global_settings") or {}
        raw: dict = gs.get("advisory") or {}

        def _get(key: str, default):
            return raw.get(key, default)

        return cls(
            enabled=_get("enabled", cls.enabled),
            deep_enabled=_get("deep_enabled", cls.deep_enabled),
        )
```

> Verify `dataclass` is already imported at the top of `auto_approve.py` (it is — `AutoApproveConfig` uses it). Do not re-import.

- [ ] **Step 4: Run, verify pass** — `.venv/bin/python -m pytest tests/unit/test_advisory_config.py -q` → PASS.

- [ ] **Step 5: Commit** — `git commit -- cinema/auto_approve.py tests/unit/test_advisory_config.py -m "feat(advisory): AdvisoryConfig project-scoped flags (enabled, deep_enabled)"`

---

### Task 3: Inline advisory on failed keyframes

**Files:**
- Modify: `cinema/shots/controller.py` — `generate_keyframe_take`, inside the `if char_diag and not id_result.passed:` block (currently `:667-669`), before `take["path"] = img_path` (`:671`).
- Test: extend the existing identity-metadata test if present.

- [ ] **Step 1: Find the existing test** — `grep -rn "identity_failure_reason\|suggested_pulid_adjustment" tests/`. If a test exercises `generate_keyframe_take` with a mocked validator, extend it (Step 3 test). If none mocks the full generate path, add the assertion to the diagnose_clip test in Task 4 instead and note it here — the pure builder (Task 1) already covers the advisory content; this task is a 3-line wire.

- [ ] **Step 2: Write/extend the test** — assert that after a keyframe take fails identity, `take["metadata"]["remediation_advisory"]["failure_reason"]` matches the mocked `primary_failure_reason.value` and `["source"] == "deterministic"`. Reuse the existing validator-mock pattern (the same fixture that already asserts `identity_failure_reason`).

- [ ] **Step 3: Run, verify fail** — run the targeted test; expect KeyError/`assert` fail on `remediation_advisory`.

- [ ] **Step 4: Implement** — **APPEND these lines immediately after the existing `suggested_pulid_adjustment` write (`controller.py:669`), still inside the `if char_diag and not id_result.passed:` block. Do NOT re-type the existing `:666-669` lines** — they already exist; you are only adding to the block:

```python
                # T6: deterministic remediation advisory (pure; advisory-only).
                # (Appended directly after the existing suggested_pulid_adjustment write at :669.)
                from cinema.auto_approve import AdvisoryConfig
                from llm.negative_prompts import build_remediation_advisory
                if AdvisoryConfig.from_project(self.project).enabled:
                    _adv = build_remediation_advisory(
                        char_diag.primary_failure_reason.value,
                        char_diag.suggested_pulid_adjustment,
                    )
                    if _adv:
                        take["metadata"]["remediation_advisory"] = _adv
```

> `char_diag` is already bound by the existing `:666` line — reuse it, do NOT re-fetch. `self.project` is the controller's project dict; confirm the attribute name by grepping the method, and if the in-scope project var differs (e.g. a local `project`), use that. Use function-level imports (matches the existing `from phase_c_vision import ...` at `:649`).

- [ ] **Step 5: Run, verify pass**; then `.venv/bin/python scripts/ci_smoke.py` → OK.

- [ ] **Step 6: Commit** — `git commit -- cinema/shots/controller.py tests/... -m "feat(advisory): persist remediation_advisory inline on failed keyframes"`

---

### Task 4: Deterministic enrichment of `diagnose_clip`

**Files:**
- Modify: `cinema/shots/controller.py` — `diagnose_clip`, the identity-failure block (`:1831-1842`).
- Test: diagnose_clip test (grep `tests/` for `diagnose_clip`; reuse/create).

- [ ] **Step 1: Find/choose the test file** — `grep -rln "diagnose_clip" tests/`. Reuse if present; else create `tests/unit/test_diagnose_clip_advisory.py`. Mock `_get_shared_validator().validate_image` to return a failing `id_result` whose `character_results[char].primary_failure_reason.value == "wrong_person"` (mirror the mock shape used in existing identity tests).

- [ ] **Step 2: Write failing test** — call `diagnose_clip(shot_id, take_id)`; assert:
  - `result["remediation_advisory"]["suggested_negative_prompt"]` is non-empty for `wrong_person`,
  - the `regenerate` recommendation's `reason` contains `"negative prompt"`.

- [ ] **Step 3: Run, verify fail.**

- [ ] **Step 4: Implement** — **REPLACE the existing identity-failure block (`:1831-1842`) wholesale** with the following. This re-emits the two existing recommendations (`face_swap` + `regenerate`) exactly once each — the regenerate reason now enriched — so the recommendation count is unchanged (no duplicate `face_swap`):

```python
                if not id_result.passed:
                    char_diag = id_result.character_results.get(chars[0])
                    failure_label = char_diag.primary_failure_reason.value if char_diag else "low_identity"
                    delta = char_diag.suggested_pulid_adjustment if char_diag else 0.0
                    # T6: structured advisory + negative-prompt-enriched regen reason.
                    from llm.negative_prompts import build_remediation_advisory, get_negative_prompt_for_failure
                    _adv = build_remediation_advisory(failure_label, delta)
                    if _adv:
                        result["remediation_advisory"] = _adv
                    _neg = get_negative_prompt_for_failure(failure_label)
                    _regen_reason = f"Regenerate with PuLID weight +{delta:.2f}"
                    if _neg:
                        _regen_reason += f"; add negative prompt: {_neg}"
                    result["recommendations"].append(
                        {"tool": "face_swap", "reason": f"Identity gate failed ({failure_label})"}
                    )
                    result["recommendations"].append(
                        {"tool": "regenerate", "reason": _regen_reason}
                    )
```

- [ ] **Step 5: Run, verify pass.**

- [ ] **Step 6: Commit** — `git commit -- cinema/shots/controller.py tests/... -m "feat(advisory): enrich diagnose_clip with negative-prompt advisory"`

---

### Task 5: Opt-in LLM deep diagnosis on `diagnose_clip`

**Files:**
- Modify: `cinema/shots/controller.py` — `diagnose_clip` signature → `(self, shot_id, take_id="", *, deep=False)`; hoist `id_result = None` / `coh = None`; add the deep block before `_record_diagnostic` (`:1878`).
- Test: same diagnose_clip test file as Task 4.

- [ ] **Step 1: Write failing tests** (mock the LLM, mirror `tests/unit/test_chief_director_parse.py`):
  - `deep=True`, key present, `ChiefDirector.evaluate_generation_quality` mocked to return `{"decision":"RETRY","diagnosis":"face drifted","prompt_mutation":"...","mutation_focus":"identity"}` → assert `result["advisory_deep"]["diagnosis"] == "face drifted"` and `["source"]=="llm"`.
  - `deep=True`, `evaluate_generation_quality` raises → assert `result["deep_error"]` set AND the deterministic `result["remediation_advisory"]` still present (fallback intact).
  - `deep=True`, no key (monkeypatch `settings.anthropic_api_key=""`, `settings.openai_api_key=""`) → assert `result["deep_error"] == "No LLM API key configured"` and `result["deep_available"] is False`.

- [ ] **Step 2: Run, verify fail.**

- [ ] **Step 3: Implement** — (a) change the signature and hoist the two vars:

```python
    def diagnose_clip(self, shot_id: str, take_id: str = "", *, deep: bool = False) -> dict:
        ...
        id_result = None   # hoist: referenced by the deep block even if identity skipped
        coh = None         # hoist: referenced by the deep block even if coherence skipped
```
(set `id_result` where it is currently assigned inside the identity block; set `coh` where currently assigned inside the coherence block — remove the local re-declaration, keep the assignment.)

(b) add before the `self._record_diagnostic(...)` call (`:1878`):

```python
        if deep:
            from config.settings import settings as _settings
            from cinema.auto_approve import AdvisoryConfig
            deep_available = bool(_settings.anthropic_api_key or _settings.openai_api_key)
            result["deep_available"] = deep_available
            if not deep_available:
                result["deep_error"] = "No LLM API key configured"
            elif AdvisoryConfig.from_project(self.project).deep_enabled and image_path and os.path.exists(str(image_path)) and chars:
                try:
                    from llm.chief_director import ChiefDirector
                    _ref = get_reference_image(self.project, chars[0]) or ""
                    _deep = ChiefDirector(self.project).evaluate_generation_quality(
                        image_path=str(image_path),
                        reference_path=_ref,
                        identity_result=id_result,
                        identity_score=result["scores"].get("identity") or 0.0,
                        shot_prompt=shot.get("prompt", ""),
                        scene_context=f"{scene.get('title', '')} — {scene.get('action', '')}",
                        coherence_result=coh,
                    )
                    result["advisory_deep"] = {
                        "diagnosis": _deep.get("diagnosis", ""),
                        "prompt_mutation": _deep.get("prompt_mutation", ""),
                        "mutation_focus": _deep.get("mutation_focus", ""),
                        "decision": _deep.get("decision", ""),
                        "source": "llm",
                    }
                except Exception as _e:   # LLM path fully isolated — never break the panel
                    result["deep_error"] = str(_e)
```

> `evaluate_generation_quality` accepts `identity_result` OR `identity_score` (handles `None`), so passing a possibly-`None` `id_result` is valid. `get_reference_image`, `scene`, `shot`, `image_path`, `chars` are all already in scope in `diagnose_clip`.

- [ ] **Step 4: Run, verify pass.** Then `.venv/bin/python scripts/ci_smoke.py` → OK.

- [ ] **Step 5: Commit** — `git commit -- cinema/shots/controller.py tests/... -m "feat(advisory): opt-in LLM deep diagnosis on diagnose_clip(deep=True)"`

---

### Task 6: Thread `deep` through `api_diagnose_shot`

**Files:**
- Modify: `web_server.py` — `api_diagnose_shot` (`:2138-2146`).

- [ ] **Step 1: Implement** — read `deep` from the body and thread it:

```python
@app.route("/api/projects/<pid>/shots/<shot_id>/diagnose", methods=["POST"])
def api_diagnose_shot(pid, shot_id):
    """Run quality diagnostics on a clip. `deep=true` adds an LLM deep diagnosis."""
    body = request.json if request.is_json else {}
    take_id = body.get("take_id", "")
    deep = bool(body.get("deep", False))
    try:
        result = _get_stage_pipeline(pid).diagnose_clip(shot_id, take_id=take_id, deep=deep)
    except ValueError:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(result)
```

- [ ] **Step 2: Verify** — `.venv/bin/python scripts/ci_smoke.py` → OK; `grep -n "diagnose_clip" web_server.py` shows the `deep=deep` thread. (No new route; pid-scoped shape unchanged.)

- [ ] **Step 3: Commit** — `git commit -- web_server.py -m "feat(advisory): thread deep flag through api_diagnose_shot"`

---

### Task 7: Frontend — thread `deep`, render advisory, Deep-diagnose button, apply prefill

**Files (editorial palette — NOT console):**
- Modify: `web/src/hooks/usePipelineState.ts` (`diagnoseShot`, `:204`)
- Modify: `web/src/App.tsx` (`:26,161`), `web/src/components/pipeline/PipelineLayout.tsx` (`:47,346`) — prop-chain signature `(shotId, takeId?, deep?)`
- Modify: `web/src/components/pipeline/ReviewStage.tsx` (`onDiagnose:46`, `handleDiagnose:299`, button `:739`, advisory render near `:747`)

- [ ] **Step 1: `diagnoseShot`** — add `deep`:
```ts
const diagnoseShot = useCallback(async (shotId: string, takeId?: string, deep = false) => {
  ...
  return postJson(`/api/projects/${projectId}/shots/${shotId}/diagnose`, { ...(takeId ? { take_id: takeId } : {}), deep })
}, [projectId, ...])
```

- [ ] **Step 2: Thread the `deep` arg** through the `onDiagnose` / `onDiagnoseShot` prop types in `App.tsx` and `PipelineLayout.tsx` to `(shotId: string, takeId?: string, deep?: boolean) => Promise<any>`. Verify every call site's labels are semantically correct (CLAUDE.md public-API watchpoint).

- [ ] **Step 3: ReviewStage** — (a) add a **"Deep diagnose"** button next to "Diagnose" (`:739`) calling `onDiagnose(shot.id, activeTakeId, true)`; disable it when the latest `diagnosis?.deep_available === false`. (b) Render `take.metadata?.remediation_advisory` and `diagnosis?.remediation_advisory` (failure reason, suggested negative prompt in mono, PuLID nudge) plus `diagnosis?.advisory_deep?.diagnosis` prose and a small note if `diagnosis?.deep_error`. Reuse the existing `editorial-warn` box style (`:748`). (c) **Apply prefill:** an "Apply negative prompt" affordance that sets the existing `negativePrompt` state to the suggested phrase (so the operator can submit via the existing keyframe-regen form). Display-only for the PuLID nudge.

- [ ] **Step 4: Gate** — `cd web && npx tsc --noEmit && npm run build` → both clean.

- [ ] **Step 5: Verify in preview** (per harness preview workflow): import a project with a failed-identity take; confirm the advisory renders and "Deep diagnose" returns prose (or a graceful note with no key). Screenshot for the user.

- [ ] **Step 6: Commit** — `git commit -- web/src/hooks/usePipelineState.ts web/src/App.tsx web/src/components/pipeline/PipelineLayout.tsx web/src/components/pipeline/ReviewStage.tsx -m "feat(advisory): review-surface advisory + Deep-diagnose button + apply-negative-prompt prefill"`

---

## Final verification (before finishing the branch)

- [ ] **Before Task 1:** capture the baseline — `.venv/bin/python -m pytest tests/ -q` → record the live pass/skip count (prior session reported ~1617 passed / 2 skipped; capture the actual number). **After Task 7:** re-run → green with no new failures vs that captured baseline.
- [ ] `.venv/bin/python scripts/ci_smoke.py` → OK.
- [ ] `cd web && npx tsc --noEmit && npm run build` → clean.
- [ ] Run the §15 smoke block in `ARCHITECTURE.md`.
- [ ] **Lane D (operator):** `diagnose_clip` + `api_diagnose_shot` are documented subsystems — update `ARCHITECTURE.md` if the diagnose behavior section drifted.
- [ ] Final cross-cutting review (subagent-driven-development closeout) over `BASE_SHA..HEAD`.

## Execution notes
- Sequential dispatch only (shared `controller.py`). Order: 1 → 2 → 3 → 4 → 5 → 6 → 7.
- Each task: implementer subagent → spec reviewer → code-quality reviewer (CLAUDE.md per-task loop). Tasks 3-5 touch thread-shared / pipeline code — ask the code reviewer to check the failure-isolation of the deep path and that `id_result`/`coh` hoisting didn't change existing control flow.
- Reference: @superpowers:test-driven-development, @superpowers:subagent-driven-development, @superpowers:verification-before-completion.
