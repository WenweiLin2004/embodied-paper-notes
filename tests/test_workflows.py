from copy import deepcopy
import json
from pathlib import Path

import pytest

from embodied_notes.library import Library, RevisionConflict, markdown_document, read_markdown
from embodied_notes.research import compose, load_packet
from embodied_notes.workflows import (
    list_queue, prepare_comparison, prepare_reproduction, queue_papers, update_queue,
)


def metadata(identifier="arxiv:2303.03378", version="v1"):
    return {"id": identifier, "title": "Fixture manipulation study", "authors": ["Test Author"],
            "source_url": "https://example.org/paper", "version": version}


def seed(root, identifier, full_text=True, complete=False):
    library = Library(root)
    paper = metadata(identifier, None)
    paper["abstract"] = "We evaluate an imitation-learning robot."
    chunks = [
        {"id": "method", "section": "Method", "text": "We train an imitation-learning policy from demonstrations."},
        {"id": "setting", "section": "Experimental setup", "text": "A robot arm performs manipulation in simulation."},
        {"id": "metric", "section": "Evaluation", "text": "Success is 7 of 10 trials under a fixed evaluation protocol."},
    ]
    claim = lambda text, ref: {"text": text, "evidence_ids": [ref]}
    embodied = {
        "task": [claim("Robot manipulation.", "setting")],
        "embodiment": [claim("A robot arm.", "setting")],
        "evaluation": [claim("Simulation.", "setting")],
        "success_definition": [claim("7 of 10 trials.", "metric")],
    }
    if complete:
        # These are explicit synthetic fixtures, not inferred or real paper facts.
        chunks[1]["text"] += " Dataset: fixture set; held-out test split; action: joint target; control: 10 Hz."
        for field, text in (("datasets", "Fixture set."), ("generalization", "Held-out test split."),
                            ("action_representation", "Joint target."), ("control_frequency", "10 Hz.")):
            embodied[field] = [claim(text, "setting")]
    summary = {
        "coverage": "full_text" if full_text else "abstract", "problem": [],
        "method": [claim("Imitation learning from demonstrations.", "method")], "contributions": [],
        "results": [claim("7/10 trials succeed.", "metric")], "limitations": [],
        "tags": ["task/manipulation", "method/imitation_learning"], "embodied": embodied,
    }
    result = library.commit_summary(library.prepare({"paper": paper, "chunks": chunks, "full_text": full_text}), summary)
    return library, result


def test_queue_initial_state_and_append_are_version_aware_and_idempotent(tmp_path):
    initial = list_queue(tmp_path)
    assert initial["revision"] is None and initial["items"] == []
    assert not Path(initial["path"]).exists()
    empty = queue_papers(tmp_path, [])
    assert empty["revision"] is None and not Path(empty["path"]).exists()
    added = queue_papers(tmp_path, [metadata(version="v1"), metadata(version="v2")], "Read for comparison")
    assert added["added"] == ["arxiv:2303.03378v1", "arxiv:2303.03378v2"]
    before = Path(added["path"]).read_bytes()
    duplicate = queue_papers(tmp_path, [metadata(version="v1")], "Do not replace my reason")
    assert duplicate["added"] == [] and duplicate["revision"] == added["revision"]
    assert Path(added["path"]).read_bytes() == before
    explicitly_versioned = queue_papers(tmp_path, [metadata("arxiv:2303.03378v1", "v1")])
    assert explicitly_versioned["skipped"] == ["arxiv:2303.03378v1"]
    assert explicitly_versioned["revision"] == added["revision"]
    assert list_queue(tmp_path)["items"][0]["paper"]["id"] == "arxiv:2303.03378"


