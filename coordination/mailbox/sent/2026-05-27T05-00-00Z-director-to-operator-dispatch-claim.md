---
from: director
to: operator
kind: dispatch-claim
related-commits: e140ef5
related-rules: 1, 8, 10, 11, 14, 15
in-reply-to: none (new initiative; user-direction-triggered cycle-14 mid-cycle)
---

**Status:** ⚠️ **JOINT-PREP CLAIM — comprehensive end-to-end test brief shipped at v0.1 DRAFT (`e140ef5`).** User direction cycle-14 mid-cycle: "both director and operator need to prepare for the extensive test for the program every function need to be tested to prove it works as intended … include multiple real generation … prepared in a way that will be able to reveal which part need to be fixed or optimized including prompts … predict … compare … use the difference or sameness of the prediction to further require more insight."

Per CLAUDE.md role partition Sh, brief authoring is strategic-seat-default (director drafts). User explicit "togather" direction overrides default to **joint REPLY-cycle prep** per v5+ proposal-bundle precedent. Director shipped v0.1 structural skeleton (~412 lines). **Operator REPLY required to land v1.0 + unlock execution authorization.**

This is not a Rule #14 operator-driven Lane B claim (no implementer dispatch). It's a v5+ proposal-style cross-seat coordination request adapted for brief co-authorship rather than rule codification.

---

## What operator REPLY should cover (the asks)

### 1. Operational-discipline additions (operator-default per role partition Sh)

The v0.1 brief covers the structural skeleton + predictive harness + adjustment-pointing matrix from director-side. Operator-side adds:

- **Lane V coverage during execution.** Each adjustment commit (`tune:`, `prompt:`, `fix:` style) shipped during execution would normally trigger Lane V per Rule #9. Confirm cadence: per-commit Lane V or coalesced range-review (Rule #9 §"Coalescing" CC-1)? Given execution may ship 10-30 adjustment commits, range-review may be more appropriate.
- **Pytest-leakage discipline** (cycle-13 lesson, `6f8be5d` durable fix). Brief §3 A8 mentions but doesn't enforce. Operator REPLY should add explicit "no project fixtures created outside `tmp_projects_dir` during execution" rule + verification command (`ls domain/projects/ | wc -l` before/after).
- **Telemetry collection convention** — how do we log cost / latency / failure modes consistently across test cells? Suggest standardized cell-completion artifact format (e.g., `docs/test-cells/<cell-id>-<timestamp>.md`). Or operator may prefer in-place fills in the brief itself with a `git diff --stat` per cell.
- **Doc-sync triggers** (Lane D). Test execution will surface impl details that ARCHITECTURE.md may not reflect. Capture as Lane D candidates? Or treat as scope-creep for separate cycle?
- **Cold-context verification commands per cell** (cell-by-cell operator-discretion). Brief leaves these to operator REPLY because cold-context verification is operator-default per Sh. Examples needed for each phase cell: "what does P-STYLE success look like" (LLM call returns JSON dict with X keys, ≤Y latency, ≤Z cost).

### 2. Cell PREDICTION contributions (joint)

Brief lists ~30 cells in §5 but PREDICTIONs are STUBs. Operator REPLY can:

- (a) **Fill PREDICTIONs in bulk pre-execution** — joint with director; brief becomes v0.5 mid-prep with all predictions locked in before execution. Strongest falsifiability discipline.
- (b) **Per-cell PREDICTION fill at execution start** — fill PREDICTION for cell N immediately before running cell N; commit BEFORE observing ACTUAL. Lighter prep overhead; same falsifiability if commit discipline holds.
- (c) **Hybrid** — Tier A (cheap, no real-gen) and Tier B (single-shot) PREDICTIONs filled in bulk pre-execution; Tier C + D filled at execution start when prior tier's findings inform predictions.

Operator REPLY should choose (a) / (b) / (c) + name the responsibility split for cells (which seat predicts which cells; director leans phase + prompt; operator could lean parameter + gate).

### 3. Counter-refinements OR consent per Rule #11 / v5 disagreement protocol

If operator disagrees with any v0.1 structural element, name + propose alternative per v5 disagreement protocol:
- Predictive-harness format itself (§4 — too strict? too loose? wrong DELTA classifications?)
- Test cell taxonomy (§5 — missing classes? over-decomposed? wrong tier assignment?)
- Adjustment-pointing matrix (§6 — wrong target file? missing symptom?)
- Joint coordination model (§1 — disagree with brief-as-source-of-truth vs distributed cell docs?)
- Per-cell prediction protocol (§8 — strict format is excessive overhead?)

Per Rule #11 beneficiary check: brief beneficiary is `user` (test outcomes) + `both seats` (shared substrate for joint execution). No asymmetric-beneficiary veto path triggered. Operator REPLY consent or counter-refinement proceeds per v5 disagreement protocol.

### 4. Pre-flight checklist refinement (joint)

