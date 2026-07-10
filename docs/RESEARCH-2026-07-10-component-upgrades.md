# Component Upgrade Research — 2026-07-10

**Method:** 5 parallel deep-research workflows (one per component area), 207 subagents total
(Fable 5, user-directed), ~8.3M tokens. Each area: 2 web-search agents → 8 sources fetched →
falsifiable-claim extraction → claim dedup → **3 adversarial refuters per claim** (existence /
accuracy / production-usability lenses; 2-of-3 refutes kills) → per-area synthesis. 48 claims
survived, 1 killed. Verifier corrections override original claim text throughout.
Provenance: workflow runs `wf_342361d0` (video), `wf_43a54e43` (image/identity), `wf_2a5d2b53`
(lip-sync), `wf_a7340590` (audio), `wf_4fbe645b` (post/QC); per-agent journals under the session
`subagents/workflows/` directory. All prices/versions below are **web-sourced claims as of
2026-07-10**, not repo-measured artifacts (R-MEASURE: label = runtime-unreproducible estimates —
re-verify at integration time).

---

## Executive summary — priority-ordered action queue

| P | Area | Action | Why | Confidence |
|---|---|---|---|---|
| **P0** | Video | **Migrate the Sora 2 route off `fal-ai/sora-2/image-to-video` before 2026-09-24** and archive any Sora-generated assets locally | OpenAI shuts down all Sora 2 models + Videos API on that date; data deleted after; no successor named | HIGH |
| **P0b** | Video | Adopt **Seedance 2.0** (`bytedance/seedance-2.0/{image,reference}-to-video`) as the replacement route | #1 on Artificial Analysis i2v arena (Elo 1195 w/ audio); native music+SFX+lip-synced dialogue in one pass; ref-to-video takes 9 images + 3 videos + 3 audio clips | HIGH (cost ~3× Sora 2 base; Seedance 2.5 announced — check before landing) |
| **P1** | Video | Move Kling route from native API to **`fal-ai/kling-video/v3/pro/image-to-video`** | Kling 3.0 ranks #11; v3 Pro adds native multi-speaker audio + `elements` character consistency; consolidates last native-API route onto fal | HIGH |
| **P2** | Image/identity | A/B **FLUX.2 native multi-reference** (up to ~10 ref images, no finetuning) against the PuLID-Flux + dual-LoRA path on the known failure case (secondary-char binding ~0.45 PuLID-alone) | FLUX.2 released 2025-11-25, day-0 ComfyUI support; could collapse the whole identity-graft stack — but supersession is vendor-framed, NOT benchmarked; verifiers downgraded it to "candidate pending A/B" | MEDIUM (capability HIGH) |
| **P3** | Lip-sync | Upgrade sync.so route to **sync-3** (`fal-ai/sync-lipsync/v3`) for still-derived speech; evaluate **react-1** for emotion-promptable performance | sync-3 is the only sync.so model that opens still/silent lips; removes 512×512 face cap; ~2.5× lipsync-2 price. react-1 re-directs whole-face performance from audio (15s cap on fal) | HIGH |
| **P4** | Audio | Adopt **Eleven v3** for hero dialogue — **gated on Professional-Voice-Clone-on-v3 quality** | v3 GA (Feb 2026): inline audio tags `[whispers]`/`[angry]`/`[laughs]` + Text-to-Dialogue API; but PVC not yet v3-optimized → character-voice consistency could regress | HIGH (caveat HIGH) |
| **P5** | Identity QC | Swap ArcFace embedding for **AdaFace** (MIT) inside the existing DeepFace harness | Better on degraded/low-quality faces (95.67 vs 94.25 TAR@FAR=0.01% IJB-B; 72.29% Rank-1 TinyFace) — matches over-cooked-render QC; pitfall: 112×112 **BGR** input. buffalo_l is easier but non-commercial license | HIGH |
| **P6** | Video | Bump LTX route to **LTX-2.3 Pro** (fal ID/pricing unverified — follow-up needed) | LTX-2 Pro #25 vs LTX-2.3 Pro #19 on same arena; stays the budget tier either way | HIGH (rank) / gap (ID) |

**Already current (no change):** `fal-ai/seedvr/upscale/video` (slug now backed by SeedVR2
server-side, 4K in-spec), OmniHuman v1.5 (still latest), RIFE (no verified successor), DeepFace
harness (keep; swap only the embedding), Suno V5 + stable-audio (alternatives exist, no
supersession), pedalboard, Veo 3.1 (mid-pack #6 but no successor/deprecation — competitive
pressure only).

**Recurring licensing trap (commercial pipeline!):** FLUX.2-dev open weights = non-commercial
(API outputs OK; klein 4B is the only Apache-2.0 local option); WithAnyone = non-commercial;
InsightFace buffalo_l models = non-commercial; ElevenLabs Music film/TV rights = Enterprise plan
only; Udio = downloads disabled entirely (disqualified). Every open-weights adoption needs a
license check before it touches revenue-bearing output.

**Open research gaps (no verified claims — need follow-up passes):** SUPIR successors for
still upscaling; LTX-2.3 fal model ID + pricing; MuseTalk status; LoRA-training service
successors; PVC-on-v3 clone quality; exact Lyria 3 model IDs/allowlist; Runway Gen-4's role
(absent from arena, no successor found — re-justify or retire).

**Capability consolidation opportunity:** Seedance 2.0 / Kling v3 Pro / Wan 2.7 all generate
native synced dialogue+SFX in the video pass — for some shot classes this could absorb the
separate lip-sync and BGM stages entirely. Worth a routing-policy think after P0 lands.

---

<!-- ===== AREA: video-gen ===== -->

# Video Generation Upgrade Digest — July 2026

Scope: the five per-shot video-generation routes (Kling 3.0, Sora 2, Veo 3.1, Runway Gen-4, LTX-2). All statements below trace to adversarially verified claims; confidence tags reflect verification vote outcomes.

---

## 1. OpenAI Sora 2 route (`fal-ai/sora-2/image-to-video`) — OUTDATED, HARD DEADLINE

