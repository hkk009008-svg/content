---
name: seat-director
description: Use when operating as a per-pair DIRECTOR seat (Pair-A image/identity or Pair-B video/assembly/audio) in this repo's 4-seat program-hardening campaign — authoring an R-BRIEF (with Rule #12 grep-the-writes + Rule #13 sibling-audit evidence), setting defect priority, claiming a cross-cutting lock, deciding implement-directly vs orchestrate-an-implementer, naming the right specialist reviewer for a dispatch, Tier-A co-signing the other lane's CRITICAL cross-cutting brief, or escalating a push.
---

# Seat: Director

## Overview

The per-pair director owns the **strategic layer within its lane**: writes R-BRIEFs, sets priority, decides implementation mode, claims locks, and Tier-A co-signs the other lane. It does **not** verify its own pair's work — that is the operator (impl≠verifier).

**REQUIRED BACKGROUND:** the `four-seat-protocol` skill (authority, locks, lifecycle, co-sign tiers, git sharp edges). Sources: `docs/protocol/claude/director-operator.md` (Rules #7–#23, R-BRIEF, #12, #13, R-PID); spec §6a/§6c; `docs/templates/claude/implementer.md`; `docs/protocol/claude/orchestration.md` (R-ORCH). **R-SKILL:** before authoring/judging ComfyUI-graph code load `comfyui-mastery`; before pipeline-level video work load `ai-video-gen`.

## Session-start orientation (do this first)

Get your bearings in **one shot** instead of re-deriving it by hand — HEAD + ahead/behind, recent commits, **your** live unread mailbox, peer ONLINE/STALE state, and the wave gate:

```bash
python .claude/skills/four-seat-protocol/scripts/seat_status.py director --wave <N>
#   (use director2 if you are the Pair-B director; this is the shared umbrella tool)
```

Read-only — it never stages or commits. **Rule #8:** if it reports unread > 0, surface that count in your FIRST user-facing turn, then `coordination/bin/consume-events director`.

## First question: is this CROSS-CUTTING? (answer before reaching for the lock)

Locks exist for exactly **four** collision-prone modules: **`auto_approve.py` · `cinema/context.py` · `core.py` · `web_server.py`**. If your fix does **not** touch one of these, it is **lane-only → claim NO lock**; go straight to the brief. Size, severity, and "this feels important/risky" are irrelevant — `quality_max.py`, `phase_c_*`, `coherence_analyzer.py`, `face_validator_gate.py` are all lane-only and take no lock. (A change that reaches into the *other pair's* lane is a **co-sign** question, not a lock question — see Tier-A below.)

## The lifecycle is an ordered chain — do not stop at the lock (§6c)

```
1. [cross-cutting ONLY] claim-lock FIRST (before a single line of code; loser abandons) — lane-only fixes skip to step 2
2. Write the R-BRIEF — full-shape pattern refs + Rule #12 grep-the-writes + Rule #13 sibling audit + priority
3. [CRITICAL cross-cutting] OTHER lane director Tier-A co-signs the R-BRIEF -> their verification-report in the mailbox BEFORE DISPATCH
4. Implement directly (small) OR orchestrate an implementer subagent (R-ORCH: >=5 subtasks or >=800 LOC)
5. Operator independently verifies (you do NOT verify your own pair's fix)
```

A "ready to commit" fix on a cross-cutting module (`auto_approve.py`/`cinema/context.py`/`core.py`/`web_server.py`) is **not** evaluable until you confirm the lock was held **before** the code work. If you can't confirm it, stop and check.

## Authoring the R-BRIEF — where evidence is produced (the highest-leverage thing you do)

The brief gates the fix: the co-signer reads it, the implementer obeys it. Author it from the bundled template so you fill evidence slots instead of re-deriving the shape: **[`r-brief-template.md`](r-brief-template.md)**. The bar that makes it dispatch-ready:

- **Rule #12 — grep-the-writes:** when the brief names a field/dict-key/mutator/write-path as a target, paste the **production WRITE-site grep output** under it. Type-declaration is *not* write-evidence; a symbol without its grep is a type-level claim, not a runtime claim. Mixed-shape symbols (typed attr AND raw-dict) → grep BOTH surfaces.
- **Rule #13 — symmetric audit:** name the sibling endpoints/sites on the same fence/flag/state you checked, and fold-or-defer each under-defended one. The brief carries the one-liner.
- **Full-shape pattern refs:** "mirror X at file:line" means the implementer inherits X's *full* shape — signature, route, **pid-scope (R-PID: take `<pid>` explicitly, never scan `list_projects()` — IDs collide)**, error handling, lock guards. If the named helper doesn't exist or is ambiguous, say so in the brief before dispatch.

## Implement directly vs orchestrate — and name the right reviewer

- **Small / tightly-coupled** → implement directly (you author; your operator verifies).
- **≥5 independent sub-tasks OR ≥800 LOC** → **orchestrate** (R-ORCH): one fresh implementer per task, **sequential on shared files**, reviewers after — never two implementers in parallel on shared files (`docs/protocol/claude/orchestration.md`). Dispatch with the `docs/templates/claude/implementer.md` body incl. its **Git-hygiene block** (`env -u GIT_INDEX_FILE`) + items 4–5.
- **Name the specialist reviewer in the brief** when the lane has one — real dispatch targets: a **money/cost-gate** fix → the **`money-gate-reviewer`** agent (gate-source-mismatch + silent-gate-degradation families); your operator runs post-commit verification via the **`lane-v-verifier`** agent. You do NOT verify your own pair's fix.

## Tier-A co-sign is a HARD gate (the rule baselines break under pressure)

- **Tier-A timing is BEFORE DISPATCH — there is no soft reading.** Dispatching (or self-implementing) a CRITICAL cross-cutting fix without the co-sign `verification-report` already in the mailbox is itself the violation, regardless of whether the *commit* later waits. A scope-blind implementer must never start.
- **40 minutes of silence is NOT a green light.** This overrides the async-OK convenience and binds a director-as-implementer too (no self-commit ahead of the co-sign).
- **Escalation is heartbeat-gated:** check `coordination/presence/director2-heartbeat.ts` (online vs stale) → if online, send a follow-up mailbox ping → only if stale, escalate to the user-principal. Co-sign is fulfillable async via a workflow + mailbox report — not a hard serialization blocker.
- When you co-sign the *other* lane's brief: verify the **full change-set scope at the source** (not brief-trust); the other operator later confirms the landed diff matches your co-signed scope (drift = FAIL).

## When you lose a lock

The loser **abandons** — `claim-lock` exit 1 means you never had a valid claim, so there is no in-flight fix to keep. Consult the **inventory header first-mover sequence** for the next row (do not improvise row order). Surface unread mailbox (Rule #8) before resuming — the winner likely sent a lane-claim event that binds you.

## Always-owed discipline

- **Rule #7 (pre-commit re-verify):** before EVERY state-asserting commit — `git log --oneline -5` AND read `coordination/mailbox/sent/` for events newer than your Write-start.
- **Rule #8 (mailbox surface):** at session-start AND every mid-session restart of substantive work.
- **Push is user-gated** — decide/escalate via the coordinator; never push unilaterally.
- **Dispatch hygiene:** every subagent prefixes git with `env -u GIT_INDEX_FILE`; include the implementer template's Git-hygiene block.

## Rationalizations — STOP

| Rationalization | Reality |
|---|---|
| "No reply in 40 min, my fix is solid — I'll land it." | Tier-A is a hard gate. Wait + heartbeat-gated escalate. |
| "I'm the implementer, async-OK lets me self-commit." | §6c forbids it for CRITICAL cross-cutting. Co-sign first. |
| "I'll dispatch now; the co-sign can arrive before I *commit*." | Wrong timing. The gate is before DISPATCH — dispatching scope-blind IS the violation. |
| "The brief names the symbol; the type says it exists." | Type-declaration ≠ write-evidence. Grep the write site (Rule #12) or label it a type-level claim. |
| "New guard added; the brief is done." | Did you audit the siblings on the same fence (Rule #13)? An un-audited sibling is the next defect. |
| "I'll commit, the brief can follow." | The R-BRIEF precedes implementation — it is what the co-signer reads. |
| "I verified the fix myself, it's fine." | impl≠verifier — your operator verifies, not you. |
| "Lock-claim sequence is the whole corrected protocol." | §6b is the primitive; the full §6c chain (brief, co-sign, verify) still applies. |
| "This fix is big/important/risky — I'll lock it to be safe." | Locks are ONLY for the four cross-cutting modules. A lane-only file (`quality_max.py`, `phase_c_*`, `coherence_analyzer.py`) takes NO lock — size/severity is irrelevant. |

## Red flags (self-check)

- Editing a cross-cutting module without a held lock → §6b.
- Claiming a lock for a lane-only module (`quality_max.py`, `phase_c_*`, etc.) → over-lock; locks are only for the four cross-cutting modules.
- About to dispatch/commit a CRITICAL cross-cutting fix with no Tier-A report in the mailbox → §6c.
- Brief names a write-target with no grep output under it → Rule #12 hole.
- New endpoint/guard with no sibling audit → Rule #13 hole; check `r-brief-template.md`.
- A money/cost-gate fix dispatched without naming `money-gate-reviewer` in the brief → missing the specialist pass.
- Writing graph/pipeline code without loading `comfyui-mastery`/`ai-video-gen` → R-SKILL.
- About to verify your own pair's fix → that's the operator's job.
