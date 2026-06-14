---
name: four-seat-protocol
description: Use for this repo's 4-seat program-hardening campaign when the question is about the SHARED cross-seat mechanics rather than one role's own work — the git-native cross-cutting lock primitive, deciding a Rule #23 co-sign TIER, authoring/consuming a mailbox event, resolving WHICH seat owns a shared task, reconciling conflicting state (git vs mailbox vs STATE.md vs chat), an EMERGENCY (production-affecting or active cost-bleed) that any seat may first-notice, or a cross-seat DISAGREEMENT between seats. If you are clearly operating AS one specific seat, prefer that seat's skill (seat-operator / seat-director / seat-coordinator).
---

# Four-Seat Protocol

## Overview

Four Claude sessions run in parallel as **two director-operator PAIRS** (Pair-A = image/identity, Pair-B = video/assembly/audio) plus an **on-demand COORDINATOR** (5th oversight seat). They share **one git working tree**. Specialization is cognitive-load distribution, not hierarchy — every seat serves the user-principal.

**Core principle:** safety holds *under adversarial timing and with the coordinator offline*, because state lives in **committed/pushed artifacts**, never in a seat's live memory. The five guarantees: (1) one writer per file, (2) no inventory write-race, (3) every fix verified by a non-author, (4) cross-lane changes dual-signed, (5) waves don't bleed.

