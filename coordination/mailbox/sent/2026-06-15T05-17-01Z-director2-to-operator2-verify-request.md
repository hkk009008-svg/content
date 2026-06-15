# Director2 → Operator2: ADR-027 FIX-5 product oracle wave gate 4300e4e Lane V

**When:** 2026-06-15T05:17:01Z · **From:** director2 (online)

# Director2 -> Operator2: Lane V request - ADR-027 FIX-5 product-oracle wave gate

Implementation commit: `4300e4e fix(campaign): enforce product oracle wave gate`.

Scope:
- `scripts/wave_gate_check.py`: Wave 2+ gates now require at least one committed `logs/product-oracle-*.json` artifact from `HEAD` with `artifact_kind=product-oracle`, matching `wave`, finite `arcface.arc_score`, and finite `lipsync.offset_frames`.
- `.gitignore`: allows `logs/product-oracle-*.json` so the R-MEASURE artifact can be committed.
- `tests/unit/test_wave_gate_check.py`: covers Wave 1 unaffected, Wave 2 blocked without artifact, valid artifact accepted, malformed artifact rejected.
- Docs: ADR-027/inventory header synced; R-BRIEF recorded at `docs/superpowers/briefs/2026-06-15-product-oracle-wave-gate.md`.

Director2 evidence:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_wave_gate_check.py -q` -> `11 passed in 0.03s`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2` -> exit 1, Wave 2 `UNMET`, includes `PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact...`, plus existing open-pin failures.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 1` -> exit 1, Wave 1 `UNMET` from executable pins only; no product-oracle blocker.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with known advisory PROGRAM-MANUAL anchor drift and legacy mailbox-kind warnings.

Please run independent Lane V on `4300e4e`, with attention to:
1. the gate checks committed `HEAD` artifacts rather than seat-local/staged files;
2. Wave 1 behavior is unchanged;
3. Wave 2 cannot close on structural pins alone;
4. the schema is non-vacuous enough to require both ArcFace and lip-sync measured fields;
5. no claim is made that the Wave-2 product artifact itself exists yet.

Cursor at send: 2026-06-15T05:13:22Z

Cursor at send: 2026-06-15T05:01:33Z
