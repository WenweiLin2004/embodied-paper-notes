---
name: paper-discover
description: Find and triage embodied AI papers through multiple scholarly sources and citation links, then maintain an explicit local reading queue. Use for paper discovery and related-work expansion, not full-paper summarization.
---

# Discover papers and build a reading queue

Use `embodied-notes` in the selected repository. Start with `get_capabilities` and the actual schemas for `federated_search`, `citation_graph` and queue tools. If only `search_papers` is available, query supported providers separately and preserve each result's provenance.

1. Turn the question into a small set of complementary queries: method names/acronyms, the task, and evaluation constraints. For example, distinguish language-conditioned manipulation from generic visual-language understanding; keep simulation and real-world evidence separate. Use exact title/identifier lookup for a known paper.
2. Search the local collection with `search_library` to identify work already read. Run `federated_search` over the supported scholarly providers. Record the query, provider, retrieval date and returned warnings; report unavailable or rate-limited providers as coverage gaps, not empty search results.
3. Deduplicate by DOI or stable arXiv identity, retaining preprint versions and publication relationships. Similar titles alone are insufficient for merging. Keep source-specific citation counts separate; do not use counts as a proxy for methodological quality.
4. For relevant seed papers, call `citation_graph` with a bounded result limit. Follow both references and citing papers when the task benefits. Read titles/abstracts before adding candidates; citation edges establish a relationship, not endorsement or replication.
5. Use `list_queue` before `queue_papers` to avoid duplicates. Queue only candidates selected for the task or an explicitly requested reading list, with a concise relevance reason. For `update_queue`, copy `paper_id` and `revision` from the latest queue response; versioned queue IDs can differ from a library paper ID. A conflict requires rereading the queue, not substituting a guessed revision. Use the advertised statuses; do not invent a state or mark a paper read from its abstract.
6. Return a prioritized shortlist with stable IDs/URLs, why each matters, reading status, and search gaps. If the request includes ingestion, route selected candidates to `paper-ingest`; update their queue state only after the corresponding step actually succeeds.

The queue is a local research record, not a scheduled task or notification. Do not download every hit automatically. When a search yields nothing useful, revise the query using the observed vocabulary rather than claiming the literature is absent. Stop broadening when new results no longer affect the requested shortlist or the user's budget is reached.

Useful next operations: `prepare_paper` for primary evidence; `prepare_research` after source notes exist; `export_citations` for verified metadata. Discovery alone must not produce unsupported full-paper summaries.
