---
name: paper-compare
description: Compare selected embodied AI papers using cited mechanisms, assumptions, and compatible experimental conditions. Use for method or benchmark comparisons; do not turn incomparable reported scores into a leaderboard.
---

# Compare papers with evidence

Use the selected repository's `embodied-notes` server. Inspect `get_capabilities` and the schema of `prepare_comparison`; select saved paper IDs through `search_library`/`list_library`. Prepare and read missing source notes with `paper-ingest` before making comparative claims.

1. State what decision the comparison should support: mechanism, generalization, sample efficiency, deployment cost, or another user criterion. Read [comparison-dimensions.md](references/comparison-dimensions.md) when designing an embodied evaluation comparison.
2. Call `prepare_comparison(paper_ids, topic)` with at least two selected papers and the comparison question. Keep its exact `packet_id` and inspect the matrix/unknowns. An unknown cell means the saved structured note lacks that value, not that the paper never reports it. Read every included source using `read_research_note(packet_id, paper_id)`; use `search_evidence` and `read_evidence_by_ids` on source packets only when available and needed to resolve a missing detail.
3. Build an internal evidence ledger: criterion → paper → reported fact → locator/evidence ID → coverage/uncertainty. Check whether each pair shares the task, data split, embodiment, action/observation setting, metric and budget before comparing numbers.
4. Distinguish directly comparable, partially comparable and not comparable results. Preserve units, denominators, confidence intervals and reported seeds. Explain what differs when no fair numeric ranking is possible; a qualitative mechanism comparison can still be useful.
5. Return a compact comparison and the decision-relevant tradeoff. If asked to save it, use `commit_research` with the packet and the payload below, then `check_library`. Reprepare on stale source/report revisions.

## Saved payload

Read `get_output_schema(kind="research")` before composing. `commit_research` receives `payload` with `packet_id`, optional `title`, and `sections`. Each section has `heading` and `claims`; each claim has `text` and `citations`, and each citation has an exact `paper_id` and nonempty `evidence_ids` from that packet. A comparison involving two papers normally cites evidence from both. Use the server's current schema if it adds constraints.

Useful headings are methods, evaluation compatibility, reported results, limitations and selection criteria. Do not invent empty conclusions just to fill headings. Persist unresolved comparison questions in optional `planning.open_questions`, follow-up experiments and acceptance criteria in `planning.proposed_steps`, and provisional assumptions in `planning.assumptions`. Each category accepts at most 50 nonempty strings of at most 4000 characters. These are unverified planning notes, not cited paper conclusions or completed experiments. A repository observation outside the evidence packet may be retained as a source-linked question to verify; it must not be inserted as an unsupported factual claim.

Coverage is part of the result: abstract-only notes support only abstract-level comparisons, and a missing text cache means locators cannot substitute for reading the underlying passages. This skill prepares analysis; it does not execute benchmarks or certify one method as universally superior.
