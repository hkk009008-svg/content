# Director transplant handoff — 2026-06-13 (PM3, Pair-A): production PuLID SDXL→FLUX fix DESIGNED + PLANNED + Chunk-1 EXECUTED (offline code landed, TDD-green); pod acceptance gate is the only thing left + it's BLOCKED on pod-up. 4-SEAT scale-up LIVE. Experiment graft still audited-GO + banked.

**Supersedes** `docs/HANDOFF-director-transplant-2026-06-13-overcook-structural-prod-hybrid-driver-built.md`.
This is now the **Pair-A** director seat (image-generation + identity/realism lane) of a **four-seat** team.

## Ground truth (verified at wrap, 2026-06-13T~09:00Z)

- **HEAD `c5199de`** (mine). Branch many commits ahead of origin; **push USER-gated** as always.
- **Smoke OK** (`scripts/ci_smoke.py` → OK; ~55 advisory PROGRAM-MANUAL doc-anchor drifts, not a gate).
- **Suite: NOT re-run full** (dirty 4-seat shared tree — my standing "no pytest against a dirty shared tree" rule). Verified instead: **scoped suite 152 passed / 0 failed** over my blast radius (test_pulid_production_flux + test_workflow_selector + test_cascade_logic + test_max_quality_templates); the 5 new PuLID tests pass. Operator's last full count was **2248/2** (their `d48b58b`).
- **Mailbox: director cursor `2026-06-13T08:54:01Z`, 0 unread** at last consume.
- **POD 07ed667: DOWN.** User reported "pod is not running"; my read-only `/system_stats` went **200 (07:16Z) → 502 (07:29Z)**. NO BURN happened, NO spend this session. ⚠ A 502 (gateway up / upstream down) is ambiguous on billing — flag to the user to confirm the instance is *stopped* in the Novita console, not just ComfyUI-crashed-while-VM-bills. Pod-work auth is session-scoped (re-obtain).
- **FOUR SEATS LIVE:** `director` (me, Pair A) + `operator` (Pair A) + `director2` + `operator2` (Pair B). Operator-1 WRAPPED (`979b880`); operator2 came online (`b324f5d`).

## ⭐ #1 PICKUP — the production PuLID fix: Chunk 1 is DONE; only the pod gate remains

**The shipping production tier rendered `COMFYUI_PULID` portraits through SDXL PuLID nodes on a FLUX UNet = a structural no-op (zero face lock).** This session I took it through the full brainstorm→spec→plan→execute flow. **Chunk 1 (offline code) is committed and TDD-green:**

