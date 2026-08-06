# Content program manual

This is the operator's guide to producing, reviewing, debugging, and packaging
a film with Content. It describes current UI and runtime behavior.

## 1. Mental model

A Content project is a durable production record:

```text
Project
  Settings and budget
  Characters and references
  Locations and references
  Scenes
    Shots
      Keyframe takes
      Performance takes
      Motion takes
      Corrections and approvals
  Checkpoint and queue state
  Immutable artifact versions
  Client packages
```

Generation, validation, approval, and delivery are different steps. A provider
returning a file does not approve it. A passing identity score does not prove
motion or audio quality. A packaged file does not rewrite the approved take.

## 2. The four UI pages

### Setup

Setup is where you configure active production behavior:

- Image backend: Gemini multi-reference or, only when live Ready, Local FLUX.2
  Klein 4B.
- Video engines and supported project overrides.
- Identity strictness, retry limit, and coherence threshold.
- Voice, dialogue mode, lipsync validation, and post-processing options.
- Auto-approve policy and budget limit.
- GPU workers: independently reported image and performance capability states,
  queue counts, safe GPU memory fields, hashes/blockers, and refresh action.

Only controls with real backend readers appear. Unsupported stored values are
not painted as a saved choice; the UI shows a blocking alert and requires a
supported selection.

### Edit

Edit is the shot-level production surface. Use it to inspect shot prompts,
references, takes, diagnostics, provider provenance, driving media, and
corrections. Generation buttons are disabled when the relevant durable job or
recovery marker already owns the work.

### Run

Run is the production control room:

- durable queue state, job ID, position, attempt count, checkpoint resume, and
  cancel/recovery actions;
- phase rail, live progress, gates, and failed shots;
- provider success/latency/estimated cost/reservations/unresolved outcomes;
- provider health evidence and AUTO-routing explanation; and
- project-scoped searchable traces.

### Capability

Capability summarizes measured project evidence: identity, coherence, motion,
lipsync, gates, routing provenance, media conformance, and evidence-backed
component engagement. `UNKNOWN` or missing evidence does not become a pass.

Preview contains **Client delivery**, where immutable versions can be inspected,
selected, packaged, and downloaded.

## 3. Production workflow

### Step 1: Create a project

Create a project from the selector and give it a clear production name. All
runtime files are stored under a project-owned directory. Avoid editing project
JSON by hand; the API applies validation, locking, and settings revision checks.

### Step 2: Configure providers and budget

Start with the smallest set of routes you can actually verify:

- Gemini key for the default image route.
- FAL or one primary video provider for motion generation.
- ElevenLabs for dialogue/TTS if the film needs speech.
- Local Windows worker for local image/performance work once Ready.

Set a project budget. Reservations count before a paid request proceeds. The UI
shows reconciled estimates, not invoice truth, so keep provider dashboards and
hard provider-side limits enabled.

### Step 3: Add references

For each recurring character, upload a clear canonical front/three-quarter
image plus useful angles. Prefer consistent lighting, unobstructed facial
features, and one person per reference. Add location references when visual
continuity matters.

Reference quality is the main operator-controlled identity input. Removed
training and graph-tuning mechanisms are not part of the current workflow.

### Step 4: Choose the image route

Gemini multi-reference is the default. It can proceed through the supported safe
cascade only after the prior route's outcome is known terminal.

Local FLUX.2 is appropriate when:

- Setup → GPU workers reports the image role `ready`;
- startup, fixed execution proof, benchmark, hashes, and license state all pass;
- at least one approved local reference exists; and
- you want local execution with no provider charge.

The local workflow accepts 1–4 unique references, including approved character
angles, secondary-character references, and an approved continuity reference.
When explicitly selected, Local FLUX.2 is pinned: a local readiness or execution
problem blocks instead of silently spending on a cloud replacement.

### Step 5: Plan the film

Generate or edit scenes and shots. Confirm framing, camera intent, action,
characters in frame, dialogue, and duration. The continuity engine adds stable
character/location constraints, deterministic scene seeds, and an explicit
approved continuity reference when available.

Approve PLAN only when the shot list is producible. The plan gate is a creative
and spend boundary, not a formality.

### Step 6: Generate and approve keyframes

Each shot produces a versioned keyframe take with backend provenance and
identity evidence where applicable. Compare:

- face and body identity against approved references;
- costume, props, location, and time-of-day continuity;
- composition and aspect ratio;
- prompt intent and unwanted extra subjects; and
- whether the frame is suitable as a motion source.

