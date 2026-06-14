#!/usr/bin/env bash
# PreToolUse(Bash) guard: block git index-mutators / pytest that lack the
# `env -u GIT_INDEX_FILE` prefix WHEN this session inherits a per-seat index.
#
# Why: D-a launched seats run with $GIT_INDEX_FILE pointing at a per-seat git
# index. A bare `git add/commit/...` or `pytest` (temp-repo tests) corrupts it
# under concurrent refreshes ("unable to read <blob>", 2026-06-12). Every
# dispatch template already mandates the prefix; this enforces it mechanically.
#
# Design: FAIL-OPEN. Any parse problem, missing python, or unexpected shape
# exits 0 (allow). It only blocks (exit 2) on a precise, confident match, so a
# bug here can never halt the fleet — it can only fail to catch a mistake.
set -uo pipefail

# Fast path: no per-seat index -> nothing to guard (the main session is here).
[ -z "${GIT_INDEX_FILE:-}" ] && exit 0

payload="$(cat)"

# Hand the decision to python for robust JSON + shell tokenization. This branch
# only runs for seats that actually have a per-seat index, so its startup cost
# is paid rarely.
PYBIN="python3"
command -v "$PYBIN" >/dev/null 2>&1 || exit 0   # fail-open if no python

exec "$PYBIN" - "$payload" <<'PY'
import sys, json, shlex, re

payload = sys.argv[1] if len(sys.argv) > 1 else ""
try:
    cmd = json.loads(payload).get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)  # fail-open

if not cmd or "env -u GIT_INDEX_FILE" in cmd:
    sys.exit(0)  # nothing to check / already safe

# Git subcommands that read or write the index (so they care about which index).
MUT = {"add", "commit", "stash", "reset", "rm", "restore", "mv", "read-tree",
       "checkout", "switch", "merge", "rebase", "cherry-pick", "apply", "clean"}

def offending_segment(c):
    # Check each shell-separated segment of a compound command independently.
    for part in re.split(r"&&|\|\||;|\|", c):
        try:
            toks = shlex.split(part)
        except Exception:
            continue
        if not toks:
            continue
        joined = " ".join(toks)
        # pytest in any form
        if any(t == "pytest" for t in toks) or "-m pytest" in joined:
            return part.strip()
        # git: skip global flags (incl. -C <path> / -c <kv>) to find the subcommand
        if "git" in toks:
            i = toks.index("git")
            j = i + 1
            while j < len(toks) and toks[j].startswith("-"):
                if toks[j] in ("-C", "-c") and j + 1 < len(toks):
                    j += 2
                else:
                    j += 1
            if j < len(toks) and toks[j] in MUT:
                return part.strip()
    return None

bad = offending_segment(cmd)
if bad:
    sys.stderr.write(
        "BLOCKED: $GIT_INDEX_FILE is set but this command lacks "
        "'env -u GIT_INDEX_FILE'.\n"
        "  Offending segment: %s\n"
        "  Seat-index corruption vector (2026-06-12 'unable to read <blob>').\n"
        "  Re-run prefixed:    env -u GIT_INDEX_FILE <your command>\n" % bad
    )
    sys.exit(2)  # PreToolUse: non-zero (esp. 2) blocks the tool and shows stderr
sys.exit(0)
PY
