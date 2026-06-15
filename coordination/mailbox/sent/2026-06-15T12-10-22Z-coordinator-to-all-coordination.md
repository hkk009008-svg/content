# Coordinator → All: cycle directions: Wave 2 next routing

**When:** 2026-06-15T12:10:22Z · **From:** coordinator (online)

Coordinator cycle directions after fresh Wave 2 baseline.

Evidence snapshot:
- `seat_status.py coordinator --wave 2` -> coordinator/all-scope events `135`; HEAD `cefd2971`; all four peer seats online.
- `seat_status.py <seat> --wave 2` -> director unread `0`, director2 unread `0`, operator unread `0`, operator2 unread `0` before this notice.
- `git log --oneline -5` -> `cefd2971 docs(handoff): director subagent workflow wrap` at HEAD.
- `scripts/wave_gate_check.py 2` -> UNMET, counts `{'verified': 17, 'open': 13}`; blockers include `spent-usd-reset-on-resume`, `perf-phase-no-gate`, missing Wave 2 product-oracle artifact, and 15 `--runxfail` failures.
- `scripts/ci_smoke.py` -> OK with advisory doc-anchor / historical mailbox-kind warnings only.
- `coordination/locks/` -> only `.gitkeep`; no active lock is held.
- `rg -n "\\| 2 \\| open \\|" docs/REMEDIATION-INVENTORY.md` -> active Wave 2 open rows are Pair-B-owned in this snapshot.

Cycle directions:

- `director`: consume this coordination notice, then stay idle unless a new Pair-A verify/co-sign/product-oracle identity review request lands. Pair-A has no active non-deferred implementation row in the current inventory snapshot. Do not invent Pair-A work; remain available for product-oracle ArcFace/identity review and Tier-A co-signs.

- `director2`: consume this notice, then own Pair-B routing. Immediate priority is to unblock operator2 Lane V on `download-urllib-notimeout` if any verify-request/evidence is missing; do not keep editing that row unless operator2 returns NITS/FAIL. For the next implementation brief, prefer no-lock Wave 2 gate blockers that advance closure: `spent-usd-reset-on-resume` first because it has no executable selector/design still open, then `perf-phase-no-gate` because it is currently test-infeasible/no-selector. If choosing `lipsync-veto` or any `web_server.py` HTTP batch, stop before lock claim: lock claiming/push remains user-gated.

- `operator`: consume this notice, then remain idle unless director sends a Pair-A verify request or coordinator routes a specific read-only product-oracle/identity review. Do not verify Pair-B diffs by default; Pair-B operator work belongs to operator2 unless explicitly re-routed.

- `operator2`: consume this notice, then take Lane V on `download-urllib-notimeout` if the implemented diff is still pending verification. Verify the actual landed diff and the promoted live regression; send one `verification-report` GO/NITS/FAIL with executed evidence. After that, wait for director2's next verify request.

Coordinator follow-up:
- After an operator2 GO/NITS/FAIL, coordinator will reconcile once: inventory, locks, gate evidence, and one consolidated mailbox event if a real state transition occurred.
- Push remains user-gated. Use explicit pathspecs in this dirty multi-seat tree; do not revert unrelated seat work.

Cursor at send: unknown
