# Scene Transitions MVP Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in cross-dissolve transition at scene→scene boundaries during final video assembly, togglable from the settings UI.

**Architecture:** Two-level stitch (Approach A). When the flag is on, `_assemble_final` concatenates each scene's clips with `-c copy` (hard cuts within a scene, unchanged), then chains the per-scene videos through an FFmpeg `xfade`+`acrossfade` filtergraph (one re-encode). When off, the existing flat `concat -c copy` path is byte-for-byte unchanged. The flag rides the existing `global_settings` open-merge path, so request-parse and frontend-send need zero changes.

**Tech Stack:** Python 3 + FFmpeg (subprocess), pytest (mocked-subprocess unit tests), React/TypeScript + Vite + Tailwind frontend.

**Spec:** `docs/superpowers/specs/2026-05-29-scene-transitions-mvp-design.md`

**Conventions (from `/Users/hyungkoookkim/Content/CLAUDE.md`):**
- Before editing an existing symbol, `grep -rn 'symbol' --include='*.py' .` for callers; Read the call sites; report blast radius.
- After edits, `git diff --stat` to confirm scope.
- Use the project venv for tests: `.venv/bin/python -m pytest ...` (system `python3` lacks deps).
- One commit per task. Conventional commits + `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer.
- Stage files by name (a local hookify rule blocks `git add -A`/`.`).
- Run the §15 smoke (`/.venv/bin/python scripts/ci_smoke.py` → `OK`) before declaring a slice done.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `phase_c_ffmpeg.py` | `_probe_duration`, `_build_xfade_filtergraph` (pure), `xfade_concat` | Create functions |
| `cinema_pipeline.py` | `_assemble_final` ON/OFF branch + per-scene grouping | Modify `:1199` |
| `tests/unit/test_xfade_transitions.py` | Unit tests for the 3 new ffmpeg functions | Create |
| `tests/unit/test_guided_pipeline.py` | `_assemble_final` ON/OFF branching tests | Add tests |
| `web/src/types/project.ts` | `GlobalSettings` type: two new optional keys | Modify |
| `web/src/components/settings/PostProcessingSection.tsx` | "Scene Transitions" checkbox + duration slider | Modify |

---

## Chunk 1: Backend (FFmpeg helpers + assembly wiring)

### Task 1: `_probe_duration` helper

**Files:**
- Modify: `phase_c_ffmpeg.py` (add function near the other ffmpeg helpers)
- Test: `tests/unit/test_xfade_transitions.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_xfade_transitions.py`:

```python
import json
import os
import subprocess
import unittest
from unittest import mock

import phase_c_ffmpeg as pcf


