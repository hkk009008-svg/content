# Handoff — director2 (Pair-B: video/assembly/delivery) — 2026-06-13 PM2

**Seat:** director2 (Pair-B director). **My landing this session:** `65e9b88` (auto-RIFE).
**HEAD at wrap:** verify `git rev-parse HEAD` (was `e61ab10` + my `65e9b88`; 4 seats move it).
**Push:** USER-gated (nothing pushed). **Read this first as the next director2.**
Companion: the W1 dispositions brief `docs/BRIEF-director2-2026-06-13-PM-W1-dispositions.md`
(§5 principal decisions) — still current except where this handoff supersedes it.

---

## TL;DR / session arc

Resumed (user "continue as director2", ultracode). Surfaced the BRIEF §5 design decisions to
the principal → principal said **"proceed as recommendation"**. Ran an adversarial **design+refute
workflow** (`wf_e5824fd6-56b`, 8 Sonnet agents) over the 4 greenlit code items BEFORE touching the
live shared tree — it materially changed the plan. **Landed auto-RIFE** (TDD-green, committed
`65e9b88`). Wrapped on user "handoff" with auto-RIFE done, the other three items design-locked, and
two decisions surfaced for the principal.

**Process win:** the design pass earned its cost — it deferred my own "cheap first win"
(silence-trim), rejected the scorer's smile-cascade approach, and surfaced a Suno config bug. AND
verifying the *refuter's* own claims caught two ghost-string guards it suggested. Verify every
layer, including the verifier.

---

## What LANDED + VERIFIED this session

| Item | Commit | Status |
|---|---|---|
| **auto-RIFE (§5.2)** — default-on RIFE in `_finalize_motion_take` | `65e9b88` | ✅ TDD-green (8 new + 70 regression), ci_smoke OK. **operator2 verifies on resume.** |

**auto-RIFE detail:** new `ShotController._maybe_auto_rife` (`cinema/shots/controller.py`) reads
`global_settings.auto_rife_smoothness_threshold` (default **0.4**; `<=0` disables), runs
`assess_motion_quality`, stores `smoothness_score` on the take, and applies
`generate_rife_interpolation` when **`recommendation != "regenerate"` AND `smoothness < threshold`**.
Rebinds `take["path"]` + `generated_video`, records new `FAL_RIFE` ($0.04) cost. Best-effort
(never fails the take). **Key safety call:** gating on the non-`regenerate` recommendation (mirrors
`diagnose_clip:2096`) — without it, every fake/short clip (smoothness 0.0) would trigger a **real
cloud RIFE call**, because **FAL_AVAILABLE=True AND fal_key IS SET in the dev venv** (verified). The
recommendation gate excludes unassessable/frozen clips that RIFE can't fix anyway → correctness +
test-safety in one guard. SKILL.md:175 ("auto-triggers RIFE") is now TRUE. NO dialogue-skip (the
ai-video-gen skill endorses RIFE-after-lipsync; interpolation preserves keyframe timing; threshold
is the gate). Deferred doc-sync: optional ARCHITECTURE.md §9.7 enhancement note + flag storyboard
per-segment RIFE cost (~6×$0.04/scene) in PROGRAM-MANUAL §5.

---

## Design-pass verdicts (`wf_e5824fd6-56b`) — the other 3 code items

> The /tmp workflow output is ephemeral; the load-bearing conclusions are captured here.

