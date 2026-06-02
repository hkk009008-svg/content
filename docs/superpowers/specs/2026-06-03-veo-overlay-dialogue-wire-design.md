# Veo + Overlay Dialogue Wire — Design Spec

*Date: 2026-06-03. Branch `feat/max-tier-provisioning`. Status: DRAFT (brainstorm-approved; pending spec-review + user review). Validation: **offline tests only** (per user). Scope: **robust/full** (per user).*

## Part 0 — Intent (why this exists)

The user-principal's dialogue decision (operator handoff 2026-06-03 §1, grounded in
this session's 4-approach test): **dialogue = Veo *video* → `lip_sync` OVERLAY(our TTS)**;
Veo native-audio is kept only for single non-dialogue shots. Rationale, evidence-backed:

- Veo has **no audio-input and no `voice_id`** (verified across Vertex + Gemini + both
  SDKs) → a *consistent character voice* is impossible with Veo's native audio.
- Veo's RAI filter **blocks hyper-photoreal talking-heads** as an output filter
  (threshold-sensitive; same path passed on a production keyframe, blocked 3/3 on a
  hyper-processed one).
- The end result is **already proven manually** this session:
  `logs/veo_musetalk_v2studio.mp4` = Veo video + our TTS overlay, sync **0.955**,
  identity preserved.

