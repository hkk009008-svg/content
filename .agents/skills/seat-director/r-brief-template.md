# R-BRIEF template — what a dispatch-ready brief contains

Read this when you are about to author an R-BRIEF (the brief that gates a fix —
read by the co-signer on a CRITICAL cross-cutting row, and by the implementer if
you dispatch). The brief is where **evidence is produced**, not where intentions
are stated: a named symbol without its grep-output is a *type-level claim*, not a
*runtime claim* (Rule #12), and a new guard without a sibling audit is a blind
spot (Rule #13). Fill every slot or say why it's N/A — an empty slot is the
defect that ships.

## Fill-in skeleton

```
# R-BRIEF: <defect-id> — <one-line what+why>

PRIORITY: CRITICAL | MAJOR | MEDIUM        LANE: A (image/identity) | B (video/assembly/audio)
CROSS-CUTTING: yes/no   (auto_approve.py · cinema/context.py · core.py · web_server.py)
  → if yes: LOCK held? <claim-lock output, exit 0=WON>   CO-SIGN: Tier-A/B? (CRITICAL x-cut ⇒ Tier-A BEFORE DISPATCH)

## The defect (file:line + observable symptom)
<where it is, what goes wrong at runtime, and the failure the user/gate sees>

## Rule #12 — grep-the-writes (the symbol is WRITTEN at runtime, not just declared)
TARGET SYMBOL: <field / dict-key / mutator / write-path the new code targets>
$ <grep that proves the production WRITE site>     # e.g. grep -rn "self.spent_usd\s*=" --include='*.py' .
→ <paste the matching file:line output>            # type-declaration is NOT write-evidence
  (mixed-shape symbol — typed attr AND raw-dict? grep BOTH surfaces.)

## Rule #13 — symmetric / sibling audit (what existing sites should mirror, or are missing)
SHARED FENCE/FLAG/STATE: <e.g. the budget gate · screening_approved · a shared lock>
$ <grep the siblings on the same fence>
→ Audited <sites>; mirroring <which guard from which sibling>; folding / deferring <which, why>.

## Full-shape pattern reference (brief-pattern = implicit spec)
MIRROR: <existing helper/endpoint at file:line> — its FULL shape:
  signature · route/pid-scope · error handling · lock guards · return contract.
  (R-PID: a project-scoped endpoint takes <pid> EXPLICITLY — never scan list_projects().)
  If the named helper doesn't exist or the wording is ambiguous → say so HERE, before dispatch.

## The fix (what changes, bounded)
<the intended change + the ~LoC delta + the files touched — scope the implementer must not exceed>

## Verification the operator/CI will run
<the test/pin that must flip, the command + expected result; for a deferred defect, the strict-xfail pin>
```

## "Verified" bar — the brief is not dispatch-ready until

- **Rule #12 slot has real grep OUTPUT** under the target symbol — not "I'll grep later," not the type declaration. Without it, label the symbol *type-level claim* explicitly so the implementer knows.
- **Rule #13 slot names the siblings actually checked** and states fold-or-defer for each under-defended one.
- **Cross-cutting?** The lock was claimed (push-first, exit 0) **before** any code; a CRITICAL cross-cutting brief carries the other lane's Tier-A `verification-report` **before you dispatch or self-implement** (silence ≠ consent; 40 min is not a green light).
- **Pattern refs are full-shape**, not just a function name.

## Dispatch decision (after the brief is verified-complete)

| Situation | Do |
|---|---|
| Small, tightly-coupled change | Implement directly (you author; your operator verifies — impl≠verifier) |
| ≥5 independent sub-tasks OR ≥800 LOC | **Orchestrate** (R-ORCH): a fresh implementer subagent per task, sequential on shared files, reviewers after. Never two implementers in parallel on shared files. See `docs/protocol/claude/orchestration.md`. |
| Dispatching an implementer | Use the body in `docs/templates/claude/implementer.md` — include its **Git-hygiene block** verbatim (subagents prefix git with `env -u GIT_INDEX_FILE`) + items 4–5 (brief-pattern adherence, pid-scope). |

**Name the right specialist reviewer** when the lane has one — these are real dispatch targets:
- **Money / cost-gate fix** (CostTracker, `spent_usd`, per-shot veto, budget pre-check) → the **`money-gate-reviewer`** agent (hunts gate-source-mismatch + silent-gate-degradation).
- **Post-commit independent verification** is your operator's job, who dispatches the **`lane-v-verifier`** agent (you do NOT verify your own pair's fix).
- **ComfyUI-graph / pipeline-design content** → load `comfyui-mastery` / `ai-video-gen` BEFORE authoring or judging the code (R-SKILL).

## Worked fragment (Rule #12 slot done right)

```
## Rule #12 — grep-the-writes
TARGET SYMBOL: CostTracker.spent_usd (the gate reads only this accumulator)
$ grep -rn "self\.spent_usd\s*=\|self\.spent_usd\s*+=" --include='*.py' . | grep -v /tests/
→ cost_tracker.py:227  self.spent_usd: float = 0.0
  cost_tracker.py:306  self.spent_usd += cost_usd     # the ONE write chokepoint (log() delegates here)
  ⇒ runtime-written confirmed; the gate's single source of truth is this line, not the type hint.
```
