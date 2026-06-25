# Threeway SP2 — Real Seat↔Bus Wiring Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the interactive seats emit and consume the live signed bus directly via two new Python CLIs (`consume_bus.py`, `seat_emit.py`), then retire the human-driven `bootstrap_emit.py` shim — covering exactly the shim's **T1** facts.

**Architecture:** SP2 adds only CALLERS onto the already-built, hardened bus substrate (`threeway/refstore.py`, `envelope.py`, `keys.py`, `loop.py`, `reducer.py`, `gate.py`). `seat_emit` hard-binds the seat from an explicit positional arg and loads only that seat's key (closing the shim's `signer`-derived key-injection). `consume_bus` reads events past a per-seat local cursor and advances it. Single-host, single-operator.

**Tech Stack:** Python 3 (stdlib `argparse`/`subprocess`), Ed25519 via `cryptography` (already wired in `threeway.keys`), `pytest`, git plumbing via `threeway.gitcas`. Bus = `refs/threeway/events` (git ref, append-CAS). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-24-threeway-sp2-seat-bus-wiring-design.md` (committed `76513cfe`). Read it before each task — it carries the verified substrate facts and the non-vacuous-pin rationale.

**Conventions for every task:**
- Subagents prefix all git with `env -u GIT_INDEX_FILE`. Commit with explicit pathspec, `-m` BEFORE `--`.
- Both new scripts begin with the ADR-055 sys.path self-bootstrap (mirror `scripts/sign_ci_result.py:19-22` / `scripts/bootstrap_emit.py:14-16`) so they run as bare subprocesses under CI without `PYTHONPATH`.
- Tests import the CLI as `from scripts.<name> import main` (codebase convention; `pyproject.toml` sets `pythonpath=["."]`, so `scripts/` is importable as a namespace package — a bare `import consume_bus` does NOT resolve).
- Tests are hermetic: a per-file `seatkit` fixture generates fresh keypairs into a temp registry + keystore and `monkeypatch.setenv("THREEWAY_KEYSTORE", …)`; `verify_and_reduce(..., registry_dir=str(reg), …)` checks against that SAME temp registry. **Never** point `registry_dir` at the committed `coordination/threeway/keys` while signing with temp keys — every event would be dropped (round-trip fails; negative pins pass vacuously).
- Run `.venv/bin/python -m pytest …` and `.venv/bin/python scripts/ci_smoke.py` (must stay green).
- TDD: write the failing test, run it RED, implement minimally, run it GREEN, commit. Each phase = one commit + an independent Lane-V before its cross-cutting effects are trusted.

---

## File Structure

| File | Disposition | Responsibility |
|---|---|---|
| `scripts/consume_bus.py` | **Create** (2a) | Read bus events addressed to a seat past its cursor; advance the local cursor. |
| `tests/unit/test_threeway_consume_bus.py` | **Create** (2a) | Unit pins for the read/filter/advance/error contract. |
| `scripts/seat_emit.py` | **Create** (2b) | Per-seat signed emission of the T1 facts; static seat↔kind authority. |
| `tests/unit/test_threeway_seat_emit.py` | **Create** (2b) | Unit pins: round-trip, rc2 authority bypass, candidate_aborted family, `--tier`. |
| `tests/unit/test_threeway_e2e_walking_skeleton.py` | **Modify in place** (2c) | Swap `bootstrap_emit` → `seat_emit`+`consume_bus`; exact consume_bus assertion. |
| `tests/unit/test_threeway_activation_scripts.py` | **Modify** (2d) | Repoint `_ACTIVATION_SCRIPTS` from `bootstrap_emit.py` to the two new CLIs. |
| `scripts/bootstrap_emit.py` | **Delete** (2d) | Retired. |
| `tests/unit/test_threeway_bootstrap_emit.py` | **Delete** (2d) | Orphaned by the rm; coverage migrated to 2a/2b tests. |
| `ARCHITECTURE.md`, `DECISIONS.md` | **Modify** (2d) | Doc-sync + new ADR marking the shim retired. |

Both new test files **copy the `seatkit` / `live_repo` / `_git` / `_env` fixtures from `tests/unit/test_threeway_gate.py`** (the codebase's canonical source — duplicated per test file by convention; do NOT restructure into a shared conftest). **Extend the copied `seatkit` seat list to all 9 keyed seats** — `director, director2, operator, operator2, coordinator, coordinator2, overseer, ci, merge-gate` — because the canonical gate.py copy omits `coordinator2`/`director2`, which PAIR_B emission needs (else a coordinator2-signed event is dropped as an unknown signer). `seat_emit` derives the pair from the seat (`coordinator`/`operator`→PAIR_A; `coordinator2`/`operator2`→PAIR_B).

---

## Chunk 1: Phase 2a — `consume_bus.py` (read-only)

### Task 1: consume_bus CLI + unit pins

**Files:**
- Create: `scripts/consume_bus.py`
- Test: `tests/unit/test_threeway_consume_bus.py`

Reference: spec §3.1 (behavior, output format, empty-bus, errors) + §6 (consume_bus pins). Substrate read pattern: `scripts/agy_observer.py`. Cursor API: `threeway/refstore.py:258-290`.

- [ ] **Step 1: Write the failing tests.** Create `tests/unit/test_threeway_consume_bus.py`. The events are appended directly via `build_candidate_events` + `RefEventStore.append` (NOT via `bootstrap_emit`, which is being retired) so this test is self-contained.

```python
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_consume_bus.py -q"""
import contextlib
import io
import os
import subprocess

import pytest

from threeway import keys
from threeway.envelope import Event
from threeway.loop import PAIR_A, build_candidate_events
from threeway.refstore import RefEventStore


# --- fixtures copied from tests/unit/test_threeway_gate.py (per-file convention) ---
def _env():
    env = dict(os.environ); env.pop("GIT_INDEX_FILE", None); return env


def _git(repo, *a, stdin=None):
    return subprocess.run(["git", "-C", str(repo), *a], check=True,
                          capture_output=True, text=(stdin is None), input=stdin, env=_env())


@pytest.fixture()
def seatkit(tmp_path, monkeypatch):
    reg = tmp_path / "pub"; ks = tmp_path / "ks"; reg.mkdir(); ks.mkdir()
    for seat in ("director", "director2", "operator", "operator2", "coordinator", "coordinator2",
                 "overseer", "ci", "merge-gate"):
        priv, pub = keys.generate_keypair()
        (reg / f"{seat}.pub").write_text(pub + "\n")
        (ks / f"{seat}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
    monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks))
    return reg, ks


@pytest.fixture()
def live_repo(tmp_path):
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q"); _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", "refs/threeway/test-main", base)
    _git(r, "checkout", "-q", "-b", "feat")
    (r / "cinema").mkdir(); (r / "cinema" / "f.py").write_text("x = 1\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "feat")
    branch = _git(r, "rev-parse", "HEAD").stdout.strip()
    return r, base, branch


def _append_all(repo, events):
    """Sign+append each event with ITS seat's key (signer prefix); return the last stored Event."""
    store = RefEventStore(repo)
    last = None
    for ev in events:
        last = store.append(ev, keys.load_private(ev.signer.split(":", 1)[0]))
    return last


