"""Standalone entry point for a single overlay/settings window: `python -m
server.webview_launcher <overlay|settings> <url>`.

Runs as its own process (not a thread inside run.py) because pywebview's
event loop (webview.start()) needs to own the main thread of whatever
process calls it, and run.py's main thread is already committed to the
blocking uvicorn.run() call. Keeping it a separate process also means
closing this window never takes the server down with it, and reopening it
later (POST /api/open-overlay / POST /api/open-settings) is just spawning a
fresh one of these. The overlay and settings windows are launched as two
separate processes (run.py starts one of each at startup) rather than both
windows from one process, since that keeps this launcher's per-window logic
simple -- one process, one webview.start() call, one window.

pywebview (backed by Windows' WebView2 engine here) is what actually makes
`frameless=True` work as a real window property, which a plain `chrome
--app=` window can't do -- Chrome draws its own minimal chrome as custom UI
regardless of OS window styles.

`transparent=True` on its own is NOT enough on Windows, though: reading
pywebview's own edgechromium.py backend shows it only sets the WebView2
*control*'s background to transparent relative to its parent Form -- the
Form itself (the actual OS window) is never made transparent to the
desktop (no AllowTransparency/WS_EX_LAYERED setup exists for it there).
Left as-is, that shows the Form's own plain gray background through the
"transparent" web content instead of the desktop -- so real desktop
transparency is applied here ourselves, via the same Win32 layered-window
mechanism used by every other translucent-overlay tool.
"""
import sys
import time

import webview

WIDTH = 440
HEIGHT = 420
OVERLAY_WINDOW_TITLE = "PitStrategy Overlay"

SETTINGS_WIDTH = 340
SETTINGS_HEIGHT = 560
SETTINGS_WINDOW_TITLE = "PitStrategy Settings"

# 0 (fully invisible) - 255 (fully opaque), applied uniformly to the whole
# window by _apply_window_transparency(). Deliberately mild -- enough to see
# through to the game, not so much that the HUD stops being legible. Tune
# this if you want more or less see-through.
WINDOW_ALPHA = 235


class _Api:
    """Exposed to the page as `window.pywebview.api` -- lets overlay.js ask
    Python to resize the actual OS window (pywebview.Window.resize()) based
    on the page's own content size, since a page-level window.resizeTo()
    call isn't meaningful for a pywebview-hosted window the way it is for a
    real browser tab.

    The window reference is stored as `_window` (leading underscore), not
    `window` -- pywebview builds the JS bridge by walking every public
    attribute of this object and recursing into non-callable ones. A plain
    `self.window` attribute pointing at the real `webview.Window` sends that
    walk into `.native` (the raw .NET WinForms object) and from there into
    cyclic .NET properties like `SyncRoot`/`DataBindings...Families`.
    Pythonnet hands back a fresh wrapper on every attribute access, so
    pywebview's id()-based cycle detector never catches the repeat, and it
    recurses until Python's stack limit before a blanket except swallows it
    -- the "maximum recursion depth exceeded" spam in the console. Leading
    underscore makes pywebview skip the attribute entirely."""

    def __init__(self):
        self._window: webview.Window | None = None

    def resize(self, width: float, height: float) -> None:
        if self._window is not None:
            self._window.resize(round(width), round(height))


def _apply_window_transparency(attempts: int = 20, interval_s: float = 0.25) -> None:
    if sys.platform != "win32":
        return

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    LWA_ALPHA = 0x2

    for _ in range(attempts):
        matches: list[int] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _lparam):
            length = user32.GetWindowTextLengthW(hwnd)
            if length == len(OVERLAY_WINDOW_TITLE):
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if buf.value == OVERLAY_WINDOW_TITLE:
                    matches.append(hwnd)
            return True

        user32.EnumWindows(callback, 0)

        if matches:
            for hwnd in matches:
                exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, exstyle | WS_EX_LAYERED)
                user32.SetLayeredWindowAttributes(hwnd, 0, WINDOW_ALPHA, LWA_ALPHA)
            return
        time.sleep(interval_s)


def main(argv: list[str] | None = None) -> None:
    """`argv` is `[role, url]`. Defaults to `sys.argv[1:3]` for the normal
    `python -m server.webview_launcher <role> <url>` invocation; run.py's
    frozen-exe dispatch (see its module docstring) passes it explicitly
    instead, since a frozen exe has no `-m` to fall back on."""
    argv = sys.argv[1:3] if argv is None else argv
    if len(argv) < 2:
        print("Usage: python -m server.webview_launcher <overlay|settings> <url>", file=sys.stderr)
        sys.exit(1)

    role, url = argv[0], argv[1]

    if role == "overlay":
        api = _Api()
        window = webview.create_window(
            OVERLAY_WINDOW_TITLE,
            url,
            width=WIDTH,
            height=HEIGHT,
            frameless=True,
            easy_drag=True,  # lets the window be dragged from anywhere on its content -- no title bar to drag by
            transparent=True,
            on_top=True,
            resizable=True,
            js_api=api,
        )
        api._window = window
        webview.start(_apply_window_transparency)
    elif role == "settings":
        # A normal windowed window -- not frameless/transparent/on_top like
        # the overlay. _apply_window_transparency() only ever matches
        # windows titled exactly OVERLAY_WINDOW_TITLE, so this window is
        # left alone by it automatically; no special handling needed here.
        webview.create_window(
            SETTINGS_WINDOW_TITLE,
            url,
            width=SETTINGS_WIDTH,
            height=SETTINGS_HEIGHT,
            resizable=True,
        )
        webview.start()
    else:
        print(f"Unknown window role: {role!r} (expected 'overlay' or 'settings')", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