class TestProbeDuration(unittest.TestCase):
    def test_parses_duration_from_ffprobe_json(self):
        payload = json.dumps({"format": {"duration": "4.25"}})

        def fake_run(cmd, **kwargs):
            self.assertIn("ffprobe", cmd[0])
            self.assertIn("format=duration", cmd)
            m = mock.MagicMock()
            m.stdout = payload
            m.returncode = 0
            return m

        with mock.patch("subprocess.run", side_effect=fake_run):
            assert pcf._probe_duration("/fake/clip.mp4") == 4.25
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_xfade_transitions.py::TestProbeDuration -v`
Expected: FAIL — `AttributeError: module 'phase_c_ffmpeg' has no attribute '_probe_duration'`

- [ ] **Step 3: Write minimal implementation**

Add to `phase_c_ffmpeg.py` (mirrors the clean `ffprobe` pattern at `lip_sync.py:99`):

```python
def _probe_duration(path: str) -> float:
    """Return the duration of a media file in seconds via ffprobe."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True, timeout=30,
    )
    return float(json.loads(probe.stdout)["format"]["duration"])
```

Ensure `import json` and `import subprocess` are present at the top of `phase_c_ffmpeg.py` (grep first: `grep -n '^import json\|^import subprocess' phase_c_ffmpeg.py` — add only if missing).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_xfade_transitions.py::TestProbeDuration -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add phase_c_ffmpeg.py tests/unit/test_xfade_transitions.py
git commit -m "$(cat <<'EOF'
feat(ffmpeg): add _probe_duration ffprobe helper for scene transitions

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `_build_xfade_filtergraph` (pure filtergraph builder)

This isolates the tricky offset math into a pure, side-effect-free function so it can be unit-tested by exact-string assertion.

**Offset math (precise — do not drift):** For ordered scene durations `d[0..N-1]` (N≥2) and uniform transition `t`, the chain joins the running video with one scene at a time. **Junction `j` (0-indexed, `j = 0..N-2`) joins the accumulated video `[clips 0..j]` with clip `j+1`:**

```
offset(j) = (Σ d[0..j]) − (j+1)·t
```

Worked example, durations `[4.0, 5.0, 6.0]`, `t = 0.5`:
- junction 0: `4.0 − 1·0.5 = 3.5`
- junction 1: `(4.0+5.0) − 2·0.5 = 8.0`

Video labels chain `[v1]`, `[v2]`, …; audio uses `acrossfade` (no offset needed). Final maps are the last video label and last audio label.

**Files:**
- Modify: `phase_c_ffmpeg.py`
- Test: `tests/unit/test_xfade_transitions.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_xfade_transitions.py`:

```python
class TestBuildXfadeFiltergraph(unittest.TestCase):
    def test_two_scenes(self):
        fg, vlab, alab = pcf._build_xfade_filtergraph([4.0, 5.0], 0.5, "dissolve")
        assert vlab == "v1"
        assert alab == "a1"
        assert fg == (
            "[0:v][1:v]xfade=transition=dissolve:duration=0.5:offset=3.5[v1];"
            "[0:a][1:a]acrossfade=d=0.5[a1]"
        )

    def test_three_scenes_chains_offsets(self):
        fg, vlab, alab = pcf._build_xfade_filtergraph([4.0, 5.0, 6.0], 0.5, "dissolve")
        assert vlab == "v2"
        assert alab == "a2"
        assert fg == (
            "[0:v][1:v]xfade=transition=dissolve:duration=0.5:offset=3.5[v1];"
            "[v1][2:v]xfade=transition=dissolve:duration=0.5:offset=8[v2];"
            "[0:a][1:a]acrossfade=d=0.5[a1];"
            "[a1][2:a]acrossfade=d=0.5[a2]"
        )
```

Note on number formatting: offsets are emitted with trailing-zero/`.0` stripped (`3.5`, `8` not `8.0`) — see the `_fmt` helper below. The tests above pin this exactly.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_xfade_transitions.py::TestBuildXfadeFiltergraph -v`
Expected: FAIL — `AttributeError: ... no attribute '_build_xfade_filtergraph'`

- [ ] **Step 3: Write minimal implementation**

Add to `phase_c_ffmpeg.py`:

```python
def _fmt(x: float) -> str:
    """Format a float for an ffmpeg filter arg: strip trailing zeros (8.0 -> '8', 3.5 -> '3.5')."""
    return f"{x:.6f}".rstrip("0").rstrip(".")


def _build_xfade_filtergraph(durations: list, duration: float, transition: str):
    """Build a chained xfade (video) + acrossfade (audio) filter_complex string.

    Returns (filter_complex, final_video_label, final_audio_label).
    Requires len(durations) >= 2. Offset for junction j is
    sum(durations[0..j]) - (j+1)*duration.
    """
    n = len(durations)
    if n < 2:
        raise ValueError("xfade filtergraph requires >= 2 inputs")

    t = _fmt(duration)
    video_parts = []
    audio_parts = []
    prev_v = "0:v"
    prev_a = "0:a"
    cumulative = durations[0]
    for j in range(n - 1):
        offset = cumulative - (j + 1) * duration
        vlabel = f"v{j + 1}"
        alabel = f"a{j + 1}"
        video_parts.append(
            f"[{prev_v}][{j + 1}:v]xfade=transition={transition}:"
            f"duration={t}:offset={_fmt(offset)}[{vlabel}]"
        )
        audio_parts.append(f"[{prev_a}][{j + 1}:a]acrossfade=d={t}[{alabel}]")
        prev_v = vlabel
        prev_a = alabel
        if j + 1 < n:
            cumulative += durations[j + 1]

    filter_complex = ";".join(video_parts + audio_parts)
    return filter_complex, f"v{n - 1}", f"a{n - 1}"
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_xfade_transitions.py::TestBuildXfadeFiltergraph -v`
Expected: PASS (both cases)

- [ ] **Step 5: Commit**

```bash
git add phase_c_ffmpeg.py tests/unit/test_xfade_transitions.py
git commit -m "$(cat <<'EOF'
feat(ffmpeg): add _build_xfade_filtergraph pure builder with chained offsets

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `xfade_concat` orchestrator

Probes scene durations, clamps the transition to fit the shortest scene, builds the filtergraph, runs the single re-encode.

**Transition clamp (MVP simplification):** Use a single global `t_eff = min(duration, 0.4 * min(durations))` so the offset math stays uniform-`t` (per-junction variable `t` is out of scope). This guarantees every junction's transition is shorter than its scenes.

**Files:**
- Modify: `phase_c_ffmpeg.py`
- Test: `tests/unit/test_xfade_transitions.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_xfade_transitions.py`:

```python
class TestXfadeConcat(unittest.TestCase):
    def _run(self, scene_videos, durations, duration=0.5):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            m = mock.MagicMock()
            m.returncode = 0
            return m

        with mock.patch.object(pcf, "_probe_duration", side_effect=durations), \
             mock.patch("subprocess.run", side_effect=fake_run):
            out = pcf.xfade_concat(scene_videos, "/out/final.mp4", duration=duration)
        return out, captured["cmd"]

    def test_builds_ffmpeg_cmd_with_inputs_filter_and_maps(self):
        out, cmd = self._run(["/s0.mp4", "/s1.mp4"], durations=[4.0, 5.0])
        assert out == "/out/final.mp4"
        # Two -i inputs in order
        i_positions = [k for k, a in enumerate(cmd) if a == "-i"]
        assert [cmd[k + 1] for k in i_positions] == ["/s0.mp4", "/s1.mp4"]
        joined = " ".join(cmd)
        assert "-filter_complex" in cmd
        assert "xfade=transition=dissolve:duration=0.5:offset=3.5" in joined
        assert "acrossfade=d=0.5" in joined
        assert "-map [v1]" in joined
        assert "-map [a1]" in joined

    def test_clamps_transition_to_shortest_scene(self):
        # Shortest scene is 0.5s -> t_eff = min(0.5, 0.4*0.5) = 0.2
        out, cmd = self._run(["/s0.mp4", "/s1.mp4"], durations=[0.5, 5.0], duration=0.5)
        joined = " ".join(cmd)
        assert "duration=0.2" in joined
        assert "acrossfade=d=0.2" in joined
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_xfade_transitions.py::TestXfadeConcat -v`
Expected: FAIL — `AttributeError: ... no attribute 'xfade_concat'`

- [ ] **Step 3: Write minimal implementation**

Add to `phase_c_ffmpeg.py`:

```python
def xfade_concat(scene_videos: list, out_path: str,
                 duration: float = 0.5, transition: str = "dissolve") -> str:
    """Chain per-scene videos with xfade (video) + acrossfade (audio).

    Probes each scene's duration, clamps the transition to fit the shortest
    scene, builds the filtergraph, and re-encodes once to out_path.
    Requires len(scene_videos) >= 2 (caller guarantees). Returns out_path.
    Raises on ffmpeg failure (caller falls back to a plain concat).
    """
    durations = [_probe_duration(v) for v in scene_videos]
    t_eff = min(duration, 0.4 * min(durations))
    filter_complex, vlab, alab = _build_xfade_filtergraph(durations, t_eff, transition)

    cmd = ["ffmpeg", "-y"]
    for v in scene_videos:
        cmd += ["-i", v]
    cmd += [
        "-filter_complex", filter_complex,
        "-map", f"[{vlab}]", "-map", f"[{alab}]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    return out_path
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_xfade_transitions.py -v`
Expected: PASS (all classes)

- [ ] **Step 5: Commit**

```bash
git add phase_c_ffmpeg.py tests/unit/test_xfade_transitions.py
git commit -m "$(cat <<'EOF'
feat(ffmpeg): add xfade_concat orchestrator (probe + clamp + re-encode)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Wire `_assemble_final` ON/OFF branch

**Blast-radius check first:** `grep -rn '_assemble_final' --include='*.py' .` — confirm callers (the live one is `cinema_pipeline.py:770`; `web_server.py` re-assemble mirrors the path; tests in `test_guided_pipeline.py` + `test_reassemble_endpoint.py`). The change is additive (new branch); OFF path unchanged, so existing callers are unaffected.

**Design:** Read `cinema_pipeline.py:1199` (`_assemble_final`). Current flow: collect flat `all_clips` (`:1211-1226`) → normalize each → `all_normalized` (`:1237-1259`) → `concat -c copy` → `stitched` (`:1261-1285`). Change:
1. While collecting, also record `scene_sizes` (clip count per scene) so the flat `all_normalized` can be regrouped by scene.
2. Read flags at the top of the method: `scene_transitions = settings.get("scene_transitions", False)`, `transition_duration = float(settings.get("transition_duration", 0.5))`.
3. At the stitch step, branch:
   - **OFF (or <2 scenes with clips, or xfade error):** existing flat concat (unchanged).
   - **ON:** split `all_normalized` by `scene_sizes` → per-scene `concat -c copy` → `scene_videos` → `xfade_concat(scene_videos, stitched, transition_duration)`.

**Files:**
- Modify: `cinema_pipeline.py:1199` (`_assemble_final`)
- Test: `tests/unit/test_guided_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_guided_pipeline.py` (mirror the existing `fake_run` harness used in `TestAssembleFinalFoleyMix`, `:381-411`):

```python
# Inherit from TestAssembleFinalFoleyMix (not GuidedPipelineTestCase) to reuse
# its `_make_pipeline_with_clips` helper.
class TestAssembleFinalSceneTransitions(TestAssembleFinalFoleyMix):
    def _run(self, settings, n_scenes):
        pipeline, _, _ = self._make_pipeline_with_clips(None, foley_paths=[])
        os.makedirs(pipeline.temp_dir, exist_ok=True)
        os.makedirs(pipeline.export_dir, exist_ok=True)
        fake_bgm = os.path.join(pipeline.temp_dir, "bgm.mp3")
        open(fake_bgm, "wb").close()
        scene_data = []
        for si in range(n_scenes):
            clip = os.path.join(pipeline.temp_dir, f"clip_{si}.mp4")
            open(clip, "wb").close()
            scene_data.append({"scene_id": f"s{si}", "clips": [clip]})

        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(list(cmd))
            for arg in cmd:
                if str(arg).endswith(".mp4"):
                    open(arg, "wb").close()
            m = mock.MagicMock(); m.returncode = 0; m.stdout = '{"format":{"duration":"4.0"}}'
            return m

        with mock.patch("subprocess.run", side_effect=fake_run), \
             mock.patch.object(pipeline, "_apply_final_loudnorm"):
            pipeline._assemble_final(scene_data, fake_bgm, settings)
        return captured

    def test_off_uses_concat_demuxer_no_xfade(self):
        cmds = self._run({"scene_transitions": False}, n_scenes=2)
        joined = [" ".join(str(a) for a in c) for c in cmds]
        assert any("-f concat" in j or "concat" in j for j in joined)
        assert not any("xfade" in j for j in joined), "OFF must not emit xfade"

    def test_default_is_off(self):
        cmds = self._run({}, n_scenes=2)
        assert not any("xfade" in " ".join(str(a) for a in c) for c in cmds)

    def test_on_with_two_scenes_emits_xfade(self):
        cmds = self._run({"scene_transitions": True}, n_scenes=2)
        assert any("xfade" in " ".join(str(a) for a in c) for c in cmds), \
            "ON with >=2 scenes must emit an xfade command"

    def test_on_with_single_scene_falls_back_to_concat(self):
        cmds = self._run({"scene_transitions": True}, n_scenes=1)
        assert not any("xfade" in " ".join(str(a) for a in c) for c in cmds), \
            "ON with 1 scene cannot xfade -> fall back to concat"

    def test_on_xfade_raises_falls_back_to_concat(self):
        # If xfade_concat raises mid-assembly, the ON path must fall back to a
        # plain concat and still return a path (spec test 5 — the only otherwise
        # untested branch). xfade_concat is imported locally inside _assemble_final,
        # so patching it on the module is picked up at call time.
        pipeline, _, _ = self._make_pipeline_with_clips(None, foley_paths=[])
        os.makedirs(pipeline.temp_dir, exist_ok=True)
        os.makedirs(pipeline.export_dir, exist_ok=True)
        fake_bgm = os.path.join(pipeline.temp_dir, "bgm.mp3")
        open(fake_bgm, "wb").close()
        scene_data = []
        for si in range(2):
            clip = os.path.join(pipeline.temp_dir, f"clip_{si}.mp4")
            open(clip, "wb").close()
            scene_data.append({"scene_id": f"s{si}", "clips": [clip]})

        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(list(cmd))
            for arg in cmd:
                if str(arg).endswith(".mp4"):
                    open(arg, "wb").close()
            m = mock.MagicMock(); m.returncode = 0; m.stdout = '{"format":{"duration":"4.0"}}'
            return m

        with mock.patch("subprocess.run", side_effect=fake_run), \
             mock.patch("phase_c_ffmpeg.xfade_concat", side_effect=RuntimeError("boom")), \
             mock.patch.object(pipeline, "_apply_final_loudnorm"):
            result = pipeline._assemble_final(scene_data, fake_bgm, {"scene_transitions": True})

        joined = [" ".join(str(a) for a in c) for c in captured]
        assert any("concat" in j for j in joined), "fallback must use the concat demuxer"
        assert result is not None, "assembly must still return a path after fallback"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_guided_pipeline.py::TestAssembleFinalSceneTransitions -v`
Expected: FAIL — `test_on_with_two_scenes_emits_xfade` fails (no xfade emitted yet); OFF tests may already pass.

- [ ] **Step 3: Write minimal implementation**

In `cinema_pipeline.py` `_assemble_final`:

(a) After the method's docstring / `final_output = ...` line, read the flags:

```python
scene_transitions = settings.get("scene_transitions", False)
transition_duration = float(settings.get("transition_duration", 0.5))
```

(b) In the clip-collection loop (`:1213-1226`), track per-scene clip counts. Replace the flat append with grouping that still yields `all_clips` in order:

```python
all_clips = []
scene_sizes = []  # number of valid clips per scene, in order
for si, sd in enumerate(scene_data):
    scene_id = sd.get("scene_id", f"scene_{si}")
    clips = sd.get("clips", [])
    count = 0
    for clip_path in clips:
        if clip_path and os.path.exists(clip_path):
            all_clips.append(clip_path)
            count += 1
            logger.debug("Assembly clip queued", extra={"scene_index": si, "scene_id": scene_id, "clip": os.path.basename(clip_path)})
    if count:
        scene_sizes.append(count)
```

(The normalize loop `:1237-1259` is unchanged — it iterates `all_clips` and produces `all_normalized` in the same order.)

(c) Replace the stitch step (`:1261-1285`) with a branch. Extract the existing concat into an inner helper so OFF, per-scene concat, and fallback all share it:

```python
def _concat_copy(clip_paths, dest, tag):
    list_path = os.path.join(self.temp_dir, f"concat_list_{tag}.txt")
    with open(list_path, "w") as f:
        for clip in clip_paths:
            f.write(f"file '{os.path.abspath(clip)}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", dest],
        check=True, capture_output=True, timeout=120,
    )
    return dest

stitched = os.path.join(self.temp_dir, "stitched.mp4")
use_transitions = scene_transitions and len(scene_sizes) >= 2

if use_transitions:
    try:
        from phase_c_ffmpeg import xfade_concat
        # regroup normalized clips by scene, concat each scene, then xfade-chain
        scene_videos = []
        idx = 0
        for si, size in enumerate(scene_sizes):
            group = all_normalized[idx:idx + size]
            idx += size
            scene_mp4 = os.path.join(self.temp_dir, f"scene_{si}.mp4")
            _concat_copy(group, scene_mp4, f"scene_{si}")
            scene_videos.append(scene_mp4)
        xfade_concat(scene_videos, stitched, duration=transition_duration)
        logger.info("Stitched clips with scene transitions", extra={"scene_count": len(scene_videos)})
    except Exception:
        logger.exception("Scene-transition stitch failed; falling back to hard-cut concat")
        try:
            _concat_copy(all_normalized, stitched, "all")
        except Exception:
            logger.exception("Stitch failed")
            return None
else:
    try:
        _concat_copy(all_normalized, stitched, "all")
        logger.info("Stitched clips", extra={"clip_count": len(all_normalized), "stitched_path": stitched})
    except Exception:
        logger.exception("Stitch failed")
        return None
```

Preserve everything from step 4 (color grade) onward exactly as-is.

- [ ] **Step 4: Run the new tests + the existing `_assemble_final` tests (regression)**

Run: `.venv/bin/python -m pytest tests/unit/test_guided_pipeline.py -v`
Expected: PASS — the new `TestAssembleFinalSceneTransitions` cases (off / default-off / on-2-scenes / single-scene-fallback / xfade-raises-fallback) AND the existing `TestAssembleFinalFoleyMix` amix tests still pass (the mix step is structurally unchanged).

- [ ] **Step 5: Run the §15 smoke + full unit suite**

Run: `.venv/bin/python scripts/ci_smoke.py` → Expected: `OK`
Run: `.venv/bin/python -m pytest tests/ -q` → Expected: the prior baseline (1129 passed / 5 skipped at branch start) plus the new tests, with no new failures.

- [ ] **Step 6: Commit**

```bash
git add cinema_pipeline.py tests/unit/test_guided_pipeline.py
git commit -m "$(cat <<'EOF'
feat(assembly): opt-in scene-boundary transitions in _assemble_final

Off by default (flat concat -c copy path unchanged). When
global_settings.scene_transitions is on and there are >=2 scenes with clips,
per-scene concat then xfade_concat across the scene videos; any failure or
<2 scenes falls back to the hard-cut concat.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Chunk 2: Frontend (settings type + toggle UI)

> The flag persists via the existing `global_settings` open-merge (`web_server.py:507`) and the universal `update()` sender in `SettingsPanel.tsx` — **no backend or sender changes**. Only the type and the toggle component change.

### Task 5: Add `GlobalSettings` type keys

**Files:**
- Modify: `web/src/types/project.ts`

- [ ] **Step 1: Locate the `GlobalSettings` interface**

Run: `grep -n 'coherence_check_enabled\|interface GlobalSettings' web/src/types/project.ts`
Read the surrounding interface to match style (optional booleans/numbers with `?`).

- [ ] **Step 2: Add the two keys**

Inside the `GlobalSettings` interface, near the other post-processing toggles, add:

```typescript
  scene_transitions?: boolean
  transition_duration?: number
```

- [ ] **Step 3: Type-check**

Run: `cd web && npx tsc --noEmit`
Expected: no new type errors.

- [ ] **Step 4: Commit**

```bash
git add web/src/types/project.ts
git commit -m "$(cat <<'EOF'
feat(web-types): add scene_transitions + transition_duration to GlobalSettings

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: "Scene Transitions" checkbox + duration slider

**Files:**
- Modify: `web/src/components/settings/PostProcessingSection.tsx`

- [ ] **Step 1: Read the mirror pattern**

Run: `grep -n 'coherence_check_enabled\|Slider\|update(' web/src/components/settings/PostProcessingSection.tsx`
Read the `coherence_check_enabled` checkbox block and the existing `Slider` usage. Match their exact markup, class names, and the `update('<key>', value)` call convention (do NOT invent new styling — copy the existing toggle's classes verbatim).

- [ ] **Step 2: Add the checkbox + conditional slider**

Mirror the `coherence_check_enabled` checkbox for `scene_transitions` (label "Scene Transitions", a one-line description like "Cross-dissolve between scenes (re-encodes on assembly)"). Below it, render the existing `Slider` for `transition_duration` **only when `s.scene_transitions` is truthy**, mirroring how an existing conditional control is gated. Slider range `0.2`–`2.0`, step `0.1`, default `0.5`, label "Transition duration (s)". Use the existing `update(...)` handler for both — no new fetch logic.

- [ ] **Step 3: Type-check + build**

Run: `cd web && npx tsc --noEmit` → Expected: clean.
Run: `cd web && npm run build` → Expected: build succeeds.

- [ ] **Step 4: Manual UI verification (REQUIRED — type-check is not feature-check)**

Start the dev server (`cd web && npm run dev`), open the settings panel for a project, and confirm:
- The "Scene Transitions" checkbox renders in the Post-Processing section and toggles.
- The duration slider appears only when the checkbox is on, and hides when off.
- Toggling fires a `PUT /api/projects/<pid>` (check the network tab) carrying `global_settings.scene_transitions` / `transition_duration`.
- Reload the page — the values persist (confirms the open-merge round-trip).

If the dev server cannot be run in this environment, state that explicitly rather than claiming the UI works.

- [ ] **Step 5: Commit**

```bash
git add web/src/components/settings/PostProcessingSection.tsx
git commit -m "$(cat <<'EOF'
feat(web): add Scene Transitions toggle + duration slider to settings

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification (after all tasks)

- [ ] `.venv/bin/python scripts/ci_smoke.py` → `OK`
- [ ] `.venv/bin/python -m pytest tests/ -q` → no new failures (baseline 1129/5 + new tests)
- [ ] `cd web && npx tsc --noEmit` → clean
- [ ] `git diff --stat <baseline>..HEAD` → only the 6 files in the File Structure table touched
- [ ] End-to-end manual check (if a pod/render is available): enable the flag on a multi-scene project, run assembly, confirm the final video cross-dissolves at scene boundaries and hard-cuts within scenes. (Pod is currently DOWN — this gate is deferred until a render is runnable.)

## Out of scope (do not implement)

- Mood-mapped transition styles (v2).
- Deleting the unused `_build_transition_prompt` (separate decision).
- Transitions on the shot-preview path (`stitch_modules`).
- Per-junction variable transition durations (global clamp only).
