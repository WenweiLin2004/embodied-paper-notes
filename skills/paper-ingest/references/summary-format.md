# Summary payload

`problem`, `method`, `contributions`, `results`, `limitations` are arrays of claims. Each claim has `text` and a non-empty `evidence_ids` list containing exact chunk IDs from the prepared packet. Unknown details are omitted; do not turn them into plausible facts.

```json
{
  "coverage": "full_text",
  "problem": [{"text": "根据已读原文写出的研究问题", "evidence_ids": ["EXACT_CHUNK_ID"]}],
  "method": [],
  "contributions": [],
  "results": [],
  "limitations": [],
  "tags": ["task/manipulation", "method/vla"],
  "embodied": {
    "task": [],
    "embodiment": [],
    "datasets": [],
    "action_representation": [],
    "control_frequency": [],
    "evaluation": [],
    "generalization": [],
    "success_definition": []
  }
}
```

This example is a schema illustration, not a paper summary. Replace the claim and ID with actual evidence. Use `coverage: "abstract"` when only an abstract is available, or `metadata` when no abstract is available. Empty sections honestly indicate that no supported claim was extracted; before committing a full-paper note, attempt to read all relevant sections rather than leaving most sections empty.

The runtime schema is `embodied_notes.synthesis.summary_schema()`. Citations are validated for existence and version context, not truth: inspect whether the cited passage actually supports the claim. Preserve units, metric definitions, comparison conditions and uncertainty.
