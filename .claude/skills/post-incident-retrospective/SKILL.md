---
name: post-incident-retrospective
description: Write the retrospective AFTER an incident or campaign resolves and BEFORE the session ends — timeline from artifacts not memory, defect ledger with mechanisms, name the control that should have caught each defect and whether it was vacuous, route each lesson to a skill or memory file, and file protocol-gap flags in docs/INCIDENT-LOG.md. Use after resolving an incident, closing a campaign, or any session that fixed three or more defects. For probing a single claim use probe-a-claim; for handoffs mid-campaign use cross-machine-handoff.
disable-model-invocation: true
---

# Post-incident retrospective

A lesson that lives only in the session transcript is a lesson the next
session pays for again. The retrospective is written from ARTIFACTS — git log,
command outputs, evidence files — never from memory of the campaign, and it is
written the same session, before context is lost. Do not draft new protocol
rules unilaterally; flag gaps and route them.

Do this first (EXECUTING HOST: Mac) — reconstruct the skeleton from the
record, not the head:

```bash
cd /Users/hyungkoookkim/Content && env -u GIT_INDEX_FILE git log --oneline --since=<campaign-start> && \
  ls -t logs/ | head -10
```

## Required structure (model: docs/RETRO-2026-08-07-identity-lab.md)

1. **Campaign in one paragraph** — goal, headline result with numbers, cost
   (defects, pushes, digest moves).
2. **Defect ledger, chronological** — for each: the mechanism (not just the
   symptom), how it was FOUND (run, read, guard, measurement), the fix shape
   (subtractive fixes are worth naming as such), and what it cost.
3. **Known-open** — everything deliberately deferred, with the reason, so the
   next session doesn't re-diagnose a known item.
4. **Patterns** — only patterns witnessed at least twice; each names its
   instances. For every defect, name the control that SHOULD have caught it
   and answer honestly: was that control vacuous?
5. **What worked** — disciplines that paid off, so they survive as practice.
6. **Routing footer** — a table: every lesson → the skill, memory file, or
   doc it now lives in. A lesson with no row is a lesson you are choosing to
   lose.

## The two-control doctrine (apply to every guard mentioned)

A **reversion** control (restore the defect, watch the guard fire) proves the
guard is non-vacuous — nothing more. An **evasion** control (guard intact,
reach the bad outcome another way) is what proves sufficiency; reversion
structurally cannot catch the evasion class. State which of the two each guard
has, and never present a reversion-only guard as sufficient.

## Routing rules

| Lesson kind | Route |
| --- | --- |
| Content-specific procedure or trap | `.claude/skills/` here, same session |
| Portable discipline (would help any repo) | `~/.claude/skills/` global |
| Campaign state, cross-session facts | project memory directory |
| Protocol/process gap | flag in `docs/INCIDENT-LOG.md`; do NOT write the rule yourself |
| Pipeline-repo doctrine change | learning-candidate route only — never edit Pipeline canon directly |

## Red flags (self-check)

- A "pattern" with one instance.
- A defect ledger entry that names no mechanism — you recorded the symptom.
- A guard praised without saying which control class proved it.
- Any load-bearing number quoted without its producing command.
- The session is ending and this file does not exist yet.
