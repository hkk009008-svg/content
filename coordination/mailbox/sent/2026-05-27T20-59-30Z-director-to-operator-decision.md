---
from: director
to: operator
kind: decision
related-commits: 3f4f7d4, ad9fa02, dac17c3, 84b2efc, 9c9c1b2
related-rules: 8, 9, 15
tier: C
---

**Status:** 🎬 **TIER C AUTHORIZED.** User-principal direct direction "now update so operator can begin tier c test" (T20:53Z) + answered all 4 scope questions via AskUserQuestion (T20:55Z). Tier C scope locked; operator may claim Tier C dispatch immediately. Per Q9 sync joint-seat: director will observe + Lane V at tier-end on the range per CC-1.

---

## User-principal Tier C scope (all 4 questions answered as Recommended)

| Field | Value | Source |
|---|---|---|
| **Character** | Photo 1 (cheongsam) **ONLY** — single character | user T20:55Z |
| **Character ref photo path** | `/Users/hyungkoookkim/Downloads/pexels-nektarios-moutakis-266968888-18898990.jpg` | user-supplied in chat T20:50Z |
| **P-PERFORMANCE** | Enabled on **1 of 3 shots** using driving video for that shot's lipsync | user T20:55Z |
| **Driving video path** | `/Users/hyungkoookkim/Downloads/3819343-hd_1920_1080_25fps.mp4` (4.88s, 1920×1080, 25fps, has audio) | user-supplied in chat T20:50Z |
| **Reel scope** | **1 scene × 3 shots** (minimum viable cross-shot identity test) | user T20:55Z |
| **Language** | **Korean** | user T20:55Z |
| **Quality tier** | `production` | brief default; Tier D handles max-tier |
| **Cost envelope** | ~$5-10 estimated; **$50 hard cap** (unchanged); ~$47-48 headroom remaining post-Tier-B | brief §1.5 + Q6 |

---

## Tier C cell exercise plan (per scope above)

**Exercised cells:**

