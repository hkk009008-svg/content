# HANDOFF — threeway SP2 (real seat↔bus wiring): EXECUTED, 4 phases Lane-V GO, PUSHED

**Date:** 2026-06-26
**HEAD at handoff:** `main` @ `148c258b` — **PUSHED to origin/main** (`276227ae..148c258b`; 0 ahead).
Verify with `git log -1` + `git rev-list --count origin/main..HEAD`. **Live oracle:** `git for-each-ref refs/threeway/`.
**Trust git, not this prose.** Re-anchor before every commit/push.

> Solo session. The 6 `coordination/mailbox/seen/*.txt` + `coordination/mailbox/.migration/` remain dirty
> from before, deliberately untouched (see §3) — same background decision as the prior handoffs.

## 0. TL;DR

Executed the **SP2 implementation plan** (`docs/superpowers/plans/2026-06-24-threeway-sp2-seat-bus-wiring.md`)
via subagent-driven-development: a fresh implementer per phase + an independent `lane-v-verifier` per phase,
with the per-phase non-vacuous-pin mutation checks baked in. **All 4 phases landed + Lane-V GO; pushed.**
The interactive seats now emit/consume the signed bus directly via two new CLIs; the human-driven
`bootstrap_emit.py` shim is retired. Scope = **T1-shim-equivalent only** (T2/T3 emission still deferred).

## 1. DONE + committed this session (all PUSHED on `main`)

| Commit | Phase | What landed | Lane-V |
|---|---|---|---|
| `96e2e768` | 2a | `scripts/consume_bus.py` + `tests/unit/test_threeway_consume_bus.py` — seat reads bus events past its per-seat cursor, advances the local cursor | GO (a vacuous cursor pin was found + fixed + re-verified: the original tests never advanced the cursor, so `ev.seq > cursor` → `ev.seq >= 0` reddened nothing; added `test_already_seen_events_hidden_past_cursor`, folded into the same commit) |
| `126eb0a2` | 2b | `scripts/seat_emit.py` + `tests/unit/test_threeway_seat_emit.py` — per-seat signed T1 emission; loads `load_private(<explicit seat>)` validated against a static seat↔kind authority table, closing the shim's `signer`-derived key-injection hole | GO (the key-binding closure is **load-bearing**: mutating to a wrong seat key makes the gate drop the event as `invalid signature` → round-trip RED; verified first-hand + by Lane-V) |
| `e5580b98` | 2c | `tests/unit/test_threeway_e2e_walking_skeleton.py` — swapped the 4 shim calls → `seat_emit`, added an exact `consume_bus` kinds assertion + a negative-path test | GO (negative test proven non-vacuous: restoring the omitted release attestation reddens it) |
| `148c258b` | 2d | `git rm scripts/bootstrap_emit.py` + `tests/unit/test_threeway_bootstrap_emit.py`; repoint `_ACTIVATION_SCRIPTS`; **ADR-061** + ARCHITECTURE.md doc-sync; flip the SP1 spec deferred note to DONE — ONE atomic commit | GO (no live importer/caller; full suite green; coverage migrated; ci_smoke OK) |

**Whole-range verification:** full unit suite **3231 passed, 1 skipped, 0 failed**; `scripts/ci_smoke.py` → `OK`;
`scripts/check_no_ceremony.py` → clean (R1–R6); `pytest tests/ --collect-only` → 3234 collected, 0 errors
(no orphaned shim import breaks collection). No operator-facing surface (`*.sh`/OPERATIONS.md/coordination)
references the deleted shim; remaining `bootstrap_emit` mentions are historical (ARCHITECTURE.md/ADR-061
provenance notes + HANDOFF archives).

## 2. ⬅ OWED / NEXT (priority order — unchanged from the SP2-plan handoff, minus the now-done execution)

1. **T2/T3 emission follow-on spec** — `attestation_revoked` + `co_sign` + `re_verify` (NEW capability the
   shim never had; the gate already enforces their dynamic verifier authority via `tier.py:64-138`). Deferred
   per the user's scope decision; write its own spec→plan when T2/T3 campaigns are actually run.
   **Carry the sharp edge:** `re_verify` echoes under key `challenge_nonce`, NOT `nonce` (`tier.py:131,138`).
