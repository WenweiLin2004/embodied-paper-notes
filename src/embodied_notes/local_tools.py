"""Bounded local retrieval and explicit, revision-checked annotation editing."""
from __future__ import annotations

import json
from pathlib import Path
import re

from .library import Library, RevisionConflict, atomic_write, digest
from .validation import validate_library


def _query(value: str) -> list[str]:
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ValueError("query must contain 1..500 characters")
    return list(dict.fromkeys(value.casefold().split()))


def _bounds(limit: int, maximum: int = 50, offset: int = 0) -> None:
    if not 1 <= limit <= maximum or offset < 0:
        raise ValueError(f"limit must be 1..{maximum}; offset must be nonnegative")


def _excerpt(text: str, terms: list[str], size: int) -> tuple[str, int]:
    folded = text.casefold()
    positions = [folded.find(term) for term in terms if term in folded]
    start = max(0, min(positions, default=0) - size // 4)
    return text[start:start + size], start


def search_library(root: Path, query: str, tags: list[str] | None = None,
                   coverage: str | None = None, limit: int = 10, offset: int = 0,
                   include_annotations: bool = False) -> dict:
    """Case-insensitive lexical AND search; no embedding or model download."""
    terms = _query(query)
    _bounds(limit, offset=offset)
    if coverage not in {None, "full_text", "abstract", "metadata"}:
        raise ValueError("Unknown coverage")
    matches = []
    for note in Library(root).list_papers():
        if tags and not set(tags).issubset(note.get("tags", [])):
            continue
        if coverage and note.get("coverage") != coverage:
            continue
        fields = {"title": note["title"], "tags": " ".join(note.get("tags", [])),
                  "summary": json.dumps(note["summary"], ensure_ascii=False), "body": note["body"]}
        if include_annotations:
            annotation_path = _annotation_path(root, note["id"])
            fields["annotation"] = annotation_path.read_text(encoding="utf-8-sig") if annotation_path.exists() else ""
        combined = "\n".join(fields.values())
        if not all(term in combined.casefold() for term in terms):
            continue
        matched = [name for name, text in fields.items() if any(t in text.casefold() for t in terms)]
        score = sum(8 if term in note["title"].casefold() else 1 for term in terms)
        excerpt, _ = _excerpt(combined, terms, 600)
        matches.append({"id": note["id"], "title": note["title"], "tags": note.get("tags", []),
                        "coverage": note["coverage"], "revision": note["revision"],
                        "matched_fields": matched, "excerpt": excerpt, "score": score})
    matches.sort(key=lambda x: (-x["score"], x["id"]))
    return {"query": query, "mode": "lexical-and", "total": len(matches),
            "results": matches[offset:offset + limit],
            "next_offset": offset + limit if offset + limit < len(matches) else None}


def read_paper_note(root: Path, paper_id: str, start: int = 0, max_chars: int = 12000) -> dict:
    if start < 0 or not 500 <= max_chars <= 20000:
        raise ValueError("start >= 0 and max_chars 500..20000 required")
    note = Library(root).get_paper(paper_id)
    if note is None:
        raise ValueError("Unknown paper ID")
    text = note["body"]
    return {k: note.get(k) for k in ("id", "title", "paper", "coverage", "tags", "revision")} | {
        "markdown": text[start:start + max_chars], "total_characters": len(text),
        "next_start": start + max_chars if start + max_chars < len(text) else None}


def search_evidence(root: Path, packet_id: str, query: str, limit: int = 6,
                    excerpt_chars: int = 900) -> dict:
    terms = _query(query)
    _bounds(limit, 12)
    if not 100 <= excerpt_chars <= 2000:
        raise ValueError("excerpt_chars must be 100..2000")
    packet = Library(root).load_packet(packet_id)
    hits = []
    for chunk in packet["chunks"]:
        haystack = chunk["section"] + "\n" + chunk["text"]
        if not all(term in haystack.casefold() for term in terms):
            continue
        excerpt, start = _excerpt(chunk["text"], terms, excerpt_chars)
        hits.append({k: chunk.get(k) for k in ("id", "section", "source_url", "page")} | {
            "excerpt": excerpt, "start": start, "characters": len(chunk["text"])})
    return {"packet_id": packet_id, "query": query, "mode": "lexical-and",
            "full_text": packet["full_text"], "hits": hits[:limit], "total": len(hits),
            "truncated": len(hits) > limit,
            "warning": "Search hits do not replace reading methods, evaluation and limitations in context."}


def read_evidence_by_ids(root: Path, packet_id: str, evidence_ids: list[str],
                         start: int = 0, max_chars: int = 6000) -> dict:
    if not 1 <= len(evidence_ids) <= 8 or len(set(evidence_ids)) != len(evidence_ids):
        raise ValueError("Select 1..8 distinct evidence IDs")
    if start < 0 or not 500 <= max_chars <= 12000:
        raise ValueError("start >= 0 and max_chars 500..12000 required")
    packet = Library(root).load_packet(packet_id)
    by_id = {c["id"]: c for c in packet["chunks"]}
    if set(evidence_ids) - by_id.keys():
        raise ValueError("Unknown evidence ID in this packet")
    chunks = []
    for identifier in evidence_ids:
        chunk = by_id[identifier]
        text = chunk["text"]
        chunks.append({**chunk, "text": text[start:start + max_chars], "start": start,
                       "next_start": start + max_chars if start + max_chars < len(text) else None,
                       "total_characters": len(text)})
    return {"packet_id": packet_id, "full_text": packet["full_text"], "chunks": chunks}


def _annotation_path(root: Path, paper_id: str) -> Path:
    lib = Library(root)
    if lib.get_paper(paper_id) is None:
        raise ValueError("Unknown paper ID")
    # Never trust a relative filename supplied by front matter or callers.
    path = lib.annotations_dir / lib.paper_path(paper_id).name
    path.resolve().relative_to(lib.root)
    if path.is_symlink():
        raise ValueError("Annotation symlinks are not editable through MCP")
    path.resolve().relative_to(lib.annotations_dir.resolve())
    return path


def read_annotation(root: Path, paper_id: str, start: int = 0, max_chars: int = 10000) -> dict:
    if start < 0 or not 500 <= max_chars <= 20000:
        raise ValueError("start >= 0 and max_chars 500..20000 required")
    path = _annotation_path(root, paper_id)
    raw = path.read_bytes() if path.exists() else None
    text = raw.decode("utf-8-sig") if raw is not None else ""
    return {"paper_id": paper_id, "content": text[start:start + max_chars], "total_characters": len(text),
            "next_start": start + max_chars if start + max_chars < len(text) else None,
            "revision": digest(raw) if raw is not None else None, "exists": raw is not None}


def update_annotation(root: Path, paper_id: str, content: str, expected_revision: str | None) -> dict:
    """Replace explicitly requested human notes only after reading their revision."""
    if not isinstance(content, str) or len(content) > 100000:
        raise ValueError("Annotation content must be text up to 100000 characters")
    path = _annotation_path(root, paper_id)
    with Library(root)._lock():
        actual = digest(path.read_bytes()) if path.exists() else None
        if actual != expected_revision:
            raise RevisionConflict("Annotation changed; read and merge before updating")
        atomic_write(path, content)
        revision = digest(content)
        if digest(path.read_bytes()) != revision:
            raise OSError("Annotation write verification failed")
    return {"paper_id": paper_id, "revision": revision, "path": str(path)}


def inspect_library(root: Path) -> dict:
    notes = Library(root).list_papers()
    identities: dict[str, list[str]] = {}
    for note in notes:
        paper = note["paper"]
        key = ("doi:" + paper["doi"].lower() if paper.get("doi") else
               "arxiv:" + paper["arxiv_id"] if paper.get("arxiv_id") else note["id"])
        identities.setdefault(key, []).append(note["id"])
    return {"validation": validate_library(root), "paper_count": len(notes),
            "coverage": {c: sum(n["coverage"] == c for n in notes) for c in ("full_text", "abstract", "metadata")},
            "possible_duplicates_or_versions": [{"identity": key, "paper_ids": ids} for key, ids in identities.items() if len(ids) > 1],
            "warning": "Versions and possible duplicates are reported only; no note is deleted or merged."}