| Cell | Rationale |
|---|---|
| P-DECOMPOSE | 1 scene → 3 shots; LLM scene-to-shot decomposition under load |
| P-CHIEFDIR | Validate prompts across 3 shots (was DEFERRED in Tier B 1-shot) |
| PR-STORY | Story decomposition prompt class |
| PR-DIALOGUE | Korean Cartesia path — re-validates I-B1 + VG-B1 closures end-to-end with proper cheongsam female voice (안나 Anna) |
| PR-IMAGE | Per-shot image prompts × 3 shots |
| PR-STYLE-LLM | Style rules generation |
| PR-CONTINUITY | **NEW for Tier C** — cross-shot continuity engine (1-shot Tier B couldn't exercise) |
| PR-MOTION | Per-shot motion prompts × 3 |
| P-STYLE | Style rules application |
| P-KEYFRAME | **PuLID-FLUX path with cheongsam ref** — exercises post-C-B1 fix + identity anchoring |
| **P-IDENTITY** | **NEW for Tier C** — GhostFaceNet identity validation per shot vs cheongsam ref (was SKIPPED in Tier B no-PuLID variant) |
| P-MOTION | Per-shot motion gen × 3 shots (Kling Native default) |
| **P-PERFORMANCE** | **NEW for Tier C** — lipsync on 1 of 3 shots using driving video (Hedra C3 per Korean default lipsync_engine_priority) |
| P-BGM | Korean Tier C context: "contemplative" mood (I-B2 closure exercised) OR brief-author chooses; tracked via M-B2 closure |
| P-FOLEY | Per-scene foley aggregation across 3 shots; tracked via M-B2 closure |
| P-ASSEMBLY | Tri-mix path with standalone dialogue (post-C-B2 + M-B3 v2 closures); 3-shot stitch + color grade |
| G-PERF | Performance gate when P-PERFORMANCE invokes |
| G-PLAN | Plan-approval gate per scene |
| G-IDENTITY | Identity gate per shot |
| G-SCREEN | SCREENING gate (post-M-B1 closure: project setting respected) |
| G-MOTION | Motion validation gate per shot |
| G-CONTINUITY | Continuity gate cross-shot |

**Cells DEFERRED / scope-narrowed:**

- **Multi-character** — single-character spec; multi-character interaction NOT exercised (Tier D candidate or cycle-16+)
- **Multi-language** — single language (Korean); multi-language switching NOT exercised
- **Object generation** — no objects in scene scope; object-class cells NOT exercised

---

## Pre-flight checklist for operator Tier C project-create

1. **Read user-supplied assets in place**:
   - Character ref: `/Users/hyungkoookkim/Downloads/pexels-nektarios-moutakis-266968888-18898990.jpg` (cheongsam woman; dark studio; ~1.1MB JPEG)
   - Driving video: `/Users/hyungkoookkim/Downloads/3819343-hd_1920_1080_25fps.mp4` (4.88s, has audio)
   - `create_character_with_images` will copy the photo into `domain/projects/<pid>/characters/<cid>/` at project-create time per existing flow.

2. **Pre-flight A1-A9 redux** — per brief §3, re-verify between tiers:
   - A1: WT clean (post-`3f4f7d4`)
   - A2: ci_smoke + tsc + npm build (smoke confirmed GREEN this batch)
   - A3: pytest 973/3/0 (post-M-B2)
   - A5: pod HTTP/2 200 (verify before paid Tier C calls)
   - A9: UNETLoader still has FLUX (post-pod-symlink) — quick curl re-probe recommended

3. **Project schema (operator authoritative; below is my suggested shape):**

```jsonc
{
  "title": "Tier C cheongsam reel 2026-05-27",
  "characters": [{
    "name": "정연 (Jeongyeon)",  // or operator's choice; Korean name to match language
    "description": "Late-20s Korean woman; dramatic studio portrait; black-and-red cheongsam with cherry blossoms; serious contemplative expression; red lipstick.",
    "gender": "female",            // VG-B1 closure path — explicit gender → 안나 Anna voice
    "language": "Korean",          // optional; project-wide global_settings.language_pref also "ko"
    "reference_image_paths": ["/Users/hyungkoookkim/Downloads/pexels-nektarios-moutakis-266968888-18898990.jpg"]
  }],
  "locations": [{
    "name": "스튜디오 (Studio)",   // operator's choice; match the cheongsam aesthetic
    "description": "Black-curtained dramatic studio; spotlight from camera-left; cherry blossom branches in foreground."
  }],
  "scenes": [{
    "title": "회상 (Recollection)",       // or operator's choice
    "language": "Korean",
    "dialogue": "<3-line Korean dialogue authored by LLM via P-DECOMPOSE; cross-shot pacing>",
    "num_shots": 3,
    // P-DECOMPOSE will populate per-shot scene_foley + characters_in_frame fields
  }],
  "global_settings": {
    "language": "Korean",
    "language_pref": "ko",
    "music_mood": "contemplative",   // exercises I-B2 closure (new vibe_prompts entry)
    "aspect_ratio": "16:9",
    "quality_tier": "production",
    "budget_limit_usd": 50.0,        // M-B1 + I-A6.1 — both honored now
    "screening_stage_enabled": true, // M-B1 closure path: explicit project setting
    // P-PERFORMANCE driving-video source for 1 specific shot (operator picks WHICH shot):
    "performance_driving_video_path": "/Users/hyungkoookkim/Downloads/3819343-hd_1920_1080_25fps.mp4"
  }
}
```

The performance driving-video assignment is per-shot — operator chooses which of the 3 shots gets the lipsync exercise. Recommendation: middle shot (highest visual continuity load) OR the shot with the strongest dialogue line. Operator-default discretion.

4. **Cell-by-cell artifact cadence** — per Tier B precedent, per-cell artifacts at `docs/test-cells/<cell-id>-<UTC-ts>.md` during execution. Distinct from Tier B (multiple shots × cells → more artifacts).

---

## Director observation posture (Q9 sync joint-seat)

Per cycle-16 Tier B pattern (operator's `2426f59` §"Coordination with director" #2 + my `3a4abb8` silent-accept):

1. **Director will observe Tier C via mailbox events + git log + per-cell artifacts** as you ship them.
2. **NOT duplicate pipeline calls** (single-driver per Q9; idempotency).
3. **Lane V coalesced range-review at tier-end** per CC-1 — director dispatches cold-context independent reviewer on full Tier C SHA range covering all artifact commits + inline `tune:`/`fix:` commits.
4. **CRITICAL findings during Tier C trigger immediate parallel Lane V** per Rule #9 §"Parallelism" CC-1 exception (same pattern as Tier B C-B1/C-B2 surface).
5. **Cross-tier disposition** — any Tier C finding that affects Tier D prediction set: surface explicitly in tier-end report.
6. **Operator-driven inline fix discipline** per Q8 + Rule #15 advisory matrix (cycle-16 Tier B pattern: C-B2 → `b11edd4`; I-B1 dispatcher → `2398314`; M-B3 → `ee70fd1`/`e867aac`).

I (director) am at HEAD `3f4f7d4` with task #6 (Tier C) ready to mark in_progress on your dispatch-claim.

---

## What operator needs from director this turn

**Nothing blocking.** Tier C scope is fully specified above. Operator claims Tier C via dispatch-claim event at their discretion (5-min silent-accept window standard).

If operator wants director input on any Tier C scope element (e.g., should P-CHIEFDIR judge model be 3-LLM ensemble per cycle-15 P11 tweak variant (c), or single Claude default? — this is a Tier C parameter genuinely up for choice), surface via REPLY event before dispatch-claim. Otherwise: proceed.

---

## Cycle-16 entry state summary (post-Tier-B; pre-Tier-C-dispatch)

| Item | State |
|---|---|
| Cycle-16 entry tier progress | Tier A ✅ + Tier B ✅ (9 findings closed) → Tier C ⏳ ready-to-dispatch |
| HEAD | `3f4f7d4` |
| Pytest baseline | 973 / 3 / 0 |
| §15 smoke | OK |
| Pod 525nb9d5cc0p3y | HTTP/2 200; UNETLoader serving FLUX (C-B1 GREEN) |
| Cost cumulative | $2.10-2.65 of $50 cap; ~$47-48 headroom for Tier C + D |
| Director cursor | T20:23:26Z |
| WT | clean (post-`3f4f7d4`) |

---

## Race-ack telemetry (cycle-16 entry running total)

Same 3 N=1 distinct shapes from earlier:
1. Concurrent-claim race (T19:19Z dispatch-claims)
2. Stale-mailbox-content assertion (operator `2426f59` item #1)
3. Pre-write re-verify gap (operator T19:31Z write)

None at N=2 emergence. This Tier C kickoff event is the first Tier-C-bound coord — if any race surfaces (e.g., simultaneous operator+director dispatch-claim on Tier C), Candidate #8 watchpoint fires.

---

## Audit trail (Tier B close → Tier C open)

| Event | Timestamp | Commit |
|---|---|---|
| Operator Tier B closure ack | T20:23:26Z | `9c9c1b2` |
| User-principal "fix all you can in b" | T20:30Z | direct |
| Director VG-B1 + LV-2 | T20:35Z | `84b2efc` |
| Director I-B2 + M-B1 | T20:40Z | `dac17c3` |
| Director M-B2 | T20:48Z | `ad9fa02` |
| Director Tier B all-closed verification-report | T20:52:44Z | `3f4f7d4` |
| User-principal "now update so operator can begin tier c test" | T20:53Z | direct |
| User-principal Tier C scope answers (AskUserQuestion) | T20:55Z | direct |
| Director Tier C kickoff decision (this event) | T20:59:30Z | (this commit) |

---

Signed,
Director-seat — 2026-05-27 cycle 16 entry, Tier C kickoff decision under user-principal direct authorization "now update so operator can begin tier c test" + 4-question scope-lock + standby for operator Tier C dispatch-claim
