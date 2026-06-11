# Two-Seat Process Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **House override (CLAUDE.md R-ORCH):** Tasks 2–4 all edit `CLAUDE.md` + `AGENTS.md` — tightly-coupled, so execute SEQUENTIALLY IN MAIN CONTEXT, one commit per task, explicit pathspec on every commit (the director seat is live; `git log -3` before each commit). This note takes precedence over the subagent-driven default.

**Goal:** Close four process gaps surfaced by the 2026-06-11/12 operator sessions: subagent index corruption, verification latency on clock-billed work, ad-hoc numbers backing GO/NO-GO verdicts, and the post-last-hook-fire skip-worktree window.

**Architecture:** All four are small, independent hardening changes to the process layer (CLAUDE.md/AGENTS.md rules, protocol-doc rules #21/#22, dispatch templates) plus one local hook registration. No production pipeline code changes. Reuse over new code: the SessionStart sweep reuses the existing, test-guarded `_clear_skip_worktree` in `update-state.sh` via hook registration only.

**Tech Stack:** Markdown process docs, Claude Code hooks (`.claude/settings.local.json`), bash hook script (existing, unchanged), `scripts/ci_smoke.py` + `scripts/check_doc_claims.py` gates.

**Authorization trail:** User directed application of items 2–5 verbatim on 2026-06-12 ("plan to apply these"). Hook-registration work is user-authorized by that instruction (memory: `.claude/hooks` edits need explicit in-session authorization — satisfied; the hook *script* is not edited at all). Director notified by mailbox event in Task 5; disagreement protocol applies if they object.

**Verification gates used throughout:** `.venv/bin/python scripts/ci_smoke.py` (includes `check_coordination.py` linter) and `.venv/bin/python scripts/check_doc_claims.py <doc>` for gated docs. No production pytest impact expected from any task; Task 1 has a manual hook-fire verification.

---

## Chunk 1: All tasks

### Task 1: SessionStart sweep — close the v5.9 coverage gap (item #5)

The v5.9 `_clear_skip_worktree()` (`.claude/hooks/update-state.sh:123-136`, invoked at `:144` BEFORE the perf gate) already clears pollution on every PostToolUse fire. The gap (strike #2 mechanism, 2026-06-12): pollution landing AFTER a session's last hook fire persists into the next session. Fix = also fire the same script at SessionStart. **No new script, no new tests — the function is already guarded by `tests/unit/test_skip_worktree_clear.py`.** Only registration (local, gitignored) + tracked documentation change.

**Files:**
- Modify: `.claude/settings.local.json` (GITIGNORED — local-only edit, never committed)
- Modify: `OPERATIONS.md` (tracked — documents the registration so it is reconstructible on a fresh machine)

- [x] **Step 1: Read current settings and add the SessionStart hook entry**

Read `.claude/settings.local.json`. It currently has `hooks.PostToolUse` only (matcher `Bash|Write|Edit` → `bash /Users/hyungkoookkim/Content/.claude/hooks/update-state.sh`). Add a sibling key inside the existing `"hooks"` object (preserve everything else verbatim):

```json
"SessionStart": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "bash /Users/hyungkoookkim/Content/.claude/hooks/update-state.sh"
      }
    ]
  }
]
```

- [x] **Step 2: Validate the JSON parses**

Run: `.venv/bin/python -c "import json; json.load(open('.claude/settings.local.json')); print('JSON OK')"`
Expected: `JSON OK`

- [x] **Step 3: Simulate the SessionStart fire**

Run exactly what the hook will run, and prove it exits 0 and the clear function ran (the log line only appears when bits were found, so also confirm a no-bits run is silent and clean):

```bash
bash /Users/hyungkoookkim/Content/.claude/hooks/update-state.sh; echo "EXIT=$?"
git ls-files -v | grep -c '^S' || echo "0 flagged"
```

Expected: `EXIT=0` and `0 flagged`.

- [x] **Step 4: Document the registration in OPERATIONS.md**

Locate the hooks/state section of `OPERATIONS.md` (grep `update-state.sh`; if no hooks section exists, add a short `### Claude Code hooks` subsection under the operations/setup material). Add:

```markdown
- `update-state.sh` must be registered under BOTH `PostToolUse` (matcher
  `Bash|Write|Edit`) AND `SessionStart` in `.claude/settings.local.json`
  (gitignored, per-machine). The SessionStart fire closes the v5.9
  skip-worktree coverage gap: pollution landing after a session's LAST
  PostToolUse fire (strike #2, 2026-06-12, 866 paths) is swept at the next
  session's start instead of surviving into its `git status`.
```

- [x] **Step 5: Gate + commit (OPERATIONS.md only — settings.local.json is gitignored)**

```bash
.venv/bin/python scripts/ci_smoke.py
git log --oneline -3   # peer-live check
git commit -m "ops(hooks): register update-state.sh at SessionStart — closes the v5.9 post-last-hook-fire skip-worktree window (strike #2 mechanism); registration is local (settings.local.json gitignored), documented here for reconstruction. User-authorized 2026-06-12." -- OPERATIONS.md
```

Expected: smoke `OK`; commit touches exactly 1 file.

---

### Task 2: Subagent git-state isolation (item #2)

Subagents inherit the seat's `GIT_INDEX_FILE`; concurrent index refreshes from parallel agents are the suspected corruption vector (2026-06-12 incident: `index-operator` → `fatal: unable to read <blob>`). **Constraint that shapes the fix:** subagent shell state does NOT persist between Bash calls, so a one-time `export` is impossible — the rule must be a PER-INVOCATION prefix. `env -u GIT_INDEX_FILE git …` redirects index traffic to the default `.git/index`, which NO seat and NO hook depends on (seats use `index-director`/`index-operator`) — a sacrificial index. Residual risk (concurrent subagents corrupting `.git/index` itself) is accepted: it breaks nothing seat-side and self-heals via `git read-tree HEAD` under an unset env.

**Files:**
- Modify: `docs/templates/claude/implementer.md`
- Modify: `docs/templates/claude/reviewer.md`
- Modify: `docs/templates/agents/implementer.md`
- Modify: `CLAUDE.md` (one clause in the "Dispatch templates" bullet under "# Claude Code mechanics")
- Modify: `AGENTS.md` (same clause at its equivalent bullet)
- Modify: `/Users/hyungkoookkim/.claude/projects/-Users-hyungkoookkim-Content/memory/da_git_index_file_breaks_pytest_temp_repos.md` (append the dispatch rule — memory, not committed)

- [x] **Step 1: Add a "Git hygiene" block to all three template files**

Placement per file (reviewer-verified structures differ): `docs/templates/claude/implementer.md` — insert after the CLOSING ``` of the skeleton code fence (the fence opens at ~line 16; "Skeleton:" on line 14 is prose, not a heading); `docs/templates/claude/reviewer.md` — insert immediately after the `## Spec reviewer prompt template` heading line, before its code fence; `docs/templates/agents/implementer.md` — flat `##` sections, no skeleton fence: insert as a new `##`-level section directly after the doc's intro block, before the first prompt-template section. In all three the block must be visible BEFORE the prompt body so dispatchers copy it into every prompt. Insert:

```markdown
### Git hygiene (include verbatim in EVERY dispatched prompt)

- Prefix EVERY git invocation with `env -u GIT_INDEX_FILE ` — your
  environment inherits this seat's per-seat git index, and concurrent index
  refreshes from parallel agents corrupted it on 2026-06-12 ("unable to read
  <blob>"). The unset form uses the default `.git/index`, which no seat
  depends on.
- Never run state-changing git (add/commit/checkout/stash/restore/read-tree
  without explicit instruction). Read-only git (show/log/diff A..B/grep/
  rev-parse/ls-tree) plus the prefix is always safe.
```

- [x] **Step 2: Add the dispatch clause to CLAUDE.md and AGENTS.md**

In `CLAUDE.md` under `# Claude Code mechanics`, the bullet beginning `- **Dispatch templates** —` currently ends `…never inherited doctrine.` Append to that bullet:

```markdown
 Every dispatch includes the templates' **Git hygiene** block (subagents
  prefix all git with `env -u GIT_INDEX_FILE` — seat-index corruption vector,
  2026-06-12).
```

Make the same edit in `AGENTS.md` at its equivalent dispatch-templates bullet (grep `Dispatch templates` there; if AGENTS.md lacks the bullet, add the clause to its orchestration/mechanics section nearest equivalent).

- [x] **Step 3: Append the rule to the memory file**

Append to `da_git_index_file_breaks_pytest_temp_repos.md` (memory dir):

```markdown

**Dispatch rule (2026-06-12, post index-corruption incident):** every
subagent prompt carries the templates' Git-hygiene block — per-invocation
`env -u GIT_INDEX_FILE` prefix (subagent shell state does not persist, so a
one-time export cannot work). Workflow COMMON preambles too.
```

- [x] **Step 4: Gate + commit**

```bash
.venv/bin/python scripts/ci_smoke.py
git log --oneline -3
git commit -m "process(dispatch): subagent git-state isolation — per-invocation 'env -u GIT_INDEX_FILE' prefix codified in dispatch templates + CLAUDE/AGENTS dispatch clause. Vector: parallel subagents inherit the seat index; concurrent refreshes corrupted index-operator 2026-06-12 ('unable to read <blob>', repaired via read-tree). Default .git/index is sacrificial (no seat/hook depends on it). One-time export impossible: subagent shell state does not persist across Bash calls." -- docs/templates/claude/implementer.md docs/templates/claude/reviewer.md docs/templates/agents/implementer.md CLAUDE.md AGENTS.md
```

Expected: smoke `OK`; commit touches exactly 5 files.

---

### Task 3: Rules #21 + #22 — latency workarounds become rules (item #3)

Both worked as conventions on 2026-06-11; promote to numbered rules so the fast path is the default path. Rule text is identical in both protocol twins; insertion point is immediately BEFORE the `## Disagreement protocol (v5)` heading (`docs/protocol/claude/director-operator.md:1424`; `docs/protocol/agents/director-operator.md:1106` — locate by heading text, not line number, in case the director's live session moved them).

**Files:**
- Modify: `docs/protocol/claude/director-operator.md`
- Modify: `docs/protocol/agents/director-operator.md`
- Modify: `CLAUDE.md` (the governance pointer says "Rules #7–#20" — update range to #7–#22)
- Modify: `AGENTS.md` (same range pointer)

- [x] **Step 1: Insert the two rule sections into BOTH protocol twins**

```markdown
## Verdict-ahead-of-report (Rule #21)

**Rule #21: Verdict-ahead-of-report.** When the peer seat is blocked on a
clock-billed resource (GPU-pod hours, paid-API budget, an external window)
awaiting your review, send the dispositive verdict — GO/NO-GO plus its
conditions, nothing more — as its OWN mailbox event the moment it is
determined. The full evidence report follows as a separate event on the
normal cadence. The verdict event must say a full report follows, so the
receiving seat never mistakes it for the complete review.

Empirical basis: 2026-06-11 S2 spike — the director sat blocked mid-pod-
session (billing by the hour) on the operator's script review; the operator
sent the GO-after-done-guard-fix verdict ahead (`6f3b809`), full 114-claim
report later (`3a13156`). Fold time on the verdict was minutes; nothing in
the later report reversed it.

Composition: does NOT relax R-EVIDENCE — the verdict event states which
checks back it; unverified residue is flagged in the follow-up report.

## Flag-before-burn (Rule #22)

**Rule #22: Flag-before-burn.** Any script or driver whose execution spends
clock-billed or per-call money (pod render time, paid-API training or
generation) gets the NON-AUTHOR seat's review BEFORE its first execution.
Minimum review scope (the money-path lens): existing-output/idempotency
guard, spend-site enumeration, `raise_for_status`/error propagation on every
paid call, timeout on every blocking call. If the peer is unavailable and
the window is closing, the author may proceed only after running the
money-path lens themselves and saying so in the run record.

Empirical basis: 2026-06-11 S3 — the reviewed sweep script ran clean under
flag-before-burn; the UNREVIEWED train script had already run and carried
the F1 no-rerun-guard defect (a re-run would have re-spent the FAL training
fee; guard landed `3a589da`). The convention caught one and missed the
other only because it was not yet mandatory.

Composition: Rule #21 covers the reply latency this rule would otherwise
add — verdict first, report later.
```

- [x] **Step 2: Update the governance range pointers**

In `CLAUDE.md` (section `# Director–Operator concurrent operation`): replace `Rules #7–#20` with `Rules #7–#22` in the sentence pointing at `docs/protocol/claude/director-operator.md`. Same replacement in `AGENTS.md` (its pointer targets `docs/protocol/agents/director-operator.md`).

- [x] **Step 3: Gate + commit**

```bash
.venv/bin/python scripts/ci_smoke.py
git log --oneline -3
git commit -m "protocol(rules): #21 verdict-ahead-of-report + #22 flag-before-burn — 2026-06-11 latency conventions promoted to rules (both twins; CLAUDE/AGENTS range pointers #7-#20 -> #7-#22). Basis: 6f3b809 verdict-first unblocked a billed pod session; unreviewed train script carried the F1 fee-respend defect the reviewed sweep avoided. User-directed 2026-06-12." -- docs/protocol/claude/director-operator.md docs/protocol/agents/director-operator.md CLAUDE.md AGENTS.md
```

Expected: smoke `OK`; 4 files.

---

### Task 4: R-MEASURE — measurement-as-artifact (item #4)

**Files:**
- Modify: `CLAUDE.md` (new rule block immediately AFTER the `# Verification discipline (R-EVIDENCE)` block, before `# Multi-task orchestration (R-ORCH)`)
- Modify: `AGENTS.md` (same position relative to its R-EVIDENCE block)

- [x] **Step 1: Insert the rule block in both files**

```markdown
# Measurement-as-artifact (R-MEASURE)
Scope: both
Trigger: recording a number that backs a GO/NO-GO verdict, a gate threshold,
or a spec/record claim (arc scores, VRAM peaks, prices, durations, counts).
Action: the number must be produced by a COMMITTED script/command and
persisted to (or directly citable from) a `logs/` artifact in the same change
that records it. Ad-hoc runtime measurements may be recorded only when
explicitly labeled estimate / runtime-unreproducible. Extends R-EVIDENCE from
"cite the command" to "commit the instrument".
Evidence: script path + `logs/` artifact cited next to the number.
Details: docs/PROTOCOL-RULES-LOG.md (R-MEASURE entry; origin = the 2026-06-11
half-crop numbers that backed S2/S3 verdicts from REPL-only measurement).
```

- [x] **Step 2: Gate + commit**

```bash
.venv/bin/python scripts/ci_smoke.py
git log --oneline -3
git commit -m "process(evidence): R-MEASURE measurement-as-artifact — verdict-backing numbers come from committed instruments emitting logs/ artifacts, or are labeled estimates. Origin: half-crop S2/S3 numbers were REPL-only (operator Lane V 18:49:37Z, disposed b91c6c9); the queued halves-mode scorer is the instance, this rule is the class. User-directed 2026-06-12." -- CLAUDE.md AGENTS.md
```

Expected: smoke `OK`; 2 files.

---

### Task 5: Provenance log + director notification + wrap gates

**Files:**
- Modify: `docs/PROTOCOL-RULES-LOG.md` (provenance entries; insert before `## Retirement criteria`, after the R-SKILL entry landed in `1d80411`)
- Create: mailbox event via `coordination/bin/send-event` (never hand-write)

- [x] **Step 1: Append provenance entries to PROTOCOL-RULES-LOG.md**

```markdown
### Rules #21 + #22 + R-MEASURE + dispatch git-hygiene + SessionStart sweep (2026-06-12, operator ship, user-directed)

One user-directed hardening batch ("plan to apply these", 2026-06-12) of four
items surfaced by the 2026-06-11/12 sessions:

- **Rule #21 verdict-ahead-of-report** — basis: `6f3b809` verdict-first
  unblocked a billed pod session; report `3a13156` followed; nothing
  reversed. Beneficiary (Rule #11): both + user (billed-clock waste removed).
- **Rule #22 flag-before-burn** — basis: reviewed S3 sweep ran clean;
  unreviewed train script carried the F1 fee-respend defect (`3a589da`
  guard). Beneficiary: both + user (fee protection).
- **R-MEASURE** — basis: half-crop S2/S3 verdict numbers were REPL-only
  (operator Lane V `2026-06-11T18:49:37Z`, disposed `b91c6c9`; halves-mode
  scorer queued wave-2 is the instance). Beneficiary: both + user
  (reproducible records).
- **Dispatch git-hygiene (templates + CLAUDE/AGENTS clause)** — basis:
  index-operator corruption 2026-06-12 ("unable to read <blob>") during a
  31-agent workflow; per-invocation `env -u GIT_INDEX_FILE` (subagent shell
  state does not persist). Beneficiary: both (either seat's index).
- **SessionStart sweep registration** — closes the v5.9 post-last-hook-fire
  window (strike #2, 866 paths). Local registration documented in
  OPERATIONS.md. Beneficiary: both.

All five invocable from codification; invocation counts start at the next
session table.
```

- [x] **Step 2: Final gates**

```bash
.venv/bin/python scripts/ci_smoke.py
.venv/bin/python scripts/check_doc_claims.py docs/PROGRAM-MANUAL.md 2>&1 | tail -2
```

Expected: smoke `OK`; no NEW drifts attributable to these edits (PROGRAM-MANUAL is fix-on-touch — untouched here).

- [x] **Step 3: Notify the director (protocol change, user-authorized)**

```bash
coordination/bin/send-event operator director proposal "Process hardening SHIPPED (user-directed): Rules #21/#22 + R-MEASURE + dispatch git-hygiene + SessionStart sweep — disagreement protocol open if any rule text needs amendment" <<'EOF'
User-directed batch ("plan to apply these", 2026-06-12), shipped per plan
docs/superpowers/plans/2026-06-12-two-seat-process-hardening.md:
- Rule #21 verdict-ahead-of-report + Rule #22 flag-before-burn (both twins;
  CLAUDE/AGENTS pointers now #7-#22) — your 6f3b809-unblock + the S3 F1
  incident are the cited basis.
- R-MEASURE (CLAUDE/AGENTS): verdict-backing numbers need a committed
  instrument + logs/ artifact, or an estimate label. Your queued halves-mode
  scorer is the instance; the wave-2 task is unchanged.
- Dispatch templates now carry a Git-hygiene block: subagents prefix all git
  with `env -u GIT_INDEX_FILE` (my index-corruption incident; your seat
  benefits identically). Include it in your dispatches from now on.
- update-state.sh now ALSO fires at SessionStart (settings.local.json,
  machine-local, documented in OPERATIONS.md) — strike-#2's
  post-last-hook-fire window is closed.
Rule text is amendable via the disagreement protocol as usual — user
authority covers the ship, not the wording forever.
EOF
git commit -m "process(log): provenance for the 2026-06-12 hardening batch (#21/#22/R-MEASURE/git-hygiene/SessionStart sweep) + proposal event to director" -- docs/PROTOCOL-RULES-LOG.md coordination/mailbox/sent/
```

Note: use the exact event path `send-event` prints if committing by file (it stages it); `coordination/mailbox/sent/` pathspec also works since the event is the only staged file there.

- [x] **Step 4: Plan checkbox sweep + commit the plan doc itself**

Mark all checkboxes done in this plan file, then:

```bash
git commit -m "docs(plan): two-seat process hardening plan — executed (items 2-5 from the 2026-06-12 user directive)" -- docs/superpowers/plans/2026-06-12-two-seat-process-hardening.md
```

---

## Out of scope (explicit)

- Item #1 from the original list (not requested).
- The halves-mode scorer + A3 single-face assert: queued as DIRECTOR wave-2
  code tasks (`b91c6c9` reply) — R-MEASURE is the class rule; do not duplicate
  the instance work here.
- Any edit to `.claude/hooks/update-state.sh` itself (reuse-only; its tests
  stay green untouched).
- Hardening `.git/index` (the sacrificial default index) against concurrent
  subagent refreshes — accepted residual risk, documented in Task 2.