Approve one keyframe take per shot. An approved keyframe may become an explicit
continuity reference for later shots; the system does not silently chain mutable
previous output.

### Step 7: Add performance capture when needed

Talking or expressive shots need a driving clip. Upload or select it in Edit.
Local LivePortrait requires the independently Ready performance capability.
Cloud adapters remain explicit choices when configured.

Performance output is reviewed separately because a good source keyframe can
still produce poor expression transfer, timing, or identity.

### Step 8: Generate motion

Shot classification and project policy produce a typed video-provider order.
AUTO routing may avoid providers scored unhealthy from recent reconciled global
routing evidence. Unknown/degraded providers remain eligible; explicitly pinned
providers are never overridden by health scoring.

Inspect the actual accepted provider and attempt history. Motion fidelity,
identity, duration, aspect, audio, and media decode are independent checks.

### Step 9: Correct and approve

Use explicit correction actions—regeneration, color work, upscale, face swap,
or lip sync—only when the corresponding feature is configured and the shot
needs it. Corrections create new artifacts/variants; they do not overwrite the
source take.

Approve REVIEW only after the chosen final take has the required identity,
motion, and audio/lipsync evidence. A numeric threshold of zero does not convert
missing or unavailable evidence into a pass.

### Step 10: Assemble and package

The pipeline assembles approved takes, dialogue, music, foley, transitions, and
final media checks. The accepted final export becomes a versioned client
deliverable.

In Preview → Client delivery:

1. Inspect the current and archived versions.
2. Expand recipe/provenance when you need to audit sources or dependencies.
3. Select the desired version for each logical deliverable.
4. Click **Package selected versions**.
5. Retain the displayed package filename and SHA-256 with the client handoff.

The ZIP builder verifies source hashes and excludes internal/runtime/credential
paths. It is deterministic for the same selected exact bytes.

## 4. Durable queue and resume behavior

Clicking Start admits one durable project job. A second click while that project
is queued or running returns the existing job. Queue position is one-based while
waiting.

The worker owns an expiring lease and heartbeat. If the app crashes:

1. the running lease expires;
2. the row becomes resumable;
3. a new worker claims the same job; and
4. the pipeline resumes from its project checkpoint.

This prevents a server restart from starting an entirely new film run. It does
not prove that every external provider request is safe to repeat; provider and
local GPU attempts have their own durable IDs and recovery state.

If the UI offers **Abandon blocked job**, verify no worker/provider job is still
active. Abandon closes an expired unverifiable queue row but cannot recall a
late external result.

## 5. UNKNOWN and manual reconciliation

Treat `UNKNOWN` as a first-class outcome. It means the request may have crossed
an acceptance boundary, but the application cannot yet prove its final state.

For a paid provider or local GPU job:

- do not click Generate again;
- do not change provider to force a fallback;
- do not delete its ledger/sidecar;
- use the exact resume/reconcile action shown in Review; and
- inspect provider or worker history for the recorded job/prompt ID.

Only a safely terminal unbilled rejection permits a different provider without
manual reconciliation. This is how the system avoids duplicate paid or GPU
work after timeouts and crashes.

## 6. Provider analytics and health

Run → Provider health offers two evidence scopes:

- **This project:** outcomes and estimates attributed to the active project.
- **Global routing history:** evidence used for AUTO base-video health avoidance.

For each provider, the UI shows success rate, p95 terminal latency, estimated
usage, active reservations, outcome sample count, unresolved accepted jobs,
health score/state, and reason codes.

Interpretation:

- `healthy`: enough recent evidence and no configured failure/latency trigger.
- `degraded`: usable but evidence indicates caution.
- `unhealthy`: AUTO base-video routing avoids it.
- `unknown`: insufficient, malformed, or non-finite evidence; never painted
  healthy by default.

Explicit provider pins remain operator authority. Health scoring does not
silently reroute them.

## 7. Searchable traces

Run → Searchable traces indexes safe structured events for the current project.
Search message/fields, filter Warning/Error/Critical, or paste an exact trace
ID. Queue jobs use their job ID as the primary run correlation ID.

Use traces to answer:

- Which provider and shot failed?
- Did the request reach acceptance?
- Why did routing skip a provider?
- Which queue attempt resumed?
- Where did a gate or artifact publication stop?

The index is bounded local SQLite. Stdout remains authoritative for deployment
logs, and this feature is not a hosted observability service.

## 8. Artifact reproducibility

Every version record preserves:

- exact output SHA-256 and byte size;
- logical name/version and media type;
- provider/model identity when applicable;
- normalized parameters;
- source and dependency hashes; and
- a reproducibility status/note.

