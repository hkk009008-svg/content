"""Bounded ComfyUI HTTP/WebSocket client used by image generation.

The historical ``RunPodComfyUI`` name is retained because callers and project
documentation use it, but the transport is host-agnostic.  The client keeps
all network calls bounded, reuses urllib3 connection pools, validates a graph
against the live ComfyUI contract before submission, and never automatically
retries ``POST /prompt`` (an acknowledgement may have been lost after ComfyUI
accepted the job).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any, Optional
from urllib.parse import quote, urlsplit, urlunsplit

import requests
from PIL import Image, UnidentifiedImageError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:  # Optional at import time; REST history polling remains available.
    from websockets.sync.client import connect as _websocket_connect
except ImportError:  # pragma: no cover - exercised only in minimal installs
    _websocket_connect = None


DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 30.0
DEFAULT_UPLOAD_READ_TIMEOUT = 120.0
DEFAULT_DOWNLOAD_READ_TIMEOUT = 120.0
DEFAULT_JOB_TIMEOUT = 600.0
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_MAX_IMAGE_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_IMAGE_PIXELS = 64 * 1024 * 1024
MAX_JSON_BYTES = 32 * 1024 * 1024
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_SAFE_RETRY_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_TERMINAL_ERROR_EVENTS = frozenset({"execution_error", "execution_interrupted"})
_IMAGE_CONTENT_TYPES = {
    "image/jpeg": "JPEG",
    "image/jpg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
_DESTINATION_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}


class ComfyUIError(RuntimeError):
    """Base error for a bounded ComfyUI operation."""


class ComfyUITransportError(ComfyUIError):
    """The server could not be reached or returned an invalid transport response."""


class ComfyUIReadinessError(ComfyUIError):
    """The live pod contract cannot execute the requested workflow."""


class ComfyUIPromptRejected(ComfyUIError):
    """ComfyUI rejected a prompt before queue acknowledgement."""

    def __init__(self, message: str, *, error: Any = None, node_errors: Any = None):
        super().__init__(message)
        self.error = error
        self.node_errors = node_errors


class ComfyUISubmitUnknown(ComfyUIError):
    """Prompt submission may have been accepted but no acknowledgement arrived."""


class ComfyUIJobError(ComfyUIError):
    """A queued prompt reached a terminal error or interruption."""


class ComfyUIJobStateUnknown(ComfyUIError):
    """A known prompt may still be running or have an unrecovered output."""


class ComfyUITimeout(ComfyUIError):
    """A queued prompt exceeded its deadline and cancellation was confirmed."""


def _build_shared_adapter() -> HTTPAdapter:
    # Only idempotent reads are retried by urllib3.  In particular, POST
    # /prompt, /upload/image, /interrupt, and /queue are each sent at most once.
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        allowed_methods=_SAFE_RETRY_METHODS,
        status_forcelist=_RETRYABLE_STATUS,
        backoff_factor=0.25,
        backoff_max=2.0,
        # A proxy-controlled Retry-After must not turn a bounded API call into
        # an unbounded sleep. The short capped exponential delay still retries
        # 429 responses without trusting arbitrary wait durations.
        respect_retry_after_header=False,
        raise_on_status=False,
    )
    return HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=retry)


_SHARED_ADAPTER = _build_shared_adapter()


def _new_session() -> requests.Session:
    session = requests.Session()
    session.mount("http://", _SHARED_ADAPTER)
    session.mount("https://", _SHARED_ADAPTER)
    return session


def _short_json(value: Any, limit: int = 2000) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        rendered = repr(value)
    return rendered if len(rendered) <= limit else rendered[:limit] + "..."


def _response_payload(response: requests.Response) -> Any:
    advertised = response.headers.get("content-length")
    if advertised:
        try:
            advertised_size = int(advertised)
            if advertised_size < 0 or advertised_size > MAX_JSON_BYTES:
                raise ComfyUITransportError(
                    f"ComfyUI JSON response exceeds {MAX_JSON_BYTES} bytes"
                )
        except ValueError as exc:
            raise ComfyUITransportError(
                f"ComfyUI sent invalid content-length {advertised!r}"
            ) from exc
    chunks: list[bytes] = []
    received = 0
    try:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            received += len(chunk)
            if received > MAX_JSON_BYTES:
                raise ComfyUITransportError(
                    f"ComfyUI JSON response exceeds {MAX_JSON_BYTES} bytes"
                )
            chunks.append(chunk)
    except requests.RequestException as exc:
        raise ComfyUITransportError(
            f"ComfyUI JSON response stream failed: {exc}"
        ) from exc
    content = b"".join(chunks)
    try:
        return json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        preview = content[:200].decode("utf-8", errors="replace").replace("\n", " ")
        raise ComfyUITransportError(
            f"ComfyUI returned non-JSON HTTP {response.status_code}: {preview!r}"
        ) from exc


def _prompt_rejection(payload: Any, status_code: int) -> Optional[ComfyUIPromptRejected]:
    if not isinstance(payload, Mapping):
        return None
    error = payload.get("error")
    node_errors = payload.get("node_errors")
    if not error and not node_errors:
        return None
    detail = _short_json({"error": error, "node_errors": node_errors})
    return ComfyUIPromptRejected(
        f"ComfyUI rejected prompt (HTTP {status_code}): {detail}",
        error=error,
        node_errors=node_errors,
    )


def _queue_item_prompt_id(item: Any) -> Optional[str]:
    if isinstance(item, (list, tuple)) and len(item) > 1 and item[1] is not None:
        return str(item[1])
    if isinstance(item, Mapping):
        value = item.get("prompt_id") or item.get("id")
        return str(value) if value is not None else None
    return None


class RunPodComfyUI:
    """Production-safe client for the standard ComfyUI server API."""

    def __init__(
        self,
        server_url: str,
        *,
        auth_token: str = "",
        session: Optional[requests.Session] = None,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
    ):
        if not isinstance(server_url, str) or not server_url.strip():
            raise ValueError("server_url must be a non-empty string")
        parsed_url = urlsplit(server_url.strip())
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("server_url must be an absolute http(s) URL")
        if parsed_url.query or parsed_url.fragment:
            raise ValueError("server_url cannot contain a query string or fragment")
        self.server_url = server_url.strip().rstrip("/")
        self.client_id = str(uuid.uuid4())
        self.connect_timeout = float(connect_timeout)
        self.read_timeout = float(read_timeout)
        if self.connect_timeout <= 0 or self.read_timeout <= 0:
            raise ValueError("ComfyUI timeouts must be positive")
        self.session = session or _new_session()
        self._websocket_headers: dict[str, str] = {}
        token = auth_token.strip()
        if token:
            if token.lower().startswith("bearer "):
                authorization = token
            else:
                authorization = f"Bearer {token}"
            self.session.headers.update({"Authorization": authorization})
        authorization = self.session.headers.get("Authorization")
        if authorization:
            # Don't forward requests' HTTP defaults (especially
            # ``Connection: keep-alive``) into the WebSocket upgrade.
            self._websocket_headers["Authorization"] = authorization

    @property
    def timeout(self) -> tuple[float, float]:
        return (self.connect_timeout, self.read_timeout)

    def _url(self, path: str) -> str:
        return f"{self.server_url}/{path.lstrip('/')}"

    def _get_json(self, path: str) -> Any:
        try:
            response_context = self.session.get(
                self._url(path), timeout=self.timeout, stream=True
            )
        except requests.RequestException as exc:
            raise ComfyUITransportError(f"GET {path} failed: {exc}") from exc
        with response_context as response:
            payload = _response_payload(response)
            if response.status_code >= 400:
                raise ComfyUITransportError(
                    f"GET {path} returned HTTP {response.status_code}: {_short_json(payload)}"
                )
            return payload

    def get_object_info(self) -> dict[str, Any]:
        payload = self._get_json("/object_info")
        if not isinstance(payload, dict):
            raise ComfyUIReadinessError("/object_info must return a JSON object")
        return payload

    def get_models(self) -> list[str]:
        payload = self._get_json("/models")
        if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
            raise ComfyUIReadinessError("/models must return a JSON string list")
        return payload

    def get_queue(self) -> dict[str, Any]:
        payload = self._get_json("/queue")
        if not isinstance(payload, dict):
            raise ComfyUIReadinessError("/queue must return a JSON object")
        for key in ("queue_running", "queue_pending"):
            if not isinstance(payload.get(key), list):
                raise ComfyUIReadinessError(f"/queue missing list field {key!r}")
        return payload

    @staticmethod
    def _validate_workflow_contract(
        workflow: Mapping[str, Any], object_info: Mapping[str, Any]
    ) -> None:
        errors: list[str] = []
        if not workflow:
            raise ComfyUIReadinessError("workflow is empty")

        for raw_node_id, raw_node in workflow.items():
            node_id = str(raw_node_id)
            if not isinstance(raw_node, Mapping):
                errors.append(f"node {node_id}: definition is not an object")
                continue
            class_type = raw_node.get("class_type")
            if not isinstance(class_type, str) or not class_type:
                errors.append(f"node {node_id}: class_type is missing")
                continue
            class_contract = object_info.get(class_type)
            if not isinstance(class_contract, Mapping):
                errors.append(f"node {node_id}: class {class_type!r} is unavailable")
                continue

            actual_inputs = raw_node.get("inputs", {})
            if not isinstance(actual_inputs, Mapping):
                errors.append(f"node {node_id}: inputs is not an object")
                continue
            input_contract = class_contract.get("input", {})
            if not isinstance(input_contract, Mapping):
                input_contract = {}
            required = input_contract.get("required", {})
            optional = input_contract.get("optional", {})
            required = required if isinstance(required, Mapping) else {}
            optional = optional if isinstance(optional, Mapping) else {}
            allowed = set(required) | set(optional)

            missing = sorted(set(required) - set(actual_inputs))
            unknown = sorted(set(actual_inputs) - allowed)
            if missing:
                errors.append(f"node {node_id} ({class_type}): missing inputs {missing}")
            if unknown:
                errors.append(f"node {node_id} ({class_type}): unknown inputs {unknown}")

            for name, value in actual_inputs.items():
                spec = required.get(name, optional.get(name))
                if not isinstance(spec, (list, tuple)) or not spec:
                    continue
                choices = spec[0]
                is_link = (
                    isinstance(value, (list, tuple))
                    and len(value) == 2
                    and isinstance(value[0], str)
                    and isinstance(value[1], int)
                )
                if (
                    isinstance(choices, (list, tuple))
                    and choices
                    and not is_link
                    and value not in choices
                ):
                    errors.append(
                        f"node {node_id} ({class_type}): {name}={value!r} "
                        f"is not installed/allowed"
                    )

        if errors:
            detail = "; ".join(errors[:20])
            if len(errors) > 20:
                detail += f"; ... {len(errors) - 20} more"
            raise ComfyUIReadinessError(f"ComfyUI workflow preflight failed: {detail}")

    def preflight(self, workflow: Mapping[str, Any]) -> dict[str, Any]:
        """Verify API readiness and graph/node/model compatibility before spend."""
        object_info = self.get_object_info()
        model_folders = self.get_models()
        queue = self.get_queue()
        self._validate_workflow_contract(workflow, object_info)
        return {
            "node_class_count": len(object_info),
            "model_folders": tuple(model_folders),
            "running": len(queue["queue_running"]),
            "pending": len(queue["queue_pending"]),
        }

    def upload_image(self, image_path: str) -> str:
        print(
            f"      ↳ Uploading {os.path.basename(image_path)} "
            "to ComfyUI ephemeral disk..."
        )
        url = self._url("/upload/image")
        try:
            with open(image_path, "rb") as source:
                response = self.session.post(
                    url,
                    files={"image": source},
                    timeout=(self.connect_timeout, DEFAULT_UPLOAD_READ_TIMEOUT),
                    stream=True,
                )
        except (OSError, requests.RequestException) as exc:
            raise ComfyUITransportError(f"ComfyUI image upload failed: {exc}") from exc
        with response:
            payload = _response_payload(response)
            if response.status_code >= 400:
                raise ComfyUITransportError(
                    f"ComfyUI image upload returned HTTP {response.status_code}: "
                    f"{_short_json(payload)}"
                )
            if not isinstance(payload, Mapping) or not isinstance(payload.get("name"), str):
                raise ComfyUITransportError("ComfyUI image upload response has no filename")
            return payload["name"]

    def queue_prompt(self, prompt_workflow: Mapping[str, Any]) -> str:
        self.preflight(prompt_workflow)
        payload = {"prompt": prompt_workflow, "client_id": self.client_id}
        try:
            # Intentionally one attempt.  A timeout/reset after sending the body
            # cannot prove whether ComfyUI accepted the prompt.
            response = self.session.post(
                self._url("/prompt"),
                json=payload,
                timeout=self.timeout,
                stream=True,
            )
        except requests.RequestException as exc:
            raise ComfyUISubmitUnknown(
                "ComfyUI prompt acknowledgement was not received; submission state is UNKNOWN"
            ) from exc
        with response:
            try:
                body = _response_payload(response)
            except ComfyUITransportError as exc:
                raise ComfyUISubmitUnknown(
                    "ComfyUI returned a malformed prompt acknowledgement; "
                    "submission state is UNKNOWN"
                ) from exc
            if response.status_code in {408, 425, 429} or response.status_code >= 500:
                raise ComfyUISubmitUnknown(
                    f"ComfyUI prompt returned HTTP {response.status_code}; "
                    "submission state is UNKNOWN"
                )
            rejection = _prompt_rejection(body, response.status_code)
            if rejection is not None:
                raise rejection
            if response.status_code >= 400:
                raise ComfyUIPromptRejected(
                    f"ComfyUI prompt returned HTTP {response.status_code}: {_short_json(body)}"
                )
            if (
                not isinstance(body, Mapping)
                or not isinstance(body.get("prompt_id"), str)
                or not body["prompt_id"]
            ):
                raise ComfyUISubmitUnknown(
                    "ComfyUI prompt response has no prompt_id; submission state is UNKNOWN"
                )
            return body["prompt_id"]

    def get_history(self, prompt_id: str) -> dict[str, Any]:
        payload = self._get_json(f"/history/{quote(prompt_id, safe='')}")
        if not isinstance(payload, dict):
            raise ComfyUITransportError("ComfyUI history response must be a JSON object")
        return payload

    @staticmethod
    def _history_terminal(
        history: Mapping[str, Any], prompt_id: str
    ) -> Optional[dict[str, Any]]:
        record = history.get(prompt_id)
        if not isinstance(record, Mapping):
            return None
        status = record.get("status")
        if isinstance(status, Mapping):
            messages = status.get("messages")
            if isinstance(messages, list):
                for message in messages:
                    if not isinstance(message, (list, tuple)) or len(message) != 2:
                        continue
                    event_type, data = message
                    if event_type in _TERMINAL_ERROR_EVENTS:
                        raise ComfyUIJobError(
                            f"ComfyUI job {prompt_id} failed: {_short_json(data)}"
                        )
            if status.get("status_str") in {"error", "failed"}:
                raise ComfyUIJobError(
                    f"ComfyUI job {prompt_id} failed: {_short_json(status)}"
                )
            if status.get("completed") is True:
                return dict(record)
        outputs = record.get("outputs")
        if isinstance(outputs, Mapping) and outputs:
            return dict(record)
        return None

    def _websocket_url(self) -> str:
        parsed = urlsplit(self.server_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        path = parsed.path.rstrip("/") + "/ws"
        query = f"clientId={quote(self.client_id, safe='')}"
        return urlunsplit((scheme, parsed.netloc, path, query, ""))

    def _wait_websocket(
        self,
        prompt_id: str,
        *,
        deadline: float,
        on_progress: Optional[Callable[[dict[str, Any]], None]],
    ) -> Optional[dict[str, Any]]:
        if _websocket_connect is None:
            return None
        headers = dict(self._websocket_headers)
        try:
            with _websocket_connect(
                self._websocket_url(),
                additional_headers=headers or None,
                open_timeout=min(self.connect_timeout, max(0.1, deadline - time.monotonic())),
                close_timeout=self.connect_timeout,
                ping_interval=20,
                ping_timeout=self.connect_timeout,
                max_size=2 * 1024 * 1024,
            ) as websocket:
                while time.monotonic() < deadline:
                    remaining = deadline - time.monotonic()
                    try:
                        message = websocket.recv(timeout=min(10.0, remaining))
                    except TimeoutError:
                        history = self.get_history(prompt_id)
                        terminal = self._history_terminal(history, prompt_id)
                        if terminal is not None:
                            return history
                        continue
                    if not isinstance(message, str):
                        continue  # binary preview frame
                    try:
                        event = json.loads(message)
                    except (TypeError, ValueError):
                        continue
                    if not isinstance(event, dict):
                        continue
                    event_type = event.get("type")
                    data = event.get("data")
                    if not isinstance(data, dict):
                        data = {}
                    event_prompt_id = data.get("prompt_id")
                    if event_prompt_id is not None and str(event_prompt_id) != prompt_id:
                        continue
                    if event_type in _TERMINAL_ERROR_EVENTS:
                        raise ComfyUIJobError(
                            f"ComfyUI job {prompt_id} failed: {_short_json(data)}"
                        )
                    if event_type == "progress" and on_progress is not None:
                        on_progress(data)
                    completed_event = event_type == "execution_success" or (
                        event_type == "executing" and data.get("node") is None
                    )
                    if completed_event:
                        history = self.get_history(prompt_id)
                        terminal = self._history_terminal(history, prompt_id)
                        if terminal is not None:
                            return history
        except ComfyUIJobError:
            raise
        except Exception as exc:
            print(f"      ↳ ComfyUI WebSocket unavailable ({exc}); using history polling")
        return None

    def wait_for_completion(
        self,
        prompt_id: str,
        *,
        timeout: float = DEFAULT_JOB_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> dict[str, Any]:
        """Wait for a prompt using WebSocket events with bounded REST fallback."""
        if timeout <= 0 or poll_interval <= 0:
            raise ValueError("job timeout and poll interval must be positive")
        deadline = time.monotonic() + timeout

        # A fast or cached graph may finish before the WebSocket is attached.
        history = self.get_history(prompt_id)
        terminal = self._history_terminal(history, prompt_id)
        if terminal is not None:
            return history

        history = self._wait_websocket(
            prompt_id,
            deadline=deadline,
            on_progress=on_progress,
        )
        if history is not None:
            return history

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            time.sleep(min(poll_interval, remaining))
            history = self.get_history(prompt_id)
            terminal = self._history_terminal(history, prompt_id)
            if terminal is not None:
                return history

        try:
            cancelled = self.cancel_prompt(prompt_id)
        except ComfyUIError as exc:
            raise ComfyUIJobStateUnknown(
                f"ComfyUI job {prompt_id} exceeded {timeout:.1f}s and "
                f"cancellation could not be confirmed: {exc}"
            ) from exc
        if not cancelled:
            raise ComfyUIJobStateUnknown(
                f"ComfyUI job {prompt_id} exceeded {timeout:.1f}s; no active "
                "prompt was found, but completion/output state is UNKNOWN"
            )
        raise ComfyUITimeout(
            f"ComfyUI job {prompt_id} exceeded {timeout:.1f}s; cancellation requested"
        )

    def interrupt(self) -> None:
        try:
            response_context = self.session.post(
                self._url("/interrupt"), timeout=self.timeout, stream=True
            )
        except requests.RequestException as exc:
            raise ComfyUITransportError(f"ComfyUI interrupt failed: {exc}") from exc
        with response_context as response:
            if response.status_code >= 400:
                raise ComfyUITransportError(
                    f"ComfyUI interrupt returned HTTP {response.status_code}"
                )

    def cancel_prompt(self, prompt_id: str) -> bool:
        """Cancel one prompt, preferring the server's atomic ID-scoped route."""
        try:
            scoped_response = self.session.post(
                self._url(f"/api/jobs/{quote(prompt_id, safe='')}/cancel"),
                timeout=self.timeout,
                stream=True,
            )
        except requests.RequestException as exc:
            raise ComfyUITransportError(
                f"ComfyUI scoped cancellation failed: {exc}"
            ) from exc
        with scoped_response:
            if scoped_response.status_code < 400:
                payload = _response_payload(scoped_response)
                if not isinstance(payload, Mapping) or not isinstance(
                    payload.get("cancelled"), bool
                ):
                    raise ComfyUITransportError(
                        "ComfyUI scoped cancellation returned an invalid response"
                    )
                return payload["cancelled"]
            if scoped_response.status_code not in {404, 405}:
                raise ComfyUITransportError(
                    "ComfyUI scoped cancellation returned HTTP "
                    f"{scoped_response.status_code}"
                )

        # Compatibility for older pods. The queue snapshot can race with a
        # transition from running to completed, so new ComfyUI versions should
        # always use the ID-scoped route above.
        queue = self.get_queue()
        pending_ids = {
            item_id
            for item_id in (_queue_item_prompt_id(item) for item in queue["queue_pending"])
            if item_id is not None
        }
        running_ids = {
            item_id
            for item_id in (_queue_item_prompt_id(item) for item in queue["queue_running"])
            if item_id is not None
        }
        if prompt_id in pending_ids:
            try:
                response = self.session.post(
                    self._url("/queue"),
                    json={"delete": [prompt_id]},
                    timeout=self.timeout,
                    stream=True,
                )
            except requests.RequestException as exc:
                raise ComfyUITransportError(f"ComfyUI queue cancellation failed: {exc}") from exc
            with response:
                if response.status_code >= 400:
                    raise ComfyUITransportError(
                        "ComfyUI queue cancellation returned HTTP "
                        f"{response.status_code}"
                    )
            raise ComfyUIJobStateUnknown(
                "legacy /queue deletion was requested, but this ComfyUI version "
                "cannot atomically confirm that the prompt did not start first"
            )
        if prompt_id in running_ids:
            raise ComfyUIJobStateUnknown(
                "this ComfyUI version has no ID-scoped running-job cancellation; "
                "refusing a racy global /interrupt"
            )
        return False

    @staticmethod
    def _validate_view_fields(filename: str, subfolder: str, folder_type: str) -> None:
        if (
            not isinstance(filename, str)
            or not filename
            or filename in {".", ".."}
            or "/" in filename
            or "\\" in filename
            or "\x00" in filename
        ):
            raise ComfyUITransportError("ComfyUI returned an unsafe output filename")
        if not isinstance(subfolder, str) or "\\" in subfolder or "\x00" in subfolder:
            raise ComfyUITransportError("ComfyUI returned an invalid output subfolder")
        subpath = PurePosixPath(subfolder)
        if subpath.is_absolute() or ".." in subpath.parts:
            raise ComfyUITransportError("ComfyUI returned an unsafe output subfolder")
        if not isinstance(folder_type, str) or folder_type not in {"output", "temp"}:
            raise ComfyUITransportError(
                f"ComfyUI returned unsupported output type {folder_type!r}"
            )

    def download_image(
        self,
        filename: str,
        subfolder: str,
        folder_type: str,
        destination: str,
        *,
        expected_dimensions: Optional[tuple[int, int]] = None,
        max_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
        max_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
    ) -> str:
        """Validate and atomically publish a ComfyUI image output."""
        self._validate_view_fields(filename, subfolder, folder_type)
        if max_bytes <= 0 or max_pixels <= 0:
            raise ValueError("max_bytes and max_pixels must be positive")
        destination_path = Path(destination)
        destination_format = _DESTINATION_FORMATS.get(destination_path.suffix.lower())
        if destination_format is None:
            raise ComfyUITransportError(
                f"unsupported image destination suffix {destination_path.suffix!r}"
            )
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        source_fd, source_temp = tempfile.mkstemp(
            prefix=".comfy-download-", suffix=".tmp", dir=str(destination_path.parent)
        )
        converted_temp: Optional[str] = None
        try:
            try:
                response_context = self.session.get(
                    self._url("/view"),
                    params={
                        "filename": filename,
                        "subfolder": subfolder,
                        "type": folder_type,
                    },
                    stream=True,
                    timeout=(self.connect_timeout, DEFAULT_DOWNLOAD_READ_TIMEOUT),
                )
            except requests.RequestException as exc:
                raise ComfyUITransportError(f"ComfyUI image download failed: {exc}") from exc

            with response_context as response:
                if response.status_code >= 400:
                    raise ComfyUITransportError(
                        f"ComfyUI image download returned HTTP {response.status_code}"
                    )
                content_type = (
                    response.headers.get("content-type", "")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )
                declared_format = _IMAGE_CONTENT_TYPES.get(content_type)
                if declared_format is None:
                    raise ComfyUITransportError(
                        f"ComfyUI returned non-image content-type {content_type!r}"
                    )
                advertised = response.headers.get("content-length")
                if advertised:
                    try:
                        advertised_size = int(advertised)
                    except ValueError as exc:
                        raise ComfyUITransportError(
                            f"ComfyUI sent invalid content-length {advertised!r}"
                        ) from exc
                    if advertised_size <= 0 or advertised_size > max_bytes:
                        raise ComfyUITransportError(
                            f"ComfyUI image content-length {advertised_size} is outside bounds"
                        )

                written = 0
                with os.fdopen(source_fd, "wb") as output:
                    source_fd = -1
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > max_bytes:
                            raise ComfyUITransportError(
                                f"ComfyUI image exceeded {max_bytes} bytes"
                            )
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if written == 0:
                    raise ComfyUITransportError("ComfyUI returned an empty image")

            try:
                with Image.open(source_temp) as image:
                    actual_format = image.format
                    dimensions = image.size
                    image.verify()
            except (UnidentifiedImageError, OSError, SyntaxError) as exc:
                raise ComfyUITransportError("ComfyUI returned invalid image bytes") from exc
            if actual_format != declared_format:
                raise ComfyUITransportError(
                    f"ComfyUI content-type says {declared_format}, bytes are {actual_format}"
                )
            if dimensions[0] <= 0 or dimensions[1] <= 0:
                raise ComfyUITransportError(
                    f"ComfyUI image has invalid dimensions {dimensions}"
                )
            if dimensions[0] * dimensions[1] > max_pixels:
                raise ComfyUITransportError(
                    f"ComfyUI image dimensions {dimensions} exceed {max_pixels} pixels"
                )
            if expected_dimensions is not None and dimensions != expected_dimensions:
                raise ComfyUITransportError(
                    f"ComfyUI image dimensions {dimensions} do not match "
                    f"expected {expected_dimensions}"
                )

            publish_temp = source_temp
            if actual_format != destination_format:
                converted_fd, converted_temp = tempfile.mkstemp(
                    prefix=".comfy-publish-",
                    suffix=".tmp",
                    dir=str(destination_path.parent),
                )
                os.close(converted_fd)
                with Image.open(source_temp) as image:
                    if destination_format == "JPEG" and image.mode not in {"RGB", "L"}:
                        image = image.convert("RGB")
                    image.save(converted_temp, format=destination_format, quality=95)
                publish_temp = converted_temp

            try:
                destination_mode = destination_path.stat().st_mode & 0o777
            except FileNotFoundError:
                destination_mode = None
            if destination_mode is not None:
                os.chmod(publish_temp, destination_mode)
            os.replace(publish_temp, destination_path)
            if publish_temp == source_temp:
                source_temp = ""
            else:
                converted_temp = None
            return str(destination_path)
        finally:
            if source_fd >= 0:
                os.close(source_fd)
            for temp_path in (source_temp, converted_temp):
                if temp_path:
                    try:
                        os.remove(temp_path)
                    except FileNotFoundError:
                        pass
