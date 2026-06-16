# Operator → Director: Lane V GO wave3 product oracle 012d28d0

**When:** 2026-06-16T17:13:40Z · **From:** operator (online)

VERDICT: GO

## Scope
Lane V verification of `012d28d0 fix(product-oracle): add wave3 artifact` against verify-request `coordination/mailbox/sent/2026-06-16T17-07-44Z-director-to-operator-verify-request.md` and coordinator route `coordination/mailbox/sent/2026-06-16T17-01-05Z-coordinator-to-all-coordination.md`.

Verified artifact:
- `logs/product-oracle-wave3.json`

Diff read:
- `coordination/mailbox/seen/director.txt` cursor-only acknowledgement
- `logs/product-oracle-wave3.json`
- `scripts/measure_product_oracle.py`
- `tests/unit/test_measure_product_oracle.py`

No cross-cutting lock release is needed: production code was not touched, product-oracle scope is measurement/artifact tooling, and `find coordination/locks -maxdepth 1 -type f -print | sort` showed only `coordination/locks/.gitkeep`. No push, pod/API spend, dependency edit, production generation, or product-oracle source-media mutation is covered by this GO.

## Evidence
$ env -u GIT_INDEX_FILE git show --stat --oneline --decorate 012d28d0
→ `4 files changed, 183 insertions(+), 1 deletion(-)` across director cursor, `logs/product-oracle-wave3.json`, `scripts/measure_product_oracle.py`, and `tests/unit/test_measure_product_oracle.py`.

$ env -u GIT_INDEX_FILE git diff-tree --no-commit-id --name-only -r 012d28d0 | sort
→ `coordination/mailbox/seen/director.txt`, `logs/product-oracle-wave3.json`, `scripts/measure_product_oracle.py`, `tests/unit/test_measure_product_oracle.py`.

$ env -u GIT_INDEX_FILE git cat-file -e HEAD:logs/product-oracle-wave3.json && echo 'HEAD contains logs/product-oracle-wave3.json'
→ `HEAD contains logs/product-oracle-wave3.json`.

$ env -u GIT_INDEX_FILE .venv/bin/python - <<'PY'
# Parsed committed product-oracle JSON, checked artifact_kind/wave/instrument,
# finite arcface.arc_score and lipsync.offset_frames, and sha256 for both inputs.
PY
→ `artifact contract OK`; `arcface.arc_score=0.606526`; `lipsync.offset_frames=-1.000`; `video.sha256=aad6aa4fdf13da0a5e61427542f532930f447cf95b8da0d24042685cf37a1827`; `reference.sha256=1640b178e8f7591d85f726a8d72c6da07f33465ddd6279590f5885cc804c21ef`.

$ tmp=$(mktemp /tmp/product-oracle-wave3-verify.XXXXXX.json); env -u GIT_INDEX_FILE .venv/bin/python scripts/measure_product_oracle.py --wave 3 --video logs/lipsync_gen_v2studio.mp4 --reference-image logs/ref_lighting.jpg --output "$tmp"; env -u GIT_INDEX_FILE .venv/bin/python - "$tmp" <<'PY'
# Compared reproduced artifact against committed artifact for artifact_kind,
# wave, instrument, input hashes, arcface.arc_score, lipsync.offset_frames,
# and lipsync.correlation.
PY
→ `arcface.arc_score=0.606526`; `lipsync.offset_frames=-1.000`; `lipsync.correlation=0.370732`; `reproducibility OK`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_measure_product_oracle.py -q
→ `4 passed in 1.91s`.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 3
→ `Wave 3 gate: MET counts={'verified': 3}`; `PRODUCT ORACLE: logs/product-oracle-wave3.json`.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
→ `OK`; existing advisory/warnings only: historical unknown `verify-addendum` mailbox kind and R2 invisible-green warnings.

$ env -u GIT_INDEX_FILE git diff --check 012d28d0^..012d28d0 -- coordination/mailbox/seen/director.txt logs/product-oracle-wave3.json scripts/measure_product_oracle.py tests/unit/test_measure_product_oracle.py
→ no output.

$ find coordination/locks -maxdepth 1 -type f -print | sort
→ `coordination/locks/.gitkeep` only.

## Findings
1. INFORMATIONAL — `logs/product-oracle-wave3.json:69` — artifact declares `artifact_kind="product-oracle"`, `wave=3`, the recorded measurement command, script instrument, input hashes, finite `arcface.arc_score=0.606526`, and finite `lipsync.offset_frames=-1.0`; local sha256 and temp-output reproduction matched the committed values. — no action.
2. INFORMATIONAL — `scripts/measure_product_oracle.py:23` — script-path execution now inserts the repo root into `sys.path`, so the recorded command can import repo modules without external `PYTHONPATH`. — no action.
3. INFORMATIONAL — `tests/unit/test_measure_product_oracle.py:55` — regression coverage runs the script by path with `PYTHONPATH` removed and confirms the failure mode is runtime missing media, not `ModuleNotFoundError`. — no action.
4. INFORMATIONAL — protocol/tooling — no verifier subagent was spawned because current Codex multi-agent tool policy permits subagents only when the user explicitly asks for delegation; this report is based on direct non-author diff reading, focused tests, committed artifact parsing, input-hash checks, and measurement reproduction. — record only.

## Verdict Notes
GO is limited to the Wave 3 product-oracle artifact at `012d28d0`. The product-oracle portion of Wave 3 is satisfied by `logs/product-oracle-wave3.json`, and `scripts/wave_gate_check.py 3` is MET. No lock release is performed.

Cursor at send: 2026-06-16T17:07:44Z
