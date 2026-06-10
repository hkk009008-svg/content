# SPEC P1-1 — Multi-character identity at GENERATION time

**Status:** REVIEWED (Session 3 of the STRATEGIC_REVIEW-2026-06-10 roadmap; adversarial
review `wf_a0a0a76a-9ff` — 76 claims checked, 48 findings folded; 1 reviewer finding
refuted with evidence, noted inline). **Operator cold Lane V folded** (4-lens workflow
`wf_c29cf61f-259`, report 2026-06-10T16:25:00Z, commit `7878d62`): 7 IMPORTANT +
5 MINOR + 3 INFO disposed in this revision — V-1/V-3/V-5/INFO-2 re-verified firsthand
at disposition time.
**Author:** director seat, 2026-06-10.
**Inputs:** 7-reader / 4-designer workflow `wf_69d94c15-fa6` (Sonnet subagents per the
standing user directive) + director firsthand verification of every load-bearing claim
in this doc. Claims carry file:line evidence; extrapolations are marked.
**Brief:** docs/STRATEGIC_REVIEW-2026-06-10.md:330 (roadmap row — "design doc
(mechanisms a/b/c costed, pod-dependence explicit) → reviewed → implementation plan")
+ :223-233 (the P1-1 strategy section with the "(b) first" recommendation).

---

## 0. Decision summary

The validator has been fully multi-character since `413317e`; generation still
conditions exactly one character per shot. **Scope boundary: multi-character identity
at MOTION time is already delivered** — `_validate_take_identity` passes the full
`chars_in_frame` list and `validate_shot` builds one config per registered character
(cinema/shots/controller.py:1027-1040; `413317e`). The gap this spec closes is
exclusively KEYFRAME-generation conditioning. This spec designs that in four parts: a
routing/accountability layer (d) plus three conditioning mechanisms (a/b/c), and
recommends a sequencing that **deviates from the strategic review's "(b) first where
LoRAs exist"** — because ground truth invalidated that premise (§2). Recommended:

- **Slice 1 (Session 4, pod-independent):** the identity-strategy router (d) +
  multi-character Kontext keyframes (a), gated by spike **S1** (~$0.20, no pod),
  plus the Aria LoRA registration (§7.3, ~10 min, pod-independent) **in parallel**.
  This upgrades the path that is actually live today (pod terminated → every
  keyframe goes through the FAL fallback) and makes generation *accountable*
  (promise metadata the validator/scorecard can hold it to).
- **Slice 2 (pod-gated):** max-tier dual identity — chained per-character LoRA
  (b, corrected to max tier) + dual ReActor rescue, then chained PuLID (c) behind
  VRAM spike **S2**. Requires a pod restart (user spend decision).

## 1. The asymmetry, verified

Detection is per-character; generation is first-character-only:

- `get_primary_character` returns `characters_in_frame[0]`
  (domain/continuity_engine.py:104-108; sole production caller :516).
- The shot controller picks ONE character's assets:
  `primary_char_id = shot.get("primary_character") or in_frame[0]`, then
  `char_lora_paths.get(primary_char_id)` / `char_lora_strengths.get(primary_char_id)`
  (cinema/shots/controller.py:544-549) — even though both settings dicts are
  per-character (written in lockstep at web_server.py:779-787).
- `generate_ai_broll`'s identity params are scalar by signature:
  `character_image=None, char_lora_path=None, char_lora_strength=None`
  (phase_c_assembly.py:75-81). The full `characters` list is accepted and forwarded
  to the max tier (phase_c_assembly.py:131) but never used for identity conditioning.
- The first-char convention is baked in at four layers that must stay in sync:
  shot model default (domain/models.py:94), scene decomposer writes
  `primary_character=char_ids[0]` at FOUR sites (domain/scene_decomposer.py:607,
  821, 864, 874 — :874 is a second shot in the same fallback template; any
  generalization must touch all four), controller fallback (controller.py:545), and
  `get_primary_character` itself.
- Characters at index 1+ receive only a text fragment — name + wardrobe + a spatial
  position hint that is pure list-index fiction (domain/continuity_engine.py:480-484:
  2-char shots get index 0 = "on the left side", 1 = "on the right side"; 3+-char
  shots get left/center/right by index; single-char shots get no hint — all
  regardless of actual choreography).
- Validation, by contrast, builds one config per registered character and
  aggregates per-character similarities (`413317e`; ContinuityEngine.validate_shot
  → IdentityValidator.validate_video). Characters without a registered reference
  are silently skipped (domain/continuity_engine.py:606-610) — generation-side
  conditioning must mirror that skip, never fail on it.

## 2. Ground-truth corrections to the strategic review (load-bearing)

Two premises in P1-1's brief (docs/STRATEGIC_REVIEW-2026-06-10.md:223-233) did not
survive verification:

**2.1 There is no "LoRA on the production tier."** Per-character LoRA enters the
pipeline at exactly one place: max-tier graph node 700 (LoraLoader) in
`pulid_max.json`, wired by `_inject_identity` (quality_max.py:461-506).
The production graph `pulid.json` has **zero** LoraLoader nodes (verified by JSON
inspection), and no FAL call anywhere passes a `loras` array (repo-wide grep: zero
hits). The "production tier + per-char LoRA" realism formula was demonstrated in a
standalone script — `scripts/_fal_lora_production.py:44-49` injects a LoraLoader
(node 777: 112→777→100.model, 11→777→122.clip) — but that pattern was never lifted
into the live path. Mechanism (b) is therefore **max-tier LoRA stacking**, not
production-tier.

**2.2 "Where LoRAs exist" is currently the empty set.** 16 of the 21 directories
under `domain/projects/` contain a `project.json`; zero of those 16 have a
`char_lora_paths` entry (verified by scan). The two trained artifacts
(`logs/char_lora_fal.safetensors`, `…_v2.safetensors`, fal-trained for
char_b9c8bcfe9af0 "Aria" in project cfd3f0967eb3, 2026-06-02) were never registered
through the web server's mutate path. A slice that conditions on registered LoRAs
has no characters to fire on until registration happens (§7.3).

**2.3 What IS true:** the Kontext plumbing claim is verified and precise.
`_fal_flux_fallback` already uploads a *list* (`image_urls`, capped `[:6]`,
phase_c_assembly.py:466-478) to `fal-ai/flux-pro/kontext/max/multi`
(phase_c_assembly.py:531-542) — but every ref in that list is an angle variant of
the *primary* character, and the prompt only ever addresses `@Image1`
(phase_c_assembly.py:489-529). The endpoint's multi-identity behavior is the spike
question (S1), not the plumbing.

**2.4 Today's live path is the FAL tier.** The pod is terminated (2026-06-10), so
production-tier keyframes route past the ComfyUI guard (phase_c_assembly.py:169)
straight to Kontext. Mechanism (a) upgrades the path current output actually uses;
(b)/(c) upgrade a path that resumes when a pod exists.

## 3. Mechanism designs

### 3(d) — The identity-strategy router + promise metadata (the symmetry layer)

A pure decision function `_resolve_identity_strategy(shot, quality_tier, settings,
cc)` in cinema/shots/controller.py — `shot` carries `characters_in_frame` +
`primary_character`; `cc` is the continuity_config dict; signature canon = the
implementation plan's (Lane-V V-7: an earlier draft listed a `project` param the
design never uses) — replacing the primary-only **asset derivation** at
controller.py:544-549 (`in_frame`, `primary_char_id`, `char_lora_path`,
`char_lora_strength`). `quality_tier` (:539)
and `style_reference` (:550-551) are inputs TO the resolver, not outputs of it —
they stay where they are. The router's justification is promise-metadata symmetry,
not detangling: the controller-side code is already a clean dict read
(`cc = enhanced.get("continuity_config", {})`, :511); the asset *resolution*
complexity lives upstream in `enhance_shot_prompt` and stays there. Returns an
`IdentityStrategy` (dataclass home: **new module `cinema/shots/strategy.py`** —
controller.py is already the repo's largest controller; the resolver function stays
in controller.py, the type does not):

