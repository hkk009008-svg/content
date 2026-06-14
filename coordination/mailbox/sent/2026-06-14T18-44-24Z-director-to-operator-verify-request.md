# Director → Operator: has-char-lora-hole + secondary-lora-hole 23c99e3 — Lane V (impl != verifier); KEY = node-700 REACHABILITY not just presence

**When:** 2026-06-14T18:44:24Z · **From:** director (online)

**Pair-A Wave-2 A1-lora-decouple — your Lane V (Rule #9; impl = director-1-orchestrated implementer subagent, NOT you).**

## Rows (two, one root)
- `has-char-lora-hole` (W2 MAJOR, quality_max.py:1060) — a LoRA-only shot silently dropped its trained LoRA.
- `secondary-lora-hole` (W2 MEDIUM, quality_max.py:1119, same root).

## Commit (LOCAL — push user-gated)
`23c99e3` fix(identity): decouple has_face_ref from has_char_lora. **Explicit-pathspec scoped (26 files)** — the shared tree's git index carries PHANTOM skip-worktree deletions (≈50 peer money-lane files show as D/?? but are on-disk + in-HEAD); verify with `git diff --no-index <(git show HEAD:path) path`, do NOT trust `git status`. My commit has ZERO deletions (`git show --diff-filter=D --name-only 23c99e3` empty).

## Brief (the full spec + verified topology)
`docs/superpowers/briefs/2026-06-15-has-character-decouple.md`.

## Fix
Split the single face-ref flag into has_face_ref (PuLID 93/97/99/100/101 + face upload + ReActor/FaceDetailer 610/600 + ArcFace/regen) and has_char_lora (LoRA node 700 + _inject_identity LoRA arm + secondary gate). New `_surviving_model_src` (priority 100>700>112) makes the always-on FLUX-incompat bridge 700-aware. secondary gate -> `if has_char_lora or has_secondary_lora`.

## THE verification that matters (don't stop at the pins)
The pins assert `"700" in wf` — NECESSARY BUT NOT SUFFICIENT. The trap: a LoRA-only shot prunes PuLID(100); the FLUX-incompat bridge would bypass to base UNet [112,0], leaving node 700 PRESENT BUT ORPHANED (LoRA loaded, render ignores it). Verify **node 700 is REACHABLE from BasicGuider(22) via model edges** for the lora-only case (has_face_ref=False, has_char_lora=True, char_lora set). New test `test_lora_only_shot_node_700_reachable_from_guider` covers it. Non-vacuity: mutate `_surviving_model_src` to return "112" (or the pulid_target to ("112",0)) and confirm that reachability test goes RED.

## Rule #13 / impact-analysis
A conformance reviewer caught my brief's grep MISS: 16 experiment scripts called `_prune_unavailable` positionally (not via the has_character name). All 19 call sites now on the 5-arg sig — AST-verified 0 non-5-arg repo-wide; 16 scripts behavior-preserving (X -> X,X). Naive-crash guard: face upload gates on has_face_ref (a merged flag would crash `_upload_with_cache(None)`).

## State
Both xfail pins flipped to live regressions. Full unit suite 2497p/0f, ci_smoke OK (my working tree; re-run at 23c99e3 — note peer-dirty-tree caveat for attribution). Pre-commit reviews: graph-reachability GO (4 cases) + brief-conformance GO (after the 16-script fix).

## Reviewers
`lane-v-verifier` (cold-context) is the core pass. Not a money row — the graph-reachability lens is what matters; re-derive the 4 shot cases (landscape/face-only/lora-only/face+lora) yourself. On GO -> coordinator reconciles open->verified (rows currently still "open" in the inventory; coordinator owns it, online).

Cursor at send: 2026-06-14T18:34:24Z

Cursor at send: 2026-06-14T17:42:12Z
