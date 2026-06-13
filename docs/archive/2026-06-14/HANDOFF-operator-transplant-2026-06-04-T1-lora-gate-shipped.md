# Operator Transplant Handoff — 2026-06-04 (T1 LoRA quality gate SHIPPED · T3/T4 done · branch finishable)

*Last verified: 2026-06-04 (early). Branch `feat/max-tier-provisioning` @ `c95317d` (substantive
tip `bf86262`; `c95317d` is a director coord commit). **`main` = `3fa46f4`; `feat` is FF-able to
main (verified ancestor — clean 35-commit fast-forward), 27 ahead of `origin/feat`.** Suite
**1607 / 0** (director-verified at `bf86262`; HEAD adds only coord commits), `ci_smoke OK`, anchors
clean, `grep "CANDIDATE BUG" tests/unit/` empty. This handoff SUPERSEDES
`HANDOFF-operator-transplant-2026-06-03-part5-phaseA-complete.md` — its OPEN #1 (T1
`validate_lora_quality`) is DONE this session.*

## ★ READ FIRST — what this session shipped

**T1 (`validate_lora_quality` + auto-retrain quality gate) — COMPLETE, reviewed, SHIP-clean.**
The `-1.0` stub is now a real ArcFace identity gate wrapped in a bounded train→validate→retrain
loop that also sweeps + **persists the best per-character LoRA strength** into production. This
was a full design-first cycle (brainstorm→spec→plan→7 TDD tasks via subagent-driven-development),
user-directed.

| T1 layer | What | Key commits |
|---|---|---|
| New `prep/lora_quality.py` | pure `_next_lora_action` decision fn · honest single-shot `_generate_with_lora` (reuses `quality_max._run_one_candidate` etc., no N=8 best-of) · `validate_lora_quality` ArcFace oracle (strength sweep × prompts) · `train_character_lora_gated` orchestrator (≤3 trains, keep-best, reject-if-net-negative) | `389e1c5`/`f36e297`/`e9388d6`/`d386fc7` |
| Refactor | `prep/lora_training.py::train_character_lora` → pure single-train; stub + `LORA_VALIDATION_SKIPPED` retired | `fb5c62c` |
| Web | `web_server.api_train_lora` → gated orchestrator; persists `char_lora_paths` **+ `char_lora_strengths`** in the existing `_mutate`; `record_lora_verdict` writes the verdict to status so `get_lora_status` surfaces `rejected`/`quality_warning` | `cfe2a27`/`54ff3d2`/`cf34004` |
| Render | `cinema/shots/controller.py` reads `char_lora_strengths` → threads `char_lora_strength` through `phase_c_assembly.generate_ai_broll` → `quality_max.generate_ai_broll_max` → `_inject_identity` (overrides node-700 strength_model/clip; **0.0 honored**; **both** call sites incl. PuLID-boost retry; tier-default fallback) | `287062e`/`4195a24` |

- **Capability win (PROGRAM-MANUAL §5):** a bad LoRA now gate-and-auto-retrains instead of
  silently degrading every shot; each character's LoRA bakes at its **validated** strength —
  closing the **1.0-over-bake gap** (realism memory: 0.55 beats 1.0, never previously wired).
- **Review trail:** spec (reviewer ✅, `082edb5`) → plan (reviewer ✅, `9bd657a`) → per-task spec
  + code-quality review on all 7 tasks → director's **independent two-chunk Lane V (✅ SHIP ×2,
  Rule #9)** → operator final cross-cutting (✅ SHIP). Layered review caught + fixed **5 real
  issues**: dead seed (`bff8803`), cwd-litter→tempdir (`0073ccf`), verdict-not-surfaced
  (`54ff3d2`/`cf34004`), strength_clip-collapse backward-compat regression (`4195a24`),
  REJECT-no-log + 2 more director-flagged minors (`94c4d73`).
- **`pipeline_status.toml` `lora_validation`: `stubbed`→`parked`(`7a20fc8`)→`wired`(`6f7df8d`)** —
  wired end-to-end; the enum is `live/wired/stubbed/parked` (NO "implemented").
- **Specs/plan:** `docs/superpowers/specs/2026-06-03-validate-lora-quality-design.md` +
  `docs/superpowers/plans/2026-06-04-validate-lora-quality-gate.md`.
- **T1 range:** `9f2ace6..6f7df8d` (21 commits incl. review-fixes + coord).

## Where the program / branch stands

- **`main` = `3fa46f4`** (the Part-3 program + prune cycle is on trunk). **`feat` (`bf86262`/
  `c95317d`) is a clean FF ahead of main** (35 commits: entire T1 + T3 + T4 + fixes), and **27
  ahead of `origin/feat`** (`9f2ace6`, behind — feat is UNPUSHED).
- **Director shipped T3 + T4 this session** (parallel, on the `quality_max.py` I handed off settled
  at `4195a24`): **T3** (`7c0dbf6`) hires_fix Pass-2 realism lever (node 18 @ denoise 0.40);
  **T4** (`e0ac702`) `conjunctive` identity-floor halt mode + director's Lane-V fix `bf86262`
  (arc-floor now guarded on `has_character` — no-char/landscape shots can early-halt). Director
  Lane-V-clean.

## NEXT — priority order (for the next operator)

