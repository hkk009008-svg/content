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
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, "GIT_INDEX_FILE": ""}, **kw)

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
        (c / "coordination" / "locks").mkdir(parents=True)
        (c / "coordination" / "locks" / ".gitkeep").write_text("x\n")
    # seed origin from A
    _git(["add", "-A"], seatA); _git(["commit", "-m", "seed"], seatA)
    _git(["push", "origin", "HEAD:main"], seatA)
    _git(["branch", "-M", "main"], seatA)
    _git(["push", "-u", "origin", "main"], seatA)
    _git(["pull", "--ff-only", "origin", "main"], seatB)
    return seatA, seatB

def test_clean_claim_succeeds_and_pushes(two_clones):
    seatA, _ = two_clones
    r = _run([str(BIN / "claim-lock"), "W1", "core.py", "operator", "bug-1"], seatA)
    assert r.returncode == 0, r.stderr
    assert (seatA / "coordination" / "locks" / "W1-core.py.lock").exists()

def test_second_claimant_is_rejected(two_clones):
    seatA, seatB = two_clones
    assert _run([str(BIN / "claim-lock"), "W1", "core.py", "operator", "bug-1"], seatA).returncode == 0
    r = _run([str(BIN / "claim-lock"), "W1", "core.py", "operator2", "bug-2"], seatB)
    assert r.returncode != 0, "second claimant must lose (push rejected)"

def test_release_deletes_and_pushes(two_clones):
    seatA, seatB = two_clones
    _run([str(BIN / "claim-lock"), "W1", "core.py", "operator", "bug-1"], seatA)
    assert _run([str(BIN / "release-lock"), "W1", "core.py"], seatA).returncode == 0
    assert not (seatA / "coordination" / "locks" / "W1-core.py.lock").exists()
    _git(["pull", "--ff-only", "origin", "main"], seatB)
    assert not (seatB / "coordination" / "locks" / "W1-core.py.lock").exists()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_lock_protocol.py -v`
Expected: FAIL (scripts `claim-lock`/`release-lock` do not exist → nonzero / FileNotFound)

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
git fetch -q origin "$(git rev-parse --abbrev-ref HEAD)" || true
git merge -q --ff-only "@{u}" 2>/dev/null || true   # see peer locks before claiming
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
git push -q origin "HEAD:$(git rev-parse --abbrev-ref HEAD)" || true
echo "RELEASED: $lock"
```

- [ ] **Step 5: Make executable + run tests to verify they pass**

Run: `chmod +x coordination/bin/claim-lock coordination/bin/release-lock && .venv/bin/python -m pytest tests/unit/test_lock_protocol.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add coordination/bin/claim-lock coordination/bin/release-lock tests/unit/test_lock_protocol.py
git commit -m "feat(campaign): git-native claim-lock/release-lock helpers (spec §6b, push-first claim)"
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

def test_provisional_blocks(tmp_path):
    inv = tmp_path / "INV.md"
    inv.write_text(INVENTORY + "| p1 | gates | core.py:9 | CRITICAL | 1 | x | t | tests/p.py | A | | 1 | provisional | | mid-wave |\n")
    wgc = _load()
    assert wgc.gate_report(inv, wave=1)["verdict"] == "UNMET"
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
git commit -m "feat(campaign): wave_gate_check.py — inventory-driven wave acceptance gate (spec §5/§6f)"
```

---

## Chunk 2: Inventory + seed migration

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
    for p in find_xfail_pins(args.tests):
        flag = "strict" if p["strict"] else "NON-STRICT"
        print(f"| {_slug(p['reason'])} |  |  |  |  |  |  | {p['test_file']} |  |  |  | open |  | {flag}: {p['reason'][:60]} |")
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
git commit -m "feat(campaign): seed_inventory.py — enumerate existing xfail pins as candidate rows"
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
Expected: one row per xfail pin (~28+).

- [ ] **Step 2: Classify each row** (coordinator)

