"""Contract tests for the shared current-generation Firecrawl boundary."""

from __future__ import annotations

import builtins
import requests
import socket
import sys
import types
from types import SimpleNamespace

import pytest

import firecrawl_adapter
import research_engine
import web_research


@pytest.fixture(autouse=True)
def _reset_shared_client(monkeypatch):
    """Keep the adapter singleton deterministic across tests."""
    monkeypatch.setattr(firecrawl_adapter, "_client", None)
    monkeypatch.setattr(firecrawl_adapter, "_client_api_key", None)


def _install_fake_sdk(monkeypatch, client_type) -> None:
    module = types.ModuleType("firecrawl")
    module.Firecrawl = client_type
    monkeypatch.setitem(sys.modules, "firecrawl", module)


class _SDKDocument:
    """Minimal shape of ``firecrawl.v2.types.Document``."""

    def __init__(self, markdown):
        self.markdown = markdown


def test_real_sdk_document_shape_is_supported():
    from firecrawl.v2.types import Document

    assert (
        firecrawl_adapter._extract_markdown(Document(markdown="# SDK document"))
        == "# SDK document"
    )


def test_client_is_lazy_cached_and_uses_only_current_scrape_contract(monkeypatch):
    constructed = []
    scrape_calls = []

    class FakeFirecrawl:
        def __init__(self, *, api_key, timeout, max_retries):
            constructed.append((api_key, timeout, max_retries))

        def scrape(self, url, *, formats):
            scrape_calls.append((url, formats))
            return _SDKDocument("# Current contract")

        def scrape_url(self, *args, **kwargs):
            pytest.fail("legacy scrape_url must never be called")

    _install_fake_sdk(monkeypatch, FakeFirecrawl)

    assert constructed == []
    assert firecrawl_adapter.scrape_markdown(
        "https://example.com/one",
        api_key="test-key",
    ) == "# Current contract"
    assert firecrawl_adapter.scrape_markdown(
        "https://example.com/two",
        api_key="test-key",
    ) == "# Current contract"

    assert constructed == [("test-key", 60.0, 0)]
    assert scrape_calls == [
        ("https://example.com/one", ["markdown"]),
        ("https://example.com/two", ["markdown"]),
    ]


