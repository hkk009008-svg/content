# Design — Veo native config-threading fix

**Date:** 2026-05-29
**Status:** Draft (brainstorming → spec)
**Author:** director-seat
**Topic:** Fix `veo_native.generate_video()` so the caller's params (`generate_audio`, `duration`, `resolution`, `reference_images`, driving video) actually reach the Veo API, instead of being dropped or passed as kwargs the SDK rejects.

---

## 1. Problem & motivation

`veo_native.generate_video()` builds `types.GenerateVideosConfig(person_generation="allow_adult", aspect_ratio="16:9")` — only two hardcoded fields — and routes the rest of its params wrong. Three confirmed bugs, one root cause (config not threaded):

1. **`reference_images` / `reference_video` → TypeError → Veo fails.** They are added to `generate_kwargs` and passed as **top-level kwargs** to `client.models.generate_videos(**generate_kwargs)` (`veo_native.py:126`, `:137`, `:147`). But the SDK method's signature is `(model, prompt, image, video, source, config)` — it does **not** accept `reference_images` / `reference_video` top-level. So any call with character refs or a driving video raises `TypeError`, is caught at `:181`, and returns `None`. For a dialogue/character shot routed to `VEO_NATIVE` with no other engine enabled, there is no fallback → the motion shot fails outright. **This is the most severe symptom — the dialogue→Veo path almost never actually runs on Veo.**
2. **`generate_audio` dropped → silent video.** Accepted (`:65`) and logged (`:96`) but never set on the config. Even when Veo runs, no audio is requested.
3. **`duration` / `resolution` dropped → SDK defaults.** Accepted but never threaded into the config, so the caller's intent is ignored.

**Live confirmation in flight:** the operator's `scripts/run_veo_dialogue_test.py` (a `VEO_NATIVE`-only dialogue E2E with an ffprobe audio-track assertion) is running now and will exhibit symptom (1) or (2). Root-cause + this design were sent to the operator at `4e12a1a`.

**Why it matters:** "dialogue → Veo native audio" is non-functional end-to-end. This fix also unblocks the deferred hybrid-dialogue build (`docs/superpowers/plans/2026-05-29-hybrid-dialogue-voice-routing.md`) — its native branch is moot if Veo emits no audio (or errors on refs).

## 2. Goals / Non-goals

**Goals**
- Every caller-intent param of `generate_video()` reaches the Veo request: `generate_audio`, `duration`, `resolution`, `reference_images` via `GenerateVideosConfig`; the driving video via the SDK's top-level `video=` param.
- No illegal top-level kwargs passed to `generate_videos` (kill the TypeError).
- The config-mapping is unit-testable offline (no Vertex, no spend).
- Preserve existing behavior: SDK-version robustness for the driving video, `None`-on-failure + cascade contract, `person_generation`/`aspect_ratio` defaults.

**Non-goals**
- No change to the dialogue routing (`controller.py`) or the `phase_c_ffmpeg.py` call site — they already pass the right values; the bug is purely in `veo_native.py`'s config build.
- No new aspect_ratio / person_generation params (YAGNI — keep hardcoded unless a caller needs them).
- The live E2E validation is the operator's existing `run_veo_dialogue_test.py`, not new code here.

## 3. Verified current state (grounded, 2026-05-29)

| Fact | Evidence |
|---|---|
| `GenerateVideosConfig` has fields `generate_audio`, `duration_seconds`, `resolution`, `reference_images`, `aspect_ratio`, `person_generation` | `.venv/bin/python` introspection of `google-genai 2.6.0` `types.GenerateVideosConfig.model_fields` |
| `generate_videos` takes only `(self, model, prompt, image, video, source, config)` — no `reference_images`/`reference_video` top-level | introspection of `google.genai.models.Models.generate_videos` |
| Config built with only `person_generation` + `aspect_ratio` | `veo_native.py:103-106` |
| `reference_images` added as top-level kwarg | `veo_native.py:117-126` |
| `reference_video` (driving video) added as top-level kwarg, with SDK-version try/except | `veo_native.py:128-144` |
| `generate_audio` accepted + logged, never set on config | `veo_native.py:65`, `:96` |
| `generate_videos(**generate_kwargs)` call site | `veo_native.py:147` |
| Caller passes `reference_images=multi_angle_refs`, `generate_audio=(... or has_dialogue)` | `phase_c_ffmpeg.py:280-282` (VEO_NATIVE branch) |
| Dialogue routes to `VEO_NATIVE` | `cinema/shots/controller.py:1117-1141` |
| `VEO_DURATIONS = ["5s","6s","8s"]`; `duration: str = "8s"` param | `veo_native.py:21`, `:63` |
| `veo_native.py` is the operator's active file | commit `39d095e` (model-id fix) |

## 4. Design (Approach B — pure config builder)

Extract the param→config mapping into a pure, side-effect-free helper so it is unit-testable without a live Veo call. `generate_video` keeps the I/O (image loading, the API call, polling, download) and delegates config construction.

### 4.1 `_build_generate_videos_config()` (new, pure)

