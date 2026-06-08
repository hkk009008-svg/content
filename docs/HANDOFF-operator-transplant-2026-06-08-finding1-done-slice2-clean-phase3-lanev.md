# Operator transplant handoff — 2026-06-08 — Finding-1 DONE · Slice 2 manual fully anchor-clean · Phase-3 Lane V reported

**READ FIRST IF PICKING UP AS OPERATOR.**

## 0. State at wrap (git-verified)

- **Branch** `feat/max-tier-provisioning`. **HEAD = `99b5d09`**, **ahead 64** of `origin/feat` (UNPUSHED — push is strategic-seat/user call).
- **`origin/main` = `a0480f5`** GREEN (unchanged this session).
- **§15 smoke:** `OK`. **doc-verifier suite:** `81 passed` (`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_doc_claims.py -q`). **Manual:** `check_doc_claims.py docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md` → **"All anchors checked — no drift."**
- **Gate:** `cinema/aspect.py:23` `SUPPORTED_ASPECT_RATIOS = ["16:9"]` — **CLOSED**; all Phase-3 portrait code INERT until T10 un-gate (director-owned, pending user preflight re-run).
- **Mailbox:** operator **0 unread**; cursor **`16:52:54Z`**. **Nothing owed.**
- **presence:** operator=wrapping (this wrap). Director=LIVE earlier (paused at T9 user-gate); git > presence.

## 1. What this session shipped (all committed, UNPUSHED on feat)

### A) Finding-1 inline-anchor verifier — HARDENED (review → fix → Lane V → close)
The user-directed verifier (`scripts/check_doc_claims.py`) is now corruption-safe + self-converging:
- **Slice 1 independent Rule #9 cold review** (workflow) — 17 findings, all adversarially confirmed, 0 refuted. Surfaced **CRITICAL `ADV-1`** (`--fix` silently corrupts a doc when two inline anchors on one line share a bare token + stale line but resolve to different files — reachable on PROGRAM-MANUAL's 20 bare `controller.py` anchors), **IMPORTANT `CQ-1`** (crash on tracked-but-absent basename candidate), **MINOR `ADV-2`** (unclosed-fence EOF silent-skip). The 2 flagged test-layout deviations were confirmed LEGITIMATE (mutation-tested).
- **Fix** `26c318b` (ADV-1 span-based `--fix` + CQ-1 OSError guard) + `94c00fc` (ADV-2 EOF warning). TDD throughout.
- **Lane V on the fix** (workflow) — 0 CRITICAL / 0 IMPORTANT / 0 refuted; one MINOR `NC-MINOR-1` (non-corrupting nested-overlap non-idempotency) → closed by `5b1a643` (`run(fix=True)` now loops `_apply_fixes` to convergence, bounded at 10).
- **`--exclude-target` feature** `13d550b` — `--fix` can hold back drifts whose target matches a substring; enabled the selective stable-subset sweep below.

