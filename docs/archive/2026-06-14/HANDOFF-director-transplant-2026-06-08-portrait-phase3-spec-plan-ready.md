# Director Transplant Handoff — 2026-06-08 — Portrait Phase-3 spec + plan READY (execution-ready)

## §0 — Current state (git is truth)

- **`origin/main` == `a0480f5`** GREEN (portrait Phase-2 merged; suite 1818/0, ci_smoke OK, gate CLOSED `["16:9"]`).
- **`origin/feat/max-tier-provisioning` == `4596b84`**; **local `feat` HEAD == `f495f3a`, AHEAD 17, UNPUSHED.** The 17 are this session's director docs/spec/plan/coord + the operator's F5 / Rule#18 / Finding-1 work — all docs/FE, **zero production-Python change**. Pytest unchanged at **1818/0** (last verified at `a0480f5`; F5 `a7216d1` was FE-only, operator-verified `test_diagnose_clip_advisory` 16 passed + `npm run build` green). **ci_smoke OK** (re-run this session, exit 0).
- Local `main` is stale at `c28f9e6` (cosmetic — FF was push-only, never checked out; `origin/main` is truth).
- Both seats **wrapped** this session (user "handoff" to both). Operator offline.

## §1 — ⭐ #1 PICKUP: EXECUTE the Phase-3 plan via subagent-driven-development

Phase 3 = **per-provider native 9:16 VIDEO + un-gate `SUPPORTED_ASPECT_RATIOS`**. The spec AND the implementation plan are written, both **cold-reviewed and review-folded**, execution-ready:

