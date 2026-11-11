"""Opt-in configurations for established external MCP servers; never store secrets."""
from __future__ import annotations

import os
from pathlib import Path
import shutil

from .install import prepare_mcp_config
from .library import atomic_write


PRESETS = {
    "arxiv": {
        "name": "arxiv-research", "runtime": "uvx", "required_env": [],
        "args": ["arxiv-mcp-server"],
        "source": "https://github.com/blazickjp/arxiv-mcp-server",
        "capabilities": ["arXiv source LaTeX", "citation graph", "downloaded paper search"],
        "setup": "Install uv (https://docs.astral.sh/uv/getting-started/installation/) so uvx is on PATH.",
    },
    "github": {
        "name": "github-research", "runtime": "docker", "required_env": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
        "args": ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "-e", "GITHUB_READ_ONLY=1",
                 "ghcr.io/github/github-mcp-server"],
        "source": "https://github.com/github/github-mcp-server",
        "capabilities": ["read repositories", "find implementations", "inspect issues and releases"],
        "setup": "Install/start Docker; set GITHUB_PERSONAL_ACCESS_TOKEN in the client process environment with only needed read permissions.",
    },
}


def list_integrations() -> dict:
    return {"core": {"name": "embodied-notes", "external_runtime_required": False},
            "optional": [{"id": key, **value, "runtime_found": shutil.which(value["runtime"]) is not None,
                          "missing_env": [name for name in value["required_env"] if not os.environ.get(name)]}
                         for key, value in PRESETS.items()],
            "notice": "Optional packages/images are downloaded by their runtimes on first use. Presets do not verify external server startup or grant write access."}


def install_integration(root: Path, integration: str, client: str = "codex", scope: str = "project",
                        home: Path | None = None, dry_run: bool = False, force: bool = False) -> dict:
    if integration not in PRESETS or scope not in {"project", "user"}:
        raise ValueError("Unknown integration or scope; use epn integrations list")
    preset = PRESETS[integration]
    command = shutil.which(preset["runtime"])
    missing = [name for name in preset["required_env"] if not os.environ.get(name)]
    if not dry_run and (not command or missing):
        raise ValueError(preset["setup"] + (f" Missing environment names: {', '.join(missing)}" if missing else ""))
    entry = {"command": command or preset["runtime"], "args": preset["args"]}
    if client == "codex" and preset["required_env"]:
        entry["env_vars"] = preset["required_env"]
    base = root if scope == "project" else (home or Path.home())
    config, updated = prepare_mcp_config(base, client, preset["name"], entry, force)
    if not dry_run:
        atomic_write(config, updated)
    return {"integration": integration, "client": client, "scope": scope, "config": str(config),
            "entry": entry, "dry_run": dry_run, "runtime_found": bool(command), "missing_env": missing,
            "secret_values_saved": False, "startup_verified": False, "restart_client": True,
            "source": preset["source"]}
