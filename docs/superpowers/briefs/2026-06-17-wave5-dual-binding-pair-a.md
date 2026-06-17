# R-BRIEF: wave5-dual-binding-director-brief - Pair-A no-spend dual-character binding direction

PRIORITY: MAJOR        LANE: A (image/identity/realism)
CROSS-CUTTING: no (does not touch auto_approve.py, cinema/context.py, core.py, or web_server.py)
LOCK: none required. CO-SIGN: not required.
PACKET: wave5-dual-binding-director-brief
R-SKILL: ai-video-gen loaded before judging the pipeline/identity direction.

## Decision

Choose Route B as the next spend-ready direction: train/validate an Aria LoRA so
both characters have comparable LoRA-strength identity anchors, then run a
production-sampler dual-character graph with dual PuLID, spatial PuLID masks,
fresh seeds, and committed measurement artifacts.

Do not spend from this brief. It opens no pod runtime, paid API call, LoRA
training, render burn, production code edit, dependency edit, lock action, or
push. The next spending step must be an explicit user authorization that names
the exact burn scope.

Why not pure Route A next: the June 15 addendum says removing the man LoRA leaves
the man under-bound, and masks only confine PuLID attention; they do not make a
weak PuLID-alone identity bind.

Why not just Route A plus masked man LoRA as the primary next direction: that is
a useful placement probe, but it keeps the known asymmetric identity stack. The
man has a global LoRA plus trigger while Aria has only PuLID, so visual bleed
remains the predictable failure mode. Use it only as a bounded diagnostic if the
operator rejects Route B as too large for the next authorized burn.

## Evidence Read This Turn