- **Spec:** `docs/superpowers/specs/2026-06-08-portrait-phase3-video-design.md` (`682e773` → `903aa68` fold operator CC-1 forward-carries → `93c6338` fold cold-review fixes). Doc-reviewer APPROVED + tech-grounding **9/9 MATCH** at HEAD.
- **Plan:** `docs/superpowers/plans/2026-06-08-portrait-phase3-video.md` (`f495f3a`). 10 tasks T1→T10, bite-sized TDD, DRY "Test Conventions" (TC-1..TC-8) grounded in a real test-convention survey. Cold 2-reviewer pass folded (T2 reframed as honest no-RED plumbing; Conventions #6 blast-radius; TC-5 video-stub shape; TC-7 Kling; etc.).

**Action:** invoke `superpowers:subagent-driven-development` and execute T1→T10. One implementer per task → spec reviewer (reads the diff, not the self-report) → code-quality reviewer; fix-loops as separate commits. **Carry the plan's "Project Conventions" block + the relevant TC- patterns into each implementer prompt.**

**Non-negotiable ordering invariant:** **T10 (un-gate, append `"9:16"` to `cinema/aspect.py:23`) is LAST and hard-gated on T9's live preflight PASS.** If the gate opens before the video providers are aspect-aware, every 9:16 project regresses to portrait-container + landscape-clips (no error, pure quality regression). Ship set = **Veo + Sora + Kling + Runway**; LTX native-only/pod-gated, Seedance + Hedra deferred.

**T9 needs USER/operator action:** `scripts/_phase3_portrait_preflight.py` makes **live API calls** (one 9:16 clip per provider + a schnell `portrait_16_9` smoke). Pause and have the user run it; paste its PASS table into the T10 commit body (ADR-013). Don't land T10 without it.

**Ground-truth provenance (don't re-derive):** the spec/plan rest on a Rule #17 audit (`wf_d41e2e96-631`, 17 agents, adversarial verify) + director spot-check (guardrail 2b), which **corrected a false-positive blocker**: U9 "ctx-plumbing" is FALSE — `cinema/shots/controller.py:496/1239/1376` DO pass project `global_settings`, so `generate_ai_video`'s `ctx` already carries the project aspect (Phase-2 images unaffected; **no controller change needed**, the spine just reads `_aspect` from `ctx`). Production anchors are zero-drift through `1e7f0cc` (re-grep at execution HEAD anyway — plan-vs-source rule).

## §2 — What this session shipped (the arc)

Brainstorm → spec → writing-plans for Phase 3 (the prior director-handoff's #1 pickup):
1. **Rule #17 provider-capability audit** (`wf_d41e2e96-631`) → verified §7-D matrix (the old matrix under-counted Runway+Seedance, over-claimed incapability on Sora+Kling). Spot-checked; U9 corrected.
2. **Spec** authored via brainstorming skill, 5 user decisions locked (ship 4 / accept+upscale Runway / LTX native-only / on-pod validation gate / pre-ship enum checks) + 2 follow-ups (automated preflight hard-gate; fix Runway `gen4` bug in-branch). Cold-reviewed.
3. **Plan** authored via writing-plans skill, grounded in a test-convention survey (`wf_84d6f38b-086`). Cold 2-reviewer pass (`wf_5d69f7c6-34a`) folded.
4. **Processed operator's CC-1 Lane V** on Phase-2 (✅ READY, 0 actionable) — concurred option-c; folded its 2 forward-carries (SPEC-3 schnell smoke → §8 preflight; INFO-1/PLUMB-5 → §10 cleanups).
5. **Memory:** consolidated the **D-a Workflow-skip-worktree** hazard into `feedback_da_stale_index_refresh.md` as vector 2 (N=2 both seats; same `git read-tree HEAD` remedy; description updated for recall).

## §3 — Cross-seat state (operator wrapped/offline)

- **Operator handoff:** `docs/HANDOFF-operator-transplant-2026-06-08-finding1-inline-anchor-spec.md`.
- **Finding-1 (inline-anchor verifier for `check_doc_claims.py`) is OPERATOR-OWNED (user-directed)** — do NOT pick it up (authority: user > git > mailbox overrode my "tracked" carry-forward). Operator left it mid-spec-review (spec v2 `b294950`, iteration-2 re-review in-flight at their wrap). Next OPERATOR resumes (spec-review → user gate → writing-plans → TDD + repo-wide inline-anchor sweep). It's in `docs/superpowers/specs/2026-06-08-inline-backtick-anchor-verification-design.md`.
- **Your Phase-3 per-feat Lane V is released to the NEXT OPERATOR** (this operator went offline). When your first Phase-3 feat commit lands, the next operator runs the independent Lane V (Rule #9). No scout-request was needed (audit gave precise anchors).
- **Mailbox:** director cursor advanced to `05:30:00Z` (both operator wrap events processed; nothing owed). Operator cursor `05:06:02Z`.

## §4 — Open carry-forwards

1. **EXECUTE Phase-3** (§1) — the whole point; plan is ready.
2. **D-a skip-worktree durable hook fix (strategic candidate, NOT claimed):** corruption hit **N=4** this session (both seats); operator suggested proactively clearing skip-worktree bits when `core.sparseCheckout` is unset, in `update-state.sh`. Worth a small strategic slice if it keeps biting. (Workaround works: `git read-tree HEAD` before every commit after a Workflow.)
3. **On-pod 9:16 latent validation** (manual, GPU-up) — pairs with T9 preflight; LTX-native pod-validate before counting it.
4. **F5 visual_findings FE render** — DONE by operator (`a7216d1`); no longer open.
5. **Rule#18 `chief_director.py` anchor sweep** — DONE by operator (`3f2c149`); no longer open.
6. **Push/merge decision** (user-gated): local `feat` is 17 ahead of `origin/feat`, all docs. Next director may push `feat` to sync origin (no production change → safe); merge-to-main is premature (Phase-3 not implemented).

## §5 — Key gotchas / D-a discipline (carry forward)

- **D-a is ACTIVE** (`GIT_INDEX_FILE=.git/index-director`, `CLAUDE_SEAT=director`). Commit with **pathspec** (`git add <paths> && git commit -- <paths>`) — a bare commit sweeps the peer's staged work.
- **After ANY backgrounded `Workflow`, run `git read-tree HEAD`** before `git add`/`diff`/commit (skip-worktree corruption — vector 2 in `feedback_da_stale_index_refresh.md`). New/untracked files are immune; tracked-file edits silently no-op if you skip it.
- **pytest:** `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/ -q` (the exported `GIT_INDEX_FILE` breaks ~9 temp-repo tests).
- **ci_smoke:** `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` (exit 0).
- **Ultracode is on** (this session was `/effort ultracode`): use Workflow for substantive analysis; lean on Rule #17 read-only workflows for audits/surveys + adversarial verify + guardrail-2b spot-check (it caught the U9 false positive).
- **D-a-safe FF merge** (when the time comes): `git push origin <verified-sha>:main` — NO checkout while peer active.

## §6 — Session commit map (director, on `feat`)

`903aa68` spec-fold-CC1 · `93c6338` spec-review-fixes · `682e773` spec · `2a815e3`/`87d7022`/`17a5f20` cursor+ack coord · `f495f3a` **plan**. (Interleaved with operator's `f849f6b`/`a7216d1`/`3f2c149`/`1ec885f`/`5d1d3fa`/`1e7f0cc`/`1aed6ed`/`b294950`/`74665a4` — all disjoint, pathspec-serialized.) This handoff + the cursor→05:30:00Z advance follow.

🔑 **Next director: read §1, invoke `superpowers:subagent-driven-development`, execute T1→T10, pause at T9 for the user's live preflight, un-gate LAST.**
