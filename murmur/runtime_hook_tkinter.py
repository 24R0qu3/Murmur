"""
Runtime hook: configure Tcl/Tk library paths for frozen (PyInstaller) builds.

When murmur is packaged as a single-file binary, the Tcl/Tk init scripts
(init.tcl, tk.tcl, …) are extracted alongside the binary's shared libs.
Python's tkinter needs TCL_LIBRARY and TK_LIBRARY to point at those dirs;
without this, it falls back to searching the host system and may fail.
"""
import os
import sys

if getattr(sys, "frozen", False):
    _mei = getattr(sys, "_MEIPASS", "")
    if _mei and os.path.isdir(_mei):
        for _name in os.listdir(_mei):
            _full = os.path.join(_mei, _name)
            if not os.path.isdir(_full):
                continue
            if _name.startswith("tcl") and "TCL_LIBRARY" not in os.environ:
                os.environ["TCL_LIBRARY"] = _full
            elif _name.startswith("tk") and "TK_LIBRARY" not in os.environ:
                os.environ["TK_LIBRARY"] = _full
