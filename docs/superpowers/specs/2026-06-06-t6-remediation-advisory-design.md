# T6 — Remediation Advisory (auto-diagnose, operator-assist) — Design Spec

*Date: 2026-06-06. Author: operator-seat. Status: **DESIGN — approved in brainstorm, pending spec-review + user sign-off**.
Branch: `feat/max-tier-provisioning`. Baseline HEAD at write: `8647a0f`.*

## 1. Context & motivation

Two quality levers are **fully implemented but dormant** (zero production callers):

- `ChiefDirector.evaluate_generation_quality(...)` — `llm/chief_director.py:336`. A 2×2 (identity × coherence)
  diagnosis that calls an LLM (Anthropic → OpenAI fallback) and returns a `dict`:
  `{decision, mutation, mutation_level, diagnosis, prompt_mutation, mutation_focus}`. It internally enriches the
  prompt-mutation with a negative prompt via `get_negative_prompt_for_failure` (`chief_director.py:480`).
  **Verified: 0 production callers; only `tests/unit/test_chief_director_parse.py` references it.**
- `llm/negative_prompts.py` — `NEGATIVE_PROMPT_BY_FAILURE_REASON` (dict mapping the 7
  `identity.types.FailureReason` values → negative-prompt phrases) + `get_negative_prompt_for_failure(reason) -> str`
  (returns `""` for `None`/unknown). **Verified: only reachable through the dead `evaluate_generation_quality`.**

T6 ("noop-audit" ticket, 2026-06-03; `docs/superpowers/2026-06-03-part3-noop-audit-tickets.md`) is to **wire these
levers into the pipeline**, raising capability per the program's full-capability intent (PROGRAM-MANUAL).

> **Doc-vs-code divergence flagged (carry into the manual-staleness check):** the ticket cites "PROGRAM-MANUAL §5"
> as if it contains an auto-diagnose/remediate *recipe*. It does not — `PROGRAM-MANUAL.md` only flags these two
> symbols as dead code; §5 frames capability intent but spells out no recipe for this loop. So this design is the
> recipe; it is not transcribed from the manual. If T6 ships, add a manual line documenting the wired behavior.

## 2. Goal & non-goals

**Goal:** an **operator-assist advisory** — when a keyframe take fails its identity gate, surface a *concrete
remediation suggestion* (the specific failure reason + a suggested negative-prompt phrase + a PuLID/identity nudge),
and offer an opt-in **LLM "deep diagnosis"** for richer reasoning. The operator decides whether/how to regenerate.

**Non-goals (explicit):**
- **No autonomous regeneration loop.** The pipeline does not auto-retry. (This was the rejected "autonomous"
  scope; the user chose operator-assist.)
- **No PuLID-strength override wiring.** No regenerate path accepts a PuLID/identity-strength parameter today; the
  PuLID nudge is **advisory text only**.
- **No fix to the `api_regenerate_shot` restart-path defect** (see §9) — that is a separate bug, out of scope here.
- **No new HTTP endpoint.** A complete Diagnose flow already exists; T6 enriches it.

## 3. Current state (verified)

| Piece | Location | Today |
|---|---|---|
| On-demand diagnose | `cinema/shots/controller.py:1791` `diagnose_clip(shot_id, take_id="")` | Re-runs the identity validator on the persisted image (`:1827` → rich `id_result`), runs motion + coherence, emits `{tool, reason}` recommendations, records a diagnostic (`:1878`), returns `{shot_id, take_id, take_kind, scores{}, recommendations[]}`. On identity failure it already reads `primary_failure_reason` + `suggested_pulid_adjustment` (`:1834-1842`). |
| Diagnose endpoint | `web_server.py:2138` `api_diagnose_shot` | `POST /api/projects/<pid>/shots/<shot_id>/diagnose`, reads `take_id` from body (`:2141`), calls `diagnose_clip` (`:2143`). **No `@_project_lock_guard`** — `diagnose_clip` self-locks via `_record_diagnostic` → `mutate_project`. |
| Diagnose button (FE) | `web/src/components/pipeline/ReviewStage.tsx:739` (`handleDiagnose:299`) → `usePipelineState.ts:204 diagnoseShot` → POST | Renders `diagnosis.recommendations` (or `latestDiagnostic.recommendations`) in an **editorial-palette** warn box (`ReviewStage.tsx:747-756`). Palette is `editorial-*`, NOT console. |
| Persisted failure signals | `cinema/shots/controller.py:661,668,669` | On a failed keyframe, `generate_keyframe_take` already sets `take["metadata"]["identity_score"]`, `["identity_failure_reason"]` (a `FailureReason.value`), `["suggested_pulid_adjustment"]` (float). `take["path"]` = image (`:671`). The rich `IdentityValidationResult` is **not** persisted (scalars only). |
| Project → FE | `web_server.py:481` `api_get_project` | Serves the full project JSON (scenes → shots → takes incl. `take.metadata`, `shot.diagnostics`). A new `take.metadata.remediation_advisory` flows through unchanged. |
| Config pattern | `cinema/auto_approve.py:107` `AutoApproveConfig.from_project(project)` reading `project["global_settings"]["auto_approve"]` | The mirror for a new `AdvisoryConfig`. `config/settings.py` is `@dataclass(frozen=True)` with `from_env`. |

