# Director transplant handoff — 2026-06-08 — portrait Phase-2 spec+plan COMPLETE (execution-ready) + operator deferred-minors batch green-unpushed

*Author: director-seat. Companion: operator transplant handoff `f18c7c6`
(deferred-minors batch). Read this FIRST if you are the next director-seat.*

---

## 0. State at handoff (verified)

| Fact | Value | Source |
|---|---|---|
| **HEAD** | `f18c7c6` at draft-time (operator transplant handoff); **this doc commits on top** → next director run `git log -1` | `git rev-parse HEAD` |
| **Branch** | `feat/max-tier-provisioning`, **ahead 19** of `origin/feat` (this session's arc, UNPUSHED) | `git status -sb` |
| **`main`** | `c28f9e6` == `origin/main` — **GREEN** (the merge-gate target; PARKED per user) | `git rev-parse` |
| **`origin/feat`** | `5c81ebd` (stale; local feat is 19 ahead) | `git rev-parse` |
| **Suite** | **1789 passed / 0 failed** (director re-run this session, `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q`; 2 benign pricing warnings, 10 subtests) | §6 stamp |
| **ci_smoke** | `OK` | `.venv/bin/python scripts/ci_smoke.py` |
| **Mailbox (director)** | 0 unread; cursor `2026-06-08T00:58:04Z` | `seen/director.txt` |

Nothing owed by the director at handoff. Two tracks live this session, both
on `feat`, **file-disjoint, zero conflicts**:

---

## 1. THIS SESSION'S WORK (director track) — portrait Phase 2 spec+plan

User directed "proceed with the portrait phases." Ran the full brainstorm →
spec → writing-plans flow for **Phase 2 (native 9:16 image keyframes)**, the
prerequisite to Phase 3 (video + un-gate). Grounded by a **Rule #17 read-only
survey** (5 parallel scouts + synthesis) + director spot-checks; every cited
file:line verified at HEAD.

**Deliverables (COMPLETE, both passed 2 independent reviewer passes):**
- **Spec:** `docs/superpowers/specs/2026-06-08-portrait-phase2-native-keyframes-design.md`
  (`f40f39c` + ctx-read refinement `a4faa9a`).
- **Plan:** `docs/superpowers/plans/2026-06-08-portrait-phase2-native-keyframes.md`
  (`a59945f` + plan-review advisory `f429ff0`).

**The design in one paragraph:** add a pure `portrait_swap(w,h,aspect)` +
`fal_image_size(aspect)` to `cinema/aspect.py` (Phase-1's single source of
truth); read `aspect_ratio` from the **already-threaded `ctx`** via
`get_project_setting(ctx, …)` (NO new param, NO `controller.py` edit); apply the
transpose at the 6 verified geometry sites. **Latent strategy = transpose each
tier's validated landscape latent** (prod node-102 1344×768→**768×1344**; max
node-102 1024×576→**576×1024**; max node-950 final (3840,2160)→**(2160,3840)**;
Pollinations URL 1344×768→768×1344; FAL `aspect_ratio`→`"9:16"` + `image_size`
`landscape_16_9`→`portrait_16_9`). **Gate stays closed** (`SUPPORTED_ASPECT_RATIOS`
untouched) — generators first, un-gate last (Phase 3). Backward-compatible
(16:9 / ctx-less = literal no-op). ~30-40 LoC + a unit test file.

### ⭐ #1 PICKUP — EXECUTE the Phase-2 plan via subagent-driven-development

The plan is 5 TDD tasks (each: failing test → run → implement → run → commit):
1. `cinema/aspect.py` — `portrait_swap` + `fal_image_size` (pure; extend
   `tests/unit/test_cinema_aspect.py`).
2. Production ComfyUI — ctx read + node-102 transpose (`phase_c_assembly.py`;
   integration test via the `RunPodComfyUI.queue_prompt` capture seam).
3. FAL ×3 + Pollinations fallbacks (`phase_c_assembly.py:515/:534/:555/:570`;
   test via the `_fal_flux_fallback` `:417` direct-call + `stub_fal` precedent
   in `test_phase_c_assembly_provenance.py`; Pollinations = urllib stub).
4. Max tier — node-102 override + node-950 transpose + ctx read
   (`quality_max.py`; test via `_load_max_workflow` pure-inspection per
   `test_quality_max_prune.py`, or queue_prompt-capture fallback).
5. Full-suite + smoke verify; confirm the gate is still `["16:9"]`.

Run via **subagent-driven-development** (CLAUDE.md multi-task loop: fresh
implementer per task + spec-compliance review + code-quality review). It is
director-driven Lane B (multi-file cross-tier). **Re-verify HEAD + re-grep the
cited `phase_c_assembly.py`/`quality_max.py` lines before dispatch** (they drift
if either seat touches those files). The plan's §"Project conventions" carries
the `env -u GIT_INDEX_FILE` pytest rule + D-a pathspec-commit rule.

