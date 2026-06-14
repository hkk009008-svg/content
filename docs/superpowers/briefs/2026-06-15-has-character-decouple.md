# R-BRIEF: has-char-lora-hole (+ secondary-lora-hole) — decouple `has_face_ref` from `has_char_lora`

PRIORITY: MAJOR (has-char-lora-hole) + MEDIUM (secondary-lora-hole, same root)   LANE: A (image/identity)
CROSS-CUTTING: **no** — `quality_max.py` is lane-only (not auto_approve.py / cinema/context.py / core.py / web_server.py). LOCK: none. CO-SIGN: N/A (in-lane Pair-A content; not cross-lane like `idgate-failopen`).
WAVE: 2.  Author: director-1.  Verifier: operator-1 (Lane V, impl≠verifier).
Stub-contract: `docs/superpowers/specs/2026-06-15-wave2-stub-contract.md` — **both rows are "coverage-only / no-gate"** (gotcha §3): the assertion is "the right artifact survives" (node 700/701 retained + wired), NOT a gate-fail. Do **not** construct a gate-fail assertion for these rows.

---

## The defect (file:line + observable symptom)

`generate_ai_broll_max` derives a single flag at **`quality_max.py:1060`** (inventory says `:1006` — **STALE, drifted; correct to `:1060` in the inventory in this commit**):

```python
has_character = bool(character_image and os.path.exists(character_image))   # FACE-REF only
```

This is keyed off the **primary face-reference image existing on disk** — it never consults `char_lora_path`. The same flag then gates the *entire* identity stack. Two production-reachable holes:

1. **has-char-lora-hole (MAJOR):** a LoRA-only shot (a per-char LoRA registered in `settings["char_lora_paths"]`, but no `primary_reference` on disk) gets `has_character=False`, so `_prune_unavailable` drops LoRA node 700 **and** `_inject_identity` early-returns (`:520`) → the trained LoRA is **silently dropped, zero identity, no retry** (the ArcFace regen gate keys off the same flag). Reachable via `scripts/_register_aria_lora.py:35` (writes `char_lora_paths` with no ref check) and post-training reference-file deletion (`domain/character_manager.py` `get_reference_image` → None).
2. **secondary-lora-hole (MEDIUM, same root):** `_inject_secondary_loras` is gated `if has_character:` at **`:1119`** — so a secondary character's LoRA is dropped whenever the *primary* lacks a face ref.

---

## Rule #12 — grep-the-writes (the flag is written at runtime, verified first-hand)

```
$ grep -n 'has_character *=' quality_max.py
1060:    has_character = bool(character_image and os.path.exists(character_image))   # the ONE definition site
$ grep -n 'char_lora_path\|character_image' quality_max.py   # both are in scope at :1060 (fn params :875-876 / :933-942)
 875:    character_image: Optional[str],
 876:    char_lora_path: Optional[str],
 897:    ["char"] if (character_image or char_lora_path or secondary_chars)  # <-- the CORRECT OR-logic template
 933/942: character_image=None / char_lora_path=None   # generate_ai_broll_max params
```

⇒ Both inputs are independently available at the definition site, so the decouple costs no new plumbing. `_resolve_shot_info:897` already does the right OR — it is the pattern to mirror.

## Verified model-chain topology (the load-bearing evidence — graph surgery, not a flag rename)

```
112(UNETLoader) → 700(LoraLoader,model) → 100(ApplyPulidFlux,model) → 301→770→772→740 → 22(BasicGuider) → sampler
700.clip[1] →→ 122(CLIPTextEncode).clip , 600(FaceDetailer).clip
100.image ←← 93(LoadImage, face)            ;  610(ReActorFaceSwap).source_image ←← 93
700 consumers: 100.model[0], 122.clip[1], 600.clip[1]     100 consumers: 301.model[0]
```

