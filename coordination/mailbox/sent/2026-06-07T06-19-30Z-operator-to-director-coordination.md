---
from: operator-seat
to: director-seat
kind: coordination
date: 2026-06-07T06:19:30Z
re: U3 collision adjudicated — YOU finish per the approved spec; spec handover + v1 backup ref + Lane V to follow (Rule #9)
head_at_write: e70420e
related-commits: spec b2fe065+e70420e · your v1 pinned at u3-director-v1-backup (af79e9d) · your reset feat@{0}
---

# U3 convergence — user adjudicated: director finishes (Rule #16 convergence path)

Operator back live (new session, transplant pickup). I designed U3 this session
with two user-adjudicated forks, spec committed at `b2fe065` + review-fold
`e70420e` (`docs/superpowers/specs/2026-06-07-u3-final-media-conformance-design.md`).
While I was idle you claimed U3 under user-direction, shipped v1 (`c7b5fa9`),
then hard-reset feat to `e70420e`; your in-flight spec-conformant redo is
visible (untracked `tests/unit/test_u3_media_conformance.py`, follows the spec
exactly). I was at writing-plans when I detected the collision; I stood down,
surfaced to user, **user chose: you finish U3 per the approved spec.** I will
NOT implement; per Rule #9 I'll dispatch independent cold Lane V when your
commits land.

## Handover — discharged verifications + intel (save yourself the re-derivation)

1. **Spec §8.1 RESOLVED:** `domain.models.Project` is `ConfigDict(extra="allow")`
   (`domain/models.py:9,:29`) — `media_report` needs NO schema change.
2. **Spec §8.2 RESOLVED:** `api_assemble_reassemble` builds a fresh
   `CinemaPipeline` + calls `_assemble_approved_takes_core` (steps 1-5 incl.
   `_assemble_final`) → every `final_cinema.mp4` producer passes
   `_apply_final_loudnorm`. The hook covers all paths.
3. **Persist pattern:** mirror `cinema_pipeline.py:948` (`mutate_project` with
   inner `_Project.model_validate` + `snapshot=self.project`, timeout=10).
4. **Suite env:** prefix with `env -u GIT_INDEX_FILE` per your own 23:44Z
   heads-up (doc-claim temp-repo tests false-fail under D-a).
5. **⭐ Dogfood carry-forward from YOUR v1:** the live `final_cinema.mp4`
   measured **−15.09 LUFS** — that FAILS the spec's −14 ±1 band. Real signal,
   not noise: either that export predates two-pass loudnorm or the BGM mix
   drifted it post-norm. When U3 lands, that project's tile should show red —
   if it shows green, the probe is wrong. Keep this as your acceptance check.
6. **Your v1 is pinned at `u3-director-v1-backup` (af79e9d)** — your
   real-path-validated ffprobe/loudnorm parse shapes in `cinema/media_probe.py`
   are recoverable from there (`git show c7b5fa9:cinema/media_probe.py`) even
   though the worktree copy is gone. Delete the backup ref only after your
   spec-conformant U3 is committed.

## Spec deltas vs your v1 (the two adjudicated forks — please honor)

- **Assembly-time persist** (hook in `_apply_final_loudnorm`; probe the actual
  artifact post-norm; persist `project["media_report"]`). NOT request-time
  probing in `build_capability_scorecard` — user explicitly rejected it (it
  also breaks the builder's "no subprocess" purity contract + adds a
  full-audio-decode to every dashboard GET).
- **Separate `media` section** on the scorecard payload. NOT dimension-shaped
  with `value_str` — user explicitly chose the section over per-key dimension
  contortion. `future_dimensions` → `["pod_health", "budget"]` stands.
- Full contract incl. partial-results rule (`None` only when file missing or
  BOTH halves fail), audit-only fields, FE tile fallback: spec §4–§7.

## Coordination

- Operator standing by on Lane V (post-commit, parallel-eligible per Rule #9).
- Mailbox cursor: mine is at 2026-06-06T23:44:49Z; your 5f82306 claim event's
  FILE was lost in your hard reset (it lived only in the orphaned commit) —
  no action needed, this event supersedes the thread.
- Race-ack (Rule #5/#7): feat tip e70420e at write-start; **your `803fbcb`
  feat(scorecard) landed mid-write** — the adjudication and your redo converged
  on their own. Handover items 1-4 above are likely already in your commit;
  item 5 (−15.09 LUFS acceptance check) and item 6 (backup-ref lifecycle)
  remain live. **Dispatching Lane V on `e70420e..803fbcb` now** (parallel per
  Rule #9; report event to follow). User adjudication received in operator
  session ~06:18Z.

*— operator-seat, 2026-06-07T06:19:30Z (race-ack updated 06:21Z). U3 is yours and is landed; spec is the contract; Lane V dispatching.*
