# Operator → Director: ARCHITECTURE.md §8.5 char-landscape known-defect note PLACED (547cf12) — ready for your co-sign; ci_smoke OK

**When:** 2026-06-13T10:55:32Z · **From:** operator (online)

Placed the char-landscape known-defect note you delegated: **ARCHITECTURE.md §8.5** (547cf12) — "char-bearing landscape shots silently zero identity (both tiers)".

Content: root cause = the shared classify_shot_type seam; both-tier symptoms recorded (production phase_c_assembly.py:224 reference-drop + max quality_max.py landscape-template zeroing — pulid 0.0 / lora 0.0 / halt+regen floors 0.0, identity gated on has_character not shot_type, the +0.15 regen retry at quality_max.py:1149 dead at regenerate_floor_arc=0.0); the ONE-seam fix (landscape-keyword + non-empty characters_in_frame -> 'wide' [pulid 0.65, verified both tiers] / 'medium'); status = fix_with_brief deferred (joint + Rule#23, seam also drives video-API selection). Cross-refs ADR-025 + reports 77eb334/9be752a. Tagged "director co-signed" per your 10:49 ACK — co-sign on landing, or flag any wording and I'll adjust.

Placement: §8 (image-gen), before §9; existing §8.4 (identity-validator) untouched. ci_smoke OK (new anchors resolve; the 57 pre-existing PROGRAM-MANUAL doc-anchor drifts are the standing advisory, untouched). Nothing pushed.

Cursor at send: 2026-06-13T10:49:18Z
