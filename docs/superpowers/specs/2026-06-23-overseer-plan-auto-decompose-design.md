# Spec — Threeway scope-b automation track: `overseer-plan` auto-decompose layer (T0/T1)

**Date:** 2026-06-23
**Status:** design approved (brainstorming); awaiting spec review + implementation plan.
**Scope:** the **automation track** fast-follow ABOVE scope-b sub-project 1 (the `overseer_emit` CLI,
landed + Lane-V verified GO `a488276a`, ADR-056). Turns "chief decision → operator hand-issues N
`overseer_emit` calls" into "chief decision (a JSON file) + live bus state → `overseer-plan` emits every
overseer fact emittable now, after dry-run + confirm." First concrete step toward the deferred
fully-automated overseer (Approach B). Builds on, and does not modify, `overseer_emit`.

> Truth lives in the code. This spec mirrors `threeway/predicate.py`, `threeway/reducer.py`,
> `threeway/loop.py:build_candidate_events`, `threeway/policy.py`, and `scripts/overseer_emit.py` as they
> stand at HEAD `a488276a`. Verify the line anchors in §"Verified anchors" against current source before
> implementing; fix drift in the same change.

## 1. Context

Sub-project 1 made the three mechanical seats operable and gave the overseer a human-operated signing CLI
(`scripts/overseer_emit.py`, 6 fact subcommands, overseer-key only). Today an operator relaying a chief
decision must hand-issue each overseer fact in turn (`brief`, then `assignment`, then `cycle_go`, then —
after the seats + CI produce the candidate/attestations/`ci_result` and an `integration_sha` exists —
`release_order`). The automation track (spec for sub-project 1, §7) defers a layer ABOVE `overseer_emit`
that ingests one structured chief decision + the current bus and emits the correct ordered sequence of
overseer facts. This spec defines that layer at minimal-operable scope (T0/T1).

The layer's trigger logic is exactly the **overseer-action trigger table**: each predicate
`PENDING "no <overseer fact>"` maps to "emit that overseer fact." The non-overseer `PENDING`s map to
"surface as owed by <seat>" — `overseer-plan` never emits them.

## 2. Goals / non-goals

**Goals**
- Read one JSON **decision file** + the live bus; compute the overseer facts emittable *now*.
- Emit the routine early-lifecycle overseer facts (`brief`, `assignment`, `cycle_go`) — **dry-run by
  default, `--confirm` to sign** — by REUSING `overseer_emit` (one signing path).
- **Idempotent:** re-reads the bus each run; plans only *absent* facts; safe to re-run as the candidate
  progresses.
- **Surface** every still-owed fact with its owner: `release_order` (overseer-manual), and the
  non-overseer facts (`candidate`, preliminary/release `attestation`, `ci_result`).

**Non-goals (this increment)**
- **No `release_order` automation** — it authorizes the merge; it stays a deliberate manual act via
  `overseer_emit release_order` (Q4). `overseer-plan` only ever *surfaces* it.
- **No T2/T3 overseer facts** (`approver_roster`, `re_verify_challenge`) — documented extension point (§7).
- **No non-overseer emission** (`candidate`/`attestation`/`ci_result`/`co_sign`/`human_approval`) — surfaced only.
- **No change to `overseer_emit`'s behavior** — `overseer-plan` is a pure consumer of it.
- No real `refs/heads/main` promotion; no hardening-track items.

## 3. Design decisions (record as ADR-057)

- **DD-1 — "advance" invocation model (not "full plan").** Each run emits every overseer fact emittable
  *given the current bus*, then re-run as the candidate progresses. Chosen because `release_order` is
  gated on `integration_sha` (`predicate.py:137-143`), which only exists after the non-overseer
  candidate+merge step — so the overseer facts are inherently interleaved with non-overseer ones; a
  single upfront burst is impossible. The advance model mirrors the trigger table 1:1 and is naturally
  idempotent.
- **DD-2 — JSON decision file as the input contract** (`overseer-decision/1`). Persistent, reviewable,
  diff-able, version-controllable; the (DD-1) re-run model reads the same file with zero re-typing. Passed
  via `--decision <path>` (explicit path avoids colon-in-`candidate_id` filename issues); convention:
  `coordination/threeway/decisions/`.
