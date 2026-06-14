# Program Hardening — Phase 0 (Campaign Bootstrap) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the infrastructure that makes the hardening campaign executable — the
remediation inventory, git-native lock tooling, the wave-gate checker, the xfail-pin
seed migration, and the discovery bug-hunt — so that Wave 1 can be planned from a real,
populated defect inventory.

**Architecture:** Implements **Phase 0 + the §6 safety tooling** of
`docs/superpowers/specs/2026-06-14-program-hardening-roadmap-design.md`. The inventory
(`docs/REMEDIATION-INVENTORY.md`) is the single source of truth; git-native lock files
(`coordination/locks/`) prevent cross-cutting collisions without a live coordinator; a
wave-gate checker (`scripts/wave_gate_check.py`) makes wave acceptance mechanically
verifiable; a discovery Workflow populates the inventory with adversarially-verified
defects.

**Tech Stack:** Python 3.9 + pytest (existing test harness, run via `.venv/bin/python -m
pytest`); POSIX shell for `coordination/bin/*` (matches existing `send-event`/`consume-events`);
the Workflow orchestration tool for discovery. No new dependencies.

**Reads (do not skip):** the spec above (esp. §2 inventory schema, §3 discovery, §6b lock
protocol, §6f deputy/SLA, §11 delegated decisions). Mirror existing patterns:
`coordination/bin/send-event` for shell style; `scripts/check_coordination.py` for
script+test style; `scripts/ci_smoke.py` for the smoke gate.

---

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `coordination/locks/.gitkeep` | Create | Make the lock dir tracked (git ignores empty dirs) |
| `coordination/bin/claim-lock` | Create | Git-native lock claim: fetch → check → commit → push-first; loser exits nonzero |
| `coordination/bin/release-lock` | Create | Delete a lock file + commit |
| `tests/unit/test_lock_protocol.py` | Create | Lock claim/release behavior incl. loser-detect (temp bare-remote) |
| `scripts/wave_gate_check.py` | Create | Parse inventory + suite xfail pins; report per-wave status; exit nonzero if a wave gate is unmet |
| `tests/unit/test_wave_gate_check.py` | Create | Gate-check logic over fixture inventory + fixture pins |
| `scripts/seed_inventory.py` | Create | Enumerate existing xfail pins (file, reason, strict) → emit candidate inventory rows |
| `tests/unit/test_seed_inventory.py` | Create | Enumerator over a fixture test tree |
| `docs/REMEDIATION-INVENTORY.md` | Create | The campaign source-of-truth inventory (header + schema + seed rows) |
| `logs/discovery-<runid>.json` | Create (runtime) | Committed discovery handoff artifact (confirmed + rejected findings) |

**Boundary notes:** `wave_gate_check.py` only *reads* (inventory + suite) and reports —
it never mutates the inventory (coordinator/deputy own writes, spec §6a/§6f). `claim-lock`
/`release-lock` only touch `coordination/locks/` + git. `seed_inventory.py` only *emits*
candidate rows to stdout — the coordinator classifies + writes them (single-writer, §2).

---

## Chunk 1: Lock tooling + wave-gate checker

### Task 1: Lock directory

**Files:**
- Create: `coordination/locks/.gitkeep`

- [ ] **Step 1: Create the tracked lock directory**

```bash
mkdir -p coordination/locks
printf '# Git-native shared-module locks (spec §6b). One file per held lock:\n# W<n>-<module>.lock containing "seat wave ts defect-id". Tracked so the\n# commit-push claim works; first-commit-wins is prevention, not recovery.\n' > coordination/locks/.gitkeep
```

- [ ] **Step 2: Verify it is tracked**

Run: `git add coordination/locks/.gitkeep && git status --short coordination/locks/`
Expected: `A  coordination/locks/.gitkeep`

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(campaign): tracked coordination/locks/ dir for git-native module locks" -- coordination/locks/.gitkeep
```

### Task 2: `claim-lock` / `release-lock` helpers

**Files:**
- Create: `coordination/bin/claim-lock`
- Create: `coordination/bin/release-lock`
- Test: `tests/unit/test_lock_protocol.py`

- [ ] **Step 1: Write the failing test**

The test drives the real shell scripts against a temp repo wired to a local *bare* remote
(so `git push` and push-rejection are exercised for real). It asserts: (a) a clean claim
succeeds and creates+pushes the lock file; (b) a second claim of the same module after the
remote already has the lock is **rejected** (nonzero exit, no implementation should follow);
(c) release deletes the lock and pushes.

```python
# tests/unit/test_lock_protocol.py
import os, subprocess, textwrap
from pathlib import Path
import pytest

BIN = Path(__file__).resolve().parents[2] / "coordination" / "bin"