### B) Slice 2 — PROGRAM-MANUAL.md + digests FULLY anchor-clean (382 issues closed)
- `32f6e52` **2a** — 287 stable def_drift (`--fix --exclude-target phase_c_ffmpeg.py sora_native.py`, deferring the volatile while director was mid-Phase-3).
- `78bdd83` **2b** — 43 ambiguous/missing/oob path qualifications (Lane B implementer + my review). Rules: `controller.py` line >700 → `cinema/shots/`, else prose-check; the 4 root re-export shims (`project_manager`/`scene_decomposer`/`dialogue_writer`/`character_manager`, all 9-LOC) → `domain/X.py`; `performance.py` → `cinema/phases/`; `shots/` → `cinema/shots/`.
- `202b8ed` **2c** — 12 **claim-level prose** fixes (Rule #18 Guard-1, each source-verified): the deleted `format_dialogue_for_voiceover`/`dialogue_to_narration_text` (pruned `45c2299`) reframed REMOVED; 6 root-shim refs mis-pointed at `domain/X.py:1-9` corrected; `base.py`→`motion_render.py:17/185` (where "F2b"/"Tier F NEW-2" actually live).
- `05c22d8` **2d** — the 47 director-volatile anchors, swept once the director signaled Phase-3 source settled.

### C) Coalesced Phase-3 Lane V (CC-1) — `verification-report` sent (`e228fe9`, event `16-52-53Z`)
Cold Rule #9 second-opinion over **`a0480f5..735ddac`** (video/aspect surface; 1712+ LOC), 4 adversarial dimensions, 0 refuted:
- **✅ SAFE: 0 CRITICAL; landscape byte-identity CONFIRMED** (`PF-2`). The arc is provably inert at 16:9.
- **2 IMPORTANT (both DORMANT behind closed gate):**
  - **`F1`** — `_accept_or_reject` probe-failure-accepts hole: the `PORTRAIT_CAPABLE` filter (`phase_c_ffmpeg.py:160-161`) only filters `fallback_list` inside `try_next_api`, NOT the initial `target_api`. A non-portrait-capable initial target (LTX via `establishing_shot` routing) at portrait + probe failure on a written file → landscape clip accepted as a portrait take. Reproduced E2E. **Director should fix before T10 un-gates** (filter the initial target too). Folds with 2 related MINORs (retry-pass `first_api` `:193`) + a regression test.
  - **`PF-1`** — `scripts/_phase3_portrait_preflight.py:97-98` `_make_ctx` doesn't set `cascade_retry_limit=0` → a failing provider is billed twice + 30s sleep; docstring under-counts spend. Lower urgency (preflight already run once).
- **3 MINOR / 10 INFO** (mostly confirmations: `gen4→gen4_turbo` is a landscape bugfix; configs verified). Sora clamp `1cfe402` reviewed landscape-safe (a bugfix — pre-fix landscape sora-2 @1080p also 400'd).
- **Disposition (Rule #15):** director owns the Phase-3 code; I recommended F1 fold-before-T10, PF-1 standalone. **Awaiting director disposition.**

## 2. ⭐ #1 PICKUP — nothing is owed; the live items are gated on others

- **Director:** T10 un-gate pending the **user's preflight RE-RUN** (confirm sora-2 720p PASSes live). My `F1`/`PF-1` await director disposition (Rule #15). If the director ships an F1/PF-1 fix, run a **cold Lane V** on it (independent 2nd opinion).
- **Finding-1 Slice 3 candidate** (task #6; spec'd in mailbox `16-58-45Z`): the verifier **def-checks line anchors but NOT range anchors** (`file:N-M` without a bound symbol is bounds-checked only → silently rots). Concrete stale examples found: `sora_native.py` digests range anchors durations cited `:81-84` actual `:100` (digests:2357), `download_content` cited `:146-151` actual `:169` (digests:2359), download_url dead-code `:133-141` (extraction removed). +18-20 off, PRE-EXISTING. **Principled fix:** enhance `check_doc_claims.py` to resolve the prose-named symbol within a cited range + flag if it moved out — catches the class like Slice 1 caught inline anchors. Then a one-pass digests range-anchor sweep. Spec next session.

## 3. Gotchas (carry forward)
- **D-a per-seat index:** `git read-tree HEAD` before EVERY tracked-file commit; `git add <paths>`; `git commit -m … -- <pathspec>` (pathspec MANDATORY, `-m` before `--`). A wholesale `git commit -am` reverts the peer's work. No drops this session.
- **pytest:** `env -u GIT_INDEX_FILE .venv/bin/python -m pytest …` (seat index breaks tmp-repo git fixtures). `.venv/bin/python`, not system python3.
- **`--exclude-target`** (new, `13d550b`): `check_doc_claims.py --fix --exclude-target <substr>` holds back drifts whose target file contains `<substr>`. Use to defer anchors into files a concurrent seat is editing (turns all-or-nothing `--fix` into all-but-the-churning-ones).
- **Presence-vs-mailbox:** the director's *active-but-quiet* execution (long subagent dispatches, no commit for 60+ min) reads as live via presence freshness, NOT commit recency — do NOT infer idle from commit silence (Rule #19). A background `git`/mailbox monitor that watches for the explicit completion signal (mailbox event / presence wrapping / un-gate commit) is the right "wake me when Phase-3 lands" mechanism — do NOT use HEAD-idle (false-fires on active execution).
- **Verifier-clean ≠ true** (Rule #18 Guard-1): every workstream this session had a green-check-invisible issue caught only by adversarial source verification (the CRITICAL `--fix` corruption, deleted-symbol prose, root-shim mis-anchors, range-anchor blind spot). Always spot-check a "clean" claim against source.

## 4. Mailbox / cursor
cursor `16:52:54Z`; 0 unread. Last director event processed: `16-52-54Z` (T9-gate / re-drift heads-up / Lane V range → 735ddac). My sends this session: `06bdfc5` (Slice 2 done), `e228fe9` (verification-report 16-52-53Z), `99b5d09` (follow-up 16-58-45Z) + this handoff. **D-a-safe commits:** `git read-tree HEAD` → `git add <paths>` → `git commit -m … -- <paths>`.
