import tkinter as tk
from pathlib import Path
from typing import Callable


_BG       = "#2b2b2b"
_BG_DARK  = "#1e1e1e"
_FG       = "#cccccc"
_FG_DIM   = "#888888"
_ACCENT   = "#4c9be8"
_BAR_W    = 140
_BAR_H    = 12

_STATE_COLORS = {
    "idle":         "#888888",
    "recording":    "#dd3333",
    "transcribing": "#dd9920",
}


class OverlayWindow:
    def __init__(
        self,
        root: tk.Tk,
        config,
        on_settings: Callable,
        on_quit: Callable,
        get_rms: Callable,
    ):
        self._root = root
        self._config = config
        self._on_settings = on_settings
        self._on_quit = on_quit
        self._get_rms = get_rms
        self._state = "idle"
        self._history: list[str] = []
        self._history_visible = False
        self._drag_x = 0
        self._drag_y = 0

        self._build()
        self._place_initial()
        self._poll_level()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        root = self._root
        root.overrideredirect(True)
        root.configure(bg=_BG)
        root.attributes("-topmost", self._config.overlay_always_on_top)

        # ── Toolbar row ───────────────────────────────────────────────────────
        bar = tk.Frame(root, bg=_BG, padx=6, pady=5)
        bar.pack(fill=tk.X)

        # Status dot
        self._dot_cv = tk.Canvas(bar, width=12, height=12, bg=_BG, highlightthickness=0)
        self._dot_cv.pack(side=tk.LEFT, padx=(0, 5))
        self._dot = self._dot_cv.create_oval(1, 1, 11, 11, fill=_STATE_COLORS["idle"], outline="")

        # Level bar
        self._bar_cv = tk.Canvas(
            bar, width=_BAR_W, height=_BAR_H,
            bg=_BG_DARK, highlightthickness=1, highlightbackground="#444",
        )
        self._bar_cv.pack(side=tk.LEFT, padx=(0, 8))
        self._bar_fill = self._bar_cv.create_rectangle(0, 0, 0, _BAR_H, fill="#4caf50", outline="")

        # Status label
        self._status_lbl = tk.Label(
            bar, text="idle", fg=_FG_DIM, bg=_BG,
            font=("Segoe UI", 9), width=11, anchor="w",
        )
        self._status_lbl.pack(side=tk.LEFT, padx=(0, 6))

        # History toggle
        self._hist_btn = self._icon_btn(bar, "▼", self._toggle_history)
        self._hist_btn.pack(side=tk.LEFT, padx=(0, 2))

        # Settings
        self._icon_btn(bar, "⚙", self._on_settings).pack(side=tk.LEFT, padx=(0, 2))

        # Hide (X) — hides overlay, keeps daemon running
        self._icon_btn(bar, "✕", self._hide, hover_bg="#aa2222").pack(side=tk.LEFT)

        # ── History panel (hidden initially) ──────────────────────────────────
        self._hist_frame = tk.Frame(root, bg=_BG_DARK)

        self._hist_text = tk.Text(
            self._hist_frame, height=6, bg=_BG_DARK, fg=_FG,
            font=("Segoe UI", 9), relief=tk.FLAT, state=tk.DISABLED,
            wrap=tk.WORD, insertbackground=_FG, selectbackground=_ACCENT,
        )
        sb = tk.Scrollbar(self._hist_frame, command=self._hist_text.yview, bg=_BG)
        self._hist_text.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._hist_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # ── Drag bindings ─────────────────────────────────────────────────────
        for w in (bar, self._status_lbl, self._bar_cv):
            w.bind("<ButtonPress-1>",   self._drag_start)
            w.bind("<B1-Motion>",       self._drag_motion)

    def _icon_btn(self, parent, text, cmd, hover_bg="#3b3b3b") -> tk.Button:
        btn = tk.Button(
            parent, text=text, fg=_FG_DIM, bg=_BG,
            activebackground=hover_bg, activeforeground="#ffffff",
            relief=tk.FLAT, font=("Segoe UI", 10), command=cmd,
            cursor="hand2", padx=4, pady=0, bd=0,
        )
        btn.bind("<Enter>", lambda e: btn.configure(fg="#ffffff"))
        btn.bind("<Leave>", lambda e: btn.configure(fg=_FG_DIM))
        return btn

    # ── Positioning ───────────────────────────────────────────────────────────

    def _place_initial(self):
        self._root.update_idletasks()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        w  = self._root.winfo_reqwidth()
        self._root.geometry(f"+{sw - w - 20}+{sh - 80}")

    def _drag_start(self, event):
        self._drag_x = event.x_root - self._root.winfo_x()
        self._drag_y = event.y_root - self._root.winfo_y()

    def _drag_motion(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        # Snap to taskbar
        sh = self._root.winfo_screenheight()
        h  = self._root.winfo_height()
        if abs((y + h) - sh) < 40:
            y = sh - h - 2
        self._root.geometry(f"+{x}+{y}")

    # ── State ─────────────────────────────────────────────────────────────────

    def set_state(self, state: str):
        self._state = state
        color = _STATE_COLORS.get(state, _STATE_COLORS["idle"])
        self._dot_cv.itemconfig(self._dot, fill=color)
        self._status_lbl.configure(
            text=state,
            fg=color if state != "idle" else _FG_DIM,
        )
        self._bar_cv.configure(
            highlightbackground=color if state == "recording" else "#444"
        )

    def add_transcription(self, text: str):
        if not text:
            return
        self._history.append(text)
        self._hist_text.configure(state=tk.NORMAL)
        if len(self._history) > 1:
            self._hist_text.insert(tk.END, "\n")
        self._hist_text.insert(tk.END, f"→ {text}")
        self._hist_text.see(tk.END)
        self._hist_text.configure(state=tk.DISABLED)
        self.set_state("idle")

    def raise_to_front(self):
        if self._config.overlay_raise_on_hotkey:
            self._root.deiconify()
            self._root.lift()
            self._root.attributes("-topmost", True)

    def apply_topmost(self, value: bool):
        self._config.overlay_always_on_top = value
        self._root.attributes("-topmost", value)

    # ── Level bar poll ────────────────────────────────────────────────────────

    def _poll_level(self):
        if self._state == "recording":
            rms    = self._get_rms()
            filled = int(min(rms / 0.06, 1.0) * _BAR_W)
            self._bar_cv.coords(self._bar_fill, 0, 0, filled, _BAR_H)
        else:
            self._bar_cv.coords(self._bar_fill, 0, 0, 0, _BAR_H)
        self._root.after(80, self._poll_level)

    # ── History toggle ────────────────────────────────────────────────────────

    def _toggle_history(self):
        if self._history_visible:
            self._hist_frame.pack_forget()
            self._hist_btn.configure(text="▼")
        else:
            self._hist_frame.pack(fill=tk.BOTH, expand=True)
            self._hist_btn.configure(text="▲")
        self._history_visible = not self._history_visible

    # ── Hide / show ───────────────────────────────────────────────────────────

    def _hide(self):
        self._root.withdraw()

    def show(self):
        self._root.deiconify()
        self._root.lift()
