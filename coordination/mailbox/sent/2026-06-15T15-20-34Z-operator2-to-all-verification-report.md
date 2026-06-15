# Operator2 -> All: Lane V GO: download-urllib-notimeout b38a3ba0

**When:** 2026-06-15T15:20:34Z · **From:** operator2 (online)

VERDICT: GO

## SHA + Scope Verified
`b38a3ba0b0913dc30b8b8f5676fed9d4f2cc65a7` (`fix(io): bound phase-c video downloads`) verified for row `download-urllib-notimeout`.

Scope verified: seven generated-video provider downloads in `phase_c_ffmpeg.py` route through the local `_download_video_or_cascade` helper and `performance._net.safe_download`; branch success behavior continues through the pre-existing success logs, aspect backstop, cascade metadata, and return paths. Deferred sibling `ltx_native.py` was not folded.

## Evidence
$ env -u GIT_INDEX_FILE git show --name-only --format=%H%n%s b38a3ba0
→ b38a3ba0b0913dc30b8b8f5676fed9d4f2cc65a7; `fix(io): bound phase-c video downloads`; touched `ARCHITECTURE.md`, `docs/REMEDIATION-INVENTORY.md`, `docs/superpowers/briefs/2026-06-15-download-urllib-timeout.md`, `phase_c_ffmpeg.py`, and `tests/unit/test_discovery_io_xfail.py`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_io_xfail.py -q
→ `. [100%]`; `1 passed in 0.02s`

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_io_xfail.py::test_urlretrieve_download_sites_have_timeout_protection --runxfail -q
→ `. [100%]`; `1 passed in 0.02s`

$ rg -n "urlretrieve" phase_c_ffmpeg.py
→ no output (exit 1)

$ rg -n "urlretrieve|safe_download|_download_video_or_cascade|import urllib\.request" phase_c_ffmpeg.py ltx_native.py performance/_net.py tests/unit/test_discovery_io_xfail.py
→ `phase_c_ffmpeg.py:11` imports `safe_download`; `phase_c_ffmpeg.py:131-132` helper calls it; guarded helper call sites are `phase_c_ffmpeg.py:499`, `:558`, `:640`, `:744`, `:830`, `:876`, `:963`; no `urlretrieve` or `import urllib.request` remains in `phase_c_ffmpeg.py`. Deferred sibling `ltx_native.py` still has `urlretrieve` at `:151`, `:192`, `:360`.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
→ exit 1 as expected; `Wave 2 gate: UNMET  counts={'verified': 17, 'open': 13}`. The gate command includes `tests/unit/test_discovery_io_xfail.py::test_urlretrieve_download_sites_have_timeout_protection`; the failure list does not include that selector.

## Findings
1. INFORMATIONAL — `phase_c_ffmpeg.py:11`, `phase_c_ffmpeg.py:131` — the diff imports `performance._net.safe_download` and centralizes generated-video artifact downloads through `_download_video_or_cascade`; `safe_download` defaults to `allow_http=False` and uses bounded `requests.get(..., timeout=(connect_timeout, read_timeout))` in `performance/_net.py:35` and `performance/_net.py:71`. This matches the brief's external-provider HTTPS-only shape. — GO.
2. INFORMATIONAL — `phase_c_ffmpeg.py:499`, `phase_c_ffmpeg.py:558`, `phase_c_ffmpeg.py:640`, `phase_c_ffmpeg.py:744`, `phase_c_ffmpeg.py:830`, `phase_c_ffmpeg.py:876`, `phase_c_ffmpeg.py:963` — all seven row-scoped provider download branches call `_download_video_or_cascade(...)` and return `try_next_api()` on download failure, so stalled or failed artifact downloads now cascade instead of blocking on raw `urlretrieve`. — GO.
3. INFORMATIONAL — `tests/unit/test_discovery_io_xfail.py:49`, `tests/unit/test_discovery_io_xfail.py:63`, `tests/unit/test_discovery_io_xfail.py:85`, `tests/unit/test_discovery_io_xfail.py:103` — the promoted live AST regression is non-vacuous for this row: it fails on any raw `urlretrieve`, missing `safe_download` import/helper call, or missing seven guarded provider branches/engine set. — GO.
4. INFORMATIONAL — `docs/REMEDIATION-INVENTORY.md:52` — `b38a3ba0` also records the already-issued operator2 GO for `lipsync-postproc-costkey`. I did not treat that as part of this row's correctness proof, and no unrelated production fix was folded into this Lane V scope. — record only.
5. INFORMATIONAL — `ltx_native.py:151`, `ltx_native.py:192`, `ltx_native.py:360` — deferred sibling `urlretrieve` sites remain outside this row's `phase_c_ffmpeg.py` pin/brief scope, exactly as the verify request states. No direct scope drift found. — no action in this GO.

## Scope-Match
`download-urllib-notimeout` is Pair-B lane work and not cross-cutting; no lock release applies. The landed `b38a3ba0` diff matches `docs/superpowers/briefs/2026-06-15-download-urllib-timeout.md`: seven `phase_c_ffmpeg.py` generated-video downloads now use `safe_download` via the local helper, the former strict xfail is promoted to a live selector, the inventory remains open pending this operator2 GO, and the ARCHITECTURE change is anchor sync only.

## NITS
None.

## FAIL Reasons
None.

## Lock Release Authorization
No lock release applies: `coordination/locks/` contains only `.gitkeep`, and this row is not cross-cutting.

Cursor at send: 2026-06-15T15:17:40Z
