"""Launches the overlay (frameless/transparent) and settings (normal
windowed) windows via server/webview_launcher.py, each run as its own
subprocess. Used both at server startup (run.py, one of each) and
on-demand via POST /api/open-overlay / POST /api/open-settings, since the
user may close either window mid-session and want it back without
restarting the server.
"""
import subprocess
import sys

_job_handle: int | None = None


def _kill_on_close_job() -> int | None:
    """A Windows Job Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.

    Every overlay/settings subprocess launched below gets assigned to this
    job, so that whenever *this* process's own handle to the job goes away
    -- which Windows does automatically on any process exit, whether that's
    closing the main server's console window, Ctrl+C, an unhandled
    exception, or a hard kill from Task Manager -- Windows tears down every
    process still in the job too. Without this, closing the console window
    left the overlay/settings windows running as orphans pointing at a dead
    server (confirmed live: exactly this happened, leaving stray processes
    holding the port on the next launch). This is enforced by the OS at the
    kernel-object level, not by catching a signal in Python, which is what
    makes it reliable across every shutdown path, not just a clean one.
    """
    global _job_handle
    if sys.platform != "win32":
        return None
    if _job_handle is not None:
        return _job_handle

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_void_p),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    JobObjectExtendedLimitInformation = 9

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    kernel32.SetInformationJobObject(
        job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
    )

    _job_handle = job
    return job


def _assign_to_kill_on_close_job(pid: int) -> None:
    job = _kill_on_close_job()
    if job is None:
        return

    import ctypes

    PROCESS_TERMINATE = 0x0001
    PROCESS_SET_QUOTA = 0x0100

    kernel32 = ctypes.windll.kernel32
    hproc = kernel32.OpenProcess(PROCESS_TERMINATE | PROCESS_SET_QUOTA, False, pid)
    if hproc:
        kernel32.AssignProcessToJobObject(job, hproc)
        kernel32.CloseHandle(hproc)


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
        proc = subprocess.Popen(args)
        _assign_to_kill_on_close_job(proc.pid)
        return "pywebview"
    except OSError:
        return None


def open_overlay_window(url: str) -> str | None:
    return _launch("overlay", url)


def open_settings_window(url: str) -> str | None:
    return _launch("settings", url)
