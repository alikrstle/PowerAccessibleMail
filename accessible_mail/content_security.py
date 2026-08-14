from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class UnsafeImageError(RuntimeError):
    pass


IMAGE_FORMATS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("image/png", ".png", ("image/png",)),
    ("image/jpeg", ".jpg", ("image/jpeg", "image/jpg", "image/pjpeg")),
    ("image/gif", ".gif", ("image/gif",)),
    ("image/webp", ".webp", ("image/webp",)),
    ("image/bmp", ".bmp", ("image/bmp", "image/x-ms-bmp")),
    ("image/tiff", ".tiff", ("image/tiff",)),
    ("image/x-icon", ".ico", ("image/x-icon", "image/vnd.microsoft.icon")),
    ("image/avif", ".avif", ("image/avif",)),
)


def validate_and_scan_image(data: bytes, declared_content_type: str) -> tuple[str, str]:
    detected_type, extension = detect_raster_image_type(data)
    declared = declared_content_type.split(";", 1)[0].strip().casefold()
    aliases = next(
        aliases
        for content_type, _extension, aliases in IMAGE_FORMATS
        if content_type == detected_type
    )
    if declared and declared not in aliases:
        raise UnsafeImageError("نوع بيانات الصورة لا يطابق نوع الملف المعلن.")
    scan_bytes_with_antimalware(data)
    return detected_type, extension


def detect_raster_image_type(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", ".gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    if data.startswith(b"BM"):
        return "image/bmp", ".bmp"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff", ".tiff"
    if data.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon", ".ico"
    if (
        len(data) >= 16
        and data[4:8] == b"ftyp"
        and any(brand in data[8:32] for brand in (b"avif", b"avis"))
    ):
        return "image/avif", ".avif"
    raise UnsafeImageError(
        "تم رفض الملف لأن محتواه ليس صورة نقطية معروفة أو لأنه قد يحتوي على محتوى نشط."
    )


def scan_bytes_with_antimalware(data: bytes) -> None:
    if os.name != "nt":
        raise UnsafeImageError("فحص الصور يتطلب نظام Windows وبرنامج مكافحة فيروسات متوافقا.")
    try:
        result = _amsi_scan_buffer(data)
    except OSError as exc:
        raise UnsafeImageError("تعذر إكمال فحص الصورة بواسطة برنامج مكافحة الفيروسات.") from exc
    if result >= 32768 or 16384 <= result <= 20479:
        raise UnsafeImageError("رفض برنامج مكافحة الفيروسات الصورة لاشتباهه بوجود محتوى ضار.")


def _amsi_scan_buffer(data: bytes) -> int:
    amsi = ctypes.WinDLL("amsi.dll", use_last_error=True)
    amsi.AmsiInitialize.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    amsi.AmsiInitialize.restype = ctypes.c_long
    amsi.AmsiScanBuffer.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.ULONG,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint),
    ]
    amsi.AmsiScanBuffer.restype = ctypes.c_long
    amsi.AmsiUninitialize.argtypes = [ctypes.c_void_p]
    amsi.AmsiUninitialize.restype = None

    context = ctypes.c_void_p()
    result = ctypes.c_uint()
    initialize_status = amsi.AmsiInitialize("Power Accessible Mail", ctypes.byref(context))
    if initialize_status < 0 or not context.value:
        raise OSError(f"AMSI initialization failed: 0x{initialize_status & 0xFFFFFFFF:08X}")
    buffer = ctypes.create_string_buffer(data)
    try:
        scan_status = amsi.AmsiScanBuffer(
            context,
            ctypes.cast(buffer, ctypes.c_void_p),
            len(data),
            "Power Accessible Mail image",
            None,
            ctypes.byref(result),
        )
        if scan_status < 0:
            raise OSError(f"AMSI scan failed: 0x{scan_status & 0xFFFFFFFF:08X}")
        return int(result.value)
    finally:
        amsi.AmsiUninitialize(context)