def test_queue_status_reason_are_preserved_on_rediscovery_and_updates_require_cas(tmp_path):
    added = queue_papers(tmp_path, [metadata()], "Discovery reason")
    changed = update_queue(tmp_path, added["added"][0], "excluded", "My exclusion decision", added["revision"])
    replay = queue_papers(tmp_path, [dict(metadata(), title="Changed upstream title")], "New automated reason")
    assert replay["revision"] == changed["revision"]
    item = list_queue(tmp_path)["items"][0]
    assert item["status"] == "excluded" and item["reason"] == "My exclusion decision"
    assert item["paper"]["title"] == "Fixture manipulation study"
    with pytest.raises(RevisionConflict):
        update_queue(tmp_path, item["paper_id"], "read", expected_revision=added["revision"])
    with pytest.raises(RevisionConflict):
        update_queue(tmp_path, item["paper_id"], "read")
    selected = update_queue(tmp_path, item["paper_id"], "selected", expected_revision=changed["revision"])
    assert selected["item"]["reason"] == "My exclusion decision"
    cleared = update_queue(tmp_path, item["paper_id"], "selected", "", selected["revision"])
    assert cleared["item"]["reason"] == ""


def test_queue_revision_covers_other_rows_and_manual_edits(tmp_path):
    first = queue_papers(tmp_path, [metadata()])
    second = queue_papers(tmp_path, [metadata("doi:10.test/other", None)])
    with pytest.raises(RevisionConflict):
        update_queue(tmp_path, first["added"][0], "read", expected_revision=first["revision"])
    path = Path(second["path"])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["items"][1]["reason"] = "A manual edit"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RevisionConflict):
        update_queue(tmp_path, first["added"][0], "read", expected_revision=second["revision"])
    assert list_queue(tmp_path)["items"][1]["reason"] == "A manual edit"


def test_queue_pagination_filtering_and_write_lock(tmp_path):
    added = queue_papers(tmp_path, [metadata(f"doi:10.test/{number}", None) for number in range(3)])
    selected = update_queue(tmp_path, added["added"][0], "selected", expected_revision=added["revision"])
    first = list_queue(tmp_path, status="candidate", limit=1)
    assert first["total"] == 2 and first["queue_total"] == 3 and first["next_offset"] == 1
    last = list_queue(tmp_path, status="candidate", limit=1, offset=first["next_offset"])
    assert last["next_offset"] is None
    assert first["items"][0]["paper_id"] != last["items"][0]["paper_id"]
    with Library(tmp_path)._lock():
        with pytest.raises(RevisionConflict, match="another process"):
            update_queue(tmp_path, added["added"][0], "read", expected_revision=selected["revision"])
    assert list_queue(tmp_path)["revision"] == selected["revision"]


