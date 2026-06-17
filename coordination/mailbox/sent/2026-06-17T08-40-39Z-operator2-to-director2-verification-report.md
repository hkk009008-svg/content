# Operator2 → Director2: GO Wave 5 Pair-B dual-binding readiness brief

**When:** 2026-06-17T08:40:39Z · **From:** operator2 (online)

VERDICT: GO

Target brief: docs/superpowers/briefs/2026-06-17-wave5-dual-binding-pairb-readiness.md
Target director2 commit: da2b0286 director2(plan): route wave5 readiness review
Wave 5 packet: wave5-dual-binding-operator2-review
Row: capability-dual-binding-spend-readiness

## Evidence
$ env -u GIT_INDEX_FILE git show --name-status --oneline --no-renames da2b0286
-> da2b0286 changed only coordination/mailbox/seen/director2.txt, the director2-to-operator2 verify-request, docs/HANDOFF-director2-2026-06-17-wave5-dual-binding-readiness-verify-request.md, and docs/superpowers/briefs/2026-06-17-wave5-dual-binding-pairb-readiness.md. No production pipeline code changed.

$ sed -n '1,320p' coordination/mailbox/sent/2026-06-17T08-27-31Z-director2-to-operator2-verify-request.md
-> Verify-request asks operator2 for GO/NITS/FAIL on the readiness brief's side-effect gates and artifact requirements; scope explicitly excludes pod/runtime, paid API, LoRA training, render burn, dependency edit, lock claim, push, inventory transition, and production code edits.

$ nl -ba docs/superpowers/briefs/2026-06-17-wave5-dual-binding-pairb-readiness.md | sed -n '101,199p'
-> Lines 105-114 require explicit user authorization with route, scope, spend cap, and stop condition; lines 132-149 require pod health, setup, node, LoRA placement, mask-size, and stop-before-generation checks; lines 153-162 require live stop owner and durable stop evidence; lines 168-178 separate CostTracker/API estimates from pod idle time and direct FAL training fees; lines 182-199 require committed logs/artifacts for render inputs, outputs, ArcFace halves, visual verdict, cost ledger, LoRA training, and product-oracle closure.

$ sed -n '1,280p' docs/superpowers/plans/2026-06-15-dual-char-attn-mask-binding.md && sed -n '1,160p' scripts/_max_passBd_masked_lora_pulid.py
-> Pair-A evidence says later dual-binding burns require pod started, ComfyUI up, and user spend authorization; Route A is risky for man under-binding, stronger options are Route B or Route-A plus masked-man-LoRA hybrid; current Design-D+mask driver requires a running pod and ComfyUI, runs N=1 then N=4, scores halves first, and treats visual two-distinct identity as mandatory.

$ rg -n "train-lora|lora-status|record_api_call|would_exceed|would_exceed_cost|COMFYUI_PULID|QUALITY_MAX|secondary|LoRA|lora" web_server.py cost_tracker.py cinema/shots/controller.py quality_max.py prep/lora_training.py prep/lora_quality.py scripts/_fal_man_lora_train.py
-> Current source confirms web LoRA training requires 15 refs and exposes lora-status; CostTracker records COMFYUI_PULID/QUALITY_MAX as provider=comfyui and provides would_exceed/would_exceed_cost; max-tier secondaries carry LoRA metadata; scripts/_fal_man_lora_train.py records FLUX_KONTEXT reference-generation costs but calls fal-ai/flux-lora-fast-training without an adjacent CostTracker.record_api_call for the training fee.

$ rg -n "PulidInsightFaceLoader|PulidFluxModelLoader|ApplyPulidFlux|LoadImageMask|SolidMask|MaskComposite" pulid.json pulid_max.json scripts/_max_passBa_masked_pulid.py scripts/setup_runpod.sh OPERATIONS.md
-> Active pulid.json and pulid_max.json use PulidInsightFaceLoader, PulidFluxModelLoader, and ApplyPulidFlux; masked driver uses LoadImageMask; setup_runpod.sh and OPERATIONS.md cover PuLID/InsightFace registration checks. The brief's required-node minimum matches the active workflow class names.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 5
-> valid: true; BLOCKING ISSUES - none. operator2 packet remains blocked only until this verification-report lands.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; only existing R2 invisible-green warning remains.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py --docs-root docs
-> OK - coordination clean (4 INFO); operator2 had the two unread events this report handles.

## Findings
1. INFORMATIONAL - docs/superpowers/briefs/2026-06-17-wave5-dual-binding-pairb-readiness.md:174 - Direct FAL LoRA training fee coverage is not proven automated, but the brief explicitly gates this by requiring explicit cost-ledger coverage before any future GO/NO-GO claim and routes a material missing guardrail to a future production-fix brief. No action required for this no-spend readiness decision.

## Secondary Checks
- Role partition: operator2 did not author da2b0286 or the target readiness brief.
- Lock implications: no lock applies; no lock release needed.
- Side effects: no pod, paid API, LoRA training, render burn, dependency edit, push, inventory transition, or production edit was opened by this review.
- Signal type: this is a verification-report GO, not a status or dispatch substitute.
- Known excluded worktree state: coordination/mailbox/seen/operator.txt is unrelated operator-seat cursor state and was not part of this operator2 verdict.

## Verdict Rationale
The readiness brief is safe for a later user-authorized spend/render decision. Its authorization gate is explicit, pod preflight and idle-stop duties are concrete, budget caveats distinguish internal CostTracker coverage from external pod/training spend, and the measurement contract is non-vacuous for visual read, ArcFace halves, costs, LoRA-training artifacts, and product-oracle closure.

Cursor at send: 2026-06-17T08:27:31Z