def test_real_sdk_transport_gets_timeout_and_makes_one_post_without_backoff(
    monkeypatch,
):
    from firecrawl.v2.utils import http_client as sdk_http_client

    requests_seen = []
    sleeps = []

    def record_transport_send(_session, request, **kwargs):
        requests_seen.append((request.method, request.path_url, kwargs))
        response = requests.Response()
        response.status_code = 502
        response._content = b'{"error":"offline bad gateway"}'
        response.headers["Content-Type"] = "application/json"
        response.request = request
        response.url = request.url
        return response

    # Observe the timeout at Requests' transport boundary after the real
    # Firecrawl client has propagated its constructor setting.
    monkeypatch.setattr(requests.sessions.Session, "send", record_transport_send)
    monkeypatch.setattr(
        sdk_http_client,
        "time",
        SimpleNamespace(sleep=lambda seconds: sleeps.append(seconds)),
    )

    with pytest.raises(
        firecrawl_adapter.FirecrawlScrapeError,
        match="scrape request failed",
    ):
        firecrawl_adapter.scrape_markdown(
            "https://example.com",
            api_key="test-key",
        )

    assert len(requests_seen) == 1
    method, path, transport_kwargs = requests_seen[0]
    assert (method, path) == ("POST", "/v2/scrape")
    assert transport_kwargs["timeout"] == 60.0
    assert sleeps == []


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        " https://example.com",
        "https://example.com ",
        "example.com",
        "ftp://example.com",
        "http:///missing-host",
        "http://[malformed",
        "https://example.com:",
        "https://example.com:not-a-port",
        "https://example.com:-1",
        "https://example.com:0",
        "https://example.com:65536",
        "https://[::1]:not-a-port",
        "https://[::1]:0",
        "https://[::1]:65536",
        "https://exa mple.com",
        "https://example.com\t.evil",
        "https://example.com\n.evil",
        "https://example.com\x00.evil",
        "https://example.com\\evil/path",
        "https://example.com\\@evil.com",
        "https://example.com/path with space",
        "https://example.com/path\u00a0with-nbsp",
        "https://example.com/reference?q=raw space",
        "https://example.com/reference\u0080",
        "https://example.com/reference\u009f",
        "https://example.com/reference\ud800",
        "https://exa\u0080mple.com",
        "https://example.com/%",
        "https://example.com/%2",
        "https://example.com/%zz",
        "https://example.com/%2G",
        "https://example.com/reference?q=%G2",
        "https://exa%mple.com",
        "https://:443",
        "https://user@:443",
        "https://user@example.com",
        "https://user:pass@example.com",
        "https://@example.com",
        "https://-bad.example",
        "https://bad-.example",
        "https://bad_label.example",
        "https://.example.com",
        "https://example..com",
        "https://example.com..",
        "https://example.com...",
        "https://例え。テスト。。",
        "https://xn--.example",
        f"https://{'a' * 64}.example",
        "https://999.999.999.999",
        # Localhost names (case, subdomain, terminal-dot, and IDNA separator).
        "http://localhost",
        "http://LOCALHOST",
        "http://localhost.",
        "http://localhost。",
        "http://api.localhost",
        "http://api.localhost.",
        "http://api。localhost",
        # Canonical IPv4 non-public space.
        "http://0.0.0.0",
        "http://10.0.0.1",
        "http://100.64.0.1",
        "http://127.0.0.1",
        "http://127.0.0.1.",
        "http://127。0。0。1",
        "http://169.254.169.254",
        "http://172.16.0.1",
        "http://192.168.1.1",
        "http://192.0.2.1",
        "http://198.18.0.1",
        "http://198.51.100.1",
        "http://203.0.113.1",
        "http://224.0.0.1",
        "http://240.0.0.1",
        "http://255.255.255.255",
        # Canonical IPv6 non-public space, including mapped and scoped forms.
        "http://[::]",
        "http://[::1]",
        "http://[::1]:8080",
        "http://[::ffff:127.0.0.1]",
        "http://[2001:db8::1]",
        "http://[fc00::1]",
        "http://[fec0::1]",
        "http://[fe80::1]",
        "http://[ff02::1]",
        "http://[2001:4860:4860::8888%25eth0]",
        # Legacy numeric IPv4 aliases: short, integer, hex, octal, and mixed.
        "http://127.1",
        "http://127.1.",
        "http://2130706433",
        "http://0x7f000001",
        "http://017700000001",
        "http://0177.0.0.1",
        "http://0x7f.0x0.0x0.0x1",
        "http://127.0x0.0.1",
        "http://127.00.00.01",
        "http://0300.0250.0001.0001",
        "http://3232235777",
        # Reject ambiguous aliases even when their decoded address is public.
        "http://134744072",
        "http://0x08080808",
        "http://8.8.2056",
        # IDNA normalization must not revive Unicode numeric aliases.
        "http://１２７。１",
        "http://①②⑦.①",
        None,
    ],
)
def test_invalid_url_fails_before_client_construction(monkeypatch, url):
    constructed = []
    scrape_calls = []

    class FakeFirecrawl:
        def __init__(self, *, api_key, timeout, max_retries):
            constructed.append((api_key, timeout, max_retries))

        def scrape(self, url, *, formats):
            scrape_calls.append((url, formats))
            return _SDKDocument("must not be returned")

    _install_fake_sdk(monkeypatch, FakeFirecrawl)
    imported = []
    real_import = builtins.__import__

    def recording_import(name, *args, **kwargs):
        if name == "firecrawl":
            imported.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", recording_import)

    with pytest.raises(
        firecrawl_adapter.FirecrawlURLValidationError,
        match=r"valid HTTP\(S\).*without credentials",
    ) as raised:
        firecrawl_adapter.scrape_markdown(url, api_key="test-key")

    assert str(raised.value) == firecrawl_adapter._URL_ERROR
    assert imported == []
    assert constructed == []
    assert scrape_calls == []


