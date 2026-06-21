"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_cursor_backfill.py -q"""
import json
import os
from pathlib import Path

import pytest

import threeway.cursor_backfill as cb
from threeway.cursor_backfill import (
    total_order, iso_to_seq_map, backfill, restore_from_manifest,
)

# Three events; two share a SECOND (the same-second tiebreak must be total).
_NAMES = [
    "2026-06-17T19-55-31Z-operator-to-director-status.md",
    "2026-06-17T20-00-00Z-director-to-operator-decision.md",
    "2026-06-17T20-00-00Z-operator-to-director-ack.md",     # same second as above
]


def _seed(root: Path, cursors: dict):
    sent = root / "coordination" / "mailbox" / "sent"
    seen = root / "coordination" / "mailbox" / "seen"
    sent.mkdir(parents=True); seen.mkdir(parents=True)
    for n in _NAMES:
        # body is irrelevant to the backfill (it reads only sent/ FILENAMES + seen/ cursors)
        (sent / n).write_text("# x\n")
    for seat, iso in cursors.items():
        (seen / f"{seat}.txt").write_text(iso + "\n")
    return root


def test_total_order_is_total_under_same_second(tmp_path):
    order = total_order(_NAMES)
    # 3 distinct seqs despite a same-second collision (tiebreak = full filename)
    assert [fn for _, fn in order] == sorted(_NAMES)
    assert len(order) == 3


def test_iso_maps_to_highest_seq_at_or_before_cursor(tmp_path):
    # director cursor at 20:00:00Z -> highest event ts <= that.
    # The two 20:00:00Z events tiebreak by filename; "...decision.md" sorts before
    # "...operator-to-director-ack.md", so the at-or-before set is {seq1, seq2} and
    # the highest is seq 2 (decision) ... wait: ack also == 20:00:00Z, so both
    # qualify -> highest seq among ts<=cursor is the LAST of the two by filename.
    m = iso_to_seq_map(_NAMES, {"director": "2026-06-17T20:00:00Z"})
    order = total_order(_NAMES)                 # [(ts,fn)...] seq = idx+1
    last_le = max(seq for seq, (ts, fn) in enumerate(order, 1)
                  if ts <= "2026-06-17T20-00-00Z")
    assert m["director"] == last_le             # exact §6 rule, recomputed independently


def test_iso_with_no_event_at_or_before_is_seq_zero(tmp_path):
    m = iso_to_seq_map(_NAMES, {"operator": "2020-01-01T00:00:00Z"})
    assert m["operator"] == 0                   # seq-0 floor (advance_cursor allows 0)


def test_backfill_then_restore_is_byte_reversible(tmp_path):
    # 7a (byte-reversibility). MUTATION (documented): after backfill, flip one byte
    # of an archived ISO in the manifest, THEN restore -> the restored seen/<seat>.txt
    # bytes != the captured original -> the round-trip assertion flips RED.
    root = _seed(tmp_path, {"director": "2026-06-17T20:00:00Z",
                            "operator": "2026-06-17T19:55:31Z"})
    seen = root / "coordination" / "mailbox" / "seen"
    before = {p.name: p.read_bytes() for p in seen.iterdir()}
    backfill(root)
    # cursors are now scalar seqs
    assert (seen / "director.txt").read_text().strip().isdigit()
    restore_from_manifest(root)
    after = {p.name: p.read_bytes() for p in seen.iterdir()}
    assert after == before                      # byte-for-byte round trip

    # --- the documented single-byte mutation must break the round-trip ---
    # NB: restore_from_manifest restores from obj["original_bytes"][<filename>] — so the
    # mutation MUST perturb that field (NOT original_iso, which restore never reads, or
    # the mutation would be a no-op and this test would falsely pass on broken restore).
    backfill(root)
    man = root / "coordination" / "mailbox" / ".migration" / "cursor-backfill.json"
    obj = json.loads(man.read_text())
    raw = obj["original_bytes"]["director.txt"]          # latin-1 str of the EXACT bytes
    obj["original_bytes"]["director.txt"] = ("X" if raw[0] != "X" else "Y") + raw[1:]  # flip one byte
    man.write_text(json.dumps(obj))
    restore_from_manifest(root)
    assert (seen / "director.txt").read_bytes() != before["director.txt"]


def test_map_recomputes_purely_from_sent_and_order(tmp_path):
    # 7b (map reproducibility). MUTATION (documented): perturb one event ts so its seq
    # bucket changes -> the recomputed map diverges from the archived map -> RED.
    root = _seed(tmp_path, {"director": "2026-06-17T20:00:00Z"})
    backfill(root)
    man = json.loads((root / "coordination" / "mailbox" / ".migration"
                      / "cursor-backfill.json").read_text())
    sent_names = sorted(p.name for p in
                        (root / "coordination" / "mailbox" / "sent").iterdir())
    recomputed = iso_to_seq_map(sent_names, man["original_iso"])
    assert recomputed == man["iso_to_seq"]      # archived map == purely-recomputed map


