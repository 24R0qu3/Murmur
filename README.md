# Murmur

> Hold a key, speak, release — transcribed text appears wherever your cursor is.

Murmur is a push-to-talk voice transcription tool. Press and hold a hotkey (default **F9**), say something, release — the text is typed into whatever window is active. Everything runs locally on your machine using [faster-whisper](https://github.com/SYSTRAN/faster-whisper). No internet connection, no account, no data sent anywhere.

Works on **Linux**, **Windows**, and **macOS**.

---

## Install

### Linux

```bash
curl -fsSL https://raw.githubusercontent.com/24R0qu3/Murmur/main/install.sh | bash
```

Installs a self-contained binary to `~/.local/bin`. No Python or other dependencies needed.

> If `~/.local/bin` is not in your PATH, the installer will tell you the exact command to add it.

**One extra step on Linux** — Murmur needs a tool to type text into other apps. Install the one that matches your desktop:

```bash
# If you use X11 (most common — e.g. Ubuntu with GNOME, KDE on Xorg):
sudo apt install xdotool

# If you use Wayland (e.g. Ubuntu 22.04+ default, GNOME on Wayland):
sudo apt install ydotool
```

Not sure which one you have? Run `echo $XDG_SESSION_TYPE` — it will say `x11` or `wayland`.

### Windows

Open **PowerShell** and run:

```powershell
irm https://raw.githubusercontent.com/24R0qu3/Murmur/main/install.ps1 | iex
```

Installs to `%LOCALAPPDATA%\Programs\murmur` and adds it to your PATH automatically.

---

## First run

After installing, open a terminal and run:

```
murmur
```

The first time, it downloads the Whisper speech model (~150 MB). This takes a minute. After that it starts instantly.

You'll see something like:

```
Loading model...
Ready.

  F9      hold to record, release to transcribe + inject
  language  en
  model     base
  device    cpu
  Ctrl+C  exit
```

A small floating toolbar also appears on your screen. That's the overlay — it shows recording status and a history of your transcriptions.

**You're ready.** Switch to any app (text editor, browser, chat), hold **F9**, speak, release. The text appears.

---

## Settings

Click the **⚙** button on the overlay toolbar to open the settings panel. From there you can change:

- **Hotkey** — the key you hold to record
- **Language** — what language you're speaking (leave blank for auto-detect)
- **Model** — larger models are more accurate but slower (see table below)
- **Wake word** — say a phrase to start recording hands-free
- **Overlay** options — always-on-top, position

Changes to the hotkey, language, and wake word take effect immediately. Model changes require a restart.

### Choosing a model

| Model | Download size | Speed | Accuracy |
|-------|--------------|-------|----------|
| `tiny` | ~75 MB | Fastest | Lower |
| `base` | ~150 MB | Fast | Good — **default** |
| `small` | ~480 MB | Moderate | Better |
| `medium` | ~1.5 GB | Slow | High |
| `large-v3` | ~3 GB | Slowest | Best — needs a GPU |

For most people, `base` is the sweet spot. If you have a GPU, `large-v3` is noticeably better.

### Config file

Settings are saved to **`~/.config/murmur/config.toml`** (Linux) or **`%APPDATA%\murmur\config.toml`** (Windows). You can also edit it directly:

```toml
model           = "base"
language        = "en"    # leave "" to auto-detect the spoken language
hotkey          = "F9"
inject_delay_ms = 0       # increase (e.g. 50) if text gets cut off in some apps
```

---

## Wake word (optional)

Wake word lets you start recording by saying a phrase — no key press needed. Because the required ML library is large (~200 MB extra), it's not included by default. Install it with:

```bash
murmur --install-wakeword
```

This requires [uv](https://docs.astral.sh/uv/getting-started/installation/) to be installed first:

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

After installing, restart Murmur and set the wake word in Settings (or in your config file):

```toml
wake_word = "hey_jarvis"
```

Available built-in phrases: `hey_jarvis`, `alexa`, `hey_mycroft`, `hey_rhasspy`. Custom model files (`.onnx`) are also supported — use the file path as the value. Built-in models are English only.

---

## GPU acceleration (optional)

Murmur auto-detects CUDA at startup. If you have an NVIDIA GPU and want to use it:

```bash
murmur --install-cuda
```

This downloads the required CUDA runtime libraries (~500 MB) without touching your system installation. Restart Murmur after installing — it will detect your GPU automatically.

To force a specific device, add to your config:

```toml
device = "cuda"   # or "cpu"
```

---

## Uninstall

Remove all data Murmur has stored (models, wake word files, config, logs):

```bash
murmur --uninstall
```

Then remove the binary itself:

```bash
# Linux
rm ~/.local/bin/murmur

# Windows (PowerShell)
Remove-Item "$env:LOCALAPPDATA\Programs\murmur" -Recurse -Force
```

---

## Troubleshooting

**Text isn't appearing when I release the key (Linux)**

- Make sure `xdotool` (X11) or `ydotool` (Wayland) is installed — see [Install](#install) above.
- On Wayland with `ydotool`, you may need to add your user to the `input` group: `sudo usermod -aG input $USER` and then log out/in.

**Nothing is recognised after transcribing**

- Check that the right language is set. If unsure, try `language = ""` for auto-detect.
- Make sure your microphone is working — if the level bar in the terminal stays flat while you speak, the wrong input device is selected.
- Try a larger model (`small` or `medium`).

**Murmur is slow to transcribe**

- You're likely on CPU with a large model. Switch to `base` or `tiny`, or install CUDA support if you have an NVIDIA GPU.

**First startup takes forever**

- It's downloading the Whisper model from Hugging Face. This only happens once.

**Audio device error on Windows**

- Make sure your microphone is set as the default recording device in Windows Sound Settings.

**Wake word isn't triggering**

- Run `murmur --install-wakeword` if you see "openwakeword is not installed".
- Lower `wake_word_threshold` in your config if it misses triggers (default 0.5). Raise it to reduce false positives.

---

## MCP server — Claude Code integration

Murmur includes an MCP server that lets Claude Code (and any MCP client) trigger recordings on demand via a `listen()` tool. The daemon starts automatically in the background — no separate setup step needed.

### Setup

```bash
# Add to Claude Code
claude mcp add murmur -- murmur --mcp
```

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "murmur": {
      "command": "murmur",
      "args": ["--mcp"]
    }
  }
}
```

### Available tools

| Tool | What it does |
|------|-------------|
| `listen()` | Records until silence, returns the transcribed text |
| `listen_semi()` | Like `listen()` but with a countdown |
| `converse()` | Multi-turn voice interaction |
| `stop_listening()` | Aborts an active recording |
| `status()` | Returns `{"running": true}` if the daemon is reachable |

---

## For developers

### Build from source

```bash
git clone https://github.com/24R0qu3/Murmur.git
cd Murmur/murmur
uv run murmur
```

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

### IPC protocol

The daemon listens on a local socket:
- **Linux**: Unix socket at `/tmp/murmur.sock`
- **Windows**: Named Pipe at `\\.\pipe\murmur`

Messages are newline-terminated JSON:

```jsonc
// Check status
→ {"cmd": "status"}
← {"running": true}

// Record until silence
→ {"cmd": "listen", "timeout": 30, "silence_duration": 1.5}
← {"text": "your transcribed words"}
```

Test on Linux:
```bash
echo '{"cmd": "status"}' | nc -U /tmp/murmur.sock
```

### Repository structure

```
Murmur/
├── install.sh / install.ps1     # One-liner installers
└── murmur/                      # Single package (uv + setuptools)
    ├── murmur.spec              # PyInstaller build spec
    └── src/
        ├── murmur/
        │   ├── main.py              # Entry point — wires everything together
        │   ├── config.py            # Config loading
        │   ├── audio.py             # Microphone capture (sounddevice)
        │   ├── transcribe.py        # faster-whisper wrapper
        │   ├── inject.py            # Text injection (xdotool / ydotool / clipboard)
        │   ├── hotkey.py            # Global hotkey (pynput)
        │   ├── ipc.py               # JSON-over-socket server
        │   ├── overlay.py           # Floating overlay toolbar (wxPython)
        │   ├── tray.py              # System tray icon (pystray)
        │   ├── settings_dialog.py   # Settings UI
        │   ├── wakeword.py          # Wake word detection (openwakeword)
        │   └── wakeword_installer.py
        └── murmur_mcp/
            ├── main.py              # FastMCP server (run via: murmur --mcp)
            └── ipc_client.py        # Connects to the daemon socket
```

---

## License

MIT — see [LICENSE](LICENSE).
