# Slice 2.5 — Legacy `coordination/` Mailbox Migration (DESIGN SPEC)

> **Status: DESIGN — rev 2 (post adversarial spec-review `wf_f2e4a49a-0b4`; 2 blockers + majors folded in).**
> This is the brainstorming-output design the Slice 2.5 TDD plan is authored from. It supersedes the
> *scope* of the tracking stub
> `docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md`
> by correcting its edit-site inventory (the stub under-counted ~3×) and pinning the migration
> architecture. Identifier: **`threeway-slice2.5-legacy-bus-migration`**. Next free ADR: **ADR-034**.
>
> **All file:line anchors are HEAD `f0b81a61` snapshots — the executor must re-grep at exec time** (they
> drift). **Companions:** spec §8 item 8 "Migration"
> (`docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md:398-400`);
> `DECISIONS.md` ADR-030 / ADR-031 (esp. Decision 8 = the approved deferral of THIS work, Decision 5 =
> cursors local-only); the Slice-2 plan `2026-06-19-cross-provider-seat-topology-slice2.md` (D-B + the
> task/test conventions to mirror); `ARCHITECTURE.md §13A`.

## 1. Goal

Migrate the **live 4-seat campaign mailbox** (`coordination/`, the human-operated markdown bus that
`send-event`/`consume-events`/`check_coordination.py`/`status.py` drive — **768** `sent/*.md` events as of
HEAD) onto the Slice-2 `refs/threeway/events` signed substrate — **without ever creating a
dual-write-authority window** — and in the same migration make **`coordinator`** (today send-only) and a
**new `coordinator2`** first-class *receiving* seats.

This is the deferred half of spec §8: Slice 2 shipped the additive `threeway/` event bus; Slice 2.5 migrates
the live bus the campaign uses right now. Slice 2's gate is green (152 passed, merged at `2a932ac0`→`origin/main`),
so the §11 boundary to **plan** this is satisfied. **This artifact is PLANNING ONLY.**

## 2. Non-goals (YAGNI)

- **No change to the event vocabulary** (`coordination/mailbox/kinds.txt`) and **no new `THREEWAY_KINDS`** —
  legacy events ride the existing `event_sent` carrier kind (§5a), so the threeway vocabulary is untouched.
- **No modification of the EXISTING Slice-2 `threeway/` modules** — `refstore` (`RefEventStore`), `gitcas`,
  `envelope`, `reducer`, `predicate`, `gate`, `tier` are *consumed*, never edited. The slice MAY add the two
  **new, read-only, additive** modules in §5 (`threeway/legacy_projector.py`, `threeway/divergence.py`), which
  only import and call the Slice-2 API.
- **Not Slice 3** — `co_sign_satisfied` returning True for T2/T3 (`threeway/tier.py:32-43`) is out of scope.
- **No remote/multi-host cursor publishing** — `advance_cursor` is local-only by design (ADR-031 Decision 5;
  `threeway/refstore.py:222`). This slice's cursor refs are per-clone local progress.
- **No dual-write bridge** — forbidden; the projector is one-way read-only (§5).

## 3. Approved design decisions

| # | Decision | Chosen | Why |
|---|---|---|---|
| **D1** | Seat-list duplication | **Consolidate (hybrid)** — `protocol_mailbox.py` is the single Python root; every Python script imports it; the 4 shell sites stay hand-synced but are guarded by a token-extraction test asserting shell-list == Python root | The roster lives in ~12 independent copies; consolidation dissolves the recurring Rule #13 hazard into one root + one guard |
| **D2** | What "shadow" writes | **In-memory projection** — the projector builds the projected event SET in memory (no `refs/threeway/events` appends) during shadow; the ref-bus is written **once**, at cutover, via the §5c backfill | Makes "no dual-write authority" *structurally* true (zero ref-bus mutation until cutover); **defers** the O(events²) append cost to the one-time cutover instead of paying it every shadow cycle |
| **D3** | coordinator2 activation | **Wire both fully now** — coordinator→receiver AND coordinator2 as a live send/receive seat; seed coordinator2's cursor at the bus head (zero spurious backlog) | Identical surface work once mapped; matches the documented target-state; half-wiring guarantees a third pass |
| **D4** | Cursor backfill reversibility | **Byte-reversible via committed manifest** — archive original `seen/<seat>.txt` ISO values + the ISO→seq map in `coordination/mailbox/.migration/cursor-backfill.json` | Stub requires "byte-reversible + reproducible from `sent/`"; an archived manifest makes rollback a file restore |
| **D5** | Doctrine prose | **Rewritten in lockstep** — the "coordinator is send-only / no cursor" prose changes in the same tasks as the code | Prose-matches-code is a repo invariant |

