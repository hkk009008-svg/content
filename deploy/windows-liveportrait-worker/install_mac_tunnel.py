#!/usr/bin/env python3
"""Install a guarded per-user launchd SSH tunnel to the Windows gateway."""

from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
import platform
import plistlib
import re
import stat
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


DEFAULT_LABEL = "com.content.liveportrait-tunnel"
WINDOWS_USER_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
LABEL_RE = re.compile(r"^[A-Za-z0-9.-]{3,128}$")
PRIVATE_IPV4_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


class TunnelInstallError(RuntimeError):
    """The tunnel cannot be installed without weakening its trust boundary."""


def _locked_file(raw: str, label: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise TunnelInstallError(f"{label} must be an absolute path")
    try:
        details = path.stat()
    except OSError as exc:
        raise TunnelInstallError(f"{label} is unavailable") from exc
    if not stat.S_ISREG(details.st_mode):
        raise TunnelInstallError(f"{label} must name a regular file")
    if details.st_mode & 0o077:
        raise TunnelInstallError(f"{label} must use mode 0600 or stricter")
    return path.resolve()


def _private_ipv4(raw: str) -> str:
    try:
        address = ipaddress.ip_address(raw)
    except ValueError as exc:
        raise TunnelInstallError("Windows host must be a concrete private IPv4 address") from exc
    # ``IPv4Address.is_private`` intentionally includes several non-routable
    # documentation/reserved ranges and has changed across Python releases.
    # The worker topology is narrower: one concrete RFC1918 LAN address.
    if address.version != 4 or not any(
        address in network for network in PRIVATE_IPV4_NETWORKS
    ):
        raise TunnelInstallError("Windows host must be a concrete private IPv4 address")
    return str(address)


def _port(value: int, label: str) -> int:
    if value < 1024 or value > 65535:
        raise TunnelInstallError(f"{label} must be an unprivileged TCP port")
    return value


def _ssh_arguments(
    *,
    windows_host: str,
    windows_user: str,
    identity_file: Path,
    known_hosts: Path,
    local_port: int,
    remote_port: int,
) -> list[str]:
    destination = f"{windows_user}@{windows_host}"
    return [
        "/usr/bin/ssh",
        # Do not inherit HostName, ProxyCommand, or extra forwarding directives
        # from a workstation's mutable ~/.ssh/config. Every authority-affecting
        # option for this one tunnel is explicit below.
        "-F",
        "/dev/null",
        "-N",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "TCPKeepAlive=yes",
        "-o",
        "GatewayPorts=no",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-i",
        str(identity_file),
        "-L",
        f"127.0.0.1:{local_port}:127.0.0.1:{remote_port}",
        destination,
    ]


def _plist_payload(
    *,
    label: str,
    arguments: list[str],
    home: Path,
    log_directory: Path,
) -> dict:
    return {
        "Label": label,
        "ProgramArguments": arguments,
        "RunAtLoad": True,
        "KeepAlive": {"NetworkState": True, "SuccessfulExit": False},
        "ProcessType": "Background",
        "ThrottleInterval": 10,
        "WorkingDirectory": str(home),
        "StandardOutPath": str(log_directory / "tunnel.stdout.log"),
        "StandardErrorPath": str(log_directory / "tunnel.stderr.log"),
    }


def _run(command: list[str], *, accepted: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if completed.returncode not in accepted:
        raise TunnelInstallError(
            f"command failed safely: {Path(command[0]).name} returned {completed.returncode}"
        )
    return completed


def _known_host_is_pinned(host: str, known_hosts: Path) -> None:
    result = _run(
        ["/usr/bin/ssh-keygen", "-F", host, "-f", str(known_hosts)],
        accepted=(0, 1),
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise TunnelInstallError(
            "Windows host key is not pinned in the declared known_hosts file"
        )


def _probe_ssh(arguments: list[str]) -> None:
    probe: list[str] = []
    skip_next = False
    for argument in arguments:
        if skip_next:
            skip_next = False
            continue
        if argument in {"-N", "-T"}:
            continue
        if argument == "-L":
            skip_next = True
            continue
        probe.append(argument)
    probe[1:1] = ["-T", "-o", "ConnectTimeout=5"]
    probe.append("exit 0")
    _run(probe)


def _launchd_pid(service: str) -> int | None:
    completed = subprocess.run(
        ["/bin/launchctl", "print", service],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode:
        return None
    match = re.search(r"(?m)^\s*pid = (\d+)\s*$", completed.stdout)
    return int(match.group(1)) if match else None


def _listening_pids(port: int) -> set[int]:
    completed = subprocess.run(
        [
            "/usr/sbin/lsof",
            "-nP",
            f"-iTCP:{port}",
            "-sTCP:LISTEN",
            "-t",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode not in {0, 1}:
        raise TunnelInstallError("could not audit the local tunnel port")
    return {
        int(line)
        for line in completed.stdout.splitlines()
        if line.strip().isdigit()
    }


def _wait_port_free(port: int, timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _listening_pids(port):
            return
        time.sleep(0.1)
    raise TunnelInstallError("the prior tunnel did not release its local port")


def _wait_ready(local_port: int, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    origin = f"http://127.0.0.1:{local_port}/health/ready"
    while time.monotonic() < deadline:
        try:
            with urlopen(origin, timeout=2) as response:
                if response.status == 200:
                    return
        except (HTTPError, URLError, TimeoutError, OSError):
            pass
        time.sleep(0.25)
    raise TunnelInstallError("supervised tunnel did not reach the worker readiness endpoint")


def _write_plist(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            plistlib.dump(payload, handle, fmt=plistlib.FMT_XML, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def install(args: argparse.Namespace) -> Path:
    if platform.system() != "Darwin":
        raise TunnelInstallError("the launchd tunnel installer must run on macOS")
    if os.geteuid() == 0:
        raise TunnelInstallError("run the tunnel installer as the intended non-root Mac user")
    if not WINDOWS_USER_RE.fullmatch(args.windows_user):
        raise TunnelInstallError("Windows user contains unsupported characters")
    if not LABEL_RE.fullmatch(args.label):
        raise TunnelInstallError("launchd label contains unsupported characters")

    host = _private_ipv4(args.windows_host)
    local_port = _port(args.local_port, "local port")
    remote_port = _port(args.remote_port, "remote port")
    identity = _locked_file(args.identity_file, "identity file")
    known_hosts = _locked_file(args.known_hosts, "known_hosts")
    _known_host_is_pinned(host, known_hosts)

    home = Path.home().resolve()
    launch_agents = home / "Library" / "LaunchAgents"
    plist_path = launch_agents / f"{args.label}.plist"
    log_directory = home / ".local" / "state" / "content" / "liveportrait-tunnel"
    log_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(log_directory, 0o700)
    arguments = _ssh_arguments(
        windows_host=host,
        windows_user=args.windows_user,
        identity_file=identity,
        known_hosts=known_hosts,
        local_port=local_port,
        remote_port=remote_port,
    )
    _probe_ssh(arguments)
    payload = _plist_payload(
        label=args.label,
        arguments=arguments,
        home=home,
        log_directory=log_directory,
    )
    if args.dry_run:
        return plist_path

    previous = plist_path.read_bytes() if plist_path.exists() else None
    service = f"gui/{os.getuid()}/{args.label}"
    domain = f"gui/{os.getuid()}"
    existing_pid = _launchd_pid(service)
    listeners = _listening_pids(local_port)
    if listeners and (existing_pid is None or listeners != {existing_pid}):
        raise TunnelInstallError(
            "local tunnel port is owned by a process outside the declared launchd service"
        )
    _run(["/bin/launchctl", "bootout", service], accepted=(0, 3, 5, 113))
    _wait_port_free(local_port)
    try:
        _write_plist(plist_path, payload)
        _run(["/bin/launchctl", "bootstrap", domain, str(plist_path)])
        _run(["/bin/launchctl", "enable", service])
        _run(["/bin/launchctl", "kickstart", "-k", service])
        _wait_ready(local_port, args.health_timeout)
    except Exception:
        _run(["/bin/launchctl", "bootout", service], accepted=(0, 3, 5, 113))
        if previous is None:
            plist_path.unlink(missing_ok=True)
        else:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{plist_path.name}.", suffix=".rollback", dir=launch_agents
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(previous)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, plist_path)
            finally:
                temporary.unlink(missing_ok=True)
            _run(
                ["/bin/launchctl", "bootstrap", domain, str(plist_path)],
                accepted=(0, 5),
            )
        raise
    return plist_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows-host", required=True)
    parser.add_argument("--windows-user", required=True)
    parser.add_argument("--identity-file", required=True)
    parser.add_argument("--known-hosts", default=str(Path.home() / ".ssh" / "known_hosts"))
    parser.add_argument("--local-port", type=int, default=18189)
    parser.add_argument("--remote-port", type=int, default=8189)
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument("--health-timeout", type=float, default=20.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        path = install(args)
    except (OSError, subprocess.SubprocessError, TunnelInstallError) as exc:
        print(f"TUNNEL INSTALL REFUSED: {exc}", file=__import__("sys").stderr)
        return 1
    print(f"TUNNEL_INSTALL_OK path={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
