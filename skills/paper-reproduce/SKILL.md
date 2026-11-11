---
name: paper-reproduce
description: Assess reproducibility of an embodied AI paper and create an evidence-linked implementation and experiment plan. Use for reproduction planning, artifact audits, or identifying missing experimental details; it does not imply permission to run costly training or control hardware.
---

# Plan a paper reproduction

Use `embodied-notes` in the selected library. Inspect `get_capabilities` and `prepare_reproduction`'s schema. Locate the saved paper with `search_library`/`read_paper_note`; if it is missing or only abstract-level, fetch and inspect original method, appendix and experimental evidence first.

1. Define the target: reproduce a specific table/figure, run official inference, port to another embodiment, or independently reimplement a method. These require different evidence and effort.
2. Call `prepare_reproduction(paper_id)` with the selected saved source. The target result is part of your analysis, not an extra tool argument. Retain the returned `packet_id` and read the source with `read_research_note`. Its `unknown` items mean no verified structured value is recorded locally; check the original/official artifacts before saying the authors omitted it. Use [reproduction-checklist.md](references/reproduction-checklist.md) to identify decision-relevant requirements and gaps.
3. Inspect linked official code, configuration, data and checkpoints with available read-only repository/web tools. Record exact commit/release and artifact versions. Documentation examples are evidence of a provided command, not proof that it succeeds or reproduces the paper.
4. Separate four things in the result: reported setup; available artifacts; missing or ambiguous details; proposed verification steps. Mark estimates explicitly and explain their basis. For example, “GPU memory not reported” differs from a tested minimum GPU requirement.
5. Produce a staged plan: environment smoke check → small inference/data check → controlled baseline → target result/ablation. Each stage needs observable acceptance criteria, expected inputs/outputs, and a stopping condition for missing artifacts or a failed earlier stage.
6. Read `get_output_schema(kind="research")` and save the complete report with `commit_research` when requested. Put supported findings in `sections`: each claim needs `text` and citations containing exact `paper_id`/`evidence_ids` from the packet. Put unresolved questions in optional `planning.open_questions`, proposed steps and their acceptance criteria in `planning.proposed_steps`, and working assumptions in `planning.assumptions`. Each is an array of at most 50 nonempty strings, each at most 4000 characters; the live schema remains authoritative. Run `check_library` after saving.

Planning is explicitly unverified and is not a source of paper facts or proof of completed experiments. A repository observation without local packet evidence cannot become a factual claim; preserve its URL/commit as a question to check in `planning.open_questions`. Do not invent evidence IDs or recast a desired result as an observed result. This separation allows a full reproduction plan to be saved alongside grounded findings.

This workflow does not prove reproducibility. Installing dependencies, executing repository code, downloading large datasets, paying for compute and commanding a robot are separate actions whose scope must come from the user's request. Continue authorized local implementation work when requested, but do not silently turn a feasibility assessment into a training run.
