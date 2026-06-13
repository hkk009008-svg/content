# Operator Transplant Handoff — 2026-06-08 (deferred-minors batch: 7 items CLOSED, T-E filed, ✅ READY unpushed)

*Last verified: 2026-06-08T01:03Z. Local `feat/max-tier-provisioning` = `f429ff0`
(17 ahead of origin/feat `5c81ebd`; **UNPUSHED**, push/merge user-gated).
**main == origin/main == `c28f9e6`** (unchanged this session). Suite
**1789 passed / 0 failed**, `ci_smoke` OK — both re-run at wrap. This handoff
SUPERSEDES `HANDOFF-operator-transplant-2026-06-08-v58-u3-ta-tb-shipped.md`.*

## ★ READ FIRST — what this session shipped

**The deferred-minors batch (USER-DIRECTED "proceed with item3"; dispatch-claim
`e018c71`; verification-report event `00:58:04Z`; director ACK `01:02:32Z`).
All 5 original deferred minors CLOSED + 2 scope-add bugs found-and-fixed:**

| Item | What | Commits | Outcome |
|---|---|---|---|
| C | `creative_llm` retired-id read-time migration (`claude-sonnet-4-20250514` retires **6/15**) + BE catalog `'claude-sonnet'`→`-4-6` sibling | `fbb313a`+`2b55206` | spec ✅ / quality Approve |
| B | diagnose_clip identity char source → in-frame (fe2aa47 residual) + face_swap/lip_sync sibling folds | `b0515a2`+`9aed3ce` | ⭐ cold reviewer caught **CRITICAL** (below); closed in-batch |
| E | **T-C** reaper ticket specced (found `cleanup.py:45` rule DEAD post-T-B-rename — nothing reaps keyed audio today) + **T-D** filed | `7fb49b7` | doc deliverable |
| F *(scope-add)* | **T-D CLOSED**: estimator scene+shot dialogue-cache keys now mirror the writers (was project-wide chars → over-counted TTS regen) | `5a8a0f8`+`e6ae6e3` | spec ✅ all 6 / quality APPROVE |
| G *(scope-add)* | `judge_map 'claude-opus'` targeted **never-valid** `claude-opus-4-20250918` (404'd TODAY) → `claude-opus-4-8` | `77f17d6` | Lane A + failure-class tests |
| A | Gemini encode→decode round-trip characterization (7 tests; encoder ALWAYS re-encodes JPEG q90 — bytes-identity is a false hypothesis) | `bbf3ac9` | coalesced ✅ |
| D | openai extraction no-retry pin (F2 single-charge; anthropic-sibling mirror) | `ff05d8c` | coalesced ✅ |

- ⭐ **The CRITICAL (`9aed3ce`)**: `b0515a2`'s lip_sync fold passed in-frame chars
  to `_ensure_scene_audio` → re-keyed `dialogue_cache_key` → paid TTS regen
  (T-B zero-TTS regression) + off-frame lines voiced via VG-B1 fallback +
  poisoned scene checkpoint. Scene audio is SCENE-scoped; only the ref/lip
  target follows the frame. Caught ONLY because the reviewer prompt named the
  cache-key watchpoint explicitly.
- **Process**: Rule #17 pre-scope workflow (5 scouts) + guardrail-2b spot-checks
  (which surfaced F and G beyond the briefs) → sequential Lane B implementers /
  parallel cold reviewers → final cross-cutting review **SHIP**. ~1.8M subagent
  tokens, 14 dispatches + 1 workflow. Catch ledger: 1 CRITICAL, 2 IMPORTANT,
  6 minors — zero from implementer self-reports.
- **T-E filed** (tickets doc): pre-existing same-class divergence at
  `controller.py:252-257`/`:1459-1462` (F1b/native paths) + shared char-filter
  helper extraction + 2 hygiene minors (`cost_tracker.py:80-81` pricing rows,
  `web_server.py:373` stale label). Verified at batch BASE — NOT introduced here.

## Where the program stands

- **main == origin/main == `c28f9e6`** — T-A/T-B era, GREEN. Local `feat` 17
  ahead (this batch's 10 + director's 4 portrait docs + coord), **UNPUSHED**.
- **Director ACTIVE on portrait Phase 2** (native 9:16 keyframes): spec
  `f40f39c`/`a4fa9a`→`a4faa9a` + plan `a59945f`/`f429ff0` complete +
  plan-reviewed; awaiting USER go to execute. Final design touches ONLY
  `cinema/aspect.py` + `phase_c_assembly.py` + `quality_max.py` + tests —
  the `controller.py` edit was DROPPED (zero overlap with item B, confirmed
  in their `01:02:32Z` event).
- Tickets: T-A/T-B/T-D CLOSED · T-C OPEN (spec ready) · T-E OPEN (filed).

## NEXT — operator-claimable, priority order

1. **Lane V on director's portrait-P2 implementation commits** when they land
   (user-gated go; their plan = subagent-driven). Primary operational duty;
   Rule #9 cold-context discipline; emphasize aspect-ratio plumbing,
   cross-system effects on assembly, 16:9 byte-identity.
2. **T-E fix cycle** (recommend standalone; director concurred "right
   consolidation"): shared `scene_characters`/`shot_characters` helpers in
   `audio.dialogue`, route all writer+estimator sites, decide the two F1b/native
   sites per-scope, regression tests. Same bug class as the CRITICAL, live in a
   reachable path.
3. **T-C reaper implementation** (spec fully written in tickets doc:
   age-sweep `max_age_days` in CLEANUP_RULES + touch-on-hit at 4 sites =
   time-LRU; QI-1 `.part`≥1-day gate).
4. **v5.8 working-criteria — datapoints to roll up at v5.9 retro**: C1 operator
   side COMPLETE (2 sessions zero storms; #2 included a live peer-commit
   mid-bootstrap handled by C1-path read-tree). C2 **zero staged-WIP-loss
   incl. a live C2-mixed instance this session** (see Gotchas). C3 spot-check
   PASS (markers advanced across peer commit). C4 holding.
5. **T1 Phase-B live LoRA-gate calibration** (GPU pod `07ed667` was 404 —
   verify Novita console FIRST; spend-gated).

## NOT operator (director-lane / user-gated)

- **Push/merge**: user-gated. Director will re-verify green at the exact batch
  tip before any FF (their `01:02:32Z` commitment; standard merge discipline).
- Portrait Phase-2 execution: director's lane (awaiting user go).
- **Memory curation (director, per partition):** candidates — (a) repoint the
  operator-handoff memory to THIS doc; (b) the "deferred minors" list in
  session memory is now CLOSED (all 5 + T-D done) — prune stale mentions;
  (c) model-id hygiene precedent (verify ids against the claude-api catalog,
  never memory — caught G) is worth a feedback memory.

## Gotchas / precedents (carry forward — updates the predecessor's list)

- ⭐ **NEW — C2-mixed live instance (the rarest D-a hazard, handled clean):**
  peer commit landed BETWEEN my `git add` and `git commit` → staged-diff showed
  a phantom 314-line DELETION of the director's just-added file. Three defenses
  held: v5.8 hook correctly refused auto-sync (B-case, staged work present);
  **pathspec commit bounded scope** (peer file untouched — check the commit
  stat, not the staged diff); post-commit `git status` exposed the residual
  phantom `D` entry → `git read-tree HEAD` (safe ONLY once your own work is
  fully committed) cleared it. If you see a staged deletion you didn't stage:
  STOP, commit only via pathspec, read-tree after.
- ⭐ **NEW — cache-key watchpoint for char-source edits:** any change to a
  character list near `_ensure_scene_audio`/`_ensure_shot_audio`/
  `dialogue_cache_key` re-keys artifacts → paid regen + possible wrong-voice.
  Scene audio = scene-filtered chars; shot audio = in-frame chars. Name this
  check EXPLICITLY in reviewer prompts (it caught the batch's only CRITICAL).
- ⭐ **NEW — model ids: verify against the claude-api skill catalog, never from
  memory** (G's `claude-opus-4-20250918` looked plausible and never existed;
  the bare `'claude-sonnet'` catalog value 404'd for months).
- **Characterization tests must pass GREEN first run** — if one fails, the
  hypothesis is wrong; fix the TEST (A's brief originally assumed
  bytes-identity; the scout's source-read corrected it pre-dispatch).
- **Suite runs**: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q`
  (pytest temp-repo trap unchanged).
- **Pathspec commits + `-m` before `--` + `git add` new files first** (unchanged;
  now load-bearing evidence via the C2-mixed instance above).
- **Presence edits**: single atomic `sed -i '' 's|^current_task:.*|…|'` (hook
  re-stamps on every tool call; Read+Edit loses the race).
- **Reviewer false-positive discipline**: verify-before-asserting (CC-2) held —
  0 hallucinated findings across 7 review dispatches this session.

## Verification at write (ADR-013)

```
$ date -u                                  → 2026-06-08T01:03:01Z
$ git rev-parse --short HEAD               → f429ff0
$ git for-each-ref … main/origin           → main c28f9e6 / origin/main c28f9e6 / origin/feat 5c81ebd
$ git rev-list --count origin/feat/max-tier-provisioning..HEAD → 17 (unpushed)
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q → 1789 passed, 0 failed (39.59s)
$ .venv/bin/python scripts/ci_smoke.py     → OK
$ cat coordination/mailbox/seen/operator.txt → 2026-06-08T01:02:32Z after this wrap (event 01:02:32Z consumed herein)
$ git status --porcelain | grep -v '^??' | wc -l → 0 (post read-tree; C2 resolved)
```