**Status: forced migration.** Sora 2 video-generation models and the Videos API are deprecated and shut down **September 24, 2026** — covering sora-2, sora-2-pro, and all dated snapshots. The web/app experiences already shut down April 26, 2026; only the API path still works today. [HIGH] ([OpenAI help article](https://help.openai.com/en/articles/20001152-what-to-know-about-the-sora-discontinuation), [video-generation guide](https://developers.openai.com/api/docs/guides/video-generation))

- **No documented successor.** Neither the discontinuation article nor the API deprecation notice names a replacement or migration path — the replacement must come from other providers (Veo, Kling, Seedance, Wan, LTX, Runway) or a future OpenAI release. Press mentions an unconfirmed in-development OpenAI model ("Spud"), but nothing is official. [HIGH] (same sources; note: the help article returned HTTP 403 to automated fetch and was corroborated via secondary coverage)
- **Data deletion.** OpenAI will permanently delete all Sora-associated data after discontinuation, after "any final export window ... (if we are able to offer one)" — OpenAI has not committed to offering one. As of today (2026-07-10) the web/app export window (sora.chatgpt.com/sunset, closed April 26, 2026) has likely passed; **archive any API-generated Sora assets locally before September 24, 2026.** [HIGH] ([help article](https://help.openai.com/en/articles/20001152-what-to-know-about-the-sora-discontinuation))
- **Baseline being replaced:** Sora 2 at $0.10/sec; Sora 2 Pro is resolution-tiered — $0.30/sec (720x1280/1280x720), $0.50/sec (1024x1792/1792x1024), $0.70/sec (1080x1920/1920x1080). Text+image input, native synced audio, 20s max per generation (theoretical 120s across six extensions). The 1080p resolutions are Pro-only; base Sora 2 is listed at 720p/480p tiers (guide also lists 1024x576, 848x480, 640x360, plus 480p and 16s clip options). Snapshot sora-2-2025-12-08 is already marked Deprecated. [HIGH] ([sora-2 model page](https://developers.openai.com/api/docs/models/sora-2), [guide](https://developers.openai.com/api/docs/guides/video-generation))

### Upgrade candidate A (quality + audio leader): ByteDance Seedance 2.0

- **#1 on the Artificial Analysis image-to-video leaderboard** — Elo 1195 on the with-audio arena (≈1345 on the without-audio arena, also #1), ahead of every Veo, Kling, and LTX model; nearest challengers are grok-imagine-video-1.5-preview and HappyHorse-1.1. Note: ByteDance has since announced Seedance 2.5, so 2.0 may not be the newest family member even though it tops this leaderboard. [HIGH] ([leaderboard](https://artificialanalysis.ai/video/leaderboard/image-to-video))
- **fal availability:** `bytedance/seedance-2.0/image-to-video` and `bytedance/seedance-2.0/reference-to-video`, each with a cheaper fast tier. Standard $0.3024/sec, fast $0.2419/sec; reference-to-video with video inputs drops to $0.1814/sec standard / $0.1452/sec fast. Output 480p/720p/1080p (1080p standard-tier only; fast caps at 720p), any 4–15s duration, multi-shot editing with natural cuts in one generation. [HIGH] ([i2v](https://fal.ai/models/bytedance/seedance-2.0/image-to-video), [r2v](https://fal.ai/models/bytedance/seedance-2.0/reference-to-video))
- **Native audio in one pass** — music, SFX, and lip-synced dialogue at no extra cost. Reference-to-video accepts up to 9 reference images, 3 videos, and 3 audio clips (12 files max), exceeding the multi-reference capacity of current stack models — could reduce reliance on the pipeline's separate lip-sync/BGM steps. [HIGH] (same fal pages)
- **Cost caveat:** at $0.3024/sec standard it is ~3x the outgoing Sora 2 base rate of $0.10/sec (though comparable to Sora 2 Pro's mid tier).

### Upgrade candidate B (contested — verify before adopting): Alibaba Wan 2.7

A claim about Wan 2.7 was **killed in fact-checking** over its pricing headline, so treat this route as contested. What the dissents themselves agreed on: Wan 2.7 exists on fal with four endpoints (`fal-ai/wan/v2.7/{text-to-video, image-to-video, reference-to-video, edit-video}`), 720p/1080p at 2–15s, native audio, five aspect ratios, and 9-grid multi-image reference with combined subject+voice referencing — but fal's per-endpoint docs price it at **$0.10/sec for 720p and $0.15/sec for 1080p** (not flat $0.10/sec; fal's marketing page contradicts the endpoint pages), and the "outranks Veo 3.1 on the arena" claim was not corroborated (one verifier found Veo 3.1 well above Wan 2.7 on the *text-to-video* with-audio arena). However, the separately **verified** image-to-video leaderboard claim does place Wan 2.7 (Elo 1100, #4) above Veo 3.1 (Elo 1087, #6) — so the arena picture conflicts between checks and likely differs by arena (t2v vs i2v). Re-verify pricing and ranking before routing spend here. [MEDIUM — contested]

---

## 2. Kling 3.0 (native Kling API) — SUPERSEDED BY KLING V3 PRO ON FAL

- Kling 3.0's best leaderboard variant ranks only **#11 (Elo 1071)** on the image-to-video arena — below Seedance 2.0, HappyHorse-1.1, Wan 2.7, and Veo 3.1. [HIGH] ([leaderboard](https://artificialanalysis.ai/video/leaderboard/image-to-video))
- **Upgrade path:** `fal-ai/kling-video/v3/pro/image-to-video` is live (plus a dedicated `/4k` endpoint) at **$0.112/sec audio-off, $0.168/sec audio-on, $0.196/sec with voice control**; 3–15s clips, native multi-speaker audio (Chinese/English native), and character/object consistency via an `elements` parameter — with the caveat that voice binding works only for video elements, not image elements. [HIGH] ([fal page](https://fal.ai/models/fal-ai/kling-video/v3/pro/image-to-video))
- Adopting the fal v3 Pro endpoint would also consolidate this route onto fal alongside the other providers (currently it is the one native-API route).

---

## 3. Google Veo 3.1 (`fal-ai/veo3.1/reference-to-video`) — MID-PACK, NOT URGENT

- Veo 3.1 sits at **Elo 1087, #6** on the image-to-video arena — outranked by HappyHorse-1.1 (Elo 1112, #3) and Wan 2.7 (Elo 1100, #4), and well behind Seedance 2.0 (#1). [HIGH] ([leaderboard](https://artificialanalysis.ai/video/leaderboard/image-to-video))
- No verified claim establishes a direct Veo successor or a deprecation; the pressure here is competitive (quality ranking), not operational. If the multi-reference role Veo 3.1 fills matters most, Seedance 2.0 reference-to-video's 12-file reference capacity is the strongest verified alternative. [HIGH for the capacity fact] ([fal r2v page](https://fal.ai/models/bytedance/seedance-2.0/reference-to-video))

---

## 4. Runway Gen-4 (runwayml SDK, 720p-wide cap) — ABSENT FROM THE ARENA

- Runway Gen-4 is **absent entirely** from the displayed image-to-video leaderboard (as is Sora 2) — it is unranked rather than ranked below the leaders. [HIGH] ([leaderboard](https://artificialanalysis.ai/video/leaderboard/image-to-video))
- No verified claim documents a Runway successor model, pricing change, or deprecation. Given the existing 720p-wide cap and no benchmark presence, this route's role should be re-justified, but no concrete upgrade path was verified in this run.

---

## 5. Lightricks LTX-2 (`fal-ai/ltx-2/image-to-video`) — OUTDATED WITHIN ITS OWN FAMILY

- The currently used **LTX-2 Pro ranks #25 (Elo 880)**; Lightricks' newer **LTX-2.3 Pro ranks #19 (Elo 955)** on the same arena — a clear intra-family upgrade signal. [HIGH] ([leaderboard](https://artificialanalysis.ai/video/leaderboard/image-to-video))
- No verified claim supplies the LTX-2.3 fal model ID, pricing, or caps — those need a follow-up check before swapping the route. Even upgraded, LTX-2.3 Pro remains the lowest-ranked model family in the stack; its continued role is presumably the budget tier.

---

## Cross-claim conflicts noted

1. **Wan 2.7 vs Veo 3.1 ranking:** the verified i2v-leaderboard claim puts Wan 2.7 above Veo 3.1 (1100 vs 1087), while a killed-claim dissent found Veo 3.1 far above Wan 2.7 on a (text-to-video, with-audio) arena. Arena-dependent; do not treat "Wan > Veo" as unconditional.
2. **Wan 2.7 pricing:** fal's marketing page says flat $0.10/sec while fal's per-endpoint docs say $0.10/sec (720p) / $0.15/sec (1080p). The endpoint docs were judged authoritative by verifiers; the flat-rate claim was killed.
3. **Sora 2 Pro pricing:** the original claim's flat $0.30/sec was corrected to resolution-tiered ($0.30/$0.50/$0.70 per sec) — the tiered figures override.

## No change needed (per this run's verified evidence)

- **Google Veo 3.1** — no deprecation or successor verified; competitive pressure only.
- **Runway Gen-4** — no verified successor or pricing change (though its absence from the arena warrants a role review, no upgrade path was verified).
- Everything outside video generation (image gen/identity, lip-sync, audio, post, identity QC) was out of scope for this run — no claims were gathered, so no change is asserted.

**Priority order:** (1) migrate the Sora 2 route before 2026-09-24 and archive its assets — Seedance 2.0 is the strongest verified replacement; (2) move Kling to `fal-ai/kling-video/v3/pro/image-to-video`; (3) evaluate LTX-2 → LTX-2.3 Pro pending fal ID/pricing verification; (4) re-verify Wan 2.7 pricing/ranking if a cheaper Sora replacement is preferred over Seedance.
---

<!-- ===== AREA: image-identity ===== -->

# Upgrade-Research Digest — Image Gen + Character Identity (as of 2026-07-10)

Scope of this run: the FLUX.1-dev fp8 + PuLID-Flux + per-character LoRA identity stack, plus FLUX 1.1 Pro Ultra / Kontext Max API tiers. All statements below trace to verified claims; verifier corrections override original claim text and are folded in.

---

## 1. Base image model (FLUX.1-dev fp8 → FLUX.2 family)

**What's outdated:** FLUX.1-dev is no longer BFL's open-weight flagship. **FLUX.2 was released November 25, 2025; FLUX.2 [dev] is a 32B-parameter open-weight rectified-flow transformer (weights on Hugging Face, reference code on GitHub) that generates, edits, and combines images** [HIGH] ([bfl.ai/blog/flux-2](https://bfl.ai/blog/flux-2), [HF FLUX.2-dev](https://huggingface.co/black-forest-labs/FLUX.2-dev), [github.com/black-forest-labs/flux2](https://github.com/black-forest-labs/flux2), [ComfyUI blog](https://blog.comfy.org/p/flux2-state-of-the-art-visual-intelligence)).

**Licensing gate (matters for this commercial pipeline):**
- FLUX.2-dev open weights ship under the FLUX Non-Commercial License — commercial open-weight use requires a separate paid BFL license. However, outputs generated via the BFL API are licensed for commercial use, and BFL sells tiered self-hosted commercial licenses — so this is a paid-license step, not a hard block. [HIGH] ([HF FLUX.2-dev](https://huggingface.co/black-forest-labs/FLUX.2-dev), [github flux2](https://github.com/black-forest-labs/flux2))
- Since Jan 15, 2026 the **FLUX.2 [klein]** small-model family is the fully-permissive open option: 4B under Apache 2.0, 9B under the Non-Commercial license, plus undistilled Base variants for fine-tuning. The 4B needs **~13GB VRAM** (RTX 3090/4070 class; ~8GB only via FP8/NVFP4 quantized variants), the 9B fits ~29GB. API pricing: $0.014–0.015 first MP, $0.001 flat subsequent MP — vs fal's FLUX 1.1 Pro Ultra at $0.06/image flat, a 1MP klein still is **~4x cheaper** (the ~2x figure would apply vs FLUX 1.1 Pro non-Ultra at ~$0.04/MP). [HIGH] ([github flux2](https://github.com/black-forest-labs/flux2), [bfl.ai/pricing](https://bfl.ai/pricing), [bfl.ai/blog/flux-2](https://bfl.ai/blog/flux-2))
  - *Internal conflict noted:* the original claim said 4B runs in ~8GB and is ~2x cheaper than Ultra; all three verifier corrections converge on ~13GB and ~4x — corrections win.

**Capability & hosting:** FLUX.2 supports photorealistic generation and editing at up to 4MP (BFL recommends working at up to 2MP for most production, reserving 4MP for print/large-format), with BFL-framed improvements in typography, lighting, spatial coherence, and sharper textures vs FLUX.1. Already hosted on fal, Replicate, Runware, TogetherAI, Cloudflare, DeepInfra, Verda, and BFL's own API. [HIGH] ([bfl.ai/blog/flux-2](https://bfl.ai/blog/flux-2), [ComfyUI blog](https://blog.comfy.org/p/flux2-state-of-the-art-visual-intelligence))

**FLUX.2 API pricing (BFL):** [pro] at `/v1/flux-2-pro`: $0.03 first generated MP + $0.015/subsequent MP + $0.015/MP per reference image; [max]: $0.07/$0.03/$0.03; [flex]: flat $0.05/MP on both reference and generated images. Reference images bill at actual MP rounded UP (minimum 1 MP each; inputs over 4 MP resized down by BFL; some providers resize inputs to 1MP). Third-party hosts differ — e.g. Replicate charges $0.06/MP for flex. [HIGH] ([bfl.ai/pricing](https://bfl.ai/pricing))

**Local/ComfyUI deployment:** FLUX.2 has day-0 ComfyUI support (≥ 0.3.72, incl. a no-GPU API Partner Node) and Diffusers support. An NVIDIA-partnered FP8 variant cuts VRAM ~40% (24GB+ recommended for high-res); 4-bit quantization runs on 24GB GPUs; the official BF16 path needs H100-class VRAM (>80GB without offloading; ~62GB with CPU offload — and per some deployment guides BF16 32B + text-encoder overhead can exceed a single 80GB H100, making FP8 the practical single-GPU datacenter path). Note the weights are gated/non-commercial on HF, so commercial pipeline use routes through the API/Partner Node or a BFL commercial license. [HIGH] ([ComfyUI blog](https://blog.comfy.org/p/flux2-state-of-the-art-visual-intelligence), [HF FLUX.2-dev](https://huggingface.co/black-forest-labs/FLUX.2-dev), [github flux2](https://github.com/black-forest-labs/flux2))

---

## 2. Character identity / multi-character binding (PuLID-Flux + per-char LoRAs, Kontext Max)

This is the pain-point area (weak dual-character binding; secondary char needs its own LoRA). Three candidate successors, each with a caveat:

### 2a. FLUX.2 native multi-reference — strongest candidate, unbenchmarked for this pipeline
FLUX.2 natively supports multi-reference conditioning — up to 10 reference images (ceiling; third-party docs report ~8 on Pro/Dev, 10 on Flex, 4 on Klein which was "coming soon" at launch; practitioner guidance puts the effective range at ~4–6 with diminishing returns above ~8) — for character/product/style consistency with no finetuning, maintaining identity, geometry, textures, wardrobe, and composition. [HIGH for the capability existing] ([bfl.ai/blog/flux-2](https://bfl.ai/blog/flux-2), [ComfyUI blog](https://blog.comfy.org/p/flux2-state-of-the-art-visual-intelligence), [HF FLUX.2-dev](https://huggingface.co/black-forest-labs/FLUX.2-dev), [github flux2](https://github.com/black-forest-labs/flux2))

**Explicit conflict/caveat:** the claim that this "directly supersedes" PuLID-Flux + per-character LoRA and Kontext-style multi-reference is an **editorial inference, not a vendor or benchmark claim** — verifiers flagged that BFL does not compare against PuLID/LoRA, still sells FLUX.1 Kontext [pro] as a supported product, and there is no independent multi-character identity-binding benchmark. Per-character LoRAs can still outperform for weak/secondary identities (prior repo evidence: PuLID-alone ~0.45 on the 2nd character). **Treat as a strong candidate replacement pending A/B measurement, not an established supersession.** [MEDIUM as a supersession claim; HIGH as a capability claim]

### 2b. WithAnyone (ICLR 2026, FLUX.1-based) — best-in-class metrics, license-blocked
Beats PuLID on MultiID-Bench SingleID face fidelity with far less copy-paste artifact (SimGT 0.460 vs PuLID 0.452; copy-paste 0.144 vs 0.315); outperforms DreamO, and outperforms UNO on identity fidelity (SimGT 0.460 vs 0.304) though UNO's copy-paste is marginally better (0.141 vs 0.144). MultiID-Bench (435 cases, 1–4 person scenarios) and MultiID-2M training set (500k paired + 1.5M unpaired group photos, ~25k identities) are publicly released. [HIGH] ([arxiv 2510.14975](https://arxiv.org/html/2510.14975), [github Doby-Xu/WithAnyone](https://github.com/Doby-Xu/WithAnyone))

Practically integrable — community ComfyUI node (@okdalto) exists, full checkpoints ~51GB disk — **but weights are under the FLUX.1 [dev] Non-Commercial License v1.1.1 (code Apache 2.0): non-commercial academic use only, a blocker for commercial pipeline adoption** without a separate BFL license. [HIGH] ([github WithAnyone](https://github.com/Doby-Xu/WithAnyone))

### 2c. Qwen-Image-Edit-2511 — training-free, vendor-claimed multi-person fusion
Enhanced 2509; training-free alternative for multi-character identity with claimed high-fidelity multi-person fusion into group shots, improved character consistency and reduced image drift; native ComfyUI workflow (qwen_image_edit_2511_bf16 + Qwen2.5-VL-7B FP8 encoder + qwen_image_vae); a lightx2v Lightning LoRA enables 4-step generation — note lightx2v is a third-party (LightX2V/ModelTC) distillation referenced by ComfyUI docs, not an Alibaba/Qwen-team release. Multi-person fusion fidelity is a **vendor claim, not independently benchmarked vs PuLID/LoRA**. [HIGH for availability/workflow; MEDIUM for fidelity claims] ([docs.comfy.org qwen-image-edit-2511](https://docs.comfy.org/tutorials/image/qwen/qwen-image-edit-2511))

---

## 3. LoRA training (fal-ai/flux-lora-fast-training)

No verified claim in this run addresses a direct successor to the fal LoRA-fast-training service itself. Relevant adjacent fact: FLUX.2 [klein] ships **undistilled Base variants explicitly for fine-tuning** [HIGH] ([github flux2](https://github.com/black-forest-labs/flux2)) — a possible future LoRA base with a permissive (Apache 2.0, 4B) license. Whether FLUX.2 multi-reference removes the need for per-character LoRAs at all is the open question flagged in §2a.

---

## Cross-claim conflicts (explicit)

1. **klein VRAM & cost multiple:** original claim said ~8GB / ~2x cheaper; three independent corrections say ~13GB (4B) / ~4x cheaper vs the Ultra tier. Corrections override.
2. **"Supersedes PuLID+LoRA":** the multi-reference claim body asserts supersession; its own verifier corrections downgrade this to "candidate pending A/B" — the corrections are authoritative.
3. **Reference-image billing:** "every reference bills as 1 MP" vs corrections: billed per actual MP rounded up, min 1 MP, with provider-dependent input resizing. Corrections override.

## Recommended validation before migration
- A/B the pipeline's known failure case (secondary-character binding, prior PuLID-alone ~0.45) on FLUX.2 multi-reference vs the current LoRA path — no independent benchmark exists.
- Budget the BFL commercial license (or API-only routing) before any FLUX.2-dev self-hosted move; klein 4B (Apache 2.0) is the only license-clean local option.

## No change needed (no superseding evidence in this run's verified claims)
- Video generation routing (Kling 3.0, Sora 2, Veo 3.1, Runway Gen-4, LTX-2) — outside this run's scope; no claims touched it.
- Lip-sync (Hedra, OmniHuman v1.5, sync.so v3, MuseTalk) — no claims.
- Audio (ElevenLabs TTS, Suno V5, whisper) — no claims.
- Post (RIFE, SeedVR) and identity QC (DeepFace + ArcFace) — no claims.
- SUPIR still-upscaling and hires-fix — no verified claim proposes a replacement (FLUX.2's native up-to-4MP generation may reduce the need, but that inference is not benchmarked).
- No topics were contested to the point of kill: the killed-claims list is empty.
---

<!-- ===== AREA: lipsync ===== -->

# Upgrade-Research Digest — Lip-Sync / Talking-Head Area
**Run date: 2026-07-10.** Scope of this run: the lip-sync / talking-head layer only (Hedra, OmniHuman, sync.so, MuseTalk + new competitors). All statements below trace to the verified claims; verifier corrections have been applied where they override original claim text.

---

## 1. Lip-Sync / Talking-Head — Incumbents (what's outdated)

### sync.so lipsync-2 / lipsync-2-pro → superseded as flagship by sync-3
- sync.so released **sync-3** as its new flagship, default-for-all-users model, superseding lipsync-2-pro as flagship. **[HIGH]** Release timing was corrected by verifiers: sync-3 launched **~April 6, 2026** (a WaveSpeedAI integration post is dated April 12, 2026), **not** July 7, 2026 as originally claimed — the date was contested and the April date carries the corrections. **[HIGH, corrected]** Note: lipsync-2-pro remains listed as a separate available model — it has not been deprecated or removed, so "superseded" means flagship status, not removal. **[HIGH]** ([sync.so/sync-3](https://sync.so/sync-3), [fal.ai/models/fal-ai/sync-lipsync/v3](https://fal.ai/models/fal-ai/sync-lipsync/v3))
- Key constraint on the old models: lipsync-2 / lipsync-2-pro are limited to **512×512 output for the generated face region** (the output video keeps its original resolution — 512×512 faces "suit most 1080p videos"), and they **require natural speaking motion in the input video**. Only sync-3 can open still/silent lips to match audio (with generic rather than speaker-style results) — directly relevant to any pipeline that lipsyncs still-derived footage. **[HIGH]** ([sync.so/docs/models/lipsync](https://sync.so/docs/models/lipsync))
- Price step-up if upgrading: sync-3 costs **$0.107–$0.133/s** (sync.so docs), consistent with fal.ai's $8/min (~$0.133/s) — roughly **2.5x lipsync-2** ($0.04–$0.05/s) and **~5x lipsync-1.9.0-beta** ($0.02–$0.025/s). **[HIGH]** ([sync.so/docs/models/lipsync](https://sync.so/docs/models/lipsync), [fal.ai sync-lipsync/v3](https://fal.ai/models/fal-ai/sync-lipsync/v3))

### Hedra Character-3 — still current named character model, but a newer flagship exists
- There is still **no Character-4**; Character-3 remains at **6 credits/s** — effectively ~$0.031–$0.060/s depending on tier (Basic $15/mo 1500 credits, Creator $30/mo 5400, Professional $75/mo 14400; subscription credits don't roll over, one-time packs never expire). It is the cheapest **lipsync** model on Hedra's platform (not the cheapest model overall — MiniMax Hailuo 2.3 Fast Standard is 4/s, non-lipsync) versus resold Kling 2.5 Turbo (10/s), Veo 3.1 Fast (20/s), Veo 3.1 (55/s), and Sora 2 Pro (70/s). **[HIGH]**
- Verifier correction adds: Hedra shipped a newer flagship character model, **Hedra Omnia** (Alpha released Feb 5, 2026, powered by Together AI), extending Character-3's face animation to **full-scene/full-body character video with lip-sync**; Omnia's per-second credit cost is not published on the pricing page. **[HIGH, correction]** ([hedra.com/pricing](https://www.hedra.com/pricing))

### ByteDance OmniHuman v1.5 — no newer version
- OmniHuman **v1.5 remains the latest** OmniHuman version on fal.ai as of 2026-07-10, priced at **$0.16/s**, taking a human-figure image (jpg/jpeg/png/webp/gif/avif) plus audio (mp3/ogg/wav/m4a/aac), with audio-driven emotional acting claimed and commercial use permitted. **[HIGH]** ([fal.ai omnihuman v1.5](https://fal.ai/models/fal-ai/bytedance/omnihuman/v1.5))

### MuseTalk
- No verified claims were produced about MuseTalk this run — its status is **unassessed**, not confirmed current.

---

## 2. Lip-Sync / Talking-Head — Upgrade Candidates

### sync-3 (sync.so) — primary lipsync upgrade
- **Endpoint:** live on fal.ai at `fal-ai/sync-lipsync/v3`, commercial use permitted. **[HIGH]**
- **Price:** $0.107–$0.133/s (~$8/min on fal.ai). **[HIGH]**
- **Capabilities (claimed):** 4K-native output with built-in super resolution, obstruction detection, extreme angles/side faces, multiple speakers, low lighting, cross-language emotion/acting preservation. Nuances per verifiers: **60fps appears only on the marketing page** (docs price at 25fps); the fal.ai model page itself states no explicit resolution/duration limits, so 4K is verified only from sync.so's own pages; docs recommend masking/cropping extra faces for best multi-speaker results. **[HIGH, with noted nuances]** ([sync.so/sync-3](https://sync.so/sync-3), [docs](https://sync.so/docs/models/lipsync), [fal.ai](https://fal.ai/models/fal-ai/sync-lipsync/v3))
- **Duration limits:** tier-gated on sync.so from 1 minute (Hobbyist) to 30 minutes (Scale+); all public models available in both Studio and API. Also available via an Adobe Premiere plugin and a ComfyUI node. **[HIGH]**
- **Fit for this stack:** the only sync.so model that can open still/silent lips — matches this pipeline's still-derived talking-head path — and removes the 512×512 face-region limit. **[HIGH]**

### react-1 (sync.so) — beyond lipsync: full-performance re-direction
- Reanimates the **entire face** from uploaded audio (not just the mouth), edits expressions/head movement/timing while preserving actor identity, supports discrete emotion prompts (surprised/angry/disgusted/sad/happy/neutral). Priced **$0.133–$0.167/s**. Page dated Jul 7, 2026. **[MEDIUM — capabilities and pricing were corroborated by all three verifiers; the dissent targeted only availability]**
- **Availability — original claim corrected:** the claim that react-1 is sync.so-API-only is **wrong**. It IS on fal.ai at `fal-ai/sync-lipsync/react-1` ($10/min ≈ $0.167/s, with lips/face/head `model_mode` and a **15s input cap**), plus WaveSpeedAI ($0.167/s) and Segmind. **[HIGH per corrections]** ([sync.so/react-1](https://sync.so/react-1), [docs](https://sync.so/docs/models/lipsync))
- **Fit:** directly addresses the "emotional acting quality" goal — emotion-promptable performance editing, not just mouth sync.

### Kling AI Avatar v2 (fal.ai) — cheaper image+audio talking-head challenger
- **$0.115/s Pro** (~$6.90/min) or **$0.0562/s Standard** (Standard costs ~49% of the Pro price, i.e. ~51% cheaper — arithmetic corrected by a verifier). Takes image (JPG/PNG/WebP/GIF/AVIF) + audio (MP3/OGG/WAV/M4A/AAC), outputs an MP4 auto-matched to audio length, animates realistic humans, animals, cartoons, or stylized characters; commercial use permitted. **[HIGH]** ([fal.ai kling ai-avatar v2 pro](https://fal.ai/models/fal-ai/kling-video/ai-avatar/v2/pro))
- **Fit:** Standard tier undercuts OmniHuman v1.5 ($0.16/s) by ~65% and sync-3 by ~2x for still-image-driven speech.

### Price ladder (per second of output, from verified claims)
| Option | $/s | Notes |
|---|---|---|
| Hedra Character-3 | ~$0.031–$0.060 | credit-tier dependent [HIGH] |
| Kling AI Avatar v2 Standard | $0.0562 | [HIGH] |
| sync-3 | $0.107–$0.133 | [HIGH] |
| Kling AI Avatar v2 Pro | $0.115 | [HIGH] |
| react-1 | $0.133–$0.167 | [MEDIUM/HIGH per corrections] |
| OmniHuman v1.5 | $0.16 | [HIGH] |

---

## 3. Conflicts / Contested Points
- **sync-3 release date:** the original verified claim said July 7, 2026; two independent verifier corrections place the launch at ~April 6, 2026 (corroborated by an April 12, 2026 WaveSpeedAI post). The corrections override: treat sync-3 as an **April 2026** release. All other details of that claim were unanimously supported.
- **react-1 availability:** the claim's "sync.so-API-only, no fal.ai endpoint" clause drew the dissent and three explicit corrections — react-1 is on fal.ai, WaveSpeedAI, and Segmind. Use the corrected availability; capabilities and pricing were not contested.
- **sync-3 60fps:** marketing-page-only; docs price at 25fps. Treat 60fps as unconfirmed in the docs/API surface.
- No claims were killed in adversarial review.

---

## 4. No Change Needed (per this run's verified claims)
- **ByteDance OmniHuman v1.5** — still the latest OmniHuman on fal.ai as of 2026-07-10; no successor exists to migrate to. [HIGH]
- **Hedra Character-3** — still Hedra's current *named* character model (no Character-4) and the cheapest lipsync option in this comparison; however, evaluate **Hedra Omnia** (Alpha, full-body) as a watch item rather than a confirmed replacement, since its pricing is unpublished. [HIGH]
- **MuseTalk** and all non-lipsync stack areas (video generation, image+identity, audio, post, identity QC) — **not covered by this run's claims**; no verified basis to declare them current or outdated.
---

<!-- ===== AREA: audio ===== -->

# Audio Stack Upgrade Digest — July 2026

Scope of this run: the AUDIO area only (TTS dialogue, music/BGM, SFX/foley, speech-to-text). All statements below trace to adversarially verified claims; verifier corrections override original claim text and are folded in.

---

## 1. Character Dialogue TTS — current: ElevenLabs TTS (SDK ≥2.0)

### What's outdated / what supersedes it

- **The pipeline's current ElevenLabs model stack is superseded by Eleven v3**, which is now generally available (after a June 2025 alpha API release), supports 70+ languages, and cuts errors on complex text (formulas, phone numbers, notation) by 68% (15.3% → 4.9%). [HIGH] ([elevenlabs.io/blog/v3-audiotags](https://elevenlabs.io/blog/v3-audiotags), [inworld.ai/resources/elevenlabs-v3-review](https://inworld.ai/resources/elevenlabs-v3-review))
- **Conflict between verified claims on the GA date:** three verifiers on one claim unanimously corrected GA to **February 2, 2026** (per ElevenLabs' official GA announcement/blog); a verifier correction on a separate claim states GA was **2026-03-14** with full public API access. The Feb 2, 2026 date has stronger support (3 independent corrections citing the official announcement vs. 1). Either way, v3 is GA and fully API-accessible as of July 2026. [HIGH on GA status; the exact date is contested]

### Why v3 matters for cinematic dialogue

- v3 adds **inline audio tags** for fine-grained expressive control suited to film dialogue/dubbing: emotions (`[sad]`, `[angry]`), delivery (`[whispers]`, `[shouts]`, `[x accent]`), reactions (`[laughs]`, `[sighs]`), and even sound effects (`[gunshot]`, `[explosion]`). A promotional 80% v3 discount ended June 2026. [HIGH] ([elevenlabs.io/blog/v3-audiotags](https://elevenlabs.io/blog/v3-audiotags))
- A **Text to Dialogue API** is available for v3. [HIGH] ([inworld.ai/resources/elevenlabs-v3-review](https://inworld.ai/resources/elevenlabs-v3-review))

### Upgrade caveats (directly relevant to this pipeline's character LoRA/voice-consistency approach)

- **Professional Voice Clones are not fully optimized for v3** — potentially lower clone quality for character-voice consistency. ElevenLabs says PVC optimization for v3 is "coming in the near future"; **re-check PVC-on-v3 status before committing the character-voice pipeline to v3.** [HIGH] ([inworld.ai/resources/elevenlabs-v3-review](https://inworld.ai/resources/elevenlabs-v3-review))
- v3 requires **more prompt engineering** than prior models. [HIGH]
- v3 is **not real-time capable**; ElevenLabs recommends Flash v2.5 (~75 ms) for conversational use. Acceptable tradeoff for pre-rendered film dialogue. [HIGH]

### Pricing

- Premium TTS (Multilingual v2 / v3): **$0.10 per 1K characters**; Flash/Turbo: **$0.05 per 1K characters**. [HIGH] ([elevenlabs.io/pricing/api](https://elevenlabs.io/pricing/api))

### TTS rivals to evaluate (arena data)

- On the Artificial Analysis TTS arena, **no ElevenLabs model is in the top cluster**: Speechmatics Simba 3.2 leads at Elo 1234, with Gemini 3.1 Flash TTS (1214), Cartesia Sonic 3.5 (1207), Fun-Realtime-TTS and Inworld Realtime TTS-2 (both 1205) within ~30 Elo. Caveat: Inworld Realtime TTS-2 is labeled "Research Preview" and may not be generally available; the other top entries are commercial APIs. [HIGH] ([artificialanalysis.ai/text-to-speech/leaderboard](https://artificialanalysis.ai/text-to-speech/leaderboard))
- Open-weights option: best open model (Step Audio EditX, Elo 1118) trails the leader by ~116 Elo; **Kokoro 82M** (downloadable open weights) is the budget floor at **$0.65 per 1M characters** (Elo 1060). [HIGH]

**Recommendation shape:** adopt v3 for expressive hero dialogue (audio tags are the killer feature), but gate the migration on PVC-on-v3 quality for existing character voices, and benchmark Simba 3.2 / Cartesia Sonic 3.5 as expressiveness rivals given the arena standings.

---

## 2. Music / BGM — current: Suno V5 with fal-ai/stable-audio fallback

### Upgrade candidates

**ElevenLabs Eleven Music API** [HIGH] ([elevenlabs.io/music-api](https://elevenlabs.io/music-api), [elevenlabs.io/pricing/api](https://elevenlabs.io/pricing/api))
- Model `music_v2` via `POST https://api.elevenlabs.io/v1/music`, Python/JS SDKs.
- Studio-grade audio with vocals in 59 languages; output formats go up to 48 kHz (`mp3_48000_192` is the auto default for v2, despite the marketing page's "up to 44.1 kHz").
- Track length **3 s to 5 min** (corrected — not 10 min as originally claimed).
- **Gotcha:** `music_v1` remains the API default during a transition period — set `music_v2` explicitly in API calls.
- Pricing: **$0.150/min music**.
- **Licensing gotcha for this pipeline:** commercial use is cleared on all paid plans, but **film, TV, and large studio game rights specifically require an Enterprise plan**. [HIGH]

**Google Lyria 3 / Lyria 3 Pro (Vertex AI, public preview — not GA)** [HIGH] ([Google Cloud blog](https://cloud.google.com/blog/products/ai-machine-learning/lyria-3-and-lyria-3-pro-on-vertex-ai), [Vertex AI music docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/music/overview))
- Available via Vertex AI API and Media Studio; docs also list `lyria-002` (Lyria 2).
- **Lyria 3 Pro:** structured compositions up to ~3 minutes (intros/verses/choruses/bridges); **base Lyria 3:** ~30 s tracks. Vocals with timed or user-provided lyrics (8 languages: EN/DE/ES/FR/HI/JA/KO/PT), instrumental-only prompting, image conditioning (stereo audio guided by reference images), SynthID watermarking with C2PA on all outputs. [HIGH]
- **Conflict between verifier corrections on exact model IDs:** one correction gives the Pro ID as `lyria-3-pro-preview` (with "lyria-3" as the docs slug, not the API string); another gives `lyria-3-clip-preview` + `lyria-3-pro-preview`; a third notes the docs nav lists no separate "Lyria 3 Pro" entry and that forum posts mention **allowlist requests** for `lyria-3-pro-preview` — Pro access may be gated despite the public-preview announcement. Confirm the exact model ID and allowlist status at integration time. [MEDIUM on exact IDs; HIGH on availability-in-preview]

### Disqualified

- **Udio is disqualified for film BGM sourcing.** Following the UMG partnership (announced Oct 29, 2025; downloads disabled Oct 30, 2025, with a one-off 48-hour grace window from Nov 3, 2025), downloading of audio, video, and stems is disabled — music is unusable outside the platform — and no official public API exists (third-party wrappers are unofficial and not production dependencies). A relaunched licensed "walled garden" platform expected in 2026 has not launched as of 2026-07-10 and would likely still bar external use. Compensation was in-platform only (credits/concurrency). [HIGH] ([help.udio.com](https://help.udio.com/en/articles/12683565-changes-associated-with-the-universal-music-group-umg-partnership))

---

## 3. Sound Effects / Foley — current: no dedicated SFX generator in stack

- **ElevenLabs sound-effects generation at $0.120/min** via the same Eleven Music API surface is the concrete API candidate for foley/SFX. [HIGH] ([elevenlabs.io/music-api](https://elevenlabs.io/music-api), [elevenlabs.io/pricing/api](https://elevenlabs.io/pricing/api))
- Additionally, Eleven v3's inline audio tags can inject effects (`[gunshot]`, `[explosion]`) directly inside dialogue lines. [HIGH] ([elevenlabs.io/blog/v3-audiotags](https://elevenlabs.io/blog/v3-audiotags))

---

## 4. Speech-to-Text / Alignment — current: openai-whisper

- **ElevenLabs Scribe is the verified candidate successor to openai-whisper** for transcription/alignment: **$0.22/hr batch, $0.39/hr realtime** (Scribe v2 Realtime drops to ~$0.28/hr on annual Business plans; add-ons extra: entity detection $0.07/hr, keyterm prompting $0.05/hr). [HIGH] ([elevenlabs.io/pricing/api](https://elevenlabs.io/pricing/api))
- No other whisper successor surfaced in this run's verified claims.

---

## Conflicts between verified claims (explicit)

1. **Eleven v3 GA date:** Feb 2, 2026 (3 verifier corrections, official blog) vs. Mar 14, 2026 (1 verifier correction on an adjacent claim). Feb 2 is better supported.
2. **Lyria 3 API model IDs:** `lyria-3` vs `lyria-3-pro-preview` vs `lyria-3-clip-preview` — verifiers disagree on the exact strings, and Pro may require an allowlist. Verify at integration.

---

## No change needed (per this run's verified claims)

- **Suno V5 / fal-ai/stable-audio (BGM):** nothing in the verified claims says these are outdated — Eleven Music and Lyria 3 are *alternatives* with specific advantages (API terms, structure, watermarking), not verified supersessions. Keep, evaluate alternatives against the Enterprise-licensing and preview-access caveats above.
- **pedalboard (mastering):** not addressed by any verified claim in this run — no evidence of supersession.
- **Hedra / OmniHuman v1.5 / sync.so v3 / MuseTalk (lip-sync)** and all non-audio stack areas: out of scope for this run; no claims gathered.
- **openai-whisper:** not verified as *broken* — Scribe is a priced candidate successor, but no claim established quality superiority, only pricing/availability. Treat as evaluate-then-swap, not forced replacement.
---

<!-- ===== AREA: post-qc ===== -->

# Upgrade Digest — Post-Processing + Identity-QC (as of 2026-07-10)

Scope: video upscalers, still-image upscalers, frame interpolation, face-embedding identity QC. All statements below are drawn exclusively from adversarially verified claims; verifier corrections override original claim text where noted.

---

## 1. Video Upscaling (current: `fal-ai/seedvr/upscale/video`)

### What's outdated / superseded
- **Nothing to migrate for SeedVR:** the pipeline's existing fal slug `fal-ai/seedvr/upscale/video` is **now backed by SeedVR2** (temporal consistency) with **no code change needed**. [HIGH] — https://fal.ai/models/fal-ai/seedvr/upscale/video

### Upgrade candidates
| Candidate | Price | Key limits/notes |
|---|---|---|
| **SeedVR2** (current slug) | $0.001 per megapixel of **output** (width × height × frames) — 1920×1080 output @ 121 frames ≈ $0.25; 4K output ≈ 4× that | `upscale_factor` 1–10 (default 2); `target_resolution` up to **2160p**, so 4K output is in-spec. Duration/frame-count limits undocumented — verify empirically for long 4K clips. Commercial use permitted. [HIGH] |
| **FlashVSR** (`fal-ai/flashvsr/upscale/video`) | $0.0005 per megapixel — **half SeedVR2's rate** | Marketed as upscaling "with the fastest speeds" (not an explicit "fal's fastest upscaler" claim); same input formats (mp4, mov, webm, m4v, gif); commercial use permitted. [HIGH] — https://fal.ai/models/fal-ai/flashvsr/upscale/video |
| **Topaz Video AI** (`fal-ai/topaz/upscale/video`, live on fal since 2025-03-13) | Per **output-second**, by resolution tier: $0.01/s ≤720p, $0.02/s ≤1080p, $0.08/s >1080p; 60fps output doubles the rate (e.g. $0.16/s >1080p); **Gaia 2** variant is half the standard tiers | Commercial-use Partner model. Upscales to 16K. [HIGH] — https://fal.ai/models/fal-ai/topaz/upscale/video, https://blog.fal.ai/topaz-video-ai-upscaler-now-live-on-fal/ |

### ⚠️ Internal conflict to note (SeedVR2)
The original verified claim asserted the spec page documents **no** max resolution or upscale factor; a verifier correction **refuted this** — the endpoint's OpenAPI schema documents `upscale_factor` 1–10 and `target_resolution` up to 2160p. Per the override rule, treat 4K as an **explicit supported target**, with only duration/frame limits undocumented. [HIGH]

### ⚠️ Verifier nuances to note (Topaz capability scope)
The "24+ temporally aware models / stabilization / SDR-to-HDR in one API call" description reflects the Topaz **suite** as marketed in fal's blog, not the single fal endpoint. Corrections diverge on exact endpoint surface but agree on the core caveat:
- The fal input schema exposes model choice (verifiers list Proteus/Artemis/Nyx/Gaia/Starlight in one account; Proteus v4 upscaling up to 8× + Apollo v8 interpolation in another), `upscale_factor`, `target_fps`, and enhancement knobs — **SDR-to-HDR and stabilization are NOT parameters of the single fal upscale call**. [HIGH]
- The "one API call" bundling is overstated: fal's own blog describes combining interpolation/slow-mo with upscaling via "multiple processing runs," so upscale + interpolation + HDR may take **chained calls**. [HIGH]

---

## 2. Frame Interpolation (current: RIFE via `fal-ai/rife/video`)

- **Topaz on fal overlaps RIFE's role:** frame interpolation is fps-targeted via `target_fps` (docs cite 16–60 FPS, up to 120 FPS; Apollo v8 auto-enabled per one verifier), not a literal "4× interpolation" knob — the blog's "4×" refers to **slow-motion** factor. [HIGH] — https://blog.fal.ai/topaz-video-ai-upscaler-now-live-on-fal/
- Whether interpolation can be stacked with upscaling in a single call is contested by verifiers (see chained-calls caveat above) — budget for **separate/chained calls** when comparing against RIFE's standalone cost. [HIGH]
- No verified claim establishes a standalone interpolation model that supersedes RIFE outright; the only verified alternative is Topaz's fps-targeted path.

---

## 3. Still-Image Upscaling (current: SUPIR)

**No verified claims arrived for this area.** No statement can be made about SUPIR supersession, alternatives, or the over-cooking issue from this run's evidence. Treat as an open research gap for a follow-up run.

---

## 4. Identity-Validation QC (current: DeepFace + ArcFace)

### What's outdated / superseded
- **ArcFace as the default embedding is the weak link.** Two verified upgrade paths exist within or adjacent to the current DeepFace harness:

**Path A — Buffalo_L (lowest effort):**
- InsightFace's default pack (RetinaFace-10GF detector + ResNet50@WebFace600K recognition, 326MB; no newer pack promoted as of July 2026) is natively wrapped by DeepFace — a one-string model-name change **in the API**, with caveats [HIGH] — https://github.com/serengil/deepface, https://github.com/deepinsight/insightface/blob/master/model_zoo/README.md:
  - Requires extra deps: `pip install insightface>=0.7.3 onnxruntime>=1.9.0 typing-extensions pydantic albumentations` (DeepFace's `Buffalo_L.py` raises `ModuleNotFoundError` otherwise — not bundled with base deepface). [HIGH]
  - Inherits InsightFace's **non-commercial model licensing**. [HIGH]
  - DeepFace uses only the pack's recognition embedding; detection (`detector_backend`) is chosen separately — the pack's RetinaFace detector is not what DeepFace uses. [HIGH]
- Benchmark context: R100@Glint360K scores 90.659 MR-ALL vs R50@WebFace600K's 90.566 vs R50@Glint360K's 87.077 — training data matters as much as backbone depth, and the heavier **antelopev2** pack (R100@Glint360K, 407MB) offers only a **marginal** gain over default buffalo_l. [HIGH] — https://github.com/deepinsight/insightface/blob/master/model_zoo/README.md

**Path B — AdaFace (best fit for degraded frames):**
- Outperforms ArcFace on mixed/low-quality faces: 95.67% vs 94.25% TAR@FAR=0.01% on IJB-B (identical R100+MS1MV2), 72.29% Rank-1 on TinyFace (R100+WebFace12M) — directly relevant to QC on over-cooked or low-res video frames. [HIGH] — https://github.com/mk-minchul/AdaFace
- MIT-licensed, **10 pretrained checkpoints** (verifier correction: not 12 — R18/R50/R100 across CASIA-WebFace, VGGFace2, WebFace4M, MS1MV2, MS1MV3, WebFace12M); repo now points to **CVLFace** for expanded architectures (ViT, SWIN-ViT, KP-RPE). [HIGH]
- **Integration pitfall:** takes 112×112 **BGR** input (mean=0.5/std=0.5) — opposite channel order from InsightFace/ArcFace's RGB convention — a trap when swapping into a DeepFace-based QC path. [HIGH]
- Verifier note: AdaFace is **no longer absolute SOTA** (later methods like TransFace/CVLFace variants score higher), but the ArcFace comparison and low-quality-face advantage remain accurate. [HIGH]

### Research-grade (not upgrade-ready)
- **TransFace++** (TPAMI 2025, extending ICCV 2023 TransFace): current ViT-based line beyond ArcFace, but research-grade PyTorch on the InsightFace codebase (models via ModelScope; ICCV-2023 TransFace also distributed in the FaceChain repo, weights downloadable — self-hostable, not waitlist-locked). **No hosted API, no ComfyUI availability, no benchmark numbers on the repo page** — any accuracy advantage must be verified from the paper. [HIGH] — https://github.com/DanJun6737/TransFace_pp

### DeepFace harness itself: keep
- Actively maintained (v0.0.100, 2026-05-09; MIT; pip + Docker/gunicorn REST) and now supports approximate nearest-neighbor search (`DeepFace.search(..., search_method="ann")`) plus vector-DB backends (PostgreSQL, MongoDB, Neo4j, PGVector, Pinecone, Weaviate) — enabling scalable identity lookup beyond pairwise verify, useful for cross-shot character QC at scale. [HIGH] — https://github.com/serengil/deepface

---

## No Change Needed

- **DeepFace as the QC harness** — actively maintained, MIT, and gaining ANN/vector-DB capability; swap the embedding model inside it, not the framework. [HIGH]
- **`fal-ai/seedvr/upscale/video` slug** — already upgraded to SeedVR2 server-side; keep the integration as-is (evaluate FlashVSR/Topaz on cost/quality, not necessity). [HIGH]
- **RIFE** — no verified claim shows a standalone interpolation successor; Topaz's fps-targeted interpolation overlaps it but may require chained calls, so RIFE stays until an empirical head-to-head. [HIGH]
- **SUPIR** — no verified evidence of supersession this run (absence of claims, not evidence of SOTA status); flag for a dedicated still-upscaler research pass.
---
