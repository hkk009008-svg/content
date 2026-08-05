#!/usr/bin/env python3
"""Bearer-authenticated proxy for a loopback-only ComfyUI worker."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
WORKER_ROLE = "performance-liveportrait"
CAPABILITY_SCHEMA_VERSION = 1
IMAGE_CAPABILITY = "image-flux2-klein"
IMAGE_BLOCKER_CODE = "candidate_artifacts_not_installed"
# Exact reviewed source-package identity. These values intentionally remain
# static until a reviewed candidate update changes both the application-side
# validator and this gateway contract.
FLUX2_PACKAGE_FIELDS = {
    "capability": IMAGE_CAPABILITY,
    "candidate_manifest_sha256": "43c505f8776ad4d9e6f6bab281db24f8763b9f6d0a9076efd0f1d2c05ee7944b",
    "workflow_sha256": "36f678709f6af1267208391145666a1dd62ef2a8292309231f7ffacf2b10821d",
    "model_manifest_sha256": "f35145f0fdc8d35a810b6905ccfc9358baa18d86c3abdfac23b373fd7e95018f",
    "revisions_manifest_sha256": "a2dd0f168cd711985bb041beb1ad6fa2ee0fe6536bb216805700fe573dd5e12f",
    "contract_digest": "303732a6cf772342a1451a4e7a845128b25fa044d4850224cc58c7c381d6f069",
}
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class GatewayConfigError(ValueError):
    """The gateway cannot enforce the worker exposure contract."""


def validate_token(value: str) -> str:
    token = value.strip()
    if token.lower().startswith("bearer "):
        raise GatewayConfigError("COMFYUI_API_KEY must be the token only")
    if len(token) < 32:
        raise GatewayConfigError("COMFYUI_API_KEY must contain at least 32 characters")
    if token.lower() in {"changeme", "replace-me", "placeholder"}:
        raise GatewayConfigError("COMFYUI_API_KEY contains a placeholder")
    return token


def validate_upstream(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS:
        raise GatewayConfigError("gateway upstream must be loopback HTTP")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise GatewayConfigError("gateway upstream contains forbidden URL data")
    return value.rstrip("/")


def validate_listen(value: str) -> str:
    if value not in {"127.0.0.1", "::1"}:
        raise GatewayConfigError("gateway listener must be loopback-only")
    return value


def filtered_headers(headers: Any, *, response: bool = False) -> dict[str, str]:
    blocked = set(HOP_BY_HOP) | {"host", "authorization"}
    if not response:
        blocked.add("content-length")
    return {key: value for key, value in headers.items() if key.lower() not in blocked}


class AuthenticatedGateway:
    def __init__(
        self,
        *,
        upstream: str,
        token: str,
        sentinel: Path,
        revisions: Path,
        models: Path,
        probe_contract: Path,
        flux2_state_root: Path | None = None,
    ) -> None:
        self.upstream = validate_upstream(upstream)
        self.token = validate_token(token)
        self.sentinel = sentinel
        self.revisions = revisions
        self.models = models
        self.probe_contract = probe_contract
        self.flux2_state_root = flux2_state_root.resolve() if flux2_state_root else None
        self.session: ClientSession | None = None

    async def start(self, _app: web.Application) -> None:
        self.session = ClientSession(
            timeout=ClientTimeout(total=None, sock_connect=10, sock_read=None),
            auto_decompress=False,
            trust_env=False,
        )

    async def stop(self, _app: web.Application) -> None:
        if self.session is not None:
            await self.session.close()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _expected_contract(self) -> dict[str, str] | None:
        try:
            probe = json.loads(self.probe_contract.read_text(encoding="utf-8"))
            workflow_value = probe.get("workflow") if isinstance(probe, dict) else None
            if not isinstance(workflow_value, str) or Path(workflow_value).is_absolute():
                return None
            probe_root = self.probe_contract.parent.resolve()
            workflow = (probe_root / workflow_value).resolve()
            if probe_root not in workflow.parents:
                return None
            workflow_hash = self._sha256(workflow)
            if probe.get("workflow_sha256") != workflow_hash:
                return None
            contract = {
                "model_manifest_sha256": self._sha256(self.models),
                "revisions_manifest_sha256": self._sha256(self.revisions),
                "role": WORKER_ROLE,
                "workflow_sha256": workflow_hash,
            }
        except (OSError, json.JSONDecodeError):
            return None
        contract["contract_digest"] = hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return contract

    def _ready_record(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.sentinel.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (
            not isinstance(payload, dict)
            or payload.get("status") != "ready"
            or payload.get("role") != WORKER_ROLE
            or payload.get("startup_ready") is not True
            or payload.get("execution_proven") is not True
        ):
            return None
        canary = payload.get("execution_canary")
        if not isinstance(canary, dict) or canary.get("state") != "passed":
            return None
        expected = self._expected_contract()
        if expected is None or any(payload.get(key) != value for key, value in expected.items()):
            return None
        return payload

    def _flux2_evidence_sha256(
        self,
        root: Path,
        record: object,
        *,
        expected_status: str,
    ) -> tuple[str, dict[str, Any]]:
        if not isinstance(record, dict):
            raise ValueError("missing evidence record")
        relative = record.get("path")
        expected_hash = record.get("sha256")
        run_id = record.get("run_id")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or not isinstance(expected_hash, str)
            or len(expected_hash) != 64
            or not isinstance(run_id, str)
            or not run_id
            or record.get("status") != expected_status
        ):
            raise ValueError("invalid evidence record")
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file() or path.is_symlink():
            raise ValueError("unsafe evidence path")
        actual = self._sha256(path)
        if not hmac.compare_digest(actual, expected_hash):
            raise ValueError("evidence hash mismatch")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("capability") != IMAGE_CAPABILITY
            or payload.get("status") != expected_status
            or str(payload.get("run_id") or payload.get("benchmark_id") or "")
            != run_id
        ):
            raise ValueError("evidence payload mismatch")
        if expected_status == "fixed_probe_passed":
            output = payload.get("output")
            if (
                record.get("workflow_sha256") != payload.get("workflow_sha256")
                or not isinstance(output, dict)
                or record.get("output_sha256") != output.get("sha256")
            ):
                raise ValueError("canary evidence summary mismatch")
        return actual, payload

    def _flux2_status_record(self) -> dict[str, Any]:
        """Rehash private durable evidence and return only its safe projection."""

        base = {
            **FLUX2_PACKAGE_FIELDS,
            "state": "not_installed",
            "startup_ready": False,
            "execution_proven": False,
            "benchmark_state": "not_run",
            "blocker_code": IMAGE_BLOCKER_CODE,
            "artifacts_installed": False,
            "runtime_contract_sha256": "",
            "license_review_state": "official_sources_selected_derivation_pending",
            "execution_canary_state": "not_run",
            "execution_canary_sha256": "",
            "benchmark_sha256": "",
        }
        if self.flux2_state_root is None:
            return base
        root = self.flux2_state_root
        status_path = root / "status.json"
        if not status_path.is_file() or status_path.is_symlink():
            return base
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if (
                not isinstance(status, dict)
                or status.get("schema_version") != 1
                or status.get("capability") != IMAGE_CAPABILITY
                or status.get("artifact_manifest_sha256")
                != FLUX2_PACKAGE_FIELDS["model_manifest_sha256"]
                or status.get("workflow_contract_sha256")
                != FLUX2_PACKAGE_FIELDS["workflow_sha256"]
                or not isinstance(status.get("updated_at"), str)
            ):
                raise ValueError("status contract mismatch")
            state = status.get("state")
            if state not in {"not_installed", "needs_benchmark", "ready"}:
                raise ValueError("invalid state")
            runtime_hash = status.get("runtime_contract_sha256")
            if runtime_hash is None:
                runtime_hash = ""
            if not isinstance(runtime_hash, str) or (
                runtime_hash and len(runtime_hash) != 64
            ):
                raise ValueError("invalid runtime contract")
            evidence = status.get("evidence")
            if not isinstance(evidence, dict):
                raise ValueError("missing evidence map")
            install_hash, _install_payload = self._flux2_evidence_sha256(
                root,
                evidence.get("install"),
                expected_status="installed_needs_execution_probe",
            )
            del install_hash  # verified but intentionally not browser-visible
            canary_hash = ""
            benchmark_hash = ""
            canary_state = "not_run"
            if state in {"needs_benchmark", "ready"}:
                canary_hash, canary_payload = self._flux2_evidence_sha256(
                    root,
                    evidence.get("canary"),
                    expected_status="fixed_probe_passed",
                )
                if canary_payload.get("runtime_contract_sha256") != runtime_hash:
                    raise ValueError("canary runtime binding mismatch")
                canary_state = "passed"
            elif evidence.get("canary") is not None:
                raise ValueError("premature canary evidence")
            if state == "ready":
                benchmark_hash, benchmark_payload = self._flux2_evidence_sha256(
                    root,
                    evidence.get("benchmark"),
                    expected_status="benchmark_passed",
                )
                if (
                    benchmark_payload.get("runtime_contract_sha256") != runtime_hash
                    or benchmark_payload.get("probe_evidence_sha256") != canary_hash
                    or benchmark_payload.get("sequence") != [1, 2, 10]
                    or benchmark_payload.get("benchmark_state") != "passed"
                ):
                    raise ValueError("benchmark evidence binding mismatch")
            elif evidence.get("benchmark") is not None:
                raise ValueError("premature benchmark evidence")

            expected = {
                "not_installed": {
                    "startup_ready": False,
                    "execution_proven": False,
                    "benchmark_state": "not_run",
                    "blocker_code": "candidate_execution_probe_not_run",
                },
                "needs_benchmark": {
                    "startup_ready": False,
                    "execution_proven": True,
                    "benchmark_state": "not_run",
                    "blocker_code": "candidate_benchmark_not_run",
                },
                "ready": {
                    "startup_ready": True,
                    "execution_proven": True,
                    "benchmark_state": "passed",
                    "blocker_code": None,
                },
            }[state]
            if any(status.get(key) != value for key, value in expected.items()):
                raise ValueError("state transition tuple mismatch")
            if (
                status.get("artifacts_installed") is not True
                or status.get("license_review_state")
                != "official_source_derivation_verified"
                or (
                    state == "not_installed" and runtime_hash != ""
                )
                or (
                    state in {"needs_benchmark", "ready"}
                    and len(runtime_hash) != 64
                )
            ):
                raise ValueError("installed evidence is incomplete")
            return {
                **FLUX2_PACKAGE_FIELDS,
                "state": state,
                "startup_ready": expected["startup_ready"],
                "execution_proven": expected["execution_proven"],
                "benchmark_state": expected["benchmark_state"],
                "blocker_code": expected["blocker_code"] or "",
                "artifacts_installed": True,
                "runtime_contract_sha256": runtime_hash,
                "license_review_state": "official_source_derivation_verified",
                "execution_canary_state": canary_state,
                "execution_canary_sha256": canary_hash,
                "benchmark_sha256": benchmark_hash,
            }
        except (OSError, json.JSONDecodeError, ValueError):
            return {
                **base,
                "state": "blocked",
                "benchmark_state": "unknown",
                "blocker_code": "candidate_status_evidence_invalid",
                "license_review_state": "review_required",
                "execution_canary_state": "unknown",
            }

    async def live(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "live", "role": WORKER_ROLE})

    async def ready(self, _request: web.Request) -> web.Response:
        record = self._ready_record()
        if record is None or self.session is None:
            return web.json_response(
                {
                    "status": "not_ready",
                    "role": WORKER_ROLE,
                    "startup_ready": False,
                    "execution_proven": False,
                },
                status=503,
            )
        try:
            async with self.session.get(self.upstream + "/system_stats") as response:
                payload = await response.json() if response.status == 200 else None
        except Exception:
            payload = None
        if not isinstance(payload, dict) or not isinstance(payload.get("system"), dict):
            return web.json_response(
                {
                    "status": "not_ready",
                    "role": WORKER_ROLE,
                    "startup_ready": False,
                    "execution_proven": False,
                },
                status=503,
            )
        return web.json_response(
            {
                "status": "ready",
                "role": WORKER_ROLE,
                "startup_ready": True,
                "execution_proven": True,
                "checked_at_unix": record.get("checked_at_unix"),
                "workflow_sha256": record.get("workflow_sha256"),
                "model_manifest_sha256": record.get("model_manifest_sha256"),
                "revisions_manifest_sha256": record.get("revisions_manifest_sha256"),
                "contract_digest": record.get("contract_digest"),
                "execution_canary_state": "passed",
            }
        )

    def _capability_record(self) -> dict[str, Any] | None:
        """Return the exact offline unified-worker contract.

        The accepted installation proves only LivePortrait execution. FLUX.2
        Klein is a separately hash-bound candidate and remains not installed;
        node reachability must never upgrade that state. This record is
        exposed only by the authenticated route. No retired image capability
        can be inferred from the performance worker's node inventory.
        """

        record = self._ready_record()
        if record is None:
            return None
        performance = {
            "role": WORKER_ROLE,
            "status": "ready",
            "startup_ready": True,
            "execution_proven": True,
            "execution_canary_state": "passed",
            "workflow_sha256": record.get("workflow_sha256"),
            "model_manifest_sha256": record.get("model_manifest_sha256"),
            "revisions_manifest_sha256": record.get("revisions_manifest_sha256"),
            "contract_digest": record.get("contract_digest"),
        }
        image = self._flux2_status_record()
        return {
            "schema_version": CAPABILITY_SCHEMA_VERSION,
            "status": "ready" if image.get("state") == "ready" else "partial",
            "capabilities": {
                WORKER_ROLE: performance,
                IMAGE_CAPABILITY: image,
            },
        }

    async def capabilities_ready(self, _request: web.Request) -> web.Response:
        """Return capability-bound readiness after bearer authentication."""

        payload = self._capability_record()
        if payload is None or self.session is None:
            return web.json_response(
                {
                    "schema_version": CAPABILITY_SCHEMA_VERSION,
                    "status": "not_ready",
                },
                status=503,
            )
        try:
            async with self.session.get(self.upstream + "/system_stats") as response:
                stats = await response.json() if response.status == 200 else None
        except Exception:
            stats = None
        if not isinstance(stats, dict) or not isinstance(stats.get("system"), dict):
            return web.json_response(
                {
                    "schema_version": CAPABILITY_SCHEMA_VERSION,
                    "status": "not_ready",
                },
                status=503,
            )
        return web.json_response(payload)

    def _authorized(self, request: web.Request) -> bool:
        return hmac.compare_digest(
            request.headers.get("Authorization", ""), f"Bearer {self.token}"
        )

    @web.middleware
    async def access_control(
        self, request: web.Request, handler: Any
    ) -> web.StreamResponse:
        if request.path in {"/health/live", "/health/ready"}:
            return await handler(request)
        if self._ready_record() is None:
            return web.json_response({"error": "backend_not_ready"}, status=503)
        if not self._authorized(request):
            return web.json_response(
                {"error": "unauthorized"},
                status=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await handler(request)

    async def proxy(self, request: web.Request) -> web.StreamResponse:
        if self.session is None:
            return web.json_response({"error": "gateway_not_ready"}, status=503)
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await self._proxy_websocket(request)
        try:
            async with self.session.request(
                request.method,
                self.upstream + str(request.rel_url),
                headers=filtered_headers(request.headers),
                data=request.content.iter_chunked(1024 * 1024),
                allow_redirects=False,
            ) as upstream:
                response = web.StreamResponse(
                    status=upstream.status,
                    reason=upstream.reason,
                    headers=filtered_headers(upstream.headers, response=True),
                )
                response.headers["X-Content-Gateway"] = "authenticated"
                await response.prepare(request)
                async for chunk in upstream.content.iter_chunked(1024 * 1024):
                    await response.write(chunk)
                await response.write_eof()
                return response
        except asyncio.CancelledError:
            raise
        except Exception:
            return web.json_response({"error": "upstream_unavailable"}, status=502)

    async def _proxy_websocket(self, request: web.Request) -> web.WebSocketResponse:
        assert self.session is not None
        downstream = web.WebSocketResponse(heartbeat=30, max_msg_size=0)
        await downstream.prepare(request)
        upstream_url = self.upstream.replace("http://", "ws://", 1) + str(request.rel_url)
        try:
            async with self.session.ws_connect(
                upstream_url,
                headers=filtered_headers(request.headers),
                heartbeat=30,
                max_msg_size=0,
            ) as upstream:

                async def copy(source: Any, target: Any) -> None:
                    async for message in source:
                        if message.type == WSMsgType.TEXT:
                            await target.send_str(message.data)
                        elif message.type == WSMsgType.BINARY:
                            await target.send_bytes(message.data)
                        elif message.type in {
                            WSMsgType.CLOSE,
                            WSMsgType.CLOSED,
                            WSMsgType.ERROR,
                        }:
                            break

                tasks = {
                    asyncio.create_task(copy(downstream, upstream)),
                    asyncio.create_task(copy(upstream, downstream)),
                }
                done, pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*done, *pending, return_exceptions=True)
        finally:
            await downstream.close()
        return downstream


def create_app(gateway: AuthenticatedGateway) -> web.Application:
    app = web.Application(middlewares=[gateway.access_control], client_max_size=1024**3)
    app.router.add_get("/health/live", gateway.live)
    app.router.add_get("/health/ready", gateway.ready)
    app.router.add_get("/api/capabilities/ready", gateway.capabilities_ready)
    app.router.add_route("*", "/{tail:.*}", gateway.proxy)
    app.on_startup.append(gateway.start)
    app.on_cleanup.append(gateway.stop)
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8189)
    parser.add_argument("--upstream", default="http://127.0.0.1:8188")
    parser.add_argument("--sentinel", type=Path, required=True)
    parser.add_argument("--revisions", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--probe-contract", type=Path, required=True)
    parser.add_argument("--flux2-state-root", type=Path)
    args = parser.parse_args()
    gateway = AuthenticatedGateway(
        upstream=args.upstream,
        token=os.environ.get("COMFYUI_API_KEY", ""),
        sentinel=args.sentinel,
        revisions=args.revisions,
        models=args.models,
        probe_contract=args.probe_contract,
        flux2_state_root=args.flux2_state_root,
    )
    web.run_app(
        create_app(gateway),
        host=validate_listen(args.listen),
        port=args.port,
        handle_signals=True,
        access_log_format='%a "%r" %s %b %Tf',
    )


if __name__ == "__main__":
    main()
