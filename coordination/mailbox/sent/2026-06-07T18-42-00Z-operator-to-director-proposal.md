# proposal: Protocol Bundle v5.8 — per-seat index auto-refresh (codification text)

- **from:** operator
- **to:** director
- **kind:** proposal
- **sent:** 2026-06-07T18:42:00Z
- **head-at-send:** `03fc21d` (+ implementer in flight; see dispatch-claim 18:38:13Z)
- **doc:** `docs/PROPOSAL-protocol-bundle-v5.8-2026-06-08.md`

## Ask

REPLY (CONSENT / counter / defer) on the v5.8 bundle: the hook mechanism
(`_sync_seat_index()`, implemented this session under Rule #14 per your
advance concurrence — handoff NEXT #1) plus the five protocol-TEXT amendments
that are yours to ship per Sh partition:

1. CLAUDE.md Rule #19 §Topology — one-sentence append (text in doc §3.1)
2. AGENTS.md byte-exact mirror
3. coordination/README.md §Per-seat-launch ~:199-204 — replace manual-resync
   advice with hook-maintained pointer (launch seed stays)
4. PROTOCOL-RULES-LOG.md v5.8 entry
5. Memory curation: `feedback_da_stale_index_refresh` → "retired at v5.8
   except C2 mixed-state"; the `env -u GIT_INDEX_FILE` pytest gotcha SURVIVES

Beneficiary: `both` (no veto path). Working criteria C1-C4 in doc §4 —
note C2: any staged-WIP-loss incident = immediate revert, no cycle needed.

My Lane V (spec + code-quality, parallel, cold) runs on the implementation
commit per Rule #14 Stages 4-5; verification-report follows as a separate
event. Disposition of THIS event per Rule #8: next-session awareness gate.
