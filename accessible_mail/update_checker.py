from __future__ import annotations

import json
import os
import re
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import APP_VERSION, app_dir, data_dir


DEFAULT_GITHUB_REPOSITORY = "alikrstle/PowerAccessibleMail"
GITHUB_API_VERSION = "2026-03-10"
MAX_UPDATE_RESPONSE_BYTES = 1024 * 1024
ARCHITECTURE_X64 = "x64"
ARCHITECTURE_X86 = "x86"


@dataclass(slots=True)
class UpdateCheckResult:
    configured: bool
    available: bool
    current_version: str
    latest_version: str = ""
    download_url: str = ""
    sha256: str = ""
    release_date: str = ""
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


def load_github_repository() -> str:
    configured = os.environ.get(
        "POWER_ACCESSIBLE_MAIL_GITHUB_REPOSITORY",
        DEFAULT_GITHUB_REPOSITORY,
    ).strip()
    if configured.startswith(("https://github.com/", "http://github.com/")):
        configured = urllib.parse.urlparse(configured).path.strip("/")
    if configured.endswith(".git"):
        configured = configured[:-4]
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", configured):
        return configured
    return ""


def updates_configured() -> bool:
    return bool(load_update_manifest_url() or load_github_repository())


def check_for_updates(
    current_version: str = APP_VERSION,
    timeout: int = 20,
    architecture: str | None = None,
) -> UpdateCheckResult:
    selected_architecture = normalize_architecture(
        architecture
        or os.environ.get("POWER_ACCESSIBLE_MAIL_ARCHITECTURE", "")
        or current_architecture()
    )
    manifest_url = load_update_manifest_url()
    if manifest_url:
        return _check_manifest(
            manifest_url,
            current_version,
            selected_architecture,
            timeout,
        )

    repository = load_github_repository()
    if not repository:
        return UpdateCheckResult(
            configured=False,
            available=False,
            current_version=current_version,
            message=(
                "لم يتم ضبط مصدر التحديثات. اضبط مستودع GitHub في متغير البيئة "
                "POWER_ACCESSIBLE_MAIL_GITHUB_REPOSITORY."
            ),
        )
    return _check_github_release(
        repository,
        current_version,
        selected_architecture,
        timeout,
    )


def current_architecture() -> str:
    return ARCHITECTURE_X64 if struct.calcsize("P") == 8 else ARCHITECTURE_X86


def normalize_architecture(value: str) -> str:
    normalized = str(value or "").strip().lower().removeprefix("win-")
    if normalized in {ARCHITECTURE_X64, "amd64", "64", "64bit"}:
        return ARCHITECTURE_X64
    if normalized in {ARCHITECTURE_X86, "i386", "i686", "32", "32bit"}:
        return ARCHITECTURE_X86
    return current_architecture()


def _check_manifest(
    manifest_url: str,
    current_version: str,
    architecture: str,
    timeout: int,
) -> UpdateCheckResult:
    request = urllib.request.Request(
        manifest_url,
        headers={"User-Agent": f"PowerAccessibleMail/{current_version}"},
    )
    try:
        manifest = _read_json_response(request, timeout)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return UpdateCheckResult(
            configured=True,
            available=False,
            current_version=current_version,
            message="ملف التحديثات غير صالح. يجب أن يكون بصيغة JSON.",
        )
    except (OSError, urllib.error.URLError, ValueError) as exc:
        return UpdateCheckResult(
            configured=True,
            available=False,
            current_version=current_version,
            message=f"تعذر الاتصال بخادم التحديثات: {exc}",
        )

    if not isinstance(manifest, dict):
        return UpdateCheckResult(
            configured=True,
            available=False,
            current_version=current_version,
            message="ملف التحديثات غير صالح.",
        )

    latest_version = str(manifest.get("version", "")).strip()
    downloads = manifest.get("downloads")
    architecture_download = (
        downloads.get(architecture)
        if isinstance(downloads, dict)
        else ""
    )
    if isinstance(architecture_download, dict):
        architecture_url = (
            architecture_download.get("download_url")
            or architecture_download.get("url")
            or ""
        )
        architecture_sha256 = architecture_download.get("sha256")
    else:
        architecture_url = architecture_download
        architecture_sha256 = ""
    download_url = str(
        architecture_url
        or manifest.get("download_url")
        or manifest.get("url")
        or ""
    ).strip()
    checksums = manifest.get("sha256")
    if isinstance(checksums, dict):
        manifest_sha256 = checksums.get(architecture)
    else:
        manifest_sha256 = checksums
    sha256 = normalize_sha256(architecture_sha256 or manifest_sha256)
    release_date = str(
        manifest.get("release_date")
        or manifest.get("published_at")
        or ""
    ).strip()
    notes = str(manifest.get("notes", "")).strip()
    if not latest_version:
        return UpdateCheckResult(
            configured=True,
            available=False,
            current_version=current_version,
            message="ملف التحديثات لا يحتوي على رقم إصدار.",
        )
    return _result_for_release(
        current_version=current_version,
        latest_version=latest_version,
        download_url=download_url,
        sha256=sha256,
        release_date=release_date,
        notes=notes,
    )


