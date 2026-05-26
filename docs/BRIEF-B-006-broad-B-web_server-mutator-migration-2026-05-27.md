# B-006-broad-B Implementer Brief — web_server.py mutator migration

**From:** Director-seat (cycle 12)
**For:** Lane B implementer subagent (to-be-dispatched, cycle 12 or 13)
**Slice:** B-006-broad-B (P1-3 part 12 — `web_server.py` mutator-variant sweep)
**Pattern doc:** [docs/MIGRATION-PATTERN-pydantic-caller.md](MIGRATION-PATTERN-pydantic-caller.md)
**Canonical sites:**
- `c296105` — B-005 / `project_manager.py` (10 sites; nearest analog, single-commit)
- `1bc9263` — P1-3 part 10 (Variant 2 lookup builder; relevant for the L1079 outer-already-migrated case)
- `f8cd45f` — P1-3 part 9 (Variant 1 origin / canonical site `scene_decomposer.py::update_scene_shots`)
- `0883201` — P1-3 part 8 (Variant 1 base; `scene_decomposer.py` migration first instance)

**Related rules:** Rule #9 (independent reviewer), Rule #12 (grep-the-writes), Rule #13 (symmetric-endpoint audit).

**Predecessor disposition:** F1 B-006-broad-SPLIT shipped at `3de55b1` (`2026-05-27T01-00-00Z` director→operator decision REPLY). Broad-A is operator-claimable; this is broad-B, director-dispatched. Broad-A may execute before broad-B; broad-A's Lane V outputs may add minor refinements to this brief but the bulk is independent.

---

## TL;DR — 60 seconds

