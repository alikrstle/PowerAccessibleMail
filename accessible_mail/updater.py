from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import threading
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .update_checker import UpdateCheckResult, normalize_sha256


MAX_INSTALLER_BYTES = 250 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 128 * 1024
ProgressCallback = Callable[[int, int], None]


class UpdateInstallError(RuntimeError):
    pass


class UpdateDownloadCancelled(UpdateInstallError):
    pass


def installer_name_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if parsed.scheme.lower() != "https":
        return ""
    name = Path(urllib.parse.unquote(parsed.path)).name
    if not re.fullmatch(
        r"PowerAccessibleMailSetup-[0-9A-Za-z.+-]+-win-(?:x64|x86)"
        r"(?:-UNSIGNED)?\.exe",
        name,
        flags=re.IGNORECASE,
    ):
        return ""
    return name


def can_install_update(result: UpdateCheckResult) -> bool:
    return bool(
        result.available
        and installer_name_from_url(result.download_url)
        and normalize_sha256(result.sha256)
    )


def download_update_installer(
    result: UpdateCheckResult,
    *,
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    target_root: Path | None = None,
    timeout: int = 90,
) -> Path:
    installer_name = installer_name_from_url(result.download_url)
    if not installer_name:
        raise UpdateInstallError(
            "لا يتوفر مثبت مباشر صالح لهذا التحديث."
        )
    expected_sha256 = normalize_sha256(result.sha256)
    if not expected_sha256:
        raise UpdateInstallError(
            "تعذر تحديث البرنامج بأمان لأن بصمة SHA-256 غير متوفرة."
        )

    root = target_root or (
        Path(tempfile.gettempdir())
        / "PowerAccessibleMail"
        / "updates"
        / result.latest_version
    )
    root.mkdir(parents=True, exist_ok=True)
    destination = root / installer_name
    partial = destination.with_suffix(destination.suffix + ".part")

    if destination.exists() and _verified_installer(
        destination,
        expected_sha256,
    ):
        if progress:
            size = destination.stat().st_size
            progress(size, size)
        return destination

    partial.unlink(missing_ok=True)
    request = urllib.request.Request(
        result.download_url,
        headers={"User-Agent": f"PowerAccessibleMail/{result.current_version}"},
    )
    downloaded = 0
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = response.geturl()
            if urllib.parse.urlparse(final_url).scheme.lower() != "https":
                raise UpdateInstallError(
                    "رفض البرنامج تنزيل التحديث من اتصال غير آمن."
                )
            total = _content_length(response)
            if total > MAX_INSTALLER_BYTES:
                raise UpdateInstallError("حجم ملف التحديث أكبر من الحد المسموح.")
            with partial.open("wb") as output:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise UpdateDownloadCancelled("تم إلغاء تنزيل التحديث.")
                    chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > MAX_INSTALLER_BYTES:
                        raise UpdateInstallError(
                            "حجم ملف التحديث أكبر من الحد المسموح."
                        )
                    output.write(chunk)
                    digest.update(chunk)
                    if progress:
                        progress(downloaded, total)
        if downloaded == 0:
            raise UpdateInstallError("ملف التحديث الذي تم تنزيله فارغ.")
        if digest.hexdigest() != expected_sha256:
            raise UpdateInstallError(
                "فشل التحقق من بصمة SHA-256 لملف التحديث."
            )
        if not _has_windows_executable_header(partial):
            raise UpdateInstallError("ملف التحديث ليس ملف Windows صالحا.")
        os.replace(partial, destination)
        return destination
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def launch_update_installer(installer_path: Path) -> subprocess.Popen[bytes]:
    path = Path(installer_path).resolve()
    if not path.is_file() or not _has_windows_executable_header(path):
        raise UpdateInstallError("ملف تثبيت التحديث غير صالح.")
    return subprocess.Popen(
        [
            str(path),
            "/SILENT",
            "/SP-",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/CLOSEAPPLICATIONS",
            "/UPDATEFROMAPP=1",
        ],
        close_fds=True,
    )


def _content_length(response: object) -> int:
    headers = getattr(response, "headers", None)
    if headers is None:
        return 0
    value = headers.get("Content-Length", "")
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _verified_installer(path: Path, expected_sha256: str) -> bool:
    if not path.is_file() or not _has_windows_executable_header(path):
        return False
    digest = hashlib.sha256()
    with path.open("rb") as installer:
        for chunk in iter(lambda: installer.read(DOWNLOAD_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected_sha256


def _has_windows_executable_header(path: Path) -> bool:
    try:
        with path.open("rb") as executable:
            return executable.read(2) == b"MZ"
    except OSError:
        return False
