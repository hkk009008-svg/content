# Scene Transitions MVP — Design

**Date:** 2026-05-29
**Status:** Draft (approved in brainstorming; pending spec-review + user sign-off)
**Scope:** Optional cross-dissolve transitions at scene boundaries during final
assembly. Opt-in, uniform dissolve, with a frontend toggle.

## Context

The cinema pipeline assembles per-scene clips into a final video by hard-cutting
everything together. `_assemble_final` (`cinema_pipeline.py:1199`) normalizes each
clip (re-encode to 1920x1080@30fps, `libx264 crf 20`, `:1247`) then stitches with
the FFmpeg `concat` demuxer using `-c copy` (`:1271-1275`) — pure hard cuts. The
docstring is explicit: *"Hard cuts between all clips (no transitions)"* (`:1202`).

There is no transition capability anywhere (`grep xfade|acrossfade` → 0 hits). This
spec adds an **optional** cinematic cross-dissolve **only at scene→scene
boundaries**, leaving shot-to-shot cuts within a scene as hard cuts (the
cinematically standard treatment; dissolving every cut looks like a slideshow).

This is a **local, pod-independent** feature — pure FFmpeg, no GPU / video-API
dependency. (An earlier idea of reusing the dead `_build_transition_prompt`
helper was rejected: its prose output is the wrong shape for an FFmpeg `xfade`,
which takes a filter name + duration, not prose. `_build_transition_prompt`
remains an unused delete-candidate, tracked separately.)

## Goals / Non-goals

**Goals (MVP):**
- A single uniform cross-dissolve (`xfade` `dissolve`) at scene boundaries, fixed
  default duration `0.5s`.
- Opt-in: OFF by default. Existing hard-cut assembly is byte-for-byte unchanged
  when the flag is off.
- Togglable end-to-end: a frontend checkbox + a duration control, persisted via
  the existing settings path, consumed by assembly.
- Audio stays in A/V sync across the dissolve.

**Non-goals (explicit YAGNI):**
- Mood-mapped transition styles (dark→light = fade-through-white, etc.) — a
  possible v2; would use a small mood→filter map, **not** the prose helper.
- Per-boundary or per-transition-type configuration.
- Transitions on the shot-level *preview* path (`stitch_modules`,
  `cinema/shots/controller.py:1862`) — previews stay hard-cut.
- AI-generated transition clips (needs a text-to-video wrapper that does not
  exist; pod-dependent).

## Approach

**Chosen: A — two-level stitch.**
1. Group normalized clips by scene (today they are flattened into one list at
   `cinema_pipeline.py:1213`).
2. Concat each scene's clips with `-c copy` (hard cuts *within* a scene — fast,
   unchanged).
3. `xfade`-chain the per-scene videos (with `acrossfade` for audio), computing each
   junction's `offset` from probed cumulative durations.

The `xfade` chain runs over *N_scenes* inputs (few), not *N_clips* — a small,
tractable filtergraph. Within-scene cuts stay stream-copy.

**Rejected:**
- **B — single mega-filtergraph** mixing `concat` + `xfade` over all clips with
  per-junction offset math. Fragile arithmetic, one giant graph, no upside over A.
- **C — AI-generated transition clips.** Needs a non-existent text-to-video
  wrapper and is pod-dependent. Out of scope.

## Components

### 1. `_probe_duration(path) -> float` (new, `phase_c_ffmpeg.py`)
Thin `ffprobe` wrapper. Mirrors the existing inlined pattern at `lip_sync.py:77`/`:99`:
`["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path]`.
No shared duration helper exists today, so this is new. Returns float seconds.

### 2. `xfade_concat(scene_videos, out_path, duration=0.5, transition="dissolve") -> str` (new, `phase_c_ffmpeg.py`)
Builds the chained `xfade` (video) + `acrossfade` (audio) filtergraph over the
ordered per-scene videos and re-encodes once to `out_path`. Offset for junction
*k* = (sum of scene durations `0..k`) − (cumulative transition overlaps so far).
Returns `out_path`.

### 3. `_assemble_final` changes (`cinema_pipeline.py:1199`)
- Read flags off the existing `settings` arg (no signature change):
  `scene_transitions = settings.get("scene_transitions", False)` and
  `transition_duration = settings.get("transition_duration", 0.5)` — mirrors the
  existing `settings.get("mood", "cinematic")` at `:1290`.
- **OFF (default):** unchanged — current flat `concat -c copy` path (`:1261-1285`).
- **ON:** keep clips grouped per scene during collection (`:1211-1226`) and
  normalization (`:1237-1259`); per-scene `concat -c copy` → scene videos; then
  `xfade_concat(scene_videos, stitched, transition_duration)`.
