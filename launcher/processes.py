"""
Processes running on this machine, identified by their id and their start time, since Windows reuses the id of an
ended process (after a reboot, for instance).
"""

import ctypes
from ctypes import wintypes

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
# INFO: Windows file times count 100 nanoseconds since 1601, Unix timestamps count seconds since 1970
FILE_TIME_UNITS_PER_SECOND = 10_000_000
FILE_TIME_UNIX_EPOCH = 116_444_736_000_000_000
START_TIME_TOLERANCE_SECONDS = 1.0

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
kernel32.GetProcessTimes.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


def read_start_time(pid):
    """Returns the start time of the process as a timestamp, or None when no process has this id."""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)

    if not handle:
        return None

    try:
        creation_time, exit_time, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))

        if not kernel32.GetProcessTimes(
            handle, ctypes.byref(creation_time), ctypes.byref(exit_time), ctypes.byref(kernel_time), ctypes.byref(user_time)
        ):
            return None

        # INFO: An ended process stays openable while a handle on it is kept, but its exit time is then filled
        if exit_time.dwHighDateTime or exit_time.dwLowDateTime:
            return None

        file_time = (creation_time.dwHighDateTime << 32) | creation_time.dwLowDateTime

        return (file_time - FILE_TIME_UNIX_EPOCH) / FILE_TIME_UNITS_PER_SECOND
    finally:
        kernel32.CloseHandle(handle)


def is_running(pid, started_at):
    """Returns whether the process with this id is running and started at started_at."""
    start_time = read_start_time(pid)

    return start_time is not None and abs(start_time - started_at) < START_TIME_TOLERANCE_SECONDS
