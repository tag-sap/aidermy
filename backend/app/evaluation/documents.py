"""Source documents: the shared, verifiable base of product knowledge.

A document is the *text of a page that was actually downloaded*. Evidence quotes
are validated against this text, never against text produced by a model. The same
document can ground several questionnaire parameters and is stored once per
composition, so a later analysis reuses it instead of downloading the page again.

What this module does NOT do: it does not search the web. URLs come from the
product record, the verified composition and Aidermy's ingredient knowledge base.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Iterable, Mapping, Protocol, Sequence
from urllib.parse import urlparse

PROVENANCE_FETCHED = "fetched"
PROVENANCE_SYNTHETIC = "synthetic"
PROVENANCE_UNKNOWN = "unknown"
DOCUMENT_PROVENANCES = (PROVENANCE_FETCHED, PROVENANCE_SYNTHETIC, PROVENANCE_UNKNOWN)

MIN_DOCUMENT_CHARS = 40
MAX_DOCUMENT_CHARS = 60_000
MAX_DOCUMENTS_PER_SESSION = 8

_WS_RE = re.compile(r"\s+")
_SCRIPT_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_PRIVATE_HOSTS = {"localhost", "metadata.google.internal"}


class DocumentUnavailable(RuntimeError):
    """A page could not be obtained; this is data, not a crash."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason


def normalize_document_text(text: str) -> str:
    """Collapse whitespace so quotes survive HTML formatting differences."""
    return _WS_RE.sub(" ", str(text or "")).strip()


def sha256_of_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceDocument:
    """Text of one downloaded page, bound to a composition by the store."""

    url: str
    text: str
    title: str = ""
    retrieved_at: str = ""
    provenance: str = PROVENANCE_FETCHED
    content_hash: str = ""

    def __post_init__(self) -> None:
        parsed = urlparse(str(self.url or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"document url must be http(s): {self.url!r}")
        if self.provenance not in DOCUMENT_PROVENANCES:
            raise ValueError(f"unknown document provenance: {self.provenance}")
        text = normalize_document_text(self.text)
        if len(text) < MIN_DOCUMENT_CHARS:
            raise ValueError(
                f"document text is too short to verify a quote: {len(text)} chars"
            )
        object.__setattr__(self, "url", parsed.geturl())
        object.__setattr__(self, "text", text[:MAX_DOCUMENT_CHARS])
        if not self.content_hash:
            object.__setattr__(self, "content_hash", sha256_of_text(self.text))
        if not self.retrieved_at:
            object.__setattr__(self, "retrieved_at", datetime.now(timezone.utc).isoformat())

    @property
    def site(self) -> str:
        return urlparse(self.url).netloc.lower()

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "retrieved_at": self.retrieved_at,
            "provenance": self.provenance,
            "content_hash": self.content_hash,
        }

def validate_public_url(url: str) -> str:
    """Reject non-public targets so a research URL cannot reach the local network."""
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise DocumentUnavailable(str(url), "нужен адрес http(s)")
    if parsed.username or parsed.password:
        raise DocumentUnavailable(str(url), "адрес с учётными данными не принимается")
    host = parsed.hostname.rstrip(".").lower()
    if host in _PRIVATE_HOSTS or host.endswith(".local"):
        raise DocumentUnavailable(str(url), "локальный адрес не принимается")
    try:
        addresses = socket.getaddrinfo(
            host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise DocumentUnavailable(str(url), f"домен не разрешается: {exc}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise DocumentUnavailable(str(url), "адрес указывает во внутреннюю сеть")
    return parsed.geturl()


class _TextExtractor(HTMLParser):
    """Minimal HTML→text: enough for quotes, no new dependencies."""

    _SKIP = {"script", "style", "noscript", "template", "svg", "head", "title"}
    _BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "section"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001 - stdlib signature
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self._parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCK:
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(data)

    @property
    def text(self) -> str:
        return normalize_document_text("".join(self._parts))


def html_to_text(html: str) -> tuple[str, str]:
    """Return ``(title, text)`` for an HTML page."""
    raw = str(html or "")
    title_match = _TITLE_RE.search(raw)
    title = normalize_document_text(title_match.group(1)) if title_match else ""
    stripped = _SCRIPT_RE.sub(" ", raw)
    parser = _TextExtractor()
    try:
        parser.feed(stripped)
        parser.close()
        text = parser.text
    except Exception:  # noqa: BLE001 - malformed HTML must not fail a research run
        text = normalize_document_text(_TAG_RE.sub(" ", stripped))
    return title, text


class DocumentFetcher(Protocol):
    """Downloads a page once; the caller decides which URLs are worth fetching."""

    name: str

    def fetch(self, url: str) -> SourceDocument: ...


class HttpDocumentFetcher:
    """Real HTTP fetcher (httpx) with SSRF protection and a size limit."""

    name = "http"

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        max_bytes: int = 2_000_000,
        user_agent: str = "AidermyResearch/1.0 (+https://aidermy.local)",
        client=None,
        validate_url: bool = True,
    ) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.user_agent = user_agent
        self._client = client
        self.validate_url = validate_url

    def _http_client(self):
        if self._client is not None:
            return self._client
        import httpx

        self._client = httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent, "Accept": "text/html,text/plain"},
        )
        return self._client

    def fetch(self, url: str) -> SourceDocument:
        from urllib.parse import urljoin

        safe_url = validate_public_url(url) if self.validate_url else str(url)
        response = None
        current = safe_url
        for _ in range(4):
            try:
                response = self._http_client().get(current, follow_redirects=False)
            except Exception as exc:  # noqa: BLE001 - network failures are data
                raise DocumentUnavailable(url, f"запрос не выполнен: {exc}") from exc
            status = int(getattr(response, "status_code", 0))
            if status not in {301, 302, 303, 307, 308}:
                break
            location = response.headers.get("location") or ""
            if not location:
                raise DocumentUnavailable(url, "редирект без адреса")
            current = urljoin(current, location)
            # Validate every hop: a public URL must not redirect into the LAN.
            if self.validate_url:
                current = validate_public_url(current)
        else:
            raise DocumentUnavailable(url, "слишком много редиректов")
        assert response is not None
        status = int(getattr(response, "status_code", 0))
        if status >= 400:
            raise DocumentUnavailable(url, f"HTTP {status}")
        content_type = str(response.headers.get("content-type") or "").lower()
        if content_type and not any(
            marker in content_type
            for marker in ("text/html", "text/plain", "application/xhtml")
        ):
            raise DocumentUnavailable(url, f"тип содержимого не текст: {content_type}")
        raw = response.content or b""
        if len(raw) > self.max_bytes:
            raw = raw[: self.max_bytes]
        html = raw.decode(response.encoding or "utf-8", errors="replace")
        title, text = html_to_text(html)
        if len(text) < MIN_DOCUMENT_CHARS:
            raise DocumentUnavailable(url, "на странице нет пригодного текста")
        return SourceDocument(
            url=str(getattr(response, "url", current) or current),
            title=title,
            text=text,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            provenance=PROVENANCE_FETCHED,
        )


