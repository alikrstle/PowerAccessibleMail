from __future__ import annotations

import hashlib
import os
import re
import subprocess
import threading
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .update_checker import UpdateCheckResult, current_architecture, normalize_sha256


MAX_INSTALLER_BYTES = 250 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 128 * 1024
ProgressCallback = Callable[[int, int], None]
INSTALLER_NAME_PATTERN = re.compile(
    r"PowerAccessibleMailSetup-(?P<version>[0-9A-Za-z.+-]+)-"
    r"win-(?P<architecture>x64|x86)(?:-UNSIGNED)?\.exe",
    flags=re.IGNORECASE,
)
UPDATE_VENDOR_DIRECTORY = "SoljanAlSharq"
UPDATE_PRODUCT_DIRECTORY = "PowerAccessibleMail"


class UpdateInstallError(RuntimeError):
    pass


class UpdateDownloadCancelled(UpdateInstallError):
    pass


def installer_name_from_url(url: str) -> str:
    return installer_details_from_url(url)[0]


def installer_details_from_url(url: str) -> tuple[str, str, str]:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        return "", "", ""
    name = Path(urllib.parse.unquote(parsed.path)).name
    match = INSTALLER_NAME_PATTERN.fullmatch(name)
    if not match:
        return "", "", ""
    return (
        name,
        match.group("version"),
        match.group("architecture").lower(),
    )


def normalized_update_version(value: str) -> str:
    version = str(value or "").strip()
    if version[:1].lower() == "v":
        version = version[1:]
    if (
        not re.fullmatch(r"[0-9A-Za-z.+-]+", version)
        or not any(character.isalnum() for character in version)
    ):
        return ""
    return version


def can_install_update(result: UpdateCheckResult) -> bool:
    installer_name, installer_version, installer_architecture = (
        installer_details_from_url(result.download_url)
    )
    latest_version = normalized_update_version(result.latest_version)
    return bool(
        result.available
        and installer_name
        and latest_version
        and installer_version.casefold() == latest_version.casefold()
        and installer_architecture == current_architecture()
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
    installer_name, installer_version, installer_architecture = (
        installer_details_from_url(result.download_url)
    )
    if not installer_name:
        raise UpdateInstallError(
            "لا يتوفر مثبت مباشر صالح لهذا التحديث."
        )
    latest_version = normalized_update_version(result.latest_version)
    if (
        not latest_version
        or installer_version.casefold() != latest_version.casefold()
    ):
        raise UpdateInstallError(
            "اسم مثبت التحديث لا يطابق رقم الإصدار المتاح."
        )
    if installer_architecture != current_architecture():
        raise UpdateInstallError(
            "معمارية مثبت التحديث لا تطابق معمارية البرنامج الحالي."
        )
    expected_sha256 = normalize_sha256(result.sha256)
    if not expected_sha256:
        raise UpdateInstallError(
            "تعذر تحديث البرنامج بأمان لأن بصمة SHA-256 غير متوفرة."
        )

    root = target_root or default_update_root(latest_version)
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
            "/NORESTART",
            "/CLOSEAPPLICATIONS",
            "/UPDATEFROMAPP=1",
        ],
        close_fds=True,
    )


def default_update_root(version: str) -> Path:
    local_app_data = str(os.environ.get("LOCALAPPDATA") or "").strip()
    if local_app_data:
        base = (
            Path(local_app_data)
            / UPDATE_VENDOR_DIRECTORY
            / UPDATE_PRODUCT_DIRECTORY
            / "Updates"
        )
    else:
        base = Path.home() / ".power_accessible_mail" / "updates"
    return base / version


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