- **DD-3 — T0/T1 scope.** Emit only the four always-required overseer facts' emittable subset
  (`brief`/`assignment`/`cycle_go`; `release_order` surfaced not emitted). The predicate collapses all
  higher-tier requirements into one `PENDING "co_sign not satisfied for {eff_tier}"` (`predicate.py:131`),
  so deciding which T3 overseer fact is owed needs `tier.py`-internal reasoning — deferred as a clean
  extension point.
- **DD-4 — `release_order` is never in the emittable set.** It is always surfaced as
  "overseer-manual: run `overseer_emit release_order --integration-sha <X>`." Faithful to the spec §7
  constraint "preserves the human checkpoint on the release key"; smallest blast radius.
- **DD-5 — single signing path: reuse `overseer_emit.main(argv)`.** `overseer-plan` constructs the argv
  for each owed fact and calls `overseer_emit.main([...])`; it does NOT re-implement signing or fact
  shapes. Guarantees the emitted facts are identical to the Lane-V-verified `overseer_emit` output and
  keeps one source of truth for payload/envelope shapes.

## 4. Components

`scripts/overseer_plan.py` (mirrors `overseer_emit.py` conventions: ADR-055 `sys.path` self-bootstrap;
run under `.venv`; tests prefixed `env -u GIT_INDEX_FILE`).

1. **Decision loader** — read + validate the JSON file; fail loud (rc 2) on a missing/malformed required
   field, with a clear message naming the field.
2. **Bus reader** — `RefEventStore(repo_dir, remote)` → `verify_and_reduce(..., bus_id)` → `EffectiveState`.
   The `--bus-id` (default `prod`) is used for BOTH this read AND every `overseer_emit` emit (§5), so the
   bus read and the bus write are always the same namespace (closes a read-prod/write-prod-only mismatch).
3. **Planner** — query the reduced state's presence accessors directly (NOT a single predicate reason, so
   it can list ALL owed facts):
   - **Emittable (overseer)** = the *absent* subset of `{brief, assignment, cycle_go}` in canonical order.
   - **Owed (surfaced, never emitted)** = `release_order` if absent → `overseer-manual`; plus the absent
     non-overseer facts (`candidate` → coordinator; preliminary/release `attestation` → primary_verifier;
     `ci_result` → CI), shown progressively (e.g. `ci_result` is only checkable once a `candidate`
     exists, since it keys on `integration_sha`).
4. **Dry-run printer** (DEFAULT) — print `WOULD EMIT (overseer): …` + `OWED (not me): …`; **sign nothing**.
5. **Confirm executor** (`--confirm`) — the plan (emittable set) is computed from a bus read at the TOP of
   THIS run (never reused from a prior dry-run); for each planned emittable fact in order, build argv
   (forwarding `--bus-id`) and call `overseer_emit.main(argv)`; stop on the first non-zero return; reprint
   the remaining owed set. Because the emittable set excludes facts already present, a completed bus yields
   an empty set and zero `overseer_emit` calls (idempotent, rc 0). A rc-1 `EventIdCollision` from
   `overseer_emit` would arise only from a concurrent/duplicate run racing the same fact onto the bus — a
   backstop, not the normal path (the CLI is human-operated; concurrent double-confirm is the only trigger).

## 5. CLI & data flow

```
overseer_plan.py --decision <path.json> [--repo-dir .] [--remote origin] [--bus-id prod] [--confirm]
```
One run: load+validate decision → reduce bus → plan (emittable + owed) → **dry-run by default** (print,
rc 0) OR **`--confirm`** (emit planned overseer facts via `overseer_emit`, print results + remaining owed;
rc 0 on success, rc 1 if any emit fails). `--remote` mirrors `overseer_emit` semantics (`""`/`none` =
local; default `origin`). `--bus-id` (default `prod`) is used for BOTH the bus read AND every forwarded
`overseer_emit` emit, so read and write share one namespace. `release_order` is never in the emittable set.

