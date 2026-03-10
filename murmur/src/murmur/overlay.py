import sys
from typing import Callable

import wx

_BG = wx.Colour(43, 43, 43)  # #2b2b2b
_BG_DARK = wx.Colour(30, 30, 30)  # #1e1e1e
_FG = wx.Colour(204, 204, 204)  # #cccccc
_FG_DIM = wx.Colour(136, 136, 136)  # #888888

_BAR_W = 140
_BAR_H = 12

_STATE_COLORS = {
    "idle": wx.Colour(136, 136, 136),
    "recording": wx.Colour(221, 51, 51),
    "transcribing": wx.Colour(221, 153, 32),
}


class _DotPanel(wx.Panel):
    """Small custom-drawn circle showing the current state color."""

    def __init__(self, parent):
        super().__init__(parent, size=(14, 14))
        self.SetBackgroundColour(_BG)
        self._color = _STATE_COLORS["idle"]
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)

    def set_color(self, color: wx.Colour):
        self._color = color
        self.Refresh()

    def _on_paint(self, event):
        dc = wx.PaintDC(self)
        dc.SetBackground(wx.Brush(_BG))
        dc.Clear()
        dc.SetBrush(wx.Brush(self._color))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawCircle(7, 7, 5)


class _LevelBar(wx.Panel):
    """Custom-drawn level bar (filled rectangle with optional border)."""

    def __init__(self, parent):
        super().__init__(parent, size=(_BAR_W, _BAR_H))
        self.SetBackgroundColour(_BG_DARK)
        self._fill = 0
        self._border_color = wx.Colour(68, 68, 68)  # #444
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)

    def set_fill(self, fraction: float, border_color: wx.Colour = None):
        self._fill = max(0.0, min(1.0, fraction))
        if border_color is not None:
            self._border_color = border_color
        self.Refresh()

    def _on_paint(self, event):
        dc = wx.PaintDC(self)
        w, h = self.GetSize()
        dc.SetBackground(wx.Brush(_BG_DARK))
        dc.Clear()
        # Fill
        filled_w = int(self._fill * w)
        if filled_w > 0:
            dc.SetBrush(wx.Brush(wx.Colour(76, 175, 80)))  # #4caf50
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRectangle(0, 0, filled_w, h)
        # Border
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.SetPen(wx.Pen(self._border_color, 1))
        dc.DrawRectangle(0, 0, w, h)


