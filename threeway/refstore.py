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


class CursorContentionExceeded(BusContentionError):   # used by a later (cursor) task
    pass


class CursorCorruptionError(ValueError):              # used by a later (cursor) task
    pass


def _request_fingerprint(ev: Event) -> str:
    # actor-scoped CANONICAL request hash — the COMPLETE logical request, not just the
    # idempotency_key formula (which omits to/candidate_id/causation_id). Excludes uuid,
    # seq, signature, created_at so a re-minted retry of the same fact still matches.
    view = {
        "from": ev.sender, "to": ev.recipient, "kind": ev.kind,
        "brief_id": ev.brief_id, "candidate_id": ev.candidate_id,
        "subject_sha": ev.subject_sha, "brief_version": ev.brief_version,
        "causation_id": ev.causation_id, "payload_digest": payload_digest(ev),
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
        for ev in self.iter_events():
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
            seqs = gitcas.list_index_seqs(self._repo, tip) if tip else []
            ev.seq = (max(seqs) + 1) if seqs else 1
            sign_event(ev, private_key)                    # signs over the NEW seq
            event_bytes = json.dumps(to_json_obj(ev), ensure_ascii=False).encode()
            event_path = f"events/{ev.brief_id}/{ev.id}.json"
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

    def iter_events(self):
        # reads the LOCAL ref (call _sync() first in remote mode — all_events does).
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

    def all_events(self):
        if self._remote is not None:
            self._sync()                                   # refresh local ref from authority
        return list(self.iter_events())
