#!/usr/bin/env python3
"""Verify Anthropic prompt caching is hitting in production.

Makes two direct Anthropic SDK calls with an identical, sufficiently-large
system block (cache_control={'type':'ephemeral'}). Reads
response.usage.cache_read_input_tokens and reports whether call 2 hit the
cache.

This is the runtime counterpart to tests/unit/test_llm_caching.py. The
tests prove we OPT INTO caching at the request shape level (system is a
list-of-blocks with cache_control). This script proves Anthropic actually
SERVES from the cache when warm — something only a real API round-trip can
demonstrate.

Usage:
    .venv/bin/python scripts/verify_llm_caching.py

Exit codes:
    0  — caching verified (call 2 had cache_read > 0)
    1  — caching NOT working (call 2 had cache_read == 0)
    2  — script error (missing API key, network failure, SDK missing)

Notes:
    - Anthropic requires ~1024 tokens of cached content (Sonnet/Opus) or
      ~2048 (Haiku) before the system block is cached. This script pads
      the system_text to ~1250 tokens to ensure cacheability.
    - The ephemeral cache TTL is ~5 minutes. The two calls in this script
      are made back-to-back so the cache is warm for call 2.
    - Run this once after any change to llm/ensemble.py:build_anthropic_system_blocks
      or to the cache_control configuration in any call site.

Cost: ~$0.005 per run (two short messages on Sonnet). Run sparingly.
"""

from __future__ import annotations

import os
import sys
import time

# Bootstrap sys.path so we can import from the repo root regardless of CWD.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def main() -> int:
    try:
        import anthropic
        from config.settings import settings
        from llm.ensemble import build_anthropic_system_blocks
    except ImportError as exc:
        print(f"[verify-caching] import failed: {exc}", file=sys.stderr)
        return 2

    if not settings.anthropic_api_key:
        print(
            "[verify-caching] no settings.anthropic_api_key — check ANTHROPIC_API_KEY env var",
            file=sys.stderr,
        )
        return 2

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Pad the system block past the 1024-token minimum cacheable size.
    # ~5 tokens per repetition × 250 reps = ~1250 tokens of filler.
    base_prompt = "You are a test assistant. Respond with a single word: ok. "
    padding = "Verification context: avoid embellishment, just say ok. " * 250
    system_text = base_prompt + padding

    rough_tokens = len(system_text) // 4
    print(f"[verify-caching] system_text length: ~{rough_tokens} tokens (rough estimate)")
    if rough_tokens < 1024:
        print(
            "[verify-caching] WARNING: system_text below 1024 token minimum — "
            "Anthropic won't cache it. Increase padding.",
            file=sys.stderr,
        )

    def call_with_stats(label: str, user_prompt: str) -> tuple[int, int]:
        """Make one Anthropic call and return (cache_creation_tokens, cache_read_tokens)."""
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=32,
            system=build_anthropic_system_blocks(system_text),
            messages=[{"role": "user", "content": user_prompt}],
        )
        creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        input_tokens = getattr(response.usage, "input_tokens", 0) or 0
        print(
            f"[verify-caching] {label}: "
            f"input={input_tokens} cache_creation={creation} cache_read={read}"
        )
        return creation, read

    print("[verify-caching] === call 1 (cold — expect cache_creation > 0) ===")
    try:
        creation_1, _read_1 = call_with_stats("call 1", "Say ok.")
    except anthropic.APIError as exc:
        print(f"[verify-caching] call 1 API error: {exc}", file=sys.stderr)
        return 2

    # Brief pause; cache should still be warm well within the 5-min TTL.
    time.sleep(1.0)

    print("[verify-caching] === call 2 (warm — expect cache_read > 0) ===")
    try:
        creation_2, read_2 = call_with_stats("call 2", "Say ok again.")
    except anthropic.APIError as exc:
        print(f"[verify-caching] call 2 API error: {exc}", file=sys.stderr)
        return 2

    print()
    if read_2 > 0:
        print(
            f"[verify-caching] PASS — call 2 read {read_2} tokens from cache "
            f"(call 1 created {creation_1})."
        )
        return 0
    if creation_1 == 0 and creation_2 == 0:
        print(
            "[verify-caching] FAIL — NO CACHE ACTIVITY ON EITHER CALL.\n"
            "  Likely cause: system_text below Anthropic's minimum cacheable size.\n"
            "  Try increasing the padding multiplier in this script.",
            file=sys.stderr,
        )
        return 1
    print(
        f"[verify-caching] FAIL — call 2 read {read_2} tokens.\n"
        f"  Cache was created on call 1 (created={creation_1}) but not read on call 2.\n"
        f"  Possible causes:\n"
        f"    - Cache TTL expired between calls (5 min for ephemeral)\n"
        f"    - System block differed byte-for-byte between calls\n"
        f"    - Anthropic region routing didn't co-locate the calls",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
