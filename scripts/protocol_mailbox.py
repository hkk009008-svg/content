#!/usr/bin/env python3
"""Shared mailbox protocol vocabulary."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
KIND_FILE = ROOT / "coordination" / "mailbox" / "kinds.txt"
SEATS = ("director", "director2", "operator", "operator2")
# Oversight-inclusive receiving roster: the 4 pair seats + both coordinators.
# `all` is a broadcast TARGET only (kept in RECIPIENTS), never a real seat, so it
# is NOT in RECEIVING_SEATS. Every independent Python roster copy imports THIS as
# its source of truth (Slice 2.5 D1 consolidation); the 4 shell whitelists are
# hand-synced and guarded by the token-extraction test (spec §8 clause #2).
RECEIVING_SEATS = (*SEATS, "coordinator", "coordinator2")
SENDERS = (*SEATS, "coordinator", "coordinator2")
RECIPIENTS = (*RECEIVING_SEATS, "all")


def load_known_kinds(root: Path | None = None) -> frozenset[str]:
    base = root if root is not None else ROOT
    path = base / "coordination" / "mailbox" / "kinds.txt"
    kinds = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            kinds.append(stripped)
    return frozenset(kinds)


KNOWN_KINDS = load_known_kinds()
COORDINATION_KINDS = KNOWN_KINDS - {"verification-report"}
