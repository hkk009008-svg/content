# Hybrid Dialogue Voice Routing Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route each dialogue shot between a native-AV path (the video model speaks the line) and a controlled path (ElevenLabs TTS + lip-sync), driven by a per-character "voice casting" flag — with the native path cascading only among native-audio engines (never silently to TTS).

**Architecture:** Add `Character.native_voice: bool`. Generalize the existing dialogue-routing override in `cinema/shots/controller.py` into a *casting router*: resolve the speaking character, read its `native_voice`, and pick the path. The native path uses a new pure helper `rank_native_audio_engines(purpose)` that filters the registry to live + funded + un-sunset native-audio engines and ranks them by purpose-fit then quality. Wire Sora-2 native audio so the native cascade has a real second engine. Everything except the final live native-audio E2E is unit/ffmpeg-testable offline (no pod, no Vertex), like the M1 xfade fix.

**Tech Stack:** Python 3.13, Pydantic v2 (`domain/models.py`), pytest (offline, mock-based; see `tests/unit/test_dialogue_routing.py`). Registry + routing helpers live in `domain/scene_decomposer.py`.

**Spec:** `docs/superpowers/specs/2026-05-29-hybrid-dialogue-voice-routing-design.md`. This plan resolves that spec's §5 open questions and refines three framings — see "Decisions" below.

---

## Decisions (resolving the spec's open questions + spec-review findings)

These were settled during spec-review against current source (`2026-05-29`). Where this plan differs from the spec's prose, **this plan wins** (the spec's §5 explicitly delegates these to the plan).

- **D1 — Speaker resolution = `primary_character` (spec §5.1).** MVP keys the casting decision on the shot's `primary_character`, falling back to the first `characters_in_frame` — mirroring the existing resolution at `cinema/shots/controller.py:381`. The "any cast char in frame → force controlled" conservative rule is **out of scope** (noted in spec §5.1; revisit only if multi-speaker shots become common).

