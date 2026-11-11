"""Versioned reading queues and evidence-only comparison/reproduction preparation.

Queue state is durable Git content. Research packets and original evidence remain
local cache data. These helpers do not schedule work, call models, or publish.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

from .library import Library, RevisionConflict, atomic_write, digest, local_date, utc_now
from . import research
from .synthesis import EMBODIED_FIELDS
from .taxonomy import as_dict

QUEUE_STATUSES = ("candidate", "selected", "excluded", "read")
PAPER_FIELDS = (
    "id", "title", "authors", "abstract", "source_url", "pdf_url", "doi",
    "arxiv_id", "version", "published", "provider",
)
FIELD_LABELS = {
    "task": "任务", "embodiment": "机器人本体", "datasets": "训练与评测数据",
    "action_representation": "动作表示", "control_frequency": "控制频率",
    "evaluation": "仿真与实机设置", "generalization": "Seen / Unseen 泛化",
    "success_definition": "成功率定义与分母", "method": "方法机制",
    "results": "报告的实验结果", "limitations": "已记录的局限",
}
COMPARISON_FIELDS = (*EMBODIED_FIELDS, "method", "results", "limitations")
ALIGNMENT_FIELDS = EMBODIED_FIELDS


def _queue_path(root: Path | str) -> Path:
    return Library(root).root / "data" / "reading-queue.json"


def _read_queue(root: Path | str) -> tuple[dict, str | None]:
    path = _queue_path(root)
    if not path.exists():
        return {"schema_version": 1, "items": []}, None
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("Reading queue is not valid UTF-8 JSON; resolve edits or Git conflicts before writing") from None
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("items"), list):
        raise ValueError("Unsupported reading queue structure")
    seen = set()
    for item in data["items"]:
        if not isinstance(item, dict):
            raise ValueError("Reading queue items must be objects")
        identifier = item.get("paper_id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError("Reading queue paper IDs must be non-empty and unique")
        if item.get("status") not in QUEUE_STATUSES or not isinstance(item.get("reason"), str):
            raise ValueError("Reading queue item has invalid status or reason")
        if not isinstance(item.get("paper"), dict):
            raise ValueError("Reading queue item is missing paper metadata")
        seen.add(identifier)
    return data, digest(raw)


def _write_queue(root: Path | str, data: dict) -> str:
    path = _queue_path(root)
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    atomic_write(path, content)
    revision = digest(content)
    if digest(path.read_bytes()) != revision:
        raise OSError("Reading queue write verification failed")
    return revision


def _paper_and_queue_id(value: Any) -> tuple[dict, str]:
    candidate = as_dict(value)
    data = as_dict(candidate["paper"]) if "paper" in candidate else candidate
    paper = {key: deepcopy(data[key]) for key in PAPER_FIELDS if key in data}
    identifier = paper.get("id")
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError("Every queued paper requires an explicit paper ID")
    identifier = identifier.strip()
    version = paper.get("version")
    if version is not None and (not isinstance(version, str) or not version.strip()):
        raise ValueError("Paper version must be a non-empty string or null")
    if version:
        version = version.strip()
        if identifier.startswith("arxiv:"):
            if not re.fullmatch(r"v[1-9]\d*", version):
                raise ValueError("arXiv versions must be v1, v2, and so on")
            match = re.fullmatch(r"(.*?)(v[1-9]\d*)?", identifier)
            existing_version = match.group(2)
            if existing_version and existing_version != version:
                raise ValueError("Paper ID and arXiv version disagree")
            identifier = match.group(1) + version
        elif not identifier.endswith("@" + version):
            identifier += "@" + version
    return paper, identifier


def list_queue(root: Path | str, status: str | None = None, limit: int = 30, offset: int = 0) -> dict:
    if status is not None and status not in QUEUE_STATUSES:
        raise ValueError("Queue status must be candidate, selected, excluded, or read")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer in 1..100")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    data, revision = _read_queue(root)
    filtered = [item for item in data["items"] if status is None or item["status"] == status]
    items = filtered[offset:offset + limit]
    next_offset = offset + len(items) if offset + len(items) < len(filtered) else None
    return {"items": items, "total": len(filtered), "queue_total": len(data["items"]),
            "offset": offset, "limit": limit, "next_offset": next_offset,
            "revision": revision, "path": str(_queue_path(root))}


def queue_papers(root: Path | str, papers: list[Any], reason: str = "") -> dict:
    """Append candidates; preserve existing status, reason, metadata and order."""
    if not isinstance(papers, list):
        raise ValueError("papers must be an array of metadata records")
    if not isinstance(reason, str):
        raise ValueError("Queue reason must be a string")
    prepared = [_paper_and_queue_id(paper) for paper in papers]
    library = Library(root)
    with library._lock():
        data, revision = _read_queue(root)
        known = {item["paper_id"] for item in data["items"]}
        added = []
        skipped = []
        now = utc_now()
        for paper, identifier in prepared:
            if identifier in known:
                skipped.append(identifier)
                continue
            data["items"].append({"paper_id": identifier, "paper": paper, "status": "candidate",
                                  "reason": reason, "created_at": now, "updated_at": now})
            known.add(identifier)
            added.append(identifier)
        if added:
            data["updated_at"] = now
            revision = _write_queue(root, data)
    return {"added": added, "skipped": list(dict.fromkeys(skipped)), "total": len(data["items"]),
            "revision": revision, "path": str(_queue_path(root))}


def update_queue(root: Path | str, paper_id: str, status: str, reason: str | None = None,
                 expected_revision: str | None = None) -> dict:
    """Update one item after checking the revision of the whole queue file."""
    if status not in QUEUE_STATUSES:
        raise ValueError("Queue status must be candidate, selected, excluded, or read")
    if reason is not None and not isinstance(reason, str):
        raise ValueError("Queue reason must be a string or null to preserve it")
    library = Library(root)
    with library._lock():
        data, revision = _read_queue(root)
        if expected_revision != revision:
            raise RevisionConflict("Reading queue changed; list_queue again and pass its current revision")
        item = next((item for item in data["items"] if item["paper_id"] == paper_id), None)
        if item is None:
            raise ValueError("Paper ID is not in the reading queue; use paper_id from list_queue")
        if item["status"] != status or (reason is not None and item["reason"] != reason):
            item["status"] = status
            if reason is not None:
                item["reason"] = reason
            item["updated_at"] = utc_now()
            data["updated_at"] = item["updated_at"]
            revision = _write_queue(root, data)
    return {"item": item, "revision": revision, "path": str(_queue_path(root))}


def _claims(note: dict, field: str) -> list[dict]:
    summary = note.get("summary", {})
    claims = summary.get("embodied", {}).get(field, []) if field in EMBODIED_FIELDS else summary.get(field, [])
    if not isinstance(claims, list):
        raise ValueError(f"Invalid saved claims: {note['id']}/{field}")
    known = {item["id"] for item in note.get("evidence", [])}
    result = []
    for claim in claims:
        refs = claim.get("evidence_ids") if isinstance(claim, dict) else None
        if (not isinstance(claim, dict) or not isinstance(claim.get("text"), str)
                or not claim["text"].strip() or not isinstance(refs, list) or not refs
                or any(not isinstance(ref, str) or ref not in known for ref in refs)):
            raise ValueError(f"Saved claim has missing or invalid evidence: {note['id']}/{field}")
        refs = list(dict.fromkeys(refs))
        result.append({"text": claim["text"], "evidence_ids": refs,
                       "citations": [{"paper_id": note["id"], "evidence_ids": refs}]})
    return result


def _selected_notes(library: Library, paper_ids: list[str], minimum: int) -> list[dict]:
    if not isinstance(paper_ids, list) or any(not isinstance(value, str) or not value.strip() for value in paper_ids):
        raise ValueError("paper_ids must be an array of saved paper ID strings")
    unique = list(dict.fromkeys(paper_ids))
    if not minimum <= len(unique) <= 30:
        raise ValueError(f"Select {minimum}..30 distinct saved papers")
    notes = []
    for identifier in unique:
        note = library.get_paper(identifier)
        if note is None:
            raise ValueError(f"Unknown saved paper ID: {identifier}")
        notes.append(note)
    return notes


def _freeze_workflow(packet: dict, workflow: str, details: dict) -> dict:
    packet["workflow"] = workflow
    packet.update(details)
    atomic_write(Path(packet["packet_path"]), json.dumps(packet, ensure_ascii=False, indent=2))
    saved = json.loads(Path(packet["packet_path"]).read_text(encoding="utf-8"))
    if saved != packet:
        raise OSError("Workflow packet write verification failed")
    # The MCP source reader can return a selected note; do not dump full originals.
    keys = ("schema_version", "packet_id", "packet_path", "report_path", "topic", "created_at", "base_revision", "warnings")
    return {**{key: packet[key] for key in keys}, "workflow": workflow,
            "notes": [{key: note[key] for key in ("id", "title", "coverage", "revision")} for note in packet["notes"]],
            **details, "next_action": "Read sources with read_research_note, then use commit_research with this packet_id. Unknown fields are questions to resolve, not findings."}


def prepare_comparison(root: Path | str, paper_ids: list[str], topic: str) -> dict:
    """Freeze evidence by field without declaring scores or settings comparable."""
    library = Library(root)
    with library._lock():
        notes = _selected_notes(library, paper_ids, minimum=2)
        matrix = []
        missing = {note["id"]: [] for note in notes}
        for field in COMPARISON_FIELDS:
            cells = []
            for note in notes:
                claims = _claims(note, field)
                if not claims:
                    missing[note["id"]].append(field)
                cells.append({"paper_id": note["id"], "status": "documented" if claims else "unknown",
                              "coverage": note["coverage"], "source_revision": note["revision"], "claims": claims})
            matrix.append({"field": field, "label": FIELD_LABELS[field], "papers": cells})
        checks = [{"field": field, "label": FIELD_LABELS[field],
                   "status": "missing_information" if any(field in fields for fields in missing.values()) else "requires_manual_alignment",
                   "missing_in": [identifier for identifier, fields in missing.items() if field in fields]}
                  for field in ALIGNMENT_FIELDS]
        comparability = {
            "status": "requires_review", "automatically_established": False,
            "missing_fields_by_paper": missing, "checks": checks,
            "reason": "Matching field names or metric labels do not establish the same tasks, data, embodiments, splits, denominators, or evaluation protocol. No automatic numeric ranking is produced.",
        }
        packet = research.prepare(library.root, topic, notes,
                                  strategy={"workflow": "comparison", "source": "selected-local-notes", "date": local_date(),
                                            "paper_ids": [note["id"] for note in notes]})
        return _freeze_workflow(packet, "comparison", {"matrix": matrix, "comparability": comparability})


REPRODUCTION_ITEMS = (
    ("task", "任务与目标", ("task",)),
    ("method", "方法机制", ("method",)),
    ("datasets", "训练与评测数据", ("datasets",)),
    ("hardware", "机器人本体与已记录硬件", ("embodiment",)),
    ("action_representation", "动作表示", ("action_representation",)),
    ("control_frequency", "控制频率", ("control_frequency",)),
    ("evaluation_setting", "仿真与实机设置", ("evaluation",)),
    ("evaluation_metrics", "已记录指标、成功定义与结果", ("success_definition", "results")),
    ("generalization", "Seen / Unseen 划分", ("generalization",)),
    ("limitations", "已记录的局限", ("limitations",)),
    ("code_and_checkpoint", "代码版本与模型权重", ()),
    ("training_configuration", "训练超参数与随机种子", ()),
    ("dependencies", "运行环境与依赖版本", ()),
    ("compute_budget", "计算资源与训练预算", ()),
)


def prepare_reproduction(root: Path | str, paper_id: str) -> dict:
    """Create a cited prerequisite checklist, never an invented experiment plan."""
    library = Library(root)
    with library._lock():
        note = _selected_notes(library, [paper_id], minimum=1)[0]
        checklist = []
        for field, label, source_fields in REPRODUCTION_ITEMS:
            claims = [claim for source_field in source_fields for claim in _claims(note, source_field)]
            item = {"field": field, "label": label, "status": "documented" if claims else "unknown",
                    "source_fields": list(source_fields), "claims": claims,
                    "source_revision": note["revision"], "coverage": note["coverage"]}
            if not claims:
                item["reason"] = "No verified structured value is recorded for this checklist item. Check the original paper or released implementation before planning an experiment."
            if field == "hardware":
                item["scope_note"] = "Only existing embodiment/hardware claims are copied; device specifications, calibration, sensors and compute are not inferred."
            checklist.append(item)
        packet = research.prepare(library.root, f"复现准备：{note['title']} [{note['id']}]", [note],
                                  strategy={"workflow": "reproduction", "source": "selected-local-note", "date": local_date(),
                                            "paper_id": note["id"], "source_revision": note["revision"]})
        return _freeze_workflow(packet, "reproduction", {
            "paper_id": note["id"], "source_revision": note["revision"],
            "plan_status": "evidence_checklist_only", "checklist": checklist,
            "unknown_fields": [item["field"] for item in checklist if item["status"] == "unknown"],
        })
