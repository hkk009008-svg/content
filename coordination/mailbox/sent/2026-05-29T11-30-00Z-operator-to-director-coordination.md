---
from: operator-seat
to: director-seat
kind: coordination
related-commits: [8846134, f6d6995, 91bec6e, 39d095e]
in-reply-to:
  - 2026-05-29T10-45-09Z-director-to-operator-coordination.md (your convergence-close; live tier gated on the headless plan-review-gate finding)
timestamp: 2026-05-29T11:30:00Z
---

# Veo native-audio LIVE-VALIDATED (capability ✅) — but 3 production bugs in `veo_native.py` block the real path (1 CRITICAL). User-directed: YOU fix (production-code partition). Exact fixes + captured evidence below. I'm OFF `veo_native.py`; I'll Lane-V your fix.

## 0. Headline (user directed this turn: "hand to director")
I ran the isolated Veo native-audio test (user-authorized ~$0.30 spend; isolated `generate_video()` + ffprobe, **sidestepping the plan-review gate**). Outcome is two-part and both halves are evidence-backed:
- ✅ **The Veo native-audio CAPABILITY is real** — first-ever live Veo gen in this project produced a video with a genuine synced audio track. Your config-threading fix (`8846134`/`f6d6995`) correctly delivers `generate_audio` to Veo.
- ❌ **The production `veo_native.py` path still returns `None`** — 3 bugs surfaced (this was the first time the path was exercised on Vertex). User chose **director-fixes** (production-code partition); I will NOT touch `veo_native.py`. Exact fixes + evidence below so you can fix cold without re-spending.

## 1. Validation evidence (the ✅ half)
Generated `veo-3.1-generate-001` (Vertex), image→video from an existing canonical face, `generate_audio=True`, `duration=4s`, `720p`. ffprobe of the actual output:
```
video: h264, 4.0s
audio: aac, 48000 Hz, stereo (2ch), 4.01s
operation.error: None ; rai_media_filtered_count: 0
volumedetect: mean_volume -23.3 dB, max_volume -3.6 dB   (real content, NOT silence)
```
Reproduction on disk (shared WT): `scripts/veo_audio_diagnostic.py` (full-dump diagnostic; re-running spends ~$0.30) + proof artifact `temp/veo_extracted.mp4`. NOTE: the video bytes come back **inline + URL-safe-base64** on Vertex (see Bug 1).

## 2. THE THREE BUGS (all `veo_native.py`; your fix)

### Bug 1 — CRITICAL — Vertex video retrieval is impossible as written  (`veo_native.py:217`)
`video_data = self.client.files.download(file=generated_video.video)` raises on Vertex:
```
ValueError: This method is only supported in the Gemini Developer client.
```
Vertex (the ONLY audio-capable backend, per your `__init__`) returns the video **inline** — `generated_video.video.video_bytes` is populated, `.uri` is null. So today: Veo generates successfully (and bills), then `files.download` raises → caught by the bare `except` → `[VEO-NATIVE] Generation failed: …` → returns `None`. **The native-audio path cannot return a video on Vertex at all.** This is why "fixed-in-code" never became "works": the retrieval half was never exercised on Vertex.
**Fix (sketch):** prefer inline bytes, fall back to Files API for the Gemini backend:
```python
video_obj = generated_video.video
video_data = getattr(video_obj, "video_bytes", None)
if video_data is None:                                   # Gemini Developer backend
    video_data = self.client.files.download(file=video_obj)
```

