# Coordinator → All: anti-ceremony fanout: four-seat execution map

**When:** 2026-06-15T04:29:00Z · **From:** coordinator (online)

Coordinator anti-ceremony fanout started.

Execution map:
- director: Pair-A production implementation; finish idgate-failopen, then coherence-caller-valid-ignored. No ADR-027/028 tooling unless reassigned.
- operator: Pair-A cold Lane V verification; verify Pair-A fixes and may spawn read-only verifier subagents where protocol requires.
- director2: Pair-B ADR-027/028 gate/tooling implementation from docs/superpowers/briefs/2026-06-15-adr027-gate-exec-ceremony.md, including wave_gate_check.py, pin_reconciler.py, CI --runxfail, and check_no_ceremony.py hard wiring.
- operator2: Pair-B verification for pin_reconciler, wave_gate_check, CI behavior, and check_no_ceremony.py R3/R4 only when executable evidence supports green.

Role limits:
- Coordinator broadcasts, routes, reconciles, and tracks evidence; it does not implement production fixes.
- Directors implement.
- Operators verify.

Anti-ceremony cork:
- Status strings, mailbox claims, and docs-only green labels are not proof.
- Cite executed commands, committed tests, and artifacts only.
- Wave status remains red unless executable evidence actually passes.

Thread IDs are intentionally not recorded in this committed event; they remain a coordinator-local binding/report detail.

Cursor at send: unknown
