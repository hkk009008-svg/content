# Design — Hybrid dialogue voice routing (per-character casting)

**Date:** 2026-05-29
**Status:** Draft (brainstorming → spec)
**Author:** director-seat
**Topic:** Per-shot routing of dialogue between native-AV (model-voiced, simultaneous video+audio) and controlled (ElevenLabs TTS + lip-sync) paths, driven by per-character voice casting.

---

## 1. Problem & motivation

Today, dialogue shots are hard-routed to a single native-audio engine: `cinema/shots/controller.py:1117` overrides `target_api` to the first `native_audio`-capable video engine and drops the fallback chain (`video_fallbacks = None`). The **only** engine flagged `native_audio: True` is `VEO_NATIVE` (`domain/scene_decomposer.py:43`), which requires Google Vertex billing. Consequences:

- If Veo/Vertex is unavailable, a dialogue shot has no native-audio fallback — it degrades to the separate TTS+lip-sync path (or, with fallbacks dropped, risks a silent take; see §8 risk).
- There is no way to mix **model-generated voices** (cheap, simultaneous, no voice control) with **cloned/scripted voices** (ElevenLabs, exact voice + script) within one project.

**Desired behavior (user-approved):** a *hybrid, per-shot* router. Some dialogue shots use native-AV (model voice); others use controlled ElevenLabs TTS + lip-sync (cloned voice). The choice is driven by **per-character voice casting**. The native-AV path must fall back to the *next-best native-audio engine* rather than silently dropping to TTS.

## 2. Goals / Non-goals

**Goals**
- Per-character casting: a character is either **cast** (has a real ElevenLabs voice → controlled path) or **native** (model generates the voice → native-AV path).
- Per-shot router resolves native vs controlled from the speaking character's casting.
- Native-AV path picks the **best available** native-audio engine (funded creds + quality rank + sunset-excluded) and cascades **among native-audio engines only** — never silently to TTS.
- Wire Sora-2 native audio (a second native-audio engine) so the fallback is real, not theoretical.

**Non-goals**
- No structured multi-speaker dialogue model (per-shot speaker arrays). Scene-level `dialogue: str` + shot `primary_character` is the substrate; true multi-speaker attribution is an edge case (§7).
- No change to the controlled (ElevenLabs + lip-sync) path's internals.
- No new upscale/image work; this is dialogue-audio routing only.

## 3. Verified current state (grounded)

| Fact | Evidence |
|---|---|
| Dialogue hard-overrides to the sole `native_audio` engine, fallbacks dropped | `cinema/shots/controller.py:1117-1139` |
| Only `VEO_NATIVE` carries `native_audio: True` | `domain/scene_decomposer.py:43` |
| Assembler skips TTS when take tagged `audio_embedded` | `cinema/shots/controller.py:1207-1213` |
| Veo native audio needs **Vertex** (`generate_audio`); Gemini-API fallback has **no audio** | `veo_native.py:27,52,65,79` |
| Sora client is **video-only** (no audio code) | `sora_native.py` (grep: no audio/speech/voice) |
| Sora 2 *does* support synced native audio; fal `fal-ai/sora-2/image-to-video` exposes the same | openai.com/index/sora-2 ; fal.ai/models/fal-ai/sora-2/image-to-video |
| **Sora 2 API sunsets 2026-09-24** | sora_native.py:6 ; OpenAI API docs |
| `Shot.primary_character` + `Shot.characters_in_frame` exist; `Scene.dialogue` is a string | `domain/models.py:93-94,129` |
| Primary char resolves as explicit field or first-in-frame | `cinema/shots/controller.py:381` |
| Engine availability is keyable from `config/settings.py` creds | `settings.py:51-126` |

## 4. Design

### 4.1 Casting model
Add `Character.native_voice: bool = False` (`domain/models.py`, Character class).
- `native_voice = False` (default, "cast"): character keeps its real ElevenLabs `voice_id` → **controlled path**. Preserves today's behavior for every existing character.
- `native_voice = True`: character's dialogue → **native-AV path** (the video model voices them); TTS is skipped for them.

*Why a new field, not `voice_id == ""`:* `voice_id` auto-assigns (`character_manager.py:167-170`), so emptiness cannot encode intent. The explicit flag is unambiguous and doesn't fight auto-assign.

### 4.2 Per-shot router
Generalize the `if has_dialogue:` block at `controller.py:1117`. For a dialogue shot:
1. Resolve the speaking character = `shot.primary_character` (fallback: first of `characters_in_frame`), per `controller.py:381`.
2. Look up that `Character.native_voice`.
   - **native** → native-AV path (§4.3), tag `audio_embedded=True` on success.
   - **cast** → controlled path (§4.5); keep the existing mandatory lip-sync pass.

Default casting (all characters `native_voice=False`) reproduces today's controlled behavior — but with the native path now available the moment a character is marked native.