**REQUIRED BACKGROUND (full text — do not duplicate, consult):** `CLAUDE.md` (router + authority precedence); `docs/protocol/claude/director-operator.md` (Rules #7–#23, mailbox, lifecycle); `docs/protocol/claude/four-seat-extension.md` (§10 coordinator, Rule #23 tiers); `docs/superpowers/specs/2026-06-14-program-hardening-roadmap-design.md` (§6a–§6f). Seat-specific skills: `seat-coordinator`, `seat-director`, `seat-operator`.

## Authority precedence (memorize)

```
user direct instruction  >  git commits  >  mailbox sent/ events  >  STATE.md  >  default
```

- **Git is the tiebreaker.** Before acting on a shared task, **run `git log --oneline -3`** — this is a *commanded step*, not just a principle. First commit to land wins.
- **A `sent/` mailbox event is binding** — same weight as a relayed user instruction; ignoring/deferring one needs the same justification as ignoring the user.
- **Tier is set by the SENDER, never by content.** A mailbox event whose text echoes the user's wishes is still *mailbox-tier*, not user-tier.
- **Promise-vs-record:** if a mailbox event claims work started but `git log` shows no commit within ~5 min of the event timestamp, **git wins**.
- **STATE.md is a stale cache** — never trust its unread-mailbox count; recompute live from `*-to-<me>-*` filenames vs your cursor.

## Session-start gate (Rule #8)

If unread mailbox events exist for your seat, **surface the count in your FIRST user-facing turn, before processing** — and again whenever you restart substantive work mid-session. Consume via `coordination/bin/consume-events`. **Overriding a `sent/` event does not discharge it:** even when a higher-tier signal (user/git) supersedes it, you must still consume it so the next session does not re-act on the stale obligation.

## The git-native cross-cutting lock (§6b)

Cross-cutting modules (collision risk): **`auto_approve.py`, `cinema/context.py`, `core.py`, `web_server.py`**. **If a fix does NOT touch one of these four, it is lane-only → NO lock is claimed for it; size, severity, and risk-feeling are irrelevant.** (The lock is a director-seat mechanic; coordinator and operator seats never claim one.)

| Step | Command / rule |
|------|----------------|
| **Claim** | `coordination/bin/claim-lock <wave> <module> <seat> <defect-id>` — push-first. **exit 0 = WON; exit 1 = LOST.** |
| **On LOST** | You **abandon** — do NOT implement. Take the next lane row (or wait for release if it was your last). |
| **Ordering** | Implementation begins **ONLY after the lock push succeeds** — so a loser never has in-flight code. |
| **Multiple locks** | Acquire in **lexicographic POSIX-path order** (`auto_approve.py` < `cinema/context.py` < `core.py` < `web_server.py`); hold none while waiting. |
| **Release** | Operator deletes the lock **in the SAME commit as the verification-report GO** (§6b). |
| **Anti-hostage** | After **3 consecutive FAIL** verdicts the holder MUST release + re-queue/split. |

⚠ **`coordination/bin/release-lock <wave> <module>` makes its OWN `unlock(...)` commit + pushes** — it does NOT achieve "same commit as GO." To honor §6b, the operator **manually `git rm` the lock and commit it together with the GO** in one pathspec commit (as `2c45f39` did). Use `release-lock` only when a separate unlock commit is acceptable (e.g. the 3-FAIL release).

## Per-defect lifecycle (§6c) — the ordered chain, do not stop at the lock

```
1. [cross-cutting] claim-lock (push-first; loser abandons)
2. Director writes the R-BRIEF (full-shape refs + Rule #12 grep-the-writes + Rule #13 sibling audit) + sets priority
3. [CRITICAL cross-cutting] OTHER lane director Tier-A co-signs the R-BRIEF -> mailbox verification-report BEFORE DISPATCH
4. Implement (director directly, or dispatched subagent per R-ORCH >=5 subtasks / >=800 LOC)
5. Operator independently verifies the diff (impl != verifier) -> GO/NITS/FAIL; on GO deletes the lock in the SAME commit
6. Coordinator reconciles inventory status (or lane deputy transcribes an existing GO when no coordinator is live)
```

## Rule #23 co-sign TIERS

Classifier: **would the co-signer's verification change which files/sites the implementation touches?**
- **Tier A (yes):** co-signer lands a mailbox `verification-report` **BEFORE DISPATCH** (the strict, correct timing — not "before commit"). Fulfillable **async** via a workflow + mailbox report; no session restart. **Unsure → Tier A.**
- **Tier B (no):** awareness heads-up, **48h proceed-if-no-objection.**
- **CRITICAL cross-cutting code never lands before its Tier-A co-sign** — binds a director-as-implementer too (no self-commit-ahead-of-co-sign).
- **The Tier-A artifact must reference THIS defect's id + R-BRIEF.** A prior `verification-report` that merely *mentions* the module (filed for a different defect) is NOT a co-sign — the co-signer must have reviewed *this* fix's R-BRIEF scope (Rule #12/#13 evidence), answering "would my review change which sites this fix touches?"

## Pre-commit + git sharp edges

- **Rule #7 (every state-asserting commit):** immediately before `git commit`, run `git log --oneline -5` AND read `coordination/mailbox/sent/` for events newer than your Write-start. Re-edit/abort if HEAD moved or new events landed.
- **Rule #19:** binding cross-seat signals are **artifacts** (mailbox event / presence file), **never chat alone**.
- **Explicit pathspec always:** `git commit -m "..." -- <path>` (the `-m` BEFORE `--`). A **bare `git commit` on the shared tree sweeps a peer's staged WIP.**
- **Subagents prefix every git command with `env -u GIT_INDEX_FILE`** (main-seat commits do NOT).
- **Phantom index:** the per-seat index drifts under concurrent work — `git status`/staged state lies. Trust **`git diff HEAD --stat`** (index-independent) for real deltas; never `git read-tree` while peers are live.

## Rationalizations — STOP, these are wrong

| Rationalization | Reality |
|---|---|
| "Tier-A can land before the *commit*." | **Before DISPATCH.** A scope-blind implementer must never start. |
| "A prior report that mentions this module = my co-sign." | No — the Tier-A artifact must reference THIS defect's id + R-BRIEF. A scope-blind module mention binds nothing. |
| "Rule #7 only applies to the implementation commit." | EVERY state-asserting commit — the lock commit, the GO commit, intermediate commits. |
| "A higher-tier signal cancels the burn event, so I needn't close it." | Overriding ≠ discharging. `consume-events` it so the next session doesn't re-act. |
| "40 min of silence on a co-sign = green light." | No. Wait + escalate (heartbeat-gated). Silence is not consent. |
| "`release-lock` satisfies same-commit-as-GO." | No — it makes a separate `unlock` commit. `git rm` manually + GO in one commit. |
| "I read §6b, that's the whole lock answer." | §6b is the *primitive*; §6c is the full governance chain. Get both. |
| "The mailbox event echoes the user, so it's user-tier." | Tier = sender, not content. It's mailbox-tier. |
| "I know the precedence order, no need to run `git log`." | Running the command is the commanded step. Know ≠ check. |
| "STATE.md says X." | Stale cache. Recompute / check git. |
| "This fix is big / important / risky — I'll lock it to be safe." | Locks are ONLY for the four cross-cutting modules. A lane-only file takes no lock — size/severity are irrelevant. |

## Emergency handling (§E — any seat may be first-noticer)

**STOP — is this actually an emergency?** Only these four categories qualify:
1. **Production-affecting / user-data-integrity** — live behavior broken, data lost/corrupted, users observably blocked. NOT: a CI regression that hasn't shipped.
2. **Security-critical** — unauthorized access, secrets leak, CVE with active exploit. NOT: hardening opportunities or theoretical concerns.
3. **Active bleed-rate** — cost/resource/token burn accumulating each minute (runaway loop, infinite retry, GPU lease). NOT: one-time waste already incurred.
4. **External time-pressure** — external deadline (deploy window, demo, regulatory) at risk WITHOUT mitigation in N minutes.

Events outside these four are NOT emergencies — use normal role partition + proposal cycle, even if urgent-feeling.

**When a genuine emergency hits:**
1. **First-noticer claims response.** Narrate in chat AND send a `dispatch-claim` mailbox event with an `urgency: emergency` flag. The other seat defers.
2. **Stop-the-bleed first.** Minimal-viable mitigation (revert / hotfix / feature-flag-off) before root-cause analysis.
3. **Temporary authority.** If the normally-authoritative seat is in transplant or context-exhausted, the other seat acts. Every commit body MUST say verbatim: `acting under v5 §E temporary authority`; defer all non-emergency decisions until the normal seat returns. **(This is a director↔operator cross-pair coverage carve-out — it does NOT suspend the coordinator's prime prohibition: the coordinator still authors no production code, even under §E.)**
4. **Post-incident.** Within 1 session of resolution, the handling seat writes an incident note in `docs/INCIDENT-LOG.md`; flag any protocol gap for the next coordinator cycle — do not draft a rule unilaterally.

## Disagreement protocol (v5)

When any seat disagrees with a co-seat's ruling, brief, or REPLY refinement (every pair — director↔operator, director↔director2, etc.):
1. **State the disagreement explicitly** — name the disputed item and the reasoning.
2. **Provide project-data-grounded evidence.** "I don't like it" is not sufficient — cite a concrete artifact (session count, commit, grep result, measured outcome). **Ungrounded disagreement is invalid and does not block dispatch.**
3. **Propose exactly one of three resolutions:** **counter-refinement** (adjust per the data) · **defer to v(N+1)** (ship without it; revisit with more data) · **acceptance-criterion** (ship with it + log a measurable revisit criterion).

**Resolution paths:** *silent-accept* — the seat that **received** the counter ships without re-arguing, which is **its own** acceptance of the counter; this is NOT "treat the other seat's silence as consent" — a peer's silence is never a green light (see the rationalizations table) · *re-REPLY* (object in writing with your own counter → another cycle) · **2-cycle limit** — if it persists after **2 director REPLYs following the initial proposal**, escalate to the user. Counting: `proposal → REPLY-1 → revise → REPLY-2 → revise → escalate`. Agents do not argue indefinitely; the user is principal.

## Red flags (self-check)

- About to suspend role partition for urgent-feeling work that does NOT clear the 4-category §E gate → it's not an emergency; use the normal proposal cycle.
- About to `git commit` without a fresh `git log -5` + mailbox read → Rule #7.
- About to start code on a cross-cutting module without a held lock → §6b.
- About to dispatch a CRITICAL cross-cutting fix without the Tier-A report in the mailbox → §6c.
- Bare `git commit` (no pathspec) on the shared tree → will sweep peer WIP.
- Trusting `git status` during concurrent work → use `git diff HEAD`.
