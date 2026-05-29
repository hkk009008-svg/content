# Veo Native Config-Threading Fix Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `veo_native.generate_video()` actually pass its caller's params (`generate_audio`, `duration`, `resolution`, `reference_images`, driving video) to the Veo API — fixing a `reference_images` TypeError that fails every character shot plus a silent-audio drop — via a pure, offline-testable config builder.

**Architecture:** Extract param→`GenerateVideosConfig` mapping into a pure `_build_generate_videos_config()` helper (no I/O → unit-testable with no Vertex/spend). `generate_video()` loads images, calls the builder, and invokes `generate_videos(model, prompt, image, video=<driving>, config=cfg)` — moving `reference_images` *into* the config (wrapped) and the driving video to the top-level `video=` param, instead of passing them as kwargs the SDK rejects.

**Tech Stack:** Python 3.13, `google-genai 2.6.0` (`types.GenerateVideosConfig`, `types.VideoGenerationReferenceImage`, `types.Video`, `types.Image`), pytest (offline, `unittest.mock`).

**Spec:** `docs/superpowers/specs/2026-05-29-veo-native-config-threading-design.md`.

---

## Decisions / context

- **Three bugs, one root cause** (spec §1): `generate_video` builds `GenerateVideosConfig(person_generation, aspect_ratio)` only, passes `reference_images`/`reference_video` as **top-level kwargs** (SDK `generate_videos` rejects them → TypeError → `None` → cascade; with `VEO_NATIVE`-only there's no fallback → shot fails), and never sets `generate_audio`/`duration`/`resolution`.
- **`reference_images` needs wrapping (grounded 2026-05-29):** `config.reference_images: Optional[list[VideoGenerationReferenceImage]]` — raw `types.Image` is the wrong type. Each loaded `Image` must be wrapped in `types.VideoGenerationReferenceImage(image=img, reference_type=<verify>)`.
- **Validation split (Rule #16 convergence):** offline unit tests are THIS plan's deliverable. The live E2E is the operator's `scripts/run_veo_dialogue_test.py` (do not re-create it). After the fix, that script's run is the live acceptance.
- **Coordination + sequencing:** `veo_native.py` is the operator's active file (`39d095e` + their running test). **Land this fix AFTER the operator's `run_veo_dialogue_test.py` run exits** — its failure output is the live confirmation that pins the unit-test expectations, and landing mid-run would collide. The implementer MUST `git log -1 -- veo_native.py` + re-read the function before editing (per CLAUDE.md impact-analysis).
- **Build deferred:** plan only; do not execute until the user says go.

### Verified source + SDK facts (2026-05-29, `google-genai 2.6.0`)

| Fact | Evidence |
|---|---|
| `GenerateVideosConfig` fields + types: `generate_audio: Optional[bool]`, `duration_seconds: Optional[int]`, `resolution: Optional[str]`, `reference_images: Optional[list[VideoGenerationReferenceImage]]` | `.venv/bin/python` introspection of `types.GenerateVideosConfig.model_fields` |
| `types.VideoGenerationReferenceImage` exists; `types.Video` exists | introspection (`hasattr`) |
| `Models.generate_videos(self, model, prompt, image, video, source, config)` — no top-level `reference_images`/`reference_video` | `inspect.signature` |
| Config built with only `person_generation`+`aspect_ratio` | `veo_native.py:103-106` |
| `reference_images` → top-level `generate_kwargs` | `veo_native.py:117-126` |
| `reference_video` → top-level `generate_kwargs`, with `types.Video`/AttributeError guard | `veo_native.py:128-144` |
| `generate_audio` accepted+logged, never set | `veo_native.py:65`, `:96` |
| call site | `veo_native.py:147` |
| `VEO_DURATIONS = ["5s","6s","8s"]` | `veo_native.py:21` |
| caller passes `reference_images=multi_angle_refs`, `generate_audio=(… or has_dialogue)`, `driving_video_path=` | `phase_c_ffmpeg.py:280-282` |

### Build-time SDK-verify gates (REQUIRED before pinning code)

Run these once at execution; adjust the sketches below to match:
1. `types.VideoGenerationReferenceImage` constructor — exact required fields + `reference_type` enum values (e.g. is it `"asset"`/`"style"`, an enum, or optional?). Pick the value meaning "preserve this subject" for character refs.
2. Confirm `config.resolution` accepts `"720p"`/`"1080p"` verbatim (type is `str`; confirm format).
3. Confirm the driving/motion-reference clip belongs on the top-level `video=` param (vs `source=`); keep the skip-on-error guard so an unsupported field can't break the call.

---

## File Structure

- `veo_native.py` — add `_parse_duration_seconds()` + `_build_generate_videos_config()` (module-level, pure); rewire `generate_video()`'s config build + call. One responsibility: native Veo client.
- `tests/unit/test_veo_native_config.py` (new) — offline unit tests for the helpers + the call-site contract (mocked client). One responsibility: veo config-threading correctness.
- Doc-sync: `ARCHITECTURE.md` Veo/native-audio section, only if it asserts the (broken) current behavior.

---

## Chunk 1: pure config builder + rewire

### Task 1: `_parse_duration_seconds()` helper

**Files:**
- Modify: `veo_native.py` (module-level, near `VEO_DURATIONS`)
- Test: `tests/unit/test_veo_native_config.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_veo_native_config.py
from veo_native import _parse_duration_seconds


def test_parses_normal_duration():
    assert _parse_duration_seconds("8s") == 8
    assert _parse_duration_seconds("5s") == 5


def test_malformed_duration_defaults_to_8():
    # A formatting edge must not fail the whole generation (spec §4.1 contract).
    assert _parse_duration_seconds("8") == 8        # missing 's'
    assert _parse_duration_seconds("") == 8
    assert _parse_duration_seconds(None) == 8
    assert _parse_duration_seconds("garbage") == 8
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_veo_native_config.py -k duration -v`
Expected: FAIL — `_parse_duration_seconds` not defined.

- [ ] **Step 3: Implement**

```python
# veo_native.py (module level)
def _parse_duration_seconds(duration, default: int = 8) -> int:
    """'8s' -> 8. Returns `default` on any malformed input (a formatting edge
    must not fail generation)."""
    try:
        return int(str(duration).strip().lower().rstrip("s"))
    except (ValueError, TypeError, AttributeError):
        return default
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_veo_native_config.py -k duration -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add veo_native.py tests/unit/test_veo_native_config.py
git commit -m "feat(veo): _parse_duration_seconds helper (malformed -> default 8)"
```

---

### Task 2: `_build_generate_videos_config()` pure builder

**Files:**
- Modify: `veo_native.py`
- Test: `tests/unit/test_veo_native_config.py`

> **Do the build-time gate #1 + #2 first** (VideoGenerationReferenceImage fields + resolution format). Adjust the wrapper call below to the confirmed constructor.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/unit/test_veo_native_config.py
from google.genai import types
from veo_native import _build_generate_videos_config


def test_builds_config_with_all_caller_params():
    cfg = _build_generate_videos_config(
        generate_audio=True, duration="8s", resolution="720p", reference_images=None)
    assert cfg.generate_audio is True
    assert cfg.duration_seconds == 8
    assert cfg.resolution == "720p"
    assert cfg.person_generation == "allow_adult"
    assert cfg.aspect_ratio == "16:9"
    assert not cfg.reference_images  # None/empty when no refs


def test_wraps_reference_images_into_config():
    # Refs must land in config.reference_images as VideoGenerationReferenceImage,
    # NOT as raw Image and NOT top-level (the TypeError bug).
    img = types.Image(gcs_uri="gs://x/y.png")  # construct per the gate; adjust if needed
    cfg = _build_generate_videos_config(
        generate_audio=False, duration="5s", resolution="720p", reference_images=[img])
    assert cfg.reference_images is not None and len(cfg.reference_images) == 1
    assert isinstance(cfg.reference_images[0], types.VideoGenerationReferenceImage)
```

> If `types.Image(gcs_uri=...)` isn't constructible offline, build the `Image` per gate #1's findings (e.g. a tiny temp file via `types.Image.from_file`) — keep the assertion on the wrapper type.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_veo_native_config.py -k build -v`
Expected: FAIL — `_build_generate_videos_config` not defined.

- [ ] **Step 3: Implement**

```python
# veo_native.py (module level)
def _build_generate_videos_config(
    *, generate_audio: bool, duration: str, resolution: str,
    reference_images=None, person_generation: str = "allow_adult",
    aspect_ratio: str = "16:9",
):
    """Pure: map generate_video() params -> GenerateVideosConfig. No I/O.
    `reference_images` is a list of already-loaded types.Image (or None);
    each is wrapped in VideoGenerationReferenceImage (the config's required type)."""
    kwargs = dict(
        person_generation=person_generation,
        aspect_ratio=aspect_ratio,
        generate_audio=generate_audio,
        duration_seconds=_parse_duration_seconds(duration),
        resolution=resolution,
    )
    if reference_images:
        kwargs["reference_images"] = [
            types.VideoGenerationReferenceImage(image=img)  # add reference_type per gate #1
            for img in reference_images
        ]
    return types.GenerateVideosConfig(**kwargs)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_veo_native_config.py -k build -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add veo_native.py tests/unit/test_veo_native_config.py
git commit -m "feat(veo): _build_generate_videos_config — thread audio/duration/resolution/refs into config"
```

---

### Task 3: Rewire `generate_video()` to use the builder + `video=`

> **Highest-risk step.** `git log -1 -- veo_native.py` and re-read `generate_video` (lines ~95-147) first; the operator may have changed it. Land AFTER the operator's `run_veo_dialogue_test.py` run exits (Decisions/sequencing). Preserve the outer `try/except`→`None` contract, the `[:3]` ref cap + existence checks, and the driving-video SDK-version guard.

**Files:**
- Modify: `veo_native.py:95-147` (the config build + call inside `generate_video`)
- Test: `tests/unit/test_veo_native_config.py` (call-site contract, mocked client)

- [ ] **Step 1: Write the failing test (the TypeError-regression guard)**

```python
# add to tests/unit/test_veo_native_config.py
import os, tempfile
from unittest.mock import MagicMock, patch
from veo_native import VeoNativeAPI


def _png():
    # minimal real file so os.path.exists + Image.from_file paths are exercised
    import struct, zlib
    fd, p = tempfile.mkstemp(suffix=".png"); os.close(fd)
    # tiny 1x1 png
    raw = (b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + struct.pack(">IIBBBBB",1,1,8,2,0,0,0)
           )  # header only is enough for from_file? if not, write a real 1x1 via PIL
    with open(p,"wb") as f: f.write(raw)
    return p


def test_generate_video_passes_config_not_toplevel_kwargs():
    api = VeoNativeAPI.__new__(VeoNativeAPI)        # bypass __init__ (no real client)
    api._model = "veo-3.1-generate-001"
    captured = {}
    fake_models = MagicMock()
    def _gen(**kw):
        captured.update(kw)
        op = MagicMock(); op.done = True
        op.response.generated_videos = [MagicMock()]
        return op
    fake_models.generate_videos.side_effect = _gen
    api.client = MagicMock(models=fake_models)
    api.client.operations.get.side_effect = lambda o: o
    api.client.files.download.return_value = b"x"

    img = _png()
    with patch("os.path.exists", return_value=True), \
         patch("os.path.getsize", return_value=10), \
         patch("builtins.open", MagicMock()):
        api.generate_video(image_path=img, prompt="hi", output_path="/tmp/o.mp4",
                           reference_images=[img], generate_audio=True, duration="8s")

    # The regression: NO illegal top-level kwargs
    assert "reference_images" not in captured
    assert "reference_video" not in captured
    # Audio + refs went via the config
    cfg = captured["config"]
    assert cfg.generate_audio is True
    assert cfg.reference_images and len(cfg.reference_images) == 1
```

> This test is fiddly (it exercises the live-call path with a mock). If the PNG/`from_file`/download mocking proves brittle, simplify to asserting on the `generate_kwargs` dict by extracting the call-assembly into a tiny seam — but keep the two core assertions: (a) no top-level `reference_images`/`reference_video`, (b) `config.generate_audio` set. Coordinate the seam with the operator if it changes `generate_video`'s shape.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_veo_native_config.py -k passes_config -v`
Expected: FAIL — current code passes `reference_images` top-level (TypeError or the assertion fails).

- [ ] **Step 3: Rewire the function**

Replace the config-build + ref/driving-video kwarg block (`veo_native.py:103-144`) with:

```python
            start_image = types.Image.from_file(location=image_path)

            # Load reference images (I/O here); the builder wraps + places them in config.
            ref_images = []
            if reference_images:
                for ref_path in reference_images[:3]:
                    if os.path.exists(ref_path):
                        ref_images.append(types.Image.from_file(location=ref_path))
                        print(f"[VEO-NATIVE] Reference image loaded: {os.path.basename(ref_path)}")
                    else:
                        print(f"[VEO-NATIVE] Reference image not found, skipping: {ref_path}")

            config = _build_generate_videos_config(
                generate_audio=generate_audio,
                duration=duration,
                resolution=resolution,
                reference_images=ref_images or None,
            )

            generate_kwargs = {
                "model": self._model,
                "prompt": prompt,
                "image": start_image,
                "config": config,
            }

            # Driving video -> top-level `video=` (NOT a kwarg the SDK rejects).
            # Preserve SDK-version robustness: skip silently if types.Video is absent.
            if driving_video_path and os.path.exists(driving_video_path):
                try:
                    generate_kwargs["video"] = types.Video.from_file(location=driving_video_path)
                    print(f"[VEO-NATIVE] Driving video loaded: {os.path.basename(driving_video_path)}")
                except AttributeError:
                    print("[VEO-NATIVE] reference_video not supported by installed SDK; image-only path")
                except Exception as _e:
                    print(f"[VEO-NATIVE] driving_video load failed ({_e}); image-only path")
```

(The `generate_videos(**generate_kwargs)` call at the old `:147` is unchanged; poll/RAI/download below it unchanged.)

- [ ] **Step 4: Run to verify it passes + full file**

Run: `.venv/bin/python -m pytest tests/unit/test_veo_native_config.py -v`
Expected: PASS (all)
Run: `.venv/bin/python scripts/ci_smoke.py`
Expected: `OK` / exit 0 (veo_native imports cleanly)

- [ ] **Step 5: Commit**

```bash
git add veo_native.py tests/unit/test_veo_native_config.py
git commit -m "fix(veo): thread params into GenerateVideosConfig + driving video via video= (kills reference_images TypeError + silent audio)"
```

---

### Task 4: Doc-sync

**Files:**
- Modify: `ARCHITECTURE.md` (Veo/native-audio section — only if it asserts current/broken behavior)

- [ ] **Step 1: Locate**

Run: `grep -n "VEO_NATIVE\|veo_native\|native audio\|generate_audio" ARCHITECTURE.md | head`

- [ ] **Step 2: Update**

If a section describes the Veo native path, note: refs go via `config.reference_images` (wrapped), audio via `config.generate_audio`, driving video via `video=`. Add file:line anchors. If no such section exists, skip (no fabricated content).

- [ ] **Step 3: Verify + commit**

Run: `.venv/bin/python scripts/ci_smoke.py` → `OK`
```bash
git add ARCHITECTURE.md
git commit -m "docs(arch): reflect Veo native config-threading fix"
```

---

## Final verification (after all tasks)

- [ ] `.venv/bin/python -m pytest tests/unit/test_veo_native_config.py -v` → all pass.
- [ ] `.venv/bin/python -m pytest tests/unit/ -q` → no NEW failures vs the ~1242/3 baseline.
- [ ] `.venv/bin/python scripts/ci_smoke.py` → `OK`.
- [ ] **Live acceptance (NOT new code — operator's harness, spend-gated, run when authorized):** `scripts/run_veo_dialogue_test.py` exits 0; its `_ffprobe_streams` reports an audio track on the motion take; character preserved (no TypeError). Coordinate with the operator (their thread).

## Out of scope (spec §8)

Dialogue routing; the `phase_c_ffmpeg.py` call site; the hybrid-dialogue build (separate plan); new aspect_ratio/person_generation params; the live-E2E harness.
