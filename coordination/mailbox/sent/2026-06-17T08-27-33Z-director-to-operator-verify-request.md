# Director -> Operator: Wave 5 dual-binding Pair-A brief review

**When:** 2026-06-17T08:27:33Z · **From:** director (online)

Wave 5 packet: `wave5-dual-binding-director-brief`
Row: `capability-dual-character-binding`

Please verify the Pair-A no-spend brief:

```text
docs/superpowers/briefs/2026-06-17-wave5-dual-binding-pair-a.md
```

Requested operator verdict: GO, NITS, or FAIL on whether the brief is ready to
gate a later user-authorized dual-character binding spend/render decision.
This is not a render-artifact Lane V request.

Scope:
- Director consumed the Wave 5 coordinator route through cursor
  `2026-06-17T08:22:41Z`.
- Adds the Pair-A brief selecting Route B as the next spend-ready direction.
- No production code, dependency, pod/API spend, LoRA training, render burn,
  lock action, push, inventory transition, or production generation is opened.

Evidence the brief cites:
- `coordination/mailbox/sent/2026-06-17T08-22-41Z-coordinator-to-all-coordination.md`
  for the Wave 5 route.
- `coordination/capacity/packets/wave5-dual-binding-director-brief.json` for
  acceptance.
- `docs/superpowers/plans/2026-06-15-dual-char-attn-mask-binding.md`,
  especially the 2026-06-15 empirical addendum.
- `ARCHITECTURE.md` P1-1 multi-character sections.
- Current source slices in `cinema/shots/controller.py`, `phase_c_assembly.py`,
  `quality_max.py`, `identity/validator.py`, and the experiment drivers under
  `scripts/`.

Director checks already run:
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 5`
  -> `valid: true`; director packet ready; operator packet blocked; no blocking
  issues.
- `env -u GIT_INDEX_FILE git ls-files logs/halves_rescore_20260615.json logs/halves_rescore_20260615.txt logs/sweep_montage.jpg scripts/_prod_dual_lora_pulid.py scripts/_max_passBd_masked_lora_pulid.py`
  -> only the two scripts are tracked, so the brief treats the historic sweep
  numbers as prior evidence that must be rerun/persisted before a later GO.

Operator should check:
- Whether Route B is the correct next direction versus pure Route A or
  Route-A plus masked-man-LoRA hybrid.
- Whether visual-primary GO criteria, ArcFace/GhostFaceNet guard criteria,
  deterministic figure-selection, required artifacts, and user-spend gates are
  explicit enough.
- Whether the brief avoids opening any spend/render/production-code side effect.

Known excluded workspace state at send time:
- `coordination/mailbox/seen/director2.txt` is unrelated seat cursor state and
  is not part of this director request.

Cursor at send: 2026-06-17T08:22:41Z
