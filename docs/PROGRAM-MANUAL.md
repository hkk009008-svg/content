# Content — AI Cinema Pipeline · Program Manual & Reference

*A comprehensive macro + micro guide to the program: what it is, how it flows end to end, every subsystem and its key functions, and how to operate it to extract its full capability when generating AI video.*

> **Pull-on-demand only.** Do not load this manual at session start. Before using
> or maintaining it, read [`docs/protocol/program-manual-guide.md`](protocol/program-manual-guide.md).
>
> **Provenance.** Originally generated 2026-05-30 by a read-only deep-research workflow (**Rule #17** — workflow-assisted analysis lanes; rule body in `docs/protocol/claude/director-operator.md`), then re-verified section-by-section against live source. In the 2026-06-09 re-sweep every `file:line` anchor was re-grepped against the current tree (the heavy drift was in `cinema_pipeline.py`, which grew ~140 lines, shifting its method anchors +95–131), every LOC count was re-counted, and references to the since-deleted `PROGRAM-MANUAL-digests.md` were removed. Re-verified 2026-06-09 on branch `claude/manual-md-update-1b3o7f`. **When a line number no longer matches, grep the symbol name — the function/class is the load-bearing reference, not the exact line.**
>
> **Where this fits in the docs.** This is the *narrative + operating* layer. The canonical verified-truth reference is [ARCHITECTURE.md](../ARCHITECTURE.md); run/configure/troubleshoot lives in [OPERATIONS.md](../OPERATIONS.md); design rationale is in [DECISIONS.md](../DECISIONS.md). If any fact here disagrees with `ARCHITECTURE.md`, that file wins.

## Table of Contents
- [1. Executive Overview](#1-executive-overview)
  - [1.1 Who this is for](#11-who-this-is-for)
  - [1.2 The value proposition](#12-the-value-proposition)
  - [1.3 The 30-second mental model](#13-the-30-second-mental-model)
  - [1.4 Headline capabilities](#14-headline-capabilities)
  - [1.5 What makes this powerful](#15-what-makes-this-powerful)
  - [1.6 Durable production controls and truth boundaries](#16-durable-production-controls-and-truth-boundaries)
- [2. The Macro Workflow — the Program as One Flow](#2-the-macro-workflow-the-program-as-one-flow)
  - [2.1 The end-to-end pipeline (one program, eleven stages)](#21-the-end-to-end-pipeline-one-program-eleven-stages)
  - [2.2 The run lifecycle — how `generate()` sequences the phases](#22-the-run-lifecycle-how-generate-sequences-the-phases)
  - [2.3 The human-approval gates](#23-the-human-approval-gates)
  - [2.4 Headless vs. interactive — the same machine, two run modes](#24-headless-vs-interactive-the-same-machine-two-run-modes)
  - [2.5 Checkpoints and resume](#25-checkpoints-and-resume)
  - [2.6 One run, narrated end to end](#26-one-run-narrated-end-to-end)
- [3. Component & Module Topology (the micro level)](#3-component-module-topology-the-micro-level)
  - [3.0 Reading this section: the dual-module shim convention](#30-reading-this-section-the-dual-module-shim-convention)
  - [3.1 Orchestration (the macro-spine)](#31-orchestration-the-macro-spine)
  - [3.2 Web / API surface (the user entry point)](#32-web-api-surface-the-user-entry-point)
  - [3.3 Phase system (the per-shot render loops)](#33-phase-system-the-per-shot-render-loops)
  - [3.4 Review / Gates / Auto-approve / Screening / Checkpoints](#34-review-gates-auto-approve-screening-checkpoints)
  - [3.5 Domain / State (the data model & persistence)](#35-domain-state-the-data-model-persistence)
  - [3.6 LLM brains (the creative-direction layer)](#36-llm-brains-the-creative-direction-layer)
  - [3.7 Script → Scenes → Dialogue → Research](#37-script-scenes-dialogue-research)
  - [3.8 Video generation + routing (the API cascade)](#38-video-generation-routing-the-api-cascade)
  - [3.9 Image / keyframe generation (single production tier)](#39-image-keyframe-generation-single-production-tier)
  - [3.10 Identity / Continuity / Coherence](#310-identity-continuity-coherence)
  - [3.11 Performance capture (engine routing + execution)](#311-performance-capture-engine-routing-execution)
  - [3.12 Post-processing / Assembly / Audio](#312-post-processing-assembly-audio)
  - [3.13 Cross-cutting services](#313-cross-cutting-services)
  - [Known divergences, dead code, and footguns](#known-divergences-dead-code-and-footguns)
- [4. Phase-by-Phase Deep Dive](#4-phase-by-phase-deep-dive)
  - [Stage map and progress checkpoints](#stage-map-and-progress-checkpoints)
  - [Stage 0 — Style rules and BGM (run setup)](#stage-0-style-rules-and-bgm-run-setup)
  - [Stage 1 — Scene decomposition (script → shots)](#stage-1-scene-decomposition-script-shots)
  - [PLAN_REVIEW gate (25%)](#plan_review-gate-25)
  - [Stage 2 — Keyframe / image render](#stage-2-keyframe-image-render)
  - [KEYFRAME_REVIEW gate (55%)](#keyframe_review-gate-55)
  - [Stage 3 — Performance capture](#stage-3-performance-capture)
  - [PERFORMANCE_REVIEW gate (65%, conditional)](#performance_review-gate-65-conditional)
  - [Stage 4 — Motion / video render](#stage-4-motion-video-render)
  - [REVIEW gate (82%)](#review-gate-82)
  - [Stage 5 — Assembly + audio mix](#stage-5-assembly-audio-mix)
  - [SCREENING gate (95%, optional) + Stage 6 — Cleanup & complete](#screening-gate-95-optional-stage-6-cleanup-complete)
- [5. The User Manual — Driving It to MAXIMUM Capability](#5-the-user-manual-driving-it-to-maximum-capability)
  - [5.1 End-to-End Operation: From Idea to Final Film](#51-end-to-end-operation-from-idea-to-final-film)
  - [5.2 The Production Image Tier (the "max" tier was retired)](#52-the-production-image-tier-the-max-tier-was-retired)
  - [5.3 The Capability-Knobs Playbook](#53-the-capability-knobs-playbook)
  - [5.4 "To Maximize X, Do Y" Recipes](#54-to-maximize-x-do-y-recipes)
  - [5.5 Auto-Approve Configuration (the unattended brain)](#55-auto-approve-configuration-the-unattended-brain)
  - [5.6 Behavior-Changing Environment Variables](#56-behavior-changing-environment-variables)
  - [5.7 Global Prompt Control (the master lever)](#57-global-prompt-control-the-master-lever)
- [6. Interconnection & Data Flow](#6-interconnection-data-flow)
  - [6.1 The state model: Project → Scene → Shot → Take](#61-the-state-model-project-scene-shot-take)
  - [6.2 How each subsystem hands off to the next](#62-how-each-subsystem-hands-off-to-the-next)
  - [6.3 The review / gate / checkpoint / resume control system](#63-the-review-gate-checkpoint-resume-control-system)
  - [6.4 The API fallback cascade (in detail)](#64-the-api-fallback-cascade-in-detail)
  - [6.5 The "LLM everywhere" layer](#65-the-llm-everywhere-layer)
  - [6.6 Headless vs. interactive control flow](#66-headless-vs-interactive-control-flow)
  - [6.7 Concurrency, locking, and the SSE queues](#67-concurrency-locking-and-the-sse-queues)
  - [6.8 The whole loop, end to end](#68-the-whole-loop-end-to-end)
- [7. Reference Appendix](#7-reference-appendix)
  - [7.1 Key Files Index](#71-key-files-index)
  - [7.2 Key Functions Index](#72-key-functions-index)
  - [7.3 Config / Env / Flags / Tiers](#73-config-env-flags-tiers)
  - [7.4 Glossary](#74-glossary)
  - [7.5 Troubleshooting / Failure Modes](#75-troubleshooting-failure-modes)
  - [7.6 Plan-vs-Source Divergences & Doc-Drift](#76-plan-vs-source-divergences-doc-drift)


---

## 1. Executive Overview

**Content** is an AI cinema pipeline that turns a written idea — a script, a scene list, a logline — into a finished, photorealistic cinematic video with synchronized audio. You define characters, locations, and scenes through a web interface; the system decomposes each scene into individual shots, generates a face-locked keyframe image for every shot, animates each keyframe into a video clip through a fault-tolerant cascade of commercial video-generation APIs, layers in dialogue, music, and environmental foley, and assembles the result into a single color-graded, loudness-normalized MP4. A metacognitive "Chief Director" LLM critiques the plan before anything renders, and the whole run can either pause for human approval at five review gates or run fully unattended.

### 1.1 Who this is for

| Audience | What this manual gives you |
|---|---|
| **Operators / filmmakers** | A map of every quality lever — which knobs raise character fidelity, which API tier costs what, how to drive a run from "idea" to "final cut," and how to maximize the system's full capability. |
| **Engineers** | An accurate, file:line-traceable reference to the architecture: the orchestration spine, the phase system, the review gates, the data model, and every subsystem's real (verified) call graph. |

### 1.2 The value proposition

The pipeline collapses a traditional multi-week production chain — storyboarding, casting consistency, cinematography, animation, sound design, color, mastering — into a single automated flow, while keeping a human in the loop wherever creative judgment matters. The output is not a slideshow of disconnected clips: characters keep the same face across every shot (PuLID face-locking + GhostFaceNet identity validation), locations keep the same architecture (deterministic per-location seeds), lighting and color stay coherent shot-to-shot, and dialogue is either generated natively with the video (Veo) or lip-synced as a mandatory post-pass.

### 1.3 The 30-second mental model

```mermaid
flowchart LR
    A[Script / scenes<br/>+ characters<br/>+ locations] --> B[Scene → Shots<br/>LLM decompose<br/>+ Chief-Director QA]
    B --> G1{PLAN<br/>gate}
    G1 --> C[Keyframe image<br/>per shot<br/>PuLID face-lock]
    C --> G2{KEYFRAME<br/>gate}
    G2 --> D[Performance<br/>capture<br/>opt.]
    D --> G3{PERF<br/>gate}
    G3 --> E[Motion render<br/>image → video<br/>API cascade]
    E --> G4{REVIEW<br/>gate}
    E --> F[Assemble:<br/>color grade +<br/>3-track audio +<br/>loudnorm]
    F --> G5{SCREENING<br/>gate}
    G5 --> Z[final_cinema.mp4]
```

One orchestrator — `cinema_pipeline.CinemaPipeline` (`cinema_pipeline.py:49`) — drives that entire left-to-right sequence. You enter through the web server (`web_server.py`, a Flask app on port 8080); it constructs the pipeline (`web_server.py:2820`) and streams progress back to the browser over Server-Sent Events. There is exactly one entry point: the legacy CLI (`main.py`) has been deleted (verified: `ls main.py` → no such file).


### 1.4 Headline capabilities

- **Multi-API video generation with a fallback cascade.** A single entry point, `generate_ai_video` (`phase_c_ffmpeg.py:208`), routes each shot. Per-shot-type routing (`workflow_selector.WORKFLOW_TEMPLATES`, `ARCHITECTURE.md` §9.1) tries `GEMINI_OMNI` **first** — the WS2 Google-first video primary for all five shot types — with `VEO_NATIVE` as first fallback; beyond that (or whenever `video_fallbacks=None`, e.g. dialogue native mode), it fails over through the module-level `DEFAULT_VIDEO_CASCADE` — `VEO_NATIVE → SEEDANCE → KLING_3_0 → RUNWAY_GEN4 → LTX → VEO (FAL)` (`phase_c_ffmpeg.py:95`). `GEMINI_OMNI` is deliberately outside this blind default because its duration/resolution/audio are prompt-inferred; deprecated `SORA_NATIVE` and `KLING_NATIVE` are explicit-only, while legacy `RUNWAY` and `SORA_2` are retired with no executable branch. The winning engine's provenance is recorded on every take.

- **Character consistency.** Keyframes are face-locked with PuLID in a ComfyUI workflow; an `IdentityValidator` (`identity/validator.py`) scores every generated frame against the character's reference embedding (GhostFaceNet), and a rolling-stats feedback loop adapts the PuLID weight per character (`workflow_selector.py:337`). Locations stay consistent via a persisted per-location seed (`domain/location_manager.py`).

- **Native audio & dialogue.** The capability registry marks `GEMINI_OMNI` and `VEO_NATIVE` as native-audio routes, and the F1a dialogue override pins the first live video entry in `PURPOSE_API_RANKING[purpose]` — currently `GEMINI_OMNI`, ahead of `VEO_NATIVE`. Backend truth still wins: Vertex/ADC Veo can generate embedded audio, while Developer-API Veo cannot and is treated as silent. Any dialogue take not proven embedded gets the **mandatory F1b lip-sync pass** (`cinema/shots/controller.py`); embedded but unmeasured dialogue remains `UNKNOWN` at final review rather than receiving a synthetic score. Separately, a full audio stack generates TTS dialogue (ElevenLabs / Cartesia for Korean), BGM (Suno / FAL Stable Audio), and environmental foley (Stability AI), mixed into a 3-track final.

- **Single production image tier, Nano Banana primary.** Keyframes render through Gemini 3.1 Flash Image ("Nano Banana 2," `gemini_image_native.GeminiImageAPI`) as the **default image PRIMARY for all projects** (WS3, user-confirmed — a project sets `identity_backend='pod'` to opt out; migrated off the sunset `gemini-2.5-flash-image` in Slice 6b, 2026-07-31); the fallback is FLUX-Dev via RunPod ComfyUI with PuLID face-lock (`pulid.json`) and a FAL fallback cascade — one validated production tier below Nano Banana, no operator tier-selection. (A heavier `"max"` tier — N=8 adaptive best-of with GhostFaceNet/aesthetic scoring, ControlNet, FLUX Redux, FaceDetailer, and SUPIR 4K upscale — was **retired in WS1 Task 4**; `ARCHITECTURE.md` §8.3 keeps the archaeology and ADR-024 records why the max graph was dropped.)

- **Metacognitive Chief-Director QA.** Before any pixels render, a `ChiefDirector` LLM (`llm/chief_director.py`) validates every shot prompt against eight hard constraints (identity firewall, schema/location/lighting locks, face-direction) and returns `APPROVED` / `MODIFIED` / `REJECTED`, or `REVIEW_REQUIRED` when validation is unavailable or malformed (`llm/chief_director.py:296`). Its verdict feeds the PLAN gate; missing evidence cannot clear it.

- **Human-in-the-loop OR fully headless.** Five review gates (PLAN_REVIEW → KEYFRAME_REVIEW → PERFORMANCE_REVIEW → REVIEW → SCREENING) punctuate the run; at each, an auto-approve heuristic clears shots that meet quality thresholds and parks the rest for an operator. Flip `headless=True` (`cinema_pipeline.py:253`) and unsatisfied gates fail fast with a diagnostic (`GateNotSatisfiedError`, `cinema/review/controller.py:93`) instead of blocking — enabling unattended batch runs.

### 1.5 What makes this powerful

- **It never silently produces junk.** Every stage is gated and scored: prompts by the Chief Director, images by GhostFaceNet identity + aesthetic gates, motion by optical-flow fidelity, lip-sync by a SyncNet gate. Failures are diagnosed and routed to rework, not buried.
- **It degrades gracefully, not catastrophically.** Vendor cascades and
  deterministic LLM-free fallbacks (for failures proven before paid
  submission) mean a missing key or rejected request narrows capability. Once
  an LLM/provider call crosses an ambiguous paid boundary, the no-replay fence
  takes precedence: it does not fall through to a second paid provider.
- **It is resumable.** Full-project jobs are accepted into a durable SQLite/WAL queue, and state is checkpointed to disk after every scene. A stopped worker is requeued for checkpoint resume after its lease expires; paid-media adapters either resume the exact provider job ID or fail closed before replacement work.
- **It is yours to tune.** Nearly every behavior is a per-project knob in `global_settings` — quality tier, identity strictness, auto-approve thresholds, scene transitions, budget cap, LLM/judge model — read through one canonical helper (`get_project_setting`, `cinema/context.py:157`). One file, `config/prompts/pipeline_context.md`, is injected into *every* LLM in the pipeline, so global creative direction is a single edit away.
- **It tracks the bill without calling estimates invoices.** A SQLite-backed
  `CostTracker` (`cost_tracker.py`) owns atomic media and planning-LLM
  reservations/reconciliation. LLM success settles from returned tokens and
  repository list prices; media settles from observed outcome and configured
  estimates. Provider analytics label both as estimates, and invoices remain
  authoritative.

The remainder of this manual documents each of these systems in depth — the orchestration spine, the web/API surface, the phase and gate machinery, the data model, the creative-LLM brains, the video-routing cascade, the image tiers, identity/continuity, post-assembly/audio, and the cross-cutting cost/config/ops layer.

### 1.6 Durable production controls and truth boundaries

Seven production controls now share the same project UI and durable evidence:

| Control | What the operator gets | Boundary that must remain visible |
|---|---|---|
| Durable job persistence | Stable queue job ID, queued position, crash recovery through the project checkpoint | One active full-project job per project. Queue persistence alone is not universal exactly-once provider execution. |
| Provider usage analytics | Paid-media, planning, identity, and research-provider success rate, latency, failures, reservations, and known estimated usage | `cost_basis` is `reconciled_estimate`; token-derived list pricing and terminally reconciled media estimates are not invoices. Research cost stays unknown when the API supplies no usage value. |
| Safe queue | Fixed global worker pool, FIFO claims, cancellation, 1..8 concurrency | Acceptance is `202`; it does not claim provider work has started. |
| Artifact versioning | Current/archived history plus generated character assets and rejected paid Gemini/motion/lip-sync candidates, with hashes and recipe/source/dependency provenance | Immutable bytes are retained, but every record truthfully says `bit_exact=false`; retention failure blocks an overwriting fallback. Acquired web references and LLM project JSON remain revision data, not generated binary artifacts. |
| Provider health | Explainable health from paid attempts and planning observations; base-video `AUTO` avoids `unhealthy` engines | Unknown/degraded remain eligible. Pinned engines, LLMs, images, lipsync and performance are not silently rerouted by this score. |
| Client packaging | Select current or historical versions and build a verified content-addressed ZIP | Only allowlisted client media under `exports/`; internal/runtime/credential-like files are refused. |
| Searchable traces | Project-scoped query/level/trace-ID search in the Run telemetry rail | Bounded redacted local SQLite index; JSON stdout remains the deployment log stream. |

The paid-work recovery boundary is adapter-opt-in. FAL queue requests and
ComfyUI prompts resume by their durable IDs, as does native Kling once its task
ID is acknowledged. Native Sora and other no-ID synchronous calls are not
replayed after an ambiguous outcome; they become `accepted_unknown` and require
provider/operator reconciliation. Shared `LLMEnsemble`, Chief Director, Cinema
Director, style, and scene-decomposition calls reserve a deterministic
no-replay paid attempt before each SDK request, reconcile successful token
usage once, and persist latency/outcome. They do not expose provider job IDs to
poll after a crash: repeat safety is a durable refusal, not response recovery.

Claude Vision identity is different: it enters the nonresumable paid-attempt
fence, reconciles SDK token usage after success, and turns an ambiguous
submission into `accepted_unknown` so the identity gate fails closed without a
second paid call. Tavily and Firecrawl persist success/failure/latency
observations; their dollar cost remains unknown when their responses expose no
authoritative usage value.

These surfaces are reachable rather than diagnostic-only: queue state,
provider analytics and traces are on the Run page
(`web/src/components/pages/RunPage.tsx:175`, `:349-350`); artifact history,
version selection and packaging are under Preview → Client delivery
(`web/src/components/PreviewPanel.tsx:36`).

Live canary evidence preserves the same truth boundary: the protected
`runpod-pulid-production` target proves only the shipping PuLID graph on the
pinned image, while `runpod-liveportrait-performance` requires a separate
performance endpoint and `PERFORMANCE_COMFYUI_*` secrets. PuLID readiness is
not LivePortrait readiness (`scripts/live_contract_canary.py:59-85`).

---

## 2. The Macro Workflow — the Program as One Flow

This section traces a single idea from text to a finished, sound-synced cinematic MP4, then describes how the orchestrator sequences that journey, where humans intervene, and how the same machine runs either interactively (web UI) or unattended (headless).

The program has exactly one runtime entry point: `web_server.py` (Flask, port
8080). `POST /generate` idempotently creates or returns one active durable job
for the project (`web_server.py:3310`); a fixed dispatcher later constructs
`cinema_pipeline.CinemaPipeline` and calls `.generate(resume=...)` through the
checkpoint path (`web_server.py:3213-3245`). The old `main.py` CLI is deleted;
there is no second orchestration path.


### 2.1 The end-to-end pipeline (one program, eleven stages)

The pipeline is a fixed, ordered gate sequence: **STYLE → SCENE_DECOMPOSE → PLAN_REVIEW → KEYFRAME_RENDER → KEYFRAME_REVIEW → PERFORMANCE_CAPTURE → PERFORMANCE_REVIEW → MOTION_RENDER → REVIEW → ASSEMBLY → SCREENING → COMPLETE**. Image/keyframe and video stages each have a fault-tolerant *cascade* underneath (multiple vendor APIs tried in priority order), and audio is generated alongside the visuals, then mixed in at the very end.

```mermaid
flowchart TD
    IDEA["Idea / script<br/>(scenes, characters, locations)"] --> STYLE

    subgraph PLANNING["Planning — LLM brain layer (llm/)"]
        STYLE["STYLE<br/>generate_style_rules()<br/>cinema_pipeline.py:958-993"]
        STYLE --> DECOMP["SCENE_DECOMPOSE (per scene)<br/>competitive_decompose_scene / decompose_scene<br/>cinema_pipeline.py:997-1068"]
        DECOMP --> RESEARCH{{"Research augmentation<br/>Tavily / Firecrawl<br/>research_cinematography()"}}
        RESEARCH --> DECOMP
        DECOMP --> DIRVAL["ChiefDirector.validate_shot_prompts<br/>HC1-HC8 → APPROVED/MODIFIED/REJECTED/REVIEW_REQUIRED<br/>+ record_director_review_on_shots (1064)"]
        DIRVAL --> DIALOGUE["Per-scene dialogue + audio<br/>_ensure_scene_audio (1067)"]
    end

    DIRVAL --> G1{{"GATE 1: PLAN_REVIEW<br/>cinema_pipeline.py:1070"}}

    subgraph IMAGE["Keyframe generation — image tiers"]
        G1 --> KF["KEYFRAME_RENDER<br/>KeyframeRenderPhase.run (1089)"]
        KF --> KFCASCADE["per shot: generate_keyframe_take<br/>FLUX+PuLID (ComfyUI) → FAL Kontext<br/>→ FLUX-Pro → Schnell → Pollinations"]
        KFCASCADE --> IDVAL1["Identity validate (GhostFaceNet)<br/>IdentityValidator.validate_image"]
    end

    KF --> G2{{"GATE 2: KEYFRAME_REVIEW<br/>cinema_pipeline.py:1099"}}

    subgraph PERF["Performance capture (optional per shot)"]
        G2 --> PC["PERFORMANCE_CAPTURE<br/>PerformanceCapturePhase.run (1119)"]
        PC --> PCROUTE["route_performance_engine:<br/>ACT_ONE / LIVE_PORTRAIT / VIGGLE / SKIP"]
    end

    PC --> G3{{"GATE 3: PERFORMANCE_REVIEW<br/>cinema_pipeline.py:1140<br/>(auto-skipped if all shots SKIP)"}}

    subgraph VIDEO["Motion / video generation — API cascade"]
        G3 --> MR["MOTION_RENDER<br/>MotionRenderPhase.run (1166)"]
        MR --> MRPATH{"storyboard_mode + non-portrait<br/>+ 2-6 shots + all keyframes?"}
        MRPATH -->|yes| SB["Kling storyboard batch<br/>1 call → split_video_into_segments"]
        MRPATH -->|no| PERSHOT["per shot: generate_motion_take<br/>Gemini Omni→Veo→Seedance→Kling→…"]
        SB --> NATAUDIO["Gemini Omni / Veo NATIVE audio<br/>(the only two native_audio=True engines)"]
        PERSHOT --> NATAUDIO
        NATAUDIO --> POST["Post: face-swap / lip-sync (F1b)<br/>/ RIFE interp / upscale"]
        POST --> IDVAL2["Validate identity + motion (GhostFaceNet + optical flow)"]
    end

    MR --> G4{{"GATE 4: REVIEW<br/>cinema_pipeline.py:1179"}}

    subgraph ASM["Assembly — phase_c_ffmpeg + audio mux"]
        G4 --> ASSEMBLE["assemble_approved_takes (853)<br/>→ _assemble_approved_takes_core (783)"]
        ASSEMBLE --> NORM["normalize clips 1920x1080@30fps"]
        NORM --> STITCH["stitch: hard-cut concat<br/>OR xfade cross-dissolve"]
        STITCH --> GRADE["color grade (mood preset / LUT)"]
        GRADE --> MIX["3-track mix: voice 1.0 + BGM 0.12 + foley 0.20"]
        MIX --> LOUD["two-pass EBU R128 loudnorm<br/>_assemble_final (1323)"]
    end

    LOUD --> G5{{"GATE 5: SCREENING<br/>cinema_pipeline.py:872-905<br/>(iterate + re-assemble loop)"}}
    G5 --> DONE["COMPLETE — exports/final_cinema.mp4<br/>cleanup + cost summary"]

    style G1 fill:#ffe0b2
    style G2 fill:#ffe0b2
    style G3 fill:#ffe0b2
    style G4 fill:#ffe0b2
    style G5 fill:#ffe0b2
    style DONE fill:#c8e6c9
```

**Reading the flow stage by stage:**

| # | Stage | What happens | Primary modules |
|---|---|---|---|
| 1 | **STYLE** | Once per run. If `global_settings.style_rules` is empty, `generate_style_rules()` (GPT-4o, optionally Tavily-grounded) produces a 7-key style dict (cinematography, color grading, lighting, photorealism…) persisted to the project. A `style_rules_to_prompt_suffix` is appended to every downstream image prompt. | `llm/style_director.py:19`; called `cinema_pipeline.py:958-993` |
| 2 | **SCENE_DECOMPOSE** | Per scene (only if the scene has no shots yet). Converts scene prose → 2–5 API-routed shot records. `competitive_generation=True` runs GPT-4o vs Claude in parallel with a judge; otherwise single GPT-4o. Each shot gets `prompt`, `camera`, `visual_effect`, `target_api`, `characters_in_frame`. | `domain/scene_decomposer.py:660`/`:796`; called `cinema_pipeline.py:997-1068` |
| 2a | **Research augmentation** | Optional, silently skipped if `TAVILY_API_KEY`/`FIRECRAWL_API_KEY` absent. A GPT-4o tool-loop (`run_with_tools`) injects live cinematography/location/music references into decomposition and dialogue prompts to ground output in real craft. | `research_engine.py:44`, `web_research.py:122` |
| 2b | **Director review** | `ChiefDirector.validate_shot_prompts` enforces hard constraints HC1–HC8 (identity firewall, schema lock, lighting lock, face-direction) and returns APPROVED / MODIFIED / REJECTED / REVIEW_REQUIRED. Missing clients, malformed replies, and unusable modifications require review. **Critical:** `record_director_review_on_shots(shots, review)` then writes `shot["director_review"]` — the field the PLAN gate reads. | `llm/chief_director.py:296`; `cinema/auto_approve.py:235`; called `cinema_pipeline.py:1064` |
| 2c | **Dialogue + scene audio** | Per scene, `generate_dialogue` (LLM) → `generate_dialogue_voiceover` (ElevenLabs Dialogue Mode for 2+ speakers, or Cartesia Sonic 3.5 for Korean) produces an MP3 cached for later mux. BGM is pre-generated upfront. | `audio/dialogue.py:730`; `cinema_pipeline.py:1067` (audio), `:995` (BGM) |
| 3 | **KEYFRAME_RENDER** | Per unapproved shot, `generate_keyframe_take` builds the prompt via `ContinuityEngine.enhance_shot_prompt`, optionally optimizes it, then calls `generate_ai_broll`: Gemini 3.1 Flash Image is primary for referenced characters; FLUX-Dev + PuLID on ComfyUI/RunPod is the first reference-conditioned fallback, followed by FAL FLUX Kontext → FLUX-Pro → Schnell → Pollinations. A durable per-shot reservation blocks duplicate submissions until success, a safe terminal failure, or explicit operator reconciliation. (The former N=8 **max tier** was retired in WS1 Task 4 — production is the sole image tier.) | `phase_c_assembly.py`; phase wrapper `cinema/phases/keyframe_render.py`; called by `cinema_pipeline.py` |
| 4 | **PERFORMANCE_CAPTURE** | Per shot with an approved keyframe, retargets a performance onto the still: ACT_ONE / LIVE_PORTRAIT / VIGGLE, or SKIP (the domain router decides via `route_performance_engine`). Shots routed to SKIP are passed over with no generation. | `cinema/phases/performance.py:35`, `domain/performance.py:103`; called `cinema_pipeline.py:1119` |
| 5 | **MOTION_RENDER** | Per shot, `generate_motion_take` turns the keyframe into a clip via the policy-gated video cascade. Automatic routing excludes deprecated Sora/Kling Native/legacy Runway; the six-engine blind fallback seed is Veo-Native→Seedance→Kling-3.0→Runway Gen-4→LTX→Veo/FAL. Dialogue routes first to **Gemini Omni**; any take not proven to contain embedded dialogue gets mandatory F1b. The optional Kling Native storyboard batch handles only non-dialogue, non-portrait scenes with 2–6 unapproved shots and approved keyframes. | `phase_c_ffmpeg.py`, `cinema/phases/motion_render.py`; called `cinema_pipeline.py` |
| 5a | **Post-processing** | Identity/continuity correction and finish passes happen at take-generation and operator-correction time: durable PixVerse face swap (FaceFusion only before submission or after explicit unbilled failure), lip-sync cascades with a SyncNet gate, RIFE interpolation, and SeedVR2/Topaz upscale. Stored as additive `postprocess_variants`. | `phase_c_vision.py`, `lip_sync.py` |
| 6 | **ASSEMBLY** | Collects approved takes in scene order, normalizes each to 1920×1080@30fps, stitches (hard-cut concat by default, or `xfade` cross-dissolve when `scene_transitions=True`), applies a mood-mapped color grade, performs the 3-track audio mix (voice 1.0 + BGM 0.12 + foley 0.20), and finishes with a two-pass EBU R128 loudness normalize. Output: `exports/final_cinema.mp4`. | `cinema_pipeline.py:783-851` / `:1315-1431`; ffmpeg helpers in `phase_c_ffmpeg.py` |
| 7 | **SCREENING → COMPLETE** | The operator watches the assembled cut, can iterate individual shots (marking them `needs_reassembly`) and trigger incremental re-assembly, then approves. On approval the run cleans temp artifacts, logs the cost summary, clears the checkpoint, and emits COMPLETE at 100%. | `cinema/screening.py`; `cinema_pipeline.py:853-925` |

**Identity & continuity is a cross-cutting spine, not a stage.** It threads through stages 3–5: `ContinuityEngine.enhance_shot_prompt` injects location fragments, wardrobe continuity, physics constraints, and an adaptive PuLID weight per shot; `IdentityValidator` (GhostFaceNet) scores keyframes and videos and feeds a rolling-stats loop that self-calibrates the next shot's PuLID weight; `coherence_analyzer` checks color/lighting/composition drift between consecutive shots.

### 2.2 The run lifecycle — how `generate()` sequences the phases

`CinemaPipeline.__init__` (`cinema_pipeline.py:55`) composes the run from four collaborators that all share **one** `RunState` reference: long-lived services live on `PipelineCore` (project dict, dirs, `ContinuityEngine`, `ChiefDirector`, `CostTracker`, `LLMEnsemble`); per-run mutable state on `RunState`; pause/cancel/gate-wait/progress on `ThreadedLifecycle`; and the three controllers `ShotController` / `ReviewController` / `CheckpointStore`. The `headless` flag is set here and read by every gate.

`generate(resume=False)` (`cinema_pipeline.py:1244`) then runs the ordered sequence below. Each gate call is the synchronization point between the worker thread and the outside world.

```
generate(resume=False)
 │
 ├─ _refresh_project_snapshot()              # load → model_validate → swap in place (443)
 ├─ [resume] _restore_from_checkpoint() + _rebuild_review_clips()   (954-956)
│
 ├─ STYLE       generate_style_rules() → mutate_project()           (958-993)  ~2%
 ├─ _ensure_bgm(settings)                                            (995)     pre-generate BGM
│
 ├─ for each scene: skip restored completed indices, then process    (997-1068) SCENE_DECOMPOSE
│    ├─ competitive_decompose_scene() / decompose_scene()
│    ├─ ChiefDirector.validate_shot_prompts(shots, scene)
 │    ├─ record_director_review_on_shots(shots, review)             (1064)  ← writes director_review
│    ├─ update_scene_shots(); _save_checkpoint()
 │    ├─ _ensure_scene_audio(scene, chars)                          (1067)
 │    └─ _save_checkpoint(completed_scene_idx=scene_idx)            (1068)
│
 ├─ ╔═ GATE 1 ═╗ _wait_for_gate("PLAN_REVIEW", …, 25)               (1070)
 │
 ├─ KeyframeRenderPhase(self, project).run(ctx)                     (1089)     ~50%
 ├─ ╔═ GATE 2 ═╗ _wait_for_gate("KEYFRAME_REVIEW", …, 55)           (1099)
 │
 ├─ PerformanceCapturePhase(self, project).run(ctx)                 (1119)    ~62%
 ├─ ╔═ GATE 3 ═╗ _wait_for_gate("PERFORMANCE_REVIEW", …)            (1140)  ← skipped if all SKIP
 │
 ├─ MotionRenderPhase(self, project).run(ctx)                       (1166)    ~80%
 ├─ _rebuild_review_clips(project); _save_checkpoint()
 ├─ ╔═ GATE 4 ═╗ _wait_for_gate("REVIEW", …, 82)                    (1179)
 │
 └─ assemble_approved_takes()                                       (853)
      ├─ _assemble_approved_takes_core()                            (783)
      │    └─ _assemble_final(scene_data, bgm, settings)            (1323)  → exports/final_cinema.mp4
      ├─ ╔═ GATE 5 ═╗ wait_for_gate("SCREENING", …)                 (872-905)  ~95%  (if enabled)
      ├─ cleanup_project(); cost_tracker.get_video_cost()
      └─ progress("COMPLETE", final_path, 100%)
```

**Phases vs. gates.** The three render loops (keyframe, performance, motion) are `Phase`-protocol objects that receive a shared `PipelineContext` and return a `PhaseResult`; the four review gates and SCREENING are **inline** in the orchestrator, not phases. Ordinary per-shot failures route through an `on_failure` callback into `RunState.failed_shots` and are reworked from the review UI; structured budget refusals are the exception, stopping performance or motion without spending further.

**Progress and cancellation.** Every stage emits a progress event through `lifecycle.report_progress()` → the per-project SSE queue → the browser. Phases poll `ctx.lifecycle.is_cancelled()` at scene and shot boundaries, so `POST /cancel` interrupts mid-loop. `pause()`/`resume()` block on a `threading.Event`.

### 2.3 The human-approval gates

Five mandatory gates punctuate the run. At each, an **auto-approve heuristic** pre-screens shots against configurable thresholds; whatever it cannot clear waits for a human (interactive) or fails fast (headless).

| Gate | Stage % | Predicate to pass (`_gate_satisfied`) | Auto-approve rule family | Operator endpoint |
|---|---|---|---|---|
| **PLAN_REVIEW** | 25 | every shot `plan_status=="approved"` | `_rules_for_plan`: vetoes unless `director_review.decision=="APPROVED"` and no violations | `…/shots/<id>/plan/approve`·`/reject` |
| **KEYFRAME_REVIEW** | 55 | every shot has `approved_keyframe_take_id` | `_rules_for_image`: production identity/composite evidence ≥ `image_min_composite` (0.60; explicit fallback bar 0.78), no disallowed cascade fallback, within budget | `…/keyframes/<take_id>/approve` |
| **PERFORMANCE_REVIEW** | 65 | each shot has `approved_performance_take_id` **or** is SKIP **or** lacks a keyframe | `_rules_for_motion` — **opt-in only**: requires `CINEMA_AUTO_APPROVE_MOTION=1`, else always manual | `…/performance/<take_id>/approve` |
| **REVIEW** | 82 | every shot has `approved_final_take_id` | `_rules_for_final`: the selected take must have measured lip-sync evidence (`UNKNOWN`/`UNAVAILABLE` always veto, even when the numeric threshold is 0), then lipsync ≥ `final_min_lipsync` (0.8); **`final_require_human_if_upstream_auto` (default True) forces a human here if any earlier gate auto-approved** | `…/final/<take_id>/approve` |
| **SCREENING** | 95 | `project["screening_approved"] == True` | n/a (operator watches the cut; may iterate shots → `needs_reassembly`, re-assemble, then approve) | `…/assemble/screen`, `…/screening/approve`, `…/assemble/re-assemble` |

Each gate is implemented by `ReviewController._wait_for_gate` (`cinema/review/controller.py:519`): it sets `RunState.current_stage`, runs `_run_auto_approve_pass(gate)` (which mutates approved shots and always appends an audit entry to `shot["auto_approve_audit"]`), then either polls `lifecycle.wait_for_gate(...)` at 0.5 s (interactive) or — in headless mode — checks the predicate once and raises `GateNotSatisfiedError` (`cinema/review/controller.py:93`) with per-shot block reasons.

> **PERFORMANCE_REVIEW auto-skip.** When *every* shot is SKIP-routed or has no approved keyframe, the gate is bypassed entirely (`cinema_pipeline.py:1140`) — a SKIP-only production never stops here.

> **The historically dangerous gate is PLAN_REVIEW.** If shots are loaded without running through decomposition, `director_review` is never written and `_rules_for_plan` vetoes forever — the cycle-17 headless stall. The fix is the unconditional `record_director_review_on_shots` call at `cinema_pipeline.py:1064`, and **MODIFIED is now normalized to APPROVED** at the gate (`cinema/auto_approve.py:267`, decision `138d7c7`) so a director-corrected scene no longer dead-ends.

### 2.4 Headless vs. interactive — the same machine, two run modes

The pipeline is one orchestrator; the run *mode* is a single constructor flag plus auto-approve configuration.

```mermaid
flowchart LR
    START["pipeline.generate()"] --> Q{"RunState.headless?"}
    Q -->|"False (web UI default)"| WEB["ThreadedLifecycle.wait_for_gate<br/>polls 0.5s until predicate True<br/>or run cancelled"]
    Q -->|"True (script / E2E)"| HL["check predicate ONCE →<br/>GateNotSatisfiedError if not cleared"]
    WEB --> AA1["auto-approve clears what it can;<br/>operator approves the rest via API"]
    HL --> AA2["auto-approve MUST clear every gate<br/>(no human to fall back to)"]
```

| Aspect | Interactive (web UI) | Headless (`CinemaPipeline(pid, headless=True)`) |
|---|---|---|
| Constructed by | `web_server.py` per `POST …/generate` | Python caller / E2E scripts |
| Lifecycle | `ThreadedLifecycle` — blocks at each gate | `ThreadedLifecycle` — **fails fast** (`GateNotSatisfiedError`) |
| Unblocked by | operator approvals via REST | auto-approve thresholds alone |
| To reach COMPLETE unattended | n/a (human drives) | tune `global_settings.auto_approve`: lower composite/lipsync floors, and **set `final_require_human_if_upstream_auto=false`** (else REVIEW always forces a human) |

> **Headless does NOT use `NullLifecycle`.** This is a sharp, repeated correction. `NullLifecycle` (`cinema/lifecycle.py:70`) is the dead CLI's no-op lifecycle and its `wait_for_gate` returns `True` regardless of the predicate — it would *silently skip* gate enforcement. The only correct non-interactive path is `CinemaPipeline(headless=True)`, which keeps `ThreadedLifecycle` but reads `RunState.headless` in `_wait_for_gate` to raise instead of poll. Any doc claiming "headless uses `NullLifecycle`" is wrong.

### 2.5 Checkpoints and resume

After every scene-loop iteration and after each audio step, `CheckpointStore._save_checkpoint` (`cinema/checkpoint.py:87`) atomically writes `temp/pipeline_state.json` (`tempfile.mkstemp` + `os.replace`), serializing `current_stage`/`scene_id`/`shot_id`, completed scene indices, scene clips/audio/foley, per-shot audio, shot results, and failed shots. `generate(resume=True)` calls `_restore_from_checkpoint()` (`cinema/checkpoint.py:167`), which rejects cross-project checkpoints, rehydrates `RunState` wholesale, and marks any referenced media that has gone missing as `"lost"`. The in-memory `review_clips` manifest is *not* persisted, so resume separately calls `_rebuild_review_clips(project)` (`cinema_pipeline.py:328`). On successful completion `_clear_checkpoint()` removes the file. The web surface exposes resumability read-only via `GET …/checkpoint` → `checkpoint_info()` (`cinema/services.py:115`), which reads the JSON without constructing a pipeline.

> **Re-assembly avoids a deadlock by design.** The SCREENING re-assemble endpoint calls `_assemble_approved_takes_core()` (`cinema_pipeline.py:1052`) directly rather than the public `assemble_approved_takes()`. The public method appends the SCREENING gate-wait, and a fresh per-request `CinemaPipeline` constructed in a Flask thread is *not* the instance that `signal_gate` will unblock — calling it there would hang the request (`cinema_pipeline.py:59-127`, orchestration gotcha #9).

### 2.6 One run, narrated end to end

Putting the pieces together, a single interactive run reads as: the operator creates and configures a project, adds characters (with reference images → multi-angle FLUX refs → GhostFaceNet embeddings) and locations, writes scenes, and posts `…/generate`. The orchestrator generates style rules, pre-generates BGM, then per scene decomposes → has the ChiefDirector validate → writes `director_review` → generates dialogue audio, and parks at **PLAN_REVIEW**. After plan approval it renders keyframes (FLUX+PuLID) and parks at **KEYFRAME_REVIEW**; then performance capture and (unless all-SKIP) **PERFORMANCE_REVIEW**; then the motion cascade — Veo-native-audio-first for dialogue, lip-sync for the rest — and **REVIEW**. On final approval it assembles (normalize → stitch → grade → 3-track mix → R128 loudnorm) into `exports/final_cinema.mp4`, parks at **SCREENING** for a watch-and-iterate loop, and on approval cleans up, logs cost, and reports **COMPLETE**. The identical sequence runs unattended when `headless=True` and auto-approve thresholds are tuned to clear all five gates without a human.

---

## 3. Component & Module Topology (the micro level)

This is the developer's "what is where / what does what" reference. It catalogs every subsystem of the pipeline, its canonical module paths (real, verified), and a compact table of its most important functions and classes with `file:line` citations. Use it to locate the code behind any behavior; use [§2](#) for how the pieces connect into a run.

All line numbers and LOC counts below were verified against the live source (`wc -l`, `grep -n`) at manual-authoring time; per the project's ADR-013 discipline, line anchors are point-in-time and can shift after edits — re-grep the symbol name if a number looks stale.

### 3.0 Reading this section: the dual-module shim convention

Six modules exist at **both** the repo root and inside `domain/`. In every case the top-level file is a **9-line re-export shim** (`from domain.<X> import *`) and the `domain/` file is canonical. This is the single most important fact for navigating the tree — `grep import scene_decomposer` finds two files; only one has logic.

| Top-level shim (9 LOC) | Canonical module | Canonical LOC |
|---|---|---|
| `scene_decomposer.py` | `domain/scene_decomposer.py` | 1286 |
| `dialogue_writer.py` | `domain/dialogue_writer.py` | 158 |
| `project_manager.py` | `domain/project_manager.py` | 1412 |
| `character_manager.py` | `domain/character_manager.py` | 719 |
| `location_manager.py` | `domain/location_manager.py` | 299 |
| `continuity_engine.py` | `domain/continuity_engine.py` | 661 |

Verified: `wc -l` on all twelve files shows 9 LOC each for the shims, the LOC above for the canonical files. New code should import from `domain.*` directly; the shims exist only to preserve legacy import surfaces from before the Phase-8 package move. Their docstrings mention `main.py` as a caller — that is stale (`main.py` was deleted).

A naming hazard that used to recur throughout is now gone: the second, unrelated `CinemaPipeline` at `cinema/pipeline.py` was deleted 2026-08-01 (ADR-081). `cinema_pipeline.CinemaPipeline` is the only class by that name. Note `pipeline_context.py` (a 15-line LLM-prompt-string loader) is still **not** `cinema/context.py` (the typed `PipelineContext` dataclass).

### 3.1 Orchestration (the macro-spine)

**Role:** `cinema_pipeline.CinemaPipeline` is the sole run driver. It owns the ordered gate sequence and `generate()` main loop, composes the three controllers (shot / review / checkpoint) over one shared `RunState`, and performs final assembly. Long-lived dependencies live on `PipelineCore`; per-run mutable state on `RunState`; pause/cancel/gate mechanics on `ThreadedLifecycle`.

**Canonical modules:** `cinema_pipeline.py` (1767 LOC, the orchestrator), `cinema/core.py`, `cinema/runstate.py`, `cinema/lifecycle.py`, `cinema/context.py`, `pipeline_context.py` (top-level LLM-prompt loader).

| Name | file:line | What it does |
|---|---|---|
| `CinemaPipeline.__init__` | `cinema_pipeline.py:55` | Builds `PipelineCore`, `ThreadedLifecycle(progress_callback)`, `RunState(headless=…)`; composes `ShotController`, `ReviewController`, `CheckpointStore` — all sharing ONE `RunState`. `headless=True` makes gates fail-fast. |
| `CinemaPipeline.generate` | `cinema_pipeline.py:942` | Main production loop. Ordered: refresh snapshot → style rules → BGM → per-scene decompose+director-review → PLAN_REVIEW gate → keyframe phase → KEYFRAME_REVIEW gate → performance phase → (conditional) PERFORMANCE_REVIEW gate → motion phase → REVIEW gate → assemble. Returns `final_cinema.mp4` path or `None`. |
| `CinemaPipeline.assemble_approved_takes` | `cinema_pipeline.py:853` | Full assembly: core assembly → SCREENING gate wait (if enabled) → cleanup → cost summary → COMPLETE at 100%. |
| `CinemaPipeline._assemble_approved_takes_core` | `cinema_pipeline.py:783` | Steps 1–5 only (refresh → REVIEW guard → scene packages → previews → `_assemble_final`). Called directly by the re-assemble endpoint to **avoid SCREENING-gate deadlock** on a Flask thread. |
| `CinemaPipeline._assemble_final` | `cinema_pipeline.py:1323` | ffmpeg: normalize 1920×1080@30 → stitch (hard-cut or xfade) → color grade → 3-track audio mix (voice/BGM/foley) → two-pass loudnorm → `exports/final_cinema.mp4`. |
| `CinemaPipeline._refresh_project_snapshot` | `cinema_pipeline.py:443` | `load_project` → `Project.model_validate` **before** swapping `self.project` (validate-before-swap keeps state coherent on failure) → rebuilds continuity trackers. Called 6+ times at gate boundaries. |
| `CinemaPipeline._build_scene_packages` | `cinema_pipeline.py:709` | Resolves approved take paths per scene; detects "all shots `audio_embedded`" to suppress double-voice TTS. |
| `build_pipeline_core` | `cinema/core.py:75` | Factory: loads project, mkdirs, constructs `PipelineCore(project, dirs, ContinuityEngine, ChiefDirector, CostTracker, LLMEnsemble)`. Raises `ValueError` if project absent. |
| `PipelineCore` | `cinema/core.py:62` | Dataclass of long-lived services (project dict, dirs, continuity, director, cost_tracker, ensemble). Process-cached in `web_server._running_cores`. |
| `RunState` | `cinema/runstate.py:60` | Dataclass: all per-run mutable state (`shot_results`, `scene_clips`, `scene_audio`, `shot_audio`, `scene_foley`, `foley_audio_paths`, `failed_shots`, `current_stage`, `headless`, `completed_scene_indices`). One instance, shared by all controllers. |
| `ThreadedLifecycle` | `cinema/lifecycle.py:110` | Event-backed pause/cancel/gate-wait. `wait_for_gate(name, predicate, poll=0.5)`, `signal_gate(name)` for early wake, `check_pause()`. |
| `NullLifecycle` | `cinema/lifecycle.py:70` | No-op lifecycle whose `wait_for_gate` returns `True` unconditionally. **NOT used by `CinemaPipeline`** — was the deleted CLI's lifecycle. See §3.13 gotcha. |
| `PipelineContext` | `cinema/context.py:51` | Typed shared state passed INTO phase `.run()` calls (`global_settings`, `lifecycle`, audio paths, legacy read-only `char_lora_*` snapshots, …). Dict-compat layer (`__getitem__`/`.get()`) keeps legacy dict-style phases working. |
| `get_project_setting(ctx, key, default)` | `cinema/context.py:157` | **Canonical** read path for per-project UI knobs (reads `ctx.global_settings`). Must be used instead of `config.settings.Settings` for any user-tunable setting. |

### 3.2 Web / API surface (the user entry point)

**Role:** `web_server.py` is the sole human-facing entry — a Flask server (port 8080) that serves the React SPA, exposes the full REST API for project/character/location/scene/shot CRUD and pipeline control, and streams progress via SSE. The project picker supports create, search, and confirmed per-project deletion; a successful delete also evicts the cached core/event bus so the same id cannot inherit stale runtime state. `web_services.py` holds the pure, unit-testable SSE-event shaper.

**Canonical modules:** `web_server.py`, `web_services.py`. Read endpoints
without constructing a pipeline come from `cinema/services.py` (§3.3); the
generated product-surface inventory, not a copied LOC/route count, is the
exhaustive HTTP surface authority.

| Name | file:line | What it does |
|---|---|---|
| `_running_pipelines` (module state) | `web_server.py:393` | pid → live `CinemaPipeline` (or `_PIPELINE_PENDING` sentinel). Single truth for "is generation active?". |
| `_running_cores` (module state) | `web_server.py:467` | pid → cached `PipelineCore`. Successful API settings writes and project deletion evict the idle entry; direct out-of-band `project.json` edits still require a restart. |
| `_progress_queues` | `web_server.py` | Per-pid `_ProjectEventBus`: bounded replay plus one bounded inbox per subscriber. It is transport, not durable job truth. |
| `_project_operation_locks` | `web_server.py` | Per-safe-project sibling `.<pid>.operation.lock` registry used by decorated mutation/direct-stage/generation-admission routes; extends the busy fence across server processes. |
| `_reassembly_in_flight` | `web_server.py:567` | Re-entrancy guard for the re-assemble endpoint (separate from `_running_pipelines` because re-assembly runs while SCREENING occupies it). |
| `_GATE_STAGES` | `web_server.py:452` | `frozenset` of stages where gate-acting endpoints bypass the busy fence. |
| `_get_or_build_core(pid)` | `web_server.py:571` | Thread-safe get-or-create of `PipelineCore`; raises `ValueError` on bad pid. |
| `_get_running_pipeline(pid)` | `web_server.py:682` | Safe reader (returns `None` for sentinel/absent). All callers MUST use this. |
| `_get_stage_pipeline(pid)` | `web_server.py:730` | Live pipeline if present, else a per-request `CinemaPipeline` sharing the cached core. Used by gate/take/shot endpoints. |
| `_reject_if_project_busy` / `…_outside_gate` | `web_server.py:796` / `:257` | 409 busy fence; the gate-bypass variant lets iterate/screening/re-assemble through while parked at a gate. |
| `_execute_pipeline_job_traced` | `web_server.py` | Fixed dispatcher worker: claims the durable row, installs the local sentinel/object, calls `pipeline.generate(resume=job.effective_resume)`, and settles the queue row. |
| `api_stream` (SSE) | `web_server.py` | Broadcast fan-out/replay with 30s HEARTBEAT and explicit END/GAP frames. If only SQLite knows an active job after restart, it hydrates a fresh bus and wakes the dispatcher; pre-restart buffered events are not durable. |
| `make_progress_callback(queue)` | `web_services.py:29` | Returns the `progress_cb(stage, detail, percent, …)` that `CinemaPipeline` receives; shapes the event dict and `queue.put`s it. Producer extras (`engine`, `spent`, `budget`, …) pass through with a JSON-serializability guard (NF-3 lift, P1-3). No-op if queue is `None`. |

**Key endpoint families** (all under `/api/projects/<pid>/…`): CRUD for
characters/objects/locations/scenes; scene prep; durable run control plus SSE;
gate and shot operations; assembly/screening; cost, artifact, delivery, trace,
project cleanup, and export. The generated product-surface inventory is the
exhaustive route authority. There is no global `POST /api/cleanup-all` route;
cleanup and deletion are project-scoped.

### 3.3 Phase system (the per-shot render loops)

**Role:** wraps the three per-shot loops (keyframe, performance, motion) in lightweight Protocol-conforming classes. Each takes a `PipelineContext`, iterates the project's shots, and returns a `PhaseResult` — leaving gates and retry policy to the orchestrator. `cinema/services.py` provides read-only disk-state helpers so web endpoints can read state without constructing the heavy pipeline.

**Canonical modules:** `cinema/phases/base.py`, `keyframe_render.py`, `performance.py`, `motion_render.py`, plus `cinema/services.py`.

| Name | file:line | What it does |
|---|---|---|
| `Phase` (Protocol) | `cinema/phases/base.py:61` | Requires `name: str` + `run(ctx) -> PhaseResult`. `@runtime_checkable`; no inheritance needed. Retry/fallback explicitly NOT part of the contract. |
| `PhaseResult` | `cinema/phases/base.py:39` | Dataclass `ok / message / elapsed_s`. Orchestrator reads only `ok`. |
| `KeyframeRenderPhase.run` | `cinema/phases/keyframe_render.py:68` | Iterates shots, skips those with `approved_keyframe_take_id`, calls `generate_keyframe_take`. Polls cancellation per scene+shot. **Partial failures do not fail the phase** (`ok=True` always except missing-config / cancel). |
| `PerformanceCapturePhase.run` | `cinema/phases/performance.py:35` | Three skip conditions: already-approved performance, `performance_engine=="SKIP"`, or no approved keyframe. Calls `generate_performance_take`. |
| `MotionRenderPhase.run` | `cinema/phases/motion_render.py` | Per scene: storyboard batch path only if `storyboard_mode`, the aspect is non-portrait, every candidate is non-dialogue, and 2–6 unapproved shots all have keyframes; otherwise per-shot `generate_motion_take`. The dialogue exclusion guarantees F1b evidence is written per shot. |
| `_get_storyboard_mode` | `cinema/phases/motion_render.py:102` | Reads the nested `global_settings.api_engines.KLING_NATIVE.storyboard_mode` (two levels deep) from `self._project`. |
| `MotionRenderPhase._run_storyboard_scene` | `cinema/phases/motion_render.py:100` | One `KlingNativeAPI.generate_storyboard` call → `split_video_into_segments` → per-segment `_finalize_motion_take(record_cost=False)`. Per-segment failure falls back to per-shot. Accesses private `_shot_ctrl` internals (see §3.13). |
| `state_snapshot(pid)` | `cinema/services.py:61` | `load_project` → gate-status counts; in-memory fields empty. Backs `GET …/pipeline-state` when idle (`web_server.py:3560`). |
| `checkpoint_info(pid)` | `cinema/services.py:115` | Reads `temp/pipeline_state.json` directly; resume-info dict. Backs `GET …/checkpoint` (`web_server.py:2859`). |

### 3.4 Review / Gates / Auto-approve / Screening / Checkpoints

**Role:** enforces the five operator review gates (PLAN_REVIEW, KEYFRAME_REVIEW, PERFORMANCE_REVIEW, REVIEW, SCREENING). A veto-rule auto-approve engine pre-clears shots meeting quality thresholds; in headless mode an unclearable gate raises a diagnosable error instead of polling forever. A JSON checkpoint persists `RunState` after every scene for crash-resume; the post-assembly SCREENING gate lets the operator preview, iterate, and re-assemble before sign-off.

**Canonical modules:** `cinema/review/controller.py` (762 LOC), `cinema/auto_approve.py` (803 LOC), `cinema/screening.py` (719 LOC), `cinema/checkpoint.py` (227 LOC), `cinema/runstate.py`.

| Name | file:line | What it does |
|---|---|---|
| `GateNotSatisfiedError` | `cinema/review/controller.py:93` | `RuntimeError` raised by `_wait_for_gate` in headless mode when auto-approve can't clear a gate; carries per-shot diagnostic reasons. |
| `ReviewController._gate_satisfied` | `cinema/review/controller.py:224` | Pure predicate: PLAN→all `plan_status=="approved"`; KEYFRAME→all `approved_keyframe_take_id`; PERFORMANCE→all SKIP or `approved_performance_take_id`; REVIEW→all `approved_final_take_id`. |
| `ReviewController._run_auto_approve_pass` | `cinema/review/controller.py:253` | Per shot calls `check_gate`, mutates approved shots, appends `auto_approve_audit`. Gate→key map; motion key only if `CINEMA_AUTO_APPROVE_MOTION=1`. Never raises. |
| `ReviewController._wait_for_gate` | `cinema/review/controller.py:519` | Runs auto-approve, then headless → check-once-and-raise, else `lifecycle.wait_for_gate` poll. |
| `ReviewController.approve_shot_plan` | `cinema/review/controller.py:645` | Human approval of a shot plan. |
| `ReviewController.approve_take` | `cinema/review/controller.py:659` | Validates collection membership (a keyframe can't be approved as final) and walks `source_take_id` for `approved_motion_take_id`. |
| `AutoApproveConfig` | `cinema/auto_approve.py` | All thresholds from `global_settings.auto_approve`. Production defaults: `image_min_composite=0.60`, explicit fallback bar `0.78`, `motion_min_identity=0.85`, `final_min_lipsync=0.8`, `final_require_human_if_upstream_auto=True`. |
| `record_director_review_on_shots` | `cinema/auto_approve.py:239` | **Writer** of `shot["director_review"]`; called unconditionally after `validate_shot_prompts` (`cinema_pipeline.py:1064`). Normalizes MODIFIED→APPROVED (cycle-17). Its absence was the headless-stall root cause. |
| `_rules_for_plan` | `cinema/auto_approve.py:214` | Two vetoes: decision≠APPROVED; non-empty violations. Reads `director_review`. |
| `check_gate` | `cinema/auto_approve.py:759` | Public entry; returns `AutoApproveDecision`. Catches all exceptions (`deferred=True` on eval error); returns not-approved if config disabled. |
| `_screening_stage_enabled` | `cinema/screening.py:104` | Flag: `global_settings.screening_stage_enabled` > `CINEMA_SCREENING_STAGE` env > default ON. |
| `_build_timeline_manifest` | `cinema/screening.py:205` | Per-shot `{start_s, end_s, take}` list; `verify_files=True` mirrors `_assemble_final`'s on-disk inclusion rule. |
| `mark_screening_approved` | `cinema/screening.py:342` | Persist `screening_approved`. |
| `mark_shot_needs_reassembly` | `cinema/screening.py:406` | Dirty-track a shot for re-assembly. |
| `clear_needs_reassembly` | `cinema/screening.py:456` | Race-safe clear (`only_shots=` preserves concurrently dirtied shots). |
| `CheckpointStore._save_checkpoint` | `cinema/checkpoint.py:87` | Atomic JSON write (mkstemp+`os.replace`) of RunState. |
| `_restore_from_checkpoint` | `cinema/checkpoint.py:186` | Rehydrate RunState on resume, marking missing files `"lost"`. |

### 3.5 Domain / State (the data model & persistence)

**Role:** the canonical in-memory schema and all on-disk persistence. Data flows as plain dicts through most of the pipeline; Pydantic v2 is a **warn-only** validation net at load/save boundaries. Persistence is `domain/projects/<pid>/project.json`, guarded by per-project `filelock`, written atomically.

**Canonical modules:** `domain/models.py` (209 LOC, schema), `domain/project_manager.py` (1412 LOC, the canonical home), `domain/shot_types.py`, `domain/performance.py` (engine routing — see §3.9).

| Name | file:line | What it does |
|---|---|---|
| `TakeRecord` / `Shot` / `Scene` / `Character` / `Location` / `Project` | `domain/models.py:62 / 82 / 156 / 172 / 193 / 204` | Pydantic models with `extra="allow"`. Several live fields (e.g. `objects`, `performance_engine`, `director_review`, `screening_approved`) are NOT in the models — they exist on the raw dict. See §3.13. |
| `DirectorialIntent` | `domain/models.py:38` | Iteration-provenance substrate (`prose`/`verb`/`params`/`target_stage`) embedded in `TakeRecord`. |
| `CascadeMetadata` | `domain/models.py:26` | Cascade-selection bookkeeping embedded in `TakeRecord`. |
| `mutate_project(pid, mutator, …)` | `domain/project_manager.py:854` | **The canonical RMW primitive.** Lock → load → normalize → `mutator(latest)` → save-if-changed. `snapshot=` syncs the caller's dict in place. |
| `load_project` | `domain/project_manager.py:816` | Locked read (auto-saves on migration). |
| `save_project` | `domain/project_manager.py:804` | Atomic validated write. |
| `make_take / make_shot / make_character / make_object / make_location / make_scene / make_project` | `domain/project_manager.py:263 / 382 / 282 / 302 / 335 / 356 / 433` | Factories. `new_id()` (`:128`) = `uuid4().hex[:12]` with type prefixes (`char_`/`loc_`/`scene_`/`take_`/`obj_`). |
| `normalize_shot_schema` | `domain/project_manager.py:521` | In-place shot migration: unique shot IDs (collision → `shot_{scene_id}_{idx}`), legacy-field migration. |
| `normalize_project_schema` | `domain/project_manager.py:668` | In-place project migration: scene re-ordering, VBench-key stripping. |
| `_validate_project` | `domain/project_manager.py:760` | `Project.model_validate`; warn-only unless `CINEMA_STRICT_SCHEMA=1`. |
| Entity mutation helpers | `domain/project_manager.py:962–1258` | Locked `add/remove/get/update/reorder` operations for characters, objects, locations, and scenes. Generated shot media is owned by `cinema/shots/controller.py` and indexed by the artifact-version store. |
| `normalize_shot_type` | `domain/shot_types.py:34` | Alias normalizer (`closeup`→`close_up`). |
| `FACE_READABLE_SHOTS` | `domain/shot_types.py:47` | `frozenset({"close_up","portrait","medium"})` used by performance routing. |

### 3.6 LLM brains (the creative-direction layer)

**Role:** the AI intelligence stack that turns intent + script into machine-executable shot specs, enforces hard constraints pre-generation, translates iteration instructions post-generation, and runs multi-provider competition with judge selection. Stateless — reads project dicts, writes back to shots.

**Canonical modules:** `llm/chief_director.py`, `llm/director.py`, `llm/ensemble.py`, `llm/prompt_optimizer.py`, `llm/style_director.py`, `llm/negative_prompts.py`.

| Name | file:line | What it does |
|---|---|---|
| `ChiefDirector.validate_shot_prompts` | `llm/chief_director.py:296` | Pre-gen gate against HC1–HC8. Returns `{decision, violations, shots}`; applies valid MODIFIED edits in place; ≤1 JSON retry. No client, API failure, malformed/non-object JSON, or missing/unsupported decisions return REVIEW_REQUIRED, never approval. |
| `ChiefDirector._call_llm` | `llm/chief_director.py:85` | Anthropic (`claude-sonnet-4-6`) primary, OpenAI (`gpt-4o`) fallback; honors `creative_llm` only if model-family matches active provider. |
| `ChiefDirector.evaluate_generation_quality` | `llm/chief_director.py:426` | 2×2 (identity × coherence) mutation matrix with negative-prompt enrichment. Missing identity evidence, no client, or unavailable/unparsable output returns REVIEW_REQUIRED. **Wired by T6** — invoked by `cinema/shots/controller.py::diagnose_clip` on the opt-in deep path (`deep=True`); see the remediation-advisory design spec. **Vision-grounded** (`d974c15`+`a4cb076`) — attaches take + canonical reference images (PIL re-encode → JPEG q90, 1568px long-edge cap) and returns an extra `visual_findings` key surfaced in `advisory_deep`. |
| `CinemaDirector.translate_intent` | `llm/director.py:275` | Permissive iteration translator (operator intent overrides HC). |
| `intent_translator` | `llm/director.py:593` | Verb DSL (`tighten_framing`/`match_shot`/`shift_emotion`) → `{revised_prompt, params_delta, anchor_refs}`. Called at `cinema/shots/controller.py:2160`. |
| `LLMEnsemble.competitive_generate` | `llm/ensemble.py:196` | Parallel multi-model gen + judge-pick → `EnsembleResult`. Default rosters per task (`script`/`decompose`/`default`); default judge `claude-sonnet-4-6`. |
| `build_anthropic_system_blocks` | `llm/ensemble.py:53` | Wraps system text with `cache_control: ephemeral` for Anthropic prompt caching; callers must pass stable strings. |
| `optimize_shot_prompt` | `llm/prompt_optimizer.py:702` | UI text → 13-field structured shot spec via ensemble (`task_type="decompose"`); `_coerce_to_valid_keys` sanitizes enums; `_fallback_optimize` is the LLM-free path. |
| `generate_style_rules` | `llm/style_director.py:19` | **OpenAI-only** 7-key style dict (Tavily-grounded); falls back to `_default_style_rules` if no OpenAI key. Asymmetric with the Anthropic-first directors (see §3.13). |
| `style_rules_to_prompt_suffix` | `llm/style_director.py:233` | Concatenates color/lighting/photorealism/composition rules into the suffix prepended to every image prompt (`cinema/shots/controller.py:497`). |
| `get_negative_prompt_for_failure` | `llm/negative_prompts.py:44` | Maps `FailureReason.value` → negative-prompt phrase; used by `evaluate_generation_quality` and `build_remediation_advisory`. |
| `build_remediation_advisory` | `llm/negative_prompts.py:55` | **Wired by T6** — builds `{failure_label, suggested_negative_prompt, remediation_steps}` advisory dict; called from `generate_keyframe_take` and `diagnose_clip`. |

### 3.7 Script → Scenes → Dialogue → Research

**Role:** converts user scenes into concrete, API-routed shot records (GPT-4o or a GPT-4o-vs-Claude ensemble enforcing five hard constraints), generates per-character dialogue, and injects live web research to ground both.

**Canonical modules:** `domain/scene_decomposer.py` (1286 LOC), `domain/dialogue_writer.py` (158 LOC), `domain/language_defaults.py` (212 LOC), `research_engine.py` (146 LOC), `web_research.py` (240 LOC).

| Name | file:line | What it does |
|---|---|---|
| `decompose_scene` | `domain/scene_decomposer.py:838` | Single-model GPT-4o decompose via `run_with_tools` (≤2 tool rounds). `target_shots = max(2, min(5, duration/2.5))`. Validates each shot through `make_shot`. Falls back to `_fallback_decompose`. |
| `competitive_decompose_scene` | `domain/scene_decomposer.py:998` | Ensemble (GPT-4o vs Claude, judged) decompose; adds `ensemble_winner`/`ensemble_scores`. Falls back to `decompose_scene`. |
| `_build_cinedecompose_system_prompt` | `domain/scene_decomposer.py:726` | Single-source CineDecompose prompt: HC1–HC5 (identity firewall, schema/location/lighting lock, face-toward-camera), `[SHOT][SCENE][ACTION][OUTFIT][QUALITY]` schema, `PIPELINE_CONTEXT`. |
| `update_scene_shots` | `domain/scene_decomposer.py:1242` | Persists shots via `mutate_project`. Called by `cinema_pipeline.py:1055` and `web_server.py:2699`. |
| `_fallback_decompose` | `domain/scene_decomposer.py:1199` | No-key path; always 2 hardcoded shots (establishing wide + medium CU). |
| `API_REGISTRY` | `domain/scene_decomposer.py:139` | 40+ engine capability table. (Also the source of `native_audio` for video routing — §3.8.) |
| `PURPOSE_API_RANKING` | `domain/scene_decomposer.py:183` | Per-purpose ordered API lists. |
| `rank_apis_for_purpose` | `domain/scene_decomposer.py:359` | Best-first ranking filter. |
| `estimate_short_cost` | `domain/scene_decomposer.py:253` | 60-shot project cost breakdown. |
| `generate_dialogue` | `domain/dialogue_writer.py:12` | Per-character lines `{character_id, character_name, text, delivery}`; non-English directive keeps `text` native, `delivery` English. |
| `merge_language_defaults_into_settings` | `domain/language_defaults.py:137` | Merges per-language defaults into project settings. |
| `get_language_defaults` | `domain/language_defaults.py:117` | Per-language pipeline defaults (TTS provider, lipsync priority, validation threshold). English/Korean/Japanese/Mandarin/`_default`. |
| `run_with_tools` | `web_research.py` | Two-phase GPT-4o tool loop (Tavily/Firecrawl) + final JSON call; threads the shared tracker through both LLM and tool requests. |
| `research_cinematography` | `research_engine.py` | Tavily/Firecrawl wrapper; records provider outcome/latency and returns `""` if unconfigured. |
| `research_location_visual` | `research_engine.py` | Tavily image-search wrapper; records provider outcome/latency and returns `[]` if unconfigured. Downloaded web references remain acquired project inputs. |
| `research_music_reference` | `research_engine.py` | Tavily/Firecrawl wrapper; records provider outcome/latency and returns `""` if unconfigured. |

### 3.8 Video generation + routing (the API cascade)

**Role:** turns a keyframe still into a video clip — classify the shot, select an automatically admissible API (`GEMINI_OMNI` primary, `VEO_NATIVE` first fallback), run a fault-tolerant ordered fallback cascade, route dialogue through backend-supported native audio or mandatory F1b, and write cascade provenance plus backend capability evidence to the take.

**Canonical modules:** `phase_c_ffmpeg.py` (2540 LOC — central routing + all per-API handlers + ffmpeg utilities), `workflow_selector.py` (436 LOC), and the native clients `kling_native.py`, `veo_native.py`, `ltx_native.py`, `sora_native.py`. (`RUNWAY*` and `SEEDANCE` are inline in `phase_c_ffmpeg.py` — no wrapper class.)

| Name | file:line | What it does |
|---|---|---|
| `generate_ai_video` | `phase_c_ffmpeg.py:208` | Central dispatch + cascade. Executable branches: KLING_NATIVE, SORA_NATIVE, VEO_NATIVE, LTX, RUNWAY_GEN4, VEO/FAL, KLING_3_0, FAL_SVD, SEEDANCE, and GEMINI_OMNI (WS2 Google-first primary, §9.4). Retired `SORA_2` and legacy `RUNWAY` retain catalog tombstones only. Returns a validated path or `None`; acknowledged deferred work is reported through `_cascade_out`. |
| `try_next_api` (inner) | `phase_c_ffmpeg.py:1089` | Iterates fallbacks, filters attempted + `api_engines`-disabled; on exhaustion sleeps 30s and retries up to `MAX_CASCADE_RETRIES` (default 1, `cascade_retry_limit` override). |
| `_record_video_cascade` (inner) | `phase_c_ffmpeg.py:861` | Writes `{engine, attempts}` into `_cascade_out` before each successful return (provenance for the take record). |
| `_veo_quota_blocked` | `phase_c_ffmpeg.py:101` | Checks the 1800s TTL cooldown flag. |
| `_VEO_QUOTA_EXHAUSTED_UNTIL` | `phase_c_ffmpeg.py:36` | Cooldown timestamp — only the **FAL-proxy VEO** branch sets/checks it; VEO_NATIVE has no quota guard (§3.13). |
| `stitch_modules` | `phase_c_ffmpeg.py:2644` | Concat demuxer (`-c copy`). |
| `split_video_into_segments` | `phase_c_ffmpeg.py:2826` | Storyboard splitter (last segment to EOF). |
| `classify_shot_type` | `workflow_selector.py:188` | → `portrait/medium/wide/action/landscape`. Note: never returns `close_up` despite a `MOTION_FIDELITY_FLOORS` key for it (§3.13). |
| `WORKFLOW_TEMPLATES` | `workflow_selector.py:29` | Per-shot-type primary API + fallback list + render params. All 5 shot types now primary `GEMINI_OMNI` (WS2), `VEO_NATIVE` first fallback; portrait/medium second-fallback to fal Kling v3 Pro (`KLING_3_0`), wide/landscape to `LTX`, action to `SEEDANCE` — full table `ARCHITECTURE.md` §9.1. |
| `VeoNativeAPI.generate_video` | `veo_native.py` | Uses Vertex only when `GOOGLE_CLOUD_PROJECT` is explicit and ADC resolves at provider construction; otherwise uses the Developer API with `GOOGLE_API_KEY`, and fails deterministically with neither. Only Vertex advertises native audio. Policy/catalog reads never probe ADC. `reference_images` and `driving_video_path` remain accepted but unwired. Duration clamps to (4,6,8). |
| `_extract_video_bytes` | `veo_native.py:229` | Inline `video_bytes` (Vertex) vs `files.download` (Gemini). Cycle-17 native-audio fix path. |
| `_clamp_image_to_video_duration` | `veo_native.py:128` | Duration clamp (5s→6). |
| `KlingNativeAPI` | `kling_native.py:39` | JWT HS256 auth; `create_image_to_video` (`:106`), `poll_task` (`:201`), `generate_storyboard` (`:394`, ≤6 shots, `face_consistency`). |
| `SoraNativeAPI.generate_video` / `LTXVideoAPI.generate_video` | `sora_native.py:50` / `ltx_native.py:197` | Sora explicit compatibility: durations [4,8,12], still-image `input_reference` only; any driving-video value is rejected before preprocessing/network. LTX: native `api.ltx.io` signed upload + asynchronous-v2 job flow preferred, with a private request-fingerprint sidecar, bounded polling, exact-job resume, and validated atomic MP4 publication; FAL is only a pre-submission proxy fallback. Pending, submission-ambiguous, or post-ack recovery cases surface as `deferred_job` and stop the provider cascade; only explicit terminal failure may advance. Scene transitions use ffmpeg xfade assembly; the old LTX transition helpers were deleted. |

### 3.9 Image / keyframe generation (single production tier)

**Role:** converts a per-shot prompt into a 1344×768 keyframe (the anchor for all downstream video). Post-WS3 the image **primary** is Gemini 3.1 Flash Image (Nano Banana 2) via `gemini_image_native.GeminiImageAPI` (PRIORITY-0 in `generate_ai_broll`; migrated off the sunset `gemini-2.5-flash-image` in Slice 6b); the FLUX-Dev-on-RunPod-ComfyUI tier with PuLID face-lock (`pulid.json`) + FAL fallback cascade is the demoted first fallback — reached when Nano Banana is keyless, errors, or fails the identity gate, or when `identity_backend='pod'`. (A heavier **max** tier — N=8 adaptive best-of with GhostFaceNet/Aesthetic scoring, Union ControlNet, Redux, FaceDetailer, SUPIR 4K — was retired in WS1 Task 4; see the retirement note below.) Performance capture (Act-Two/LivePortrait/Viggle) lives alongside.

**Canonical modules:** `phase_c_assembly.py` (image routing/workflow injection), `comfyui_client.py` (bounded pod transport/job control/output publication), the WS3 image primary `gemini_image_native.py`, `workflow_selector.py`, `face_validator_gate.py`, `cinema/shots/controller.py`, plus the `performance/` package and the production ComfyUI graph `pulid.json`. (The max-tier driver `quality_max.py` and its `pulid_max.json` graph were deleted in WS1 Task 4.)

| Name | file:line | What it does |
|---|---|---|
| `generate_ai_broll` | `phase_c_assembly.py:98` | Priority chain: **PRIORITY-0 Gemini 3.1 Flash Image (Nano Banana 2, WS3 — `:224`)** → ComfyUI PuLID (`pulid.json`) → `_fal_flux_fallback`. Runtime values set prompt/latent/seed/PuLID; init-image continuity uses only FLUX-compatible `LoadImage → VAEEncode` nodes 200–201. The former SD1.5 ControlNet and incompatible IP-Adapter injections are removed. `quality_tier` is still accepted but informational — the `=="max"` fork was retired in WS1 Task 4. |
| `GeminiImageAPI.generate_image` | `gemini_image_native.py:146` | The PRIORITY-0 Nano Banana path (`generate_ai_broll:206`). Multi-ref identity (frontal `character_image` + `multi_angle_refs` + secondary-char refs). Identity pass → `ImageGenResult(_, "GEMINI_IMAGE")`; on fail/keyless/error it records a billed-reject and **falls through** to the pod/FAL cascade (never raises, never returns `None` — silent-gate-degradation discipline). Opt out via `identity_backend='pod'`. |
| `RunPodComfyUI` | `comfyui_client.py` | Bounded ComfyUI client: live graph/model/queue preflight, pooled REST transport, optional bearer auth, one-shot `/prompt`, WebSocket terminal/progress events with history fallback, atomic ID-scoped cancellation (legacy queue requests remain `UNKNOWN`; global interrupt is explicit-only), and validated atomic image publication. |
| `_fal_flux_fallback` | `phase_c_assembly.py:1040` | FLUX Kontext Max Multi → FLUX-Pro → Schnell → Pollinations. |
| `ImageGenResult` | `phase_c_assembly.py:33` | `NamedTuple(path, api_name)`; `api_name` is the authoritative backend token. |
| `score_candidate` | `face_validator_gate.py:174` | Composite = `0.6·arc + 0.4·aesthetic`. |
| `should_halt` | `face_validator_gate.py:231` | Halt on budget or composite ≥ threshold. |
| `needs_regenerate` | `face_validator_gate.py:330` | Regenerate (one PuLID-boost retry) if `arc < floor`. |
| `get_workflow_params` | `workflow_selector.py:260` | Per-type params + UI overlays. |
| `apply_workflow_params` | `workflow_selector.py:357` | Write params into the `pulid.json` node map. |
| `get_adaptive_pulid_weight` | `workflow_selector.py:382` | Rolling-stats adaptive PuLID weight. |

> **Max tier retired (WS1 Task 4, `267af0cd`).** The `generate_ai_broll_max` driver (`quality_max.py`) and its `pulid_max.json` graph — N=8 adaptive best-of, node probe/prune, the five `_inject_*` axes, and the ControlNet / Redux / FaceDetailer / SUPIR post-passes — were deleted; production (`pulid.json` + FAL) is the sole ComfyUI/pod image tier (WS3 later layered Nano Banana in front as the image **primary** — see the §3.9 role). `ARCHITECTURE.md` §8.3 keeps the mechanism archaeology; ADR-024 records why (the max graph over-cooks structurally, so `production`/`pulid.json` is the validated survivor). Of the scoring primitives above, `score_candidate` remains in the retained, policy-inactive LoRA validator code; it has no live product caller. `should_halt` / `needs_regenerate` are likewise dormant.
| `generate_keyframe_take` | `cinema/shots/controller.py:1308` | Requires `plan_status=="approved"`; `enhance_shot_prompt` → optional optimizer → `generate_ai_broll` → identity validate → append take → record cost. |

### 3.10 Identity / Continuity / Coherence

**Role:** keeps characters, locations, and visual properties coherent across shots. Four continuity sub-engines + a unified identity validation stack (GhostFaceNet, adaptive frame sampling, rolling stats feeding PuLID adaptation) + a pixel-level coherence analyzer.

**Canonical modules:** `domain/continuity_engine.py` (661 LOC, 4 sub-engines + orchestrator), `coherence_analyzer.py` (281 LOC), `face_validator_gate.py` (§3.9), `domain/character_manager.py` (719 LOC), `domain/location_manager.py` (299 LOC), and the `identity/` package (`__init__.py`, `types.py`, `validator.py`). Note: the skill source-map's flat `identity_validator.py`/`identity_types.py` are **wrong** — the real package is `identity/`.

| Name | file:line | What it does |
|---|---|---|
| `ContinuityEngine.enhance_shot_prompt` | `domain/continuity_engine.py:446` | Central shot augmentation: builds enhanced prompt + the `continuity_config` dict (`use_img2img`, `init_image`, `denoise_strength`, seeds, `primary_reference`, `multi_angle_refs`, `identity_anchor`, `pulid_weight_override`). |
| `ContinuityEngine.validate_shot` | `domain/continuity_engine.py:583` | Delegates to `IdentityValidator.validate_video` for post-gen video identity. |
| `TemporalConsistencyManager.get_denoise_strength` | `domain/continuity_engine.py:368` | Context-aware denoise (0.30–0.55). |
| `should_use_img2img` | `domain/continuity_engine.py:352` | img2img only same-scene, `shot_index>0`. |
| `IdentityValidator.validate_video` | `identity/validator.py:768` | Adaptive sampling (`_compute_sample_positions` `:1083`, 3–10 frames by shot type) → `_analyze_frame` (`:1126`, GhostFaceNet cosine) → aggregate → `IdentityValidationResult`. |
| `IdentityValidator.get_rolling_stats` | `identity/validator.py:902` | Window over history → `suggested_pulid_delta` (success<0.5→+0.10, etc.). Drives adaptive PuLID weight. |
| `SHOT_TYPE_THRESHOLDS` | `identity/types.py:96` | Per-type strict/standard/lenient thresholds. |
| `get_threshold_for_shot` | `identity/types.py:105` | Attempt-based interpolation toward lenient. |
| `make_validator` | `identity/__init__.py:40` | Factory (wires `vision_fallback`). Always use this — bare `IdentityValidator` lacks the fallback. |
| `get_shared_validator` | `identity/__init__.py:62` | Process-wide singleton wrapper over `make_validator`. |
| `assess_coherence` | `coherence_analyzer.py:219` | `overall = (1-color_drift)·0.4 + lighting·0.3 + composition·0.3`; returns `valid=False` if either image fails to load — callers MUST check `valid`. |
| `create_character_with_images` | `domain/character_manager.py:498` | Canonical-face pick; orchestrates the full character build. |
| `_generate_multi_angle_refs` | `domain/character_manager.py:766` | FLUX Kontext Max Multi 5-angle reference generation. |
| `assign_voice` | `domain/character_manager.py:1012` | Language + gender voice assignment. |
| `build_identity_anchor` | `domain/character_manager.py:1105` | `"{name}: {traits}"` anchor (injected verbatim, never rephrased). |
| `create_location_with_images` | `domain/location_manager.py:114` | Location refs (+ optional Tavily research). |
| `build_location_prompt_fragment` | `domain/location_manager.py:205` | Verbatim prompt fragment for the location. |
| `get_location_seed` | `domain/location_manager.py:286` | Persistent seed for architectural consistency. |

### 3.11 Performance capture (engine routing + execution)

**Role:** retargets a still keyframe into a performance clip (lip-readable acting) for dialogue/face-readable shots, routing per shot to Act-Two (engine key still `ACT_ONE`), LivePortrait, Viggle, or SKIP, with a post-gen identity/motion gate.

**Canonical modules:** `domain/performance.py` (222 LOC, pure routing), `performance/_router.py` (dispatch), and per-engine modules `act_two.py`, `live_portrait.py`, `viggle.py`, `driving_video.py`, plus the gates `motion_gate.py`, `identity_gate.py`.

| Name | file:line | What it does |
|---|---|---|
| `route_performance_engine` | `domain/performance.py:110` | Decision matrix → `ACT_ONE / LIVE_PORTRAIT / VIGGLE / SKIP`: SKIP (no chars/wide) → ACT_ONE (dialogue + face-readable; budget mode → LIVE_PORTRAIT) → VIGGLE (action no-dialogue; uncontained ADR-082, catalog LIMITED) → ACT_ONE (remaining dialogue) → SKIP. |
| `should_capture` | `domain/performance.py:72` | Pure gate (skip no-chars/landscape/wide-no-dialogue). |
| `shot_needs_driving_video` | `domain/performance.py:94` | Whether the shot needs a driving video (all real engines do; only SKIP doesn't). |
| `driving_video_source` | `domain/performance.py:168` | Driving-video source (`upload`/`tts_auto`/`none`). |
| `precondition_error` | `domain/performance.py:186` | Pre-allocation guard, runs BEFORE Mode-B synth (ACT_ONE needs driving_video_path OR audio_path — audio alone still satisfies this pre-check since Mode-B can synth from it; LP/VIGGLE need an explicit driving video). |
| `dispatch` | `performance/_router.py:93` | The single engine entry called by `cinema/shots/controller.py:921`; routes to the per-engine `generate_*` based on the resolved engine. |
| `generate_act_two_performance` | `performance/act_two.py:114` | Runway Act-Two via SDK (REST fallback if the `runwayml` package is missing); identity comes from the keyframe + a required driving/reference video (no audio-only mode). |
| `generate_live_portrait_performance` / `generate_viggle_performance` | `performance/live_portrait.py:58` / `viggle.py:80` | LivePortrait (driving video) and Viggle Mode-A motion retargeting. |
| `score_motion_fidelity` | `performance/motion_gate.py:141` | Optical-flow motion-fidelity score (sample count from `MOTION_GATE_SAMPLES`, read once at module load). |
| `needs_remotion` | `performance/motion_gate.py:184` | Remotion advisory. |
| `validate_performance_take` | `performance/identity_gate.py:106` | 1s-frame GhostFaceNet check via the shared validator; floor `DEFAULT_PERFORMANCE_FLOOR=0.70`. Returns similarity or `None` (inconclusive). |

### 3.12 Post-processing / Assembly / Audio

**Role:** everything after video generation — face-swap, lip-sync (overlay or full talking-head), RIFE interpolation, SeedVR2/Topaz upscale, and the ffmpeg assembly that grades, stitches, mixes 3-track audio, and normalizes to EBU R128. Historical LoRA status/trainer modules remain in this area, but the product policy makes training, registration, and production use inactive and read-only. The audio side generates dialogue TTS, BGM, foley, forced alignment, and voice DSP.

**Canonical modules:** `phase_c_ffmpeg.py` (assembly utilities — §3.8), `phase_c_vision.py` (488 LOC, face-swap + vision QC), `lip_sync.py` (1258 LOC), `prep/lora_policy.py` (the dormant boundary), retained `prep/lora_training.py` history/status code, `prep/topaz_upscale.py` (151 LOC), and the `audio/` package (`dialogue.py`, `music.py`, `foley.py`, `effects.py`, `alignment.py`, `voiceover.py`, `_client.py`).

| Name | file:line | What it does |
|---|---|---|
| `apply_color_grade` | `phase_c_ffmpeg.py:3197` | 8 grade presets (`COLOR_GRADE_PRESETS` at `:3185`) or LUT. |
| `two_pass_loudnorm` | `phase_c_ffmpeg.py:3335` | EBU R128 two-pass (-14 LUFS). |
| `xfade_concat` | `phase_c_ffmpeg.py:3612` | Cross-dissolve (mixed-audio-presence fix in `_build_xfade_filtergraph` at `:3543`). |
| `assess_motion_quality` | `phase_c_ffmpeg.py:3073` | Optical-flow → `accept/interpolate/regenerate`. Requires OpenCV. |
| `face_swap_video_frames` | `phase_c_vision.py` | Durable fal PixVerse request-ID recovery; FaceFusion CLI only when cloud work was not submitted or explicitly failed unbilled. The fixed 5s/720p PixVerse tier is tracked as a $0.20 reconciled estimate. |
| `validate_shot_quality_vision` | `phase_c_vision.py:433` | GPT-4o QC (0–10); default-pass on missing key/image. |
| `validate_identity_vision` | `phase_c_vision.py` | Claude identity match through the nonresumable paid fence. Missing key/output and ambiguous provider outcomes fail closed; an absent reference is an explicit skip. |
| `validate_scene_coherence_vision` | `phase_c_vision.py:731` | Gemini coherence; default-pass on missing key/image. |
| `lipsync_overlay` | `lip_sync.py:585` | Overlay cascade (SyncV3→MuseTalk→LatentSync→SyncV2). |
| `lipsync_generation` | `lip_sync.py:1213` | Generation cascade (Omnihuman v1.5→Creatify Aurora; Hedra and Kling were dropped from this cascade in `40bc8c60` and WS4). |
| `generate_lip_sync_video` | `lip_sync.py:1467` | Smart router (`mode="auto"`); SyncNet quality gate via `_sync_gate_settings` at `:1192`. |
| `generate_rife_interpolation` | `lip_sync.py:1644` | Cloud RIFE (FPS multiplier). |
| `upscale_video_seedvr2` | `lip_sync.py:1862` | Cloud SeedVR2 upscale (1080p/2160p). |
| `train_character_lora` | `prep/lora_training.py:439` | Retained ai-toolkit FLUX LoRA producer implementation; its entry path is unconditionally denied by `prep.lora_policy` and is not operational product capability. |
| `prepare_character_lora_dataset` | `prep/lora_training.py:166` | Retained dataset-preparation implementation behind the same inactive policy; historical/status compatibility only. |
| `upscale_with_topaz` | `prep/topaz_upscale.py:75` | Local Topaz CLI wrapper (no-op if CLI absent → caller falls back to SeedVR2). |
| `generate_dialogue_voiceover` | `audio/dialogue.py:730` | ElevenLabs v3 Dialogue Mode (2+ speakers) or per-line loop; Cartesia Sonic 3.5 for Korean; optional `.alignment.json` sidecar. |
| `generate_fal_bgm` | `audio/music.py:536` | FAL Stable Audio BGM (25+ vibes). |
| `master_music` | `audio/music.py:713` | Mastering via AU/Pedalboard/ffmpeg presets (`MUSIC_MASTERING_PRESETS` at `:37`). |
| `generate_stability_foley` | `audio/foley.py:113` | Stability AI Stable Audio 2.0 foley (15+ environment prompts). |
| `_build_foley_prompt` | `audio/foley.py:33` | Builds the foley prompt from the scene descriptor. |
| `align_audio_to_text` | `audio/alignment.py:222` | WhisperX → vanilla Whisper word timestamps; thread-safe model cache. |
| `apply_voice_effect` | `audio/effects.py:230` | AU plugin → Pedalboard chain → ffmpeg (13 voice-FX presets). |

### 3.13 Cross-cutting services

**Role:** pipeline-wide infrastructure — durable full-run queue, paid-media
attempt/budget ledger, provider analytics/health, immutable artifact history,
client packaging, searchable structured traces, file-lifecycle cleanup, and the
single env-var settings singleton.

**Canonical modules:** `pipeline_jobs.py`, `paid_provider.py`,
`cost_tracker.py`, `domain/provider_health.py`, `cinema/artifact_versions.py`,
`cinema/artifact_indexing.py`, `cinema/trace_store.py`,
`cinema/logging_config.py`, `web_observability.py`, `web_artifacts.py`,
`cleanup.py`, and `config/settings.py`.

| Name | file:line | What it does |
|---|---|---|
| `PipelineJobStore` / `PipelineJobDispatcher` | `pipeline_jobs.py:123`, `:769` | SQLite/WAL queue, one active job per project, FIFO claims, leases/heartbeats/process fences, fixed global worker pool, checkpoint-resume recovery. |
| `CostTracker` | `cost_tracker.py:392` | SQLite cost + paid-attempt ledger (`data/experiments.db`) and atomic budget gate. Project spend is rehydrated before new work is admitted. |
| `reserve_paid_attempt` / `reconcile_paid_attempt` | `cost_tracker.py` | Legal-transition ledger for reserved/submitting/running/ambiguous/terminal paid media and planning calls; a provider job ID, when the provider supplies one, is immutable once acknowledged. |
| `run_durable_fal_job` / `run_durable_comfy_job` | `paid_provider.py:692`, `:1038` | Resume exact provider IDs and block blind submit replay. `run_nonresumable_paid_call` (`:500`) fail-closes ambiguous no-ID providers. |
| `get_provider_usage_analytics` | `cost_tracker.py` | Paid-media plus planning/research observation success, latency, failure, reservation and reconciled-estimate aggregation by engine/provider. |
| `assess_provider_health` | `domain/provider_health.py:36` | Conservative deterministic health from durable paid-attempt evidence; the base-video `AUTO` path removes only `unhealthy`. |
| `record_api_call` | `cost_tracker.py:1735` | Ordinary API cost logging path. |
| `run_fenced_llm_call` | `paid_provider.py` | Real project trackers reserve a deterministic planning-LLM attempt and conservative token upper bound before the SDK call; success settles once from returned usage, ambiguity becomes `accepted_unknown`, and the same logical retry is blocked. No provider-job-ID resume exists. |
| `log_llm` | `cost_tracker.py` | Legacy/standalone token-cost logging path. Paid-authority planning calls suppress this duplicate write because their attempt settlement already records the exact token-derived list-price cost. |
| `would_exceed` / `is_over_budget` | `cost_tracker.py:1847`, `:1913` | Pre-call reservation predicate and post-call project budget state. |
| `API_COST_USD` | `cost_tracker.py:55` | Repository estimates — operators must calibrate against invoices. |
| `ArtifactVersionStore` / `ClientPackageBuilder` | `cinema/artifact_versions.py:350`, `:850` | Content-addressed immutable bytes, append-only hash-chained provenance, deterministic allowlisted historical/current deliverable packages. |
| `record_take_version` / `record_auxiliary_version` / `record_final_version` | `cinema/artifact_indexing.py` | Index accepted takes, rejected paid Gemini/motion/lip-sync candidates, generated character assets, non-take outputs, and final master with available source/dependency/recipe evidence. |
| `cleanup_project` | `cleanup.py:56` | Deletes intermediate `temp/` artifacts post-assembly (called at `cinema_pipeline.py:1209`, non-fatal); `aggressive=True` also removes generated media. |
| `CLEANUP_RULES` | `cleanup.py:34` | The delete-pattern ruleset `cleanup_project` applies. |
| `setup_logging` / `SQLiteTraceHandler` | `cinema/logging_config.py:97`, `cinema/trace_store.py:200` | JSON stdout plus bounded/redacted/project-scoped local trace index. Trace indexing failure never changes pipeline control flow. |
| `search_traces` | `cinema/trace_store.py:312` | Bounded project/level/query/trace-ID search used by `GET .../traces`. |
| `_JsonFormatter` | `cinema/logging_config.py:68` | The JSON-line log-record formatter. |
| `Settings` | `config/settings.py:102` | Frozen dataclass of all env vars. **Only API keys + infra paths belong here**; project UI knobs flow through `get_project_setting`. |
| `get_settings` | `config/settings.py:225` | `@lru_cache` singleton accessor. |
| `_parse_cors_origins` | `config/settings.py:84` | Parses `WEB_CORS_ORIGINS`. (`CINEMA_*` behavioral flags are read live via `os.environ`, not cached in `Settings`.) |

### Known divergences, dead code, and footguns

These are the load-bearing gotchas a developer will hit; each is verified against source.

| Item | Where | Note |
|---|---|---|
| `pipeline_context.py` vs `cinema/context.py` | top-level vs `cinema/` | 15-line prompt-string loader vs typed `PipelineContext` dataclass. |
| `headless=True` does NOT use `NullLifecycle` | `cinema/lifecycle.py:70` | Headless still uses `ThreadedLifecycle`; `RunState.headless` makes `_wait_for_gate` raise. `NullLifecycle.wait_for_gate` returns `True` unconditionally — using it would silently skip gate enforcement. |
| PLAN_REVIEW headless stall (FIXED) | `cinema_pipeline.py:1064`, `cinema/auto_approve.py:235` | Without `record_director_review_on_shots`, `_rules_for_plan` always vetoed → headless hang. Now called unconditionally; MODIFIED→APPROVED (cycle-17, `138d7c7`). |
| `evaluate_generation_quality` wired by T6 | `llm/chief_director.py:696` | Full 2×2 mutation matrix; **now called** by `diagnose_clip(deep=True)` in `cinema/shots/controller.py:4114` (T6, `10a0eb4`); vision-grounded since `d974c15` (take + reference images attached to the LLM call). |
| `style_director` is OpenAI-only | `llm/style_director.py:38` | No Anthropic path — asymmetric with the Anthropic-first ChiefDirector/CinemaDirector. |
| Veo `reference_images` silently dropped (Bug #4) | `veo_native.py:155` | Vertex rejects image+reference both set; identity comes from the start frame only. `driving_video_path` also unwired on Veo (only Sora wires it). |
| VEO_NATIVE has no quota guard | `phase_c_ffmpeg.py:376` | The 1800s cooldown TTL is set/checked only by the FAL-proxy `VEO` branch. |
| `close_up` unreachable in motion floors | `workflow_selector.py:170` | `MOTION_FIDELITY_FLOORS` has a `close_up` key but `classify_shot_type` never returns it. |
| Several live shot/project fields not in Pydantic models | `Shot` (`domain/models.py:82`) / `Project` (`domain/models.py:204`) | `objects`, `performance_engine`, `driving_video_path`, `director_review`, `screening_approved`, `needs_reassembly`, `auto_approve_audit` live via `extra="allow"`. Strict mode warns; default absorbs. |
| `shot_id` not globally unique | `domain/project_manager.py:405` | `shot_{scene_id}_{idx}` can collide across projects (cycle-6/S13 F1 CRITICAL) — always pair with `project_id` on endpoints. |
| Audio `CostTracker()` instances bypass the budget gate | `audio/dialogue.py`, `audio/music.py` | Audio helpers can still construct fresh no-budget trackers; performance capture now threads the core tracker through the adapters and pre-spend-gates both the resolved performance engine and expected Mode-B driving synth. |
| `EXPERIMENTS_DB_PATH` wired env-direct, not via `Settings` | `cost_tracker.py:157` vs `config/settings.py:128`, `cinema/core.py:113` | Since T7 (`4af8c05`) `CostTracker.__init__` resolves `db_path` arg > `EXPERIMENTS_DB_PATH` env > `data/experiments.db`, so the env var takes effect for every tracker. `Settings.experiments_db_path` is never threaded into the constructor — decorative; both read the same env var. |
| Project spend rehydrates at core construction | `cinema/core.py`, `cost_tracker.py` | A new `PipelineCore` seeds `spent_usd` from durable rows before admitting any paid work, whether the next run is fresh or checkpoint-resumed. Checkpoint restore repeats the same normalization defensively. |
| `_running_cores` and settings edits | `web_server.py:467` | Supported PUT/PATCH settings writes evict the idle core; direct out-of-band `project.json` edits still need a server restart. |
| Re-assemble must call `_assemble_approved_takes_core` directly | `web_server.py:4065`, `cinema_pipeline.py:783` | Calling the full `assemble_approved_takes()` from a Flask thread during screening deadlocks (the approve signal targets the original pipeline). |
| Single-mode / zero-caller features | `cinema/auto_approve.py:775`, `face_validator_gate.py` | `should_halt` / `needs_regenerate` in `face_validator_gate.py` were the max-tier best-of gate; with the max tier retired (WS1 Task 4) they have no live caller. `score_candidate` and `validate_lora_quality` remain in policy-inactive historical LoRA code, not a live product path. `summarize_audit` is defined but no web endpoint calls it. |
| `reporter.py` + dialogue helpers removed | — | The legacy `reporter.py` diagnostic orphan has been **deleted** outright; the dead dialogue helpers `format_dialogue_for_voiceover` / `dialogue_to_narration_text` were also removed (audio uses raw `generate_dialogue` output). |

---

## 4. Phase-by-Phase Deep Dive

This section walks the pipeline stage by stage in execution order, exactly as `CinemaPipeline.generate()` drives it (`cinema_pipeline.py:942`). Each stage documents its inputs, processing, the key functions (with file:line), the decision points (routing, cascade, gate pass/fail, tier selection), outputs, and failure/recovery behavior.

Two structural facts shape every stage below and are worth stating once:

- **The real orchestrator is `cinema_pipeline.CinemaPipeline` (`cinema_pipeline.py:49`).** It is now the only class by that name — the generic `cinema/pipeline.py` driver was deleted 2026-08-01 (ADR-081).
- **Three render stages are `Phase` objects** (keyframe, performance, motion) implementing the `Phase` Protocol (`cinema/phases/base.py:61`). The **gates between them are not phases** — they are inline `_wait_for_gate(...)` calls in the orchestrator. Ordinary per-shot failures stay non-aborting and surface through `on_failure` into `failed_shots`; structured budget refusals stop performance or motion so the run does not keep walking shots that would be refused identically.

### Stage map and progress checkpoints

| # | Stage | Type | Key entry point | Progress % | Gate after |
|---|---|---|---|---|---|
| 0 | Style rules + BGM | inline | `generate_style_rules()` / `_ensure_bgm()` | 2% | — |
| 1 | Scene decomposition | inline loop | `competitive_decompose_scene()` / `decompose_scene()` | — | PLAN_REVIEW (25%) |
| 2 | Keyframe / image render | `KeyframeRenderPhase` | `keyframe_render.py:31` | 50% | KEYFRAME_REVIEW (55%) |
| 3 | Performance capture | `PerformanceCapturePhase` | `performance.py:19` | 62% | PERFORMANCE_REVIEW (65%, conditional) |
| 4 | Motion / video render | `MotionRenderPhase` | `motion_render.py:125` | 80% | REVIEW (82%) |
| 5 | Assembly + audio mix | inline | `assemble_approved_takes()` | up to 95% | SCREENING (95%, optional) |
| 6 | Cleanup + complete | inline | `cleanup_project()` | 100% | — |

Verified call sites: PLAN_REVIEW gate `cinema_pipeline.py:1070`; keyframe phase `:1100`; KEYFRAME_REVIEW `:1110`; performance phase `:1130`; PERFORMANCE_REVIEW `:1153`; motion phase `:1180`; REVIEW `:1201`; assembly `:1208`.

```mermaid
flowchart TD
    A[Style rules + BGM<br/>2%] --> B[Scene decompose loop]
    B --> C{PLAN_REVIEW<br/>25%}
    C -->|all plans approved| D[KeyframeRenderPhase<br/>50%]
    C -->|headless + unapproved| X[GateNotSatisfiedError]
    D --> E{KEYFRAME_REVIEW<br/>55%}
    E --> F[PerformanceCapturePhase<br/>62%]
    F --> G{PERFORMANCE_REVIEW<br/>65%}
    G -->|all SKIP / no keyframe| H[MotionRenderPhase<br/>80%]
    G -->|needs review| H
    H --> I{REVIEW<br/>82%}
    I --> J[assemble_approved_takes<br/>normalize→stitch→grade→mix→loudnorm]
    J --> K{SCREENING<br/>95%}
    K -->|approved| L[cleanup + COMPLETE 100%]
```

---

### Stage 0 — Style rules and BGM (run setup)

**INPUTS:** `project.global_settings` (`music_mood`, `color_palette`, `aspect_ratio`, pre-existing `style_rules`, `music_mastering`); the project snapshot reloaded from disk by `_refresh_project_snapshot()` (`cinema_pipeline.py:463`).

**PROCESSING:**
1. `generate_style_rules(project_name, mood, color_palette, music_mood, aspect_ratio)` (`llm/style_director.py:19`) produces a 7-key style dict (`director_vision`, `cinematography_rules`, `color_grading_palette`, `lighting_rules`, `sound_design`, `photorealism_rules`, `composition_rules`), persisted via `mutate_project` (`cinema_pipeline.py:958-993`).
2. `_ensure_bgm(settings)` (`cinema_pipeline.py:770`) generates BGM upfront via `generate_fal_bgm(..., duration=47)`, then optionally masters it via `master_music(..., preset="cinema_master")`.

**KEY FUNCTIONS:** `generate_style_rules` (`llm/style_director.py:19`, OpenAI-only — see failure mode); `style_rules_to_prompt_suffix` (`llm/style_director.py:233`, the string appended to every downstream image prompt); `_ensure_bgm` (`cinema_pipeline.py:770`).

**DECISION POINTS:**
- **Skip style-gen if pre-baked.** If `global_settings.style_rules` is non-empty at run start, the LLM call is skipped entirely (`cinema_pipeline.py:959`). Operators who want determinism can hand-author this dict.
- **Style director is OpenAI-only.** If only `ANTHROPIC_API_KEY` is set (no OpenAI key), `generate_style_rules` falls through to `_default_style_rules` immediately (`llm/style_director.py:152-158`) — asymmetric with ChiefDirector/CinemaDirector, which prefer Anthropic.

**OUTPUTS:** `project.global_settings.style_rules` persisted; `temp/bgm_*.mp3` (mastered or raw).

**FAILURE MODES + RECOVERY:** Style-gen failure → hardcoded `_default_style_rules` keyed on mood (`llm/style_director.py:152`); the run continues. BGM mastering failure is **non-critical** — logs a WARNING and proceeds with the unmastered track (`cinema_pipeline.py:627`).

---

### Stage 1 — Scene decomposition (script → shots)

**INPUTS:** Per scene: `scene` dict (`title`, `action`, `dialogue`, `mood`, `duration_seconds`, `characters_present`, `location_id`), the matched `characters` and `location` dicts, `global_settings`, and the `style_rules` from Stage 0. The injected `PIPELINE_CONTEXT` string (`pipeline_context.py:15`, loaded from `config/prompts/pipeline_context.md`) rides along in every LLM system prompt.

**PROCESSING (per scene with empty `shots`):**
1. **Route:** `use_competitive = settings.get("competitive_generation", True)` (`cinema_pipeline.py:1026`).
2. **Decompose:** `competitive_decompose_scene()` (`domain/scene_decomposer.py:998`) runs GPT-4o + Claude-Sonnet in parallel via `LLMEnsemble.competitive_generate(task_type="decompose")` and a judge picks the winner; or `decompose_scene()` (`domain/scene_decomposer.py:838`) runs a single GPT-4o tool-loop call. Shot count: `target_shots = max(2, min(5, int(duration_seconds / 2.5)))` (`domain/scene_decomposer.py:563` direct; `:737` competitive).
3. **Validate (ChiefDirector pre-gen gate):** `self.director.validate_shot_prompts(shots, scene)` (`cinema_pipeline.py:1041`; `llm/chief_director.py:296`) enforces hard constraints HC1–HC8 and returns `APPROVED` / `MODIFIED` / `REJECTED` / `REVIEW_REQUIRED`; unavailable or unusable evidence cannot clear the gate.
4. **Record the verdict — critical:** `record_director_review_on_shots(shots, review)` (`cinema_pipeline.py:1064`; `cinema/auto_approve.py:235`) writes `shot["director_review"]` onto every shot. **This call is load-bearing for headless runs** (see failure mode).
5. **Persist:** `update_scene_shots(project, scene_id, shots)` (`domain/scene_decomposer.py:1242`) writes shots under the per-project lock.
6. **Per-scene dialogue:** `_ensure_scene_audio(scene, chars)` (`cinema_pipeline.py:550`) calls `generate_dialogue` → `generate_dialogue_voiceover`, caching the MP3.
7. `_save_checkpoint()` after each scene.

**DECISION POINTS:**
- **Competitive vs single-model** (`cinema_pipeline.py:1026`). Competitive doubles LLM cost but consistently wins on quality.
- **MODIFIED → APPROVED normalization.** `record_director_review_on_shots` normalizes a `MODIFIED` verdict to a gate-decision of `APPROVED` (`cinema/auto_approve.py:246`, cycle-17 user decision, commit `138d7c7`). The raw verdict is preserved in `chief_director_verdict`. Any older doc that calls MODIFIED a *blocking* state is stale.
- **REJECTED → re-decompose.** A REJECTED scene re-runs `decompose_scene` with stricter constraints (`cinema_pipeline.py:1047`).

**OUTPUTS:** Per-shot dicts (`make_shot`, `domain/project_manager.py:386`) with `prompt`, `camera`, `visual_effect`, `target_api`, `characters_in_frame`, `director_review`, `plan_status="pending_review"`; per-scene dialogue MP3.

**FAILURE MODES + RECOVERY:**
- **LLM unavailable / parse failure.** `decompose_scene` falls back to `_fallback_decompose` (`domain/scene_decomposer.py:1199`) — exactly two hardcoded shots (an establishing wide + a medium close-up). `validate_shot_prompts` is fail-safe-for-throughput: on a None client or persistent `JSONDecodeError` (after ≤1 retry) it returns `APPROVED` with no modifications (`llm/chief_director.py:507-568`).
- **PLAN_REVIEW headless stall (FIXED, cycle-17).** Before `record_director_review_on_shots` was called unconditionally, `_rules_for_plan`'s `plan_decision_not_approved` veto always fired (because `shot["director_review"]` was never written), so a headless run polled forever. The fix wires the writer at `cinema_pipeline.py:1064`. **If you load shots that never passed through this call, the PLAN gate will veto.**

---

### PLAN_REVIEW gate (25%)

The first of five gates. Each gate runs the same machinery (`ReviewController._wait_for_gate`, `cinema/review/controller.py:519`): set `runstate.current_stage`, emit progress, run an **auto-approve pre-screen**, then either block on the operator (web) or fail fast (headless).

**Auto-approve pre-screen** (`_run_auto_approve_pass`, `cinema/review/controller.py:294`): for every unapproved shot, `check_gate("plan", ...)` (`cinema/auto_approve.py:759`) evaluates the plan veto rules (`_rules_for_plan`, `cinema/auto_approve.py:214`):
- `plan_decision_not_approved` — fires if `director_review.decision != "APPROVED"`.
- `plan_has_violations` — fires if `director_review.violations` is non-empty.

**Gate predicate** (`_gate_satisfied`, `cinema/review/controller.py:265`): PLAN_REVIEW is satisfied when **all shots have `plan_status == "approved"`**.

**DECISION POINT — web vs headless:**
- **Web:** `lifecycle.wait_for_gate(gate, predicate)` polls every 0.5s (`cinema/lifecycle.py:182`) until the operator approves remaining shots via `POST /api/projects/<pid>/shots/<shot_id>/plan/approve` → `approve_shot_plan` (`cinema/review/controller.py:695`).
- **Headless** (`RunState.headless=True`): the predicate is checked **once**; if unsatisfied, `GateNotSatisfiedError` is raised (`cinema/review/controller.py:93`) with per-shot reasons from `_gate_block_details`. This replaces the prior infinite poll.

**Critical headless caveat:** `headless=True` does **not** swap in `NullLifecycle`. It still uses `ThreadedLifecycle`; only `_wait_for_gate` changes behavior by reading `runstate.headless`. `NullLifecycle.wait_for_gate` returns `True` unconditionally (`cinema/lifecycle.py:110`) and would silently *skip* gate enforcement — so the only correct non-interactive path is `CinemaPipeline(headless=True)`.

---

### Stage 2 — Keyframe / image render

**INPUTS:** Approved shot plans. Per shot: `prompt`, `characters_in_frame`, previous shot's approved keyframe (img2img init), `global_settings` (sampler knobs, identity backend/strictness, style paths, plus legacy read-only LoRA snapshots that have no production consumer), and the production ComfyUI workflow graph (`pulid.json`).

**PROCESSING** (`KeyframeRenderPhase.run`, `cinema/phases/keyframe_render.py:68` → per shot `generate_keyframe_take`, `cinema/shots/controller.py:1308`):
1. Skip shots already carrying `approved_keyframe_take_id`.
2. Require `shot["plan_status"] == "approved"`.
3. `ContinuityEngine.enhance_shot_prompt` (`domain/continuity_engine.py:446`) builds the augmented prompt + a `continuity_config` dict (img2img flag, `init_image`, `denoise_strength`, scene/location seed, `pulid_weight_override`, identity anchor, threshold).
4. Optional `optimize_shot_prompt` (`llm/prompt_optimizer.py:702`) when `prompt_optimizer_enabled=True`, cached on `shot["optimizer_cache"]`.
5. Atomically claim `shot["deferred_keyframe_job"]` with a private attempt token and active-request deadline, then call `generate_ai_broll(...)`. A concurrent request sees the claim and cannot submit another paid render.
6. Post-gen identity validation: `IdentityValidator.validate_image(...)` against `identity_strictness` (default 0.60).
7. Append the take and clear the durable keyframe reservation in the same locked mutation; then record cost.

**KEY FUNCTIONS:** `generate_ai_broll` (`phase_c_assembly.py:98`); `enhance_shot_prompt` (`domain/continuity_engine.py:461`); `classify_shot_type` (`workflow_selector.py:188`); `get_workflow_params` (`workflow_selector.py:260`) / `apply_workflow_params` (`workflow_selector.py:357`); `get_adaptive_pulid_weight` (`workflow_selector.py:382`).

**DECISION POINTS:**

*Image path* — `generate_ai_broll` (`phase_c_assembly.py:98`) runs one tier (the `quality_tier == "max"` fork was retired in WS1 Task 4; `quality_tier` is now accepted but informational):

| Path | Behavior |
|---|---|
| Gemini 3.1 Flash Image (primary for referenced characters) | Used when Google/Gemini credentials and a character reference are available unless `identity_backend="pod"`. |
| ComfyUI + PuLID via `RunPodComfyUI` (first reference-conditioned fallback) | Used when `COMFYUI_SERVER_URL` is set AND `pulid.json` exists. |
| `_fal_flux_fallback` (fallback) | FLUX Kontext Max Multi → FLUX-Pro → FLUX Schnell → Pollinations (`phase_c_assembly.py:1040`). |

*Shot-type → PuLID weight* (production `WORKFLOW_TEMPLATES`, `workflow_selector.py:29`, **verified**):

| shot_type | pulid_weight | image route |
|---|---|---|
| portrait | **1.0** | ComfyUI PuLID (max face-lock) |
| medium | **0.9** | ComfyUI PuLID |
| wide | **0.65** | ComfyUI PuLID |
| action | **0.8** | ComfyUI PuLID |
| landscape | **0.0** | PuLID skipped → FAL |

*Identity thresholds* (`SHOT_TYPE_THRESHOLDS`, `identity/types.py:96`, **verified**): portrait 0.75/0.70/0.60, medium 0.70/0.65/0.55, wide 0.60/0.55/0.45, action 0.65/0.60/0.50, landscape 0.0 (strict/standard/lenient). On retry, the threshold degrades linearly toward `lenient` (`get_threshold_for_shot`, `identity/types.py:105`), preventing infinite retry loops.

*img2img / continuity denoise* (`TemporalConsistencyManager.get_denoise_strength`, `domain/continuity_engine.py:368`): first shot 0.55, location change 0.50, same-location index ≤1 → 0.40, same-location index >1 → 0.30. UI override `continuity_options.img2img_denoise` clamps to **[0.2, 0.6]**.

**OUTPUTS:** JPEG at `{project_dir}/shots/{shot_id}/{take_id}.jpg` (1344×768); `ImageGenResult(path, api_name)` with the backend token; take metadata carrying `identity_score`, `identity_failure_reason`, `suggested_pulid_adjustment`.

**FAILURE MODES + RECOVERY:**
- **Ordinary per-shot failures remain operator-rework failures.** They route through `on_failure`; budget refusal and deferred provider state stop the phase without mislabelling the shot failed.
- **ComfyUI terminal error, bounded 600s deadline, invalid output, or pod down** → `_fal_flux_fallback` only after terminal failure or confirmed cancellation. A lost/malformed `/prompt` acknowledgement, unconfirmed cancellation, worker crash after the durable claim, or missing output after reported completion leaves `deferred_keyframe_job`, stops the phase, and disables every keyframe-creation control in Review. After checking ComfyUI queue/history and billing, **Confirm Manual Reconciliation** clears the marker through an explicit confirmation endpoint; it does not retry or create a take, and it returns 409 while the original claim remains inside its 660-second active window. Attempt-bound mutations prevent a late expired response from erasing or publishing over a newer claim. Global `/interrupt` remains an explicit operator control, not an automatic fallback step.

---

### KEYFRAME_REVIEW gate (55%)

Same machinery as PLAN_REVIEW. Auto-approve runs `_rules_for_image`: `image_composite_below_threshold` (production threshold `image_min_composite=0.60`, or `image_min_composite_fallback=0.78` for a fallback-engine take), `image_cascade_fallback`, and `image_over_budget`. On approval, `approved_keyframe_take_id` is set to the highest-composite take. Fresh projects persist the same 0.60 production floor that `AutoApproveConfig.from_project` uses, avoiding the retired 0.97 max-tier trap. **Gate predicate:** all shots have `approved_keyframe_take_id`.

---

### Stage 3 — Performance capture

**INPUTS:** Shots with an approved keyframe. Per shot: `performance_engine` (routed earlier by `route_performance_engine`, `domain/performance.py:110`), optional `driving_video_path`, dialogue/audio.

**PROCESSING** (`PerformanceCapturePhase.run`, `cinema/phases/performance.py:35` → `generate_performance_take`): iterate shots, calling the performance engine for each that needs one. Three skip conditions per shot (`cinema/phases/performance.py:63-72`): (1) already has `approved_performance_take_id`; (2) `performance_engine == "SKIP"`; (3) no `approved_keyframe_take_id` (no anchor → motion would also skip). A take can also self-report `result.get("skipped")`.

**KEY FUNCTIONS:** `route_performance_engine` (`domain/performance.py:110`); `precondition_error` (`domain/performance.py:186`); `validate_performance_take` (`performance/identity_gate.py:106`, single-frame GhostFaceNet at 1s, floor 0.70).

**DECISION POINTS — engine routing** (`domain/performance.py:110`):

| Condition | Engine |
|---|---|
| no characters / wide-no-dialogue / landscape | `SKIP` |
| dialogue + face-readable (`close_up`/`portrait`/`medium`) | `ACT_ONE` (or `LIVE_PORTRAIT` if `performance_budget_mode="budget"`) |
| action, no dialogue | `VIGGLE` (uncontained ADR-082; catalog `LIMITED` — needs a driving video) |
| any remaining dialogue | `ACT_ONE` |

Driving-video mode (`driving_video_source`, `domain/performance.py:168`): `"upload"` when `driving_video_path` set; `"tts_auto"` when engine ≠ SKIP with dialogue; else `"none"`. ACT_ONE (Runway Act-Two, `performance/act_two.py`) requires a driving video by dispatch time — `precondition_error` accepts audio_path alone at this pre-check since Mode-B can still synthesize one from it before dispatch; LIVE_PORTRAIT/VIGGLE require an explicit driving video.

**OUTPUTS:** Performance take records appended to the shot; `approved_performance_take_id` set at the gate.

**FAILURE MODES + RECOVERY:** Per-shot failure doesn't fail the phase (always `ok=True`). A shot that *was* supposed to get a performance but failed (landing in `failed_shots`) will keep the PERFORMANCE_REVIEW gate open for manual handling — it is not auto-skipped.

---

### PERFORMANCE_REVIEW gate (65%, conditional)

**This gate is conditionally skipped.** The orchestrator computes `all_skipped` over the project (`cinema_pipeline.py:1133`): every shot is either `performance_engine == "SKIP"` **or** lacks an approved keyframe. If `all_skipped`, the gate is bypassed with a `PERFORMANCE_SKIPPED_GATE` progress event at 65%; otherwise the `PERFORMANCE_REVIEW` gate-wait runs at `cinema_pipeline.py:1140`.

> **Cross-reference:** the `_gate_satisfied` PERFORMANCE_REVIEW branch (`cinema/review/controller.py:265-278`) carries an inline comment pointing at the orchestrator's all-skipped bypass at `cinema_pipeline.py:1133-1140`; the predicate logic mirrors that bypass, extended with the explicit-approval branch. (A previously-flagged stale line-cite in that comment was fixed in the same touch as this note.)

**Auto-approve here is opt-in.** The motion gate map entry is only added when `CINEMA_AUTO_APPROVE_MOTION` is truthy (`1`/`true`/`yes`, case-insensitive; `cinema/auto_approve.py:620`). Without it, PERFORMANCE_REVIEW is always manual even when auto-approve is otherwise enabled. When enabled, `_rules_for_motion` (`cinema/auto_approve.py:351`) checks `motion_min_identity=0.85` and `motion_min_motion_score=0.7`. **Gate predicate** (`cinema/review/controller.py:224`): each shot is SKIP, lacks a keyframe, or has `approved_performance_take_id`.

---

### Stage 4 — Motion / video render

**INPUTS:** Approved keyframes (and approved performance takes where applicable). Per shot: `target_api`, `camera`, `duration`, `motion_description`/`prompt`, `negative_constraints`, `has_dialogue` (derived from optimizer purpose), `driving_video_path`, `multi_angle_refs`, `ctx` carrying `api_engines` + `cascade_retry_limit`.

**PROCESSING** (`MotionRenderPhase.run`, `cinema/phases/motion_render.py:525` → `generate_motion_take` → `generate_ai_video`, `phase_c_ffmpeg.py:208`):

*Storyboard batch path (optional).* When `global_settings.api_engines.KLING_NATIVE.storyboard_mode=True`, the aspect is non-portrait, and a scene has **2–6 non-dialogue unapproved shots** all with approved keyframes, `_run_storyboard_scene` calls `KlingNativeAPI.generate_storyboard()` once, then `split_video_into_segments()` recovers per-shot clips and registers them via `_finalize_motion_take(record_cost=False)`. Dialogue-purpose shots are deliberately ineligible so they cannot bypass per-shot F1b evidence. Cost is recorded once for the batch. **Caveat:** `storyboard_mode` is at the nested path `global_settings.api_engines.KLING_NATIVE.storyboard_mode`; reading it flat returns `None` (`_get_storyboard_mode`).

*Per-shot path* — `generate_ai_video` (`phase_c_ffmpeg.py:208`) classifies the shot, resolves the engine, and runs a fault-tolerant cascade.

**KEY FUNCTIONS:** `generate_ai_video` (`phase_c_ffmpeg.py:208`); inner `try_next_api` (`phase_c_ffmpeg.py:1089`) and `_record_video_cascade` (`phase_c_ffmpeg.py:861`); the dialogue override + `audio_embedded` tagging + mandatory lipsync at `cinema/shots/controller.py:134` (routing helper), `:184` (tagging), and `:1880` (F1b lipsync), all driven from `generate_motion_take` (`:2956`).

**DECISION POINTS:**

*API resolution* (dialogue-routing helper `cinema/shots/controller.py:134-180`, applied in `generate_motion_take`):
- `target_api == "AUTO"` → run the optimizer suggestion and shot template through the automatic-dispatch policy. Deprecated or explicit-only engines are rejected even if they remain valid catalog keys; the first admitted candidate wins.
- **Dialogue override (F1a):** if `has_dialogue=True`, scan `PURPOSE_API_RANKING[purpose]` for the first entry with `native_audio=True AND modality=="video" AND status=="live"` — currently **GEMINI_OMNI** (it outranks `VEO_NATIVE` in `PURPOSE_API_RANKING["dialogue_close_up"]`, `domain/scene_decomposer.py:183`) — and pin it; `video_fallbacks` is nulled only in `dialogue_voice_mode="native"` — the overlay default keeps the template fallbacks so a Gemini/Veo RAI-block cascades to a silent engine and F1b overlays the voice. `GEMINI_OMNI` and `VEO_NATIVE` are the *only two* engines with `native_audio: True` (`domain/scene_decomposer.py:43-44`).
- Explicit `target_api` → use as-is, no fallbacks.

*Fallback cascade* (`try_next_api`, default order = the module-level `DEFAULT_VIDEO_CASCADE`): `VEO_NATIVE → SEEDANCE → KLING_3_0 → RUNWAY_GEN4 → LTX → VEO`. `GEMINI_OMNI` is deliberately excluded from this blind default order (its duration/resolution/audio are prompt-inferred, not structured kwargs) — it is reached through the per-shot-type template primary or an explicit target. Deprecated `SORA_NATIVE`, `KLING_NATIVE`, and legacy `RUNWAY`, plus retired `SORA_2`, are absent from automatic routing. The cascade filters already-attempted engines and any disabled via `ctx.api_engines[engine].enabled == False`. On total exhaustion it sleeps 30s and retries the whole list up to `MAX_CASCADE_RETRIES` (default 1, override `cascade_retry_limit`).

*Per-engine duration / behavior highlights:*

| Engine | Duration | Notable |
|---|---|---|
| KLING_NATIVE | 5s | Deprecated explicit-only v1.6 compatibility; removed from automatic templates/cascade. Its separate storyboard batch remains opt-in for eligible non-dialogue scenes. |
| SORA_NATIVE | explicit-only; 4 / 8 / 12s | still-image `input_reference` only; driving video is rejected before network |
| VEO_NATIVE | **clamped to {4,6,8}** (`veo_native.py:26`) | `generate_audio=(landscape or has_dialogue)`; 5s is server-rejected, snapped up (5→6, 7→8) |
| LTX | `duration*24` frames | 4K for landscape; cheapest |
| RUNWAY_GEN4 | 10s | `runwayml` SDK, 300s poll |

**OUTPUTS:** MP4 at the shot's take path; `_cascade_out["cascade_metadata"]` records engine/attempts and backend-verified capabilities; `take.metadata.audio_embedded=True` only when the winning backend actually generated native dialogue audio (Vertex Veo can, Developer-API Veo cannot); `take.metadata.has_dialogue` is always written for gate awareness.

**FAILURE MODES + RECOVERY:**
- **Cascade** is the primary recovery only for failures proven to occur before paid submission and explicit terminal provider failures (including safety/RAI rejection). Those cases call `try_next_api`, which recurses into the next engine. Once any durable FAL motion engine (VEO, Kling 3.0, Seedance, or LTX), Runway, Gemini Omni, or native Veo may have accepted work, an ambiguous submit/poll/result-publication outcome records `deferred_motion_job` and stops instead of risking a duplicate charge. The UI can check/resume the exact durable FAL/Runway task; native providers without a safe application recovery binding remain manual reconciliation.
- **Dialogue native-audio guarantee is primary-attempt only.** When `has_dialogue=True` the override sets `video_fallbacks=None` (native mode) or keeps the template fallbacks (overlay default). In overlay mode, a pinned `GEMINI_OMNI` attempt falls through toward engines without `native_audio` only after an explicit pre-submit/terminal/RAI failure; an accepted or ambiguous job defers recovery instead (`cinema/shots/controller.py:165-180`).
- **Mandatory lipsync pass (F1b).** Post-render, if `has_dialogue=True` AND `not audio_embedded`, `generate_lip_sync_video(mode="auto")` runs (`cinema/shots/controller.py:1880`), writing both `lipsync_score` and `lipsync_validation_state`. No output, missing prerequisites, skip mode, or exceptions become `None`/`UNKNOWN`, never numeric zero or a synthetic pass. Dialogue shots are excluded from the storyboard batch so they traverse this per-shot path.
- **VEO_NATIVE has no quota cooldown.** The `_VEO_QUOTA_EXHAUSTED_UNTIL` TTL flag (`phase_c_ffmpeg.py:36`) is set/checked only on the FAL-proxy `VEO` branch. Native Veo still has no cooldown, but an ambiguous quota/transport result after submission is deferred; it does not silently cascade.

---

### REVIEW gate (82%)

The last per-shot gate before assembly. `_rebuild_review_clips(project)` builds the in-memory manifest first (`cinema/review/controller.py:659`). Auto-approve runs `_rules_for_final` (`cinema/auto_approve.py:395`) over `postprocess_variants + motion_takes`:
- `final_lipsync_unverified` — unconditional selected-take veto for `UNKNOWN`/`UNAVAILABLE`, missing/non-finite evidence on dialogue takes, and legacy storyboard dialogue takes inferred from optimizer purpose. Audio-presence flags do not prove synchronization, and this veto remains active when `final_min_lipsync=0`.
- `final_lipsync_below_threshold` — compares the selected measurable take against `final_min_lipsync=0.8`; non-dialogue takes remain N/A.
- `final_upstream_was_auto_approved` — **safety net**: if any earlier gate auto-approved this shot, force human review at REVIEW (`final_require_human_if_upstream_auto=True` by default).

On approval, `approved_final_take_id` (and `approved_motion_take_id` via the `source_take_id` chain) is set to the same take the rules judged (`pick_best_take_for_final` prefers measurable lip-sync evidence, then non-fallback, then highest composite). **Gate predicate** (`cinema/review/controller.py:224`): all shots have `approved_final_take_id`.

> **Footgun for unattended runs:** `final_require_human_if_upstream_auto=True` blocks a *fully* headless completion even when every other rule passes — by design. To complete fully unattended, set it to `false` in `global_settings.auto_approve` (after the pipeline is calibrated). This is the single most common headless dead-end after the cycle-17 PLAN fix.

---

### Stage 5 — Assembly + audio mix

**INPUTS:** Approved final takes (collected in scene order), per-scene dialogue MP3s, per-scene foley MP3s, the BGM MP3, and `global_settings` (`mood`, `scene_transitions`, `transition_duration`, `music_mastering`).

**PROCESSING** (`assemble_approved_takes`, `cinema_pipeline.py:1155` → `_assemble_approved_takes_core`, `:1052` → `_assemble_final`, `:1675`):
1. `_refresh_project_snapshot()` then re-assert the REVIEW gate as a guard.
2. `_build_scene_packages(project)` (`cinema_pipeline.py:945`) resolves each approved take path and collects per-scene audio/foley. **All-embedded detection:** when every approved shot in a scene has `metadata.audio_embedded=True`, standalone TTS is suppressed to avoid double-voice from Veo/Omnihuman.
3. `_assemble_final(scene_data, bgm_path, settings)` (`cinema_pipeline.py:1675`):
   a. **Normalize** each clip to 1920×1080@30fps (`scale + pad + fps`, `libx264 crf=20`, `aac 192k`).
   b. **Stitch** — hard-cut concat demuxer by default, OR `xfade_concat` cross-dissolve per scene boundary when `scene_transitions=True` (`phase_c_ffmpeg.py:3612`), with transition clamped to `0.4 * min(durations)`.
   c. **Color grade** via `apply_color_grade()` (`phase_c_ffmpeg.py:3197`), resolving `global_settings.color_grade_preset` → `music_mood`→preset map → `"warm_cinema"` (`COLOR_GRADE_PRESETS`, `phase_c_ffmpeg.py:3185`).
   d. **Tri-mix audio:** voice (1.0) + BGM (0.12) + foley (0.20). Voice source binds dynamically: `[0:a]` when audio is embedded, else the standalone dialogue MP3; `amix duration=longest` for the standalone path, `first` when embedded.
   e. **Two-pass loudnorm** EBU R128 (`two_pass_loudnorm`, `phase_c_ffmpeg.py:3335`; defaults -14 LUFS / 11 LU / -1.5 dBTP).

**KEY FUNCTIONS:** `_assemble_final` (`cinema_pipeline.py:1675`); `_build_scene_packages` (`:945`); `xfade_concat` (`phase_c_ffmpeg.py:3612`) / `_build_xfade_filtergraph` (`:3543`); `apply_color_grade` (`phase_c_ffmpeg.py:3197`); `two_pass_loudnorm` (`phase_c_ffmpeg.py:3335`).

**DECISION POINTS:**
- **Stitch mode** — `scene_transitions` (default `False`).
- **Voice source** — embedded vs standalone, decided per the all-embedded detection.
- **Re-assembly bypass (S21).** The web re-assemble endpoint calls `_assemble_approved_takes_core()` **directly** (`cinema_pipeline.py:1052`), skipping the SCREENING gate-wait — calling the full public `assemble_approved_takes()` from a Flask request thread during screening would deadlock (the gate predicate polls `is_screening_approved()`, which is False by design, and the request's fresh pipeline is not the instance `signal_gate` will unblock).

**OUTPUTS:** `exports/final_cinema.mp4` — 1920×1080@30fps, H.264, AAC, EBU R128 normalized, color-graded, with optional scene transitions and the dialogue+BGM+foley mix. Per-stage intermediates land in `temp/` (`*_norm.mp4`, `stitched.mp4`, `graded.mp4`).

**FAILURE MODES + RECOVERY:**
- **Audio mix fallback cascade** (`_assemble_final`): 3-input → 2-input → BGM-only → copy-as-is, so a missing foley/BGM track degrades gracefully rather than failing assembly.
- **xfade audio mismatch (FIXED, Lane V #24/#25).** Engines like Kling produce silent clips; Veo embeds audio. `_has_audio_stream` (`phase_c_ffmpeg.py:3523`) probes each leg: all-silent → video-only filtergraph (`alab=None`); mixed → silent legs padded with `anullsrc` and every leg normalized to 48kHz stereo `fltp` before `acrossfade` (`phase_c_ffmpeg.py:1444-1511`). A `xfade_concat` failure raises, and the caller falls back to hard-cut concat.
- **Color grade is a single project-level choice** — `global_settings.color_grade_preset` when set, else the `music_mood`→preset map, else `"warm_cinema"`. Every scene gets the same grade; per-scene `Scene.mood` is not honored at the final grade.

---

### SCREENING gate (95%, optional) + Stage 6 — Cleanup & complete

**SCREENING gate** (`assemble_approved_takes`, `cinema_pipeline.py:1155-1186`): runs only if `_screening_stage_enabled()` (`cinema/screening.py:104`; project override > `CINEMA_SCREENING_STAGE` env > default ON). The pipeline emits 95% progress and blocks on `lifecycle.wait_for_gate("SCREENING", predicate)` where the predicate reads `is_screening_approved(project)` (`cinema/screening.py:330`).

During the wait the operator: hits `POST .../assemble/screen` for the timeline manifest; may iterate individual shots (each iterate marks `mark_shot_needs_reassembly`, `cinema/screening.py:406`); may `POST .../assemble/re-assemble` to re-stitch only dirty shots (`clear_needs_reassembly(only_shots=...)` preserves concurrently-dirtied shots, `cinema/screening.py:456`); and finally `POST .../screening/approve` → `mark_screening_approved` + `lifecycle.signal_gate("SCREENING")` (`web_server.py:3854`) to wake the waiter. **Precondition:** `screening/approve` requires `exports/final_cinema.mp4` to exist, returning 409 otherwise (`api_screening_approve`, `web_server.py:5370`).

**Cleanup & complete** (`cinema_pipeline.py:905-935`): `cleanup_project(pid, aggressive=False)` purges intermediate temp artifacts (always-delete patterns only; generated media preserved unless `aggressive=True`); `cost_tracker.get_video_cost()` logs the spend breakdown; `_clear_checkpoint()` removes `temp/pipeline_state.json`; a final `COMPLETE` progress event fires at 100%.

**FAILURE MODES + RECOVERY:** Cleanup is non-fatal — wrapped in try/except, a failure logs and the run still completes (`cinema_pipeline.py:906-913`). Across the whole run, **checkpointing** (`_save_checkpoint`, `cinema/checkpoint.py:99`, atomic via `mkstemp + os.replace`) is written after every scene and audio step, so a crashed run resumes via `generate(resume=True)` → `_restore_from_checkpoint` (`cinema/checkpoint.py:186`), which rehydrates `RunState` and marks any vanished referenced files as `"lost"`.

---

**Cross-cutting note on the cost gate (assembly-relevant):** the budget gate (`would_exceed`, `is_over_budget`) covers image/video generation and performance capture through the shared `CostTracker`. Audio modules (`audio/dialogue.py`, `audio/music.py`, `audio/foley.py`) still have isolated helper paths, so operators relying on `budget_limit_usd` should treat standalone audio spend as a remaining limitation unless the caller explicitly threads the core tracker.

---

## 5. The User Manual — Driving It to MAXIMUM Capability

This is the operator's playbook. It assumes you have the server running (see §3 for env-var setup) and want to take a project from a blank idea to a finished, photorealistic film — and to squeeze every drop of quality out of the pipeline along the way. Every knob below is grounded in a real setting, flag, or endpoint with a file:line citation so you can verify it yourself.

> **Two things to internalize before you start.**
> 1. **`web_server.py` is the only entry point.** The old CLI (`main.py`) is deleted. Everything you do is an HTTP call to the Flask server (port 8080, `web_server.py:4242`) or a click in the React UI that maps to one. There is no auth layer — CORS is the only access control (`web_server.py:69`), so do not expose it to a hostile network without a reverse proxy.
> 2. **Per-project quality knobs live in `project["global_settings"]`, set via `PUT /api/projects/<pid>` (`web_server.py:1388`).** They are read at runtime through `get_project_setting(ctx, key, default)` (`cinema/context.py:157`), *not* from `config/settings.py`. The `config/settings.py` singleton is for API keys and infra paths only. If a doc tells you to set a creative knob via an env var, it is almost certainly wrong — the only env vars that change pipeline *behavior* are the `CINEMA_*` flags in §5.5.

### 5.1 End-to-End Operation: From Idea to Final Film

The pipeline is a fixed gate sequence owned by `CinemaPipeline.generate()` (`cinema_pipeline.py:942`):

```
STYLE → SCENE_DECOMPOSE → PLAN_REVIEW → KEYFRAME_RENDER → KEYFRAME_REVIEW
   → PERFORMANCE_CAPTURE → PERFORMANCE_REVIEW → MOTION_RENDER → REVIEW
   → ASSEMBLY → SCREENING → COMPLETE
```

Five of those are **mandatory operator gates** (PLAN_REVIEW, KEYFRAME_REVIEW, PERFORMANCE_REVIEW, REVIEW, SCREENING). At each, the pipeline worker thread blocks in `lifecycle.wait_for_gate` until you act — or, if auto-approve clears every shot, it sails through unattended (§5.3, §5.6).

#### The operator workflow, step by step

| # | Action | Endpoint (verify) | What happens |
|---|---|---|---|
| 1 | **Create project** | `POST /api/projects` (`web_server.py:1101`) | `create_project(name)` returns a project with a `pid`. |
| 2 | **Configure global settings** | `PUT /api/projects/<pid>` (`web_server.py:1388`) | Writes your `global_settings` dict (aspect ratio, language, mood, quality tier, identity knobs, auto-approve thresholds…). |
| 3 | **Add characters** (with reference images) | `POST .../characters` — multipart plus stable 32-hex `creation_request_id` | `create_character_with_images` face-detects the best upload, generates five FLUX refs through durable request-ID recovery and the shared budget tracker, indexes each as an immutable `character_reference`, computes an embedding, and assigns a voice. Retry `paid_work_pending`/`artifact_version_pending` with the same token; stop for `paid_work_reconciliation_required`. |
| 4 | **Add locations** | `POST .../locations` (`web_server.py:2236`) | Builds a reusable `prompt_fragment` + deterministic `seed` so every shot at that location is architecturally consistent. |
| 5 | **(Optional) Style board** | `POST .../style-board` (`web_server.py:2015`) | Uploads style-reference images into `style_reference_paths`. (Its FLUX Redux consumer was the max tier, retired in WS1 Task 4 — the path is threaded but dormant, pending the FLUX.2 A/B rework.) |
| 6 | **Add scenes** | `POST .../scenes` (`web_server.py:2383`) | A scene = title, action, mood, dialogue, duration, characters, location. |
| 7 | **(Optional) Generate dialogue** | `POST .../scenes/<sid>/generate-dialogue` (`web_server.py:2622`) | LLM writes per-character spoken lines. |
| 8 | **(Optional) Generate style rules** | `POST .../style-rules` (`web_server.py:2715`) | LLM produces cinematography/color/lighting/photorealism rules persisted into `global_settings.style_rules`. *Skipped automatically at run time if already present* (`cinema_pipeline.py:959`). |
| 9 | **(Optional) Decompose a scene early** | `POST .../scenes/<sid>/decompose` (`web_server.py:2658`) | Turns a scene into shots now (single-model path — see the divergence note below). |
| 10 | **Queue the run** | `POST /api/projects/<pid>/generate` (`web_server.py:3310`) | Returns `202` with a stable durable `job_id` and queue snapshot. A repeat while active returns the same project job; a fixed worker pool starts it when capacity is available. |
| 11 | **Stream progress / inspect queue** | `GET /api/projects/<pid>/stream` and `.../pipeline-state` (`web_server.py:3474`, `:4217`) | Per-subscriber SSE fan-out/replay plus durable queued/running/terminal state, position, attempt count, checkpoint-resume flag and legal actions. A second tab receives its own events; it does not steal from the first. |
| 12 | **Clear the gates** | per-gate approve endpoints (§5.1 gate table) | You approve shot plans, keyframes, performances, final takes. |
| 13 | **Screen & sign off** | `POST .../assemble/screen` → `.../screening/approve` (`web_server.py:3768`, `:2280`) | Preview the assembled cut, iterate shots, then approve. |
| 14 | **Retrieve/package the film** | `GET /api/projects/<pid>/export`; Preview → **Client delivery** | Raw final MP4 remains available. The version selector can package current or explicit historical client-deliverable IDs into a verified content-addressed ZIP with manifest/checksums (`web_artifacts.py:133`). |

Character creation's request token is a durable ownership boundary, not a
client correlation hint. Before its first paid dispatch the server stores a
project-level pending reservation and a private sidecar containing the staged
inputs and fingerprint. `GET .../characters/pending-creation` returns the safe
status. Retry `paid_work_pending` or `artifact_version_pending` only with the
same token and unchanged inputs. A manual `DELETE` of that status requires the
exact token plus `confirmation=reconciled_no_resumable_paid_work`; use it only
after provider/billing reconciliation proves no recoverable paid task remains.

> **Divergence to know (decompose path):** The on-demand `POST .../scenes/<sid>/decompose` endpoint always uses the single-model `decompose_scene` (`web_server.py:2658`). The *competitive* GPT-4o-vs-Claude ensemble path (`competitive_decompose_scene`) only runs inside the automated pipeline when `competitive_generation=True` (`cinema_pipeline.py:1026`). If you want the higher-quality ensemble decomposition, let the pipeline do it — don't pre-decompose via the UI button.

#### The five gates and how to clear each

```mermaid
flowchart TD
    Start([POST /generate]) --> Style[STYLE 2%]
    Style --> Decomp[SCENE_DECOMPOSE]
    Decomp --> G1{{PLAN_REVIEW 25%}}
    G1 -->|approve shot plans| KF[KEYFRAME_RENDER 50%]
    KF --> G2{{KEYFRAME_REVIEW 55%}}
    G2 -->|approve keyframes| Perf[PERFORMANCE_CAPTURE 62%]
    Perf --> G3{{PERFORMANCE_REVIEW 65%}}
    G3 -->|approve performances<br/>auto-skipped if all SKIP| Motion[MOTION_RENDER 80%]
    Motion --> G4{{REVIEW 82%}}
    G4 -->|approve final takes| Asm[ASSEMBLY]
    Asm --> G5{{SCREENING 95%}}
    G5 -->|screening/approve| Done([COMPLETE 100%<br/>final_cinema.mp4])
    G1 -.auto-approve clears.-> KF
    G2 -.auto-approve clears.-> Perf
    G4 -.auto-approve clears.-> Asm
```

| Gate | What you approve | Approve endpoint | Predicate to satisfy (`controller.py`) |
|---|---|---|---|
| **PLAN_REVIEW** | Each shot's plan | `POST .../shots/<sid>/plan/approve` (`web_server.py:3122`) | all shots `plan_status=="approved"` (`cinema/review/controller.py:224`) |
| **KEYFRAME_REVIEW** | The chosen keyframe take | `POST .../keyframes/<take_id>/approve` (`web_server.py:3172`) | all shots have `approved_keyframe_take_id` |
| **PERFORMANCE_REVIEW** | The performance take (lip/body retarget) | `POST .../performance/<take_id>/approve` (`web_server.py:3183`) | each shot has `approved_performance_take_id` **OR** `performance_engine=="SKIP"` **OR** lacks a keyframe. **Auto-skipped entirely if all shots are SKIP-routed** (`cinema_pipeline.py:1133`). |
| **REVIEW** | The final motion take | `POST .../final/<take_id>/approve` (`web_server.py:3220`) | all shots have `approved_final_take_id` |
| **SCREENING** | The whole assembled cut | `POST .../screening/approve` (`web_server.py:3854`) | `screening_approved == True`; requires `exports/final_cinema.mp4` to exist on disk or returns 409 (`web_server.py:3854`) |

**Reject / iterate while at a gate.** You are not limited to approve. You can:
- **Reject a plan:** `POST .../shots/<sid>/plan/reject` with a reason (`web_server.py:3134`).
- **Reject an auto-approval:** `POST .../shots/<sid>/reject-auto-approve` with `{gate, reason}` (`web_server.py:3334`) — pulls a shot back for human review.
- **Iterate a take with directorial intent:** `POST .../takes/<take_id>/iterate` (`web_server.py:3231`) with a `DirectorialIntent` body (prose, or a verb DSL — see §5.4). This is the single most powerful creative lever during review.
- **Edit a shot's spec:** `PUT .../shots/<sid>` (`web_server.py:3443`). Allowlisted fields only: `target_api`, `camera`, `visual_effect`, `prompt`, `scene_foley`, `negative_constraints`, `continuity_constraints`, `intent_notes` (`web_server.py:3443`–1996). Anything else in the body is silently dropped.

**Pause / resume / cancel** the running pipeline at any time: `POST .../pause` (`web_server.py:3540`), `.../resume` (`:2008`), `.../cancel` (`:1597`). Cancel signals all gate events so the worker exits its wait promptly.

#### Interactive vs. headless mode

| | Interactive (default) | Headless |
|---|---|---|
| **How invoked** | `POST /api/projects/<pid>/generate` (the web path) | `CinemaPipeline(pid, headless=True)` in Python (`cinema_pipeline.py:59`) |
| **Gate behavior** | Worker blocks at each gate, polling the predicate at 0.5 s until you approve (`cinema/review/controller.py:559`) | Each gate is checked **once**; if auto-approve can't clear it, raises `GateNotSatisfiedError` with a per-shot diagnostic (`cinema/review/controller.py:93`, `:553`) — fails fast, never hangs |
| **Lifecycle** | `ThreadedLifecycle` (event-backed) | Still `ThreadedLifecycle` — **not** `NullLifecycle`. `headless=True` only flips the gate-wait to fail-fast (`cinema/lifecycle.py:70` docstring; this corrects a common doc error) |
| **Use it for** | Hands-on creative control, shot-by-shot iteration | Unattended batch runs, CI/E2E, overnight renders |

> **Critical headless caveat.** Do **not** instantiate `NullLifecycle` for unattended runs — its `wait_for_gate` returns `True` even when the predicate is false (`cinema/lifecycle.py:89`), silently skipping all gate enforcement. The only correct unattended path is `CinemaPipeline(headless=True)`. For headless to actually complete, you must also satisfy the auto-approve gates (see the unattended recipe in §5.6).

### 5.2 The Production Image Tier (the "max" tier was retired)

The image pipeline has a single tier since WS1 Task 4. `quality_tier` in `global_settings` is still read at the top of `generate_ai_broll` (`phase_c_assembly.py:98`) but is now **informational** — the `"max"` branch it used to select was deleted, so any value renders on the production tier.

| Production image tier (the only tier) | |
|---|---|
| **Image engine — PRIORITY-0 primary** | Gemini 3.1 Flash Image ("Nano Banana 2," `gemini_image_native.GeminiImageAPI`) — multi-reference identity (character + multi-angle + secondary-char refs) in one call, WS3 default for every project unless `identity_backend='pod'` |
| **Image engine — fallback** | FLUX-Dev on RunPod ComfyUI + PuLID face-lock (`pulid.json`, 22 nodes, FLUX-native `ApplyPulidFlux`), reached when Nano Banana is keyless/errors/fails the identity gate; with a further FAL fallback chain (Kontext → FLUX-Pro → Schnell → Pollinations) |
| **Generation strategy** | Single image per shot, gated by a post-keyframe identity validation pass |
| **Identity** | Gemini multi-reference on the primary path; PuLID weight by shot type + adaptive self-calibration from rolling GhostFaceNet stats on the ComfyUI fallback |
| **Style / composition continuity** | FLUX-compatible img2img (`LoadImage → VAEEncode`, controlled denoise); no production IP-Adapter or ControlNet injection |
| **Cost / shot** | ~$0.067 (`GEMINI_IMAGE`, PRIORITY-0 primary) or ~$0.04 (`COMFYUI_PULID`, fallback) |
| **Output resolution** | 1344×768 keyframe |

> **The retired `"max"` tier.** WS1 Task 4 (commit `267af0cd`) deleted the `quality_max.py` driver and its `pulid_max.json` 56-node graph. That tier ran **N=8 adaptive best-of** (GhostFaceNet + LAION-Aesthetic composite, adaptive halt, PuLID-boost retry), added 4-channel Union ControlNet + per-character LoRA + FLUX Redux, and finished with FaceDetailer + SUPIR 4K (up to 3840×2160) — at roughly 10× the cost. It was dropped because the max graph over-cooks structurally (ADR-024: `production`/`pulid.json` is the validated survivor); `ARCHITECTURE.md` §8.3 keeps the full mechanism archaeology. Setting `quality_tier: "max"` today is a no-op that renders on the production tier.

### 5.3 The Capability-Knobs Playbook

Every knob below lives in `project["global_settings"]` unless marked as an env var or per-shot field. Set them with `PUT /api/projects/<pid>` `{"global_settings": {…}}`.

#### A. API routing strategy (per shot type)

The router classifies each shot via `classify_shot_type` (`workflow_selector.py:188`) into `portrait | medium | wide | action | landscape`, then picks a primary video API and an ordered fallback cascade from `WORKFLOW_TEMPLATES` (`workflow_selector.py:29`). Since WS2 (Google-first), **all five shot types now primary `GEMINI_OMNI`**, with `VEO_NATIVE` as the universal first fallback:

| shot_type | Primary video API | Fallback cascade |
|---|---|---|
| portrait | `GEMINI_OMNI` | VEO_NATIVE → KLING_3_0 (fal Kling v3 Pro) → RUNWAY_GEN4 → SEEDANCE |
| medium | `GEMINI_OMNI` | VEO_NATIVE → KLING_3_0 (fal Kling v3 Pro) → RUNWAY_GEN4 → SEEDANCE → LTX |
| wide | `GEMINI_OMNI` | VEO_NATIVE → LTX → KLING_3_0 → RUNWAY_GEN4 |
| action | `GEMINI_OMNI` | VEO_NATIVE → SEEDANCE → KLING_3_0 → RUNWAY_GEN4 → LTX |
| landscape | `GEMINI_OMNI` | VEO_NATIVE → LTX → KLING_3_0 |

The cascade is fault-tolerant: `generate_ai_video` (`phase_c_ffmpeg.py:208`) tries the primary, and on failure walks the fallback list (`try_next_api`, `phase_c_ffmpeg.py:1089`), skipping already-attempted engines. On total exhaustion it sleeps 30 s and retries up to `cascade_retry_limit` (default 1).

**Levers:**
- **Pin an engine per shot:** set `shot.target_api` to any `API_REGISTRY` key via `PUT .../shots/<sid>`. `"AUTO"` (default) uses smart routing; an explicit value disables fallbacks (`video_fallbacks=None`).
- **Disable engines globally:** `api_engines` — e.g. `{"api_engines": {"VEO_NATIVE": {"enabled": false}}}` drops that engine from the cascade (`phase_c_ffmpeg.py:158`).
- **Raise retry resilience:** `cascade_retry_limit` (int ≥ 0) for flaky API environments (`phase_c_ffmpeg.py:183`).
- **Storyboard batch (cross-shot consistency):** `api_engines.KLING_NATIVE.storyboard_mode=true` — for non-dialogue, non-portrait scenes of **2–6 unapproved shots that all have approved keyframes**, generates one Kling clip with cross-shot `image_references`, then splits it. Dialogue-purpose shots always take the per-shot path so F1b cannot be bypassed.

#### B. Character-consistency strategy

This is where most of your perceived quality lives. The knobs, in order of impact:

| Knob | Default | Range | Effect | File |
|---|---|---|---|---|
| `identity_strictness` | 0.60 | — | Threshold for post-keyframe identity validation; the project-wide override for the per-shot threshold below | `domain/project_manager.py:444`, `cinema/shots/controller.py:1072` |
| `identity_threshold` | per shot type | — | Per-shot face-similarity threshold. **Not operator-settable** — derived from the shot type (`get_threshold_for_shot`), then overridden project-wide by `identity_strictness` | `domain/continuity_engine.py:541`, `identity/types.py` |
| `adaptive_pulid` | True | bool | Self-calibrates PuLID weight from rolling GhostFaceNet stats (`get_adaptive_pulid_weight`) | `domain/continuity_engine.py:538`, `workflow_selector.py:337` |
| `img2img_denoise` | 0.35 | 0.2–0.6 | Continuity strength: lower = more consistent with prior shot | `workflow_selector.py:285` |
| `char_lora_paths` | {} | dict | Legacy read-only LoRA registry snapshot; cannot be changed or consumed by current product paths | `global_settings` |

Per-shot identity thresholds also auto-scale by shot type (`SHOT_TYPE_THRESHOLDS`, `identity/types.py:96`): portrait standard 0.70, medium 0.65, wide 0.55, action 0.60, landscape 0.0 (faces aren't gated in landscapes).

**There is no per-character PuLID weight to set.** The PuLID face-lock weight on ComfyUI node `100` is resolved entirely by the machine: `workflow_selector`'s shot-type template supplies the base (portrait 1.0, medium 0.9, action 0.8, wide 0.65, landscape 0.0 — PuLID off), and `adaptive_pulid` then nudges it from rolling ArcFace stats. A per-character `ip_adapter_weight` field used to be stored and shown in the UI but was never read by generation; it was deleted end to end (audit 2026-07-30, slice 9d + removal follow-up) because a single per-character scalar is the wrong shape for a weight whose measured value is shot-type dependent — pinning it would flatten that curve. To bias identity lock, use `identity_strictness` and reference-image quality, not a face-lock number.

**LoRA availability is inactive by policy.** `POST .../characters/<cid>/train-lora` returns a stable 409 before it can load trainer/project dependencies, and project updates reject changes to the legacy `char_lora_paths`, `char_lora_strengths`, and `char_lora_triggers` snapshots. `GET .../characters/<cid>/lora-status` remains only to read historical sidecars; it reports `training_available=false`, `registration_available=false`, `consumer_available=false`, and `policy="dormant"`. Those fields are diagnostics, never reactivation flags. The active identity path is reference-based: upload clear multi-angle reference images for Gemini multi-reference (the default primary), with PuLID reference conditioning on the ComfyUI fallback.

**Face swap** (post-hoc identity correction): `POST .../shots/<sid>/correct` with `action="face_swap"` → `controller.apply_correction`. PixVerse uses a durable fal request ID, atomic budget reservation, and exact-task resume. FaceFusion runs CPU-only and is eligible only before PixVerse submission or after explicit terminal unbilled failure; ambiguous/billed work blocks replacement.

#### C. Native audio, dialogue & lip-sync strategy

The pipeline achieves talking characters via **Veo's look + your TTS voice overlaid** —
the default since 2026-06-03. This realizes a *consistent character voice* (Veo has no
`voice_id` so its native audio is never character-consistent). The mode is controlled by
`dialogue_voice_mode`.

**Default flow (`dialogue_voice_mode="overlay"`):**
1. A shot is dialogue if its optimizer purpose ∈ `{dialogue_close_up, talking_head_full}` → `has_dialogue=True`.
2. Router selects the first automatically admitted native-audio route in the purpose ranking (currently `GEMINI_OMNI`) but requests a silent clip. The template fallback cascade remains intact, so provider rejection still falls through and the overlay fires.
3. Per-shot TTS is rendered (`_ensure_shot_audio`); when Veo wins, clip duration clamps to ≥ speech length ({4s,6s,8s}).
4. F1b lip-sync pass overlays TTS onto the silent clip → lip-synced output with your consistent voice.
5. On overlay success, `take.metadata.dialogue_audio_in_clip=True`; assembler suppresses scene-level TTS (no double-voice).

**Native path (`dialogue_voice_mode="native"`):** requests provider-native voice and
sets `video_fallbacks=None`. The take is tagged `audio_embedded=True` only when
the winning backend supports/generated it: Vertex/ADC Veo can; Developer-API
Veo cannot and therefore receives F1b. Embedded dialogue has no measured
lip-sync score by itself, so the final gate records `UNKNOWN` and requires review.

**Lip-sync and dialogue knobs:**

| Knob | Default | Values | Effect |
|---|---|---|---|
| `dialogue_voice_mode` | `"overlay"` | `overlay`/`native` | `overlay` = silent video + TTS/F1b (consistent voice); `native` = request embedded voice, with backend verification and F1b fallback |
| `lip_sync_mode` | `"auto"` | `auto`/`overlay`/`generation`/`skip` | `overlay` = mouth-only on existing video (SyncV3→MuseTalk→LatentSync→SyncV2); `generation` = full talking-head from a still (Omnihuman v1.5→Creatify Aurora — Hedra has zero remaining consumers post-WS4) (`lip_sync.py:697`) |
| `lipsync_quality_validation` | True | bool | Enables the SyncNet quality gate (`lip_sync.py:429`) |
| `lipsync_validation_threshold` | 0.65 | 0–1 | Raise to 0.8+ to force the cascade to try more engines until sync clears |
| `dialogue_mode_enabled` | True | bool | ElevenLabs v3 Dialogue Mode for 2+ speaker scenes (best prosody continuity) (`audio/dialogue.py:419`) |
| `forced_alignment_enabled` | False | bool | Emits word-level `.alignment.json` sidecars (WhisperX) for tighter sync (`audio/dialogue.py:419`) |
| `language` | "English" | — | Korean routes TTS to Cartesia Sonic 3.5; sets a stricter 0.70 lip-sync gate (`audio/dialogue.py:208`) |

> **To maximize dialogue quality:** keep `dialogue_voice_mode="overlay"` (default) and ensure `ELEVENLABS_API_KEY` is set for high-quality TTS. Set `dialogue_mode_enabled=true` for 2+ speaker scenes. Raise `lipsync_validation_threshold` to 0.80+ to push the cascade toward better sync engines. For non-English projects, call `POST .../apply-language-defaults` (`web_server.py:1014`) for the right TTS provider + native-trained lip-sync ordering. The overlay approach was validated end-to-end at sync score 0.955 (`logs/veo_musetalk_v2studio.mp4`).

#### D. Continuity & coherence tuning

| Knob | Default | Effect | File |
|---|---|---|---|
| `coherence_check_enabled` | True | Per-shot color/lighting/composition coherence scoring vs. the prior shot (`assess_coherence`) | `coherence_analyzer.py:219` |
| `color_drift_sensitivity` | 0.3 | Lower = more aggressive color-correction recommendations | `global_settings` |
| `coherence_threshold` | 0.6 (read with fallback; **not** scaffolded by default — set it explicitly) | Overall coherence floor below which a regenerate is recommended | `cinema/shots/controller.py:1932` |
| `scene_transitions` | False | Cross-dissolve between scenes via ffmpeg `xfade` instead of hard cuts | `cinema_pipeline.py:1337` |
| `transition_duration` | 0.5 s | xfade length; clamped to 0.4× shortest clip | `cinema_pipeline.py:1375` |

Location consistency is automatic: each location carries a fixed `seed` and a verbatim `prompt_fragment` injected into every shot at that location (`domain/location_manager.py:117`, `:198`).

#### E. Cost-vs-quality tradeoffs

| Knob | Cheaper | Pricier / higher quality |
|---|---|---|
| `competitive_generation` | `false` (single LLM) | `true` (GPT-4o + Claude quorum — doubles LLM cost, better shots) |
| `quality_judge_llm` | `"auto"` (claude-sonnet-4-6) | `"claude-opus"` (best judge, → `claude-opus-4-8`) (`llm/ensemble.py:146-155`) |
| `budget_limit_usd` | set a cap | `0`/null = uncapped |
| video API | `LTX` (~$0.36/shot — 6s minimum @$0.06/s on fal ltx-2.3) | `SORA_NATIVE`/`VEO_NATIVE` ($0.40–0.80) |

**Budget governance** — three caveats that bite operators:
1. `budget_limit_usd` gates image/video generation and performance capture through `ShotController` pre-spend checks; **standalone audio API costs can still run uncapped** when audio helpers create isolated `CostTracker()` instances that log to the DB but do not update the core tracker's `spent_usd`.
2. A raw `CostTracker` initializes its in-memory accumulator at zero, but every
   production `PipelineCore` immediately rehydrates the current project's
   durable spend before new work is admitted (`cinema/core.py` →
   `CostTracker.rehydrate_spent_usd_from_video`). This applies to fresh and
   checkpoint-resumed runs; checkpoint restore repeats the normalization.
3. `EXPERIMENTS_DB_PATH` works **via the environment only**: since T7 (`4af8c05`) every `CostTracker` resolves it at construction (`db_path` arg > env var > `data/experiments.db`, `cost_tracker.py:392`), but `Settings.experiments_db_path` is never threaded into the constructor (`cinema/core.py:113`) — set the env var, not the settings field.

> **Cost-estimate note:** `API_REGISTRY` and `cost_tracker.API_COST_USD` disagree on a few engines (e.g. VEO_NATIVE: $0.40 in the registry, $0.30 in the cost table). Both are ±30% estimates — calibrate against real invoices before trusting either for budgeting.

#### F. Upscale & interpolation (post-processing)

Triggered via `POST .../shots/<sid>/correct` (`web_server.py:3713`) or auto-recommended by `POST .../shots/<sid>/diagnose` (`web_server.py:3733`):

| Action | Engine | Knob | File |
|---|---|---|---|
| `rife` | fal.ai RIFE cloud | `num_frames` (1–4; 2 = 3× FPS) | `lip_sync.py:758` |
| `upscale` | fal.ai SeedVR2 cloud | `target_resolution="2160p"` for 4K | `lip_sync.py:815` |
| (offline) | Topaz Video AI local CLI | `model="cinema"` (rhea-1, grain-preserving), `scale=4` | `prep/topaz_upscale.py:75` — local-only, no cloud fallback |

### 5.4 "To Maximize X, Do Y" Recipes

**To maximize identity lock in portraits / close-ups:**
1. Use the default `identity_backend="gemini_multiref"` so Gemini binds identity from the character's reference set; keep the ComfyUI/RunPod PuLID path available as its reference-conditioned fallback. (There is no longer a `quality_tier="max"` switch — it was retired in WS1 Task 4.)
2. Upload many clear real reference photos per character, with front, three-quarter, and profile coverage; let the multi-angle reference expansion run.
3. Confirm every in-frame character has a canonical reference and useful multi-angle references. Per-character LoRA is policy-inactive and is not part of this recipe.
4. `identity_strictness=0.70`, and keep `adaptive_pulid=true` so the PuLID fallback self-calibrates its face-lock weight from the shot-type base. (There is no operator-settable face-lock weight — see §B.)
5. Keep `img2img_denoise` low (0.2–0.3) for consecutive same-scene shots so the prior approved keyframe anchors identity.

**To get a clean, controlled background (no smear, no stray figures):**
1. Understand the cause first: the painterly "background smear" is the **base FLUX+PuLID generation reacting to an under-specified backdrop** — it is authored at generation time, not by any finishing pass. Fix it at the prompt. (This was validated on-pod 2026-06-09 against the then-max-tier SUPIR/hires-fix passes, which left the background unchanged; those passes were retired with the max tier, but the root cause — and the fix — are unchanged for the production tier.)
2. Put an **explicit backdrop in the positive prompt** (the shot/scene prompt), e.g. `"plain neutral grey seamless studio backdrop"` or `"softly-lit plain interior wall"`. Leaving the background unspecified lets FLUX hallucinate smeary depth and stray figures.
3. **The production keyframe is FLUX with `BasicGuider` (`pulid.json` node 22) — it has NO negative-prompt channel** (the only text node is the positive `CLIPTextEncode` node 122; `generate_ai_broll`'s `negative_prompt` arg is accepted but unwired). So express exclusions **positively** in the prompt: `"solo, alone, one person only, plain empty backdrop, no other people in frame"`. A negative prompt is a no-op on the FLUX keyframe.
4. For the recurring **neck/collarbone elongation** artifact, likewise use **positive** anatomy guidance (`"natural proportional neck and shoulders, well-defined collarbone"`) — not a negative term. (The shot's `negative_constraints` field still threads to video-gen, but the FLUX keyframe's `BasicGuider` ignores it.)
5. Keep the photoreal suffix consistent across every shot via `style_rules.photorealism_rules` (`llm/style_director.py:143`) → `style_rules_to_prompt_suffix` (`:233`, applied at `cinema/shots/controller.py:497`) so the background treatment doesn't drift shot-to-shot.
6. **On-pod confirmation (2026-06-09):** explicit clean backdrop + positive exclusion phrasing yielded a clean background with identity intact (arc 0.829). The base FLUX+PuLID generation authors the background — the (positive) prompt does, not any finishing pass.

**To maximize motion realism in action shots:**
1. Let `classify_shot_type` route to `action` → primary `GEMINI_OMNI` (Google-first, WS2); the automatic fallback list includes `SEEDANCE` (multi-reference, best for multi-character action) followed by Kling 3.0, Runway Gen-4, and LTX. Deprecated Sora is available only as an explicit pre-sunset compatibility pin.
2. Don't pin `target_api` unless you must; keep the fallback cascade alive.
3. After generation, run `POST .../shots/<sid>/diagnose` — `assess_motion_quality` (optical flow, `phase_c_ffmpeg.py:3073`) recommends `interpolate` (RIFE) or `regenerate`.
4. For slow-mo smoothness, `correct` with `rife`, `num_frames=4` (5× FPS).

**To maximize scene-to-scene coherence:**
1. Reuse the same location (fixed seed + prompt fragment) across consecutive shots.
2. `coherence_check_enabled=true`, lower `color_drift_sensitivity` to ~0.2, set `coherence_threshold=0.65` explicitly.
3. Enable `api_engines.KLING_NATIVE.storyboard_mode=true` only for 2–6-shot **non-dialogue** scenes; dialogue is intentionally per-shot so sync evidence cannot be bypassed.
4. `scene_transitions=true` with `transition_duration≈0.5` for cinematic dissolves.
5. Hand-author `style_rules` (or generate once and keep) so every shot shares the same color-grade/lighting/photorealism suffix (`style_rules_to_prompt_suffix`, `llm/style_director.py:233`).

**To maximize dialogue + lip-sync fidelity:**
1. For provider-native Veo audio, set `GOOGLE_CLOUD_PROJECT` and working ADC; a key-only Developer-API Veo run is treated as silent and receives F1b.
2. `dialogue_mode_enabled=true`, `forced_alignment_enabled=true`.
3. `lipsync_quality_validation=true`, `lipsync_validation_threshold=0.8` (forces the cascade to keep trying engines until sync clears).
4. For non-English, `POST .../apply-language-defaults` with `overwrite_existing=true`.

**To minimize cost:**
1. `quality_tier="production"`, `competitive_generation=false`, `quality_judge_llm="auto"`.
2. Pin cheap engines: `shot.target_api="LTX"` for non-dialogue B-roll.
3. Set a real `budget_limit_usd` (remembering it caps image/video plus performance capture; standalone audio helper spend remains the caveat, and core construction rehydrates prior project spend before fresh or resumed work).
4. `lipsync_quality_validation=false` to skip extra cascade attempts where sync quality isn't critical.

**To run fully unattended / headless** (no human ever touches a gate):
1. Drive via `CinemaPipeline(pid, headless=True)` — never `NullLifecycle`.
2. Pre-tune auto-approve in `global_settings.auto_approve` (defaults in §5.5). The **most common footgun**: `final_require_human_if_upstream_auto` defaults to `True` (`cinema/auto_approve.py:99`), which forces a human at REVIEW if any earlier gate auto-approved. Set it to `false` for true unattended completion.
3. `PERFORMANCE_REVIEW` auto-approve is off by default — set env `CINEMA_AUTO_APPROVE_MOTION=1` to enable it (`cinema/auto_approve.py:620`), or ensure all shots route to SKIP so the gate is auto-bypassed.
4. To skip the SCREENING gate entirely, env `CINEMA_SCREENING_STAGE=0` (`cinema/screening.py:147`).
5. Calibrate thresholds gradually (track `auto_approve_audit` veto rates) before loosening `image_min_composite`/`final_min_lipsync`.

### 5.5 Auto-Approve Configuration (the unattended brain)

Set under `global_settings.auto_approve` (deserialized by `AutoApproveConfig.from_project`, `cinema/auto_approve.py:71`). Each gate runs a veto-rule pass before blocking; a shot that passes is auto-approved and audited.

| Field | Default | Effect |
|---|---|---|
| `enabled` | `true` | Master switch; `false` forces all gates manual |
| `image_min_composite` | `0.60` | Production identity/composite floor for keyframe auto-approve |
| `image_min_composite_fallback` | `0.78` | Explicit bar when a fallback engine was used |
| `image_max_spent_multiplier` | `1.5` | Veto if shot cost > 1.5× per-shot budget |
| `motion_min_identity` | `0.85` | Identity floor at motion gate (needs `CINEMA_AUTO_APPROVE_MOTION=1`) |
| `motion_min_motion_score` | `0.7` | Motion-fidelity floor |
| `final_min_lipsync` | `0.8` | Lip-sync floor for final-take auto-approve |
| `final_require_human_if_upstream_auto` | `true` | Safety net — forces a human at REVIEW if any earlier gate auto-approved. **Set `false` for fully unattended runs.** |

All verified at `cinema/auto_approve.py:80`–99. Write them with `PUT /api/projects/<pid>` `{"global_settings": {"auto_approve": {…}}}` (`web_server.py:1388`).

> **The headless plan-gate fix you inherit (cycle-17):** PLAN_REVIEW auto-approve reads `shot["director_review"]`, which is written by `record_director_review_on_shots` *immediately after* the ChiefDirector validates each scene (`cinema_pipeline.py:1064`, `cinema/auto_approve.py:235`). A valid `MODIFIED` verdict is normalized to `APPROVED` so a director-corrected scene no longer dead-ends a headless run; missing/unavailable/malformed review becomes `REVIEW_REQUIRED` and vetoes. If you build your own runner that loads shots without going through decompose, you must call `record_director_review_on_shots` yourself or PLAN_REVIEW will veto forever.

### 5.6 Behavior-Changing Environment Variables

These are the *only* env vars that alter pipeline behavior (everything else in `config/settings.py` is API keys / paths). Set before server start.

| Env var | Default | Effect | Verify |
|---|---|---|---|
| `CINEMA_SCREENING_STAGE` | ON | `0`/`false`/`no` skips the SCREENING gate + its three endpoints | `cinema/screening.py:147` |
| `CINEMA_AUTO_APPROVE_MOTION` | OFF | `1`/`true`/`yes` enables PERFORMANCE_REVIEW auto-approve | `cinema/auto_approve.py:620` |
| `CINEMA_DIRECTORIAL_ITERATION` | ON | `0`/`false`/`no` disables the iterate endpoint | `cinema/shots/controller.py:112` |
| `CINEMA_STRICT_SCHEMA` | OFF | `1`/`true`/`yes` makes project-load validation raise instead of warn | `domain/project_manager.py:641` |
| `CINEMA_LOG_LEVEL` | INFO | `DEBUG` for verbose pipeline tracing (JSON-line logs) | `cinema/logging_config.py:104` |
| `PIPELINE_JOB_DB_PATH` | `data/pipeline_jobs.db` | Durable filesystem-backed SQLite/WAL full-run queue; in-memory/URI forms fail startup | `pipeline_jobs.py:39` |
| `PIPELINE_QUEUE_CONCURRENCY` | `1` | Fixed global queue worker count, validated 1..8 | `pipeline_jobs.py:62` |
| `CINEMA_TRACE_DB_PATH` | `data/telemetry.db` | Searchable local structured trace index used by the Run UI | `cinema/trace_store.py:126` |
| `CINEMA_TRACE_RETENTION_DAYS` | `30` | Trace age retention, 1..365 days | `cinema/trace_store.py:195` |
| `CINEMA_TRACE_MAX_EVENTS` | `50000` | Global trace row cap, 1,000..1,000,000 | `cinema/trace_store.py:195` |
| `WEB_BIND_HOST` | `127.0.0.1` | Loopback only; non-loopback binds are rejected until remote authentication exists | `config/settings.py:96` |
| `WEB_CORS_ORIGINS` | localhost:8080,5173 | Comma-separated explicit origins; `*` is rejected | `config/settings.py:84` |

> **Flag-parser inconsistency to know:** `CINEMA_STRICT_SCHEMA` uses an exact tuple match `in ("1","true","TRUE","yes")` and does *not* accept Python's `"True"` capitalization, whereas `CINEMA_AUTO_APPROVE_MOTION` is case-insensitive. When in doubt, use lowercase `1`/`true`/`yes`.

### 5.7 Global Prompt Control (the master lever)

One file shapes **every** LLM call in the pipeline: `config/prompts/pipeline_context.md`, loaded as `PIPELINE_CONTEXT` (`pipeline_context.py:15`) and injected into the system prompts of ChiefDirector, SceneDecomposer, DialogueWriter, and StyleDirector. Editing it changes API-routing guidance, identity rules, and prompt structure **across the whole pipeline without touching code**. This is the highest-leverage, lowest-effort customization available — but it is also a known source of drift (e.g., its lip-sync routing guidance currently disagrees with the hard-coded `PURPOSE_API_RANKING`; `domain/scene_decomposer.py:183`), so verify any change against the actual router behavior before trusting it.

---

## 6. Interconnection & Data Flow

This section is the "how it all wires together" narrative. Sections 2–5 describe each subsystem in isolation; here we trace the **state object** that every subsystem reads and writes, the **hand-offs** between stages, the **gate/checkpoint/resume control system** that interleaves with generation, the **API fallback cascade**, the **"LLM everywhere" layer**, the **headless-vs-interactive** control split, and the **concurrency/locking** model that makes a single Flask process safe to drive multiple projects.

A naming note that no longer applies: there used to be two unrelated classes named `CinemaPipeline`. The generic list-of-phases driver was deleted 2026-08-01 (ADR-081), leaving `cinema_pipeline.CinemaPipeline` as the only one.

---

### 6.1 The state model: Project → Scene → Shot → Take

Almost everything in this pipeline is a plain Python `dict` describing one **Project**, persisted as JSON at `domain/projects/<pid>/project.json`. Pydantic v2 models (`domain/models.py`) exist, but they are used **only as a warn-only validation net at load/save boundaries** — the live data that flows through every stage is the raw dict, and many runtime fields exist via `extra="allow"` and never appear in the typed model (`domain/models.py:82` for `Shot`; §7.6 enumerates the missing fields). The canonical home for all factory/CRUD/persistence logic is `domain/project_manager.py` (1412 LOC); the repo-root `project_manager.py` is a **9-line re-export shim** (`project_manager.py:9`) preserved for legacy imports. (This shim pattern repeats across `scene_decomposer.py`, `dialogue_writer.py`, `character_manager.py`, `location_manager.py`, `continuity_engine.py` — top-level is always the shim, `domain/` is always canonical; import from `domain.*` in new code.)

The nesting is four levels deep, and the data that carries between stages lives in **specific fields at each level**:

```mermaid
graph TD
    P["<b>Project</b> dict<br/>id · name · global_settings<br/>characters[] · locations[] · objects[]<br/>screening_approved · needs_reassembly[]"]
    P --> SC["<b>Scene</b> dict<br/>id · order · location_id<br/>characters_present[] · action · mood<br/>duration_seconds · shots[]"]
    SC --> SH["<b>Shot</b> dict<br/>id · prompt · camera · visual_effect<br/>target_api · characters_in_frame[]<br/>plan_status · director_review<br/>performance_engine · driving_video_path"]
    SH --> KT["keyframe_takes[]"]
    SH --> PT["performance_takes[]"]
    SH --> MT["motion_takes[]"]
    SH --> PP["postprocess_variants[]"]
    KT --> TR["<b>TakeRecord</b> dict<br/>id · kind · path · source_take_id<br/>status · created_at<br/>metadata{composite, identity_score,<br/>motion_score, lipsync_score,<br/>audio_embedded} · cascade_metadata"]
    MT --> TR
    PT --> TR
    PP --> TR
    SH -.approval pointers.-> AP["approved_keyframe_take_id<br/>approved_performance_take_id<br/>approved_motion_take_id<br/>approved_final_take_id"]
```

**The fields that carry data between stages** — the load-bearing "wiring" of the whole system — are:

| Field (on shot, unless noted) | Written by | Read by | What it carries forward |
|---|---|---|---|
| `global_settings` (project-level) | Web UI strict, revision-bound `PATCH /api/projects/<pid>` (compat whole-object `PUT` remains guarded) | every subsystem via `get_project_setting(ctx, key, default)` | all user-tunable knobs (thresholds, language, `api_engines`, …); UI writes are serialized and each success advances the revision used by the next write |
| `director_review` | `record_director_review_on_shots` (`cinema/auto_approve.py:239`), called at `cinema_pipeline.py:1064` | PLAN_REVIEW auto-approve `_rules_for_plan` (`auto_approve.py:214`) | ChiefDirector verdict; valid **MODIFIED is normalized to APPROVED**, while missing/unavailable validation is REVIEW_REQUIRED and cannot clear the gate |
| `plan_status` | `approve_shot_plan` / auto-approve | PLAN_REVIEW gate predicate (`controller.py:695`) | `"approved"` unlocks keyframe generation |
| `target_api` | scene decomposer / operator (`PUT .../shots/<id>`) | video cascade routing (`cinema/shots/controller.py:1310`) + image routing | which engine to try first; `"AUTO"` triggers smart routing |
| `approved_keyframe_take_id` | `approve_take(kind="keyframe")` | KeyframeRenderPhase skip-gate, performance/motion `init_image` chain | the anchor still for all downstream video |
| `performance_engine` | `route_performance_engine` (`domain/performance.py:103`) | PerformanceCapturePhase + gate bypass | `ACT_ONE`/`LIVE_PORTRAIT`/`VIGGLE`/`SKIP`; `"SKIP"` skips the shot and (if all-SKIP) the whole gate |
| `approved_performance_take_id` | `approve_take(kind="performance")` | PERFORMANCE_REVIEW predicate, motion phase driving-video | retargeted-performance clip |
| `approved_final_take_id` (+ `approved_motion_take_id`) | `approve_take(kind="final")` | REVIEW predicate, `_build_scene_packages` | the clip that goes into final assembly |
| `metadata.audio_embedded` (on take) | video cascade post-call (`cinema/shots/controller.py`) | `_build_scene_packages` / `_assemble_final` audio mix | set only for native-mode dialogue when the winning engine/backend supports embedded voice; Developer-API Veo explicitly cannot set it |
| `cascade_metadata` (on take) | `_record_video_cascade` (`phase_c_ffmpeg.py`) | audit / `audio_embedded` decision | winning engine, attempt list, and backend-specific capability evidence such as `native_audio_generated` |
| `screening_approved` (project-level) | `mark_screening_approved` (`screening.py:342`) | SCREENING gate predicate | operator sign-off on the assembled cut |
| `needs_reassembly[]` (project-level) | `mark_shot_needs_reassembly` | re-assemble endpoint | shots iterated during screening that need re-stitching |
| `final_video_path` / `exports/final_cinema.mp4` | `_assemble_final` (`cinema_pipeline.py:1675`) | export endpoint, `screening/approve` precondition | the deliverable |

The crucial architectural property: **takes are append-only history, and "approval" is a pointer.** A shot accumulates many `keyframe_takes`/`motion_takes`; approving one just writes its id into the corresponding `approved_*_take_id` field. The take a downstream stage consumes is always resolved through the approval pointer, never by "latest". This is what makes iteration (regenerate, screen-and-redo) safe — old takes are never destroyed.

---

### 6.2 How each subsystem hands off to the next

The orchestrator's `generate()` method (`cinema_pipeline.py:1244`) is the spine. It does **not** hold media in memory and pass it along — instead, each stage **mutates the persisted project dict** (via `mutate_project`) and **re-reads a fresh snapshot** (`_refresh_project_snapshot`, `cinema_pipeline.py:463`) at the next gate boundary. The hand-off medium is the project JSON on disk, not function arguments. `_refresh_project_snapshot` is called 6+ times through `generate()`; critically it **validates before swapping** `self.project` (`cinema_pipeline.py:1244`, cycle-11 fix) so a validation failure leaves the in-memory state coherent, and it rebuilds the `ContinuityEngine`'s typed-id-keyed `characters`/`locations` dicts each time.

```mermaid
flowchart TD
    A["Operator / web_server<br/>creates + configures project"] --> B["STYLE<br/>generate_style_rules → global_settings.style_rules"]
    B --> C["BGM pre-generated<br/>_ensure_bgm"]
    C --> D["SCENE loop (per scene)"]
    D --> D1["decompose_scene /<br/>competitive_decompose_scene<br/>→ shots[]"]
    D1 --> D2["ChiefDirector.validate_shot_prompts<br/>→ APPROVED/MODIFIED/REJECTED/REVIEW_REQUIRED"]
    D2 --> D3["record_director_review_on_shots<br/>→ shot.director_review"]
    D3 --> D4["update_scene_shots (persist)<br/>+ _save_checkpoint<br/>+ _ensure_scene_audio (TTS)"]
    D4 --> G1{{"PLAN_REVIEW gate"}}
    G1 --> E["KeyframeRenderPhase<br/>generate_keyframe_take per shot<br/>→ ComfyUI+PuLID / FAL FLUX<br/>→ identity validation → keyframe_takes"]
    E --> G2{{"KEYFRAME_REVIEW gate"}}
    G2 --> F["PerformanceCapturePhase<br/>ACT_ONE/LIVE_PORTRAIT/VIGGLE/SKIP<br/>→ performance_takes"]
    F --> G3{{"PERFORMANCE_REVIEW gate<br/>(auto-skipped if all SKIP)"}}
    G3 --> H["MotionRenderPhase<br/>generate_motion_take per shot<br/>→ video cascade → motion_takes<br/>+ mandatory lipsync if dialogue"]
    H --> G4{{"REVIEW gate"}}
    G4 --> I["assemble_approved_takes<br/>_build_scene_packages → _assemble_final<br/>normalize→stitch→grade→tri-mix→loudnorm"]
    I --> G5{{"SCREENING gate"}}
    G5 --> J["cleanup + cost summary<br/>+ clear checkpoint → COMPLETE"]
```

The hand-off contracts, stage by stage:

1. **Decompose → Director → Plan.** `decompose_scene` (`domain/scene_decomposer.py:838`) or its competitive variant produces shot dicts from `make_shot`. `ChiefDirector.validate_shot_prompts` (`llm/chief_director.py:296`) may modify them in place. `record_director_review_on_shots` then writes `director_review` onto each shot — **this single call is what unblocks the PLAN_REVIEW auto-approve gate**; without it, `_rules_for_plan` always vetoes (the field is absent) and a headless run dead-ends. `update_scene_shots` persists.
2. **Plan → Keyframe.** Once PLAN_REVIEW clears, `KeyframeRenderPhase.run(ctx)` (`cinema/phases/keyframe_render.py:68`) iterates shots, skipping any with `approved_keyframe_take_id`, and calls `generate_keyframe_take` (delegated to `ShotController`). The keyframe is the anchor still; its identity score lands in `take.metadata.identity_score`.
3. **Keyframe → Performance.** `PerformanceCapturePhase` (`cinema/phases/performance.py:19`) skips shots that are SKIP-routed, have no approved keyframe, or already have an approved performance take. The performance take (a driving-video / retarget) becomes optional conditioning for the motion stage.
4. **Performance → Motion.** `MotionRenderPhase` turns the approved keyframe into a video clip via the cascade (§6.4). Its optional Kling Native storyboard batch is limited to non-dialogue, non-portrait scenes with 2–6 unapproved shots and approved keyframes; dialogue always follows the per-shot F1b path. Any batch failure falls through to per-shot generation.
5. **Motion → Review → Assembly.** After motion, `_rebuild_review_clips` builds the in-memory manifest the web UI reads, and the REVIEW gate waits for `approved_final_take_id` on every shot. Then `assemble_approved_takes` resolves those approved takes' paths in `_build_scene_packages` (`cinema_pipeline.py:945`) and `_assemble_final` (`cinema_pipeline.py:1675`) produces `exports/final_cinema.mp4`.

A key correctness detail in the final hand-off: **the audio source for assembly depends on verified take metadata, not the engine name alone.** `_build_scene_packages` suppresses standalone TTS only when every approved take in a scene has `metadata.audio_embedded=True`. Vertex/ADC Veo can earn that tag; Developer-API Veo cannot. If the scene is mixed, TTS is retained for non-embedded shots and `_assemble_final` binds the voice filtergraph label to the correct input index.

**Phases never fail the run.** All three phases return `PhaseResult(ok=True)` even when individual shots fail — partial failures route through the `on_failure` callback into `RunState.failed_shots` and emit a `SHOT_FAILED` SSE event, but the phase proceeds (`cinema/phases/keyframe_render.py:105`). Operators rework failed shots from the review UI. The only `ok=False` returns are missing-constructor-args and cancellation. Callers that need to know about per-shot failures must inspect `failed_shots`, not the phase result.

---

### 6.3 The review / gate / checkpoint / resume control system

Five mandatory **gates** punctuate generation: PLAN_REVIEW → KEYFRAME_REVIEW → PERFORMANCE_REVIEW → REVIEW → SCREENING. They are **not phases** — they are inline `_wait_for_gate(...)` calls in `generate()` that block the worker thread until a predicate is satisfied. The gate machinery is `ReviewController` (`cinema/review/controller.py`), and it interleaves with generation as follows: a phase runs (generating takes), then a gate blocks (waiting for approvals), then the next phase runs against the now-approved state.

Each `_wait_for_gate` call (`controller.py:560`) does three things in order:

1. Sets `RunState.current_stage` and emits a progress event.
2. **Runs an auto-approve pass** (`_run_auto_approve_pass`, `controller.py:294`) — for each not-yet-approved shot it calls `auto_approve.check_gate(...)`, which evaluates per-gate veto rules; qualifying shots are pre-approved (their approval pointer/`plan_status` is written and a `<gate>_auto_approved` flag set), and an audit entry is appended to `shot["auto_approve_audit"]` for **every** shot checked. This pass **never raises** — on error it falls through to manual review.
3. **Waits** — using one of two completely different control paths depending on mode (§6.6).

The gate predicates (`_gate_satisfied`, `controller.py:265`) are pure functions of shot state:

| Gate | Satisfied when (all shots) |
|---|---|
| PLAN_REVIEW | `plan_status == "approved"` |
| KEYFRAME_REVIEW | `approved_keyframe_take_id` set |
| PERFORMANCE_REVIEW | `performance_engine == "SKIP"` **OR** no approved keyframe **OR** `approved_performance_take_id` set |
| REVIEW | `approved_final_take_id` set |
| SCREENING | `is_screening_approved(project)` is True |

```mermaid
stateDiagram-v2
    [*] --> RunAutoApprove: _wait_for_gate(GATE)
    RunAutoApprove --> CheckMode: shots pre-approved + audited
    CheckMode --> Headless: RunState.headless == True
    CheckMode --> Interactive: RunState.headless == False

    Headless --> GateSatisfied: predicate true
    Headless --> RaiseError: predicate false → GateNotSatisfiedError(per-shot reasons)
    RaiseError --> [*]

    Interactive --> Poll: lifecycle.wait_for_gate(predicate, 0.5s)
    Poll --> Poll: predicate false (re-refresh snapshot)
    Poll --> GateSatisfied: predicate true OR signal_gate wake
    Poll --> Cancelled: lifecycle.cancel()
    Cancelled --> [*]
    GateSatisfied --> [*]: phase proceeds
```

**Auto-approve thresholds** live in `global_settings.auto_approve` (`AutoApproveConfig`, `cinema/auto_approve.py:75`). The veto rules per gate: PLAN (decision-not-APPROVED, has-violations), IMAGE (composite below threshold — dynamic 0.97 PuLID / 0.78 fallback, cascade-fallback, over-budget), MOTION (identity/motion-score floors — **opt-in via `CINEMA_AUTO_APPROVE_MOTION=1`**), FINAL (lipsync floor, and the `final_require_human_if_upstream_auto` safety net). That last default is the most common footgun for unattended runs: if any earlier gate auto-approved a shot, the REVIEW gate forces a human unless you set `final_require_human_if_upstream_auto=false`.

**Checkpointing and resume.** `CheckpointStore` (`cinema/checkpoint.py`) atomically writes `temp/pipeline_state.json` (via `tempfile.mkstemp` + `os.replace`) after **each scene** and after each audio step (`_save_checkpoint`, `checkpoint.py:99`). It serializes the `RunState` fields wholesale: `current_stage/scene_id/shot_id`, `completed_scene_indices`, `scene_clips`, `scene_audio`, `shot_audio`, `scene_foley`, `foley_audio_paths`, `shot_results`, `failed_shots`. On `generate(resume=True)`, `_restore_from_checkpoint` (`checkpoint.py:167`) rejects a project-id mismatch, rehydrates those fields, and marks any referenced file that's gone as `"lost"`. One subtlety: `review_clips` is **not** persisted in the checkpoint — it is rebuilt in-memory by a separate `_rebuild_review_clips` call on resume (`cinema_pipeline.py:328`).

**Screening (the post-assembly gate).** After `_assemble_final` produces the mp4, if screening is enabled (`CINEMA_SCREENING_STAGE` default ON, overridable per-project) the pipeline parks at the SCREENING gate at 95%. The operator hits `POST .../assemble/screen` to get a timeline manifest, may iterate individual shots (each iterate calls `mark_shot_needs_reassembly`), may call `POST .../assemble/re-assemble` to re-stitch only the dirty shots, and finally `POST .../screening/approve` → `mark_screening_approved` → the gate's predicate flips True. To wake the blocking waiter promptly, the approve endpoint also calls `pipeline.lifecycle.signal_gate(SCREENING_STAGE_NAME)` (`web_server.py:3854`); if the live pipeline object isn't reachable, the 0.5s poll is the fallback (verified `web_server.py:3854-2362`).

---

### 6.4 The API fallback cascade (in detail)

Video generation is the most fault-tolerant subsystem because vendor APIs fail, rate-limit, and reject inputs constantly. The single entry point is `generate_ai_video` (`phase_c_ffmpeg.py:208`); inside it, the closure `try_next_api` (`phase_c_ffmpeg.py:1089`) implements an ordered, fault-tolerant cascade.

**Resolution → attempt → fallback** flows like this:

1. **Routing (caller side, `ShotController`).** For `target_api == "AUTO"`, the controller checks the optimizer's suggestion through the active-lifecycle fence, then falls to the shot-type template's primary + fallback list (`WORKFLOW_TEMPLATES[shot_type]`, e.g. portrait → `GEMINI_OMNI` with fallbacks `VEO_NATIVE, KLING_3_0, RUNWAY_GEN4, SEEDANCE`). For an explicit `target_api`, it preserves that compatibility pin and sets `video_fallbacks = None`.
2. **Dialogue override (F1a).** If `has_dialogue`, the controller scans `PURPOSE_API_RANKING[purpose]` for the first engine with `native_audio=True AND modality=="video" AND status=="live"` (today: `GEMINI_OMNI`, which outranks `VEO_NATIVE`) and overrides `target_api` to it. Fallback handling depends on `dialogue_voice_mode` (default `"overlay"`): overlay mode **keeps the template `video_fallbacks`** so a Gemini/Veo RAI-block cascades to a silent engine and the F1b TTS overlay still fires; native mode **sets `video_fallbacks = None`** so a cross-engine fallback can't silently route to a non-native-audio engine and drop the embedded voice (`cinema/shots/controller.py:133-180` helper; call site + rationale `:1348-1370`).
3. **Engine-disabled short-circuit.** Before attempting the targeted engine, `generate_ai_video` reads `api_engines` from `ctx`; if the operator set `{ENGINE: {enabled: false}}`, it delegates straight to `try_next_api` (respects "if I disabled X, don't use X even when explicitly targeted").
4. **Attempt the engine.** Each current engine has its own handler branch (native/SDK: Kling, Veo, Sora compatibility, LTX, Gemini Omni, and Runway Gen-4; FAL-proxy: VEO, KLING_3_0, FAL_SVD, and Seedance). Retired FAL `SORA_2` and legacy Runway have no handler. On success, `_record_video_cascade(api_name)` writes `{engine, attempts}` into `_cascade_out["cascade_metadata"]` and returns the path.
5. **Fallback on an eligible failure.** A failure proven to be pre-submission, or an explicit terminal/RAI provider result, enters `try_next_api`. It walks the fallback list (or the default order), **filters out already-attempted engines and `api_engines`-disabled ones**, and recurses into `generate_ai_video` with the next engine. An acknowledged/ambiguous paid attempt instead stops the chain: FAL engines such as `FAL_SVD` resume their exact request ID, native Kling resumes an acknowledged task ID, and native Sora becomes `accepted_unknown` because its synchronous boundary exposes no durable recovery ID.
6. **Exhaustion + retry.** When the list is exhausted, it sleeps 30s and restarts the whole cascade from the first engine, up to `MAX_CASCADE_RETRIES` (default 1, overridable via `cascade_retry_limit`). After that, it returns `None` (total failure).

```mermaid
flowchart TD
    R["Resolve target_api<br/>(AUTO→template, or explicit)"] --> DLG{has_dialogue?}
    DLG -- yes --> OV["Override → first native_audio<br/>video engine (GEMINI_OMNI)<br/>video_fallbacks = None (native mode only)"]
    DLG -- no --> DIS
    OV --> DIS{api_engines<br/>disabled this engine?}
    DIS -- yes --> TNA
    DIS -- no --> ATT["Attempt engine handler"]
    ATT -- success --> REC["_record_video_cascade<br/>write cascade_metadata · return path"]
    ATT -- "pre-submit or explicit<br/>terminal / RAI failure" --> TNA["try_next_api()"]
    ATT -- "accepted or ambiguous<br/>paid provider job" --> DEF["persist deferred_motion_job<br/>stop · surface recovery in UI"]
    TNA --> LST["fallback list<br/>(custom or default order)<br/>filter attempted + disabled"]
    LST --> NEXT{next engine<br/>available?}
    NEXT -- yes --> ATT
    NEXT -- no --> RETRY{retries <<br/>MAX_CASCADE_RETRIES?}
    RETRY -- yes --> SLEEP["sleep 30s · reset attempted<br/>restart from first engine"]
    SLEEP --> ATT
    RETRY -- no --> NONE["return None<br/>(total cascade failure)"]
    REC --> POST["Controller post-call:<br/>if native-mode dialogue + backend<br/>verified embedded audio → tag it;<br/>else mandatory lipsync pass (F1b)"]
    DEF --> MAN["FAL/LTX/Kling with saved ID:<br/>resume exact job<br/>Sora/no-ID ambiguity:<br/>accepted_unknown + reconcile"]
```

The **default cascade order** (when no custom `video_fallbacks`) is verified as: `VEO_NATIVE, SEEDANCE, KLING_3_0, RUNWAY_GEN4, LTX, VEO` (`phase_c_ffmpeg.py:94`). `GEMINI_OMNI` is deliberately outside this blind order; deprecated Sora/Kling Native are explicit-only, while retired legacy Runway and `SORA_2` have no payload branch. Explicit-only does not mean unguarded: native Kling can resume its acknowledged exact task ID, while Sora ambiguity is fenced as `accepted_unknown`. `FAL_SVD` is also explicit-only and resumes its exact FAL request ID. Note that `VEO_NATIVE` (native SDK) and `VEO` (FAL proxy) are **distinct cascade members**.

Three cascade caveats engineers must know:

- **Native-audio is backend-specific, not implied by the route name.** Vertex/ADC Veo supports it; Developer-API Veo does not. After download, any dialogue take without `audio_embedded` receives mandatory F1b, which writes a measurable score/state or explicit `UNKNOWN`. A native embedded take also remains unmeasured and cannot silently auto-approve.
- **`VEO_NATIVE` has no quota-block guard.** The `_VEO_QUOTA_EXHAUSTED_UNTIL` 30-min cooldown TTL (`phase_c_ffmpeg.py:36`) is set/checked only for the **FAL-proxy `VEO`** branch. Native Veo does not gain a cooldown here: explicit terminal/pre-submit quota failure can cascade, while an ambiguous result after possible acceptance becomes recovery-required and stops.
- **Some engine params are accepted but silently dropped.** Veo's `reference_images`/`multi_angle_refs` (Bug #4 — Vertex rejects image+reference_images together) and `driving_video_path` (SDK `video=`/`image=` mutual exclusivity) are accepted for interface stability but have no effect. Sora does not accept driving-video input either; its compatibility wrapper rejects any such value before preprocessing or network access.

The same `try_next_api`-style fault tolerance recurs in the **image** path (ComfyUI+PuLID → FAL FLUX Kontext → FLUX-Pro → Schnell → Pollinations, `phase_c_assembly.py:413`), the **lipsync** path (SyncV3 → MuseTalk → LatentSync → SyncV2 for overlay; Omnihuman v1.5 → Creatify Aurora for generation, `lip_sync.py`), and the **TTS/BGM** paths. The pattern — ordered list, skip-on-failure, best-of-failed recovery, provenance written to a cascade dict — is the project's house style for any external dependency.

---

### 6.5 The "LLM everywhere" layer

LLMs are not a single stage — they are threaded through almost every decision point. The creative-LLM stack (`llm/`) sits above all image/video generation: nothing reaches a diffusion model or video API without passing through at least one of these. Every LLM that touches the pipeline ingests the shared `PIPELINE_CONTEXT` string (loaded from `config/prompts/pipeline_context.md` via `pipeline_context.py:15`) in its system prompt — so editing that one markdown file reshapes the behavior of **every** LLM in the pipeline without a code change.

```mermaid
flowchart LR
    subgraph Decompose["Scene → Shots"]
        SD["scene_decomposer<br/>GPT-4o (or GPT-4o+Claude ensemble)"]
        DW["dialogue_writer<br/>GPT-4o → dialogue lines"]
    end
    subgraph Style["Once per run"]
        STY["style_director<br/>GPT-4o (OpenAI-only)<br/>→ global_settings.style_rules"]
    end
    subgraph Plan["Pre-generation gate"]
        CD["ChiefDirector<br/>Claude Sonnet (Anthropic→OpenAI)<br/>HC1–HC8 validation → director_review"]
    end
    subgraph PerShot["Per shot, pre-image"]
        PO["prompt_optimizer<br/>LLMEnsemble decompose-task<br/>→ structured shot spec"]
    end
    subgraph Iterate["Per take, on operator iterate"]
        DIR["CinemaDirector (PERMISSIVE)<br/>Claude Sonnet → revised_prompt"]
    end
    EN["LLMEnsemble<br/>parallel multi-model + judge-pick<br/>(Anthropic/OpenAI/Gemini)"]
    SD --> EN
    PO --> EN
    STY -. style suffix .-> PO
    CD -. verdict .-> Plan
    PIPCTX["PIPELINE_CONTEXT<br/>(config/prompts/pipeline_context.md)"] -.injected into system prompts.-> SD & CD & DIR & STY
```

| Stage | Module | Model(s) | Role |
|---|---|---|---|
| Global style (once) | `llm/style_director.py:12` | **GPT-4o only** (no Anthropic path; falls to hardcoded defaults if no OpenAI key) | produces 7-key `style_rules` dict → `style_rules_to_prompt_suffix` is appended to every image prompt |
| Scene → shots | `domain/scene_decomposer.py` | GPT-4o, or GPT-4o+Claude via `LLMEnsemble` when `competitive_generation=True` | shot specs with HC1–HC5 constraints |
| Dialogue | `domain/dialogue_writer.py:12` | GPT-4o | per-character spoken lines |
| Pre-gen validation | `llm/chief_director.py:296` | Claude Sonnet 4 (Anthropic→OpenAI fallback) | enforces HC1–HC8; writes the `director_review` that gates PLAN_REVIEW |
| Per-shot prompt optimize | `llm/prompt_optimizer.py:702` | `LLMEnsemble` `decompose` roster | freeform → structured 13-field spec |
| Per-take iteration | `llm/director.py:275` | Claude Sonnet 4 | translates a `DirectorialIntent` into a `revised_prompt` (permissive — operator intent overrides HC firewalls) |
| Ensemble engine | `llm/ensemble.py:139` | parallel Anthropic/OpenAI/Gemini + judge | `competitive_generate` dispatches all models, judge picks winner |

One historical divergence is now resolved: `ChiefDirector.evaluate_generation_quality` (`llm/chief_director.py:406`) is fully implemented and **wired by T6** (`10a0eb4`) — invoked by `cinema/shots/controller.py::diagnose_clip` on the opt-in `deep=True` path. `negative_prompts.build_remediation_advisory` is similarly wired (`8d18e57`), called from both `generate_keyframe_take` and `diagnose_clip`. The remaining open divergence: `style_director` is **asymmetric** with the others (OpenAI-only), so an Anthropic-key-only deployment silently gets hardcoded default style rules. Model selection is steered by `global_settings.creative_llm` and `quality_judge_llm`, but the override is **family-checked, not provider-switching** — setting a `claude-*` model when only OpenAI is configured silently uses the OpenAI default.

---

### 6.6 Headless vs. interactive control flow

The same `generate()` code runs in two modes; the divergence is entirely localized to **how gates wait**, controlled by one boolean: `RunState.headless`, set once at `CinemaPipeline(headless=...)` construction.

```mermaid
flowchart TD
    GEN["generate() reaches _wait_for_gate(GATE)"] --> AA["_run_auto_approve_pass(GATE)<br/>(identical in both modes)"]
    AA --> MODE{RunState.headless?}
    MODE -- "True (script/E2E)" --> H["Refresh snapshot once<br/>predicate satisfied?"]
    H -- yes --> HOK["return True → phase proceeds"]
    H -- no --> HERR["raise GateNotSatisfiedError<br/>(per-shot block reasons)<br/>FAIL FAST — no operator exists"]
    MODE -- "False (web)" --> W["lifecycle.wait_for_gate(predicate)<br/>poll every 0.5s, re-refresh snapshot"]
    W -- "operator approves via HTTP" --> WOK["predicate flips True<br/>(or signal_gate wake) → proceed"]
    W -- "lifecycle.cancel()" --> WC["return False → run aborts"]
```

**Interactive (web) mode** (`headless=False`): the worker thread blocks in `ThreadedLifecycle.wait_for_gate` (`cinema/lifecycle.py:182`), which polls the predicate every 0.5s and re-refreshes the project snapshot each poll, so operator approvals made via HTTP endpoints are picked up automatically — **no explicit "Resume" click is needed** after approving. An explicit `signal_gate` call (e.g. from the screening-approve endpoint) wakes the waiter immediately rather than waiting for the next poll tick.

**Headless mode** (`headless=True`): there is no operator and no web UI, so polling forever would hang. Instead, after the auto-approve pass, the gate checks the predicate **once** and, if unsatisfied, **raises `GateNotSatisfiedError`** (`controller.py:93`) with per-shot block reasons (`_gate_block_details`). This is the cycle-17 fix for the headless plan-review stall.

A critical, easily-mis-stated fact: **headless mode does NOT use `NullLifecycle`.** `NullLifecycle` (`cinema/lifecycle.py:70`) was the now-deleted CLI's lifecycle; its `wait_for_gate` returns `True` regardless of the predicate, which would **silently skip all gate enforcement**. The correct non-interactive path is `CinemaPipeline(headless=True)`, which still uses `ThreadedLifecycle` but flips the fail-fast branch. Any doc claiming "headless uses NullLifecycle" is wrong. (Note also that `MEMORY.md` records `run_tier_c.py` was never a real unattended harness — it expected web approval; the supported unattended entry is `CinemaPipeline(headless=True)`.)

---

### 6.7 Concurrency, locking, and the SSE queues

A shared SQLite queue now controls full-project concurrency across server
processes; the in-memory registries still protect one process's live objects.
Six mechanisms compose rather than replacing one another.

**1. Durable queue and fixed global concurrency.** `PipelineJobStore`
(`pipeline_jobs.py:123`) uses WAL and short `BEGIN IMMEDIATE` transactions.
`enqueue` (`pipeline_jobs.py:346`) returns the existing active row for the
project or creates one stable 32-hex job ID. `claim`
(`pipeline_jobs.py:384`) selects the oldest queued row only when the durable
global `running` count is below `PIPELINE_QUEUE_CONCURRENCY`; the dispatcher
owns a fixed worker pool (`pipeline_jobs.py:769`) instead of spawning a thread
per HTTP request.

Each running row has a lease/heartbeat and a worker ID tied to a process-held
POSIX `flock`. Expiry only makes a row eligible for inspection: automatic
requeue happens when that exact owner fence is provably stopped, at which point
`resume_required=1` sends the job through the project checkpoint
(`pipeline_jobs.py:267`). A live fence waits. An unverifiable fence blocks and
is the only state in which the UI can offer the exact, acknowledgement-gated
`POST .../queue/abandon` action (`pipeline_jobs.py:573`,
`web_server.py:3584`).

**2. In-process pipeline registry and PENDING sentinel.** Once a durable job is
claimed, `_execute_pipeline_job_traced` reserves `_running_pipelines[pid]`
with `_PIPELINE_PENDING`, constructs the heavy `CinemaPipeline` outside
`_pipelines_lock`, swaps in the real object, and calls
`pipeline.generate(resume=job.effective_resume)` (`web_server.py:3213`).
`_get_running_pipeline` (`web_server.py:682`) is the safe reader and treats the
sentinel as not-yet-callable. `_running_cores` remains a per-process cache
guarded by `_cores_lock` (`web_server.py:468-469`).

**3. Cross-process web operation lock.** Decorated project mutation,
direct-stage, and generation-admission routes hold the sibling
`domain/projects/.<pid>.operation.lock` for the complete HTTP operation
(`_project_lock_guard`, `web_server.py`). The registry reuses one `FileLock`
object per canonical path for same-thread re-entry, while independent threads
and server processes contend on the filesystem lock. A timeout returns a
retryable `project_locked` 409.

**4. Project mutation lock.** Durable project JSON writes still funnel through
`mutate_project(pid, mutator)` (`domain/project_manager.py:854`): a
per-project file lock, fresh read, normalization, in-place mutation, and atomic
replace. Queue ownership does not authorize bypassing this write primitive.
External callers already holding `project_lock()` must use the unlocked save
helper; reacquiring the public lock deadlocks. Shot IDs are not globally
unique, so every endpoint and durable record remains project-scoped.

**5. Busy fence and gate bypass.** Direct paid/stage/admin requests check both
the active queue row and the local registries (`_reject_if_project_busy`,
`web_server.py:766`). Gate-acting endpoints remain usable while the pipeline is
parked at PLAN_REVIEW, KEYFRAME_REVIEW, PERFORMANCE_REVIEW, REVIEW, or
SCREENING via `_reject_if_project_busy_outside_gate`
(`web_server.py:805`). Reassembly keeps its separate guard because it runs
while SCREENING still owns the full-run slot.

**6. SSE is transport, never job truth.** `_progress_queues` actually stores a
`_ProjectEventBus`, not a `queue.Queue` (`web_server.py:386`). Every subscriber
gets a bounded private inbox; the bus fans out and retains a bounded replay
window (`_ProjectEventBus`, `web_server.py:212`). `Last-Event-ID` or the query
fallback replays buffered events and emits an explicit GAP when a range aged
out. A queued job gets a bus immediately, so clients can subscribe before a
worker claim (`web_server.py:3362`). Disconnecting from SSE never cancels or
completes the durable job. After process restart, `/stream` checks the active
SQLite row, hydrates a fresh bus, and wakes the dispatcher; that new bus cannot
replay the prior process's event buffer, so `pipeline-state` supplies current
queue/stage truth before new live events arrive.

```mermaid
flowchart LR
    POST["POST /generate"] --> OPLOCK["project operation lock<br/>cross-process admission fence"]
    OPLOCK --> ENQ["SQLite enqueue<br/>stable job ID / 202"]
    ENQ --> WAIT["queued<br/>durable position"]
    WAIT -->|"global slot available"| CLAIM["atomic claim<br/>lease + process fence"]
    CLAIM --> SENT["local _PIPELINE_PENDING"]
    SENT --> RUN["CinemaPipeline.generate<br/>fresh or checkpoint resume"]
    RUN -->|"heartbeat"| CLAIM
    RUN -->|"project writes"| JSON[("project.json + checkpoint")]
    RUN -->|"progress"| BUS["_ProjectEventBus<br/>fan-out + replay"]
    BUS --> UI["Run UI / SSE subscribers"]
    RUN --> DONE["durable terminal row"]
    CLAIM -->|"expired + owner stopped"| WAIT
    CLAIM -->|"expired + owner unverifiable"| BLOCK["operator reconciliation<br/>optional exact abandonment"]
```

---

### 6.8 The whole loop, end to end

Putting the pieces together, a single web-driven run is: **enqueue → claim → configure → STYLE → BGM → (per scene: decompose → ChiefDirector → record review → persist → TTS) → PLAN_REVIEW gate → keyframes → KEYFRAME_REVIEW gate → performance → PERFORMANCE_REVIEW gate (auto-skipped if all SKIP) → motion (+cascade, +lipsync) → REVIEW gate → assemble (normalize → stitch → grade → tri-mix → loudnorm) → SCREENING gate → cleanup + cost summary → COMPLETE.** Every arrow that crosses a stage boundary is a `mutate_project` write followed by a `_refresh_project_snapshot` read; every gate interleaves an auto-approve pass with either a fail-fast (headless) or a poll-until-approved (web) wait. Paid-media calls enter a provider adapter that either resumes a durable job ID or fail-closes an ambiguous/nonresumable outcome; no cascade may treat `accepted_unknown` as an ordinary failure and spend on a replacement. Accepted take/auxiliary/final outputs, generated character assets, and locally rejected paid Gemini/motion/lip-sync bytes are indexed into immutable artifact history. Acquired web references and LLM-authored project JSON remain ordinary revision inputs/state. The project dict is the stage hand-off bus, the durable queue is full-run truth, the paid-attempt ledger is provider-work truth, and `RunState` is per-run scratch space serialized by the checkpoint.

---

## 7. Reference Appendix

This appendix is the quick-lookup layer of the manual: the files an engineer opens first, the functions they reach for, every tunable knob, the vocabulary, the failure-mode playbook, and — importantly — a catalog of the documentation drift discovered while building this manual so the next reader is not misled by stale maps. Every concrete claim carries a `file:line` citation traceable to the source as of the 2026-06-09 re-sweep. Where divergences exist between the plan and the source, they are surfaced rather than smoothed over (see §7.6).

### 7.1 Key Files Index

The pipeline's single entry point is `web_server.py` → `cinema_pipeline.py`; the old CLI `main.py` was deleted and no longer exists at the repo root (verified: `ls main.py` → "No such file or directory"). LOC values below were re-verified via `wc -l` in the 2026-06-09 re-sweep.

#### Orchestration & lifecycle

| Path | LOC | Role |
|---|---|---|
| `web_server.py` | 4270 | Flask app (port 8080), the **sole** human entry point: REST CRUD, SSE progress stream, pipeline control, module-level concurrency state |
| `cinema_pipeline.py` | 1767 | `CinemaPipeline` — the real orchestrator. Owns `generate()`, the 12-stage gate sequence, `_assemble_final`, scene-audio/foley/BGM helpers, checkpoint delegation |
| `cinema/core.py` | 115 | `PipelineCore` + `build_pipeline_core()` — long-lived services (project dict, dirs, `ContinuityEngine`, `ChiefDirector`, `CostTracker`, `LLMEnsemble`) |
| `cinema/runstate.py` | 157 | `RunState` dataclass — the single shared home for per-run mutable state; one instance, shared by all three controllers |
| `cinema/lifecycle.py` | 208 | `LifecycleService` protocol + `NullLifecycle` (no-op, **not** wired into `CinemaPipeline`) + `ThreadedLifecycle` (interactive, event-backed) |
| `cinema/context.py` | 211 | `PipelineContext` dataclass passed into phases; `get_project_setting()` canonical knob reader |
| `pipeline_context.py` | 15 | Loads `config/prompts/pipeline_context.md` into `PIPELINE_CONTEXT`, injected into every LLM system prompt |
| `web_services.py` | 121 | Pure SSE-event builder `make_progress_callback` (factored out for unit-testability) |

#### Phases

| Path | LOC | Role |
|---|---|---|
| `cinema/phases/base.py` | 81 | `Phase` Protocol + `PhaseResult` dataclass — the entire phase contract |
| `cinema/phases/keyframe_render.py` | 125 | `KeyframeRenderPhase` — per-shot image-generation loop |
| `cinema/phases/performance.py` | 99 | `PerformanceCapturePhase` — per-shot performance-retargeting loop (skips SKIP-routed shots) |
| `cinema/phases/motion_render.py` | 659 | `MotionRenderPhase` — per-shot image→video loop + Kling storyboard batch path |
| `cinema/services.py` | 133 | Read-only disk-state helpers (`state_snapshot`, `checkpoint_info`) for web endpoints — no `CinemaPipeline` construction |

#### Review, gates, persistence

| Path | LOC | Role |
|---|---|---|
| `cinema/review/controller.py` | 762 | `ReviewController` — gate-wait logic, auto-approve integration, per-shot approval mutations, review-clip manifest |
| `cinema/auto_approve.py` | 803 | Veto-rule engine: per-gate rule builders, `check_gate`, `record_director_review_on_shots` |
| `cinema/screening.py` | 719 | Post-assembly SCREENING stage: feature flag, timeline manifest, `screening_approved` flag, `needs_reassembly` dirty-tracking |
| `cinema/checkpoint.py` | 227 | `CheckpointStore` — atomic JSON checkpoint save/load/restore into `RunState` |
| `domain/project_manager.py` | 1262 | **Canonical** persistence: factories, `normalize_*_schema`, `mutate_project` RMW primitive, per-project filelock, and entity mutation helpers |
| `domain/models.py` | 209 | Pydantic v2 schema (validation-only, warn-by-default); the live data type is a plain dict |
| `domain/shot_types.py` | 51 | Shot-type constants + `normalize_shot_type` alias normalizer |
| `domain/performance.py` | 222 | Pure performance-engine routing (`route_performance_engine`, `should_capture`) |

#### LLM / creative brain

| Path | LOC | Role |
|---|---|---|
| `llm/chief_director.py` | 664 | `ChiefDirector` — pre-gen HC1–HC8 validation gate (`validate_shot_prompts`); sole writer of `director_review` |
| `llm/director.py` | 432 | `CinemaDirector` — permissive iteration translator (`translate_intent`, S18 verb DSL) |
| `llm/ensemble.py` | 597 | `LLMEnsemble` — multi-provider parallel generation + judge-pick; `build_anthropic_system_blocks` caching helper |
| `llm/prompt_optimizer.py` | 923 | UI-text → structured shot spec (`optimize_shot_prompt`) |
| `llm/style_director.py` | 200 | Per-project global style rules (`generate_style_rules`) — **OpenAI-only** |
| `llm/negative_prompts.py` | 72 | Failure-reason → negative-prompt phrase lookup |
| `domain/scene_decomposer.py` | 1286 | **Canonical** scene→shots: `API_REGISTRY`, `PURPOSE_API_RANKING`, `decompose_scene`, `competitive_decompose_scene` |
| `domain/dialogue_writer.py` | 158 | **Canonical** dialogue writer (`generate_dialogue`) |
| `domain/language_defaults.py` | 212 | Per-language pipeline defaults (TTS, lipsync priority, voice IDs) |
| `research_engine.py` / `web_research.py` | 160 / 221 | Tavily + Firecrawl wrappers; `run_with_tools` GPT-4o tool loop |

#### Image / video generation

| Path | LOC | Role |
|---|---|---|
| `phase_c_assembly.py` | 844 | **Image** gen (the only tier): ComfyUI+PuLID, FLUX Kontext/Pro fallbacks, `generate_ai_broll` |
| `phase_c_ffmpeg.py` | 2540 | Central video routing (`generate_ai_video`) + all per-API handlers + FFmpeg assembly utilities (concat, xfade, color grade, loudnorm) |
| `workflow_selector.py` | 436 | `classify_shot_type`, `WORKFLOW_TEMPLATES`, adaptive PuLID weight (`MAX_QUALITY_TEMPLATES` retired WS1 Task 2) |
| `kling_native.py` | 519 | Kling 3.0 native client (JWT HS256, image2video, storyboard mode) |
| `veo_native.py` | 313 | Veo 3.1 client (Vertex-preferred, Gemini fallback) — one of two `native_audio` engines (`gemini_omni_native.py` is the other, and now outranks it in dialogue routing — §3.8) |
| `ltx_native.py` | 1047 | LTX Video 2.3 client (native signed upload + fail-closed resumable async-v2 jobs; pre-submission FAL fallback) |
| `sora_native.py` | 245 | Deprecated explicit-only OpenAI Sora 2 compatibility client; accepts one still-image reference and rejects driving video before provider I/O |
| `pulid.json` | 22 nodes | Production ComfyUI workflow — the only image graph (FLUX-native `ApplyPulidFlux`; fixed 2026-06-13, ADR-025) |

#### Identity / continuity / coherence

| Path | LOC | Role |
|---|---|---|
| `domain/continuity_engine.py` | 661 | 4 sub-engines + `ContinuityEngine.enhance_shot_prompt` (builds `continuity_config`) |
| `identity/validator.py` | 1677 | `IdentityValidator` — GhostFaceNet embedding cache, adaptive frame sampling, rolling stats |
| `identity/types.py` | 127 | `FailureReason`, `SHOT_TYPE_THRESHOLDS`, `get_threshold_for_shot` |
| `identity/__init__.py` | 100 | `make_validator()` factory, `get_shared_validator()` singleton |
| `coherence_analyzer.py` | 281 | Pixel-level color/lighting/composition coherence (`assess_coherence`) |
| `face_validator_gate.py` | 347 | `score_candidate` composite scorer retained by the policy-inactive historical LoRA oracle; `should_halt`/`needs_regenerate` were the max-tier best-of gate, dormant since WS1 Task 4 |
| `domain/character_manager.py` | 719 | Character creation, multi-angle FLUX refs, voice assignment |
| `domain/location_manager.py` | 299 | Location creation, prompt fragments, deterministic seeds |
| `performance/identity_gate.py` | 119 | Performance-take single-frame GhostFaceNet check |

#### Post-processing & audio

| Path | LOC | Role |
|---|---|---|
| `phase_c_vision.py` | 488 | Face swap (PixVerse → FaceFusion), GPT-4o QC, Claude identity, Gemini coherence |
| `lip_sync.py` | 1258 | Lipsync overlay + generation cascades, RIFE interp, SeedVR2 upscale, SyncNet gate |
| `audio/dialogue.py` | 883 | Multi-character TTS (ElevenLabs Dialogue Mode / per-line; Cartesia for Korean) |
| `audio/music.py` | 440 | BGM (Suno V5 → FAL Stable Audio) + mastering presets |
| `audio/foley.py` | 193 | Environmental foley via Stability AI Stable Audio 2.0 |
| `audio/effects.py` | 284 | Pedalboard chain + macOS AU host + 13 FFmpeg voice-FX presets |
| `audio/alignment.py` | 293 | Forced alignment (WhisperX → Whisper word timestamps) |
| `prep/lora_training.py` | 582 | Retained per-character LoRA status/dataset/trainer implementation behind the unconditional dormant policy; no operational product caller |
| `prep/topaz_upscale.py` | 151 | Topaz Video AI local CLI wrapper |

#### Cross-cutting services & config

| Path | LOC | Role |
|---|---|---|
| `cost_tracker.py` | 845 | SQLite spend ledger + budget gate (`record_api_call`, `would_exceed`, `is_over_budget`) |
| `config/settings.py` | 140 | Frozen `Settings` dataclass; `lru_cache` singleton; **API keys + infra paths only** |
| `cleanup.py` | 154 | Post-assembly temp/ file purge (`cleanup_project`) |
| `cinema/logging_config.py` | 114 | JSON-line root logger; reads `CINEMA_LOG_LEVEL` |

### 7.2 Key Functions Index

The functions an engineer reaches for most, grouped by task. All `file:line` references verified against current source.

#### Driving a run

| Function | Location | What it does |
|---|---|---|
| `CinemaPipeline.__init__` | `cinema_pipeline.py:55` | Builds `PipelineCore`, `ThreadedLifecycle`, `RunState(headless=…)`, composes the 3 controllers sharing one `RunState` |
| `CinemaPipeline.generate` | `cinema_pipeline.py:942` | Main loop; `resume=True` restores checkpoint. Returns `final_cinema.mp4` path or `None` |
| `CinemaPipeline.assemble_approved_takes` | `cinema_pipeline.py:853` | Full assembly + SCREENING gate + cleanup + cost summary |
| `CinemaPipeline._assemble_approved_takes_core` | `cinema_pipeline.py:783` | Assembly WITHOUT the SCREENING gate-wait — called by the re-assemble endpoint to avoid Flask-thread deadlock (D-9) |
| `CinemaPipeline._assemble_final` | `cinema_pipeline.py:1323` | normalize → stitch → color grade → 3-track audio mix → EBU R128 loudnorm |
| `CinemaPipeline._refresh_project_snapshot` | `cinema_pipeline.py:443` | `load_project` → **validate-before-swap** → rebuild trackers (cycle-11 correctness fix) |
| `build_pipeline_core` | `cinema/core.py:75` | Factory; constructs `CostTracker(budget_usd=…)` (note: **no** `db_path` — see D-config-1) |

#### Project state & persistence

| Function | Location | What it does |
|---|---|---|
| `mutate_project` | `domain/project_manager.py:854` | The canonical read-modify-write primitive: lock → load → normalize → `mutator(project)` → atomic save |
| `load_project` | `domain/project_manager.py:816` | Lock → read → `normalize_project_schema` (auto-saves if changed) → warn-only validate |
| `save_project` | `domain/project_manager.py:804` | Validate → filelock → atomic `mkstemp`+`os.replace`. **Do not** call while holding the lock — use the unlocked variant (D-state-1) |
| `make_shot` / `make_project` / `make_take` | `domain/project_manager.py:382 / 433 / 263` | Factories; `make_shot` scaffolds all take lists + performance fields the Pydantic `Shot` model omits |
| `normalize_shot_schema` | `domain/project_manager.py:521` | Enforces unique shot ID (collision → `shot_{scene_id}_{shot_index}`), migrates legacy fields |

#### Gates & approval

| Function | Location | What it does |
|---|---|---|
| `ReviewController._wait_for_gate` | `cinema/review/controller.py:519` | Runs auto-approve pass, then blocks (web) or raises `GateNotSatisfiedError` (headless, line 565) |
| `ReviewController._gate_satisfied` | `cinema/review/controller.py:224` | Per-gate predicate (plan/keyframe/performance/final approval-ID checks) |
| `check_gate` | `cinema/auto_approve.py:759` | Public auto-approve entry; returns `AutoApproveDecision`; catches all exceptions → `deferred=True` |
| `record_director_review_on_shots` | `cinema/auto_approve.py:239` | **Writes** `shot["director_review"]`; called at `cinema_pipeline.py:1064`. Without it the PLAN gate hangs headless runs (D-gate-1) |
| `approve_shot_plan` / `approve_take` | `cinema/review/controller.py:695 / 709` | Human approval mutations for the four review gates |
| `mark_screening_approved` | `cinema/screening.py:342` | Sets `screening_approved=True`; unblocks the SCREENING waiter |

#### Image / video generation

| Function | Location | What it does |
|---|---|---|
| `generate_ai_broll` | `phase_c_assembly.py:98` | Image-gen dispatch: ComfyUI+PuLID (`pulid.json`) → FAL fallback (single tier since WS1 Task 4) |
| `generate_ai_video` | `phase_c_ffmpeg.py:208` | Central video routing + fault-tolerant cascade across 9+ engines |
| `classify_shot_type` | `workflow_selector.py:188` | Returns `portrait\|medium\|wide\|action\|landscape` (note: **never** returns `close_up` — D-video-1) |
| `get_workflow_params` / `apply_workflow_params` | `workflow_selector.py:260 / 357` | Per-shot-type template + ComfyUI node injection |
| `get_adaptive_pulid_weight` | `workflow_selector.py:382` | Rolling-stats feedback → PuLID weight delta, clamped [0,1] |

#### Identity / continuity / audio assembly

| Function | Location | What it does |
|---|---|---|
| `ContinuityEngine.enhance_shot_prompt` | `domain/continuity_engine.py:446` | Builds enhanced prompt + `continuity_config` (img2img, seed, refs, thresholds) |
| `IdentityValidator.validate_video` | `identity/validator.py:768` | Adaptive 3–10 frame sampling, GhostFaceNet cosine similarity |
| `IdentityValidator.get_rolling_stats` | `identity/validator.py:902` | Window-10 history → `suggested_pulid_delta` feedback |
| `score_candidate` / `should_halt` | `face_validator_gate.py:174 / 231` | Composite = `0.6·arc + 0.4·aesthetic`; halt when `n≥min_n AND best≥threshold` |
| `assess_coherence` | `coherence_analyzer.py:219` | `overall = (1-color_drift)·0.4 + lighting·0.3 + composition·0.3`; check `result.valid` first |
| `two_pass_loudnorm` | `phase_c_ffmpeg.py:3335` | EBU R128 normalize to −14 LUFS / −1.5 dBTP |
| `xfade_concat` | `phase_c_ffmpeg.py:3612` | Cross-dissolve stitch; handles mixed audio-presence legs (Lane V #24/#25 fixes) |

#### Cost & cleanup

| Function | Location | What it does |
|---|---|---|
| `CostTracker.record_api_call` | `cost_tracker.py:293` | Logs a video/image/audio API spend (success path only); updates in-process `spent_usd` |
| `CostTracker.would_exceed` / `is_over_budget` | `cost_tracker.py:353 / 363` | Pre-call and post-call budget gates (return `False`/no-op when `budget_usd=None`; falsy budgets coerce to None at construction — 0 = unlimited) |
| `CostTracker.get_video_cost` | `cost_tracker.py:376` | Per-video breakdown by provider/operation |
| `cleanup_project` | `cleanup.py:56` | Deletes always-delete temp patterns; `aggressive=True` also deletes generated media |

### 7.3 Config / Env / Flags / Tiers

#### 7.3.1 Environment variables — API keys

Set in `.env` (loaded once at import via `load_dotenv`, frozen into the `Settings` singleton). Only API keys + infra paths belong here; **per-project UI knobs must NOT** be added to `Settings` — they flow through `get_project_setting(ctx, …)` (`config/settings.py:102`; `cinema/context.py:151`).

| Variable | Required? | Default | Effect |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | LLMEnsemble, ChiefDirector, CinemaDirector (primary provider) |
| `OPENAI_API_KEY` | Yes | — | LLMEnsemble fallback, style director, dialogue writer, scene decompose |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Recommended | — | Powers the WS2/WS3 Google-first defaults: `GEMINI_OMNI` (video primary for every shot type) and Gemini 3.1 Flash Image / Nano Banana 2 (image primary) both need one of these; also the Gemini LLM-ensemble judge option and Veo's Gemini-fallback path. `GOOGLE_API_KEY` is tried first, `GEMINI_API_KEY` second. Without either, image/video fall through to their ComfyUI/FAL/other-vendor fallback tiers. |
| `GOOGLE_CLOUD_PROJECT` + ADC | Optional | — | Selects Veo's Vertex backend only when Application Default Credentials resolve at provider construction. This is the Veo path that supports native audio; policy/catalog reads do not probe ADC. Without it, `GOOGLE_API_KEY` selects the Developer API and F1b remains mandatory for dialogue. |
| `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` | Optional | — | KLING_NATIVE — deprecated kling-v1-6 explicit compatibility + storyboard mode (automatic Kling = fal KLING_3_0 via FAL_KEY) |
| `FAL_KEY` | Recommended | — | Seedance (action's first fallback behind `GEMINI_OMNI` since WS2), Sora, Veo-proxy, Kling 3.0, LTX-proxy, all lipsync (MuseTalk/LatentSync/sync.so/Omnihuman/Aurora), music, FLUX image fallback |
| `LTX_API_KEY` | Optional | — | LTX native signed upload + persisted async-v2 job polling (preferred over FAL proxy) |
| `RUNWAYML_API_SECRET` | Optional | — | Runway Gen-4 automatic fallback and Act-Two performance; Gen-3 dispatch is retired |
| `ELEVENLABS_API_KEY` | Yes (audio) | — | TTS narration + dialogue voiceover |
| `CARTESIA_API_KEY` | Optional | — | Cartesia Sonic 3.5 (Korean dialogue) |
| `STABILITY_API_KEY` | Optional | — | Stable Audio foley/BGM |
| `SUNO_API_KEY` (alias `SUNO_TOKEN`) | Optional | — | Suno V5 BGM (`config/settings.py:117`) |
| `SUNO_API_BASE` | Optional | `https://api.suno.ai/v1` | Suno endpoint override |
| `VIGGLE_API_KEY` | Optional | — | Viggle Mode-A retarget. Uncontained 2026-08-01 (ADR-082); cataloged `LIMITED` — contract-correct, not live-verified. Action-shot routing selects it again. `HEDRA_API_KEY` was removed: Hedra has zero remaining consumers post-WS4. |
| `GOOGLE_CLOUD_PROJECT` | Req. for Veo/Vertex | — | Vertex AI project ID |
| `GOOGLE_CLOUD_LOCATION` | Optional | `us-central1` | Vertex AI region |
| `TAVILY_API_KEY` / `FIRECRAWL_API_KEY` | Optional | — | Web research / scraping (Pexels config removed — unwired, Slice 6c) |

#### 7.3.2 Environment variables — infrastructure & web

| Variable | Default | Effect |
|---|---|---|
| `COMFYUI_SERVER_URL` | unset | Explicit RunPod ComfyUI pod address; absence forces FAL image fallback |
| `COMFYUI_API_KEY` | unset | Optional bearer token for an authenticated ComfyUI reverse proxy |
| `EXPERIMENTS_DB_PATH` | `data/experiments.db` | Honored by every tracker via the `CostTracker` default-path env read (`cost_tracker.py:392`, T7 `4af8c05`); the `Settings.experiments_db_path` field itself is decorative (D-config-1 resolved) |
| `PIPELINE_JOB_DB_PATH` | `data/pipeline_jobs.db` | Durable SQLite/WAL full-project queue; must be a filesystem path |
| `PIPELINE_QUEUE_CONCURRENCY` | `1` | Global fixed worker pool, validated 1..8 |
| `CINEMA_TRACE_DB_PATH` | `data/telemetry.db` | Searchable project-scoped local trace index |
| `CINEMA_TRACE_RETENTION_DAYS` | `30` | Trace age retention, validated 1..365 days |
| `CINEMA_TRACE_MAX_EVENTS` | `50000` | Trace row cap, validated 1,000..1,000,000 |
| `PERFORMANCE_CACHE_DIR` | `data/cache/driving` | SHA256-keyed driving-video cache |
| `MOTION_GATE_SAMPLES` | `8` | Frame-pair count for motion-fidelity scoring; read once at module load |
| `WEB_BIND_HOST` | `127.0.0.1` | Loopback-only Flask bind; unauthenticated remote binds are rejected |
| `WEB_CORS_ORIGINS` | `localhost:8080,localhost:5173` | Explicit CORS allowlist; wildcard is rejected |
| `CINEMA_LOG_LEVEL` | `INFO` | Root logger level; `DEBUG` for verbose tracing (`cinema/logging_config.py:104`) |

#### 7.3.3 Behavioral feature flags (`CINEMA_*`)

Read live via `os.environ.get(...)` at call time — NOT cached in `Settings`. Two classes:

| Variable | Class | Default | Truthy form | Effect |
|---|---|---|---|---|
| `CINEMA_STRICT_SCHEMA` | A (opt-in) | OFF | `1`/`true`/`TRUE`/`yes` (NOT `"True"`) | `_validate_project` raises instead of warning (`domain/project_manager.py:760`) |
| `CINEMA_AUTO_APPROVE_MOTION` | A (opt-in) | OFF | `1`/`true`/`yes` (case-insensitive) | Wires motion-gate auto-approve into PERFORMANCE_REVIEW (`cinema/auto_approve.py:620`) |
| `CINEMA_DIRECTORIAL_ITERATION` | B (opt-out) | ON | anything not `0`/`false`/`no` (case-insensitive; `off` or empty string still leaves it ON) | Enables the iterate endpoint (`cinema/shots/controller.py:112`) |
| `CINEMA_SCREENING_STAGE` | B (opt-out) | ON | anything not `0`/`false`/`no` | Enables SCREENING gate + endpoints (`cinema/screening.py:147`) |

> **Parser inconsistency (carry forward):** `CINEMA_STRICT_SCHEMA` uses a tuple membership test that rejects Python-cased `"True"`; `CINEMA_AUTO_APPROVE_MOTION` uses `.strip().lower()`. New flags should follow the case-insensitive form.

#### 7.3.4 Project-level knobs (`global_settings`)

Set via `PUT /api/projects/<pid>` with `{"global_settings": {...}}`. The capability-maximizing values are flagged. Defaults from `make_project` (`domain/project_manager.py:433`).

**Creative / planning**

| Key | Default | Effect | Max-quality value |
|---|---|---|---|
| `competitive_generation` | `True` | GPT-4o + Claude parallel quorum, judged (doubles LLM cost) | keep `True` |
| `quality_judge_llm` | `"auto"` (→ `claude-sonnet-4-6`) | Judge model; maps `claude-opus`→`claude-opus-4-8`, `gemini-pro`→`gemini-3.1-pro-preview` (migrated off the sunset `gemini-2.5-pro` in Slice 6b) (`llm/ensemble.py:146-155`) | `"claude-opus"` |
| `creative_llm` | `"auto"` | ChiefDirector/CinemaDirector model; family-checked, not provider-switching (D-llm-1) | `"auto"` |
| `style_rules` | `{}` (auto-gen) | If non-empty, skips the OpenAI style-gen call entirely | hand-craft to bypass OpenAI dep |
| `language` | `"English"` | Dialogue language; Korean routes to Cartesia | — |

**Image / identity**

| Key | Default | Effect | Max-quality value |
|---|---|---|---|
| `quality_tier` | `"production"` | Informational only — the `"max"` fork was retired in WS1 Task 4; production is the sole tier | `"production"` |
| `identity_strictness` | `0.60` | Face-similarity threshold post-keyframe | `0.70–0.75` for portraits |
| `adaptive_pulid` | `True` | Rolling-stats PuLID self-calibration — the only face-lock-strength control; the per-character `ip_adapter_weight` field was removed as reader-less | keep `True` |
| `prompt_optimizer_enabled` | `True`¹ | LLM rewrites prompt pre-gen, cached on `optimizer_cache` | `True` |
| `char_lora_paths` | `{}` | Legacy read-only LoRA registry snapshot | preserve old values unchanged; current identity uses Gemini multi-reference / PuLID references |
| `style_reference_paths` | `[]` | Style-board images (fed FLUX Redux in the retired max tier; now threaded but dormant) | provide a style board |
| `coherence_check_enabled` | `True` | Per-shot coherence comparison | keep `True` |
| `color_drift_sensitivity` | `0.3` | Color-grade recommendation threshold | lower to `0.2` for tight grading |

¹ The `make_project` default for `prompt_optimizer_enabled` is **True** (`domain/project_manager.py:433`, inside `make_project` at `:433`) — treat True as authoritative if any older note says otherwise.

**Max-tier halt & ComfyUI knobs — RETIRED (WS1 Task 4).** The `max_candidate_*` / `max_halt_*` / `max_regenerate_floor_arc` / `max_quality_parallel_workers` / `ays_steps` / `slg_scale` / `detail_daemon_amount` / `controlnet_*_strength` / `redux_strength` / `face_detailer_*` / `supir_*` / `hires_fix_*` knobs were all consumed by `quality_max.py`, which was deleted; setting them today is inert. `ARCHITECTURE.md` §8.3 records what they did. The frontend follow-up is now closed too: the `MaxQualityTierSection.tsx` panel and its `web/src/components/settings/` home were deleted (`b2658d87`); the retired fields still linger as unused optional types in `web/src/types/project.ts` (no UI surface, no consumer) and the active settings UI now lives in `web/src/components/setup/SettingsInspector.tsx` + `setup/inspector/{Video,Image,Identity,Voice,AutoApprove,Budget}Section.tsx`. The Auto-Approve section exposes the active enable flag, final measured lip-sync floor, and final-human-review policy; UNKNOWN/unavailable sync evidence remains manual-review-only even at a numeric floor of zero.

**Video / motion / audio assembly**

| Key | Default | Effect |
|---|---|---|
| `api_engines` | absent (opt-in) | `{ENGINE:{enabled:false}}` drops an engine from the cascade |
| `api_engines.KLING_NATIVE.storyboard_mode` | `False` | Kling storyboard batch for 2–6-shot scenes (nested 2 levels; **is** wired — D-12) |
| `cascade_retry_limit` | `1` | Overrides `MAX_CASCADE_RETRIES` |
| `scene_transitions` + `transition_duration` | `False` / `0.5` | Cross-dissolve between scenes (ffmpeg xfade) |
| `color_grade_preset` | — (then `music_mood` map, then `"warm_cinema"`) | Color-grade preset selector (project-level; same grade for all scenes — D-post-1) |
| `music_mood` | `"suspense"` | BGM mood + style-rule input |
| `music_mastering` | `"cinema_master"` | Mastering preset; read from `global_settings`, NOT `Settings` (D-orch-1) |
| `lip_sync_mode` | `"auto"` | `auto`/`overlay`/`generation`/`skip` |
| `lipsync_quality_validation` + `lipsync_validation_threshold` | `True` / `0.65` | SyncNet gate toggle + floor |
| `dialogue_mode_enabled` | `True` | ElevenLabs v3 Dialogue Mode for 2+ speakers |
| `forced_alignment_enabled` | `False` | Emits `.alignment.json` word-timing sidecar |
| `budget_limit_usd` | `0`/`None` (unlimited) | `CostTracker.budget_usd`; pauses pipeline when exceeded; core construction rehydrates prior project spend before fresh or resumed work (D-config-3) |
| `auto_approve.*` | see §7.3.5 | Per-gate veto thresholds |

#### 7.3.5 Auto-approve veto config (`global_settings.auto_approve`)

`AutoApproveConfig.from_project` (`cinema/auto_approve.py:71`). Lower thresholds = more permissive; set `enabled=False` to force full human review at every gate.

| Field | Default | Effect |
|---|---|---|
| `enabled` | `True` | Master switch for all auto-approve gates |
| `plan_require_approved` | `True` | Veto if `director_review.decision != "APPROVED"` |
| `plan_reject_on_violations` | `True` | Veto if ChiefDirector violation list non-empty |
| `image_min_composite` | `0.60` | Production identity/composite floor for keyframe auto-approve |
| `image_min_composite_fallback` | `0.78` | Composite floor when a fallback engine was used |
| `image_veto_on_fallback` | `True` | Veto any cascade-fallback keyframe |
| `image_max_spent_multiplier` | `1.5` | Veto if shot cost > 1.5× per-shot budget |
| `motion_min_identity` | `0.85` | Motion identity floor (needs `CINEMA_AUTO_APPROVE_MOTION=1`) |
| `motion_min_motion_score` | `0.7` | Motion-fidelity floor |
| `final_min_lipsync` | `0.8` | Lipsync floor for final auto-approve |
| `final_require_human_if_upstream_auto` | `True` | **Safety net**: forces human at REVIEW if any earlier gate auto-approved — the #1 footgun for "why won't my headless run finish" (D-gate-2) |

#### 7.3.6 Quality tiers at a glance

| Tier | Image path | Identity | Notable |
|---|---|---|---|
| `production` (the only tier) | PRIORITY-0 Gemini 3.1 Flash Image (Nano Banana 2) → ComfyUI FLUX-Dev + PuLID (`pulid.json`, 22 nodes) → FAL Kontext/Pro/Schnell/Pollinations | Gemini multi-reference on the primary path; single GhostFaceNet pass on the ComfyUI fallback | 1344×768 keyframe; `ApplyPulidFlux` (FLUX-native; fixed 2026-06-13, start_at=0.0) on the ComfyUI fallback |
| ~~`max`~~ (retired WS1 Task 4) | — | — | `quality_max.py`/`pulid_max.json` deleted; `quality_tier: "max"` now renders on production. See `ARCHITECTURE.md` §8.3. |

### 7.4 Glossary

| Term | Meaning |
|---|---|
| **Shot** | The atomic pipeline unit: one prompt → one keyframe → one video clip. Lives in `scene["shots"][]`. ID format `shot_{scene_id}_{index}` after normalization — **not globally unique**, always pair with `pid` (D-state-4) |
| **Shot type** | `portrait \| medium \| wide \| action \| landscape`, from `classify_shot_type`. Drives PuLID weight, API routing, identity threshold. (`close_up` appears in threshold tables but is never emitted — D-video-1) |
| **Take** | One generation attempt for a shot, recorded as a `TakeRecord` of `kind ∈ {keyframe, motion, performance, postprocess}`. Shots hold four take lists; approval is by `approved_*_take_id` |
| **Gate** | A mandatory checkpoint between phases: PLAN_REVIEW, KEYFRAME_REVIEW, PERFORMANCE_REVIEW, REVIEW, SCREENING. The pipeline blocks (or fails-fast in headless) until satisfied |
| **Auto-approve** | Heuristic pre-screen at each gate (`check_gate`) that approves shots meeting thresholds; failures fall to human review. Veto rules per gate in `cinema/auto_approve.py` |
| **Veto rule** | A named predicate (`VetoRule`) that blocks auto-approval, e.g. `plan_decision_not_approved`, `image_cascade_fallback`. Carries a human-readable reason |
| **Cascade** | The fault-tolerant ordered fallback across video engines in `generate_ai_video`. On engine failure, `try_next_api` advances; total exhaustion sleeps 30 s and retries up to `cascade_retry_limit` |
| **Cascade metadata** | `{engine, attempts[]}` written by `_record_video_cascade` on success → persisted to the take for provenance/audit |
| **PuLID** | Identity-locking ComfyUI node that binds a character's face to generation from a reference image. Weight is shot-type-dependent and adaptively tuned. Both production and max now use `ApplyPulidFlux` (FLUX-native; production fixed 2026-06-13, ADR-025 — see D-image-3 for the historical class divergence) |
| **Composite score** | `0.6·arc_score + 0.4·aesthetic_score`; missing component substitutes neutral 0.5 (`face_validator_gate.py`'s `score_candidate` — was the max-tier candidate metric and remains only in policy-inactive historical LoRA validation code) |
| **GhostFaceNet (not ArcFace)** | The face-embedding model `IdentityValidator` actually runs via DeepFace (`config/settings.py` default `identity_embed_model`), cosine similarity mapped to [0,1] as `(1+cos)/2`. Nearly every docstring/comment across the codebase (and, until `8b56fd9e`, the UI itself) calls this "ArcFace" — that's a naming bug: ArcFace is the *loss function* GhostFaceNet was trained with, not the model. Cosmetic only (the scoring math is unaffected), but this manual now says GhostFaceNet throughout to match the corrected UI labels (ADR cross-ref: `DECISIONS.md` ADR on the identity-validator singleton; `ARCHITECTURE.md` §11). |
| **Coherence score** | Pixel-level cross-shot consistency: `(1−color_drift)·0.4 + lighting·0.3 + composition·0.3`. Result may be invalid (image read failed) — check `result.valid` |
| **Identity drift** | Character face changing across shots — the core problem the continuity + PuLID + identity-validation stack exists to prevent |
| **Chief Director** | The pre-generation LLM gate (`ChiefDirector.validate_shot_prompts`) enforcing hard constraints HC1–HC8; sole writer of `director_review`. Valid verdicts include APPROVED/MODIFIED/REJECTED; unavailable or malformed evidence becomes REVIEW_REQUIRED |
| **Cinema Director** | The **permissive** iteration LLM (`CinemaDirector.translate_intent`) that converts operator `DirectorialIntent` into a revised prompt; operator intent overrides HC firewalls here |
| **DirectorialIntent** | Operator iteration substrate: `{prose, verb, params, refs, target_stage}`. Verb DSL (`tighten_framing`/`match_shot`/`shift_emotion`) gives deterministic iteration |
| **Headless** | `CinemaPipeline(headless=True)` — non-interactive mode where gates fail-fast with `GateNotSatisfiedError` instead of polling. Still uses `ThreadedLifecycle`, **NOT** `NullLifecycle` (D-orch-2). The correct way to run unattended |
| **Tier** | `quality_tier` ∈ `production` / `max` — see §7.3.6 |
| **Storyboard mode** | Kling batch path: one `generate_storyboard` call for a 2–6-shot non-dialogue scene (all keyframes present, non-portrait aspect) instead of N per-shot calls; dialogue is excluded so F1b evidence is never bypassed |
| **Lip-sync overlay vs generation** | Overlay = mouth-only edit on existing video (MuseTalk/LatentSync/SyncV2/V3); generation = full talking-head from still+audio (Omnihuman v1.5/Creatify Aurora — Hedra and Kling have no remaining consumers in this cascade) |
| **`audio_embedded`** | Take metadata flag for native-mode dialogue whose winning provider/backend produced voiced video. Vertex Veo can set it; Developer-API Veo cannot. It suppresses standalone TTS but does not itself prove lip-sync quality |
| **RMW / `mutate_project`** | Read-modify-write under per-project filelock — the only safe way to mutate persisted project state |
| **Shim** | A 9-line top-level `from domain.X import *` re-export preserving legacy import paths. Canonical code is in `domain/` (see §7.6) |
| **Lane V / Lane D** | Project's operational verification (Lane V) and doc-sync (Lane D) workflows; many fixes cited in source comments reference "Lane V #N" findings |

### 7.5 Troubleshooting / Failure Modes

Each entry: **symptom → diagnose → fix**, with the source location that governs the behavior.

#### Identity drift (character face changes across shots)

- **Diagnose:** Check `take["metadata"]["identity_score"]` + `identity_failure_reason`. Run `IdentityValidator.get_rolling_stats(char_id)` — `common_failure` tells you the class (`FACE_ANGLE_EXTREME`, `SMALL_FACE_REGION`, `WRONG_PERSON`, `LOW_CONFIDENCE_DETECTION`).
- **Fix:** Upload more real front-facing and multi-angle references (not synthetic); use Gemini multi-reference as the primary identity backend and keep PuLID reference conditioning available as fallback; let multi-angle FLUX generation run (`_generate_multi_angle_refs`, needs `FAL_KEY`); raise `identity_strictness` to 0.70–0.75 for portraits; keep `adaptive_pulid=True`. Per-character LoRA is policy-inactive. Note: boosting PuLID does **not** fix `FACE_ANGLE_EXTREME` — the adaptive logic correctly caps the delta to 0 in that case (`workflow_selector.py:369`).

#### Color shift / temporal discontinuity between shots

- **Diagnose:** `assess_coherence(current, previous)` returns `color_drift`, `lighting_consistency`, `composition_similarity` (`coherence_analyzer.py:219`). **First check `result.valid`** — `False` means an image failed to load, the scores are meaningless.
- **Fix:** Lower `color_drift_sensitivity` (→0.2) to trigger `adjust_color_prompt` sooner; lower `continuity_options.img2img_denoise` (→0.25–0.30) for tighter same-location consistency; for final-cut polish enable `scene_transitions` (cross-dissolve smooths boundaries); apply a per-shot color-grade correction via the iterate/correct endpoint. Caveat: the final color grade is a **single project-level preset** — `global_settings["color_grade_preset"]`, else a `music_mood`-derived default — so all scenes get the same grade (D-post-1).

#### Quota exhaustion / deferred paid jobs during video generation

- **Diagnose:** Inspect `cascade_metadata.attempts` for eligible fallback attempts and the shot's `deferred_motion_job` for accepted/ambiguous paid work. A FAL-proxy `VEO` 429 sets `_VEO_QUOTA_EXHAUSTED_UNTIL` (30-min TTL); **`VEO_NATIVE` has no such guard**. The absence of a cooldown does not authorize fallthrough after possible acceptance (D-video-3).
- **Fix:** For resumable FAL VEO/Kling 3.0/Seedance/LTX/`FAL_SVD`,
  Runway, and acknowledged native Kling tasks, use **Check / Resume {engine}
  Job** in Review; it polls the saved provider ID and never starts a fallback.
  A lost native-Kling submit acknowledgement and every ambiguous native-Sora
  `create_and_poll` attempt are `accepted_unknown`; reconcile them in provider
  history rather than submitting again. For Gemini/native Veo or another
  no-binding provider, reconcile the displayed evidence in the provider
  console and do not clear the marker/start a fallback until billing/job
  outcome is known. Explicit compatibility pins do not weaken these fences.

#### Keyframe job recovery required

- **Diagnose:** Review renders the saved `deferred_keyframe_job` status, reason, and sanitized ComfyUI prompt ID when known. New keyframe generation, adjustment, regeneration, and keyframe iteration controls stay disabled.
- **Fix:** Inspect ComfyUI queue/history, recover any valid output, and reconcile provider billing. Only after no live/recoverable job remains, use **Confirm Manual Reconciliation**. The confirmation-gated endpoint removes the marker and records a diagnostic; it does not submit a replacement and refuses a still-active submission window. If the marker came from a worker crash before a prompt ID was returned, wait for the displayed `resolve_after` time, then reconcile by timestamp/project/shot before clearing it. A private attempt token prevents any late old response from clearing or registering over a newer request.

#### Lip-sync prerequisites not met / poor sync

- **Diagnose:** `check_overlay_prerequisites` / `check_generation_prerequisites` return blockers/warnings. Overlay needs video ≥0.5 s, width ≥256 px, audio within 2× duration ratio; generation needs image ≥512×512 and audio ≤60 s (blocker). Validation falls back to coarse duration-match evidence when both durations are probeable; it returns `UNKNOWN` when no scorer or heuristic can produce evidence and never fabricates a perfect score.
- **Fix:** Vertex-backed **VEO_NATIVE** can generate voice+video together and avoids the overlay pass, but native audio alone is still unmeasured sync evidence and therefore requires manual final review. Developer-API Veo is treated as silent and receives the mandatory F1b pass. Raise `lipsync_validation_threshold` to 0.8+ to make the cascade try more engines; for Korean, apply language defaults (stricter 0.70 gate, native-trained engine ordering).

#### Headless / E2E run hangs or dead-ends at a gate

This is the most common operational failure and has three distinct causes — all fixed/known as of cycle-17:

| Symptom | Cause | Fix |
|---|---|---|
| Hangs forever at PLAN_REVIEW | `shot["director_review"]` never written → veto always fires | Ensure `record_director_review_on_shots` runs after `validate_shot_prompts` (now unconditional at `cinema_pipeline.py:1064`). Don't load shots into a run bypassing decompose (D-gate-1) |
| Dead-ends on a MODIFIED verdict | (Historical) MODIFIED used to block | Fixed: MODIFIED is now normalized to gate-decision APPROVED (`auto_approve.py:267`, commit `138d7c7`) |
| Never reaches COMPLETE despite all auto-approve thresholds met | `final_require_human_if_upstream_auto=True` forces a human at REVIEW if any earlier gate auto-approved | Set `auto_approve.final_require_human_if_upstream_auto=false` for fully unattended runs (D-gate-2) |

- **Critical anti-pattern:** Do **not** use `NullLifecycle` for headless runs — `NullLifecycle.wait_for_gate` returns `True` unconditionally (`lifecycle.py:70`), silently skipping ALL gate enforcement. The only correct non-interactive path is `CinemaPipeline(headless=True)`, which uses `ThreadedLifecycle` but reads `runstate.headless` in `_wait_for_gate` to raise `GateNotSatisfiedError` (D-orch-2, D-gate-3).

#### Re-assembly deadlock (Flask request hangs)

- **Diagnose:** A re-assemble or screening call never returns; the worker is parked at the SCREENING gate.
- **Fix:** The re-assemble endpoint must call `_assemble_approved_takes_core()` (`cinema_pipeline.py:1052`), NOT the public `assemble_approved_takes()` — the latter appends the SCREENING gate-wait, and the fresh per-request `CinemaPipeline` is not the instance `signal_gate` will unblock (D-9, `web_server.py:4065`). `screening/approve` requires `exports/final_cinema.mp4` to exist or returns 409 (`web_server.py:3854`).

#### Budget gate doesn't fire

- **Diagnose:** Spend exceeds `budget_limit_usd` but the pipeline keeps running.
- **Causes & fixes (all known limitations):**
  - A raw `CostTracker.spent_usd` starts at 0.0, but production core
    construction rehydrates current-project durable spend before both fresh and
    resumed work. Checkpoint restore is a second defensive normalization
    (D-config-3 resolved).
  - Audio helper paths can still construct **isolated** `CostTracker()` instances (no `budget_usd`); performance capture now threads the core tracker and pre-spend-gates the resolved performance engine plus expected Mode-B driving synth (D-config-2 partially resolved).
  - `EXPERIMENTS_DB_PATH` is honored by every tracker (env read in `CostTracker.__init__` default path, `cost_tracker.py:157`, T7 `4af8c05`); only the `Settings.experiments_db_path` field is decorative (D-config-1 resolved).

#### SSE progress stream behaves oddly

- **Diagnose:** Events missing in a browser tab, or stream closes early.
- **Fix:** SSE is a per-subscriber fan-out — a second tab on the same
  `/stream` receives every event rather than stealing from a shared queue.
  Heartbeats fire every 30 s of silence and a terminal bus sentinel emits END.
  After server restart, an active SQLite queue row lets `/stream` hydrate a new
  bus and wake the dispatcher, but events buffered by the old process are gone;
  refresh `pipeline-state` before following the new stream. Re-assembly
  deliberately uses a no-op progress callback, so its progress never appears
  in SSE (D-web-2).

#### Image generation silently falls back to FAL (no ComfyUI)

- **Diagnose:** Keyframes return `api_name` of `FLUX_KONTEXT`/`FLUX_PRO`/`POLLINATIONS` instead of `COMFYUI_PULID`.
- **Fix:** Set `COMFYUI_SERVER_URL` and ensure `pulid.json` is present. Note: landscape shots intentionally skip PuLID and route to FAL even when ComfyUI is available (`phase_c_assembly.py:196`).

### 7.6 Plan-vs-Source Divergences & Doc-Drift

This is corrective truth gathered while building the manual. The `ai-video-gen` skill source-map and several inherited docs are partly stale; each item below states **what the doc says** and **what is actually true**, verified at the cited location.

#### Skill source-map: top-level paths that are really in `llm/` or `domain/`

The skill lists `chief_director.py`, `scene_decomposer.py`, `character_manager.py`, `continuity_engine.py`, etc. as top-level modules.

- **Actual:** `chief_director`, `director`, `style_director`, `prompt_optimizer`, `ensemble`, `negative_prompts` live under **`llm/`** (verified: `llm/chief_director.py:52`, etc.). The other names exist at **both** the top level and in `domain/` as a shim/canonical pair.

#### Shim-vs-canonical pairs (all verified 2026-06-09)

Each top-level file is a **9-line `from domain.X import *` re-export shim**; the canonical implementation is in `domain/`. New code should import from `domain.*` directly.

| Top-level shim | LOC | Canonical | Canonical LOC |
|---|---|---|---|
| `scene_decomposer.py` | 9 | `domain/scene_decomposer.py` | 1286 |
| `dialogue_writer.py` | 9 | `domain/dialogue_writer.py` | 158 |
| `project_manager.py` | 9 | `domain/project_manager.py` | 1412 |
| `character_manager.py` | 9 | `domain/character_manager.py` | 719 |
| `location_manager.py` | 9 | `domain/location_manager.py` | 299 |
| `continuity_engine.py` | 9 | `domain/continuity_engine.py` | 661 |

(Verified: each top-level head line is `from domain.<X> import *  # noqa: F401, F403`.) The shims' own docstrings still name `main.py`/`cleanup.py` as callers — `main.py` is deleted, so that comment is stale (D-script-4).

#### Named-but-absent files in the skill source-map

| Skill names | Reality (verified) |
|---|---|
| `identity_validator.py`, `identity_types.py` (flat) | **Absent.** Real files are `identity/validator.py` (1677 LOC) and `identity/types.py` (127 LOC) — a package, not flat modules |
| `phase_b_audio.py` | **Absent** at repo root and `cinema/phases/`. The audio subsystem is the `audio/` package (`dialogue.py`, `music.py`, `foley.py`, `effects.py`, `alignment.py`, `voiceover.py`) |
| `Pulid.json` (historical) | **Reconciled 2026-06-13 — now a single lowercase `pulid.json`.** Was git-tracked capital-P while all code opens `open('pulid.json')`; on case-insensitive macOS both resolved to the **same inode** so it worked, but a case-sensitive checkout (Linux CI/pod) would `FileNotFoundError` and silently cascade past the production PuLID branch. Renamed via `git mv` (git/disk/code/test now agree). Since WS1 Task 4 there is one workflow graph — `pulid.json` (production, 22 nodes); the former `pulid_max.json` (max tier) was deleted. |

#### Two classes named `CinemaPipeline` (D-1)

`cinema_pipeline.py:984` is the orchestrator. The generic list-of-`Phase` driver that used to share its class name (`cinema/pipeline.py`) was deleted 2026-08-01 (ADR-081); phases are run directly with `.run(ctx)`.

#### `pipeline_context.py` vs `cinema/context.py` (D-3)

Confusingly similar, different things: `pipeline_context.py` (15 LOC) loads the `PIPELINE_CONTEXT` LLM-prompt **string**; `cinema/context.py` (211 LOC) is the typed `PipelineContext` **dataclass** passed to phases. The orchestrator uses both.

#### Dead / unwired code

| Item | Claim | Verified reality |
|---|---|---|
| `evaluate_generation_quality` | Active post-gen evaluator | **Wired by T6** (`10a0eb4`, 2026-06-06) — definition at `chief_director.py:696`; called by `cinema/shots/controller.py:1961` in `diagnose_clip(deep=True)`. 2×2 mutation matrix + negative-prompt enrichment are now reachable via the opt-in deep diagnosis path. **Vision-grounded** (`d974c15`+`a4cb076`, 2026-06-07): attaches the generated take + canonical reference images, grounding `diagnosis` in what the model sees (dogfood: text-only restated "0.504 < 0.65"; vision identified a male figure vs the female reference and ruled out a detection false negative). |
| `reporter.py` | Diagnostic reporter | **Orphan** — the only `generate_report()` caller is its own `if __name__ == "__main__"` block (line 52). Globs from CWD, not project dirs; hardcoded 21/20/20 counts are legacy. Removal candidate |
| `validate_lora_quality` | Historical LoRA GhostFaceNet gate | Implementation retained in `prep/lora_quality.py`, but `prep/lora_policy.LORA_POLICY="dormant"` makes training, registry writes, and consumption unreachable from current product paths; only read-only historical status remains |
| `format_dialogue_for_voiceover`, `dialogue_to_narration_text` | Dialogue helpers | **Removed entirely** — both functions are gone repo-wide; the pipeline uses `audio.dialogue.generate_dialogue_voiceover` directly |
| `TemporalConsistencyManager.record_shot_generated` / `reset_scene` | Temporal chaining | **Uncalled in production** — chaining relies on `approved_anchor_image` passed explicitly; the in-memory `last_generated_image` path is functionally dead |
| LTX native async job sidecar | Accepted image-to-video job recovery | **Reachable on every `LTX_API_KEY` request** — signed upload, v2 submission, private request-fingerprint sidecar, exact-job resume, and bounded polling; completed MP4 output is MIME/container validated before atomic publication. The obsolete transition helpers were deleted; scene transitions use ffmpeg xfade assembly. |
| Gemini Omni / native Veo accepted-job guard | Paid-job ambiguity recovery | **Reachable in both native dispatch branches.** Submit acknowledgement loss, accepted-job polling ambiguity, and completed-output retrieval/publication failure persist a public-safe `deferred_motion_job` and stop fallback. The UI exposes the exact sanitized job ID for manual provider-console recovery; automatic Google-job resume is not claimed. |
| `summarize_audit` | PostRunSummary endpoint | Defined (`auto_approve.py:870`) but **no web endpoint calls it** |

#### `storyboard_mode` is read and wired

An older audit listed `storyboard_mode` as having "zero callers" — that is **stale.** The flag **is** read and wired: `_get_storyboard_mode` at `cinema/phases/motion_render.py:102`, consumed at `cinema/phases/motion_render.py:364` and `cinema/phases/motion_render.py:393` (eligibility `2 ≤ unapproved ≤ 6`). Treat **storyboard_mode as functional.** (Verified by grep: live read sites in `motion_render.py`.)

#### Configuration & budget wiring gaps

| ID | Issue | Verified |
|---|---|---|
| D-config-1 | `EXPERIMENTS_DB_PATH` formerly unwired — RESOLVED by T7 (`4af8c05`) | `cinema/core.py:113` still builds `CostTracker(budget_usd=budget_usd)` with no `db_path`, but `cost_tracker.py:392` resolves `db_path or os.environ.get("EXPERIMENTS_DB_PATH", "data/experiments.db")` — env var honored by every tracker (explicit `db_path` arg wins) |
| D-config-2 | Audio helper paths can use isolated `CostTracker()` (no budget); performance capture is now shared-tracker-gated | confirmed remaining audio limitation across `audio/*`; performance fixed by `perf-phase-no-gate` |
| D-config-3 | **Resolved:** production core construction rehydrates durable project spend before fresh or resumed paid work; checkpoint restore repeats it defensively | `cinema/core.py`, `cost_tracker.py`, `cinema/checkpoint.py` |

#### Schema-vs-live-dict divergences (Pydantic `extra="allow"`)

The Pydantic models in `domain/models.py` are validation-only and omit several live fields:

- `Shot` model lacks `approved_performance_take_id`, `performance_engine`, `driving_video_path`, `objects_in_frame`, `primary_object`, `optimizer_cache`, `auto_approve_audit`, `director_review` — all live on the raw dict, scaffolded by `make_shot`.
- `Character.reference_image` (singular, str) vs the raw dict's `reference_images` (plural, list) from `make_character`.
- `Project` lacks `objects`, `global_settings`, `screening_approved`, `needs_reassembly` — all `extra="allow"`.
- **Shot IDs are not globally unique** (`shot_{scene_id}_{index}`); the cycle-6/S13 F1 CRITICAL required pid-scoping all HTTP endpoints. Always pair shot_id with project_id (D-state-4).

#### Smaller behavioral divergences (carry forward)

| ID | Truth |
|---|---|
| D-video-1 | `classify_shot_type` never returns `close_up`, yet `MOTION_FIDELITY_FLOORS` has a `close_up` key (with a comment acknowledging the inconsistency) — that floor is unreachable |
| D-video-2 | **RESOLVED 2026-07-11** — Seedance dispatch rewired to the verified fal endpoints (`bytedance/seedance-2.0/image-to-video`, `.../reference-to-video` keyframe-first ≤9 refs) and promoted to action primary for the Sora sunset (2026-09-24); `SEEDANCE_API_KEY` deleted, rides `FAL_KEY`. **Superseded 2026-07-30 (WS2/Slice 3):** `GEMINI_OMNI` is now the primary for every shot type including action; Seedance is action's first fallback (`WORKFLOW_TEMPLATES["action"]`, `workflow_selector.py:107`). |
| D-video-3 | `VEO_NATIVE` has no quota-cooldown guard (only the FAL-proxy `VEO` branch sets the TTL flag). Accepted/ambiguous native jobs are nevertheless fenced as recovery-required and cannot cascade. |
| D-image-1 | **RESOLVED** (historical) — `should_halt` dispatched `composite_only` AND `conjunctive`; only `budget_only` remained deferred. Moot since WS1 Task 4: `should_halt` was the max-tier best-of gate and now has no live caller |
| D-image-3 | **RESOLVED 2026-06-13 (ADR-025)** — production `pulid.json` uses `ApplyPulidFlux` / `PulidFluxModelLoader` (FLUX-native); was SDXL-era `ApplyPulid` / `PulidModelLoader` (a FLUX no-op, validated OFF 0.6205 → ON 0.8779). (The former production-vs-max upscale-node divergence — production 500–502 Real-ESRGAN vs max 500–503 SUPIR — is moot since WS1 Task 4 deleted the max graph.) |
| D-llm-1 | `creative_llm` override is family-checked but **not** provider-switching; a cross-family value (e.g. `claude-*` when only OpenAI is configured) is silently ignored |
| D-llm-2 | `style_director` is **OpenAI-only** (no Anthropic path); with only `ANTHROPIC_API_KEY` set it falls straight to `_default_style_rules` |
| D-llm-3 | `competitive_enabled` is stored from settings but never enforced — `competitive_generate` always runs full competition |
| D-script-1 | The on-demand decompose endpoint (`web_server.py:1400`) always uses single-model `decompose_scene`, never `competitive_decompose_scene`; only the automated pipeline honors `competitive_generation` |
| D-script-6 | **RESOLVED 2026-07-28 (hardened):** direct and competitive decomposition share `_build_cinedecompose_shot_schema` (`{"shots":[...]}`), `_parse_decomposition_payload`, and `_enrich_validated_shots` (enum/required/five-section/count validation; no physical traits in prompt context). Pins: `test_scene_decomposer_prompt.py`. |
| D-driving-video | Base video-generation routes do not support `driving_video_path`: Sora rejects it before client or image work, while Veo and Kling accept the compatibility argument but do not apply it. Use the separate performance-capture axis for driving-video transfer. |
| D-veo-refs | Veo `reference_images` are accepted by the call chain but dropped before the SDK call ("Bug #4"); identity comes from the start frame only (`veo_native.py:155`) |
| D-state-1 | `save_project` acquires its own lock — calling it while already holding `project_lock()` deadlocks; use the unlocked variant inside a held lock |
| D-post-1 | The final color grade is one project-level preset (`global_settings["color_grade_preset"]`, else `music_mood`-mapped); all scenes share it |

> **General caution on line anchors:** `check_doc_claims.py` does not verify prose/comment line-RANGE anchors, and any edit shifts line numbers. The `file:line` citations throughout this appendix are point-in-time (2026-06-09). When a line no longer matches, grep the symbol name — the function/class is what's load-bearing, not the exact line.
