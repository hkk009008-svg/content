# SPEC — Pass B Multi-character Direction (Post-S2/S3 Redirect)

**Status: DRAFT — pending director review + user pod/spend authorization**

**Author:** operator-seat subagent, 2026-06-12 (cold read from spec §6 + runbook
exit record + code firsthand). Not yet Lane-V'd.

**Purpose:** Define the direction for the next pod session (Pass B) after the
2026-06-11 pod arc closed with S2 CONDITIONAL-GO (binding uncontrolled) and S3
BLEED-at-all-strengths. Provides a concrete design for attention-masked
dual-PuLID (Design A), per-face identity binding (Design B), and per-face
best-of-N + ReActor swap rescue (Design C), plus a RUNBOOK-style spike protocol
with offline-first sequencing and explicit GO/NO-GO criteria.

**Primary inputs (all firsthand-read this session):**
- `docs/SPEC-P1-1-multichar-generation-identity-2026-06-10.md` §3, §6 (authoritative
  numbers and verdicts)
- `docs/RUNBOOK-pod-session-p1-1-s2-2026-06-11.md` (session structure + exit record)
- `DECISIONS.md` ADR-023 (per-shot-class halt_rule)
- `git show dc5ad2b` (best-face fix — operator Lane V ✅ SAFE `2026-06-11T18:49:37Z`; dispositions in SPEC-P1-1 §3(d))
- `pulid_max.json` (graph structure verified by node inspection)
- `scripts/_max_s2_dual_pulid.py` (S2 dual-PuLID wiring used)
- `scripts/_max_s3_stack_sweep.py` (S3 sweep wiring)
- `identity/validator.py` (validate_image + _analyze_frame current state)
- `cinema/shots/controller.py:808-816` (per-char scoring loop post-slice-2)
- `.claude/skills/comfyui-mastery/nodes-face-identity.md` (ApplyPulidAdvanced schema)

---

## 1. Verdict recap — authoritative numbers + artifact citations

Source for all numbers: `docs/SPEC-P1-1-multichar-generation-identity-2026-06-10.md`
§6 "Pod-session results record (2026-06-11)". The runbook exit record
(`docs/RUNBOOK-pod-session-p1-1-s2-2026-06-11.md` §Exit record) is the pointer;
§6 is the truth. Artifacts exist on-disk as cited; do not re-derive numbers from
images.

### Pass-A (Phase 3) — GREEN

Re-run after root-cause fix `945d022` (shot_hint `or {}` replacement; landscape
misclassification zeroed identity conditioning). Production dispatch, `medium`
class, N_max=8, halt@composite=0.90/arc=0.83, fp8.

- Best arc across 8 candidates: **0.819** (at or above 0.80 regen floor; no
  boost retry needed).
- `ImageGenResult(api_name='QUALITY_MAX')`.
- Accepted artifact: `logs/pass_a_multichar.jpg` (coherent/photoreal-leaning).
  Failed landscape artifact preserved: `logs/pass_a_multichar_FAILED_landscape_20260610.jpg`.
- All 8 candidates: `logs/pass_a_multichar_cand0.jpg` through `cand7.jpg`.
- **Open finding (carried):** the accepted artifact's secondary (man) scores
  **0.487** on a **half-crop** validate_image call (his half-crop score vs his
  ref; the full-image score is **0.597**, per SPEC-P1-1 §3 line 187 — the
  difference reflects the co-star face pollution that dc5ad2b's best-face fix
  addresses for the full-image path). The ReActor swap targeting/blend under a
  coherent base is the source of Design C below. The FAILED landscape artifact's
  man-half scored >=0.70 (both halves), confirming the swap CAN deliver; the
  coherent-base execution does not always target the right face.

### S2 — dual-PuLID: VRAM GO / identity CONDITIONAL

Script: `scripts/_max_s2_dual_pulid.py`. Graph wiring: node 103 (`ApplyPulidFlux`)
spliced between node 100 and its surviving post-prune consumer; nodes 99/101/97
(loaders) shared; node 95 (`LoadImage`) carries man ref. Both weights 0.85.
Seeds: 990011/990022/990033/990044. Prompt: "a woman with short dark wavy hair
on the left and a middle-aged man with a grey beard on the right…" (medium two-shot).

- VRAM peak: **41.8 GiB** (vs single-char baseline **41.4 GiB = +0.4 GiB delta**;
  baseline recorded at session wrap `f25af7c`). No OOM across all 4 renders.
- Identity results (per §6, full-image validate_image on saved artifacts):
  - n1: both figures render female (operator visual per SPEC-P1-1 §6
    correction block); man-read **0.641** on the full image. This seed does NOT
    support "identities materialize"; it weakens the 2/4 identity read and
    STRENGTHENS the binding-uncontrolled verdict. (Artifacts:
    `logs/s2_dual_n1.jpg`–`n4.jpg` exist.)
  - n2: Aria-duplication (both halves ~0.73 Aria). GO criterion failed.
  - n3 (best): L:man **0.832** / R:Aria **0.773**. Both >=0.70. GO criterion
    met for VRAM. BUT: the man's GEOMETRY (scored 0.832) sat on the LEFT
    (beardless figure), the beard followed the text prompt to the RIGHT figure
    which scored Aria-side (0.773). **Identity↔figure binding UNCONTROLLED.**
  - n4: near-miss (**0.672** — correction-block value; main record says 0.670).
- Summary: both-arc >=0.70 in **2/4 seeds**.
- Metric calibration (firsthand, §6): Aria-ref↔man-ref cross floor **0.447**,
  self **1.000**. The >=0.70 signal is real (geometry reads above random cross);
  the metric CANNOT distinguish which face a score belongs to without spatial
  isolation.
- **Verdict: VRAM-GO, identity CONDITIONAL-GO. Pass B direction: dual-PuLID
  is feasible (cheap VRAM overhead), but production use requires spatial binding
  (Design A: attn_mask) or per-face selection + swap rescue (Design C).**

### S3 — multi-LoRA stacking: BLEED at all strengths (visual verdict overrides)

Script: `scripts/_max_s3_stack_sweep.py`. Primary: Aria LoRA 0.55 + PuLID anchor.
Secondary: `char_lora_man_v1` (FAL-trained this session, trigger TOKman, 6 refs
painterly-lineage, 2500 steps) swept at {0.35, 0.45, 0.55}. Fixed seed 880221.

- All 3 arms render **two women** — Aria's trained wardrobe on both figures, no
  beard, "grey beard" token present as neck-texture artifact.
- Artifact citations: `logs/s3_stack_sec35.jpg`, `s3_stack_sec45.jpg`,
  `s3_stack_sec55.jpg`.
- Embedding traces of the man's geometry exist (sec45 L scored **0.828** vs
  man's ref) but the **visual identity is unusable**: two-women homogenization
  is unambiguous, embedding metric would have FALSE-GO'd.
- **Finding: a pure-LoRA secondary (<=0.55, the §3b clamp) under a
  PuLID-anchored primary CANNOT hold a distinct visual identity.** LoRA-only
  secondaries are dead as an identity mechanism in this configuration.
- Caveats: man LoRA trained on painterly-lineage specimens (6 refs, 2500 steps);
  single seed per arm. A photoreal man LoRA with more refs may reduce bleed —
  UNVERIFIED, and testing this is lower priority than the PuLID-binding path.
- **Consequence for the production formula:** LoRAs remain in the pipeline for
  REALISM (the single-char Aria proof: arc 0.880 live, photoreal, §6 Phase 2
  record). LoRAs cannot replace PuLID/faceswap support for secondaries.

### Supporting calibration artifacts (cited, not re-derived)

- Man LoRA training log: `logs/man_lora_train.log`; artifact: `logs/char_lora_man_v1.safetensors`
  (pod-placed, also registered).
- Man reference images (training lineage): `logs/man_lora_refs/`.
- FAL training spend: $5.40 (1st run) + user-funded 2nd run (total UNVERIFIED;
  FAL $0.08/img confirmed for inference but training rate is ESTIMATED at
  ~$2/1000 steps — no in-repo log/invoice artifact backs this; treat as ESTIMATE
  until a further training run pins it with logged cost per SPEC-P1-1 §6
  correction block).

