# Reference-set rebuild — sequential plan

Written 2026-08-08. The durable record for a multi-phase build; read this before
resuming, and update it when a decision is made rather than at wrap-up.

## Why

This is a cinema pipeline: every still exists to become a shot. Video models
COPY identity from the references they are handed and do not invent it, so the
reference SET is the identity lever — not the single keyframe the pipeline was
built around.

Measured today, on the one real character:

- The record's `multi_angle_refs` held **2** paths while **10** usable images sat
  on disk. The downstream `[:4]` and `[:8]` slices never fired. The record was
  the bottleneck, not the caps.
- `VEO_NATIVE` receives **zero** references (`veo_native.py:381-392` passes
  `reference_images=None`; Vertex forbids image+reference_images together).
- Two slices sit below the capacity their own adjacent comments state:
  `phase_c_ffmpeg.py:2422` `[:8]` against "accepts up to 9";
  `phase_c_assembly.py:1095` `[:6]` against "up to 9 reference images".
- **Objects and locations reach no image or video provider at all.** Object
  metadata is serialised to TEXT by `llm/prompt_optimizer.py:768-779`;
  `get_location_reference` has zero non-test callers. Both have full upload APIs
  and a UI implying conditioning that does not exist.
- The identity scorer INVERTS RANK off-angle (ADR-092): a real photograph of the
  subject in profile scores 0.556 and fails the 0.70 gate, while a generated
  panel the subject confirmed is NOT him scored 0.570. Selection can never be
  score-driven, and no UI may present a score as a verdict for an off-angle
  reference.
- `_count_faces` (`character_manager.py:953`) has no minimum-area floor. On the
  subject's own 4032x3024 canonical it reports **2 faces** — a 58x58 speck,
  0.0276% of frame, detected at confidence 0.98 against the real face's 0.94.
  Four of ten images trip it. Character creation would reject the photograph
  that defines the character.

## Decisions taken (user, 2026-08-08)

1. Described characters are a FIRST-CLASS creation kind, alongside real ones.
2. Objects AND locations get full reference conditioning.
3. The full Reference Sheet page is built now, not deferred.

## Sequence

Each phase is independently useful and leaves the tree green. Do not start a
phase before the previous one's suite passes.

### Phase 0 — stop active harm

These lose quality or money today.

- **0.1** Area floor in `_count_faces`, `character_manager.py:953`. Currently
  rejects real single-subject photographs. Blocks every later phase because the
  sheet generator and the describe-first page both feed creation.
- **0.2** Delete the browser-side gate `score < 0.7`,
  `web/src/components/pipeline/ShotApprovalControls.tsx:19`. A fourth threshold
  that ignores `identity_strictness` and the shot-typed table (`wide` = 0.55),
  and post-ADR-092 it flags every turned shot. It recommends rejecting correct
  footage, and rejection costs a re-render.
- **0.3** Failure copy: "Gate cannot judge this pose — compared against
  <canonical>", with actions ordered Keep / Add this pose / Regenerate (priced,
  last).

### Phase 1 — take the capacity already documented

