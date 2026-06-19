# Reviewer prompt template — Claude Code

> Relocated verbatim from `CLAUDE.md` as part of the operative/provenance
> split (see `docs/protocol/migration-map-claudemd-split.md`). Loaded **at dispatch**,
> not at session start. Two-tree strategy: this is the `claude` copy.
> During the add-first window the root file still holds this content; it will be
> stubbed once this destination is confirmed.

---

## Canonical verdict vocabulary (read first)

One enum, three values, used verbatim in the RESULT SCHEMA below and as the
machine token everywhere: **`pass` | `issues` | `unable_to_verify`**.

- **Human render (prose only — never a second encoding):** `pass` = ✅ ;
  `issues` = ⚠️ (worst severity minor) / ❌ (worst severity critical or important) ;
  `unable_to_verify` = ⛔.
- **Seat shorthand maps 1:1:** GO = `pass` · NITS = `issues` (all minor) ·
  FAIL = `issues` (≥1 critical/important) · RE-DISPATCH/ESCALATE = `unable_to_verify`.
- **Severity is a separate axis** (`issues[].severity` ∈ critical/important/minor). A
  single reviewer's verdict is **binary** (`pass`/`issues`); the operator's synthesis
  derives the band from the merged `issues[].severity`. `unable_to_verify` is
  **orthogonal to severity** — it is a property of the verification *run*, never a defect.
- **`unable_to_verify` MUST NEVER become a `REMEDIATION-INVENTORY.md` row `status`** — it
  would silently bypass `wave_gate_check.py`'s blocking logic (ADR-027). It is a
  reviewer/operator verdict only; the row stays in its prior state (typically `open`).

## Independence + verify-before-asserting (include verbatim in EVERY dispatched reviewer prompt)

