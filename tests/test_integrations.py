import json
import tomllib

import pytest

from embodied_notes.integrations import install_integration, list_integrations
from embodied_notes.install import install, prepare_mcp_config


def test_optional_integration_preflight_and_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr("embodied_notes.integrations.shutil.which", lambda name: None)
    result = install_integration(tmp_path, "arxiv", dry_run=True)
    assert result["runtime_found"] is False and not (tmp_path / ".codex").exists()
    with pytest.raises(ValueError, match="Install uv"):
        install_integration(tmp_path, "arxiv")
    assert not (tmp_path / ".codex").exists()


def test_github_readonly_config_never_saves_token(tmp_path, monkeypatch):
    monkeypatch.setattr("embodied_notes.integrations.shutil.which", lambda name: "/usr/bin/" + name)
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "test-secret-must-not-be-written")
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text('# preserve\nmodel="existing"\n[mcp_servers.other]\ncommand="other"\n', encoding="utf-8")
    first = install_integration(tmp_path, "github")
    install_integration(tmp_path, "github")
    raw = config.read_text(encoding="utf-8")
    value = tomllib.loads(raw)
    assert "# preserve" in raw and "test-secret" not in raw + json.dumps(first)
    entry = value["mcp_servers"]["github-research"]
    assert "GITHUB_READ_ONLY=1" in entry["args"]
    assert entry["env_vars"] == ["GITHUB_PERSONAL_ACCESS_TOKEN"]
    assert value["mcp_servers"]["other"]["command"] == "other"
    assert "test-secret" not in json.dumps(list_integrations())


def test_generic_integration_preserves_other_servers(tmp_path, monkeypatch):
    monkeypatch.setattr("embodied_notes.integrations.shutil.which", lambda name: "/usr/bin/" + name)
    config = tmp_path / ".mcp.json"
    config.write_text('{"mcpServers":{"other":{"command":"keep"}}}', encoding="utf-8")
    install_integration(tmp_path, "arxiv", client="generic")
    entries = json.loads(config.read_text())["mcpServers"]
    assert entries["other"]["command"] == "keep"
    assert entries["arxiv-research"]["args"] == ["arxiv-mcp-server"]


def test_codex_unicode_paths_remain_valid_toml(tmp_path):
    entry = {"command": "python", "args": ["--root", "C:/papers/🤖"]}
    _, content = prepare_mcp_config(tmp_path, "codex", "embodied-notes", entry)
    assert tomllib.loads(content)["mcp_servers"]["embodied-notes"] == entry


def test_incompatible_inline_mcp_table_is_rejected_without_mutations(tmp_path):
    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    original = '# existing valid config\nmcp_servers = {}\n'
    config.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError, match="expand inline"):
        install(tmp_path)
    assert config.read_text(encoding="utf-8") == original
    assert not (tmp_path / ".agents").exists()
