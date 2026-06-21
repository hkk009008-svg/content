# HANDOFF — Threeway candidate_id↔pair-binding DoS CLOSED (ADR-042), pushed

**Date:** 2026-06-21
**Merged + pushed:** `origin/main` @ `e2181eba` — 1 commit, clean fast-forward `fba8e13d..e2181eba` off the availability-slice tip. Built **directly on `main`** (no feature branch/worktree), consistent with the prior threeway slices; `main == origin/main == e2181eba`.
**Verification at handoff:** `tests/unit/test_threeway_*.py` → **309 passed, 0 xfailed**; `scripts/ci_smoke.py` → OK ("no ceremony detected"); `scripts/check_no_ceremony.py` → clean; tree clean except a pre-existing, unrelated `.claude/settings.json` toggle (untouched, correctly excluded from the commit).

> Trust git, not this prose. On resume: `git fetch && git log -1 && git rev-list --count origin/main..HEAD`. The numbers above were true at `e2181eba`.

---

## 1. What this session did

Started from "continue task" with the insider availability/DoS class CLOSED (ADR-039/040/041) and **one tracked residual**: `threeway-candidate-id-pair-binding-dos` (MAJOR, strict-xfail). Closed it. **The whole threeway merge-gate control plane now has no remaining tracked defect** — both the forgery/integrity class (ADR-036/037/038) and the insider availability/DoS class (ADR-039/040/041/042) are closed + certified.

**The residual.** `candidate_id` was a free-form, globally-shared namespace, so TWO overseer-assigned pairs (A, B) could each be **self-consistent** for the SAME id (self-consistency = the candidate's signer-seat == the `executing_coordinator` the overseer assigned to the pair the candidate declares). A LEGITIMATE executing_coordinator of pair B could reuse a victim's `candidate_id`, declare pair B, capture `authoritative_candidate`, and stall the victim's pair-A merge. **Availability-only — never promotes** (it can never forge pair A's verifier attestations; integrity class unaffected).

**The arc (the load-bearing lesson).** The FIRST fix — **first-writer-wins** (bind the id to the pair of its EARLIEST self-consistent declaration via a `_candidate_first_seq` map; reasoning: `append()` reassigns `seq` monotonically before signing so an insider can't out-rank an existing declaration) — LOOKED correct: its strict-xfail flipped, a 2-way mutation matrix passed, 309 tests green. **The mandated adversarial re-verify Workflow (`wf_01844a2a-03a`, 5 Opus dims, real-gate repros) CONFIRMED it only INVERTED the race** — it closed attacker-declares-LATER but reopened attacker-declares-EARLIER (a legit pair-B coordinator declaring the victim's id FIRST wins the lowest `seq`, captures authority, stalls the victim). **An order-based tiebreak can NEVER close a shared-namespace collision — whoever controls the order wins.** This is a fresh instance of the standing META-LESSON: adversarially re-verify your OWN security fix end-to-end through the real gate; a fix that passes its own tests + mutation-proofs can still be wrong at the design level.

I surfaced the verified finding + the scope tradeoff (ship-partial vs complete-structural-fix) to the user-principal in prose; user chose the complete fix.

## 2. ADR-042 — the complete, order-INDEPENDENT fix

Pair-namespaced candidate ids `"<pair>:<local>"` (e.g. `"A:c1"`). In `threeway/reducer.py`:
- `_pair_namespace(cid)` = the prefix before the first `":"` ( `"A:c1"`→`"A"`; non-str/un-namespaced → `None` → no candidate is authoritative, fail-safe).
- `authoritative_candidate` adds an eligibility clause: a candidate is authoritative only if its DECLARED `payload["pair"]` equals the id's namespace (plus the existing self-consistency check). This binds a `candidate_id` to ONE pair as a **pure function of its own id** — a coordinator of any OTHER pair declares a non-matching pair and is ineligible, **regardless of declare order**. The `_candidate_first_seq` machinery is REMOVED; the `(seq, seat)` pick is now only a defensive deterministic tiebreak (≤1 eligible expected).
- `threeway/loop.py::build_candidate_events` auto-namespaces a bare local id by its pair.

**Why it closes the CLASS, not the instance.** The binding is a pure function of the victim's own id (its namespace prefix), which the attacker cannot change for the victim's id; neither declare order helps. `assignment()` is overseer-only (record-time filter), so an attacker cannot forge a pair-A assignment naming itself; declaring pair A while signing as another seat fails self-consistency. The clause only NARROWS eligibility (never widens what promotes), so the integrity class + ADR-039/040/041 stay green and `run_gate` stays TOTAL (the `isinstance(pair, str)` skip + the `_pair_namespace` None-guard).

