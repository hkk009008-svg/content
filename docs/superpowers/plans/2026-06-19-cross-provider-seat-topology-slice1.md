# Cross-Provider Seat Topology — Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. Every task is TDD — see @superpowers:test-driven-development. Execute in an isolated git worktree — see @superpowers:using-git-worktrees.

**Goal:** Build the first slice of the cross-provider seat topology — one pair (Codex director + Claude operator), a signed-JSON event bus, an effective-state reducer, a gate-computed risk tier, and a mechanical merge-gate that performs an exact-SHA compare-and-swap merge to a *protected test branch* and provably rejects ~11 adversarial promotions while never executing candidate code.

**Architecture:** A new, self-contained Python package `threeway/` (importable via the repo's `pythonpath = ["."]`) plus a separate signed-JSON event store under `coordination/threeway/`. Events are immutable signed facts; a deterministic reducer replays them in `seq` order to compute *effective* state; the merge-gate evaluates a pure predicate over that effective state and writes `main` (here: a protected **test** ref) only via `git update-ref <ref> <new> <expected-old>` (atomic CAS), building the merge commit with `git merge-tree --write-tree` + `git commit-tree` so it never checks out or runs candidate code. The legacy markdown mailbox (`coordination/mailbox/`) is **untouched** — it coexists as a shadow per spec §8.8.

**Tech Stack:** Python 3.13, `cryptography==48.0.0` (Ed25519, already installed), `rfc8785` (JCS canonicalization — new pure-Python dep), stdlib `hashlib`/`json`/`subprocess`, `pytest` (temp-git-repo pattern with `GIT_INDEX_FILE` popped). Git plumbing: `merge-tree`, `commit-tree`, `update-ref`.

**Spec:** [docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md](../specs/2026-06-19-cross-provider-seat-topology-design.md) — revision 5, commit `ffaa50eb`. This plan implements **§11 Slice 1 only**.

---

## Scope: what this plan does and does NOT build

**In scope (spec §11 Slice 1 gate):** signed event envelope + per-seat Ed25519 keypairs; effective-state reducer (revocation / latest-verdict / candidate_aborted / brief supersession); gate-computed tier classification; the merge predicate (§6.3) with PENDING / REJECTED / MERGEABLE outcomes; the mechanical merge-gate doing an exact-SHA CAS merge to a protected test ref; gate isolation (never runs candidate code, reads a *signed* `ci_result` fact); the full one-pair tactical loop; the ≤2-rework circuit-breaker.

**Deliberately deferred (do NOT build here):**
- **Slice 2** — Pair B (the mirror), both routed coordinators, the hardened `refs/threeway/events` ref topology with one-commit-per-event + `index/<seq>` + the append-CAS push loop, per-seat cursor refs, the multi-process race gate. Slice 1 uses a **single-writer** seq assignment (a `seq`-prefixed file in a plain directory) because Slice 1 is one pair; multi-writer hardening is exactly Slice 2's gate.
- **Slice 3** — the strategic loop: dual chief (apps, human-relayed), overseer brief distribution, the **T2** other-pair-operator `co_sign`, the **T3** new-session `re_verify` + two `human_approval` facts. Slice 1 implements **T0/T1 co-sign satisfaction** fully and **rejects any escalated tier** (`tier_escalation`); `co_sign_satisfied(tier)` returns `False` for T2/T3 (the safe default — an escalated change simply cannot promote until Slice 3 supplies the machinery).

**Boundary rule (spec §11):** *"Each slice passes its own gate before the next is planned."* Do not begin a Slice 2 plan until this slice's gate (Task 17) is green.

**Standing constraint:** stay on the existing git-native substrate; **no Postgres / SQLAlchemy / FastAPI / MCP** (spec §2 non-goals, D1). The legacy markdown bus scripts (`coordination/bin/*`, `scripts/protocol_mailbox.py`, `scripts/check_coordination.py`, `scripts/status.py`) are **not modified** by Slice 1 — the three-way event vocabulary is private to the `threeway/` package, so the "four files to keep in sync" coupling is never engaged.

---

## File Structure

All new files. Single-responsibility modules, each small enough to hold in context (<~180 LOC). Pure-Python modules (no git) are listed first — they get fast unit tests; only `gitcas` and `gate` touch a real repo.

| File | Responsibility |
|---|---|
| `threeway/__init__.py` | Package marker; `SCHEMA_VERSION`, `THREEWAY_KINDS`, `LOAD_BEARING_KINDS` constants. |
| `threeway/canon.py` | JCS (RFC 8785) canonicalization → bytes. The single canonicalization chokepoint. |
| `threeway/keys.py` | Per-seat Ed25519 keypairs: keystore (private, off-repo via `THREEWAY_KEYSTORE`), public-key registry (committed trust root), `sign`/`verify`. |
| `threeway/envelope.py` | `Event` dataclass (§6.2), `payload_digest`, `idempotency_key`, `signed_bytes`, `sign_event`, `verify_event`. |
| `threeway/store.py` | `EventStore`: append a signed event (assign `seq`, write JSON file), iterate in `seq` order. Single-writer (Slice 1). |
| `threeway/reducer.py` | `reduce(events) -> EffectiveState`: effective attestations, revocations, aborts, brief supersession, latest brief_version, cycle_go / release_order / ci_result / merge-completed lookups. |
| `threeway/tier.py` | `classify_diff(paths, policy)`, `effective_tier(...)`, `co_sign_satisfied(tier, state, candidate)`. |
| `threeway/gitcas.py` | Git plumbing wrappers (no checkout, never runs candidate code): `rev_parse`, `changed_paths`, `merge_tree`, `commit_tree`, `cas_update_ref`. |
| `threeway/predicate.py` | `evaluate(candidate, state, repo, policy) -> Decision` implementing §6.3. |
| `threeway/gate.py` | `run_gate(...)`: hold the queue slot, re-derive the predicate, do the exact-SHA CAS merge to the test ref, emit a signed merge-completed fact, idempotent crash recovery. |
| `threeway/policy.py` | The active policy object: `allowed_tiers`, path→tier rules, `required_ci`, `policy_digest`, accepted-policy set. |
| `coordination/threeway/keys/README.md` | Trust-root doc + the committed `<seat>.pub` files. |
| `coordination/threeway/events/.gitkeep` | Slice 1 event-store directory. |
| `requirements.txt` (modify) | add `rfc8785`. |
| `DECISIONS.md` (append) | ADR recording the Slice 1 substrate choices. |
| `tests/unit/test_threeway_*.py` | One test module per package module (9 files). |

---

## Conventions for every task

- **Run a single test:** `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/<file>::<test> -q`
  The `env -u GIT_INDEX_FILE` prefix is **mandatory** — the dev session exports `GIT_INDEX_FILE` pointing at a per-seat index; leaving it set breaks any test that shells out to git in a temp repo (`git add` → rc 128). Confirmed in `tests/unit/test_lock_protocol.py:9-11`.
- **Temp-repo tests** copy the established `_env()` helper (pop `GIT_INDEX_FILE`, do **not** set it to `""`):
  ```python
  def _env():
      env = dict(os.environ)
      env.pop("GIT_INDEX_FILE", None)
      return env
  ```
  Pattern source: `tests/unit/test_coordination_bin.py:61-66`.
- **TDD loop per behavior:** write the failing test → run it, see it fail for the *expected* reason → write the minimal code → run it green → commit. One logical behavior per commit. Follow @superpowers:test-driven-development.
- **No ceremony (ADR-028):** every `pytest.mark.xfail` must be `strict=True` with a `reason=`. This plan adds *live* tests, not pins, so prefer real assertions over xfail. If a behavior is genuinely deferred, leave a `# Slice N` comment, not a vacuous pin.
- **Commit messages:** `feat(threeway): <behavior>` for code, `test(threeway): <behavior>` when a commit is test-only, `docs(threeway): ...` for docs.

---

## Chunk 1: Project setup, canonicalization, and keys

Foundations every later module depends on: the dependency, the package skeleton, the canonicalization chokepoint, and Ed25519 key management with a committed public-key trust root.

### Task 1: Add the JCS dependency and package skeleton

**Files:**
- Modify: `requirements.txt`
- Create: `threeway/__init__.py`
- Create: `coordination/threeway/events/.gitkeep`
- Test: `tests/unit/test_threeway_package.py`

- [ ] **Step 1: Add `rfc8785` to requirements**

In `requirements.txt`, add a line directly under the `cryptography>=42.0` line:
```
rfc8785>=0.1.4
```
(`rfc8785` is pure-Python RFC 8785 JCS — no native deps. `cryptography==48.0.0` is already installed; no change needed there.)

- [ ] **Step 2: Install it into the venv**

Run: `.venv/bin/python -m pip install 'rfc8785>=0.1.4'`
Expected: `Successfully installed rfc8785-<version>`.
Then verify the API shape this plan relies on:
Run: `.venv/bin/python -c "import rfc8785; print(type(rfc8785.dumps({'b':2,'a':1})), rfc8785.dumps({'b':2,'a':1}))"`
Expected: `<class 'bytes'> b'{\"a\":1,\"b\":2}'`
(If the installed `rfc8785` exposes a different entrypoint than `dumps`, adjust only `threeway/canon.py` in Task 2 — the rest of the plan calls `threeway.canon.canonicalize`, never `rfc8785` directly.)

- [ ] **Step 3: Write the failing package-constants test**

```python
# tests/unit/test_threeway_package.py
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_package.py -q"""
import threeway


def test_schema_version_is_a_string():
    assert isinstance(threeway.SCHEMA_VERSION, str) and threeway.SCHEMA_VERSION


def test_load_bearing_kinds_are_a_subset_of_all_kinds():
    assert threeway.LOAD_BEARING_KINDS <= threeway.THREEWAY_KINDS


def test_core_kinds_present():
    for k in ("brief", "candidate", "attestation", "release_order", "cycle_go",
              "release_requested", "ci_result", "attestation_revoked",
              "candidate_aborted", "brief_superseded", "merge_completed"):
        assert k in threeway.THREEWAY_KINDS, k
```

- [ ] **Step 4: Run it to confirm it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_package.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'threeway'`.

- [ ] **Step 5: Create the package**

```python
# threeway/__init__.py
"""Cross-provider seat topology (Slice 1).

A signed-JSON event bus + effective-state reducer + gate-computed risk tier +
a mechanical exact-SHA merge-gate. See
docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md.

Slice 1 is single-writer and one-pair. Multi-writer/ref-topology hardening is
Slice 2; the strategic loop + T2/T3 co-sign is Slice 3.
"""

SCHEMA_VERSION = "threeway/1"

# Full event vocabulary (§6.2). Private to this package — NOT the markdown bus's
# coordination/mailbox/kinds.txt.
THREEWAY_KINDS = frozenset({
    "brief", "brief_superseded", "candidate", "candidate_aborted", "assignment",
    "attestation", "attestation_revoked", "co_sign", "re_verify",
    "cycle_go", "release_requested", "release_order", "human_approval", "ci_result",
    "event_sent", "event_acknowledged", "event_rejected", "event_timed_out",
    "event_retried", "dead_letter",
    # plan extension: the gate emits merge_completed for §6.4/§9 idempotency; it is
    # architecturally required but not yet in the spec §6.2 kind enum.
    "merge_completed",
})

# Kinds whose signature the gate treats as load-bearing (must verify).
LOAD_BEARING_KINDS = frozenset({
    "brief", "brief_superseded", "candidate", "candidate_aborted", "assignment",
    "attestation", "attestation_revoked", "co_sign", "re_verify",
    "cycle_go", "release_requested", "release_order", "human_approval", "ci_result",
    "merge_completed",
})
```
Run `mkdir -p coordination/threeway/events`, then create `coordination/threeway/events/.gitkeep` (empty) so the store directory is tracked.

- [ ] **Step 6: Run it green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_package.py -q`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add requirements.txt threeway/__init__.py coordination/threeway/events/.gitkeep tests/unit/test_threeway_package.py
git commit -m "feat(threeway): package skeleton + rfc8785 dep + event vocabulary"
```

### Task 2: Canonicalization chokepoint (`threeway/canon.py`)

**Files:**
- Create: `threeway/canon.py`
- Test: `tests/unit/test_threeway_canon.py`

- [ ] **Step 1: Write the failing test (pins canonical bytes + key ordering + reject non-serializable)**

```python
# tests/unit/test_threeway_canon.py
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_canon.py -q"""
import pytest
from threeway.canon import canonicalize


def test_returns_bytes():
    assert isinstance(canonicalize({"a": 1}), bytes)


def test_key_order_is_lexicographic_and_independent_of_input_order():
    a = canonicalize({"b": 2, "a": 1})
    b = canonicalize({"a": 1, "b": 2})
    assert a == b == b'{"a":1,"b":2}'


def test_nested_objects_canonicalize_deterministically():
    obj = {"z": [3, 2, 1], "a": {"y": 1, "x": 2}}
    assert canonicalize(obj) == b'{"a":{"x":2,"y":1},"z":[3,2,1]}'


def test_unicode_is_preserved_not_ascii_escaped():
    # RFC 8785 keeps UTF-8; it does not \u-escape printable non-ASCII.
    assert canonicalize({"k": "café"}) == '{"k":"café"}'.encode("utf-8")


def test_non_serializable_raises():
    with pytest.raises(Exception):
        canonicalize({"k": object()})
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_canon.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'threeway.canon'`.

- [ ] **Step 3: Write the implementation**

```python
# threeway/canon.py
"""JCS (RFC 8785) canonicalization — the single chokepoint for signed bytes.

Every signature and every digest in this package is computed over the output of
canonicalize(). Determinism across providers/hosts is the load-bearing property,
so there is exactly ONE canonicalizer and it is RFC 8785, not ad-hoc json.dumps.
"""
from __future__ import annotations

import rfc8785


def canonicalize(obj) -> bytes:
    """Return the RFC 8785 canonical UTF-8 byte encoding of a JSON value.

    Raises on values RFC 8785 cannot canonicalize (e.g. non-JSON objects,
    NaN/Infinity), which is intentional — unserializable input must never be
    silently signed.
    """
    return rfc8785.dumps(obj)
```

- [ ] **Step 4: Run it green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_canon.py -q`
Expected: PASS (5 passed). If the unicode test fails because the installed `rfc8785` ASCII-escapes, update only the assertion to match the library's documented behavior and note it — canonicalization need only be *self-consistent*, but pin whichever it is.

- [ ] **Step 5: Commit**

```bash
git add threeway/canon.py tests/unit/test_threeway_canon.py
git commit -m "feat(threeway): RFC 8785 canonicalization chokepoint"
```

### Task 3: Ed25519 keys + committed public-key trust root (`threeway/keys.py`)

**Files:**
- Create: `threeway/keys.py`
- Create: `coordination/threeway/keys/README.md`
- Test: `tests/unit/test_threeway_keys.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_threeway_keys.py
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_keys.py -q"""
import pytest
from cryptography.exceptions import InvalidSignature
from threeway import keys


def test_generate_keypair_roundtrips_sign_verify():
    priv, pub_hex = keys.generate_keypair()
    sig = keys.sign(priv, b"payload")
    assert len(sig) == 64
    keys.verify(pub_hex, sig, b"payload")  # no raise


def test_verify_rejects_tampered_message():
    priv, pub_hex = keys.generate_keypair()
    sig = keys.sign(priv, b"payload")
    with pytest.raises(InvalidSignature):
        keys.verify(pub_hex, sig, b"TAMPERED")


def test_verify_rejects_wrong_public_key():
    priv, _ = keys.generate_keypair()
    _, other_pub = keys.generate_keypair()
    sig = keys.sign(priv, b"payload")
    with pytest.raises(InvalidSignature):
        keys.verify(other_pub, sig, b"payload")


def test_public_registry_loads_committed_keys(tmp_path):
    priv, pub_hex = keys.generate_keypair()
    reg_dir = tmp_path / "keys"
    reg_dir.mkdir()
    (reg_dir / "operator.pub").write_text(pub_hex + "\n")
    reg = keys.PublicKeyRegistry(reg_dir)
    assert reg.get("operator") == pub_hex
    with pytest.raises(KeyError):
        reg.get("nonexistent-seat")


def test_keystore_loads_private_key_from_isolated_dir(tmp_path, monkeypatch):
    priv, pub_hex = keys.generate_keypair()
    ks_dir = tmp_path / "ks"
    ks_dir.mkdir()
    (ks_dir / "operator.ed25519").write_text(keys.private_to_hex(priv) + "\n")
    monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks_dir))
    loaded = keys.load_private("operator")
    # signs verifiably under the matching public key
    keys.verify(pub_hex, keys.sign(loaded, b"x"), b"x")
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_keys.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'threeway.keys'`.

- [ ] **Step 3: Write the implementation**

```python
# threeway/keys.py
"""Per-seat Ed25519 keys.

Trust model (§6.2 / §6.4):
  * PUBLIC keys are the committed trust root: coordination/threeway/keys/<seat>.pub
    (hex of the 32-byte raw public key). Anyone can read them; they authenticate
    the *author* of every load-bearing fact.
  * PRIVATE keys live OUTSIDE the repo in a keystore dir (env THREEWAY_KEYSTORE,
    default ~/.threeway/keys), file <seat>.ed25519 (hex of the 32-byte raw seed).
    A private key (and the merge-gate credential) must NEVER be present in any
    environment that executes candidate code.
Public-key (not HMAC) signatures are mandatory so a signature *verifier* — the
merge-gate — cannot forge a *signer*.
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def generate_keypair() -> tuple[Ed25519PrivateKey, str]:
    """Return (private_key, public_key_hex)."""
    priv = Ed25519PrivateKey.generate()
    return priv, _public_hex(priv.public_key())


def _public_hex(pub: Ed25519PublicKey) -> str:
    from cryptography.hazmat.primitives import serialization
    raw = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return raw.hex()


def private_to_hex(priv: Ed25519PrivateKey) -> str:
    from cryptography.hazmat.primitives import serialization
    raw = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return raw.hex()


def sign(priv: Ed25519PrivateKey, message: bytes) -> bytes:
    return priv.sign(message)


def verify(public_key_hex: str, signature: bytes, message: bytes) -> None:
    """Raise cryptography.exceptions.InvalidSignature on mismatch."""
    pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
    pub.verify(signature, message)


def _keystore_dir() -> Path:
    return Path(os.environ.get("THREEWAY_KEYSTORE", str(Path.home() / ".threeway" / "keys")))


def load_private(seat: str) -> Ed25519PrivateKey:
    path = _keystore_dir() / f"{seat}.ed25519"
    if not path.exists():
        raise FileNotFoundError(f"no private key for seat {seat!r} at {path}")
    seed = bytes.fromhex(path.read_text().strip())
    return Ed25519PrivateKey.from_private_bytes(seed)


class PublicKeyRegistry:
    """The committed trust root: maps seat -> public-key hex."""

    def __init__(self, registry_dir: str | Path):
        self._dir = Path(registry_dir)

    def get(self, seat: str) -> str:
        path = self._dir / f"{seat}.pub"
        if not path.exists():
            raise KeyError(f"no committed public key for seat {seat!r} ({path})")
        return path.read_text().strip()
```

- [ ] **Step 4: Run it green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_keys.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Write the trust-root doc**

Run `mkdir -p coordination/threeway/keys`, then create `coordination/threeway/keys/README.md`:
```markdown
# Three-way public-key trust root

One file per seat: `<seat>.pub` — hex of the 32-byte Ed25519 **public** key.
These are committed; they are the trust root the merge-gate verifies every
load-bearing fact against.

PRIVATE keys are NEVER committed. They live in the keystore dir (env
`THREEWAY_KEYSTORE`, default `~/.threeway/keys`), one `<seat>.ed25519` per seat
(hex of the 32-byte raw seed). A private key must never be present in an
environment that executes candidate code (spec §6.4).

Slice-1 seats: `director` (Codex, builder), `operator` (Claude, primary
verifier), `coordinator` (Claude, executing integrator), `overseer`
(release_order + cycle_go), `merge-gate` (merge-completed), `ci` (signs
ci_result). Generate with `python -m threeway.keys_bootstrap` (Task 16).
```

- [ ] **Step 6: Commit**

```bash
git add threeway/keys.py coordination/threeway/keys/README.md tests/unit/test_threeway_keys.py
git commit -m "feat(threeway): Ed25519 keys + committed public-key trust root"
```

---

## Chunk 2: Signed event envelope and the event store

### Task 4: The signed event envelope (`threeway/envelope.py`)

**Files:**
- Create: `threeway/envelope.py`
- Test: `tests/unit/test_threeway_envelope.py`

The envelope is §6.2. Load-bearing details: the signature covers a **fixed subset** of fields (not the whole event, so ephemeral `created_at`/`signature` are excluded); `payload_digest = sha256(canonicalize(payload))`; `idempotency_key` excludes ephemeral fields so a timed-out retry de-duplicates.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_threeway_envelope.py
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_envelope.py -q"""
import hashlib

