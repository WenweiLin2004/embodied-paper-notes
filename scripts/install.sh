#!/usr/bin/env sh
set -eu
repo_path=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_path"
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/epn --root "$repo_path" install --client "${1:-codex}"
printf '%s\n' 'Installed project skills and MCP. Restart your agent client to load them.'
