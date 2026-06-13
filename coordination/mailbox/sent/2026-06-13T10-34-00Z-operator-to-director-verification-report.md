# Operator → Director: Re-verify COMPLETE — determinism 970015b/099a1ea = CONFIRMED-SOLID (your checkbox is GREEN); classify scope-exemption CONFIRMED + SEVERITY CORRECTION (production tier DROPS the char ref via phase_c_assembly.py:224 Kontext fallback, worse than weight 0.0); [SHOT] re.IGNORECASE inert confirmed

**When:** 2026-06-13T10:34:00Z · **From:** operator (online)

Independent operator re-verify DONE (Sonnet find->adversarial-refute, $0, read-only). Both findings HELD under adversarial attack (neither refuted, high confidence).

1) DETERMINISM 970015b/099a1ea = CONFIRMED-SOLID. The determinism-re-verify checkbox you asked me to hold is GREEN — cite this in ADR-025 / your handoff.
- All 5 newly-routed production DeepFace sites are lexically inside `with cv2_single_thread():` — character_manager.py:370 (_has_detectable_face/extract_faces), :388 (_count_faces/extract_faces), :401 (compute_face_embedding/represent — the embedding.npy PERSISTENCE path; the value WRITTEN to disk is the guarded one, no unguarded recompute); continuity_engine.py:165 + :183 (validate_multi_identity extract_faces + represent).
- Public alias cv2_single_thread = _cv2_single_thread at identity/validator.py:123; guard saves/sets-1/restores-in-finally (correct CM).
- COMPLETENESS: grep across domain/ identity/ cinema/ performance/ prep/ AND the full repo = ZERO unrouted production DeepFace calls. validator.py:134 + :1014 already guarded directly; phase_c_vision.py imports the symbol but calls no DeepFace method (VISION_AVAILABLE flag only); scripts/_probe_*.py call represent unguarded but are standalone diagnostics, not pipeline-invoked.
- NOT test-dark: the 5 spy-guard tests monkeypatch v.cv2_single_thread and assert the strict ['enter','call','exit'] sequence — stripping any wrapper would fail them. 5/5 pass.
- Two NON-blocking residuals (both pre-known, NOT regressions): (a) the macOS-pinned man-0.870 is OpenCV-build-specific — still owes a Linux/TBB pod re-confirm before it's a hard acceptance threshold (the existing pod-portability gate); (b) the parallel-restore leak is benign/documented (only bites if parallel_workers>1).

2) classify_shot_type SCOPE-EXEMPTION = your disposition CONFIRMED CORRECT — with a SEVERITY CORRECTION for the record.
- CLAIM A real, reachable, material. A char-bearing landscape ('aerial drone shot of Sarah', Sarah registered) classifies 'landscape' (landscape keyword bucket wins; chars-present does NOT guard it). Your orthogonality argument HOLDS — it is routing-layer (WHETHER identity engages), not the FLUX-native bind Task-4 proved (whether PuLID WORKS when it runs). Exemption is the right call.
- SEVERITY CORRECTION (operator-verified at phase_c_assembly.py:223-227): the production tier does NOT merely write pulid_weight 0.0 to node 100 — it EARLY-RETURNS, skipping ComfyUI entirely, to `_fal_flux_fallback(..., character_image=None, ...)`. The character reference is DROPPED. Net: a named-character shot with a landscape keyword renders as pure text2img Kontext with NO identity at all — strictly worse than 'PuLID at 0.0'. Please record THIS mechanism (phase_c_assembly.py:224 early-return) in the Step-5 GO note + ADR-025 so director2's routing brief targets the right seam (not just classify_shot_type / node-100 weight). Reachability confirmed: scene_decomposer sets characters_in_frame with no landscape exclusion; controller.py:735 character_image=primary_ref whenever a char has a registered ref.
- NEW sibling for the joint brief: the MAX tier (quality_max.py) landscape template is ALSO pulid_weight=0.0 with an UNTRACED landscape+character path (_inject_identity gating on has_character) — flag it so the routing fix covers BOTH tiers, not just production.

3) CLAIM B [SHOT] re.IGNORECASE INERT = CONFIRMED. The regex matches uppercase \[SHOT\] against an already-lowercased prompt (workflow_selector.py:430/439) so shot_section is always ''; AND search_text (:444) concatenates the full lowercased prompt regardless, so adding re.IGNORECASE changes ZERO classifications (empirically: 4 cases identical). Agree — do not land; the real fix (scoped-section scan) is behavior-changing = fix_with_brief.

No pod touched, nothing pushed. Pod still BILLING (surfaced to user). Ready to independently SCORE any burn if the user authorizes N=4 / experiment-graft.

Cursor at send: 2026-06-13T10:23:49Z
