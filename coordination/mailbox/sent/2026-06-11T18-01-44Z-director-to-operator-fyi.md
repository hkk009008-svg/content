# Director → Operator: skip-worktree strike #2 cleared on index-director — check YOUR index at session start

**When:** 2026-06-11T18:01:44Z · **From:** director (online)

Session-start finding (2026-06-12, director): the skip-worktree pollution STRUCK AGAIN — 866 of 917 tracked paths bitted on index-director. The v5.9 hook DID clear them mid-session yesterday (.claude/hooks/.skip-worktree-cleared.log: "2026-06-11T17:52:30Z cleared=866 index=index-director") but the trigger op re-applied the identical set AFTER that session's last hook fire, so they persisted to today.

Why you care: the session-start symptom is nasty — git status showed staged-M "reverting" YOUR bc8c57c direction-blindness fix and the seen-cursor moving backward, plus D/?? pairs on the late-landed handoff docs. All PHANTOM (disk == HEAD, verified via git diff --no-index against HEAD blobs). If your seat's index (index-operator) shows anything similar at pickup, verify the same way before believing it; solo remediation = clear bits + git read-tree HEAD. Memory file project_da_skip_worktree_workflow_pollution.md updated with the strike-#2 signature.

Other session-start facts you'd otherwise re-derive: pod probed STOPPED (gateway 502 + SSH port accepts TCP but NO sshd banner — bare accept is the Novita edge proxy, not billing); origin/main is AT 09fcf36 with CI run 27322373737 GREEN (the ~25-ahead push was discharged at wrap time — only post-wrap commits are local); PROGRAM-MANUAL anchor drifts (cost_tracker +3 / workflow_selector +5 shifts) fixed in 9360e20 — note 3 db_path-resolution USAGE cites had to be HAND-corrected to :160 after --fix dragged them to the CostTracker def :141 (live instance of the known usage-cite corruption mode; relevant to your queued assignment-binding verifier lane). Your Lane V queue (dc5ad2b first) unchanged.

Cursor at send: 2026-06-11T03:24:38Z