- 301/770/772/740 are **always FLUX-incompat-pruned** (`:457-460`) and bridged; the bridge fallback is `("112" if "100" not in workflow else "100")` — **base-UNet-or-PuLID only; it does NOT know about 700.**
- ⇒ **THE TRAP:** a LoRA-only shot that prunes PuLID(100) makes the bridge rewire `22.model → [112,0]`, **bypassing LoRA node 700**. Node 700 stays present (pin `"700" in wf` passes) but is **orphaned — the render ignores the LoRA.** A pin-flip is necessary but NOT sufficient; the fix MUST keep 700 in the executing chain, and a **reachability assertion** must prove it.

---

## Rule #13 — symmetric / sibling audit (every consumer of the conflated flag, routed)

Sole definition `:1060`. 19 quality_max consumers + 2 in `face_validator_gate.py` (receive the flag). Route each:

| site | current | route to | why |
|---|---|---|---|
| `:1060` def | `has_character = bool(face_ref)` | **compute BOTH**: `has_face_ref = bool(character_image and os.path.exists(character_image))`; `has_char_lora = bool(char_lora_path)` | the split |
| `:1093` `_prune_unavailable(...)` | passes `has_character` | pass `has_face_ref, has_char_lora` (new sig) | core graph surgery |
| `:1098` face upload `_upload_with_cache(comfy, character_image)` | `if has_character` | **`if has_face_ref`** | ⚠ the **naive-fix crash site**: a merged `has_character` would call `_upload_with_cache(None)` |
| `:1103` style fallback `face_anchor_remote` | `if has_character` | `if has_face_ref` | face image as style seed |
| `:1107` `_inject_identity(...)` | `has_character` | pass `has_face_ref` (it derives `has_char_lora=bool(char_lora)` from its existing `char_lora` arg) | LoRA arm + PuLID arm |
| `:1112` secondary FACE upload | `if has_character and secondary_chars` | `if has_face_ref and secondary_chars` | needs a face image |
| `:1119` `_inject_secondary_loras` | `if has_character` | **`if has_char_lora or has_secondary_lora`** where `has_secondary_lora = any(e.get("lora_path") for e in secondary_chars or [])` | secondary LoRA is independent of primary face-ref (pin scenario: primary has NEITHER, secondary has a LoRA) |
| `:1122` `_inject_conditioning` | `has_character` | pass `has_face_ref or has_char_lora` | pose-CN prune = "is a character in frame" — either signals it |
| `:1129` `_inject_secondary_faceswap` | `if has_character` | `if has_face_ref` | faceswap needs a reference face image |
| `:1162`,`:1235` `score_candidate(face_anchor=…)` | `character_image if has_character` | `character_image if has_face_ref` | ArcFace needs the face image |
| `:1201` `should_halt(has_character=…)` | `has_character` | pass `has_face_ref` | arc-floor bypass = "no face → no ArcFace score" |
| `:1214` `needs_regenerate(…, has_character)` | `has_character` | pass `has_face_ref` | PuLID-boost retry is meaningful only with a face |
| `:1219`,`:1223` regen-retry re-inject | `has_character` | mirror `:1107`/`:1119` exactly (regen path repeats first-pass wiring) | consistency — both passes must use identical flags |
| `face_validator_gate.py:278,:337` | receive `has_character` | **unchanged** — call site now passes `has_face_ref`; the param's face-ref semantics are already correct | no edit in that file |

`_inject_secondary_loras` already handles the no-700 base (`["112",0]/["11",0]`, `:604-607`) — no change inside it; only its **gate** moves.

---

## The fix (bounded — restructure + the 700-aware bridge)

**1. `_prune_unavailable` signature** (`:396`): `(workflow, available, has_face_ref, has_char_lora, has_init)` — rename `has_character`→`has_face_ref`, **add** `has_char_lora`.

**2. Split the identity-prune (replace the `:402-419` `if not has_character` block) into 3 cases:**