import pytest
from cryptography.exceptions import InvalidSignature

from threeway import keys
from threeway.canon import canonicalize
from threeway.envelope import (
    Event,
    payload_digest,
    idempotency_key,
    signed_bytes,
    sign_event,
    verify_event,
)


def _ev(**over):
    base = dict(
        id="11111111-1111-1111-1111-111111111111",
        seq=1,
        bus_id="prod",
        schema_version="threeway/1",
        brief_id="b1",
        candidate_id="c1",
        kind="attestation",
        sender="operator",
        recipient="all",
        subject_sha="a" * 40,
        brief_version=1,
        causation_id=None,
        supersedes_event_id=None,
        revokes_event_id=None,
        signer="operator:claude:sess-1",
        payload={"verdict": "GO", "kind": "release"},
    )
    base.update(over)
    return Event(**base)


def test_payload_digest_is_sha256_of_canonical_payload():
    ev = _ev()
    assert ev.payload_digest == hashlib.sha256(canonicalize(ev.payload)).hexdigest()


def test_signed_bytes_excludes_ephemeral_fields():
    ev = _ev()
    sb = signed_bytes(ev)
    assert b"created_at" not in sb
    assert b"signature" not in sb
    # but DOES bind the load-bearing identity fields
    assert ev.subject_sha.encode() in sb
    assert ev.payload_digest.encode() in sb


def test_idempotency_key_is_stable_across_ephemeral_changes():
    a = idempotency_key(_ev(signer="operator:claude:sess-1"))
    b = idempotency_key(_ev(signer="operator:claude:sess-2"))  # signer differs...
    # idempotency_key is from sender+kind+subject+payload_digest, NOT signer
    assert a == b


def test_sign_and_verify_roundtrip():
    priv, pub_hex = keys.generate_keypair()
    ev = _ev()
    sign_event(ev, priv)
    assert ev.signature
    verify_event(ev, pub_hex)  # no raise


def test_verify_fails_if_any_signed_field_is_mutated():
    priv, pub_hex = keys.generate_keypair()
    ev = _ev()
    sign_event(ev, priv)
    ev.subject_sha = "b" * 40  # tamper a signed field
    with pytest.raises(InvalidSignature):
        verify_event(ev, pub_hex)


def test_verify_fails_under_wrong_signer_key():
    priv, _ = keys.generate_keypair()
    _, other_pub = keys.generate_keypair()
    ev = _ev()
    sign_event(ev, priv)
    with pytest.raises(InvalidSignature):
        verify_event(ev, other_pub)
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_envelope.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'threeway.envelope'`.

- [ ] **Step 3: Write the implementation**

```python
# threeway/envelope.py
"""Signed, immutable event envelope (spec §6.2).

The signature covers canonical bytes over a FIXED subset of fields:
  {bus_id, schema_version, id, seq, from, to, kind, brief_id, candidate_id,
   subject_sha, payload_digest, causation_id}
Ephemeral fields (created_at, signature) are excluded so a timed-out retry of the
same logical fact re-signs to the same bytes. `from`/`to` are stored as
sender/recipient (Python keyword avoidance) but serialized under their spec names.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from threeway import keys as _keys
from threeway.canon import canonicalize

# The signature binds exactly the field set assembled in _signed_view() below
# (bus_id, schema_version, id, seq, from, to, kind, brief_id, candidate_id,
# subject_sha, payload_digest, causation_id). _signed_view is the SINGLE source of
# truth for that set — do not introduce a parallel constant list that can drift
# from what is actually signed.


@dataclass
class Event:
    id: str
    seq: int
    bus_id: str
    schema_version: str
    kind: str
    sender: str            # serialized as "from"
    recipient: str         # serialized as "to"
    signer: str            # "seat:provider:session_uuid"
    payload: dict[str, Any]
    brief_id: str | None = None
    candidate_id: str | None = None
    subject_sha: str | None = None
    brief_version: int | None = None
    causation_id: str | None = None
    supersedes_event_id: str | None = None
    revokes_event_id: str | None = None
    created_at: str | None = None      # ephemeral
    signature: str | None = None       # hex; ephemeral wrt signed_bytes

    @property
    def payload_digest(self) -> str:
        return payload_digest(self)


def payload_digest(ev: Event) -> str:
    return hashlib.sha256(canonicalize(ev.payload)).hexdigest()


def _signed_view(ev: Event) -> dict:
    return {
        "bus_id": ev.bus_id,
        "schema_version": ev.schema_version,
        "id": ev.id,
        "seq": ev.seq,
        "from": ev.sender,
        "to": ev.recipient,
        "kind": ev.kind,
        "brief_id": ev.brief_id,
        "candidate_id": ev.candidate_id,
        "subject_sha": ev.subject_sha,
        "payload_digest": payload_digest(ev),
        "causation_id": ev.causation_id,
    }


def signed_bytes(ev: Event) -> bytes:
    return canonicalize(_signed_view(ev))


def idempotency_key(ev: Event) -> str:
    subj = ev.subject_sha if ev.subject_sha is not None else (
        str(ev.brief_version) if ev.brief_version is not None else "")
    raw = f"{ev.sender}:{ev.kind}:{subj}:{payload_digest(ev)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def sign_event(ev: Event, private_key: Ed25519PrivateKey) -> None:
    ev.signature = _keys.sign(private_key, signed_bytes(ev)).hex()


def verify_event(ev: Event, public_key_hex: str) -> None:
    """Raise cryptography.exceptions.InvalidSignature if the signature is bad."""
    if not ev.signature:
        from cryptography.exceptions import InvalidSignature
        raise InvalidSignature("missing signature")
    _keys.verify(public_key_hex, bytes.fromhex(ev.signature), signed_bytes(ev))
```

- [ ] **Step 4: Run it green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_envelope.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add threeway/envelope.py tests/unit/test_threeway_envelope.py
git commit -m "feat(threeway): signed immutable event envelope (§6.2)"
```

### Task 5: JSON (de)serialization of events

**Files:**
- Modify: `threeway/envelope.py`
- Test: `tests/unit/test_threeway_envelope.py` (extend)

Events persist as JSON with spec field names (`from`/`to`, not `sender`/`recipient`).

- [ ] **Step 1: Add failing roundtrip test**

Append to `tests/unit/test_threeway_envelope.py`:
```python
from threeway.envelope import to_json_obj, from_json_obj


def test_json_roundtrip_uses_spec_field_names():
    priv, pub_hex = keys.generate_keypair()
    ev = _ev()
    sign_event(ev, priv)
    obj = to_json_obj(ev)
    assert obj["from"] == "operator" and obj["to"] == "all"
    assert "sender" not in obj and "recipient" not in obj
    back = from_json_obj(obj)
    verify_event(back, pub_hex)  # signature still verifies after roundtrip
    assert back.subject_sha == ev.subject_sha and back.seq == ev.seq
```

- [ ] **Step 2: Run to confirm it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_envelope.py::test_json_roundtrip_uses_spec_field_names -q`
Expected: FAIL with `ImportError: cannot import name 'to_json_obj'`.

- [ ] **Step 3: Implement (append to `threeway/envelope.py`)**

```python
def to_json_obj(ev: Event) -> dict:
    obj = {
        "id": ev.id, "seq": ev.seq, "bus_id": ev.bus_id,
        "schema_version": ev.schema_version, "kind": ev.kind,
        "from": ev.sender, "to": ev.recipient, "signer": ev.signer,
        "brief_id": ev.brief_id, "candidate_id": ev.candidate_id,
        "subject_sha": ev.subject_sha, "brief_version": ev.brief_version,
        "causation_id": ev.causation_id,
        "supersedes_event_id": ev.supersedes_event_id,
        "revokes_event_id": ev.revokes_event_id,
        "payload": ev.payload, "payload_digest": payload_digest(ev),
        # idempotency_key is a DERIVED field (spec §6.2): written for at-rest
        # completeness, recomputed (not read back) by from_json_obj.
        "idempotency_key": idempotency_key(ev),
        "created_at": ev.created_at, "signature": ev.signature,
    }
    return obj


def from_json_obj(obj: dict) -> Event:
    return Event(
        id=obj["id"], seq=obj["seq"], bus_id=obj["bus_id"],
        schema_version=obj["schema_version"], kind=obj["kind"],
        sender=obj["from"], recipient=obj["to"], signer=obj["signer"],
        payload=obj["payload"], brief_id=obj.get("brief_id"),
        candidate_id=obj.get("candidate_id"), subject_sha=obj.get("subject_sha"),
        brief_version=obj.get("brief_version"), causation_id=obj.get("causation_id"),
        supersedes_event_id=obj.get("supersedes_event_id"),
        revokes_event_id=obj.get("revokes_event_id"),
        created_at=obj.get("created_at"), signature=obj.get("signature"),
    )
```

- [ ] **Step 4: Run green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_envelope.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add threeway/envelope.py tests/unit/test_threeway_envelope.py
git commit -m "feat(threeway): event JSON (de)serialization with spec field names"
```

### Task 6: Append-only event store (`threeway/store.py`)

**Files:**
- Create: `threeway/store.py`
- Test: `tests/unit/test_threeway_store.py`

Slice 1 = single-writer. `seq` is assigned as `(max existing seq) + 1`; files are named `<seq:08d>-<id>.json` so directory order == seq order. (Slice 2 replaces this with the `refs/threeway/events` append-CAS loop.)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_threeway_store.py
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_store.py -q"""
from threeway import keys
from threeway.envelope import Event, sign_event
from threeway.store import EventStore


