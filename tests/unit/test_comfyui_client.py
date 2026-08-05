"""Offline contract tests for the bounded ComfyUI transport."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
import requests
from PIL import Image

import comfyui_client as cc


class _Response:
    def __init__(
        self,
        payload=None,
        *,
        status_code=200,
        headers=None,
        body=None,
        chunks=None,
    ):
        if body is None:
            body = json.dumps(payload).encode("utf-8")
        self.content = body
        self.status_code = status_code
        self.headers = headers or {"content-type": "application/json"}
        self._payload = payload
        self._chunks = list(chunks) if chunks is not None else [body]

    @property
    def text(self):
        return self.content.decode("utf-8", errors="replace")

    def json(self):
        if self._payload is not None:
            return self._payload
        return json.loads(self.content)

    def iter_content(self, *, chunk_size):
        assert chunk_size == 64 * 1024
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _Session:
    def __init__(self, *, gets=(), posts=()):
        self.headers = {}
        self._gets = iter(gets)
        self._posts = iter(posts)
        self.get_calls = []
        self.post_calls = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        response = next(self._gets)
        if isinstance(response, BaseException):
            raise response
        return response

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        response = next(self._posts)
        if isinstance(response, BaseException):
            raise response
        return response


def _object_info(*, allowed_model="model.safetensors"):
    return {
        "Loader": {
            "input": {
                "required": {
                    "model_name": ([allowed_model],),
                    "strength": ("FLOAT",),
                }
            }
        }
    }


def _workflow(*, model="model.safetensors"):
    return {
        "1": {
            "class_type": "Loader",
            "inputs": {"model_name": model, "strength": 1.0},
        }
    }


def _ready_gets():
    return [
        _Response(_object_info()),
        _Response(["checkpoints", "upscale_models"]),
        _Response({"queue_running": [], "queue_pending": []}),
    ]


def _image_bytes(fmt="PNG", size=(8, 6), color=(10, 20, 30, 255)):
    output = io.BytesIO()
    Image.new("RGBA", size, color).save(output, format=fmt)
    return output.getvalue()


def test_client_uses_bounded_timeouts_and_bearer_auth():
    session = _Session(gets=[_Response({})])
    client = cc.ComfyUIClient(
        "https://worker.example/",
        auth_token="secret",
        session=session,
        connect_timeout=3,
        read_timeout=11,
    )

    assert client.get_history("prompt/id") == {}
    assert session.headers == {"Authorization": "Bearer secret"}
    assert session.get_calls == [
        (
            "https://worker.example/history/prompt%2Fid",
            {"timeout": (3.0, 11.0), "stream": True},
        )
    ]


def test_capability_readiness_uses_authenticated_bounded_route():
    contract = {
        "schema_version": 1,
        "status": "partial",
        "capabilities": {},
    }
    session = _Session(gets=[_Response(contract)])
    client = cc.ComfyUIClient(
        "http://127.0.0.1:18189",
        auth_token="c" * 32,
        session=session,
        connect_timeout=2,
        read_timeout=4,
    )

    assert client.get_gateway_capabilities_readiness() == contract
    assert session.headers == {"Authorization": f"Bearer {'c' * 32}"}
    assert session.get_calls == [
        (
            "http://127.0.0.1:18189/api/capabilities/ready",
            {"timeout": (2.0, 4.0), "stream": True},
        )
    ]


def test_capability_readiness_rejects_non_object_body():
    client = cc.ComfyUIClient(
        "http://127.0.0.1:18189",
        session=_Session(gets=[_Response([])]),
    )

    with pytest.raises(cc.ComfyUIReadinessError, match="must return a JSON object"):
        client.get_gateway_capabilities_readiness()


@pytest.mark.parametrize(
    "server_url",
    ["", "worker:8188", "file:///tmp/socket", "https://worker.example/?token=leak"],
)
def test_client_rejects_non_http_server_urls(server_url):
    with pytest.raises(ValueError, match="non-empty|http|query"):
        cc.ComfyUIClient(server_url)


def test_default_pool_retries_only_idempotent_reads():
    retries = cc._SHARED_ADAPTER.max_retries

    assert retries.allowed_methods == frozenset({"GET", "HEAD", "OPTIONS"})
    assert retries.status_forcelist == frozenset({429, 500, 502, 503, 504})
    assert "POST" not in retries.allowed_methods
    assert retries.backoff_max == 2.0
    assert retries.respect_retry_after_header is False


def test_queue_prompt_preflights_then_submits_once():
    session = _Session(
        gets=_ready_gets(),
        posts=[_Response({"prompt_id": "p-1", "number": 4})],
    )
    client = cc.ComfyUIClient("http://worker:8188", session=session)

    assert client.queue_prompt(_workflow()) == "p-1"
    assert [url.rsplit("/", 1)[-1] for url, _ in session.get_calls] == [
        "object_info",
        "models",
        "queue",
    ]
    assert len(session.post_calls) == 1
    url, kwargs = session.post_calls[0]
    assert url == "http://worker:8188/prompt"
    assert kwargs["timeout"] == (5.0, 30.0)
    assert kwargs["stream"] is True
    assert kwargs["json"]["prompt"] == _workflow()


def test_upload_uses_bounded_timeout_and_parses_remote_name(tmp_path):
    image_path = tmp_path / "face.png"
    image_path.write_bytes(b"local-image")
    session = _Session(posts=[_Response({"name": "face_1.png", "type": "input"})])
    client = cc.ComfyUIClient("http://worker:8188", session=session)

    assert client.upload_image(str(image_path)) == "face_1.png"
    url, kwargs = session.post_calls[0]
    assert url == "http://worker:8188/upload/image"
    assert kwargs["timeout"] == (5.0, 120.0)
    assert kwargs["stream"] is True
    assert set(kwargs["files"]) == {"image"}


def test_preflight_rejects_missing_class_unknown_input_and_model():
    object_info = _object_info()
    bad_workflow = {
        "1": {
            "class_type": "Loader",
            "inputs": {
                "model_name": "missing.safetensors",
                "strength": 1.0,
                "mystery": True,
            },
        },
        "2": {"class_type": "NotInstalled", "inputs": {}},
    }

    with pytest.raises(cc.ComfyUIReadinessError) as caught:
        cc.ComfyUIClient._validate_workflow_contract(bad_workflow, object_info)

    message = str(caught.value)
    assert "missing.safetensors" in message
    assert "unknown inputs ['mystery']" in message
    assert "NotInstalled" in message


def test_prompt_error_and_node_errors_are_raised_immediately():
    rejection = {
        "error": {"type": "prompt_outputs_failed_validation", "message": "bad graph"},
        "node_errors": {"100": {"errors": [{"message": "missing model"}]}},
    }
    session = _Session(
        gets=_ready_gets(),
        posts=[_Response(rejection, status_code=400)],
    )
    client = cc.ComfyUIClient("http://worker:8188", session=session)

    with pytest.raises(cc.ComfyUIPromptRejected) as caught:
        client.queue_prompt(_workflow())

    assert caught.value.error == rejection["error"]
    assert caught.value.node_errors == rejection["node_errors"]
    assert "missing model" in str(caught.value)


def test_prompt_transport_failure_is_unknown_and_never_blindly_retried():
    session = _Session(
        gets=_ready_gets(),
        posts=[requests.ConnectionError("ack lost")],
    )
    client = cc.ComfyUIClient("http://worker:8188", session=session)

    with pytest.raises(cc.ComfyUISubmitUnknown, match="UNKNOWN"):
        client.queue_prompt(_workflow())

    assert len(session.post_calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        _Response(
            {"error": {"message": "proxy failed"}, "node_errors": {}},
            status_code=503,
        ),
        _Response(payload=None, status_code=200, body=b"not-json"),
        _Response({"number": 7}, status_code=200),
    ],
    ids=["server-error", "malformed-json", "missing-prompt-id"],
)
def test_ambiguous_prompt_acknowledgements_are_unknown(response):
    session = _Session(gets=_ready_gets(), posts=[response])
    client = cc.ComfyUIClient("http://worker:8188", session=session)

    with pytest.raises(cc.ComfyUISubmitUnknown, match="UNKNOWN"):
        client.queue_prompt(_workflow())

    assert len(session.post_calls) == 1


def test_wait_for_completion_surfaces_history_execution_error(monkeypatch):
    monkeypatch.setattr(cc, "_websocket_connect", None)
    history = {
        "p-1": {
            "outputs": {},
            "status": {
                "status_str": "error",
                "completed": False,
                "messages": [
                    ["execution_error", {"prompt_id": "p-1", "exception_message": "CUDA OOM"}]
                ],
            },
        }
    }
    session = _Session(gets=[_Response(history)])
    client = cc.ComfyUIClient("http://worker:8188", session=session)

    with pytest.raises(cc.ComfyUIJobError, match="CUDA OOM"):
        client.wait_for_completion("p-1", timeout=1)


def test_wait_for_completion_consumes_websocket_progress_and_completion(monkeypatch):
    initial = _Response({})
    completed = _Response(
        {"p-1": {"outputs": {"9": {"images": []}}, "status": {"completed": True}}}
    )
    session = _Session(gets=[initial, completed])
    progress = []

    class _Websocket:
        def __init__(self):
            self.messages = iter(
                [
                    json.dumps(
                        {"type": "progress", "data": {"prompt_id": "p-1", "value": 2, "max": 4}}
                    ),
                    json.dumps(
                        {"type": "executing", "data": {"prompt_id": "p-1", "node": None}}
                    ),
                ]
            )

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def recv(self, *, timeout):
            assert timeout > 0
            return next(self.messages)

    seen = {}

    def _connect(url, **kwargs):
        seen["url"] = url
        seen["kwargs"] = kwargs
        return _Websocket()

    monkeypatch.setattr(cc, "_websocket_connect", _connect)
    client = cc.ComfyUIClient("https://worker.example/proxy", auth_token="key", session=session)

    history = client.wait_for_completion("p-1", timeout=1, on_progress=progress.append)

    assert history["p-1"]["status"]["completed"] is True
    assert progress == [{"prompt_id": "p-1", "value": 2, "max": 4}]
    assert seen["url"].startswith("wss://worker.example/proxy/ws?clientId=")
    assert seen["kwargs"]["additional_headers"] == {"Authorization": "Bearer key"}


def test_modern_execution_success_ignores_foreign_terminal_error(monkeypatch):
    session = _Session(
        gets=[
            _Response({}),
            _Response(
                {
                    "p-1": {
                        "outputs": {"9": {"images": []}},
                        "status": {"completed": True},
                    }
                }
            ),
        ]
    )

    class _Websocket:
        def __init__(self):
            self.messages = iter(
                [
                    json.dumps(
                        {
                            "type": "execution_error",
                            "data": {
                                "prompt_id": "someone-else",
                                "exception_message": "foreign failure",
                            },
                        }
                    ),
                    json.dumps(
                        {"type": "execution_success", "data": {"prompt_id": "p-1"}}
                    ),
                ]
            )

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def recv(self, *, timeout):
            return next(self.messages)

    monkeypatch.setattr(cc, "_websocket_connect", lambda *args, **kwargs: _Websocket())
    client = cc.ComfyUIClient("https://worker.example", session=session)

    history = client.wait_for_completion("p-1", timeout=1)

    assert history["p-1"]["status"]["completed"] is True
    assert len(session.get_calls) == 2


def test_legacy_pending_delete_is_dispatched_but_not_claimed_atomic():
    queue = {
        "queue_running": [],
        "queue_pending": [[7, "p-1", {"1": {}}, {}, []]],
    }
    session = _Session(
        gets=[_Response(queue)],
        posts=[_Response({}, status_code=404), _Response({})],
    )
    client = cc.ComfyUIClient("http://worker:8188", session=session)

    with pytest.raises(cc.ComfyUIJobStateUnknown, match="cannot atomically confirm"):
        client.cancel_prompt("p-1")
    assert session.post_calls == [
        (
            "http://worker:8188/api/jobs/p-1/cancel",
            {"timeout": (5.0, 30.0), "stream": True},
        ),
        (
            "http://worker:8188/queue",
            {
                "json": {"delete": ["p-1"]},
                "timeout": (5.0, 30.0),
                "stream": True,
            },
        )
    ]


def test_legacy_running_cancel_refuses_racy_global_interrupt():
    queue = {
        "queue_running": [[7, "p-1", {"1": {}}, {}, []]],
        "queue_pending": [],
    }
    session = _Session(gets=[_Response(queue)], posts=[_Response({}, status_code=404)])
    client = cc.ComfyUIClient("http://worker:8188", session=session)

    with pytest.raises(cc.ComfyUIJobStateUnknown, match="racy global /interrupt"):
        client.cancel_prompt("p-1")
    assert session.post_calls == [
        (
            "http://worker:8188/api/jobs/p-1/cancel",
            {"timeout": (5.0, 30.0), "stream": True},
        )
    ]


def test_cancel_prefers_atomic_prompt_scoped_route():
    session = _Session(posts=[_Response({"cancelled": True})])
    client = cc.ComfyUIClient("http://worker:8188", session=session)

    assert client.cancel_prompt("p/1") is True
    assert session.get_calls == []
    assert session.post_calls == [
        (
            "http://worker:8188/api/jobs/p%2F1/cancel",
            {"timeout": (5.0, 30.0), "stream": True},
        )
    ]


def test_explicit_global_interrupt_is_bounded_and_not_retried():
    session = _Session(posts=[_Response({})])
    client = cc.ComfyUIClient("http://worker:8188", session=session)

    client.interrupt()

    assert session.post_calls == [
        (
            "http://worker:8188/interrupt",
            {"timeout": (5.0, 30.0), "stream": True},
        )
    ]


def test_job_deadline_allows_fallback_only_after_confirmed_scoped_cancel(monkeypatch):
    monkeypatch.setattr(cc, "_websocket_connect", None)
    ticks = iter([0.0, 0.5, 0.5, 1.1])
    monkeypatch.setattr(cc.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(cc.time, "sleep", lambda delay: None)
    session = _Session(
        gets=[_Response({}), _Response({})],
        posts=[_Response({"cancelled": True})],
    )
    client = cc.ComfyUIClient("http://worker:8188", session=session)

    with pytest.raises(cc.ComfyUITimeout, match="cancellation requested"):
        client.wait_for_completion("p-1", timeout=1.0, poll_interval=0.1)

    assert session.post_calls == [
        (
            "http://worker:8188/api/jobs/p-1/cancel",
            {"timeout": (5.0, 30.0), "stream": True},
        )
    ]


def test_job_deadline_fails_closed_when_scoped_cancel_finds_no_active_job(
    monkeypatch,
):
    monkeypatch.setattr(cc, "_websocket_connect", None)
    ticks = iter([0.0, 0.5, 0.5, 1.1])
    monkeypatch.setattr(cc.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(cc.time, "sleep", lambda delay: None)
    session = _Session(
        gets=[_Response({}), _Response({})],
        posts=[_Response({"cancelled": False})],
    )
    client = cc.ComfyUIClient("http://worker:8188", session=session)

    with pytest.raises(cc.ComfyUIJobStateUnknown, match="UNKNOWN"):
        client.wait_for_completion("p-1", timeout=1.0, poll_interval=0.1)

    assert len(session.post_calls) == 1


def test_download_validates_png_and_atomically_publishes_jpeg(tmp_path, monkeypatch):
    png = _image_bytes("PNG", size=(8, 6))
    response = _Response(
        body=png,
        headers={"content-type": "image/png", "content-length": str(len(png))},
        chunks=[png[:12], png[12:]],
    )
    session = _Session(gets=[response])
    client = cc.ComfyUIClient("http://worker:8188", session=session)
    destination = tmp_path / "take.jpg"
    destination.write_bytes(b"known-good")
    real_replace = cc.os.replace
    observations = []

    def _replace(source, target):
        observations.append((Path(target).read_bytes(), Path(source).read_bytes()[:3]))
        real_replace(source, target)

    monkeypatch.setattr(cc.os, "replace", _replace)

    result = client.download_image(
        "frame.png",
        "project/shot",
        "output",
        str(destination),
        expected_dimensions=(8, 6),
    )

    assert result == str(destination)
    assert observations[0][0] == b"known-good"
    assert observations[0][1] == b"\xff\xd8\xff"
    assert session.get_calls[0][1]["stream"] is True
    assert session.get_calls[0][1]["timeout"] == (5.0, 120.0)
    with Image.open(destination) as image:
        assert image.format == "JPEG"
        assert image.size == (8, 6)
    assert list(tmp_path.glob(".comfy-*.tmp")) == []


@pytest.mark.parametrize(
    ("headers", "body", "expected"),
    [
        ({"content-type": "text/html"}, b"<html>error</html>", "non-image"),
        ({"content-type": "image/png"}, b"not really png", "invalid image bytes"),
    ],
)
def test_invalid_download_preserves_existing_destination(
    tmp_path, headers, body, expected
):
    response = _Response(body=body, headers=headers, chunks=[body])
    session = _Session(gets=[response])
    client = cc.ComfyUIClient("http://worker:8188", session=session)
    destination = tmp_path / "take.jpg"
    destination.write_bytes(b"known-good")

    with pytest.raises(cc.ComfyUITransportError, match=expected):
        client.download_image("frame.png", "", "output", str(destination))

    assert destination.read_bytes() == b"known-good"
    assert list(tmp_path.glob(".comfy-*.tmp")) == []


def test_wrong_dimensions_preserve_existing_destination(tmp_path):
    png = _image_bytes("PNG", size=(8, 6))
    response = _Response(
        body=png,
        headers={"content-type": "image/png"},
        chunks=[png],
    )
    session = _Session(gets=[response])
    client = cc.ComfyUIClient("http://worker:8188", session=session)
    destination = tmp_path / "take.png"
    destination.write_bytes(b"known-good")

    with pytest.raises(cc.ComfyUITransportError, match="do not match"):
        client.download_image(
            "frame.png",
            "",
            "output",
            str(destination),
            expected_dimensions=(16, 9),
        )

    assert destination.read_bytes() == b"known-good"


def test_excessive_pixel_count_preserves_existing_destination(tmp_path):
    png = _image_bytes("PNG", size=(8, 6))
    response = _Response(
        body=png,
        headers={"content-type": "image/png"},
        chunks=[png],
    )
    session = _Session(gets=[response])
    client = cc.ComfyUIClient("http://worker:8188", session=session)
    destination = tmp_path / "take.png"
    destination.write_bytes(b"known-good")

    with pytest.raises(cc.ComfyUITransportError, match="exceed"):
        client.download_image(
            "frame.png", "", "output", str(destination), max_pixels=47
        )

    assert destination.read_bytes() == b"known-good"


def test_unsafe_output_metadata_is_rejected_before_network(tmp_path):
    session = _Session()
    client = cc.ComfyUIClient("http://worker:8188", session=session)

    with pytest.raises(cc.ComfyUITransportError, match="unsafe output filename"):
        client.download_image("../secret.png", "", "output", str(tmp_path / "x.png"))

    assert session.get_calls == []


def test_json_limit_is_enforced_while_streaming(monkeypatch):
    monkeypatch.setattr(cc, "MAX_JSON_BYTES", 5)

    class _StreamingOnlyResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        @property
        def content(self):
            raise AssertionError("response.content must never be buffered")

        def iter_content(self, *, chunk_size):
            assert chunk_size == 64 * 1024
            yield b"1234"
            yield b"56"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    session = _Session(gets=[_StreamingOnlyResponse()])
    client = cc.ComfyUIClient("http://worker:8188", session=session)

    with pytest.raises(cc.ComfyUITransportError, match="exceeds 5 bytes"):
        client.get_history("p-1")
