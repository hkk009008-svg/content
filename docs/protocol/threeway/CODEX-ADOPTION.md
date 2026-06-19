# Codex — Three-Way Protocol Adoption Manual

**Read first:** [`UNIFIED-OPERATING-DOCTRINE.md`](UNIFIED-OPERATING-DOCTRINE.md) (the shared rules) and
the spec
[`docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md`](../../superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md)
(the truth-source for Layer 1). **Codex's own root contract is [`AGENTS.md`](../../../AGENTS.md);** its
executable harness model is [`scripts/codex_protocol_model.py`](../../../scripts/codex_protocol_model.py)
and its mechanics adapter is [`docs/protocol/codex/continuation.md`](../codex/continuation.md). When
this manual disagrees with those, **they win — fix this file in the same change.**

This manual is for a Codex session adopting the **three-way cross-provider protocol**. The headline:
**Codex already implements almost all of the Layer-2 operating doctrine.** Adoption is therefore
*not* a rewrite — it is (1) knowing which Layer-1 seats Codex holds, and (2) executing the bounded
migration that makes the signed bus live. Do not duplicate what already exists.

---

## 1. What Codex already has (adapt, don't rebuild)

Verified present in-repo. Treat these as the substrate the threeway protocol plugs into:

- **The kernel** — [`scripts/codex_protocol_model.py`](../../../scripts/codex_protocol_model.py): the
  12 active kernel invariants, **four runtime modes** (readiness-bridge | live-seat | coordinator |
  subagent), the **16-variable `CODEX_*` env contract** with per-mode defaults, the
  concrete-seat-vs-behavior-source map, the Pair Operating Contract, and the Seat Subagent Development
  contract.
- **Six spawnable role agents** — `.codex/agents/`: `protocol-director`, `protocol-operator`,
  `protocol-coordinator`, `readiness-bridge`, and read-only `lane-v-verifier` + `money-gate-reviewer`;
  plus self-codified `agentNN.toml` guardrail extensions (`agent01`–`agent04`).
- **Three hooks** — `.codex/hooks.json`: `session-smoke.sh` (R-START smoke tripwire, fail-open),
  `guard-git-index.sh` (blocks git-mutators / pytest missing `env -u GIT_INDEX_FILE` when a per-seat
  index is set), `update-state.sh` (regenerates STATE.md + presence heartbeat + per-seat index
  refresh + skip-worktree clear).
- **The mailbox bus** — `coordination/mailbox/sent/` + `seen/<seat>.txt` cursors +
  `coordination/bin/{send-event,consume-events,claim-lock,release-lock}`; coordinator unpinned.
- **Per-seat git isolation** — `GIT_INDEX_FILE=<git-dir>/index-codex-$CODEX_SEAT` + the `env -u
  GIT_INDEX_FILE` policy for ordinary git/pytest.
- **Read-only orientation/gating scripts** — `continuation_readiness.py`, the four-seat-protocol
  skill's `seat_status.py`, `wave_gate_check.py`, `protocol_capacity_board.py` (`--validate-route`),
  `protocol_doctor.py`, `ci_smoke.py`.
- **The agent-agnostic doctrine** — `AGENTS.md` + `docs/protocol/agents/` already carry R-EVIDENCE,
  R-MEASURE, R-VERIFY-TIER, R-ORCH, R-BRIEF/Rule #12/#13, anti-ceremony, authority precedence,
  same-seat-handoff-first, and user-gated side effects.

**Conclusion:** the entire Layer-2 doctrine is live for Codex today. The Part III capability table in
the unified doc maps cleanly onto Codex's primitives. The remaining work is **Layer-1**.

## 2. Which threeway seats Codex holds

From the spec §4 / [`threeway/loop.py:43-52`](../../../threeway/loop.py):

