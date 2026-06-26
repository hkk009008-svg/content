# Spec - Threeway expanded core mechanism

**Date:** 2026-06-26
**Status:** implemented on branch `antigravity-harness-adoption` through Task 8. Evidence commands are
listed in §9; original scope text below is preserved as the implementation spec.
**Scope:** make the signed three-way bus a first-class Codex/core protocol mechanism beyond the SP2
T1 path: include T2/T3 non-overseer emitters, revocation/supersession CLIs, bus-first Codex readiness
surfaces, real-main hardening boundaries, and docs sync. This spec records the intended scope; §9 records
the implementation evidence.

## 1. Grounding

This spec continues the SP2 handoff rather than reopening the whole protocol. SP2 already landed
`scripts/consume_bus.py` and `scripts/seat_emit.py`, retired `scripts/bootstrap_emit.py`, and proved a
T1 brief-to-merge flow through `overseer_emit`, `seat_emit`, `sign_ci_result`, `run_merge_gate`, and
`consume_bus`.

Verified before drafting:

```text
$ rg --files docs/protocol/threeway threeway scripts tests | rg '(threeway|seat_emit|consume_bus|overseer|tier|reducer|sign_ci|ci_result|bus_unread|event_store|protocol_model|continuation|mailbox|STATE|state)'
threeway/tier.py
threeway/reducer.py
threeway/refstore.py
scripts/seat_emit.py
scripts/consume_bus.py
scripts/overseer_emit.py
scripts/overseer_plan.py
scripts/sign_ci_result.py
scripts/run_merge_gate.py
scripts/bus_unread.py
scripts/continuation_readiness.py
tests/unit/test_threeway_seat_emit.py
tests/unit/test_threeway_overseer_emit.py
tests/unit/test_threeway_overseer_plan.py
tests/unit/test_threeway_e2e_walking_skeleton.py
```

The pre-implementation grep showed two classes of stale current-state text: SP2 limited the direct seat
CLI path to T1-equivalent facts, and threeway adoption docs still described the signed bus as
non-authoritative. Those lines are superseded by the implementation evidence in §9 and the docs sync in
Task 8.

The current implementation reality is therefore mixed:

- T1 seat-to-bus emission and consumption are live.
- T2/T3 gate predicates, reducers, and adversarial tests are already present.
- T2/T3 non-overseer event emission is not live through principal-safe CLIs.
- Some adoption docs still describe the pre-SP2 state.
- `run_merge_gate.py` defaults to `refs/threeway/test-main`; real `refs/heads/main` remains a hardening
  boundary, not a casual flag.

## 2. Goals

1. Add an executable mechanism ledger that says which three-way facts are live, partially live, or missing.
2. Complete principal-safe emitters for the non-overseer T2/T3 and revocation facts:
   `co_sign`, `re_verify`, `human_approval`, `attestation_revoked`, and `brief_superseded`.
3. Make T3 chief approver key provisioning explicit instead of relying on ad hoc test fixtures.
4. Prove complete T2 and T3 flows against `refs/threeway/test-main`, with negative cases that fail closed.
5. Make Codex readiness/status surfaces treat signed-bus state as first-class where the bus is already live,
   while preserving the free-form mailbox for human coordination.
6. Add real-main safety boundaries so `refs/heads/main` cannot be targeted by accidental operator flags.
7. Sync stale docs only after executable behavior is pinned.

## 3. Non-goals

- Do not replace free-form `coordination/mailbox/sent/*.md`; it still carries human-readable coordination.
- Do not let Codex or any live seat push protected `main`; the mechanical merge gate remains the writer.
- Do not put private keys in the repo or make a seat environment hold unrelated principal keys.
- Do not build external ref-ACL enforcement inside a single local repo. If a check is deployment-only,
  label it `test-infeasible` and make the local code fail closed where possible.
- Do not automate `release_order`; it remains a deliberate overseer action.
- Do not use real cloud/API/pod spend for this scope.

## 4. Architecture

### 4.1 Mechanism ledger

Create `docs/protocol/threeway/MECHANISM-LEDGER.md` and keep it backed by a small read-only verifier,
`scripts/threeway_mechanism_ledger.py`.

The ledger should classify each load-bearing kind from `threeway.LOAD_BEARING_KINDS` as:

```text
$ .venv/bin/python -c 'import threeway; print("\n".join(sorted(threeway.LOAD_BEARING_KINDS)))'
approver_roster
assignment
attestation
attestation_revoked
brief
brief_superseded
candidate
candidate_aborted
ci_result
co_sign
cycle_go
human_approval
merge_completed
re_verify
re_verify_challenge
release_order
release_requested
```