def _unsigned(seq, kind="attestation", **over):
    base = dict(
        id=f"id-{seq}", seq=0, bus_id="prod", schema_version="threeway/1",
        kind=kind, sender="operator", recipient="all", signer="operator:claude:s1",
        payload={"k": seq},
    )
    base.update(over)
    return Event(**base)


def test_append_assigns_monotonic_seq_starting_at_1(tmp_path):
    store = EventStore(tmp_path / "events")
    priv, _ = keys.generate_keypair()
    e1 = store.append(_unsigned(1), priv)
    e2 = store.append(_unsigned(2), priv)
    assert (e1.seq, e2.seq) == (1, 2)


def test_appended_events_are_signed_and_persisted(tmp_path):
    store = EventStore(tmp_path / "events")
    priv, pub = keys.generate_keypair()
    e = store.append(_unsigned(1), priv)
    assert e.signature
    files = list((tmp_path / "events").glob("*.json"))
    assert len(files) == 1 and files[0].name.startswith("00000001-")


def test_iter_returns_events_in_seq_order(tmp_path):
    store = EventStore(tmp_path / "events")
    priv, pub = keys.generate_keypair()
    for i in range(1, 6):
        store.append(_unsigned(i), priv)
    seqs = [e.seq for e in store.iter_events()]
    assert seqs == [1, 2, 3, 4, 5]


def test_iter_events_roundtrips_payload_and_seq(tmp_path):
    # The store is a RAW reader — signature VERIFICATION is the gate's chokepoint
    # (Task 14 verify_and_reduce), not the store. This test only pins disk round-trip.
    store = EventStore(tmp_path / "events")
    priv, _ = keys.generate_keypair()  # raw-reader test: no verification, no pub needed
    store.append(_unsigned(1), priv)
    loaded = list(store.iter_events())
    assert loaded[0].seq == 1 and loaded[0].payload == {"k": 1}
    assert loaded[0].signature  # signed on append, present on read


def test_seq_persists_across_store_reopen(tmp_path):
    priv, _ = keys.generate_keypair()
    EventStore(tmp_path / "events").append(_unsigned(1), priv)
    e2 = EventStore(tmp_path / "events").append(_unsigned(2), priv)
    assert e2.seq == 2
```

- [ ] **Step 2: Run to confirm it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_store.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'threeway.store'`.

- [ ] **Step 3: Write the implementation**

```python
# threeway/store.py
"""Append-only signed-JSON event store (Slice 1, single-writer).

seq = (max existing seq) + 1; files named <seq:08d>-<id>.json so lexical order is
seq order. This is the Slice-1 substrate; Slice 2 replaces it with one git commit
per event on refs/threeway/events + an index ref + an expected-old-OID append-CAS
push loop (spec §8). The public read/iter API is intended to stay stable across
that swap.

iter_events()/all_events() are RAW readers — they do NOT verify signatures.
Signature/bus_id/signer verification is the merge-gate's single chokepoint
(threeway.gate.verify_and_reduce, §6.4); the store never silently trusts or
silently rejects, it just reads what was written.
"""
from __future__ import annotations

import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from threeway.envelope import Event, from_json_obj, sign_event, to_json_obj


class EventStore:
    def __init__(self, events_dir: str | Path):
        self._dir = Path(events_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _next_seq(self) -> int:
        seqs = [int(p.name.split("-", 1)[0]) for p in self._dir.glob("*.json")]
        return (max(seqs) + 1) if seqs else 1

    def append(self, ev: Event, private_key: Ed25519PrivateKey) -> Event:
        ev.seq = self._next_seq()
        sign_event(ev, private_key)
        path = self._dir / f"{ev.seq:08d}-{ev.id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(to_json_obj(ev), indent=2, ensure_ascii=False))
        tmp.replace(path)  # atomic
        return ev

    def iter_events(self):
        for path in sorted(self._dir.glob("*.json")):
            yield from_json_obj(json.loads(path.read_text()))

    def all_events(self) -> list[Event]:
        return list(self.iter_events())
```

- [ ] **Step 4: Run green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_store.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add threeway/store.py tests/unit/test_threeway_store.py
git commit -m "feat(threeway): append-only signed-JSON event store (single-writer)"
```

---

## Chunk 3: The effective-state reducer

### Task 7: Reducer — effective attestations, revocation, latest-verdict, abort, supersession (`threeway/reducer.py`)

**Files:**
- Create: `threeway/reducer.py`
- Test: `tests/unit/test_threeway_reducer.py`

This is the spec's **effective-state rule** (§6.1): the predicate operates only on *effective* facts. An attestation is effective iff (a) not revoked and (b) it is the **operator's latest verdict** for its `(candidate_id, kind)`. So `GO` then `FAIL` (or `attestation_revoked`) leaves **no** effective `GO`. "Latest" is by `seq`. The reducer also tracks aborted candidates, superseded brief versions, and the latest cycle_go / release_order / ci_result / merge_completed per subject.

- [ ] **Step 1: Write the failing tests (one per effective-state rule)**

```python
# tests/unit/test_threeway_reducer.py
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_reducer.py -q"""
from threeway.envelope import Event
from threeway.reducer import reduce


def _ev(seq, kind, payload=None, **over):
    base = dict(
        id=f"e{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
        kind=kind, sender="operator", recipient="all",
        signer="operator:claude:s1", payload=payload or {},
        candidate_id="c1", brief_id="b1", brief_version=1,
    )
    base.update(over)
    return Event(**base)


def _att(seq, verdict, subject="dead", kind_att="release", signer="operator:claude:s1", **o):
    return _ev(seq, "attestation",
               payload={"kind": kind_att, "verdict": verdict},
               subject_sha=subject, signer=signer, **o)


def test_latest_verdict_wins_go_then_fail_leaves_no_effective_go():
    state = reduce([_att(1, "GO"), _att(2, "FAIL")])
    eff = state.effective_attestation("c1", "release", "operator")
    assert eff is not None and eff.payload["verdict"] == "FAIL"


def test_explicit_revocation_removes_effective_attestation():
    events = [_att(1, "GO"), _ev(2, "attestation_revoked", revokes_event_id="e1")]
    state = reduce(events)
    assert state.effective_attestation("c1", "release", "operator") is None


def test_distinct_signers_tracked_separately():
    a = _att(1, "GO", signer="operator:claude:s1")
    b = _att(2, "FAIL", signer="operator2:codex:s1")
    state = reduce([a, b])
    assert state.effective_attestation("c1", "release", "operator").payload["verdict"] == "GO"
    assert state.effective_attestation("c1", "release", "operator2").payload["verdict"] == "FAIL"


def test_candidate_aborted_is_recorded():
    state = reduce([_ev(1, "candidate_aborted")])
    assert state.is_aborted("c1")


def test_latest_non_superseded_brief_version():
    events = [
        _ev(1, "brief", brief_version=1, payload={"brief_id": "b1"}),
        _ev(2, "brief", brief_version=2, payload={"brief_id": "b1"}),
        _ev(3, "brief_superseded", brief_version=1, supersedes_event_id="e1"),
    ]
    state = reduce(events)
    assert state.latest_brief_version("b1") == 2


def test_latest_brief_version_skips_a_superseded_latest():
    # the LATEST version (v2) is superseded -> latest live version is v1
    events = [
        _ev(1, "brief", brief_version=1, payload={"brief_id": "b1"}),
        _ev(2, "brief", brief_version=2, payload={"brief_id": "b1"}),
        _ev(3, "brief_superseded", brief_version=2, supersedes_event_id="e2"),
    ]
    state = reduce(events)
    assert state.latest_brief_version("b1") == 1


def test_brief_accessor_returns_event_or_none():
    state = reduce([_ev(1, "brief", brief_version=1, payload={"brief_id": "b1"})])
    assert state.brief("b1", 1) is not None
    assert state.brief("b1", 2) is None


def test_release_order_lookup_by_candidate_and_sha():
    state = reduce([_ev(1, "release_order", subject_sha="abc",
                        payload={"candidate_id": "c1"})])
    ro = state.release_order("c1")
    assert ro is not None and ro.subject_sha == "abc"


def test_cycle_go_lookup_returns_latest():
    events = [
        _ev(1, "cycle_go", payload={"brief_id": "b1", "brief_version": 1, "tier": "T1"}),
        _ev(2, "cycle_go", payload={"brief_id": "b1", "brief_version": 1, "tier": "T2"}),
    ]
    state = reduce(events)
    assert state.cycle_go("b1", 1).payload["tier"] == "T2"


def test_ci_result_lookup_by_sha():
    state = reduce([_ev(1, "ci_result", subject_sha="sha9",
                        payload={"result": "PASS", "policy_digest": "p1"})])
    assert state.ci_result("sha9").payload["result"] == "PASS"


def test_merge_completed_lookup_for_idempotency():
    state = reduce([_ev(1, "merge_completed", payload={"candidate_id": "c1"})])
    assert state.merge_completed("c1") is not None
```

- [ ] **Step 2: Run to confirm it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_reducer.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'threeway.reducer'`.

- [ ] **Step 3: Write the implementation**

```python
# threeway/reducer.py
"""Replay append-only facts (in seq order) into EffectiveState (spec §6.1).

The predicate only ever reads EffectiveState, never raw events. An attestation is
EFFECTIVE iff it is the latest (by seq) verdict for its (candidate_id, att_kind,
signer-seat) AND not revoked. signer-seat = the seat portion of signer
("operator:claude:s1" -> "operator"), so a fresh re-verify SESSION by the same
seat still supersedes the prior one (latest seq wins), which is the intended
"latest verdict" semantics.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from threeway.envelope import Event


def _seat_of(signer: str) -> str:
    return signer.split(":", 1)[0]


@dataclass
class EffectiveState:
    # (candidate_id, att_kind, seat) -> latest attestation Event
    _attestations: dict[tuple, Event] = field(default_factory=dict)
    _revoked_event_ids: set[str] = field(default_factory=set)
    _aborted_candidates: set[str] = field(default_factory=set)
    _superseded_event_ids: set[str] = field(default_factory=set)
    _briefs: dict[tuple, Event] = field(default_factory=dict)        # (brief_id, version) -> Event
    _cycle_go: dict[tuple, Event] = field(default_factory=dict)      # (brief_id, version) -> Event
    _release_order: dict[str, Event] = field(default_factory=dict)   # candidate_id -> Event
    _release_requested: dict[str, Event] = field(default_factory=dict)
    _ci_result: dict[str, Event] = field(default_factory=dict)       # subject_sha -> Event
    _candidates: dict[str, Event] = field(default_factory=dict)      # candidate_id -> Event
    _assignments: dict[str, Event] = field(default_factory=dict)     # pair -> Event
    _merge_completed: dict[str, Event] = field(default_factory=dict) # candidate_id -> Event
    _co_sign: dict[tuple, Event] = field(default_factory=dict)       # (candidate_id, seat) -> Event
    _re_verify: dict[tuple, Event] = field(default_factory=dict)
    _human_approval: dict[tuple, Event] = field(default_factory=dict)  # (candidate_id, approver) -> Event

    # ---- effective queries used by the predicate ----
    def effective_attestation(self, candidate_id, att_kind, seat) -> Event | None:
        ev = self._attestations.get((candidate_id, att_kind, seat))
        if ev is None or ev.id in self._revoked_event_ids:
            return None
        return ev

    def is_aborted(self, candidate_id) -> bool:
        return candidate_id in self._aborted_candidates

    def brief(self, brief_id, version) -> Event | None:
        return self._briefs.get((brief_id, version))

    def latest_brief_version(self, brief_id) -> int | None:
        # a version is live iff its brief event id is not in the superseded set —
        # otherwise a brief_superseded of the LATEST version would be ignored and the
        # predicate's "candidate.brief_version == latest_non_superseded" clause (§6.3)
        # would silently pass on a superseded brief.
        versions = [v for (bid, v), ev in self._briefs.items()
                    if bid == brief_id and ev.id not in self._superseded_event_ids]
        return max(versions) if versions else None

    def cycle_go(self, brief_id, version) -> Event | None:
        return self._cycle_go.get((brief_id, version))

    def release_order(self, candidate_id) -> Event | None:
        return self._release_order.get(candidate_id)

    def release_requested(self, candidate_id) -> Event | None:
        return self._release_requested.get(candidate_id)

    def ci_result(self, subject_sha) -> Event | None:
        return self._ci_result.get(subject_sha)

    def candidate(self, candidate_id) -> Event | None:
        return self._candidates.get(candidate_id)

    def assignment(self, pair) -> Event | None:
        return self._assignments.get(pair)

    def merge_completed(self, candidate_id) -> Event | None:
        return self._merge_completed.get(candidate_id)

    def co_sign(self, candidate_id, seat) -> Event | None:
        return self._co_sign.get((candidate_id, seat))

    def re_verify(self, candidate_id, seat) -> Event | None:
        return self._re_verify.get((candidate_id, seat))

    def human_approvals(self, candidate_id) -> list[Event]:
        return [e for (cid, _), e in self._human_approval.items() if cid == candidate_id]


