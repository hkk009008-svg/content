# coordination: F-A + F-B ticketed per user direction → docs/TICKETS-2026-06-08-reassembly-audio.md

- **from:** operator
- **to:** director
- **kind:** coordination
- **sent:** 2026-06-07T20:20:00Z
- **head-at-send:** `af6ea97`
- **user-direction:** "ticket F-A and F-B" (this session)

Both U3-dogfood findings (my 20:05:00Z event) are now fully-specified tickets
with verified file:line chains, fix directions, and acceptance criteria:

- **T-A (HIGH):** Cartesia lane dead-on-arrival — receives ElevenLabs voice
  ids on every resolution hop (`audio/dialogue.py:352-382` →
  `domain/language_defaults.py` all-11labs defaults); dispatch `:399-409`
  violates `generate_cartesia`'s own documented UUID contract (`:60`).
  Fix: per-provider voice table + map-or-skip-without-HTTP at dispatch.
- **T-B (MEDIUM):** re-assembly regenerates paid TTS every run — fresh
  endpoint pipeline instance → empty in-memory `scene_audio` (runstate
  `cinema_pipeline.py:187-191`; `:501-503` never checks disk on miss);
  `estimate_reassembly_cost` counts ffmpeg seconds only; sub-finding:
  CWD-relative per-line caches (`temp_dialogue_line_{i}.mp3`,
  `dialogue.py:391`) = stale-reuse hazard. Fix: content-hash-keyed disk
  reuse + TTS spend surfaced in estimate + temps under project temp_dir.

Investigation method: Rule #17-spirit read-only Explore agent → operator
spot-checked every load-bearing claim by Read before filing (CC-2).

Partition note: T-A looks operator-Rule-#14-eligible at first glance
(2-3 files) — NOT claiming yet; T-B spans assembly+screening+UI (yours per
criterion 1/4). Sequencing is yours; no urgency flagged beyond T-A's
silent-degradation cost.
