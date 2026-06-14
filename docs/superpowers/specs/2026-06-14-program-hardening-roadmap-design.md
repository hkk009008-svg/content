# Program Hardening Roadmap — "Runs as Intended, Bug-Free" — Design Spec

*Date: 2026-06-14 · Author: coordinator seat (Session-6), brainstormed with the
user-principal · Status: design approved; revised after spec-review panel
(`wf_c37fb3eb-823`) closed 6 blocking + high-value advisory findings.*

## 0. Locked decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Success definition | **(D)** all three, sequenced: robustness → capability → verified E2E |
| Discovery scope | **(B)** bounded discovery of high-risk subsystems, then remediate |
| Execution shape | **Approach 2** — discovery spine + severity waves across parallel lanes |
| Role distribution | git-native safe distribution; survives coordinator absence (see §6) |
| Deliverable | sequenced multi-session roadmap the 4-seat team executes, coordinator-integrated |

## 1. Problem & intent

**"Runs as intended"** = the program realizes `docs/PROGRAM-MANUAL.md` §1–2: a
script/idea becomes finished, photorealistic cinematic video with synced audio,
operated to full capability.

**"Bug-free"** = no crashes, no *silent degradation* (wrong result with no
signal), every gate fails safe, and the end-to-end path is provably reproducible.

**Why a campaign, not a patch:** the program is already clean on surface hygiene
(2 production `TODO`s, `ci_smoke` green, ~2,400 tests passing). The real surface is
concentrated and partly already under repair by the live 4-seat team:

- **~28 pinned defects** (xfail), genuine code defects clustering in **NaN/inf-gate
  bypasses** and **silent-degradation holes** — the in-flight NaN-gate epic.
- **Coverage gaps** (`docs/TEST-COVERAGE-ANALYSIS-2026-06-14.md`, coordinator-verified
  via `wf_bf7078e7-4ab`): HTTP surface ~46/66 untested, audio DSP zero-tested,
  orchestration mutation paths.
- **Structural quality**: max-wide over-cook, secondary-char binding, `has_character`
  LoRA-only hole.
- **E2E-verification gap**: "runs as intended" is proven only by manual pod burns.

## 2. Architecture — one inventory, drained in waves

A single living artifact, **`docs/REMEDIATION-INVENTORY.md`**, is the spine and
source of truth. Discovery populates it; waves drain it; the E2E lock freezes it
against regression.

**Inventory row schema:**

```
id · subsystem · file:line · severity · priority · fail-mode · repro · xfail-pin ·
lane-owner · shared-lock · wave · status(open|fixing|fixed|verified) · verifier · notes
```

- **`priority`** orders items *within* a (lane, wave); the owning director sets it
  in the brief, the coordinator records it. (Closes the intra-wave ordering gap.)
- **`shared-lock`** = the git lock-file path when the row touches a cross-cutting
  module (see §6b). Empty for pure-lane rows.

The inventory is a **batch-updated burn-down view, not real-time**: status reflects
the **last reconciliation** (§6f), not fix-time. It answers "how many CRITICALs
remain, in which lane, blocking which wave" as of the last reconcile.

## 3. Phase 0 — the discovery bug-hunt

**Precondition (coordinator, committed before the hunt fires):** migrate the
existing xfail pins into the inventory as **seed rows**, *after* checking each
against current HEAD — any module already fixed+verified-closed (e.g.
`workflow_selector.py`, closed by `bf1034a`) is recorded as `verified`, **not**
re-hunted. Seed migration is a Phase-0 *precondition*, not an output.

A coordinator-owned **discovery Workflow** then fans adversarial agents across
*high-risk subsystems only*, each probing **fail-open paths**:

- **Gates** — `auto_approve`, `face_validator_gate`, `motion_gate`, `identity_gate`,
  `coherence_analyzer`
- **Money** — `core.py` budget, cost-estimation, lip-sync pricing
- **Silent-degradation I/O** — image/video decode, API-error swallow, ffmpeg/ffprobe
- **HTTP mutators** — `web_server.py` destructive / state-mutating endpoints
- **Resume/checkpoint** — state reconstruction on restart
- **Identity/continuity** — PuLID/LoRA injection, secondary-char binding

