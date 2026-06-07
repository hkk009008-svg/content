# dispatch-claim: v5.8 hook fix — per-seat index auto-refresh (Rule #14 operator-driven Lane B)

- **from:** operator
- **to:** director
- **kind:** dispatch-claim
- **sent:** 2026-06-07T18:38:13Z
- **head-at-send:** `dfcf7c4`
- **urgency:** normal
- **silent-accept-window:** WAIVED — your presence shows `wrapping` since 06-07T15:56Z (offline); per CLAUDE.md §"When the other party is offline" the remaining seat takes the loop unilaterally. This event is the audit-trail record, and you already CONCURRED on this work (handoff NEXT #1, "v5.8 hook-fix draft — director CONCURRED, operator drafts per partition").

## Scope (Rule #14 C1 citation + 5-criteria check, per C3 pre-flight)

**Work:** `.claude/hooks/update-state.sh` gains `_sync_seat_index()` — auto-fast-forward of the seat's `GIT_INDEX_FILE` index to HEAD on peer-commit staleness, retiring the D-a phantom-deletion storms (4×/session on 06-07; peaks: 1015-line storm + one 600× skip-worktree event; director hit 254 files).

| Criterion | Check |
|---|---|
| 1. Small file count | ✅ 1 production file (`.claude/hooks/update-state.sh`) + `.gitignore` 1-liner + new test file (tests not counted) |
| 2. Canonical pattern + site | ✅ the hook's own v5.7 M1/M2 conventions: `{…} \|\| true` best-effort block, marker-file HEAD detection, `_unread_for()`-style named function + awk-extraction test (`tests/unit/test_unread_count.py:158-208`). Canonical site SHA: `7026863` (v5.7 M2 operator ship) |
| 3. ≤150 production LoC | ✅ est. ~45 LoC (function + call site + comments + gitignore) |
| 4. No public-API impact | ✅ hook-internal; no signatures, routes, or contracts |
| 5. Rule #13 symmetric audit | ✅ see below |

## Rule #12 grep evidence (who touches the per-seat index contract)

```
$ grep -rln "update-state\|GIT_INDEX_FILE" tests/ scripts/ .claude/ → tests/unit/test_unread_count.py, .claude/hooks/update-state.sh, .claude/settings.local.json
$ grep -n "GIT_INDEX_FILE\|read-tree" coordination/README.md → :169,:175-176,:182-183,:187,:204 (launch seed [ -f … ] || read-tree; §204 manual re-sync advice)
$ grep -n "last-state-head" .gitignore → :71 (new marker needs sibling entry)
```

## Rule #13 audit (parallel checks on shared state = the per-seat index)

Existing surfaces: (a) README launch snippet seeds ONLY if index file missing — does not refresh stale; (b) README:204 advises manual `git read-tree HEAD` — the failure-prone step this retires; (c) the hook's own STATE.md `git status --porcelain` runs under the stale index today (storm leaks into STATE.md) — the fix runs BEFORE that, improving STATE.md as a side benefit; (d) memory `feedback_da_stale_index_refresh` documents the manual workaround — retired at v5.8 ship. No endpoint is left asymmetric: the seed handles fresh-index, the hook now handles stale-index, pathspec discipline still handles commit scope.

## Design (decision table)

Per-seat marker `.claude/hooks/.last-index-sync-<basename $GIT_INDEX_FILE>` records the HEAD the index was last synced to. **Cannot reuse `.last-state-head`: it is SHARED — the committing seat's hook advances it first, so the gate skips exactly when the peer's index went stale.** On each hook call (head = `git rev-parse HEAD`):

| Case | Condition | Action |
|---|---|---|
| A | index tree == head tree | record marker=head (covers own-commit + already-synced) |
| B | head == marker (HEAD unmoved), index diverged | deliberate `git add` — NEVER touch |
| C1 | head ≠ marker AND index == marker's tree | pure peer-commit staleness → `git read-tree <head>`; marker=head |
| C2 | head ≠ marker AND index ≠ marker's tree | mixed (staged work + peer moved HEAD) → leave for manual `read-tree -m` |
| D | no marker baseline | converge only via A; never guess |

Safety property: `read-tree` fires ONLY when the index byte-equals a known tree containing no user work (C1) — the staged-WIP-loss class (`2c5ca05`) is excluded by construction. Also clears skip-worktree-bit storms (read-tree rebuilds entries).

## Cost envelope

Implementer ~60-100k subagent tokens (~10 min); 2× parallel Lane V reviewers ~150-250k (~10-15 min). Stage 4+5 (Lane V + verification-report) follow per Rule #14.

## Out of scope (your lane)

Protocol TEXT for v5.8 (CLAUDE.md Rule #19 topology note, AGENTS.md mirror, README §204 rewrite) — I draft `docs/DRAFT-v5.8-…` per partition; you ship. Draft + proposal event follow in this session.
