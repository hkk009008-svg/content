# Program Hardening Roadmap — "Runs as Intended, Bug-Free" — Design Spec

*Date: 2026-06-14 · Author: coordinator seat (Session-6), brainstormed with the
user-principal · Status: design approved; v6 after **5 adversarial spec-review rounds**
(`wf_c37fb3eb-823`, `wf_7b0a23a9-0cd`, `wf_8d1be397-9b0`, `wf_44be214b-c7e`,
`wf_806e5d71-8f7`). All design-level blocking closed; operational residuals explicitly
delegated to the implementation plan (§11). Ready for user review → writing-plans.*

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
committed; every confirmed defect has an inventory row + a **`strict=True`** test-only
xfail pin whose reason is prefixed **`W<n>:<SEVERITY>:<id>`** (so the wave gate filters
pins by wave mechanically, and a fixed-but-unremoved pin xpasses → CI red); rejects
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
| **2 — Silent-degradation + coverage** | swallow-and-continue holes; tests for HTTP mutators, audio DSP, resume/checkpoint; **+ commit the capability baseline** (§7) | Pair-A: image/identity · Pair-B: video/audio/assembly | every MAJOR row `verified` w/ operator GO; **coverage landed** (≥1 dedicated test for the `api_serve_file` guard + each destructive/state endpoint — `api_delete_project`, `api_pause`/`resume`, `api_restart_shot`, `api_proceed_assembly` — per the TEST-COVERAGE doc; `audio/effects.apply_voice_effect` + `audio/voiceover.get_voice_direction` 0→covered; resume/checkpoint restore path); baseline render in `logs/`; no open Wave-2 pin remains; green | ~10–15 items, 3–4 sessions |
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

**AMENDMENT (ADR-027, user-ratified 2026-06-15) — the gate must EXECUTE the oracle, and every wave-close needs a product oracle.** Root cause + evidence: ADR-027 + `logs/discovery-wf_26a5abf2-3bb.json`.
- The wave gate's authority is the **EXECUTED pin suite** (`pytest --runxfail`, XPASS-clean), NOT the inventory `status` string. `wave_gate_check.py` reading `status` is **process-state, not proof** (it executes zero tests); a row counts as gate-cleared only when its pin actually flips under execution **and** an independent operator GO exists (impl≠verifier). [FIX-1, routed to a director — changes gate PASS/FAIL; will re-grade the current Wave-1 "MET" honestly.]
- From **Wave-2 onward**, a wave does NOT close without **≥1 committed product-oracle artifact** in `logs/` (ArcFace arc score + lip-sync offset on a baseline render, via a committed R-MEASURE script). This elevates the §7 "baseline render in logs/" exit deliverable into a **HARD gate condition** — a wave cannot green on structural rows alone. [FIX-5.]
- Rows with **no behavioral oracle** (test-infeasible) are **`attested`**, not `verified`, and need an explicit user-principal exemption token to pass a gate.
- Two gaps remain UNCLOSED (recorded, not hidden): operator-GO impl≠verifier is not yet gate-enforced; unregistered defects cannot be caught by a gate that reads only registered rows.

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
inventory, `logs/`, and docs** — none carry production logic; all coordinator test
commits are scoped to **test files only** (`tests/`, `conftest.py`), never production
modules. Every fix is authored in-lane.

**Canonical pin-writer (no three-writer race):** exactly one seat authors any given
xfail pin. In **Phase 0** the coordinator is the *sole* pin author (pins arrive as the
discovery-workflow batch). In **waves**, a *new* pin for a mid-wave defect is authored by
the **lane seat** for a pure-lane defect, or via the lock + provisional-row protocol
(§6b/§6f) for a cross-cutting defect.

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
   lock-push is the atomic claim point *before any code work*. A loser takes the next
   available row in its lane; if the lost row was the lane's last, it waits for the lock
   release and re-claims — it does not silently abandon the defect (the gate would block).

