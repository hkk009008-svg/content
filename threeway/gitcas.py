"""Git plumbing for the mechanical merge-gate.

INVARIANT: never checks out a working tree, never reads candidate workflow files,
never executes candidate code. Only object-store plumbing: merge-tree, commit-tree,
update-ref. Every call strips GIT_INDEX_FILE (per-seat index pollution, CLAUDE.md).
"""
from __future__ import annotations

import os
import subprocess
import tempfile

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


def rev_parse_any(repo, ref: str) -> str | None:
    """Resolve <ref> to an OID with NO ^{commit} peel — needed for a ref that points
    directly at a BLOB (a cursor). rev_parse's ^{commit} peel returns None for a blob ref."""
    p = _run(repo, "rev-parse", "--verify", ref, check=False)
    return p.stdout.strip() if p.returncode == 0 else None


def changed_paths(repo, base_sha: str, head_sha: str) -> list[str]:
    p = _run(repo, "diff", "--name-only", base_sha, head_sha)
    return [line for line in p.stdout.splitlines() if line]


def merge_tree(repo, base_sha: str, branch_sha: str) -> tuple[str | None, bool]:
    """Return (tree_oid, clean). clean is driven by the EXIT CODE: merge-tree
    exits 1 on conflict but STILL prints a (conflict-marked) tree OID — using that
    OID would merge conflict markers into source. So clean=False on non-zero exit.

    ADR-048 — byte-determinism: pin the merge ALGORITHM config via highest-precedence
    `-c` flags so the result is HOST-INDEPENDENT. `_DET_ENV` pins only the COMMIT identity
    (commit_tree/commit_on); nothing else pinned the merge algorithm, so two seats with a
    different ambient `merge.renames` / `merge.renameLimit` / `diff.algorithm` (from
    ~/.gitconfig or GIT_CONFIG_*) computed DIFFERENT (tree, clean) for identical inputs —
    seats then disagreed on mergeability and `integration_sha`. A command-line `-c` overrides
    config from EVERY source (files and env), so these make the merge deterministic. The
    fixed-high renameLimit ensures the rename-detection threshold can never silently flip an
    individual seat on a large diff.
    """
    p = _run(repo,
             "-c", "merge.renames=true",
             "-c", "merge.renameLimit=999999",
             "-c", "diff.algorithm=histogram",
             "merge-tree", "--write-tree", base_sha, branch_sha, check=False)
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


# NB: blob I/O deliberately does NOT route through gitcas._run — _run forces text=True,
# which would corrupt read_blob's raw bytes. Keep these as raw subprocess.run(env=_env()).
def write_blob(repo, data: bytes) -> str:
    """Write a blob into the object store; return its 40-hex OID. No working tree."""
    p = subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
                       input=data, capture_output=True, env=_env(), check=True)
    return p.stdout.decode().strip()


def read_blob(repo, oid: str) -> bytes:
    p = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", oid],
                       capture_output=True, env=_env(), check=True)
    return p.stdout


def read_blob_at(repo, commit_ish: str, path: str) -> bytes | None:
    """Read blob bytes at <commit>:<path>; None on cat-file failure.

    NOTE: None CONFLATES "blob absent" with "unresolvable" — it is returned for (a) the
    path genuinely absent, (b) <commit_ish>:<path> resolving to a TREE not a blob, and
    (c) a malformed/unknown commit-ish — all indistinguishable. Callers that need None to
    mean "absent" (e.g. RefEventStore's idempotency scan) MUST pass a VALIDATED commit-ish
    plus an INDEX-DERIVED path, so the tree/bad-commit cases cannot arise and None is safely
    treated as "absent"."""
    p = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", f"{commit_ish}:{path}"],
                       capture_output=True, env=_env(), check=False)
    return p.stdout if p.returncode == 0 else None


def list_index_seqs(repo, commit_ish: str) -> list[int]:
    """Sorted seqs from index/<8-digit> entries at <commit>. [] if ref/tree absent."""
    p = _run(repo, "ls-tree", "--name-only", commit_ish, "index/", check=False)
    if p.returncode != 0:
        return []
    seqs = []
    for line in p.stdout.splitlines():
        name = line.rsplit("/", 1)[-1]
        if name.isdigit():
            seqs.append(int(name))
    return sorted(seqs)


