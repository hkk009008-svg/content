# HANDOFF — threeway SP2 (real seat↔bus wiring): spec + implementation plan AUTHORED, ready to execute

**Date:** 2026-06-25
**HEAD at handoff:** `main` @ `470f5d1f` (the plan commit). **3 commits ahead of origin/main, UNPUSHED**
(spec→spec-reviewed→plan). Verify with `git log -1` + `git rev-list --count origin/main..HEAD`.
**Live oracle:** `git for-each-ref refs/threeway/`. **Trust git, not this prose.** Re-anchor before every commit/push.

> Clean-solo session (no peer movement; the 6 `coordination/mailbox/seen/*.txt` + `.migration/` remain
> dirty from before, deliberately untouched — see §3).

## 0. TL;DR

Drove the full **brainstorming → spec → implementation-plan** flow for **sub-project 2** (the roadmap's
next code track: interactive seats emit/consume the signed bus directly, retiring the `bootstrap_emit` shim).
**No production code yet** — this session produced two committed design artifacts, both adversarially
reviewed to convergence. **NEXT = execute the plan** (subagent-driven, 4 phases 2a→2d). Two user decisions
were taken mid-flow: **single-host deployment** and **scope = T1-shim-equivalent only** (T2/T3 emission
deferred to a follow-on).

## 1. DONE + committed this session (all UNPUSHED on `main`)

| Commit | Artifact | Review |
|---|---|---|
| `136e4faa` | SP2 spec v1 ("design approved") | superseded by ↓ |
| `76513cfe` | **SP2 spec** `docs/superpowers/specs/2026-06-24-threeway-sp2-seat-bus-wiring-design.md` | 5-iteration 3-lens adversarial review; factual-grounding lens APPROVED (every load-bearing claim re-verified vs HEAD); 2 blockers caught+fixed |
| `470f5d1f` | **SP2 plan** `docs/superpowers/plans/2026-06-24-threeway-sp2-seat-bus-wiring.md` | 3-iteration 2-lens review; plan-document lens APPROVED; code-grounding verified every substrate call |

**Grounding pass (6 readers) verified the seam first-hand:** the entire bus substrate (`refstore`,
`envelope`, `keys`, `loop`, `reducer`, `gate`, `predicate`) is built + hardened. **SP2 adds only CALLERS.**
The seam = `RefEventStore` + per-seat cursor + `load_private(seat)`.

## 2. ⬅ OWED / NEXT (priority order)

1. **Execute the plan** (subagent-driven-development — fresh subagent per phase + the per-chunk Lane-V baked
   into each task). Phase order, each its own commit:
   - **2a** `scripts/consume_bus.py` (read-only; lowest risk) + `tests/unit/test_threeway_consume_bus.py`
   - **2b** `scripts/seat_emit.py` (closes the `bootstrap_emit.py:50` key-injection) + `test_threeway_seat_emit.py`
   - **2c** modify `tests/unit/test_threeway_e2e_walking_skeleton.py` in place → seat_emit+consume_bus, no shim
   - **2d** `git rm scripts/bootstrap_emit.py` + `tests/unit/test_threeway_bootstrap_emit.py` (coverage
     migrated), repoint the activation pin, doc-sync ADR — **one atomic commit**
   The plan has complete copy-paste code + bite-sized TDD steps; follow it.
2. **Push decision** — 3 doc commits (spec + plan) sit unpushed. User has NOT yet authorized a push.
3. **T2/T3 emission follow-on spec** — `attestation_revoked` + `co_sign` + `re_verify` (NEW capability the
   shim never had; the gate already enforces their dynamic verifier authority via `tier.py:64-138`). Deferred
   per the user's scope decision; write its own spec→plan when T2/T3 campaigns are actually run.
4. **Legacy-mailbox scalar-cursor follow-up** (separate, small) — `consume-events` regression check string-
   compares dash-ISO and misbehaves on the now-live scalar cursors; `status.count_unread()`/`_unread_for()`
   return `0` for scalar cursors; `check_coordination._check_cursors()` skips them. SP2's `consume_bus` is the
   authoritative bus unread surface; wiring the mailbox tools to it is this follow-up's job.

