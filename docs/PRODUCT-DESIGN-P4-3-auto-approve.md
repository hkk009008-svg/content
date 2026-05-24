# P4-3 Product Design — Auto-Approve Heuristics

**Author:** Director (cycle 3, in-session)
**Trigger:** POST-ROADMAP top-pick #1 (product-blocked). The "4-gate
review fatigue" surface is the most operator-visible UX gap remaining
after cycles 1–3 closed every Tier-1 engineering pickup.
**Companion:** [docs/STRATEGIC_REVIEW-2026-05-24.md](STRATEGIC_REVIEW-2026-05-24.md) §P4-3.
**Purpose:** Surface the product decisions a director / product
operator must make BEFORE any implementation session is scoped. The
doc is for you to read, mark up, and reply to — it's not an
implementation plan.

> This doc deliberately stops short of a session brief. The questions
> below are LOAD-BEARING choices that change the implementation in
> incompatible ways depending on the answer. Once decided, a Session
> 11-style brief can be authored in 20–30 min.

---

## Problem framing

The cinema pipeline currently has **four manual review gates** between
the operator and a finished shot:

| # | Gate | What's reviewed | When triggered |
|---|---|---|---|
| 1 | **Plan review** | Structured prompt + planning output from ChiefDirector | After scene_decomposer + ChiefDirector finish; before any GPU generation |
| 2 | **Image (keyframe) review** | Generated keyframe + face validator composite score | After keyframe pipeline produces 1+ takes |
| 3 | **Motion review** | Generated motion (video) + identity + coherence scores | After the motion/video pipeline produces 1+ takes |
| 4 | **Final review** | Post-processed result (lip-sync, face-swap, frame interp) | After post-processing pipeline completes |

Each gate currently requires manual operator approval. **A 10-shot
project = 40 clicks** under the default flow. Most clicks are
rubber-stamp ("looks fine, approve") — the operator's attention budget
is wasted on the easy cases instead of focused on the exceptions.

**The product question is not "should we auto-approve?"** It's "**under
what signals, with what defaults, and with what audit trail?**" Three
sub-decisions each have multiple valid options that ship to different
implementations.

---

## Current state — what signals are available

Cycles 1–3 produced these signals; the auto-approve heuristics build
on them:

### Per-gate signal inventory

| Gate | Signal | Source | Range | Already a halt-or-continue gate today? |
|---|---|---|---|---|
| Plan | `director_review.decision` | ChiefDirector | `APPROVED \| MODIFIED \| REJECTED` | Partial (REJECTED short-circuits) |
| Plan | `director_review.quality_score` | ChiefDirector | `0.0 – 1.0` | No — informational only |
| Plan | `director_review.violations[]` | ChiefDirector | List | No — surfaced but not auto-actioned |
| Image | `composite` (per-take) | `face_validator_gate.score_candidate` | `0.0 – 1.0` (arc * 0.6 + aes * 0.4) | YES — `should_halt(threshold=0.92)` already short-circuits generation |
| Image | `arc_score` | ArcFace face-similarity | `0.0 – 1.0` | Component of composite |
| Image | `aes_score` | AestheticsPredictorV2 | `0.0 – 1.0` | Component of composite |
| Image | `cascade_metadata.fallback` | Cascade pipeline (Session 6) | `bool` | No — display-only badge today |
| Image | `cascade_metadata.attempts[]` | Cascade pipeline | List of engine names | No — display-only |
| Motion | `identity_score` | Face validator on video frames | `0.0 – 1.0` | YES — coherence/motion thresholds in pipeline |
| Motion | `motion_score` | Motion quality predictor | `0.0 – 1.0` | YES — pipeline gates |
| Motion | `coherence_score` | Continuity check | `0.0 – 1.0` | YES — pipeline gates |
| Motion | `cascade_metadata.*` | Same as image | Same | Display-only |
| Final | `lipsync_score` (when applicable) | Lipsync engine quality | `0.0 – 1.0` | Partial — used in cascade selection |
| Final | All the above (composite) | Aggregated | Various | No composite-of-composites today |

### Per-shot cost signals (added by Session 5)