1. **T1 Phase-B — LIVE calibration (GPU pod, spend-gated).** The ONLY T1 piece left: on a real
   pod, tune `PASS_THRESHOLD`(0.6) / `NET_NEGATIVE_BASELINE`(0.45) / `DEFAULT_STRENGTH_SWEEP` against
   live ArcFace scores + run one real end-to-end train→validate→persist. Design is
   correct-by-construction + fully boundary-tested offline; values are sensible defaults.
   ⚠️ Pod `07ed667` was 404/stopped (memory) — verify Novita before spend.
2. **Part 4 — UI surfacing** (last $0 offline program piece; design-first): U1 capability scorecard,
   U2 per-shot coherence/motion/lipsync scores (already in `take.metadata`), U8 cascade-provenance.
   `web/.../Telemetry.tsx`, React 19. Engage the user (subjective design).
3. **T6** (MED, design-first) — wire `chief_director.evaluate_generation_quality` + `negative_prompts`
   auto-diagnose/remediate loop (dormant quality lever; no production caller). PROGRAM-MANUAL §5.
4. **Optional UI follow-up:** `hires_fix_steps` has a schema/template knob but **no React slider**
   yet (T3 left it API-only).
5. **T1 cosmetic minors (accepted, NO ACTION — recorded for completeness):** (a) `_gated_result`
   train-failure early-return has a non-uniform key set vs the success path — safe (callers use
   `.get()`); (b) `_generate_with_lora` hard-codes `shot_type="portrait"` for tier params while one
   validation prompt is "full body" — a Phase-B calibration note, not a correctness issue.

## NOT operator (director-lane / user-gated) — IN FLIGHT

- **Push `feat` + FF-merge to main** — the director is **presenting this to the user-principal NOW**
  (director-default per role partition; clean 35-commit FF). This **supersedes** the earlier
  "keep branch as-is" the user told operator (that choice was made *before* T3/T4 landed; the hold
  rationale — director mid-T3/T4 — is now resolved). Operator concurs (Rule #16 convergence note
  sent). **Watch `git log` / the user's decision; do not double-drive the merge.**
- Director's honest caveats carried into the merge: T3 denoise=0.40 is a pod-UNvalidated realism
  hypothesis; T4 `conjunctive` is opt-in (default `composite_only`); `budget_only` halt mode deferred.

## Coordination state

- **Director: ACTIVE.** Shipped T8/T11/T7/T5 (earlier) + T3/T4 (this session); ran 2× independent
  Lane V on T1 (both ✅ SHIP); presenting the merge. Latest director event `2026-06-03T18-04-35Z`
  (processed). `quality_max.py` is the director's now (settled at `4195a24`, unchanged through T1).
- **Operator cursor:** `2026-06-03T17:24:54Z` → advancing to `18:04:35Z` this wrap.
- **No open director→operator asks** beyond the merge presentation (which is user-facing, not an
  operator action).

## Gotchas / precedents (carry forward)

- **`ci_smoke.py` INCLUDES the doc-anchor check** — a code edit that shifts an anchored line (e.g.
  `api_generate_dialogue` in `web_server.py`, anchored from `ARCHITECTURE.md:613`) FAILS ci_smoke
  until `check_doc_claims.py --fix`. Run `--fix` + commit the doc in the same change.
- **Survey-can-be-wrong is the norm** — the T1 survey mis-named `face_validator_gate.score_candidate`'s
  2nd param (`face_anchor`, not `reference_path`) and put `get_max_quality_params`/`RunPodComfyUI`
  in `quality_max` when they live in `workflow_selector`/`phase_c_assembly` (re-exported). ALWAYS
  verify load-bearing primitives at HEAD before encoding (ADR-013).
- **Layered review earns its keep** — 5 real T1 bugs were caught by the per-task code-quality +
  independent Lane V passes (the dead-seed + strength_clip-collapse were spec-compliant but
  semantically wrong; only a cold code-quality reviewer caught them). Keep dispatching independent
  (Rule #9) reviewers.
- **Shared tree, pathspec commits ALWAYS** — director is live on the same branch (`feat`); never
  `git add -A`/`commit -a`; `git diff --cached --name-only` then `git commit -- <paths>`. (Hit the
  shared-index hazard awareness throughout T1; no incident.)
- **`cinema_pipeline.py::CinemaPipeline` (live) ≠ `cinema/pipeline.py::CinemaPipeline`
  (preserved-primitive scaffold).** Same name, different files — don't confuse when grepping.
- **Two `validate_lora_quality` no longer exist** — the stub in `prep/lora_training.py` is GONE; the
  real oracle is `prep/lora_quality.py:validate_lora_quality`.

## Verification at write (ADR-013)
```
$ git rev-parse --short HEAD              → c95317d  (substantive tip bf86262)
$ git rev-parse --short main              → 3fa46f4
$ git merge-base --is-ancestor main HEAD  → (true; feat FF-able to main)
$ git status -sb | head -1                → ...feat/max-tier-provisioning [ahead 27]
$ .venv/bin/python scripts/ci_smoke.py            → OK
$ .venv/bin/python scripts/check_doc_claims.py    → All anchors checked — no drift.
$ grep -rn "CANDIDATE BUG" tests/unit/            → (empty, count 0)
$ .venv/bin/python -m pytest tests/unit/ -q       → 1607 passed, 0 failed, 10 subtests  (operator-verified at HEAD c95317d, 2026-06-04)
```
