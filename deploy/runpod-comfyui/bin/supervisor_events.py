#!/usr/bin/env python3
"""Exit the container when the guarded ComfyUI process leaves RUNNING."""

from __future__ import annotations

import os
import signal
import sys


def _headers(line: str) -> dict[str, str]:
    return dict(item.split(":", 1) for item in line.strip().split())


def main() -> None:
    while True:
        sys.stdout.write("READY\n")
        sys.stdout.flush()
        header_line = sys.stdin.readline()
        if not header_line:
            return
        headers = _headers(header_line)
        payload = sys.stdin.read(int(headers["len"]))
        sys.stdout.write("RESULT 2\nOK")
        sys.stdout.flush()
        payload_headers = _headers(payload.splitlines()[0]) if payload else {}
        if payload_headers.get("processname") == "comfyui":
            os.kill(os.getppid(), signal.SIGTERM)


if __name__ == "__main__":
    main()