## 4. The verified edit-site surface (Rule #13)

The stub named 6 sites; the true surface (grounding `wf_c9162998-703` + review `wf_f2e4a49a-0b4`, both vs HEAD
`f0b81a61`) is below. **The plan must update every live copy or the new seat silently half-breaks.** Excluded
(vendored, regenerate from the live tree): `.claude/worktrees/wf_*/**`, `.claude/skill-eval/**`.

### 4a. Seat-roster copies

| File:line | Symbol | Today | Note |
|---|---|---|---|
| `scripts/protocol_mailbox.py:11-13` | `SEATS`/`SENDERS`/`RECIPIENTS` | 4 seats; coordinator in SENDERS only | **canonical root** → D1 consolidate target |
| `scripts/status.py:126` | `_MAILBOX_SEATS` | 4 (independent copy) | + render `:232`, collect `:347/:352`, subcmd `:503`, help `:484/:506` |
| `scripts/check_coordination.py:51` | `ROLES = SEATS` | imports root | `_check_cursors` (≈`:119-127`) will DEMAND `seen/<role>.txt` once coord enters → FATAL `cursor_missing` |
| `scripts/mailbox_monitor.py:21` | `SEATS` | 4 (independent) | watchboard `:167/:246`, `_read_cursor:80` |
| `scripts/draft_handoff.py:21` | `SEATS` | 5 (incl coordinator, special-cased unpinned `:85-86/:95/:140-141`) | + **separate** inline peer tuple `:118` |
| `scripts/proof_bundle.py:13` | `SEATS` | 5 (incl coordinator, not coordinator2) | |
| `scripts/protocol_capacity.py:13` | `SEAT_ORDER` | 5 (incl coordinator, not coordinator2) | **rejects** a coordinator2-addressed packet `:368/:380` |
| `scripts/codex_protocol_model.py:99-101` | `SEATS`/`DIRECTOR_SEATS`/`OPERATOR_SEATS` | 4 + pair tuples | `_mode_from_seat:503`→coordinator2 to no mode; env whitelists `:147/:152` |
| `scripts/continuation_readiness.py:28` | `SEATS` | 4 | iterated `:86` |
| **`.agents/skills/four-seat-protocol/scripts/seat_status.py:39`** | `SEATS` | 4 | **canonical** (invoked by `proof_bundle.py:12`, `codex_protocol_model.py:315`, `continuation_readiness.py:148`); argparse choices `:218` **rejects** coordinator2; coordinator special-case `:117/:125/:148/:156`; strptime `:61` |
| `.claude/skills/four-seat-protocol/scripts/seat_status.py:31` | `SEATS` | 4 (stale mirror) | skill-local copy; the plan **confirms which the `four-seat-protocol` skill loads** and edits-for-parity OR repoints the skill at the canonical, then drops the stale copy |
| `.codex/hooks/update-state.sh:216-219` | inline `_unread_for` calls | 4 | + STATE.md line `:235` |
| `.claude/hooks/update-state.sh:217-220` | inline `_unread_for` calls | 4 (mirror) | + STATE.md line `:236` |
| `scripts/protocol_effectiveness_report.py:24` | imports `SEATS` | inherits root | coordinator **sender** literals `:620/:630` + seat loop `:782` are independent (receiver coverage) |

### 4b. Seat-alternation regex copies (filename frm/to groups)

| File:line (def) | Today | Risk on coordinator2 |
|---|---|---|
| `scripts/check_coordination.py:56` `_EVENT_NAME_RE` | frm: 4+coordinator; to: 4+all | `-to-coordinator(2)-` → **FATAL** `bad_filename` |
| `scripts/check_coordination.py:79` `_LIVE_SEAT_ARTIFACT_RES` | to: 4+all | falsely flags missing live-seat artifact |
| `scripts/mailbox_monitor.py:25` `_EVENT_RE` | frm/to 4(+coordinator) | event silently **dropped** from monitor |
| `scripts/status.py:53` `_EVENT_RE` | to-group generic `\w+` | **OK** — already matches (no edit for the seat add) |
| `scripts/protocol_effectiveness_report.py:51` `MAILBOX_RE` | recipient group generic `[A-Za-z0-9_]+` | **OK** — already matches; receiver gap is the `:620/:630` sender literals, not this regex |