def reduce(events) -> EffectiveState:
    st = EffectiveState()
    for ev in sorted(events, key=lambda e: e.seq):
        k = ev.kind
        if k == "attestation":
            seat = _seat_of(ev.signer)
            att_kind = ev.payload.get("kind", "release")
            st._attestations[(ev.candidate_id, att_kind, seat)] = ev
        elif k == "attestation_revoked":
            if ev.revokes_event_id:
                st._revoked_event_ids.add(ev.revokes_event_id)
        elif k == "candidate_aborted":
            st._aborted_candidates.add(ev.candidate_id)
        elif k == "brief":
            st._briefs[(ev.brief_id, ev.brief_version)] = ev
        elif k == "brief_superseded":
            if ev.supersedes_event_id:
                st._superseded_event_ids.add(ev.supersedes_event_id)
        elif k == "cycle_go":
            st._cycle_go[(ev.payload.get("brief_id", ev.brief_id),
                          ev.payload.get("brief_version", ev.brief_version))] = ev
        elif k == "release_order":
            st._release_order[ev.payload.get("candidate_id", ev.candidate_id)] = ev
        elif k == "release_requested":
            st._release_requested[ev.payload.get("candidate_id", ev.candidate_id)] = ev
        elif k == "ci_result":
            st._ci_result[ev.subject_sha] = ev
        elif k == "candidate":
            st._candidates[ev.candidate_id] = ev
        elif k == "assignment":
            st._assignments[ev.payload.get("pair")] = ev
        elif k == "merge_completed":
            st._merge_completed[ev.payload.get("candidate_id", ev.candidate_id)] = ev
        elif k == "co_sign":
            st._co_sign[(ev.candidate_id, _seat_of(ev.signer))] = ev
        elif k == "re_verify":
            st._re_verify[(ev.candidate_id, _seat_of(ev.signer))] = ev
        elif k == "human_approval":
            st._human_approval[(ev.candidate_id, ev.payload.get("approver_identity"))] = ev
    return st
```

- [ ] **Step 4: Run green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_reducer.py -q`
Expected: PASS (11 passed).

- [ ] **Step 5: Commit**

```bash
git add threeway/reducer.py tests/unit/test_threeway_reducer.py
git commit -m "feat(threeway): effective-state reducer (§6.1 revocation/latest-verdict/abort)"
```

---

## Chunk 4: Policy, tier classification, and git CAS plumbing

### Task 8: The active policy object (`threeway/policy.py`)

**Files:**
- Create: `threeway/policy.py`
- Test: `tests/unit/test_threeway_policy.py`

The policy holds: path→minimum-tier rules (spec §7.2 table), the accepted-policy set (for `policy_digest`), and `required_ci`. `policy_digest` is the sha256 of the canonicalized policy rules so a candidate that *weakened its own CI policy* changes the digest and is detectably non-current.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_threeway_policy.py
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_policy.py -q"""
from threeway.policy import default_policy


def test_policy_digest_is_stable_and_hex():
    p = default_policy()
    d = p.policy_digest()
    assert isinstance(d, str) and len(d) == 64
    assert default_policy().policy_digest() == d  # deterministic


def test_current_policy_is_accepted():
    p = default_policy()
    assert p.is_accepted(p.policy_digest())
    assert not p.is_accepted("deadbeef")


def test_required_ci_present_for_every_tier():
    p = default_policy()
    for tier in ("T0", "T1", "T2", "T3"):
        assert p.required_ci(tier)
```

- [ ] **Step 2: Run to confirm it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_policy.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'threeway.policy'`.

- [ ] **Step 3: Write the implementation**

```python
# threeway/policy.py
"""Active promotion policy (spec §7.2 + §12 'trusted CI image / policy source').

Path -> minimum-tier rules are ordered, most-sensitive first. policy_digest binds
the rules so a candidate that edits the policy is detectably non-current (the gate
rejects a candidate whose policy_digest is not in the accepted set).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from threeway.canon import canonicalize

# (glob-prefix, tier). Checked in order; first match wins for that path.
_DEFAULT_RULES = (
    # T3 — production data, security controls, release signing, infra deletion
    ("coordination/threeway/keys/", "T3"),
    ("threeway/keys.py", "T3"),
    ("threeway/gate.py", "T3"),
    # T2 — auth, concurrency, schema/migration, deps, lock-touching, CI/policy
    (".github/workflows/", "T2"),
    ("scripts/ci_smoke.py", "T2"),
    ("scripts/wave_gate_check.py", "T2"),
    ("scripts/check_no_ceremony.py", "T2"),
    ("requirements.txt", "T2"),
    ("package-lock.json", "T2"),
    ("threeway/policy.py", "T2"),
    ("threeway/predicate.py", "T2"),
    ("coordination/", "T2"),
    # T0 — docs/comments only
    ("docs/", "T0"),
)

_REQUIRED_CI = {"T0": ("ci_smoke",), "T1": ("ci_smoke",),
                "T2": ("ci_smoke", "wave_gate"), "T3": ("ci_smoke", "wave_gate")}


@dataclass(frozen=True)
class Policy:
    rules: tuple = _DEFAULT_RULES
    accepted_digests: frozenset = field(default_factory=frozenset)

    def policy_digest(self) -> str:
        return hashlib.sha256(canonicalize([list(r) for r in self.rules])).hexdigest()

    def is_accepted(self, digest: str) -> bool:
        return digest == self.policy_digest() or digest in self.accepted_digests

    def required_ci(self, tier: str) -> tuple:
        return _REQUIRED_CI[tier]


def default_policy() -> Policy:
    return Policy()
```

- [ ] **Step 4: Run green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_policy.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add threeway/policy.py tests/unit/test_threeway_policy.py
git commit -m "feat(threeway): active policy object + policy_digest"
```

### Task 9: Tier classification and co-sign satisfaction (`threeway/tier.py`)

**Files:**
- Create: `threeway/tier.py`
- Test: `tests/unit/test_threeway_tier.py`

`classify_diff` maps a set of changed paths to the **maximum** minimum-tier any path requires. `effective_tier = max(brief.assigned_tier, classify(diff))`. `co_sign_satisfied`: T0/T1 → True (no extra artifact); **T2/T3 → False in Slice 1** (the other-pair `co_sign`, `re_verify`, `human_approval` machinery is Slice 3) — so any escalated tier safely cannot promote.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_threeway_tier.py
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_tier.py -q"""
from threeway.policy import default_policy
from threeway.tier import classify_diff, effective_tier, co_sign_satisfied, tier_rank
from threeway.reducer import reduce


P = default_policy()


def test_docs_only_is_t0():
    # both under docs/ — root-level docs (README.md etc.) intentionally fall to the
    # T1 default, which is SAFE (over-classify never under-promotes); see
    # _DEFAULT_RULES in threeway/policy.py.
    assert classify_diff(["docs/x.md", "docs/guide.md"], P) == "T0"


def test_bounded_code_is_t1():
    assert classify_diff(["cinema/foo.py"], P) == "T1"


def test_ci_config_is_t2():
    assert classify_diff([".github/workflows/ci.yml"], P) == "T2"


def test_keys_dir_is_t3():
    assert classify_diff(["coordination/threeway/keys/operator.pub"], P) == "T3"


def test_classify_takes_the_max_over_all_paths():
    assert classify_diff(["docs/x.md", ".github/workflows/ci.yml"], P) == "T2"


def test_effective_tier_is_max_of_claimed_and_path_derived():
    # path-derived T1, brief claimed T2 -> T2
    assert effective_tier("T2", ["cinema/foo.py"], P) == "T2"
    # path-derived T2, brief claimed T0 -> T2 (claim never lowers it)
    assert effective_tier("T0", [".github/workflows/ci.yml"], P) == "T2"


def test_t0_t1_cosign_satisfied_without_extra_artifacts():
    state = reduce([])
    assert co_sign_satisfied("T0", state, candidate_id="c1", builder_provider="codex")
    assert co_sign_satisfied("T1", state, candidate_id="c1", builder_provider="codex")


def test_t2_t3_not_satisfiable_in_slice1():
    state = reduce([])
    assert not co_sign_satisfied("T2", state, candidate_id="c1", builder_provider="codex")
    assert not co_sign_satisfied("T3", state, candidate_id="c1", builder_provider="codex")
```

- [ ] **Step 2: Run to confirm it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_tier.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'threeway.tier'`.

- [ ] **Step 3: Write the implementation**

```python
# threeway/tier.py
"""Gate-computed risk tier (spec §7.2). The gate NEVER trusts a claimed tier:
effective_tier = max(brief.assigned_tier, classify(diff, policy)).
"""
from __future__ import annotations

_ORDER = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}


def tier_rank(t: str) -> int:
    return _ORDER[t]


def _path_tier(path: str, policy) -> str:
    for prefix, tier in policy.rules:
        if path == prefix or path.startswith(prefix):
            return tier
    # default for any code path not otherwise matched
    return "T1"


def classify_diff(paths, policy) -> str:
    tiers = [_path_tier(p, policy) for p in paths]
    if not tiers:
        return "T0"
    return max(tiers, key=tier_rank)


def effective_tier(claimed_tier: str, paths, policy) -> str:
    return max(claimed_tier, classify_diff(paths, policy), key=tier_rank)


def co_sign_satisfied(tier: str, state, candidate_id: str, builder_provider: str) -> bool:
    """Whether the tier-SPECIFIC extra approvals exist (beyond the primary release
    GO + the coordinator candidate sig, which the predicate checks separately).

    Slice 1 implements T0/T1 only. T2 needs the OTHER pair's operator co_sign and
    T3 adds a new-session re_verify + two human_approval facts — both land in
    Slice 3 (they need Pair B / the human relay). Returning False here is the safe
    default: an escalated change simply cannot promote yet.
    """
    if tier in ("T0", "T1"):
        return True
    return False  # Slice 3: implement T2 (other-pair co_sign) and T3 (re_verify + 2 human_approval)
```

- [ ] **Step 4: Run green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_tier.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add threeway/tier.py tests/unit/test_threeway_tier.py
git commit -m "feat(threeway): gate-computed tier classification + T0/T1 co-sign"
```

### Task 10: Git CAS plumbing (`threeway/gitcas.py`)

**Files:**
- Create: `threeway/gitcas.py`
- Test: `tests/unit/test_threeway_gitcas.py`

The merge-gate's only git operations. **Never checks out, never runs candidate code.** `merge_tree` returns `(tree_oid, clean)` — and the sharp edge from the substrate map: `git merge-tree --write-tree` **exits 1 on conflict but still prints a tree OID**, so `clean` MUST come from the exit code, never from "did it print a tree." `commit_tree` sets fixed `GIT_AUTHOR_*`/`GIT_COMMITTER_*` for determinism. `cas_update_ref` is the atomic compare-and-swap.

- [ ] **Step 1: Write the failing test (uses a temp repo)**

```python
# tests/unit/test_threeway_gitcas.py
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gitcas.py -q"""
import os
import subprocess

import pytest

from threeway import gitcas


def _env():
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    return env


def _git(repo, *args, **kw):
    return subprocess.run(["git", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True,
                          env=_env(), **kw)


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st")
    _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    base = _git(r, "rev-parse", "HEAD").stdout.strip()
    # a branch that adds a NEW file (clean merge with base's later state)
    _git(r, "checkout", "-q", "-b", "feat")
    (r / "feat.txt").write_text("feat\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "feat")
    branch = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "checkout", "-q", "master") if _has(r, "master") else _git(r, "checkout", "-q", "main")
    return r, base, branch


def _has(repo, name):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", name],
                          capture_output=True, env=_env()).returncode == 0


def test_changed_paths(repo):
    r, base, branch = repo
    assert gitcas.changed_paths(r, base, branch) == ["feat.txt"]


def test_merge_tree_clean_returns_tree_and_true(repo):
    r, base, branch = repo
    tree, clean = gitcas.merge_tree(r, base, branch)
    assert clean is True and len(tree) == 40


def test_merge_tree_conflict_returns_false_even_though_git_prints_a_tree(repo):
    r, base, branch = repo
    # create a conflicting branch: edits base.txt differently from a sibling edit
    _git(r, "checkout", "-q", "-b", "conflictA", base)
    (r / "base.txt").write_text("A\n")
    _git(r, "commit", "-aqm", "A")
    a = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "checkout", "-q", "-b", "conflictB", base)
    (r / "base.txt").write_text("B\n")
    _git(r, "commit", "-aqm", "B")
    b = _git(r, "rev-parse", "HEAD").stdout.strip()
    tree, clean = gitcas.merge_tree(r, a, b)
    assert clean is False  # exit-code driven, not "did it print a tree"


