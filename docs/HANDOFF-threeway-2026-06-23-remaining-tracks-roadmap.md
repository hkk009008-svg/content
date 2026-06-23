# HANDOFF / ROADMAP — threeway remaining tracks (sub-project 2 + hardening), decomposed

**Date:** 2026-06-23
**HEAD:** `main` @ `acbe6bbd` (== origin/main). Verify with `git log -1`.

> Context: the **automation track is COMPLETE + Lane-V verified** this session — `overseer_plan`
> (ADR-057) + its T3 extension (ADR-058). What remains are two LARGE tracks with real design forks +
> dependencies (mapped below from a grounding pass). This roadmap orders them for rigorous execution; it
> deliberately does NOT pre-implement major operational/infra change without design sign-off.

## What is DONE + verified (this session)

| Deliverable | Verdict | Record |
|---|---|---|
| scope-b sub-project 1 (mechanical-seat runtime) | Lane-V GO | `logs/verify-adr056-scope-b-sp1-lane-v.json` |
| `overseer_plan` auto-decompose (T0/T1) | Lane-V GO + §6c re-verify GO | `logs/verify-adr057-overseer-plan-lane-v.json` |
| `overseer_plan` T3 extension | Lane-V GO | `logs/verify-adr058-overseer-plan-t3-lane-v.json` |

The overseer can now (human-driven, dry-run+confirm, idempotent) decompose a chief decision into all the
overseer-authority facts across all tiers; the merge-gate daemon promotes the protected TEST ref; the CI
signer is operable. **Bus transport LIVE; the strategic LOOP (real seats producing/consuming bus events,
liveness/recovery, production real-`main` promotion) is the remaining work.**

## Track B — Sub-project 2: real seat↔bus wiring (LARGE; design forks → surface before building)

**Goal:** interactive seats (director/operator/coordinator ×2) emit + consume bus events directly, instead
of the file mailbox; `scripts/bootstrap_emit.py` is then removed.

**Why it needs design (not autonomous implementation):** it changes the LIVE coordination mechanism the
seats use right now (`coordination/bin/{send-event,consume-events,claim-lock,release-lock}`). Design forks:
1. **Consumption model** — how does a Claude/Codex *session* consume signed bus events? A new
   `coordination/bin/consume-bus` mirroring `consume-events` (cursor-per-seat over `refs/threeway/events`)?
   Bus events are signed envelopes, not mailbox `.md` files — the seat tooling + presence/heartbeat model
   must adapt.
2. **Emission model** — seats emit `candidate`/`attestation`/`release_requested` via signed CLIs (the
   `bootstrap_emit` shapes, but as the real seat with its own key) — do we keep one CLI per fact, or a
   seat-aware `seat_emit`? How do seats hold their keys (already per-seat in `coordination/threeway/keys`)?
3. **Transition** — dual-run mailbox + bus during cutover, or hard switch? The mailbox is the seats'
   current source of truth; a hard switch is risky. Recommend dual-run with the bus authoritative for
   threeway facts and the mailbox retained for free-form coordination, then retire `bootstrap_emit`.
4. **Scope vs the gate** — still TEST-ref only (real-`main` is the hardening track). Sub-project 2 makes the
   T1 walking-skeleton run with REAL seats instead of `bootstrap_emit`, end-to-end on the test ref.

**Recommended decomposition:** (2a) `consume-bus` reader + per-seat cursor; (2b) seat emission path
(real-seat candidate/attestation/release_requested); (2c) E2E with real seats (no `bootstrap_emit`);
(2d) retire `bootstrap_emit.py`. Each its own spec→plan→TDD→Lane-V.

## Track C — Hardening track (gates production real-`main`; 7 items, mostly infra)

Ordered by (value to production sign-off) × (in-repo tractability):

| # | Item | Nature | Notes / dependency |
|---|---|---|---|
| C1 | **Liveness/recovery — rework ESCALATE breaker** | in-repo code | `threeway/rework.py` `should_escalate` is UNWIRED **and** its input `candidate_aborted` is **never emitted** (no emit path, not in `kinds.txt`/reducer) and there is **no driver** (`loop.py` is the event builder, not a runtime). Real fix = (a) a `candidate_aborted` emit path (who aborts a cycle?), (b) a consult point (overseer_plan refuses to emit a new `cycle_go` when `should_escalate` → ESCALATE/surface), (c) timeouts/stale-eviction. **Has a design question (abort authority + shape) — not a one-line wiring.** |
| C2 | **CI attestor** (independent re-derive of outcome + runner-image/test-set digest + nonce) | CI infra | GitHub Actions design; the current `needs:`-trust model is the gap. |
| C3 | **Ref-ACL / append-only enforcement** on the bus host (deny force-delete/update; retention; replication) | infra/config | GitHub branch-protection on `refs/threeway/*`; deployment, not repo code. |
| C4 | **External trust anchor** (gate build / policy / key registry pinned outside the repo the gate writes) | infra/deployment | architecture decision. |
| C5 | **Key versioning / rotation / revocation / break-glass** | key-lifecycle | partly code (registry versioning) + partly ops. |
| C6 | **Per-principal human-approver keys** (each chief holds their own key) | key mgmt | keys are already per-seat; this is distribution + enrollment. |
| C7 | **Richer attestation payloads** (policy version, toolchain digest, evidence hash, expiry) | code, cross-cutting | touches the attestation shape (`loop.py`/`bootstrap_emit`) + the predicate (enforce expiry/digest) — modifies the verified gate logic; design + careful Lane-V. |

**Recommendation:** C1 (liveness/rework) is the highest-value *code* item but needs the abort-path design
decided first; C3/C4 (ref-ACL + trust anchor) are the highest-value *security* items but are infra/ops
the user must drive (GitHub settings, where the trust anchor lives). C7 is in-repo but modifies the
audited gate — do it with a full adversarial Lane-V.

## Suggested next-session order

1. **C1 design** — decide the `candidate_aborted` abort authority + shape, then wire the breaker into
   `overseer_plan` (refuse new `cycle_go` on escalate) + a `candidate_aborted` emit path. In-repo, builds
   on the verified `overseer_plan`. **Needs one design decision from the user (who may abort a cycle).**
2. **Track B (sub-project 2)** — start with 2a (`consume-bus`) after the consumption-model fork is chosen.
3. **C3/C4** (ref-ACL + trust anchor) — user-driven infra; I can write the runbook + the branch-protection
   config, but the user applies the GitHub/deployment settings.

## Open background (unchanged)

The 6 `coordination/mailbox/seen/*.txt` (ISO→scalar) + `coordination/mailbox/.migration/` cutover
rollback manifest remain uncommitted — decide whether to commit for durable migration rollback. A chip is
queued for the unrelated `ci_smoke` false-positive SHA (`a38a3d69`) in the ADR-054 block.
