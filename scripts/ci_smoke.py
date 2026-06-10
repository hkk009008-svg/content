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
from pathlib import Path

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

    # Doc-anchor drift gate (§ check_doc_claims Phase-1).
    # Hard-fail locally; warn-only in CI.
    import check_doc_claims as _cdc

    _repo_root = Path(_REPO_ROOT)
    _drifts = _cdc.run(["ARCHITECTURE.md"], _repo_root)
    if _drifts:
        _n = len(_drifts)
        if os.environ.get("CI"):
            print(
                f"WARNING: {_n} doc-anchor drift(s) found (non-blocking in CI; "
                f"run .venv/bin/python scripts/check_doc_claims.py --fix to repair)"
            )
            for _d in _drifts:
                print(f"  [{_d.kind}] {_d.target_file}:{_d.target_line} — {_d.message}")
        else:
            print(f"\nDOC-ANCHOR DRIFT: {_n} issue(s) found in ARCHITECTURE.md")
            for _d in _drifts:
                _hint = f"  → suggested line {_d.suggested_line}" if _d.suggested_line else ""
                print(f"  [{_d.kind}] {_d.target_file}:{_d.target_line}{_hint}")
                print(f"    {_d.message}")
            print(
                "\nRun: .venv/bin/python scripts/check_doc_claims.py --fix"
            )
            return 1

    # PROGRAM-MANUAL anchor-drift WARN (never a hard-fail): the ungated manual
    # decays at code-churn rate (STRATEGIC_REVIEW-2026-06-10 NF-5 / P2-2 —
    # warn-in-smoke + fix-on-touch). The hard gate above stays
    # ARCHITECTURE.md-only by design. Advisory kinds (ambiguous_path etc.)
    # are excluded — they are exit-neutral in the CLI too.
    _manual_drifts, _ = _cdc._split_advisories(
        _cdc.run(["docs/PROGRAM-MANUAL.md"], _repo_root)
    )
    if _manual_drifts:
        _mn = len(_manual_drifts)
        print(
            f"WARNING: {_mn} doc-anchor drift(s) in docs/PROGRAM-MANUAL.md "
            f"(advisory; fix-on-touch: .venv/bin/python "
            f"scripts/check_doc_claims.py --fix docs/PROGRAM-MANUAL.md)"
        )
        for _d in _manual_drifts[:5]:
            print(f"  [{_d.kind}] {_d.target_file}:{_d.target_line} — {_d.message}")
        if _mn > 5:
            print(f"  ... and {_mn - 5} more")

    # Manifest drift WARN (never a hard-fail — manifest is not auto-fixable).
    _manifest_drifts = _cdc.check_manifest(
        _repo_root / "docs" / "pipeline_status.toml", _repo_root
    )
    if _manifest_drifts:
        _mn = len(_manifest_drifts)
        print(
            f"WARNING: {_mn} stale manifest claim(s) in docs/pipeline_status.toml"
            f" (edit the manifest):"
        )
        for _md in _manifest_drifts:
            print(f"  {_md.message}")

    # Commit-SHA ref drift WARN (git-backed; never a hard-fail — shallow clones
    # skip reachability, and SHA drift is not auto-fixable).
    _sha_drifts = _cdc.check_sha_refs(_cdc.SHA_DEFAULT_DOCS, _repo_root)
    if _sha_drifts:
        _sn = len(_sha_drifts)
        print(
            f"WARNING: {_sn} stale commit-SHA ref(s) in docs"
            f" (run .venv/bin/python scripts/check_doc_claims.py --sha-refs):"
        )
        for _sd in _sha_drifts:
            print(
                f"  [{_sd.kind}] {Path(_sd.doc_path).name}:{_sd.doc_line}"
                f" (sha: {_sd.symbol}) — {_sd.message}"
            )

    # Coordination-state gate (protocol v6.0, § check_coordination).
    # FATAL (broken cursor / filename-convention violation) hard-fails locally,
    # warns in CI; ADVISORY warns everywhere; INFO (unread counts) is silent
    # here — the CLI prints it.
    import check_coordination as _cc

    _coord_issues = _cc.run(_repo_root / "coordination")
    _coord_fatal = [_i for _i in _coord_issues if _i.severity == "FATAL"]
    _coord_adv = [_i for _i in _coord_issues if _i.severity == "ADVISORY"]
    for _i in _coord_adv:
        print(f"WARNING: coordination ADVISORY [{_i.kind}] {_i.path} — {_i.message}")
    if _coord_fatal:
        for _i in _coord_fatal:
            print(f"COORDINATION FATAL [{_i.kind}] {_i.path} — {_i.message}")
        if not os.environ.get("CI"):
            print("\nRun: .venv/bin/python scripts/check_coordination.py")
            return 1
        print("WARNING: coordination FATALs are non-blocking in CI")

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
