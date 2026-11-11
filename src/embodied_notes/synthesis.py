"""Evidence-linked output contracts and deterministic validation.

These checks establish source identity, not semantic entailment. An agent must
read the quoted evidence and explicitly distinguish author claims from analysis.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .taxonomy import DEFAULT_TAGS, validate_tags

SECTIONS = ("problem", "method", "contributions", "results", "limitations")
EMBODIED_FIELDS = (
    "task", "embodiment", "datasets", "action_representation", "control_frequency",
    "evaluation", "generalization", "success_definition",
)


class SummaryValidationError(ValueError):
    pass


def summary_schema() -> dict:
    claim = {
        "type": "object", "additionalProperties": False,
        "required": ["text", "evidence_ids"],
        "properties": {
            "text": {"type": "string", "minLength": 1},
            "evidence_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        },
    }
    claims = {"type": "array", "items": claim}
    return {
        "type": "object", "additionalProperties": False,
        "required": ["coverage", *SECTIONS, "tags"],
        "properties": {
            "coverage": {"type": "string", "enum": ["full_text", "abstract", "metadata"]},
            **{name: deepcopy(claims) for name in SECTIONS},
            "tags": {"type": "array", "items": {"type": "string"}},
            "embodied": {"type": "object", "additionalProperties": False,
                         "properties": {name: deepcopy(claims) for name in EMBODIED_FIELDS}},
        },
    }


def _claims(value: Any, known_ids: set[str], field: str) -> list[dict]:
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        raise SummaryValidationError(f"{field} must be an array of evidence-linked claims")
    output = []
    for claim in value:
        if not isinstance(claim, dict) or set(claim) - {"text", "evidence_ids"}:
            raise SummaryValidationError(f"{field}: expected only text and evidence_ids")
        text = claim.get("text")
        refs = claim.get("evidence_ids")
        if not isinstance(text, str) or not text.strip():
            raise SummaryValidationError(f"{field}: claim text is empty")
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) for ref in refs):
            raise SummaryValidationError(f"{field}: every claim needs evidence_ids")
        missing = set(refs) - known_ids
        if missing:
            raise SummaryValidationError(f"{field}: unknown evidence ids: {sorted(missing)}")
        output.append({"text": text.strip(), "evidence_ids": list(dict.fromkeys(refs))})
    return output


def validate_summary(summary: dict, packet: dict, allowed_tags: set[str] | None = None) -> dict:
    if not isinstance(summary, dict):
        raise SummaryValidationError("Summary must be a JSON object")
    unknown = set(summary) - {"coverage", *SECTIONS, "tags", "embodied"}
    if unknown:
        raise SummaryValidationError(f"Unknown summary fields: {sorted(unknown)}")
    missing = set(SECTIONS) - set(summary)
    if missing:
        raise SummaryValidationError(f"Missing summary sections: {sorted(missing)}")
    coverage = summary.get("coverage")
    if coverage not in {"full_text", "abstract", "metadata"}:
        raise SummaryValidationError("coverage must be full_text, abstract, or metadata")
    if coverage == "full_text" and not packet.get("full_text"):
        raise SummaryValidationError("Full text was not retrieved; full_text coverage is forbidden")
    if coverage == "abstract" and not packet.get("paper", {}).get("abstract"):
        raise SummaryValidationError("No abstract was retrieved")
    chunks = packet.get("chunks", [])
    ids = [chunk["id"] for chunk in chunks]
    if len(ids) != len(set(ids)):
        raise SummaryValidationError("Evidence chunk ids are not unique")
    known_ids = set(ids)
    output = {"coverage": coverage}
    for field in SECTIONS:
        output[field] = _claims(summary[field], known_ids, field)
    embodied = summary.get("embodied", {})
    if not isinstance(embodied, dict) or set(embodied) - set(EMBODIED_FIELDS):
        raise SummaryValidationError("embodied has an unsupported field")
    output["embodied"] = {field: _claims(value, known_ids, "embodied." + field) for field, value in embodied.items()}
    try:
        output["tags"] = validate_tags(summary.get("tags", []), allowed_tags if allowed_tags is not None else DEFAULT_TAGS)
    except ValueError as error:
        raise SummaryValidationError(str(error)) from error
    if not any(output[field] for field in SECTIONS) and coverage != "metadata":
        raise SummaryValidationError("An entirely empty summary cannot be committed")
    return output
