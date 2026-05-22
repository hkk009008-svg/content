# ADR-0001: Video Provider Routing

**Status:** Proposed
**Date:** 2026-05-23
**Deciders:** repo owner (solo dev today; future contributors)
**Supersedes:** none
**Related:** `phase_c_ffmpeg.py:generate_ai_video`, `cost_tracker.py`,
`docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md`

---

## 1. Context

`phase_c_ffmpeg.py:generate_ai_video(target_api, video_fallbacks, shot_type, ...)`
is the single video-synth entry point. It contains an if/elif chain over
**11 providers**:

```
KLING_NATIVE, SORA_NATIVE, VEO_NATIVE, LTX,
RUNWAY_GEN4, SORA_2, VEO, KLING_3_0, COMFY_UI, RUNWAY, SEEDANCE
```

Each branch (a) imports the provider client, (b) shapes a provider-specific
prompt, (c) maps generic params (`camera_motion`, `shot_type`,
`multi_angle_refs`) to provider-specific params, (d) calls the API,
(e) falls back to `try_next_api()` on failure.

The function is **policy-free**: it receives `target_api: str` and the
ordered `video_fallbacks: list[str]` from its caller. The actual routing
decision (which provider is best for *this* shot) is implicit in
whatever upstream code populates those arguments. Grep currently shows
that population happening in scattered places (defaults in
`comfyui_workflow_gen.py:565`, hardcoded `["KLING_NATIVE"]` at
`phase_c_ffmpeg.py:223`) — there is no central router.

### 1.1 Forces

| Force | Today's reality |
|---|---|
| **Cost variance** | LTX < Kling < Sora ≈ Veo < Runway. 10× spread per shot. `cost_tracker.py` exists but isn't consulted at routing time. |
| **Quality variance per shot type** | Sora best at motion physics; Kling best at face/identity; Veo best with reference images + native audio (landscapes); LTX best at 4K environments + transitions. |
| **API reliability** | Veo was removed from auto-cascade due to quota exhaustion (`phase_c_ffmpeg.py:7-9`). Reliability is dynamic, not static. |
| **Identity preservation** | Hero-character shots need face_consistency + multi-angle refs — narrows to Kling Native or Veo Native. |
| **Batching** | Kling 3.0 storyboard mode can batch 6 shots in one call ("unified latent space") — only viable if all 6 shots share a scene context. |
| **Operator override** | The web UI needs to let an operator force a specific provider for a shot ("re-record with Sora"). |
| **Determinism for retries** | After a failure, the fallback chain must be predictable so users understand cost/quality regressions. |

### 1.2 What this ADR does and does not decide

**Decides:** where the routing policy lives, what inputs it consumes,
how operator overrides flow in, what guardrails apply.

**Does not decide:** the exact provider-quality weights — those are
calibration data that should live in a config file the policy reads,
not in the ADR. Provider weights will change every few months as APIs
evolve; the ADR should not need a revision each time.

---

## 2. Decision

Introduce a **`VideoRouter`** in a new `cinema/video_router.py` module.
`VideoRouter.route(shot, context) -> RoutingDecision` returns
`(primary: str, fallbacks: list[str], reason: str)` — `target_api` and
`video_fallbacks` for `generate_ai_video` are derived from this single
call.

Inputs to the router:

```python
@dataclass(frozen=True)
class RoutingInput:
    shot_type: Literal["portrait", "medium", "action", "wide", "landscape"]
    has_character_ref: bool       # multi_angle_refs present
    needs_face_consistency: bool  # hero character in frame
    needs_native_audio: bool      # landscape with diegetic sound
    target_resolution: Literal["1080p", "4k"]
    estimated_cost_budget_usd: float | None  # per-shot ceiling
    operator_override: str | None  # forces primary, keeps fallback chain

@dataclass(frozen=True)
class RoutingDecision:
    primary: str
    fallbacks: list[str]
    reason: str  # human-readable, e.g. "face_consistency + 4 refs → KLING_NATIVE"
```

Policy data lives in `config/video_routing.yaml` (a new file). The
router is a pure function over `(RoutingInput, policy_yaml)`. No
network, no provider import.

---

## 3. Options Considered

