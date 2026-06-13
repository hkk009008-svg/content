# Director-Seat Transplant Handoff — 2026-05-29 (cycle 17 POST-MID-7)

**Outgoing director-seat session:** cold-pickup at `7837ffb` (POST-MID-6) → **hybrid-dialogue voice-routing PLAN** (`42bd014`, build deferred) → resolved a "two-director-sessions" confusion (it was an operator-spawned chip session, not a rival) → **memory cost_log correction** → **Veo native-audio investigation** (found a confirmed multi-bug) → **Veo config-threading fix: spec → plan → implement → review → SHIP** (`8846134` + `f6d6995`) → operator convergence (heads-up `4e12a1a` saved a wasted live test; close `e91d86b`) → this handoff.
**Inheritor:** next director-seat.
**Prior handoff:** `docs/HANDOFF-director-transplant-2026-05-29-cycle17-post-mid-6.md`.
**Companion (operator, active this session):** char+PuLID PASS → pod bridge CLOSED (`9f0256d`); cost_log provenance fix (`def2fe5`/`2c5ca05`, Lane-V'd ✅ `9866c00`/`3e216f8`); veo model-id fix (`39d095e`); **stopped** their Veo dialogue test (`3d51b1e`); flagged the headless plan-review-gate stall (event `T10:23:57Z`).
**HEAD at handoff:** `e91d86b`, origin synced 0/0.
**Pytest:** `1251 passed / 3 skipped` (verified `.venv/bin/python -m pytest tests/unit/ -q` at `f6d6995`; `e91d86b` is docs/mailbox-only). **§15 smoke OK** (`.venv/bin/python scripts/ci_smoke.py` → `OK`).
**Pod:** Novita H100 UP (unchanged from POST-MID-6).

---

## TL;DR — Veo native audio was silently broken; now fixed. Hybrid-dialogue planned. A headless gate blocks live E2E.

1. **⭐ Veo config-threading fix SHIPPED** (`8846134` + `f6d6995`). The dialogue→Veo "native audio" path was **non-functional end-to-end**: `veo_native.generate_video()` built `GenerateVideosConfig` with only 2 hardcoded fields and routed everything else wrong — `reference_images`/`reference_video` passed as **top-level kwargs the SDK rejects** (TypeError → Veo failed → cascade; VEO_NATIVE-only = shot fails), and `generate_audio`/`duration`/`resolution` **never set** (silent video). Fixed via a pure `_build_generate_videos_config()` + `_parse_duration_seconds()`: refs wrapped in `VideoGenerationReferenceImage(ASSET)` **inside** the config; audio/duration/resolution threaded; **driving-video is now image-only** (SDK `image`/`video` are mutually exclusive — a cold-context review catch). Suite 1251/3; review verdict SHIP. Spec+plan in `docs/superpowers/{specs,plans}/2026-05-29-veo-native-config-threading*`.
2. **Hybrid-dialogue voice-routing PLAN** (`42bd014`, build DEFERRED) — from spec `d81f534`; pure `resolve_dialogue_routing()`; per-character `native_voice` casting → native-AV (purpose-fit-then-quality ranked) vs ElevenLabs+lip-sync. Decisions D1-D6 (incl. D5: with Vertex live, default flips dialogue from Veo-model-voice to the character's cast voice). 2× plan-reviewed. `docs/superpowers/plans/2026-05-29-hybrid-dialogue-voice-routing.md`.
3. **⚠️ Headless plan-review-gate stall** (operator finding `T10:23:57Z`) — `CinemaPipeline.generate()` hangs at the plan-review/auto-approve gate **before the first keyframe** in a script run (no web UI). **UNOWNED, not root-caused.** Blocks **all** headless E2E — incl. live-validating the Veo fix + the operator's `run_veo_dialogue_test.py`. Highest-leverage open item.
4. **cost_log provenance fix** (`def2fe5`/`2c5ca05`, operator-spawned chip session; Lane-V'd ✅) — pod keyframes now log `provider='comfyui'` (was hardcoded `fal/FLUX_KONTEXT`); **"provider != fal" is a real pod discriminator again**. char+PuLID bridge CLOSED (`9f0256d`).

---

## What's CLOSED + verified this session

| Item | Status | Refs |
|---|---|---|
| Veo config-threading fix (3 bugs) | ✅ shipped; 1251/3; review=SHIP; SDK-verified vs google-genai 2.6.0 | `8846134`, `f6d6995` |
| Veo fix spec + plan | ✅ spec-reviewed + 2× plan-reviewed | `e426e0e`/`2c4ec31`, `41242b5`/`b45a302` |
| Hybrid-dialogue plan | ✅ planned, build deferred | `42bd014` |
| Operator's live Veo test convergence (Rule #16) | ✅ heads-up `4e12a1a` (saved a wasted run — operator stopped at 0 takes); close `e91d86b` | — |
| "Two director sessions" confusion | ✅ resolved — operator-spawned chip session (provenance fix), NOT a rival director | — |
| Memory cost_log framing | ✅ corrected (MEMORY.md + `director_transplant_handoff.md`, local) | — |

---

## 🟡 OPEN ITEMS (next director)

1. **⚠️ Headless plan-review-gate stall — UNOWNED, high-leverage.** Root-cause + fix unblocks **all** headless E2E (the Veo-fix live validation, the operator's harness, any script-run pipeline). Operator's symptom: `current_stage=SCENE`, shots `plan_status=pending_review`, 0 keyframes, PID idle w/ `CLOSE_WAIT` sockets → either auto-approve must be explicitly enabled for headless (config) OR the auto-approve judge LLM call hung. Start at `cinema/review/controller.py:243 _run_auto_approve_pass`.
2. **Live E2E validation of the Veo fix** — gated on #1 + spend authorization. Harness = operator's `scripts/run_veo_dialogue_test.py` (forces VEO_NATIVE + dialogue + screening-off + $5 cap). **VEO_NATIVE now incurs real Veo spend** (it used to TypeError→cascade).
3. **Hybrid-dialogue build** (`42bd014`, deferred) — now has a *working* Veo audio path underneath (post-fix); still needs #1 + Veo native-audio live-validated for its live tier. Resume at subagent-driven-development.
4. **GPU backlog** (unchanged): HiDream firing · storyboard/dialogue validation · research Part 2 · max-tier SUPIR/HiDream · pod-independent B2 + SD3_5 (spec-able now) · upscale (user design decision) · scene-transitions real-render · doc-maint graduation N≥3.

---

## What the next director needs to know

1. **The "two director sessions" was an operator-spawned chip session** (the cost_log provenance fix the operator filed as a spawn-task), NOT a rival director. A spawn-task chip launches a fresh independent session that self-identifies its role by work-TYPE (provenance/cost_log = strategic = director-voice). All seats commit under one git identity (`hkk009008-svg`); tell them apart by **event voice/content**, not author.
2. **Shared-index sweep is a live failure mode** — `2c5ca05` swept a director's staged WIP (8 files) into an operator handoff commit because `git commit` commits the *whole* index. **ALWAYS** `git commit -- <pathspec>` + check `git diff --cached` first. Both seats hit it; both now disciplined. (Candidate Rule #7 refinement.)
3. **Veo fix — driving-video motion-conditioning is NOT wired** (no correct SDK slot on the image-to-video path: `video=`/`source.video` is for video *extension*, mutually exclusive with the start `image`). The param is accepted for interface stability but produces image-only; wiring it needs a separate `GenerateVideosSource` design (spec §4.2). Don't pretend it works.
4. **Implementation lane:** the Veo fix was done in **main context** (not subagent-orchestrated) per CLAUDE.md's small-tightly-coupled-single-file carve-out (2 files, ~60-80 LOC, coupled tasks), then independently code-reviewed. Appropriate for that size; the hybrid-dialogue build (≥5 files) should be subagent-driven.

---

## Mailbox state at handoff

Director cursor advanced **`T08:42:54Z` → `T10:23:57Z`** (consumed operator's `T09-02-55Z` sweep race-ack + `T10-23-57Z` convergence reply). Last director-sent: **`T10:45:09Z`** (`e91d86b` — veo-fix-landed close + cost note + headless-gate-blocks-live reminder). **0 genuine director-unread** — modulo the STATE.md hook false-positive (it counts `sent/*.md` in BOTH directions vs a stale `seen/` mtime; reconcile against `sent/` + this cursor).

---

## Sign-off

Cycle-17 POST-MID-7. Picked up at `7837ffb`; the headline is **the dialogue→Veo native-audio path was silently broken (config never threaded) and is now fixed + shipped** (`8846134`+`f6d6995`, 1251/3, review=SHIP) — discovered while planning the user-directed Veo validation. Also: **hybrid-dialogue voice-routing planned** (`42bd014`, deferred), the **cost_log provenance fix** closed the pod-vs-FAL discriminator (operator-spawned chip), and the **two-director confusion** was resolved (spawned chip, not a rival). Biggest open item: the **unowned headless plan-review-gate stall** that blocks all live E2E. Both seats coalesced, origin synced. Coordinate with the operator (they own the live validation tier + flagged the headless gate).

Signed,
Director-seat — 2026-05-29 (cycle 17 POST-MID-7).
