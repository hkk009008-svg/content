---
from: operator
to: director
kind: dispatch-claim
related-commits: f0e5c0c, 5fd2e58, 0ecda24, 0f6527f
related-rules: 2, 8, 9, 14
urgency: standard
silent-accept-window: 5min
---

**Status:** 🚀 Dispatch-claim. **User-principal execution authorization received** at operator session — "begin all testing". Operator-seat claiming Tier A pre-flight; will surface tier-end findings + Tier B gate to user post-Tier-A.

---

## Claim scope

**Tier A pre-flight** (brief §3 A1-A9; ~30 min wall-clock; $0).

Cells covered in this claim:
- **A1** working tree state + git log baseline
- **A2** static gates (`scripts/ci_smoke.py` + `web && npx tsc --noEmit` + `web && npm run build`)
- **A3** full unit suite — brief baseline 866 STALE; cycle-15 actual baseline 925/3/0 (will note doc drift in artifact)
- **A4** ARCHITECTURE.md §15 smoke (same script as A2)
- **A5** RunPod ComfyUI pod HTTP/2 reachability — verified GREEN at session start; will re-verify at execution start
- **A6** LLM provider keys + budget headroom — A6 closed at `0ecda24` `override=True` fix; will re-verify ANTHROPIC + OPENAI + FAL load post-fix
- **A7** Identity validator weights (GhostFaceNet via DeepFace)
- **A8** Sample project ready + baseline `domain/projects/` count delta = 0 setup
- **A9** ComfyUI workflow probe (PulidFluxInsightFaceLoader + 8 other custom nodes + CheckpointLoaderSimple introspection) — verified GREEN at brief v1.0 ship per `0f6527f` body; will re-verify

## Artifact format

Per `0f6527f` execution-begin handoff §"Step 2": single Tier A artifact at `docs/test-cells/A-2026-05-27T19-XX-XXZ.md` covering all A1-A9 cells. ONE commit at tier-end; subject form `test(cell): A-tier <PASS|MINOR|MAJOR|FALSIFIED> — Tier A pre-flight A1-A9`.

## Tier-end disposition

Per brief §1.5 Lane V cadence + CC-1 coalescing:

- **A1-A9 are verification-only cells (no generation, no code change).** Tier A produces 1 artifact commit; Lane V range-review at tier-end MAY be skipped if zero code paths touched (artifact-only commits don't change shipping code). Operator default: send `verification-report` event summarizing A1-A9 outcomes; only escalate to Lane V if a cell surfaces a code defect.
- **Cross-tier dispositions:** any A-tier finding affecting Tier B prediction set → flag explicitly in tier-end report; director-side fold or defer disposition per Rule #15 advisory matrix.

## Coordination with director

Per Q9 sync joint-seat: director-seat MAY observe in parallel and contribute findings independently. **No director action required** unless:

1. A Tier A cell surfaces a CRITICAL → director Lane V dispatch parallel per Rule #9 §"Parallelism"
2. Director-seat wants to claim concurrent Tier A re-run for cold-context independent verification (welcome; non-conflicting since A1-A9 are read-only verification commands; both can run identical sequence and compare)
3. Tier B authorization conversation surfaces before operator-side Tier A complete — defer to user-principal coordination

**5-min silent-accept window** standard. If director-seat wants to counter-claim or refine scope, surface via mailbox before T19:24:51Z (~5 min from this event timestamp).

## TaskCreate state

Operator session has 7 tasks created for the full Tier A→B→C→D + final-report workflow. Task 1 (this dispatch-claim) is `in_progress`. Tasks 2-7 are `pending`. Cycle-15 close pattern: TaskCreate is used here per CLAUDE.md ≥5-sub-task threshold (7 tasks > 5 threshold; multi-tier execution warrants tracking).

## Cost envelope (cumulative through this dispatch-claim)

| Tier | Estimated cost | Status |
|---|---|---|
| Tier A (pre-flight) | $0 | Starting now |
| Tier B (single-shot) | $3-7 | Gated on Tier A green + user surface |
| Tier C (full reel) | $8-15 | Gated on Tier B green + user re-auth |
| Tier D (parameter sweep) | $1-5 | Optional; gated on Tier C green |
| **Cumulative cap** | **$50 hard / $40 soft** | Enforced by `cost_tracker.py` |

User authorization at session: "begin all testing" — broad authorization covering all tiers; operator-side discipline: surface findings + cost between tiers; do not silently barrel through if any red emerges.

---

Signed,
Operator-seat — 2026-05-27 cycle 16 entry, Tier A pre-flight dispatch-claim under user-principal "begin all testing" authorization
