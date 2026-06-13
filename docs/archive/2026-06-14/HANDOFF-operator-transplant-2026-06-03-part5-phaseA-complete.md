# Operator Transplant Handoff — 2026-06-03 (Part-5 Phase-A complete · moderates shipped+pushed · prune + no-op audit done)

*Last verified: 2026-06-03 (late). Branch `feat/max-tier-provisioning` @ `6d87f22` (+1 for this
handoff commit). **Origin at `7e807d8`, branch AHEAD 10** — the moderates cycle is pushed
(origin==7e807d8, director-Lane-V-clean); the Part-5 prune + audit work (10 commits) is UNPUSHED.
Suite **1512 passed / 3 skipped / 0 failed**; §15 smoke `OK`; doc anchors clean. This handoff
SUPERSEDES `HANDOFF-operator-transplant-2026-06-03-part3-shipped-test-hygiene.md` — its OPEN item #1
(deferred Part-3 moderates) is DONE + shipped; items 2-4 are addressed or ticketed (below).*

## ★ READ FIRST — what this (long) session shipped

Three coherent arcs, all verified (suite/smoke/anchors green throughout):

### Arc 1 — Part-3 deferred moderates/minors (design-first cycle) — SHIPPED + PUSHED + Lane-V-clean
- Brainstorm → spec (`6fb287f`, reviewer-✅) → plan (`c83beba`, reviewer-✅) → **6 tasks via subagent-driven-development** (TDD + 2-stage review per task) → **2 follow-ups** → opus final cross-cutting review ✅.
- **13 findings closed** (6 FIX + 3 CLEANUP + 3 DOCUMENT + 1 LEAVE). Code range `d7fc45d..d15c56b`. Done-signal: `grep -rn "CANDIDATE BUG" tests/unit/` → **empty**.
- **2 capability wins** (PROGRAM-MANUAL §5): **Sora 1080p** (`d7fc45d` — `resolution` was ignored/hardcoded 720p; now wired via `RESOLUTION_MAP`) + **LTX 5xx/network → FAL fallback** (`4bf2637`+`c293524`).
- **2 cold-context catches (Rule #9/#13 working):** (a) **CRITICAL** `c293524` — the first ltx fix swallowed network `URLError`/timeout (OSError subclasses) into no-fallback, defeating its own intent; fixed with a specific-first except clause. (b) **Rule #13 symmetric** `db383d7` — the `threshold=0.0` G4 fix in `validate_video` had an identical `threshold or X` divergence in sibling `validate_image`; completed the bug-class.
- **Survey corrected in 3 places** (handoff predicted): G5 vision-threshold NOT a live gate bug (IdentityValidator re-thresholds — documented); G4 latent; G(sora)1/G(ltx)3 intentional conventions.
- Follow-ups: `f211c54` (`VIDEO_ZERO_FRAMES` failure_reason) + `d15c56b` (style web-research now logs).
- **Director independent Lane V = ✅ SHIP-CLEAN** (`7e807d8`, event `2026-06-03T07-25-00Z`), pushed to origin/feat.

### Arc 2 — Part-5 Phase-A item 2: PRUNE (327 LOC) — UNPUSHED on feat
- Read-only re-verify audit first (cold agent, re-grep incl. tests + dynamic/string refs per `feedback_re-verify-before-destructive-commits`); user chose **"prune confirmed-dead, keep nuance."**
- **5 chore prunes** (re-grep-before-each-delete, green-after-each): `b4a03c8` reporter.py (52) · `e31d6a2` generate_characters.py (68) · `45c2299` dialogue_writer 2 fns (28) · `6e8ce34` continuity_engine 2 methods (7; `last_generated_image` LEFT — still live) · `8a5d425` run_tier_c.py (172). **Total 327 LOC, suite UNCHANGED.**
- `51f1826` ARCHITECTURE.md doc-sync (dropped 2 stale refs). `fbc318f` coord+ADR-draft → **director committed ADR-020 (`f499c81`)**.
- **KEPT:** `validate_multi_identity` + `summarize_audit` (user). **`cinema/pipeline.py::CinemaPipeline` RECLASSIFIED KEEP** — it's a *"preserved primitive"* (ARCHITECTURE §4.8) guarded by the §15.9 zero-callers invariant + part of the cinema/phases scaffold; NOT dead code (I pulled it from the batch + inspected to avoid a careless §15 truth-doc edit).

### Arc 3 — Part-5 Phase-A item 3: NO-OP AUDIT → tickets + stale-doc fix — UNPUSHED on feat
- Re-verified all **11 Part-3 fix-list items** at HEAD (cold agent). **#2 (dialogue routing) + #10 (hedra ARCHITECTURE §10.6) already DONE** (spec was stale). **#9 storyboard_mode stale-doc FIXED** (`fb8d628` — last current-truth site in `PROGRAM-MANUAL-digests.md`; manual §D-12 + pipeline_status.toml were already correct).
- **8 triaged tickets** → `docs/superpowers/2026-06-03-part3-noop-audit-tickets.md` (`6d87f22`).

## Where we are in the Test/Audit program (spec `docs/superpowers/specs/2026-06-02-program-test-audit-plan-design.md`)

| Part | What | Status |
|---|---|---|
| Part 1 | Capability ledger | done (prior) |
| Part 2 | Prune list | **DONE** — 5 pruned (327 LOC), ADR-020; cinema/pipeline.py kept |
| Part 3 | Fix list (HIGH + moderates) | **DONE** — HIGH (prior) + moderates (this session, shipped); residual no-ops → tickets |
| **Part 5 Phase A ($0 offline)** | characterize + prune + no-op audit | **COMPLETE this session** |
| Part 4 | UI dimension (U1/U2/U8) | **NOT started** (next $0 piece; design-first frontend) |
| Part 5 Phase B/C | live per-API + e2e scorecard | **NOT started** (spend-gated) |

## NEXT — priority order (for the next operator)

1. **Part 4 — UI surfacing** (the last $0 offline program piece; completes the definition-of-done): U1 capability scorecard, U2 per-shot coherence/motion/lipsync scores (already in `take.metadata`), U8 cascade-provenance (`cascade_metadata`). React 19, `Telemetry.tsx`. **Design-first** (brainstorm→spec→plan→implement) — subjective UI design, engage the user.
2. **The 8 no-op tickets** (`docs/superpowers/2026-06-03-part3-noop-audit-tickets.md`), by severity:
   - **T1 (HIGH)** `validate_lora_quality` is a `-1.0` stub (`prep/lora_training.py:515`) — the #1 identity lever; bad LoRA silently degrades every shot. **Design-first** (proposed approach: generate samples with the trained LoRA → identity-similarity vs reference → threshold-gate; capability-design — surface to user per PROGRAM-MANUAL).
   - **T6 (MED)** wire `evaluate_generation_quality`+`negative_prompts` auto-remediate loop (dormant lever).
   - T3 (verify hires_fix injection — likely already wired, cheap close) · T4 (max_halt_rule modes) · T5 (audio budget cap) · T7 (EXPERIMENTS_DB_PATH wire/remove) · T8 (pipeline_context.md prompt drift — behavior-adjacent) · T11 (3 @unittest.skip).
3. **Push** the Part-5 work (10 commits) to origin/feat — operator offered, user said "handoff" first; **user/director call**.
4. **Merge-to-main** — director + user decision (main still `26d9b1e`; feat carries everything: max-tier + dialogue + moderates + prune).
5. **Phase B/C** — spend-gated live capability checks + e2e scorecard.

## Key gotchas / precedents (carry forward)
- **Survey-can-be-wrong is the norm.** Both the moderates findings AND the Part-3 fix list were stale in multiple places when re-verified at HEAD. ALWAYS re-verify spec/handoff claims against current source before acting.
- **Two-stage review earns its keep:** the ltx URLError CRITICAL (`c293524`) was spec-compliant but semantically wrong — only the cold code-quality reviewer caught it. The validate_image Rule #13 symmetric site (`db383d7`) too. Keep dispatching independent (Rule #9) reviewers.
- **`cinema_pipeline.py::CinemaPipeline` (live, root) ≠ `cinema/pipeline.py::CinemaPipeline` (preserved-primitive scaffold, KEEP).** Same name, different files — don't confuse when grepping.
- **Destructive prunes:** re-grep each candidate at HEAD (incl. dynamic/string refs) immediately before delete; one chore commit per concern; ADR (director). cinema/pipeline.py-class prunes touch §15 truth-doc — handle deliberately, not in a mechanical batch.
- **Anchor drift:** line-shifting doc edits can break `check_doc_claims` → run it before each commit (`--fix` if drift).
- **Pathspec commits (shared index):** `git diff --cached --name-only` then `git commit -m "..." -- <paths>` — never `git add -A`.
- **Two-seat coordination is live:** director committed ADR-020 (`f499c81`) from my draft mid-session, and Lane-V'd the moderates SHIP-CLEAN. Match the commit-body + mailbox discipline.

## Coordination state
- **Director: active.** Lane V'd the moderates (✅ SHIP-CLEAN, `7e807d8`, pushed) + committed **ADR-020** (`f499c81`) from my prune ADR-draft. No open director→operator asks (latest event `2026-06-03T07-25-00Z`, processed).
- **Mailbox** (operator→director this session): `05-24-09Z` (execution claim), `06-30-05Z` (moderates completion verification-report), `09-11-52Z` (prune report + ADR draft). Cursor/processing current.
- **feat AHEAD 10 of origin** — moderates pushed (origin==7e807d8); Part-5 prune+audit (10 commits) UNPUSHED. Push is user/director's call.

## Verification at write (ADR-013)
```
$ git rev-parse --short HEAD            → 6d87f22   (+1 for this handoff)
$ git status -sb | head -1              → ...feat/max-tier-provisioning [ahead 10]
$ .venv/bin/python -m pytest tests/unit/ -q   → 1512 passed, 3 skipped, 0 failed
$ .venv/bin/python scripts/ci_smoke.py        → OK
$ .venv/bin/python scripts/check_doc_claims.py → All anchors checked — no drift.
$ grep -rn "CANDIDATE BUG" tests/unit/        → (empty)
```
