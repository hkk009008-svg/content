"""Shared Firecrawl SDK boundary.

The optional SDK is imported and constructed lazily so importing research
modules never creates a client or performs network work.  Consumers receive
typed, secret-free failures and apply their own user-facing fallback policy.
"""

from __future__ import annotations

from collections.abc import Mapping
from threading import Lock
from urllib.parse import urlparse


class FirecrawlAdapterError(RuntimeError):
    """Base class for safe Firecrawl boundary failures."""


class FirecrawlConfigurationError(FirecrawlAdapterError):
    """Firecrawl cannot run because required configuration is absent."""


class FirecrawlDependencyError(FirecrawlAdapterError):
    """The installed Firecrawl SDK is missing or incompatible."""


class FirecrawlInitializationError(FirecrawlAdapterError):
    """The Firecrawl client could not be initialized."""


class FirecrawlURLValidationError(FirecrawlAdapterError):
    """The requested URL is not an HTTP(S) URL."""


class FirecrawlScrapeError(FirecrawlAdapterError):
    """The Firecrawl scrape call failed."""


class FirecrawlResultError(FirecrawlAdapterError):
    """The Firecrawl response did not contain usable markdown."""


_client = None
_client_api_key: str | None = None
_client_lock = Lock()
_MISSING = object()


def _validate_url(url: str) -> str:
    """Return a normalized HTTP(S) URL without making a network request."""
    if not isinstance(url, str) or not url.strip():
        raise FirecrawlURLValidationError(
            "URL must be a non-empty HTTP(S) URL."
        )

    normalized = url.strip()
    try:
        parsed = urlparse(normalized)
    except ValueError:
        raise FirecrawlURLValidationError(
            "URL must be a non-empty HTTP(S) URL."
        ) from None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise FirecrawlURLValidationError(
            "URL must be a non-empty HTTP(S) URL."
        )
    return normalized


def _get_client(api_key: str):
    """Return the one lazily constructed client for the configured API key."""
    global _client, _client_api_key

    normalized_key = api_key.strip() if isinstance(api_key, str) else ""
    if not normalized_key:
        raise FirecrawlConfigurationError("FIRECRAWL_API_KEY is missing.")

    if _client is not None and _client_api_key == normalized_key:
        return _client

    with _client_lock:
        if _client is not None and _client_api_key == normalized_key:
            return _client

        try:
            from firecrawl import Firecrawl
        except (ImportError, ModuleNotFoundError):
            raise FirecrawlDependencyError(
                "A compatible firecrawl-py package is unavailable."
            ) from None
        except Exception:
            raise FirecrawlInitializationError(
                "The Firecrawl SDK could not be loaded."
            ) from None

        try:
            candidate = Firecrawl(api_key=normalized_key)
        except Exception:
            raise FirecrawlInitializationError(
                "The Firecrawl client could not be initialized."
            ) from None

        try:
            scrape_method = getattr(candidate, "scrape", None)
        except Exception:
            raise FirecrawlInitializationError(
                "The Firecrawl client could not be initialized."
            ) from None

        if not callable(scrape_method):
            raise FirecrawlDependencyError(
                "The installed firecrawl-py package lacks scrape support."
            )

        _client = candidate
        _client_api_key = normalized_key
        return _client


def is_available(api_key: str) -> bool:
    """Return whether a configured, compatible client can be constructed."""
    try:
        _get_client(api_key)
    except Exception:
        return False
    return True


def _extract_markdown(result: object) -> str:
    """Extract SDK ``Document.markdown`` with a narrow mapping fallback.

    The mapping branch deliberately supports decoded responses and lightweight
    test doubles.  It is response compatibility only; requests always use the
    current SDK method.
    """
    try:
        if isinstance(result, Mapping):
            markdown = result.get("markdown", _MISSING)
        else:
            markdown = getattr(result, "markdown", _MISSING)
    except Exception:
        raise FirecrawlResultError(
            "Firecrawl response markdown could not be read."
        ) from None

    if markdown is _MISSING:
        raise FirecrawlResultError("Firecrawl response is missing markdown.")
    if markdown is None:
        raise FirecrawlResultError("Firecrawl response markdown is null.")
    if not isinstance(markdown, str):
        raise FirecrawlResultError("Firecrawl response markdown is not text.")
    if not markdown.strip():
        raise FirecrawlResultError("Firecrawl response markdown is empty.")
    return markdown


def scrape_markdown(url: str, *, api_key: str) -> str:
    """Scrape one URL through the current SDK and return validated markdown."""
    normalized_url = _validate_url(url)
    client = _get_client(api_key)

    try:
        result = client.scrape(normalized_url, formats=["markdown"])
    except Exception:
        raise FirecrawlScrapeError(
            "Firecrawl scrape request failed."
        ) from None

    return _extract_markdown(result)
