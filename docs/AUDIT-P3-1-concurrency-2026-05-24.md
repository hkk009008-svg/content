# P3-1 Concurrency Audit — 2026-05-24

**Auditor:** Director (cycle 3, in-session)
**Trigger:** POST-ROADMAP Tier-1 #3 — "audit-shaped" promotion from
honorable-mention after Session 5 reviewer caught one missing lock
(`_cores_lock`) and the rest was unaudited.
**Scope:** All module-level mutable globals accessible across threads,
plus all `threading.Lock` / `threading.RLock` declarations in the
codebase (excluding `.venv/`, `.git/`, `tests/`, `.claude/worktrees/`).
**Method:** Filesystem grep for `^_[a-z_]*: dict|list|set` and
`= {}|[]` + `threading.Lock|RLock` declarations; targeted reads of
each guard's acquire / release sites to verify symmetry; trace of
unguarded global accesses to look for check-then-write or check-then-use
patterns.

> This is a findings document. No fixes shipped in the audit commit.
> Each finding's recommended remediation is sized so a follow-up
> implementer brief can scope a fix slice without re-discovering the
> surface.

---

## TL;DR — two real race surfaces, both in `web_server.py`

1. **CRITICAL — `_running_pipelines` is unguarded across check-then-write.**
   `web_server.py:1161-1173`. Two concurrent `POST /api/projects/{pid}/generate`
   requests for the same `pid` can BOTH pass the `pid in _running_pipelines`
   check, both spawn background threads, both run the heavy CinemaPipeline
   constructor, both write to `_running_pipelines[pid]`. The losing
   pipeline is still RUNNING (GPU work, API calls, project.json writes) —
   it's just no longer reachable via the dict. Result: duplicate GPU
   spend, racing disk writes, state corruption.

2. **MODERATE — `_progress_queues` check-then-set in `_ensure_progress_queue`.**
   `web_server.py:97-102`. Two concurrent callers for the same `pid`
   can both see `None`, both create a `queue.Queue`, both write —
   second wins. The first queue is orphaned with a thread writing to
   it; SSE consumers reading `_progress_queues.get(pid)` get the
   second queue and miss the first's events. Result: lost progress
   events, memory leak.

The recommended fix is the same pattern already in production for
`_running_cores` / `_cores_lock` and `_lora_training_threads` /
`_lora_training_lock` — add a module-level `threading.Lock` and
hold it around any composite read-then-write on the dict.

---

## Inventory of module-level mutable globals

Verified via two grep passes (lowercase + uppercase typing
annotations, with-and-without explicit `dict[...]` annotation):

```bash
$ grep -n "^_[a-z_]*: dict|list|set|^_[a-z_]* = {}|[]" --include="*.py" \
    -r /Users/hyungkoookkim/Content/ | grep -v ".venv|.git|tests|worktrees|web/"

$ grep -rn "^[A-Z_][A-Z_0-9]*: (Dict|List|Set|dict|list|set)|^[a-z_][a-z_0-9]*: (Dict|List|Set)|^_[a-z_]* = dict()|^_[a-z_]* = list()|^_[a-z_]* = set()" \
    --include="*.py" /Users/hyungkoookkim/Content/ | grep -v ".venv|.git|tests|worktrees|web/"
```

| Global | Location | Guard | Status |
|---|---|---|---|
| `_progress_queues: dict[str, queue.Queue]` | `web_server.py:66` | — | ❌ **UNGUARDED** |
| `_running_pipelines: dict[str, CinemaPipeline]` | `web_server.py:67` | — | ❌ **UNGUARDED** |
| `_running_cores: dict[str, PipelineCore]` | `web_server.py:76` | `_cores_lock` (L77) | ✅ Guarded (Session 5 fix) |
| `_lora_training_threads: dict[str, threading.Thread]` | `web_server.py:537` | `_lora_training_lock` (L538) | ✅ Guarded |
| `_UPLOAD_CACHE: Dict[str, str]` | `quality_max.py:71` | `_UPLOAD_CACHE_LOCK` (L79) | ✅ Guarded |
| `_WHISPERX_MODEL_CACHE: dict` | `audio/alignment.py:31` | `_MODEL_LOCK` (L34) | ✅ Guarded |
| `_ALIGN_MODEL_CACHE: dict` | `audio/alignment.py:32` | `_MODEL_LOCK` (L34) | ✅ Guarded |
| `_WHISPER_MODEL_CACHE: dict` | `audio/alignment.py:33` | `_MODEL_LOCK` (L34) | ✅ Guarded |