def _run(cmd, cwd, **kw):
    # UNSET GIT_INDEX_FILE (do not zero it: GIT_INDEX_FILE="" makes `git add` fail
    # rc=128 "unable to write new index file"). CLAUDE.md requires `env -u`.
    env = {k: v for k, v in os.environ.items() if k != "GIT_INDEX_FILE"}
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env, **kw)

def _git(args, cwd):
    r = _run(["git", *args], cwd)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()

@pytest.fixture
def two_clones(tmp_path):
    """A bare 'origin' + two clones (seatA, seatB) sharing it."""
    bare = tmp_path / "origin.git"
    _run(["git", "init", "--bare", str(bare)], tmp_path)
    seatA = tmp_path / "A"; seatB = tmp_path / "B"
    for c, seat in ((seatA, "operator"), (seatB, "operator2")):
        _run(["git", "clone", str(bare), str(c)], tmp_path)
        _git(["config", "user.email", f"{seat}@x"], c)
        _git(["config", "user.name", seat], c)
    # Create coordination/locks ONLY in seatA, commit+push it; seatB receives it via the
    # pull below. Writing .gitkeep into seatB too would make its ff-merge abort on an
    # untracked working-tree file.
    (seatA / "coordination" / "locks").mkdir(parents=True)
    (seatA / "coordination" / "locks" / ".gitkeep").write_text("x\n")
    _git(["add", "-A"], seatA); _git(["commit", "-m", "seed"], seatA)
    _git(["branch", "-M", "main"], seatA)
    _git(["push", "-u", "origin", "main"], seatA)
    _git(["pull", "--ff-only", "origin", "main"], seatB)
    return seatA, seatB

def test_clean_claim_succeeds_and_pushes(two_clones):
    seatA, _ = two_clones
    r = _run([str(BIN / "claim-lock"), "W1", "core.py", "operator", "bug-1"], seatA)
    assert r.returncode == 0, r.stderr
    assert (seatA / "coordination" / "locks" / "W1-core.py.lock").exists()

def test_second_claimant_aborts_via_precheck(two_clones):
    # PRIMARY defense: claim-lock fetches+ff-merges first, so the 2nd seat SEES the lock
    # file locally and aborts BEFORE committing/pushing. (The push-race is the secondary
    # defense, tested separately below.)
    seatA, seatB = two_clones
    assert _run([str(BIN / "claim-lock"), "W1", "core.py", "operator", "bug-1"], seatA).returncode == 0
    r = _run([str(BIN / "claim-lock"), "W1", "core.py", "operator2", "bug-2"], seatB)
    assert r.returncode != 0, "second claimant must lose via the pre-check"
    # the lock file IS present in seatB now (claim-lock fetch+merged seatA's lock into the
    # worktree); prove seatB never wrote ITS OWN entry — i.e. it did not claim.
    lockf = seatB / "coordination" / "locks" / "W1-core.py.lock"
    assert "operator2" not in lockf.read_text()

def test_release_deletes_and_pushes(two_clones):
    seatA, seatB = two_clones
    _run([str(BIN / "claim-lock"), "W1", "core.py", "operator", "bug-1"], seatA)
    assert _run([str(BIN / "release-lock"), "W1", "core.py"], seatA).returncode == 0
    assert not (seatA / "coordination" / "locks" / "W1-core.py.lock").exists()
    _git(["pull", "--ff-only", "origin", "main"], seatB)
    assert not (seatB / "coordination" / "locks" / "W1-core.py.lock").exists()

def test_push_rejection_rollback_primitive(two_clones):
    # SECONDARY defense: a seat that passed its pre-check on a stale view and only loses at
    # push must `git reset --hard origin/main` to drop its dangling local lock commit.
    # We reproduce that exact end-state (origin advanced under a locally-committed lock).
    seatA, seatB = two_clones
    assert _run([str(BIN / "claim-lock"), "W1", "core.py", "operator", "a"], seatA).returncode == 0
    lockB = seatB / "coordination" / "locks" / "W1-core.py.lock"
    lockB.write_text("operator2 W1 t b\n")                # simulate a stale-view local commit
    _git(["add", "--", "coordination/locks/W1-core.py.lock"], seatB)
    _git(["commit", "-m", "racing lock"], seatB)
    assert _run(["git", "push", "origin", "HEAD:main"], seatB).returncode != 0  # non-ff reject
    _git(["fetch", "origin", "main"], seatB)
    _git(["reset", "--hard", "origin/main"], seatB)        # the script's recovery branch
    assert not lockB.exists(), "rollback must drop the loser's local lock"

