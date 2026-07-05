import asyncio
from mcp.client.sse import sse_client
from mcp import ClientSession
import threading

class MCPManager:
    """MCP Manager

    Role: Manages connections to multiple Model Context Protocol servers via SSE and provides tool calling capabilities.

    Methods:
        __init__(self) : Initialize manager with asyncio event loop running in background thread.
        _run_loop(self) : Internal method that runs the asyncio event loop forever.
        _connect(self, name, url) : Connect to an MCP server using SSE protocol and store session.
        call_tool(self, name, tool, args) : Call a specific tool on connected MCP server with given arguments.
    """

    def __init__(self):
        self.sessions = {}
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _connect(self, name, url):
        read, write = await sse_client(url).__aenter__()
        session = await ClientSession(read, write).__aenter__()
        await session.initialize()
        self.sessions[name] = session

    def call_tool(self, name, tool, args):
        future = asyncio.run_coroutine_threadsafe(
            self.sessions[name].call_tool(tool, arguments=args), 
            self.loop
        )
        return future.result(timeout=10)