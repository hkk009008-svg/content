# xfade Mixed-Audio (anullsrc-pad) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. (Note: per the project's CLAUDE.md, this single coupled ~30-LOC slice in one file may instead be executed in main context — operator/director discretion at the execution handoff.)

**Goal:** Close the Lane V #25 **M1** edge — when scene-transition inputs have *mixed* audio presence (some have an embedded audio stream, some don't), pad the silent ones with `anullsrc` so the cross-dissolve preserves embedded audio instead of dropping it all.

**Architecture:** Surgical change to `phase_c_ffmpeg.py` only. `xfade_concat` computes a per-input `audio_flags` list and passes it to `_build_xfade_filtergraph`, which branches three ways: all-audio → raw acrossfade (unchanged); none → video-only (unchanged); mixed → normalize every leg (`aresample`/`aformat`) + `anullsrc`-pad the silent legs → acrossfade. No `cinema_pipeline.py` change (step-5's dialogue mux is decoupled — see spec §4.4).

**Tech Stack:** Python 3.13, ffmpeg 8.1 (local, CPU — not pod-gated), `unittest` + `unittest.mock`, `.venv/bin/python -m pytest`.

**Spec:** [docs/superpowers/specs/2026-05-29-xfade-mixed-audio-anullsrc-design.md](../specs/2026-05-29-xfade-mixed-audio-anullsrc-design.md)

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `phase_c_ffmpeg.py` | `_build_xfade_filtergraph` (filtergraph builder) + `xfade_concat` (driver) | Modify (~30 LOC): signature `include_audio` → `audio_flags`; add mixed branch; update M1 comment |
| `tests/unit/test_xfade_transitions.py` | unit tests (mock-based) + new real-ffmpeg integration test | Modify: rename/update 1 test; add ~5 tests + 1 skipif-guarded real-ffmpeg test |

No other files. `xfade_concat`'s public signature is unchanged; only the private builder's 4th param changes (backward-compatibly via `None` default).

---

## Chunk 1: Implementation

### Task 1: Refactor `_build_xfade_filtergraph` signature (behavior-preserving)

Migrate the 4th param `include_audio: bool = True` → `audio_flags: Optional[list] = None` (where `None` ≡ all-audio). Behavior stays **identical to today**: all-audio → acrossfade; everything else (none *and* mixed) → video-only. The mixed→padded behavior is added in Task 2. This isolates the mechanical signature change from the new logic.

**Files:**
- Modify: `phase_c_ffmpeg.py` — `_build_xfade_filtergraph` (~`:1232-1267`), `xfade_concat` (~`:1285-1306`)
- Test: `tests/unit/test_xfade_transitions.py` (~`:112-117` rename/update; add 2 tests)

- [ ] **Step 1: Update + add the failing tests**

In `tests/unit/test_xfade_transitions.py`, **read** the existing `test_include_audio_false_omits_acrossfade` (~`:112-117`) to preserve its assertions, then **rename + update** it to use the new param, and add two regression tests in the same `TestCase` class:

```python
    def test_no_audio_video_only(self):
        # was test_include_audio_false_omits_acrossfade; include_audio= -> audio_flags=
        fg, vlab, alab = pcf._build_xfade_filtergraph(
            [4.0, 5.0], 0.5, "dissolve", audio_flags=[False, False])
        self.assertNotIn("acrossfade", fg)
        self.assertIsNone(alab)

    def test_audio_flags_none_defaults_all_audio(self):
        fg, vlab, alab = pcf._build_xfade_filtergraph([4.0, 5.0], 0.5, "dissolve")
        self.assertIn("acrossfade", fg)
        self.assertNotIn("anullsrc", fg)
        self.assertEqual(alab, "a1")

    def test_all_audio_uses_raw_acrossfade(self):
        fg, vlab, alab = pcf._build_xfade_filtergraph(
            [4.0, 5.0], 0.5, "dissolve", audio_flags=[True, True])
        self.assertIn("[0:a][1:a]acrossfade", fg)
        self.assertNotIn("anullsrc", fg)
        self.assertNotIn("aformat", fg)
        self.assertEqual(alab, "a1")
```

- [ ] **Step 2: Run the tests — verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_xfade_transitions.py -v`
Expected: `test_no_audio_video_only` + `test_all_audio_uses_raw_acrossfade` ERROR/FAIL (unexpected kwarg `audio_flags`). `test_audio_flags_none_defaults_all_audio` PASSES already (positional, still all-audio). Pre-existing tests still pass.

- [ ] **Step 3: Migrate the signature (behavior-preserving)**

In `phase_c_ffmpeg.py`, replace the `_build_xfade_filtergraph` signature + audio handling. New version (mixed still video-only here — added in Task 2):

```python
def _build_xfade_filtergraph(durations: list, duration: float, transition: str,
                             audio_flags: Optional[list] = None):
    """Build a chained xfade (video) + acrossfade (audio) filter_complex string.

    Returns (filter_complex, final_video_label, final_audio_label).
    Requires len(durations) >= 2. audio_flags is a per-input list of bools
    (True = that input has an audio stream); None ≡ all inputs have audio.
      - all True -> raw acrossfade on [j:a]   (engine-embedded audio)
      - else     -> video-only, audio label None
    (Task 2 adds the mixed -> anullsrc-pad branch.)
    """
    n = len(durations)
    if n < 2:
        raise ValueError("xfade filtergraph requires >= 2 inputs")
    if audio_flags is None:
        audio_flags = [True] * n

    emit_audio = all(audio_flags)  # Task 2 widens this to any() + a padded branch

    t = _fmt(duration)
    video_parts = []
    audio_parts = []
    prev_a = "0:a"
    prev_v = "0:v"
    cumulative = durations[0]
    for j in range(n - 1):
        offset = cumulative - (j + 1) * duration
        vlabel = f"v{j + 1}"
        video_parts.append(
            f"[{prev_v}][{j + 1}:v]xfade=transition={transition}:"
            f"duration={t}:offset={_fmt(offset)}[{vlabel}]"
        )
        prev_v = vlabel
        if emit_audio:
            alabel = f"a{j + 1}"
            audio_parts.append(f"[{prev_a}][{j + 1}:a]acrossfade=d={t}[{alabel}]")
            prev_a = alabel
        cumulative += durations[j + 1]

    filter_complex = ";".join(video_parts + audio_parts)
    return filter_complex, f"v{n - 1}", (f"a{n - 1}" if emit_audio else None)
```

Then update `xfade_concat` (~`:1285-1306`): replace the `include_audio` scalar with the per-input list and switch the two `if include_audio:` guards to `if alab is not None:`.

```python
    durations = [_probe_duration(v) for v in scene_videos]
    audio_flags = [_has_audio_stream(v) for v in scene_videos]
    t_eff = min(duration, 0.4 * min(durations))
    filter_complex, vlab, alab = _build_xfade_filtergraph(
        durations, t_eff, transition, audio_flags=audio_flags)

    cmd = ["ffmpeg", "-y"]
    for v in scene_videos:
        cmd += ["-i", v]
    cmd += ["-filter_complex", filter_complex, "-map", f"[{vlab}]"]
    if alab is not None:
        cmd += ["-map", f"[{alab}]"]
    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "20"]
    if alab is not None:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += [out_path]
