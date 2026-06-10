# Director transplant handoff — 2026-06-10 (late night): slice 1 COMPLETE + operator-verified + @ImageN desync FIXED + slice-2 plan LANDED (4-lens reviewed, adversarially executed, APPROVED) — next = EXECUTE the slice-2 plan

**Supersedes** `docs/HANDOFF-director-transplant-2026-06-10-disposition-s1-pod-chunk2-landed.md`
(its ⭐#1 (a)/(b)/(c) all discharged: Task-6 reviewed+disposed, Chunk 3 Tasks 7–12
landed+reviewed+disposed, pod/push/scheduling resolved by user directives below).

## Ground truth (verified at wrap, 2026-06-10T21:12:47Z)

- **HEAD == this wrap commit** (slice-2 plan at `567c801`; the desync fix at
  `67a179c`). **origin/main == `1f49040`, local ~26 ahead — push is
  USER/operator-gated** (the operator owns push conversion per the 19:00:27Z
  directive; do NOT push unprompted).
- **Suite: 2059 passed / 0 failed / 2 skipped at `67a179c`** (my full run;
  every commit after it is docs/coord-only). Smoke OK at wrap (21:12:47Z run).
  Doc-claims: zero drift (verified at `cf78718` + by Task-12/disposition runs).
- **Mailbox: 0 unread both directions at wrap.** My cursor **21:11:42Z**
  (the v6.0 proposal consumed; ack in my wrap event).
  `coordination/mailbox/seen/director.txt` updated 18:11:34Z → 21:11:42Z in
  this wrap commit — closing the triple-truth gap the operator's v6.0 evidence
  named (the stale seen-file was MINE).
- **Operator: ONLINE at wrap** (presence 21:12:44Z), implementing protocol
  v6.0 Tier 1 in their lane (linter + send/consume scripts + cursor folding —
  USER said "proceed", their `a5e44c6` / 21:11:42Z proposal event). Expect
  `scripts/check_coordination.py` + `coordination/bin/*` to exist soon; once
  they land, use `coordination/bin/consume-events director` instead of
  hand-rolling cursor updates.
- **Pod: STOPPED** (user verbatim "pod is stopped", operator-confirmed 502).
  **Standing directive (operator events 18:59:11Z + 19:00:27Z, both
  user-verbatim): NO pod-scheduling asks; signal pod-need via mailbox exactly
  when slice-2 offline code completes or a task hits a pod-gated step; the
  OPERATOR converts that into the single user push notification.**
- FAL per-call price for Kontext multi: **still UNVERIFIED** — needs a user
  dashboard read; surface when convenient, do not nag.

## What landed this session (director seat, chronological)

1. **`2f82572` Task-6 disposition** — my 3-lens review (spec PASS / quality
   3M+2I / anchors PASS) converged with the operator's independent Lane V
   (✅ SAFE 0C/0I). Folded: dead else-None, char_lora_strength pin, V-5
   VALUE pin (non-empty fixture), test rename + comment, new
   NO_IDENTITY_ASSET arm pin, spec:153 anchor, ARCH staleness (controller
   LOC, web_server stats + dual-bound handler anchor, eval call-site cite).
   Timeline lesson: my anchors lens "refuted" a :1864 claim that was actually
   the operator's mid-review fix `aec432e` — git-log-before-attributing
   prevented a false refutation.
2. **Chunk 3 / slice 1 completion** (sequential Sonnet implementers +
   per-task reviews, all pathspec): **T7** `feee2e2` allocator+builder
   (review PASS, byte-verbatim) · **T8** `27eee33` fallback branch (2-lens
   PASS; V-1 traced; tests/__init__.py + tests/unit/__init__.py NEW —
   verified required + CI-safe) · **T9** `9a86a0e` identity_per_char (PASS,
   pure addition) · **T10** `e74bb45` scorecard identity_multi (PASS) ·
   **disposition** `6872c3e` (golden test parametrized None+[];
   discriminating per-char stub 0.8/0.55 + exact-value assert) · **T11**
   `a43b59d` Aria LoRA registration (script byte-verbatim — I diffed it;
   3 keys live on disk: 0.55 + TOKwoman for char_b9c8bcfe9af0; project.json
   untracked at HEAD so script-only commit) · **T12** `3677bfe` ARCH §8.2
   flow (8 grep-backed anchors) + my `cf78718` scoping fix (in-frame
   registered-ref wording). Operator §8.2 method-name fix `1cf0b8a` rode in
   parallel (enhance_shot_prompt, not get_continuity_config).
3. **`67a179c` — the @ImageN desync fix** (operator Lane-V disposition
   request; verdict on the batch itself ✅ SAFE 0/82). Mechanism (firsthand
   re-verified): slots allocated from ref_paths BEFORE upload + silent
   per-ref upload failures → mid-list failure left-shifts image_urls under
   unmoved @ImageN labels → prompt addresses the WRONG face. Fix:
   upload-first sequencing (dedup-upload all candidates → filter survivors
   per char → allocate over survivors → map urls). 3 new pins (mid-list
   alignment, dropped-secondary block removal + budget reclaim, all-primary-
   failed degradation — which also killed a latent IndexError at :551).
   Folded operator MINOR-1 same commit: char_c in-frame-unregistered →
   AC3 negative invariant (unconditioned never scored) now PROVEN.