---

## 2. Design A — attention-masked dual-PuLID

### 2.1 Node-level mechanism

The current S2 dual-chain (nodes 100 + 103, both `ApplyPulidFlux`) injects
identity patches into the global attention of the FLUX UNet without spatial
constraint. Both nodes share the same loaders (99/101/97). The result:
identities materialize but can land on either figure.

The `ApplyPulidAdvanced` node (documented in
`.claude/skills/comfyui-mastery/nodes-face-identity.md:56-68`) exposes an
`attn_mask` input (type MASK, optional) that scopes the identity patch to a
spatial region. **This is the documented escape hatch for the binding failure.**

Key distinction: `ApplyPulidAdvanced` is possibly SDXL-era (`ApplyPulid`'s
advanced sibling) — **UNKNOWN until the pod `/object_info` probe** (the skill doc
gives no explicit architecture split); the production graph uses `ApplyPulidFlux`
(FLUX-native, node 100). The skill's comparison table (`nodes-face-identity.md:350`) lists
"Multi-face: Single" for PuLID — this refers to `ApplyPulidFlux`. The advanced
node with attn_mask has a different class name. **UNKNOWN: whether the installed
comfyui-pulid custom node on the Novita pod exposes `ApplyPulidAdvanced` with an
`attn_mask` input for FLUX, or only for SDXL. This must be verified via
`/object_info` before any Pass B graph surgery.** The 2026-06-11 census counted
44 of 48 expected classes; `ApplyPulidAdvanced` was not listed in the 4 absent
classes per the operator handoff — but the census did not explicitly enumerate
each class against a named expected list, so its presence is UNVERIFIED.

### 2.2 Mask generation plan

A spatial mask needs a face bounding box in the generated-frame coordinate space.
Two possible sources:

**Option 1 — Keyframe-detector face bboxes (preferred if available).**
`identity/validator.py:_analyze_frame` already calls `DeepFace.extract_faces`
and reads `facial_area` (keys `x`, `y`, `w`, `h` — verified at
`validator.py:467-471`). This runs on each sampled frame. The existing detection
infrastructure produces bboxes per detected face; the data just is not forwarded
to a mask. A new helper could generate a binary mask image from the left/right
bbox for use as `attn_mask`. This runs LOCAL, offline, no pod spend.

**Option 2 — InsightFace via shared node 97** (`PulidInsightFaceLoader`). Node 97
already loads the InsightFace analysis model. InsightFace provides face detection
with bboxes as part of the PuLID embedding extraction path — but ComfyUI's
PuLID node does this internally; there is no separate "output face bboxes" wire
on `ApplyPulidFlux` or `ApplyPulidAdvanced`.

**Option 3 — ComfyUI mask creation nodes.** The standard node set includes
geometry-based mask primitives (e.g., `SolidMask`, `MaskComposite`,
`CreateMask`). A simple L/R split mask (left half for char A, right half for char
B) requires no detection — just the image width. This is the simplest to build
offline and test on the pod. **Recommended starting point for the spike:** hard
left/right split mask (no detection required; tests the binding mechanism
without detection dependency; can be upgraded to bbox-derived masks once binding
is confirmed).

Implementation plan for the hard-split mask:
- Node 200: `SolidMask` (value=1.0, width=image_width/2, height=image_height)
  → left mask.
- Node 201: `SolidMask` (value=1.0, width=image_width/2, height=image_height)
  → right mask (placed at x=width/2 via `MaskComposite`, or invert left mask
  via a `InvertMask` node if available).
- `ApplyPulidAdvanced` node 100A reads left mask; node 103A reads right mask.

UNKNOWN: whether `SolidMask` and `MaskComposite` are available on the Novita
pod (they are standard ComfyUI nodes but the census was 44/48). Check
`/object_info` cheaply before building.

### 2.3 Graph delta vs the S2 dual-chain driver

The S2 driver (`scripts/_max_s2_dual_pulid.py`) produces this graph:
- Node 100 (`ApplyPulidFlux`, Aria ref, weight 0.85) → spliced before its
  post-prune consumer.
- Node 103 (`ApplyPulidFlux`, man ref, weight 0.85) → chain from 100's output;
  replaces the post-prune consumer's previous model input.
- Node 95 (`LoadImage`, man ref).

Design A replaces both `ApplyPulidFlux` nodes with `ApplyPulidAdvanced` nodes
(if available on pod) and adds mask inputs. Loader sharing (99/101/97) is
unchanged. Inputs change:

| Input | Node 100A (Aria, left) | Node 103A (man, right) | Verified? |
|---|---|---|---|
| weight | 0.85 (keep S2 value for comparison) | 0.85 | YES — skill doc line 61 |
| projection | ortho_v2 | ortho_v2 | YES — skill doc line 62 |
| fidelity | 8 | 8 | YES — skill doc line 63 |
| noise | 0.0 | 0.0 | YES — skill doc line 64 |
| start_at | 0.0 | 0.0 | YES — skill doc line 65 |
| end_at | **0.9** (match S2 baseline — isolate attn_mask as the only delta) | **0.9** | YES — `pulid_max.json` node 100 line 64; skill doc line 66 default is 1.0 but production uses 0.9 |
| attn_mask | left mask (node 200) | right mask (node 201) | YES — skill doc line 67 |
| model | from prior stage (LoRA chain or base) | ["100A", 0] | **UNVERIFIED** — not listed in skill doc for ApplyPulidAdvanced; present on ApplyPulidFlux (node 100) |
| pulid_flux | ["99", 0] | ["99", 0] | **UNVERIFIED** — not listed in skill doc for ApplyPulidAdvanced |
| eva_clip | ["101", 0] | ["101", 0] | **UNVERIFIED** — not listed in skill doc for ApplyPulidAdvanced |
| face_analysis | ["97", 0] | ["97", 0] | **UNVERIFIED** — not listed in skill doc for ApplyPulidAdvanced |
| image | Aria ref (node 93) | man ref (node 95) | **UNVERIFIED** — not listed in skill doc for ApplyPulidAdvanced |

**WARNING on the UNVERIFIED inputs above:** The skill doc
(`.claude/skills/comfyui-mastery/nodes-face-identity.md:56-68`) only documents
the 7 inputs listed for `ApplyPulidAdvanced` (`weight`, `projection`, `fidelity`,
`noise`, `start_at`, `end_at`, `attn_mask`). It does NOT list `model`, `pulid_flux`,
`eva_clip`, `face_analysis`, or `image`. These are inputs on `ApplyPulidFlux`
(verified: node 100 in pulid_max.json). Whether `ApplyPulidAdvanced` shares this
input schema is UNKNOWN — the node may not accept these inputs, or may accept them
under different names. Do NOT write a script against the UNVERIFIED rows without
first verifying via `/object_info/ApplyPulidAdvanced` on the pod.

**FLUX-specific parameters present on `ApplyPulidFlux` (node 100, verified in
`pulid_max.json` lines 65-69): `fusion`, `fusion_weight_max`, `fusion_weight_min`,
`train_step`, `use_gray`.** These five inputs are NOT listed in the
`ApplyPulidAdvanced` skill doc schema. If `ApplyPulidAdvanced` is FLUX-compatible
but omits these tuning parameters, the Design A vs S2-baseline comparison will be
confounded: any binding improvement (or regression) could be due to the missing
FLUX-specific tuning, not just the `attn_mask`. Probe `/object_info/ApplyPulidAdvanced`
for these fields before concluding Design A is parameter-equivalent to S2.

**UNKNOWN: `ApplyPulidAdvanced` on FLUX may require different parameters than
on SDXL (`projection`, `fidelity`, `noise` per the skill doc) — the FLUX variant
may not expose all of these. Verify via `/object_info/ApplyPulidAdvanced` on the
pod before committing to this node.**

