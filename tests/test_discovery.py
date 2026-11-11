import json
import sys

import httpx
import pytest

from embodied_notes import discovery as d
from embodied_notes.models import Paper
from embodied_notes.sources.client import SourceError


def paper(identifier="arxiv:2406.09246v1", **kwargs):
    return Paper(id=identifier, title="OpenVLA: A Vision-Language-Action Model",
                 authors=["Alice Robot"], published="2024-06-13", **kwargs)


def response(data, status=200):
    return httpx.Response(status, json=data, request=httpx.Request("GET", "https://api.semanticscholar.org/graph/v1/paper/search"))


def s2_item(identifier="a" * 40, **kwargs):
    return {"paperId": identifier, "title": "Robot Learning", "authors": [{"name": "Alice"}],
            "externalIds": {"ArXiv": "2406.09246", "DOI": "10.1234/R"}, "year": 2024, **kwargs}


def test_crossref_source_uses_authoritative_metadata(monkeypatch):
    calls = []
    def get(url, params):
        calls.append((url, params))
        return response({"message": {"items": [{"DOI": "10.1234/R", "title": ["Robot & Policy"],
            "author": [{"given": "Alice", "family": "Robot"}], "abstract": "<p>Text</p>",
            "published": {"date-parts": [[2024, 2, 3]]}}]}})
    monkeypatch.setattr(d, "get", get)
    results = d.search_provider("robot", "crossref", 2)
    assert results[0].doi == "10.1234/r"
    assert results[0].authors == ["Alice Robot"]
    assert results[0].abstract == "Text" and results[0].published == "2024-02-03"
    assert calls[0][1]["rows"] == 2


def test_s2_search_does_not_invent_arxiv_version(monkeypatch):
    monkeypatch.setattr(d, "_s2_get", lambda *args: response({"data": [s2_item()]}))
    result = d.search_provider("robot", "semantic_scholar", 2)[0]
    assert result.arxiv_id == "2406.09246" and result.version is None
    assert result.id.startswith("semantic_scholar:")


@pytest.mark.parametrize("payload", [{"message": []}, {"message": {}}, {"message": {"items": [{"title": ["No DOI"]}]}}])
def test_malformed_crossref_is_error_not_empty_search(monkeypatch, payload):
    monkeypatch.setattr(d, "get", lambda *args, **kwargs: response(payload))
    with pytest.raises(SourceError):
        d.search_provider("robot", "crossref", 1)


def test_federated_partial_failure_retains_success(monkeypatch):
    def search(query, provider, limit):
        if provider == "semantic_scholar":
            raise SourceError("Source returned HTTP 429")
        return [paper(provider="arxiv", arxiv_id="2406.09246", version="v1")]
    monkeypatch.setattr(d, "search_provider", search)
    result = d.federated_search("robot", providers=["arxiv", "semantic_scholar"])
    assert result["status"] == "partial" and result["total"] == 1 and result["metadata_only"]
    assert result["providers"]["semantic_scholar"]["status"] == "rate_limited"
    assert result["providers"]["semantic_scholar"]["http_status"] == 429


def test_merge_doi_retains_provenance_without_invented_version():
    rows, warnings = d._merge_papers([
        paper("oa:1", provider="openalex", doi="10.1234/r", source_url="https://oa.example/r"),
        paper(provider="arxiv", arxiv_id="2406.09246", version="v1", doi="10.1234/r", source_url="https://arxiv.org/abs/2406.09246v1"),
    ])
    assert len(rows) == 1 and rows[0]["version"] == "v1"
    assert len(rows[0]["sources"]) == 2
    assert rows[0]["source_url"].endswith("v1")


def test_distinct_versions_and_unknown_version_stay_separate():
    rows, warnings = d._merge_papers([
        paper(arxiv_id="2406.09246", version="v1", doi="10.1234/r"),
        paper("arxiv:2406.09246v2", arxiv_id="2406.09246", version="v2", doi="10.1234/r"),
        paper("oa:1", doi="10.1234/r"),
    ])
    assert len(rows) == 3
    assert {r["version"] for r in rows} == {"v1", "v2", None}
    assert any("Versionless" in x for x in warnings)


def test_dedup_does_not_merge_conflicting_arxiv_ids_with_same_doi():
    rows, warnings = d._merge_papers([
        paper(arxiv_id="2406.09246", doi="10.1234/r"),
        paper("arxiv:2406.00001", arxiv_id="2406.00001", doi="10.1234/r"),
    ])
    assert len(rows) == 2 and warnings


def test_bridge_metadata_merges_even_if_provider_order_differs():
    rows, _ = d._merge_papers([
        paper("doi:10.1234/r", doi="10.1234/r"),
        paper(arxiv_id="2406.09246", version="v1"),
        paper("oa:1", arxiv_id="2406.09246", doi="10.1234/r"),
    ])
    assert len(rows) == 1 and len(rows[0]["sources"]) == 3


def test_identical_titles_are_not_fuzzy_merged():
    rows, _ = d._merge_papers([paper("one"), paper("two")])
    assert len(rows) == 2


def test_version_can_be_recovered_from_exact_source_id():
    rows, _ = d._merge_papers([paper(arxiv_id="2406.09246"),
                             paper("arxiv:2406.09246v2", arxiv_id="2406.09246")])
    assert len(rows) == 2 and {row["version"] for row in rows} == {"v1", "v2"}
    assert "2406.09246v1" in d.export_citations([paper(arxiv_id="2406.09246")])["content"]