### 4c. Cursor-format sites (ISO → scalar `seq`)

| File:line | Today | Severity on scalar |
|---|---|---|
| `scripts/check_coordination.py:63` `_CURSOR_RE` | `^\d{4}-..T..:..:..Z$` ISO-only | **HARD FATAL** — gates `cursor_unparseable`; MUST loosen to accept scalar |
| `scripts/status.py:53/:73` (`_EVENT_RE`/`_normalize_ts`) | ISO/dash compare | silent **mis-count** |
| `scripts/mailbox_monitor.py:35` | strptime ISO | unparseable → wrong unread |
| `.agents/.../seat_status.py:61`, `coordination/bin/consume-events:53`, both `update-state.sh` byte-compares | ISO assumed | silent mis-count |

### 4d. Shell whitelist copies (hand-synced; guarded by the D1 sync test)

| File:line | Kind |
|---|---|
| `coordination/bin/send-event:29` FROM case, `:30` TO case | load-bearing whitelists |
| `coordination/bin/send-event:49` | the `Cursor at send:` footer read (`head -1 seen/$FROM.txt`) — not a whitelist |
| `coordination/bin/consume-events:27` ROLE case; `:6/:15` usage strings | load-bearing + usage |
| `scripts/codex_protocol_model.py:147/152` | CODEX_AGENT_ROLE / CODEX_SEAT descriptive whitelists |
| `.agents/.../seat_status.py:218` | argparse choices |

## 5. Architecture — the carrier-event projection

The legacy `kinds.txt` vocabulary (25 human-coordination kinds: `coordination`, `verification-report`,
`status`, `fyi`, `verify-request`, …) is **100% disjoint** from the threeway *governance* kinds
(`brief`/`attestation`/`co_sign`/…) — `reduce()` (`threeway/reducer.py:93`, no `else`) would silently drop
every legacy event. **Therefore the migration does NOT fold legacy traffic through `reduce()`.** It carries
each legacy event as the existing **`event_sent` carrier kind** (already in `THREEWAY_KINDS`,
`threeway/__init__.py:15-23`) — no new kinds, no governance semantics.

### 5a. The legacy→ref projector (new: `threeway/legacy_projector.py`, read-only)

A pure function: read `coordination/mailbox/sent/<ts>-<from>-to-<to>-<kind>.md` → emit `threeway.envelope.Event`
objects. **No `refs/threeway/events` writes.** Per event:

- `kind = "event_sent"` (carrier); the **original** legacy kind, subject (H1), `When:`, `Cursor at send:`
  footer, recipient, and full body bytes go into `payload` (the divergence-check reconstructs the legacy view
  from `payload`, so nothing is lost).
- `sender`/`recipient` from the filename grammar (`check_coordination.py:56` `_EVENT_NAME_RE`); the `all`
  broadcast is preserved as **one** event (never fanned out to 4) so fan-in semantics match.
- **`subject_sha = sha256(source_filename)`** — filenames are unique even within a same-second collision, so
  this makes `idempotency_key` (`envelope.py:97-101` = `sha256(sender:kind:subj:payload_digest)`) **injective**
  over the corpus. Without it, the ~125 same-`(sender,kind)` events with identical bodies (terse `status`/`ack`)
  would collide and the cutover would drop one (set-bijection failure). The plan ships a test that two
  byte-identical same-`(sender,kind)` legacy events **both** land. **Filename uniqueness is the single shared
  load-bearing invariant** under both this injectivity and the §6 total order; the §8 clause #5 set-bijection
  (with the non-empty floor) is the one guard that fails RED if any two `sent/*.md` filenames ever collide.
- **`brief_id = "legacy-import"`** (synthetic) — so all 768 carriers land under `events/legacy-import/<id>.json`,
  a dedicated tree namespace, rather than the `events/None/` directory a `None` brief_id would produce
  (`refstore.py:138`); event-id uniqueness keeps the per-event paths distinct.
- **Signing:** carrier events are signed by a designated **migration-importer identity**. `event_sent` is
  **NOT** load-bearing (`threeway/__init__.py:26-31`), so the gate's `verify_and_reduce` never reads a carrier's
  signature/signer (`gate.py:38`) — the importer identity needs **no** `PublicKeyRegistry` entry, any
  reproducible importer key is acceptable, and a carrier structurally **cannot** masquerade as a governance
  attestation (the gate skips it). §8 clause #8 pins this.

