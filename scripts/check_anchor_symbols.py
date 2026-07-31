#!/usr/bin/env python
"""Verify `<file>.py:<N>` anchors in a doc actually land on something meaningful.

Heuristic, deliberately conservative: an anchor is reported STALE only when the
target line is blank//a bare comment/a closing bracket, or when the doc's own
adjacent backticked symbol is NOT found within +/- WINDOW lines of the target.
Everything else is reported OK, so this UNDER-reports rather than crying wolf.
"""
import re
import sys
import os

ROOT = "/Users/hyungkoookkim/Content"
WINDOW = 6

doc = sys.argv[1]
only = sys.argv[2] if len(sys.argv) > 2 else None

text = open(os.path.join(ROOT, doc), encoding="utf-8").read()
lines = text.splitlines()

# `symbol` ... (`path.py:123`)   or   (`path.py:123`) after a backticked symbol
ANCHOR = re.compile(r"`([A-Za-z0-9_./-]+\.py):(\d+)(?:[-–]\d+)?`")
SYM = re.compile(r"`([A-Za-z_][A-Za-z0-9_.]*)`")
# Lines that ARE a definition: a route decorator, a def/class, or a module-level
# binding. An anchor pointing at one of these is right regardless of which
# symbol the doc sentence happens to name first.
DEF_SITE = re.compile(
    r"^(@\w+[\w.]*\.route\b|@app\.\w+\b|def |async def |class |[A-Za-z_]\w*\s*(:[^=]+)?=)"
)

cache = {}


def src(path):
    if path not in cache:
        p = os.path.join(ROOT, path)
        cache[path] = open(p, encoding="utf-8").read().splitlines() if os.path.exists(p) else None
    return cache[path]


stale, ok, missing = [], 0, []
for i, line in enumerate(lines, 1):
    for m in ANCHOR.finditer(line):
        path, n = m.group(1), int(m.group(2))
        if only and only not in path:
            continue
        s = src(path)
        if s is None:
            missing.append((i, path, n, "FILE MISSING"))
            continue
        if n < 1 or n > len(s):
            stale.append((i, path, n, f"out of bounds (file has {len(s)})"))
            continue
        target = s[n - 1].strip()
        # A DEFINITION SITE is correct by construction — accept without the
        # symbol-proximity check. Without this, a doc line that carries several
        # symbols and several anchors (a table row naming a helper AND the
        # endpoint that calls it) reports every one of its anchors as suspect,
        # because each anchor gets tested against the LINE's symbols rather than
        # its own. That produced 9 false positives on PROGRAM-MANUAL.md, all
        # landing squarely on the right @app.route.
        if DEF_SITE.match(target):
            ok += 1
            continue
        # symbols mentioned on the doc line, nearest-before this anchor
        syms = [x.group(1) for x in SYM.finditer(line[: m.start()])]
        syms = [x for x in syms if not x.endswith(".py")][-3:]
        lo, hi = max(0, n - 1 - WINDOW), min(len(s), n + WINDOW)
        window = "\n".join(s[lo:hi])
        if syms and not any(x.split(".")[-1] in window for x in syms):
            stale.append((i, path, n, f"none of {syms} within +/-{WINDOW}; line={target[:60]!r}"))
        elif not target or target.startswith("#") or target in (")", "]", "}", '"""'):
            stale.append((i, path, n, f"lands on filler: {target[:50]!r}"))
        else:
            ok += 1

print(f"{doc}: {ok} OK, {len(stale)} suspect, {len(missing)} missing-file")
for row in stale:
    print(f"  doc:{row[0]:<6} {row[1]}:{row[2]:<6} {row[3]}")
for row in missing:
    print(f"  doc:{row[0]:<6} {row[1]}:{row[2]:<6} {row[3]}")
