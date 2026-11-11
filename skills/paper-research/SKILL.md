---
name: paper-research
description: Investigate an embodied AI research question using multi-source paper discovery and a local evidence-backed library, then save a cited comparison, literature review, or research-gap report. Use for topic research and cross-paper synthesis.
---

# Evidence-backed research

Use the `embodied-notes` MCP tools or `epn --root <library> research` CLI. Store queries, papers and reports in the repository. Do not use Notion.

Read `get_capabilities` when available and inspect current tool schemas. Use `paper-discover` for multi-source candidate/queue work, `paper-compare` for a named experimental comparison, and `paper-reproduce` for a replication plan. Ordinary topic synthesis can stay within this skill.

Start from the actual research question: what method, task, embodiment, evaluation setting or tradeoff is being compared? Narrow unclear scope using the conversation; ask only when the distinction materially changes the research.

1. Search arXiv and, where useful, other supported providers with explicit queries. Prefer `federated_search` when available and keep its per-provider warnings; `search_papers` remains the single-provider fallback. Capture queries, sources, dates, inclusion/exclusion rationale and known coverage gaps. `epn research discover TOPIC --query QUERY --provider arxiv` saves a candidate packet. Search hits are metadata, not full-text evidence.
2. Select relevant papers, deduplicate their identities and versions, and fetch/read the needed original evidence. Use the installed `paper-ingest` skill, or perform its equivalent via `prepare_paper`, `read_evidence` and `commit_paper_summary`. Do not summarize every candidate indiscriminately.
3. Call `prepare_research(topic, paper_ids, strategy)` on the saved papers, then `read_research_note(packet_id, paper_id)` for each source. The packet records evidence, coverage and source-note revisions. Do not cite a candidate that has no evidence in `notes`.
4. Read `get_output_schema(kind="research")` when available, then compose the report JSON described in [research-format.md](references/research-format.md). Compare mechanisms and assumptions before scores. Separate genuine disagreements from different metrics, training data, embodiments or simulation conditions. Mark conclusions based on abstract-only sources. Phrase gaps as bounded by the searched corpus, not universal absence. Keep factual claims in cited `sections`; save unresolved questions, proposed steps/acceptance criteria and working assumptions in optional `planning`, explicitly as unverified planning rather than paper facts or completed experiments.
5. Call `commit_research(payload)` or `epn research commit REPORT_JSON`. If source revisions changed, prepare a new packet and reconsider affected conclusions. Run `check_library` / `epn validate` and report the result path and coverage limits.

All factual comparison claims require paper/evidence citations. A one-paper observation is not multi-paper consensus. No scheduled monitoring, external messages, or Git push is implicit in a research request.

Design references: PaperQA2's evidence-centered answers and GPT Researcher's question/source separation. The local implementation adds fixed paper identities, structured embodied evaluation fields and revision checks; it does not depend on either full application.
