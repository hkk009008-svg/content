# Cross-Provider Seat Topology — Design Spec

**Date:** 2026-06-19
**Status:** Design (brainstorming output), revision 5 — adopts the dual-chief REVISE findings
as normative (event-sourced bus, mandatory signatures, gate-computed tier, full predicate,
operator-based co-sign, exact-SHA CAS promotion). Remaining items are field-level schemas /
mechanisms scoped to the implementation plan (§12). Pending user approval, then plan.
**Author seat:** Pair-A working session (Claude), driven by the user-principal.
**Adapts:** the *Three-Way Protocol Implementation Kit* (manual v1.0, ref 2026-06-18) to
this repository. Records the adaptation per the kit's bootstrap directive.

> **Ratified calls:** bus ordering = sequenced (uuid events + monotonic index + scalar
> cursor); Pair A/B candidates are independent, serially-queued (merge queue); the overseer
> issues a per-cycle `cycle_go` and a per-SHA `release_order`; T2/T3 second semantic opinion =
> the other pair's operator (choice A, both-model-families-must-agree).

---

## 1. Why this exists (context)

A formal multi-lens audit of the Three-Way kit (`wf_3f459475-0da`, 11 agents) did **not**
clear its "all agree" gate: the repo-fit lens reached DO_NOT_PROCEED on two grounds —
(1) the kit's correctness argument needs *three distinct providers*, but this repo runs
*four all-Claude seats*; (2) two CRITICALs lived on Antigravity's CLI write path.

The user-principal's design neutralizes all three surviving CRITICALs without importing the
kit's Postgres control plane:

- **Cross-provider within each pair** restores the independence property.
- **Antigravity leaves the CLI write path**: strategic reasoners are Gemini Deep Think +
  ChatGPT Pro used as *apps* (human-relayed); the overseer is read-only on code.

This spec is the adapted design we intend to build, on the **existing git-native bus**.

## 2. Goals / non-goals

