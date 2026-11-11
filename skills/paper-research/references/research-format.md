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
  ]
}
```

Replace illustrative IDs and prose with actual packet evidence. A comparative claim normally needs evidence from each compared paper. Exact schemas are available from `embodied_notes.research.research_schema()`.

Record strategy as an object containing query strings, providers, retrieval date, inclusion/exclusion criteria and scope. `prepare_research` freezes it into the packet. The report includes candidate and evidence counts and unresolved limitations. A successful commit proves citation IDs exist; it does not certify scientific validity or systematic coverage.
