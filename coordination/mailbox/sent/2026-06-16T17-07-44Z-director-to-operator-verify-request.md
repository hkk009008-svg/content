# Director → Operator: Wave 3 product-oracle artifact ready

**When:** 2026-06-16T17:07:44Z · **From:** director (online)

Director landed the Wave 3 product-oracle artifact and requests operator Lane V.

Commit to verify:
- `012d28d0 fix(product-oracle): add wave3 artifact`

Route:
- `coordination/mailbox/sent/2026-06-16T17-01-05Z-coordinator-to-all-coordination.md`

Artifact:
- `logs/product-oracle-wave3.json`

Implementation scope:
- `logs/product-oracle-wave3.json`
- `scripts/measure_product_oracle.py` bootstrap fix so the recorded script-path command can import repo modules without external `PYTHONPATH`
- `tests/unit/test_measure_product_oracle.py` regression for script-path execution
- `coordination/mailbox/seen/director.txt` consumed the coordinator route through `2026-06-16T17:01:05Z`

Measurement command:
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/measure_product_oracle.py --wave 3 --video logs/lipsync_gen_v2studio.mp4 --reference-image logs/ref_lighting.jpg --output logs/product-oracle-wave3.json`

Measurement output:
- `wrote logs/product-oracle-wave3.json`
- `arcface.arc_score=0.606526 lipsync.offset_frames=-1.000 lipsync.correlation=0.370732`

Director verification run before this request:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_measure_product_oracle.py -q` -> `4 passed`
- `.venv/bin/python scripts/wave_gate_check.py 3` -> `Wave 3 gate: MET counts={'verified': 3}`; `PRODUCT ORACLE: logs/product-oracle-wave3.json`
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with known historical `verify-addendum`/R2 advisories only
- `env -u GIT_INDEX_FILE git show --stat --oneline --decorate HEAD` -> `012d28d0`, 4 files changed: director cursor, artifact, script, test

No pod/API spend, dependency edit, lock claim/release, production generation, or push is included. Inputs are existing local media/reference files recorded by path and sha256 in the artifact.

Please verify the landed HEAD artifact is committed, finite, reproducible from the recorded command/input hashes, and satisfies the product-oracle portion of `scripts/wave_gate_check.py 3`. Send GO/NITS/FAIL. Push remains user-gated.

Cursor at send: 2026-06-16T17:01:05Z
