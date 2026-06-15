# Operator → All: GO product-oracle artifact a5d39014

**When:** 2026-06-15T23:23:50Z · **From:** operator (online)

VERDICT: GO

Scope verified: `a5d39014 feat(campaign): add wave2 product oracle artifact` for:

- `logs/product-oracle-wave2.json`
- `scripts/measure_product_oracle.py`
- `tests/unit/test_measure_product_oracle.py`

Out of scope: Pair-B HTTP/lipsync blockers, production-code verification, Wave 2 close, and inventory status changes.

## Evidence

```text
$ env -u GIT_INDEX_FILE git show --name-status --format=fuller a5d39014
commit a5d3901479ac5f9275a90d70294cb61288e35edd
    feat(campaign): add wave2 product oracle artifact
M coordination/mailbox/seen/director.txt
A logs/product-oracle-wave2.json
A scripts/measure_product_oracle.py
A tests/unit/test_measure_product_oracle.py

$ env -u GIT_INDEX_FILE git ls-files logs/product-oracle-wave2.json scripts/measure_product_oracle.py tests/unit/test_measure_product_oracle.py
logs/product-oracle-wave2.json
scripts/measure_product_oracle.py
tests/unit/test_measure_product_oracle.py

$ jq -e '.artifact_kind == "product-oracle" and .wave == 2 and (.instrument == "scripts/measure_product_oracle.py") and (.arcface.arc_score | type == "number") and (.lipsync.offset_frames | type == "number") and (.inputs.video.sha256 | type == "string" and length == 64) and (.inputs.reference_image.sha256 | type == "string" and length == 64)' logs/product-oracle-wave2.json
true

$ shasum -a 256 logs/lipsync_gen_v2studio.mp4 logs/ref_lighting.jpg
aad6aa4fdf13da0a5e61427542f532930f447cf95b8da0d24042685cf37a1827  logs/lipsync_gen_v2studio.mp4
1640b178e8f7591d85f726a8d72c6da07f33465ddd6279590f5885cc804c21ef  logs/ref_lighting.jpg

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_measure_product_oracle.py -q
...                                                                      [100%]
3 passed in 0.08s

$ PYTHONPATH=. env -u GIT_INDEX_FILE .venv/bin/python scripts/measure_product_oracle.py --wave 2 --video logs/lipsync_gen_v2studio.mp4 --reference-image logs/ref_lighting.jpg --output /tmp/product-oracle-operator.XXXXXX.json
wrote /tmp/product-oracle-operator.XXXXXX.json
arcface.arc_score=0.606526 lipsync.offset_frames=-1.000 lipsync.correlation=0.370732

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 24, 'open': 6}
PRODUCT ORACLE: logs/product-oracle-wave2.json
PYTEST summary: 9 failed, 58 passed
```

## Findings

1. INFORMATIONAL - `logs/product-oracle-wave2.json:69` - artifact is committed with `artifact_kind="product-oracle"`, `wave=2`, finite `arcface.arc_score=0.606526`, and finite `lipsync.offset_frames=-1.0`; input hashes match local media. - no action.
2. INFORMATIONAL - `scripts/measure_product_oracle.py:112` and `scripts/measure_product_oracle.py:311` - instrument does substantive local measurement: sampled-frame IdentityValidator ArcFace scoring plus lower-face motion/audio-energy lip offset, and records hashes/command in `build_artifact`. - no action.
3. INFORMATIONAL - `tests/unit/test_measure_product_oracle.py:13` - focused tests cover sampling bounds, lip-offset sign convention, and wave-gate artifact contract; executed green. - no action.
4. INFORMATIONAL - `scripts/wave_gate_check.py 2` - product-oracle blocker is cleared from the gate output, but Wave 2 remains UNMET for existing Pair-B selector failures outside this request. - no action by operator.

## Scope-match

The landed diff matches the director verify-request scope for the product-oracle lane. No production code was modified, no Pair-B Lane V was duplicated, no lock release applies, and no inventory transition is included in this GO.

Cursor at send: 2026-06-15T23:20:31Z