@pytest.mark.parametrize(
    "url",
    [
        # Every unqualified name stays local to some resolver context.
        "http://printer",
        "http://PRINTER.",
        "http://例え",
        "http://例え。",
        # Resolver-local/private namespaces, including IDNA dot folding.
        "http://localdomain",
        "http://api.localdomain.",
        "http://device.local",
        "http://device。LOCAL。",
        "http://device.ｌｏｃａｌ",
        "http://home.arpa",
        "http://router.home.arpa.",
        "http://router.ｈｏｍｅ。ａｒｐａ",
        "http://service.internal",
        "http://service。INTERNAL。",
        "http://service.ｉｎｔｅｒｎａｌ",
        # Standards-backed special-use namespaces.
        "http://service.test",
        "http://service.invalid.",
        "http://demo.example",
        "http://hidden.onion",
        "http://resolver.alt.",
    ],
)
def test_non_public_dns_names_fail_before_sdk_import(monkeypatch, url):
    class MustNotConstruct:
        def __init__(self, **_kwargs):
            pytest.fail("non-public host must not construct the SDK client")

    _install_fake_sdk(monkeypatch, MustNotConstruct)
    imported = []
    real_import = builtins.__import__

    def recording_import(name, *args, **kwargs):
        if name == "firecrawl":
            imported.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", recording_import)

    with pytest.raises(firecrawl_adapter.FirecrawlURLValidationError):
        firecrawl_adapter.scrape_markdown(url, api_key="test-key")

    assert imported == []


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "http://example.com:1",
        "https://example.com:65535",
        "https://example.com:443/path?q=value#fragment",
        "https://example.com/path%20with%20space?q=value%20encoded",
        "https://example.com/%00/%2f?q=%FF#%20",
        "http://1.1.1.1",
        "https://8.8.8.8:443/reference",
        "https://9.9.9.9./reference",
        "http://[2606:4700:4700::1111]",
        "https://[2001:4860:4860::8888]:443/reference",
        "https://[::ffff:8.8.8.8]/reference",
        "https://例え.テスト",
        "https://例え。テスト",
        "https://例え．テスト",
        "https://例え｡テスト",
        "https://例え。テスト。",
        "https://例え．テスト．",
        "https://例え｡テスト｡",
        "https://example.com.",
    ],
)
def test_valid_http_hosts_reach_current_scrape_call(monkeypatch, url):
    constructed = []
    scrape_calls = []

    class FakeFirecrawl:
        def __init__(self, *, api_key, timeout, max_retries):
            constructed.append((api_key, timeout, max_retries))

        def scrape(self, requested_url, *, formats):
            scrape_calls.append((requested_url, formats))
            return _SDKDocument("# Valid host")

    _install_fake_sdk(monkeypatch, FakeFirecrawl)

    assert firecrawl_adapter.scrape_markdown(
        url,
        api_key="test-key",
    ) == "# Valid host"
    assert constructed == [("test-key", 60.0, 0)]
    assert scrape_calls == [(url, ["markdown"])]


def test_valid_dns_host_is_not_resolved_before_current_scrape(monkeypatch):
    resolver_calls = []
    scrape_calls = []

    def resolver_bomb(*args, **kwargs):
        resolver_calls.append((args, kwargs))
        raise AssertionError("URL validation must not resolve DNS")

    for resolver_name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        monkeypatch.setattr(socket, resolver_name, resolver_bomb)

    class FakeFirecrawl:
        def __init__(self, *, api_key, timeout, max_retries):
            assert api_key == "test-key"
            assert timeout == 60.0
            assert max_retries == 0

        def scrape(self, url, *, formats):
            scrape_calls.append((url, formats))
            return _SDKDocument("# No preflight")

    _install_fake_sdk(monkeypatch, FakeFirecrawl)

    assert firecrawl_adapter.scrape_markdown(
        "https://public-research.example.com/path",
        api_key="test-key",
    ) == "# No preflight"
    assert resolver_calls == []
    assert scrape_calls == [
        ("https://public-research.example.com/path", ["markdown"]),
    ]


def test_missing_key_fails_without_importing_sdk(monkeypatch):
    imported = []
    real_import = builtins.__import__

    def recording_import(name, *args, **kwargs):
        if name == "firecrawl":
            imported.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", recording_import)

    with pytest.raises(
        firecrawl_adapter.FirecrawlConfigurationError,
        match="FIRECRAWL_API_KEY is missing",
    ):
        firecrawl_adapter.scrape_markdown(
            "https://example.com",
            api_key="   ",
        )

    assert imported == []


def test_missing_package_has_safe_dependency_error(monkeypatch):
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "firecrawl":
            raise ModuleNotFoundError("secret package detail")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    with pytest.raises(
        firecrawl_adapter.FirecrawlDependencyError,
        match="compatible firecrawl-py package is unavailable",
    ) as raised:
        firecrawl_adapter.scrape_markdown(
            "https://example.com",
            api_key="test-key",
        )

    assert "secret package detail" not in str(raised.value)


def test_sdk_import_failure_has_safe_initialization_error(monkeypatch):
    real_import = builtins.__import__

    def broken_import(name, *args, **kwargs):
        if name == "firecrawl":
            raise RuntimeError("import leaked fc-secret-value")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_import)

    with pytest.raises(
        firecrawl_adapter.FirecrawlInitializationError,
        match="SDK could not be loaded",
    ) as raised:
        firecrawl_adapter.scrape_markdown(
            "https://example.com",
            api_key="test-key",
        )

    assert "fc-secret-value" not in str(raised.value)


