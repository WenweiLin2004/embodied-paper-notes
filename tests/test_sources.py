"""Offline fixtures exercise source identity and evidence, never external uptime."""
import json

import httpx
import pytest

from embodied_notes.models import Paper
from embodied_notes.sources import api
from embodied_notes.sources import client as source_client
from embodied_notes.sources.client import SourceError, validate_url
from embodied_notes.sources.parsing import CHUNK_CHARS, chunks_for_text, extract_html, extract_pdf


def feed(*identifiers):
    entries = "".join(f"""<entry><id>http://arxiv.org/abs/{identifier}</id>
      <title> A Robot Policy </title><summary>Abstract about embodiment.</summary>
      <author><name>Alice Robot</name></author><published>2024-01-01T00:00:00Z</published>
      </entry>""" for identifier in identifiers)
    return f'<feed xmlns="http://www.w3.org/2005/Atom">{entries}</feed>'


def response(url, text=None, data=None, content=None):
    options = {"text": text} if text is not None else ({"json": data} if data is not None else {"content": content})
    return httpx.Response(200, request=httpx.Request("GET", url), **options)


@pytest.mark.parametrize("input_id, expected", [
    ("arXiv:2401.12345v2", "2401.12345v2"),
    ("https://arxiv.org/pdf/2401.12345v2.pdf?download=1", "2401.12345v2"),
    ("https://arxiv.org/html/2401.12345v2#S2", "2401.12345v2"),
    ("https://arxiv.org/abs/hep-ph/9901234v1", "hep-ph/9901234v1"),
    ("https://evil.example/arxiv.org/2401.12345", None),
])
def test_identifiers(input_id, expected):
    assert api._arxiv_id(input_id) == expected


def test_resolve_preserves_exact_version(monkeypatch):
    monkeypatch.setattr(api, "_get", lambda url, **kwargs: response(url, text=feed("2401.12345v2")))
    paper = api.resolve("https://arxiv.org/html/2401.12345v2")
    assert paper.id == "arxiv:2401.12345v2"
    assert paper.arxiv_id == "2401.12345"
    assert paper.version == "v2"
    assert paper.pdf_url.endswith("v2")
    assert paper.authors == ["Alice Robot"]


def test_version_mismatch_is_not_silently_upgraded(monkeypatch):
    monkeypatch.setattr(api, "_get", lambda url, **kwargs: response(url, text=feed("2401.12345v3")))
    with pytest.raises(SourceError, match="version mismatch"):
        api.resolve("2401.12345v2")


def test_wrong_paper_identity_rejected(monkeypatch):
    monkeypatch.setattr(api, "_get", lambda url, **kwargs: response(url, text=feed("2401.99999v2")))
    with pytest.raises(SourceError, match="requested paper"):
        api.resolve("2401.12345v2")


def test_search_deduplicates_and_keeps_latest(monkeypatch):
    calls = []
    def fake_get(url, **kwargs):
        calls.append(kwargs["params"])
        return response(url, text=feed("2401.12345v1", "2401.12345v2", "2401.99999v1"))
    monkeypatch.setattr(api, "_get", fake_get)
    papers = api.search('"robot policy"', categories=["cs.RO"], date_from="2024-01-01")
    assert [p.id for p in papers] == ["arxiv:2401.12345v2", "arxiv:2401.99999v1"]
    assert "cat:cs.RO" in calls[0]["search_query"]
    assert "202401010000" in calls[0]["search_query"]


def test_doi_is_metadata_only_with_traceable_abstract(monkeypatch, tmp_path):
    data = {"message": {"DOI": "10.1234/robot", "title": ["Robot study"],
                        "abstract": "<jats:p>Measured grasp success.</jats:p>",
                        "published": {"date-parts": [[2024, 1, 2]]}}}
    monkeypatch.setattr(api, "_get", lambda url, **kwargs: response(url, data=data))
    result = api.fetch_paper("https://doi.org/10.1234/ROBOT", tmp_path)
    assert result.paper.doi == "10.1234/robot"
    assert result.paper.published == "2024-01-02"
    assert not result.full_text
    assert result.parser == "metadata-only"
    assert result.chunks[0].id.startswith("ev-")
    assert result.chunks[0].source_url == "https://doi.org/10.1234/robot"
    assert "Crossref" in result.warnings[0]


