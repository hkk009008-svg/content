# Director transplant handoff — 2026-06-08 — portrait Phase-2 EXECUTED + MERGED

**Read first if you are the next director seat.** This supersedes
`docs/HANDOFF-director-transplant-2026-06-08-portrait-phase2-spec-plan.md`
(the spec+plan handoff, now executed).

---

## 0. TL;DR / state at handoff

- **`main` == `origin/main` == `origin/feat/max-tier-provisioning` == `a0480f5`** GREEN.
  Verified `git ls-remote` at `2026-06-08T03:51:52Z`: both refs = `a0480f5`.
- Local `feat` tip is **`1fa3966`** (1 ahead of origin = the merge-coordination
  mailbox commit; coordination only, not code). Push it to sync if you like;
  the handoff commit + this doc will advance it further (see §5).
- **Suite 1818 passed / 0 failed**, `ci_smoke.py` **OK**, gate **CLOSED**
  (`SUPPORTED_ASPECT_RATIOS == ["16:9"]`, `cinema/aspect.py:23`). Re-verified at
  HEAD immediately before the merge.
- Mailbox: director cursor `2026-06-08T03:03:02Z`; **0 unread**; nothing owed.

## 1. What this session did — portrait Phase-2 (native 9:16 image keyframes), executed + merged

Executed the 5-task plan `docs/superpowers/plans/2026-06-08-portrait-phase2-native-keyframes.md`
via `subagent-driven-development` (fresh implementer per task → spec review →
code-quality review; two review IMPORTANTs + final-review MINORs folded as
separate `fix:` commits). All on main now.

| Task | Commit(s) | What |
|---|---|---|
| T1 | `40ca756` | `portrait_swap` + `fal_image_size` helpers in `cinema/aspect.py` (landed prior session) |
| T2 | `cc0c984` | production ComfyUI node-102 latent transpose (1344×768→768×1344); aspect read from already-threaded `ctx` (no new param, no `controller.py` edit) |
| T3 | `daaba13` + `dff7c61` | FAL Kontext/Pro/schnell + Pollinations → 9:16. **Load-bearing fix:** aspect read HOISTED to `generate_ai_broll` top; `_fal_flux_fallback` gained `aspect_ratio=None` (backward-compat) threaded from **6** call sites incl. early-return + `except` paths (the plan's "already in scope" note was wrong — 3 sites fire before the old read, 2 in the except handler where the local could be unbound). `dff7c61` extracted `fal_aspect_ratio` (killed a duplicated orientation ternary). |
| T4 | `6a05c42` + `c3e90fe` | max-tier `quality_max.py`: `_inject_aspect(workflow, aspect_ratio)` transposes node-102 (1024×576→576×1024) + node-950 ImageScale (3840×2160→2160×3840), reading each node's current dims (robust to template drift). Called ONCE after `_inject_post_passes`, BEFORE the best-of-N `copy.deepcopy` fan-out, so both per-candidate + boosted-retry submits inherit portrait dims. `c3e90fe` dropped a `_gps` import alias + strengthened the ordering test. |
| final-review | `cf75e24` | cross-cutting review MINORs: consolidated a triple `get_project_setting` import in `generate_ai_broll_max` to one function-scope import; commented the ControlNet node-400 `resolution: 1344` as an aspect-independent non-site. |
| docs | `a0480f5` | ARCHITECTURE.md §8.2/§8.3 Phase-2 portrait note (anchors verified via `check_doc_claims.py`: no drift). |

**Architecture principle held throughout:** ALL aspect geometry lives in
`cinema/aspect.py` (`portrait_swap` / `fal_image_size` / `fal_aspect_ratio`,
all bottoming out in `is_portrait` → `resolve_output_dimensions`, None-safe,
default 16:9). No generation path reimplements orientation.

**Reviews:** every task got spec + code-quality review; the director final
cross-cutting review returned **ready-to-merge** (the two MINORs above folded).

## 2. The merge (user-directed)

- User said **"merge"**, overriding the prior session-turn "hold for operator
  Lane V" (user-tier > the hold). Pre-merge gate re-run at HEAD (1818/0 + smoke
  OK + gate closed). Clean FF (`git merge-base --is-ancestor main HEAD` ✓).
- `git push origin a0480f5:main` (c28f9e6→a0480f5) + `git push origin
  a0480f5:feat/max-tier-provisioning` (5c81ebd→a0480f5). **No checkout** (D-a:
  peer active on the shared tree).
- The merged arc also carries the operator's earlier T-E + deferred-minors batch
  (all were on the same local feat line).

## 3. ⚠️ OPEN — operator's coalesced CC-1 Lane V on Phase-2 was IN FLIGHT at merge

