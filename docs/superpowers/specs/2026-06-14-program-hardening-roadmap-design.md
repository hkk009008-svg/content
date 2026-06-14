# Program Hardening Roadmap — "Runs as Intended, Bug-Free" — Design Spec

*Date: 2026-06-14 · Author: coordinator seat (Session-6), brainstormed with the
user-principal · Status: design approved; spec-review v3 — closes all blocking
findings from review rounds 1 (`wf_c37fb3eb-823`) and 2 (`wf_7b0a23a9-0cd`).*

## 0. Locked decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Success definition | **(D)** all three, sequenced: robustness → capability → verified E2E |
| Discovery scope | **(B)** bounded discovery of high-risk subsystems, then remediate |
| Execution shape | **Approach 2** — discovery spine + severity waves across parallel lanes |
| Role distribution | git-native safe distribution; correct under adversarial timing + coordinator absence (§6) |
| Deliverable | sequenced multi-session roadmap the 4-seat team executes, coordinator-integrated |

## 1. Problem & intent

**"Runs as intended"** = the program realizes `docs/PROGRAM-MANUAL.md` §1–2: a
script/idea becomes finished, photorealistic cinematic video with synced audio,
operated to full capability. **"Bug-free"** = no crashes, no *silent degradation*
(wrong result with no signal), every gate fails safe, end-to-end path provably
reproducible.

**Why a campaign, not a patch:** the program is already clean on surface hygiene
(2 production `TODO`s, `ci_smoke` green, ~2,400 tests passing). The real surface,
partly already under repair by the live 4-seat team:

- **~28 pinned defects** (xfail): **NaN/inf-gate bypasses** + **silent-degradation
  holes** — the in-flight NaN-gate epic.
- **Coverage gaps** (`docs/TEST-COVERAGE-ANALYSIS-2026-06-14.md`, coordinator-verified
  via `wf_bf7078e7-4ab`): HTTP ~46/66 untested, audio DSP zero-tested, orchestration
  mutation paths.
- **Structural quality**: max-wide over-cook, secondary-char binding, `has_character`
  LoRA-only hole.
- **E2E-verification gap**: "runs as intended" proven only by manual pod burns.

## 2. Architecture — one inventory, drained in waves

A single living artifact, **`docs/REMEDIATION-INVENTORY.md`**, is the spine and
source of truth. Discovery populates it; waves drain it; the E2E lock freezes it.

**Inventory row schema:**

```
id · subsystem · file:line · severity · priority · fail-mode · repro · xfail-pin ·
lane-owner · shared-lock · wave · status(open|fixing|fixed|verified|provisional) · verifier · notes
```

- **`priority`** orders items within a (lane, wave): the owning director sets it **in
  the R-BRIEF**; the coordinator (sole inventory-writer) transcribes it into the column.
  No double-write — the brief is the director's channel, the inventory is the coordinator's.
- **`shared-lock`** = the git lock-file path (§6b) when the row touches a cross-cutting
  module; empty for pure-lane rows.
- **`lane-owner`** scopes the deputy-write path (§6f): a pair may deputy-write only rows
  whose `lane-owner` is that pair.

The inventory is a **batch-updated burn-down view, not real-time**: status reflects the
**last reconciliation** (§6f), not fix-time.

The inventory header records two campaign constants: the **wave-gate SLA** (§6f, default
24h) and the **Wave-1 cross-cutting first-mover sequence** (§6b).

## 3. Phase 0 — the discovery bug-hunt

**Precondition (coordinator, committed before the hunt fires):** seed-migrate the
existing xfail pins into the inventory, *HEAD-checked*, with status vocabulary:
- merged + verified-closed (e.g. `workflow_selector.py`, `bf1034a`) → **`verified`** (not re-hunted);
- fix already dispatched in the live tree but not operator-verified → **`fixing`**;
- pinned-but-unfixed → **`open`**.
Seed migration is a Phase-0 *precondition*, not an output.

A coordinator-owned **discovery Workflow** then fans adversarial agents across
*high-risk subsystems only*, probing **fail-open paths**: **Gates** (`auto_approve`,
`face_validator_gate`, `motion_gate`, `identity_gate`, `coherence_analyzer`); **Money**
(`core.py` budget, cost-estimation, lip-sync pricing); **Silent-degradation I/O**
(image/video decode, API-error swallow, ffmpeg/ffprobe); **HTTP mutators**
(`web_server.py`); **Resume/checkpoint**; **Identity/continuity** (PuLID/LoRA, secondary-char).

