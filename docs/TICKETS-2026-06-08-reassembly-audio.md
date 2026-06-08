# Tickets — re-assembly audio findings (U3 dogfood, 2026-06-08)

*Filed by operator-seat per user direction ("ticket F-A and F-B"). Source:
U3 dashboard dogfood, mailbox event `2026-06-07T20-05-00Z` (commit `f777f13`).
Runtime evidence from a real `/assemble/re-assemble` on project `7cddd0c59f6d`
(server log preserved at the event; key lines quoted below). All file:line
refs verified by Read at `af6ea97`.*

---

## T-A — Cartesia TTS receives ElevenLabs voice ids: lane is dead-on-arrival

**STATUS: CLOSED 2026-06-08** — `0276d41` + folds `35b3f95`/`ffabcf2` (the
'ko'-normalization live catch); merged to main at `c28f9e6`. Live acceptance:
first-ever Cartesia 200 (`voice=ce9ca2b6…`, no fallback) on `7cddd0c59f6d`.
Verification-report event `2026-06-07T23-08-17Z`.

**Severity: HIGH** (capability silently degraded — the Korean-prosody lane
the router selects can never succeed; every routed line burns a guaranteed-400
HTTP round-trip, then falls back to ElevenLabs, masking the breakage).

### Runtime evidence

```
[CARTESIA] Generating [language=ko] voice=21m00Tcm...
⚠️ [CARTESIA] failed: 400 Client Error: Bad Request for url: https://api.cartesia.ai/tts/bytes
[CARTESIA] failed for line 1; falling back to ElevenLabs
```

`21m00Tcm4TlvDq8ikWAM` is the ElevenLabs "Rachel" voice id. Cartesia expects
its own UUID-shaped voice ids — `generate_cartesia`'s OWN docstring states the
contract: *"voice_id: Cartesia voice ID (UUID-shaped strings per Cartesia
voice library)"* (`audio/dialogue.py:60`). Callers violate it by construction.

### Root cause (verified chain)

1. Voice resolution `audio/dialogue.py:352-382` yields an **ElevenLabs** id on
   every hop: character assignment (`char_voices.get(cid)`, :352 — pool ids
   are 11labs, see `domain/character_manager.py`), any-other-character (:364),
   language defaults (:366-378 — `domain/language_defaults.py:63,82,95,109,125`
   are ALL ElevenLabs ids, including Korean `uyVNoMrnUku1dZyVEXwD` Anna),
   legacy hardcode `pNInz6obpgDQGcFmaJgB` (:382).
2. Provider routing `_resolve_tts_provider` (:397) checks language/key, NOT
   voice-id provenance; dispatch (:399-409) passes the 11labs id straight into
   `generate_cartesia(voice_id=voice_id, …)` (:405-407) → API 400.
3. No per-provider voice mapping exists anywhere in the repo (grep
   `21m00Tcm` → only 11labs pools/defaults; no Cartesia voice table).

### Fix direction (minimal)

Per-provider voice mapping at the dispatch point (`audio/dialogue.py:~399`):
- Add a Cartesia voice table to `domain/language_defaults.py` (per
  language × gender, Cartesia UUID ids from their voice library).
- At dispatch: if routed to CARTESIA and `voice_id` is not Cartesia-shaped,
  map via the table; if no mapping, **skip Cartesia without the HTTP call**
  (fast-fallback) and log once per assembly, not per line.
- Rule #12 applies: the new table must be wired with write-evidence (grep
  the dispatch reads it), not just declared.

### Acceptance

- Korean project + `CARTESIA_API_KEY` set → server log shows Cartesia 200s,
  zero "falling back" lines.
- Unit test (mirror `tests/unit/` style): dispatch with an 11labs-shaped id →
  `generate_cartesia` is called with a mapped Cartesia id OR not called at all.
- The `[CARTESIA] failed: 400` class is gone from assembly logs.

---

## T-B — Re-assembly silently regenerates paid TTS; cost estimate counts only ffmpeg seconds

