# Operator Transplant Handoff — 2026-06-03 (VIDEO HALF SOLVED + program test/audit plan authored)

*Last verified: 2026-06-03. Branch `feat/max-tier-provisioning` @ `61554a0` (7 unpushed
commits this session). §15 smoke `OK`. Pod `07ed667` gateway → **HTTP 502 (ComfyUI down)**
— see ⚠️ pod note below.*

## ★ READ FIRST — what this session did

Four things, in one long session:

1. **VIDEO HALF SOLVED** — the dialogue architecture is decided: **Veo (video) → lip_sync OVERLAY(your TTS)** gives Veo's best-in-class visual *and* a consistent character voice. Veo native for single non-dialogue shots.
2. **Hedra Character-3 wired** (`hedra_native.py`, `cb31207`) as the lip_sync GENERATION-cascade ATTEMPT-0 — now an **optional premium fallback** (Veo+overlay won the dialogue call; the $30/mo Hedra Creator sub is **droppable**).
3. **Char-LoRA v2 confirmed** — stronger than v1 but **run at strength 0.55, NOT 1.0** (1.0 over-bakes → back-of-head).
4. **Program test/audit plan authored** (the user's main ask): a manual-intent-grounded **spec** + a **plan-reviewed Plan 1**, both committed. **Plan 1 is NOT executed yet** — it's the clean pickup point.

## Current state (verified at write)

- **Branch:** `feat/max-tier-provisioning` @ `61554a0`. **UNPUSHED** — 7 commits this session: `50c6831` `fb04c6f` `cbcd45a` `cb31207` `6c3e196` `620e81f` `61554a0`.
- **§15 smoke:** `OK` (`.venv/bin/python scripts/ci_smoke.py`).
- **⚠️ Pod `07ed667`:** gateway `/system_stats` → **HTTP 502 = ComfyUI is DOWN** (per `pod-ssh-credential.md`, "502 = ComfyUI down, not a bad URL"). **502 does NOT tell you if the VM is still running/billing.** It was billing all session and I could not stop it (only the user can, via the Novita console). **VERIFY in the Novita console whether the VM is still running; stop it if so.** If you need the pod again: restart ComfyUI per `pod-ssh-credential.md` (SSH `-p 38597 root@35.164.116.189`, password in that local-only memory file).
- **Uncommitted (intentional, not swept):** SUPIR-A bake (`pulid_max.json`, `workflow_selector.py` — prior session, deprioritized) + ~25 untracked `scripts/_*.py` scratch + `logs/` + `.claude/launch.json`. All commits this session used **explicit pathspec** (shared index / D-a discipline).

---

## 1. VIDEO HALF — the dialogue decision (THE headline)

**Blocker (now understood):** Veo's RAI filter blocks *hyper-photoreal talking-heads*. Root cause (systematic-debugging Phase 1, evidence-backed): it's an **OUTPUT filter** ("videos were filtered out … violated Vertex AI's usage guidelines", no category, no bypass), **threshold-sensitive** — the SAME Veo path PASSED on our production keyframe but BLOCKED 3/3 on the hyper-processed max-tier SUPIR keyframe (`max_super_supirA`). `person_generation` is already `allow_adult`; no config fixes it. **Veo also has NO audio-input and NO voice_id** (verified across Vertex + Gemini + both SDKs) — so you cannot make Veo use a consistent voice natively.

**4 dialogue approaches tested** on the SAME keyframe (`logs/falprod_v2s055_4_studio.jpg`, v2@0.55) + SAME TTS line (`domain/projects/66c9483624ab/temp/audio_scene_34acebe7b968.mp3`):

| Approach | Visual | Voice | Sync | Clip |
|---|---|---|---|---|
| Veo native-audio | 🏆 best | Veo's own (varies) | native | `logs/veo_v2studio_clip.mp4` |
| Omnihuman v1.5 (fal) | good | your TTS | good | `logs/lipsync_gen_v2studio.mp4` |
| Hedra Character-3 (direct API) | very good | your TTS | 0.955 | `logs/hedra_v2studio.mp4` |
| **Veo + sync.so-v3/MuseTalk overlay** | 🏆 **Veo's** | ✅ **your TTS** | **0.955** | `logs/veo_musetalk_v2studio.mp4` |

**DECISION (user):** **dialogue = Veo video → `lip_sync` OVERLAY(your TTS); Veo native for single shots.** Veo's look + consistent voice. (All 4 clips preserve identity — verified by frame inspection.)

**Hedra wiring (`cb31207`):** `hedra_native.HedraAPI.generate_talking_head` (direct `api.hedra.com/web-app/public`, Character-3 `d1dd37a3-…`) is the GENERATION-cascade ATTEMPT-0, replacing the **dead** `fal-ai/hedra/character-3` (HTTP 404). Key in `.env` `HEDRA_API_KEY` (gitignored). **Optional now** — Veo+overlay won; keep as premium fallback or drop the sub.

**lip_sync bug (fixed):** `lipsync_generation`/`lipsync_overlay` had a settings-param-shadowing crash (the `settings` param shadowed the frozen-dataclass module global). Fixed by the user's spawned task → `cbcd45a` (routes the 5 `.fal_key` checks through `ENV_SETTINGS`).

---

## 2. CHAR-LoRA v2 (image-half follow-up)

v2 (`logs/char_lora_fal_v2.safetensors`; 2500 steps, 6 md5-deduped refs — dropped the duplicate `ref_0.png`) is **stronger than v1 but must run at inference strength ~0.55** (at 1.0 it over-bakes → back-of-head). At 0.55 it beats v1: `1_window` 0.612→0.737, `4_studio` 0.556→**0.783**. **The lever was strength, not step count.** Banked: finding in the prior realism handoff (`50c6831`), method scripts (`fb04c6f`: `_fal_lora_train.py` + `_fal_lora_production.py`). Reproduce: `FALPROD_LORA=char_lora_fal_v2.safetensors FALPROD_LORA_STRENGTH=0.55 … scripts/_fal_lora_production.py`. (Full image-half context: `docs/HANDOFF-operator-transplant-2026-06-02-realism-char-lora.md`, its §ADDENDUM.)

---

## 3. TEST/AUDIT PLAN (the user's main deliverable)

- **Spec:** `docs/superpowers/specs/2026-06-02-program-test-audit-plan-design.md` (`6c3e196` + review-fix `620e81f`). Manual-intent-grounded (Part 0 = success criteria S1–S14); Parts 1 capability ledger / 2 prune / 3 fix / 4 UI / 5 cost-tiered sequencing. **Extends** the prior `75ada03` capability-test-suite design. Spec-reviewed (2 blocking factual errors caught + fixed).
- **Plan 1 (execution):** `docs/superpowers/plans/2026-06-03-dialogue-machinery-phase-a1.md` (`61554a0`). 3 **offline ($0)** tasks: (1) fix `storyboard_mode` stale manifest, (2) document `hedra_native` in `ARCHITECTURE.md §10.6`, (3) characterization tests for `hedra_native` (7 branches, mocked HTTP). **Plan-reviewed** — caught a blocking bug (`settings` is `@dataclass(frozen=True)` → can't monkeypatch; fixed via the `_api()` instance-key-inject, reviewer-verified to pass). **NOT executed yet.**
- **Plan 2+ (not written):** remaining zero-test components — `identity/validator.py` (**highest leverage**, S1 core), `style_director.py`, `sora_native.py`, `ltx_native.py`, `phase_c_vision.py` — each needs an **interface survey first** (don't write TDD code for unread components). Then prune verification, the **Veo+overlay routing wire** (`generate_lip_sync_video`/`lip_sync_mode` @ `lip_sync.py:680` + `motion_render` — this is the Part-3 HIGH fix that makes the §1 decision real in the pipeline), and the bigger fixes (`validate_lora_quality` stub, audio-uncapped budget).

---

## OPEN ITEMS (priority order)

1. **Execute Plan 1** — 3 $0/offline tasks, reviewer-verified. Use `superpowers:subagent-driven-development` (or, since tiny, direct in main context per the CLAUDE.md Lane-A heuristic).
2. **⚠️ Verify pod billing** (Novita console) — 502 ≠ stopped. Stop the VM if running.
3. **Wire the Veo+overlay dialogue route** as default (Part-3 HIGH; makes the §1 decision real in the pipeline).
4. **Plan 2** — interface-survey + tests for the 5 remaining zero-test components.
5. **Push** `feat/max-tier-provisioning` (7 unpushed commits) — user/director call.
6. **Hedra subscription** — droppable (Veo+overlay won dialogue); user's call.
7. **Uncommitted durability** — `scripts/_hedra_test.py` is the cited reference for `hedra_native.py`; `_musetalk_overlay_test.py` / `_veo_from_keyframe.py` / `_lipsync_gen_test.py` are the dialogue-test harnesses. Decide what to commit (per the prior "what's durable" deferral).
8. **Memory** (director-default) — the §1 dialogue decision + v2@0.55 should land in `MEMORY.md`.

## Key gotchas

- **`config/settings.py` is `@dataclass(frozen=True)`** → cannot monkeypatch `settings` (`FrozenInstanceError`). Inject on the instance (see Plan 1 Task 3 `_api()`).
- **Veo:** no audio-input, no voice_id. Consistent voice = Veo video + overlay your TTS.
- **v2 LoRA: run @ strength 0.55, not 1.0.**
- **Pod 502 = ComfyUI down** (restart per `pod-ssh-credential.md`) — but verify VM billing first.
- **Shared git index / D-a:** commit with explicit pathspec (`git commit -- <paths>`); never bare `git commit`.

*Verification at write: `git rev-parse --short HEAD` → `61554a0`; `git log --oneline -7` → the 7 session commits; `scripts/ci_smoke.py` → `OK`; pod `/system_stats` → HTTP 502; `git status -s` → SUPIR bake (2 modified) + ~25 untracked scratch.*
