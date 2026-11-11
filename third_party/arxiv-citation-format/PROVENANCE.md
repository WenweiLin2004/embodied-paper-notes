# Citation formatting adaptation

- Upstream: https://github.com/blazickjp/arxiv-mcp-server
- Commit: `572e301bb3198962c025d5ed5e14becb86868daa`
- Source file: `src/arxiv_mcp_server/tools/export_citations.py`
- Source symbols: `_BIBTEX_REPLACEMENTS`, `_bibtex_escape`
- Local adaptation: `src/embodied_notes/discovery.py`, `_BIBTEX_ESCAPES` and `_bibtex_escape`
- License: Apache-2.0; full upstream license retained in `LICENSE` beside this file.
- Reviewed and adapted: 2026-11-11.

Changes: single-pass character replacement replaces the upstream NUL-sentinel
algorithm. Control characters are removed, whitespace is normalized, and literal
braces use balanced `textbraceleft` / `textbraceright` commands. This prevents field
values from altering BibTeX entry nesting. Author strings are protected individually.

The discovery adapters, version-aware federation, per-direction graph pagination,
CSL-JSON output, stable hashed citation keys and tests are original implementation.
The upstream `citation_graph.py` was consulted for explicit provider/rate-limit
failures and bounded metadata output; no code from that file was copied.
