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
                from embodied_notes.mcp_extensions import capabilities
                described = capabilities(tmp_path)
                assert names == {name for group in described["tool_groups"].values() for name in group}
                resources = await session.list_resources()
                assert len(resources.resources) == 3
                value = await session.read_resource("epn://capabilities")
                assert json.loads(value.contents[0].text)["tool_count"] == len(names)
                prompts = await session.list_prompts()
                assert len(prompts.prompts) == 4
                prompt = await session.get_prompt("compare_papers", {"paper_ids": "id-1,id-2"})
                assert "prepare_comparison" in prompt.messages[0].content.text
                checked = await session.call_tool("search_library", {"query": "robot"})
                assert not checked.isError
                empty_queue = await session.call_tool("list_queue", {})
                assert not empty_queue.isError
    asyncio.run(check())
