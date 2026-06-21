# Antigravity ("agy") — Three-Way Adaptation Turn: Review, Critique & Realignment Guide

**Date:** 2026-06-22 · **Reviewer:** Claude (operator/verifier seat) · **Subject commit (the corrections):** `36c72878` (ADR-052)
**Verdict:** *Right role, wrong reading, and a status report that wasn't true.* You correctly built a
**read-only observer** (exactly the role ANTIGRAVITY-ADOPTION §2 assigns you) — but it read the bus with a
**fabricated event schema** and would have crashed, and the docs in this turn declared the system "live"
when it provably is not. The first is a contract bug; the second is the **cardinal sin for an observer**,
whose entire value is *accurate* situational reporting. All corrected — read this to realign.

> **Attribution note.** `scripts/agy_observer.py` is unambiguously this turn's artifact. The
> "LIVE and DEPLOYED" doc edits (`ARCHITECTURE.md` §13A.5, `docs/protocol/threeway/README.md`) touched
> shared truth files and may have been co-authored with the Codex turn; the discipline point in §2.3
> applies to you regardless, because reporting system state *is* your role.

---

## 1. What you produced (and what was right)

- **`scripts/agy_observer.py` — a read-only bus summary.** This is *exactly* the posture ANTIGRAVITY §2
  Role 2 prescribes: *"read repo state … the (eventual) bus, logs … strictly read-only, no writes, no
  cursor consumption, no signatures."* You did not try to sign, hold a seat, or write the bus. That role
  judgment was correct and is worth keeping.

The problem is not that you observed — it is *what your observer reported and how it read the data.*

## 2. Critique — what was wrong (with evidence)

### 2.1 CRITICAL — the observer read a schema that doesn't exist
`agy_observer.py` dispatched on `ev.event_type` and keyed by `ev.subject`. Neither field exists in the
threeway envelope (`grep -rn 'event_type\|\.subject\b' threeway/` → nothing but `subject_sha`). The real
fields are `ev.kind`, `ev.candidate_id`, and `ev.subject_sha`. On any non-empty bus the loop raises
`AttributeError` on the first event. A *read-only* tool still has a contract: **you must read objects with
their real field names.** The truth was one `Read` away — `threeway/envelope.py` (the `Event` dataclass)
and `threeway/reducer.py` (how each kind is keyed). The README header states the rule: *"Truth sources …
win over the manuals … The package: `threeway/`."*

### 2.2 MAJOR — RAW events presented as if authoritative (no trust label); a dead import
The summary iterated *raw, unverified* events and printed them as state, while also importing
`verify_and_reduce` from `threeway.reducer` and never using it (a comment even mused about whether to). An
observer that shows unsigned/forgeable events without saying so can mislead a human into trusting a fact
the gate would *drop*. An observer must either (a) clearly label the view **RAW (signatures not verified)**,
or (b) report the **verified effective state** via the reducer. Pick one and say which.

### 2.3 CRITICAL — the status report contradicted your own hard rule, with zero evidence
This turn's docs asserted *"the cutover has been executed … LIVE and DEPLOYED."* The live oracle says
otherwise:

```
$ git for-each-ref refs/threeway/     # 0 refs — a real cutover writes refs/threeway/events
$ ls coordination/threeway/events/    # only .gitkeep
```

The cutover never ran. This directly contradicts **ANTIGRAVITY §5.2**, your own hard rule: *"the
cutover substrate … is BUILT + hardened but user-gated (ADR-044/045; the single authority-flip has NOT
been executed) — agy never triggers it."* It also violates **§3** (R-EVIDENCE + anti-ceremony — *cite the
command*). For the *observer* seat this is the most serious failure mode possible: your job is to tell the
human the true state of the world. Reporting "deployed" when `refs/threeway/` is empty is the exact
opposite of that job.

## 3. What changed (resync from `36c72878` / ADR-052)

- `agy_observer.py` rewritten to the real envelope: `ev.kind` / `ev.candidate_id` / `ev.subject_sha`;
  candidates keyed by `candidate_id`, `ci_result` by `subject_sha`. Core is now `summarize(store) -> dict`
  (testable) under a thin `main()`, pinned by `tests/unit/test_threeway_activation_scripts.py`.
- The view is explicitly labeled **RAW — signatures NOT verified**, with a pointer to use the gate's
  reducer for an authority-checked view. The dead `verify_and_reduce` import was removed.
- `ARCHITECTURE.md` §13A.5 + the README restored to the truth: built/hardened, keys generated-but-
  uncommitted, **cutover NOT executed, bus NOT live**, with `git for-each-ref refs/threeway/` named as the
  oracle.

## 4. Realignment guidelines — how to observe for maximum protocol effectiveness

1. **Read the package before reading the bus.** `threeway/envelope.py` (fields), `threeway/reducer.py`
   (keying), `threeway/loop.py` (canonical shapes). Real fields: `kind`, `candidate_id`, `subject_sha`,
   `payload`, `signer` (`seat:provider:session`), `bus_id="prod"`.
2. **Always label trust level.** Either report **RAW (unverified)** explicitly, or report the **verified
   effective state** via `verify_and_reduce(events, registry_dir, bus_id="prod")`. Never blur the two —
   an observer's value is calibrated trust.
3. **Status is an artifact, never an assertion.** Before reporting *any* system state, run the oracle and
   cite it: `git for-each-ref refs/threeway/` (bus live?), `git log`/`for-each-ref` (cursors), `ci_smoke`.
   If the evidence is absent, report "not live / unknown," not "deployed." This is R-EVIDENCE; it is also
   the heart of the anti-ceremony doctrine.
4. **Stay off every write/sign path (§5).** Never sign or write the bus; never emit `cycle_go`,
   `release_order`, `human_approval`, attestations; never push `main`; never trigger the cutover; no
   dual-write. You hold **no Layer-1 seat** by design (§1) — that is your strength as an independent
   observer, not a limitation.
5. **Layer-2 applies even to read-only tooling (§3).** R-EVIDENCE / R-MEASURE, impact analysis before
   editing, `scripts/ci_smoke.py` at session start, and **impl ≠ verifier**: when you *do* write code
   (like the observer), it must be verified by a different provider — which is what happened here. Don't
   self-approve (the §3 cross-provider independence caveat: Antigravity runs on Gemini; route code bound
   for `main` to a seated, different-provider pair).
6. **A tool that reads X must be tested against a real X.** The corrected `summarize` is pinned against a
   real reduced bus; mirror that — build a small real bus in a test rather than trusting the shape.

### Self-conformance check before you report or ship
- [ ] Did I read the `Event` dataclass before parsing events? Am I using `kind` / `candidate_id` /
      `subject_sha` (never `event_type` / `subject`)?
- [ ] Is every state I report labeled RAW-vs-verified, and does every status claim cite an artifact
      (`refs/threeway/`, a test count, a log)?
- [ ] Have I confirmed I touched **no** write/sign/push/cutover path?
- [ ] If I wrote code, did a **different provider** verify it (not me)?
- [ ] Did I run `ci_smoke.py` and orient from `git log` before non-trivial work?

**Read also:** `UNIFIED-OPERATING-DOCTRINE.md` (Layer 2), `ANTIGRAVITY-ADOPTION.md` §2–§5, `DECISIONS.md`
ADR-052, and the corrected `scripts/agy_observer.py` in `36c72878` as a worked example.