| Threeway seat | Codex role | Pair | Maps to the Codex harness as… |
|---|---|---|---|
| `director` | **builder** (own branch) | A | a Codex `live-seat` (`CODEX_SEAT=director`) — its behavior source is already `director2` per `SEAT_BEHAVIOR_SOURCE` |
| `operator2` | **primary verifier** (read-only repo) | B | a Codex `live-seat` (`CODEX_SEAT=operator2`) — behavior source `operator`; pair with the `lane-v-verifier` role agent |
| `coordinator2` | **executing integrator** (staging refs only) | B | **does not exist in the Codex harness yet** — see §4 (it is Slice 2.5 scope, not a `codex_protocol_model.py` edit) |

Codex's builder (`director`) is verified by Claude's `operator`; Codex's verifier (`operator2`)
verifies Claude's `director2` build; Codex's `coordinator2` integrates Claude-built candidates. That
is the cross-provider independence property in practice — **a Codex seat never primarily verifies or
integrates Codex-built code.**

> The `CODEX_SEAT` values today are `director | director2 | operator | operator2 | coordinator`
> (`scripts/codex_protocol_model.py:151-154`). They overlap with the threeway builder/verifier seat
> names but the threeway bus also needs `coordinator2`, `overseer`, `ci`, `merge-gate` — those are
> mechanical/strategic, not Codex `live-seat`s, and are provisioned as **keys**, not as harness modes.

## 3. Prerequisite: key provisioning and custody

The signed bus needs Ed25519 keys per seat. **The correct generation command is a single
invocation** (`threeway/keys_bootstrap.py:16-29`) — *not* one call per seat, and there is no
`--seat` flag:

```bash
.venv/bin/python -m threeway.keys_bootstrap \
    --registry coordination/threeway/keys \
    --keystore "$THREEWAY_KEYSTORE"
```

This generates **all nine** seats in one pass (`director, operator, coordinator, director2,
operator2, coordinator2, overseer, ci, merge-gate`), writing `<seat>.pub` to the registry and
`<seat>.ed25519` to the keystore (default `~/.threeway/keys` per `threeway/keys.py:66`). To restrict,
use the **plural** `--seats director operator2 ...`.

**Generation ≠ custody — this is the load-bearing distinction (`threeway/keys.py:3-13`; spec §6.2 key isolation + §12 key management):**

1. **Commit only the `.pub` files** in `coordination/threeway/keys/` (the trust root). Private keys
   are **never** committed.
2. **Distribute each `<seat>.ed25519` to the single environment that runs that seat**, then remove it
   from the central keystore. A Codex session running `operator2` holds **only** the `operator2`
   private key.
3. **No private key — and especially not the `merge-gate` credential — may live in any environment
   that executes candidate code.** The `ci` key lives only on the unprivileged CI runner; the
   `merge-gate` key lives only on the protected merge-gate runner.

Set `THREEWAY_KEYSTORE` to point at the seat-local keystore; Codex loads its key via
`threeway.keys.load_private(seat)` and verifies others via `PublicKeyRegistry(registry_dir)`.

## 4. The adoption path (sequenced — there is no switch to flip)

Per the unified doc §I.5, the `threeway/` package is **wired into nothing** today, and the design
**forbids dual-write** (`docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md:70`, audited). So adoption is the migration,
in order:

1. **Provision keys** (§3) and commit the registry.
2. **Slice 2.5 — author the real migration plan** from the stub. The concrete Codex edit-sites are
   the **six seat-list copies** that must change together to make `coordinator`/`coordinator2`
   first-class receiving seats: `scripts/protocol_mailbox.py:11` (`SEATS`), `coordination/bin/send-event`,
   `coordination/bin/consume-events`, `scripts/check_coordination.py`, `scripts/status.py:126`
   (`_MAILBOX_SEATS`). Backfill cursors ISO→scalar `seq`. **Method: shadow read-only projection →
   single-writer cutover (no dual-write window).** The legacy mailbox stays authoritative until
   cutover.
3. **Wire CI to emit a signed `ci_result`.** Today `.github/workflows/ci.yml` runs bare `pytest
   tests/unit/` and signs nothing. A real `ci_result` (signed by the `ci` seat, binding
   `integration_sha` + `policy_digest`, `result: PASS`) must be produced by the unprivileged runner
   and appended to the bus before the gate's predicate can pass (`threeway/predicate.py:138-147`).
