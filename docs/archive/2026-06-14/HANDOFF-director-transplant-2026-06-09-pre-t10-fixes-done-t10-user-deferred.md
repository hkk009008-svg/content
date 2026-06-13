# Director transplant handoff — 2026-06-09

**Pre-T10 fixes DONE + adversarially reviewed (clean); T10 un-gate USER-DEFERRED
(now gated ONLY on a clean live preflight — all code blockers cleared).**

---

## 0. State at wrap (verified, not remembered)

| Fact | Value | How verified |
|---|---|---|
| Branch | `feat/max-tier-provisioning` | `git status` |
| HEAD | **`cde6dec`** | `git rev-parse HEAD` |
| Ahead of `origin/feat` | **72 commits, UNPUSHED** | `git rev-list --count origin/feat..HEAD` → 72 |
| `origin/main` | `a0480f5` GREEN | `git rev-parse origin/main` |
| `origin/feat/max-tier-provisioning` | `4596b84` (stale; behind local) | `git rev-parse origin/feat...` |
| Gate `cinema/aspect.py:23` | `SUPPORTED_ASPECT_RATIOS = ["16:9"]` — **CLOSED** (portrait INERT) | `sed -n 22,23p cinema/aspect.py` |
| Suite | **1895 passed / 0 failed / 2 skipped** | `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/ -q` |
| `ci_smoke` | **OK** | `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` |
| Mailbox (director) | **0 unread**; cursor `16:58:45Z` | newest event is my own `17-13-00Z-director-to-operator`; no newer operator→director |
| Presence | both seats `wrapping`/offline at wrap | `coordination/presence/*.md` |

