# P1-1 Slice 2 — Max-Tier Multi-Character Identity (offline code) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make max-tier keyframes condition up to two secondary characters — per-secondary LoRA chaining (spec §3(b)) plus a dual ReActor face-swap rescue (spec §3(c) Pass A) — all code + unit tests pod-independent; live rendering waits for the bundled pod session.

**Architecture:** The slice-1 promise layer (router → `IdentityStrategy` → take metadata → per-char validation → scorecard) is reused wholesale: the router's max arm lifts from the `MAX_TIER_PRIMARY_ONLY` stub to `MAX_TIER_MULTI_LORA`, secondary specs ride the *existing* `secondary_char_refs` kwarg (their `to_dict()` simply grows LoRA fields), and `quality_max.py` gains two new **pure, idempotent** graph-surgery injectors: the LoRA chain runs right after `_inject_identity`; the faceswap splice runs AFTER `_inject_post_passes` (whose SUPIR-absent branch re-feeds node 950 from a 610-priority list and would silently bypass an earlier-injected 611 — adversarial plan review, verified at quality_max.py:597-602). Both re-run on the PuLID-boost retry as cheap defensive insurance (the retry's `_inject_identity` re-call cannot actually break the chain today — see ground truth — but idempotent re-injection protects against future `_inject_identity` changes). Trigger tokens — stored but never read at inference today — get one pure prompt-assembly helper inside the max tier.

**Tech Stack:** Python (graph surgery on `pulid_max.json` dicts), pytest (`tests/unit/`), no new dependencies, no pod access.

---

## Ground truth this plan is built on (verified 2026-06-11 at HEAD `81ea83c`; anchors re-verified during the 4-lens plan review at `a8ff247` — the `67a179c` desync disposition touched phase_c_assembly.py without moving any anchor cited here. Re-verify anchors at execution time as usual.)

| Fact | Anchor |
|---|---|
| Router max arm is a stub: `tag = MAX_TIER_PRIMARY_ONLY  # slice 2 lifts this to MULTI_LORA`; NO secondary specs are built on the max path | cinema/shots/controller.py:316-317 |
| `MAX_TIER_MULTI_LORA` constant does NOT exist yet (docstring reserves the name) | cinema/shots/strategy.py:7,12-15 |
| `CharIdentitySpec` fields: char_id, reference, identity_anchor, fidelity, multi_angle_refs — NO lora fields | cinema/shots/strategy.py:19-31 |
| **`secondary_char_refs` is DROPPED at the max dispatch** — forwarded into `generate_ai_broll` but not into `generate_ai_broll_max` | phase_c_assembly.py:125-145 |
| `generate_ai_broll_max` signature ends at `ctx`; no secondary/trigger params | quality_max.py:701-719 |
| **Nothing reads `char_lora_triggers` at inference** (grep: only prep/, scripts/) | scripts/_register_aria_lora.py:37 |
| Prompt text enters the graph at exactly one place: `_inject_conditioning` → node 122 | quality_max.py:509-513 |
| `_inject_identity(workflow, char_lora, face_anchor_remote, params, has_character, char_lora_strength=None)`; LoRA-ful sets 700 inputs; LoRA-less prunes 700 + rewires 100.model←[112,0], 122.clip←[11,0], 600.clip←[11,0] | quality_max.py:461-506 |
| Surgery order: `_prune_unavailable` :863 → uploads :868-874 → `_inject_identity` :877 → `_inject_conditioning` :879 → `_inject_sampling` :880 → `_inject_latent_source` :881 → `_inject_post_passes` :882 → `_inject_aspect` :883 → per-candidate deepcopy :937; retry re-calls `_inject_identity` :976 (boosted params). **Retry rewire truth (plan-review corrected):** the consumer rewires live ONLY in the LoRA-LESS else-branch, which is guarded by `if "700" in workflow:` — after the first LoRA-less call pruned 700, the retry SKIPS the branch entirely; the LoRA-ful retry rewrites 700's inputs without touching consumers. The retry therefore CANNOT break a 701-chain today; the plan still re-runs the injectors there as defensive insurance against future `_inject_identity` changes | quality_max.py:461-506, 863-979 |
| **`_inject_post_passes` SUPIR-absent branch re-feeds 950**: `feed_node = next((n for n in ("610","600","902","8") if n in workflow), "8")` then `workflow["950"]["inputs"]["image"] = [feed_node, 0]` — the priority list does not know 611, so a faceswap injected BEFORE post_passes gets bypassed. Faceswap MUST inject after `_inject_post_passes` (adversarial plan-review CRITICAL, verified firsthand) | quality_max.py:597-602 |
| Node 700 consumers (complete): 100.model←[700,0], 122.clip←[700,1], 600.clip←[700,1] | pulid_max.json |
| Node 610 (ReActorFaceSwap): input_image=["600",0], source_image=["93",0], input_faces_index **"0" (string)**, input_faces_order "left-right"; sole consumer: 501.image←[610,0] | pulid_max.json |
| Node ids **611, 94, 95, 701, 702 are all FREE** in the static graph (59 ComfyUI nodes + 1 `_metadata` entry = 60 top-level keys) | pulid_max.json |
| `_prune_node` tolerates absent nodes (`pop(node_id, None)`) | quality_max.py:346-361 |
| Registered LoRA value is a LOCAL ABSOLUTE PATH (`/Users/.../logs/char_lora_fal_v2.safetensors`) — node 700's `lora_name` expects a pod-side loras/-relative name; today's verbatim pass-through has never run live (zero registered LoRAs until 2026-06-11) | domain/projects/cfd3f0967eb3/project.json; quality_max.py:474 |
| Per-char validation block is tier-agnostic and iterates `strategy.secondary_specs` — max-tier secondaries get scored with ZERO new validation code | cinema/shots/controller.py:738-788 |
| Scorecard `identity_multi` reads mechanism/conditioned/unconditioned generically — no scorecard change needed | cinema/capability_scorecard.py:163-170 |
| Graph-test idiom: call `_load_max_workflow()` inline (deep-copied pulid_max.json), mirror production call order, assert `workflow[nid]["inputs"][key] == [ref, slot]`; `_reachable_dangling` helper lives in tests/unit/test_quality_max_prune.py (importable since tests/ became a package in slice-1 Task 8) | tests/unit/test_quality_max_prune.py:68,147,193 |
| web_server LoRA-train mutate persists char_lora_paths + char_lora_strengths (lockstep pop on None) — triggers NOT persisted there | web_server.py:778-788 |
| TWO LoRA artifacts on disk: logs/char_lora_fal.safetensors (v1, superseded) and logs/char_lora_fal_v2.safetensors (v2, registered) — spec **§3(b) lines 259-260** says the FAL path "produced the only existing artifacts" (stale wording, Task 9 fixes — note the wording is in §3(b), NOT §7.3) | logs/ |
| Suite baseline at plan time: **2056 passed / 0 failed** (2059/0 after the `67a179c` desync disposition — re-baseline at execution) | commit 6872c3e..67a179c session record |

