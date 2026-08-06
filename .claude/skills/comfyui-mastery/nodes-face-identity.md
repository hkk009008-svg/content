# Reference conditioning and identity evidence

This repository separates generation-time reference conditioning from
post-generation identity evidence. A reference was accepted by the graph does
not prove that the output depicts the intended person.

## FLUX.2 reference conditioning

The hash-bound FLUX.2 Klein builder accepts one to four unique approved regular
files. Each remote reference follows this fixed chain:

```text
LoadImage
  -> ImageScaleToTotalPixels (1 MP, dimensions aligned to 16)
  -> VAEEncode
  -> ReferenceLatent on positive conditioning
  -> ReferenceLatent on negative conditioning
```

Reference chains are appended in caller order. The caller collects the primary
character reference, approved multi-angle references, additional-character
references, and one approved continuity reference, deduplicates them, and caps
the list at four.

There is no mutable per-character weight in this graph. Do not manufacture a
weight, splice an untracked node, or claim that two references have spatially
separate authority. If reference order or selection must change, change the
provider-neutral caller policy, preserve provenance, and create a new artifact
version.

## Input requirements

- Every path must resolve to a regular, non-symlink local file.
- References must be unique after resolution.
- At least one approved reference is required for the explicit local route.
- Upload begins only after exact authenticated worker readiness passes.
- Uploaded remote filenames are treated as untrusted and passed only into the
  hash-bound builder's path validator.

## Post-generation identity validation

`identity/validator.py` is the validation authority. It samples image/video
frames, reads detected faces under the deterministic OpenCV guard, compares
approved character embeddings, and emits per-character diagnostics plus a
concrete `FailureReason`.

Important outcomes include:

- `NO_FACE_DETECTED`, `SMALL_FACE_REGION`, and `FACE_ANGLE_EXTREME`: evidence
  may be inherently weak for that framing; do not translate this into a
  hidden generator adjustment.
- `WRONG_PERSON` or `MULTIPLE_FACES_AMBIGUOUS`: review reference binding,
  framing, and the provider's multi-subject semantics.
- `IDENTITY_UNVERIFIED`: evidence is unavailable or unsuitable. This requires
  manual review/retry policy, never synthetic approval.
- `PASSED`: the measured output cleared the shot-specific threshold; retain
  the score, threshold, references, provider, seed, and artifact hash.

Thresholds live in `identity/types.py`. Do not duplicate or recalibrate them in
a ComfyUI workflow file.

## Continuity

Continuity is provider-neutral and provenance-bound: approved character and
location references, deterministic seeds, prompt/style constraints, and
artifact versions. A prior output is used only when the caller explicitly
approves it as a continuity reference. Do not imply that every consecutive
shot automatically inherits previous pixels.