class OverlayWindow(wx.Frame):
    def __init__(
        self,
        config,
        on_settings: Callable,
        on_quit: Callable,
        get_rms: Callable,
        on_move: Callable = None,
    ):
        style = wx.FRAME_NO_TASKBAR | wx.STAY_ON_TOP | wx.BORDER_NONE
        if sys.platform == "darwin":
            style |= wx.FRAME_TOOL_WINDOW
        super().__init__(None, style=style)

        self._config = config
        self._on_settings = on_settings
        self._on_quit = on_quit
        self._get_rms = get_rms
        self._on_move = on_move
        self._state = "idle"
        self._history: list[str] = []
        self._history_visible = False
        self._drag_start_pos = None

        self.SetBackgroundColour(_BG)
        self._build()
        self._place_initial()

        if not config.overlay_always_on_top:
            self.SetWindowStyleFlag(self.GetWindowStyleFlag() & ~wx.STAY_ON_TOP)

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self._timer)
        self._timer.Start(80)

        self.Show()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ── Toolbar row ───────────────────────────────────────────────────────
        self._toolbar = wx.Panel(self)
        self._toolbar.SetBackgroundColour(_BG)
        bar_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Status dot
        self._dot = _DotPanel(self._toolbar)
        bar_sizer.Add(self._dot, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 4)

        # Level bar
        self._level_bar = _LevelBar(self._toolbar)
        bar_sizer.Add(self._level_bar, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        # Status label
        self._status_lbl = wx.StaticText(self._toolbar, label="idle")
        self._status_lbl.SetForegroundColour(_FG_DIM)
        self._status_lbl.SetBackgroundColour(_BG)
        self._status_lbl.SetMinSize((88, -1))
        bar_sizer.Add(self._status_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)

        # History toggle button
        self._hist_btn = self._make_btn(self._toolbar, "▼", self._toggle_history)
        bar_sizer.Add(self._hist_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)

        # Settings button
        settings_btn = self._make_btn(self._toolbar, "⚙", self._on_settings)
        bar_sizer.Add(settings_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)

        # Quit button
        quit_btn = self._make_btn(self._toolbar, "✕", self._on_quit)
        bar_sizer.Add(quit_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        self._toolbar.SetSizer(bar_sizer)
        bar_sizer.Fit(self._toolbar)
        main_sizer.Add(self._toolbar, 0, wx.EXPAND)

        # ── History panel (hidden initially) ──────────────────────────────────
        self._hist_panel = wx.Panel(self)
        self._hist_panel.SetBackgroundColour(_BG_DARK)
        hist_sizer = wx.BoxSizer(wx.VERTICAL)

        self._hist_text = wx.TextCtrl(
            self._hist_panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_NONE,
            size=(_BAR_W + 200, 100),
        )
        self._hist_text.SetBackgroundColour(_BG_DARK)
        self._hist_text.SetForegroundColour(_FG)
        hist_sizer.Add(self._hist_text, 1, wx.EXPAND | wx.ALL, 4)
        self._hist_panel.SetSizer(hist_sizer)
        self._hist_panel.Hide()
        main_sizer.Add(self._hist_panel, 0, wx.EXPAND)

        self.SetSizer(main_sizer)
        main_sizer.Fit(self)

        # ── Drag bindings ─────────────────────────────────────────────────────
        for w in (self._toolbar, self._status_lbl, self._level_bar):
            w.Bind(wx.EVT_LEFT_DOWN, self._drag_start)
            w.Bind(wx.EVT_LEFT_UP, self._drag_end)
            w.Bind(wx.EVT_MOTION, self._drag_motion)

    def _make_btn(self, parent, label: str, handler: Callable) -> wx.Button:
        btn = wx.Button(parent, label=label, style=wx.BORDER_NONE | wx.BU_EXACTFIT)
        btn.SetBackgroundColour(_BG)
        btn.SetForegroundColour(_FG_DIM)
        btn.Bind(wx.EVT_BUTTON, lambda e: handler())
        btn.Bind(wx.EVT_ENTER_WINDOW, lambda e: btn.SetForegroundColour(_FG))
        btn.Bind(wx.EVT_LEAVE_WINDOW, lambda e: btn.SetForegroundColour(_FG_DIM))
        return btn

    # ── Positioning ───────────────────────────────────────────────────────────

    def _place_initial(self):
        if self._config.overlay_x >= 0 and self._config.overlay_y >= 0:
            self.SetPosition((self._config.overlay_x, self._config.overlay_y))
        else:
            display = wx.Display(0)
            geom = display.GetGeometry()
            w, h = self.GetSize()
            x = geom.x + geom.width - w - 20
            y = geom.y + geom.height - h - 80
            self.SetPosition((x, y))

    def _drag_start(self, event):
        screen_pos = event.GetEventObject().ClientToScreen(event.GetPosition())
        win_pos = self.GetPosition()
        self._drag_start_pos = (screen_pos.x - win_pos.x, screen_pos.y - win_pos.y)

    def _drag_motion(self, event):
        if (
            self._drag_start_pos is None
            or not event.Dragging()
            or not event.LeftIsDown()
        ):
            return
        screen_pos = event.GetEventObject().ClientToScreen(event.GetPosition())
        x = screen_pos.x - self._drag_start_pos[0]
        y = screen_pos.y - self._drag_start_pos[1]
        # Snap to taskbar
        display = wx.Display(0)
        geom = display.GetGeometry()
        sh = geom.y + geom.height
        h = self.GetSize().height
        if abs((y + h) - sh) < 40:
            y = sh - h - 2
        self.SetPosition((x, y))

    def _drag_end(self, event):
        if self._drag_start_pos is not None:
            self._drag_start_pos = None
            if self._on_move:
                pos = self.GetPosition()
                self._on_move(pos.x, pos.y)

    # ── State ─────────────────────────────────────────────────────────────────

    def set_state(self, state: str):
        self._state = state
        color = _STATE_COLORS.get(state, _STATE_COLORS["idle"])
        self._dot.set_color(color)
        self._status_lbl.SetLabel(state)
        self._status_lbl.SetForegroundColour(color if state != "idle" else _FG_DIM)
        border_color = color if state == "recording" else wx.Colour(68, 68, 68)
        self._level_bar.set_fill(self._level_bar._fill, border_color)
        self._toolbar.Layout()

    def add_transcription(self, text: str):
        if not text:
            return
        self._history.append(text)
        existing = self._hist_text.GetValue()
        if existing:
            self._hist_text.AppendText(f"\n→ {text}")
        else:
            self._hist_text.AppendText(f"→ {text}")
        self.set_state("idle")

    def raise_to_front(self):
        if not self._config.overlay_raise_on_hotkey:
            return
        self.Show()
        self.Raise()
        if sys.platform not in ("win32", "darwin"):
            # GTK ignores Raise() from non-focused apps; use xdotool windowraise.
            # windowactivate is avoided — it triggers synthetic clicks on
            # click-to-focus WMs, causing the settings dialog to open spuriously.
            import shutil
            import subprocess

            if shutil.which("xdotool"):
                subprocess.Popen(
                    ["xdotool", "windowraise", str(self.GetHandle())],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

    def apply_topmost(self, value: bool):
        self._config.overlay_always_on_top = value
        style = self.GetWindowStyleFlag()
        if value:
            style |= wx.STAY_ON_TOP
        else:
            style &= ~wx.STAY_ON_TOP
        self.SetWindowStyleFlag(style)

    # ── Level bar poll (timer) ─────────────────────────────────────────────────

    def _on_timer(self, event):
        if self._state == "recording":
            rms = self._get_rms()
            fraction = min(rms / 0.06, 1.0)
            border_color = _STATE_COLORS["recording"]
            self._level_bar.set_fill(fraction, border_color)
        else:
            self._level_bar.set_fill(0.0, wx.Colour(68, 68, 68))

    # ── History toggle ────────────────────────────────────────────────────────

    def _toggle_history(self):
        if self._history_visible:
            self._hist_panel.Hide()
            self._hist_btn.SetLabel("▼")
        else:
            self._hist_panel.Show()
            self._hist_btn.SetLabel("▲")
        self._history_visible = not self._history_visible
        self.GetSizer().Fit(self)
        self.Layout()

    # ── Misc ──────────────────────────────────────────────────────────────────

    def recenter(self):
        display = wx.Display(0)
        geom = display.GetGeometry()
        w, h = self.GetSize()
        x = geom.x + (geom.width - w) // 2
        y = geom.y + (geom.height - h) // 2
        self.SetPosition((x, y))
        if self._on_move:
            self._on_move(x, y)
