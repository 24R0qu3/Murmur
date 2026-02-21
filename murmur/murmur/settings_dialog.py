import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-reattr]

_MODELS  = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
_DEVICES = ["auto", "cpu", "cuda"]
_BG = "#2b2b2b"
_FG = "#cccccc"


class SettingsDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Tk,
        config,
        config_path: Path,
        on_save: Callable,
    ):
        super().__init__(parent)
        self._config      = config
        self._config_path = config_path
        self._on_save     = on_save
        self._binding     = False

        self.title("Murmur Settings")
        self.resizable(False, False)
        self.grab_set()
        self._build()
        self._center(parent)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        pad = {"padx": 12, "pady": 5}

        frm = tk.Frame(self, padx=8, pady=8)
        frm.pack(fill=tk.BOTH, expand=True)

        def row(label, widget_fn, r):
            tk.Label(frm, text=label, anchor="w").grid(row=r, column=0, sticky="w", **pad)
            widget_fn(r)

        # Model
        self._model_var = tk.StringVar(value=self._config.model)
        row("Model", lambda r: ttk.Combobox(
            frm, textvariable=self._model_var,
            values=_MODELS, state="readonly", width=14,
        ).grid(row=r, column=1, sticky="w", **pad), 0)

        # Language
        self._lang_var = tk.StringVar(value=self._config.language)
        row("Language", lambda r: tk.Entry(
            frm, textvariable=self._lang_var, width=8,
        ).grid(row=r, column=1, sticky="w", **pad), 1)

        # Hotkey
        self._hotkey_var = tk.StringVar(value=self._config.hotkey)
        row("Hotkey", lambda r: self._hotkey_row(frm, r), 2)

        # Device
        self._device_var = tk.StringVar(value=self._config.device)
        row("Device", lambda r: ttk.Combobox(
            frm, textvariable=self._device_var,
            values=_DEVICES, state="readonly", width=8,
        ).grid(row=r, column=1, sticky="w", **pad), 3)

        ttk.Separator(frm, orient=tk.HORIZONTAL).grid(
            row=4, column=0, columnspan=3, sticky="ew", padx=12, pady=6,
        )

        # Always on top
        self._topmost_var = tk.BooleanVar(value=self._config.overlay_always_on_top)
        tk.Checkbutton(
            frm, text="Always on top", variable=self._topmost_var,
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=12)

        # Raise on hotkey
        self._raise_var = tk.BooleanVar(value=self._config.overlay_raise_on_hotkey)
        tk.Checkbutton(
            frm, text="Bring to front on hotkey press", variable=self._raise_var,
        ).grid(row=6, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 8))

        # Buttons
        btn_row = tk.Frame(frm)
        btn_row.grid(row=7, column=0, columnspan=3, pady=(4, 0))
        tk.Button(btn_row, text="Save",   command=self._save,   width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_row, text="Cancel", command=self.destroy, width=10).pack(side=tk.LEFT, padx=5)

    def _hotkey_row(self, parent, row):
        self._hotkey_entry = tk.Entry(
            parent, textvariable=self._hotkey_var, width=10,
            state="readonly", cursor="arrow",
        )
        self._hotkey_entry.grid(row=row, column=1, sticky="w", padx=12, pady=5)
        tk.Button(
            parent, text="Click to bind", command=self._start_bind, width=12,
        ).grid(row=row, column=2, padx=(0, 12), pady=5)

    def _start_bind(self):
        self._hotkey_var.set("Press a key…")
        self._hotkey_entry.configure(state="normal")
        self._binding = True
        self.bind("<KeyPress>", self._on_key)
        self._hotkey_entry.focus_set()

    def _on_key(self, event):
        if not self._binding:
            return
        key = event.keysym
        if key == "Escape":
            self._hotkey_var.set(self._config.hotkey)
        elif key not in ("Return", "Tab"):
            # Normalise: F9 → F9, a → a
            self._hotkey_var.set(key.upper() if len(key) > 1 else key)
        self._hotkey_entry.configure(state="readonly")
        self._binding = False
        self.unbind("<KeyPress>")

    def _center(self, parent):
        self.update_idletasks()
        px, py = parent.winfo_x(), parent.winfo_y()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h   = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        new = dict(
            model                 = self._model_var.get(),
            language              = self._lang_var.get().strip(),
            hotkey                = self._hotkey_var.get(),
            device                = self._device_var.get(),
            overlay_always_on_top = self._topmost_var.get(),
            overlay_raise_on_hotkey = self._raise_var.get(),
        )

        # Preserve unknown keys from existing TOML
        existing: dict = {}
        if self._config_path.exists():
            with open(self._config_path, "rb") as f:
                existing = tomllib.load(f)
        existing.update(new)

        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(_dump_toml(existing))

        needs_restart = (
            new["model"]  != self._config.model or
            new["device"] != self._config.device
        )

        self._on_save(**new)
        self.destroy()

        if needs_restart:
            messagebox.showinfo(
                "Restart required",
                "Model or device changes will take effect after restarting Murmur.",
            )


def _dump_toml(data: dict) -> str:
    lines = []
    for k, v in data.items():
        if isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        elif isinstance(v, (int, float)):
            lines.append(f"{k} = {v}")
    return "\n".join(lines) + "\n"
