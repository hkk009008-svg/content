# Director-seat transplant handoff — 2026-06-03 (≈12:56Z)

*Authoring director session: picked up from `HANDOFF-director-transplant-2026-06-02.md`. This was a
high-throughput verify-and-integrate session — operator shipped four cycles (Part-3 HIGH, Part-3
moderates, the dead-code prune, Part-5 audits); I verified each (Rule #9 Lane V), merged two to main,
cleaned the orphan branch, and shipped ADR-020. State re-verified live at write-time (ADR-013).*

> **TL;DR for the next director:** `main` (`7e807d8`, **pushed, GREEN 1512/3/0**) carries the entire
> Part-3 program through the **moderates/minors** cycle. The live line `feat/max-tier-provisioning`
> (`6d87f22`) is **ahead 10 of origin/feat and UNPUSHED** — it holds the **dead-code prune (327 LOC,
> verified 0-callers)**, **ADR-020**, and 2 docs commits. **#1 pickup item: push `feat` → origin and
> decide the merge-to-main** (user gated both this session; awaiting go). Everything ahead-10 is
> verified clean.

---

## 1. Branch map (verified `git log`/`rev-parse` at 2026-06-03T12:56Z)

| Branch | Tip | Pushed? | What it is | suite |
|---|---|---|---|---|
| **`main`** | `7e807d8` | **YES** (origin==`7e807d8`) | Trunk. Carries max-tier provisioning + **dialogue wire (Veo+overlay)** + Plan-2 char tests + **P0 fix** + **Part-3 F1/F2/F3** + **all Part-3 moderates/minors**. | **1512 / 3 / 0** |
| **`feat/max-tier-provisioning`** *(HEAD)* | `6d87f22` | **NO — ahead 10** | Live line on `main`. The +10: 7 `chore(prune)`/doc-sync (`b4a03c8`..`51f1826`, 327 LOC) + **ADR-020** (`f499c81`) + 2 docs (`fb8d628` manual digests sync, `6d87f22` Part-3 no-op audit tickets). origin/feat==`7e807d8`. | **1512 / 3 / 0** (smoke OK, anchors clean) |

Both seats idle at write (operator wrapped ~3h ago; director wrapping now). The orphan
`max-tier-provisioning-2026-06-01` branch + `.claude/worktrees/f1-max-tier` were **cleaned this
session** (local + remote deleted; reflog `50b4f63`/`e5a880e` ~90d). Other `.claude/worktrees/claude-*`
are harness worktrees — leave.

---

## 2. What this session shipped (the four operator cycles + my integration)

1. **Dialogue wire + Plan-2 verification.** Verified operator's Veo+overlay dialogue wire + 157 Plan-2
   char-tests (3 cold reviewers, Rule #9). Found a **surprise CRITICAL the green suite missed: P0
   `_voice_mode` UnboundLocalError crashing *every non-AUTO shot*** (`controller.py` — bound inside the
   `if raw_api=="AUTO"` block, used unconditionally below; non-AUTO is the normal prod case). Directed
   it (mailbox `32f2d47`); user adjudicated **operator-owns-as-slice-0**.
2. **Part-3 F1/F2/F3** (`38064f9..20673a6`). Operator shipped (design-first, subagent-driven) the
   honest skip-vs-fail identity gate (`overall_score: Optional[float]` + `skipped`); P0 fixed
   (`f5fd4e7`). My **Lane V = ✅ SHIP-CLEAN** (`25d9634`). **Merged `feat`→`main` (`26d9b1e`).**
3. **Part-3 moderates/minors** (`38064f9`-era … `d15c56b`). sora resolution / ltx fallback ordering /
   style web-research gating / `threshold=0.0` / `VIDEO_ZERO_FRAMES` / vision face-swap. My **Lane V =
   ✅ SHIP-CLEAN** (`7e807d8`); **pushed + merged to main (`7e807d8`)**.
4. **Dead-code prune (327 LOC)** + Part-5 audits — UNPUSHED on feat. Operator pruned the §4a
   confirmed-dead set; I re-verified **0 production callers** for each, suite **unchanged 1512/3/0**,
   keep-set intact, and shipped operator's drafted **ADR-020** (`f499c81`). Operator then added the
   no-op audit tickets + a manual sync (docs).

**Discipline that paid off:** operator kept committing **live** while I verified, so I pushed/merged the
**exact verified SHA** each time (a guard refused to push anything unchecked). Nothing unverified reached
trunk. Reuse this.

---

## 3. Open items (owner)

1. **Push `feat`→origin + merge-to-main** *(user/director — #1)* — the ahead-10 (prune + ADR-020 + 2
   docs) is **verified clean** (0-callers re-grep, 1512/3/0, smoke OK) but **local-only**. User gated
   push+merge this session; awaiting go. *FF to main is clean* (`main` is ancestor of `6d87f22`).
2. **Part 4 (UI)** of the test/audit program — not started (`docs/superpowers/specs/2026-06-02-program-test-audit-plan-design.md`).
3. **Part-3 no-op audit: 8 open tickets** (`6d87f22`, `docs/.../2026-06-03-part3-noop-audit-tickets.md`) — triage/close.
4. **Live wired-E2E**: dialogue route (~$0.50–1, spend-gated) + max-tier pod validation. **Pod `07ed667`
   is 404/stopped** — verify in Novita before any spend.
5. **`validate_lora_quality`** — still a wired stub (capability-positive; LoRA is the top identity lever). Backlog.
6. **`feat` branch disposition** — `== main` after each merge; keep as working line or retire.

---

## 4. Insight to carry forward

- **The dead-vs-dormant prune boundary** (ADR-020): prune superseded/ops dead code; **KEEP** dormant
  QUALITY levers (`negative_prompts.py`, `evaluate_generation_quality`, `validate_lora_quality`, ltx
  transitions) and **preserved primitives** — operator correctly reclassified `cinema/pipeline.py::CinemaPipeline`
  from prune-candidate to KEEP (it's a documented §4.8 primitive + a §15.9 zero-callers GUARD invariant,
  not dead code). Pruning a `§15` truth-doc invariant is a trap; the cold-audit caught it.
- **Re-verify-before-destructive** (standing rule) earned its keep again: I re-grepped 0-callers for all
  7 pruned symbols at HEAD before shipping the ADR / recommending merge.
- **Two-seat loop worked cleanly:** operator design-first ships → director independent Lane V (Rule #9)
  → merge. The independent pass has real value — operator's own review missed `chief_director:510`
  (caught in their 2-stage review); my Lane V independently re-confirmed all None-readers across the
  nullable-score change.

---

## 5. Coordination state
- **D-a INACTIVE** this session (`CLAUDE_SEAT`/`GIT_INDEX_FILE` unset → shared index → **`git commit -- <pathspec>`**
  + **exact-SHA pushes** throughout). USER must relaunch with `CLAUDE_SEAT`+`GIT_INDEX_FILE` to activate D-a.
- Presence files **dormant** (hook doesn't bump without `CLAUDE_SEAT`); both seats read **git as truth**
  (Rule #8). Mailbox: newest to-director `2026-06-03T09-11-52Z` (prune coordination — processed; ADR-020 shipped).
  My Lane V verdicts are committed mailbox events (`25d9634`, `7e807d8`).
- Director cursor effectively current (all to-director events through the prune coordination processed).

## 6. How to pick up (session-start)
1. `.venv/bin/python scripts/ci_smoke.py` (§15) + `git log --oneline -12 main feat/max-tier-provisioning`
   to confirm this map. 2. Read `docs/PROGRAM-MANUAL.md` (intent) early. 3. Decide the **#1 open item**:
   push `feat`→origin + merge-to-main (verified clean). 4. Check `coordination/presence/*.md` + recompute
   unread per Rule #20. 5. The next operator handoff (operator-seat) covers the Part-5 audit detail.

*Signed: director-seat, 2026-06-03 ≈12:56Z. State verified live (refs, suite 1512/3/0, smoke OK,
0-caller re-grep). The ahead-10 on feat is clean — the only question is push/merge timing.*
