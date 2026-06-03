---
from: operator
to: director
kind: coordination
re: Part-5 Phase-A item 2 (prune) executed — 5 confirmed-dead concerns, 327 LOC; ADR draft for you to append
related-commits: b4a03c8 e31d6a2 45c2299 6e8ce34 8a5d425 51f1826
---

User directed "next testing pieces" → executed the Part-5 Phase-A item-2 prune (re-verify Part-2
prune list → prune PRs). Read-only re-verify audit first (cold agent, re-grep incl. tests +
dynamic/string refs per `feedback_re-verify-before-destructive-commits`); user chose "prune
confirmed-dead, keep nuance."

**Done (5 chore commits + doc-sync, on feat):**
- `b4a03c8` reporter.py (52 LOC, true orphan) · `e31d6a2` generate_characters.py (68, superseded) ·
  `45c2299` dialogue_writer.{format_dialogue_for_voiceover,dialogue_to_narration_text} (28) ·
  `6e8ce34` continuity_engine.{record_shot_generated,reset_scene} (7; `last_generated_image` left —
  still live, 8 prod + 10 test refs) · `8a5d425` run_tier_c.py (172).
- `51f1826` docs(arch-sync): dropped the 2 stale ARCHITECTURE.md refs (record_shot_generated §7.5,
  reporter.py §17). **Total 327 LOC. Suite 1512/3/0 UNCHANGED, §15 smoke OK, anchors clean.**

**KEPT (not pruned):**
- `continuity_engine.validate_multi_identity` — user kept (multi-char Tier-D lever).
- `auto_approve.summarize_audit` — user kept (has a unit test).
- **`cinema/pipeline.py::CinemaPipeline` — RECLASSIFIED to KEEP.** On inspection it is NOT dead code:
  ARCHITECTURE §4.8 calls it a **"preserved primitive"**, §15.9 is a deliberate zero-callers GUARD
  invariant, and cinema/phases/{base,__init__} reference it as the "future orchestrator" of the phase
  scaffold. Pruning it would remove a documented design artifact + a §15 invariant. Surfaced to user;
  recommending keep. (I pulled it from the mechanical batch specifically to avoid a careless §15
  truth-doc edit.)

**ACTION FOR YOU (Strategic-seat — DECISIONS.md is yours):** append an ADR for this prune (spec mandates
"ADR per ADR-016"). Draft below; assign the next number + commit:

---
## ADR-0NN: Prune 5 confirmed-dead modules/symbols (327 LOC)
**Status:** Accepted (2026-06-03). **Precedent:** ADR-016 (GitNexus removal).
**Context:** The Test/Audit program (Part 2) flagged suspected dead code. Each candidate was
re-grepped at HEAD incl. tests + dynamic/string refs (cold audit, per
`feedback_re-verify-before-destructive-commits`). User approved pruning the confirmed-zero-reference
set; nuance items kept.
**Decision:** Removed (one chore commit each, on feat): reporter.py (52) · generate_characters.py (68,
superseded by `character_manager.create_character_with_images`) · `dialogue_writer`.{format_dialogue_for_voiceover,
dialogue_to_narration_text} (28) · `continuity_engine`.{record_shot_generated, reset_scene} (7;
`last_generated_image` retained — still live) · run_tier_c.py (172). Total 327 LOC. ARCHITECTURE.md
doc-synced (51f1826).
**Kept (explicitly NOT pruned):** validate_multi_identity (multi-char Tier-D lever), auto_approve.summarize_audit
(tested), cinema/pipeline.py::CinemaPipeline ("preserved primitive" per §4.8 + §15.9 guard — intentional scaffold).
**Consequences:** −327 LOC maintenance surface; zero behavior change (zero callers); suite 1512/3/0 unchanged,
§15 smoke OK.
---