## 3. Verification / certification

- Strict-xfail residual pin (`test_cross_pair_candidate_id_reuse_dos_residual`) replaced by **two positive tests pinning BOTH declare orders**: `test_cross_pair_namespace_blocks_reuse_attacker_declares_earlier` / `_later`.
- **Mutation-proof (executed):** dropping the `if pair != ns` clause reddens ONLY the attacker-EARLIER test (the later case is closed by seq-order alone — that diff is exactly WHY namespacing was needed).
- 309 passed/0 xfailed; ci_smoke OK; check_no_ceremony clean.
- **Re-certified by `wf_28567ca6-c41`** (4 Opus adversarial dims through the real gate: namespace-bypass both directions, namespace edge-cases, integrity, totality+regression) — **0 confirmed findings** (1 INFO, see §5).

## 4. NEXT (threeway program — unchanged, deferred by prior decision)

No remaining tracked control-plane defect. The two deferred items:
- **Slice-3 scope (b) — the strategic loop:** dual-chief apps (Gemini/ChatGPT, human-relayed) + LIVE emission of `co_sign`/`re_verify`/`human_approval`; closes the two filed deferrals `threeway-signer-unsigned-session` + `threeway-human-approval-overseer-asserted`.
- **The LIVE cutover (operational):** Slice 2.5 shipped the tested machinery (`threeway/cutover.py`, `run_cutover`→`ready_to_flip`); the authority-flip onto `refs/threeway/events` was NOT run — the live `coordination/` bus is still on ISO cursors.

## 5. Loose thread (INFO, deliberately NOT fixed — out of scope)

The re-cert surfaced one INFO: a **non-str `candidate_id` ARGUMENT** to `run_gate` raises (`merge_completed.get` on a non-hashable arg) — caller-misuse, NOT an insider bus event, and **pre-existing** (true before ADR-042). `run_gate` has no production callers yet (the driver isn't wired), so it's not a live risk. Folding a guard into this slice would be scope creep; worth a one-liner when the gate driver is wired in scope-(b)/cutover.

## 6. Sharp edges / lessons (durable)

- **An order-based tiebreak cannot close a shared-namespace collision.** first-writer-wins / latest-wins both just MOVE the race. The structural fix (bind the key to data the attacker can't control for the victim — here the id's own namespace prefix) is what closes it.
- **A security fix that passes its own tests + mutation-proofs can still be wrong at the design level.** Only the multi-agent real-gate adversarial review caught the inverted race. Re-verify your OWN fix.
- **Test-migration sharp edges (namespacing forced ALL legit ids to be pair-namespaced → 64 failures across 7 files):**
  - A SHADOW/poison contesting the victim keeps the VICTIM's namespaced id (`"A:c1"`) with its bogus declared pair UNCHANGED (so namespace≠pair makes it ineligible). Do NOT namespace a shadow to its OWN pair — that makes it a different id and silently destroys the contest.
  - The gate recomputes the merge commit message as `f"threeway merge {candidate_id}"` (`gate.py`), so any test that STAGES the integration commit must use the namespaced id in that message or it REJECTS on "recomputed merge != attested integration_sha". This bit both the `_seed_valid` path and the slice2 `_stage` helper.
  - `predicate`/`reducer` tests build candidates DIRECTLY (own `_e`/Event helpers); `gate`/`loop`/`adversarial`/`slice2` use `build_candidate_events` (auto-namespaced). Migrated the 5 mechanical files via parallel Opus subagents (independent files → safe to parallelize), the security-critical `test_threeway_gate.py` by hand.
- **`run_gate` has NO production callers** (the driver isn't wired) → the whole ADR-042 change has zero production blast radius. Confirmed by grep before relying on it.
- Built directly on `main`; committed with explicit pathspec (`git add -- <paths>` then `git commit -- <paths>`), `git show --stat HEAD` after, fetched + ancestor-checked before the push (clean fast-forward). The unrelated `.claude/settings.json` was excluded by listing paths explicitly.

## 7. Where the truth lives

`DECISIONS.md` ADR-042 (full rationale, the rejected first attempt, the deviation story, evidence). `ARCHITECTURE.md` §13A.7 (the candidate_id↔pair binding is now STRUCTURAL; + two refreshed reducer line anchors). `docs/REMEDIATION-INVENTORY.md` row `threeway-candidate-id-pair-binding-dos` → **fixed** (verifier `wf_28567ca6-c41`). Memory: `project-cross-provider-topology-design` (the ADR-042 section + the META-instance lesson). Adversarial evidence: workflows `wf_01844a2a-03a` (caught the partial-fix inverted race) and `wf_28567ca6-c41` (re-cert, 0 findings).
