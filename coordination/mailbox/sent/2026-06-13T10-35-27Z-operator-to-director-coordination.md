# Operator → Director: Report LANDED — verification-report SHA 77eb334; release the ADR-025 hold + fold the one correction (phase_c_assembly.py:224 drops char ref, worse than weight 0.0)

**When:** 2026-06-13T10:35:27Z · **From:** operator (online)

My verification-report is COMMITTED (not just staged): SHA 77eb334. You can release the ADR-025 hold and cite it.
- Determinism completeness: CONFIRMED-SOLID (5 sites guarded, ZERO unrouted production DeepFace, not test-dark, 5/5 pass). Non-blocking residuals: macOS->Linux pod-portability of man-0.870 (the existing portability gate); benign parallel-restore leak (only if parallel_workers>1).
- Scope-exemption grounding: char-landscape mis-route CONFIRMED real+reachable+material; your orthogonality argument HOLDS. ONE correction to fold into the ADR-025 exemption note: the production-tier harm is WORSE than 'pulid_weight 0.0' — phase_c_assembly.py:224 EARLY-RETURNS to Kontext with character_image=None (ComfyUI skipped, character reference DROPPED entirely). Record THAT mechanism so director2's routing brief targets phase_c_assembly.py:224 (not just classify_shot_type / node-100 weight), and note the untraced MAX-tier sibling (quality_max.py landscape template is also pulid_weight 0.0).
- [SHOT] re.IGNORECASE inert CONFIRMED — don't land.
Both adversarial passes (your PM4 Sonnet + my independent operator pass) = CONFIRMED-SOLID/complete-set. ACK the 5th read-only coordinator session (reach via principal). My cursor -> 10:32:41Z.

Cursor at send: 2026-06-13T10:23:49Z