- `mechanism_tag` — one of `PRIMARY_ONLY | KONTEXT_MULTI_CHAR |
  MAX_TIER_PRIMARY_ONLY | MAX_TIER_MULTI_LORA | MAX_TIER_DUAL_PULID |
  NO_IDENTITY_ASSET` (only tags whose mechanism is implemented are ever emitted);
- `conditioned_chars` — per-char spec: char_id, assets used (refs/LoRA/strength),
  promised fidelity class; `unconditioned_chars` — chars present with no usable
  assets (text-fragment only), so a low validator score on them is *expected*, not
  a generation failure;
- the existing primary fields (`primary_char_id`, `char_lora_path`,
  `char_lora_strength`) so the call into `generate_ai_broll` is unchanged for
  single-char shots — **zero-regression invariant: a single-char shot's strategy
  must reproduce today's exact asset bundle.**

Written to `take["metadata"]["identity_strategy"]` BEFORE generation; after the
result returns, `mechanism_actually_used` is **derived from `result.api_name` ×
the strategy** (Lane-V V-2): api_name alone is backend-granular
(`FLUX_KONTEXT`/`FLUX_PRO`/`QUALITY_MAX`) and cannot distinguish a multi-char
Kontext call from a primary-only one — record `FLUX_KONTEXT_MULTI_CHAR` when
api_name is `FLUX_KONTEXT` AND the strategy emitted secondary blocks, else the
raw api_name. The downgrade direction stays visible either way (the cascade
winner can differ from the promise — e.g. Kontext timeout → FLUX-Pro
no-face-lock). Honesty boundary: the derived value records what was EMITTED,
not what the server honored — a silent server-side `@Image2`-ignore is
undetectable in metadata by construction; S1 plus per-char validation exist to
catch exactly that. The controller call site at controller.py:643 passes
`secondary_char_refs=[c.to_dict() for c in strategy.secondary_specs] or None`
into `generate_ai_broll` — the POST-resolution, post-cap list (≤2 secondaries,
the Kontext-tier cap the router applies), NOT the raw `cc.get("secondary_chars")`
list, which would bypass the cap and could overflow the 6-ref budget on 3+-char
shots (the allocator does not re-cap). This wire-up is the load-bearing line that
makes (a) do anything at runtime; the kwarg is None-safe (no-op for single-char
shots). Post-generation keyframe validation
loops over `conditioned_chars` (today it scores only the primary,
controller.py:666-704) and writes `take["metadata"]["identity_per_char"]` — the
SAME key name the motion take uses (controller.py:1060-1066); keyframe and motion
takes are separate dicts, so there is no collision and the scorecard reads one
convention. The capability scorecard loop (cinema/capability_scorecard.py:141-148)
currently reads only the scalar `identity_score` (:144); slice 1 adds an
`identity_multi` sub-field at that same loop site. The scalar stays primary-only
in slice 1 for backward compatibility.

