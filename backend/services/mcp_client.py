import asyncio
import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from mcp_server.video_details_server import HOST, PORT

BACKEND_DIR = Path(__file__).parent.parent
SERVER_URL = f"http://{HOST}:{PORT}/mcp"

CONNECT_TIMEOUT_SECONDS = 10
CONNECT_RETRY_INTERVAL_SECONDS = 0.2


class MCPToolError(Exception):
    pass


class VideoDetailsMCPClient:
    def __init__(self):
        self._stack = AsyncExitStack()
        self._process: asyncio.subprocess.Process | None = None
        self.session: ClientSession | None = None

    async def connect(self):
        self._process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "mcp_server.video_details_server",
            cwd=str(BACKEND_DIR),
        )

        await self._wait_until_ready()

        read, write = await self._stack.enter_async_context(streamable_http_client(SERVER_URL))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()

    async def _wait_until_ready(self):
        deadline = asyncio.get_event_loop().time() + CONNECT_TIMEOUT_SECONDS
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    await client.get(SERVER_URL, timeout=1)
                    return
                except httpx.HTTPError:
                    if asyncio.get_event_loop().time() >= deadline:
                        raise RuntimeError(
                            f"MCP server did not become ready at {SERVER_URL} within "
                            f"{CONNECT_TIMEOUT_SECONDS}s"
                        )
                    await asyncio.sleep(CONNECT_RETRY_INTERVAL_SECONDS)

    async def fetch_video_details(self, url: str) -> dict:
        result = await self.session.call_tool("fetch_video_details", {"url": url})
        if result.is_error:
            message = result.content[0].text if result.content else "Unknown MCP tool error"
            raise MCPToolError(message)
        if result.structured_content is not None:
            return result.structured_content
        return json.loads(result.content[0].text)

    async def close(self):
        await self._stack.aclose()
        if self._process is not None and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
