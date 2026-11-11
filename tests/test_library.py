import json

import pytest

from embodied_notes.library import Library, RevisionConflict, markdown_document, read_markdown
from embodied_notes.synthesis import SummaryValidationError


def retrieved(full_text=True):
    return {
        "paper": {"id": "arxiv:2303.03378v2", "title": "A robot manipulation study",
                  "authors": ["Example Author"], "abstract": "We evaluate a robot policy.",
                  "source_url": "https://arxiv.org/abs/2303.03378v2", "arxiv_id": "2303.03378", "version": "v2"},
        "chunks": [{"id": "results-1", "section": "Results", "text": "Success was 7/10 on held-out tasks. " * 50,
                    "source_url": "https://arxiv.org/html/2303.03378v2", "page": 4}],
        "full_text": full_text, "parser": "test", "warnings": [],
    }


def summary(coverage="full_text"):
    return {"coverage": coverage, "problem": [], "method": [], "contributions": [],
            "results": [{"text": "The reported success rate is 7/10.", "evidence_ids": ["results-1"]}],
            "limitations": [], "tags": ["task/manipulation"]}


def test_rejects_fabricated_evidence_and_inflated_coverage(tmp_path):
    library = Library(tmp_path)
    packet = library.prepare(retrieved(False))
    with pytest.raises(SummaryValidationError, match="Full text"):
        library.commit_summary(packet, summary())
    data = summary("abstract")
    data["results"][0]["evidence_ids"] = ["not-real"]
    with pytest.raises(SummaryValidationError, match="unknown evidence"):
        library.commit_summary(packet, data)
    assert library.list_papers() == []


def test_annotations_and_locked_tags_survive_regeneration(tmp_path):
    library = Library(tmp_path)
    first = library.commit_summary(library.prepare(retrieved()), summary())
    annotation = library.annotations_dir / library.paper_path(first["paper_id"]).name
    annotation.write_text("My private hypothesis\n", encoding="utf-8")
    path = library.paper_path(first["paper_id"])
    metadata, body = read_markdown(path)
    metadata["locked_tags"] = ["role/benchmark"]
    path.write_text(markdown_document(metadata, body), encoding="utf-8")
    packet = library.prepare(retrieved())
    revised = summary()
    revised["results"][0]["text"] = "Success is reported on ten held-out trials."
    result = library.commit_summary(packet, revised)
    assert annotation.read_text(encoding="utf-8") == "My private hypothesis\n"
    assert "role/benchmark" in result["tags"]
    assert result["revision"] != first["revision"]
    assert library.get_paper(first["paper_id"])["summary"]["results"][0]["text"].startswith("Success")


def test_stale_packet_and_tampered_packet_are_rejected(tmp_path):
    library = Library(tmp_path)
    one = library.prepare(retrieved())
    two = library.prepare(retrieved())
    library.commit_summary(one, summary())
    with pytest.raises(RevisionConflict):
        library.commit_summary(two, summary())
    newer = library.prepare(retrieved())
    newer["chunks"][0]["text"] = "Invented evidence"
    with pytest.raises(ValueError, match="packet has changed"):
        library.commit_summary(newer, summary())


def test_cache_keeps_full_text_out_of_committed_notes(tmp_path):
    library = Library(tmp_path)
    packet = library.prepare(retrieved())
    result = library.commit_summary(packet["packet_id"], summary())
    note = library.get_paper(result["paper_id"])
    assert "excerpt" not in note["evidence"][0]
    assert "text" not in note["evidence"][0]
    assert len(note["evidence"][0]["text_sha256"]) == 64
    assert retrieved()["chunks"][0]["text"] not in note["body"]
    assert json.loads((library.cache_dir / "packets" / (packet["packet_id"] + ".json")).read_text(encoding="utf-8"))["chunks"] == packet["chunks"]


def test_rejects_unknown_taxonomy_without_writing(tmp_path):
    library = Library(tmp_path)
    data = summary()
    data["tags"] = ["method/imaginary_method"]
    with pytest.raises(SummaryValidationError, match="Unknown taxonomy"):
        library.commit_summary(library.prepare(retrieved()), data)
    assert library.list_papers() == []


def test_navigation_pages_are_not_library_papers(tmp_path):
    library = Library(tmp_path)
    library.papers_dir.mkdir(parents=True)
    (library.papers_dir / "index.md").write_text("# Papers\n", encoding="utf-8")
    (library.papers_dir / "about.md").write_text("---\ntitle: About\n---\nNavigation\n", encoding="utf-8")
    assert library.list_papers() == []


def test_metadata_card_can_be_saved_without_invented_claims(tmp_path):
    library = Library(tmp_path)
    material = retrieved(False)
    material["paper"]["abstract"] = ""
    material["chunks"] = []
    data = {"coverage": "metadata", "problem": [], "method": [], "contributions": [],
            "results": [], "limitations": [], "tags": []}
    result = library.commit_summary(library.prepare(material), data)
    assert result["coverage"] == "metadata"
    assert library.get_paper(result["paper_id"])["evidence"] == []
