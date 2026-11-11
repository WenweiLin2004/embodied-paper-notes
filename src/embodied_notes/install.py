"""Install the bundled skills and a local stdio MCP entry without clobbering clients."""
from __future__ import annotations

import json
import shutil
import sys
import tomllib
from importlib.resources import files
from pathlib import Path


def skill_source() -> Path:
    packaged = Path(str(files("embodied_notes").joinpath("bundled_skills")))
    if packaged.is_dir():
        return packaged
    checkout = Path(__file__).resolve().parents[2] / "skills"
    if checkout.is_dir():
        return checkout
    raise ValueError("Bundled skills missing; reinstall the distribution")


def install(root: Path, client: str = "codex", scope: str = "project",
            home: Path | None = None, force: bool = False, dry_run: bool = False) -> dict:
    if client not in {"codex", "claude", "generic"} or scope not in {"project", "user"}:
        raise ValueError("Unsupported client or scope")
    base = root if scope == "project" else (home or Path.home())
    skill_dir = base / (".agents/skills" if client == "codex" and scope == "project"
                        else ".codex/skills" if client == "codex"
                        else ".claude/skills" if client == "claude" else "skills")
    # Python module invocation works even when epn's scripts directory is not on PATH.
    entry = {"command": sys.executable, "args": ["-m", "embodied_notes.mcp_server", "--root", str(root)]}
    config = base / (".codex/config.toml" if client == "codex" else ".mcp.json")
    original = config.read_text(encoding="utf-8") if config.exists() else ""
    if client == "codex":
        data = tomllib.loads(original) if original.strip() else {}
        previous = data.get("mcp_servers", {}).get("embodied-notes")
        if previous is not None and previous != entry:
            raise ValueError(f"Existing embodied-notes MCP entry differs in {config}; update it explicitly")
        snippet = "\n[mcp_servers.embodied-notes]\ncommand = " + json.dumps(entry["command"]) + "\nargs = " + json.dumps(entry["args"]) + "\n"
        updated = original if previous is not None else original.rstrip() + "\n" + snippet
    else:
        data = json.loads(original) if original.strip() else {}
        previous = data.setdefault("mcpServers", {}).get("embodied-notes")
        if previous is not None and previous != entry and not force:
            raise ValueError(f"Existing embodied-notes MCP entry differs in {config}; use --force to replace only that entry")
        data["mcpServers"]["embodied-notes"] = entry
        updated = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    copies: list[tuple[Path, Path]] = []
    for source in sorted(skill_source().rglob("*")):
        if not source.is_file():
            continue
        target = skill_dir / source.relative_to(skill_source())
        if target.exists() and target.read_bytes() != source.read_bytes() and not force:
            raise ValueError(f"Skill file already differs: {target}; use --force to update bundled skill files")
        copies.append((source, target))
    if not dry_run:
        for source, target in copies:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(updated, encoding="utf-8")
    return {"client": client, "scope": scope, "skills": str(skill_dir), "mcp_config": str(config),
            "entry": entry, "dry_run": dry_run, "restart_client": True}
