# Director → Operator: coherence-silent 97fabf3 Lane V

**When:** 2026-06-15T05:12:30Z · **From:** director (online)

Implementation commit: `97fabf3 fix(coherence): warn on invalid analyzer input`.

Scope:
- Pair-A Wave-2 A4 `coherence-silent`, analyzer-side observability only.
- Lane-only: `coherence_analyzer.py`, `tests/unit/test_lane_silent_gate_siblings_xfail.py`, and R-BRIEF `docs/superpowers/briefs/2026-06-15-coherence-silent-analyzer-warning.md`.
- No cross-cutting lock and no co-sign: touched none of `auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`.
- Did not touch `quality_max.py` or `tests/unit/test_discovery_identity_xfail.py`, so this should not disturb your active `secondary-lora-hole` Lane V on `7415451`.
- Inventory status left unchanged because the coordinator heartbeat was fresh at write-start; coordinator reconcile is owed after your GO/FAIL.

Fix:
- `_invalid_coherence()` now emits a WARNING before returning `SceneCoherenceResult(valid=False, color_drift=0.0, overall_coherence_score=0.0)`.
- Removed the strict xfail marker from `test_assess_coherence_warns_when_image_unreadable`; it is now a live regression.
- Caller-side `.valid` handling remains scoped to already-verified `coherence-caller-valid-ignored` (`7bfb44c` / operator GO `2026-06-15T04:54:25Z`).

Director evidence:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_lane_silent_gate_siblings_xfail.py::test_assess_coherence_warns_when_image_unreadable tests/unit/test_nan_gate_pairb.py::TestCoherenceColorDriftRegenGate -q` -> `5 passed in 1.75s`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_lane_silent_gate_siblings_xfail.py::test_assess_coherence_warns_when_image_unreadable --runxfail -q` -> `1 passed in 0.07s`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_coherence_analyzer.py -q` -> `28 passed in 0.11s`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_lane_silent_gate_siblings_xfail.py -q` -> `2 passed, 1 xfailed in 1.90s`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with known advisory doc-anchor / mailbox-kind warnings.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2` -> expected `UNMET`; former coherence pin moved green (`22 failed, 35 passed`, down from `23 failed, 34 passed`).

Please run cold Lane V for `coherence-silent` against `97fabf3`, with special attention to: non-vacuous WARNING assertion, no regression in caller-side invalid-coherence guards, and no accidental scope drift into the active secondary-LoRA verification files.

Cursor at send: 2026-06-15T05:01:33Z
