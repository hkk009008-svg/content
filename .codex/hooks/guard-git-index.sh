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
    data = json.loads(payload)
except Exception:
    sys.exit(0)  # fail-open on malformed JSON

# Robust extraction: any unexpected shape (non-dict payload, non-dict
# tool_input, non-string command) -> fail-open, never crash/exit-nonzero.
cmd = ""
if isinstance(data, dict):
    ti = data.get("tool_input")
    if isinstance(ti, dict):
        cmd = ti.get("command", "")
if not isinstance(cmd, str) or not cmd or "env -u GIT_INDEX_FILE" in cmd:
    sys.exit(0)  # nothing to check / already safe

# Git subcommands that read or write the index (so they care about which index).
MUT = {"add", "commit", "stash", "reset", "rm", "restore", "mv", "read-tree",
       "checkout", "switch", "merge", "rebase", "cherry-pick", "apply", "clean"}

# Scope note: this guard targets the ACCIDENTAL mistake — a seat that forgot the
# `env -u GIT_INDEX_FILE` prefix on a normal `git <mutator>` / `pytest`. It is a
# guardrail, not an anti-evasion sandbox: deliberately obfuscated forms
# (`sh -c 'git commit'`, `git$(echo " ")commit`, `git-commit`) are out of scope —
# the dispatch templates mandate the prefix, and chasing obfuscation in a
# tokenizer only adds false positives. Detection keys off the COMMAND position
# (first token after any VAR=val env assignments), so `git`/`pytest` appearing as
# an ARGUMENT (e.g. `grep 'pytest' tests/`, `grep git add`) is correctly allowed.
def command_segments(c):
    try:
        lex = shlex.shlex(c, posix=True, punctuation_chars=";&|")
        lex.whitespace_split = True
        toks = list(lex)
    except Exception:
        return []

    segments = []
    current = []
    for tok in toks:
        if tok in {";", "|", "||", "&&"}:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(tok)
    if current:
        segments.append(current)
    return segments


def offending_segment(c):
    for toks in command_segments(c):
        if not toks:
            continue
        # command token = first token that is not a `VAR=val` env assignment
        ci = 0
        while ci < len(toks) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[ci]):
            ci += 1
        if ci >= len(toks):
            continue
        cmd0 = toks[ci].split("/")[-1]  # basename of the invoked command
        segment_for_message = " ".join(toks)
        # pytest: `pytest …`, `.venv/bin/pytest …`, or `python[3] -m pytest …`
        if cmd0 == "pytest":
            return segment_for_message
        if cmd0.startswith("python") and any(
            toks[k] == "-m" and k + 1 < len(toks) and toks[k + 1] == "pytest"
            for k in range(ci + 1, len(toks))
        ):
            return segment_for_message
        # git index-mutator: command is git, subcommand (after global flags) in MUT
        if cmd0 == "git":
            j = ci + 1
            while j < len(toks) and toks[j].startswith("-"):
                if toks[j] in ("-C", "-c") and j + 1 < len(toks):
                    j += 2
                else:
                    j += 1
            if j < len(toks) and toks[j] in MUT:
                return segment_for_message
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