### Scorer (§5.1 SyncNet + §5.4 alignment) — VERDICT: RECONSIDER → REDESIGN (task #1)
The spec's mouth-detection via **`haarcascade_smile.xml` is WRONG** — it's a *smile* detector,
~20-40% recall on speech frames → systematically depressed scores → would **reject correct
lip-sync** (worst for Korean, which has `forced_alignment_enabled=True`). **Redesign to a
pixel-energy inter-frame mouth-motion estimator** (mean abs pixel diff in the lower-center frame
region across consecutive sampled frames; speech↔motion, silence↔still). No new deps,
phoneme-agnostic, unit-testable on synthetic numpy frames. Also fold in: (a) wire the
`alignment_scorer_enabled` gate (spec left it unwired); (b) fix the dup-signal bug
(`lipsync_alignment_score` must differ from `lipsync_score` — store the pre-alignment heuristic
separately); (c) the **coordinator's HELD loud-gate** — add a WARNING at `lip_sync.py:408` so the
SyncNet-absent silent degradation (which still feeds the 0.8 approval gate at
`auto_approve.py:495`→`review/controller.py:324`, a *falsely-green* gate) becomes visible.
Direction (alignment sidecar → real scorer) is correct + needed. Re-true `alignment.py` docstring
(`fe8e7c6` set it to "write-only" — update to "consumed by the scorer") + ARCHITECTURE.md §12.2.
**This is the principal's headline item — do it carefully; consider a fresh focused design pass for
the pixel-diff algorithm.**

### Suno reconnect (§5.3) — VERDICT: SOUND_WITH_CHANGES + a CONFIG BUG (task #2)
Reconnect is mechanical: `cinema_pipeline.py:632` `generate_fal_bgm` → `generate_bgm` router;
thread `cost_tracker` through `generate_bgm`'s FAL fallback (`audio/music.py:280` drops it).
**BLOCKER surfaced (verified):** `config/settings.py:118` defaults `suno_api_base` to
`https://api.suno.ai/v1`, but `music.py:198` builds `{base}/api/v1/generate` → doubled path
`…/v1/api/v1/generate` → **Suno 404s every call**, so "Suno-first" is inert. Code comments reference
`sunoapi.org`. → **SURFACE to principal** (below). Also re-true ARCHITECTURE.md §4.1 (line ~225,
"FAL Stable Audio" → router) + §12.5 + `music.py:5` docstring. Lowest-risk item once api_base
decided.

### Silence-trim (§5 option A) — VERDICT: DEFER (task #4)
Both design agents converged on **DEFER** — my desync instinct confirmed. Overlay-mode desync is
unmitigatable without a dual-path audio architecture (the Veo clip is sized from the *untrimmed*
TTS at `controller.py:1582` BEFORE the overlay pass); no proven benefit until a real scorer exists;
and `forced_alignment_enabled` is True for all languages so the "data absent" rationale is void.
**Immediate cheap action regardless:** fix the false skill claim `post-processing.md:214`
("Silence trimming: Applied to TTS output" — it is NOT). **SURFACE the DEFER to principal** (it
reverses the greenlit "cheap first win").

---

## DECISIONS FOR THE PRINCIPAL (surface — don't silently decide)

1. **Silence-trim → DEFER (reverses my own "cheap first win").** The adversarial design pass shows
   the overlay desync risk dominates and there's no benefit case until a real lip-sync scorer
   exists. **Recommend: defer it; revisit after the scorer lands.** (Will fix the false doc claim
   regardless.)
2. **Suno `suno_api_base` default is malformed** (doubled `/api/v1` path → every Suno call 404s).
   The reconnect is pointless until this is fixed. **Recommend: correct the default to
   `https://api.sunoapi.org`** (matches the code comments + test fixtures) — but this changes which
   external endpoint prod hits, so confirm the intended Suno provider/account before I land it.

---

## ⭐ NEXT pickups (ordered) for the next director2

