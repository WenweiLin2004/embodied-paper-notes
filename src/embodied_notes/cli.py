"""Command-line entry point shared with the local MCP server."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from .paths import library_root

app = typer.Typer(no_args_is_help=True, help="具身论文笔记：检索、证据入库、调研与安装。")
research_app = typer.Typer(no_args_is_help=True, help="Evidence-backed topic research")
app.add_typer(research_app, name="research")
queue_app = typer.Typer(no_args_is_help=True, help="Git-synced candidate screening")
integration_app = typer.Typer(no_args_is_help=True, help="Optional external MCP configurations")
app.add_typer(queue_app, name="queue")
app.add_typer(integration_app, name="integrations")


def emit(value: object) -> None:
    # JSON redirected to files or another program must stay UTF-8 on Windows too.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def failure(exc: Exception) -> None:
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(1)


@app.callback()
def options(ctx: typer.Context, root: Annotated[Path | None, typer.Option(help="Library path (or EPN_ROOT)")] = None):
    ctx.obj = {"root": root}


def selected(ctx: typer.Context) -> Path:
    return library_root(ctx.find_root().obj["root"])


@app.command()
def init(path: Path):
    """Initialize a content library; clone this repository for the full website."""
    path = path.expanduser().resolve()
    for name in ("papers", "research", "annotations"):
        (path / "content" / name).mkdir(parents=True, exist_ok=True)
    marker = path / "epn.toml"
    if not marker.exists():
        marker.write_text('[library]\nname = "Embodied Paper Notes"\nlanguage = "zh-CN"\n', encoding="utf-8")
    ignore = path / ".gitignore"
    previous = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    rules = [".cache/", ".venv/", ".env", ".env.*", ".codex/config.toml", ".mcp.json", ".agents/skills/", ".claude/skills/"]
    missing = [rule for rule in rules if rule not in previous.splitlines()]
    if missing:
        ignore.write_text(previous.rstrip() + "\n" + "\n".join(missing) + "\n", encoding="utf-8")
    emit({"root": str(path), "initialized": True})


@app.command()
def search(query: str, limit: Annotated[int, typer.Option(min=1, max=50)] = 5,
           provider: str = "arxiv"):
    """Search external paper metadata; this does not publish notes."""
    from .sources import search as find
    try:
        if provider == "all":
            from .discovery import federated_search
            emit(federated_search(query, limit_per_provider=limit,
                                  providers=["arxiv", "openalex", "crossref", "semantic_scholar"]))
        elif provider in {"crossref", "semantic_scholar"}:
            from .discovery import search_provider
            emit([p.model_dump() for p in search_provider(query, provider, limit)])
        else:
            emit([p.model_dump() for p in find(query, limit=limit, provider=provider)])
    except Exception as exc:
        failure(exc)


@app.command()
def ingest(ctx: typer.Context, url: str,
           auto: Annotated[bool, typer.Option(help="Call configured model API; may incur cost")] = False,
           pdf_parser: str = "auto"):
    """Fetch paper evidence; optionally generate and validate a note with --auto."""
    from .library import Library
    from .sources import fetch_paper
    try:
        root = selected(ctx)
        lib = Library(root)
        packet = lib.prepare(fetch_paper(url, cache_dir=root / ".cache" / "epn" / "sources", pdf_parser=pdf_parser))
        if auto:
            from .provider import generate
            from .taxonomy import classify
            from .models import Paper
            summary = generate(packet, tags=all_tags(root))
            summary.setdefault("tags", classify(Paper.model_validate(packet["paper"])))
            emit(lib.commit_summary(packet, summary))
        else:
            emit(packet)
    except Exception as exc:
        failure(exc)


def all_tags(root: Path) -> list[str]:
    from .taxonomy import load_taxonomy
    taxonomy = load_taxonomy(root)
    # Normalized by the taxonomy module; keep this routing adaptable to its structure.
    if isinstance(taxonomy, dict):
        if "tags" in taxonomy:
            tags = taxonomy["tags"]
            return list(tags) if isinstance(tags, dict) else [x if isinstance(x, str) else x["id"] for x in tags]
        return [str(k) for k in taxonomy if "/" in str(k)]
    return list(taxonomy)


@app.command("commit")
def commit_note(ctx: typer.Context, packet: Path, summary: Path, expected_revision: str | None = None):
    """Validate model/agent JSON and write the note; human annotations are preserved."""
    from .library import Library
    try:
        emit(Library(selected(ctx)).commit_summary(packet, json.loads(summary.read_text(encoding="utf-8")), expected_revision))
    except Exception as exc:
        failure(exc)


@app.command("list")
def list_notes(ctx: typer.Context):
    from .library import Library
    try:
        emit(Library(selected(ctx)).list_papers())
    except Exception as exc:
        failure(exc)


@app.command()
def validate(ctx: typer.Context):
    """Check all generated notes and research evidence records."""
    from .validation import validate_library
    try:
        result = validate_library(selected(ctx))
        emit(result)
        if not result["ok"]:
            raise typer.Exit(1)
    except (ValueError, OSError) as exc:
        failure(exc)


@app.command("install")
def install_client(ctx: typer.Context, client: str = "codex", scope: str = "project",
                   force: bool = False, dry_run: bool = False):
    """Install bundled skills plus a stdio MCP entry (project scope by default)."""
    from .install import install
    try:
        emit(install(selected(ctx), client=client, scope=scope, force=force, dry_run=dry_run))
    except (ValueError, OSError) as exc:
        failure(exc)


@app.command()
def mcp(ctx: typer.Context):
    """Start the MCP stdio server. No HTTP port and no model key required."""
    from .mcp_server import create_server
    create_server(selected(ctx)).run(transport="stdio")


@app.command()
def doctor(ctx: typer.Context):
    """Report local configuration without exposing credentials."""
    import importlib.util
    try:
        root = selected(ctx)
        emit({"root": str(root), "model_configured": bool(os.environ.get("EPN_MODEL") and os.environ.get("EPN_API_KEY")),
              "docling_installed": importlib.util.find_spec("docling") is not None,
              "site_present": (root / "site" / "package.json").is_file(),
              "agent_mode": "ready; does not need model API credentials"})
    except ValueError as exc:
        failure(exc)


@research_app.command("discover")
def discover(ctx: typer.Context, topic: str, query: str | None = None,
             provider: str = "arxiv", limit: Annotated[int, typer.Option(min=1, max=50)] = 10):
    """Save a reproducible candidate search and map existing library evidence."""
    from .sources import search as find
    from .research import prepare
    try:
        strategy = {"query": query or topic, "provider": provider, "limit": limit}
        if provider == "all":
            from .discovery import federated_search
            found = federated_search(query or topic, limit_per_provider=limit,
                                     providers=["arxiv", "openalex", "crossref", "semantic_scholar"])
            papers = found["papers"]
            strategy["provider_statuses"] = found["providers"]
        elif provider in {"crossref", "semantic_scholar"}:
            from .discovery import search_provider
            papers = search_provider(query or topic, provider, limit)
        else:
            papers = find(query or topic, provider=provider, limit=limit)
        emit(prepare(selected(ctx), topic, papers, strategy=strategy))
    except Exception as exc:
        failure(exc)


@research_app.command("prepare")
def prepare_research(ctx: typer.Context, topic: str, papers: str = ""):
    """Prepare synthesis from saved library notes (comma-separated IDs, or all)."""
    from .library import Library
    from .research import prepare
    try:
        root = selected(ctx)
        lib = Library(root)
        ids = [x.strip() for x in papers.split(",") if x.strip()]
        candidates = [lib.get_paper(x) for x in ids] if ids else lib.list_papers()
        if any(p is None for p in candidates):
            raise ValueError("Unknown paper ID; use epn list to select saved papers")
        emit(prepare(root, topic, candidates, strategy={"source": "local-library", "paper_ids": ids}))
    except Exception as exc:
        failure(exc)


@research_app.command("commit")
def commit_research(ctx: typer.Context, payload: Path):
    from .research import compose
    try:
        emit(compose(selected(ctx), json.loads(payload.read_text(encoding="utf-8"))))
    except Exception as exc:
        failure(exc)


@research_app.command("auto")
def auto_research(ctx: typer.Context, packet: Path):
    """Generate a cited report from a prepared packet with the configured model API."""
    from .provider import generate
    from .research import compose
    try:
        material = json.loads(packet.read_text(encoding="utf-8"))
        payload = generate(material, kind="research")
        payload["packet_id"] = material["packet_id"]
        emit(compose(selected(ctx), payload))
    except Exception as exc:
        failure(exc)


@app.command()
def capabilities(ctx: typer.Context):
    """List installed skills, MCP tool groups, resources and supported formats."""
    from .mcp_extensions import capabilities as describe
    emit(describe(selected(ctx)))


@app.command("find")
def find_local(ctx: typer.Context, query: str, tags: str = "", coverage: str | None = None,
               limit: int = 10, offset: int = 0):
    """Search saved notes by lexical query with optional comma-separated tags."""
    from .local_tools import search_library
    try:
        emit(search_library(selected(ctx), query, tags.split(",") if tags else None, coverage, limit, offset))
    except Exception as exc:
        failure(exc)


@app.command("evidence")
def find_evidence(ctx: typer.Context, packet_id: str, query: str, limit: int = 6):
    """Find bounded passages in one prepared paper."""
    from .local_tools import search_evidence
    try:
        emit(search_evidence(selected(ctx), packet_id, query, limit))
    except Exception as exc:
        failure(exc)


@app.command("citations")
def citations(ctx: typer.Context, papers: Annotated[str, typer.Option()], format: str = "bibtex", output: Path | None = None):
    """Export comma-separated saved paper IDs; optionally write to a local file."""
    from .library import Library
    from .discovery import export_citations
    try:
        ids = [i.strip() for i in papers.split(",") if i.strip()]
        notes = [Library(selected(ctx)).get_paper(i) for i in ids]
        if not notes or any(n is None for n in notes):
            raise ValueError("Select saved paper IDs using epn list")
        result = export_citations([n["paper"] for n in notes], format)
        if output:
            output.write_text(result["content"], encoding="utf-8")
            result = {k: v for k, v in result.items() if k != "content"} | {"path": str(output.resolve())}
        emit(result)
    except Exception as exc:
        failure(exc)


@app.command("graph")
def graph(identifier: str, direction: str = "both", limit: int = 10):
    """Discover one bounded layer of references or citing papers; metadata only."""
    from .discovery import citation_graph
    try:
        emit(citation_graph(identifier, direction, limit))
    except Exception as exc:
        failure(exc)


@app.command("inspect")
def inspect(ctx: typer.Context):
    """Report coverage, validation, and possible duplicates or versions without editing notes."""
    from .local_tools import inspect_library
    try:
        emit(inspect_library(selected(ctx)))
    except Exception as exc:
        failure(exc)


@queue_app.command("list")
def queue_list(ctx: typer.Context, status: str | None = None, limit: int = 30, offset: int = 0):
    from .workflows import list_queue
    try:
        emit(list_queue(selected(ctx), status, limit, offset))
    except Exception as exc:
        failure(exc)


@queue_app.command("add")
def queue_add(ctx: typer.Context, metadata: Path, reason: str = ""):
    """Add metadata JSON (a list, federated result, or research candidates) to the screening queue."""
    from .workflows import queue_papers
    try:
        value = json.loads(metadata.read_text(encoding="utf-8"))
        papers = value.get("papers", value.get("candidates")) if isinstance(value, dict) else value
        emit(queue_papers(selected(ctx), papers, reason))
    except Exception as exc:
        failure(exc)


@queue_app.command("update")
def queue_update(ctx: typer.Context, paper_id: str, status: str, reason: str,
                 expected_revision: Annotated[str, typer.Option()]):
    from .workflows import update_queue
    try:
        emit(update_queue(selected(ctx), paper_id, status, reason, expected_revision))
    except Exception as exc:
        failure(exc)


@research_app.command("compare")
def compare(ctx: typer.Context, topic: str, papers: Annotated[str, typer.Option()]):
    from .workflows import prepare_comparison
    try:
        emit(prepare_comparison(selected(ctx), [i.strip() for i in papers.split(",") if i.strip()], topic))
    except Exception as exc:
        failure(exc)


@research_app.command("reproduce")
def reproduce(ctx: typer.Context, paper_id: str):
    from .workflows import prepare_reproduction
    try:
        emit(prepare_reproduction(selected(ctx), paper_id))
    except Exception as exc:
        failure(exc)


@integration_app.command("list")
def integrations_list():
    from .integrations import list_integrations
    emit(list_integrations())


@integration_app.command("install")
def integrations_install(ctx: typer.Context, name: str, client: str = "codex", scope: str = "project",
                         dry_run: bool = False, force: bool = False):
    """Configure a chosen external MCP; runtime and credentials must already be available."""
    from .integrations import install_integration
    try:
        emit(install_integration(selected(ctx), name, client, scope, dry_run=dry_run, force=force))
    except Exception as exc:
        failure(exc)


def main() -> None:
    # Apply before help/error rendering too, including redirected Windows output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    app()


if __name__ == "__main__":
    main()
