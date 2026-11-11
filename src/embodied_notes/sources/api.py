"""Source adapters shared by all interfaces; credentials are never needed for arXiv."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from bs4 import BeautifulSoup

from ..models import Paper, RetrievedPaper
from .arxiv_ids import arxiv_version_suffix, bare_arxiv_id, parse_arxiv_id
from .client import SourceError, get as _get, validate_url
from .parsing import chunks_for_text, clean, extract_html, extract_pdf

ARXIV_API = "https://export.arxiv.org/api/query"
_ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
CACHE_VERSION = 1


def _arxiv_id(value: str) -> str | None:
    # Preserve the vendored helper exactly; add HTML URLs at this adapter boundary.
    parsed = urlparse(value.strip())
    if parsed.hostname in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        value = re.sub(r"^/(?:html|abs|pdf)/", "", parsed.path).removesuffix(".pdf").rstrip("/")
    result = parse_arxiv_id(value)
    return result.lower() if result else None


def _doi(value: str) -> str | None:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.hostname in {"doi.org", "dx.doi.org", "www.doi.org"}:
        value = unquote(parsed.path.lstrip("/"))
    value = re.sub(r"^doi:\s*", "", value, flags=re.I)
    return value.lower() if _DOI_RE.fullmatch(value) else None


def _parse_arxiv_feed(xml: str) -> list[Paper]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise SourceError("arXiv returned invalid Atom XML.") from exc
    papers = []
    for entry in root.findall("a:entry", _ATOM):
        identifier = _arxiv_id(entry.findtext("a:id", "", _ATOM))
        if not identifier:
            error = clean(entry.findtext("a:summary", "", _ATOM))
            if error:
                raise SourceError(f"arXiv returned an error: {error[:300]}")
            continue
        papers.append(Paper(
            id=f"arxiv:{identifier}",
            title=clean(entry.findtext("a:title", "", _ATOM)),
            authors=[clean(a.findtext("a:name", "", _ATOM)) for a in entry.findall("a:author", _ATOM)],
            abstract=clean(entry.findtext("a:summary", "", _ATOM)),
            source_url=f"https://arxiv.org/abs/{identifier}",
            pdf_url=f"https://arxiv.org/pdf/{identifier}",
            doi=entry.findtext("arxiv:doi", None, _ATOM),
            arxiv_id=bare_arxiv_id(identifier), version=arxiv_version_suffix(identifier),
            published=entry.findtext("a:published", None, _ATOM), provider="arxiv",
        ))
    return papers


def _deduplicate(papers: list[Paper]) -> list[Paper]:
    """Exact identifiers first; retain latest arXiv version within search results."""
    results: dict[str, Paper] = {}
    for paper in papers:
        key = f"arxiv:{paper.arxiv_id}" if paper.arxiv_id else (f"doi:{paper.doi.lower()}" if paper.doi else paper.id)
        previous = results.get(key)
        version = int((paper.version or "v0")[1:]) if paper.arxiv_id else 0
        old_version = int((previous.version or "v0")[1:]) if previous and previous.arxiv_id else -1
        if previous is None or version > old_version:
            results[key] = paper
    return list(results.values())


def _crossref(doi: str) -> Paper:
    try:
        item = _get(f"https://api.crossref.org/works/{quote(doi, safe='')}").json()["message"]
    except (KeyError, ValueError) as exc:
        raise SourceError("Crossref returned invalid metadata.") from exc
    actual = str(item.get("DOI", "")).lower()
    if actual != doi:
        raise SourceError("Crossref metadata does not match the requested DOI.")
    date = item.get("published", {}).get("date-parts", [[]])[0]
    authors = [clean(f"{a.get('given', '')} {a.get('family', '')}") or a.get("name", "") for a in item.get("author", [])]
    return Paper(id=f"doi:{doi}", title=(item.get("title") or [""])[0], authors=authors,
                 abstract=clean(BeautifulSoup(item.get("abstract", ""), "html.parser").get_text(" ")),
                 doi=doi, source_url=f"https://doi.org/{doi}", provider="crossref",
                 published="-".join(str(n).zfill(2) for n in date) or None)


def _page_metadata(url: str, html: str) -> Paper:
    soup = BeautifulSoup(html, "html.parser")

    def meta(name: str) -> str:
        element = soup.find("meta", attrs={"name": re.compile(f"^{re.escape(name)}$", re.I)})
        return clean(str(element.get("content", ""))) if element else ""

    title = meta("citation_title") or meta("dc.title") or (clean(soup.title.get_text()) if soup.title else "")
    doi = _doi(meta("citation_doi") or meta("dc.identifier"))
    authors = [str(x.get("content", "")) for x in soup.find_all("meta", attrs={"name": re.compile("^citation_author$", re.I)})]
    abstract = meta("citation_abstract") or meta("description")
    pdf = meta("citation_pdf_url")
    if pdf:
        from urllib.parse import urljoin
        pdf = validate_url(urljoin(url, pdf))
    return Paper(id=f"doi:{doi}" if doi else "url:" + hashlib.sha256(url.encode()).hexdigest()[:20],
                 title=title, authors=authors, abstract=abstract, source_url=url,
                 pdf_url=pdf or None, doi=doi, published=meta("citation_publication_date") or None,
                 provider="web")


def resolve(url_or_id: str) -> Paper:
    """Resolve arXiv IDs/URLs, DOIs, and public paper pages to canonical metadata."""
    identifier = _arxiv_id(url_or_id)
    if identifier:
        papers = _parse_arxiv_feed(_get(ARXIV_API, params={"id_list": identifier}).text)
        for paper in papers:
            if paper.arxiv_id == bare_arxiv_id(identifier):
                requested = arxiv_version_suffix(identifier)
                if requested and paper.version != requested:
                    raise SourceError(f"Requested {identifier}, but arXiv returned {paper.id}; refusing a version mismatch.")
                return paper
        raise SourceError(f"arXiv did not return the requested paper {identifier}.")
    doi = _doi(url_or_id)
    if doi:
        return _crossref(doi)
    url = validate_url(url_or_id.strip())
    response = _get(url)
    if response.content.startswith(b"%PDF"):
        return Paper(id="url:" + hashlib.sha256(url.encode()).hexdigest()[:20],
                     title=Path(urlparse(url).path).name, source_url=url, pdf_url=url, provider="pdf")
    return _page_metadata(str(response.url), response.text)


def _abstract_result(paper: Paper, warnings: list[str]) -> RetrievedPaper:
    chunks = chunks_for_text(paper.abstract, "Abstract (metadata only)", paper.source_url) if paper.abstract else []
    return RetrievedPaper(paper=paper, chunks=chunks, full_text=False, warnings=warnings, parser="metadata-only")


def _cached(path: Path, paper: Paper) -> RetrievedPaper | None:
    if not path.exists():
        return None
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if envelope.get("cache_version") != CACHE_VERSION:
            return None
        result = RetrievedPaper.model_validate(envelope["result"])
        if result.paper.id == paper.id and result.paper.source_url == paper.source_url and result.full_text:
            return result
    except (ValueError, KeyError, OSError):
        pass
    return None


def _check_response_identity(response, paper: Paper) -> None:
    """Never silently follow an arXiv redirect to another paper or version."""
    if not paper.arxiv_id:
        return
    actual = _arxiv_id(str(response.url))
    if actual and (bare_arxiv_id(actual) != paper.arxiv_id or
                   (paper.version and arxiv_version_suffix(actual) != paper.version)):
        raise SourceError(f"Full-text URL changed paper/version: {response.url}")


def fetch_paper(url_or_id: str, cache_dir: Path, *, pdf_parser: str = "auto") -> RetrievedPaper:
    """Fetch sectioned evidence; explicitly return metadata-only on full-text failure."""
    if pdf_parser not in {"auto", "docling"}:
        raise ValueError("pdf_parser must be 'auto' or 'docling'.")
    paper = resolve(url_or_id)
    cache_dir = Path(cache_dir)
    cache_identity = f"{paper.id}|{paper.source_url}|{paper.pdf_url}|{paper.version}|{pdf_parser}"
    digest = hashlib.sha256(cache_identity.encode()).hexdigest()
    cache_path = cache_dir / f"{digest}.json"
    cached = _cached(cache_path, paper)
    if cached:
        return cached
    warnings: list[str] = []
    if paper.provider == "pdf":
        warnings.append("Imported a direct PDF URL. Title and bibliographic identity have not been independently verified.")
    result: RetrievedPaper | None = None
    if paper.provider == "crossref":
        # Crossref is an authority for metadata, not a full-text service.
        return _abstract_result(paper, ["DOI resolved through Crossref. Full text was not retrieved; import an arXiv, publisher paper-page or public PDF URL to read the paper."])
    html_url = f"https://arxiv.org/html/{paper.arxiv_id}{paper.version or ''}" if paper.arxiv_id else paper.source_url
    if paper.provider != "pdf":
        try:
            response = _get(html_url)
            _check_response_identity(response, paper)
            chunks, complete, notes = extract_html(response.text, html_url)
            warnings.extend(notes)
            if complete:
                result = RetrievedPaper(paper=paper, chunks=chunks, full_text=True, warnings=warnings, parser="html")
        except SourceError as exc:
            warnings.append(f"HTML retrieval unavailable: {exc}")
    if result is None and paper.pdf_url:
        try:
            response = _get(paper.pdf_url)
            _check_response_identity(response, paper)
            if not response.content.startswith(b"%PDF"):
                raise SourceError("The PDF endpoint did not return a PDF document.")
            chunks, complete, notes, parser = extract_pdf(response.content, paper, pdf_parser=pdf_parser)
            warnings.extend(notes)
            if chunks:
                result = RetrievedPaper(paper=paper, chunks=chunks, full_text=complete, warnings=warnings, parser=parser)
        except SourceError as exc:
            warnings.append(f"PDF retrieval unavailable: {exc}")
    if result is None:
        result = _abstract_result(paper, warnings + ["No full text was obtained. Do not infer methods or results from the abstract alone."])
    if result.full_text:
        cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps({"cache_version": CACHE_VERSION, "result": result.model_dump(mode="json")},
                                        ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(cache_path)
    return result


def search(query: str, limit: int = 5, provider: str = "arxiv", *, categories: list[str] | None = None,
           date_from: str | None = None, date_to: str | None = None, sort_by: str = "relevance",
           api_key: str | None = None) -> list[Paper]:
    """Search arXiv (default) or OpenAlex; no credentials are read from disk."""
    if not query.strip():
        raise ValueError("A non-empty query is required.")
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50.")
    for value in (date_from, date_to):
        if value:
            from datetime import date
            date.fromisoformat(value)
    if date_from and date_to and date_from > date_to:
        raise ValueError("date_from must not be after date_to.")
    if provider == "arxiv":
        expression = f"({query})"
        if categories:
            if any(not re.fullmatch(r"[A-Za-z-]+(?:\.[A-Za-z-]+)?", c) for c in categories):
                raise ValueError("Invalid arXiv category.")
            expression += " AND (" + " OR ".join(f"cat:{c}" for c in categories) + ")"
        if date_from or date_to:
            expression += f" AND submittedDate:[{(date_from or '1991-01-01').replace('-', '')}0000 TO {(date_to or '2099-12-31').replace('-', '')}2359]"
        order = {"relevance": "relevance", "date": "submittedDate", "submittedDate": "submittedDate", "updated": "lastUpdatedDate"}.get(sort_by)
        if not order:
            raise ValueError("sort_by must be relevance, date, submittedDate, or updated.")
        response = _get(ARXIV_API, params={"search_query": expression, "start": 0,
                                          "max_results": limit, "sortBy": order, "sortOrder": "descending"})
        return _deduplicate(_parse_arxiv_feed(response.text))[:limit]
    if provider == "openalex":
        params: dict = {"search": query, "per-page": limit}
        filters = []
        if date_from:
            filters.append(f"from_publication_date:{date_from}")
        if date_to:
            filters.append(f"to_publication_date:{date_to}")
        if filters:
            params["filter"] = ",".join(filters)
        if api_key:
            params["api_key"] = api_key
        if sort_by in {"date", "submittedDate", "updated"}:
            params["sort"] = "publication_date:desc"
        elif sort_by != "relevance":
            raise ValueError("Unsupported sort order.")
        if categories:
            raise ValueError("arXiv category filters cannot be applied to OpenAlex.")
        try:
            results = _get("https://api.openalex.org/works", params=params).json()["results"]
        except (KeyError, ValueError) as exc:
            raise SourceError("OpenAlex returned invalid search data.") from exc
        papers = []
        for item in results:
            words = {position: word for word, positions in (item.get("abstract_inverted_index") or {}).items() for position in positions}
            location = item.get("best_oa_location") or item.get("primary_location") or {}
            doi = _doi(item.get("doi") or "")
            papers.append(Paper(id=item["id"], title=item.get("title") or "",
                                authors=[a["author"]["display_name"] for a in item.get("authorships", [])],
                                abstract=" ".join(words[k] for k in sorted(words)),
                                source_url=location.get("landing_page_url") or item["id"],
                                pdf_url=location.get("pdf_url"), doi=doi,
                                published=item.get("publication_date"), provider="openalex"))
        return _deduplicate(papers)[:limit]
    raise ValueError("provider must be 'arxiv' or 'openalex'.")
