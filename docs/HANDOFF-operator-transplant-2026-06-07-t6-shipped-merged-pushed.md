# Operator Transplant Handoff — 2026-06-07 (T6 advisory SHIPPED → merged → pushed; presence hook fixed)

*Last verified: 2026-06-06T17:58Z (local 2026-06-07 JST). **`origin/main` = `origin/feat` = `main` = `feat` = `5f53afa`** — fully synced + public (clean FFs). Trunk green: `ci_smoke OK` at HEAD; full suite **1634 passed / 2 skipped** verified at `caad497` (the commits since — `3c93401`/`35dbeaa`/`5f53afa` — are coord docs + a `.claude/` hook fix, no pipeline code). Working tree clean except untracked scratch (`docs/adr/`, `scripts/_*.py`). This handoff SUPERSEDES `HANDOFF-operator-transplant-2026-06-06-part4-capability-shipped.md` — its OPEN #1 (T6) is DONE.*

## ★ READ FIRST — what this session shipped (all on public trunk `5f53afa`)

1. **T6 — Remediation Advisory (the user-chosen feature). COMPLETE, reviewed, merged, pushed.**
   Full design-first cycle (brainstorm → spec → plan → subagent-driven-development), then merged to `main` + pushed.
   - **Goal:** operator-assist **advisory** (NOT autonomous retry). **Engine:** hybrid — deterministic advisory (`negative_prompts`) inline on identity-gate failures + in `diagnose_clip`, PLUS opt-in LLM **"Deep diagnose"** (`evaluate_generation_quality`). Built on the EXISTING diagnose flow (`diagnose_clip` / `api_diagnose_shot` / ReviewStage "Diagnose" button) — **no new endpoint**. Both dormant levers are now wired.
   - **Commits:** spec `47afe84` + `4d3e129` · plan `7f46346` · 7 tasks `ddfeceb` `fa738f6` `89b110e` `8d18e57` `10a0eb4` `570b2a5` `a935360` · isolation fix `7c48692` · Lane-D/staleness doc-sync `caad497`.
   - **Reviews:** per-task spec + code-quality (each cold), + a **final cross-cutting review ✅** (key-by-key contract match across build→persist→serve→consume; no regressions; non-goals respected).
   - **Design docs:** `docs/superpowers/specs/2026-06-06-t6-remediation-advisory-design.md` + `docs/superpowers/plans/2026-06-06-t6-remediation-advisory.md` (both cold-reviewer-✅).
   - **Two deferred Minors** (non-blocking, NOT fixed): FE `diagnosis` state widened to `any` (cleaner: extend the `Diagnosis` interface with optional fields); `handleDiagnose`/`handleDeepDiagnose` lack try/finally so loading state sticks on a network error (the missing-finally is a PRE-EXISTING pattern, not introduced by T6).

2. **§9 defect — CLOSED (by the user's spawned background task).** `api_regenerate_shot` claimed `negative_prompt` support its code dropped. Fixed: `3d98d72` (docstring) + `6dae9f8` (actually threads `negative_prompt` through the keyframe regen path). NOT T6's code; flagged + spun off during T6 design.

3. **Presence-freshness hook — FIXED (`35dbeaa`).** Root cause of "both seats keep seeing each other offline": `.claude/hooks/update-state.sh` stamps `coordination/presence/<seat>.md` only when `CLAUDE_SEAT` is set; this session launched WITHOUT it → presence silently no-op'd ALL session. Fix: seat resolves `CLAUDE_SEAT` (preferred) ELSE a per-session marker `.claude/presence-seat.<CLAUDE_CODE_SESSION_ID>` (collision-safe — keyed by the session id the hook inherits). Verified LIVE (presence now bumps every tool call; `current_task`/`status` left alone per Rule #19).

4. **Merge + push (user-gated, user-authorized this session):** FF `main` `3fa46f4`→`caad497`→`5f53afa`; pushed `origin/main` + `origin/feat`. Everything synced at `5f53afa`.

## Where the program / branch stands

- **`origin/main` = `origin/feat` = `main` = `feat` = `5f53afa`.** The whole accumulated program is on public trunk: T6 + Part 4 (Capability dashboard) + T1/T3/T4 + §9 fix + presence-hook fix + docs.
- `main` is no longer "untouched at 3fa46f4" — it now carries everything (this session merged + pushed it per user go).

## NEXT — operator-claimable, priority order (design-first / $0 unless noted)

1. **U3 — audio LUFS + format probe** (the prime follow-on eyed during the Part-4 brainstorm; carried from the prior handoff). ffprobe the final mp4 → scorecard dims for −14 LUFS / 1920×1080 / h264+aac; un-grey the `audio_lufs`/`format_codec` tiles in `CapabilityConsole.tsx`. Mirror an existing `build_capability_scorecard` dimension.
2. **T6 deep-path live dogfood** — the LLM "Deep diagnose" (`evaluate_generation_quality`) is wired + unit-tested (LLM mocked) but never run against a REAL LLM on a real failed-identity take. A live test (needs an API key + a project with a failed keyframe) would confirm the `advisory_deep` prose is actually useful + tune it. $ (one LLM call per click).
3. **T1 Phase-B — live LoRA-gate calibration** (GPU pod, **spend-gated**). Tune thresholds vs real ArcFace + one real train→validate→persist. ⚠️ pod `07ed667` was 404 — verify Novita before spend.
4. **Optional UI:** `hires_fix_steps` React slider (T3 left it API-only); live-SSE auto-refresh of the Capability dashboard; LoRA strength-sweep viz.
5. **T6 deferred Minors** (low priority, see §★1): the FE `any` widening + the diagnose try/finally.

## NOT operator (director-lane / their call)

- **Director's HELD post-merge Lane V** over T6 (`7f46346..a935360` + `7c48692`) + Part 4 + T1/T3/T4. Offered in coord events; trunk is already reviewed (operator's final cross-cutting ✅), so it's a second opinion, not a missing gate. Do NOT drive it.
- **Future merge-go.** `main` == `feat` now; the next merge decision arises only when `feat` advances again — user-gated.

