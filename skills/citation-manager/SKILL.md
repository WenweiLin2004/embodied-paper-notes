---
name: citation-manager
description: Resolve paper identities and export verified bibliographic metadata from an Embodied Paper Notes library. Use for BibTeX or supported CSL exports, reference checking, and preprint/publication reconciliation; never invent missing citation fields.
---

# Verified citations

Use the selected library's `embodied-notes` server. Inspect `get_capabilities` and `export_citations`'s schema for supported identifiers and output formats. Do not infer RIS/CSL support from another server with a similarly named tool.

1. Find saved references through `search_library`/`read_paper_note`. `resolve_paper` can verify an external DOI/arXiv identity, but the local `export_citations` tool accepts only saved `paper_ids`, not arbitrary metadata or unresolved search hits. A title-only match needs author/year/identifier confirmation before export. For a paper not yet saved, ingest it only when the request includes adding it; otherwise use a separately available authoritative citation exporter or report the local limitation.
2. Preserve the relationship between an arXiv preprint, its explicit version and a published DOI record. Export the version the user intends to cite; do not silently merge conference/journal metadata into the preprint.
3. Call `export_citations` using exact saved paper IDs and a supported format. The bibliography must come from the stored verified record, not generative completion of author names, venue, volume, pages or DOI.
4. Inspect per-item status and warnings. Return successful entries and identify failures separately. Preserve Unicode names and source-provided capitalization; retain tool-generated stable citation keys unless a real collision requires a deterministic correction.
5. For a manuscript bibliography, match cited keys to the exported records and report duplicate IDs, missing entries and version ambiguities. An export with valid syntax does not verify that the cited paper supports a scientific statement.

Write an export file only to the user's requested location or an appropriate repository output path; avoid replacing an existing hand-edited bibliography without inspecting its contents. No Zotero writes, collection moves, item merges or remote synchronization are implicit in exporting references.

If the requested format is unsupported, state the limitation and offer a documented conversion path using an available bibliographic tool. Never change the extension of BibTeX text and label it CSL-JSON.