```

(Leave the existing M1 known-limitation comment in place for now; Task 2 rewrites it.)

- [ ] **Step 4: Run the tests — verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_xfade_transitions.py -v`
Expected: all PASS (including the unchanged pre-existing tests — behavior is identical for all/none).

- [ ] **Step 5: Verify no stale callers + smoke**

Run: `grep -rn "include_audio" phase_c_ffmpeg.py tests/` → Expected: **no matches** (fully migrated).
Run: `.venv/bin/python scripts/ci_smoke.py` → Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add phase_c_ffmpeg.py tests/unit/test_xfade_transitions.py
git commit -m "refactor(ffmpeg): _build_xfade_filtergraph include_audio -> audio_flags (behavior-preserving)"
```

---

### Task 2: Implement the mixed-case anullsrc-pad

Widen the audio branch: `any(audio_flags)` emits audio; when mixed (`any` but not `all`), normalize every leg and `anullsrc`-pad the silent legs before acrossfade. Update the M1 comment to reflect the fix.

**Files:**
- Modify: `phase_c_ffmpeg.py` — `_build_xfade_filtergraph` audio section + the `xfade_concat` M1 comment
- Test: `tests/unit/test_xfade_transitions.py` (add 3 mock tests + 1 real-ffmpeg test; add `import shutil, tempfile`)

- [ ] **Step 1: Write the failing tests (mock construction + real-ffmpeg)**

Add to the builder's `TestCase` in `tests/unit/test_xfade_transitions.py`:

```python
    def test_mixed_audio_pads_silent_leg(self):
        # input 0 has audio, input 1 is silent (durations 4.0, 5.0)
        fg, vlab, alab = pcf._build_xfade_filtergraph(
            [4.0, 5.0], 0.5, "dissolve", audio_flags=[True, False])
        self.assertIn("[0:a]aresample=48000", fg)                          # real leg normalized
        self.assertIn("anullsrc=r=48000:cl=stereo,atrim=0:5", fg)          # silent leg, input-1 duration
        self.assertIn("aformat=sample_fmts=fltp:channel_layouts=stereo", fg)
        self.assertIn("acrossfade", fg)
        self.assertEqual(alab, "a1")

    def test_mixed_audio_silent_first(self):
        fg, vlab, alab = pcf._build_xfade_filtergraph(
            [4.0, 5.0], 0.5, "dissolve", audio_flags=[False, True])
        self.assertIn("anullsrc=r=48000:cl=stereo,atrim=0:4", fg)          # leg 0 silent, dur 4
        self.assertIn("[1:a]aresample=48000", fg)                          # leg 1 real
        self.assertEqual(alab, "a1")

    def test_mixed_audio_cmd_maps_audio(self):
        captured = {}
        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            m = mock.MagicMock(); m.returncode = 0; return m
        with mock.patch.object(pcf, "_probe_duration", side_effect=[4.0, 5.0]), \
             mock.patch.object(pcf, "_has_audio_stream", side_effect=[True, False]), \
             mock.patch("subprocess.run", side_effect=fake_run):
            pcf.xfade_concat(["a.mp4", "b.mp4"], "out.mp4")
        cmd = captured["cmd"]
        self.assertIn("[a1]", cmd)     # audio stream mapped
        self.assertIn("aac", cmd)      # audio re-encoded