- Steps 4+ (color grade `:1287`, BGM/foley `amix`) are **structurally unchanged** —
  they still receive a single `stitched` mp4, so the existing `amix` inputs-2-vs-3
  tests (`test_guided_pipeline.py`) stay valid.

### 4. Settings flag (no backend parse change)
`global_settings` is an open merge — `web_server.py` `PUT /api/projects/<pid>` does
`project["global_settings"].update(data["global_settings"])`. Any key the frontend
sends is persisted automatically. `_assemble_final` reads it via the settings
fetched at `cinema_pipeline.py:751` (verified: that dict is the one passed to
`_assemble_final` at `:770`). **No new backend request-parsing code.**

### 5. Frontend toggle (React/TS SPA under `web/`)
Mirror the existing `coherence_check_enabled` boolean toggle (per survey, in
`web/src/components/settings/PostProcessingSection.tsx`) — exact line numbers to be
confirmed at implementation (they drift):
- Add `scene_transitions?: boolean` + `transition_duration?: number` to the
  `GlobalSettings` TypeScript interface (`web/src/types/project.ts`).
- Add a "Scene Transitions" checkbox in `PostProcessingSection.tsx` mirroring the
  `coherence_check_enabled` checkbox; add a conditionally-rendered duration
  `<Slider>` (a Slider component already exists in that file) shown only when the
  checkbox is on.
- **No change** to `SettingsPanel.tsx`'s `update()` sender — it already PUTs the
  full `global_settings` dict.

## Data flow

```
Frontend checkbox (PostProcessingSection.tsx)
  → update(key, value)  [SettingsPanel.tsx — unchanged]
  → PUT /api/projects/<pid> { global_settings: { scene_transitions, transition_duration } }
  → web_server.py :506  project["global_settings"].update(...)  [unchanged]
  → persisted to project record
  ...at render/assembly time...
  → cinema_pipeline.py:751  settings = project.get("global_settings", {})
  → :770  _assemble_final(scene_data, bgm_path, settings)
  → reads scene_transitions / transition_duration → xfade_concat or flat concat
```

## Edge cases

- **< 2 scenes with valid clips:** `xfade` needs ≥2 inputs → fall back to the flat
  `concat` path (no transition).
- **Scene shorter than `transition_duration`:** clamp that junction's transition to
  `min(transition_duration, scene_len * 0.4)`; if still degenerate, skip the
  transition at that junction (hard cut there).
- **Scene with 0 valid clips:** dropped from the boundary sequence (no empty input).
- **`xfade_concat` failure:** log and fall back to the flat `concat` path so a
  transition error never fails the whole assembly (mirrors the normalize-fallback
  posture at `:1254-1259`).

## Audio behavior (known tradeoff)

`xfade` is video-only; `acrossfade` overlaps audio by the same `duration` so total
A/V stays in sync. This crossfades ~0.5s of **dialogue** audio at scene boundaries.
Bounded: only at scene cuts (not within-scene), and BGM/foley are layered later and
continuous, so they are unaffected. Accepted for MVP.

## Testing

Mirror the existing mocked-subprocess pattern (`test_guided_pipeline.py` captures
`subprocess.run` calls; `ffprobe` mocked to return fixed durations):
1. **OFF → regression guard:** assembly issues a `concat` demuxer command and **no**
   `xfade`/`acrossfade` in any command.
2. **ON + ≥2 scenes:** assembly issues per-scene `concat` + an `xfade`+`acrossfade`
   filtergraph; assert the transition type and that offsets derive from probed
   durations and `transition_duration`.
3. **ON + 1 scene:** falls back to flat `concat` (no `xfade`).
4. **ON + ultra-short scene:** transition clamped/skipped at that junction.
5. **ON + `xfade_concat` raises:** falls back to flat `concat`; assembly still
   returns a path.
6. **Unit tests for `xfade_concat` offset math** with known durations.

## Insertion points

- `phase_c_ffmpeg.py` — add `_probe_duration` + `xfade_concat`. [new]
- `cinema_pipeline.py:1199` (`_assemble_final`) — read flags; branch ON/OFF; group
  by scene when ON. [pipeline]
- `web/src/types/project.ts` (`GlobalSettings`) — add two optional keys. [type]
- `web/src/components/settings/PostProcessingSection.tsx` — checkbox + duration
  slider, mirroring `coherence_check_enabled`. [frontend-markup]
- `web_server.py:506` — **no change** (open-merge passthrough). [verified]
- `web/src/components/SettingsPanel.tsx` — **no change** (universal sender).

## Out of scope / follow-ups

- Mood-mapped transition styles (v2).
- Deleting the now-confirmed-unused `_build_transition_prompt` (separate decision;
  this MVP does not use it).
- Transitions on the shot preview path.
