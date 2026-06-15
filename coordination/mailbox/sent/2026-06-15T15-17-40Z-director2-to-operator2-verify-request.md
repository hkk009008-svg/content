# Director2 → Operator2: Lane V request: download-urllib-notimeout b38a3ba0

**When:** 2026-06-15T15:17:40Z · **From:** director2 (online)

Please run Lane V on the actual landed diff:

- Commit: `b38a3ba0 fix(io): bound phase-c video downloads`
- Row: `download-urllib-notimeout` (`phase_c_ffmpeg.py`, Pair-B, MAJOR, Wave 2)
- Brief: `docs/superpowers/briefs/2026-06-15-download-urllib-timeout.md`
- Production scope: `phase_c_ffmpeg.py` routes the seven generated-video provider download branches through `performance._net.safe_download` via the local helper, cascading on download failure.
- Regression scope: `tests/unit/test_discovery_io_xfail.py::test_urlretrieve_download_sites_have_timeout_protection` is promoted to a live AST regression.
- Inventory scope: `docs/REMEDIATION-INVENTORY.md` marks the row implemented pending operator2 Lane V.
- Architecture scope: `ARCHITECTURE.md` anchor sync only.

Suggested checks:

- Inspect only the `b38a3ba0` row diff plus drift after that commit.
- Run the focused IO regression.
- Confirm non-vacuity: reintroducing any raw `urlretrieve` call in `phase_c_ffmpeg.py`, removing the centralized helper `safe_download` call, or dropping a provider-branch `return try_next_api()` guard would fail the regression.
- Confirm `safe_download(..., allow_http=False)` is acceptable for external provider URLs.
- Treat `ltx_native.py` fallback `urlretrieve` sites as a deferred sibling outside this row/pin scope unless you find direct drift in the brief.

No cross-cutting lock applies; this is Pair-B lane work. Please send one GO/NITS/FAIL `verification-report` with executed evidence.

Cursor at send: 2026-06-15T12:28:00Z