def _run(argv):
    from scripts.consume_bus import main
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = main(argv)
    return rc, out.getvalue()


def test_shows_addressed_event_and_advances_cursor(seatkit, live_repo):
    r, base, branch = live_repo
    last = _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, pair=PAIR_A, candidate_id="c1"))
    rc, out = _run(["coordinator", "--repo-dir", str(r), "--remote", ""])
    assert rc == 0
    kinds = {l.split("\t")[1] for l in out.splitlines() if l.strip()}
    assert "candidate" in kinds
    assert RefEventStore(r).cursor_seq("coordinator") == last.seq          # advanced to tip


def test_no_advance_leaves_cursor(seatkit, live_repo):
    r, base, branch = live_repo
    _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, pair=PAIR_A, candidate_id="c1"))
    _run(["coordinator", "--repo-dir", str(r), "--remote", "", "--no-advance"])
    assert RefEventStore(r).cursor_seq("coordinator") == 0


def test_addressee_filter_hides_directed_event(seatkit, live_repo):
    # MUTATION TARGET: an event with recipient="director" must NOT show for coordinator.
    r, base, branch = live_repo
    ev = Event(id="x-coordinator-c1", seq=0, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="director",
               signer="coordinator:claude:s1", payload={"candidate_id": "A:c1"},
               brief_id="b1", brief_version=1, candidate_id="A:c1")
    RefEventStore(r).append(ev, keys.load_private("coordinator"))
    rc, out = _run(["coordinator", "--repo-dir", str(r), "--remote", ""])
    assert rc == 0 and out.strip() == ""                                   # leaks RED if filter removed


def test_empty_bus_clean_noop(seatkit, live_repo):
    r, *_ = live_repo
    rc, out = _run(["operator", "--repo-dir", str(r), "--remote", ""])
    assert rc == 0 and out.strip() == ""
    assert RefEventStore(r).cursor_seq("operator") == 0                     # no max() ValueError; cursor 0


def test_kinds_filter(seatkit, live_repo):
    r, base, branch = live_repo
    _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, pair=PAIR_A, candidate_id="c1"))
    rc, out = _run(["coordinator", "--repo-dir", str(r), "--remote", "", "--kinds", "candidate"])
    assert {l.split("\t")[1] for l in out.splitlines() if l.strip()} == {"candidate"}


def test_bus_id_filter_hides_foreign(seatkit, live_repo):
    r, base, branch = live_repo
    _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, bus_id="staging",
                                          pair=PAIR_A, candidate_id="c1"))
    rc, out = _run(["coordinator", "--repo-dir", str(r), "--remote", "", "--bus-id", "prod"])
    assert out.strip() == ""                                               # foreign-bus hidden