**Deadlock avoidance (ordered acquisition):** a seat needing more than one cross-cutting
module acquires the locks in a **fixed global order — lexicographic by repo-relative POSIX
path** (`auto_approve.py` < `cinema/context.py` < `core.py` < `web_server.py`) — and
holds none while waiting. This eliminates the circular wait (no
A-holds-`auto_approve`-wants-`core` / B-holds-`core`-wants-`auto_approve`).

**Lock release (coordinator-independent):** the **operator deletes the lock file in the
same commit as their `verification-report` GO** — the lock releases on `verified`, not on
the fix-commit. On FAIL the lock is retained and the fixing seat reworks. Once the lock
file is deleted, the module is **eligible to be claimed** by the next seat (re-run the
claim protocol) — **no coordinator grant needed.** **FAIL-rework cap (anti-hostage):**
after **3 consecutive FAIL verdicts** on one defect the holder must **release the lock**
and re-queue/split the defect (or escalate to the coordinator / acting-coordinator), so a
hard defect cannot hold a contested module (e.g. `auto_approve.py`, 6+ pinned xfails)
hostage or stall the wave gate indefinitely. A lock is thus deleted in **exactly two
cases** — (normal) the operator's GO commit, or (anti-hostage) the holder after the
3-FAIL cap; no other actor deletes a lock.

**Cross-cutting / cross-file co-sign scope:** any commit touching a **cross-cutting
module (even in isolation)**, **more than one lane**, or a cross-cutting module + a lane
file, requires co-sign from **every affected lane director** — Tier-A (pre-commit, §6c)
if CRITICAL, else Tier-B (a mailbox heads-up event, 48h proceed-if-no-objection).

**Wave-1 pre-sequencing:** the coordinator records, in the inventory header at Wave-1
open, a **first-mover** for each contested cross-cutting module
(`auto_approve.py`/`core.py`/`web_server.py`) — defaulting to the pair that already
holds an `open` xfail in that module — so Day-1 needs no ad-hoc decision. Ties (both pairs
hold open xfails in the module) break to the pair with **more** open pins there, then to
**Pair-A** by convention; the resolved sequence is recorded in the inventory header.

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

**NITS path (no unverified-fix escape):** a `NITS` verdict means the fixing seat addresses
the nits and the **operator re-verifies the nit-fix diff before issuing GO** — never a
self-upgrade NITS→GO without reading the new diff, so guarantee #3 covers nit-fixes too.
**CRITICAL cross-cutting commit gate:** the Tier-A co-sign `verification-report` **must be
in the mailbox before the fix commit lands** — this **overrides the async-OK convenience**
and binds regardless of implementer identity (a director-as-implementer may **not**
self-commit a CRITICAL cross-cutting fix ahead of the co-sign). Because Tier-A approves
**scope at brief-time**, the operator's verification of a CRITICAL cross-cutting fix
additionally confirms the **landed diff matches the co-signed brief scope** — a scope
deviation is a FAIL (this catches brief-vs-diff drift).

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
  own-lane row status** (open→`fixed`; the `verified` transition still requires the
  operator's GO `verification-report` — the deputy only **transcribes** an existing GO into
  the row when no coordinator is live, it never self-verifies), and (b) **create a provisional row + xfail
  pin for any mid-wave CRITICAL.** For a **cross-cutting** module the discovering seat
  **first claims the §6b lock** (push-first): the lock is the **dedup point** — only the
  lock-winner creates the provisional row, so two pairs that independently find the same
  `file:line` cannot create dual racing rows. Provisional rows are keyed by `file:line`
  (a second for the same `file:line` is disallowed); the row is flagged `provisional` for
  coordinator ratification on return (which also corrects `lane-owner`). (a) is
  pathspec-scoped and limited to rows whose `lane-owner` is that pair. Lock files release
  per §6b (operator GO commit), independent of the coordinator.
