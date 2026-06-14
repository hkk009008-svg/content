"""R-VERIFY-TIER(B) pin — cost-conn-crossthread-drop (W2:MAJOR, money).

BUG: cost_tracker.py:228 creates the SQLite connection with the default
check_same_thread=True.  The shared CostTracker instance (core.py) is
constructed on the pipeline background thread; Flask request threads then
call record_api_call() -> log_api() -> log() -> conn.execute() on that same
connection object from a DIFFERENT thread.  sqlite3 raises
ProgrammingError("SQLite objects created in a thread can only be used in
that same thread") on the foreign-thread conn.execute at cost_tracker.py:271.
The exception propagates out of record_api_call, the cost entry is dropped,
and the budget accumulator (spent_usd) is not incremented — budget undercount.

(coordinator-filed Wave-2 row 04108cb; X1+X2 hold, X3 refuted = the prod call
sites log a WARNING so it is observable, not silent. This pin reproduces it at
the CostTracker level where the raw call deterministically raises.)

FIX (not landed): pass check_same_thread=False to sqlite3.connect() at
cost_tracker.py:228 and add a threading.Lock around conn writes so that
concurrent threads do not interleave commits.  When fixed, the cross-thread
record_api_call call succeeds: no exception, spent_usd > 0, and a SQLite
row is present.

NON-VACUITY STRATEGY: construct a real CostTracker on the main thread,
then call record_api_call('VEO') from a second threading.Thread.  Capture
any exception raised inside the thread.  Assert the FIXED behaviour: no
exception AND spent_usd > 0 AND a row is present in the DB.  Today the
foreign-thread conn.execute raises ProgrammingError -> xfail.
"""
import sqlite3
import threading

import pytest


@pytest.mark.xfail(
    strict=True,
    reason=(
        "W2:MAJOR:cost-conn-crossthread-drop cost_tracker.py:228: "
        "sqlite3.connect() uses default check_same_thread=True; the shared "
        "CostTracker.conn is created on the pipeline thread but Flask request "
        "threads call record_api_call() -> log() -> conn.execute (line 271) "
        "from a foreign thread, raising sqlite3.ProgrammingError and dropping "
        "the cost entry (budget undercount). "
        "Fix: check_same_thread=False + threading.Lock around conn writes; "
        "then cross-thread record_api_call succeeds, spent_usd > 0, and the "
        "SQLite row is present — this pin flips XPASS and is removed."
    ),
)
def test_cross_thread_record_api_call_succeeds(tmp_path):
    """record_api_call() from a second thread must not raise and must record spend.

    Reproduces the cross-thread sqlite3.ProgrammingError that drops cost
    entries when the shared CostTracker is called from Flask request threads
    (cost-conn-crossthread-drop).  The FIXED behaviour: no exception,
    spent_usd > 0, and a row is persisted in the DB.
    """
    from cost_tracker import CostTracker

    db = str(tmp_path / "cost.db")
    # Construct the tracker on the MAIN thread — mirrors how core.py creates
    # the shared CostTracker at pipeline startup (on the background thread).
    tracker = CostTracker(db_path=db, budget_usd=100.0)

    raised: list[BaseException] = []

    def worker():
        """Simulate a Flask request thread calling record_api_call."""
        try:
            tracker.record_api_call("VEO")
        except Exception as exc:  # noqa: BLE001
            raised.append(exc)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout=5.0)

    # --- FIXED behaviour assertions ---

    # 1. No exception propagated out of record_api_call on the foreign thread.
    assert not raised, (
        f"record_api_call('VEO') raised from a foreign thread: {raised[0]!r} — "
        "cost-conn-crossthread-drop: sqlite3.ProgrammingError due to "
        "check_same_thread=True (cost_tracker.py:228)"
    )

    # 2. The in-process accumulator must reflect the spend (VEO > $0.00).
    assert tracker.spent_usd > 0.0, (
        f"spent_usd={tracker.spent_usd!r} after cross-thread record_api_call('VEO') "
        "— cost was silently dropped (cost-conn-crossthread-drop)"
    )

    # 3. A cost_log row must be present in the DB.
    conn_check = sqlite3.connect(db)
    try:
        row_count = conn_check.execute(
            "SELECT COUNT(*) FROM cost_log WHERE model='VEO'"
        ).fetchone()[0]
    finally:
        conn_check.close()

    assert row_count >= 1, (
        f"No cost_log row for VEO after cross-thread call (row_count={row_count}) "
        "— cost-conn-crossthread-drop"
    )
