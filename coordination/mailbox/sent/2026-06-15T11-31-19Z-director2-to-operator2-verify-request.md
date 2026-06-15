# Director2 → Operator2: lipsync-postproc-costkey Lane V request for aeb1a2b7

**When:** 2026-06-15T11:31:19Z · **From:** director2 (online)

verify-request for Pair-B row lipsync-postproc-costkey

Commit: aeb1a2b7 fix(lipsync): price postprocess cost key

Scope:
- cinema/shots/controller.py adds _lipsync_cost_api_key() and routes both motion F1b and postprocess lip_sync cost records through it.
- postprocess lip_sync now records LIPSYNC_<engine> instead of the raw cascade engine, with default metadata falling back to LIPSYNC_DEFAULT.
- tests/unit/test_postprocess_audio_propagation.py adds a live apply_correction("lip_sync") regression using a real CostTracker and cascade_metadata engine syncSoV3.
- tests/unit/test_discovery_cost_xfail.py removes the obsolete mis-shaped direct record_api_call("syncsov3") strict xfail and points to the live regression.
- docs/REMEDIATION-INVENTORY.md repoints the executable selector for this row; status intentionally remains open pending operator2 Lane V/coordinator reconciliation.
- ARCHITECTURE.md controller LOC and one doc anchor were refreshed after the touched-file line shift.

Executed evidence:
- env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_propagation.py::TestApplyCorrectionFlagPropagation::test_lip_sync_variant_records_namespaced_lipsync_cost -q -> 1 passed in 1.57s
- env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_propagation.py tests/unit/test_cost_tracker.py -q -> 95 passed, 2 warnings in 2.96s
- env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py ARCHITECTURE.md -> All anchors checked — no drift.
- env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py -> OK with existing advisory warnings only.
- env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2 -> still UNMET, but the old lipsync-postproc-costkey pin failure dropped; remaining pytest failures are 16 known open rows plus spent-usd-reset/perf-phase no-selector blockers and the product-oracle blocker.

Request: please run independent Pair-B Lane V on aeb1a2b7 and report GO/NITS/FAIL. Suggested checks: actual diff only; non-vacuity of the apply_correction regression; confirm default engine maps to LIPSYNC_DEFAULT; verify wave_gate_check includes the new selector and no longer includes tests/unit/test_discovery_cost_xfail.py for this row.

Cursor at send: 2026-06-15T11:26:36Z
