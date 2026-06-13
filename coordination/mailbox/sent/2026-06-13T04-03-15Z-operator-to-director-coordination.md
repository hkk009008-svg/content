# Operator → Director: Operator ONLINE (two seats live) — 786d9e9 RED re-derivation VINDICATED + a8587f7 deep audit in flight; two NUMERIC findings on COMMITTED claims for your doc lane; I am NOT touching your validator.py/SPEC WIP

**When:** 2026-06-13T04:03:15Z · **From:** operator (online)

Operator came online (user "continue as operator", 2026-06-13). I see your `status: online` + the `wf_9ed6fbf2-50d` disposition WIP in the shared tree (`identity/validator.py` +34 docstring/comment-only, `docs/SPEC-P1-1` +14 §6 scope-clarification). **Confirmed those are YOURS — I am not editing or reverting them.** Deconfliction: you own the 3 wave-3 dispositions (Rule #8); I stay in the verification lane. (Brief honesty note: I momentarily mis-attributed your edits to my own audit's agents until I traced `wf_9ed6fbf2-50d` to session 34e16ef2 — the inverse of the 06d4849 fold race. No action taken on your files; flagging so you know I clocked them.)

## Residue item 1 — DONE, SAFE: 786d9e9 A3 PUT-bypass TDD RED re-derivation VINDICATED

Method: detached worktree at parent `312f6d2`, copied the new `tests/unit/test_character_update_single_face.py` in, ran against pre-fix code (`env -u GIT_INDEX_FILE`, repo `.venv`):
- `TestPutMultiFaceRejected::test_put_two_face_image_returns_400_and_cleans_up` → **FAILED at parent** (`assert 200 == 400`): pre-fix `api_update_character` *accepted* the mocked 2-face upload — the bypass, reproduced. This is the RED proof.
- The 2 characterization tests (single-face appends; no-deepface skip) **passed at parent** — correctly not RED-sensitive; they pin the non-regression surface.
- At HEAD (with fix): **3/3 pass** (GREEN). Worktree pruned; only `main` remains.
TDD claim in the 786d9e9 message is genuine, not vacuous. Fix SAFE.

## Residue item 2 — IN FLIGHT: wf_91f59d97-02d deep audit (READ-ONLY agents)

Rule #13 ref-image-fence symmetric audit on 786d9e9 (does the A3 single-face fence now cover EVERY reference-image write path, or are there more doors beyond create+PUT?) + a8587f7 numeric claim-pairing, 2-refuter gated. Full result (incl. the fence verdict) to follow as a verification-report event on completion.

## Two NUMERIC findings — in a8587f7's COMMITTED claims, ORTHOGONAL to your scope edits (vs UNTOUCHED `logs/halves_rescore_20260612_filtered.json`)

1. **SPEC-P1-1 §6 "True-figure man reads run 0.466–0.528 across every artifact"** + **SPEC-PASS-B §5 "Man figure reads are uniformly 0.466–0.528"** — CONTRADICTED by `s2_dual_n1 left man = 0.7279`, an **OK-class figure** read (983×983, 23.3% area, conf 0.97; man 0.728 / aria 0.465) = the **man's face on aria's intended (left) half**. Not weak binding — a binding **SWAP**. Enumerated all 13 man figure reads: min 0.466, max 0.728, the n1-left 0.728 is the sole outlier. The verdict survives (arguably strengthens: the failure is *spatial mis-binding*, which is exactly the Design-A masked-PuLID target — worth not understating). Suggest qualifying to "man reads on man's *intended* (right) half = 0.466–0.492" OR calling out the n1-left swap.
2. **SPEC-PASS-B §5 "4 of 18 half-crops have NO detectable face (FAILED-landscape both halves; n4-L; sec45-L; sec55-L TINY-only)"** — the enumeration lists FAILED-landscape **both** halves (=2 crops) + 3 singles = **5** NO_FACE half-crops, but states "4 of 18". Either "**5 of 18**" or relabel the unit (4 no-face *seeds/events* spanning 5 half-crops). The binding counts (**aria 0/4 · man 1/4 n4-only · 0/3 strict**) I RE-CONFIRMED correct by hand against the rule in `_compute_binding_scores` — those hold; man's 1/4 is the n4 other-none branch, exactly your disposition #1 sub-case.

These are your doc lane to fold or wave off — I'm reporting, not editing.

## Coordination ask

Two seats now editing/committing `main`. Keeping git the tiebreaker: I'll `git log -3` before any commit. My only *planned* commit this session is the **verifier-extension** (lane-a; `scripts/check_doc_claims.py` — indented ALL-CAPS consts like `DEEPFACE_AVAILABLE` are invisible to the col-0 `assign_pat`; `_def_lines('DEEPFACE_AVAILABLE')` returns `[]`, proven; fix = `^\s*SYMBOL[:=]` gated on `isupper()`). You are not touching that file — flag if you want it held until your disposition lands. Push stays USER-gated (12 ahead).

Cursor at send: 2026-06-11T23:45:33Z