### Option A: Static policy table (shot_type → ordered provider list)

A YAML mapping like:

```yaml
portrait:  [KLING_NATIVE, SORA_NATIVE, VEO_NATIVE]
action:    [SORA_NATIVE, KLING_NATIVE, LTX]
landscape: [VEO_NATIVE, LTX, KLING_NATIVE]
```

| Dimension | Assessment |
|---|---|
| Complexity | **Low** — ~40 LOC + YAML |
| Cost | **Low** — no per-call overhead |
| Scalability | Limited — can't react to budget, reliability, or character refs |
| Team familiarity | **High** — everyone reads YAML |
| Predictability | **High** — same input → same output |

**Pros:** Trivial to read, audit, version. Routing decisions are stable
across runs.
**Cons:** Can't honor a per-shot cost budget. Can't react to dynamic
reliability (Veo quota). Operator overrides require a side channel.

### Option B: Rule-based router class with explicit predicates

```python
def route(inp: RoutingInput) -> RoutingDecision:
    if inp.operator_override:
        return RoutingDecision(inp.operator_override, _default_fallbacks(inp), "override")
    if inp.needs_face_consistency and inp.has_character_ref:
        return RoutingDecision("KLING_NATIVE", ["VEO_NATIVE", "SORA_NATIVE"], "face+refs")
    if inp.shot_type == "landscape" and inp.target_resolution == "4k":
        return RoutingDecision("LTX", ["VEO_NATIVE", "KLING_NATIVE"], "4k landscape")
    ...
```

| Dimension | Assessment |
|---|---|
| Complexity | **Medium** — ~120 LOC of predicates |
| Cost | **Low** |
| Scalability | Can grow predicates as shot types diversify |
| Team familiarity | **High** — readable Python conditions |
| Predictability | **High** — deterministic |

**Pros:** Encodes multiple inputs at once. Easy to add new predicates
("if `needs_native_audio` → Veo"). Operator override is first-class.
**Cons:** Predicate ordering matters — bugs are subtle. Tests must
cover combinatorial input space.

### Option C: LLM-based router (use LLMEnsemble to pick)

Ask the LLM: "Given this shot description, which provider?"

| Dimension | Assessment |
|---|---|
| Complexity | **Low** code, **high** in prompt engineering |
| Cost | **Medium** — extra LLM call per shot (cents) |
| Scalability | Can reason about novel shot types |
| Team familiarity | **Medium** — LLMs are familiar but unpredictable |
| Predictability | **Low** — same input may produce different output |

**Pros:** Can adapt to shot descriptions the rule set didn't anticipate.
**Cons:** Adds latency to every shot (≥1s per LLM round-trip). Hard to
audit "why did it pick LTX for shot 4?" Cost grows linearly with shot
count.

### Option D: Cost+quality multi-objective optimizer

Score each provider as `quality_for(shot_type) − cost_weight * price`,
pick argmax.

| Dimension | Assessment |
|---|---|
| Complexity | **Medium** — scoring functions + tuning |
| Cost | **Low** |
| Scalability | Optimal as quality data improves |
| Team familiarity | **Low** — needs calibration data nobody has yet |
| Predictability | **High** within a scoring version |

**Pros:** Principled. Cost guardrail emerges naturally.
**Cons:** Requires quality scores per (provider, shot_type) — that's
empirical data the project does not yet have. Cold-start problem.

### Option E (recommended): Hybrid — rule-based router + cost guardrail + policy YAML

Take Option B's predicate structure, but:

1. **Predicate body is data, not code.** YAML rules of the form
   `{ when: { needs_face_consistency: true, has_character_ref: true },
   then: { primary: KLING_NATIVE, fallbacks: [VEO_NATIVE, SORA_NATIVE] } }`.
2. **Cost guardrail wraps the result.** After predicate match, if
   `estimated_cost(primary) > budget`, swap to the cheapest fallback
   that meets the must-have flags (`needs_face_consistency`, etc.).
3. **Operator override is highest priority.** If set, that's the
   primary; predicates only compute fallbacks.
4. **Reliability tagging is optional.** A provider can be flagged
   `degraded: true` in YAML; the router skips it without re-deriving
   the policy. (This is how VEO_NATIVE was removed in the existing
   code — formalize it.)

