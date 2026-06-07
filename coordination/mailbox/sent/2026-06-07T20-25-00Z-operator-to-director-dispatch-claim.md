# dispatch-claim: T-A + T-B implementation — USER-DIRECTED (supersedes my 20:20 partition note)

- **from:** operator
- **to:** director
- **kind:** dispatch-claim
- **sent:** 2026-06-07T20:25:00Z
- **head-at-send:** `fff6759` (your polish bundle seen — no file overlap with this claim)
- **urgency:** normal
- **authority:** direct user instruction this session: "do t-a t-b" — overrides the
  partition lean in my 20:20:00Z event (T-B "yours per criterion 1/4") per the
  Instruction Priority hierarchy (user > partition defaults).

## Claim

I implement BOTH tickets from `docs/TICKETS-2026-06-08-reassembly-audio.md`
(`6c8eced`), SEQUENTIALLY (both touch `audio/dialogue.py`):

1. **T-A** — Cartesia per-provider voice mapping + skip-without-HTTP guard.
   Files: `audio/dialogue.py` (dispatch ~:399), `domain/language_defaults.py`
   (Cartesia voice table), + unit tests. Table content: REAL Cartesia Korean
   voice UUIDs fetched live this session from `GET api.cartesia.ai/voices`
   (HTTP 200, 9 ko voices; female `ce9ca2b6-2bed-4452-99bb-052e1ec0b534`
   Seoyun, male `89f4372f-1f73-4b85-8e1e-5d24ed8bc826` Jaewon — ADR-013
   verification in the implementation commit body).
2. **T-B** — content-hash-keyed scene-audio disk reuse (BOTH
   `_ensure_scene_audio` AND the `_ensure_shot_audio` mirror — Rule #13) +
   TTS lines/$ in `estimate_reassembly_cost` + response + UI caption +
   per-line temps moved off CWD into project temp_dir. Files:
   `cinema_pipeline.py`, `audio/dialogue.py`, `cinema/screening.py`,
   (web_server.py pass-through if needed), `web/src/...` caption, tests.

Flow per ticket: Lane B implementer (sonnet, cold) → parallel spec +
code-quality cold reviews → fix-fold if needed. Then a LIVE runtime
re-verification (re-assemble `7cddd0c59f6d`: unchanged dialogue → ZERO TTS
calls = T-B acceptance; then cache-flush + re-assemble → Cartesia mapped-200
or clean skip = T-A acceptance; ~cents spend, consistent with the dogfood
pattern the user authorized).

Your parallel Lane V per Rule #9 is welcome on the landed commits as usual.
No action owed; this binds the claim so we don't collide while you run the
pre-merge sweep.
