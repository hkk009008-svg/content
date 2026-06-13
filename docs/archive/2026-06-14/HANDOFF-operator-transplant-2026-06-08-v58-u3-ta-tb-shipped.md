# Operator Transplant Handoff — 2026-06-08 (v5.8 index-autosync + U3 dogfood + T-A/T-B shipped, live-verified, MERGED)

*Last verified: 2026-06-07T23:56Z (06-08 JST). **main == origin/main == origin/feat == `c28f9e6`** — T-A/T-B PUBLIC. Local `feat` = `6ebfc09` (+ this wrap commit) ahead of main by coordination-only commits. Suite **1764 passed / 0 failed** (director independently re-verified at merge), `ci_smoke` OK, tsc+build clean. This handoff SUPERSEDES `HANDOFF-operator-transplant-2026-06-08-vision-tickets-and-p1-lanev.md`.*

## ★ READ FIRST — what this session shipped (4 arcs)

1. **v5.8 per-seat index auto-refresh — full Rule #14 cycle, bundle CLOSED.**
   `_sync_seat_index()` in `update-state.sh` (`454e770` + fold `a614f68`):
   A/B/C1/C2/D decision table; `read-tree` fires ONLY in C1 (index byte-equals
   last-synced tree — staged-WIP-loss excluded by construction); per-seat
   marker (the shared `.last-state-head` is advanced by the committing seat
   first — can't gate this). 7 awk-extraction tests. Proposal `62f09e8` →
   director CONSENT + ALL protocol text shipped `b5413da`. **The 4×/session
   phantom-deletion storms are retired** — zero storms this session post-ship
   (C1-criterion datapoint #1). ⚠️ Precedent: **agent edits to `.claude/hooks/`
   are USER-gated per-session** (harness self-mod classifier; peer concurrence
   ≠ user auth; AskUserQuestion authorized mine) — codified in RULES-LOG v5.8.

2. **U3 dashboard dogfood — ✅ PASS at the real surfaces** (event 20:05:00Z,
   `f777f13`). Real browser (Playwright + system Chrome headless, `/tmp/u3-pw/`),
   real re-assembly on `7cddd0c59f6d` (the −15.09 LUFS project): greyed
   "— not yet measured" BEFORE → measured GREEN −14.23 AFTER → RED proven via
   labeled synthetic probe → old export `aa777d858e71` stays greyed. The
   "must show RED" handoff prediction was stale-by-environment (loudnorm
   self-corrects; RED needs >1dB residual). Found **F-A/F-B/F-C** → ticketed
   `6c8eced` → user: "do t-a t-b".

3. **T-A + T-B — shipped, live-verified, merged to main.**
   Sequential Lane B (shared `audio/dialogue.py`), dual cold reviews each:
   - **T-A** (`0276d41` + folds `35b3f95`/`ffabcf2`): Cartesia voice mapping
     (REAL Korean UUIDs, live voices-API fetch: Seoyun `ce9ca2b6…` female /
     Jaewon `89f4372f…` male, `language_defaults.py:87-88`) +
     skip-without-HTTP guard. **Live: first-ever Cartesia 200** —
     `voice=ce9ca2b6… ✅ [Cartesia]`, no fallback (was: guaranteed 400/line).
   - **T-B** (`516abca` + fold `86090cc`): content-keyed dialogue-audio reuse
     (`dialogue_cache_key`; BOTH `_ensure_scene_audio`/`_ensure_shot_audio`),
     per-line temps off CWD content-keyed, atomic publishes (`.part`+replace)
     on all audio writes, TTS lines/$ in `estimate_reassembly_cost` →
     endpoint → ScreeningStage caption. **Live: zero-TTS re-assembly**
     (`[SCENE-AUDIO] Cache hit`).
   - **The ko-catch** (`ffabcf2`): 4 cold reviewers + 39 green unit tests
     missed that real projects store `language='ko'` while
     `get_language_defaults` exact-matches `"Korean"` — only the live run
     exposed it. Resolver now normalizes by 'ko'-prefix like the router.
   - Director re-verified green independently + FF-merged the EXACT verified
     SHA (`c28f9e6:main`), event 23:29:45Z. **No separate director Lane V**
     (user's bar was "merge once green"); backstop available on request.

4. **Coordination ran textbook all session** — director popped in 3× from
   `wrapping` presence (v5.8 CONSENT `b5413da`/`86f6013`; portrait-P1+all
   feat→main `fff6759`/`f9a9741` user-gated "do all"; T-A/T-B merge
   `c28f9e6`/`6ebfc09`). Dispatch-claims prevented every collision. Cursors
   current both sides at write (mine 23:29:45Z; theirs 23:08:17Z). My 20:25
   dispatch-claim remains formally in their unread set but is OBE (its content
   was consumed via the verification-report + merge).

## Where the program stands

- **main == origin/main == origin/feat == `c28f9e6`** — carries portrait-P1
  + vision + tickets 1-4 + v5.8 + U3 + T-A/T-B + converged polish. GREEN
  (1764/0, smoke OK, independently re-verified at merge).
- Local `feat` ahead by coord/wrap commits only (`6ebfc09` + this).
- Morning queue fully closed: #1 v5.8 ✅ · #2 polish folded by director
  (`fff6759`) · #3 U3 ✅ · T-A/T-B (beyond-queue) ✅ MERGED.

## NEXT — operator-claimable, priority order

1. **v5.8 working-criteria observation** (C1: zero storms across 2 sessions —
   datapoint #1 logged above; C3: spot-check markers advancing). Passive.
2. **T1 Phase-B live LoRA-gate calibration** (prior handoff #4; GPU pod
   `07ed667` was 404 — verify Novita console FIRST; spend-gated).
3. **Deferred minors** (prior handoff §5, all still open, none urgent):
   Gemini encode→decode round-trip test; `identity_result` single-char vs
   in-frame refs divergence; `creative_llm` persisted-old-model-id read-time
   migration (degrades via fallback after 6/15); openai-extraction no-retry
   test. Plus new: **temp-artifact reaper** (keyed mp3s accumulate; director
   ack'd as future ticket).
4. Offer the director the optional cold Lane V backstop on `465891e..ffabcf2`
   only if they ask (their 23:29 event leaves it to them).

## NOT operator (director-lane / user-gated)

- Push/merge: user-gated (now routine — two user-gated merges this session).
- Director's deferred: Rule #18 doc-maintenance anchor sweep
  (`chief_director.py` ~30 anchors) + F5 `visual_findings` FE render.
- **Memory curation (director, per partition):** candidates — (a) update the
  operator-handoff pointer memory to THIS doc; (b) verify
  `feedback_da_stale_index_refresh` was retired-except-C2 (their v5.8 REPLY
  claimed it; memory is outside git — unverifiable from repo); (c) the 'ko'
  seam + atomic-publish invariant are repo-recorded (commit bodies + tickets
  doc) — no memory entry needed.

## Gotchas / precedents (carry forward — updates the predecessor's list)

- **Stale-index storms: AUTO-FIXED by v5.8.** Manual handling remains ONLY
  for C2 mixed-state (hook correctly refuses; hit once this session via the
  director's uncommitted cursor-file edits): `git read-tree HEAD` is safe iff
  YOU have no staged work; else `read-tree -m`.
- **Suite runs**: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q`
  (UNCHANGED by v5.8 — the pytest temp-repo trap survives).
- **Pathspec commits + `-m` before `--` + `git add` new files first** (unchanged).
- **Presence edits while a subagent runs**: the hook re-stamps the file on
  EVERY tool call (subagents share the seat env) → Read+Edit always loses the
  race → use one atomic `sed -i '' 's|^current_task:.*|…|'`.
- **Server lifecycle**: Flask loads modules at import — RESTART after code
  changes before live-verifying. Kill via `kill $(lsof -ti :8080)` —
  `pkill -f "python web_server.py"` MISSES the macOS venv shim (ps shows
  capital-P `Python.app/.../Python web_server.py`).
- **Live-verify beats green CI for seam bugs** (the 'ko' case): unit tests
  encode their authors' assumptions; the real artifact store doesn't.
- **Reviewer fix-directions need judgment** (QI-1): a bare exists-guard over
  cached artifacts CAUSES permanent poisoning unless writes are atomic —
  `exists ⇒ complete` must be an invariant before any guard lands.
- **Cartesia voices list** (`GET api.cartesia.ai/voices`, X-API-Key) is free
  read-only — use it (not fabrication) for voice-table changes.
- `/tmp/u3-pw/` (4 dashboard screenshots) + `/tmp/u3-dogfood-backup/`
  (pre-dogfood project.json+mp4, server logs) — ephemeral evidence, gone on
  reboot; the durable trail is in events/commits.
- Untracked scratch unchanged: `scripts/_*.py`, `docs/adr/0002` (stale
  Proposed ADR from 05-23, benign).

## Verification at write (ADR-013)
```
$ date -u                                  → 2026-06-07T23:56:09Z (06-08 JST)
$ git rev-parse --short HEAD main origin/main → 6ebfc09 / c28f9e6 / c28f9e6
$ git rev-list --count origin/feat/max-tier-provisioning..HEAD → 0 (all pushed at write)
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q → 1764 passed, 0 failed
$ .venv/bin/python scripts/ci_smoke.py     → OK
$ cat coordination/mailbox/seen/operator.txt → 2026-06-07T23:29:45Z after this wrap (event 23:29:45Z consumed herein)
$ git status --short | grep -v '^??' | wc -l → 0 (post read-tree; C2 resolved)
```
