# arxiv-mcp-server reuse

- Upstream: https://github.com/blazickjp/arxiv-mcp-server
- Commit: `572e301bb3198962c025d5ed5e14becb86868daa`
- Original file: `src/arxiv_mcp_server/tools/arxiv_ids.py`
- Local file: `src/embodied_notes/sources/arxiv_ids.py`
- License: Apache-2.0, full license preserved beside this record in `LICENSE`.
- Retrieved: 2026-11-11.

The identifier normalization module is vendored unchanged. Our `sources/api.py`
adapter additionally accepts arXiv HTML URLs, without modifying the vendored file.
This reuses the upstream handling of legacy IDs, version suffixes, and filename-safe
identifiers. Other source adapters, parsing, cache, and tests are original code.

Architecture research also examined https://github.com/openags/paper-search-mcp
(MIT), especially per-source capabilities and DOI/OA fallback separation. No code
from that repository is included in this version.
