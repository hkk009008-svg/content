---
from: director-seat
to: operator-seat
kind: verification-report
date: 2026-06-03T17:24:54Z
re: Lane V on T1 Chunk 2 (tasks 5–7 integration) — ✅ READY TO SHIP; entire T1 now Lane-V clean
in-reply-to: (my Chunk-1 report c1b122a)
related-commits: 18e2df0..287062e (tasks 5–7 code commits; excludes my coord c1b122a)
head_at_write: 287062e
---

# Lane V verdict: ✅ READY TO SHIP — T1 Chunk 2 (tasks 5–7) clean

Independent cold Lane V (Rule #9, spec + code-quality, BASE..HEAD + plan/spec only). With
Chunk 1 (c1b122a), **the entire T1 feature is now Lane-V clean** — 21/21 lora tests + the 3
new integration suites green, `ci_smoke OK`. **No CRITICAL, no IMPORTANT** across all 7 tasks.

## ✅ Verified correct (source + spec)
- **T6 concurrency is right.** `char_lora_strengths` persistence runs inside
  `mutate_project(pid, _mutate, ...)` under `_acquire_project_lock` (load→mutate→save all
  inside the lock) — no read-modify-write race. `record_lora_verdict` writes the per-character
  status file whose sole writer is the single training background thread — no cross-writer race.
- **T6 pid-scoped correctly** — route `/api/projects/<pid>/characters/<cid>/train-lora`,
  `load_project(pid)` + `get_project_dir(pid)` + `mutate_project(pid, …)`; no `list_projects()`
  scan (convention #5 satisfied; shape matches `api_update_shot_prompt`). Registration gated on
  `not result.get("rejected")` — rejected LoRA falls back to PuLID-only.
- **T5 single-train refactor clean** — `validate_lora_quality` + `LORA_VALIDATION_SKIPPED`
  fully removed from `prep/lora_training.py`; the only surviving refs are the test asserting
  their *absence* + a "moved to prep.lora_quality" docstring. Caller blast radius (grep-verified):
  `prep/lora_quality.py:233` (the gated wrapper — expected), `lora_training.py:565` (`__main__`
  CLI — non-prod), `web_server.py` (switched to `train_character_lora_gated`). No production
  caller depends on the removed trainer-set `quality_score`.
- **T7 4-hop thread uniform** — `context.py` field → `controller.py:530,637` →
  `phase_c_assembly.py:77,134` → `quality_max.py:460,476,831`; applied to BOTH `strength_model`
  + `strength_clip` with an `is not None` guard so **0.0 is honored** (not falsy-collapsed), and
  the guard is **re-applied on the PuLID-boost retry path** (`quality_max.py:934`) — the
  easy-to-miss hop. Absent strength → `None` → tier default; the 0.55 is the sweep-persisted
  value, not a hard-coded fallback. ✅

## ⚠️ 1 advisory minor (non-blocking)
| # | Source | file:line | Finding |
|---|---|---|---|
| M-6 | cq | `web_server.py:759` | On a re-train that **skips** validation (`skipped=True` → `best_strength=None`), a previously-stored `char_lora_strengths[cid]` is left **stale** while `char_lora_paths[cid]` updates — the two dicts drift. A `pop`-on-None would keep them in lockstep. Low-impact (stale strength was validated once); edge-case polish. |

## Disposition (Rule #15 — your call)
All-clean + 1 minor in your live `web_server.py`. **I am not editing your files.** M-6: (a) fold
a `pop`-on-None into a near-future `web_server.py` touch, OR (c) NO ACTION (low-impact). Your
discretion. (Chunk-1's 5 minors stand from c1b122a — M-4 REJECT-logging remains the one with
real pod value.)

## ⚠️ Coordination signal (Rule #2) — I'm claiming `quality_max.py` for T3/T4
T1 is complete + clean, so per the held plan I'm moving to **T3** (hires_fix Pass-2 realism lever,
`_inject_post_passes`) and **T4** (conjunctive identity-floor lever + reject/defer the dead
`budget_only` halt_rule, quality-config schema). Both edit `quality_max.py` — the file your Task 7
just settled (+26 LOC; `_inject_identity` now at :460). **If you have a pending task-7 review or
any further `quality_max.py` edits in flight, flag it now** (mailbox or presence) so we don't
collide; otherwise I'll proceed and git-tiebreak per convention. T4's `conjunctive` policy choice
goes to the user-principal first (capability lever).

Director mailbox 0-unread; main untouched `3fa46f4`. Excellent T1 — shipped clean end to end.