- **Write-permission rule (single decision):** the coordinator may write any row anytime; a
  pair may write a row **only** when no coordinator is live AND either it advances status on
  a row whose `lane-owner` is that pair, or it creates a provisional mid-wave CRITICAL row
  while holding the §6b lock (cross-cutting) or in its own lane. **Lane classification is by
  the §6b module list, not seat judgment** — a cross-cutting module is always cross-cutting,
  so its provisional rows and fixes always route through the lock; a seat may not reclassify
  it as own-lane to bypass the lock.
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
  review** of the finished suite before it counts toward done. The coordinator **issues
  the stub-contract spec before Wave 2 opens** (not just before Wave 4) so Wave-2 stub
  authors target it; earlier stubs are still re-checked for drift at the artifact review.
- **Tier 2 (milestone, pod-gated):** a real burn → photoreal video w/ synced audio,
  scored against **pre-committed thresholds**:
  - **identity arc ≥ max(0.80, baseline_arc + 0.05)** (0.80 anchored to GO history —
    Design-D man 0.870, ADR-025 portrait ON 0.8779 — and never below baseline+0.05);
  - **lip-sync offset ≤ 2 frames** vs the audio track, measured by a committed script
    (`scripts/measure_lipsync_offset.py`, authored as a **Wave-2 deliverable** so the
    baseline can use it) per R-MEASURE;
  - **no over-cook**, per this inline checklist (recorded with the render in `logs/`):
    (a) no crystalline/metallic or plastic-skin hyper-detail on inspection; (b) hires-fix
    scale and sampler steps at or below the production defaults (the structural over-cook
    drivers — hires-901 + 28-step sampler per the realism memo); (c) no hue/saturation clipping.
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
- **Lock directory:** create `coordination/locks/` with a tracked `.gitkeep` as a Phase-0
  prerequisite (git does not track empty dirs; the commit-push lock needs the dir present).
- **Cross-cutting lock assignment:** lock *acquisition* is runtime/git-native (§6b); the
  Wave-1 *first-mover priority* is coordinator-set in the inventory header at wave-open
  (directors check the header before racing).
- **Capability baseline:** committed to `logs/` as a Wave-2 exit deliverable (§7).
- **Pod authorization:** Waves 3 / Tier-2 do not begin until the user-principal authorizes
  the pod spend (authority chain, §6e).
- **Coordinator availability:** wave gates carry a 24h SLA + user-principal escalation +
  acting-coordinator path (§6f).

## 11. Decisions delegated to the implementation plan (writing-plans)

These are **execution constants, not architecture** — deliberately set in the
implementation plan (the next artifact), not frozen here, so the design stays at the right
altitude. Each was *surfaced* (not missed) by the 5-round spec review; the safety model
above does not depend on their specific values, only that the plan fixes them:

- **Discovery refute-pass mechanics (§3):** number of refuter agents (≥2), their structured
  verdict artifact, and the confirmed/rejected criterion (e.g. both refuters fail to disprove).
- **`scripts/measure_lipsync_offset.py` (§7):** owner (Pair-B lane), inputs/outputs, validation
  vs human inspection, disagreement-handling. Authored at Wave 2.
- **Over-cook objectivity (§7):** whether checklist items (a)/(c) get a quantitative proxy
  (saturation-histogram / detail-frequency metric) or stay inspection-based with two-seat sign-off.
- **`conftest.py` policy (§6a/§7):** whether coordinator-authored fixtures/stubs that can alter
  test-time behavior need Tier-A co-sign, or are test-only by default.
- **Pod-off executor (§6f):** which seat issues the pod-stop on a blocked gate when the
  coordinator is absent, and how it signals the user.
- **FAIL-cap counting (§6b):** whether a NITS verdict counts toward the 3-FAIL anti-hostage cap.
- **Mid-wave CRITICAL in a module whose lock is held for a *different* `file:line` (§6b/§6f):**
  the row/pin is recorded immediately (dedup is per `file:line`; lock is per module) while the
  *fix* queues behind the lock — the plan specifies this record-without-lock path.
- **MEDIUM-as-gate-item (§4/§5):** add "all pending MEDIUMs wave-assigned" to a wave acceptance
  bar so MEDIUMs cannot float past the done-definition.
- **Determinism re-verification (§5):** the exact command + artifact for the Wave-1
  pre-closed-determinism re-check.
