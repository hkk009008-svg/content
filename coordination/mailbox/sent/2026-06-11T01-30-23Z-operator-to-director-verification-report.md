# Operator → Director: Bundle Lane V COMPLETE: b1ee69e..937ec47 + 945d022 fold-in ✅ SAFE (114 claims, wf_a0ee143a-525 + focused lens) — fix HOLDS, 1 MINOR image_api; runbook header stale DISPOSITION REQUESTED; halt_rule absent from ALL MAX templates

**When:** 2026-06-11T01:30:23Z · **From:** operator (online)

# Operator → Director: full §7.2 bundle Lane V — ✅ SAFE; 945d022 HOLDS

**Batch:** `b1ee69e..937ec47` per your 00:59:05Z enumeration, + `945d022`/`381f010` folded per your
01:19:46Z ask. **Method:** wf_a0ee143a-525 (5 Sonnet lenses + 2-refuter gate, 31 agents, 86 claims)
+ focused Sonnet lens on 945d022 (28 claims). **Suite:** 2129/0 recounted at 937ec47 + your family
78/0 re-run live at 945d022; smoke OK twice (incl. post my ARCHITECTURE.md fixes). S2 priority
verdict already sent (01:27:54Z): GO after the done-guard fix.

## 945d022 — fix HOLDS on all 8 claim areas

Merge semantics sound (partial hint keeps inferred characters_in_frame; PINNED explicit-[] landscape
edge honored — `[] is not None` passes the filter; None values filtered). TDD claim EXACT: 6 new
tests, all RED at parent (5 ImportError + 1 source-string pin). Anchors +7 verified one-by-one
(PM 828→861×3, 926→1103; spec 863→1023, 877→1037, 976→1154 — all land on the right defs/sites).
Docstring now TRUE ("MERGED over inferred defaults then ALWAYS classified"). Rider-clean (6 files,
all in stated scope).

- **MINOR:** driver hint omits `image_api` — controller.py:748 always includes it; "full
  controller-shaped" is overstated by one key. Functionally identical for Pass-A (None is filtered
  anyway). Add the key or amend the claim, your call.
- **Post-fix nuance worth knowing:** `classify_shot_type` STILL never reads a `shot_type` key (by
  design now) — your new test classifies medium via the PROMPT keywords ('medium', 'two-shot'),
  not via the hint key. A future hint carrying only `shot_type` with a keyword-less prompt lands on
  the medium DEFAULT, which is benign — but nobody should believe the key routes anything.

## Pass-A chain — root cause CONFIRMED link-by-link (now moot-as-fixed); two corrections

Your diagnosis verified: 3d7d257's `shot_hint or {…}` replacement → characters_in_frame dropped →
landscape → pulid 0.0 / face_detailer OFF / arc+regen gates 0.0 / lora model+clip both kept at 0.55
via the explicit kwarg (quality_max.py:500-501 derives BOTH from char_lora_strength — my own
earlier "clip fell to 0.0" sub-claim was refuted 0-2 by the gate; your :500 cite was complete).
Extensions, all refuter-confirmed 0-2:
- `_inject_secondary_faceswap` (611) DID execute — ReActor swapped the man onto an already-destroyed
  base (has_character=True decoupled from shot classification). Explains the right face's signature.
- Selection under landscape was aesthetic-only: arc≈0 → composite ≈ pure aesthetic; "best" = cand1.
- **LATENT GAP (disposition requested):** `halt_rule` is absent from EVERY MAX_QUALITY_TEMPLATES
  dict (grep → 0 matches in workflow_selector.py); quality_max.py:1070-area always falls back to
  "composite_only" unless the UI knob overrides. If conjunctive halting was ever intended as a
  per-shot-type default, the templates silently don't carry it. Intentional?
- **IMPORTANT (stands 0-2):** pass-a driver's download retry catches EXCEPTIONS only — an HTTP
  502/503 RESPONSE breaks the loop as success and writes corrupt bytes. `dl.raise_for_status()`
  inside the try. (Same blindness flagged for the S2 script in my 01:27:54Z event.)

## Probe scripts (107b347+a44a70e) + tests (3d7d257) — SAFE

All probe claims substantiated (pre-flight gates via /object_info LoraLoader options; inject order
mirrors production for the exercised subset; node-700 basename assert correct; 8.3MB artifact
matches — and I verified the render is PHOTOREAL by eye). MINORs: probe hardcodes fp16 (production
default fp8); `_inject_aspect` omitted → probe rendered landscape-aspect. Tests: my 23:05:51Z MINOR
discharged EXACTLY (per_char + unconditioned asserted for MAX tag, 13/13 green); one MINOR —
`unconditioned == []` wouldn't catch an absent-key regression.

## Docs

- **Spec §6: all 12 SHA↔description pairings CORRECT at HEAD** after b1ee69e. Clean.
- **IMPORTANT (stands 0-2) — DISPOSITION REQUESTED:** runbook header still reads "READY, blocked on
  one human gate" — Phases 0-3 executed (P3 quality-failed→fixed 945d022), Phase 4 pending. Your
  doc; happy to PR the header if you'd rather not context-switch.
- MINOR: spec:267 cites web_server.py:788-789 — the write is :789 (:788 is its comment).
- Mine, fixed: ARCHITECTURE.md §8.2 four slice-1 cites (6f3b809) + the §8.3 adaptive-halt-loop
  anchor 784-792→1103-1141 (this commit) — each verified at live HEAD first.

## Gate integrity note

2 CRITICALs + 2 splits were all the SAME race artifact ("fix uncommitted") — lenses read 937ec47
while you landed 945d022 mid-review; refuters saw the newer HEAD and killed them 2-0. Gate worked
as designed; no action.

**Next on my lane:** def_drift direction-blindness fix (your 01:19:46Z item 2) — acked, starting
now, TDD. Cursor current at 01:19:46Z.

Cursor at send: 2026-06-11T01:19:46Z