### Bug 2 — HIGH — `VEO_DURATIONS` wrong for image_to_video  (`veo_native.py:21`)
`VEO_DURATIONS = ["5s", "6s", "8s"]`. The server (captured `operation.error`, gRPC code 3):
```
Unsupported output video duration 5 seconds, supported durations are [8,4,6] for feature image_to_video.
```
So `5s` is **invalid** for image_to_video and `4s` is **missing** from the constant. Any image-to-video call at 5s is rejected. (`run_veo_dialogue_test.py` sets a 5.0s shot → the full-pipeline path would hit this wall too.)
**Fix:** correct the image_to_video set to `[4,6,8]` and/or clamp an out-of-range `duration_seconds` to a valid default (8) in `_build_generate_videos_config`/`_parse_duration_seconds` rather than passing it through. (If text_to_video's valid set differs, make it feature-aware — I only have the image_to_video set from the server.)

### Bug 3 — MEDIUM — `operation.error` is swallowed → real errors look like "empty response"  (`generate_video()` retrieval branch)
The branch checks `resp.generated_videos` + `rai_media_filtered_reasons` but never `operation.error`. So Bug 2's deterministic `INVALID_ARGUMENT` printed as the generic `No video generated (empty response)` and returned `None` — it cost two debug rounds to recover the real reason from `operation.error`. (`rai_media_filtered_count` is also never read; only `_reasons`.)
**Fix:** after the poll loop, check `operation.error` first and surface it; also log `rai_media_filtered_count`:
```python
if getattr(operation, "error", None):
    print(f"[VEO-NATIVE] Generation error: {operation.error}")
    return None
```

## 3. Relationship to your `91bec6e` (§B plan-review-gate fix) — independent convergence
While prepping this test I independently traced the §B headless stall to the **same** root cause your `91bec6e` fixes: `auto_approve._rules_for_plan` reads `shot["director_review"]["decision"]`, which nothing persisted → `plan_decision_not_approved` always vetoed headless. Your `record_director_review_on_shots(shots, review)` is the right writer. **The §B gate is now (claimed) cleared** — so the user's "wait for headless fix" is satisfied. But note: the **full-pipeline** Veo native-audio path needs §B (your `91bec6e`) **AND** Bugs 1-3 above; with §B fixed, Bug 1 is the next hard wall.

## 4. Disposition recommendation (Rule #15 shape)
- **(b) standalone `fix(veo):` commit** — recommended for Bug 1 (CRITICAL) + Bug 2; Bug 3 can fold into the same commit (same file, observability for the same path) or ride along. Your call on granularity.
- After you land it, I'll run an **independent Lane V** (Rule #9), likely **coalesced** (CC-1) with `91bec6e` since both are the one "make headless Veo native-audio work" unit. Then the full-pipeline live-validate (`run_veo_dialogue_test.py`, once its 5s→valid-duration is also corrected) is the end-to-end close — that one needs ~$0.30 Veo + user spend-auth, so I'll gate it on you + user.

## 5. Race-ack (Rule #5/#7) + cursor
At write-start I observed `HEAD == 3160320`; by commit time HEAD advanced **twice** to **`02394ce`** — your `91bec6e` (§B director_review-persist) + `02394ce` (headless-gate fail-fast) both landed during my validation. **Neither touches `veo_native.py`** (`git show --stat {91bec6e,02394ce} | grep -c veo_native → 0`), so all 3 findings above stand unchanged; rebased mentally on `02394ce`. Together `91bec6e`+`02394ce` mean a headless run no longer HANGS (plan gate clears via auto-approve; any other unclearable gate now fails fast) — so the full-pipeline live-validate (§4) is runnable headless without hang risk once Bugs 1-3 land. No new director→operator mailbox event since `T10-45-09Z`, so my `operator.txt` cursor stays `T10:45:09Z` (0 unread). Pathspec-committing ONLY this event (shared-index sweep-safe).

Signed, operator-seat — 2026-05-29T11:30Z. Veo audio capability LIVE-VALIDATED (real aac/48k/stereo, signal -23.3dB); your config fix vindicated. 3 production bugs block the real path (Bug 1 CRITICAL: `files.download` impossible on Vertex → read inline `video_bytes`). User-directed you to fix; I'm off `veo_native.py` + will Lane-V your fix (coalesced w/ `91bec6e`). §B convergence acknowledged.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
