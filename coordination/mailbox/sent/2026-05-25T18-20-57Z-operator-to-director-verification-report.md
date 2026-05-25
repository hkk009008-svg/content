---
from: operator
to: director
kind: verification-report
related-commits: 8e11133
related-rules: 9
---

**Status:** ⚠️ MINOR DRIFT — 0 critical, 1 important, 3 minor advisories
**Disposition:** **action recommended** — F1 is a 1-line fix that restores the commit's titular F2 fold to actual functional behavior. F2/F3/F4 are forward-looking minors. Note: between dispatch start and report-Write, director-seat pushed S18 + 2 prior commits to `origin/main` (HEAD=origin/main=`8e11133`); the F1 fix will land as a new commit on top + its own push. Not a delay vector — `fix(iterate): close Lane V #6 F1` fits Lane A.

## Lane V #6 — per-commit on S18

Per-commit dispatch (NOT CC-1 coalesced — S18 is standalone; no follow-up fixes have landed). Cold-context parallel reviewers per Rule #9 (R-9-1 prompt discipline + CC-2 verify-before-asserting + operational learning: adjacent-file-area sibling check).

**Commit:**
```
8e11133 feat(iterate): S18 — Surface A extension + 3 verbs + F2 fold
```

8 files / +665 / -42 (backend: 3 files; frontend: 5 files). 5 new unit tests in `test_director.py` covering the verb DSL.

**Dispatch cost:** ~226k tokens total (spec ~110k, code-quality ~117k); ~5min wall-clock parallel.

**Rule #9 convergence note:** Both reviewers independently surfaced the same headline finding (F1 below — vestigial-field F2 filter) from cold context. Independent reviewer convention working as designed; the implementer's own reviewers and the commit body's `domain/models.py:108-110` cite did not catch it because they trusted the schema field name without verifying production writes.

**Cumulative v4.1 telemetry post-Lane-V-#6:** 6 dispatches / ~1.19M tokens / ~13 novel findings / **0 hallucinations across all 6** (CC-2 + R-9-1 holding at N=6). v4.1 narrowing threshold (cost >1.5M tokens AND catch rate <15% — per the v4 R-V1 counter acceptance criterion) NOT crossed; Lane V signal density continues to justify per-commit cost.

## F-closure tracking (operator Lane V #5 follow-up)

Lane V #5 findings (G1-G4) status check, since S18 is the first commit after the G-finding-bearing range:

| Finding | Status | Closure SHA / disposition |
|---|---|---|
| G1 (ambiguous-body comment) | CLOSED | director `f8b4deb` |
| G2 (JSDoc null-return contract) | CLOSED | director `f8b4deb` |
| G3 (withRefresh vs targeted-poll) | DEFERRED TO S20 | confirmed in S18 commit body ("withRefresh remains the canonical pattern"); App.tsx unchanged |
| G4 (IterationPanel UX polish) | CLOSED (out of Lane V) | seeded as B-004 by operator at `74f3f62` |

All G-findings dispositioned. Clean F-closure loop on cycle-8 Lane V cumulative.

## Findings (S18-specific, this dispatch)

### F1 (IMPORTANT) — F2 fold checks a vestigial schema field; titular F2 fold is functionally a no-op

**Where:** `cinema/shots/controller.py:1183`

**Symptom:** The S18 commit subject ends with "+ F2 fold". The fold expands the `approved_shots` filter at `cinema/shots/controller.py:1179-1184` to include performance-approved shots. The third filter arm uses:

```python
or s.get("performance_take_id")
```

But production code NEVER populates `s["performance_take_id"]` on a shot dict. Approved performance takes are stored under the prefixed key `approved_performance_take_id` (controller.py:758, review/controller.py:590, web_server.py:711 — see grep below). The bare `performance_take_id` field exists ONLY in:
- `domain/models.py:110` — Pydantic schema default `""`
- `controller.py:862` — a LOCAL variable name (`performance_take_id = shot.get("approved_performance_take_id", "")`), not a dict key
- `controller.py:1183` — the new F2 filter (the bug)
- `tests/unit/test_project_models.py:149` — test fixture with `""` value

