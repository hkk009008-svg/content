# HANDOFF — Threeway 2 deferred cutover residual gaps CLOSED (ADR-050/051, Lane-V GO)

**Date:** 2026-06-22
**HEAD:** `main` @ `374478cf` — **2 commits this session, UNPUSHED** (`efdf8e33` fix + `374478cf`
Lane-V GO / NIT-fix / verified-reconcile). Parent `2b82b527` was the prior handoff.
**Verification at handoff:** full threeway suite **349 passed / 1 skipped / 0 xfailed**; `ci_smoke` +
`check_no_ceremony` clean; both fixes **independently Lane-V GO** (3/3 unanimous, mutation-proven).
The `.claude/settings.json` `codex:false` toggle stayed excluded from every commit (pre-existing local
change, unrelated) — same as the prior session.

> Trust git, not this prose. On resume: `git fetch && git log -1 && git rev-list --count origin/main..HEAD`.

---

## 0. TL;DR

Did the one in-lane proactive item the prior handoff (§5) named: the **follow-up adversarial round on
the 2 deferred dormant cutover-substrate gaps** (`threeway-cutover-total-order-congruence` +
`threeway-cutover-seen-filename-seat-key`). Both were critic-flagged but **NOT reproduced E2E**. Both
now reproduced against HEAD (TDD red), fixed, ADR'd, independently Lane-V GO, rows reconciled
`verified`. The signed-bus **activation** path (the other §5 item) is untouched — still user-gated +
irreversible.

## 1. What landed (2 commits)

| Commit | What |
|---|---|
| `efdf8e33` | **ADR-050 (total-order congruence) + ADR-051 (seat-key canonicalization)** — see below. 9 files (3 prod, 3 test, 3 doc). |
| `374478cf` | **Lane-V GO + 2 NITs closed + rows `fixed`→`verified`** + the `logs/` Lane-V artifact (`git add -f`). |

**ADR-050 — total-order congruence.** "Which sent/ files are events, in what order" was computed with
TWO predicates: the projector's append order used the full `_EVENT_NAME_RE` grammar (skip
non-matching); the cursor numbering (`cursor_backfill._sent_names`→`total_order`) used a loose `_TS`
leading-ts regex (raise on no-ts, but COUNT a ts-prefixed file). A file matching `_TS` but not
`_EVENT_NAME_RE` (non-roster sender) was skipped by the projector yet counted by the cursor numbering
→ +1 seq shift in the archived `iso_to_seq` → ADR-049's `force=True` re-run sourced the authoritative
cursor refs from that shifted map → cursors point off after cutover. **Fix:** ONE shared classifier
(`legacy_projector.ordered_event_names`/`is_event_filename`/`ts_of`); `project()` +
`cursor_backfill.total_order`/`_sent_names` refactored onto it; the local `_TS` removed → congruence by
construction. **Deliberate contract change (surfaced):** skip-vs-raise unified + tightened — a clean
non-event `.md` (no ts) is skipped, a ts-prefixed-malformed `.md` now RAISES `MalformedEventFilename`
(never silently drop a suspected event in a one-way irreversible migration). Live corpus has zero
non-grammar files, so this is a no-op safety net on clean input.

**ADR-051 — seat-key canonicalization.** The seat→cursor map used `{p.stem: …}` in two sites
(`cutover._read_iso_cursors` + `cursor_backfill.backfill`). `p.stem` mis-splits `operator.foo.txt`;
`Operator.txt` → phantom key; and `cutover.py` did `seq_map.get(seat, 0)` → a missing/misnamed roster
seat silently got cursor 0 and re-processed the ENTIRE migrated bus. **Fix:** one shared
`cursor_backfill.canonical_seat_cursors` (+ `SEATS` const + `SeatCursorError`) used by both sites —
strips exactly `.txt`, lowercases to the roster, RAISES on a stray/case-collision; `cutover._SEATS`
aliases `cursor_backfill.SEATS`; the cursor loop raises `SeatCursorError` on a missing roster seat
(empty `seen/<seat>.txt` = the explicit seq-0 opt-in).

## 2. Verification artifacts (R-MEASURE)

