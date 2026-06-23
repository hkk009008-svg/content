# Spec — `overseer-plan` T3 extension (emit approver_roster + re_verify_challenge; tier-aware owed surface)

**Date:** 2026-06-23
**Status:** design (code-grounded); the documented fast-follow of ADR-057. Streamlined artifact (additive
extension of an already-verified component); authoritative gate is the independent Lane-V.
**Scope:** extend `scripts/overseer_plan.py` (ADR-057, Lane-V verified `bac52067`) from T0/T1 to **all
tiers**. Adds the two higher-tier OVERSEER facts to the emittable set and makes the owed surface
tier-aware. Builds on, and does not modify, `overseer_emit` (which already signs all 6 facts).

> Truth lives in the code. Mirrors `threeway/tier.py` (`co_sign_satisfied` and its helpers),
> `threeway/predicate.py:131` (the `co_sign not satisfied` PENDING), `threeway/reducer.py`
> (`approver_roster`/`re_verify_challenge`/`co_sign`/`re_verify`/`human_approvals` accessors), and
> `scripts/overseer_emit.py` (the reuse target) at HEAD `bac52067`. Verify before implementing.

## 1. Context

ADR-057's `overseer_plan` handles T0/T1: it emits `brief`/`assignment`/`cycle_go` and surfaces
`release_order` + the non-overseer facts as owed; it rejects T2/T3. The predicate collapses every
higher-tier requirement into one `PENDING "co_sign not satisfied for {eff_tier}"` (`predicate.py:131`),
which `tier.co_sign_satisfied` decomposes. This extension teaches `overseer_plan` that decomposition:
which parts are **overseer-emittable** vs **owed by a non-overseer seat**.

## 2. The tier decomposition (from `tier.py`, verified)

`co_sign_satisfied(tier, …)`:
- **T0/T1:** `True` (nothing extra). *(unchanged)*
- **T2:** requires cross-provider independence + `_t2_mirror_cosign` — a `co_sign` GO @ integration_sha
  from the **mirror pair's primary_verifier** (`tier.py:90-98`). **Non-overseer (owed).** Its only overseer
  prerequisite is the *mirror pair's own* `assignment`, which belongs to that pair's decision — NOT this
  candidate's; `overseer_plan` for this decision does not emit it (surfaced, not emitted).
- **T3:** T2 PLUS `_t3_cross_provider_re_verify` (`tier.py:101-138`) — a `re_verify` GO @ integration_sha
  from the **candidate pair's primary_verifier** echoing the overseer's challenge nonce — PLUS
  `_two_distinct_human_approvals` (`tier.py:141-170`) — two distinct rostered `human_approval`s.

**Overseer-emittable facts this adds (T3 only):**
- `approver_roster` — publishes the allowed-approver seats (`tier.py:151` reads it; needs `approvers[]`).
- `re_verify_challenge` — issues the fresh-nonce challenge bound to integration_sha (`tier.py:128-131`
  reads it; `overseer_emit` mints the nonce via `secrets.token_hex`).

**Owed (surfaced, never emitted by overseer_plan):** `co_sign` (T2/T3, mirror pair primary_verifier);
`re_verify` GO (T3, candidate pair primary_verifier); `human_approval` ×2 (T3, rostered seats).

## 3. Design decisions (→ ADR-058)

- **DD-1 — generalize the DD-4 safety boundary by direction, not by enumerating one fact.**
  `overseer_plan` auto-emits overseer facts that only **add a requirement or publish a decision**
  (`brief`, `assignment`, `cycle_go`, `approver_roster`, `re_verify_challenge`); it **never** emits the
  one fact that **removes the final gate** (`release_order` — authorizes the merge). `approver_roster`
  and `re_verify_challenge` can only make the gate STRICTER, so auto-emitting them is fail-safe.
  `release_order` stays manual (carried from ADR-057 DD-4).
- **DD-2 — `re_verify_challenge` is progressive (needs `integration_sha`).** Emittable only when a
  `candidate` exists on the bus (its `integration_sha` is the challenge `subject_sha`) AND the challenge is
  absent. Like the `release_order` gating, but the challenge IS auto-emitted (it only adds a requirement).
- **DD-3 — single-round challenge only.** `overseer_emit` keys `re_verify_challenge` on the fixed id
  `re_verify_challenge-overseer-{cid}`, so exactly one challenge per candidate is emittable (ADR-056
  deferred-note). `overseer_plan`'s idempotency (re-read → skip if present) means it emits the challenge
  once; a multi-round re-challenge (fresh nonce, new id) remains deferred. Sufficient for a single T3 pass.
- **DD-4 — `approvers[]` is a required decision field for T3.** The roster must name ≥2 distinct seats
  (`tier.py:158` fails closed on <2). Validated at load for T3; ignored for T0/T1/T2.
