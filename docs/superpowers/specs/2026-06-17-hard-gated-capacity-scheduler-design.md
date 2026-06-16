# Hard-Gated Capacity Scheduler Design

Date: 2026-06-17
Status: design approved by user-principal; ready for implementation planning
Authoring role: coordinator/design pass

## 0. Problem

The four-seat protocol already has durable mailbox state, seat roles, lock
rules, wave gates, operator verification reports, and coordinator-owned
reconciliation. It still relies too much on human interpretation to decide
whether all five active protocol actors are being used well:

- coordinator
- director
- operator
- director2
- operator2

The missing piece is a hard scheduler. The harness can describe how a routed
seat should behave, but it does not yet enforce a paced, balanced set of
work packets that can be worked simultaneously and then joined into a final
finished state.

This design adds a hard-gated capacity scheduler with explicit exceptions.
The default rule is: invalid routing does not proceed. Exceptions are allowed
only through a durable exception ticket that names the exact gate being
bypassed, its scope, and the convergence condition.

## 1. Goals

1. Give every protocol actor one clear packet per cycle, or a recorded
   idle/block reason.
2. Make work chunks independently executable when they are truly disjoint.
3. Prevent two seats from working the same files, lock, or verification target.
4. Preserve director/operator separation: directors implement/request
   verification; operators verify landed diffs and issue GO/NITS/FAIL.
5. Preserve coordinator boundaries: coordinator routes and reconciles, but does
   not author production fixes or issue correctness GO.
6. Make convergence explicit: a cycle is not finished until packets either
   reach done evidence or carry a valid exception, and the join gate succeeds.
7. Allow emergency or judgment-call bypasses without letting them disappear
   into chat memory.

## 2. Non-Goals

- Do not replace the existing mailbox protocol.
- Do not replace `docs/REMEDIATION-INVENTORY.md` as the campaign board.
- Do not let subagents become seats.
- Do not auto-push, claim locks, start pods, or spend paid API budget.
- Do not make the coordinator a production implementer.
- Do not require a new database. Durable repository artifacts are enough.

## 3. Design Choice

Use approach 2 from brainstorming: a capacity scheduler CLI plus route/hook
gates.

Rejected alternatives:

- Coordinator-route validation only: too weak because seats can drift after a
  valid route.
- Full orchestrator: too much authority shift, more brittle, and likely to hide
  the useful judgment currently held by each seat.

The scheduler follows three borrowed patterns:

- Kanban-style WIP: one active packet per actor unless blocked or exempted.
- CI DAG semantics: packets declare dependencies and join gates.
- Incident-command separation: coordinator owns global state; seats own the
  modifying or verifying work.

## 4. Durable Packet Model

Add a machine-readable work-packet format. The implementation may choose JSON
or TOML; JSON is preferred for simple parsing and tests.

Suggested path:

```text
coordination/capacity/packets/<packet-id>.json
```

Required fields:

```json
{
  "id": "wave4-identity-arcface-embselect-director",
  "wave": 4,
  "cycle": "2026-06-17-wave4-open",
  "owner": "director",
  "packet_type": "director-implementation",
  "row_ids": ["identity-arcface-embselect"],
  "allowed_paths": ["identity/validator.py", "tests/unit/..."],
  "lock_keys": [],
  "dependencies": [],
  "acceptance": [
    "brief names write sites",
    "focused regression or test-infeasible label",
    "verify-request sent to operator"
  ],
  "done_evidence": [],
  "next_recipient": "operator",
  "status": "ready"
}
```

Allowed `owner` values:

- `coordinator`
- `director`
- `operator`
- `director2`
- `operator2`

Allowed `packet_type` values:

- `director-implementation`
- `director-brief`
- `director-cosign`
- `operator-verification`
- `operator-doc-sync`
- `coordinator-route`
- `coordinator-reconcile`
- `coordinator-join`
- `receipt-only`
- `idle`
- `blocked`

Allowed `status` values:

