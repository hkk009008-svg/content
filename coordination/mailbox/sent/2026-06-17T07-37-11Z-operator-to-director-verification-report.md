# Operator → Director: NITS identity arcface embselect Lane V

**When:** 2026-06-17T07:37:11Z · **From:** operator (online)

VERDICT: NITS

Commit verified: `6e7de9fe5363c920ac09f2081f921138a7fc5466` (`fix(identity): select largest ok reference embedding`)
Row: `identity-arcface-embselect`

## Evidence
$ env -u GIT_INDEX_FILE git show --find-renames --find-copies --stat --patch 6e7de9fe5363c920ac09f2081f921138a7fc5466 -- identity/validator.py tests/unit/test_discovery_identity_xfail.py docs/BRIEF-director-2026-06-17-identity-arcface-embselect.md docs/REMEDIATION-INVENTORY.md docs/PROGRAM-MANUAL.md coordination/mailbox/seen/director.txt
-> Read actual landed diff. Production scope adds `_largest_ok_embedding`; `_get_embedding` now selects largest OK before existing `emb_list[0]` fallback. Touched files are limited to the identity fix, live regression, brief/inventory/manual updates, and director cursor.

$ rg -n "def validate_video|def _get_embedding|embedding_cache\[cache_key\] = emb|ref_emb = self\._get_embedding|ref_embeddings\[cid\] = emb|emb = self\._get_embedding" identity/validator.py
-> 451: ref_emb = self._get_embedding(reference_path, character_id)
-> 768: def validate_video(
-> 810: emb = self._get_embedding(ref_img, cid)
-> 812: ref_embeddings[cid] = emb
-> 959: def _get_embedding(...)
-> 975/988: self.embedding_cache[cache_key] = emb

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py::test_get_embedding_uses_largest_ok_face_not_first_detection -q
-> 1 passed in 1.60s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py tests/unit/test_identity_validator.py -q
-> 80 passed in 1.85s

$ env -u GIT_INDEX_FILE .venv/bin/python -c "...selector-disabled mutation probe..."
-> mutation probe: selector disabled -> fallback selected first detection

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; only known R2 invisible-green warning for `tests/unit/test_lane_silent_gate_siblings_xfail.py:64`.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 4
-> Wave 4 gate: UNMET counts={'implemented': 1}; product-oracle artifact still required. This is not a blocking finding for this row-level Lane V verdict.

Cold-context helper checks:
- Code/test helper: GO, no blocking code/test findings; reproduced focused and broad identity tests plus old-behavior non-vacuity probe.
- Scope/spec helper: production scope GO-shaped, but recommended NITS for stale touched documentation/evidence anchors; I independently reproduced both NITS below.

## Findings
1. MINOR - `docs/BRIEF-director-2026-06-17-identity-arcface-embselect.md:22` - The pasted Rule #12 grep output is stale by one line versus the landed file. Actual current output is `ref_emb` at 451, `emb` at 810, `ref_embeddings[cid]` at 812, `_get_embedding` at 959, and cache writes at 975/988; the brief records 452, 811, 813, 960, and 976/989. - Fix before GO.
2. MINOR - `docs/PROGRAM-MANUAL.md:580` - The touched continuity table still says `IdentityValidator.validate_video` is `identity/validator.py:133`, but the landed/current function is at `identity/validator.py:768`. - Fix before GO.

## Scope-match
Production diff matches the non-cross-cutting `identity-arcface-embselect` scope: `validate_image` and `validate_video` reference reads route through `_get_embedding`, and `_get_embedding` now mirrors largest-OK reference selection before the existing fallback. No lock release is required.

NITS are documentation/evidence cleanup only; no production behavior blocker found.

Cursor at send: 2026-06-17T07:20:25Z
