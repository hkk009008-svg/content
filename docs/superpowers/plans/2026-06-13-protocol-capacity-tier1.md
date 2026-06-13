# Protocol Capacity — Tier-1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the three lowest-risk, highest-confidence capacity levers from the 2026-06-13 protocol audit (workflow `wf_6be2ee18-f4b`) — compact the over-budget MEMORY.md, codify handoff-doc hygiene + relocate recurring git sharp-edges into one standing place, and add a verification-tiering rule — to cut coordination overhead **without removing load-bearing safety**.

**Architecture:** Three independent doc/process changes. Task 1 edits the *out-of-repo* auto-memory file (no git commit). Tasks 2 & 3 edit in-repo protocol docs on the isolated branch `protocol-capacity-tier1`. No production Python changes; verification is `ci_smoke` + size/grep checks. Each lever is the **steelman-refined** form from the audit (narrower than the raw proposal — the steelman is why we do NOT mass-rename handoffs, NOT move coordination events to gitignored files, and NOT merge R-EVIDENCE/R-MEASURE).

**Tech Stack:** Markdown docs; `scripts/ci_smoke.py` (run via the main repo venv `/Users/hyungkoookkim/Content/.venv/bin/python`).

**Scope guard:** Levers #5–#8 (commit batching, git-worktree migration, Rule #23 split, coordinator-seat change) rewrite code/machinery all five seats depend on and are explicitly OUT of scope — held for a separate, explicitly-authorized effort.

**Provenance:** Audit result file `/private/tmp/claude-501/-Users-hyungkoookkim-Content/3dd124ed-7e9a-4b22-b546-7f7c2dfc7bc9/tasks/w0cd8gtom.output` (12 levers, each steelmanned; all verdicts = `modify`).

---

## Chunk 1: Tier-1 capacity levers

### Task 1: Compact MEMORY.md (lever #1 — out-of-repo auto-memory)

**Why:** MEMORY.md is 33.7 KB against a 24.4 KB harness limit — it is **silently truncated every session** (the harness warned this in the current session), which means state is being lost at session start. The file's own instructions already mandate one-line index entries (`~200 chars`); the "Current state" entries currently run 700–1,400 chars each.

**Refined change (steelman-survived):** enforce one-line entries; delete entries explicitly marked historical/superseded; move volatile HEAD/push/pod/ahead state OUT entirely (replaced by a single "always check git" sentinel); KEEP the one header-level STALE sentinel (it is load-bearing per the coordinator handoff). Do NOT add a new size-check ceremony — the one-line rule is the enforcement.

**Files:**
- Modify: `/Users/hyungkoookkim/.claude/projects/-Users-hyungkoookkim-Content/memory/MEMORY.md`

- [ ] **Step 1: Snapshot baseline + capture referenced docs (integrity guard)**

Run:
```bash
mem="/Users/hyungkoookkim/.claude/projects/-Users-hyungkoookkim-Content/memory/MEMORY.md"
wc -c "$mem"
grep -oE '\(([a-zA-Z0-9_./-]+\.md)\)' "$mem" | tr -d '()' | sort -u
```
Expected: ~33.7 KB; a list of referenced topic/handoff docs. Record it — every referenced doc must still be resolvable after the rewrite (no dangling pointer introduced).

- [ ] **Step 2: Rewrite the "Current state" section to one-line entries**

For each "Current state" bullet, collapse to: `**[<seat> <date>](<doc>.md)** — <≤150-char clause: what changed + what is OPEN/CLOSED>`. Delete bullets explicitly marked historical/superseded (e.g. older director PM wraps superseded by a later same-seat wrap that the entry itself names as superseding). Preserve all "Standing directives & feedback" entries (already terse durable facts) and all `[[topic]]` links. Keep the single header STALE sentinel line.

- [ ] **Step 3: Replace volatile git-state prose with one sentinel line**

Remove every "push USER-gated / N ahead / nothing pushed / $0 / origin public / HEAD <sha>" phrase from the body. Add one line under the Current-state header:
`> Push/HEAD/pod state is NOT tracked here — always run \`git log -1\` + \`git rev-list --count origin/main..HEAD\`. Trust git, not prose.`

- [ ] **Step 4: Verify size + pointer integrity**

