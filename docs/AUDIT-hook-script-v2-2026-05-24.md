# Hook Script Audit — v2.1 baseline

**Baseline:** v2 §A specification (`416d610` / [docs/PROPOSAL-protocol-bundle-v2-2026-05-24.md](PROPOSAL-protocol-bundle-v2-2026-05-24.md) §A)
+ v2.1 modifications (`5e0329d` / `chore(protocol): Protocol Bundle v2.1 — pytest regex fix + stale-by-one doc`).

**Reconciles against:** `.claude/hooks/update-state.sh` at the bundle ship commit (see footer for actual SHA after this ship lands).

**Auditor:** Director session, 2026-05-25 (Protocol Bundle v3 §H deliverable).

**Purpose:** One-time spec-compliance audit per v3 §H. Identifies divergences between the actual hook behavior and the v2 §A as amended by v2.1, plus failure modes not addressed by either baseline.

---

## TL;DR (60 seconds)

| Result | Count | Notes |
|---|---|---|
| **PASS** | 9 / 9 | All v2 §A acceptance criteria met under the v2.1-amended baseline |
| **Divergences (additions)** | 1 | Marker-file mechanism (`.claude/hooks/.last-state-head`) — added at v2 ship time, never went through REPLY review |
| **Mystery resolution** | 1 | Operator's "STATE.md is now SHA-accurate" observation is INCORRECT; my v2.1 stale-by-one doc is right. The hook DOES leave STATE.md one-SHA stale (verified by reading lines 42, 55, 104-115, 122 of the script) |
| **Failure modes not addressed** | 5 | All low-priority; recommended as deferred v3.x patches (none block v3 ship) |

**Bottom-line:** The hook is spec-compliant under the v2.1-amended baseline. The marker mechanism is a justifiable refinement that should be retroactively documented. The "SHA-accurate" claim in v3 proposal §H is wrong and worth correcting in this audit doc.

---

## Acceptance criteria — point-by-point

### 1. Reads HEAD SHA, branch ahead/behind, working tree state ✓ PASS

| Line | Code | Verdict |
|---|---|---|
| 42 | `CURRENT=$(git rev-parse HEAD 2>/dev/null || exit 0)` | ✅ HEAD SHA |
| 55 | `HEAD_SHA="$CURRENT"` | ✅ Stored at write-time |
| 56 | `HEAD_SUBJECT=$(git log -1 --format='%s' HEAD)` | ✅ Commit subject |
| 57 | `BRANCH=$(git rev-parse --abbrev-ref HEAD)` | ✅ Branch name |
| 58 | `AHEAD=$(git rev-list --count "origin/${BRANCH}..HEAD" ...)` | ✅ Ahead count |
| 59 | `BEHIND=$(git rev-list --count "HEAD..origin/${BRANCH}" ...)` | ✅ Behind count |
| 61-66 | `git status --porcelain` + truncation logic | ✅ Working tree, first 5 modified files |

### 2. Extracts smoke from latest commit body (per R1) ✓ PASS

Lines 72-79. Greps for `ci_smoke.py` with -A1 context, classifies as OK / FAIL / unknown. Matches v2.1's R1 spec exactly.

### 3. Extracts pytest from latest commit body (per v2.1 regex fix) ✓ PASS

