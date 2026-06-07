# U3 — Final-media conformance (audio LUFS + format) on the Capability Scorecard

*Status: user-approved design (2026-06-07). Operator-seat, design-first.*
*Origin: handoff `docs/HANDOFF-operator-transplant-2026-06-07-t6-shipped-merged-pushed.md` NEXT #1 (carried from the Part-4 brainstorm).*

## 1. Problem

The Capability dashboard (Part 4) declares `audio_lufs` and `format_codec` as
`future_dimensions` (`cinema/capability_scorecard.py:109`) and renders them as
greyed/dashed placeholder tiles (`web/src/components/console/CapabilityConsole.tsx:62-72`).
The pipeline already *normalizes* the final mp4 to −14 LUFS via two-pass EBU R128
(`phase_c_ffmpeg.py::two_pass_loudnorm`, applied by
`cinema_pipeline.py::_apply_final_loudnorm`) but **discards the measurements** and
never verifies the delivered artifact. Nothing measures whether `final_cinema.mp4`
actually conforms to the delivery bar: −14 LUFS ±1 LU, 1920×1080, h264 video +
aac audio.

## 2. Decisions (user-adjudicated)

| Fork | Decision | Why |
|---|---|---|
| When to measure | **Assembly-time, persist on the project** | Scorecard builder stays pure (its documented contract: "No mutation, no Flask"); GET stays fast. A LUFS measure is a full audio decode (~seconds) — wrong cost for a dashboard GET. Already-assembled projects show "— not measured" until their next (re)assembly. |
| Payload shape | **New `media` section on the scorecard** | LUFS (target −14, pass = within ±1 LU) and codec conformance (boolean) don't fit the `CapabilityDimension` contract (`pass = value >= bar`, 0–1 values, progress bar). Forcing them in would display opaque synthetic numbers. |

Measurement is **ground truth on the artifact**: probe whatever file ends up as
`final_cinema.mp4` *after* the loudnorm step, whether loudnorm succeeded or not.
If loudnorm silently failed, the tile shows the real off-target value — that is
the scorecard's job.

## 3. Architecture / data flow

```
_assemble_final (cinema_pipeline.py:1245)
  └─ _apply_final_loudnorm(final_output)        ← single hook point: all 3 loudnorm
       │                                           call sites are inside _assemble_final,
       │                                           each immediately before `return`.
       ├─ two_pass_loudnorm(...)                  existing — unchanged behavior
       ├─ NEW probe_final_media(final_path)       phase_c_ffmpeg.py
       └─ NEW persist via mutate_project          project["media_report"]

GET /api/projects/<pid>/capability-scorecard (web_server.py:488)
  └─ build_capability_scorecard(project, project_dir)
       └─ reads project["media_report"] → "media" block  (pure; no subprocess)

CapabilityConsole.tsx
  └─ sc.media → two real tiles; dashed placeholders when sc.media is null
```

## 4. Components

### 4.1 `phase_c_ffmpeg.py` — measurement helpers

- **Extract `measure_loudness(path) -> dict | None`** from `two_pass_loudnorm`'s
  pass-1 (the ffmpeg `loudnorm=...print_format=json` run + the stderr JSON
  regex parse + required-keys check). `two_pass_loudnorm` calls it; behavior
  unchanged (same command, same timeout 180s, same `None`/skip semantics).
- **New `probe_final_media(path) -> dict | None`:**
  - `ffprobe -v error -show_streams -show_format -of json <path>` → first video
    stream (`codec_name`, `width`, `height`), first audio stream (`codec_name`),
    `format.duration`.
  - `measure_loudness(path)` → `input_i` (integrated LUFS of the file as-is),
    `input_tp`, `input_lra`.
  - Returns
    ```python
    {"audio": {"integrated_lufs": float, "true_peak_dbtp": float, "lra": float},
     "format": {"width": int, "height": int, "vcodec": str, "acodec": str,
                "duration_s": float}}
    ```
    Partial results: if exactly one half succeeds (ffprobe XOR loudness),
    return the dict with the failed half absent — the scorecard renders each
    half independently. Return `None` only when the file is missing or BOTH
    halves fail.

### 4.2 `cinema_pipeline.py::_apply_final_loudnorm` — probe + persist

After the existing normalize-and-replace (and equally on the loudnorm-failed
path):

```python
report = probe_final_media(final_path)
if report:
    report["loudnorm_applied"] = normed_ok          # bool from two_pass_loudnorm
    report["measured_at"] = utcnow-iso
    mutate_project(project_id, _persist_media_report, timeout=10,
                   snapshot=self.project)            # inner model_validate, mirrors :948
```

- Probe/persist failure → `logger.warning`, **assembly outcome unaffected**.
- Every reassembly funnels through the same hook → the report can't go stale
  (it is overwritten on each new `final_cinema.mp4`).

### 4.3 `domain/models.py` — schema

No change needed: `Project` uses `ConfigDict(extra="allow")` (permissive by
design; verified at `domain/models.py:9,:29` during spec review), so the new
`media_report` key passes the inner-validate untouched.

