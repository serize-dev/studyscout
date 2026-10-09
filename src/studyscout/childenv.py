"""Clean environment for child processes (browser, mail client).

The frozen (PyInstaller onefile) binary unpacks itself into a temp _MEI dir
and points LD_LIBRARY_PATH at it, saving the user's original value in
LD_LIBRARY_PATH_ORIG. Children inherit that, so Firefox/xdg-open start up
loading OUR bundled libraries instead of the system's and crash. glibc reads
LD_LIBRARY_PATH once at process start, so undoing it in os.environ is safe
for the running app and fixes every child — webbrowser.open included, which
has no env= parameter.
"""
from __future__ import annotations

import os
import sys


def child_env(environ=None, bundle_dir=None) -> dict:
    """Return a copy of `environ` with the PyInstaller bundle scrubbed out."""
    env = dict(os.environ if environ is None else environ)
    if bundle_dir is None:
        bundle_dir = getattr(sys, "_MEIPASS", None)
    if not bundle_dir:
        return env                                  # not frozen: hands off
    orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if orig:
        env["LD_LIBRARY_PATH"] = orig
    elif orig is not None:
        env.pop("LD_LIBRARY_PATH", None)            # user had none
    for key, val in list(env.items()):
        if bundle_dir in val:                       # any other path-list var
            kept = [p for p in val.split(os.pathsep) if p and bundle_dir not in p]
            if kept:
                env[key] = os.pathsep.join(kept)
            else:
                del env[key]
    return env


def scrub_environ() -> None:
    """Apply child_env() to os.environ in place (call once at startup)."""
    clean = child_env()
    for key in [k for k in os.environ if k not in clean]:
        del os.environ[key]
    for key, val in clean.items():
        if os.environ.get(key) != val:
            os.environ[key] = val
