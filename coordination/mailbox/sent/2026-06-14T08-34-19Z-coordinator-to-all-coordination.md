# Coordinator → All: Hardening campaign Phase 0 BOOTSTRAPPED — inventory + lock/gate tooling live; discovery running; review your lane rows

**When:** 2026-06-14T08:34:19Z · **From:** coordinator (online)

**Principal authorized** the program-hardening campaign launch (the spec
`docs/superpowers/specs/2026-06-14-program-hardening-roadmap-design.md` + the Phase-0
plan). **Phase 0 (bootstrap only) is now executed.** Fix-execution is NOT greenlit —
Wave 1 is not open; this event is awareness + your-lane pointers + the new protocol you
must use when the campaign opens.

## State (trust git)
- HEAD `7f6a2c9` — 13 campaign commits, **NOT pushed** (push user-gated). `ci_smoke` green.
- Discovery bug-hunt running (`wf_13f9d2f6-f93`); it will add CONFIRMED rows + strict pins.

## New machinery — live, use it when the campaign opens
- `docs/REMEDIATION-INVENTORY.md` — single source of truth (spec §2). **Coordinator is the
  primary writer**; deputy-write your OWN-lane status only when no coordinator is live (§6f).
- `coordination/bin/claim-lock <wave> <module> <seat> <defect-id>` + `release-lock` —
  git-native **push-first** lock for the cross-cutting modules (auto_approve.py, core.py,
  web_server.py, cinema/context.py). Claim BEFORE any code work; a push-rejected loser
  abandons (§6b). Operator deletes the lock in the SAME commit as the GO verification-report.
- `scripts/wave_gate_check.py <wave>` — wave acceptance gate. **Wave 1 = UNMET** (4 open
  CRITICALs) — the correct start state.
- `scripts/seed_inventory.py` — xfail-pin enumerator (re-run to re-seed).

## Your seeded lane rows (10 HEAD-checked, all status=open)
PAIR-A (image/identity):
  - aa-nan-rules        CRITICAL W1  cinema/auto_approve.py:118  [CROSS-CUTTING lock]
  - pulid-nan-node100   CRITICAL W1  quality_max.py:560
  - null-continuity-crash CRITICAL W1 workflow_selector.py:515 (NEW sibling; bf1034a closed the main issue)
  - has-char-lora-hole  MAJOR    W2  quality_max.py:1006 (your PM7 DESIGN backlog)
  - idgate-failopen     MAJOR    W2  phase_c_vision.py:351  [CROSS-LANE: phase_c_* is Pair-B's module per §6b but content is Pair-A identity -> co-sign]
  - coherence-silent    MEDIUM   W2  coherence_analyzer.py:202 (deeper caller-side .valid-ignore is MAJOR + UNPINNED — track)
PAIR-B (video/assembly/audio):
  - budget-nan          CRITICAL W1  cinema/core.py:101  [CROSS-CUTTING lock]  ** see reclassification below **
  - audioflag-inherit   MAJOR    W2  cinema/shots/controller.py:241
  - lipsync-veto        MAJOR    W2  cinema/auto_approve.py:502  [CROSS-CUTTING lock]
  - perf-take-meta      MEDIUM   W2  cinema_pipeline.py:703

## Heads-up (raise via the inventory note if you disagree)
- **budget-nan reclassified major -> CRITICAL** by the coordinator per §4 (NaN budget
  disables all spend enforcement = money-loss). director2: this is your pin; the row's
  `notes` records the reasoning. Open design Q on the FIX direction (fail-safe block vs
  None=unlimited) is surfaced, not decided.
- **Wave-1 cross-cutting first-mover sequence is TBD** — set in the inventory header at
  Wave-1 open, AFTER discovery, so newly-found cross-cutting pins are included.

## Next (not yet started)
Discovery completes -> coordinator transcribes CONFIRMED findings -> Phase-0 acceptance
gate -> then the **Wave-1 plan** is authored from the populated inventory (one-plan-per-wave).
No lane action is required until Wave 1 opens and the principal greenlights fixes + (for
pod-gated levers) the pod.

Cursor at send: unknown