**STATUS: CLOSED 2026-06-08** — `516abca` + fold `86090cc` (atomic publishes,
11labs per-line guard, concat temps off CWD, SI-1 action-only estimate);
merged to main at `c28f9e6`. Live acceptance: zero-TTS re-assembly
(`[SCENE-AUDIO] Cache hit`). Documented residuals (conservative str-dialogue
estimate; LLM-dialogue non-cacheable; one-time migration miss; temp-artifact
accumulation → future reaper ticket) in verification-report
`2026-06-07T23-08-17Z`.

**Severity: MEDIUM** (real spend per re-assembly on dialogue projects +
non-deterministic audio between cuts — regenerated TTS ≠ the takes the
operator just screened).

### Runtime evidence

The U3 dogfood's forced re-assemble fired live TTS (Cartesia attempt →
ElevenLabs fallback → "✅ Multi-character dialogue assembled"), then
pedalboard BGM mastering. Pre-loudnorm intermediate measured −27.97 LUFS vs
the old export's −15.09 — the audio bed was genuinely rebuilt, not reused.

### Root cause (verified chain)

1. `web_server.py:2471-2485` (re-assemble endpoint) constructs a **fresh**
   `CinemaPipeline` → `_assemble_approved_takes_core` →
   `_build_scene_packages` (`cinema_pipeline.py:727`) →
   `_ensure_scene_audio` (:499).
2. `:501-503` consults the **in-memory** `self.scene_audio` dict first
   (runstate property, :187-191); the disk check (:502) runs ONLY when the
   in-memory entry exists. A fresh instance has an empty dict → regenerates
   via `generate_dialogue_voiceover` (:532) even though the output path is
   deterministic (`temp/audio_{scene_id}.mp3`, :524) and may exist on disk.
   (`_save_checkpoint()` at :541 persists state, but the endpoint's fresh
   instance does not restore it for this path — empirically TTS re-fired.)
3. `estimate_reassembly_cost` (`cinema/screening.py:498-578`) counts ffmpeg
   wall-clock only (:564-565 — per-shot overhead + duration factor); no TTS
   line count or $ estimate exists in the response or UI.
