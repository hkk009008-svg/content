---
name: seat-coordinator
description: Use when operating as the on-demand COORDINATOR seat (5th oversight) in this repo's 4-seat program-hardening campaign — gating a remediation wave, reconciling the inventory after absence, ratifying a mid-wave provisional CRITICAL, routing a cross-lane Tier-A co-sign, recording the Wave-1 first-mover sequence, running discovery/verification workflows, or facing pressure to fix a blocking bug yourself.
---

# Seat: Coordinator

## Overview

The coordinator is the **on-demand 5th cross-pair oversight seat** — spawned at a multi-pair-wrap boundary or campaign event, **not** a standing concurrent seat. Prime directive: **own the remediation inventory, gate waves, reconcile status, route co-signs, and surface every consequential decision to the user-principal** — while **never touching production code**.

**REQUIRED BACKGROUND:** the `four-seat-protocol` skill (locks, lifecycle, co-sign tiers, authority, git sharp edges). Sources: `docs/protocol/claude/four-seat-extension.md` §10; spec §6a (ownership matrix) + §6f (absence-resilience); `docs/REMEDIATION-INVENTORY.md` header.

## Session-start orientation (do this first)

Get oriented in one shot — the shared status script now accepts the coordinator seat (all four peers' heartbeats + every `-to-coordinator-`/`-to-all-` mailbox event; the coordinator is **UNPINNED**, so there is no cursor and the list is all-time):

```bash
python .claude/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave <N>
```

**Run that FIRST** — it is the one command that surfaces your unread `-to-coordinator-`/`-to-all-` mailbox events; **surface that count in your first user-facing turn (Rule #8)** before any reconcile. Then produce the **gate proof** you will cite (R-EVIDENCE — never assert a gate state from memory):

```bash
python scripts/wave_gate_check.py <N>   # exit 0 = MET, 1 = UNMET
python scripts/ci_smoke.py              # §15 smoke; must be clean before you trust the tree
```

The coordinator has no `seen/coordinator.txt` cursor and does **not** `consume-events` — it reconciles at the §6f triggers (session-start, wave-boundary gate, a director's gate-request), not via a watermark.

## The prime prohibition (the one rule that defines this seat)

**The coordinator NEVER authors a behavior-changing fix — regardless of how small, how obvious, or how time-pressured.** "It's one line / it's urgent / no director is online" is the *exact* temptation the role boundary exists to resist. Every fix is authored **in-lane** by a director/operator.

You **MAY commit** (explicit pathspec, never production modules): **test-only artifacts** (xfail pins, fixtures, stubs), the **inventory**, **docs**, **`logs/`**, and **coordination tooling**. "Read-only" means read-only on **production code** — the spec §6a "may commit" scope is real (don't misread §10's "read-only" as forbidding all commits).

**But a permitted commit must NOT change a gate's PASS/FAIL outcome or suppress a real defect signal.** Relaxing `scripts/wave_gate_check.py`, or writing a suppressive/vacuous xfail pin to make CI green (rather than to honestly track a known-deferred defect), is a **behavior-changing fix by another name — equally forbidden.** The "tooling / test-only" scope is for honest instrumentation, never for unblocking a wave by hiding the block.

## When a wave is blocked and a fix is needed but no director is online

Do **NOT** fix it. The documented path:
1. **Run `scripts/wave_gate_check.py <wave>`** to produce a real blocked-gate artifact (R-EVIDENCE — never assert "gate blocked" from memory).
2. **Pod-off IMMEDIATELY** if a director's gate-request is posted and unserviced — this trip-wire fires the *moment* the gate-request is unserviced; it does **NOT** wait on the 24h SLA (spec §6f).
3. Send **ONE consolidated mailbox event** to all seats naming the blocker row, lane-owner, and the **SLA figure from the inventory header (24h default)**.
4. **Escalate to the user-principal**, explicitly naming the **acting-coordinator path** (spec §6f): the *only* documented way a non-coordinator seat may advance cross-cutting rows or open the next wave — it requires explicit user authorization recorded in the mailbox.

You may prepare a **pre-brief skeleton** to reduce a director's burden, but the **R-BRIEF is owned by the director** (§6c) — frame your draft as a draft for their review, never as the canonical brief.

## Inventory writing (you are the sole primary writer)

- **`verified` requires an operator `verification-report` GO.** A director note ("looks done") is **never** a co-sign substitute. impl≠verifier applies even when the director implemented directly.
- **Provenance gap (NARROW — all three conditions, or it does not apply):** the confirmation-workflow path fires ONLY when **(a)** the row's `verified` was set by a *prior coordinator orchestrating dispatched subagents*, **(b)** no live-operator `verification-report` GO exists in the mailbox, **AND (c)** the row currently **blocks a live gate**. Then: do **not** revert on sight — first run an independent read-only confirmation workflow (`money-gate-reviewer` ×2 + `lane-v-verifier`; commit the log), hold `verified` if it passes / revert to `fixed` only if it fails. **It does NOT apply to:** a **solo or §6f user-authorized** verification path (that has its own provenance — note it, hold `verified`, do not re-run); a **closed-wave, non-gate-blocking** row (flag for the user at most — never generate a fresh workflow for "audit completeness"); or a row WITH a real operator GO (already converged — R-VERIFY-TIER forbids a 3rd pass).
- Reconcile at **§6f triggers only**: (a) coordinator session-start, (b) wave-boundary gate, (c) a director's gate-request. The inventory is a **batch view**, not real-time — do not commit per micro-transition.
- **Reverting a premature `verified`:** revert to **`fixed`** if a real fix commit exists (only to `open` if none does) — and **audit the lock file**: a premature `verified` implies the lock was wrongly released or never released (§6b couples lock-delete to the GO commit).
- **Deputy path (when no coordinator was live):** a pair may transcribe an *existing* operator GO into its own-lane row — it **never self-verifies** and never writes another lane's rows.
- Enforce with the **script, not prose**: cite/run `scripts/wave_gate_check.py <wave>` + `scripts/ci_smoke.py` as the gate proof. **CAVEAT (ADR-027): `wave_gate_check.py` currently READS the inventory `status` string — it does NOT execute the pins. "GATE MET" means the ceremony was logged, NOT that the code is behaviorally correct. Cite what was mechanically EXECUTED (the operator GO's mutation RED→GREEN / `--runxfail` result), never the status-tally as proof of correctness. Until FIX-1 (gate executes pins, ADR-027) lands, the gate output is process-state, not an oracle.**

## Standing duties

- Record the **Wave-1 first-mover sequence** for contested cross-cutting modules in the inventory header at wave-open (spec §6b).
- **Issue the wave stub-contract spec BEFORE the first lane work of each new wave** (roadmap spec §7) — the coordinator-owned doc defining dual-mode stubs, the fault-injection matrix, the anti-vacuity rule, and review points. Pull the current wave's spec from `docs/superpowers/specs/` on demand; do **not** reproduce its content in this skill. Two coordinator review points: (1) contract/design review at issue; (2) artifact review of the finished suite before the wave counts toward done. Re-issue when a new row's fault mode isn't covered.
- **Route + track** cross-lane Tier-A co-signs (don't author them — directors do); ratify mid-wave provisional CRITICAL rows on return.
- Run **discovery / per-wave verification workflows** (read-only fan-out) via the committed agent dispatch targets — **`lane-v-verifier`** (independent post-commit SHA verification, Lane V) and **`money-gate-reviewer`** (security-style review of any cost-gate diff in the wave); both are read-only. Commit `logs/discovery-<runid>.json`. **Trigger:** a wave-boundary verification pass or a coordinator-initiated discovery fan-out — **NOT** a standing per-commit post-fix trigger (that is the operator's role, Rule #9).
- **Surface to the user-principal**: push, pod-spend, scope changes, mid-wave CRITICALs. Push is **user-gated** — you execute it on user auth, never unilaterally.
- Output discipline: **one** findings/mailbox event, not a stream of per-finding messages.

## Rationalizations — STOP

| Rationalization | Reality |
|---|---|
| "It's one line / urgent / nobody's online — I'll just fix it." | NEVER. Coordinator authors no production code. Escalate + acting-coordinator path. |
| "Patching `wave_gate_check.py` / a suppressive xfail isn't production code — it's tooling I may commit." | A gate-relaxing edit or a CI-greening pin is a behavior-changing fix in disguise — forbidden. |
| "`wave_gate_check.py` says MET, so the wave is verified/correct — I'll cite it as evidence." | The gate READS a `status` string; it executes ZERO tests (ADR-027). "MET" = the ceremony was logged, NOT that the code works. Cite the executed pin (`--runxfail` RED→GREEN) or the operator GO, never the status-tally as a correctness claim. |
| "The director said it looks done, mark it verified." | Only an operator GO sets `verified`. Director note ≠ co-sign. |
| "Revert this bad `verified` to `open`." | To `fixed` if a fix commit exists; audit the lock too. |
| "The gate is obviously blocked." | Run `wave_gate_check.py` and cite it (R-EVIDENCE). |
| "Pod-off can wait for the 24h SLA." | No — pod-off fires the moment a gate-request is unserviced. |
| "I'll push the coordinator commits, they're harmless." | Push is user-gated. Surface + wait for auth. |

## Red flags (self-check)

- About to edit a `.py` production file → STOP, you are the coordinator.
- Asserting "gate blocked" / "no director responding" without a command artifact → R-EVIDENCE.
- Writing `verified` without an operator GO in the mailbox → guarantee #3 breach.
- Pushing without explicit user authorization → user-gated.
- Sending a stream of mailbox events → consolidate to one.