Run:
```bash
mem="/Users/hyungkoookkim/.claude/projects/-Users-hyungkoookkim-Content/memory/MEMORY.md"
wc -c "$mem"  # expect < 24400
for d in $(grep -oE '\(([a-zA-Z0-9_./-]+\.md)\)' "$mem" | tr -d '()' | sort -u); do
  base=$(basename "$d")
  ls "/Users/hyungkoookkim/.claude/projects/-Users-hyungkoookkim-Content/memory/$base" >/dev/null 2>&1 \
    || ls "/Users/hyungkoookkim/Content/$d" >/dev/null 2>&1 \
    || echo "DANGLING: $d"
done
```
Expected: size < 24,400 bytes; zero `DANGLING` lines.

- [ ] **Step 5: No commit** — MEMORY.md is the user's auto-memory outside the repo. The memory subsystem persists it directly; there is nothing to commit.

---

### Task 2: Handoff-doc hygiene (lever #2 — repo, on branch)

**Why:** 119 active HANDOFF docs (21.8 KLOC); filenames up to 131 chars bake *reversible verdicts* into permanent names (`...task4-GO-shipping-default-cleared-pod-BILLING.md`), which go stale within hours and force "STALE — trust git" caveats. Recurring git-tooling "sharp edges" are re-derived across 5+ successive handoffs instead of living in one standing place.

**Refined change (steelman-survived):** (a) codify a handoff *filename convention* going forward — seat + date + sequence only, verdicts live in the body; do NOT mass-rename existing files (append-only history is load-bearing for concurrent-write race detection). (b) Consolidate the durable git-tooling sharp edges into ONE standing section in `core.md` and point CLAUDE.md's git-mechanics at it, so handoffs reference rather than re-derive.

**Files:**
- Modify: `docs/protocol/claude/core.md` (add "Session-wrap & handoff hygiene" + "Git-tooling sharp edges (standing)" sections)
- Modify: `CLAUDE.md` (point the git-mechanics section at the new standing sharp-edges section)

- [ ] **Step 1: Add the handoff filename convention to `core.md`**

Append a new section after "When you change something":
```markdown
# Session-wrap & handoff hygiene
*Capacity lever #2 (audit wf_6be2ee18-f4b). Cuts stale-filename churn.*

- **Handoff filenames carry NO reversible state.** Name = `HANDOFF-<seat>-YYYY-MM-DD[-PMn].md` only (seat + date + optional sequence). Verdicts, GO/NO-GO, pod/push/HEAD status, blast-radius — all live in the BODY, where they can be corrected without spawning a new file. A filename like `...task4-GO-...-pod-BILLING.md` is false hours later and forces "STALE — trust git" caveats downstream.
- **Body is reconstructable-minus-git.** Record only: last_commit SHA, open carry-forwards with status, session-specific sharp edges not yet promoted to a standing doc, cursor position. Omit anything `git log` already proves.
- Append-only across sessions is retained (one file per seat per session) — it is the concurrent-write race-detection signal; do not overwrite-in-place.
```

- [ ] **Step 2: Consolidate durable git-tooling sharp edges into `core.md`**

Append a standing section that absorbs the recurring edges (currently scattered across `director-operator.md`, `four-seat-extension.md`, CLAUDE.md, and re-derived in handoffs):
```markdown
# Git-tooling sharp edges (standing — stop re-deriving these in handoffs)
*Capacity lever #2. These are durable environment facts, not session observations.*

- **Stale per-seat / default index → phantom `MM`/deletions.** `git status` and `git diff --stat HEAD` read the index and can show committed files as modified/deleted. Ground truth: `git cat-file -e HEAD:<f>` (in HEAD?) + `test -f <f>` (on disk?). Reseed with `git read-tree HEAD`.
- **macOS `core.ignorecase=true` collapses case-only renames.** `git mv Foo.json foo.json` can become a no-op/duplicate. Verify via the object store (`git ls-tree HEAD`), or use `git -c core.ignorecase=false`, or `rm --cached` + `add`.
- **Partial commits need an explicit pathspec.** `git commit -m … -- <path>` builds a temp index from HEAD and cannot sweep a peer's staged WIP even if HEAD moved under you. A bare `git commit` from a shared/default index can sweep peers — always pathspec-scope.
- **Subagent git uses `env -u GIT_INDEX_FILE`** (subagent shell state does not persist); main-seat commits go through the per-seat index directly — do NOT apply `env -u` there.
- **ComfyUI re-render of an identical graph+seed = cache hit → empty `/history` outputs** (false-fail, not OOM). Cache-bust the filename_prefix / use fresh seeds.
```

