# Director transplant handoff — 2026-06-09

**Portrait 9:16 delivery is LIVE on `main` (T10 merged). Final cross-cutting review
done (Rule #17) + all feat/fix commits cross-seat Lane V'd ✅ SAFE. One MINOR
follow-up open: lip_sync portrait-fencing (the M-1 twin).**

---

## 0. State at wrap (verified, not remembered)

| Fact | Value | How verified |
|---|---|---|
| Branch | `feat/max-tier-provisioning` | `git status` |
| HEAD | **`05c710e`** | `git rev-parse HEAD` |
| `origin/main` | **`05c710e`** ⭐ MERGED (was `a0480f5`) | `git rev-parse origin/main` |
| `origin/feat` | `05c710e` (synced) | `git rev-parse origin/feat/...` |
| Gate `cinema/aspect.py:25` | `SUPPORTED_ASPECT_RATIOS = ["16:9", "9:16"]` — **OPEN, portrait LIVE** | `sed -n 25p cinema/aspect.py` |
| Suite | **1920 passed / 0 failed / 2 skipped** | `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/ -q` |
| `ci_smoke` | **exit 0** | `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` |
| Mailbox (director) | **0 unread**; cursor `00:53:45Z` | consumed operator's wrap |
| Both seats | wrapping/offline at wrap (user said "handoff" to both) | `coordination/presence/*.md` |

**The whole Phase-1→3 portrait arc + the operator's Slice-3 verifier work are now on
`main` (clean FF `a0480f5..05c710e`).** Nothing owed either direction.

---

## 1. ⭐ #1 PICKUP — lip_sync portrait-fencing (the M-1 twin; MINOR, tracked)

My Rule #17 final review surfaced a PRE-EXISTING defensive-symmetry gap (the operator's
diff-scoped Lane V correctly didn't flag it — it's outside the T10/M-1 diffs):

- **`lip_sync.py:579` (Kling) / `:600` (Omnihuman v1.5) / `:624` (Aurora)** call FAL
  providers **directly** (not via `generate_ai_video`), pass **no aspect param**, and have
  **no orientation backstop** (the lipsync gate checks SyncNet quality, not orientation).
  Only Hedra (`:557`) derives aspect via `_hedra_aspect_ratio_from_image`.
- **This is the structural twin of the M-1 storyboard bug** (provider call bypassing the
  F1 guard + `_accept_or_reject` backstops). Reachable for dialogue shots via
  `cinema/shots/controller.py:1485,2080`.
- **MINOR / no live broken artifact today:** FAL avatars preserve the input keyframe's
  aspect, and assembly normalize+pad guarantees the portrait container (the I1-guard path,
  now regression-pinned — see §2). So no LANDSCAPE final artifact; the gap is the absence
  of an explicit fence.