**Discovery→coordinator handoff contract (named artifact):** the workflow returns
structured JSON (StructuredOutput) of confirmed + rejected findings, each a record
`{subsystem, file:line, fail-mode, reproducer, severity-guess, refuter-verdict}`. The
coordinator **commits this as `logs/discovery-<runid>.json`** — that committed file
*is* the refuter→coordinator boundary (not chat output) — and transcribes confirmed
findings into inventory rows. Each candidate first passes an **adversarial refute pass**
(independent agents try to prove it *isn't* real — the discipline that caught this
session's path-traversal false alarm). Rejected findings are kept in the JSON and noted
in the inventory `notes` as `REJECTED:<reason>`, never silently dropped.

**xfail-pin authorship (resolves the coordinator/code contradiction):** the discovery
workflow emits each pin as a **test-only artifact** (a `pytest.mark`, no production
logic). The coordinator commits the discovery batch (inventory rows + test-only pins +
the `logs/` JSON) — within its narrowed code scope (§6a). The *fix* that flips a pin
green is always authored in-lane, never by the coordinator.

**Acceptance for Phase 0:** seed migration committed; discovery run; `logs/discovery-<runid>.json`
committed; every confirmed defect has an inventory row + test-only xfail pin; rejects
recorded; `ci_smoke` green.

## 4. Severity taxonomy

| Severity | Definition | Routes to |
|---|---|---|
| **CRITICAL** | crash · state/data corruption · money-loss · gate-bypass shipping a bad take | Wave 1 |
| **MAJOR** | silent degradation (wrong result, *no signal*) · critical-path coverage hole | Wave 2 |
| **MEDIUM** | recoverable degradation · poll/backoff inefficiency · partial result | **coordinator triages into Wave 2 or 3 at wave-open** (records the `wave`) |
| **MINOR** | cosmetic · observability · dead code | deferred / batched (YAGNI) |

Draining top-down by severity yields the robustness→capability ordering automatically.

## 5. The four remediation waves

Acceptance bars name **checkable artifacts**:

| Wave | Content | Lanes | Acceptance bar (coordinator-checkable) | Rough estimate* |
|---|---|---|---|---|
| **1 — Critical robustness** | NaN/inf-gate family, budget bypass, gate-bypass, crash paths | both pairs, by file proximity | every CRITICAL row `verified`; xfail green; **operator `verification-report` (GO)** in mailbox per item; **no open/provisional Wave-1 CRITICAL pin remains**; `ci_smoke` green | ~8–12 items, 2–3 sessions |
| **2 — Silent-degradation + coverage** | swallow-and-continue holes; tests for HTTP mutators, audio DSP, resume/checkpoint; **+ commit the capability baseline** (§7) | Pair-A: image/identity · Pair-B: video/audio/assembly | every MAJOR row `verified` w/ operator GO; coverage landed; baseline render in `logs/`; no open Wave-2 pin remains; green | ~10–15 items, 3–4 sessions |
| **3 — Capability levers** *(pod-gated, best-effort)* | over-cook, secondary-char binding, dialogue/lip-sync quality | Pair-A (realism/identity) · Pair-B (dialogue/audio) | each lever **attempted + result recorded** (GO → improvement in `logs/`; HOLD/inconclusive → row `DEFERRED` w/ R-MEASURE artifact). A HOLD does **not** block Wave 4. | 2–3 pod burns |
| **4 — E2E lock** | Tier-1 CI harness + one Tier-2 real render (§7) | coordinator-orchestrated | Tier-1 green in CI (stub-fidelity reviewed, §7); one Tier-2 render passes §7 thresholds | 2–3 sessions |

*Rough scope signals for the plan author, not commitments.

**Determinism item — PRE-CLOSED:** the OpenCV thread-race fix is already merged
(`cv2.setNumThreads(1)` + deterministic tie-break, `ARCHITECTURE.md` §11.1, 30/30
byte-identical). Wave 1 carries only a **re-verification check**, not a fresh fix;
Phase 0 must not re-discover it.

**Mid-wave CRITICAL rule:** any CRITICAL discovered *during* Wave N implementation is a
**Wave N gate blocker**. The discovering seat immediately creates a **provisional row +
xfail pin** via the deputy-write path (§6f covers new-row creation for mid-wave
CRITICALs in *any* module, including cross-cutting); the coordinator ratifies on return.
The gate counts pins (the acceptance bars require "no open/provisional Wave-N CRITICAL
pin remains"), so a provisional CRITICAL blocks the gate even before reconciliation. It
cannot be deferred to Wave N+1 without explicit user-principal authorization.

## 6. Role distribution & coordination safety

### 6a. Ownership matrix

| Concern | **Coordinator** | **Director** (per pair) | **Operator** (per pair) |
|---|---|---|---|
| Inventory artifact (severity/wave/lane/priority cols) | **OWNS — primary writer** | deputy-writes own-lane status + provisional CRITICAL rows when coordinator offline (§6f) | reads slice |
| Defect status reconcile | **reconciles** at §6f triggers | advances own-lane rows (deputy) | **reports** via `verification-report` |
| Per-defect brief (R-BRIEF) + `priority` | transcribes priority to inventory | **OWNS** brief + sets priority | — |
| The fix (production code) | **never** | implements *or* dispatches (own lane) | — |
| Test-only xfail pins + docs/inventory + `logs/` | **MAY commit** (from workflows) | may pin in-lane | may pin in-lane |
| Independent verification (impl ≠ verifier) | gates wave on the GO artifact | — | **OWNS**; releases the lock on GO (§6b) |
| Cross-lane / cross-cutting co-sign (Rule #23) | routes & tracks | **OWNS** (signs other lane) | — |
| Doc-truth re-sync (ARCHITECTURE/cross) | **OWNS** | lane docs | lane doc-sync |
| Wave gate + sequencing | **OWNS** (SLA + escalation, §6f) | — | feeds verification |
| Discovery + per-wave verification workflows | **OWNS** (read-only fan-out) | — | — |
| Push (user-gated) | executes on user auth | decides/escalates via coordinator | — |

**Coordinator code scope:** read-only on production code; **never authors a
behavior-changing fix.** May commit **test-only artifacts (xfail pins, fixtures, stubs),
inventory, `logs/`, and docs** — none carry production logic. Every fix is authored in-lane.

### 6b. Lane partition + git-native shared-module lock

- **Pair-A lane (image/identity):** `quality_max.py`, PuLID/LoRA injectors,
  `face_validator_gate`, `identity_gate`, `coherence_analyzer`, over-cook, secondary-char.
- **Pair-B lane (video/assembly/audio):** `phase_c_*`, `lip_sync.py`, `audio/*`,
  `motion_gate`, `cinema/checkpoint`, dialogue.
- **Cross-cutting (collision risk):** `auto_approve.py`, `core.py` (budget),
  `web_server.py`, `cinema/context.py`. (`workflow_selector.py` largely closed by
  `bf1034a` — re-verify only.)

**Lock claim protocol (atomic, prevention not recovery, coordinator-independent):**
1. The claiming seat runs **`git fetch`**, then checks for
   `coordination/locks/W<n>-<module>.lock`.
2. If absent, it **commits the lock file** (`seat·wave·ts·defect-id`) and **pushes it
   immediately**.
3. If the push is **rejected** (a peer claimed first), the seat **lost** — it abandons,
   does **not** implement. **Implementation (own commit or dispatched subagent) begins
   ONLY after the lock push succeeds** — so a loser never has an in-flight fix. The
   lock-push is the atomic claim point *before any code work*.

**Deadlock avoidance (ordered acquisition):** a seat needing more than one cross-cutting
module acquires the locks in a **fixed global order — lexicographic by module path** —
and holds none while waiting. This eliminates the circular wait (no
A-holds-`auto_approve`-wants-`core` / B-holds-`core`-wants-`auto_approve`).

**Lock release (coordinator-independent):** the **operator deletes the lock file in the
same commit as their `verification-report` GO** — the lock releases on `verified`, not on
the fix-commit. On FAIL the lock is retained and the fixing seat reworks. Once the lock
file is deleted, the module is **eligible to be claimed** by the next seat (re-run the
claim protocol) — **no coordinator grant needed.**

**Cross-file commit co-sign scope:** any commit touching **more than one lane**, or a
**cross-cutting module + a lane file**, requires co-sign from **every affected lane
director**.

**Wave-1 pre-sequencing:** the coordinator records, in the inventory header at Wave-1
open, a **first-mover** for each contested cross-cutting module
(`auto_approve.py`/`core.py`/`web_server.py`) — defaulting to the pair that already
holds an `open` xfail in that module — so Day-1 needs no ad-hoc decision.

### 6c. Per-defect lifecycle (the safe handoff chain)

```
Wave opens: row available
 ─▶ [cross-cutting?] claimant runs the §6b claim protocol (fetch → commit+push lock; loser abandons)
 ─▶ Director writes R-BRIEF (full-shape refs) + sets priority
 ─▶ [CRITICAL cross-lane/cross-cutting?] other Director Tier-A co-signs THE R-BRIEF (full change-set scope)
        — BEFORE any code lands, regardless of whether the director implements directly or dispatches
 ─▶ Implementer (director directly for small fixes, else dispatched subagent): TDD xfail→fix→green ▶ ONE pathspec commit
 ─▶ Operator: independent diff verify (impl≠verifier) ▶ verification-report GO/NITS/FAIL; on GO, deletes the lock file in the SAME commit
 ─▶ Status advance: coordinator reconciles (§6f) — or the lane deputy-writes its own-lane row when coordinator offline
 ─▶ Wave end: coordinator (or acting-coordinator, §6f) runs verify-workflow + ci_smoke ▶ gate next wave
```

**Tier-A co-sign gates the R-BRIEF, not the lock:** the lock merely *reserves* the file
so brief work isn't wasted; the co-sign happens *after* the brief exists, so the
co-signer sees the **full change-set scope**, never a blank check. **No CRITICAL
cross-cutting code lands before Tier-A co-sign — whether authored by a director's own
commit or a dispatched implementer.** Non-critical cross-lane items may use Tier-B
(48h proceed-if-no-objection).

**Director-as-implementer:** a director may implement a small fix directly or dispatch a
subagent (dispatch required per R-ORCH at ≥5 subtasks or ≥800 LOC). Either way the
**operator is the independent verifier**, so impl≠verifier holds in both modes.

### 6d. The five safety guarantees (correct under adversarial timing)

1. **One writer per file** — lane separation + git-native locks where the **lock-push is
   the atomic claim before any code work** (loser never starts) + ordered acquisition
   (no deadlock). Holds with the coordinator offline.
2. **No inventory write-race** — coordinator is primary writer; in-lane status uses the
   §6f deputy path scoped by `lane-owner` (own rows only).
3. **Every fix verified by a non-author** — operator GO artifact per item; the gate
   checks for it and for "no open/provisional Wave-N pin."
4. **Cross-lane changes dual-signed** — Rule #23; CRITICAL cross-cutting code never lands
   before Tier-A co-sign (any author); cross-file commits co-signed by all affected lanes.
5. **Waves don't bleed** — per-wave gate (every row `verified` + GO + xfail green + no
   open/provisional Wave-N pin + `ci_smoke` green + coverage/E2E threshold).

### 6e. Unified teamwork — the integration spine

The inventory is the shared burn-down. Pairs work **independently within a wave** and
**converge at the wave-boundary gate**. The coordinator is the integration point and
surfaces every consequential decision (push, pod-spend, scope, mid-wave CRITICALs) to
the **user-principal**, top of the authority chain (`user > git commits > mailbox sent/ >
STATE.md > default`).

### 6f. Coordinator-absence resilience (the on-demand reality)

The coordinator is on-demand; the protocol must not stall on its absence:

- **Reconcile triggers:** the coordinator reconciles mailbox→inventory at (a) each
  coordinator session-start, (b) every wave-boundary gate, (c) a director's explicit gate
  request. Between reconciles the inventory is a batch view (§2).
- **Deputy-write path (scope):** when no coordinator is live, a pair may (a) **advance its
  own-lane row status** (open→fixed→verified), and (b) **create a provisional row + xfail
  pin for any mid-wave CRITICAL** (including cross-cutting), flagged `provisional`, for
  coordinator ratification on return. Both are pathspec-scoped; (a) is limited to rows
  whose `lane-owner` is that pair. Lock files release per §6b (operator GO commit),
  independent of the coordinator.
- **Wave-gate SLA + trip-wire:** SLA = **24h default** (user-adjustable; recorded in the
  inventory header). A director's gate-request is the formal trigger: the moment it is
  posted and unserviced, the gate is **formally blocked → the pod goes OFF immediately**
  (pod-off does not wait on the 24h). If no coordinator is reachable within the SLA, the
  gate decision **escalates to the user-principal**.
- **Acting-coordinator:** past the SLA with no coordinator, the user-principal may
  designate a director as **acting-coordinator** (recorded in mailbox) — the *only* path
  by which a non-coordinator seat advances cross-cutting rows or opens the next wave. It
  requires explicit user authorization, preserving the authority chain.

## 7. The E2E lock & the concrete "done" definition

- **Tier 1 (CI, no pod, no $):** drive `CinemaPipeline(pid, headless=True)` through *all*
  phases with **stubbed providers** (fixture ComfyUI / video-API / audio / LLM). **Stub
  contract:** each stub must be configurable to return *both* a happy-path *and* a
  gate-fail response, and the suite must include **≥1 gate-fail assertion per gate**
  (proving the gate fires). Stub ownership: the lane that covers the provider. The
  coordinator runs the **stub-fidelity review at two points** — (1) a **contract/design
  review** of the stub specs *before* Wave-4 stub implementation, and (2) an **artifact
  review** of the finished suite before it counts toward done; stubs authored earlier
  (e.g. a Wave-2 coverage stub) are re-checked at the artifact review for drift.
- **Tier 2 (milestone, pod-gated):** a real burn → photoreal video w/ synced audio,
  scored against **pre-committed thresholds**:
  - **identity arc ≥ max(0.80, baseline_arc + 0.05)** (0.80 anchored to GO history —
    Design-D man 0.870, ADR-025 portrait ON 0.8779 — and never below baseline+0.05);
  - **lip-sync offset ≤ 2 frames** vs the audio track;
  - **no over-cook** per the realism checklist (qualitative + structural over-cook checks).
  The **baseline render** (current-default arc/lip-sync/frame-samples) is committed to
  `logs/` as a **Wave-2 exit deliverable**, so "improvement vs baseline" is defined before
  Wave 3 runs.

**"Runs as intended & bug-free" = done when, and only when:**
1. inventory drained — 0 open CRITICAL/MAJOR; MEDIUMs explicitly triaged;
2. all defect-xfails flipped green;
3. critical-path coverage landed (HTTP mutators, audio DSP, resume/checkpoint);
4. **Tier-1 E2E green in CI** (stub-fidelity reviewed, both points);
5. **one Tier-2 real render passing the pre-committed thresholds**;
6. **Wave-3 levers each attempted** with result recorded (GO or DEFERRED) — capability is
   best-effort; a DEFERRED lever does **not** block "done."

## 8. Risks & guards

- **Re-drift on the live tree** → fix-on-touch; coordinator re-syncs `ARCHITECTURE.md`
  (as in Session-6 for the quality_max/phase_c anchors).
- **Pod cost/availability** → Waves 3 + Tier-2 pod-gated; **pod OFF on any blocked gate**
  (§6f trip-wire); surface spend to the principal before each burn.
- **Measurement non-determinism** → already fixed (§5 note); re-verified in Wave 1.
- **Boiling the ocean** → discovery bounded to §3 subsystems; cold code excluded; MINORs
  deferred; already-closed modules skipped via the seed-migration HEAD check.
- **False positives** → adversarial refute pass (§3) + verification workflows at gates.
- **Concurrency hazards** → per-seat `GIT_INDEX_FILE`; subagents prefix git with
  `env -u GIT_INDEX_FILE`; explicit-pathspec commits; one commit per defect; git-native
  locks with push-first claim + ordered acquisition (§6b); deputy own-rows-only (§6f).
- **Coordinator-as-bottleneck** → git-native locks + deputy writes + provisional rows +
  SLA/escalation + acting-coordinator (§6f) keep the coordinator out of the hot path.

## 9. Out of scope (YAGNI)

- Refactors not required to close a defect or land a wave's coverage.
- Auditing cold/rarely-executed code paths.
- A permanent always-on pod or a per-commit real-render gate (Tier-2 is milestone-gated).
- New product features beyond PROGRAM-MANUAL intent.
- The unrelated `operator2 cursor_orphan` advisory (separate lane item).

## 10. Execution prerequisites (resolved)

- **Inventory bootstrap:** Phase 0 creates `docs/REMEDIATION-INVENTORY.md`; existing xfail
  pins are seed-migrated (HEAD-checked, status-vocabulary per §3) **before** discovery
  fires — a Phase-0 precondition owned by the coordinator.
- **Campaign constants in the inventory header:** wave-gate SLA (default 24h) and the
  Wave-1 cross-cutting first-mover sequence (§6b).
- **Cross-cutting lock assignment:** runtime, git-native (§6b), not pre-frozen.
- **Capability baseline:** committed to `logs/` as a Wave-2 exit deliverable (§7).
- **Pod authorization:** Waves 3 / Tier-2 do not begin until the user-principal authorizes
  the pod spend (authority chain, §6e).
- **Coordinator availability:** wave gates carry a 24h SLA + user-principal escalation +
  acting-coordinator path (§6f).
