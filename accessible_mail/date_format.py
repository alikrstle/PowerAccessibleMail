from __future__ import annotations

import ctypes
import sys
import unicodedata
from ctypes import wintypes
from datetime import datetime


DATE_LONGDATE = 0x00000002
TIME_NOSECONDS = 0x00000002


class SystemTime(ctypes.Structure):
    _fields_ = (
        ("year", wintypes.WORD),
        ("month", wintypes.WORD),
        ("day_of_week", wintypes.WORD),
        ("day", wintypes.WORD),
        ("hour", wintypes.WORD),
        ("minute", wintypes.WORD),
        ("second", wintypes.WORD),
        ("milliseconds", wintypes.WORD),
    )


def format_system_datetime(value: datetime) -> str:
    system_value = _windows_formatted_datetime(value)
    if system_value:
        return system_value
    return value.strftime("%A, %d %B %Y, %H:%M")


def format_message_date(timestamp: float, fallback: str = "") -> str:
    if timestamp <= 0:
        return fallback
    try:
        value = datetime.fromtimestamp(timestamp).astimezone()
    except (OverflowError, OSError, ValueError):
        return fallback
    return format_system_datetime(value)


def _windows_formatted_datetime(value: datetime) -> str:
    if sys.platform != "win32":
        return ""
    system_time = SystemTime(
        value.year,
        value.month,
        (value.weekday() + 1) % 7,
        value.day,
        value.hour,
        value.minute,
        value.second,
        value.microsecond // 1000,
    )
    try:
        kernel32 = ctypes.windll.kernel32
        _configure_windows_formatters(kernel32)
        date_text = _windows_date_text(
            kernel32,
            system_time,
            flags=DATE_LONGDATE,
        )
        weekday = _windows_date_text(
            kernel32,
            system_time,
            format_string="dddd",
        )
        time_text = _windows_time_text(kernel32, system_time)
    except (AttributeError, OSError, TypeError, ValueError):
        return ""
    if not date_text:
        return ""
    if weekday and weekday.casefold() not in date_text.casefold():
        date_text = f"{weekday}{_text_separator(weekday)}{date_text}"
    return f"{date_text}{_text_separator(date_text)}{time_text}" if time_text else date_text


def _configure_windows_formatters(kernel32: object) -> None:
    kernel32.GetDateFormatEx.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(SystemTime),
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.LPCWSTR,
    )
    kernel32.GetDateFormatEx.restype = ctypes.c_int
    kernel32.GetTimeFormatEx.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(SystemTime),
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        ctypes.c_int,
    )
    kernel32.GetTimeFormatEx.restype = ctypes.c_int


def _windows_date_text(
    kernel32: object,
    system_time: SystemTime,
    *,
    flags: int = 0,
    format_string: str | None = None,
) -> str:
    length = kernel32.GetDateFormatEx(
        None,
        flags,
        ctypes.byref(system_time),
        format_string,
        None,
        0,
        None,
    )
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length)
    if not kernel32.GetDateFormatEx(
        None,
        flags,
        ctypes.byref(system_time),
        format_string,
        buffer,
        length,
        None,
    ):
        return ""
    return buffer.value.strip()


def _windows_time_text(kernel32: object, system_time: SystemTime) -> str:
    length = kernel32.GetTimeFormatEx(
        None,
        TIME_NOSECONDS,
        ctypes.byref(system_time),
        None,
        None,
        0,
    )
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length)
    if not kernel32.GetTimeFormatEx(
        None,
        TIME_NOSECONDS,
        ctypes.byref(system_time),
        None,
        buffer,
        length,
    ):
        return ""
    return buffer.value.strip()


def _text_separator(text: str) -> str:
    for character in text:
        direction = unicodedata.bidirectional(character)
        if direction in {"R", "AL"}:
            return "، "
        if direction == "L":
            return ", "
    return ", "
