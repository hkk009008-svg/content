# Threeway scope-b sub-project 1 — Minimal Operable Mechanical-Seat Runtime — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. Per the user's standing directive (2026-06-21), every Agent/subagent dispatch defaults to `model: 'sonnet'`; escalate a specific task to `model: 'opus'` **only after asking the user** (Opus is opt-in per task).

**Goal:** Make the three mechanical seats (`overseer`, `ci`, `merge-gate`) into operable processes so one T1 candidate can flow brief→merge end-to-end, driven by a human operator, against the protected **test** ref `refs/threeway/test-main` (never real `main`).

**Architecture:** Two new human-operated signing CLIs — `scripts/overseer_emit.py` (the overseer authority, 6 fact kinds) and `scripts/bootstrap_emit.py` (a clearly-temporary shim for the interactive seats' facts) — plus a hardened standing daemon (`scripts/run_merge_gate.py` + a thin `scripts/run_merge_gate.sh` wrapper). Each CLI mirrors the proven `scripts/sign_ci_result.py` template: construct an `Event` (seq=0), then `RefEventStore.append(ev, private_key)` (which assigns the seq AND signs — the CLI never pre-signs). The CI signer is already operable (ADR-055); this slice only verifies it stays green and folds the two new scripts into its bare-subprocess pin. An end-to-end walking-skeleton test drives the real CLIs as subprocesses + the daemon (`--run-once`) and asserts `refs/threeway/test-main` advances and `merge_completed` is emitted.

**Tech Stack:** Python 3, pytest. Signed event-sourced bus (`threeway/`), Ed25519 + RFC 8785 JCS canonicalization. **Run threeway tests with the mandatory `env -u GIT_INDEX_FILE` prefix** (per-seat index pollution; CLAUDE.md "Git-tooling sharp edges"). Acceptance gates: `.venv/bin/python scripts/ci_smoke.py` and `.venv/bin/python scripts/check_no_ceremony.py`.

**Spec:** [`docs/superpowers/specs/2026-06-22-threeway-scope-b-mechanical-seat-runtime-design.md`](../specs/2026-06-22-threeway-scope-b-mechanical-seat-runtime-design.md). Baseline HEAD = `e45f2cf6` (ADR-055). This plan's anchors were re-derived against HEAD `84397381` by workflow `wf_1fe17b9e-bc7` (5 verifiers, file:line evidence); §"Verified anchors" below records them.

**Scope guard (campaign discipline):** This is sub-project 1 of scope-b. **OUT of scope:** real seat↔bus wiring (sub-project 2), any promotion of real `refs/heads/main`, all §7 hardening-track items (CI attestor, per-principal approver keys, external trust anchor, ref-ACL enforcement, liveness/recovery, key rotation, richer attestations), and the §7 **automation track** `overseer-plan` auto-decompose layer (a fast-follow ABOVE `overseer_emit` that turns one structured chief decision + bus state into the ordered emit sequence — landed in the spec by peer `42ab8001`; this plan builds the *manual* `overseer_emit` foundation it will later sit on). Do not build them here. If a task tempts scope creep, stop and flag it.

---

## Carried threat-model framing (spec §8 — do NOT re-litigate)

- **Fault model (review B5):** within a pair the verifier and integrator share a provider, so the independent third party is **the mechanical gate + overseer + CI**, NOT a third provider. A single compromised provider cannot merge alone.
- **`integration_sha` is a deterministic COMMIT OID (review B2):** the gate recomputes it (`gate.py:204-208`) and equality-checks it; byte-reproducible via `_DET_ENV` (`gitcas.py:14-21`) + ADR-048 merge `-c` flags. Unclean merges are hard-REJECTED.
- **Exact T2/T3 signer seats (review I4):** unchanged by this slice — the walking-skeleton is **T1** (no co_sign, no re_verify, no human_approval). The `overseer_emit` `approver_roster` / `re_verify_challenge` subcommands are built + unit-pinned but not exercised in the T1 E2E.
- **`required_ci` (review I3):** advisory/unwired; do not wire it here.

---

## Design decisions (record as **ADR-056** in the docs task)

These five decisions resolve drift/tension the verification pass found between the spec and the code at HEAD. Each is the faithful reading of the spec's *intent*; DD-1 strengthens a safety boundary and must be flagged for ratification.

**DD-1 — merge-gate daemon defaults to the TEST ref (safety-critical).**
`scripts/run_merge_gate.py` currently sets `--main-ref` **default `refs/heads/main`** (verified, run_merge_gate.py:56), which *overrides* the safe library default `predicate.MAIN_REF = "refs/threeway/test-main"` (predicate.py:26) and `evaluate(..., main_ref=MAIN_REF)` (predicate.py:39). The spec's safety boundary (§3.2: "the minimal daemon writes the protected TEST ref … NOT `refs/heads/main`; a daemon bug therefore cannot corrupt real main") only holds if the wrapper passes the flag — a bare `python scripts/run_merge_gate.py` would target real `main`. **Resolution:** (a) change the daemon default to `refs/threeway/test-main`; (b) the wrapper passes `--main-ref refs/threeway/test-main` explicitly anyway (belt-and-suspenders); (c) a guard test asserts both. Real-`main` promotion stays in the hardening track. **Flag this default change for user/coordinator ratification** — it changes an existing CLI's behavior.

**DD-2 — the wrapper does NOT export PYTHONPATH.**
Spec §3.2 says the wrapper "exports PYTHONPATH (repo root)", but §3.3 and ADR-055 (verified: run_merge_gate.py:19-21 self-bootstraps `sys.path`) make that unnecessary and fragile. **Resolution:** the wrapper relies on the script's self-bootstrap; it sets no PYTHONPATH. This resolves the internal spec contradiction in favor of §3.3.

**DD-3 — add `--remote` to the daemon so it can poll the live bus.**
`run_merge_gate.py` has NO `--remote` arg; it builds `RefEventStore(Path(args.repo_dir))` in **local** mode, so it would never observe origin events — making §4-step-5 ("daemon polls the live bus") hollow. **Resolution:** add `--remote` (default `None`) to `run_merge_gate.py`, thread it into `RefEventStore(..., remote=args.remote)`; the wrapper passes `--remote origin` for live deployment; the walking-skeleton E2E uses local mode (no remote).

**DD-4 — CLI `--remote` default + clean contention exit.**
`overseer_emit.py` defaults `--remote origin` (spec §3.1), a deliberate departure from the `sign_ci_result.py` template (default `None`). Treat empty string as local: `remote = args.remote or None` (lets the E2E temp-repo pass `--remote ""`). Both new CLIs catch `AppendContentionExceeded` → clean `exit 1` with a message (spec §5; the template lets it traceback).

**DD-5 — signing is `store.append`'s job; never pre-sign.**
The CLI constructs the `Event` with `seq=0` and calls `store.append(ev, private_key)`, which allocates the real seq then signs over it (refstore.py:154-155). Calling `sign_event` first would produce a stale signature over `seq=0`. (This is a *code* invariant, not a doc; it shapes every emit helper.)

---

## Verified anchors (re-derived at HEAD `84397381`; do NOT re-derive)

**Overseer fact shapes** — payload dict vs envelope kwargs (the boundary that, if wrong, makes the reducer/predicate *silently* drop the fact):

| Fact | payload keys | envelope kwargs (beyond defaults) | signer seat | builder ref |
|---|---|---|---|---|
| `brief` | `brief_id, assigned_tier, allowed_paths[]` | `brief_id`, `candidate_id`; `brief_version` is the envelope default (1) | `overseer` | loop.py:80-82 |
| `assignment` | `pair, builder, builder_provider, primary_verifier, primary_verifier_provider, executing_coordinator` | `candidate_id` | `overseer` | loop.py:83-88 |
| `cycle_go` | `brief_id, brief_version, tier, policy_digest` | `candidate_id` (brief_version in BOTH payload & envelope) | `overseer` | loop.py:101-103 |
| `release_order` | `candidate_id` only | **`subject_sha`=integration_sha** (predicate reads `ro.subject_sha`, predicate.py:142) | `overseer` | loop.py:109-110 |
| `approver_roster` | `approvers: [seats]` | `candidate_id` | `overseer` | tier.py:154, reducer.py:367-371 |
| `re_verify_challenge` | `nonce` | **`subject_sha`=integration_sha** | `overseer` | tier.py:129/131, reducer.py:357-362 |

**Seat fact shapes** (bootstrap_emit) — `candidate`/`release_requested` are signed by the pair **coordinator**; both attestations by the pair **primary_verifier**:

| Fact | payload keys | envelope kwargs | id (must be unique) | signer seat (Pair A) |
|---|---|---|---|---|
| `candidate` | `pair, staging_base_sha, branch_sha, integration_sha, risk_tier_claimed, policy_digest` | `subject_sha`=integration_sha | `candidate-{coord}-{cid}` | `coordinator` |
| `attestation` (preliminary) | `kind:"preliminary", verdict:"GO"` | `subject_sha`=**branch_sha** | `attestation-preliminary-{verifier}-{cid}` | `operator` |
| `attestation` (release) | `kind:"release", verdict:"GO"` | `subject_sha`=integration_sha | `attestation-release-{verifier}-{cid}` | `operator` |
| `release_requested` | `candidate_id` | `subject_sha`=integration_sha | `release_requested-{coord}-{cid}` | `coordinator` |

> **ID-uniqueness invariant (loop.py:112-117):** `RefEventStore` keys the tree path on `events/<brief_id>/<id>.json` with **no seq prefix** — a duplicate id silently OVERWRITES a prior blob. Every emitted event must have a unique id. The two attestations therefore carry their sub-kind in the id.

**Event constructor** (envelope.py:37-56) — 9 required positional fields `id, seq, bus_id, schema_version, kind, sender, recipient, signer, payload`; then optional `brief_id, candidate_id, subject_sha, brief_version, …`. `sender` serializes as `"from"`, `recipient` as `"to"`. Default `signature_version="threeway-sign/2"`.

**The proven template** (`scripts/sign_ci_result.py`):
- sys.path bootstrap (ADR-055): lines 19-22 — `_REPO_ROOT = Path(__file__).resolve().parent.parent; if str(_REPO_ROOT) not in sys.path: sys.path.insert(0, str(_REPO_ROOT))`.
- `load_private(seat) -> Ed25519PrivateKey` (keys.py:69-74; raises `FileNotFoundError` if absent; reads `$THREEWAY_KEYSTORE` or `~/.threeway/keys/<seat>.ed25519`).
- `RefEventStore(repo, remote=None, …)` (refstore.py:92); `.append(ev, private_key)` assigns seq + signs (refstore.py:133-183); `AppendContentionExceeded` (refstore.py:52, message `append lost CAS {n}x for {id}`); idempotent no-op when `idempotency_key` + fingerprint match.
- `verify_event(ev, public_key_hex)` (envelope.py:114) + `PublicKeyRegistry(registry_dir).get(seat)` (keys.py:80) for round-trip pins.
- `gate.verify_and_reduce(events, registry_dir, bus_id, gate_seat="merge-gate")` (gate.py:38); `reduce(events)` (no signing) for pure-logic pins.

**Test harness** (all fixtures are FILE-LOCAL — there is **no** threeway `conftest.py`):
- `seatkit` fixture (copy from test_threeway_gate.py:17-34): generates per-seat keypairs, writes `<seat>.pub` to a registry dir + hex private key to a keystore dir, `monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks))`, returns `(reg, ks, privs)`. Seats include `overseer, ci, merge-gate, coordinator, operator, …`.
- `live_repo` fixture (copy from test_threeway_gate.py:192-206): temp repo, commits `base.txt`, `update-ref refs/threeway/test-main`, branches `feat`, commits `cinema/foo.py`; returns `(r, base, branch)`.
- `_git(repo, *args)` helper: `subprocess.run(["git","-C",str(repo),*a], check=True, capture_output=True, text=True, env=<os.environ minus GIT_INDEX_FILE>)`.
- Build a full signed set: `for ev in build_candidate_events(base, branch, integ, {}): store.append(ev, privs[ev.signer.split(":",1)[0]])`.
- Compute a real integ: `tree,clean = gitcas.merge_tree(r, base, branch); integ = gitcas.commit_tree(r, tree, [base, branch], f"threeway merge {cid}")`.
- Bare-subprocess pin (test_threeway_activation_scripts.py:211-235): `_ACTIVATION_SCRIPTS` list + `_bare_env()` (strips `GIT_INDEX_FILE` and `PYTHONPATH`) + `subprocess.run([sys.executable, f"scripts/{script}", "--help"], cwd=_REPO_ROOT, env=_bare_env())`; asserts `"ModuleNotFoundError" not in proc.stderr` and `returncode == 0`.
- `poll_once(store, repo=r, registry_dir=reg, bus_id="prod", main_ref="refs/threeway/test-main")` returns **`list[tuple[str, GateResult]]`** (sorted by candidate_id; run_merge_gate.py:40-48) — iterate `for cid, res in poll_once(...)`, NOT as a dict (imported `from scripts.run_merge_gate import poll_once`).
- EffectiveState accessors (reducer.py, all verified): `brief(brief_id, version)` :94, `assignment(pair)` :180, `cycle_go(brief_id, version)` :106, `release_order(candidate_id)` :109, `candidate(candidate_id)` :118, `ci_result(subject_sha)` :115, `merge_completed(candidate_id)` :186, `approver_roster(candidate_id)` :213, `re_verify_challenge(candidate_id)` :205, `human_approvals(candidate_id)` :201, `release_requested(candidate_id)` :112, `effective_attestation(candidate_id, att_kind, seat)` :85 — **all are METHODS (call with the candidate_id), and `effective_attestation` returns a raw `Event` (verdict is `ev.payload["verdict"]`, SHA is `ev.subject_sha` — there is NO `.verdict`/`.event` attribute).**
- Helpers: `keys.private_to_hex(priv)` (keys.py:45), `keys.PublicKeyRegistry(dir).get(seat)` (keys.py:77/83), `keys.load_private(seat)` (keys.py:69), `keys.generate_keypair()` (keys.py:25); `gitcas.rev_parse(repo, ref) -> str | None` (gitcas.py:39 — **returns None on an unresolvable ref; guard it**), `gitcas.merge_tree(repo, base_sha, branch_sha) -> (tree, clean)` (gitcas.py:56), `gitcas.commit_tree(repo, tree_oid, parents, message)` (gitcas.py:80).

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `scripts/overseer_emit.py` | overseer signing CLI; 6 subcommands, one per overseer fact kind | **Create** |
| `scripts/bootstrap_emit.py` | TEMPORARY shim; emits the interactive seats' facts (candidate/attestation/release_requested) | **Create** |
| `scripts/run_merge_gate.py` | merge-gate daemon | **Modify**: safer `--main-ref` default (DD-1), add `--remote` (DD-3), SIGTERM/SIGINT clean-shutdown + stop-flag |
| `scripts/run_merge_gate.sh` | thin daemon wrapper | **Create** |
| `tests/unit/test_threeway_overseer_emit.py` | overseer CLI round-trip + mutation pins | **Create** |
| `tests/unit/test_threeway_bootstrap_emit.py` | shim CLI round-trip pins | **Create** |
| `tests/unit/test_threeway_merge_gate_daemon.py` | daemon default/remote/shutdown pins + wrapper guard | **Create** |
| `tests/unit/test_threeway_activation_scripts.py` | add the two new scripts to the bare-subprocess pin | **Modify** |
| `tests/integration/test_threeway_e2e_walking_skeleton.py` | full T1 brief→merge via subprocesses + daemon | **Create** |
| `DECISIONS.md` | ADR-056 (DD-1..DD-5) | **Modify** (append; never edit prior ADRs) |
| `ARCHITECTURE.md` | record the operable runtime + the 3 new scripts | **Modify** |
| `docs/superpowers/specs/2026-06-22-…-design.md` | fix the two stale anchors found (re_verify fold 357-362; sys.path 19-22) | **Modify** |

> **Lock discipline:** the only *shared* file is `scripts/run_merge_gate.py` (Chunk 3) and `tests/unit/test_threeway_activation_scripts.py` (Chunk 4). All other files are new. If peers are active on the tree, `coordination/bin/claim-lock W?-run_merge_gate.py.lock` before Chunk 3's edits and release on the GO commit. Re-anchor (`git fetch`; ahead/behind) before every commit/push.

---

## Chunk 1: overseer_emit.py — the overseer authority CLI

### Task 1: Scaffold + shared emit helper + the `brief` subcommand

**Files:**
- Create: `scripts/overseer_emit.py`
- Test: `tests/unit/test_threeway_overseer_emit.py`

- [ ] **Step 1 (RED): write the `brief` round-trip + mutation pins.** Copy `seatkit` (test_threeway_gate.py:17-34) and a `_new_repo` helper (test_threeway_loop.py:22-31) into the new test file. Drive the CLI **in-process** via `from scripts.overseer_emit import main`.

```python
import os, subprocess, sys
from pathlib import Path
import pytest
from threeway import keys
from threeway.envelope import verify_event
from threeway.gate import verify_and_reduce
from threeway.refstore import RefEventStore
# ... copy seatkit fixture + _git + _new_repo helpers here ...

def _events(repo):
    return RefEventStore(Path(repo)).all_events()

def test_brief_round_trips_authority_correct(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main
    rc = main(["brief", "--candidate-id", "A:c1", "--brief-id", "b1",
               "--assigned-tier", "T1", "--allowed-paths", "cinema/",
               "--repo-dir", str(repo), "--remote", ""])
    assert rc == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    bf = state.brief("b1", 1)
    assert bf is not None
    assert bf.signer.split(":", 1)[0] == "overseer"
    assert bf.payload["assigned_tier"] == "T1"
    assert bf.payload["allowed_paths"] == ["cinema/"]
    assert "brief_version" not in bf.payload          # envelope-only (spec §3.1)
    verify_event(bf, keys.PublicKeyRegistry(str(reg)).get("overseer"))  # signature valid

def test_brief_signed_with_nonoverseer_key_is_dropped(seatkit, tmp_path, monkeypatch):
    # MUTATION: if the CLI loaded the wrong seat key, verify_and_reduce drops the fact.
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    # Point load_private("overseer") at the OPERATOR key by overwriting the keystore file.
    (ks / "overseer.ed25519").write_text(keys.private_to_hex(privs["operator"]) + "\n")
    from scripts.overseer_emit import main
    main(["brief", "--candidate-id", "A:c1", "--brief-id", "b1",
          "--assigned-tier", "T1", "--allowed-paths", "cinema/",
          "--repo-dir", str(repo), "--remote", ""])
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    assert state.brief("b1", 1) is None   # signature mismatch vs registry "overseer" pubkey → dropped
```

- [ ] **Step 2: run → FAIL** (`ModuleNotFoundError: scripts.overseer_emit`).
Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_overseer_emit.py -q`

- [ ] **Step 3 (GREEN): write `scripts/overseer_emit.py` scaffold + `brief`.** Mirror the `sign_ci_result.py` template exactly (sys.path bootstrap, imports, `seq=0`, append-signs).

```python
#!/usr/bin/env python3
"""overseer_emit.py — human-operated overseer signing CLI (threeway scope-b sub-project 1).

Emits each overseer-authority fact (brief/assignment/cycle_go/release_order/
approver_roster/re_verify_challenge) signed with the OVERSEER key only. Mirrors the
payload/envelope shapes built by threeway.loop.build_candidate_events (the implicit
spec — a wrong key name makes the reducer/predicate silently drop the fact).
"""
import argparse
import secrets
import sys
from pathlib import Path

# ADR-055: bare `python scripts/overseer_emit.py` puts scripts/ (not the repo root) on
# sys.path[0]; put the repo root first so `import threeway` resolves.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from threeway.envelope import Event
from threeway.keys import load_private
from threeway.refstore import AppendContentionExceeded, RefEventStore

BUS = "prod"
OVERSEER_SIGNER = "overseer:mech:cli"   # seat MUST be "overseer"; signed with the overseer key


def _emit(repo_dir, remote, ev: Event) -> Event:
    """Append+sign ev with the overseer key. seq=0 in; store assigns seq then signs."""
    private_key = load_private("overseer")            # overseer key ONLY
    store = RefEventStore(Path(repo_dir), remote=(remote or None))
    return store.append(ev, private_key)              # DD-5: never pre-sign


def _build_event(kind, payload, candidate_id, *, brief_id="b1", brief_version=1,
                 subject_sha=None, bus_id=BUS, ev_id=None) -> Event:
    return Event(
        id=ev_id or f"{kind}-overseer-{candidate_id}", seq=0, bus_id=bus_id,
        schema_version="threeway/1", kind=kind, sender="overseer", recipient="all",
        signer=OVERSEER_SIGNER, payload=payload, brief_id=brief_id,
        brief_version=brief_version, candidate_id=candidate_id, subject_sha=subject_sha,
    )


def _cmd_brief(a) -> Event:
    payload = {"brief_id": a.brief_id, "assigned_tier": a.assigned_tier,
               "allowed_paths": list(a.allowed_paths)}
    return _build_event("brief", payload, a.candidate_id, brief_id=a.brief_id,
                        brief_version=a.brief_version, bus_id=a.bus_id)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Threeway overseer signing CLI.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _common(p):
        p.add_argument("--candidate-id", required=True, help="full pair-namespaced id, e.g. A:c1")
        p.add_argument("--bus-id", default=BUS)
        p.add_argument("--repo-dir", default=".")
        p.add_argument("--remote", default="origin", help='"" or "none" = local mode')  # DD-4

    pb = sub.add_parser("brief"); _common(pb)
    pb.add_argument("--brief-id", default="b1")
    pb.add_argument("--brief-version", type=int, default=1)
    pb.add_argument("--assigned-tier", required=True, choices=["T0", "T1", "T2", "T3"])
    pb.add_argument("--allowed-paths", nargs="+", required=True)
    pb.set_defaults(fn=_cmd_brief)

    args = ap.parse_args(argv)
    if (args.remote or "").lower() in ("", "none"):
        args.remote = None
    try:
        ev = _emit(args.repo_dir, args.remote, args.fn(args))
    except FileNotFoundError as e:
        print(f"Error loading overseer key: {e}", file=sys.stderr); return 1
    except AppendContentionExceeded as e:
        print(f"Bus contention, not emitted: {e}", file=sys.stderr); return 1   # DD-4
    print(f"Emitted {ev.kind} for {ev.candidate_id} (seq {ev.seq}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: run → PASS** both `brief` tests.
Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_overseer_emit.py -q`

- [ ] **Step 5: Commit.**
```bash
git add scripts/overseer_emit.py tests/unit/test_threeway_overseer_emit.py
env -u GIT_INDEX_FILE git commit -m "feat(threeway): overseer_emit CLI scaffold + brief subcommand [ADR-056]"
```

### Task 2: `assignment` and `cycle_go` subcommands

**Files:** Modify `scripts/overseer_emit.py`; Test `tests/unit/test_threeway_overseer_emit.py`.

- [ ] **Step 1 (RED):** add round-trip pins.
```python
def test_assignment_round_trips(seatkit, tmp_path):
    reg, ks, privs = seatkit; repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main
    assert main(["assignment", "--candidate-id", "A:c1", "--pair", "A",
                 "--builder", "director", "--builder-provider", "codex",
                 "--primary-verifier", "operator", "--primary-verifier-provider", "claude",
                 "--executing-coordinator", "coordinator",
                 "--repo-dir", str(repo), "--remote", ""]) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    a = state.assignment("A")
    assert a is not None and a.signer.split(":", 1)[0] == "overseer"
    assert a.payload["builder_provider"] == "codex"
    assert a.payload["primary_verifier_provider"] == "claude"
    assert a.payload["executing_coordinator"] == "coordinator"

def test_cycle_go_round_trips(seatkit, tmp_path):
    reg, ks, privs = seatkit; repo = _new_repo(tmp_path)
    from threeway.policy import default_policy
    from scripts.overseer_emit import main
    pd = default_policy().policy_digest()
    assert main(["cycle_go", "--candidate-id", "A:c1", "--brief-id", "b1",
                 "--brief-version", "1", "--tier", "T1", "--policy-digest", pd,
                 "--repo-dir", str(repo), "--remote", ""]) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    cg = state.cycle_go("b1", 1)
    assert cg is not None and cg.payload["tier"] == "T1" and cg.payload["policy_digest"] == pd
```

- [ ] **Step 2: run → FAIL** (unknown subcommands).
- [ ] **Step 3 (GREEN):** add the two builders + parsers.
```python
def _cmd_assignment(a) -> Event:
    payload = {"pair": a.pair, "builder": a.builder, "builder_provider": a.builder_provider,
               "primary_verifier": a.primary_verifier,
               "primary_verifier_provider": a.primary_verifier_provider,
               "executing_coordinator": a.executing_coordinator}
    return _build_event("assignment", payload, a.candidate_id, bus_id=a.bus_id)

def _cmd_cycle_go(a) -> Event:
    payload = {"brief_id": a.brief_id, "brief_version": a.brief_version,
               "tier": a.tier, "policy_digest": a.policy_digest}
    return _build_event("cycle_go", payload, a.candidate_id,
                        brief_id=a.brief_id, brief_version=a.brief_version, bus_id=a.bus_id)
```
```python
pa = sub.add_parser("assignment"); _common(pa)
for f in ("pair", "builder", "builder-provider", "primary-verifier",
          "primary-verifier-provider", "executing-coordinator"):
    pa.add_argument(f"--{f}", required=True)
pa.set_defaults(fn=_cmd_assignment)

pc = sub.add_parser("cycle_go"); _common(pc)
pc.add_argument("--brief-id", default="b1")
pc.add_argument("--brief-version", type=int, default=1)
pc.add_argument("--tier", required=True, choices=["T0", "T1", "T2", "T3"])
pc.add_argument("--policy-digest", required=True)
pc.set_defaults(fn=_cmd_cycle_go)
```
- [ ] **Step 4: run → PASS** all overseer tests.
- [ ] **Step 5: Commit** `feat(threeway): overseer_emit assignment + cycle_go subcommands [ADR-056]`.

### Task 3: `release_order` subcommand (envelope `subject_sha`)

**Files:** Modify `scripts/overseer_emit.py`; Test `tests/unit/test_threeway_overseer_emit.py`.

- [ ] **Step 1 (RED):** the SHA must land on the ENVELOPE (`ro.subject_sha`), NOT in payload.
```python
def test_release_order_subject_sha_on_envelope_not_payload(seatkit, tmp_path):
    reg, ks, privs = seatkit; repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main
    assert main(["release_order", "--candidate-id", "A:c1",
                 "--integration-sha", "deadbeef", "--repo-dir", str(repo), "--remote", ""]) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    ro = state.release_order("A:c1")
    assert ro is not None and ro.signer.split(":", 1)[0] == "overseer"
    assert ro.subject_sha == "deadbeef"          # envelope
    assert ro.payload == {"candidate_id": "A:c1"}  # subject_sha NOT in payload
```
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3 (GREEN):**
```python
def _cmd_release_order(a) -> Event:
    return _build_event("release_order", {"candidate_id": a.candidate_id}, a.candidate_id,
                        subject_sha=a.integration_sha, bus_id=a.bus_id)
```
```python
pr = sub.add_parser("release_order"); _common(pr)
pr.add_argument("--integration-sha", required=True)
pr.set_defaults(fn=_cmd_release_order)
```
- [ ] **Step 4: run → PASS.**
- [ ] **Step 5: Commit** `feat(threeway): overseer_emit release_order subcommand [ADR-056]`.

### Task 4: `approver_roster` + `re_verify_challenge` (T3 facts; nonce minting)

**Files:** Modify `scripts/overseer_emit.py`; Test `tests/unit/test_threeway_overseer_emit.py`.

- [ ] **Step 1 (RED):** roster carries `approvers[]`; challenge mints a fresh nonce + binds `subject_sha`.
```python
def test_approver_roster_round_trips(seatkit, tmp_path):
    reg, ks, privs = seatkit; repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main
    assert main(["approver_roster", "--candidate-id", "A:c1",
                 "--approvers", "chief-gemini", "chief-chatgpt",
                 "--repo-dir", str(repo), "--remote", ""]) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    r = state.approver_roster("A:c1")
    assert r is not None and r.payload["approvers"] == ["chief-gemini", "chief-chatgpt"]

def test_re_verify_challenge_mints_fresh_nonce(seatkit, tmp_path):
    reg, ks, privs = seatkit; repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main
    assert main(["re_verify_challenge", "--candidate-id", "A:c1",
                 "--integration-sha", "deadbeef", "--repo-dir", str(repo), "--remote", ""]) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    ch = state.re_verify_challenge("A:c1")
    assert ch is not None and ch.subject_sha == "deadbeef"  # envelope
    assert isinstance(ch.payload["nonce"], str) and len(ch.payload["nonce"]) >= 16  # minted
```
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3 (GREEN):**
```python
def _cmd_approver_roster(a) -> Event:
    return _build_event("approver_roster", {"approvers": list(a.approvers)},
                        a.candidate_id, bus_id=a.bus_id)

def _cmd_re_verify_challenge(a) -> Event:
    # ADR-043 freshness: the overseer mints a fresh, unguessable nonce; the gate enforces
    # only the echo binding. secrets.token_hex (NOT random) satisfies the freshness precondition.
    nonce = a.nonce or secrets.token_hex(16)
    return _build_event("re_verify_challenge", {"nonce": nonce}, a.candidate_id,
                        subject_sha=a.integration_sha, bus_id=a.bus_id)
```
```python
pr2 = sub.add_parser("approver_roster"); _common(pr2)
pr2.add_argument("--approvers", nargs="+", required=True, help="allowed approver SEATS")
pr2.set_defaults(fn=_cmd_approver_roster)

pv = sub.add_parser("re_verify_challenge"); _common(pv)
pv.add_argument("--integration-sha", required=True)
pv.add_argument("--nonce", default=None, help="omit to mint a fresh one (recommended)")
pv.set_defaults(fn=_cmd_re_verify_challenge)
```
- [ ] **Step 4: run → PASS** the full overseer suite.
- [ ] **Step 5: Commit** `feat(threeway): overseer_emit approver_roster + re_verify_challenge (fresh nonce) [ADR-056]`.

---

## Chunk 2: bootstrap_emit.py — the temporary interactive-seat shim

### Task 5: `bootstrap_emit.py` (candidate, attestation×2, release_requested)

**Files:**
- Create: `scripts/bootstrap_emit.py`
- Test: `tests/unit/test_threeway_bootstrap_emit.py`

**Design:** Reuse the canonical builder. Call `build_candidate_events(base_sha, branch_sha, integ, {}, bus_id, tier, pair=PAIR, candidate_id=cid)`, then emit ONLY the kinds this shim owns — `candidate` (coordinator key), the two `attestation`s (primary_verifier key, select by `payload["kind"]`), and `release_requested` (coordinator key). Compute the deterministic `integ` from the repo via `gitcas.merge_tree`+`commit_tree` (mirrors `_seed_valid`). The overseer facts and `ci_result` from the same builder are NOT appended here (they come from `overseer_emit` / the CI signer).

- [ ] **Step 1 (RED):** the four seat facts round-trip authority-correct, with the right seats + SHAs.
Use the standard `live_repo` pytest **fixture** (copy from test_threeway_gate.py:192-206 into this file — it returns `(r, base, branch)` with `refs/threeway/test-main` set + a `feat` branch). `effective_attestation` returns a raw `Event` — read the verdict from `ev.payload["verdict"]` and the SHA from `ev.subject_sha` (there is NO `.verdict`/`.event` attribute). `release_requested` is a METHOD — call it with the candidate_id.

```python
def test_bootstrap_emit_seat_facts_round_trip(seatkit, live_repo):
    reg, ks, privs = seatkit
    r, base, branch = live_repo                    # fixture: (r, base, branch)
    from scripts.bootstrap_emit import main
    common = ["--candidate-id", "A:c1", "--pair", "A", "--staging-base", base,
              "--branch", branch, "--repo-dir", str(r), "--remote", ""]
    assert main(["candidate", *common]) == 0
    assert main(["attestation", "--phase", "preliminary", *common]) == 0
    assert main(["attestation", "--phase", "release", *common]) == 0
    assert main(["release_requested", *common]) == 0
    state = verify_and_reduce(RefEventStore(Path(r)).all_events(),
                              registry_dir=str(reg), bus_id="prod")
    cand = state.candidate("A:c1")
    assert cand is not None and cand.signer.split(":", 1)[0] == "coordinator"
    assert cand.payload["staging_base_sha"] == base and cand.payload["branch_sha"] == branch
    integ = cand.payload["integration_sha"]
    prelim = state.effective_attestation("A:c1", "preliminary", "operator")  # -> Event
    rel = state.effective_attestation("A:c1", "release", "operator")          # -> Event
    assert prelim.payload["verdict"] == "GO" and prelim.subject_sha == branch  # prelim @ branch_sha
    assert rel.payload["verdict"] == "GO" and rel.subject_sha == integ         # release @ integration_sha
    assert state.release_requested("A:c1") is not None    # METHOD — non-vacuous: call with the cid
```

- [ ] **Step 2: run → FAIL** (`scripts.bootstrap_emit` missing).
- [ ] **Step 3 (GREEN):** write `scripts/bootstrap_emit.py`.
```python
#!/usr/bin/env python3
"""bootstrap_emit.py — TEMPORARY interactive-seat fact shim (threeway scope-b sub-project 1).

REPLACED by sub-project 2 (real seat<->bus wiring). Emits the facts the interactive
seats own — candidate + release_requested (pair COORDINATOR key) and the two
attestations (pair PRIMARY_VERIFIER key) — so a human can drive a full brief->merge
flow today. Reuses threeway.loop.build_candidate_events for the canonical shapes.
"""
import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from threeway import gitcas
from threeway.keys import load_private
from threeway.loop import PAIR_A, PAIR_B, build_candidate_events
from threeway.refstore import AppendContentionExceeded, RefEventStore

_PAIRS = {"A": PAIR_A, "B": PAIR_B}


def _candidate_set(a):
    """Return (pair, {kind/phase: Event}) for the candidate, computing the deterministic integ."""
    pair = _PAIRS[a.pair]
    base_sha = gitcas.rev_parse(Path(a.repo_dir), a.staging_base)   # gitcas.py:39 -> str | None
    branch_sha = gitcas.rev_parse(Path(a.repo_dir), a.branch)
    if base_sha is None:
        raise SystemExit(f"cannot resolve staging-base ref {a.staging_base!r}")
    if branch_sha is None:
        raise SystemExit(f"cannot resolve branch ref {a.branch!r}")
    cid = a.candidate_id if ":" in a.candidate_id else f"{pair.pair}:{a.candidate_id}"
    tree, clean = gitcas.merge_tree(Path(a.repo_dir), base_sha, branch_sha)
    if not clean:
        raise SystemExit("merge not clean — cannot compute integration_sha")
    integ = gitcas.commit_tree(Path(a.repo_dir), tree, [base_sha, branch_sha],
                               f"threeway merge {cid}")
    events = build_candidate_events(base_sha, branch_sha, integ, {}, bus_id=a.bus_id,
                                    tier=a.tier, pair=pair, candidate_id=a.candidate_id)
    return pair, events


def _append(a, ev) -> None:
    seat = ev.signer.split(":", 1)[0]
    store = RefEventStore(Path(a.repo_dir), remote=(a.remote or None))
    store.append(ev, load_private(seat))


def _pick(events, kind, phase=None):
    for ev in events:
        if ev.kind == kind and (phase is None or ev.payload.get("kind") == phase):
            return ev
    raise SystemExit(f"builder produced no {kind}/{phase} event")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Threeway interactive-seat bootstrap emitter (TEMPORARY).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _common(p):
        p.add_argument("--candidate-id", required=True)
        p.add_argument("--pair", default="A", choices=["A", "B"])
        p.add_argument("--staging-base", required=True, help="ref or sha")
        p.add_argument("--branch", required=True, help="ref or sha")
        p.add_argument("--tier", default="T1", choices=["T0", "T1", "T2", "T3"])
        p.add_argument("--bus-id", default="prod")
        p.add_argument("--repo-dir", default=".")
        p.add_argument("--remote", default="origin")

    for name in ("candidate", "release_requested"):
        p = sub.add_parser(name); _common(p); p.set_defaults(kind=name, phase=None)
    pat = sub.add_parser("attestation"); _common(pat)
    pat.add_argument("--phase", required=True, choices=["preliminary", "release"])
    pat.set_defaults(kind="attestation")

    args = ap.parse_args(argv)
    if (args.remote or "").lower() in ("", "none"):
        args.remote = None
    phase = getattr(args, "phase", None)
    try:
        _pair, events = _candidate_set(args)
        ev = _pick(events, args.kind, phase)
        _append(args, ev)
    except FileNotFoundError as e:
        print(f"Error loading seat key: {e}", file=sys.stderr); return 1
    except AppendContentionExceeded as e:
        print(f"Bus contention, not emitted: {e}", file=sys.stderr); return 1
    print(f"Emitted {ev.kind}{'/' + phase if phase else ''} for {ev.candidate_id} (seq {ev.seq}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
> **Confirmed:** `gitcas.rev_parse(repo, ref) -> str | None` exists (gitcas.py:39) — it returns `None` on an unresolvable ref, hence the guards above. `gitcas.merge_tree` (gitcas.py:56) and `gitcas.commit_tree` (gitcas.py:80) exist with the arity used here. `build_candidate_events`'s `privs` param is vestigial (events are unsigned), so passing `{}` is correct.

- [ ] **Step 4: run → PASS.**
Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_bootstrap_emit.py -q`
- [ ] **Step 5: Commit** `feat(threeway): bootstrap_emit shim — candidate/attestation/release_requested [ADR-056]`.

---

## Chunk 3: merge-gate daemon hardening + wrapper

> **Lock (if peers active):** `coordination/bin/claim-lock W?-run_merge_gate.py.lock` before Task 6; release on the Task 7 GO commit.

### Task 6: safer `--main-ref` default (DD-1), `--remote` (DD-3), clean shutdown

**Files:**
- Modify: `scripts/run_merge_gate.py`
- Test: `tests/unit/test_threeway_merge_gate_daemon.py`

- [ ] **Step 1 (RED):** three pins — default ref is the TEST ref; `--remote` threads through; SIGTERM-style stop flag exits 0 cleanly without aborting mid-iteration.
```python
def test_default_main_ref_is_test_main_not_real_main():
    # DD-1: a bare invocation must NOT target refs/heads/main.
    import argparse
    from scripts import run_merge_gate
    # Parse with no --main-ref and assert the default.
    ns = run_merge_gate._build_argparser().parse_args(["--run-once"])
    assert ns.main_ref == "refs/threeway/test-main"

def test_run_once_merges_a_valid_candidate(seatkit, live_repo):
    # Seed a full valid T1 set inline (no separate helper), then main() --run-once promotes it.
    reg, ks, privs = seatkit
    r, base, branch = live_repo                       # fixture: test-main ref + feat branch
    from threeway import gitcas
    from threeway.loop import build_candidate_events
    from threeway.refstore import RefEventStore
    tree, clean = gitcas.merge_tree(r, base, branch); assert clean
    integ = gitcas.commit_tree(r, tree, [base, branch], "threeway merge A:c1")
    store = RefEventStore(r)                          # local bus
    for ev in build_candidate_events(base, branch, integ, {}):   # privs vestigial -> {}
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    from scripts import run_merge_gate
    rc = run_merge_gate.main(["--repo-dir", str(r), "--registry-dir", str(reg),
                              "--bus-id", "prod", "--main-ref", "refs/threeway/test-main",
                              "--run-once"])
    assert rc == 0
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ

def test_stop_flag_exits_clean_without_running_iteration(monkeypatch, capsys):
    # DD: a stop request observed at the top of the loop returns 0 and logs the stop line,
    # and does NOT enter poll_once.
    from scripts import run_merge_gate
    monkeypatch.setattr(run_merge_gate, "_STOP", True, raising=False)
    called = {"n": 0}
    monkeypatch.setattr(run_merge_gate, "poll_once", lambda *a, **k: called.__setitem__("n", called["n"] + 1) or [])
    monkeypatch.setattr(run_merge_gate, "load_private", lambda seat: object())
    rc = run_merge_gate.main(["--repo-dir", ".", "--registry-dir", "x", "--bus-id", "prod"])
    assert rc == 0
    assert called["n"] == 0
    assert "merge-gate daemon stopped" in capsys.readouterr().out
```
> Copy the file-local `seatkit` + `live_repo` fixtures and the `_git` helper into this test file (from test_threeway_gate.py:17-34, :192-206, and the module-top `_git`). The seeding is inline (above) — no separate helper to define.

- [ ] **Step 2: run → FAIL** (default is `refs/heads/main`; no `_build_argparser`; no `--remote`; no `_STOP`).
- [ ] **Step 3 (GREEN):** edit `scripts/run_merge_gate.py`:
  1. Extract the argparser into `def _build_argparser():` so it is unit-testable.
  2. Change `--main-ref` default to `"refs/threeway/test-main"` (DD-1).
  3. Add `--remote` (default `None`); pass it to `RefEventStore(Path(args.repo_dir), remote=args.remote)`.
  4. Add the signal handler + stop-flag, checked at the TOP of the loop body (never abort mid-`poll_once`):
```python
import signal
_STOP = False

def _handle_stop(signum, frame):
    global _STOP
    _STOP = True

# inside main(), after load_private precondition, before `while True:`:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    print("merge-gate daemon started.")
    while True:
        if _STOP:
            print("merge-gate daemon stopped")
            return 0
        try:
            store = RefEventStore(Path(args.repo_dir), remote=args.remote)
            for cid, res in poll_once(store, repo=Path(args.repo_dir),
                                      registry_dir=args.registry_dir, bus_id=args.bus_id,
                                      main_ref=args.main_ref):
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                if res.outcome == "COMPLETED":
                    print(f"[{ts}] MERGED {cid}")
                elif res.outcome != "PENDING":
                    print(f"[{ts}] {res.outcome} {cid}: {res.reason}")
        except Exception as e:
            print(f"merge-gate iteration error: {e}", file=sys.stderr)
        if args.run_once:
            break
        time.sleep(args.interval)
    return 0
```
> The per-outcome logging block above is the EXISTING run_merge_gate.py:72-75 verbatim — preserve it inside the restructured loop (do not drop it). The stop check is additive and sits ABOVE the try, so an in-flight `poll_once` always finishes (`run_gate` is TOTAL, ADR-040). The existing per-iteration try/except is unchanged.

- [ ] **Step 4: run → PASS** the daemon tests; then run the existing activation pin to confirm no regression:
`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_merge_gate_daemon.py tests/unit/test_threeway_activation_scripts.py -q`
- [ ] **Step 5: Commit** `feat(threeway): merge-gate daemon — test-ref default, --remote, clean shutdown [ADR-056]`.

### Task 7: `run_merge_gate.sh` wrapper

**Files:**
- Create: `scripts/run_merge_gate.sh`
- Test: `tests/unit/test_threeway_merge_gate_daemon.py`

- [ ] **Step 1 (RED):** a guard test on the wrapper text (DD-1 + DD-2): it passes the TEST ref, the registry dir, and `--remote origin`, and does NOT export PYTHONPATH.
```python
# module-top of test_threeway_merge_gate_daemon.py:
_REPO_ROOT = Path(__file__).resolve().parents[2]   # tests/unit/<file> -> repo root

def test_wrapper_passes_test_ref_and_no_pythonpath():
    text = (_REPO_ROOT / "scripts/run_merge_gate.sh").read_text()  # absolute, CWD-independent
    assert "refs/threeway/test-main" in text          # DD-1 safety boundary
    assert "--registry-dir coordination/threeway/keys" in text
    assert "--remote origin" in text                  # DD-3 live bus
    assert "refs/heads/main" not in text              # never real main
    assert "PYTHONPATH" not in text                   # DD-2: rely on ADR-055 self-bootstrap
```
- [ ] **Step 2: run → FAIL** (file missing).
- [ ] **Step 3 (GREEN):** write `scripts/run_merge_gate.sh`:
```bash
#!/usr/bin/env bash
# Standing merge-gate daemon (threeway scope-b sub-project 1).
# Writes the protected TEST ref refs/threeway/test-main (NEVER refs/heads/main; ADR-056 DD-1).
# Relies on ADR-055 sys.path self-bootstrap in run_merge_gate.py (no PYTHONPATH export; DD-2).
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python scripts/run_merge_gate.py \
    --registry-dir coordination/threeway/keys \
    --main-ref refs/threeway/test-main \
    --remote origin \
    "$@"
```
Then `chmod +x scripts/run_merge_gate.sh`.
- [ ] **Step 4: run → PASS.**
- [ ] **Step 5: Commit** `feat(threeway): run_merge_gate.sh daemon wrapper (test-ref, no PYTHONPATH) [ADR-056]`. Release the lock on this commit if held.

---

## Chunk 4: CI signer verification + activation-script coverage

### Task 8: confirm ADR-055 pin green + fold the two new scripts into it (spec §3.3 — no new signer code)

**Files:**
- Modify: `tests/unit/test_threeway_activation_scripts.py`

- [ ] **Step 1 (RED):** add the two new scripts to the bare-subprocess parametrization so they're covered by the existing `ModuleNotFoundError`-absent + `returncode==0` pin.
```python
# test_threeway_activation_scripts.py — extend the list:
_ACTIVATION_SCRIPTS = ["sign_ci_result.py", "run_merge_gate.py", "agy_observer.py",
                       "overseer_emit.py", "bootstrap_emit.py"]
```
> Note: the existing pin runs `scripts/{script} --help`. `overseer_emit.py` and `bootstrap_emit.py` use `add_subparsers(required=True)`, so bare `--help` exits 0 and prints top-level help (argparse handles `--help` before the required-subcommand check). Verify this when running; if argparse exits non-zero on `--help` without a subcommand on this Python, relax the pin for those two to assert only `"ModuleNotFoundError" not in stderr` (the actual ADR-055 defect), matching the spec §3.3 intent.

- [ ] **Step 2: run.** This is a **coverage extension, not a RED-first cycle**: in normal chunk ordering (after Tasks 1-7) both new scripts already exist with the correct ADR-055 bootstrap, so the pin goes GREEN immediately. To confirm the pin is non-vacuous, temporarily delete the `sys.path` bootstrap block from one new script, run → expect FAIL (`ModuleNotFoundError` in stderr), then restore it.
Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_activation_scripts.py -q`
- [ ] **Step 3 (GREEN):** with the bootstrap restored, the pin is GREEN. If a script genuinely fails, fix its sys.path block to match `sign_ci_result.py:19-22` exactly. (No `sign_ci_result.py` change — §3.3 owes no new signer code; this task re-confirms it stays green and extends coverage to the two new CLIs.)
- [ ] **Step 4: run → PASS.**
- [ ] **Step 5: Commit** `test(threeway): cover overseer_emit + bootstrap_emit in the bare-subprocess pin [ADR-055/056]`.

---

## Chunk 5: end-to-end walking-skeleton

### Task 9: full T1 brief→merge via real CLI subprocesses + daemon `--run-once`

**Files:**
- Create: `tests/integration/test_threeway_e2e_walking_skeleton.py`

**This is the "operable" acceptance proof.** Drive the CLIs as **subprocesses** (the way they actually run), against a temp repo + local bus (no origin). Sequence mirrors spec §4: overseer brief/assignment/cycle_go → bootstrap candidate + preliminary attestation → CI signer `ci_result` → bootstrap release attestation + release_requested → overseer release_order → daemon `--run-once`.

- [ ] **Step 1 (RED): write the E2E test.**
```python
import os, subprocess, sys
from pathlib import Path
import pytest
from threeway import gitcas, keys
from threeway.policy import default_policy
# copy seatkit + live_repo (test-main ref + feat branch) + _git into this file

def _run(script, *args, repo, ks):
    env = dict(os.environ); env.pop("GIT_INDEX_FILE", None); env.pop("PYTHONPATH", None)
    env["THREEWAY_KEYSTORE"] = str(ks)
    proc = subprocess.run([sys.executable, f"scripts/{script}", *args],
                          cwd=Path(__file__).resolve().parents[2],
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0, f"{script} {args} failed:\n{proc.stdout}\n{proc.stderr}"
    return proc

def test_t1_brief_to_merge_walking_skeleton(seatkit, live_repo):
    reg, ks, privs = seatkit
    r, base, branch = live_repo
    cid = "A:c1"; pd = default_policy().policy_digest()
    # compute the deterministic integ the daemon will recompute+equality-check
    tree, clean = gitcas.merge_tree(r, base, branch); assert clean
    integ = gitcas.commit_tree(r, tree, [base, branch], f"threeway merge {cid}")
    L = ["--repo-dir", str(r), "--remote", ""]
    # 1. overseer facts
    _run("overseer_emit.py", "brief", "--candidate-id", cid, "--brief-id", "b1",
         "--assigned-tier", "T1", "--allowed-paths", "cinema/", *L, repo=r, ks=ks)
    _run("overseer_emit.py", "assignment", "--candidate-id", cid, "--pair", "A",
         "--builder", "director", "--builder-provider", "codex",
         "--primary-verifier", "operator", "--primary-verifier-provider", "claude",
         "--executing-coordinator", "coordinator", *L, repo=r, ks=ks)
    _run("overseer_emit.py", "cycle_go", "--candidate-id", cid, "--brief-id", "b1",
         "--tier", "T1", "--policy-digest", pd, *L, repo=r, ks=ks)
    # 2. interactive-seat facts (candidate + preliminary attestation)
    B = ["--candidate-id", cid, "--pair", "A", "--staging-base", base, "--branch", branch, *L]
    _run("bootstrap_emit.py", "candidate", *B, repo=r, ks=ks)
    _run("bootstrap_emit.py", "attestation", "--phase", "preliminary", *B, repo=r, ks=ks)
    # 3. CI signer
    _run("sign_ci_result.py", "--integration-sha", integ, "--result", "PASS",
         "--repo-dir", str(r), repo=r, ks=ks)
    # 4. release attestation + release_requested + release_order
    _run("bootstrap_emit.py", "attestation", "--phase", "release", *B, repo=r, ks=ks)
    _run("bootstrap_emit.py", "release_requested", *B, repo=r, ks=ks)
    _run("overseer_emit.py", "release_order", "--candidate-id", cid,
         "--integration-sha", integ, *L, repo=r, ks=ks)
    # 5. daemon --run-once promotes the TEST ref + emits merge_completed
    _run("run_merge_gate.py", "--repo-dir", str(r), "--registry-dir", str(reg),
         "--bus-id", "prod", "--main-ref", "refs/threeway/test-main", "--run-once",
         repo=r, ks=ks)
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ
    from threeway.gate import verify_and_reduce
    from threeway.refstore import RefEventStore
    state = verify_and_reduce(RefEventStore(r).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.merge_completed(cid) is not None
```
> **Watch items when implementing:** (a) `sign_ci_result.py` needs the `ci` key in the keystore (seatkit provides it) and finds the candidate by `integration_sha` — ensure the candidate is emitted before the CI signer runs (it is, step 2). (b) The `policy_digest` the CLIs use must match across candidate/cycle_go/ci_result — all derive from `default_policy().policy_digest()`, so they agree. (c) Place the file in `tests/integration/` — **confirmed collected** (`pyproject.toml:34 testpaths = ["tests"]`; the dir already exists with collected tests). Do NOT move it; keep it matching the file-structure table.

- [ ] **Step 2: run → FAIL** first (most likely a predicate PENDING/REJECTED — read `res.reason` by temporarily logging the daemon output). Iterate using the verified predicate chain (§"Verified anchors") until MERGEABLE.
- [ ] **Step 3 (GREEN): make it pass.** Do NOT weaken the gate — fix the emit sequence/args until the real predicate is satisfied. The ref must advance to `integ` and `merge_completed` must exist.
- [ ] **Step 4: run the whole threeway suite** to confirm no regression:
`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/ -k threeway -q`
- [ ] **Step 5: Commit** `test(threeway): E2E walking-skeleton — T1 brief->merge operable [ADR-056]`.

---

## Chunk 6: docs + acceptance gates

### Task 10: ADR-056, ARCHITECTURE.md, spec drift fixes, gates

**Files:**
- Modify: `DECISIONS.md`, `ARCHITECTURE.md`, `docs/superpowers/specs/2026-06-22-threeway-scope-b-mechanical-seat-runtime-design.md`

- [ ] **Step 1: Append ADR-056 to `DECISIONS.md`** (never edit prior entries). Record DD-1..DD-5 with the rationale above. Call out DD-1 as a behavior change to an existing CLI awaiting ratification.
- [ ] **Step 2: Update `ARCHITECTURE.md`** — add the three new operable scripts (`overseer_emit.py`, `bootstrap_emit.py`, `run_merge_gate.sh`) and the daemon's TEST-ref boundary to the threeway topology section, with file:line anchors on the SAME line as the symbol (the doc-checker only gates same-line `symbol (path:N)` anchors — see [doc_checker_same_line_blindspot]). Update any "BUS LIVE / seat-runtime unbuilt" banner to "seat-runtime: sub-project 1 operable (human-driven); sub-project 2 (real wiring) + hardening track pending."
- [ ] **Step 3: Fix the two stale spec anchors** the verification found (R-EVIDENCE staleness discipline): in the design spec, `re_verify_challenge` reducer fold is `reducer.py:357-362` (not 357-360); the `sign_ci_result.py` sys.path bootstrap is at `:19-22` (not 17-22). Mark §3.3 done.
- [ ] **Step 4: Run the acceptance gates** and capture output:
```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/ -k threeway -q
```
Expected: ci_smoke OK (PROGRAM-MANUAL drift is advisory, not a hard gate); check_no_ceremony clean (note: R3/R4 may remain RED pending the unrelated FIX-1/FIX-2 wave-gate work — confirm this slice introduces NO new ceremony, i.e. no non-strict xfail, no status-only assertion); threeway suite green.
- [ ] **Step 5: Commit** `docs(threeway): ADR-056 + ARCHITECTURE + spec drift fixes for scope-b sub-project 1`.

---

## Acceptance criteria (spec §9 — verify before claiming done)

- [ ] `overseer_emit` emits all six facts; each round-trips through `verify_and_reduce` authority-correct; the non-overseer-key mutation pin is RED (fact dropped).
- [ ] `bootstrap_emit` emits candidate + both attestations (prelim@branch_sha, release@integration_sha) + release_requested, signed by the correct seats.
- [ ] The merge-gate daemon: default `--main-ref` is the TEST ref (DD-1); `--run-once` merges a valid candidate and no-ops cleanly otherwise; a stop signal exits 0 after logging `merge-gate daemon stopped` without aborting mid-iteration.
- [ ] The CI signer runs without `ModuleNotFoundError` (bare-subprocess pin GREEN), and the two new scripts are covered by it.
- [ ] The E2E walking-skeleton drives a full T1 brief→merge through the real CLIs (as subprocesses) + the daemon and passes: `refs/threeway/test-main` advances to the recomputed `integ`, `merge_completed` emitted; real `refs/heads/main` untouched.
- [ ] `ci_smoke` + `check_no_ceremony` clean (no NEW ceremony from this slice); full threeway suite green; spec drift fixed in-change.

## Post-merge handoff

After all chunks land + verify: per the campaign's operator discipline, the implementer's commits are `fixed`, NOT `verified`. Request an operator Lane-V pass (independent re-derivation: mutation-test the daemon's TEST-ref default, the non-overseer-key drop, and the E2E ref-advance) before this sub-project is marked verified. Then proceed to the §7 hardening track or sub-project 2 per the handoff.
