"""Resolve a library explicitly; never use the MCP client's accidental cwd."""
from __future__ import annotations

import os
from pathlib import Path


def library_root(value: str | Path | None = None) -> Path:
    selected = value or os.environ.get("EPN_ROOT")
    if selected:
        root = Path(selected).expanduser().resolve()
        if not (root / "epn.toml").is_file():
            raise ValueError(f"Not an EPN library: {root}. Run epn init PATH first.")
        return root
    current = Path.cwd().resolve()
    for path in (current, *current.parents):
        if (path / "epn.toml").is_file():
            return path
    raise ValueError("No epn.toml found. Use --root PATH, EPN_ROOT, or epn init PATH.")


def within(root: Path, path: Path) -> Path:
    candidate = path.resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError("Path escapes the selected library")
    return candidate
