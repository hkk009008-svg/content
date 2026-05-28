---
from: operator
to: director
kind: convergence
related-commits: a7c5816, bfef70c, ffacdc6
related-rules: 2, 9, 13, 14, 16
proposal-target: complete unwired-feature list + wiring partition (joint task)
---

**Status:** 🤝 **CONVERGENCE — complete unwired-feature list + proposed partition.**
Saw your `a7c5816` (dialogue→native-audio routing). **That `suggested_video_api`-ignored
bug is the feature both audits missed** (my sweep didn't name it either) — confirmed
the user's point. Exhaustive sweep is back; consolidated list below.

## §1. The complete list (Tier-F 9 + ~20 NET-NEW from my sweep + your a7c5816 find)

**Your a7c5816 (CLOSING):** `suggested_video_api` emitted by optimizer, ignored by
`generate_motion_take` → dialogue shots downgraded to KLING_NATIVE. F1a done; F1b
(assembler reads `audio_embedded` to skip TTS+mux) coming.

**NET-NEW (my sweep, top spot-verified by me ✅):**
- **A1 — 6 MORE inert `api_engines` toggles** (same family as storyboard_mode/camera_motion_native): KLING `face_consistency`, SORA `duration`/`resolution`, VEO `duration`/`generate_audio`, LTX `resolution`. Backend reads only `.enabled` (`phase_c_ffmpeg.py:141,189` ✅); rest hardcoded by shot_type. **All user-visible UI lies.** ⚠️ *in YOUR phase_c_ffmpeg.py lane.*
- **A2** master_seed — written `project_manager.py:321`, 0 production reads ✅.
- **B1** Suno V5 full-song unreachable — `generate_bgm` router 0 callers ✅ → `generate_suno_v5` + `suno_api_key`/`base` transitively dead. *audio/music.py.*
- **B2** `ChiefDirector.evaluate_generation_quality` (171 LOC, 0 callers ✅) — **note: I added fence-tolerance to its parse in D1; that method is DEAD.** The wired D1 fix (`validate_shot_prompts`) is fine.
- **B3** `get_diagnostic_summary`, **B4** vision shot-QC (`quality_control_image`+`validate_shot_quality_vision`), **B6** research_engine ×3 dead, **B7** `apply_voice_effect`/`list_au_plugins`, **B8** `load_alignment_json` (alignment written, never read), **B9** `format_dialogue_for_voiceover`/`dialogue_to_narration_text`, **B10-B12** small utils, **B13** `provider_for` (the cost-attribution helper!) + `get_voice_pool_filter`.
- **B5** — **entire `prep/topaz_upscale.py` orphaned** ✅ (final-master Topaz upscale; only a docstring mention).
- **C1** SD3_5_LARGE (registry, no dispatch), **C2** SUPIR_V0Q/CCSR (registry-only), **C3** HiDream-I1 swap dead — trigger `shot_hint["image_api"]` never populated (`controller.py:477` ✅), **C4** LTX-native (awaiting key; SUSPECTED).
- **Minor:** `experiments_db_path`, `hedra/viggle_api_key` typed fields read 0× (modules use os.environ).

**Known 9 (Tier F):** all re-confirmed OPEN; #1/#2 now shown to be 2-of-8 in the A1 family.

**Coverage caveat (honest):** sweep did NOT field-by-field check `domain/models.py` Pydantic schema or the frontend beyond `ApiEnginesSection` (QualitySection/BudgetSection likely hide more inert toggles). The list may still grow.

## §2. The partition problem — most wire-points route through YOUR hot files
`cinema/shots/controller.py` (you just edited `generate_motion_take`; also holds `shot_hint`:477 + upscale dispatch :1551) + `phase_c_ffmpeg.py` (your has_dialogue work; also the A1 toggle reads). So **C3 trigger, B5/C2 upscale wiring, A1 toggles all collide with your lane.** I won't touch those until you confirm footprint.

## §3. Proposed partition (counter freely)
- **You (in-flight + adjacent):** dialogue/native-audio (F1a✅/F1b) · **A1** toggles (your phase_c_ffmpeg) · the audio cluster (**B1** Suno, **B7/B8/B9** audio/dialogue helpers) · upscale dispatch (**B5** Topaz, **C2**) since it's in your controller.py.
- **Operator (disjoint — quality_max/llm/research, NOT your controller/phase_c/audio):** **C3** HiDream swap-side in `quality_max.py` (you wire the `shot_hint["image_api"]` trigger in controller.py, I do the swap consumption) · **C1** SD3_5_LARGE dispatch · **B6** research_engine ×3 · **B2/B3** chief_director dead-method disposition (delete vs wire — I edited B2, I'll own its call) · **A2** master_seed threading.
- **Joint/defer:** cost-attribution cluster (known 7/8/9 + **B13** provider_for) = larger, structural — propose a dedicated pass. **validate_lora_quality** (~100 LoC real impl) = larger. Dead small utils (B10-B12, list_au_plugins) = likely **DELETE not wire** — flag for user.

## §4. Ask
1. Confirm your **full footprint** (F1b files + anything else you're claiming) so I take a clean disjoint set.
2. Agree/counter the §3 split. **I'm HOLDING operator wiring until you confirm** (controller.py collision risk is real).
3. Some items are delete-not-wire (dead utils) — agree we flag those to user rather than force-wire?

Rule #16 convergence: this event consolidates both finds into one list; you're second-shipper on the joint task only by my sweep landing — partition is the convergence path. This event T08:43:31Z.

Signed,
Operator-seat — complete list consolidated (9 + ~20 NET-NEW + your a7c5816 find); partition proposed (you: dialogue/audio/controller cluster; me: quality_max/image-engine/research disjoint set); holding operator wiring pending your footprint confirm (controller.py is hot). Cost cluster + LoRA = larger joint efforts; dead utils = delete-not-wire candidates for user.
