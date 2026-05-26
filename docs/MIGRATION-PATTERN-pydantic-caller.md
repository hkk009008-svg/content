# P1-3 caller migration pattern (Pydantic-typed access)

_Session 10 — 2026-05-24. This doc is the canonical recipe for Sessions 12+
to migrate additional callers from raw-dict access to Pydantic-typed access._

---

## WHEN to migrate

Migrate a call site when ALL of these hold:

1. The call site reaches into `project["scenes"]`, `scene["shots"]`, or their
   nested dicts using key access (e.g. `shot.get("target_api", "AUTO")`).
2. The function is **read-only or has a trivially-isolated write-back** (see
   GOTCHAS below on write-back).
3. The call site is a stable endpoint or module entry-point (not deep utility
   code that many callers share — those migrate last).

Do NOT migrate:

- `load_project` / `save_project` return types (still `dict`; boundary stays
  dict until enough callers are migrated for a cutover decision).
- Sites where `model_validate` overhead matters on a per-frame hot path (use
  profiling before migrating those).

---

## HOW to migrate

### Step 1 — Add `model_validate` at the function boundary

```python
from domain.models import Project as _Project  # local import is fine; avoids circular risk

project_typed = _Project.model_validate(project)  # project is the raw dict from load_project
```

`model_validate` is idempotent on already-validated dicts. It will warn (or
raise with `CINEMA_STRICT_SCHEMA=1`) on schema violations before you touch
any attribute.

### Step 2 — Switch dict access to attribute access

| Before | After |
|--------|-------|
| `project["scenes"]` | `project_typed.scenes` |
| `scene["id"]` | `scene.id` |
| `scene.get("characters_present", [])` | `scene.characters_present` (defaults to `[]`) |
| `shot.get("target_api", "AUTO")` | `shot.target_api or "AUTO"` — see GOTCHAS |
| `scene.get("mood", "neutral")` | `scene.mood or "neutral"` — see GOTCHAS |

### Step 3 — Inline comment block at the migration site

```python
# P1-3 migration template (Session 10): validate to Pydantic at the
# function boundary, then access via attributes.  Future call sites
# follow this pattern (Sessions 12+).  See
# docs/MIGRATION-PATTERN-pydantic-caller.md for the full recipe.
```

### Step 4 — Write-back (only if needed)

If the function mutates the project, convert back to `dict` via
`project_typed.model_dump()` before passing to `save_project`:

```python
mutated = project_typed.model_dump()
save_project(mutated)
```

Do NOT pass a Pydantic model object to `save_project` — it expects `dict`.

---

## Canonical example — Session 10

**Target:** `web_server.py`, `api_generate_dialogue` endpoint (line ~1096).

**Before:**
```python
scene = next((s for s in project["scenes"] if s["id"] == sid), None)
chars = [c for c in project["characters"] if c["id"] in scene.get("characters_present", [])]
lines = generate_dialogue(scene, chars, scene.get("mood", "neutral"), language=lang)
```

**After:**
```python
from domain.models import Project as _Project
project_typed = _Project.model_validate(project)
scene = next((s for s in project_typed.scenes if s.id == sid), None)
chars = [c for c in project_typed.characters if c.id in scene.characters_present]
lines = generate_dialogue(scene.model_dump(), [c.model_dump() for c in chars],
                          scene.mood or "neutral", language=lang)
```

Why `scene.model_dump()` when passing to `generate_dialogue`? That function
expects a `dict` (Session 8 boundary: downstream helpers still use dict
access internally). Pass `.model_dump()` until those helpers are also
migrated.

---

## GOTCHAS

### Default-value translation (the `or "AUTO"` pattern)

Pydantic model defaults for optional strings are `""` (empty string), NOT
the domain-specific defaults some dict callers used (e.g. `"AUTO"`,
`"neutral"`). Always use **call-site `or`** to restore the intended default:

```python
# CORRECT — preserves "AUTO" fallback without changing the Pydantic model
api = shot.target_api or "AUTO"
mood = scene.mood or "neutral"

# WRONG — changing Pydantic model default ripples to EVERY caller of Project
# class Shot(BaseModel):
#     target_api: str = "AUTO"   # DON'T DO THIS — it changes the shared model
```

Document any non-empty default you encounter in the migration inline comment.

### Write-back via `model_dump`

