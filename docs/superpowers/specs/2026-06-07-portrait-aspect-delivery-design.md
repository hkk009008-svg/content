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
| Image/keyframe gen (ComfyUI) | `pulid.json` EmptyLatent 1344×768; `pulid_max.json` node 102 EmptyLatent 1024×576 + node 950 ImageScale 3840×2160 | `pulid.json:117`, `pulid_max.json:303,510` *(verified)* |
| Video gen (providers) | Veo's config has `aspect_ratio` (`:57`) but `generate_video` (`:138`) doesn't thread it → hard-pinned `"16:9"`; Sora `size` strings landscape-only; LTX `{w,h}` dict landscape-only; Kling exposes NO aspect param at all | `veo_native.py:57,138`, `sora_native.py:21`, `ltx_native.py:34`, `kling_native.py` *(verified — see §7-D matrix)* |
| Final assembly | hard-codes `scale=1920:1080…pad=1920:1080` — **the sole resolution-fixing site** (§7-A verified) | `cinema_pipeline.py:1337` (`_assemble_final`, def :1282) |
| Scorecard conformance (U3) | `EXPECTED_RESOLUTION = (1920, 1080)`; check at `:94` | `cinema/capability_scorecard.py:20,94` |
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

16:9 must remain **byte-identical** to today. `_assemble_final` already receives
`settings` (verified `:1282`; both callers pass `project["global_settings"]`), so
no signature change. **Golden string** — the test MUST assert exact equality of
`_normalize_filter(1920, 1080)` against this verified current literal
(`cinema_pipeline.py:1337`):
`scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30`

