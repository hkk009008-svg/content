# coordination: U3 dashboard dogfood DONE (handoff NEXT #3) — ✅ PASS + 3 findings (1 latent bug)

- **from:** operator
- **to:** director
- **kind:** coordination
- **sent:** 2026-06-07T20:05:00Z
- **head-at-send:** `31d5c96`
- **user-direction:** "#3 proceed" (this session)

## Result: U3 verified at the REAL surfaces — ✅ PASS

Full runtime dogfood (web server + real browser screenshots via system Chrome,
not API-only). Project `7cddd0c59f6d` ("Tier B Korean Probe", the −15.09 LUFS
file per your handoff §1b acceptance check):

1. **BEFORE** — scorecard `media: null`; UI tiles AUDIO LUFS + FORMAT CODEC
   render dashed/greyed "— not yet measured" (screenshot).
2. **Force re-assembly** (`POST …/assemble/re-assemble {"only_if_changed":false}`)
   → 200, ~16s wall.
3. **AFTER** — `media_report` persisted (real probe: −14.23 LUFS, TP −1.21,
   LRA 0.8, 1920×1080 h264+aac, loudnorm_applied, measured_at) → scorecard
   computes pure → **UI tiles LIVE: −14.23 LUFS GREEN, 1920×1080 GREEN**
   (screenshot).
4. **Old-export claim** — `aa777d858e71` (final mp4 on disk, pre-U3): media
   null, tiles stay greyed (screenshot). Assembly-time architecture confirmed.
5. **RED branch** — exercised via labeled synthetic-state probe (injected the
   historically-real −15.09 into media_report, screenshot: **AUDIO LUFS RED
   while FORMAT stays GREEN** — per-tile independence; restored genuine −14.23
   afterward, API-verified). Probes: default-body POST → `skipped:true`
   short-circuit ✓; bogus pid → 404 ✓.

## Findings

- **F-A (latent bug, ticket-worthy):** re-assembly's dialogue TTS called
  **Cartesia with an ElevenLabs-format voice id** (`voice=21m00Tcm…` = 11labs
  "Rachel") → guaranteed `400 Bad Request` → fell back to ElevenLabs. The
  Cartesia lane appears dead-on-arrival whenever the configured voice id is
  ElevenLabs-shaped — fallback masks it. Server-log evidence:
  `[CARTESIA] Generating [language=ko] voice=21m00Tcm…` → 400 → "falling back
  to ElevenLabs" → "✅ Multi-character dialogue assembled".
- **F-B (ops/cost):** `/assemble/re-assemble` is **NOT ffmpeg-only** — it
  re-generates the dialogue audio bed (TTS spend; ElevenLabs fallback fired)
  + pedalboard BGM mastering. The S21 "cost_estimate_seconds" framing
  undersells real $ on dialogue-heavy projects, and regenerated TTS makes
  cuts non-deterministic between assemblies. (This dogfood: 1 Korean line,
  ~cents.) Pre-norm intermediate measured −27.97 → rebuilt mix differs from
  the old export's; loudnorm then lands −14.23.
- **F-C (handoff calibration):** my handoff #3's "tile must show RED after
  reassembly" was stale-by-environment: −15.09 was the OLD export's loudness;
  fresh two-pass loudnorm self-corrects into tolerance → GREEN is the correct
  honest outcome. RED needs a loudnorm residual >1dB. U3 itself verified in
  BOTH directions (real green + synthetic red).
- Cosmetic: `measured_at` serializes `+00:00` (house convention elsewhere is
  `Z`-suffix; see project_manager timestamp shape).

State: project `7cddd0c59f6d` now carries the genuine post-reassembly
media_report + new export (desirable end state). Backup of pre-dogfood
project.json + mp4 at `/tmp/u3-dogfood-backup/`. No code changes; no commits
beyond this event. Screenshots: `/tmp/u3-pw/{before,after,red-probe,old-export}-*.png`.

Disposition recs: F-A → ticket (grep voice-id plumbing per provider);
F-B → ticket or OPERATIONS.md note; F-C → no action (recorded here).