def test_federated_bounded_abstract_is_marked(monkeypatch):
    monkeypatch.setattr(d, "search_provider", lambda *args: [paper(abstract="x" * 2100)])
    result = d.federated_search("robot", 1, ["arxiv"])
    assert len(result["papers"][0]["abstract"]) == 2000
    assert result["papers"][0]["abstract_truncated"] and result["truncated"]


def test_graph_direction_and_work_level_identity(monkeypatch):
    calls = []
    def fetch(path, params):
        calls.append((path, params))
        field = "citedPaper" if path.endswith("references") else "citingPaper"
        return response({"data": [{field: s2_item()}], "next": 1})
    monkeypatch.setattr(d, "_s2_get", fetch)
    graph = d.citation_graph("https://arxiv.org/abs/2406.09246v2", limit=1)
    assert graph["resolved_identifier"] == "ARXIV:2406.09246"
    assert graph["status"] == "ok" and "work-level" in graph["warnings"][0]
    assert len(calls) == 2 and calls[0][1]["limit"] == 1
    assert graph["directions"]["references"]["truncated"]
    assert graph["directions"]["citations"]["papers"][0]["version"] is None


def test_graph_forbidden_is_not_empty_success(monkeypatch):
    monkeypatch.setenv("S2_API_KEY", "secret-test-key")
    def fail(*args):
        raise SourceError("HTTP 403 secret-test-key")
    monkeypatch.setattr(d, "_s2_get", fail)
    result = d.citation_graph("10.1234/r", "references", 1)
    assert result["status"] == "error"
    assert result["directions"]["references"]["status"] == "forbidden"
    assert "secret-test-key" not in json.dumps(result)


def test_authenticated_s2_key_never_follows_redirect(monkeypatch):
    monkeypatch.setenv("S2_API_KEY", "secret-test-key")
    original = httpx.Client
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://evil.example/steal"}, request=request)
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(d.httpx, "Client", lambda **kwargs: original(transport=transport, **kwargs))
    monkeypatch.setattr(d.time, "sleep", lambda _: None)
    with pytest.raises(SourceError, match="HTTP 302"):
        d._s2_get("/paper/search", {"query": "robot"})
    assert len(calls) == 1 and calls[0].url.host == "api.semanticscholar.org"
    assert calls[0].headers["x-api-key"] == "secret-test-key"


@pytest.mark.parametrize("limit", [0, 21, True, 1.5])
def test_bounds_rejected_before_network(limit):
    with pytest.raises(ValueError):
        d.federated_search("robot", limit)
    with pytest.raises(ValueError):
        d.citation_graph("2406.09246", limit=limit)


def test_citation_export_deterministic_with_versions():
    rows = [paper(arxiv_id="2406.09246", version="v1"), paper("arxiv:2406.09246v2", arxiv_id="2406.09246", version="v2")]
    first = d.export_citations(rows)
    second = d.export_citations(list(reversed(rows)))
    assert first["count"] == 2
    assert {i["citation_key"] for i in first["items"]} == {i["citation_key"] for i in second["items"]}
    assert "2406.09246v1" in first["content"] and "2406.09246v2" in first["content"]


def test_bibtex_metadata_cannot_inject_entry_or_command():
    malicious = Paper(id="x\n@misc{evil", title="X }\n@misc{evil, title={pwn}} \\input{secret}%\x00", authors=["A and B {x}"])
    result = d.export_citations([malicious])
    text = result["content"]
    assert result["count"] == 1 and "\n@misc{evil" not in text
    assert "\\input{" not in text and "\\textbackslash{}input" in text
    assert "\\textbraceright{}" in text and "\\%" in text and "\x00" not in text
    assert text.count("{") == text.count("}")
    assert "author = {{A and B" in text


def test_csl_preserves_literals_without_guessing_author_name():
    record = paper(arxiv_id="2406.09246", version="v1", doi="10.1234/R", source_url="https://example.org/r")
    result = d.export_citations([record], "csl-json")
    data = json.loads(result["content"])
    assert data == result["records"]
    assert data[0]["author"] == [{"literal": "Alice Robot"}]
    assert data[0]["issued"] == {"date-parts": [[2024, 6, 13]]}
    assert data[0]["DOI"] == "10.1234/r" and data[0]["archive_location"] == "2406.09246v1"


def test_export_missing_metadata_and_duplicate_handling():
    p = Paper(id="x", title="Only known title", source_url="javascript:alert(1)")
    result = d.export_citations([p, p, {"id": "bad"}])
    assert result["count"] == 1
    assert [i["status"] for i in result["items"]] == ["ok", "duplicate", "error"]
    assert "javascript" not in result["content"] and "year =" not in result["content"]
    assert result["items"][0]["warnings"]


def test_export_has_no_network_dependency(monkeypatch):
    monkeypatch.setattr(d, "get", lambda *args, **kwargs: pytest.fail("Unexpected network"))
    assert d.export_citations([paper()])["count"] == 1


def test_invalid_inputs():
    for call in [lambda: d.federated_search(" "), lambda: d.federated_search("x", providers=[]),
                 lambda: d.federated_search("x", providers=["fake"]),
                 lambda: d.citation_graph("file:///etc/passwd"),
                 lambda: d.citation_graph("2406.09246", direction="forward"),
                 lambda: d.export_citations([], "bibtex"), lambda: d.export_citations([paper()], "ris")]:
        with pytest.raises(ValueError):
            call()