def test_backfill_is_idempotent_preserves_original_anchor(tmp_path):
    # Idempotency / archive-once. The cutover (Task 13) is RETRYABLE — it re-calls
    # backfill() after tearing down a partial events ref. A SECOND backfill must NOT
    # re-archive: by then the seen/*.txt are already scalar seqs, so re-reading them as
    # "original" would clobber the real-ISO rollback anchor with the scalar values.
    #
    # NON-VACUITY: on the PRE-FIX code the second backfill() overwrites the manifest with
    # original_bytes={"director.txt":"<seq>\n"} (the scalar), so restore would yield the
    # SCALAR bytes (e.g. "2\n") != the ORIGINAL ISO -> this assertion goes RED. (Confirmed
    # RED by scratch-reverting the `if man.exists(): ... return` guard.) The fix makes the
    # second call re-apply the archived map and return, leaving original_bytes untouched.
    root = _seed(tmp_path, {"director": "2026-06-17T20:00:00Z",
                            "operator": "2026-06-17T19:55:31Z"})
    seen = root / "coordination" / "mailbox" / "seen"
    before = {p.name: p.read_bytes() for p in seen.iterdir()}   # the ORIGINAL ISO bytes
    backfill(root)                              # cursors -> scalar; manifest archives ISO
    assert (seen / "director.txt").read_text().strip().isdigit()
    backfill(root)                              # 2nd call: must NOT re-archive the scalars
    # the cursors are still scalar (re-applied from the archived map), not re-ISO'd
    assert (seen / "director.txt").read_text().strip().isdigit()
    restore_from_manifest(root)
    after = {p.name: p.read_bytes() for p in seen.iterdir()}
    assert after == before                      # rollback anchor still the ORIGINAL ISO


# ----------------------------------------------------------------------------
# ADR-047 — manifest write must be ATOMIC and the readers robust to corruption.
# run_cutover step 5b (cutover.py:168) does NOT tear down on a backfill failure — it
# relies on "retry resumes cheaply". A crash/ENOSPC mid `man.write_text(json.dumps(...))`
# left a TRUNCATED manifest, and BOTH readers (backfill resume + restore_from_manifest)
# did a bare `json.loads` -> JSONDecodeError -> retry AND rollback both wedged, with no
# auto-recovery. Fix: atomic tmp+os.replace (a crash leaves NO committed manifest, and the
# cursor rewrite runs AFTER the write so seen/*.txt stay ISO -> a retry resumes via fresh
# archive); plus a clear typed CursorBackfillManifestError on any corrupt manifest.
# ----------------------------------------------------------------------------
def test_crash_during_atomic_manifest_write_leaves_no_committed_manifest_and_retry_resumes(tmp_path, monkeypatch):
    root = _seed(tmp_path, {"director": "2026-06-17T20:00:00Z",
                            "operator": "2026-06-17T19:55:31Z"})
    man = root / "coordination" / "mailbox" / ".migration" / "cursor-backfill.json"
    seen = root / "coordination" / "mailbox" / "seen"
    def _boom(*a, **k):
        raise RuntimeError("simulated crash at the atomic commit step")
    monkeypatch.setattr(os, "replace", _boom)          # crash at the tmp->final rename
    with pytest.raises(RuntimeError):
        cb.backfill(root)
    assert not man.exists()                             # no committed/truncated manifest
    assert (seen / "director.txt").read_text().strip() == "2026-06-17T20:00:00Z"  # cursors still ISO
    monkeypatch.undo()
    cb.backfill(root)                                  # retry resumes cleanly (fresh archive)
    assert man.exists()
    assert (seen / "director.txt").read_text().strip().isdigit()