- **D2 — Native-path ranking = purpose-fit THEN quality (refines spec §4.3).** The spec's pure-global-`quality_score` ranking would route *dialogue* to `SORA_NATIVE` (0.88) over `VEO_NATIVE` (0.85), but the registry's `best_for` + `PURPOSE_API_RANKING` place Sora in `action_motion`/`macro_detail`, **not** dialogue; Veo is the dialogue-tuned native-audio engine. So `rank_native_audio_engines` ranks by `(purpose in best_for, quality_score)` descending. For `dialogue_close_up` with all creds present this yields `[VEO_NATIVE, SORA_NATIVE, SORA_2]` — Veo primary (purpose-correct), Sora a *real* fallback (the spec's goal). The candidate set is built from the **whole registry's native-audio video engines**, not just the purpose ranking, so Sora is reachable as a fallback even though it isn't purpose-listed for dialogue.

- **D3 — Cast/native branch split + cast-engine guard (refines spec §4.2).** The existing `if has_dialogue:` block (`controller.py:1117-1141`) force-routes *all* dialogue to native. The casting router splits it:
  - `native_voice=True` → ranked native selection (D2), with `video_fallbacks = order[1:]` so the cascade stays **inside** the native-audio set (safe — every entry is `native_audio`, so no silent-voice regression; this is *better* than today's `video_fallbacks=None` which relied on a single engine's internal cascade).
  - `native_voice=False` (cast, the default) → **skip** the native override; keep the optimizer/template engine + its fallbacks so F1b's mandatory lip-sync (`controller.py:1220-1244`) runs over the character's ElevenLabs voice. A guard (`downgrade_native_audio_engine`) ensures the resolved engine is **not** native-audio, so an optimizer/template native suggestion can't silently embed a model voice over the cast voice (which would set `audio_embedded=True` at `controller.py:1212` and skip lip-sync).

- **D4 — `sunset_passed(engine, *, now=None)` takes an injectable `now`** so cascade/sunset tests are deterministic (no wall-clock dependence). `creds_available(engine)` uses **`config/settings.py` truthiness** (`openai_api_key` / `fal_key` / `google_cloud_project`), **not** a live init-probe — the router runs per-shot and a probe per call is too costly. This matches how the rest of the codebase keys availability off settings.

- **D5 — "Default preserves today's behavior" is a behavior CHANGE, stated honestly (spec-review F1).** With Vertex now LIVE, today a dialogue shot hard-overrides to `VEO_NATIVE`, comes back `audio_embedded=True`, and the lip-sync pass is skipped — i.e. dialogue currently uses Veo's *model* voice, ignoring the character's ElevenLabs `voice_id`. After this change, the default (`native_voice=False` = cast) routes dialogue to the **controlled** path (the character's cast voice). That is the *intended* hybrid correction, but it **does change** the current-with-Vertex behavior. It must be called out in the doc-sync task and the PR body, not described as a no-op.

- **D6 — Sequencing: build + verify offline now; live native-audio E2E deferred.** Spec §7's router/casting/Sora-wiring/cascade-invariant tests are offline (mock-based, like `test_dialogue_routing.py` and the M1 ffmpeg fix). Only the final *live native-audio E2E* (a real Veo/Sora dialogue generation producing embedded voice) is Vertex/pod-gated and is **not** part of this plan — track it as a follow-up validation once a native-voice character is exercised end-to-end.

### Verified source facts (grounding — `2026-05-29`, HEAD `9f0256d`)

| Fact | Evidence |
|---|---|
| `Character` is a Pydantic `BaseModel`, `extra="allow"`; fields like `voice_id: str = ""`, `gender: str = ""` | `domain/models.py:137-152` |
| `native_voice` absent today (new field) | `grep -n native_voice domain/models.py` → no match |
| Registry engines already carry `quality_score`, `modality`, `status`, `best_for`; values match the spec exactly (`SORA_NATIVE` 0.88, `SORA_2` 0.87, `VEO_NATIVE` 0.85) | `domain/scene_decomposer.py:42,49,43` |
| `native_audio: True` is on `VEO_NATIVE` only | `domain/scene_decomposer.py:43`; no other engine has the key |
| `sunset` field absent today (new field) | `grep -n sunset domain/scene_decomposer.py` → no match |
| `SORA_NATIVE` (OpenAI direct) + `SORA_2` (FAL proxy) both exist, `status:"live"` | `domain/scene_decomposer.py:42,49` |
| Speaking-char resolution pattern | `cinema/shots/controller.py:381` — `shot.get("primary_character") or (in_frame[0] if in_frame else "")` |
| Dialogue override block to generalize | `cinema/shots/controller.py:1117-1141` |
| `audio_embedded` tag (winning native-audio engine) | `cinema/shots/controller.py:1206-1213` |
| F1b mandatory lip-sync pass (cast path) | `cinema/shots/controller.py:1220-1244` |
| `sora_native.py:generate_video()` is video-only (no `generate_audio` param) | `sora_native.py:42-51` |
| `SORA_NATIVE` call site (no audio passed) | `phase_c_ffmpeg.py:243-256` |
| `SORA_2` fal arguments (no audio field) | `phase_c_ffmpeg.py:412-417` |
| Veo's audio gating pattern to mirror | `phase_c_ffmpeg.py:281` — `generate_audio=(shot_type == "landscape" or has_dialogue)` |
| `has_dialogue` is in scope at the Sora branches (function param) | `phase_c_ffmpeg.py` `generate_ai_video(...)` passes/receives `has_dialogue`; `controller.py:1195` |
| Existing tests assert dialogue → `VEO_NATIVE` (will need updating for casting) | `tests/unit/test_dialogue_routing.py:52-57` |

---

## File Structure

- `domain/models.py` — add `Character.native_voice: bool = False` (one field). Responsibility unchanged: domain data model.
- `domain/scene_decomposer.py` — add `native_audio`/`sunset` to two Sora registry rows; add a module logger; add pure helpers `sunset_passed`, `creds_available`, `rank_native_audio_engines`, `downgrade_native_audio_engine`, and the decision function `resolve_dialogue_routing`. These live here because the registry + `PURPOSE_API_RANKING` they read live here, and keeping the decision pure makes it directly testable and shrinks the `controller.py` edit.
- `sora_native.py` — add a `generate_audio: bool = False` param to `generate_video()` (interface symmetry with Veo; wiring verified against the live SDK at build time).
- `phase_c_ffmpeg.py` — pass `generate_audio` on the `SORA_NATIVE` call and add it to the `SORA_2` fal arguments, gated on `has_dialogue` (mirror `:281`).
- `cinema/shots/controller.py` — generalize the `has_dialogue` override (1117-1141) into the casting router (D3). The single highest-risk change; isolated to that block.
- `tests/unit/test_dialogue_routing.py` — extend with casting/ranking/cascade tests; **update** the existing tests that assume unconditional dialogue → `VEO_NATIVE`.
- `tests/unit/test_native_audio_ranking.py` (new) — unit tests for the pure helpers + `resolve_dialogue_routing` (reuses local `_settings_with`/`_all_creds` stubs).
- Doc-sync: `ARCHITECTURE.md` dialogue/routing section; fix the stale `recommend_lip_sync_mode()` reference in the `ai-video-gen` skill.

---

## Chunk 1: Casting model, registry, and native-audio ranking helpers

### Task 1: `Character.native_voice` field

**Files:**
- Modify: `domain/models.py:145` (add field next to `voice_id`)
- Test: `tests/unit/test_models_native_voice.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_models_native_voice.py
from domain.models import Character


def test_native_voice_defaults_false():
    c = Character(id="char_1", name="Aria")
    assert c.native_voice is False


def test_native_voice_can_be_set_true_and_roundtrips():
    c = Character(id="char_1", name="Aria", native_voice=True)
    assert c.native_voice is True
    # Pydantic round-trip (the project persists characters via model_dump/validate).
    again = Character.model_validate(c.model_dump())
    assert again.native_voice is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_models_native_voice.py -v`
Expected: `test_native_voice_defaults_false` FAILS — `extra="allow"` means the attribute is absent unless passed, so `c.native_voice` raises `AttributeError`. (`test_..._set_true` may incidentally pass via `extra="allow"`, but the default test pins the real behavior.)

- [ ] **Step 3: Add the field**

In `domain/models.py`, in the `Character` class, immediately after `voice_id: str = ""` (line 145):

```python
    # Per-character voice casting (hybrid dialogue routing). False ("cast"):
    # the character keeps its ElevenLabs voice_id → controlled TTS + lip-sync.
    # True ("native"): the video model voices them → native-AV path; TTS skipped.
    # Explicit flag, not voice_id=="" — voice_id auto-assigns, so emptiness can't
    # encode intent. See docs/superpowers/plans/2026-05-29-hybrid-dialogue-voice-routing.md.
    native_voice: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_models_native_voice.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add domain/models.py tests/unit/test_models_native_voice.py
git commit -m "feat(models): add Character.native_voice for hybrid dialogue casting"
```

---

### Task 2: Sora-2 native-audio wiring

**Files:**
- Modify: `sora_native.py:42-51` (add `generate_audio` param)
- Modify: `phase_c_ffmpeg.py:243-256` (pass it on the `SORA_NATIVE` call), `phase_c_ffmpeg.py:412-417` (add it to the `SORA_2` fal arguments)
- Test: `tests/unit/test_dialogue_routing.py` (add a Sora-audio-wiring test class)

> **Build-time verification — REQUIRED, blocks the rest of this task.** Sora 2 produces synced native audio by design. Before finalizing the wiring, confirm the exact audio-toggle field name for **(a)** the OpenAI `videos.create_and_poll` SDK and **(b)** the `fal-ai/sora-2/image-to-video` schema (Context7 / the fal model page). Grounding: the VEO-fal and KLING-fal payloads already use `"generate_audio"` as the fal audio key (`phase_c_ffmpeg.py:486,543`), so `"generate_audio"` is the established convention here — likely correct for sora-2, but **confirm it**. If the OpenAI SDK exposes no toggle (audio implicit), keep the `generate_audio` param for interface symmetry and document that Sora-direct audio is implicit. **If the confirmed fal key differs from `generate_audio`, update BOTH the implementation (Step 3) and the capture test (Step 1) together.** Report any divergence per the plan-vs-source rule.

- [ ] **Step 1: Write the failing test**

```python
# in tests/unit/test_dialogue_routing.py — new class
class TestSoraGenerateAudioParam:
    def test_generate_video_accepts_generate_audio(self):
        import inspect
        import sora_native
        sig = inspect.signature(sora_native.SoraNativeAPI.generate_video)
        assert "generate_audio" in sig.parameters
        assert sig.parameters["generate_audio"].default is False

    def test_sora2_fal_call_passes_audio_for_dialogue(self):
        # Offline capture: the SORA_2 fal call must carry the audio toggle for a
        # dialogue shot. fal arguments use "generate_audio" (same key as the
        # VEO-fal/KLING-fal payloads, phase_c_ffmpeg.py:486,543) — confirm at
        # build time (Step 3 note); update this key + the impl together if it
        # differs. `settings`, `FAL_AVAILABLE`, `fal_client` are module-level in
        # phase_c_ffmpeg (verify before relying on these patch targets).
        import phase_c_ffmpeg as pcf
        from phase_c_ffmpeg import generate_ai_video
        captured = {}

        def _fake_subscribe(model, arguments=None, **kw):
            captured["model"] = model
            captured["arguments"] = arguments or {}
            return {"video": {"url": "http://x/out.mp4"}}

        fake_fal = MagicMock(subscribe=_fake_subscribe, upload_file=lambda p: "http://x/in.png")
        with patch.object(pcf, "fal_client", fake_fal), \
             patch.object(pcf, "FAL_AVAILABLE", True), \
             patch.object(pcf, "settings", MagicMock(fal_key="fal-x")), \
             patch("urllib.request.urlretrieve"), \
             patch("os.path.exists", return_value=True):
            generate_ai_video(
                image_path="/tmp/f.png", camera_motion="zoom_in_slow",
                target_api="SORA_2", output_mp4="/tmp/o.mp4",
                shot_type="portrait", has_dialogue=True,
            )
        assert captured["model"] == "fal-ai/sora-2/image-to-video"
        assert captured["arguments"].get("generate_audio") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest "tests/unit/test_dialogue_routing.py::TestSoraGenerateAudioParam" -v`
Expected: FAIL — `generate_audio` not in signature.

- [ ] **Step 3: Add the param + wire the fal call**

`sora_native.py` `generate_video` signature (after `resolution`, before `driving_video_path`):

```python
        generate_audio: bool = False,
```

Add to the docstring Args and, per the build-time verification, pass the audio toggle into the OpenAI `videos.create_and_poll(...)` call if the SDK supports it (else leave a documented note that Sora-direct audio is implicit).

`phase_c_ffmpeg.py` `SORA_NATIVE` call (`:243`), add the argument (mirror Veo `:281`):

```python
                generate_audio=has_dialogue,  # Sora 2 native synced audio for dialogue
```

`phase_c_ffmpeg.py` `SORA_2` fal arguments (`:412`), add to the `arguments` dict:

```python
                        "generate_audio": bool(has_dialogue),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest "tests/unit/test_dialogue_routing.py::TestSoraGenerateAudioParam" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sora_native.py phase_c_ffmpeg.py tests/unit/test_dialogue_routing.py
git commit -m "feat(sora): wire generate_audio through Sora-native + Sora-2 fal paths"
```

---

### Task 3: Flag `native_audio` + `sunset` on the Sora registry entries

**Files:**
- Modify: `domain/scene_decomposer.py:42` (`SORA_NATIVE`), `:49` (`SORA_2`)
- Test: `tests/unit/test_native_audio_ranking.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_native_audio_ranking.py
from domain.scene_decomposer import API_REGISTRY


def test_sora_engines_now_carry_native_audio():
    assert API_REGISTRY["SORA_NATIVE"].get("native_audio") is True
    assert API_REGISTRY["SORA_2"].get("native_audio") is True


def test_sora_engines_carry_a_valid_sunset_date():
    # The EXACT date is an external fact (see Step 3 research note); this test
    # pins the MECHANISM — both Sora engines carry a parseable ISO sunset — and
    # reads the value from the registry instead of hardcoding an unverified one.
    from datetime import date
    for eng in ("SORA_NATIVE", "SORA_2"):
        raw = API_REGISTRY[eng].get("sunset")
        assert raw, f"{eng} must carry a sunset date"
        date.fromisoformat(raw)  # raises if not a valid ISO date


def test_veo_native_unchanged():
    assert API_REGISTRY["VEO_NATIVE"].get("native_audio") is True
    assert API_REGISTRY["VEO_NATIVE"].get("sunset") is None  # no announced Veo sunset
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_native_audio_ranking.py -v`
Expected: FAIL — Sora rows lack `native_audio`/`sunset`.

- [ ] **Step 3: Edit the two registry rows**

**First, confirm the exact OpenAI Sora 2 API sunset date** (WebSearch / Context7 the OpenAI API deprecation docs). `sora_native.py:6` says only *"September 2026"* — no day — so `2026-09-24` (the spec's value) is **UNVERIFIED precision**; do not pin it as fact without a source (Rule #1 / ADR-013). Pin the confirmed ISO date in both rows. Then add `"native_audio": True, "sunset": "<confirmed-ISO-date>"` to the `SORA_NATIVE` (`:42`) and `SORA_2` (`:49`) dicts (append before the closing brace, matching the existing inline-dict style). The mechanism test above passes for any valid ISO date; the exact value is documentation-of-record — **cite the source in the commit body.** If the date can't be confirmed, use a conservative best-estimate and label it as such in an inline comment.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_native_audio_ranking.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add domain/scene_decomposer.py tests/unit/test_native_audio_ranking.py
git commit -m "feat(registry): flag native_audio + sunset on SORA_NATIVE/SORA_2"
```

---

### Task 4: `sunset_passed()` helper

**Files:**
- Modify: `domain/scene_decomposer.py` (add helper near `API_REGISTRY`)
- Test: `tests/unit/test_native_audio_ranking.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/unit/test_native_audio_ranking.py
from datetime import date, timedelta
from domain.scene_decomposer import sunset_passed, API_REGISTRY


def test_no_sunset_field_never_passes():
    assert sunset_passed("VEO_NATIVE", now=date(2099, 1, 1)) is False


# Boundary tests DERIVE the date from the registry (not a hardcoded literal) so
# they stay correct whatever sunset value Task 3 pins at build time. Hardcoding
# 2026-09-24 here would silently re-assume the very date Task 3 says is unverified.
def _sora2_sunset():
    return date.fromisoformat(API_REGISTRY["SORA_2"]["sunset"])


def test_day_before_sunset_not_passed():
    assert sunset_passed("SORA_2", now=_sora2_sunset() - timedelta(days=1)) is False


def test_on_sunset_date_still_live():
    # "now <= sunset" means NOT passed on the sunset day itself.
    assert sunset_passed("SORA_2", now=_sora2_sunset()) is False


def test_after_sunset_passed():
    assert sunset_passed("SORA_2", now=_sora2_sunset() + timedelta(days=1)) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_native_audio_ranking.py -k sunset -v`
Expected: FAIL — `sunset_passed` not defined.

- [ ] **Step 3: Implement**

```python
# domain/scene_decomposer.py — near API_REGISTRY
from datetime import date as _date


def sunset_passed(engine_key: str, *, now: "_date | None" = None) -> bool:
    """True if the engine has a `sunset` date and `now` is strictly after it.
    Engines without a `sunset` field never sunset. `now` is injectable for
    deterministic tests; defaults to today's date when None."""
    raw = API_REGISTRY.get(engine_key, {}).get("sunset")
    if not raw:
        return False
    sunset = _date.fromisoformat(raw)
    today = now if now is not None else _date.today()
    return today > sunset
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_native_audio_ranking.py -k sunset -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add domain/scene_decomposer.py tests/unit/test_native_audio_ranking.py
git commit -m "feat(registry): sunset_passed() helper (injectable now)"
```

---

### Task 5: `creds_available()` helper

**Files:**
- Modify: `domain/scene_decomposer.py`
- Test: `tests/unit/test_native_audio_ranking.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/unit/test_native_audio_ranking.py
from unittest.mock import patch
from domain.scene_decomposer import creds_available


def _settings_with(**kw):
    class _S: ...
    s = _S()
    s.openai_api_key = kw.get("openai_api_key", "")
    s.fal_key = kw.get("fal_key", "")
    s.google_cloud_project = kw.get("google_cloud_project", "")
    return s


def test_veo_needs_google_cloud_project():
    with patch("domain.scene_decomposer.settings", _settings_with(google_cloud_project="proj")):
        assert creds_available("VEO_NATIVE") is True
    with patch("domain.scene_decomposer.settings", _settings_with()):
        assert creds_available("VEO_NATIVE") is False


def test_sora_native_needs_openai_key():
    with patch("domain.scene_decomposer.settings", _settings_with(openai_api_key="sk-x")):
        assert creds_available("SORA_NATIVE") is True
    with patch("domain.scene_decomposer.settings", _settings_with()):
        assert creds_available("SORA_NATIVE") is False


def test_sora_2_needs_fal_key():
    with patch("domain.scene_decomposer.settings", _settings_with(fal_key="fal-x")):
        assert creds_available("SORA_2") is True
    with patch("domain.scene_decomposer.settings", _settings_with()):
        assert creds_available("SORA_2") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_native_audio_ranking.py -k creds -v`
Expected: FAIL — `creds_available` not defined.

> **Build-time check (verified `2026-05-29`):** `domain/scene_decomposer.py:14` already has `from config.settings import settings`, so `patch('domain.scene_decomposer.settings', ...)` works as written. Re-confirm with `grep -n 'from config.settings' domain/scene_decomposer.py` if the file has moved.

- [ ] **Step 3: Implement**

```python
# domain/scene_decomposer.py
_CREDS_BY_ENGINE = {
    "VEO_NATIVE": "google_cloud_project",  # Vertex via ADC; project id is the truthiness proxy
    "SORA_NATIVE": "openai_api_key",
    "SORA_2": "fal_key",
}


def creds_available(engine_key: str) -> bool:
    """True if the funded credential this engine needs is present in settings.
    Truthiness only — no live probe (the router runs per-shot). Engines not in
    the map are treated as available (their availability is gated elsewhere)."""
    attr = _CREDS_BY_ENGINE.get(engine_key)
    if attr is None:
        return True
    return bool(getattr(settings, attr, ""))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_native_audio_ranking.py -k creds -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add domain/scene_decomposer.py tests/unit/test_native_audio_ranking.py
git commit -m "feat(registry): creds_available() helper (settings truthiness)"
```

---

### Task 6: `rank_native_audio_engines()` candidate-builder

**Files:**
- Modify: `domain/scene_decomposer.py`
- Test: `tests/unit/test_native_audio_ranking.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/unit/test_native_audio_ranking.py
from datetime import date
from unittest.mock import patch
from domain.scene_decomposer import rank_native_audio_engines


def _all_creds():
    class _S: ...
    s = _S()
    s.openai_api_key = "sk-x"; s.fal_key = "fal-x"; s.google_cloud_project = "proj"
    return s


def test_dialogue_ranks_veo_first_then_sora_fallbacks():
    # Purpose-fit (Veo is best_for dialogue) beats Sora's higher global quality.
    with patch("domain.scene_decomposer.settings", _all_creds()):
        order = rank_native_audio_engines("dialogue_close_up", now=date(2026, 1, 1))
    assert order[0] == "VEO_NATIVE"
    assert set(order[1:]) == {"SORA_NATIVE", "SORA_2"}  # real native fallbacks
    assert order[1] == "SORA_NATIVE"  # quality tiebreak among non-purpose-fit: 0.88 > 0.87


def test_no_creds_excludes_engine():
    class _S: ...
    s = _S(); s.openai_api_key = ""; s.fal_key = ""; s.google_cloud_project = "proj"
    with patch("domain.scene_decomposer.settings", s):
        order = rank_native_audio_engines("dialogue_close_up", now=date(2026, 1, 1))
    assert order == ["VEO_NATIVE"]  # only funded native-audio engine


def test_past_sunset_excludes_sora():
    with patch("domain.scene_decomposer.settings", _all_creds()):
        order = rank_native_audio_engines("dialogue_close_up", now=date(2026, 9, 25))
    assert order == ["VEO_NATIVE"]  # both Sora engines sunset 2026-09-24


def test_cascade_invariant_all_native_audio_video_live():
    from domain.scene_decomposer import API_REGISTRY
    with patch("domain.scene_decomposer.settings", _all_creds()):
        order = rank_native_audio_engines("dialogue_close_up", now=date(2026, 1, 1))
    for key in order:
        info = API_REGISTRY[key]
        assert info.get("native_audio") is True
        assert info.get("modality") == "video"
        assert info.get("status") == "live"


def test_empty_when_no_funded_engine():
    class _S: ...
    s = _S(); s.openai_api_key = ""; s.fal_key = ""; s.google_cloud_project = ""
    with patch("domain.scene_decomposer.settings", s):
        assert rank_native_audio_engines("dialogue_close_up", now=date(2026, 1, 1)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_native_audio_ranking.py -k rank -v`
Expected: FAIL — `rank_native_audio_engines` not defined.

- [ ] **Step 3: Implement**

```python
# domain/scene_decomposer.py
def rank_native_audio_engines(purpose: str, *, now=None) -> list[str]:
    """Native-AV candidate list for a dialogue shot: live, funded, un-sunset
    native-audio video engines, ranked by purpose-fit then quality. The chain
    stays inside this set — callers must NOT fall back to a non-native engine
    (that silently drops embedded voice). Returns [] when none are available."""
    candidates = [
        key for key, info in API_REGISTRY.items()
        if info.get("native_audio")
        and info.get("modality") == "video"
        and info.get("status") == "live"
        and creds_available(key)
        and not sunset_passed(key, now=now)
    ]
    candidates.sort(
        key=lambda k: (
            purpose in API_REGISTRY[k].get("best_for", []),
            API_REGISTRY[k].get("quality_score", 0.0),
        ),
        reverse=True,
    )
    return candidates
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_native_audio_ranking.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add domain/scene_decomposer.py tests/unit/test_native_audio_ranking.py
git commit -m "feat(routing): rank_native_audio_engines() — purpose-fit then quality, creds/sunset-filtered"
```

---

## Chunk 2: The casting router + integration

### Task 7: `downgrade_native_audio_engine()` cast guard

**Files:**
- Modify: `domain/scene_decomposer.py`
- Test: `tests/unit/test_native_audio_ranking.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/unit/test_native_audio_ranking.py
from domain.scene_decomposer import downgrade_native_audio_engine


def test_non_native_engine_unchanged():
    # KLING_NATIVE is not native-audio → returned as-is for the cast path.
    assert downgrade_native_audio_engine("dialogue_close_up", "KLING_NATIVE") == "KLING_NATIVE"


def test_native_engine_downgraded_to_non_native():
    # A cast char must not be routed to a native-audio engine (would embed a
    # model voice over the cast voice). VEO_NATIVE → first non-native in ranking.
    result = downgrade_native_audio_engine("dialogue_close_up", "VEO_NATIVE")
    from domain.scene_decomposer import API_REGISTRY
    assert API_REGISTRY[result].get("native_audio") is not True
    assert API_REGISTRY[result].get("modality") == "video"


def test_talking_head_full_downgrades_via_global_fallback():
    # REGRESSION: talking_head_full's PURPOSE_API_RANKING is lipsync engines +
    # VEO_NATIVE only — NO non-native VIDEO engine. The guard must fall back to a
    # global non-native video engine, NOT silently return the native VEO_NATIVE
    # (which would set audio_embedded=True and skip lip-sync for a cast voice).
    result = downgrade_native_audio_engine("talking_head_full", "VEO_NATIVE")
    from domain.scene_decomposer import API_REGISTRY
    assert API_REGISTRY[result].get("native_audio") is not True
    assert API_REGISTRY[result].get("modality") == "video"
    assert API_REGISTRY[result].get("status") == "live"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_native_audio_ranking.py -k downgrade -v`
Expected: FAIL — not defined.

- [ ] **Step 3: Implement**

`domain/scene_decomposer.py` has **no module logger** today (verified `2026-05-29`). Add one once, near the top imports:

```python
import logging
logger = logging.getLogger(__name__)
```

Then the helper:

```python
# domain/scene_decomposer.py
def _first_live_non_native_video(purpose: str) -> str | None:
    """First live non-native-audio VIDEO engine — purpose ranking first, then a
    global registry scan (guarantees a result whenever any such engine exists,
    e.g. KLING_NATIVE / LTX)."""
    for key in PURPOSE_API_RANKING.get(purpose, []):
        info = API_REGISTRY.get(key, {})
        if (info.get("modality") == "video" and info.get("status") == "live"
                and not info.get("native_audio")):
            return key
    for key, info in API_REGISTRY.items():
        if (info.get("modality") == "video" and info.get("status") == "live"
                and not info.get("native_audio")):
            return key
    return None


def downgrade_native_audio_engine(purpose: str, current: str) -> str:
    """Controlled (cast) path guard: if `current` is a native-audio engine,
    return a live non-native-audio VIDEO engine so F1b lip-sync runs over the
    cast voice (instead of an embedded model voice setting audio_embedded=True).
    Prefers a purpose-ranked engine, then ANY live non-native video engine
    (talking_head_full's ranking is lipsync-only + VEO_NATIVE, so the global
    fallback is load-bearing). Returns `current` unchanged only when it is
    already non-native; logs a warning in the (registry-misconfig) case where no
    non-native video engine exists at all."""
    if not API_REGISTRY.get(current, {}).get("native_audio"):
        return current
    fallback = _first_live_non_native_video(purpose)
    if fallback is not None:
        return fallback
    logger.warning(
        "downgrade_native_audio_engine: no non-native video engine in the "
        "registry; cast character may receive embedded model audio "
        "(purpose=%s, engine=%s).", purpose, current,
    )
    return current
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_native_audio_ranking.py -k downgrade -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add domain/scene_decomposer.py tests/unit/test_native_audio_ranking.py
git commit -m "feat(routing): downgrade_native_audio_engine() cast-path guard"
```

---

### Task 8: `resolve_dialogue_routing()` — the casting decision (pure function)

Extract the native-vs-controlled decision into a pure function so it is directly unit-testable (no controller invocation) and the `controller.py` edit (Task 9) stays minimal. This is the spec §4.2 router logic + the spec §7 cast-vs-native assertions, as one testable unit.

**Files:**
- Modify: `domain/scene_decomposer.py`
- Test: `tests/unit/test_native_audio_ranking.py` (reuses the `_all_creds`/`_settings_with` helpers from Tasks 4-6)

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/unit/test_native_audio_ranking.py
from datetime import date
from unittest.mock import patch
from domain.scene_decomposer import resolve_dialogue_routing, API_REGISTRY


def test_native_dialogue_picks_top_native_with_native_fallbacks():
    with patch("domain.scene_decomposer.settings", _all_creds()):
        target, fallbacks = resolve_dialogue_routing(
            True, "dialogue_close_up", "KLING_NATIVE", ["LTX"], now=date(2026, 1, 1))
    assert target == "VEO_NATIVE"                       # purpose-fit native engine
    assert set(fallbacks) == {"SORA_NATIVE", "SORA_2"}  # cascade stays native
    assert all(API_REGISTRY[e].get("native_audio") for e in (target, *fallbacks))


def test_cast_dialogue_downgrades_a_native_suggestion():
    # Cast char + optimizer suggested VEO_NATIVE → must downgrade so the winning
    # engine is non-native (→ audio_embedded stays falsy → F1b lip-sync runs).
    with patch("domain.scene_decomposer.settings", _all_creds()):
        target, fallbacks = resolve_dialogue_routing(
            False, "dialogue_close_up", "VEO_NATIVE", None, now=date(2026, 1, 1))
    assert API_REGISTRY[target].get("native_audio") is not True
    assert fallbacks is None                            # input fallbacks passed through unchanged


def test_cast_dialogue_keeps_non_native_engine_and_fallbacks():
    with patch("domain.scene_decomposer.settings", _all_creds()):
        target, fallbacks = resolve_dialogue_routing(
            False, "dialogue_close_up", "KLING_NATIVE", ["LTX"], now=date(2026, 1, 1))
    assert target == "KLING_NATIVE"                     # already non-native → unchanged
    assert fallbacks == ["LTX"]


def test_native_with_no_creds_falls_to_controlled():
    no_creds = _settings_with()  # all blank
    with patch("domain.scene_decomposer.settings", no_creds):
        target, fallbacks = resolve_dialogue_routing(
            True, "dialogue_close_up", "VEO_NATIVE", None, now=date(2026, 1, 1))
    assert API_REGISTRY[target].get("native_audio") is not True  # downgraded to controlled
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_native_audio_ranking.py -k resolve_dialogue -v`
Expected: FAIL — `resolve_dialogue_routing` not defined.

- [ ] **Step 3: Implement**

```python
# domain/scene_decomposer.py
def resolve_dialogue_routing(native_voice: bool, purpose: str,
                             target_api: str, video_fallbacks, *, now=None):
    """Pure casting decision for a dialogue shot. Given the speaking character's
    native_voice flag and the already-resolved (target_api, video_fallbacks),
    return the (possibly overridden) pair:
      - native_voice=True with a funded/in-date native-audio engine → that
        engine + the remaining native engines as fallbacks (cascade stays inside
        the native-audio set — no silent-voice regression).
      - otherwise (cast, OR native requested but none available) → controlled:
        guarantee a non-native engine so F1b lip-sync runs over the cast voice;
        keep the resolved fallbacks.
    `now` is forwarded to the sunset filter for deterministic tests."""
    if native_voice:
        order = rank_native_audio_engines(purpose, now=now)
        if order:
            return order[0], (order[1:] or None)
        # native requested but nothing funded/in-date → fall through to controlled
    return downgrade_native_audio_engine(purpose, target_api), video_fallbacks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_native_audio_ranking.py -k resolve_dialogue -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add domain/scene_decomposer.py tests/unit/test_native_audio_ranking.py
git commit -m "feat(routing): resolve_dialogue_routing() — pure native-vs-controlled decision"
```

---

### Task 9: Wire the controller to the casting router (the `controller.py` edit)

> **Highest-risk file — the `has_dialogue` block (`controller.py:1117-1141`) is heavily patched (F1a/F1b Lane V fixes; comments at 1110/1215/1310). Re-read 1085-1245 in full before editing; preserve every existing comment and the downstream `audio_embedded` (`:1206-1213`) + F1b lip-sync (`:1220-1244`) contract. Per CLAUDE.md, grep the surrounding method's callers and report blast radius before editing.**

With the decision logic now a tested pure function (Task 8), the controller edit is small: resolve the speaking character, then delegate.

**Files:**
- Modify: `cinema/shots/controller.py:1117-1141` (replace the F1a override with the glue below)
- Test: `tests/unit/test_dialogue_routing.py` (concrete glue tests — speaker resolution)

- [ ] **Step 1: Write the failing glue tests**

The glue is the speaker resolution from `project.characters` + the `resolve_dialogue_routing` call. Test it with the file's logic-replication pattern (the established style for routing that lives inside `generate_motion_take`). Add a local settings stub to this file (small) so creds are deterministic:

```python
# tests/unit/test_dialogue_routing.py
def _all_creds_stub():
    s = MagicMock()
    s.openai_api_key = "sk-x"; s.fal_key = "fal-x"; s.google_cloud_project = "proj"
    return s


class TestCastingRouterGlue:
    """Controller glue (generate_motion_take): resolve the speaking character
    from project.characters → native_voice → resolve_dialogue_routing. Logic-
    replication of the 6-line glue (the decision itself is tested in
    test_native_audio_ranking.py::test_*resolve_dialogue*)."""

    def _glue(self, project, shot, purpose, target_api, fallbacks):
        from domain.scene_decomposer import resolve_dialogue_routing
        in_frame = shot.get("characters_in_frame") or []
        sid = shot.get("primary_character") or (in_frame[0] if in_frame else "")
        speaker = next((c for c in (project.get("characters") or []) if c.get("id") == sid), {})
        return resolve_dialogue_routing(
            bool(speaker.get("native_voice", False)), purpose, target_api, fallbacks)

    def test_resolves_primary_character_native_flag(self):
        from domain.scene_decomposer import API_REGISTRY
        with patch("domain.scene_decomposer.settings", _all_creds_stub()):
            project = {"characters": [{"id": "c1", "native_voice": True}, {"id": "c2"}]}
            shot = {"primary_character": "c1", "characters_in_frame": ["c2", "c1"]}
            target, _ = self._glue(project, shot, "dialogue_close_up", "KLING_NATIVE", None)
        assert target == "VEO_NATIVE"  # c1 native → native path

    def test_falls_back_to_first_in_frame_when_no_primary(self):
        with patch("domain.scene_decomposer.settings", _all_creds_stub()):
            project = {"characters": [{"id": "c1", "native_voice": True}]}
            shot = {"characters_in_frame": ["c1"]}  # no primary_character
            target, _ = self._glue(project, shot, "dialogue_close_up", "KLING_NATIVE", None)
        assert target == "VEO_NATIVE"

    def test_unknown_speaker_defaults_to_cast(self):
        from domain.scene_decomposer import API_REGISTRY
        with patch("domain.scene_decomposer.settings", _all_creds_stub()):
            project = {"characters": []}
            shot = {"primary_character": "ghost", "characters_in_frame": []}
            target, _ = self._glue(project, shot, "dialogue_close_up", "KLING_NATIVE", None)
        assert API_REGISTRY[target].get("native_audio") is not True  # no speaker → cast
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest "tests/unit/test_dialogue_routing.py::TestCastingRouterGlue" -v`
Expected: FAIL — `resolve_dialogue_routing` import errors until Task 8 lands (Task 8 ships first; if running in order this passes the import and fails only if the glue assertions are wrong).

- [ ] **Step 3: Implement the controller glue**

Replace the body of the `if has_dialogue:` block (`controller.py:1117-1141`, the F1a override) with — preserving the surrounding `if raw_api == "AUTO":` structure:

```python
            # ---- Casting-driven dialogue router (hybrid voice routing) ----
            # Resolve the speaking character, read native_voice, and delegate to
            # the pure resolver. Default native_voice=False ("cast") → controlled
            # (ElevenLabs TTS + lip-sync). Decision logic + tests live in
            # domain/scene_decomposer.py::resolve_dialogue_routing.
            # See docs/superpowers/plans/2026-05-29-hybrid-dialogue-voice-routing.md (D2/D3/D5).
            if has_dialogue:
                from domain.scene_decomposer import resolve_dialogue_routing
                _in_frame = shot.get("characters_in_frame") or []
                _speaker_id = shot.get("primary_character") or (_in_frame[0] if _in_frame else "")
                _speaker = next(
                    (c for c in (self.project.get("characters") or []) if c.get("id") == _speaker_id),
                    {},
                )
                _prev_api = target_api
                target_api, video_fallbacks = resolve_dialogue_routing(
                    bool(_speaker.get("native_voice", False)),
                    cached_purpose, target_api, video_fallbacks,
                )
                if target_api != _prev_api:
                    logger.info(
                        "dialogue casting router: %s → %s (native_voice=%s, purpose=%s)",
                        _prev_api, target_api,
                        bool(_speaker.get("native_voice", False)), cached_purpose,
                    )
```

> **Behavior notes (verify on read):**
> - This **removes** the old unconditional `video_fallbacks = None` for dialogue. The native branch now sets `video_fallbacks = order[1:]` (all native-audio → safe cascade); the cast branch keeps the resolved fallbacks. The non-AUTO branch at `:1142-1144` (`target_api = raw_api; video_fallbacks = None`) is **untouched** — pinned-API dialogue shots are unaffected.
> - The downstream `audio_embedded` tag (`:1206-1213`) is unchanged: cast → non-native winning engine → `audio_embedded` falsy → F1b lip-sync runs; native → native winning engine → `audio_embedded=True` → lip-sync skipped. This is exactly the spec §7 cast-vs-native split, achieved without touching the tag logic.
> - `self.project` is the project dict (`get("characters")`); confirm `self.project` is in scope at this point in `generate_motion_take` (it is used elsewhere in the method, e.g. the F1b block at `:1235`).

- [ ] **Step 4: Verify existing tests are unaffected**

`TestDialogueRoutingResolvesVeoNative` replicates only the *pre-override* suggestion-resolution logic (test `:92-98`) and stops **before** the casting block, so it stays green (the fixture's `suggested_video_api="VEO_NATIVE"` still resolves). No fixture edits are required — confirm by running:

Run: `.venv/bin/python -m pytest tests/unit/test_dialogue_routing.py tests/unit/test_f1b_dialogue_lipsync.py -v`
Expected: PASS — F1b lip-sync contract preserved for the cast (default) path; existing routing tests unchanged. (If any existing test *does* exercise the override and breaks, set `native_voice=True` on its speaking character — e.g. `project["characters"][0]["native_voice"] = True` — to preserve the native→VEO_NATIVE expectation, per D5.)

- [ ] **Step 5: Commit**

```bash
git add cinema/shots/controller.py tests/unit/test_dialogue_routing.py
git commit -m "feat(routing): wire casting-driven hybrid dialogue router in controller"
```

---

### Task 10: Doc-sync

**Files:**
- Modify: `ARCHITECTURE.md` (dialogue/routing section — describe the casting router + D5 behavior change)
- Modify: `.claude/skills/ai-video-gen/SKILL.md:169` (stale `recommend_lip_sync_mode()` reference — verified present `2026-05-29`; spec §8)
- Modify: `DECISIONS.md` — **NO** (ADRs are director-only; if this warrants an ADR, leave a note for the director, don't author it here)

- [ ] **Step 1: Locate the routing section + the stale ref**

Run: `grep -n "native_audio\|dialogue.*rout\|VEO_NATIVE" ARCHITECTURE.md | head`
The stale ref is at `.claude/skills/ai-video-gen/SKILL.md:169` (verified `2026-05-29`). Re-confirm with `grep -rn "recommend_lip_sync_mode" .claude/skills/ai-video-gen/` before editing.

- [ ] **Step 2: Update `ARCHITECTURE.md`**

Document: the casting router (`Character.native_voice` → native vs controlled), the `rank_native_audio_engines` purpose-fit-then-quality ranking, the native-only cascade invariant, and **D5** (with Vertex live, the default flips dialogue from Veo-native-voice to the character's cast voice). Add file:line anchors. Run the §15 smoke per ADR-013 before committing.

- [ ] **Step 3: Fix the stale skill reference**

Replace the `recommend_lip_sync_mode()` mention with the current API (`generate_lip_sync_video(mode="auto"|"overlay"|"generation")`, `lip_sync.py:687`).

- [ ] **Step 4: Verify + commit**

Run: `.venv/bin/python scripts/ci_smoke.py` → Expected: `OK` / exit 0
```bash
git add ARCHITECTURE.md <skill-file>
git commit -m "docs(arch): document hybrid dialogue casting router + behavior change (D5)"
```

---

## Final verification (after all tasks)

- [ ] Full unit suite: `.venv/bin/python -m pytest tests/unit/ -q` → Expected: no NEW failures vs the 1230/3 baseline (the updated `test_dialogue_routing.py` tests pass; net test count rises).
- [ ] Smoke: `.venv/bin/python scripts/ci_smoke.py` → `OK` / exit 0.
- [ ] **Deferred (not this plan — D6):** live native-audio E2E — exercise a `native_voice=True` character through `/generate` on Vertex/pod and confirm the take carries embedded voice + the cast path produces ElevenLabs+lip-sync. Track as a follow-up validation.

## Out of scope (spec §9)

Structured multi-speaker dialogue (per-shot speaker arrays); upscale/image routing; controlled-path internals; a UI casting toggle; making `cost_log` provider diagnostic (separate provenance-fix chip — see operator `2026-05-29T08-42-54Z` event).
