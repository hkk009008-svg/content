# HANDOFF — operator2 (Pair B), 2026-06-14 (§4 nan-gate) — READ FIRST AS OPERATOR2

**Seat:** `operator2` = Pair-B **operator** (independent verification + doc-sync + mailbox reports).
**Lane:** VIDEO + ASSEMBLY + DELIVERY (`phase_c_ffmpeg`/`phase_c_assembly`, video-API selection, `lip_sync.py`,
dialogue/TTS, `cinema/shots` continuity, `web_server`/`cinema_pipeline` video orchestration). Pair partner =
**director2** (leads recon/briefs; you verify). Protocol: `docs/protocol/claude/four-seat-extension.md`.

---

## ⭐ SESSION OUTCOME — PM7 §4 (nan-gate) LANDED + director2 VERIFIED **GO**

director2's PM7 priority is §2(done)→§3(done)→§4→§5. **§4 is now DONE + GO.** §3's authoritative verify
(owed at last handoff) was DISCHARGED this session (director2 `741d818`/`00:07:56Z`, triple-convergent GO).

### My 3 commits (all local; push user-gated, origin at `fec4e76`)
- **`a812ee4`** — §4A fix. Shared `_finite_or` in **`cinema/context.py`** beside `get_project_setting` (director2's
  `999a249` home; byte-for-byte identical to `quality_max:191` so Pair-A's import-swap is a verified no-op). 5 sites:
  `lip_sync._sync_gate_settings` (lipsync_validation_threshold, MAJOR), controller `identity_strictness`/
  `coherence_threshold`/`color_drift_sensitivity`, `capability_scorecard` bars. NaN/inf defeats gates because
  `score < NaN`/`>= NaN` are both False and `float(NaN)` succeeds (try/except misses it). **Did NOT touch
  `quality_max.py`** (Pair-A lane).
- **`81688c6`** — mailbox: verify-request to director2 + to-all attribution correction.
- **`c8dd329`** — doc-sync: 10 ARCHITECTURE.md anchors my a812ee4 insert shifted (the deferred carry, DISCHARGED
  once ARCHITECTURE.md was clean at HEAD; ci_smoke green; all were ungated markdown-link anchors).

### TDD / verification
- `tests/unit/test_nan_gate_pairb.py` (16 RED→green), incl. a **behavioral** diagnose_clip proof (NaN coherence
  floor → `recs=[]` RED → fires `regenerate` GREEN). Blast-radius 114 passed / 5 xfailed; no import cycle.
- **director2 §4 GO** (`wf_99bc3ff7-fe4`, 5 refute-first lenses, `ca77f9a`/`00:33:09Z`): 4 SAFE + the budget
  sweep-find. **identity_strictness "Pair-A confirm" flag SATISFIED** (director2: it's a true no-op on all
  production-valid input; the cc `identity_threshold` NaN-default passthrough is UNREACHABLE — hardcoded constant).

## ⭐ THE OPERATOR VALUE-ADD — independent sweep proved §4A INCOMPLETE
My completeness sweep (`wf_2ca5b0ae-e26`, 4 area-sweepers + reconcile, Sonnet) confirmed all 5 §4A sites EXACTLY
and found **6 NOVEL MAJOR sites the brief MISSED** in `cinema/auto_approve.py` — a different *shape* of the bug
(rule-registration `if config.<field> > 0:`, where NaN makes `nan>0` False → the veto rule is NEVER registered →
keyframe/motion/final gates silently pass everything, budget veto disabled). **Verified by direct read**, not just
the agent. Coordinator independently re-confirmed (`899d643`/`00:36:49Z`). Sites: `image_min_composite:287`,
`image_min_composite_fallback:285`, `image_max_spent_multiplier:326`, `motion_min_identity:346`,
`motion_min_motion_score:360`, `final_min_lipsync:388`. **xfail(strict)-pinned** `tests/unit/test_auto_approve_nangate_xfail.py`
(R-VERIFY-TIER B) — NOT edited (cross-lane Pair-A image/identity; matches director2's "don't widen §4, sequence
auto_approve separately" steer).

director2's verify then found a **7th** sibling: **NaN `budget_limit_usd` → whole-session unbounded spend**
(`core.py:101` float(nan) survives, `cost_tracker.py:170` bool(nan)=True stores it). xfail-pinned `e28f4fa`
(`tests/unit/test_budget_nan_gate_xfail.py`). And f1addd3's mouth-energy scorer has **D1-D4** defects (director2
`wf_46f1d3ec-145`; D1 = silent opencv-absent fall-through to 1.0, re-creating the bug it claims to fix; pinned `8304fea`).

## ⭐ NEXT — director2's CONSOLIDATED HARDENING EPIC (my call: EPIC > §5; replied `03:02:49Z`)
director2 proposed ONE "auto_approve + lipsync + nan-gate hardening" epic (cross-lane, Pair-A co-sign), after §4.
**My recommendation (sent): epic over §5** — it's 7 MAJOR safety holes vs §5's LOW disk-leaks. Sequence by readiness:
1. **f1addd3 D1 WARNING** — my lane (lip_sync `_score_mouth_energy` outer except), NO co-sign, ready NOW. TDD first.
2. **auto_approve `_get_finite` chokepoint** (one fix, all 6 sites; uses the landed `_finite_or`) — needs Pair-A co-sign.
3. **budget-NaN** — blocked on a DESIGN CALL (recommend fail-safe-block-on-non-finite per cost_tracker:167-169's
   stated philosophy); needs Pair-A/coordinator co-sign.
4. **S2** (best-take credits `dialogue_audio_in_clip`, auto_approve.py:502) — sequence with #2.
5. **D3 calibration** — pod-gated (pod up but ComfyUI 502 per op-1); GATING experiment. D3 + `final_min_lipsync:388`
   are the same gate from opposite angles.
6. **§5 tmpfile** (LOW) — last. (Sites from director2 PM7 §5: `audio/dialogue.py:685-687` move cleanup to finally;
   `lip_sync.py:307/618`; `cinema_pipeline.py:1270/1306/1406` _concat_* clobber; `phase_c_ffmpeg.py:984`.)
This is a roadmap-priority + cross-lane-co-sign + pod call → wants the **principal's** steer; surfaced, not started.

## CARRIES
- **Epic sequencing** — my recommendation is sent; needs director2 confirm + principal priority steer + Pair-A
  co-signs (auto_approve gates + budget design call) + a pod burn for D3.
- **diagnose_clip latent seam (director2-flagged, NOT a §4 defect):** reads `_diag_settings` from `self.project`
  (controller.py ~:2252) not the refreshed local `project` (~:2178) — harmless IF `_refresh_project_snapshot`
  updates core.project in-place; a future look, not blocking.
- **quality_max:191 import-swap** — Pair-A's to do anytime (shared `_finite_or` landed + verified no-op).
- **2 director2 minors (your call to pin):** `flux_guidance` NaN→ComfyUI node 60 (Pair-A workflow_selector, may be
  fixed by `bf1034a`); `transition_duration` NaN→ffmpeg-rejects→hard-cut (our lane, self-mitigated).

## SHARP EDGES (this session)
- **zsh does NOT word-split unquoted `$FILES`** — `git add $FILES` / `git commit -- $FILES` passed the whole
  string as ONE bogus pathspec (silent no-op + a "did not match" fatal). Use a LITERAL file list for pathspec
  commits, never a shell var (or `${=FILES}`). Composes with the explicit-pathspec rule.
- **Explicit literal pathspec held against a HOT tree + a polluted per-seat index.** Across the session HEAD moved
  325f750→…→2c485fa under me (Pair-A committed has_character mid-work). `git commit -F - -- <literal files>`
  committed ONLY my 6 files; Pair-A's uncommitted `quality_max.py`(+39)/`test_quality_max_nan_gate.py`(+241) +
  a phantom index mailbox-deletion all stayed out. `git commit -- <file>` commits the WORKING-TREE version,
  bypassing a phantom staged version → safe for the surgical doc-sync too.
- **Phantom index pollution is the norm here.** `git status` showed MM/D/?? on ~15 files that were byte-identical
  to HEAD (`git diff --no-index <(git show HEAD:path) path` proved it). Do NOT `git read-tree HEAD` (solo-only;
  4 seats active). Trust `diff --no-index`/`ls-tree`, not `git status`.
- **Don't attribute shared-tree WIP by the PLAN.** Coordinator `6061a85`/`00:12:14Z` mislabeled Pair-A's quality_max
  WIP as my §4 (because my §4 *plan* mentioned the :191 swap). I never touched quality_max; corrected `81688c6` →
  coordinator acknowledged. Verify the commit/blame trail, not the plan.
- **The brief is a curated list; the sweep finds the missed family.** §4A brief was ~57% complete (5 of 11+ sites).
  Fan-out "find ALL of pattern X, classify vs the known list" beats a single reviewer at completeness — same as §3
  (4 missed siblings). This is the operator's structural value-add; worth a workflow even on a tight brief.
- **ci_smoke RED ≠ your fault.** Mid-session ci_smoke was RED purely from Pair-A's uncommitted quality_max anchor
  drift (untouched by me); it went green when their PM8 doc-sync landed. Check WHOSE file before owning a red gate.

## COORDINATION STATE @ wrap
HEAD `2c485fa`; **23 ahead of origin** (`fec4e76`; push USER-gated — do NOT push). My 3 commits LANDED local.
**Multi-pair-wrap boundary**: coordinator (Session-5 `a554ee8`), director-1 (PM8 `10d4450`), operator-1 (`2c485fa`)
all wrapped. director2 ONLINE (pair lead); §4 GO recorded; my epic recommendation sent `03:02:49Z`. ci_smoke GREEN.
Pod STARTED by principal but ComfyUI HTTP 502 (Pair-A lane). My cursor `seen/operator2.txt` → 2026-06-14T02:59:25Z.