This is the #1 thing for the next director to watch.

- The operator's independent coalesced Lane V (Rule #9 second opinion) over the
  Phase-2 range had **not reported** when the user directed the merge. It is
  **still valid** — it reviews the Phase-2 commits by SHA
  (`3902ed4..c3e90fe -- cinema/aspect.py phase_c_assembly.py quality_max.py +3 tests`),
  all now reachable from main.
- **Disposition when it lands:** process per Rule #8; close any finding via a
  **Rule #15 standalone `fix:` on main** (option (a) fold-in is foreclosed by the
  merge). The work is **provably inert in production** regardless — the gate stays
  `["16:9"]`, so every portrait site is a 16:9 no-op until Phase 3. So even a
  post-merge CRITICAL is a correctness fix for the dormant 9:16 path, NOT a
  production incident.
- Operator was notified of the merge + this disposition path at
  `coordination/mailbox/sent/2026-06-08T03-49-03Z-director-to-operator-coordination.md`.

## 4. #1 PICKUP + carry-forwards

**#1 PICKUP — Phase 3 (own-spec-later):** per-provider native 9:16 **video** +
un-gate `SUPPORTED_ASPECT_RATIOS` (append `"9:16"`). Phase 2 was the prerequisite
(image keyframes); Phase 3 is the video half + flipping the gate. The portrait
spec §7-D provider matrix **UNDER-counts** — a Rule#17 survey is worth running
before speccing:
- **Veo** — native-9:16 capable today (only one).
- **Runway** — 2 sites `phase_c_ffmpeg.py:363` / `:682` (unnamed in the matrix).
- **Seedance** — `phase_c_ffmpeg.py:718` (unnamed).
- **Kling** — no aspect param.
- **Sora / LTX / Hedra** — unverified.

**Other carry-forwards (tracked, not blocking):**
- **On-pod 9:16 latent validation** (manual, GPU-up): generate one production +
  one max keyframe with `aspect_ratio="9:16"` via a dev harness (gate still
  closed) and confirm true portrait pixels / photoreal / no squish. The unit
  tests prove the *plumbing*; only the pod proves the latents *look right*.
- **F5** `visual_findings` FE render.
- **Rule#18** `chief_director.py` MANUAL/digests anchor sweep (~30 anchors).

## 5. Coordination state + D-a discipline (for the next seat)

- **Cursor:** director `2026-06-08T03:03:02Z`, 0 unread. Last processed event =
  operator T-E verification-report (✅ 1813/0, self-closed; nothing owed).
- **Presence:** `coordination/presence/director.md` (gitignored, local) reflects
  merged state. Set `status: wrapping` at session end.
- **Local feat ahead of origin:** after this handoff commit, local feat will be
  ~2-3 ahead of `origin/feat` (a0480f5) = coordination + this doc. Push to sync
  with `git push origin <tip>:feat/max-tier-provisioning` (no checkout).
- 🔑 **D-a discipline:** shared working tree; per-seat `GIT_INDEX_FILE`. ALWAYS
  `git commit -- <pathspec>` (bare `git commit` sweeps the peer's staged work).
  FF-merge = `git push origin <verified-sha>:main` (NEVER `checkout main` while
  peer active). Run pytest with `env -u GIT_INDEX_FILE .venv/bin/python -m pytest`
  (the export breaks temp-git-repo tests). If `git status` shows a phantom
  mass-deletion, your per-seat index is stale vs a peer commit — the v5.8 hook
  auto-refreshes on peer-commit staleness; `git read-tree -m HEAD` only for the
  mixed staged-work+peer-commit case.

## 6. Key facts / gotchas surfaced this session

- **Plan-vs-source divergence (T3):** "aspect_ratio already in scope" was false —
  trace real control flow (6 call sites, early-returns + except). The two-stage
  review reads the *actual diff against the actual file*, which is how this was
  caught at dispatch-design time.
- **Reviewer false-positive (T4 final review):** reviewer recommended dropping the
  function-top import (line 739) to fix a "duplicate import" — that would
  `UnboundLocalError` the aspect read at 740 (runs before the conditional
  re-imports). Correct fix was the inverse: keep 739, drop the redundant
  conditional re-imports. Verify reviewer claims against control flow before
  acting (CLAUDE.md false-positive discipline).
- **`get_project_setting` is None-safe** (`cinema/context.py:151`: `ctx is None
  → default`) — that's why ctx-less keyframe paths default to landscape cleanly.
- **Gate-closed = provably-inert merge:** the whole Phase-2 risk surface with the
  gate closed is the risk of a no-op. That's what let the merge ship before the
  operator's Lane V.
