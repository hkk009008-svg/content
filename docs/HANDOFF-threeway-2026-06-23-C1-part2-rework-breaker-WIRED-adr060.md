# HANDOFF — threeway: C1 COMPLETE (rework breaker WIRED on authority-aware aborts) [ADR-059 + ADR-060]

**Date:** 2026-06-23
**HEAD at handoff:** `main` @ `bc7c30b7` (== origin/main; pushed, 0 ahead / 0 behind). Verify with `git log -1`.
**Live oracle:** `git for-each-ref refs/threeway/`.

> Trust git, not this prose. Re-anchor (`git fetch`; ahead/behind) before every commit/push.
> Clean-solo session (GIT_INDEX_FILE unset, 0 skip-worktree) — no peer movement throughout.

## 0. TL;DR

**C1 is now COMPLETE.** Part 1 (ADR-059, `2ab8bb79`) closed the `candidate_aborted` forge/cross-pair
merge-DoS. Part 2 (ADR-060, `bc7c30b7`) WIRES the rework circuit-breaker on that authority — a
repeatedly-failing brief now escalates to humans, and a FORGED abort can neither trip the breaker (a
forced-ESCALATE merge-DoS) nor inflate a rival brief-version's count. Both independently Lane-V'd GO.
**Both pushed. User ratification owed for both ADRs.**

## 1. DONE + verified this session (both on origin/main)

| Deliverable | Commit | Verdict | Evidence |
|---|---|---|---|
| ADR-059 — `candidate_aborted` read-time abort authority (C1 Part 1) | `2ab8bb79` | Lane-V GO (4 GO+1 NITS) | `logs/verify-adr059-candidate-aborted-authority-lane-v.json` (`wf_4b612e08-fa2`) |
| ADR-060 — wire the rework circuit-breaker (C1 Part 2) | `bc7c30b7` | Lane-V GO (3 GO+2 NITS) | `logs/verify-adr060-rework-breaker-lane-v.json` (`wf_556f8109-0bd`) |

ADR-060's three components:
- **A** `threeway/rework.py` + `reducer.py`: `should_escalate`/`rework_count` take the REDUCED state (was
  raw events); count only DISTINCT candidates that are authoritatively aborted (`is_aborted`) AND whose
  AUTHORITATIVE candidate matches the target brief_id/brief_version. New `EffectiveState.aborted_candidate_ids()`.
- **B** `scripts/bootstrap_emit.py candidate_aborted`: coordinator-signed abort, payload `{"candidate_id": cid}`
  (idempotency-key distinctness — candidate_id is NOT in the fingerprint, `envelope.py:105`; empty payload
  would dedup/lose the 2nd abort on RefEventStore). Clean rc1 on bad key/contention/bad repo-dir.
- **C** `scripts/overseer_plan.py`: `main()` computes `should_escalate`; `plan(escalate=)` WITHHOLDS a new
  `cycle_go` and prints `⚠ ESCALATE` when tripped — fail-safe / requirement-adding only (ADR-058 DD-1).

**Why trustworthy:** TDD RED→GREEN (14 new pins for Part 2; 8 for Part 1); executed mutations redden the
authority filter, the brief_version match, and the cycle_go withhold. Full threeway suite **416 passed,
1 skipped**; ci_smoke OK; check_no_ceremony clean. Each Part's adversarial Lane-V = 5 independent non-author
verifiers, each REPRODUCING the exploit (monkeypatch to the loose behavior). All NITs from both Lane-Vs were
fixed in-commit (Part-2: abort-CLI bad-repo totality → caught + pinned; stale breaker prose → updated; a
test comment).

## 2. ⬅ OWED (priority order)

1. **User ratification of ADR-059 + ADR-060** — both landed solo-Tier-A (core control-plane), ratification
   owed. The one scope decision worth a glance: abort authority is **executing-coordinator-only**
   (overseer cannot abort; ADR-059 DD-4) — the documented default.
2. **Sub-project 2** (real seat↔bus wiring) — LARGE; design forks (consumption model, mailbox↔bus
   transition). Write a spec + surface before building. `bootstrap_emit` (incl. the new abort subcommand)
   is the TEMPORARY shim it replaces.
3. **Hardening C2–C7** — mostly infra/ops the USER must drive (CI attestor, ref-ACL/branch-protection,
   external trust anchor, key rotation); C7 (richer attestation payloads) modifies the audited gate →
   full adversarial Lane-V. Full detail: `docs/HANDOFF-threeway-2026-06-23-remaining-tracks-roadmap.md`.

## 3. Open background (NOT this work's scope)

- 6 `coordination/mailbox/seen/*.txt` (ISO→scalar) + `coordination/mailbox/.migration/` rollback manifest
  remain uncommitted (dirty since before this session). DELIBERATELY excluded from both fix commits.
  Decide whether to commit for durable migration rollback — a separate call.

## 4. Sharp edges (this session)

- **A line-adding fix shifts ARCHITECTURE.md hard anchors TWICE** — ADR-059's `is_aborted` and ADR-060's
  `aborted_candidate_ids()` each pushed `authoritative_candidate` down (132→159→165); ci_smoke `def_drift`
  caught both. Re-check the gated anchors after every reducer edit; fix in the same change.
- **`candidate_id` is NOT in the idempotency fingerprint** (`envelope.py:105`) — any new per-candidate
  coordinator fact (the abort emit) MUST carry `candidate_id` in payload or RefEventStore silently dedups
  the 2nd one. TDD's RefEventStore-based fixture caught this (it would have been a lost-abort prod bug).
- **New CLI code paths don't inherit the old paths' pre-flight** — `candidate_aborted` skips `_candidate_set`,
  so it lacked the rev_parse pre-flight that turns a bad repo into a clean ValueError; a Lane-V totality
  lens caught the resulting traceback. Fixed by catching `subprocess.CalledProcessError`.
- **This change falsified its own predecessor's prose** — ADR-059 said the breaker was "UNWIRED / no live
  callers"; ADR-060 makes that false. A regression-lens verifier caught the stale claim. Update predecessor
  prose in the same change that invalidates it.
- `logs/verify-*.json` gitignored → `git add -f`; own-seat commit = explicit pathspec (kept mailbox cursors
  out); `env -u GIT_INDEX_FILE` on all threeway python; re-anchor before every push.