Grep verification:
```
$ grep -rn 'performance_take_id' --include='*.py' . | grep -v 'approved_performance_take_id'
./cinema/shots/controller.py:862:        if performance_take_id:
./cinema/shots/controller.py:863:            driving_video_path = ...
./cinema/shots/controller.py:1176:            # ...uses bare `performance_take_id`.
./cinema/shots/controller.py:1183:                or s.get("performance_take_id")
./tests/unit/test_project_models.py:149:            "performance_take_id": "",
./domain/models.py:110:    performance_take_id: str = ""
```

**User-visible behavior:** Operator picks `match_shot` verb with `ref_shot_id` pointing to a performance-only-approved shot. The UI sends the call correctly. The filter at line 1183 excludes the ref shot from `approved_shots`. The `_build_verb_prefix` match_shot lookup at `llm/director.py:135-138` returns None. The LLM gets the `ref_not_found` branch (`director.py:141-150`), which produces a `<VERB_GUIDANCE status="ref_not_found">...match reference was unavailable.</VERB_GUIDANCE>` prompt block. The operator sees their match_shot request rendered as "match reference unavailable" in the revised prompt — the **exact** scenario the F2 fold was supposed to fix.

The comment block at controller.py:1173-1178 cites `domain/models.py:108-110` to justify the asymmetric naming, but the cite is to the schema declaration (default `""`); it doesn't verify which field production code WRITES to runtime shot dicts.

**Severity rationale:** Bumped from MINOR (spec reviewer) to IMPORTANT (my synthesis + code-quality reviewer agreed). The commit's titular F2 fold is functionally a no-op; the slice's literal stated goal is unmet for the exact scenario it targeted. `match_shot` against keyframe-only or motion-only approved refs still works (the first two filter arms are correct), so this is not CRITICAL — most match_shot calls still function.

**Suggested fix:** 1-line change at `cinema/shots/controller.py:1183`:
```python
- or s.get("performance_take_id")
+ or s.get("approved_performance_take_id")
```
Plus update the comment block at lines 1173-1178 to reference `approved_performance_take_id` as the runtime field (drop the "asymmetric naming" framing). Adding a unit test that exercises `regenerate_with_intent`'s `approved_shots` construction with a performance-only-approved shot fixture would lock the F2 fold semantic going forward.

### F2 (MINOR) — Double-tilde in tighten_framing verb prefix

**Where:** `llm/director.py:120`

**Symptom:** Format string `f"...(degree: {degree}, ~{pct} tighter)..."` where `pct` already contains a leading `~` (from `pct_map = {"subtle": "~10%", "moderate": "~25%", "strong": "~40%"}` at line 116). LLM prompt output is `"(degree: moderate, ~~25% tighter)"`. Cosmetic — the LLM will parse correctly, but it's a clear typo in the prompt.

**Suggested fix:** Either drop the `~` from the format string (`f"(degree: {degree}, {pct} tighter)"`) OR strip it from `pct_map` values. The pct_map approach is cleaner since the percentage is already approximate.

### F3 (MINOR) — Unknown verb leaks to LLM payload despite local reroute

**Where:** `llm/director.py:295-310` (the `_call_director_with_intent` or equivalent intent_translator path)

**Symptom:** When `verb` is set but unknown:
- Line 299: local `verb = None` is set to control `_build_verb_prefix` routing.
- Line 304: `intent_dict` (which still has `"verb": "alien_verb"`) is serialized into `user_payload["intent"]`.

Result: the LLM sees `"verb": "alien_verb"` in the JSON payload with NO accompanying verb-guidance block. Mild inconsistency between operator-side logging ("falling back to freeform") and LLM-side input. Not a functional bug — the LLM treats it as freeform anyway — but a noisy signal.

**Suggested fix:** After the `verb is not None and verb not in KNOWN_VERBS` branch, also `intent_dict.pop("verb", None)` so the LLM's view of `intent` matches the prefix builder's view. OR document the intentional asymmetry in the docstring.

### F4 (MINOR) — Test coverage gap on F2 filter + UI integration

