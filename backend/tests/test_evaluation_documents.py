"""Source documents: validation, extraction and shared-library rules."""
from __future__ import annotations

import unittest

import httpx

from app.evaluation.documents import (
    DocumentLibrary,
    DocumentUnavailable,
    FakeDocumentFetcher,
    HttpDocumentFetcher,
    SourceDocument,
    collect_source_urls,
    html_to_text,
    validate_public_url,
)

URL = "https://brand.example/serum"
LONG_TEXT = (
    "Formula: Aqua, Glycerin, Niacinamide. Glycerin helps keep the skin hydrated "
    "and supports the skin barrier."
)


class SourceDocumentTests(unittest.TestCase):
    def test_document_requires_http_url(self):
        with self.assertRaises(ValueError):
            SourceDocument(url="ftp://brand.example/x", text=LONG_TEXT)

    def test_document_requires_verifiable_text(self):
        with self.assertRaises(ValueError):
            SourceDocument(url=URL, text="too short")

    def test_document_rejects_unknown_provenance(self):
        with self.assertRaises(ValueError):
            SourceDocument(url=URL, text=LONG_TEXT, provenance="guessed")

    def test_hash_is_stable_and_whitespace_normalised(self):
        first = SourceDocument(url=URL, text="Glycerin   helps\n keep the skin hydrated " + "x" * 20)
        second = SourceDocument(url=URL, text=" Glycerin helps keep the skin hydrated " + "x" * 20)
        self.assertEqual(first.content_hash, second.content_hash)
        self.assertEqual(first.text, second.text)

    def test_retrieved_at_defaults_to_now(self):
        document = SourceDocument(url=URL, text=LONG_TEXT)
        self.assertTrue(document.retrieved_at)
        self.assertEqual(document.site, "brand.example")


class HtmlExtractionTests(unittest.TestCase):
    def test_scripts_and_head_are_not_part_of_the_text(self):
        title, text = html_to_text(
            "<html><head><title>Serum</title><script>var x=1;</script></head>"
            "<body><p>Glycerin helps keep the skin hydrated</p></body></html>"
        )
        self.assertEqual(title, "Serum")
        self.assertNotIn("var x", text)
        self.assertIn("Glycerin helps keep the skin hydrated", text)

    def test_malformed_html_still_yields_text(self):
        _, text = html_to_text("<p>Glycerin helps keep the skin hydrated<br>")
        self.assertIn("Glycerin", text)


class UrlCollectionTests(unittest.TestCase):
    def test_collects_mapping_list_and_extra_without_duplicates(self):
        urls = collect_source_urls(
            {"url": "https://a.example/p", "incidecoder_url": "https://b.example/p"},
            ["https://a.example/p", "not-a-url"],
            {"source_urls": ["https://c.example/p"]},
            extra=("https://d.example/p",),
        )
        self.assertEqual(
            urls,
            (
                "https://a.example/p",
                "https://b.example/p",
                "https://c.example/p",
                "https://d.example/p",
            ),
        )

    def test_non_http_values_are_ignored(self):
        self.assertEqual(collect_source_urls({"source": "catalog"}, "ftp://x"), ())

    def test_private_addresses_are_rejected(self):
        for url in ("http://localhost/x", "http://127.0.0.1/x", "http://10.0.0.5/x"):
            with self.assertRaises(DocumentUnavailable, msg=url):
                validate_public_url(url)


class DocumentLibraryTests(unittest.TestCase):
    def test_library_deduplicates_by_url(self):
        library = DocumentLibrary()
        self.assertTrue(library.add(SourceDocument(url=URL, text=LONG_TEXT)))
        self.assertFalse(library.add(SourceDocument(url=URL, text=LONG_TEXT + " more")))
        self.assertEqual(len(library), 1)
        self.assertIn(URL, library)
        self.assertEqual(len(library.texts()), 1)

    def test_extend_returns_number_of_new_documents(self):
        library = DocumentLibrary([SourceDocument(url=URL, text=LONG_TEXT)])
        added = library.extend(
            [
                SourceDocument(url=URL, text=LONG_TEXT),
                SourceDocument(url="https://other.example/p", text=LONG_TEXT),
            ]
        )
        self.assertEqual(added, 1)
        self.assertEqual(len(library.documents()), 2)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class HttpDocumentFetcherTests(unittest.TestCase):
    def _fetcher(self, handler) -> HttpDocumentFetcher:
        return HttpDocumentFetcher(client=_client(handler), validate_url=False)

    def test_html_page_becomes_a_fetched_document(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                html="<html><head><title>Serum</title></head>"
                "<body><p>Glycerin helps keep the skin hydrated and supports the "
                "skin barrier.</p></body></html>",
                request=request,
            )

        document = self._fetcher(handler).fetch(URL)
        self.assertEqual(document.provenance, "fetched")
        self.assertEqual(document.title, "Serum")
        self.assertIn("Glycerin helps keep the skin hydrated", document.text)

    def test_http_error_is_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, request=request)

        with self.assertRaises(DocumentUnavailable):
            self._fetcher(handler).fetch(URL)

    def test_binary_content_is_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "application/pdf"},
                content=b"%PDF-1.7 ...",
                request=request,
            )

        with self.assertRaises(DocumentUnavailable):
            self._fetcher(handler).fetch(URL)

    def test_page_without_text_is_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"<html><body><script>x</script></body></html>",
                request=request,
            )

        with self.assertRaises(DocumentUnavailable):
            self._fetcher(handler).fetch(URL)


    def test_redirect_to_a_public_page_is_followed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/serum":
                return httpx.Response(
                    302, headers={"location": "https://brand.example/full"}, request=request
                )
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                html="<html><body><p>Glycerin helps keep the skin hydrated and "
                "supports the skin barrier.</p></body></html>",
                request=request,
            )

        document = self._fetcher(handler).fetch(URL)
        self.assertIn("Glycerin", document.text)


class FakeDocumentFetcherTests(unittest.TestCase):
    def test_fake_fetcher_is_deterministic_and_logs_calls(self):
        fetcher = FakeDocumentFetcher({URL: ("Serum", LONG_TEXT)})
        document = fetcher.fetch(URL)
        self.assertEqual(document.provenance, "synthetic")
        self.assertEqual(document.title, "Serum")
        self.assertEqual(fetcher.calls, [URL])

    def test_fake_fetcher_reports_unavailable(self):
        fetcher = FakeDocumentFetcher({}, unavailable=[URL])
        with self.assertRaises(DocumentUnavailable):
            fetcher.fetch(URL)


if __name__ == "__main__":
    unittest.main()

