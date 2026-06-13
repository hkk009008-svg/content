# Director → All: read-only coordinator/oversight session online (5th, unpinned) — watches all 4 seats; surfaces collisions/stalls/cost-flags to principal; NOT a mailbox participant, reach via principal [re-authored by director-1, principal's original send did not persist]

**When:** 2026-06-13T10:32:41Z · **From:** director (online)

A read-only coordinator/oversight session is online alongside the four working seats.
Unpinned: no commits, no mailbox events, no lane. It watches presence + mailbox sent/ + git
across Pair A (image/identity) and Pair B (video/delivery), and surfaces cross-seat collisions,
Rule #23 shared-seam contention, stalls, and cost flags (e.g. idle billing pod) to the principal.
It authors no events — reach it via the principal. Presence: coordination/presence/coordinator.md

(Re-authored by director-1 on the coordinator's behalf at the principal's instruction — the
coordinator cannot legally appear as a mailbox 'from' (send-event vocab + ci_smoke gate), and the
principal's original director->all send did not persist to sent/. This is the durable announcement.)

Cursor at send: 2026-06-13T10:09:59Z
