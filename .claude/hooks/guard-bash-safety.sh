#!/usr/bin/env bash
# PreToolUse(Bash) guard: the git-safety rules and measurement-instrument traps
# that this project previously carried only as PROSE.
#
# Why this exists: six `.claude/hookify.*.local.md` rules encoded these same
# guards, but the hookify plugin is disabled and the files are gitignored, so
# they never executed — a guard that cannot run is indistinguishable from no
# guard at all. Separately, a 2026-08-08 session produced four measurement
# faults and ZERO code faults; three were shell idioms with known footguns, and
# writing the lesson into doctrine did not stop the fourth twenty minutes later.
# Instructions govern deliberate judgment; only mechanism reaches a reflex.
#
# Design: FAIL-OPEN, copied from guard-git-index.sh. Any parse problem, missing
# python, or unexpected payload shape exits 0 (allow). It denies (exit 2) only
# on a precise, confident match, so a bug here can never halt work — it can only
# fail to catch a mistake.
#
# Scope note: this targets the ACCIDENTAL mistake, not a determined evader.
# Obfuscated forms (`sh -c '...'`, `git$(echo " ")push`) are out of scope;
# chasing them in a tokenizer only buys false positives.
set -uo pipefail

payload="$(cat)"

PYBIN="python3"
command -v "$PYBIN" >/dev/null 2>&1 || exit 0   # fail-open if no python

exec "$PYBIN" - "$payload" <<'PY'
import sys, json, shlex, re

payload = sys.argv[1] if len(sys.argv) > 1 else ""
try:
    data = json.loads(payload)
except Exception:
    sys.exit(0)  # fail-open on malformed JSON

cmd = ""
if isinstance(data, dict):
    ti = data.get("tool_input")
    if isinstance(ti, dict):
        cmd = ti.get("command", "")
if not isinstance(cmd, str) or not cmd:
    sys.exit(0)


def strip_quoted(s, quotes="'\""):
    """Blank out quoted spans, preserving length so indices stay comparable.

    Two different views are needed, because the shell treats the two quote
    types differently:

    * pipes and separators — blank BOTH quote types. `rg -n 'foo|bar' src/`
      contains no pipeline, and shlex.split keeps the `|` inside its token, so
      a substring check on the reconstructed string still sees one.
    * `$?` — blank only SINGLE quotes. `echo "EXIT=$?"` still expands; only
      `echo 'EXIT=$?'` is literal.
    """
    out = []
    quote = None
    for ch in s:
        if quote:
            out.append(" ")
            if ch == quote:
                quote = None
        elif ch in quotes:
            quote = ch
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def segments(c):
    """Shell segments with their token lists, skipping unparseable ones."""
    out = []
    for part in re.split(r"&&|\|\||;", c):
        try:
            toks = shlex.split(part)
        except Exception:
            continue
        if toks:
            out.append((part.strip(), toks))
    return out


def command_token(toks):
    """First token that is not a VAR=val assignment, as a basename."""
    i = 0
    while i < len(toks) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[i]):
        i += 1
    if i >= len(toks):
        return None, i
    return toks[i].split("/")[-1], i


def git_subcommand(toks, i):
    """Subcommand after any global flags, or None."""
    j = i + 1
    while j < len(toks) and toks[j].startswith("-"):
        if toks[j] in ("-C", "-c") and j + 1 < len(toks):
            j += 2
        else:
            j += 1
    return (toks[j] if j < len(toks) else None), j


def deny(title, detail, fix):
    sys.stderr.write("BLOCKED: %s\n  %s\n  Do instead: %s\n" % (title, detail, fix))
    sys.exit(2)


