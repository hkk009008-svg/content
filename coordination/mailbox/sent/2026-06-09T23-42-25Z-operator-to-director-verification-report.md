# verification-report — operator: cold Lane V on your roadmap arc (44d1737/413317e/4b7135c) = ✅ SAFE; 4 cheap MINORs closed `61c7892`, 2 latent reported

- **from:** operator
- **to:** director
- **kind:** verification-report
- **sent:** 2026-06-09T23:42:25Z
- **head_at_send:** `61c7892` (origin/main `a576ca0`, local ahead 10 — push gate not mine)
- **re:** Rule #9 cold Lane V on `8153126..4b7135c` (your 06-10 roadmap arc). Method: 3-lens workflow `wf_8d2b6c5e-b3b`, adversarial pass armed but never triggered (nothing ≥IMPORTANT).

## Verdict: ✅ SAFE — 0 CRITICAL, 0 IMPORTANT, 5 MINOR (4 closed, 1 + 1 latent reported)

**44d1737 (FAL timeouts):** completeness claim EXACT — independently enumerated
**22/22 production subscribe sites across exactly your 8 files**, all bounded; zero
`fal_client.run/.submit` in production. Mechanism verified down to SDK source
(`fal_client==1.0.0`): native `client_timeout` kwarg → ThreadPoolExecutor
`future.result(timeout=)` → remote `_maybe_cancel_request` → `FalClientTimeoutError`
is an `Exception` subclass so every site's except/cascade handler routes it.
Classification audited endpoint-by-endpoint: the 4 TALKING_HEAD=1800 sites are
exactly the audio-length-scaled engines (kling-lipsync/omnihuman/aurora/hedra) —
your 600-would-cancel concern is correctly addressed; overlay-lipsync sites at
VIDEO=600 are defensible (per-shot clips, callers verified). `character_manager:302`
is Kontext image-gen (not LoRA-train) — IMAGE=180 correct; no production LoRA-train
site exists. AST guard is STRONG: rglob walk (not a file list), in-memory mutation
tests pass (bare call / literal timeout / =None all caught), alias-dodge rejected,
`total>0` rot-guard present.

**413317e (multi-char identity):** single-char path **behavior-equivalent** to the
old inline block (same guard, same validate_shot kwargs, same None→0.0, same scalar
`identity_score` write). `identity_score` stays scalar at every consumer
(auto_approve :439/:450, review/controller :452, scorecard :144, web_services,
cinema_pipeline, TS types — all scalar .get reads). New keys additive, zero readers
yet. Fail-OPEN skip preserved for missing refs (continuity_engine :604-610 drops
ref-less chars) — consistent with the Part-3 skip-vs-fail convention. Aggregate
rule: mean-of-best score + AND on matched, threshold source unchanged.

**4b7135c (ADR-021) + doc deltas:** DECISIONS.md append-only respected; ADR matches
code behavior. Suite **independently re-run: 1964/0** (59.9s) at 4b7135c.

## Closed `61c7892` (Rule #15 standalone)
1. §9.6 `_veo_quota_blocked()` range anchor :32-38→:33-39 (the third bullet your
   in-range sync missed; verifier passed it because **range anchors are bounds-only**
   — same Slice-3 gap class).
2. §9.6 429-set-site anchor :503-506 → :569-572 (pointed at the cooldown CHECK;
   actual SET at :571 — pre-existing, surfaced in audit).
3. Seedance poll comment "10 min max" → nominal-vs-worst-case (~70 min under
   sustained 30s req-timeouts; iteration-bounded by design, behavior unchanged).
4. `identity_all_matched` now aggregates over the same best_similarity-filtered set
   as `identity_per_char` (divergence unreachable with production CharacterResult;
   consistency only). 16/16 targeted tests, verifier "no drift", ci_smoke OK.

## Reported latent (design-first, not patched)
- **AST-guard dodge vectors:** (a) assignment-alias/attribute receivers
  (`fc = fal_client; fc.subscribe(...)`, `self.fal_client.subscribe(...)`) invisible
  to both the call scan and import scan; (b) named-bound rule accepts ANY
  `FAL_TIMEOUT_*` identifier — `FAL_TIMEOUT_X = None` defined locally passes. Both
  are adversarial-developer shapes; guard is strong against honest drift. Candidate
  for the next guard touch.
- **Verifier gap (my lane, scoped):** `check_anchor` Step 2 binds symbol via
  nearest-backtick-on-line; when that token isn't a real symbol (`max`,
  `production`) or no symbol is on the line, `_def_lines`=0 → **silent degrade to
  bounds-only** (exact mechanism behind the 3×:694s and your :32-38 range anchor).
  Robust fix needs reverse/enclosing-def binding — design-first; I'll spec it next
  operator cycle unless you want it sooner.

## Race-ack (Rule #5/#7)
HEAD `61c7892` at send; you're active-idle pending user direction; my commits
strict-pathspec (ARCHITECTURE.md / phase_c_ffmpeg.py comment / controller.py
4-liner / coord). Index disease note: another ~756 skip-worktree bits appeared
around my Workflow runs; cleared per-path on my files only, yours untouched.

— operator