### 4.3 Native-AV path — best-available, auto-ranked (the "second-best fallback")
Flag `native_audio: True` on `SORA_NATIVE` and `SORA_2` (after §4.4 wiring); add a `sunset: "YYYY-MM-DD"` field where applicable. Build the candidate list at routing time:

```
candidates = [e for e in API_REGISTRY
              if e.native_audio and e.modality == "video" and e.status == "live"
              and creds_available(e)            # funded credentials present
              and not sunset_passed(e)]          # current date <= sunset
order = sorted(candidates, by quality_score desc)
```

- `creds_available`: `VEO_NATIVE` ⇐ `google_cloud_project` + Vertex ADC; `SORA_NATIVE` ⇐ `openai_api_key`; `SORA_2` ⇐ `fal_key`.
- Quality ranks (registry): `SORA_NATIVE` 0.88 > `SORA_2` 0.87 > `VEO_NATIVE` 0.85.
- Cascade through `order`; **the chain stays inside `order`** — it must not fall to a non-native engine (that would silently drop embedded voice, the exact bug `controller.py:1135-1138` guards against today).
- Outcomes: no Google → Sora carries it (until sunset); Vertex set up → Veo participates (durable); Sora past sunset → auto-excluded; both present → ranked. If `order` is empty → fall to controlled path (TTS+lip-sync) with a logged warning (graceful, not silent).

### 4.4 Sora-2 audio wiring (new code)
`sora_native.py` is video-only. Add `generate_audio: bool = False` to its generate call (mirror `veo_native.py:65`), pass it through the `fal-ai/sora-2/image-to-video` invocation (`phase_c_ffmpeg.py` SORA paths ~227/386), and ensure the winning-engine `native_audio` check at `controller.py:1208-1213` tags `audio_embedded=True` for Sora the same way it does for Veo.

### 4.5 Controlled path (unchanged)
Cast character → existing ElevenLabs TTS (their `voice_id`, via `audio/dialogue.py`) + lip-sync (`generate_lip_sync_video(mode="auto"|"overlay"|"generation")`, `lip_sync.py:687`) + ffmpeg mux. No internal changes.

### 4.6 Assembler hook
`audio_embedded=True` already gates TTS-skip (`controller.py:1207`). Extending the `native_audio` flag to Sora engines makes this work for the new path with no assembler change.

## 5. Data-model & open questions (for the plan)
1. **Multi-speaker shots.** `dialogue` is scene-level; a shot tracks `primary_character` + `characters_in_frame`, not who-speaks-which-line. MVP keys on `primary_character`. Optional conservative rule: if *any* `characters_in_frame` member is cast, force controlled (protects cast voices at the cost of occasionally over-routing to controlled). **Plan must pick one; MVP recommendation = primary_character.**
2. **Sunset representation.** New registry `sunset` field + a `sunset_passed()` helper using runtime `datetime`. Confirm no other code path assumes Sora is always live.
3. **`creds_available()` for Veo/Vertex.** ADC presence isn't a simple env var; decide the detection (try-init probe vs. `google_cloud_project` truthiness + a cached health check).

## 6. Risks
- **Sora-2 sunset (2026-09-24).** Auto-ranking + sunset-exclusion (§4.3) handles it without a hard dependency, but post-sunset the native path needs Veo funded or it falls to controlled. Documented, not silent.
- **Behavior change to a load-bearing routing block** (`controller.py:1117`). Mitigation: default casting reproduces today's behavior; the native path only activates when a character is explicitly `native_voice=True`.
- **Silent-voice regression** if the cascade ever leaves the native-audio set. Mitigation: §4.3 chain invariant + a test asserting it.

## 7. Testing
**Unit**
- Router resolves native vs controlled correctly from `primary_character.native_voice` (both values; default-false reproduces controlled).
- `order` ranking: filters by creds, excludes past-sunset, sorts by quality; empty → controlled with warning.
- Cascade invariant: native path never yields a non-native engine.
**Integration**
- Cast character shot → take has TTS+lip-sync, `audio_embedded` falsy.
- Native character shot → routes to a native-audio engine, `audio_embedded=True`, TTS skipped.
- (ffmpeg-layer, pod-independent: assertable like the M1 fix.)

## 8. Files touched (est.)
- `domain/models.py` — `Character.native_voice` field.
- `domain/scene_decomposer.py` — `native_audio` flag on Sora engines + `sunset` field + ranking helper.
- `cinema/shots/controller.py` — generalize the dialogue override into the casting router.
- `sora_native.py` — `generate_audio` wiring.
- `phase_c_ffmpeg.py` — pass audio flag on Sora path.
- Tests under `tests/unit/`.
- Doc-sync: ARCHITECTURE.md dialogue/routing section; fix the stale `recommend_lip_sync_mode()` reference in the ai-video-gen skill.

## 9. Out of scope
Structured multi-speaker dialogue; upscale/image routing; controlled-path internals; UI for casting (a later per-shot override layer could sit on top).
