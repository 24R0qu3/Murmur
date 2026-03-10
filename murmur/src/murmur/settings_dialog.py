from pathlib import Path
from typing import Callable

import wx

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-reattr]

_MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
_DEVICES = ["auto", "cpu", "cuda"]
_WAKEWORD_MODELS = [
    "(none)",
    "hey_jarvis",
    "alexa",
    "hey_mycroft",
    "hey_rhasspy",
    "ok_google",
]


def _get_wakeword_models() -> list[str]:
    """Return available model names; tries openwakeword's own registry first."""
    try:
        import openwakeword

        # openwakeword >= 0.6 exposes MODELS; 0.4.x exposes models (lowercase)
        registry = getattr(openwakeword, "MODELS", None) or getattr(
            openwakeword, "models", None
        )
        if registry:
            return ["(none)"] + sorted(registry.keys())
    except Exception:
        pass
    return list(_WAKEWORD_MODELS)


class SettingsDialog(wx.Dialog):
    def __init__(
        self,
        parent,
        config,
        config_path: Path,
        on_save: Callable,
        on_recenter: Callable = None,
    ):
        super().__init__(
            parent,
            title="Murmur Settings",
            style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP,
        )
        self._config = config
        self._config_path = config_path
        self._on_save = on_save
        self._on_recenter = on_recenter
        self._binding = False

        self._build()
        self._center(parent)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        panel = wx.Panel(self)
        fgs = wx.FlexGridSizer(rows=0, cols=3, vgap=5, hgap=12)
        fgs.AddGrowableCol(1)

        def label(text):
            lbl = wx.StaticText(panel, label=text)
            return lbl

        def spacer():
            return wx.StaticText(panel, label="")

        # Model
        fgs.Add(label("Model"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        self._model_choice = wx.Choice(panel, choices=_MODELS)
        idx = _MODELS.index(self._config.model) if self._config.model in _MODELS else 0
        self._model_choice.SetSelection(idx)
        fgs.Add(self._model_choice, 0, wx.ALIGN_CENTER_VERTICAL)
        fgs.Add(spacer())

        # Language
        fgs.Add(label("Language"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        self._lang_ctrl = wx.TextCtrl(panel, value=self._config.language, size=(80, -1))
        fgs.Add(self._lang_ctrl, 0, wx.ALIGN_CENTER_VERTICAL)
        fgs.Add(spacer())

        # Hotkey
        fgs.Add(label("Hotkey"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        self._hotkey_ctrl = wx.TextCtrl(
            panel,
            value=self._config.hotkey,
            style=wx.TE_READONLY,
            size=(90, -1),
        )
        fgs.Add(self._hotkey_ctrl, 0, wx.ALIGN_CENTER_VERTICAL)
        self._bind_btn = wx.Button(panel, label="Click to bind")
        self._bind_btn.Bind(wx.EVT_BUTTON, self._start_bind)
        fgs.Add(self._bind_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        # Device
        fgs.Add(label("Device"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        self._device_choice = wx.Choice(panel, choices=_DEVICES)
        didx = (
            _DEVICES.index(self._config.device)
            if self._config.device in _DEVICES
            else 0
        )
        self._device_choice.SetSelection(didx)
        fgs.Add(self._device_choice, 0, wx.ALIGN_CENTER_VERTICAL)
        fgs.Add(spacer())

        # Separator
        sep1 = wx.StaticLine(panel)
        fgs.Add(sep1, 0, wx.EXPAND | wx.ALL, 4)
        fgs.AddSpacer(0)
        fgs.AddSpacer(0)

        # Wake word
        ww_current = self._config.wake_word or "(none)"
        ww_models = _get_wakeword_models()
        fgs.Add(label("Wake word"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        self._wakeword_combo = wx.ComboBox(
            panel,
            value=ww_current,
            choices=ww_models,
            style=wx.CB_DROPDOWN,
            size=(130, -1),
        )
        fgs.Add(self._wakeword_combo, 0, wx.ALIGN_CENTER_VERTICAL)
        fgs.Add(spacer())

        # Sensitivity
        fgs.Add(
            label("Sensitivity (0.10–1.00)"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8
        )
        self._thresh_spin = wx.TextCtrl(
            panel,
            value=f"{self._config.wake_word_threshold:.2f}",
            size=(80, -1),
        )
        fgs.Add(self._thresh_spin, 0, wx.ALIGN_CENTER_VERTICAL)
        fgs.Add(spacer())

        # Separator
        sep2 = wx.StaticLine(panel)
        fgs.Add(sep2, 0, wx.EXPAND | wx.ALL, 4)
        fgs.AddSpacer(0)
        fgs.AddSpacer(0)

        # Always on top
        self._topmost_cb = wx.CheckBox(panel, label="Always on top")
        self._topmost_cb.SetValue(self._config.overlay_always_on_top)
        fgs.Add(self._topmost_cb, 0, wx.LEFT | wx.BOTTOM, 8)
        fgs.AddSpacer(0)
        fgs.AddSpacer(0)

        # Raise on hotkey
        self._raise_cb = wx.CheckBox(panel, label="Bring to front on hotkey press")
        self._raise_cb.SetValue(self._config.overlay_raise_on_hotkey)
        fgs.Add(self._raise_cb, 0, wx.LEFT | wx.BOTTOM, 8)
        fgs.AddSpacer(0)
        fgs.AddSpacer(0)

        panel.SetSizer(fgs)
        fgs.Fit(panel)

        # Buttons
        btn_sizer = wx.StdDialogButtonSizer()
        save_btn = wx.Button(self, label="Save")
        save_btn.Bind(wx.EVT_BUTTON, lambda e: self._save())
        cancel_btn = wx.Button(self, wx.ID_CANCEL, label="Cancel")
        cancel_btn.Bind(wx.EVT_BUTTON, lambda e: self.Destroy())
        btn_sizer.Add(save_btn, 0, wx.ALL, 4)
        btn_sizer.Add(cancel_btn, 0, wx.ALL, 4)
        if self._on_recenter:
            recenter_btn = wx.Button(self, label="Recenter overlay")
            recenter_btn.Bind(wx.EVT_BUTTON, lambda e: self._on_recenter())
            btn_sizer.Add(recenter_btn, 0, wx.ALL, 4)
        btn_sizer.Realize()

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND | wx.ALL, 8)
        outer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.BOTTOM, 8)
        self.SetSizer(outer)
        outer.Fit(self)

    # ── Hotkey binding ────────────────────────────────────────────────────────

    def _start_bind(self, event=None):
        self._hotkey_ctrl.SetValue("Press a key…")
        self._hotkey_ctrl.SetEditable(True)
        self._binding = True
        self.Bind(wx.EVT_KEY_DOWN, self._on_key)
        self._hotkey_ctrl.SetFocus()

    def _on_key(self, event):
        if not self._binding:
            event.Skip()
            return
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_ESCAPE:
            self._hotkey_ctrl.SetValue(self._config.hotkey)
        elif keycode in (wx.WXK_RETURN, wx.WXK_TAB):
            event.Skip()
            return
        elif wx.WXK_F1 <= keycode <= wx.WXK_F24:
            fn = keycode - wx.WXK_F1 + 1
            self._hotkey_ctrl.SetValue(f"F{fn}")
        else:
            try:
                ch = chr(keycode)
                self._hotkey_ctrl.SetValue(ch.upper() if len(ch) > 1 else ch)
            except (ValueError, OverflowError):
                self._hotkey_ctrl.SetValue(self._config.hotkey)
        self._hotkey_ctrl.SetEditable(False)
        self._binding = False
        self.Unbind(wx.EVT_KEY_DOWN)

    def _center(self, parent):
        display = wx.Display(0)
        geom = display.GetGeometry()
        w, h = self.GetSize()
        x = geom.x + (geom.width - w) // 2
        y = geom.y + (geom.height - h) // 2
        self.SetPosition((x, y))

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        ww_raw = self._wakeword_combo.GetValue().strip()
        try:
            thresh = max(0.10, min(1.00, float(self._thresh_spin.GetValue())))
        except ValueError:
            thresh = self._config.wake_word_threshold
        new = dict(
            model=_MODELS[self._model_choice.GetSelection()],
            language=self._lang_ctrl.GetValue().strip(),
            hotkey=self._hotkey_ctrl.GetValue(),
            device=_DEVICES[self._device_choice.GetSelection()],
            wake_word="" if ww_raw == "(none)" else ww_raw,
            wake_word_threshold=thresh,
            overlay_always_on_top=self._topmost_cb.GetValue(),
            overlay_raise_on_hotkey=self._raise_cb.GetValue(),
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
            new["model"] != self._config.model or new["device"] != self._config.device
        )

        self._on_save(**new)
        self.Destroy()

        if needs_restart:
            wx.MessageBox(
                "Model or device changes will take effect after restarting Murmur.",
                "Restart required",
                wx.OK | wx.ICON_INFORMATION,
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
