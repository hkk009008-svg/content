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
- Verified-truth + decisions: [`ARCHITECTURE.md`](../../../ARCHITECTURE.md) §13A · [`DECISIONS.md`](../../../DECISIONS.md) (ADR-034..049)
- Principle root: [`AGENTS.md`](../../../AGENTS.md) · Claude mechanics: [`CLAUDE.md`](../../../CLAUDE.md) · Codex mechanics: [`docs/protocol/codex/continuation.md`](../codex/continuation.md)

**Status (verify before relying — `git for-each-ref refs/threeway/` is the live oracle):** the
`threeway/` package — Slice 1+2 (signed bus, effective-state reducer, gate, RefEventStore), Slice 2.5
(legacy-bus migration substrate), and Slice 3 (tiered T2/T3 co-sign machinery) — is BUILT, hardened,
and test-green, but the bus is **NOT yet live**: `refs/threeway/events` does not exist and the live
coordination substrate is still the legacy mailbox bus.

What has changed toward go-live (NOT yet a flip):
- **Keys generated** into `coordination/threeway/keys/` (`<seat>.pub` for all 9 signing seats) — the
  prior hard blocker. NOTE: these are still **uncommitted** here; committing the `.pub` trust root is
  itself part of the user-gated go-live (a T3-classified commit), and private `*.ed25519` keys are
  gitignored and live only in the keystore dir.
- **Activation tooling** exists: `scripts/sign_ci_result.py` (CI signs `ci_result`),
  `scripts/run_merge_gate.py` (the merge-gate daemon over `threeway.gate.run_gate`),
  `scripts/agy_observer.py` (Antigravity read-only bus summary), `scripts/execute_threeway_cutover.sh`
  (key provisioning + cutover driver), and a CI step in `.github/workflows/ci.yml`.

The single authority-flip cutover has **NOT been executed** (irreversible; gated on explicit user
confirmation — DECISIONS.md ADR-045). "Adoption" = executing the sequenced, user-gated migration, not
flipping this status line. See `UNIFIED-OPERATING-DOCTRINE.md` §I.5.
