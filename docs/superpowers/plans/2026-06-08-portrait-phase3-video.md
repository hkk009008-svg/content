# Portrait Phase-3 Video Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (subagents are available in this harness). Steps use checkbox (`- [ ]`) syntax for tracking. Per the project CLAUDE.md, this is a multi-task plan → ORCHESTRATE (fresh subagent per task + two-stage review), do not implement directly in main context.

**Goal:** Make the four shipped video providers (Veo, Sora, Kling, Runway) emit true 9:16 (1080×1920) portrait video, validate it on-pod, then un-gate `SUPPORTED_ASPECT_RATIOS` — taking the whole portrait path live end-to-end.

**Architecture:** Extend the proven Phase-1/2 pattern — orientation logic stays in `cinema/aspect.py` (pure, stdlib); every provider call routes through it. The spine reads `aspect_ratio` from the `ctx` that `generate_ai_video` already receives (no new param, no controller change — the U9 "ctx-plumbing blocker" was verified false). A post-generation aspect backstop in the cascade rejects wrong-orientation clips so a portrait project can never silently ship landscape. The gate flip is the LAST task, hard-gated on an `ffprobe` preflight.

**Tech Stack:** Python 3.13, pytest (`tests/unit/`), `unittest.mock` / `monkeypatch`, `fal_client` + provider SDKs (mocked in tests), `ffprobe` (mocked via `subprocess.run` JSON side-effect in unit tests; real in the preflight script).

