"""MCP tools operate on one explicitly selected local library."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .paths import library_root, within


def create_server(root: Path) -> FastMCP:
    from .library import Library
    from .sources import fetch_paper, resolve, search
    from .research import prepare, compose
    from .validation import validate_library

    server = FastMCP("embodied-notes", instructions="Evidence-grounded local paper notes and topic research. Read every relevant evidence section before writing. No git push is performed by tools.")
    lib = Library(root)

    @server.tool()
    def resolve_paper(url: str) -> dict:
        """Resolve arXiv ID, paper URL or DOI into authoritative metadata."""
        return resolve(url).model_dump()

    @server.tool()
    def search_papers(query: str, limit: int = 5, provider: str = "arxiv") -> list[dict]:
        """External paper discovery. Results are metadata, not evidence of full reading."""
        if not 1 <= limit <= 50:
            raise ValueError("limit must be 1..50")
        return [p.model_dump() for p in search(query, limit=limit, provider=provider)]

    @server.tool()
    def prepare_paper(url: str, pdf_parser: str = "auto") -> dict:
        """Fetch/cache original paper and prepare an immutable evidence packet; no note is published."""
        packet = lib.prepare(fetch_paper(url, cache_dir=root / ".cache" / "epn" / "sources", pdf_parser=pdf_parser))
        return {k: v for k, v in packet.items() if k != "chunks"} | {"evidence_count": len(packet["chunks"]),
                "outline": [{"id": c["id"], "section": c["section"], "characters": len(c["text"])} for c in packet["chunks"]]}

    def packet_path(packet_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", packet_id):
            raise ValueError("Invalid packet ID")
        return within(root, root / ".cache" / "epn" / "packets" / f"{packet_id}.json")

    @server.tool()
    def read_evidence(packet_id: str, start: int = 0, limit: int = 4) -> dict:
        """Read bounded paper chunks by offset. Follow next_start until needed sections are covered."""
        if start < 0 or not 1 <= limit <= 10:
            raise ValueError("start >= 0 and limit 1..10 required")
        packet = json.loads(packet_path(packet_id).read_text(encoding="utf-8"))
        chunks = packet["chunks"]
        selected = chunks[start:start + limit]
        return {"packet_id": packet_id, "chunks": selected, "total": len(chunks),
                "next_start": start + len(selected) if start + len(selected) < len(chunks) else None,
                "full_text": packet["full_text"], "warnings": packet.get("warnings", [])}

    @server.tool()
    def commit_paper_summary(packet_id: str, summary: dict, expected_revision: str | None = None) -> dict:
        """Validate cited claims and taxonomy, then write a generated note without changing human annotations."""
        return lib.commit_summary(packet_path(packet_id), summary, expected_revision)

    @server.tool()
    def list_library(limit: int = 30) -> list[dict]:
        """List saved paper notes; use their stable paper IDs in a research packet."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be 1..100")
        return [{k: p.get(k) for k in ("id", "title", "coverage", "tags", "revision")} for p in lib.list_papers()[:limit]]

    @server.tool()
    def prepare_research(topic: str, paper_ids: list[str], strategy: dict | None = None) -> dict:
        """Prepare a topic comparison from selected saved notes and their evidence."""
        if not 1 <= len(paper_ids) <= 30:
            raise ValueError("Select 1..30 saved papers")
        papers = [lib.get_paper(i) for i in paper_ids]
        if any(p is None for p in papers):
            raise ValueError("Unknown paper ID; select saved papers from list_library")
        packet = prepare(root, topic, papers, strategy)
        return {k: v for k, v in packet.items() if k != "notes"} | {
            "notes": [{k: n.get(k) for k in ("id", "title", "coverage", "revision")} for n in packet["notes"]],
            "next_action": "Use read_research_note for each source before synthesis"}

    @server.tool()
    def read_research_note(packet_id: str, paper_id: str) -> dict:
        """Read a selected source's summary and evidence from the frozen research packet."""
        from .research import load_packet
        packet = load_packet(root, packet_id)
        for note in packet["notes"]:
            if note["id"] == paper_id:
                return note
        raise ValueError("Paper not selected in this research packet")

    @server.tool()
    def commit_research(payload: dict) -> dict:
        """Write a research report after validating every paper/evidence citation."""
        return compose(root, payload)

    @server.tool()
    def check_library() -> dict:
        """Check saved note structure, metadata, evidence records, and links."""
        return validate_library(root)

    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    args = parser.parse_args()
    create_server(library_root(args.root)).run(transport="stdio")


if __name__ == "__main__":
    main()
