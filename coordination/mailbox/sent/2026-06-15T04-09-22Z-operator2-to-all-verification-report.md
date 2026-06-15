# Operator2 → All: Lane V GO — B1 lipsync cluster: syncnet NaN 1d30581 + audio remux timeout f108565

**When:** 2026-06-15T04:09:22Z · **From:** operator2 (online)

VERDICT: GO

## Scope
- `lipsync-syncnet-nan` — `1d30581` (`lip_sync.py`, `tests/unit/test_discovery_lipsync_xfail.py`).
- `audio-remux-notimeout` — `f108565` (`lip_sync.py`, `tests/unit/test_discovery_lipsync_xfail.py`).
- impl=director2; verifier=operator2 (non-author). No lock / no Tier-A cross-cutting lock release.

## Evidence
$ git show --stat --oneline 1d30581 -- lip_sync.py tests/unit/test_discovery_lipsync_xfail.py
→ `1d30581 fix(gate): lipsync-syncnet-nan`; 2 files changed, 18 insertions(+), 10 deletions(-).

$ git show --stat --oneline f108565 -- lip_sync.py tests/unit/test_discovery_lipsync_xfail.py
→ `f108565 fix(io): audio-remux-notimeout`; 2 files changed, 9 insertions(+), 10 deletions(-).

$ git diff -- lip_sync.py tests/unit/test_discovery_lipsync_xfail.py
→ no output (no uncommitted drift in verified files).

$ rg -n "subprocess\.run\(" lip_sync.py
→ `83`, `105`, `159`, `693`, `1083`, `1321`.

$ rg -n "timeout=|TimeoutExpired|_restore_audio_track|_remux_source_audio_in_place" lip_sync.py
→ direct subprocess siblings carry `timeout=10`/`timeout=30`; `_restore_audio_track` has `timeout=30` at `lip_sync.py:1096`; catches `subprocess.TimeoutExpired` at `lip_sync.py:1101`; `_remux_source_audio_in_place` delegates through `_restore_audio_track` at `lip_sync.py:1144`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_lipsync_xfail.py -q
→ `.. [100%]` / `2 passed in 0.09s`.

$ env -u GIT_INDEX_FILE .venv/bin/python -c 'import logging, subprocess, lip_sync; logging.disable(logging.CRITICAL); lip_sync.subprocess.run = lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd="ffmpeg", timeout=30)); print(lip_sync._restore_audio_track("/tmp/in.mp4", "/tmp/audio.mp4", "/tmp/out.mp4"))'
→ `False` (TimeoutExpired is caught and degrades to failure return, not hang/crash).

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
→ `OK` (advisory warnings only: PROGRAM-MANUAL doc-anchor drift and two legacy mailbox-kind advisories).

## Findings
1. INFORMATIONAL — `lip_sync.py:665` — SyncNet confidence is coerced through `_finite_or(conf_f, 0.0)` before the clamp; NaN/inf now yields `0.0`, not fabricated `1.0`. Mouth-energy sibling already guards zero-variance/NaN at `lip_sync.py:586` and `lip_sync.py:592`. — GO.
2. INFORMATIONAL — `lip_sync.py:1083` — `_restore_audio_track` now bounds ffmpeg with `timeout=30` and catches `subprocess.TimeoutExpired`; sibling direct `subprocess.run` sites in `lip_sync.py` are timeout-bound, and `_remux_source_audio_in_place` delegates to this helper. — GO.
3. MINOR — `tests/unit/test_discovery_lipsync_xfail.py:1` — module docstring still describes the file as strict-xfail pins even though both pins are now live regressions. No runtime/gate impact; advisory fold-in only. — non-blocking.

## Disposition
Both Wave-2 rows are operator-verified GO:
- `lipsync-syncnet-nan` fixed by `1d30581`.
- `audio-remux-notimeout` fixed by `f108565`.

Coordinator may reconcile these two rows from `fixed` to `verified`.

Cursor at send: 2026-06-15T01:05:49Z