### Goals
- Cross-provider independence: the builder-provider never performs the **primary**
  verification or the **executing** integration of its own work. (For T2/T3 the *second*
  semantic opinion comes from the other pair's operator — a real cross-family verifier — §7.2.)
- Every load-bearing event is **signed** (public-key); the merge-gate **never executes
  candidate code** — it acts only on signed facts and trusted CI (§6.4).
- Keep the existing git-native bus (`coordination/`) as substrate — no Postgres, no MCP.
- Promotion to `main` gated by **evidence bound to the exact merged SHA**, via a **single
  mechanical writer**.
- A per-cycle strategic loop that sets direction without putting strategic prose on the
  merge path.
- A bus hardened for concurrent, possibly multi-host, cross-provider writers.

### Non-goals (deliberately not adopting from the kit)
Postgres/SQLAlchemy/FastAPI control plane; MCP facade; Antigravity **CLI** as an autonomous
seat; DB-backed leases/fencing/proof tables as v1 (ideas borrowed, §10); dynamic
mid-attempt rotation (we use a static mirror).

## 3. Decisions (ratified) with rationale

| # | Decision | Rationale |
|---|---|---|
| D1 | Substrate = existing git-native bus, not a new control plane | Zero logged coordination-authority failures; reversible; avoids the infra jump the audit flagged (anti-pattern #18). |
| D2 | Mirrored cross-provider pairs: A = Codex director + Claude operator; B = Claude director-2 + Codex operator-2 | Restores correlated-error independence; hedges role-provider coupling; static form of the kit's rotation, no mid-attempt timing hazard. |
| D3 | Pairs are **complementary** — different briefs in parallel. "Mirror" = provider-role swap only. | Matches how the repo's two pairs already operate. Competing/compare-select mode deferred (§12). |
| D4 | Integration is a dedicated authority; neither director nor operator pushes `main`. | Kit rule: the builder must not integrate its own work. |
| D5 | Two coordinators, routed opposite-provider-to-builder: Codex-built → Claude coordinator; Claude-built → Codex coordinator. | Carries builder-provider ≠ integrator-provider to `main`; load-balances by pair. |
| D6 | Coordinators are **mechanically constrained**: deterministic clean merge only (§6.4); any conflict → `candidate_aborted` + REWORK. The coordinator signature is a *mechanical* integration agreement, not a semantic review. | A semantically-edited integration SHA would need fresh verification and creates verify/integrate correlation. |
| D7 | A single **mechanical merge-gate** is the sole writer to protected `main`. Coordinators stage candidates. | Two writers converging on `main` invite races/stale approvals/merge-order bugs. |
| D8 | Two-key promotion (operator release attestation + overseer `release_order`), both bound to the **exact integration SHA**, plus a gate-computed tier (§7.2). | Review consensus + kit invariants #11/#13. See §6.3. |
| D9 | Tiered co-sign (§7.2). **A NEW risk-tier scheme**, analogous to the kit's risk tiers — *not* the repo's Rule #23 (which governs co-sign *scope*; §7.3). | Cross-provider agreement where it can hurt; speed where it can't. |
| D10 | Overseer = read-only on code, write on control-plane (route / `cycle_go` / `release_order` / `abort`). Mechanical dispatcher + ledger; `data→info` is a real summarization step. | Separate repo permissions from control-plane permissions. |
| D11 | Dual chief = Gemini Deep Think + ChatGPT Pro, as apps (human-relayed). | App-mediated → no Antigravity CLI on any path; strategic-axis independence distinct from the verification axis. |
| D12 | Bus is **event-sourced**: immutable signed facts, uuid-named, with a **monotonic index** for total order (sequenced model). | A scalar cursor requires a total order; status/lifecycle are *facts*, not mutable fields (§6.1). |

## 4. Roles, seats, permissions

Colour = model family; seat = role; permission is explicit and separate from identity.

| Seat (bus id) | Provider | Layer | Repo perm | Bus perm | May NOT |
|---|---|---|---|---|---|
| `director` (Pair A) | Codex | build | W: own branch | R + emit (signed) | push `main`; verify/integrate own work |
| `director2` (Pair B) | Claude | build | W: own branch | R + emit (signed) | push `main`; verify/integrate own work |
| `operator` (Pair A) | Claude | verify | **R:repo only** | R + emit attestation | edit candidate; integrate; **push `main`** |
| `operator2` (Pair B) | Codex | verify | **R:repo only** | R + emit attestation | edit candidate; integrate; **push `main`** |
| `coordinator` (Pair A) | Claude | integrate | W: staging refs only | R + emit | write `main`; semantic code edits |
| `coordinator2` (Pair B) | Codex | integrate | W: staging refs only | R + emit | write `main`; semantic code edits |
| **merge-gate** | mechanical | release | **W: protected `main` (sole writer)** | R + emit | run candidate code; write if predicate (§6.3) fails |
| `overseer` | mechanical | strategy | **no code-write**; R: logs/branches/CI | W: route / `cycle_go` / `release_order` / `abort` | author code; issue a verdict |
| dual chief | Gemini Deep Think + ChatGPT Pro (apps) | strategy | none | via overseer (human-relayed) | write code or state directly |

**Merge-gate identity & invocation (security-critical).** The merge-gate is a single
mechanical process — a **dedicated, protected runner**, not a seat any agent can invoke. It
holds the *only* credential able to write protected `main`, stored outside every seat
environment. It is *triggered* by bus events but **re-evaluates the full predicate itself from
authoritative bus state** — it never trusts the trigger. It holds the merge-queue slot (a
`claim-lock` on the `main` target) while evaluating and writing atomically. It **never executes
candidate code** (§6.4); predicate fails → it emits `event_rejected` and does not write.

**Emergent property:** the provider that wrote a change is locked out of the **primary**
verification and the **executing** integration of its own work. (At T2/T3 it may give the
*second* semantic opinion via the other pair's operator — §7.2 — never as the sole or primary
approver.) The merge-gate holding the `main` credential never executes candidate code (§6.4).

## 5. Lifecycle and the two loops

### 5.1 Tactical loop (per task) — six logical steps

`strategy → build → preliminary verify → integrate(stage) → release attestation → release(merge-queue)`

1. **Brief** (versioned) originates in the strategic loop and is distributed to a pair.
2. **Build:** director builds on its own branch, runs build-side checks, commits `branch_sha`.
3. **Preliminary verify:** the pair's different-provider operator gets a **fresh checkout at
   `branch_sha`**, reproduces required checks, emits a **preliminary attestation** bound to
   `branch_sha`. `FAIL`/`NITS` → REWORK before staging is spent. Read-only; no code edits.
4. **Integrate (stage):** the routed coordinator deterministically **merges** (v1: merge-only,
   §6.4) the verified candidate onto current `main.head`, producing `integration_sha` on a
   **staging ref** and signing the `candidate` record. Any textual conflict → **ABORT → REWORK**
   (a re-stage mints a new `candidate_id`; no semantic edits).
5. **Release attestation:** the operator re-checks the **exact `integration_sha`** (CI on the
   staged tree) and emits a **release attestation** bound to `integration_sha`. *This* is the
   attestation the predicate checks — the pre-staging one does not satisfy it.
6. **Release:** the operator's release attestation is observed by the coordinator, which emits
   `release_requested(candidate_id, integration_sha)`; the overseer emits
   `release_order(candidate_id, integration_sha)`; the **merge-gate** acts only when both exist,
   re-evaluates the predicate (§6.3) atomically while holding the queue slot, and writes `main`
   iff it holds.

### 5.2 Strategic loop (per cycle)

`results → overseer (data→info + bookkeeping) → dual chief (analyze + order) → overseer
(distribute briefs + issue cycle_go) → tactical loop → results …`

The overseer's **`cycle_go(brief_id, brief_version, tier, policy)`** is the *strategic* key
("this brief, at this tier, is in scope this cycle"). It is necessary for a brief to enter the
tactical loop, but it is **not** the merge key. The merge key is the per-SHA
**`release_order(integration_sha)`** issued at step 6. The gate *does* check that `cycle_go`
covers the gate-computed tier (§7.2), so strategic approval is mechanically enforced, not
procedural.

## 6. Events, attestations, candidate, and the merge predicate

### 6.1 Append-only event model

The bus is **event-sourced**. Every record is an immutable, **signed**, append-only fact;
nothing mutates in place. A status change is a *new* fact referencing the fact it acts on. A
deterministic reducer replays facts in `seq` order to compute current ("effective") state.

Lifecycle and revocation are facts, not fields:

```
event_sent · event_acknowledged · event_rejected · event_timed_out · event_retried
attestation_revoked (revokes_event_id) · brief_superseded (supersedes_event_id) · candidate_aborted
```

**Effective-state rule (load-bearing).** The predicate operates only on *effective* facts: an
attestation is effective iff it is not revoked and is the operator's latest verdict for its
`(candidate_id, kind)`. So an operator that emits `GO` then later `FAIL` (or
`attestation_revoked`) leaves **no** effective `GO` — the gate cannot promote on a stale
verdict. A re-stage always mints a **new** `candidate_id`/`attempt_id`; ids are never reused, so
an earlier `candidate_aborted` is unambiguous.

### 6.2 Event envelope (signed, immutable)

```
event {
  id: uuid
  seq: int                      # assigned by the index append (§8); total order
  bus_id: string                # environment/bus id — rejects cross-bus / test→prod replay
  schema_version: string
  brief_id: uuid | null
  candidate_id: uuid | null
  kind: one of {
          brief, brief_superseded, candidate, candidate_aborted, assignment,
          attestation, attestation_revoked, co_sign, re_verify,
          cycle_go, release_requested, release_order, human_approval, ci_result,
          event_sent, event_acknowledged, event_rejected, event_timed_out, event_retried,
          dead_letter }
  from: seat_id
  to: seat_id | "all"
  subject_sha: 40-hex | null
  brief_version: int | null
  causation_id: uuid | null
  supersedes_event_id: uuid | null
  revokes_event_id: uuid | null
  signer: "seat:provider:session_uuid"            # session distinguishes a fresh re-verify by the same seat
  payload: object
  payload_digest: sha256(canonical(payload))      # canonical JSON (JCS); EXCLUDES signature + created_at
  idempotency_key: sha256(from + ":" + kind + ":" + (subject_sha|brief_version|"") + ":" + payload_digest)
  signature: <REQUIRED on all load-bearing kinds>
  created_at: RFC3339                              # ephemeral; NOT in payload_digest or idempotency_key
}
```

- **Signatures are mandatory** for every load-bearing kind. The signature covers canonical bytes
  over `{bus_id, schema_version, id, seq, from, to, kind, brief_id, candidate_id, subject_sha,
  payload_digest, causation_id}`. JSON canonicalization is **normative**. **Public-key** signatures
  (per-seat keypair) are used so a signature *verifier* cannot forge a signer (HMAC would let the
  merge-gate impersonate any seat). Append-only storage protects *history*; signatures
  authenticate the *author*.
- **Idempotency keys exclude ephemeral fields** (`created_at`, `signature`), so a timed-out retry
  of the same logical fact yields the *same* key and de-duplicates.
- **Key isolation:** candidate code must NEVER execute in an environment holding any signing key
  or the merge-gate credential (§6.4).

### 6.3 Attestation, candidate, and the merge predicate

```
attestation {
  attestation_id: uuid
  kind: "preliminary" | "release" | "co_sign" | "re_verify"
  candidate_id, brief_id, brief_version
  subject_sha             # branch_sha (preliminary) | integration_sha (release/co_sign/re_verify)
  policy_digest
  verdict: "GO" | "NITS" | "FAIL"
  evidence_manifest_digest    # signed evidence manifest (§12), not a bare digest
  # signer + signature live in the envelope
}

candidate {               # signed by the executing coordinator = its MECHANICAL integration sign-off
  candidate_id, attempt_id, brief_id, brief_version, risk_tier_claimed, pair
  build_base_sha          # base the builder branched from
  branch_sha              # the builder commit (preliminary-attested)
  staging_base_sha        # main.head at staging — the CAS expected-old for promotion
  integration_sha         # the staged result (release-attested)
  policy_digest
  created_by              # coordinator seat
}
```

The merge-gate computes this predicate over **effective** state, atomically, holding the queue
slot:

```
mergeable(candidate) :=
  # freshness — exact-SHA CAS precondition
  candidate.staging_base_sha == main.head
  # assignment & independence (from the signed `assignment` fact for candidate.pair)
  AND assignment names builder, primary_verifier, executing_coordinator
  AND primary_verifier.provider != builder.provider
  AND candidate is signed by assignment.executing_coordinator          # mechanical integration sign-off
  # primary semantic verification (cross-provider operator), both phases, EFFECTIVE
  AND effective preliminary attestation: signer == assignment.primary_verifier
        AND verdict == GO AND subject_sha == candidate.branch_sha AND brief_version matches
  AND effective release attestation: signer == assignment.primary_verifier
        AND verdict == GO AND subject_sha == candidate.integration_sha AND brief_version matches
  # tier is GATE-COMPUTED, never trusted from the candidate
  AND effective_tier == max(brief.assigned_tier,
                            classify(diff(staging_base_sha, integration_sha), active_policy))
  AND co_sign_satisfied(effective_tier)                                # §7.2
  # strategic authorization, mechanically enforced
  AND effective cycle_go covers (brief_id, brief_version, effective_tier, policy_digest)
  # release key, bound to THIS candidate
  AND effective release_order: candidate_id == candidate.candidate_id
        AND subject_sha == candidate.integration_sha
  # scope, policy, evidence, version
  AND diff(staging_base_sha, integration_sha) ⊆ brief.allowed_paths
  AND candidate.policy_digest is currently-accepted (or explicitly grandfathered)
  AND ci_result signed by trusted CI, binding integration_sha AND policy_digest, == PASS
  AND candidate.brief_version == latest_non_superseded_version(brief_id)
  AND no effective candidate_aborted for candidate.candidate_id
  # every signature valid; every approval unique, authorized, effective, unrevoked
```

**Three outcomes** (a failed clause is not always a rejection):
- **PENDING** — valid so far, but an expected approval / co-sign / CI result has not arrived. The
  gate re-evaluates when any relevant `attestation`, `co_sign`, `release_order`, `ci_result`,
  `candidate_aborted`, or `brief_superseded` for this candidate arrives.
- **REJECTED** — bad/absent signature, wrong signer, revoked/superseded evidence, policy or CI
  failure, **tier_escalation** (§7.2), out-of-`allowed_paths` diff, or an invalid integration
  transform.
- **DEAD_LETTER** — malformed or permanently unprocessable event.

**`co_sign_satisfied(tier)`** (signatures distinguished by `signer`, incl. session):
- **T0/T1:** the primary operator's release attestation + the executing coordinator's `candidate`
  signature. No additional artifact.
- **T2:** the above **plus** a semantic `co_sign` (GO over `integration_sha`) from the **other
  pair's operator** — a real semantic verifier of the other provider, not the mechanical
  coordinator.
- **T3:** T2 **plus** a fresh `re_verify` attestation from a *new-session* cross-provider operator
  (distinct `signer` session) **plus** two distinct `human_approval` facts.

**Trigger flow.** The operator emits the release `attestation`; the executing coordinator observes
it and emits `release_requested`; the overseer emits `release_order`. The gate acts when both
triggers exist and re-evaluates the whole predicate from authoritative bus state. If `main.head`
moves first, the candidate is stale → re-stage as a **new** candidate.

### 6.4 Exact-SHA promotion and gate isolation

The strongest invariant — *the attested `integration_sha` is exactly what reaches `main`* — is
enforced mechanically:

- The final write is an **expected-old-OID compare-and-swap**: update `main` from
  `expected_old == candidate.staging_base_sha` to a result whose tree equals the *trusted* merge.
  A hosting-platform "merge" that mints a fresh commit is **not** allowed (it changes the SHA).
- **v1 strategy = merge-only** (deterministic): first parent `staging_base_sha`, second parent
  `branch_sha`, resulting tree == the trusted merge calculation; any textual conflict → `ABORT`.
  Rebase is deferred (needs a patch-equivalence proof).
- The merge-gate process holding the `main` credential **never executes candidate code**. It reads
  `ci_result` facts produced by an **unprivileged** runner; CI policy and workflow come from a
  **protected gate image**, never candidate-controlled workflow files.

## 7. Decision protocols

### 7.1 Dual-chief protocol
One chief **proposes** the cycle's orders; the other **critiques**. Low-risk: either chief's
order suffices (other informed). High-risk (T2/T3): **both** chiefs must agree before the
overseer issues `cycle_go`. Unresolved disagreement → **escalate to the human**; no auto-merge on
chief deadlock.

### 7.2 Risk tiers, gate-computed assignment, and co-sign

**Assignment.** A brief carries a *claimed* `risk_tier`, but the **merge-gate computes the
effective tier itself** and never trusts the claim:

```
effective_tier = max( brief.assigned_tier,
                      classify(diff(staging_base_sha, integration_sha), active_policy) )
```

| Content touched | Minimum tier |
|---|---|
| docs / comments only | T0 |
| bounded code change, tests | T1 |
| auth, concurrency, schema/migration, dependency lockfile, lock-touching, CI/policy config | **T2** |
| production data, security controls, release signing, infra deletion | **T3** |

**Tier-escalation rule.** If `effective_tier` exceeds the tier the effective `cycle_go`
authorized, the gate rejects with `tier_escalation`. The overseer must then issue a **new
brief_version** and obtain the required chief (and, for T3, human) approvals — merely raising a
candidate field is insufficient, because the high-risk chief approval would never have happened.

**Co-sign matrix** (the executing coordinator's `candidate` signature is a *mechanical
integration* agreement, not a semantic review; semantic agreement always comes from operators):

| Effective tier | Semantic verification | Integration | Chief (via `cycle_go`) | Human |
|---|---|---|---|---|
| T0/T1 | primary cross-provider operator (preliminary + release GO) | executing coordinator candidate sig | either chief | no |
| T2 | + **other pair's operator** `co_sign` (GO over `integration_sha`) | same | both chiefs | conditional |
| T3 | + fresh **new-session** cross-provider operator `re_verify` | same | both chiefs | **two distinct approvals** |

*Independence (ratified choice A).* The primary verifier and the executing coordinator are always
cross-provider to the builder. The T2/T3 *second* semantic opinion is the other pair's operator —
which, for a given change, may be the builder's provider; that is the deliberate
**both-model-families-must-agree** reinforcement, never a sole or primary approval.

### 7.3 Relationship to the repo's existing Rule #23
§7.2 (risk tier) governs **how many signatures** a promotion needs. The repo's **Rule #23 Tier
A/B** governs **co-sign scope** (does a co-signer's verification change which files the
implementation touches → Tier A pre-dispatch, else Tier B awareness). They compose; neither
replaces the other.

## 8. The git-native bus (hardened, sequenced, event-sourced)

Verified current state (`coordination/`): a single append-only `mailbox/sent/` log of
timestamp-named markdown events with filename routing; per-seat `mailbox/seen/<seat>.txt` scalar
cursors; `coordinator` is a *send-only* pseudo-seat; `send-event` validates kinds and guards
same-second collisions; seats are `director, director2, operator, operator2`.

**Concrete v1 topology** (one design, not "refs or a repo"):

1. **One protected, append-only event ref** (e.g. `refs/threeway/events`). **One atomic git
   commit per event**, containing *both* the event file (`events/<brief-id>/<uuid>.json`) and its
   index entry (`index/<seq>` → `{uuid, path, object_digest}`).
2. **Append via expected-old-OID CAS push**: the writer pushes with the prior ref tip as the
   expected old value; Git rejects a non-fast-forward. On rejection the writer re-fetches,
   allocates the next `seq`, **re-signs** (`seq` is in the signed bytes), and retries with
   backoff. `send-event` wraps this loop. There is no separate sequencer process — Git's ref
   update *is* the CAS.
3. **Per-seat cursor refs** (`refs/threeway/cursors/<seat>`), writable only by that seat via
   **ref-level** permission (path-level "only you may write `seen/<seat>`" is unenforceable when
   every seat writes one shared branch). A cursor means **"last `seq` scanned,"** not "last
   side-effect completed"; durable `event_acknowledged` facts + idempotent handlers cover a crash
   between performing an action and advancing the cursor.
4. **Inbox projections are generated locally** from the index and **never committed as authority**.
   A derived inbox is *not* confidentiality (a seat that can read the event ref sees everything).
5. **Append-only & immutability** are enforced by ref protection on the event ref + mandatory
   signatures (§6.2); bus traffic stays on bus refs so it never touches code commit history.
6. **Versioned seat→provider mapping.** Which provider occupies which seat is a **signed,
   versioned `assignment` fact** on the bus — not a mutable config file — so historical
   validation (who verified what, with which provider) is reproducible.
7. **New addressable seats.** `coordinator`/`coordinator2` become first-class receiving seats; the
   four files to keep in sync are `send-event`, `consume-events`, `check_coordination.py`,
   `scripts/status.py`.
8. **Migration.** `events/`+`index/` coexist with legacy `mailbox/sent/` (shadow), which becomes a
   read-only projection then retires; cursors migrate from ISO-timestamp to scalar `seq` with a
   one-time backfill. No dual-write authority at any point.

## 9. Failure & recovery state machine

State is the reduction of append-only facts (§6.1); a transition *emits a fact*, never mutates one.

| State | Owner | Trigger (effective fact) | Fact emitted | Next state(s) | Bound |
|---|---|---|---|---|---|
| BUILD | director | brief distributed / `rework` | `candidate` (on submit) | PRELIM_VERIFY | — |
| PRELIM_VERIFY | operator | branch submitted | `attestation(preliminary)` | STAGING (GO) \| REWORK (FAIL) | verify window |
| STAGING | coordinator | preliminary GO | `candidate` (staged) | AWAITING_RELEASE_ATTN \| ABORT | — |
| AWAITING_RELEASE_ATTN | operator | staged candidate | `attestation(release)` | RELEASE_REQUESTED (GO) \| REWORK (FAIL) | attest window |
| RELEASE_REQUESTED | coordinator | release GO observed | `release_requested` | GATE_PENDING | — |
| GATE_PENDING | merge-gate | `release_requested` + `release_order` | — (re-eval on relevant facts) | RELEASE \| GATE_PENDING \| REJECTED | co-sign/CI window → ESCALATE |
| RELEASE | merge-gate | predicate PASS, holding slot | exact-SHA CAS write | COMPLETED \| REJECTED (stale base) | atomic |
| REWORK | director | FAIL / `candidate_aborted` / `brief_superseded` | `rework` | BUILD (new candidate_id) | **≤2 per brief_version → ESCALATE** |
| ABORT | coordinator | non-clean merge | `candidate_aborted` | REWORK | — |
| REJECTED | merge-gate | bad sig / tier_escalation / policy / CI / out-of-scope | `event_rejected` | REWORK \| (tier_escalation) new brief_version | by reason |
| ESCALATE | overseer | chief/co-sign deadlock or timeout | `event_timed_out` / `dead_letter` | human | — |
| POST_MERGE_REGRESSION | overseer | regression after a write | incident | revert/forward-fix → fresh verify | — |

`GATE_PENDING` distinguishes "still waiting for an expected approval" (re-evaluate later) from
`REJECTED` (a hard failure). A re-stage mints a **new** `candidate_id`. The **≤2 rework cap per
brief_version** is the circuit-breaker. **Ownership is per-lane:** the owner is the seat of the
pair whose candidate triggered the state.

## 10. What we borrow from the kit (ideas, not infrastructure)

Verification bound to exact revision + mandatory post-integration gates (#11/#13) → §6.3/§6.4.
Content-addressed immutable evidence → signed uuid facts + attestation/evidence digests (§6).
Effectively-once via reserve/execute/finalize → mechanical merge-gate holding the queue slot +
idempotency keys. Fencing intuition → attestation-binds-to-SHA + `staging_base_sha == main.head`
CAS + brief-version checks, instead of DB fencing tokens (v1).

## 11. First slice and phasing (with gate criteria)

- **Slice 1 — one pair, real bus, real gate.** Codex director + Claude operator on one brief;
  preliminary + **release** attestation bound to `integration_sha`; a coordinator stages and signs
  the candidate; the mechanical merge-gate performs an exact-SHA CAS write to a **protected test
  branch** under the predicate; the overseer issues one `release_order` and one cycle ledger.
  **Gate (security-first) — the predicate must reject each of:** a tampered `integration_sha`; a
  missing/forged `from` or **invalid/absent signature**; a valid signature from the **wrong seat
  or provider**; an **old `GO` later revoked / followed by `FAIL`** (no effective GO); a candidate
  that **weakened its own CI policy** or **modified its own CI workflow**; a **stage ref moved
  after** the release attestation; a **risk tier mislabeled** below the path-derived minimum and a
  **tier-escalation without a new `cycle_go`**; a **diff outside `allowed_paths`**; a **replay** of
  a valid event from a test bus (`bus_id` mismatch); and a **crash after the release claim but
  before the `main` CAS** that recovers without a double-write. A clean change merges; one REWORK
  cycle completes and the ≤2 cap escalates on the third.
- **Slice 2 — the mirror + bus hardening.** Add Pair B; both routed coordinators; event-sourced
  `events/`+`index/` + per-seat cursor refs; the append CAS loop.
  **Gate:** two pairs run concurrently with **no lost/duplicated event under a 2-process race**;
  abort-on-conflict → rework; the serial merge queue re-stages the loser when `main` advances.
- **Slice 3 — strategic loop.** Dual chief (apps, human-relayed) + overseer distribution + tiered
  co-sign + `cycle_go`/`release_order` + the T2 other-pair-operator co_sign.
  **Gate:** a full cycle with **a T2 change lacking the other-pair operator `co_sign` rejected**,
  and a **gate-computed tier escalation** correctly blocked until a new `cycle_go`.

Each slice passes its own gate before the next is planned.

## 12. Field-level schemas / mechanisms for the implementation plan

The design above is normative. These are the field-level details the plan defines:
- **Public-key signing scheme + key management** — per-seat keypairs, canonicalization = JCS, keys
  stored isolated from any candidate-executing environment (§6.2/§6.4). Mandatory, not optional.
- **Signed evidence manifest** (referenced by `evidence_manifest_digest`):
  `{artifact_location, retention, subject_sha, policy_digest, check_ids[], artifact_digest}` — so
  CI/test evidence is retrievable and bound, not a bare hash.
- **Trusted CI image / policy source** for `required_CI(tier)` — start from `scripts/ci_smoke.py` +
  wave gates; policy/workflow served from the protected gate image (§6.4), never candidate files.
- **Brief record + `latest_non_superseded_version`**: a signed `brief` fact
  `{brief_id, brief_version, risk_tier, allowed_paths, acceptance_criteria, required_checks}`;
  supersession is a `brief_superseded` fact. The kit's brief schema (manual §11.1) is the start.
- **Human-approval record (T3)**: a signed `human_approval` fact
  `{approver_identity, candidate_id, integration_sha, decision}`; identity/auth mechanism → plan.
- **Chief-relay provenance**: each relayed chief result records `{relaying_human,
  chief_model_label, prompt_or_bundle_digest, response_digest, normalization}` for auditability.
- **Competing / compare-select mode** for high-stakes briefs (D3 reserves it; not v1).
- **Per-seat delivery confidentiality** (separate delivery refs/repos) — only if ever required.

## 13. Risks
- Cross-provider operational surface doubles (each provider runs as both builder and verifier) —
  mitigated by phasing (Slice 1 = one pair).
- Mechanical merge-only strictness (abort-on-conflict) increases rework on entangled changes —
  accepted; complementary briefs (D3) reduce cross-pair conflict.
- Strategic-loop latency (human-relayed chiefs) — accepted as a per-cycle human checkpoint.
- The append CAS on one event ref is a single serialization point — acceptable at current volume;
  revisit (causal model + per-producer high-water marks) if multi-host write concurrency grows.
