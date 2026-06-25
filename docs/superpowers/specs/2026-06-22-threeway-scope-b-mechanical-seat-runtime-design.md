# Spec — Threeway scope-b, sub-project 1: minimal operable mechanical-seat runtime

**Date:** 2026-06-22
**Status:** design approved (brainstorming); awaiting spec review + implementation plan.
**Scope:** the FIRST of two scope-b sub-projects. Makes the three mechanical seats
(`overseer`, `ci`, `merge-gate`) into operable processes so a candidate can flow
brief→merge end-to-end **driven by a human operator**. The interactive seats (sub-project 2)
still use the legacy mailbox; this sub-project provides an explicit temporary shim for their facts.

> Truth lives in the code. This spec mirrors `threeway/loop.py:build_candidate_events`,
> `threeway/predicate.py`, `threeway/gate.py`, `threeway/reducer.py`, `threeway/tier.py`, and
> `scripts/sign_ci_result.py` as they stand at HEAD `e45f2cf6` (ADR-055). Verify against them before
> implementing; fix drift in the same change.

## 1. Context

The threeway signed bus is **live as infrastructure** (cut over 2026-06-22: 768 carriers on
`refs/threeway/events` on origin, `THREEWAY_BUS_LIVE=true`, `.pub` trust root committed). But the
**strategic-loop runtime is unbuilt** — `import threeway` appears only in `threeway/`, `tests/`, and
the three go-live scripts; no live seat emits or consumes bus events. Until that runtime exists, the
signed bus has no producers and the seats keep coordinating via the legacy mailbox.

This sub-project builds the **smallest runtime that makes the bus operable end-to-end**, chosen as
"minimal operable" over a fully-hardened build (see §7 deferred items). It was scoped after an external
architecture review (2026-06-22) whose verified findings are folded in: most "blocking" issues were
already implemented (the review assessed the lossy diagram); the genuine gaps are deferred to a
hardening track, and the confirmed framing items are carried as spec content here.

## 2. Goals / non-goals

**Goals**
- Emit every overseer-authority fact via a human-operated, audited signing CLI.
- Deploy the merge-gate as a standing daemon that promotes the protected **test** ref.
- Make the CI `ci_result` signer actually run (fix the `PYTHONPATH` crash).
- Provide a clearly-temporary bootstrap emitter for interactive-seat facts so a full
  brief→merge flow is demonstrable now.
- Prove operability with an end-to-end walking-skeleton test.

**Non-goals (this sub-project)**
- No real seat↔bus wiring (sub-project 2).
- No promotion of real `refs/heads/main` (stays on `refs/threeway/test-main`).
- None of the hardening-track items in §7.

## 3. Components

### 3.1 `scripts/overseer_emit.py` — overseer signing CLI (the authority deliverable)
- Subcommands, one per overseer-signed fact kind: `brief`, `assignment`, `cycle_go`,
  `release_order`, `approver_roster`, `re_verify_challenge`.
- Each subcommand:
  1. Parses + **validates** the per-kind required args (below) before doing anything.
  2. Builds an `Event` whose payload keys **exactly match** the shapes emitted by
     `threeway/loop.py:build_candidate_events` (R-BRIEF: that builder is the implicit spec; a wrong
     key name makes the reducer/predicate silently drop or reject the fact).
  3. Loads `keys.load_private("overseer")` — and ONLY the overseer key (the CLI cannot sign as
     another seat).
  4. Appends via `RefEventStore(repo_dir, remote=remote)` (default `--remote origin`), reusing the
     proven `sign_ci_result.py` pattern (append-CAS, idempotency, signature).
