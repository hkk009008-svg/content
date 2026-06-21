"""RefEventStore — the spec §8 event-sourced substrate (remote push-CAS or local).

One git commit per event on EVENTS_REF; the tree adds the signed event JSON
(events/<brief_id>/<id>.json) + its index entry (index/<seq:08d>). seq is allocated
from the AUTHORITATIVE tip and the event is RE-SIGNED on every retry (seq is signed).
iter_events()/all_events() are RAW readers (no signature verify — the gate's chokepoint
is threeway.gate, §6.4); idempotency dedup DOES verify (a forged event must not suppress
a legitimate append — Blocker 1: key-match ALONE is not sufficient).

Two modes:
  * remote (authoritative, §8): `remote` names a bare authoritative bus repo. append
    FETCHES the authoritative `events` ref, reads the tip, allocates seq, signs, builds
    the extending tree, commits, and PUSH-CAS (force-with-lease against the fetched tip).
    On rejection it re-fetches, re-seqs, re-signs and retries.
  * local (co-located): remote=None -> atomic update-ref CAS in one repo.

The idempotency scan is O(events) per attempt (it re-scans every event to recompute
+ verify keys) — the store therefore assumes a bounded coordination-scale event count.
"""
from __future__ import annotations

import hashlib
import json
import random
import time

from cryptography.exceptions import InvalidSignature

from threeway import gitcas, keys
from threeway.canon import canonicalize
from threeway.envelope import (
    Event,
    from_json_obj,
    idempotency_key,
    payload_digest,
    sign_event,
    to_json_obj,
    verify_event,
)

EVENTS_REF = "refs/threeway/events"
_DEFAULT_MAX_ATTEMPTS = 50
_BACKOFF_BASE = 0.005
_BACKOFF_CAP = 0.5


class BusContentionError(RuntimeError):
    pass


class AppendContentionExceeded(BusContentionError):
    pass


class IdempotencyKeyReused(ValueError):
    pass


class EventIdCollision(ValueError):
    # ADR-037: event `id` must be globally unique. A colliding (brief_id,id) from another
    # seat (or a different request) would OVERWRITE the victim's stored blob — refuse it.
    pass


class CursorContentionExceeded(BusContentionError):   # used by a later (cursor) task
    pass


class CursorCorruptionError(ValueError):              # used by a later (cursor) task
    pass


def _request_fingerprint(ev: Event) -> str:
    # actor-scoped CANONICAL request hash — the COMPLETE logical request, not just the
    # idempotency_key formula (which omits to/candidate_id/causation_id). Excludes uuid,
    # seq, signature, created_at so a re-minted retry of the same fact still matches.
    # INCLUDES the load-bearing revokes_event_id/supersedes_event_id (ADR-044) so a
    # revoke/supersede of a DIFFERENT target is a distinct request, never deduped to a prior.
    view = {
        "from": ev.sender, "to": ev.recipient, "kind": ev.kind,
        "brief_id": ev.brief_id, "candidate_id": ev.candidate_id,
        "subject_sha": ev.subject_sha, "brief_version": ev.brief_version,
        "causation_id": ev.causation_id, "payload_digest": payload_digest(ev),
        "revokes_event_id": ev.revokes_event_id,
        "supersedes_event_id": ev.supersedes_event_id,
    }
    return hashlib.sha256(canonicalize(view)).hexdigest()


