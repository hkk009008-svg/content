# Live contract canary

The manual GitHub Actions workflow `.github/workflows/live-contract-canary.yml`
runs exactly one explicitly authorized production-boundary check. It is not a
general provider test runner and it does not make a provider production-ready.

There are two selectable targets:

| Target | Boundary | Fixed cost policy |
|---|---|---|
| `runway-act-two` | One Runway Act-Two request using the pinned fixture and durable attempt ledger | estimate `$0.15`; accepted cap `$0.15`–`$0.20` |
| `windows-liveportrait-performance` | One authenticated round trip through the fixed Mac loopback tunnel to the role-bound Windows worker | estimate and cap `$0.00` |

The local FLUX.2 fixed probe and 1/2/4-reference benchmark run through its
guarded Windows package, not this GitHub live-contract workflow.

The successful 2026-08-06 KST install, fixed probe, and sequential
1/2/10-reference benchmark remains preserved as historical evidence in
`logs/worker-benchmarks/windows-flux2-klein/rtx-5070-ti-2026-08-06-v1.summary.json`.
It predates the current official 1/2/4 Klein contract and cannot promote the
current candidate to Ready. In that historical run, the tested 16 GB RTX 5070
Ti worker remained single-concurrency: the
10-reference case peaked at 15,299,448,196 bytes of VRAM use with
1,795,027,580 bytes free, so the result does not authorize parallel GPU work.

## Authorization

Dispatch the workflow only from `main`, select one non-default target, and type
the exact approval phrase:

```text
I APPROVE ONE LIVE CONTRACT CANARY
```

The `live-contract-canary` GitHub environment must require reviewer approval.
The authorization job validates the target, phrase, and finite cost cap before
the protected environment exposes any secret. The live job repeats validation
immediately before the fixed test. Unknown targets, mixed-case phrases,
placeholder credentials, negative/non-finite caps, and caps outside the fixed
target range fail closed.

## Runway boundary

The Runway target requires the protected `RUNWAYML_API_SECRET`. A GitHub
Deployment preclaim and a durable SQLite attempt ledger bind authority to the
exact workflow run, fixture hash, request fingerprint, and provider task ID.
The ledger is restored before a retry and retained for 30 days. An ambiguous or
already-owned provider submission is recovered or refused; it is never replaced
with a second paid request merely because the GitHub job was retried.

The latest accepted Runway boundary evidence is the successful 2026-08-06 KST
run recorded in
`logs/live-contract-canary/runway-act-two-2026-08-06.json`. The repository
record binds the workflow/head, fixture, provider task, one-attempt ledger hash,
deployment authority, artifact retention identity, and reconciled application
cost without retaining provider credentials or generated media.

## Windows LivePortrait boundary

The Windows target requires:

- a temporary self-hosted macOS JIT runner with label
  `content-liveportrait-ephemeral-jit`;
- the exact runner confirmation phrase
  `I CONFIRM EPHEMERAL JIT RUNNER`;
- `PERFORMANCE_COMFYUI_API_KEY` in the protected environment; and
- the fixed endpoint `http://127.0.0.1:18189`, provided by the authenticated
  Mac-to-Windows tunnel.

Before any media upload or prompt submission, the probe requires the exact
`performance-liveportrait` role, tracked workflow/model/revision hashes,
contract digest, startup readiness, and successful execution proof. A generic
ComfyUI health response, an image-worker role, a mismatched manifest, or a
different endpoint is not sufficient.

Remove the temporary runner registration and stop the tunnel after the job.
Never register a persistent shared runner for this workflow.

## Local FLUX.2 boundary

The required local image-worker sequence is install, one fixed probe, a cold
restart, sequential 1/2/4-reference benchmarks, another cold restart, and an
authenticated zero-media shared-readiness check. Every workload submission is
single-concurrency and bound to the tracked candidate, model, revision,
workflow, runtime, input, output, and evidence hashes. No current-contract
Windows execution evidence has been recorded yet.

The repository retains the sanitized summary and hashes. The Windows worker's
`D:\ContentFlux2Klein` evidence tree retains the exact JSON records and small
generated PNGs; the model cache is deliberately not copied into Git. A failed
pre-submission schema check is recorded separately and did not upload media,
submit a prompt, or enqueue GPU work.

## Local preflight

Input validation can run without secrets or network access:

```bash
LIVE_CONTRACT_CANARY_TARGET=windows-liveportrait-performance \
LIVE_CONTRACT_CANARY_APPROVAL='I APPROVE ONE LIVE CONTRACT CANARY' \
LIVE_CONTRACT_CANARY_MAX_COST_USD=0 \
LIVE_CONTRACT_CANARY_WINDOWS_RUNNER_AUTHORIZATION='I CONFIRM EPHEMERAL JIT RUNNER' \
python scripts/live_contract_canary.py check-inputs
```

`check-ready`, `probe-worker`, `verify-runway-fence`, and `run` belong inside
the protected workflow because they require secrets, authority, or live worker
state. Do not paste credentials into shell history, workflow inputs, logs, or
this document.

## Evidence limits

A passing canary proves only the selected contract at the tested commit and
time. It does not prove invoice truth, another worker role, another provider,
future availability, or licensing clearance. A failure or unknown result stays
visible and must not be rewritten as a pass.
