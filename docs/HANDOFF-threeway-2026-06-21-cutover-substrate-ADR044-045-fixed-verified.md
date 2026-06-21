# HANDOFF — Threeway cutover substrate: 2 MAJORs FIXED+VERIFIED (ADR-044) + Rule-13 sibling CLOSED (ADR-045)

**Date:** 2026-06-21
**Pushed:** `origin/main` @ `e3e5e650`, 0 unpushed. Three commits this session on `main`:
`d3a157e1` (ADR-044 fix), `e3e5e650` (ADR-045 fix + ADR-044 rows verified), preceded by `99d92795`
(audit handoff). The `.claude/settings.json` `codex:false` toggle was excluded from every commit
(pre-existing, unrelated).
**Verification at handoff:** full threeway suite **329 passed / 0**; full repo suite **3129 passed / 0**
(`b8b5uj2jo`); `ci_smoke` + `check_no_ceremony` clean.

> Trust git, not this prose. On resume: `git fetch && git log -1 && git rev-list --count origin/main..HEAD`.

---

## 0. TL;DR

Drove the threeway program from "all defects closed, two audits to run" to "control plane AND its cutover
substrate audited, and the two MAJORs the substrate audit found are fixed + independently verified."

- **Two adversarial audits ran** (read-only, real-gate): composition `wf_2ca48247-f19` → **0 emergent gaps**;
  cutover-substrate `wf_ce0bba9f-0ac` → **2 confirmed MAJOR**.
- **ADR-044 closed both MAJORs** (`d3a157e1`): (1) `cutover._teardown` non-atomic + masked-cause →
  best-effort-per-ref + `TeardownError` chained `from original`; (2) `idempotency_key`/`_request_fingerprint`
  omitted `revokes_event_id`/`supersedes_event_id` → a distinct-target revoke/supersede was silently
  deduped → include both in both keys. TDD red→green.
- **Independent Lane-V re-verify** (`wf_be151f19-aa7`: 2 worktree mutators + critic) → **GO/NITS, both rows
  VERIFIED**, non-vacuity proven by 5 isolating mutations, Rule-13 sweep found no dedup twin — and surfaced a
  **distinct pre-existing half-flip gap**.
- **ADR-045 closed that sibling** (`e3e5e650`): `run_cutover`'s validation steps (`total_order` /
  `iso_to_seq_map` / `_read_iso_cursors`) ran outside the teardown guard; moved inside the cursor `try`.
  TDD red→green.

## 1. Inventory status (all threeway rows)

- `threeway-cutover-teardown-nonatomic-masks-cause` → **verified** (Lane-V GO `wf_be151f19-aa7`).
- `threeway-refstore-dedup-omits-revoke-supersede-target` → **verified** (Lane-V GO `wf_be151f19-aa7`).
- `threeway-cutover-pretry-strand-no-teardown` → **fixed** (ADR-045; TDD red→green + full suite; a Lane-V
  pass is optional — mechanical move-into-try with a non-vacuous pin, R-VERIFY-TIER does not require a 3rd
  independent pass on a fix this simple).
- All prior threeway rows remain `fixed`/`verified` (ADR-036..043). **No open threeway defects.**

## 2. Verification artifacts (R-MEASURE — committed)

- `logs/audit-wf_2ca48247-f19-threeway-composition.json` — composition audit (0 emergent gaps).
- `logs/audit-wf_ce0bba9f-0ac-threeway-cutover-substrate.json` — cutover-substrate audit (the 2 MAJORs +
  the flip-readiness verdict + `preconditions_for_flip`).
- `logs/verify-wf_be151f19-aa7-adr044-lane-v.json` — Lane-V GO/NITS, 5 mutations, Rule-13 sweep.

## 3. NEXT — operationalization only, all user/external-gated (unchanged shape)

The control plane + its cutover substrate now have **no open tracked defect**. Remaining work is the same
operationalization the ADR-043 handoff named, plus the audit's **flip preconditions**:

- **Live cutover — HOLD for explicit user confirmation** (irreversible-only-with-effort). Audit
  `wf_ce0bba9f-0ac` verdict = CONDITIONALLY SAFE; ADR-044 records the **preconditions_for_flip**:
  (a) FREEZE the coordination tree for the flip window (no concurrent `refs/threeway/*` writer — belt-and-
  suspenders now that teardown is best-effort + the pre-try gap is closed); (b) clean `divergence` check;
  (c) `force=True` dry-run asserting `ready_to_flip` against a throwaway clone; (d) an OUT-OF-BAND pre-run
  ref snapshot for manual recovery; (e) chief/overseer registry-key provisioning.
- **Scope-(b) operational layer:** dual-chief apps + overseer nonce/roster EMITTER + chief-key provisioning.
- **Wire the gate driver:** `run_gate` still has **zero production callers**.

Residual NOT driven by the audits (named, no silent caps): refstore REMOTE push-CAS under concurrent
multi-writer contention; backfill partial-then-retry resumability end-to-end; gitcas merge-tree determinism
beyond the fixtures.

## 4. Config (this session, personal/local — NOT pushed)

`permissions.defaultMode: "bypassPermissions"` in **`.claude/settings.local.json`** (gitignored), per user
request. Takes effect next session start; first engage may show the one-time `skipDangerousModePermissionPrompt`
dialog.

## 5. Sharp edges (durable)

- **Adversarially re-verify your OWN fix — it found the next layer AGAIN.** The Lane-V Rule-13 sweep on the
  teardown fix surfaced the pre-cursor-try strand gap (ADR-045) that the substrate audit itself missed. The
  layered-defect lesson held for a fourth time this session (composition→store-dedup→teardown→pre-try).
- **`logs/` is gitignored; audit artifacts are committed via `git add -f`** (matches the tracked
  `logs/discovery-wf_*.json`). `git status` won't show a new `logs/*.json` as untracked.
- **Test-count reconciled to a concurrent PEER commit, not environment.** Session-start collected 321; a
  concurrent same-identity commit `bfd5efbe` (test-only: +2 gate-level T3 negatives in
  `tests/unit/test_threeway_gate.py`, 15:59Z, NO overlap with my files) raised the baseline to 323; +5
  ADR-044 tests + 1 ADR-045 test → **329** (321+2+5+1, exactly). It sits between my handoff `99d92795` and my
  fix `d3a157e1`, so my fixes built on top of it (clean FF pushes, no file overlap). LESSON: a mid-session
  baseline shift is a peer-commit signal FIRST — check `git log` for an interposed commit before blaming the
  environment. Reconcile via `git diff --name-only HEAD` (it showed only my files) — that habit prevented
  building on a false picture even while my first *explanation* of the +2 was wrong.
- **`idempotency_key` is load-bearing across ADR-037/038/044** — change it only with the Rule-13 dedup-
  surface sweep (gate `seen_ids` keys on id-alone; Slice-1 `store.py` has no request-content dedup; remote
  CAS shares the same computed keys). The Lane-V sweep confirmed the surface is exactly
  `{idempotency_key, _request_fingerprint}`.

## 6. Where the truth lives

`DECISIONS.md` ADR-044 + ADR-045 (full rationale + verification). `docs/REMEDIATION-INVENTORY.md` (the 3
rows). The three `logs/` artifacts above. `ARCHITECTURE.md` §13A prose verified still accurate (recompute-
and-verify dedup described generically; `revokes/supersedes_event_id` remain unsigned) — no edit needed.
