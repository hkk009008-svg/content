#!/usr/bin/env python3
"""Bearer-authenticated HTTP/WebSocket gateway for loopback-only ComfyUI."""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web


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
    """The gateway cannot enforce the production exposure contract."""


def validate_token(value: str) -> str:
    token = value.strip()
    if token.lower().startswith("bearer "):
        raise GatewayConfigError("COMFYUI_API_KEY must contain only the token, without 'Bearer '")
    if len(token) < 32:
        raise GatewayConfigError("COMFYUI_API_KEY must be a random token of at least 32 characters")
    if token.lower() in {"changeme", "replace-me", "placeholder"}:
        raise GatewayConfigError("COMFYUI_API_KEY contains a placeholder")
    return token


def validate_upstream(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise GatewayConfigError("gateway upstream must be loopback HTTP")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise GatewayConfigError("gateway upstream must not contain credentials, query, or fragment")
    return value.rstrip("/")


def filtered_headers(headers: Any, *, response: bool = False) -> dict[str, str]:
    blocked = set(HOP_BY_HOP)
    blocked.update({"host", "authorization"})
    if not response:
        blocked.add("content-length")
    return {key: value for key, value in headers.items() if key.lower() not in blocked}


class AuthenticatedGateway:
    def __init__(self, *, upstream: str, token: str, sentinel: Path) -> None:
        self.upstream = validate_upstream(upstream)
        self.token = validate_token(token)
        self.sentinel = sentinel
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

    def _ready_record(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.sentinel.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("status") != "ready":
            return None
        return payload

    async def live(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "live"})

    async def ready(self, _request: web.Request) -> web.Response:
        record = self._ready_record()
        if record is None or self.session is None:
            return web.json_response({"status": "not_ready"}, status=503)
        try:
            async with self.session.get(self.upstream + "/system_stats") as response:
                if response.status != 200 or response.content_type != "application/json":
                    return web.json_response({"status": "not_ready"}, status=503)
                payload = await response.json()
        except Exception:
            return web.json_response({"status": "not_ready"}, status=503)
        if not isinstance(payload, dict) or not isinstance(payload.get("system"), dict):
            return web.json_response({"status": "not_ready"}, status=503)
        return web.json_response(
            {"status": "ready", "checked_at_unix": record.get("checked_at_unix")}
        )

    def _authorized(self, request: web.Request) -> bool:
        supplied = request.headers.get("Authorization", "")
        return hmac.compare_digest(supplied, f"Bearer {self.token}")

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

        upstream_url = self.upstream + str(request.rel_url)
        headers = filtered_headers(request.headers)
        try:
            async with self.session.request(
                request.method,
                upstream_url,
                headers=headers,
                data=request.content.iter_chunked(1024 * 1024),
                allow_redirects=False,
            ) as upstream_response:
                response = web.StreamResponse(
                    status=upstream_response.status,
                    reason=upstream_response.reason,
                    headers=filtered_headers(upstream_response.headers, response=True),
                )
                response.headers["X-Content-Gateway"] = "authenticated"
                await response.prepare(request)
                async for chunk in upstream_response.content.iter_chunked(1024 * 1024):
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

                async def downstream_to_upstream() -> None:
                    async for message in downstream:
                        if message.type == WSMsgType.TEXT:
                            await upstream.send_str(message.data)
                        elif message.type == WSMsgType.BINARY:
                            await upstream.send_bytes(message.data)
                        elif message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
                            break

                async def upstream_to_downstream() -> None:
                    async for message in upstream:
                        if message.type == WSMsgType.TEXT:
                            await downstream.send_str(message.data)
                        elif message.type == WSMsgType.BINARY:
                            await downstream.send_bytes(message.data)
                        elif message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
                            break

                tasks = {
                    asyncio.create_task(downstream_to_upstream()),
                    asyncio.create_task(upstream_to_downstream()),
                }
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
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
    app.router.add_route("*", "/{tail:.*}", gateway.proxy)
    app.on_startup.append(gateway.start)
    app.on_cleanup.append(gateway.stop)
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8189)
    parser.add_argument("--upstream", default="http://127.0.0.1:8188")
    parser.add_argument("--sentinel", type=Path, default=Path("/run/content/comfyui-ready.json"))
    args = parser.parse_args()
    token = os.environ.get("COMFYUI_API_KEY", "")
    gateway = AuthenticatedGateway(upstream=args.upstream, token=token, sentinel=args.sentinel)
    web.run_app(
        create_app(gateway),
        host=args.listen,
        port=args.port,
        handle_signals=True,
        access_log_format='%a "%r" %s %b %Tf',
    )


if __name__ == "__main__":
    main()
