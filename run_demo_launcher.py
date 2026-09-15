"""Tiny standalone launcher for the demo build: finds PitStrategy.exe next to
itself and starts it with `--demo`, so someone can double-click a single file
to try the app with synthetic data -- no terminal, no typing a flag.

Built as its own separate tiny exe (see pitstrategy.spec) rather than
importing run.py directly, so it stays a few KB instead of pulling in the
full webview/uvicorn/pyirsdk dependency tree a second time -- it only ever
spawns the real PitStrategy.exe as a child process and gets out of the way.
"""
import subprocess
import sys
from pathlib import Path

CREATE_NEW_CONSOLE = 0x00000010  # child gets its own console window, same as double-clicking PitStrategy.exe directly


def main() -> None:
    exe_dir = Path(sys.executable).parent
    target = exe_dir / "PitStrategy.exe"
    if not target.exists():
        # This exe is built with console=False (see pitstrategy.spec) -- no
        # console of its own to print an error to, so a message box is the
        # only way to actually surface this instead of silently doing
        # nothing.
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            f"Couldn't find PitStrategy.exe next to this launcher in:\n{exe_dir}",
            "PitStrategy Demo",
            0x10,  # MB_ICONERROR
        )
        return
    subprocess.Popen([str(target), "--demo"], creationflags=CREATE_NEW_CONSOLE)


if __name__ == "__main__":
    main()
