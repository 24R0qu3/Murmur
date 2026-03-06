# Murmur

> Push-to-talk voice-to-text for developers — local, fast, no cloud.

Hold a hotkey, speak, release. The transcribed text is injected directly into whatever window is active. Everything runs locally via [faster-whisper](https://github.com/SYSTRAN/faster-whisper); nothing leaves your machine.

An optional companion MCP server lets Claude Code (and any MCP-compatible client) trigger recordings on demand via the `listen()` tool.

---

## Features

- **Push-to-talk** — hold F9 (configurable), speak, release
- **Fully local** — faster-whisper runs on CPU or CUDA; no API keys, no internet
- **Cross-platform** — Linux (X11 + Wayland) and Windows
- **Wake word** — optional always-on detection via openwakeword (`murmur --install-wakeword`)
- **GUI overlay** — floating recording indicator (tkinter, optional via config)
- **System tray** — tray icon with status and quit option (optional via config)
- **Live audio meter** — visual feedback in the terminal while recording
- **MCP integration** — expose `listen()` and `status()` tools to Claude Code
- **Configurable** — model size, language, hotkey, device, compute type, inject delay

---

## How it works

```
F9 press  →  microphone opens
F9 hold   →  audio buffered  →  live level bar in terminal
F9 release →  faster-whisper transcribes  →  text injected into active window
```

IPC path (used by the MCP server):

```
{"cmd": "listen"}  →  records until silence  →  {"text": "..."}
{"cmd": "status"}  →  {"running": true}
```

---

## Requirements

### Linux

| Display server | Package needed |
|----------------|----------------|
| X11            | `xdotool`      |
| Wayland        | `ydotool`      |

```bash
# Debian / Ubuntu
sudo apt install xdotool      # X11
sudo apt install ydotool      # Wayland
```

### Windows

No extra tools needed. Text is injected via the clipboard (Ctrl+V).

### CUDA (optional)

Murmur auto-detects CUDA at startup. To force a specific device, set `device = "cuda"` or `device = "cpu"` in your config file.

### Source / pip install only

- Python 3.11+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

---

## Wake word (optional)

Murmur supports always-on wake word detection via [openwakeword](https://github.com/dscripka/openWakeWord). Because it adds ~200 MB of ML dependencies, it is not bundled in the binary — install it on demand with one command:

```bash
murmur --install-wakeword
```

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) to be installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`). This downloads `openwakeword` into a user-local directory and leaves the main binary untouched. Restart Murmur afterwards.

Then set `wake_word` in your config (see [Configuration](#configuration) below).

Available built-in model names: `hey_jarvis`, `alexa`, `hey_mycroft`, `hey_rhasspy`, and others — see the [openwakeword model list](https://github.com/dscripka/openWakeWord#pre-trained-models). Custom `.onnx` / `.tflite` model files are also supported (use the file path as the value).

**Install location:**

| Platform | Directory |
|----------|-----------|
| Linux    | `~/.local/share/murmur/wakeword` |
| macOS    | `~/Library/Application Support/murmur/wakeword` |
| Windows  | `%LOCALAPPDATA%\murmur\wakeword` |

---

## Installation

### Linux / macOS — one-liner (binary, no Python needed)

```bash
curl -fsSL https://raw.githubusercontent.com/24R0qu3/Murmur/main/install.sh | bash
```

Installs the self-contained binary to `~/.local/bin`. Override the location:

```bash
INSTALL_DIR=/usr/local/bin bash <(curl -fsSL https://raw.githubusercontent.com/24R0qu3/Murmur/main/install.sh)
```

### Windows — one-liner (binary, no Python needed)

```powershell
irm https://raw.githubusercontent.com/24R0qu3/Murmur/main/install.ps1 | iex
```

Installs to `%LOCALAPPDATA%\Programs\murmur` and adds it to the user PATH automatically.

### From source (Python required)

```bash
git clone https://github.com/24R0qu3/Murmur.git
cd Murmur/murmur
uv run murmur
```

### From GitHub (pip / uv)

```bash
# uv
uv tool install "murmur @ git+https://github.com/24R0qu3/Murmur.git#subdirectory=murmur"

# pip
pip install "murmur @ git+https://github.com/24R0qu3/Murmur.git#subdirectory=murmur"
```

---

On first run the Whisper model is downloaded automatically (≈150 MB for `base`). Subsequent starts are fast.

Expected output:

```
Loading model...
Ready.

  F9      hold to record, release to transcribe + inject
  language  de
  model     base
  device    cuda  (auto-detected)
  compute   int8_float32
  Ctrl+C  exit
```

---

## Configuration

Config file location: **`~/.config/murmur/config.toml`**

Create the file if it doesn't exist. All fields are optional — omitted fields use the defaults shown below.

```toml
model           = "base"   # Whisper model size (see table below)
language        = "de"     # ISO 639-1 code, or "" to auto-detect
hotkey          = "F9"     # Any key name recognised by pynput
device          = "auto"   # "auto", "cpu", or "cuda"
compute_type    = "auto"   # "auto", "int8", "int8_float32", "float16", "float32"
inject_delay_ms = 0        # ms to wait before injecting (helps some apps)

# GUI
tray                   = true   # system tray icon
overlay                = true   # floating recording indicator
overlay_always_on_top  = true
overlay_raise_on_hotkey = true
overlay_x              = -1     # position in pixels; -1 = auto (bottom-right)
overlay_y              = -1

# Wake word (requires murmur --install-wakeword)
wake_word           = ""    # e.g. "hey_jarvis" — leave empty to disable
wake_word_threshold = 0.5   # 0.0–1.0, higher = fewer false positives
```

### Model sizes

| Model    | Size   | Speed (CPU) | Notes                        |
|----------|--------|-------------|------------------------------|
| `tiny`   | ~75 MB | fastest     | Lower accuracy               |
| `base`   | ~150 MB| fast        | Good balance — **default**   |
| `small`  | ~480 MB| moderate    |                              |
| `medium` | ~1.5 GB| slow        | High accuracy                |
| `large-v3`| ~3 GB | slowest     | Best accuracy, needs GPU     |

### Language codes

Set `language = ""` to let Whisper auto-detect the spoken language (adds ~0.5 s). Otherwise use an [ISO 639-1 code](https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes): `"en"`, `"de"`, `"fr"`, `"es"`, `"ja"`, etc.

---

## MCP server — Claude Code integration

The `murmur-mcp` package is a thin MCP server that connects to the running Murmur daemon and exposes two tools:

| Tool | Description |
|------|-------------|
| `listen()` | Starts recording; returns transcribed text when silence is detected |
| `status()` | Returns `{"running": true}` if the daemon is reachable |

### Start the daemon first

```bash
cd murmur
uv run murmur
```

### Add to Claude Code (recommended)

```bash
claude mcp add murmur -- uv --directory /path/to/Murmur/murmur-mcp run murmur-mcp
```

Replace `/path/to/Murmur` with the absolute path to your clone.

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "murmur": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/Murmur/murmur-mcp",
        "run",
        "murmur-mcp"
      ]
    }
  }
}
```

The MCP server will print a clear error if the daemon is not running:

```
ConnectionError: Murmur daemon is not running. Start it with: uv run murmur
```

---

## Repository structure

```
Murmur/
├── install.sh               # One-liner installer (Linux / macOS)
├── install.ps1              # One-liner installer (Windows)
├── murmur/                  # Daemon package
│   ├── pyproject.toml
│   ├── murmur.spec          # PyInstaller spec
│   └── src/murmur/
│       ├── main.py          # Entry point — wires everything together
│       ├── config.py        # Config loading (~/.config/murmur/config.toml)
│       ├── audio.py         # Microphone capture (sounddevice + auto device detection)
│       ├── transcribe.py    # faster-whisper wrapper
│       ├── inject.py        # Text injection (xdotool / ydotool / clipboard+Ctrl+V)
│       ├── hotkey.py              # Global hotkey listener (pynput)
│       ├── ipc.py                 # JSON-over-socket server (Unix socket / Named Pipe)
│       ├── wakeword.py            # Wake word detection (openwakeword)
│       ├── wakeword_installer.py  # In-app openwakeword installer
│       └── log.py                 # Rotating file logger
└── murmur-mcp/              # MCP server package
    ├── pyproject.toml
    └── src/murmur_mcp/
        ├── main.py          # FastMCP entry point
        ├── ipc_client.py    # IPC client (connects to the daemon)
        └── log.py           # Rotating file logger
```

---

## IPC protocol

The daemon listens on:
- **Linux**: Unix socket at `/tmp/murmur.sock`
- **Windows**: Named Pipe at `\\.\pipe\murmur`

Messages are newline-terminated JSON:

```jsonc
// Check status
→ {"cmd": "status"}
← {"running": true}

// Record until silence and transcribe
→ {"cmd": "listen"}
← {"text": "your transcribed words"}

// Error response
← {"error": "Unknown command: 'foo'"}
```

Test on Linux:

```bash
echo '{"cmd": "status"}' | nc -U /tmp/murmur.sock
echo '{"cmd": "listen"}' | nc -U /tmp/murmur.sock
```

---

## Troubleshooting

### Audio device not opening (Windows)

Murmur automatically probes WASAPI and common sample rates at startup and uses the first combination that works. If no device is found, check that your microphone is set as the default recording device in Windows Sound Settings.

### Text not injected (Linux / X11)

Make sure `xdotool` is installed and `$DISPLAY` is set. Some Wayland compositors require `ydotool` and elevated permissions — see the ydotool documentation.

### Model download fails

Faster-whisper downloads models from Hugging Face on first use. If you're offline or behind a proxy, download the model manually and point `model` to the local path in your config.

### Wake word not triggering

- Run `murmur --install-wakeword` if you see "openwakeword is not installed"
- Raise `wake_word_threshold` to reduce false positives, lower it if it misses detections
- Built-in models are English-only; use a custom model file for other languages

### Nothing recognised

- Ensure the correct language is set (or use `language = ""` for auto-detect)
- Try a larger model (`small` or `medium`)
- Check microphone input levels — if the live bar in the terminal shows no activity, the wrong input device may be selected

---

## License

MIT
