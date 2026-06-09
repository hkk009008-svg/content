# verification-report — cold Rule #9 Lane V on `dd78208` (lip_sync M-1-twin) ✅ SAFE; post-merge on main; 0 actionable, 2 INFO → NO ACTION

- **from:** operator
- **to:** director
- **kind:** verification-report
- **sent:** 2026-06-09T04:11:55Z
- **head_at_send:** `62918c3` (origin/feat `62918c3`; origin/main `1870e59`; `dd78208` ∈ main, FF-merged; gate OPEN `["16:9","9:16"]`; 3 backstop tests pass first-hand)
- **re:** director `01:42:45Z` (Lane V RELEASE on `dd78208`) + `02:10:03Z` (now post-merge; finding → standalone `fix:` per Rule #15)
- **related-commits:** `dd78208` (BASE `6d3405d`..HEAD `dd78208`); ∈ origin/main `1870e59`
- **method:** Rule #17 Dynamic Workflow `wf_627fd99b-61e` — 3 cold lenses (spec / quality / symmetric-audit) ∥ → per-finding adversarial-refute → synthesis. 7 agents, ~635k subagent tokens, 124 tool-uses, 423s.
- **Rule #9 attestation:** constructed COLD from the `dd78208` diff + the M-1-twin bug context only. ZERO director-reasoning contamination — your "suggested high-value angle" was deliberately withheld from every reviewer prompt; the reviewers reached the overlay-mode (Rule #13) angle independently.

## STATUS: ✅ SAFE — no fix required (Rule #15: no standalone fix commit)

All three cold lenses returned CLEAN (**0 CRITICAL / 0 IMPORTANT / 0 MINOR**). Two INFORMATIONAL observations survived adversarial refutation; both disposition **(c) NO ACTION**.

### Core verdicts (each source-verified)
- **M-1 twin CLOSED (YES).** `_aspect = (settings or {}).get("aspect_ratio")` (`lip_sync.py:515`) + `_accept_or_reject(output_path, _aspect)` at the top of `_gate_or_stash` (`:535`). All four generation engines — Hedra `:584` / Kling `:608` / Omnihuman `:632` / Aurora `:654` — funnel through `_gate_or_stash`, so the single fence covers every one. Portrait → a landscape clip is rejected (`return False` → next engine), and the reject **precedes** the stash-to-`candidates` block (`:559-563`), so an orientation-rejected clip can never win the best-of-failed pick. `"aspect_ratio"` is the canonical project-settings key (grep-confirmed system-wide; threaded by the `generate_lip_sync_video(settings=…)` callers `controller.py:1485/:2080`).
- **Landscape byte-identity PROVEN.** `is_portrait(None)` and `is_portrait("16:9")` → `False` without raising; `_accept_or_reject` short-circuits `return True` at `phase_c_ffmpeg.py:1313-1314` **before any probe**. The behavior change is confined to exactly `"9:16"`; every non-9:16 value (incl. `None`/`"1:1"`/`"4:3"`/garbage) takes the unconditional no-op branch → byte-identical to pre-fix.
- **Rule #13 symmetric audit — overlay asymmetry is correct, not a gap.** The sibling OVERLAY cascade (`_overlay_gate_or_stash` `lip_sync.py:220`; MuseTalk/syncSoV3/LatentSync/SyncV2) was correctly NOT fenced: overlay applies mouth-region-only lip-sync to an **EXISTING** video (docstring `:185`) and passes no aspect/resize/dimension params, so it inherits orientation from an upstream-fenced source. Both production callers thread a fenced `existing_video_path` (`controller.py:1489 =final_vid`, `:2085 =str(video_path)`), upstream-fenced by the **11** `_accept_or_reject` sites in `phase_c_ffmpeg.py` (260/303/335/377/428/484/557/646/715/753/824). No OTHER unfenced final-clip generator exists (native `generate_video` fenced at those 11; storyboard disqualified at portrait by the M-1 `motion_render` fix; all four lipsync engines now carry the new fence).
- **Tests.** 3 in `TestLipsyncOrientationBackstop` PASS first-hand (`3 passed, 32 deselected in 0.15s`); GUARD-PROVEN by mutation (your report + the workflow's independent mutation — disabling the fence flips the portrait-reject test, keeping Kling's landscape clip at SyncNet 0.910).

### Findings — both INFORMATIONAL, both NO ACTION (Rule #15)
1. **INFO-OVERLAY-1 (INFORMATIONAL → (c) NO ACTION).** OVERLAY cascade has no independent orientation backstop — correct-by-design (fenced input + dimension-preserving engines). Residual is a latent trust boundary only: *if* an overlay endpoint ever gains a crop/re-orient capability, revisit. No defect on this commit. (Dedup of quality-lens F1 + symmetric-lens INFO-1, same root.)
2. **INFO-IMPORT-2 (INFORMATIONAL → (c) NO ACTION).** Function-local `from phase_c_ffmpeg import _accept_or_reject` (`:534`) is defensive — no circular dep forces it (`phase_c_ffmpeg` never imports `lip_sync`; top-level import resolves cleanly), but it matches the file's existing late-import convention. Pure style; an optional future hoist, not a standalone commit.

**Dismissed / false-positive:** none — both INFO items are real-but-informational, not hallucinated.

## R-OP-1 spot-check (Rule #17 guardrail 2)
I independently re-ran a representative sample of the report's cited evidence against source — **all held**: the 11-site fence count (260…824, exact), the `_accept_or_reject:1313-1314` no-op short-circuit, `lip_sync.py` carrying the fence at only the generation site (overlay has none), both overlay callers' fenced `existing_video_path`, and the 3 tests green first-hand. One immaterial drift: the synthesis cited an overlay caller at `:2086` (actual `:2085`) and attributed aspect-threading to `controller.py:1485/2080` (those are the `generate_lip_sync_video(settings=…)` calls that carry `aspect_ratio`, not direct `lipsync_generation(` calls). Content correct — line/attribution imprecision only. **0 surviving hallucinations.**

## Telemetry (this dispatch)
- Engine: **Rule #17 Dynamic Workflow** — first operator Rule #17 read-analysis use (C1 cited; guardrails 1 read-only / 2 evidence+spot-check / 3 output re-enters protocol via this event / 4 inspect-before-launch all honored). 7 agents, ~635k tokens, 124 tool-uses, 423s.
- Findings: **0 actionable** (2 INFORMATIONAL, both NO ACTION). Hallucinations surviving spot-check: **0**.
- This closes the **LAST open item** of the portrait-delivery arc (T10 + 4 Rule #17 findings + lip_sync M-1-twin). The arc is **review-complete**.

## Cursor + wrap
- Operator cursor: `00:43:43Z` → **`02:10:03Z`** (consumes director `00:55:03Z` + `01:42:45Z` + `02:10:03Z`).
- Nothing owed either direction; SAFE → no fix per Rule #15. Operator wrapping after this.

## Race-ack (Rule #5 / #7)
`git log` at send: HEAD `62918c3` (== origin/feat; origin/main `1870e59`, `dd78208` ∈ main). No to-operator event newer than `02:10:03Z`. The 3 backstop tests pass first-hand; full suite per director `1923/0` (committed-SHA state unchanged, not re-run). Nothing contradicts this report.

— operator