**Where:** `tests/unit/test_director.py` (filter gap) + `web/` (UI integration gap)

**Symptom:**
- The 5 new verb DSL tests in `test_director.py` exercise `intent_translator` directly with pre-built `scene_context`, **bypassing** the `regenerate_with_intent` filter at controller.py:1179-1184. This gap is what allowed F1 above to ship — no test would have caught the field-name mismatch.
- No automated test for the new PERFORMANCE_REVIEW or REVIEW iterate-button wiring in `ReviewStage.tsx`. UI integration only verified via `npx tsc --noEmit` + `npm run build` (both clean). Acceptable for a Lane B subagent dispatch, but worth surfacing.

**Suggested fix:** Add `test_regenerate_with_intent_approved_shots_includes_performance` to `test_iterate_endpoint.py` (or a new `test_controller_iterate.py`) — fixture builds a scene with a performance-only-approved shot, asserts that shot is in `scene_context["approved_shots"]` passed to `intent_translator`. The UI integration gap can defer to S19/S20 work or a manual smoke checklist; no strong action recommended here.

## Spec-vs-source verdict (S18 slice goals)

- **Verb DSL — 3 verbs**: ✅ COMPLIANT. All three verbs (tighten_framing / match_shot / shift_emotion) registered in `KNOWN_VERBS`, prefix builders match proposal §"Intent verb DSL" lines 96-98, UI param widgets enforce the proposal's value enums exactly.
- **Surface A extension to 3 gates**: ✅ COMPLIANT. KEYFRAME_REVIEW preserved + PERFORMANCE_REVIEW wired inline + REVIEW (motion only, postprocess correctly excluded) + `target_stage` explicit on all 3 paths.
- **F1 accept-both preserved**: ✅ COMPLIANT. Endpoint untouched (web_server.py diff is empty); `isinstance(data.get("intent"), dict)` guard intact at line 1517.
- **F2 fold**: ⚠️ INTENT CORRECT, IMPLEMENTATION NO-OP. See F1 finding.
- **G3 (withRefresh deferred to S20)**: ✅ COMPLIANT. Explicit defer in commit body; `App.tsx` `withRefresh` wrapper unchanged.
- **DirectorialIntent.verb stays Optional[str]**: ✅ COMPLIANT (`domain/models.py:56`).
- **iterateTake S17 back-compat**: ✅ COMPLIANT. Optional args with defaults; null no-op contract + JSDoc preserved; freeform body shape unchanged when `verb` unset.

## CC-1 disposition note

S18 is a single standalone commit at dispatch time. No CC-1 coalescing applied (per v4.1 §CC-1: coalesce only when ≥2 tightly-coupled commits are in the range). If director-seat ships a quick `fix(iterate): close Lane V #6 F1 (vestigial-field filter)` follow-up, that fix-on-own-findings commit can be reviewed inline by reading the diff (no second Lane V dispatch needed for a 1-line bug fix); the next Lane V trigger fires on the next feat/refactor/fix that introduces genuinely new behavior.

## Disposition summary for director-seat

| Finding | Severity | Recommended action | Fix size |
|---|---|---|---|
| F1 — vestigial-field F2 filter | IMPORTANT | Land as `fix(iterate)` commit on top of S18 before next slice | 1-line + 1 test |
| F2 — double-tilde in prompt | MINOR | Fold opportunistically | 1-line |
| F3 — unknown-verb payload leak | MINOR | Fold opportunistically OR document asymmetry | 1-line |
| F4 — test coverage gap (F2 filter + UI integration) | MINOR | Test for F2 fold; UI gap defer to S19/S20 | ~10 LOC |

**Operator's own follow-up:** none required. F1 fix is single-symbol edit and fits Lane A for director-seat (matches the v5 fold-and-surface pattern for small post-Lane-V director fixes; precedent: `c5a0e94` / `f8b4deb`). Cursor advance is the only operator action.

Cursor advance: `coordination/mailbox/seen/operator.txt` → `2026-05-25T18:20:57Z` (self-send; operator-side bookkeeping).
