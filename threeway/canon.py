"""JCS (RFC 8785) canonicalization — the single chokepoint for signed bytes.

Every signature and every digest in this package is computed over the output of
canonicalize(). Determinism across providers/hosts is the load-bearing property,
so there is exactly ONE canonicalizer and it is RFC 8785, not ad-hoc json.dumps.
"""
from __future__ import annotations

import rfc8785


def canonicalize(obj) -> bytes:
    """Return the RFC 8785 canonical UTF-8 byte encoding of a JSON value.

    Raises on values RFC 8785 cannot canonicalize (e.g. non-JSON objects,
    NaN/Infinity), which is intentional — unserializable input must never be
    silently signed.
    """
    return rfc8785.dumps(obj)
