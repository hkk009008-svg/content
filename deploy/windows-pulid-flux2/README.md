# PuLID-FLUX2 Klein compatibility gate

This directory is an offline compatibility audit, not a Windows installer,
ComfyUI node, workflow, model downloader, or GPU runner. The pinned public
candidate is **evaluation only**, **incompatible**, and **license blocked**.
Nothing here can mark it production ready.

## Why the published candidate is blocked

- FLUX.2 Klein 4B at the pinned BFL source commit has hidden size 3072, five
  double blocks, and twenty single blocks.
- Both pinned Fayens checkpoints are 1,364,389,800 bytes with 119 F32 tensors.
  Their headers expose `id_former.latents` as `[1, 4, 4096]`, 4096-wide
  injection weights, and legacy `pulid_ca_double.*` / `pulid_ca_single.*`
  names.
- The pinned node source constructs `double_ca.*` / `single_ca.*`, uses a
  permissive state-dict load, and declares random initialization fallbacks for
  mismatched Klein dimensions. A run could therefore succeed while not using
  the trained injection weights.
- The required InsightFace AntelopeV2 pretrained model is restricted to
  noncommercial research unless separately licensed. The node and adapter's
  own license declarations do not remove that dependency restriction.

The exact revisions, artifact sizes, hashes, and observed header facts are in
`candidate.json`.

## What would be needed for a replacement

There is no replacement implementation to validate, so this package does not
invent projection shapes or call them a minimum contract. A future candidate
must first pin its actual runtime implementation. Its attention widths,
projection shapes, and injection map must then be derived from that code.

Only after that can a candidate be checked for strict loading, zero missing or
unexpected injection keys, no random-weight fallback, a hash-bound injection
map, a commercially permissible face model, an independent effect control,
Windows execution, VRAM/latency measurement, restart recovery, and a
benchmark. Until those concrete inputs exist, the replacement gate remains
explicitly unresolved and PuLID is not exposed as a runnable method.

## Offline use

Status only (always exits nonzero because the candidate is blocked):

```powershell
python .\deploy\windows-pulid-flux2\verify.py
```

Header audit (reads the first bounded JSON header and file metadata only):

```powershell
python .\deploy\windows-pulid-flux2\verify.py C:\path\candidate.safetensors
```

Optional `--runtime-audit` and `--face-license` arguments accept local JSON
records. They can expose additional blockers, but self-supplied records are
reported as unverified evidence and cannot yield a static pass or change this
package's `production_ready: false` status. The shipped candidate contract
cannot be replaced through the verifier API.
