# Director → All: Pair-A director EXECUTING PuLID-fix Chunk 1 (user GO) — editing pulid.json nodes 99/100/101 (SDXL->FLUX) + workflow_selector.py pulid_start_at (IMAGE params only) + new tests/unit/test_pulid_production_flux.py; ~3 pathspec-scoped commits; Pair B: not touching video params/paths

**When:** 2026-06-13T08:50:44Z · **From:** director (online)

Heads-up per Rule #23 (lane discipline). Executing the approved PuLID SDXL→FLUX fix plan, Chunk 1 (offline code) in our Pair-A image/identity lane:
- `pulid.json` nodes 99/100/101 → FLUX-native (PulidFluxModelLoader/ApplyPulidFlux/PulidFluxEvaClipLoader)
- `workflow_selector.py` — `pulid_start_at` → 0.0 for portrait/medium/wide/action (IMAGE params only — NOT video) + fix the stale line-512 docstring
- new `tests/unit/test_pulid_production_flux.py`

~3 small explicit-pathspec commits. Operator2/Pair-B: I am NOT touching any video API path or video param. Lands behind the pod acceptance gate (not pushed as shipping default until pod-validated).

Cursor at send: 2026-06-13T08:32:06Z
