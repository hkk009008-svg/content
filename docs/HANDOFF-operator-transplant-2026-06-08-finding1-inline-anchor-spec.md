# Operator transplant handoff — 2026-06-08 — Finding-1 inline-anchor verifier (spec mid-review)

**READ FIRST IF PICKING UP AS OPERATOR.**

## 0. State at wrap

- **Branch:** `feat/max-tier-provisioning`. **HEAD = `b294950`** (local; ahead of
  `origin/feat` — this session's commits are UNPUSHED, push is strategic-seat/user call).
- **`origin/main` = `a0480f5`** (unchanged this session; the portrait Phase-2 arc + all
  prior work merged earlier). The Part-3/portrait program is on main and GREEN.
- **0 unread** for operator; **cursor `05:06:02Z`**. Nothing owed via mailbox.
- **presence:** operator=wrapping; director=active (on Phase-3 — see §5).
- **§15 smoke OK**, full suite GREEN at last check (no production code touched this
  session — all work was Lane V / FE-render / docs / spec).

## ⭐ #1 PICKUP — finish the Finding-1 inline-anchor verifier (USER-directed, mid-flow)

The user directed operator to **"extend check_doc_claims.py for inline-backtick
anchors"** (Finding 1 from this session — the verifier blind spot). I am **mid-flow in
the `superpowers:brainstorming` skill**, at the spec-review loop. **HARD-GATE: do NOT
start implementation until the user approves the written spec** (brainstorming skill
rule). Sequence to resume:

1. **Consume the iteration-2 re-review** (`wf_e84e5012-1b4`, doc-completeness +
   adversarial on spec v2). It was IN-FLIGHT at wrap. **[VERDICT — see §2.3; if the
   /tmp output is gone (cross-session), re-run a 2-reviewer spec-review on `b294950`
   confirming the iter-1 fixes, or just proceed to step 2 — the user gate is the real
   decision point.]**
2. **User spec-review gate:** ask the user to review
   `docs/superpowers/specs/2026-06-08-inline-backtick-anchor-verification-design.md`
   (currently **v2 @ `b294950`**) and approve before planning. If they request changes,
   fold + re-review.
3. **`writing-plans`** → an implementation plan (Slice 1 = tool + tests via TDD;
   Slice 2 = repo-wide sweep).
4. **TDD implement** Slice 1, then **run the repo-wide sweep** (Slice 2).

## 1. What shipped this session (all committed, UNPUSHED on feat)

| Item | Commit | Status |
|---|---|---|
| **CC-1 Lane V** on portrait Phase-2 (the prior #1 pickup) | `f849f6b` (report) | ✅ CLOSED — 5/5 dims clean, 9 INFORMATIONAL / 0 actionable, 0 hallucinations; inert-at-16:9 adversarially confirmed (whole-dict snapshot identity). Director **concurred option-c** (`87d7022`); forward-carries (SPEC-3 schnell smoke) folded into Phase-3 spec (`903aa68`). Nothing owed. |
| **F5** — render `visual_findings` in FE Deep Diagnosis box | `a7216d1` | ✅ DONE. `web/src/components/pipeline/ReviewStage.tsx` — backend already wired it to `advisory_deep.visual_findings`; FE just didn't render it. Placed first in the box, labeled. `diagnosis` is `useState<any>` → no type change. Backend test 16 passed; `npm run build` (tsc+vite) green. |
| **Rule #18 anchor sweep** — chief_director.py anchors in MANUAL + digests | `3f2c149` | ✅ DONE. ~30 drifted line-anchors fixed (file grew 501→664; SYSTEM_PROMPT :147→:217 shifted everything below). 32 swaps / 23 refs, count-asserted + R-OP-1 spot-checked 8/8, 0 hallucinations. |
| **2 findings surfaced** to director | `1ec885f` | Finding 1 (verifier blind spot) → **now being implemented (#1 pickup)**. Finding 2 (D-a skip-worktree corruption) → director **wrote the memory** (consolidated into `feedback_da_stale_index_refresh.md` as a two-vector memory). |
| **Finding-1 claim** (deconflict) | `5d1d3fa` | Operator claimed Finding-1 per user direction, overriding director's `05-06-02Z` "carry-forward" (user-tier > mailbox). Director has NOT picked it up (verified git log); proceed. |

## 2. Finding-1 detail (the in-flight work)

### 2.1 Design (user-APPROVED in brainstorming)
3 decisions chosen via AskUserQuestion: **resolve-unique + advise-ambiguous** basenames;
**full repo-wide sweep** (tool + tests + fix all inline-anchor drift); **conservative
false-positive** guard. Approach **A — extend in place** (unify anchor iteration; reuse
`check_anchor`/`_def_lines`/`_apply_fixes`/`_shift_display`).

### 2.2 Spec history
- v1 `1aed6ed` → spec-review iteration 1 (`wf_cd203e8e-392`, 3 cold reviewers):
  tech-grounding **APPROVED** (all code-claims TRUE at HEAD; caught an ADR-013 count error
  — "18 collide" is wrong, it's **9 colliding basenames / 27 files**); doc-completeness +
  adversarial found 1 BLOCKING + several IMPORTANT/MINOR.
- **v2 `b294950`** folded ALL iteration-1 findings. Headline = the **BLOCKING fix**:
  `ambiguous_path` exit-neutral would have silently passed ~54 *bare-ambiguous* manual
  anchors (`controller.py`×34 etc.) — re-creating the false-green the project exists to
  kill. Fix = **symbol-disambiguation** (ambiguous basename + bound symbol resolving to
  exactly one candidate-that-defines-it → real def-drift check) + Slice-2 sweep qualifies
  residual to zero + optional future `--strict`. Also folded: fenced-code-block awareness
  (checker + `--fix`); letters-only ext class `[A-Za-z]+` (rejects `v1.2:30`); de-dup by
  `(file,line)` equality not span-inside; preceding-backtick-only symbol bind;
  all-tracked-files basename index; `Drift.style` field for fix routing; +6 tests; count
  fix. Operator spot-checked reviewer evidence (count=9/27, ~54 bare anchors, regex) —
  0 hallucinations.

### 2.3 Iteration-2 re-review verdict
<!-- IN-FLIGHT at wrap (wf_e84e5012-1b4). Fill from the notification if it lands; else
the next operator re-runs or proceeds to the user gate. -->
**[PENDING — was running at wrap; consume `wf_e84e5012-1b4` result or proceed to the user
spec-review gate, which is the actual decision point.]**

### 2.4 Implementation surface (already mapped — saves the next operator a read)
`scripts/check_doc_claims.py` (808 lines): `_ANCHOR_RE` (L48, markdown-link only, ext
`[A-Za-z]+`); `check_anchor` (L79 — resolve file, bind symbol via nearest-backtick
before/after, def-drift via `_def_lines` L60 + range-match L145-156, bounds L180);
`check_line_anchors` (L203 — iterates `_ANCHOR_RE` per line); `_shift_display` (L241 —
bare + range shift, syntax-agnostic, REUSE as-is); `_apply_fixes` (L261 — per-line
`_ANCHOR_RE.sub` producing `[display](file:new)` — needs a backtick-form branch for
inline + the `Drift.style` field). `--sha-refs`/`--show-subjects`/manifest are separate
(untouched). Test harness `tests/unit/test_check_doc_claims.py` (874 lines): `_write_py`
L43, `_write_md` L49, `_init_repo` L66 (git-init only — does NOT commit source; new
basename tests must `git add`+commit the .py so `git ls-files` populates). **Run tests
with `env -u GIT_INDEX_FILE`** (D-a launch index breaks tmp-repo tests).

## 3. Open items + ownership

- **#1 (operator):** finish Finding-1 (above).
- **(operator, standing) Phase-3 per-feat Lane V** — when director's Phase-3
  implementation lands, run independent Lane V per feat-commit (Rule #9). Director will
  signal the first feat commit. No scout-request expected.
- **(strategic/user) push `feat` → origin / merge to main** — this session's commits are
  unpushed; push/merge is the strategic-seat/user call.
- Carry-forwards (pre-existing): on-pod 9:16 latent validation (GPU-up); F5 is now done.

## 4. ⚠️ Recurring D-a skip-worktree corruption (N=4 this session)

`index-operator` repeatedly re-acquires **~664 orphaned skip-worktree bits** (with
`core.sparseCheckout` UNSET) — caused by background-Workflow/subagent git ops inheriting
the seat `GIT_INDEX_FILE`. Symptom: `git add`/`diff`/commit **silently ignore**
working-tree edits to tracked files ("outside sparse-checkout" / empty diff on an edited
file). **NEW files are immune** (skip-worktree only affects tracked files). **Remedy:
`git read-tree HEAD` immediately before every commit that touches a tracked file**, then
`git add` + pathspec commit. Both seats hit this; documented in
`feedback_da_stale_index_refresh.md` (two-vector). Hit it once and it'll cost you a
silently-dropped edit (it dropped the cursor at `5d1d3fa`, re-landed `1e7f0cc`).

## 5. Director (concurrent) — Phase 3

Director is live on their **#1 pickup, Phase 3** (per-provider 9:16 video + un-gate).
Spec written + reviewed (`682e773`→`903aa68`→`93c6338`; doc-reviewer APPROVED, 9/9
tech-grounding). Ship set = Veo+Sora+Kling+Runway; un-gate LAST behind an `ffprobe`
preflight. Next (director): user spec review → `writing-plans` → Lane B implementation.
**Your Lane V applies per-feat-commit when it lands.**

## 6. Mailbox / cursor

cursor `05:06:02Z`; 0 unread. Last operator sends: `1ec885f` (findings),
`5d1d3fa`+`1e7f0cc` (Finding-1 claim + cursor), spec commits `1aed6ed`/`b294950`.
Last director event processed: `05-06-02Z` (memory written, Finding-1 tracked, Phase-3
spec review complete). **D-a-safe commits: `git read-tree HEAD` → `git add <paths>` →
`git commit -m … -- <paths>`** (pathspec mandatory; `-m` before `--`).