**Spec:** `docs/superpowers/specs/2026-06-08-portrait-phase3-video-design.md` (reviewed; tech-grounding 9/9 at HEAD). Where this plan and the spec/source disagree, **use the actual source at execution HEAD and report the divergence** (CLAUDE.md plan-vs-source rule). Production-file anchors below have **zero drift** through HEAD `1e7f0cc` (intervening commits are coord/docs only); a few test-file anchors may be off by 1-2 lines — **re-grep before editing** (Project Convention #4).

---

## File Structure

**Production (modify):**
- `cinema/aspect.py` — add `runway_ratio(aspect, model)`; (T10) append `"9:16"` to `SUPPORTED_ASPECT_RATIOS`. *Single source of truth for orientation.*
- `phase_c_ffmpeg.py` — the spine (`generate_ai_video` reads `_aspect`); fal-branch literals (`:423` SORA_2, `:491` VEO, `:718` SEEDANCE-excluded); Runway routes (`:355` model fix, `:363`/`:682` ratios); cascade filter + post-gen backstop (`generate_ai_video` `:126-170`).
- `veo_native.py` — `generate_video` gains a trailing `aspect_ratio` param threaded into `_build_generate_videos_config`.
- `sora_native.py` — `portrait_swap` the resolution dims + fix the landscape force-resize.

**Production (no change expected, verify only):** `cinema_pipeline.py` (assembly normalize `:1320`/`:45` already scales-to-container — T8 verifies it upscales sub-1080 → 1080×1920).

**Tests (create/extend):**
- `tests/unit/test_cinema_aspect.py` — extend: `runway_ratio` triad; (T10) flip the gate test.
- `tests/unit/test_phase_c_video_aspect.py` — **NEW**: the spine + per-provider fal/native 9:16 wiring + cascade routing-safety + backstop tests (the bulk).
- `tests/unit/test_veo_native_config.py` — extend: `cfg.aspect_ratio == "9:16"` when parameterized.
- `tests/unit/test_sora_native.py` — extend: portrait `size` + resize fix.
- `tests/unit/test_kling_native.py` — **NEW** (green-field; mirror `test_sora_native.py`): Kling has no aspect param (assert payload unchanged; capability is keyframe-driven).
- `tests/unit/test_web_server_aspect_validation.py` — (T10) 9:16 PUT now persists.

**Dev harness (create):**
- `scripts/_phase3_portrait_preflight.py` — live one-clip-per-provider 9:16 + `ffprobe` PASS/FAIL (T9). Mirrors `scripts/_veo_from_keyframe.py` + `scripts/_max_harness_preflight.py`.

---

## Test Conventions (DRY — read once; every task below references this)

**Run command (LOCAL, under D-a):**
```
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_<file>.py -q
```
(The exported `GIT_INDEX_FILE` from the D-a launch breaks ~9 temp-repo tests; CI is unaffected and uses `pytest tests/unit/ --tb=short -q`.)

**TC-1 — Pure-helper triad** (`test_cinema_aspect.py` style): flat `test_<helper>_<scenario>` functions, no class, no `parametrize`; direct `assert helper(in) == literal`. Each new helper gets: landscape-noop + portrait-transpose + unknown/None-default.

**TC-2 — Byte-identity refute** (the no-op-at-16:9 proof): build/load a fresh object, run the injector, assert the *specific* payload values equal the **template** at `"16:9"`/`None` and the **flipped** values at `"9:16"`. (There is NO whole-dict `== deepcopy` assertion; assert the concrete fields.)

**TC-3 — Provider mocking, strategy A (native module unit test):** at top of file `sys.modules.pop("<x>_native", None)` then `import <x>_native`. Patch the client where the module looks it up:
- Sora: `patch("sora_native.settings", _fake_settings(...))` + `patch("sora_native.openai.OpenAI", return_value=fake)`; assert on `api.client.videos.create_and_poll.call_args.kwargs`.
- LTX: `monkeypatch.setattr(ltx_native.fal_client, "subscribe", mock)`; assert `mock.call_args.kwargs["arguments"]["width"/"height"]`.
- Veo: pure `_build_generate_videos_config(...)` then `assert cfg.aspect_ratio == ...` (no client needed); or bypass `__init__` via `VeoNativeAPI.__new__(VeoNativeAPI)` + `side_effect` capture for the call-site.

**TC-4 — Provider mocking, strategy B (`generate_ai_video`/cascade):** stub all provider modules, then drive the real function:
```python
mock_inst = MagicMock(); mock_inst.generate_video.return_value = "/tmp/out.mp4"
with patch.dict("sys.modules", {"veo_native": MagicMock(VeoNativeAPI=MagicMock(return_value=mock_inst))}):
    with patch("os.path.exists", return_value=True):
        generate_ai_video(image_path="/tmp/f.png", camera_motion="zoom_in_slow",
                          target_api="VEO_NATIVE", output_mp4="/tmp/o.mp4",
                          shot_type="portrait", ctx=PipelineContext(global_settings={"aspect_ratio": "9:16"}))
assert mock_inst.generate_video.call_args.kwargs.get("aspect_ratio") == "9:16"
```
Works because each branch lazy-imports its provider (`from veo_native import VeoNativeAPI` at `:275`, kling `:206`, sora `:236`, ltx `:303`).

**TC-5 — fal-branch payload capture** (SORA_2 `:423` / VEO fal `:491`): build a **phase_c_ffmpeg-scoped** stub — patch `phase_c_ffmpeg.fal_client` + `phase_c_ffmpeg.settings` — whose `subscribe` returns the **video** shape `{"video": {"url": "..."}}` (the video branches read `result["video"]["url"]`; the image shape `{"images":[...]}` makes the branch return `None` → cascade, and the assertion never fires). Then:
```python
arguments = stub_fal.subscribe.call_args_list[0][1]["arguments"]
assert arguments["aspect_ratio"] == "9:16"
```
(`test_phase_c_assembly_portrait.py:166` `stub_fal_portrait` is a **pattern reference only** — it's image-scoped to `phase_c_assembly` and returns `{"images":...}`; build the video analog scoped to `phase_c_ffmpeg`.)

**TC-6 — ctx construction:** `from cinema.context import PipelineContext; ctx = PipelineContext(global_settings={"aspect_ratio": "9:16"})`. Three-case matrix: portrait / landscape (`"16:9"`) / no-ctx (`None` → default landscape).

**TC-7 — frozen settings injection:** `monkeypatch.setattr(<module>, "settings", dataclasses.replace(<module>.settings, <field>=...))`. **Kling** caches its keys at `__init__` (`self.access_key`/`self.secret_key`) AND calls `_generate_token` during construction — so for Kling **patch settings BEFORE constructing**: `monkeypatch.setattr(kling_native, "settings", dataclasses.replace(kling_native.settings, kling_access_key="x", kling_secret_key="y"))` then build. (Post-construction instance-attr override is too late — `_generate_token` already ran. The attrs are `access_key`/`secret_key`, not `_key`.)

**TC-8 — ffprobe dims (mocked, for backstop + upscale):** reuse `test_u3_media_conformance.py`'s harness — a fixture dict + `_make_ffprobe_run(fixture)` side-effect; `patch("phase_c_ffmpeg.subprocess.run", side_effect=...)`; the production probe is `phase_c_ffmpeg.probe_final_media(path)` → `result["format"]["width"/"height"]`. Add `FFPROBE_PORTRAIT = {"streams":[{"codec_type":"video","width":1080,"height":1920}],"format":{"width":1080,"height":1920,"duration":"5.0"}}`.

---

## Project Conventions (every task; subagent prompts MUST carry these)

1. **Impact analysis first:** before editing a symbol, `grep -rn '<symbol>' --include='*.py' .`, Read call sites, report blast radius.
2. **One commit per task** (T5 is two commits: 5a model-fix, 5b ratios). Type: `feat`/`refactor`/`test`/`fix`(scope). End with the `Co-Authored-By:` trailer.
3. **D-a commits:** `git add <paths>` then `git commit -- <paths>` (pathspec — shared index). **After any backgrounded Workflow, `git read-tree HEAD` before trusting `git add`/`diff`** (skip-worktree corruption; see `feedback_da_stale_index_refresh.md`).
4. **Plan-vs-source:** production anchors verified (zero prod drift through `1e7f0cc`); re-grep, use actual source, report divergence.
5. **Smoke before "done":** `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` (exit 0).
6. **Backward-compat (Rule #12):** `veo_native.generate_video`'s new param is appended LAST with a default. Its blast radius is **exactly ONE caller** — `phase_c_ffmpeg.py:277` (`veo.generate_video(...)`), keyword-arg → safe. (`:208`/`:249`/`:319` are the *kling/sora/ltx* call sites, NOT veo callers — don't conflate.)

---

## Chunk 1: Spine + Veo + Sora

### Task 1: `runway_ratio` helper in `cinema/aspect.py`

**Files:**
- Modify: `cinema/aspect.py` (add helper after `fal_aspect_ratio`, ~`:77`)
- Test: `tests/unit/test_cinema_aspect.py` (extend)

- [ ] **Step 1: Write the failing test** (TC-1 triad) in `test_cinema_aspect.py`:

```python
from cinema.aspect import runway_ratio  # add to existing imports

def test_runway_ratio_landscape_is_default():
    assert runway_ratio("16:9", "gen4_turbo") == "1280:720"
    assert runway_ratio("16:9", "gen3a_turbo") == "1280:768"
    assert runway_ratio(None, "gen4_turbo") == "1280:720"
    assert runway_ratio("4:3", "gen3a_turbo") == "1280:768"

def test_runway_ratio_portrait_per_model():
    assert runway_ratio("9:16", "gen4_turbo") == "720:1280"
    assert runway_ratio("9:16", "gen3a_turbo") == "768:1280"
```

- [ ] **Step 2: Run → FAIL** `... -m pytest tests/unit/test_cinema_aspect.py -q` → ImportError/`runway_ratio` undefined.

- [ ] **Step 3: Implement** in `cinema/aspect.py` (mirror `fal_aspect_ratio`'s docstring style):

```python
# Runway's ratio is a model-dependent "W:H" string; gen4 family tops at 720-wide
# portrait, gen3a_turbo at 768-wide. Centralizes the model+orientation choice.
_RUNWAY_PORTRAIT = {"gen3a_turbo": "768:1280"}
_RUNWAY_LANDSCAPE = {"gen3a_turbo": "1280:768"}

def runway_ratio(aspect_ratio: Optional[str], model: str) -> str:
    """Runway `ratio` string for the given aspect + model (landscape default)."""
    if is_portrait(aspect_ratio):
        return _RUNWAY_PORTRAIT.get(model, "720:1280")
    return _RUNWAY_LANDSCAPE.get(model, "1280:720")
```

- [ ] **Step 4: Run → PASS**.
- [ ] **Step 5: Commit** `feat(aspect): add runway_ratio helper (model-aware portrait W:H)` — `git add cinema/aspect.py tests/unit/test_cinema_aspect.py && git commit -- ...`

---

### Task 2: Aspect-threading spine in `generate_ai_video`

**Files:**
- Modify: `phase_c_ffmpeg.py` — top of `generate_ai_video` (after the early body, ~`:90`)
- Test: `tests/unit/test_phase_c_video_aspect.py` (**NEW**)

> **Plan-review note:** this is an **honest no-RED plumbing commit** — the spine hoist (`_aspect`) has no independently-observable behavior on its own (`_aspect` is assigned but unread until a provider consumes it in Task 3). Do NOT ship a fake "runs-without-error" RED: such a test passes green both pre- and post-change (verified: there is currently zero `_aspect` reference in `phase_c_ffmpeg.py`). The first genuine RED for the spine is **Task 3's** Veo `cfg.aspect_ratio == "9:16"`.

- [ ] **Step 1: Implement the hoist.** At the top of `generate_ai_video`'s body, in the **enclosing scope BEFORE the `try_next_api()` closure** (~:124) so the closure captures `_aspect`. **NOTE (review-corrected):** `get_project_setting` is NOT in scope at the function top today — it is imported only inside nested blocks (`:138`/`:164`/`:192`), so you MUST add its import here; and there is no `from cinema.aspect` import in this file yet:

```python
from cinema.context import get_project_setting   # NOT in scope at the spine today — add it
from cinema.aspect import DEFAULT_ASPECT_RATIO, is_portrait, fal_aspect_ratio, runway_ratio
_aspect = get_project_setting(ctx, "aspect_ratio", DEFAULT_ASPECT_RATIO)
```
(Module-top imports are fine if the file's convention prefers; the `_aspect` assignment must be in the enclosing scope so every branch + the closure sees it.)

- [ ] **Step 2: Verify no regression** — `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/ -q` stays green AND `ci_smoke.py` exit 0. (No behavior change yet; `_aspect` is first consumed in Task 3.)
- [ ] **Step 3: Commit** `refactor(video): hoist project aspect_ratio (_aspect) into generate_ai_video spine`

---

### Task 3: Veo native + fal 9:16

**Files:**
- Modify: `veo_native.py` (`generate_video` `:138` + thread to `_build` `:208`); `phase_c_ffmpeg.py` (`:277` native call pass-through; `:491` fal literal)
- Test: `tests/unit/test_veo_native_config.py` (extend); `tests/unit/test_phase_c_video_aspect.py` (fal branch)

- [ ] **Step 1: Failing tests.** (a) `test_veo_native_config.py` (TC-3 Veo): `cfg = _build_generate_videos_config(..., aspect_ratio="9:16"); assert cfg.aspect_ratio == "9:16"`. (b) `test_phase_c_video_aspect.py` (TC-4): drive `VEO_NATIVE` with portrait ctx → `assert mock_inst.generate_video.call_args.kwargs["aspect_ratio"] == "9:16"`. (c) fal VEO branch (TC-5): drive `VEO` (fal) → `arguments["aspect_ratio"] == "9:16"`; and a 16:9 refute (`== "16:9"`).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement.** `veo_native.generate_video`: append `aspect_ratio: str = "16:9"` LAST in the signature (`:138`); pass it into the `_build_generate_videos_config(...)` call (`:208`). `phase_c_ffmpeg.py:277`: add `aspect_ratio=fal_aspect_ratio(_aspect)` to the `veo.generate_video(...)` kwargs. `phase_c_ffmpeg.py:491`: replace `"aspect_ratio": "16:9"` with `"aspect_ratio": fal_aspect_ratio(_aspect)`.
- [ ] **Step 4: Run → PASS** (+ existing `test_veo_native_config.py:61` 16:9-default test still green).
- [ ] **Step 5: Commit** `feat(video): Veo native + fal emit 9:16 via fal_aspect_ratio`

---

### Task 4: Sora native + fal 9:16 (incl. landscape force-resize fix)

**Files:**
- Modify: `sora_native.py` (`RESOLUTION_MAP`/dims `:108-109`; force-resize `:111-120`, resize call `:115`); `phase_c_ffmpeg.py` (`:423` fal literal; `:249` native call threads aspect)
- Test: `tests/unit/test_sora_native.py` (extend); `tests/unit/test_phase_c_video_aspect.py` (fal branch)

- [ ] **Step 1: Failing tests.** (a) `test_sora_native.py` (TC-3 Sora): portrait `size` → `create_and_poll` receives `size="1080x1920"` (or the 720 portrait per U6) and the keyframe is NOT force-resized to landscape. (b) `test_phase_c_video_aspect.py` (TC-5): SORA_2 fal branch → `arguments["aspect_ratio"] == "9:16"` + 16:9 refute.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement.** `sora_native.generate_video`: thread the resolved aspect; apply `portrait_swap(target_w, target_h, aspect_ratio)` to the dims (`:108-109`); fix the force-resize (`:111-120`, resize call `:115`) to use the (possibly swapped) target dims, not the landscape `size`. `phase_c_ffmpeg.py:423`: literal → `fal_aspect_ratio(_aspect)`. `phase_c_ffmpeg.py:249`: thread aspect into `sora.generate_video(...)`. **U6:** if `sora-2` only yields 720p portrait, that's fine — §T8 upscales to 1080×1920; do NOT switch to `sora-2-pro` (cost) without a separate decision.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(video): Sora native + fal emit 9:16; fix landscape force-resize`

---

## Chunk 2: Runway + Kling + Routing safety

### Task 5a: Fix Runway `model="gen4"` (separate commit, pre-req for 5b)

**Files:** Modify `phase_c_ffmpeg.py:355` (RUNWAY_GEN4 route) · Test: `tests/unit/test_phase_c_video_aspect.py`

- [ ] **Step 1: Failing test** — grep the installed SDK for the valid enum first: `env -u GIT_INDEX_FILE .venv/bin/python -c "import runwayml, inspect; ..."` (or grep the SDK type stubs for `Literal[` model values). Write a test asserting the RUNWAY_GEN4 branch passes a model in the SDK's valid set (drive via TC-4, assert `mock_inst...call_args.kwargs["model"] in {"gen4_turbo","gen4.5"}`).
- [ ] **Step 2: Run → FAIL** (current `model="gen4"`).
- [ ] **Step 3: Implement** — replace `model="gen4"` (`:355`) with `gen4_turbo` (the installed runwayml SDK enum is `{gen3a_turbo, gen4.5, gen4_turbo}` — confirmed at plan-review; bare `gen4` is invalid). Re-grep the SDK to confirm at execution HEAD. Aspect-independent.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `fix(video): RUNWAY_GEN4 uses valid SDK model (gen4_turbo); bare 'gen4' not in SDK enum`

### Task 5b: Runway portrait ratios (both routes)

**Files:** Modify `phase_c_ffmpeg.py:363` (gen4), `:682` (gen3a_turbo) · Test: `test_phase_c_video_aspect.py`

- [ ] **Step 1: Failing tests** (TC-4): RUNWAY_GEN4 portrait → `ratio == "720:1280"`, landscape → `"1280:720"`; RUNWAY (gen3a) portrait → `"768:1280"`, landscape → `"1280:768"`.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — `:363` → `ratio=runway_ratio(_aspect, "gen4_turbo")`; `:682` → `ratio=runway_ratio(_aspect, "gen3a_turbo")` (use the same model literal each route actually passes).
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `feat(video): Runway both routes emit portrait ratio via runway_ratio`

---

### Task 6: Kling keyframe-provenance (no aspect param; keyframe-driven)

**Files:** Test `tests/unit/test_kling_native.py` (**NEW**, mirror `test_sora_native.py`); Modify `phase_c_ffmpeg.py` KLING_NATIVE branch (`:206-224`) only if adding a defensive log.

- [ ] **Step 1: Failing/characterization tests.** (a) `test_kling_native.py` (TC-3, **note TC-7 pattern B** — Kling caches `settings.kling_access_key/secret_key` at `__init__`, so override instance attrs): assert `KlingNativeAPI.generate_video` builds its payload with **no** aspect/ratio/size key (capability is keyframe-driven; documents the contract). (b) `test_phase_c_video_aspect.py`: a **defensive-log** test — drive KLING_NATIVE with a portrait ctx but a landscape `source_image` (mock `probe_final_media`/`os.path` to report landscape dims) → assert a warning is logged (the leak-catch). If the team prefers no log, this becomes a doc-only characterization test.
- [ ] **Step 2: Run → FAIL** (test_kling_native.py new; defensive log not present).
- [ ] **Step 3: Implement** — `test_kling_native.py` is mostly characterization (no production change for the payload). For the defensive log: in the KLING_NATIVE branch, if `is_portrait(_aspect)` and the keyframe probes landscape, `logger.warning("[ASPECT] portrait project but landscape keyframe for Kling i2v — output will be 16:9")`. (Belt-and-suspenders; the §T7 backstop is the real net.)
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `test(video): Kling keyframe-driven 9:16 contract + landscape-keyframe warning`

---

### Task 7: Portrait routing safety — cascade filter + post-gen aspect backstop

**Files:** Modify `phase_c_ffmpeg.py` (`generate_ai_video` `:126-170`: the `fallback_list` build + the cascade success path) · Test: `test_phase_c_video_aspect.py`

- [ ] **Step 1: Failing tests** (the most novel — green-field cascade tests, TC-4 + TC-8):
  1. **Filter:** with a portrait ctx, build a fallback list including a non-shipped provider (e.g. `LTX`/`SEEDANCE`) → assert it is **excluded** from the portrait cascade (the non-shipped provider's mock is never constructed/called).
  2. **Backstop reject-retry:** drive a portrait cascade where provider A's mocked `generate_video` returns a **landscape** clip (mock `probe_final_media` → `FFPROBE` landscape dims) and provider B returns portrait → assert **B's mock is called** (A's wrong-orientation result was rejected → `try_next_api`).
  3. **Terminal fail-loud:** all providers return landscape → assert `generate_ai_video` returns `None` (cascade exhausts; no landscape clip returned).
  4. **16:9 unaffected:** landscape ctx → no filtering, no rejection (refute).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement.**
  - **Filter:** the `fallback_list` build lives **inside the `try_next_api()` closure** (~:124); mirror the existing `enabled`-filter at `:135-143` (review-corrected location). When `is_portrait(_aspect)` (captured from the enclosing spine scope — Task 2 placed `_aspect` before the closure), drop providers not in the portrait-capable set `{VEO_NATIVE, VEO, SORA_NATIVE, SORA_2, KLING_NATIVE, KLING, RUNWAY_GEN4, RUNWAY}` (exclude LTX*, SEEDANCE, Hedra). Define the set as a module constant near the top.
  - **Backstop:** factor a small helper `def _accept_or_reject(result, _aspect) -> bool` that probes `result` via `probe_final_media` and returns False when `is_portrait(_aspect) != (height > width)`. Apply it on each provider's success path so a wrong-orientation clip routes to `try_next_api()` instead of `return result` (the plan author picks: wrap the per-provider `return result` at `:227/:266/:294`, or — preferred — a single guard at the cascade's return boundary to avoid duplication). Terminal: unchanged — `try_next_api` chain exhausts to `return None` (`:170`).
- [ ] **Step 4: Run → PASS** + full suite green.
- [ ] **Step 5: Commit** `feat(video): portrait routing safety — cascade filter + post-gen aspect backstop`

---

## Chunk 3: Upscale + Preflight + Un-gate

### Task 8: Sub-1080 upscale verification (Runway + Sora-720p)

**Files:** Verify `cinema_pipeline.py` assembly normalize (`:1320`, scale filter `:45`) · Test: `tests/unit/test_phase_c_video_aspect.py` or a normalize-focused test

- [ ] **Step 1: Failing/characterization test** (TC-8): feed the normalize path a 720×1280 (and 768×1280) portrait clip dims → assert the output is normalized to **1080×1920** (the scale filter upscales-to-container). Mock `ffprobe`/`subprocess.run` per TC-8; assert the ffmpeg scale args target 1080×1920 (or, if a real-ffmpeg gate is acceptable, use the `@skipUnless(shutil.which("ffmpeg"))` pattern).
- [ ] **Step 2: Run → FAIL** (if a gap exists) or PASS-as-characterization (if normalize already covers it — then this task is verification + a regression test, no prod change).
- [ ] **Step 3: Implement** — only if a gap: ensure `resolve_output_dimensions("9:16")=(1080,1920)` flows into the scale filter for sub-1080 inputs. Likely **no prod change** (the container dims already drive normalize); the deliverable is the regression test.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** `test(assembly): verify sub-1080 portrait (Runway/Sora-720p) upscales to 1080x1920`

---

### Task 9: On-pod portrait preflight harness

**Files:** Create `scripts/_phase3_portrait_preflight.py` (mirror `scripts/_veo_from_keyframe.py` + `scripts/_max_harness_preflight.py`)

- [ ] **Step 1: Write the script** (no TDD test — it's a live dev harness; the convention is `_`-prefixed, not unit-tested). Shape:
  - Shebang + docstring stating step, **live API spend**, usage.
  - `sys.path.insert(0, repo_root)`; import the production provider paths + `config.settings`.
  - For each shipped provider (Veo, Sora, Kling, Runway): generate **one** 9:16 clip from a provided 9:16 keyframe (CLI arg, default to a known portrait keyframe).
  - Local `ffprobe_streams(path)` helper (copy from `_veo_from_keyframe.py:31-42`); assert `height > width`.
  - **Also** the SPEC-3 schnell smoke: a live FAL schnell `image_size="portrait_16_9"` generation, ffprobe the result is portrait.
  - Accumulate `problems = []`; print a PASS/FAIL table per provider; `sys.exit(len(problems))`.
- [ ] **Step 2: Manual run** (USER/operator, live spend): `env -u GIT_INDEX_FILE .venv/bin/python scripts/_phase3_portrait_preflight.py [keyframe]` → expect all-PASS table, exit 0. Capture the output.
- [ ] **Step 3: Commit** `feat(scripts): _phase3_portrait_preflight — live 9:16 per-provider + schnell enum smoke`

---

### Task 10: Un-gate `SUPPORTED_ASPECT_RATIOS` (LAST — hard-gated on T9 PASS)

**Files:** Modify `cinema/aspect.py:23` · Test: flip `tests/unit/test_cinema_aspect.py:29-32`; `tests/unit/test_web_server_aspect_validation.py`

**PRECONDITION:** T9 preflight ran live and returned all-PASS (exit 0). Paste its output into this commit body (ADR-013 evidence). **Do not land T10 without it.**

- [ ] **Step 1: Flip the failing tests.** `test_cinema_aspect.py`: rename/rewrite `test_is_supported_gate_excludes_9_16_until_phase3` → `test_is_supported_gate_includes_9_16` asserting `is_supported("9:16") is True` (and `"4:3"` still False). `test_web_server_aspect_validation.py`: a 9:16 settings PUT now **persists** (no 400).
- [ ] **Step 2: Run → FAIL** (gate still `["16:9"]`).
- [ ] **Step 3: Implement** — `cinema/aspect.py:23` → `SUPPORTED_ASPECT_RATIOS: list[str] = ["16:9", "9:16"]`.
- [ ] **Step 4: Run → PASS** + full suite green + `ci_smoke.py` exit 0.
- [ ] **Step 5: Commit** `feat(aspect): un-gate 9:16 — portrait delivery live (preflight PASS in body)` with the T9 PASS table pasted in the body.

---

## Execution Notes

- **Ordering is an invariant:** T1→T2→T3→T4→T5a→T5b→T6→T7→T8→T9→**T10 last**. T10 must not land before T9's live PASS (else a 9:16 project gets portrait container + landscape clips). T5a precedes T5b (a working Runway route is needed to wire/validate ratios).
- **Subagent-driven execution** (CLAUDE.md): baseline commit any prep first; one implementer per task → spec reviewer (reads the diff, not the self-report) → code-quality reviewer; fix-loops as separate commits. Carry the **Project Conventions** block + the relevant **TC-** patterns into each implementer prompt. The operator runs **independent Lane V** (Rule #9) per feat-commit in parallel.
- **Pre-ship enum checks (decision #5)** are verify-then-wire inside T3 (fal veo3.1 `9:16` spelling), T4 (Sora `sora-2` 1080p tier / U6), folded — not separate tasks.
- **Opportunistic cleanups (operator CC-1 INFO-1/PLUMB-5)** only if a task touches `_inject_aspect`/the production swap sites; not standalone.
- **Final:** after T10, cross-cutting review (BASE=baseline, HEAD=T10), update `ARCHITECTURE.md §8.x` (Lane D / same PR), then `superpowers:finishing-a-development-branch`.
