"""Small stdlib-only system information helpers."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import platform
import sys


def cpu_name() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                value, _value_type = winreg.QueryValueEx(key, "ProcessorNameString")
                if isinstance(value, str) and value.strip():
                    return " ".join(value.split())
        except OSError:
            pass

    candidates = [
        platform.processor(),
        platform.machine(),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return "Unknown"


def physical_cpu_cores() -> int | None:
    if sys.platform == "win32":
        return _windows_physical_core_count()
    return None


def logical_cpu_threads() -> int | None:
    return os.cpu_count()


def installed_memory() -> str:
    if sys.platform == "win32":
        return _windows_installed_memory()
    page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else None
    page_count = os.sysconf("SC_PHYS_PAGES") if hasattr(os, "sysconf") else None
    if isinstance(page_size, int) and isinstance(page_count, int):
        return format_bytes(page_size * page_count)
    return "Unknown"


def format_bytes(value: int) -> str:
    gib = value / (1024**3)
    if gib >= 10:
        return f"{gib:.0f} GB"
    return f"{gib:.1f} GB"


def _windows_installed_memory() -> str:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return format_bytes(status.ullTotalPhys)
    return "Unknown"


def _windows_physical_core_count() -> int | None:
    relation_processor_core = 0
    error_insufficient_buffer = 122
    ulong_ptr = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class SystemLogicalProcessorInformation(ctypes.Structure):
        _fields_ = [
            ("ProcessorMask", ulong_ptr),
            ("Relationship", ctypes.wintypes.DWORD),
            ("Reserved", ctypes.c_byte * 16),
        ]

    length = ctypes.wintypes.DWORD(0)
    result = ctypes.windll.kernel32.GetLogicalProcessorInformation(None, ctypes.byref(length))
    if result:
        return None
    if ctypes.windll.kernel32.GetLastError() not in {0, error_insufficient_buffer}:
        return None

    buffer = ctypes.create_string_buffer(length.value)
    result = ctypes.windll.kernel32.GetLogicalProcessorInformation(
        ctypes.cast(buffer, ctypes.POINTER(SystemLogicalProcessorInformation)),
        ctypes.byref(length),
    )
    if not result:
        return None

    entry_size = ctypes.sizeof(SystemLogicalProcessorInformation)
    if entry_size <= 0:
        return None

    entries = length.value // entry_size
    info_array = ctypes.cast(
        buffer,
        ctypes.POINTER(SystemLogicalProcessorInformation * entries),
    ).contents
    return sum(1 for entry in info_array if entry.Relationship == relation_processor_core)