- [ ] **Step 3: Point CLAUDE.md's git-mechanics at the standing section**

In `CLAUDE.md` under "Claude Code mechanics", add one bullet:
```markdown
- **Git-tooling sharp edges** — the recurring shared-tree/index edges (phantom index, case-only renames, pathspec discipline, `env -u GIT_INDEX_FILE`) are documented once in `docs/protocol/claude/core.md` → "Git-tooling sharp edges (standing)". Reference it; do not re-derive in handoffs.
```

- [ ] **Step 4: Verify ci_smoke green + sections present**

Run:
```bash
cd "$HOME/.config/superpowers/worktrees/Content/protocol-capacity-tier1"
/Users/hyungkoookkim/Content/.venv/bin/python scripts/ci_smoke.py 2>&1 | tail -1
grep -c "Session-wrap & handoff hygiene\|Git-tooling sharp edges (standing" docs/protocol/claude/core.md
grep -c "Git-tooling sharp edges" CLAUDE.md
```
Expected: ci_smoke `OK`; core.md count = 2; CLAUDE.md count ≥ 1.

- [ ] **Step 5: Commit (on branch)**

```bash
cd "$HOME/.config/superpowers/worktrees/Content/protocol-capacity-tier1"
git add docs/protocol/claude/core.md CLAUDE.md
git commit -m "docs(protocol): handoff-filename hygiene + consolidate git sharp-edges (capacity lever #2)"
```

---

### Task 3: Verification tiering (lever #3 — repo, on branch)

**Why:** The protocol applies the same adversarial multi-agent depth to a doc-only note about an undisputed deferred defect as to irreversible production code. The §8.5 char-landscape note consumed ~25–31 Sonnet agent-runs across 4 independent passes to produce one ARCHITECTURE.md paragraph and zero fix lines. Separately, agent-found deferred defects ship with no RED test, so the next session must re-verify by agent rather than by CI.