- `spent_usd` per-shot (lifetime sum of `record_api_call` costs)
- `record_api_call` traces (per-call cost + latency)

These enable cost-aware auto-approve: "auto-approve unless the shot
is already over budget."

### Per-shot retry signals

- `retry_count` on `ShotState` — how many regenerate cycles this shot
  has been through
- `take_count` on each take list — how many takes generated at this
  gate

These enable "first attempt was great → auto-approve" vs. "third
attempt and quality still mediocre → human review."

---

## The 5 load-bearing product decisions

Each decision is framed as **Why this matters → Options → My
recommendation → Implementation impact**. Read top-to-bottom; later
decisions depend on earlier ones.

---

### Decision 1: Single-signal threshold OR composite-of-signals?

**Why this matters.** The simplest auto-approve is one signal one
threshold (e.g., "auto-approve image gate if `composite >= 0.92`").
The most accurate is a composite of all available signals weighted
by what the operator actually cares about. The two have very
different implementations.

**Options:**

| Option | Description | Pros | Cons |
|---|---|---|---|
| **A. Single-signal per gate** | Each gate has one canonical threshold on one signal (e.g., image: composite; motion: identity_score; final: lipsync_score) | Simple to explain; tunable per-gate; matches existing `face_validator_gate.should_halt` shape | May miss cases where one signal looks great but another is concerning (e.g., high composite + cascade-fallback should still raise hand) |
| **B. Composite-of-composites** | Define a per-gate "approve_score" combining 2–4 signals with weights (e.g., image_approve = 0.7 * composite + 0.2 * (1 - fallback_penalty) + 0.1 * cost_within_budget) | Captures multi-dimensional confidence; one threshold per gate; aligns with existing composite pattern | Weight-tuning is a forever-task; explainability suffers ("why was this auto-approved?" requires showing all components) |
| **C. Veto-list** | Auto-approve by default; ANY signal below its individual threshold vetoes (forces human review). Composite isn't computed. | Easiest to reason about ("anything weird → human"); operator audit trail is clear; matches "defensive defaults" instinct | May veto too often if individual thresholds are conservative; doesn't leverage signals' complementary strengths |

**My recommendation: Option C — Veto-list.** It maps cleanly to the
operator's mental model ("review is for the unusual"). Each veto
condition is a separately-explainable rule, which makes auditing
auto-approvals straightforward. Option B's tuning burden is real and
high; Option A loses information.

**Implementation impact:**
- Option A: ~50 LOC + 4 thresholds in config
- Option B: ~150 LOC + 4 weight schemas + 4 thresholds + a "compute
  approve_score" function per gate
- Option C: ~80 LOC + N veto rules (one per veto-able signal, listed
  per gate) + a "any rule fires → veto" combinator

---

### Decision 2: Per-gate independence OR globally-tunable?

**Why this matters.** Gates 1–4 have very different stakes. Plan
review affects everything downstream; Final review is the last
chance before delivery. Should they share the same thresholds, or
have independent settings?

**Options:**

| Option | Description | Pros | Cons |
|---|---|---|---|
| **A. Independent per gate** | Each gate has its own threshold/veto-list, tuned independently | Lets operator trust auto-approve on cheap gates (image) while keeping strict on expensive gates (final) | More config surface; 4 sets of dials to tune |
| **B. Global confidence dial** | One "auto-approve aggressiveness" setting (0=off, 1=loose). Gates derive their thresholds proportionally | Simpler operator UX; one knob | Loses gate-specific nuance; may auto-approve too liberally at image gate (cheap) when set for "conservative on final" |
| **C. Hybrid** | Global dial sets default; per-gate override possible for power users | Best of both | More complex implementation; operators may forget overrides |

**My recommendation: Option A — Independent per gate.** Each gate
has fundamentally different signals (plan ≠ image ≠ motion ≠ final),
so a global dial is mathematically lossy. The "config surface" cost
is one-time; the "lose nuance" cost is forever. Surface the per-gate
config in a single settings panel so the dials live together visually.

**Implementation impact:**
- Option A: 4× config entries in `project.json` `global_settings` (or
  similar); 4× threshold checks in code
- Option B: 1 config entry + derived-threshold function
- Option C: 4 entries + 1 global with override merge logic

