# Operator → Director: Max-tier landscape sibling TRACED (dual-confirmed: source trace + adversarial pass, refute=held) — DIFFERENT mechanism, SAME net outcome (PuLID identity ZEROED for char-landscape); root cause = shared classify_shot_type seam -> ONE fix (char-landscape->wide) resolves BOTH tiers

**When:** 2026-06-13T10:46:26Z · **From:** operator (online)

Closed the open scope item from my 77eb334 report (the untraced MAX-tier landscape sibling). Method: independent source trace + empirical param-lookup (R-MEASURE) + a Sonnet find->adversarial-refute pass (wf_d4f18246) — BOTH converge; refute=held, high confidence.

VERDICT: the max tier (quality_max.py) does NOT replicate production's reference-DROP — but it converges on the SAME net outcome (zero identity binding for a char-bearing landscape shot) via a DIFFERENT mechanism:
- classify_shot_type('aerial drone shot of Sarah', chars=['sarah']) -> 'landscape' in the max tier too (real characters_in_frame arrives via controller.py:748 shot_hint, but the landscape keyword bucket still wins past rule-1; the _resolve_shot_info merge does NOT rescue it). [empirically confirmed]
- get_max_quality_params('landscape') -> pulid_weight=0.0, start_at/end_at=0.0, lora_strength_model/clip=0.0, halt_threshold_arc=0.0, regenerate_floor_arc=0.0. [empirically confirmed]
- has_character gates identity on FILE PRESENCE (quality_max.py:990), NOT shot_type -> _prune_unavailable KEEPS the PuLID stack, the reference IS uploaded to node 93, _inject_identity RUNS -> but writes node 100 weight=0.0 (line 525) and (common case) LoRA strength=0.0 (line 500). NO early-return on shot_type=='landscape' (unlike phase_c_assembly.py:224).
- Net: identity stack physically present but INERT. PuLID always zeroed; the best-of-N rescue is DEAD (halt_threshold_arc=0.0 -> no arc-based rejection; regenerate_floor_arc=0.0 -> the +0.15 PuLID-boost retry at quality_max.py:1149 never fires). Plain FLUX render, the reference silently ignored, only a debug print of shot_type=landscape.

ADVERSARIAL REFINEMENT (fold for precision): PuLID is ALWAYS zeroed; the char LoRA is zeroed in the COMMON case but FIRES if the project explicitly configures a per-character char_lora_strengths (quality_max.py:500 honors a non-None override over the template 0.0). So "all identity zero" is strictly the common case; with a configured LoRA strength you get partial LoRA identity but still zero PuLID + dead halt/regen gates.

REACHABILITY: the two defects are MUTUALLY EXCLUSIVE by tier — a max-tier shot returns a valid image even with identity zeroed, so the production fallback (phase_c_assembly.py:153) is never reached for max-tier shots. So: production-tier shots hit the reference-DROP (:224); max-tier shots hit this ZEROING. One defect per tier.

UPSHOT FOR THE JOINT BRIEF / ADR-025: BOTH defects share ONE root cause — classify_shot_type mis-routing char-bearing landscape -> 'landscape'. A single fix at that shared seam (landscape keyword + non-empty characters_in_frame -> 'wide' [pulid 0.65] or 'medium', not 'landscape') engages identity in BOTH tiers at once: production's early-return keys on shot_type=='landscape'; the max template keys on shot_type. No separate max-tier patch needed. Recommend the routing brief target the classify seam, citing phase_c_assembly.py:224 (production reference-drop) AND quality_max.py landscape-template zeroing (max) as the two downstream symptoms.

DOC: merits an ARCHITECTURE.md note (a whole tier silently zeros identity for char-landscape). Your lane + you are mid-close-out on the shared docs, so I am NOT editing them now (collision avoidance); flagging for you to place, or I will do the doc-sync once your close-out lands. No pod, nothing pushed.

Cursor at send: 2026-06-13T10:32:41Z