`model_dump()` serializes only declared fields + extra fields (because
`extra="allow"`). If the raw dict had undeclared top-level keys that
`extra="allow"` carried through, `model_dump()` includes them. Round-trip
fidelity is high but do a sanity diff `raw vs model_dump()` the first time
you migrate a mutating call site.

### Performance of `model_validate` per request

`model_validate` on a typical project (5 scenes × 10 shots) takes ~1-2 ms.
This is acceptable for HTTP endpoint handlers. Do NOT use it in tight loops
(e.g. per-frame rendering or per-take polling). For those, migrate only the
outer boundary and keep inner loops on the typed object you already have.

### `generate_dialogue` and other helpers still expect `dict`

Until Sessions 12+ migrate helper functions, pass `.model_dump()` when
calling helpers that use key-access internally. The type annotations will
tell you: if a helper is typed `scene: dict`, pass `scene.model_dump()`.

---

## Unhappy-path test recipe

_Added 2026-05-25 per BACKLOG.md B-001 (originated from operator-seat's
Lane V #3 on `e1b72ca`, F2 advisory). Closes the inherited test gap
for ALL P1-3 migrations (S10 + part 3 + part 4 + future part N) at
the template level rather than per-migration._

### Why this matters

The migration moves the failure surface for malformed projects from
**"runtime `KeyError` or silent default partway through the function"**
to **"`pydantic.ValidationError` raised at the function boundary."**
That behavioral-contract change deserves a regression test pin so
future refactors don't silently relax the boundary (e.g. by removing
`model_validate` and regressing to dict access, or by wrapping it in
a try/except that swallows the exception).

### What to test

For each TEMPLATE (not per migration), assert that
`Project.model_validate()` raises `ValidationError` when given a
malformed project dict — missing a required field (e.g. `id`) or
with a type-mismatched array (e.g. `scenes: "not a list"`). The
tests live in `tests/unit/test_project_models.py:TestMigratedCaller`
alongside the per-migration regression tests.

### Example tests

```python
import pytest
from pydantic import ValidationError
from domain.models import Project

def test_project_model_validate_raises_on_missing_id(self):
    """The migrated caller's boundary raises ValidationError on a
    malformed dict, NOT KeyError mid-function."""
    raw = self._make_project_dict()
    del raw["id"]  # Project.id is required
    with pytest.raises(ValidationError):
        Project.model_validate(raw)

def test_project_model_validate_raises_on_malformed_scenes(self):
    """Type-level malformation also raises at the boundary."""
    raw = self._make_project_dict()
    raw["scenes"] = "not a list"  # type mismatch with List[Scene]
    with pytest.raises(ValidationError):
        Project.model_validate(raw)
```

### Why one template-level test set, not per-migration

The unhappy-path contract is set by `Project.model_validate()`
itself, not by any specific call site. One template-level test pair
covers the contract for ALL P1-3 migrations. Per-migration unhappy-
path tests would be redundant AND would couple test code to specific
call-site implementations — making any future caller-side refactor
needlessly noisy.

### When per-migration unhappy-path tests ARE warranted

Only when the migrated caller explicitly wraps `model_validate` in a
`try`/`except ValidationError` block and translates the exception to
a domain-specific error (e.g. an HTTP 400 response). In that case,
test the translation behavior at the caller level. If the caller
lets `ValidationError` propagate unchanged (the default migration
shape — and the shape S10 / parts 3 / 4 all use), the template-level
tests above are sufficient.

---

## Pattern variants (cycle-10 additions: parts 9 + 10)

The base pattern above (validate-at-boundary + typed attribute access)
handles read-only call sites. Cycle 10 surfaced two variants for
non-trivial cases. Both build on the base; both are validated by
production code at the cited SHAs.

### Variant 1 — Mutator-inner-validation (part 9, `f8cd45f`)

**When:** the call site is a mutator that needs to read typed shape
WHILE holding the per-project `mutate_project` lock, then dict-write
back to the locked record.

**Canonical site:** `domain/scene_decomposer.py::update_scene_shots`.

**Shape:**

