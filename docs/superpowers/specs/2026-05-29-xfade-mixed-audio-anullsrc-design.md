# Design — F1 M1: mixed-audio fix for `xfade_concat` (anullsrc-pad, surgical)

**Date:** 2026-05-29
**Status:** Design — approved, pending spec review
**Author:** director-seat
**Topic:** Close the (c)-deferred Lane V #25 **M1** mixed-audio-presence edge in the
opt-in scene-transitions stitch (`phase_c_ffmpeg.py::xfade_concat`).
**Origin:** Lane V #25 M1 (documented + (c)-deferred per user 2026-05-29); escalation
path "(b) anullsrc-pad" recorded in `phase_c_ffmpeg.py::xfade_concat` and mailbox
`2026-05-29T02-43-46Z`.

---

## 1. Problem

The cycle-17 scene-transitions MVP cross-dissolves per-scene videos via
`xfade_concat` (opt-in, default-OFF). After the F1 CRITICAL fix (`1f9d46b`), audio is
crossfaded **only when every input has an audio stream**:

```python
# phase_c_ffmpeg.py:1286 (current)
include_audio = all(_has_audio_stream(v) for v in scene_videos)
```

**M1 (the bug):** on **mixed audio-presence** inputs — some scene videos carry an
embedded audio stream, some don't — `all(...)` is `False`, so the **entire** stitch
goes video-only and the embedded audio is **dropped from the scenes that had it**.

This arises when motion engines differ per scene (e.g. an Omnihuman/Veo scene that
embeds dialogue audio sits next to a Kling-Native/LTX silent scene). It is narrow
(transitions are default-OFF and GPU-gated end-to-end) but the impact — silently
discarding real embedded dialogue — is a correctness bug, not cosmetic.

### Why `all()` is there (the F1 history, not to be regressed)
The pre-F1 code emitted an **unconditional** `acrossfade` referencing `[j:a]` for
every input. On the default silent path (`[0:a]` absent) ffmpeg errored, the caller
silently fell back to a hard-cut concat, and the cross-dissolve was a **silent
no-op**. F1 (`1f9d46b`) made audio conditional on `all(_has_audio_stream)`. This spec
keeps the F1 guarantee intact and only adds correct handling for the mixed case.

---

## 2. Grounding (verified against HEAD this session)

| Fact | Evidence |
|---|---|
| `xfade_concat` defined | `phase_c_ffmpeg.py:1270`; builder `_build_xfade_filtergraph:1232`; helpers `_has_audio_stream:1212`, `_probe_duration:1202` |
| Builder callers (blast radius) | `xfade_concat` (`phase_c_ffmpeg.py:1295`) + tests `test_xfade_transitions.py:28,37,113`; only `:113` passes `include_audio=` explicitly |
| `_assemble_final` calls `xfade_concat` | `cinema_pipeline.py:1269` (opt-in branch, `use_transitions` at `:1256`) |
| **Step-5 voice source is decoupled from `stitched` audio** | `cinema_pipeline.py:1362` — `use_standalone_dialogue = (dialogue_track_path and exists)`; voice label `[N:a]` vs `[0:a]` chosen at `:1383-1386` by that flag, **not** by whether `stitched` has audio |
| ffmpeg available locally | `ffmpeg version 8.1` (`/opt/homebrew/bin/ffmpeg`) — this is CPU/ffmpeg work, **unit-testable now without the pod** |
| Existing tests are mock-based | `test_xfade_transitions.py` mocks `subprocess.run`/`_probe_duration`/`_has_audio_stream`, asserts on the constructed command; no real-ffmpeg test exists |

**Key de-risk.** The escalation note warned to "verify against the `_assemble_final`
standalone-mp3 dialogue mux first." Verified: step-5 selects the dialogue source on
**"do per-scene dialogue mp3s exist?"**, *not* on whether `stitched` carries audio.
Therefore emitting audio from `xfade_concat` where it previously emitted none does
**not** suppress the standalone dialogue mux — `stitched[0:a]` is simply not mapped
when standalone dialogue is used (output maps `0:v` + the mixed `[aout]`). **No
dialogue regression on any path.**

---

## 3. Goals / Non-goals

**Goal.** When transitions are ON and inputs are mixed audio-presence, preserve each
scene's embedded audio across the cross-dissolve (silence where a scene has none),
instead of dropping all audio. Keep the all-audio and none-audio paths byte-for-byte
unchanged (surgical scope, user-selected).

