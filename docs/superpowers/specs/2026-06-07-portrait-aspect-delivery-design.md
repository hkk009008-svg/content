# Portrait / aspect-aware delivery (9:16) — design

*Status: user-approved design (2026-06-07). Director-seat, brainstorm → spec.*
*Origin: U3 Lane V finding **F4** — the format-conformance check hard-codes
`EXPECTED_RESOLUTION = (1920, 1080)`. Investigation showed F4 is not a scorecard
bug: portrait delivery is unimplemented end-to-end, so the check is correct
today. User chose to **build portrait delivery** rather than patch the symptom.*

## 1. Problem

`aspect_ratio` is a live project setting (`global_settings.aspect_ratio`,
default `"16:9"`; `domain/project_manager.py:318`) and the UI offers five values
(`web_server.py:319` `/api/config` → `["16:9","9:16","1:1","21:9","4:3"]`).
**None of them change the output.** Every surface that fixes a dimension
hard-codes landscape:

| Surface | Today | Evidence |
|---|---|---|
| Image/keyframe gen (ComfyUI) | `pulid.json` EmptyLatent 1344×768 → 2688×1536; `pulid_max.json` 1024×576 → 3840×2160 | `pulid.json:117`, `pulid_max.json:303,510` |
| Video gen (5 providers) | Veo accepts `aspect_ratio` (passed `"16:9"`); Sora `size` strings; LTX `{w,h}` dict; Kling/Hedra differ — all landscape | `veo_native.py:57`, `sora_native.py:18`, `ltx_native.py:35` |
| Final assembly | hard-codes `scale=1920:1080…pad=1920:1080` | `cinema_pipeline.py:1337` (`_assemble_final`, def :1282) |
| Scorecard conformance (U3) | `EXPECTED_RESOLUTION = (1920, 1080)` | `cinema/capability_scorecard.py:20` |
| `aspect_ratio` consumers | only `generate_style_rules` / `style_director` (LLM prompt text) | `cinema_pipeline.py:930`, `llm/style_director.py:70` |

So `final_cinema.mp4` is **always 1920×1080**; selecting `9:16` silently yields
a landscape file. Two costs: (a) a latent bug — the UI offers four ratios
(`9:16/1:1/21:9/4:3`) that do nothing; (b) no vertical/social delivery, a real
capability gap against the program's full-capability intent
(`docs/PROGRAM-MANUAL.md`).

## 2. Decisions (user-adjudicated)

| Fork | Decision | Why |
|---|---|---|
| Target ratios | **9:16 only** (+ existing 16:9) | Dominant social-vertical case; smallest coherent scope. 1:1/4:5/21:9 deferred. |
| Production path | **Native 9:16 generation** (not crop/pad of 16:9) | Real vertical composition; no thrown-away pixels; aligns with full-capability intent. |
| Provider coverage | **All active providers** (Veo/Kling/Sora/LTX) | No routing restriction; a portrait shot can use any engine. Each provider's 9:16 support is **verified before** relying on it (§7). |
| Sequencing | **Phased, gated until complete** | Each phase independently reviewed/merged; `9:16` stays unselectable until the whole chain works — users never hit a half-working mode. |

## 3. Architecture — shared foundation + three phases

**Shared foundation (built in Phase 1, consumed by all phases):** one source of
truth, `cinema/aspect.py`. No surface hard-codes dimensions after this lands.

```
cinema/aspect.py
  ASPECT_DIMENSIONS = {"16:9": (1920,1080), "9:16": (1080,1920)}
  DEFAULT_ASPECT_RATIO = "16:9"
  SUPPORTED_ASPECT_RATIOS = ["16:9"]        # the GATE — Phase 3's last task → +"9:16"
  resolve_output_dimensions(aspect_ratio) -> (W,H)   # unknown/unsupported → DEFAULT dims; never raises
  is_portrait(aspect_ratio) -> bool
  is_supported(aspect_ratio) -> bool
```

