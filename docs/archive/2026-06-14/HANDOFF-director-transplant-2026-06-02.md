# Director-seat transplant handoff — 2026-06-02 (≈01:44Z)

*Authoring director session: picked up cycle-17 on the `max-tier-provisioning-2026-06-01` branch, closed the operator's max-tier Lane V (F1/F2/F3), studied the full program manual + digests, and produced a dead-code prune recommendation. State was re-verified live at write-time per Rule #4/#7 + ADR-013 — and it had moved a LOT (read §1 first).*

> **TL;DR for the next director:** The canonical trunk `main` (`5425f9e`, **pushed**) now carries the F1 + F1b dangling-link fixes and is **green (1295 passed / 0 failed)**. `feat/max-tier-provisioning` (`86d5f4d`, **unpushed**, the live working line) is the consolidated max-tier path, **LIVE-validated 4K image on pod**. **My session's branch `max-tier-provisioning-2026-06-01` (`50b4f63`) is SUPERSEDED/orphaned** — the *finding* + hand-off spec + TDD test carried into the canonical fix, but the commits did not. Read the operator's freshest ops handoff: `docs/HANDOFF-operator-transplant-2026-06-02-max-tier-live-validation.md`.

---

## 1. Current state — branch map (verified `git log`/`merge-base` at 2026-06-02T01:43Z)

| Branch | Tip | Pushed? | What it is | pytest |
|---|---|---|---|---|
| **`main`** | `5425f9e` | **YES** (origin==`5425f9e`) | Trunk. Carries **F1** (no-char dangling, `a302585`) + **F1b** (no-init FaceDetailer conditioning dangling, `5425f9e`), both CRITICAL, + my reachability test `tests/unit/test_quality_max_prune.py`. | green: 1295 passed / 5 skip / 0 fail |
| **`feat/max-tier-provisioning`** | `86d5f4d` | **NO** | **Active max-tier line**, built on `main`. `setup_runpod.sh --max`/`--max-fp16`, fp8/fp16 re-point, LoRA-less max path, pod-aligned `pulid_max.json`, **LIVE-validated 4K image on pod**. Main tree is checked out here. | green (same suite) |
| `capability-test-suite` | `1fae944` | NO | Operator's capability test-suite Plan 1 (8 commits, 12/12 green, additive). User: keep-as-is, no merge/push. | green |
| `max-tier-provisioning-2026-06-01` | `50b4f63` | NO (origin stale @ `e5a880e`) | **MY SESSION'S WORK — SUPERSEDED/ORPHANED.** Diverged at `6679ef2`; commits NOT in `main`/`feat`. Clean up (see §3). | 26 pre-existing fails (lacked main's scene-transition fixes — irrelevant now) |

Fork point for everything: **`6679ef2`** (the pre-fork max-tier handoff commit). `feat/max-tier-provisioning` descends from `main@5425f9e`; `max-tier-provisioning-2026-06-01` and `capability-test-suite` are independent forks off `6679ef2`.

**Worktrees** (`git worktree list`): main tree `/Users/hyungkoookkim/Content` → `feat/max-tier-provisioning`; **`.claude/worktrees/f1-max-tier` → `max-tier-provisioning-2026-06-01` (my orphaned worktree — remove, see §3)**; four `.claude/worktrees/claude-*` are harness subagent worktrees (leave).

---

## 2. What this director session shipped — and where the value landed

I closed the operator's max-tier **Lane V** (report `coordination/mailbox/sent/2026-06-01T09-56-12Z-operator-to-director-verification-report.md`) on the `max-tier-provisioning-2026-06-01` branch, TDD-first:
- `4b20f1b` — **F1** (CRITICAL no-char/landscape dangling: pruned FaceDetailer(600)+ReActor(610), FLUX-incompat fallback→112) + **F2** (504/505 prune-gap). New `tests/unit/test_quality_max_prune.py` (reachability-from-SaveImage link-integrity, 5 tests, RED→GREEN).
- `8108467` — **F3** (`setup_runpod_max.sh` compat-patch drift now FAILs + records to summary).
- `893cffc` / `50b4f63` — coord + cursor advance + **cold F1-port hand-off spec** to operator.