**Non-goals (documented, explicitly out of scope):**
1. **Step-5's binary voice source.** `_assemble_final` cannot represent "some scenes
   embedded + some scenes standalone-dialogue" simultaneously (it picks one source).
   M1 neither fixes nor worsens this; it is a separate, deeper limitation of the
   step-5 audio model.
2. **All-audio heterogeneous formats.** The all-audio path keeps its current *raw*
   acrossfade; if two engines both embed audio in differing formats it could still
   mismatch. Pre-existing, out of the surgical scope. (The mixed path *does* normalize
   — see §4.)
3. **No-BGM copy branch.** `cinema_pipeline.py:1437` copies `stitched` as-is and does
   not mux dialogue; unrelated to M1.

---

## 4. Design (Approach A1 — in-filtergraph anullsrc + canonical normalization)

### 4.1 Behavior contract (three cases)
`xfade_concat` computes a per-input presence list and branches:

| Case | Condition | Audio behavior | Status |
|---|---|---|---|
| All audio | `all(audio_flags)` | raw acrossfade on `[j:a]` (current) | unchanged |
| None audio | `not any(audio_flags)` | video-only, no audio map (current) | unchanged |
| **Mixed** | `any` and not `all` | normalize every leg + `anullsrc`-pad silent legs, then acrossfade | **new** |

### 4.2 `xfade_concat` (`phase_c_ffmpeg.py`)
- Replace the scalar gate with a per-input list:
  ```python
  audio_flags = [_has_audio_stream(v) for v in scene_videos]
  ```
- Pass `audio_flags` to the builder. The output still maps `[alab]` and sets
  `-c:a aac -b:a 192k` whenever an audio chain is emitted (all **or** mixed); video-only
  when none. Input list stays `scene_videos` only — `anullsrc` is a filter *source*,
  needs no `-i`.

### 4.3 `_build_xfade_filtergraph` (`phase_c_ffmpeg.py`)
- **Signature (backward-compatible):** change the 4th parameter from
  `include_audio: bool = True` to `audio_flags: list[bool] | None = None`, where
  `None` ≡ "all inputs have audio" (preserves the positional test calls at
  `test_xfade_transitions.py:28,37`). Derive:
  ```python
  if audio_flags is None or all(audio_flags):   emit_audio, padded = True,  False
  elif not any(audio_flags):                     emit_audio, padded = False, False
  else:                                          emit_audio, padded = True,  True
  ```
- **Video chain:** unchanged.
- **Audio chain:**
  - `emit_audio = False` → omit (video-only), return audio label `None`.
  - `padded = False` (all-audio) → **current raw chain**: `[prev_a][{j+1}:a]acrossfade=d={t}[a{j+1}]`.
  - `padded = True` (mixed) → build a normalized leg per input, then acrossfade the legs:
    - real (`audio_flags[j]`): `[{j}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[na{j}]`
    - silent: `anullsrc=r=48000:cl=stereo,atrim=0:{_fmt(durations[j])},aformat=sample_fmts=fltp:channel_layouts=stereo[na{j}]`
    - acrossfade chain over `[na{j}]` with the same `t` used by the video xfade (keeps A/V in sync; total audio length = `sum(durations) − (n−1)·t`, matching the video).
- `aresample`+`aformat` on **every** leg guarantees acrossfade's matching-rate/layout/
  format precondition regardless of heterogeneous embedded formats (the exact
  mixed-engine reality M1 comes from).

> **To validate at implementation (TDD):**
> (a) the exact silent-source incantation (`anullsrc=...,atrim=0:{dur}` vs
> `aevalsrc=0:d={dur}`) against ffmpeg 8.1;
> (b) **[spec-review R2]** that `_fmt`'s decimal precision is sufficient for `atrim` —
> an under-trimmed silent pad could make `acrossfade` run short. The Tier-2 real-ffmpeg
> test (§6, test 5) catches both by asserting the output's audio-stream duration.
> A mock cannot prove ffmpeg accepts the graph — which is the class of bug F1 was.

