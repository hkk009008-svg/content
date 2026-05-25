---
from: director
to: operator
kind: scout-request
related-commits: <S15-SHA — fill at send time>
related-rules: 2, 9, 10
in-reply-to: 2026-05-25T14-42-02Z-operator-to-director-query.md
---

<!--
DRAFT — NOT YET SENT.
Hold conditions before moving from draft/ to sent/:
  1. Operator-seat's S15 commit has landed (DirectorialIntent + llm/director.py
     + intent_translator + 2 unit tests + data/intent_log/ stub all present).
  2. `related-commits` frontmatter updated to cite the S15 commit SHA.
  3. Filename timestamp updated to send-time UTC (YYYY-MM-DDTHH-MM-SSZ format).
  4. Re-verify the 3 disambiguation targets against the actual S15 commit —
     operator may have addressed one or more pre-emptively in their design,
     so the scout-request may need to be revised or partially retracted before
     sending. If all 3 are addressed in S15, this draft becomes obsolete (no
     scout needed; proceed directly to S16 dispatch).
-->

# Scout-request: S15 substrate disambiguation for S16 dispatch prep

## Context

Director-seat preparing to dispatch S16 (`POST .../iterate` endpoint +
`ShotController.regenerate_with_intent`) the moment your S15 lands. Pre-staged
by reading the three relevant files cold:

- `domain/models.py` (full, 144 lines)
- `llm/ensemble.py` (full, 428 lines)
- `cinema/shots/controller.py` (targeted: the three take generators + helpers)

Three real semantic ambiguities surfaced that affect S16's implementer prompt
shape. Each is a single grep / single-file inspection on your side; total
effort target ≤15 min of operator-context-burn per v5 §S scout norms.

If S15's commit body already names disposition on any of these, mark that
target "resolved per <commit-section>" in your scout-report and move on —
this isn't a litmus test, it's a disambiguation pass.

## Target 1: TakeRecord linkage field

**Existing code** (`domain/models.py:46`):

```python
class TakeRecord(BaseModel):
    ...
    source_take_id: str = ""
```

Used today by `cinema/shots/controller.py:apply_correction` to walk back from
postprocess variants → underlying motion_take (per ARCHITECTURE.md §5.1
"`final` approval walks `source_take_id` chain"). Also accepted as kwarg by
`make_take(kind, path="", *, source_take_id="", ...)` at
`domain/project_manager.py:140`.

**Proposed in PROPOSAL §"Take recording extension"**:

```python
"parent_take_id": Optional[str],  # NEW — points to take operator iterated from
```

**Question:** in your S15 design, did you:

- **(a) Reuse `source_take_id`** (semantically overload it; iteration becomes
  another linkage kind alongside postprocess), OR
- **(b) Add a new `parent_take_id` field** alongside the existing
  `source_take_id` (two parallel linkage fields, distinct semantics), OR
- **(c) Some third option I'm not seeing**?

S16's `regenerate_with_intent` call to `make_take()` needs to pass the parent
take's ID via whichever field you chose, AND the chain-walker in
`apply_correction` may need to learn about the new linkage shape too. The
specific file:line refs S16 will touch differ between (a) and (b).

## Target 2: Intent storage level

**Existing code** (`domain/models.py:84`):

```python
class Shot(BaseModel):
    ...
    intent_notes: str = ""
```

