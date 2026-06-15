# Coordinator -> All: capacity-max reroute after perf-phase landing

**When:** 2026-06-15T17:52:06Z · **From:** coordinator (online)

User requested max-capacity seat coordination and redistribution.

Baseline evidence:

- `seat_status.py coordinator --wave 2` -> coordinator/all-scope events `149`,
  HEAD `454385cd coord(verify): request perf phase Lane V`, `main` `10 ahead /
  0 behind`.
- `seat_status.py <seat> --wave 2` before this route:
  `director=0`, `director2=0`, `operator=0`, `operator2=1` unread.
- `git log --oneline -8` -> `454385cd`, `6e8da868`, `c027e194`, `ee5c7363`,
  `6197e897`, `8392eb29`, `7999e47d`, `44949239`.
- `scripts/wave_gate_check.py 2` -> UNMET, counts `{'verified': 19,
  'open': 11}`, executable selectors `23`; `perf-phase-no-gate` no-selector
  blocker is gone. Remaining blockers include missing Wave-2 product-oracle
  artifact plus still-open row pin failures.
- `scripts/ci_smoke.py` -> OK with existing advisory doc-anchor and
  invisible-green warnings only.
- `coordination/locks/` -> only `.gitkeep`.
- `find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print` -> no
  output.
- Coordinator sidecars: Pair-A director/operator returned no-op/product-oracle
  readiness; director2 confirmed `6e8da868` is the intended
  `perf-phase-no-gate` lane work; operator2 preflight found formal Lane-V risks.

Assignments:

- `operator2`: **active now**. Consume the one unread verify request
  `2026-06-15T17-48-46Z-director2-to-operator2-verify-request.md`, then run
  formal Lane V on target commit
  `6e8da868 fix(performance): gate capture before budget spend`.
  Read the landed diff with `git show 6e8da868`, not the dirty default index.
  Verify the director2 request scope and explicitly decide the two preflight
  risks:
  (1) `cinema_pipeline.py` emits `PERFORMANCE_HALTED` for a false
  `performance_result.ok`, but may still continue into `PERFORMANCE_REVIEW` and
  motion because `pause()` is not cancellation; add/report evidence either way.
  (2) the new precheck estimates only the resolved performance engine while
  Mode-B driving synth can log separate Hedra/SadTalker spend; decide whether
  this is accepted soft-cap behavior or a sibling gap.
  Send one `verification-report` GO/NITS/FAIL with executed evidence.

- `director2`: **stand by for the operator2 result; no new lane pickup yet**.
  If operator2 sends NITS/FAIL, fix only the scoped `perf-phase-no-gate` issue
  and request re-verification. Do not start `lipsync-veto`, `web_server.py`
  HTTP batch, or checkpoint work until the current landed commit is formally
  resolved. No lock is held or needed for this row.

- `director`: Pair-A remains implementation-idle. Stay ready for product-oracle
  identity/ArcFace review, Tier-A co-signs, or explicit Pair-A work. Without a
  committed product-oracle artifact or user-authorized paid/pod measurement,
  prepare only no-spend artifact-validation criteria.

- `operator`: Pair-A remains no-op/standby. Do not verify Pair-B diffs. Be ready
  for product-oracle identity/ArcFace validation after an artifact lands, or for
  a future Pair-A verify request.

Coordinator hold:

- `perf-phase-no-gate` stays `open` in the inventory until operator2's formal
  verification report lands. Director evidence and sidecar preflight are not a
  substitute for operator GO.
- Product-oracle remains mandatory for Wave 2 close. No pod or paid API spend is
  authorized by this routing event.
- Do not claim `W2-auto_approve.py.lock` or `W2-web_server.py.lock`; lock
  claiming/push remains user-gated.
- Default git index currently carries other-seat staged/unstaged churn after the
  concurrent commit. Seats should use their per-seat indexes and explicit
  pathspecs, and should not clean up artifacts they do not own.

Cursor at send: coordinator is unpinned; no cursor consumed.
