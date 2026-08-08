#!/usr/bin/env python3
"""Is each NATIVE video engine actually reachable, or only present in the code?

WHY
---
Operator directive 2026-08-09: prefer a provider's own API; use fal only where
it is the only option. Auditing `DEFAULT_VIDEO_CASCADE` against that turned up
something I had reported wrongly and want measured instead of asserted.

`GEMINI_OMNI` and `SORA_NATIVE` are absent from the default cascade while
`KLING_3_0` (a fal proxy) is in it. I told the operator they were excluded by a
"product-support policy". THEY ARE NOT. The policy blocks
{NOT_IMPLEMENTED, DISCONNECTED, KNOWN_BROKEN, UNSUPPORTED}; both are classified
`limited`, and so are `VEO_NATIVE` and `RUNWAY_GEN4`, which ARE in the cascade —
one of them first. They are simply missing from a hardcoded list with no
comment, no ADR and no recorded reason anywhere in the repository. A test pins
their absence, which preserves the status quo without justifying it.

So the exclusion has no evidence behind it. This probe produces some.

ONE EXCEPTION WORTH KNOWING: `KLING_NATIVE` is NOT the modern native path. The
catalog describes it as "Kling Native (legacy v1.6) — deprecated explicit-only
kling-v1-6 JWT compatibility route; automatic Kling uses KLING_3_0". Preferring
it over the fal-hosted KLING_3_0 would downgrade two model generations, so fal
genuinely is the only route to current Kling and the directive is satisfied by
leaving it alone.

WHAT IS MEASURED, AND WHAT IS NOT
---------------------------------
FREE tier only, by design. For each engine: does the module import, does the
client construct, do its credentials resolve? That is enough to separate "wired
and reachable" from "present in the code and dead", which is the question the
cascade ordering actually turns on.

It deliberately does NOT generate. A readiness answer should not cost $0.25-1.51
per engine, and three provider caps measured today (VEO 4->3, Kontext 6->4,
Seedance 9 OK) show that generation probes are worth spending on only once a
cheaper check has narrowed the field.

A PASS here means reachable, NOT good. Whether an engine belongs in the cascade
is a quality decision this script cannot make.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

ENGINES = [
    {
        "key": "VEO_NATIVE", "module": "veo_native", "provider": "google (Vertex)",
        "in_cascade": True,
        "check": lambda m: m.VeoNativeAPI(),
    },
    {
        "key": "GEMINI_OMNI", "module": "gemini_omni_native", "provider": "google_gemini_api",
        "in_cascade": False,
        "check": lambda m: m.GeminiOmniAPI(),
    },
    {
        "key": "SORA_NATIVE", "module": "sora_native", "provider": "openai",
        "in_cascade": False,
        "check": lambda m: m.SoraNativeAPI(),
    },
    {
        # No wrapper module: the branch imports the `runwayml` SDK directly
        # (phase_c_ffmpeg.py:2027) and authenticates with
        # settings.runwayml_api_secret — a key my first credential scan missed
        # because it does not end in "_key".
        "key": "RUNWAY_GEN4", "module": "runwayml", "provider": "runway",
        "in_cascade": True,
        "check": lambda m: m.RunwayML(
            api_key=__import__("config.settings", fromlist=["settings"]).settings.runwayml_api_secret
        ),
    },
]


def main() -> int:
    from config.settings import settings  # noqa: F401  — loads .env

    print("NATIVE ENGINE READINESS — free checks only, nothing is generated\n")
    print(f"{'engine':14s}{'in cascade':12s}{'provider':22s}{'verdict'}")
    results = {}
    for entry in ENGINES:
        key = entry["key"]
        try:
            module = __import__(entry["module"])
        except Exception as exc:
            results[key] = f"MODULE MISSING ({type(exc).__name__})"
            print(f"{key:14s}{str(entry['in_cascade']):12s}{entry['provider']:22s}{results[key]}")
            continue
        try:
            client = entry["check"](module)
            results[key] = "REACHABLE" if client is not None else "NO CLIENT CLASS"
        except Exception as exc:
            # A credential error is the interesting negative: the code is wired
            # but the account is not, which is a different fix from missing code.
            text = str(exc)[:90].replace("\n", " ")
            results[key] = f"NOT READY: {type(exc).__name__}: {text}"
        print(f"{key:14s}{str(entry['in_cascade']):12s}{entry['provider']:22s}{results[key]}")

    print("\nA PASS means reachable, not good. Promoting an engine into the "
          "cascade is a quality decision this script cannot make.")
    missing = [k for k, v in results.items() if v == "REACHABLE"
               and not next(e for e in ENGINES if e["key"] == k)["in_cascade"]]
    if missing:
        print(f"\nREACHABLE BUT EXCLUDED FROM THE DEFAULT CASCADE: {missing}")
        print("These are native paths with working credentials, kept out by a "
              "list with no recorded rationale.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
