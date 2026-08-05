#!/usr/bin/env python3
"""Strict liveness/readiness probe for the authenticated ComfyUI gateway."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def probe(url: str, mode: str, timeout: float) -> None:
    path = "/health/live" if mode == "liveness" else "/health/ready"
    request = Request(url.rstrip("/") + path, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            if response.headers.get_content_type() != "application/json":
                raise RuntimeError("health endpoint did not return application/json")
            payload = json.load(response)
    except (HTTPError, URLError, json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"{mode} probe failed: {exc}") from exc
    expected = "live" if mode == "liveness" else "ready"
    if not isinstance(payload, dict) or payload.get("status") != expected:
        raise RuntimeError(f"{mode} probe returned unexpected schema: {payload!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8189")
    parser.add_argument("--mode", choices=("liveness", "readiness"), required=True)
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args(argv)
    try:
        probe(args.url, args.mode, args.timeout)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"{args.mode} probe passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
