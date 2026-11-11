# Research payload

```json
{
  "packet_id": "EXACT_PREPARED_PACKET_ID",
  "title": "具体研究问题",
  "sections": [
    {
      "heading": "比较",
      "claims": [
        {
          "text": "从选定论文证据得出的比较结论",
          "citations": [
            {"paper_id": "EXACT_PAPER_ID", "evidence_ids": ["EXACT_EVIDENCE_ID"]}
          ]
        }
      ]
    },
    {"heading": "共识", "claims": []},
    {"heading": "分歧", "claims": []},
    {"heading": "研究缺口", "claims": []}
  ],
  "planning": {
    "open_questions": ["待核实：两篇论文的成功率是否使用相同的试验分母？"],
    "proposed_steps": ["拟议：核对两个评测脚本的任务划分；验收标准是记录脚本版本、分母定义和差异，并保留来源链接。"],
    "assumptions": ["工作假设：先以仿真评测作为比较范围，尚未验证它与实机结果的一致性。"]
  }
}
```

Replace illustrative IDs and prose with actual packet evidence and the user's actual planning needs. A comparative factual claim normally needs evidence from each compared paper. Read `get_output_schema(kind="research")` for the authoritative current contract; the same schema is available from `embodied_notes.research.research_schema()`.

`sections` holds evidence-backed claims and still requires valid citations. Optional `planning` accepts only `open_questions`, `proposed_steps`, and `assumptions`; omit categories that are not useful. Each category is an array of at most 50 nonempty strings, each 1..4000 characters. Put acceptance criteria alongside the proposed step they assess. These notes are rendered as unverified planning, not paper findings or evidence that an experiment has run.

A repository observation without evidence in the local packet must not be submitted as a factual claim. Preserve its source URL and commit/release in a planning question to verify instead, or first ingest it through a supported evidence workflow. Do not invent evidence IDs, claim a planned check passed, or use `planning` to conceal unsupported scientific conclusions.

Record strategy as an object containing query strings, providers, retrieval date, inclusion/exclusion criteria and scope. `prepare_research` freezes it into the packet. The report includes candidate and evidence counts and unresolved limitations. A successful commit proves citation IDs exist; it does not certify scientific validity or systematic coverage.
