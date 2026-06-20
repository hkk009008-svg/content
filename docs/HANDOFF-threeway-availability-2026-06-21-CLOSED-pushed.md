# HANDOFF — Threeway insider availability/DoS class CLOSED + certified (ADR-039/040/041)

**Date:** 2026-06-21
**Merged + pushed:** `origin/main` @ `16b0a5e9` — 11 commits `3f7c6a6b..16b0a5e9`, clean fast-forward off the Slice-3 forgery-hardened tip `4070222d`. Built **directly on `main`** (no feature branch / worktree for this slice), so "merge" = already on `main` + `origin/main`; `main == origin/main == 16b0a5e9`.
**Verification at handoff:** `tests/unit/test_threeway_*.py` → **307 passed, 1 xfailed**; `scripts/ci_smoke.py` → OK ("no ceremony detected"); `scripts/check_no_ceremony.py` → clean; tree clean (only a pre-existing, unrelated `.claude/settings.json` toggle, untouched).

> Trust git, not this prose. On resume: `git fetch && git log -1 && git rev-list --count origin/main..HEAD`. The numbers above were true at `16b0a5e9`.

---

## 1. What this session did

Started from "continue task" with the forgery class closed (ADR-036/037/038) and the **availability/DoS slice scoped** (`docs/superpowers/plans/2026-06-21-threeway-control-plane-availability-hardening.md`). Executed that plan via `superpowers:subagent-driven-development` (Opus implementers; per-task spec + code-quality review; mutation-proofs), then ran the plan's mandated **whole-implementation adversarial review** as a multi-agent Workflow (`wf_30e51cdf-f6b`) plus a chain of fresh-eyes certifications.

**The insider availability/DoS class is now CLOSED + CERTIFIED.** The forgery/integrity class (ADR-036/037/038) was re-confirmed CLOSED at every step — every non-fail-safe outcome the reviews found was availability-only, never a forged promotion.

