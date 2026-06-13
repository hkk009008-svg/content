# Director Transplant Handoff — 2026-06-08 — Portrait Phase-3: T5a–T9 + Sora-fix DONE; T10 un-gate PENDING (F1 fix + clean preflight first)

**You are the next director.** Phase-3 video is **substantively complete and independently Lane-V'd SAFE**, but the final un-gate (T10) is **hard-gated** on two things that are NOT yet done. Read §1, then execute in that order. **Do NOT un-gate (T10) until F1 lands AND a clean live preflight all-PASS exists.**

## §0 — State (git is truth; re-verify `git log --oneline -15`)

- **`origin/main` == `a0480f5`** GREEN (Phase-2 merged; gate CLOSED `["16:9"]`). **UNPUSHED.**
- **Local `feat/max-tier-provisioning` HEAD == `99b5d09`**, **66 ahead of origin/main, 0 behind** (all this session + operator's interleaved doc-verifier/manual line; git-serialized clean).
- **Full suite: `1892 passed, 2 skipped, 0 failed`** (verified at HEAD this wrap, `env -u GIT_INDEX_FILE .venv/bin/python -m pytest -q`). **`scripts/ci_smoke.py` exit 0.**
- **Gate CLOSED `["16:9"]`** (`cinema/aspect.py:23`) → **all portrait code is INERT** until T10. Every Phase-3 finding below is dormant behind this gate.
- Plan: `docs/superpowers/plans/2026-06-08-portrait-phase3-video.md` (T1→T10). Spec: `docs/superpowers/specs/2026-06-08-portrait-phase3-video-design.md`.

## §1 — ⭐ #1 PICKUP: the exact T10 sequence (do these IN ORDER)

T10 (append `"9:16"` to `SUPPORTED_ASPECT_RATIOS`) is the LAST task and is hard-gated. Before it:

1. **Fix F1** (operator Lane V IMPORTANT — *MUST land before T10*; see §4). Filter the **initial `target_api`** by `PORTRAIT_CAPABLE`, not just `fallback_list`. Fold the 2 same-root MINORs + a regression test. ~Lane B or Lane A (small). Spec + code-quality review. **This is dormant today but goes LIVE the instant T10 un-gates.**
2. **Fix PF-1** (preflight cost, IMPORTANT-low): `scripts/_phase3_portrait_preflight.py` `_make_ctx` → add `'cascade_retry_limit': 0` so a failing provider isn't billed twice (+30s). 2-line fix + docstring spend-count correction.
3. **(Recommended) Fix the Kling 180s timeout** (§4) so the preflight isn't flaky on Kling. Operational, not aspect.
4. **USER re-runs the T9 preflight live** (`env -u GIT_INDEX_FILE .venv/bin/python scripts/_phase3_portrait_preflight.py`) → need a **clean all-5-PASS, exit 0** table. Paste it into T10's commit body (ADR-013 evidence).
5. **T10 un-gate** (`cinema/aspect.py:23` → `["16:9","9:16"]`; flip `test_cinema_aspect.py::test_is_supported_gate_excludes_9_16_until_phase3` → `..._includes_9_16`; `test_web_server_aspect_validation.py` 9:16 PUT persists). Full suite green + ci_smoke 0. **Surface the un-gate to the USER** (it's their consequential, hard-to-reverse call — see §6).
6. **Final cross-cutting review** (BASE `a0480f5` .. HEAD), update **`ARCHITECTURE.md §8.x`** (Lane D — portrait now live), then `superpowers:finishing-a-development-branch` (user-gated push/merge).

## §2 — What shipped this session (T5a–T9 + Sora-fix), all two-stage-reviewed

Each task: implementer → spec reviewer → code-quality reviewer; review findings folded as SEPARATE commits.
- **T5a** `d06d70d` (+`5a6a2c2`) — Runway `gen4`→`gen4_turbo` (invalid SDK enum; landscape-active bugfix).
- **T5b** `4d7622a` (+`83ae87d`) — Runway both routes emit portrait ratio via `runway_ratio` (added `runway_ratio` to the `phase_c_ffmpeg.py:88` import — plan-vs-source: it was missing).
- **T6** `88c2108` (+`c4b6e2c` +`6e8c289`) — Kling no-aspect-key contract test (keyframe-driven; **test-only by my decision** — leak-catch deferred to T7 backstop). `6e8c289` repaired a self-inflicted regression (changed a test default secret without updating its assertion; caught immediately, fix-forward not amend).
- **T7** `c3902be` (+`f66cc22`) — **HOT PATH**: `PORTRAIT_CAPABLE` cascade filter + `_accept_or_reject` post-gen aspect backstop at all 11 success sites. Landscape no-op / byte-identity (Lane V `PF-2` independently confirmed). **Built via a Rule #17 read-only blast-radius workflow** (`wf_2bca4fc8`) — the cascade is recursion-based, 11 scattered success-returns, no single chokepoint; spot-checked the survey before dispatch. **F1 (§4) is the residual gap in this task.**
- **T8** `e24b9d5` (+`e14063d`) — real-ffmpeg `@skipif` proof that sub-1080 portrait (720×1280/768×1280) upscales → 1080×1920 (the characterization half was already covered; this adds the behavioral pixel proof). No prod change.
- **T9** `33b8d08` — live preflight harness `scripts/_phase3_portrait_preflight.py` (per-provider via real `generate_ai_video` + `video_fallbacks` pin; schnell smoke). Structurally reviewed; **user-run** (live spend).
- **T9-fix** `1cfe402` (+`735ddac`) — **sora-2 720p clamp** (see §3). systematic-debugging + TDD. Spec ✅ + code-quality SHIP-CLEAN; operator Lane V (extended to ..735ddac) concurs landscape-safe.

(Operator's interleaved commits — Finding-1 doc-verifier + PROGRAM-MANUAL Slice-2 anchor sweep — are disjoint: `8ef4677`..`2e83c45`, `26c318b`, `94c00fc`, `5b1a643`, `13d550b`, `32f6e52`, `78bdd83`, `202b8ed`, `05c22d8`, + coord/verification-report commits. NOT yours.)

## §3 — T9 live preflight: TWO runs, the real bug found+fixed, transient noise remains

**Run 1** (pre-fix): VEO ✅720×1280, **SORA ❌** (`create_and_poll(sora-2, 1080x1920)`→400 "only 720x1280/1280x720"), KLING ✅1216×1664, RUNWAY ✅720×1280, SCHNELL ✅576×1024.
→ **Root cause (systematic-debugging):** sora-2 supports ONLY the 720p tier; `sora_native.generate_video` defaulted `resolution=1080p`; portrait_swap was correct but the base tier was wrong. **PRE-EXISTING** (landscape sora-2 @1080p also 400'd pre-T4); anticipated by plan U6. **Fix `1cfe402`:** clamp `model==sora-2 → 720p` (assembly normalize upscales to container at render); sora-2-pro unclamped; corrected 2 T4 tests that had pinned the API-invalid 1080p sizes.

**Run 2** (post-fix): **SORA ✅720×1280 (fix CONFIRMED LIVE)**, RUNWAY ✅720×1280, SCHNELL ✅576×1024; **VEO ❌** (Vertex RAI content-filter — non-deterministic, "not charged", passed run 1), **KLING ❌** (timed out @180s while "processing" — took 178s run 1).

**Net:** all 5 providers have each produced a valid live 9:16 clip **across the two runs**; the run-2 VEO/KLING failures are **transient/operational, NOT aspect/code**. But **no single run is a clean exit-0 all-PASS** — which is what §1 step 4 needs.

## §4 — Operator's coalesced Lane V (a0480f5..735ddac): ✅ SAFE, 0 CRITICAL — but F1 gates T10

Full report: `coordination/mailbox/sent/2026-06-08T16-52-53Z-operator-to-director-verification-report.md` (+ follow-up `16-58-45Z`). 15 findings, 0 refuted, 0 hallucinations, landscape byte-identity CONFIRMED (`PF-2`). **Consumed (cursor → 13:54:31Z then 16:58:45Z); my disposition is in the wrap event `2026-06-08T17-1x` — see §5.**

- **F1 (IMPORTANT — MUST fix before T10):** the `is_portrait(_aspect)` `PORTRAIT_CAPABLE` filter (`phase_c_ffmpeg.py:160-161`) lives INSIDE `try_next_api()` and only filters `fallback_list` — **the initial `target_api` dispatch is unfiltered.** `establishing_shot` routes initial `target_api='LTX'` (`domain/scene_decomposer.py:125`, `LTX_DIRECT` :161); LTX is non-portrait-capable (excluded from `PORTRAIT_CAPABLE`), produces a 16:9 clip, and `_accept_or_reject` **fail-opens on probe failure** (`phase_c_ffmpeg.py:~1295` `return True` when dims unprobeable — my deliberate "don't strand the pipeline" choice). Path: portrait + establishing_shot + LTX 16:9 output + ffprobe fails → landscape accepted as portrait. **Narrow** (common path: probe succeeds → reject → cascade filters LTX out → works), **dormant** behind the gate, **goes live at T10.**
  **Fix direction:** add a pre-dispatch portrait-capability short-circuit mirroring the existing disabled-engine one at `phase_c_ffmpeg.py:195-201` — `if is_portrait(_aspect) and target_api.upper() not in PORTRAIT_CAPABLE: return try_next_api()`. Fold the 2 MINORs (the retry-pass `first_api` at `:193` has the same bypass) + a regression test (portrait + initial non-portrait-capable target → excluded/rejected; PF-4 gap). Operator offered to close it standalone but it's our cascade domain (you know the establishing_shot intent).
- **PF-1 (IMPORTANT-low):** §1 step 2 (preflight `cascade_retry_limit=0`).
- **MINORs:** F1/F2 retry-pass bypass (fold with F1); PF-4 test coverage (no RUNWAY_GEN4 cascade test; add the F1 regression).
- **INFO (10, good signal):** `gen4→gen4_turbo` is a landscape bugfix not a regression; INFO-1 fal `9:16` enum for veo3.1/sora-2 only confirmed by the live preflight (no unit test — INFO-1 is now LIVE-confirmed for sora-2 via run-2 PASS; veo3.1 fal path unconfirmed); INFO-2 SEEDANCE intentionally 16:9 (backstop-protected); accept_or_reject ignores rotation metadata (fine here).

## §5 — Cross-seat state (operator is LIVE; presence-over-inferred-idle)

- **Operator** finished **Finding-1 (inline-anchor verifier)** + **Slice 2** (PROGRAM-MANUAL + digests fully anchor-clean, "no drift") + ran the **coalesced Phase-3 Lane V** (above). They added `--exclude-target` to `check_doc_claims.py` (`13d550b`) to fix the all-or-nothing `--fix`.
- **Re-drift was a FALSE alarm:** my `1cfe402` sora clamp inserted ~8 lines at `sora_native.py:105`, but the operator's Slice-2d sora anchors are **def anchors ABOVE** (`SoraNativeAPI`@:29 / `generate_video`@:56) → didn't shift. Verifier reads "no drift." No re-sweep needed (my heads-up was conservative; operator verified).
- **Operator-owned NEW finding (Finding-1 Slice 3 candidate, NON-urgent):** range anchors (`file:N-M`) without a bound symbol are bounds-checked only, never def-checked → rot silently (several `sora_native.py` range anchors in the digests are +18-20 stale, PRE-EXISTING). Operator will spec a def-check-range-anchors enhancement next session. **Not yours, not Phase-3.**
- **Cursors:** director consumed through `13:54:31Z` in git; the wrap event below advances to `16:58:45Z`. Operator cursor `16:52:54Z`.
- **My owed disposition** of the verification-report goes out as the wrap event (§ below).

## §6 — The T10 un-gate is the USER's call (surface it; don't unilaterally un-gate)

T10 opens 9:16 to all production — consequential + hard-to-reverse. The user chose **handoff** rather than make the call this session. When you reach §1 step 5:
- **Gate INTENT is met:** every shipped provider has produced a valid live 9:16 clip (across 2 runs); the one real code bug (Sora) is fixed+confirmed; Lane V is SAFE (0 CRITICAL, landscape byte-identical). The VEO/KLING transient failures are operational and absorbed by the production cascade + backstop.
- **Gate LITERAL form not yet met:** no single clean exit-0 all-PASS run; F1 not yet fixed.
- **My recommendation:** fix F1 + PF-1 (+ Kling timeout), get ONE clean preflight all-PASS, THEN present the un-gate decision to the user with the clean table. Per the user-principal's "full capability" intent + the program-manual directive, surface the tradeoff rather than deciding silently.

**Kling 180s timeout (operational, recommended fix):** `kling_native.py:288` `generate_video` defaults `timeout = kwargs.pop("timeout", 180)`; the KLING_NATIVE cascade branch (`phase_c_ffmpeg.py:212`) passes no timeout → 180s. Kling i2v takes ~178–195s (right on the boundary → flaky timeout). Bump the default (e.g. 300s) for reliability. Not an aspect bug; Kling produced valid portrait (1216×1664) in run 1.

## §7 — Gotchas / D-a conventions (carry forward)

- **D-a per-seat index:** `CLAUDE_SEAT=director`, `GIT_INDEX_FILE=.git/index-director`. **Pathspec commits MANDATORY** (`git add <paths> && git commit -m "..." -- <paths>`, `-m` before `--`) — a bare commit clobbers the peer's staged work. `git update-index --no-skip-worktree <file>` if `git add` won't stage a tracked file. **`env -u GIT_INDEX_FILE` for pytest + ci_smoke.** `git read-tree HEAD` after any backgrounded Workflow.
- **Verification is a SEPARATE step from commit** — I once bundled run+commit in one bash block and a red test landed (`c4b6e2c`→`6e8c289` fix-forward). Run the test, confirm green, THEN commit.
- **ci_smoke is `scripts/ci_smoke.py`** (not repo root). It runs `check_doc_claims.py` → adding a module constant can shift a documented anchor and trip the doc-verifier (`c3902be` shifted `_veo_quota_blocked`; `--fix`ed in the same commit).
- **Operator is LIVE on disjoint files** — coordinate via mailbox + presence, not chat (Rule #19). Send a `scout-request` if you want Lane S help; signal at phase transitions.
- **Rule #17 workflows** are read-only analysis only (the T7 blast-radius survey is the model). Implementation stays on `subagent-driven-development`.

🔑 **Resume: implement F1 (initial-target filter) → PF-1 (preflight cost) → Kling timeout → USER re-runs preflight for a clean all-PASS → surface T10 un-gate to user → land T10 → final review + ARCHITECTURE.md §8.x + finishing-a-development-branch.**