### 5b. The divergence-check (new: `threeway/divergence.py`, read-only)

Compares the projected event SET against the live legacy mailbox — **on the raw set, never `reduce()`/
`EffectiveState`** — and asserts zero drift. Compared fields (the reconciliation contract):

1. **event SET bijection** — `sent/*.md` count + identity-set ↔ projected event-set, with a **non-empty floor**
   (`projected count == live sent count` — currently 768; guards the degenerate-empty vacuity and the Slice-2
   id-overwrite class where two events shared an id).
2. `from`, `to` (incl. `all` preserved), the original `kind`, `subject`, `When:`, `Cursor at send:`, body bytes
   (all from `payload`), and the filename `ts`.
3. **filename ↔ envelope self-consistency** (filename from/to/ts == in-file `**From:**`/`**When:**`).
4. **per-seat cursor + derived unread** — for every seat, the legacy `seen/<seat>.txt` high-water mark and its
   strictly-greater-than unread count == the projection's consumed-seq and `seq>cursor_seq` unread count
   (using the §6 total order so the equivalence is exact).

### 5c. Cutover — the single authoritative write (768 sequential appends, then one authority-flip)

After ≥1 full shadow cycle at zero divergence + a one-pair canary:

1. **Fail-closed pre-check:** `preflight_bus_init(repo, force=False)` (`threeway/gitcas.py:231`) — raises
   `BusInitRefusedError` over any pre-existing `refs/threeway/*`, never deletes a ref. `force=True` is **only**
   an explicit operator acknowledgement and it **short-circuits** (no enumeration, no remote check — `gitcas.py:240-241`);
   it is **not** the writer and guards nothing on its own.
2. **Backfill:** `RefEventStore.append()` each of the 768 carrier events in the §6 total order. This is **768
   non-atomic CAS appends**, not one atomic write — so define the failure semantics: on any append failure
   (e.g. an unexpected idempotency collision), **tear down the partial `refs/threeway/events` prefix** (or mark
   the bus not-yet-authoritative) so no reader sees a half-backfilled bus.
3. **Cursor backfill** (§6) for all 6 seats.
4. **Authority flip = one explicit act** (a doctrine/marker commit) that happens **only after all 768 appends +
   6 cursor backfills succeed**. Before that act, legacy `sent/` is authoritative; after it, the ref-bus is, and
   legacy `sent/` is retained read-only (§5d). There is no implicit "from here the ref-bus is authoritative."

### 5d. Rollback

- **Pre-cutover:** legacy stays authoritative + untouched during shadow → rollback = stop reading the projection.
- **Post-cutover:** **legacy `sent/` is RETAINED read-only as the rollback source** (not regenerated). The
  forward projector is lossy w.r.t. exact markdown framing, so we do *not* claim byte-regeneration; rollback =
  re-designate the retained `sent/` tree authoritative + restore the cursor manifest (§6). This keeps rollback
  honest and trivially verifiable.

## 6. Cursor model (ISO → scalar `seq`)

- **Total order (deterministic):** events are projected to `seq` in `(filename ts, full filename)` order —
  filenames are unique even within a same-second collision (the live tree has 13 events in same-second groups),
  so the order is total and reproducible. Every downstream cursor claim depends on this single order.