- Per-kind fields — the **payload dict** and the **envelope kwargs** are DISTINCT; getting one in the
  wrong place makes the predicate silently reject. Mirror `threeway/loop.py:build_candidate_events` for
  the four facts it builds, and `threeway/tier.py` + `threeway/reducer.py` for the two it does not.
  `candidate_id` is always the envelope `candidate_id` (the full pair-namespaced id).
  - `brief` (loop.py:80-82): payload `{brief_id, assigned_tier, allowed_paths[]}`; envelope `brief_id`
    (+ `brief_version` lives on the **envelope**, default — it is NOT a payload key).
  - `assignment` (loop.py:83-88): payload `{pair, builder, builder_provider, primary_verifier,
    primary_verifier_provider, executing_coordinator}`.
  - `cycle_go` (loop.py:101-103): payload `{brief_id, brief_version, tier, policy_digest}`.
  - `release_order` (loop.py:109-110): payload `{candidate_id}` only; **envelope** `subject_sha`=
    integration_sha (NOT a payload key — `predicate.py:142` reads `ro.subject_sha`).
  - `approver_roster` (NOT in loop.py — consumer `tier.py:154` `roster.payload.get("approvers")`, fold
    `reducer.py:367-371`): payload `{approvers: [seats]}` (allowed approver **seats**); keyed by envelope
    `candidate_id`.
  - `re_verify_challenge` (NOT in loop.py — consumers `tier.py:131` `challenge.payload.get("nonce")` and
    `tier.py:129` `challenge.subject_sha`, fold `reducer.py:357-362`): payload `{nonce}`; **envelope**
    `subject_sha`=integration_sha; keyed by envelope `candidate_id`. The CLI MINTS a fresh unguessable
    nonce via `secrets.token_hex(...)` (the ADR-043 freshness precondition: the overseer must issue
    fresh, non-reused nonces; the gate enforces only the echo binding).
- Exit non-zero with a clear message on any validation failure or key-load failure.

### 3.2 Merge-gate daemon deployment
- `scripts/run_merge_gate.py` already exists; deploy it as a standing loop via a thin
  `scripts/run_merge_gate.sh` wrapper that exports `PYTHONPATH` (repo root), passes
  `--registry-dir coordination/threeway/keys`, and **`--main-ref refs/threeway/test-main`**.
- **Safety boundary:** the minimal daemon writes the existing Slice-1 protected **test** ref
  (`predicate.py:26 MAIN_REF = "refs/threeway/test-main"`), NOT `refs/heads/main`. Promoting real
  `main` is deferred to the hardening track (it ties to G1/ref-ACL deployment hardening). A daemon
  bug therefore cannot corrupt real main.
- Runs where the `merge-gate` private key lives and **candidate code never runs** (the gate is
  object-store-only by invariant; `gitcas.py` never checks out a working tree).
- Per-outcome logging (MERGED / `{outcome} {cid}: {reason}`) ALREADY exists (`run_merge_gate.py:65-68`).
  The only new daemon code is a **clean-shutdown handler**: install a `SIGTERM`/`SIGINT` handler that
  sets a stop flag; the loop checks it at the top of each iteration and exits 0 after logging
  `merge-gate daemon stopped` (never abort mid-`run_gate` — it is already TOTAL). The wrapper script is
  the other new deliverable.

### 3.3 CI signer — DONE (ADR-055, `e45f2cf6`); verify & preserve, no new code owed
- The `ModuleNotFoundError` crash is already fixed: `scripts/sign_ci_result.py:19-22` self-bootstraps
  the repo root onto `sys.path` (chosen over a ci.yml `PYTHONPATH:` so `run_merge_gate.py` and
  `agy_observer.py` get the same treatment). A bare-subprocess pin already exists —
  `tests/unit/test_threeway_activation_scripts.py::test_activation_script_runs_as_a_bare_subprocess`
  runs all three scripts the way CI invokes them.
- This sub-project therefore owes NO new CI/signer code here — only: confirm that pin stays green and
  that the §3.2 daemon wrapper relies on the same `sys.path` bootstrap rather than re-introducing a
  `PYTHONPATH` dependency. Keep the minimal `needs:`-trust model; the independent attestor (re-derive
  outcome + runner-image/test-set digest + nonce) is a §7 fast-follow.

