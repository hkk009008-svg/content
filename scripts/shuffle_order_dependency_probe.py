#!/usr/bin/env python
"""Seeded file-order shuffle over the sys.modules stub family + the blamed file.

Usage: shuffle2.py <n_seeds> [--order-only SEED]
"""
import os, random, subprocess, sys, glob

ROOT = "/Users/hyungkoookkim/Content"
os.chdir(ROOT)

fam = sorted(
    p for p in glob.glob("tests/unit/*.py")
    if "sys.modules[" in open(p, encoding="utf-8", errors="ignore").read()
)
if "tests/unit/test_ltx_native.py" not in fam:
    fam.append("tests/unit/test_ltx_native.py")

env = dict(os.environ); env.pop("GIT_INDEX_FILE", None)

if len(sys.argv) > 2 and sys.argv[1] == "--order-only":
    files = list(fam); random.seed(int(sys.argv[2])); random.shuffle(files)
    print(" ".join(files)); raise SystemExit(0)

n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
fails = []
for seed in range(1, n + 1):
    files = list(fam); random.seed(seed); random.shuffle(files)
    r = subprocess.run([".venv/bin/python", "-m", "pytest", "-q", *files],
                       capture_output=True, text=True, env=env)
    out = r.stdout
    bad = [l for l in out.splitlines() if l.startswith(("FAILED", "ERROR"))]
    if r.returncode == 0:
        print(f"seed {seed}: PASS")
    else:
        print(f"seed {seed}: FAIL  {bad[0][:100] if bad else '(no FAILED line)'}")
        fails.append(seed)
print("─" * 30)
print(f"{len(fails)}/{n} orders FAILED  {fails}")
raise SystemExit(len(fails))
