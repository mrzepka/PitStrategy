# Build with: pyinstaller pitstrategy.spec
# Produces dist/PitStrategy/PitStrategy.exe (onedir -- see notes below).
#
# run.py starts the FastAPI/uvicorn server on the main thread, which in turn
# spawns server/webview_launcher.py as *subprocesses* for the overlay/
# settings windows (see server/browser.py's docstring for why -- pywebview's
# event loop needs to own a process's main thread, and this process's main
# thread is already committed to uvicorn.run()). Running from source, those
# subprocesses are `python -m server.webview_launcher <role> <url>`. A
# frozen exe has no real "python -m" to fall back on (sys.executable there
# is PitStrategy.exe itself, not a Python interpreter), so
# server/browser.py detects sys.frozen and instead reruns this *same* exe
# with `--webview-window <role> <url>`, which run.py's main() intercepts
# before any normal server-startup argument parsing and dispatches straight
# to server.webview_launcher.main() -- see run.py's own module docstring
# for the full version of this.
#
# Onedir (COLLECT), not onefile: onefile self-extracts to a fresh temp
# directory on every launch, which is slower and has been flaky in the past
# for pywebview/pythonnet builds (DLL search-path issues during
# self-extraction). Onedir starts faster and is more reliable for a
# WebView2-based app; distribute the whole dist/PitStrategy/ folder (zip it)
# rather than just the .exe.
#
# console=True (a visible console window) is deliberate for now, not an
# oversight -- this app is still under active iteration, and startup errors
# (missing WebView2 runtime, pyirsdk failing to attach, etc.) are much
# easier to diagnose with visible output than silently failing behind a
# windowed app. Switch to console=False once it's stable enough that this
# stops being useful.

from PyInstaller.utils.hooks import collect_all

datas = [("server/static", "server/static")]
binaries = []
hiddenimports = ["irsdk"]

# These three have historically needed explicit collection with PyInstaller
# (dynamic .NET interop for pythonnet/clr_loader, and uvicorn's
# dynamically-selected loop/protocol implementations) -- collect_all() is
# the belt-and-suspenders approach the PyInstaller docs recommend when a
# package's own hook (if any) doesn't catch everything.
for pkg in ["webview", "clr_loader", "uvicorn"]:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PitStrategy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="PitStrategy",
)