**Plan-time check (§7-A):** grep `_assemble_final` (and the rest of
`cinema_pipeline.py`'s assembly path) for any *other* hard-coded `1920`/`1080`
(a second scale/concat pass, a thumbnail, the loudnorm/probe path). Every clip
that contributes to `final_cinema.mp4` must use the resolved dims, or a portrait
project gets mixed-size clips. U3's `probe_final_media` only *reports* actual
dims (no change needed there).

### 4.3 `cinema/capability_scorecard.py` (`_build_media_block`)
*Verified current state:* `EXPECTED_RESOLUTION = (1920, 1080)` (`:20`), compared at
`:94` (`resolution_ok = (w,h) == EXPECTED_RESOLUTION`); `_build_media_block(project)`
(`:57`) has the project dict in scope but does **not** currently read
`global_settings` (the `gs = ...` at `:119` is in `build_capability_scorecard`,
def `:117`, not in `_build_media_block`) — the plan adds that read. So a 9:16 project would
assemble correctly (after §4.2) yet the scorecard would **false-fail** it against
1920×1080 — the exact F4 symptom. The plan MUST NOT skip this wiring.

Replace the `EXPECTED_RESOLUTION` constant comparison with
`resolve_output_dimensions(gs.get("aspect_ratio") or DEFAULT_ASPECT_RATIO)` so
`format.pass` checks the project's target, not a fixed 1920×1080:
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

### 4.4 `web_server.py:319` `/api/config` — gate at the UI *(BUILD STEP, not yet done)*
*Verified:* `:319` hard-codes `["16:9","9:16","1:1","21:9","4:3"]`; it does **not**
import `SUPPORTED_ASPECT_RATIOS` (and `cinema/aspect.py` does not exist yet — `ls`
exit 1). This is a Phase-1 deliverable, NOT an existing state. Build: (a) create
`cinema/aspect.py` (§4.1); (b) import + replace the literal at `:319` with
`SUPPORTED_ASPECT_RATIOS`. Until Phase 3 this returns `["16:9"]` — gating portrait
**and** fixing the latent bug (stops offering `1:1/21:9/4:3`, which never worked).

### 4.4b `web/src/components/settings/ProductionSection.tsx:148` — close the FE gate hole *(REQUIRED — corrects "no TS change")*
*Verified gate hole:* the dropdown renders
`{(config?.aspect_ratios || ['16:9','9:16','1:1']).map(...)}`. The hard-coded
fallback activates whenever `config.aspect_ratios` is null/undefined (config fetch
failure / cold cache), **bypassing the /api/config gate entirely**. Phase 1 MUST
change the fallback to `['16:9']` (or remove it so the dropdown renders only what
config returns). This means Phase 1 **does** touch the frontend — the FE gate
(`cd web && npx tsc --noEmit && npm run build`) is in scope. *(Cosmetic-only,
NOT selection sources, left as-is: `EditorialShell.tsx:313` `'9:16'` display
default; `PipelineLayout.tsx:276` `'9:16 Vertical'` literal text.)*

### 4.5 `web_server.py` settings PUT (~517) — gate at the API
*Verified:* inside the `_mutate_project` closure, `Project.model_validate(project)`
runs at `:514` **before** `project["global_settings"].update(data["global_settings"])`
at `:518`. The `Project` model uses `extra="allow"`, so `model_validate` will **NOT**
reject an unsupported `aspect_ratio` value — a **bespoke check** is required (do
not rely on the model). Add it **before** the `.update()`:
- Only when `"aspect_ratio"` is present in `data["global_settings"]` (partial
  updates must stay valid — e.g. editing `language` on a project whose stored
  `aspect_ratio` is a now-removed `1:1` must NOT be rejected).
- If present and `∉ SUPPORTED_ASPECT_RATIOS` → **reject 400** with a fixed body
  shape: `{"error": "unsupported aspect_ratio", "value": <v>, "supported": SUPPORTED_ASPECT_RATIOS}`.
- Coerce-to-default is the rejected alternative (silent correction hides client
  bugs). This is the only client-reachable arbitrary writer (§7-C), so this single
  gate closes the API hole.

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

Test file placement (named so a cold implementer doesn't guess):
- **`tests/unit/test_cinema_aspect.py`** (new): `resolve_output_dimensions` for `16:9`/`9:16`/unknown/empty/None; `is_portrait`; `is_supported`; gate currently excludes `9:16`. Plus `_normalize_filter` (import from `cinema_pipeline`): **assert EXACT string equality** of `_normalize_filter(1920,1080)` against the §4.2 golden literal (byte-identical regression guard), and `_normalize_filter(1080,1920)` → the `1080:1920` variant.
- **`tests/unit/test_u3_media_conformance.py`** (extend): scorecard `format.pass` — aspect `16:9` + 1920×1080 probe → pass; aspect `9:16` + 1080×1920 → pass, + 1920×1080 → fail. Reuse existing fixtures/patterns.
- **`tests/unit/test_web_server_aspect_validation.py`** (new, or reuse an existing settings/PUT test module if present): `/api/config` `aspect_ratios == SUPPORTED_ASPECT_RATIOS`; PUT unsupported `aspect_ratio` → 400 with the §4.5 body; supported → 200; payload without `aspect_ratio` (e.g. a `language`-only edit on a `1:1`-stored project) → unaffected (backward-compat).
- **FE:** `ProductionSection.tsx:148` fallback change → **FE gate IS in scope**: `cd web && npx tsc --noEmit && npm run build` (corrects the earlier "no TS change" assumption).
- **Regression:** existing `_assemble_final` behavior + all U3 tests + the 16:9 path stay green.
- §15 smoke (`.venv/bin/python scripts/ci_smoke.py`) + full unit suite (run with `env -u GIT_INDEX_FILE` under D-a, or `test_check_doc_claims.py` false-fails).

## 7. Plan-time verifications (Rule #12/#13) — **RESULTS** (verify-review workflow, 2026-06-07)

- **§7-A (Phase 1) — CONFIRMED:** `cinema_pipeline.py:1337` (in `_assemble_final`) is the **only** resolution-fixing site in the final-assembly path. Other `1920/1080` refs are video-*generation* params (`phase_c_ffmpeg.py:261` Sora, `:317` LTX, `:682` Runway), not assembly. Audio/loudnorm/color/xfade paths preserve resolution (no `-vf scale`). Routing the resolver through `:1337` alone is sufficient.
- **§7-B (Phase 1) — REFUTED (gate hole found):** `/api/config` is **not** the only UI source — `ProductionSection.tsx:148` has a hard-coded fallback that bypasses the gate (now folded into §4.4b as a required Phase-1 FE change). `EditorialShell.tsx:313` / `PipelineLayout.tsx:276` are cosmetic-only displays.
- **§7-C (Phase 1) — CONFIRMED:** of 5 `global_settings` writers (`web_server.py:434` language-defaults, `:518` PUT-unrestricted, `:769` lora-paths, `:959` style-paths, `:1481` style-rules), only PUT `/api/projects/<pid>` (`:518`) accepts arbitrary client `aspect_ratio`. The single §4.5 gate at `:518` closes the API hole.
- **§7-D (Phase 3 feasibility) — provider matrix (verified cold; web-doc items flagged unverified):**

  | Provider | Native 9:16 | Mechanism / gap | Phase-3 action |
  |---|---|---|---|
  | **Veo** | **yes** | `_build_generate_videos_config` has `aspect_ratio` (`:57`) but `generate_video` (`:138`) doesn't thread it → hard-pinned `"16:9"` | thread the param through `generate_video`; no fallback |
  | **Sora** | **no** | `RESOLUTION_MAP` (`:21`) landscape-only; `size` takes flat `WxH` so a portrait entry *could* be added **iff** OpenAI docs support it (UNVERIFIED) | verify docs; else crop/pad fallback |
  | **LTX** | **unknown** | passes `{width,height}` with no aspect-lock so `width<height` is syntactically passable; API acceptance UNVERIFIED (docs.ltx.video) | verify docs; else crop/pad fallback |
  | **Kling** | **no** | `kling_native.py` exposes **no** aspect/size/width param at all — landscape only | **exclude from 9:16 routing** OR post-gen crop/pad |
  | **Hedra** | **unknown** | not inspected; optional lip-sync overlay (droppable per memory) | verify only if still in the routing chain |

  **Implication for the Q3 decision ("all active providers"):** only Veo supports native 9:16 today; Kling cannot; Sora/LTX/Hedra need doc verification + likely crop/pad fallback. "All providers" is achievable only with a per-provider fallback strategy — **revisit this scope at the Phase-3 spec** (the "Veo-first, gate the rest" option may be the pragmatic Phase-3a).

  *Caveat (Rule #17):* `shot_type="portrait"` (`phase_c_ffmpeg.py:242`, a cinematographic framing/close-up concept) is **independent** of `9:16` aspect — do not conflate them when wiring Phase 3.

## 8. Non-goals (Phase 1)

- No image-gen change (Phase 2), no video-provider change (Phase 3).
- No real 9:16 content; `9:16` not selectable until Phase 3's gate flip.
- No 1:1/4:5/21:9 (those ratios stay out of `SUPPORTED_ASPECT_RATIOS` and out of the UI; revisit per future demand).
- No persist-target-dims-in-media_report hardening (noted §4.3; follow-up).

**Phase-1 release note (operators):** the scorecard derives expected dims from the
*current* `aspect_ratio`, so **changing `aspect_ratio` on an already-assembled
project** flips a passing format tile to fail until you re-assemble. (Mitigated
fully by the deferred persist-target-dims hardening; until then, re-assemble after
any aspect change.) Low-impact today since `9:16` isn't selectable until Phase 3.

## 9. Estimated scope (Phase 1)

~120–180 production LoC: `cinema/aspect.py` (new, ~30) + `cinema_pipeline.py`
(`_normalize_filter` + call site, ~15) + `cinema/capability_scorecard.py` (~10)
+ `web_server.py` (`/api/config` + PUT validation, ~15) + tests (~80–100).
Single coherent slice; no cross-provider work (that's Phase 3).