| Phase | Scope | Done-when |
|---|---|---|
| **1 — Foundation** *(this spec; implementable now)* | `cinema/aspect.py`; assembly derives (W,H); scorecard derives expected dims; `/api/config` + settings PUT gated to `SUPPORTED_ASPECT_RATIOS` | Container aspect-correct + consistent; latent bug fixed; `9:16` still not selectable |
| **2 — Native image keyframes** *(own spec later)* | `pulid.json` / `pulid_max.json` portrait latent + upscale dims, driven by the resolver | Keyframes generate at true 9:16 |
| **3 — Native video + un-gate** *(own spec later)* | Per-provider 9:16 (Veo/Kling/Sora/LTX), each **verified first** with crop/pad fallback for any that can't; final task flips `SUPPORTED_ASPECT_RATIOS` to include `"9:16"` | Portrait delivery fully live + selectable |

**Gating property:** every phase builds and unit-tests against `"9:16"`
directly, but the user-facing capability stays `["16:9"]` until Phase 3's last
task flips one constant. Machinery is exercised throughout; no half-working mode
is ever exposed. The flip is a single-constant change, not scattered
conditionals.

---

## 4. Phase 1 — Foundation (the implementable spec)

### 4.1 `cinema/aspect.py` (new)
Pure module, no project deps. Contents per §3 foundation block.
- `resolve_output_dimensions(aspect_ratio)`: `ASPECT_DIMENSIONS.get(aspect_ratio,
  ASPECT_DIMENSIONS[DEFAULT_ASPECT_RATIO])`. Defensive: unknown/empty/`None` →
  DEFAULT dims (debug-logged); never raises (assembly must not crash on a bad
  setting).
- `is_portrait(ar)`: `h > w` for the resolved dims.
- `is_supported(ar)`: `ar in SUPPORTED_ASPECT_RATIOS`.

### 4.2 `cinema_pipeline.py::_assemble_final` (~1337)
Replace the hard-coded `scale=1920:1080:force_original_aspect_ratio=decrease,
pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30` with dims from
`resolve_output_dimensions(settings.get("aspect_ratio", DEFAULT_ASPECT_RATIO))`,
built by a **pure helper** so it's unit-testable without ffmpeg:

```python
def _normalize_filter(w: int, h: int) -> str:
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps=30")
```

16:9 must remain **byte-identical** to today (`1920:1080`). `_assemble_final`
already receives `settings`, so no signature change.

