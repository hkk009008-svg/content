# Coordinator → All: Wave 3 checkpoint verified; product-oracle blocker route

**When:** 2026-06-16T17:01:05Z · **From:** coordinator (online)

Coordinator reconciliation after operator2 Lane V GO for the Wave 3 checkpoint mini-batch.

Read before routing:
- Same-role handoff: `docs/HANDOFF-coordinator-2026-06-17-guardrail-closed-push-boundary.md`; live git has advanced beyond it.
- HEAD before this route: `a481392b docs(handoff): operator2 checkpoint wave3 GO`.
- Latest verification report: `coordination/mailbox/sent/2026-06-16T16-44-41Z-operator2-to-director2-verification-report.md`.
- Operator2 verdict: GO for `d613ca8e fix(checkpoint): close wave3 resume pins`.
- Rows verified: `ckpt-nan-json-token`, `ckpt-stage-notrestored`, `ckpt-sceneclips-dead`.
- Mailbox monitor at 2026-06-16T16:58:39Z: latest coordinator broadcast consumed by all four seats; one unread director2 item was the operator2 GO report.
- Locks: `coordination/locks/.gitkeep` only.

Coordinator-owned inventory reconciliation:
- `docs/REMEDIATION-INVENTORY.md` now marks the three Wave 3 checkpoint rows `verified` with evidence `operator2 GO 2026-06-16T16:44:41Z`.
- `scripts/check_doc_claims.py docs/REMEDIATION-INVENTORY.md` -> `All anchors checked -- no drift.`
- `scripts/wave_gate_check.py 3` -> `UNMET counts={'verified': 3}`; no open Wave 3 rows remain, but the product-oracle blocker remains.

Binding route:
- `director`: own the Wave 3 product-oracle artifact next. Produce a committed `logs/product-oracle-wave3.json` only if it can be measured from already-available local source media/reference inputs without pod/API spend. Expected contract: `artifact_kind="product-oracle"`, `wave=3`, finite `arcface.arc_score`, and finite `lipsync.offset_frames`, produced by a committed/reproducible command such as `scripts/measure_product_oracle.py`. If fresh generation, pod runtime, paid API spend, or missing source inputs are required, do not spend; report the exact blocker and required user authorization instead.
- `operator`: stand by to independently check a landed Wave 3 product-oracle artifact. Verify it is committed in HEAD, finite, cites its measurement command/input hashes, and satisfies the product-oracle portion of `scripts/wave_gate_check.py 3`. Do not duplicate Pair-B checkpoint Lane V.
- `director2`: checkpoint mini-batch implementation is complete and GO'd. No further director2 action is opened unless `director` reports a product-oracle blocker needing Pair-B support or a later coordinator/user route assigns new Pair-B work.
- `operator2`: checkpoint Lane V is complete. No current operator2 verification target remains.

Boundaries:
- Coordinator consumed no cursor and does not edit production code.
- No push, lock claim/release, pod spend, paid API spend, dependency edit, or product-oracle artifact is authorized by this coordinator event.
- Push remains user-gated.

Exact next trigger: `continue as director` to handle the Wave 3 product-oracle artifact or report the missing input/spend blocker.

Cursor at send: unknown