The adversarial loop earned its keep: it surfaced a chain of **six successive layers of the same root** — *`run_gate` step 1 (`verify_and_reduce`→`reduce`, which runs OUTSIDE `run_gate`'s try) dereferences insider-controlled fields as set/dict/sort keys or via attribute access, so one malformed-but-validly-signed (or at-rest-planted) event raises uncaught → a single-insider TOTAL-BUS brick.* Per-field drop-not-raise patches kept revealing the next field; the whack-a-mole ended only with a comprehensive structural guard at the first dereference.

## 2. The three ADRs

| ADR | Closed | Note |
|---|---|---|
| **039** | Authority-aware reducer (record-time filter on the 6 static singletons); `authoritative_candidate` **self-consistency** (signed by the executing_coordinator of the overseer assignment for the pair THAT candidate declares — used by predicate AND `run_gate`); `run_gate` post-CAS totality + reserved-`merge-` namespace DROP + main-state idempotency | **DEVIATED** from the plan's literal design 2(a) ("read pair from the latest candidate") — it had a pair-redirection DoS + a `run_gate` forgery hazard |
| **040** | Verify-phase totality: the four explicit `raise`s (bus_id / sig_version / unknown-seat / invalid-sig) → DROP+WARNING; pre-CAS `except Exception → REJECTED`; removed the now-subsumed ADR-038 step-2b | **DEVIATED** from the plan's "raise at ingestion" — raising bricks the WHOLE bus |
| **041** | `run_gate` **step 1** totality: a comprehensive `well_formed(ev)` envelope-structural guard (`threeway/envelope.py`) at BOTH `verify_and_reduce` + `reduce()` ingestion, + `reduce()`'s fold `try/except` (payload-value keys) + `authoritative_candidate`'s `isinstance(pair,str)` skip | Consolidated the scattered per-field guards into one structural check |

**The 11 commits:** `3f7c6a6b` (ADR-039 static-singleton filter), `fea57c6b` (ADR-039 authoritative_candidate + gate_seat threading), `f8003b3b` (ADR-039 run_gate post-CAS totality + reserved-namespace drop), `4d058a1d` (ADR-039 docs), `1f3e65a4` (ADR-040 verify-phase drop + pre-CAS guard), `c88c41b9` (ADR-040 docs + residual filed), `eb0b1000` (ADR-041 reduce() totality), `584e9f8c` (ADR-041 authoritative_candidate pair), `600e50e6` (ADR-041 verify-phase id/signer/sig_version), `be9c04f0` (ADR-041 comprehensive well_formed), `16b0a5e9` (ADR-041 docs).

## 3. NEXT (primary) — close the one tracked residual

**`threeway-candidate-id-pair-binding-dos`** (MAJOR, **open**, strict-xfail `tests/unit/test_threeway_gate.py::test_cross_pair_candidate_id_reuse_dos_residual`): a legitimate executing_coordinator of ANOTHER overseer-assigned pair can reuse a victim's `candidate_id`, declare its own pair at a higher seq, capture `authoritative_candidate`, and stall the victim's merge at a non-merge outcome. **Availability-only — it NEVER promotes** (the attacker cannot forge the other pair's verifier attestations). Root: `candidate_id` is not bound to a single `(pair, executing_coordinator)`. **Fix direction:** pair-namespaced candidate ids, OR first-writer-wins on the `(candidate_id, seat)` slot. When the binding fix lands, the strict-xfail flips RED → remove the pin. Scope it as its own small slice (subagent-driven, Opus) the same way this one ran.

## 4. Still deferred (unchanged — pre-existing scope)

- **Slice-3 scope (b) — the strategic loop:** dual-chief apps (human-relayed) + LIVE emission of `co_sign`/`re_verify`/`human_approval`; closes `threeway-signer-unsigned-session` + `threeway-human-approval-overseer-asserted`.
- **The LIVE cutover (operational):** Slice 2.5 shipped the tested machinery (`threeway/cutover.py`); the authority-flip onto `refs/threeway/events` was NOT run; the live `coordination/` bus is still on ISO cursors.

## 5. Sharp edges / lessons (durable)

- **Drop-not-raise.** A malformed/unauthenticated event has NO authority → DROP (ignore) it. RAISING in a shared read path (`verify_and_reduce`/`reduce`, outside `run_gate`'s try) bricks EVERY candidate — a self-inflicted DoS, not fail-closed. This is the unifying principle across ADR-040/041.
- **Guard at the FIRST dereference, structurally — not per-field.** The type-safety belongs where a field is first touched (the gate's ingestion + `reduce()`'s up-front filter), as ONE comprehensive `well_formed(ev)` check, not as N narrow guards. Per-field patches invited the next layer (Rule #13: when you guard field X, audit ALL sibling dereferences).
- **Adversarially re-verify your own fix, end-to-end through the REAL gate** (live Ed25519). Every one of the six layers was found by re-running attacks, not paper review. **Monotonically-decaying severity** across rounds (CRITICAL→MAJOR, graceful/no-forgery) + an **exhaustive certification catalogue** (the closing pass ran 35 envelope-field + 15 payload-value poisons, all fail-closed) is the CONVERGENCE / closure signal.
- **`signer` is UNSIGNED** (excluded from the 14-field signed view, `envelope.py:67`) — an insider can set it to any value with a valid signature; structural guards on it must not assume a string. `from_json_obj` does NO at-rest type validation, and `reduce()` is a public function callable directly with no sig check — so `well_formed` is load-bearing at both `verify_and_reduce` AND `reduce()`.
- Built directly on `main`; shared seat index → tests with `env -u GIT_INDEX_FILE`, commits with explicit pathspec, `git show --stat HEAD` after each. No peer commit interleaved (reflog-verified at each amend).

## 6. Where the truth lives

`DECISIONS.md` ADR-039 / ADR-040 / ADR-041 (full rationale, the two deviations, evidence). `ARCHITECTURE.md` §13A.7 (availability hardening — authority-aware reducer + `well_formed` + run_gate totality). `docs/REMEDIATION-INVENTORY.md` rows: `threeway-reducer-shadow-dos` / `threeway-merge-completed-no-seat-check` / `threeway-run-gate-not-total` / `threeway-reserved-merge-id-dos` / `threeway-verify-phase-brick-dos` / `threeway-step1-not-total-malformed-input` all **fixed**; `threeway-candidate-id-pair-binding-dos` **open** (xfail-pinned). Memory: `project-cross-provider-topology-design`.