Happy path across runs (one T1 candidate):
1. `overseer_plan --decision d.json --confirm` → emits `brief` + `assignment` + `cycle_go`; surfaces owed:
   `candidate` (coordinator), prelim `attestation` (primary_verifier), `ci_result` (CI), `release_order`
   (overseer-manual).
2. Seats/CI produce `candidate` + attestations + `ci_result` (via `bootstrap_emit` / the CI signer).
3. `overseer_plan --decision d.json` (dry-run) → "nothing to emit; owed: `release_order` (overseer-manual)
   — run `overseer_emit release_order --integration-sha <X>`."
4. Operator runs `overseer_emit release_order …` deliberately; the merge-gate daemon promotes the test ref.

## 6. Decision-file schema (`overseer-decision/1`)

```json
{
  "schema": "overseer-decision/1",
  "candidate_id": "A:c1",
  "brief_id": "b1",
  "brief_version": 1,
  "tier": "T1",
  "allowed_paths": ["cinema/"],
  "assignment": {
    "pair": "A", "builder": "director", "builder_provider": "codex",
    "primary_verifier": "operator", "primary_verifier_provider": "claude",
    "executing_coordinator": "coordinator"
  },
  "policy_digest": null
}
```
- Required: `candidate_id`, `brief_id`, `tier` (one of T0/T1 for this increment), `allowed_paths` (non-empty
  list), `assignment` (all six sub-fields).
- Optional: `brief_version` (default 1); `policy_digest` (null/absent → derive
  `default_policy().policy_digest()` so `cycle_go` matches the gate).
- `integration_sha` and the `re_verify` nonce are NOT in the decision (bus-derived / minted).
- A `tier` of T2/T3 is rejected with a clear "T0/T1 only in this increment" message (DD-3 extension point).

## 7. Scope boundaries

**In:** §4 components + §8 tests + this spec.

**Deferred → T3 extension (fast-follow):** emit `approver_roster` + `re_verify_challenge` and decompose
the `co_sign not satisfied` PENDING into its overseer-emittable vs non-overseer-owed parts via `tier.py`.
The planner is structured so adding two facts + the `approvers[]` decision field is additive.

