# Evidence register

Every load-bearing claim this pipeline rests on, what would falsify it, which
instrument can measure it, and what it currently has behind it.

A claim in this table is in exactly one state:

| status | meaning |
| --- | --- |
| **MEASURED** | a real experiment produced a number, and the artifact is cited |
| **PINNED** | a test enforces it, so it cannot silently revert — but no render proved it *helps* |
| **REASONED** | argued from mechanism, never rendered. The honest default for most of this |
| **VOID** | measured, then the instrument was found unable to support the reading |

`PINNED` and `MEASURED` are different things and the difference has bitten here
before. A test that asserts "the anchor reaches the provider" proves delivery.
It says nothing about whether delivery improves the picture. Only a render does.

## The instruments, and what each may be used for

| instrument | question it answers | may NOT be used for |
| --- | --- | --- |
| `structure_match` | "is this the same picture — same things in the same places?" | shot-to-shot continuity, where a framing change is CORRECT |
| `palette_match` | "is this the same place, lit the same way?" (framing-blind) | anything spatial; it cannot see composition at all |
| `temporal_drift` | "is the picture being re-invented frame to frame?" | absolute quality; only ever a delta between matched arms |
| GhostFaceNet identity | frontal likeness to a real person | **anything off-angle** — ADR-092, it ranks a stranger above the subject |
| operator judgement | everything | nothing. It is the gold standard and outranks every number here |

The metrics are validated against known values in
`tests/unit/test_evidence_metrics.py` before any of them is trusted on an
unknown. That file exists because the first spatial metric drafted for this
harness scored two **unrelated rooms** at 0.874 — it would have confirmed H4 no
matter what the provider did.

---

## H1 — A product photograph beats a description of the product

**Claim** (ADR-093). For a shot with a product and no character, conditioning on
the product's own photograph produces better fidelity than serialising
brand/material/surface/scale into prompt text.

**Status: REASONED.** Delivery is PINNED (`test_object_references.py`), effect is
not measured.

**Falsifier.** Product shots rendered with the photograph score no better than
text-only arms on legibility of markings and on shape fidelity, judged by the
operator on a blind contact sheet.

**Instrument.** Operator judgement primary. `structure_match` against the source
product photograph as a secondary signal — the product should appear with its
real proportions.

**Cost.** 2 arms × 3 prompts × FLUX_KONTEXT $0.08 = **$0.48**

---

## H2 — Location plates improve establishing shots

**Claim** (ADR-094). Plates conditioned into a shot with no character produce a
more faithful room than the location's prompt fragment alone.

**Status: REASONED.** Delivery PINNED (`test_location_references.py`).

**Falsifier.** Plate arms are no closer to the plate's own palette and structure
than text-only arms.

**Instrument.** `palette_match` and `structure_match` against the plate; operator
judgement decides.

**Cost.** 2 arms × 3 prompts × $0.08 = **$0.48**

---

## H3 — The scene anchor beats a sixth face reference

**Claim** (ADR-097). On a saturated single-character set, giving slot 6 to the
previous shot's keyframe improves inter-shot consistency more than a sixth
facial angle improves identity.

**Status: REASONED, and it is the one place a subject displaces another.**
This is the weakest-supported decision in the codebase and it was taken
knowingly.

**Falsifier.** Across shots 2–5 of one scene, the `{5 faces + anchor}` arm shows
no better inter-shot `palette_match` than `{6 faces}` — or shows better palette
consistency at a visible cost to the face, judged by the operator.

**Instrument.** Inter-shot `palette_match` (framing-blind, so a correct framing
change is not punished) + operator judgement on identity. **Not GhostFaceNet**:
per ADR-092 it cannot rank these and has no opinion about rooms.

**Cost.** 4 shots × 2 arms × ($0.08 still + $0.25 VEO) = **$2.64**

---

## H4 — Sending the approved keyframe to VEO beats sending four face photos

**Claim** (ADR-098). The fal VEO branch discarded the approved keyframe on every
shot whose character had references. Leading with it should preserve the
approved composition.

**Status: REASONED — but this one has an unusually clean falsifier**, because the
question "did the keyframe reach the model?" leaves a direct trace.

