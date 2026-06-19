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