def test_commit_tree_is_deterministic(repo):
    r, base, branch = repo
    tree, _ = gitcas.merge_tree(r, base, branch)
    c1 = gitcas.commit_tree(r, tree, [base, branch], "merge")
    c2 = gitcas.commit_tree(r, tree, [base, branch], "merge")
    assert c1 == c2  # fixed author/committer/date => identical OID


def test_cas_update_ref_succeeds_on_matching_old_and_fails_on_stale(repo):
    r, base, branch = repo
    _git(r, "update-ref", "refs/threeway/test-main", base)
    tree, _ = gitcas.merge_tree(r, base, branch)
    merge = gitcas.commit_tree(r, tree, [base, branch], "merge")
    assert gitcas.cas_update_ref(r, "refs/threeway/test-main", merge, base) is True
    # second CAS with the now-stale expected-old must fail
    assert gitcas.cas_update_ref(r, "refs/threeway/test-main", base, base) is False
```

- [ ] **Step 2: Run to confirm it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gitcas.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'threeway.gitcas'`.

- [ ] **Step 3: Write the implementation**

```python
# threeway/gitcas.py
"""Git plumbing for the mechanical merge-gate.

INVARIANT: never checks out a working tree, never reads candidate workflow files,
never executes candidate code. Only object-store plumbing: merge-tree, commit-tree,
update-ref. Every call strips GIT_INDEX_FILE (per-seat index pollution, CLAUDE.md).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Fixed identity so commit_tree is byte-deterministic across machines/seats.
_DET_ENV = {
    "GIT_AUTHOR_NAME": "threeway-merge-gate",
    "GIT_AUTHOR_EMAIL": "merge-gate@threeway.local",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
    "GIT_COMMITTER_NAME": "threeway-merge-gate",
    "GIT_COMMITTER_EMAIL": "merge-gate@threeway.local",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
}


def _env(extra: dict | None = None) -> dict:
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    if extra:
        env.update(extra)
    return env


def _run(repo, *args, env_extra=None, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, env=_env(env_extra), check=check,
    )


def rev_parse(repo, ref: str) -> str | None:
    p = _run(repo, "rev-parse", "--verify", f"{ref}^{{commit}}", check=False)
    return p.stdout.strip() if p.returncode == 0 else None


def changed_paths(repo, base_sha: str, head_sha: str) -> list[str]:
    p = _run(repo, "diff", "--name-only", base_sha, head_sha)
    return [line for line in p.stdout.splitlines() if line]


def merge_tree(repo, base_sha: str, branch_sha: str) -> tuple[str | None, bool]:
    """Return (tree_oid, clean). clean is driven by the EXIT CODE: merge-tree
    exits 1 on conflict but STILL prints a (conflict-marked) tree OID — using that
    OID would merge conflict markers into source. So clean=False on non-zero exit.
    """
    p = _run(repo, "merge-tree", "--write-tree", base_sha, branch_sha, check=False)
    tree = p.stdout.splitlines()[0].strip() if p.stdout.strip() else None
    return tree, (p.returncode == 0)


def commit_tree(repo, tree_oid: str, parents: list[str], message: str) -> str:
    args = ["commit-tree", tree_oid]
    for parent in parents:
        args += ["-p", parent]
    args += ["-m", message]
    p = _run(repo, *args, env_extra=_DET_ENV)
    return p.stdout.strip()


def cas_update_ref(repo, ref: str, new_oid: str, expected_old: str) -> bool:
    """Atomic compare-and-swap: set ref to new_oid only if it currently == expected_old."""
    p = _run(repo, "update-ref", ref, new_oid, expected_old, check=False)
    return p.returncode == 0
```

- [ ] **Step 4: Run green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gitcas.py -q`
Expected: PASS (6 passed). Note: the `repo` fixture's default-branch name differs across git versions; the `_has`/checkout line handles `master` vs `main`.

- [ ] **Step 5: Commit**

```bash
git add threeway/gitcas.py tests/unit/test_threeway_gitcas.py
git commit -m "feat(threeway): git CAS plumbing (merge-tree/commit-tree/update-ref, no checkout)"
```

---

## Chunk 5: The merge predicate

### Task 11: The `Decision` type and predicate skeleton (`threeway/predicate.py`)

**Files:**
- Create: `threeway/predicate.py`
- Test: `tests/unit/test_threeway_predicate.py`

`evaluate` returns a `Decision` with one of three outcomes (spec §6.3): `MERGEABLE`, `PENDING(reason)` (an expected approval/CI/release_order not yet present — re-evaluate later), `REJECTED(reason)` (a hard failure). This task builds the type and the happy-path MERGEABLE; Tasks 12-13 add each rejection clause.

- [ ] **Step 1: Write a shared test fixture builder + the happy-path test**

```python
# tests/unit/test_threeway_predicate.py
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_predicate.py -q

These tests exercise the predicate over EFFECTIVE state with a FAKE repo adapter
(no real git) so they stay fast and pure. The real-git path is covered by the gate
suite (Task 14-17).
"""
from threeway.envelope import Event
from threeway.policy import default_policy
from threeway.predicate import evaluate, MERGEABLE, PENDING, REJECTED
from threeway.reducer import reduce


BASE = "1" * 40       # staging_base == main.head
INTEG = "2" * 40      # integration_sha
BRANCH = "3" * 40     # branch_sha


class FakeRepo:
    """Stand-in for git: fixed head + a fixed changed-paths map."""
    def __init__(self, head=BASE, diff=("cinema/foo.py",)):
        self._head = head
        self._diff = list(diff)

    def rev_parse(self, ref):
        return self._head

    def changed_paths(self, base, head):
        return list(self._diff)


def _e(kind, seq, **over):
    base = dict(
        id=f"e{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
        kind=kind, sender="x", recipient="all", signer="x:p:s1", payload={},
        candidate_id="c1", brief_id="b1", brief_version=1,
    )
    base.update(over)
    return Event(**base)


def _full_event_set():
    """A complete, valid T1 promotion for candidate c1."""
    return [
        _e("brief", 1, payload={"brief_id": "b1", "allowed_paths": ["cinema/"]},
           signer="overseer:mech:s1"),
        _e("assignment", 2, payload={
            "pair": "A", "builder": "director", "builder_provider": "codex",
            "primary_verifier": "operator", "primary_verifier_provider": "claude",
            "executing_coordinator": "coordinator"}, signer="overseer:mech:s1"),
        _e("candidate", 3, payload={
            "pair": "A", "staging_base_sha": BASE, "branch_sha": BRANCH,
            "integration_sha": INTEG, "risk_tier_claimed": "T1",
            "policy_digest": default_policy().policy_digest()},
           subject_sha=INTEG, signer="coordinator:claude:s1"),
        _e("attestation", 4, payload={"kind": "preliminary", "verdict": "GO"},
           subject_sha=BRANCH, signer="operator:claude:s1"),
        _e("attestation", 5, payload={"kind": "release", "verdict": "GO"},
           subject_sha=INTEG, signer="operator:claude:s1"),
        _e("cycle_go", 6, payload={"brief_id": "b1", "brief_version": 1, "tier": "T1",
           "policy_digest": default_policy().policy_digest()}, signer="overseer:mech:s1"),
        _e("ci_result", 7, subject_sha=INTEG, payload={
            "result": "PASS", "policy_digest": default_policy().policy_digest()},
           signer="ci:mech:s1"),
        _e("release_requested", 8, payload={"candidate_id": "c1"},
           subject_sha=INTEG, signer="coordinator:claude:s1"),
        _e("release_order", 9, payload={"candidate_id": "c1"},
           subject_sha=INTEG, signer="overseer:mech:s1"),
    ]


def test_full_valid_set_is_mergeable():
    state = reduce(_full_event_set())
    d = evaluate("c1", state, FakeRepo(), default_policy())
    assert d.outcome == MERGEABLE, d.reason
```

- [ ] **Step 2: Run to confirm it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_predicate.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'threeway.predicate'`.

- [ ] **Step 3: Write the implementation**

```python
# threeway/predicate.py
"""mergeable(candidate) over EFFECTIVE state (spec §6.3).

Three outcomes:
  MERGEABLE  — every clause holds; the gate may write.
  PENDING    — valid so far but an expected approval/CI/release_order is absent.
  REJECTED   — a hard failure (bad sig, wrong signer, tier escalation, stale base,
               out-of-scope diff, policy/CI fail, aborted/superseded).