```

Add a new real-ffmpeg integration class at the end of the file (and `import shutil`, `import tempfile` at the top):

```python
@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "ffmpeg/ffprobe not available")
class TestXfadeConcatRealFFmpeg(unittest.TestCase):
    def _make_clip(self, path, dur, with_audio):
        cmd = ["ffmpeg", "-y", "-f", "lavfi",
               "-i", f"testsrc=size=320x240:rate=30:duration={dur}"]
        if with_audio:
            cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}"]
        cmd += ["-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast"]
        if with_audio:
            cmd += ["-c:a", "aac", "-shortest"]
        cmd.append(path)
        subprocess.run(cmd, check=True, capture_output=True)

    def _has_audio(self, path):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True).stdout
        return "audio" in out

    def _audio_duration(self, path):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=duration", "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, check=True).stdout.strip()
        return float(out)

    def test_mixed_audio_runs_and_outputs_audio(self):
        with tempfile.TemporaryDirectory() as d:
            a, b, out = (os.path.join(d, n) for n in ("a.mp4", "b.mp4", "out.mp4"))
            self._make_clip(a, 3, with_audio=True)
            self._make_clip(b, 3, with_audio=False)
            pcf.xfade_concat([a, b], out, duration=0.5)
            self.assertTrue(os.path.exists(out))
            self.assertTrue(self._has_audio(out))   # the M1 fix: audio preserved, not dropped
            # Duration ≈ sum − overlap = 3 + 3 − 0.5 = 5.5s. Guards atrim under-trim
            # (spec §6 test-5 / spec-review R2): a too-short silent pad would shorten
            # the acrossfade — a mock can't see this, presence-only wouldn't catch it.
            self.assertAlmostEqual(self._audio_duration(out), 5.5, delta=0.3)
```

- [ ] **Step 2: Run the tests — verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_xfade_transitions.py -v`
Expected: the 3 mixed mock tests FAIL (no `anullsrc`/`aresample` emitted — mixed is still video-only after Task 1) and `test_mixed_audio_runs_and_outputs_audio` FAILS (`_has_audio(out)` is False — audio dropped).

- [ ] **Step 3: Implement the mixed branch**

In `phase_c_ffmpeg.py::_build_xfade_filtergraph`, replace the audio section so it emits on `any(audio_flags)` and pads when mixed. Full audio block (after the video loop, which no longer builds audio inline):

