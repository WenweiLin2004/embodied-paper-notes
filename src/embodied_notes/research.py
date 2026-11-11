"""Prepare bounded review packets and compose reports with verifiable citations."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any
import uuid

from .library import Library, RevisionConflict, atomic_write, digest, file_key, local_date, markdown_document, plain, utc_now
from .taxonomy import as_dict

DEFAULT_SECTIONS = ("比较", "共识", "分歧", "研究缺口")
PLANNING_LABELS = {"open_questions": "待核实问题", "proposed_steps": "拟议步骤与验收标准", "assumptions": "工作假设"}


def normalize_planning(value: Any) -> dict:
    if not isinstance(value, dict) or set(value) - PLANNING_LABELS.keys():
        raise ValueError("planning accepts only open_questions, proposed_steps, assumptions")
    result = {}
    for key in PLANNING_LABELS:
        items = value.get(key, [])
        if (not isinstance(items, list) or len(items) > 50
                or any(not isinstance(item, str) or not item.strip() or len(item) > 4000 for item in items)):
            raise ValueError("Planning entries must be 1..4000 character strings, at most 50 per category")
        result[key] = [item.strip() for item in items]
    return result


def research_schema() -> dict:
    citation = {
        "type": "object", "additionalProperties": False,
        "required": ["paper_id", "evidence_ids"],
        "properties": {"paper_id": {"type": "string"}, "evidence_ids": {
            "type": "array", "minItems": 1, "items": {"type": "string"}}},
    }
    return {
        "type": "object", "additionalProperties": False,
        "required": ["packet_id", "sections"],
        "properties": {
            "packet_id": {"type": "string"}, "title": {"type": "string"},
            "planning": {"type": "object", "additionalProperties": False, "properties": {
                key: {"type": "array", "maxItems": 50,
                      "items": {"type": "string", "minLength": 1, "maxLength": 4000}}
                for key in PLANNING_LABELS}},
            "sections": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["heading", "claims"],
                "properties": {
                    "heading": {"type": "string"},
                    "claims": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False,
                        "required": ["text", "citations"],
                        "properties": {"text": {"type": "string", "minLength": 1},
                                       "citations": {"type": "array", "minItems": 1, "items": citation}}}},
                }}},
        },
    }


def prepare(root: Path | str, topic: str, papers: list[Any], strategy: Any = None) -> dict:
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("Research topic must not be empty")
    library = Library(root)
    candidates = []
    notes = []
    warnings = []
    seen = set()
    for value in papers:
        item = as_dict(value)
        paper = as_dict(item["paper"]) if "paper" in item else item
        paper_id = paper.get("id")
        if not isinstance(paper_id, str):
            raise ValueError("Research candidates require paper IDs")
        if paper_id in seen:
            continue
        seen.add(paper_id)
        candidates.append(paper)
        note = library.get_paper(paper_id)
        if note is None:
            warnings.append(f"{paper_id}: not in the local library; metadata is not evidence for a review claim")
            continue
        prepared_note = {key: note[key] for key in ("id", "title", "paper", "coverage", "summary", "evidence", "revision")}
        cached_source = None
        if note.get("source_packet_id"):
            try:
                cached_source = library.load_packet(note["source_packet_id"])
            except (OSError, ValueError):
                pass
        if cached_source is not None:
            chunks = {chunk["id"]: chunk for chunk in cached_source["chunks"]}
            prepared_note["evidence"] = [
                {**evidence, "text": chunks[evidence["id"]]["text"]}
                if evidence["id"] in chunks and digest(chunks[evidence["id"]]["text"]) == evidence["text_sha256"] else evidence
                for evidence in note["evidence"]]
        else:
            warnings.append(f"{paper_id}: original text cache is absent; this packet contains note summaries and source locators only")
        notes.append(prepared_note)
        if note["coverage"] != "full_text":
            warnings.append(f"{paper_id}: coverage is {note['coverage']}; avoid full-text conclusions")
    report_path = library.root / "content" / "research" / (file_key(topic.strip()) + ".md")
    packet = {
        "schema_version": 1, "packet_id": uuid.uuid4().hex, "created_at": utc_now(),
        "topic": topic.strip(), "strategy": strategy if strategy is not None else "User-selected candidate set; no systematic-search completeness claim.",
        "candidates": candidates, "notes": notes, "warnings": warnings,
        "report_path": str(report_path),
        "base_revision": digest(report_path.read_bytes()) if report_path.exists() else None,
        "instructions": "Use only notes[].evidence IDs for substantive claims. Search results are candidates, not full-text evidence. State comparisons only where evaluation settings are comparable. No claim of systematic coverage unless the search log supports it.",
    }
    packet["packet_path"] = str(library.cache_dir / "research" / (packet["packet_id"] + ".json"))
    atomic_write(Path(packet["packet_path"]), json.dumps(packet, ensure_ascii=False, indent=2))
    return packet


def load_packet(root: Path | str, identifier: str) -> dict:
    key = Path(identifier).stem if str(identifier).endswith(".json") else str(identifier)
    if not re.fullmatch(r"[0-9a-f]{32}", key):
        raise ValueError("Invalid research packet ID")
    path = Library(root).cache_dir / "research" / (key + ".json")
    return json.loads(path.read_text(encoding="utf-8"))


def compose(root: Path | str, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Research output must be a JSON object")
    unknown = set(payload) - {"packet_id", "packet_path", "title", "sections", "planning", "expected_revision"}
    if unknown:
        raise ValueError(f"Unknown research fields: {sorted(unknown)}")
    packet = load_packet(root, payload.get("packet_id") or payload.get("packet_path") or "")
    library = Library(root)
    available = {note["id"]: note for note in packet["notes"]}
    planning = normalize_planning(payload.get("planning", {}))
    sections = payload.get("sections")
    if not isinstance(sections, list):
        raise ValueError("Research sections must be an array")
    references: list[dict] = []
    reference_numbers: dict[tuple[str, str], int] = {}
    normalized = []
    for section in sections:
        if not isinstance(section, dict) or set(section) != {"heading", "claims"}:
            raise ValueError("Each research section needs only heading and claims")
        if not isinstance(section["heading"], str) or not section["heading"].strip():
            raise ValueError("Section heading must be non-empty")
        if not isinstance(section["claims"], list):
            raise ValueError("Section claims must be an array")
        claims = []
        for claim in section["claims"]:
            if not isinstance(claim, dict) or set(claim) != {"text", "citations"}:
                raise ValueError("Research claim needs text and citations")
            if not isinstance(claim["text"], str) or not claim["text"].strip():
                raise ValueError("Research claim text is empty")
            if not isinstance(claim["citations"], list) or not claim["citations"]:
                raise ValueError("Every research claim needs citations")
            numbers = []
            citations = []
            for citation in claim["citations"]:
                if not isinstance(citation, dict) or set(citation) != {"paper_id", "evidence_ids"}:
                    raise ValueError("Citations need paper_id and evidence_ids")
                paper_id = citation["paper_id"]
                if not isinstance(paper_id, str) or paper_id not in available:
                    raise ValueError(f"Paper is not an evidence source in this packet: {paper_id}")
                evidence = {item["id"]: item for item in available[paper_id]["evidence"]}
                evidence_ids = citation["evidence_ids"]
                if not isinstance(evidence_ids, list) or not evidence_ids or any(not isinstance(item, str) for item in evidence_ids):
                    raise ValueError("Every citation requires evidence_ids")
                for evidence_id in evidence_ids:
                    if evidence_id not in evidence:
                        raise ValueError(f"Unknown evidence: {paper_id}/{evidence_id}")
                    pair = (paper_id, evidence_id)
                    if pair not in reference_numbers:
                        reference_numbers[pair] = len(references) + 1
                        durable_evidence = {key: value for key, value in evidence[evidence_id].items() if key not in {"text", "excerpt"}}
                        references.append({"paper_id": paper_id, "evidence_id": evidence_id,
                                           "paper_revision": available[paper_id]["revision"],
                                           "title": available[paper_id]["title"], **durable_evidence})
                    numbers.append(reference_numbers[pair])
                citations.append({"paper_id": paper_id, "evidence_ids": list(dict.fromkeys(evidence_ids))})
            if section["heading"].strip().lower() in {"共识", "consensus", "agreement"} and len({item["paper_id"] for item in citations}) < 2:
                raise ValueError("A consensus claim requires at least two distinct cited papers; leave the section empty when evidence is insufficient")
            claims.append({"text": claim["text"].strip(), "citations": citations, "reference_numbers": sorted(set(numbers))})
        normalized.append({"heading": section["heading"].strip(), "claims": claims})
    headings = {section["heading"] for section in normalized}
    normalized += [{"heading": name, "claims": []} for name in DEFAULT_SECTIONS if name not in headings]
    title = payload.get("title", packet["topic"])
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Research title must be a non-empty string")
    strategy = packet["strategy"] if isinstance(packet["strategy"], str) else json.dumps(packet["strategy"], ensure_ascii=False, indent=2)
    lines = ["# " + plain(title), "", "## 研究问题", "", plain(packet["topic"]), "", "## 检索策略与范围", "", plain(strategy), "",
             f"候选 {len(packet['candidates'])} 篇；可引用的本地笔记 {len(available)} 篇。候选集不代表完整文献覆盖。", ""]
    for section in normalized:
        lines += ["## " + plain(section["heading"]), ""]
        if not section["claims"]:
            lines += ["尚无有证据支持的结论。", ""]
        for claim in section["claims"]:
            refs = " ".join(f"[来源 {number}](#reference-{number})" for number in claim["reference_numbers"])
            lines += ["- " + plain(claim["text"]) + " " + refs]
        lines.append("")
    if any(planning.values()):
        lines += ["## 规划备注（非论文事实）", "", "以下是待核实问题、拟议计划与工作假设，不代表论文结论或已完成实验。", ""]
        for key, label in PLANNING_LABELS.items():
            if planning[key]:
                lines += ["### " + label, ""] + ["- " + plain(item) for item in planning[key]] + [""]
    lines += ["## 引用与证据", ""]
    for number, ref in enumerate(references, 1):
        note = available[ref["paper_id"]]
        anchor = next(index + 1 for index, evidence in enumerate(note["evidence"]) if evidence["id"] == ref["evidence_id"])
        link = "../papers/" + library.paper_path(ref["paper_id"]).name + f"#evidence-{anchor}"
        lines += [f'<a id="reference-{number}"></a>', f"{number}. [{plain(ref['title'])}]({link}) — {plain(ref.get('section') or '原文')}；阅读范围 {note['coverage']}。", ""]
    lines += ["## 不确定性", "", "引文校验只验证来源存在，不等于已证明每个陈述成立；需核对原文与评测条件。", ""]
    lines += ["- " + plain(warning) for warning in packet["warnings"]]
    metadata = {"schema_version": 1, "title": title.strip(), "topic": packet["topic"], "created_at": utc_now(),
                "date": local_date(), "tags": ["research"], "status": "ai-draft",
                "strategy": packet["strategy"], "candidate_count": len(packet["candidates"]),
                "source_count": len(available), "sections": normalized, "planning": planning, "references": references,
                "warnings": packet["warnings"]}
    path = library.root / "content" / "research" / (file_key(packet["topic"]) + ".md")
    document = markdown_document(metadata, "\n".join(lines))
    with library._lock():
        expected = payload.get("expected_revision", packet.get("base_revision"))
        actual = digest(path.read_bytes()) if path.exists() else None
        if expected != actual:
            raise RevisionConflict("Research report changed since prepare")
        for paper_id in available:
            note = library.get_paper(paper_id)
            if note is None or note["revision"] != available[paper_id]["revision"]:
                raise RevisionConflict(f"Source note changed since research prepare: {paper_id}")
        atomic_write(path, document)
        if digest(path.read_bytes()) != digest(document):
            raise OSError("Research write verification failed")
    return {"path": str(path), "revision": digest(document), "topic": packet["topic"],
            "source_count": len(available), "cited_source_count": len({ref["paper_id"] for ref in references}),
            "warnings": packet["warnings"]}
