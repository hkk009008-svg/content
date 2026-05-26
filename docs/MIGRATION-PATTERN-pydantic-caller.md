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

**Additional Variant 1 production sites** (F2 uniformity pass — cycle 12):

B-005 part 11 (`c296105`) — `domain/project_manager.py` ×10: `add_character`,
`remove_character`, `add_object`, `remove_object` (raw-dict deviation;
`extra="allow"`), `add_location`, `remove_location`, `add_scene`,
`update_scene`, `remove_scene`, `reorder_scenes`.

B-006-broad-A (`5b68776`) — `cinema/screening.py` ×3 (simplified inner-only),
`cinema/shots/controller.py` ×1 (full; dict-callback API preserved),
`cinema_pipeline.py` ×1 (simplified inner-only), `domain/location_manager.py`
×1 (mixed-shape inner-only).

B-006-broad-B (this, P1-3 part 12) — `web_server.py` ×15:
V1 simplified (×5): `api_apply_language_defaults` (L420), `api_update_project`
(L485, inner-only; no prior load), `api_train_lora` background `_runner`
(L691, inner-only; ValidationError swallowed by pre-existing thread handler),
`api_upload_style_board` (L831), `api_generate_style_rules` (L1301).
V1 full (×8): `api_update_character` (L607), `api_upload_driving_video` (L772;
outer already at L789 part 6), `api_clear_performance` (L795),
`api_update_object` (L956; raw-dict deviation, `extra="allow"`),
`api_update_location` (L1079; outer already at L1145 part 5),
`api_reject_auto_approve` (L1696), `api_update_shot_prompt` (L1722),
`api_update_shot` (L1761).
Base read-only (×1): `api_restart_shot::_resolve_scene_id` (L1828).
Mixed-shape conditional (×1): `api_regenerate_shot` (L1863).

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
| Base (S10) | Read-only call sites | Typed attribute access | None | None |
| Variant 1 (part 9) | Mutator call sites | Typed iterate (outer + inner) | Dict-write under lock | per-project mutate_project lock |
| Variant 2 (part 10) | Lookup builders (init or external) | Typed iterate for keys | Dict-ref values (preserved) | None for init; external-writer site adds validate-before-swap discipline |

When choosing a variant, ask:

1. Is the call site read-only? → **Base.**
2. Is the call site a mutator? → **Variant 1.**
3. Is the call site building an id-keyed lookup whose CONSUMERS need
   to see live dict-state via the lookup values? → **Variant 2.**
4. Is the call site an EXTERNAL writer rebuilding a Variant-2 lookup
   on project reload? → **Variant 2 + validate-before-swap discipline.**

All three variants share the same R12 (brief-level grep-the-writes)
discipline for symbol verification + the same template-level unhappy-
path test recipe above.
