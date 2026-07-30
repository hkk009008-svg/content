"""Shared Firecrawl SDK boundary.

The optional SDK is imported and constructed lazily so importing research
modules never creates a client or performs network work.  Consumers receive
typed, secret-free failures and apply their own user-facing fallback policy.
"""

from __future__ import annotations

from collections.abc import Mapping
from ipaddress import IPv4Address, IPv6Address
import re
from threading import Lock
from unicodedata import category as unicode_category
from urllib.parse import urlsplit


class FirecrawlAdapterError(RuntimeError):
    """Base class for safe Firecrawl boundary failures."""


class FirecrawlConfigurationError(FirecrawlAdapterError):
    """Firecrawl cannot run because required configuration is absent."""


class FirecrawlDependencyError(FirecrawlAdapterError):
    """The installed Firecrawl SDK is missing or incompatible."""


class FirecrawlInitializationError(FirecrawlAdapterError):
    """The Firecrawl client could not be initialized."""


class FirecrawlURLValidationError(FirecrawlAdapterError):
    """The requested URL is not an allowed public HTTP(S) URL."""


class FirecrawlScrapeError(FirecrawlAdapterError):
    """The Firecrawl scrape call failed."""


class FirecrawlResultError(FirecrawlAdapterError):
    """The Firecrawl response did not contain usable markdown."""


_client = None
_client_api_key: str | None = None
_client_lock = Lock()
_MISSING = object()
_URL_ERROR = "URL must be a valid HTTP(S) URL without credentials."
_HOST_LABEL = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
)
_LEGACY_IPV4_PART = re.compile(r"(?:0[xX][0-9A-Fa-f]+|[0-9]+)")
_ASCII_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _raise_url_error() -> None:
    raise FirecrawlURLValidationError(_URL_ERROR)


def _validate_public_ip(address: IPv4Address | IPv6Address) -> None:
    """Allow only literal addresses that are globally routable unicast."""
    if (
        not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or (
            isinstance(address, IPv6Address)
            and (address.is_site_local or address.scope_id is not None)
        )
    ):
        _raise_url_error()


def _looks_like_legacy_ipv4(hostname: str) -> bool:
    """Recognize browser-compatible non-canonical numeric IPv4 spellings."""
    labels = hostname.split(".")
    return (
        1 <= len(labels) <= 4
        and all(_LEGACY_IPV4_PART.fullmatch(label) for label in labels)
    )


def _validate_hostname(hostname: str) -> None:
    """Reject unsafe IP literals, numeric aliases, and malformed DNS names."""
    if ":" in hostname:
        try:
            address = IPv6Address(hostname)
        except ValueError:
            _raise_url_error()
        _validate_public_ip(address)
        return

    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        _raise_url_error()

    has_terminal_dot = ascii_hostname.endswith(".")
    canonical_hostname = (
        ascii_hostname[:-1] if has_terminal_dot else ascii_hostname
    )
    if not canonical_hostname or canonical_hostname.endswith("."):
        _raise_url_error()

    canonical_hostname = canonical_hostname.lower()
    if (
        canonical_hostname == "localhost"
        or canonical_hostname.endswith(".localhost")
    ):
        _raise_url_error()

    try:
        address = IPv4Address(canonical_hostname)
    except ValueError:
        address = None
    if address is not None:
        _validate_public_ip(address)
        return

    # Browsers and HTTP stacks may interpret one-to-four decimal, octal, or
    # hexadecimal components as IPv4 even when ``ipaddress`` correctly refuses
    # the non-canonical spelling.  Never let those ambiguous aliases fall
    # through as DNS names.
    if _looks_like_legacy_ipv4(canonical_hostname):
        _raise_url_error()

    ascii_labels = canonical_hostname.split(".")
    if any(not label for label in ascii_labels):
        _raise_url_error()

    for ascii_label in ascii_labels:
        try:
            if ascii_label.lower().startswith("xn--"):
                decoded = ascii_label.encode("ascii").decode("idna")
                round_trip = decoded.encode("idna").decode("ascii")
                if round_trip.lower() != ascii_label.lower():
                    _raise_url_error()
        except (UnicodeError, ValueError):
            _raise_url_error()

        if not _HOST_LABEL.fullmatch(ascii_label):
            _raise_url_error()

    if len(canonical_hostname) > 253:
        _raise_url_error()


def _validate_percent_escapes(url: str) -> None:
    """Require every raw percent sign to begin one ASCII hex triplet."""
    position = 0
    while True:
        position = url.find("%", position)
        if position < 0:
            return
        escape = url[position + 1:position + 3]
        if (
            len(escape) != 2
            or any(character not in _ASCII_HEX_DIGITS for character in escape)
        ):
            _raise_url_error()
        position += 3


def _validate_url(url: str) -> str:
    """Return the original public HTTP(S) URL after deterministic validation."""
    if not isinstance(url, str) or not url or url != url.strip():
        _raise_url_error()
    if any(
        character.isspace()
        or unicode_category(character) in {"Cc", "Cs"}
        for character in url
    ):
        _raise_url_error()
    _validate_percent_escapes(url)

    scheme_delimiter = url.find("://")
    if scheme_delimiter <= 0:
        _raise_url_error()
    authority_start = scheme_delimiter + 3
    authority_end = len(url)
    for delimiter in "/?#":
        position = url.find(delimiter, authority_start)
        if position >= 0:
            authority_end = min(authority_end, position)
    authority = url[authority_start:authority_end]
    if (
        not authority
        or "\\" in authority
        or any(character.isspace() for character in authority)
    ):
        _raise_url_error()

    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
        username = parsed.username
        password = parsed.password
    except (UnicodeError, ValueError):
        raise FirecrawlURLValidationError(_URL_ERROR) from None

    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        _raise_url_error()
    if parsed.netloc != authority:
        _raise_url_error()
    if username is not None or password is not None or "@" in authority:
        _raise_url_error()
    if not hostname or authority.endswith(":"):
        _raise_url_error()

    bracketed_authority = authority.startswith("[")
    if bracketed_authority != (":" in hostname):
        _raise_url_error()
    if port is not None and not 1 <= port <= 65535:
        _raise_url_error()

    _validate_hostname(hostname)
    return url


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
            candidate = Firecrawl(
                api_key=normalized_key,
                max_retries=0,
            )
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
    validated_url = _validate_url(url)
    client = _get_client(api_key)

    try:
        result = client.scrape(validated_url, formats=["markdown"])
    except Exception:
        raise FirecrawlScrapeError(
            "Firecrawl scrape request failed."
        ) from None

    return _extract_markdown(result)