def test_initialization_failure_does_not_expose_exception_secret(monkeypatch):
    class BrokenFirecrawl:
        def __init__(self, *, api_key, timeout, max_retries):
            assert timeout == 60.0
            assert max_retries == 0
            raise RuntimeError(f"rejected credential {api_key}")

    _install_fake_sdk(monkeypatch, BrokenFirecrawl)

    with pytest.raises(
        firecrawl_adapter.FirecrawlInitializationError,
        match="could not be initialized",
    ) as raised:
        firecrawl_adapter.scrape_markdown(
            "https://example.com",
            api_key="fc-secret-value",
        )

    assert "fc-secret-value" not in str(raised.value)


def test_legacy_only_sdk_is_rejected_without_fallback(monkeypatch):
    class LegacyOnlyFirecrawl:
        def __init__(self, *, api_key, timeout, max_retries):
            self.api_key = api_key
            assert timeout == 60.0
            assert max_retries == 0

        def scrape_url(self, *args, **kwargs):
            pytest.fail("legacy scrape_url must never be called")

    _install_fake_sdk(monkeypatch, LegacyOnlyFirecrawl)

    with pytest.raises(
        firecrawl_adapter.FirecrawlDependencyError,
        match="lacks scrape support",
    ):
        firecrawl_adapter.scrape_markdown(
            "https://example.com",
            api_key="test-key",
        )


def test_call_failure_does_not_expose_exception_secret(monkeypatch):
    class FailingFirecrawl:
        def __init__(self, *, api_key, timeout, max_retries):
            self.api_key = api_key
            assert timeout == 60.0
            assert max_retries == 0

        def scrape(self, url, *, formats):
            raise RuntimeError("upstream leaked fc-secret-value")

    _install_fake_sdk(monkeypatch, FailingFirecrawl)

    with pytest.raises(
        firecrawl_adapter.FirecrawlScrapeError,
        match="scrape request failed",
    ) as raised:
        firecrawl_adapter.scrape_markdown(
            "https://example.com",
            api_key="test-key",
        )

    assert "fc-secret-value" not in str(raised.value)


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (object(), "missing markdown"),
        ({}, "missing markdown"),
        (_SDKDocument(None), "markdown is null"),
        (_SDKDocument(123), "markdown is not text"),
        (_SDKDocument(""), "markdown is empty"),
        (_SDKDocument("   "), "markdown is empty"),
    ],
)
def test_empty_or_malformed_markdown_fails_clearly(
    monkeypatch,
    result,
    message,
):
    class FakeFirecrawl:
        def __init__(self, *, api_key, timeout, max_retries):
            self.api_key = api_key
            assert timeout == 60.0
            assert max_retries == 0

        def scrape(self, url, *, formats):
            return result

    _install_fake_sdk(monkeypatch, FakeFirecrawl)

    with pytest.raises(
        firecrawl_adapter.FirecrawlResultError,
        match=message,
    ):
        firecrawl_adapter.scrape_markdown(
            "https://example.com",
            api_key="test-key",
        )


def test_mapping_result_is_a_deliberate_response_compatibility_path(monkeypatch):
    class FakeFirecrawl:
        def __init__(self, *, api_key, timeout, max_retries):
            self.api_key = api_key
            assert timeout == 60.0
            assert max_retries == 0

        def scrape(self, url, *, formats):
            return {"markdown": "# Decoded response"}

        def scrape_url(self, *args, **kwargs):
            pytest.fail("mapping compatibility must not trigger a legacy call")

    _install_fake_sdk(monkeypatch, FakeFirecrawl)

    assert firecrawl_adapter.scrape_markdown(
        "https://example.com",
        api_key="test-key",
    ) == "# Decoded response"


def test_both_consumers_share_one_lazy_client_and_no_legacy_method(monkeypatch):
    instances = []
    scrape_calls = []

    class FakeFirecrawl:
        def __init__(self, *, api_key, timeout, max_retries):
            assert timeout == 60.0
            assert max_retries == 0
            instances.append(self)

        def scrape(self, url, *, formats):
            scrape_calls.append((url, formats))
            return _SDKDocument(f"markdown for {url}")

        def scrape_url(self, *args, **kwargs):
            pytest.fail("legacy scrape_url must never be called")

    _install_fake_sdk(monkeypatch, FakeFirecrawl)
    monkeypatch.setattr(
        web_research,
        "settings",
        SimpleNamespace(firecrawl_api_key="shared-key"),
    )
    monkeypatch.setattr(
        research_engine,
        "settings",
        SimpleNamespace(firecrawl_api_key="shared-key"),
    )

    assert web_research.scrape_url(
        "https://example.com/web"
    ) == "markdown for https://example.com/web"
    assert research_engine.scrape_technique_reference(
        "https://example.com/engine"
    ) == "markdown for https://example.com/engine"

    assert len(instances) == 1
    assert scrape_calls == [
        ("https://example.com/web", ["markdown"]),
        ("https://example.com/engine", ["markdown"]),
    ]
    assert "_get_firecrawl" not in web_research.__dict__
    assert "_get_firecrawl" not in research_engine.__dict__
    assert "_firecrawl_app" not in web_research.__dict__
    assert "_firecrawl_app" not in research_engine.__dict__