def build_tree_with(repo, base_tree: str | None, entries: list[tuple[str, str]]) -> str:
    """Return a tree OID = base_tree (or empty) plus (path, blob_oid) entries.
    Uses a SCRATCH index file — never the seat index, never a working tree."""
    # Reserve a NAME but leave NO file: git refuses a pre-existing 0-byte GIT_INDEX_FILE
    # ("index file smaller than expected") and only creates a fresh index when the path
    # is ABSENT. So mkstemp then immediately remove. (NamedTemporaryFile would leave the
    # empty file behind and break update-index.)
    fd, idx = tempfile.mkstemp(dir=str(repo), suffix=".idx")
    os.close(fd)
    os.remove(idx)
    try:
        env = _env({"GIT_INDEX_FILE": idx})
        if base_tree:
            subprocess.run(["git", "-C", str(repo), "read-tree", base_tree],
                           env=env, check=True, capture_output=True)
        for path, blob in entries:
            subprocess.run(["git", "-C", str(repo), "update-index", "--add",
                            "--cacheinfo", f"100644,{blob},{path}"],
                           env=env, check=True, capture_output=True)
        p = subprocess.run(["git", "-C", str(repo), "write-tree"],
                           env=env, check=True, capture_output=True, text=True)
        return p.stdout.strip()
    finally:
        if os.path.exists(idx):
            os.remove(idx)


def tree_of(repo, commit_ish: str) -> str | None:
    """Resolve <commit>^{tree} to a tree OID; None if unresolvable.
    REQUIRED because gitcas.rev_parse hardcodes a ^{commit} peel — calling it with
    f'{tip}^{{tree}}' becomes '{tip}^{tree}^{commit}' and ERRORS. Do not reuse rev_parse
    for tree resolution (the predicate gate depends on rev_parse's ^{commit} peel)."""
    p = _run(repo, "rev-parse", "--verify", f"{commit_ish}^{{tree}}", check=False)
    return p.stdout.strip() if p.returncode == 0 else None


def commit_on(repo, tree_oid: str, parent: str | None, message: str) -> str:
    args = ["commit-tree", tree_oid]
    if parent:
        args += ["-p", parent]
    args += ["-m", message]
    p = _run(repo, *args, env_extra=_DET_ENV)
    return p.stdout.strip()


_ZERO_OID = "0" * 40  # SHA-1-specific (40 hex zeros); a SHA-256 repo would need 64.


def cas_create_or_update_ref(repo, ref: str, new_oid: str, expected_old: str | None) -> bool:
    """LOCAL atomic ref CAS (single-repo case). expected_old=None creates the ref."""
    old = expected_old if expected_old is not None else _ZERO_OID
    p = _run(repo, "update-ref", ref, new_oid, old, check=False)
    return p.returncode == 0


# ---- remote authoritative-bus primitives (spec §8: expected-old-OID CAS PUSH) ----

def fetch_ref(repo, remote: str, ref: str) -> str | None:
    """Fetch <ref> from the authoritative remote into the same ref locally; return the
    fetched tip OID (None if the remote ref does not exist). The retry path MUST call
    this before reading the tip / scanning idempotency, so it sees authoritative state."""
    # BY DESIGN: a transient fetch failure is indistinguishable from "remote ref absent" —
    # both fall through to the local ref (a stale tip, or None). The push-CAS lease is the
    # real guard against acting on stale state, so do NOT "fix" this into a hard failure.
    _run(repo, "fetch", "-q", remote, f"+{ref}:{ref}", check=False)
    return rev_parse(repo, ref)


def push_cas(repo, remote: str, commit: str, ref: str, expected_old: str | None) -> bool:
    """Expected-old-OID CAS PUSH (the real append mechanism). True iff the remote ref was
    exactly expected_old and is now `commit`. Git rejects a non-ff / lease-mismatch -> False.

    create-only (expected_old=None): leases against the ZERO oid, so the push succeeds IFF
    the remote ref does NOT exist, and is rejected (False) if it exists — true create-only,
    symmetric with cas_create_or_update_ref's zero-OID create. (A PLAIN `push commit:ref`
    would only enforce FAST-FORWARD, so a FF descendant pushed with the create form to an
    already-existing ref would silently succeed and violate create-only.)
    update (expected_old set): force-with-lease against the explicit expected-old.
    """
    if expected_old is None:                       # create-only: lease against the ZERO oid (ref must be absent)
        p = _run(repo, "push", f"--force-with-lease={ref}:{_ZERO_OID}",
                 remote, f"{commit}:{ref}", check=False)
    else:                                          # update: force-with-lease = explicit expected-old
        p = _run(repo, "push", f"--force-with-lease={ref}:{expected_old}",
                 remote, f"{commit}:{ref}", check=False)
    return p.returncode == 0


def for_each_ref(repo, pattern: str) -> list[str]:
    """Local ref names under a glob (e.g. 'refs/threeway/*'). [] if none."""
    p = _run(repo, "for-each-ref", "--format=%(refname)", pattern, check=False)
    return [ln for ln in p.stdout.splitlines() if ln]


def ls_remote_refs(repo, remote: str, pattern: str) -> list[str]:
    """Remote ref names under a glob (authoritative-state probe). [] if none."""
    p = _run(repo, "ls-remote", remote, pattern, check=False)
    return [ln.split("\t", 1)[1] for ln in p.stdout.splitlines() if "\t" in ln]


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
