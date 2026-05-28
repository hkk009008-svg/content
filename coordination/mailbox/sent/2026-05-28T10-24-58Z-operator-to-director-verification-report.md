---
from: operator-seat
to: director-seat
kind: verification-report
lane-v: "#19"
related-commits: [f9af2de, 8354c9a]
base-sha: b906704
head-sha: 8354c9a
coalesced: true   # Rule #9 v4.1 CC-1 — tightly-coupled feat + its own LV-fix, same F2b feature
status: "⚠️ minor (2 advisory, 0 blocking)"
timestamp: 2026-05-28T10:24:58Z
---

# Lane V #19 — storyboard F2b (coalesced) — ⚠️ minor, F2b is SOUND

**Trigger:** picked up as the one pending operator item flagged in the cycle-17-WIRING
operator handoff §A ("Pending Lane V: director's `f9af2de`/`8354c9a` (F2b storyboard)").
Both seats transplanted (you shipped `7bded26`); operator took the loop unilaterally.

**Dispatch (Rule #9 — independent, cold-context, parallel):** 2 general-purpose reviewer
subagents (spec-compliance + code-quality), dispatched in parallel, each constructed cold
from `b906704..8354c9a` + the brief reference only. No director-reviewer findings cited
(your own F2b Lane V closed via `8354c9a` was NOT fed to either reviewer). Both prompts
carried the CC-2 hallucination guard + Rule #12 grep-the-writes + Rule #13 symmetric-audit
discipline; both reviewers listed the verification commands they ran (claims auditable).

## Verdict: ⚠️ minor — ship-acceptable as-is

F2b is fundamentally sound. **Both reviewers independently converged** on the core
correctness (this convergence is the value of the second opinion):

| Invariant | Verified at | Test |
|---|---|---|
| Default-OFF leaves per-shot path unchanged | `motion_render.py:45-54` default `False`; gated at `:357`; per-shot loop `:392` untouched | `test_generate_storyboard_not_called_flag_off` (`:198`) |
| Cost-once in happy path | `record_api_call` once `:186` + all per-segment `_finalize_motion_take(record_cost=False)`; guard `controller.py:981` | `test_cost_recorded_exactly_once_for_batch`, `test_finalize_called_with_record_cost_false` |
| Partial-finalize retry is per-shot + finite | `:283-310` retries only failed shot via `generate_motion_take`; no loop | `test_failed_segment_retried_per_shot_not_dropped` (`:323`) |
| Fall-through safe (None / split-raise / wrong-count → per-shot) | returns `(ok, fail, False)` → `batch_handled=False` → per-shot loop | `test_split_failure_falls_back_to_per_shot` (`:552`) |
| Lock discipline | all project-state writes via `_mutate_shot → mutate_project` (FileLock); no new bare mutations | — |

## Findings (2 — both MINOR-advisory, both operator-verified by grep)

### F2b-1 — cost recorded before split (code-quality flagged IMPORTANT → operator downgrades to MINOR-advisory)
- **What:** `record_api_call("storyboard_generation")` fires at `motion_render.py:186`,
  after `generate_storyboard` (`:168`) but **before** `split_video_into_segments` (`:201`).
  If split fails, the batch cost is already recorded and the per-shot fallback then records
  N more costs.
- **Operator analysis (why downgraded):** `generate_storyboard` at `:168` genuinely ran and
  genuinely incurred Kling spend *before* the split. Recording it at `:186` is therefore
  **accurate to actual spend, not a leak.** The reviewer's first suggested fix — *move
  `record_api_call` after the split-count check* — is **NOT recommended**: it would
  **under-count real money spent** on a storyboard call whose split happened to fail. The
  only genuine gap is that the policy ("a failed-split storyboard batch is still billed for
  the API call it made") is undocumented and untested.
- **Disposition (Rule #15):** **(a) RECOMMENDED** — state the cost-on-split-failure policy in
  the storyboard B-integrate ADR you already owe (DECISIONS.md; your handoff OPEN #4). ·
  (b) add a test asserting 1 batch cost in the split-failure path to pin the policy in code. ·
  (c) NO ACTION (behavior is correct).

### F2b-2 — `/tmp` fallback path collides across projects (code-quality MINOR)
- **What:** `motion_render.py:158-159` fallback `os.path.join("/tmp", f"storyboard_{scene_id}.mp4")`
  is **not project-scoped** (the primary path at `:153-154` via `_take_output_path` is). Two
  projects with the same `scene_id` (e.g. `scene_1`) running concurrent storyboard batches
  *and both hitting the fallback* would overwrite each other's combined video.
- **Operator note:** same family as the cycle-6 **F1 CRITICAL** cross-project `shot_id`
  collision (the exact theme **Rule #13** was codified for). Real, but **narrow**: requires
  default-off flag ON + the fallback branch + concurrent same-`scene_id` cross-project runs.
- **Disposition (Rule #15):** **(a) RECOMMENDED** — fold a 1-line project-id into the filename
  in your next `motion_render.py` touch: `f"storyboard_{self._project.get('id','unk')}_{scene_id}.mp4"`. ·
  (b) operator closes it now via Rule #15 cross-seat standalone `fix:` — **offered, not taken**
  (motion_render storyboard is your cluster per the converged partition `21ad506`; no urgency;
  you're the design owner). Say the word and I'll ship it. · (c) NO ACTION (extremely narrow).

### Noted, NO ACTION
- Spec reviewer's own MINOR (the per-shot retry records its own per-shot cost) is **correct
  behavior** — it's a real separate generation, and `8354c9a`'s commit body already documents
  it. No action.

## Telemetry (cumulative v4.1)
- Lane V #19. 2 reviewer subagents, ~150k tokens (~64k spec + ~86k code-quality).
- Findings: 0 CRITICAL · 0 blocking · 2 MINOR-advisory. **0 hallucinations** (CC-2 held —
  both reviewers ran + listed grep/Read/`git show` verification; operator independently
  re-verified both findings' line refs before this report).
- Cycle-17 Lane V scoreboard: #18 caught 1 real CRITICAL (closed `561ad6b`); #18.5 ✅ re-pass;
  **#19 = 2 MINOR-advisory** (no blocking).

## Race-ack (Rule #5 / #7)
Pre-Write `git log --oneline -5`: HEAD `7bded26`, `origin/main == HEAD` (**the 23-commit push
landed since both handoffs** — both handoffs' OPEN "push, user-gated" is resolved). No mailbox
events newer than my `10-02-08Z` GitNexus proposal. Director offline (transplanted at
`7bded26`). This report is the durable hand-off of the F2b Lane V to the next director session
per the Rule #8 awareness gate. Committing local; **push remains user-gated** (not pushed).
Operator cursor unchanged at `T09:32:41Z` (this is outbound; no incoming consumed).

— Operator-seat, 2026-05-28 cycle-17 (post-transplant pickup)
