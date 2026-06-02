# Veo + Overlay Dialogue Wire — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "dialogue shot = Veo *silent* video → lip-sync OVERLAY of our per-shot TTS" the pipeline default (with a `native` escape hatch), so dialogue gets Veo's look + a consistent character voice.

**Architecture:** Approach A — reuse the existing F1b lip-sync OVERLAY pass at `cinema/shots/controller.py:1233` (it already does Veo-video + TTS → lip-synced clip; it's just gated off for Veo dialogue by the `audio_embedded` tag). The wire: remove that short-circuit in `overlay` mode, run Veo silent, restore the video fallback cascade, feed per-shot TTS sized to speech, and dedup audio at assembly. Gated by a new `dialogue_voice_mode ∈ {overlay, native}` global setting (default `overlay`).

**Tech Stack:** Python 3.13, pytest + `monkeypatch` (offline, mocked HTTP/FAL/Veo/TTS — NO live API calls per the validation decision).

**Source spec:** `docs/superpowers/specs/2026-06-03-veo-overlay-dialogue-wire-design.md` (read it for full design rationale + the verified anchor table in Part 7). This plan implements that spec.

**Branch:** `feat/max-tier-provisioning` @ `de90cba` (NOT a worktree — shared-branch D-a model). **Working-tree note:** unrelated uncommitted state exists (modified `pulid_max.json`, `workflow_selector.py`; untracked `scripts/_*.py`, `logs/`). **Every commit uses explicit pathspec** — never `git add -A` / bare `git commit`.

**Project conventions every implementer MUST follow** (per `CLAUDE.md`):
1. Before editing an existing symbol, `grep -rn 'symbolName' --include='*.py' .` to find callers/importers; Read the call sites; report blast radius.
2. After edits, `git diff --stat` to confirm scope; commit with **explicit pathspec**.
3. **Brief-pattern adherence:** where this plan says "mirror X at file:line," verify the FULL shape of X (signature, defaults, call sites) before implementing; report divergence rather than guessing.
4. **Plan-vs-source divergence:** if the plan's line number / code shape differs from HEAD, use the actual source and report it.
5. Tests are **offline** — mock `requests`/`fal_client`/Veo/TTS as the existing dialogue tests do (see `tests/unit/test_dialogue_routing.py`, `test_f1b_dialogue_lipsync.py`, `test_hedra_native.py`). Assert routing + metadata, not real media.

**Global verification (run after each task):** `.venv/bin/python scripts/ci_smoke.py` → `OK`; the task's tests green. Final: `.venv/bin/python -m pytest tests/unit/ -q` → no NEW failures vs the 1302-passed/3-skipped baseline.

---

## Chunk 1: Setting + routing (silent Veo, fallbacks, audio_embedded gate)

### Task 1: `dialogue_voice_mode` setting + helper

**Files:**
- Modify: `cinema/shots/controller.py` (add a small mode helper near the existing dialogue logic)
- Modify: `web_server.py:339` (add the UI option list, mirroring `"lip_sync_modes"`)
- Test: `tests/unit/test_dialogue_voice_mode.py` (new)

`dialogue_voice_mode` is a **`global_settings` key** read via `settings.get("dialogue_voice_mode", "overlay")` — mirror `lip_sync_mode` at `controller.py:1256`. No `config/settings.py` change (it is a per-project global setting, not a `Settings` singleton field).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_dialogue_voice_mode.py
"""dialogue_voice_mode resolution (global_settings key, default 'overlay')."""
from cinema.shots.controller import _dialogue_voice_mode  # new helper


def test_defaults_to_overlay():
    assert _dialogue_voice_mode({}) == "overlay"
    assert _dialogue_voice_mode({"other": 1}) == "overlay"


def test_respects_explicit_value():
    assert _dialogue_voice_mode({"dialogue_voice_mode": "native"}) == "native"
    assert _dialogue_voice_mode({"dialogue_voice_mode": "overlay"}) == "overlay"


def test_unknown_value_falls_back_to_overlay():
    # Guard against typos in project settings.
    assert _dialogue_voice_mode({"dialogue_voice_mode": "bogus"}) == "overlay"
```

- [ ] **Step 2: Run it — expect FAIL** (`ImportError: cannot import name '_dialogue_voice_mode'`)

Run: `.venv/bin/python -m pytest tests/unit/test_dialogue_voice_mode.py -v`

- [ ] **Step 3: Implement the helper** in `cinema/shots/controller.py` (module level, near the other dialogue helpers):

```python
_VALID_DIALOGUE_VOICE_MODES = {"overlay", "native"}

def _dialogue_voice_mode(settings: dict) -> str:
    """Resolve the dialogue voice mode from global_settings (default 'overlay').
    'overlay' = Veo silent video + our TTS lip-sync overlay (consistent voice).
    'native'  = Veo generates its own embedded voice (legacy)."""
    mode = (settings or {}).get("dialogue_voice_mode", "overlay")
    return mode if mode in _VALID_DIALOGUE_VOICE_MODES else "overlay"
```

- [ ] **Step 4: Expose the UI list** in `web_server.py` next to `"lip_sync_modes"` (~:339):
  `"dialogue_voice_modes": ["overlay", "native"],`

- [ ] **Step 5: Run tests — expect PASS**; then `ci_smoke.py` → `OK`.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(dialogue): add dialogue_voice_mode setting (default overlay)" -- cinema/shots/controller.py web_server.py tests/unit/test_dialogue_voice_mode.py
```

---

### Task 2: Silent Veo for dialogue (overlay mode)

**Files:**
- Modify: `phase_c_ffmpeg.py` (`generate_ai_video` signature ~:43; the `generate_audio=` computation at `:281`)
- Modify: `cinema/shots/controller.py:1186-1201` (pass the new flag from the `generate_ai_video` call)
- Test: `tests/unit/test_dialogue_routing.py` (add cases)

**Impact analysis FIRST:** `grep -rn 'generate_ai_video(' --include='*.py' .` — list ALL callers. The new param is **defaulted** so non-dialogue callers are unaffected; confirm no other caller passes `has_dialogue=True` expecting embedded audio (report any that do).

Design: add `dialogue_native_audio: bool = False` to `generate_ai_video`; change `:281` from
`generate_audio=(shot_type == "landscape" or has_dialogue)` to
`generate_audio=(shot_type == "landscape" or dialogue_native_audio)`.
The controller computes `dialogue_native_audio = has_dialogue and _dialogue_voice_mode(settings) == "native"` and passes it.

- [ ] **Step 1: Write the failing test** — assert the `generate_audio` decision:

```python
# in tests/unit/test_dialogue_routing.py (new test)
import phase_c_ffmpeg

def test_generate_audio_false_for_overlay_dialogue(monkeypatch):
    """Overlay-mode dialogue → Veo silent (generate_audio=False)."""
    captured = {}
    def fake_veo(*a, **k):
        captured["generate_audio"] = k.get("generate_audio")
        return None  # force graceful return; we only inspect the flag
    # patch the Veo entrypoint generate_ai_video calls; mirror how existing
    # tests stub the cascade (grep test_dialogue_routing.py for the pattern).
    ...
    # Call generate_ai_video with shot_type="medium", has_dialogue=True,
    # dialogue_native_audio=False → expect captured["generate_audio"] is False.

def test_generate_audio_true_for_landscape():
    """Landscape still gets native audio regardless of dialogue."""
    # shot_type="landscape" → generate_audio True.

def test_generate_audio_true_for_native_dialogue():
    """native mode dialogue → dialogue_native_audio=True → generate_audio True."""
```

*(Implementer: match the existing cascade-stub pattern in `test_dialogue_routing.py`; if the cleanest unit is to test the boolean expression directly via a tiny helper, extract `_should_generate_audio(shot_type, dialogue_native_audio)` and test that — note the divergence.)*

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** the param + `:281` change + the controller call-site flag.
- [ ] **Step 4: Run tests — expect PASS;** `ci_smoke.py` → `OK`.
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(dialogue): silent Veo for overlay-mode dialogue (generate_audio gated on native)" -- phase_c_ffmpeg.py cinema/shots/controller.py tests/unit/test_dialogue_routing.py
```

---

### Task 3: Restore video_fallbacks for dialogue in overlay mode

**Files:**
- Modify: `cinema/shots/controller.py:1120-1147` (the dialogue routing override)
- Test: `tests/unit/test_dialogue_routing.py`

Today (`:1120-1144`) dialogue forces the native-audio engine (VEO) and sets `video_fallbacks = None`. New behavior:
- **`overlay` mode (default):** keep VEO_NATIVE as the dialogue primary (the §1 look decision) but **do NOT null `video_fallbacks`** — restore the standard video-modality fallback cascade (reuse the non-dialogue `video_fallbacks` builder; grep how it is built for non-dialogue shots and apply the same). Result: a Veo RAI-block falls through to Kling/Sora/etc. (silent) → overlay still applies.
- **`native` mode:** preserve today's behavior verbatim (force native-audio engine + `video_fallbacks=None`).

- [ ] **Step 1: Write the failing test(s)** — (a) overlay dialogue keeps fallbacks non-None + VEO primary; native dialogue keeps `None`; (b) **RAI-block → fallback → overlay** (spec Part 5 #4): when VEO fails/RAI-blocks and a fallback engine (e.g. Kling) wins, the take is NOT `audio_embedded` (overlay mode) so the F1b overlay pass still fires — i.e. the restored cascade + overlay survive a Veo block. *(Match the existing routing-assertion / cascade-stub style in `test_dialogue_routing.py`.)*
- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** the mode branch at `:1120-1147`.
- [ ] **Step 4: Run — expect PASS;** `ci_smoke.py` → `OK`.
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(dialogue): restore video fallback cascade for overlay-mode dialogue (RAI-block no longer fails the shot)" -- cinema/shots/controller.py tests/unit/test_dialogue_routing.py
```

---

### Task 4: Gate `audio_embedded` behind native mode → overlay fires

**Files:**
- Modify: `cinema/shots/controller.py:1215-1216`
- Test: `tests/unit/test_dialogue_routing.py:288-306` (UPDATE — currently asserts the old behavior)

Change `:1215` from `if engine_info.get("native_audio") and has_dialogue:` to also require native mode:
`if engine_info.get("native_audio") and has_dialogue and _dialogue_voice_mode(settings) == "native":`
In `overlay` mode the tag is not set, so the F1b pass at `:1233` runs for dialogue.

- [ ] **Step 1: UPDATE the existing test** `test_audio_embedded_set_when_winning_engine_is_native_audio_and_dialogue` (`:288`): split into (a) **native** mode → `audio_embedded=True` (old assertion, now mode-qualified); (b) **overlay** mode → NOT `audio_embedded`.
- [ ] **Step 2: Run — expect FAIL** (overlay case fails against current code).
- [ ] **Step 3: Implement** the `:1215` mode gate.
- [ ] **Step 4: Run — expect PASS;** `ci_smoke.py` → `OK`.
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(dialogue): only tag audio_embedded in native mode (overlay mode runs the lip-sync pass)" -- cinema/shots/controller.py tests/unit/test_dialogue_routing.py
```

---

## Chunk 2: Per-shot TTS + duration sizing

### Task 5: `_ensure_shot_audio` helper

**Files:**
- Create helper in: `cinema_pipeline.py` (near `_ensure_scene_audio` at `:481`)
- Test: `tests/unit/test_ensure_shot_audio.py` (new)

Mirror `_ensure_scene_audio` (`:481-524`) but render **only this shot's line** (`shot.get("dialogue")`) to `audio_{shot_id}.mp3` via `generate_dialogue_voiceover` (`audio/dialogue.py:286`). Return `None` when `shot.get("dialogue")` is None/empty (the scene-level fallback trigger).

- [ ] **Step 1: Write the failing test** (mock `generate_dialogue_voiceover` + filesystem, like the existing audio tests):

```python
# tests/unit/test_ensure_shot_audio.py — offline, mocked.
# - shot with "dialogue": "Hello." -> writes audio_<shot_id>.mp3, returns its path,
#   caches per-shot (second call returns cached path without re-rendering).
# - shot with no/empty "dialogue" -> returns None (scene-level fallback trigger).
# - render failure (generate_dialogue_voiceover returns falsy) -> returns None.
```
*(Implementer: instantiate the pipeline host the same minimal way `_ensure_scene_audio`'s tests do; if none exist, construct with a temp `temp_dir` + a stub project. Grep for existing `_ensure_scene_audio` tests first.)*

- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement `_ensure_shot_audio(self, shot, scene, characters)`** mirroring `_ensure_scene_audio`, keyed on `shot["id"]`, rendering `shot.get("dialogue")`.
- [ ] **Step 4: Run — expect PASS;** `ci_smoke.py` → `OK`.
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(dialogue): per-shot TTS helper _ensure_shot_audio (scene fallback when no shot line)" -- cinema_pipeline.py tests/unit/test_ensure_shot_audio.py
```

---

### Task 6: Wire per-shot TTS + clip-duration sizing into the F1b pass

**Files:**
- Modify: `cinema/shots/controller.py:1233-1262` (the F1b overlay block) + the `generate_ai_video` call-site duration (~:1186)
- Test: `tests/unit/test_f1b_dialogue_lipsync.py` (UPDATE + add)

Two changes, **overlay mode only** (native mode unchanged):
1. **Call-site swap** at `:1243`: replace `self._host._ensure_scene_audio(scene, chars_dicts)` with `self._host._ensure_shot_audio(shot, scene, chars_dicts)`, **falling back** to `_ensure_scene_audio` when it returns `None`.
2. **Duration sizing:** for an overlay-mode dialogue shot, resolve the per-shot TTS BEFORE `generate_ai_video`, measure its duration, and set the Veo `duration` string (`veo_native.generate_video(duration:str="8s")`) to the nearest supported value ≥ speech length, clamped to the supported set `{"4s","6s","8s"}` (cap at `8s`; over-length tails truncate — flagged out-of-scope). When no per-shot line exists, keep the shot's configured duration. *(Implementer — confirmed gap: `duration` is NOT currently a param on `generate_ai_video`; add `duration: str = "8s"` to its signature and thread it through BOTH the `VEO_NATIVE` branch (`phase_c_ffmpeg.py:265-287`, which calls `veo.generate_video(...)` without `duration`) and the fal-proxy branch (`:484`, which hardcodes `"duration":"8s"`). Measure the per-shot TTS length with the EXISTING `phase_c_ffmpeg._probe_duration(path)` util (`:1202`, ffprobe-based) — do NOT add a dep.)*

- [ ] **Step 1: Write/UPDATE tests** in `test_f1b_dialogue_lipsync.py`:
  - overlay-mode dialogue calls `_ensure_shot_audio` (not `_ensure_scene_audio`) when the shot has a line;
  - falls back to `_ensure_scene_audio` when the shot has no line;
  - Veo `duration` is set to the clamped per-shot-TTS length;
  - native mode path is unchanged.
- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** the call-site swap + duration sizing (overlay branch only).
- [ ] **Step 4: Run — expect PASS;** `ci_smoke.py` → `OK`.
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(dialogue): per-shot TTS + Veo clip sized to speech for overlay dialogue" -- cinema/shots/controller.py tests/unit/test_f1b_dialogue_lipsync.py
```

---

## Chunk 3: Assembler dedup (no double-audio)

### Task 7: `dialogue_audio_in_clip` flag + per-shot TTS suppression

**Files:**
- Modify: `cinema/shots/controller.py` (~:1260, the F1b overlay-success branch)
- Modify: `cinema_pipeline.py:633` (the `_build_scene_packages` count)
- Test: `tests/unit/test_f1b_dialogue_lipsync.py` + `tests/unit/test_dialogue_routing.py`

1. On overlay success (where `final_vid = ls_result`, ~:1260) set `take["metadata"]["dialogue_audio_in_clip"] = True` — the overlaid clip now carries the TTS.
2. At `cinema_pipeline.py:633`, change `if take_meta.get("audio_embedded"):` to
   `if take_meta.get("audio_embedded") or take_meta.get("dialogue_audio_in_clip"):`
   so a scene whose dialogue shots are all overlay-in-clip suppresses the scene-TTS mux (`scene_audio=None`, `:646-647`) — exactly as the native path does today (which already proves each clip's own audio survives concat, verified in spec Part 4 / `_assemble_final` `-c:a aac` + `-c copy`).

- [ ] **Step 1: Write tests:**
  - overlay success sets `dialogue_audio_in_clip=True`;
  - `_build_scene_packages`: scene with all dialogue shots `dialogue_audio_in_clip` → `scene_audio is None` (no double-voice);
  - **mixed scene** (one in-clip, one not) → `scene_audio` is kept (non-in-clip shot not silenced). *(Grep `_build_scene_packages` tests; mock approved-take metadata.)*
- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** both edits.
- [ ] **Step 4: Run — expect PASS;** `ci_smoke.py` → `OK`.
- [ ] **Step 5: Commit**

```bash
git commit -m "feat(dialogue): assembler dedup — suppress scene TTS for overlay-in-clip shots (no double-voice)" -- cinema/shots/controller.py cinema_pipeline.py tests/unit/test_f1b_dialogue_lipsync.py tests/unit/test_dialogue_routing.py
```

---

## Chunk 4: Regression sweep + docs

### Task 8: Full-suite regression + native-mode end-to-end test

**Files:**
- Test: `tests/unit/test_dialogue_routing.py`, `tests/unit/test_f1b_dialogue_lipsync.py`

- [ ] **Step 1: Add a `dialogue_voice_mode="native"` regression test** asserting the full legacy path (forced native-audio engine, `video_fallbacks=None`, `audio_embedded=True`, no overlay) is preserved — this is the escape hatch's guarantee.
- [ ] **Step 2: Run the full unit suite** `.venv/bin/python -m pytest tests/unit/ -q` — expect no NEW failures vs the 1302-passed/3-skipped baseline (the updated dialogue tests pass; everything else unchanged). Capture the count.
- [ ] **Step 3: Commit** (only if test files changed)

```bash
git commit -m "test(dialogue): native-mode escape-hatch regression + full-suite green" -- tests/unit/test_dialogue_routing.py tests/unit/test_f1b_dialogue_lipsync.py
```

---

### Task 9: Documentation

**Files:**
- Modify: `ARCHITECTURE.md` §10.6/§10.7 (the lipsync + `lip_sync_mode` sections)
- Modify: `OPERATIONS.md` (dialogue config), `docs/PROGRAM-MANUAL.md` §5 (the capability playbook)
- Modify: `docs/pipeline_status.toml` if a dialogue/lipsync component entry exists

Document: dialogue now defaults to **Veo silent video → per-shot-TTS lip-sync overlay** (consistent voice); `dialogue_voice_mode ∈ {overlay (default), native}`; Veo native audio is the `native` opt-in; RAI-block now falls through the restored video cascade.

- [ ] **Step 1:** Update §10.6/§10.7 in `ARCHITECTURE.md` (prose + the `lip_sync_mode` note); add `dialogue_voice_mode` to OPERATIONS.md + PROGRAM-MANUAL §5. Update each file's `*Last verified:*` footer with a 2026-06-03 scoped note (NOT a whole-file re-verify, per ADR-013).
- [ ] **Step 2: Verify** `ci_smoke.py` → `OK` (runs `check_doc_claims` on ARCHITECTURE.md — keep anchors valid).
- [ ] **Step 3: Commit**

```bash
git commit -m "docs(dialogue): document Veo+overlay default + dialogue_voice_mode (§10.6/§10.7, OPERATIONS, MANUAL §5)" -- ARCHITECTURE.md OPERATIONS.md docs/PROGRAM-MANUAL.md docs/pipeline_status.toml
```

---

## Done criteria

- `dialogue_voice_mode` default `overlay`: dialogue shots run Veo **silent** → restored video fallback cascade → per-shot TTS sized to speech → F1b overlay → `dialogue_audio_in_clip` → assembler suppresses scene-TTS (no double-voice). `native` preserves the legacy embedded path.
- Offline tests only; full unit suite green (no new failures vs 1302/3 baseline); `ci_smoke.py` → `OK`.
- 9 commits, each pathspec-scoped; unrelated working-tree state (SUPIR bake, scratch) untouched.
- Docs (ARCHITECTURE §10.6/§10.7, OPERATIONS, MANUAL §5) reflect the new default.
- **Deferred (out of scope, per spec Part 6):** live wired-E2E (approach already proven by `logs/veo_musetalk_v2studio.mp4`); full line→shot dialogue mapping; long-line splitting across shots.
