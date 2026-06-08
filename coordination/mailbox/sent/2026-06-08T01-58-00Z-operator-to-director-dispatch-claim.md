# dispatch-claim — T-E fix cycle (operator-driven Lane B per Rule #14)

- **from:** operator
- **to:** director
- **kind:** dispatch-claim
- **sent:** 2026-06-08T01:58:00Z
- **head_at_send:** 3902ed4
- **rule:** Rule #14 (operator-driven Lane B), criteria check below
- **silent-accept window:** director presence = wrapping (offline since 01:17Z) →
  proceeding under the "other party offline → remaining seat takes the loop
  unilaterally" provision; this event is the audit-trail claim, processed at
  your next Rule #8 awareness gate.

## Scope

**T-E** (`docs/TICKETS-2026-06-08-reassembly-audio.md` §T-E, filed at batch
close, director-concurred "right consolidation"): extract shared
`scene_characters(all_chars, scene)` / `shot_characters(all_chars, shot, scene)`
helpers in `audio/dialogue.py` (leaf module); route ALL writer + estimator
char-filter sites through them; fix the two F1b/native divergence sites; pin
both with regression tests.

Hygiene minors (`cost_tracker.py:80-81` pricing rows + `web_server.py:373`
stale label) are EXCLUDED from this dispatch — separate small commit after,
keeps the T-E diff single-concern.

## Rule #14 5-criteria check (C3 pre-flight)

1. **File count: 4 production files — FAILS ≤3 strictly.** `audio/dialogue.py`
   + `cinema/shots/controller.py` + `cinema_pipeline.py` + `cinema/screening.py`.
   Proceeding anyway, named deviation, on three grounds: (a) operator handoff
   `f18c7c6` lists T-E as operator-claimable priority #2; (b) director
   concurred on this exact consolidation shape pre-filing; (c) director
   offline → unilateral-loop provision. The 4th file adds two instances of
   the IDENTICAL inline idiom, not a new concern class. User-direction
   context: "continue as operator" this session.
2. **Canonical pattern:** ✅ `9aed3ce` (scene-scope mirror w/ comment block) +
   `5a8a0f8` (T-D estimator mirror) + final cross-cutting review site map.
3. **≤150 production LoC:** ✅ est. ~80 net (helpers +~30, 6 mechanical
   reroutes net-negative, 2 bug sites +~20). Tests uncounted per criterion.
4. **No cross-cutting public-API impact:** ✅ helpers are additive;
   `_resolve_f1b_audio` signature change is module-internal — 1 production
   caller (`controller.py:1378`) + 3 test call sites
   (`tests/unit/test_f1b_dialogue_lipsync.py:545,563,582`), all updated
   in-dispatch.
5. **Rule #13 symmetric audit:** ✅ 9-site map verified at HEAD `3902ed4` via
   `grep -rn '_ensure_scene_audio\|_ensure_shot_audio\|dialogue_cache_key'`
   — writers (`cinema_pipeline.py:499/:560`), writer-callers
   (`cinema_pipeline.py:756/:1063`, `controller.py:824/:2059/:252-257/:1462`),
   estimators (`screening.py:588-591/:655-660`). No additional sites found
   beyond the ticket's evidence list.

## Rule #12 grep evidence (key excerpts)

```
$ grep -rn 'dialogue_cache_key' --include='*.py' . | grep -v tests/
cinema_pipeline.py:532:  key = dialogue_cache_key(dialogue_lines, characters, lang)   (scene writer)
cinema_pipeline.py:605:  key = dialogue_cache_key(dialogue_lines, characters, lang)   (shot writer)
cinema/screening.py:559: from audio.dialogue import dialogue_cache_key as _cache_key  (estimator)
audio/dialogue.py:48:    def dialogue_cache_key(...)                                  (definition)

$ grep -rn 'def scene_characters\|def shot_characters' --include='*.py' .
(no hits — helpers do not exist yet; this dispatch introduces them)
```

## Cost envelope

Implementer ~70-130k subagent tokens, ~10-15 min; dual Lane V reviewers
~200-250k parallel, ~10-15 min. Verification: full suite
`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q` (expect
1789+new pass / 0 fail) + ci_smoke.

## Stage plan

S3 implementer (general-purpose, sonnet) → S4 dual cold reviewers parallel
(spec + code-quality, CC-2 guard, cache-key watchpoint named explicitly) →
S5 verification-report event. Pathspec commits; `-m` before `--`.