- **`a1103bd`** — `Pulid.json` nodes 99/100/101 → FLUX-native (`PulidFluxModelLoader`/`ApplyPulidFlux`/`PulidFluxEvaClipLoader`, `pulid_flux_v0.9.1`, `start_at=0.0`, `model:["112",0]` direct — no LoRA, single production PuLID) + new `tests/unit/test_pulid_production_flux.py` (pins the FLUX classes; the bug was **test-dark**).
- **`f05c83b`** — `workflow_selector.py`: production `pulid_start_at` → 0.0 for portrait/medium/wide/action (**the crux** — `apply_workflow_params` writes `start_at` onto node 100 at runtime, so the SDXL-era 0.2–0.35 would overwrite the graph's 0.0 and re-suppress the FLUX coarse-identity window) + fixed the stale `ApplyPulid`/`method` docstring (line 512). `MAX_QUALITY_TEMPLATES` untouched (separate tier).
- **`c5199de`** — updated `test_workflow_selector::test_sets_correct_node_values` (it pinned the *applied* `start_at == 0.2`; my grep for the *template key* `pulid_start_at` missed it — same blind spot the plan-reviewer had; the plan's Task 3 anticipated this structural update).

**ONLY remaining: Task 4 = the pod acceptance gate (BLOCKED on pod-up + user spend-go).** Plan: `docs/superpowers/plans/2026-06-13-production-pulid-flux-fix.md` Chunk 2. Before/after identity render on the fixed graph (PuLID-off baseline vs PuLID-on) using the now-deterministic scorer (operator's `d48b58b`/`68e9722`). GO = identity rises materially toward ~0.87 single-face + visual photoreal + a face is detectable (no NO_FACE → confirms FaceDetailer-free binding). Two empirical unknowns it settles: **fp8 compatibility** (prod node 112 = `flux1-dev-fp8` vs max's fp16) and FaceDetailer-free binding. **The fix is committed locally but is NOT the shipping default until this gate passes** (don't push as authoritative until validated). Spec: `docs/superpowers/specs/2026-06-13-production-pulid-flux-fix-design.md`; ADR-024.

**Next operator (Pair-A) is set to independently verify Chunk 1** (operator-1's `979b880`).

## ⭐ #2 — the experiment graft (dual-identity realism), still parked, still ready

`scripts/_prod_dual_lora_pulid.py` @ c5d0a80 (the dual-PuLID+LoRA realism experiment) is **audited GO + banked** (operator Rule #22 SAFE + my independent 4-lens pre-burn audit `wf_3b4ddaf1` = GO/0-blockers + blob byte-confirmed). Burns on pod-up + spend-go (`--n 1`, ~$0.03, seed 990011). Read arc man≥~0.75 + VISUAL photoreal. This is the *two-character* track (ADR-024); distinct from ⭐#1 (single production PuLID).

## What else landed this session

- **ADR-024 (`a7a87b4`)** — production-tier identity GRAFT decision (reject tier-unification + post-pass toggling); records over-cook-structural + the prod-PuLID no-op data-integrity finding.
- **Spec + plan** for the production fix, both through the superpowers reviewers (spec `4c018ff`→`ef72cb9`; plan `f7eb9f6`→`874138f`) — both reviewers independently **re-verified every node delta / file:line vs live code**.
- **4-SEAT scale-up** (user directive, relayed via operator, principal-confirmed in my session): I ACK'd the mechanics + cleared the lane-agnostic tooling cutover (`948f551`); relayed the principal-confirmed **lane split FINAL** (`32b63b1`): **Pair A = image-gen + identity/realism (us)**, **Pair B = video + assembly + delivery**. Operator landed the cutover (`813d0d4`), lanes ACCEPTED (`85f8bde`). Cross-director ADR sign-off = new Rule #23.

## Pair-A backlog (carried)

- **Pod acceptance gate for the PuLID fix** (⭐#1 Task 4) — pod-blocked.
- **Experiment graft N=1 burn** (⭐#2) — pod + spend-blocked.
- **Route the 2 data-integrity siblings** the operator flagged: `domain/continuity_engine.py:181` + `domain/character_manager.py:396` (same identity/no-op class; our lane) — after the PuLID fix.
- **⚠ CASE-SENSITIVITY LANDMINE (new, found this session):** the graph file is git-tracked as **`Pulid.json`** (capital P) but ALL code opens **`pulid.json`** (lowercase, e.g. `phase_c_assembly.py:204`). Works on case-insensitive macOS (dev + the local arc/smoke); the pod never opens it by name (drivers read it on macOS then submit JSON). But on a case-SENSITIVE checkout (Linux CI/pod) `open("pulid.json")` would fail → production render falls to the cascade. Latent portability bug in our lane — fix = `git mv Pulid.json pulid.json` (careful on case-insensitive FS: use `git mv -f` via a temp name) + a test. Not done.
- Placement (man-left/aria-right) for the experiment — DEFERRED below quality (masking proven inert; levers = prompt-order/seed/PuLID-swap, re-measure on a clean render).

## Sharp edges (this session — read before committing)

1. **Do NOT prefix your OWN (main director seat) git with `env -u GIT_INDEX_FILE`.** That's a SUBAGENT hygiene rule (dispatch templates). The main seat commits THROUGH its `GIT_INDEX_FILE` (the per-seat index). I slipped once — `env -u git commit` operated on the (stale) default index and failed. Use plain `git` for your commits; reserve `env -u GIT_INDEX_FILE` for **pytest** (it breaks temp-repo tests) and for subagents. (The plan's pre-flight `env -u` note is correct for *subagent* execution, wrong for main-seat — I ran main-seat.)
2. **The graph file is `Pulid.json` (capital P), not `pulid.json`** — pathspecs are case-sensitive even though the FS isn't. `git ls-files | grep -i pulid` to get the real name; commit with it or you get "pathspec did not match" (or worse, a case-collision second entry).
3. **Per-seat index pollution is REAL and looks scary** — `git status` showed the operator's committed cutover files as `MM`/`D` + a "264 deletions" phantom in `git diff HEAD`. These are NOT real edits/deletions — they're my stale per-seat index + skip-worktree bits disagreeing with HEAD. **Verify against the HEAD blob:** `git diff --no-index <(git show HEAD:path) path`. And **tight explicit pathspec on every commit is the safety boundary** — a partial commit (`git commit -- <only my files>`) structurally excludes the pollution. Never bare `git commit`/`git add -A`.
4. **Don't run the full pytest suite against the 4-seat shared tree** — peer WIP contaminates + misattributes. Scope to your change's blast radius; cite `ci_smoke` (self-contained) + the scoped run.
5. **`git log -1` before EVERY commit** — with 4 live seats the HEAD moves constantly (it moved under me ~10 times this session). My commits all landed clean because of the guard + pathspec.

## Cross-seat state at wrap

Four seats live. Operator-1 wrapped (`979b880`) → next Pair-A operator verifies my Chunk 1 + the pod-portability re-baseline gate. Pair B (`director2`/`operator2`) owns video/assembly/delivery, just stood up. My coordination is consumed through cursor `08:54:01Z`. Pod DOWN. No money spent this session.

*Last verified: 2026-06-13T~09:00Z — HEAD c5199de; ci_smoke OK; scoped suite 152/0; Chunk-1 commits a1103bd/f05c83b/c5199de; pod DOWN (200→502); 4 seats live.*
