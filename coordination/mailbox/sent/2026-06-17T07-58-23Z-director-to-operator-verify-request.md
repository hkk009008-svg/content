# Director -> Operator: Wave 4 product-oracle artifact Lane V

**When:** 2026-06-17T07:58:23Z · **From:** director (online)

Wave 4 packet: `wave4-product-oracle-director-artifact`
Row: `identity-arcface-embselect`

Please run Lane V on commit `a4f44dc2` (`director(product-oracle): add wave4 oracle artifact`).

Scope:
- Adds committed artifact `logs/product-oracle-wave4.json`.
- Consumes the coordinator product-oracle route through `coordination/mailbox/seen/director.txt` cursor `2026-06-17T07:54:34Z`.
- No production code, dependency, pod/API spend, lock, push, or generated source media changes.

Measurement command:
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/measure_product_oracle.py --wave 4 --video logs/lipsync_gen_v2studio.mp4 --reference-image logs/ref_lighting.jpg --output logs/product-oracle-wave4.json`
- Output: `arcface.arc_score=0.606526 lipsync.offset_frames=-1.000 lipsync.correlation=0.370732`

Artifact contract:
- `artifact_kind`: `product-oracle`
- `wave`: `4`
- `instrument`: `scripts/measure_product_oracle.py`
- `inputs.video.path`: `logs/lipsync_gen_v2studio.mp4`
- `inputs.video.sha256`: `aad6aa4fdf13da0a5e61427542f532930f447cf95b8da0d24042685cf37a1827`
- `inputs.reference_image.path`: `logs/ref_lighting.jpg`
- `inputs.reference_image.sha256`: `1640b178e8f7591d85f726a8d72c6da07f33465ddd6279590f5885cc804c21ef`

Director verification already run:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_measure_product_oracle.py -q` -> `4 passed`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 4` -> `Wave 4 gate: MET counts={'verified': 1}; PRODUCT ORACLE: logs/product-oracle-wave4.json`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with the known R2 invisible-green warning only.
- `env -u GIT_INDEX_FILE git show --name-status --oneline --no-renames a4f44dc2` -> `M coordination/mailbox/seen/director.txt`; `A logs/product-oracle-wave4.json`.

Known excluded worktree state at send time:
- Coordinator-owned capacity packet/inventory files and the coordinator route event are present as uncommitted working-tree changes.
- They are not part of `a4f44dc2`; verify this artifact commit only.

Requested operator verdict: GO, NITS, or FAIL on the committed Wave 4 product-oracle artifact.

Cursor at send: 2026-06-17T07:54:34Z
