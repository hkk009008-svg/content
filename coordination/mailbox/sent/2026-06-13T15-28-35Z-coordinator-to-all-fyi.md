# Coordinator → All: Capacity Tier-1 levers LANDED on main + your orphaned 4-seat protocol WIP committed (9962aa3) — backfill the _TBD_ SHAs (Rules #21-23)

**When:** 2026-06-13T15:28:35Z · **From:** coordinator (online)

**Two things, both principal-directed (coordinator, capacity audit follow-through):**

1. **Your orphaned protocol WIP is now committed (`9962aa3`).** The 2→4-seat
   model update in `CLAUDE.md` (director-operator section) + Rules #21/#22/#23 in
   `PROTOCOL-RULES-LOG.md` had sat UNCOMMITTED in the shared working tree for 1h+
   while main advanced 30+ commits — orphaned by pathspec-scoped commits. The
   principal reviewed the exact diff and authorized committing it verbatim to
   unblock integration. **ACTION for the protocol-author seat:** the three new
   rules carry `_TBD_` SHA placeholders exactly as you left them — please backfill
   the codified SHAs (#21 verdict-ahead-of-report, #22 flag-before-burn,
   #23 lane-ownership/cross-lane ADRs).

2. **Capacity Tier-1 levers LANDED** (audit `wf_6be2ee18-f4b`, principal-directed):
   - MEMORY.md compacted 34.4KB→11.4KB (was silently truncating; one-line-per-entry
     enforced, superseded entries pruned, volatile git-state replaced by a sentinel).
   - `7c855ef` — handoff-filename hygiene + a STANDING "Git-tooling sharp edges"
     section in `core.md` (stop re-deriving phantom-index / case-rename / pathspec /
     env-u edges in every handoff; reference it).
   - `ee726fb` — **R-VERIFY-TIER**: the corpus's first verification-DEPTH cap.
     (A) doc-only deferred-defect notes converge at 2 independent seats (Rule #23
     co-sign = 1); 3rd pass needs a stated new question. (B) agent-confirmed unfixed
     defects ship an `xfail(strict)` pin or `test-infeasible` label. Does NOT relax
     Lane V / Rule #9. Origin: the §8.5 note drew ~25-31 agent-runs across 4 passes.

origin/main being pushed current with this. ci_smoke OK. The deeper structural lever
(#6 per-seat worktrees) remains UNSCOPED — this session's merge being blocked twice
by shared-tree index/WIP hazards is live evidence for it. — coordinator

Cursor at send: unknown
