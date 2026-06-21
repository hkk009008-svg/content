"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_divergence.py -q"""
from threeway.divergence import diverge
from threeway.legacy_projector import project

_BODY = (
    "# {subj}\n\n"
    "**When:** {when} · **From:** {frm} (online)\n\n"
    "body line\n\n"
    "Cursor at send: {cursor}\n"
)


def _write(sent, ts, frm, to, kind, *, subj="S", when="2026-06-01T00:00:00Z",
           cursor="2026-05-31T00:00:00Z"):
    name = f"{ts}-{frm}-to-{to}-{kind}.md"
    (sent / name).write_text(_BODY.format(subj=subj, when=when, frm=frm, cursor=cursor))
    return name


def _fixture(tmp_path):
    sent = tmp_path / "mailbox" / "sent"; sent.mkdir(parents=True)
    seen = tmp_path / "mailbox" / "seen"; seen.mkdir(parents=True)
    _write(sent, "2026-06-01T10-00-00Z", "operator", "director", "report",
           when="2026-06-01T10:00:00Z")
    _write(sent, "2026-06-01T11-00-00Z", "director", "operator", "decision",
           when="2026-06-01T11:00:00Z")
    # director consumed both events (cursor at-or-after the 2nd ts) -> unread 0
    (seen / "director.txt").write_text("2026-06-01T11:00:00Z\n")
    # operator consumed only the 1st -> the 2nd (a -to-operator-) is unread (count 1)
    (seen / "operator.txt").write_text("2026-06-01T10:00:00Z\n")
    return sent, seen


def test_zero_drift_on_faithful_fixture(tmp_path):
    sent, seen = _fixture(tmp_path)
    rep = diverge(project(sent), sent, seen)
    assert rep.ok is True, rep.drifts
    assert rep.drifts == []


def test_field_drift_when_body_perturbed_MUTATION(tmp_path):
    # MUTATION (ADR-028): change exactly one fact — one event's BODY on disk AFTER
    # projecting from a pristine copy — so the projected body != the on-disk body. The
    # field-level body compare must flip rep.ok False. (We project first, then perturb
    # the file, then diverge against the perturbed dir.)
    sent, seen = _fixture(tmp_path)
    projected = project(sent)
    victim = next(p for p in sent.iterdir() if "report" in p.name)
    victim.write_text(victim.read_text() + "\nTAMPERED EXTRA LINE\n")
    rep = diverge(projected, sent, seen)
    assert rep.ok is False
    assert any("body" in d for d in rep.drifts)


def test_bijection_floor_red_when_a_sent_file_deleted_MUTATION(tmp_path):
    # MUTATION: delete exactly one sent/*.md AFTER projecting -> projected count (2) !=
    # on-disk count (1). The non-empty-floor bijection must flip RED. Distinct from the
    # body-drift mutation above (this is a count/identity-set break, not a field break).
    sent, seen = _fixture(tmp_path)
    projected = project(sent)
    next(p for p in sent.iterdir() if "decision" in p.name).unlink()
    rep = diverge(projected, sent, seen)
    assert rep.ok is False
    assert any("bijection" in d or "count" in d for d in rep.drifts)


def test_cursor_unread_drift_when_seen_rewound_MUTATION(tmp_path):
    # MUTATION: rewind director's cursor to before the 2nd event -> the legacy
    # strictly-greater unread becomes 1, but the projection-consumed unread for that
    # rewound cursor must MATCH (both recomputed from the same seen value), so this
    # asserts the cursor clause is LIVE by instead corrupting the seen value to a ts that
    # has NO event at-or-before it while the projection still sees 2 events — the
    # consumed-seq equivalence (§8 clause 4) must still hold; to force a drift we make
    # the seen file claim MORE consumed than exists.
    sent, seen = _fixture(tmp_path)
    projected = project(sent)
    # claim a cursor far in the FUTURE: legacy unread = 0; projection consumed = all.
    # then DROP one projected event so projection's max-seq < legacy's implied consumed.
    (seen / "director.txt").write_text("2099-01-01T00:00:00Z\n")
    rep = diverge(projected[:1], sent, seen)   # projection missing the 2nd event
    assert rep.ok is False
    # NB: this case ALSO trips the bijection floor (projected count 1 vs disk 2). It is
    # kept as the "a missing projected event is detected" pin, but it does NOT isolate
    # the cursor clause (clause #4) — that is the next test.


def test_cursor_clause_isolated_with_bijection_intact_MUTATION(tmp_path):
    # CURSOR-ISOLATING mutation (spec §8 clause #4). The bijection stays FULLY intact
    # (project ALL events; the projected source_filename set == the on-disk set → the
    # floor + identity-set checks are GREEN), so a drift here can ONLY come from the
    # per-seat cursor/unread clause, never the floor. NON-VACUITY REQUIRES the
    # implementation to source `legacy_unread` from the RAW on-disk sent/*.md `to`
    # tokens (the legacy checker's own view) and `proj_unread` from the projected
    # events' `e.recipient` seq-view — two INDEPENDENT derivations that agree on a
    # faithful projection and CAN drift when the projection mis-routes one event (see
    # the implementation note: legacy side reads disk, projection side reads events).
    sent, seen = _fixture(tmp_path)
    projected = project(sent)                       # ALL events -> bijection intact
    # operator's cursor between the two events (10:30 is after the 10:00 -report-, before
    # the 11:00 -to-operator- -decision-): legacy strictly-greater unread for operator = 1.
    (seen / "operator.txt").write_text("2026-06-01T10:30:00Z\n")
    # a faithful projection agrees -> zero drift (proves the clause does not false-positive).
    assert diverge(projected, sent, seen).ok is True
    # MUTATION (one fact): the projection mis-routes the -to-operator- event's recipient.
    # On disk the file is STILL -to-operator- (bijection untouched: same source_filename
    # set), so the legacy side counts operator's unread=1 while the projection side, now
    # seeing 0 events addressed to operator, counts unread=0 -> the cursor clause drifts.
    victim = next(e for e in projected if e.recipient == "operator")
    victim.recipient = "director2"
    rep = diverge(projected, sent, seen)
    assert rep.ok is False
    # PIN clause #4 SPECIFICALLY: a `cursor[operator]` drift string is emitted ONLY by the
    # cursor block. (The recipient tamper also emits a field-drift string, but deleting
    # the cursor block would drop THIS string while the field drift alone would not carry
    # it — so this assertion fails if clause #4's code is removed, proving it is pinned.)
    assert any(d.startswith("cursor[operator]") for d in rep.drifts), rep.drifts


