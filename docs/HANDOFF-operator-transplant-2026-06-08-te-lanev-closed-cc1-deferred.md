# Operator transplant handoff — 2026-06-08 — T-E Lane V CLOSED; coalesced CC-1 Lane V DEFERRED (#1 pickup)

> **Seat:** operator. **Written:** 2026-06-08T03:53Z. **Wrap trigger:** user "handoff".
> **State at write (verified `git log --oneline -10` + `git ls-remote`):**
> `origin/main == origin/feat/max-tier-provisioning == a0480f5` GREEN.
> Local `feat` HEAD `1fa3966` = AHEAD of origin by **1** (director's unpushed
> coord-mailbox commit — NOT operator work; not load-bearing).
> Suite **1818/0**, ci_smoke OK, gate CLOSED (`cinema/aspect.py:23 = ["16:9"]`),
> verified by director's pre-merge gate at `a0480f5`.

---

## ⭐ #1 PICKUP — coalesced CC-1 Lane V on portrait Phase-2 (OWED, deferred, fully specified)

Director requested this twice (`03-19-36Z`, `03-49-03Z`) and pre-decided the
disposition. It is **the single open operator obligation.** It is **non-urgent**
(work is inert: gate closed → every portrait site is a 16:9 no-op until Phase 3),
so deferring it across a transplant is safe. Run it as your first action.

**Exact range (copy verbatim into the reviewer prompt):**
```
git diff 3902ed4..c3e90fe -- cinema/aspect.py phase_c_assembly.py quality_max.py \
  tests/unit/test_cinema_aspect.py tests/unit/test_phase_c_assembly_portrait.py \
  tests/unit/test_quality_max_portrait.py
```
(Those SHAs are reachable from `a0480f5`/main — unchanged by the merge.)

**Phase-2 production commits in range:**

| Task | Commit | What |
|---|---|---|
| 1 | `40ca756` | `portrait_swap` + `fal_image_size` helpers (`cinema/aspect.py`) |
| 2 | `cc0c984` | production ComfyUI node-102 ctx read + transpose |
| 3 | `daaba13` | FAL Kontext/Pro/schnell + Pollinations → 9:16; aspect read hoisted to `generate_ai_broll` top; `_fal_flux_fallback` gains `aspect_ratio=None` threaded from 6 sites |
| 3-fix | `dff7c61` | extract `fal_aspect_ratio` helper (kill duplicated ternary) |
| 4 | `6a05c42` | max-tier `_inject_aspect` transposes node 102 (1024×576→576×1024) + node 950 (3840×2160→2160×3840) once before the best-of-N deepcopy fan-out |
| 4-fix | `c3e90fe` | drop `_gps` alias; strengthen ordering test with non-default `final_resolution` |

**Files (Phase-2 only):** `cinema/aspect.py` (+29), `phase_c_assembly.py` (+43),
`quality_max.py` (+28), 3 test files (+429).

**Emphases (operator-set, restated by director for the brief):**
1. **aspect-ratio plumbing** — read via `get_project_setting(ctx, "aspect_ratio", DEFAULT_ASPECT_RATIO)` (None-safe); threaded, NOT a new fn param; no `controller.py` edit.
2. **assembly cross-system effects** — `_fal_flux_fallback` is also called directly by `test_phase_c_assembly_provenance.py` (6 sites, no aspect_ratio → landscape; backward-compat).
3. **16:9 byte-identity** — landscape/None/unknown must be a no-op at every site (`portrait_swap` returns input dims; `fal_aspect_ratio`/`fal_image_size` default landscape). **Worth a refute-test: does ANY site change 16:9 output?**

**Method:** Rule #17 dual cold workflow (spec + code-quality), per-finding adversarial
verify, CC-2 hallucination guard, R#17-C2 spot-check the cited evidence before the
report re-enters protocol. Director already ran their OWN final cross-cutting review
(ready-to-merge, 2 MINORs folded `cf75e24`); yours is the Rule #9 **independent**
second opinion — construct cold from `3902ed4..c3e90fe` + the portrait spec only; do
NOT cite director's findings.

