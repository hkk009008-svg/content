# Shot routing and provider policy

## Shot classification

`workflow_selector.classify_shot_type()` returns one of five shared classes.
Classification order is:

1. no characters -> `landscape`;
2. structured `[SHOT]` keywords;
3. full prompt and camera keywords; then
4. `medium` as the default.

| Type | Representative keywords |
| --- | --- |
| portrait | close-up, portrait, ECU, 85mm, macro, headshot |
| action | tracking, crane, dolly, chase, running, handheld |
| wide | wide, establishing, 24mm, full shot, master shot |
| landscape | aerial, drone, skyline, environment, no character |
| medium | medium, 50mm, waist, two-shot |

These classes set identity thresholds and seed the video candidate order. They
do not provide mutable local-image graph parameters.

## Current video order seed

`WORKFLOW_TEMPLATES` contains only `target_api`, `video_fallbacks`, and a
description:

| Shot | Primary seed | Fallback seed |
| --- | --- | --- |
| portrait | GEMINI_OMNI | VEO_NATIVE, KLING_3_0, RUNWAY_GEN4, SEEDANCE |
| medium | GEMINI_OMNI | VEO_NATIVE, KLING_3_0, RUNWAY_GEN4, SEEDANCE, LTX |
| wide | GEMINI_OMNI | VEO_NATIVE, LTX, KLING_3_0, RUNWAY_GEN4 |
| action | GEMINI_OMNI | VEO_NATIVE, SEEDANCE, KLING_3_0, RUNWAY_GEN4, LTX |
| landscape | GEMINI_OMNI | VEO_NATIVE, LTX, KLING_3_0 |

This table is a historical/order seed, not dispatch authority.
`get_resolved_workflow_routing()` delegates to `domain.video_engine_policy`,
which removes duplicates and rejects candidates based on current catalog
lifecycle, product support, runtime configuration, project enablement, and
date-sensitive policy. If none is admitted, it returns `AUTO` plus rejection
evidence rather than inventing an available engine. Provider-health filtering
is a later `phase_c_ffmpeg.py` step only for `AUTO` when durable cost authority
can supply analytics; it removes only deterministically `unhealthy` entries.

## Image backend selection

Image provider selection is separate from shot classification:

- `gemini_multiref` is the default selection. Gemini Image runs when its
  credential and approved character reference are available. A safely rejected
  result may continue through guarded local/cloud fallbacks.
- `local_flux2_klein` explicitly selects the local worker. It requires one to
  four approved references, a `ready` authenticated capability, and durable job
  authority. Any missing requirement blocks; it does not silently spend on a
  cloud replacement.

The local graph's four steps, scheduler, sampler, CFG, model files, and aspect
dimensions are immutable in `deploy/windows-flux2-klein/workflow.py`. Do not
add image parameters to `WORKFLOW_TEMPLATES`.

## Dialogue and performance axes

Dialogue video first uses an admitted native-audio candidate. Any result not
proven to contain embedded dialogue proceeds through the separate lip-sync
policy; lip-sync providers are not video-routing fallbacks.

Performance capture is also separate:

- dialogue plus face-readable framing -> Runway Act-Two by default;
- explicit `budget`/`cheap` performance signal -> local LivePortrait;
- action without dialogue -> Viggle when policy admits its `LIMITED` support;
- character-free or unsuitable wide/landscape framing -> skip.

Every real performance engine needs an operator-supplied driving video.

## Duration contracts

Duration must be validated against the selected engine before its network
call. Do not assume the requested scene duration is accepted unchanged.

- VEO_NATIVE accepts its fixed duration enum and snaps through its adapter.
- LTX accepts 6, 8, or 10 seconds and rejects unsupported values before I/O.
- SEEDANCE accepts bounded integer durations selected by shot policy.
- RUNWAY_GEN4 uses its fixed adapter contract.
- LivePortrait accepts a finite duration greater than zero and no more than
  eight seconds, at 25 fps/200 driving frames maximum.

Cost accounting must use the actual provider/model and actual dispatched
duration whenever available. Repository estimates are not invoice truth.

## Retry and recovery

Provider cascades may advance only after a definitively safe failure. A timeout,
ambiguous submit, accepted provider job, billed response awaiting validation,
or local prompt with unknown history must be recovered through its durable
attempt before any replacement is started.

Keep provider rejection evidence and actual-engine provenance with the shot.
Do not reduce routing to a blanket exception-driven `try_next` loop.