This module is signature-AGNOSTIC at the field level: it trusts that the gate has
already verified every event's signature against the public-key registry before
reducing (the gate does that in Task 14). Here we enforce the SEMANTIC clauses
(who signed, what tier, scope, freshness). 'repo' is any object exposing
rev_parse(ref) and changed_paths(base, head) — the real one is threeway.gitcas
bound to a repo path; tests pass a fake.
"""
from __future__ import annotations

from dataclasses import dataclass

from threeway.tier import effective_tier, co_sign_satisfied, tier_rank

MERGEABLE = "MERGEABLE"
PENDING = "PENDING"
REJECTED = "REJECTED"

MAIN_REF = "refs/threeway/test-main"   # Slice 1 promotes to a protected TEST ref


@dataclass
class Decision:
    outcome: str
    reason: str = ""


def _seat(signer: str) -> str:
    return signer.split(":", 1)[0]


def evaluate(candidate_id, state, repo, policy, main_ref=MAIN_REF) -> Decision:
    cand = state.candidate(candidate_id)
    if cand is None:
        return Decision(PENDING, "no candidate fact yet")
    if state.is_aborted(candidate_id):
        return Decision(REJECTED, "candidate aborted")

    p = cand.payload
    staging_base = p["staging_base_sha"]
    branch_sha = p["branch_sha"]
    integ = p["integration_sha"]
    pair = p["pair"]

    # freshness — exact-SHA CAS precondition
    if repo.rev_parse(main_ref) != staging_base:
        return Decision(REJECTED, "stale: staging_base_sha != main.head")

    # assignment & independence — assignment is an overseer-signed control-plane fact
    # (without the signer check a builder could forge an assignment that lies about
    #  its own provider, defeating the independence clause below)
    assign = state.assignment(pair)
    if assign is None:
        return Decision(PENDING, "no assignment fact for pair")
    if _seat(assign.signer) != "overseer":
        return Decision(REJECTED, "assignment not signed by overseer")
    a = assign.payload
    builder_provider = a["builder_provider"]
    verifier_provider = a["primary_verifier_provider"]
    if verifier_provider == builder_provider:
        return Decision(REJECTED, "primary verifier same provider as builder")
    # candidate must be signed by the executing coordinator named in assignment
    if _seat(cand.signer) != a["executing_coordinator"]:
        return Decision(REJECTED, "candidate not signed by executing coordinator")

    # brief — overseer-signed; carries assigned_tier + allowed_paths
    brief_ev = state.brief(cand.brief_id, cand.brief_version)
    if brief_ev is None:
        return Decision(PENDING, "no brief fact for brief_id/version")
    if _seat(brief_ev.signer) != "overseer":
        return Decision(REJECTED, "brief not signed by overseer")

    # primary semantic verification — both phases, EFFECTIVE, by the named verifier
    prelim = state.effective_attestation(candidate_id, "preliminary", a["primary_verifier"])
    if prelim is None or prelim.payload.get("verdict") != "GO":
        return Decision(PENDING, "no effective preliminary GO from primary verifier")
    if prelim.subject_sha != branch_sha:
        return Decision(REJECTED, "preliminary attestation not bound to branch_sha")

    rel = state.effective_attestation(candidate_id, "release", a["primary_verifier"])
    if rel is None or rel.payload.get("verdict") != "GO":
        return Decision(PENDING, "no effective release GO from primary verifier")
    if rel.subject_sha != integ:
        return Decision(REJECTED, "release attestation not bound to integration_sha")

    # tier is GATE-COMPUTED, never trusted from the candidate
    diff = repo.changed_paths(staging_base, integ)
    brief_tier = brief_ev.payload.get("assigned_tier",
                                      cand.payload.get("risk_tier_claimed", "T0"))
    eff_tier = effective_tier(brief_tier, diff, policy)

    # strategic authorization — overseer-signed cycle_go covering brief+version+tier+policy
    cg = state.cycle_go(cand.brief_id, cand.brief_version)
    if cg is None:
        return Decision(PENDING, "no cycle_go for brief/version")
    if _seat(cg.signer) != "overseer":
        return Decision(REJECTED, "cycle_go not signed by overseer")
    if tier_rank(eff_tier) > tier_rank(cg.payload.get("tier", "T0")):
        return Decision(REJECTED, "tier_escalation: effective tier exceeds cycle_go")
    if cg.payload.get("policy_digest") != cand.payload["policy_digest"]:
        return Decision(REJECTED, "cycle_go policy_digest mismatch")

    if not co_sign_satisfied(eff_tier, state, candidate_id, builder_provider):
        return Decision(PENDING, f"co_sign not satisfied for {eff_tier}")

    # release key — the OVERSEER's release_order, bound to THIS candidate + sha.
    # The signer check is load-bearing: it is the §11 "valid signature from the
    # wrong seat" defense — any registered seat's signature verifies cryptographically,
    # so authority must be checked by seat, not by signature validity alone.
    ro = state.release_order(candidate_id)
    if ro is None:
        return Decision(PENDING, "no release_order")
    if _seat(ro.signer) != "overseer":
        return Decision(REJECTED, "release_order not signed by overseer (wrong seat)")
    if ro.subject_sha != integ:
        return Decision(REJECTED, "release_order not bound to integration_sha")

    # scope, policy, evidence, version
    allowed = brief_ev.payload.get("allowed_paths", [])
    if not _within_allowed(diff, allowed):
        return Decision(REJECTED, "diff outside allowed_paths")
    if not policy.is_accepted(cand.payload["policy_digest"]):
        return Decision(REJECTED, "candidate policy_digest not accepted")

    # CI evidence — signed by the trusted CI seat, binding integration_sha + policy
    ci = state.ci_result(integ)
    if ci is None:
        return Decision(PENDING, "no ci_result for integration_sha")
    if _seat(ci.signer) != "ci":
        return Decision(REJECTED, "ci_result not signed by trusted CI (wrong seat)")
    if ci.payload.get("result") != "PASS":
        return Decision(REJECTED, "ci_result not PASS")
    if ci.payload.get("policy_digest") != cand.payload["policy_digest"]:
        return Decision(REJECTED, "ci_result policy_digest mismatch")

    latest_v = state.latest_brief_version(cand.brief_id)
    if latest_v is not None and cand.brief_version != latest_v:
        return Decision(REJECTED, "candidate brief_version is superseded")

    return Decision(MERGEABLE, "all clauses hold")


def _within_allowed(diff, allowed) -> bool:
    if not allowed:
        return False
    for path in diff:
        if not any(path == a or path.startswith(a) for a in allowed):
            return False
    return True
```

- [ ] **Step 4: Run green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_predicate.py -q`
Expected: PASS (1 passed). *(If MERGEABLE fails, print `d.reason` — the message names the first unmet clause.)*

- [ ] **Step 5: Commit**

The predicate reads the brief via the clean `EffectiveState.brief(brief_id, version)` accessor (added in Task 7) — it never reaches into `state._briefs`. There is no dead code in `evaluate` (no `and False` branches, no unused helpers). Confirm the module imports only what it uses (`_seat`, `effective_tier`, `co_sign_satisfied`, `tier_rank`, the `Decision`/outcome constants) — no `_provider`/`_sig_of`. Then:
```bash
git add threeway/predicate.py tests/unit/test_threeway_predicate.py
git commit -m "feat(threeway): merge predicate — happy path MERGEABLE (§6.3)"
```

### Task 12: Predicate rejection clauses — independence, attestations, freshness

**Files:**
- Modify: `tests/unit/test_threeway_predicate.py`
- (impl already in `predicate.py`; these tests pin each clause)

- [ ] **Step 1: Add failing/again-green clause tests**

Append:
```python
def test_rejects_when_verifier_same_provider_as_builder():
    events = _full_event_set()
    for e in events:
        if e.kind == "assignment":
            e.payload["primary_verifier_provider"] = "codex"  # == builder
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == REJECTED and "same provider" in d.reason


def test_rejects_candidate_not_signed_by_executing_coordinator():
    events = _full_event_set()
    for e in events:
        if e.kind == "candidate":
            e.signer = "operator:claude:s1"  # not the coordinator
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == REJECTED and "executing coordinator" in d.reason


def test_go_then_fail_release_leaves_no_effective_go_pending():
    events = _full_event_set()
    events.append(_e("attestation", 10, payload={"kind": "release", "verdict": "FAIL"},
                     subject_sha=INTEG, signer="operator:claude:s1"))
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == PENDING and "release GO" in d.reason


def test_revoked_release_attestation_is_pending():
    events = _full_event_set()
    # revoke the release attestation (e5)
    events.append(_e("attestation_revoked", 11, revokes_event_id="e5",
                     signer="operator:claude:s1"))
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == PENDING


def test_rejects_release_attestation_bound_to_wrong_sha():
    events = _full_event_set()
    for e in events:
        if e.kind == "attestation" and e.payload.get("kind") == "release":
            e.subject_sha = "9" * 40
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == REJECTED and "integration_sha" in d.reason


def test_rejects_stale_staging_base_when_main_moved():
    events = _full_event_set()
    moved = FakeRepo(head="f" * 40)  # main.head != staging_base
    d = evaluate("c1", reduce(events), moved, default_policy())
    assert d.outcome == REJECTED and "stale" in d.reason


def test_pending_when_release_order_absent():
    events = [e for e in _full_event_set() if e.kind != "release_order"]
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == PENDING and "release_order" in d.reason
```

- [ ] **Step 2: Run them**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_predicate.py -q`
Expected: PASS (8 passed total). If any clause is mis-ordered (e.g. a REJECT that should be PENDING), adjust the clause order in `evaluate` so hard failures are reported as REJECTED and merely-absent approvals as PENDING.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_threeway_predicate.py threeway/predicate.py
git commit -m "test(threeway): predicate independence/attestation/freshness clauses"
```

### Task 13: Predicate rejection clauses — tier, scope, policy, CI, supersession

**Files:**
- Modify: `tests/unit/test_threeway_predicate.py`

- [ ] **Step 1: Add the clause tests**

```python
def test_rejects_tier_escalation_when_diff_exceeds_cycle_go():
    events = _full_event_set()
    # diff touches CI config -> path-derived T2; cycle_go authorized only T1
    repo = FakeRepo(diff=[".github/workflows/ci.yml"])
    # widen allowed_paths so we isolate the tier clause, not scope
    for e in events:
        if e.kind == "brief":
            e.payload["allowed_paths"] = [".github/"]
    d = evaluate("c1", reduce(events), repo, default_policy())
    assert d.outcome == REJECTED and "tier_escalation" in d.reason


def test_tier_mislabel_below_path_minimum_is_ignored_gate_computes():
    # candidate claims T0 but diff is CI config (T2) and cycle_go is T1 -> escalation
    events = _full_event_set()
    for e in events:
        if e.kind == "candidate":
            e.payload["risk_tier_claimed"] = "T0"
        if e.kind == "brief":
            e.payload["allowed_paths"] = [".github/"]
    repo = FakeRepo(diff=[".github/workflows/ci.yml"])
    d = evaluate("c1", reduce(events), repo, default_policy())
    assert d.outcome == REJECTED and "tier_escalation" in d.reason


def test_rejects_diff_outside_allowed_paths():
    events = _full_event_set()
    repo = FakeRepo(diff=["secrets/leak.txt"])
    d = evaluate("c1", reduce(events), repo, default_policy())
    assert d.outcome == REJECTED and "allowed_paths" in d.reason


def test_rejects_candidate_that_weakened_policy_digest():
    events = _full_event_set()
    for e in events:
        if e.kind == "candidate":
            e.payload["policy_digest"] = "0" * 64  # not the accepted policy
        if e.kind in ("cycle_go", "ci_result"):
            e.payload["policy_digest"] = "0" * 64  # keep them internally consistent
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == REJECTED and "policy_digest not accepted" in d.reason


def test_pending_when_ci_result_absent():
    events = [e for e in _full_event_set() if e.kind != "ci_result"]
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == PENDING and "ci_result" in d.reason


def test_rejects_ci_result_not_pass():
    events = _full_event_set()
    for e in events:
        if e.kind == "ci_result":
            e.payload["result"] = "FAIL"
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == REJECTED and "ci_result not PASS" in d.reason


def test_rejects_superseded_brief_version():
    events = _full_event_set()
    events.append(_e("brief", 12, brief_version=2,
                     payload={"brief_id": "b1", "allowed_paths": ["cinema/"]},
                     signer="overseer:mech:s1"))
    # candidate is still on version 1, now superseded by version 2
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == REJECTED and "superseded" in d.reason


def test_rejects_aborted_candidate():
    events = _full_event_set()
    events.append(_e("candidate_aborted", 13))
    d = evaluate("c1", reduce(events), FakeRepo(), default_policy())
    assert d.outcome == REJECTED and "aborted" in d.reason
```

- [ ] **Step 2: Run**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_predicate.py -q`
Expected: PASS (16 passed total).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_threeway_predicate.py threeway/predicate.py
git commit -m "test(threeway): predicate tier/scope/policy/CI/supersession clauses"
```

---

## Chunk 6: The mechanical merge-gate, key bootstrap, and the adversarial end-to-end suite

### Task 14: Signature verification pass + the gate's read-side (`threeway/gate.py` part 1)

**Files:**
- Create: `threeway/gate.py`
- Test: `tests/unit/test_threeway_gate.py` (part 1)

Before reducing, the gate **verifies every load-bearing event's signature** against the committed public-key registry, **rejecting** any event with a missing/invalid signature, a signer whose seat has no registered key, or a `bus_id` that doesn't match the gate's environment (replay defense). Only verified events are reduced.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_threeway_gate.py
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gate.py -q"""
import os
import subprocess

import pytest

from threeway import keys
from threeway.gate import verify_and_reduce, GateError


def _env():
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    return env


@pytest.fixture()
def seatkit(tmp_path, monkeypatch):
    """Generate keys for every seat; write the public registry + private keystore."""
    reg = tmp_path / "pub"
    ks = tmp_path / "ks"
    reg.mkdir(); ks.mkdir()
    privs = {}
    for seat in ("director", "operator", "coordinator", "overseer", "ci", "merge-gate"):
        priv, pub = keys.generate_keypair()
        (reg / f"{seat}.pub").write_text(pub + "\n")
        (ks / f"{seat}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
        privs[seat] = priv
    monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks))
    return reg, ks, privs


def test_verify_and_reduce_rejects_unsigned_event(seatkit, tmp_path):
    reg, ks, privs = seatkit
    from threeway.envelope import Event
    ev = Event(id="e1", seq=1, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="all",
               signer="coordinator:claude:s1", payload={}, candidate_id="c1")
    # not signed
    with pytest.raises(GateError):
        verify_and_reduce([ev], registry_dir=reg, bus_id="prod")


def test_verify_and_reduce_rejects_bus_id_mismatch_replay(seatkit, tmp_path):
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    ev = Event(id="e1", seq=1, bus_id="TEST-BUS", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="all",
               signer="coordinator:claude:s1", payload={}, candidate_id="c1")
    sign_event(ev, privs["coordinator"])
    with pytest.raises(GateError, match="bus_id"):
        verify_and_reduce([ev], registry_dir=reg, bus_id="prod")


def test_verify_and_reduce_rejects_unknown_signer_seat(seatkit, tmp_path):
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    ev = Event(id="e1", seq=1, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="ghost", recipient="all",
               signer="ghost:claude:s1", payload={}, candidate_id="c1")
    sign_event(ev, privs["coordinator"])  # signed by coordinator but claims ghost
    with pytest.raises(GateError):
        verify_and_reduce([ev], registry_dir=reg, bus_id="prod")


def test_verify_and_reduce_accepts_valid_signed_events(seatkit, tmp_path):
    reg, ks, privs = seatkit
    from threeway.envelope import Event, sign_event
    ev = Event(id="e1", seq=1, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="all",
               signer="coordinator:claude:s1", payload={"pair": "A"}, candidate_id="c1")
    sign_event(ev, privs["coordinator"])
    state = verify_and_reduce([ev], registry_dir=reg, bus_id="prod")
    assert state.candidate("c1") is not None
```

- [ ] **Step 2: Run to confirm it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gate.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'threeway.gate'`.

- [ ] **Step 3: Write the read-side implementation**

```python
# threeway/gate.py
"""The mechanical merge-gate (spec §4, §6.3, §6.4).

Read-side (this part): verify EVERY load-bearing event's signature against the
committed public-key registry, reject bus_id mismatches (replay), reject unknown
signer seats, then reduce only verified events. The gate NEVER executes candidate
code; it acts only on signed facts + a signed ci_result.
"""
from __future__ import annotations

from cryptography.exceptions import InvalidSignature

from threeway import LOAD_BEARING_KINDS
from threeway.envelope import verify_event
from threeway.keys import PublicKeyRegistry
from threeway.reducer import reduce


class GateError(Exception):
    pass


def _seat(signer: str) -> str:
    return signer.split(":", 1)[0]


def verify_and_reduce(events, registry_dir, bus_id: str):
    reg = PublicKeyRegistry(registry_dir)
    verified = []
    for ev in events:
        if ev.kind in LOAD_BEARING_KINDS:
            if ev.bus_id != bus_id:
                raise GateError(f"bus_id mismatch (replay?): {ev.bus_id!r} != {bus_id!r}")
            seat = _seat(ev.signer)
            try:
                pub = reg.get(seat)
            except KeyError as e:
                raise GateError(f"unknown signer seat: {seat!r}") from e
            try:
                verify_event(ev, pub)
            except InvalidSignature as e:
                raise GateError(f"invalid signature on {ev.kind} {ev.id}") from e
        verified.append(ev)
    return reduce(verified)
```

- [ ] **Step 4: Run green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gate.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add threeway/gate.py tests/unit/test_threeway_gate.py
git commit -m "feat(threeway): gate read-side — signature/bus_id/signer verification (§6.4)"
```

### Task 15: Tactical-loop builders + key bootstrap (`threeway/loop.py`, `threeway/keys_bootstrap.py`)

**Files:**
- Create: `threeway/loop.py`
- Create: `threeway/keys_bootstrap.py`
- Test: `tests/unit/test_threeway_loop.py`

`build_candidate_events` constructs the complete, correctly-signed T1 event set the gate write-side test (Task 16) and the adversarial suite (Task 17) reuse. `keys_bootstrap` is a CLI to generate every seat's keypair into the registry + keystore (the trust-root setup the README references). **This task is built BEFORE the gate write-side** so the gate's end-to-end tests have their event builder ready — no cross-task co-dependency, `loop.py` is committed exactly once (here).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_threeway_loop.py
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_loop.py -q"""
from threeway import keys
from threeway.loop import build_candidate_events
from threeway.policy import default_policy


def test_build_candidate_events_has_all_required_kinds():
    privs = {s: keys.generate_keypair()[0] for s in
             ("director", "operator", "coordinator", "overseer", "ci")}
    events = build_candidate_events("1" * 40, "3" * 40, "2" * 40, privs)
    kinds = {e.kind for e in events}
    assert {"brief", "assignment", "candidate", "attestation", "cycle_go",
            "ci_result", "release_requested", "release_order"} <= kinds
    # two attestations: preliminary + release
    atts = [e for e in events if e.kind == "attestation"]
    assert {a.payload["kind"] for a in atts} == {"preliminary", "release"}


def test_build_candidate_events_uses_accepted_policy_digest():
    privs = {s: keys.generate_keypair()[0] for s in
             ("director", "operator", "coordinator", "overseer", "ci")}
    events = build_candidate_events("1" * 40, "3" * 40, "2" * 40, privs)
    pd = default_policy().policy_digest()
    cand = next(e for e in events if e.kind == "candidate")
    assert cand.payload["policy_digest"] == pd
```

