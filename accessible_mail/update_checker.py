from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import APP_VERSION, app_dir, data_dir


@dataclass(slots=True)
class UpdateCheckResult:
    configured: bool
    available: bool
    current_version: str
    latest_version: str = ""
    download_url: str = ""
    notes: str = ""
    message: str = ""


def update_manifest_url_paths() -> list[Path]:
    if getattr(sys, "frozen", False):
        runtime_dir = Path(sys.executable).resolve().parent
    else:
        runtime_dir = app_dir()
    return [
        runtime_dir / "update_manifest_url.txt",
        data_dir() / "update_manifest_url.txt",
    ]


def load_update_manifest_url() -> str:
    env_url = os.environ.get("POWER_ACCESSIBLE_MAIL_UPDATE_URL", "").strip()
    if env_url:
        return env_url
    for path in update_manifest_url_paths():
        if not path.exists():
            continue
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return ""


def check_for_updates(current_version: str = APP_VERSION, timeout: int = 20) -> UpdateCheckResult:
    manifest_url = load_update_manifest_url()
    if not manifest_url:
        return UpdateCheckResult(
            configured=False,
            available=False,
            current_version=current_version,
            message=(
                "لم يتم ضبط خادم التحديثات بعد. ضع رابط ملف التحديثات في "
                "update_manifest_url.txt بجانب البرنامج أو داخل مجلد بيانات المستخدم."
            ),
        )

    request = urllib.request.Request(
        manifest_url,
        headers={"User-Agent": f"PowerAccessibleMail/{current_version}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read(1024 * 1024)
    except (OSError, urllib.error.URLError) as exc:
        return UpdateCheckResult(
            configured=True,
            available=False,
            current_version=current_version,
            message=f"تعذر الاتصال بخادم التحديثات: {exc}",
        )

    try:
        manifest = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return UpdateCheckResult(
            configured=True,
            available=False,
            current_version=current_version,
            message="ملف التحديثات غير صالح. يجب أن يكون بصيغة JSON.",
        )
    if not isinstance(manifest, dict):
        return UpdateCheckResult(
            configured=True,
            available=False,
            current_version=current_version,
            message="ملف التحديثات غير صالح.",
        )

    latest_version = str(manifest.get("version", "")).strip()
    download_url = str(manifest.get("download_url") or manifest.get("url") or "").strip()
    notes = str(manifest.get("notes", "")).strip()
    if not latest_version:
        return UpdateCheckResult(
            configured=True,
            available=False,
            current_version=current_version,
            message="ملف التحديثات لا يحتوي على رقم إصدار.",
        )

    available = version_key(latest_version) > version_key(current_version)
    message = (
        f"يوجد إصدار جديد {latest_version}."
        if available
        else f"أنت تستخدم آخر إصدار متاح: {current_version}."
    )
    return UpdateCheckResult(
        configured=True,
        available=available,
        current_version=current_version,
        latest_version=latest_version,
        download_url=download_url,
        notes=notes,
        message=message,
    )


def version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.replace("-", ".").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts or [0])