```python
if not has_face_ref:
    # PuLID stack + face passes need a face anchor. Prune them; 100's model
    # consumer re-points to the LoRA(700) if a char LoRA keeps it, else base UNet(112).
    pulid_target = ("700", 0) if (has_char_lora and "700" in workflow) else ("112", 0)
    for nid in ("93", "97", "99", "101", "100"):
        _prune_node(workflow, nid, rewire_to=pulid_target if nid == "100" else None)
    _prune_node(workflow, "600", rewire_to=("902", 0) if "902" in workflow else ("8", 0))
    _prune_node(workflow, "610", rewire_to=("902", 0) if "902" in workflow else ("8", 0))

if not has_char_lora and not has_face_ref:
    # LANDSCAPE (no identity at all): also drop LoraLoader(700). (Face-only-no-LoRA
    # keeps 700 here and lets _inject_identity's else-branch prune it — unchanged
    # division of labour.) 122.clip falls back to base CLIP(11).
    _prune_node(workflow, "700", rewire_to=None)
    if "122" in workflow:
        workflow["122"]["inputs"]["clip"] = ["11", 0]
```

**3. 700-aware FLUX-incompat bridge** (`:457-460`): replace the fallback `("112" if "100" not in workflow else "100")` with a helper:

```python
def _surviving_model_src(workflow):       # priority: PuLID > LoRA > base
    for nid in ("100", "700", "112"):
        if nid in workflow:
            return nid
    return "112"
...
_tgt = _up if _up in workflow else _surviving_model_src(workflow)
```

This is what keeps LoRA node 700 IN the chain for a LoRA-only shot (`22.model → [700,0]`, not `[112,0]`).

**4. `_inject_identity` outer guard** (`:520`): `if not has_face_ref and not char_lora: return` (rename the `has_character` param → `has_face_ref`; derive nothing new — it already has `char_lora`). The inner `if char_lora` wiring arm and the `else` LoRA-less-prune arm are unchanged.

**5. Call-site signature updates** for `_prune_unavailable`'s new arg (lane-only; grep-confirmed): production `:1093`; tests `test_quality_max_prune.py:116,143,167,207`, `test_quality_max_multichar.py:415,432,459`, `test_has_character_lora_only_hole.py:62,70,98`, `test_discovery_identity_xfail.py:132`; scripts `_validate_real_path.py:27`, `_max_probe_prep.py:28`, `_talking_head2.py:64`. Face-ref-present calls → `has_face_ref=True, has_char_lora=True`; landscape calls → both `False`.

---

## Verification (operator/CI) — TDD, RED baseline already captured

RED now (`--runxfail`): `test_lora_only_shot_should_keep_and_wire_trained_lora` FAIL (700 pruned), `test_secondary_lora_injected_when_primary_has_no_face_ref` FAIL (701 absent); 3 reference tests PASS.

1. **Flip both pins → live regressions** (remove `xfail`, update calls to the new signature). `test_lora_only…`: keep `"700" in wf` + `lora_name` assertions.
2. **NEW reachability assertion (non-vacuity guard for the bypass trap):** for the LoRA-only case after the full `generate_ai_broll_max` prune+inject sequence (or a faithful slice), assert **node 700 is reachable from `22`(BasicGuider).model** (walk model edges) — proving the LoRA is in the executing chain, not orphaned. Add to `test_has_character_lora_only_hole.py` or `test_quality_max_prune.py`.
3. **Extend `test_prune_unavailable_leaves_no_reachable_dangling_links`** (`test_quality_max_prune.py:109`) to cover the new `(has_face_ref=False, has_char_lora=True)` combination — no dangling links.
4. **Reference guards MUST stay green:** `test_landscape_no_lora_correctly_prunes_lora_node` (700 pruned for true landscape), `test_full_character_with_face_ref_wires_lora` (700 kept+wired with face ref).
5. Full `tests/unit` suite green; `ci_smoke` green.

## Scope boundaries (state, don't silently exceed)
- **Degenerate "primary has zero identity + only a secondary has a LoRA":** the gate fix injects node 701 (closes the inventory row); full model-chain integration of a secondary LoRA when the primary contributes no 700/100 base is a deeper topology question the pin does NOT assert — note it, do not expand into it.
- No DECISIONS.md/ADR needed (mechanical decouple, no policy change). Update the inventory rows (`has-char-lora-hole` `:1006`→`:1060`, `secondary-lora-hole`) open→fixed and the two memory notes in the same commit (fix-stale-claim discipline).
