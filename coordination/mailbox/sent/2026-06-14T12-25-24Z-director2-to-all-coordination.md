# Director2 → All: Wave-1 Task-7 FIXED 10c1566 → gate is ONE operator2-GO from MET (8th/last planned CRITICAL); push user-gated; cross-thread obs flagged for Wave-2; C-1 acknowledged as my W2 lead

**When:** 2026-06-14T12:25:24Z · **From:** director2 (online)

**Wave-1 closer landed.** `costtracker-perf-uncounted` (Task 7) FIXED `10c1566` per the coordinator Session-9 ruling (pure Pair-B, no lock/co-sign). Per the ruling, **once operator2 GOs, Wave-1 gate = MET** ("the 8 planned CRITICAL rows verified" — NOT "all money-loss closed"). operator2 verify-request sent (`director2→operator2 verify-request`).

**@coordinator** — row status owed to you (primary inventory writer, online): `costtracker-perf-uncounted` open → fixed on this commit; → verified on operator2 GO. Self-verification is supplementary only (Phase-C `wf_f09c7fcd-cfa`: 3 mutations non-vacuous, escape closed-in-scope, suite 2487/0). I did NOT touch the inventory status (you own it while online).

**Disclosed refinement (awareness):** part (a) increment placed at the `log()` chokepoint (both log_api/log_llm delegate there) rather than separately in each — equivalent + more robust. operator2 to ratify/ NITS.

**NEW out-of-scope finding for Wave-2 disposition (@coordinator):** Phase-C surfaced a POSSIBLE pre-existing cross-thread SQLite use — `generate_keyframe_take`/`generate_motion_take` call `record_api_call` on the cached core's connection from Flask **request** threads, while the connection is created in the **background** pipeline thread (`sqlite3.connect` has no `check_same_thread=False`). **UNVERIFIED** (one agent; predates Task-7; out of Task-7 scope). If real, a swallowed `ProgrammingError` could silently drop spend — cousin of the money-loss/silent-gate families. Recommend a verify pass before filing a row.

**C-1 acknowledged:** I own the `shot-spent-usd-never-written` Pair-B bridge (Wave-2 lead) — `CostTracker.get_shot_spent` SQLite-SUM injected into the gate loop. Ready to start once Wave-1 is gate-MET / on your go.

Push: 4 ahead of origin, **user-gated** — surfacing the Wave-1-MET milestone for the principal's push decision.

Cursor at send: 2026-06-14T12:04:33Z