- **1.1** `phase_c_ffmpeg.py:2422` `[:8]` -> `[:9]`.
- **1.2** `phase_c_assembly.py:1095` `[:6]` -> `[:9]`.
- **1.3** Prepend the canonical once, at `domain/continuity_engine.py:463`, so
  every consumer agrees and slot 0 stops being load-bearing by accident
  (`phase_c_ffmpeg.py:2247` uploads `valid_refs[0]` as Kling's FRONTAL).
- **1.4** Deprioritise `VEO_NATIVE` in the cascade for identity-critical shots
  while its reference cap is zero.
- **1.5** Reconcile the Gemini cap: `gemini_image_native.py:33` allows 8 while
  the pinned flash tier documents 4 character references. Latent until the
  record was filled; live now.

### Phase 2 — the reference-set data model

- **2.1** `identity_refs: [{id, path, view, origin, roles[], judged, reason}]`.
  `view` from a closed set; `origin` in {photo, derived, invented} — derived
  means generated from a source that CONTAINED the requested geometry, invented
  means it did not. The distinction is the whole lesson of ADR-092.
- **2.2** Keep `canonical_reference` / `reference_images` / `multi_angle_refs`
  as DERIVED PROJECTIONS rewritten on every mutation. 71 read sites across 9
  files — deriving is free, deleting is not.
- **2.3** Migration inside `normalize_project_schema`
  (`domain/project_manager.py:848`), synthesising `identity_refs` from the three
  legacy fields with `view: unknown`.
- **2.4** A write route. Today NO character route writes `multi_angle_refs`
  (`web_server.py:2755` POST, `:3108` PUT, `:3250` DELETE) — there is no way
  through HTTP to add, remove, reorder, relabel or judge a reference.
- **2.5** Ordering contract: slot 0 = canonical/hero; then descending
  information gain; PHOTOGRAPHS before generated panels so that any consumer
  cutting at 4 sees only real images — `get_identity_reference_paths` stops at 4
  and a generated panel in slot 3 silently changed which set the Identity Lab
  would consent to.

### Phase 3 — creation kinds

- **3.1** `creation_kind` on the character record.
- **3.2** Text -> canonical generation. Three text-to-image paths exist
  (`phase_c_assembly.py:1184`, `:1212`, `gemini_image_native.py:146`) and none
  is reachable from character creation.
- **3.3** The 0.70 gate changes ROLE for described characters: it measures
  drift from panel 1, not fidelity to a real person.
- **3.4** Consent semantics. `web_identity_experiments.py:426` requires
  `lora_consent is True` and checks a reference COUNT, not provenance — a
  synthetic sheet would train a LoRA under consent asserted for nobody.
- **3.5** Sheet planner: the target provider's slot count decides the panel
  plan, and the ordering contract decides what survives truncation.

### Phase 4 — objects and locations

- **4.1** Objects: reference sets plus real provider wiring. A product needs
  hero / three-quarter L / three-quarter R / back / top / one detail per feature
  named in `texture_anchor` / one in-hand for `scale_reference`. A back panel is
  NEW information, unlike a back-of-head. Missing and not derivable from the
  record today: geometry class, symmetry, articulation.
- **4.2** Locations: a plate atlas — wide establishing, two complementary camera
  positions, one detail, one light-direction plate. Note `time_of_day` and
  `weather` live on Location and not Scene, so "same street, dawn and night"
  needs two records; and `make_location` assigns a fresh random seed with no way
  to pass one in (`project_manager.py:352`).

### Phase 5 — the UI

- **5.1** Delivery strip, read-only: one row per enabled engine, capacity
  server-supplied, struck-through thumbnails past each cut. Shows VEO_NATIVE at
  zero and the keyframe at one.
- **5.2** Reference Sheet page: coverage grid (rows = angle / expression /
  lighting, empty cells in the dashed-border grammar `CharacterPanel` already
  uses), per-reference KEEP/REJECT with reason, rejects moving to
  `characters/_quarantine/`.
- **5.3** Provenance instead of score on off-angle tiles: `PHOTO` /
  `DERIVED from <source>` / `INVENTED`, and where a number would go, the UNKNOWN
  pattern from `console/TakeStrip.tsx:56-67`.
- **5.4** Describe-first page, converging with upload on the same reference-set
  view.
- **5.5** Cost before the click, server-computed, following the precedent at
  `pipeline/ScreeningStage.tsx:662`.

## Provider routing (research 2026-08-08)

- Characters, keyframe: `gemini-3-pro-image` — 5 character references,
  provider-documented. Route by model ID; marketing aliases are unreliable.
- Characters, motion: Seedance reference-to-video. NEVER `VEO_NATIVE`.
- Products: `gemini-3-pro-image` (6 object references) or FLUX.2 [pro] edit.
  Motion route UNRESOLVED — fal's Kling v3 page states "Only 1 element is
  supported", contradicting a third-party figure of 3.
- Locations: fal Veo 3.1 reference-to-video is the one wired endpoint whose
  provider names *scene* as a reference class.
- Disqualified: Hunyuan (licence excludes South Korea). Local FLUX.2 Klein is
  the worst carrier for any plate — 4 slots and measured AVERAGING (1 ref 0.791,
  4 refs 0.499).

## Standing constraints

- No score-driven reference selection, ever. ADR-092.
- No UI element presenting an identity score as a verdict for an off-angle
  reference.
- Paid actions show their cost before the click and reserve through the durable
  paid-attempt ledger.
- Every phase ends with the full suite green and the generated-artifact checks
  at 0.
