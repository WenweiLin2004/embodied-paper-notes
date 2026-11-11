"""Deterministic evidence extraction. A landing-page abstract is not full text."""
from __future__ import annotations

import hashlib
import re

from bs4 import BeautifulSoup

from ..models import EvidenceChunk, Paper

CHUNK_CHARS = 6000
MAX_TEXT_CHARS = 600_000


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def chunks_for_text(text: str, section: str, source_url: str, *, page: int | None = None) -> list[EvidenceChunk]:
    """Bound each chunk, preserving exact text spans and stable content-derived IDs."""
    text = text.strip()
    chunks = []
    while text:
        end = min(len(text), CHUNK_CHARS)
        if end < len(text):
            split = text.rfind(" ", max(0, end - 500), end)
            if split > 0:
                end = split
        part, text = text[:end].strip(), text[end:].lstrip()
        digest = hashlib.sha256(f"{source_url}|{section}|{page}|{part}".encode()).hexdigest()[:16]
        chunks.append(EvidenceChunk(id=f"ev-{digest}", section=section, text=part,
                                    source_url=source_url, page=page))
    return chunks


def extract_html(html: str, source_url: str) -> tuple[list[EvidenceChunk], bool, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    for math in soup.select("math[alttext]"):
        math.replace_with(" $" + str(math.get("alttext", "")) + "$ ")
    for tag in soup.select("script, style, nav, footer, header, .ltx_bibliography, .ltx_page_footer, .ltx_page_header"):
        tag.decompose()
    article = soup.select_one("article.ltx_document, article, .ltx_document, main")
    if article is None:
        return [], False, ["No structured article body found; only metadata is available."]
    chunks: list[EvidenceChunk] = []
    section, paragraphs, total, truncated = "Body", [], 0, False
    meaningful_headings = []

    def flush() -> None:
        if paragraphs:
            chunks.extend(chunks_for_text("\n\n".join(paragraphs), section, source_url))
            paragraphs.clear()

    for element in article.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "table", "figcaption", "pre"]):
        # Tables and captions often contain p tags; avoid counting nested text twice.
        if element.find_parent(["p", "table", "figcaption", "pre"]) is not None:
            continue
        value = clean(element.get_text(" ", strip=True))
        if not value:
            continue
        if element.name.startswith("h"):
            flush()
            section = value
            if element.name != "h1" and not re.search(r"abstract|references|bibliography|摘要", value, re.I):
                meaningful_headings.append(value)
        else:
            if total + len(value) > MAX_TEXT_CHARS:
                truncated = True
                break
            paragraphs.append(value)
            total += len(value)
    flush()
    has_body = bool(meaningful_headings) and total >= 800
    warnings = []
    if not has_body:
        warnings.append("HTML lacks sufficient sectioned full text; it may be an abstract or landing page.")
    if truncated:
        warnings.append("Article exceeds the 600,000 character extraction limit; evidence is incomplete.")
    return chunks, has_body and not truncated, warnings


def _extract_docling(content: bytes, paper: Paper) -> tuple[list[EvidenceChunk], bool, list[str], str]:
    """Run Docling only when explicitly selected; it may download model weights."""
    try:
        from io import BytesIO
        from docling.datamodel.base_models import DocumentStream
        from docling.document_converter import DocumentConverter
    except ImportError:
        return [], False, ["Docling was requested but is not installed. Install embodied-paper-notes[pdf]."], "docling"
    try:
        result = DocumentConverter().convert(DocumentStream(name="paper.pdf", stream=BytesIO(content)))
        document = result.document
        status = str(getattr(result.status, "value", result.status)).lower()
        section, chunks, total, truncated = "Body", [], 0, False
        for item, _ in document.iterate_items():
            label = str(getattr(item.label, "value", item.label)).lower()
            if label in {"page_header", "page_footer"}:
                continue
            text = getattr(item, "text", "")
            if label in {"title", "section_header"}:
                section = clean(text) or section
                continue
            if label == "table" and hasattr(item, "export_to_markdown"):
                text = item.export_to_markdown(doc=document)
            if not text:
                continue
            total += len(text)
            if total > MAX_TEXT_CHARS:
                truncated = True
                break
            provenance = getattr(item, "prov", []) or []
            page = provenance[0].page_no if provenance else None
            chunks.extend(chunks_for_text(text, section, paper.pdf_url or paper.source_url, page=page))
        complete = status == "success" and total >= 800 and not truncated
        warnings = ["Docling extraction may still need visual checking of equations, tables and figures."]
        if truncated:
            warnings.append("Docling text exceeds the 600,000 character limit; evidence is incomplete.")
        if not complete:
            warnings.append(f"Docling conversion is incomplete or has insufficient text (status={status}).")
        return chunks, complete, warnings, "docling"
    except Exception as exc:
        return [], False, [f"Docling conversion failed ({type(exc).__name__}); check installation and model availability."], "docling"


def extract_pdf(content: bytes, paper: Paper, *, pdf_parser: str = "auto") -> tuple[list[EvidenceChunk], bool, list[str], str]:
    """Optional local PDF extraction; no OCR and no automatic heavy model downloads."""
    if pdf_parser == "docling":
        return _extract_docling(content, paper)
    if pdf_parser != "auto":
        raise ValueError("pdf_parser must be 'auto' or 'docling'.")
    pages: list[str] = []
    parser = ""
    try:
        import pymupdf
        parser = "pymupdf"
        with pymupdf.open(stream=content, filetype="pdf") as document:
            pages = [page.get_text(sort=True) for page in document]
    except ImportError:
        try:
            from pypdf import PdfReader
            from io import BytesIO
            parser = "pypdf"
            pages = [page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages]
        except ImportError:
            return [], False, ["PDF found, but no PDF parser installed. Install pypdf or select the Docling extra explicitly."], "metadata-only"
        except Exception as exc:
            return [], False, [f"PDF could not be parsed ({type(exc).__name__})."], parser or "metadata-only"
    except Exception as exc:
        return [], False, [f"PDF could not be parsed ({type(exc).__name__})."], parser or "metadata-only"
    chunks: list[EvidenceChunk] = []
    total = 0
    for index, page_text in enumerate(pages, 1):
        total += len(page_text)
        if total > MAX_TEXT_CHARS:
            return chunks, False, ["PDF exceeds the 600,000 character extraction limit; evidence is incomplete."], parser
        chunks.extend(chunks_for_text(page_text, f"Page {index}", paper.pdf_url or paper.source_url, page=index))
    empty_pages = sum(len(clean(p)) < 30 for p in pages)
    complete = total >= 800 and empty_pages == 0
    warnings = ["PDF reading order, equations and tables may require visual verification."]
    if not complete:
        warnings.append("PDF contains missing or insufficient extractable text; OCR may be needed.")
    return chunks, complete, warnings, parser
