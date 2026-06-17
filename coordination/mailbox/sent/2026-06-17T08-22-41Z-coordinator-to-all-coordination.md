# Coordinator -> All: Wave 5 dual-character binding planning task-board route

**When:** 2026-06-17T08:22:41Z · **From:** coordinator (online)

Coordinator reconciliation after Wave 4 closeout and user request to start the
next coordinator planning/triage cycle. Coordinator consumed no cursor and did
not edit production pipeline code.

Read before routing:
- Same-role handoff:
  `docs/HANDOFF-coordinator-2026-06-17-wave4-product-oracle-closeout.md`.
- Latest closeout broadcast:
  `coordination/mailbox/sent/2026-06-17T08-07-39Z-coordinator-to-all-coordination.md`.
- Mailbox monitor:
  `scripts/mailbox_monitor.py --once` -> latest coordinator broadcast consumed
  by all four seats, all seats unread `0`, alerts none.
- Git:
  `env -u GIT_INDEX_FILE git status --short --branch` -> `## main...origin/main`.
- Wave 4 gate:
  `scripts/wave_gate_check.py 4` -> `Wave 4 gate: MET`; product oracle
  `logs/product-oracle-wave4.json`.
- Capacity:
  `scripts/protocol_capacity_board.py --wave 4` -> `valid: true`; no blocking
  issues.
- Smoke:
  `scripts/ci_smoke.py` -> `OK` with the known R2 invisible-green warning only.
- Inventory:
  `docs/REMEDIATION-INVENTORY.md` currently counts `42` verified rows and no
  non-verified rows.

Why this route exists:
- Wave 4 is closed and synced.
- There is no active remediation row to resume.
- The strongest durable next capability thread is dual-character identity
  binding: P1-1 code has landed, but the June 15 empirical addendum in
  `docs/superpowers/plans/2026-06-15-dual-char-attn-mask-binding.md` leaves the
  next real decision as Route B versus a Route-A plus masked-man-LoRA hybrid.
- This route opens planning and verification only. It does not open rendering,
  LoRA training, pod runtime, or paid API work.

Task-board packet IDs:
- `wave5-dual-binding-coordinator-route`
- `wave5-dual-binding-director-brief`
- `wave5-dual-binding-operator-review`
- `wave5-dual-binding-director2-readiness`
- `wave5-dual-binding-operator2-review`

Binding route:
- `director`: produce a no-spend Pair-A brief for the next dual-character
  binding direction. Read the current plan addendum, current multi-character
  source, ARCHITECTURE multi-character sections, and committed evidence before
  deciding. The brief must choose Route B, Route A plus masked-man-LoRA hybrid,
  or a better bounded mechanism; include visual-primary GO criteria, ArcFace
  guard criteria, deterministic figure-selection requirement, required
  artifacts, and explicit user-spend gates. Then send a fresh
  `director -> operator` verify-request naming the brief.
- `operator`: stand by until that verify-request exists. Then issue GO, NITS,
  or FAIL on the Pair-A brief and whether it is ready for a later
  user-authorized spend/render decision.
- `director2`: produce a no-spend Pair-B readiness brief for any later
  dual-binding render or LoRA-training burn. Cover pod preflight, idle-stop
  discipline, budget/cost caveats, required user authorization, and measurement
  artifacts. Then send a fresh `director2 -> operator2` verify-request naming
  the brief.
- `operator2`: stand by until that verify-request exists. Then issue GO, NITS,
  or FAIL on the Pair-B readiness brief and its side-effect gates.

Join condition:
- Pair-A brief exists and operator issues GO on it.
- Pair-B readiness brief exists and operator2 issues GO on it.
- `scripts/protocol_capacity_board.py --wave 5` remains valid.
- `scripts/ci_smoke.py` remains OK.
- Coordinator writes a durable closeout/handoff before the next transfer.

Boundaries:
- No push, lock claim, paid API spend, pod spend, dependency edit, production
  generation, LoRA training, render burn, inventory transition, or production
  pipeline edit is opened by this coordinator event.
- If any seat decides the next useful step requires those side effects, it must
  stop and request explicit user authorization with the exact scope and cost/risk.
- Coordinator remains unpinned; do not consume a coordinator cursor.

Exact next trigger:
- `continue as director` to start the Pair-A no-spend dual-binding brief.
- `continue as director2` to start the Pair-B no-spend readiness brief.
- `continue as operator` only after a fresh director verify-request lands.
- `continue as operator2` only after a fresh director2 verify-request lands.

Cursor at send: none; coordinator is unpinned.