Migrate **15 `mutate_project(...)` call sites in `web_server.py`** to the canonical migration pattern variants. Pre-scoped distribution (independent Lane C survey): **13 Variant 1** (5 simplified + 8 full) + **1 Base read-only** (L1828) + **1 Mixed-shape conditional** (L1863). All 15 are **pid-scoped via route parameters** (zero `list_projects()`-scan survivors — Rule #13 audit clean). **Single commit** target shape: ~80-130 LoC added; +1 to +3 unhappy-path or race-protection tests at template level if applicable.

**Pre-existing out-of-scope concerns flagged** (do NOT fix in this slice — see §"Out of scope"): 6 sites silently swallow `None` returns from `mutate_project` (missing project → 2xx success); L691 runs in a background thread with broad exception swallowing.

---

## Pre-scope verification (Rule #12 + Rule #13)

### Rule #12 — grep-the-writes

The migration symbol `Project.model_validate(...)` is the canonical entry for Variant 1 inner-validation per the pattern doc. Verified at pre-scope time:

```
$ grep -rn "_Project.model_validate" --include='*.py' . | wc -l
~32 occurrences (10 in project_manager.py after B-005 + sibling pre-existing sites in cinema/, domain/, web_server.py)
```

The symbol IS populated at runtime across already-migrated sites. Pattern is mechanical given the canonical site reference at `c296105` (`domain/project_manager.py`).

### Rule #13 — symmetric-endpoint audit at design time

External `mutate_project(...)` caller surface verified via:

```
$ grep -rn "mutate_project(" --include='*.py' . | grep -v "project_manager.py" \
    | grep -v "test_" | grep -v ".venv/" | sort
```

**Surface partition** (per F1 decision REPLY at `3de55b1`):

- **B-006-broad-A** (operator-claimable, cycle 12+): `cinema_pipeline.py` ×1, `cinema/screening.py` ×3, `cinema/shots/controller.py` ×1, `domain/location_manager.py` ×1 = **4 files / 6 sites**.
- **B-006-broad-B (THIS BRIEF):** `web_server.py` ×15 outer call sites. Implementer counts at execution time; operator's earlier "×17" estimate counted `def _mutate_project` inner-lambda blocks separately.
- **Already-migrated, excluded from B-006:** `domain/scene_decomposer.py:927` (P1-3 part 8, `0883201`).

Partial coverage of the broad-B surface (e.g., migrating only 10 of 15) would itself be a Rule #13 violation. Full B-006-broad-B coverage of `web_server.py` is the design intent.

### Pid-scope audit (Rule #13 — S13 origin failure mode)

ALL 15 sites take `pid` as a route parameter (`<pid>` path segment) AND pass it directly to `mutate_project(pid, ...)`. No site resolves pid via `list_projects()` scan. The pid-collision class of bugs (S13 F1 CRITICAL at `9e24323`) is absent from the broad-B surface. **No remediation work needed; verify the audit at implementer time by spot-checking 2-3 sites.**

---

## Per-site table (15 sites, classified by independent Lane C survey)

> **Source:** cycle-12 director-side Lane C survey of `web_server.py` ×15 sites, read cold against the pattern-doc variant taxonomy. Implementer verifies each row before applying the recipe.

| # | Outer call | Inner mutator | Route name | Mutation shape | Variant fit | Lock | Return type | Migration notes |
|---|---|---|---|---|---|---|---|---|
| 1 | L420 | L413 (`_mutate`) | `api_apply_language_defaults` | merges language defaults into `project["global_settings"]` | **V1 simplified** | default | `MutationResult(True, save=bool(changed))` — return discarded | `snapshot=project`; return value silently discarded; **pre-existing None-swallow** (see §OOS) |
| 2 | L485 | L478 (`_mutate_project`) | `api_update_project` | writes `project["name"]` and/or `project["global_settings"]` | **V1 simplified** | default | `dict` or `None` | `if not project:` at L486 catches None→404 (correct shape); no `snapshot=` |
| 3 | L607 | L583 (`_mutate_project`) | `api_update_character` | typed-find char by `cid` in `latest_project["characters"]`; writes fields + appends ref images | **V1 full** | default | `dict` or `MutationResult(None, save=False)` | `snapshot=project`; mutator re-finds by raw `o["id"]` — implementer adds inner `_Project.model_validate(latest_project)` + typed-iterate-for-find using `latest_typed.characters` |
| 4 | L691 | L685 (`_mutate`) | `api_train_lora` (background `_runner` thread) | writes `project["global_settings"]["char_lora_paths"][cid]` after LoRA training success | **V1 simplified** | default | `MutationResult(True, save=True)` — return discarded | **Outlier:** mutate_project called from `threading.Thread` target, not HTTP handler. **Pre-existing exception swallow** by `except Exception as me: print(...)` will also swallow new ValidationError (see §OOS) |
| 5 | L772 | L761 (`_mutate`) | `api_upload_driving_video` | finds shot by `sid` via nested raw-dict loop; writes `shot["driving_video_path"]`; clears `performance_engine` if SKIP | **V1 full** | default | `MutationResult(dest_path, save=True)` or `MutationResult(None, save=False)` — discarded | `snapshot=project`; outer boundary at L743-746 already uses `Project.model_validate` to resolve `scene_id`; **pre-existing None-swallow** (see §OOS) |
| 6 | L795 | L786 (`_mutate`) | `api_clear_performance` | nested raw-dict loop finds shot by `sid`; clears `approved_performance_take_id` and `performance_engine` | **V1 full** | default | `MutationResult(True, save=True)` or `MutationResult(None, save=False)` — discarded | `snapshot=project`; **pre-existing None-swallow** (see §OOS) |
| 7 | L831 | L823 (`_mutate`) | `api_upload_style_board` | appends to `project["global_settings"]["style_reference_paths"]` with dedup loop | **V1 simplified** | default | `list` or `None` | response uses `len(refs or [])`; no `snapshot=` passed; **pre-existing None-swallow returns `len(0)` on missing project** (see §OOS) |
| 8 | L956 | L933 (`_mutate_project`) | `api_update_object` | raw-dict find of object by `oid` in `latest_project["objects"]`; writes fields + appends ref images | **V1 full** (with caveat) | default | `dict` or `MutationResult(None, save=False)` | `snapshot=project`; **mirrors B-005 `remove_object` deviation** — `Project` has `extra="allow"` and NO typed `Object` class. Inner `_Project.model_validate(latest_project)` still applies for race protection; typed-iterate-for-find is NOT applicable (no `latest_typed.objects` attribute). Use raw-dict iterate for find, like B-005's `remove_object`. See `c296105` per-mutator table for the canonical deviation pattern. |
| 9 | L1079 | L1059 (`_mutate_project`) | `api_update_location` | typed-find location at outer boundary (L1041); inner mutator uses raw dict to find `lid` and writes fields + appends images | **V1 full** | default | `dict` or `MutationResult(None, save=False)` | `snapshot=project`; **partially migrated — outer ALREADY has `Project.model_validate(project)` at L1040 (P1-3 part 5)**. Implementer adds ONLY the inner validate + typed-iterate-for-find; do NOT re-add the outer validate or duplicate the import. |
| 10 | L1301 | L1296 (`_mutate_project`) | `api_generate_style_rules` | writes generated `rules` to `project["global_settings"]["style_rules"]` | **V1 simplified** | default | `list/dict` — discarded | `snapshot=project`; **pre-existing None-swallow** (see §OOS); rules generated outside mutator then written under lock |
| 11 | L1696 | L1687 (`_mutate_project`) | `api_reject_auto_approve` | nested raw-dict loop finds shot by `shot_id`; appends to `shot["auto_approve_audit"]`; sets `shot[flag_key] = False` | **V1 full** | default | `dict {"shot_id": ..., "gate": ...}` or `MutationResult(False, save=False)` | `result is None` → 404 (correct); `flag_key = f"{gate}_auto_approved"` is computed — verify the dynamic key pattern at implementer time |
| 12 | L1722 | L1714 (`_mutate_project`) | `api_update_shot_prompt` | nested raw-dict loop finds shot by `shot_id`; sets `shot["prompt"]` | **V1 full** | default | `True` (bool) or `MutationResult(False, save=False)` | `result is None` → 404 (correct); no `snapshot=` passed |
| 13 | L1761 | L1753 (`_mutate_project`) | `api_update_shot` | nested raw-dict loop finds shot by `shot_id`; applies `shot.update(updates)` for allowlisted fields | **V1 full** | default | `True` (bool) or `MutationResult(False, save=False)` | `result is None` → 404 (correct); `updates` pre-filtered against `allowed_fields` set; no `snapshot=` |
| 14 | L1828 | L1821 (`_resolve_scene_id`) | `api_restart_shot` | read-only scene-id lookup via nested raw-dict loop; returns `scene["id"]` for downstream pipeline call | **Base** (read-only; `save=False` always) | default — lock acquired for read-only lookup, established pattern | `str` (scene_id) or `MutationResult(False, save=False)` | **Outlier:** mutator name is `_resolve_scene_id`, not `_mutate_project`. `save=False` means no race; **inner validate is NOT required** (Base read-only pattern — see §"Variant recipe" for the Base instructions). Outer boundary validate IS required for race-protection-on-validation-only semantics. Acquiring the per-project lock for a read-only lookup is the established codebase pattern — preserve. |
| 15 | L1863 | L1853 (`_mutate_project`) | `api_regenerate_shot` | nested raw-dict loop finds shot; conditionally writes `shot["prompt"]` if `new_prompt` set; returns `scene["id"]` for downstream pipeline call | **Mixed-shape: conditional V1 simplified (write path) OR Base (no-write path)** | default | `str` (scene_id) or `MutationResult(False, save=False)` | `result is None` → 404 (correct); the write path (`shot["prompt"] = new_prompt`) uses raw dict + needs inner validate for race protection; the no-write path returns `MutationResult(scene["id"], save=False)` — Base read-only shape. **One mutator, two shapes** — see §"Variant recipe / Mixed-shape" for the conditional recipe |

---

## Variant recipe — per-bucket instructions

### Variant 1 simplified (5 sites: L420, L485, L691, L831, L1301)

**Shape:** mutator does `.append()`, `.setdefault().append()`, or single-field writes (`project["name"] = ...`, `project["global_settings"][...] = ...`). No typed-iterate-for-find needed because there's no ID-lookup-then-mutate.

**Recipe (mirror `add_character` from B-005's `c296105`):**

```python
def api_<endpoint>(pid):
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    from domain.models import Project as _Project
    _Project.model_validate(project)  # outer boundary — fail fast on malformed

    def _mutate(latest_project: dict):
        # P1-3 part 12 (Variant 1 simplified): inner validate for race
        # protection — `_Project.model_validate(...)` raises
        # ValidationError unconditionally on shape mismatch (race
        # protection requires deterministic raise; NOT gated by
        # CINEMA_STRICT_SCHEMA).  Then dict-write under the lock.
        # See docs/MIGRATION-PATTERN-pydantic-caller.md §"Variant 1".
        _Project.model_validate(latest_project)
        # ... existing dict-write logic (no typed-iterate needed) ...
        return MutationResult(...)

    result = mutate_project(pid, _mutate, snapshot=project)
    # ... existing post-mutator response handling ...
```

**Comment-block phrasing**: use the wording above (`unconditionally on shape mismatch`), NOT "raises in CINEMA_STRICT_SCHEMA mode" — see §"OBS#1 phrasing convention".

### Variant 1 full (8 sites: L607, L772, L795, L956, L1079, L1696, L1722, L1761)

**Shape:** mutator does ID-lookup-then-mutate, e.g., `for shot in scene["shots"]: if shot["id"] == sid: shot["prompt"] = ...`. Typed-iterate-for-find is the canonical race-protection shape.

**Recipe (mirror `update_scene` or `update_scene_shots` canonical at `f8cd45f` / `c296105`):**

```python
def _mutate_project(latest_project: dict):
    # P1-3 part 12 (Variant 1 full): inner validate + typed-iterate-
    # for-find.  `_Project.model_validate(latest_project)` validates
    # the latest snapshot the mutator sees; race protection requires
    # this deterministic raise on shape mismatch (NOT gated by
    # CINEMA_STRICT_SCHEMA).  Typed-iterate for FIND; dict-write to
    # MUTATE under the lock.  Index parity between latest_typed.X[i]
    # and latest_project["X"][i] is preserved by pydantic list-order
    # invariant (see pattern doc §"Caveat: pydantic list-order
    # preservation").
    latest_typed = _Project.model_validate(latest_project)
    for i, char in enumerate(latest_typed.characters):
        if char.id == cid:
            # dict-write under lock; index from typed iteration
            latest_project["characters"][i]["name"] = new_name
            # ... other field writes ...
            return MutationResult(latest_project["characters"][i], save=True)
    return MutationResult(None, save=False)
```

**Per-site specialization notes** (per the table above):

- **L956 `api_update_object`** — Project has `extra="allow"` and NO typed `Object` class. Inner `_Project.model_validate(latest_project)` STILL applies (race protection on the project shape). Typed-iterate-for-find is NOT applicable for `objects`; use raw-dict iterate, like B-005's `remove_object` deviation. Document the deviation in the inline comment block per the B-005 precedent.
- **L1079 `api_update_location`** — outer ALREADY migrated (P1-3 part 5; `_Project.model_validate(project)` at L1040). DO NOT add a second outer validate; DO NOT add a duplicate import. Only add the inner validate + typed-iterate-for-find inside `_mutate_project` at L1059.
- **L607, L772, L795, L1696, L1722, L1761** — standard V1 full recipe; no per-site quirks beyond the table's notes.

### Base read-only (1 site: L1828 `api_restart_shot::_resolve_scene_id`)

**Shape:** mutator is read-only (`save=False` always); returns a derived value (scene_id string) for the route to use post-lock-release. The per-project lock is acquired for invariant consistency across the read, established pattern.

**Recipe:**

```python
def api_restart_shot(pid, shot_id):
    project = load_project(pid)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    from domain.models import Project as _Project
    _Project.model_validate(project)  # outer boundary; race protection on validation

    def _resolve_scene_id(latest_project: dict):
        # P1-3 part 12 (Base read-only): no inner validate required —
        # save=False means no race-write to protect; outer boundary
        # validate is sufficient.  Typed-iterate is OPTIONAL here for
        # readability; raw-dict iterate is also acceptable since
        # there's no race-write to protect against.  See pattern doc
        # §"Pattern variants" / Base entry.
        for scene in latest_project["scenes"]:
            for shot in scene["shots"]:
                if shot["id"] == shot_id:
                    return MutationResult(scene["id"], save=False)
        return MutationResult(False, save=False)

    result = mutate_project(pid, _resolve_scene_id)
    # ... existing dispatch to pipeline.restart_shot(...) using result ...
```

**Implementer judgment:** if typed-iterate is cleaner than the existing raw-dict double-loop, switch; if the existing shape is well-tested, preserve. NOT a Variant 1 inner-validate site.

### Mixed-shape conditional (1 site: L1863 `api_regenerate_shot`)

**Shape:** mutator conditionally writes (V1 simplified shape if `new_prompt` is set) or returns derived value without writing (Base read-only shape otherwise). Two paths in one mutator.

**Recipe:**

```python
def _mutate_project(latest_project: dict):
    # P1-3 part 12 (Mixed-shape conditional): inner validate is
    # required UNCONDITIONALLY because the write path (new_prompt
    # set) does dict-write under lock and needs race-protection on
    # the latest snapshot shape.  The no-write path benefits from
    # the same validate for consistency (cheap; ~1-2ms per call).
    # `_Project.model_validate(...)` raises ValidationError
    # unconditionally on shape mismatch (NOT gated by
    # CINEMA_STRICT_SCHEMA).  See pattern doc §"Variant 1".
    _Project.model_validate(latest_project)
    for scene in latest_project["scenes"]:
        for shot in scene["shots"]:
            if shot["id"] == shot_id:
                if new_prompt:
                    shot["prompt"] = new_prompt
                    return MutationResult(scene["id"], save=True)
                else:
                    return MutationResult(scene["id"], save=False)
    return MutationResult(False, save=False)
```

**Comment phrasing:** explicitly note the dual-path nature in the inline comment so future readers don't refactor away the conditional `save=`.

---

## OBS#1 phrasing convention (per Lane V #11 carry-forward)

When writing the inline comment block at EACH new site, use **the corrected phrasing**:

> `_Project.model_validate(...)` raises `ValidationError` UNCONDITIONALLY on shape mismatch — race protection requires deterministic raise. NOT gated by `CINEMA_STRICT_SCHEMA` (that env var only applies to `_validate_project`'s warn-mode wrapper, not bare model_validate).

DO NOT write "raises in CINEMA_STRICT_SCHEMA mode" or any variant that implies the validate is conditional on the env var. The Variant 1 race-protection contract requires the unconditional raise; the misleading phrasing originated in B-005's adjacent sites (cycle-11 Lane V #11 OBS#1) and should not propagate.

Pre-existing comment text at the 15 sites: **none** of the existing 15 inline comment blocks (verified by survey) have the misleading phrasing — this is a new-text-only concern.

---

## Out of scope (pre-existing concerns; do NOT fix in B-006-broad-B)

Surfaced by the Lane C survey; flagged here so the implementer ignores them. Each will become a separate follow-up slice or backlog item.

### 1. HTTP-error-shape None-swallow (6 sites)

L420, L691, L772, L795, L831, L1301 silently swallow `None` returns from `mutate_project` (which signals "project not found"). These endpoints return 2xx success even when the project does not exist. The migration does NOT fix this — it preserves existing behavior. But: after the migration adds the outer `_Project.model_validate(project)`, malformed (not missing) projects will raise `ValidationError` instead of silently failing partway through. Missing-project behavior remains broken; report this as a separate follow-up issue if you observe a regression while testing.

### 2. L691 background-thread exception swallow

`api_train_lora`'s `_runner` thread wraps the entire mutator in `except Exception as me: print(...)`. New `ValidationError` raised by inner validate will also be swallowed by this catch. NOT B-006-broad-B's job to surface the exception path. Document in the inline comment block that ValidationError-on-shape-mismatch in this background mutator will be silently logged via the existing `[LoRA]` print handler; do NOT modify the exception handler.

### 3. L831 `api_upload_style_board` 2xx-on-missing-project

The response uses `len(refs or [])` which evaluates to `0` when `refs` is `None`. After migration, `_Project.model_validate(project)` at the outer boundary will raise on malformed projects, so the "missing project" path remains 2xx with `total_refs: 0`. Implementer does NOT add a None-check or `if not project: 404` — preserve existing shape. (The pre-existing 2xx-on-missing-project bug pre-dates B-006-broad-B.)

### 4. Test coverage gaps

The existing `tests/unit/test_web_server.py` (or wherever route tests live) may not have coverage for malformed-project ValidationError at the 15 routes. Implementer adds ONE template-level test per `tests/unit/test_project_models.py:TestMigratedCaller` pattern (per pattern doc §"Unhappy-path test recipe", lines 195-203). Do NOT add per-route ValidationError tests — the template-level contract is sufficient. If template-level tests are already covering this from B-005, no new tests needed.

---

## Estimated commit shape

**Single commit:**

```
feat(schema): P1-3 part 12 — migrate web_server.py mutators (15 sites) to Project.model_validate with Variant 1 / Base / Mixed-shape per site
```

**Per-site bucket:**

| Bucket | Sites | LoC delta estimate (added) | Inline comment block |
|---|---|---|---|
| V1 simplified | 5 sites | ~3-5 LoC each = 15-25 LoC | yes, 5 blocks |
| V1 full | 8 sites | ~5-8 LoC each = 40-65 LoC | yes, 8 blocks |
| Base read-only | 1 site (L1828) | ~3-5 LoC | yes, 1 block |
| Mixed-shape | 1 site (L1863) | ~5-7 LoC | yes, 1 block |
| Imports + cross-cutting | — | ~3-5 LoC | — |
| **Total estimate** | **15 sites** | **~80-130 LoC added; ~10-20 LoC modified** | **15 blocks** |

**Tests:**

- Verify `tests/unit/test_project_models.py::TestMigratedCaller` (or wherever template-level unhappy-path tests live as of B-005) already covers `_Project.model_validate(...)` ValidationError. If yes: no new tests.
- If no template-level coverage exists for the mutator-inner-validation contract at web_server.py call sites specifically, add +1 race-protection test mirroring B-005's `tests/unit/test_project_manager.py::TestMutatorVariant1RaceProtection` shape.

**Pytest baseline:** 866 → expected 866 (no new tests if template covers) or 867-869 (if 1-3 new tests added).

**Smoke + tsc:** unchanged; no frontend changes. `.venv/bin/python scripts/ci_smoke.py` should remain OK.

---

## Verification commands

Implementer MUST run these and capture output in the implementation report:

```
# 1. Rule #12 grep-the-writes — verify model_validate is the canonical entry
grep -n "_Project.model_validate" web_server.py
# Expected: 15 new occurrences post-migration (1 outer per site) + any pre-existing
# from P1-3 part 5 at L1040 (don't double-count)

# 2. Rule #13 symmetric audit re-verification — confirm all 15 sites touched
grep -n "mutate_project(" web_server.py | grep -v "def _mutate" | grep -v "^[0-9]*: *#"
# Expected: 15 outer call sites confirmed

# 3. Pytest baseline
.venv/bin/python -m pytest tests/unit/ --tb=no -q | tail -5
# Expected: 866 → 866-869 (depending on test additions)

# 4. Smoke
.venv/bin/python scripts/ci_smoke.py
# Expected: OK

# 5. tsc + npm run build (no frontend changes; sanity)
(cd web && npx tsc --noEmit)
(cd web && npm run build)
# Expected: clean; build successful
```

---

## Before you begin (ask first if any of these)

If the implementer subagent has questions about any of the following BEFORE implementing, ask via the dispatch caller (director-seat):

1. **L956 `api_update_object` deviation handling** — is the B-005 `remove_object` precedent (raw-dict iterate inside inner-validate-confirmed-shape) the right pattern, or do you want a different shape?
2. **L1828 typed-iterate vs raw-dict** — preserve existing raw-dict double-loop for stability, or modernize to typed-iterate while touching the comment block?
3. **L1863 Mixed-shape comment block** — single block at the top of `_mutate_project` describing both paths, or separate notes at the `if new_prompt:` and `else:` branches?

If you have no questions on these (or they're unambiguous from the per-site notes), proceed.

---

## Your job (numbered)

1. **Read** `docs/MIGRATION-PATTERN-pydantic-caller.md` in full. Familiarize with Variant 1 / Variant 2 / Base / Mixed-shape recipes + the GOTCHAS section.
2. **Read** `c296105` (`git show c296105 -- domain/project_manager.py`) — see B-005's 10-site application of Variant 1 + the `remove_object` deviation handling. Note the inline comment block style for use here.
3. **Read** `f8cd45f` (`git show f8cd45f -- domain/scene_decomposer.py`) — see Variant 1 canonical at `update_scene_shots`.
4. **Pre-implementation Rule #13 spot-check** — re-grep `mutate_project(` in `web_server.py` and verify 15 outer call sites match this brief's table. Surface any discrepancy in your status report BEFORE migration.
5. **Migrate 15 sites in one commit.** Apply per-site recipe from §"Variant recipe / per-bucket". Maintain inline comment block style consistent with `c296105`.
6. **Run verification commands** above; capture output for the report.
7. **Self-review** for: (a) inline comment phrasing matches OBS#1 convention (no "CINEMA_STRICT_SCHEMA mode"); (b) L1079 outer is NOT duplicated; (c) L1828 has NO inner validate (Base read-only); (d) L1863's both paths visible in one mutator; (e) L956 deviation documented per B-005 precedent.
8. **Commit** with the message shape above; include a per-bucket table in the commit body listing the 15 sites + variant fit (mirror B-005's commit body style).

---

## When you're in over your head

Report **BLOCKED** with what you tried if:

- Any of the 15 sites can't be classified into V1 simplified / V1 full / Base / Mixed (i.e., you find a site shape this brief doesn't cover).
- Outer boundary validate at any site would require restructuring more than the per-site recipe shows (e.g., the route already has a different validation mechanism that conflicts).
- Test additions would break or skip more than 5 existing tests (rollback risk).
- `_Project.model_validate(...)` raises on a project that previously worked in production (genuine shape regression — pre-existing data has a hidden issue).

Reports are evaluated for: (a) all 15 sites correctly migrated per their variant; (b) no out-of-scope changes; (c) inline comment blocks using OBS#1-corrected phrasing; (d) pytest baseline matches expectation; (e) commit body lists per-site variant fits.

---

## Report format

After the commit lands, your status report should include:

- **Status:** DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT
- **Sites migrated:** 15 (or partial; specify which sites if partial)
- **Per-bucket distribution actually applied:** V1 simplified ×N, V1 full ×N, Base ×N, Mixed ×N (compare to brief's 5+8+1+1=15)
- **Any deviations from the per-site recipe:** site + reason (e.g., "L956: applied B-005 `remove_object` deviation per pre-spec guidance")
- **Rule #13 spot-check finding:** sites matching brief / discrepancies
- **Verification command output:** all 5 verification commands' results
- **Files changed:** paths only
- **Commit SHA:** captured from `git commit` stdout (authoritative as of B-003 Option E)
- **Self-review findings:** any pre-existing concerns observed but NOT fixed (cross-check against §"Out of scope")

---

## Lane V plan (post-implementer commit)

Director-seat (or whichever seat is active) will dispatch parallel cold-context Lane V reviewers (spec + code-quality) per Rule #9:

- **Spec reviewer:** verify each of the 15 sites against this brief's per-site recipe + variant table; flag any unaccounted-for deviation. Cite Rule #12 verification commands in the reviewer prompt.
- **Code-quality reviewer:** verify lock-window correctness, inner-validate-first ordering, index-parity preservation (where applicable), inline comment phrasing consistency with OBS#1 convention.

Both reviewer prompts will include CC-2 hallucination guard + Rule #12 grep-the-writes + Rule #13 symmetric-endpoint audit instructions per cycle-11 precedent.

Cost envelope projection: implementer ~80-120k tokens + Lane V ~200-250k tokens = ~280-370k subagent tokens for B-006-broad-B end-to-end. Within v4.1 budget envelope at ~2.65-2.74M cumulative across all Lane V dispatches.

---

*Cycle-12 director-side implementer brief for B-006-broad-B. Self-contained for cold-context Lane B dispatch. Single commit; 15 sites; 4 variant buckets (V1 simplified ×5 + V1 full ×8 + Base ×1 + Mixed ×1); ~80-130 LoC + 0-3 tests; ~280-370k subagent token envelope. Per-site Lane C survey already done; implementer verifies + applies. Pre-existing out-of-scope concerns (6 None-swallows + L691 thread + L831 2xx-on-missing) flagged explicitly to prevent scope creep. OBS#1 corrected phrasing convention codified for new inline comment blocks. Pattern-doc cross-reference + canonical-site SHAs + Rule #9/#12/#13 discipline citations included. Brief is dispatch-ready; director-seat assembles into subagent prompt at execution time.*
