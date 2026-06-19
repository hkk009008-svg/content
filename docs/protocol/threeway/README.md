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
- The package: [`threeway/`](../../../threeway/)
- Principle root: [`AGENTS.md`](../../../AGENTS.md) · Claude mechanics: [`CLAUDE.md`](../../../CLAUDE.md) · Codex mechanics: [`docs/protocol/codex/continuation.md`](../codex/continuation.md)

**Status (verify before relying):** the `threeway/` package (Slice 1+2) is built but **wired into
nothing**; the live coordination substrate is still the legacy mailbox bus. Slice 2.5 (migration) is a
deferred stub and Slice 3 (strategic loop) is unbuilt. "Adoption" = executing the sequenced migration,
not flipping a switch. See `UNIFIED-OPERATING-DOCTRINE.md` §I.5.
