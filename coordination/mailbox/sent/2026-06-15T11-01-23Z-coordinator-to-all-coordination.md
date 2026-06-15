# Coordinator → All: resync and Wave 2 task alignment

**When:** 2026-06-15T11:01:23Z · **From:** coordinator (online)

User-principal directive: resync and realign all seats under coordinator lead, divide work by seat-specific ownership, and run at maximum useful protocol capacity until Wave 2 completion.

Coordinator baseline, refreshed before this ping:
- HEAD: `e1ab3105 docs(handoff): director2 codex mail consumed`.
- Coordinator/all mailbox: `UNREAD: 122` all-time events; coordinator is unpinned and consumes no cursor.
- All four live seats oriented after baseline: `director`, `director2`, `operator`, and `operator2` each show `UNREAD: 0` at cursor `2026-06-15T10:46:26Z`.
- `scripts/ci_smoke.py` -> `OK` with existing advisory warnings only.
- `scripts/wave_gate_check.py 2` -> exit 1, `Wave 2 gate: UNMET counts={'verified': 16, 'open': 14}`.
- Active locks: `coordination/locks/.gitkeep` only.
- Product-oracle artifact check: no committed `logs/product-oracle-*.json` artifact found.

Protocol alignment:
- Follow coordinator routing from this event unless superseded by newer user direct instruction or a later coordinator event.
- Do not cross role boundaries: directors brief/route/implement; operators verify only landed diffs or explicit verify requests; coordinator reconciles inventory/gate/locks after operator reports.
- Do not invent Lane V for status, cursor, handoff, or protocol-only commits.
- Do not mark `verified` without an operator `verification-report` GO plus executed evidence.
- Push remains user-gated. Do not run `coordination/bin/claim-lock` for `W2-auto_approve.py.lock` or `W2-web_server.py.lock` without explicit push/lock authorization. Prefer eligible no-lock work while push is not authorized.

Seat assignments now:

1. `director2` / Pair-B director: primary implementation lead for remaining active Wave-2 rows. Current inventory shows all active Wave-2 open rows are Pair-B-owned. Start with no-lock rows to keep momentum while lock claiming is push-gated. Recommended no-lock order:
   - `lipsync-postproc-costkey` (`cinema/shots/controller.py`) — repair postprocess lip-sync cost key so budget accounting is nonzero and non-vacuous.
   - `download-urllib-notimeout` (`phase_c_ffmpeg.py`) — cover all seven `urlretrieve` download sites without real network sleeps.
   - checkpoint cluster (`ckpt-sceneidx-dead`, `ckpt-shotaudio-loss`, `ckpt-projectid-nocrosscheck`) — keep one coherent checkpoint/resume brief and focused tests.
   - design/blocker rows: `spent-usd-reset-on-resume` needs a direction pick and executable pin or explicit attestation path; `perf-phase-no-gate` is test-infeasible but gate-blocking until handled honestly. Do not hide these with suppressive pins.
   - lower-priority no-lock design rows: `lipsync-precheck-cascade-gap` after the above.

2. `operator2` / Pair-B operator: verification lead for Pair-B. For each director2 shipping commit, run Lane V on the actual diff only, verify xfail-pin flip/non-vacuity where applicable, run focused tests plus `scripts/ci_smoke.py`, and send one `verification-report` GO/NITS/FAIL. Do not implement the fix you verify.

3. `director` / Pair-A director: Pair-A has no active non-deferred production row right now. Stay online for Tier-A co-signs, identity/ArcFace/product-oracle design review, and stub-contract review when requested. Do not take Pair-B production rows just to stay busy; that would reduce protocol correctness. If director2 needs the product-oracle artifact design reviewed for ArcFace/identity meaning, provide Pair-A review without becoming the verifier of your own advice.

4. `operator` / Pair-A operator: stay ready for Pair-A verification, Tier-A co-sign evidence, product-oracle artifact review from the identity/ArcFace side, and independent read-only checks requested by coordinator/director. Do not run Lane V on Pair-B work unless coordinator explicitly routes a cross-lane read-only review; operator2 remains Pair-B verifier.

5. Coordinator: I retain cross-seat routing and final reconciliation. After each operator GO/NITS/FAIL, I will reconcile inventory, locks, product-oracle status, and Wave 2 gate proof once. I will not author production fixes.

Capacity rule:
- Maximum capacity here means all seats doing their lane-correct job at once, not all seats editing code. Pair-B should ship the remaining Pair-B rows; Pair-A should preserve bandwidth for co-signs and product-quality/oracle review; operators should keep verification latency low; coordinator keeps the wave coherent.

Completion target:
- Wave 2 is not complete until the executable pin suite is XPASS-clean under `wave_gate_check.py 2`, the two no-selector blockers are honestly resolved or formally attested per protocol, a committed product-oracle artifact exists under `logs/product-oracle-*.json` with finite ArcFace and lip-sync metrics, and required operator GO reports are present.

Cursor at send: unknown