**Conclusion:** the gap is exactly two missing wires — `diagnose_clip` never calls `get_negative_prompt_for_failure`,
and nothing calls `evaluate_generation_quality`. The Diagnose surface, validator re-run, and persisted signals all
already exist.

## 4. Design

### 4.1 Component A — Deterministic advisory (always-on core, $0, no LLM)

A pure builder, **`build_remediation_advisory`**, added to `llm/negative_prompts.py` (co-located with the
failure→phrase map; alternative placement `cinema/remediation_advisory.py` — confirm import direction during planning):

```python
def build_remediation_advisory(
    failure_reason: Optional[str],
    suggested_pulid_adjustment: float = 0.0,
) -> Optional[dict]:
    """Deterministic remediation advice for a failed take. None when no failure_reason."""
    if not failure_reason:
        return None
    return {
        "failure_reason": failure_reason,
        "suggested_negative_prompt": get_negative_prompt_for_failure(failure_reason),
        "suggested_pulid_adjustment": round(suggested_pulid_adjustment, 3),
        "source": "deterministic",
    }
```

Used in two places, both from data already in hand (no extra cost, no validator re-run for the inline case):

1. **Inline at generation** — `cinema/shots/controller.py`, immediately after the identity-failure block sets
   `identity_failure_reason`/`suggested_pulid_adjustment` (~`:668-669`): build the advisory and persist
   `take["metadata"]["remediation_advisory"] = build_remediation_advisory(reason, delta)`. Pure dict lookup →
   advice is present in review **without** an operator click.
2. **In `diagnose_clip`** — when identity fails (`:1834`), attach the same structured advisory to `result`
   (e.g. `result["remediation_advisory"] = build_remediation_advisory(failure_label, delta)`) and enrich the existing
   `regenerate` recommendation's `reason` to include the suggested negative-prompt phrase.

### 4.2 Component B — LLM deep diagnosis (opt-in)

Extend the signature: **`diagnose_clip(self, shot_id, take_id="", *, deep=False)`**. `diagnose_clip` already holds the
rich `id_result` (`:1827`), the coherence score, and `image_path` (`:1816`); reference + prompt + scene context are
reconstructable (`get_reference_image(project, char)`; `shot["prompt"]`; `scene` fields). When `deep=True` and an LLM
key is configured:

```python
director = ChiefDirector(project)               # mirror existing construction
deep = director.evaluate_generation_quality(
    image_path=str(image_path),
    reference_path=primary_ref,
    identity_result=id_result,                   # rich object already computed above
    coherence_result=coh if coherence_ran else None,
    shot_prompt=shot.get("prompt", ""),
    scene_context=f"{scene.get('title','')} — {scene.get('action','')}",
)
result["advisory_deep"] = {
    "diagnosis": deep.get("diagnosis", ""),
    "prompt_mutation": deep.get("prompt_mutation", ""),
    "mutation_focus": deep.get("mutation_focus", ""),
    "decision": deep.get("decision", ""),
    "source": "llm",
}
```

`api_diagnose_shot` reads `deep` from the POST body (default `False`) and threads it. The frontend gets a separate
**"Deep diagnose"** button, enabled only when `deep_enabled` (see §4.4).

### 4.3 Data flow
- Run → failed keyframe → inline deterministic advisory on `take.metadata` → visible in review immediately.
- Operator clicks **Diagnose** → `diagnose_clip()` (deterministic; recommendations now carry the negative-prompt phrase).
- Operator clicks **Deep diagnose** → `diagnose_clip(deep=True)` → LLM. **On LLM error / missing key: catch, skip
  `advisory_deep`, set `result["deep_error"] = "<msg>"`, return the deterministic result** — the panel never breaks.

### 4.4 Frontend (`ReviewStage.tsx`, editorial palette)
- Render `take.metadata.remediation_advisory` (inline) and `diagnosis.remediation_advisory` / `advisory_deep`:
  failure reason, suggested negative prompt (mono), PuLID nudge text, and (when present) the LLM `diagnosis` prose —
  in/near the existing `editorial-warn` box (`:747`).
- A **"Deep diagnose"** button beside "Diagnose" (`:739`); render `advisory_deep.diagnosis` when returned; show a
  small note if `deep_error` present.
- **Assist action:** "Apply suggested negative prompt" pre-fills the existing regen form's negative-prompt field
  (`ReviewStage` already has `negativePrompt` state; the keyframe-take path `controller.py:464` accepts
  `negative_prompt`). Operator submits. *(Confirm during planning that the generate-keyframe endpoint threads
  `negative_prompt` end-to-end; the restart path does not — §9.)*

