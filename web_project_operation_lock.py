"""Shared cross-process boundary for project-scoped HTTP mutations."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Iterator

from filelock import FileLock, Timeout as FileLockTimeout

from domain.project_manager import ProjectLockError, get_project_dir, is_safe_project_id


_PROJECT_OPERATION_LOCKS: dict[str, FileLock] = {}
_PROJECT_OPERATION_LOCKS_LOCK = threading.Lock()


def project_operation_lock_path(project_id: str) -> str | None:
    """Return the stable sibling lock path without creating the project."""

    if not is_safe_project_id(project_id):
        return None
    projects_root = os.path.dirname(os.path.abspath(get_project_dir(project_id)))
    os.makedirs(projects_root, exist_ok=True)
    return os.path.join(projects_root, f".{project_id}.operation.lock")


@contextmanager
def project_operation_lock(project_id: str, *, timeout: float) -> Iterator[None]:
    """Serialize one complete project operation across threads and processes."""

    path = project_operation_lock_path(project_id)
    if path is None:
        # The endpoint itself owns the public invalid-ID response. There is no
        # safe filesystem name to lock before that validation runs.
        yield
        return
    with _PROJECT_OPERATION_LOCKS_LOCK:
        lock = _PROJECT_OPERATION_LOCKS.get(path)
        if lock is None:
            lock = FileLock(path, timeout=timeout, mode=0o600, thread_local=True)
            _PROJECT_OPERATION_LOCKS[path] = lock
    try:
        with lock.acquire(timeout=timeout):
            yield
    except FileLockTimeout as exc:
        raise ProjectLockError(project_id, timeout) from exc
