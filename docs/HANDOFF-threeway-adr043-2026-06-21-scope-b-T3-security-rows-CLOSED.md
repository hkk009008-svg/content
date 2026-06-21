# HANDOFF — Threeway scope-(b) T3 SECURITY rows CLOSED (ADR-043), PUSHED

**Date:** 2026-06-21
**Merged + pushed:** `origin/main` @ `bd31fbe1` — 2 commits (`d67aa146` fix + `bd31fbe1` this handoff),
built directly on `main` (consistent with the prior threeway slices), clean fast-forward
`01b282c1..bd31fbe1`. `main == origin/main == bd31fbe1`, 0 unpushed. The live cutover was deliberately
NOT taken (the recommendation was to land the defect-closure and STOP before the irreversible flip).
**Verification at handoff:** `tests/unit/test_threeway_*.py` → **321 passed**; `scripts/ci_smoke.py` OK;
`scripts/check_no_ceremony.py` clean; tree clean except a pre-existing, unrelated `.claude/settings.json`
toggle (excluded from the commit).

> Trust git, not this prose. On resume: `git fetch && git log -1 && git rev-list --count origin/main..HEAD`.

---

## 1. What this session did

Resumed from "continue task" with the threeway control plane CLOSED except the **two open scope-(b)
deferral rows** (the only `open` threeway inventory rows). Surfaced the fork (scope-b security core vs
the operational dual-chief layer vs the live cutover); user chose "proceed as recommendation" →
**closed the two SECURITY rows + the §5 loose thread, and stopped before the cutover.**

**Closed via ADR-043 (one commit `d67aa146`):**
- `threeway-signer-unsigned-session` (MAJOR) → **re_verify freshness challenge.** New overseer-signed
  `re_verify_challenge` kind carries an unguessable `nonce` bound to candidate+integration_sha;
  `tier._t3_cross_provider_re_verify` requires the re_verify's payload `challenge_nonce` (bound via the
  signed `payload_digest`) to equal it. A replayed stale re_verify carries an old nonce → fails the
  current challenge → freshness verifiable from signed facts.
