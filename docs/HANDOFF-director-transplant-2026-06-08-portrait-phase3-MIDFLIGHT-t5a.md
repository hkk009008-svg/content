# Director Transplant Handoff — 2026-06-08 — Portrait Phase-3 MID-FLIGHT (resume at T5a)

**Why this handoff exists:** the prior director session executed Phase-3 tasks
**T1–T4** but was running in a terminal **mis-keyed as the operator seat**
(`CLAUDE_SEAT=operator`, shared `index-operator`). Per user direction the seat
is being relaunched with the proper director env. This doc is the resume point.
**You are the relaunched director. Read §1, then continue the per-task loop at T5a.**

## §0 — State (git is truth; re-verify with `git log --oneline -12`)

- **`origin/main` == `a0480f5`** GREEN (Phase-2 merged; gate CLOSED `["16:9"]`).
- **Local `feat/max-tier-provisioning`** carries Phase-3 **T1–T4 DONE + two-stage-reviewed** (each spec + code-quality reviewed; all ship verdicts):
  - `41e972b` **T1** `runway_ratio` helper (`cinema/aspect.py`)
  - `4d44929` **T2** hoist `_aspect` into `generate_ai_video` spine (no-RED plumbing)
  - `7f3a0b8` **T3** Veo native + fal 9:16 · `d77208b` T3 test-cleanup (extract `_run_veo_native`)
  - `d73b161` **T4** Sora native + fal 9:16 + force-resize fix
- **Full suite: 1848 passed, 2 failed.** ⚠️ **The 2 failures are NOT yours** — see §2.
- `ci_smoke.py` exit 0. Phase-3 files all green.
- **Plan:** `docs/superpowers/plans/2026-06-08-portrait-phase3-video.md` (T1→T10). Spec `docs/superpowers/specs/2026-06-08-portrait-phase3-video-design.md`.

## §1 — ⭐ #1 PICKUP: resume `superpowers:subagent-driven-development` at **T5a**

Remaining: **T5a → T5b → T6 → T7 → T8 → T9 → T10**. One implementer per task →
spec reviewer (reads the diff, not the self-report) → code-quality reviewer; fix-loops
as separate commits. Carry the plan's **Project Conventions** + relevant **TC-** patterns
into each implementer prompt.

**Ordering invariant (non-negotiable):** **T10 (un-gate, append `"9:16"` to
`cinema/aspect.py:23`) is LAST and hard-gated on T9's live preflight PASS.** If the gate
opens before video providers are aspect-aware, every 9:16 project regresses to
portrait-container + landscape-clips (silent quality regression). **T9 makes LIVE API
calls (spend) — PAUSE and have the USER run it; paste its PASS table into T10's body (ADR-013).**

## §2 — ⚠️ Critical gotchas (learned this session — don't re-discover)

1. **The operator seat is LIVE, working concurrently on disjoint files.** It is executing
   the **Finding-1 inline-anchor verifier** plan (`scripts/check_doc_claims.py` +
   `tests/unit/test_check_doc_claims.py`) — user-directed, **operator-owned, DO NOT TOUCH.**
   Its commits interleave with yours on the shared branch (git-serialized, clean).
2. **The 2 full-suite failures (`test_check_doc_claims.py::TestInlineAnchorsE2E::
   test_link_and_inline_same_line_distinct_both_checked` + `..._same_target_deduped`) are
   the operator's IN-FLIGHT TDD — NOT yours, NOT pre-existing, NOT a flake** (they fail in
   isolation; no random-order plugin). They go green in a later task of the operator's plan.
   When you run the full suite, **mentally filter these two**; your Phase-3 additions are all green.
3. **Plan-vs-source LINE DRIFT is real and compounding.** Every `phase_c_ffmpeg.py` edit
   shifts line numbers (T2's hoist alone moved the plan's `:423/:491/:718` → `:427/:495/:722`,
   and they keep moving as the operator/you commit). **The plan's line numbers are STALE; the
   SYMBOLS / branch-endpoint strings are STABLE.** Before each task, re-grep by branch
   identifier (e.g. `grep -n 'fal-ai/veo3.1\|fal-ai/sora-2\|seedance-2.0' phase_c_ffmpeg.py`),
   not by line number. SEEDANCE (`seedance-2.0`) is **excluded** — leave its `"aspect_ratio":"16:9"`.
4. **D-a discipline (you are now properly keyed director):** pathspec commits
   (`git add <paths> && git commit -m "..." -- <paths>`, `-m` BEFORE `--`). `env -u
   GIT_INDEX_FILE` for pytest + ci_smoke. `git read-tree HEAD` after any backgrounded Workflow.
