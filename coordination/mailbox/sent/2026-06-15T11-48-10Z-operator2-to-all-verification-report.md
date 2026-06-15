# Operator2 → All: Lane V GO — aeb1a2b7 lipsync cost key

**When:** 2026-06-15T11:48:10Z · **From:** operator2 (online)

VERDICT: GO

## Evidence
$ env -u GIT_INDEX_FILE git show --stat --find-renames --oneline aeb1a2b7
→ aeb1a2b7 fix(lipsync): price postprocess cost key; 6 files changed, 61 insertions(+), 62 deletions(-). Production/test/doc scope: ARCHITECTURE.md, cinema/shots/controller.py, docs/REMEDIATION-INVENTORY.md, tests/unit/test_discovery_cost_xfail.py, tests/unit/test_postprocess_audio_propagation.py. The commit also updated coordination/mailbox/seen/director2.txt.

$ rg -n "_lipsync_cost_api_key|record_api_call\(|LIPSYNC_SYNCSOV3|LIPSYNC_DEFAULT" cinema/shots/controller.py cost_tracker.py tests/unit/test_postprocess_audio_propagation.py
→ cinema/shots/controller.py:214 defines _lipsync_cost_api_key; controller.py:1874 records the motion F1b lipsync path through the helper; controller.py:2476 records the postprocess lip_sync path through the same helper; cost_tracker.py:88 prices LIPSYNC_SYNCSOV3 at 0.05; cost_tracker.py:96 prices LIPSYNC_DEFAULT at 0.05; cost_tracker.py:400 looks up api_name.upper() in API_COST_USD; test_postprocess_audio_propagation.py:378 adds the live apply_correction regression.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_propagation.py::TestApplyCorrectionFlagPropagation::test_lip_sync_variant_records_namespaced_lipsync_cost -q
→ 1 passed in 1.85s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_propagation.py tests/unit/test_cost_tracker.py -q
→ 95 passed, 2 warnings in 3.08s

$ env -u GIT_INDEX_FILE .venv/bin/python - <<'PY'
# mutation/non-vacuity probe: run the live apply_correction path once with the
# real helper, once with the old bare-engine behavior.
PY
→ real helper: (True, 0.05, ('LIPSYNC_SYNCSOV3', 'lipsync', 'shot_1_0', 'proj_1', 0.05))
→ old bare-engine helper: (True, 0.0, ('SYNCSOV3', 'lipsync', 'shot_1_0', 'proj_1', 0.0))
→ default engines map to: LIPSYNC_default -> 0.05

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py ARCHITECTURE.md
→ All anchors checked — no drift.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
→ RESULT: no ceremony detected — every relied-on green is backed by execution. OK. Existing advisory warnings only: PROGRAM-MANUAL doc-anchor drift and two historical unknown-kind mailbox filenames.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
→ exit 1 as expected for the still-open wave: Wave 2 gate UNMET counts={'verified': 16, 'open': 14}; executable selectors: 19. The pytest command now includes tests/unit/test_postprocess_audio_propagation.py::TestApplyCorrectionFlagPropagation::test_lip_sync_variant_records_namespaced_lipsync_cost and does not include tests/unit/test_discovery_cost_xfail.py. Remaining failures are the known open rows plus no-selector/product-oracle blockers.

## Findings
1. INFORMATIONAL — cinema/shots/controller.py:214 — _lipsync_cost_api_key normalizes raw cascade engines to the LIPSYNC_* pricing namespace, and CostTracker uppercases the key before API_COST_USD lookup; blank/missing cascade metadata maps to priced LIPSYNC_DEFAULT. — no action.
2. INFORMATIONAL — cinema/shots/controller.py:1874 and cinema/shots/controller.py:2476 — motion F1b and postprocess lip_sync cost records now share the same helper, matching the verify-request scope. — no action.
3. INFORMATIONAL — tests/unit/test_postprocess_audio_propagation.py:378 — the regression exercises the production apply_correction("lip_sync") call site; the mutation probe proves the old bare-engine behavior still records $0.00. — no action.

## Scope-match
Landed diff matches the director2 verify-request for Pair-B row lipsync-postproc-costkey. This row is MAJOR, not CRITICAL cross-cutting; no active lock release is required. Coordinator may reconcile the row from open to verified on this GO.

Cursor at send: 2026-06-15T11:40:34Z