### 3.4 `scripts/bootstrap_emit.py` — temporary interactive-seat fact emitter (the shim)
- Header comment states it is a TEMPORARY bootstrap, replaced by sub-project 2 (real seat↔bus wiring).
- Emits `candidate`, `attestation` (preliminary @ branch_sha, release @ integration_sha), and
  `release_requested` as the relevant seat, loading that seat's local key. Reuses the `loop.py`
  builders directly where possible.
- Lets a human drive a complete brief→merge flow for end-to-end validation today.

## 4. Data flow (one T1 candidate, happy path)
1. Operator (relaying chief decisions) → `overseer_emit brief` / `assignment` / `cycle_go` → bus.
2. `bootstrap_emit` → `candidate`, preliminary + release `attestation`, `release_requested` → bus.
3. CI (GitHub Actions, manual `workflow_dispatch`) → signs `ci_result` @ integration_sha → bus.
4. Operator → `overseer_emit release_order` @ integration_sha → bus.
5. Merge-gate daemon polls → `run_gate` → verify+reduce → predicate → recompute trusted merge →
   exact-SHA CAS to `refs/threeway/test-main` → emit `merge_completed`.

## 5. Error handling
- CLIs validate payloads before signing; fail loud on bad/missing args; load only the named seat key.
- Append contention is handled by `RefEventStore`'s existing retry; surface `AppendContentionExceeded`
  with a clear message.
- The daemon relies on `run_gate` being TOTAL (never raises post-CAS, ADR-040) plus the existing
  per-iteration `try/except` (`run_merge_gate.py:69-70`); add outcome logging and clean shutdown.

## 6. Testing (campaign TDD discipline)
- **Per-CLI round-trip pins:** emit a fact → `gate.verify_and_reduce` shows it present and
  authority-correct; **mutation** (wrong payload key, or non-overseer key) → the predicate
  REJECTs/PENDINGs — proving the pin is non-vacuous.
- **CI signer subprocess pin:** run `scripts/sign_ci_result.py` as a subprocess the way CI does;
  assert no `ModuleNotFoundError` (RED before the fix).
- **Daemon `--run-once` pin:** over a synthetic bus with a planted MERGEABLE candidate, assert it
  merges; with none, assert clean no-op.
- **End-to-end walking-skeleton test:** drive a full T1 brief→merge through the real CLIs (invoked as
  **subprocesses**, the way they actually run) + the daemon (`--run-once`) against a temp bus + temp
  repo; assert `refs/threeway/test-main` advances and `merge_completed` is emitted. This is the
  "operable" acceptance proof.

## 7. Scope boundaries

**In:** §3 components + §6 tests + this spec carrying the carried decisions in §8.