**Honesty note on the tag name:** `MAX_TIER_MULTI_LORA` (the name spec §3(d)/strategy.py reserved) is promised whenever ≥1 secondary is conditioned on the max tier — including a secondary WITHOUT a LoRA, which gets ReActor-swap-from-reference only. The per-char truth lives in each spec's `fidelity` field (`lora` vs `reference`); the validator + scorecard hold the promise accountable per character. Reviewers pushed on this at plan review: keeping the reserved name beats inventing a fourth max tag, and `fidelity` already disambiguates.

## Conventions for every task (read once, apply throughout)

1. A PEER Claude session is live in this working tree. NEVER bare `git add -A` / `git add .` / `git commit -a` / `git read-tree`. Don't trust `git status` — use `git show` / `git ls-tree HEAD`.
2. Before committing: `git log --oneline -3`, then `git diff --cached --name-only` (only your files), then commit with explicit pathspec (`-m` BEFORE `--`).
3. pytest always as: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest …`
4. After each task: full suite (`tests/unit/ -q`) green + `.venv/bin/python scripts/ci_smoke.py` → OK. If line-shifts drift doc anchors, run `.venv/bin/python scripts/check_doc_claims.py --fix ARCHITECTURE.md docs/PROGRAM-MANUAL.md`, verify the diff is PURE anchor-number shifts, include the docs in the pathspec.
5. R-BRIEF: when this plan cites a pattern at file:line, read the FULL shape before implementing; report divergences BEFORE improvising.
6. The pod is STOPPED. Nothing in this plan touches the network. If code you write would need a pod to test, the design is wrong — stop and report.

## Chunk 1: Promise layer + plumbing (Tasks 1–4)

### Task 1: Strategy types — `MAX_TIER_MULTI_LORA` + per-char LoRA fields

**Files:**
- Modify: `cinema/shots/strategy.py`
- Test: `tests/unit/test_identity_strategy_router.py` (unit section, extend)

- [ ] **Step 1: Write the failing tests** (append to the unit section, after `test_to_metadata_dict_is_json_safe_and_complete`):

```python
def test_char_spec_lora_fields_default_none_and_serialize():
    s = CharIdentitySpec(char_id="char_b", reference="/r/b.jpg",
                         fidelity="lora", lora_path="/l/b.safetensors",
                         lora_strength=0.55, trigger="TOKman")
    d = s.to_dict()
    assert d["lora_path"] == "/l/b.safetensors"
    assert d["lora_strength"] == 0.55
    assert d["trigger"] == "TOKman"
    # defaults stay None and serialize (Kontext-tier specs carry them as None)
    bare = CharIdentitySpec(char_id="c", reference="/r/c.jpg").to_dict()
    assert bare["lora_path"] is None and bare["trigger"] is None


def test_strategy_carries_primary_trigger_and_multi_lora_tag_importable():
    from cinema.shots.strategy import MAX_TIER_MULTI_LORA
    s = IdentityStrategy(mechanism_tag=MAX_TIER_MULTI_LORA,
                         primary_char_id="char_a", char_lora_trigger="TOKwoman")
    assert s.char_lora_trigger == "TOKwoman"
    json.dumps(s.to_metadata_dict())  # stays JSON-safe
```

- [ ] **Step 2: Run — expect FAIL** (TypeError unexpected kwarg / ImportError)

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_identity_strategy_router.py -q`

- [ ] **Step 3: Implement.** In `cinema/shots/strategy.py`: add the constant after :14; extend both dataclasses (defaults keep every existing constructor call valid — the dataclass is frozen, fields must come after existing defaulted fields):

```python
MAX_TIER_MULTI_LORA = "MAX_TIER_MULTI_LORA"
```

In `CharIdentitySpec`, after `multi_angle_refs`:

```python
    # P1-1 slice 2 (§3b): per-char LoRA assets — populated only on the max
    # tier for registered-LoRA secondaries; None elsewhere (Kontext specs
    # carry them as None and the Kontext branch ignores them).
    lora_path: Optional[str] = None
    lora_strength: Optional[float] = None
    trigger: Optional[str] = None
```

Extend `to_dict()`:

```python
    def to_dict(self) -> dict:
        return {"char_id": self.char_id, "reference": self.reference,
                "identity_anchor": self.identity_anchor, "fidelity": self.fidelity,
                "multi_angle_refs": list(self.multi_angle_refs),
                "lora_path": self.lora_path, "lora_strength": self.lora_strength,
                "trigger": self.trigger}
```

In `IdentityStrategy`, after `char_lora_strength`:

```python
    char_lora_trigger: Optional[str] = None
```

Update the module docstring's "slice 2 adds …" line to reflect that `MAX_TIER_MULTI_LORA` now EXISTS (only `MAX_TIER_DUAL_PULID` remains reserved for Pass B/S2). Also update `fidelity`'s inline comment (`slice 2 adds lora` → `lora` is now live).