class RefEventStore:
    def __init__(self, repo, remote=None, events_ref=EVENTS_REF,
                 max_attempts=_DEFAULT_MAX_ATTEMPTS, sleeper=time.sleep):
        self._repo = repo
        self._remote = remote
        self._ref = events_ref
        self._max_attempts = max_attempts
        self._sleep = sleeper

    def _sync(self):
        # remote: fetch AUTHORITATIVE state into the local ref; local: repo is authority.
        if self._remote is not None:
            return gitcas.fetch_ref(self._repo, self._remote, self._ref)
        return gitcas.rev_parse(self._repo, self._ref)

    def _find_verified_idempotent(self, target_key, my_pub_hex):
        # recompute the key (never trust the serialized value) + verify the signature
        # against the appender's OWN pubkey so a forged/unsigned event cannot suppress
        # a legitimate append.
        # dedup is scoped to the appender's keypair; one seat ⇒ one signing key
        # (load_private(seat) loads one key) — a second key under the same `sender`
        # would legitimately produce a distinct event, not a dup.
        # Iterate _iter_local (NOT iter_events): append already _sync()s at the loop
        # top, so this scan must not re-fetch the remote (hot-path: one fetch/attempt).
        # NOTE: O(events) per attempt — the store assumes a bounded coordination-scale
        # event count.
        for ev in self._iter_local():
            if idempotency_key(ev) != target_key:
                continue
            try:
                verify_event(ev, my_pub_hex)
            except InvalidSignature:
                continue
            return ev
        return None

    def _backoff(self, attempt):
        base = min(_BACKOFF_CAP, _BACKOFF_BASE * (2 ** attempt))
        return base * (0.5 + random.random() * 0.5)

    # _before_cas / _after_cas are test seams (Task 9 fault injection:
    # forced-CAS-loss / lost-ack); None in production.
    def append(self, ev, private_key, _before_cas=None, _after_cas=None):
        target_key = idempotency_key(ev)
        target_fp = _request_fingerprint(ev)
        my_pub_hex = keys.public_hex(private_key)
        for attempt in range(self._max_attempts):
            tip = self._sync()
            existing = self._find_verified_idempotent(target_key, my_pub_hex)
            if existing is not None:
                if _request_fingerprint(existing) == target_fp:
                    return existing
                raise IdempotencyKeyReused(
                    f"idempotency_key collides with a different request: {target_key}")
            # ADR-037: event id must be GLOBALLY unique — the gate (seen_ids) and reducer
            # (seat_by_id) key on id ALONE, so uniqueness must be brief- AND kind-agnostic. A
            # per-(brief_id,id) path check is bypassable (brief_id is attacker-chosen), so scan
            # by id across the whole bus. Our idempotent re-append was already returned above,
            # so any other event carrying this id is a genuine collision — refuse, never OVERWRITE.
            if any(e.id == ev.id for e in self._iter_local()):
                raise EventIdCollision(f"event id already present: {ev.id!r}")
            event_path = f"events/{ev.brief_id}/{ev.id}.json"
            seqs = gitcas.list_index_seqs(self._repo, tip) if tip else []
            ev.seq = (max(seqs) + 1) if seqs else 1
            sign_event(ev, private_key)                    # signs over the NEW seq
            event_bytes = json.dumps(to_json_obj(ev), ensure_ascii=False).encode()
            digest = hashlib.sha256(event_bytes).hexdigest()
            index_bytes = json.dumps(
                {"uuid": ev.id, "path": event_path, "object_digest": digest},
                ensure_ascii=False).encode()
            index_path = f"index/{ev.seq:08d}"
            blob_e = gitcas.write_blob(self._repo, event_bytes)
            blob_i = gitcas.write_blob(self._repo, index_bytes)
            # tree_of (NOT rev_parse) — rev_parse hardcodes a ^{commit} peel that would
            # double-peel ^{tree} to None and silently drop all prior events.
            base_tree = gitcas.tree_of(self._repo, tip) if tip else None
            tree = gitcas.build_tree_with(
                self._repo, base_tree,
                [(event_path, blob_e), (index_path, blob_i)])
            commit = gitcas.commit_on(self._repo, tree, tip, f"threeway event {ev.seq:08d}")
            if _before_cas is not None:
                _before_cas(attempt)
            if self._remote is not None:
                won = gitcas.push_cas(self._repo, self._remote, commit, self._ref, tip)
            else:
                won = gitcas.cas_create_or_update_ref(self._repo, self._ref, commit, tip)
            if won:
                if _after_cas is not None:
                    _after_cas(attempt)
                return ev
            self._sleep(self._backoff(attempt))            # re-loop: re-fetch + re-seq + re-sign
        raise AppendContentionExceeded(
            f"append lost CAS {self._max_attempts}x for {ev.id}")

    def _iter_local(self):
        # reads the LOCAL ref, NO sync. append's idempotency scan uses this directly
        # (append already _sync()s at the loop top, so it must not re-fetch). Public
        # readers go through iter_events()/all_events(), which sync first in remote mode.
        tip = gitcas.rev_parse(self._repo, self._ref)
        if tip is None:
            return
        for seq in gitcas.list_index_seqs(self._repo, tip):
            idx = gitcas.read_blob_at(self._repo, tip, f"index/{seq:08d}")
            if idx is None:
                continue
            entry = json.loads(idx)
            raw = gitcas.read_blob_at(self._repo, tip, entry["path"])
            if raw is None:
                continue
            yield from_json_obj(json.loads(raw))

    def iter_events(self):
        # remote-safe public reader: a direct external caller (not via append, which
        # already syncs) would otherwise read stale/empty local state in remote mode.
        if self._remote is not None:
            self._sync()                                   # refresh local ref from authority
        yield from self._iter_local()

    def all_events(self):
        if self._remote is not None:
            self._sync()                                   # refresh local ref from authority
        return list(self._iter_local())                    # _iter_local: avoid double-sync

    # ---- per-seat cursors: refs/threeway/cursors/<seat> (spec §8) -------------
    # A cursor = "last seq scanned," stored as a blob (decimal seq text) the ref
    # points at DIRECTLY (git allows a ref -> blob). Advanced only by CAS.
    def _cursor_ref(self, seat: str) -> str:
        return f"refs/threeway/cursors/{seat}"

    def _read_cursor(self, ref):
        oid = gitcas.rev_parse_any(self._repo, ref)        # blob, not commit
        if oid is None:
            return None, 0
        raw = gitcas.read_blob(self._repo, oid)
        # Type ALL malformedness as CursorCorruptionError (never a bare error, never a
        # silent 0 — silent-gate-degradation bug class). Wrap BOTH the decode and the
        # int-parse: a non-UTF-8 blob raises UnicodeDecodeError before any guard, and a
        # Unicode digit ('²'.isdigit() is True) passes isdigit() but int() raises bare.
        try:
            val = int(raw.decode("utf-8").strip())
        except (UnicodeDecodeError, ValueError):
            raise CursorCorruptionError(f"cursor blob is not a non-negative int: {raw!r}")
        if val < 0:                                        # malformed -> corruption, not 0
            raise CursorCorruptionError(f"cursor blob is negative: {val}")
        return oid, val

    def cursor_seq(self, seat: str) -> int:
        return self._read_cursor(self._cursor_ref(seat))[1]

    def advance_cursor(self, seat: str, seq: int) -> bool:
        # LOCAL-ONLY BY DESIGN: the cursor blob is written via the LOCAL
        # gitcas.cas_create_or_update_ref, NOT push_cas — unlike append(), which
        # publishes events to the remote authority. A cursor is per-seat "last seq
        # scanned" progress for THIS clone; remote/multi-host cursor publishing is
        # deferred Slice-3 work (spec §13). The asymmetry is intentional.
        # The _sync() + in-range validation below still run against the AUTHORITATIVE
        # event head: even though the cursor WRITE stays local, a cursor must never be
        # advanced past events that exist on the authority.
        #
        # Owner-only enforcement (spec §8 point 3 "writable only by that seat") is a
        # DEPLOYMENT ref-ACL concern — it cannot be enforced in a single local repo, so
        # it is test-infeasible here (the real guard is the bus's ref-ACL layer). The API
        # takes `seat`; the caller advances only its OWN cursor.
        if seq < 0:
            raise ValueError("cursor seq must be non-negative")
        tip = self._sync()                                 # authoritative event head
        valid = set(gitcas.list_index_seqs(self._repo, tip)) if tip else set()
        if seq != 0 and seq not in valid:
            raise ValueError(f"cursor seq {seq} has no index entry / is beyond the event head")
        ref = self._cursor_ref(seat)
        for attempt in range(self._max_attempts):
            cur_oid, cur = self._read_cursor(ref)
            if seq <= cur:
                return False                               # monotonic: regression / no-op
            new_oid = gitcas.write_blob(self._repo, f"{seq}\n".encode())
            if gitcas.cas_create_or_update_ref(self._repo, ref, new_oid, cur_oid):
                return True
            self._sleep(self._backoff(attempt))            # CAS lost a concurrent advance; re-read
        raise CursorContentionExceeded(f"cursor CAS lost for {seat}")