Route and packet evidence:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 5
# Protocol Capacity Board
wave: 5
valid: true
director    packets=wave5-dual-binding-director-brief status=ready
operator    packets=wave5-dual-binding-operator-review status=blocked
BLOCKING ISSUES
- none
```

Current route:

```text
coordination/mailbox/sent/2026-06-17T08-22-41Z-coordinator-to-all-coordination.md
```

The route asks director to produce a no-spend Pair-A brief, choose Route B,
Route A plus masked-man-LoRA hybrid, or a better bounded mechanism, then send a
fresh verify-request to operator.

Current architecture/source evidence:

- ARCHITECTURE.md:871-888 documents the P1-1 Kontext multi-character branch and
  per-character score surfacing.
- ARCHITECTURE.md:977-991 documents the max-tier multi-LoRA path:
  `_inject_secondary_loras`, trigger prepending, secondary ReActor rescue, and
  unchanged per-character validation.
- cinema/shots/controller.py:330-394 resolves the identity strategy and emits
  `MAX_TIER_MULTI_LORA` when max-tier secondaries carry LoRA assets.
- cinema/shots/controller.py:783-800 passes `secondary_char_refs` into
  `generate_ai_broll`.
- cinema/shots/controller.py:863-873 writes
  `take["metadata"]["identity_per_char"]`.
- phase_c_assembly.py:475-537 implements the current Kontext reference-slot and
  prompt-preservation branch.
- quality_max.py:517-532 prepends primary and secondary LoRA triggers.
- quality_max.py:607-672 chains up to two secondary LoRA nodes and clamps
  secondary LoRA strength to 0.55.
- identity/validator.py:567-625 computes half-crop spatial binding scores and
  requires distinct intended slots from callers.

Experiment/prior evidence:

- docs/superpowers/plans/2026-06-15-dual-char-attn-mask-binding.md:73-80
  records the June 15 empirical addendum: man PuLID-alone stayed around 0.49 at
  the default production graft, man-weight was a dead lever, strength 0.95 made
  the man bind but visually bled into Aria, and the addendum recommends Route B
  sooner or a Route-A plus masked-man-LoRA hybrid.
- docs/HANDOFF-director-2026-06-15-pairA-realism-burn-ADR024-sweep-route-correction.md:29-42
  records the same result as the durable director handoff: realism won, clean
  dual-binding stayed blocked by the global man-LoRA asymmetry, and Route B was
  favored.
- scripts/_prod_dual_lora_pulid.py:1-43 records the production-sampler graft:
  clean production sampler plus FLUX PuLID identity stack, man LoRA, and second
  ApplyPulidFlux node.
- scripts/_max_passBd_masked_lora_pulid.py:1-53 records the diagnostic hybrid:
  man LoRA plus dual PuLID plus masks, with a caveat that masks gate PuLID
  attention, not the global LoRA.

Measurement-artifact caveat:

```text
$ env -u GIT_INDEX_FILE git ls-files logs/halves_rescore_20260615.json logs/halves_rescore_20260615.txt logs/sweep_montage.jpg scripts/_prod_dual_lora_pulid.py scripts/_max_passBd_masked_lora_pulid.py
scripts/_max_passBd_masked_lora_pulid.py
scripts/_prod_dual_lora_pulid.py
```

The historic sweep logs are present locally, but not tracked by git. Therefore
the numeric sweep values are useful prior evidence only. Any later GO/NO-GO
must rerun the committed measurement command and commit the resulting logs or
explicitly label the measurement runtime-unreproducible.

## Rule #12 - Grep The Writes

TARGET SYMBOL: N/A for this brief. This is a planning brief and does not add,
modify, or target a production write path.

Runtime accountability paths were checked instead:

```text
$ nl -ba cinema/shots/controller.py | sed -n '330,394p'
330 def _resolve_identity_strategy(...)
371 if quality_tier == "max":
377     for entry in secondary[:2]:
380         conditioned.append(CharIdentitySpec(
384             fidelity="lora" if sec_lora else "reference",
385             lora_path=sec_lora,
394         tag = MAX_TIER_MULTI_LORA if len(conditioned) > 1 else MAX_TIER_PRIMARY_ONLY

$ nl -ba cinema/shots/controller.py | sed -n '783,800p'
783 result = generate_ai_broll(
799     secondary_char_refs=[c.to_dict() for c in strategy.secondary_specs] or None,

$ nl -ba cinema/shots/controller.py | sed -n '863,873p'
865 per_char = {primary_char_id: identity_score}
866 for spec_c in strategy.secondary_specs:
872     per_char[spec_c.char_id] = sec_result.overall_score
873 take["metadata"]["identity_per_char"] = per_char
```

## Rule #13 - Symmetric / Sibling Audit

SHARED STATE: dual-character identity conditioning and validation.

Audited siblings:

- Kontext multi-character branch: current low/no-pod-spend reference fallback;
  useful for ordinary multi-char keyframes but not the high-fidelity
  production-sampler LoRA/PuLID question.
- Max-tier multi-LoRA branch: current shipped path for registered LoRA
  secondaries; still inherits max-tier over-cook risk for this specific
  photoreal dual-binding target.
- Production graft driver: preserves the clean sampler and binds the man only
  when his global LoRA is present.
- Masked hybrid driver: tests placement/bleed but cannot confine a global LoRA
  because `attn_mask` is a PuLID input.
- Identity binding instrument: half-crop figure-read semantics exist and must
  be pinned with distinct left/right slots before any N=4 GO.

No endpoint, persistent flag, shared lock, or production guard is changed by
this brief.

## Full-Shape Pattern Reference

Future implementation should mirror the full shape of
`scripts/_prod_dual_lora_pulid.py` rather than grafting max-tier post-passes
into production:

- load `pulid.json` directly;
- deep-copy only the needed FLUX identity nodes from `pulid_max.json`;
- keep the production sampler/RealESRGAN chain intact;
- fail before `/prompt` when required nodes, `start_at=0.0`, or clean-sampler
  invariants are missing;
- use `render_leg` or an equivalently timeout-guarded money path;
- use fresh seeds to avoid ComfyUI cache-hit false-fails;
- write committed logs for every verdict-backing number.

For Route B, add only the minimum required Aria LoRA assets/trigger and the
dual-PuLID/mask wiring. Do not call max-tier `_inject_post_passes` in a
production-sampler experiment.

## Selected Mechanism

Recommended later user-authorized sequence:

1. Preflight only, no spend: confirm Aria training inputs, current man LoRA
   artifact, `ApplyPulidFlux.attn_mask`, `LoadImageMask`, model census, and
   local driver invariants.
2. With explicit user approval: train or validate an Aria LoRA with the existing
   LoRA quality gate; persist training status and selected strength/trigger.
3. Build a production-sampler Route B driver using:
   - Aria LoRA plus trigger and Aria PuLID;
   - man LoRA plus trigger and man PuLID;
   - left/right PuLID masks;
   - no max-tier hires-fix, SUPIR, FaceDetailer, or DetailDaemon.
4. Run N=1 smoke with a fresh seed. Read visual first for product truth:
   woman-left, man-right, both photoreal, no over-cook, no masculine bleed on
   Aria.
5. Only if N=1 is visually plausible, run the measurement guard on that single
   artifact, then N=4 seed robustness.

## GO / NITS / FAIL Criteria For Later Spend

Visual primary GO:

- Left figure reads as Aria/woman.
- Right figure reads as the grey-bearded man.
- Both faces are photoreal with production-sampler skin texture.
- No max-tier over-cook, no double-man, no blended face, no clothing/identity
  transfer, no empty or wrong-side figure.

Secondary ArcFace/GhostFaceNet guard:

- `aria-LEFT >= 0.75`.
- `man-RIGHT >= 0.75`.
- Cross-side scores do not indicate bleed, especially man score on Aria's left
  half.
- Scores come from the committed half-crop figure-read instrument, not a
  whole-image fallback or a multi-artifact mixed invocation.

Deterministic figure-selection requirement:

- Use one artifact path or one controlled glob per scorer invocation.
- Require both halves to have OK-classified figure reads for a seed to count.
- Require distinct intended slots: one left, one right.
- Use the current largest-OK face selector and OpenCV single-thread guard from
  identity/validator.py.
- Treat NO_FACE, TINY, DEGENERATE, or cache-hit empty-output artifacts as NITS or
  FAIL until rerun with clean evidence.

N=4 robustness:

- GO requires at least 3/4 strict seeds meeting both visual and metric criteria.
- HOLD/DEFER is acceptable if Route B improves evidence but does not clear the
  bar; do not spend further without a fresh user decision.

## Required Artifacts For A Later User-Authorized Burn

- Brief path: `docs/superpowers/briefs/2026-06-17-wave5-dual-binding-pair-a.md`.
- Driver source for the exact graph used.
- Mask assets or deterministic mask generator, with target resolution stated.
- Aria LoRA training/validation status, selected strength, trigger, and model
  artifact basename.
- Man LoRA artifact basename and strength.
- Pod/object-info preflight output.
- Render logs with seeds, prompt id, output filenames, hashes, runtime, and peak
  VRAM.
- Half-crop identity measurement JSON/TXT in `logs/`, committed if it backs a
  verdict.
- Visual montage or individual output images when user-facing visual judgment is
  needed.
- Operator verification report before any coordinator closeout.

## User-Spend Gates

Stop and ask the user before any of these:

- starting or keeping a pod running;
- uploading to a live pod for a render/training burn;
- FAL/API LoRA training;
- any paid render or image/video generation;
- N=1 or N=4 burn;
- dependency/model download;
- productionizing the experiment driver into the main pipeline.

The ask must name the exact operation, expected artifacts, rough runtime, and
what decision the spend will unlock.

## Operator Verification Request

Please verify this brief, not a render artifact. The requested verdict is
whether the brief is ready to gate a later user-authorized spend/render
decision and whether Route B is the correct next Pair-A direction under the
current source/evidence.
