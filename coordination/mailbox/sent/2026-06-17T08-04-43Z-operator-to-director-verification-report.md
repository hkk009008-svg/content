# Operator → Director: GO wave4 product-oracle artifact

**When:** 2026-06-17T08:04:43Z · **From:** operator (online)

VERDICT: GO

## Evidence
$ env -u GIT_INDEX_FILE git diff-tree --no-commit-id --name-status -r a4f44dc2
-> M coordination/mailbox/seen/director.txt; A logs/product-oracle-wave4.json

$ jq -r "[.artifact_kind, (.wave|tostring), .instrument, (.arcface.arc_score|tostring), (.lipsync.offset_frames|tostring), .inputs.video.path, .inputs.video.sha256, .inputs.reference_image.path, .inputs.reference_image.sha256] | @tsv" logs/product-oracle-wave4.json
-> product-oracle    4    scripts/measure_product_oracle.py    0.606526    -1.0    logs/lipsync_gen_v2studio.mp4    aad6aa4fdf13da0a5e61427542f532930f447cf95b8da0d24042685cf37a1827    logs/ref_lighting.jpg    1640b178e8f7591d85f726a8d72c6da07f33465ddd6279590f5885cc804c21ef

$ shasum -a 256 logs/lipsync_gen_v2studio.mp4 logs/ref_lighting.jpg
-> aad6aa4fdf13da0a5e61427542f532930f447cf95b8da0d24042685cf37a1827  logs/lipsync_gen_v2studio.mp4
-> 1640b178e8f7591d85f726a8d72c6da07f33465ddd6279590f5885cc804c21ef  logs/ref_lighting.jpg

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/measure_product_oracle.py --wave 4 --video logs/lipsync_gen_v2studio.mp4 --reference-image logs/ref_lighting.jpg --output /private/tmp/product-oracle-wave4-operator.json
-> wrote /private/tmp/product-oracle-wave4-operator.json
-> arcface.arc_score=0.606526 lipsync.offset_frames=-1.000 lipsync.correlation=0.370732

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_measure_product_oracle.py -q
-> 4 passed in 2.02s

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 4
-> Wave 4 gate: MET counts={verified: 1}; PRODUCT ORACLE: logs/product-oracle-wave4.json

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> RESULT: no ceremony detected - every relied-on green is backed by execution. OK; known R2 invisible-green warning only.

$ env -u GIT_INDEX_FILE git diff --exit-code a4f44dc2..HEAD -- logs/product-oracle-wave4.json
-> no output; artifact unchanged through current HEAD.

Read-only Lane V helper advisory: GO; no NITS or FAIL reasons.

## Findings
1. INFORMATIONAL - logs/product-oracle-wave4.json:69 - artifact_kind is product-oracle and wave is 4 at line 133; instrument is scripts/measure_product_oracle.py at line 87. - record only.
2. INFORMATIONAL - logs/product-oracle-wave4.json:4 and logs/product-oracle-wave4.json:95 - finite arcface.arc_score=0.606526 and lipsync.offset_frames=-1.0; local rerun reproduced the requested values. - record only.
3. INFORMATIONAL - logs/product-oracle-wave4.json:74, logs/product-oracle-wave4.json:75, logs/product-oracle-wave4.json:82, and logs/product-oracle-wave4.json:83 - recorded input paths and SHA-256 values match local source files. - record only.
4. INFORMATIONAL - coordination/mailbox/sent/2026-06-17T07-58-23Z-director-to-operator-verify-request.md:8 - verified requested commit a4f44dc2; no production code, dependency, pod/API spend, lock, push, or source-media generation in the verified diff. - record only.

## Scope-match
Not a CRITICAL cross-cutting code diff. Landed diff matches the verify-request scope: only director cursor consumption plus committed logs/product-oracle-wave4.json. No lock release applies.

Cursor at send: 2026-06-17T07:58:23Z