`bit_exact=false` is intentional for stochastic provider work. Exact historic
bytes remain available, and the recipe supports auditing/replay, but a future
provider invocation may generate different pixels or frames.

## 9. Local GPU operating rules

The Windows gateway reports image and performance roles independently. One role
being Ready cannot upgrade the other.

Before installing, probing, benchmarking, warming, or restarting the worker:

- stop competing RTX workloads;
- ensure ComfyUI has an empty queue;
- ensure the model/cache and state volumes have enough space;
- use the tracked package and exact state root; and
- keep bearer credentials out of command output and tracked files.

The FLUX.2 sequence is install → fixed probe → sequential 1/2/4 benchmark →
Ready. The LivePortrait readiness record includes its own fixed execution proof.
Both application adapters persist exact Comfy prompt IDs. One Comfy process
still means one physical execution queue.

## 10. Auto-approve guidance

Auto-approve is useful only after you have calibrated the project. Start with
human review and inspect false positives/negatives.

- PLAN requires an approved director decision with no blocking violations.
- IMAGE evaluates the available measured quality/identity signal and whether a
  fallback occurred.
- MOTION uses configured identity and motion evidence when enabled.
- FINAL evaluates measured lipsync where applicable and can require a human if
  an upstream gate auto-approved.

Unknown, failed, unavailable, or non-finite applicable evidence remains a veto
or manual-review condition.

## 11. Practical quality recipes

### Strong recurring identity

1. Use clear real references with varied useful angles.
2. Keep one canonical identity description across scenes.
3. Raise identity strictness gradually after measuring normal scores.
4. Approve the strongest keyframe, not merely the newest.
5. Use an approved continuity reference for related later shots.
6. Regenerate a bad frame before motion; motion rarely repairs a weak source.

### Consistent multi-character scenes

1. Give each in-frame character a distinct canonical reference.
2. Keep names, wardrobe, side of frame, and action explicit in shot prompts.
3. Inspect every face; one good primary score does not prove the secondary.
4. Use local FLUX.2 only after the 4-reference benchmark passed on the exact
   worker, and keep every shot within the official Klein reference limit.

### Lower spend risk

1. Keep the full-project queue concurrency at one.
2. Set a project budget and provider-side hard limits.
3. Resolve every UNKNOWN before retrying.
4. Use local Ready routes where their quality fits the shot.
5. Package approved versions instead of regenerating delivery media.

### Easier debugging

1. Note the queue job ID and shot ID.
2. Search traces by that ID.
3. Check provider analytics for unresolved attempts and health reasons.
4. Inspect artifact recipe/source hashes.
5. Reproduce offline contract failures before authorizing another live call.

## 12. Failure guide

| Symptom | Correct response |
| --- | --- |
| Local image option disabled | Refresh GPU workers and resolve the exact blocker; do not edit project JSON. |
| Worker reachable, not Ready | Verify authenticated capability, hashes, state root, probe, benchmark, and license evidence. |
| Image backend unsupported | Select Gemini, or live Ready Local FLUX.2. |
| Job already queued/running | Monitor the existing job; do not start another. |
| Provider/local result UNKNOWN | Resume/reconcile the exact durable ID and suppress replacement. |
| Provider health unhealthy | AUTO base-video avoids it; inspect evidence before explicitly pinning it. |
| No provider history | Generate terminal attempts or verify the attempt database path. |
| Trace search empty | Verify project scope, filters, and trace database writability. |
| Artifact package rejected | Fix missing/hash-drifted/non-deliverable files; do not bypass the allowlist. |
| Settings revision conflict | Reload current settings and reapply the intended change. |

## 13. What the system does not claim

- Estimated usage is not provider invoice truth.
- Local GPU work has no provider charge but still consumes power and hardware.
- A recipe does not guarantee bit-exact stochastic regeneration.
- Local searchable traces are not an external logging platform.
- AUTO health avoidance does not override explicit provider choices.
- Static manifests, open ports, and old evidence do not prove worker readiness.
- Historical fields or artifacts do not restore removed product capabilities.

## 14. Before delivering a project

- All intended shots have one approved final take.
- Applicable identity, motion, lipsync, and media evidence is Pass—not Unknown.
- No durable provider/local attempts remain unresolved.
- Queue state is terminal and checkpoints are complete.
- Provider estimates have been compared with provider dashboards.
- Desired immutable versions are selected.
- Client package downloads successfully and its SHA-256 is recorded.
- Source project and evidence remain archived separately from the delivery ZIP.
