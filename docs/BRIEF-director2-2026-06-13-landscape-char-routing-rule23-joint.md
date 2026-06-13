# BRIEF — Char-bearing landscape routing fix (Rule #23 joint) — director2 author

**Author:** director2 (Pair-B). **Status:** AUTHORED — **implementation HELD pending Pair-A
director Rule #23 co-sign** (touches 3 Pair-A-lane callers + re-scopes the ADR-025 Task-4 gate).
**Implements:** the ADR-025 *scope exemption* (`DECISIONS.md` ADR-025 Consequences) +
`ARCHITECTURE.md` §8.5 known-defect note (director-1 quadruple-verified `1b94dd7`).
**Lane:** cross-pair. **Implement:** operator2. **Verify:** director2 (implementer≠verifier).

> This brief does not re-derive the defect — `ARCHITECTURE.md` §8.5 is the canonical,
> verified record. This is the **actionable implementation spec + Rule #23 audit + decisions
> to surface**. Read §8.5 first; this brief points at it rather than duplicating it.

---

## 1. The defect (one-paragraph pointer)

A shot with a **registered character** whose prompt carries a landscape keyword
(`landscape`/`aerial`/`drone`/`skyline`/`panoramic`/`environment`/`scenery`/`no character`)
and **no earlier portrait/action/wide keyword** is mis-classified `landscape` by the shared
seam [`workflow_selector.classify_shot_type`](../workflow_selector.py:416). Both image tiers
then lose identity by *different* mechanisms (§8.5):
- **Production** ([`phase_c_assembly.py:223-227`](../phase_c_assembly.py:223)): early-returns to
  `_fal_flux_fallback(..., character_image=None, secondary_char_refs=None)` → ComfyUI skipped,
  **reference dropped entirely** (strictly worse than `pulid_weight=0.0`).
- **Max** (`MAX_QUALITY_TEMPLATES['landscape']`, [`workflow_selector.py:329-341`](../workflow_selector.py:329)):
  reference physically uploaded but `pulid_weight=0.0`/`lora_strength=0.0`/`regenerate_floor_arc=0.0`
  → PuLID **inert** and the best-of-N identity rescue **dead** (the `0.0` regen floor means
  [`needs_regenerate`](../face_validator_gate.py:326) never fires).

The mis-route is **narrow**: dict-order is first-match-wins `portrait → action → wide → landscape
→ medium`, so e.g. *"drone tracking shot"* → `action` (no bug). It fires only when a landscape
keyword is the *first* bucket hit. (R-EVIDENCE: `SHOT_TYPE_KEYWORDS` order, `workflow_selector.py:112`.)

---

## 2. Recommended fix — single classifier seam (covers both tiers in one edit)

Per §8.5's root-cause finding ("one `classify_shot_type` fix covers both"), route a
landscape-keyword shot **that still has a non-empty `characters_in_frame`** to `wide` instead
of `landscape`. `wide` sets `pulid_weight=0.65` in **both** tiers (production
[`workflow_selector.py:54`](../workflow_selector.py:54); max [`:236-248`](../workflow_selector.py:236),
which also restores `lora_strength=0.9`) → identity re-engages everywhere at once.

```python
# workflow_selector.py classify_shot_type — the keyword-scan return (~446-452)
    for shot_type, keywords in SHOT_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in search_text:
                # A landscape-keyword shot that STILL has a registered character must
                # keep identity. Route to "wide" (pulid_weight 0.65 both tiers) rather
                # than "landscape" (production drops the ref; max zeroes the weight).
                # The chars-empty case already returned "landscape" at the top of the fn,
                # so this only overrides char-BEARING landscapes.
                if shot_type == "landscape" and chars:
                    return "wide"
                return shot_type
    return "medium"
```

Notes that make this safe:
- The `if not chars: return "landscape"` early-return (line 434) is **untouched** — a *true*
  characterless landscape still routes `landscape` (cheap Kontext path stays correct).
- `wide` is reachable here only as a deliberate override: `wide` keywords precede `landscape`
  in dict order, so reaching the `landscape` match proves no wide keyword matched. We are
  intentionally promoting these shots to wide-tier identity handling.

**Rejected alternative — per-tier consumption-site patches** (un-drop the ref at
`phase_c_assembly.py:227` *and* fix the max template separately): two edits, two test sites,
two future drift risks, and it leaves `classify_shot_type` returning a value (`landscape`) that
lies about a char-bearing shot to the other 4 callers. The seam fix is strictly better.

---

## 3. Fallback-target decision — `wide` (recommended) vs `medium` — **surface to principal/Pair-A**

| Target | pulid_weight (prod/max) | Semantics | Verdict |
|---|---|---|---|
| **`wide`** | 0.65 / 0.65 (+ max lora 0.9) | wide framing, char present but small-in-frame | **Recommended** — closest composition match that preserves identity; §8.5-verified weights |
| `medium`  | higher weight | implies a closer shot — semantically wrong for an aerial/vista composition | not recommended |

Recommend **`wide`**. This sets the PuLID weight for a class of shipping shots → it is a
**Pair-A identity-lane call** and a co-sign item (§5).

---

## 4. Rule #23 symmetric-caller audit (all 6 production callers)

Verified caller set (R-EVIDENCE: `grep -rn 'classify_shot_type(' --include='*.py'` minus
tests/scripts/redefs → **6 production callers**, correcting the earlier "5"):

