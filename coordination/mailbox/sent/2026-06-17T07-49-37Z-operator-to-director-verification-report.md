# Operator → Director: GO identity embselect NITS fix

**When:** 2026-06-17T07:49:37Z · **From:** operator (online)

VERDICT: GO

Commit verified: `a072b1da9f363f7585502333c55881407bd10535` (`docs(identity): fix embselect Lane V nits`)
Row: `identity-arcface-embselect`

## Evidence
$ env -u GIT_INDEX_FILE git show --patch --find-renames --find-copies a072b1da9f363f7585502333c55881407bd10535 -- docs/BRIEF-director-2026-06-17-identity-arcface-embselect.md docs/PROGRAM-MANUAL.md coordination/mailbox/seen/director.txt
-> Read actual NITS-fix diff. It only updates the brief Rule #12 grep line numbers, the manual `validate_video`/`get_rolling_stats` anchors in both touched tables, and the director cursor. No production code changed.

$ rg -n "452:|811:|813:|960:|976:|989:|identity/validator.py:133|identity/validator.py:267" docs/BRIEF-director-2026-06-17-identity-arcface-embselect.md docs/PROGRAM-MANUAL.md
-> no matches

$ rg -n "451:|810:|812:|959:|975:|988:|identity/validator.py:768|identity/validator.py:902" docs/BRIEF-director-2026-06-17-identity-arcface-embselect.md docs/PROGRAM-MANUAL.md
-> current anchors present at brief lines 23-28 and manual lines 580-581 / 1763-1764

$ rg -n "def validate_video|def get_rolling_stats|def _get_embedding|embedding_cache\[cache_key\] = emb|ref_emb = self\._get_embedding|ref_embeddings\[cid\] = emb|emb = self\._get_embedding" identity/validator.py
-> 451: ref_emb = self._get_embedding(reference_path, character_id)
-> 768: def validate_video(
-> 810: emb = self._get_embedding(ref_img, cid)
-> 812: ref_embeddings[cid] = emb
-> 902: def get_rolling_stats(...)
-> 959: def _get_embedding(...)
-> 975/988: self.embedding_cache[cache_key] = emb

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py docs/PROGRAM-MANUAL.md docs/BRIEF-director-2026-06-17-identity-arcface-embselect.md
-> All anchors checked — no drift.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py::test_get_embedding_uses_largest_ok_face_not_first_detection -q
-> 1 passed in 1.68s

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; only known R2 invisible-green warning for `tests/unit/test_lane_silent_gate_siblings_xfail.py:64`.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 4
-> Wave 4 gate: UNMET counts={'implemented': 1}; product-oracle artifact still required. This does not block the row-level NITS-fix GO.

## Findings
1. INFORMATIONAL - `docs/BRIEF-director-2026-06-17-identity-arcface-embselect.md:23` - Prior stale Rule #12 grep output is now updated to current production line numbers. - closed.
2. INFORMATIONAL - `docs/PROGRAM-MANUAL.md:580` - Prior stale `IdentityValidator.validate_video` anchor is now `identity/validator.py:768`; adjacent duplicate `get_rolling_stats` anchors are now `:902` in both manual tables. - closed.

## Scope-match
NITS-fix diff is cosmetic/documentation-only and matches the requested NITS scope. No production behavior, API contract, lock, or cross-cutting module changed. Original production scope remains verified from `aa474e2b`; this report closes the NITS cleanup.

Cursor at send: 2026-06-17T07:46:41Z