def test_abstract_page_is_never_full_text():
    chunks, full, warnings = extract_html("<article><h2>Abstract</h2><p>" + "Robot study. " * 100 + "</p></article>", "https://arxiv.org/abs/2401.12345")
    assert chunks and not full and warnings


def full_html():
    return ("<article><h1>Robot paper</h1><h2>1 Introduction</h2><p>" + "Robot interaction context. " * 40 +
            "</p><h2>2 Method</h2><p>Actions use <math alttext='a_t'>x</math>. " + "Policy evidence. " * 40 + "</p></article>")


def test_html_section_boundaries_and_math_are_preserved():
    chunks, full, warnings = extract_html(full_html(), "https://arxiv.org/html/2401.12345v2")
    assert full and not warnings
    assert [x.section for x in chunks] == ["1 Introduction", "2 Method"]
    assert "$a_t$" in chunks[1].text
    assert all(x.page is None for x in chunks)


def test_bounded_stable_chunks():
    text = "long evidence " * 1400
    chunks = chunks_for_text(text, "Method", "https://example.org/paper")
    assert len(chunks) > 1
    assert all(len(x.text) <= CHUNK_CHARS for x in chunks)
    assert chunks == chunks_for_text(text, "Method", "https://example.org/paper")
    assert " ".join(x.text for x in chunks) == text.strip()


def test_full_html_fetch_cache_is_versioned(monkeypatch, tmp_path):
    calls = []
    def fake_get(url, **kwargs):
        calls.append(url)
        return response(url, text=feed("2401.12345v2") if url == api.ARXIV_API else full_html())
    monkeypatch.setattr(api, "_get", fake_get)
    first = api.fetch_paper("2401.12345v2", tmp_path)
    second = api.fetch_paper("2401.12345v2", tmp_path)
    assert first == second and first.full_text and first.parser == "html"
    assert calls.count("https://arxiv.org/html/2401.12345v2") == 1
    envelope = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert envelope["result"]["paper"]["version"] == "v2"


def test_fulltext_failure_returns_honest_abstract(monkeypatch, tmp_path):
    def fake_get(url, **kwargs):
        if url == api.ARXIV_API:
            return response(url, text=feed("2401.12345v2"))
        raise SourceError("source timeout")
    monkeypatch.setattr(api, "_get", fake_get)
    result = api.fetch_paper("2401.12345v2", tmp_path)
    assert not result.full_text
    assert result.chunks[0].section == "Abstract (metadata only)"
    assert any("timeout" in x for x in result.warnings)
    assert not list(tmp_path.glob("*.json"))


def test_fulltext_version_redirect_is_rejected(monkeypatch, tmp_path):
    def fake_get(url, **kwargs):
        if url == api.ARXIV_API:
            return response(url, text=feed("2401.12345v2"))
        return response("https://arxiv.org/html/2401.12345v3", text=full_html())
    monkeypatch.setattr(api, "_get", fake_get)
    result = api.fetch_paper("2401.12345v2", tmp_path)
    assert not result.full_text
    assert any("changed paper/version" in x for x in result.warnings)