- `logs/verify-wf_7c8fa7bd-9f0-cutover-residual-lane-v.json` — the Lane-V: 3 independent Sonnet
  verifiers (congruence / seat-key / completeness critic), each re-deriving GO from the diff + a fresh
  suite, mutation-testing every guard by reverting the COUPLED production files to pre-fix
  (`git checkout efdf8e33~1 -- …`) and confirming the pin reddens. Unanimous GO; all 7 live pins RED on
  pre-fix, GREEN on fix.
- The 8 new pins ARE the E2E reproduction (the gaps were "NOT reproduced E2E" before this session):
  4 ADR-050 (projector, backfill, 2 cutover) + 3 ADR-051 (case-canon, phantom-reject, missing-seat) +
  1 NIT (empty-seen→seq-0 opt-in). 1 is `test_canonical_seat_cursors_rejects_case_collision`
  (self-skips on a case-insensitive FS).

## 3. Inventory status (threeway rows)

- `threeway-cutover-total-order-congruence` → **verified** (ADR-050, Lane-V GO).
- `threeway-cutover-seen-filename-seat-key` → **verified** (ADR-051, Lane-V GO).
- **NEW open row `threeway-divergence-seen-stem-phantom-key`** (MINOR, dormant) — Rule-13 sibling of
  ADR-051 surfaced by the impact-analysis grep: `divergence.py:110` `{f.stem for f in seen.glob('*.txt')}`
  has the same phantom-key/case fragility, but it is the READ-ONLY divergence checker (NOT the cutover
  write-path; `diverge()` is only called from tests). Filed separately rather than scope-creeping the
  irreversible-cutover fix. Fix direction in the row. All 3 Lane-V lenses confirmed the scope-out.
- All prior threeway rows remain `verified`/`fixed` (ADR-036..049).

## 4. NEXT

- **Push** `efdf8e33` + `374478cf` to `origin/main` (2 unpushed) — **user-gated** (asked at handoff;
  not pushed without the user's go-ahead, per the harness push rule).
- **`divergence.py:110`** follow-up (reproduce E2E → fix → Lane-V) — when the divergence checker is next
  touched, or proactively. Lower stakes (read-only).
- **Signed-bus activation** — UNCHANGED from the prior handoff §5: user-gated + irreversible (provision
  keys, run the cutover, wire CI to sign `ci_result`, deploy the merge-gate runner, Slice-3 scope-b
  runtime). NONE started. The cutover substrate is now one layer more hardened (these 2 gaps closed).

## 5. Sharp edges (durable, from this session)

- **"Two predicates for one set" is a recurring shape.** ADR-050's root cause was the append path and
  the cursor path each computing "is this an event" independently. The fix is to collapse to ONE shared
  function (congruence by construction), not to patch the +1 symptom. Look for this whenever two paths
  must agree on the same set.
- **Mutation-test via coupled-file pre-fix revert.** The cleanest non-vacuity proof was
  `git checkout efdf8e33~1 -- <files>` (the ACTUAL pre-fix code), run pin → RED, restore. Revert
  COUPLED files together (post-fix `cursor_backfill` imports from `legacy_projector`; reverting one
  alone breaks the import and masks the true RED behind a collection error).
- **Line-adding fixes shift ARCHITECTURE anchors.** `legacy_projector` +46 lines moved `def project`
  63→109; §13A.5 re-anchored. `ci_smoke` happened not to gate that specific anchor, but the staleness
  discipline fixes it regardless — run `ci_smoke` + grep ARCHITECTURE for the touched file's anchors
  before each commit.
- **Surface the contract-tighten, do not block on it.** The projector skip→raise-on-malformed change
  is a deliberate data-integrity call for the irreversible migration; recorded in ADR-050 + the commit
  + this handoff. Made the call, kept moving (no AskUserQuestion).
- `logs/` is gitignored → `git add -f` the R-MEASURE artifact (as the prior session did).
- Workflow prompts are plain JS strings — built with `[...].join('\n')` arrays of single-/double-quoted
  lines, avoiding literal backticks/`${}` inside, per the prior handoff's parser warning.

## 6. Where the truth lives

`DECISIONS.md` ADR-050/051 (full rationale + Lane-V GO). `docs/REMEDIATION-INVENTORY.md` (2 rows
verified + 1 new open MINOR). `logs/verify-wf_7c8fa7bd-9f0-cutover-residual-lane-v.json`.
`ARCHITECTURE.md` §13A.5 (re-anchored; shared-classifier prose). The new pins in
`tests/unit/test_threeway_{legacy_projector,cursor_backfill,cutover}.py`.
