from __future__ import annotations

import json
import os
import re
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
EDITION_FULL = "full"
EDITION_GMAIL_API_LIMITED = "gmail_api_limited"


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
    edition: str | None = None,
) -> UpdateCheckResult:
    manifest_url = load_update_manifest_url()
    if manifest_url:
        return _check_manifest(manifest_url, current_version, timeout)

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
    selected_edition = (
        edition or os.environ.get("POWER_ACCESSIBLE_MAIL_EDITION", EDITION_FULL)
    ).strip().lower()
    return _check_github_release(repository, current_version, selected_edition, timeout)


def _check_manifest(
    manifest_url: str,
    current_version: str,
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
    download_url = str(manifest.get("download_url") or manifest.get("url") or "").strip()
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
        notes=notes,
    )


def _check_github_release(
    repository: str,
    current_version: str,
    edition: str,
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
        fallback = _check_github_latest_page(repository, current_version, timeout)
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
        fallback = _check_github_latest_page(repository, current_version, timeout)
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
    download_url = select_installer_asset(release.get("assets"), edition) or release_url
    notes = str(release.get("body") or "").strip()
    return _result_for_release(
        current_version=current_version,
        latest_version=latest_version,
        download_url=download_url,
        notes=notes,
    )


def _check_github_latest_page(
    repository: str,
    current_version: str,
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
    return _result_for_release(
        current_version=current_version,
        latest_version=latest_version,
        download_url=release_url,
        notes="",
    )


def _read_json_response(request: urllib.request.Request, timeout: int) -> object:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read(MAX_UPDATE_RESPONSE_BYTES + 1)
    if len(payload) > MAX_UPDATE_RESPONSE_BYTES:
        raise ValueError("استجابة التحديثات أكبر من الحجم المسموح.")
    return json.loads(payload.decode("utf-8"))


def select_installer_asset(assets: object, edition: str) -> str:
    if not isinstance(assets, list):
        return ""
    candidates: list[tuple[int, str]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "").strip()
        url = _https_url(asset.get("browser_download_url"))
        if not name or not url or not name.lower().endswith(".exe"):
            continue
        score = _installer_asset_score(name, edition)
        if score >= 0:
            candidates.append((score, url))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _installer_asset_score(name: str, edition: str) -> int:
    lower_name = name.lower()
    if edition == EDITION_GMAIL_API_LIMITED:
        if lower_name.startswith("poweraccessiblemailsetup-"):
            score = 100
        elif lower_name.startswith("poweraccessiblemailgmailapilimitedsetup-"):
            score = 90
        else:
            return -1
    else:
        if not lower_name.startswith("poweraccessiblemailfullsetup-"):
            return -1
        score = 100
    if "win-x64" in lower_name:
        score += 5
    if "unsigned" in lower_name:
        score -= 10
    return score


def _result_for_release(
    *,
    current_version: str,
    latest_version: str,
    download_url: str,
    notes: str,
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
