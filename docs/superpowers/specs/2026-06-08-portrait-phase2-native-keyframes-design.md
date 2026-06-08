# Portrait Phase 2 — native 9:16 image keyframes — design

*Status: user-approved design (2026-06-08). Director-seat, brainstorm → spec.*
*Origin: continuation of the portrait/aspect-aware delivery program. **Phase 1**
([docs/superpowers/specs/2026-06-07-portrait-aspect-delivery-design.md](2026-06-07-portrait-aspect-delivery-design.md),
shipped + merged to `main` at `c28f9e6`) built the **delivery foundation** —
`cinema/aspect.py` (the single source of truth + the gate), assembly dims, the
scorecard, the `/api/config` GET + settings-PUT gate, and the FE fallback. Phase 1
deliberately left `SUPPORTED_ASPECT_RATIOS = ["16:9"]` so `9:16` is **defined but
gated** until the generators produce true portrait. **Phase 2 builds the image
half** (native 9:16 keyframes). Phase 3 (per-provider 9:16 video + the final
un-gate) is a separate spec and follows Phase 2.*

---

## 1. Problem

Phase 1 made the **delivery side** 9:16-ready end-to-end (dims, validation, UI,
scorecard) and verified `cinema/aspect.py` already defines
`ASPECT_DIMENSIONS["9:16"] = (1080, 1920)`. But the **image-keyframe generators
still hard-code landscape geometry** at every site. If a project's
`aspect_ratio` were `9:16` (it can't be selected yet — gated), keyframes would
still generate at 16:9 and the portrait container would letterbox/crop them.

The keyframe path also never receives `aspect_ratio` at all: `controller.py`
reads `global_settings` but does not extract or thread `aspect_ratio` into
generation (`grep aspect_ratio cinema/shots/controller.py` → 0 hits, *verified*).

**Hard-coded landscape geometry in image generation (all verified this session,
HEAD `e018c71`):**

| Path | Tier | Site | Today (16:9) | Evidence |
|---|---|---|---|---|
| ComfyUI primary | production | `phase_c_assembly.py:212-213` node 102 `EmptyLatentImage` | 1344×768 | *verified — `sed -n 211,214p`* |
| ComfyUI primary | max | `pulid_max.json` node 102 `EmptyLatentImage` (template default; **not** overridden by `quality_max.py`) | 1024×576 | *verified — `json` node 102; `grep '"102"' quality_max.py` shows only rewire `:408,:435,:579`, no width/height set* |
| ComfyUI primary | max | `quality_max.py:609-611` node 950 "Final downsample resolution" | `params.final_resolution` default (3840, 2160) | *verified — `sed -n 606,611p`* |
| FAL fallback ×2 | both† | `phase_c_assembly.py:515, :534` `"aspect_ratio"` | `"16:9"` | *verified — `grep -n aspect_ratio`* |
| FAL fallback | both† | `phase_c_assembly.py:555` `"image_size"` enum | `"landscape_16_9"` | *verified — `grep -n image_size`* |
| Pollinations | both† | `phase_c_assembly.py:570` URL `width=1344&height=768` | 1344×768 | *verified — `grep -n pollinations.ai/prompt`* |

†*The FAL/Pollinations fallbacks live in the production-path function
`generate_ai_broll` (`phase_c_assembly.py`). Max tier delegates to
`quality_max.generate_ai_broll_max` at `:118-120` and returns early; if
`quality_max` is unavailable it falls through to the production path
(`:143`), so the production fallbacks cover both tiers' degradation case.*

**Control-flow fact (decisive for the per-tier split, verified):**
`generate_ai_broll` (`phase_c_assembly.py:76`) branches at `:118`
`if quality_tier == "max":` → imports + calls `generate_ai_broll_max` and
returns; the node-102 mutation at `:211-214` is therefore **production-only**.
Max geometry lives entirely in `quality_max.py`.

---

## 2. Decisions (user-adjudicated, 2026-06-08)

| # | Decision | Choice |
|---|---|---|
| D1 | Scope split & sequence | **Two specs, Phase 2 (image) → Phase 3 (video).** Build Phase 2 first as the prerequisite; the un-gate is Phase 3's final task. |
| D2 | Fallback coverage | **Full coverage — all image paths** (ComfyUI primary + FAL + Pollinations) emit true 9:16. The fallback params already exist, so it's cheap and avoids silent landscape degradation. |
| D3 | Aspect granularity | **Project-level only** (`global_settings.aspect_ratio`, as Phase 1 persists it). No per-shot aspect override. |
| D4 | Implementation approach | **Approach A — geometry stays in `cinema/aspect.py`.** Add a pure `portrait_swap` helper; thread the `aspect_ratio` string; each site applies the swap to its own base latent. |
| D5 | Portrait latent strategy | **Transpose each tier's validated landscape latent** when portrait (1344×768→768×1344 prod; 1024×576→576×1024 max; (3840,2160)→(2160,3840) max final). Inherits each tier's tuned pixel budget; all dims divisible by 16 (FLUX-friendly). FAL's `image_size` is the one non-transpose site (named enum → `portrait_16_9`). |

---

## 3. Architecture — geometry helper + threading

```
global_settings["aspect_ratio"]            (domain/project_manager.py:318, default "16:9")
        │  controller.py:477 reads global_settings → ctx
        ▼
controller.py ──aspect_ratio──► generate_ai_broll(aspect_ratio="16:9")     [phase_c_assembly.py:76]
                                       │
            quality_tier=="max"? ──────┤  (:118 branch)
                  │ no (production)     └──► generate_ai_broll_max(aspect_ratio=...)   [quality_max.py]
                  ▼                              │
       pulid.json node 102 (768×1344)    pulid_max.json node 102 (576×1024)
       + FAL/Pollinations fallbacks       + node 950 final_resolution (2160×3840)
                  │                              │
                  └──────────► cinema/aspect.py : portrait_swap(w, h, aspect_ratio) ◄──────────┘
                                  (→ (h, w) when is_portrait(aspect_ratio), else (w, h))
```

The helper is pure, reuses the existing `is_portrait()`, never raises:

```python
def portrait_swap(w: int, h: int, aspect_ratio: Optional[str]) -> tuple[int, int]:
    """Transpose (w, h) → (h, w) when aspect_ratio resolves to portrait.

    Lets each generation path keep its own tuned pixel budget, just rotated.
    Unknown/None/landscape → unchanged. Mirrors resolve_output_dimensions'
    never-raise contract.
    """
    return (h, w) if is_portrait(aspect_ratio) else (w, h)
```

---

## 4. Phase 2 — the implementable spec

### 4.1 `cinema/aspect.py` — add `portrait_swap` (new)

Add the pure helper above. No change to `ASPECT_DIMENSIONS`,
`SUPPORTED_ASPECT_RATIOS` (the gate stays `["16:9"]`), or existing functions.
A FAL enum constant lives here too (single source of truth for aspect↔FAL
naming):

```python
# FAL image_size enum is a named bucket, not pixel dims — map by orientation.
FAL_IMAGE_SIZE = {"16:9": "landscape_16_9", "9:16": "portrait_16_9"}

def fal_image_size(aspect_ratio: Optional[str]) -> str:
    return FAL_IMAGE_SIZE.get(aspect_ratio or "", "landscape_16_9")
```

### 4.2 Threading — `controller.py` → `generate_ai_broll` → `generate_ai_broll_max`

- Add `aspect_ratio: str = DEFAULT_ASPECT_RATIO` param to `generate_ai_broll`
  (`phase_c_assembly.py:76`) and `generate_ai_broll_max` (`quality_max.py`).
  **Default = "16:9" → no-op for all existing callers** (backward compatible).
- `controller.py` (~`:477`, where it already reads `global_settings` into `ctx`)
  passes `global_settings.get("aspect_ratio", DEFAULT_ASPECT_RATIO)`.
- The `:118` max branch forwards `aspect_ratio` to `generate_ai_broll_max`.

*Plan-time confirm (Rule #12): grep all callers of `generate_ai_broll` /
`generate_ai_broll_max` and confirm the new defaulted param doesn't break a
positional call site.*

### 4.3 Production ComfyUI — `phase_c_assembly.py:212-213` (node 102)

```python
w, h = portrait_swap(1344, 768, aspect_ratio)
workflow["102"]["inputs"]["width"]  = w
workflow["102"]["inputs"]["height"] = h
```

### 4.4 Max ComfyUI — `quality_max.py` (node 102 + node 950)

- **Node 102 (latent):** today inherits the `pulid_max.json` template default
  (1024×576) — `quality_max.py` does not set it. Add an explicit portrait
  override so portrait actually transposes:
  ```python
  if is_portrait(aspect_ratio):
      lw, lh = portrait_swap(1024, 576, aspect_ratio)   # → 576×1024
      workflow["102"]["inputs"]["width"]  = lw
      workflow["102"]["inputs"]["height"] = lh
  ```
  (Base 1024×576 read from the template / a named constant, not re-magic'd —
  plan-time: confirm whether to read the template's current value or use the
  documented default.)
- **Node 950 (final downsample, `:609-611`):** swap the `final_resolution`
  default:
  ```python
  w, h = portrait_swap(*params.get("final_resolution", (3840, 2160)), aspect_ratio)
  workflow["950"]["inputs"]["width"]  = w   # → 2160 when portrait
  workflow["950"]["inputs"]["height"] = h   # → 3840 when portrait
  ```

### 4.5 FAL fallbacks — `phase_c_assembly.py:515, :534, :555`

```python
# :515, :534
"aspect_ratio": aspect_ratio,                 # "16:9" | "9:16"
# :555
"image_size": fal_image_size(aspect_ratio),   # "landscape_16_9" | "portrait_16_9"
```

### 4.6 Pollinations — `phase_c_assembly.py:570`

```python
pw, ph = portrait_swap(1344, 768, aspect_ratio)
poll_url = f"https://image.pollinations.ai/prompt/{encoded}?width={pw}&height={ph}&nologo=True&model=flux&seed={seed or 42}"
```

### 4.7 Data flow (summary)

`global_settings.aspect_ratio` (project record) → controller `ctx` →
`generate_ai_broll(aspect_ratio)` → {production sites | `generate_ai_broll_max`} →
`portrait_swap` / `fal_image_size` at each site → ComfyUI/FAL/Pollinations emit
native 9:16 → assembly (Phase 1 resolver, already wired) composes a true 9:16
`final_cinema.mp4`.

---

## 5. Error handling

- **Unknown / absent / landscape aspect → 16:9 everywhere.** `portrait_swap` and
  `fal_image_size` default to the landscape value via `is_portrait`/the enum
  `.get`. No new raise path.
- **Backward compatibility.** The `aspect_ratio` param defaults to `"16:9"`, so
  every current (landscape) generation is a literal no-op — **zero behavior
  change** until a project opts into `9:16`.
- **Gate stays closed.** Phase 2 does **not** modify `SUPPORTED_ASPECT_RATIOS`;
  `9:16` remains un-selectable in the UI/API. Phase 2 is exercised by passing
  `aspect_ratio="9:16"` directly (tests + a dev harness), never through the
  gated user path. This preserves the "generators first, un-gate last"
  ordering — flipping the gate before video lands (Phase 3) would expose a
  half-working mode.

---

## 6. Testing

**Unit (offline, no GPU):**
- `portrait_swap` truth table: 16:9 → no-op; 9:16 → transpose; unknown/None →
  no-op; both tier base latents (1344×768, 1024×576) and (3840,2160) → correct
  portrait tuples.
- `fal_image_size`: 16:9 → `landscape_16_9`; 9:16 → `portrait_16_9`; unknown →
  landscape default.
- Threading: with a mocked `workflow` dict and `aspect_ratio="9:16"`, assert
  node 102 = (768,1344) production / (576,1024) max, node 950 = (2160,3840),
  FAL params + Pollinations URL carry portrait values; with `"16:9"` assert all
  unchanged (no-op proof).
- Caller-compat: confirm existing `generate_ai_broll` callers pass with the new
  defaulted param.

**On-pod validation (the empirical proof unit tests can't give):**
- Generate one production + one max keyframe at `aspect_ratio="9:16"` on the GPU
  pod; confirm true portrait pixels + photoreal quality. This validates D5 (that
  768×1344 / 576×1024 are *good* FLUX latents, not just valid ones). Standard
  "wire it, then pod-validate" discipline.

---

## 7. Plan-time verifications (Rule #12/#13) — RESULTS (this session)

Grounded by a Rule #17 read-only survey (5 parallel scouts + synthesis) +
director spot-check of load-bearing citations at HEAD `e018c71`:

- ✅ `cinema/aspect.py:23` gate = `["16:9"]`; `ASPECT_DIMENSIONS` has both ratios
  (full read).
- ✅ `phase_c_assembly.py:212-213` node 102 = 1344×768 (production-only; `:118`
  max branch returns early).
- ✅ `pulid_max.json` node 102 = 1024×576; `quality_max.py` does NOT set node-102
  width/height (only rewires latent edges `:408/:435/:579`).
- ✅ `quality_max.py:609-611` node 950 `final_resolution` default (3840,2160),
  parameterized via `params`.
- ✅ FAL three param shapes: `aspect_ratio` (`:515,:534`) + `image_size`
  (`:555` `landscape_16_9`); Pollinations URL `width=1344&height=768` (`:570`).
- ✅ `controller.py` does not thread `aspect_ratio` today (0 grep hits).
- **Rule #13 symmetric-site audit:** all six geometry sites enumerated above are
  the complete set of image-dimension writers; the `shot_type='portrait'` hits
  at `phase_c_assembly.py:254,:336` are PuLID-strength tuning, **unrelated to
  aspect** (do not conflate — verified).

*Open plan-time confirms (for the implementation plan, not blockers):*
- Exact caller list of `generate_ai_broll` / `generate_ai_broll_max` (positional
  arg safety).
- Whether node-102 max base should be read from the template at runtime vs. a
  named constant.

---

## 8. Non-goals (Phase 2)

- **The un-gate** (`SUPPORTED_ASPECT_RATIOS` += `"9:16"`) — Phase 3's final task.
- **Video providers** (Veo/Kling/Sora/LTX/Hedra/Runway/Seedance) — Phase 3.
- **Per-shot aspect** — project-level only (D3).
- **`media_report` target-dim persistence hardening** (Phase-1 spec §4.3 / Q11) —
  scorecard robustness, rides with Phase 3 or later.
- **Other ratios** (`1:1`, `21:9`, `4:3`) — out of program scope; only `9:16`.

---

## 9. Estimated scope (Phase 2)

- `cinema/aspect.py`: +~10 LoC (`portrait_swap` + `fal_image_size`/`FAL_IMAGE_SIZE`).
- `phase_c_assembly.py`: ~6 sites edited (node 102; FAL ×3; Pollinations) +
  `aspect_ratio` param + thread to max — ~15-20 LoC.
- `quality_max.py`: node 102 override + node 950 swap + `aspect_ratio` param —
  ~10 LoC.
- `cinema/shots/controller.py`: thread `aspect_ratio` from `global_settings` —
  ~2-3 LoC.
- Tests: ~1 new unit file (`portrait_swap`/`fal_image_size`/threading), ~60-100
  LoC.

**~40-50 LoC production + tests, backward-compatible, gate untouched.** Small,
reviewable, single-prerequisite slice. Lane assignment decided at
writing-plans / dispatch time (the cross-file threading touches
`controller.py` + `phase_c_assembly.py` + `quality_max.py`, so likely
director-driven Lane B; note the live overlap with operator's deferred-minors
batch on `controller.py` — re-verify HEAD + grep their landed hunk before
dispatch).