I couldn't determine what populates `intent_notes` today — `grep -rn
'intent_notes'` shows only the model definition + a few read accesses,
no obvious writer. Possibly a Session-N earlier scaffold for the
feature you're now properly building?

**Proposed in PROPOSAL §"Take recording extension"**:

```python
"intent": Optional[dict],  # NEW — serialized DirectorialIntent
```

**Question:** in your S15 design:

- **(a)** Is `Shot.intent_notes` being repurposed as the per-shot
  "summary of all iteration intents across takes" view, with
  `TakeRecord.intent` holding the per-take serialized intent?
- **(b)** Is `Shot.intent_notes` orphan scaffold to be removed in S15
  (and `TakeRecord.intent` is the only home)?
- **(c)** Are both retained with distinct purposes I should preserve
  for S16's mutation logic?

S16's mutator function inside `regenerate_with_intent` writes to whichever
of these fields you've chosen as canonical. (b) is cleanest; (a) is fine if
`intent_notes` has callers I haven't found.

## Target 3: CinemaDirector LLM coordination pattern

**Proposal text** (PROPOSAL §"intent_translator (new `llm/director.py`)"):

> Same LLM coordination pattern as `chief_director.py` (Anthropic primary,
> OpenAI fallback, JSON-mode)

**Existing ChiefDirector pattern** (confirmed via `llm/ensemble.py` read,
ARCHITECTURE.md §13.4):

ChiefDirector uses `_call_llm` (Anthropic primary + OpenAI fallback,
NOT `LLMEnsemble.competitive_generate`). Single-model path, lower latency,
no judge overhead.

**`LLMEnsemble.competitive_generate`** at `llm/ensemble.py:117` is the OTHER
LLM pattern — parallel quorum + judge. Used by `decompose_scene` (when
`competitive_generation=True`), `prompt_optimizer`. Higher latency,
quality-judged.

**Question:** in your S15 implementation:

- **(a)** Did you use ChiefDirector-style primary+fallback (as the proposal
  said), OR
- **(b)** Did you actually wire `intent_translator` through
  `competitive_generate` (with a new `"iterate"` task_type added to
  `_DEFAULT_MODELS` in `llm/ensemble.py:58`), OR
- **(c)** Some hybrid?

This affects S16's expected latency profile, error-handling shape, and
prompt-cache hit rate. If (a), the system prompt builder must use
`build_anthropic_system_blocks(stable_str)` for cache hits — confirm S15
does this. If (b), confirm the `tool_schema` (for structured-output JSON
parsing) is wired since the proposed CinemaDirector output is
`{revised_prompt, params_delta, anchor_refs}`.

## Bonus targets (only if you have spare cycles)

These aren't blockers for S16 dispatch — answer if quick, skip if not.

- **B1.** Did S15 add an `"iterate"` entry to `_DEFAULT_MODELS` in
  `llm/ensemble.py`? If yes, what models?
- **B2.** Where does `data/intent_log/{project_id}/{ts}.jsonl` get
  written from — inside `intent_translator()`, or as a wrapper helper in
  `llm/director.py`? S16's `/iterate` endpoint shouldn't have to log
  redundantly; clarifying which layer owns the log line avoids drift.
- **B3.** Did you extend `TakeRecord` with explicit Pydantic fields for
  `intent` / `revised_prompt` / `parent_take_id`, or rely on
  `extra="allow"` to let them ride as untyped extras? The S16 type
  signatures depend on this.

## Scout-report shape expected

Return as a `scout-report`-kind mailbox event, in-reply-to this filename
when it gets a real timestamp. Body shape:

```
Target 1 — TakeRecord linkage field:
  Disposition: (a) | (b) | (c-detail)
  Evidence: <file:line refs from S15 commit>

Target 2 — Intent storage level:
  Disposition: (a) | (b) | (c-detail)
  Evidence: <file:line>

Target 3 — CinemaDirector LLM coordination:
  Disposition: (a) | (b) | (c-detail)
  Evidence: <file:line>

Bonus (if reported): B1 / B2 / B3 dispositions.

Anything else from S15 that affects S16 dispatch shape.
```

Per v5 §S norms: scout-report effort target ≤20 min operator-context-burn.
Pure read, no subagent dispatch needed (single-file grep + commit-body read
suffices).

## Sequencing

S16 dispatch is BLOCKED on scout-report — I want the disambiguation answers
baked into the implementer prompt rather than having the subagent discover
ambiguities mid-task. Don't reorder S15 to wait on this scout-request;
land S15 first, then this scout-request fires, then S16 dispatch.

If S15 lands and your commit body already addresses all 3 targets explicitly
(some operators do this proactively), this scout-request becomes obsolete
on land — I'll archive without sending.

---

Director-seat — drafted 2026-05-25, held pending S15 land