class FakeDocumentFetcher:
    """Deterministic fetcher for tests: no network, full call log."""

    name = "fake"

    def __init__(
        self,
        pages: Mapping[str, str | tuple[str, str]] | None = None,
        *,
        unavailable: Iterable[str] = (),
    ) -> None:
        self._pages = dict(pages or {})
        self._unavailable = set(unavailable)
        self.calls: list[str] = []

    def fetch(self, url: str) -> SourceDocument:
        self.calls.append(url)
        if url in self._unavailable or url not in self._pages:
            raise DocumentUnavailable(url, "источник недоступен")
        value = self._pages[url]
        title, text = value if isinstance(value, tuple) else ("", value)
        return SourceDocument(
            url=url,
            title=title,
            text=text,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            provenance=PROVENANCE_SYNTHETIC,
        )


class DocumentLibrary:
    """Session-scoped set of documents, deduplicated by URL."""

    def __init__(self, documents: Iterable[SourceDocument] = ()) -> None:
        self._documents: dict[str, SourceDocument] = {}
        for document in documents:
            self.add(document)

    def add(self, document: SourceDocument) -> bool:
        if document.url in self._documents:
            return False
        self._documents[document.url] = document
        return True

    def extend(self, documents: Iterable[SourceDocument]) -> int:
        return sum(1 for document in documents if self.add(document))

    def get(self, url: str) -> SourceDocument | None:
        return self._documents.get(url)

    @property
    def urls(self) -> tuple[str, ...]:
        return tuple(self._documents)

    def documents(self) -> tuple[SourceDocument, ...]:
        return tuple(self._documents.values())

    def texts(self) -> dict[str, str]:
        return {url: document.text for url, document in self._documents.items()}

    def __contains__(self, url: object) -> bool:
        return url in self._documents

    def __len__(self) -> int:
        return len(self._documents)


_URL_FIELDS = (
    "url",
    "source",
    "source_url",
    "incidecoder_url",
    "official_url",
    "product_url",
)


def collect_source_urls(*values: object, extra: Sequence[str] = ()) -> tuple[str, ...]:
    """Collect candidate URLs from product/composition records, keeping order.

    Only http(s) values are returned. Nothing is fetched here: a URL is merely a
    candidate, and failures are reported by the fetcher, not hidden.
    """
    urls: list[str] = []

    def add(value: object) -> None:
        text = str(value or "").strip()
        if not text:
            return
        parsed = urlparse(text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return
        if text not in urls:
            urls.append(text)

    for value in values:
        if value is None:
            continue
        if isinstance(value, Mapping):
            for key in _URL_FIELDS:
                add(value.get(key))
            nested = value.get("source_urls") or value.get("sources") or ()
            if isinstance(nested, (list, tuple, set)):
                for item in nested:
                    add(item)
            continue
        if isinstance(value, (list, tuple, set)):
            for item in value:
                add(item)
            continue
        add(value)
    for url in extra:
        add(url)
    return tuple(urls)