**Plan-time check (§7-A):** grep `_assemble_final` (and the rest of
`cinema_pipeline.py`'s assembly path) for any *other* hard-coded `1920`/`1080`
(a second scale/concat pass, a thumbnail, the loudnorm/probe path). Every clip
that contributes to `final_cinema.mp4` must use the resolved dims, or a portrait
project gets mixed-size clips. U3's `probe_final_media` only *reports* actual
dims (no change needed there).

### 4.3 `cinema/capability_scorecard.py` (`_build_media_block`)
Replace the `EXPECTED_RESOLUTION` constant with
`resolve_output_dimensions(project's aspect_ratio)` so `format.pass` checks the
project's target, not a fixed 1920×1080:
`format.pass = (w,h) == resolve_output_dimensions(aspect) and vcodec=="h264"
and acodec=="aac"`.
- Source aspect from `project["global_settings"]["aspect_ratio"]` (default
  `"16:9"`).
- **Sub-decision (resolved):** derive from the *current* setting (simplest;
  aspect rarely changes post-assembly) rather than persisting target dims into
  `media_report` at assembly-time. Persisting is recorded as a **hardening
  follow-up** (immunity to a setting change between assembly and scorecard read),
  out of Phase 1 scope to avoid re-touching the U3 persist hook.
- `EXPECTED_VCODEC`/`EXPECTED_ACODEC` unchanged.

### 4.4 `web_server.py:319` `/api/config` — gate at the UI
Source `"aspect_ratios"` from `SUPPORTED_ASPECT_RATIOS` (import from
`cinema.aspect`) instead of the hard-coded five. Until Phase 3 this returns
`["16:9"]` — gating portrait **and** fixing the latent bug (stops offering
`1:1/21:9/4:3`, which never worked). Visible UI change: the dropdown narrows to
the truth.

### 4.5 `web_server.py` settings PUT (~517) — gate at the API
The PUT `/api/projects/<pid>` path does `global_settings.update(data[...])` with
no validation. Add a lightweight guard: an incoming `aspect_ratio ∉
SUPPORTED_ASPECT_RATIOS` is **rejected (400 + message)** (UI-only gates are
bypassable). Coerce-to-default is the rejected alternative (silent correction
hides client bugs). Only validate when `aspect_ratio` is present in the payload
(partial updates must stay valid).

### 4.6 Data flow
`global_settings.aspect_ratio` (default 16:9, validated ∈ SUPPORTED) →
`_assemble_final` → `resolve_output_dimensions` → `_normalize_filter` → ffmpeg →
`final_cinema.mp4` at (W,H). Scorecard reads the same setting → same resolver →
`format.pass`. UI dropdown ← `SUPPORTED_ASPECT_RATIOS`.

## 5. Error handling (Phase 1)

| Failure | Behavior |
|---|---|
| `aspect_ratio` unknown/empty/None at assembly | resolver → DEFAULT (1920×1080); today's behavior preserved; no crash |
| Unsupported `aspect_ratio` in settings PUT | 400 + message (rejected at boundary) |
| Scorecard reads a project whose aspect is unknown | resolver → DEFAULT dims; `format.pass` computed against default |
| `cinema.aspect` import fails in scorecard/web (shouldn't — pure stdlib) | scorecard already wraps bar-sourcing in try/except → falls back; web `/api/config` would surface the import error normally |

## 6. Testing (Phase 1)

- `cinema/aspect.py`: `resolve_output_dimensions` for `16:9`/`9:16`/unknown/empty/None; `is_portrait`; `is_supported`; the gate currently excludes `9:16`.
- `_normalize_filter(w,h)`: `1920,1080 → "scale=1920:1080:…pad=1920:1080:…"` (byte-match today) and `1080,1920 → "…1080:1920…"`.
- Scorecard `format.pass`: aspect `16:9` with a 1920×1080 probe → pass; aspect `9:16` with 1080×1920 → pass, with 1920×1080 → fail. Reuse U3 fixtures (`tests/unit/test_u3_media_conformance.py` patterns).
- `/api/config`: `aspect_ratios == SUPPORTED_ASPECT_RATIOS` (currently `["16:9"]`).
- Settings PUT: unsupported `aspect_ratio` → 400; supported → 200; payload without `aspect_ratio` → unaffected.
- **Regression:** existing `_assemble_final` behavior + all U3 tests + the 16:9 path stay green; the normalize filter for 16:9 is unchanged.
- §15 smoke (`.venv/bin/python scripts/ci_smoke.py`) + full unit suite. FE gate: `cd web && npx tsc --noEmit && npm run build` (only if FE touched — `/api/config` is backend; the dropdown is data-driven so no TS change expected — **verify**).

## 7. Plan-time verifications (Rule #12/#13, carried into the plan)

- **§7-A (Phase 1):** grep all hard-coded `1920`/`1080` in `cinema_pipeline.py`'s assembly path; confirm `_assemble_final` is the only resolution-fixing site (or route the others through the resolver too).
- **§7-B (Phase 1):** confirm `/api/config`'s `aspect_ratios` is the *only* source the UI uses for the dropdown (grep `web/src` for `aspect_ratio` option lists / any hard-coded duplicate).
- **§7-C (Phase 1):** confirm the settings PUT path (`web_server.py:~517`) is the only writer of `global_settings.aspect_ratio` reachable from the client (Rule #13 symmetric-endpoint audit) — else the API gate has a hole.
- **§7-D (Phase 3 feasibility, surfaced now):** verify each provider's true 9:16 support before Phase 3 relies on it — Veo `aspect_ratio="9:16"` (documented?), Sora `size` portrait strings, LTX `{width<height}` dict, Kling aspect/resolution API. Any provider without native 9:16 needs a documented crop/pad fallback or exclusion. **This is the largest Phase 3 unknown; record the per-provider matrix in the Phase 3 spec.**

## 8. Non-goals (Phase 1)

- No image-gen change (Phase 2), no video-provider change (Phase 3).
- No real 9:16 content; `9:16` not selectable until Phase 3's gate flip.
- No 1:1/4:5/21:9 (those ratios stay out of `SUPPORTED_ASPECT_RATIOS` and out of the UI; revisit per future demand).
- No persist-target-dims-in-media_report hardening (noted §4.3; follow-up).

## 9. Estimated scope (Phase 1)

~120–180 production LoC: `cinema/aspect.py` (new, ~30) + `cinema_pipeline.py`
(`_normalize_filter` + call site, ~15) + `cinema/capability_scorecard.py` (~10)
+ `web_server.py` (`/api/config` + PUT validation, ~15) + tests (~80–100).
Single coherent slice; no cross-provider work (that's Phase 3).
