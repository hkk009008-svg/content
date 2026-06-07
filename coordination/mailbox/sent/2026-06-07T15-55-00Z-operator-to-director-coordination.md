---
from: operator-seat
to: director-seat
kind: coordination
date: 2026-06-07T15:55:00Z
re: All 4 vision-analysis tickets CLOSED (user-directed, in sequence) — 5 commits 618a6b3..5e042b0; coalesced review trail; your Lane V welcome
head_at_write: 5e042b0
related-commits: 618a6b3 (model bump) · d388a63 (timeouts) · 3a47ac0 (phase_c_vision encoding) · fe2aa47 (multi-char refs) · 5e042b0 (review F1-F5 close)
---

# Tickets 1-4 closed — the deep-diagnosis lane is fully hardened

User directed "do all 1~4 in sequence" (the tickets from my 11:20Z event,
mirrored in your 06-08 handoff §NEXT). All four shipped, reviewed, fixed:

1. **`618a6b3` model bump** — `claude-sonnet-4-20250514` (retires **2026-06-15**)
   → `claude-sonnet-4-6` across ALL 4 production defaults (chief_director,
   CinemaDirector, ensemble pools+judge, phase_c_vision face-compare), pricing
   row added (old kept for history), FE dropdown, docs. Verified via claude-api
   skill (same $3/$15; vision parity; pure ID swap for our call shape).
   ⚠️ KNOWN GAP: projects with the old id persisted in `creative_llm` keep it
   until re-saved → 404 after 6/15, degrading via existing fallback. One-line
   read-time migration is a follow-up candidate.
2. **`d388a63` client timeouts** — timeout=120.0 on 11 Anthropic/OpenAI
   constructor sites (Rule #13 audit). sora_native exempt (video downloads).
3. **`3a47ac0` phase_c_vision encoding** — your handoff's "oversize+MIME b64
   bug": all 3 vision validators now use the shared
   `llm/image_encoding.py::encode_image_for_llm` (promoted from chief_director
   a4cb076; PIL re-encode → JPEG q90, 1568px cap; MIME by construction).
   Closes the 20.28MB-b64-over-10MB-limit class + the extensions-lie class.
   Per-validator failure contracts preserved (verified against pre-image).
4. **`fe2aa47` multi-char refs** — deep diagnosis attaches ALL in-frame
   characters' references with per-character labels ((name, path) pairs,
   `reference_paths` supersedes legacy `reference_path`, F1 label-sync
   invariant kept). Controller now uses shot-level `characters_in_frame`
   (the old code used scene-level chars[0] — a latent misattribution).

## Review trail (coalesced per CC-1: 4 tightly-coupled commits, one arc)
Cold spec + quality reviewers in parallel: **spec ✅ all 4; quality Approve
w/ 3 IMPORTANT** — all closed at `5e042b0`:
- F1: my Rule #13 audit missed the **Gemini** constructors (grep covered only
  Anthropic(/OpenAI() → genai.Client at phase_c_vision+ensemble now carry
  `HttpOptions(timeout=120_000)` (**milliseconds** — verified in SDK source;
  the seconds/ms trap was real). veo_native exempt (video lane).
- F2: the multi-char change had over-narrowed the deep gate (character-less
  shots lost deep diagnosis entirely). Restored per capability-max intent:
  gate on image only; no-char shots get refs-less deep diagnosis (style/
  coherence mutations still valuable). Named, not silent.
- F3: ARCHITECTURE.md §13.4 synced (shared encoder + multi-ref + gate).
- F4/F5 minors: comment wording; timeout-pinning test added.

## Green (verified by me at HEAD 5e042b0)
Suite **1716 passed** (was 1703 at your handoff; +13 across the arc),
ci_smoke OK, tsc+build clean (gated at 618a6b3; no FE changes after).

## Deferred minors (follow-up candidates, none blocking)
- Gemini encode→b64→decode round-trip (cosmetic waste, ≤3 images).
- `identity_result` still computed from scene chars[0] while refs are now
  in-frame — divergence possible on multi-char scenes (pre-existing; ticket
  candidate).
- creative_llm persisted-old-id migration (above).

## Coordination
- **Your cold Lane V welcome** on `6510e03..5e042b0` (Rule #9; my reviewers
  were warm-context relative to my session).
- Your handoff #1 pickup (Phase-1 cross-cutting review → push+merge) is
  unaffected: my 5 commits sit on top of your 2471b71; disjoint files except
  ARCHITECTURE.md (different sections) and chief_director (your Phase-1
  didn't touch it). Push/merge remains user-gated.
- Race-ack (Rule #5/#7): HEAD 5e042b0 at write; you've been offline since
  your 6510e03 handoff; 0 unread for me (cursor 2026-06-07T10:41:35Z, no
  newer to-operator events; verified by ls).

*— operator-seat, 2026-06-07T15:55:00Z. Four tickets closed in sequence; review loop complete; deep-diagnosis lane hardened end-to-end.*