**Disposition (Rule #15, pre-decided by director `03-49-03Z`):** Phase-2 is already
on main, so any finding closes as a **standalone `fix:` on main (option b)** — option
a (fold-into-unmerged) is foreclosed by the merge. Even a CRITICAL is a dormant-9:16
correctness fix, not a production risk (gate closed). Land the report; director
processes per Rule #8.

---

## ✅ DONE this session (T-E Lane V — fully closed, on main)

Picked up mid-flight (prior operator context `/clear`'d during T-E Stage 4). Resumed
and completed the operator-driven Lane B (Rule #14) close-out for **T-E**
(`9403f87` shared char-filter helpers + 2 F1b/native bug-site fixes; `e68e5fb` hygiene
minors — both from the pre-`/clear` context).

**Verification:** two independent Rule #17 dual cold reviews (one inherited, one
re-dispatched covering the full range incl. the chore), each with per-finding
adversarial verify. **Strong cross-run convergence**; both adversarial passes
independently downgraded the headline IMPORTANT→MINOR. **0 hallucinations** (CC-2 held).

**Findings (4 confirmed / 3 refuted) — all self-closed (fix-on-own-findings):**

| # | Finding | Sev | Closed by |
|---|---|---|---|
| 1 | Bug site B (`controller.py:1475` native `_ensure_scene_audio` fallback) proxy-pinned only — a revert stayed green; production code **correct** | MINOR (↓IMPORTANT) | **`b2f5444`** test pin |
| 2 | `cinema_pipeline.py:22` dead `shot_characters` import | MINOR | **`f2b387e`** |
| 3 | `screening.py:61` module-import made lazy `_cache_key` guard `:560-563` dead code | MINOR | **`f2b387e`** |
| 4 | `screening.py:652` stale comment ref → relocated `controller.py:1373-1380` | INFO | **`f2b387e`** |
| — | prompt-optimizer `:568-570`; tolerant guards; local-var shadow | REFUTED | — |

**`b2f5444` detail (the technique worth carrying forward):** the site-B test drives
the REAL `generate_motion_take` into the `:1475` line via a precise reachability
setup — **native** voice_mode + `KLING_NATIVE` pinned non-AUTO (only `VEO_NATIVE` has
`native_audio` in `domain/scene_decomposer.py:43` → `audio_embedded` stays unset →
lipsync block runs) + `_f1b_audio` None + 2-char-present/1-in-frame so scene-vs-in-frame
is discriminable. **Red-phase verified**: reverting `:1475` to in-frame turns it RED
(`{'char_1'} != {'char_1','char_2'}`), restored → green. *Lesson: a green test on a
"covered" line proves nothing without the red-phase revert — finding #1 was exactly a
12-test suite that pinned the helper contract but never executed the production line.*

**Verification-report:** `37fbed7` (event `2026-06-08T03-03-02Z`). Suite **1813/0** at
my tip, then **1818/0** at `a0480f5` after director's Phase-2 (+5 portrait tests).
T-E tickets doc (`docs/TICKETS-2026-06-08-reassembly-audio.md` §T-E) acceptance now
FULLY met ("regression tests pin both F1b/native sites").

---

## Coordination state

- **Cursor:** operator `seen/operator.txt` → **`2026-06-08T03:49:03Z`** (both director
  Phase-2 events processed). **0 unread.**
- **Sent this session:** `01-58-00Z` dispatch-claim, `02-02-00Z` coordination,
  `03-03-02Z` verification-report, `03-53-04Z` wrap-coordination (all committed:
  `37fbed7` + this handoff's commit).
- **Director:** active; presence head `1fa3966`; was standing by for my CC-1 Lane V —
  my `03-53-04Z` event tells them it's DEFERRED (not in-flight) so they stop blocking.
- **D-a:** ACTIVE. `CLAUDE_SEAT=operator`, `GIT_INDEX_FILE=…/index-operator`. Stale
  per-seat index bit twice this session (phantom `phase_c_assembly.py` mods after
  peer commits) → `git read-tree HEAD` cleared it. **Always pathspec-commit**
  (`git commit -m … -- <paths>`, `-m` BEFORE `--`). Run pytest with
  `env -u GIT_INDEX_FILE`.

## Other open carry-forwards (unchanged from prior handoffs; not owed by operator now)

- **F5** `visual_findings` FE render (director-tracked).
- **Rule #18** `chief_director.py` MANUAL/digests anchor sweep (~30 anchors).
- **Portrait Phase 3** (per-provider 9:16 video + un-gate) — own-spec-later; Rule #17
  survey found the §7-D matrix under-counts (Veo API-capable+unwired; Kling no aspect
  param; Sora/LTX/Hedra unverified; Runway 2 sites `phase_c_ffmpeg.py:363/:682`;
  Seedance `:718`). The CC-1 Lane V (#1 above) is Phase-2 only; Phase 3 is separate.
- **On-pod 9:16 latent validation** (post-merge; max-tier `pulid_max.json` node-102/950
  transpose).

## 🔑 Quick-start for next operator

1. **Session-start:** run `ARCHITECTURE.md` §15 smoke (`.venv/bin/python scripts/ci_smoke.py`).
   `git log --oneline -10`; `cat coordination/presence/director.md`.
2. **#1:** dispatch the coalesced CC-1 Lane V (range + emphases + disposition above).
   Send the `verification-report`; close any finding as standalone `fix:` on main.
3. **Hygiene:** `env -u GIT_INDEX_FILE` for pytest; `git read-tree HEAD` if `git status`
   shows phantom mass-mods after a peer batch; pathspec commits only.

— operator, 2026-06-08T03:53Z
