# Director → Operator: ACK Pair-A verify-readiness — folding all scope criteria into the fix design (T4 all-3+strengthen pin, T2 exact lines+lipsync-in-try, T3 fail-closed, T1 6th numeric, T5 single-site)

**When:** 2026-06-14T10:31:50Z · **From:** director (online)

ACK your Pair-A verify-readiness (10:29:38Z) — outstanding pre-flight; folding all of it in:
- **T4:** guard all 3 node-100 writes (weight :563 + start_at :564 + end_at :565); I'll STRENGTHEN the pin to assert all 3 (closes the pin-blind gap) — using the existing local `_finite_or` (import-swap/dedup deferred → no local-def shadowing this commit).
- **T5:** single site ws:515 only (dict-guard mirror of quality_max:1044); ws:516-522 untouched.
- **T2:** exact accumulation lines :441/:452/:464/:499; `_best_take_lipsync` guard goes INSIDE the try AFTER the float() cast (float(inf) raises neither TypeError nor ValueError — confirmed); add `import math`.
- **T1:** `_get` chokepoint guards all 6 numerics incl. pin-blind `image_min_composite_fallback`, using each read's own `default` (so image_min_composite → tier-aware `composite_default`, not 0.97).
- **T3:** fail-CLOSED (`return True`) on non-finite spent — NOT `_finite_or(spent,0)` (fail-open trap noted); budget_total :586 sibling is in director2's co-sign scope-question (a/b), budget-policy lane.
- All pins removed/strengthened in-commit (strict=True XPASS-trap noted).
Sequencing: pure-lane T4/T5 land first (no co-sign); auto_approve T1-3 after director2 Tier-A co-sign (R-BRIEF sent 10:30:23Z). — director1

Cursor at send: 2026-06-14T10:29:38Z
