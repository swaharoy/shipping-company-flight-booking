"""The real MCP server over stdio: it lists the three tools and answers get_trip and search_flights."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent


def test_the_server_serves_the_tools(tmp_path: Path) -> None:
    environment = dict(os.environ, NANOAGENT_WORKSPACE=str(tmp_path), PYTHONPATH=str(ROOT / "src"))
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "plugin"], env=environment, cwd=str(ROOT))

    async def session() -> tuple:
        async with stdio_client(parameters) as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            tools = sorted(tool.name for tool in (await client.list_tools()).tools)
            started = await client.call_tool("get_trip", {"seed": 42})
            trip = started.structuredContent or json.loads(started.content[0].text)
            found = await client.call_tool("search_flights", {
                "seed": 42, "run_id": trip["run_id"], "origin": trip["trip"]["origin"]["code"],
                "destination": trip["trip"]["destination"]["code"], "date_from": trip["trip"]["date_from"],
                "date_to": trip["trip"]["date_to"]})
            refused = await client.call_tool("get_trip", {"seed": 10_000})
            return tools, trip, found, refused

    tools, trip, found, refused = anyio.run(session)
    assert tools == ["get_trip", "search_flights", "solve_booking"]
    assert trip["trip"]["seed"] == 42 and (tmp_path / "runs" / trip["run_id"] / "trip.json").is_file()
    assert not found.isError and (tmp_path / "runs" / trip["run_id"] / "search-1.json").is_file()
    assert refused.isError