```python
def _build_generate_videos_config(
    *,
    generate_audio: bool,
    duration: str,                # "5s" | "6s" | "8s"
    resolution: str,              # "720p" | "1080p" | ...
    reference_images: list | None,  # list of types.Image already loaded (or None)
    person_generation: str = "allow_adult",
    aspect_ratio: str = "16:9",
) -> "types.GenerateVideosConfig":
    """Map generate_video() params to a GenerateVideosConfig. Pure — no file/network I/O.
    Image objects are loaded by the caller; this only assembles the config."""
```

It sets `generate_audio`, `duration_seconds` (parsed from `"8s"`→`8`), `resolution`, `person_generation`, `aspect_ratio`, and `reference_images` (when non-empty) on the config. Returns the config. **Contract on malformed `duration`** (not matching `"<N>s"`, or `N` not in `VEO_DURATIONS`): default `duration_seconds` to `8` (Veo's safe default) rather than raising — a formatting edge must not fail the whole generation. A unit test pins this.

> **Plan-time SDK-verify gates** (confirm against `google-genai 2.6.0` before pinning): exact `config.resolution` accepted format (e.g. `"720p"` vs `"720"`); `duration_seconds` type (int seconds); whether `reference_images` wants `types.Image` vs a `VideoGenerationReferenceImage` wrapper. Where the actual API differs from this sketch, use the actual and note the divergence (plan-vs-source rule).

### 4.2 `generate_video()` changes

- Build the loaded `reference_images` list as today (`types.Image.from_file`, the `[:3]` cap, existence checks), then pass the loaded list to `_build_generate_videos_config(...)` instead of `generate_kwargs`.
- Call: `self.client.models.generate_videos(model=self._model, prompt=prompt, image=start_image, video=<driving or omitted>, config=cfg)`.
- **Driving video** moves from the illegal `generate_kwargs["reference_video"]` to the top-level **`video=`** param (the SDK's documented slot), keeping the existing version-robustness try/except (skip silently if the installed SDK lacks `types.Video`). **Verify gate:** confirm `video=` is the correct slot for a motion-reference clip (vs `source=`); if uncertain, keep the current skip-on-error guard so an unsupported field can't break the call.
- Everything downstream (operation poll, RAI check, download) is unchanged.

### 4.3 Error handling (unchanged contract)

The whole body stays in the existing `try/except` that returns `None` on failure (→ caller cascade). The driving-video load keeps its own inner try/except. No new exception types surface to callers.

## 5. Validation

**Tier 1 — offline unit tests (the deliverable here; no Vertex, no spend):**
- `_build_generate_videos_config(generate_audio=True, ...)` → config `.generate_audio is True`, `.duration_seconds == 8`, `.resolution == "720p"`, `.reference_images` set when passed.
- Call-site test: mock `client.models.generate_videos`; call `generate_video(..., reference_images=[...], generate_audio=True)`; assert it is invoked with a `config=` carrying the fields and **no** `reference_images` / `reference_video` top-level kwarg (the TypeError-regression guard); driving video appears as `video=`.
- A regression test that the old top-level-kwarg shape would have raised (assert the new call signature only uses allowed params).

**Tier 2 — live E2E (NOT new code — the operator's harness):**
- `scripts/run_veo_dialogue_test.py` is the live validation. **Acceptance after the fix lands:** the script exits 0; its `_ffprobe_streams` reports an audio track on the motion take; the character is preserved (refs applied, no TypeError). Spend-gated (~Veo per-shot cost); run when authorized. Coordinate with the operator (their script, their thread).

## 6. Risks

- **Coordination — `veo_native.py` is the operator's active file** (`39d095e`, + their running test). The fix overlaps; the plan must flag it and the implementer must `git log -1 veo_native.py` + re-read before editing. **Recommended sequencing: land the fix AFTER the operator's `run_veo_dialogue_test.py` run exits** (so the diff doesn't collide mid-run, and the operator's failure output becomes the live confirmation that pins the unit-test expectations).
- **SDK API shape uncertainty** (§4.1/§4.2 gates). Mitigation: verify against `google-genai 2.6.0` at plan execution; keep the driving-video skip-on-error guard.
- **Behavior change:** Veo will now actually run for character shots (previously TypeError→cascade) and request audio. This is the intended fix, but it changes what `VEO_NATIVE` produces — call out in the doc-sync + PR body.

## 7. Files touched (est.)

- `veo_native.py` — add `_build_generate_videos_config()`; rewire `generate_video()` config build + the `generate_videos` call (driving video → `video=`).
- `tests/unit/test_veo_native_config.py` (new) — Tier-1 unit tests.
- Doc-sync: `ARCHITECTURE.md` Veo/native-audio section if it asserts the (broken) current behavior.

## 8. Out of scope

The dialogue routing; the `phase_c_ffmpeg.py` call site; the hybrid-dialogue build (separate plan); new aspect_ratio/person_generation params; the live-E2E harness (operator's `run_veo_dialogue_test.py`).