4. **`567c801` — the slice-2 implementation plan**
   (`docs/superpowers/plans/2026-06-11-p1-1-slice2-max-tier-multichar.md`,
   836 lines, 9 tasks, 3 chunks, ALL pod-free). Provenance: 4-reader
   ground-truth sweep (wf_0b4df51f-c19) → authored → 4-lens review
   (wf_e0516f27-750; the adversarial lens EXECUTED the graph-surgery code
   against pulid_max.json) → all findings folded → second-pass APPROVED.
   Scope: router max arm lifts to MAX_TIER_MULTI_LORA (+CharIdentitySpec
   lora_path/strength/trigger fields), web_server trigger persistence,
   plumbing through the max dispatch (which silently DROPS
   secondary_char_refs today — sweep finding), `_inject_secondary_loras`
   (701/702 chain, ≤0.55 clamp, basename lora_name — the registered LOCAL
   path would fail verbatim on the pod), `_inject_secondary_faceswap`
   (611/94 splice, input_faces_index "1"), `_assemble_max_prompt` (trigger
   prepend — triggers are stored but NEVER read at inference today),
   accountability pins, doc sync, pod-need signal step.
5. Coordination: events 18:42:00Z, 19:02:37Z, 20:23:37Z, 20:56:01Z,
   21:11:01Z (+ wrap event); consumed operator 18:48:13Z, 18:59:11Z,
   19:00:27Z, 20:37:07Z, 20:56:01Z, 21:11:42Z.

## ⭐ #1 PICKUP (in order)

a. **EXECUTE the slice-2 plan** — `docs/superpowers/plans/`
   `2026-06-11-p1-1-slice2-max-tier-multichar.md`, same dispatch pattern as
   slice 1 (Sonnet implementer + review per task, sequential on shared
   files, pathspec). The plan is review-hardened; trust its ground-truth
   table but re-verify anchors at execution time (its header says how).
   Two review-yield facts you MUST not relearn the hard way: the faceswap
   injector goes AFTER `_inject_post_passes` (SUPIR-absent 950 re-feed,
   quality_max.py:597-602), and the retry CANNOT break the LoRA chain
   (rewires are 700-presence-guarded; the retry re-injection is defensive).
b. **Plan Task 9 Step 5 = the pod-need signal** (mailbox → operator converts
   to the user push). Fire it exactly when slice-2 offline code completes —
   the bundle: pod-side LoRA placement (basename char_lora_fal_v2.safetensors
   into ComfyUI loras/), S2 (dual-PuLID), S3 (stacking clamp tune — still
   needs a 2nd registered LoRA, user-funded FAL training decision), P1-2
   over-cook, live multi-char max render.
c. **v6.0 director-lane items** (operator's 21:11:42Z asks, conventions
   ACKED in my wrap event): Rule #8 text update (cursor folding +
   scripts-as-canonical-writer) in docs/protocol/claude/director-operator.md
   + mailbox README sync, at your convenience once their Tier 1 lands.
   Tier-2 (presence-split hook edit) needs explicit in-session user
   authorization — whichever seat implements asks.
d. Surface to the user when convenient: the FAL dashboard price read.

## Director backlog (carried)

Spec §9 debts (pulid.json SDXL-PuLID-on-FLUX latent bug; lipsync single-face;
scorecard scalar; pipeline_status NOTE; LoRA-training cost uninstrumented) ·
budget-coverage map / ADR-022 exemptions · LLMEnsemble hermeticity ·
`check_pause()` wiring · SSE-bridge note · strategic-review P2 row
(P2-1 + P2-5 + NF-7 loggers/honesty/dead-code) is the named next arc AFTER
slice 2 · QUALITY_MAX_MULTI cost entry ships with Pass B (spec §4).

## Operational notes (this session, on top of predecessors')

- **Adversarial-EXECUTION review pays**: the plan's graph-surgery code was
  run against the real pulid_max.json by a review lens — it caught a
  CRITICAL (post_passes 950 re-feed bypassing 611) that four readers and
  the author all missed reading the same code. For plans with verbatim
  code, make one lens EXECUTE it.
- **Refutation discipline works in both directions**: two lenses refuted MY
  retry-resets-rewires theory (700-presence guard) — the plan's test would
  have shipped a factually-wrong intermediate assertion. Verify reviewer
  claims AND author theories against the code.
- **Concurrent-seat timeline trap (2nd occurrence)**: a reviewer's
  "stale anchor" finding was already fixed by the operator mid-review.
  git log -3 before attributing/refuting anything about tree state.
- **Sonnet directive holding**: ~20 subagents this session (2 ground-truth/
  review workflows × 4 + implementers + reviewers + second-pass), zero
  stalls.
- v5.9 skip-worktree auto-clear: no strikes observed this session.
- Suite arithmetic this session: 2042 → 2043 (T6 disposition +1) → 2048
  (T7 +5) → 2051 (T8 +3) → 2053 (T9 +2) → 2055 (T10 +2) → 2056 (T8/9
  disposition net +1) → 2059 (desync fix +3).

*Last verified: 2026-06-10T21:12:47Z (smoke OK my-run at wrap; suite 2059/0 =
my full run at `67a179c`, docs/coord-only commits after; mailbox/presence as
quoted; seen/director.txt synced in this commit).*
