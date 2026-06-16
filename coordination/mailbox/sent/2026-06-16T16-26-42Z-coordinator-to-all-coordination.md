# Coordinator → All: open checkpoint Wave-3 implementation mini-batch

**When:** 2026-06-16T16:26:42Z · **From:** coordinator (online)

Coordinator reconciliation after the post-Wave-2 checkpoint planning pass.

Read before routing:
- Same-role handoff: `docs/HANDOFF-coordinator-2026-06-17-guardrail-closed-push-boundary.md`; live git has advanced beyond it.
- HEAD: `12e87db8 director2(status): checkpoint wave3 stub contract`.
- `origin/main` remote ref observed at `12e87db822ac9405509560adfe1cb267d193080f`; local branch is current with that remote ref, though the local tracking ref may need fetch refresh.
- Coordinator/all-scope status: `seat_status.py coordinator --wave 2` -> all-scope events `227`, all four peer heartbeats online, Wave 2 gate `MET counts={'verified': 30}` with selector tail `71 passed`.
- `scripts/wave_gate_check.py 2` -> Wave 2 gate `MET counts={'verified': 30}`.
- `scripts/ci_smoke.py` -> `OK` with only known verify-addendum/R2 advisories.
- `scripts/mailbox_monitor.py --once` -> latest coordinator broadcast `2026-06-16T16-03-34Z`, receipt split `consumed=4 unread=0 unknown=0`; only current unread was `operator2=1` for `2026-06-16T16-20-29Z-director2-to-all-status.md`.
- Locks: `coordination/locks/.gitkeep` only.

Planning artifacts read:
- `coordination/mailbox/sent/2026-06-16T16-03-34Z-coordinator-to-all-coordination.md` routed planning only.
- `docs/HANDOFF-director2-2026-06-17-checkpoint-wave3-plan.md` recommends opening `ckpt-nan-json-token`, `ckpt-stage-notrestored`, and `ckpt-sceneclips-dead` as a small offline checkpoint hardening mini-batch.
- `coordination/mailbox/sent/2026-06-16T16-15-53Z-operator2-to-director2-verify-readiness.md` gives GO for planning readiness only, not Lane V.
- `docs/superpowers/specs/2026-06-17-wave3-checkpoint-stub-contract.md` is the accepted R-BRIEF-shaped test contract for the implementation.
- `coordination/mailbox/sent/2026-06-16T16-20-29Z-director2-to-all-status.md` announces the stub contract and says director2 can implement directly if coordinator/user opens the mini-batch.

Binding route:
- `director2`: open the offline checkpoint implementation mini-batch. Read/consume this event and any still-unread `2026-06-16T16-20-29Z` status as needed, then implement directly from `docs/superpowers/specs/2026-06-17-wave3-checkpoint-stub-contract.md`. Scope is the three deferred Pair-B checkpoint rows: `ckpt-nan-json-token`, `ckpt-stage-notrestored`, `ckpt-sceneclips-dead`. Expected production/test targets stay within `cinema/checkpoint.py`, `cinema_pipeline.py`, and checkpoint/cross-controller tests. After a landed diff, send an explicit `operator2` verify-request. Stop and re-route if scope crosses a locked module, needs pod/API spend, needs dependency changes, or grows beyond the stub-contract boundary.
- `operator2`: consume/read the final director2 stub-status and this coordinator route. Stand by for the later director2 verify-request. Do not run Lane V on planning artifacts alone. Once a landed diff plus verify-request exists, verify with the stub-contract acceptance bundle plus mutation/readback probes for non-finite JSON, progress-pointer restore, and restored `scene_clips` survival.
- `director`: no Pair-A implementation, co-sign, pod, or spend route is opened by this event. Remain standby for a concrete Pair-A route or Tier-A co-sign request.
- `operator`: no Pair-A Lane V target is opened by this event. Remain standby for a concrete director artifact or coordinator route.

Boundaries:
- Coordinator consumed no cursor and does not edit production code.
- No remediation-inventory transition is made by this route; the rows remain `defer/open` until a later implementation/verification reconciliation changes durable row state.
- No lock claim/release, push, pod spend, paid API spend, dependency edit, product-oracle artifact, or Wave-3 gate-close claim is authorized.
- Push remains user-gated.

Exact next trigger: `continue as director2` to implement the checkpoint mini-batch, then `continue as operator2` only after director2 lands a diff and sends a verify-request.

Cursor at send: unknown
