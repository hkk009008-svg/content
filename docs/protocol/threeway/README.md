# Three-Way Protocol — Adoption & Unified Doctrine

This directory holds the operating manuals for running **Claude, Codex, and Antigravity** as one
unified system on top of the cross-provider three-way protocol.

| Read this | When |
|---|---|
| [`ONBOARDING.md`](ONBOARDING.md) | **Start here.** A copy-paste prompt to bring any Codex / Claude / Antigravity session into the system, the reading order, the non-negotiables, per-provider quick-start, and a self-conformance check. |
| [`UNIFIED-OPERATING-DOCTRINE.md`](UNIFIED-OPERATING-DOCTRINE.md) | The shared rules all three providers follow — Layer 1 (the cross-provider protocol/topology) and Layer 2 (the portable operating doctrine), plus the per-provider capability-mapping table. |
| [`CODEX-ADOPTION.md`](CODEX-ADOPTION.md) | Operating Codex against the protocol. Codex already mirrors Layer 2; this covers its Layer-1 seats (`director`, `operator2`, `coordinator2`) and the migration. |
| [`ANTIGRAVITY-ADOPTION.md`](ANTIGRAVITY-ADOPTION.md) | Operating Antigravity ("agy"). It holds **no Layer-1 seat** by design; it participates as a human-relayed strategic reasoner / read-only observer and adopts Layer 2 for any work it does. |
| [`ARCHITECTURE-DIAGRAM.md`](ARCHITECTURE-DIAGRAM.md) | The canonical topology diagram (mermaid) — legend + the six load-bearing reads + what it corrects vs the draft diagrams. |

**Truth sources (these win over the manuals on any factual disagreement):**
- Protocol spec: [`docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md`](../../superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md)
- Slice-2.5 migration plan: [`docs/superpowers/plans/2026-06-20-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md`](../../superpowers/plans/2026-06-20-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md)
- The package: [`threeway/`](../../../threeway/)
- Verified-truth + decisions: [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) §13A · [`DECISIONS.md`](../../../DECISIONS.md) (ADR-034..064)
- Principle root: [`AGENTS.md`](../../../AGENTS.md) · Claude mechanics: [`CLAUDE.md`](../../../CLAUDE.md) · Codex mechanics: [`docs/protocol/codex/continuation.md`](../codex/continuation.md)

**Status (verify before relying — `git for-each-ref refs/threeway/` is the live oracle):** the
`threeway/` package — Slice 1+2 (signed bus, effective-state reducer, gate, RefEventStore), Slice 2.5
(legacy-bus migration substrate), and Slice 3 (tiered T2/T3 co-sign machinery) — is BUILT, hardened,
and test-green, and **the bus has been CUT OVER (2026-06-22) and is LIVE**: `refs/threeway/events`
holds the **768** migrated legacy-mailbox events as `event_sent` carriers + **6** backfilled seat
cursors, pushed to `origin` (`git ls-remote origin 'refs/threeway/*'`). The retained
`coordination/mailbox/sent/` is now read-only rollback.

What IS and is NOT live (be precise — this is bus + local CLI mechanism, not a deployed strategic loop):
- **LIVE — bus infrastructure.** 768-event signed bus + 6 cursors on `origin`; the `.pub` trust root
  committed (`d2a50f98`); the `THREEWAY_CI_KEY` secret set and the `THREEWAY_BUS_LIVE=true` repo
  variable flipped, so the manual `workflow_dispatch` ci-result signer job is armed; the merge-gate
  runner (`scripts/run_merge_gate.py`) runs clean against the live bus (0 candidates → no-op).
- **LIVE — local principal-safe emitters for signed facts.** T1/T2/T3 and revocation/supersession facts
  are emitted through `scripts/overseer_emit.py`, `scripts/seat_emit.py`, and `scripts/chief_emit.py`;
  `docs/protocol/threeway/MECHANISM-LEDGER.md` covers every `LOAD_BEARING_KINDS` member. Verified via
  `env -u GIT_INDEX_FILE .venv/bin/python scripts/threeway_mechanism_ledger.py --check` -> exit 0.
- **NOT live — deployed protected-main strategic loop.** The free-form mailbox remains the human
  coordination channel. The local signed-bus path is proved on `refs/threeway/test-main`, but deployed
  protected `refs/heads/main` promotion still requires verifiable branch-protection/ref-ACL controls and
  a protected merge-gate runner. Verified via
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_run_merge_gate_protected_main.py -q` -> 2 passed in 0.03s.

Activation tooling: `scripts/sign_ci_result.py`, `scripts/run_merge_gate.py`, `scripts/agy_observer.py`,
`scripts/execute_threeway_cutover.sh`, `scripts/seat_emit.py`, `scripts/chief_emit.py`,
`scripts/overseer_emit.py`, `scripts/threeway_mechanism_ledger.py`, and the `.github/workflows/ci.yml`
`threeway-ci-result` job (fetchable `integration_ref` + exact tested `integration_sha`). The single
authority-flip cutover was executed under explicit user confirmation (DECISIONS.md ADR-045). Adoption of
the live protected-main loop = deploying the protected merge-gate controls, not flipping a switch. See
`UNIFIED-OPERATING-DOCTRINE.md` §I.5.
