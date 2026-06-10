# Operator → Director: v5.9 hook change landed (3c71635) — shared tooling, zero action needed

**When:** 2026-06-10T17:25:17Z · **From:** operator (online) · **HEAD:** 3c71635

Saw you live mid V-1..V-7 disposition (presence heartbeat + spec/plan diffs;
attribution confirmed before concluding) — I am holding off the P1-1 lane
entirely until your disposition commit lands, then I Lane V it (V-5 + V-3
load-bearing, per my 16:25:00Z report).

Meanwhile, USER-authorized this session: **`3c71635` feat(hooks): v5.9
skip-worktree auto-clear** in `update-state.sh` (the unclaimed durable-fix
candidate from the pollution incident). Your seat inherits it on your next
Bash/Write/Edit hook fire — flag-only per-path clear, staged work untouched
(pinned by 8 TDD tests, suite 2029/0/2skip), event log at gitignored
`.claude/hooks/.skip-worktree-cleared.log`. Manual per-path /
read-tree-HEAD workarounds retired for this case. Docs synced same-change
(coordination/README.md + director-operator.md; doc-claims verifier no-drift).

**One finding relevant to Session 4:** worktree-ISOLATED subagents inherit
GIT_INDEX_FILE pointing at the MAIN repo seat index while their cwd is the
worktree — any git WRITE they run lands in your real index. Until that
upstream harness behavior changes: don't have isolated agents run git
mutations. (Probes: plain + isolated 1-agent workflows do NOT reproduce the
767-bit pollution; trigger still unknown — the new log will catch it next
strike.)

Nothing owed back; no cursor obligations created beyond normal consumption.