def _check_github_release(
    repository: str,
    current_version: str,
    architecture: str,
    timeout: int,
) -> UpdateCheckResult:
    owner, repo = repository.split("/", 1)
    api_url = (
        "https://api.github.com/repos/"
        f"{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/releases/latest"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": f"PowerAccessibleMail/{current_version}",
    }
    github_token = os.environ.get("POWER_ACCESSIBLE_MAIL_GITHUB_TOKEN", "").strip()
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    request = urllib.request.Request(api_url, headers=headers)
    try:
        release = _read_json_response(request, timeout)
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        exc.close()
        if status_code == 404:
            return _no_github_release(current_version)
        fallback = _check_github_latest_page(
            repository,
            current_version,
            architecture,
            timeout,
        )
        if fallback is not None:
            return fallback
        return _github_connection_error(current_version, f"HTTP {status_code}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return UpdateCheckResult(
            configured=True,
            available=False,
            current_version=current_version,
            message="استجابة GitHub Releases غير صالحة.",
        )
    except (OSError, urllib.error.URLError, ValueError) as exc:
        fallback = _check_github_latest_page(
            repository,
            current_version,
            architecture,
            timeout,
        )
        if fallback is not None:
            return fallback
        return _github_connection_error(current_version, str(exc))

    if not isinstance(release, dict):
        return UpdateCheckResult(
            configured=True,
            available=False,
            current_version=current_version,
            message="استجابة GitHub Releases غير صالحة.",
        )

    latest_version = _version_from_tag(str(release.get("tag_name", "")))
    if not latest_version:
        return UpdateCheckResult(
            configured=True,
            available=False,
            current_version=current_version,
            message="إصدار GitHub لا يحتوي على رقم إصدار صالح.",
        )

    release_url = _https_url(release.get("html_url"))
    download_url, sha256 = select_installer_asset_details(
        release.get("assets"),
        architecture,
    )
    download_url = download_url or release_url
    release_date = str(
        release.get("published_at")
        or release.get("created_at")
        or ""
    ).strip()
    notes = str(release.get("body") or "").strip()
    return _result_for_release(
        current_version=current_version,
        latest_version=latest_version,
        download_url=download_url,
        sha256=sha256,
        release_date=release_date,
        notes=notes,
    )