Line 87 regex: `[0-9]+ passed, [0-9]+ skipped(, [0-9]+ failed)?`. The `(, [0-9]+ failed)?` group is the v2.1 fix (originally REPLY R1, then this commit's regex broadened to make `, Z failed` optional). Inline comment block at lines 81-86 documents the fix history.

### 4. Counts unread mailbox events for each role ✓ PASS

Lines 91-100. Two `find ... -newer ...seen/{role}.txt` calls produce per-role counts. Defaults to 0 if `seen/{role}.txt` is missing (defensive). The `coordination/mailbox/sent` directory check at line 93 is the outer guard.

### 5. Writes STATE.md atomically with --amend --no-edit ✓ PASS (with caveat)

Lines 104-115 (write) + 121-122 (stage + amend). The amend itself is atomic in the git sense — no separate commit appears in `git log`, the STATE.md becomes part of the just-made commit.

**Caveat (low-severity):** The `cat > STATE.md` write itself is NOT atomic — a crash between truncate and write would leave STATE.md empty. Real-world risk is small (hook is fast), but a tempfile-and-rename approach would be safer. Recommended as a v3.x patch.

### 6. Skips if STATE.md already in staged set (loop prevention) ✓ PASS

Lines 50-53. `git diff --cached --name-only | grep -qx 'STATE.md'` → `exit 0`. Combined with the marker check above (lines 41-48), the hook has TWO independent loop-prevention mechanisms. The marker is the primary; the staged check is a defensive secondary.

### 7. Documents --amend SHA-change cost (per v2.1 KNOWN LIMITATION block) ✓ PASS

Lines 12-16 document the SHA-change cost per REPLY C2. Lines 18-28 document the v2.1 KNOWN LIMITATION (stale-by-one) per REPLY R-H1 context. Both blocks are in the header comment as required.

### 8. Uses git add STATE.md not git add . (per v2.1 inline comment) ✓ PASS

Lines 117-121 are the C4 inline comment block explaining the deliberate single-file stage. Line 121 is the explicit `git add STATE.md`. Compliant.

### 9. Tolerates missing origin/main (fresh clone, detached HEAD) ✓ PASS

| Line | Tolerance | Verdict |
|---|---|---|
| 39 | `cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0` | ✅ Silent exit if no git repo |
| 42 | `git rev-parse HEAD 2>/dev/null || exit 0` | ✅ Silent exit if detached HEAD or no HEAD |
| 58-59 | `2>/dev/null || echo "?"` | ✅ Fallback to "?" for missing remote tracking |

---

## Divergences from spec

### D1 — Marker-file mechanism (`.claude/hooks/.last-state-head`)

**Not in v2 §A.** Added during v2 ship (lines 41-48 + 124-126). Rationale documented in lines 30-35: Claude Code's PostToolUse:Bash matcher fires on EVERY Bash tool call, not just git commits. Without the marker, the hook would attempt to regenerate STATE.md + amend on every Bash call, even when no new commit landed. The marker holds the post-amend HEAD SHA; subsequent hook invocations match against the marker and exit early.

**Audit verdict:** Justifiable addition. The mechanism is correct (no infinite amend loops observed in cycle-3 + cycle-4 testing). The omission from v2 §A spec is a documentation gap, not a behavioral defect.

**Recommendation:** Retroactively add to v2.1 documentation or as a v3.x patch — note the marker mechanism in the hook spec so future maintainers don't see it as undocumented magic.

### D2 — "STATE.md is SHA-accurate" claim in v3 proposal §H is WRONG

The v3 proposal §H §Problem block states:
> "the 'stale-by-one' issue I assumed in earlier analysis turned out NOT to be the actual behavior — STATE.md is now SHA-accurate"

**This is incorrect.** Reading the script:
- Line 42: `CURRENT=$(git rev-parse HEAD)` captures pre-amend HEAD
- Line 55: `HEAD_SHA="$CURRENT"` (= pre-amend SHA)
- Lines 104-115: STATE.md is written with `${HEAD_SHA}` (= pre-amend SHA)
- Line 122: `git commit --amend --no-edit --no-verify` creates a NEW SHA
- After amend: actual HEAD ≠ HEAD_SHA in STATE.md by exactly one amend.

STATE.md IS stale by one SHA, exactly as my v2.1 chore commit (`5e0329d`) documented and as the hook's KNOWN LIMITATION block (lines 18-28) explicitly says. The operator's observation in v3 §H is incorrect, likely caused by observing STATE.md after a second hook invocation that re-amended (which would leave STATE.md referencing the SHA from one amend ago — coincidentally close to current HEAD if amends are frequent).

**Audit verdict:** Confirmed: stale-by-one is the actual behavior. Operator's "SHA-accurate" observation was a misread. No code change needed; v3 proposal §H's framing should be corrected in a future revision.

---

## Failure modes not addressed (recommended deferred patches)

### F1 — Non-atomic STATE.md write (low severity)

Line 104: `cat > STATE.md <<EOF` truncates STATE.md before writing. A crash between truncate and write leaves an empty or partial STATE.md. Real-world risk is small (hook is sub-second) but a tempfile-and-rename approach would close the window:

```bash
tmpfile=$(mktemp -p . .state.md.XXXX)
cat > "$tmpfile" <<EOF
...
EOF
mv -f "$tmpfile" STATE.md
```

**Severity:** LOW. Recommended as a v3.x patch.

### F2 — Shell-metachar injection in commit subjects (low severity)

Line 56: `HEAD_SUBJECT=$(git log -1 --format='%s' HEAD)` captures the commit subject. Lines 105-115 use it inside an unquoted heredoc with `${HEAD_SUBJECT}` substitution. If a commit subject contains backticks or `$()` (a malicious or accidental subject like `` `whoami` ``), they could execute as commands.

**Severity:** LOW. Realistic exploitation requires control over a commit subject + bash escape characters. Defense: use a quoted heredoc (`<<'EOF'`) and substitute via sed/awk, OR escape `${HEAD_SUBJECT}` via parameter expansion.

**Recommendation:** Patch in v3.x. Sample fix:

```bash
HEAD_SUBJECT=$(git log -1 --format='%s' HEAD | tr -d '`$\\')
```

(Strips backticks, `$`, and backslashes — slightly destructive but safe.)

### F3 — Concurrent hook invocations (low severity)

Two back-to-back Bash tool calls could fire the hook simultaneously. If both pass the marker check (race window ~milliseconds), both would attempt `git add STATE.md` + `git commit --amend`. Git's locking would serialize the amends, but only one's content lands in the final commit; the other's STATE.md content is lost (re-overwritten by the first invocation's amend, or possibly left in working tree if the second's amend lost the race).

**Severity:** LOW. Race window is very small; Claude Code's tool-call serialization makes simultaneous invocations unlikely.

**Recommendation:** Defer. If observed in practice, add a `flock` around the marker check + amend:

```bash
exec 9>".claude/hooks/.update-state.lock"
flock 9
# ... rest of script ...
```

### F4 — Marker corruption / missing gitignore entry (low severity)

The marker file at `.claude/hooks/.last-state-head` is gitignored (`.gitignore` line "Claude subagent worktrees... + .claude/hooks/.last-state-head" added in v2 ship). If the gitignore entry is accidentally removed or the marker becomes corrupted (binary garbage), the LAST != CURRENT comparison would treat the marker as a different SHA and re-amend. Not catastrophic but wasteful.

**Severity:** LOW. Defensive parsing in line 43 (`|| echo ""`) handles missing marker; corrupted marker would behave like missing.

**Recommendation:** No patch needed; current behavior is acceptable.

### F5 — Non-bash hook origin (informational)

If something else changes HEAD outside Claude Code (e.g., user runs `git commit --amend` in their terminal), the marker becomes stale relative to the new HEAD. Next Bash tool call → hook fires → marker ≠ CURRENT → hook regenerates STATE.md + amends. This is CORRECT behavior, just adds one useless-feeling amend.

**Severity:** N/A (correct behavior, not a failure).

---

## Recommendations summary

| ID | Patch | Severity | Defer? |
|---|---|---|---|
| F1 | Atomic STATE.md write via tempfile + mv | LOW | Defer to v3.x |
| F2 | Escape HEAD_SUBJECT to prevent shell-metachar injection | LOW | Defer to v3.x; recommended within 1-2 cycles |
| F3 | flock around critical section | LOW | Defer indefinitely; patch if observed |
| F4 | Marker corruption detection | LOW | No patch needed |
| F5 | Non-bash HEAD changes | N/A | Behavior is correct as-is |
| D2 | Correct the "SHA-accurate" framing in v3 proposal | docs-only | Patch in v3.x revision of the proposal doc |

**Net conclusion:** The hook is production-ready under the v2.1-amended baseline. All 9 acceptance criteria pass. One legitimate divergence (D1, the marker mechanism) is well-implemented and should be retroactively documented. One factual error in v3 proposal §H (D2, the "SHA-accurate" claim) is worth correcting but doesn't change the audit's pass verdict. Five low-severity failure modes (F1-F5) are deferred patches; none block v3 ship.

---

## What this audit didn't cover

- **Bash script style / linting** (per locked Decision #3: "spec compliance only, not bikeshedding the bash"). The script could be cleaner in places (e.g., consistent quoting, exit-code propagation through pipes), but those are stylistic concerns, not behavioral.
- **Hook performance under load.** Not measured; assumed acceptable based on observed sub-second execution time during cycles 3-4.
- **STATE.md schema evolution.** The current 7-field schema is stable for v2/v2.1/v3; future schema changes would require their own audit pass.

---

*Verified at HEAD `ec1e64e` (operator's v3 revision) with the hook script in tree (no in-flight modifications). Audit doc itself ships in the v3 bundle commit.*