- You are an **independent, cold-context** reviewer (Rule #9). **Do NOT trust the
  implementer's report**, and do NOT cite or anchor on any other reviewer's findings —
  form your verdict only from the actual diff/commit under review.
- **Verify before asserting (CC-2).** Before claiming any symbol / file / line exists,
  `grep`/Read to confirm it against the real bytes. A confident "X is a bug" you have not
  verified is a hallucination — verify it, or label the claim unverified.
- **Dispatch on Opus.** A high-quality review is partly a function of reviewer capability;
  the standing subagent-model directive applies to reviewer subagents too.

## Git hygiene (include verbatim in EVERY dispatched prompt)

- Prefix EVERY git invocation with `env -u GIT_INDEX_FILE ` — your
  environment inherits this seat's per-seat git index, and concurrent index
  refreshes from parallel agents corrupted it on 2026-06-12 ("unable to read
  <blob>"). The unset form uses the default `.git/index`, which no seat
  depends on.
- Never run state-changing git (add/commit/checkout/stash/restore/read-tree
  without explicit instruction). Read-only git (show/log/diff A..B/grep/
  rev-parse/ls-tree) plus the prefix is always safe.
- The Evidence-preamble git calls below (`rev-parse` / `status --short` / `show` /
  `diff A..B` / `cat-file -e`) are all read-only and obey this same prefix; they
  introduce no state-changing git.

## RESULT SCHEMA (emit verbatim as the LAST thing in your reply)

After your prose report, emit ONE fenced ```json block as the LAST thing in your reply,
conforming to this shape. The prose is for the human reader; this block is for safe
machine consumption and serializes the EXECUTED evidence (it is not a status assertion —
ADR-028). Emitting it is MANDATORY for every reviewer dispatch.

```json
{
  "schema_version": "reviewer-result/1",
  "role": "spec | code_quality",
  "verdict": "pass | issues | unable_to_verify",
  "reviewed_commit": "<SHA the dispatch named as under review>",
  "reviewed_head": "<git rev-parse HEAD — what you actually inspected>",
  "working_tree_clean": true,
  "commands": [
    {"command": "<exact command run>", "exit_code": 0, "summary": "<one line, e.g. 12 passed in 3.4s>"}
  ],
  "issues": [
    {"severity": "critical | important | minor", "file": "<path>", "line": 0,
     "requirement": "<enumerated id | unlisted>", "finding": "<what is wrong>"}
  ],
  "commit_trailer": {"present": true,
                     "expected": "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>",
                     "observed": "<verbatim trailer line | null>"},
  "unverifiable_reason": null,
  "blocked": null
}
```

Invariants:
- `pass` ⇒ `issues` is empty. `issues` ⇒ ≥1 entry.
- `unable_to_verify` ⇒ `issues` is EMPTY (the code is unjudged), `unverifiable_reason` ∈
  {`U1`,`U2`,`U3`,`U4`,`U5`} (see the Evidence preamble), and `blocked` is a non-null object
  naming the failing command. Never record a defect under `unable_to_verify`.
- `reviewed_head != reviewed_commit` ⇒ forced `unable_to_verify` with
  `unverifiable_reason: "U4"` — you cannot prove you read the right code.
- `working_tree_clean: false` co-occurs ONLY with `unable_to_verify`
  (`unverifiable_reason: "U3"`); a `pass` requires a clean tree over the reviewed paths.
- Every command you relied on appears in `commands[]` with its real `exit_code`. A pytest
  run's `summary` is the exact pytest tail line, never a paraphrase.
- A W2 independent-pass find that is not tied to an enumerated requirement sets
  `issues[].requirement: "unlisted"`.
- The word cap (in the sub-templates) applies to PROSE only — this json block is exempt.

> **Agents-tree note:** there is no `docs/templates/agents/reviewer.md` today. If one is ever
> created, it MUST carry this RESULT SCHEMA section verbatim (two-tree verbatim-per-file rule).

## Evidence preamble — RUN every command, paste output verbatim (do NOT assert; ADR-028)

All git below uses the `env -u GIT_INDEX_FILE ` prefix. Run these in order and paste each
command with its output and exit code. If a precondition (steps 1–3) fails, STOP the normal
pass and return `unable_to_verify` with the precondition — do NOT score requirements or report
defects against an unverified tree, and do NOT run the independent pass.

1. **Reviewed-HEAD pin** — `env -u GIT_INDEX_FILE git rev-parse HEAD` → record as REVIEWED_HEAD.
   If REVIEWED_HEAD ≠ the dispatch's reviewed `<SHA>` → `unable_to_verify` (**U4**).
2. **Working-tree cleanliness** — `env -u GIT_INDEX_FILE git status --short` → MUST be empty over
   the reviewed paths. Any stray/uncommitted line → `unable_to_verify` (**U3**); name the paths.
3. **Base availability** — `env -u GIT_INDEX_FILE git cat-file -e <BASE>` → if the BASE_SHA for
   `git diff <BASE>..<SHA>` is absent → `unable_to_verify` (**U5**).
4. **Provenance** — read each file you assert about FROM the commit
   (`env -u GIT_INDEX_FILE git show <SHA>:<path>`), not an editor buffer. State
   "files inspected via `git show <SHA>:…` — provenance = reviewed commit".
5. **Commit trailer (W4)** — `env -u GIT_INDEX_FILE git show -s --format=%(trailers) <SHA>` →
   record the literal trailer block into `commit_trailer.observed`; `expected` is the
   `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` line (the only sanctioned trailer).
   **Absent ≠ unreadable**: a missing trailer is `present:false`; an unreadable commit is U5.
6. **Tests** — run exactly the dispatch's mandated `… pytest … -q`; paste the LITERAL summary
   line (`N passed[, M failed][, K skipped][, J xfailed]`) and the pytest EXIT CODE. Any
   `skipped` / `xfailed` / `xpassed` / `error` token is FLAGGED (invisible-green ceremony). If
   `.venv` is missing or tests cannot collect for ENVIRONMENT reasons (not a code defect) →
   `unable_to_verify` (**U1** no interpreter / **U2** tests-cannot-run), NOT a defect.
7. **Re-run the pins (CRITICAL — the anti-ceremony keystone)** — for each pin selector the
   dispatch/implementer names, run it with `--runxfail`, paste the summary, AND confirm a
   one-fact mutation flips it RED (non-vacuity). A pin that passes on reverted code is not
   evidence (ADR-027). A green suite that does not exercise the changed symbols is not `pass`.

Per-command rule: EVERY command above and every task-specific command records its `exit_code`.
The exit code is the evidence; "looks fine" is not (R-EVIDENCE / R-MEASURE).

**U1..U5 (the only `unable_to_verify` triggers):** U1 no usable venv/interpreter · U2 tests
cannot run for env reasons (missing dep, no process-spawn for the harness, collection error
unrelated to the diff) · U3 dirty worktree over reviewed paths · U4 HEAD ≠ reviewed SHA ·
U5 base/reviewed commit unavailable.

**UTV-vs-NO-GO discriminator:** NO-GO (`issues`, ❌) = the verification RAN and the code FAILED a
check (a pin went RED, a requirement is unmet, a defect with file:line). `unable_to_verify` (⛔)
= the verification did NOT run to a conclusion (U1–U5); the environment/inputs are the problem,
the code is unjudged. Never conflate the two.

## Spec reviewer prompt template

```
You are reviewing whether Task <N>'s implementation matches its spec.
Include the Independence, Git-hygiene, RESULT SCHEMA, and Evidence-preamble
blocks above VERBATIM. **Do NOT trust the implementer's report** — read the code.

## What Was Requested

<paste exact requirements + numbered checklist of behaviors>

## What Implementer Claims

<list claims to be verified, including commit SHA + the pin selectors they ran>

## Your Job

0. Run the Evidence preamble. If any precondition (U1–U5) fires, STOP and return
   `unable_to_verify` — do not proceed.
1. `git show <SHA> -- <file>` — read the diff from the reviewed commit.
2. Verify each enumerated requirement above.
3. Independent defect pass — read the diff once more for defects NOT on the list,
   hunting this repo's known bug families: silent-gate-degradation (a gate no-ops on
   dep-absent / swallowed-except / NaN), money-loss gate-source-mismatch, invisible-green
   pins (skip/xfail/importorskip), concurrency/ordering hazards, swallowed exceptions,
   off-by-one / boundary, secret handling. Report finds with `requirement: "unlisted"`, or
   state explicitly "independent pass: no unlisted defects". (Skip this pass under any UTV
   precondition.)
4. Flaky/non-deterministic runs — if a test's pass/fail is not reproducible across runs,
   report the per-run outcomes and disposition it as a flaky-test FINDING (a real defect to
   fix), never silently retried-to-green. This is NOT a clean `pass`.
5. <task-specific verification commands>

## Report

Prose (for the human): ✅ Spec compliant / ❌ Issues — list with file:line refs /
⛔ unable_to_verify — state which precondition (U1–U5) + the command + its output;
this is NOT an implementation NO-GO (the code is unjudged); re-dispatch in a fixed env.
- Evidence block (verbatim): REVIEWED_HEAD; `git status --short` result; provenance
  statement; the literal pytest summary + exit code; the `--runxfail` pin result + mutation
  check; the trailer line. (NOT counted toward the word cap.)

Then emit the RESULT SCHEMA json block (role: "spec") as the LAST thing in your reply.

Under <N> words (prose only — the pasted Evidence block, the unable_to_verify precondition
output, and the final RESULT SCHEMA json do NOT count toward the cap).
```

## Code quality reviewer prompt template

```
Code quality review for Task <N> (commit `<SHA>`).
Include the Independence, Git-hygiene, RESULT SCHEMA, and Evidence-preamble blocks above
VERBATIM. Run the Evidence preamble first; if a precondition fires, return unable_to_verify.

**WHAT_WAS_IMPLEMENTED:** <one-paragraph summary>
**PLAN_OR_REQUIREMENTS:** <reference to plan section>
**BASE_SHA:** `<sha>`
**HEAD_SHA:** `<sha>`
**PIN_SELECTORS:** <the pin node-ids the implementer reports running>
**DESCRIPTION:** <one-paragraph context>

**Working directory:** `<absolute>`
**Diff command:** `git diff <BASE>..<HEAD> -- <files>`

In addition to standard concerns, check:
- <task-specific concern 1> (e.g., concurrency if threading is involved)
- <task-specific concern 2> (e.g., public API stability if refactor)
- defects beyond the listed concerns: do one independent pass and report any you find (or none).
- Commit trailer: the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` line is present
  and well-formed (the only sanctioned trailer).

Report: Strengths, Issues (Critical / Important / Minor), Assessment.
If verification could not run (U1–U5), report Assessment = unable_to_verify with the failing
precondition + command output, and report NO Issues (the code is unjudged, not defective).
Then emit the RESULT SCHEMA json block (role: "code_quality"); map Critical/Important/Minor →
critical/important/minor in `issues[].severity`.

Under <N> words (prose only — the pasted Evidence block, the unable_to_verify precondition
output, and the final RESULT SCHEMA json do NOT count toward the cap).
```

## Reviewer-conflict resolution (operator synthesis)

When the spec reviewer and the code-quality reviewer — or two parallel Lane-V passes — disagree
on the SAME diff, the operator's synthesis resolves to the **more conservative** verdict:
`issues` dominates `pass`; `unable_to_verify` dominates BOTH (you cannot synthesize a clean
verdict from a run that did not conclude). A genuine spec-vs-quality CONTRADICTION (one says
compliant, the other finds a critical defect) **escalates** to the receiving seat for
adjudication — it never auto-merges to `pass`. The operator's verdict is its own cold-context
synthesis, not a passthrough of either subagent's json.

## Hardening notes — provenance for the reviewer-template additions

The Canonical-vocabulary, Independence, RESULT SCHEMA, Evidence-preamble (incl. pin
re-execution), Reviewer-conflict, and 3-way-verdict additions are codified per ADR-031,
from the adversarial design pass `wf_b89b9c6c-128` over an external "Level 4 of 5" assessment of
the live Slice-2 verification dispatch. The keystone is Evidence-preamble step 7 (re-run the
implementer's pins with `--runxfail` + a mutation non-vacuity check): a machine-readable result
schema of *pasted* evidence is ceremony unless the pins are actually executed (ADR-027/028). If
you trim this template, do NOT trim the four "include verbatim" blocks or step 7.