- `ready`
- `active`
- `blocked`
- `done`
- `excepted`

Coordinator packets are coordination-only. A coordinator packet may route,
reconcile, validate, or join a cycle, but it cannot authorize coordinator
production fixes, operator GO, push, lock-claim side effects, pod spend, or
paid API spend. The four live seats remain the worker lanes; coordinator is
the WIP-limited global-state lane.

## 5. Capacity Board Command

Add a read-only command:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave <N>
```

The command reads:

- `docs/REMEDIATION-INVENTORY.md`
- `coordination/capacity/packets/*.json`
- `coordination/protocol-exceptions/*.json`
- `coordination/mailbox/sent/*.md`
- `coordination/mailbox/seen/*.txt`
- `coordination/locks/*`
- recent git commits
- `scripts/wave_gate_check.py <N>` output
- optionally `scripts/ci_smoke.py` when `--smoke` is set

It renders:

- one row per actor;
- current packet id or idle/block reason;
- dependency state;
- lock/path collisions;
- unread mailbox state relevant to each seat;
- convergence state;
- hard-gate failures.

It also supports machine output:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave <N> --json
```

The JSON output is the testable contract for hooks and route validation.

## 6. Hard Gates

The scheduler should fail closed when any of these conditions are true.

### G1. Seat Coverage

For an active cycle, coordinator plus all four live seats must each have
exactly one current packet, or a valid `idle`/`blocked` packet with a concrete
reason. "No one told this actor" is not a valid reason.

### G2. WIP Limit

A seat may have at most one `ready` or `active` packet in a cycle. New packets
for that seat must wait until the old packet is `done`, `blocked`, or
`excepted`.

### G3. Path And Lock Isolation

Two active implementation packets must not overlap `allowed_paths` or
`lock_keys`. Operators may verify paths touched by their target commit, but
operator packets must name the commit/range and must not claim production
write authority.

### G4. Dependency DAG

Packet dependencies must exist and must be acyclic. A packet may become active
only when its dependencies are `done` or `excepted` by a matching exception.

### G5. Director To Operator Boundary

A director packet cannot be marked `done` if it claims implementation
completion without:

- committed diff or explicit test-infeasible label;
- acceptance evidence filled in `done_evidence`;
- a verify-request mailbox event or a valid reason verification is not needed.

### G6. Operator Verification Boundary

An operator packet cannot become active unless it names:

- verify-request mailbox file or equivalent route;
- landed commit SHA or BASE..HEAD range;
- scoped files or row ids.

An operator packet cannot be `done` unless it records GO/NITS/FAIL evidence.
Only GO may satisfy a verified transition.

### G7. Coordinator Route Validity

A `coordinator-to-all` task-board event that opens active work must validate
against the capacity board before it is sent or committed. It must name the
packet ids assigned to each seat and the join condition.

### G8. Join Gate

A cycle cannot close unless:

- all packets are `done` or `excepted`;
- every implementation packet needing verification has operator GO;
- `scripts/wave_gate_check.py <wave>` is MET when a wave claim is made;
- `scripts/ci_smoke.py` is OK when environment cleanliness is claimed;
- inventory reconciliation is current for affected rows;
- a handoff or exact next trigger is recorded when work transfers or stops.

### G9. Exception Match

An exception may bypass only the exact gate, packet, path, row, and expiry
condition it names. Broad exceptions are invalid.

## 7. Exception Tickets

Suggested path:

```text
coordination/protocol-exceptions/<exception-id>.json
```

Required fields:

```json
{
  "id": "EX-2026-06-17-wave4-identity-fixture",
  "created_at": "2026-06-17T00:00:00Z",
  "approving_actor": "user-principal",
  "bypassed_gate": "G6",
  "reason": "live multi-detection DeepFace fixture is unavailable locally",
  "scope": {
    "packet_ids": ["wave4-identity-arcface-embselect-operator"],
    "row_ids": ["identity-arcface-embselect"],
    "paths": ["identity/validator.py"]
  },
  "expiry": {
    "type": "condition",
    "value": "fixture committed or row marked test-infeasible in inventory"
  },
  "convergence_condition": "operator records test-infeasible verification report and coordinator reconciles inventory",
  "status": "active"
}
```

Allowed exception approvers:

- `user-principal`
- `coordinator` only for coordinator-owned protocol/doc/test/log artifacts
- affected director plus affected operator for seat-local non-production
  exceptions

Disallowed exceptions:

- push authorization
- paid API spend
- pod spend
- silent lock acquisition
- coordinator production fixes
- operator GO without independent verification

Those remain user-gated or structurally forbidden.

## 8. Route Validation

Add a validation mode:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py \
  --wave <N> \
  --validate-route coordination/mailbox/sent/<event>.md
```

For `coordinator-to-all` task-board events, validation checks:

- the event names all packet ids;
- each named packet exists;
- each seat has one packet or valid idle/block packet;
- packet dependencies and locks are valid;
- the event does not imply push, spend, lock claim, or production work outside
  packet scope;
- the event names the join condition.

Implementation can start advisory for non-task-board mail, but task-board
mail should be hard-gated.

## 9. Hook Strategy

Add hard gates in the lowest-risk order:

1. CLI validation with tests.
2. Coordinator checklist and docs require the CLI before task-board routes.
3. A hook blocks commits adding `coordinator-to-all` task-board mail unless
   route validation passes.
4. Optional later hook blocks packet files with invalid schema or collisions.

The first implementation should avoid blocking ordinary seat cursor commits
and ordinary handoff docs. Gate only the new scheduler surfaces and
coordinator task-board routes.

## 10. Error Handling

All scheduler errors should be actionable:

- name the failed gate id;
- name packet ids and seats involved;
- name conflicting paths or locks;
- name the valid exception shape if an exception is allowed;
- never infer correctness from missing data.

Missing or malformed packet files fail closed for active cycles.

## 11. Testing

Focused tests should cover:

- packet schema parsing;
- exactly-one-packet-per-seat coverage;
- WIP limit per seat;
- path overlap detection;
- lock collision detection;
- DAG dependency ordering and cycle rejection;
- director packet done requirements;
- operator packet active/done requirements;
- route event validation;
- exception ticket matching;
- exception expiry/mismatch rejection;
- join gate close criteria.

Existing tests to keep green:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py -q
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

New tests should be narrow and fixture-driven. They should not require live
mailbox mutation, lock claims, network, pods, or paid APIs.

## 12. Implementation Sequence For Next Seat

1. Add the packet and exception parser in a new scheduler module, likely under
   `scripts/` unless a package boundary is already more appropriate.
2. Add `scripts/protocol_capacity_board.py` read-only rendering and `--json`.
3. Add validation rules G1-G9 with focused tests.
4. Add route validation for coordinator task-board events.
5. Add the least invasive hook or check that blocks invalid task-board commits.
6. Update Codex protocol docs and skills to require the capacity board before
   active coordinator task-board routes.
7. Add one sample packet fixture and one sample exception fixture under tests.
8. Run focused tests, protocol artifact tests, and smoke.

## 13. Acceptance Criteria

Implementation is complete when:

- a coordinator can render a capacity board from durable repo state;
- invalid active cycles fail with named gate ids;
- valid exception tickets bypass only their named gate and scope;
- invalid exceptions fail closed;
- coordinator task-board mail can be validated before commit;
- docs/skills tell future seats when to run the scheduler;
- focused scheduler tests pass;
- protocol model/artifact tests pass;
- `scripts/ci_smoke.py` passes.

## 14. Follow-Up Work

After the hard gate is stable, a later iteration may:

- generate packets from inventory rows automatically;
- add historical flow metrics;
- add a richer text dashboard for active monitoring;
- make scheduler output part of handoff scaffolding;
- add stricter enforcement for packet schema commits.

Those are deliberately outside the first implementation so the hard gate lands
small and testable.