**Deferred → hardening track (gates production sign-off; the review's conditions #1/#5/#6/#7):**
- CI **attestor** independent validation: re-derive the test outcome, bind a runner-image digest, a
  test-set digest, and a nonce (review B1 residue).
- Per-principal human-approver keys (each chief holds their own key) — review B3/#3 hardening.
- External trust anchor for gate build / policy / key registry, pinned outside the repo the gate
  writes (review G1).
- Ref-ACL / append-only **enforcement** on the bus host (deny force-delete/force-update/withhold);
  retention; replication (review G2-substrate).
- Liveness/recovery: timeouts, seat reassignment, cancellation, stale-candidate eviction, emergency
  rollback; **wire the existing dead `rework.py` ESCALATE breaker** into the driver (review G5).
- Key versioning/rotation, replacement-key enrollment, effective-time-scoped revocation,
  overseer-key-compromise break-glass (review I5).
- Richer attestation payloads: policy version, toolchain digest, evidence hash, expiry; bind tree-OID
  separately (review G4).

**Deferred → automation track (fast-follow, ABOVE this sub-project):**
- **`overseer-plan` auto-decompose layer.** A tool above `overseer_emit` that ingests ONE structured
  chief decision (a defined decision-schema = the chief-output contract) + the current bus state, and
  emits the correct ORDERED sequence of overseer facts — instead of the operator hand-issuing each
  `overseer_emit`. Constraints: (a) **dry-run + explicit confirm** before signing — preserves the human
  checkpoint on the release key (`release_order`); (b) emits ONLY overseer-authority facts and SURFACES
  the non-overseer facts still owed (candidate / attestation / ci) for the seats or `bootstrap_emit`;
  (c) **idempotent** — re-reads the bus, never re-emits a fact already present. Turns "chief decision →
  you relay → operator hand-emits N facts" into "chief decision → you relay → `overseer-plan` emits the
  sequence on confirm." Deferred from minimal because it removes a per-fact human checkpoint and needs
  the structured-decision schema defined first; it is the first step toward the fully-automated overseer
  (the deferred Approach B). Its trigger logic is exactly the overseer-action trigger table (each
  predicate `PENDING "no <overseer fact>"` → emit that fact).

**DONE (sub-project 2, ADR-061):** real seat↔bus wiring — interactive seats emit via `scripts/seat_emit.py` and read via `scripts/consume_bus.py`; `bootstrap_emit.py` retired.

## 8. Carried decisions (from the 2026-06-22 review verification)
- **Fault model (review B5):** within a pair the verifier and integrator share a provider, so the
  independent third party is **the mechanical gate + overseer + CI**, NOT a third provider. A single
  compromised provider cannot merge alone: the coordinator signs only SHA facts (no semantic
  authority; the gate recomputes the merge and the tier), and a merge still requires overseer-signed
  brief/cycle_go/release_order + ci-signed PASS + (T2+) the other provider's mirror co-sign.
- **`integration_sha` is a deterministic COMMIT OID (review B2):** recomputed and equality-checked by
  the gate (`gate.py:204-208`); byte-reproducible because `_DET_ENV` pins author/committer
  name+email+date and the message is the fixed `threeway merge <cid>` string; the tree is
  host-independent via ADR-048 `-c` flags. Unclean (conflict) merges are hard-REJECTED, so manual
  conflict resolution is structurally impossible.
- **Exact T2/T3 required signer seats (review I4):** T0/T1 — none. T2 — the EXACTLY-ONE mirror pair's
  primary_verifier seat (provider role-swap), key-bound `co_sign` GO @ integration_sha
  (provider-diversity). T3 — T2 PLUS the candidate pair's own primary_verifier `re_verify` GO echoing
  the overseer challenge nonce, PLUS two DISTINCT key-bound `human_approval` seats on the overseer
  `approver_roster` (seat-diversity). Always-required: overseer brief/cycle_go/release_order, the
  pair's primary_verifier preliminary+release GO, ci `ci_result` PASS.
- **`required_ci` (review I3):** currently advisory/unwired — `policy._REQUIRED_CI` has no
  predicate/gate consumer; the predicate enforces a single `ci_result` PASS tier-independently, and
  T0/T1 are byte-identical in requirements. Decision: document as advisory for now; wiring it into the
  predicate's CI clause (so the per-tier table becomes load-bearing) is a hardening-track option.

## 9. Acceptance criteria
- `overseer_emit` can emit all six facts; each round-trips through `verify_and_reduce` as
  authority-correct; mutation pins are RED on the wrong payload/key.
- The merge-gate daemon runs standing against the live bus, promotes `refs/threeway/test-main` for a
  MERGEABLE candidate, and no-ops cleanly otherwise.
- The CI signer runs without `ModuleNotFoundError` (subprocess pin GREEN).
- The end-to-end walking-skeleton test drives a full T1 brief→merge and passes.
- `ci_smoke` + `check_no_ceremony` clean; full threeway suite green; spec drift fixed in-change.
