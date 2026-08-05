# Live contract canary

The `Live contract canary` GitHub Actions workflow is the only CI lane for the
three paid or externally hosted release boundaries below. It is manual-only,
runs exactly one fixed test, and cannot spend with its default inputs.

Configure a protected GitHub environment named `live-contract-canary` with
required reviewers and prevent administrators from bypassing its protection.
Store these environment secrets:

- `RUNWAYML_API_SECRET` for `runway-act-two`.
- `COMFYUI_SERVER_URL` and `COMFYUI_API_KEY` for
  `runpod-pulid-production`. This must identify the pinned production image,
  whose live contract is the repository's `pulid.json` graph.
- `PERFORMANCE_COMFYUI_SERVER_URL` and `PERFORMANCE_COMFYUI_API_KEY` for
  `runpod-liveportrait-performance`. This must identify a separately deployed
  performance image that includes LivePortrait and Video Helper Suite nodes.

Both URLs must be credential-free HTTPS origins of authenticated gateways,
and both tokens must contain at least 32 characters. Do not point the
performance variables at the pinned production PuLID endpoint: that image does
not claim a LivePortrait contract.

To dispatch one run from the Actions UI:

1. Select exactly one target. Leaving `none` selected fails before protected
   environment access.
2. Enter the approval phrase exactly: `I APPROVE ONE LIVE CONTRACT CANARY`.
3. Enter a finite maximum cost. Runway's fixed three-second canary is estimated
   at `$0.15` and accepts `$0.15` through `$0.20`. The production PuLID image
   canary is estimated at `$0.04` and accepts `$0.04` through `$0.05`. The
   fixed two-second LivePortrait performance canary is estimated at `$0.03`
   and accepts `$0.03` through `$0.05`.
4. A required reviewer approves access to the protected environment.

The input gate does not claim to be a provider-side billing limit. The bound is
enforced structurally: a target maps to one immutable pytest selector with a
fixed duration, the runner has a 12-minute timeout, the job has a 15-minute
timeout, and concurrency never cancels an already submitted provider task.
Provider invoices remain the final billing authority.

Any configured provider that returns no output, rejects the fixture, lacks a
required node, times out, or produces an invalid artifact fails the canary.
Skipping is reserved for a target that was not selected or a provider that was
not configured; the protected workflow's preflight rejects both conditions, so
a dispatched live test must end in pass or failure.

Each RunPod test follows a real application adapter path. The production target
loads and submits the repository's shipping `pulid.json`; the performance
target submits the LivePortrait workflow only to its separately configured
endpoint. A gateway health response alone is insufficient: authorization,
workflow queueing, polling, artifact download, and validation must all work
through the selected deployed boundary.