**Finding-record schema (each discovery agent emits):**
`{subsystem, file:line, fail-mode, reproducer, severity-guess, refuter-verdict}`.
Each candidate gets an **adversarial refute pass** (independent agents try to prove
it *isn't* real — the discipline that caught this session's path-traversal false
alarm). **Confirmed** findings → the coordinator populates an inventory row from
the record. **Rejected** findings are recorded (in the inventory's `notes` as
`REJECTED:<reason>`), never silently dropped.

**xfail-pin authorship (resolves the coordinator/code contradiction):** the
discovery workflow *emits the xfail pin as a test-only artifact* (a `pytest.mark`,
no production logic). The coordinator commits the discovery batch (inventory rows +
test-only pins) — this is within the coordinator's narrowed code scope (§6a). The
*fix* that flips a pin green is always authored in-lane, never by the coordinator.

**Acceptance for Phase 0:** seed migration committed; discovery run; every confirmed
defect has an inventory row + test-only xfail pin; every rejected finding recorded;
`ci_smoke` green (pins are xfail, not red).

## 4. Severity taxonomy (this is how the (D) ordering falls out automatically)

| Severity | Definition | Routes to |
|---|---|---|
| **CRITICAL** | crash · state/data corruption · money-loss · gate-bypass shipping a bad take | Wave 1 |
| **MAJOR** | silent degradation (wrong result, *no signal*) · critical-path coverage hole | Wave 2 |
| **MEDIUM** | recoverable degradation · poll/backoff inefficiency · partial result | Wave 2/3 (triaged) |
| **MINOR** | cosmetic · observability · dead code | deferred / batched (YAGNI) |

Draining the inventory top-down by severity yields the robustness→capability
ordering automatically: the CRITICALs *are* the robustness work.

## 5. The four remediation waves

Acceptance bars name **checkable artifacts** (not vague "verified"):

| Wave | Content | Lanes | Acceptance bar (coordinator-checkable) | Rough estimate* |
|---|---|---|---|---|
| **1 — Critical robustness** | NaN/inf-gate family, budget bypass, gate-bypass, crash paths | both pairs, by file proximity | every CRITICAL row `verified`; its xfail flipped green; an **operator `verification-report` (GO)** in mailbox per item; `ci_smoke` green | ~8–12 items, 2–3 sessions |
| **2 — Silent-degradation + coverage** | swallow-and-continue holes; tests for HTTP mutators, audio DSP, resume/checkpoint; **+ establish the capability baseline** (§7) | Pair-A: image/identity · Pair-B: video/audio/assembly | every MAJOR row `verified` w/ operator GO; coverage landed; baseline render committed to `logs/`; green | ~10–15 items, 3–4 sessions |
| **3 — Capability levers** *(pod-gated, best-effort)* | over-cook, secondary-char binding, dialogue/lip-sync quality | Pair-A (realism/identity) · Pair-B (dialogue/audio) | each lever **attempted + result recorded** (GO → improvement in `logs/`; HOLD/inconclusive → row marked `DEFERRED` with the R-MEASURE artifact). A HOLD does **not** block Wave 4. | 2–3 pod burns |
| **4 — E2E lock** | Tier-1 CI harness + one Tier-2 real render (§7) | coordinator-orchestrated | Tier-1 green in CI (stub-fidelity reviewed); one Tier-2 render passes §7 thresholds | 2–3 sessions |

*Estimates are rough scope signals for the plan author, not commitments.

**Determinism item — PRE-CLOSED:** the OpenCV thread-race determinism fix is
already merged (`cv2.setNumThreads(1)` + deterministic tie-break, `ARCHITECTURE.md`
§11.1, 30/30 byte-identical). Wave 1 carries only a **re-verification check** (confirm
the existing determinism test still green), **not** a fresh fix; Phase 0 must not
re-discover it.

