# Program Hardening — Wave 1 (Critical Robustness) Execution Plan

> **For the 4-seat team (NOT a coordinator-run subagent plan).** This wave's fixes
> are **production code** → per spec §6a the **coordinator never authors a fix**. Each
> task below is executed **in-lane** by the owning pair (director writes the R-BRIEF +
> implements or dispatches; operator independently verifies), under the git-native lock
> protocol (§6b) and Tier-A co-sign discipline (§6c). The coordinator only **gates the
> wave** (§6f) and reconciles the inventory. Do **NOT** run
> `superpowers:subagent-driven-development` on this plan from the coordinator seat —
> that would put the coordinator in the fix path. Steps use `- [ ]` for the executing
> seat's own tracking.

**Goal:** Drain all **8 CRITICAL rows** of `docs/REMEDIATION-INVENTORY.md` (wave=1) to
`verified` — every NaN/inf-gate bypass, money-loss bypass, crash path, and data-corruption
path closed, each fix verified by a non-author, with `ci_smoke` green and the determinism
fix re-confirmed.

**Architecture:** One inventory drained in severity waves (spec §2). Wave 1 = the
top-severity slice. Phase 0 already wrote every defect's **strict-xfail pin** (the RED);
Wave 1 lands the **fix that flips it GREEN** and removes the pin. Pairs work independently
within the wave and converge at the **wave-boundary gate** (`scripts/wave_gate_check.py 1`
MET). Cross-cutting modules (`auto_approve.py`, `core.py`, `web_server.py`) are serialized
by **push-first git locks** + **Tier-A cross-lane co-sign** (these are all CRITICAL).

**Tech Stack:** Python 3 / pytest (strict-xfail pins), `cinema/auto_approve.py`,
`cinema/core.py`, `cinema/context.py` (`_finite_or` helper), `quality_max.py`,
`workflow_selector.py`, `cost_tracker.py`, `web_server.py`. Git-native locks under
`coordination/locks/`; mailbox `verification-report` artifacts.

**Spec:** `docs/superpowers/specs/2026-06-14-program-hardening-roadmap-design.md` (v6,
design-approved). **Inventory (source of truth):** `docs/REMEDIATION-INVENTORY.md`.

> **⚠ LIVE STATUS (plan authored 2026-06-14, HEAD `b33c595`).** A seat **already
> self-started Wave-1** under the §6f deputy/solo path while the coordinator was offline:
> **Task 8 (`ws-reorder-deletes`) is already `fixed`** (`b33c595`, impl=solo; lock
> `W2-web_server.py.lock` held; **operator verify pending**). So the live wave is **7 rows
> `open` + 1 `fixed`-pending-verify**, not 8 `open`. Task 8 below is rewritten to the
> `fixed→verified` path. A peer is/was live editing `tests/unit/test_discovery_web_server_xfail.py`
> (regression-test hardening) — **do not touch `web_server.py` or that test file** while its
> lock is held.

---

## Chunk 1: Wave-1 scope, roles, constants, lifecycle

### A. The 8 CRITICAL rows (inventory wave=1, severity=CRITICAL)

| # | id | file:line | lane | cross-cutting? | lock | co-sign | pin (RED, exists) |
|---|----|-----------|------|----------------|------|---------|-------------------|
| 1 | `aa-nan-rules` | `cinema/auto_approve.py:118` | **A** | yes | `W1-auto_approve.py.lock` | **Tier-A** (Pair-B dir) | `tests/unit/test_auto_approve_nangate_xfail.py` |
| 2 | `aa-inf-scorebypass` | `cinema/auto_approve.py:424` | **A** | yes | `W1-auto_approve.py.lock` | **Tier-A** (Pair-B dir) | `tests/unit/test_discovery_auto_approve_xfail.py` |
| 3 | `aa-budget-nan-veto` | `cinema/auto_approve.py:584` | **A** | yes | `W1-auto_approve.py.lock` | **Tier-A** (Pair-B dir) | `tests/unit/test_discovery_auto_approve_xfail.py` |
| 4 | `pulid-nan-node100` | `quality_max.py:560` | **A** | no (pure-lane) | — | none | `tests/unit/test_nangate_siblings_op1_verify.py` |
| 5 | `null-continuity-crash` | `workflow_selector.py:515` | **A** | no (pure-lane) | — | none | `tests/unit/test_nangate_siblings_op1_verify.py` |
| 6 | `budget-nan` | `cinema/core.py:101` | **B** | yes | `W1-core.py.lock` | **Tier-A** (Pair-A dir) | `tests/unit/test_budget_nan_gate_xfail.py` |
| 7 | `costtracker-perf-uncounted` | `cost_tracker.py:282` | **B** | no (pure-lane) | — | none | `tests/unit/test_discovery_cost_xfail.py` |
| 8 | `ws-reorder-deletes` ✅ FIXED (verify pending) | `web_server.py:1402` | **B** | yes | `W2-web_server.py.lock` | **Tier-A** (Pair-A dir) | (pin removed; now a live regression test) |

