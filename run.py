"""PitStrategy server entry point.

Also doubles as the frozen exe's entry point for launching overlay/settings
windows (see server/browser.py's _launch()): a PyInstaller-frozen exe has no
"python -m" to fall back on for spawning server/webview_launcher.py as a
subprocess, since sys.executable there is the exe itself, not a real Python
interpreter. So the frozen build reruns THIS SAME exe with
`--webview-window <role> <url>`, which main() below intercepts before
touching any of the normal server-startup argument parsing and dispatches
straight to server.webview_launcher.main(). Running from source
(`python run.py`) never takes this path -- server/browser.py only builds a
--webview-window command line when `sys.frozen` is set.
"""
import argparse
import sys
import threading
import time

import uvicorn

from server.app import create_app
from server.browser import open_overlay_window, open_settings_window


def _launch_windows(overlay_url: str, settings_url: str | None, delay_s: float = 1.5) -> None:
    """Waits for uvicorn to actually be listening, then opens the overlay and
    (if given a URL) settings windows -- fails soft, never crashes the
    server, since this is a convenience, not load-bearing. (Same on-demand
    paths are also exposed at runtime via POST /api/open-overlay /
    POST /api/open-settings for reopening a closed window mid-session.)"""
    time.sleep(delay_s)
    overlay = open_overlay_window(overlay_url)
    if overlay:
        print(f"[PitStrategy] Opened overlay in {overlay} ({overlay_url})")
    else:
        print(f"[PitStrategy] Could not auto-launch the overlay window -- open {overlay_url} manually.")

    if settings_url is None:
        return
    settings = open_settings_window(settings_url)
    if settings:
        print(f"[PitStrategy] Opened settings in {settings} ({settings_url})")
    else:
        print(f"[PitStrategy] Could not auto-launch the settings window -- open {settings_url} manually.")


def main() -> None:
    if len(sys.argv) >= 4 and sys.argv[1] == "--webview-window":
        from server.webview_launcher import main as webview_main

        webview_main(sys.argv[2:4])
        return

    parser = argparse.ArgumentParser(description="PitStrategy server")
    parser.add_argument("--demo", action="store_true", help="Use synthetic telemetry instead of live iRacing")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8734)
    parser.add_argument(
        "--no-open-overlay",
        action="store_true",
        help="Don't automatically open the overlay or settings windows on startup",
    )
    parser.add_argument(
        "--no-open-settings",
        action="store_true",
        help="Auto-open the overlay window as usual, but skip the settings window",
    )
    args = parser.parse_args()

    app = create_app(demo=args.demo)

    if not args.no_open_overlay:
        overlay_url = f"http://{args.host}:{args.port}/overlay"
        settings_url = None if args.no_open_settings else f"http://{args.host}:{args.port}/settings"
        threading.Thread(target=_launch_windows, args=(overlay_url, settings_url), daemon=True).start()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
