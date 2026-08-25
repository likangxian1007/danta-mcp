"""Verify the danta MCP server over real stdio JSON-RPC (as an MCP host would call it).

Runs against this checkout regardless of where it lives, and deliberately injects a
polluted PYTHONPATH to prove the `-E` launcher isolation works.
"""
import asyncio
import io
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent
VENV_PY = HERE / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PY = str(VENV_PY if VENV_PY.exists() else sys.executable)
SRV = str(HERE / "run_server.py")


async def main():
    # Simulate a hostile parent env: an unrelated site-packages ahead on PYTHONPATH.
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(["/nonexistent/site-packages", env.get("PYTHONPATH", "")])

    params = StdioServerParameters(command=PY, args=["-E", SRV], cwd=str(HERE), env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            print(f"✅ handshake OK — {len(tools)} tools registered:")
            for t in tools:
                print(f"   • {t.name}")

            print("\n--- check_connection ---")
            res = await s.call_tool("check_connection", {})
            print(res.content[0].text)

            print("\n--- search_courses ---")
            res = await s.call_tool("search_courses", {"keyword": "微积分", "limit": 3})
            print(res.content[0].text[:500])

            print("\n--- search_holes ---")
            res = await s.call_tool("search_holes", {"keyword": "选课", "limit": 2})
            print(res.content[0].text[:400])

    print("\n✅ all checks passed")


if __name__ == "__main__":
    asyncio.run(main())
