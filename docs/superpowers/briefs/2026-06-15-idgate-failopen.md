# R-BRIEF: idgate-failopen — identity-gate fail-OPEN-to-PASS on vision-LLM error (CRITICAL, CROSS-LANE)

PRIORITY: **CRITICAL** (PROVISIONAL upgrade MAJOR→CRITICAL, coordinator S12; **awaits operator-1 ratification per R-VERIFY-TIER** — evidence below)   LANE: A content (identity-gate policy) in a §6b **Pair-B module** (`phase_c_vision.py`) ⇒ **CROSS-LANE**.
CROSS-CUTTING: **no** (`phase_c_vision.py` is not auto_approve.py / cinema/context.py / core.py / web_server.py) → **no lock**.
CO-SIGN: **Tier-A — director2 lands a `verification-report` BEFORE DISPATCH** (no soft reading; 40 min of silence ≠ consent). Author: director-1. Verifier: operator-1 (Lane V).

---

## The defect (file:line + observable symptom)

`phase_c_vision.py::validate_identity_vision(reference_path, generated_path)` returns a **passing** result on three error fallbacks:

```
phase_c_vision.py:253   default_pass = {"match": True, "confidence": 0.7, "issues": [], "source": "default"}
phase_c_vision.py:261-263   if not api_key:  print("...No ANTHROPIC_API_KEY — returning default pass"); return default_pass
phase_c_vision.py:278-280   if ref_b64 is None or gen_b64 is None: ... return default_pass     # image-encode failure
phase_c_vision.py:351-353   except Exception as e: print("...Claude identity validation failed: {e}"); return default_pass
```

On the production cloud the identity gate is **exclusively** this path, and the fabricated `0.7` is evaluated as a real score → a forged identity PASS. **A shot with the WRONG person ships silently** — a direct violation of the program's core promise (identity-consistent photoreal video).

## Severity proof — CRITICAL (first-hand, cited; supports the coordinator's provisional upgrade)

1. **Exclusive path on prod cloud** — `identity/validator.py:399-403`:
   ```python
   if not DEEPFACE_AVAILABLE:
       return self._vision_llm_validate_image(image_path, reference_path, character_id, character_name,
                                               shot_type, threshold if threshold is not None else get_threshold_for_shot(shot_type))
   ```
   When `DEEPFACE_AVAILABLE=False` (the prod cloud), `validate_image` returns the vision path immediately — DeepFace (`:405-443`) is never reached. No alternative catches a bad identity.

2. **The fabricated 0.7 IS re-thresholded and PASSES** — `identity/validator.py:1337-1347` (THE decisive site):
   ```python
   result = self._vision_fallback(reference_path, image_path)        # = validate_identity_vision
   if result.get("skip"): return self._skipped_result(...)
   if result.get("missing_generated"): return self._missing_output_result(...)
   confidence = result.get("confidence", 0.0)
   matched = confidence >= threshold
   ```
   On error, `confidence = 0.7` → `matched = 0.7 >= threshold`. Standard thresholds (`identity/types.py:95-101`): portrait 0.70, medium 0.65, wide 0.55, action 0.60. **`0.7 ≥` all of them → forged PASS for every standard/lenient tier.** Only strict-portrait (0.75) escapes.
   ⇒ The inline comment at `phase_c_vision.py:338-341` ("the 0.7 never governs a real production gate") is **WRONG for the error path** — it describes only the success path (real Claude response re-thresholded). The error fallback rides the SAME `:1346` comparison.

3. **`source="default"` is unobservable** — `_vision_llm_validate_image` reads only `confidence`/`issues`/`skip`/`missing_generated` (`:1341-1351`); `source` is discarded, never reaching `IdentityValidationResult`. No downstream caller distinguishes a fabricated 0.7 from a real one (grep-confirmed).

4. **Wiring** — `identity/__init__.py:52-54` injects `validate_identity_vision` as `vision_fallback`; production callers route via `identity.get_shared_validator()` → `validate_image`/`validate_video` (`cinema/shots/controller.py:817,853,1371,2218`).

5. **Worst case = the no-key path (`:261-263`)**: a deployment missing `ANTHROPIC_API_KEY` forges a PASS on EVERY identity check — a deterministic, guaranteed fail-open, not just an on-error one.

## Rule #12 — the fabricated value reaches the gate (grep-the-read)
TARGET: the `confidence` key of `validate_identity_vision`'s return.
`identity/validator.py:1346  confidence = result.get("confidence", 0.0)` ← reads the fallback dict's `0.7` directly; `:1347  matched = confidence >= threshold` is the gate. Runtime-evaluated, not advisory.