# --- Git safety (ported from the inert hookify rules) ----------------------
for raw, toks in segments(cmd):
    name, i = command_token(toks)
    if name != "git":
        continue
    sub, j = git_subcommand(toks, i)
    args = toks[j + 1:] if sub else []

    if sub == "push":
        if any(a == "--force" or a == "-f" for a in args):
            deny(
                "force-push",
                "A force-push can overwrite a peer's commits and rewrite published history.",
                "--force-with-lease after confirming remote state with the user, "
                "or ask the user to run it themselves.",
            )
    if sub == "add":
        if any(a in ("-A", "--all", ".") for a in args):
            deny(
                "bulk `git add` (-A / --all / .)",
                "This project stages by name: bulk-adding pollutes a reviewer's "
                "range and can stage a peer's in-flight work or untracked logs/.",
                "git add path/to/file1 path/to/file2",
            )
    if sub in ("commit", "push", "merge", "rebase"):
        if any(a in ("--no-verify", "--no-gpg-sign") for a in args):
            deny(
                "skipping git hooks or signing",
                "A failing pre-commit hook means the commit did NOT happen; "
                "bypassing hides the failure instead of fixing it.",
                "fix the hook failure and make a new commit "
                "(never --amend after a hook failure).",
            )

# --- pytest outside the project venv ---------------------------------------
if ".venv" not in cmd:
    for raw, toks in segments(cmd):
        name, i = command_token(toks)
        if name is None:
            continue
        is_pytest = name == "pytest" or (
            name.startswith("python")
            and any(
                toks[k] == "-m" and k + 1 < len(toks) and toks[k + 1] == "pytest"
                for k in range(i + 1, len(toks))
            )
        )
        if is_pytest:
            deny(
                "pytest outside the project venv",
                "System python lacks this project's test dependencies, so a pass "
                "or a fail here is not evidence about the project.",
                "env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/ -q",
            )

# --- Instrument traps ------------------------------------------------------
# Trap 1: reading $? after a pipeline. `cmd | tail; echo $?` reports TAIL's
# status, so a failing checker reads as a passing one. Observed live: a
# `gen_doc_index.py --check` that printed STALE was recorded as exit 0.
# PIPESTATUS is the deliberate correct form and is always allowed.
if "PIPESTATUS" not in cmd:
    # Separator positions come from the fully-stripped view; `$?` is read from
    # the single-quote-stripped view. Both are the same length as the original,
    # so the same slice boundaries apply to each.
    shell_view = strip_quoted(cmd)
    expand_view = strip_quoted(cmd, quotes="'")
    bounds, pos = [], 0
    for m in re.finditer(r"&&|;", shell_view):
        bounds.append((pos, m.start()))
        pos = m.end()
    bounds.append((pos, len(shell_view)))

    saw_pipe = False
    for start, end in bounds:
        if "$?" in expand_view[start:end] and saw_pipe:
            deny(
                "reading $? after a pipeline",
                "$? is the LAST command's status, not the one you meant to check; "
                "a failing command reads as a passing one.",
                "redirect instead:  cmd > out.txt 2>&1; echo \"EXIT=$?\"   "
                "(or use ${PIPESTATUS[0]})",
            )
        if "|" in shell_view[start:end]:
            saw_pipe = True

# Trap 2: counting processes with a pattern that matches the counting shell
# itself. `ps aux | grep -c pytest` includes its own grep (and any wrapper
# whose command line contains the word), inflating the count. Observed live:
# one pytest run counted as five.
segs = [s.strip() for s in cmd.split("|")] if "|" in strip_quoted(cmd) else []
for prev, cur in zip(segs, segs[1:]):
    try:
        prev_toks = shlex.split(prev)
    except Exception:
        continue
    prev_name, _ = command_token(prev_toks)
    if prev_name != "ps":
        continue
    try:
        cur_toks = shlex.split(cur)
    except Exception:
        continue
    cur_name, ci = command_token(cur_toks)
    if cur_name not in ("grep", "egrep", "fgrep"):
        continue
    flags = [t for t in cur_toks[ci + 1:] if t.startswith("-")]
    if not any("c" in f.lstrip("-") for f in flags):
        continue
    patterns = [t for t in cur_toks[ci + 1:] if not t.startswith("-")]
    if patterns and not any("[" in p for p in patterns):
        p = patterns[0]
        bracketed = "[%s]%s" % (p[:1], p[1:]) if p else "[x]"
        deny(
            "counting processes with a self-matching pattern",
            "`ps | grep -c X` counts its own grep and any wrapper whose command "
            "line contains X, so the count is inflated.",
            "bracket the first character:  ps aux | grep -c '%s'  — or better, "
            "`ps -eo pid,etime,command` and read the real argv." % bracketed,
        )

sys.exit(0)
PY
