# R-BRIEF — Pair-B Tier 3: Audio DSP (voice-FX router & voice-direction resolver)

Seat: `director2` · Date: `2026-06-27` · Lane: Pair-B (video/assembly/audio)
Source directive: `coordination/mailbox/sent/2026-06-26T23-10-00Z-coordinator-to-all-coordination.md`
Spec: `docs/TEST-COVERAGE-ANALYSIS-2026-06-14.md` §4 Tier 3 (Audio DSP)
Reviewer: `operator2` (impl ≠ verifier) — `env -u GIT_INDEX_FILE pytest tests/unit/`

PRIORITY: MEDIUM   LANE: B (video/assembly/audio)
CROSS-CUTTING: **no** — targets `audio/effects.py` + `audio/voiceover.py`, neither is one
of the four lock modules (`auto_approve.py · cinema/context.py · core.py · web_server.py`).
→ **lane-only → NO lock.** (Test-only additions; even the production files are not edited.)

## Gate status — DO NOT DISPATCH YET

This brief is **authored and held**. Per the directive ("Once Tier 2 is stable, move to
Tier 3") and director2's own verify-request (`c9411ab6`), Tier 3 does not begin until
**operator2 returns the Tier-2 per-component GO**. At author time the Tier-2 batch
(`2e56f077`→`ade1ca4c`) is dispatched and awaiting operator2 Lane-V. Dispatch this brief
only after that GO lands; push remains user-gated.

## Scope & classification

Test-only additions — two **new** files (`tests/unit/test_effects.py`,
`tests/unit/test_voiceover.py`; neither exists today, verified `ls tests/unit/`). No
production edit, no spend, no network, no pod, no dependency edit. Characterization tests
of *correct current behavior* — green expected; any genuine defect surfaced ships a
`pytest.mark.xfail(strict=True, reason=…)` pin (R-VERIFY-TIER), not a silent skip.

Mode: **implement directly OR single implementer** — 2 targets, ≪5 sub-tasks and ≪800 LOC,
so **below the R-ORCH threshold**; no orchestration. Operator2 verifies BASE..HEAD per file.

## Test-infra prerequisite (dispatch-readiness, verified)

`audio/effects.py:20` hard-imports `pedalboard` at module top (the module docstring states
it is a hard dependency with *no* graceful fallback). Test collection therefore imports it.
- `$ .venv/bin/python -c "import pedalboard; print(pedalboard.__version__)"` → `0.9.23` (installed locally).
- CI safety: `test_effects.py` must open with `pytest.importorskip("pedalboard")` at module
  top — mirrors the repo R2 convention already used for `cv2` in `test_coherence_analyzer.py`
  (cited in the Tier-2 brief). `audio/voiceover.py` has no heavy import → no skip needed.

## Rule #12 evidence — every target read at its runtime branch (not type decl)

| # | Target (live file:line) | Branches under test (the gap) | Pin (mocked surface in parens) |
|---|---|---|---|
| 1 | `effects.apply_voice_effect` `audio/effects.py:230` | router priority **AU > Pedalboard > FFmpeg** `:248-284`. Sentinel: each engine returns the **original `audio_path` (identity)** on no-op/failure, and the router only short-circuits when `result != audio_path` (`:251,257`). | (mock `apply_au_plugin`/`apply_pedalboard_chain`/`subprocess.run`/`os.path`) — **(a)** `au_plugin` set + helper returns a new path → returns that path, Pedalboard+FFmpeg **not** reached; **(b)** `au_plugin` set but helper returns `audio_path` → **falls through** to next engine; **(c)** `pedalboard_chain` set, AU absent → Pedalboard path; **(d)** `effect="none"` → returns `audio_path` unchanged `:261-262`; **(e)** `effect` not in `VOICE_EFFECTS` → returns `audio_path` `:261-262`; **(f)** valid effect, ffmpeg writes non-empty output → returns `output_path` `:277-279`; **(g)** ffmpeg runs but output missing/0-byte → returns `audio_path` `:280`; **(h)** `subprocess.run` raises → caught `:282-284`, returns `audio_path` (**never propagates**). |
| 2 | `voiceover.get_voice_direction` `audio/voiceover.py:284` | `delivery.lower().strip()` `:291`; exact `:294-295`; fuzzy substring `:298-300`; default `:303`. | pure fn, no mocks — **(a)** exact key (e.g. `"natural"`) → that profile; **(b)** case/whitespace (`"  WHISPER "`) → same as `"whisper"` (lower+strip); **(c)** fuzzy substring (`"he said softly, whispering"` contains key `"whisper"`) → whisper profile; **(d)** unknown (`"zzz-nonsense"`) → returns `VOICE_DIRECTIONS["natural"]`, **not** `KeyError` `:303`; **(e)** returned dict carries `stability/similarity/style/speaker_boost`; `markup` is **optional** (present on 5/40 profiles — `whisper,hushed,confessional,angry,furious`; verified) so a caller must not assume it. |

**Defensive/unreachable branch — do NOT contrive a test:** `apply_voice_effect:265` (`if not
filter_chain: return audio_path`) is unreachable via the shipped presets — the only preset
with `filter=None` is `"none"`, already returned at `:261`. Verified:
`$ python -c "from audio.effects import VOICE_EFFECTS as v; print([k for k,d in v.items() if d.get('filter') is None])"` → `['none']`.
Note the branch as defensive in a test comment; do not fabricate an unreachable-path test.

## Rule #13 — sibling branches each test must also cover

- **#1 router ↔ its two helpers** (`apply_au_plugin` `:88`, `apply_pedalboard_chain` `:156`):
  all three share **one contract — never raise; return the original `audio_path` on any
  failure** (each wraps the body in `try/except Exception → return audio_path`:
  `:151-153`, `:213-215`, `:282-284`). The router's short-circuit (`result != audio_path`)
  is *coupled* to that identity-sentinel, so the fall-through cases (b)/(c) above are the
  symmetric guard — assert the helpers' own never-raise contract directly too:
  `apply_au_plugin` plugin-not-found → returns `audio_path` `:122-124`;
  `apply_pedalboard_chain` empty `effects` → `audio_path` `:176-177`, and unknown fx types
  filtered to empty `chain` → `audio_path` `:197-198`. A future engine added to the router
  must preserve this sentinel or the priority logic silently breaks.
- **#2 resolver ↔ `DELIVERY_STYLES`** (`voiceover.py:307 = sorted(VOICE_DIRECTIONS.keys())`):
  the fuzzy loop iterates `VOICE_DIRECTIONS` in **insertion order** while `DELIVERY_STYLES`
  is **alphabetical** — so fuzzy-match precedence is NOT alphabetical. Pin a delivery string
  containing two keys and assert the **insertion-order-first** key wins, so a future dict
  reorder can't silently change which profile a phrase resolves to. Also note `voiceover.py:18`:
  `VOICE_DIRECTIONS` is re-exported through `web_server.py` for the UI — the returned dict
  **shape** is a cross-surface contract; assert the four always-present keys so a profile edit
  that drops one is caught here, not in the UI.

## Per-target dispatch (new file; mirror existing audio-test fixtures/style)

| # | Implementer writes | Mirror |
|---|---|---|
| 1 | `tests/unit/test_effects.py` (NEW) | `pytest.importorskip("pedalboard")` top; `unittest.mock.patch` of `audio.effects.subprocess.run` / `os.path.exists` / `os.path.getsize` / the two helpers — mock style as in `test_kling_native.py`/`test_ltx_native.py` |
| 2 | `tests/unit/test_voiceover.py` (NEW) | pure-function asserts; no mocks; style as in existing `tests/unit/test_*` value-table tests |

Acceptance per target: new tests **green** under
`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_<x>.py -q`;
**one clean commit per file** (operator2 verifies BASE..HEAD per component), exact pathspecs
only (the shared tree carries unrelated untracked files — never `git add -A`).

## Verification the operator2 / CI will run

```
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_effects.py tests/unit/test_voiceover.py -q
```
Expect all green (characterization of correct behavior). operator2 confirms per component:
the pinned branch matches the live function, crash paths (`apply_voice_effect` with ffmpeg
raising; `get_voice_direction` on unknown delivery) raise **no** unexpected exception, then
issues GO/NITS/FAIL per file. impl ≠ verifier — operator2's independent run is the GO gate.

## Sequencing

Tier 2 (`docs/superpowers/briefs/2026-06-27-testcov-pairb-tier2.md`) must be operator2-stable
first. This Tier 3 brief completes the Pair-B half of the coordinator test-coverage directive;
no Tier 4 for Pair-B. Push user-gated throughout.
