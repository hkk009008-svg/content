#!/usr/bin/env python3
"""Shared mailbox protocol vocabulary."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
KIND_FILE = ROOT / "coordination" / "mailbox" / "kinds.txt"
SEATS = ("director", "director2", "operator", "operator2")
SENDERS = (*SEATS, "coordinator")
RECIPIENTS = (*SEATS, "all")


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
