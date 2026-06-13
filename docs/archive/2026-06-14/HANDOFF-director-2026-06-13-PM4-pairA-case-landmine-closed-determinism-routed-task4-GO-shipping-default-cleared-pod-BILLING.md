# Director transplant handoff — 2026-06-13 (PM4, Pair-A): case landmine F1 CLOSED + determinism siblings ROUTED + Task-4 pod acceptance GO (fix VALIDATED, cleared as shipping-default) + pod work queued. ⚠ POD RUNNING + BILLING.

**Supersedes** `docs/HANDOFF-director-2026-06-13-PM3-pulid-flux-chunk1-executed-pod-gate-pending-4seat-pairA.md`.
Pair-A director seat (image-generation + identity/realism lane) of the four-seat team.

## Ground truth at wrap (2026-06-13T~10:05Z)

- **HEAD `20a8ca7`** (operator's `--n` argparse fix). The 4-seat tree moves constantly — `git log -1` before every commit.
- **`ci_smoke.py` → OK** (~55 advisory PROGRAM-MANUAL doc-anchor drifts, non-gating).
- **Suite**: not re-run full (dirty 4-seat tree — standing rule). Scoped green this session: case-fix surface 166, determinism surface 146→111, all my commits TDD-green.
- **⚠ POD `07ed667`: RUNNING + ComfyUI UP + BILLING** (`/system_stats` → 200 at wrap). User brought it up ("pod is up use it"). **FLAG TO USER: the pod bills until stopped in the Novita console.** No further burns without spend-go; I did NOT burn this session (wrapped on user "handoff" before the N=4/experiment burns).
- **Branch ahead of origin; push USER-gated** (git reported 15 ahead at wrap vs ~72 at session start — verify origin/main sync; I pushed nothing).
- **Four seats live**: director (me, Pair A) + operator (Pair A) + director2 + operator2 (Pair B, video/assembly/delivery). All actively committing.

## ⭐ #1 PICKUP — Task-4 GO landed; make the Step-5 shipping-default close-out

**The production PuLID SDXL→FLUX fix is now EMPIRICALLY VALIDATED on the shipping fp8 pod.** The operator ran the Task-4 acceptance A/B (user-directed) via the committed instrument `scripts/_prod_pulid_acceptance.py` and scored it (`f21d9a4`):
- **OFF** (PuLID bypassed = plain FLUX txt2img): arc **0.620** — a *different generic woman* (coincidental prompt-match, NOT the identity).
- **ON** (production `pulid.json` as-shipped, ApplyPulidFlux, aria ref, start_at=0.0): arc **0.878** — aria identity LOCKED, at the ~0.87 single-clean-face ceiling.
- **delta +0.257**; peak VRAM 18.2 GiB. Artifact `logs/prod_pulid_acceptance_20260613.json` (logs/ gitignored; reproduce via `a43358f`).
- **All four plan Task-4 Step-4 GO criteria met**: material lift ✓ · **FaceDetailer-free binding** (figure read, no NO_FACE — answers the open node-600 question) ✓ · **fp8 compat** (node 112 `flux1-dev-fp8` bound to 0.878 — retires the fp8-vs-fp16 escalation) ✓ · **VISUAL photoreal** (operator viewed both; ON natural skin/no over-cook) ✓.

**DIRECTOR'S STEP-5 CALL (mine, recorded here): GO — the FLUX-native production PuLID fix is VALIDATED and cleared to be the shipping production default.** The fix is already committed in `pulid.json` (it IS what production renders); Task-4 removes the "not authoritative until validated" caveat. Remaining mechanics (next director, ~10 min doc work):
1. Mark plan `docs/superpowers/plans/2026-06-13-production-pulid-flux-fix.md` Task-4 = GO / Step-5 done.
2. Close out **ADR-024** in `DECISIONS.md` with the Task-4 result (0.620→0.878, +0.257, fp8 + FaceDetailer-free confirmed).
3. The fix is then push-ready (push remains USER-gated).

**Optional robustness before/after the flip (pod is UP):** N=4 seed sweep — `PYTHONPATH=. .venv/bin/python scripts/_prod_pulid_acceptance.py --n 4` (driver supports `--n`, fixed in `20a8ca7`; sweeps seeds 990011/22/33/44, ~$0.06, ~5 min). Not required by the plan (single-seed GO is decisive) — confirms the 0.878 isn't seed-luck. I CLAIMED the pod for this + the experiment burn (`8c5350b`) but wrapped before burning; **release/re-claim before running** so you don't collide with the operator (ComfyUI queues globally — serial).

## ⭐ #2 PICKUP — the dual-identity experiment burn (pod-ready)

`scripts/_prod_dual_lora_pulid.py` (two-character realism graft, ADR-024 track) — audited-GO + banked (operator Rule #22 SAFE + prior 4-lens audit `wf_3b4ddaf1`). Protocol: Rule #22 `--dry` pre-flight ($0) → `--n 1` (~$0.03, seed 990011) → **read arc FIRST** (man≥~0.75 cf the 0.870 bar) → **VIEW the artifact** (visual photoreal = PRIMARY GO) → then N=4. Distinct from ⭐#1 (single production PuLID). Pod + spend-gated (user gave "use it" spend-go this session; re-confirm next session — pod-auth is session-scoped).

## What LANDED this session (my Pair-A director commits)

| Commit | What |
|---|---|
| `d09eef1` | director-1 ONLINE (resumed post-PM3-wrap) |
| **`a924055`** | **case landmine F1 CLOSED** — `git mv Pulid.json → pulid.json` + case-pin regression test (asserts HEAD tree, FS-independent) + doc-sync (.agents/skills/ai-video-gen, PROGRAM-MANUAL) |
| `7b54af9` | fold operator Chunk-1 advisories F2 (start_at fallback 0.3→0.0) / F3 (node-301 PAG wiring guard) / F4 (docstring) |
| `a6f9627` | ACK operator — case landmine closed, convergence clean |
| `000cba7` | Rule #23 heads-up to director2 (continuity_engine shared seam) |
| **`970015b`** | **determinism siblings ROUTED** — 5 unrouted DeepFace sites (character_manager 369/385/396 + continuity_engine 164/181) → cv2 single-thread guard via new public `identity.validator.cv2_single_thread` alias + ARCHITECTURE.md anchor sync |
| `099a1ea` | close continuity determinism-routing test gap (adversarial-verifier finding) |
| `0bf135c` | determinism report to operator |
| `8c5350b` | pod-claim (N=4 + experiment) — wrapped before burning |

**Adversarial verification** (dispatched Sonnet agent): determinism fix = CONFIRMED-SOLID, the 5 sites are the COMPLETE unrouted set (all other face paths route through `IdentityValidator` → already guarded). 111 green.

## Case-landmine convergence (important coordination story)

Both Pair-A seats acted on the `Pulid.json→pulid.json` rename concurrently: the **user authorized the operator** to `git mv` while I was offline (`3a74960`), which **botched into a case-DUPLICATE** (core.ignorecase collapsed the delete side); my `test_production_graph_tracked_lowercase` caught it; my `a924055` cleaned + extended it (test + doc-sync); operator stood down + independently re-verified (`3fa3b4a`). Lesson logged to memory: case-only rename on macOS needs `git -c core.ignorecase=false` (or `rm --cached`+`add`) + verify against the OBJECT STORE (`git ls-tree`/`cat-file`), never the diff — `git diff`/`--stat` both LIE under ignorecase.

## Pair-A backlog (carried)

- **Step-5 doc close-out** (plan + ADR-024) — ⭐#1 mechanics.
- **N=4 robustness** (`--n 4`) + **experiment burn** (`_prod_dual_lora_pulid.py`) — pod-ready, pod UP.
- **Placement** (man-left/aria-right) for the experiment — DEFERRED below quality (masking proven inert); needs a clean render to measure.

## Sharp edges (this session)

1. **Main-seat git: NO `env -u GIT_INDEX_FILE`** (subagent/pytest-only). Commit through your per-seat index; `-m` BEFORE `--` on pathspec commits.
2. **Per-seat index pollution + phantom deletions are RAMPANT with 4 live seats** — `read-tree HEAD` to refresh your index; tight explicit pathspec is the safety boundary; verify against HEAD blobs/tree, never `git status`/`git diff` alone.
3. **Case-only rename**: object-store verification only (see convergence story).
4. **`git log -1` before EVERY commit** — HEAD moved ~20× this session.
5. **Pod is a SERIAL shared resource** — claim it (mailbox dispatch-claim) + confirm the other Pair-A seat stands down before any burn; ComfyUI queues globally, interleaved renders contaminate.
6. **Read driver code before running it** — caught the operator's `--n` arg bug (`280fff6`) by reading; they self-fixed (`20a8ca7`) before I ran. Empirical confirmation (run `--dry`) beats assuming.

## Cross-seat state at wrap

Four seats live. Operator (Pair A) ran Task-4 (GO) + built/fixed the N-seed driver + offered N=4. Pair B (director2/operator2) wrapped their inaugural session (video/assembly recon + W1.1 `9d90889` + 3 staged Tier-1 fixes); director2 ACK'd my Rule #23 heads-up (`b01fc9f`, no collision). My coordination consumed through cursor ~09:58Z. **POD RUNNING + BILLING — flag to user. $0 spent by me.**

*Last verified: 2026-06-13T~10:05Z — HEAD 20a8ca7; ci_smoke OK; Task-4 GO (0.620→0.878); case landmine + determinism siblings landed + verified; pod UP+BILLING; nothing pushed.*