- `live`: production CLI or runtime path exists and has an executable test.
- `partial`: reducer/gate support exists, but principal-safe runtime emission is missing.
- `deferred`: intentionally outside this scope, with a `test-infeasible` or explicit follow-up reason.

The first expected classifications are:

- `live`: `brief`, `assignment`, `cycle_go`, `approver_roster`, `re_verify_challenge`, `candidate`,
  `candidate_aborted`, `attestation`, `release_requested`, `release_order`, `ci_result`,
  `merge_completed`.
- `partial`: `co_sign`, `re_verify`, `human_approval`, `attestation_revoked`, `brief_superseded`.
- `deployment-hardening`: remote owner-only cursor ACL, bus-host ref ACL, private-key custody, protected
  real-main runner deployment, chief approver key custody.

The verifier should not parse prose as truth. It should inspect script parser help or exported command
tables where feasible, import `threeway.LOAD_BEARING_KINDS`, and fail when the ledger omits a kind.

### 4.2 Authority-complete emitters

Extend the existing CLI family rather than adding another bus abstraction. Keep one append/sign path:
construct `threeway.envelope.Event`, call `RefEventStore.append`, and load exactly the principal key that
is supposed to sign the event.

#### `scripts/seat_emit.py`

Extend `seat_emit` for interactive operator/verifier facts:

- `co_sign`: emitted by the mirror pair's `primary_verifier` for T2/T3.
- `re_verify`: emitted by the candidate pair's own `primary_verifier` for T3, echoing the signed
  challenge as `payload["challenge_nonce"]`, not `payload["nonce"]`.
- `attestation_revoked`: emitted by a seat to revoke one of its own prior load-bearing facts.

For `co_sign` and `re_verify`, the CLI should read and verify current bus state before append:

- Resolve the candidate, assignment, `integration_sha`, and effective tier from the bus.
- Fail with rc2 and zero new events if the requested signer seat is not the required dynamic authority.
- For `re_verify`, require an overseer `re_verify_challenge` whose `subject_sha` equals the integration
  SHA; echo its nonce under `challenge_nonce`.
- Preserve gate as the security boundary, but prevent obvious wrong-principal writes at the CLI boundary.

This likely needs a small public resolver module, for example `threeway/approval_authority.py`, rather
than importing private helpers from `threeway.tier`.

#### `scripts/chief_emit.py`

Add a focused CLI for chief/human principal facts:

- `human_approval`: emitted by a rostered approver key, payload includes
  `{"approver_identity": <seat>, "integration_sha": <sha>, "decision": "approve"}`.
- `attestation_revoked`: emitted by the same chief key to revoke its own approval.

The CLI must:

- Load `load_private(<approver-seat>)`, never the overseer key.
- Read the bus and require an overseer `approver_roster` naming the approver seat.
- Require the candidate integration SHA and bind the approval to it.
- Fail with rc2 and zero new events for unrostered approvers, wrong SHA, missing roster, or unsupported
  decision.

Before this CLI is usable outside tests, make chief key provisioning explicit. `threeway/keys_bootstrap.py`
currently defaults to the six interactive seats plus `overseer`, `ci`, and `merge-gate`; T3 tests create
`chief-gemini` and `chief-chatgpt` keys ad hoc. The implementation must either add those chief seats to a
documented default/option or require an explicit `--seats chief-gemini chief-chatgpt` provisioning command
in the runbook. In either case, `chief_emit` must fail visibly when the roster names a seat with no public
registry key or when the local principal lacks that private key.

#### `scripts/overseer_emit.py`

Extend overseer emission for overseer-authority rollback facts:

- `brief_superseded`: carries `supersedes_event_id` for a prior brief version.
- `attestation_revoked`: overseer override revocation for any load-bearing event id.

The reducer already authorizes revocation/supersession by overseer or target signer; the CLI provides the
safe human-operated path. These subcommands must keep `release_order` manual and must not turn
`overseer_plan.py` into a merge-authorizing tool.

### 4.3 T2/T3 walking skeletons

Add `tests/unit/test_threeway_t2_t3_emitters_e2e.py` or extend the existing walking skeleton if the result
stays readable.

T2 happy path:

1. Overseer emits briefs/assignments/cycle_go for pair A and the mirror pair.
2. Pair A emits candidate + primary attestations.
3. CI emits `ci_result`.
4. Mirror pair primary verifier emits `co_sign`.
5. Release request/order happen.
6. `run_merge_gate.py --main-ref refs/threeway/test-main --run-once` completes.