**Fix (a fresh slice, own-spec-or-direct):** thread aspect into the 3 FAL providers (mirror
Hedra's `_hedra_aspect_ratio_from_image` pattern), OR add an orientation backstop in
`lipsync_generation` mirroring `_accept_or_reject`. TDD. **The operator will run a cold Lane V
on it next session** (per the boundary convention; they've committed to this in their wrap).

Other open carry-forwards (lower priority):
- **On-pod 9:16 latent validation** (manual, GPU-up) — still open from the Phase-2/3 arc.
- The 2 ARCHITECTURE.md multi-range comma-list anchors were **quieted** by the operator's
  §16 truth-sync `b67bf7f` (ci_smoke verifier now clean) — no longer open.

---

## 2. What shipped this session (user-directed "run it" → "merge now")

The whole T10 landing, in order, all green:

| SHA | Type | What |
|---|---|---|
| `28ed484` | **M-1** `fix(motion)` | Disqualify the storyboard batch path at portrait (ANDs `not is_portrait(_aspect)` into `storyboard_mode` in `motion_render.run()` → falls through to the guarded per-shot path). TDD; 32/32. |
| `2aa5718` | **T10** `feat(aspect)` | Un-gate `["16:9"]` → `["16:9","9:16"]`. Portrait LIVE. TDD gate-test flips + ARCHITECTURE.md §8.2/§8.3 doc-sync. Preflight 5/5 in body. |
| `2de7847` | `fix(decompose)` | Orientation-aware R4 prompt descriptor — no hardcoded "widescreen" for 9:16 (was biasing gpt-4o framing horizontal for portrait). + test + 2 ARCHITECTURE.md anchor fixes my edit shifted. |
| `8b0da35` | `test(aspect)` | I1-guard portrait-container regression pin at `_assemble_final` (GUARD PROVEN via injected letterboxing mutation) + config-gate value-assert. |

**Live preflight (ADR-013, in T10 body): effective 5/5.** Full preflight
(`scripts/_phase3_portrait_preflight.py`) returned 4/5 — VEO alone blocked by the Vertex RAI
content-filter on the default keyframe (free, non-deterministic, non-code). A VEO-only re-check
on a known-good keyframe (`scripts/_veo_recheck.py`, project `aa777d858e71`) passed **720×1280**,
confirming the flake. Sora 720×1280 / Kling 1216×1664 / Runway 720×1280 / FAL 576×1024 all PASS.
(In production the F1-guarded cascade also recovers from a VEO RAI-block → Sora/Kling/Runway.)

---

## 3. Reviews — doubly-verified safe

- **My Rule #17 final cross-cutting review** (`wf_36dc3739`, 9 agents, ~845k tokens): 0 CRITICAL,
  0 IMPORTANT in the diffs; **landscape byte-identity HOLDS, M-1 correct**. Surfaced 4
  pre-existing latent issues the open gate exposed: I1-guard test gap (IMPORTANT → fixed
  `8b0da35`), widescreen prompt (MINOR → fixed `2de7847`), config tautology (MINOR → fixed
  `8b0da35`), lip_sync twin (MINOR → §1 follow-up). 0 refuted (all 4 survived adversarial verify).
- **Operator cross-seat Rule #9 Lane V ×4, all ✅ SAFE:** pre-T10 stack `6acefd1` (caught M-1);
  portrait-ungate `2968c5c` (landscape byte-identity PROVEN, Rule #13 audit clean); `2de7847`
  `05c710e` (16:9 byte-identical). The portrait-ungate is independently confirmed safe from two
  cold angles.

**ADR-013 correction (recorded):** I initially misattributed "7 full-suite failures" to the
operator's committed Slice-3 pollution + credited `ceb6b15` for the fix. Wrong on both: they were
a **concurrent dirty-tree transient** (running the full suite against the peer's in-flight tree),
cleared at tree-settle. Lesson saved to memory. **Don't run `pytest tests/` against a dirty shared
tree mid-concurrent-work; scope acceptance to committed state.**

---

## 4. Cross-seat (operator)

- **Operator Slice-3 COMPLETE** (`e77ce9c`/`20a165b`/`2257976`/`ceb6b15`/`3036cd9`/`5ffcd4c` +
  §16 truth-sync `b67bf7f`) — range-anchor verifier; on `main` now. Their handoff:
  `docs/HANDOFF-operator-transplant-2026-06-09-slice3-done-three-lanev-safe.md`.
- Both lanes were disjoint (my video/code line vs their doc/verifier line), git-serialized; the
  merge shipped both in their complete state.
- lip_sync (§1) is the one open cross-seat item: my fix, their next-session cold Lane V.

---

## 5. Operational notes (D-a per-seat index active)

- `CLAUDE_SEAT=director`, `GIT_INDEX_FILE=.git/index-director`.
- **`env -u GIT_INDEX_FILE`** for pytest + ci_smoke (per-seat index confuses them).
- **Pathspec commits** mandatory: `git commit -m "…" -- <paths>` (`-m` BEFORE `--`); `git add`
  explicit paths for new files (pathspec-commit won't stage untracked). NEVER `git add -A`.
- **`git read-tree HEAD`** before each tracked commit + after any Workflow (and to clear the
  `MM`/`D` D-a index-staleness that appears when the peer commits — those are NOT real
  uncommitted changes).
- **D-a-safe FF merge = `git push origin <verified-sha>:main`** (NO checkout while peer active —
  it would disturb the shared tree). Merge the EXACT SHA you verified green; capture HEAD
  before+after the verify run to confirm it didn't move.
- **Verify-THEN-commit** as separate steps (Rule #7 caught peer commits landing mid-work several
  times this session — all benign, race-ack'd).
- **Workflow gotcha:** `run_in_background` is NOT a Workflow param (it always backgrounds); and
  NO backticks inside a template-literal prompt string (premature-close parse error) — build
  multi-line prompts with an array + `.join('\n')`.
- Presence: set `status`/`current_task`; `status: wrapping` at session end. The hook races your
  presence Edits (bumps `updated`/`head_at_write` every tool call) — expected, low-value, don't fight.

— director (wrapping)