**On-pod validation (manual, post-merge):** unit tests prove the plumbing; only
a GPU-pod render proves 9:16 keyframes look right (D5's empirical claim — that
768×1344 / 576×1024 are *good* FLUX latents). Pod has been intermittently down
(handoffs) — wire+unit-test now, validate on-pod when up.

---

## 2. OTHER TRACK (operator) — deferred-minors batch, green-UNPUSHED

Operator shipped a **7-item USER-DIRECTED batch** (10 commits `fbb313a..ff05d8c`,
their handoff `f18c7c6`): item C `creative_llm` retired-id read-migration (the
6/15 deadline; `chief_director.py:117` was already `claude-sonnet-4-6` pre-batch
— my handoff ticket is CLOSED), B `diagnose_clip` identity source (+ in-batch
**CRITICAL** caught & fixed `9aed3ce` — lip_sync re-keying `dialogue_cache_key`
→ paid-TTS regen), E/T-C reaper spec, F/T-D estimator key mirror, G `judge_map`
404'd model id, A/D test pins. **Suite 1789/0** (their stamp), double-reviewed
(spec + quality per item) + cross-cutting SHIP. **NOT pushed — merge to main is
USER-GATED and PARKED ("Not now," 2026-06-08).** If user says merge: independently
re-verify green at the exact tip, then D-a-safe FF (push verified SHA, no
checkout while peer active).

**Filed follow-up T-E** (pre-existing, not this session): `controller.py:252-257`
+ `:1459-1462` still pass in-frame chars to `_ensure_scene_audio` (same class as
the CRITICAL) + shared char-filter-helper extraction (kills 4-site mirror drift)
+ 2 hygiene minors (`cost_tracker.py:80-81`, `web_server.py:373`).

---

## 3. OPEN ITEMS / FOLLOW-UPS

- **Portrait Phase 3** (per-provider 9:16 video + the final un-gate) — own-spec-later.
  Spec must FIRST pin the live provider inventory (Rule #17 survey found the
  Phase-1 §7-D matrix UNDER-counts: only **Veo** is API-capable for native 9:16
  today and it's not wired; **Kling** has no aspect param; **Sora/LTX/Hedra**
  unverified vs vendor docs; **Runway has TWO ratio sites** `phase_c_ffmpeg.py:363`/`:682`
  + **Seedance** `:718` — neither in the spec's Phase-3 sentence). Likely a
  pragmatic **Phase-3a (Veo + crop/pad-for-Kling) → 3b (verify the rest)** split.
- **Merge-gate** — operator batch (green-unpushed) + this session's portrait docs;
  user PARKED ("Not now").
- **T-E** (above) — operator-filed.
- Carry-forwards from prior handoff: **F5** `visual_findings` FE render; **Rule #18**
  MANUAL/digests `chief_director.py` anchor sweep (~30 anchors).

---

## 4. COORDINATION STATE

- **Director cursor:** `2026-06-08T00:58:04Z` (`seen/director.txt`); 0 unread.
- **Mailbox events this session (director→operator):** `2e53409` (ack dispatch-claim
  + flag portrait track), `9abf654` (ack verification-report). Operator→director:
  dispatch-claim `00:13:08Z`, verification-report `00:58:04Z` — both consumed.
- **Presence:** update `coordination/presence/director.md` `status: wrapping` +
  clear `current_task` at session-end (Rule #19).
- **D-a active:** per-seat `GIT_INDEX_FILE`; commit with pathspec; `env -u
  GIT_INDEX_FILE` for pytest. Two-track work this session proved file-disjoint
  (the spec refinement dropping the `controller.py` edit removed the one overlap).

---

## 5. KEY DECISIONS THIS SESSION (for the audit trail)

- Two specs P2→P3 (not combined); Phase 2 first as prerequisite. (user)
- Full fallback coverage (ComfyUI + FAL + Pollinations emit 9:16). (user)
- Project-level aspect granularity (not per-shot). (default, user-confirmed scope)
- Approach A: geometry in `cinema/aspect.py`. (user)
- Latent = transpose tier's validated landscape latent (D5). (director, on-pod-validate)
- Read aspect from already-threaded ctx (no param, no controller edit). (refinement
  from spec-review's :624 finding — strictly simpler + zero operator overlap)

---

## 6. VERIFICATION STAMPS (ADR-013)

```
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q
  → 1789 passed, 0 failed, 2 warnings, 10 subtests passed in 30.70s   (director re-run, 2026-06-08)
$ .venv/bin/python scripts/ci_smoke.py
  → OK
$ git rev-parse --short main origin/main
  → c28f9e6  c28f9e6   (GREEN; merge-gate parked)
$ grep -n SUPPORTED_ASPECT_RATIOS cinema/aspect.py
  → 23:SUPPORTED_ASPECT_RATIOS: list[str] = ["16:9"]   (gate closed — Phase 2 not yet executed)
```