| Dimension | Assessment |
|---|---|
| Complexity | **Medium** — ~150 LOC + YAML schema |
| Cost | **Low** |
| Scalability | Adding a provider = one YAML entry; adding an input dimension = one predicate field |
| Team familiarity | **High** — predicate YAML is readable |
| Predictability | **High** — deterministic, debuggable via `reason` field |

---

## 4. Trade-off Analysis

The key tension is **flexibility vs predictability**:

- LLM routing (C) is maximally flexible but operationally opaque. When a
  bad shot lands in production, "the LLM picked it" is not a debuggable
  answer. Reserve LLM routing for shot *prompt* generation, not provider
  selection.
- Static tables (A) are maximally predictable but can't honor budgets
  or reliability changes — the very things that motivated this ADR.
- Optimizer (D) is theoretically right but premature without quality
  data. Revisit in 3–6 months when `cost_tracker.py` has accumulated
  enough runs to calibrate scores.

Option E is the smallest design that addresses all forces in §1.1:
character-ref preservation, cost budget, reliability flags, operator
override. The YAML stays human-readable; the wrapping cost guardrail
gives one fail-safe.

**Why not just keep the implicit caller-decides model?** Because the
current scattered defaults (`["KLING_NATIVE"]` in one place, hardcoded
provider lists in `comfyui_workflow_gen.py:565`) mean there is no single
location to (a) audit cost behavior, (b) respond to provider degradation,
(c) implement operator override consistently. Centralizing is the value.

---

## 5. Consequences

### What becomes easier

- Adding a new provider: write the dispatch branch in `generate_ai_video`,
  add one entry in `config/video_routing.yaml`, ship.
- Responding to a provider outage: flip `degraded: true` in YAML, no code
  change, no redeploy.
- Cost analysis: every routing decision carries a `reason` field, so
  retrospectives over `cost_tracker.py` data can attribute spend to
  routing rules.
- Testing: the router is a pure function, so unit tests are trivial.

### What becomes harder

- Routing decisions are now centralized — code that previously hardcoded
  `target_api` (e.g., `phase_c_ffmpeg.py:223` cascade retry, the
  `comfyui_workflow_gen.py:565` default) must be migrated to call the
  router. That's a small one-time cost.
- The YAML schema is now a public contract; changes to its shape need
  to be backward-compatible or guarded by a version field.

### What we'll need to revisit

- **Per-character routing preferences.** A specific character's identity
  may be best preserved by Kling, another by Veo. The current
  `RoutingInput` doesn't carry character identity. Add a
  `character_id: str | None` field when this becomes a measured concern.
- **Storyboard batching.** Kling 3.0's `multi_prompt` mode batches 6
  shots. The router operates per-shot today; batching would need a
  separate `route_scene(shots: list[Shot])` entry point. Defer until
  batching is reintroduced in the pipeline.
- **Quality scores.** When `cost_tracker.py` has enough data, migrate
  toward Option D's scoring as a successor ADR.

---

## 6. Action Items

1. [ ] Create `cinema/video_router.py` with `RoutingInput`,
   `RoutingDecision`, and `route()` function.
2. [ ] Create `config/video_routing.yaml` with current behavior encoded
   (mirror the existing implicit defaults; this is a no-op refactor at
   first).
3. [ ] Replace the cascade-retry hardcoded `["KLING_NATIVE"]` at
   `phase_c_ffmpeg.py:223` with a call to `VideoRouter.route(...)`.
4. [ ] Update `comfyui_workflow_gen.py:565` default to query the router
   instead of hardcoding `"KLING_NATIVE"`.
5. [ ] Add `degraded: true` for `VEO_NATIVE` in the YAML, matching the
   `_VEO_QUOTA_EXHAUSTED` flag at `phase_c_ffmpeg.py:7-9`. Delete the
   flag once parity is verified.
6. [ ] Add unit tests in `tests/unit/test_video_router.py` covering each
   shot_type × character-ref × budget combination.
7. [ ] Add a `reason` field to the entry that `cost_tracker.py` writes
   per generation, so spend can be attributed to routing rules.
8. [ ] Document the YAML schema in `config/video_routing.schema.md`.
