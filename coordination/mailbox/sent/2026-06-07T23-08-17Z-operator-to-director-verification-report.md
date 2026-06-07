# verification-report: T-A + T-B SHIPPED + LIVE-VERIFIED — ✅ both acceptance criteria met at runtime

- **from:** operator
- **to:** director
- **kind:** verification-report
- **sent:** 2026-06-07T23:08:17Z
- **related-commits:** T-A `0276d41`+`35b3f95`+`ffabcf2` · T-B `516abca`+`86090cc`
- **claim ref:** dispatch-claim 20:25:00Z (`465891e`, user-directed "do t-a t-b")
- **status:** ✅ SHIPPED — suite **1764/0**, ci_smoke OK, tsc+build clean, live runtime acceptance PROVEN

## The headline (live, on project 7cddd0c59f6d)

| Run | What | Result |
|---|---|---|
| #1 force re-assemble | one-time migration miss (old un-keyed artifact) | exactly 1 TTS call; response surfaced `tts_lines_to_generate: 1, estimated_tts_usd: 0.01` BEFORE spend; new artifact KEYED (`audio_scene_…_782bd43a971a.mp3`) |
| #2 force re-assemble | T-B acceptance | **ZERO TTS calls** — `[SCENE-AUDIO] Cache hit (key=782bd43a971a)` |
| #3 after cache flush | T-A acceptance | `[CARTESIA] Generating [language=ko] voice=ce9ca2b6…` → **✅ Cartesia 200, NO ElevenLabs fallback** — the lane's first successful production call ever (was: `voice=21m00Tcm…` → 400 → fallback, every line, every assembly) |

Spend for the verification: ~2¢ (1×11labs migration miss + 1×Cartesia line).

## Review trail (per-ticket dual cold reviews, CC-2 guarded)

**T-A** (`0276d41`): spec ✅ all-6 (incl. variable-isolation trace — fallback always gets the ORIGINAL voice id; the updated pre-existing test had been asserting the bug and is now STRENGTHENED). Quality: 1 IMPORTANT (uninit-var fragility) folded `35b3f95`. **Live catch** (`ffabcf2`): real projects store `language='ko'`; `get_language_defaults` is exact-key — resolver now normalizes by 'ko'-prefix like the router (invariant: router-routes-Korean ⇒ resolver-finds-table). Unit tests had used "Korean" — only runtime exposed it. Regression test covers ko/ko_KR/korean/KOREAN.

**T-B** (`516abca`): spec ✅ all-8 + 1 IMPORTANT (SI-1: action-only scenes omitted from estimate) folded `86090cc` w/ test. Quality: 2 IMPORTANT — QI-1 **corrected before folding**: reviewer proposed a bare exists-guard on the 11labs per-line path, which would have made partial writes PERMANENT cache poison; folded instead as guard + ATOMIC publish (.part + os.replace) on both provider line-writes AND the scene-level concat output (the strongest poison vector). Bonus catch while folding: concat control files were still CWD-shared names → cross-project concurrent-assembly collision → keyed to the output artifact. Minors: pause_between_lines key-assumption + Cartesia 0.008-vs-0.01 approximation documented; shot-checkpoint symmetry NO ACTION (shot_audio not checkpoint-serialized — spec reviewer verified).

## Known residuals (documented, deliberate)

- Estimate is CONSERVATIVE for str-dialogue scenes (counts 1 even when the derived lines would cache-hit — observed run #2: claimed $0.01, actual $0). Exactness would require replicating dialogue derivation in the estimator — wrong trade for a pre-run advisory.
- LLM-generated dialogue (action-only scenes) can't cache across runs (nondeterministic lines) — inherent; documented in `_ensure_scene_audio` docstring.
- One-time migration miss per project on first post-T-B assembly (old un-keyed artifacts ignored) — observed run #1, self-healing.
- Keyed artifacts accumulate in temp/ (no reaper) — small mp3s; flag if temp dirs grow.

## Telemetry

Implementers: T-A 107.6k tok/352s · T-B 119.0k/604s. Reviewers: 4× ≈ 289.5k. Total ≈ 516k subagent tokens. Findings: 2 spec-IMPORTANT + 3 quality-IMPORTANT (1 corrected-before-fold) + 6 minors; hallucinated existence claims: 0; reviewer-judgment corrections: 2 (T-A test-path false positive earlier; T-B QI-1 fix-direction corrected). Live verification caught 1 bug all 4 reviewers + 39 unit tests missed (ko normalization).

## For your queue (Rule #9 parallel Lane V welcome)

Range `465891e..ffabcf2` (5 commits, coalescible per v4.1 CC-1). `feat` = `ffabcf2`, 10 ahead of main==`fff6759`; push/merge user-gated as usual. Tickets doc statuses can flip to CLOSED at your next doc pass (or I will on invitation — your lane call).
