---
from: director-seat
to: operator-seat
kind: coordination
related-commits: [d73eebb, cfc4da0]
related-rules: [2, 8, 9, 13, 15]
in-reply-to:
  - 2026-05-28T11-52-29Z (operator Lane V #20 — d28474e + 46a2cfa, 5 minor 0 blocking)
---

# Director coordination — Lane V #20 dispositions (user split: I did M-2, you have M-1/M-3) + Suno for your Lane V

## 1. Lane V #20 received (Rule #8) — thanks; both commits ✅ sound
Consumed your `11-52-29Z` report. 0 blocking, 5 minor. User-principal directed the split:
**I take M-2; you take M-1 + M-3.** Dispositions:

- **M-2 (image-routing user-pin guard) — DONE (director, `d73eebb`).** User overrode your
  (c) NO-ACTION-now and directed it land now. Image routing now mirrors the video-routing
  AUTO guard: a user-pinned **`shot["image_api"]` wins → else `opt_spec.suggested_image_api`
  → else `None`** (was an unconditional forward). Safe today (no image-pin field exists), but
  the asymmetry is closed.
  - ⚠️ **Coordination for your M-1:** since M-2 changed the forward logic, **your M-1
    forwarding-seam test must assert the GUARDED behavior** — pin wins → suggestion → None —
    not the old unconditional forward. The guard lives at `controller.py:~458-470`
    (`_image_api_hint`); the forward is `shot_hint["image_api"]=_image_api_hint` at `~482`.
- **M-1 (forwarding-seam test) + M-3 (lipsync `shot_id` logging) — YOURS** per user split.
  - M-3 sites for reference: `controller.py:1271` + `:1757`
    (`logger.warning("lipsync cost record skipped", exc_info=True)`) — add
    `extra={"shot_id": shot_id}` to match the keyframe (`:557`) / motion (`:994`) pattern.
  - **Conflict-safe:** M-2 (image routing ~458-482) is disjoint from M-3 (lipsync 1271/1757)
    and M-1 (test file), so our concurrent controller.py edits won't clash on lines.
- **warning-noise + spent_usd-lock (pre-existing) + the M-2 advisory's own forward-looking
  note:** NO ACTION — resolve when lipsync pricing lands (your report's disposition stands).

## 2. New director commit for your Lane V (if you want it)
- **`cfc4da0` fix(music): adapt Suno BGM to sunoapi.org contract.** User provided a
  sunoapi.org key; I rewrote `audio/music.py::generate_suno_v5` from the generic
  `{base}/songs` + chirp-v5 shape to sunoapi.org's `POST /api/v1/generate` → poll
  `GET /api/v1/generate/record-info?taskId=...` (status set PENDING/TEXT_SUCCESS/
  FIRST_SUCCESS→poll, SUCCESS→done, *_FAILED→abort) → download
  `data.response.sunoData[0].audioUrl`. Model `_SUNO_MODEL="V5"`; `callBackUrl` is a
  placeholder (we poll, no public callback). +5 mocked-HTTP tests
  (`tests/unit/test_suno_music.py`). Graceful-False preserved → FAL Stable Audio fallback
  intact. **Not live-tested** (a real generate call spends sunoapi.org credits). `audio/`
  isn't a Lane D trigger, so no doc-sync needed; Lane V optional.

## 3. State + race-ack (Rule #5 / #7)
HEAD `d73eebb`; origin/main `5dfe0d0`; **6 ahead** (your `5e979c7`/`7ce6440`/`af49f96`/
`68c4879` + my `cfc4da0`/`d73eebb`); push user-gated. Your toggle follow-up #1 fix
(`7ce6440`) acked — clean, your cluster, closed. Director cursor advanced to
`2026-05-28T11:52:29Z` (consumed Lane V #20).

Signed,
Director-seat — 2026-05-28 cycle-17 post-MID. Lane V #20: M-2 landed (`d73eebb`); M-1/M-3
yours per user split (M-1 test must assert M-2's pin-guard); Suno→sunoapi.org shipped
(`cfc4da0`) for optional Lane V.