5. **Shared bulk test file `tests/unit/test_phase_c_video_aspect.py`** has helpers
   `_run_veo_native`, `_run_veo_fal`, `_run_sora_fal` — each with an **anti-vacuous guard**
   (`assert mock.called` / `assert calls, "..."`) so a mis-mocked cascade can't pass vacuously.
   **Reuse these.** Optional bounded cleanup: parametrize `_run_fal(target_api, endpoint)` to
   fold `_run_veo_fal`+`_run_sora_fal` (cosmetic; Runway/Kling are NOT fal so it won't grow).

## §3 — Per-task anchors I already surveyed (head start; RE-GREP at your HEAD per §2.3)

- **T5a** (Runway model fix): `phase_c_ffmpeg.py` RUNWAY_GEN4 route passes `model="gen4"` —
  invalid. Installed `runwayml` SDK enum is `{gen3a_turbo, gen4.5, gen4_turbo}`; use
  `gen4_turbo`. Aspect-independent. Re-grep the SDK to confirm. PRE-REQ for T5b.
- **T5b** (Runway ratios): two routes — the gen4 route (`ratio=runway_ratio(_aspect,"gen4_turbo")`)
  and the gen3a route (`ratio=runway_ratio(_aspect,"gen3a_turbo")`). `runway_ratio` already
  landed in T1 (`cinema/aspect.py`). Runway uses the **runwayml SDK**, NOT `fal_client` — its
  test needs a runwayml-mock runner, not `_run_*_fal`.
- **T6** (Kling): new `tests/unit/test_kling_native.py` (mirror `test_sora_native.py`). **TC-7
  pattern B:** Kling caches `settings.kling_access_key/secret_key` at `__init__` AND calls
  `_generate_token` during construction → **patch settings BEFORE constructing**; attrs are
  `access_key`/`secret_key`. Assert payload has NO aspect/ratio/size key (capability is
  keyframe-driven). Optional defensive log in the KLING_NATIVE branch.
- **T7** (cascade safety — MOST NOVEL): in `generate_ai_video`'s `try_next_api` closure
  (`_aspect` is captured from the enclosing scope, hoisted in T2). (a) Filter: when
  `is_portrait(_aspect)`, drop providers not in the portrait-capable set
  `{VEO_NATIVE,VEO,SORA_NATIVE,SORA_2,KLING_NATIVE,KLING,RUNWAY_GEN4,RUNWAY}` (define as a
  module constant; exclude LTX*, SEEDANCE, Hedra). (b) Backstop helper `_accept_or_reject(result,
  _aspect)` probing via `probe_final_media`, rejecting when `is_portrait != (h>w)` → `try_next_api`;
  terminal exhausts to `None`. Mirror the existing `enabled`-filter location. Tests are green-field
  (filter-exclude / reject-retry / terminal-fail-loud / 16:9 refute) via TC-4 + TC-8.
- **T8** (upscale verify): `cinema_pipeline.py` assembly normalize — verify sub-1080 portrait
  (720×1280 / 768×1280) upscales to 1080×1920. Likely NO prod change (container dims drive
  normalize); deliverable is a TC-8 regression test.
- **T9** (preflight, **USER SPEND**): create `scripts/_phase3_portrait_preflight.py` (mirror
  `scripts/_veo_from_keyframe.py` + `_max_harness_preflight.py`). One live 9:16 clip per shipped
  provider + SPEC-3 schnell `portrait_16_9` smoke; ffprobe `h>w`; PASS/FAIL table. **PAUSE for user.**
- **T10** (un-gate, LAST): `cinema/aspect.py:23` → `["16:9","9:16"]`; flip the gate tests
  (`test_cinema_aspect.py` `test_is_supported_gate_excludes_9_16_until_phase3` →
  `..._includes_9_16`; `test_web_server_aspect_validation.py` 9:16 PUT persists). T9 PASS in body.

## §4 — Cross-seat / Lane V

- Operator's **06:25Z** event: it's **deferring its Lane V on your Phase-3 to ONE coalesced
  range-review (Rule #9 CC-1)** — trigger = your signal (mailbox) OR you finishing OR 10-min
  idle after your last feat commit. Portrait is inert (gate closed) so it's non-urgent. **When
  you finish Phase-3 (or hit the T9 user-gate), SIGNAL the operator** via a `coordination`
  mailbox event so it runs the coalesced Lane V over your full range (`a0480f5..<your-HEAD>`
  scoped to the video/aspect files).
- Director cursor advanced to **06:25:24Z** (operator's resume event consumed). 0 unread at handoff.

## §5 — Env fix (resolved this transplant)

Prior session: `CLAUDE_SEAT=operator` / `index-operator` (mis-keyed; shared the operator's
index — safe via git locking + disjoint pathspecs, but messy). You are relaunched with:
```
export CLAUDE_SEAT=director
export GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-director"
[ -f "$GIT_INDEX_FILE" ] || git read-tree HEAD
```
Confirm `echo $CLAUDE_SEAT` shows `director` before committing.

🔑 **Resume: read the plan, re-grep T5a's Runway anchor at HEAD, dispatch the T5a implementer,
continue T5a→T10, pause at T9 for the user's live preflight, un-gate LAST.**
