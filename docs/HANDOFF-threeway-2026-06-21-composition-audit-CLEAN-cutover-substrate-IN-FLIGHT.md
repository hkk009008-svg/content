# HANDOFF — Threeway: composition audit CLEAN (ADR-036..043), cutover-substrate audit IN-FLIGHT

**Date:** 2026-06-21
**Pushed:** this handoff + `logs/audit-wf_2ca48247-f19-threeway-composition.json` to `origin/main`,
built directly on `main` (consistent with the prior threeway slices). The `.claude/settings.json`
`codex@openai-codex:false` toggle was **excluded** (pre-existing, unrelated, excluded by every prior
threeway session).
**Verification at handoff:** no production code changed this session — this was an **audit-only** session
(read-only adversarial workflows driving the real gate; the working tree's only tracked delta is the
committed artifact + this doc). `tests/unit/test_threeway_*.py` were exercised *by the audit agents*
(321 baseline still holds; the audit added no tests).

> Trust git, not this prose. On resume: `git fetch && git log -1 && git rev-list --count origin/main..HEAD`.

---

## 0. TL;DR for the next seat

- The threeway control plane has **0 open tracked defects** (all ADR-036..043 rows `fixed`, pushed before
  this session). This session did **not** change that — it **audited the assembled whole**.
- **Audit #1 (composition / forgery — COMPLETE, CLEAN):** `wf_2ca48247-f19` — *"does the COMPOSITION of
  ADR-036..043 admit an emergent forged-promotion / merge-DoS no per-fix pass would have caught?"* →
  **NO. 0 confirmed, 0 new rows.** Drove the REAL gate end-to-end on a full T3 set for the **first time**
  (no committed test does this) — merged correctly. Artifact: `logs/audit-wf_2ca48247-f19-threeway-composition.json`.
- **Audit #2 (cutover-substrate correctness — RUNNING, no verdict yet):** `wf_ce0bba9f-0ac` /
  task `wfdcoioo7`. Covers the residual audit #1 named: `cutover.py` one-shot-flip atomicity, `_teardown`
  exactness, `divergence.py` false-negative, the legacy no-write-path invariant, backfill idempotency,
  refstore/gitcas CAS under contention. **On completion: write `logs/audit-wf_ce0bba9f-0ac-*.json` and
  fold its verdict + `preconditions_for_flip` into the cutover decision.** Resume the result via
  `TaskOutput`/`/workflows`; script at
  `…/workflows/scripts/threeway-cutover-substrate-audit-wf_ce0bba9f-0ac.js`.
- **The LIVE CUTOVER remains GATED on explicit user confirmation** (irreversible-only-with-effort). Neither
  audit authorizes it; audit #1 strengthens the *core* case, audit #2 is the *substrate* gate. **Do NOT flip
  without the user's go.**

## 1. What this session did

Resumed from "continue task (/ultracode-/workflow)". With all threeway defect rows already `fixed` + pushed,
the highest-value autonomous, non-destructive move was a **holistic cross-ADR audit** — a genuinely-new
question (R-VERIFY-TIER compliant: whole-system *composition*, NOT a re-run of any single per-ADR cert).

**Audit #1 — `wf_2ca48247-f19` (17 agents, 1.75M tok, ~40min, all Opus). Verdict: NO emergent composition gap.**
- 5 map-slice readers reconstructed the assembled trust model from code → 5 adversarial lenses drove the
  REAL gate (`run_gate`/`verify_and_reduce` via the seatkit signing fixture) → 3-skeptic adversarial refute
  per candidate → synthesis. 2 candidates, **both refuted, 0 confirmed.**
- Strongest cross-fix attack exercised + failed closed: ADR-036/037 *revoke + id-collision* machinery turned
  against ADR-043's NEW overseer singletons (`re_verify_challenge`, `approver_roster`). `_revoke_authorized`
  gates them (ids enter `seat_by_id` overseer-only); non-overseer revoke ignored; colliding-id squat blocked
  by `store.append` `EventIdCollision` or fails closed `GateError` per ADR-037.
- The "build-pipeline seat doubles as approver" worry was driven through the real gate (operator2, the T2
  mirror co-signer, also rostered as a T3 human) → merges with two genuinely-distinct key-bound seats, as
  designed. It's a **roster-construction policy** question for the overseer (same class as ADR-043's
  documented nonce-rotation precondition), not a code gap.
- Honest NOT-COVERED list (no silent caps) → became audit #2's scope (see artifact `not_covered`).

**Audit #2 — `wf_ce0bba9f-0ac` (RUNNING at handoff).** Reoriented from forgery to **recovery correctness**:
injects mid-sequence failures and drives the real `cutover`/`divergence`/`backfill`/`refstore` machinery,
ranked by the data-loss directions (half-flipped-unrecoverable / divergence-false-negative /
backfill-non-idempotent / cas-loss-or-dup / no-write-path-invariant-broken). Synthesis emits a plain
**flip-readiness verdict** + concrete **preconditions_for_flip**.

## 2. Config changes (this session, NOT pushed where personal)

- `permissions.defaultMode: "bypassPermissions"` added to **`.claude/settings.local.json`** (gitignored,
  personal) — at user request, merged alongside the existing 77-entry `allow` list (not the team file:
  bypass-all is a personal trust posture, committing it would disarm prompts for the whole fleet). Takes
  effect next session start; first engage may show the one-time `skipDangerousModePermissionPrompt` dialog.
- `.claude/settings.json` `codex:false` toggle left uncommitted (excluded, as every prior threeway session).

## 3. NEXT (unchanged program shape; audit #2 is the only new thread)

1. **Drain audit #2 `wf_ce0bba9f-0ac`** → persist its `logs/` artifact → if CLEAN, the substrate gate is
   satisfied; if it confirms defects, file the recommended inventory rows + fix BEFORE any flip.
2. **Operationalization (still all user/external-gated, from the ADR-043 handoff §4):** dual-chief apps +
   overseer nonce/roster EMITTER + **chief-* registry key provisioning** (the re-cert MAJOR — required for
   T3 liveness); wire the gate driver (`run_gate` still has **zero production callers**); then the **LIVE
   CUTOVER** (hold for explicit confirmation).

## 4. Sharp edges (this session)

- `logs/` is **gitignored**; audit/discovery artifacts are committed via `git add -f` (the prior
  `logs/discovery-wf_*.json` are tracked the same way). `git status` won't show a new `logs/*.json` as
  untracked — `git check-ignore` to confirm, then `git add -f`.
- The composition audit's disjointness argument **rests on** the legacy no-write-path invariant
  (legacy projection → only the non-load-bearing `event_sent` kind, never reduced). Audit #2 lens
  `no-write-path-invariant` re-checks it in code precisely because audit #1 *assumed* it — if it's false,
  the forged-promotion class reopens via the migration path. Watch that lens's result.
- Audit-only session: **no production code, no new tests, no new ADR/inventory rows.** Don't let a future
  reconcile mistake the clean composition verdict for a code change.

## 5. Where the truth lives

`logs/audit-wf_2ca48247-f19-threeway-composition.json` (audit #1 full verdict + coverage + not-covered).
`DECISIONS.md` ADR-036..043 (the defect closures audit #1 stress-tested). `ARCHITECTURE.md` §13A.
`docs/REMEDIATION-INVENTORY.md` (all threeway rows `fixed`; audit #1 added none). Audit #2 verdict +
its artifact land on completion of `wf_ce0bba9f-0ac`.