### 4.4 Interaction with `_assemble_final` step 5
No change to `cinema_pipeline.py`. Per §2, step-5 keys on standalone-dialogue
existence, so the new mixed-case `stitched[0:a]` is consumed only when there are no
standalone dialogue mp3s (pure-embedded mixed engines → correct: embedded dialogue
preserved, silence elsewhere). When standalone dialogue mp3s exist, `[0:a]` is ignored
and the standalone mux path is untouched.

---

## 5. Error handling
Unchanged. `xfade_concat` wraps the ffmpeg run in `try/except` and **raises** on
failure (`CalledProcessError`); `_assemble_final` catches and falls back to a hard-cut
concat (`cinema_pipeline.py:1274-1284`). The mixed branch introduces no new raise
paths beyond ffmpeg itself; a malformed graph degrades to the existing hard-cut
fallback (the F1 silent-no-op is gone because audio is now emitted by construction).

---

## 6. Test plan (two-tier; runnable locally now)

**Tier 1 — mock-based construction/regression tests** (match existing convention in
`tests/unit/test_xfade_transitions.py`; mock `_probe_duration`/`_has_audio_stream`/
`subprocess.run`; assert on the built filtergraph + maps):
1. `test_mixed_audio_pads_silent_leg` — flags `[True, False]`: filtergraph contains
   `anullsrc` for the silent leg, `aresample`/`aformat` on both legs, an `acrossfade`,
   and the command has `-map [a...]` + `-c:a aac`.
2. `test_mixed_audio_silent_first` — flags `[False, True]`: anullsrc on leg 0; order/
   offset robustness.
3. `test_all_audio_unchanged` — flags `[True, True]` (or `audio_flags=None`): raw
   acrossfade, **no** `anullsrc`/`aformat` (regression guard for surgical scope).
4. `test_no_audio_video_only` — flags `[False, False]`: no audio map (this **replaces/
   renames** the current `test_include_audio_false_omits_acrossfade` at
   `test_xfade_transitions.py:112-114`, updating `include_audio=False` →
   `audio_flags=[False, False]`).

**Tier 2 — one real-ffmpeg integration test** (NEW pattern for this module; guard with
`@pytest.mark.skipif(shutil.which("ffmpeg") is None, ...)` so ffmpeg-less CI skips):
5. `test_mixed_audio_runs_and_outputs_audio` — synthesize via lavfi: audio clip =
   `testsrc`+`sine`; silent clip = `testsrc` only; call `xfade_concat([audio, silent])`;
   assert the run succeeds **and** `ffprobe -show_streams` reports an audio stream of
   the expected (`sum−overlap`) duration. This proves the graph ffmpeg-*executes* —
   the thing mocks (and the pre-F1 code) missed.

Existing positional builder tests (`:28,:37`) are unaffected (default `audio_flags=None`).

---

## 7. Impact analysis (CLAUDE.md pre-edit discipline)
- `_build_xfade_filtergraph` signature change touches: its body (`phase_c_ffmpeg.py:1260,1267`),
  `xfade_concat` (`:1295-1296,:1302,:1305`), and `test_xfade_transitions.py:113`
  (the explicit `include_audio=` call). Positional calls at `:28,:37` keep working via
  the `None` default. Re-grep `_build_xfade_filtergraph` / `include_audio` after the edit
  to confirm zero stale references.
- No `cinema_pipeline.py` change. No public-API change (`xfade_concat`'s signature is
  unchanged; only the private builder's 4th param changes, backward-compatibly).

---

## 8. Acceptance criteria
1. Mixed-presence inputs + transitions ON → output `stitched.mp4` has an audio stream;
   audio-bearing scenes' audio is preserved (not dropped); silent scenes contribute
   silence; no ffmpeg error.
2. All-audio and none-audio paths produce **identical** commands to today (Tier-1
   regression tests 3 & 4 green).
3. No dialogue regression on the standalone-dialogue path (guaranteed structurally by
   §4.4; no `cinema_pipeline.py` change).
4. Tier-1 mock tests + Tier-2 real-ffmpeg test green locally; §15 smoke OK; full suite
   green.

---

## 9. Estimated scope
~30 LOC of production change in one file (`phase_c_ffmpeg.py`) + ~5 tests in
`tests/unit/test_xfade_transitions.py`. Implementation + verification are **not
pod-gated** (CPU/ffmpeg). End-to-end multi-scene render validation remains pod-gated
and is tracked separately (scene-transitions real-render open item).
