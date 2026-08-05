#!/usr/bin/env python3
"""Run ComfyUI under Supervisor and publish readiness only after full validation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from typing import Any

from startup_guard import StartupGuardError, verify_backend


class ComfySupervisor:
    def __init__(self, command: list[str], sentinel: Path) -> None:
        self.command = command
        self.sentinel = sentinel
        self.child: subprocess.Popen[Any] | None = None
        self.forwarded_signal: int | None = None

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        self.forwarded_signal = signum
        if self.child is not None and self.child.poll() is None:
            os.killpg(self.child.pid, signum)

    def _remove_sentinel(self) -> None:
        self.sentinel.unlink(missing_ok=True)

    def _write_sentinel(self, payload: dict[str, Any]) -> None:
        self.sentinel.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=".ready-", suffix=".json",
            dir=self.sentinel.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.sentinel)

    def run(self, *, backend_url: str, workflow: Path, startup_timeout: float) -> int:
        self._remove_sentinel()
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
        self.child = subprocess.Popen(self.command, start_new_session=True)
        try:
            ready = verify_backend(backend_url, workflow, startup_timeout=startup_timeout)
            ready["pid"] = self.child.pid
            self._write_sentinel(ready)
            print("ComfyUI startup contract passed; readiness published", flush=True)
            return_code = self.child.wait()
            if self.forwarded_signal is not None and return_code < 0:
                return 128 + self.forwarded_signal
            return return_code
        except (StartupGuardError, OSError, subprocess.SubprocessError) as exc:
            print(f"ComfyUI startup contract failed: {exc}", file=sys.stderr, flush=True)
            if self.child.poll() is None:
                os.killpg(self.child.pid, signal.SIGTERM)
                try:
                    self.child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(self.child.pid, signal.SIGKILL)
                    self.child.wait()
            return 2
        finally:
            self._remove_sentinel()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comfyui-root", type=Path, default=Path("/opt/comfyui"))
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--workflow", type=Path, default=Path("/opt/content/pulid.json"))
    parser.add_argument(
        "--extra-model-paths", type=Path, default=Path("/run/content/extra_model_paths.yaml")
    )
    parser.add_argument("--sentinel", type=Path, default=Path("/run/content/comfyui-ready.json"))
    parser.add_argument("--startup-timeout", type=float, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    work = args.workspace / "comfyui"
    command = [
        sys.executable,
        str(args.comfyui_root / "main.py"),
        "--listen", "127.0.0.1",
        "--port", "8188",
        "--disable-auto-launch",
        "--disable-api-nodes",
        "--extra-model-paths-config", str(args.extra_model_paths),
        "--input-directory", str(work / "input"),
        "--output-directory", str(work / "output"),
        "--temp-directory", str(work / "temp"),
        "--user-directory", str(work / "user"),
    ]
    os.chdir(args.comfyui_root)
    return ComfySupervisor(command, args.sentinel).run(
        backend_url="http://127.0.0.1:8188",
        workflow=args.workflow,
        startup_timeout=args.startup_timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