def test_corrupt_manifest_backfill_raises_clear_typed_error(tmp_path):
    root = _seed(tmp_path, {"director": "2026-06-17T20:00:00Z",
                            "operator": "2026-06-17T19:55:31Z"})
    man = root / "coordination" / "mailbox" / ".migration" / "cursor-backfill.json"
    cb.backfill(root)
    good = man.read_text()
    man.write_text(good[: len(good) // 2])             # truncate -> not valid JSON
    with pytest.raises(cb.CursorBackfillManifestError):
        cb.backfill(root)                              # resume must raise the TYPED error


def test_corrupt_manifest_restore_raises_clear_typed_error(tmp_path):
    root = _seed(tmp_path, {"director": "2026-06-17T20:00:00Z"})
    man = root / "coordination" / "mailbox" / ".migration" / "cursor-backfill.json"
    cb.backfill(root)
    good = man.read_text()
    man.write_text(good[: len(good) // 2])
    with pytest.raises(cb.CursorBackfillManifestError):
        cb.restore_from_manifest(root)


def test_iso_to_seq_map_rejects_non_iso_cursor(tmp_path):
    # ADR-049 defense: a non-ISO (e.g. already-SCALAR) cursor must RAISE loudly, not be
    # lexicographically compared against timestamps (which silently mis-advances).
    with pytest.raises(cb.CursorBackfillManifestError):
        cb.iso_to_seq_map(_NAMES, {"director": "3"})


def test_archived_seq_map_returns_manifest_iso_to_seq(tmp_path):
    # ADR-049: after backfill archives the manifest, archived_seq_map returns the correct
    # ISO-derived seqs — the cutover RE-RUN uses this instead of re-reading the scalar seen/*.txt.
    root = _seed(tmp_path, {"director": "2026-06-17T20:00:00Z"})
    cb.backfill(root)
    man = json.loads((root / "coordination" / "mailbox" / ".migration"
                      / "cursor-backfill.json").read_text())
    assert cb.archived_seq_map(root) == man["iso_to_seq"]


def test_canonical_seat_cursors_rejects_case_collision(tmp_path):
    # ADR-051: two seen/ files mapping to the SAME canonical roster seat (Operator.txt +
    # operator.txt) must RAISE — FS-dependent iterdir() order would otherwise silently
    # last-write-wins differently per host. Skipped on a case-insensitive FS where the two
    # names cannot coexist as distinct files.
    seen = tmp_path / "seen"; seen.mkdir()
    (seen / "operator.txt").write_text("2026-06-17T20:00:00Z\n")
    try:
        (seen / "Operator.txt").write_text("2026-06-17T19:00:00Z\n")
    except OSError:
        pytest.skip("filesystem rejected the case-variant filename")
    if len(list(seen.iterdir())) < 2:
        pytest.skip("case-insensitive filesystem: the two names are one file, no collision")
    with pytest.raises(cb.SeatCursorError):
        cb.canonical_seat_cursors(seen)


def test_backfill_numbers_over_projector_event_set_skip_clean_raise_malformed(tmp_path):
    # ADR-050: the cursor seq numbering must use the SAME event set + order as the
    # projector's append order. Pre-fix backfill() numbered over _sent_names() = ALL .md via
    # the loose _TS regex, so:
    #   - a CLEAN non-event .md (README.md, no leading ts) made _TS raise -> spurious abort;
    #   - a ts-prefixed-but-malformed .md was COUNTED here but SKIPPED by the projector ->
    #     every later seq shifted +1 -> the archived iso_to_seq diverged from the appended
    #     index -> a force-rerun (which reads archived_seq_map) over-advanced the cursor refs.
    from threeway.legacy_projector import MalformedEventFilename

    # (a) a clean non-event file is skipped, NOT counted -> director (cursor covers all 3
    #     events) still maps to seq 3.  Pre-fix this RAISED (total_order _TS miss on README).
    root = _seed(tmp_path / "clean", {"director": "2026-06-17T20:00:00Z"})
    (root / "coordination" / "mailbox" / "sent" / "README.md").write_text("not an event\n")
    backfill(root)
    man = json.loads((root / "coordination" / "mailbox" / ".migration"
                      / "cursor-backfill.json").read_text())
    assert man["iso_to_seq"]["director"] == len(_NAMES)            # README not counted -> 3, no +1

    # (b) a ts-prefixed-but-malformed file -> RAISE (never silently counted -> seq shift).
    root2 = _seed(tmp_path / "malformed", {"director": "2026-06-17T20:00:00Z"})
    (root2 / "coordination" / "mailbox" / "sent"
     / "2026-06-17T21-00-00Z-stranger-to-director-foo.md").write_text("x\n")
    with pytest.raises(MalformedEventFilename):
        backfill(root2)


def test_keyincomplete_manifest_raises_clear_typed_error(tmp_path):
    # schema-VALID but a required key MISSING (older/hand-edited manifest) must also raise
    # the typed error, not a bare KeyError in the resume/rollback read.
    root = _seed(tmp_path, {"director": "2026-06-17T20:00:00Z"})
    man = root / "coordination" / "mailbox" / ".migration" / "cursor-backfill.json"
    cb.backfill(root)
    obj = json.loads(man.read_text())
    del obj["iso_to_seq"]
    man.write_text(json.dumps(obj))
    with pytest.raises(cb.CursorBackfillManifestError):
        cb.backfill(root)
