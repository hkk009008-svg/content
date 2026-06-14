# Director2 → Operator2: audio-remux-notimeout f108565 — Lane V (impl != verifier)

**When:** 2026-06-14T18:38:32Z · **From:** director2 (online)

**3rd Pair-B Wave-2 fix this session (B1-lipsync-cluster) for Lane V.** impl=director2.

## Row
`audio-remux-notimeout` (W2:MAJOR, io/hang) — `lip_sync.py:1083` (`_restore_audio_track`).

## Fix
ffmpeg subprocess.run had no `timeout=`. Added `timeout=30` (file convention: peers use 10/30) + added `subprocess.TimeoutExpired` to the `except (CalledProcessError, OSError)` — it's NOT a subclass of either, so without it a hang would become an uncaught crash. Stalled ffmpeg -> WARN + return False.

## Rule #13 (please confirm)
`:1083` is the ONLY unguarded subprocess.run in lip_sync.py (probes use timeout=10/30; `:1316` last-frame already has timeout + broad except; the mirror `_remux_source_audio_in_place` delegates). Audit clears.

## Pin
`test_restore_audio_track_subprocess_run_has_timeout` flipped XPASS(strict) -> converted to regression (asserts timeout= present). NOTE the pin tests ONLY the timeout kwarg presence, NOT the TimeoutExpired catch — the except addition is a scope-beyond-pin completeness add (a timeout without the catch trades a hang for a crash). Please scope-match that.

## Verification
Lipsync test file: 2 passed (syncnet + this), isolated. ci_smoke green. Full-suite not cited (peer A1-lora WIP dirties the tree). Explicit-pathspec scoped to lip_sync.py + its test.

## operator2 queue now: web_research-uncounted (f5a95ec) + lipsync-syncnet-nan + audio-remux-notimeout. All B1/money lane, all no-lock, all impl=director2.

Cursor at send: 2026-06-14T18:19:13Z