def test_openalex_reconstructs_abstract(monkeypatch):
    item = {"id": "https://openalex.org/W1", "title": "Robotics", "doi": "https://doi.org/10.1234/r",
            "abstract_inverted_index": {"Robots": [0], "learn": [1]}, "authorships": [],
            "best_oa_location": {"landing_page_url": "https://example.org/paper", "pdf_url": None}}
    monkeypatch.setattr(api, "_get", lambda url, **kwargs: response(url, data={"results": [item, item]}))
    papers = api.search("robot", provider="openalex")
    assert len(papers) == 1 and papers[0].abstract == "Robots learn"
    assert papers[0].doi == "10.1234/r"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1/paper", "http://localhost/paper", "http://u:p@example.org/paper", "http://169.254.169.254/latest"])
def test_non_public_urls_rejected(url):
    with pytest.raises(SourceError):
        validate_url(url)


def test_bad_pdf_returns_warning_not_fulltext():
    chunks, full, warnings, parser = extract_pdf(b"%PDF-broken", Paper(id="test", source_url="https://example.org/paper"))
    assert not chunks and not full and warnings


def test_upstream_failure_is_not_empty_search(monkeypatch):
    def fail(*args, **kwargs):
        raise SourceError("Source returned HTTP 429")
    monkeypatch.setattr(api, "_get", fail)
    with pytest.raises(SourceError, match="429"):
        api.search("robot")


def mock_http(monkeypatch, handler):
    original = httpx.Client
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(source_client.httpx, "Client", lambda **kwargs: original(transport=transport, **kwargs))
    monkeypatch.setattr(source_client.time, "sleep", lambda _: None)


def test_http_retries_transient_errors(monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(503 if len(requests) == 1 else 200, text="paper", request=request)
    mock_http(monkeypatch, handler)
    assert source_client.get("https://example.org/paper").text == "paper"
    assert len(requests) == 2


def test_http_gzip_is_not_decoded_twice(monkeypatch):
    import gzip
    def handler(request):
        return httpx.Response(200, content=gzip.compress(b"paper"), headers={"Content-Encoding": "gzip"}, request=request)
    mock_http(monkeypatch, handler)
    assert source_client.get("https://example.org/paper").text == "paper"


def test_http_download_is_bounded(monkeypatch):
    monkeypatch.setattr(source_client, "MAX_DOWNLOAD_BYTES", 10)
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=b"x" * 11, request=request))
    with pytest.raises(SourceError, match="limit"):
        source_client.get("https://example.org/paper")


def test_http_rejects_redirect_to_localhost(monkeypatch):
    mock_http(monkeypatch, lambda request: httpx.Response(302, headers={"Location": "http://localhost/private"}, request=request))
    with pytest.raises(SourceError, match="local address"):
        source_client.get("https://example.org/paper")


def test_docling_explicit_parser_preserves_section_and_page(monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace
    modules = {name: ModuleType(name) for name in ["docling", "docling.datamodel", "docling.datamodel.base_models", "docling.document_converter"]}
    modules["docling.datamodel.base_models"].DocumentStream = lambda **kwargs: SimpleNamespace(**kwargs)
    items = [SimpleNamespace(label="section_header", text="Methods", prov=[]),
             SimpleNamespace(label="text", text="Robot control evidence. " * 50, prov=[SimpleNamespace(page_no=2)])]
    document = SimpleNamespace(iterate_items=lambda: iter((item, 0) for item in items))
    calls = []
    class Converter:
        def convert(self, stream):
            calls.append(stream)
            return SimpleNamespace(status=SimpleNamespace(value="success"), document=document)
    modules["docling.document_converter"].DocumentConverter = Converter
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    chunks, full, warnings, parser = extract_pdf(b"%PDF-test", Paper(id="test", pdf_url="https://example.org/paper.pdf"), pdf_parser="docling")
    assert full and parser == "docling" and len(calls) == 1
    assert chunks[0].section == "Methods" and chunks[0].page == 2
    assert chunks[0].source_url == "https://example.org/paper.pdf"


def test_invalid_pdf_parser_fails_before_network(tmp_path):
    with pytest.raises(ValueError, match="pdf_parser"):
        api.fetch_paper("2401.12345", tmp_path, pdf_parser="imaginary")
