from mcp.server.fastmcp import FastMCP

from .ipc_client import IPCClient

mcp = FastMCP("murmur")
_client = IPCClient()


@mcp.tool()
async def listen() -> str:
    """Record speech via the Murmur daemon and return the transcribed text."""
    result = _client.send({"cmd": "listen"})
    if "error" in result:
        raise RuntimeError(result["error"])
    return result.get("text", "")


@mcp.tool()
async def status() -> dict:
    """Check whether the Murmur daemon is running."""
    return _client.send({"cmd": "status"})


def main():
    mcp.run()


if __name__ == "__main__":
    main()
