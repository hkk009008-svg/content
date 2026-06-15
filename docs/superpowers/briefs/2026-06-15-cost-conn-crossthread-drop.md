# R-BRIEF: cost-conn-crossthread-drop - make shared CostTracker SQLite writes thread-safe

PRIORITY: MAJOR        LANE: B (video/assembly/audio money gate)
CROSS-CUTTING: no
No lock: `cost_tracker.py` is not one of the four protocol cross-cutting lock files
(`auto_approve.py`, `cinema/context.py`, `core.py`, `web_server.py`).

## The defect

`CostTracker` creates one SQLite connection on the constructing thread, then
request/pipeline threads can call `record_api_call()` / `log_api()` / `log_llm()`
through the shared core tracker. With SQLite's default `check_same_thread=True`,
the foreign-thread write raises `sqlite3.ProgrammingError`, drops the cost row,
and leaves `spent_usd` stale. This also explains the operator2 FAIL on
`llmensemble-cost-uncounted`: ensemble candidate calls log from
`ThreadPoolExecutor` workers into the shared tracker.

## Rule #12 - grep-the-writes

TARGET SYMBOL: `CostTracker.conn` write path and `CostTracker.spent_usd`
accumulator.

```text
$ rg -n "self\.conn\s*=|sqlite3\.connect|self\.conn\.execute|self\.conn\.commit|self\.spent_usd\s*\+=" cost_tracker.py
228:        self.conn = sqlite3.connect(self.db_path)
237:        self.conn.execute("""
251:        self.conn.commit()
271:        self.conn.execute(
279:        self.conn.commit()
306:        self.spent_usd += cost_usd
499:        row = self.conn.execute(
516:        rows = self.conn.execute(
560:        row = self.conn.execute(
612:        rows = self.conn.execute("SELECT * FROM cost_log").fetchall()
```

Runtime write sites are `self.conn.execute`/`commit` in `_create_table()` and
`log()`, with `self.spent_usd += cost_usd` as the in-process budget-gate
accumulator write.

## Rule #13 - symmetric / sibling audit

SHARED STATE: the single `CostTracker.conn` plus `spent_usd`.

```text
$ rg -n "def log\(|def log_llm\(|def log_api\(|def record_api_call\(|def get_shot_spent\(|def get_video_cost\(|def get_session_cost\(|def get_summary\(|def close\(" cost_tracker.py
257:    def log(
319:    def log_llm(
360:    def log_api(
381:    def record_api_call(
478:    def get_shot_spent(self, shot_id: str) -> float:
508:    def get_video_cost(self, video_id: str) -> dict:
551:    def get_session_cost(self, lookback_hours: float = 24.0) -> float:
605:    def get_summary(self) -> str:
681:    def close(self):
```

Audit result: `log_llm()`, `log_api()`, and `record_api_call()` all delegate to
`log()`, so one lock around `log()` covers all cost writes. `_create_table()`
uses the same connection during construction and should use the same lock.
Read helpers and `close()` share the connection and should also take the lock so
reads cannot interleave with commits or close while another thread is writing.
Budget predicate reads of `spent_usd` should snapshot it under the same lock.

## Full-shape pattern reference

MIRROR: existing `log()` chokepoint at `cost_tracker.py:257` - all write APIs
delegate to this method and it returns a `CostEntry` only after SQLite commit.
Preserve that contract: no accumulator increment before a successful commit, no
caller-facing API shape change, and no per-call fresh tracker.

## The fix

Small direct implementation in Pair-B:

- open the SQLite connection with `check_same_thread=False`;
- add an instance lock around connection writes/reads and `spent_usd` mutation;
- keep `log_llm()`, `log_api()`, and `record_api_call()` public signatures stable;
- convert `tests/unit/test_cost_conn_crossthread_xfail.py` from strict xfail pin
  to live regression after it passes.

Expected files touched: `cost_tracker.py`,
`tests/unit/test_cost_conn_crossthread_xfail.py`,
`docs/REMEDIATION-INVENTORY.md`.

## Verification

Expected focused commands:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cost_conn_crossthread_xfail.py -q
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_llmensemble_cost_uncounted_xfail.py -q
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cost_tracker.py -q
```

Operator2 Lane V should additionally rerun the money/cost slice and decide
whether the repaired root row is sufficient to GO the prior llmensemble FAIL.