**Refined change (steelman-survived):** two narrow rules. (A) Doc-only deferred-defect notes converge at **two** independent seats; a 3rd pass requires a *stated new question* (the director Rule #23 co-sign = pass 1, operator re-verify = pass 2). This does NOT touch production-code verification (Lane V / Rule #9 stays per-commit). (B) An agent-confirmed defect that is NOT fixed in the same session must ship a `pytest.mark.xfail(strict=True, reason=...)` pin (or be labeled `test-infeasible` with a reason). Keep R-EVIDENCE and R-MEASURE separate (the steelman showed the split caught a real gap).

**Files:**
- Modify: `CLAUDE.md` (add `R-VERIFY-TIER` stub in the verification cluster, after R-MEASURE ~L111)
- Modify: `docs/protocol/claude/core.md` (the detail, in the verification-discipline area)
- Modify: `docs/PROTOCOL-RULES-LOG.md` (provenance entry)

- [ ] **Step 1: Add the `R-VERIFY-TIER` stub to CLAUDE.md**

Insert after the R-MEASURE block (before "# Multi-task orchestration"):
```markdown
# Verification tiering (R-VERIFY-TIER)
Scope: both
Trigger: about to launch a 3rd+ independent verification pass on a claim two seats
already confirmed; OR confirming a code defect you are NOT fixing this session.
Action: (A) For doc-only notes about an already-known/deferred defect, convergence =
TWO independent seats confirming the same file:line claims (a Rule #23 co-sign counts
as one). A 3rd pass is allowed ONLY for a genuinely different question, stated before
launch. Does NOT relax per-commit production-code verification (Lane V / Rule #9).
(B) An agent-confirmed defect left unfixed this session must ship a
`pytest.mark.xfail(strict=True, reason=...)` pin in the same session, or be labeled
`test-infeasible` with a one-line reason in the handoff — so CI, not next session's
agents, re-verifies.
Evidence: the stated new question for any 3rd pass; the xfail pin (or test-infeasible label).
Details: docs/protocol/claude/core.md (R-VERIFY-TIER); origin = audit wf_6be2ee18-f4b
(the §8.5 quadruple-verify on a doc note).
```

- [ ] **Step 2: Add the detail block to `core.md`**

Append after the "When you cannot comply" verification subsection:
```markdown
## Verification tiering (R-VERIFY-TIER)
*Router handle: `R-VERIFY-TIER` (stub in CLAUDE.md). Capacity lever #3, audit wf_6be2ee18-f4b.*

The discipline that prevents under-verification (R-EVIDENCE, Rule #9) has no
companion that prevents OVER-verification. The §8.5 char-landscape note — a doc-only
paragraph about an undisputed, deferred defect — drew ~25–31 adversarial agent-runs
across four passes (wf_73f95c8c / wf_e09bded6 / wf_5d39bbe3 / wf_ed13f2b4), producing
zero fix code. Past the second independent confirmation, additional passes on the same
question add cost, not confidence.

- **(A) Convergence cap for doc-only deferred-defect notes.** Two independent seats
  confirming the same file:line claims = converged. A Rule #23 co-sign is one of the
  two. A third adversarial pass is justified ONLY when scoped to a *different* question
  (e.g. blast-radius mapping beyond the note, as wf_5d39bbe3 legitimately was) — and
  the launching seat must state that incremental question first. This applies to
  `docs(arch)`-class deferred notes only; production code keeps Lane V / Rule #9
  per-commit verification.
- **(B) RED test at find-time.** When an adversarial workflow or agent-assisted
  investigation confirms a code defect that is NOT being fixed this session
  (`fix_with_brief` / `fix_deferred`), the finding seat commits a
  `pytest.mark.xfail(strict=True, reason='...')` reproducing the failure in the same
  session. If a faithful test is infeasible within budget, label the finding
  `test-infeasible` with the specific reason in the handoff. Turns O(agents × sessions)
  re-verification into O(seconds in CI).

Keep R-EVIDENCE (cite the command) and R-MEASURE (commit the instrument) distinct —
they close different gaps. R-VERIFY-TIER caps the *number* of passes; it does not
weaken any single pass.
```

- [ ] **Step 3: Log provenance in PROTOCOL-RULES-LOG.md**

Insert a rule entry above "## Retirement criteria":
```markdown
- **R-VERIFY-TIER** (capacity lever #3, audit `wf_6be2ee18-f4b`, 2026-06-13) —
  caps verification DEPTH where R-EVIDENCE/Rule #9 only ever raised it. (A) doc-only
  deferred-defect notes converge at two independent seats; 3rd pass needs a stated new
  question. (B) agent-confirmed unfixed defects ship an `xfail(strict)` pin or a
  `test-infeasible` label. Empirical basis: the §8.5 char-landscape note drew ~25–31
  agent-runs across 4 passes for one doc paragraph + 0 fix lines. Beneficiary: both
  (frees cycles for the deliverable). Does NOT relax production-code verification.
```

- [ ] **Step 4: Verify ci_smoke green + rule present in all three files**

Run:
```bash
cd "$HOME/.config/superpowers/worktrees/Content/protocol-capacity-tier1"
/Users/hyungkoookkim/Content/.venv/bin/python scripts/ci_smoke.py 2>&1 | tail -1
grep -l "R-VERIFY-TIER" CLAUDE.md docs/protocol/claude/core.md docs/PROTOCOL-RULES-LOG.md
```
Expected: ci_smoke `OK`; all three files listed.

- [ ] **Step 5: Commit (on branch)**

```bash
cd "$HOME/.config/superpowers/worktrees/Content/protocol-capacity-tier1"
git add CLAUDE.md docs/protocol/claude/core.md docs/PROTOCOL-RULES-LOG.md
git commit -m "docs(protocol): add R-VERIFY-TIER — cap verification depth + RED-test-at-find-time (capacity lever #3)"
```

---

## Completion

After all tasks: use superpowers:finishing-a-development-branch to present merge/PR options. Note the plan file itself is on the branch; include it in the final integration. Merge to `main` is a USER decision (these are shared protocol docs the four working seats read).
