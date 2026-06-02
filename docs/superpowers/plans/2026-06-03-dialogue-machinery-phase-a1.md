# Dialogue Machinery — Phase A.1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lock in and document the dialogue machinery this session built — add characterization tests for the new `hedra_native.py`, and correct the two stale-doc claims this session's work created.

**Architecture:** Three independent tasks. Task 1 + Task 2 are doc-truth fixes (no code, verified by `ci_smoke.py`'s `check_doc_claims` anchor gate). Task 3 adds offline ($0) characterization tests for the existing `hedra_native.py` using mocked `requests` + `time.sleep` — these validate the module works (PASS) or reveal a bug (FAIL → ticket); this is the "find what works/doesn't" core for one component.

**Tech Stack:** Python 3.13, pytest, `monkeypatch` (stdlib, no new deps), `requests` (mocked).

**Source spec:** `docs/superpowers/specs/2026-06-02-program-test-audit-plan-design.md` (Part 1 `hedra_native` blind spot + Part 3 stale-doc fixes). This is **Plan 1 of a sequence**; Plan 2 covers the remaining zero-test components (`identity/validator`, `style_director`, `sora/ltx_native`, `phase_c_vision`) after an interface survey; later plans cover prune verification, the Veo+overlay routing wire, and the bigger fixes.

**Branch:** `feat/max-tier-provisioning` @ `620e81f`. **Working-tree note:** unrelated uncommitted state exists (modified `pulid_max.json`, `workflow_selector.py`; untracked `scripts/_*.py`, `logs/`). Every commit below uses **explicit pathspec** — never `git add -A` / bare `git commit`.

**Key gotcha (plan-reviewed):** `config/settings.py` declares `@dataclass(frozen=True) class Settings`, so the `settings` singleton **cannot be monkeypatched** (`FrozenInstanceError`). Task 3 injects the API key on the `HedraAPI` *instance* instead (the `_api()` helper). Do not try to patch `settings`.

---

## Chunk 1: Dialogue machinery tests + doc fixes

### Task 1: Fix the `storyboard_mode` stale-manifest claim

The F2b slice wired `storyboard_mode` (`cinema/phases/motion_render.py`: `_get_storyboard_mode`:45 gates `_run_storyboard_scene`:100 → `KlingNativeAPI.generate_storyboard`), with coverage in `tests/unit/test_f2b_storyboard_mode.py`. But `docs/pipeline_status.toml` still says `status="stubbed"` / "zero callers / toggle does nothing." Correct it.

**Files:**
- Modify: `docs/pipeline_status.toml` (the `storyboard_mode` component block, ~lines 40-44)
- Modify: `docs/PROGRAM-MANUAL.md` (§5.3A storyboard claim — read it first; correct only the stale "stubbed/does-nothing" wording)

- [ ] **Step 1: Verify the wiring is real at HEAD** (don't trust this plan blindly)

Run: `grep -n '_get_storyboard_mode\|_run_storyboard_scene\|generate_storyboard' cinema/phases/motion_render.py`
Expected: `_get_storyboard_mode` def (~:45) + `_run_storyboard_scene` (~:100) + a `generate_storyboard(` call (~:170). If absent, STOP and report — the manifest may be correct.

- [ ] **Step 2: Update the manifest entry**

In `docs/pipeline_status.toml`, the `storyboard_mode` block, change:
```toml
status = "stubbed"
anchor = "kling_native.py:generate_storyboard"
note = "§10 F-A.1: 135 LoC, zero callers; UI toggle `storyboard_mode` is never read by phase_c_ffmpeg.py, so the toggle does nothing. Cycle-17+ wire candidate (brief P1-5)."
```
to:
```toml
status = "wired"
anchor = "cinema/phases/motion_render.py:_run_storyboard_scene"
note = "F2b wired it: motion_render._get_storyboard_mode (:45) gates _run_storyboard_scene (:100) -> KlingNativeAPI.generate_storyboard. Covered by tests/unit/test_f2b_storyboard_mode.py."
```
(`status="wired"` is a valid enum — already used by other components in this file.)

- [ ] **Step 3: Correct the manual §5.3A storyboard claim**

`grep -n 'storyboard' docs/PROGRAM-MANUAL.md` → read the §5.3A passage → correct only the stale "stubbed / toggle does nothing" wording to "wired via motion_render (F2b)". Do not rewrite unrelated prose.

- [ ] **Step 4: Verify doc-claim anchors still pass**

Run: `.venv/bin/python scripts/check_doc_claims.py 2>&1 | tail -5` then `.venv/bin/python scripts/status.py 2>&1 | grep -i storyboard`
Expected: no anchor errors; storyboard shows `wired ... @100`.

- [ ] **Step 5: Commit (explicit pathspec)**

```bash
git commit -m "docs(status): storyboard_mode is wired (F2b), not stubbed" -- docs/pipeline_status.toml docs/PROGRAM-MANUAL.md
```

---

### Task 2: Document `hedra_native.py` in ARCHITECTURE.md §10.6

§10.3 documents the old driving-video Hedra paths; §10.6 (Lipsync, `lip_sync.py`) does NOT mention the new GENERATION-cascade ATTEMPT-0 — direct `api.hedra.com/web-app/public` Character-3 via `hedra_native.py` (`cb31207`), which replaced the dead `fal-ai/hedra/character-3` (HTTP 404).

**Files:**
- Modify: `ARCHITECTURE.md` §10.6 (around line 1067, the `lip_sync.py` lipsync section)

- [ ] **Step 1: Read §10.6 and the generation cascade**

Read `ARCHITECTURE.md` lines 1067–1110 (use the Read tool, not `sed`/`cat`). Then run `grep -n 'HedraAPI\|hedra_native\|ATTEMPT 0' lip_sync.py`.
Confirm §10.6's generation-cascade table lists order-0 as the dead `fal-ai/hedra/character-3` and does NOT mention `hedra_native`/`api.hedra.com`, and that `lip_sync.py` imports `HedraAPI` (~:39) + calls it (~:559).

- [ ] **Step 2: Add the hedra_native note to §10.6**

In §10.6, document the generation cascade's ATTEMPT-0: `hedra_native.HedraAPI.generate_talking_head` → direct `api.hedra.com/web-app/public` (Character-3 model `d1dd37a3-…`), replacing the dead `fal-ai/hedra/character-3` proxy (wired `cb31207`); falls through to Kling → Omnihuman → Creatify. Match the table/prose style already in §10.6. Update the file-level `*Last verified:*` footer date.

- [ ] **Step 3: Verify the doc-anchor smoke passes**

Run: `.venv/bin/python scripts/ci_smoke.py 2>&1 | tail -3`
Expected: `OK` (ci_smoke runs `check_doc_claims.run(["ARCHITECTURE.md"])`).

- [ ] **Step 4: Commit (explicit pathspec)**

```bash
git commit -m "docs(arch): document hedra_native direct Character-3 as lipsync ATTEMPT-0 (§10.6)" -- ARCHITECTURE.md
```

---

### Task 3: Characterization tests for `hedra_native.py`

`hedra_native.py` (172 LoC, `cb31207`) has **zero tests**. Add offline tests covering all 7 branches of `HedraAPI.generate_talking_head` with mocked `requests` + `time.sleep`. **These test EXISTING code** — they should PASS (validating the module); a FAIL reveals a real bug → file a ticket, do not "fix the test."

**Key technique:** `settings` is a **frozen dataclass** and cannot be monkeypatched. `HedraAPI.__init__` reads `settings.hedra_api_key` into `self._key`; the empty-key guard checks `self._key`. So inject the key on the **instance** via the `_api()` helper below (verified during plan review to pass). Mock the module-level `requests`/`time` (`import requests`/`import time` at top of `hedra_native.py`).

**Files:**
- Create: `tests/unit/test_hedra_native.py`
- Reference (read-only): `hedra_native.py` (the code under test)

- [ ] **Step 1: Write the test file**

```python
# tests/unit/test_hedra_native.py
"""Characterization tests for hedra_native.HedraAPI (offline, mocked HTTP).
Validate the existing module's success + every graceful-failure branch."""
import hedra_native
from hedra_native import HedraAPI


class _Resp:
    """Minimal fake requests.Response."""
    def __init__(self, status_code=200, json_data=None, content=b""):
        self.status_code = status_code
        self._json = json_data or {}
        self.content = content
        self.text = ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


def _api(key="sk_test_xxx"):
    """Build a HedraAPI with an injected key. `settings` is a FROZEN dataclass
    (config/settings.py: @dataclass(frozen=True)) so it cannot be monkeypatched;
    HedraAPI reads settings.hedra_api_key into self._key at construction, so we
    override the instance attribute instead."""
    api = HedraAPI()
    api._key = key
    api._headers = {"x-api-key": key}
    return api


def _files(tmp_path):
    img = tmp_path / "i.jpg"; img.write_bytes(b"img")
    aud = tmp_path / "a.mp3"; aud.write_bytes(b"aud")
    out = tmp_path / "o.mp4"
    return str(img), str(aud), str(out)


def test_empty_key_returns_none(tmp_path):
    img, aud, out = _files(tmp_path)
    assert _api(key="").generate_talking_head(img, aud, out) is None


def test_missing_image_returns_none(tmp_path):
    _, aud, out = _files(tmp_path)
    assert _api().generate_talking_head(str(tmp_path / "nope.jpg"), aud, out) is None


def test_missing_audio_returns_none(tmp_path):
    img, _, out = _files(tmp_path)
    assert _api().generate_talking_head(img, str(tmp_path / "nope.mp3"), out) is None


def test_happy_path_writes_output(monkeypatch, tmp_path):
    img, aud, out = _files(tmp_path)
    monkeypatch.setattr(hedra_native.time, "sleep", lambda *_: None)
    posts = iter([
        _Resp(json_data={"id": "img-asset"}),   # POST /assets (image)
        _Resp(),                                 # POST /assets/{id}/upload (image)
        _Resp(json_data={"id": "aud-asset"}),    # POST /assets (audio)
        _Resp(),                                 # POST /assets/{id}/upload (audio)
        _Resp(json_data={"id": "gen-1"}),        # POST /generations
    ])
    gets = iter([
        _Resp(json_data={"status": "complete", "download_url": "http://x/v.mp4"}),  # /status
        _Resp(content=b"VIDEOBYTES"),            # download GET
    ])
    monkeypatch.setattr(hedra_native.requests, "post", lambda *a, **k: next(posts))
    monkeypatch.setattr(hedra_native.requests, "get", lambda *a, **k: next(gets))
    res = _api().generate_talking_head(img, aud, out)
    assert res == out
    with open(out, "rb") as f:
        assert f.read() == b"VIDEOBYTES"


def test_generation_rejected_returns_none(monkeypatch, tmp_path):
    img, aud, out = _files(tmp_path)
    monkeypatch.setattr(hedra_native.time, "sleep", lambda *_: None)
    posts = iter([
        _Resp(json_data={"id": "img-asset"}), _Resp(),
        _Resp(json_data={"id": "aud-asset"}), _Resp(),
        _Resp(status_code=400),                  # POST /generations rejected
    ])
    monkeypatch.setattr(hedra_native.requests, "post", lambda *a, **k: next(posts))
    assert _api().generate_talking_head(img, aud, out) is None


def test_status_error_returns_none(monkeypatch, tmp_path):
    img, aud, out = _files(tmp_path)
    monkeypatch.setattr(hedra_native.time, "sleep", lambda *_: None)
    posts = iter([
        _Resp(json_data={"id": "img-asset"}), _Resp(),
        _Resp(json_data={"id": "aud-asset"}), _Resp(),
        _Resp(json_data={"id": "gen-1"}),
    ])
    monkeypatch.setattr(hedra_native.requests, "post", lambda *a, **k: next(posts))
    monkeypatch.setattr(hedra_native.requests, "get",
                        lambda *a, **k: _Resp(json_data={"status": "error", "error_message": "boom"}))
    assert _api().generate_talking_head(img, aud, out) is None


def test_timeout_returns_none(monkeypatch, tmp_path):
    img, aud, out = _files(tmp_path)
    monkeypatch.setattr(hedra_native.time, "sleep", lambda *_: None)
    posts = iter([
        _Resp(json_data={"id": "img-asset"}), _Resp(),
        _Resp(json_data={"id": "aud-asset"}), _Resp(),
        _Resp(json_data={"id": "gen-1"}),
    ])
    monkeypatch.setattr(hedra_native.requests, "post", lambda *a, **k: next(posts))
    monkeypatch.setattr(hedra_native.requests, "get",
                        lambda *a, **k: _Resp(json_data={"status": "processing"}))  # never completes
    assert _api().generate_talking_head(img, aud, out) is None
```

- [ ] **Step 2: Run the tests — expect PASS (validates the module)**

Run: `.venv/bin/python -m pytest tests/unit/test_hedra_native.py -v`
Expected: **7 passed.** If any FAIL, that is a real `hedra_native` bug — capture the failure, file a ticket in the spec's Part-3 fix list, and surface it; do NOT weaken the test to make it pass.

- [ ] **Step 3: Confirm no collateral breakage**

Run: `.venv/bin/python scripts/ci_smoke.py 2>&1 | tail -2`
Expected: `OK`.

- [ ] **Step 4: Commit (explicit pathspec)**

```bash
git commit -m "test(hedra): characterization tests for hedra_native.HedraAPI (7 branches, mocked HTTP)" -- tests/unit/test_hedra_native.py
```

---

## Done criteria

- `storyboard_mode` shows `wired` in `pipeline_status.toml` + the manual; ARCHITECTURE §10.6 documents `hedra_native`; `ci_smoke.py` → `OK`.
- `tests/unit/test_hedra_native.py` → 7 passed (or any FAIL filed as a Part-3 bug ticket).
- Three commits, each pathspec-scoped; unrelated working-tree state untouched.
- Then proceed to **Plan 2** (interface survey → `identity/validator` + `style_director` + remaining zero-test components).
