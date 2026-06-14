---
name: seat-director
description: Use when operating as a per-pair DIRECTOR seat (Pair-A image/identity or Pair-B video/assembly/audio) in this repo's 4-seat program-hardening campaign — writing an R-BRIEF, setting defect priority, claiming a cross-cutting lock, deciding implement-directly vs dispatch an implementer, Tier-A co-signing the other lane's CRITICAL cross-cutting brief, or escalating a push.
---

# Seat: Director

## Overview

The per-pair director owns the **strategic layer within its lane**: writes R-BRIEFs, sets priority, decides implementation mode, claims locks, and Tier-A co-signs the other lane. It does **not** verify its own pair's work — that is the operator (impl≠verifier).

**REQUIRED BACKGROUND:** the `four-seat-protocol` skill (authority, locks, lifecycle, co-sign tiers, git sharp edges). Sources: `docs/protocol/claude/director-operator.md` (Rules #7–#23, R-BRIEF, #12, #13, R-PID); spec §6a/§6c; `docs/templates/claude/implementer.md`. **R-SKILL:** before authoring/judging ComfyUI-graph code load `comfyui-mastery`; before pipeline-level video work load `ai-video-gen`.

## The lifecycle is an ordered chain — do not stop at the lock (§6c)

```
1. [cross-cutting] claim-lock FIRST (before a single line of code; loser abandons)
2. Write the R-BRIEF — full-shape pattern refs + Rule #12 grep-the-writes evidence + Rule #13 sibling audit + priority
3. [CRITICAL cross-cutting] OTHER lane director Tier-A co-signs the R-BRIEF -> their verification-report in the mailbox BEFORE DISPATCH
4. Implement directly (small) OR dispatch an implementer subagent (R-ORCH: >=5 subtasks or >=800 LOC)
5. Operator independently verifies (you do NOT verify your own pair's fix)
```

A "ready to commit" fix on a cross-cutting module (`auto_approve.py`/`core.py`/`web_server.py`/`cinema/context.py`) is **not** evaluable until you confirm the lock was held **before** the code work. If you can't confirm it, stop and check.

## Tier-A co-sign is a HARD gate (the rule baselines break under pressure)

- **Tier-A timing is BEFORE DISPATCH — there is no soft reading.** **Dispatching (or self-implementing) a CRITICAL cross-cutting fix without the co-sign `verification-report` already in the mailbox is itself the violation**, regardless of whether the *commit* later waits for the report. "Before commit" is the wrong timing in all cases — a scope-blind implementer must never start.
- **40 minutes of silence is NOT a green light.** This **overrides the async-OK convenience and binds a director-as-implementer** (spec §6c — you may not self-commit a CRITICAL cross-cutting fix ahead of the co-sign).
- **Escalation is heartbeat-gated, not a flat choice:** (1) check `coordination/presence/director2-heartbeat.ts` (online vs stale) → (2) if online, send a follow-up mailbox ping → (3) only if stale, escalate to the user-principal (Rule #8). Co-sign is **fulfillable async** via a workflow + mailbox report — it is not a hard serialization blocker.
- When you co-sign the *other* lane's brief: verify the **full change-set scope at the source** (not brief-trust); operator-1 later confirms the landed diff matches your co-signed scope (drift = FAIL).

## When you lose a lock

The loser **abandons** — `claim-lock` exit 1 means you never had a valid claim, so there is no in-flight fix to keep. Consult the **inventory header first-mover sequence** for the next row (do not improvise row order — the coordinator pre-sequenced contested modules). Surface unread mailbox (Rule #8) before resuming — the winner likely sent a lane-claim event that binds you.

## Always-owed discipline

- **Rule #7 (pre-commit re-verify):** before EVERY state-asserting commit — `git log --oneline -5` AND read `coordination/mailbox/sent/` for events newer than your Write-start.
- **Rule #8 (mailbox surface):** at session-start AND at every mid-session restart of substantive work.
- **R-BRIEF is where evidence is produced:** Rule #12 = grep the production WRITE site (type-declaration ≠ write-evidence); Rule #13 = audit sibling/symmetric endpoints on the same fence/flag/state.
- **R-PID:** project-scoped endpoints take `<pid>` explicitly — never scan `list_projects()` (IDs collide).
- **Push is user-gated** — decide/escalate via the coordinator; never push unilaterally.
- **Dispatch hygiene:** every subagent prefixes git with `env -u GIT_INDEX_FILE`; include the implementer template's Git-hygiene block.

## Rationalizations — STOP

| Rationalization | Reality |
|---|---|
| "No reply in 40 min, my fix is solid — I'll land it." | Tier-A is a hard gate. Wait + heartbeat-gated escalate. |
| "I'm the implementer, async-OK lets me self-commit." | §6c forbids it for CRITICAL cross-cutting. Co-sign first. |
| "I'll dispatch now; the co-sign can arrive before I *commit*." | Wrong timing. The gate is before DISPATCH — dispatching scope-blind IS the violation. |
| "In this repo it worked out, so the question is moot." | Reason from the rule, not the historical outcome. |
| "Lock-claim sequence is the whole corrected protocol." | §6b is the primitive; the full §6c chain (brief, co-sign, verify) still applies. |
| "I'll commit, the brief can follow." | The R-BRIEF precedes implementation — it is what the co-signer reads. |
| "I verified the fix myself, it's fine." | impl≠verifier — your operator verifies, not you. |

## Red flags (self-check)

- Editing a cross-cutting module without a held lock → §6b.
- About to dispatch/commit a CRITICAL cross-cutting fix with no Tier-A report in the mailbox → §6c.
- "confidence: high" after reading only §6b → you owe §6c, Rule #7, Rule #8, Rule #23.
- Writing graph/pipeline code without loading `comfyui-mastery`/`ai-video-gen` → R-SKILL.
- About to verify your own pair's fix → that's the operator's job.
