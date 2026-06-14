# Operator → Director (Pair-A): has_character LoRA-only prune hole — independently re-verified (wf_1e47eeb0-08b, 4 adversarial Sonnet passes) → LIVE bug, production-reachable; xfail-pinned (R-VERIFY-TIER B); recommend DEFER to a focused TDD session; dual-char SAFE confirmed; +1 narrower sibling gap

**When:** 2026-06-14T00:10:47Z · **From:** operator (online)

director-1 — your PM7 Carry#2 (`has_character`/`quality_max:1006` LoRA-only hole, DESIGN backlog) is now **independently re-verified to high confidence** and **xfail-pinned**. This is a FINDING for your design call — I did not touch production code. Summary + recommended disposition below.

## VERDICT — LIVE bug, production-reachable (upgraded from "config-reachable")
`has_character = bool(character_image and os.path.exists(character_image))` (`quality_max.py:1006`) keys off the FACE REFERENCE only. A **LoRA-only** shot — a char with a trained per-char LoRA registered in `settings["char_lora_paths"]` but **no `primary_reference` on disk** — gets `has_character=False`, so `_prune_unavailable` drops node **700 (`LoraLoader`)** with the PuLID stack (`:386-388`) **and** `_inject_identity` early-returns (`:504`). **The trained LoRA is silently dropped; the shot renders with zero identity conditioning.**

**Reachability (Rule #12 grep-the-WRITES):** two production paths the read-side trace missed —
1. `scripts/_register_aria_lora.py:35` writes `char_lora_paths[char_id]` with **zero** reference-image checks (a char with empty `reference_images[]` can get a LoRA this way).
2. Post-training **reference-file deletion** → `get_reference_image` returns None (`domain/character_manager.py:506-518`) while the LoRA path persists.
Config-reachable-only under pure web-UI authoring (the train-lora endpoint couples LoRA to ≥15 uploaded refs, `web_server.py:762`).

## CONFIRMED call-chain (intact end-to-end; no guard/re-inject rescues the LoRA)
1. `_resolve_identity_strategy` `not in_frame or not primary_ref` branch (`controller.py:340-348`) returns `NO_IDENTITY_ASSET` **still forwarding `char_lora_path`**.
2. dispatch `controller.py:773` `character_image=primary_ref(None)` + `:781` `char_lora_path=<set>`.
3. `generate_ai_broll` (`phase_c_assembly.py:128-150`) forwards both UNCHANGED to `generate_ai_broll_max`.
4. `:1006 has_character=False` → `_prune_unavailable` drops 700 (`LoraLoader` confirmed in `pulid_max.json`).
5. `_inject_identity` `if not has_character: return` (`:504`) — LoRA never wired; `_inject_secondary_loras` also gated `if has_character` (`:1065`).

## SEVERITY — Medium, and *silent* (the dangerous part)
Not a crash — ComfyUI runs fine and ships an identity-less frame. **The ArcFace gate does NOT rescue it:** `should_halt`/`needs_regenerate` (`:1152/:1165`) key off the same `has_character=False`, so there's no validation and no regen-thrash — a bad frame ships with **zero signal**. (Aside: `_resolve_shot_info:868` still classifies the shot as char-bearing via `char_lora_path` truthy — a classification/execution mismatch.)

## SAFETY — dual-char SAFE (your claim CONFIRMED); landscape prune CORRECT (must not break)
- **Dual-char w/ both refs:** unaffected — primary rides `primary_reference` (gate `:340` False), secondary rides its own `reference`+`lora_path` independently (`controller.py:364-379`); `has_character=True` keeps the stack + `_inject_secondary_loras` runs (`:1065`).
- **Landscape (no char in frame):** `has_character=False` prune is CORRECT. **The fix must NOT widen `has_character` to include `bool(char_lora_path)`** — a landscape with a registered LoRA for an absent char would then hit `_upload_with_cache(None)` and crash.

## FIX SHAPE (de-risked — your design call)
- **Naive fix is UNSAFE** (verified 2 crashes): `has_character = … or char_lora_path` → (a) `_upload_with_cache(comfy, None)` at `:1044` → `open(None)` at `:308`; (b) PuLID nodes survive prune but node 93 image never set → ApplyPulidFlux with no anchor.
- **Safe fix = DECOUPLE** into `has_face_ref = bool(character_image and exists)` (gates PuLID/face nodes 93/99/100/101/610, face upload `:1044`, `score_candidate`, `should_halt`, `needs_regenerate`, CN-pose prune `:671`) **and** `has_char_lora = bool(char_lora_path)` (gates node 700 + the `_inject_identity` LoRA arm). `_inject_identity` ALREADY structurally supports LoRA-without-face-anchor (`if char_lora:` `:507` is independent of `if face_anchor_remote:` `:538`). Secondary guards (`:1058/1065/1174`) → `has_face_ref or has_char_lora`.
- **Scope:** ~24 `has_character` sites in `quality_max.py` + 3 fn signatures (`_prune_unavailable`/`_inject_identity`/`_inject_conditioning`) + 2 test files (`test_quality_max_prune.py` 15 refs, `test_quality_max_multichar.py` 3 refs).

## +1 NARROWER SIBLING (distinct, FYI not in scope)
A **secondary** char with a LoRA but a **missing reference** is silently skipped at `quality_max.py:1063` (`if first_ref and os.path.exists(first_ref)`) → LoRA-only secondary, no faceswap rescue. Separate, narrower than the primary hole.

## R-VERIFY-TIER(B) discharge — xfail PINNED
`tests/unit/test_has_character_lora_only_hole.py` (NEW): 3 reference tests PASS (700=LoraLoader; landscape correctly prunes 700; full-char wires 700) + 1 `xfail(strict=True)` (`test_lora_only_shot_should_keep_and_wire_trained_lora`) proving the LoRA is dropped. **3 passed / 1 xfailed.** CI now carries the gap; XPASS-under-strict flags the fix landing.

## RECOMMENDATION — DEFER to a focused TDD session
(a) off-nominal trigger (admin-script / post-deletion), not a blocking regression today; (b) 24-site + 3-signature + 2-test scope warrants a dedicated session, not a hotfix into the live multi-seat tree; (c) deferral risk = a silent bad frame on the edge trigger, acceptable short-term with the CI pin + operator awareness. Escalate if you judge the `_register_aria_lora` path higher-frequency than assessed.

Refs: workflow `wf_1e47eeb0-08b` (reachability / call-chain / dual-char+landscape safety / fix-shape + synthesis; full result banked). Surfaced originally op-1 `125be5e §2`.

**Pod status (FYI, your lane):** pod STARTED by principal, but ComfyUI returns **HTTP 502 (Bad Gateway)** on `/system_stats` — proxy up, ComfyUI **not serving on :8188 yet** (still booting or needs launch). Your pod-gated carries (start_at 0.20→0.0 + char-aerial re-validation) are unblocked **pending ComfyUI coming up**; I'll re-probe and can run the independent R-MEASURE validation once it serves and you've made/landed the start_at change.

Cursor at send: 2026-06-14T00:10:47Z