def test_corrupt_cursor_exits_rc1(seatkit, live_repo):
    r, base, branch = live_repo
    _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, pair=PAIR_A, candidate_id="c1"))
    oid = _git(r, "hash-object", "-w", "--stdin", stdin=b"not-an-int\n").stdout.decode().strip()
    _git(r, "update-ref", "refs/threeway/cursors/coordinator", oid)
    rc, _ = _run(["coordinator", "--repo-dir", str(r), "--remote", ""])
    assert rc == 1                                                         # CursorCorruptionError, no traceback
```

- [ ] **Step 2: Run the tests — verify they FAIL.**
  Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_consume_bus.py -q`
  Expected: `ModuleNotFoundError: No module named 'scripts.consume_bus'` (script not created yet).

- [ ] **Step 3: Implement `scripts/consume_bus.py`.**

```python
#!/usr/bin/env python3
"""consume_bus.py — read signed-bus events addressed to a seat past its cursor and advance the
seat's LOCAL cursor. The bus analog of coordination/bin/consume-events. Raw read: signature
verification is the gate's job, not the consume path (SP2 spec §3.1)."""
import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:                      # ADR-055 self-bootstrap (no PYTHONPATH)
    sys.path.insert(0, str(_REPO_ROOT))

from threeway.refstore import (                          # noqa: E402
    CursorContentionExceeded, CursorCorruptionError, RefEventStore,
)

# The 6 cursor/interactive seats (== cursor_backfill.SEATS), NOT the full keyed-seat universe
# (which also has overseer/ci/merge-gate); only these 6 have per-seat read cursors.
SEATS = ("director", "director2", "operator", "operator2", "coordinator", "coordinator2")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read bus events addressed to a seat; advance its cursor.")
    ap.add_argument("seat", choices=SEATS)
    ap.add_argument("--kinds", default=None, help="comma-separated kind allowlist")
    ap.add_argument("--no-advance", action="store_true")
    ap.add_argument("--repo-dir", default=".")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--bus-id", default="prod")
    a = ap.parse_args(argv)
    remote = (a.remote or None)                          # "" -> None (local); RefEventStore checks `is not None`
    seat = a.seat
    store = RefEventStore(Path(a.repo_dir), remote=remote)
    try:
        cursor = store.cursor_seq(seat)
        events = list(store.iter_events())              # collect ONCE (iter_events re-fetches per call)
    except CursorCorruptionError as e:
        print(f"cursor blob corrupt for {seat}: {e}", file=sys.stderr)
        return 1
    tip = max((ev.seq for ev in events), default=0)     # full-snapshot watermark (empty-safe)
    kinds = set(a.kinds.split(",")) if a.kinds else None
    shown = [
        ev for ev in events
        if ev.seq > cursor and ev.bus_id == a.bus_id and ev.recipient in (seat, "all")
        and (kinds is None or ev.kind in kinds)
    ]
    for ev in shown:
        ref = ev.candidate_id or ev.brief_id or "-"
        ssha = (ev.subject_sha or "")[:12] or "-"
        print(f"{ev.seq}\t{ev.kind}\t{ev.sender}\t{ref}\t{ssha}")
    if not a.no_advance:
        try:
            store.advance_cursor(seat, tip)             # local CAS; monotonic no-op for seq<=cur
        except (CursorContentionExceeded, CursorCorruptionError) as e:   # advance re-reads the cursor blob
            print(f"cursor advance failed for {seat}: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests — verify they PASS.**
  Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_consume_bus.py -q` → all green.