This spec wires that decision into the pipeline so it happens automatically. It serves
PROGRAM-MANUAL §2 ("dialogue is either generated natively with the video (Veo) or
lip-synced as a mandatory post-pass") by making the lip-sync-overlay path the **default**
for dialogue, with Veo's native voice demoted to an opt-in.

## Part 1 — Current behavior (what's wrong)

Verified trace through `cinema/shots/controller.py::generate_motion_take` at HEAD:

1. **Dialogue detected** → shot purpose `dialogue_close_up` / `talking_head_full`
   (`controller.py:412-433`, recomputed at `:1091-1093`).
2. **Routing override** (`controller.py:1120-1144`): for dialogue + AUTO, loops
   `PURPOSE_API_RANKING[purpose]` (`domain/scene_decomposer.py:120-122`) and forces the
   first engine with `native_audio==True AND modality=="video" AND status=="live"` →
   **VEO_NATIVE** (the only such engine, `scene_decomposer.py:43`). **Sets
   `video_fallbacks = None`** — so a Veo failure/RAI-block has *no* fallback and the take
   dies (`:1138-1141`, `:1203-1204`).
3. **Veo gets audio** (`phase_c_ffmpeg.py:281`): `generate_audio=(shot_type=="landscape"
   or has_dialogue)` → Veo generates its own (inconsistent) voice, embedded.
4. **`audio_embedded` tag** (`controller.py:1215-1216`): winning engine `native_audio` +
   `has_dialogue` → `take["metadata"]["audio_embedded"]=True`.
5. **Overlay short-circuited** (`controller.py:1233` vs `:1313`): the F1b mandatory
   lip-sync OVERLAY pass fires only `if has_dialogue and NOT audio_embedded`. Veo dialogue
   is `audio_embedded=True` → it takes the `elif` branch (`:1313-1322`): `lipsync_score=1.0`
   telemetry, **no overlay**, Veo's voice is final.
6. **Assembler honors embedded** (`cinema_pipeline.py:628-664`): per scene, if *all*
   approved shots are `audio_embedded` → `scene_audio=None` (suppress TTS mux); else mux
   the scene-level TTS.

The F1b overlay pass (`controller.py:1233-1312`) **already does exactly what we want**
(`generate_lip_sync_video(existing_video_path=veo_clip, audio_path=tts, mode→overlay)` →
replaces the take's video with the lip-synced output) — it is simply gated off for Veo
dialogue. **Two further gaps** for the robust scope:

- **Duration mismatch:** `_ensure_scene_audio` (`cinema_pipeline.py:481-524`) emits ONE
  `audio_{scene_id}.mp3` containing *all* the scene's lines; the overlay pass overlays
  that whole-scene track onto a *single* shot's video. Mismatch on any multi-shot scene.
- **No fallback:** `video_fallbacks=None` for dialogue means a Veo RAI-block kills the
  shot outright (the very failure mode §0 documents).

## Part 2 — Design (Approach A: reuse the F1b overlay pass)

Chosen over a dedicated parallel dialogue path (Approach B) because the overlay machinery
already exists, is proven, and is wired — A removes a short-circuit and improves inputs;
B duplicates it. A new config flag `dialogue_voice_mode` preserves the native path as an
opt-in escape hatch (absorbs the "keep it configurable" alternative cheaply).

### Component 1 — Routing: silent Veo + restored fallback cascade
*Files: `cinema/shots/controller.py:1120-1147`, `phase_c_ffmpeg.py:281`.*

- Keep **VEO_NATIVE as the dialogue primary** (the §0 look decision) under
  `dialogue_voice_mode=overlay` (default), but **do NOT null `video_fallbacks`** — restore
  the standard video-modality fallback cascade (e.g. VEO → Kling → Sora → Runway → LTX,
  live video engines in quality order) so a Veo RAI-block falls through to a silent-video
  engine instead of failing the take. *(Exact fallback-list construction — reuse the
  existing non-dialogue `video_fallbacks` builder — is an implementation detail for the
  plan; the requirement is "non-None, video-modality, VEO-first.")*
- `phase_c_ffmpeg.py:281`: change `generate_audio=(shot_type=="landscape" or has_dialogue)`
  → `generate_audio=(shot_type=="landscape")`. Dialogue Veo runs **silent**
  (`generate_audio=False`, the `veo_native.generate_video` default), which (a) lowers RAI
  block-rate and (b) guarantees no Veo voice can leak through the overlay regardless of the
  overlay engine's audio handling. Non-dialogue Veo already uses this path and assembles
  fine, so no assembler regression.
- Under `dialogue_voice_mode=native`, the current override behavior is preserved verbatim.

### Component 2 — Fire the overlay for dialogue
*File: `cinema/shots/controller.py:1215-1216, 1233`.*

- Gate the `audio_embedded=True` tag behind `dialogue_voice_mode==native`. In `overlay`
  mode the tag is not set, so the existing F1b pass at `:1233` runs for dialogue: it calls
  `generate_lip_sync_video(existing_video_path=final_vid, audio_path=<per-shot TTS>,
  mode=settings.get("lip_sync_mode","auto"))` → `auto` selects overlay because
  `existing_video_path` is present (`lip_sync.py:680` auto-route).

### Component 3 — Per-shot TTS, clip sized to speech (the duration fix)
*Files: new `_ensure_shot_audio` near `cinema_pipeline.py:481`; ordering in
`controller.py::generate_motion_take`; `audio/dialogue.py:286` reuse.*

- Add `_ensure_shot_audio(self, shot, scene, characters) -> Optional[str]`: mirrors
  `_ensure_scene_audio` but renders **only this shot's line** (`shot.get("dialogue")`) to
  `audio_{shot_id}.mp3` via `generate_dialogue_voiceover` (`audio/dialogue.py:286`).
  Returns `None` when the shot has no own line.
- For a dialogue shot in `overlay` mode: generate the **per-shot TTS first**, measure its
  duration, set the Veo clip `duration` (a **string** like `"6s"` per
  `veo_native.generate_video:143`) to the nearest engine-supported value ≥ speech length
  (clamped to the supported set, e.g. {4s, 6s, 8s}), then generate the (silent) video, then
  overlay. Result: video length ≈ speech length → clean sync, no truncation.
- **Fallback:** when `_ensure_shot_audio` returns `None` (i.e. `shot.get("dialogue")` is
  None/empty; dialogue lives only at scene level), fall back to today's
  `_ensure_scene_audio` + the shot's configured duration (current behavior, partial). The
  overlay still runs; only the duration-sizing benefit is skipped.
- **Call site (do not miss):** the F1b pass at `controller.py:1243` currently calls
  `self._host._ensure_scene_audio(scene, chars_dicts)` — *this* is the line that feeds the
  overlay's `audio_path`. For overlay-mode dialogue it must be replaced with
  `_ensure_shot_audio(shot, scene, chars_dicts)` (with the scene-audio fallback inside).
  Adding `_ensure_shot_audio` to `cinema_pipeline.py` without changing `:1243` would leave
  the scene-level call in place (a silent no-op fix).

### Component 4 — Assembler dedup (no double-audio)
*File: `cinema_pipeline.py:628-664`.*

- After a successful overlay (`controller.py` F1b success branch ~`:1260`), set
  `take["metadata"]["dialogue_audio_in_clip"]=True` (the overlaid clip now carries the
  TTS).
- In `_build_scene_packages`, the per-shot count at `:633` becomes
  `if take_meta.get("audio_embedded") or take_meta.get("dialogue_audio_in_clip")`. A scene
  whose dialogue shots are all overlay-in-clip then suppresses the scene-TTS mux
  (`scene_audio=None`, `:646-647`) — exactly as the native-embedded path does today, which
  already proves each clip's own audio survives the concat mux. Prevents the double-voice
  (clip TTS + scene TTS).

### Component 5 — Config escape hatch
- `global_settings.dialogue_voice_mode ∈ {"overlay", "native"}`, **default `"overlay"`**.
  Read with the same `settings.get(...)` pattern used for `lip_sync_mode`
  (`controller.py:1256`). `native` = today's Veo-native-voice behavior end-to-end
  (Components 1, 2, 4 all branch on it). Document in OPERATIONS.md / PROGRAM-MANUAL §5.

## Part 3 — New dialogue data flow (overlay mode, per-shot line present)

1. `has_dialogue` True; `dialogue_voice_mode=overlay`.
2. `_ensure_shot_audio(shot,…)` → `audio_{shot_id}.mp3`; measure duration → clamp →
   Veo duration string.
3. Routing: primary VEO_NATIVE, **silent** (`generate_audio=False`), `video_fallbacks` =
   video cascade. `generate_ai_video` produces a silent clip (Veo, or a fallback engine on
   RAI-block).
4. `audio_embedded` NOT set (overlay mode). F1b pass at `:1233` runs:
   `generate_lip_sync_video(existing_video_path=silent_clip, audio_path=shot_tts,
   mode=overlay)` → lip-synced clip with our consistent TTS. `final_vid = ls_result`;
   `lipsync_score` recorded; cost tracked (`:1276-1284`); `dialogue_audio_in_clip=True`.
5. Assembler: scene's dialogue shots all `dialogue_audio_in_clip` → `scene_audio=None`;
   clips' own (overlaid) audio rides the concat. No double-voice.

## Part 4 — Error handling / edge cases

- **Veo RAI-block:** falls through `video_fallbacks` to a silent-video engine → overlay
  still applies. Dialogue shot survives (today it dies). If *all* video engines fail,
  the take fails as today (`:1203-1204`).
- **Per-shot TTS fails / absent:** fall back to scene audio + configured duration
  (Component 3 fallback); overlay still runs. If both audio sources are absent, the
  existing `:1294-1303` DEGRADED-no-lipsync path applies (`lipsync_score=0.0`, gate FAIL).
- **Overlay returns nothing:** existing `:1285-1292` path (`lipsync_score=0.0`); the take
  is *not* `dialogue_audio_in_clip` → assembler keeps scene TTS for it (no silent shot).
- **Duration clamp:** TTS longer than max supported Veo duration → clamp to max; the
  overlay engine truncates the tail (flagged; long-line splitting is out of scope).
- **Mixed scene (some dialogue-in-clip, some not):** existing mixed-scene branch
  (`:654-664`) keeps scene TTS for the non-in-clip shots; in-clip shots already carry
  their audio. *(Known limitation: the scene TTS muxed for non-in-clip shots is still
  scene-level; this spec does not change non-dialogue audio.)*

## Part 5 — Testing (offline, mocked; $0)

**Update (assert the new default):**
- `tests/unit/test_dialogue_routing.py:288-306` — asserts `audio_embedded=True` for
  VEO+dialogue. Under default `overlay`: assert NOT `audio_embedded`, fallbacks restored,
  `generate_audio=False` for dialogue. Add a `native`-mode case keeping the old assertion.
- `tests/unit/test_f1b_dialogue_lipsync.py` — currently asserts the gate passes
  audio-embedded takes; update to assert the overlay path produces a `lipsync_score` and
  `dialogue_audio_in_clip`.

**New (`tests/unit/`):**
1. `generate_audio=False` for dialogue, `=True` for landscape (`phase_c_ffmpeg.py:281`).
2. Overlay pass fires for dialogue in `overlay` mode (no `audio_embedded`).
3. `_ensure_shot_audio` renders the shot line; Veo `duration` clamped to speech length;
   scene-audio fallback specifically when `shot.get("dialogue")` is None/empty (the
   fallback trigger).
4. Veo failure → fallback engine wins → overlay still applies (`video_fallbacks` non-None).
5. Assembler suppresses scene TTS when all dialogue shots are `dialogue_audio_in_clip`
   (no double-audio); mixed scene keeps TTS for non-in-clip shots.
6. `dialogue_voice_mode=native` preserves the current embedded path end-to-end.

Mock `requests`/FAL/Veo/TTS as the existing dialogue tests do; assert routing + metadata,
not real media. `ci_smoke.py` green; full unit suite green.

## Part 6 — Out of scope (YAGNI / deferred)

- **Live wired-E2E** (deferred per the validation choice; approach already proven by
  `logs/veo_musetalk_v2studio.mp4`).
- **Full line→shot dialogue mapping** when dialogue exists only at scene level (use the
  per-shot line when present; else scene-level fallback).
- **Splitting one long line across shots** / multi-character single-shot dialogue mixing.
- **Non-dialogue audio** changes; BGM/foley; the assembler's scene-level mux model.

## Part 7 — File change summary (anchors)

| File | Change |
|---|---|
| `cinema/shots/controller.py:1120-1147` | Dialogue routing: VEO primary, restore `video_fallbacks`, gate native-only behavior on `dialogue_voice_mode` |
| `cinema/shots/controller.py:1215-1216` | Gate `audio_embedded` tag behind `dialogue_voice_mode==native` |
| `cinema/shots/controller.py:1233-1262` | Per-shot TTS + duration sizing before video; **replace the `_ensure_scene_audio` call at `:1243` with `_ensure_shot_audio`** (scene fallback inside); set `dialogue_audio_in_clip` on overlay success |
| `phase_c_ffmpeg.py:281` | `generate_audio=(shot_type=="landscape")` (drop `or has_dialogue`) |
| `cinema_pipeline.py` (~:481) | New `_ensure_shot_audio` |
| `cinema_pipeline.py:633` | Count `dialogue_audio_in_clip` alongside `audio_embedded` for TTS suppression |
| `config/settings.py` + settings plumbing | `dialogue_voice_mode` default `"overlay"` |
| `tests/unit/test_dialogue_routing.py`, `test_f1b_dialogue_lipsync.py`, +new | Per Part 5 |
| `ARCHITECTURE.md §10.6/§10.7`, `OPERATIONS.md`, `PROGRAM-MANUAL §5` | Document the new default + `dialogue_voice_mode` |

## Verification at write

- Anchors verified at HEAD `4bbce8d` via Read/grep: `controller.py:1120,1215,1233,1313`;
  `phase_c_ffmpeg.py:281`; `cinema_pipeline.py:481,633,646`;
  `scene_decomposer.py:43,120-122`; `veo_native.py:143,146`; `audio/dialogue.py:286`;
  `lip_sync.py:177,680`; tests `test_dialogue_routing.py:288-306`.
- `logs/veo_musetalk_v2studio.mp4` exists (1.4 MB, the proven manual result).