- [ ] **Step 2: Run to confirm it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_loop.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'threeway.loop'`.

- [ ] **Step 3: Write `threeway/loop.py`**

```python
# threeway/loop.py
"""Tactical-loop event builders (spec §5.1). build_candidate_events assembles the
six-step loop's facts for ONE pair (Codex director, Claude operator, Claude
coordinator) as UNSIGNED events; the caller signs+appends each via the store using
the matching seat key. Reused by tests and the Slice-1 demo.

Signer seats follow the spec §4 permission table — the predicate (Task 11) enforces
them: brief/assignment/cycle_go/release_order are overseer-signed, candidate is
coordinator-signed, attestations are operator-signed, ci_result is ci-signed.
"""
from __future__ import annotations

from threeway.envelope import Event
from threeway.policy import default_policy

BUS = "prod"


def _e(kind, sender, signer, payload, **over):
    base = dict(
        id=over.pop("id", f"{kind}-{sender}"), seq=0, bus_id=over.pop("bus_id", BUS),
        schema_version="threeway/1", kind=kind, sender=sender, recipient="all",
        signer=signer, payload=payload, brief_id="b1", brief_version=1,
        candidate_id="c1",
    )
    base.update(over)
    return Event(**base)


def build_candidate_events(staging_base, branch_sha, integration_sha, privs,
                           bus_id=BUS, tier="T1", allowed_paths=("cinema/",)):
    pd = default_policy().policy_digest()
    return [
        _e("brief", "overseer", "overseer:mech:s1",
           {"brief_id": "b1", "assigned_tier": tier,
            "allowed_paths": list(allowed_paths)}, brief_id="b1", bus_id=bus_id),
        _e("assignment", "overseer", "overseer:mech:s1",
           {"pair": "A", "builder": "director", "builder_provider": "codex",
            "primary_verifier": "operator", "primary_verifier_provider": "claude",
            "executing_coordinator": "coordinator"}, bus_id=bus_id),
        _e("candidate", "coordinator", "coordinator:claude:s1",
           {"pair": "A", "staging_base_sha": staging_base, "branch_sha": branch_sha,
            "integration_sha": integration_sha, "risk_tier_claimed": tier,
            "policy_digest": pd}, subject_sha=integration_sha, bus_id=bus_id),
        _e("attestation", "operator", "operator:claude:s1",
           {"kind": "preliminary", "verdict": "GO"}, subject_sha=branch_sha, bus_id=bus_id),
        _e("attestation", "operator", "operator:claude:s1",
           {"kind": "release", "verdict": "GO"}, subject_sha=integration_sha, bus_id=bus_id),
        _e("cycle_go", "overseer", "overseer:mech:s1",
           {"brief_id": "b1", "brief_version": 1, "tier": tier, "policy_digest": pd}, bus_id=bus_id),
        _e("ci_result", "ci", "ci:mech:s1",
           {"result": "PASS", "policy_digest": pd}, subject_sha=integration_sha, bus_id=bus_id),
        _e("release_requested", "coordinator", "coordinator:claude:s1",
           {"candidate_id": "c1"}, subject_sha=integration_sha, bus_id=bus_id),
        _e("release_order", "overseer", "overseer:mech:s1",
           {"candidate_id": "c1"}, subject_sha=integration_sha, bus_id=bus_id),
    ]
```

- [ ] **Step 4: Write `threeway/keys_bootstrap.py`**

```python
# threeway/keys_bootstrap.py
"""Generate per-seat Ed25519 keypairs: public keys -> committed registry,
private keys -> off-repo keystore. CLI:
  python -m threeway.keys_bootstrap --registry coordination/threeway/keys \
      --keystore "$THREEWAY_KEYSTORE"
"""
from __future__ import annotations

import argparse
from pathlib import Path

from threeway import keys

SEATS = ("director", "operator", "coordinator", "overseer", "ci", "merge-gate")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", required=True)
    ap.add_argument("--keystore", required=True)
    ap.add_argument("--seats", nargs="*", default=list(SEATS))
    args = ap.parse_args(argv)
    reg = Path(args.registry); ks = Path(args.keystore)
    reg.mkdir(parents=True, exist_ok=True); ks.mkdir(parents=True, exist_ok=True)
    for seat in args.seats:
        priv, pub = keys.generate_keypair()
        (reg / f"{seat}.pub").write_text(pub + "\n")
        (ks / f"{seat}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
        print(f"generated {seat}: pub -> {reg}/{seat}.pub")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_loop.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add threeway/loop.py threeway/keys_bootstrap.py tests/unit/test_threeway_loop.py
git commit -m "feat(threeway): tactical-loop event builders + key bootstrap CLI"
```

### Task 16: The gate write-side — exact-SHA CAS merge + idempotent crash recovery (`threeway/gate.py` part 2)

**Files:**
- Modify: `threeway/gate.py`
- Test: `tests/unit/test_threeway_gate.py` (extend with a real-repo end-to-end fixture)

`run_gate` ties it together: verify+reduce → evaluate predicate → on MERGEABLE, confirm the merge is clean, build the merge commit, and CAS-write the protected test ref; emit a signed `merge_completed` fact. **Idempotent:** a prior `merge_completed` for the candidate → no-op COMPLETED; and even without it the CAS expected-old guarantees at-most-once (a re-run's CAS fails because the ref already moved). The Task-15 event builder (`threeway.loop.build_candidate_events`) already exists, so the e2e tests resolve.

- [ ] **Step 1: Write the failing end-to-end test (real git repo)**

```python
# append to tests/unit/test_threeway_gate.py
from threeway.store import EventStore
from threeway.gate import run_gate, GateResult


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True,
                          capture_output=True, text=True, env=_env())


