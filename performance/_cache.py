"""Content-hash cache for Mode-B driving-video synthesis.

WHY THIS EXISTS
---------------
Hedra Character-3 is ~$0.05/shot. The operator's "regenerate performance"
button currently re-synthesizes the driving face even when audio+keyframe
haven't changed. Caching by (audio_hash, keyframe_hash, duration) avoids
repeat charges.

The cache lives under PERFORMANCE_CACHE_DIR (env), defaulting to
data/cache/driving/. Cache entries are deduplicated by SHA-256.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from typing import Optional


def _cache_dir() -> str:
    return os.environ.get("PERFORMANCE_CACHE_DIR", "data/cache/driving")


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def driving_cache_key(audio_path: str, keyframe_path: str, duration_s: float) -> str:
    """Stable key from audio bytes + keyframe bytes + duration."""
    parts = [
        _sha256_file(audio_path),
        _sha256_file(keyframe_path),
        f"{round(float(duration_s), 2)}",
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _cache_path(key: str) -> str:
    return os.path.join(_cache_dir(), f"{key}.mp4")


def lookup_cache(key: str) -> Optional[str]:
    """Return the cached path if present, else None."""
    p = _cache_path(key)
    return p if os.path.exists(p) else None


def store_cache(key: str, source_path: str) -> Optional[str]:
    """Copy source_path into the cache under `key`. Returns the cached path."""
    if not os.path.exists(source_path):
        return None
    os.makedirs(_cache_dir(), exist_ok=True)
    dst = _cache_path(key)
    shutil.copyfile(source_path, dst)
    return dst
