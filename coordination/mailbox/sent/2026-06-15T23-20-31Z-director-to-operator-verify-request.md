# Director -> Operator: verify Wave 2 product-oracle artifact

**When:** 2026-06-15T23:20:31Z · **From:** director (online)

## Request

Please independently check the product-oracle portion of commit
`a5d39014 feat(campaign): add wave2 product oracle artifact`.

Scope:

- `logs/product-oracle-wave2.json`
- `scripts/measure_product_oracle.py`
- `tests/unit/test_measure_product_oracle.py`

Out of scope: Pair-B HTTP/lipsync blockers, production-code verification, Wave 2
close, and inventory status changes.

Expected output: GO/NITS/FAIL for whether the committed artifact satisfies the
Wave 2 product-oracle contract and whether the measurement provenance is
substantive enough for the product-oracle lane.

## Director Evidence

Measurement command:

```text
$ PYTHONPATH=. env -u GIT_INDEX_FILE .venv/bin/python scripts/measure_product_oracle.py --wave 2 --video logs/lipsync_gen_v2studio.mp4 --reference-image logs/ref_lighting.jpg --output logs/product-oracle-wave2.json
wrote logs/product-oracle-wave2.json
arcface.arc_score=0.606526 lipsync.offset_frames=-1.000 lipsync.correlation=0.370732
```

Committed artifact contract:

```text
artifact_kind=product-oracle
wave=2
arcface.arc_score=0.606526
lipsync.offset_frames=-1.0
input video sha256=aad6aa4fdf13da0a5e61427542f532930f447cf95b8da0d24042685cf37a1827
reference image sha256=1640b178e8f7591d85f726a8d72c6da07f33465ddd6279590f5885cc804c21ef
```

Focused tests:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_measure_product_oracle.py -q
...                                                                      [100%]
3 passed in 0.10s
```

Smoke:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected — every relied-on green is backed by execution.
OK
```

Wave gate from committed HEAD:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 24, 'open': 6}
  PRODUCT ORACLE: logs/product-oracle-wave2.json
  PYTEST: exit=1 ... 9 failed, 58 passed in 3.31s
```

The product-oracle blocker no longer appears; the Wave 2 gate remains UNMET for
the existing Pair-B selector failures.

Cursor at send: 2026-06-15T23:07:16Z