Uppercase-named constants that are populated at module-load time only
and never mutated at runtime (`API_COST_USD`, `WORKFLOW_TEMPLATES`,
`MAX_QUALITY_TEMPLATES`, `MOTION_FIDELITY_FLOORS`,
`_MAX_TIER_KNOB_SCHEMA`, `NEGATIVE_PROMPT_BY_FAILURE_REASON`,
`_DEFAULT_MODELS`, `SHOT_TYPE_THRESHOLDS`) were filtered out — they're
effectively read-only after import. The two grep passes above are the
union of patterns; the inventory above is exhaustive for declared-type-
annotated mutable module-globals.

## Inventory of `threading.Lock` declarations

Verified via:

```bash
$ grep -rn "threading\.Lock\(\)|threading\.RLock\(\)" --include="*.py" \
    /Users/hyungkoookkim/Content/ | grep -v ".venv|.git|worktrees"
```

| Lock | Location | Guards | Status |
|---|---|---|---|
| `_cores_lock` | `web_server.py:77` | `_running_cores` | ✅ Symmetric (acquire at L89, L1628) |
| `_lora_training_lock` | `web_server.py:538` | `_lora_training_threads` | ✅ Symmetric (acquire at L587, L592) |
| `_AES_LOCK` | `face_validator_gate.py:45` | Lazy init of `_AES_MODEL`, `_AES_PROCESSOR` | ✅ Init-only guard; post-init reads are CPython-GIL-safe |
| `_SHARED_VALIDATOR_LOCK` | `identity/__init__.py:59` | Lazy init of `_SHARED_VALIDATOR` | ✅ Double-checked locking; unguarded read at L81 is safe under CPython GIL |
| `_WORKFLOW_LOCK` | `quality_max.py:77` | Workflow cache | ✅ Symmetric (used at L188) |
| `_NODE_AVAILABILITY_LOCK` | `quality_max.py:78` | Node availability cache | ✅ Symmetric (used at L263, L274) |
| `_UPLOAD_CACHE_LOCK` | `quality_max.py:79` | Upload cache | ✅ Symmetric (used at L306, L311) |
| `_MODEL_LOCK` | `audio/alignment.py:34` | 3 whisper/align/whisperx model caches | ✅ Symmetric (used at L98, L113, L182) |
| `self._gate_lock` (instance) | `cinema/lifecycle.py:130` | Per-instance gate state | Scope-bounded; not a module-global concern |

All locks except the two unguarded module-globals above are
correctly paired.

---

## Findings

### Finding #1 — CRITICAL: `_running_pipelines` check-then-write race

**Where:** `web_server.py:1161-1173`

```python
if pid in _running_pipelines:                    # L1161  ← READ
    return jsonify({"error": "..."}), 409

# ... 9 lines of setup ...

def run_pipeline():
    try:
        pipeline = CinemaPipeline(pid, ...)      # L1172  ← HEAVY (100ms-2s)
        _running_pipelines[pid] = pipeline       # L1173  ← WRITE
        ...
    finally:
        _running_pipelines.pop(pid, None)        # L1181  ← DELETE
```

**Race window:** Between L1161 (read) and L1173 (write), the heavy
`CinemaPipeline(...)` constructor runs (ContinuityEngine + ChiefDirector
+ LLMEnsemble + QualityTracker + CostTracker instantiation — easily
100ms to several seconds). During that window, a second
`POST /api/projects/{pid}/generate` for the same `pid` sees an empty
slot and spawns its own background thread.

**Reachability:** Two clicks within ~1-2 seconds on the same project
trigger this. Multi-device access guarantees it. Frontend
button-debounce would close one window but not all (curl, scripted
requests, etc.).

