# Portrait Phase-3 — Per-Provider Native 9:16 Video + Un-Gate (Design Spec)

- **Date:** 2026-06-08
- **Author:** director-seat
- **Status:** approved (design) → ready for `writing-plans`
- **Extends:** `docs/superpowers/specs/2026-06-07-portrait-aspect-delivery-design.md`
  (Phase 1 = aspect gate + assembly + scorecard; Phase 2 = native 9:16 image keyframes).
  **Supersedes that spec's §7-D provider matrix** (it under-counted 2 providers and
  over-claimed incapability on 2 — see §2 below).
- **Ground-truth provenance:** verified via a Rule #17 read-only audit workflow
  (`wf_d41e2e96-631`, 17 agents, adversarial per-provider verify pass) **and
  director spot-check** of the load-bearing citations (Rule #17 guardrail 2b).
  All file:line refs are at HEAD `1237d4f` (code-identical to `origin/main`
  `a0480f5`; `1237d4f` is a docs commit on top). Per the CLAUDE.md plan-vs-source
  divergence rule, implementers re-verify each anchor at execution HEAD and report
  drift.

---

## 1. Context & Goal

The pipeline delivers cinematic video at a chosen aspect ratio. Phases 1–2 made
the **container, scorecard, settings, UI, and image keyframes** aspect-aware, but
the **gate is still closed**:

```
cinema/aspect.py:23   SUPPORTED_ASPECT_RATIOS = ["16:9"]   # CLOSED
cinema/aspect.py:18   ASPECT_DIMENSIONS["9:16"] = (1080, 1920)   # already present
```

So everything portrait is a **provable 16:9 no-op today**. **Phase 3 makes the
*video* providers emit true 9:16, validates it on-pod, then appends `"9:16"` to
the gate** — at which point the whole portrait path goes live end-to-end.

Phase 2's inert-at-16:9 property is **independently verified** by the operator's
coalesced CC-1 Lane V (Rule #9 second opinion): 5/5 dimensions clean, 0 actionable,
adversarial whole-dict byte-identity refutation (could not produce a single 16:9
counterexample) — report `2026-06-08T04-31-45Z`. Phase 3 builds on a confirmed-clean
foundation, and inherits two forward-carries from that review (§8, §10).

**Ship set (user decision #1):** **Veo, Sora, Kling, Runway.** LTX (native-only,
pod-gated), Seedance, and Hedra are **deferred/excluded** from portrait (§7).

**Goal acceptance:** a project with `global_settings.aspect_ratio == "9:16"`
produces 1080×1920 portrait video from every shipped provider, validated by
`ffprobe`, with no silent landscape leak; un-gating exposes the choice in the UI.

---

## 2. Verified Provider Capability Matrix (ground truth — ADR-013)

Capability flags survived an adversarial verify pass except **LTX** (audit said
`yes`; verify downgraded to `unknown` — FAL default route is 16:9-locked). The
director spot-check additionally **corrected U9** (see §10): the claimed
"ctx-plumbing blocker" is **false** — `cinema/shots/controller.py:641` and `:1376` both build
`PipelineContext(global_settings=settings)` where `settings = project.get(
"global_settings", {})` (verified by reading `cinema/shots/controller.py:496`, `:1239`,
`:1376`). The motion `ctx` correctly carries project settings; **no controller
ctx fix is needed**, and Phase-2 images are unaffected.

| Provider | Active? | Native 9:16? | Conf. | Current handling (file:line @ `1237d4f`) | Phase-3 wiring |
|---|---|---|---|---|---|
| **Veo — native** (Google SDK) | active | **yes** | high (doc) | no aspect threaded; `veo_native.generate_video:138` drops the `_build_generate_videos_config:57` default `aspect_ratio="16:9"` → 16:9 pin. Call site `phase_c_ffmpeg.py:277`. | add param to `generate_video:138`, thread to `_build` call (~`:208`); pass `fal_aspect_ratio(_aspect)` at `:277` |
| **Veo — fal** (veo3.1/ref-to-video) | active | **yes** (cap) / spelling low | high/low | hardcoded literal `phase_c_ffmpeg.py:491` | replace `:491` → `fal_aspect_ratio(_aspect)`; **confirm fal `9:16` enum spelling** |
| **Sora — native** (OpenAI SDK) | active | **yes** | high (doc) | `size` WxH; `RESOLUTION_MAP` landscape-only (`sora_native.py:21-25`); **keyframe force-resized to landscape `:114-118`**; call `phase_c_ffmpeg.py:249` | `portrait_swap` the dims (`sora_native.py:108-109`) **+ fix `:114-118` resize**; thread `_aspect` in |
| **Sora — fal** (sora-2) | active | **yes** | high (doc enum `auto,9:16,16:9`) | hardcoded literal `phase_c_ffmpeg.py:423` | replace `:423` → `fal_aspect_ratio(_aspect)` |
| **Kling — native + fal** | active | **yes — keyframe-conditional** | high (doc) | **no aspect param exists** on either i2v route; output aspect = input keyframe aspect. Native call `:208`, fal `:579`. | **no payload change**; rely on 9:16 keyframe (Bucket B, §5) |
| **Runway — gen4** | active | **yes**, but ≤ **720:1280** | high (SDK) | hardcoded `phase_c_ffmpeg.py:363` `ratio="1280:720"`; **`model="gen4"` not in SDK v4.14.0 enum (latent bug)** | fix `model`→`gen4_turbo` (separate commit), then `ratio=runway_ratio(_aspect,model)` |
| **Runway — gen3a_turbo** | active | **yes**, but ≤ **768:1280** | high (SDK) | hardcoded `phase_c_ffmpeg.py:682` `ratio="1280:768"` | `ratio=runway_ratio(_aspect,"gen3a_turbo")` |
| **LTX** | active | **⚠️ unknown — path-dependent** | — | no aspect param; FAL default `fal-ai/ltx-2/image-to-video` (`ltx_native.py:29`) **16:9-LOCKED**; native `ltx-2-3-pro` (`:233`) doc-plausible, untested, env-gated on `LTX_API_KEY` | **deferred** (§7): native-only when pod-validated; FAL-LTX **excluded** from portrait cascade (§5) |
| **Seedance** | optional/dormant | provider-yes, **endpoint unverified** | medium | hardcoded `phase_c_ffmpeg.py:718`; non-official aggregator `api.seedance.ai`; 720p ceiling | **excluded** from portrait cascade (§5) |
| **Hedra** | optional/dormant | **⚠️ unknown** | — | lip-sync only, not a phase_c shot provider; image-derived aspect (`lip_sync.py:450-467`) | **excluded** from portrait scope |

**Verified-solid (state as fact):** Veo/Sora native 9:16 (provider docs + wired
SDK field); Kling keyframe-conditional 9:16 (AI/ML API doc for both called
endpoints); Runway portrait `ratio` `Literal`s (SDK v4.14.0 type stubs); all
hardcoded-site + invocation line refs (re-grepped at HEAD, zero drift); the
4-surface un-gate consumer map (§6). **Not-yet-verified** items are tracked in §10
and resolved either in-task (enum spellings) or by the §8 preflight (live dims).

---

## 3. Locked Decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Ship scope | **Veo + Sora + Kling + Runway**; LTX/Seedance/Hedra deferred |
| 2 | Runway sub-1080 width | **accept native portrait dims + assembly upscale** to 1080×1920 |
| 3 | LTX | **native-only** (`ltx-2-3-pro`); exclude 16:9-locked FAL-LTX; pod-gated |
| 4 | Validation gate | **automated preflight + hard gate** on the un-gate (§8) |
| 5 | Pre-ship API checks | **proceed** — fold enum/spelling checks into wiring tasks (§10) |
| 6a | Validation operationalization | `scripts/_phase3_portrait_preflight.py`, PASS/FAIL, evidence in un-gate commit body |
| 6b | Runway `gen4` latent bug | **fix proactively in-branch** as a separate commit (`gen4`→`gen4_turbo`/`gen4.5`, exact value grepped from installed SDK) |

---

## 4. Design

**Architecture:** extend the Phase-1/2 pattern — orientation logic lives **only** in
`cinema/aspect.py` (pure, stdlib); every provider call routes through it. The
spine reads aspect from the existing, correct `ctx`; no controller/signature
churn on the spine.

### §4.1 `cinema/aspect.py` — only new pure logic
- **Reuse:** `fal_aspect_ratio`, `portrait_swap`, `is_portrait`, `DEFAULT_ASPECT_RATIO`.
- **Add `runway_ratio(aspect, model) -> str`:** portrait → `"720:1280"`
  (gen4 family) / `"768:1280"` (gen3a_turbo); landscape → the existing values.
  Centralizes Runway's model-dependent WxH-string ratios (no inline ternary, per
  the module's stated principle).

### §4.2 Threading spine (`phase_c_ffmpeg.py generate_ai_video`)
- Hoist once near the top (after `~:89`):
  `_aspect = get_project_setting(ctx, "aspect_ratio", DEFAULT_ASPECT_RATIO)`.
- Add `from cinema.aspect import fal_aspect_ratio, is_portrait, runway_ratio,
  portrait_swap, DEFAULT_ASPECT_RATIO` (the module does not yet import `cinema.aspect`).
- One read serves every provider branch. `ctx` (= `motion_ctx`) carries project
  `global_settings` (verified §2/§10).

### §4.3 Bucket A — native-param providers
Per the §2 matrix "Phase-3 wiring" column. Key gotchas:
- **Veo native:** new `aspect_ratio` param is **additive** — append it as the
  **last** parameter of `generate_video` with default `"16:9"`. Back-compat is
  **verified, not asserted** (Rule #12): the only `*.generate_video(` callers are
  the 4 production sites `phase_c_ffmpeg.py:208/249/277/319` (kling/sora/veo/ltx),
  all **keyword-arg** (e.g. `:277` passes `image_path=…, prompt=…, output_path=…`),
  plus 3 `scripts/_*.py` dev harnesses (also keyword) — so no positional caller can
  be shifted. Use `fal_aspect_ratio` (SDK enum), **not** `portrait_swap` (no pixel
  transpose).
- **Sora native:** the `:114-118` keyframe **force-resize to landscape** must be
  fixed (apply `portrait_swap` or skip when portrait) or the portrait `size`
  fights a landscape-resized frame.
- **Runway:** fix `model="gen4"` **first** (separate commit), then wire ratios.

### §4.4 Bucket B — Kling (keyframe-inherits)
No payload change (no aspect param exists). Kling i2v inherits aspect from the
input keyframe. **Keyframe-provenance trace (load-bearing):** confirm a genuine
9:16 Phase-2 keyframe reaches `source_image` (`cinema/shots/controller.py:1405` →
`generate_ai_video`); add a defensive log/assert if the source image is landscape
while the project is portrait.

### §4.5 Portrait routing safety (the backstop — load-bearing)
The fallback cascade can silently route a portrait shot to a 16:9-locked provider
(LTX-fal/Seedance) which emits 16:9 **with no error**. Two coordinated defenses:
1. **Routing filter:** when `is_portrait(_aspect)`, exclude non-shipped providers
   (LTX-fal, Seedance, Hedra) from the `video_fallbacks` cascade.
2. **Post-generation aspect backstop:** after a clip is produced, probe its dims
   (`ffprobe`) and reject it if orientation ≠ the project aspect, converting a
   *wrong-orientation success* into a cascade advance. **Integration surface:** the
   cascade in `generate_ai_video` (`phase_c_ffmpeg.py`) — each provider returns its
   clip via `return result` on success (`:227/:266/:294`) or `try_next_api()` on
   failure. The success sites are currently **per-provider** (`return result` at
   `:227/:266/:294`), so the probe must run on **every** provider's success path —
   either at each `return result` or, preferably, via a **shared helper wrapping the
   returned clip** so no provider can bypass it (the plan picks the exact factoring,
   avoiding per-provider duplication). A wrong-orientation clip routes to
   `try_next_api()` (treated as a provider failure). **Terminal behavior (the reviewer-flagged gap):** if every shipped
   provider yields wrong orientation, the cascade **exhausts → `return None`
   (`:170`) → the caller (`cinema/shots/controller.py:1404`) reports "Video
   generation failed"** — the correct **fail-loud** outcome for a portrait project
   (never ship a landscape clip). The cascade is bounded by `fallback_list`
   (finite), so there is **no infinite-retry risk**; and the routing filter (item 1
   above) keeps only portrait-capable providers in the list, so
   exhaustion-by-wrong-orientation indicates a provider API regression — which
   *should* fail loudly. Catches **all** silent-landscape paths (Kling keyframe
   leak, Sora resize, any cascade fall-through). The scorecard remains the final
   backstop.

### §4.6 Sub-1080 upscale (decision #2 — Runway, and Sora if 720p)
Runway tops at 720:1280 / 768:1280; **Sora** native may return 720×1280 portrait if
`sora-2` lacks a 1080p portrait tier (U6). The assembly normalize
(`cinema_pipeline.py:1320`, scale filter `:45`) already scales-to-container →
1080×1920, so it covers **any** sub-1080 provider generically. Verify it upscales
correctly **for both Runway and Sora-720p**; add a test. Likely **no new code** —
this is the owning task for Acceptance Criterion #1's 1080×1920 guarantee on any
sub-1080 provider.

---

## 5. The Silent-Landscape Failure Mode (why §4.5 exists)

Three paths emit a 16:9 clip with **no exception**, so only an explicit aspect
check catches them:
1. **Kling** fed a 16:9 keyframe (i2v inherits aspect → silent 16:9).
2. **Sora** native `:114-118` force-resizing the keyframe to landscape.
3. The **cascade** dropping a portrait shot onto LTX-fal/Seedance (16:9-locked).

A 16:9 clip in a 1080×1920 container → letterbox/distort on normalize, **no
error surfaced**. §4.5's post-gen aspect backstop is the net; the per-provider
wiring is the primary fix.

---

## 6. Un-Gate Ordering Invariant (must be LAST)

**The edit:** append `"9:16"` to `cinema/aspect.py:23`. Single constant.

Appending it activates **4 already-wired surfaces** (verified):
1. **UI picker** — `/api/config` (`web_server.py:320`) emits the longer list →
   FE renders the second toggle (`web/src/components/settings/ProductionSection.tsx:148-162`).
2. **Settings-PUT persistence (linchpin)** — `api_update_project_settings`
   (`web_server.py:509`) rejects unsupported values; un-gating makes
   `is_supported("9:16")→True` so the value persists.
3. **Assembly container** — `cinema_pipeline.py:1367-1370` coerces unsupported →
   default today; un-gating lets 9:16 pass → `resolve_output_dimensions("9:16")=
   (1080,1920)`.
4. **Scorecard** — `cinema/capability_scorecard.py:96-98` grades the portrait format pass.

These serve **images + container + scorecard**. If the gate opens **before** the
video providers are aspect-aware, every portrait project regresses to
**landscape-in-portrait, with no error**. Therefore the un-gate is the **last**
task, gated on the §8 preflight PASS. No consumer *errors* on the flip (the dims
entry already exists); the risk is purely quality regression on ordering violation.

---

## 7. Out of Scope / Deferred

- **LTX:** native-only (`ltx-2-3-pro`), pod-validated before counting; FAL-LTX
  excluded from portrait routing (§4.5). Not in the ship/validation set.
- **Seedance:** excluded from portrait (dormant terminal fallback; aggregator
  endpoint unverified; 720p ceiling).
- **Hedra:** excluded (dormant in the default Veo+overlay route; lip-sync only).
- **`KLING_3_0` / `FAL_SVD`** (routing map, un-audited): pass no aspect. If
  portrait-reachable, commission an audit before wiring — **out of scope here**.
- **Spec §7-D supersession:** the prior spec's §7-D matrix
  (`2026-06-07-...-design.md` lines ~195-201, 5 rows) is corrected by §2 of this
  doc (adds Runway + Seedance; flips Sora and Kling to capable).

---

## 8. On-Pod Validation Preflight (decision #4)

`scripts/_phase3_portrait_preflight.py` (a `_`-prefixed dev harness, like the
existing `scripts/_*.py`):
- For each **shipped** provider (Veo, Sora, Kling, Runway), generate **one** live
  9:16 clip from a 9:16 keyframe.
- `ffprobe` the output; assert `height > width` (and ≥ target after upscale where
  applicable).
- **Image-keyframe enum smoke (operator CC-1 forward-carry SPEC-3):** also run a
  live FAL **schnell** generation to confirm `image_size="portrait_16_9"` is the
  correct enum — the Phase-2 unit tests assert the *mapping*, not API *acceptance*.
  Pairs with the on-pod 9:16 latent validation; cheap insurance against a portrait
  image-keyframe path that unit-tests-green but API-rejects.
- Print a **PASS/FAIL table**; exit non-zero on any FAIL.
- **Hard gate:** the §9-T10 un-gate commit is **blocked until PASS**; the table
  output is pasted into the un-gate commit body (ADR-013 evidence).
- Run by the user/operator (incurs live API spend; may need the GPU pod up for
  LTX-native checks — but LTX is deferred, so the ship preflight is Veo/Sora/
  Kling/Runway only).

---

## 9. Task Breakdown & Ordering (→ `writing-plans`)

One commit per task; tests fold into their task; the Runway model fix and the
un-gate are their **own** commits. ~10 sub-tasks → subagent-driven-development.

| T | Task | Acceptance |
|---|---|---|
| **T1** | `cinema/aspect.py`: add `runway_ratio(aspect, model)` + unit tests | both models × both orientations correct; 16:9 unchanged |
| **T2** | Threading spine: hoist `_aspect` + import helpers in `generate_ai_video` | `_aspect` available to all branches; 16:9 path byte-identical |
| **T3** | Veo wiring (native param + thread; fal `:491`) + tests; confirm fal enum spelling | 9:16 → Veo emits portrait; 16:9 refute test passes; new param additive/back-compat |
| **T4** | Sora wiring (fal `:423`; native dims + **`:114-118` resize fix**) + tests | 9:16 → portrait `size`/clip; landscape force-resize fixed; 16:9 refute test; **if `sora-2` returns 720p portrait, 1080×1920 is delivered via §4.6/T8 upscale** |
| **T5a** | **Runway `model="gen4"`→valid SDK model** (separate commit; grep installed SDK enum) | Runway gen4 route uses a valid model; no behavior change to aspect |
| **T5b** | Runway ratios via `runway_ratio` (`:363`, `:682`) + tests | 9:16 → 720:1280 / 768:1280; 16:9 refute test |
| **T6** | Kling keyframe-provenance trace + defensive assert + test | confirmed 9:16 keyframe reaches the call; landscape-keyframe-when-portrait logged/caught |
| **T7** | Portrait routing safety: cascade filter (`phase_c_ffmpeg.py:126-145`) + **post-gen aspect backstop** at the shared success boundary + tests | portrait cascade excludes LTX-fal/Seedance/Hedra; wrong-orientation clip → `try_next_api()`; **all-wrong → cascade exhausts → `None` (fail-loud), bounded (no infinite retry)**; test covers reject-retry + exhaustion paths |
| **T8** | Sub-1080 upscale verification (assembly normalize) — Runway **and** Sora-720p | 720/768-wide → 1080×1920 verified for both providers |
| **T9** | `scripts/_phase3_portrait_preflight.py` | PASS/FAIL table per shipped provider; exit code reflects result |
| **T10** | **Un-gate** — append `"9:16"` to `SUPPORTED_ASPECT_RATIOS` | **GATED on T9 PASS**; evidence in commit body; un-gate is the final commit |

**Ordering:** T1 → T2 → T3 → T4 → T5a → T5b → T6 → T7 → T8 → T9 → **T10 (last)**.
Pre-ship enum checks (decision #5) are verify-then-wire steps inside T3/T4.

---

## 10. Open Verification Items (pre-ship)

| # | Item | Status | Resolved by |
|---|---|---|---|
| U9 | ctx threads project aspect to motion | **RESOLVED — FALSE positive** (director spot-check: `cinema/shots/controller.py:496/1239/1376` pass project `global_settings`) | this spec §2 |
| U5 | fal veo3.1 `9:16` enum spelling | open | T3 verify-then-wire |
| U6 | Sora `sora-2` portrait 1080p tier (vs `sora-2-pro`) | open | T4 (accept+upscale if 720p) |
| U7 | Runway runtime accepts portrait `ratio` | open | T9 preflight (live) |
| U8 | `model="gen4"` actually fails today | superseded — fixing proactively (decision 6b) | T5a |
| U10 | a real 9:16 keyframe reaches the i2v call | open | T6 trace + T7 backstop |
| LTX | native `ltx-2-3-pro` 9:16; `LTX_API_KEY` in prod | deferred | post-ship pod-validate |
| SPEC-3 | schnell `image_size="portrait_16_9"` FAL enum (image keyframe) | open — operator CC-1 forward-carry | T9 preflight (live schnell smoke) |

No item resting on `unknown`/low-confidence is treated as `yes` in the ship; each
is closed in-task or by the preflight before T10.

**Opportunistic cleanups (operator CC-1 forward-carry INFO-1 / PLUMB-5):** if a
task touches `_inject_aspect` or the production swap sites, fold the cosmetic
cleanups then (INFO-1: `ins = node.get("inputs", {})` throwaway-dict fallback is
unreachable-but-harmless → cleaner `node.get("inputs")` + isinstance-continue;
PLUMB-5: production node-102/Pollinations hardcoded-1344×768 vs max-tier dynamic
node-read asymmetry — awareness only). **Not worth a standalone commit** on a
dormant path.

---

## 11. Acceptance Criteria (Phase-3 done)

1. A `9:16` project produces **1080×1920** video from Veo, Sora, Kling, Runway
   (Runway via upscale), verified by `ffprobe` in the §8 preflight (PASS table).
2. No silent landscape leak: §4.5 backstop rejects wrong-orientation clips; the
   portrait cascade excludes non-capable providers.
3. Every 16:9 wiring site has a **byte-identity refute test** (no landscape
   behavior change).
4. The un-gate is the **last** commit, gated on preflight PASS, evidence in body.
5. Full suite green; §15 smoke OK; ARCHITECTURE.md §8.x updated for the video
   aspect wiring (Lane D / same-PR doc-sync).

---

## 12. Risks

- **Ordering violation** (un-gate before wiring) → letterboxed portrait, no error.
  Mitigated by T10-last + preflight hard gate.
- **External enum drift** (fal/Sora API changes) → mitigated by verify-then-wire
  + the live preflight.
- **Cascade fall-through** to a 16:9 provider → mitigated by §4.5 (filter +
  post-gen backstop).
- **Public-API change** on `generate_video` signatures → additive optional params
  only (16:9 default); spec reviewer verifies back-compat.
