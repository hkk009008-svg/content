# Program Hardening Roadmap — "Runs as Intended, Bug-Free" — Design Spec

*Date: 2026-06-14 · Author: coordinator seat (Session-6), brainstormed with the
user-principal · Status: design approved, pending spec-review + plan.*

## 0. Locked decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Success definition | **(D)** all three, sequenced: robustness → capability → verified E2E |
| Discovery scope | **(B)** bounded discovery of high-risk subsystems, then remediate |
| Execution shape | **Approach 2** — discovery spine + severity waves across parallel lanes |
| Role distribution | safe, single-writer inventory; lane-partitioned; impl ≠ verifier (see §6) |
| Deliverable | sequenced multi-session roadmap the 4-seat team executes, coordinator-integrated |

## 1. Problem & intent

**"Runs as intended"** = the program realizes `docs/PROGRAM-MANUAL.md` §1–2: a
script/idea becomes finished, photorealistic cinematic video with synced audio,
operated to full capability.

**"Bug-free"** = no crashes, no *silent degradation* (wrong result with no
signal), every gate fails safe, and the end-to-end path is provably reproducible.

**Why this is a campaign, not a patch:** the program is already clean on surface
hygiene (2 production `TODO`s, `ci_smoke` green, ~2,400 tests passing). The real
"not yet bug-free" surface is concentrated and partly already under repair by the
live 4-seat team:

- **~28 pinned defects** (xfail), genuine code defects clustering in two families:
  **NaN/inf-gate bypasses** (`auto_approve` thresholds, `budget_limit_usd` at
  `core.py:101`, `pulid_weight`→ComfyUI node 100, `get_workflow_params` crash) and
  **silent-degradation holes** (`coherence_analyzer` unreadable-image,
  `validate_identity_vision` on API error, `_best_take_lipsync`, mouth-energy
  scorer). This is the in-flight NaN-gate hardening epic.
- **Coverage gaps** (`docs/TEST-COVERAGE-ANALYSIS-2026-06-14.md`, coordinator-verified
  via `wf_bf7078e7-4ab`): HTTP surface ~46/66 untested, audio DSP zero-tested,
  orchestration mutation paths.
- **Structural quality issues**: max-wide over-cook, secondary-character binding,
  `has_character` LoRA-only hole.
- **E2E-verification gap**: "runs as intended" is proven only by manual pod burns;
  the integration tests are environment-gated smoke stubs.

## 2. Architecture — one inventory, drained in waves

A single living artifact, **`docs/REMEDIATION-INVENTORY.md`**, is the spine and the
single source of truth. Discovery populates it; the waves drain it; the E2E lock
freezes it against regression.

**Inventory row schema** (one row per defect / gap / lever):

```
id · subsystem · file:line · severity · fail-mode · repro · xfail-pin ·
lane-owner · wave · status(open|fixing|fixed|verified) · verifier · notes
```

**Flow:** Discovery (Phase 0) → severity-ranked inventory → Wave 1 → Wave 2 →
Wave 3 → Wave 4 (E2E lock) → done. Each arrow is a coordinator-gated boundary.

The inventory is the **burn-down chart**: at any moment it answers "how many
CRITICALs remain, in which lane, blocking which wave." This is the mechanism that
stops the recurring re-discovery of already-known defects.

## 3. Phase 0 — the discovery bug-hunt

A coordinator-owned **discovery Workflow** fans adversarial agents across
*high-risk subsystems only*, each probing **fail-open paths** (not the happy
paths the existing tests already cover):

- **Gates** — `auto_approve`, `face_validator_gate`, `motion_gate`,
  `identity_gate`, `coherence_analyzer`
- **Money** — `core.py` budget, cost-estimation, lip-sync pricing
  (unbounded-spend class)
- **Silent-degradation I/O** — image/video decode, API-error swallow,
  ffmpeg/ffprobe failure
- **HTTP mutators** — `web_server.py` destructive / state-mutating endpoints
- **Resume/checkpoint** — state reconstruction on restart
- **Identity/continuity** — PuLID/LoRA injection, secondary-char binding

