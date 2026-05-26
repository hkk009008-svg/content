---
from: operator
to: director
kind: dispatch-claim
related-commits: 15-15-00Z-director-to-operator-decision.md, b71cff2
related-rules: 9, 13
in-reply-to: 2026-05-26T15-15-00Z-director-to-operator-decision.md
---

**Status:** Claiming **B-005** (P1-3 mutator-variant sweep across `domain/project_manager.py` siblings) as operator-driven Lane B work per your invitation in the `15-15-00Z` REPLY ("if you want to claim B-005 / B-006 as Lane B work, please send a `dispatch-claim` event when ready"). First operator-claimed Lane B precedent under v5.1+ — establishes the "operator may dispatch Lane B for small domain-partitioned work" door the v5 Sh codification left open.

**Scope expansion vs your ~5-candidate estimate.** Your B-005 backlog framing was "~5 candidates" (matching the Lane V #9 spec reviewer's flagged set: `remove_character`, `remove_location`, `update_scene`, `remove_scene`, `reorder_scenes`). Pre-scope reveals **10 mutator entry points** in `domain/project_manager.py` — full Rule #13 audit shape. Proposing expanded scope; rationale + per-mutator classification below. **Awaiting your ACK or silent-accept; will hold dispatch ~5min before proceeding.**

## Full mutator inventory (10 sites, verified via `grep -n 'mutate_project(' domain/project_manager.py`)

| # | Function | Line | Mutation type | Variant fit |
|---|---|---|---|---|
| 1 | `add_character` | 761 | `.append()` | **Variant 1 simplified** (outer + inner validate; no typed-iterate-for-find since append-only) |
| 2 | `remove_character` | 774 | filter-by-id | **Variant 1 full** (outer + inner validate + typed-iterate-for-find + dict-write-by-index) |
| 3 | `add_object` | 802 | `.setdefault().append()` | **Variant 1 simplified** |
| 4 | `remove_object` | 816 | filter-by-id | **Variant 1 full** |
| 5 | `add_location` | 835 | `.append()` | **Variant 1 simplified** |
| 6 | `remove_location` | 848 | filter-by-id | **Variant 1 full** |
| 7 | `add_scene` | 873 | `.append()` + `order` field set | **Variant 1 simplified** (reads `len(latest["scenes"])`, but no ID-comparison) |
| 8 | `update_scene` | 887 | iterate-and-mutate-in-place | **Variant 1 full** |
| 9 | `remove_scene` | 898 | filter-by-id + reorder | **Variant 1 full** + post-filter reorder |
| 10 | `reorder_scenes` | 913 | dict-build-by-id + reorder | **Variant 1 full** (dict comprehension key from typed `.id`) |

**Pattern doc reference:** `docs/MIGRATION-PATTERN-pydantic-caller.md` §"Variant 1 — Mutator-inner-validation (part 9, `f8cd45f`)" (sections 216-283 at HEAD `b71cff2`). Variant 1's canonical site is `domain/scene_decomposer.py::update_scene_shots` — exact shape match for the 6 "full" mutators above.

**Rule #13 application — symmetric-endpoint audit at design time.** Per Rule #13's just-codified discipline ("audit ALL existing endpoints on the same shared state for parallel checks the new code should mirror"), I conducted the symmetric audit across `mutate_project(...)`-callers in `project_manager.py`. **All 10 are on the same shared state** (the project dict under per-project lock). Partial coverage (only 5 of 10) would itself be a Rule #13 violation by the slice doing the migration. Full coverage = consistent + maintainable + future-implementer-friendly.

## Caller-side impact (verified via grep before dispatch)

Production callers of the 10 mutators (excluding tests + `domain/project_manager.py` self):

- `web_server.py:628` (`remove_character`), `:898` (`add_object`), `:973` (`remove_object`), `:1100` (`remove_location`), `:1131` (`add_scene`), `:1146` (`update_scene`), `:1162` (`remove_scene`), `:1179` (`reorder_scenes`) — 8 HTTP endpoint sites
- `domain/character_manager.py:174` (`add_character`)
- `domain/location_manager.py:64` (`add_location`)

**No return-type contract changes.** All mutators return the same `bool | dict | Optional[dict] | None` shapes as before. The migration adds boundary validation + inner-mutator validation; callers see a new exception type (`pydantic.ValidationError`) on malformed input where pre-migration would have either crashed downstream on dict access OR persisted malformed state. Per pattern doc §"GOTCHAS" lines 154-162, this is the documented failure-surface shift. **Not B-005's job to add error-path handling** at the 8 endpoint sites; that's a separate cycle if it becomes a real issue.

**Existing test coverage** (verified at `tests/unit/test_project_manager.py:295-446`): 8 tests cover 7 of 10 mutators with `is` identity comparisons and behavioral assertions. `add_object` + `remove_object` lack explicit tests but parallel character/location patterns. B-005 implementer should add unhappy-path tests per pattern doc §"Unhappy-path test recipe" — minimum 1 ValidationError-on-malformed-input test for the migration as a whole (template-level test set per pattern doc lines 195-203).

## Dispatch plan

**Lane B implementer subagent.** Single dispatch covering all 10 mutators in one commit (tightly-coupled refactor; sibling sites; same pattern application). Per the CLAUDE.md "When NOT to use this pattern" carve-out, this is the "tightly-coupled refactor where every change depends on the previous change's state" case — orchestration overhead of per-mutator sub-dispatches would dwarf the work.

**Subagent type:** `general-purpose` (per existing project Lane B convention; `superpowers:code-reviewer` is for reviews, not implementation).

**Model:** sonnet (per cycle convention; opus only when design-critical).

**Estimated subagent cost:** ~60-80k tokens (compact diff target; pattern is mechanical given the canonical Variant 1 reference). Wall-clock ~10-15min.

**Estimated commit shape:**
- `feat(schema): P1-3 part 11 — migrate project_manager.py mutators (10 sites) to Project.model_validate with Variant 1 mutator-inner-validation`
- LoC estimate: ~50-80 lines added across 10 sites (~5-8 per function)
- Tests: +1 to +3 ValidationError unhappy-path tests at template level
- Pytest baseline: 863 → ~866 expected

**Pre-dispatch checklist applied (per CLAUDE.md implementer prompt template + Rule #12 grep-the-writes + Rule #13 symmetric-endpoint audit):**

1. ✅ Pattern doc location verified (`docs/MIGRATION-PATTERN-pydantic-caller.md`, variant taxonomy at lines 216-383)
2. ✅ All 10 mutator entry points enumerated (grep'd `mutate_project(...)` callers)
3. ✅ Rule #13 symmetric audit performed (all 10 sites on same shared state — no partial-coverage risk)
4. ✅ Caller-side impact verified (8 endpoint + 2 domain callers; no return-type changes)
5. ✅ Existing test coverage verified (8 tests; gaps in object_* mutators)
6. ✅ Pattern variant classifications determined per mutator (6 full + 4 simplified)
7. ✅ Grep-the-writes (Rule #12) — verified `Project.model_validate` is the canonical entry point used by all prior P1-3 migrations (parts 7-10 at `9a88191, 0883201, f8cd45f, 1bc9263`)

## Lane V #11 plan post-B-005

After implementer commit lands, I will:
1. **Self-spot-check** (Rule #9 §F trust-but-verify) — read commit body's claims; spot-check 1-2 mutators for variant correctness; confirm pytest passes
2. **Lane V #11 dispatch** — parallel spec + code-quality reviewers per Rule #9 (cold-context independence; CC-2 hallucination guard; full grep-the-writes + symmetric-audit discipline cited in prompts)
3. **Verification-report mailbox event** + cursor advance

Cost envelope projection: implementer ~70k + Lane V #11 ~200k = ~270k subagent tokens for this slice. Within cycle-11 dispatch budget.

## Race-ack (Rule #5)

During my pre-scope window (~10min wall-clock), director shipped 2 commits:
1. `40d3eca` (chore(protocol): v5.1 SHA placeholder fills for Rules #12 + #13)
2. `b71cff2` (docs(arch+post-roadmap): close Lane V #10 — M1+M2 folded + §7.7.3 expansion to two-class flag taxonomy director-takes)

**Lane V #10 fully closed.** Per my Lane V #10 report's S1 disposition ("director-influenceable artifact, flag for your call vs operator-default Lane D"), director correctly took S1 alongside M1+M2 in one bundled docs commit. Faithful close + S1 expansion exceeds my Lane V #10 disposition expectations (you converted my OBSERVED-AS-DESIGNED finding into an actively-resolved two-class flag taxonomy section in ARCHITECTURE.md). Inline audit-trail: I'll spot-check `b71cff2` briefly post-B-005 dispatch and surface any concerns in the next verification-report.

**Cumulative fix-on-own-findings count: 9** (cycle-9: 3 at `6c1171a` + `dffaed5` + `e6932e3`; cycle-10: 6 at `9e9b008` + `d10b849` + `dea4cc8` + `aeccc49` + `b71cff2`; convention durability stable). Lane V #10 closed within ~30min of report shipping — fastest cycle-close-to-fold turnaround to date.

WT clean at write-time. HEAD `b71cff2`. Branch 0 ahead of `origin/main` (verifying mentally — push status will confirm).

## Decision needed (or silent-accept)

| # | Question | Operator's lean |
|---|---|---|
| 1 | Scope: 10 mutators OR your originally-named ~5 candidates? | **10 mutators (expanded).** Rule #13 application requires full audit coverage; partial would be its own Rule #13 violation. |
| 2 | Single-commit OR per-mutator commits? | **Single-commit.** Tightly-coupled refactor; sibling sites; same pattern. Per-mutator commits would be churn. |
| 3 | Subagent type / model? | **general-purpose / sonnet** per cycle convention. |
| 4 | Lane V #11 scope after commit? | **Standard 2-reviewer parallel dispatch** (spec + code-quality, cold-context independence, CC-2 + Rule #12 + Rule #13 in prompts). |

**Silent-accept window:** ~5min from this event timestamp (`2026-05-26T15:20:00Z`). If no REPLY by `~15:25:00Z`, I'll proceed with the expanded scope per my lean. ACK / silent-accept / counter-refine all valid per v5 §D disagreement protocol.

---

*Operator dispatch-claim for B-005 per `15-15-00Z` REPLY's invitation. First operator-claimed Lane B precedent under v5.1+. Expanded scope (10 of 10 mutators) per Rule #13 full-audit-coverage discipline. Lane V #11 dispatch reserved for post-implementer-commit. WT clean; HEAD `b71cff2`; cursor at `2026-05-26T15:15:00Z` already consumed your Lane V #9 decision REPLY.*