## Coordination state

- **0 unread for operator** (cursor `2026-06-04T02:34:22Z` == latest to-operator event; no new director→operator since 2026-06-04).
- **Operator sent 3 coord events this session:** `T11:29Z` (T6 executing + status correction), `T12:21Z` (merge-go record — the FF leaves no merge commit, so that event IS the merge record), `T17:40Z` (push-done). Director processes per Rule #8 when back.
- **Director was OFFLINE all session** (presence stale `head_at_write: 8647a0f` / `updated: 11:07Z`, zero activity). Operator drove the merge under the offline-provision + direct user authorization. When director returns: relaunch with `CLAUDE_SEAT=director` to get auto-presence + pick up their Lane V.

## Gotchas / precedents (carry forward)

- ⚠️ **LAUNCH WITH `CLAUDE_SEAT`.** The #1 lesson this session: a session launched without `export CLAUDE_SEAT=<seat>` makes the presence hook silently no-op → both seats mis-read liveness for hours. The hook now self-heals VIA a per-session marker, but ONLY if the session records its seat. **Next operator: either (a) launch with `CLAUDE_SEAT=operator` (`coordination/README.md` §"Per-seat launch"), OR (b) early in the session run `printf operator > ".claude/presence-seat.$CLAUDE_CODE_SESSION_ID"`.** Then presence auto-bumps.
- **Presence file churns every tool call now** (the hook bumps `head_at_write`/`updated`). Expect "file modified since read" on Edits to `coordination/presence/operator.md` → Read-then-Edit. Only touch `current_task`/`status` (hook owns the other two).
- **Shared tree:** commit with explicit pathspec; never `git add -A`. **`-m` flags MUST precede the `--` pathspec** (`git commit -- <paths> -m ...` fails — git treats `-m` as a pathspec).
- **§15 smoke = `.venv/bin/python scripts/ci_smoke.py`.** No FE test runner — frontend gate is `cd web && npx tsc --noEmit && npm run build`.
- **T6 surface for follow-ups:** advisory dict `{failure_reason, suggested_negative_prompt, suggested_pulid_adjustment, source}` is built by `llm/negative_prompts.py::build_remediation_advisory`; persisted at `cinema/shots/controller.py:~670` (keyframe) + attached in `diagnose_clip` (`~:1855`); deep path at `diagnose_clip(deep=True)` (`~:1913`); endpoint `api_diagnose_shot` threads `deep`; FE in `web/src/components/pipeline/ReviewStage.tsx`. Config `AdvisoryConfig` in `cinema/auto_approve.py`.

## Verification at write (ADR-013)
```
$ git rev-parse --short HEAD main origin/main origin/feat/max-tier-provisioning  → all 5f53afa
$ git status -sb | head -1   → ## feat/max-tier-provisioning...origin/feat/max-tier-provisioning (even)
$ .venv/bin/python scripts/ci_smoke.py   → OK
$ git log --oneline -10      → 5f53afa coord · 35dbeaa hook-fix · 3c93401 coord · caad497 doc-sync · a935360..89b110e T6 (7 tasks + isolation fix) · (below) 6dae9f8/3d98d72 §9
$ cat coordination/mailbox/seen/operator.txt   → 2026-06-04T02:34:22Z (== latest to-operator event → 0 unread)
  full suite 1634 passed / 2 skipped verified at caad497 this session (pipeline code unchanged since)
```