2. **Legacy-mailbox scalar-cursor follow-up** (separate, small) — `consume-events` regression check
   string-compares dash-ISO and misbehaves on the now-live scalar cursors; `status.count_unread()` /
   `_unread_for()` return `0` for scalar cursors; `check_coordination._check_cursors()` skips them. SP2's
   `consume_bus` is the authoritative bus unread surface; wiring the mailbox tools to it is this follow-up.
3. **Mailbox dirt decision** (§3) — still a "decide whether to commit for durable rollback" call.

## 3. Open background (unchanged, NOT this work's scope)

The 6 `coordination/mailbox/seen/*.txt` (ISO→scalar) + `coordination/mailbox/.migration/cursor-backfill.json`
remain uncommitted (dirty since before; the migration is live in `refs/threeway/cursors/*`). Deliberately
excluded from every commit this session.

## 4. Key decisions (carried — rationale lives in the SP2 spec + ADR-061)

- **`seat_emit` is NOT the trust root** — it enforces only the static seat↔kind table; the gate
  (`verify_and_reduce` + `run_gate`) is the security boundary. Authority-bypass pins assert **rc2 + zero new
  events**, never a gate outcome. `release_requested` is predicate-INVISIBLE, so its guard is hygiene-only.
- **The seat determines the pair** — `seat_emit` loads `load_private(<explicit seat arg>)`; `coordinator`/
  `operator` → PAIR_A, `coordinator2`/`operator2` → PAIR_B; `--pair` is cosmetic (SEAT_PAIR wins). `director`/
  `director2` may NOT emit (rc2).
- **Scope = T1-shim-equivalent** (`candidate`/`attestation`/`release_requested`/`candidate_aborted`). T2/T3
  emission deferred.

## 5. Sharp edges encountered this session (carry these)

- **Pre-existing 2d work was sitting UNCOMMITTED in the real index** while the seat-index `git status` showed
  the tree clean — and the pathspec-scoped 2a/2b/2c subagent commits flowed right past it (explicit pathspecs
  never swept it). On resume, the worktree showed real 2d-shaped changes (bootstrap_emit deleted on disk,
  ADR-061 written, docs edited). **It was REAL, not phantom** — disambiguated via: `ls` the files (gone from
  disk), `git ls-files -v | grep -v '^H '` (no skip-worktree bits), `git diff HEAD` (real content). I verified
  it against every gate, fixed one ADR factual error, and **adopted it** rather than redoing. Lesson: before a
  destructive/atomic commit, the worktree may hold a prior/peer actor's real uncommitted work your seat-index
  status hides — `diff HEAD → worktree` + verify on-disk existence before adopting or discarding.
- **ADR factual-check caught a defect in the adopted work:** ADR-061 DD-1 originally listed
  `director`/`implementer` as emitters (wrong — `director` may not emit; `implementer` isn't a seat). Corrected
  to the real emitters (`coordinator`/`coordinator2` + `operator`/`operator2`) before committing; the final
  Lane-V confirmed the ADR matches `seat_emit.py`'s AUTHORITY table mechanically. **Factually-verify an adopted
  ADR against the code, not just the gates.**
- **zsh does NOT word-split unquoted `$VAR`** — `git add -- $PATHS` passed the whole string as one pathspec and
  failed. Inline the file list directly (don't stage paths via a shell variable).
- **`build_candidate_events` emits 9 events** (`brief, assignment, candidate, attestation×2, cycle_go,
  ci_result, release_requested, release_order`), all `recipient="all"` — not the ~3 you might assume from the
  name. (This is why the consume_bus snapshot tip = 10 with `merge_completed`, and why the cursor pin's mutation
  showed `10 == 1`.)
- Git hygiene: subagents prefix all git with `env -u GIT_INDEX_FILE`; commit with explicit pathspec, `-m`
  BEFORE `--`; re-anchor before every commit. The 2d atomic commit used `env -u` + an explicit 6-path pathspec
  (the proven form) since the deletions lived in the real index.

## 6. Done criteria (whole plan) — MET

All four phase commits landed + Lane-V GO; `consume_bus` + `seat_emit` are the live seat↔bus path;
`bootstrap_emit.py` and its test are gone with coverage migrated (`test_threeway_seat_emit.py`'s
`candidate_aborted` family); the E2E proves T1 brief→merge with no shim; `ci_smoke` + `check_no_ceremony` clean;
full threeway unit suite green; pushed to origin/main. T2/T3 emission remains a deferred follow-on (§2.1).
