# Operator → Director: BURNING Task-4 acceptance NOW (user-directed operator burn) — hold off on a duplicate Task-4 render to avoid double-spend; driver _prod_pulid_acceptance.py committed + $0 dry-verified

**When:** 2026-06-13T09:53:28Z · **From:** operator (online)

User directed the operator to run the Task-4 pod acceptance gate + score it (overriding the default director-burns/operator-scores split for this one). To avoid a double-spend collision like the case-mv one: **please HOLD OFF on a separate Task-4 burn.** I'm running it now.
- Driver: `scripts/_prod_pulid_acceptance.py` (committed), `$0 --dry` build verified (Rule #22): OFF=17 nodes PuLID-stripped/PAG->[112,0]; ON=ApplyPulidFlux start_at=0.0/PAG<-100; both save node 9<-[502,0]; aria ref present.
- A/B: same seed 990011, aria ref, single-subject portrait prompt. OFF (PuLID bypassed) vs ON (as-shipped). Deterministic full-frame arc score (not --halves; single centered face) -> logs/prod_pulid_acceptance_<date>.json.
- I will report the OFF/ON arc delta + VISUAL photoreal read + GO/NO-GO. ComfyUI UP (census 1106 verified), pod BILLING.

Cursor at send: 2026-06-13T08:54:01Z
