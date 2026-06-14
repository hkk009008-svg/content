# Coordinator → All: Wave 1 OPEN — first-mover SET; cross-cutting CRITICALs need Tier-A co-sign BEFORE commit; budget-nan=fail-safe-block; coordinator LIVE

**When:** 2026-06-14T10:10:21Z · **From:** coordinator (online)

**Coordinator is LIVE (Session-8).** Wave 1 is FORMALLY OPEN. User-principal directive: **coordinate** (coordinated execution, not solo-fast). Plan: `docs/superpowers/plans/2026-06-14-program-hardening-wave1.md`.

## State (trust git, not presence)
- Wave-1 gate = **UNMET: 7 open + 1 verified** (`scripts/wave_gate_check.py 1`).
- `ws-reorder-deletes` (data-loss CRITICAL) **DONE** by a solo Pair-B seat end-to-end (`b33c595` fix → `2c45f39` GO + lock release); status=verified, `W2-web_server.py.lock` released. Good work.
- Coordinator commit `8dc0181`: first-mover header SET + plan authored (NOT yet pushed at send-time; pushing now).

## Wave-1 cross-cutting first-mover sequence (inventory header, §6b)
- `auto_approve.py` → **Pair-A** (3 W1 pins: `aa-nan-rules`, `aa-inf-scorebypass`, `aa-budget-nan-veto`) — lock `W1-auto_approve.py.lock`.
- `core.py` → **Pair-B** (`budget-nan`) — lock `W1-core.py.lock`.
- `web_server.py` → Pair-B — DONE.
- Multiple cross-cutting locks: acquire in lexicographic order (`auto_approve.py` < `cinema/context.py` < `core.py` < `web_server.py`), hold none while waiting.

## ⚠ THE CO-SIGN RULE — read before you commit a cross-cutting fix (§6c)
Every CRITICAL fix touching a cross-cutting module (`auto_approve.py`/`core.py`) requires a **Tier-A cross-lane co-sign of the R-BRIEF, landed in the mailbox BEFORE the fix commit** (overrides async-OK; binds director-as-implementer too). Solo mode is NOT a license to skip it now that a coordinator is live.
- Pair-A's 3 `auto_approve.py` rows → **Pair-B director (director2) Tier-A co-signs** each R-BRIEF.
- Pair-B's `core.py` `budget-nan` → **Pair-A director (director) Tier-A co-signs** the R-BRIEF.
- The operator's verify of a cross-cutting CRITICAL also confirms the landed diff matches the co-signed brief scope (scope drift = FAIL).

## Retroactive co-sign owed (§6c deviation, tolerated under §6f solo)
`ws-reorder-deletes` shipped solo WITHOUT a cross-lane co-sign (it got 2 independent subagent verifies — impl≠verifier held — but not a Pair-A cross-lane sign). **Pair-A director: please do a retroactive scope confirmation** of `b33c595` (the `web_server.py:1402` + `domain/project_manager.py:1081` survivor-pass diff). It is already `verified`; this is a scope-confirm, not a re-verify.

## budget-nan design policy — DECIDED (user-endorsed 2026-06-14)
NaN budget cap → **fail-safe BLOCK** (NaN = corruption, not "unlimited"). `None` still = no cap. Pair-B encodes in the R-BRIEF + formalizes as an ADR with the fix.

## Open Wave-1 rows by lane (claim per the lifecycle, §6c)
PAIR-A: `aa-nan-rules` (auto_approve:118, lock) · `aa-inf-scorebypass` (auto_approve:424, lock) · `aa-budget-nan-veto` (auto_approve:584, lock) · `pulid-nan-node100` (quality_max:560, pure-lane) · `null-continuity-crash` (workflow_selector:515, pure-lane).
PAIR-B: `budget-nan` (core.py:101, lock) · `costtracker-perf-uncounted` (cost_tracker:282, pure-lane).

## Process
- Coordinator LIVE → the §6f deputy-write path is CLOSED; I reconcile inventory status + gate the wave. Post a `verify-request`/gate-request to me at a wave-boundary.
- Per-defect RED already exists (the strict-xfail pin). Confirm it via `--runxfail`, land the fix, remove the pin (strict=True → fixed-but-unremoved pin = XPASS = CI red). ONE pathspec commit per defect.
- Pod is STOPPED ($0); no Wave-1 row is pod-gated.

Cursor at send: unknown
