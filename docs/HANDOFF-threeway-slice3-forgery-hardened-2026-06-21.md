# HANDOFF — Threeway Slice 3 forgery class CLOSED (post-merge hardening); availability class scoped

**Date:** 2026-06-21
**Pushed:** `origin/main` @ `93cfe3e7` (12 commits `4a90aca9..93cfe3e7`, fast-forward off the Slice-3 merge `6463c772`)
**Verification at handoff:** `tests/unit/test_threeway_*.py` → **248 passed**; `scripts/ci_smoke.py` → OK; `scripts/check_no_ceremony.py` → clean; tree clean.

> Trust git, not this prose. On resume: `git fetch && git log -1 && git rev-list --count origin/main..HEAD`. The verification numbers above were true at `93cfe3e7`.

---

## 1. What this session did

Started from "continue task" with Slice 3 (`co_sign_satisfied` T2/T3) already merged. The remaining plan step was the **whole-implementation review**, run as a multi-agent adversarial workflow. It **overturned the original Slice-3 panel's "no forgeable promotion" verdict** and triggered a hardening campaign across 6 adversarial rounds. Each fix's *own* re-verification found the next layer; severity decayed monotonically (CRITICAL→CRITICAL→MAJOR→MAJOR→availability-class), which was the convergence signal.

**The forged-promotion / merge-DoS-via-collision-or-revoke CLASS is now CLOSED and CONVERGED** — confirmed by a holistic adversarial agent AND an independent completeness-critic, every exploit reproduced end-to-end through the REAL `gate.verify_and_reduce`/`evaluate` (live Ed25519) pre-fix and fail-closed post-fix.

## 2. The three ADRs (forgery class)

| ADR | Root cause | Fix |
|---|---|---|
| **036** | Revocation was an **unauthenticated** authority channel — `reduce()` honored ANY `attestation_revoked`, and `revokes_event_id` is UNSIGNED (envelope.py:67). A forged non-overseer revoke of a rival mirror's overseer-signed assignment collapsed the fail-closed T2/T3 mirror ambiguity → forged MERGEABLE (+ 2-pair merge DoS). | `_revoke_authorized`: honor a revoke only from `overseer` or the target's own seat (self-revocation); collision-aware `id→{seats}` index built from `LOAD_BEARING_KINDS` only. + tier hardening (same-provider reject, eligible-PAIR mirror count, T3 empty-seat). + `brief_superseded` gated by the same rule (the OTHER unsigned reference field — Rule #13 sibling). |
| **037** | Event `id` is signed but enforced-unique **nowhere** → an insider could re-use a victim's id (poison the revoke index, or overwrite a victim's stored blob). | `verify_and_reduce` rejects a duplicate load-bearing id; `refstore.append` + `store.py` refuse a colliding id (by-id, brief- and kind-agnostic) → `EventIdCollision`. `seat_by_id` scoped to load-bearing kinds (non-LB carrier can't contest). |
| **038** | The predictable `merge-<cid>` completion id is insider-poisonable, and ADR-037's guard turned that into an **uncaught crash after the irreversible CAS merge** (`run_gate` caught only `CalledProcessError`). | `run_gate` step-2b reserved-id integrity check → REJECT before merging. |

## 3. NEXT — the availability/DoS slice (primary)

Round 6 opened a **distinct class**: insider **availability/DoS** (block a legit merge — NOT forge one). 3 confirmed MAJOR, one systematic root: the reducer records control-plane singletons via **unauthenticated last-write-wins**, authority checked only at read time, so a higher-seq shadow displaces the authoritative fact.

**Plan (ready to execute):** `docs/superpowers/plans/2026-06-21-threeway-control-plane-availability-hardening.md`
- Design: **authority-aware reducer** (resolve each singleton from its AUTHORIZED seat — overseer for assignment/brief/cycle_go/release_order, ci for ci_result, gate for merge_completed; **candidate** via its per-pair `executing_coordinator`, the one dynamic-authority case); reserve the `merge-*` id namespace; make `run_gate` total + recoverable (main-state idempotency).
- Inventory rows (open, in `docs/REMEDIATION-INVENTORY.md`): `threeway-reducer-shadow-dos`, `threeway-merge-completed-no-seat-check`, `threeway-run-gate-not-total`. (`threeway-reserved-merge-id-dos` residual is also folded into the slice.)
- Execute via `superpowers:subagent-driven-development` (Opus subagents per the standing directive).

## 4. Still deferred (unchanged from before this session)

- **Slice 3 scope (b) — the strategic loop:** dual-chief apps (human-relayed) + LIVE emission of `co_sign`/`re_verify`/`human_approval`; closes `threeway-signer-unsigned-session` (re_verify freshness needs an overseer challenge in the SIGNED payload) + `threeway-human-approval-overseer-asserted` (per-approver auth).
- **The LIVE cutover (operational):** Slice 2.5 shipped the tested machinery (`threeway/cutover.py`); the authority-flip onto `refs/threeway/events` was NOT run; live `coordination/` bus still on ISO cursors.

## 5. Sharp edges / lessons

- **Adversarially RE-VERIFY your own security fix.** Every fix this session introduced or revealed the next gap (the collision-aware index trusted a non-unique id; ADR-037's guard crashed `run_gate`). End-to-end repros through the REAL gate caught what paper-review missed.
- **Recurring class: a gate trusting an UNAUTHENTICATED input** (cousin of money-loss gate-source-mismatch + silent-gate-degradation). The unauthenticated inputs found one root deeper each round: revoke channel → non-unique id → predictable reserved id → supersede channel → last-write-wins reducer.
- **Two unsigned reference fields** (`revokes_event_id`, `supersedes_event_id`, envelope.py:67-69) are now BOTH authority-gated via the same `_revoke_authorized`. If a third unsigned reference is ever added, gate it too.
- Tests run with `env -u GIT_INDEX_FILE` (shared seat index). Commits used explicit pathspec. Carrier ids = source filename (`legacy_projector.py id=p.name`), so the id-uniqueness guards don't block the cutover.

## 6. Where the truth lives

`DECISIONS.md` ADR-036/037/038 (full rationale + evidence); `ARCHITECTURE.md` §13A.6 (revoke-authority + id-uniqueness); `docs/REMEDIATION-INVENTORY.md` (rows: revoke-authority-unsigned, event-id-not-unique, brief-supersede-authority all `fixed`; the 3 availability rows + reserved-merge-id-dos `open`). Memory: `project-cross-provider-topology-design`.