@pytest.mark.parametrize("kwargs", [{"status": "daily-task"}, {"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_queue_rejects_invalid_requests(tmp_path, kwargs):
    with pytest.raises(ValueError):
        list_queue(tmp_path, **kwargs)


def test_queue_does_not_overwrite_git_conflicts_or_partial_bad_batch(tmp_path):
    result = queue_papers(tmp_path, [metadata()])
    path = Path(result["path"])
    initial = path.read_bytes()
    with pytest.raises(ValueError):
        queue_papers(tmp_path, [metadata("doi:10.test/new", None), {"title": "No identity"}])
    assert path.read_bytes() == initial
    path.write_text("<<<<<<< local\nconflict\n=======\nremote\n>>>>>>> remote\n", encoding="utf-8")
    conflict = path.read_bytes()
    with pytest.raises(ValueError, match="Git conflicts"):
        queue_papers(tmp_path, [metadata()])
    assert path.read_bytes() == conflict


def test_comparison_freezes_exact_evidence_and_marks_unknowns(tmp_path):
    library, first = seed(tmp_path, "fixture:a")
    _, second = seed(tmp_path, "fixture:b", full_text=False)
    prepared = prepare_comparison(tmp_path, [first["paper_id"], second["paper_id"]], "Compare manipulation protocols")
    cells = {row["field"]: row["papers"] for row in prepared["matrix"]}
    assert cells["control_frequency"][0]["status"] == "unknown"
    assert cells["control_frequency"][0]["claims"] == []
    assert cells["task"][0]["claims"][0]["evidence_ids"] == ["setting"]
    assert prepared["notes"][1]["coverage"] == "abstract"
    assert "evidence" not in prepared["notes"][0]
    assert prepared["comparability"]["automatically_established"] is False
    frozen = load_packet(tmp_path, prepared["packet_id"])
    assert frozen["matrix"] == prepared["matrix"]
    assert frozen["notes"][0]["revision"] == first["revision"]
    assert any("coverage is abstract" in warning for warning in prepared["warnings"])


def test_complete_matching_fields_still_do_not_establish_comparability(tmp_path):
    seed(tmp_path, "fixture:a", complete=True)
    seed(tmp_path, "fixture:b", complete=True)
    prepared = prepare_comparison(tmp_path, ["fixture:a", "fixture:b"], "Matching labels are insufficient")
    assert all(check["status"] == "requires_manual_alignment" for check in prepared["comparability"]["checks"])
    assert prepared["comparability"]["status"] == "requires_review"
    assert prepared["comparability"]["automatically_established"] is False


def test_comparison_packet_flows_into_report_and_stale_source_is_rejected(tmp_path):
    library, first = seed(tmp_path, "fixture:a")
    seed(tmp_path, "fixture:b")
    prepared = prepare_comparison(tmp_path, ["fixture:a", "fixture:b"], "Two-paper report")
    row = next(row for row in prepared["matrix"] if row["field"] == "task")
    payload = {"packet_id": prepared["packet_id"], "sections": [{"heading": "比较", "claims": [{
        "text": "Both saved notes describe manipulation tasks.",
        "citations": [cell["claims"][0]["citations"][0] for cell in row["papers"]]}]}]}
    assert compose(tmp_path, payload)["source_count"] == 2
    stale = prepare_comparison(tmp_path, ["fixture:a", "fixture:b"], "Stale report")
    path = library.paper_path("fixture:a")
    path.write_text(path.read_text(encoding="utf-8") + "\nManual correction\n", encoding="utf-8")
    payload["packet_id"] = stale["packet_id"]
    with pytest.raises(RevisionConflict, match="Source note changed"):
        compose(tmp_path, payload)


def test_reproduction_is_a_source_bound_checklist_and_can_be_saved(tmp_path):
    library, note = seed(tmp_path, "fixture:a")
    prepared = prepare_reproduction(tmp_path, "fixture:a")
    checklist = {item["field"]: item for item in prepared["checklist"]}
    assert prepared["source_revision"] == note["revision"]
    assert prepared["plan_status"] == "evidence_checklist_only"
    assert checklist["hardware"]["claims"][0]["text"] == "A robot arm."
    for field in ("control_frequency", "datasets", "training_configuration", "code_and_checkpoint", "compute_budget"):
        assert checklist[field]["status"] == "unknown" and checklist[field]["claims"] == []
    original_claim = checklist["hardware"]["claims"][0]
    result = compose(tmp_path, {"packet_id": prepared["packet_id"], "sections": [{"heading": "已知复现条件", "claims": [
        {"text": original_claim["text"], "citations": original_claim["citations"]}]}]})
    assert result["source_count"] == 1
    assert Path(result["path"]).exists()


def test_workflows_reject_unknown_papers_and_corrupted_evidence_before_freezing(tmp_path):
    library, first = seed(tmp_path, "fixture:a")
    with pytest.raises(ValueError, match="Unknown saved paper"):
        prepare_comparison(tmp_path, ["fixture:a", "fixture:missing"], "Unknown source")
    with pytest.raises(ValueError, match="distinct"):
        prepare_comparison(tmp_path, ["fixture:a", "fixture:a"], "Same source twice")
    path = library.paper_path("fixture:a")
    metadata_value, body = read_markdown(path)
    metadata_value["summary"]["embodied"]["task"][0]["evidence_ids"] = ["fabricated"]
    path.write_text(markdown_document(metadata_value, body), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid evidence"):
        prepare_reproduction(tmp_path, "fixture:a")