1. **operator2 verifies auto-RIFE `65e9b88`** on resume (implementer≠verifier; operator2 is offline).
2. **Get the principal's steer** on the 2 decisions above (silence-trim DEFER, suno_api_base).
3. **Suno reconnect (task #2)** once api_base decided — lowest-risk, mechanical, ~XS. TDD with a real
   CostTracker (mock masks the cost-thread bug).
4. **Scorer redesign + build (task #1)** — pixel-diff mouth-motion, fold in the loud-gate WARNING +
   dup-signal fix + settings gate. The principal's headline item; design it carefully.
5. **Landscape Rule#23 brief (task #5)** — BRIEF only, joint with Pair-A's director. SCOPE EXPANDED
   by director-1's severity correction (`...10-46-28Z`): the mis-route **early-returns at
   `phase_c_assembly.py:224`** to `_fal_flux_fallback(character_image=None)` → ComfyUI skipped,
   char ref DROPPED, **zero identity (worse than weight 0.0)**. Target that early-return +
   `classify_shot_type` + an untraced **MAX-tier `quality_max.py`** sibling; cross-ref **ADR-025
   (`6aad3b2`)**; director-1 co-signs. Operator already placed the ARCHITECTURE.md §8.5 known-defect
   note (`547cf12`/`e61ab10`) — coordinate, don't duplicate.
6. **Disposition operator2's 6 test-dark defects** (their PM2 wrap `d407ee5` /
   `docs/HANDOFF-operator2-2026-06-13-PM2-A1-landed-testdark-6defects-verified-autorife-WIP-observed.md`):
   3 fix_now_trivial (D1 Seedance null-`task_id` polls `/status/None` 120×; D4 `stitch_modules`
   bare-CWD `concat_list.txt` collision+leak; D6 lipsync best-of-failed `copyfile` returns truthy
   stale path) + 2 fix_with_brief = director2's call (D3 FAL_SVD char ref uploaded-but-never-forwarded;
   D2 Seedance `multi_angle_refs` never read). D5 was REFUTED → no_action (cv2 is a hard dep — the
   "[SHOT]-inert" lesson repeating). operator2 also independently re-confirmed W1 §5 all-four broken
   and that Suno `generate_bgm` lacks `cost_tracker` (the bonus-bug — convergent). A1 `shot_id=''`
   refine LANDED+verified `4121a83`.
7. W2 delivery (subtitles on live alignment — `srt.py` was deleted, net-new; SeedVR2-4K; LUT) + W4
   Sora succession remain queued.

---

## Cross-lane state (Pair-A = image/identity)

- **✅ Pod `07ed667` STOPPED** (`b123632`) — billing resolved (was the standing flag; no longer).
- **Pair-A Step-5 PuLID shipping-default COMPLETE+VERIFIED** (`735adb9`); ADR-025 (`6aad3b2`) records
  the char-landscape routing defect as a scope-exemption.
- Coordinator (5th read-only seat) wrapped (`b76c2e8`); it added a `coordinator` send-only mailbox
  seat (`fd334d3`) and shipped doc-truth fixes (`fe8e7c6` alignment.py, `ed24add` ARCHITECTURE §11.1).

## Sharp edges (held this session)

- **FAL is configured in the dev venv** (`FAL_AVAILABLE=True`, `fal_key` set) — a *default-on*
  feature that calls a cloud API will fire **real network calls in the unit suite** unless it gates
  on something the test fixtures don't satisfy. Gate cloud-enhancement steps on the assessment's
  *recommendation* (`!= "regenerate"`), not a raw smoothness threshold — fake/short clips resolve to
  "regenerate" → no call. (This is why auto-RIFE's safety guard == its correctness guard.)
- **Verify the verifier:** two guards the adversarial refuter *recommended* (`quality_tier=="draft"`,
  `dialogue_audio_in_clip`) were themselves ghost strings (only `max`/`production` tiers exist; the
  real dialogue flag is `has_dialogue`). Grep the reviewer's claims too.
- **Phantom per-seat index:** session-start `git status` ghosts (incl. a `scripts/_prod_pulid_acceptance.py`
  *deletion* that is NOT real). All matched HEAD. Commit with **explicit pathspec** (I listed my 3
  files) so the phantom is excluded; `git show --stat` to confirm scope. Don't "revert" the ghosts.
- **HEAD moved ~10× under me** (Pair-A Step-5 close-out + coordinator + operator). `git log -1`
  before each commit. `origin` push stays USER-gated.
