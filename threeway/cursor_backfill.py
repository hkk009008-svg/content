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

# THE shared carrier-event classifier/order (ADR-050): the cursor numbering below derives its
# event set + §6 order from the SAME source as legacy_projector's append order, so the two can
# never disagree about which sent/ files are events (the loose local _TS regex this replaces
# counted ts-prefixed-but-malformed files the projector skipped -> a +1 seq shift).
from threeway.legacy_projector import ordered_event_names, ts_of

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")    # a seen/*.txt ISO cursor value
_SCHEMA = "cursor-backfill/1"

# The fixed 6-seat cursor roster (THE single source — cutover imports this as its _SEATS so
# the snapshot/advance loop and the seen/ canonicalization agree). Distinct from
# keys_bootstrap.SEATS, which is the wider 9-entry SIGNING roster (adds overseer/ci/merge-gate).
SEATS = ("director", "director2", "operator", "operator2", "coordinator", "coordinator2")


class SeatCursorError(ValueError):
    """A seen/*.txt legacy cursor file cannot be unambiguously attributed to a roster seat —
    a stray non-roster filename (operator.foo.txt, stranger.txt) or two case-variant files
    colliding on one canonical seat (Operator.txt + operator.txt, whose resolution is
    FS-dependent iterdir order). The irreversible cutover must refuse rather than coin a
    phantom seat key or silently last-write-wins (ADR-051)."""


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
    # ADR-050: ONLY carrier-event names, in §6 order — the SAME set/order the projector
    # appends, via the shared classifier (a clean non-event .md is skipped, a ts-prefixed
    # malformed one raises). Pre-fix this returned every .md, so backfill numbered the
    # cursors over a different set than the appended bus.
    d = _mailbox_base(coord_root) / "sent"
    return ordered_event_names(p.name for p in d.iterdir())


def total_order(sent_names: list[str]) -> list[tuple[str, str]]:
    """[(ts_token, filename)] in spec §6 (ts, filename) order; seq = index+1. Membership +
    order come from the SHARED carrier-event classifier (legacy_projector.ordered_event_names),
    so the cursor numbering is provably the SAME function of sent/ as the projector's append
    order (ADR-050): a clean non-event name is skipped, a ts-prefixed-malformed name RAISES
    MalformedEventFilename. Accepts EITHER raw sent/ names or an already-classified list —
    ordered_event_names is idempotent, so a caller that pre-filters via _sent_names does not
    double-count. NB: the tiebreak on the FULL filename keeps a same-second group total (the
    load-bearing invariant)."""
    return [(ts_of(n), n) for n in ordered_event_names(sent_names)]


def iso_to_seq_map(sent_names: list[str], iso_cursors: dict[str, str]) -> dict[str, int]:
    """seat -> highest seq whose event ts <= the seat's ISO cursor (0 if none).

    ADR-049: each cursor value MUST be an ISO timestamp (YYYY-MM-DDThh:mm:ssZ) or empty. A
    non-ISO value (e.g. an already-SCALAR seq left in seen/*.txt by a prior backfill) would
    be lexicographically compared against the filename timestamps and SILENTLY over- or
    under-advance the cursor (`"2026-..." <= "3"` is True) — reject it LOUDLY instead
    (silent-gate-degradation class)."""
    order = total_order(sent_names)
    out: dict[str, int] = {}
    for seat, iso in iso_cursors.items():
        s = iso.strip()
        if s == "":
            out[seat] = 0                                    # no cursor yet -> seq 0
            continue
        if not _ISO.match(s):
            raise CursorBackfillManifestError(
                f"cursor for {seat!r} is not an ISO timestamp: {iso!r} — a scalar seq here "
                f"would lexicographically mis-advance the cursor (ADR-049)")
        iso_dash = s[:11] + s[11:].replace(":", "-")         # ISO colon -> filename dash form
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


def canonical_seat_cursors(seen_dir: Path) -> dict[str, str]:
    """seen/<seat>.txt -> stripped cursor value, keyed by the CANONICAL lowercase roster seat.
    THE single source of truth for reading the legacy seen/ cursors, shared by the cutover's
    step-4 read (_read_iso_cursors) and the backfill's archive read, so they can never
    disagree (ADR-051).

    RAISES SeatCursorError on a stray non-roster file (operator.foo.txt — p.stem mis-splits
    it to a phantom 'operator.foo') or a case-collision (Operator.txt + operator.txt, whose
    resolution is FS-dependent). A clean single .txt per seat is normalized to its lowercase
    roster key, so seen/Operator.txt is the 'operator' cursor — never a phantom 'Operator'
    that later falls back to a silent cursor 0."""
    out: dict[str, str] = {}
    for p in sorted(seen_dir.iterdir()):
        if p.suffix != ".txt":
            continue
        stem = p.name[: -len(".txt")]              # strip exactly .txt (p.stem mis-splits a.b.txt)
        canon = stem.lower()
        if canon not in SEATS:
            raise SeatCursorError(
                f"seen/ has a non-roster cursor file {p.name!r} (stem {stem!r} is not a roster "
                f"seat); refusing to coin a phantom seat key during the irreversible cutover")
        if canon in out:
            raise SeatCursorError(
                f"seen/ has case-colliding cursor files for seat {canon!r} (e.g. {p.name!r}); "
                f"FS-dependent iterdir order would resolve this differently per host")
        out[canon] = p.read_text().strip()
    return out


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
    # original_bytes stays keyed by the LITERAL filename (byte-perfect rollback target);
    # original_iso is keyed by the CANONICAL roster seat (ADR-051) — raising on a stray/
    # case-colliding seen/*.txt rather than archiving a phantom seat into the manifest.
    original_bytes = {p.name: p.read_bytes() for p in seen.iterdir() if p.suffix == ".txt"}
    original_iso = canonical_seat_cursors(seen)
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


def archived_seq_map(coord_root: Path) -> dict:
    """Return the seat->seq map archived by a prior backfill (the manifest's iso_to_seq).
    The cutover's cursor step uses this on a force=True RE-RUN: by then seen/*.txt hold
    SCALAR seqs (the prior run's backfill rewrote them), so re-deriving via iso_to_seq_map
    would lexicographically OVER-advance every cursor past unread events (ADR-049). The
    manifest's iso_to_seq is the correct ISO-derived map from the first run. Raises
    CursorBackfillManifestError if the manifest is corrupt (ADR-047)."""
    return dict(_load_manifest(_manifest_path(coord_root))["iso_to_seq"])
