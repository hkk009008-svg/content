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

The Runway target uses SDK `4.14.0` and the official ephemeral-upload API.
Its character image and driving performance are derived locally from the
repository's synthetic, fictional-adult expression sheet and accepted only
when its SHA-256 digest matches the canary constant. The panels are blended
into a cut-free video of exactly three seconds; no captured real-person media
is sent to Runway. Fixture provenance is recorded in
`tests/assets/live_contract/README.md`. A terminal Runway result logs a
sanitized task ID and failure code, and the workflow keeps the complete attempt
ledger as a 30-day artifact even when the test fails. The complete SQLite/WAL
directory is also restored from the most recent target-specific Actions cache,
so an ordinary rerun resumes an accepted task instead of uploading or
submitting again. The protected job re-reads the fixed GitHub Deployment key
for its current run ID and run-attempt immediately before execution; it never
trusts an upstream job output as authority. Fixture construction and ephemeral
uploads finish first. At the final boundary before the provider POST, the
adapter creates one logical-attempt Deployment preclaim, then issues one POST
with SDK retries disabled. Immediately after Runway returns a task ID, it
records that UUID as a Deployment status before any local ledger write or
polling, then appends the provider's terminal success, failure, or cancellation
so the Deployment UI does not remain falsely in progress. A replacement runner
reconstructs its local ledger from that remote task ID and performs retrieval
only. If a runner is lost in the narrow
preclaim/acceptance/checkpoint interval, the Deployment remains but has no task
ID, so every later run fails closed for manual provider reconciliation instead
of risking a second paid task. GitHub Deployments are trusted-writer crash and
retry fencing, not tamper-resistant storage: repository actors with Deployment
write permission can delete them. A new paid attempt needs a new reviewed
logical fixture/fence version and fresh approval; deleting an existing
Deployment is not a retry mechanism. The live authority is restricted to
`refs/heads/main`.

The input gate does not claim to be a provider-side billing limit. The bound is
enforced structurally: a target maps to one immutable pytest selector with a
fixed duration, the runner has a 12-minute timeout, the job has a 15-minute
timeout, and concurrency never cancels an already submitted provider task.
Provider invoices remain the final billing authority.

The RunPod canary caps cover only the fixed generation call. GPU pod uptime,
network volume, image build, registry, and model-transfer charges are separate
infrastructure costs and require their own budget before provisioning.

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

## Reconciled evidence

The fixed Runway canary completed successfully on 2026-08-05 in
[workflow run 30993506462](https://github.com/hkk009008-svg/content/actions/runs/30993506462)
at head `7e82baaa9a6de33bc8893e88f32469cf63f60729`. Runway task
`36a7e1f9-d615-4fb1-ad1e-4de034eea6de` reported `SUCCEEDED` and an actual
provider cost of 15 credits. The downloaded SQLite authority ledger passed
`PRAGMA integrity_check`, recorded one `succeeded` attempt, and reconciled the
configured `$0.15` estimate once. Provider invoices remain authoritative for
the currency value.

The 30-day ledger artifact is `8925181275`, with ZIP digest
`sha256:c9e58784b9049e28c02533b6381d4ee9eb1064ee0356b2f7c624cb85520dcf49`
and expiry `2026-09-04T09:32:02Z`. Deployment authority `5759174510` has a
terminal `success` status for the same task UUID. This evidence does not cover
either RunPod target; those remain unrun until their separately pinned
deployments, credentials, infrastructure budget, and applicable model-license
approval exist.