```python
def update_scene_shots(project_id: str, scene_id: str, new_shots: list[dict]) -> dict:
    # OUTER boundary validate: the call site is the boundary; we
    # validate the project shape BEFORE entering the mutator so
    # malformed projects fail fast (lock not even acquired).
    project = load_project(project_id)
    from domain.models import Project as _Project
    _Project.model_validate(project)  # boundary check; ignore return

    def _mutator(latest_project: dict):
        # INNER mutator-scope validate: revalidate the latest_project
        # snapshot the mutator sees (it may have changed between
        # outer validate and lock acquisition). Use the typed object
        # for the read-shape walk; write back to the dict.
        latest_typed = _Project.model_validate(latest_project)
        for scene in latest_typed.scenes:
            if scene.id == scene_id:
                # Dict-write under the lock: mutator MUST write to
                # latest_project (the lock-held dict), NOT to
                # latest_typed (a snapshot). Typed-iterate to FIND
                # the scene; dict-write to MUTATE it.
                idx = latest_typed.scenes.index(scene)
                latest_project["scenes"][idx]["shots"] = new_shots
                return MutationResult(...)
        return MutationResult(success=False, ...)

    return mutate_project(project_id, _mutator)
```

**Why this shape:**

- **Outer boundary validate** is the same as the base S10 pattern;
  fails fast on malformed projects so the lock isn't even acquired
  for a doomed mutation.
- **Inner mutator validate** handles the race: between outer-validate
  and lock-acquisition, another writer may have changed the project
  shape. The inner validate runs on the lock-held `latest_project`
  snapshot the mutator actually sees.
- **Index-by-typed-iteration** finds the target scene via typed walk
  (`scene.id == scene_id` is type-safe); the matched index is then
  used to dict-write back. Typed-and-dict in parallel: typed for
  reading, dict for writing under the lock.
- **Redundant validation cost** (~2-4 ms per mutation) is acceptable
  for mutator paths (low-frequency relative to read paths).

**Caveat: pydantic.list-order preservation.** This shape relies on
`latest_typed.scenes[i]` corresponding to `latest_project["scenes"][i]`.
Pydantic's `List[Scene]` field doesn't reorder; this holds. If a
future Scene field adds a custom validator that reorders, the index
parity breaks and the dict-write would write to the wrong scene. Pin
this invariant with a regression test if list order ever matters.

### Variant 1 sub-pattern: inner-only (no-prior-load case)