**Both seats are offline.** I (this session's director) held the full loop unilaterally
per "When the other party is offline."

---

## 1. ⭐ #1 PICKUP — T10 un-gate (USER-DEFERRED this session; code is READY)

**The user chose "Defer T10, wrap + handoff"** when I surfaced the decision (AskUserQuestion,
this session). So T10 did NOT land. Everything that gated T10 *in code* is now done — the
ONLY remaining gate is the **USER-run live preflight returning a clean exit-0 all-5-PASS**.

**Do, IN ORDER, next session (only once the user is ready to authorize ~$2–4 live spend):**

1. **Surface T10 to the user again** (it's consequential + hard-to-reverse; the user owns it).
2. **User runs the live preflight** — `python scripts/_phase3_portrait_preflight.py`
   (or inline `! python scripts/_phase3_portrait_preflight.py`). Need a clean **exit-0
   all-5-PASS** (4 video providers + 1 FAL image smoke). Paste its output into the T10
   commit body (ADR-013 evidence — the plan §Task 10 makes this a hard precondition:
   *"Do not land T10 without it."*).
3. **Land T10** per `docs/superpowers/plans/2026-06-08-portrait-phase3-video.md` §Task 10
   (TDD): flip the gate tests (`tests/unit/test_cinema_aspect.py:29-32` → assert
   `is_supported("9:16") is True`, `"4:3"` still False; `test_web_server_aspect_validation.py`
   → a 9:16 PUT now persists, no 400) → run RED (gate still `["16:9"]`) → implement
   `cinema/aspect.py:23` → `["16:9", "9:16"]` → run GREEN + full suite + `ci_smoke` exit 0 →
   commit `feat(aspect): un-gate 9:16 — portrait delivery live (preflight PASS in body)`
   with the T9 PASS table in the body.
4. **Final cross-cutting review** (BASE = baseline of the whole Phase-3 arc, HEAD = T10).
5. **`ARCHITECTURE.md §8.x` doc-sync** (Lane D / same PR) — portrait now LIVE end-to-end.
6. **`superpowers:finishing-a-development-branch`** — and surface the push decision (feat is
   72 ahead, UNPUSHED; push is USER-GATED — the user picked "defer" over "push feat first"
   this session, so it remains explicitly deferred).

**Why the preflight should pass clean now (vs. T9 run-2):** the two *operational* flakes that
kept T9 run-2 from a clean exit-0 are FIXED this session — KLING 180s timeout (`6c76ec1`) and
the double-bill-on-failure (`60c2496`). The third (VEO Vertex RAI content-filter) is
non-deterministic (passed run-1), not a code issue; it may or may not recur. All 5 checks
have each produced a valid live 9:16 across the two T9 runs → capability already proven.

---

## 2. What shipped this session — the pre-T10 fix stack (5 commits, all green)

| SHA | Type | What | Verification |
|---|---|---|---|
| `46e3b87` | **F1** (operator Lane V IMPORTANT + 2 same-root MINORs) | Top-level pre-dispatch portrait-capability guard in `phase_c_ffmpeg.generate_ai_video` (`:216-228`): `if is_portrait(_aspect) and target_api.upper() not in PORTRAIT_CAPABLE: return try_next_api()`. Mirrors the disabled-engine short-circuit (`:208-214`). Closes the initial-target hole AND the `:193` retry-pass `first_api` MINOR (that branch re-enters `generate_ai_video` from the top → re-passes the guard). + PF-4-gap regression test. | TDD: RED reproduced the fail-open landscape-accept (`[ASPECT-BACKSTOP]…accepting`) → GREEN. |
| `60c2496` | **PF-1** (IMPORTANT-low) | Preflight `_make_ctx` pins `cascade_retry_limit=0` so a failing pinned provider can't double-bill (`sleep(30)` + 2nd call). | Behavioral: `_make_ctx('9:16').global_settings == {aspect_ratio, cascade_retry_limit:0}`. Prod contract already unit-tested at `test_phase_c_video_aspect.py:711`. |
| `6c76ec1` | **Kling** | `generate_video` default poll timeout `180→300s` (i2v ~178-195s; 180 timed out flakily). | TDD: RED default 300 (was 180) → GREEN. |
| `917d575` | **Kling** (review-fix) | Honor `timeout=` override — pop `timeout` BEFORE `create_image_to_video(**kwargs)` (it has a fixed signature; leaving it raised TypeError→silent None). | TDD with `autospec=True` (plain MagicMock hid the bug). |
| `cde6dec` | **PF-1** (review-fix) | Docstring provider count `5→4` (4 video + 1 FAL image = 5 checks). | `len(_PROVIDERS)==4` at source. |

**`917d575` + `cde6dec` came from my own Rule #17 adversarial-review workflow** (see §3) —
they are fix-on-OWN-findings, both MINOR, both about text truthfulness (one false capability
claim masking a latent bug, one miscount). Neither was a behavioral defect.

---

## 3. Rule #17 adversarial review (substituted for the offline operator Lane V)

Ran a Rule #17 read-analysis workflow (`wf_d8e2efb1-ca7`) over `594f074..6c76ec1` — 5 cold
dimensions (F1 completeness / F1 landscape-safety / F1 test-quality / PF-1 correctness /
Kling scope) + per-finding adversarial refutation, grep-cited evidence, output spot-checked
at source before acting (guardrail 2). **Result: 0 behavioral defects.** 13 INFO findings were
all *confirmations* — notably one agent **empirically reproduced RED** by stripping the F1
guard and re-running the regression test (strongest "the test actually guards it" signal);
another walked termination (no infinite recursion); landscape byte-identity confirmed.
2 MINOR truthfulness findings survived → closed as `917d575` + `cde6dec`.

**This does NOT substitute for the operator's cross-seat Rule #9 Lane V** (guardrail 3) —
that pass is RELEASED to the next operator (see §4).

---

## 4. Cross-seat coordination (operator)

- **Operator's Rule #9 Lane V on `46e3b87..cde6dec` (the 5 pre-T10 commits) is RELEASED** to
  the next operator — my Rule #17 self-review is independent input, not the cross-seat pass.
  Sent a closure + Lane-V-release mailbox event this session (director→operator).
- **F1 + PF-1 are CLOSED** (operator flagged them in their coalesced Phase-3 Lane V
  `verification-report` `16-52-53Z`; I owned the fix per Rule #15 option (a)).
- **Operator-owned, non-urgent (their Slice 3):** range-anchor verifier gap in
  `check_doc_claims.py` (range anchors `file:N-M` are bounds-checked only, never def-checked →
  silent rot; several `sora_native.py` digests anchors are +18-20 stale). NOT Phase-3. Theirs.
- Director cursor `16:58:45Z`, 0 unread. No new operator→director events to consume.

---

## 5. Open carry-forwards

- **T10 un-gate** (#1 above) — user-deferred; code-ready; needs user preflight.
- **`feat` is 72 ahead of `origin/feat`, UNPUSHED** — push is USER-GATED (user picked defer
  over push this session). Durability risk noted. D-a-safe push = `git push origin <sha>:feat/max-tier-provisioning`
  (NO checkout while a peer is active).
- **VEO Vertex RAI content-filter** — non-deterministic preflight flake (not code); watch on re-run.
- **On-pod 9:16 latent validation** (manual, GPU-up) — still open from the Phase-2/3 arc.
- **Operator range-anchor Slice 3** (their lane).
- **`ARCHITECTURE.md §8.x`** portrait-live update — part of T10's finish, not before.

---

## 6. Operational notes (D-a per-seat index active)

- `CLAUDE_SEAT=director`, `GIT_INDEX_FILE=.git/index-director`.
- **`env -u GIT_INDEX_FILE`** for pytest + ci_smoke (the per-seat index confuses them otherwise).
- **Pathspec commits** mandatory under D-a: `git commit -m "…" -- <explicit paths>` (`-m` BEFORE
  `--`); wholesale `git add -A` would clobber a peer's staged work.
- **`git read-tree HEAD`** before each tracked commit, and **after any Workflow** (the workflow
  may touch the index).
- **Verify-THEN-commit** as separate steps (Rule #7 pre-commit re-verify caught the operator's
  benign `594f074` landing during my session-start orientation).
- Presence: set your `status` + `current_task`; `status: wrapping` at session end; the hook bumps
  `updated`/`head_at_write` every tool call (it will race your Edits to the presence file —
  expected, low-value, don't fight it).

— director (wrapping)
