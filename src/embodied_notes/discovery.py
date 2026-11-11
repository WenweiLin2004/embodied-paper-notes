"""Bounded metadata discovery and deterministic citation export; no LLM calls.

BibTeX escaping is adapted from blazickjp/arxiv-mcp-server (Apache-2.0).
See third_party/arxiv-citation-format/PROVENANCE.md for exact provenance.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import hashlib
import json
import os
import re
import threading
import time
import unicodedata
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup
import httpx

from .models import Paper
from .sources import search as source_search
from .sources.api import _arxiv_id, _doi
from .sources.arxiv_ids import arxiv_version_suffix, bare_arxiv_id
from .sources.client import SourceError, get

PROVIDERS = ("arxiv", "openalex", "crossref", "semantic_scholar")
S2_ROOT = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = "title,authors,year,abstract,externalIds,url,openAccessPdf,publicationDate"
MAX_LIMIT = 20
_S2_LOCK = threading.Lock()
_S2_LAST_REQUEST = 0.0


def _check_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError("limit must be an integer between 1 and 20.")


def _query(query: str) -> str:
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        raise ValueError("query must contain 1..1000 characters.")
    return query.strip()


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _s2_get(path: str, params: dict) -> httpx.Response:
    """Send credentials only to the fixed S2 origin; never follow its redirects."""
    global _S2_LAST_REQUEST
    if not path.startswith("/paper/") or "?" in path or "#" in path:
        raise ValueError("Invalid Semantic Scholar endpoint.")
    with _S2_LOCK:
        wait = 1.0 - (time.monotonic() - _S2_LAST_REQUEST)
        if wait > 0:
            time.sleep(wait)
        _S2_LAST_REQUEST = time.monotonic()
    url = S2_ROOT + path
    key = os.environ.get("S2_API_KEY", "").strip()
    if not key:
        return get(url, params=params)
    # An authenticated request has no retry/downgrade: 403 and 429 stay visible.
    try:
        with httpx.Client(timeout=httpx.Timeout(20, connect=10), follow_redirects=False,
                          headers={"x-api-key": key, "User-Agent": "embodied-paper-notes/0.1"}) as client:
            with client.stream("GET", url, params=params) as response:
                response.raise_for_status()
                data = bytearray()
                for part in response.iter_bytes():
                    data.extend(part)
                    if len(data) > 2 * 1024 * 1024:
                        raise SourceError("Semantic Scholar metadata exceeds the 2 MB response limit.")
                return httpx.Response(response.status_code, content=bytes(data), request=response.request)
    except httpx.HTTPStatusError as exc:
        raise SourceError(f"Semantic Scholar returned HTTP {exc.response.status_code}.") from exc
    except httpx.TransportError as exc:
        raise SourceError(f"Semantic Scholar request failed ({type(exc).__name__}).") from exc


def _json(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError as exc:
        raise SourceError("Provider returned invalid JSON metadata.") from exc
    if not isinstance(data, dict):
        raise SourceError("Provider returned an unexpected metadata response.")
    return data


def _s2_paper(item: dict) -> Paper:
    if not item.get("paperId"):
        raise ValueError("Semantic Scholar record has no paper ID.")
    ids = item.get("externalIds") or {}
    arxiv = _arxiv_id(str(ids.get("ArXiv") or ""))
    doi = _doi(str(ids.get("DOI") or ""))
    published = item.get("publicationDate") or (str(item["year"]) if item.get("year") else None)
    return Paper(id="semantic_scholar:" + str(item["paperId"]), title=_text(item.get("title")),
                 authors=[_text(a.get("name")) for a in item.get("authors") or []],
                 abstract=_text(item.get("abstract")),
                 source_url=item.get("url") or "https://www.semanticscholar.org/paper/" + str(item["paperId"]),
                 pdf_url=(item.get("openAccessPdf") or {}).get("url"), doi=doi,
                 arxiv_id=bare_arxiv_id(arxiv) if arxiv else None,
                 version=arxiv_version_suffix(arxiv) if arxiv else None,
                 published=published, provider="semantic_scholar")


def _crossref_paper(item: dict) -> Paper:
    doi = _doi(str(item.get("DOI") or ""))
    if not doi:
        raise ValueError("Crossref record has no valid DOI.")
    date_parts = (item.get("published", {}).get("date-parts") or [[]])[0]
    return Paper(id=f"doi:{doi}", title=_text((item.get("title") or [""])[0]),
                 authors=[_text(a.get("name") or f"{a.get('given', '')} {a.get('family', '')}") for a in item.get("author") or []],
                 abstract=_text(BeautifulSoup(item.get("abstract") or "", "html.parser").get_text(" ")),
                 source_url=f"https://doi.org/{doi}", doi=doi,
                 published="-".join(str(x).zfill(2) for x in date_parts) or None, provider="crossref")


def search_provider(query: str, provider: str = "arxiv", limit: int = 5) -> list[Paper]:
    """Search one metadata provider. Network/schema failures raise SourceError."""
    query = _query(query)
    _check_limit(limit)
    if provider in {"arxiv", "openalex"}:
        return source_search(query, limit=limit, provider=provider)
    if provider == "crossref":
        data = _json(get("https://api.crossref.org/works", params={"query.bibliographic": query, "rows": limit}))
        message = data.get("message")
        items = message.get("items") if isinstance(message, dict) else None
        parser = _crossref_paper
    elif provider == "semantic_scholar":
        data = _json(_s2_get("/paper/search", {"query": query, "limit": limit, "fields": S2_FIELDS}))
        items = data.get("data")
        parser = _s2_paper
    else:
        raise ValueError("Unknown provider. Choose arxiv, openalex, crossref, or semantic_scholar.")
    if not isinstance(items, list):
        raise SourceError(f"{provider} response has no paper list.")
    try:
        return [parser(item) for item in items[:limit]]
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise SourceError(f"{provider} returned malformed paper metadata ({type(exc).__name__}).") from exc


def _error(exc: Exception) -> dict:
    # Never include a configured key in an error, including errors from test adapters.
    message = str(exc)
    secret = os.environ.get("S2_API_KEY", "")
    if secret:
        message = message.replace(secret, "[redacted]")
    match = re.search(r"HTTP\s+(\d{3})", message)
    code = int(match.group(1)) if match else None
    status = "rate_limited" if code == 429 else "forbidden" if code == 403 else "error"
    warnings = []
    if code == 429:
        warnings.append("Provider rate limit reached. Retry later; an S2_API_KEY may improve Semantic Scholar reliability.")
    if code == 403:
        warnings.append("Access was denied. Check the provider/key; this is not an empty search result.")
    return {"status": status, "count": 0, "error": message[:600], "http_status": code, "warnings": warnings}


def _identity(paper: Paper) -> tuple[str | None, str | None, str | None]:
    candidates = [value for value in (_arxiv_id(paper.arxiv_id or ""), _arxiv_id(paper.id),
                                      _arxiv_id(paper.source_url)) if value]
    arxiv = candidates[0] if candidates else None
    versions = [arxiv_version_suffix(value) for value in candidates
                if arxiv and bare_arxiv_id(value) == bare_arxiv_id(arxiv) and arxiv_version_suffix(value)]
    version = paper.version or (versions[0] if versions else None)
    return _doi(paper.doi or ""), bare_arxiv_id(arxiv) if arxiv else None, version


def _merge_papers(papers: list[Paper]) -> tuple[list[dict], list[str]]:
    """Merge stable IDs, preserving conflicting/ambiguous versions and provenance."""
    identities = [_identity(p) for p in papers]
    versions: dict[str, set[str]] = {}
    for doi, arxiv, version in identities:
        if version:
            for key in (f"doi:{doi}" if doi else None, f"arxiv:{arxiv}" if arxiv else None):
                if key:
                    versions.setdefault(key, set()).add(version)
    groups: list[dict] = []
    warnings: set[str] = set()
    # Exact versions are preferred as canonical records over versionless metadata.
    order = sorted(range(len(papers)), key=lambda i: (identities[i][2] is None,
                                                      -sum(bool(x) for x in identities[i][:2]), i))
    for index in order:
        paper = papers[index]
        doi, arxiv, version = identities[index]
        paper = paper.model_copy(update={"arxiv_id": arxiv, "version": version})
        source = {"provider": paper.provider, "id": paper.id, "url": paper.source_url}
        match = None
        for group in groups:
            old_doi, old_arxiv, old_version = group["identity"]
            same = (doi and old_doi == doi) or (arxiv and old_arxiv == arxiv) or paper.id == group["paper"].id
            if not same:
                continue
            if ((doi and old_doi and doi != old_doi) or (arxiv and old_arxiv and arxiv != old_arxiv)):
                warnings.add("Conflicting DOI/arXiv identities were kept separate; review upstream metadata.")
                continue
            if version and old_version and version != old_version:
                continue
            if bool(version) != bool(old_version):
                keys = [f"doi:{doi or old_doi}", f"arxiv:{arxiv or old_arxiv}"]
                if any(len(versions.get(key, set())) > 1 for key in keys):
                    warnings.add("Versionless metadata was kept separate where multiple known arXiv versions exist.")
                    continue
            match = group
            break
        if match is None:
            groups.append({"paper": paper, "identity": (doi, arxiv, version), "sources": [source], "rank": index})
        else:
            if source not in match["sources"]:
                match["sources"].append(source)
            # Merge identifiers only. Do not inject a versionless abstract into a versioned record.
            existing = match["paper"]
            match["paper"] = existing.model_copy(update={"doi": existing.doi or doi,
                                                        "arxiv_id": existing.arxiv_id or arxiv})
            match["identity"] = (match["identity"][0] or doi, match["identity"][1] or arxiv, match["identity"][2])
            match["rank"] = min(match["rank"], index)
    output = []
    for group in sorted(groups, key=lambda x: x["rank"]):
        record = group["paper"].model_dump(mode="json")
        record["sources"] = group["sources"]
        record["abstract_truncated"] = len(record["abstract"]) > 2000
        record["abstract"] = record["abstract"][:2000]
        output.append(record)
    return output, sorted(warnings)


def federated_search(query: str, limit_per_provider: int = 5, providers: list[str] | None = None) -> dict:
    """Concurrent metadata search with explicit partial failures, at most 80 records."""
    query = _query(query)
    _check_limit(limit_per_provider)
    chosen = list(dict.fromkeys(providers if providers is not None else ["arxiv", "openalex"]))
    if not chosen or len(chosen) > len(PROVIDERS) or any(p not in PROVIDERS for p in chosen):
        raise ValueError("providers must select 1..4 supported providers.")
    statuses, found = {}, {}
    with ThreadPoolExecutor(max_workers=len(chosen)) as pool:
        futures = {pool.submit(search_provider, query, p, limit_per_provider): p for p in chosen}
        for future in as_completed(futures):
            provider = futures[future]
            try:
                papers = future.result()
                found[provider] = papers[:limit_per_provider]
                statuses[provider] = {"status": "ok", "count": len(found[provider]), "warnings": [],
                                      "limit_reached": len(papers) >= limit_per_provider}
            except Exception as exc:
                statuses[provider] = _error(exc)
                found[provider] = []
    records, warnings = _merge_papers([p for name in chosen for p in found[name]])
    successes = sum(statuses[p]["status"] == "ok" for p in chosen)
    return {"query": query, "metadata_only": True,
            "status": "ok" if successes == len(chosen) else "partial" if successes else "error",
            "providers": {p: statuses[p] for p in chosen}, "papers": records, "total": len(records),
            "truncated": any(statuses[p].get("limit_reached", False) for p in chosen),
            "warnings": warnings + ["Results contain metadata only; abstract snippets are capped at 2,000 characters. No full paper was read."]}


def _graph_identifier(identifier: str) -> tuple[str, list[str]]:
    if not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 1000:
        raise ValueError("identifier must contain 1..1000 characters.")
    value = identifier.strip()
    arxiv = _arxiv_id(value)
    if arxiv:
        warning = ["Semantic Scholar's graph is work-level, not specific to the requested arXiv version."] if arxiv_version_suffix(arxiv) else []
        return "ARXIV:" + bare_arxiv_id(arxiv), warning
    doi = _doi(value)
    if doi:
        return "DOI:" + doi, []
    if value.lower().startswith("semantic_scholar:"):
        value = value.split(":", 1)[1]
    parsed = urlparse(value)
    if parsed.hostname in {"semanticscholar.org", "www.semanticscholar.org"}:
        value = parsed.path.rstrip("/").split("/")[-1]
    if re.fullmatch(r"[0-9a-fA-F]{40}", value):
        return value.lower(), []
    if re.fullmatch(r"CorpusId:\d+", value, re.I):
        return "CorpusId:" + value.split(":", 1)[1], []
    raise ValueError("Use an arXiv ID, DOI, Semantic Scholar paper ID/URL, or CorpusId.")


def citation_graph(identifier: str, direction: str = "both", limit: int = 10) -> dict:
    """Read one bounded page per direction; references point out, citations point in."""
    _check_limit(limit)
    if direction not in {"both", "references", "citations"}:
        raise ValueError("direction must be 'both', 'references', or 'citations'.")
    normalized, warnings = _graph_identifier(identifier)
    selected = ["references", "citations"] if direction == "both" else [direction]
    directions = {}
    for edge in selected:
        try:
            data = _json(_s2_get(f"/paper/{quote(normalized, safe='')}/{edge}", {"limit": limit, "fields": S2_FIELDS}))
            rows = data.get("data")
            if not isinstance(rows, list):
                raise SourceError("Semantic Scholar graph response has no edge list.")
            field = "citedPaper" if edge == "references" else "citingPaper"
            papers, skipped = [], 0
            for row in rows[:limit]:
                try:
                    paper = _s2_paper(row.get(field) or {}).model_dump(mode="json")
                    paper["abstract_truncated"] = len(paper["abstract"]) > 2000
                    paper["abstract"] = paper["abstract"][:2000]
                    papers.append(paper)
                except (ValueError, AttributeError, TypeError):
                    skipped += 1
            notes = [f"{skipped} edges lacked valid paper metadata and were omitted."] if skipped else []
            directions[edge] = {"status": "ok", "count": len(papers), "papers": papers,
                                "next_offset": data.get("next"), "truncated": data.get("next") is not None,
                                "warnings": notes}
        except Exception as exc:
            directions[edge] = _error(exc) | {"papers": [], "next_offset": None, "truncated": False}
    successes = sum(x["status"] == "ok" for x in directions.values())
    return {"identifier": identifier, "resolved_identifier": normalized, "provider": "semantic_scholar",
            "metadata_only": True, "status": "ok" if successes == len(selected) else "partial" if successes else "error",
            "directions": directions, "warnings": warnings + ["Citation edges are metadata, not evidence that a paper supports or contradicts another. Missing graph entries do not prove absence."]}


# Adapted from upstream _BIBTEX_REPLACEMENTS/_bibtex_escape. Single-pass mapping
# avoids sentinel collisions; named brace commands cannot alter BibTeX nesting.
_BIBTEX_ESCAPES = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
                   "#": r"\#", "_": r"\_", "{": r"\textbraceleft{}", "}": r"\textbraceright{}",
                   "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def _bibtex_escape(value: str) -> str:
    value = _text(re.sub(r"[\x00-\x1f\x7f]", " ", value))
    return "".join(_BIBTEX_ESCAPES.get(char, char) for char in value)


def _date_parts(published: str | None) -> list[int] | None:
    if not published:
        return None
    match = re.match(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?(?:T.*)?$", published)
    if not match:
        return None
    values = [int(v) for v in match.groups() if v is not None]
    try:
        date(values[0], values[1] if len(values) > 1 else 1, values[2] if len(values) > 2 else 1)
    except ValueError:
        return None
    return values


def _citation_key(paper: Paper) -> str:
    author = paper.authors[0].split()[-1] if paper.authors and paper.authors[0].split() else "paper"
    ascii_name = unicodedata.normalize("NFKD", author).encode("ascii", "ignore").decode("ascii")
    prefix = re.sub(r"[^A-Za-z0-9]", "", ascii_name).lower()[:24] or "paper"
    year = (_date_parts(paper.published) or [""])[0]
    identity = f"{paper.id}|{paper.arxiv_id}|{paper.version}"
    return f"{prefix}{year}_{hashlib.sha256(identity.encode()).hexdigest()[:10]}"


def export_citations(papers: list[Paper | dict], format: str = "bibtex") -> dict:
    """Export supplied metadata only. Never invent dates, author splits or venues."""
    if format not in {"bibtex", "csl-json"}:
        raise ValueError("format must be 'bibtex' or 'csl-json'.")
    if not isinstance(papers, list) or not 1 <= len(papers) <= 100:
        raise ValueError("Provide 1..100 papers.")
    entries, records, items, seen = [], [], [], set()
    for value in papers:
        paper_id = str(value.id if isinstance(value, Paper) else value.get("id", "")) if isinstance(value, (Paper, dict)) else ""
        try:
            paper = value if isinstance(value, Paper) else Paper.model_validate(value)
            if not paper.id.strip() or not paper.title.strip():
                raise ValueError("A paper ID and title are required.")
            if len(paper.title) > 10000 or len(paper.id) > 1000 or len(paper.authors) > 200 or any(len(a) > 500 for a in paper.authors):
                raise ValueError("Citation metadata exceeds field limits.")
            identity = (paper.id, paper.arxiv_id, paper.version)
            key = _citation_key(paper)
            if identity in seen:
                items.append({"paper_id": paper.id, "citation_key": key, "status": "duplicate", "warnings": []})
                continue
            seen.add(identity)
            warnings = []
            dates = _date_parts(paper.published)
            if not dates:
                warnings.append("Publication date unavailable or invalid; omitted.")
            if not paper.authors:
                warnings.append("Authors unavailable; omitted.")
            doi = _doi(paper.doi or "")
            if paper.doi and not doi:
                warnings.append("Invalid DOI omitted.")
            url = paper.source_url if urlparse(paper.source_url).scheme in {"http", "https"} and urlparse(paper.source_url).netloc else ""
            if paper.source_url and not url:
                warnings.append("Non-HTTP(S) source URL omitted.")
            _, arxiv, version = _identity(paper)
            if version and not re.fullmatch(r"v[1-9]\d*", version):
                raise ValueError("Invalid arXiv version; refusing to export a misleading identifier.")
            eprint = arxiv + (version or "") if arxiv else None
            fields = [("title", _bibtex_escape(paper.title))]
            if paper.authors:
                fields.append(("author", " and ".join("{" + _bibtex_escape(a) + "}" for a in paper.authors)))
            if dates:
                fields.append(("year", str(dates[0])))
            if doi:
                fields.append(("doi", _bibtex_escape(doi)))
            if eprint:
                fields.extend([("eprint", _bibtex_escape(eprint)), ("archivePrefix", "arXiv")])
            if url:
                fields.append(("url", _bibtex_escape(url)))
            entries.append("@misc{" + key + ",\n" + ",\n".join(f"  {name} = {{{text}}}" for name, text in fields) + "\n}")
            record = {"id": key, "type": "article", "title": paper.title}
            if paper.authors:
                record["author"] = [{"literal": name} for name in paper.authors]
            if dates:
                record["issued"] = {"date-parts": [dates]}
            if doi:
                record["DOI"] = doi
            if url:
                record["URL"] = url
            if eprint:
                record["archive"] = "arXiv"
                record["archive_location"] = eprint
                if version:
                    record["version"] = version
            records.append(record)
            items.append({"paper_id": paper.id, "citation_key": key, "status": "ok", "warnings": warnings})
        except (ValueError, TypeError, AttributeError) as exc:
            items.append({"paper_id": paper_id, "status": "error", "error": str(exc)[:400], "warnings": []})
    content = "\n\n".join(entries) + ("\n" if entries else "") if format == "bibtex" else json.dumps(records, ensure_ascii=False, indent=2)
    result = {"format": format, "content": content, "items": items, "count": len(records),
              "warnings": ["Rendered deterministically from supplied metadata; no provider was contacted. Author names are preserved literally and missing bibliographic fields are not inferred."]}
    if format == "csl-json":
        result["records"] = records
    return result
