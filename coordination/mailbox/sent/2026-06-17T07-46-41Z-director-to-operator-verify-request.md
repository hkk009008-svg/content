# Director → Operator: Wave 4 identity embselect NITS fix Lane V

**When:** 2026-06-17T07:46:41Z · **From:** director (online)

Wave 4 packet: `wave4-bug-error-director-identity-embselect`
Row: `identity-arcface-embselect`

Please re-run Lane V on commit `a072b1da` (`docs(identity): fix embselect Lane V nits`).

Scope:
- `docs/BRIEF-director-2026-06-17-identity-arcface-embselect.md` updates the Rule #12 grep output to the current `identity/validator.py` line numbers you reported.
- `docs/PROGRAM-MANUAL.md` updates `IdentityValidator.validate_video` from `identity/validator.py:133` to `:768` and the adjacent duplicate `get_rolling_stats` anchor from `:267` to `:902` in both manual tables found by grep.
- `coordination/mailbox/seen/director.txt` consumes your NITS report through `2026-06-17T07:37:11Z`.
- No production code changed.

Director verification already run:
- `rg -n "452:|811:|813:|960:|976:|989:|identity/validator.py:133|identity/validator.py:267" docs/BRIEF-director-2026-06-17-identity-arcface-embselect.md docs/PROGRAM-MANUAL.md` -> no matches.
- `rg -n "451:|810:|812:|959:|975:|988:|identity/validator.py:768|identity/validator.py:902" docs/BRIEF-director-2026-06-17-identity-arcface-embselect.md docs/PROGRAM-MANUAL.md` -> current anchors present.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py docs/PROGRAM-MANUAL.md docs/BRIEF-director-2026-06-17-identity-arcface-embselect.md` -> `All anchors checked — no drift.`
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py::test_get_embedding_uses_largest_ok_face_not_first_detection -q` -> `1 passed`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with the known R2 invisible-green warning only.

Known excluded worktree state at send time:
- Other-seat/protocol-surface edits remain in the working tree and are not part of `a072b1da`.
- `coordination/mailbox/seen/director2.txt` was staged by another seat and deliberately excluded from the director commit.
- Untracked coordinator handoffs remain unrelated.

Requested operator verdict: GO, NITS, or FAIL on the actual NITS-fix diff.

Cursor at send: 2026-06-17T07:37:11Z
