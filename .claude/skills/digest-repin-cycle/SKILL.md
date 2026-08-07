---
name: digest-repin-cycle
description: Re-pin a hash-bound Windows deploy package after editing any file inside it — recompute bindings and package_digest, revalidate, ship by SHA, and re-establish execution evidence on the worker. Use when you are about to edit or have edited anything under deploy/windows-*, or when a pin must move. Doctrine (immutable builders, never relabel old evidence) lives in comfyui-mastery; this is only the ordered procedure. For DIAGNOSING why a live hash differs from a pinned one, use check-artifact-that-runs first; for worker start/stop mechanics, windows-worker-ops.
disable-model-invocation: true
---

# Digest re-pin cycle

Every file inside a pinned deploy package is bound by hash in `candidate.json`,
and the whole inventory rolls up into `package_digest`. Editing ANY byte —
including a comment — moves the digest and invalidates the installed candidate.
Never edit installed copies on Windows, never relabel old evidence as current,
and never hand-compute a hash you can recompute with the instrument.

Do this first (EXECUTING HOST: Mac) — validate the instrument on the KNOWN
value before trusting it on the new one. This command applies to packages that
expose `contract.package_digest()` (today: `windows-flux2-lora` only); the
other packages pin per-file (`candidate.json` bindings, `models.json`,
`revisions.json`) — hash those files directly and follow the package README:

```bash
cd /Users/hyungkoookkim/Content/deploy/windows-flux2-lora && \
  /Users/hyungkoookkim/Content/.venv/bin/python -B -c "
import sys; sys.dont_write_bytecode=True
import contract; print(contract.package_digest())"
```

The `-B` is load-bearing: a bare import writes `__pycache__` into the tree and
the exact-set `rglob` inventory fails with a phantom "drifted" error. This trap
caught two different agents in one day.

## The cycle

1. Confirm the CURRENT digest matches the pinned/live value (instrument check
   above). A mismatch here means drift to diagnose FIRST, not a re-pin.
2. Edit the file(s). Prefer subtraction; keep the diff minimal.
3. Recompute each edited file's sha256 and update its `bindings` entry in
   `candidate.json` (and `models.json`/`revisions.json` if touched).
4. Rerun the package's static preflight, then recompute `package_digest` under
   `-B`. Record the old → new digest pair.
5. Run the full backend suite; commit on a branch; merge `--no-ff`; push only
   with explicit user authorization.
6. Hand off to Windows by FULL COMMIT SHA zip (never a branch), with a
   three-way gate the Windows side runs before installing: digest == expected,
   plus 1–2 package-specific invariants. Use `cross-machine-handoff` for the
   brief.
7. On Windows: delete ALL THREE write-once artifacts every time —
   `package\`, `runtime\runtime-receipt.json`, `evidence\install.json`. Do
   not reason about which one is load-bearing this round: the receipt also
   pins TOOLKIT_COMMIT, the live packages snapshot, and the Qwen revision, so
   it can block a re-install even with an untouched `requirements.lock`. Then
   re-run the installer bare (no output redirection) and verify the installed
   digest independently.
8. Re-establish EXECUTION evidence: the install proves bytes, not behavior.
   Probe/benchmark/canary state resets on re-pin — that reset is correct, not
   a regression; old evidence belonged to the old candidate.

## Traps

- **Trap 1 — relabeled evidence.** Readiness resets to `not_installed` after a
  re-pin because prior canary/benchmark evidence belonged to the previous
  digest. Re-earn it; never copy it forward.
- **Trap 2 — live-vs-pinned drift found by a human.** The 2026-08-07 klein
  incident: the worker served a manifest hash from a superseded candidate for
  days. The gate is comparing live `/api/capabilities/ready` hashes against
  the repo pin — run it at session start, not post-mortem.
- **Trap 3 — the digest that moved seven times.** Under active debugging the
  digest changes faster than anyone's memory. Never quote one from memory;
  every brief states digest + SHA together, and SUPERSEDED ones explicitly.

## Red flags (self-check)

- Editing a file inside `deploy/windows-*` "without needing a re-pin".
- An install that "succeeded" without the three write-once deletions after a
  digest move.
- Evidence timestamps older than the digest they claim to prove.
- A handoff naming a branch instead of a SHA.