## 3. Open background (unchanged, NOT this work's scope)

The 6 `coordination/mailbox/seen/*.txt` (ISO→scalar) + `coordination/mailbox/.migration/cursor-backfill.json`
remain uncommitted (dirty since before this session; the migration is already live in `refs/threeway/cursors/*`).
Deliberately excluded from every commit this session. Still a "decide whether to commit for durable rollback"
call — unchanged from the prior handoffs.

## 4. Key decisions (carried — the design rationale lives in the spec; this is the short form)

- **Single-host, single-operator** → cursor-locality / OS-key-isolation / ref-ACL are all deferred-by-
  construction (the `advance_cursor` docstring, `refstore.py:261-274`, draws exactly this line).
- **Scope = T1-shim-equivalent** (`candidate`/`attestation`/`release_requested`/`candidate_aborted`). T2/T3
  emission deferred — it's NEW capability, and bundling it would gate shim retirement on unrelated features.
- **Seat-invoked emission** (the seat session runs the CLI, like `send-event`/`consume-events`), NOT daemons.
- **`seat_emit` is not the trust root** — it enforces only the static seat↔kind table; the gate
  (`verify_and_reduce`+`run_gate`) is the security boundary. Authority-bypass pins therefore assert
  **rc2 + zero new events**, never a gate outcome.
- **The seat determines the pair** (coordinator/operator→A, coordinator2/operator2→B); `seat_emit` loads
  `load_private(<explicit seat arg>)`, never the shim's `load_private(ev.signer.split(":")[0])`.

## 5. Sharp edges (review findings worth carrying into execution — these are why the plan is shaped as it is)

- **Verify the spec/plan against HEAD before implementing** — line numbers may drift. The plan cites exact
  substrate APIs verified this session; re-confirm if HEAD moved.
- **`re_verify` (deferred T2/T3) echoes under key `challenge_nonce`, NOT `nonce`** (`tier.py:131,138`: source
  key `nonce` → destination key `challenge_nonce`). A `nonce`-keyed echo silently fails T3. (Carry into the
  T2/T3 follow-on.)
- **`release_requested` is predicate-INVISIBLE** — `predicate.py` never reads it; its only consumer is the
  merge-gate daemon's `collect_candidate_ids` (`run_merge_gate.py:28,42,47`). So its `seat_emit` guard is a
  hygiene control, not a security boundary; pin rc2+zero-events only, never a gate outcome.
- **Non-vacuous-pin traps (the plan's mutation steps encode these):** (a) `seat_emit director attestation`
  "attestation absent from state" is VACUOUS — the gate *also* drops it; assert rc2 + zero new events. (b) The
  authority-guard's real detector is **rc2**, not the event count — removing the guard makes `director` hit a
  `SEAT_PAIR["director"]` KeyError (the test ERRORS), so the count "stays 0" either way.
- **Test scaffolding (the plan got these right; an implementer must keep them):** import as
  `from scripts.consume_bus import main` (a bare `import consume_bus` does NOT resolve — `pythonpath=["."]`);
  copy `seatkit`/`live_repo` from `tests/unit/test_threeway_gate.py` and **extend seatkit to all 9 keyed
  seats** (gate.py's copy lacks `coordinator2`/`director2`, which PAIR_B needs); `verify_and_reduce(...,
  registry_dir=str(reg), ...)` must use the **temp** registry, never the committed `coordination/threeway/keys`
  (else every event is dropped → round-trip fails, negatives pass vacuously); `seat_emit`'s argparse `choices`
  = all 6 seats so the body-level "may not emit" fires for `director`.
- **2d atomicity:** the `git rm bootstrap_emit.py` + the orphaned-test deletion + the activation-pin repoint
  must land in ONE commit, else the suite breaks on a missing import.
- Git hygiene: subagents prefix all git with `env -u GIT_INDEX_FILE`; commit with explicit pathspec, `-m`
  BEFORE `--`; re-anchor before every commit.