---

### Decision 3: Default state — opt-in OR opt-out?

**Why this matters.** New auto-approve features ship with a default.
"Opt-in" means the operator must turn it on (no UX disruption until
they actively engage); "opt-out" means it's on for all new projects
(immediate workflow change). The choice signals product confidence in
the heuristic.

**Options:**

| Option | Description | Pros | Cons |
|---|---|---|---|
| **A. Opt-in (off by default)** | Operator must enable per project | Safe rollout; existing workflows unchanged; operator opts in once trust is built | Most operators never enable it ("if it's off by default, it can't be important"); UX gap persists |
| **B. Opt-out (on by default for new projects)** | Auto-approve runs on every new project; existing projects keep their current setting | Operators immediately experience the benefit; reduces friction by default | Risk of an early auto-approve mistake eroding trust before tuning is right |
| **C. Conservative-on by default** | Auto-approve enabled with a very conservative threshold (e.g., composite >= 0.97 for image) — only "absolutely confident" cases auto-approve, everything else hands off | Hybrid: gets some friction reduction immediately, but rarely surprises operator | The conservative thresholds may approve so few cases that the win is invisible; operator may not realize it's on |

**My recommendation: Option C — Conservative-on by default.** The
operator gets immediate value (~30–50% of clearly-good shots auto-
approved) without surprise on edge cases. As trust builds, the
operator can loosen the threshold via per-project settings. This is
the "show the value, don't shock" path.

**Implementation impact:**
- Option A: 1 boolean per project; default `False`
- Option B: 1 boolean; default `True`
- Option C: 4 thresholds per gate; defaults set conservatively;
  needs explicit "auto-approve is enabled" notice in UI

---

### Decision 4: Audit trail — how does the operator review auto-approved decisions?

**Why this matters.** If auto-approve is silent, the operator can't
catch the system's mistakes. If it's loud (every auto-approval pops
a notification), it defeats the purpose. The audit trail design is
the bridge.

**Options:**

| Option | Description | Pros | Cons |
|---|---|---|---|
| **A. Inline tag** | Each auto-approved gate shows a small "Auto" badge in the timeline; operator scrolls and sees them in context | Discoverable; no extra clicks for the operator; matches existing cascade-badge pattern (Session 6) | Operator may not look at the timeline; auto-approvals can pile up unnoticed |
| **B. Post-run summary** | At project completion, surface a "5 shots auto-approved with these signals" summary modal | Forces a checkpoint; operator can spot-check after the run | Late feedback; if something was wrong, all 5 already shipped |
| **C. Soft-block on outliers** | Auto-approve as normal, BUT any auto-approval where a SECONDARY signal was borderline (e.g., composite >= threshold but coherence < 0.7) gets flagged for retroactive operator confirmation in a separate queue | High-signal; only escalates the cases worth looking at | Implementation complexity; risk of operator ignoring the queue if it fills up |

**My recommendation: Option A + B combined.** Inline tag (cheap to
add, leverages the existing cascade-badge component from Session 6)
+ post-run summary (no implementation outside web/ + Session 5's
cost telemetry framework). Option C is right in theory but
demonstrably under-used in similar UI patterns (notification-queue
fatigue is its own UX gap).

**Implementation impact:**
- Option A: ~40 LOC web/ (new `AutoApproveBadge` component) + ~10 LOC
  Python (set a `auto_approved: True` field on the gate state)
- Option B: ~80 LOC web/ (new modal) + reuse Session 5's cost-tracker
  query API
- Option C: ~150 LOC backend + new "review queue" data model + UI for it

---

### Decision 5: Failure mode — when auto-approve is wrong, what's the recovery?

**Why this matters.** Eventually a shot gets auto-approved that the
operator would have rejected. The recovery path is the contract
between the operator and the system: "you can trust auto-approve
because here's what happens when it's wrong."

**Options:**

