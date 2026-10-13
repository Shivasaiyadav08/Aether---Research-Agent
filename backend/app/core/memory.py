"""Memory diagnostics and management utilities for Aether Research backend.

Provides cross-platform RSS memory tracking, environment tuning for OpenMP/glibc,
safe garbage collection triggers, and stage-by-stage memory logging without
exposing sensitive user data, document contents, or file paths.
"""

import gc
import logging
import os
import sys

logger = logging.getLogger("aether.memory")

# Windows psapi structures (cached at import time if on Windows)
_IS_WINDOWS = sys.platform == "win32"
_WIN_PMC = None
_WIN_GET_PROCESS_MEMORY_INFO = None
_WIN_PROCESS_HANDLE = None

if _IS_WINDOWS:
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        _WIN_PMC = PROCESS_MEMORY_COUNTERS_EX
        psapi = ctypes.windll.psapi
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        _WIN_GET_PROCESS_MEMORY_INFO = psapi.GetProcessMemoryInfo
        _WIN_PROCESS_HANDLE = ctypes.windll.kernel32.GetCurrentProcess()
    except Exception as exc:
        logger.debug("Windows psapi initialization failed: %s", exc)


def configure_process_memory_environment() -> None:
    """Configure runtime environment variables before heavy C extensions load.

    Restricts OpenMP, MKL, OpenBLAS and glibc memory arenas to prevent unbounded
    thread pools and virtual memory fragmentation on containers with small RAM limits.
    """
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
    os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
    # Limit glibc malloc arenas on Linux containers (glibc defaults to 8 * CPU cores)
    os.environ.setdefault("MALLOC_ARENA_MAX", "2")


def get_process_memory_mb() -> float:
    """Return the current resident set size (RSS) of the process in megabytes.

    Reads /proc/self/status on Linux (Render), psapi on Windows, and falls back
    to resource.getrusage. Returns 0.0 if unable to query.
    """
    # 1. Linux /proc/self/status (accurate for containers on Render)
    if os.path.exists("/proc/self/status"):
        try:
            with open("/proc/self/status", "r", encoding="utf-8") as status_file:
                for line in status_file:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            return round(int(parts[1]) / 1024.0, 2)
        except Exception:
            pass

    # 2. Windows via psapi WorkingSetSize
    if _IS_WINDOWS and _WIN_GET_PROCESS_MEMORY_INFO and _WIN_PMC and _WIN_PROCESS_HANDLE:
        try:
            import ctypes

            counters = _WIN_PMC()
            counters.cb = ctypes.sizeof(_WIN_PMC)
            if _WIN_GET_PROCESS_MEMORY_INFO(
                _WIN_PROCESS_HANDLE, ctypes.byref(counters), counters.cb
            ):
                return round(counters.WorkingSetSize / (1024.0 * 1024.0), 2)
        except Exception:
            pass

    # 3. Fallback to resource module (macOS / Unix)
    try:
        import resource

        # On macOS ru_maxrss is in bytes, on Linux it is in kilobytes
        ru_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return round(ru_rss / (1024.0 * 1024.0), 2)
        return round(ru_rss / 1024.0, 2)
    except Exception:
        pass

    return 0.0


def log_stage_memory(stage: str, **extra) -> float:
    """Record a memory diagnostic event with current process RSS.

    Does not log sensitive contents, file paths, or credentials.
    """
    rss = get_process_memory_mb()
    details = " ".join(f"{k}={v}" for k, v in extra.items()) if extra else ""
    logger.info("[Memory Stage: %s] RSS=%.2f MB %s", stage, rss, details)
    return rss


def check_and_collect_garbage(force: bool = False, threshold_mb: float = 400.0) -> float:
    """Optionally run garbage collection if RSS exceeds a specified threshold or forced.

    Returns the RSS in MB after check.
    """
    current_rss = get_process_memory_mb()
    if force or (threshold_mb > 0 and current_rss > threshold_mb):
        collected = gc.collect()
        after_rss = get_process_memory_mb()
        logger.debug(
            "Garbage collection executed (unreachable=%d): before=%.2f MB -> after=%.2f MB",
            collected,
            current_rss,
            after_rss,
        )
        return after_rss
    return current_rss
