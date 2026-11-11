"""Offline integrity checks for CI; not a claim of scientific correctness."""
from pathlib import Path
from .library import Library, read_markdown
from .synthesis import validate_summary
from .taxonomy import load_taxonomy


def validate_library(root: Path) -> dict:
    library = Library(root)
    errors, warnings, notes = [], [], {}
    count = 0
    for path in sorted((root / "content" / "papers").glob("*.md")):
        if path.name == "index.md":
            continue
        try:
            note, _ = read_markdown(path)
            if "id" not in note or "paper" not in note:
                continue
            identifier = note["id"]
            if identifier in notes:
                raise ValueError("duplicate paper identity")
            if path != library.paper_path(identifier) or note["paper"]["id"] != identifier:
                raise ValueError("paper file or metadata identity mismatch")
            packet = {"paper": note["paper"], "chunks": note["evidence"], "full_text": note["coverage"] == "full_text"}
            validate_summary(note["summary"], packet, load_taxonomy(root))
            for evidence in note["evidence"]:
                if not evidence.get("source_url", "").startswith(("http://", "https://")):
                    raise ValueError("evidence source URL is missing or unsupported")
            if not (root / "content" / "annotations" / path.name).exists():
                warnings.append(f"{path.name}: personal annotation file not found")
            notes[identifier] = library.get_paper(identifier)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            errors.append(f"{path.name}: {exc}")
    for path in sorted((root / "content" / "research").glob("*.md")):
        if path.name == "index.md":
            continue
        try:
            report, _ = read_markdown(path)
            if "references" not in report:
                continue
            if "planning" in report:
                from .research import normalize_planning
                normalize_planning(report["planning"])
            refs = report["references"]
            for ref in refs:
                note = notes.get(ref["paper_id"])
                if note is None:
                    raise ValueError(f"missing source paper {ref['paper_id']}")
                if ref["evidence_id"] not in {e["id"] for e in note["evidence"]}:
                    raise ValueError(f"missing source evidence {ref['evidence_id']}")
                if ref["paper_revision"] != note["revision"]:
                    warnings.append(f"{path.name}: source {ref['paper_id']} changed; review this report")
            known = {(r["paper_id"], r["evidence_id"]) for r in refs}
            for section in report["sections"]:
                for claim in section["claims"]:
                    if not claim.get("citations"):
                        raise ValueError("research claim lacks citations")
                    for citation in claim["citations"]:
                        if not citation["evidence_ids"] or any((citation["paper_id"], e) not in known for e in citation["evidence_ids"]):
                            raise ValueError("research claim references undeclared evidence")
            count += 1
        except (ValueError, KeyError, TypeError, OSError) as exc:
            errors.append(f"{path.name}: {exc}")
    return {"ok": not errors, "papers": len(notes), "reports": count, "errors": errors, "warnings": sorted(set(warnings))}
