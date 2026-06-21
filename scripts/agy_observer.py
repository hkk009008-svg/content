#!/usr/bin/env python3
"""Antigravity (agy) read-only observer: a summary of the threeway coordination bus.

agy holds no Layer-1 seat (ANTIGRAVITY-ADOPTION.md) — this is a read-only situational view. It
reports the RAW event stream (it does NOT verify signatures); for an authority-checked view use the
gate's reducer (threeway.gate.verify_and_reduce). Fields are the REAL envelope — `ev.kind`,
`ev.candidate_id`, `ev.subject_sha` (never `event_type` / `subject`).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from threeway.refstore import RefEventStore


def summarize(store) -> dict:
    """Structured RAW summary of the bus: total count + active briefs + candidates + ci_results.
    Returns a dict (also the basis for the printed report). candidates are keyed by candidate_id;
    ci_results by subject_sha (the integration sha)."""
    events = list(store.iter_events())
    briefs: dict = {}
    candidates: dict = {}
    ci_results: dict = {}
    for ev in events:
        if ev.kind == "brief":
            briefs[ev.brief_id] = ev.signer
        elif ev.kind == "brief_superseded":
            briefs.pop(ev.brief_id, None)
        elif ev.kind == "candidate":
            candidates.setdefault(ev.candidate_id, {
                "integration_sha": ev.payload.get("integration_sha"),
                "signer": ev.signer, "attestations": 0,
                "release_requested": False, "release_order": False})
        elif ev.kind == "attestation":
            if ev.candidate_id in candidates:
                candidates[ev.candidate_id]["attestations"] += 1
        elif ev.kind == "release_requested":
            if ev.candidate_id in candidates:
                candidates[ev.candidate_id]["release_requested"] = True
        elif ev.kind == "release_order":
            if ev.candidate_id in candidates:
                candidates[ev.candidate_id]["release_order"] = True
        elif ev.kind == "ci_result":
            ci_results[ev.subject_sha] = ev.payload.get("result", "UNKNOWN")
    return {"total_events": len(events), "briefs": briefs,
            "candidates": candidates, "ci_results": ci_results}


def _print_summary(s: dict) -> None:
    if not s["total_events"]:
        print("Bus is currently empty.")
        return
    print(f"Total events on bus: {s['total_events']}  (RAW view — signatures NOT verified)")
    print("\n--- Active Briefs ---")
    for bid, signer in s["briefs"].items():
        print(f"Brief {bid} | signer {signer}")
    print("\n--- Candidates ---")
    for cid, c in s["candidates"].items():
        print(f"Candidate {cid} | integ {c['integration_sha']} | signer {c['signer']}")
        print(f"  attestations={c['attestations']} release_requested={c['release_requested']} "
              f"release_order={c['release_order']} "
              f"ci={s['ci_results'].get(c['integration_sha'], 'PENDING')}")


def summarize_bus(repo_dir=".") -> dict:
    s = summarize(RefEventStore(Path(repo_dir)))
    _print_summary(s)
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Antigravity read-only threeway bus summary.")
    ap.add_argument("--repo-dir", default=".")
    args = ap.parse_args(argv)
    summarize_bus(args.repo_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
