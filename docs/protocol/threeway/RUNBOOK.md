# Three-Way Ready-Not-Live Runbook

This runbook is for the adoption phase where the threeway protocol is executable
for dry-run and preflight checks, but the **legacy mailbox remains authoritative**.
Do not treat any command here as a live authority flip.

## Current Boundaries

- Production public keys are not committed. `coordination/threeway/keys/` should
  contain only `README.md` until an explicit key ceremony.
- Private keys are never committed. They live only in the off-repo keystore named
  by `THREEWAY_KEYSTORE`.
- `.github/workflows/threeway-ci-dry-run.yml` is `workflow_dispatch` only. It
  uploads a signed dry-run `ci_result` artifact and never appends to the bus.
- `scripts/threeway_gate_runner.py` defaults to `refs/threeway/test-main` and
  refuses protected `main` refs.
- `scripts/threeway_cutover_check.py` is read-only. It never calls
  `threeway.cutover.run_cutover`.

## Readiness

Run the JSON report:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/threeway_readiness.py --json
```

Use the one-line form in local state or hooks:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/threeway_readiness.py --state-line
env -u GIT_INDEX_FILE .venv/bin/python scripts/threeway_readiness.py --hook-summary
```

Expected pre-live result: ready-not-live mode with blockers for missing
production public keys. That is correct until a user-gated key ceremony lands.

## Dry-Run CI Artifact

Use the manual GitHub workflow:

```text
Actions -> Threeway CI Dry Run -> Run workflow
```

The workflow:

- generates an ephemeral `ci` keypair under `$RUNNER_TEMP`;
- runs `python -m pytest tests/unit/test_threeway_*.py -q`;
- signs a dry-run `ci_result` with `scripts/threeway_ci_result.py`;
- uploads `ci-result.json` and `evidence-manifest.json`;
- does not call `scripts/threeway_append_event.py`.

Local artifact generation has the same shape:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m threeway.keys_bootstrap \
  --registry /tmp/threeway-registry \
  --keystore /tmp/threeway-keystore \
  --seats ci

env -u GIT_INDEX_FILE .venv/bin/python scripts/threeway_ci_result.py \
  --keystore /tmp/threeway-keystore \
  --bus-id dry-run-local \
  --candidate-id A:c1 \
  --integration-sha <40-char-sha> \
  --policy-digest <policy-digest> \
  --result PASS \
  --evidence-manifest <manifest.json> \
  --output <ci-result.json>
```

## Explicit Event Append

Use `scripts/threeway_append_event.py` only with an explicit input event JSON,
seat, registry, keystore, bus id, and pre-live store:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/threeway_append_event.py \
  --store-dir /tmp/threeway-events \
  --registry /tmp/threeway-registry \
  --keystore /tmp/threeway-keystore \
  --bus-id dry-run-local \
  --seat coordinator \
  --event-json <event.json>
```

The script refuses signer/kind authority mismatches and checks that the private
key matches the registry public key. It has no private-key fallback.

## Gate Dry Run

Default dry run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/threeway_gate_runner.py \
  --repo . \
  --registry /tmp/threeway-registry \
  --store-dir /tmp/threeway-events \
  --bus-id dry-run-local \
  --candidate-id A:c1 \
  --json
```

The default `main_ref` is `refs/threeway/test-main`. The wrapper refuses
`main`, `origin/main`, `refs/heads/main`, and `refs/remotes/origin/main`.
Production-main execution requires a later explicit task and a new user-gated
production flag outside this runbook.

## Cutover Preflight

Read-only cutover check:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/threeway_cutover_check.py \
  --repo . \
  --coord-root . \
  --json
```

This projects the legacy mailbox and reports divergence and existing
`refs/threeway/*` state. It does not append, advance cursors, backfill `seen/`,
or run `run_cutover`.

## Future Live Cutover Prerequisites

Do not execute these without an explicit user-gated live cutover task:

1. Production key ceremony: generate the full runtime signing roster, commit only
   `.pub` files, distribute each private key to its isolated runtime, and verify no
   private key enters candidate-executing environments.
2. Zero-divergence shadow proof: run the readiness and cutover-check reports
   against the live mailbox and record evidence.
3. CI live signer: promote the dry-run artifact path into a real signed
   `ci_result` bus append from the unprivileged CI runner.
4. Protected merge-gate runner: deploy the runner holding the only protected-main
   credential and wire the production-safe gate invocation.
5. Single authority flip: run the cutover only after the above evidence is green
   and the user explicitly authorizes the operation.