- [ ] **Step 4: Run — PASS.** Targeted file, then full suite + smoke (Conventions #4). NOTE: the Kontext integration tests in the same file assert `"multi_angle_refs" in sent[0]`-style shapes — the three NEW to_dict keys must not break them (they assert specific keys, not full equality — verify, and if any test does full-dict equality on `to_dict()` output, extend its expectation in THIS task).

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(p1-1-s2): CharIdentitySpec carries per-char LoRA assets + MAX_TIER_MULTI_LORA tag" -- cinema/shots/strategy.py tests/unit/test_identity_strategy_router.py
```

### Task 2: Router max arm — secondaries conditioned, MULTI_LORA promised

**Files:**
- Modify: `cinema/shots/controller.py:288-342` (`_resolve_identity_strategy`)
- Test: `tests/unit/test_identity_strategy_router.py` (unit section)

- [ ] **Step 1: Rewrite the now-obsolete max-arm test + add the new contract tests.** `test_two_char_max_tier_is_max_primary_only_with_secondary_unconditioned` (:57) pins the SLICE-1 stub behavior and must be REPLACED (this is the one intentional contract change of the slice — call it out in the commit body):

```python
def test_two_char_max_tier_promises_multi_lora_with_secondary_conditioned():
    # slice 2: registered-ref secondary is CONDITIONED on max (ReActor rescue
    # at minimum; LoRA chain when one is registered for it).
    s = _resolve_identity_strategy(_shot(["char_a", "char_b"]), "max",
                                   SETTINGS_NO_LORA, CC_TWO_REGISTERED)
    assert s.mechanism_tag == "MAX_TIER_MULTI_LORA"
    assert [c.char_id for c in s.conditioned_chars] == ["char_a", "char_b"]
    sec = s.conditioned_chars[1]
    assert sec.fidelity == "reference"     # no LoRA registered for char_b here
    assert sec.lora_path is None
    assert s.unconditioned_chars == []


def test_max_tier_secondary_with_lora_gets_lora_fidelity_and_assets():
    settings = {"quality_tier": "max",
                "char_lora_paths": {"char_b": "/l/b.safetensors"},
                "char_lora_strengths": {"char_b": 0.7},
                "char_lora_triggers": {"char_b": "TOKman"}}
    s = _resolve_identity_strategy(_shot(["char_a", "char_b"]), "max",
                                   settings, CC_TWO_REGISTERED)
    sec = s.conditioned_chars[1]
    assert sec.fidelity == "lora"
    assert sec.lora_path == "/l/b.safetensors"
    assert sec.lora_strength == 0.7
    assert sec.trigger == "TOKman"


def test_max_tier_single_char_stays_primary_only():
    s = _resolve_identity_strategy(_shot(["char_a"]), "max",
                                   SETTINGS_NO_LORA, CC_PRIMARY_ONLY)
    assert s.mechanism_tag == "MAX_TIER_PRIMARY_ONLY"
    assert s.unconditioned_chars == []


def test_max_tier_secondary_cap_two_overflow_unconditioned():
    cc = dict(CC_TWO_REGISTERED)
    cc["secondary_chars"] = [
        {"char_id": f"char_{i}", "reference": f"/r/{i}.jpg",
         "multi_angle_refs": [], "identity_anchor": ""} for i in "bcd"
    ]
    s = _resolve_identity_strategy(_shot(["char_a", "char_b", "char_c", "char_d"]),
                                   "max", SETTINGS_NO_LORA, cc)
    assert len(s.conditioned_chars) == 3
    assert s.unconditioned_chars == ["char_d"]


def test_primary_trigger_rides_strategy():
    settings = {"quality_tier": "max",
                "char_lora_paths": {"char_a": "/l/a.safetensors"},
                "char_lora_triggers": {"char_a": "TOKwoman"}}
    s = _resolve_identity_strategy(_shot(["char_a"]), "max", settings,
                                   CC_PRIMARY_ONLY)
    assert s.char_lora_trigger == "TOKwoman"
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement.** In `_resolve_identity_strategy`: hoist the trigger lookup next to the existing lora lookups (:293-295):

```python
    char_lora_triggers = settings.get("char_lora_triggers", {}) or {}
    char_lora_trigger = char_lora_triggers.get(primary_char_id) or None
```

Add `char_lora_trigger=char_lora_trigger` to BOTH `IdentityStrategy(...)` return sites (the NO_IDENTITY_ASSET early return at :300-306 and the final return at :335-342). Replace the max-arm stub (:316-317) with:

```python
    if quality_tier == "max":
        # P1-1 slice 2 (§3b + §3c-A): same registered-ref gate + 2-cap as the
        # Kontext arm; per-secondary LoRA assets looked up exactly like the
        # primary's (settings dicts keyed by char_id). A LoRA-less secondary
        # still rides as fidelity="reference" — the ReActor rescue swaps its
        # face from the canonical even without a LoRA.
        for entry in secondary[:2]:
            sec_id = entry["char_id"]
            sec_lora = char_lora_paths.get(sec_id) or None
            conditioned.append(CharIdentitySpec(
                char_id=sec_id, reference=entry["reference"],
                identity_anchor=entry.get("identity_anchor", ""),
                multi_angle_refs=tuple(entry.get("multi_angle_refs") or ()),
                fidelity="lora" if sec_lora else "reference",
                lora_path=sec_lora,
                lora_strength=(settings.get("char_lora_strengths", {}) or {}).get(sec_id),
                trigger=char_lora_triggers.get(sec_id),
            ))
            conditioned_ids.add(sec_id)
        tag = MAX_TIER_MULTI_LORA if len(conditioned) > 1 else MAX_TIER_PRIMARY_ONLY
```

Import `MAX_TIER_MULTI_LORA` in the function's local import block (:287-290 region — it imports the other tags there).

- [ ] **Step 4: Run targeted + full suite + smoke.** The Task-6/Task-9 integration tests (production-tier fixtures) are unaffected (they pass `quality_tier="production"` via fixture settings — verify none uses "max").

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(p1-1-s2): router max arm conditions registered secondaries — MAX_TIER_MULTI_LORA promised (contract change: replaces the slice-1 PRIMARY_ONLY stub pin)" -- cinema/shots/controller.py tests/unit/test_identity_strategy_router.py
```

### Task 3: web_server train-endpoint persists `char_lora_triggers` (spec §3(b) prerequisite)

**Files:**
- Modify: `web_server.py:778-788` (the LoRA-train `_mutate`)
- Possibly modify: the training-result producer (find it — see Step 0)
- Test: extend the file that covers this endpoint (find via `grep -rln "char_lora_paths" tests/`)

- [ ] **Step 0 (R-BRIEF, report before implementing):** find where the train-callback `result` dict is BUILT (`grep -rn '"lora_path"' prep/ *.py | grep -v test`) and determine whether a `trigger_token` key already rides it (the LOCAL path writes it to dataset_manifest.json — prep/lora_training.py:224-232; the FAL path hardcodes `TOKwoman` in scripts only). If the producer can cheaply include `trigger_token`, add it there; if the FAL path cannot, the mutate simply sees it absent (lockstep pop). Report what you found.

- [ ] **Step 1: Write the failing test** — mirror the existing test for this mutate (find the test asserting `char_lora_paths` persistence and copy its fixture shape): a result carrying `trigger_token="TOKx"` lands in `global_settings.char_lora_triggers[cid]`; a result WITHOUT it pops any stale entry (lockstep with the strengths pattern at :781-787).

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement** inside `_mutate`, after the strengths block (:781-787), mirroring it exactly:

```python
                    if result.get("trigger_token"):
                        settings.setdefault("char_lora_triggers", {})[cid] = result["trigger_token"]
                    else:
                        # lockstep with strengths: a re-trained LoRA without a
                        # known trigger must not inherit a stale token.
                        settings.get("char_lora_triggers", {}).pop(cid, None)
```

Rule #13 note: this mutate is the ONLY writer of char_lora_paths/strengths (besides scripts/_register_aria_lora.py) — confirm by grep and state it in the commit body.

- [ ] **Step 4: Run targeted + full suite + smoke; Step 5: Commit**

```bash
git commit -m "feat(p1-1-s2): train-endpoint persists char_lora_triggers in lockstep (spec 3b prerequisite)" -- web_server.py <test file>
```

### Task 4: Plumbing — secondaries + triggers reach `generate_ai_broll_max`; prompt assembly; lora_name normalization

**Files:**
- Modify: `cinema/shots/controller.py:704-724` (one kwarg), `phase_c_assembly.py:75-145` (passthrough + dispatch), `quality_max.py:701-719` (signature) + new pure helper `_assemble_max_prompt` + `_inject_identity`'s lora_name write (:474)
- Test: `tests/unit/test_quality_max_multichar.py` (NEW — helper tests), `tests/unit/test_phase_c_assembly_provenance.py` or sibling (dispatch-forwarding test), `tests/unit/test_identity_strategy_router.py` (controller integration)

- [ ] **Step 1: Write the failing tests.**

In NEW `tests/unit/test_quality_max_multichar.py` (header mirrors test_quality_max_prune.py's import style):

```python
from quality_max import _assemble_max_prompt


def test_assemble_max_prompt_no_triggers_is_identity():
    assert _assemble_max_prompt("a prompt", None, None) == "a prompt"
    assert _assemble_max_prompt("a prompt", None, [{"trigger": "TOKman"}]) == "a prompt"
    # ^ secondary trigger WITHOUT lora_path contributes nothing


def test_assemble_max_prompt_prepends_primary_then_lora_secondaries():
    out = _assemble_max_prompt(
        "a prompt", "TOKwoman",
        [{"trigger": "TOKman", "lora_path": "/l/b.safetensors"},
         {"trigger": "TOKthird", "lora_path": None}])
    assert out == "TOKwoman, TOKman, a prompt"
```

Dispatch-forwarding test: **mirror the EXISTING test for this exact seam** — `tests/unit/test_char_lora_strength_thread.py:235-236` stubs the dispatch with `sys.modules["quality_max"] = fake_qm` (a module-shaped fake whose `generate_ai_broll_max` captures kwargs). phase_c_assembly imports it INSIDE the dispatch (`from quality_max import generate_ai_broll_max` at :127), so the sys.modules replacement is the established convention here (plan-review corrected an earlier `monkeypatch.setattr` suggestion — both work, but follow the corpus). Read that test file first (R-BRIEF) and place the new test beside it or in test_quality_max_multichar.py. Call `generate_ai_broll(prompt=..., quality_tier="max", secondary_char_refs=[{...}], char_lora_trigger="TOKwoman", ...)`; assert the fake received `secondary_chars == [{...}]` and `char_lora_trigger == "TOKwoman"`.

Controller integration (extend test_identity_strategy_router.py's integration section): a `controller_two_chars_max` fixture — clone `controller_two_chars` but with `global_settings` carrying `quality_tier: "max"` (read `_build_host` first to see where settings are injected); assert the take's `identity_strategy.mechanism_tag == "MAX_TIER_MULTI_LORA"`, `captured["kwargs"]["char_lora_trigger"] is None` (no trigger registered in fixture), and `identity_per_char` covers both chars (the tier-agnostic validation block — this is the slice-2 accountability pin, no new validation code).

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement.**

(a) `cinema/shots/controller.py` `generate_ai_broll` call (:704-724): add ONE kwarg next to `char_lora_strength`:

```python
            char_lora_trigger=strategy.char_lora_trigger,
```

(b) `phase_c_assembly.py` `generate_ai_broll` signature (:75-81 region): add `char_lora_trigger=None` beside `char_lora_path`/`char_lora_strength` with the docstring note "P1-1 slice 2: max-tier trigger token; ignored on other tiers". In the MAX-TIER DISPATCH (:128-145), forward BOTH:

```python
                char_lora_trigger=char_lora_trigger,
                secondary_chars=secondary_char_refs,
```

(c) `quality_max.py` `generate_ai_broll_max` signature (:713-718 region, beside the other max-tier extras):

```python
    char_lora_trigger: Optional[str] = None,
    secondary_chars: Optional[List[dict]] = None,
```

(d) `quality_max.py` new pure helper (place directly above `_inject_identity`):

```python
def _assemble_max_prompt(prompt: str, char_lora_trigger: Optional[str],
                          secondary_chars: Optional[list]) -> str:
    """Prepend LoRA trigger tokens (training-caption convention: token first).

    Primary trigger first, then each secondary's — but a secondary token only
    when that secondary actually carries a LoRA (a trigger without its LoRA in
    the chain is noise). No tokens -> prompt unchanged (every pre-slice-2
    call path).
    """
    triggers = [char_lora_trigger] if char_lora_trigger else []
    for entry in secondary_chars or []:
        if entry.get("trigger") and entry.get("lora_path"):
            triggers.append(entry["trigger"])
    if not triggers:
        return prompt
    return f"{', '.join(triggers)}, {prompt}"
```

(e) `quality_max.py` lora_name normalization at :474 — the registered value is a local absolute path; ComfyUI wants a loras/-relative name:

```python
            workflow["700"]["inputs"]["lora_name"] = os.path.basename(char_lora)
```

Add a one-line comment: pod-side placement of the file into ComfyUI's `loras/` dir under this basename is the slice-2 POD-SESSION step (spec §7.2). Pin with a test in test_quality_max_multichar.py: `_inject_identity(wf, "/abs/path/char_lora_fal_v2.safetensors", None, params, True)` → `wf["700"]["inputs"]["lora_name"] == "char_lora_fal_v2.safetensors"` (mirror the existing `test_inject_identity_with_lora_keeps_700` fixture shape in test_quality_max_prune.py).

NOTE: do NOT wire `_assemble_max_prompt` into the body yet — that is Task 7 (keeps this task green without the injectors).

- [ ] **Step 4: Run targeted + full suite + smoke; Step 5: Commit**

```bash
git commit -m "feat(p1-1-s2): secondaries + triggers plumbed to generate_ai_broll_max; prompt assembly helper; lora_name basename normalization" -- cinema/shots/controller.py phase_c_assembly.py quality_max.py tests/unit/test_quality_max_multichar.py tests/unit/test_identity_strategy_router.py <dispatch test file if separate>
```

## Chunk 2: Graph surgery (Tasks 5–7)

### Task 5: `_inject_secondary_loras` — the §3(b) chain

**Files:**
- Modify: `quality_max.py` (new function directly below `_inject_identity`)
- Test: `tests/unit/test_quality_max_multichar.py` (extend)

- [ ] **Step 1: Write the failing tests.** The graph-test file preamble (plan-review hardened — `_AVAILABLE` and `_params` do NOT exist in test_quality_max_prune.py; that file uses `_all_class_types(workflow)` inline and bare `params = {}`. Define everything explicitly). **Import-progression note:** the block below shows the FINAL import set; add each quality_max symbol in the task that creates it (Task 5: `_inject_secondary_loras`; Task 6: `_inject_secondary_faceswap`; Task 7: `_inject_conditioning`/`_inject_post_passes` if not yet present) — importing a not-yet-existing injector fails collection for the WHOLE file, which is the intended RED for that task only:

```python
import copy

from quality_max import (
    _assemble_max_prompt,
    _inject_conditioning,
    _inject_identity,
    _inject_post_passes,
    _inject_secondary_faceswap,
    _inject_secondary_loras,
    _load_max_workflow,
    _prune_node,
    _prune_unavailable,
)
from tests.unit.test_quality_max_prune import _all_class_types, _reachable_dangling

_AVAILABLE = _all_class_types(_load_max_workflow())   # full pod class set


def _params():
    return {}   # minimal params, matching test_quality_max_prune.py usage


def _sec(char_id="char_b", lora="/l/b.safetensors", strength=0.5):
    return {"char_id": char_id, "reference": f"/r/{char_id}.jpg",
            "lora_path": lora, "lora_strength": strength, "trigger": None,
            "identity_anchor": "", "multi_angle_refs": [], "fidelity": "lora"}


def test_one_secondary_chains_701_after_700():
    wf = _load_max_workflow()
    _inject_identity(wf, "/l/a.safetensors", None, _params(), True)
    _inject_secondary_loras(wf, [_sec()])
    assert wf["701"]["class_type"] == "LoraLoader"
    assert wf["701"]["inputs"]["model"] == ["700", 0]
    assert wf["701"]["inputs"]["clip"] == ["700", 1]
    assert wf["701"]["inputs"]["lora_name"] == "b.safetensors"
    # consumers moved to the END of the chain
    assert wf["100"]["inputs"]["model"] == ["701", 0]
    assert wf["122"]["inputs"]["clip"] == ["701", 1]
    assert wf["600"]["inputs"]["clip"] == ["701", 1]


def test_two_secondaries_chain_702_after_701_consumers_on_702():
    wf = _load_max_workflow()
    _inject_identity(wf, "/l/a.safetensors", None, _params(), True)
    _inject_secondary_loras(wf, [_sec(), _sec("char_c", "/l/c.safetensors")])
    assert wf["702"]["inputs"]["model"] == ["701", 0]
    assert wf["100"]["inputs"]["model"] == ["702", 0]
    assert wf["122"]["inputs"]["clip"] == ["702", 1]


def test_loraless_primary_chains_from_base_loaders():
    wf = _load_max_workflow()
    _inject_identity(wf, None, None, _params(), True)   # prunes 700
    _inject_secondary_loras(wf, [_sec()])
    assert "700" not in wf
    assert wf["701"]["inputs"]["model"] == ["112", 0]
    assert wf["701"]["inputs"]["clip"] == ["11", 0]
    assert wf["100"]["inputs"]["model"] == ["701", 0]


def test_strength_clamped_at_055_and_below_clamp_passthrough():
    wf = _load_max_workflow()
    _inject_identity(wf, "/l/a.safetensors", None, _params(), True)
    _inject_secondary_loras(wf, [_sec(strength=0.9)])
    assert wf["701"]["inputs"]["strength_model"] == 0.55
    assert wf["701"]["inputs"]["strength_clip"] == 0.55
    # below-clamp values pass through untouched (a future S3 tune that
    # accidentally inverted min() to max() would fail HERE, not silently)
    _inject_secondary_loras(wf, [_sec(strength=0.3)])
    assert wf["701"]["inputs"]["strength_model"] == 0.3


def test_no_lora_secondaries_is_noop():
    wf = _load_max_workflow()
    _inject_identity(wf, "/l/a.safetensors", None, _params(), True)
    before = copy.deepcopy(wf)
    _inject_secondary_loras(wf, [dict(_sec(), lora_path=None)])
    _inject_secondary_loras(wf, None)
    assert wf == before


def test_inject_secondary_loras_idempotent_after_identity_rerun():
    """The PuLID-boost retry re-calls _inject_identity (boosted params).
    Plan-review established the retry CANNOT break the chain today: the
    consumer rewires live only in the LoRA-less else-branch, guarded by
    'if "700" in workflow:' — after the first LoRA-less call pruned 700, the
    retry skips the branch entirely. The defensive re-injection must
    therefore be a clean no-op-equivalent: chain intact, no duplicates."""
    wf = _load_max_workflow()
    _inject_identity(wf, None, None, _params(), True)
    _inject_secondary_loras(wf, [_sec()])
    _inject_identity(wf, None, None, _params(), True)   # retry re-call
    assert wf["100"]["inputs"]["model"] == ["701", 0]   # chain SURVIVES (no reset)
    _inject_secondary_loras(wf, [_sec()])               # defensive re-inject
    assert wf["100"]["inputs"]["model"] == ["701", 0]   # still correct
    assert wf["701"]["inputs"]["model"] == ["112", 0]   # still chained from base
    assert "702" not in wf                              # no duplicate chain
```

(`_params()` = the minimal params dict the prune-file tests use — copy its shape.)

- [ ] **Step 2: Run — expect FAIL (ImportError)**

- [ ] **Step 3: Implement** (directly below `_inject_identity`):

```python
def _inject_secondary_loras(workflow: dict, secondary_chars: Optional[list]):
    """Chain one LoraLoader per LoRA-bearing secondary after the primary's 700.

    P1-1 slice 2, spec §3(b). MUST run after _inject_identity (the chain base
    depends on whether 700 survived). Idempotent: pops 701/702 first, so the
    PuLID-boost retry can re-run it defensively after its _inject_identity
    re-call (which cannot break the chain today — the consumer rewires are
    700-presence-guarded — but re-injection is cheap insurance against
    future _inject_identity changes).
    Chain base = node 700 when the primary kept its LoRA, else the base
    loaders (112 model / 11 clip — the LoRA-less-primary path prunes 700).
    Consumers (100.model, 122.clip, 600.clip) move to the LAST chained node.
    Strength clamp ≤0.55 per secondary (§3b bleed mitigation; S3 tunes).
    lora_name takes the artifact's BASENAME — pod-side placement into
    ComfyUI's loras/ dir is the slice-2 pod-session step (spec §7.2).
    """
    workflow.pop("701", None)
    workflow.pop("702", None)
    entries = [e for e in (secondary_chars or []) if e.get("lora_path")][:2]
    if not entries:
        return
    if "700" in workflow:
        model_src, clip_src = ["700", 0], ["700", 1]
    else:
        model_src, clip_src = ["112", 0], ["11", 0]
    last = None
    for i, entry in enumerate(entries):
        nid = str(701 + i)
        strength = entry.get("lora_strength")
        strength = min(strength if strength is not None else 0.55, 0.55)
        workflow[nid] = {
            "inputs": {
                "lora_name": os.path.basename(entry["lora_path"]),
                "strength_model": strength,
                "strength_clip": strength,
                "model": list(model_src),
                "clip": list(clip_src),
            },
            "class_type": "LoraLoader",
        }
        model_src, clip_src = [nid, 0], [nid, 1]
        last = nid
    if "100" in workflow:
        workflow["100"]["inputs"]["model"] = [last, 0]
    if "122" in workflow:
        workflow["122"]["inputs"]["clip"] = [last, 1]
    if "600" in workflow:
        workflow["600"]["inputs"]["clip"] = [last, 1]
```

- [ ] **Step 4: Run targeted + full suite + smoke; Step 5: Commit**

```bash
git commit -m "feat(p1-1-s2): _inject_secondary_loras — per-secondary LoraLoader chain (spec 3b)" -- quality_max.py tests/unit/test_quality_max_multichar.py
```

### Task 6: `_inject_secondary_faceswap` — the §3(c) Pass A dual ReActor

**Files:**
- Modify: `quality_max.py` (new function below `_inject_secondary_loras`)
- Test: `tests/unit/test_quality_max_multichar.py` (extend; import `_reachable_dangling` from tests.unit.test_quality_max_prune)

- [ ] **Step 1: Write the failing tests:**

```python
def test_faceswap_injects_94_and_611_and_rewires_consumers():
    wf = _load_max_workflow()
    _inject_secondary_faceswap(wf, "sec_face_remote.jpg")
    assert wf["94"] == {"inputs": {"image": "sec_face_remote.jpg"},
                        "class_type": "LoadImage"}
    n = wf["611"]
    assert n["class_type"] == "ReActorFaceSwap"
    assert n["inputs"]["input_image"] == ["610", 0]
    assert n["inputs"]["source_image"] == ["94", 0]
    assert n["inputs"]["input_faces_index"] == "1"   # string, like 610's "0"
    assert n["inputs"]["source_faces_index"] == "0"
    # 610's static consumer moves to 611 (501.image in the full graph)
    assert wf["501"]["inputs"]["image"] == ["611", 0]
    # 611 inherits 610's scalar config (swap model, restore model, ordering)
    assert n["inputs"]["swap_model"] == wf["610"]["inputs"]["swap_model"]
    assert n["inputs"]["input_faces_order"] == "left-right"


def test_faceswap_noop_without_remote_or_without_610():
    wf = _load_max_workflow()
    before = copy.deepcopy(wf)
    _inject_secondary_faceswap(wf, None)
    assert wf == before
    _prune_node(wf, "610", rewire_to=("600", 0))
    _inject_secondary_faceswap(wf, "x.jpg")
    assert "611" not in wf and "94" not in wf


def test_faceswap_idempotent_double_call_no_dangling():
    wf = _load_max_workflow()
    original_ids = set(wf)
    _inject_secondary_faceswap(wf, "a.jpg")
    _inject_secondary_faceswap(wf, "b.jpg")
    assert wf["94"]["inputs"]["image"] == "b.jpg"
    assert wf["501"]["inputs"]["image"] == ["611", 0]
    # exactly one 611 in the graph, nothing dangling
    assert _reachable_dangling(wf, original_ids | {"611", "94"}) == []


def test_faceswap_after_full_prune_sequence_when_reactor_pruned():
    """When ReActorFaceSwap is NOT in the pod's available classes,
    _prune_unavailable drops 610 — the injector must no-op, and the graph
    stays clean end-to-end."""
    wf = _load_max_workflow()
    available = set(_AVAILABLE) - {"ReActorFaceSwap"}
    _prune_unavailable(wf, available, has_character=True, has_init=False)
    assert "610" not in wf
    before = copy.deepcopy(wf)
    _inject_secondary_faceswap(wf, "x.jpg")
    assert wf == before


def test_faceswap_after_post_passes_supir_absent_feeds_611():
    """THE ordering pin (adversarial plan-review CRITICAL): when SUPIR is
    absent, _inject_post_passes re-feeds 950 from a 610-priority list that
    does not know 611 (quality_max.py:597-602). Injecting the faceswap AFTER
    post_passes makes the dynamic consumer-rewire catch that fresh
    950.image<-[610,0] and move it to 611. (Injected BEFORE, 611 would be
    silently bypassed — generated but never consumed.)"""
    wf = _load_max_workflow()
    available = set(_AVAILABLE) - {"SUPIR_model_loader_v2"}
    _prune_unavailable(wf, available, has_character=True, has_init=False)
    _inject_identity(wf, None, None, _params(), True)
    _inject_post_passes(wf, _params(), available)       # re-feeds 950 from 610
    assert wf["950"]["inputs"]["image"] == ["610", 0]
    _inject_secondary_faceswap(wf, "sec.jpg")           # production order: AFTER
    assert wf["950"]["inputs"]["image"] == ["611", 0]
```

(Adapt `_reachable_dangling`'s exact call signature from its definition at tests/unit/test_quality_max_prune.py:68 — R-BRIEF.)

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement:**

```python
def _inject_secondary_faceswap(workflow: dict, secondary_face_remote: Optional[str]):
    """Dual face swap (P1-1 slice 2, spec §3(c) Pass A).

    MUST run AFTER _inject_post_passes: its SUPIR-absent branch re-feeds 950
    from a 610-priority list that does not know 611 (quality_max.py:597-602)
    — injected earlier, 611 would be generated but never consumed.
    Splice LoadImage(94) + ReActorFaceSwap(611) after the existing 610: 611
    swaps face index "1" — the right-hand face under ReActor's left-right
    ordering, matching the prompt's position hints for 2-char shots
    (domain/continuity_engine.py:480-484) — from the secondary's canonical.
    Idempotent: restores 611's consumers to 610 and pops 611/94 before
    re-injecting. No-ops when 610 was pruned (ReActor not on the pod) or no
    remote was uploaded. Cap: ONE extra swap node — the 3-char center
    position has no ReActor equivalent (§3c); the per-char validator owns
    that gap. Mis-ordered faces are a known failure mode the validator
    catches (§3c).
    """
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        for key, val in node.get("inputs", {}).items():
            if isinstance(val, list) and len(val) == 2 and str(val[0]) == "611":
                node["inputs"][key] = ["610", val[1]]
    workflow.pop("611", None)
    workflow.pop("94", None)
    if not secondary_face_remote or "610" not in workflow:
        return
    workflow["94"] = {"inputs": {"image": secondary_face_remote},
                      "class_type": "LoadImage"}
    inputs_611 = copy.deepcopy(workflow["610"]["inputs"])
    inputs_611["input_image"] = ["610", 0]
    inputs_611["source_image"] = ["94", 0]
    inputs_611["input_faces_index"] = "1"
    inputs_611["source_faces_index"] = "0"
    workflow["611"] = {"class_type": "ReActorFaceSwap", "inputs": inputs_611}
    for nid, node in workflow.items():
        if nid == "611" or not isinstance(node, dict):
            continue
        for key, val in node.get("inputs", {}).items():
            if isinstance(val, list) and len(val) == 2 and str(val[0]) == "610":
                node["inputs"][key] = ["611", val[1]]
```

- [ ] **Step 4: Run targeted + full suite + smoke; Step 5: Commit**

```bash
git commit -m "feat(p1-1-s2): _inject_secondary_faceswap — dual ReActor splice (spec 3c Pass A)" -- quality_max.py tests/unit/test_quality_max_multichar.py
```

### Task 7: Wire the injectors + prompt assembly into `generate_ai_broll_max`

**Files:**
- Modify: `quality_max.py` (main body ~:877-879 + retry ~:976-977; both shifted by Tasks 4-6 — re-grep `_inject_identity(` for the two call sites)
- Test: `tests/unit/test_quality_max_multichar.py` (extend)

- [ ] **Step 1: Write the failing test** — the composed-sequence mirror (the wire-up itself is I/O-adjacent; what's testable offline is the documented production order, mirroring test_max_extras_absent_full_sequence_no_dangling at test_quality_max_prune.py:193):

```python
def test_full_multichar_sequence_no_dangling_and_retry_safe():
    """Mirror of the production order in generate_ai_broll_max with
    secondaries, including the PuLID-boost retry re-injection. ORDER IS
    LOAD-BEARING: loras after identity; faceswap after post_passes
    (adversarial plan-review CRITICAL — see the 950 re-feed pin)."""
    wf = _load_max_workflow()
    original_ids = set(wf)
    params = _params()
    available = set(_AVAILABLE)
    _prune_unavailable(wf, available, has_character=True, has_init=False)
    _inject_identity(wf, None, None, params, True)          # LoRA-less primary
    _inject_secondary_loras(wf, [_sec()])
    prompt = _assemble_max_prompt("a prompt", None, [_sec()])
    _inject_conditioning(wf, prompt, None, None, params, True)
    _inject_post_passes(wf, params, available)
    _inject_secondary_faceswap(wf, "sec.jpg")               # AFTER post_passes
    # retry leg (defensive re-injection)
    _inject_identity(wf, None, None, dict(params, pulid_weight=1.0), True)
    _inject_secondary_loras(wf, [_sec()])
    _inject_secondary_faceswap(wf, "sec.jpg")
    assert wf["100"]["inputs"]["model"] == ["701", 0]
    assert wf["122"]["inputs"]["clip"] == ["701", 1]
    assert wf["501"]["inputs"]["image"] == ["611", 0]       # 611 consumed
    assert _reachable_dangling(wf, original_ids | {"701", "611", "94"}) == []
```

Plus a static wire-up pin that the call sites exist in the right order (cheap, honest about being a source-level pin):

```python
def test_wireup_call_order_in_source():
    import inspect, quality_max
    src = inspect.getsource(quality_max.generate_ai_broll_max)
    i_id = src.index("_inject_identity(")
    i_loras = src.index("_inject_secondary_loras(")
    i_cond = src.index("_inject_conditioning(")
    i_post = src.index("_inject_post_passes(")
    i_swap = src.index("_inject_secondary_faceswap(")
    # loras right after identity; faceswap AFTER post_passes (the SUPIR-absent
    # 950 re-feed at quality_max.py:597-602 would bypass an earlier 611)
    assert i_id < i_loras < i_cond < i_post < i_swap
    # retry leg re-injects both, after the boosted _inject_identity
    retry = src[src.index("boosted_params"):]
    assert "_inject_secondary_loras(" in retry
    assert "_inject_secondary_faceswap(" in retry
    assert "_assemble_max_prompt(" in src
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement.** TWO insertion points in the main body (plan-review corrected — the faceswap must NOT go before `_inject_post_passes`):

(i) After the `_inject_identity` call (currently :877-878), BEFORE `_inject_conditioning` (:879):

```python
    sec_face_remote = None
    if has_character and secondary_chars:
        first_ref = secondary_chars[0].get("reference")
        if first_ref and os.path.exists(first_ref):
            sec_face_remote = _upload_with_cache(comfy, first_ref)
    if has_character:
        _inject_secondary_loras(workflow, secondary_chars)
    prompt = _assemble_max_prompt(prompt, char_lora_trigger, secondary_chars)
```

(ii) AFTER `_inject_post_passes` (:882), BEFORE `_inject_aspect` (:883) — post_passes' SUPIR-absent branch re-feeds 950 from a 610-priority list (quality_max.py:597-602); injecting 611 after it lets the dynamic consumer-rewire catch that fresh feed:

```python
    if has_character:
        _inject_secondary_faceswap(workflow, sec_face_remote)
```

In the retry block, directly after the boosted `_inject_identity` call (:976-977):

```python
        if has_character:
            _inject_secondary_loras(workflow, secondary_chars)
            _inject_secondary_faceswap(workflow, sec_face_remote)
```

(The retry re-injection is DEFENSIVE — plan-review established the retry's `_inject_identity` cannot break the chain today (the consumer rewires are 700-presence-guarded); idempotent re-injection is cheap insurance against future `_inject_identity` changes. The retry never re-runs `_inject_post_passes`, so the 611 wiring persists regardless. `sec_face_remote` is already uploaded; no second upload.)

- [ ] **Step 4: Run targeted + full suite + smoke; Step 5: Commit**

```bash
git commit -m "feat(p1-1-s2): generate_ai_broll_max wires secondary injectors + trigger prompt (retry-safe)" -- quality_max.py tests/unit/test_quality_max_multichar.py
```

## Chunk 3: Accountability pins + docs (Tasks 8–9)

### Task 8: Accountability pins — scorecard + metadata surface MULTI_LORA with zero new production code

**Files:**
- Test only: `tests/unit/test_capability_scorecard.py` (extend `TestIdentityMulti`), `tests/unit/test_identity_strategy_router.py` (extend if Task 4's integration test didn't already cover identity_per_char on max)

- [ ] **Step 1: Write the tests (they should PASS immediately — these PIN that slice-1's generic accountability code needs no change; if either FAILS, that is a finding to report, not to code around):**

```python
def test_identity_multi_surfaces_max_tier_multi_lora(self):
    project = self._project_with_shot({
        "identity_score": 0.8,
        "identity_per_char": {"char_a": 0.8, "char_b": 0.61},
        "identity_strategy": {"mechanism_tag": "MAX_TIER_MULTI_LORA",
                              "primary_char_id": "char_a",
                              "conditioned_chars": [
                                  {"char_id": "char_a", "fidelity": "pulid"},
                                  {"char_id": "char_b", "fidelity": "lora"}],
                              "unconditioned_chars": []},
    })
    card = build_capability_scorecard(project, project_dir="/tmp/x")
    assert card["per_shot"][0]["identity_multi"]["mechanism"] == "MAX_TIER_MULTI_LORA"
```

(Adapt the helper call shape to `TestIdentityMulti`'s actual `_project_with_shot` — R-BRIEF.) If Task 4's `controller_two_chars_max` integration test did not assert `identity_per_char` covers char_b, add that pin here.

- [ ] **Step 2: Run — expect PASS (report if not); Step 3: Commit**

```bash
git commit -m "test(p1-1-s2): pin scorecard + per-char validation surface MAX_TIER_MULTI_LORA generically" -- tests/unit/test_capability_scorecard.py tests/unit/test_identity_strategy_router.py
```

### Task 9: Doc sync + spec staleness + final verification

**Files:**
- Modify: `ARCHITECTURE.md` (the max-tier section — locate via `grep -n "quality_max" ARCHITECTURE.md`; extend with the slice-2 data flow, 2-4 sentences, every anchor grep-verified at HEAD), `docs/SPEC-P1-1-multichar-generation-identity-2026-06-10.md` (three staleness fixes)

- [ ] **Step 1: ARCHITECTURE.md** — describe: router max arm (MULTI_LORA promise) → secondaries via `secondary_char_refs` → max dispatch forwards → `_inject_secondary_loras` (701/702 chain, ≤0.55 clamp, basename lora_name) + `_inject_secondary_faceswap` (611/94 splice, faces-index "1") + `_assemble_max_prompt` (trigger prepend) → retry-safe re-injection → per-char validation + scorecard unchanged. Anchors verified by grep at HEAD.

- [ ] **Step 2: Spec staleness fixes** (each verified this plan-cycle):
  1. §3(b) "controller.py:540-549 generalized" → the router max arm (`_resolve_identity_strategy`, cinema/shots/controller.py:316 at plan time — cite the CURRENT line after implementation).
  2. §3(b) lines 259-260 ("the FAL cloud path — which produced the only existing artifacts") → two artifacts exist (v1 superseded, v2 registered — both in logs/); registration done 2026-06-11 (`a43b59d`). NOTE: the wording lives in §3(b), NOT §7.3 (plan-review corrected).
  3. §3(b) trigger-persistence prerequisite → note RESOLVED by Task 3's web_server mutate + the manual registration script.
  Also append a §6-style implementation record stub for slice 2: offline code complete, S2/S3 + pod placement pending the bundled pod session.

- [ ] **Step 3: Doc verifier + full suite + smoke:**

Run: `.venv/bin/python scripts/check_doc_claims.py ARCHITECTURE.md docs/PROGRAM-MANUAL.md` → no drift
Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/ -q` → N passed / 0 failed (N ≈ 2056 + ~27 new — report exact)
Run: `.venv/bin/python scripts/ci_smoke.py` → OK

- [ ] **Step 4: Commit**

```bash
git commit -m "docs(p1-1-s2): ARCHITECTURE max-tier multi-char flow + spec 3b/3c staleness fixes" -- ARCHITECTURE.md docs/SPEC-P1-1-multichar-generation-identity-2026-06-10.md
```

- [ ] **Step 5: Signal pod-need.** Slice-2 offline code is now COMPLETE — per the user's standing directive (operator mailbox 2026-06-10T19:00:27Z), send the operator a mailbox event stating the pod-gated bundle is ready: pod-side LoRA placement (basename `char_lora_fal_v2.safetensors` into ComfyUI `loras/`), S2 (dual-PuLID VRAM/wiring), S3 (stacking clamp tune — needs a 2nd registered LoRA), P1-2 over-cook, live multi-char max render. The OPERATOR converts that into the single user notification (they own the push).

---

## Out of scope (do not let the session absorb these)

- **Pass B (chained dual PuLID / `MAX_TIER_DUAL_PULID`)** — gated on spike S2 (insertion point vs post-prune graph, VRAM, attention-patch composition); pod session.
- Pod-side LoRA placement, live rendering, S2/S3 spikes — the bundled pod session (spec §7.2).
- `QUALITY_MAX_MULTI` cost entry — explicitly deferred to Pass B ship (spec §4); Pass A overhead is post-gen swap, not separately billed.
- Training a second character's LoRA (S3 prerequisite; user-funded FAL decision).
- SSE/FE surfacing of identity_multi; scorecard scalar→mean swap (spec §9 backlog).
- 3-char center-position ReActor (no equivalent; validator owns the gap — §3c).
