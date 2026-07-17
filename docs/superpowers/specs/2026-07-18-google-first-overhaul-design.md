# Google-First Pipeline Overhaul — Design Spec

**Date:** 2026-07-18
**Status:** Design approved (all four workstreams + open questions resolved by user 2026-07-18).
Next: writing-plans → orchestrated execution.
**Author seat:** director (main context)

## Billing reality (CORRECTED 2026-07-18 — supersedes any "spend my credit" framing)

The user holds a **Google AI Ultra ($200/mo)** subscription. Verified against Google's
own announcement + multiple sources: **AI Ultra is a CONSUMER plan and does NOT fund this
pipeline's programmatic API usage.** Its inclusions (Gemini app limits, Flow/Antigravity
"AI Credits", YouTube Premium) do not cover Vertex AI or Gemini Developer API calls, which
bill **pay-as-you-go** on the project's Cloud / AI Studio billing account. A rumored
"$100/mo Cloud credit" is NOT in Google's official inclusions — treat as unconfirmed.

**User decision (informed):** proceed Google-first anyway, for the **quality** win (Omni
Flash is arena #1), accepting pay-as-you-go cost. The rationale is quality, not free credit.

**Verified environment (2026-07-18, read-only checks):** Vertex AI (`aiplatform`) ENABLED,
Gemini Developer API (`generativelanguage`) ENABLED, ADC token VALID, project
`project-ffb1f53f-bb4c-4add-8e7`, account `hkk009008@gmail.com`. So Veo 3.1 runs full
**video+audio via Vertex**; Omni Flash runs via the Gemini Developer API (not on Vertex yet).

## Provenance / evidence base

- Deep-research run `wf_e57971f7-a98` (video/lipsync/identity/TTS, 105 agents) and
  `wf_30861a3d-404` (ComfyUI/pod/identity, 109 agents), both 2026-07-17→18.
- Prior verified doc `docs/RESEARCH-2026-07-10-component-upgrades.md`.
- Live API verification 2026-07-18 (WebSearch/WebFetch): Gemini Omni Flash, Veo 3.1,
  Nano Banana (Gemini 2.5 Flash Image).
- `DECISIONS.md` ADR-024 (max-tier over-cook is structural), ADR-025 (production FLUX
  PuLID validated OFF 0.62 → ON 0.88).

**CAVEAT (R-MEASURE / R-EVIDENCE):** all prices, model IDs, and API surfaces below are
web-sourced 2026-07-18 claims verified while the safety classifier was intermittently
unavailable. Re-verify each against a live call at integration time before it becomes
load-bearing. Nothing here is a repo-measured artifact yet.

---

## Motivation

Two user directives converge:

1. **Simplify the pod** — the max image-gen tier is complicated without proportional
   benefit. ADR-024 proved (3 independent probes) its over-cook is *structural* to the
   60-node graph; retiring it removes ~2,000 LOC and 6 of 7 custom node packs.
2. **Spend Google credit** — the user holds substantial Google (Gemini Developer API)
   credit and wants Google models to be the most-used route across video *and* image.
   The July-2026 arena also makes this a quality *upgrade*, not just a cost play:
   Gemini Omni Flash is the #1 image-to-video model; Nano Banana leads managed
   multi-reference image identity.

## Non-goals

- FLUX.2 / Qwen managed-image A/B (deferred; Nano Banana becomes the de-facto A/B).
- Full pod retirement (explicit user decision: **keep the production pod** as fallback).
- Deleting the per-character LoRA training subsystem (kept dormant for the future A/B).
- TTS changes (research gap; `eleven_v3` already wired; out of scope this pass).

---

## Workstreams

Four independent, separately-shippable workstreams. Suggested land order: WS4 → WS1 →
WS2 → WS3 (cheapest/safest first; WS3 highest blast radius last).

### WS1 — Retire the max image-gen tier (keep LoRA dormant)

**Delete:** `quality_max.py` (1,297 LOC), `pulid_max.json` (60-node graph),
`MAX_QUALITY_TEMPLATES` + accessor in `workflow_selector.py`, 8 max-only tests
(`test_quality_max_*.py`, `test_max_quality_templates.py`,
`test_max_wide_pulid_startat_gap.py`, `test_hires_fix_pass2.py`). Sweep the
`scripts/_max_*.py` experiment drivers separately (low-risk, ~20 files).

**Modify (sever `quality_tier == "max"` fork):** `phase_c_assembly.py` (drop max branch
~L152), `workflow_selector.py`, `domain/scene_decomposer.py` (`is_max` / best-of-N
`candidate_count>1`), `cinema/shots/controller.py` + `strategy.py` (`MAX_TIER_MULTI_LORA`
/ `fidelity="pulid"` branch → all shots ride `fidelity="reference"`),
`cinema/auto_approve.py` (max composite threshold), `cinema/capability_scorecard.py`,
`cost_tracker.py` (max cost rows + `QUALITY_MAX` provider entry).

**Preserve (dormant):** `prep/lora_training.py`, `prep/lora_quality.py`,
`web_server.api_train_lora`, the `char_lora_paths` write path, and their tests. Repoint
`test_char_lora_strength_thread.py` to assert *storage*, not max-tier *consumption*.

**Safety invariant:** retiring max does NOT strip identity from production. Production
`pulid.json` still runs `ApplyPulidFlux` (ADR-025: OFF 0.62 → ON 0.88). Only the
LoRA-augmented dual-character path (which only ever worked on the over-cooking graph) is
suspended, and its *training* half survives.

**Acceptance:** `ci_smoke` green; full suite green after max tests removed / LoRA tests
repointed; `grep -rn 'quality_max\|MAX_QUALITY_TEMPLATES\|pulid_max' --include='*.py'`
returns only the preserved-and-intentional sites (none in the production render path);
a production-tier image gen still returns `COMFYUI_PULID` and clears the arc gate.

### WS2 — Google-first VIDEO (wire Gemini Omni Flash, reorder cascades)

**New client:** `gemini_omni_native.py` — `GeminiOmniAPI.generate_video(image_path,
prompt, reference_images=[], aspect_ratio, output_path)`. Uses `google-genai`
`client.interactions.create(model="gemini-omni-flash-preview", input=[{image},{text}])`;
`generation_config.video_config.task ∈ {image_to_video, reference_to_video}`; delivery
`"data"` (inline base64 <4MB) or `"uri"` (poll until `state=="ACTIVE"`). Duration /
resolution / audio are prompt-inferred (NOT configurable) — encode intent in the prompt.
Key from `settings` (`GOOGLE_API_KEY`/`GEMINI_API_KEY`). Mirror `veo_native.py`'s
graceful-None-on-failure contract so the cascade falls through cleanly.

**Cascade dispatch:** add a `GEMINI_OMNI` branch in `phase_c_ffmpeg.py` alongside the
existing `VEO_NATIVE` branch (~L420). Add to the native-branch allow-lists (L34/L56).

**Reorder** `workflow_selector.py` `WORKFLOW_TEMPLATES` (`target_api` + `video_fallbacks`)
so Google holds the top two slots of every shot type:

| Shot | New primary → fallbacks |
|---|---|
| Portrait | `GEMINI_OMNI` → `VEO_NATIVE`, `KLING_3_0`, `SEEDANCE` |
| Medium | `GEMINI_OMNI` → `VEO_NATIVE`, `KLING_3_0`, `SEEDANCE`, `LTX` |
| Wide | `GEMINI_OMNI` → `VEO_NATIVE`, `LTX`, `KLING_3_0` |
| Action | `GEMINI_OMNI` → `VEO_NATIVE`, `SEEDANCE`, `KLING_3_0` |
| Landscape | `GEMINI_OMNI` → `VEO_NATIVE`, `LTX` |
| Dialogue | `GEMINI_OMNI` → `VEO_NATIVE`, `OMNIHUMAN` |

**Cost/attribution:** add `GEMINI_OMNI` → `"google"` in `cost_tracker._provider_map`
(before any `GEMINI`/`VEO` fal prefix); add a `GEMINI_OMNI` cost row (~$0.112/s, verify).

**Scene decomposer:** teach `domain/scene_decomposer.py` + `pipeline_context.md` that
`GEMINI_OMNI` is the video primary so LLM `target_api` decisions prefer it.

**Preview caveat:** `gemini-omni-flash-preview` may change without notice — Veo 3.1
(already wired, native audio via Vertex) is the immediate fallback that absorbs any Omni
Flash instability. Not on Vertex yet → Gemini-API billing only.

**Acceptance:** a live `GEMINI_OMNI` i2v call returns a downloadable mp4 attributed to
`google`; on forced Omni failure the cascade falls to `VEO_NATIVE`; `ci_smoke` green.

### WS3 — Google-first IMAGE (wire Nano Banana, pod → first fallback)

**New client / route:** `GEMINI_IMAGE` (Nano Banana, `gemini-2.5-flash-image`) via
`google-genai` standard generate. Accepts a prompt + **up to 20 reference images** for
character consistency + 10 aspect ratios. Key from `settings`. Returns image bytes.

**Cascade reorder** `phase_c_assembly.generate_ai_broll`: `GEMINI_IMAGE` (primary) →
`COMFYUI_PULID` (pod, first fallback) → `FLUX_KONTEXT` → `FLUX_PRO` → `FLUX_SCHNELL` →
`POLLINATIONS`. The identity validator scores every `GEMINI_IMAGE` output; a shot that
fails the arc threshold cascades to the validated pod automatically — this IS the
managed-multi-ref-vs-pod A/B, run as production telemetry with a safety net.

**Identity conditioning:** Nano Banana binds identity via *reference images*, not PuLID
weight. Feed the shot's `primary_reference` + `multi_angle_refs` (+ secondary-char refs,
up to the 20-image budget) as reference inputs. The `_resolve_identity_strategy` fidelity
tag gains a `"gemini_multiref"` value (or reuses `"reference"`) — coordinate with WS1's
router changes so the two edits to the same function compose (Rule #13 sibling audit).

**Cost/attribution:** add `GEMINI_IMAGE` → `"google"`; cost row ~$0.03–0.039/image.

**Watch item (surface, don't silently accept):** Nano Banana's dual-character binding is
unbenchmarked against the pipeline's 0.870 LoRA baseline. The arc-gate fallback makes
demotion safe, but WS3 should log a per-shot Nano-Banana-vs-pod arc comparison so the
future full-pod-retirement decision has data. Silent quality regression is the failure
mode to guard against.

**Acceptance:** a `GEMINI_IMAGE` gen returns an image attributed to `google` that clears
the portrait arc gate on a single-character shot; a forced failure falls to
`COMFYUI_PULID`; identity validator telemetry records both scores.

### WS4 — Hedra removal (dead key)

User confirms the Hedra subscription lapsed / key is dead. `HEDRA_API_KEY` is still
present in `.env`, so the guard `if not api_key: skip` does NOT skip — it burns a full
failed HTTP round-trip on every dialogue shot before falling through.

**Do:** unset `HEDRA_API_KEY` in `.env` (both cascades then skip cleanly at the guard);
remove the Hedra ATTEMPT-0 block from `lip_sync.py` (generation cascade → OmniHuman/Kling
become the still→talking-head path) and from `performance/driving_video.py` Mode-B
(→ SadTalker); retire `hedra_native.py` and the dead `/v1/audio/talking-image` endpoint
at `driving_video.py:93`; drop `LIPSYNC_HEDRA` / `PERFORMANCE_DRIVING_HEDRA` cost rows.
Note: sync-3 is video-to-video re-sync and does NOT fill the still→talking-head slot —
OmniHuman v1.5 (already ATTEMPT 2) or the unwired Kling AI Avatar v2 Std ($0.0562/s) do.

**Acceptance:** no `HEDRA` symbol remains in a live cascade path; dialogue lipsync still
produces output via OmniHuman/Kling; `ci_smoke` green.

---

## Cross-cutting concerns

- **Rule #13 sibling audit:** WS1 and WS3 both edit `_resolve_identity_strategy` —
  sequence them so the second rebases on the first; never two implementers in parallel on
  that file.
- **Rule #12 grep-the-writes:** for each new `char_lora_paths` / provider-map / target_api
  key, grep the runtime WRITE site before trusting it is populated.
- **Money-lane review:** WS2/WS3/WS4 all touch `cost_tracker` provider attribution and
  cost rows → route each through the `money-gate-reviewer` agent (guards the
  money-loss-gate-source-mismatch + silent-gate-degradation families).
- **Doc staleness (same-commit):** `ARCHITECTURE.md` (two-tier→one-tier; new Google video
  + image primaries; Hedra removal), `DECISIONS.md` (new ADRs: max-tier retirement;
  Google-first routing), `OPERATIONS.md` (env keys), the `ai-video-gen` +
  `comfyui-mastery` skills, `pipeline_context.md`.
- **Orchestration (R-ORCH):** >2,000 LOC across ~18 modules + 2 new clients →
  orchestrate. Main context holds plan + task state; fresh implementer subagent per task;
  spec-reviewer + code-quality-reviewer (+ money-gate-reviewer on money tasks) per diff;
  one clean commit per task. Subagent model = Sonnet default (ASK before any Opus task).

## Resolved decisions (user, 2026-07-18)

1. **Land order:** WS4 → WS1 → WS2 → WS3 (safest/cheapest first). CONFIRMED.
2. **WS3 aggressiveness:** Nano Banana as image **primary**, pod demoted to first fallback
   (runs the managed-vs-pod A/B in production; arc-gate fallback keeps it safe). CONFIRMED.
3. **WS4 Hedra:** retire `hedra_native.py` outright + the dead `/v1/audio/talking-image`
   endpoint; unset `HEDRA_API_KEY`. CONFIRMED (key is dead).
4. **Veo audio:** Vertex verified working → keep Veo as full **video+audio** fallback (not
   video-only). RESOLVED.
5. **Economics:** Google-first for quality, pay-as-you-go accepted (see Billing reality). RESOLVED.
