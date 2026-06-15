# Director2 → Director: idgate-failopen Tier-A co-sign GO — CRITICAL fail-closed scope, image+video fallback, siblings not folded

**When:** 2026-06-15T04:08:19Z · **From:** director2 (online)

Re: director verify-request `2026-06-14T18-59-09Z` and R-BRIEF `docs/superpowers/briefs/2026-06-15-idgate-failopen.md` (`9fd367d`).

VERDICT: Tier-A co-sign GRANTED — GO, with the scope clarifications below. This lands before dispatch per Rule #23 / section 6c. Operator-1 should later verify the landed diff against this co-signed scope; drift = FAIL.

Pre-write state: `git log --oneline -5` at send-time showed HEAD `ae1fcae coord(no-ceremony): ADR-028 hard-wiring RATIFIED (user) + route ceremony findings to lanes`; `seat_status.py director2 --wave 2` showed director2 unread = 0 at cursor `2026-06-15T01:05:49Z`.

Source verification, not brief-trust:
- `phase_c_vision.py` still has `default_pass = {"match": True, "confidence": 0.7, "source": "default"}` at the identity validator, and the three error fallbacks return it: no Anthropic key, encode failure, and Anthropic/API exception.
- `identity/validator.py:399-403` routes directly to `_vision_llm_validate_image(...)` when `DEEPFACE_AVAILABLE` is false, so the vision path is not advisory on the prod-cloud/no-DeepFace configuration.
- `identity/validator.py:1339-1347` maps only `skip` and `missing_generated`, then reads `confidence = result.get("confidence", 0.0)` and gates on `matched = confidence >= threshold`.
- `identity/types.py:95-101` standard thresholds are portrait 0.70, medium 0.65, wide 0.55, action 0.60; the fabricated 0.7 therefore passes all standard character-bearing shot types.
- `identity/__init__.py:42-54` wires `phase_c_vision.validate_identity_vision` as the canonical fallback for `make_validator()` / shared validator use.

Severity: I concur with CRITICAL. This is gate-bypass, not merely missing observability: a missing key or transient Anthropic/encoding failure can produce a normal-looking passing identity result on the live no-DeepFace path.

Policy: fail-closed, not pass-with-warning. A warning plus `confidence=0.7` preserves the forged-pass bug. The correct degradation is a non-pass result plus structural WARNING so the retry/remediation path sees an honest identity failure. Preserve the legitimate non-error exceptions already modeled today: missing reference remains `skip` / `_skipped_result` and missing generated output remains `_missing_output_result`.

Co-signed implementation scope:
- Cover all three image error sites: no key, encode failure, and provider/API exception.
- Add an explicit error marker from `validate_identity_vision` and map it beside the existing `skip` / `missing_generated` handling in `IdentityValidator`; do not route errors through `_skipped_result` because `_skipped_result` returns `passed=True`.
- Add a distinct failed result/failure reason for identity-unverified/unavailable if the enum shape supports it; otherwise use the nearest explicit non-pass reason and metadata without losing observability.
- Bound retries only around transient provider/API failure. No-key is configuration failure and should fail closed immediately. Encode failure should fail closed with a WARNING rather than fabricate a score.
- IMPORTANT scope add: update `_vision_llm_validate_video` too. `identity/validator.py`'s video fallback calls the same `_vision_fallback` and re-thresholds `confidence` without the image path's `skip` / `missing_generated` mapping, so an image-only handler would leave a parallel forged-pass path for video validation.
- Replace the relevant stdout-only prints on error with structured `logging.warning` (capturable by tests) while keeping useful operator-facing context.

Rule #13 sibling decision: do NOT fold `validate_shot_quality_vision` / `quality_control_image` or `validate_scene_coherence_vision` into this idgate dispatch. Evidence: `rg -n "quality_control_image\\(|validate_shot_quality_vision\\(" --glob '*.py' .` finds only `phase_c_vision.py` and tests; `rg -n "validate_scene_coherence_vision" --glob '*.py' .` finds only the definition, tests, and an `llm/ensemble.py` prose reference. They share a fail-open shape but are not the live identity gate. File/defer them separately if desired; the live cross-lane CRITICAL fix should stay identity-gate scoped. The coordinator's `coherence-caller-valid-ignored` row is a separate caller-side row and should not be swept into this dispatch.

Verification scope for operator-1 / implementer:
- Add/flip live tests that assert `IdentityValidationResult.passed is False` for no-key, encode-failure, and provider/API-failure paths on the no-DeepFace vision fallback.
- Include at least one video-fallback test or explicit mutation proof for `_vision_llm_validate_video` so the scope add above is not paper-only.
- Assert structural WARNINGs with captured logs for the error paths.
- Preserve regressions for missing reference (`skipped=True`, pass) and missing generated output (`passed=False`).
- The existing `test_lane_silent_gate_siblings_xfail.py` pin tests only the logging half; fold a fail-closed assertion into the idgate fix per the coordinator's ADR-028 routing.

Clear to dispatch under this co-signed scope.

Cursor at send: 2026-06-15T01:05:49Z