Retake note: the strategy resolves at GENERATION time, so takes of the same shot
may carry different mechanism tags if conditions change between takes (pod comes
up, LoRA gets registered) — progressive enhancement by design; the approved take's
strategy is what the scorecard surfaces. Known constraint: the Kontext call passes
no seed (phase_c_assembly.py:531-542 — no `seed` key), so retakes are
nondeterministic on this tier independent of the router.

This layer is what makes the program *symmetric*: the validator stops measuring
unkept un-promises. Pod-independent, no new spend paths, ~80-LOC helper + a
dataclass. All three mechanisms below plug into it.

### 3(a) — Multi-character Kontext keyframes (FAL tier; pod-independent)

Extend the already-plural `image_urls` to carry refs for up to 2 secondary
characters, addressed per-character in the prompt:

- domain/continuity_engine.py:548-575 — populate `continuity_config["secondary_chars"]`
  (char_id → canonical ref, multi-angle refs, identity_anchor) for
  `chars_in_frame[1:]` with a registered reference (same existence guard as primary).
- phase_c_assembly.py — `generate_ai_broll` and `_fal_flux_fallback` gain a
  `secondary_char_refs=None` kwarg (while touching the signature, audit whether
  `ctx` should also be forwarded into `_fal_flux_fallback` — `generate_ai_broll`
  accepts it, the fallback currently does not). **The single-char path is a
  structural early-return**: `if not secondary_char_refs: <existing code,
  untouched>` — byte-equivalence with today's prompt is guaranteed by construction,
  not by test assertion (review verdict: a unified 1-to-N code path cannot
  credibly promise byte-identity).
