import json
import tomllib
import pytest
from embodied_notes.install import install


def test_project_install_preserves_unrelated_config_and_is_idempotent(tmp_path):
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text('# keep comment\nmodel = "chosen"\n[mcp_servers.other]\ncommand = "other"\n', encoding="utf-8")
    install(tmp_path)
    first = config.read_text(encoding="utf-8")
    install(tmp_path)
    assert config.read_text(encoding="utf-8") == first
    parsed = tomllib.loads(first)
    assert parsed["model"] == "chosen"
    assert parsed["mcp_servers"]["other"]["command"] == "other"
    assert (tmp_path / ".agents/skills/paper-research/SKILL.md").is_file()


def test_conflict_is_preflight_and_dry_run_writes_nothing(tmp_path):
    install(tmp_path, dry_run=True)
    assert list(tmp_path.iterdir()) == []
    target = tmp_path / ".agents/skills/paper-ingest/SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("user edition", encoding="utf-8")
    with pytest.raises(ValueError):
        install(tmp_path)
    assert target.read_text() == "user edition"
    assert not (tmp_path / ".codex/config.toml").exists()


def test_generic_merge_preserves_other_server(tmp_path):
    config = tmp_path / ".mcp.json"
    config.write_text('{"mcpServers":{"other":{"command":"unchanged"}}}', encoding="utf-8")
    install(tmp_path, client="generic")
    assert json.loads(config.read_text())["mcpServers"]["other"] == {"command": "unchanged"}
