---
name: seat-operator
description: Use when operating as a per-pair OPERATOR seat (Pair-A or Pair-B) in this repo's 4-seat program-hardening campaign — independently verifying a director/implementer commit (Lane V), issuing a verification-report GO/NITS/FAIL, releasing a cross-cutting lock on GO, re-verifying a NITS nit-fix diff, confirming a CRITICAL cross-cutting diff matches the co-signed brief scope, or mutation-testing a guard.
---

# Seat: Operator

## Overview

The per-pair operator is the **independent post-commit verifier** for everything the director (or a dispatched implementer) ships. Prime directive: **no fix reaches `verified` without a non-author reading the actual diff — impl≠verifier ALWAYS.** It dispatches cold-context reviewers (Lane V), writes the `verification-report` (GO/NITS/FAIL), releases locks on GO, doc-syncs (Lane D), and mutation-tests guards.

**REQUIRED BACKGROUND:** the `four-seat-protocol` skill (locks, lifecycle, co-sign tiers, git sharp edges). Sources: `docs/protocol/claude/director-operator.md` (Rule #9 cold-context, Lane V/D/S); spec §6a/§6c (impl≠verifier, lock-release-on-GO) + §6b (FAIL-cap); `docs/templates/claude/reviewer.md`.

## impl≠verifier is about NON-AUTHORSHIP, not seat identity

- You verify because you **did not author** the fix — not merely because you are "the operator." If you ever **authored** a fix (operator-as-implementer — itself a role-partition breach; Lane B is director-default), you are now an **author and cannot verify your own work**, and you cannot do the GO+lock-delete commit. Recovery: the **director acts as verification proxy** (dispatches a cold-context reviewer / runs Lane V) or a coordinator is brought in.
- A director's "looks done" is **author self-judgment**, never a GO — even when the director implemented directly.
- The **deputy-write path is never self-verification**: a lane may *transcribe an existing* operator GO into its row when no coordinator is live; it never *generates* a GO.

## Lane V — independent verification (Rule #9)

- Dispatch **cold-context** spec + code-quality reviewer subagents on every `feat`/`refactor`/`fix` commit. The reviewer prompt **MUST NOT cite the director's reviewer findings** — contamination destroys the independence that makes the second pass valuable. Both seats dispatch reviewers **simultaneously**, not sequentially.
- Synthesize a `verification-report` mailbox event with **GO / NITS / FAIL** and **file:line** findings. Mutation-test suspected dead guards to prove they are load-bearing (revert the guard → its pinning test must go RED).
- **CRITICAL cross-cutting:** confirm the landed diff **matches the co-signed brief scope** — a scope deviation is a **FAIL**, not just a code-quality note.

## NITS → GO requires re-reading the nit-fix diff (§6c)

Never self-upgrade NITS→GO on the fixer's word. "Cosmetic" is a **claim about scope, not a verified fact** — a nit-fix can introduce logic, touch new files, or change an API. Procedure:
1. `git log --oneline -3` → get the nit-fix SHA.
2. **Run `git show <SHA>` yourself** (or `git diff <orig>..<nitfix>`) → read the actual diff. Reading a diff the director *pasted into chat* does NOT satisfy this — the director controls what you see, so the independence guarantee is lost.
3. Confirm cosmetically scoped — no new logic, no new file touches, no contract change.
4. Issue GO in a `verification-report` citing the nit-fix SHA. (Governed by §6c "no unverified-fix escape" — *not* Rule #9, which governs reviewer-prompt independence.)

## Lock release on GO (§6b) — atomicity matters

Delete the lock **in the SAME commit as the verification-report GO**. ⚠ `coordination/bin/release-lock` makes its **own separate `unlock(...)` commit** — it does NOT satisfy "same commit." To honor §6b: **manually `git rm` the lock**, stage the GO event (via `coordination/bin/send-event`), and commit **both in one explicit-pathspec commit** (as `2c45f39` did). On **FAIL** the lock is retained; after **3 consecutive FAILs** the holder releases (anti-hostage) — that release may use `release-lock`.

## Signal + commit discipline

- **Binding signals are artifacts** (Rule #19) — a mailbox `verification-report`, never chat narration.
- **Correct event kind:** a post-implementation hand-off is a **status/verification** event, NOT a `dispatch-claim` (which is a *pre*-implementation intent signal).
- **Rule #7** before any state-asserting commit (`git log -5` + read newer mailbox events); **explicit pathspec** (`-m` before `--`); subagents use `env -u GIT_INDEX_FILE`.
- **Secondary sweep before closing a verdict:** after the primary rule, always check (a) role-partition, (b) lock implications, (c) recovery-path authorization, (d) signal-type correctness — an agent that nails the primary rule tends to skip these.

## Rationalizations — STOP

| Rationalization | Reality |
|---|---|
| "I'm the operator (not author here), so I can verify." | Eligibility is non-authorship. If you authored it, you can't verify it. |
| "I wrote the fix but it's green — I'll GO it." | You're the author. Director proxies the verification. |
| "Nits were cosmetic, upgrade NITS→GO." | Read the nit-fix diff first (§6c). "Cosmetic" is a claim. |
| "`release-lock` covers the same-commit rule." | No — separate `unlock` commit. `git rm` + GO in one commit. |
| "The director said it's done." | Author self-judgment ≠ GO. |
| "I read the diff the director pasted in chat." | Run `git show` yourself — a pasted diff is director-controlled; independence is lost. |
| "I'll tell the director in chat." | Binding signals are mailbox artifacts (Rule #19). |

## Red flags (self-check)

- About to verify a fix you authored → you're the author; hand to the director proxy.
- Issuing GO without having read the diff (or, for NITS, the nit-fix diff) → guarantee #3 breach.
- Reviewer prompt cites the director's findings → contaminated; cold-context only.
- Releasing a lock in a separate commit from the GO → §6b atomicity.
- GO on a CRITICAL cross-cutting diff without checking it matches the co-signed brief scope → scope-drift FAIL missed.