**Consequences:**
- Two CinemaPipelines run on the same project concurrently.
- Both write to `projects/{pid}/project.json` — last-write-wins data
  corruption. Note that `save_project` already uses a per-project
  file-lock (`_acquire_project_lock`) at `domain/project_manager.py`,
  so the disk write itself is serialized, but the two pipelines'
  in-memory state diverges from disk.
- Both call paid APIs (Kling, Sora, Anthropic, etc.) — direct cost
  duplication.
- GPU resources double-booked; one pipeline likely OOMs or slows the
  other dramatically.
- `_running_pipelines.pop(pid, None)` at L1181 removes EITHER
  pipeline's entry on its `finally`. If one pipeline finishes first,
  the other's entry is removed too, breaking subsequent
  `_running_pipelines.get(pid)` reads (cancel, status endpoints
  return "no generation in progress" while a pipeline is still
  running).

**Recommended fix shape (~10-15 LOC):**

```python
_pipelines_lock = threading.Lock()  # new

# In api_generate (around L1161-1192):
with _pipelines_lock:
    if pid in _running_pipelines:
        return jsonify({"error": "..."}), 409
    # Reserve the slot BEFORE leaving the lock.
    _running_pipelines[pid] = _PIPELINE_PENDING  # sentinel

# Inside run_pipeline, replace the slot once constructed:
def run_pipeline():
    try:
        pipeline = CinemaPipeline(pid, ...)
        with _pipelines_lock:
            _running_pipelines[pid] = pipeline   # replace sentinel
        ...
    finally:
        with _pipelines_lock:
            _running_pipelines.pop(pid, None)
```

The sentinel pattern matters because between "reserve" and
"construct" the entry must already evidence "busy" to other readers.
Readers in `_get_stage_pipeline` / `_reject_if_project_busy` should
treat the sentinel as "busy but not yet ready" — likely return a
409 / 503 with retry-after.

Alternative (simpler): hold the lock across the entire
`CinemaPipeline(...)` construction. This serializes pipeline starts
globally, which is fine for a small operator team but limits
concurrent project starts. Trade-off worth surfacing.

### Finding #2 — MODERATE: `_progress_queues` check-then-set race

**Where:** `web_server.py:97-102`

```python
def _ensure_progress_queue(pid: str) -> queue.Queue:
    q = _progress_queues.get(pid)        # L98  ← READ
    if q is None:
        q = queue.Queue()
        _progress_queues[pid] = q        # L101 ← WRITE
    return q
```

**Race window:** Standard double-create-and-overwrite pattern. Two
threads see None, both create, second's write replaces first's.

