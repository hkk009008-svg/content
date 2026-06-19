"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_store.py -q"""
from threeway import keys
from threeway.envelope import Event, sign_event
from threeway.store import EventStore


def _unsigned(seq, kind="attestation", **over):
    base = dict(
        id=f"id-{seq}", seq=0, bus_id="prod", schema_version="threeway/1",
        kind=kind, sender="operator", recipient="all", signer="operator:claude:s1",
        payload={"k": seq},
    )
    base.update(over)
    return Event(**base)


def test_append_assigns_monotonic_seq_starting_at_1(tmp_path):
    store = EventStore(tmp_path / "events")
    priv, _ = keys.generate_keypair()
    e1 = store.append(_unsigned(1), priv)
    e2 = store.append(_unsigned(2), priv)
    assert (e1.seq, e2.seq) == (1, 2)


def test_appended_events_are_signed_and_persisted(tmp_path):
    store = EventStore(tmp_path / "events")
    priv, pub = keys.generate_keypair()
    e = store.append(_unsigned(1), priv)
    assert e.signature
    files = list((tmp_path / "events").glob("*.json"))
    assert len(files) == 1 and files[0].name.startswith("00000001-")


def test_iter_returns_events_in_seq_order(tmp_path):
    store = EventStore(tmp_path / "events")
    priv, pub = keys.generate_keypair()
    for i in range(1, 6):
        store.append(_unsigned(i), priv)
    seqs = [e.seq for e in store.iter_events()]
    assert seqs == [1, 2, 3, 4, 5]


def test_iter_events_roundtrips_payload_and_seq(tmp_path):
    # The store is a RAW reader — signature VERIFICATION is the gate's chokepoint
    # (verify_and_reduce), not the store. This test only pins disk round-trip.
    store = EventStore(tmp_path / "events")
    priv, _ = keys.generate_keypair()  # raw-reader test: no verification, no pub needed
    store.append(_unsigned(1), priv)
    loaded = list(store.iter_events())
    assert loaded[0].seq == 1 and loaded[0].payload == {"k": 1}
    assert loaded[0].signature  # signed on append, present on read


def test_seq_persists_across_store_reopen(tmp_path):
    priv, _ = keys.generate_keypair()
    EventStore(tmp_path / "events").append(_unsigned(1), priv)
    e2 = EventStore(tmp_path / "events").append(_unsigned(2), priv)
    assert e2.seq == 2