- For the multi-char branch: a slot allocator partitions the 6-ref budget with
  **FIXED shares and CONTIGUOUS slots** (primary 3 / secondary-1 2 /
  secondary-2 1; primary takes up to 6 only when no secondaries exist; thin
  secondaries leave the cap unfilled rather than reordering slots — the cap is
  a ceiling, not a quota; canon = the plan's Task-7 allocator, Lane-V V-7) and
  returns a `slot_map: {char_id: [@ImageN indices]}`. **Hard cap: 2 secondaries**
  — characters beyond the cap are moved to `unconditioned_chars` by the router
  (this is a Kontext-tier limit, recorded in the strategy metadata, not a general
  ceiling). The prompt builder emits one `PRESERVE IDENTITY: The person from
  @Image{N} is {identity_anchor}…` block per character plus a shared CONSTRAINTS
  block referencing all tokens.
- Existing prompt discipline holds: never pass raw character descriptions to
  Kontext (phase_c_assembly.py:447) — the per-char block uses the short
  `identity_anchor`, not trait dumps.
- Cascade interaction (corrected by Lane-V V-1; re-verified at disposition): the
  Kontext rewrite (`kontext_prompt`) is scoped INSIDE the Kontext try-block — on
  Kontext failure the FLUX-Pro fallback passes the **ORIGINAL `prompt`**
  (phase_c_assembly.py:557), so `@ImageN` tokens never reach FLUX-Pro today. The
  multi-char branch MUST preserve that: never forward the token-bearing
  multi-char prompt to the fallback (pinned by a provenance test, plan Task 8).
  Secondaries therefore degrade to today's text-only behavior on fallback —
  acceptable. Known asymmetry: the fallback passes `seed`
  (phase_c_assembly.py:560); the Kontext call passes none (the §3(d) retake
  note).

**Fidelity ceiling:** 2 (max 3) simultaneous characters; secondary identity is
reference-conditioned only (no LoRA on this tier) — expected GhostFaceNet ~0.45-0.60
on secondaries (extrapolated; thresholds at identity/types.py:95-101 — medium-shot
standard is 0.65), i.e. advisory-fail territory but above the text-only status quo
(S1 measures the actual gap — see its control-call design, §6). Primary fidelity
risk: the slot budget drops the primary from up to 6 angle refs to 3 on multi-char
shots.
**Failure containment:** if `@Image2` is ignored server-side, output degrades to
exactly today's behavior for secondaries — the call still succeeds.
**Effort:** 1.5-2 sessions including tests; ~100-150 LOC, all FAL-tier-contained.

### 3(b) — Per-character LoRA stacking (max tier; corrected scope)

Chain a second LoraLoader (node "701", then "702", cap 2 secondaries) after node
700 at runtime in `_inject_identity` (quality_max.py:461-506): node N+1 takes
`model/clip` from node N; final node feeds ApplyPulidFlux(100).model and
122/600.clip (the FaceDetailer-clip rewire at 600 must move to the last chained
node — missing it leaves FaceDetailer on char-A-only CLIP; node 600's clip is
`["700",1]` in the static JSON). Ordering fact that SIMPLIFIES the design:
`_prune_unavailable` runs at quality_max.py:863, BEFORE `_inject_identity`
(:877, retry :976), on a per-call deep copy — injected nodes never pre-exist in
the static JSON and are injected only when secondaries exist, so **no prune-rule
changes are needed**; LoraLoader is a core node present on any ComfyUI. The
injector simply does not inject for absent secondaries. (The first-draft "state
handoff" between injector and pruner is withdrawn — review caught that the call
order makes it unnecessary AND impossible as drafted.) Asymmetric case to design
for in slice 2 (Lane-V INFO-2; verified at disposition): when a SECONDARY has a
LoRA but the primary has none, there is no node 700 to chain from —
`_inject_identity` prunes 700 entirely on the LoRA-less-primary path
(quality_max.py:494) and rewires consumers to the base loaders (100.model←112,
122/600.clip←11, :495-500) — so node 701 must chain from 112 (model) / 11 (clip)
directly. Live the moment Aria registers and a pod exists.

- Controller side: collect `secondary_char_loras = [(cid, path, strength), …]` for
  all in-frame chars with a registered LoRA (controller.py:540-549 generalized).
- Trigger tokens — corrected provenance: the LOCAL training path writes
  `trigger_token` to `loras/<char_id>/dataset_manifest.json`
  (prep/lora_training.py:224); the FAL cloud path — which produced the only
  existing artifacts — writes NO manifest (no `loras/` directory exists anywhere;
  verified). Aria's trigger `TOKwoman` is hardcoded only in
  scripts/_fal_lora_production.py:25 and scripts/_fal_lora_train.py:28.
  Prerequisite fix: persist `global_settings.char_lora_triggers[cid]` at the same
  web_server.py:779-787 mutate that registers path/strength, accepting a manual
  value for FAL-trained LoRAs (nothing injects triggers at inference today —
  verified; injection becomes part of this mechanism's prompt assembly).
- Bleed risk: two face-LoRAs stacked on FLUX's global attention can cross-leak
  features. Mitigations: validated per-char strengths (the [0.45, 0.55, 0.7, 1.0]
  sweep argmax, prep/lora_quality.py:151), a stacking clamp (≤0.55 per secondary,
  spike-tuned in S3), and the per-char validator already catching bleed as a low
  secondary score.

**Fidelity ceiling:** secondary chars get LoRA-weight identity (~0.65-0.75
extrapolated from the single-char strength-sweep findings) but NOT a face anchor —
only one ApplyPulidFlux node exists; that is mechanism (c)'s territory.
**Pod-dependence:** hard to RUN (the graph executes on the pod), but ALL code +
unit tests (graph-surgery assertions on the JSON dict) ship pod-independently —
the branch is dead code until `quality_tier=="max"` AND a pod exists.
**Cost:** still one QUALITY_MAX unit ($0.40, cost_tracker.py:63); ~+5-10% pod
wall-clock per candidate (extrapolated).

### 3(c) — Max-tier dual identity: ReActor rescue now, chained PuLID behind a spike

Two fidelity passes, both pure Python graph surgery (no new custom nodes — the
2026-06-09 pod `/object_info` probe explicitly confirmed ReActorFaceSwap,
ApplyPulidFlux, and FaceDetailer among 1106 classes
(docs/HANDOFF-director-transplant-2026-06-09-max-tier-pod-validated.md:25); the
PuLID loaders were confirmed by the earlier 2026-05-29 probe. A NEW pod must
re-run the probe before relying on either):

- **Pass A (composable with (b)):** post-generation dual face swap — keep node 610
  (ReActorFaceSwap) for face index 0, inject node 611 consuming `["610",0]` with
  `input_faces_index="1"` (string — matching node 610's existing `"0"` schema;
  a review claim that this field is integer-typed was checked and is wrong) and a
  second source LoadImage (node 94, secondary canonical). ReActor's
  `input_faces_order: "left-right"` pairs with the same list-index convention the
  prompt's position hints use for 2-char shots (continuity_engine.py:480-484) —
  consistent for the 2-char case; the 3-char center position has no ReActor
  equivalent, and mis-ordered faces are a known failure mode the per-char
  validator catches.
- **Pass B (gated on spike S2):** a second ApplyPulidFlux (node 103) with its own
  face anchor — generation-time identity for both faces, approaching single-char
  max-tier fidelity for BOTH characters (single-char N=1 benchmark: arc 0.831).
  Three open questions gate it: whether PuLID-FLUX attention patches compose
  additively across chained nodes; VRAM headroom on the 48 GB card under N=8 +
  SUPIR (current peak unmeasured); and the INSERTION POINT — the static chain
  100→301→770→772→740→22 is partially pruned for FLUX compatibility at runtime
  (quality_max.py:412-428 drops 301/770/772/740), and injection runs after pruning
  (:863 → :877), so node 103 must be wired against the POST-prune graph (feeding
  the surviving downstream consumer, e.g. BasicGuider 22) — exact wiring resolved
  in S2. Optional regional refinement: `ConditioningSetAreaPercentage` (core
  ComfyUI node, no install) to spatially scope each identity — effect on a
  PuLID-patched FLUX graph is architecturally uncertain; visual smoke test on the
  pod.

**Pod-dependence:** to RUN — hard, both passes; the spikes need a live pod.
Pass A's CODE (graph surgery + unit tests) ships pod-independently, same as (b).
**Cost:** ~$0.44-0.51/shot — **extrapolation**: QUALITY_MAX $0.40 + 10-27%
dual-identity overhead. N=8 wall-clock has never been measured (the 8.5-min
benchmark in the 2026-06-09 handoff was N=1) — the overhead percentage is an
estimate on top of an estimate; treat as an order-of-magnitude figure and add a
`QUALITY_MAX_MULTI` cost entry when Pass B ships rather than silently
under-counting (§4). **Effort:** ~3 sessions total (1 offline code+tests, 1 pod
spike session, 1 regional/polish) — the natural Slice 2/3.

## 4. Cost model

| Item | Estimate | Basis |
|---|---|---|
| Kontext multi-char keyframe | $0.04/call | cost_tracker.py:59 `FLUX_KONTEXT` — repo estimate; per-input-image surcharge **unverified**. If FAL bills per ref, today's single-char 6-ref calls are ALSO mispriced against this entry (and the multi-char slot cap of 3 primary refs could even lower single-call cost). S1 reads the real price off the FAL dashboard; update `FLUX_KONTEXT` after S1 regardless of the spike's go/no-go. Multi logs under the same key as single — the record site is controller.py:744-751, keyed by `result.api_name` (cite corrected per Lane-V M-2; phase_c_assembly.py:546 is where the `FLUX_KONTEXT` name originates, not where cost is logged). |
| Max-tier multi-LoRA shot | $0.40/shot | cost_tracker.py:63 `QUALITY_MAX`; same pod call, no new billing unit |
| Max-tier dual-PuLID shot | ~$0.44-0.51/shot | **extrapolation**: QUALITY_MAX $0.40 + 10-27% overhead; N=8 timing unmeasured (the 8.5-min benchmark was N=1) — add `QUALITY_MAX_MULTI` ≈ $0.50 to API_COST_USD when Pass B ships |
| Spike S1 (@Image2 behavior) | ~$0.20 | 5 calls @ ~$0.04: single-char baseline + 3 multi-char arms on the Kontext endpoint (N=3 variance design per Lane-V V-4, §6) + 1 text-only control on `fal-ai/flux-pro/v1.1-ultra`, whose price may differ; contingent on flat-rate pricing — the same unverified assumption the row above flags |
| Spike S2/S3 pod session | ~$0.50-1.20 | **assumes 1-4 h total billed pod uptime** (spin-up + development + idle + N=1 runs @ $0.30/hr) — generation cycles alone would be ~$0.36; the range prices the session, not the renders |
| LoRA training (prereq) | **uninstrumented** | zero API_COST_USD entry / record_api_call anywhere under prep/ (verified) — must be priced before slice 2 makes training routine |

Budget-gate note: keyframe spend is *tracked* (record_api_call at controller.py:746)
but *ungated* (no `would_exceed` in `generate_keyframe_take`; the operator's K8
coverage map already records this — director backlog). Mechanism (a) adds no new
spend path (same single Kontext call), so it inherits, not worsens, that gap; the
gap itself stays on the ADR-022 budget-coverage backlog item, not in this spec's
scope.

## 5. Pod-dependence matrix

| Component | Pod needed to ship code? | Pod needed to run? |
|---|---|---|
| (d) router + promise metadata | no | no |
| (a) Kontext multi-char | no | no (FAL) |
| (b) LoRA stacking | no (unit-testable graph surgery) | yes (max tier) |
| (c) Pass A dual ReActor | no (same) | yes |
| (c) Pass B chained PuLID | spike S2 first | yes |
| S1 spike | no | no |
| S2/S3 spikes | — | yes (user spend decision) |

## 6. Spikes, with go/no-go criteria

- **S1 — Kontext multi-identity behavior** (gates (a); no pod; ~$0.20; run
  BEFORE slice-1 implementation commits to the prompt-per-char design). Script
  (`scripts/_test_kontext_multi_char.py`), five calls sharing one scene prompt:
  (1) single-char baseline (primary only — today's shape); (2) **text-only
  control** (both characters described, no secondary ref) to measure the floor the
  mechanism must beat; (3-5) **three identical two-char calls** with both faces in
  `image_urls` + `@Image1`/`@Image2` blocks — N=3 on the multi arms because this
  tier is unseeded (§3(d) retake note) and N=1-2 can NO-GO on output variance
  alone (Lane-V V-4); the verdict is per-arm, decided by **majority (≥2/3)**.
  Score every output face with the shared GhostFaceNet validator. **Go (per
  arm):** secondary ≥ (text-only control + 0.10) AND secondary ≥ **0.45** — the
  absolute floor at the bottom of §3(a)'s projected 0.45-0.60 band (numerically
  the wide-shot lenient threshold, identity/types.py:98). The per-shot-type
  lenient threshold (0.55 for medium, :97) sits INSIDE the projected band and
  would false-veto a real reference-grade lift (Lane-V V-3), so it is recorded
  as ADVISORY context with the result, not gated on — slice 2 is what raises
  the fidelity ceiling to production thresholds. AND primary within 0.05 of its
  single-char baseline. **Blend signal = no-go:** both faces of the same arm
  scoring in the 0.40-0.50 band (faces averaged rather than separated). The
  blend check deliberately OVERRIDES the floor in the [0.45, 0.50) overlap
  zone: a secondary there is GO only if the primary sits outside the blend
  band — when both faces land in it, the apparent lift is an averaging
  artifact, not identity transfer. **Power
  limit, acknowledged (V-4):** N=3 distinguishes separation-vs-blend, not fine
  threshold effects — record the per-arm spread alongside the verdict. On no-go,
  (a) reduces to interleaved-refs-without-addressing; re-scope slice 1 to router
  (d) + per-char validation only, and record the finding. Also read the actual
  multi-call price off the FAL dashboard while there.

  **S1 RESULT (run 2026-06-10, user-approved; AC5 record):** pair = Aria
  canonical (cfd3f0967eb3, @Image1/left) + 정연 canonical (bf1a4e9e8a9a,
  @Image2/right); scene "a quiet rooftop cafe at dusk", medium two-shot;
  outputs + crops in `logs/s1_kontext_multichar/`.
  - *Pass 1 (full-frame, scripts/_test_kontext_multi_char.py --live):*
    baseline a=0.549 b=0.488 · control a=0.646 b=0.522 · multi a/b/c
    secondary spread [0.574, 0.555, 0.505], |a-base| ≤ 0.031, blend=False ×3
    → **NO-GO 0/3** (go bar = control+0.10 = 0.622).
  - *Pass 2 (per-face half-crops, scripts/_s1_rescore_crops.py — required
    correction: §6 says score every FACE; pass 1 scored every IMAGE, validator
    face-pick undetermined):* baseline L/a=0.680 R/b=0.610 · control
    L/a=0.671 R/b=0.483 · multi R/b = [0.518, 0.550, 0.545], blend=False ×3
    → **NO-GO 0/3** (bar 0.583).
  - *Measurement-validity analysis — the criteria, not the mechanism, failed:*
    (i) control-anchor saturation: the descriptive anchors (hair color/style,
    ethnicity, lips) let TEXT-ONLY generation score 0.671 vs Aria's ref —
    within 0.01 of the baseline that HAD her photo — so "control+0.10" was
    unreachable for metric, not mechanism, reasons; (ii) embedding domain-gap:
    the baseline (no @Image2 at all) scored HIGHER vs 정연's ref (0.610) than
    every conditioned arm (≤0.550), and cross-terms exceed diagonals
    (right-side faces ~0.67 vs ARIA's ref in all images) — at dim two-shot
    face scale GhostFaceNet tracks image statistics, not identity.
  - *Qualitative result on the blocking question (visual inspection, all five
    outputs):* @Image2 is HONORED — all three multi arms render two distinct,
    recognizable identities (정연's bangs/red lips/earring; Aria's hair/face);
    **zero blending** (consistent with blend=False ×3 and |a-base| ≤ 0.035).
    NEW failure mode found: **wardrobe cross-bleed** — multi_b put 정연's
    reference cheongsam on BOTH characters; the Task-7 prompt builder should
    add a keep-own-clothing constraint line (recorded as an implementation
    note, not a gate).
  - *Disposition (director, surfaced to the user-principal in-session):* the
    no-go path's premise ("@Image2 ignored → reduces to
    interleaved-refs-without-addressing") is CONTRADICTED by the evidence;
    blend signal — the explicit no-go trigger — is absent. **Proceed with
    (d)+(a) including Tasks 7–8**, with secondaries remaining advisory-fail
    territory exactly as §3(a) already projects, and the quantitative
    per-char lift recorded as UNMEASURED at two-shot scale (the same limit
    applies to the production per-char validator — identity_per_char stays
    advisory, never gating, which §3(d) already specifies). Per-input-image
    FAL pricing: still unverified — needs a dashboard read (no CLI access).
- **S2 — dual-PuLID VRAM + composition** (gates (c) Pass B; pod). Measure peak
  VRAM of the current single-char N=8+SUPIR run first (never measured), then inject
  node 103 at N=1 against the post-prune graph (§3(c)). **Go:** no OOM at N=4+ and
  both arc scores >0.70.
- **S3 — multi-LoRA stacking strengths** (tunes (b); pod; needs ≥2 registered
  LoRAs). Sweep stacked strengths (primary at validated, secondary ∈ {0.35, 0.45,
  0.55}); watch for bleed (cross-character feature leakage shows as paired score
  collapse).

## 7. Recommended sequencing — and the deviation, surfaced

**7.1 Slice 1 (Session 4): (d) + (a), S1 first, §7.3 in parallel.** Rationale: it
conditions the tier that generates every keyframe TODAY (pod down), needs no spend
decision beyond ~$0.20, establishes the promise/accountability schema all later
mechanisms reuse, and is the only slice whose acceptance can be demonstrated
end-to-end this week. ~2 sessions including S1.

The steelmanned alternative — register Aria's LoRA and polish single-char max-tier
first — was weighed: registration is indeed pod-independent and takes minutes
(which is why §7.3 moves INTO slice 1), but everything it unblocks beyond
registration itself (max-tier LoRA rendering, fidelity measurement) waits on a pod,
and (a)+(d) deliver multi-char capability on the live path in the same session.
The honest trade: slice 1's secondary-character fidelity is reference-grade
(advisory-fail territory, §3(a)) until slice 2's LoRA/PuLID work raises the
ceiling — S1's control-call design exists precisely to prove the reference-grade
lift is real before we build on it.

**7.2 Slice 2 (pod-gated): (b) + (c) Pass A code-complete offline; S2/S3 in the
next pod session; Pass B if S2 passes.** Bundle the spikes into ONE pod session
with the P1-2 over-cook investigation if the user green-lights pod spend (shared
spin-up cost).

**7.3 Prerequisite, folded into slice 1 (~10 min, pod-independent):** register the
existing Aria LoRA — `logs/char_lora_fal_v2.safetensors` → `char_lora_paths` via
the established mutate shape (web_server.py:779-787). Two corrections from review:
(i) **no machine-readable validated strength exists** — the v2 sweep covered only
{0.55, 0.70} in `logs/_test_v2_sweep.log` plus 0.65 in `logs/_test_v2_s065.log`
(evidence split across files, Lane-V M-1), never the full
[0.45, 0.55, 0.7, 1.0] sweep, and no argmax/best_strength was persisted anywhere;
registration must supply the strength MANUALLY (0.55, the best performer of the
partial sweep and the 2026-06-02 finding) or `char_lora_strengths` stays unset.
(ii) the trigger token must also be supplied manually (`TOKwoman`,
scripts/_fal_lora_production.py:25) into the new `char_lora_triggers` — there is
no manifest to read for FAL-trained LoRAs (§3(b)). Value: with zero registered
LoRAs, every LoRA-conditioned branch in (b)/(c) — and today's *single-char*
max-tier LoRA path — has an empty target set; registration makes them exercisable
the moment a pod exists. (Registration benefits the MAX tier; it is unrelated to
the production-graph PuLID bug recorded in §9.)

**Deviation from the strategic review:** its recommendation — "implement (b) first
where LoRAs exist" — rested on the production-tier-LoRA premise (false, §2.1) and
on registered LoRAs existing (none do, §2.2), and lands entirely behind a
terminated pod. Per the PROGRAM-MANUAL full-capability directive this spec
surfaces the reorder rather than silently following the stale brief: **(a)+(d)
deliver capability on the live path now; (b)+(c) follow when the pod does.** If
the user prefers pod-first (e.g. a pod session is imminent anyway), slice order
inverts cleanly — the router (d) is first in either ordering.

## 8. Acceptance criteria

Slice 1 (per the §15 smoke + suite discipline; all tests green throughout):
1. Single-char shots: identical asset bundle and prompt. Enforced structurally
   (the multi-char branch early-returns when `secondary_char_refs` is empty,
   §3(a)) AND by a golden-file snapshot of today's single-char Kontext prompt
   **captured BEFORE the refactor** (no prompt-snapshot mechanism exists in the
   suite today — the capture step is part of the slice, not an afterthought).
2. Two-char shot, both with refs, FAL tier: `image_urls` carries both characters'
   refs per the slot map; prompt addresses each via its own `@ImageN` block;
   `identity_strategy.mechanism_tag == "KONTEXT_MULTI_CHAR"`.
3. `identity_per_char` written on keyframe takes for every conditioned char;
   unconditioned chars unscored (no false-fails); scorecard surfaces
   `identity_multi`. Single-char shots: `identity_per_char == {primary:
   identity_score}` — the scalar convention is pinned unchanged (Lane-V INFO-3).
4. `mechanism_actually_used` reflects the cascade winner on fallback AND
   distinguishes multi-char from primary-only emission on a successful Kontext
   call (derived api_name × strategy, §3(d); Lane-V V-2).
5. S1 result recorded in the spec/ADR with the measured scores, whichever way it
   goes.
6. Existing tests named for extension: `test_phase_c_assembly_provenance.py`
   (calls `_fal_flux_fallback` with the current signature — extend for the new
   kwarg; the extension is an explicit plan Task-8 step covering the V-1
   fallback-keeps-original-prompt pin, per Lane-V V-6), `test_continuity_engine.py` (continuity_config gains
   `secondary_chars`), `test_capability_scorecard.py` (`identity_multi`), plus new
   strategy-resolver tests over the decision matrix (in_frame × tier × asset
   availability).

Slice 2 adds: graph-surgery unit tests for 701/702/611/103 injection (Rule #13
audit across the post-prune wiring), live two-char pod render with both arc scores
>0.70 (Pass B) or secondary >0.60 (Pass A), no OOM at the shipped N.

## 9. Adjacent debts surfaced by this work (recorded, NOT in scope)

- **Production `pulid.json` runs SDXL-generation PuLID on a FLUX UNet** — node 112
  loads `FLUX1/flux1-dev-fp8.safetensors` while node 99/100 load
  `ip-adapter_pulid_sdxl_fp16.safetensors` via legacy `ApplyPulid` (verified by
  JSON inspection; max tier correctly uses `ApplyPulidFlux`). Latent quality bug on
  the pod production path; candidate for ARCHITECTURE.md §16 + a fix ticket.
- **Lipsync is single-face**: `generate_lip_sync_video(character_image_path, …)`
  (lip_sync.py:705-733) is called with the primary ref only (controller.py:1562).
  In a two-character dialogue shot the secondary's face is never synced — out of
  this spec's scope; a follow-on when multi-char dialogue shots become routine.
- Scorecard's identity dimension reads the keyframe's single-char score even though
  motion takes carry `identity_per_char` since `413317e` (slice 1 partially fixes
  the keyframe side; the scorecard scalar swap is follow-up).
- `pipeline_status.toml::multi_identity_validation = stubbed` is accurate for the
  zero-caller legacy helper it anchors, but its NOTE mischaracterizes the live
  path as "single-char validate_shot" — validate_shot has been multi-char since
  `413317e`. Fix the note, not the status.
- LoRA training has zero cost instrumentation (§4); audio/performance modules'
  throwaway `CostTracker()` instances bypass the budget accumulator (already on the
  director backlog as the ADR-022 budget-coverage item).
- `prompt_optimizer` builds `identity_anchor` from `characters[0]` only
  (llm/prompt_optimizer.py:227-230) — the optimizer sees all chars but anchors one.
- auto_approve `motion_min_identity`: the scorecard reads 0.85 from
  AutoApproveConfig in normal execution; the 0.6 appears only in the
  exception-path fallback (capability_scorecard.py except-block) — the risk is a
  *silent downgrade under unexpected exceptions*, not a live divergence.

## 10. Questions for the user-principal

1. **Slice-1 go:** approve S1 (~$0.20 FAL spend, 5 calls with the N=3 variance
   design) + the (d)+(a) implementation + Aria registration as Session 4? (§7.1;
   the review's (b)-first order is not executable as written. S1's go/no-go
   criteria were revised per operator Lane-V V-3/V-4 BEFORE this ask was put to
   you — the go-floor now sits at the absolute bottom (0.45) of the projected
   0.45-0.60 band rather than inside it at 0.55, eliminating the false-veto bias
   for real lifts in 0.45-0.55, and the verdict is majority-of-3 rather than
   all-of-1-2.)
2. **Pod session:** green-light a pod restart for S2/S3 (~$0.50-1.20, assumes 1-4 h
   uptime), ideally bundled with the P1-2 over-cook spike?

---
*Last verified: 2026-06-11 (director disposition session). Drafted against HEAD `17ecf59`;
review pass `wf_a0a0a76a-9ff` (76 claims checked) folded against HEAD `fa3bf8c`
(delta from 17ecf59 touches only the doc verifier + its tests, no production code).
Operator cold Lane V (`wf_c29cf61f-259`, 16:25:00Z report) disposed 2026-06-11:
V-1..V-7 + M-1/M-2 + INFO-2/INFO-3 folded here, V-5/V-6 + M-3/M-4/M-5 in the plan;
INFO-1 was already recorded in §9. V-1/V-3/V-5/INFO-2 cites re-verified firsthand
against HEAD `008787d` at disposition time.
Implementation plan: docs/superpowers/plans/2026-06-10-p1-1-slice1-router-kontext-multichar.md.*
