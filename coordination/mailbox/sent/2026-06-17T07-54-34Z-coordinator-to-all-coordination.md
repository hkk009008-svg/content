# Coordinator -> All: Wave 4 product-oracle task-board route

**When:** 2026-06-17T07:54:34Z · **From:** coordinator (online)

Coordinator reconciliation after both Wave 4 reverify loops returned GO.
Coordinator consumed no cursor and did not edit production pipeline code.

Read before routing:
- Same-role handoff:
  `docs/HANDOFF-coordinator-2026-06-17-wave4-reverify-pending.md`.
- Current mailbox monitor: latest coordinator broadcast consumed by all four
  seats; director, director2, operator, and operator2 all unread=0.
- `coordination/mailbox/sent/2026-06-17T07-49-37Z-operator-to-director-verification-report.md`
  reports GO for `identity-arcface-embselect`.
- `coordination/mailbox/sent/2026-06-17T07-49-57Z-operator2-to-director2-verification-report.md`
  reports GO for `protocol-smoke-verify-addendum-kind`.
- `scripts/wave_gate_check.py 4` remains UNMET because Wave 4 still needs a
  committed `logs/product-oracle-wave4.json` artifact with
  `artifact_kind=product-oracle`, `wave=4`, finite `arcface.arc_score`, and
  finite `lipsync.offset_frames`.
- `scripts/ci_smoke.py` is OK with only the known R2 invisible-green warning.

Closed first-cycle packet IDs:
- `wave4-bug-error-coordinator-route`
- `wave4-bug-error-director-identity-embselect`
- `wave4-bug-error-operator-identity-lanev`
- `wave4-bug-error-director2-mailbox-kind-registry`
- `wave4-bug-error-operator2-mailbox-kind-lanev`
- `wave4-bug-error-coordinator-join`

New task-board cycle:
- `2026-06-17-wave4-product-oracle-a`

Current capacity packets:
- `wave4-product-oracle-coordinator-route`
- `wave4-product-oracle-director-artifact`
- `wave4-product-oracle-operator-lanev`
- `wave4-product-oracle-director2-standby`
- `wave4-product-oracle-operator2-standby`

Binding route:
- `director`: own the Wave 4 product-oracle artifact next. Produce committed
  `logs/product-oracle-wave4.json` only if it can be measured from
  already-available local source media/reference inputs with committed tooling.
  Expected contract: `artifact_kind="product-oracle"`, `wave=4`, finite
  `arcface.arc_score`, and finite `lipsync.offset_frames`. If fresh generation,
  pod runtime, paid API spend, dependency edits, production generation, or
  missing source inputs are required, do not spend; report the exact blocker and
  required user authorization instead.
- `operator`: stand by for a fresh `director -> operator` verify-request naming
  the product-oracle artifact commit. Verify the artifact is committed at HEAD,
  finite, cites its measurement command/input hashes when available, and
  satisfies the product-oracle portion of `scripts/wave_gate_check.py 4`.
- `director2`: standby. Mailbox-kind cleanup is operator2 GO. No Pair-B
  implementation is opened unless a later coordinator/user route assigns it.
- `operator2`: standby. Do not duplicate operator product-oracle Lane V unless
  a later coordinator/user route assigns it.

Join condition:
- `director` either lands a committed Wave 4 product-oracle artifact and sends
  a fresh verify-request to `operator`, or reports the exact no-spend blocker.
- `operator` issues GO/NITS/FAIL on any landed product-oracle artifact.
- Coordinator reruns mailbox monitor, Wave 4 capacity board, this route
  validation, `scripts/wave_gate_check.py 4`, and `scripts/ci_smoke.py`, then
  writes a closeout or reroute.

Boundaries:
- No push, lock claim, lock release, pod spend, paid API spend, dependency edit,
  production generation, or production pipeline edit is opened by this
  coordinator route.
- Local `main` is ahead of `origin/main`; publication remains user-gated.

Exact next trigger:
- `continue as director`

Cursor at send: unknown