- **DD-5 — keep the single signing path (ADR-057 DD-5).** The two new facts are emitted via
  `overseer_emit.main(["approver_roster", …])` / `(["re_verify_challenge", …])`; no re-implemented shapes.

## 4. Changes to `scripts/overseer_plan.py`

- **Tier acceptance:** `load_decision` accepts `T0..T3` (drop the T2/T3 rejection). For `T3`, require
  `approvers` to be a list of ≥2 distinct strings; else `DecisionError`.
- **`_EMITTABLE`** becomes the full ordered tuple
  `("brief", "assignment", "cycle_go", "approver_roster", "re_verify_challenge")` (still load-bearing;
  `release_order` still excluded → Q4 guard holds).
- **`plan(decision, state)`** computes, per emittable fact, a `(present, eligible)` pair and returns the
  absent+eligible ones in `_EMITTABLE` order:
  - `brief`/`assignment`/`cycle_go`: eligible always.
  - `approver_roster`: eligible iff `tier == "T3"`; present = `state.approver_roster(cid)`.
  - `re_verify_challenge`: eligible iff `tier == "T3"` AND `state.candidate(cid)` exists (integration_sha
    known); present = `state.re_verify_challenge(cid)`.
  - **owed** gains, tier-aware: T2/T3 → `("co_sign", "<mirror pair primary_verifier>")` (resolve the seat
    via `tier._mirror_pair_verifier_seat` when the mirror assignment is on the bus, else a generic label);
    T3 → `("re_verify", "<candidate pair primary_verifier>")` and
    `("human_approval", "<rostered seat>")` for each of the 2 still missing (count via
    `state.human_approvals(cid)` filtered to rostered seats + integration_sha + decision==approve).
- **`_emit_argv`** gains arms (release_order still absent → reaches the `ValueError` guard):
  - `approver_roster`: `["approver_roster", "--candidate-id", cid, "--approvers", *approvers, *tail]`.
  - `re_verify_challenge`: `["re_verify_challenge", "--candidate-id", cid, "--integration-sha", integ, *tail]`
    (no `--nonce` → `overseer_emit` mints it). `integ` is read from `state.candidate(cid).payload["integration_sha"]`
    and threaded into `_emit_argv` (an extra param; `None` for facts that don't need it).

## 5. Testing (TDD; non-vacuous)

- `load_decision`: T2 accepted (no approvers needed); T3 without `approvers` → `DecisionError`; T3 with
  `approvers=["a"]` (only 1) → `DecisionError`; T3 with 2 distinct → ok.
- `plan` (T3, empty bus): emittable = `["brief","assignment","cycle_go","approver_roster"]` (NOT
  `re_verify_challenge` — no candidate yet); owed includes `co_sign`, `re_verify`, 2×`human_approval`.
- `plan` (T3, candidate present): `re_verify_challenge` becomes emittable.
- `--confirm` (T3, candidate seeded): emits `approver_roster` (round-trips; `state.approver_roster(cid)`
  authority-correct = overseer; approvers match) and `re_verify_challenge` (subject_sha == candidate
  integration_sha; nonce minted, ≥16 hex); `release_order` STILL `None` (Q4 guard holds across tiers —
  mutation-tested).
- Idempotency: second `--confirm` (T3) emits zero (spy on `overseer_emit.main`).
- T2 `--confirm`: emits only `brief`/`assignment`/`cycle_go` (NO approver_roster/re_verify_challenge —
  those are T3-only); surfaces `co_sign` owed.
- All ADR-057 T0/T1 pins stay green (regression).

## 6. Scope boundaries

**In:** §4 changes + §5 tests + ADR-058. **Out:** emitting any non-overseer fact (co_sign/re_verify/
human_approval/candidate/attestation/ci_result — surfaced only); `release_order` automation; multi-round
re_verify_challenge; the mirror pair's own brief/assignment/cycle_go (a different decision's lifecycle);
real `refs/heads/main`; any change to `overseer_emit`/`tier`/`predicate`/`reducer`.

## 7. Acceptance criteria

- A T2/T3 decision is accepted; T3 requires `approvers` (≥2 distinct) or `DecisionError`.
- T3 `--confirm` emits `approver_roster` + (once a candidate exists) `re_verify_challenge`, both
  authority-correct (overseer), and NEVER `release_order` (mutation-tested across tiers).
- The owed surface is tier-aware (T2 adds co_sign; T3 adds re_verify + 2 human_approval).
- Idempotent; T0/T1 behaviour unchanged (all ADR-057 pins green); `ci_smoke` + `check_no_ceremony` clean;
  full threeway suite green.

## 8. Post-implementation

impl≠verifier: implementer commits are `fixed`; an independent Lane-V (mutation-test the Q4 guard across
tiers, the T3 emittability gating, the approvers validation, idempotency) promotes to `verified`.