4. **Sub-finding (caching design inconsistency):** per-LINE caches are
   CWD-relative — `temp_dialogue_line_{i}.mp3` (`audio/dialogue.py:391`) with
   exists-short-circuit in `generate_cartesia` (:76-78, "Caller-controlled
   cache hit"; docstring says ElevenLabs path mirrors it). Index-keyed names
   in the server's CWD = stale cross-run/cross-project reuse hazard + repo-root
   pollution. (No hit occurred in the dogfood run — "Generating" printed —
   but the hazard is structural.)

### Fix direction

1. **Disk-first reuse with a content key.** Plain "reuse if
   `temp/audio_{scene_id}.mp3` exists" is WRONG under iteration — dialogue may
   have changed while scene_id stayed stable. Key the artifact by a hash of
   `dialogue_lines` (+ voice ids + language), e.g.
   `audio_{scene_id}_{content_hash}.mp3`; reuse on hash match, regenerate on
   miss. The `needs_reassembly` dirty-set is shot-level and does not track
   dialogue edits — do not reuse it as the invalidation signal without
   verifying that (open question for the implementer).
2. **Surface the spend.** `estimate_reassembly_cost` adds
   `tts_lines_to_generate` (uncached count) + `estimated_tts_usd`; the
   re-assemble response and the UI's re-assemble button caption include it.
3. **Kill the CWD-relative temps.** Per-line files move under the project's
   `temp_dir` with content-keyed names (composes with (1)).

### Acceptance

- Re-assemble with unchanged dialogue → **zero** TTS API calls in the log;
  with one edited line → exactly the edited lines regenerate.
- Estimate/response surfaces TTS line count + $ before the run.
- `ls` repo root after an assembly shows no `temp_dialogue_line_*.mp3`.

---

## T-C — Temp-artifact reaper: T-B's keyed audio artifacts accumulate unboundedly; the existing cleanup rule for them is dead

**STATUS: OPEN — specced 2026-06-08** (operator deferred-minors batch,
dispatch-claim `e018c71`; director pre-ack'd as future ticket in the T-B
residuals above). Spec source: Rule #17 read-only scout + operator Read
spot-checks (guardrail 2b); file:line refs verified at `5c81ebd`.

**Severity: LOW** (unbounded per-project disk growth only — no spend,
no correctness impact; but naive fixes are dangerous: a wrong reaper
defeats the zero-TTS cache T-B exists to provide, or breaks the
`exists ⇒ complete` atomic-publish invariant — QI-1 class).

### Evidence (the write surface — all under `get_project_dir(pid)/temp/`, cinema/core.py:92)

| Artifact | Writer | Cache-hit guard | Lifetime today |
|---|---|---|---|
| `dialogue_line_{12hex}.mp3` per-line TTS | `audio/dialogue.py:497-499` (key `_line_cache_key` :78-89); atomic `.part`+replace both lanes (:161-164 Cartesia, :583-585 11labs) | `:126-128` / `:566-569` | never deleted (deliberate per-line cache, :647-650) |
| `audio_{scene_id}_{key}.mp3` scene audio | `cinema_pipeline.py:532-533` (key `dialogue_cache_key`, dialogue.py:48-75); atomic publish dialogue.py:637-643 | `cinema_pipeline.py:534-538` | never deleted in standard mode |
| `audio_{shot_id}_{key}.mp3` shot audio | `cinema_pipeline.py:605-610` (exact scene mirror) | `:607` | never deleted in standard mode |
| `*.concat.txt`, `*.silence.mp3`, `*.part(.mp3)` control/in-flight files | dialogue.py:617-618 | n/a | removed on success (:651-653) but **leaked on the concat-exception path (:661-664)** and on kill-mid-write |

- **Accumulation drivers** (what changes a key → orphans the old artifact):
  any dialogue-line dict edit, voice_id change, scene-character add/remove,
  language change. **Worst driver: LLM-generated dialogue** — fresh key on
  EVERY full pipeline run (`cinema_pipeline.py:512-521` comment acknowledges
  "won't cache-hit") → one orphan scene mp3 + N orphan line mp3s per such
  scene per run, forever.
- **The intended cleanup is dead:** `cleanup.py:45` rule pattern
  `temp_dialogue_line_*.mp3` matches NOTHING after T-B's rename to
  `dialogue_line_*.mp3` (grep: only cleanup.py:45 still carries the old
  name). Keyed `audio_*.mp3` fall under the `scene_audio` **keep** rule
  (:51) — reaped only in `aggressive` mode, which nukes the LIVE cache too.
  Net: nothing reaps keyed artifacts in normal operation.
- **No mtime refresh on cache hits** — none of the four hit sites touches
  the file, so an actively-reused artifact looks as old as its creation
  date. Any age-based policy MUST add touch-on-hit or it reaps live cache.

### Fix direction (recommended: age-based sweep = time-LRU, inside existing machinery)

1. **`cleanup.py`** — add optional `max_age_days` to `CLEANUP_RULES` entries
   + an age gate in the `cleanup_project` loop (skip when
   `now - mtime < max_age_days*86400`; age-carrying rules are delete-eligible
   in standard mode). Rules: REPLACE dead `:45` with
   `{"pattern": "dialogue_line_*.mp3", "action": "delete", "max_age_days": 14}`;
   ADD `audio_*.mp3` age-reap; ADD crash-leftover rules `*.part`/`*.part.mp3`
   and `*.concat.txt`/`*.silence.mp3` with `max_age_days≈1` — the ≥1-day gate
   is what guarantees the reaper can never touch an in-flight atomic write
   (preserves `exists ⇒ complete`). Keep `cleanup_project`'s return contract
   (`files_deleted`/`bytes_freed`/`details`) — consumed by `web_server.py:2565`
   and `cinema_pipeline.py:910-912`.
2. **Touch-on-hit** — `os.utime(path, None)` (OSError-tolerant) at ALL FOUR
   hit sites: `cinema_pipeline.py:534` (scene), `:607` (shot),
   `audio/dialogue.py:126` (Cartesia line), `:566` (11labs line). Symmetry
   is mandatory (Rule #13): missing one lane silently un-protects that lane's
   projects (Cartesia = Korean).
3. **No new trigger.** The existing post-export auto-cleanup
   (`cinema_pipeline.py:908-915`, aggressive=False) + manual endpoints become
   the reaper once rules carry `max_age_days`. Deliberately do NOT sweep at
   re-assembly start — that's the reap-then-need race; post-success timing is
   structurally race-free for the current run (just-used artifacts have fresh
   mtimes).

**Rejected alternatives:** mark-and-sweep (requires re-deriving keys outside
the writer; the estimator mirror has ALREADY drifted once — see T-D — and a
drifted mark phase deletes LIVE cache = silent cache defeat); LRU size cap
(same touch-on-hit prerequisite + sizing machinery for marginal benefit);
manual-only (already exists; demonstrably didn't prevent accumulation).

### Acceptance

- Backdated `dialogue_line_*.mp3` / `audio_{id}_{key}.mp3` reaped in standard
  mode; fresh ones survive; `*.part` younger than 1 day SURVIVES (the QI-1
  invariant test); older `.part`/`.concat.txt`/`.silence.mp3` reaped.
- Cache hit at each of the 4 sites bumps mtime (regression in
  `tests/unit/test_dialogue_audio_cache.py`).
- Reuse-not-defeated: fresh keyed artifact + standard `cleanup_project` →
  subsequent ensure-site call cache-hits (no TTS call, assert via mock).
- bgm/foley `keep` rules untouched (bounded cardinality, not accumulation
  hazards); `aggressive` semantics unchanged (document only).

### Known residual risks (accepted in this design)

Reap-then-need after >N idle days = paid TTS regen, graceful (exists-guards
regenerate; atomicity prevents poisoning); manual `/cleanup` endpoint vs
in-flight assembly race is a PRE-EXISTING exposure class (optional hardening:
make the endpoint respect `_reassembly_in_flight` — out of scope here);
checkpoint-persisted `scene_audio` paths can dangle post-reap — covered by
exists-guards (`cinema_pipeline.py:503/579`).

---

## T-D — Estimator computes dialogue cache keys with project-wide characters; writer uses scene-filtered (estimate-only inaccuracy)

**STATUS: OPEN — fix in flight 2026-06-08** (operator deferred-minors batch
item F, dispatch-claim `e018c71` + this doc; found via Rule #17 guardrail-2b
spot-check of the T-C scout's side-observation).

**Severity: MEDIUM-low** (T-B's `tts_lines_to_generate` estimate over-counts —
predicts regen where assembly would cache-hit — whenever a scene's
`characters_present` is a strict subset of the project's characters; assembly
itself keys correctly, so no wasted spend, but the estimate UI lies in the
conservative direction, undermining T-B's cost-visibility purpose).

### Evidence (verified at `5c81ebd`)

- Estimator: `cinema/screening.py:565` — `characters = project.get("characters", [])`
  feeds `dialogue_cache_key(scene_dialogue, characters, lang)` (:589).
- Writer: `cinema_pipeline.py:738-741` — filters to
  `character.get("id") in scene.get("characters_present", [])` before keying.
- `dialogue_cache_key` (audio/dialogue.py:48-75) hashes sorted
  `(id, voice_id)` of the PASSED characters → different lists ⇒ different key
  ⇒ estimator checks a path that was never written.

### Fix direction

Filter `characters` per-scene inside the estimator loop, exact mirror of the
writer's comprehension; audit the shot-level estimate path for the same
asymmetry (Rule #13). Regression test asserting estimator and writer produce
the same key for a subset-characters scene.

### Acceptance

- Multi-char project, scene with subset `characters_present`, artifact on
  disk under the writer's key → estimate reports 0 lines to generate.

---

*Disposition (final): user-directed "do t-a t-b" same session — operator
implemented both (dispatch-claim `465891e`), sequential Lane B + dual cold
reviews each + live runtime acceptance; director independently re-verified
green and FF-merged `c28f9e6` (event `2026-06-07T23-29-45Z`). Both CLOSED.
T-C appended 2026-06-08 (operator deferred-minors batch, OPEN).*
