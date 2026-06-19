# HANDOFF — Cross-Provider Seat Topology, Slice 1: EXECUTED · MERGED · PUSHED (2026-06-19)

**Read first if you are picking up the cross-provider seat-topology work.** Companion
docs: spec `docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md`
(rev 5, `ffaa50eb`); plan `docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice1.md`
(`e3899da1`); ADR-030 in `DECISIONS.md`.

## TL;DR

Slice 1 of the cross-provider seat topology is **built, reviewed, merged to `main`, and
pushed to `origin`**. The spec §11 Slice 1 gate is **MET**. Slice 2 is now unblocked per
the §11 boundary rule. There are **3 carried hardening findings** (all fail-closed) to fold
into the Slice 2 plan, plus one spec-enum reconciliation note.

## What shipped

- **21 commits** (`d0797d55^..622cf392` — i.e. `d0797d55` through `622cf392` inclusive), executed via `superpowers:subagent-driven-development`
  in an isolated worktree (`.worktrees/threeway-slice1`, now removed) — one commit per plan
  task, each through a fresh **opus** implementer + two-stage review (spec compliance →
  code quality), capped by a whole-package final review.
- **Merged to `main`** via fast-forward (no merge commit; linear per-task ledger preserved).
- **Pushed:** `origin/main == 622cf392` (verified `git rev-parse origin/main` == local HEAD;
  `git rev-list --count origin/main..HEAD` == 0).
- Additive only: 32 files / +2,323 lines; the sole edits to existing files are a
  `DECISIONS.md` append (ADR-030) and one line in `requirements.txt` (`rfc8785>=0.1.4`).
  The legacy markdown bus (`coordination/mailbox/`), `scripts/`, `cinema/`, `web_server.py`,
  `cinema_pipeline.py` are **untouched**.

## Verification evidence (first-hand, on merged `main`)

- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q` →
  **`93 passed`**.
- `.venv/bin/python scripts/ci_smoke.py` → **`no ceremony detected … OK`** (the single R2 WARN
  is a pre-existing `importorskip('cv2')` in `test_lane_silent_gate_siblings_xfail.py:64` —
  unrelated to `threeway/`, not a hard gate).
- Spec §11 Slice 1 Definition-of-Done: every one of the 11 adversarial cases (+ clean-merge,
  + ≤2-rework breaker) maps to a passing test in `tests/unit/test_threeway_gate_adversarial.py`,
  **proven non-vacuous by mutation** (drop a clause's reason substring → its test fails).

## The package (what's where)

| Module | Responsibility |
|---|---|
| `threeway/canon.py` | RFC 8785 (JCS) canonicalization — the single signed-bytes chokepoint. |
| `threeway/keys.py` | Per-seat Ed25519; committed `.pub` trust root; off-repo keystore (`THREEWAY_KEYSTORE`). |
| `threeway/envelope.py` | `Event` + the fixed 12-field `_signed_view`; `payload_digest`, `idempotency_key`, sign/verify, JSON serde. |
| `threeway/store.py` | Append-only signed-JSON store; single-writer `seq` (Slice 1). Raw reader — no sig verify. |
| `threeway/reducer.py` | `reduce(events) → EffectiveState` (§6.1 revocation / latest-verdict / abort / supersession). |
| `threeway/policy.py` | Path→tier rules + `policy_digest` (binds the rule table). |
| `threeway/tier.py` | `classify_diff` / `effective_tier` (gate-computed, claim only raises) / `co_sign_satisfied` (T2/T3 → False). |
| `threeway/gitcas.py` | Object-store-only git plumbing (merge-tree/commit-tree/update-ref); never checks out, never runs candidate code. |
| `threeway/predicate.py` | `evaluate(...) → Decision` (§6.3): MERGEABLE / PENDING / REJECTED. |
| `threeway/gate.py` | `verify_and_reduce` (sig/bus_id/seat trust boundary) + `run_gate` (recompute + exact-SHA CAS + idempotent merge_completed). |
| `threeway/loop.py` | `build_candidate_events` — the signed T1 promotion the gate tests reuse. |
| `threeway/keys_bootstrap.py` | CLI: generate per-seat keypairs → registry + keystore. |
| `threeway/rework.py` | ≤2-rework circuit-breaker (§9). |

## Security properties confirmed under adversarial review

1. **Single canonicalization chokepoint** (RFC 8785) → byte-identical signatures across providers.
2. **§11 wrong-seat defense** — authority checked by *seat*, not signature-validity-alone; a
   validly-signed `release_order`/`ci_result` from the wrong seat is REJECTED. Pinned by
   `test_rejects_valid_signature_wrong_seat`.
3. **Non-bypassable trust boundary** — a meta-test (`test_every_reducer_consumed_kind_is_load_bearing`)
   asserts `reducer-consumed-kinds ⊆ LOAD_BEARING_KINDS` via the reducer's AST, so a future
   reducer branch that forgets to mark a kind load-bearing fails CI instead of silently opening
   an unsigned-injection bypass.
4. **Recompute-not-trust + exact-SHA CAS** — the gate recomputes the merge (never trusts the
   candidate's `integration_sha`) and CAS-writes the protected test ref; at-most-once is doubly
   guaranteed (idempotency no-op + CAS expected-old). Never executes candidate code.

## ⚠ Carried hardening findings — FOLD INTO THE SLICE 2 PLAN

All three are **fail-closed** (none can promote a bad change; worst case is a crash or an
over-strict reject). They were left out of Slice 1 deliberately (two touch security
*semantics*/spec) and surfaced by adversarial review.

1. **`_within_allowed` slash-less-prefix false-accept** — `threeway/predicate.py:154`
   (`path.startswith(a)`), def at `:150`, caller at `:127`. `allowed=["cinema"]` (no trailing
   `/`) accepts `cinemax/y`. Not currently exploitable (Slice-1 builders emit `"cinema/"`), but a
   scope-bypass vector. **Fix:** require a path-boundary match (prefix `endswith("/")` or exact
   equality). NOTE: do **not** apply the same change to `threeway/tier._path_tier` — there the
   generous `startswith` is the *safe* (over-classify) direction; this is a Rule-#13
   "siblings audited, fix differs per module" case.
2. **Uncaught `subprocess.CalledProcessError` on a non-existent attested SHA** —
   `threeway/predicate.py:94` (`repo.changed_paths(staging_base, integ)`) and the gate's
   merge recompute. A candidate attesting a well-formed-but-nonexistent `integration_sha` makes
   `git diff` exit 128 → the exception escapes `run_gate` instead of a clean REJECTED. Fails
   closed (ref never moves) but violates the `run_gate → GateResult` contract. **Fix:**
   `rev_parse`-guard `base`/`integ` (or catch in `gitcas`) and map to REJECTED.
3. **`attestation.brief_version` not in the signed set** — `threeway/envelope.py:68`
   (`_signed_view`); `brief_version` is intentionally excluded (documented at `envelope.py:63-66`).
   Spec §6.3 wants attestations "bound to brief+version"; the impl binds via `subject_sha` only.
   **Action:** reconcile spec §6.3 vs. code in Slice 2/3 (either sign `brief_version` or amend the
   spec to state SHA-binding is sufficient).

**Spec-enum reconciliation (not a defect):** the `merge_completed` kind is a plan extension
(`threeway/__init__.py:21-23` documents it as "architecturally required but not yet in the spec
§6.2 kind enum"). Add it to spec §6.2 when Slice 2 touches the event vocabulary.

## Open deployment question (deferred from Slice 1, §6.4)

**Where the CI / private keys live for a non-test run.** All 17 gate tests use ephemeral
generated keys, so nothing is blocked today. But a real (non-test) demo needs the keystore
provisioned outside the repo, and the trusted `ci` signer key must live where CI can sign but
candidate code cannot read it. This is a deployment detail, not code — resolve before any
non-test run. `threeway/keys_bootstrap.py` is the provisioning CLI.

## Process notes for the next session

- **Worktree pattern:** Slice 1 ran in `.worktrees/threeway-slice1` (gitignored via `6982be73`);
  the worktree `.venv` was a symlink to the main checkout's venv. Worktree + branch are now
  removed. Re-create a fresh worktree for Slice 2.
- **Subagent model = OPUS** for this work (user directive 2026-06-19), overriding the standing
  `[[feedback_sonnet_for_subagents]]` default. Scoped to this work unless the user says otherwise.
- **Test command is mandatory-prefixed:** `env -u GIT_INDEX_FILE .venv/bin/python -m pytest … -q`
  (a leaked `GIT_INDEX_FILE` breaks any test that shells out to git in a temp repo). Temp-repo
  tests pop `GIT_INDEX_FILE` in their `_env()` helper.
- **Design requirement caught during execution (carry into Slice 2):** the coordinator (which
  stages `integration_sha`) and the gate (which recomputes it for the exact-SHA equality check)
  MUST use an identical deterministic merge-commit construction — same tree, same parents,
  **same commit message** (`f"threeway merge {candidate_id}"`), same `_DET_ENV`. The plan's draft
  test fixtures staged with a different message and would have spuriously rejected; this is now
  baked into the committed tests.
- **Two plan bugs were caught + fixed pre-flight:** (a) the gate e2e fixtures' staging-message
  mismatch (above); (b) Task 10's prose said "6 passed" but the verbatim test code defined 5 tests
  (a prose miscount, not a code gap). The plan doc still carries these prose artifacts — harmless,
  but note them if re-reading the plan.

## Next: Slice 2 (planned only now that Slice 1's gate is green — spec §11 boundary rule)

Scope (do NOT start without a written plan): **Pair B (the mirror)** + both routed coordinators;
the hardened `refs/threeway/events` ref topology (one commit per event + `index/<seq>` +
expected-old-OID append-CAS push loop) replacing the single-writer file store; per-seat cursor
refs; the multi-process race gate. **Fold the 3 carried findings above into that plan.** Slice 3
(strategic loop: dual chief, overseer brief distribution, T2 other-pair `co_sign`, T3 `re_verify`
+ two `human_approval`) follows Slice 2's gate.

---
*Session: user-principal main session executed the Slice 1 plan end-to-end. All claims above
verified first-hand on `origin/main` at `622cf392`.*