### 4.5 Config — `AdvisoryConfig.from_project` (mirror `AutoApproveConfig`)
Read `project["global_settings"]["advisory"]`:
- `enabled: bool = True` — gate the inline persistence + diagnose enrichment.
- `deep_enabled: bool = True` — gate the LLM button; **auto-false when no Anthropic/OpenAI key is configured**
  (reuse `ChiefDirector`'s existing key detection).
No new score threshold: the advisory keys off the existing identity pass/fail (it fires exactly when the gate already
says "failed"), so there is nothing new to tune.

## 5. Interfaces (summary)
- `build_remediation_advisory(failure_reason: Optional[str], suggested_pulid_adjustment: float=0.0) -> Optional[dict]` — new, pure.
- `diagnose_clip(self, shot_id, take_id="", *, deep=False) -> dict` — `deep` kwarg added (back-compatible default).
- `api_diagnose_shot` — read `deep` from body; thread to `diagnose_clip`. Route/shape unchanged.
- `take.metadata.remediation_advisory: {failure_reason, suggested_negative_prompt, suggested_pulid_adjustment, source}` — new, optional.
- `diagnose_clip` result gains optional `remediation_advisory`, `advisory_deep`, `deep_error`.
- `AdvisoryConfig{enabled, deep_enabled}` + `.from_project`.

## 6. File-by-file change list
1. `llm/negative_prompts.py` — add `build_remediation_advisory` (+ import `Optional`).
2. `cinema/shots/controller.py` — inline advisory in `generate_keyframe_take` (~`:670`); enrich + `deep` branch in `diagnose_clip` (`:1791`).
3. `web_server.py` — `api_diagnose_shot` (`:2138`) read+thread `deep`.
4. `cinema/auto_approve.py` *or* a small new module — `AdvisoryConfig` (placement mirrors `AutoApproveConfig`).
5. `web/src/hooks/usePipelineState.ts` (`:204`) — `diagnoseShot(shotId, takeId?, deep?)`.
6. `web/src/components/pipeline/ReviewStage.tsx` — advisory render + Deep-diagnose button + apply-negative-prompt prefill. Thread the `deep` arg through `App.tsx` / `PipelineLayout.tsx` props.
7. Tests — see §7.

## 7. Testing
- **Deterministic (no LLM):** unit-test `build_remediation_advisory` (each `FailureReason` → expected phrase; `None` → `None`). Unit-test `diagnose_clip` identity-failure path attaches `remediation_advisory` and the enriched recommendation reason (mock the validator to return a failing `id_result`, as existing tests do).
- **LLM deep path:** mock `ChiefDirector.evaluate_generation_quality` (pattern: `tests/unit/test_chief_director_parse.py`); assert `advisory_deep` shape on success and `deep_error` + graceful fallback on raise.
- **Config:** `AdvisoryConfig.from_project` defaults + override; `deep_enabled` auto-false with no key.
- **Frontend gate:** `cd web && npx tsc --noEmit && npm run build` (no FE test runner in this repo — do not add one).
- **Smoke:** `.venv/bin/python scripts/ci_smoke.py` + full `pytest` green.

## 8. Error handling & safety
- LLM path fully isolated; the deterministic core never imports/awaits it. LLM failure/no-key → fallback (§4.3).
- Inline advisory is a pure lookup off already-set scalars — cannot fail the generation path (guard `if reason`).
- `deep=True` is the only path that spends money/latency, and only on an explicit operator click.

## 9. Out of scope — flagged observations (not fixed here)
- **`api_regenerate_shot` defect** (`web_server.py:2071`): docstring (`:2074`) claims *"Supports positive_prompt and
  negative_prompt"* but the code reads only `positive_prompt` (`:2076`) and `regenerate_shot(scene_id, shot_id)`
  (`controller.py:1551`) takes no prompt args — `negative_prompt` is **silently dropped** on the restart path.
  T6's "apply" uses the keyframe-take path (honors `negative_prompt`), sidestepping it. Separate follow-up
  (docstring fix at minimum; threading `negative_prompt` if desired).
- **No PuLID-strength override param** in any regenerate path → the PuLID nudge stays advisory text.

## 10. Open questions resolved in brainstorm
- Outcome scope = **operator-assist advisory** (not autonomous). Engine = **hybrid** (deterministic always-on + opt-in
  LLM deep). Inline-persistence = **yes** (full hybrid approved).

## 11. Risks
- `ChiefDirector(project)` construction cost / key handling on the deep path — mitigated by `deep_enabled` auto-gating.
- FE prop-threading churn through `App.tsx`/`PipelineLayout.tsx`/`ReviewStage.tsx` for the new `deep` arg — small but
  spans 3 files; verify call-site label correctness (CLAUDE.md public-API watchpoint).
- `cinema` → `llm` import edge for `build_remediation_advisory` — confirm acceptable during planning (else place the
  builder in `cinema/`).
