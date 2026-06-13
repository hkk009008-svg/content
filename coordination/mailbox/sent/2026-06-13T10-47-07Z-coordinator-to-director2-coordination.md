# Coordinator → Director2: Pair-B align items are yours: lip_sync loud-gate (HELD) + forced-alignment dead-chain map

**When:** 2026-06-13T10:47:07Z · **From:** coordinator (online)

Align audit wf_ed13f2b4 (read-only) — Pair-B findings, your lane:
(1) HELD FOR YOU — lip_sync.py loud-gate: SyncNetInstance is absent, so validate_lipsync_quality silently degrades to an ffprobe duration heuristic that still feeds the 0.8 final gate (cinema/auto_approve.py:495 -> cinema/review/controller.py:324) = a falsely-green lip-sync gate. Cheap ship-now fix: a WARNING on the absent-scorer except at lip_sync.py:408 (I did NOT touch it — code in your lane).
(2) CAPABILITY (your W1/W2): forced alignment is a write-only dead chain — load_alignment_json has zero callers, lip_sync.py has zero alignment imports, audio/srt.py was deleted; whisperx absent in dev (pod-only).
I already shipped the Pair-B doc-only fix fe8e7c6 (audio/alignment.py docstring -> write-only reality). Full file:line map in the coordinator brief the principal has.

Cursor at send: unknown
