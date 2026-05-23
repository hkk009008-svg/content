#!/usr/bin/env python3
"""Single source of truth for the ARCHITECTURE.md §15 smoke invariants.

Verifies the four runtime-executable §15 invariants in one runnable script.
Mirrored from / supersedes the inline Python blocks previously duplicated in
ARCHITECTURE.md §15, OPERATIONS.md §7, docs/HANDOFF-roadmap-2026-05-24.md
Session 1 pre-work, and .github/workflows/ci.yml. Those references now point
here so the spec changes in one place.

Invariants verified (subset of ARCHITECTURE.md §15's prose list — the
runtime-executable ones):

  - §15.2  `import cinema_pipeline` succeeds (Python 3.13 PEP 604 + the
           orchestrator's import graph stays composable).
  - §15.5  `phase_c_vision._get_shared_validator()` is a stable singleton
           across calls.
  - §15.6  All four access paths return the same IdentityValidator instance
           (identity.get_shared_validator, phase_c_vision._get_shared_validator,
           face_validator_gate._get_validator, performance.identity_gate._get_validator).
  - §15.7  PipelineContext.global_settings plumbs through get_project_setting
           (the historical getattr(settings, ...) silent-failure bug stays fixed).
  - §15.8  phase_c_assembly.generate_ai_broll is importable (image-gen surface).

Invariants NOT covered by this script (the prose §15 list also includes):

  - §15.1  All `.py` files compile cleanly on Python 3.13 — verified by
           pytest collection + CI's pytest job.
  - §15.3  `LLMEnsemble()` instantiates — not exercised here; covered
           implicitly by import + tested in tests/unit/test_llm_caching.py.
  - §15.4  `import identity.validator` does NOT pull `phase_c_vision`
           (lazy import) — would need a fresh subprocess to verify; out of
           scope for a fast smoke script.
  - §15.9  `cinema/pipeline.py:CinemaPipeline` has zero production callers
           — static check, not runtime.

Usage:
    .venv/bin/python scripts/ci_smoke.py    # local
    python scripts/ci_smoke.py              # CI (after pip install)

Exit codes:
    0 — invariants hold
    1 — assertion failed (an invariant broke)
   >1 — script error (import-time failure, etc.)
"""
from __future__ import annotations

import os
import sys

# Bootstrap sys.path so we can import from the repo root regardless of CWD
# (matches the pattern in scripts/verify_llm_caching.py + calibrate_motion_floor.py).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def main() -> int:
    import cinema_pipeline  # noqa: F401  — §15.2
    from cinema.context import PipelineContext, get_project_setting
    from phase_c_vision import _get_shared_validator
    from phase_c_assembly import generate_ai_broll  # noqa: F401  — §15.8
    from identity import get_shared_validator
    from face_validator_gate import _get_validator as fvg_get
    from performance.identity_gate import _get_validator as pig_get

    # §15.5 + §15.6 — singleton across 4 access paths + idempotent.
    a, b = _get_shared_validator(), _get_shared_validator()
    c, d = get_shared_validator(), fvg_get()
    e = pig_get()
    assert a is b is c is d is e, "singleton broken"

    # §15.7 — project-setting plumbing (the getattr(settings,...) bug stays dead).
    ctx = PipelineContext(global_settings={"tts_provider": "CARTESIA_SONIC_2"})
    assert get_project_setting(ctx, "tts_provider") == "CARTESIA_SONIC_2"

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
