# Wave-2 Stub-Contract Spec

> **Status:** issued by coordinator (Session-10), 2026-06-15, gating Wave-2 open.
> **Authority:** roadmap design `docs/superpowers/specs/2026-06-14-program-hardening-roadmap-design.md`
> §7 ("the coordinator issues the stub-contract spec before Wave 2 opens … so Wave-2
> stub authors target it") + §6a (ownership matrix). This document is the **contract**
> Wave-2 test authors build to; it is reviewed by the coordinator at two points (§8).
> **Coordinator-authored = a spec, not production code.** It changes no gate outcome.

## 0. Why this exists (the one failure it prevents)

Wave-2 fixes the **silent-degradation family**: a gate that swallows an error, a NaN
that defeats a comparison, a `None` that no-ops a check. The trap is that a test for
such a fix can pass **vacuously** — if the stub never produces the fault, the gate is
never exercised, and a still-broken gate looks green. A green suite then certifies a
dead gate. The whole contract below exists to make that impossible: **every gate must
be driven to FAIL by a stub, and asserted to fire, before the wave counts it done.**

This is the test-layer mirror of the campaign's two recurring bug classes
([[silent_gate_degradation_bug_class]], [[money_loss_gate_source_mismatch_bug_class]]):
the bug is "the gate silently no-ops"; the anti-bug is "the test proves the gate fires."

## 1. The universal stub contract (every provider stub MUST satisfy)

A "provider stub" is any test double standing in for an external/expensive dependency
(image gen, video gen, audio/TTS+lip-sync, LLM, file/HTTP I/O, cost ledger).

1. **Dual-mode by construction.** Each stub is configurable to return **both** a
   happy-path response **and** a gate-fail response — selected per-test, not hardcoded.
   A stub that can only succeed is non-compliant (it can't drive the FAIL assertion).
2. **Fault-injection surface.** Each stub exposes the fault modes its lane's Wave-2 rows
   require (the matrix in §3): `nan`/`inf` numeric returns, `None`/null returns,
   raised exceptions (API error), missing-key / zero-cost returns, stall/timeout, and
   cross-thread access. Faults are **opt-in flags**, default = happy-path.
3. **Determinism.** A stub introduces **no nondeterminism** — no wall-clock, no RNG, no
   thread-order dependence in its own logic (the OpenCV thread-race lesson, ARCHITECTURE
   §11.1). Fault selection is explicit input, never sampled.
4. **No real I/O, no real spend.** Stubs never hit a network, a GPU, a pod, or a paid
   API. Cost stubs record to an **in-memory or `:memory:` SQLite** ledger only.
5. **Observability passthrough.** When a stub injects a fault that the *fixed* code is
   expected to log (WARNING for structural, INFO per-clip — the silent-gate principle),
   the test asserts the log line. A fault that produces no observable signal post-fix is
   itself a finding, not a passing test.

## 2. Provider stubs & lane ownership (§6a: the lane that covers the provider owns its stub)

| Stub | Stands in for | Owner lane | Primary Wave-2 consumers |
|------|---------------|------------|--------------------------|
| **ComfyUI graph stub** | image gen + graph wiring (PuLID/LoRA/node injection) | **Pair-A** | has-char-lora-hole, secondary-lora-hole, coherence-silent |
| **Identity/vision stub** | ArcFace embedding, identity-gate LLM (Anthropic vision) | **Pair-A** | identity-nan-arc-bypass, idgate-failopen* |
| **video-API stub** | Kling/Sora/Veo/LTX/Runway motion+perf capture | **Pair-B** | perf-take-meta, perf-phase-no-gate, download paths |
| **audio/lip-sync stub** | TTS, SyncNet scorer, ffmpeg remux, audio-stream probe | **Pair-B** | lipsync-syncnet-nan, lipsync-veto, audioflag-inherit, audio-remux-notimeout |
| **LLM tool-use stub** | planning LLM (scene_decomposer/dialogue_writer/web_research) | **Pair-B** | web_research-uncounted |
| **CostTracker / budget fixture** | the spend ledger + budget gate (`cost_tracker.py`) | **Pair-B** | shot-spent-usd-never-written (C-1), cost-spent-nan-poison, charmgr-cost-fresh-instance, lipsync-postproc-costkey, cost-conn-crossthread-drop |
| **HTTP request stub** | Flask request/`request.json`/FileStorage on mutators | **Pair-B** | http-clearperf-silent200, http-drivingvid-orphan, http-addchar-float-unguarded, http-null-json-body, http-styleboard-false201 |
| **checkpoint fixture** | `pipeline_state.json` read/write + resume | **Pair-B** | ckpt-sceneidx-dead, spent-usd-reset-on-resume, ckpt-* |

\* **`idgate-failopen` is CROSS-LANE** — the module (`phase_c_vision.py`) is a Pair-B
file but the identity-gate policy is a Pair-A call (§6b). Its stub (vision LLM raising an
API error → fail-open-to-PASS) is authored by **Pair-A**, and the fix carries a **Tier-A
co-sign with the Pair-B director** (the fail-open-to-PASS severity may be CRITICAL, a
Pair-A policy call). Coordinator routes that co-sign.

## 3. Fault-injection matrix (what each row's stub must be able to do)

The stub author reads off the fault mode their row needs; the matrix is **complete for
every open Wave-2 row** (verified against the inventory at issue, Session-10 reviewer pass).
If a future Wave-2 row's fault mode is not here, the spec is **re-issued** (§8 point 1).

| Fault mode | Stub configuration | Rows it serves |
|------------|--------------------|----------------|
| **`nan`/`inf` numeric** | return non-finite float from scorer/cost/embedding/input | cost-spent-nan-poison, lipsync-syncnet-nan, identity-nan-arc-bypass, http-addchar-float-unguarded (NaN/inf **input** path) |
| **`None`/null return ignored** | return `None`/`MutationResult(None)` where a dict/score/result is expected | http-null-json-body, http-clearperf-silent200 (DELETE on missing shot → must 404, not 200), ckpt-projectid cross-project (Wave-1 null-continuity precedent) |
| **raised exception** | raise `APIError`/`ValueError`/`Exception` mid-call | idgate-failopen (vision LLM API error → fail-open-to-PASS), audioflag-inherit (swallowed `_has_audio_stream` probe), http-addchar-float-unguarded (non-numeric string → bare `float()` raises `ValueError` → 500) |
| **missing-key / zero-cost** | return engine name lacking the cost prefix → `$0.0` lookup | lipsync-postproc-costkey |
| **fresh / unthreaded instance** | provider builds its **own** `CostTracker()` instead of the shared one | charmgr-cost-fresh-instance, web_research-uncounted |
| **never-written / never-populated field** | a state dict/checkpoint where production never writes the key (`.add()`/save never called) | shot-spent-usd-never-written (C-1; no `spent_usd`), ckpt-sceneidx-dead (`completed_scene_indices` never populated), ckpt-shotaudio-loss (`shot_audio` never saved/restored) |
| **stall / timeout (network/subprocess)** | block past a short deadline via an **injected slow callable** (never a real sleep) | download-urllib-notimeout, audio-remux-notimeout |
| **lock-timeout / TOCTOU race** | force the project-lock acquire to time out / a shot-delete to interleave mid-write | http-drivingvid-orphan (file written before lock → orphaned; `mutate_project` return discarded) |
| **cross-thread** | call the ledger from a second thread | cost-conn-crossthread-drop |
| **wrong-field / field-selection** | a shot with the *right* answer in a field the buggy code doesn't read | lipsync-veto (base take `lipsync_score=0.0` + a postprocess variant with the real score + `dialogue_audio_in_clip`), perf-take-meta (an approved **performance** take the metadata search omits) |
| **silent-invalid / no-log observability** | a degraded result (`valid=False`, `0.0`) produced with **no log signal** | coherence-silent (unreadable image → silent color_grade suppression; assert WARNING fires post-fix) |
| **empty-input / guard-bypass** | input that passes the outer presence guard but is empty inside | http-styleboard-false201 (`FileStorage` with empty filename → `saved=[]` yet 201; assert a 4xx/`uploaded=0` signal) |
| **config-injection → assert-not-pruned (coverage-only / no-gate)** | a valid config the flag-logic mishandles — there is **no NaN/gate to fire**, so the assertion is "the right artifact survives" | has-char-lora-hole (LoRA-only shot: `char_lora` set, no `face_ref` → assert node 700 **retained**, not pruned), secondary-lora-hole (same `has_character` root, secondary LoRA) |

**Stub-exempt rows (no pin, no stub this wave — labeled, not skipped):** `lipsync-precheck-cascade-gap`
and `perf-phase-no-gate` (test-infeasible: the precheck sits inside a ~400–600-line method needing a
full `ShotController` harness), `spent-usd-reset-on-resume` (design-open, no pin until direction-pick).

## 4. The anti-vacuity rule (§7 "≥1 gate-fail assertion per gate")

For **every gate** a Wave-2 row touches, the suite must include **at least one test that
configures the stub to FAIL and asserts the gate fires** (raises / returns the
fail-safe / logs the WARNING / flips the xfail to XPASS post-fix). Concretely:

- The strict-`xfail` pin proves the bug exists **today** (non-vacuous: `--runxfail` → RED
  for the row's real reason). The same pin, when the fix lands, **flips to XPASS** — that
  flip is the gate-fires proof. operator removes the pin on the GO (it becomes a live
  regression test).
- A "fix" whose pin would pass even with the bug present (vacuous) is a **NITS/FAIL** at
  operator verify. The author proves non-vacuity by mutating the fix off and showing RED
  (the Lane-V mutation discipline already in use, e.g. `wf_07b27cf2-cea`).
- **Money rows specifically:** the cost stub injects a known spend over a known cap and
  the test asserts `is_over_budget()` / `would_exceed()` returns **True** (the
  budget-nan demo: `$100` on a `$10` cap → must be `True`). For `cost-spent-nan-poison`
  the fix keeps the accumulator **ALIVE** (coerce non-finite→0.0 + WARN), so the assertion
  is "gate still fires on a real over-cap after a NaN cost was logged" — **not** "gate
  blocks" (it is the accumulator, not the cap; mirror-opposite of budget-nan).

## 5. conftest.py / coordinator-fixture policy (resolves roadmap §7 open question, line 408)

The roadmap left open "whether coordinator-authored fixtures/stubs that can alter [gate
outcomes] are allowed." **Resolution:**

- The coordinator **MAY** author and commit **neutral test scaffolding** — a shared stub
  base class, a `:memory:` SQLite fixture factory, fault-flag plumbing — under
  `tests/` / `conftest.py` (test-only artifact, explicit pathspec). This is instrumentation.
- The coordinator **MUST NOT** author the **gate-outcome-determining configuration** — i.e.
  *which* fault a given test injects and *what* the asserted gate result is. That selection
  is the lane's, in the lane's test, reviewed by the lane's operator. A coordinator fixture
  that flips a specific gate's PASS/FAIL is a **behavior-changing fix by another name** —
  forbidden (seat-coordinator prime prohibition).
- Litmus: *would removing this fixture change which sites the fix touches, or which way a
  gate resolves in a test?* If yes → lane-authored. If it's pure plumbing → coordinator-OK.

## 6. Done-criteria for the stub layer (what "stub-fidelity reviewed" means at §7)

A Wave-2 row's test layer is contract-compliant when:

1. its stub is **dual-mode** (happy + the fault from §3);
2. there is **≥1 gate-fail assertion** proving the gate fires (§4);
3. the pin is **non-vacuous** (`--runxfail` RED for the real reason) and **flip-correct**
   (XPASS exactly when the named fix lands);
4. determinism + no-real-I/O hold (§1.3–§1.4);
5. observability asserted where the fixed code logs (§1.5).

## 7. First lane work authorized this wave-open (the 2 CRITICAL money rows)

Per the user-principal's direction (2026-06-15), Wave-2 opens on the **two CRITICAL money
rows first**, both Pair-B, both exercising the **CostTracker / budget fixture**:

- **`shot-spent-usd-never-written` (C-1, CRITICAL)** — bridge `CostTracker.get_shot_spent`
  (SQLite `SUM(cost_usd) WHERE shot_id=?`) injected into the gate loop before `check_gate`.
  Stub: a `:memory:` ledger with per-shot rows; pin = `get_shot_spent` unit (gate-loop
  end-to-end = test-infeasible, full ShotController harness — labeled, not skipped).
- **`cost-spent-nan-poison` (CRITICAL)** — coerce non-finite `cost_usd`→0.0 **+ WARN at the
  `log()` chokepoint, keep the gate ALIVE** (§4 money note). Stub: cost returns `nan`/`inf`;
  assert `is_over_budget()` still True on a real over-cap + the WARNING fires.

Both pins already landed non-vacuous (`21e8a5d`, operator2 R-VERIFY-TIER(B)). Pair-B
director owns both fixes; operator2 verifies (impl≠verifier); coordinator reconciles on GO.

**Lock note (settled at wave-open, verified against code):**
- `cost-spent-nan-poison` — fix is entirely in `cost_tracker.py` (not a cross-cutting
  module). **Pure Pair-B lane, NO lock, no co-sign.**
- `shot-spent-usd-never-written` (C-1) — the `get_shot_spent` bridge is pure `cost_tracker.py`
  (no lock). The **injection point is a director R-BRIEF design call** that decides the lock:
  the single veto caller is `cinema/auto_approve.py:341` (cross-cutting, `W2-auto_approve.py.lock`),
  but `auto_approve.py` is a pure-dict module with **no `CostTracker` handle** — so the
  minimal-blast-radius option is to write `shot_state["spent_usd"] = tracker.get_shot_spent(shot_id)`
  at the **upstream caller** (controller/pipeline, which holds the live tracker), leaving
  `auto_approve.py` untouched → **no lock**. **IF** the R-BRIEF instead edits `_shot_over_budget`
  or the gate-builder *inside* `auto_approve.py`, the director **must `claim-lock W2 auto_approve.py`
  first (§6b push-first)** and apply the Tier-A classifier (cross-cutting **+** CRITICAL → unsure
  ⇒ Tier-A; auto_approve.py also carries `lipsync-veto`, another Pair-B row sharing that lock).
  Caller-injection (no lock) is **preferred** but not mandated — the director settles it.

## 8. Coordinator review points (§7)

1. **Contract/design review** — *this document*, before stub implementation. Re-issued if
   a wave row's fault mode isn't covered by §3.
2. **Artifact review** — the finished Wave-2 suite, before it counts toward "done":
   spot-check dual-mode + non-vacuity + the gate-fires assertion per row. Earlier stubs
   are re-checked for drift here too (§7 of the roadmap).
