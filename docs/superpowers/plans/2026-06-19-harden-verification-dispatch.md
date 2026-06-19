# Harden the Verification Dispatch Protocol — Implementation Plan

> **For agentic workers:** REQUIRED execution model below differs from the generic
> subagent-driven default and says why. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Lift the repo's verification-dispatch protocol from "Level 4" to a self-executing,
machine-consumable, fail-aware contract by hardening the reviewer template + the operator
verification-report vocabulary, closing the five assessed weaknesses **and** the keystone
anti-ceremony gap the assessment missed (reviewer never re-runs the implementer's pins).

**Architecture:** One canonical verdict enum (`pass | issues | unable_to_verify`) carried by a
new `reviewer-result/1` JSON schema and rendered (not duplicated) at every human surface.
The five assessment weaknesses + four found gaps collapse onto the *same ~15 lines* of
`reviewer.md`, so the template is rewritten **atomically by one author**. Protocol vocab,
disposition matrix, a reciprocal implementer change, and one mechanical anti-ceremony guard
(`check_no_ceremony.py` R5) land as coordinated edits. The JSON *consumer* (and the
fabrication-detection re-run) is deferred to a tracked follow-up so we never ship a schema no
instrument executes (that would itself be ceremony — ADR-028).

**Tech Stack:** Markdown protocol docs + templates; one Python detector script
(`scripts/check_no_ceremony.py`, stdlib only: `ast`, `pathlib`); `DECISIONS.md` ADR log.

---

## Provenance

This plan is the durable form of an adversarial design pass (`wf_b89b9c6c-128`: 5 per-weakness
designers + 2 cross-cutting critics, ~537k tokens) over the external "Level 4 of 5" assessment.
Every current-state claim below was grep/Read-verified against `feat/threeway-slice2-exec` and
`main` (R-EVIDENCE).

## Decisions locked (user-approved 2026-06-19)

1. **Canonical enum** = `pass | issues | unable_to_verify`. Emoji (`✅/⚠️/❌/⛔`) and seat
   `GO/NITS/FAIL` are *human render* of it via a documented 1:1 map — **no fifth vocabulary**.
   Severity stays a separate axis (`issues[].severity`).
2. **W4 = Option (a)** — name the existing `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
   trailer (the only sanctioned one). **No** `Verified-by:` trailer (reviewer is read-only/cold;
   Option b costs 4+ files + CI + becomes status-without-evidence ceremony).
3. **M-RERUN-PINS is in scope as CRITICAL** — the reviewer must re-execute the implementer's
   named pins with `--runxfail` + a one-fact mutation non-vacuity check. Without it the whole
   schema is "elegant ceremony."
4. **Mechanical guard now, consumer later** — ship `check_no_ceremony.py` **R5** (UTV-never-a-row-
   status) in this change; **defer** the `scripts/` JSON consumer + fabrication-detection re-run +
   **R6** (report-cites-executed-pin) to a tracked follow-up. Mailbox-level JSON block stays
   **OPTIONAL**; reviewer-subagent emit is **MANDATORY**.
5. **Re-review the live branch** — after the template lands, run a hardened re-review of
   `feat/threeway-slice2-exec` `612d6109` (the original subject) to prove the new dispatch
   exercises pin re-execution against the refstore/envelope pins.

## Execution model (deviation from generic subagent-driven-development — stated per skill)

The design already came from fresh-context agents (the workflow); `main` holds the exact target
text. Re-dispatching that text to fresh *implementer* subagents adds telephone-game risk and a
multi-subagent shared-index corruption vector (the documented 2026-06-12 failure) for **zero**
independence benefit — the independence that matters lives in the **review**. So:

- **Implement** in main context (single author on a fresh branch), one commit per task, TDD for
  the one code task. This is the repo's own director-authors / operator-verifies model and the
  "tightly-coupled work → stay in main context" R-ORCH carve-out.
- **Verify** by dispatching independent Lane-V reviewers (spec-compliance + code-quality, in
  parallel, on Opus) over the diff — never trusting the author's report.

## File structure / blast radius

| File | Change | Why |
|---|---|---|
| `docs/templates/claude/reviewer.md` | **atomic rewrite** | All 5 weaknesses + 4 gaps collide here; one author. |
| `docs/protocol/claude/director-operator.md` | modify `:89`, `:681`, `:692-693`, `:790-823` | UTV vocab + RE-DISPATCH disposition. |
| `docs/protocol/agents/director-operator.md` | modify `:77-78` | Two-tree mirror of the Lane-V status vocab. |
| `docs/templates/claude/implementer.md` | add to Report Format | Emit pin selectors so M-RERUN-PINS has a handle. |
| `scripts/check_no_ceremony.py` | add `rule_utv_not_a_row_status` (R5) | Mechanically forbid UTV laundering past the wave gate. |
| `DECISIONS.md` | append **ADR-032** | Record the schema + UTV disposition + reviewer-executes-pins doctrine. |

There is **no** `docs/templates/agents/reviewer.md` (verified) — the reviewer template is
claude-tree-only; the new RESULT SCHEMA section carries an "agents copy, when created, inherits
this verbatim" marker so a future agents reviewer cannot silently drift.

---

## The canonical normalization (the spine every task references)

- **Verdict enum (wire value):** `pass` | `issues` | `unable_to_verify`.
- **Render map (prose only, do not re-encode):** `pass` = ✅ ; `issues` = ⚠️ (worst severity minor) / ❌ (worst severity critical/important) ; `unable_to_verify` = ⛔.
- **Seat shorthand:** GO = `pass` · NITS = `issues` (all minor) · FAIL = `issues` (≥1 critical/important) · RE-DISPATCH/ESCALATE = `unable_to_verify`.
- **Severity is a separate axis** (`issues[].severity` ∈ critical/important/minor). A single reviewer's verdict is **binary** (`pass`/`issues`); the operator synthesis derives the band. `unable_to_verify` is **orthogonal to severity** — a property of the *run*, never a defect.
- **Severity → inventory map** (document in the deferred consumer, do **not** rename either vocab): critical→CRITICAL, important→MAJOR, minor→MEDIUM.

---

## Task 1: Atomic rewrite of `docs/templates/claude/reviewer.md`

**Files:** Modify `docs/templates/claude/reviewer.md` (whole file).

The rewrite preserves the relocated-verbatim header note and the existing Git-hygiene block,
and adds, in this order, the following sections. (Five separate Edits are impossible — they
mutate overlapping anchors at `:38`, `:45-49`, `:48`, `:65-71`, `:70`.)

- [ ] **Step 1: Add `## Canonical verdict vocabulary (read first)`** — the spine above, verbatim,
  including the "UTV must NEVER become an inventory row `status` (ADR-027 wave-gate bypass)" line.

- [ ] **Step 2: Add `## Independence + verify-before-asserting (include verbatim in EVERY dispatched reviewer prompt)`** — closes **M-COLD-CONTEXT**:
  - cold-context independence (Rule #9): do NOT trust the implementer's report; do NOT cite or
    anchor on any other reviewer's findings; form the verdict only from the diff under review.
  - verify-before-asserting (CC-2): grep/Read to confirm any symbol/file/line exists before
    claiming it; an unverified "X is a bug" is a hallucination — verify or label unverified.
  - "Dispatch on Opus" standing note (reviewer capability is load-bearing).

- [ ] **Step 3: Extend the Git-hygiene block** with one sentence: the Evidence-preamble git calls
  (`rev-parse` / `status --short` / `show` / `diff` / `cat-file -e`) are read-only and obey the
  `env -u GIT_INDEX_FILE` prefix; they introduce no state-changing git.

- [ ] **Step 4: Add `## RESULT SCHEMA (emit verbatim as the LAST thing in your reply)`** — closes **W1**.
  The schema (one object, `role` discriminates spec vs code_quality):

````
```json
{
  "schema_version": "reviewer-result/1",
  "role": "spec | code_quality",
  "verdict": "pass | issues | unable_to_verify",
  "reviewed_commit": "<SHA the dispatch named>",
  "reviewed_head": "<git rev-parse HEAD — what you actually inspected>",
  "working_tree_clean": true,
  "commands": [{"command": "<exact>", "exit_code": 0, "summary": "<one line, e.g. 12 passed in 3.4s>"}],
  "issues": [{"severity": "critical|important|minor", "file": "<path>", "line": 0,
              "requirement": "<enumerated id | unlisted>", "finding": "<what is wrong>"}],
  "commit_trailer": {"present": true, "expected": "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>", "observed": "<verbatim|null>"},
  "unverifiable_reason": null,
  "blocked": null
}
```
````
  Invariants (stated below the block): `pass` ⇒ `issues` empty; `issues` ⇒ ≥1 entry;
  `unable_to_verify` ⇒ `issues` empty **and** `unverifiable_reason` ∈ {U1..U5} **and** `blocked`
  non-null; `reviewed_head != reviewed_commit` ⇒ forced `unable_to_verify`
  (`unverifiable_reason: U4`). A W2 independent-pass find sets `requirement: "unlisted"`.
  **Reviewer-subagent emit is MANDATORY; the word cap applies to PROSE only.** An "agents-tree
  reviewer.md, when created, MUST carry this schema verbatim" marker goes here.

- [ ] **Step 5: Add `## Evidence preamble — RUN every command, paste output verbatim (ADR-028)`** — closes **W3 + W5 reviewer-side + W4 + M-RERUN-PINS**:
  1. **Reviewed-HEAD pin:** `env -u GIT_INDEX_FILE git rev-parse HEAD` → must equal the dispatch's
     `<SHA>`. Differ ⇒ STOP, `unable_to_verify` (U4).
  2. **Cleanliness:** `env -u GIT_INDEX_FILE git status --short` → must be empty over reviewed
     paths. Non-empty ⇒ `unable_to_verify` (U3), name the paths.
  3. **Base availability:** `env -u GIT_INDEX_FILE git cat-file -e <BASE>` → absent ⇒ `unable_to_verify` (U5).
  4. **Provenance:** read each asserted file FROM the commit (`git show <SHA>:<path>`), not the
     editor buffer; state "provenance = reviewed commit".
  5. **Trailer (W4):** `git show -s --format=%(trailers) <SHA>` → record `commit_trailer.observed`
     verbatim; expected = the Co-Authored-By line. *Absent ≠ unreadable* — unreadable is U5, not
     `present:false`.
  6. **Tests (W3):** run the dispatch's mandated `… pytest … -q`; paste the literal summary line +
     pytest exit code. Any `skipped/xfailed/xpassed/error` token is flagged (invisible-green).
     `.venv` missing / collection fails for env reasons ⇒ `unable_to_verify` (U1/U2), NOT a defect.
  7. **Re-run pins (M-RERUN-PINS, CRITICAL):** for each pin selector the dispatch/implementer names,
     run it with `--runxfail`, paste the summary, and confirm a one-fact mutation flips it RED
     (non-vacuity). A pin that passes on reverted code is not evidence.
  - Per-command rule: EVERY command records its `exit_code` (R-EVIDENCE/R-MEASURE).
  - **U1..U5 definitions** + the **UTV-vs-NO-GO discriminator** (UTV = the run did not reach a
    conclusion; NO-GO = the run ran and the code failed) go here verbatim.

- [ ] **Step 6: Rewrite the Spec reviewer sub-template** "Your Job" as: (0) Evidence preamble →
  (1) `git show <SHA>` read → (2) verify each enumerated requirement → (3) **independent defect
  pass** seeded with this repo's bug taxonomy — silent-gate-degradation, money-loss
  gate-source-mismatch, invisible-green pins, concurrency/ordering, swallowed exceptions, NaN/
  boundary — reporting finds as `requirement: "unlisted"` or the explicit line "independent pass:
  no unlisted defects" (**W2**) → (4) **flaky rule**: a non-reproducible pass/fail is reported
  per-run and dispositioned as a flaky-test FINDING, never silently retried-to-green
  (**M-FLAKY-PARTIAL**). Report block = 3-way prose verdict (✅/❌/⛔) + evidence-block bullet
  (exempt from cap) + the mandatory RESULT SCHEMA json. The W2 pass is **skipped under any UTV
  precondition**.

- [ ] **Step 7: Rewrite the Code-quality sub-template** with the same Evidence preamble reference,
  a one-line independent-defect bullet, a `commit_trailer` bullet, the 3-way verdict incl.
  `unable_to_verify`, and the mandatory RESULT SCHEMA json (`role: code_quality`).

- [ ] **Step 8: Word-cap exemption** — change both `Under <N> words.` lines to:
  `Under <N> words (prose only — the pasted Evidence block, the unable_to_verify precondition output, and the final RESULT SCHEMA json do NOT count toward the cap).`

- [ ] **Step 9: Add `## Reviewer-conflict resolution`** — closes **M-DISAGREE**: when the spec and
  code-quality reviewers (or two parallel Lane-V passes) disagree on one diff, resolve to the
  **more conservative** verdict (`issues` dominates `pass`; `unable_to_verify` dominates both —
  you cannot synthesize a clean verdict from an unverified run); a genuine spec-vs-quality
  contradiction **escalates** to the receiving seat, never auto-merges to `pass`.

- [ ] **Step 10: Add `## Hardening notes — provenance`** — one short paragraph crediting
  `wf_b89b9c6c-128` + the assessment, mirroring implementer.md's provenance convention.

- [ ] **Step 11: Commit** — `feat(protocol): reviewer template — result schema, evidence preamble, UTV verdict, pin re-execution, conflict + cold-context rules`.

## Task 2: Protocol vocab + disposition + reciprocal implementer change

**Files:** Modify `docs/protocol/claude/director-operator.md`, `docs/protocol/agents/director-operator.md`, `docs/templates/claude/implementer.md`.

- [ ] **Step 1:** `director-operator.md:89-90` — append `/ ⛔ unable_to_verify` to the Lane-V
  status vocab + one sentence: UTV = the run could not conclude (U1–U5 in the reviewer template);
  the consumer RE-DISPATCHES in a fixed env, it does NOT mark the implementation failed.
- [ ] **Step 2:** `director-operator.md:681` — append `/ ⛔ unable_to_verify` to the Stage-5 status.
- [ ] **Step 3:** `director-operator.md:692-693` — add a fourth disposition: **RE-DISPATCH (UTV only)** —
  receiving seat changes NO implementation status; re-dispatches a fresh cold-context Lane V in a
  corrected env (build venv / clean tree / checkout the SHA / fetch base) and consumes only the
  re-run's conclusive verdict. Inventory row stays in its prior state (typically `open`).
- [ ] **Step 4:** `director-operator.md:813-823` (severity matrix) — add a row:
  `| unable_to_verify | RE-DISPATCH in a fixed env; cap 2 re-dispatches then ESCALATE to user-principal; persistent UTV → R-VERIFY-TIER(B) test-infeasible label | Never (a)/(b)/(c); the code is unjudged. |`
- [ ] **Step 5:** `agents/director-operator.md:77-78` — mirror Step 1 (append `/ ⛔ unable_to_verify`
  + the same sentence). Record that the agents tree has **no** reviewer.md to mirror Task 1 into.
- [ ] **Step 6:** `implementer.md` Report Format — add a line: **Pin selectors run** — the exact
  `pytest` node-ids / `xfail-pin` column values executed (so the reviewer can re-run them with
  `--runxfail`).
- [ ] **Step 7: Commit** — `feat(protocol): add unable_to_verify verdict + RE-DISPATCH disposition (both trees) + implementer emits pin selectors`.

## Task 3: Mechanical anti-ceremony guard — `check_no_ceremony.py` R5 (TDD)

**Files:** Modify `scripts/check_no_ceremony.py`. (No pytest file exists; the script self-executes
and is run by `ci_smoke.py` — verify by executing it.)

- [ ] **Step 1 (red): add `rule_utv_not_a_row_status()`** — parse `docs/REMEDIATION-INVENTORY.md`'s
  `status` column; HARD FAIL if any cell lowercases to `unable_to_verify`. Mirror the existing
  `rule_*` shape `(status, lines)`; high-precision (string match), per the script's precision bar.
  Temporarily inject a fake `| unable_to_verify |` status row context to confirm the rule fires,
  then remove it.
- [ ] **Step 2 (red→green): wire R5 into `main()`** next to R4 (print line + `hard_fail |=`), and
  extend the module docstring rules list with `R5 utv-not-a-row-status`.
- [ ] **Step 3 (verify):** `env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py` →
  R5 PASS on the real inventory (which has no UTV status); overall result unchanged (R3/R4 stay
  the known-RED systemic ceremony — do NOT mask them).
- [ ] **Step 4 (smoke):** `.venv/bin/python scripts/ci_smoke.py` → OK.
- [ ] **Step 5: Commit** — `feat(ceremony): R5 — unable_to_verify is a verdict, never an inventory row status (wave-gate bypass guard)`.

## Task 4: ADR-032 + close-out

**Files:** Append to `DECISIONS.md`.

- [ ] **Step 1:** Append **ADR-032 — The verification dispatch is a self-executing, fail-aware,
  machine-consumable contract** (Context: the Level-4 assessment + the missed keystone; Decision:
  the canonical enum, `reviewer-result/1`, the Evidence preamble incl. pin re-execution, the UTV
  disposition + RE-DISPATCH, R5; the **deferred** consumer + R6 + fabrication re-run, with the
  reason they are deferred not dropped; Evidence: this plan + `wf_b89b9c6c-128`; Cross-refs:
  ADR-027/028, reviewer.md, director-operator.md, R-EVIDENCE/R-MEASURE/R-VERIFY-TIER).
- [ ] **Step 2: Commit** — `docs(adr): ADR-032 — self-executing fail-aware verification dispatch contract`.

## Verification / acceptance

- [ ] `.venv/bin/python scripts/ci_smoke.py` → OK (no ARCHITECTURE.md/PROGRAM-MANUAL drift introduced).
- [ ] `env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py` → R1/R5 PASS; R3/R4 unchanged (RED, tracked).
- [ ] `git diff --stat main..HEAD` matches the blast-radius table; no unintended files.
- [ ] **Independent Lane-V review** (spec + code-quality, parallel, Opus) over the full diff:
  verdict `pass` with the new schema, or findings addressed.
- [ ] **D5:** hardened re-review of `feat/threeway-slice2-exec` `612d6109` exercising the Evidence
  preamble + pin re-execution against `tests/unit/test_threeway_envelope.py` / `_refstore.py` pins.

## Deferred follow-up (file as a tracked slice)

A `scripts/` consumer that parses the `reviewer-result/1` block from a verification-report,
**re-runs the reported pytest to detect a fabricated summary**, maps reviewer-severity →
inventory-severity, proposes `REMEDIATION-INVENTORY.md` status transitions, adds
`check_no_ceremony.py` **R6** (a `pass` report cites an executed `--runxfail` run), and is wired
into `ci_smoke`. Build before promoting any mailbox-level JSON block to MANDATORY — until then
the block stays OPTIONAL so the schema is never an unconsumed (ceremonial) artifact.