For each candidate, fill `severity` (§4 taxonomy), `wave` (CRITICAL→1, MAJOR→2, etc.),
`lane-owner` (§6b partition), and `status` (HEAD-check vocabulary). Paste the completed
rows under the table in `docs/REMEDIATION-INVENTORY.md`. Cross-check each against HEAD: a
module already fixed+verified (e.g. `workflow_selector.py`/`bf1034a`) is `verified`, not re-hunted.

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
- Create (runtime): `logs/discovery-<runid>.json`
- Modify: `docs/REMEDIATION-INVENTORY.md`

The discovery bug-hunt is a **coordinator-owned Workflow** (orchestration, not pytest-TDD).
Author a workflow that fans adversarial agents across the §3 high-risk subsystems, each
probing fail-open paths, then a **refute pass** (≥2 independent refuters per candidate, the
§11-delegated mechanic) that must fail to disprove for a finding to be CONFIRMED. The
workflow returns the structured finding records (`{subsystem, file:line, fail-mode,
reproducer, severity-guess, refuter-verdict}`); the coordinator commits them to
`logs/discovery-<runid>.json` (the §3 named handoff artifact).

- [ ] **Step 1: Author the discovery workflow script**

Subsystems (one finder agent each, §3): gates (`auto_approve`, `face_validator_gate`,
`motion_gate`, `identity_gate`, `coherence_analyzer`); money (`core.py` budget,
cost-estimation, lip-sync pricing); silent-degradation I/O (image/video decode, API-error
swallow, ffmpeg/ffprobe); HTTP mutators (`web_server.py`); resume/checkpoint;
identity/continuity (PuLID/LoRA, secondary-char). Each finder emits finding records via a
StructuredOutput schema. Pipeline each finding through ≥2 refuters; CONFIRMED iff no refuter
disproves it. Use Sonnet for all agents (project directive). Skip modules the seed marked
`verified` (e.g. `workflow_selector.py`).

- [ ] **Step 2: Run discovery + commit the handoff artifact**

Run the workflow; write the returned JSON to `logs/discovery-<runid>.json`.

```bash
git add logs/discovery-*.json
git commit -m "chore(campaign): discovery bug-hunt handoff artifact (confirmed + rejected findings)" -- logs/
```

- [ ] **Step 3: Transcribe CONFIRMED findings → inventory rows + author strict xfail pins**

For each CONFIRMED finding the coordinator adds an inventory row (severity, wave, lane,
status `open`) and authors a **`strict=True`** xfail pin whose reason is prefixed
`W<n>:<SEVERITY>:<id>` (spec §3). REJECTED findings are recorded in the inventory `notes`
as `REJECTED:<reason>` (never silently dropped). Commit inventory + pins together
(test-only artifacts, coordinator-scoped, §6a).

```bash
git add docs/REMEDIATION-INVENTORY.md tests/
git commit -m "chore(campaign): transcribe confirmed discovery findings -> inventory rows + strict xfail pins"
```

### Task 8: Phase-0 acceptance gate

**Files:** none (verification only)

- [ ] **Step 1: ci_smoke green (pins are xfail, not red)**

Run: `.venv/bin/python scripts/ci_smoke.py`
Expected: `OK` (exit 0). Newly-pinned defects are `xfail`, so the suite stays green.

- [ ] **Step 2: every confirmed defect has a row + a strict pin**

Run: `.venv/bin/python scripts/seed_inventory.py --tests tests | grep -c NON-STRICT`
Expected: `0` new non-strict pins among the campaign pins (legacy non-strict pins, if any, are noted for lane upgrade).

- [ ] **Step 3: the wave gates reflect the populated inventory**

Run: `.venv/bin/python scripts/wave_gate_check.py 1 --inventory docs/REMEDIATION-INVENTORY.md; echo "exit=$?"`
Expected: `UNMET`, `exit=1` (Wave 1 has open CRITICALs to fix — correct campaign start state).

- [ ] **Step 4: Phase-0 done — hand off to the Wave-1 plan**

Phase 0 is complete when: seed migration committed; `logs/discovery-<runid>.json` committed;
every CONFIRMED defect has an inventory row + strict pin; rejects recorded; `ci_smoke` green.
**Next:** write the Wave-1 implementation plan from the now-populated inventory (its tasks =
the Wave-1 CRITICAL rows), per the campaign's one-plan-per-wave decomposition.

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
