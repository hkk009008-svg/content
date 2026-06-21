# HANDOFF — Threeway residual surfaces CLOSED + adoption suite UNIFIED to HEAD (pushed)

**Date:** 2026-06-21
**Pushed:** `origin/main` @ `caa914f6`, 0 unpushed. **7 commits this session** on `main`
(`73c285a2..caa914f6`, clean fast-forward). The `.claude/settings.json` `codex:false` toggle was
excluded from every commit (pre-existing local change, unrelated).
**Verification at handoff:** threeway suite **341 passed / 0 xfailed**; `ci_smoke` + `check_no_ceremony`
clean; all 4 fixes independently Lane-V GO; the doc refresh passed both review lenses.

> Trust git, not this prose. On resume: `git fetch && git log -1 && git rev-list --count origin/main..HEAD`.

---

## 0. TL;DR

Two threads, both complete + verified + pushed:

1. **Residual-surface hardening.** An adversarial audit of the three named-but-un-audited substrate
   surfaces (refstore remote CAS, backfill resumability, gitcas merge-tree determinism) + the cutover
   composition (`wf_48aefc7d-589`) found **4 confirmed MAJOR defects**, reproduced end-to-end against
   HEAD. All 4 fixed (TDD red→green, mutation-proven, ADR + inventory row each) and **independently
   Lane-V GO** in isolated worktrees (`wf_5906f5e7-9d5`). A dormant Rule-13 sibling the A-verifier
   surfaced was also closed.
2. **Doc unification.** All 6 `docs/protocol/threeway/` adoption manuals (Claude · Codex · Antigravity)
   refreshed to HEAD (ADR-034..049), driven by an exhaustive currency+consistency audit
   (`wf_a18c7acb`) and applied per-doc + two-lens reviewed (`wf_c10b6e65`).

## 1. What landed (the 7 commits)

