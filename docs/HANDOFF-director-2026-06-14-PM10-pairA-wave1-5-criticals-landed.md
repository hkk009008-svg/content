# HANDOFF — Director (Pair-A), 2026-06-14 PM10

**READ FIRST AS PAIR-A DIRECTOR.** Supersedes PM9. Resumed ("continue as director1",
ultracode) into the **live program-hardening campaign Wave-1** (coordinator Session-8
LIVE, directive=coordinate; both pairs active). PM9's deferred "import-swap pass" had
been absorbed into the formal Wave-1 inventory. **Drained all 5 Pair-A Wave-1 CRITICAL
rows** end-to-end (claim lock → R-BRIEF → Tier-A co-sign → implement → self-verify),
plus the coordination owed. Trust `git log`, not this prose.

## TL;DR — 5 Pair-A Wave-1 CRITICAL rows FIXED + landed (local; push USER-gated)
| row | commit | guard |
|---|---|---|
| `pulid-nan-node100` (T4, pure-lane) | `4eca599` | `_finite_or` on PuLID node-100 weight/start_at/end_at (mirror 700/701) |
| `null-continuity-crash` (T5, pure-lane) | `af03eeb` | `isinstance(_co, dict)` guard at `workflow_selector.py:515` (mirror quality_max:1044) |
| `aa-nan-rules` (T1, cross-cutting) | `5ef3605` | finite-guard chokepoint in `AutoApproveConfig.from_project._get` (all 6 numerics) |
| `aa-inf-scorebypass` (T2, cross-cutting) | `b8e3d72` | `math.isfinite` skip-guard in the 4 `_best_take_*` helpers |
| `aa-budget-nan-veto` (T3, cross-cutting) | `baac518` | fail-closed `_shot_over_budget` on non-finite spent + budget_total |

- **Verification:** each pin → live regression, **mutation-proven** (revert guard → RED);
  ci_smoke hard-gate green per commit; **full unit suite 2480 passed / 0 failed / 0 xpassed**;
  T3 has **11/11 `_shot_over_budget` edge cases**. **Adversarial workflow `wf_955f2b6c-16e`
  CLEAN** (5/5 refuted=false high-conf, 0 bypasses, 0 uncovered siblings).
- **Tier-A co-sign:** director2 GO `10:35:37Z` (verified at source, BEFORE code, §6c) for the
  3 auto_approve rows. `W1-auto_approve.py.lock` HELD (`a25d455`).
- **Coordination done:** retroactive `ws-reorder-deletes` Pair-A scope-confirm DISCHARGED
  (no overreach, delegator endpoint); concurred Pair-B's budget-nan pure-lane re-anchor.

## Convergences (the 4-seat design paying off)
- **T1 `5ef3605` closes operator2's `aa-inf-multiplier`** (auto_approve.py:595): the `_get`
  chokepoint coerces inf/NaN `image_max_spent_multiplier` → 1.5 (VERIFIED). Chokepoint
  subsumes the whole numeric family, not just the pinned thresholds.
- **T3 `baac518` closes operator2's `aa-nan-budget-total`** (auto_approve.py:587) = exactly
  director2's co-signed option-a (guard budget_total fail-closed in `_shot_over_budget`).
  → Coordinator: do NOT open separate rows for either; mark verified-by-T1/T3.

## Carries for the next Pair-A director
1. **operator-1 per-fix verify PENDING** (impl≠verifier). On their **last** auto_approve GO
   they release `W1-auto_approve.py.lock` in the same commit; coordinator advances the 5 rows
   open→fixed→verified. operator-1 front-loaded verify-readiness (`10:29Z`/`10:33Z`) — RED
   baseline + scope-match criteria all confirmed; pure-lane T4/T5 → straight GO.
2. **⚠ T3 placement refinement (flagged, awaiting operator-1 scope-match):** the budget_total
   guard adds `is not None` to director2's *literal* co-signed placement — without it a NULL
   cap would be mis-flagged fail-closed, but ADR-026 says None=no-cap. Proven by 11/11 edge
   cases. operator-1: scope-match the BEHAVIOR (fail-closed on corrupt cap + None=no-cap),
   not the literal placement. If operator-1 NITS it, the fix is to accept the refinement
   (it's more correct per director2's own ADR-026) — don't revert to the literal form.
3. **C-1 `shot-spent-usd-never-written`** (auto_approve.py:594, op2 sweep): the per-shot veto
   my T3 hardens is **dead in production** (nothing writes `spent_usd` into a shot dict). My
   T3 is correct-but-insufficient by design (right shape for when the veto IS wired). The
   **bridge is Pair-B** (`CostTracker.get_shot_spent(shot_id)` injected into the gate loop) —
   **director2 owns it**. No Pair-A action; just don't re-fix T3.
4. **PUSH user-gated, wave-boundary batch.** 16 commits ahead of origin (mine + interleaved
   peer), all local. The coordinator gates the Wave-1 push when all 8 rows verified (Pair-B
   still has Task 7 + C-1/C-2). Don't push Pair-A alone mid-surge (drags peer commits).
5. **Realism/pod levers UNCHANGED** (pod STOPPED, $0): ADR-024 dual-LoRA graft burn +
   max-wide start_at re-measure remain pod-gated for a deliberate supervised session.
   See [[realism_production_plus_char_lora]], [[max_wide_pulid_startat_adr025_gap]].

## Sharp edges (this session)
- **Doc-anchor gated/ungated split (refines the blind-spot lesson):** ci_smoke gates
  `` `symbol` (path:N) `` same-line def-anchors; **"Helper at [path:N]" markdown-links with
  NO backtick symbol are UNGATED even when pointing at a def.** My quality_max +5 / auto_approve
  +14 line shifts drifted 8 + 2 such anchors that ci_smoke never flags — re-synced manually.
  Anchor-drift risk = only anchors BELOW the edit point (T5's were all above → no re-sync).
- **`replace_all` caught a Rule#13 sibling:** `def _get` appears twice (AutoApproveConfig +
  AdvisoryConfig); the latter reads bools only → EXEMPT (director2 co-sign confirmed). Used
  `quality_tier` context to target only the AutoApproveConfig one.
- **Honor the finding, refine the implementation:** director2's co-signed budget_total
  placement had a None edge bug; I shipped the correct form + flagged it (receiving-code-review
  discipline) rather than ship verbatim-but-wrong.
- **Shared-tree hygiene held:** HEAD moved ~8× under me (4 seats + coordinator). Every commit
  used explicit pathspec; peer WIP (`??` files, ` M` peer cursors) never swept; per-commit
  blob/HEAD checks. claim-lock does `git reset --hard @{u}` on a lost race → only claim on a
  clean tree.

## State at wrap (trust `git log -1`)
HEAD `3d9028f`; **16 ahead of origin, 0 behind, tree CLEAN** (my fix commits +
coordination + interleaved peer). `W1-auto_approve.py.lock` HELD (operator-1 releases on
last GO). ci_smoke hard gate green (PROGRAM-MANUAL.md advisory drift only — batch-fixable).
Pod STOPPED, $0. Push USER-gated.
