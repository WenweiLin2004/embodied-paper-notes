import pytest

from embodied_notes.library import Library, RevisionConflict
from embodied_notes import local_tools as tools


@pytest.fixture
def saved(tmp_path):
    lib = Library(tmp_path)
    packet = lib.prepare({"paper": {"id": "arxiv:2406.09246v1", "title": "机器人 VLA policy",
        "arxiv_id": "2406.09246", "version": "v1", "source_url": "https://arxiv.org/abs/2406.09246v1"},
        "full_text": True, "chunks": [{"id": "eval", "section": "Evaluation",
        "text": "Unseen robot tasks had 7/10 success. " * 100, "source_url": "https://arxiv.org/html/2406.09246v1"}]})
    note = lib.commit_summary(packet, {"coverage": "full_text", "problem": [], "method": [],
        "contributions": [], "results": [{"text": "Unseen robot success 7/10.", "evidence_ids": ["eval"]}],
        "limitations": [], "tags": ["method/vla"]})
    return tmp_path, packet, note["paper_id"]


def test_lexical_search_and_annotation_opt_in(saved):
    root, _, paper_id = saved
    result = tools.search_library(root, "机器人 VLA", tags=["method/vla"])
    assert result["total"] == 1 and result["results"][0]["id"] == paper_id
    assert tools.search_library(root, "机器人", coverage="abstract")["total"] == 0
    old = tools.read_annotation(root, paper_id)
    tools.update_annotation(root, paper_id, "Human idea: lunar grasp", old["revision"])
    assert tools.search_library(root, "lunar")["total"] == 0
    assert tools.search_library(root, "lunar", include_annotations=True)["total"] == 1
    page = tools.read_paper_note(root, paper_id, max_chars=500)
    assert len(page["markdown"]) <= 500 and page["next_start"] == 500


def test_evidence_ids_and_pagination_preserve_context(saved):
    root, packet, _ = saved
    found = tools.search_evidence(root, packet["packet_id"], "unseen success", excerpt_chars=100)
    assert found["hits"][0]["id"] == "eval" and len(found["hits"][0]["excerpt"]) <= 100
    read = tools.read_evidence_by_ids(root, packet["packet_id"], ["eval"], max_chars=500)
    assert read["chunks"][0]["text"] == packet["chunks"][0]["text"][:500]
    assert read["chunks"][0]["next_start"] == 500
    with pytest.raises(ValueError, match="Unknown evidence"):
        tools.read_evidence_by_ids(root, packet["packet_id"], ["invented"])
    with pytest.raises(ValueError):
        tools.search_evidence(root, "../../other", "success")


def test_stale_annotations_never_overwrite_human_work(saved):
    root, _, paper_id = saved
    original = tools.read_annotation(root, paper_id)
    updated = tools.update_annotation(root, paper_id, "My new hypothesis", original["revision"])
    with pytest.raises(RevisionConflict):
        tools.update_annotation(root, paper_id, "stale replacement", original["revision"])
    assert tools.read_annotation(root, paper_id)["content"] == "My new hypothesis"
    assert updated["revision"] != original["revision"]
    assert tools.inspect_library(root)["paper_count"] == 1


def test_invalid_search_bounds_do_not_dump_library(saved):
    root, packet, _ = saved
    with pytest.raises(ValueError):
        tools.search_library(root, " ")
    with pytest.raises(ValueError):
        tools.search_evidence(root, packet["packet_id"], "success", limit=1000)


def test_annotation_returns_own_revision_when_another_writer_follows(saved, monkeypatch):
    from contextlib import contextmanager
    from embodied_notes.library import digest
    root, _, paper_id = saved
    path = Library(root).annotations_dir / Library(root).paper_path(paper_id).name
    actual_lock = Library._lock
    @contextmanager
    def next_writer_after_unlock(library):
        with actual_lock(library):
            yield
        path.write_text("writer B", encoding="utf-8")
    old = tools.read_annotation(root, paper_id)
    monkeypatch.setattr(Library, "_lock", next_writer_after_unlock)
    result = tools.update_annotation(root, paper_id, "writer A", old["revision"])
    assert result["revision"] == digest("writer A")
    assert path.read_text() == "writer B"
    with pytest.raises(RevisionConflict):
        tools.update_annotation(root, paper_id, "replace unread B", result["revision"])