_Codified 2026-05-27 cycle-12 from cluster M1 (Lane V #12 broad-A) +
M-1 + M-2 (Lane V #13 operator-side broad-B). Closes the "outer-
omitted" terminology gap surfaced across both Lane V dispatches._

**When:** the call site has NO `load_project()` preamble — route
handlers that go directly to `mutate_project(pid, ...)` without
first loading the dict, OR helper functions that take a `project_id:
str` and have no project dict at their boundary. Outer boundary
validate is not structurally available; inner validate alone
preserves race-protection because it runs on the lock-held snapshot.

**Shape:**

```python
def api_<endpoint>(pid):
    # NO load_project(pid) preamble; no outer Project.model_validate(...)
    # available at the route boundary.

    def _mutator(latest_project: dict):
        # P1-3 sub-pattern (Variant 1 inner-only, no prior load):
        # inner validate is the race-protection point.
        # `Project.model_validate(latest_project)` runs on the lock-held
        # snapshot; raises ValidationError unconditionally on shape
        # mismatch. Outer boundary validate is OMITTED because no prior
        # load exists at the route scope.
        Project.model_validate(latest_project)
        # ... existing dict-write logic (Variant 1 simplified OR full) ...
        return MutationResult(...)

    result = mutate_project(pid, _mutator)
    # ... existing response handling ...
```

**Race-protection equivalence to full Variant 1:** the canonical
Variant 1 shape uses outer + inner validate, but the outer is a
fast-fail optimization (avoid lock acquisition for a doomed mutation),
NOT a race-protection requirement. The inner validate on the lock-
held snapshot is what preserves the race-protection contract. When
no outer validate is available, the inner alone is sufficient.

### Base sub-pattern: validate-inside-mutator (no-prior-load case)

_Codified 2026-05-27 cycle-12 from M-1 (Lane V #13 operator-side
broad-B Site #14 brief-spec terminology gap)._

**When:** the call site is read-only (Base; `save=False` always) AND
has no prior `load_project()` preamble. Place a SINGLE
`Project.model_validate(...)` inside the mutator function body (the
lock-held snapshot point). This is functionally equivalent to outer-
validate-then-read because the lock holds the snapshot stable from
validate-call through return.

**Shape:**

```python
def api_<readonly_endpoint>(pid, target_id):
    # NO load_project(pid) preamble.

    def _resolver(latest_project: dict):
        # P1-3 Base sub-pattern (no-prior-load): single validate
        # inside the mutator; lock-held snapshot is the validation
        # point. save=False always — read-only resolver shape.
        Project.model_validate(latest_project)
        # ... existing read logic ...
        return MutationResult(<derived_value>, save=False)

    result = mutate_project(pid, _resolver)
    # ... use result downstream ...
```

**Important terminology note:** the "single validate inside the
mutator" for the Base sub-pattern is NOT the same as the "inner
validate" of Variant 1. There is no outer validate to pair with; the
single validate IS the boundary validate, just located inside the
mutator scope due to no-prior-load. Briefs that say "no inner validate"
for Base sites should be read as "no inner validate in the V1-paired
sense" — a single boundary validate at the lock-held snapshot is the
correct shape.

**Canonical sites of inner-only / no-prior-load patterns:**

| Site | Shape | Reason |
|---|---|---|
| `cinema/screening.py::mark_screening_approved` (broad-A site #1) | V1 simplified inner-only | Takes `project_id: str`, not project dict |
| `cinema/screening.py::mark_shot_needs_reassembly` (broad-A site #2) | V1 simplified inner-only | Takes `project_id: str` |
| `cinema/screening.py::clear_needs_reassembly` (broad-A site #3) | V1 simplified inner-only | Takes `project_id: str` |
| `cinema_pipeline.py::_persist_style_rules` (broad-A site #5) | V1 simplified inner-only | Helper called inside `start_pipeline`; outer validate at caller's scope, not function boundary |
| `domain/location_manager.py::get_location_prompt::_mutate` (broad-A site #6) | V1 mixed-shape inner-only | Helper called from many sites; cannot assume caller pre-validates |
| `web_server.py::api_update_project` (broad-B L485) | V1 simplified inner-only | Direct POST endpoint, no prior load |
| `web_server.py::api_train_lora::_runner` (broad-B L691) | V1 simplified inner-only | Background thread; closure captures pid |
| `web_server.py::api_reject_auto_approve` (broad-B L1696) | V1 full inner-only | Direct POST, no prior load |
| `web_server.py::api_update_shot_prompt` (broad-B L1722) | V1 full inner-only | Direct POST, no prior load |
| `web_server.py::api_update_shot` (broad-B L1761) | V1 full inner-only | Direct POST, no prior load |
| `web_server.py::api_restart_shot::_resolve_scene_id` (broad-B L1828) | Base no-prior-load | Read-only resolver; no prior load |

**Variant 1 production sites — full enumeration** (F2 uniformity pass — cycle 13 completion of cycle-12 broad-B drive-by):

**Cumulative through cycle-12:** **32 `mutate_project(...)` production callers migrated** to `Project.model_validate` discipline (1 part-9 canonical + 10 B-005 + 6 B-006-broad-A + 15 B-006-broad-B). Breakdown by primary classification: **30 Variant 1 strict** (full + simplified + inner-only sub-pattern); **1 Base sub-pattern** (read-only resolver, no prior load); **1 Mixed-shape conditional** (V1 + Base hybrid). Excludes test files; excludes Variant 2 sites (`continuity_engine.py` + `cinema_pipeline.py::_refresh_project_snapshot`) which use validate-before-swap discipline separately — see §"Variant 2" below.

**Part 9 canonical** (`f8cd45f`) — `domain/scene_decomposer.py` ×1:
- `update_scene_shots` (L895) — V1 full (outer + inner; typed iterate-for-find; dict-write under lock at parity index)

**B-005 part 11** (`c296105`) — `domain/project_manager.py` ×10 (all V1 full; all with prior load via `project: dict` parameter):
- `add_character` (L761) — V1 full
- `remove_character` (L786) — V1 full (typed-iterate-for-find)
- `add_object` (L828) — V1 full
- `remove_object` (L852) — V1 full (**raw-dict deviation**; Object model has `extra="allow"` so typed-iterate may lose fields — kept dict-iterate per the deviation gotcha)
- `add_location` (L883) — V1 full
- `remove_location` (L906) — V1 full (typed-iterate-for-find)
- `add_scene` (L945) — V1 full
- `update_scene` (L969) — V1 full (typed-iterate-for-find)
- `remove_scene` (L990) — V1 full (typed-iterate + filter; post-filter re-number order)
- `reorder_scenes` (L1020) — V1 full (typed-iterate + dict-build-by-id)

**B-006-broad-A** (`5b68776`) — 4 files ×6 sites:
- `cinema/screening.py::mark_screening_approved` (L258) — V1 simplified **inner-only (no-prior-load sub-pattern; takes `project_id: str`)**
- `cinema/screening.py::mark_shot_needs_reassembly` (L322) — V1 simplified **inner-only (no-prior-load sub-pattern)**
- `cinema/screening.py::clear_needs_reassembly` (L372) — V1 simplified **inner-only (no-prior-load sub-pattern)**
- `cinema/shots/controller.py::_mutate_shot` (L262) — V1 full (with prior load via `self.project`; 13 internal callers preserved dict-callback contract)
- `cinema_pipeline.py::_persist_style_rules` (L793, inner closure in `start_pipeline`) — V1 simplified **inner-only (no-prior-load sub-pattern; helper called inside orchestrator)**
- `domain/location_manager.py::get_location_prompt::_mutate` (L119, inner closure) — V1 mixed-shape **inner-only (no-prior-load sub-pattern; helper called from many sites)**

**B-006-broad-B (P1-3 part 12)** (`a0493dc`) — `web_server.py` ×15 (line numbers at-ship-time; post-`336403d` +3 shift):

V1 simplified (×5):
- `api_apply_language_defaults` (L420) — full V1 (outer + inner)
- `api_update_project` (L485) — **inner-only (no-prior-load sub-pattern)**
- `api_train_lora::_runner` (L691) — **inner-only (no-prior-load sub-pattern; background thread; ValidationError now logged with stack trace per `336403d` M-3 close — was swallowed by pre-existing thread handler at broad-B ship time per OOS)**
- `api_upload_style_board` (L831) — full V1 (outer + inner)
- `api_generate_style_rules` (L1301) — full V1 (outer + inner)

V1 full (×8):
- `api_update_character` (L607) — full V1
- `api_upload_driving_video` (L772) — full V1 (outer at L789 part 6; only inner+typed-iterate added)
- `api_clear_performance` (L795) — full V1
- `api_update_object` (L956) — full V1 (**raw-dict deviation**; `extra="allow"`)
- `api_update_location` (L1079) — full V1 (outer at L1145 part 5; only inner+typed-iterate added)
- `api_reject_auto_approve` (L1696) — **inner-only (no-prior-load sub-pattern)**
- `api_update_shot_prompt` (L1722) — **inner-only (no-prior-load sub-pattern)**
- `api_update_shot` (L1761) — **inner-only (no-prior-load sub-pattern)**

Base sub-pattern (×1):
- `api_restart_shot::_resolve_scene_id` (L1828) — **Base validate-inside-mutator (no-prior-load sub-pattern; single validate at lock-held snapshot; `save=False` always)**

Mixed-shape conditional (×1):
- `api_regenerate_shot` (L1863) — Mixed-shape (V1 simplified write path + Base no-write path; both share single inner validate)

### Variant 2 — Value-preserving-dict-ref (part 10, `1bc9263`)

**When:** the call site builds an id-keyed lookup for downstream
consumers that do dict-attribute access. The lookup VALUES must remain
the original dict references (not `model_dump` snapshots) so caller-side
mutations on the underlying dict are visible through the lookup.

**Canonical sites:**

- `domain/continuity_engine.py::CharacterContinuityTracker.__init__` —
  builds `self.characters = {char_id: dict_ref}`; consumer
  `build_character_prompt_fragment` does `char.get("name", ...)`.
- `domain/continuity_engine.py::LocationPersistence.__init__` —
  parallel shape for locations.
- `cinema_pipeline.py::CinemaPipeline._refresh_project_snapshot` —
  external-writer site that REBUILDS the same id-keyed lookups when
  the project snapshot is reloaded from disk.

**Shape:**

```python
class CharacterContinuityTracker:
    def __init__(self, project: dict):
        from domain.models import Project as _Project
        self.project = project
        project_typed = _Project.model_validate(project)
        # TYPED-ITERATE for the .id key extraction (type-safe walk
        # over Character objects); DICT-REF as the value (preserves
        # implicit contract: mutating project["characters"][0]["name"]
        # is visible through self.characters[char_id]["name"]).
        self.characters = {
            c.id: project["characters"][i]
            for i, c in enumerate(project_typed.characters)
        }
```

**Why this shape:**

- **Typed iteration for keys** uses the validated typed object's
  attribute access (`c.id`) — type-safe.
- **Dict references as values** preserves the consumer-side contract.
  Consumer sites continue to read via `.get("name", default)` against
  the dict; migrating consumer sites to typed attribute access is a
  separate slice.
- **Index-by-enumerate** pairs typed-iteration with dict-indexing.
  Same pydantic-list-order-preservation caveat as Variant 1.

**External-writer extension (cinema_pipeline.py:432-470 +
_refresh_project_snapshot's Lane V #9 I-1 fix at `<v5.1+ ship>`):**

When external code (not the `__init__`) needs to REBUILD the lookup
because the project state was reloaded, follow the same variant shape
PLUS the validate-before-swap discipline:

```python
def _refresh_project_snapshot(self, timeout: float = 10) -> Optional[dict]:
    latest = load_project(self.project["id"], timeout=timeout)
    if not latest:
        return None
    # VALIDATE FIRST on the loaded dict. If this raises ValidationError,
    # self.project must remain unchanged so tracker indices stay coherent
    # with prior state. (Lane V #9 I-1: pre-fix did clear → update →
    # validate, which left a partial-state window if validate raised.)
    from domain.models import Project as _Project
    latest_typed = _Project.model_validate(latest)
    self.project.clear()
    self.project.update(latest)
    # Rebuild id-keyed lookups using the variant-2 shape: typed iterate
    # for keys + dict-ref values.
    self.continuity.character_tracker.characters = {
        c.id: self.project["characters"][i]
        for i, c in enumerate(latest_typed.characters)
    }
    self.continuity.location_persistence.locations = {
        l.id: self.project["locations"][i]
        for i, l in enumerate(latest_typed.locations)
    }
    # Cross-class project-pointer rebinds happen AFTER validation +
    # swap, so a failed validation leaves these pointers unchanged.
    self.continuity.project = self.project
    self.continuity.character_tracker.project = self.project
    self.continuity.location_persistence.project = self.project
    self.director.project = self.project
    return self.project
```

**Regression test:** see
`tests/unit/test_refresh_project_snapshot.py` for the I-1
partial-state preservation test pair (validation-raises path + happy
path + None-on-load-failure path).

### Variant taxonomy summary

| Variant | When | Read-shape | Write-shape | Lock |
|---|---|---|---|---|
| Base (S10) | Read-only call sites WITH prior `load_project()` preamble | Outer-validate then typed attribute access | None | None |
| Base sub-pattern (no-prior-load) | Read-only call sites with NO prior `load_project()` preamble | Single validate inside mutator + typed read | None (`save=False`) | per-project mutate_project lock (acquired for snapshot consistency) |
| Variant 1 full (part 9) | Mutator call sites WITH prior `load_project()` preamble | Outer + inner validate; typed iterate-for-find | Dict-write under lock at parity index | per-project mutate_project lock |
| Variant 1 inner-only sub-pattern (cycle-12) | Mutator call sites with NO prior `load_project()` preamble (direct POST handlers; helpers taking `project_id: str`) | Inner validate only; typed iterate (V1 full) or simplified | Dict-write under lock | per-project mutate_project lock |
| Variant 2 (part 10) | Lookup builders (init or external) | Typed iterate for keys | Dict-ref values (preserved) | None for init; external-writer site adds validate-before-swap discipline |

When choosing a variant, ask:

1. Is the call site read-only?
   - If YES + `load_project()` preamble available → **Base.**
   - If YES + NO `load_project()` preamble → **Base sub-pattern (no-prior-load): single validate inside mutator.**
2. Is the call site a mutator?
   - If YES + `load_project()` preamble available → **Variant 1 full or simplified** (outer + inner).
   - If YES + NO `load_project()` preamble (direct POST handler; helper taking `project_id: str`) → **Variant 1 inner-only sub-pattern.**
3. Is the call site building an id-keyed lookup whose CONSUMERS need
   to see live dict-state via the lookup values? → **Variant 2.**
4. Is the call site an EXTERNAL writer rebuilding a Variant-2 lookup
   on project reload? → **Variant 2 + validate-before-swap discipline.**

All variants share the same R12 (brief-level grep-the-writes)
discipline for symbol verification + the same template-level unhappy-
path test recipe above. The inner-only sub-patterns preserve the same
race-protection contract as their full counterparts; the outer validate
is a fast-fail optimization, NOT a race-protection requirement.
