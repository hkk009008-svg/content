"""Cross-provider seat topology (Slice 1).

A signed-JSON event bus + effective-state reducer + gate-computed risk tier +
a mechanical exact-SHA merge-gate. See
docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md.

Slice 1 is single-writer and one-pair. Multi-writer/ref-topology hardening is
Slice 2; the strategic loop + T2/T3 co-sign is Slice 3.
"""

SCHEMA_VERSION = "threeway/1"

# Full event vocabulary (§6.2). Private to this package — NOT the markdown bus's
# coordination/mailbox/kinds.txt.
THREEWAY_KINDS = frozenset({
    "brief", "brief_superseded", "candidate", "candidate_aborted", "assignment",
    "attestation", "attestation_revoked", "co_sign", "re_verify",
    "cycle_go", "release_requested", "release_order", "human_approval", "ci_result",
    "event_sent", "event_acknowledged", "event_rejected", "event_timed_out",
    "event_retried", "dead_letter",
    # the gate emits merge_completed for §6.4/§9 idempotency (listed in the §6.2 kind enum).
    "merge_completed",
})

# Kinds whose signature the gate treats as load-bearing (must verify).
LOAD_BEARING_KINDS = frozenset({
    "brief", "brief_superseded", "candidate", "candidate_aborted", "assignment",
    "attestation", "attestation_revoked", "co_sign", "re_verify",
    "cycle_go", "release_requested", "release_order", "human_approval", "ci_result",
    "merge_completed",
})