**Reachability:** Lower than Finding #1 because the typical call
pattern is "one /generate call → one queue create". But:
- Concurrent /generate on the same project triggers this same
  function twice (in addition to Finding #1).
- Any future code path that calls `_ensure_progress_queue` from
  multiple threads independently would also trigger.

**Consequences:**
- First queue is orphaned. The first thread holds it by reference and
  writes events to it. Nobody reads (the SSE stream reads from
  `_progress_queues.get(pid)` which returns the second queue).
- Memory leak — the orphaned queue grows until the producer thread
  exits and lets GC reclaim.
- Lost progress events from the orphaned producer.

**Recommended fix shape (~5 LOC):**

```python
_queues_lock = threading.Lock()  # new (or reuse _pipelines_lock)

def _ensure_progress_queue(pid: str) -> queue.Queue:
    with _queues_lock:
        q = _progress_queues.get(pid)
        if q is None:
            q = queue.Queue()
            _progress_queues[pid] = q
        return q
```

Note: the cleanup at `web_server.py:1186-1187` (`if
_progress_queues.get(pid) is q: _progress_queues.pop(pid, None)`)
already uses an identity-check to avoid pop-after-replace. With the
lock above, that check could move inside the lock too for full
airtightness, but the current code's race window is microscopic
(`get is q` then `pop`); accepting it is reasonable.

### Finding #3 — LOW: Reader-side staleness on unguarded `_running_pipelines.get`

**Where:** `web_server.py:119, 1230, 1438, 1448, 1458, 1478, 1512, 1578`

All these sites do:

```python
pipeline = _running_pipelines.get(pid)
if pipeline:
    pipeline.cancel()  # or .status() or .get_progress() etc.
```

CPython GIL guarantees `dict.get` is atomic at the C level. The
reader can't see a half-initialized pipeline. But:

- Between `get` and `pipeline.cancel()`, the `finally` block at L1181
  may `pop(pid)` the entry. The reader still holds a reference so the
  pipeline object isn't GC'd, but the pipeline may be mid-shutdown.
- `pipeline.cancel()` and friends should be idempotent / safe-to-call-
  during-cleanup. **Worth verifying as a separate audit slice**
  (read `CinemaPipeline.cancel` semantics).

**Risk severity:** LOW. The CinemaPipeline lifecycle methods are
likely idempotent (or fail gracefully). But the audit can't claim
this without reading them; surface as a follow-up.

**Recommended action:** Out of scope for the lock-add slice. Spin off
as a separate small audit task: "verify `CinemaPipeline.cancel` /
`.pause` / `.resume` / `.get_state` are safe to call concurrently
with the pipeline's own background thread during shutdown."

### Finding #4 — OK: All other locks are correctly paired

Every other `threading.Lock` in the codebase is correctly used:
- `_cores_lock` (web_server.py:77) — symmetric, properly guards
  `_running_cores`. This is the Session 5 fix.
- `_lora_training_lock` (web_server.py:538) — symmetric, guards
  `_lora_training_threads`.
- `_AES_LOCK`, `_SHARED_VALIDATOR_LOCK` — lazy-init guards,
  double-checked locking pattern is safe under CPython GIL.
- `_WORKFLOW_LOCK`, `_NODE_AVAILABILITY_LOCK`, `_UPLOAD_CACHE_LOCK`
  (quality_max.py:77-79) — all symmetric.
- `_MODEL_LOCK` (audio/alignment.py:34) — symmetric, guards all 3
  model caches (`_WHISPERX_MODEL_CACHE`, `_ALIGN_MODEL_CACHE`,
  `_WHISPER_MODEL_CACHE`) with a check-then-set pattern that's
  airtight under the lock.
- `self._gate_lock` (cinema/lifecycle.py:130) — instance-scoped, no
  cross-instance contention.

No locks are MISSING acquire/release pairs, no nested-lock orderings
that could deadlock, no `Lock` vs `RLock` misuse spotted.

---

## Out-of-scope for this audit

- **`CinemaPipeline` internal thread-safety** — the pipeline itself
  is a complex multi-stage state machine. Whether `cancel()` / `pause()`
  etc. are safe under concurrent calls is a deeper question. Out of
  scope here; see Finding #3.
- **SQLite / DB connection threading** — Session 5 partially audited
  the cost-tracker DB connection. A full DB-threading audit would
  trace every `sqlite3.connect` site and verify connection-per-thread
  semantics. Out of scope.
- **`asyncio` / event-loop interactions** — this codebase uses
  threading, not asyncio, for background work, so no event-loop /
  thread mixing concerns. Confirmed via grep for `asyncio` (no
  production usage).
- **Frontend race conditions** (button debounce, optimistic UI, etc.)
  — front-end is React; not a Python-concurrency concern. The
  frontend SHOULD debounce the Generate button as a defense-in-depth
  measure, but it's not a substitute for the lock.

---

## Recommended next step

**Author a Session 9-style brief** for a "concurrency hardening" slice
covering Findings #1 + #2. Estimated scope:
- `+1 lock declaration`, `~15 LOC` lock-acquire wrapping in
  `web_server.py`, `+1 sentinel constant`
- `~5 tests` in `tests/unit/test_web_server_concurrency.py` (NEW) that
  use `threading.Thread` + `threading.Event` to spin up two concurrent
  `api_generate` calls and assert exactly one succeeds.
- Acceptance: `pytest tests/unit/` whole-suite still passes; new tests
  prove the race is closed.

Effort: S (1 session, ~60-90 min implementer subagent).

Finding #3 should be a separate audit task ("CinemaPipeline lifecycle
thread-safety") that doesn't need a fix slice — purely investigative.

---

*Verified at HEAD `64c7571` (2026-05-24, post-Monitor-wiring close):
`grep` inventory complete; `wc -l web_server.py` confirms file
boundaries; all line numbers cited in this doc resolve to the cited
code in the working tree.*
