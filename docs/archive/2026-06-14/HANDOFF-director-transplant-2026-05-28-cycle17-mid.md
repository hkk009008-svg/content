# Director-Seat Transplant Handoff — 2026-05-28 (cycle 17 MID)

**Outgoing director-seat session:** cycle-17 entry → mid (continued from `0eaa366` cycle-16 close)
**Inheritor:** next director-seat
**Prior handoff:** `docs/HANDOFF-director-transplant-2026-05-28-cycle16-close.md`
**HEAD at handoff:** `23ba766` (operator's GitNexus phantom-rule proposal; last director commit `2e565f4`)
**Pytest:** 1103 passed / 5 skipped / 10 subtests (verified 2026-05-28 at HEAD `23ba766`: `1103 passed ... in 31.66s`)
**§15 smoke:** OK (verified at `23ba766`)
**Ahead of origin:** 23 commits, **unpushed** (push user-gated)
**Cycle-17 state:** entry P0 (C-D4) + Tier F DONE; user's 2 explicit features (dialogue + storyboard) DONE+verified; joint wire-all sweep IN PROGRESS (both seats).

---

## TL;DR — 60 seconds

Cycle-17 opened with the C-D4 PuLID setup harden + a GPU-free Tier F audit, then pivoted to **two user-requested production fixes**: (1) **dialogue** — shots now route to VEO native audio so lip-sync comes from one engine, with a reliable separate-lipsync fallback + a fixed blind auto-approve gate; (2) **storyboard (B-integrate)** — batched Kling generation split back into per-shot takes, behind the `storyboard_mode` flag. Mid-session this collided with an **operator-led "wire-all-unwired" sweep** (user directed "wire all together" to operator) — resolved via a **Rule #16 Shape-A partition** (director: controller.py-centric cluster; operator: disjoint prompt_optimizer/quality_max/research). Operator's cold **Lane V #18 caught a real CRITICAL** in my first dialogue cut (dialogue_close_up still resolved to KLING, not VEO) — fixed + independently re-verified CLEAN. **Everything is additive/behind-flag → no regression (1103 green).** The real dialogue/storyboard QUALITY is **GPU-gated** (task #5, pod down).

---

## Director commit ledger (this session)

```
2e565f4 feat(intent-notes): call-site pass-through (cross-seat split close)
8354c9a fix(storyboard): close F2b Lane V — partial-finalize retry-per-shot + per-shot classify
f9af2de feat(storyboard): wire batch mode behind storyboard_mode flag (F2b; closes F-A.1)
51e6886 feat(storyboard): split helper + reusable finalize-take helper (F2a, no behavior change)
561ad6b feat(dialogue): mandatory lipsync + fix blind auto-approve gate + assembler guard (F1b + F1a-CRITICAL fix)
933c794 test(dialogue): fix F1a review M1
a7c5816 feat(dialogue): route dialogue → native-audio engine + tag embedded-voice take (F1a)
e82524c fix(runpod-setup): close Lane V #14 F1+F2 (comment + restart-on-rerun)
ffacdc6 docs(tier-f): cycle-17 audit re-execution — 0 regressed + 2 NEW gaps
149ee5f docs(brief): A10 inventory — C-D4 script-side closed
345f697 fix(runpod-setup): close C-D4 script-side — PuLID-Flux + InsightFace + antelopev2 + node probe
(+ director mailbox coord events: d690142, c0e4ce0, 923b07d, 21ad506, …)
```
Operator's parallel (disjoint set): `57f63d6`/`1b3ca2d` (C-D3), `1cab3d2`/`fd67f2e` (C-D5), `2551595` (C-D2) — Phase-1 §8.6 pilot; `585554a`/`c721aa9` (img2img_denoise); `8f887f1` (intent_notes prompt-side); `9d52019` (project_manager doc).

---

## What's CLOSED + verified this session

| Item | Status | Refs |
|---|---|---|
| C-D4 PuLID setup harden (script-side) + Lane V #14 | ✅ | `345f697` + `e82524c` |
| Tier F audit re-execution (GPU-free) | ✅ 0 regressed, 2 NEW gaps | `ffacdc6` / `docs/TIER-F-AUDIT-cycle17-2026-05-28.md` |
| **Dialogue: native-audio routing + reliable lipsync + gate fix** | ✅ verified (mine + operator LV#18.5 CLEAN) | `a7c5816`+`933c794`+`561ad6b` |
| **Storyboard B-integrate (behind `storyboard_mode`, default off)** | ✅ reviewed + LV-fixed; closes F-A.1 | `51e6886`+`f9af2de`+`8354c9a` |
| intent_notes (cross-seat split) | ✅ | operator `8f887f1` + director `2e565f4` |

**Key save:** operator Lane V #18 caught that `_top_live_api_for_purpose("dialogue_close_up")` returns KLING_NATIVE (no native audio) — my F1a was a no-op for the primary dialogue case + my subagent's tests hid it (hardcoded `suggested=VEO`). Fixed via consumer-side override (`controller.py:894-915`). The two-seat independent review is what caught it.

---

## 🟡 OPEN ITEMS (next director)

1. **Push** — 23 commits ahead of origin, **user-gated**. Surface first.
2. **GPU validation (task #5)** — pod was down this session. When back: Tier B Korean-dialogue re-probe (assert embedded-voice OR lipsync_score≥threshold per dialogue shot) + a `storyboard_mode=on` run. **3 storyboard tuning items flagged for that run:** anchor=first-keyframe + others as image_references (tuning); split uses REQUESTED durations not actual Kling output length (last segment absorbs drift); batch motion prompt is thinner than per-shot. **+ dialogue tradeoff:** dialogue is now VEO-only (video_fallbacks dropped) — if VEO unavailable, shot relies on VEO internal cascade then fails (no KLING+lipsync degrade). Verify VEO availability on pod.
3. **Remaining director-cluster sweep** (the wire-all set, lower priority): image-engine routing (C3 HiDream trigger `controller.py:477` + C1 SD3_5_LARGE — the IMAGE twin of the dialogue VIDEO routing just done) · upscale dispatch (B5 Topaz + C2 SUPIR/CCSR, `controller.py:1551`) · the 8 inert `api_engines` toggles (phase_c reads) · `_build_transition_prompt` (cinema_pipeline.py) · cost-attribution cluster (+ `provider_for`; this is also Tier F NEW-2's theme).
4. **Storyboard B-integrate ADR** — director-owed (DECISIONS.md). Design = batch Kling → `split_video_into_segments` → `_finalize_motion_take(record_cost=False)` per segment; cost-once; partial-finalize retries per-shot; behind flag.
5. **Unprocessed operator events (Rule #8):** `23ba766` GitNexus phantom-rule-correction proposal (UNREAD) + `0952dd8` memory-candidate "transplant-pointer currency" (director-owned memory write, still pending). Process both.

---

## What the next director needs to know

1. **This was a JOINT wire-all-unwired effort** (user → operator: "wire all together / deeper coverage / wire not delete"). The complete unwired-feature inventory (Tier-F 9 + ~24 NET-NEW) is in operator's convergence event `coordination/mailbox/sent/2026-05-28T08-43-31Z-operator-to-director-convergence.md` + `45eea64`. The **partition** (director controller.py-centric / operator disjoint) is in `923b07d` + `2026-05-28T09-32-41Z-director-to-operator-decision.md`. Honor it; surgical-stage named files only (both seats parallel-editing).
2. **dead-utils policy** (user "wire not delete"): wire the ones with a sensible call site; **flag genuinely-purposeless ones to user** (don't fabricate calls). B2 `evaluate_generation_quality` already flagged-to-user by operator.
3. **Rule #16 Shape-A dogfood:** this session is a strong N-instance — both seats wiring concurrently → operator surfaced the collision → partition convergence → independent Lane V caught a CRITICAL the originating seat + its own reviewer missed. Worth a retrospective data point.
4. **Pytest 1103; smoke OK. Everything shipped is additive or behind a default-off flag — no regression.** Keep it that way; the sweep items are mostly wiring inert toggles / dead code, low blast radius.
5. **Tasks #1-4 complete, #5 (GPU validation) pending** in the TaskList.

---

## Mailbox state at handoff

Director cursor: consumed through operator's `2026-05-28T09-43-57Z` decision (intent_notes signal — acted on via `2e565f4`). **UNREAD:** `23ba766` GitNexus phantom-rule proposal + `0952dd8` memory-candidate. Last director-sent: `2026-05-28T09-32-41Z` (resume + consent). Operator is live + executing their disjoint set (research fns in progress).

---

## Sign-off

Cycle-17 MID. User's two explicit asks — **dialogue lip-sync** and **storyboard (B) integrate** — are built, cold-reviewed, and verified green (1103). The hard validation (real Veo dialogue sync + storyboard coherence) waits on the GPU pod (task #5). Joint wire-all sweep continues under the converged partition. Push, the sweep remainder, the storyboard ADR, and two unread operator events are the open threads.

Signed,
Director-seat — 2026-05-28 (cycle 17 mid).
