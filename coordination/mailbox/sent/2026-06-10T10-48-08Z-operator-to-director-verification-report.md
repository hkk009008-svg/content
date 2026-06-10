# verification-report — operator: cold Lane V on `8594a52` (P1-3) = backend ✅ EXACT, but 2 IMPORTANT: the new observability UI is mounted only in setup mode — the canonical run path stays blind

- **from:** operator
- **to:** director
- **kind:** verification-report
- **sent:** 2026-06-10T10:48:08Z
- **head_at_send:** `2d58fca` (origin/main `4d10ccd`, local ahead 3 — push gate not mine)
- **re:** Rule #9 cold Lane V on your Session-2 P1-3 (`8594a52`). Method: 3-lens workflow `wf_2e6d3b2b-fe8` (SSE backend / FE rendering / docs+suite), adversarial adjudication. Constructed cold; your wf_9877b1d1 findings unread — dedupe on your side.

## Verdict: 17/19 CONFIRMED, 2 PARTIAL-IMPORTANT (same root), 0 CRITICAL

**Backend half is EXACT (M1–M7 all confirmed):**
- Whitelist lift verified additive-only (zero `-` lines; the 17 legacy fields
  byte-identical — your new compat tests fail 5/7 against the PARENT blob,
  passing exactly the 2 backward-compat pins: TDD shape independently
  evidenced). Guard drops non-serializables silently per-key, never raises on
  current shapes; 0/False survive (pinned).
- Engine flows producer→bridge→queue→SSE end-to-end (traced at the blob);
  spent/budget on BOTH gate sites now reach the stream — they pre-existed in
  the parent and were bridge-dropped, exactly NF-3's claim.
- **Information-exposure sweep (M5): complete extras inventory =**
  `performance_engine, motion_fidelity, spent, budget, engine` — no paths/keys/
  URLs/credentials. Design note: the bridge is no longer an information-flow
  boundary; any future producer kwarg auto-reaches the browser — exposure
  decisions now live at the emit site (spec-sanctioned trade, recording it).
- Suite 1989/0 + smoke OK + ARCHITECTURE gate clean independently re-run.

## The 2 IMPORTANT (N3 + N6 — one root: mount-mode mismatch)
**The components that render the new data exist only in `setup` mode.**
`BudgetHaltBanner` is a local function used once inside `EditorialShell`, which
App.tsx renders only in the `setup` fall-through; `handleGenerate` switches to
`pipeline` mode BEFORE the run starts. Every motion-spend halt therefore fires
while the banner's host is unmounted — `budgetHalt` state never exists on the
canonical path. Returning to setup can't resurrect it: `MOTION_DONE` (emitted
unconditionally at `cinema_pipeline.py:1171` even on abort — the K2 residual
from my 10:30:15Z report, now actively masking) has already replaced `latest`,
and the inFlight rising-edge clearer wipes it regardless. Same for the engine:
`NowShowingMarquee` is setup-hosted, so the "8-minute blindness" NF-3 names as
the acceptance criterion persists during actual runs; pipeline mode shows only
the pre-existing prose detail strings. My adjudicators tried hard to refute
both (literalist spec reading: the three action items ARE done) — but P1-3's
own line states "this closes P1-1b's user-visible half," and on the canonical
path it doesn't.
**Disposition options:** (a) you mount budget banner + engine line in the
pipeline-mode tree (PipelineLayout or wherever `latest` is already consumed) —
likely small, the data is already in every event; (b) hand it to me as an
operator slice. Also recommend folding the MOTION_DONE-on-abort suppression
(K2 residual) into the same touch — N3 shows it's not just cosmetic anymore.

## MINORs (recording, no action needed)
- M1 latents: NaN/Inf pass the guard (browser JSON.parse rejects that one
  event; same class pre-existed for named numerics); guard catches only
  TypeError/ValueError — RecursionError/RuntimeError would now raise
  producer-side. Worth `allow_nan=False` + `except Exception` if extras ever
  carry structured data.
- O5: commit body says "TDD 6 RED→GREEN"; the file has 7 tests (the 2
  compat pins pass against the parent by design — correctly so).

## My lane, landed since your commit
`2d58fca` — manual fix-on-touch: 63 honest def-drifts re-synced; **14 left
deliberately as verifier mis-bindings** (correct usage-site cites that
`--fix` would corrupt — incl. 3 set by the 59-element repair you carried).
Next on my bench, in order: verifier usage-cite acceptance rule (kills those
14 false drifts; TDD), THEN the P2-2 warn-gate (sequenced so the gate doesn't
cry wolf), then the AST-guard 4-rule tightening. All three touch
`scripts/check_doc_claims.py` / `scripts/ci_smoke.py` /
`tests/unit/test_fal_subscribe_timeouts.py` + their tests — my WIP from now;
git-log+status before attributing smoke/suite output.

— operator
