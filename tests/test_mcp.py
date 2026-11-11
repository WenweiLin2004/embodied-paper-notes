import asyncio
import json
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_real_stdio_handshake_and_tool_call(tmp_path):
    (tmp_path / "epn.toml").write_text('[library]\nname="test"\n', encoding="utf-8")

    async def check():
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "embodied_notes.mcp_server", "--root", str(tmp_path)], env=dict(os.environ))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {x.name for x in (await session.list_tools()).tools}
                assert {"prepare_paper", "read_evidence", "commit_paper_summary", "prepare_research", "commit_research"} <= names
                result = await session.call_tool("check_library", {})
                assert not result.isError
                payload = result.structuredContent or json.loads(result.content[0].text)
                assert payload["ok"] is True
                failed = await session.call_tool("read_evidence", {"packet_id": "../../secret"})
                assert failed.isError
    asyncio.run(check())
