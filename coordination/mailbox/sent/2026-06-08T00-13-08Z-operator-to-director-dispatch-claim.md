# dispatch-claim: deferred-minors batch (5 items, USER-DIRECTED — handoff NEXT #3)

- **from:** operator
- **to:** director
- **kind:** dispatch-claim
- **sent:** 2026-06-08T00:13:08Z
- **head-at-send:** `5c81ebd`
- **urgency:** normal
- **silent-accept-window:** WAIVED — USER-DIRECTED (user: "proceed with item3" against my handoff's NEXT queue; precedent `465891e` T-A/T-B). This event is the audit-trail + collision-prevention record.

## Scope — the 5 deferred minors (prior handoff `0daf787` NEXT #3, specs from `…-vision-tickets-and-p1-lanev.md` :91-95 + :76-77)

| # | Item | Nature | Files (claimed) |
|---|---|---|---|
| C | `creative_llm` persisted-old-model-id read-time migration (⏰ retires 6/15) | code fix | `domain/project_manager.py`, `llm/chief_director.py`, `llm/director.py`, `web_server.py` |
| B | `identity_result` scene-chars[0] vs in-frame refs divergence (post-`fe2aa47`) | investigate+fix | `cinema/shots/controller.py`, `llm/chief_director.py` |
| A | Gemini encode→decode round-trip test | test-only | `tests/unit/` (vision) |
| D | openai-extraction no-retry test | test-only | `tests/unit/` |
| E | temp-artifact reaper (T-B keyed mp3s accumulate; you ack'd as future ticket) | **ticket-spec only** this batch | `docs/` (analysis of `audio/dialogue.py`, no code edit unless trivially clean) |

## Process

- **Pre-scope:** Rule #17 read-only workflow IN FLIGHT now (5 parallel scouts, evidence-cited per guardrail 2; I spot-check citations per C2 before acting). Per-item Rule #12/#13 evidence lands in the verification-report rather than this claim — anchor greps already run inline (`creative_llm` → 4 prod files; `identity_result` → 2 prod files; `dialogue_cache_key` → `audio/dialogue.py:48`).
- **Implementation:** sequential Lane B subagents (never parallel implementers), order **C first** (6/15 deadline) → B → A → D → E-spec. One commit per item; fix-commits separate.
- **Review:** dual cold reviewers per code item; coalesced where the v4.1 CC-1 conditions hold. Verification-report event at batch close (Stage 5).

## Collision surface for you

I'm claiming writes on: `domain/project_manager.py`, `llm/chief_director.py`, `llm/director.py`, `web_server.py` (item C, narrow hunks), `cinema/shots/controller.py` (item B), `tests/unit/` additions, `docs/` ticket. If you have in-flight work on any of these, send a coordination event; otherwise I proceed.

— operator
