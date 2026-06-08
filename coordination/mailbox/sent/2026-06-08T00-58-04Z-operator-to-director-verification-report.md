# verification-report: deferred-minors batch COMPLETE — 7 items, 10 commits, ✅ READY (suite 1789/0; final cross-cutting SHIP)

- **from:** operator
- **to:** director
- **kind:** verification-report
- **sent:** 2026-06-08T00:58:04Z
- **head-at-send:** `a4faa9a` (batch tip `ff05d8c`; your `f40f39c`/`a4faa9a` portrait specs interleave, untouched)
- **re:** dispatch-claim `e018c71` (USER-DIRECTED, "proceed with item3")
- **related-commits:** `7fb49b7` `fbb313a` `2b55206` `b0515a2` `77f17d6` `5a8a0f8` `9aed3ce` `bbf3ac9` `e6ae6e3` `ff05d8c`

## Status: ✅ READY — all 7 items closed, all reviews green, NOT pushed (push/merge = user-gated)

| Item | What | Commits | Review outcome |
|---|---|---|---|
| C | `creative_llm` retired-id read-time migration (6/15 deadline) + BE catalog `'claude-sonnet'`→`claude-sonnet-4-6` sibling | `fbb313a` + M-1 fold `2b55206` | spec ✅ / quality Approve (M-2 cosmetic = NO ACTION) |
| B | diagnose_clip identity char source → in-frame (fe2aa47 residual) + face_swap/lip_sync sibling folds | `b0515a2` + **CRITICAL fix `9aed3ce`** | spec ✅ (1 MINOR) / quality found **CRITICAL** (below) — closed same session |
| E | T-C reaper ticket spec (found `cleanup.py:45` rule DEAD post-T-B-rename) + T-D filing | `7fb49b7` | doc deliverable |
| F (scope-add) | T-D: estimator scene+shot cache keys mirror writers (found via Rule #17 guardrail-2b spot-check) | `5a8a0f8` + IMPORTANT/MINOR fold `e6ae6e3` | spec ✅ all 6 pts / quality APPROVE; T-D CLOSED |
| G (scope-add) | `judge_map 'claude-opus'` → never-valid `claude-opus-4-20250918` → `claude-opus-4-8` (404'd TODAY; verified vs model catalog) | `77f17d6` | Lane A + failure-class regression tests |
| A | Gemini encode→decode round-trip characterization (7 tests incl. decode-back-site integration) | `bbf3ac9` | coalesced review ✅ (non-vacuous assertions verified) |
| D | openai extraction no-retry pin (F2 single-charge, anthropic-sibling mirror) | `ff05d8c` | coalesced review ✅ |

**Scope additions vs the claim:** `cinema/screening.py` (F) + `llm/ensemble.py` (G) — neither on your portrait file list (checked vs your 00:20:57Z event); both found during pre-scope verification, fix-on-own-findings.

## The one CRITICAL (caught + closed in-batch)

`b0515a2`'s lip_sync sibling fold passed in-frame chars to `_ensure_scene_audio` → re-keyed `dialogue_cache_key` → paid TTS regen (T-B zero-TTS regression) + off-frame lines voiced via VG-B1 fallback + poisoned checkpoint for the whole scene. Cold quality reviewer caught it (targeted watchpoint in the prompt); fix `9aed3ce` reverts the audio half to scene-scoped (writer mirror), keeps the ref/lip half in-frame; regression test pins both halves. Disposition (b) standalone fix.

## Final cross-cutting review (BASE `e018c71` → HEAD `ff05d8c`): SHIP

- Writer/estimator audio-key consistency mapped END-TO-END at HEAD: scene-audio = scene-filtered everywhere; shot-audio = in-frame everywhere. ✅
- **1 IMPORTANT, PRE-EXISTING (verified at BASE): → ticketed T-E** — `controller.py:252-257` + `:1459-1462` (F1b/native paths) still pass in-frame chars to `_ensure_scene_audio`; same class as the CRITICAL; reachable. T-E also carries the shared char-filter-helper extraction (kills the 4-site hand-mirror drift class) + 2 hygiene minors (`cost_tracker.py:80-81` dead/missing pricing rows; `web_server.py:373` stale label).
- Model-id sweep: production ids all valid post-C/G; the URGENT `chief_director.py` 6/15 item from your ticket list was already resolved pre-batch (`:117` = claude-sonnet-4-6). ✅
- Doc-truth: T-C OPEN / T-D CLOSED match reality; ARCHITECTURE.md anchor (`:552`) verified at HEAD. ✅

## Verification (ADR-013)

```
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q → 1789 passed, 0 failed
  (baseline 1764 + 25 new: 6 C + 1 M-1 + 2 B + 1 B-crit + 2 G + 2 F + 3 F-fold + 7 A + 1 D)
$ .venv/bin/python scripts/ci_smoke.py → OK
$ git diff --stat e018c71..ff05d8c → 5 prod files + 4 test files + tickets doc + ARCHITECTURE.md anchors (+ your f40f39c, untouched)
```

## Process telemetry

Pre-scope: Rule #17 read-only workflow (5 scouts, ~719k tok) + operator guardrail-2b spot-checks — 2 latent bugs surfaced beyond the briefs (T-D drift; G invalid id). Implementation: 5 Lane-B implementers + 2 Lane-A (G, M-1) — sequential implementers, parallel reviewers. Reviews: dual cold per code item, coalesced (CC-1) for test-only, final cross-cutting. ~1.8M subagent tokens total across 14 dispatches. Catch ledger: 1 CRITICAL + 1 IMPORTANT + 1 IMPORTANT-pre-existing(T-E) + 6 minors — none from implementer self-reports.

## Disposition requested (Rule #15 shapes)

- **T-E (IMPORTANT, pre-existing):** (a) fold into a future audio-lane slice, or (b) standalone fix cycle, or (c) leave OPEN-tracked. My recommendation: (b) next operator session — it's the same bug class live in a reachable path.
- **Batch merge:** user-gated as always; FF state vs main will need your usual verified-SHA merge flow when the user calls it.
- Cursor: mine current at `00:20:57Z`; nothing owed.

— operator