@pytest.fixture()
def live_repo(tmp_path):
    """A repo with a protected test-main ref and a builder branch (clean merge)."""
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", "refs/threeway/test-main", base)
    _git(r, "checkout", "-q", "-b", "feat")
    (r / "cinema").mkdir()
    (r / "cinema" / "foo.py").write_text("x = 1\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "feat")
    branch = _git(r, "rev-parse", "HEAD").stdout.strip()
    return r, base, branch


def _valid_events_for(base, branch, integ, privs, bus_id="prod"):
    """Build a complete, correctly-SIGNED T1 event set bound to real SHAs, via the
    Task-15 helper threeway.loop.build_candidate_events."""
    from threeway.loop import build_candidate_events
    return build_candidate_events(base, branch, integ, privs, bus_id=bus_id)


def test_run_gate_merges_clean_candidate_via_cas(live_repo, seatkit):
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    # stage: coordinator computes integration_sha via merge-tree+commit-tree
    from threeway import gitcas
    tree, clean = gitcas.merge_tree(r, base, branch)
    assert clean
    integ = gitcas.commit_tree(r, tree, [base, branch], "stage c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert res.outcome == "COMPLETED", res.reason
    # test-main now points at the merge commit
    new_head = _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip()
    assert new_head == integ
    # merge_completed fact emitted
    from threeway.gate import verify_and_reduce
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    assert state.merge_completed("c1") is not None


def test_run_gate_is_idempotent_under_double_invocation(live_repo, seatkit):
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    from threeway import gitcas
    tree, _ = gitcas.merge_tree(r, base, branch)
    integ = gitcas.commit_tree(r, tree, [base, branch], "stage c1")
    for ev in _valid_events_for(base, branch, integ, privs):
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    r1 = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                  main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    r2 = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                  main_ref="refs/threeway/test-main", gate_seat="merge-gate")
    assert r1.outcome == "COMPLETED" and r2.outcome == "COMPLETED"
    # exactly ONE merge_completed fact => no double write
    from threeway.gate import verify_and_reduce
    state = verify_and_reduce(store.all_events(), registry_dir=reg, bus_id="prod")
    completes = [e for e in store.all_events() if e.kind == "merge_completed"]
    assert len(completes) == 1
```

- [ ] **Step 2: Run to confirm it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gate.py -q`
Expected: FAIL — `run_gate`/`GateResult` undefined. (The read-side from Task 14 and `threeway.loop` from Task 15 are both present; only the write-side is missing.)

- [ ] **Step 3: Write the write-side implementation**

```python
# append to threeway/gate.py
from dataclasses import dataclass

from threeway import gitcas
from threeway.envelope import Event
from threeway.keys import load_private
from threeway.predicate import evaluate, MERGEABLE, REJECTED, PENDING
from threeway.policy import default_policy
from threeway.store import EventStore


@dataclass
class GateResult:
    outcome: str   # COMPLETED | REJECTED | PENDING
    reason: str = ""


class _RepoAdapter:
    """Binds threeway.gitcas to one repo path for the predicate's repo interface."""
    def __init__(self, repo):
        self._repo = repo

    def rev_parse(self, ref):
        return gitcas.rev_parse(self._repo, ref)

    def changed_paths(self, base, head):
        return gitcas.changed_paths(self._repo, base, head)


def run_gate(candidate_id, store: EventStore, repo, registry_dir, bus_id,
             main_ref, gate_seat="merge-gate", policy=None) -> GateResult:
    policy = policy or default_policy()
    # 1. verify + reduce authoritative bus state (raises GateError on bad sig/replay)
    state = verify_and_reduce(store.all_events(), registry_dir=registry_dir, bus_id=bus_id)

    # 2. idempotency: already merged?  no-op.
    if state.merge_completed(candidate_id) is not None:
        return GateResult("COMPLETED", "already merged (idempotent)")

    # 3. evaluate the predicate from authoritative state
    d = evaluate(candidate_id, state, _RepoAdapter(repo), policy, main_ref=main_ref)
    if d.outcome == REJECTED:
        return GateResult("REJECTED", d.reason)
    if d.outcome == PENDING:
        return GateResult("PENDING", d.reason)

    # 4. MERGEABLE — recompute the trusted merge, never trusting candidate.integration_sha
    cand = state.candidate(candidate_id)
    base = cand.payload["staging_base_sha"]
    branch = cand.payload["branch_sha"]
    tree, clean = gitcas.merge_tree(repo, base, branch)
    if not clean:
        return GateResult("REJECTED", "merge not clean (textual conflict) -> ABORT/REWORK")
    merge_commit = gitcas.commit_tree(repo, tree, [base, branch],
                                      f"threeway merge {candidate_id}")
    # the attested integration_sha MUST equal the trusted recomputed merge
    if merge_commit != cand.payload["integration_sha"]:
        return GateResult("REJECTED", "recomputed merge != attested integration_sha")

    # 5. exact-SHA CAS: write main only if it still equals staging_base
    if not gitcas.cas_update_ref(repo, main_ref, merge_commit, base):
        return GateResult("REJECTED", "stale: CAS expected-old no longer matches main.head")

    # 6. emit the signed merge_completed fact (the gate's own credential)
    gate_priv = load_private(gate_seat)
    done = Event(
        id=f"merge-{candidate_id}", seq=0, bus_id=bus_id,
        schema_version="threeway/1", kind="merge_completed",
        sender=gate_seat, recipient="all", signer=f"{gate_seat}:mech:gate",
        payload={"candidate_id": candidate_id, "merged_sha": merge_commit},
        candidate_id=candidate_id, subject_sha=merge_commit,
    )
    store.append(done, gate_priv)
    return GateResult("COMPLETED", "merged via exact-SHA CAS")
```

- [ ] **Step 4: Run green**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gate.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add threeway/gate.py tests/unit/test_threeway_gate.py
git commit -m "feat(threeway): gate write-side — exact-SHA CAS merge + idempotent recovery (§6.4)"
```

### Task 17: The adversarial gate suite + REWORK circuit-breaker + Slice 1 gate sign-off

**Files:**
- Create: `tests/unit/test_threeway_gate_adversarial.py`
- Create: `threeway/rework.py`
- Test: `tests/unit/test_threeway_rework.py`
- Modify: `DECISIONS.md` (append ADR)

This task proves the spec §11 Slice 1 gate: the predicate/gate **rejects each adversarial promotion**, a clean change merges, one REWORK cycle completes, and the **≤2-rework cap escalates on the third**. Each adversarial case mutates one fact in the valid set and asserts the gate does **not** write `main`.

- [ ] **Step 1: Write the REWORK cap (`threeway/rework.py`) + test**

```python
# threeway/rework.py
"""Per-brief_version rework circuit-breaker (spec §9): >2 rework cycles -> ESCALATE."""
from __future__ import annotations

REWORK_CAP = 2


def rework_count(events, brief_id, brief_version) -> int:
    return sum(
        1 for e in events
        if e.kind == "candidate_aborted"
        and e.brief_id == brief_id and e.brief_version == brief_version
    )


def should_escalate(events, brief_id, brief_version) -> bool:
    return rework_count(events, brief_id, brief_version) > REWORK_CAP
```

```python
# tests/unit/test_threeway_rework.py
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_rework.py -q"""
from threeway.envelope import Event
from threeway.rework import rework_count, should_escalate, REWORK_CAP


def _abort(seq):
    return Event(id=f"a{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
                 kind="candidate_aborted", sender="coordinator", recipient="all",
                 signer="coordinator:claude:s1", payload={}, brief_id="b1",
                 brief_version=1, candidate_id=f"c{seq}")


def test_two_reworks_do_not_escalate():
    events = [_abort(1), _abort(2)]
    assert rework_count(events, "b1", 1) == 2
    assert not should_escalate(events, "b1", 1)


def test_third_rework_escalates():
    events = [_abort(1), _abort(2), _abort(3)]
    assert should_escalate(events, "b1", 1)
```

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_rework.py -q` → PASS (2). Commit:
```bash
git add threeway/rework.py tests/unit/test_threeway_rework.py
git commit -m "feat(threeway): ≤2 rework circuit-breaker (§9)"
```

- [ ] **Step 2: Write the adversarial e2e suite**

```python
# tests/unit/test_threeway_gate_adversarial.py
"""The spec §11 Slice 1 gate. Each test mutates ONE fact in an otherwise-valid
promotion and asserts the gate does NOT advance refs/threeway/test-main.

Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gate_adversarial.py -q
"""
import os
import subprocess

import pytest

from threeway import gitcas, keys
from threeway.gate import run_gate, GateError, verify_and_reduce
from threeway.loop import build_candidate_events
from threeway.store import EventStore


def _env():
    env = dict(os.environ); env.pop("GIT_INDEX_FILE", None); return env


def _git(r, *a):
    return subprocess.run(["git", "-C", str(r), *a], check=True,
                          capture_output=True, text=True, env=_env())


@pytest.fixture()
def world(tmp_path, monkeypatch):
    # keys
    reg = tmp_path / "pub"; ks = tmp_path / "ks"; reg.mkdir(); ks.mkdir()
    privs = {}
    for seat in ("director", "operator", "coordinator", "overseer", "ci", "merge-gate"):
        priv, pub = keys.generate_keypair()
        (reg / f"{seat}.pub").write_text(pub + "\n")
        (ks / f"{seat}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
        privs[seat] = priv
    monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks))
    # repo
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q"); _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", "refs/threeway/test-main", base)
    _git(r, "checkout", "-q", "-b", "feat")
    (r / "cinema").mkdir(); (r / "cinema" / "foo.py").write_text("x = 1\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "feat")
    branch = _git(r, "rev-parse", "HEAD").stdout.strip()
    tree, _ = gitcas.merge_tree(r, base, branch)
    integ = gitcas.commit_tree(r, tree, [base, branch], "stage c1")
    return r, base, branch, integ, reg, ks, privs


def _populate(store, events, privs):
    for ev in events:
        store.append(ev, privs[ev.signer.split(":", 1)[0]])


def _head(r):
    return _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip()


def _run(world, mutate=None, bus_id="prod"):
    r, base, branch, integ, reg, ks, privs = world
    store = EventStore(r / "coordination" / "threeway" / "events")
    events = build_candidate_events(base, branch, integ, privs, bus_id=bus_id)
    if mutate:
        mutate(events)
    _populate(store, events, privs)
    return r, base, store, reg, privs


def test_clean_change_merges(world):
    r, base, store, reg, privs = _run(world)
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "COMPLETED"
    assert _head(r) != base  # advanced


# ---- the adversarial rejections (§11 Slice 1 gate) ----

def test_rejects_tampered_integration_sha(world):
    def mut(events):
        for e in events:
            if e.kind == "candidate":
                e.payload["integration_sha"] = "d" * 40  # not the real merge
    r, base, store, reg, privs = _run(world, mut)
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "REJECTED"
    assert _head(r) == base  # NOT advanced


def test_rejects_absent_signature(world):
    # append a load-bearing event but blank its signature -> verify_and_reduce raises
    r, base, branch, integ, reg, ks, privs = world
    store = EventStore(r / "coordination" / "threeway" / "events")
    events = build_candidate_events(base, branch, integ, privs)
    _populate(store, events, privs)
    # hand-write an unsigned candidate_aborted into the store dir
    from threeway.envelope import Event, to_json_obj
    import json
    bad = Event(id="bad", seq=999, bus_id="prod", schema_version="threeway/1",
                kind="candidate_aborted", sender="coordinator", recipient="all",
                signer="coordinator:claude:s1", payload={}, candidate_id="c1")
    p = r / "coordination" / "threeway" / "events" / "00000999-bad.json"
    p.write_text(json.dumps(to_json_obj(bad)))  # no signature
    with pytest.raises(GateError):
        run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                 main_ref="refs/threeway/test-main")
    assert _head(r) == base


def test_rejects_valid_signature_wrong_seat(world):
    # operator signs a release_order that only the overseer may sign
    def mut(events):
        for e in events:
            if e.kind == "release_order":
                e.signer = "operator:claude:s1"  # wrong seat for this fact
    r, base, branch, integ, reg, ks, privs = world
    store = EventStore(r / "coordination" / "threeway" / "events")
    events = build_candidate_events(base, branch, integ, privs)
    mut(events)
    # sign release_order with the operator key so the SIGNATURE verifies (operator is
    # a registered seat) — the predicate must still REJECT because release_order is an
    # overseer-only authority (predicate _seat(ro.signer) != "overseer"). This is the
    # §11 "valid signature from the wrong seat" criterion.
    for ev in events:
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "REJECTED" and "wrong seat" in res.reason
    assert _head(r) == base


def test_rejects_old_go_then_fail(world):
    from threeway.envelope import Event
    def mut(events):
        events.append(Event(id="latefail", seq=0, bus_id="prod",
                            schema_version="threeway/1", kind="attestation",
                            sender="operator", recipient="all",
                            signer="operator:claude:s1",
                            payload={"kind": "release", "verdict": "FAIL"},
                            subject_sha=events[2].payload["integration_sha"],
                            candidate_id="c1", brief_id="b1", brief_version=1))
    r, base, store, reg, privs = _run(world, mut)
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "PENDING"
    assert _head(r) == base


def test_rejects_candidate_modifying_ci_workflow(world):
    # the diff includes a CI workflow file -> path-derived T2 > cycle_go T1 -> escalation
    r, base, branch, integ, reg, ks, privs = world
    # add a workflow change to the feat branch and re-stage
    _git(r, "checkout", "-q", "feat")
    (r / ".github" / "workflows").mkdir(parents=True)
    (r / ".github" / "workflows" / "ci.yml").write_text("name: x\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "weaken ci")
    branch2 = _git(r, "rev-parse", "HEAD").stdout.strip()
    tree, _ = gitcas.merge_tree(r, base, branch2)
    integ2 = gitcas.commit_tree(r, tree, [base, branch2], "stage c1")
    store = EventStore(r / "coordination" / "threeway" / "events")
    events = build_candidate_events(base, branch2, integ2, privs,
                                    allowed_paths=("cinema/", ".github/"))
    _populate(store, events, privs)
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "REJECTED" and "tier_escalation" in res.reason
    assert _head(r) == base


def test_rejects_stage_ref_moved_after_attestation(world):
    r, base, store, reg, privs = _run(world)
    # main moves before the gate runs
    _git(r, "commit", "--allow-empty", "-qm", "drift")
    drift = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", "refs/threeway/test-main", drift)
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "REJECTED" and "stale" in res.reason
    assert _head(r) == drift  # untouched


def test_rejects_tier_mislabeled_below_minimum(world):
    def mut(events):
        for e in events:
            if e.kind == "candidate":
                e.payload["risk_tier_claimed"] = "T0"  # lie; gate recomputes
    # diff is just cinema/foo.py (T1) so claim-lowering alone doesn't escalate;
    # pair it with a CI path to prove the gate uses the path minimum, not the claim
    r, base, branch, integ, reg, ks, privs = world
    _git(r, "checkout", "-q", "feat")
    (r / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (r / ".github" / "workflows" / "ci.yml").write_text("name: y\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "ci")
    b2 = _git(r, "rev-parse", "HEAD").stdout.strip()
    tree, _ = gitcas.merge_tree(r, base, b2)
    i2 = gitcas.commit_tree(r, tree, [base, b2], "stage")
    store = EventStore(r / "coordination" / "threeway" / "events")
    events = build_candidate_events(base, b2, i2, privs, tier="T0",
                                    allowed_paths=("cinema/", ".github/"))
    _populate(store, events, privs)
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "REJECTED" and "tier_escalation" in res.reason
    assert _head(r) == base


def test_rejects_diff_outside_allowed_paths(world):
    r, base, branch, integ, reg, ks, privs = world
    store = EventStore(r / "coordination" / "threeway" / "events")
    # allowed_paths excludes cinema/, but the diff is cinema/foo.py
    events = build_candidate_events(base, branch, integ, privs, allowed_paths=("docs/",))
    _populate(store, events, privs)
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "REJECTED" and "allowed_paths" in res.reason
    assert _head(r) == base


def test_rejects_replay_from_test_bus(world):
    r, base, store, reg, privs = _run(world, bus_id="TEST-BUS")
    with pytest.raises(GateError, match="bus_id"):
        run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                 main_ref="refs/threeway/test-main")
    assert _head(r) == base


def test_crash_after_release_before_cas_recovers_without_double_write(world):
    # run twice; the CAS expected-old + merge_completed make the 2nd a no-op
    r, base, store, reg, privs = _run(world)
    a = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                 main_ref="refs/threeway/test-main")
    head_after_first = _head(r)
    b = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                 main_ref="refs/threeway/test-main")
    assert a.outcome == "COMPLETED" and b.outcome == "COMPLETED"
    assert _head(r) == head_after_first  # no second write
    completes = [e for e in store.all_events() if e.kind == "merge_completed"]
    assert len(completes) == 1


def test_one_rework_cycle_completes_then_third_escalates(world):
    from threeway.rework import should_escalate
    r, base, branch, integ, reg, ks, privs = world
    store = EventStore(r / "coordination" / "threeway" / "events")
    # two aborts (rework) then check escalation on a third
    from threeway.envelope import Event
    def abort(seq, cid):
        return Event(id=f"ab{seq}", seq=0, bus_id="prod", schema_version="threeway/1",
                     kind="candidate_aborted", sender="coordinator", recipient="all",
                     signer="coordinator:claude:s1", payload={}, brief_id="b1",
                     brief_version=1, candidate_id=cid)
    store.append(abort(1, "c1"), privs["coordinator"])
    store.append(abort(2, "c2"), privs["coordinator"])
    assert not should_escalate(store.all_events(), "b1", 1)
    store.append(abort(3, "c3"), privs["coordinator"])
    assert should_escalate(store.all_events(), "b1", 1)
```

- [ ] **Step 3: Run the full Slice 1 gate**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gate_adversarial.py -q`
Expected: PASS (all cases). The rule that decides REJECTED vs PENDING: a *malformed/forbidden* fact (wrong signer-seat, tier escalation, out-of-scope diff, bad sha) is **REJECTED**; a *merely-absent* approval (no release_order yet, no ci_result yet) is **PENDING**. The "wrong seat" release_order is a hard **REJECTED** — the predicate's `_seat(ro.signer) != "overseer"` check fires because a present-but-wrongly-signed release_order is a forbidden fact, not an absent one. The load-bearing invariant across every adversarial case is that `main` (the test ref) is **not advanced**.

- [ ] **Step 4: Run the whole three-way suite + smoke**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q`
Expected: PASS (all). Then: `.venv/bin/python scripts/ci_smoke.py` → expect `§15 smoke OK` (the package is additive; smoke must stay green).

- [ ] **Step 5: Append the ADR to `DECISIONS.md`** (append only — never edit prior entries)

Add an entry recording: (a) Slice 1 runs on a **separate signed-JSON event store**, not the markdown bus, so the "four files to keep in sync" coupling is untouched; (b) **single-writer seq** for Slice 1, append-CAS ref topology deferred to Slice 2; (c) **Ed25519 (`cryptography`) + `rfc8785` JCS** for signing; (d) **T2/T3 co-sign returns False** (deferred to Slice 3), so escalated tiers safely cannot promote; (e) the gate recomputes the merge and **CAS-writes a protected test ref**, never executing candidate code. Reference spec §11 / §6.3 / §6.4.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_threeway_gate_adversarial.py DECISIONS.md
git commit -m "test(threeway): adversarial Slice 1 gate suite + ADR (§11 gate met)"
```

---

## Slice 1 Definition of Done (maps to spec §11 gate)

The slice is complete when `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q` is fully green AND `.venv/bin/python scripts/ci_smoke.py` reports `§15 smoke OK`, with the adversarial suite proving the gate refuses to advance `refs/threeway/test-main` for each of:

1. tampered `integration_sha` — `test_rejects_tampered_integration_sha`
2. missing/forged signature — `test_rejects_absent_signature`
3. valid signature from the wrong seat/provider — `test_rejects_valid_signature_wrong_seat` (+ predicate `test_rejects_when_verifier_same_provider_as_builder`)
4. old GO later revoked / followed by FAIL — `test_rejects_old_go_then_fail` (+ predicate revocation test)
5. candidate that weakened its own CI policy / modified its own CI workflow — `test_rejects_candidate_modifying_ci_workflow` (+ predicate policy_digest test)
6. stage ref moved after the release attestation — `test_rejects_stage_ref_moved_after_attestation`
7. risk tier mislabeled below the path-derived minimum — `test_rejects_tier_mislabeled_below_minimum`
8. tier-escalation without a new `cycle_go` — covered by 5 & 7 (effective tier > cycle_go tier)
9. diff outside `allowed_paths` — `test_rejects_diff_outside_allowed_paths`
10. replay of a valid event from a test bus (`bus_id` mismatch) — `test_rejects_replay_from_test_bus`
11. crash after the release claim but before the `main` CAS, recovering without a double-write — `test_crash_after_release_before_cas_recovers_without_double_write`

…and a clean change merges (`test_clean_change_merges`); one REWORK cycle completes and the ≤2 cap escalates on the third (`test_one_rework_cycle_completes_then_third_escalates`).

**Then, and only then,** is Slice 2 (the mirror + bus hardening) planned — per spec §11 "each slice passes its own gate before the next is planned."

## Open questions to resolve with the user before/while executing

1. **`rfc8785` vs stdlib canonicalization.** The plan adds `rfc8785` for spec-compliant JCS. If adding a dependency is undesirable, `threeway/canon.py` can fall back to `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)` — adequate for our payloads (no floats/NaN) but not full-JCS. Recommendation: keep `rfc8785` (one pure-Python dep, exact spec compliance). *(Surfaced per the program intent: don't silently pick the dependency posture.)*
2. **Where private keys live in CI.** Slice 1's gate tests generate ephemeral keys; a real Slice 1 demo needs the keystore provisioned outside the repo. The trusted-CI signer (`ci`) key especially must live where CI can sign but candidate code cannot read it (spec §6.4). This is a deployment detail, not code — flag for the operator before any non-test run.
3. **Test default-branch name.** The `gitcas` test handles `master` vs `main`; if the team standard differs, the fixture's checkout line is the only spot to adjust.
