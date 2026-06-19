"""Git plumbing for the mechanical merge-gate.

INVARIANT: never checks out a working tree, never reads candidate workflow files,
never executes candidate code. Only object-store plumbing: merge-tree, commit-tree,
update-ref. Every call strips GIT_INDEX_FILE (per-seat index pollution, CLAUDE.md).
"""
from __future__ import annotations

import os
import subprocess

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


class BusInitRefusedError(Exception):
    """Raised when preflight finds prior refs/threeway/* state and force is not set.

    Fail-closed: the bus is NOT initialized over existing state unless the operator
    explicitly acknowledges the migration with force=True. NEVER deletes a ref.
    """


def preflight_bus_init(repo, remote: str | None = None, force: bool = False) -> None:
    """Fail-closed, NON-DESTRUCTIVE preflight before initializing the event bus.

    Enumerate refs/threeway/* LOCALLY, and (when `remote` is given) on the REMOTE.
    If any such state exists and `force` is not True, raise BusInitRefusedError —
    requiring an explicit migration acknowledgement. With force=True, proceed even
    over prior state. Either way this NEVER deletes a ref (absence of .pub files is
    NOT proof of no state — only the ref enumeration counts).

    On a clean slate (no refs/threeway/*) it returns normally, initializing the
    "threeway-sign/2" signature profile (no state to write yet).
    """
    if force:
        return
    # LOCAL enumeration. Branch on returncode: a git error (rc != 0) leaves state
    # UNDETERMINABLE — fail CLOSED rather than read empty stdout as "clean slate".
    local = _run(repo, "for-each-ref", "refs/threeway/", check=False)
    if local.returncode != 0:
        raise BusInitRefusedError(
            f"cannot verify refs/threeway state (git for-each-ref exited "
            f"{local.returncode}); refusing bus init (fail-closed)."
        )
    if local.stdout.strip():
        raise BusInitRefusedError(
            "refs/threeway/* already exists locally; refusing to init over prior "
            "bus state. Pass force=True to acknowledge the migration "
            "(no ref is ever deleted)."
        )
    # REMOTE enumeration (only when a remote is named). Same fail-closed branching:
    # an unreachable/auth-failed/transient remote (rc != 0) must NOT proceed.
    if remote is not None:
        rem = _run(repo, "ls-remote", remote, "refs/threeway/*", check=False)
        if rem.returncode != 0:
            raise BusInitRefusedError(
                f"cannot verify refs/threeway state on remote {remote!r} (git "
                f"ls-remote exited {rem.returncode}); refusing bus init (fail-closed)."
            )
        if rem.stdout.strip():
            raise BusInitRefusedError(
                f"refs/threeway/* already exists on remote {remote!r}; refusing to "
                "init over prior bus state. Pass force=True to acknowledge the "
                "migration (no ref is ever deleted)."
            )
