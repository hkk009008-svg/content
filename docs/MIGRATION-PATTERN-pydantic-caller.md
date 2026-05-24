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
