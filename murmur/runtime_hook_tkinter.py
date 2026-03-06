"""
Runtime hook: configure Tcl/Tk library paths for frozen (PyInstaller) builds.

When murmur is packaged as a single-file binary, the Tcl/Tk init scripts
(init.tcl, tk.tcl, …) are extracted alongside the binary's shared libs.
Python's tkinter needs TCL_LIBRARY and TK_LIBRARY to point at those dirs;
without this, it falls back to searching the host system and may fail.

We also pre-load libtcl*.so / libtk*.so via ctypes so the dynamic linker
finds them before _tkinter is imported.  _tkinter.so may carry an RPATH
that points to the build-time Python home (which does not exist on the
user's machine).  Preloading via ctypes registers the libraries in the
process-global dlopen cache by their soname, so the subsequent implicit
dlopen() inside _tkinter succeeds regardless of RPATH.
"""
import glob
import os
import sys

if getattr(sys, "frozen", False):
    _mei = getattr(sys, "_MEIPASS", "")
    if _mei and os.path.isdir(_mei):
        # ── 1. Set TCL_LIBRARY / TK_LIBRARY for Tcl/Tk init scripts ──────────
        for _name in os.listdir(_mei):
            _full = os.path.join(_mei, _name)
            if not os.path.isdir(_full):
                continue
            if _name.startswith("tcl") and "TCL_LIBRARY" not in os.environ:
                os.environ["TCL_LIBRARY"] = _full
            elif _name.startswith("tk") and "TK_LIBRARY" not in os.environ:
                os.environ["TK_LIBRARY"] = _full

        # ── 2. Preload Tcl/Tk shared libs so _tkinter.so can find them ────────
        # Load libtcl before libtk (tk depends on tcl); sorted() gives that order.
        import ctypes

        for _pat in ("libtcl*.so*", "libtk*.so*"):
            for _p in sorted(glob.glob(os.path.join(_mei, _pat))):
                if os.path.isfile(_p):
                    try:
                        ctypes.CDLL(_p, mode=ctypes.RTLD_GLOBAL)
                    except OSError:
                        pass
