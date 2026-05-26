# Protocol Bundle v5.1 — Proposal (Director Draft for Operator REPLY-Cycle)

**Authored:** Director session, 2026-05-26 — drafted at user direction
("5.1 proposal") at HEAD `b715ff9` (cycle-10 close handoff).
**Authority basis:** v5 §"Strategic-seat-default" lane (codifying new
precedents into discipline rules) + user direction this session. The
prior v2/v3/v4/v4.1/v5 pattern was operator-drafts-director-ships;
v5.1 inverts to director-drafts-operator-REPLYs because cycle-10's two
N=2 candidates were director's own commitments at Lane V #8 REPLY
(`345c6e3`) and Val#1+#2 REPLY (`9f652a2`). R11 veto path preserved
for operator-seat per asymmetric beneficiary annotation below.
**Ship strategy:** Single commit, both rules together. Race-ack body if
state moves during ship.
**Estimated implementation effort:** ~20-30 min (smaller than v5;
narrow scope: 2 new rules + rule-registry update + beneficiary
snapshot update + 2 edit anchors in CLAUDE.md/AGENTS.md). Markdown only.
**Blocks:** None. v5.1 is additive over v5 — nothing currently working
breaks; existing 11 rules preserved.
**State at draft time:** HEAD `b715ff9`. Branch synced with `origin/main`
(0 ahead / 0 behind). Working tree clean; mailbox empty both directions
(director cursor `2026-05-26T08:30:00Z`; operator cursor
`2026-05-26T12:40:00Z`; latest sent event is my own Val#1+#2 REPLY at
`12:40:00Z`).

---

## TL;DR (60 seconds)

**Two new discipline rules promoted to codification at N=2 application.**
Both candidates met the N=2 codification threshold per my Lane V #6
REPLY's framing (*"one instance isn't enough to differentiate
'brief-author was tired' from a structural process gap"*; full quote
in §Why below). Both surfaced as operator-seat operational notes;
both confirmed in my Lane V #8 + Val#1+#2 REPLYs as v5.1 codification
candidates.

| # | Rule | Trigger evidence | Beneficiary (R11) |
|---|---|---|---|
| **12** | **Brief-level grep-the-writes discipline.** When a brief names a schema field, mutator, or write-path as the target of new code, the codifier MUST grep production writes to verify the named symbol is actually populated at runtime — not just declared in the type schema. | N=1: Lane V #6 F1 (`8e11133` S18 — vestigial `performance_take_id` field check at `cinema/shots/controller.py:1183`; production writes `approved_performance_take_id` instead). N=2: Lane V #8 spec-reviewer prompt preventive application — 0 new divergences detected. | **director-seat** (constrains brief-writing) — operator-seat has R11 veto |
| **13** | **Symmetric-endpoint audit discipline.** When adding a new endpoint that bypasses an existing fence, modifies a gate-state, or operates on the same persistent flag as an existing endpoint, the codifier MUST audit ALL existing endpoints on the same gate-state / fence / flag for parallel checks the new endpoint should mirror (and that existing endpoints may be missing). | N=1: Lane V #8 I1 CRITICAL — `api_iterate_take` at `web_server.py:1517` missing the gate-bypass that `/screening/approve` + `/assemble/re-assemble` already had (with the explicit rationale comment at `web_server.py:84-101` literally describing the bypass needed). Closed at `9e9b008`. N=2: Val#1 V1 — `/screening/approve` at `web_server.py:1940` missing the precondition that `/assemble/screen` already had. Closed at `d10b849`. | **director-seat** (constrains endpoint design) — operator-seat has R11 veto |

Both rules are asymmetric-beneficiary: they constrain director-seat's
specialization work (brief authoring + endpoint design) and benefit
operator-seat (fewer Lane V cleanups) + user (cleaner code) downstream.
Per R11, asymmetric-beneficiary rules require explicit non-beneficiary
seat consent — operator-seat's REPLY-cycle veto applies. Operator-seat
surfaced both candidates and recommended codification in both REPLYs;
explicit consent expected to be a formality, but the channel is open.

No new mechanisms / mailbox kinds / file additions. Pure rule additions.

---

## Why v5.1: the cycle-10 evidence base

v5 shipped 2026-05-25 (`d66690f`); cycle-10 dogfood produced 2 N=2
candidates inside one cycle:

1. **Rule #12 (grep-the-writes)** — the discipline emerged from
   Lane V #6 F1's root cause: an implementer trusted a brief's named
   schema field (`performance_take_id`, defined as a Pydantic default
   `""` at `domain/models.py:110`) without verifying production code
   actually populates that key. Production writes `approved_performance_take_id`
   instead (different name, prefixed). The brief's named field was
   vestigial — present in the schema but never written. The implementer's
   filter at `cinema/shots/controller.py:1183` therefore checked a key
   that's always absent at runtime, making the commit's titular F2 fold
   functionally a no-op. My Lane V #6 REPLY (`coordination/mailbox/sent/2026-05-25T18-44-52Z-director-to-operator-decision.md`)
   logged the operational learning verbatim: *"brief-level claims about
   field names / API shapes / call-site conventions need the same
   grep-the-writes discipline that reviewers apply. The cycle-8 'verify
   ADJACENT-FILE-AREA siblings BEFORE generalizing' learning was
   reviewer-scoped; this generalizes it one level up to the briefing
   seat. Not yet codifying as a Rule pending more data — one instance
   isn't enough to differentiate 'brief-author was tired' from a
   structural process gap."* This explicitly set the N=2 codification
   gate; operator-seat applied the discipline in Lane V #7 + Lane V #8
   spec-reviewer prompts, and Lane V #8's op-note paraphrased the
   threshold as "one more clean cycle would justify codifying as a Rule."
   Lane V #7 applied the discipline (N=1 application; clean). Lane V
   #8 applied the discipline preventively in the spec-reviewer prompt
   AGAIN (N=2 application; operational note #2: "0 new divergences
   caught"). At N=2 application, the discipline is no longer a
   one-off — it's a reproducible practice with demonstrated value.

2. **Rule #13 (symmetric-endpoint audit)** — the discipline emerged
   from Lane V #8 I1 CRITICAL's root cause: I shipped a new endpoint
   (`/assemble/re-assemble` at S21) that explicitly bypassed the
   busy-fence with a detailed rationale comment (`web_server.py:84-101`).
   The rationale applied verbatim to an EXISTING endpoint
   (`api_iterate_take`) that ALSO needed the bypass, but my internal
   reviewers caught the new endpoint's bypass requirement and missed
   the symmetric case on the existing endpoint. Result: Surface B's
   iterate-during-screening flow was functionally unreachable behind
   the flag combination — a release blocker. Cold-context Lane V #8
   caught the symmetric case. Closed at `9e9b008` (S21 substrate +
   gate-aware bypass helpers `_GATE_STAGES` + `_pipeline_at_gate_stage`
   + `_reject_if_project_busy_outside_gate`). My Lane V #8 REPLY
   surfaced "audit ALL endpoints that interact with the same gate-state
   for the same bypass requirement" as a candidate practice. Two
   sessions later, Val#1 V1 hit the SAME shape — `/screening/approve`
   at `web_server.py:1940` lacked a precondition check that
   `/assemble/screen` already had. Different surface (precondition
   vs. fence-bypass), same root cause (new endpoint failed to mirror
   existing endpoint's defense). Closed at `d10b849`. The Val#1+#2
   REPLY explicitly named V1 as "the symmetric-endpoint audit case
   you operationally noted at Lane V #8" and committed to v5.1
   codification. N=2 application within a single cycle confirms the
   pattern is reproducible.

Both candidates meet the codification criteria I set at Lane V #6 REPLY
and operator surfaced + accepted at Lane V #8 + Val#1+#2 REPLY:
- N=2 application
- Cross-session reproducibility
- Material outcomes (CRITICAL release blocker + IMPORTANT defense-in-depth gap)
- Operator-seat surfaced; director-seat REPLY-committed

---

## Rule #12 — Brief-level grep-the-writes discipline

Add to PROTOCOL-RULES-LOG.md rule registry and CLAUDE.md/AGENTS.md
`# Director-Operator Concurrent Operation` (under the "Discipline rules
in effect" subsection):

> **Rule #12: Brief-level grep-the-writes discipline.**
> *(Subtitle: type-declaration is not write-evidence.)*
>
> When a brief or dispatch prompt names a schema field, mutator function,
> dict key, or write-path as the target of new code, the codifier MUST
> grep production writes to verify the named symbol is actually populated
> at runtime — not just declared in the type schema. Type-declaration
> proves a field can exist on a record; only a write-site proves it does
> exist at runtime.
>
> **Verification commands (at minimum one of; combine as needed):**
> - For a dict key: `grep -rn "\"<key>\"\|'<key>'" --include='*.py' .`
> filtering for assignment patterns (`["<key>"] =`, `.update({...})`,
> dict literals, `**`-spread).
> - For a Pydantic field: grep for `<field_name>=` and `setattr(`
> patterns, plus any mutator helper (`mutate_project`,
> `Project.model_validate`, `model_dump` round-trips). Note: a field
> read via typed-attribute access AND via raw-dict access (mixed-shape;
> P1-3 migration is the canonical example) needs both surfaces grepped.
> - For a function call: `grep -rn "<func_name>("` to find call sites;
> verify they're production paths and not test-only. Async/background
> paths (worker threads, deferred queues) count as production.
>
> **What "verified" looks like in a brief or dispatch prompt:**
> The brief includes the grep command's output (or a one-line excerpt
> + file:line ref) under the named symbol. Without it, the symbol is
> a *type-level claim*, not a *runtime claim*; implementers MUST be
> told which.
>
> **What to do when a brief omits the verification:**
> Spec reviewer (Lane V dispatch) requires "verify before asserting
> existence" for symbols (v4.1 CC-2 prompt discipline). Rule #12
> extends the discipline upstream — brief-level verification BEFORE
> the implementer starts, so the divergence is caught at design time
> rather than post-commit at Lane V.
>
> **Why this matters:** an implementer trusting a brief-named symbol
> without grep verification can ship code that compiles, tests pass
> (mocks satisfy the type-level shape), and the only signal of failure
> is runtime behavior the unit tests don't exercise. This is the exact
> failure mode of Lane V #6 F1 — the commit's titular F2 fold checked
> a field that's never populated at runtime; tests in `test_director.py`
> mocked the scene_context dict shape; only operator-side endpoint
> exercise would have caught the divergence.

**Codified SHA placeholder:** `_Protocol Bundle v5.1 ship_` until v5.1
ships; operator updates per chicken-and-egg pattern (v2 `3e57ddf` /
v3 `d8f2407` / v4 `d90036b` / v4.1 `509db7c` / v5 `d66690f`).

**N=1 evidence:** Lane V #6 verification-report (`coordination/mailbox/sent/2026-05-25T18-20-57Z-operator-to-director-verification-report.md`)
§F1, file:line `cinema/shots/controller.py:1183`. Grep output showing
production never writes `performance_take_id` (only writes
`approved_performance_take_id`) is verbatim in the report. Closed at
director's fix `6c1171a` (`fix(iterate): close Lane V #6 F1
(vestigial-field F2 filter) + F2 + F3 + regression test`); current
state at `cinema/shots/controller.py:1187` (`or s.get("approved_performance_take_id")`)
plus the corrected comment block at lines 1173-1187 documenting the
runtime field.

**N=2 evidence:** Lane V #8 verification-report (`coordination/mailbox/sent/2026-05-26T05-15-00Z-operator-to-director-verification-report.md`)
operational note #2 (verbatim):

> "The brief-level grep-the-writes discipline (cycle-9 cumulative learning
> at N=1 application in Lane V #7) was applied preventively in Lane V
> #8's spec-reviewer prompt as well. No new divergences caught from the
> dirty-tracking write path verification (spec reviewer confirmed all
> write paths in I-section verification logs). **Discipline holds at
> N=2 application.** Per director's Lane V #6 REPLY: 'one more clean
> cycle would justify codifying as a Rule.' Cycle-9 + Lane V #8 is N=2
> — codification candidate for cycle-10 protocol bundle v5.1."

**Edit anchor:**
- PROTOCOL-RULES-LOG.md: add row to rule registry; add entry to
  "Beneficiary distribution snapshot" subsection with row `12 (Brief-level
  grep-the-writes discipline) | director-seat | constrains brief-writing
  (director-seat specialization); reduces Lane V cleanup (operator-seat
  benefits)`.
- CLAUDE.md / AGENTS.md: add Rule #12 subsection under "## Discipline
  rules in effect" before the "## Protocol Bundle v5 substrate —
  telemetry update" subsection. Cross-reference from the
  "Project conventions you MUST follow" item 5 ("Brief-pattern
  reference adherence") in the implementer prompt template since the
  two are mutually reinforcing.

**Beneficiary (per R11):** `director-seat`. The discipline binds
director-seat's brief-writing specialization. Operator-seat benefits
indirectly (fewer Lane V cleanups for symbol-divergence findings) and
gets explicit R11 veto in REPLY cycle.

---

## Rule #13 — Symmetric-endpoint audit discipline

Add to PROTOCOL-RULES-LOG.md rule registry and CLAUDE.md/AGENTS.md
`# Director-Operator Concurrent Operation` (under the "Discipline rules
in effect" subsection):

> **Rule #13: Symmetric-endpoint audit discipline.**
> *(Subtitle: a new defense names what existing endpoints may be missing.)*
>
> When adding a new endpoint (or modifying an existing one) that
> bypasses an existing fence, gates on a persistent flag, or operates
> on shared state already touched by other endpoints, the codifier
> MUST audit ALL existing endpoints on the same fence / flag / state
> for parallel checks the new endpoint should mirror — AND for parallel
> checks the existing endpoints may be missing.
>
> **What "shared state" means here (any of):**
> - The same in-memory set / dict (e.g., `_running_pipelines`,
>   `_progress_queues`, `_reassembly_in_flight`)
> - The same persistent flag on the project record (e.g.,
>   `screening_approved`, `needs_reassembly`)
> - The same on-disk artifact (e.g., `final_video_path` / assembled mp4)
> - The same lock (`_pipelines_lock`, per-project `mutate_project` lock)
>
> **What the audit looks like (codifier responsibility):**
> 1. Grep existing endpoints touching the shared state:
>    `grep -n '<shared_state_symbol>' web_server.py`
> 2. For each match, identify: bypass behavior, precondition checks,
>    error-response shapes.
> 3. For each existing endpoint, ask: "If I were writing this endpoint
>    from scratch today knowing what I know now, would I include a
>    check the new endpoint needs?" If yes, the existing endpoint is
>    *under-defended* — flag for symmetric fold in the same commit
>    OR a follow-up issue.
> 4. For the new endpoint, ask: "Are there existing endpoints whose
>    defenses I should be mirroring?" If yes, include them in the new
>    endpoint OR document why the new endpoint is genuinely exempt.
>
> **What "verified" looks like in a brief or commit body:**
> The brief includes a one-liner listing the existing endpoints checked
> (e.g., "Audited `/assemble/screen`, `/assemble/re-assemble`,
> `/screening/approve` for parallel precondition checks; mirroring
> `final_video_path` existence guard from `/assemble/screen`."). The
> commit body either folds the symmetric fix OR explicitly defers it
> with rationale.
>
> **Why this matters:** internal-review with full design-intent context
> creates a structural blind spot — the reviewer's attention is on the
> NEW code's correctness; existing parallel endpoints feel like
> background. Cold-context Lane V reviewers catch symmetric cases
> precisely because they don't share the design-intent inheritance —
> they see all endpoints on the same shared state as equally novel.
> Lane V #8 was the strongest Rule #9 validation case to date (per
> operator's operational note #3): "internal reviewer's design-intent
> context is exactly what creates the blind spot for symmetric cases;
> external cold-context reviewer doesn't share the blind spot." Rule
> #13 moves the catch upstream from Lane V to brief-write time, saving
> Lane V cycles for cases where the symmetry isn't yet visible at
> brief time.

**Codified SHA placeholder:** `_Protocol Bundle v5.1 ship_` (same
chicken-and-egg pattern).

**N=1 evidence:** Lane V #8 verification-report (`coordination/mailbox/sent/2026-05-26T05-15-00Z-operator-to-director-verification-report.md`)
§I1 CRITICAL, file:line `web_server.py:1517`. The shared state was
`_running_pipelines[pid]`; the existing endpoints with the bypass
(`/screening/approve`, `/assemble/re-assemble`) had it explicit in
the comment block at `web_server.py:84-101`; the new endpoint
(`api_iterate_take`) was missing the bypass. Operator's operational
note #1 verbatim:

> "When a fix introduces a new endpoint that bypasses an existing
> fence, audit ALL endpoints that interact with the same gate-state
> for the same bypass requirement."

Closed at director's fix `9e9b008` — gate-aware bypass helpers
(`_GATE_STAGES` + `_pipeline_at_gate_stage` +
`_reject_if_project_busy_outside_gate`); verified live by operator's
Val#1 V4 (`tests/unit/test_iterate_endpoint.py::TestIterateEndpointGateBypass`
7/7 pass).

**N=2 evidence:** Val#1 verification-report (`coordination/mailbox/sent/2026-05-26T08-00-00Z-operator-to-director-verification-report.md`)
§V1, file:line `web_server.py:1940` (`api_screening_approve`). The
shared state was the persistent `screening_approved` flag + the
on-disk `final_video_path` precondition; the existing endpoint
(`/assemble/screen`) had the `os.path.exists(final_video_path)` guard;
the new-ish endpoint (`/screening/approve`) was missing it. Operator's
V1 suggested-fix verbatim:

> "Mirrors `/assemble/screen`'s already-existing precondition check
> at the same condition (verified at `web_server.py:1935`-ish range —
> that endpoint 409s on missing mp4)."

Closed at director's fix `d10b849` — precondition check mirroring
`/assemble/screen`'s same-condition check; commit body explicitly
names "the symmetric-endpoint audit case operator surfaced as an
operational note in Lane V #8" and confirms "this pattern is now at
N=2 application."

**Edit anchor:**
- PROTOCOL-RULES-LOG.md: add row to rule registry; add entry to
  "Beneficiary distribution snapshot" subsection with row `13 (Symmetric-endpoint
  audit discipline) | director-seat | constrains endpoint design
  (director-seat specialization); reduces Lane V findings (operator-seat
  benefits)`.
- CLAUDE.md / AGENTS.md: add Rule #13 subsection under "## Discipline
  rules in effect" after Rule #12 subsection. Cross-reference from
  the "Project conventions you MUST follow" item 6 ("pid-scope check
  on new endpoints") in the implementer prompt template since item 6
  is the narrower domain-specific application of Rule #13's broader
  shape.

**Beneficiary (per R11):** `director-seat`. The discipline binds
director-seat's endpoint-design specialization. Operator-seat benefits
indirectly (fewer symmetric-case Lane V findings) and gets explicit
R11 veto in REPLY cycle.

---

## Locked design decisions (5 new)

| # | Question | Decision |
|---|---|---|
| 1 | Rule #12 wording — "grep-the-writes" or "verify-the-symbol-is-written" | **"Grep-the-writes"** as rule line; "type-declaration is not write-evidence" as subtitle. "Grep" is the specific command; the subtitle captures the broader principle (a Pydantic default value isn't proof of population). |
| 2 | Rule #13 wording — "symmetric-endpoint audit" or "shared-state audit" | **"Symmetric-endpoint audit"** as rule line. "Shared-state" is more abstract but less directive; "symmetric-endpoint" names the failure mode and matches operator's surfacing language. |
| 3 | Beneficiary for both rules — `director-seat` (asymmetric, R11 veto) or `both` (symmetric) | **`director-seat`** for both. The rules constrain director-seat's specialization work. Operator-seat benefits downstream (fewer Lane V cleanups) but is not the primary obligated party. R11 veto path opens explicitly; operator-seat consent expected to be a formality given operator surfaced both candidates but the channel is the right channel. |
| 4 | Cross-reference from implementer prompt template items 5 + 6 — explicit or implicit | **Explicit cross-reference.** Item 5 ("Brief-pattern reference adherence") is mutually reinforcing with Rule #12; item 6 ("pid-scope check on new endpoints") is a narrower instance of Rule #13's broader audit shape. Explicit cross-reference helps next-cycle director and prevents the rules from being treated as orthogonal to the template they're meant to strengthen. **Cross-file numbering note:** CLAUDE.md numbers these as items 5/6; AGENTS.md numbers the semantically-equivalent items as 4/5 (and uses slightly genericized wording). Ship-time edits target items by semantic identity, not numeric position. |
| 5 | Codification placement — under "## Discipline rules in effect" (alphabetic / numeric) or as a new subsection "## v5.1 rule additions" | **Inline under "## Discipline rules in effect" — Rule #12, Rule #13 inserted in numeric order after Rule #11.** Matches the existing rule registry's pattern. v5.1-specific framing lives in PROTOCOL-RULES-LOG.md's invocation log + this proposal's audit trail. |

---

## Composability with prior bundles

| Pair | Composition |
|---|---|
| **v4.1 CC-2 (spec-reviewer "verify before asserting") + v5.1 Rule #12** | CC-2 is the **downstream** version of Rule #12 (Lane V spec-reviewer prompts verify symbols before assertions). Rule #12 is the **upstream** version (briefs verify symbols before dispatch). Together they form a two-layer discipline: Rule #12 catches at brief-write time; CC-2 catches at Lane V time. Compatible by construction; no overlap. |
| **v4 Rule #9 (independent reviewer) + v5.1 Rule #13** | Rule #9 establishes the cold-context-catches-symmetric-cases principle as a structural property of Lane V. Rule #13 moves the catch upstream from Lane V (post-commit) to brief-write time (pre-dispatch). Rule #9 still applies — Rule #13 isn't a replacement, it's a complement that reduces Lane V load on symmetric-case findings specifically. |
| **v5 §S (Lane S scout activation) + v5.1 Rules #12 + #13** | Lane S is the **mechanism** for both rules' verification step. A director who needs to verify "are there existing endpoints whose defenses I should mirror?" (Rule #13) can send a `scout-request` to operator-seat naming the new endpoint + the shared state; operator's `scout-report` returns the audit. Same for Rule #12's grep-the-writes — `scout-request` can name the symbol and operator returns the grep output. v5.1 doesn't REQUIRE Lane S; opt-in remains per v5 §S decision. But Lane S is the natural place for these audits when director-seat doesn't have the bandwidth. |
| **v5 R10 (joint-team mode) + v5.1 Rules #12 + #13** | R10 says both seats serve user-principal; specialization is cognitive-load distribution. Rules #12 + #13 fit cleanly: they constrain director-seat's specialization (brief-writing + endpoint design) but benefit operator-seat + user. The asymmetric beneficiary annotation makes the load-distribution explicit. |
| **v5 R11 (codification bias check) + v5.1 self-application** | R11 self-application to v5.1: both rules beneficiary `director-seat`, 0 both, 0 user, 0 operator-seat. v5.1 is the FIRST bundle since v5's R11 was codified to have director-seat-only beneficiaries. **This is a noteworthy data point for R11's distribution snapshot** — previously (Rules 1-11) the distribution was 6 both / 2 user / 3 operator-seat / 0 director-seat = 11 rules. v5.1 shifts the post-ship distribution to 6 both / 2 user / 3 operator-seat / 2 director-seat = 13-rule balance. R11's veto path is active; operator-seat REPLY signals consent or counter. (Drive-by: the existing PROTOCOL-RULES-LOG.md snapshot footer reads "`both`: 5" but the listed rule IDs are 1,2,3,5,7,10 = 6 rules. Will correct to "`both`: 6" as part of v5.1's snapshot edit; not scope-creep since the snapshot is the file v5.1 is editing.) |
| **v5.1 Rules #12 + #13 + implementer prompt template items 5/6** | Items 5 (brief-pattern reference adherence) and 6 (pid-scope check on new endpoints) in the implementer prompt template (from cycle-5/6 failure modes) are domain-specific applications of v5.1's broader principles. Rule #12 generalizes item 5 ("verify the pattern reference is real before claiming it"); Rule #13 generalizes item 6 ("verify endpoint scoping by inspecting sibling endpoints"). Explicit cross-reference per locked decision #4. |

---

## Open questions for operator REPLY-cycle

| # | Question | Director's lean |
|---|---|---|
| 1 | Rule #12 verification command set — three grep variants (dict key / Pydantic field / function call) or generalized "grep the writes"? | **Three variants explicit.** Different field types have different write patterns; a generic "grep the writes" is hand-wavy. Explicit variants give the codifier (director-seat) a checklist. Counter would be: "Just say 'verify production writes' and let context dictate command." Both shippable; lean explicit. |
| 2 | Rule #13 "all existing endpoints" scope — repo-wide grep or just `web_server.py`? | **`web_server.py` is sufficient for current scope** since all endpoints live there. Future may split (e.g., `cinema/web/*.py`); the rule says "all existing endpoints on the same shared state" which is symbol-grep-driven, not file-driven. Lean: rule wording leaves file scope implicit; verification command examples use `web_server.py` as the current state. |
| 3 | Rule #12 + Rule #13 explicit invocation in implementer prompt template — add a new "Project conventions you MUST follow" item 7 + 8 referencing the rules, OR cross-reference existing items 5 + 6? | **Cross-reference existing items 5 + 6** (locked decision #4 above). Adding items 7 + 8 would duplicate item 5 + 6's domain-specific content. Cross-reference keeps the template tight. |
| 4 | Implementer prompt template item 5 + 6 cross-reference — quote the rules inline (long-form) OR add a short line ("see Rule #12 / Rule #13")? | **Short line.** The implementer prompt template is already 80-150 lines; adding rule text inline duplicates content already in the rule registry. A one-line "(see Rule #12 in PROTOCOL-RULES-LOG.md for the broader discipline)" preserves the template's tightness. |
| 5 | Should v5.1 also add a "Rule emergence rate" subsection to PROTOCOL-RULES-LOG.md noting that 2 rules promoted in 1 cycle is the highest emergence rate to date (vs. v2's 5 / v3's 1 / v4's 1 / v4.1's 0 / v5's 2)? | **Defer to v5.2+.** Two data points (v5 + v5.1) is too few to establish a meaningful "rate" framing. Note the emergence in the rules-log's "Invocation log" section as a session-narrative line; don't codify "emergence rate" as a tracked metric until we have v6/v7 baseline. |

---

## Trade-offs and risks

| Risk | Mitigation |
|---|---|
| **Rule #12 + #13 add brief-write-time friction for director-seat** | Friction is bounded: Rule #12's grep is ~1-2 commands per named symbol; Rule #13's audit is ~1 grep + 1-2 file reads. For briefs with rich pattern references (most cycle-10 briefs), this is ~30 seconds of director-seat work that catches design-time failures Lane V would catch post-commit. Cost-benefit: clearly positive at current Lane V cost per finding (~30k tokens). |
| **Rule #13's "audit ALL existing endpoints" is unbounded in principle** | Scope is shared-state-driven, not enumeration-driven. The audit is "all endpoints that touch the named shared state" — typically 2-5 endpoints for current state symbols (`_running_pipelines`, `screening_approved`, `needs_reassembly`). For future shared state symbols with wider footprints, scope can be narrowed via Lane S `scout-request` (operator-seat does the audit). |
| **Asymmetric beneficiary may trigger R11 veto inappropriately** | Operator-seat surfaced both candidates and explicitly recommended codification in both REPLYs (Lane V #8 op-note #2 + Val#1+#2 REPLY's V1 disposition). Veto unlikely but the channel is the right channel. If operator-seat counters with "rule wording is too prescriptive" or "scope is too broad," I refine in next revision cycle. |
| **Rule #12 + #13 codification could be seen as director-seat self-correction without true bundle-level discipline** | Honest assessment: yes, both rules ARE director-seat self-correction. But they're empirically-derived (operator-seat surfaced both via Lane V) and they meet the N=2 threshold. The proposal cycle's purpose is to make codification visible + auditable, not to require external authorship. R11's beneficiary annotation makes the self-correction nature explicit. |
| **The two rules' verification commands could feel like bureaucratic overhead in routine briefs** | Most briefs DON'T name new schema fields or new endpoints. Rules apply when they apply; routine refactor briefs / doc updates / chore commits don't trigger either rule. Empirically: cycle-10 had ~14 director commits; Rule #12 would have applied to 4 (P1-3 parts 7-10's mutator references) and Rule #13 would have applied to 1 (Val#1 V1 fix's mirror reference). ~35% of commits affected; rest unchanged. |
| **Future failures of Rules #12 + #13 (catches missed despite codification) could weaken protocol confidence** | Same risk applies to all rules. v4.1 narrowing-threshold model (>1.5M tokens AND <15% catch rate → narrow scope) generalizes to Rule #12 + #13: if catch rate drops below 15% within ~3-4 cycles of v5.1 ship, treat as narrowing signal and revise in v5.2 / v6. |

---

## What v5.1 does NOT do

- Does NOT introduce new mailbox kinds (no parallel to v5 §M)
- Does NOT introduce new lanes (no parallel to v5 §S activation)
- Does NOT add new files (no parallel to v5 §B BACKLOG.md or §E INCIDENT-LOG.md)
- Does NOT modify existing rules (no clarifications to Rule #1-#11)
- Does NOT change role partition or seat authority
- Does NOT add automation (Phase 2 territory remains deferred)
- Does NOT change memory write authority or mailbox enum
- Does NOT introduce new TypeScript/Python code changes — pure protocol/docs
- Does NOT mandate Lane S `scout-request` for the audit (opt-in per v5 §S decision)
- Does NOT promote any of the deferred candidates from v5's "v5.1+" markers (B Lane V claim expansion, M user-direct path, S mandatory above N LOC) — those remain v5.2+ candidates if data accumulates

---

## Dogfood / acceptance

**v5.1 is "shipped" when:**
1. CLAUDE.md / AGENTS.md `## Discipline rules in effect` subsection has Rule #12 + Rule #13 added in numeric order after Rule #11
2. Cross-references from implementer prompt template items 5 + 6 are added (one line each pointing at Rule #12 / Rule #13)
3. PROTOCOL-RULES-LOG.md rule registry has rows for Rules #12 + #13 with `_Protocol Bundle v5.1 ship_` placeholders
4. PROTOCOL-RULES-LOG.md "Beneficiary distribution snapshot" subsection updated with Rules #12 + #13 rows and refreshed totals (5 both / 2 user / 3 operator-seat / 2 director-seat = 12-rule balance)
5. This proposal's footer updated post-ship per Rule #6/#7 ship discipline
6. STATE.md reflects the ship (auto-regenerated; not committed per B-003 Option E)
7. Rules #12 + #13 ship with `_Protocol Bundle v5.1 ship_` placeholder; operator updates next session-close to actual ship SHA per chicken-and-egg precedent

**v5.1 is "working" when (within next 2-3 cycles):**
- ≥1 Rule #12 invocation in a brief or dispatch prompt (grep output captured under named symbol)
- ≥1 Rule #13 invocation in a brief or commit body (audit one-liner naming existing endpoints checked)
- Lane V findings of the same shape as Lane V #6 F1 / Lane V #8 I1 / Val#1 V1 decrease in frequency by ≥50% over 2-3 cycles, OR if any do occur, they're surfaced as Rule #12 / #13 evasion (brief skipped the grep / audit) rather than codification failure
- Two-layer-defense framing preserved: codification is a SECOND layer (brief-write-time) over the existing Lane V layer (post-commit cold-context). Post-codification Lane V catches of those shapes are evidence of working two-layer defense, not broken rule.

**v5.1 rollback trigger:** if Rule #12 or Rule #13 generates measurable friction (operator-seat counter via mailbox event citing specific incident) within 3 sessions OR if "working" criteria fail, revise in v5.2 (analogous to v2.1, v4.1 patterns).

---

## v5.1 beneficiary check (per R11, applied to v5.1 itself)

| Component | Beneficiary | Notes |
|---|---|---|
| Rule #12 (grep-the-writes) | director-seat | constrains brief-writing |
| Rule #13 (symmetric-endpoint audit) | director-seat | constrains endpoint design |

**Distribution:** 0 both, 0 user, 0 operator-seat, **2 director-seat**.

**Post-ship 13-rule distribution:** 6 both / 2 user / 3 operator-seat / 2 director-seat. v5.1 RE-BALANCES the distribution — pre-v5.1 it was 6/2/3/0; post-v5.1 it's 6/2/3/2. This addresses the "0 director-seat" data point from v5's R11 introduction without forcing artificial balance — these are rules that genuinely constrain director-seat's specialization work, empirically derived from N=2 failure modes.

**R11 veto availability for operator-seat:** explicit. Both rules are asymmetric (`director-seat` only); operator-seat REPLY-cycle can:
- Counter with rule-wording refinement (most likely)
- Counter with scope adjustment ("limit Rule #13 to gate-state, not all shared state")
- Defer to v5.2+ ("not yet ripe — wait for N=3 instances")
- Downgrade to advisory ("rule is good guidance but shouldn't be a hard discipline")
- Silent-accept (precedent: v4 R-V1's counter was silent-accepted)

---

## Ship strategy

Bundle as single commit. Race-ack body per Rule #5 if state moves during ship.

Estimated implementation effort: ~20-30 min. Smaller than v5 (~45-60 min)
because narrower scope: pure rule additions, no philosophical reframe,
no new files, no mailbox/lane mechanism additions.

**Files touched at ship:**
1. `CLAUDE.md` — Rule #12 + Rule #13 added under "## Discipline rules in effect" subsection (numeric order after Rule #11); 2 cross-references added to implementer prompt template items 5 + 6
2. `AGENTS.md` — mirror of CLAUDE.md
3. `docs/PROTOCOL-RULES-LOG.md` — 2 new rule registry rows; 2 new rows in "Beneficiary distribution snapshot" with updated totals
4. This proposal file — footer state update post-ship

**SHA placeholder pattern:** Rules #12 + #13 ship with `_Protocol Bundle
v5.1 ship_`; operator-seat (or whoever ships the ship-commit follow-up)
updates to actual SHA in follow-up commit per chicken-and-egg precedent
(`3e57ddf` v2 / `d8f2407` v3 / `d90036b` v4 / `509db7c` v4.1 / `d66690f` v5).

**Blocks:** None. v5.1 is additive over v5 — nothing currently working breaks; existing 11 rules preserved.

---

## What this proposal explicitly answers for the user

User said: "5.1 proposal" (concise direction; cycle-11 priority slate had v5.1 as #3 per the cycle-10 handoff).

This proposal:

1. **Codifies** the two N=2 candidates I committed to drafting in Lane V #8 REPLY (`345c6e3`) and Val#1+#2 REPLY (`9f652a2`).
2. **Annotates beneficiary** per Rule #11 — both rules are `director-seat` (asymmetric); operator-seat has explicit REPLY-cycle veto.
3. **Preserves the proposal cycle** — director-drafts here (inverted from v2-v5's operator-drafts), but operator-seat REPLY-cycle is the next step; ship requires operator consent (silent-accept or affirmative).
4. **Mirrors v5's format** with narrower scope — TL;DR + Why + per-rule sections + locked decisions + composability + open questions + trade-offs + dogfood + R11 self-check + ship strategy.

If any of this misses the user's intent, the disagreement protocol (v5 §D) is the channel — counter-refinement in next REPLY cycle. The "two seats one team" framing (v5 R10) means user-direction overrides agent discretion; v5.1 is designed to be revised before ship if it doesn't land.

---

## References

- v5 proposal + REPLY + ship: `2e06fe1` → `642250d` → `d66690f`
- v4 proposal + REPLY + ship + v4.1: `5302fe6` → `8975a45` → `d61bdc8` → `509db7c`
- v3 proposal + REPLY + ship: `749341b` → `26a0842` → `3340d1f`
- v2 proposal + REPLY + ship + v2.1: `1b3f6f8` → `c6a8f22` → `416d610` → `5e0329d`
- Lane V #6 F1 verification-report: `coordination/mailbox/sent/2026-05-25T18-20-57Z-operator-to-director-verification-report.md` (Rule #12 N=1)
- Lane V #8 verification-report: `coordination/mailbox/sent/2026-05-26T05-15-00Z-operator-to-director-verification-report.md` (Rule #12 N=2 op-note #2; Rule #13 N=1 I1)
- Val#1 verification-report: `coordination/mailbox/sent/2026-05-26T08-00-00Z-operator-to-director-verification-report.md` (Rule #13 N=2 V1)
- Director's Lane V #8 decision REPLY: `coordination/mailbox/sent/2026-05-26T07-20-00Z-director-to-operator-decision.md` (`345c6e3`)
- Director's Val#1+#2 combined decision REPLY: `coordination/mailbox/sent/2026-05-26T12-40-00Z-director-to-operator-decision.md` (`9f652a2`)
- Cycle-10 close handoff: `docs/HANDOFF-director-transplant-2026-05-26-cycle10.md` (`b715ff9`)
- I1 fix: `9e9b008` (`fix(iterate+reassemble): close Lane V #8 I1 CRITICAL + I2 + I3`)
- V1 fix: `d10b849` (`fix(screening): close Val#1 V1 — /screening/approve precondition check`)
- F1 fix: `6c1171a` (`fix(iterate): close Lane V #6 F1 (vestigial-field F2 filter) + F2 + F3 + regression test`)
- v5.1 REPLY (operator): `9f032db` ([docs/REPLY-protocol-bundle-v5.1-operator-2026-05-26.md](REPLY-protocol-bundle-v5.1-operator-2026-05-26.md))
- Current HEAD at proposal-write: `b715ff9`; at v5.1 ship: see ship commit (chicken-and-egg placeholder).

---

*Director-draft proposal authored 2026-05-26 at HEAD `b715ff9`. Operator-REPLY at `9f032db` (`docs(reply): operator response to Protocol Bundle v5.1 proposal — explicit consent + 2 comment-only refinements + 5 open-question concurrences`) returned explicit R11 non-veto consent on both rules + 2 comment-only refinements (R-D-1 dogfood criterion #3 reframe; R-Q1-1 verification-commands header). Both refinements folded inline pre-ship per operator's silent-acceptable framing.*

***SHIPPED 2026-05-26** by director — Rules #12 + #13 codified in CLAUDE.md / AGENTS.md / docs/PROTOCOL-RULES-LOG.md; beneficiary distribution snapshot updated to 6 both / 2 user / 3 operator-seat / 2 director-seat = 13 rules (drive-by correction to prior "both: 5 → 6" rule-count typo folded inline since rules-log was already the file being edited). SHA placeholders (`_Protocol Bundle v5.1 ship_`) for Rules #12 + #13 ship in the same commit per chicken-and-egg precedent; will be filled at next session-close (whichever seat is active) per cycle precedent (`3e57ddf` v2 / `d8f2407` v3 / `d90036b` v4 / `509db7c` v4.1 / `d66690f` v5).*

*Race-ack note: operator-seat shipped Lane V #9 verification-report at `bef8d12` between v5.1 proposal at `b583305` and v5.1 REPLY at `9f032db`; Lane V #9 disposition is separate from v5.1 ship per role partition + operator's own REPLY framing. Director-seat will issue Lane V #9 decision REPLY in a separate commit. User direction can override at any point per existing CLAUDE.md "Instruction Priority" and v5 §P1.*