def test_stray_nonroster_seen_file_reported_not_coined_as_phantom_MUTATION(tmp_path):
    # Rule-13 sibling of ADR-051 (the cutover seen-filename-seat-key fix). The seated set was
    # derived via `f.stem`, which mis-splits a stray NON-ROSTER cursor file
    # (seen/operator.foo.txt -> a PHANTOM 'operator.foo' seat) and is case-fragile
    # (Operator.txt -> 'Operator'). A phantom seat enters the loop seeing only broadcasts ->
    # it VACUOUSLY agrees, so a corrupt seen/ roster is silently tolerated (a FALSE-GREEN),
    # exactly the failure mode the inventory row flags. The checker must instead REPORT the
    # malformed roster as a drift (READ-ONLY contract: surface, never crash like the one-way
    # cutover, which RAISES).
    sent, seen = _fixture(tmp_path)
    projected = project(sent)
    assert diverge(projected, sent, seen).ok is True          # control: faithful -> zero drift
    # MUTATION (one fact): drop a stray non-roster cursor file into seen/.
    (seen / "operator.foo.txt").write_text("2099-01-01T00:00:00Z\n")
    rep = diverge(projected, sent, seen)
    # PRE-FIX: `f.stem` coins phantom 'operator.foo' that vacuously agrees -> ok=True (BUG: RED).
    # POST-FIX: the shared canonical roster reader rejects the non-roster stem -> reported drift.
    assert rep.ok is False, rep.drifts
    assert any(d.startswith("seated:") for d in rep.drifts), rep.drifts


def test_broadcast_only_seat_is_checked_not_skipped_MUTATION(tmp_path):
    # COVERAGE-GAP pin (Slice 2.5): a seated seat that receives ONLY broadcasts and is
    # NEVER a direct (non-`all`) recipient — in the live corpus that is `coordinator` AND
    # `coordinator2`, the brand-new seats this slice adds — must be VERIFIED by clause #4,
    # not silently skipped. PRE-FIX, the `seats` set was derived from the on-disk direct
    # `to` tokens (+ projected non-`all` recipients), so a broadcast-only seat never
    # entered the loop and NO `cursor[coordinator]` drift could EVER be emitted — making
    # this mutation's assertion FAIL on the buggy code (RED) and pass only after the fix
    # sources the seated set from the seen/ cursors (Phase A seeds the coordinators).
    sent = tmp_path / "mailbox" / "sent"; sent.mkdir(parents=True)
    seen = tmp_path / "mailbox" / "seen"; seen.mkdir(parents=True)
    # a realistic corpus: two direct events + one -to-all- broadcast.
    _write(sent, "2026-06-01T10-00-00Z", "operator", "director", "report",
           when="2026-06-01T10:00:00Z")
    _write(sent, "2026-06-01T11-00-00Z", "director", "operator", "decision",
           when="2026-06-01T11:00:00Z")
    _write(sent, "2026-06-01T12-00-00Z", "director", "all", "broadcast",
           when="2026-06-01T12:00:00Z")
    (seen / "director.txt").write_text("2026-06-01T12:00:00Z\n")   # consumed all
    (seen / "operator.txt").write_text("2026-06-01T12:00:00Z\n")   # consumed all
    # coordinator is the BROADCAST-ONLY seat: cursor set BEFORE the 12:00 broadcast ts,
    # so coordinator's legacy strictly-greater unread = 1 (the broadcast).
    (seen / "coordinator.txt").write_text("2026-06-01T11:30:00Z\n")
    projected = project(sent)
    # a FAITHFUL projection -> coordinator now VERIFIED-as-agreeing (legacy unread 1 ==
    # projection unread 1, since the broadcast is addressed via recipient=='all'), NOT a
    # false positive. PRE-FIX this was ok=True only by VACUOUS skip; now by agreement.
    assert diverge(projected, sent, seen).ok is True
    # MUTATION (one fact): re-route the projected broadcast to a non-`all`, non-coordinator
    # seat. The on-disk file is STILL -to-all- (bijection untouched: same source_filename
    # set), so the legacy side still counts coordinator's broadcast unread = 1, while the
    # projection side no longer counts it for coordinator (recipient != coordinator/all).
    victim = next(e for e in projected if e.recipient == "all")
    victim.recipient = "director"
    rep = diverge(projected, sent, seen)
    assert rep.ok is False
    # PIN the broadcast-only-seat coverage SPECIFICALLY: a `cursor[coordinator]` drift can
    # ONLY be emitted if coordinator entered the seats loop. PRE-FIX coordinator is never
    # in that loop -> this assertion FAILS (RED); it passes only after the seated-set fix.
    assert any(d.startswith("cursor[coordinator]") for d in rep.drifts), rep.drifts