| Commit | Thread | What |
|---|---|---|
| `fbeb241f` | fix | **A — refstore `_iter_local` TOTAL vs malformed blob [ADR-046]** — a single malformed event/index blob wedged every append + every `run_gate` (the `all_events()` materialize at `gate.py:168` is OUTSIDE `run_gate`'s try) → a one-event total-bus DoS. ADR-041's `well_formed` only guarded already-deserialized Events; the crash was upstream. Now drop-not-raise at the deserialization source. |
| `1aba208b` | fix | **B — atomic cursor-backfill manifest [ADR-047]** — non-atomic `man.write_text` + bare `json.loads` readers → a crash mid-write wedged the cutover's resume AND rollback. Now `_atomic_write_text` (tmp+`os.replace`) + a typed `CursorBackfillManifestError` on any corrupt manifest. |
| `ccf00e7e` | fix | **store-sibling totality (Rule-13 of ADR-046)** + flips A's inventory row to verified. Dormant `EventStore.iter_events` (Slice-1, zero live callers) had the same bare deserialization — closed before `run_gate` is ever wired to it. |
| `219111fa` | fix | **C — merge-tree determinism [ADR-048]** — `merge_tree` pinned no merge-algorithm config, so ambient `merge.renames`/`renameLimit`/`diff.algorithm` made two seats compute different `(tree, clean)` for identical inputs. Now pinned via highest-precedence `-c` flags. |
| `54144d98` | fix | **D — cutover force-rerun cursor over-advance [ADR-049]** — on a `force=True` re-run, step 4 re-read the (now-scalar) `seen/*.txt` as ISO → lexicographic `"2026-…" <= "3"` → over-advanced the cursor ref past unread events. Now sources the seq-map from the prior run's archived manifest + rejects non-ISO cursors. Also re-anchored ARCHITECTURE §13A.2. |
| `a590294e` | reconcile | B/C/D Lane-V GO → inventory rows `verified`; closed ADR-048's value-coverage nit; filed the 2 deferred critic gaps as open rows. |
| `caa914f6` | docs | **Adoption suite unified to HEAD (ADR-034..049)** — see §3. |

## 2. Verification artifacts (R-MEASURE — committed via `git add -f`)

- `logs/audit-wf_48aefc7d-589-threeway-residual-surfaces.json` — the residual-surface audit (13 candidates
  → 5 reproduced → 4 distinct defects; 8 refuted incl. 3 main-read candidates).
- `logs/verify-wf_5906f5e7-9d5-bcd-lane-v.json` — worktree-isolated Lane-V of B/C/D (all GO, every guard
  mutation EXECUTED RED + reverted, Rule-13 sweeps).
- `logs/audit-wf_a18c7acb-7a0-threeway-doc-unification.json` — the doc currency+consistency audit (40
  stale items + 18 cross-doc contradictions + verified activation facts).
- `logs/refresh-wf_c10b6e65-ace-doc-unification.json` — the per-doc refresh + two-lens review (conformance
  PASS 0 findings; unification-consistency PASS).
- (A was Lane-V GO via a main-tree agent earlier in the session; that verdict is summarized in ADR-046 +
  the inventory row.)

## 3. Doc unification — what changed (commit `caa914f6`)

All 6 manuals + ARCHITECTURE §13A.4 brought current; both review lenses PASS.
- **Stale build-status corrected everywhere:** Slice 2.5 substrate **BUILT + hardened** (ADR-044/045) but
  the cutover **NOT executed** (user-gated, ADR-045); Slice-3 tier machinery **BUILT + enforcing**
  (ADR-035) — `co_sign_satisfied` does **not** return False for T2/T3; keys **not provisioned** (hard
  blocker); package still **wired into nothing**.
- **`coordinator2`:** the "harness rejects it" claim corrected across CODEX/ONBOARDING — it now binds
  coordinator **mode** (compatibility alias; `codex_protocol_model.py:104,155-156`,
  `protocol_mailbox.py:17`); only the **live signed-bus integrator role** is target-state.
- **~12 drifted file:line anchors fixed** (`run_gate` 95→158, append `store.py:39`/`refstore.py:132`,
  predicate by-seat `:136` + ci_result `:152-161`, `cas_create_or_update_ref` `gitcas.py:185`,
  `preflight_bus_init` `:245`, ci_result fixture `loop.py:104-105`, `status.py:141`, rooted
  `seat_status.py` path); no-dual-write citation unified to "spec §8 item 8" + Slice-2.5 design D2:47;
  dead PR#19 fallback branch → on main.
- **ADR-036→049 folded in.** Seat→provider table verified **byte-identical across all 6 docs + matches
  `threeway/loop.py:43-52`**.
- **CODEX-ADOPTION §4** is now an accurate sequenced **activation runbook** with each step's real status.

## 4. Inventory status (threeway rows)

- ADR-046 (`threeway-refstore-iter-local-not-total`) → **verified** (Lane-V GO `fbeb241f`).
- `threeway-store-iter-not-total` → **fixed** (Rule-13 sibling; dormant, test-covered).
- ADR-047 (`threeway-cursor-backfill-manifest-nonatomic`) → **verified** (Lane-V GO `1aba208b`).
- ADR-048 (`threeway-merge-tree-nondeterministic-ambient-config`) → **verified** (Lane-V GO `219111fa`).
- ADR-049 (`threeway-cutover-rerun-scalar-cursor-overadvance`) → **verified** (Lane-V GO `54144d98`).
- **2 NEW open rows (DEFERRED, dormant — cutover not executed):**
  `threeway-cutover-total-order-congruence` and `threeway-cutover-seen-filename-seat-key`. Both
  completeness-critic-flagged + confirmed-present-by-inspection but **NOT reproduced E2E**; queued for the
  next residual-audit round. NOT fixed (scope-bound). Fix directions recorded in the rows.
- All prior threeway rows remain `fixed`/`verified` (ADR-036..045).

## 5. NEXT — all user/external-gated (nothing owed in-lane)

- **Activation of the signed bus is user-gated + irreversible** — the runbook documents it; execution is
  your call: (1) provision keys (the hard blocker; T3-classified commit of the `.pub` registry),
  (2) run the cutover (`threeway/cutover.py run_cutover`; ~50-min O(n²) append, expected not a hang;
  ADR-044 preconditions_for_flip), (3) wire CI to sign `ci_result`, (4) deploy the merge-gate runner
  (`run_gate` is in-process, zero production callers), (5) Slice-3 scope-b runtime (dual-chief apps,
  overseer fact emission). NONE started this session.
- **Follow-up adversarial round** on the 2 deferred dormant gaps (reproduce E2E → fix → Lane-V) — when the
  cutover path is next touched, or proactively.

## 6. Sharp edges (durable, from this session)

- **A green suite ≠ a hardened surface.** The doc audit's activation pass called the substrate "hardened,
  341 passed"; the adversarial code audit found 4 reproducible MAJORs the suite never exercised. Document
  "hardened" only after closing what an adversary finds — fix-then-document was a correctness constraint on
  the deliverable, not ceremony.
- **"Guard exists at the wrong layer" recurs.** A extended ADR-041's `well_formed` drop-contract *upstream*
  to deserialization; C extended `_DET_ENV`'s determinism from commit-identity to the *merge algorithm*.
  Always ask whether an existing guard actually covers the new entry point.
- **Verify your own fix — it found the next layer a 5th time.** A's Lane-V Rule-13 sweep surfaced the
  dormant `store.py` sibling.
- **Defense-in-depth must degrade safely.** D's verifier showed that with layer-1 (manifest-source) off,
  layer-2 (non-ISO guard) made the re-run fail *safe* (raise→teardown); only disabling *both* reproduced
  the silent over-advance.
- **Line-adding fixes shift ARCHITECTURE hard anchors.** C's `merge_tree` +14 lines drifted
  `cas_create_or_update_ref`/`preflight_bus_init` anchors → ci_smoke red until re-anchored. Run `ci_smoke`
  before each commit, not just at session end.
- **Workflow scripts are plain JS:** literal backticks and apostrophes inside the prompt template-literals
  break the parser — use single quotes / string concat for inline code refs.
- **Verifier worktrees need the venv via abs-path + PYTHONPATH** (`.venv` is gitignored, absent from the
  worktree): `env -u GIT_INDEX_FILE PYTHONPATH="$PWD" /…/.venv/bin/python -m pytest …`.

## 7. Where the truth lives

`DECISIONS.md` ADR-046..049 (full rationale + verification). `docs/REMEDIATION-INVENTORY.md` (5 verified/fixed
rows + 2 new open). The 4 `logs/` artifacts in §2. `ARCHITECTURE.md` §13A (re-anchored; §13A.4 count now
341/0). The unified suite under `docs/protocol/threeway/`.