If `ApplyPulidAdvanced` is absent or FLUX-incompatible, the fallback is to keep
`ApplyPulidFlux` with a ComfyUI `IPAdapterMaskEmbeds`-style workaround
(UNVERIFIED — requires research) or to stay on the unmasked dual chain and
accept Design C's swap approach as the binding mechanism.

### 2.4 UNKNOWNS to resolve on-pod (probe first, cheap)

All probes are single `GET /object_info/<class_name>` calls — zero render cost:

1. **`ApplyPulidAdvanced` presence + schema:** does it exist? does it expose
   `attn_mask` as an input? does it list a `pulid_flux` input (FLUX-native)
   or only a `pulid` input (SDXL-era)?
2. **`SolidMask` and `MaskComposite` presence** (standard nodes but census gap
   of 4 classes is unresolved): `GET /object_info/SolidMask`,
   `GET /object_info/MaskComposite`, `GET /object_info/InvertMask`.
3. **Census gaps:** the 2026-06-11 census reported 44/48 expected classes
   (operator handoff). Identify the 4 absent classes before any graph surgery
   that depends on them.
4. **`attn_mask` coordinate space (operator disposition #3):** pixel-space
   `SolidMask` output vs the attention/latent resolution (FLUX latents are
   /8) is unaddressed by any in-repo source. Schema probe first (does the
   input declare a `MASK` type with dimension hints?); then resolve
   empirically at the Phase-3 N=1 smoke — feed the mask and inspect
   shapes/erroring BEFORE the N=4 batch. A silently mis-scaled mask would
   produce unmasked-equivalent results and read as a false Design-A NO-GO.

All probes must pass before any Design A render. Budget: 4 HTTP calls +
one N=1 smoke already in the protocol, $0 incremental cost.

---

## 3. Design B — per-face identity assignment (step 2 of §3(d))

### 3.1 What S2 measured vs what is needed

The S2 validation called `validate_image(full_image, ref)` for each character.
The fix `dc5ad2b` (`identity/validator.py:549-561`) scores the **best-matching
detected face across all faces in the image** (verified by reading the diff and
the test `TestValidateImageMultiFace`). This correctly answers "is this character
present in the image?" but does NOT answer "is this character assigned to their
intended spatial position?"

In S2 n3, the man's geometry scored 0.832 on the LEFT figure. Full-image
validate_image returned 0.832 for the man — which is technically correct (the
man IS present) but misleading in context: the man's face is on the wrong figure's
body. The metric said GO; the visual said BINDING FAILURE.

**The missing step:** a binding score that asks "is character X's face on the
body we intended for them?" — not just "is character X's face somewhere in the
image?"

### 3.2 Definition of a binding score

A binding score for character X in a two-shot with the convention (X=left,
Y=right) is:

```
binding_score(X) = validate_image(left_crop, X.ref) - validate_image(right_crop, X.ref)
```

where "left_crop" and "right_crop" are 50%-width crops of the frame.
- binding_score > 0 → X's face is more prominent in their intended position.
- binding_score <= 0 → BINDING FAILURE (the face scored higher on the wrong half).

The absolute identity score (dc5ad2b's best-face) answers presence; the binding
score answers assignment. Both are needed to declare a pass.

**Implementation note:** `validate_image` (and the underlying `_analyze_single_image`,
lines 546-561) already iterates over all detected faces in the crop and takes the
best-matching embedding via the `max(similarity, ...)` accumulator loop. Do NOT
wrap the call in an additional `max()` — the internal best-face selection is already
there, and the formula should call `validate_image` once per crop, not `max()` over
a scalar. The half-crop approach already isolates to roughly one face per crop; the
internal best-face logic handles edge cases (e.g., a second face near the boundary).
The `_s1_rescore_crops.py:33-38` `score()` helper calls `validate_image` directly —
reuse that pattern.

An alternative that avoids hardcoded L/R: if face bboxes are available
(via `_analyze_frame`'s existing DeepFace.extract_faces call), assign each
detected face to the character whose ref embedding it best matches, then check
whether the assigned face's bbox center lies on the correct half of the frame.
This is more robust but requires bbox coordinates to be threaded through.

The half-crop approach is already implemented for OFFLINE use in
`scripts/_s1_rescore_crops.py:22-30` (verified by reading the script):
`crop_half(img_path, side, outdir)` uses PIL to produce 50%-width crops.
**Reuse this function for the binding metric computation — no new code needed
for the measurement, only for the pass/fail decision logic.**

### 3.3 Where it lives in identity/validator.py

Current state after dc5ad2b (verified by reading the diff and the file):

- `validate_image` (line 68): takes a single `image_path` and `reference_path`.
  Calls `_analyze_single_image` which scores the best-matching face. Returns a
  single `IdentityValidationResult` with `overall_score` = best-face score.
- `_analyze_frame` (line 409): takes `ref_embeddings: Dict[str, np.ndarray]`
  (multi-char), detects faces via `DeepFace.extract_faces`, matches each
  detected face crop to each ref_emb via the best-similarity loop (lines 457-520).
  Returns `Dict[str, FrameSample]` — one per character. This is the VIDEO path.
- `_analyze_single_image` (line 537): IMAGE path, scores best-face but does not
  have access to `facial_area` bbox coordinates (calls
  `DeepFace.represent` not `extract_faces`, so no bbox dict returned).

**The binding score belongs in a new function** that:
1. Calls `DeepFace.extract_faces(image_path)` to get face regions + `facial_area`
   dicts (already done in `_analyze_frame` — reuse that pattern).
2. For each character, finds the detected face with the best embedding match
   (same as dc5ad2b's best-face loop) and records that face's `facial_area.x`
   centroid.
3. Assigns the face to a spatial slot (left/right/center based on image width).
4. Returns a `binding_score` float and a `binding_ok: bool` per character.

This function does NOT exist today. It is a new capability, not a refactor
of existing code.

**Location:** `identity/validator.py`, new method `_compute_binding_scores`:

```python
def _compute_binding_scores(
    self,
    image_path: str,
    char_specs: List[Dict],   # [{"char_id": ..., "ref_emb": ..., "intended_slot": "left"|"right"|"center"}, ...]
    image_width: int,
) -> Dict[str, Dict]:  # char_id -> {"binding_score": float, "binding_ok": bool, "detected_x": int}
```

**Schema gap — MUST RESOLVE BEFORE CODING (flagged for director):** The
`_compute_binding_scores` signature proposes `char_specs: List[Dict]` with
`"intended_slot": "left"|"right"|"center"`, but `CharIdentitySpec`
(verified at `cinema/shots/strategy.py:20-43`) has NO `intended_slot` field.
The controller at `controller.py:808-816` iterates `strategy.secondary_specs`,
which are `CharIdentitySpec` objects — they do not carry slot information.
Three approaches exist, each with different implications:

(a) **Add `intended_slot` to `CharIdentitySpec`** — a frozen dataclass schema
  change; all callers that construct `CharIdentitySpec` must be updated. Affects
  `IdentityStrategy` builders, `to_dict()`, and any test fixtures. This is the
  most complete fix but touches a high-fanout dataclass.

(b) **Derive slot from prompt position hints** — the production prompt includes
  spatial language ("on the left", "on the right"); derive slot from the prompt
  text rather than storing it in the spec. Fragile against prompt variation.

(c) **Hard-code the 2-char convention** — primary is always one side, secondary
  always the other, based on `primary_char_id` vs `secondary_specs[0]`. Works
  for 2-char shots only; breaks at 3+ chars (no center convention exists).

**RESOLVED (2026-06-12, director, recorded at `ef7b60c`):** the metric is
slot-source-agnostic — callers pass `intended_slot` explicitly per character
(option (c)-as-parameter). Phase-0/Phase-3 callers (instrument, spike driver)
know the prompt convention; the `CharIdentitySpec` schema change (option (a))
is deferred until the spike validates the metric and production wiring
(A1/A2/A4 gating) begins.

**Dependency chain:** the controller at `controller.py:808-816` calls
`validate_image` per character on the full image (post-dc5ad2b, scores best
face). Adding binding requires either a new separate call or extending the
existing per-char loop. Recommended: add `validate_image_with_binding` as a
new method that returns both scores; keep `validate_image` unchanged for
backward compatibility.

### 3.4 Co-star false-positive family — what Design B's binding metric must close

(Source: SPEC-P1-1 §3(d), "Per-face validation follow-up — sharpened scope
(2026-06-12)", operator Lane V report `2026-06-11T18:49:37Z`, director-disposed.)

The best-face fix (`dc5ad2b`) closed the first-face false-NEGATIVE but leaves
a latent co-star false-POSITIVE family. Design B's binding metric is the
designated implementation home for closing it:

- **A1** — the ADR-023 conjunctive halt (portrait/medium) can early-fire when
  the best-matching face in the full image is the CO-STAR's, not the intended
  character's. A binding-aware controller must check that the matched face is
  on the intended spatial side before treating the score as a halt trigger.
- **A2** — secondary scoring at `controller.py:810` can false-pass on the
  PRIMARY's face. Live evidence: Pass-A man full-image 0.597 vs half-crop
  0.487 — the full-image score was elevated by Aria's face being the detected
  best-match for the "man" ref query on that crop. The binding metric
  (left-crop vs right-crop delta) closes this by requiring the score to be
  stronger on the intended side.
- **A4** — regen-floor bypass via co-star match (refuter-split 1-1; treat as
  plausible until assignment lands). The binding metric must gate the regen-floor
  decision, not just the halt.

**A3** (ref-side `_get_embedding` first-face `[0]` contract is aspirational —
enforce single-face at character-registration time) is queued as a SEPARATE
code task, not part of Design B's binding metric implementation.

**A5 — other-half-empty false-positive** (operator Lane V `2026-06-12T00:02:59Z`
advisory #1; director-disposed + adversarially re-verified `wf_9ed6fbf2-50d`).
A NEW family member: the co-star is dominant on the character's INTENDED half
AND the other half is face-absent. The `other_rtype=='none'` branch
(`validator.py:602-605`) then sets `binding_ok = intended_score > 0`, with no
co-star/own-face discrimination — a wrong-identity face on the intended half
(reading ~0.49 cross-identity vs the wrong ref) still passes. **Bounded for the
spike**: under the spike's OPPOSITE-slot assignment + strict count (below), the
character whose intended_slot is the empty half hits `intended_rtype=='none' →
binding_ok=False`, so BOTH-chars-pass is unsatisfiable on a face-absent seed —
A5 cannot lift a genuine `<3/4` to a GO **so long as two guards hold**:
(i) the GO bar uses the STRICT count (§5 below) so face-absent-half seeds are
excluded from the binding denominator; and (ii) callers assign DISTINCT slots.
The adversary found the bound LEAKS for a same-slot caller — both specs
defaulting to `intended_slot='left'` (the `spec.get(...,"left")` default) makes
both fire the other-none branch and both pass on a face-absent-right seed. The
Phase-3 driver MUST assign opposite slots AND add an O(n) slot-uniqueness guard
(`assert len({s['intended_slot'] for s in specs}) == len(specs)` or a logged
WARNING) to `_compute_binding_scores`'s caller path. Thresholding is the WRONG
tool here: a floor above the 0.447 cross-floor would not catch 0.492, and a
floor above 0.492 would eat true man reads (0.466–0.492 on the intended half).
Close it with the
strict count + slot guard, not a similarity threshold.

Risk today: LOW for cross-gender pairs (cross floor 0.447 vs 0.65–0.85
thresholds), MATERIAL for same-gender pairs. Design B eliminates this risk
class for both.

**Note on dc5ad2b operator-review status:** `dc5ad2b` has been reviewed —
operator Lane V report `2026-06-11T18:49:37Z`, verdict ✅ SAFE (18 claims
verified; test non-vacuous, RED 0.5221 reproduced). Dispositions from that
review are folded into SPEC-P1-1 §3(d) "Per-face validation follow-up —
sharpened scope (2026-06-12)". The per-face scoring numbers in §1 above
(n3: L:man 0.832) came from the S2 spike BEFORE dc5ad2b landed — they used
half-crop scripts (`_s1_rescore_crops.py` pattern), not the production
validate_image. **Correction (operator Lane V 20:14:36Z, firsthand-refuted;
director-disposed):** best-face-on-full-image is NOT equivalent to half-crop
scoring. The equivalence holds only for "is X present anywhere in frame";
per-FIGURE reads differ — which is the binding dimension itself. Evidence
(second correction, 2026-06-12 late: the original sec45 leg of this argument
was itself a junk read — operator-owned in their 21:16:46Z probe report —
and the unfiltered instrument's man-column was 13/18 non-figure reads):
the per-face probe (`scripts/_probe_halves_faces.py`) reads the Pass-A man
FIGURE at 0.480 on his half vs 0.597 full-image (co-star elevation), and
the detection-FILTERED instrument (`scripts/_arc_score_session.py --halves`
at `312f6d2`: largest-OK-face only, blobs and whole-image fallbacks
excluded) reads n3-L man figure 0.519 (the unfiltered 0.780 was a 93×93
blob) and Pass-A man L 0.480 / R 0.481. Pass-B implementers MUST NOT use
full-image reads as binding evidence; binding numbers come from
detection-filtered per-half figure reads only.

---

## 4. Design C — per-face best-of-N selection + ReActor swap rescue

### 4.1 input_faces_index targeting

The current production wiring (`quality_max.py:_inject_secondary_faceswap`):
- Node 610 (`ReActorFaceSwap`, static in graph): `input_faces_index="0"`,
  `source_image=node 93` (Aria ref), `input_faces_order="left-right"`.
- Node 611 (injected): `input_faces_index="1"`, `source_image=node 94`
  (secondary canonical), chains `input_image` from node 610 output.
- Node 501 (`SUPIR_first_stage`) reads from 610 (static); `_inject_secondary_faceswap`
  rewires 501 to read from 611 when present.

The `left-right` ordering paired with `input_faces_index="0"/"1"` means ReActor
processes faces in left-to-right spatial order and swaps the Nth one. This
requires at least two detected faces AND that DetectedFace[0] is the left figure
and DetectedFace[1] is the right figure. If generation produces the characters in
the wrong spatial order OR if detection fails to find two faces, the targeting
goes wrong.

### 4.2 The open Pass-A question: why did the swap underdeliver?

The accepted Pass-A artifact (`logs/pass_a_multichar.jpg`) scored the man's half
at 0.487 vs his ref (per §6), while the FAILED landscape artifact's man-half
scored >=0.70 (both halves). Hypotheses (none confirmed by this session):

**H1: Single-face base.** The coherent QUALITY_MAX pass-A candidate may have
generated a strong Aria face (PuLID-anchored) but left the man's face as a
prompt-only generic figure without a strong face region for ReActor to target.
The landscape failure had less coherent face geometry, which paradoxically may
have given ReActor's face detector a different region to work with.

**H2: Detection order mismatch.** If the Aria face is spatially on the left but
detection returns it first (index 0), the swap correctly targets her. If the man
is on the right (index 1), node 611 targets him. But if generation places the
man on the left (prompt says "left: woman"), the left-right ordering maps
DetectedFace[0] to the woman's position, and the man swap (index 1) targets the
right figure — which is correct. However, if only ONE face is confidently
detected by ReActor's InsightFace, the swap for index 1 is silently skipped.

**H3: Blending under high FaceDetailer denoise.** Node 600 (FaceDetailer, denoise
0.35) runs on node 902's output (VAEDecode). FaceDetailer uses the SAME PuLID
weights from node 740 (DifferentialDiffusion chain) — it re-denoises the face
region with Aria's identity embedded. If FaceDetailer reprocesses the man's
face region, it may blend Aria's features back in, undermining the ReActor swap.

### 4.3 A cheap offline experiment using existing artifacts

The S2 artifacts (`logs/s2_dual_n1.jpg` through `n4.jpg`) have strong man-side
geometry scores (n3: L:man 0.832). These were generated WITHOUT the ReActor
swap. Run `_s1_rescore_crops.py`-style half-crop validation on each S2 artifact
to confirm which half carries the man's face and at what absolute score.

Then: run a local ReActor-style post-process swap test (if a local ReActor
build is available — UNVERIFIED) on the S2 n3 artifact. If local ReActor is
unavailable, the pod probe (Phase 0 of the spike) can run a lightweight
ReActor-only test: upload the S2 n3 JPEG and apply node 611 targeting
`input_faces_index="1"` to see whether the swap finds and targets the
right-half face.

**Cost: $0 (offline); pod-only if ReActor test needed (~0.01 GPU-hr, no FLUX
render required).**

### 4.4 Best-of-N selection with binding as the tiebreaker

The existing N=8 best-of-N selection uses `face_validator_gate` with
ADR-023's `conjunctive` halt_rule for portrait/medium. The arc score is
composite (aesthetics + identity). After Design B lands, add a
`binding_score_all_chars` entry to take metadata and use it as a tiebreaker
when two candidates have comparable arc scores:

Priority: `binding_ok=True` for all conditioned chars > arc score > aesthetics.

This does not replace the arc selection but ensures a spatially-correct
binding is preferred over a high-arc binding-failure candidate.

---

## 5. Spike protocol (RUNBOOK style)

**Prerequisites (must hold before pod spin-up):**

- [ ] Pod gateway probe returns 200 (pod may have been stopped; user decision
  on restart, P2-2 guardrails still NOT_DONE — surface billing immediately if
  the pod is running).
- [ ] `dc5ad2b` is operator-reviewed and merged (spec design assumes it is live).
- [ ] Offline Phase 0 work (mask plumbing + binding metric) complete before
  any pod render (see Phase 0 below).
- [ ] User verbatim pod/spend authorization (pod session required for all
  render phases).

**Pod: Novita RTX 6000 Ada 48 GiB, billed at ~$0.30/hr** (verified in prior
session handoffs: `docs/HANDOFF-director-transplant-2026-06-10-disposition-s1-pod-chunk2-landed.md:30`).
Pod credential + start command in director's local-only memory (not in repo).

### Phase 0 — OFFLINE (no pod required, do before spin-up)

**0a. Binding metric experiment on S2 artifacts (Design C, §4.3).**
Run `scripts/_s1_rescore_crops.py`-style half-crops on `logs/s2_dual_n1.jpg`
through `n4.jpg`:

```bash
env -u GIT_INDEX_FILE .venv/bin/python - <<'EOF'
# PSEUDOCODE — implement as a short inline script or new scripts/_s2_binding_check.py
from scripts._s1_rescore_crops import crop_half, score
import os
aria_ref = "domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg"
man_ref = "logs/p12_fresh_face_man.jpg"
for i in range(1, 5):
    img = f"logs/s2_dual_n{i}.jpg"
    left = crop_half(img, "left", "/tmp/s2_crops")
    right = crop_half(img, "right", "/tmp/s2_crops")
    la = score(left, aria_ref, "aria")
    ra = score(right, aria_ref, "aria")
    lm = score(left, man_ref, "man")
    rm = score(right, man_ref, "man")
    print(f"n{i}: L:aria={la:.3f} R:aria={ra:.3f} L:man={lm:.3f} R:man={rm:.3f}")
    print(f"     binding:aria={'LEFT' if la>ra else 'RIGHT'}, binding:man={'LEFT' if lm>rm else 'RIGHT'}")
EOF
```

This produces binding signal for each S2 seed at zero cost. Expected from §6:
n3 man geometry on left (L:man > R:man expected). Use this to calibrate the
mask design: if n3 has man on left but prompt placed man on right, the mask
design needs to account for generation-vs-prompt spatial disagreement.

**0b. Mask generation prototype (Design A).**
Write `scripts/_mask_gen.py` — a simple helper that takes image dimensions and
returns a 50%-split PIL mask for left and right halves. No pod needed. The mask
will be saved as a JPEG/PNG and uploaded to the pod as a node input.

**0c. Binding metric function (Design B).**
Implement `IdentityValidator._compute_binding_scores` in `identity/validator.py`.
Write TDD (RED → GREEN). Test against S2 n3 artifact using the known binding
expectation (man's face geometry should bind to LEFT per n3 embedding scores).
This is fully OFFLINE and can be reviewed before pod spin-up.

**PHASE 0 RESULTS (2026-06-12 — COMPLETE):**

- **0a** — binding directions derived from the committed instrument
  (no new compute). **0b** `fcd06b5` — `scripts/_mask_gen.py`, boundary
  test-pinned to `crop_half`'s `w//2`. **0c** `ef7b60c` — binding metric +
  `validate_image_with_binding`, 18 tests (+10 by `312f6d2` → 28 HEAD total;
  operator C4 — the 28 was the post-filter total, not ef7b60c's). **Filter (unplanned, blocking)**
  `312f6d2` — the operator's 21:16:46Z probe showed the unfiltered
  instrument's man-column was 13/18 non-figure reads (blobs + whole-image
  fallbacks); detection-filtered figure reads (largest OK face, ≥1% area)
  now back both the instrument and the metric; ref embeddings use the
  largest-OK guard. A3 hardening rode along: registration assert `418dee2`
  + PUT-bypass closed `786d9e9`.
- **Unmasked baseline (FILTERED figure reads, S2 n1–4, intended
  aria=left / man=right per the driver prompt):** aria binding_ok **0/4**;
  man **1/4** (n4 only, via face-absent-on-other-half semantics; **0/3**
  on seeds where both halves had detectable faces). Man figure reads are
  0.466–0.492 on the man's INTENDED (right) half; the full filtered range is
  0.466–0.728 (the 0.728 = n1 man on aria's left half, a binding SWAP — operator
  C7). Re-emitted table:
  `logs/halves_rescore_20260612_filtered.{json,txt}` (regenerate:
  `PYTHONPATH=. .venv/bin/python scripts/_arc_score_session.py --halves`).
- **New signal for Phase 3:** 5 of 18 half-crops have NO detectable face
  at all (FAILED-landscape both halves =2; n4-L; sec45-L; sec55-L — all
  read_type='none'/NO_FACE; operator C8 — was miscounted "4 of 18" with a
  spurious "TINY-only" label on sec55-L) —
  per-half face-presence is itself a cheap render-quality gate worth
  recording per seed in Phase 3.
- Design A's ≥3/4 GO bar therefore measures against a **0/4 (strict 0/3)**
  unmasked baseline.

### Phase 1 — Pod spin-up + census (same as S2 runbook Phase 0)

1. **User gate:** verbatim go-ahead for ComfyUI start.
2. Start ComfyUI; wait ~10s; `GET /system_stats` → 200.
3. Census: `GET /object_info`. Expect ~1106 classes. Verify critical additions:
   - `ApplyPulidAdvanced` (UNKNOWN — Design A pivot depends on result)
   - `SolidMask`, `MaskComposite`, `InvertMask` (mask nodes for Design A)
   - All prior S2 classes: `ApplyPulidFlux`, `PulidFluxModelLoader`,
     `ReActorFaceSwap`, `SUPIR_model_loader_v2`, `FaceDetailer`
4. Record: census count + GPU name/VRAM from `/system_stats`.
5. **Design A GATE (operator disposition #2 — this probe is GO/NO-GO, not
   advisory):** Design A proceeds ONLY if `ApplyPulidAdvanced` is present
   AND its schema shows FLUX compatibility (a `pulid_flux`-typed input, not
   only SDXL-era `pulid`) AND it exposes `attn_mask`. Class presence alone
   is NOT a pass — nothing in-repo confirms FLUX compatibility, and the
   production FLUX path uses `ApplyPulidFlux`, which has no `attn_mask`.
   Absent-or-SDXL-only → Design A NO-GO for this spike; fall back in order:
   Design C (swap rescue, Phase 4) with Design B's binding metric as the
   measurement layer either way. Document the NO-GO; do not abort the
   session.

**PHASE 1 RESULTS (2026-06-13 — COMPLETE; pod 07ed667 RUNNING, ComfyUI
restarted; instrument `scripts/_passb_census.py`, artifact
`logs/passb_phase1_census_20260613.{json,txt}`, regenerate:
`.venv/bin/python scripts/_passb_census.py --url $COMFYUI_SERVER_URL --out logs/passb_phase1_census_<date>`
— R-MEASURE, logs gitignored so the committed instrument is the guarantee):**

- **Census: 1106 classes** (exact match to the validated S2 baseline). GPU
  RTX 6000 Ada, 49140 MiB. Both char LoRAs present in `models/loras/`
  (`char_lora_fal_v2.safetensors` + `char_lora_man_v1.safetensors`); disk 87%
  (14 GiB free). All critical classes present incl. mask nodes (`SolidMask`,
  `MaskComposite`, `InvertMask`, `LoadImageMask`, `ImageToMask`).
- **DESIGN-A GATE: GO — but the premise above was STALE and is hereby
  corrected.** The census schemas show:
    - `ApplyPulidFlux` (the PRODUCTION FLUX node, already in the S2 dual driver):
      `pulid_flux` input typed `PULIDFLUX` → FLUX-compatible, **AND it DOES
      expose `attn_mask` (optional `MASK`).** The spec's "ApplyPulidFlux has no
      attn_mask" was an UNVERIFIED assumption — REFUTED by census.
    - `ApplyPulidAdvanced`: present, exposes `attn_mask`, BUT its `pulid` input
      is typed `PULID` (SDXL/SD15-era), NOT `pulid_flux` → `flux_compatible=False`.
      It is the SDXL PuLID applier; feeding a FLUX model is an architecture
      mismatch. So it is NOT the route, attn_mask notwithstanding.
- **Consequence (favorable):** masked dual-PuLID on FLUX needs NO new node
  class. The route is the production `ApplyPulidFlux.attn_mask` — the Phase-3
  delta from `_max_s2_dual_pulid.py` collapses to "wire a `MASK` into each
  `ApplyPulidFlux.attn_mask` input." Lower risk than the original
  `ApplyPulidAdvanced` plan (production node, already VRAM/identity-validated
  in S2). `attn_mask` coordinate space (probe #4) still UNKNOWN from schema
  alone — resolve empirically at the Phase-3 N=1 smoke (pixel vs latent/8;
  `scripts/_mask_gen.py` emits pixel-space — a mis-scale registers as a false
  NO-GO, see its docstring).

### Phase 2 — VRAM baseline re-confirm (N=1, ~5 min)

Single-char Aria render at N=1 (no secondary). Poll `/system_stats` for VRAM.
Compare to 41.4 GiB S2 baseline. Accept if within ±0.5 GiB (pod may have
different process state). Purpose: confirm the baseline is stable before adding
the dual-identity stack.

### Phase 3 — Design A: attention-masked dual-PuLID (if Phase 1 census passes)

**N=1 smoke first, then N=4.**

Script: new `scripts/_max_passBa_masked_pulid.py`. Extends `_max_s2_dual_pulid.py`
with mask nodes:
1. Inject mask nodes (200 left, 201 right) — `SolidMask` + crop/pad or
   `MaskComposite` to produce 50%-width binary masks.
2. Replace both `ApplyPulidFlux` nodes with `ApplyPulidAdvanced` nodes (if
   available per Phase 1).
3. Wire `attn_mask` inputs.

**Seeds:** 990011/990022/990033/990044 (same as S2 for direct comparison).
Both weights 0.85 (keep constant vs S2 for isolation).

**VRAM expectation:** mask operations add minimal overhead; expect ~41.8 GiB
or below (the S2 peak with unmasked dual-PuLID). If VRAM rises meaningfully,
investigate before scaling to N=4.

**Halt rules (ADR-023, `conjunctive` for medium shot-class):**
- OOM at N=1: ABORT Design A.
- OOM at N=4 but N=1 OK: document VRAM ceiling; reduce to N=2 for production.
- Both arc scores >=0.70 AND binding_ok for BOTH characters in >=3/4 seeds
  (see GO/NO-GO criteria): DESIGN A GO.

**PHASE 3 RESULTS (2026-06-13 — DESIGN A = NO-GO at N=1; did NOT scale to N=4).**
Instrument: `scripts/_max_passBa_masked_pulid.py` (= `_max_s2_dual_pulid.build_dual`
+ per-char `attn_mask` on the PRODUCTION `ApplyPulidFlux`, per the Phase-1
correction — NOT `ApplyPulidAdvanced`, which is SDXL-era). Artifacts:
`logs/passb_n1.jpg` (swapped polarity) + `logs/passb_n1_noswap.jpg`; binding
table `logs/halves_rescore_20260613.{json,txt}` (regenerate:
`scripts/_arc_score_session.py --halves --artifacts logs/passb_n1*.jpg`). Spend
~$0.06 (2 × N=1 smoke). Seed 990011 both runs.

- **VRAM (Phase 2 FOLDED): PASS** — peak 33.9 / 32.9 GiB, well below S2's 41.8
  and the 48 GiB ceiling; no OOM. The masked dual adds no VRAM risk.
- **attn_mask IS functional, but the man-absent outcome is mask-independent
  (CORRECTED — operator graph-JSON diagnosis `d569edd` 04:53:22Z).** My first
  read was "swap-INVARIANT → masks inert"; that was WRONG. The operator pulled
  both executed graphs from the pod `/history` (read-only, $0): the two runs
  (`00101` default, `00102` swapped) produced DIFFERENT pod outputs (distinct
  md5, 8894702 vs 8895386 bytes) — so `attn_mask` DOES perturb the render. My
  "identical" read came from a local download-naming artifact (both locally
  scored files briefly resolved to `00101` before the swap render landed).
  Man-node wiring verified CORRECT (node 103 weight 0.85, attn_mask wired, man
  applied LAST). But the OUTCOME is the same in BOTH polarities: aria **0.823 /
  0.828** on the right, man **0.450 / 0.454** (cross-floor), left NO_FACE.
- **Man never binds — the blocker is UPSTREAM of masking.** Masking the man to
  the right (default) OR left (swap) makes no difference to whether he appears:
  he doesn't manifest at all (cross-floor 0.45, consistent with Pass-A 0.487 /
  S2 0/4). Root cause (operator R-SKILL/comfyui-mastery diagnosis, CONVERGENT
  with this doc's reframe): the man ref `logs/p12_fresh_face_man.jpg` is
  PAINTERLY/stylized → weak InsightFace embedding, overwhelmed by aria's strong
  photoreal embedding at equal 0.85 weights. `attn_mask` is a soft spatial
  perturbation; it CANNOT make an identity appear that isn't binding upstream.
  Masking was never the lever — identity reinforcement is (→ Design D / asym
  weights / better ref).
- **VISUAL (mandatory, overrides embeddings): NO-GO.** Both figures render as
  the same woman (aria-like, short dark wavy hair, feminine) — the prompt's
  "middle-aged man with a grey beard" is absent. Textbook S3 homogenization.
- **Binding GO bar (STRICT count): 0/1 both-chars** — man fails every seed; not
  scaled to N=4 because N=1 is unambiguous and saves ~4× spend (ADR-023 spirit).
- **ROOT-CAUSE REFRAME (carried to the fork):** the driver runs **LoRA-LESS by
  design** (`build_dual` → `_inject_identity(..., None, ...)` to isolate the
  PuLID axis), yet a trained **`char_lora_man_v1.safetensors` sits unused on the
  pod**. The man's chronic PuLID-only underbinding may simply be that PuLID
  alone is too weak for the secondary identity. Candidate **Design D**: dual
  render WITH the man LoRA (@~0.55 per the realism config) + PuLID — tests the
  production approach, not just the isolated-PuLID axis. Surfaced to user as the
  recommended next direction over Design C swap-rescue.

**DESIGN D RESULTS (2026-06-13 — BREAKTHROUGH on the core problem; user chose
D).** Instrument: `scripts/_max_passBd_lora_pulid.py` (= S2 dual topology + man
LoRA `char_lora_man_v1` @0.55 on node 700 + `TOKman` trigger; aria PuLID-only;
SINGLE LoRA, not the S3 stack; no masks). N=1 smoke, seed 990011, ~$0.03.
Artifact `logs/passb_d_n1.jpg`; binding `logs/halves_rescore_20260613.*`
(regenerate: `scripts/_arc_score_session.py --halves --artifacts logs/passb_d_n1.jpg`).

- **THE MAN BINDS — first time ever.** LEFT half: **man 0.870** / aria 0.476;
  RIGHT half: aria **0.763** / man 0.507. Two DISTINCT, strongly-bound
  identities on separate halves (man 0.870 ≫ the 0.70 bar; cf. the chronic
  0.45–0.52 man cross-floor in Pass-A/S2/Design-A). The reframe is CONFIRMED:
  PuLID-alone was too weak for the secondary; his trained LoRA was the missing
  piece. VRAM 41.6 GiB (LoRA adds ~8 GiB vs Design A's 33.9; still well under 48,
  no OOM).
- **CAVEAT 1 — placement SWAPPED:** rendered man-LEFT / aria-RIGHT vs the
  prompt's woman-left/man-right. So the STRICT intended-slot binding_ok reads
  0/1 (both on the "wrong" half) EVEN THOUGH both bound distinctly — the GO bar
  as written measures placement-correctness, which is a SEPARATE axis from
  "does the secondary bind at all" (now solved). Placement is tractable (prompt
  order, seed, or masking now that two real identities exist to place).
- **CAVEAT 2 — visual OVER-COOKED:** crusty/over-processed skin, no crisp grey
  beard — the documented max-tier over-cook (`realism_production_plus_char_lora`:
  production tier + char LoRA @0.55 = realism; max over-cooks). Tier/quality is
  a separate axis from binding.
- **Disposition:** core multi-character binding problem SOLVED via man LoRA.
  Remaining: placement control + tier/quality polish. Surfaced to user for the
  next direction (N=4 confirm / placement fix / production-tier quality /
  strength tune). NOT yet scaled to N=4 (placement swap would read 0/4 strict
  and undersell the binding win — fix placement first).

### Phase 4 — Design C: ReActor swap rescue probe (with or without Design A)

**Use the best seed from Phase 3** (or from S2 n3 if Phase 3 is skipped/aborting).

Test: upload S2 n3 artifact (`logs/s2_dual_n3.jpg`) to the pod. Run a
minimal workflow with ONLY the ReActor swap nodes (no FLUX render).

**Required rewire — MUST do before executing:** In the production graph, node
610's `input_image` comes from node 600 (`FaceDetailer`, verified
`pulid_max.json`: `node 610 inputs.input_image = ["600", 0]`). Node 600
itself reads from node 902 (`VAEDecode`). An uploaded JPEG cannot be fed into
this graph without breaking that chain. The executing seat must:

1. Inject node 612 as a `LoadImage` node (or reuse an existing `LoadImage`
   node not in the minimal path) that holds the uploaded S2 n3 JPEG.
2. Rewire node 610's `input_image` to read from node 612:
   ```python
   w['610']['inputs']['input_image'] = ['612', 0]
   ```
3. Remove or stub the FaceDetailer/VAEDecode chain from the minimal submit
   (do not execute them — they require a FLUX UNet in the graph).
4. Wire a `SaveImage` node to node 611's output (the injected secondary swap
   node from `_inject_secondary_faceswap`), or to node 610's output if testing
   index-0 targeting only.

The minimal graph therefore consists of: LoadImage(612) → ReActorFaceSwap
610 (Aria, index 0) → ReActorFaceSwap 611 (man, index 1) → SaveImage.
All other nodes from `pulid_max.json` should be omitted from the submitted
graph to avoid triggering the full FLUX pipeline.

- Node 610: swap face index 0 with Aria ref (should be a no-op if Aria is
  already on the left in n3 per the binding check from Phase 0a).
- Node 611: swap face index 1 with man ref.
- Save output.

Score with half-crop binding check (Phase 0a script).

**Expected outcome (if H1/H2 hypotheses hold):** the swap successfully
targets the right-half face in n3 (which should be the Aria-geometry figure
from S2), producing a man face there. This would confirm the swap CAN target
the secondary face — the Pass-A failure was not a ReActor limitation but a
base-image property.

**Cost:** ~1 GPU-min (image-only, no diffusion). $~0.01 pod time.

### Phase 5 — Integration: Design B binding metric live validation

Run the Phase 0c binding metric implementation against the Phase 3 outputs.
Record per-character binding scores alongside arc scores. Confirm the metric
correctly identifies binding-OK vs binding-failure candidates.

### Phase 6 — Exit record

Results → new spec (this document) §6 record (to be added by the executing
seat). Include:
- Phase 1 census: `ApplyPulidAdvanced` present/absent.
- Phase 3: arc scores per seed, binding scores per seed, VRAM peak.
- Phase 4: ReActor swap result on S2 n3.
- Phase 5: binding metric calibration.
- GO/NO-GO verdict per design.

Pod stop/keep: user decision.

### GO/NO-GO criteria

**Design A GO (masked dual-PuLID):**
- Phase-1 GATE passed (2026-06-13: GO via `ApplyPulidFlux.attn_mask`, the
  production FLUX node — `ApplyPulidAdvanced` is SDXL-era `PULID` and NOT the
  route; see Phase-1 RESULTS).
- No OOM at N=4.
- Both arc scores >=0.70 (VRAM criterion from S2, unchanged).
- Binding_ok=True for BOTH conditioned characters in **>=3/4 seeds** (true
  majority; 2/4 is not a majority and equals the unmasked S2 baseline — the
  masked arm must BEAT the baseline, not tie it).
  **STRICT COUNT (director disposition 2026-06-12T00:02:59Z + adversarial verify
  `wf_9ed6fbf2-50d`; closes the §3.4 A5 GO-leak):** count only seeds where BOTH
  halves have a figure read (`read_type=='figure'`). Seeds with NO_FACE on
  either half are EXCLUDED from the denominator — they MUST NOT count toward the
  ≥3, because the `other-none` branch hands the present-half character a free
  `binding_ok=True` (A5) that is not a real binding test. So: a GO needs **≥3 of
  4 seeds in which both halves have a figure read AND both characters bind on
  the intended side.** If fewer than 3 seeds have both-halves figure reads,
  record the strict count and the raw count separately and treat as NO-GO (too
  few testable seeds). The per-half face-presence already recorded per seed
  (Phase-3 quality signal) is the EXCLUSION input — wire it into the GO tally,
  not just the quality log. The unmasked baseline is **0/4 (strict 0/3)**; the
  masked arm must reach ≥3/4 on the strict count.
- **Instrument (R-MEASURE; operator disposition #1 DISCHARGED `45c6e52`):**
  all per-half arc/binding numbers for Phase-3 artifacts come from the
  committed scorer — `scripts/_arc_score_session.py --halves --artifacts
  'logs/passb_*.jpg'` — emitting the `logs/halves_rescore_<date>.{json,txt}`
  table. No ad-hoc runtime reads (the S2-era ad-hoc numbers produced two
  unreproducible record entries; see SPEC-P1-1 §6 instrument append).
- **VISUAL CHECK mandatory**: binding metric numbers alone are insufficient given
  the S3 lesson (embeddings can false-GO). Director or operator must visually
  confirm both faces are on the intended figures.

**Design C GO (ReActor swap rescue):**
- ReActor successfully swaps the secondary face in the Phase 4 probe.
- The swap produces binding_ok=True for the secondary character.
- No blending artifacts from FaceDetailer re-denoise (visual check).

**VISUAL-VERDICT-OVERRIDES-EMBEDDINGS rule** (established by S3 finding):
Any arm where both faces are visually homogenized (same gender, same
wardrobe) is an automatic NO-GO regardless of embedding scores. The cross-floor
(0.447 aria↔man) means >=0.70 is real signal for geometry — but geometry
and visual identity can diverge (S3's beard=neck-texture case). Visual
inspection is non-optional.

**Cross-floor calibration context:** the 0.447 cross-floor was measured as
aria-ref↔man-ref similarity (§1, §6). Any score >=0.70 on a two-shot face is
real signal (above the 0.447 noise floor by >0.25). The critical additional
check is VISUAL confirmation that the 0.70+ signal is associated with the
right-positioned face.

### Cost estimate

| Item | Estimate | Basis |
|---|---|---|
| Phase 0 offline work | $0 | No API calls |
| Phase 1 pod spin-up + census | ~$0.05 | ~10 min @ $0.30/hr |
| Phase 2 N=1 VRAM baseline | ~$0.03 | ~5 min pod |
| Phase 3 masked dual-PuLID N=1 + N=4 | ~$0.10 | ~20 min pod + N=4 renders (if renders take as long as S2 session, actual may be higher) |
| Phase 4 ReActor swap probe | ~$0.01 | ~2 min pod (no FLUX) |
| Phase 5 binding metric validation | $0 | Local compute only |
| Pod idle (between phases) | ~$0.10–0.30 | 20–60 min idle @ $0.30/hr |
| **Total session estimate** | **~$0.30–0.50** | Assumes ~1–1.5 h billed uptime — treat as FLOOR, not cap; if Design A renders take as long as the comparable S2 session, the total may exceed this |

FAL spend: $0 (all renders are pod-side QUALITY_MAX in this session, not FAL).

The previous S2/S3 session ran ~$0.50–1.20 (per spec §4 row). Pass B is
tighter because the baseline is already established and the main unknown
(VRAM) is already bounded at 41.8 GiB.

### What can be built and tested OFFLINE first

| Work item | Offline | Pod required |
|---|---|---|
| Phase 0a: S2 binding check via half-crops | Yes | No |
| Phase 0b: mask generation helper | Yes | No |
| Phase 0c: `_compute_binding_scores` + TDD | Yes | No |
| `ApplyPulidAdvanced` node availability probe | No | Yes (Phase 1) |
| `SolidMask`/`MaskComposite` availability probe | No | Yes (Phase 1) |
| Design A graph surgery script | Yes (write) | Yes (execute) |
| Design C ReActor swap probe | No | Yes (Phase 4) |
| Design B integration with controller scoring | Yes | No (unit-testable) |

---

## 6. Out-of-scope + risks

### Out of scope

- **Mechanism (a) Kontext multi-char (slice 1):** already implemented (slice-1
  plan); this spec covers the max-tier pod path (slice 2/Pass B) only.
- **LoRA training for additional characters:** man LoRA exists; Aria LoRA v2
  registered at 0.55. Additional training is deferred; the current two-char
  pair is sufficient for Pass B validation.
- **S3 revisit with a photoreal man LoRA:** S3 BLEED is confirmed at the
  clamp strength. A photoreal-lineage man LoRA (more refs, higher steps) MIGHT
  reduce bleed. This is low priority vs the PuLID-binding path; do not spend
  pod time on it in this session without a directorial decision.
- **P1-2 over-cook investigation:** already directionally resolved
  (per-identity-mode post-pass tuning); not in scope for this spike.
- **Multi-char lip-sync:** noted in spec §9 adjacent debts; out of scope.

### Risks

**R1: `ApplyPulidAdvanced` absent or FLUX-incompatible (HIGH probability for
the FLUX variant).** The skill document distinguishes `ApplyPulid` (SDXL) from
`ApplyPulidFlux` (FLUX-native). `ApplyPulidAdvanced` may be SDXL-only and
incompatible with the FLUX UNet. If so, Design A blocks and the session falls
back to Design C exclusively. The offline work (Phase 0) is unaffected; only
Phase 3 is skipped.

**R2: S3's LoRA-only-secondary finding is seed-specific (LOW-MEDIUM probability).**
S3 used a single seed per arm. A different seed or a photoreal man LoRA might
show less bleed. However, the VISUAL homogenization (two women) is a
strong finding — it is not a subtle metric difference. The LoRA-dead-as-sole-mechanism
conclusion is treated as firm; reversing it requires a dedicated sweep, not
a side-experiment in this session.

**R3: Man LoRA trained on painterly lineage (LOW probability of causing
Pass-B issues).** The man LoRA was trained on 6 refs from the P1-2 "fresh face"
painterly specimen. For REALISM purpose, this is suboptimal — but for identity
matching the LoRA captures the face geometry regardless of style. S2 (which
had no man LoRA, just the PuLID anchor) scored man geometry at 0.832. The
LoRA adds CLIP-level style which the bleed analysis found dominant. The question
for Pass B is whether the PuLID anchor (not the LoRA) can bind correctly;
the LoRA's painterly bias is secondary.

**R4: FaceDetailer re-denoising the secondary face (MEDIUM probability).**
Node 600 (FaceDetailer, denoise 0.35) reads CLIP from node 700 (Aria's LoRA,
single-char). In the multi-char path, node 700 carries Aria's CLIP. If
FaceDetailer re-denoises the man's face region, it uses Aria's CLIP context and
may blend Aria features into the man's face. This is Hypothesis H3 in §4.2.
Mitigation: the Phase 4 ReActor probe (which bypasses the FLUX render + FaceDetailer
by operating on the finished image) will reveal whether the swap itself works
or whether FaceDetailer is the blocker.

**R5: Identity binding is L/R-ordered for 2-char shots but unspecified for
3+-char shots (KNOWN DESIGN GAP).** The `left-right` convention works for the
validated 2-char pair. 3+-char shots (center position) have no ReActor
equivalent per spec §3(c). This spec scopes to the 2-char case; 3+-char
multi-identity is deferred.

**R6: LoRAs as secondaries are dead under PuLID primary — LoRA-only
secondaries should not be promised (ESTABLISHED, from S3).** The production
formula for multi-char shots with two active LoRAs:
- Primary: LoRA + PuLID anchor → works (S2 n3 proves PuLID carries geometry).
- Secondary: LoRA only (no PuLID, insufficient VRAM for triple-PuLID) → BLEED.
- Required: secondary must have PuLID or ReActor, not LoRA-only.

The `MAX_TIER_MULTI_LORA` mechanism_tag (strategy type) should be understood
as "primary gets LoRA + PuLID; secondary gets LoRA + ReActor rescue." If Pass B
Design A succeeds, the secondary can have a masked PuLID node instead. If
Design A fails, Design C (ReActor rescue) is the secondary identity mechanism.

**R7: dc5ad2b reviewed-SAFE (resolved).** Operator Lane V report
`2026-06-11T18:49:37Z`: ✅ SAFE (18 claims verified; test non-vacuous, RED
0.5221 reproduced). Dispositions folded into SPEC-P1-1 §3(d) sharpened scope.
The co-star false-positive family (A1/A2/A4) surfaced by that review is the
active risk; implementation home is Design B's binding metric (see §3.3 and the
new §3.4 subsection). The concern that best-face scoring changes behavior for
single-face portraits was examined and not flagged — single-face path returns
the only detected face, behaviour unchanged.

---

*Sources verified: SPEC-P1-1 §3/§6 (numbers), RUNBOOK exit record (session
summary), DECISIONS.md ADR-023, git show dc5ad2b, pulid_max.json node inspection
(nodes 100/301/770/772/740/22/600/610/501, class types + input schemas),
scripts/_max_s2_dual_pulid.py, scripts/_max_s3_stack_sweep.py,
identity/validator.py (lines 68-131, 409-535, 537-583),
cinema/shots/controller.py (lines 808-816),
.claude/skills/comfyui-mastery/nodes-face-identity.md (ApplyPulidAdvanced schema).
Last verified against HEAD: 2026-06-12 (this session).*