## Rule #13 — sibling audit
- **Same fail-open pattern in the two sibling vision gates** (note, fold-or-file — NOT silently leave):
  - `validate_face_quality_vision` (GPT-4o, `phase_c_vision.py:~242-244`) → `default_pass {"pass": True}` on error.
  - `validate_scene_coherence_vision` (`phase_c_vision.py:356+`) → `default_pass {"coherent": True}` on error. (Relates to the coordinator's unpinned `coherence-silent` caller-side half — flag to coordinator; this brief FIXES identity, and applies the SAME fail-closed pattern to the two siblings IF director2 co-signs that scope, else files them as their own rows.)
- **The correct pattern already exists**: `validator.py:1341-1344` maps `skip`/`missing_generated` → non-pass results. The legitimate `skip` (no reference on disk, `:267`) and `missing_generated` (`:270`) are CORRECT and MUST be preserved — the bug is ONLY the three *error* fallbacks returning a passing 0.7.

## The fix (policy + mechanism)

**POLICY (co-sign point b): FAIL-CLOSED, not pass-with-warning.** On no-key / API-error / encode-fail, `validate_identity_vision` returns a NON-PASSING marker + a structural WARNING — never `confidence: 0.7`. Justification (downstream verified, `cinema/shots/controller.py:817-847`): a failed gate (`passed=False`) records `identity_failure_reason` + `suggested_pulid_adjustment` and feeds the remediation/regen path — it does **NOT raise or deadlock**. So fail-closed degrades honestly: a transient error → a regen attempt; a persistent outage → best-of-N exhausts and ships the best take **with the failure recorded**, never a forged pass.

**MECHANISM:**
1. Error fallbacks return a marker the validator maps to a NON-PASS result — mirror the `missing_generated` path (`validator.py:1343-1344` → `_missing_output_result`, a non-pass), NOT the `skip` path (advisory). E.g. `validate_identity_vision` returns `{"match": False, "confidence": 0.0, "error": True, "source": "default", "issues": ["identity check unavailable: <reason>"]}`; add a handler `if result.get("error"): return self._error_result(...)` (passed=False, a distinct `FailureReason`, e.g. IDENTITY_UNVERIFIED) alongside the existing skip/missing handlers at `validator.py:1341-1344`. **Implementer must CONFIRM `_skipped_result`'s `passed` value** so the error path does not accidentally route through an advisory/pass.
2. **Bounded retry before fail-closed** (absorb transient blips → bound spurious regen cost): 2–3 attempts with short backoff around the `client.messages.create` call before the `:351` except returns the error marker. The no-key path (`:261-263`) does NOT retry — it is a config error → fail-closed immediately + a loud structural WARNING (`logging.warning`, not `print`).
3. **Cover ALL THREE error sites** (`:263` no-key, `:280` encode-fail, `:353` API-exception) + replace the `print`s with structural `WARNING`s (observability is contractual per the stub-contract spec).
4. Preserve the legitimate `skip` (no reference) and `missing_generated` paths unchanged.

## Co-sign scope (director2 — Tier-A `verification-report` BEFORE dispatch)
The coordinator (S12 §4) requires the co-sign to cover: **(a)** ack severity now CRITICAL (gate-bypass, not just observability) — evidence above, decisive site `validator.py:1346-1347`; **(b)** ratify the policy: **fail-closed** (recommended) vs pass-with-warning — confirm the downstream `controller.py:817-847` non-deadlock reasoning; **(c)** confirm the fix covers both print sites (`:353`/`:263`) + the no-api-key path (`:261-263`) — and acknowledge the encode-fail site `:280` (a THIRD error site the S12 list did not name) + the Rule #13 sibling decision (fold the two siblings here, or file as separate rows). Verify the full change-set scope at the source (not brief-trust); operator-1 confirms the landed diff matches this co-signed scope (drift = FAIL).

## Verification (operator/CI) — stub-contract: this IS a gate-fail row (NOT coverage-only)
Per `docs/superpowers/specs/2026-06-15-wave2-stub-contract.md`: dual-mode identity/vision stub (Pair-A owned), ≥1 gate-fail assertion, observability asserted.
- **New strict-xfail → live pin(s)** asserting: for each of the 3 error fallbacks, the identity gate **FAILS** (`IdentityValidationResult.passed is False`) for a standard-mode shot — i.e. drive `validate_identity_vision` to its error path (stub: raise inside the Anthropic call / unset key / encode→None) and assert the validator returns `passed=False` (today it returns `True` — the non-vacuous RED).
- Assert the structural WARNING fires (captured-log) on each error path.
- Assert the legitimate `skip`/`missing_generated` paths still behave (regression guard — do not over-fix).
- Mutation proof: revert the error marker → the gate re-passes (RED) → confirms non-vacuity.
- Reviewer: `lane-v-verifier` (cold). Not a money row; the gate-bypass lens is the focus.

## Scope boundaries
- DECISIONS.md ADR: a fail-open→fail-closed identity-gate POLICY change warrants a one-line ADR (cite this brief + the decisive site). Author on GO.
- Do NOT expand into the broader `coherence-silent` caller-side row (`controller.py:2266`) — that is a separate Pair-A row; only the `validate_scene_coherence_vision` *fallback* is in scope here (and only if director2 co-signs the sibling fold).