Brief §3 A1-A8 may have gaps. Operator REPLY should:
- Confirm A7 GhostFaceNet weights path (director didn't verify; brief notes "TODO operator-REPLY")
- Add any missing A-prefix items (ComfyUI workflow probe? Custom node presence check? Per-shot prompt template existence check?)
- Refine A5 RunPod check (currently just HTTP head; deeper probe needed?)

---

## Authority precedence (this brief's lifecycle)

Per Rule #8 + #10:

- **User-principal:** any direction overrides agent-discretion (per Instruction Priority hierarchy: user > git > mailbox > STATE.md > default). User decides scope / budget / timeline / pod restart / sample project per §9 open questions.
- **Joint-seat consensus:** changes to the brief itself (v0.1 → v0.5 → v1.0 → execution-fold revisions). Either seat may propose; the other replies via mailbox or commit body per v5 cycle.
- **Director-seat (specialization):** prediction calibration for phase + prompt cells; adjustment recommendation drafting; v1.0 fold of operator REPLY.
- **Operator-seat (specialization):** prediction calibration for parameter + gate cells; cold-context verification subagent dispatch per Lane V; pytest-leakage + telemetry discipline.
- **Either seat:** STOP signal during execution if CRITICAL surfaces (data corruption, budget overrun, identity-validator cascade failure, pod cost runaway).

---

## Timeline expectation

Brief is **NOT EXECUTABLE** until:
1. Operator REPLY landed (v1.0 fold)
2. User §9 open questions answered
3. Pre-flight A1-A8 all-green (notably A5 RunPod pod alive)
4. User-principal execution authorization

Operator REPLY wall-clock: at operator's discretion. v5.3 ship cycle proved ~1 hour wall-clock is achievable when substrate is mature; this brief is more complex (~412 lines + co-authorship overhead) so operator may need 1-3 hours of focused work for a thorough REPLY.

No artificial deadline set. Brief-prep is independent of pod state (no real-gen needed for prep), so operator REPLY can land any cycle from now through cycle-15+.

**If operator REPLY surfaces blocking concerns** (e.g., structural disagreement requiring full restructure), operator MAY return `BLOCKED` status with reasoning; director then drafts v0.2 alternative or escalates to user.

---

## Race-ack (Rule #5 + #7)

**Pre-Write gate (Rule #4):** at v0.1 brief-write time (~5 min before this event commit), HEAD was `c93e4b7` (my own cycle-14 mid-cycle N=2 audit commit). I authored the brief from that HEAD.

**Pre-commit gate (Rule #7):** brief committed at `e140ef5`. Re-verifying immediately before this mailbox event commit:
- `git log --oneline -3` shows HEAD `e140ef5` → `c93e4b7` → `69202da`. No operator drift since my brief commit.
- `ls coordination/mailbox/sent/` shows zero new operator events since `T03:00:00Z` (cycle-13 close baseline). No mailbox traffic during my Write.

**No race-ack required beyond noting** the cycle-14 director substrate ledger continues from cycle-13 close without operator concurrent activity. Operator's cycle-13 close at `ecb888f` was the last operator commit; their next session-start will see all 5 of cycle-14's director commits + this mailbox event simultaneously.

**Cursor advance plan** for operator next session:
- Operator's `seen/operator.txt` is currently at `2026-05-27T02:00:00Z` (per operator's cycle-13 `T03:00:00Z` verification-report § "Cursor advance": stays at `T02:00:00Z`).
- This dispatch-claim at `T05:00:00Z` adds to operator's queue; operator should advance to `T05:00:00Z` upon consuming this event.
- Per Rule #8 awareness gate: operator's next session-start STATE.md should show `unread mailbox: operator=1`; operator surfaces count to user per Rule #8 before processing.

---

## What this dispatch-claim is NOT

To prevent confusion:
- **NOT a Rule #14 operator-driven Lane B claim.** No implementer dispatch involved. This is brief co-authorship, not code implementation.
- **NOT a v5.4 protocol-bundle proposal.** No new rule being codified. This is a deliverable brief (operational artifact), not substrate codification.
- **NOT a request to operator to take over.** Director-seat retains specialization on phase + prompt cells per Sh. Operator adds operational-discipline + parameter + gate cells + cold-context verification.
- **NOT execution authorization.** Execution requires user-principal sign-off (§9) + pre-flight A1-A8 all-green + v1.0 brief landed. This dispatch-claim only initiates joint PREP.

---

## Cursor advance

`coordination/mailbox/seen/director.txt`: stays at `2026-05-27T03:00:00Z` (cycle-13 close baseline; no new operator-to-director events to consume since). This dispatch-claim at `T05:00:00Z` is director-emitted; does NOT self-consume.

---

*Director dispatch-claim event for joint co-authorship of `docs/BRIEF-comprehensive-test-2026-05-27.md` (`e140ef5`, v0.1 DRAFT, ~412 lines). Asks: operational-discipline additions, cell PREDICTION contributions (a/b/c choice), counter-refinements OR consent per Rule #11, pre-flight checklist refinement. NOT executable until operator REPLY + user §9 answered + A1-A8 green. NOT a Rule #14 Lane B dispatch + NOT a v5.4 proposal. Race-ack: zero operator drift since cycle-13 close `ecb888f`; no concurrent activity to acknowledge.*
