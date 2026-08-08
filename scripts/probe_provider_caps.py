#!/usr/bin/env python3
"""Measure how many reference images each provider ACTUALLY accepts.

WHY THIS EXISTS
---------------
Two caps in this repository were read from code and both were wrong, and both
were found only by issuing a real request:

    VEO      code said [:4]  -> measured ceiling 3  (ADR-099)
    Kontext  code said [:6]  -> measured ceiling 4  (ADR-100)

Kontext's was not a cosmetic overshoot. It is the reference-conditioned fallback
the cascade reaches when the identity gate rejects Gemini's output; above four
images it hard-fails, the cascade drops through to text-to-image with NO
reference conditioning, and the keyframe comes back as a stranger. The failure
scaled with reference count, so adding good photographs of the subject made the
output worse.

Every remaining cap is a figure of the same kind — written from documentation or
inference, never exercised:

    Seedance   [:8] angle refs alongside a keyframe (9 total)
    Gemini     GEMINI_MULTIREF_MAX_REFS = 8, while vendor docs for the pinned
               tier say FOUR
    Kling 3.0  valid_refs[1:4] as elements beside a frontal

TWO FAILURE SHAPES, AND ONLY ONE IS LOUD
----------------------------------------
Kontext returns an explicit 422 naming the range. VEO returns a soft
`no_media_generated` that reads like the model declining a prompt. The cascade
is built to absorb exactly that second shape and move on, which is right for a
flaky provider and precisely wrong for a request that can never succeed: from
inside the cascade, a provider that always fails is indistinguishable from one
that is unlucky today. This probe therefore records the ERROR TEXT, not just
pass/fail, so the two can be told apart.

COST DISCIPLINE
---------------
A success costs a real generation. The probe starts at the count the code
currently sends — the single most valuable question is "does the shipped value
work?" — and only then walks downward to find the ceiling. Nothing is probed
above the shipped value unless asked, because a higher ceiling is an
optimisation while a lower one is an outage.

`--plan` prices the walk and spends nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _endpoints():
    """Each provider's endpoint, the count the CODE sends, and its payload.

    `counts` is walked in order and stops at the first success, so the shipped
    value is always tried first.
    """

    from cost_tracker import API_COST_USD

    return [
        {
            "name": "kontext",
            "endpoint": "fal-ai/flux-pro/kontext/max/multi",
            "engine": "FLUX_KONTEXT",
            "unit_usd": API_COST_USD["FLUX_KONTEXT"],
            "code_sends": 4,          # post ADR-100
            "counts": [4, 3, 2, 1],
            "build": lambda urls: {
                "prompt": "PRESERVE IDENTITY: keep the exact person from @Image1. "
                          "CHANGE BACKGROUND: a quiet kitchen at first light.",
                "image_urls": urls, "num_images": 1, "aspect_ratio": "16:9",
            },
        },
        {
            "name": "veo",
            "endpoint": "fal-ai/veo3.1/reference-to-video",
            "engine": "VEO",
            "unit_usd": API_COST_USD["VEO"],
            "code_sends": 3,          # post ADR-099
            "counts": [3, 2, 1],
            "build": lambda urls: {
                "prompt": "MOTION: slow push in. Cinematic.",
                "image_urls": urls, "aspect_ratio": "16:9",
                "duration": "8s", "resolution": "720p", "generate_audio": False,
            },
        },
        {
            "name": "seedance",
            # The path the shipped code uses (phase_c_ffmpeg.py:2541). My first
            # probe prefixed "fal-ai/" and got a 404 — reading the
            # endpoint out of the code beats reconstructing it.
            "endpoint": "bytedance/seedance-2.0/reference-to-video",
            "engine": "SEEDANCE",
            "unit_usd": API_COST_USD["SEEDANCE"],
            "code_sends": 9,          # keyframe + [:8]
            "counts": [9, 5, 3, 2],
            "build": lambda urls: {
                # Mirrors phase_c_ffmpeg.py:2528-2542 exactly. duration is an
                # INT there, not a string; a probe that guesses the payload
                # measures the guess.
                "prompt": "MOTION: slow push in. Cinematic.",
                "image_urls": urls, "aspect_ratio": "16:9",
                "resolution": "720p", "duration": 4, "generate_audio": False,
            },
        },
    ]


def _probe(entry, refs, keyframe):
    import fal_client

    uploads = [fal_client.upload_file(p) for p in [keyframe, *refs]]
    rows = []
    for count in entry["counts"]:
        urls = uploads[:count]
        if len(urls) < count:
            rows.append({"count": count, "result": "skipped",
                         "detail": "not enough distinct images available"})
            continue
        started = time.time()
        try:
            fal_client.subscribe(entry["endpoint"], arguments=entry["build"](urls))
            rows.append({"count": count, "result": "accepted",
                         "seconds": round(time.time() - started, 1)})
            print(f"   {entry['name']:9s} {count:2d} images -> ACCEPTED", flush=True)
            break
        except Exception as exc:
            text = str(exc)
            # The distinction that matters: an explicit range rejection is a
            # contract statement; a soft refusal could be this prompt today.
            shape = "schema" if "must be between" in text or "value_error" in text \
                else "soft" if "no_media_generated" in text else "other"
            rows.append({"count": count, "result": "rejected", "shape": shape,
                         "detail": text[:400]})
            print(f"   {entry['name']:9s} {count:2d} images -> REJECTED ({shape})",
                  flush=True)
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true", help="price it; spend nothing")
    parser.add_argument("--run", default="",
                        help="comma-separated provider names (COSTS MONEY)")
    parser.add_argument("--authorize-usd", type=float, default=None)
    args = parser.parse_args(argv)

    entries = _endpoints()
    selected = {t.strip().lower() for t in args.run.split(",") if t.strip()}
    chosen = [e for e in entries if not selected or e["name"] in selected]

    print("PROVIDER CAP PROBE — the code's number is tried FIRST\n")
    worst = 0.0
    for entry in chosen:
        walk = " -> ".join(str(c) for c in entry["counts"])
        cost = entry["unit_usd"] * len(entry["counts"])
        worst += cost
        print(f"  {entry['name']:9s} code sends {entry['code_sends']:2d}   "
              f"walk {walk:16s}  worst case {len(entry['counts'])} x "
              f"${entry['unit_usd']:.2f} = ${cost:.2f}")
    print(f"\nWORST CASE TOTAL: ${worst:.2f}  (each provider STOPS at its first "
          f"acceptance, so the real cost is usually far lower)")

    if not selected:
        return 0
    if args.authorize_usd is None or args.authorize_usd + 1e-9 < worst:
        print(f"\nREFUSED: pass --authorize-usd >= {worst:.2f} to run.")
        return 1

    from config.settings import settings  # loads .env -> FAL_KEY
    from domain.project_manager import load_project
    from domain.character_manager import get_multi_angle_refs

    project = load_project("42c74e230519")
    refs = [r for r in get_multi_angle_refs(project, project["characters"][0]["id"])
            if os.path.exists(r)]
    keyframe = sorted((REPO / "logs" / "evidence").glob("*/H4/*_keyframe.jpg"))[-1]

    findings = {}
    for entry in chosen:
        print(f"\nprobing {entry['name']} ({entry['endpoint']})")
        findings[entry["name"]] = {
            "endpoint": entry["endpoint"],
            "code_sends": entry["code_sends"],
            "attempts": _probe(entry, refs, str(keyframe)),
        }

    out = REPO / "logs" / "evidence" / "provider-caps.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(findings, indent=2), encoding="utf-8")
    print(f"\nartifact: {out.relative_to(REPO)}")
    for name, data in findings.items():
        accepted = [a["count"] for a in data["attempts"] if a["result"] == "accepted"]
        ceiling = max(accepted) if accepted else None
        verdict = ("MATCHES the code" if ceiling == data["code_sends"]
                   else f"CODE SENDS {data['code_sends']}, ceiling {ceiling}")
        print(f"  {name:9s} ceiling={ceiling}  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