- [ ] **Step 5: Confirm the addressee-filter pin is NON-VACUOUS.** Temporarily delete `and ev.recipient in (seat, "all")`; rerun `test_addressee_filter_hides_directed_event` and confirm it goes RED; restore. (Don't commit the mutation.)

- [ ] **Step 6: Smoke + commit.**
  Run: `.venv/bin/python scripts/ci_smoke.py` → `OK`.
  ```bash
  env -u GIT_INDEX_FILE git add scripts/consume_bus.py tests/unit/test_threeway_consume_bus.py
  env -u GIT_INDEX_FILE git commit -m "feat(threeway): consume_bus — seat reads bus events past cursor [SP2 2a]" -- \
    scripts/consume_bus.py tests/unit/test_threeway_consume_bus.py
  ```

- [ ] **Step 7: Lane-V.** Dispatch a `lane-v-verifier` on this commit: re-derive GO/NITS/FAIL from the diff + a fresh test run; key claim = the addressee / `bus_id` / cursor mutations redden. Address NITS before proceeding.

---

## Chunk 2: Phase 2b — `seat_emit.py` (the shim's replacement)

### Task 2: seat_emit CLI + unit pins

**Files:**
- Create: `scripts/seat_emit.py`
- Test: `tests/unit/test_threeway_seat_emit.py`

Reference: spec §3.2 (authority table, provider lookup, event shapes, `--tier`, boundary) + §6 (pins) + §8 (authority classes → rc2+zero-event pins). Event-building pattern: `scripts/bootstrap_emit.py` `_candidate_set`/`_abort_event` (read it — present until 2d) and `threeway/loop.py:build_candidate_events`. **The one change vs the shim: `seat_emit` loads `load_private(<explicit seat arg>)`, validated against the authority table, NOT `load_private(ev.signer.split(":")[0])`.**

- [ ] **Step 1: Write the failing tests.** Copy `seatkit`/`live_repo`/`_git`/`_env` from `tests/unit/test_threeway_gate.py` (as in Task 1). Then:

```python
import contextlib
import io

from threeway.gate import verify_and_reduce
from threeway.refstore import RefEventStore


def _run(argv):
    from scripts.seat_emit import main
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


def test_operator_attestation_round_trips_and_verifies(seatkit, live_repo):
    reg, ks = seatkit
    r, base, branch = live_repo
    common = ["--candidate-id", "c1", "--pair", "A", "--staging-base", base, "--branch", branch,
              "--repo-dir", str(r), "--remote", ""]
    assert _run(["operator", "attestation", "--phase", "preliminary", *common])[0] == 0
    state = verify_and_reduce(RefEventStore(r).all_events(), registry_dir=str(reg), bus_id="prod")
    att = state.effective_attestation("A:c1", "preliminary", "operator")   # folded + sig-verified by the gate
    assert att is not None and att.payload["verdict"] == "GO" and att.subject_sha == branch


def test_authority_bypass_is_rc2_and_zero_new_events(seatkit, live_repo):
    reg, ks = seatkit
    r, base, branch = live_repo
    n0 = len(RefEventStore(r).all_events())
    rc, _, err = _run(["director", "attestation", "--phase", "preliminary", "--candidate-id", "c1",
                       "--pair", "A", "--staging-base", base, "--branch", branch,
                       "--repo-dir", str(r), "--remote", ""])
    assert rc == 2 and "may not emit" in err                               # static seat↔kind guard fires
    assert len(RefEventStore(r).all_events()) == n0                        # NOTHING appended (non-vacuous)


def test_release_requested_bypass_is_rc2_zero_events(seatkit, live_repo):
    # class-(3): the gate never reads release_requested; only seat_emit's guard matters.
    reg, ks = seatkit
    r, base, branch = live_repo
    n0 = len(RefEventStore(r).all_events())
    rc, _, _ = _run(["director", "release_requested", "--candidate-id", "c1", "--pair", "A",
                     "--staging-base", base, "--branch", branch, "--repo-dir", str(r), "--remote", ""])
    assert rc == 2 and len(RefEventStore(r).all_events()) == n0


def test_candidate_aborted_authoritative_fold(seatkit, live_repo):
    # MIGRATED from test_bootstrap_emit_candidate_aborted_is_authoritative
    reg, ks = seatkit
    r, base, branch = live_repo
    from scripts.overseer_emit import main as omain
    otail = ["--repo-dir", str(r), "--remote", "", "--bus-id", "prod"]
    assert omain(["assignment", "--candidate-id", "A:c1", "--pair", "A",
                  "--builder", "director", "--builder-provider", "codex",
                  "--primary-verifier", "operator", "--primary-verifier-provider", "claude",
                  "--executing-coordinator", "coordinator", *otail]) == 0
    assert _run(["coordinator", "candidate_aborted", "--candidate-id", "c1", "--pair", "A",
                 "--repo-dir", str(r), "--remote", ""])[0] == 0
    state = verify_and_reduce(RefEventStore(r).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.is_aborted("A:c1") is True


def test_candidate_aborted_namespaces_bare_id(seatkit, live_repo):
    # MIGRATED from test_bootstrap_emit_candidate_aborted_namespaces_bare_id
    reg, ks = seatkit
    r, *_ = live_repo
    _run(["coordinator", "candidate_aborted", "--candidate-id", "c9", "--pair", "A",
          "--repo-dir", str(r), "--remote", ""])
    aborts = [e for e in RefEventStore(r).all_events() if e.kind == "candidate_aborted"]
    assert aborts and aborts[-1].candidate_id == "A:c9"


def test_candidate_aborted_bad_repo_dir_exits_clean_rc1(seatkit, tmp_path):
    # MIGRATED error-path totality: a non-git repo-dir -> clean rc1, no traceback
    reg, ks = seatkit
    nope = tmp_path / "nope"; nope.mkdir()
    rc, _, err = _run(["coordinator", "candidate_aborted", "--candidate-id", "c1", "--pair", "A",
                       "--repo-dir", str(nope), "--remote", ""])
    assert rc == 1 and "Not emitted" in err


def test_unresolvable_ref_exits_clean_rc1(seatkit, live_repo):
    # MIGRATED error-path totality (candidate path): bad staging-base ref -> clean rc1
    reg, ks = seatkit
    r, base, branch = live_repo
    rc, _, err = _run(["coordinator", "candidate", "--candidate-id", "c1", "--pair", "A",
                       "--staging-base", "no-such-ref", "--branch", branch,
                       "--repo-dir", str(r), "--remote", ""])
    assert rc == 1 and "Not emitted" in err


def test_tier_sets_risk_tier_claimed(seatkit, live_repo):
    reg, ks = seatkit
    r, base, branch = live_repo
    _run(["coordinator", "candidate", "--candidate-id", "c1", "--pair", "A", "--tier", "T2",
          "--staging-base", base, "--branch", branch, "--repo-dir", str(r), "--remote", ""])
    cand = [e for e in RefEventStore(r).all_events() if e.kind == "candidate"][-1]
    assert cand.payload["risk_tier_claimed"] == "T2"


def test_coordinator2_candidate_round_trips_pair_b(seatkit, live_repo):
    # PAIR_B emission coverage (requires coordinator2 in the extended seatkit).
    reg, ks = seatkit
    r, base, branch = live_repo
    assert _run(["coordinator2", "candidate", "--candidate-id", "c1", "--pair", "B",
                 "--staging-base", base, "--branch", branch, "--repo-dir", str(r), "--remote", ""])[0] == 0
    state = verify_and_reduce(RefEventStore(r).all_events(), registry_dir=str(reg), bus_id="prod")
    cand = state.candidate("B:c1")
    assert cand is not None and cand.signer.split(":", 1)[0] == "coordinator2"
```

- [ ] **Step 2: Run the tests — verify they FAIL.**
  Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_seat_emit.py -q` → `ModuleNotFoundError: No module named 'scripts.seat_emit'`.

- [ ] **Step 3: Implement `scripts/seat_emit.py`.**

```python
#!/usr/bin/env python3
"""seat_emit.py — a real interactive seat signs ITS OWN T1 control-plane fact with ITS OWN key
(SP2 spec §3.2). Replaces scripts/bootstrap_emit.py. Static seat↔kind authority is enforced BEFORE
construction; the key is load_private(<explicit seat arg>), never derived from a caller-supplied
signer (the bootstrap_emit.py:50 injection hole)."""
import argparse
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:                      # ADR-055 self-bootstrap
    sys.path.insert(0, str(_REPO_ROOT))

from threeway import gitcas                              # noqa: E402
from threeway.envelope import Event                      # noqa: E402
from threeway.keys import load_private                   # noqa: E402
from threeway.loop import PAIR_A, PAIR_B, build_candidate_events  # noqa: E402
from threeway.refstore import AppendContentionExceeded, RefEventStore  # noqa: E402

SEATS = ("director", "director2", "operator", "operator2", "coordinator", "coordinator2")

# Static seat↔kind authority (T1 facts only; T2/T3 emission is a deferred follow-on).
AUTHORITY = {
    "coordinator":  {"candidate", "release_requested", "candidate_aborted"},
    "coordinator2": {"candidate", "release_requested", "candidate_aborted"},
    "operator":     {"attestation"},
    "operator2":    {"attestation"},
}
# The seat determines the pair (and thus the canonical event signer). No --pair-vs-seat conflict.
SEAT_PAIR = {"coordinator": PAIR_A, "operator": PAIR_A, "coordinator2": PAIR_B, "operator2": PAIR_B}
# provider derived from PairConfig (no operator_provider field — key on role).
PROVIDER = {}
for _p in (PAIR_A, PAIR_B):
    PROVIDER[_p.coordinator] = _p.coordinator_provider
    PROVIDER[_p.primary_verifier] = _p.verifier_provider


def _namespaced(pair, cid):
    return cid if ":" in cid else f"{pair.pair}:{cid}"


def _build_event(a) -> Event:
    """Build the seat's one fact, hard-binding the seat. Mirrors bootstrap_emit's shapes."""
    pair = SEAT_PAIR[a.seat]
    if a.fact == "candidate_aborted":
        cid = _namespaced(pair, a.candidate_id)
        ev = Event(
            id=f"candidate_aborted-{pair.coordinator}-{cid}", seq=0, bus_id=a.bus_id,
            schema_version="threeway/1", kind="candidate_aborted", sender=pair.coordinator,
            recipient="all", signer="", payload={"candidate_id": cid},
            brief_id=a.brief_id, brief_version=a.brief_version, candidate_id=cid,
        )
    else:
        repo = Path(a.repo_dir)
        base_sha = gitcas.rev_parse(repo, a.staging_base)
        branch_sha = gitcas.rev_parse(repo, a.branch)
        if base_sha is None:
            raise ValueError(f"cannot resolve staging-base ref {a.staging_base!r}")
        if branch_sha is None:
            raise ValueError(f"cannot resolve branch ref {a.branch!r}")
        cid = _namespaced(pair, a.candidate_id)
        tree, clean = gitcas.merge_tree(repo, base_sha, branch_sha)
        if not clean:
            raise ValueError("merge not clean — cannot compute integration_sha")
        integ = gitcas.commit_tree(repo, tree, [base_sha, branch_sha], f"threeway merge {cid}")
        events = build_candidate_events(base_sha, branch_sha, integ, {}, bus_id=a.bus_id,
                                        tier=a.tier, pair=pair, candidate_id=a.candidate_id)
        phase = getattr(a, "phase", None)
        ev = next((e for e in events
                   if e.kind == a.fact and (phase is None or e.payload.get("kind") == phase)), None)
        if ev is None:
            raise ValueError(f"builder produced no {a.fact}/{phase} event")
    # Hard-bind the seat identity into the (unsigned) signer tail; --session is audit-only. Event is a
    # mutable dataclass and `signer` is outside the 14-field signed view, so this does not affect the sig.
    ev.signer = f"{a.seat}:{PROVIDER[a.seat]}:{a.session}"
    assert ev.sender == a.seat, f"builder sender {ev.sender} != seat {a.seat}"   # authority-table invariant
    return ev


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A seat emits its own signed T1 bus fact.")
    ap.add_argument("seat", choices=SEATS)                # all 6 — body rejects non-emitters with rc2
    ap.add_argument("fact")
    ap.add_argument("--candidate-id", required=True)
    ap.add_argument("--pair", default="A", choices=["A", "B"])   # accepted for symmetry; SEAT_PAIR wins
    ap.add_argument("--staging-base", default=None)
    ap.add_argument("--branch", default=None)
    ap.add_argument("--tier", default="T1", choices=["T0", "T1", "T2", "T3"])
    ap.add_argument("--phase", default=None, choices=["preliminary", "release"])
    ap.add_argument("--brief-id", default="b1")
    ap.add_argument("--brief-version", type=int, default=1)
    ap.add_argument("--session", default=None)
    ap.add_argument("--bus-id", default="prod")
    ap.add_argument("--repo-dir", default=".")
    ap.add_argument("--remote", default="origin")
    a = ap.parse_args(argv)
    a.session = a.session or "s1"

    # AUTHORITY CHECK FIRST — before any PairConfig/build work, so a bad (seat,fact) is rc2 not a crash.
    if a.fact not in AUTHORITY.get(a.seat, set()):
        print(f"seat {a.seat} may not emit {a.fact}", file=sys.stderr)
        return 2
    if a.fact != "candidate_aborted" and (a.staging_base is None or a.branch is None):
        print(f"{a.fact} requires --staging-base and --branch", file=sys.stderr)
        return 2
    if a.fact == "attestation" and a.phase is None:
        print("attestation requires --phase preliminary|release", file=sys.stderr)
        return 2

    try:
        ev = _build_event(a)
        store = RefEventStore(Path(a.repo_dir), remote=(a.remote or None))
        store.append(ev, load_private(a.seat))           # <-- EXPLICIT seat key, not signer-derived
    except FileNotFoundError as e:
        print(f"Error loading seat key: {e}", file=sys.stderr); return 1
    except AppendContentionExceeded as e:
        print(f"Bus contention, not emitted: {e}", file=sys.stderr); return 1
    except ValueError as e:
        print(f"Not emitted: {e}", file=sys.stderr); return 1
    except subprocess.CalledProcessError as e:
        print(f"Not emitted: git failed ({e})", file=sys.stderr); return 1
    print(f"Emitted {ev.kind}{'/' + a.phase if a.phase else ''} for {ev.candidate_id} (seq {ev.seq}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests — verify they PASS.**
  Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_seat_emit.py -q` → all green.

- [ ] **Step 5: Confirm the authority-bypass pin is NON-VACUOUS.** The `rc == 2` assertion is the real detector: temporarily delete the `if a.fact not in AUTHORITY…: return 2` guard and rerun `test_authority_bypass_is_rc2_and_zero_new_events`. It goes RED because the `director` path then reaches `SEAT_PAIR["director"]` — a `KeyError` (the guard is what stops an unauthorized seat from reaching the build) — so the test ERRORS instead of returning rc2. **The zero-event count is a belt-and-suspenders invariant only** — it holds either way for `director` (the crash also appends nothing), so do NOT treat the count alone as the proof. Restore the guard.

- [ ] **Step 6: Smoke + commit.**
  Run: `.venv/bin/python scripts/ci_smoke.py` → `OK`.
  ```bash
  env -u GIT_INDEX_FILE git add scripts/seat_emit.py tests/unit/test_threeway_seat_emit.py
  env -u GIT_INDEX_FILE git commit -m "feat(threeway): seat_emit — per-seat signed T1 emission, key-injection closed [SP2 2b]" -- \
    scripts/seat_emit.py tests/unit/test_threeway_seat_emit.py
  ```

- [ ] **Step 7: Lane-V (key-binding mutation is the core proof).** Dispatch a `lane-v-verifier`. KEY non-vacuity check: mutate `store.append(ev, load_private(a.seat))` → `load_private("director")` (a wrong, unauthorized key) and confirm `test_operator_attestation_round_trips_and_verifies` goes RED (the gate drops the wrong-key-signed event → `effective_attestation` returns None) — this proves the explicit-seat key binding is load-bearing and closes the injection hole. Also confirm the rc2+zero-event pins are non-vacuous. Address NITS.

---

## Chunk 3: Phase 2c — E2E walking skeleton (modify in place)

### Task 3: Swap the E2E to seat_emit + consume_bus

**Files:**
- Modify: `tests/unit/test_threeway_e2e_walking_skeleton.py` (already has its own `seatkit`/`live_repo`)

Reference: spec §3.3 (modify in place; exact consume_bus assertion; CI ordering) + §4 (data flow).

- [ ] **Step 1: Read the existing E2E** and locate every `bootstrap_emit` invocation (overseer facts come from `overseer_emit`; CI from `sign_ci_result`; the gate from `run_merge_gate`/`run_gate`).

- [ ] **Step 2: Replace the four `bootstrap_emit` calls with `seat_emit`, using the file's existing `_run(script, *args, repo, ks)` helper** (it sets `THREEWAY_KEYSTORE`, strips `PYTHONPATH`, and asserts rc==0 — so a seat_emit failure surfaces at the call site). The existing `B` flag list is reused as-is:
  - `_run("bootstrap_emit.py", "candidate", *B, repo=r, ks=ks)` → `_run("seat_emit.py", "coordinator", "candidate", *B, repo=r, ks=ks)`
  - `…"attestation", "--phase", "preliminary", *B…` → `_run("seat_emit.py", "operator", "attestation", "--phase", "preliminary", *B, repo=r, ks=ks)`
  - `…"attestation", "--phase", "release", *B…` → `_run("seat_emit.py", "operator", "attestation", "--phase", "release", *B, repo=r, ks=ks)`
  - `…"release_requested", *B…` → `_run("seat_emit.py", "coordinator", "release_requested", *B, repo=r, ks=ks)`
  Keep the existing overseer/CI/gate `_run(...)` calls unchanged.

- [ ] **Step 3: Add the exact consume_bus assertion** (after the `merge_completed` assertion in `test_t1_brief_to_merge_walking_skeleton`), via the same `_run` helper:

```python
    proc = _run("consume_bus.py", "coordinator", "--repo-dir", str(r), "--remote", "", repo=r, ks=ks)
    kinds = sorted(line.split("\t")[1] for line in proc.stdout.splitlines() if line.strip())
    assert kinds == sorted([
        "brief", "assignment", "cycle_go", "candidate", "attestation", "attestation",
        "ci_result", "release_requested", "release_order", "merge_completed",
    ])
    n = len(RefEventStore(r).all_events())
    assert RefEventStore(r).cursor_seq("coordinator") == n          # advanced to the snapshot tip
    _run("consume_bus.py", "operator", "--repo-dir", str(r), "--remote", "", repo=r, ks=ks)
    assert RefEventStore(r).cursor_seq("operator") == n             # a second seat also advances
```

  Do NOT assert all six seats (identical, since all-broadcast — brittle).

- [ ] **Step 4: ADD a new negative-path test** (spec §6 — there is NO existing negative test to "retain"; the file has one test function today). A second test function runs the same flow but OMITS the release attestation, then asserts the gate does NOT complete:

```python
def test_missing_release_attestation_stays_pending(seatkit, live_repo):
    reg, ks, privs = seatkit
    r, base, branch = live_repo
    cid = "A:c1"; pd = default_policy().policy_digest()
    tree, clean = gitcas.merge_tree(r, base, branch)
    integ = gitcas.commit_tree(r, tree, [base, branch], f"threeway merge {cid}")
    L = ["--repo-dir", str(r), "--remote", ""]
    B = ["--candidate-id", cid, "--pair", "A", "--staging-base", base, "--branch", branch, *L]
    _run("overseer_emit.py", "brief", "--candidate-id", cid, "--brief-id", "b1",
         "--assigned-tier", "T1", "--allowed-paths", "cinema/", *L, repo=r, ks=ks)
    _run("overseer_emit.py", "assignment", "--candidate-id", cid, "--pair", "A",
         "--builder", "director", "--builder-provider", "codex",
         "--primary-verifier", "operator", "--primary-verifier-provider", "claude",
         "--executing-coordinator", "coordinator", *L, repo=r, ks=ks)
    _run("overseer_emit.py", "cycle_go", "--candidate-id", cid, "--brief-id", "b1",
         "--tier", "T1", "--policy-digest", pd, *L, repo=r, ks=ks)
    _run("seat_emit.py", "coordinator", "candidate", *B, repo=r, ks=ks)
    _run("seat_emit.py", "operator", "attestation", "--phase", "preliminary", *B, repo=r, ks=ks)
    _run("sign_ci_result.py", "--integration-sha", integ, "--result", "PASS", "--repo-dir", str(r), repo=r, ks=ks)
    # NB: NO release attestation emitted.
    _run("seat_emit.py", "coordinator", "release_requested", *B, repo=r, ks=ks)
    _run("overseer_emit.py", "release_order", "--candidate-id", cid, "--integration-sha", integ, *L, repo=r, ks=ks)
    _run("run_merge_gate.py", "--repo-dir", str(r), "--registry-dir", str(reg),
         "--bus-id", "prod", "--main-ref", "refs/threeway/test-main", "--run-once", repo=r, ks=ks)
    state = verify_and_reduce(RefEventStore(r).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.merge_completed(cid) is None                       # gate PENDING, not COMPLETED
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == base   # ref did NOT advance
```

- [ ] **Step 5: Run the E2E — verify it PASSES.**
  Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_e2e_walking_skeleton.py -q` → green. Confirm `grep -n bootstrap_emit tests/unit/test_threeway_e2e_walking_skeleton.py` → empty.

- [ ] **Step 6: Smoke + commit.**
  Run: `.venv/bin/python scripts/ci_smoke.py` → `OK`.
  ```bash
  env -u GIT_INDEX_FILE git add tests/unit/test_threeway_e2e_walking_skeleton.py
  env -u GIT_INDEX_FILE git commit -m "test(threeway): E2E walking-skeleton runs on seat_emit+consume_bus, no bootstrap_emit [SP2 2c]" -- \
    tests/unit/test_threeway_e2e_walking_skeleton.py
  ```

- [ ] **Step 7: Lane-V.** Key claim = the E2E proves `seat_emit` ≡ the shim's T1 facts (full brief→merge merges with no `bootstrap_emit`), and the consume_bus assertion is exact (not rc0-only).

---

## Chunk 4: Phase 2d — retire `bootstrap_emit.py`

### Task 4: Delete the shim + its orphaned test; repoint the activation pin; doc-sync

**Files:**
- Delete: `scripts/bootstrap_emit.py`, `tests/unit/test_threeway_bootstrap_emit.py`
- Modify: `tests/unit/test_threeway_activation_scripts.py` (`_ACTIVATION_SCRIPTS`)
- Modify: `ARCHITECTURE.md`, `DECISIONS.md`, and the SP1 spec's "Deferred → sub-project 2" note

Reference: spec §3.4. ONE atomic commit so no pin goes RED on a missing script without a green replacement.

- [ ] **Step 1: Repoint the activation pin.** In `tests/unit/test_threeway_activation_scripts.py`, replace the `bootstrap_emit.py` entry in `_ACTIVATION_SCRIPTS` with `consume_bus.py` and `seat_emit.py`, each invoked with `--help` (exactly matching the existing entries — `tests/unit/test_threeway_activation_scripts.py:231`).

- [ ] **Step 2: Run the activation pin — verify it PASSES.**
  Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_activation_scripts.py -q` → green.

- [ ] **Step 3: Delete the shim + its test.**
  ```bash
  env -u GIT_INDEX_FILE git rm scripts/bootstrap_emit.py tests/unit/test_threeway_bootstrap_emit.py
  ```

- [ ] **Step 4: Grep-confirm no survivors.**
  Run: `git grep -n "bootstrap_emit" -- '*.py'` → empty (no live import or call). `git grep -n "bootstrap_emit" -- '*.md'` → only historical doc mentions under `docs/superpowers/` may remain.

- [ ] **Step 5: Doc-sync + ADR.** Add a `DECISIONS.md` ADR (next number) marking `bootstrap_emit.py` retired and `consume_bus`/`seat_emit` as the live seat↔bus path; update the relevant `ARCHITECTURE.md` line(s); flip the SP1 spec's "Deferred → sub-project 2" note to DONE. `ARCHITECTURE.md` is a hard doc-anchor gate — fix any drift in this commit.

- [ ] **Step 6: Full suite + smoke.**
  Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/ -q` → green (the "full threeway suite green" gate; confirms no orphaned `bootstrap_emit` import breaks collection).
  Run: `.venv/bin/python scripts/ci_smoke.py` → `OK`; `.venv/bin/python scripts/check_no_ceremony.py` (if present) → clean.

- [ ] **Step 7: Commit (atomic).**
  ```bash
  env -u GIT_INDEX_FILE git add tests/unit/test_threeway_activation_scripts.py DECISIONS.md ARCHITECTURE.md \
    docs/superpowers/specs/2026-06-22-threeway-scope-b-mechanical-seat-runtime-design.md
  env -u GIT_INDEX_FILE git commit -m "refactor(threeway): retire bootstrap_emit shim — seat_emit+consume_bus are the live path [SP2 2d]" -- \
    scripts/bootstrap_emit.py tests/unit/test_threeway_bootstrap_emit.py tests/unit/test_threeway_activation_scripts.py \
    DECISIONS.md ARCHITECTURE.md docs/superpowers/specs/2026-06-22-threeway-scope-b-mechanical-seat-runtime-design.md
  ```
  (The `git rm` already staged the two deletions; the explicit pathspec includes them so deletion + repoint + docs land together.)

- [ ] **Step 8: Lane-V (final).** Key claims = (a) `git grep bootstrap_emit -- '*.py'` shows no live importer/caller; (b) the full suite is green with the shim gone; (c) the activation pin covers both new CLIs. On GO, SP2 is complete.

---

## Done criteria (whole plan)

All four phase commits landed + Lane-V GO; `consume_bus` + `seat_emit` are the live seat↔bus path; `bootstrap_emit.py` and its test are gone with coverage migrated; the E2E proves T1 brief→merge with no shim; `ci_smoke` + `check_no_ceremony` clean; full threeway suite green. T2/T3 emission (`attestation_revoked`/`co_sign`/`re_verify`) remains a deferred follow-on (spec §7).