- `threeway-human-approval-overseer-asserted` (MINOR) → **per-approver key-bound auth.** New
  overseer-signed `approver_roster` kind lists allowed approver SEATS; `reduce()` keys `_human_approval`
  by `(candidate_id, signer-seat)`; `tier._two_distinct_human_approvals` requires ≥2 distinct roster
  seats (was ≥2 overseer-relayed labels). A compromised overseer can't assert two humans for one
  keyholder (it lacks the chiefs' keys).
- §5 (ADR-042 loose thread) → `run_gate` rejects a non-str `candidate_id` ARGUMENT (caller-misuse
  totality).

**Result: ALL threeway inventory rows are now `fixed` — 0 open.** Both the forgery/integrity class
(ADR-036/037/038) and the insider availability/DoS class (ADR-039/040/041/042) AND the two scope-(b) T3
security rows (ADR-043) are closed.

## 2. Why it's safe (design)

No change to the 14-field signed view — both fixes place data in the PAYLOAD, already bound via the
signed `payload_digest`, so no breaking protocol change. Both new kinds fold **overseer-only at record
time** (ADR-039 authority filter) and are in `LOAD_BEARING_KINDS`. Both clauses only ADD fail-closed
requirements → the T3 path is strictly NARROWER; nothing newly promotes. `run_gate` stays TOTAL (the new
payload-value derefs live only in tier, inside run_gate's broad pre-CAS except, read via `.get()`+
`isinstance`, never as keys).

## 3. Verification / certification

- **Mutation-proofs (executed, reverted):** A = remove nonce check → reddens stale/missing-nonce pins;
  C = disable roster gate → reddens not-on-roster pin; D = disable challenge authority filter → reddens
  forged-nonoverseer-challenge pin. B revealed the per-approver fix is **defense-in-depth** (reducer
  per-seat keying collapses same-seat approvals even if the tier layer is mutated) — a single-layer
  mutation won't redden the same-seat test.
- **Adversarial re-cert `wf_d3c80806-ad9`** (5 Opus dims + verifiers, each driving the REAL signed gate):
  **0 confirmed bypasses, no_new_promotion=true, regression GREEN** across all dims. Findings (all
  addressed, none a bypass):
  - **MAJOR (fail-closed operational precondition):** chief approver seats now need their OWN registry
    keys (`coordination/threeway/keys/<chief>.pub`) or `verify_and_reduce` drops their approval as
    unknown-seat (ADR-040) → T3 stuck PENDING. Never widens; pure liveness. ADDRESSED: two real-gate
    tests (`test_run_gate_completes_full_t3_through_signed_gate` = COMPLETED with chiefs registered;
    `test_run_gate_t3_pending_when_chief_keys_unregistered` = the regression guard) + docs. **Chief-key
    provisioning is a scope-(b) cutover step.**
  - INFO: freshness rests on the overseer issuing fresh nonces (gate enforces the binding, not
    nonce-rotation discipline) — docstring corrected; fresh-nonce emission is a scope-(b) emitter job.
  - INFO: the roster admits any overseer-named seat — key-distinctness, not human-vs-machine (the correct
    irreducible trust floor; human-ness is overseer policy).

## 4. NEXT (threeway program — what remains, all deferred by the standing recommendation)

The control plane has **no remaining tracked defect.** The remaining work is OPERATIONALIZATION, to be
done as deliberate, separately-confirmed steps (the recommended sequence was driver → strategic-loop →
cutover, with the cutover gated on explicit confirmation):

- **Scope-(b) OPERATIONAL layer (NOT the security — that's now closed):** the dual-chief apps
  (Gemini/ChatGPT, human-relayed) + LIVE emission of `co_sign`/`re_verify`/`human_approval`, **the
  overseer nonce/roster EMITTER** (issues fresh `re_verify_challenge` nonces + the `approver_roster`),
  and **provisioning the chief-* registry keys** (required-for-liveness per the re-cert MAJOR).
- **The LIVE cutover (operational, reversible-only-with-effort):** Slice 2.5 shipped the tested machinery
  (`threeway/cutover.py` → `ready_to_flip=True`); the authority-flip onto `refs/threeway/events` was NOT
  run. **Hold for explicit confirmation.**
- **Wire the gate driver:** `run_gate` still has zero production callers.

## 5. Sharp edges / lessons (durable)

- **The per-approver fix is two-layer defense-in-depth** (reducer keys by seat + tier counts by seat) —
  so mutating ONE layer doesn't redden the same-seat test; pin each layer with an isolating mutation
  (here: the roster-membership gate) and add an explicit ORIGINAL-CVE pin (two overseer-relayed labels).
- **A signed-payload nonce is the cheap way to add a signed field** without touching the 14-field signed
  view — `payload_digest` already binds the whole payload, so a challenge-response nonce in the payload
  is cryptographically committed with zero protocol-version churn.
- **The unit suites (tier/predicate) reduce() WITHOUT signature verification** — they pin LOGIC but miss
  the registry/signature layer. The re-cert MAJOR was exactly that gap (chief keys must be in the
  registry). Always add at least one REAL-signed-gate test (`run_gate`/`verify_and_reduce` via the
  `seatkit` fixture) for a fix that changes WHO signs a load-bearing fact.
- Adding lines to `reducer.py` shifted the `authoritative_candidate` ARCHITECTURE.md anchor (127→132) —
  ci_smoke caught it; fixed same-line (not blanket `--fix`).
- Built directly on `main`, committed with explicit pathspec (`git add -- <paths>` then
  `git commit -m … -- <paths>`); `.claude/settings.json` excluded by listing paths.

## 6. Where the truth lives

`DECISIONS.md` ADR-043 (full rationale + the re-cert findings). `ARCHITECTURE.md` §13A.6 (T3 freshness +
per-approver auth now key-bound; operational precondition). `docs/REMEDIATION-INVENTORY.md` rows
`threeway-signer-unsigned-session` + `threeway-human-approval-overseer-asserted` → **fixed** (verifier
`wf_d3c80806-ad9`). Adversarial evidence: `wf_d3c80806-ad9`.