def test_lock_filename_flattens_slashes(two_clones):
    # A cross-cutting module with a slash (spec §6b: cinema/context.py) must map to ONE
    # deterministic lock filename, else two seats could 'hold' the same file under
    # different names. Verifies the flat= replacement in claim-lock.
    seatA, _ = two_clones
    assert _run([str(BIN / "claim-lock"), "W1", "cinema/context.py", "operator", "c"], seatA).returncode == 0
    assert (seatA / "coordination" / "locks" / "W1-cinema__context.py.lock").exists()
```

- [ ] **Step 2: Run to verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_lock_protocol.py -v`
Expected: FAIL (scripts `claim-lock`/`release-lock` do not exist → `FileNotFoundError`)
(`env -u GIT_INDEX_FILE` matches the `test_coordination_bin.py` convention — a seat's phantom index would corrupt `git add` in the subprocess.)

- [ ] **Step 3: Implement `coordination/bin/claim-lock`**

The module arg may contain `/` (e.g. `cinema/context.py`); flatten it for the lock
filename. Claim is **push-first**: only a successful push means you won the lock, so
implementation must only start after this script exits 0.

```bash
#!/usr/bin/env bash
# coordination/bin/claim-lock <wave> <module> <seat> <defect-id>
# Git-native shared-module lock claim (spec §6b). Push-first: exit 0 == you won.
set -euo pipefail
[ $# -eq 4 ] || { echo "usage: claim-lock <wave> <module> <seat> <defect-id>" >&2; exit 2; }
wave="$1"; module="$2"; seat="$3"; defect="$4"
cd "$(git rev-parse --show-toplevel)"
flat="${module//\//__}"               # cinema/context.py -> cinema__context.py
lock="coordination/locks/${wave}-${flat}.lock"
git fetch -q origin "$(git rev-parse --abbrev-ref HEAD)" \
  || echo "WARNING: fetch failed, proceeding on stale view (push-first still protects)" >&2
git merge -q --ff-only "@{u}" 2>/dev/null || true   # best-effort: see peer locks before claiming
if [ -e "$lock" ]; then echo "LOST: $lock already held" >&2; exit 1; fi
printf '%s %s %s %s\n' "$seat" "$wave" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$defect" > "$lock"
git add -- "$lock"
git commit -q -m "lock(${wave}): ${module} -> ${seat} (${defect})" -- "$lock"
if git push -q origin "HEAD:$(git rev-parse --abbrev-ref HEAD)"; then
  echo "WON: $lock"; exit 0
else
  git reset -q --hard "@{u}"          # undo local lock commit; we lost the race
  echo "LOST: push rejected (peer claimed first)" >&2; exit 1
fi
```

- [ ] **Step 4: Implement `coordination/bin/release-lock`**

```bash
#!/usr/bin/env bash
# coordination/bin/release-lock <wave> <module>
# Delete a held lock (spec §6b: operator GO commit, or holder after 3-FAIL cap).
set -euo pipefail
[ $# -eq 2 ] || { echo "usage: release-lock <wave> <module>" >&2; exit 2; }
wave="$1"; module="$2"
cd "$(git rev-parse --show-toplevel)"
flat="${module//\//__}"
lock="coordination/locks/${wave}-${flat}.lock"
[ -e "$lock" ] || { echo "no such lock: $lock" >&2; exit 0; }
git rm -q -- "$lock"
git commit -q -m "unlock(${wave}): ${module}" -- "$lock"
# A failed release-push leaves the lock LIVE on origin while it looks released
# locally — a silent wave-blocker. Exit nonzero so the caller must retry.
if ! git push -q origin "HEAD:$(git rev-parse --abbrev-ref HEAD)"; then
  git reset -q --hard "@{u}"   # restore the lock file locally so a retry re-attempts the full flow
  echo "RELEASE PUSH FAILED: $lock still held on origin — fetch + retry" >&2; exit 1
fi
echo "RELEASED: $lock"
```

- [ ] **Step 5: Make executable + run tests to verify they pass**

Run: `chmod +x coordination/bin/claim-lock coordination/bin/release-lock && env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_lock_protocol.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add coordination/bin/claim-lock coordination/bin/release-lock tests/unit/test_lock_protocol.py
git commit -m "feat(campaign): git-native claim-lock/release-lock helpers (spec §6b, push-first claim)" -- coordination/bin/claim-lock coordination/bin/release-lock tests/unit/test_lock_protocol.py
```

### Task 3: `wave_gate_check.py`

**Files:**
- Create: `scripts/wave_gate_check.py`
- Test: `tests/unit/test_wave_gate_check.py`

**Behavior:** given a wave number, parse `docs/REMEDIATION-INVENTORY.md`'s markdown table
and report, for that wave: counts by status, and the **gate verdict** — UNMET if any row
of severity CRITICAL/MAJOR in that wave is not `verified`, or if any `provisional` row
exists in that wave, else MET. Exit 0 if MET, 1 if UNMET. (Loose-pin cross-check against
the suite is a §11-delegated enhancement; this task ships the inventory-driven gate.)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_wave_gate_check.py
import importlib.util, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("wgc", ROOT / "scripts" / "wave_gate_check.py")

INVENTORY = """\
# Remediation Inventory

| id | subsystem | file:line | severity | priority | fail-mode | repro | xfail-pin | lane-owner | shared-lock | wave | status | verifier | notes |
|----|-----------|-----------|----------|----------|-----------|-------|-----------|------------|-------------|------|--------|----------|-------|
| budget-nan | money | core.py:101 | CRITICAL | 1 | nan bypass | t | tests/x.py | B |  | 1 | verified | op2 |  |
| gate-nan | gates | auto_approve.py:120 | CRITICAL | 2 | nan veto | t | tests/y.py | A | W1-auto_approve.py.lock | 1 | open | | |
| audio-zero | audio | audio/effects.py:230 | MAJOR | 1 | no tests | t | tests/z.py | B | | 2 | verified | op2 | |
"""

def _load():
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def test_unmet_when_open_critical(tmp_path):
    inv = tmp_path / "INV.md"; inv.write_text(INVENTORY)
    wgc = _load()
    report = wgc.gate_report(inv, wave=1)
    assert report["verdict"] == "UNMET"
    assert any(r["id"] == "gate-nan" for r in report["blockers"])

def test_met_when_all_verified(tmp_path):
    inv = tmp_path / "INV.md"; inv.write_text(INVENTORY)
    wgc = _load()
    report = wgc.gate_report(inv, wave=2)   # only audio-zero, verified
    assert report["verdict"] == "MET"
    assert report["blockers"] == []

def test_provisional_blocks_regardless_of_severity(tmp_path):
    # Wave 3 has no seeded rows, so a lone MINOR provisional cleanly isolates the
    # provisional-check (Wave 1 was already UNMET from its open CRITICAL).
    inv = tmp_path / "INV.md"
    inv.write_text(INVENTORY + "| p1 | x | core.py:9 | MINOR | 1 | x | t | tests/p.py | A | | 3 | provisional | | mid |\n")
    wgc = _load()
    rep = wgc.gate_report(inv, wave=3)
    assert rep["verdict"] == "UNMET" and any(r["id"] == "p1" for r in rep["blockers"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_wave_gate_check.py -v`
Expected: FAIL (`scripts/wave_gate_check.py` not found)

- [ ] **Step 3: Implement `scripts/wave_gate_check.py`**

```python
#!/usr/bin/env python3
"""Wave-gate checker for the hardening campaign (spec §5 acceptance, §6f).

Reads docs/REMEDIATION-INVENTORY.md and reports, for a wave, whether the gate is MET:
every CRITICAL/MAJOR row in the wave is `verified` and no `provisional` row remains.
Read-only — never mutates the inventory.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

_COLS = ("id", "subsystem", "file:line", "severity", "priority", "fail-mode",
         "repro", "xfail-pin", "lane-owner", "shared-lock", "wave", "status",
         "verifier", "notes")
_BLOCK_SEV = {"CRITICAL", "MAJOR"}

def _parse_rows(inventory_path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in inventory_path.read_text().splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(_COLS):           # header / separator / malformed
            continue
        row = dict(zip(_COLS, cells))
        if row["id"] in ("id", "----", "") or set(row["id"]) <= {"-"}:
            continue
        rows.append(row)
    return rows

def gate_report(inventory_path: Path, wave: int) -> dict:
    rows = [r for r in _parse_rows(inventory_path) if r["wave"] == str(wave)]
    blockers = [
        r for r in rows
        if r["status"] == "provisional"
        or (r["severity"].upper() in _BLOCK_SEV and r["status"] != "verified")
    ]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {
        "wave": wave,
        "verdict": "MET" if not blockers else "UNMET",
        "counts": counts,
        "blockers": blockers,
    }

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("wave", type=int)
    ap.add_argument("--inventory", default="docs/REMEDIATION-INVENTORY.md", type=Path)
    args = ap.parse_args(argv)
    if not args.inventory.exists():
        print(f"inventory not found: {args.inventory}", file=sys.stderr)
        return 2
    rep = gate_report(args.inventory, args.wave)
    print(f"Wave {rep['wave']} gate: {rep['verdict']}  counts={rep['counts']}")
    for b in rep["blockers"]:
        print(f"  BLOCKER [{b['severity']}/{b['status']}] {b['id']} ({b['file:line']})")
    return 0 if rep["verdict"] == "MET" else 1

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_wave_gate_check.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/wave_gate_check.py tests/unit/test_wave_gate_check.py
git commit -m "feat(campaign): wave_gate_check.py — inventory-driven wave acceptance gate (spec §5/§6f)" -- scripts/wave_gate_check.py tests/unit/test_wave_gate_check.py
```

---

## Chunk 2: Inventory + seed migration

**Prerequisite:** Chunk 1 is complete — Task 4 Step 2 and Task 6 Step 3 invoke
`scripts/wave_gate_check.py` (created in Chunk 1 Task 3). Do not start Chunk 2 first.

### Task 4: Create the inventory artifact

**Files:**
- Create: `docs/REMEDIATION-INVENTORY.md`

- [ ] **Step 1: Write the inventory with header + schema + empty wave sections**

```bash
cat > docs/REMEDIATION-INVENTORY.md <<'EOF'
# Remediation Inventory — Program Hardening Campaign

> Single source of truth (spec `docs/superpowers/specs/2026-06-14-program-hardening-roadmap-design.md` §2).
> **Writer:** coordinator (primary) + deputy own-lane status when coordinator offline (§6f).
> Status one of: open | fixing | fixed | verified | provisional.

## Campaign constants
- **Wave-gate SLA:** 24h (§6f).
- **Wave-1 cross-cutting first-mover sequence:** TO BE SET by coordinator at Wave-1 open (§6b).

## Schema
`| id | subsystem | file:line | severity | priority | fail-mode | repro | xfail-pin | lane-owner | shared-lock | wave | status | verifier | notes |`

| id | subsystem | file:line | severity | priority | fail-mode | repro | xfail-pin | lane-owner | shared-lock | wave | status | verifier | notes |
|----|-----------|-----------|----------|----------|-----------|-------|-----------|------------|-------------|------|--------|----------|-------|
EOF
```

- [ ] **Step 2: Verify the gate checker parses an empty inventory as MET**

Run: `.venv/bin/python scripts/wave_gate_check.py 1 --inventory docs/REMEDIATION-INVENTORY.md`
Expected: `Wave 1 gate: MET  counts={}` (exit 0 — no rows yet)

- [ ] **Step 3: Commit**

```bash
git add docs/REMEDIATION-INVENTORY.md   # new file: a pathspec commit will NOT auto-stage an untracked path
git commit -m "feat(campaign): seed docs/REMEDIATION-INVENTORY.md (schema + header)" -- docs/REMEDIATION-INVENTORY.md
```

### Task 5: `seed_inventory.py` — enumerate existing xfail pins

**Files:**
- Create: `scripts/seed_inventory.py`
- Test: `tests/unit/test_seed_inventory.py`

**Behavior:** scan `tests/` for `pytest.mark.xfail(...)` usages, extract `(test_file,
reason, strict)`, and emit candidate inventory rows (id from a reason slug, file:line
from the reason if present, blank wave/severity for the coordinator to classify). Pure
enumerator → stdout; it does NOT write the inventory (single-writer, §2/§6a).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_seed_inventory.py
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("seed", ROOT / "scripts" / "seed_inventory.py")

def _load():
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def test_finds_strict_xfail(tmp_path):
    t = tmp_path / "tests"; t.mkdir()
    (t / "test_a.py").write_text(
        'import pytest\n'
        '@pytest.mark.xfail(strict=True, reason="W1:CRITICAL:budget-nan core.py:101 nan bypass")\n'
        'def test_budget(): assert False\n'
    )
    pins = _load().find_xfail_pins(t)
    assert len(pins) == 1
    p = pins[0]
    assert p["strict"] is True
    assert p["test_file"].endswith("test_a.py")
    assert "budget-nan" in p["reason"]

def test_ignores_nonstrict_and_plain(tmp_path):
    t = tmp_path / "tests"; t.mkdir()
    (t / "test_b.py").write_text(
        'import pytest\n'
        '@pytest.mark.xfail(reason="flaky")\n'
        'def test_x(): pass\n'
    )
    pins = _load().find_xfail_pins(t)
    assert pins[0]["strict"] is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_seed_inventory.py -v`
Expected: FAIL (`scripts/seed_inventory.py` not found)

- [ ] **Step 3: Implement `scripts/seed_inventory.py`**

```python
#!/usr/bin/env python3
"""Enumerate existing pytest xfail pins under a tests/ tree → candidate inventory rows.

Emits to stdout; never writes the inventory (coordinator is the single writer, spec §2).
Uses the AST so it is robust to formatting. Captures reason + strict for each xfail mark.
"""
from __future__ import annotations
import argparse, ast, sys
from pathlib import Path

def _xfail_marks(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        # match pytest.mark.xfail(...) / mark.xfail(...)
        if isinstance(f, ast.Attribute) and f.attr == "xfail":
            yield node

def find_xfail_pins(tests_root: Path) -> list[dict]:
    pins: list[dict] = []
    for path in sorted(Path(tests_root).rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for call in _xfail_marks(tree):
            reason, strict = "", False
            for kw in call.keywords:
                if kw.arg == "reason" and isinstance(kw.value, ast.Constant):
                    reason = str(kw.value.value)
                if kw.arg == "strict" and isinstance(kw.value, ast.Constant):
                    strict = bool(kw.value.value)
            pins.append({"test_file": str(path), "reason": reason, "strict": strict})
    return pins

def _slug(reason: str) -> str:
    # "W1:CRITICAL:budget-nan core.py:101 ..." -> "budget-nan" when prefixed, else first token
    parts = reason.split()
    head = parts[0] if parts else "unknown"
    if head.count(":") >= 2:
        return head.split(":")[2]
    return (head[:32] or "unknown")

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests", default="tests", type=Path)
    args = ap.parse_args(argv)
    seen: dict[str, int] = {}
    for p in find_xfail_pins(args.tests):
        flag = "strict" if p["strict"] else "NON-STRICT"
        sid = _slug(p["reason"])
        seen[sid] = seen.get(sid, 0) + 1
        if seen[sid] > 1:
            sid = f"{sid}-{seen[sid]}"   # de-collide duplicate slugs (e.g. two 'sibling' pins)
        print(f"| {sid} |  |  |  |  |  |  | {p['test_file']} |  |  |  | open |  | {flag}: {p['reason'][:60]} |")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_seed_inventory.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/seed_inventory.py tests/unit/test_seed_inventory.py
git commit -m "feat(campaign): seed_inventory.py — enumerate existing xfail pins as candidate rows" -- scripts/seed_inventory.py tests/unit/test_seed_inventory.py
```

### Task 6: Seed-migrate the existing pins (coordinator action)

**Files:**
- Modify: `docs/REMEDIATION-INVENTORY.md`

This is a **coordinator** classification step (not pure code): run the enumerator, then for
each pin set `severity`, `wave`, `lane-owner`, and `status` per the spec §3 HEAD-check
vocabulary (merged+verified → `verified`; fix dispatched-not-verified → `fixing`;
pinned-unfixed → `open`). NON-STRICT pins are flagged for upgrade to `strict=True` in their
owning lane (recorded in `notes`, not edited here — that is a lane fix).

- [ ] **Step 1: Generate candidate rows**

Run: `.venv/bin/python scripts/seed_inventory.py --tests tests > /tmp/seed_rows.md && wc -l /tmp/seed_rows.md`
Expected: one row per xfail **decorator** — **≈10** in the current suite (cross-check:
`grep -rn 'mark.xfail' tests/ | grep -v __pycache__ | wc -l`). Note: the spec's "~28 pins"
counts xfail *cases* (incl. parametrized / multi-assert pins); this enumerates *decorators*.

- [ ] **Step 2: Classify each row** (coordinator)

For each candidate, fill **all working fields**: `subsystem`, `file:line` (from the pin's
reason/target), `severity` (§4 taxonomy), `priority` (intra-lane order), `fail-mode`,
`repro`, `lane-owner` (§6b partition), `wave` (CRITICAL→1, MAJOR→2, …), `priority` (leave
**blank** at seed — directors set it per-wave in the R-BRIEF; `wave_gate_check` ignores it), and `status`
(HEAD-check vocabulary). (`shared-lock` is only for cross-cutting rows; `verifier` is filled
at verification time.) Paste the completed rows under the table in
`docs/REMEDIATION-INVENTORY.md`. Cross-check each against HEAD: a module already
fixed+verified (e.g. `workflow_selector.py`/`bf1034a`) is `verified`, not re-hunted.
HEAD-check status mapping (§3): merged+verified-closed → `verified`; fix dispatched but not
yet operator-verified → `fixing`; pinned-but-unfixed → `open`.

- [ ] **Step 3: Verify the gate checker reads the seeded inventory**

Run: `.venv/bin/python scripts/wave_gate_check.py 1 --inventory docs/REMEDIATION-INVENTORY.md`
Expected: `Wave 1 gate: UNMET` with the open/fixing CRITICALs listed as blockers (exit 1 — correct: Wave 1 has open defects).

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(campaign): seed-migrate existing xfail pins into the remediation inventory (HEAD-checked)" -- docs/REMEDIATION-INVENTORY.md
```

---

## Chunk 3: Discovery bug-hunt

### Task 7: Author + run the discovery Workflow

**Files:**
- Create: `coordination/workflows/discovery-bughunt.js` (committed for reproducibility)
- Create (runtime): `logs/discovery-<runid>.json`
- Modify: `docs/REMEDIATION-INVENTORY.md` + new `tests/unit/test_discovery_*_xfail.py` pins

The discovery bug-hunt is a **coordinator-run Workflow** (orchestration, not pytest-TDD):
one finder per high-risk subsystem (§3) probing fail-open paths, then ≥2 independent
**refuters** per candidate; CONFIRMED iff no refuter disproves it. Sonnet for all agents
(project directive). Excludes the PRE-CLOSED determinism fix (§5) and `workflow_selector.py`
(closed by `bf1034a`).

- [ ] **Step 1: Author `coordination/workflows/discovery-bughunt.js`**

Run `mkdir -p coordination/workflows` first (the directory may not exist yet), then write
this script to `coordination/workflows/discovery-bughunt.js`:

```javascript
export const meta = {
  name: 'discovery-bughunt',
  description: 'Phase 0 adversarial bug-hunt across high-risk subsystems + refute pass',
  phases: [{ title: 'Find' }, { title: 'Refute' }],
}
const FINDING = {
  type: 'object', additionalProperties: false, required: ['findings'],
  properties: { findings: { type: 'array', items: {
    type: 'object', additionalProperties: false,
    required: ['subsystem','file_line','fail_mode','reproducer','severity_guess'],
    properties: {
      subsystem:{type:'string'}, file_line:{type:'string'}, fail_mode:{type:'string'},
      reproducer:{type:'string'},
      severity_guess:{type:'string',enum:['CRITICAL','MAJOR','MEDIUM','MINOR']},
    }}}},
}
const VERDICT = { type:'object', additionalProperties:false, required:['refuted','reasoning'],
  properties:{ refuted:{type:'boolean'}, reasoning:{type:'string'} } }
const SUBSYSTEMS = [
  {key:'gates', probe:'auto_approve, face_validator_gate, motion_gate, identity_gate, coherence_analyzer'},
  {key:'money', probe:'core.py budget, cost-estimation, lip-sync pricing (unbounded-spend)'},
  {key:'io', probe:'image/video decode, API-error swallow, ffmpeg/ffprobe failure'},
  {key:'http', probe:'web_server.py destructive/state-mutating endpoints'},
  {key:'checkpoint', probe:'resume/checkpoint state reconstruction'},
  {key:'identity', probe:'PuLID/LoRA injection, secondary-char binding'},
]
const FIND = (s) => `Repo root /Users/hyungkoookkim/Content. READ-ONLY (grep/Read only). Hunt FAIL-OPEN bugs (not happy paths the tests already cover) in the ${s.key} subsystem: ${s.probe}. Focus on silent-degradation, NaN/inf, and swallowed-error paths. EXCLUDE the OpenCV determinism fix (PRE-CLOSED, ARCHITECTURE §11.1) and workflow_selector.py (closed by bf1034a). Each finding needs a concrete reproducer.`
const REFUTE = (f,i) => `Repo root /Users/hyungkoookkim/Content. READ-ONLY. A finder claims: ${f.subsystem} ${f.file_line} — "${f.fail_mode}" (repro: ${f.reproducer}). Try to REFUTE it — read the code + its guards/callers. Set \`refuted=true\` if you can PROVE it is NOT a real defect; set \`refuted=false\` only if you cannot disprove it after genuine effort. (Note the field direction: true = disproved, false = finding stands.) Skeptic #${i}.\`

phase('Find')
const found = (await parallel(SUBSYSTEMS.map(s => () =>
  agent(FIND(s), {label:`find:${s.key}`, phase:'Find', schema:FINDING, model:'sonnet'}))))
  .filter(Boolean).flatMap(r => r.findings)

phase('Refute')
const judged = await parallel(found.map(f => () =>
  parallel([0,1].map(i => () =>
    agent(REFUTE(f,i), {label:`refute:${f.file_line}`, phase:'Refute', schema:VERDICT, model:'sonnet'})))
    .then(vs => { const ok = vs.filter(Boolean);
      // CONFIRMED requires BOTH refuters to have returned AND neither to refute.
      // (Guard the vacuous-truth: [].every() === true would confirm a finding whose
      //  refuters both died — the opposite of safe. A missing verdict => not confirmed.)
      return { finding:f, verdicts: ok, confirmed: ok.length === 2 && ok.every(v => !v.refuted) }; })))

return {  // refuter reasoning preserved in logs/discovery-<runid>.json (§3 finding-record)
  confirmed: judged.filter(j => j.confirmed).map(j => ({ ...j.finding, refuters: j.verdicts })),
  rejected:  judged.filter(j => !j.confirmed).map(j => ({ ...j.finding, refuters: j.verdicts })),
}
```

- [ ] **Step 2: Run discovery + commit the handoff artifact**

Invoke via the Workflow tool: `Workflow({scriptPath: "coordination/workflows/discovery-bughunt.js"})`.
When it completes, write its returned `{confirmed, rejected}` object verbatim to
`logs/discovery-<runId>.json`, where `<runId>` is the **`Run ID`** field in the Workflow
tool's result (e.g. `wf_ab12cd34`).
Expected: a non-empty `confirmed` array (each finder typically surfaces ≥1 fail-open path);
`rejected` holds the refuted candidates.

```bash
mkdir -p coordination/workflows logs
# A Workflow/subagent run can leave skip-worktree pollution in the index (hook v5.9 / memory).
# If `git add` below silently no-ops or errors with a sparse-checkout message, clear it:
#   git ls-files -v | awk '/^S/{print $2}' | xargs -r git update-index --no-skip-worktree --
git add coordination/workflows/discovery-bughunt.js logs/discovery-*.json
git commit -m "chore(campaign): discovery bug-hunt workflow + handoff artifact (confirmed + rejected)" -- coordination/workflows/discovery-bughunt.js logs/
```

- [ ] **Step 3: Transcribe CONFIRMED findings → inventory rows + strict xfail pins**

For each CONFIRMED finding the coordinator adds **one inventory row** (status `open`;
severity = `severity_guess` re-checked against §4; wave + lane from §4/§6b) and authors a
**`strict=True`** xfail pin whose reason is prefixed `W<n>:<SEVERITY>:<id>` (§3), the test
reproducing `reproducer`. **REJECTED findings** are not added to the active table; they are
recorded (a) in full in `logs/discovery-<runid>.json` and (b) one line each under a
`## Rejected findings (discovery)` appendix in the inventory — `file:line — REJECTED:<reason>`
— satisfying spec §3 ("noted in the inventory, never silently dropped"). Commit inventory +
pins together (test-only artifacts, coordinator-scoped, §6a).

```bash
git add docs/REMEDIATION-INVENTORY.md tests/
git commit -m "chore(campaign): transcribe confirmed discovery findings -> inventory rows + strict xfail pins"
```

### Task 8: Phase-0 acceptance gate

**Files:** none (verification only)

- [ ] **Step 1: ci_smoke green (pins are xfail, not red)**

Run: `.venv/bin/python scripts/ci_smoke.py`
Expected: `OK` (exit 0). Newly-pinned defects are `xfail`, so the suite stays green.

- [ ] **Step 2: every CONFIRMED *campaign* pin is strict (legacy pins excluded)**

Campaign pins carry a `W<n>:` reason prefix; pre-existing legacy pins are out of scope here.
Run: `.venv/bin/python scripts/seed_inventory.py --tests tests | grep 'NON-STRICT' | grep 'W[0-9]:' | wc -l`
Expected: `0` (no campaign-prefixed pin is non-strict). `wc -l` is used instead of `grep -c`
because `grep -c` exits nonzero on zero matches, which would look like a step failure. Legacy
non-strict pins, if any, are listed for their owning lane to upgrade — not gated by Phase 0.

- [ ] **Step 3: the wave gates reflect the populated inventory**

Run: `.venv/bin/python scripts/wave_gate_check.py 1 --inventory docs/REMEDIATION-INVENTORY.md; echo "exit=$?"`
Expected: `UNMET`, `exit=1` (Wave 1 has open CRITICALs to fix — correct campaign start state).

- [ ] **Step 4: Phase-0 done — hand off to the Wave-1 plan**

Phase 0 is complete when: seed migration committed; `logs/discovery-<runId>.json` committed;
every CONFIRMED defect has an inventory row + strict pin; rejects recorded; `ci_smoke` green.

**Next (Wave-1 planning):**
1. Coordinator records the **Wave-1 cross-cutting first-mover sequence** in the inventory
   header (spec §6b/§10 prerequisite — must precede Wave-1 open).
2. Invoke **superpowers:writing-plans** to author
   `docs/superpowers/plans/2026-06-14-program-hardening-wave1.md` from the now-populated
   inventory (its tasks = the Wave-1 CRITICAL rows), per the one-plan-per-wave decomposition.

---

## Notes for the executor

- **Commits:** explicit pathspec, one logical change per commit (coordinator/seat model).
  Subagents prefix git with `env -u GIT_INDEX_FILE`.
- **Determinism (§5):** the OpenCV thread-race fix is PRE-CLOSED (`ARCHITECTURE.md` §11.1) —
  do not re-discover it in Task 7; the discovery prompt excludes it.
- **§11 delegated decisions** resolved within this plan: refuter count (≥2, Task 7);
  seed status vocabulary (Task 6); pin convention (strict + `W<n>:<SEV>:<id>`, Tasks 6–7).
  The remaining §11 items (lip-sync script I/O, conftest policy, pod-off executor, NITS-vs-
  FAIL-cap) belong to the **Wave-2/Wave-4 plans**, not Phase 0.
