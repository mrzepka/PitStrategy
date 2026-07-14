"""Launches the overlay (frameless/transparent) and settings (normal
windowed) windows via server/webview_launcher.py, each run as its own
subprocess. Used both at server startup (run.py, one of each) and
on-demand via POST /api/open-overlay / POST /api/open-settings, since the
user may close either window mid-session and want it back without
restarting the server.
"""
import subprocess
import sys


def _launch(role: str, url: str) -> str | None:
    """Returns "pywebview" on success, or None if the launch failed."""
    if getattr(sys, "frozen", False):
        # Frozen (PyInstaller) build: sys.executable is PitStrategy.exe
        # itself, not a python.exe -- there's no "-m" to fall back on. Rerun
        # this same exe with a special flag that run.py's main() intercepts
        # and dispatches straight to server.webview_launcher.main(), instead
        # of going through the normal server-startup argument parsing. See
        # run.py's module docstring / pitstrategy.spec's comments for the
        # full reasoning.
        args = [sys.executable, "--webview-window", role, url]
    else:
        args = [sys.executable, "-m", "server.webview_launcher", role, url]
    try:
        subprocess.Popen(args)
        return "pywebview"
    except OSError:
        return None


def open_overlay_window(url: str) -> str | None:
    return _launch("overlay", url)


def open_settings_window(url: str) -> str | None:
    return _launch("settings", url)