**Mid-wave CRITICAL rule:** any CRITICAL discovered *during* Wave N implementation
is automatically a **Wave N gate blocker**. The discovering seat adds a provisional
inventory row + xfail pin immediately via the deputy-write path (§6f); the
coordinator ratifies on return. It cannot be deferred to Wave N+1 without explicit
user-principal authorization. (Closes the "loose xfail pin invisible to the gate"
gap — the gate counts pins, not just reconciled rows: a Wave-N pin that is not yet
`verified` blocks the gate.)

## 6. Role distribution & coordination safety

### 6a. Ownership matrix

| Concern | **Coordinator** | **Director** (per pair) | **Operator** (per pair) |
|---|---|---|---|
| Inventory artifact (severity/wave/lane/priority cols) | **OWNS — primary writer** | reads slice; deputy-writes own-lane status when coordinator offline (§6f) | reads slice |
| Defect status reconcile | **reconciles** at the triggers in §6f | advances own-lane rows (deputy) | **reports** via `verification-report` |
| Per-defect brief (R-BRIEF) + intra-lane `priority` | — | **OWNS** (own lane) | — |
| The fix (production code) | **never** | implements *or* dispatches implementer (own lane) | — |
| Test-only xfail pins + docs/inventory | **MAY commit** (from workflows) | may pin in-lane | may pin in-lane |
| Independent verification (impl ≠ verifier) | gates wave on the GO artifact | — | **OWNS** (own lane) |
| Cross-lane / cross-cutting co-sign (Rule #23) | routes & tracks | **OWNS** (signs other lane) | — |
| Doc-truth re-sync (ARCHITECTURE/cross) | **OWNS** | lane docs | lane doc-sync |
| Wave acceptance gate + sequencing | **OWNS** (SLA + escalation, §6f) | — | feeds verification |
| Discovery + per-wave verification workflows | **OWNS** (read-only fan-out) | — | — |
| Push (user-gated) | executes on user auth | decides/escalates via coordinator | — |

**Coordinator code scope (narrowed, resolves the contradiction):** the coordinator
is **read-only on production code and never authors a behavior-changing fix.** It
*may* commit **test-only artifacts (xfail pins, fixtures), inventory, and docs** —
none carry production logic. Every fix is authored in-lane.

### 6b. Lane partition + git-native shared-module lock

- **Pair-A lane (image/identity):** `quality_max.py`, PuLID/LoRA injectors,
  `face_validator_gate`, `identity_gate`, `coherence_analyzer`, over-cook, secondary-char.
- **Pair-B lane (video/assembly/audio):** `phase_c_*`, `lip_sync.py`, `audio/*`,
  `motion_gate`, `cinema/checkpoint`, dialogue.
- **Cross-cutting modules (collision risk):** `auto_approve.py`, `core.py` (budget),
  `web_server.py`, `cinema/context.py`. (`workflow_selector.py` is largely closed by
  `bf1034a` — re-verify only.)

**Lock protocol (git-native — prevention, not recovery; survives coordinator
absence):**
1. A seat claims a shared-module by committing an empty marker
   `coordination/locks/W<n>-<module>.lock` containing `seat · wave · ts · defect-id`.
   **First commit wins** (git tiebreaker is now *prevention*: the loser sees the
   lock file before dispatching and does not start).
2. The other lane director **Rule #23 co-signs** (mailbox `verification-report`)
   before any implementation begins.
3. **Both lanes need the same cross-cutting file in the same wave** → they serialize:
   the second lock is granted only after the first holder's row is `verified` and the
   first lock released (lock file deleted in the verifying commit).
4. The coordinator audits/overrides locks but **prevention does not depend on it.**

**Cross-file commit co-sign scope:** any commit touching files in **more than one
lane**, or a **cross-cutting module + a lane file**, requires co-sign from **every
affected lane director** — not just "the other director" generically. This closes
the "lane file changed incidentally under a cross-cutting lock without that lane's
review" blind spot.

### 6c. Per-defect lifecycle (the safe handoff chain)

```
Discovery ─▶ Coordinator: seed-migrate + write inventory row (severity·lane·wave·priority) + commit test-only xfail pin
          ─▶ Wave opens: row available; shared-cutting module ⇒ claimant commits coordination/locks/ lock (first wins)
          ─▶ Director writes R-BRIEF (full-shape refs); IMPLEMENTS directly (small) or DISPATCHES an implementer subagent
          ─▶ [cross-lane/cross-cutting?] other Director co-signs FIRST — Tier-A (pre-commit) for any CRITICAL; Tier-B (48h) only for non-critical
          ─▶ Implementer: TDD — xfail reproduces defect ▶ fix ▶ flip green ▶ ONE pathspec commit (releases lock if held)
          ─▶ Operator: independent diff verify (impl≠verifier) ─▶ mailbox verification-report (GO/NITS/FAIL)
          ─▶ Status advance: coordinator reconciles (§6f) — or the lane deputy-writes its own row open→fixed→verified when coordinator offline
          ─▶ Wave end: coordinator runs verify-workflow + ci_smoke ─▶ gate next wave (SLA/escalation per §6f)
```

**Director-as-implementer:** the director **may** implement a small fix directly OR
dispatch an implementer subagent (dispatch is required per R-ORCH at ≥5 subtasks or
≥800 LOC). Either way the **operator is the independent verifier**, so impl≠verifier
holds in both modes. **CRITICAL cross-lane fixes use Tier-A pre-commit co-sign** —
they never sit in `main` for a 48h Tier-B window.

### 6d. The five safety guarantees (now coordinator-absence-tolerant)

1. **One writer per file** — lane separation + **git-native lock files** (first-commit-
   wins *prevents*, doesn't merely detect). Holds even if the coordinator is offline.
2. **No inventory write-race** — coordinator is primary writer; in-lane status uses the
   §6f deputy path (own-lane rows only, pathspec-scoped) ⇒ no two seats write the same row.
3. **Every fix verified by a non-author** — operator GO artifact per item; the wave
   gate checks for it explicitly.
4. **Cross-lane changes dual-signed** — Rule #23; CRITICALs pre-commit (Tier-A);
   cross-file commits co-signed by *all* affected lanes.
5. **Waves don't bleed** — per-wave gate (every row `verified` + GO artifact + xfail
   green + `ci_smoke` green + coverage/E2E threshold). Loose Wave-N pins block the gate.

### 6e. Unified teamwork — the integration spine

The inventory is the shared burn-down every seat reads. Pairs work **independently
within a wave** and **converge at the wave-boundary gate** (sync at boundaries, not
per-commit). The coordinator is the integration point and surfaces every consequential
decision (push, pod-spend, scope, mid-wave CRITICALs) to the **user-principal**, top
of the authority chain (`user > git commits > mailbox sent/ > STATE.md > default`).

### 6f. Coordinator-absence resilience (the on-demand reality)

The coordinator is on-demand; the team routinely runs for hours without it. The
protocol must not stall on its absence:

- **Status reconcile triggers:** the coordinator reconciles mailbox→inventory at
  (a) each coordinator session-start, (b) every wave-boundary gate, (c) on a director's
  explicit gate request. Between reconciles the inventory is a batch view (§2).
- **Deputy-write path:** when no coordinator is live, a pair **advances its own-lane
  rows** (`open→fixed→verified`) via a pathspec-scoped commit to the inventory (own
  rows only) + a mailbox note; the coordinator reconciles/ratifies on return. This
  keeps within-lane throughput coordinator-independent. Cross-lane rows and the wave
  gate stay coordinator-owned.
- **Locks are git-native (§6b)** so collision-prevention never waits on the coordinator.
- **Wave-gate SLA + escalation:** a wave gate must be serviced within an agreed window
  of a director's request; if no coordinator is reachable, the **gate decision escalates
  to the user-principal** (who is the authority anyway). The **pod is OFF during any
  inter-wave stall** so a blocked gate never burns GPU idle.

## 7. The E2E lock & the concrete "done" definition

Two-tier fix for the "proven only by manual pod burns" gap:

- **Tier 1 (CI, no pod, no $):** drive `CinemaPipeline(pid, headless=True)` through
  *all* phases with **stubbed providers** (fixture ComfyUI / video-API / audio / LLM).
  **Stub-fidelity contract (closes the gameable-green risk):** each stub must be
  configurable to return *both* a happy-path *and* a gate-fail response, and the
  Tier-1 suite must include at least one **gate-fail assertion per gate** (proving the
  gate actually fires, not just that happy-path passes). Stub ownership: the lane that
  covers the provider. The coordinator runs a **stub-fidelity review** before Tier-1
  counts toward "done."
- **Tier 2 (milestone, pod-gated):** a real burn → photoreal video w/ synced audio,
  scored against **pre-committed thresholds** (closes the observer-effect risk):
  - **identity arc ≥ 0.80** (anchored to the program's GO history; e.g. Design-D man
    0.870, ADR-025 portrait ON 0.8779) **or** baseline + 0.05, whichever is higher;
  - **lip-sync offset ≤ 2 frames** vs the audio track;
  - **no over-cook** per the realism checklist (qualitative pass + the structural
    over-cook checks).
  The **baseline render** (current-default arc/lip-sync/frame-samples) is committed to
  `logs/` as a **Wave-2 exit deliverable**, so Tier-2's "improvement vs baseline" is
  defined *before* Wave 3 runs.

**"Runs as intended & bug-free" = done when, and only when:**
1. inventory drained — 0 open CRITICAL/MAJOR; MEDIUMs explicitly triaged;
2. all defect-xfails flipped green;
3. critical-path coverage landed (HTTP mutators, audio DSP, resume/checkpoint);
4. **Tier-1 E2E green in CI** (stub-fidelity reviewed);
5. **one Tier-2 real render passing the pre-committed thresholds**;
6. **Wave-3 levers each attempted** with result recorded (GO or DEFERRED) — capability
   is best-effort, so a DEFERRED lever does **not** block "done."

## 8. Risks & guards

- **Re-drift on the live tree** → fix-on-touch; coordinator re-syncs `ARCHITECTURE.md`
  (as done in Session-6 for the quality_max/phase_c anchors).
- **Pod cost/availability** → Waves 3 + Tier-2 pod-gated; pod OFF during inter-wave
  stalls (§6f); surface spend to the principal before each burn.
- **Measurement non-determinism** → already fixed (§5 determinism note); re-verified in
  Wave 1, never re-discovered.
- **Boiling the ocean** → discovery bounded to §3 subsystems; cold code excluded;
  MINORs deferred; already-closed modules skipped via the seed-migration HEAD check.
- **False positives** → adversarial refute pass (§3) + verification workflows at gates.
- **Concurrency hazards** → per-seat `GIT_INDEX_FILE`; subagents prefix git with
  `env -u GIT_INDEX_FILE`; explicit-pathspec commits; one commit per defect; git-native
  locks (§6b); deputy-write own-rows-only (§6f).
- **Coordinator-as-bottleneck** → git-native locks + deputy status writes + wave-gate
  SLA/escalation (§6f) remove the coordinator from the hot path.

## 9. Out of scope (YAGNI)

- Refactors not required to close a defect or land a wave's coverage.
- Auditing cold/rarely-executed code paths.
- A permanent always-on pod or a per-commit real-render gate (Tier-2 is milestone-gated).
- New product features beyond PROGRAM-MANUAL intent.
- The unrelated `operator2 cursor_orphan` advisory (separate lane item).

## 10. Execution prerequisites (resolved)

- **Inventory bootstrap:** Phase 0 creates `docs/REMEDIATION-INVENTORY.md`; the existing
  xfail pins are seed-migrated (HEAD-checked) **before** discovery fires — a Phase-0
  precondition owned by the coordinator, committed first (§3).
- **Cross-cutting lock assignment:** runtime, git-native (§6b), not pre-frozen here.
- **Capability baseline:** committed to `logs/` as a Wave-2 exit deliverable (§7).
- **Pod authorization:** Waves 3 / Tier-2 do not begin until the user-principal
  authorizes the pod spend (authority chain, §6e).
- **Coordinator availability:** wave gates carry an SLA + user-principal escalation (§6f).
