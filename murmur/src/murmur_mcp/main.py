import asyncio
import os

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


_CONVERSE_READING_TIME = 8  # seconds to wait after Claude's response before recording


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


@mcp.tool()
async def get_config() -> dict:
    """Get the current Murmur configuration (language, model, hotkey, wake word, etc.)."""
    result = _client.send({"cmd": "get_config"})
    if "error" in result:
        raise RuntimeError(result["error"])
    return result


@mcp.tool()
async def configure(setting: str, value: str) -> dict:
    """Change a Murmur configuration setting. Changes persist to the config file.

    Settings:
    - language: transcription language code (e.g. "en", "de", "" for auto-detect)
    - model: whisper model — tiny, base, small, medium, large-v3 (requires restart)
    - device: "auto", "cpu", or "cuda" (requires restart)
    - compute_type: "auto", "int8", "float16", "float32" (requires restart)
    - hotkey: push-to-talk key (e.g. "F9", "ctrl+space")
    - wake_word: trigger phrase (e.g. "hey_jarvis", "alexa", "" to disable)
    - wake_word_threshold: sensitivity 0.0–1.0, lower = more sensitive (default 0.5)
    - inject_delay_ms: ms to wait before injecting text (default 0)
    """
    result = _client.send({"cmd": "configure", "setting": setting, "value": value})
    if "error" in result:
        raise RuntimeError(result["error"])
    return result


_LANG_NAMES = {
    "": "Auto-detect",
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "tr": "Turkish",
    "sv": "Swedish",
}
_MODEL_INFO = {
    "tiny": "tiny — fastest, lower accuracy (~75 MB)",
    "base": "base — fast, good accuracy (~150 MB)",
    "small": "small — balanced (~480 MB)",
    "medium": "medium — high accuracy (~1.5 GB)",
    "large-v2": "large-v2 — best accuracy, needs GPU (~3 GB)",
    "large-v3": "large-v3 — best accuracy, needs GPU (~3 GB)",
}
_WAKE_WORDS = {"hey_jarvis", "alexa", "hey_mycroft", "hey_rhasspy"}


@mcp.prompt()
def murmur_settings() -> str:
    """Show current Murmur settings and offer to change them."""
    try:
        cfg = _client.send({"cmd": "get_config"})
    except ConnectionError as e:
        return str(e)

    lang = cfg.get("language") or ""
    lang_label = _LANG_NAMES.get(lang, lang) if lang else "Auto-detect"
    model = cfg.get("model", "base")
    model_label = _MODEL_INFO.get(model, model)
    device = cfg.get("device", "auto")
    device_label = {
        "auto": "Auto (use GPU if available)",
        "cpu": "CPU only",
        "cuda": "GPU (CUDA)",
    }.get(device, device)
    hotkey = cfg.get("hotkey", "F9")
    wake_word = cfg.get("wake_word") or ""
    wake_label = wake_word if wake_word else "Disabled"
    threshold = cfg.get("wake_word_threshold", 0.5)
    delay = cfg.get("inject_delay_ms", 0)

    lines = [
        "## Murmur – current settings\n",
        "**Transcription**",
        f"  • Language:  {lang_label}" + (f"  (`{lang}`)" if lang else ""),
        f"  • Model:     {model_label}",
        f"  • Device:    {device_label}",
        "",
        "**Input**",
        f"  • Hotkey:    Hold **{hotkey}** to record",
        f"  • Wake word: {wake_label}"
        + (f"  (sensitivity {threshold})" if wake_word else ""),
        "",
        "**Output**",
        f"  • Inject delay: {delay} ms"
        + ("  (increase if text gets cut off)" if delay == 0 else ""),
        "",
        "Display the above settings to the user clearly.",
        "Then ask what they'd like to change and apply it with `configure()`.",
        "Reminders: model/device changes require a restart.",
        f"Available wake words: {', '.join(sorted(_WAKE_WORDS))} — or a path to a custom .onnx file.",
    ]
    return "\n".join(lines)


def main():
    try:
        mcp.run()
    except KeyboardInterrupt:
        os._exit(0)


if __name__ == "__main__":
    main()
