# FLUX.2 Klein 4B character LoRA

This package installs and runs one fixed Windows/RTX 5070 Ti character-LoRA
path. The checked-in candidate remains `not_installed` until Windows produces
the install, training, and inference evidence. Nothing starts automatically.

## Install

Run from the Content checkout on the Windows worker. `HF_TOKEN` may be set for
Hugging Face authentication; URLs, revisions, destinations, and hashes are not
caller-controlled.

```powershell
.\deploy\windows-flux2-lora\Install-Candidate.ps1
```

The installer creates these stable paths:

- `%PROGRAMDATA%\Content\IdentityLab\flux2-lora\package\train.py`
- `%PROGRAMDATA%\Content\IdentityLab\flux2-lora\package\candidate.json`
- `%PROGRAMDATA%\Content\IdentityLab\flux2-lora\runtime\venv\Scripts\python.exe`
- `%PROGRAMDATA%\Content\IdentityLab\flux2-lora\runtime\ai-toolkit`
- `%PROGRAMDATA%\Content\IdentityLab\flux2-lora\runtime\models`

It installs the hash-locked Python inventory, checks out the exact AI Toolkit
commit, downloads and verifies the Base 4B transformer, training VAE, and every
Qwen cache file, copies the pinned proven FLUX.2 inference validator, and writes
runtime/model/install receipts. Before recording installation it imports every
direct runtime dependency inside the fixed venv, runs CUDA tensor,
torchvision-CUDA, torchaudio, and AI Toolkit startup smokes, and checks the
exact torch 2.13.0/torchvision 0.28.0/torchaudio 2.11.0 cu130 stack. It never
marks a training or inference canary passed.

## Training contract

The gateway is the only training launcher. `train.py` requires the
gateway-created, hash-bound `training` activity lease for the same deterministic
job ID before it reads GPU state or writes job evidence; there is no standalone
training wrapper.

The job ID is `sha256(canonical UTF-8 API manifest bytes)[:32]`. Its fixed input
directory contains four fully decoded RGB/RGBA PNGs named
`reference-01.png` through `reference-04.png` and these exact captions:

```text
portrait photograph of hkkperson person, identity reference view 1
portrait photograph of hkkperson person, identity reference view 2
portrait photograph of hkkperson person, identity reference view 3
portrait photograph of hkkperson person, identity reference view 4
```

Consent is bound to the complete input set. Training is fixed at 512 buckets,
batch 1, rank/alpha 16, BF16, quantized low-VRAM transformer/text encoder,
gradient checkpointing, disk latent cache, AdamW8bit, seed 0, and 500 steps.
One explicit same-job resume is allowed only from a hash-bound dead process with
the exact 100/200/300/400-step checkpoint and optimizer state.

A passing adapter must contain exactly the 80 pinned Klein block modules as 160
BF16 A/B tensors. Their source-derived rank and base dimensions imply exactly
46,202,880 tensor-data bytes. The adapter filename, tensor inventory, training
inputs/config/package, and proven inference runtime are content-bound in its
metadata.

## Benchmark

The gateway normally starts this benchmark automatically after it validates a
passing training terminal. It replaces the completed training lease with a
separate hash-bound `benchmark` lease and does not mark the job successful until
the benchmark proof passes.

For diagnosis after a passing training terminal, and only while no gateway GPU
activity is active, the same benchmark can be run manually:

```powershell
& "$env:ProgramData\Content\IdentityLab\flux2-lora\package\Benchmark-Candidate.ps1" -JobId <job-id>
```

The benchmark holds the shared GPU activity lease, persists the exact live
`object-info.json`, `control-workflow.json`, and `lora-workflow.json`, then runs
the control and LoRA graphs sequentially with one fixed prompt, seed 0, Euler,
four steps, CFG 1, and 1024x1024 output. It records latency, peak VRAM, and PNG
hashes. Equal outputs are a permanent causality failure. An ambiguous prompt
submission or post-accept outcome is `UNKNOWN`, retains the lease, and is not
automatically retried. Proven pre-submission failures release the lease.

Offline package integrity check:

```powershell
python -B .\deploy\windows-flux2-lora\preflight.py
```