- **Backfill:** each seat's ISO high-water cursor (`seen/<seat>.txt`) → the **highest `seq` whose event ts ≤ the
  ISO cursor** under the total order. An ISO cursor with no event at-or-before it → `seq 0` (matches
  `advance_cursor`'s `seq==0` allowance, `refstore.py:240`). Materialize `refs/threeway/cursors/<seat>` via
  `advance_cursor(seat, seq)` (monotonic CAS, `refstore.py:222`).
- **Reversible manifest:** `coordination/mailbox/.migration/cursor-backfill.json` archives original ISO values +
  the ISO→seq map (recomputable purely from `sent/*.md` + the total order). Restoring it rewrites `seen/*.txt`
  byte-for-byte.
- **Regex loosening:** `check_coordination.py:63` `_CURSOR_RE` accepts a scalar `seq` (transitionally also ISO);
  the other cursor parsers (§4c) updated in lockstep — **all in Phase C, atomically**.
- **Phase ordering (critical):** coordinator/coordinator2 cursor files are seeded in **Phase A** using the **ISO
  format** (the un-loosened `_CURSOR_RE` is ISO-only, so a scalar seed would be instant `cursor_unparseable`
  FATAL). The scalar-seq conversion of **all** cursors happens in **Phase C**, in the same change as the regex
  loosening — no intermediate commit ever has a scalar cursor under an ISO-only regex.
- **Atomicity:** the coordinator/coordinator2 cursor files are seeded in the **same task** that adds them to
  `ROLES`, else `_check_cursors` raises `cursor_missing` FATAL the instant they enter the roster.

## 7. coordinator / coordinator2 → receivers

Two edit classes (per grounding):

- **coordinator (send-only → receiving):** *remove* the scattered send-only special-casing — the
  `check_coordination.py:53-55` comment + `_check_cursors` exemption, `draft_handoff.py:85-86/:95/:140-141`,
  `.agents/.../seat_status.py:117/:125/:148/:156`, `consume-events:27` (not consumable), `send-event:30` (not a
  valid TO) — add coordinator to RECIPIENTS, consuming ROLES, the to-alternations, and seed `seen/coordinator.txt`.
- **coordinator2 (new):** add to every roster tuple, every frm+to alternation (§4b), every FROM/TO/ROLE
  whitelist, every argparse `choices`, the `codex_protocol_model.py` mode resolvers (so `CODEX_SEAT=coordinator2`
  binds), and seed `seen/coordinator2.txt` at the bus head. Closes the gap `docs/protocol/threeway/CODEX-ADOPTION.md:112` flagged.

`self`-address stays refused (`send-event:31`): coordinator→coordinator2 allowed; coordinator→coordinator not.

## 8. Acceptance gate (each clause → a named observable + a single-fact mutation; ADR-028 zero-ceremony)

1. **Roster completeness — BEHAVIORAL, not grep-for-literal.** For each importable Python site, `import` the
   module and assert its live roster object **equals** the `protocol_mailbox` root incl. coordinator2
   (e.g. `set(status._MAILBOX_SEATS) == set(protocol_mailbox.RECEIVING_SEATS)`). For non-importable sites
   (regexes, shell case-arms, argparse `choices`), drive a **coordinator2-addressed input through the real entry
   point** and assert ACCEPT (a `-to-coordinator2-` filename passes `_EVENT_NAME_RE`; `seat_status.py coordinator2`
   is accepted). **Mutation:** drop coordinator2 from one real tuple/arm → the import-compare or accept-test flips
   RED. A comment/docstring occurrence must NOT satisfy the check. (The importable-module set is a curated
   registry; the plan lists it explicitly.)
2. **Shell↔Python sync guard — token extraction.** Parse the actual FROM/TO/ROLE **case-arm tokens** (not whole
   file text) from `send-event`, `consume-events`, the two `update-state.sh`, and assert the extracted set == the
   `protocol_mailbox` root. **Mutation:** drop coordinator2 from the `send-event` TO case-arm only (leave it in
   the usage string) → guard goes RED (proves it reads the load-bearing arm).
3. **Legacy checkers stay green WITH staged coord/coord2 traffic.** Place a real `-to-coordinator2-` envelope in a
   fixture mailbox + a seeded `seen/coordinator2.txt`, run `check_coordination.py`/`status.py`, assert exit 0 AND
   no FATAL lines. **Mutation:** remove coordinator2 from `_EVENT_NAME_RE` (or delete the seeded cursor) → checker
   FATALs (`bad_filename`/`cursor_missing`). A bare exit-0-on-current-tree assertion is disallowed (it passes today).
4. **Divergence zero-drift on the raw event SET.** Assert the §5b field-level contract over a full projected
   cycle, with the **non-empty floor** (`projected count == live sent count`). **Mutation:** perturb one event's
   `to`/body → a field-drift is reported RED.
5. **Reconciliation set-bijection at three points (distinct from #4).** legacy `sent/*.md` set == projected
   event set == post-backfill `index/<seq>` set on `refs/threeway/events`. **Mutation:** drop or duplicate one
   `sent/*.md` before projection → the three-way bijection breaks RED.
6. **No dual-write — pinned observable.** Snapshot `before = gitcas.rev_parse(repo, EVENTS_REF)`, run a full
   shadow projection, assert `gitcas.rev_parse(repo, EVENTS_REF) == before` (unchanged/None). Belt-and-suspenders:
   monkeypatch `gitcas.push_cas` **and** `gitcas.cas_create_or_update_ref` to raise, run shadow, assert it
   completes without raising. **Mutation:** make the projector call `append()` once → both checks flip RED.
7. **Cursor backfill — split.** **7a (byte-reversibility):** clean manifest restore round-trips `seen/*.txt`
   byte-for-byte; **mutation:** flip one byte of an archived ISO value → restored file ≠ original → RED.
   **7b (map reproducibility):** recompute ISO→seq purely from `sent/*.md` + the §6 total order, assert it equals
   the archived map; **mutation:** perturb one event's ts so its seq bucket changes → recomputed map diverges → RED.
8. **Fail-closed init + carrier verification bypass.** (a) Create `refs/threeway/events`, call
   `preflight_bus_init(force=False)` → raises `BusInitRefusedError`; assert the ref still resolves afterward
   (non-destructive); reuse the existing `tests/unit/test_threeway_preflight.py` shape. (b) A carrier event
   (`kind="event_sent"`) signed by a **non-registered** migration-importer key still passes
   `verify_and_reduce` (it is not load-bearing). **Mutation:** add `event_sent` to `LOAD_BEARING_KINDS` → the
   gate now demands a registered signer and raises RED — proving carriers bypass governance verification today.
9. **Smoke + ceremony (repo-doctrine gates, layered on the five stub/carrier clauses #3/#5/#6/#7/#8).**
   `scripts/ci_smoke.py` OK; `scripts/check_no_ceremony.py` clean (zero xfail/skip/importorskip; the suite needs none).

## 9. Phasing (additive-safe first; the breaking cursor change behind the shadow)

- **Phase A — additive seat wiring (backward-compatible, safe on a live bus):** D1 consolidation; add
  coordinator/coordinator2 to every roster/alternation/whitelist/argparse; seed `seen/coordinator.txt` +
  `seen/coordinator2.txt` **in ISO format** (Phase-A predates the regex loosening); rewrite the send-only
  doctrine prose. Existing 4 seats byte-unaffected; no in-flight send/consume can break.
- **Phase B — projector + divergence-check (read-only, zero bus writes):** build `legacy_projector` +
  `divergence`; run shadow ≥1 cycle to zero drift; canary one pair.
- **Phase C — cursor migration + cutover (the only risky write):** loosen `_CURSOR_RE` + the other cursor
  parsers and convert all cursors ISO→scalar **atomically**; reversible manifest; the §5c cutover
  (preflight → 768 appends → 6 cursor backfills → single authority-flip act), reverse path = retained `sent/`.

## 10. Live-bus safety & risk

Edits the `coordination/` bus the live 4-seat campaign uses **while seats are active**. Mitigations: Phase A is
purely additive; no dual-write authority at any point (D2 makes it structural, clause #6 makes it testable);
shadow is in-memory read-only; the cutover is 768 non-atomic appends with explicit teardown-on-failure and a
single post-success authority-flip; rollback is the retained read-only `sent/` + the reversible cursor manifest;
execution (a separate later session) runs when bus activity is quiet and re-anchors on git refs before every
action (`env -u GIT_INDEX_FILE` on git-touching tests; expect `git status`/`diff` to lie under peer activity —
verify against `git show HEAD:<path>`).

## 11. Tech & conventions (mirror the Slice-2 plan)

TDD tasks (RED test → verify FAIL → GREEN impl → verify PASS → commit), grouped into sequentially-dependent
chunks with a no-commit chunk-close verification task; tests `tests/unit/test_threeway_*.py` with inline fixtures
(no shared conftest), run `env -u GIT_INDEX_FILE .venv/bin/python -m pytest <path> -q`; non-vacuity by single-fact
mutation that flips the outcome (each pinned in §8); explicit-pathspec commits, one per task, `Co-Authored-By`
trailer; ADR-034 + `ARCHITECTURE.md §13A` + `DECISIONS.md` doc-sync in the final chunk (re-anchor all file:line
refs against the then-current HEAD). **PLANNING ONLY** — execution is a separate later session
(subagent-driven-development, Opus) gated on user sign-off of the plan.

---
*Authored 2026-06-20 from grounding `wf_c9162998-703` (5 Opus readers) + adversarial spec-review `wf_f2e4a49a-0b4`
(4 Opus critics; 2 blockers + 4 majors folded into rev 2), verified against HEAD `f0b81a61`. Supersedes the stub's
edit-site inventory (~3× under-count). Decisions D1/D2/D3 + reversibility + doctrine-lockstep user-approved. The TDD
plan is authored from this spec via `superpowers:writing-plans`.*
