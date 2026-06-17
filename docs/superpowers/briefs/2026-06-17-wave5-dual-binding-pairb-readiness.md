# Director2 Brief - Wave 5 Pair-B Dual-Binding Spend Readiness

Generated: `2026-06-17T08:27:31Z`
Seat: `director2`
Wave: `5`
Cycle: `2026-06-17-wave5-dual-character-binding-planning-a`
Packet: `wave5-dual-binding-director2-readiness`
Row: `capability-dual-binding-spend-readiness`

## Disposition

This is a no-spend readiness brief, not authorization to burn. Pair-B is ready
for operator2 review of the side-effect gates and artifact contract for any
later dual-binding render or LoRA-training burn.

Cross-cutting: no. The brief does not touch `auto_approve.py`,
`cinema/context.py`, `core.py`, or `web_server.py`.

Lock: none.

Production edits: none.

User-gated side effects remain closed: push, pod start/runtime, paid API calls,
LoRA training, production generation, dependency edits, and inventory
transitions.

## Evidence Read

Coordinator route:

```text
$ sed -n '1,320p' coordination/mailbox/sent/2026-06-17T08-22-41Z-coordinator-to-all-coordination.md
director2: produce a no-spend Pair-B readiness brief for any later dual-binding render or LoRA-training burn.
Cover pod preflight, idle-stop discipline, budget/cost caveats, required user authorization, and measurement artifacts.
Then send a fresh director2 -> operator2 verify-request naming the brief.
Boundaries: no push, lock claim, paid API spend, pod spend, dependency edit, production generation, LoRA training, render burn, inventory transition, or production pipeline edit.
```

Packet acceptance:

```text
$ sed -n '1,220p' coordination/capacity/packets/wave5-dual-binding-director2-readiness.json
allowed_paths: docs/superpowers/briefs, docs/HANDOFF-director2-*.md
acceptance: read OPERATIONS.md pod setup and idle-cost sections, PROGRAM-MANUAL capability-max spend caveats, current cost/pod source touchpoints, and Pair-A dual-binding plan; produce readiness brief; send verify-request.
```

Operations and manual evidence:

```text
$ sed -n '200,320p' OPERATIONS.md
Pod setup requires a ComfyUI pod for production/max tier; setup_runpod.sh installs PuLID-FLUX nodes and optional max-tier nodes; idle pods cost real money and must be autoscaled or manually stopped.

$ sed -n '390,535p' OPERATIONS.md
Cost DB is EXPERIMENTS_DB_PATH; COMFYUI pod failures are checked through COMFYUI_SERVER_URL/object_info; rough costs include RunPod pod time and commercial video/audio/API providers; budget control is global_settings.budget_limit_usd.

$ sed -n '80,155p' docs/PROGRAM-MANUAL.md
The program target is finished photoreal cinematic video with identity continuity, quality gates, tuning knobs, and bill tracking through CostTracker.
```

Current source touchpoints:

```text
$ sed -n '1,130p' phase_c_assembly.py
RunPodComfyUI wraps /upload/image, /prompt, /view, and /history; ImageGenResult records the backend that actually ran.

$ sed -n '779,905p' web_server.py
POST /api/projects/<pid>/characters/<cid>/train-lora starts background LoRA training only with at least 15 refs and exposes GET .../lora-status.

$ sed -n '388,480p' cost_tracker.py
record_api_call maps COMFYUI_PULID and QUALITY_MAX to provider "comfyui"; would_exceed and would_exceed_cost are the pre-spend budget checks.

$ sed -n '310,405p' cinema/shots/controller.py
Max-tier multi-character shots collect primary plus up to two secondary identity specs; secondaries receive LoRA metadata when registered.

$ sed -n '980,1010p' ARCHITECTURE.md
Max-tier multi-character flow chains secondary LoRAs, prepends triggers, and injects secondary face-swap rescue.
```

Pair-A dual-binding plan evidence:

```text
$ sed -n '1,260p' docs/superpowers/plans/2026-06-15-dual-char-attn-mask-binding.md
Empirical addendum: Route A masked PuLID alone likely under-binds the man; stronger next options are Route B or a Route-A plus masked-man-LoRA hybrid. Pod must be started, ComfyUI up, and user spend-authorized before any render or train.

$ sed -n '1,125p' scripts/_max_passBd_masked_lora_pulid.py
The current masked Design-D driver requires the pod running and ComfyUI up, runs N=1 then N=4, scores halves first with _arc_score_session.py, and treats visual two-distinct identity as mandatory.
```

Cost caveat surfaced during this brief:

```text
$ rg -n "flux-lora-fast-training|record_api_call|CostTracker|FAL|fal_client.subscribe" prep scripts web_server.py cost_tracker.py -g '*.py'
scripts/_fal_man_lora_train.py records FLUX_KONTEXT reference-generation costs, then calls fal-ai/flux-lora-fast-training; no adjacent CostTracker.record_api_call for the training fee was found in the grep result.
```