**Deferred (unchanged from sub-project 1's spec):** real seat↔bus wiring (sub-project 2); the hardening
track; real `refs/heads/main` promotion.

## 8. Testing (campaign TDD discipline; pins must be non-vacuous)

- **Decision loader:** a valid file loads; dropping any required field → rc 2 with the field named
  (mutation: remove the field → RED).
- **Planner — empty bus:** plans `[brief, assignment, cycle_go]`; owes `release_order` (overseer-manual)
  + `candidate`/prelim `attestation`/`ci_result` (by owner).
- **Planner — idempotency:** with `brief` already on the bus, plans `[assignment, cycle_go]` only; with
  all three present, plans `[]` ("nothing to emit").
- **Dry-run pin (default):** a default run leaves the bus **byte-unchanged** (assert event count / tip
  unchanged) and prints the plan — mutation: an accidental emit reddens it.
- **`--confirm` pin:** emits `brief`/`assignment`/`cycle_go`, each round-trips through
  `verify_and_reduce` authority-correct (signer seat `overseer`).
- **Q4 checkpoint guard (mutation-tested):** after `--confirm`, `state.release_order(cid) is None`
  (overseer-plan must NOT have emitted it) — mutation: if `release_order` were added to the emittable set,
  this goes RED.
- **Idempotency pin:** two successive `--confirm` runs → the second makes **zero** `overseer_emit.main`
  calls (assert via a spy / unchanged bus tip) and exits 0 — the emittable set is empty, so
  `EventIdCollision` is never even reachable.
- **Single-signing-path pin:** the facts `overseer-plan --confirm` produces are authority-identical to
  those `overseer_emit` produces directly (same payload/envelope/signer).
- **Bare-subprocess pin:** add `overseer_plan.py` to `tests/unit/test_threeway_activation_scripts.py`
  (`ModuleNotFoundError`-absent + `--help` rc 0; ADR-055 self-bootstrap).

## 9. Verified anchors (re-derive against HEAD `a488276a` before implementing; do not trust blindly)

**Overseer-action trigger table** — `threeway/predicate.py` `PENDING` reasons → action:

| predicate PENDING reason (anchor) | owner | overseer-plan action |
|---|---|---|
| `no brief fact for brief_id/version` (predicate.py:83) | overseer | EMIT `brief` |
| `no assignment fact for pair` (predicate.py:63) | overseer | EMIT `assignment` |
| `no cycle_go for brief/version` (predicate.py:115) | overseer | EMIT `cycle_go` |
| `no release_order` (predicate.py:139) | overseer | SURFACE (manual — DD-4) |
| `no candidate fact yet` / `no candidate from executing coordinator` (predicate.py:48/55) | coordinator | SURFACE |
| `no effective preliminary/release GO from primary verifier` (predicate.py:90/96) | primary_verifier | SURFACE |
| `no ci_result for integration_sha` (predicate.py:155) | CI | SURFACE |
| `co_sign not satisfied for {eff_tier}` (predicate.py:131) | mixed (T2/T3) | OUT OF SCOPE (DD-3) |

**EffectiveState presence accessors** (`threeway/reducer.py`; all methods, call with the id) — used by the
planner for presence checks: `brief(brief_id, version)`, `assignment(pair)`, `cycle_go(brief_id, version)`,
`release_order(candidate_id)`, `candidate(candidate_id)`, `ci_result(subject_sha)`,
`effective_attestation(candidate_id, att_kind, seat)` (returns a raw `Event`, verdict at
`ev.payload["verdict"]`), `merge_completed(candidate_id)`.

**`overseer_emit` reuse surface** (`scripts/overseer_emit.py`, verified GO `a488276a`): `main(argv) -> int`
(0 ok / 1 fail). argv per fact:
- `brief`: `["brief","--candidate-id",cid,"--brief-id",bid,"--assigned-tier",tier,"--allowed-paths",*paths,"--repo-dir",repo,"--remote",remote,"--bus-id",bus]`
- `assignment`: `["assignment","--candidate-id",cid,"--pair",pair,"--builder",b,"--builder-provider",bp,"--primary-verifier",pv,"--primary-verifier-provider",pvp,"--executing-coordinator",ec,"--repo-dir",repo,"--remote",remote,"--bus-id",bus]`
- `cycle_go`: `["cycle_go","--candidate-id",cid,"--brief-id",bid,"--brief-version",str(ver),"--tier",tier,"--policy-digest",pd,"--repo-dir",repo,"--remote",remote,"--bus-id",bus]`

(All three forward `--bus-id` so the emit namespace matches the read; `overseer_emit._common` already
registers `--bus-id` (`overseer_emit.py:91`, default `BUS="prod"` at `:24`).)

**Policy:** `threeway.policy.default_policy().policy_digest()` is the digest the gate checks `cycle_go`
against (`predicate.py:121` policy_digest mismatch → REJECTED).

## 10. Acceptance criteria

- `overseer-plan` reads a valid decision file + the bus and, dry-run by default, prints the emittable
  overseer facts and the owed (non-emitted) facts with owners; it signs nothing without `--confirm`.
- `--confirm` emits the absent subset of `brief`/`assignment`/`cycle_go` via `overseer_emit`
  (authority-correct round-trip); it NEVER emits `release_order` (mutation-tested).
- Re-running is idempotent (only absent facts planned/emitted; complete state → nothing to emit).
- A T2/T3 decision is rejected with a clear "T0/T1 only" message.
- `ci_smoke` + `check_no_ceremony` clean (no new ceremony); full threeway suite green; spec drift fixed
  in-change.

## 11. Post-implementation

Per campaign discipline (impl≠verifier): the implementer's commits are `fixed`, not `verified`. Request an
independent operator Lane-V pass (mutation-test the dry-run no-emit, the `--confirm` authority round-trip,
the `release_order`-never-emitted checkpoint, and idempotency) before this is marked verified. Then the T3
extension or the hardening track per chief prioritization.
