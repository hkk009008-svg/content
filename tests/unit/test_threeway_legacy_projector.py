"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_projector.py -q"""
import hashlib

import pytest

from threeway.envelope import idempotency_key
from threeway.legacy_projector import project

# --- inline fixture: build a fake sent/ dir with controlled filenames + bodies ---
_BODY = (
    "# {subj}\n\n"
    "**When:** {when} · **From:** {frm} (online)\n\n"
    "VERDICT: GO\n\n"
    "Cursor at send: {cursor}\n"
)


def _write(sent_dir, ts, frm, to, kind, *, subj="S", when="2026-06-01T00:00:00Z",
           cursor="2026-05-31T00:00:00Z"):
    name = f"{ts}-{frm}-to-{to}-{kind}.md"
    (sent_dir / name).write_text(
        _BODY.format(subj=subj, when=when, frm=frm, cursor=cursor))
    return name


def _sent(tmp_path):
    d = tmp_path / "mailbox" / "sent"
    d.mkdir(parents=True)
    return d


def test_project_round_trips_every_field_and_preserves_broadcast(tmp_path):
    sent = _sent(tmp_path)
    n1 = _write(sent, "2026-06-01T10-00-00Z", "operator", "director",
                "verification-report", subj="GO 5e70e43f")
    n2 = _write(sent, "2026-06-01T11-00-00Z", "director", "all",  # broadcast
                "fyi", subj="heads up")
    evs = project(sent)

    # one Event per FILE; the broadcast is ONE event, never fanned to 4
    assert len(evs) == 2
    by_to = {e.recipient: e for e in evs}
    assert set(by_to) == {"director", "all"}        # 'all' preserved, not expanded

    e1 = by_to["director"]
    assert e1.kind == "event_sent"                  # carrier kind (not the legacy kind)
    assert e1.sender == "operator"
    assert e1.brief_id == "legacy-import"
    assert e1.signature is None                      # UNSIGNED at projection
    # the ORIGINAL legacy kind + subject/when/cursor/body/source land in payload
    assert e1.payload["legacy_kind"] == "verification-report"
    assert e1.payload["subject"] == "GO 5e70e43f"
    assert e1.payload["when"] == "2026-06-01T00:00:00Z"
    assert e1.payload["cursor_at_send"] == "2026-05-31T00:00:00Z"
    assert e1.payload["recipient"] == "director"
    assert e1.payload["source_filename"] == n1
    # subject_sha = sha256(source_filename) hex
    assert e1.subject_sha == hashlib.sha256(n1.encode()).hexdigest()


def test_two_identical_bodies_same_sender_kind_both_land_with_distinct_keys(tmp_path):
    # spec §5a injectivity: two byte-identical same-(sender,kind) events must BOTH
    # project, with DISTINCT event ids AND distinct idempotency_keys — proving
    # subject_sha=sha256(filename) breaks the collision that terse status/ack bodies
    # would otherwise hit.
    sent = _sent(tmp_path)
    _write(sent, "2026-06-01T12-00-00Z", "operator", "director", "ack",
           subj="ack", when="2026-06-01T00:00:00Z", cursor="2026-05-31T00:00:00Z")
    _write(sent, "2026-06-01T12-00-01Z", "operator", "director", "ack",
           subj="ack", when="2026-06-01T00:00:00Z", cursor="2026-05-31T00:00:00Z")
    evs = project(sent)
    assert len(evs) == 2
    assert evs[0].id != evs[1].id
    assert idempotency_key(evs[0]) != idempotency_key(evs[1])   # injective


def test_total_order_is_filename_ts_then_full_filename(tmp_path):
    # spec §6 total order: (filename ts, full filename). Two same-second files sort by
    # full filename; a later-ts file sorts after both.
    sent = _sent(tmp_path)
    _write(sent, "2026-06-01T12-00-00Z", "operator", "director", "zeta")
    _write(sent, "2026-06-01T12-00-00Z", "operator", "director", "alpha")
    _write(sent, "2026-06-01T13-00-00Z", "operator", "director", "mid")
    names = [e.payload["source_filename"] for e in project(sent)]
    assert names == sorted(names)               # full-filename total order within + across


def test_subject_sha_empty_collides_two_identical_bodies_MUTATION(tmp_path):
    # MUTATION proof of non-vacuity (ADR-028) for the §5a injectivity keystone.
    #
    # WHY the naive "just set subject_sha='' on both" mutation is VACUOUS: the projector
    # also puts the (distinct) `source_filename` into `payload`, so `payload_digest`
    # already differs between two same-(sender,kind) events and `idempotency_key`
    # (sender:kind:subject_sha:payload_digest) is injective via source_filename ALONE,
    # even with an empty subject_sha. The keys would NOT collide — the assertion would be
    # false on correct GREEN code, making the test tautologically broken.
    #
    # The CORRECT collision requires removing BOTH injectivity sources at once: strip
    # `source_filename` from the payload AND set subject_sha='' for both events. Only the
    # single conceptual fact "no per-file discriminator survives" is mutated; assert the
    # keys THEN collide — proving the live projector's distinctness (asserted in
    # test_two_identical_bodies_... above) is load-bearing, not decorative.
    sent = _sent(tmp_path)
    _write(sent, "2026-06-01T12-00-00Z", "operator", "director", "ack", subj="ack")
    _write(sent, "2026-06-01T12-00-01Z", "operator", "director", "ack", subj="ack")
    a, b = project(sent)
    # sanity: on GREEN code the two keys are DISTINCT (source_filename in payload).
    assert idempotency_key(a) != idempotency_key(b)
    # the mutation: remove EVERY per-file discriminator (subject_sha AND the payload
    # source_filename) from both -> the bodies are now byte-identical in every
    # key-contributing field -> the keys collide.
    a.subject_sha = ""
    b.subject_sha = ""
    a.payload = {k: v for k, v in a.payload.items() if k != "source_filename"}
    b.payload = {k: v for k, v in b.payload.items() if k != "source_filename"}
    assert idempotency_key(a) == idempotency_key(b)   # both discriminators gone -> collide
    # ...therefore the live subject_sha=sha256(filename) is defense-in-depth ON TOP OF the
    # payload source_filename; together they keep idempotency_key injective over the corpus.


def test_project_skips_clean_nonevent_but_raises_on_tsprefixed_malformed(tmp_path):
    # ADR-050: "which sent/ files become carrier events" is ONE classifier, shared with
    # cursor_backfill so the append-seq numbering (here) and the cursor-seq numbering (there)
    # are provably the same function of sent/. The classifier is THREE-way:
    #   - a CLEAN non-event file (no leading dash-ts token) is SKIPPED;
    #   - a ts-prefixed .md that fails the full <ts>-<from>-to-<to>-<kind> grammar (a
    #     suspected-but-unparseable event) RAISES — it must NOT be silently dropped during
    #     the irreversible cutover (pre-fix project() silently skipped BOTH).
    from threeway.legacy_projector import MalformedEventFilename
    sent = _sent(tmp_path)
    n_ok = _write(sent, "2026-06-01T10-00-00Z", "operator", "director", "status")
    (sent / "README.md").write_text("not an event\n")                  # clean non-event -> skip
    evs = project(sent)
    assert [e.payload["source_filename"] for e in evs] == [n_ok]        # README skipped, event kept

    # a ts-prefixed but non-roster sender -> looks like an event, fails the grammar -> RAISE
    (sent / "2026-06-01T11-00-00Z-stranger-to-director-foo.md").write_text("x\n")
    with pytest.raises(MalformedEventFilename):
        project(sent)