```python
    n = len(durations)
    if n < 2:
        raise ValueError("xfade filtergraph requires >= 2 inputs")
    if audio_flags is None:
        audio_flags = [True] * n

    emit_audio = any(audio_flags)
    padded = emit_audio and not all(audio_flags)

    t = _fmt(duration)
    video_parts = []
    prev_v = "0:v"
    cumulative = durations[0]
    for j in range(n - 1):
        offset = cumulative - (j + 1) * duration
        vlabel = f"v{j + 1}"
        video_parts.append(
            f"[{prev_v}][{j + 1}:v]xfade=transition={transition}:"
            f"duration={t}:offset={_fmt(offset)}[{vlabel}]"
        )
        prev_v = vlabel
        cumulative += durations[j + 1]

    if not emit_audio:
        return ";".join(video_parts), f"v{n - 1}", None

    # Audio legs. padded (mixed) -> normalize every leg to a canonical format so
    # acrossfade's matching rate/layout/fmt precondition holds across heterogeneous
    # embedded audio + anullsrc silence (Lane V #25 M1). all-audio -> raw [j:a].
    _AFMT = "aformat=sample_fmts=fltp:channel_layouts=stereo"
    leg_parts = []
    if padded:
        audio_src = []
        for j in range(n):
            if audio_flags[j]:
                leg_parts.append(f"[{j}:a]aresample=48000,{_AFMT}[na{j}]")
            else:
                leg_parts.append(
                    f"anullsrc=r=48000:cl=stereo,atrim=0:{_fmt(durations[j])},{_AFMT}[na{j}]"
                )
            audio_src.append(f"na{j}")
    else:
        audio_src = [f"{j}:a" for j in range(n)]

    audio_parts = []
    prev_a = audio_src[0]
    for j in range(n - 1):
        alabel = f"a{j + 1}"
        audio_parts.append(f"[{prev_a}][{audio_src[j + 1]}]acrossfade=d={t}[{alabel}]")
        prev_a = alabel

    filter_complex = ";".join(video_parts + leg_parts + audio_parts)
    return filter_complex, f"v{n - 1}", f"a{n - 1}"
```

Then **replace** the M1 known-limitation comment in `xfade_concat` (the block after `audio_flags = [...]`) with the fixed-state note:

```python
    # Mixed audio-presence (some inputs carry an embedded audio stream, some don't):
    # silent inputs are padded with anullsrc and every leg is normalized to a canonical
    # format, so acrossfade runs uniformly and embedded audio is preserved across the
    # stitch rather than dropped (Lane V #25 M1, fixed 2026-05-29). The downstream
    # _assemble_final dialogue mux is unaffected — it selects its voice source on
    # standalone-dialogue-mp3 existence, not on whether this stitch carries audio.
```

- [ ] **Step 4: Run the tests — verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_xfade_transitions.py -v`
Expected: ALL pass, including `test_mixed_audio_runs_and_outputs_audio` (real ffmpeg confirms the mixed output has an audio stream). If the real-ffmpeg test fails on the `anullsrc`/`atrim` incantation, fix the filter string (spec §4.3 note (a)/(b)) and re-run — this is the gate a mock can't provide.

- [ ] **Step 5: Full-suite + smoke verification**

Run: `.venv/bin/python scripts/ci_smoke.py` → Expected: `OK`.
Run: `.venv/bin/python -m pytest tests/ -q` → Expected: green (no regressions; suite was 1212/5-ish + the doc-tooling tests at branch HEAD — confirm no NEW failures vs. baseline).

- [ ] **Step 6: Commit**

```bash
git add phase_c_ffmpeg.py tests/unit/test_xfade_transitions.py
git commit -m "fix(ffmpeg): close Lane V #25 M1 — anullsrc-pad mixed-audio xfade_concat (preserve embedded audio)"
```

---

## Final verification (after both tasks)

- [ ] `grep -rn "include_audio" phase_c_ffmpeg.py tests/` → no matches (migration complete).
- [ ] `.venv/bin/python -m pytest tests/unit/test_xfade_transitions.py -v` → all pass; real-ffmpeg test ran (not skipped) locally.
- [ ] `.venv/bin/python scripts/ci_smoke.py` → `OK`.
- [ ] `git diff --stat` baseline..HEAD → only `phase_c_ffmpeg.py` + `tests/unit/test_xfade_transitions.py` touched.
- [ ] Acceptance criteria (spec §8) met: mixed → audio preserved; all/none paths unchanged; no `cinema_pipeline.py` change.

**Out of scope (do not implement here):** step-5 binary voice-source limitation; all-audio heterogeneous-format normalization; no-BGM copy-branch dialogue mux (spec §3 non-goals). End-to-end multi-scene render validation remains pod-gated.
