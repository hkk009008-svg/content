# Coordinator → All: authorized Wave 2 route: product-oracle and Pair-B locks

**When:** 2026-06-15T23:07:16Z · **From:** coordinator (online)

User-principal authorization received in the live coordinator session: `authorized.` This authorizes the side effects named in the prior coordinator report: lock-claim/push for the Wave 2 `lipsync-veto` and HTTP rows, plus product-oracle artifact write/pod/paid-API spend as needed. Treat this event as the consolidated task board; coordinator remains unpinned and consumed no cursor.

## Live Baseline At Route

- HEAD at route prep: `148a81df coord(cursor): director consume protocol notice`.
- `seat_status.py` showed all four seats at `UNREAD: 0` before this event.
- `scripts/wave_gate_check.py 2` remains UNMET: `counts={'verified': 24, 'open': 6}`, missing committed `logs/product-oracle-*.json`, and `9 failed, 58 passed` in the executed selector run.
- `scripts/ci_smoke.py` is OK with existing advisory warnings only.
- `coordination/locks/` contains only `.gitkeep`.
- `git status -sb` reports `main...origin/main [ahead 19, behind 8]` plus dirty protocol-effectiveness / handoff WIP. Do not run lock helpers over an unprotected dirty tree if their failure path could clobber WIP.

## Route Board

### director2 — Pair-B implementation owner

Task: advance the active Pair-B Wave 2 code blockers, using locks now that the user has authorized lock-claim/push side effects.

Allowed write set after a successful lock claim:
- For `lipsync-veto`: `cinema/auto_approve.py`, `tests/unit/test_postprocess_audio_siblings_xfail.py`, brief/docs/inventory as needed, mailbox verify-request.
- For HTTP cluster: `web_server.py`, `tests/unit/test_discovery_web_server_xfail.py`, brief/docs/inventory as needed, mailbox verify-request.

Lock discipline:
- First refresh git/mailbox state and protect dirty WIP. The helper `coordination/bin/claim-lock` can `git reset --hard @{u}` on push rejection; do not run it from an unsafe dirty shared tree.
- If claiming both locks in one work period, acquire in documented lexicographic order: `auto_approve.py` before `web_server.py`; hold none while waiting.
- Claim command for single-row start: `coordination/bin/claim-lock 2 cinema/auto_approve.py director2 lipsync-veto`.
- Claim command for HTTP batch once safe: `coordination/bin/claim-lock 2 web_server.py director2 http-clearperf-silent200`; the held `W2-web_server.py.lock` covers all five open HTTP rows listed below.

Required coverage:
- `lipsync-veto`: `tests/unit/test_postprocess_audio_siblings_xfail.py::test_best_take_lipsync_credits_successful_postprocess_lipsync`.
- HTTP rows: `http-clearperf-silent200`, `http-drivingvid-orphan`, `http-addchar-float-unguarded`, `http-null-json-body`, `http-styleboard-false201`.
- Rule #13 for `http-addchar-float-unguarded`: cover all four float sites, not only add-character/add-object: `api_add_character`, `api_add_object`, `api_update_character`, `api_update_object`; non-numeric and non-finite values must not become Flask 500s or NaN/inf JSON tokens.
- `http-null-json-body`: cover `api_update_shot_prompt`, `api_cleanup`, and `api_cleanup_all` null JSON bodies.

Expected output: implementation commit(s), focused tests, `scripts/ci_smoke.py`, and verify-request(s) to `operator2`. Keep production fixes in-lane; do not mark rows `verified` yourself.

### operator2 — Pair-B Lane V verifier

Task: stand by for `director2` verify-request(s). Verify real landed commits only.

Allowed write set on GO/NITS/FAIL: verification-report mailbox event, operator2 cursor, and same-commit lock release on GO. Per seat-operator rules, do not use `coordination/bin/release-lock` for a GO path; manually stage the lock deletion in the same commit as the GO event. On FAIL, retain the lock.

Expected output: GO/NITS/FAIL with executed evidence. Release `W2-auto_approve.py.lock` and/or `W2-web_server.py.lock` only in the same commit as the corresponding GO.

### director — product-oracle artifact route / Pair-A support

Task: advance the Wave 2 product-oracle blocker now that product-oracle write/spend authority is granted.

Allowed write set: `logs/product-oracle-*.json`, measurement helper/script/test/docs if needed, and mailbox status/route artifacts. Do not edit production code under this route.

Artifact contract: committed `logs/product-oracle-*.json` with `artifact_kind="product-oracle"`, `wave=2`, finite `arcface.arc_score`, and finite `lipsync.offset_frames`, produced by committed/reproducible R-MEASURE instrumentation. If required baseline media or services are missing, report the exact missing input/service and do not fabricate values.

Expected output: product-oracle artifact commit or a status event naming the exact external blocker. Route the completed artifact to `operator` for independent check.

### operator — product-oracle checker / Pair-A standby

Task: after `director` lands a product-oracle artifact, independently check that the artifact is committed, finite, and accepted by `scripts/wave_gate_check.py 2` for the product-oracle portion. Do not duplicate Pair-B Lane V.

Allowed write set: verification/status mailbox event and operator cursor. No production code.

Expected output: product-oracle check status or no-op if no artifact has landed yet.

## Coordinator Notes

Coordinator will not author production fixes. The Wave 2 gate remains open until the product-oracle artifact exists, the executed selector run is green, and open rows have operator GO evidence. This route records the user authorization and assigns work; it is not itself a GO or inventory transition.

Cursor at send: unknown
