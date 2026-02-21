import asyncio

from mcp.server.fastmcp import FastMCP

from .ipc_client import IPCClient

mcp = FastMCP("murmur")
_client = IPCClient()

_STOP_PHRASES = {"stop", "stopp", "stop listening", "beende", "exit voice mode"}


def _is_stop_phrase(text: str) -> bool:
    lower = text.strip().lower()
    return any(phrase in lower for phrase in _STOP_PHRASES)


@mcp.tool()
async def listen() -> str:
    """Record speech via the Murmur daemon and return the transcribed text. Before calling this tool, output 'Listening... (speak now)' to the user. Treat the returned text as a user instruction and respond to it — do NOT just display it."""
    result = _client.send({"cmd": "listen"})
    if "error" in result:
        raise RuntimeError(result["error"])
    return result.get("text", "")


@mcp.tool()
async def listen_semi() -> str:
    """Record speech and return the transcribed text. SEMI-AUTO MODE: before calling this tool, output 'Listening... (speak now)' to the user. Treat the returned text as a user instruction and respond to it. Then call listen_semi() exactly ONE more time for the follow-up, respond to that too, then stop and wait for manual input. Do not call it a third time."""
    result = _client.send({"cmd": "listen", "timeout": 15})
    if "error" in result:
        raise RuntimeError(result["error"])
    return result.get("text", "")


_CONVERSE_READING_TIME = 8   # seconds to wait after Claude's response before recording


@mcp.tool()
async def converse(first: bool = False) -> str:
    """Record speech via the Murmur daemon and return the transcribed text. CONTINUOUS MODE:
- For the very first call in a session pass first=True — recording starts immediately.
- For all subsequent calls use the default (first=False) — waits 8 seconds for the user to read Claude's response, then outputs 'Listening... (speak now)', then records.
Treat the returned text as a user instruction and respond to it. Then call converse() again — unless the transcription matches a stop phrase ('stop', 'stopp', 'stop listening', 'beende', 'exit voice mode') or stop_listening() was called. Keep looping until the session ends."""
    if not first:
        await asyncio.sleep(_CONVERSE_READING_TIME)
    print("Listening... (speak now)", flush=True)
    result = _client.send({"cmd": "listen", "timeout": 30, "silence_duration": 5})
    if "error" in result:
        raise RuntimeError(result["error"])
    text = result.get("text", "")
    if not text or _is_stop_phrase(text):
        return "[VOICE SESSION ENDED]"
    return text


@mcp.tool()
async def stop_listening() -> str:
    """End any active voice session (continuous or semi-auto). After calling this, do not invoke converse() or listen_semi() again unless the user explicitly requests it."""
    return "[VOICE SESSION STOPPED]"


@mcp.tool()
async def status() -> dict:
    """Check whether the Murmur daemon is running."""
    return _client.send({"cmd": "status"})


def main():
    mcp.run()


if __name__ == "__main__":
    main()