**Falsifier.** Extract frame 0 of the generated clip and compare it to the
approved keyframe with `structure_match`. If the keyframe-led arm is not
markedly higher than the references-only arm, either the fix does nothing or the
provider ignores reference order — both worth knowing.

This is the highest-value cell in the register: it is cheap, it is objective, it
needs no face embedder, and it tests a defect that was silently discarding
everything the still stage produced.

**Instrument.** `structure_match(frame_0, approved_keyframe)`, plus
`palette_match` for lighting carry-over.

**Cost.** 2 arms × 2 shots × VEO $0.25 = **$1.00**

---

## H5 — A subject-appropriate prompt beats unconditional face language

**Claim** (ADR-098). On a shot with no character, "maintain rigid facial bone
structure" is noise at best in the prompt's highest-attention position.

**Status: REASONED.** Clause selection is PINNED
(`test_motion_keyframe_and_subject.py`).

**Falsifier.** Product clips generated with the face clause show no more marking
instability than clips with the product clause.

**Instrument.** `temporal_drift` delta between matched arms (same shot, same
camera move), operator judgement on whether logos/text swim.

**Cost.** 2 arms × 2 shots × VEO $0.25 = **$1.00**

---

## H6 — One reference beats two beats four on Klein

**Status: MEASURED** (ADR-089). 1 ref 0.791 · 2 refs 0.766 · 4 refs 0.499, same
prompt and seed. Artifact: `logs/adr089-battery`.

**Scope limit that matters.** Measured on Klein (local FLUX.2), FRONTAL only.
It does **not** transfer to Kontext or Gemini, and every slot decision in
ADRs 093/094/097 that cites it cites it only as "budgets are non-monotonic,
therefore adding an image is not free" — not as a number about those providers.

---

## H7 — The identity scorer inverts rank off-angle

**Status: MEASURED, and it VOIDED other findings** (ADR-092). A real photograph
of the subject in profile scored 0.556; a generated panel the subject confirmed
was not him scored 0.570.

This is why the register has its own metrics at all.

---

## H8 — Canonical-first ordering beats incidental record order

**Claim.** Slot 0 is uploaded as Kling's frontal image; before normalisation it
held whatever the record listed first — on this project a left profile.

**Status: PINNED** (`test_continuity_engine.py`), **REASONED** for effect.

**Falsifier.** Clips generated with a profile at slot 0 are no worse than clips
with the frontal there.

**Instrument.** Operator judgement. There is no honest automatic measure of
"Kling was told the wrong thing about which view is frontal".

**Cost.** 2 arms × 2 shots × KLING_3_0 $0.56 = **$2.24**

---

## H9 — Coverage ordering beats score ordering

**Claim.** Ordering a reference set by identity score fills a small budget with
frontal images and drops the profile, because the scorer floors off-angle.
Coverage ordering keeps the turn.

**Status: PINNED** (`test_reference_set.py`) as an ordering property. The
downstream effect is **REASONED**, and it inherits H7 — a score-ordered arm
cannot be judged by the score that ordered it.

**Falsifier.** A turning shot rendered from a score-ordered set is no worse than
from a coverage-ordered set.

**Cost.** 2 arms × 2 shots × ($0.08 + $0.25) = **$1.32**

---

## What is NOT in this register, and will not be

- **"The pipeline produces good video."** Not a hypothesis; not falsifiable as
  written. Decomposed into the cells above.
- **Anything resting on an off-angle GhostFaceNet score.** ADR-092 removed that
  instrument for those readings; re-adding it under a new name would be the same
  error with better branding.
- **Provider ceilings taken from vendor documentation** (Kontext 6 vs 9, Gemini
  4 vs 8). These need a live capability probe, not a render comparison, and a
  wrong guess here fails closed rather than degrading quality.

## Running it

    # Plan only. Spends nothing, prints every cell and the total.
    .venv/bin/python scripts/evidence_harness.py --plan

    # Execute. The authorised amount must match the plan exactly.
    .venv/bin/python scripts/evidence_harness.py --run H4 --authorize-usd 1.00

Results land in `logs/evidence/<run-id>/` as a manifest, per-cell metrics, and a
contact sheet — because the operator's eye outranks every number in this file.