T2 negative cases:

- Missing `co_sign` keeps the gate pending.
- Wrong mirror seat CLI call returns rc2 and appends zero events.
- A forged/manual wrong-seat `co_sign` may exist on the bus but does not satisfy the gate.

T3 happy path:

1. All T2 facts exist.
2. Overseer emits `approver_roster` and `re_verify_challenge`.
3. Candidate pair primary verifier emits `re_verify` with `challenge_nonce`.
4. Two distinct rostered chiefs emit `human_approval`.
5. Gate completes on `refs/threeway/test-main`.

T3 negative cases:

- Stale challenge nonce keeps the gate pending.
- One human approval keeps the gate pending.
- Two approvals from the same key collapse to one and keep the gate pending.
- Unrostered chief CLI call returns rc2 and appends zero events.
- Revoking `co_sign`, `re_verify`, or one human approval makes the gate pending again for an unmerged
  candidate.

### 4.4 Codex bus-first readiness surfaces

Do not remove mailbox orientation. The free-form mailbox remains the human coordination channel. The
change is that signed-bus facts become first-class in readiness and status output when the bus is live.

Expected surfaces:

- `scripts/continuation_readiness.py`: add a `Threeway Bus` section with local event tip, remote event ref
  availability, cursor availability, and unread bus counts for the six interactive seats.
- `.agents/skills/four-seat-protocol/scripts/seat_status.py`: keep current bus-unread behavior and add
  latest unread bus fact details when count is nonzero.
- `scripts/mailbox_monitor.py`: keep legacy mailbox fields, but label migrated seats as `ref-bus` and show
  event descriptors from `bus_unread.format_unread`.
- `scripts/codex_protocol_model.py`, `docs/protocol/codex/continuation.md`, and `.codex/agents/*.toml`:
  describe the signed bus as the load-bearing three-way state source while keeping mailbox-first for
  free-form four-seat protocol events.

The main design constraint is no silent zero. If the bus is unavailable or corrupt, render a visible
`(unavailable: ref-bus)` sentinel, not `0`.

### 4.5 Real-main hardening boundary

`scripts/run_merge_gate.py` currently defaults to `refs/threeway/test-main` and accepts `--main-ref`.
Keep the default. Add a hard boundary before any implementation plan allows real `refs/heads/main`:

- Refuse `--main-ref refs/heads/main` unless an explicit flag such as `--allow-protected-main` is present.
- Even with that flag, run a preflight function before polling:
  - verify the repo is clean for gate-owned refs,
  - verify `refs/threeway/events` is fetchable from the configured remote,
  - verify the public key registry contains all required seats,
  - verify `merge-gate` private key is loadable,
  - verify the target ref exists and is not a detached local-only ref,
  - verify CI result events bind the exact integration SHA,
  - emit a clear refusal if branch protection/ref-ACL cannot be verified from the current environment.

For checks that Git cannot prove locally, label the local check `test-infeasible` and document the required
deployment control. The local code must still fail closed when it cannot distinguish protected-main
conditions from unsafe conditions.

### 4.6 Docs sync

Only after the executable tests above are green, update:

- `docs/protocol/threeway/README.md`
- `docs/protocol/threeway/ONBOARDING.md`
- `docs/protocol/threeway/CODEX-ADOPTION.md`
- `docs/protocol/threeway/UNIFIED-OPERATING-DOCTRINE.md`
- `ARCHITECTURE.md`
- `DECISIONS.md`

Required doc changes:

- Replace stale pre-implementation claims that describe the signed bus as non-authoritative.
- Distinguish three layers: free-form mailbox, signed bus T1 seat path, and completed T2/T3 emitter path.
- State that `test-main` is the verified local/protocol target; real protected `main` requires the hardening
  preflight and deployment controls.
- Cite the commands that verify any numbers or inventory counts.

## 5. Error handling

All new CLIs should match existing operator-facing behavior:

- Authority or malformed requested action: rc2, stderr, zero new events.
- Missing key, git failure, append contention, malformed state, or bus unavailable: rc1, stderr, no traceback.
- Idempotent re-emission of the same logical event: rc0 and existing event returned by `RefEventStore`.
- Same id with different request: rc1 with a clean "Not emitted" message.

Zero-new-event authority tests are mandatory. A test that only checks gate pending is too weak because the
bad event may still pollute the bus.

## 6. Testing and verification