Each candidate finding gets an **adversarial refute pass** (independent agents try
to prove it *isn't* real) to kill false positives — the discipline that caught
this session's path-traversal false alarm. Every **confirmed** defect is
**xfail-pinned in the same pass** so CI tracks it from day one.

**Acceptance for Phase 0:** inventory committed; every confirmed defect has an
xfail pin; every finding has a severity and a candidate lane; false positives
recorded as rejected (not silently dropped).

## 4. Severity taxonomy (this is how the (D) ordering falls out automatically)

| Severity | Definition | Routes to |
|---|---|---|
| **CRITICAL** | crash · state/data corruption · money-loss · gate-bypass that ships a bad take | Wave 1 |
| **MAJOR** | silent degradation (wrong result, *no signal*) · critical-path coverage hole | Wave 2 |
| **MEDIUM** | recoverable degradation · poll/backoff inefficiency · partial result | Wave 2/3 (triaged) |
| **MINOR** | cosmetic · observability · dead code | deferred / batched (YAGNI) |

Sorting the whole discovered inventory by severity and draining it top-down
yields the robustness→capability ordering automatically: the CRITICALs *are* the
robustness work; the capability levers are lower-severity "doesn't run as
intended at full quality" items.

## 5. The four remediation waves

| Wave | Content | Lanes | Acceptance bar |
|---|---|---|---|
| **1 — Critical robustness** | NaN/inf-gate family, budget bypass, gate-bypass, crash paths; **+ pin measurement determinism** | both pairs, by file proximity | every CRITICAL closed, xfail→green, fail-safe by construction, independently verified, `ci_smoke` green |
| **2 — Silent-degradation + coverage** | swallow-and-continue holes; tests for HTTP mutators, audio DSP, resume/checkpoint | Pair-A: image/identity · Pair-B: video/audio/assembly | every MAJOR closed; critical-path coverage landed; green + indep-verified |
| **3 — Capability levers** *(pod-gated)* | over-cook, secondary-char binding, dialogue/lip-sync quality | Pair-A (realism/identity) · Pair-B (dialogue/audio) | measured improvement vs baseline; R-MEASURE artifacts persisted to `logs/` |
| **4 — E2E lock** | automated script→video proof wired to CI (see §7) | coordinator-orchestrated | Tier-1 E2E green in CI; one Tier-2 real render passes thresholds |

**Determinism note (Wave 1):** the measurement-determinism guard is a Wave-1 item
*before* any capability measurement — the program's history shows capability
metrics were untrustworthy because of degradation/non-determinism (the OpenCV
thread-race; ArcFace scoring over-cooked renders). Robustness is the instrument
that makes capability measurable.

## 6. Role distribution & coordination safety

### 6a. Ownership matrix

| Concern | **Coordinator** | **Director** (per pair) | **Operator** (per pair) |
|---|---|---|---|
| Inventory artifact (severity/wave/lane cols) | **OWNS — single writer** | reads its slice | reads its slice |
| Defect status (open→fixed→verified) | **reconciles** from mailbox | — | **reports** via `verification-report` |
| Per-defect brief (R-BRIEF full-shape) | — | **OWNS** (own lane) | — |
| The fix (implementation) | **never** (read-only on code) | does / dispatches (own lane) | — |
| Independent verification (impl ≠ verifier) | gates wave on it | — | **OWNS** (own lane) |
| Cross-lane co-sign (Rule #23, tiered) | routes & tracks | **OWNS** (signs other lane) | — |
| Doc-truth re-sync (ARCHITECTURE/cross) | **OWNS** | lane docs | lane doc-sync |
| Wave acceptance gate + sequencing | **OWNS** | — | feeds verification |
| Discovery + per-wave verification workflows | **OWNS** (read-only fan-out) | — | — |
| Push (user-gated) | executes on user auth | decides/escalates via coordinator | — |

### 6b. Lane partition — collision-free by construction

- **Pair-A lane (image/identity):** `quality_max.py`, PuLID/LoRA injectors,
  `face_validator_gate`, `identity_gate`, `coherence_analyzer`, over-cook,
  secondary-char binding.
- **Pair-B lane (video/assembly/audio):** `phase_c_*`, `lip_sync.py`, `audio/*`,
  `motion_gate`, `cinema/checkpoint`, dialogue.
- **Cross-cutting modules (the collision risk):** `auto_approve.py`, `core.py`
  (budget), `web_server.py`, `cinema/context.py`, `workflow_selector.py`.
  **Handling:** each cross-cutting module gets a single campaign primary-owner
  seat *per wave* — recorded in the inventory as a **shared-module lock** — and any
  change to it requires the **other director's Rule #23 co-sign**. This guarantees
  *one writer per file at a time* even for shared code.

### 6c. Per-defect lifecycle (the safe handoff chain)

```
Discovery ─▶ Coordinator writes inventory row (severity·lane·wave) + xfail pin
          ─▶ Wave opens: Coordinator assigns row to a lane (shared module ⇒ lock to ONE seat)
          ─▶ Director writes R-BRIEF (full-shape pattern refs) ─▶ dispatches implementer
          ─▶ Implementer: TDD — xfail reproduces defect ▶ fix ▶ flip green ▶ ONE pathspec commit
          ─▶ Operator: independent diff verify (impl≠verifier) ─▶ mailbox verification-report (GO/NITS/FAIL)
          ─▶ [cross-lane?] other Director Rule #23 co-sign (Tier-A before dispatch / Tier-B 48h)
          ─▶ Coordinator: reconcile status into inventory; at wave end run verify-workflow + ci_smoke ─▶ gate next wave
```

### 6d. The five safety guarantees

1. **One writer per file** — lane separation + per-wave shared-module locks ⇒ no
   merge collisions (honors "never two implementers in parallel on shared files").
2. **One writer for the inventory** — coordinator is sole inventory-writer; seats
   report status via **mailbox**, not by editing the artifact ⇒ no
   assignment/status races. (Producer/consumer queue, not a shared-write file.)
3. **Every fix verified by a non-author** — operator (or cross-seat) verifies each
   diff; coordinator gates the wave on it.
4. **Cross-lane changes dual-signed** — Rule #23 tiered co-sign; cross-cutting
   modules never change single-handed.
5. **Waves don't bleed** — the coordinator's per-wave acceptance gate (all items
   green + indep-verified + `ci_smoke` green + coverage/E2E threshold) blocks wave
   N+1 until wave N is truly done.

### 6e. Unified teamwork — the integration spine

The inventory is the shared source of truth — one severity-ranked burn-down every
seat reads. Pairs work **independently within a wave** and **converge at the
wave-boundary gate** (sync at boundaries, not per-commit). The coordinator is the
**integration point**: routes cross-lane work, runs the discovery/verification
workflows, keeps docs true, and surfaces every consequential decision (push,
pod-spend, scope) to the **user-principal**, who is the top of the authority
chain (`user > git commits > mailbox sent/ > STATE.md > default`).

## 7. The E2E lock & the concrete "done" definition

The deepest gap is that "runs as intended" is proven only by manual pod burns.
Two-tier fix:

- **Tier 1 (CI, no pod, no $):** drive `CinemaPipeline(pid, headless=True)` through
  *all* phases with **stubbed providers** (fixture ComfyUI / video-API / audio /
  LLM responses), asserting orchestration + gates + assembly run clean end-to-end.
  Catches wiring / gate / state regressions on every commit. Uses the existing
  headless contract (`GateNotSatisfiedError` fail-fast; PLAN gate auto-approve via
  ChiefDirector APPROVED + `director_review` written).
- **Tier 2 (milestone, pod-gated):** a real burn → actual photoreal video with
  synced audio, scored against acceptance thresholds (arc / lip-sync / no
  over-cook), run at milestones (not per-commit) due to GPU cost.

**"Runs as intended & bug-free" = done when, and only when:**
1. inventory drained — 0 open CRITICAL/MAJOR; MEDIUMs explicitly triaged;
2. all defect-xfails flipped green;
3. critical-path coverage landed (HTTP mutators, audio DSP, resume/checkpoint);
4. **Tier-1 E2E green in CI**;
5. **one Tier-2 real render passing the acceptance thresholds**.

## 8. Risks & guards

- **Re-drift on the live tree** → fix-on-touch discipline; coordinator re-syncs
  `ARCHITECTURE.md`/docs (as done in Session-6 for the quality_max/phase_c anchors).
- **Pod cost/availability** → Waves 3 and Tier-2 are pod-gated; batch into pod
  sessions; surface spend to the principal before each burn.
- **Measurement non-determinism** → the determinism guard is a Wave-1 item, before
  any capability measurement.
- **Boiling the ocean** → discovery is bounded to the high-risk subsystems in §3;
  cold/rarely-run code is excluded; MINORs are deferred.
- **False positives** → the adversarial refute pass in Phase 0 + verification
  workflows at each wave gate.
- **Concurrency hazards** → per-seat `GIT_INDEX_FILE`; subagents prefix git with
  `env -u GIT_INDEX_FILE`; explicit-pathspec commits; one commit per defect; git
  is the tiebreaker (first to land wins).

## 9. Out of scope (YAGNI)

- Refactors not required to close a defect or land a wave's coverage.
- Auditing cold/rarely-executed code paths.
- A permanent always-on pod or a per-commit real-render gate (cost-prohibitive;
  Tier-2 is milestone-gated instead).
- New product features beyond PROGRAM-MANUAL's stated intent.
- Fixing the unrelated `operator2 cursor_orphan` advisory (separate lane item).

## 10. Execution prerequisites (resolved, not open)

- **Inventory bootstrap:** Phase 0 creates `docs/REMEDIATION-INVENTORY.md`; the
  ~28 existing xfail pins are migrated into it as the seed rows before the hunt
  adds unknowns.
- **Lane assignment of cross-cutting modules:** decided per wave at wave-open by
  the coordinator (recorded as the shared-module lock), not pre-frozen here — this
  is a runtime assignment, deliberately deferred to wave-open and owned by §6b's
  mechanism, not an unspecified gap.
- **Pod authorization:** Waves 3 / Tier-2 do not begin until the user-principal
  authorizes the pod spend (per the authority chain).
```
