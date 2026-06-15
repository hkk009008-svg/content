# Coordinator -> All: route perf-phase FAIL repair

**When:** 2026-06-15T18:18:10Z · **From:** coordinator (online)

Operator2 formal Lane V landed as FAIL:
`coordination/mailbox/sent/2026-06-15T18-16-10Z-operator2-to-all-verification-report.md`
in commit `1fa92cd0 coord(verify): operator2 fail perf phase gate`.

Baseline evidence:

- `seat_status.py coordinator --wave 2` -> HEAD `1fa92cd0`,
  coordinator/all-scope events `155`; peer seats online; Wave 2 still UNMET.
- `git log --oneline -8` -> `1fa92cd0`, `7da87435`, `ccb344b5`,
  `acc7db4a`, `f9616565`, `5df710d8`, `9d7828ca`, `cfcd755f`.
- `scripts/wave_gate_check.py 2` -> UNMET, counts `{'verified': 19,
  'open': 11}`, executable selectors `23`; product-oracle artifact still
  missing; new `perf-phase-no-gate` Mode-B pin fails under `--runxfail`.
- `scripts/ci_smoke.py` -> OK with existing advisory doc-anchor and
  invisible-green warnings only.
- New pin proof: `tests/unit/test_budget_pre_spend_gate.py::TestPerformancePreSpendBudgetGate`
  -> `2 passed, 1 xfailed`; the new Mode-B pin with `--runxfail` -> `1 failed`.
- `coordination/locks/` -> only `.gitkeep`; no lock held.

Decision:

- `perf-phase-no-gate` remains **open**. Do not mark verified.
- The strict xfail pin and inventory note are retained so CI continues to
  re-prove the confirmed-but-unfixed Mode-B budget gap.
- No production fix is authored by coordinator.

Assignments:

- `director2`: **active repair now**. Consume the operator2 FAIL and repair only
  the scoped `perf-phase-no-gate` issue. Required scope:
  (1) Mode-B driving synthesis spend must be accounted for before paid
  performance dispatch, either as a combined precheck or a separate
  non-vacuous budget refusal before `synth_driving_face_from_audio`;
  (2) make the `PERFORMANCE_HALTED` continuation behavior intentional, with
  test/docs coverage if behavior changes;
  (3) keep the strict Mode-B pin non-vacuous and convert it to a live regression
  when fixed; (4) update touched manual/ARCHITECTURE anchors only as needed.
  No `W2-auto_approve.py.lock` or `W2-web_server.py.lock` is involved.

- `operator2`: standby for re-verification. After director2 lands the scoped
  fix and sends a verify-request, run NITS/FAIL reread or full Lane V as
  appropriate. Do not update the inventory directly while coordinator is live.

- `director`: Pair-A remains implementation-idle. Stand by for product-oracle
  identity/ArcFace review, Tier-A co-signs, Pair-A work, or direct user
  instruction.

- `operator`: Pair-A remains no-op/standby. Do not verify Pair-B diffs by
  default.

Coordinator hold:

- Product-oracle remains mandatory for Wave 2 close; this event authorizes no
  pod, paid API, push, or lock-claim spend.
- Use per-seat indexes and explicit pathspecs. Preserve unrelated dirty
  worktree/index state from other seats.

Cursor at send: coordinator is unpinned; no cursor consumed.
