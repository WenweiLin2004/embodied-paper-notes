import pytest

from embodied_notes.library import Library, RevisionConflict
from embodied_notes.research import compose, prepare


def seed(root):
    library = Library(root)
    paper = {"id": "doi:10.1234/example", "title": "Embodied test", "abstract": "A test.", "source_url": "https://doi.org/10.1234/example"}
    packet = library.prepare({"paper": paper, "chunks": [{"id": "c1", "text": "Seven of ten trials succeed.", "section": "Results", "page": 3}],
                              "full_text": True, "parser": "test"})
    summary = {"coverage": "full_text", "problem": [], "method": [], "contributions": [],
               "results": [{"text": "Seven of ten trials succeed.", "evidence_ids": ["c1"]}], "limitations": [], "tags": []}
    library.commit_summary(packet, summary)
    return library, paper


def payload(packet_id, evidence_id="c1"):
    return {"packet_id": packet_id, "sections": [{"heading": "比较", "claims": [
        {"text": "This study reports 7/10 successful trials.", "citations": [
            {"paper_id": "doi:10.1234/example", "evidence_ids": [evidence_id]}]}]}]}


def test_review_links_real_evidence_and_marks_missing_findings(tmp_path):
    library, paper = seed(tmp_path)
    packet = prepare(tmp_path, "Manipulation", [paper], strategy={"query": "robot manipulation", "date": "2026-11-11"})
    result = compose(tmp_path, payload(packet["packet_id"]))
    from pathlib import Path
    text = Path(result["path"]).read_text(encoding="utf-8")
    assert result["source_count"] == 1
    assert "## 检索策略与范围" in text
    assert "## 共识" in text and "## 分歧" in text and "## 研究缺口" in text
    assert "尚无有证据支持的结论" in text
    assert "#evidence-1" in text


def test_review_rejects_unknown_evidence_and_metadata_only_candidates(tmp_path):
    library, paper = seed(tmp_path)
    packet = prepare(tmp_path, "Manipulation", [paper])
    with pytest.raises(ValueError, match="Unknown evidence"):
        compose(tmp_path, payload(packet["packet_id"], "fake"))
    other = dict(paper, id="doi:10.1234/not-read")
    candidate_packet = prepare(tmp_path, "Other", [other])
    assert candidate_packet["notes"] == []
    candidate_payload = payload(candidate_packet["packet_id"])
    candidate_payload["sections"][0]["claims"][0]["citations"][0]["paper_id"] = other["id"]
    with pytest.raises(ValueError, match="not an evidence source"):
        compose(tmp_path, candidate_payload)


def test_changed_source_blocks_stale_research_write(tmp_path):
    library, paper = seed(tmp_path)
    packet = prepare(tmp_path, "Manipulation", [paper])
    path = library.paper_path(paper["id"])
    with path.open("a", encoding="utf-8") as stream:
        stream.write("\nManual correction\n")
    with pytest.raises(RevisionConflict, match="Source note changed"):
        compose(tmp_path, payload(packet["packet_id"]))


def test_review_never_accepts_uncited_free_text(tmp_path):
    library, paper = seed(tmp_path)
    packet = prepare(tmp_path, "Manipulation", [paper])
    data = payload(packet["packet_id"])
    data["sections"][0]["claims"][0]["citations"] = []
    with pytest.raises(ValueError, match="needs citations"):
        compose(tmp_path, data)


def test_single_paper_cannot_be_presented_as_consensus(tmp_path):
    library, paper = seed(tmp_path)
    packet = prepare(tmp_path, "Manipulation", [paper])
    data = payload(packet["packet_id"])
    data["sections"][0]["heading"] = "共识"
    with pytest.raises(ValueError, match="two distinct"):
        compose(tmp_path, data)