def _check_github_latest_page(
    repository: str,
    current_version: str,
    architecture: str,
    timeout: int,
) -> UpdateCheckResult | None:
    latest_url = f"https://github.com/{repository}/releases/latest"
    request = urllib.request.Request(
        latest_url,
        headers={
            "Accept": "text/html",
            "User-Agent": f"PowerAccessibleMail/{current_version}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(1)
            release_url = response.geturl()
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        exc.close()
        if status_code == 404:
            return _no_github_release(current_version)
        return None
    except (OSError, urllib.error.URLError):
        return None

    parsed = urllib.parse.urlparse(release_url)
    marker = "/releases/tag/"
    if parsed.netloc.lower() != "github.com" or marker not in parsed.path:
        return None
    tag = urllib.parse.unquote(parsed.path.split(marker, 1)[1]).strip("/")
    latest_version = _version_from_tag(tag)
    if not latest_version:
        return None
    download_url = (
        _find_public_installer(
            repository,
            tag,
            latest_version,
            architecture,
            current_version,
            timeout,
        )
        or release_url
    )
    return _result_for_release(
        current_version=current_version,
        latest_version=latest_version,
        download_url=download_url,
        notes="",
    )


def _find_public_installer(
    repository: str,
    tag: str,
    latest_version: str,
    architecture: str,
    current_version: str,
    timeout: int,
) -> str:
    base_name = f"PowerAccessibleMailSetup-{latest_version}-win-{architecture}"
    candidate_names = [f"{base_name}.exe", f"{base_name}-UNSIGNED.exe"]
    encoded_tag = urllib.parse.quote(tag, safe="")
    for name in candidate_names:
        encoded_name = urllib.parse.quote(name, safe="")
        url = (
            f"https://github.com/{repository}/releases/download/"
            f"{encoded_tag}/{encoded_name}"
        )
        request = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": f"PowerAccessibleMail/{current_version}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout):
                return url
        except urllib.error.HTTPError as exc:
            exc.close()
        except (OSError, urllib.error.URLError):
            continue
    return ""


def _read_json_response(request: urllib.request.Request, timeout: int) -> object:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read(MAX_UPDATE_RESPONSE_BYTES + 1)
    if len(payload) > MAX_UPDATE_RESPONSE_BYTES:
        raise ValueError("استجابة التحديثات أكبر من الحجم المسموح.")
    return json.loads(payload.decode("utf-8"))


def select_installer_asset(assets: object, architecture: str) -> str:
    return select_installer_asset_details(assets, architecture)[0]


def select_installer_asset_details(
    assets: object,
    architecture: str,
) -> tuple[str, str]:
    if not isinstance(assets, list):
        return "", ""
    candidates: list[tuple[int, str, str]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "").strip()
        url = _https_url(asset.get("browser_download_url"))
        if not name or not url or not name.lower().endswith(".exe"):
            continue
        score = _installer_asset_score(name, architecture)
        if score >= 0:
            candidates.append(
                (
                    score,
                    url,
                    normalize_sha256(asset.get("digest")),
                )
            )
    if not candidates:
        return "", ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1], candidates[0][2]


def _installer_asset_score(name: str, architecture: str) -> int:
    lower_name = name.lower()
    architecture = normalize_architecture(architecture)
    if not lower_name.startswith("poweraccessiblemailsetup-"):
        return -1
    if f"win-{architecture}" not in lower_name:
        return -1
    score = 100
    if "unsigned" in lower_name:
        score -= 10
    return score


def _result_for_release(
    *,
    current_version: str,
    latest_version: str,
    download_url: str,
    notes: str,
    sha256: str = "",
    release_date: str = "",
) -> UpdateCheckResult:
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
        sha256=normalize_sha256(sha256),
        release_date=release_date,
        notes=notes,
        message=message,
    )


def _no_github_release(current_version: str) -> UpdateCheckResult:
    return UpdateCheckResult(
        configured=True,
        available=False,
        current_version=current_version,
        message="لا يوجد إصدار منشور في GitHub Releases حتى الآن.",
    )


def _github_connection_error(current_version: str, details: str) -> UpdateCheckResult:
    return UpdateCheckResult(
        configured=True,
        available=False,
        current_version=current_version,
        message=f"تعذر الاتصال بـ GitHub Releases: {details}",
    )


def _https_url(value: object) -> str:
    url = str(value or "").strip()
    if urllib.parse.urlparse(url).scheme.lower() == "https":
        return url
    return ""


def normalize_sha256(value: object) -> str:
    checksum = str(value or "").strip().lower()
    if checksum.startswith("sha256:"):
        checksum = checksum[7:]
    return checksum if re.fullmatch(r"[0-9a-f]{64}", checksum) else ""


def _version_from_tag(tag: str) -> str:
    cleaned = tag.strip()
    match = re.fullmatch(
        r"[vV]?(\d+(?:\.\d+){1,3})(?:[-+][0-9A-Za-z.-]+)?",
        cleaned,
    )
    return match.group(1) if match else ""


def version_key(version: str) -> tuple[int, ...]:
    parts = [int(piece) for piece in re.findall(r"\d+", version)]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts or [0, 0, 0, 0])