| Option | Description | Pros | Cons |
|---|---|---|---|
| **A. Manual rollback** | Operator clicks "regenerate" / "reject" on the take just like a manual review; no auto-approve-specific recovery | Simplest; matches existing flow; nothing new to learn | Auto-approve's mistakes are indistinguishable from the operator's own; no learning loop |
| **B. Soft-rollback with reason capture** | When operator rejects an auto-approved take, surface a quick "why did auto-approve fail here?" prompt (composite was high but motion was poor / cascade fell back / etc.) | Generates data for tuning thresholds; reinforces operator agency | Adds 1 click per rollback; modal fatigue risk |
| **C. Aggressive learn** | Every operator-rejected auto-approval feeds into a per-project threshold-adjustment system; next time signals like this surface, raise the threshold | Self-tuning; operator effort compounds | Complex; thresholds can drift to be useless; opacity ("why did the threshold change?") |

**My recommendation: Option B — Soft-rollback with reason capture,
WITH SKIP.** Adds the prompt but makes it optional (one click to
dismiss). Captures data for retrospective threshold review without
forcing the prompt to be useful for every operator. The captured
reasons become input to manual threshold tuning later (which is the
right answer for now — Option C's automated tuning is premature).

**Implementation impact:**
- Option A: 0 LOC (already exists)
- Option B: ~30 LOC backend (new `auto_approve_overrides` log) + 60
  LOC web/ (rejection modal with optional reason)
- Option C: ~200 LOC backend (threshold-adjustment engine) + 80 LOC
  web/ + new "auto-tuning history" feature

---

## Recommended starting point — Session 11 brief shape

If you concur with my recommendations (Decisions 1C + 2A + 3C + 4A+B +
5B), the implementation brief would be:

**Session 11 — P4-3 auto-approve (conservative defaults + veto-list +
inline tag):**

- **IN:** Per-gate veto rules in a new `cinema/auto_approve.py`
  module; 4 default thresholds in `project.json.global_settings`;
  inline `auto_approved: True` field on gate state; AutoApproveBadge
  web/ component; post-run summary modal; soft-rollback reason
  capture
- **OUT:** Composite-of-composites scoring (Option 1B); global
  confidence dial (Option 2B); soft-block queue (Option 4C);
  auto-tuning (Option 5C). All explicitly deferred.
- **Effort:** L — 2 implementer sessions (backend rules + tests,
  frontend badges + modal) + 1 product session for default-threshold
  calibration against real project data

**Default thresholds (starting point — operator will tune):**

| Gate | Veto if |
|---|---|
| Plan | `decision != "APPROVED"` OR `len(violations) > 0` |
| Image | `composite < 0.97` OR `cascade_metadata.fallback == True` OR `spent_usd > 1.5 * budget_per_shot` |
| Motion | `identity_score < 0.85` OR `motion_score < 0.7` OR `cascade_metadata.fallback == True` |
| Final | `lipsync_score < 0.8` (when applicable) OR ANY previous gate auto-approved (require human at final regardless) |

The "ANY previous gate auto-approved → require human at final" rule
in the final gate is a safety net — at least one human eyeball on
every shot, but the friction is reduced by 75% (3 of 4 gates auto-
approve).

---

## What I need from you

Mark up this doc (or reply in conversation) with your decisions on
Decisions 1–5. If you concur with my recommendations, just say "all
defaults" and I can author the Session 11 brief in 20-30 min. If
you diverge on any decision, surface which one(s) and the reasoning;
I'll re-frame the brief accordingly.

If any of these matter for context:

- **How often do you currently reject vs. approve at each gate?**
  This tells us where auto-approve has the most leverage.
- **Have you experienced an auto-approve "miss" elsewhere that
  shaped how you want to handle it here?**
- **Is there a specific shot type (dialogue close-up, action,
  establishing) where you would NEVER want auto-approve?**

These aren't required but would let me refine the default thresholds
in the Session 11 brief from "starting point" to "calibrated against
your actual workflow."

---

*Verified at HEAD `607348d` (2026-05-24, mid-cycle-3):
`face_validator_gate.py:225-281` confirms `should_halt(halt_threshold_composite=0.92)`
is the existing image-gate pattern; `domain/scene_decomposer.py:41-58`
confirms per-engine `quality_score` 0.74–0.90 range. Signal inventory
sourced from `web/src/types/project.ts` (TakeRecord, ShotState,
DirectorReview, QualityMetrics) and `cinema/lifecycle.py` (gate
state).*