This is a future guardrail question, not a production patch in this planning
cycle. If the later chosen route uses direct FAL LoRA training, the spend ledger
must manually capture the training fee or a new director2 brief should route a
cost-tracking fix before relying on automated budget evidence.

## Readiness Contract For A Later User-Authorized Burn

### 1. Required Authorization

A later burn must start only after an explicit user-principal authorization that
names:

- route: render-only, LoRA-training, or both;
- scope: scripts/driver, project, character ids, seed count, and whether N=1
  smoke may continue to N=4;
- spend cap: pod runtime cap plus any paid API/training cap;
- stop condition: exact GO/HOLD/NO-GO thresholds and whether to stop after N=1.

No authorization is inherited from this planning brief.

### 2. Free Local Preflight Before Spend

Before starting or using a pod:

- confirm working tree scope and branch with `env -u GIT_INDEX_FILE git status --short --branch`;
- confirm the selected Pair-A route and artifact paths;
- confirm character reference paths exist;
- confirm the driver is the intended no-spend/offline graph construction path until `/prompt`;
- run no-spend import or local preflight where applicable, such as
  `scripts/_max_harness_preflight.py`, understanding that it only proves local
  imports/scoring/backend construction and environment readiness.

If local preflight fails, do not start pod spend.

### 3. Pod Preflight

If user authorization includes pod runtime:

- record pod provider, pod id, start time, intended max runtime, and who is
  responsible for stopping it;
- set and verify `COMFYUI_SERVER_URL`;
- check pod health through `/object_info` and `/system_stats`;
- if provisioning from scratch, use `scripts/setup_runpod.sh` and verify the
  torch/CUDA channel against `nvidia-smi`;
- verify required node classes before any `/prompt`: at minimum
  `ApplyPulidFlux`, `PulidFluxModelLoader`, `PulidInsightFaceLoader`,
  `LoraLoader`, and the mask nodes used by the selected driver;
- verify required LoRA files are present in ComfyUI's `loras/` directory by
  basename before submitting a LoRA-dependent graph;
- verify any mask dimensions match the latent size the driver uses, not the
  upscaled output size.

If any check fails, stop before generation and either fix offline or request a
new authorization scope.

### 4. Idle-Stop Discipline

Pod runtime is external money. A later burn must include:

- a live stop owner named before pod start;
- a stop-after-N=1 checkpoint unless the user authorized automatic N=4
  continuation;
- immediate pod stop or autoscale-to-zero after artifacts are retrieved;
- durable stop evidence: timestamp, provider state, and whether any process was
  left running;
- no handoff while a pod is billing unless the handoff explicitly names the
  person responsible for stopping it and the user has accepted that risk.

### 5. Budget And Cost Caveats

Application cost tracking is necessary but not sufficient:

- `global_settings.budget_limit_usd = 0` means no cap; a later run should use a
  finite cap when it is driven through the project pipeline;
- `CostTracker.would_exceed` and `would_exceed_cost` guard known estimated API
  costs, but external pod idle time is not automatically bounded by them;
- `record_api_call` distinguishes `COMFYUI_PULID` and `QUALITY_MAX` as
  `provider="comfyui"` in `cost_log`;
- direct FAL LoRA scripts need explicit cost ledger coverage before their
  numbers back a GO/NO-GO claim;
- if a missing automated cost guard becomes material, open a future
  production-fix brief instead of silently treating manual accounting as
  equivalent to a gate.

### 6. Measurement Artifacts

Any later GO/HOLD/NO-GO claim must be backed by committed scripts and `logs/`
artifacts per R-MEASURE. Required artifact contract:

- render inputs: driver path, seed list, mask files if any, character refs, LoRA
  basename/checksum, route chosen by Pair-A;
- render outputs: retrieved images/videos in `logs/` or an explicitly named
  artifact folder;
- identity scores: `_arc_score_session.py --halves` JSON with finite per-half
  ArcFace scores for intended slots;
- visual verdict: a short persisted JSON or markdown artifact naming whether
  the woman-left/man-right visual read passed, separate from embeddings;
- cost ledger: pod start/stop times, estimated and observed API/training costs,
  and any CostTracker export or manual billing source used;
- LoRA-training runs: dataset manifest, training status, best strength, quality
  score, rejection/warning flags, LoRA checksum, trigger token, and registration
  diff;
- product-oracle closure, if a coordinator later asks to close a wave, must use
  the current product-oracle gate contract and not substitute a chat verdict.

## Operator2 Verification Request

Please verify whether this brief is safe for a later user-authorized
spend/render decision. Suggested operator2 checks:

- side-effect gates are explicit and no current spend/render/training is opened;
- pod preflight covers setup, health, required nodes, LoRA placement, and
  failure-stop behavior;
- idle-stop discipline is concrete enough for a handoff while money is at risk;
- budget caveats distinguish CostTracker-covered API costs from external pod
  idle time and direct training fees;
- measurement artifacts satisfy R-MEASURE and are non-vacuous for visual and
  ArcFace claims;
- any surfaced missing guardrail is routed as future work, not patched in this
  planning cycle.