4. **Deploy the merge-gate** as a dedicated protected runner holding the only protected-`main`
   credential, invoking `threeway.gate.run_gate(...)`. Note: `run_gate` is an **in-process function**
   today (`threeway/gate.py:95`) — there is no daemon yet; the runner is what's missing.
5. **Slice 3** — the strategic loop, overseer distribution, `cycle_go`/`release_order`, and the T2
   other-pair-operator co-sign that makes `co_sign_satisfied` true for escalated tiers.

Only after this is the signed bus the live substrate. Until then, Codex coordinates on the **legacy
mailbox bus** exactly as it does today.

## 5. How a Codex seat emits threeway events (for when wiring lands)

When Codex operates a threeway seat against the live bus, it constructs and signs **its own** events
— it does **not** call `build_candidate_events` (that is a whole-loop *test/demo fixture* in
`threeway/loop.py` that fabricates all nine events for all seats as unsigned; the docstring says so).
The real pattern:

- Build an `Event` (`threeway/envelope.py`), set the `signer` to your seat, then **append + sign**:
  `store.append(event, load_private(my_seat))` — `append` signs with the seat key and assigns `seq`
  (`threeway/store.py:33-40`; `RefEventStore.append` for the ref bus, `threeway/refstore.py:122`).
- Each seat signs only the facts it owns (`predicate.py` enforces this by seat): the Codex
  `director` does **not** sign the candidate (the coordinator does) or the attestations (the operator
  does). A Codex `coordinator2` signs the `candidate`; a Codex `operator2` signs `attestation`
  (preliminary + release).
- `EventStore` vs `RefEventStore` is a **deliberate caller choice**, not an automatic switch; the
  *read* API (`iter_events`/`all_events`) is intended to stay stable, but the constructor differs
  (`RefEventStore(repo, remote=...)` vs `EventStore(events_dir)`).

## 6. Mode and orientation (unchanged from the existing harness)

- A fresh Codex session is a **readiness bridge** by default and never silently upgrades into a seat
  (`docs/protocol/codex/continuation.md`). It becomes `director`/`operator2`/`coordinator2` only on
  explicit user/parent instruction.
- On assuming a seat, **find the newest `docs/HANDOFF-<concrete-seat>-*.md` first**, then orient via
  `seat_status.py <seat> --wave <N>` (read-only), then check mail before any protocol decision.
- All Layer-2 rules in the unified doc apply verbatim through Codex's primitives (Part III): subagents
  via `.codex/agents/*.toml`, git hygiene via `guard-git-index.sh` + `env -u GIT_INDEX_FILE`,
  verification via the `lane-v-verifier` / `money-gate-reviewer` role agents, side effects
  user-gated.

## 7. Codex-specific hard rules (do not violate)

- **Never push to `main` from a Codex seat.** In the threeway protocol only the mechanical merge-gate
  writes protected `main`; `director`/`operator2`/`coordinator2` may not. (This composes with the
  existing user-gated-push rule.)
- **A Codex `coordinator2` does a deterministic merge-only stage** — any textual conflict is an ABORT
  → REWORK, never a semantic edit (a semantically-edited integration SHA would need fresh
  verification). The merge-gate recomputes the merge anyway and rejects a mismatch.
- **No dual-write.** Do not "read old tasks from the mailbox and write new ones to the threeway bus."
- **Keys never touch candidate-executing environments** (§3).
- **The `ci_result` is real evidence, not a fixture.** The fixture in `loop.py:99` does not satisfy
  the gate; CI must produce a signed one.

---

*Provenance: built against the verified `threeway/` package + `scripts/codex_protocol_model.py` +
`AGENTS.md` + `docs/protocol/codex/continuation.md`, cross-checked by audit `wf_34ae3dc6-731`. The
"what Codex already has" inventory is from distillation `wf_7dea0939-78c`.*
