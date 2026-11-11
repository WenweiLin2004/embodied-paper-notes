"""Portable data contracts shared by the CLI, MCP server and note pipeline."""
from pydantic import BaseModel, Field


class Paper(BaseModel):
    id: str
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    source_url: str = ""
    pdf_url: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    version: str | None = None
    published: str | None = None
    provider: str = "unknown"


class EvidenceChunk(BaseModel):
    id: str
    section: str = "Body"
    text: str = ""
    source_url: str = ""
    page: int | None = None


class RetrievedPaper(BaseModel):
    paper: Paper
    chunks: list[EvidenceChunk] = Field(default_factory=list)
    full_text: bool = False
    warnings: list[str] = Field(default_factory=list)
    parser: str = "metadata-only"
