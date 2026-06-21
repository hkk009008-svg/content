"""ISO→scalar-seq cursor backfill + byte-reversible manifest (Slice 2.5 §6, §8 D4).

Pure functions + two filesystem ops. NO refs/threeway/* writes (the ref-bus cursors
are materialized in the cutover, Task 13, via advance_cursor). The total order is
(filename-ts, full-filename) over sent/*.md — filenames are unique even within a
same-second group, so the order is total and reproducible from sent/ alone.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)-")   # leading filename ts token
_SCHEMA = "cursor-backfill/1"


class CursorBackfillManifestError(ValueError):
    """The cursor-backfill manifest is corrupt/partial — unparseable JSON, a non-object,
    a wrong/missing schema, or a missing required key. Raised as a SINGLE clear typed
    error instead of a bare json.JSONDecodeError/KeyError so the cutover's resume
    (`backfill`) and rollback (`restore_from_manifest`) paths fail DIAGNOSABLY rather than
    as an opaque wedge (ADR-047)."""


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text atomically: a sibling temp file + os.replace (atomic within a
    filesystem). A crash/ENOSPC mid-write can then never leave a TRUNCATED manifest that
    wedges the readers' json.loads — the final path is either the prior state or the
    COMPLETE new content, never a torn prefix (ADR-047)."""
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _load_manifest(path: Path) -> dict:
    """Parse + validate the manifest; raise CursorBackfillManifestError on ANY corruption
    (unparseable JSON, non-object, wrong/missing schema, or a missing/!dict required key)
    instead of a bare JSONDecodeError/KeyError. With `_atomic_write_text` a crash can no
    longer PRODUCE a corrupt manifest; this guards external/FS corruption and any
    pre-atomicity artifact, and makes recovery inspectable (delete the corrupt manifest to
    re-derive while seen/*.txt are still ISO)."""
    try:
        obj = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise CursorBackfillManifestError(
            f"cursor-backfill manifest is not valid JSON at {path}: {e}") from e
    if not isinstance(obj, dict) or obj.get("schema") != _SCHEMA:
        got = obj.get("schema") if isinstance(obj, dict) else "<non-object>"
        raise CursorBackfillManifestError(
            f"cursor-backfill manifest schema {got!r} != expected {_SCHEMA!r} at {path}")
    for key in ("original_bytes", "original_iso", "iso_to_seq"):
        if not isinstance(obj.get(key), dict):
            raise CursorBackfillManifestError(
                f"cursor-backfill manifest missing/!dict key {key!r} at {path}")
    return obj


def _mailbox_base(coord_root: Path) -> Path:
    """The `.../mailbox` dir for either layout: a root *containing* `coordination/`,
    OR a root that already *is* `coordination`. Single source of truth so the two
    layouts can never diverge across the sent/seen/manifest paths (M-2/M-4)."""
    base = coord_root / "coordination" if (coord_root / "coordination").is_dir() else coord_root
    return base / "mailbox"


def _sent_names(coord_root: Path) -> list[str]:
    d = _mailbox_base(coord_root) / "sent"
    return sorted(p.name for p in d.iterdir() if p.name.endswith(".md"))


def total_order(sent_names: list[str]) -> list[tuple[str, str]]:
    """[(ts_token, filename)] in (ts, filename) order; seq = index+1. NB: tiebreak on
    the FULL filename keeps a same-second group total (the load-bearing invariant)."""
    keyed = []
    for n in sent_names:
        m = _TS.match(n)
        if not m:                                   # a non-event file in sent/ is a hard error
            raise ValueError(f"sent/ filename has no leading ts token: {n!r}")
        keyed.append((m.group(1), n))
    return sorted(keyed, key=lambda t: (t[0], t[1]))


def iso_to_seq_map(sent_names: list[str], iso_cursors: dict[str, str]) -> dict[str, int]:
    """seat -> highest seq whose event ts <= the seat's ISO cursor (0 if none)."""
    order = total_order(sent_names)
    out: dict[str, int] = {}
    for seat, iso in iso_cursors.items():
        iso_dash = iso[:11] + iso[11:].replace(":", "-")     # ISO colon -> filename dash form
        seq = 0
        for i, (ts, _fn) in enumerate(order, start=1):
            if ts <= iso_dash:
                seq = i
        out[seat] = seq
    return out


def _seen_dir(coord_root: Path) -> Path:
    return _mailbox_base(coord_root) / "seen"


def _manifest_path(coord_root: Path) -> Path:
    return _mailbox_base(coord_root) / ".migration" / "cursor-backfill.json"


def backfill(coord_root: Path) -> None:
    """Rewrite each seen/<seat>.txt ISO cursor to its scalar seq; archive the EXACT
    original bytes + the iso_to_seq map to the manifest (rollback = restore).

    Idempotent / archive-once: the cutover (Task 13) calls this and is RETRYABLE
    (it tears down on append failure), so a retry after a partial cutover must NOT
    re-archive. If the manifest already exists, the seen/*.txt are already scalar —
    re-reading them as "original" would clobber the real-ISO rollback anchor with the
    scalar seqs. So we re-APPLY the scalar cursors from the EXISTING manifest's archived
    map and return: safe re-run, AND it completes a partial first run (manifest written,
    some cursors not yet rewritten -> the re-apply finishes them)."""
    seen = _seen_dir(coord_root)
    man = _manifest_path(coord_root)
    if man.exists():
        obj = _load_manifest(man)           # ADR-047: typed error on a corrupt/partial manifest
        for seat, seq in obj["iso_to_seq"].items():
            (seen / f"{seat}.txt").write_text(f"{seq}\n")
        return
    sent_names = _sent_names(coord_root)
    original_bytes = {p.name: p.read_bytes() for p in seen.iterdir() if p.suffix == ".txt"}
    original_iso = {p.stem: p.read_text().strip() for p in seen.iterdir() if p.suffix == ".txt"}
    seq_map = iso_to_seq_map(sent_names, original_iso)
    man.parent.mkdir(parents=True, exist_ok=True)
    # ADR-047: write the manifest ATOMICALLY (tmp + os.replace) BEFORE rewriting any
    # cursor, so a crash here leaves NO committed manifest (the seen/*.txt are still ISO)
    # and a retry resumes via the fresh-archive branch — never a truncated manifest that
    # wedges both the resume and the rollback readers.
    _atomic_write_text(man, json.dumps({
        "schema": _SCHEMA,
        # EXACT original file bytes (latin-1 round-trippable) so restore is byte-perfect,
        # plus the human-readable stripped ISO + the recomputable map (the §8 7b check).
        "original_bytes": {k: v.decode("latin-1") for k, v in original_bytes.items()},
        "original_iso": original_iso,
        "iso_to_seq": seq_map,
    }, indent=2, sort_keys=True))
    for seat, seq in seq_map.items():
        (seen / f"{seat}.txt").write_text(f"{seq}\n")


def restore_from_manifest(coord_root: Path) -> None:
    """Byte-for-byte restore seen/*.txt from the archived manifest (rollback)."""
    path = _manifest_path(coord_root)
    if not path.exists():
        raise FileNotFoundError(f"no cursor-backfill manifest at {path}; nothing to restore")
    obj = _load_manifest(path)              # ADR-047: typed error on corrupt/partial/wrong-schema
    seen = _seen_dir(coord_root)
    for fname, text in obj["original_bytes"].items():
        (seen / fname).write_bytes(text.encode("latin-1"))