**The value transferred completely (the commits did not):**
- Operator ported F1 **verbatim from my hand-off spec** → `a302585` on `main` ("…from the director's cold hand-off spec, mailbox").
- **My reachability test then surfaced a bonus bug — F1b** (no-init FaceDetailer conditioning `[804,0]` dangling, exists only on the 56-node base) → fixed `5425f9e` on `main`.
- F3/setup work was *re-done* properly on `feat` (`9850b7b` scrubbed my `setup_runpod_max.sh` as "fabricated", consolidated into `setup_runpod.sh --max`; `912d562` redid the FLUX-incompat prune on the live pod). So my F2/F3 specifics are superseded; the F1 finding + test methodology are the durable contribution.

Also this session: **studied `docs/PROGRAM-MANUAL.md` (2033L) + `docs/PROGRAM-MANUAL-digests.md` (3891L) end-to-end** (program intent + §5 capability-max playbook + all 12 subsystem digests + footguns internalized), and produced the **dead-code prune recommendation** in §4.

---

## 3. Open items (owner)

1. **Clean up my orphaned work** *(director/next)* — delete branch `max-tier-provisioning-2026-06-01` and `git worktree remove .claude/worktrees/f1-max-tier`. Its F1/F2/F3 are superseded by `a302585`/`5425f9e`/`feat`. Nothing of value is lost (verify: `git log main..max-tier-provisioning-2026-06-01` is all superseded). Don't push `origin/max-tier-provisioning-2026-06-01` (stale @ `e5a880e`); consider deleting the remote branch too.
2. **Push `feat/max-tier-provisioning`** *(user/director)* — it's the live-validated max-tier line, currently local-only. Decide push / PR-to-main.
3. **Dead-code prune** *(user go → director/operator)* — recommendation ready in §4; land on **`main`** (the live trunk) as its own `chore` commit(s). Awaiting user go-ahead.
4. **`validate_lora_quality`** *(backlog, capability-positive)* — implement (it's a wired stub returning −1.0; LoRA is the biggest identity lever per §5). Do NOT prune.
5. **Dormant quality levers** *(backlog)* — `evaluate_generation_quality`+`negative_prompts.py` (auto-diagnose/remediate loop), `ltx_native._fal_transition`/`_native_transition` (keyframe transitions), `summarize_audit`. Keep/wire; pruning these trades against full capability.
6. **capability-test-suite Plans 2–N** *(operator)* — Plan 1 done; user kept-as-is.
7. **GPU pod** — user reported it stopped earlier this session; **verify before any spend**. Pod ID/SSH in prior handoffs/memory.

---

## 4. Insight to carry forward

### 4a. Dead-code prune recommendation (filtered to "unnecessary for MAX quality")
Verified zero live callers on `main`; the dividing line is **prune superseded/ops dead code; KEEP dormant quality levers.**

**Recommend pruning (quality-neutral — superseded-by-better or pure ops):**
- `reporter.py` (whole file) — orphan diagnostics printer, not imported.
- `generate_characters.py` (whole file) — legacy standalone, superseded by `character_manager.create_character_with_images`.
- `domain/dialogue_writer.py::format_dialogue_for_voiceover` + `dialogue_to_narration_text` — absorbed into `generate_dialogue_voiceover`.
- `domain/continuity_engine.py::record_shot_generated` + `reset_scene` — dead `last_generated_image` path (live path uses the *better* `approved_anchor_image`).
- `domain/continuity_engine.py::validate_multi_identity` — legacy, superseded by `IdentityValidator.validate_video` (update the `identity/validator.py:45` docstring on removal).
- *Optional (ops/scaffolding, not quality):* `auto_approve.summarize_audit`, `cinema/pipeline.py::CinemaPipeline` (generic driver, 0 prod importers), `run_tier_c.py` (never a real harness).

**Do NOT prune (dormant QUALITY levers — see §3.5).** Re-grep incl. `tests/` + dynamic refs at prune time; one `chore` commit per concern; ADR per ADR-016 precedent.

### 4b. Program model (from the manual/digest study)
One orchestrator (`cinema_pipeline.CinemaPipeline.generate()`), one entry (`web_server.py`:8080), 11 stages / 5 gates, **project-dict-as-bus + append-only takes + approval-pointers**, cascades + LLM-everywhere. Max-quality levers (§5): `quality_tier="max"` (N=8 + SUPIR 4K), per-char **LoRA**, `identity_strictness≈0.70`+`adaptive_pulid`, `competitive_generation`+`quality_judge="claude-opus"`, VEO_NATIVE for dialogue, `config/prompts/pipeline_context.md` as the global LLM lever. Top footguns: two `CinemaPipeline` classes; **headless uses `ThreadedLifecycle` NOT `NullLifecycle`**; `record_director_review_on_shots` unblocks PLAN; `final_require_human_if_upstream_auto=True` is the #1 unattended dead-end; **`shot_id` not globally unique → pid-scope**; budget gate covers only video/image. Truth order: `ARCHITECTURE.md` > manual > digests; all `file:line` anchors are point-in-time (grep the symbol).

### 4c. The branch-fork lesson (load-bearing for coordination)
**D-a inactive (shared index) + shared-tree branch-switching produced a 3-way divergence** (`main` / `max-tier-…` / `capability-test-suite` / then `feat/max-tier-provisioning`). Because the files diverged, the F1 fix had to be **re-implemented on `main`** (not cherry-picked). Lesson: when seats work different lines in one shared tree, **coordinate branch ownership explicitly** and prefer landing fixes on `main` first. The reachability-TDD pattern (`test_quality_max_prune.py`) is reusable and earned its keep (found F1b) — keep that test shape for any ComfyUI graph-surgery.

---

## 5. Coordination state
- **D-a INACTIVE** this session (`CLAUDE_SEAT`/`GIT_INDEX_FILE` unset → shared index → `git commit -- <pathspec>` discipline). USER must relaunch with `CLAUDE_SEAT`+`GIT_INDEX_FILE` to activate D-a (see `coordination/README.md`).
- **Both seats wrapped/offline** at write-time: operator presence `status:wrapping`, `head_at_write:86d5f4d`, `updated 2026-06-01T20:53Z` (~4.75h stale); director presence updated by me.
- **Cross-branch mailbox/cursor fork:** my F1 Lane V exchange (cursor advance to `T09:56:12Z`) lives on the orphaned `max-tier-…` branch; on the canonical line the director cursor reads `T00:29:40Z` with **0 unread** to-director events. Reconcile cursors when lines converge.
- Mailbox archive holds the full F1 lifecycle (Lane V report → my closes → hand-off) for audit.

## 6. How to pick up (session-start)
1. Run `.venv/bin/python scripts/ci_smoke.py` (§15). 2. Read the operator's freshest ops handoff `docs/HANDOFF-operator-transplant-2026-06-02-max-tier-live-validation.md`. 3. Read `docs/PROGRAM-MANUAL.md` (intent) early. 4. `git worktree list` + `git log --oneline -8 main feat/max-tier-provisioning` to confirm this map still holds. 5. Check `coordination/presence/*.md` + recompute unread per Rule #20. 6. First real action candidates: the §3 cleanup + the §4a prune (on user go) + pushing `feat/max-tier-provisioning`.

*Signed: director-seat, 2026-06-02 ≈01:44Z. State verified live; supersedes any earlier mental model of the max-tier branch as the active line.*