| # | Caller | Lane | Effect of `landscape→wide` for char-bearing shots | Co-sign |
|---|---|---|---|---|
| 1 | [`phase_c_assembly.py:212`](../phase_c_assembly.py:212) | assembly | landscape early-return at :227 **no longer fires** → ComfyUI runs, ref preserved (the prod fix) | — |
| 2 | [`quality_max.py:901`](../quality_max.py:901) | **Pair-A** | `get_max_quality_params("wide")` → 0.65 + lora 0.9 instead of 0.0 (the max fix) | **YES** |
| 3 | [`motion_render.py:265`](../cinema/phases/motion_render.py:265) | motion | motion-floor/routing now uses `wide` not `landscape` for these shots — confirm wide's floor is acceptable | review |
| 4 | [`controller.py:1509`](../cinema/shots/controller.py:1509) | shots | identity-validation threshold + motion now keyed to `wide` | review |
| 5 | [`performance.py:52`](../domain/performance.py:52) | **Pair-A** | `should_capture(...)` decision flips for these shots (continuity ref capture) | **YES** |
| 6 | [`continuity_engine.py:528`](../domain/continuity_engine.py:528) | **Pair-A** | `get_threshold_for_shot`/`get_adaptive_pulid_weight` now returns a **non-zero** identity threshold (≈0.0→0.55) — identity is now *enforced* on these shots | **YES** |

(`scripts/calibrate_motion_floor.py:63` also sees the change — a calibration script, not prod;
note only.)

**Desired side-effects, not collateral:** #6's threshold going 0.0→nonzero is *correct* — once
identity engages, it should be validated. But it changes Pair-A continuity behavior, hence the
co-sign. No caller needs an exemption under this analysis; operator2 must re-confirm during
implementation (Rule #13).

---

## 5. ADR-025 / Pair-A Task-4 gate re-scoping (the cross-pair crux)

ADR-025's Task-4 pod gate validated **PuLID-engaged** shot classes and **explicitly exempted**
char-landscape ("NOT landing in this change"). This fix moves char-landscape shots *into* the
PuLID-engaged set (0.0 → 0.65). Consequences for the implementing change:
- **Close the ADR-025 scope-exemption** (or append a follow-up ADR) recording that char-landscape
  now engages PuLID via `wide`; mark §8.5 **FIXED** with the commit.
- **Pod re-validation owed (deferred):** ADR-025 binding numbers were pod-measured; a char-landscape
  binding re-confirm on the Linux/TBB pod is the honest follow-up. **Pod is STOPPED** → this is a
  flagged debt, not a blocker for the code change. Land code + tests now; mark the pod re-confirm
  as owed (R-MEASURE: do not assert a binding number we have not measured).

This is why the brief carries **director (Pair-A) Rule #23 co-sign** — it re-scopes their
validated shipping gate.

---

## 6. Test plan (RED-first; operator2)

In `tests/unit/test_workflow_selector.py` (the classifier's home suite):
1. **RED:** `characters_in_frame=["hero"]`, prompt with `"aerial"` and no portrait/action/wide
   keyword → assert `classify_shot_type == "wide"` (today: `"landscape"`).
2. **No-regression:** no characters + `"aerial"` → still `"landscape"` (chars-empty early-return).
3. **Precedence pin:** chars + both a wide keyword and a landscape keyword → `"wide"` (unchanged,
   but lock it).
4. **Integration (assembly):** a char-bearing landscape shot through the `phase_c_assembly`
   workflow-selector block → assert the landscape early-return (`character_image=None`) is **not**
   taken (mock the ComfyUI/Kontext boundary; assert the ComfyUI branch + that `character_image`
   survives).
5. **Max tier:** `get_max_quality_params` for the routed shot → `pulid_weight==0.65` (was 0.0).

Then: `ci_smoke` + the full workflow_selector / phase_c_assembly / quality_max suites green.

---

## 7. Implementation order (operator2 ← after co-sign)

1. Patch `classify_shot_type` (§2). 2. RED tests (§6) green. 3. Rule #13 re-confirm the 6
callers (§4) — document any exemption. 4. Doc-sync: §8.5 → FIXED + commit; ADR-025 exemption →
closed/superseded; PROGRAM-MANUAL capability note if relevant. 5. Flag pod re-validation owed
(§5). One commit, explicit pathspec.

## 8. Decisions to surface (don't silently decide)

- **D1 — Land at all?** This *changes shipping behavior*: char-landscape shots go from
  cheap-Kontext/zero-identity to ComfyUI-PuLID at 0.65 (better identity, **higher per-shot cost**
  for that shot class). Aligns with PROGRAM-MANUAL §5 capability-max (more faithful identity).
  Recommend **land** — zero-identity on a char-bearing shot is a correctness bug, not a cost
  knob.
- **D2 — Fallback target** `wide` vs `medium` (§3). Recommend `wide`.
- **D3 — Pod re-validation** of char-landscape binding is owed but pod-gated. Recommend land
  now, re-confirm on next pod-up. (R-MEASURE: don't claim a binding number unmeasured.)

**Gate:** Pair-A director Rule #23 co-sign on D1+D2 (sets PuLID weight + re-scopes their gate)
before operator2 implements. Authored + ready; HELD.