> **Lock-name note (#8):** the inventory `shared-lock` for `ws-reorder-deletes` is
> `W2-web_server.py.lock` (born when `web_server.py` rows were filed at wave 2, before this
> row was upgraded MAJOR→CRITICAL and re-waved to 1). The live seat **already claimed
> `W2-web_server.py.lock`** (on disk, `solo`), so the plan uses `W2` to match — **do not
> rename it to `W1` now**; the pending `release-lock` keys off the `W2` name and renaming
> would break the release. Cosmetic mismatch (wave=1 row, `W2`-prefixed lock); leave as-is.

**Lane load:** Pair-A = 5 rows (#1–#5), Pair-B = 3 rows (#6–#8; #8 pre-fixed, verify pending).

**Why 5 of 8 need Tier-A co-sign:** §6b — *any* commit touching a cross-cutting module
(`auto_approve.py` / `core.py` / `web_server.py`), **even in isolation**, requires co-sign
from every other affected lane director; because all five are **CRITICAL**, the co-sign is
**Tier-A (pre-commit)** per §6c — the co-sign `verification-report` **must be in the mailbox
before the fix commit lands** (this overrides async-OK). The 3 pure-lane rows (#4, #5, #7)
are CRITICAL but touch no cross-cutting module → no co-sign.

### B. Wave-1 cross-cutting first-mover sequence (§6b — recorded in the inventory header at wave-open)

Each contested cross-cutting module has open Wave-1 pins from exactly **one** lane, so the
§6b tie-break never fires — the first-mover is the pin-holding pair:

| module | lock | first-mover | rationale |
|--------|------|-------------|-----------|
| `auto_approve.py` | `W1-auto_approve.py.lock` | **Pair-A** | holds all 3 open W1 pins (`aa-nan-rules`, `aa-inf-scorebypass`, `aa-budget-nan-veto`) |
| `core.py` | `W1-core.py.lock` | **Pair-B** | holds the only open W1 pin (`budget-nan`) |
| `web_server.py` | `W2-web_server.py.lock` (live) | **Pair-B** | held the only open W1 pin (`ws-reorder-deletes`); **already claimed solo + fixed `b33c595`**, verify pending |

`cinema/context.py` is cross-cutting but **no Wave-1 row targets it** — `aa-nan-rules`'s fix
*reads* the `_finite_or` helper from it but edits `auto_approve.py` only; no first-mover
needed for `context.py` in Wave 1 (if a fix must *edit* `context.py`, claim
`W1-cinema/context.py.lock` first and acquire locks in lexicographic order per §6b).

### C. Execution constants (the §11 decisions this plan fixes for Wave 1)

These were deliberately delegated by the spec to the implementation plan. **Resolved for Wave 1:**

- **C1 — Determinism re-verification (§5/§11).** Wave 1 carries a *re-verify*, not a fresh
  fix (the OpenCV thread-race is closed: `cv2.setNumThreads(1)` + deterministic tie-break,
  `ARCHITECTURE.md` §11.1).
  - **CI re-verify (no pod, the Wave-1 gate item):**
    `.venv/bin/python -m pytest tests/unit/test_embedding_determinism_routing.py -q` →
    **5 passed**. This confirms all DeepFace `represent`/`extract_faces` sites + the
    `domain/` siblings still route through `cv2_single_thread` (the routing is the
    regression surface; a fix elsewhere that drops the wrap would turn this red).
  - **Pod probe (NOT a Wave-1 item — pod-gated, pre-burn gate):**
    `scripts/_probe_embedding_determinism.py --load` (guarded = 30/30 byte-identical).
    This is a **no-op on macOS GCD** (`setNumThreads(1)` doesn't serialize there) and only
    meaningful on the Linux pod, where the pinned man-0.870 value must also be re-confirmed
    before it is trusted as the production baseline. Defer to the Tier-2 pre-burn gate
    (Wave-3), not Wave-1.

- **C2 — FAIL-cap counting (§6b/§11).** The 3-consecutive-FAIL anti-hostage cap counts
  **only `FAIL` verdicts**. A `NITS` verdict does **not** count toward the cap (NITS means
  the fix is substantively correct with minor issues; counting it would punish near-misses
  and incentivize FAIL-vs-NITS gaming). A NITS resets nothing and adds nothing to the
  counter; only a hard FAIL increments it. After 3 FAILs on one defect the holder releases
  the lock and re-queues/splits (or escalates to coordinator), per §6b.

- **C3 — Mid-wave CRITICAL in a module whose lock is held for a different `file:line`
  (§6b/§6f/§11).** If a seat discovers a new CRITICAL in a cross-cutting module whose lock
  is currently held for a *different* `file:line`, it **records the provisional row + pin
  immediately** (dedup is per `file:line`; the lock is per *module*) so the gate counts it,
  while the **fix queues behind the lock**. Recording the row does **not** require holding
  the lock; only the *fix* does. This is the record-without-lock path: a mid-wave CRITICAL
  is never lost to a busy lock.

- **C4 — MEDIUM-as-gate-item (§4/§11).** Wave 1 contains **no MEDIUM rows** (all 8 are
  CRITICAL), so no MEDIUM can float past this gate. The Wave-1 gate additionally asserts
  **no un-`wave`-assigned MEDIUM exists in the inventory** (`wave` column non-empty for every
  MEDIUM) — carried forward so the rule is live before Wave 2 inherits the MEDIUM backlog.

- **C5 — `conftest.py` policy (§6a/§11).** Coordinator-authored test fixtures/stubs are
  **test-only by default** and need **no** Tier-A co-sign, *unless* a fixture can alter the
  **test-time behavior of a production path** (e.g. monkeypatching a production module at
  import) — those need a Tier-A co-sign from the affected lane director. Wave 1 needs no new
  shared fixtures (each pin is self-contained); this policy governs Wave-2 stub authoring.

- **C6 — Pod-off executor (§6f/§11).** When a gate is formally blocked (a director's
  gate-request goes unserviced) and **no coordinator is live**, the **director who posted the
  gate-request issues the pod-stop immediately** (the trip-wire does not wait on the 24h SLA)
  and signals the user-principal via a mailbox event + a presence-file update; the coordinator
  confirms the stop on return. *(Operationally moot for Wave 1 — the pod is currently STOPPED,
  $0 — but resolved here so the rule is live before any pod-gated wave.)*

### D. Per-defect lifecycle (§6c — the template every task below follows)

```
Row available (wave open, status=open)
 1. [cross-cutting only] Claim the §6b lock: `git fetch`; if no W1-<module>.lock,
    `coordination/bin/claim-lock W1 <module> <defect-id>` → commits + pushes the lock.
    If the push is REJECTED, you LOST — do NOT implement; take the next lane row.
    Implementation begins ONLY after the lock push succeeds.
 2. Director writes the R-BRIEF (R-BRIEF: full-shape refs — verify the exact signature,
    call sites, and existing guard patterns at the file:line before implementing) and sets
    `priority` (coordinator transcribes priority into the inventory column).
 3. [cross-cutting + CRITICAL only] The OTHER lane director Tier-A co-signs THE R-BRIEF
    (full change-set scope) → lands a `verification-report` in the mailbox BEFORE any code.
    No CRITICAL cross-cutting code lands before this co-sign (binds director-as-implementer too).
 4. Implement (director directly for a small fix, else a dispatched subagent — R-ORCH at
    ≥5 subtasks / ≥800 LOC). The strict-xfail pin IS the RED; the fix flips it. Remove the
    pin (or update its reason) in the SAME commit — strict=True turns a fixed-but-unremoved
    pin into an XPASS → CI red. ONE pathspec commit per defect.
 5. Operator independently verifies the diff (impl ≠ verifier) → `verification-report`
    GO / NITS / FAIL. On GO, the operator **deletes the lock file in the SAME commit**
    (`coordination/bin/release-lock W1 <module>`), releasing the module. NITS → fixing seat
    addresses, operator re-verifies the nit-diff before GO (no self-upgrade).
    For a CRITICAL cross-cutting fix, the operator additionally confirms the landed diff
    matches the co-signed brief scope (scope drift = FAIL).
 6. Status advance: coordinator reconciles open→fixed→verified at a §6f trigger; when no
    coordinator is live, the lane deputy transcribes the operator's existing GO into its
    own-lane row (deputy never self-verifies).
```

**`fixed→verified` shortcut (a fix already landed, e.g. `ws-reorder-deletes`):** when a row is
already `fixed` (deputy-written by a solo seat) and the pin is already removed, do **NOT** run
the `open→fixed` steps (claim lock / `--runxfail` RED / implement). The remaining obligation is
only: operator independent diff verify → `verification-report` GO → `release-lock` in the GO
commit → coordinator advances status to `verified`.

**Finding your wave's rows:** use the **inventory** `xfail-pin` column as the
authoritative row→pin map (the source of truth). Do **not** grep `W1:` to enumerate —
3 seed-migrated pins (`aa-nan-rules`, `pulid-nan-node100`, `null-continuity-crash`) predate
the reason-prefix convention and carry no wave-tag (cosmetic; the gate is inventory-driven).
If you remove one of those pins as part of a fix, no action needed; if you touch its reason,
add the `W1:CRITICAL:<id>` prefix opportunistically.

---

## Chunk 2: The 8 tasks + the Wave-1 gate

> Each task is owned by the named pair. The **fix-direction hint** is a pointer from the
> inventory `notes` — it is **NOT** the spec for the fix. The director's R-BRIEF owns the
> actual change shape (§6a); verify the full shape at the file:line before implementing.

### Task 1 — `aa-nan-rules` (Pair-A · cross-cutting · Tier-A co-sign)

**Files:**
- Modify: `cinema/auto_approve.py:118` (NaN threshold read in `from_project`)
- Pin (RED): `tests/unit/test_auto_approve_nangate_xfail.py` (5 parametrized cases)
- Lock: `coordination/locks/W1-auto_approve.py.lock`

- [ ] Claim `W1-auto_approve.py.lock` (Pair-A is first-mover; §6b push-first).
- [ ] Director R-BRIEF + priority; Pair-B director Tier-A co-signs the R-BRIEF (mailbox `verification-report` BEFORE code).
- [ ] Confirm RED: `.venv/bin/python -m pytest tests/unit/test_auto_approve_nangate_xfail.py --runxfail -q` → fails with a **domain AssertionError** (a NaN threshold makes `nan > 0` False so the veto rule never registers; gate silently passes).
- [ ] Implement the fix. **Hint:** finite-guard the numeric reads in `from_project` via `cinema.context._finite_or` (the established chokepoint; same family as the 700/701 guards). Remove the pin in the same commit.
- [ ] Verify GREEN: `... pytest tests/unit/test_auto_approve_nangate_xfail.py -q` (pin removed → all 5 cases green or gone). `ci_smoke` green.
- [ ] ONE pathspec commit. Operator independent verify → GO + `release-lock W1 auto_approve.py` in the same commit; confirm diff matches the co-signed brief scope.

> **Sequencing note (auto_approve.py holds 3 W1 rows #1/#2/#3):** they share the
> `W1-auto_approve.py.lock`. The lock is **per-module**, so Pair-A holds it across all three
> — implement them as a single locked work-stream (one commit per defect, lock released only
> after the **last** of the three is operator-GO'd), or release+reclaim between defects. Either
> way the three commits are independent pathspec commits and each needs its own operator GO.
> Tier-A co-sign covers each R-BRIEF's scope; if the three share one R-BRIEF, the co-sign
> covers the combined change-set.

### Task 2 — `aa-inf-scorebypass` (Pair-A · cross-cutting · Tier-A co-sign)

**Files:**
- Modify: `cinema/auto_approve.py:424` (+ siblings 445/456/468: `_best_take_composite`, `_best_take_identity`, `_best_take_motion_score`, `_best_take_lipsync`)
- Pin (RED): `tests/unit/test_discovery_auto_approve_xfail.py::test_inf_composite_score_must_not_auto_approve`
- Lock: `W1-auto_approve.py.lock` (shared with Tasks 1, 3)

- [ ] Hold/claim `W1-auto_approve.py.lock`; R-BRIEF + Pair-B Tier-A co-sign.
- [ ] Confirm RED (`--runxfail`): `inf` composite passes `float()`/`max()`; `inf < threshold` always False → `auto_approved=True`. All four take-score helpers share the gap.
- [ ] Implement. **Hint:** add a `math.isfinite` guard in `_best_take_composite` and the **three sibling helpers** so inf/NaN scores are treated as invalid (gate rejects). Note the pin docstring: motion gate needs **both** `identity_score` AND `motion_fidelity` inf to bypass — guard all four. Remove the pin.
- [ ] Verify GREEN + `ci_smoke`. ONE commit. Operator GO + lock release (after last auto_approve task). Scope-match check.

### Task 3 — `aa-budget-nan-veto` (Pair-A · cross-cutting · Tier-A co-sign)

**Files:**
- Modify: `cinema/auto_approve.py:584-595` (`_shot_over_budget`)
- Pin (RED): `tests/unit/test_discovery_auto_approve_xfail.py` (the `_shot_over_budget` NaN case)
- Lock: `W1-auto_approve.py.lock` (shared with Tasks 1, 2)

- [ ] Hold/claim lock; R-BRIEF + Pair-B Tier-A co-sign.
- [ ] Confirm RED (`--runxfail`): `spent = shot_state.get('spent_usd', 0) or 0` keeps NaN (NaN is truthy), and `float(nan) > multiplier*budget` is False under IEEE 754 → veto silently skipped.
- [ ] Implement. **Hint:** replace the `or 0` idiom with `math.isfinite(spent)` / `_finite_or` so NaN `spent_usd` is detected and the veto fires (returns True). Remove the pin.
- [ ] Verify GREEN + `ci_smoke`. ONE commit. Operator GO + lock release (last auto_approve task releases `W1-auto_approve.py.lock`). Scope-match check.

### Task 4 — `pulid-nan-node100` (Pair-A · pure-lane · no co-sign)

**Files:**
- Modify: `quality_max.py:560` (+ `start_at`/`end_at` at 561-562; PuLID node-100 weight)
- Pin (RED): `tests/unit/test_nangate_siblings_op1_verify.py` (pulid_weight node-100 case)

- [ ] No lock (pure Pair-A lane). Director R-BRIEF (no co-sign — pure-lane).
- [ ] Confirm RED (`--runxfail`): NaN `pulid_weight` reaches node-100 `weight` with no `_finite_or` guard (unlike nodes 700/701); `start_at`/`end_at` share the gap → silent render corruption. Reachable via `controller.py:778` `pulid_weight_override` (no chokepoint).
- [ ] Implement. **Hint:** mirror the node-700/701 `_finite_or` guard onto node-100 `weight` + `start_at`/`end_at` (this is the director-1 "import-swap pass" — `_finite_or` from `cinema.context`; verify the import is circular-safe, a prior reviewer's suggested fix introduced a circular import). Remove the pin.
- [ ] Verify GREEN + `ci_smoke`. ONE commit. Operator independent verify → GO.

### Task 5 — `null-continuity-crash` (Pair-A · pure-lane · no co-sign)

**Files:**
- Modify: `workflow_selector.py:515` (`get_workflow_params`)
- Pin (RED): `tests/unit/test_nangate_siblings_op1_verify.py` (null continuity_options case)

- [ ] No lock (pure Pair-A lane). Director R-BRIEF.
- [ ] Confirm RED (`--runxfail`): JSON-null `continuity_options` → `None.get('img2img_denoise')` → `AttributeError` crash.
- [ ] Implement. **Hint:** the sibling site `quality_max.py:1041` already has the `isinstance(..., dict)` dict-guard this block lacks — mirror it. Note: `bf1034a` closed the main `workflow_selector.py` non-finite issue but its audit boundary did **not** extend to this null-crash sibling. Remove the pin.
- [ ] Verify GREEN + `ci_smoke`. ONE commit. Operator independent verify → GO.

### Task 6 — `budget-nan` (Pair-B · cross-cutting · Tier-A co-sign)

**Files:**
- Modify: `cinema/core.py:101-104` (budget read)
- Pin (RED): `tests/unit/test_budget_nan_gate_xfail.py`
- Lock: `coordination/locks/W1-core.py.lock`

- [ ] **PRE-STEP — resolve the design question BEFORE claiming the lock** (so the lock isn't
  held while waiting on the principal): fail-safe **block** on NaN budget vs `None` = unlimited.
  This is a behavior policy with money implications → **SURFACE, do not silently decide** (§6e) —
  the Pair-B director surfaces the choice to the user-principal and records the decision in the
  R-BRIEF + `DECISIONS.md`. Default lean: **fail-safe block** (a NaN cap is corruption, not "unlimited").
- [ ] Claim `W1-core.py.lock` (Pair-B is first-mover). R-BRIEF (encodes the resolved policy) + **Pair-A** director Tier-A co-sign (mailbox before code).
- [ ] Confirm RED (`--runxfail`): NaN `budget_limit_usd` survives `float()`; `bool(nan)=True` stores it; `would_exceed`/`is_over_budget` compare against NaN (always False) → unbounded spend masquerading as a set cap.
- [ ] Implement per the resolved policy. **Hint:** finite-guard the budget read so a NaN cap is rejected/blocked, not treated as no-cap. Remove the pin.
- [ ] Verify GREEN + `ci_smoke`. ONE commit. Operator GO + `release-lock W1 core.py` in the same commit. Scope-match check.

### Task 7 — `costtracker-perf-uncounted` (Pair-B · pure-lane · no co-sign)

**Files:**
- Modify: `cost_tracker.py:282,303` (`log_api`, `log_llm`) + the fresh-instance pattern
- Pin (RED): `tests/unit/test_discovery_cost_xfail.py` (2 cases: `log_api`, `log_llm`)

- [ ] No lock (`cost_tracker.py` is not a §6b cross-cutting module; pure Pair-B/money lane). R-BRIEF.
- [ ] Confirm RED (`--runxfail`): `log_api()`/`log_llm()` write SQLite only with **no** `self.spent_usd` increment; all 4 performance phases + web_research use **fresh `CostTracker()` instances**; `would_exceed`/`is_over_budget` read only the in-process accumulator → entire performance + research spend invisible to the budget gate.
- [ ] Implement. **Hint:** 3 compounding defects — (a) `log_api`/`log_llm` must increment `self.spent_usd`; (b) the fresh-instance pattern means per-instance accumulators don't aggregate (consider reading the SQLite total in `would_exceed`/`is_over_budget`, or a shared accumulator); (c) the gate must see cross-instance spend. The R-BRIEF decides the aggregation approach. Remove both pin cases.
- [ ] Verify GREEN + `ci_smoke`. ONE commit. Operator independent verify → GO.

### Task 8 — `ws-reorder-deletes` ✅ ALREADY FIXED — `fixed→verified` path (Pair-B · cross-cutting · DATA-LOSS)

> **A solo seat already landed this fix** (`b33c595`, 2026-06-14) under the §6f deputy path
> while the coordinator was offline. Do **NOT** re-implement (the `--runxfail` RED no longer
> exists — the strict-xfail pin was flipped XPASS and removed; it is now a live regression
> test). The remaining obligation is **verification only** (`fixed→verified` shortcut).

**Files (already changed by `b33c595`):**
- Modified: `web_server.py:1402` (`reorder_scenes` survivor pass) + `domain/project_manager.py:1081`
- Test: `tests/unit/test_discovery_web_server_xfail.py` (pin removed → `test_reorder_scenes_partial_list_preserves_unlisted_scenes`, a live regression test; a peer is **currently hardening it** with an `order`-contiguity assertion, uncommitted — leave it alone)
- Lock: `coordination/locks/W2-web_server.py.lock` (held `solo`, **still on disk** — releases on operator GO)

- [ ] **Operator (Pair-B) independent diff verify** of `b33c595` (impl≠verifier holds: impl=solo seat, verifier=Pair-B operator). Confirm the survivor pass preserves scenes absent from the posted `scene_ids` (partial-list reorders never delete) **and** the parallel `domain/project_manager.py:1081` fix; confirm the landed diff matches the (retroactive) co-signed scope — a CRITICAL cross-cutting + cross-file change, so **Pair-A director Tier-A co-sign is owed**; since the fix already landed solo, the coordinator surfaces this scope to the Pair-A director for a **retroactive scope confirmation** (or FAIL if the diff overreaches).
- [ ] On GO: operator lands `verification-report` GO **and deletes the lock in the same commit** (`coordination/bin/release-lock W2 web_server.py`).
- [ ] Coordinator advances the inventory row `fixed → verified` (records `verifier`).

> **Data-loss priority:** `ws-reorder-deletes` is irreversible data corruption (the reason it
> was upgraded MAJOR→CRITICAL) — which is why a seat self-prioritized it. A background-task
> chip was spawned for it in Session-7; it is now superseded by `b33c595` (dismiss/ignore the chip).
> **Process note for the coordinator:** a CRITICAL cross-cutting fix landing `solo` *before* its
> Tier-A co-sign is a deviation from §6c (co-sign should precede the commit). Under §6f solo/deputy
> mode it is tolerated for a data-loss CRITICAL, but the retroactive Pair-A scope confirmation
> above is **mandatory** before this row reaches `verified` — do not let the gate pass without it.

### Wave-1 gate (coordinator-owned; §5 acceptance, §6f)

The wave closes only when **all** hold (coordinator runs at the wave-boundary or on a
director's gate-request):

- [ ] `scripts/wave_gate_check.py 1` → **`MET`** (every CRITICAL row `verified`; no
  `provisional` row remains). Run WITHOUT a pipe (`| head` masks the exit code).
- [ ] **Per-item operator `verification-report` GO** in the mailbox for all 8 (the gate
  trusts inventory `status=verified`; the GO artifact is the evidence behind it).
- [ ] **No open/provisional Wave-1 CRITICAL pin remains** — every Wave-1 pin removed or
  XPASS-clean (strict-xfail would turn a fixed-but-unremoved pin red).
- [ ] **Determinism re-verify (C1):**
  `.venv/bin/python -m pytest tests/unit/test_embedding_determinism_routing.py -q` → 5 passed.
- [ ] **MEDIUM-wave-assignment check (C4):** every MEDIUM row has a non-empty `wave`.
- [ ] `.venv/bin/python scripts/ci_smoke.py` → `OK`; full unit suite green (0 failed; any
  xfail count drops by the number of Wave-1 pins removed).
- [ ] All 3 Wave-1 cross-cutting lock files (`W1-auto_approve.py.lock`, `W1-core.py.lock`,
  **`W2-web_server.py.lock`** — note the `W2` prefix, see Task 8) released (deleted via operator GO commits).
- [ ] `ws-reorder-deletes` advanced `fixed → verified` with the **retroactive Pair-A Tier-A
  scope confirmation** recorded (the solo fix landed before co-sign — §6c deviation tolerated
  under §6f for a data-loss CRITICAL, but the scope confirmation is mandatory; see Task 8).
- [ ] Coordinator reconciles the inventory (status columns) and surfaces the GO/NO-GO to
  the user-principal before opening Wave 2.

**Mid-wave CRITICAL rule (§5):** any CRITICAL found *during* Wave 1 is a **Wave-1 gate
blocker** — provisional row + pin created via the deputy/lock path (C3), ratified by the
coordinator; it cannot defer to Wave 2 without explicit user-principal authorization.

---

## Known cosmetic gaps (not blockers)

- 3 seed-migrated W1 pins lack the `W1:CRITICAL:<id>` reason prefix (`aa-nan-rules`,
  `pulid-nan-node100`, `null-continuity-crash`) — they predate the convention. The gate is
  inventory-driven so this is cosmetic; the inventory `xfail-pin` column is the authoritative
  row→pin index. Add the prefix opportunistically when touching those pins' reasons.
- The wave gate keys off the inventory `wave`/`status` columns (not the pin reason prefix);
  the prefix's job is the strict-xfail XPASS tripwire + traceability, a complementary mechanism.
