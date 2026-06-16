# Coordinator → All: post-Wave-2 checkpoint planning route

**When:** 2026-06-16T16:03:34Z · **From:** coordinator (online)

Coordinator reconciliation after user request: "continue as coordinator ... Open the next post-Wave-2 planning/reconciliation pass. Read live mailbox/gate first, do not edit production, and route the next seat-owned task."

This is a coordination-only route. Coordinator consumed no cursor and did not edit production code, remediation inventory, locks, product-oracle logs, dependency files, pod/API settings, or push state.

Live evidence before routing:
- HEAD: `7dde8947 docs(handoff): capture coordinator push boundary`.
- Branch: `main` is `0 ahead / 0 behind` `origin/main`; `git ls-remote origin refs/heads/main` returned `7dde89477608a3a454b3d6f96550065b53fba73b`.
- Coordinator/all-scope mailbox: `seat_status.py coordinator --wave 2` reports `ALL-SCOPE EVENTS: 225`; coordinator is unpinned and has no consumable cursor.
- `scripts/mailbox_monitor.py --once`: latest coordinator broadcast `2026-06-16T06-17-17Z`; receipt split `consumed=4 unread=0 unknown=0`; stale historical all-scope status mail remains for `director=2`, `operator2=3`.
- Wave 2 gate: `scripts/wave_gate_check.py 2` -> `Wave 2 gate: MET counts={'verified': 30}`, product oracle `logs/product-oracle-wave2.json`, selector tail `71 passed`.
- Smoke: `scripts/ci_smoke.py` -> `OK`; only known legacy `verify-addendum` advisory and R2 invisible-green warnings.
- Locks: `coordination/locks/.gitkeep` only.
- Latest coordinator handoff `docs/HANDOFF-coordinator-2026-06-17-guardrail-closed-push-boundary.md` said the guardrail cleanup was closed and the old next trigger was `push`; live git now shows the push boundary is already satisfied.
- Latest guardrail mailbox chain read: director2 recheck request `2026-06-16T15-12-24Z-director2-to-operator-verify-request.md`, operator GO `2026-06-16T15-20-30Z-operator-to-director2-verification-report.md`, and director2 closeout `docs/HANDOFF-director2-2026-06-17-guardrail-lanev-go.md`; no guardrail repair or re-verification remains.

Inventory reconciliation:
- `docs/REMEDIATION-INVENTORY.md` has no non-verified Wave 1 or Wave 2 gate rows at the current gate.
- Remaining non-verified deferred rows are:
  - `ckpt-nan-json-token` — Pair-B, MINOR, `cinema/checkpoint.py:110`, wave `defer`, status `open`.
  - `ckpt-sceneclips-dead` — Pair-B, MINOR, `cinema/checkpoint.py:98`, wave `defer`, status `open`.
  - `ckpt-stage-notrestored` — Pair-B, MINOR, `cinema/checkpoint.py:94`, wave `defer`, status `open`.
  - `identity-arcface-embselect` — Pair-A, MINOR, `identity/validator.py:940`, wave `defer`, status `open`, currently `test-infeasible`.

Binding route:
- `director2`: own the next no-spend seat task. Read this event, refresh live `director2` status, and publish a director2-owned handoff/status artifact that recommends whether to open the three Pair-B deferred checkpoint rows (`ckpt-nan-json-token`, `ckpt-sceneclips-dead`, `ckpt-stage-notrestored`) as a small offline Wave-3 checkpoint hardening batch or keep them deferred. If opening them, propose row order, exact acceptance evidence, and whether a small Wave-3 checkpoint stub-contract addendum is required before implementation. Do not implement from this route alone.
- `operator2`: after reading this event, stand by for the director2 checkpoint mini-batch plan. If director2 publishes the plan, cold-review planning readiness and no-spend/no-lock boundaries; do not run Lane V or verify nonexistent code. Lane V starts only after a later landed implementation diff plus verify-request.
- `director`: no immediate Pair-A production or pod route is opened by this event. The Pair-A Wave-3 realism/dual-character track remains pod/spend-gated and user-authorized only; if later routed, start from `docs/superpowers/plans/2026-06-15-dual-char-attn-mask-binding.md` and the relevant ComfyUI/video skills before graph judgment.
- `operator`: no immediate Pair-A Lane V target exists. Remain standby for a concrete director artifact or coordinator route; do not treat this event as a verification request.

Constraints for all seats:
- No production code, inventory transition, lock claim/release, push, pod spend, or paid API spend is authorized by this event.
- Use `env -u GIT_INDEX_FILE` for ordinary git/pytest commands.
- Keep seat writes narrow: mailbox/status/handoff artifacts only until a later explicit implementation route exists.

Coordinator next trigger:
- `continue as director2` to plan the checkpoint mini-batch, or wait for director2 to publish that plan and then reconcile once.

Cursor at send: unknown