### 4.4 `cinema/capability_scorecard.py` — `media` block

```python
"media": {                       # None when no media_report on the project
  "lufs":   {"value": -14.1, "target": -14.0, "tolerance": 1.0, "pass": True},
  "format": {"width": 1920, "height": 1080, "vcodec": "h264", "acodec": "aac",
             "pass": True},
  "measured_at": "...",
},
"future_dimensions": ["pod_health", "budget"],   # audio_lufs + format_codec graduate out
```

- `lufs.pass = abs(value - target) <= tolerance`; constants
  `LUFS_TARGET = -14.0`, `LUFS_TOLERANCE = 1.0` (streaming-platform window;
  matches `two_pass_loudnorm`'s default target).
- `format.pass = vcodec == "h264" and acodec == "aac" and (width, height) == (1920, 1080)`;
  constants `EXPECTED_RESOLUTION = (1920, 1080)`, `EXPECTED_VCODEC/ACODEC`.
- Either half absent from the persisted report → that sub-block is `None`,
  the other still renders (`media` itself only `None` when no report at all).
- `loudnorm_applied` and the raw `true_peak_dbtp`/`lra`/`duration_s` stay
  **audit-only on the persisted report** — deliberately NOT in the `media`
  payload (the off-target LUFS value tells the story; don't widen the contract).
- Malformed report (non-dict, wrong types) → `media: None` + debug log; never
  raises (mirror the builder's existing defensive style).

### 4.5 Frontend

- `web/src/types/project.ts`: extend `CapabilityScorecard` with a typed `media`
  field (no `any` — the T6 deferred-minor lesson). Sub-blocks nullable per §4.4.
- `web/src/components/console/CapabilityConsole.tsx`: where the greyed
  `audio_lufs` / `format_codec` tiles render today, render real tiles from
  `sc.media`:
  - **AUDIO LUFS** tile: `−14.10 LUFS` big-number + `target −14 ±1` sub-line,
    pass/fail colored like the existing dimension tiles, no progress bar.
  - **FORMAT** tile: `1920×1080` big-number + `h264+aac` sub-line, pass/fail
    colored.
  - `sc.media` (or a sub-block) null → dashed/greyed placeholder identical to
    the current future-dimension style.
  - Remaining `future_dimensions` (`pod_health`, `budget`) keep rendering
    generically, unchanged.

## 5. Error handling

| Failure | Behavior |
|---|---|
| ffprobe or loudness measure fails | log warning; persist whatever half succeeded (or nothing); assembly returns normally |
| mutate_project fails | log warning; assembly returns normally |
| No `media_report` on project | scorecard `media: None`; FE shows greyed placeholders |
| Malformed persisted report | scorecard `media: None` + debug log |
| loudnorm itself failed | report still written from the un-normalized file, `loudnorm_applied: false` — the LUFS tile honestly shows the miss |

## 6. Testing

- `measure_loudness`: stderr-JSON parse happy path, missing-keys, no-JSON,
  timeout (subprocess mocked). Verify `two_pass_loudnorm` still passes its
  existing tests after the extraction.
- `probe_final_media`: ffprobe JSON fixtures (conformant, wrong codec, wrong
  resolution, no audio stream, no video stream, ffprobe failure,
  loudness-half failure, both-halves-fail → `None`).
- Scorecard `media`: report present/absent/half-present/off-target (−16.2)/
  at-tolerance-edge (−15.0 passes, −15.01 fails)/malformed.
- Persist hook: probe mocked; assert mutate payload + that probe/persist
  exceptions don't propagate out of `_apply_final_loudnorm`.
- FE gate: `cd web && npx tsc --noEmit && npm run build`.
- Suite + `.venv/bin/python scripts/ci_smoke.py` green per commit.

## 7. Non-goals

- No backfill/lazy probing for already-assembled projects (user chose
  assembly-time-only; an old project lights up on its next reassembly).
- No new endpoint; no change to the GET contract beyond the additive `media` key.
- No UI for re-measuring on demand.
- `pod_health` / `budget` stay future dimensions.

## 8. Plan-time verifications (Rule #12/#13 carried into the plan)

1. ~~Does `domain.models.Project` reject unknown top-level keys?~~ RESOLVED at
   spec review: `ConfigDict(extra="allow")` — §4.3 needs no schema change.
2. Confirm `api_assemble_reassemble` / `api_assemble_screen` paths reach
   `_apply_final_loudnorm` (web_server.py:2448's loudnorm comment suggests yes) —
   i.e., every producer of `final_cinema.mp4` passes the hook.
3. Existing tests touching `two_pass_loudnorm` (extraction must keep them green).

## 9. Estimated scope

~120–160 production LoC across `phase_c_ffmpeg.py`, `cinema_pipeline.py`,
`cinema/capability_scorecard.py`, `domain/models.py` (conditional),
`web/src/types/project.ts`, `web/src/components/console/CapabilityConsole.tsx`.
