#!/usr/bin/env python3
"""Provider-catalog claim checker (Slice 14a — generated-facts validation).

``config/prompts/pipeline_context.md`` and the ``ai-video-gen`` SKILL.md
(both the ``.agents/skills/`` and ``.claude/skills/`` copies) assert specific
lifecycle/product-support/parameter facts about a handful of video engines.
``domain/provider_catalog.py``'s ``CATALOG`` is the single typed source of
truth for those facts (see ARCHITECTURE.md's provider-ledger section). This
script re-derives the facts from ``CATALOG`` and fails loud if a doc's claim
has drifted, instead of trusting hand-maintained prose forever.

Checked claims (the exact drift Slice 14a found and fixed):
  - GEMINI_OMNI is routable        (repaired/re-admitted 2026-07-30 — not in
                                     a broken product-support state)
  - SORA_2 is fully retired        (Lifecycle.RETIRED + ProductSupport.UNSUPPORTED)
  - RUNWAY_ACT_ONE is retired      (migrated to Act-Two; catalog key kept for
                                     compat — Lifecycle.RETIRED + KNOWN_BROKEN)
  - VIGGLE is KNOWN_BROKEN         (contained pending a dedicated repair slice)
  - LTX duration is exactly {6, 8, 10} seconds

This is a narrow, hand-picked fact set, not a general doc-claim parser — it
exists so the next drift in THESE specific facts fails loud instead of
rotting quietly, mirroring check_env_example.py's job for .env.example.
Prose rationale in the docs stays human-authored; only the underlying typed
facts are machine-checked here (plan invariant 8: generated facts, authored
rationale).

Public API
----------
check(repo_root) -> list[str]   drift messages (empty = clean)
main(argv=None) -> int          exit 0=clean, 1=drift, >1=error

Usage:
  .venv/bin/python scripts/check_provider_catalog_claims.py
  .venv/bin/python scripts/check_provider_catalog_claims.py --check   # explicit alias
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check(repo_root: Path = ROOT) -> list[str]:
    """Return a list of human-readable drift messages; empty means clean."""
    # Imported lazily (after sys.path setup) so this module stays importable
    # for its own docstring/--help without requiring the repo layout.
    from domain.provider_catalog import CATALOG, Lifecycle, ProductSupport

    messages: list[str] = []
    _BROKEN_SUPPORT = {
        ProductSupport.KNOWN_BROKEN,
        ProductSupport.NOT_IMPLEMENTED,
        ProductSupport.DISCONNECTED,
        ProductSupport.UNSUPPORTED,
    }

    def _entry_or_missing(key: str, claim: str) -> object | None:
        entry = CATALOG.get(key)
        if entry is None:
            messages.append(
                f"{key} is missing from CATALOG entirely — docs assume {claim}"
            )
        return entry

    gemini_omni = _entry_or_missing(
        "GEMINI_OMNI", "it is the repaired, routable Google-first primary"
    )
    if gemini_omni is not None and (
        gemini_omni.lifecycle is Lifecycle.RETIRED
        or gemini_omni.product_support in _BROKEN_SUPPORT
    ):
        messages.append(
            f"GEMINI_OMNI is lifecycle={gemini_omni.lifecycle}/"
            f"support={gemini_omni.product_support} — pipeline_context.md and "
            f"the ai-video-gen SKILL.md decision tree claim it is the "
            f"repaired, routable Google-first primary; re-verify"
        )

    sora_2 = _entry_or_missing("SORA_2", "it is a fully retired, unsupported entry")
    if sora_2 is not None and not (
        sora_2.lifecycle is Lifecycle.RETIRED
        and sora_2.product_support is ProductSupport.UNSUPPORTED
    ):
        messages.append(
            f"SORA_2 is lifecycle={sora_2.lifecycle}/support={sora_2.product_support} "
            f"— the ai-video-gen SKILL.md claims it is fully RETIRED/UNSUPPORTED "
            f"(distinct from the still-dispatchable, pre-sunset SORA_NATIVE)"
        )

    act_one = _entry_or_missing(
        "RUNWAY_ACT_ONE", "it is retired/broken, migrated to Act-Two"
    )
    if act_one is not None and not (
        act_one.lifecycle is Lifecycle.RETIRED
        and act_one.product_support is ProductSupport.KNOWN_BROKEN
    ):
        messages.append(
            f"RUNWAY_ACT_ONE is lifecycle={act_one.lifecycle}/"
            f"support={act_one.product_support} — the ai-video-gen SKILL.md "
            f"claims Act-One is retired/broken and migrated to Act-Two; "
            f"re-verify that migration note is still accurate"
        )

    viggle = _entry_or_missing("VIGGLE", "it is a contained, KNOWN_BROKEN entry")
    if viggle is not None and viggle.product_support is not ProductSupport.KNOWN_BROKEN:
        messages.append(
            f"VIGGLE product_support is {viggle.product_support}, not "
            f"KNOWN_BROKEN — the ai-video-gen SKILL.md and .env.example claim "
            f"it is contained/broken pending a dedicated repair slice"
        )

    ltx = _entry_or_missing("LTX", "it has a duration ParameterConstraint of {6, 8, 10}")
    if ltx is not None:
        duration = next((p for p in ltx.parameters if p.name == "duration"), None)
        allowed = set(duration.allowed_values) if duration is not None else None
        if allowed != {6, 8, 10}:
            messages.append(
                f"LTX duration allowed_values is {allowed}, not {{6, 8, 10}} — "
                f"pipeline_context.md, the ai-video-gen SKILL.md, and "
                f".env.example all claim 6/8/10s-only clips (6s default)"
            )

    return messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Explicit alias for the (only) verification mode this script runs.",
    )
    parser.parse_args(argv)

    messages = check()
    if not messages:
        print(
            "OK: pipeline_context.md / ai-video-gen SKILL.md provider-lifecycle "
            "claims match domain/provider_catalog.py."
        )
        return 0

    print(
        f"DRIFT: {len(messages)} provider-catalog claim(s) no longer match "
        f"domain/provider_catalog.py:"
    )
    for msg in messages:
        print(f"  - {msg}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