Focused expected commands:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_threeway_seat_emit.py \
  tests/unit/test_threeway_overseer_emit.py \
  tests/unit/test_threeway_overseer_plan.py \
  tests/unit/test_threeway_t2_t3_emitters_e2e.py \
  tests/unit/test_threeway_e2e_walking_skeleton.py -q

env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_threeway_tier.py \
  tests/unit/test_threeway_reducer.py \
  tests/unit/test_threeway_gate.py \
  tests/unit/test_threeway_gate_adversarial.py -q

env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_continuation_readiness.py \
  tests/unit/test_mailbox_monitor.py \
  tests/unit/test_bus_unread.py \
  tests/unit/test_threeway_keys_bootstrap.py \
  tests/unit/test_codex_protocol_model.py -q

env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py
```

Mutation/non-vacuous pins:

- Mutating `re_verify` to use `payload["nonce"]` instead of `payload["challenge_nonce"]` must redden T3.
- Removing the dynamic mirror-seat check must redden wrong-seat `co_sign` CLI tests.
- Removing roster validation must redden unrostered `human_approval` CLI tests.
- Removing the real-main refusal must redden a `run_merge_gate.py --main-ref refs/heads/main` test.
- Replacing bus-unavailable sentinel with `0` must redden readiness/status tests.

## 7. Acceptance criteria

- Mechanism ledger exists and covers every `LOAD_BEARING_KINDS` member.
- Chief approver key provisioning is explicit and tested; T3 no longer relies only on ad hoc fixture keys.
- T2 and T3 happy paths complete against `refs/threeway/test-main` using real CLIs and temp keys.
- T2/T3 negative paths fail closed and prove zero new events where CLI authority should block.
- Revocation/supersession facts can be emitted through principal-safe CLIs and affect unmerged gate state.
- Codex readiness/status output surfaces ref-bus state without silent zero degradation.
- `run_merge_gate.py` cannot target `refs/heads/main` accidentally.
- Stale adoption docs are updated with command-cited evidence after tests pass.
- No push, lock claim, pod spend, paid API spend, or real protected-main merge is part of this implementation.

## 8. Implementation sequencing

This scope is large enough to require a plan before code. Recommended plan slices:

1. Mechanism ledger and current-state tests.
2. `seat_emit` T2/T3 operator facts.
3. `chief_emit` human approvals.
4. `overseer_emit` revocation/supersession facts.
5. T2/T3 E2E and negative-path tests.
6. Codex readiness/status bus-first surfacing.
7. Real-main guard/preflight.
8. Docs sync and ADR.

Each slice should be independently testable, with one focused commit. Implementation should use the
subagent-driven development path from the project plan discipline: implementer, spec review, code-quality
review, then parent synthesis before any verify request.

## 9. Implementation evidence

Verified via `env -u GIT_INDEX_FILE .venv/bin/python scripts/threeway_mechanism_ledger.py --check` -> exit 0.

Verified via `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_t2_t3_emitters_e2e.py -q`:

```text
......                                                                   [100%]
6 passed in 41.34s
```

Verified via `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_run_merge_gate_protected_main.py -q`:

```text
..                                                                       [100%]
2 passed in 0.03s
```

Final focused verification after Task 8 status sync:

- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_mechanism_ledger.py tests/unit/test_threeway_keys_bootstrap.py tests/unit/test_threeway_seat_emit.py tests/unit/test_threeway_chief_emit.py tests/unit/test_threeway_overseer_emit.py tests/unit/test_threeway_t2_t3_emitters_e2e.py tests/unit/test_threeway_e2e_walking_skeleton.py tests/unit/test_threeway_run_merge_gate_protected_main.py -q`:

```text
............................................                             [100%]
44 passed in 61.24s (0:01:01)
```

- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_tier.py tests/unit/test_threeway_reducer.py tests/unit/test_threeway_gate.py tests/unit/test_threeway_gate_adversarial.py -q`:

```text
........................................................................ [ 49%]
........................................................................ [ 98%]
..                                                                       [100%]
146 passed in 10.24s
```

- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_continuation_readiness.py tests/unit/test_mailbox_monitor.py tests/unit/test_bus_unread.py tests/unit/test_codex_protocol_model.py -q`:

```text
................................................                         [100%]
48 passed in 17.38s
```

- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> exit 0, including
  `RESULT: no ceremony detected - every relied-on green is backed by execution.` and known pre-existing
  `cv2` importorskip warning.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py` -> exit 0, including
  `RESULT: no ceremony detected - every relied-on green is backed by execution.` and known pre-existing
  `cv2` importorskip warning.
