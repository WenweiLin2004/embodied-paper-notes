# Metadata discovery and citation export

These operations do not read full papers, generate model summaries, write notes,
change a library, or push Git commits. Search candidates must pass through the
normal evidence ingestion workflow before a method/result claim can be saved.

## Python interface

```python
from embodied_notes.discovery import (
    search_provider, federated_search, citation_graph, export_citations,
)

papers = search_provider("vision language action", provider="crossref", limit=5)
results = federated_search("vision language action")
graph = citation_graph("2406.09246v1", direction="both", limit=10)
citations = export_citations(papers, format="bibtex")
```

`search_provider` supports `arxiv`, `openalex`, `crossref`, and
`semantic_scholar`, with 1–20 results per request. A bad query/provider/limit raises
`ValueError`; provider network or schema errors raise `SourceError`.

`federated_search` defaults to arXiv and OpenAlex. Optional providers are selected
with `providers=["arxiv", "openalex", "crossref", "semantic_scholar"]`. Providers run
concurrently. The result contains `status` (`ok`, `partial`, or `error`), each
provider's status/count/error/warnings, and merged `papers`. Each paper keeps
`sources` with the contributing provider, original record ID, and source URL.
Abstracts are capped at 2,000 characters and marked `abstract_truncated`.
`truncated=true` means at least one provider filled the requested result budget;
it is not a claim that a known total was exhaustively counted.

Deduplication uses DOI/arXiv/provider identifiers, not fuzzy title matching. Known
arXiv versions remain separate. Versionless metadata stays separate when several
known versions match. Missing exact-version abstracts are not filled from a
versionless record. Conflicting DOI/arXiv identifiers remain separate with a warning.
Without a shared identifier, potentially related records deliberately remain apart.

## Citation graph

`citation_graph` accepts arXiv IDs/URLs, DOI values/URLs, Semantic Scholar paper
IDs/URLs, and `CorpusId:...`. `direction` is `references`, `citations`, or `both`;
the limit is 1–20 per direction. References point from the requested work to works
it cites; citations point from other works to the requested work. One page per
direction is returned, with `next_offset` and `truncated` when the API exposes more.
This is not a recursive graph crawl. The graph is work-level; an arXiv version is
preserved in the caller's input but stripped from the graph lookup with a warning.

Semantic Scholar anonymous access may be throttled. Optionally set `S2_API_KEY` in
the local process environment. The authenticated transport sends it only in the
`x-api-key` header to `https://api.semanticscholar.org`, follows no redirects, and
does not silently retry without the key. HTTP 429/403 remain explicit
`rate_limited`/`forbidden` statuses rather than successful empty results. No key is
written to output or files. The shared source client handles anonymous requests.

## Citation output

`export_citations` accepts 1–100 `Paper` models or dictionaries and supports
`bibtex` and `csl-json`. It returns `content`, per-item outcomes, and `count`;
CSL-JSON also returns `records`. It makes no network or model calls. Thus an
export is only as authoritative as the supplied metadata.

Unknown years, authors, and URLs are omitted and reported. Venue, issue, page range,
and peer-review status are never inferred. BibTeX uses `@misc` because the common
Paper model does not establish publication type. CSL uses generic `article`;
author names are preserved as literal strings rather than guessing family/given
name boundaries. Versioned arXiv identifiers survive both formats. Citation keys
contain a stable identity digest; identical inputs are deterministic and duplicate
identities are reported. Field values are escaped to prevent BibTeX structure or
TeX-command injection. JSON serialization preserves strings without interpolation.

## Sources and reuse

- [Semantic Scholar Graph API](https://api.semanticscholar.org/api-docs/graph):
  search, citations/references endpoints and their field selection.
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/):
  bibliographic queries and deposited DOI metadata.
- [arxiv-mcp-server citation exporter at the reviewed commit](https://github.com/blazickjp/arxiv-mcp-server/blob/572e301bb3198962c025d5ed5e14becb86868daa/src/arxiv_mcp_server/tools/export_citations.py):
  small BibTeX escaping adaptation, Apache-2.0, retained license and changes in
  `third_party/arxiv-citation-format/`.
- [arxiv-mcp-server citation graph at the reviewed commit](https://github.com/blazickjp/arxiv-mcp-server/blob/572e301bb3198962c025d5ed5e14becb86868daa/src/arxiv_mcp_server/tools/citation_graph.py):
  design reference only; the bounded endpoint adapters here are original code.

Offline tests use simulated provider responses for partial failures, rate limits,
version conflicts, credential-safe redirects, pagination, deterministic output,
and hostile citation field strings. Successful offline tests do not establish
that an upstream provider is currently reachable or that its metadata is complete.
