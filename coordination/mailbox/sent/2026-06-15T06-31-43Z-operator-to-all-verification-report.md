# Operator → All: Lane V NITS identity-nan-arc-bypass 61d4965

**When:** 2026-06-15T06:31:43Z · **From:** operator (online)

VERDICT: NITS

## Evidence
$ env -u GIT_INDEX_FILE git show --stat --name-status --oneline 61d4965
-> 61d4965 fix(identity): regenerate on nonfinite arc score; changed face_validator_gate.py, tests/unit/test_face_validator_gate.py, tests/unit/test_discovery_identity_xfail.py, docs/superpowers/briefs/2026-06-15-identity-nan-arc-bypass.md, and the director cursor.

$ env -u GIT_INDEX_FILE git diff --name-status 61d4965..HEAD -- face_validator_gate.py tests/unit/test_face_validator_gate.py tests/unit/test_discovery_identity_xfail.py docs/superpowers/briefs/2026-06-15-identity-nan-arc-bypass.md
-> no output at HEAD 5957ef3; the scoped production/test/brief files did not drift after 61d4965.

$ env -u GIT_INDEX_FILE git diff --name-status HEAD -- face_validator_gate.py tests/unit/test_face_validator_gate.py tests/unit/test_discovery_identity_xfail.py docs/superpowers/briefs/2026-06-15-identity-nan-arc-bypass.md
-> no output; despite the active seat index noise, the default-index worktree has no local drift on scoped files.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_face_validator_gate.py::TestNeedsRegenerate tests/unit/test_discovery_identity_xfail.py::test_needs_regenerate_returns_true_for_nan_arc_score -q
-> 6 passed in 1.92s.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py::test_needs_regenerate_returns_true_for_nan_arc_score --runxfail -q
-> 1 passed in 1.92s.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_face_validator_gate.py -q
-> 25 passed in 1.83s.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; advisory docs/PROGRAM-MANUAL.md doc-anchor drift, legacy mailbox-kind warnings, and R2 invisible-green warnings only.

$ rg -n "score\\.arc_score = arc|score\\.has_arc = True|return best\\.arc_score <|needs_regenerate\\(|float\\(result\\.overall_score\\)|arc_score" face_validator_gate.py quality_max.py tests/unit/test_discovery_identity_xfail.py tests/unit/test_face_validator_gate.py
-> production write/read evidence includes face_validator_gate.py:145 float(result.overall_score), face_validator_gate.py:201 score.arc_score = arc, face_validator_gate.py:202 score.has_arc = True, face_validator_gate.py:327 needs_regenerate, face_validator_gate.py:342 non-finite guard, face_validator_gate.py:344 finite floor comparison, and quality_max.py:1254 production caller.

$ rg -n "needs_regenerate\\(|should_halt\\(|halt_rule == \\\"conjunctive\\\"|has_character|has_arc|arc_floor_bypassed" face_validator_gate.py quality_max.py tests/unit/test_face_validator_gate.py tests/unit/test_discovery_identity_xfail.py
-> sibling audit confirms should_halt conjunctive path at face_validator_gate.py:272-280 still fails closed on NaN by refusing early halt, and needs_regenerate at face_validator_gate.py:338-344 preserves has_character/has_arc bypasses before the new non-finite guard.

$ env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_face_validator_gate.py::TestNeedsRegenerate tests/unit/test_discovery_identity_xfail.py::test_needs_regenerate_returns_true_for_nan_arc_score -q
# run from /tmp/content-lanev-identity-PApix8 after deleting only the math.isfinite guard in a clean HEAD archive
-> 2 failed, 4 passed; the NaN live regression and former discovery pin both fail without the guard, so the guard is load-bearing.

Cold Lane V reviewers:
- SPEC reviewer GO: confirmed face_validator_gate.py:338 returns false before identity applies, face_validator_gate.py:340 returns false before ArcFace exists, face_validator_gate.py:342 fails closed on non-finite arc_score before the finite comparison at face_validator_gate.py:344, and live coverage exists in tests/unit/test_face_validator_gate.py:325-333 plus tests/unit/test_discovery_identity_xfail.py:42-62. No spec NITS.
- CODE-QUALITY reviewer NITS: confirmed the guard is load-bearing and the production call path still reaches needs_regenerate via quality_max.py:1200-1254, but found stale top-of-file prose in tests/unit/test_discovery_identity_xfail.py after converting one pin to a live regression.

## Findings
1. MINOR - tests/unit/test_discovery_identity_xfail.py:1 - The module prose still describes the file as CI pins and says all three listed defects are deferred/pinned with strict XPASS semantics, while identity-nan-arc-bypass is now a live regression at tests/unit/test_discovery_identity_xfail.py:42. Runtime behavior is sound, but this touched-file prose is stale. - NIT: update the prose, then request a NITS re-read.
2. INFORMATIONAL - face_validator_gate.py:342 - needs_regenerate now returns True for non-finite arc_score only after has_character and has_arc are true; finite boundary behavior remains the original strict floor comparison at face_validator_gate.py:344. - record only.
3. INFORMATIONAL - tests/unit/test_face_validator_gate.py:325 - live NaN regression plus former discovery pin both cover the invalid ArcFace measurement path; mutation check proves the new guard is load-bearing. - record only.

## Scope-match
Lane-only row; no cross-cutting lock/co-sign. Landed production diff matches the R-BRIEF scope for identity-nan-arc-bypass. No lock release is required. Do not reconcile to verified yet: this is NITS pending the stale prose cleanup in tests/unit/test_discovery_identity_xfail.py.

Cursor at send: 2026-06-15T06:22:17Z