def test_both_production_consumers_route_through_shared_adapter_and_truncate(
    monkeypatch,
):
    calls = []

    def fake_scrape_markdown(url, *, api_key):
        calls.append((url, api_key))
        return "x" * 5000

    monkeypatch.setattr(
        firecrawl_adapter,
        "scrape_markdown",
        fake_scrape_markdown,
    )
    monkeypatch.setattr(
        web_research,
        "settings",
        SimpleNamespace(firecrawl_api_key="web-key"),
    )
    monkeypatch.setattr(
        research_engine,
        "settings",
        SimpleNamespace(firecrawl_api_key="engine-key"),
    )

    assert web_research.scrape_url("https://example.com/web") == "x" * 4000
    assert (
        research_engine.scrape_technique_reference(
            "https://example.com/engine"
        )
        == "x" * 1000
    )
    assert calls == [
        ("https://example.com/web", "web-key"),
        ("https://example.com/engine", "engine-key"),
    ]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            firecrawl_adapter.FirecrawlConfigurationError("safe"),
            "Firecrawl API not configured (FIRECRAWL_API_KEY missing).",
        ),
        (
            firecrawl_adapter.FirecrawlDependencyError("safe"),
            "install a compatible firecrawl-py package",
        ),
        (
            firecrawl_adapter.FirecrawlInitializationError("safe"),
            "Check the Firecrawl API key and SDK installation",
        ),
        (
            firecrawl_adapter.FirecrawlURLValidationError(
                "upstream leaked fc-secret-value"
            ),
            "valid HTTP(S) URL without credentials",
        ),
        (
            firecrawl_adapter.FirecrawlResultError("safe"),
            "Firecrawl returned no usable markdown content",
        ),
        (
            firecrawl_adapter.FirecrawlScrapeError("safe"),
            "Check the URL and Firecrawl service status",
        ),
    ],
)
def test_web_consumer_returns_actionable_safe_errors(
    monkeypatch,
    error,
    expected,
):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(firecrawl_adapter, "scrape_markdown", fail)
    monkeypatch.setattr(
        web_research,
        "settings",
        SimpleNamespace(firecrawl_api_key="test-key"),
    )

    result = web_research.scrape_url("https://example.com")

    assert expected in result
    assert "test-key" not in result
    assert "fc-secret-value" not in result


def test_web_consumer_never_exposes_unexpected_exception_details(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("upstream leaked fc-secret-value")

    monkeypatch.setattr(firecrawl_adapter, "scrape_markdown", fail)
    monkeypatch.setattr(
        web_research,
        "settings",
        SimpleNamespace(firecrawl_api_key="test-key"),
    )

    result = web_research.scrape_url("https://example.com")

    assert "Firecrawl is unavailable" in result
    assert "fc-secret-value" not in result


@pytest.mark.parametrize(
    "error",
    [
        firecrawl_adapter.FirecrawlConfigurationError("safe"),
        firecrawl_adapter.FirecrawlDependencyError("safe"),
        firecrawl_adapter.FirecrawlInitializationError("safe"),
        firecrawl_adapter.FirecrawlURLValidationError("safe"),
        firecrawl_adapter.FirecrawlScrapeError("safe"),
        firecrawl_adapter.FirecrawlResultError("safe"),
        RuntimeError("upstream leaked fc-secret-value"),
    ],
)
def test_research_consumer_quietly_returns_empty_on_every_failure(
    monkeypatch,
    capsys,
    error,
):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(firecrawl_adapter, "scrape_markdown", fail)
    monkeypatch.setattr(
        research_engine,
        "settings",
        SimpleNamespace(firecrawl_api_key="test-key"),
    )

    assert (
        research_engine.scrape_technique_reference("https://example.com")
        == ""
    )
    assert capsys.readouterr().out == ""
