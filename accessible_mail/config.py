from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import Account


APP_NAME = os.environ.get("POWER_ACCESSIBLE_MAIL_APP_NAME", "PowerAccessibleMail")
APP_TITLE = os.environ.get("POWER_ACCESSIBLE_MAIL_APP_TITLE", "Power Accessible Mail")
APP_VERSION = "1.2.10"
PASSWORD_PREFIX = "dpapi:"
LEGACY_PROFILE_NAMES = ("PowerAccessibleMailGmailApiLimited",)
LANGUAGE_ARABIC = "ar"
LANGUAGE_ENGLISH = "en"
VIEWER_HTML = "html"
VIEWER_SIMPLE = "simple"
THEME_LIGHT = "light"
THEME_DARK = "dark"
TRANSLATION_INLINE = "inline"
TRANSLATION_DIALOG = "dialog"
_CONFIG_WRITE_LOCK = threading.RLock()
_PROFILE_MIGRATION_LOCK = threading.Lock()
_MIGRATED_PROFILE_ROOTS: set[Path] = set()


@dataclass(slots=True)
class ProgramSettings:
    language: str = LANGUAGE_ARABIC
    message_viewer: str = VIEWER_HTML
    theme: str = THEME_LIGHT
    translation_mode: str = TRANSLATION_DIALOG


def app_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        appdata_root = Path(appdata)
        root = appdata_root / APP_NAME
    else:
        appdata_root = None
        root = Path.home() / ".accessible_mail"
    root.mkdir(parents=True, exist_ok=True)
    if appdata_root is not None and APP_NAME == "PowerAccessibleMail":
        _migrate_legacy_profiles(appdata_root, root)
    return root


def _migrate_legacy_profiles(appdata_root: Path, destination: Path) -> None:
    resolved_destination = destination.resolve(strict=False)
    with _PROFILE_MIGRATION_LOCK:
        if resolved_destination in _MIGRATED_PROFILE_ROOTS:
            return
        marker = destination / ".unified-profile-migration-v1"
        if marker.exists():
            _MIGRATED_PROFILE_ROOTS.add(resolved_destination)
            return

        legacy_roots = [
            appdata_root / name
            for name in LEGACY_PROFILE_NAMES
            if (appdata_root / name).is_dir()
        ]
        if not legacy_roots:
            _MIGRATED_PROFILE_ROOTS.add(resolved_destination)
            return

        try:
            for legacy_root in legacy_roots:
                _merge_legacy_accounts(
                    legacy_root / "accounts.json",
                    destination / "accounts.json",
                )
                _copy_legacy_path_if_missing(
                    legacy_root / ".mail_store",
                    destination / ".mail_store",
                )
                _copy_legacy_path_if_missing(
                    legacy_root / "update_manifest_url.txt",
                    destination / "update_manifest_url.txt",
                )
            marker.write_text(
                "Merged legacy Gmail API profile into PowerAccessibleMail.\n",
                encoding="ascii",
            )
        except OSError:
            return
        _MIGRATED_PROFILE_ROOTS.add(resolved_destination)


def _merge_legacy_accounts(source: Path, destination: Path) -> None:
    source_payload = _read_json_with_backup(source)
    if not isinstance(source_payload, list):
        return
    destination_payload = _read_json_with_backup(destination)
    if not isinstance(destination_payload, list):
        destination_payload = []

    merged: list[object] = list(destination_payload)
    positions: dict[str, int] = {}
    for index, item in enumerate(merged):
        key = _account_migration_key(item)
        if key:
            positions[key] = index
    for item in source_payload:
        key = _account_migration_key(item)
        if key and key in positions:
            merged[positions[key]] = item
        else:
            if key:
                positions[key] = len(merged)
            merged.append(item)

    if destination.exists():
        backup = destination.with_name("accounts.pre-unified-backup.json")
        if not backup.exists():
            shutil.copy2(destination, backup)
    _atomic_write_json(destination, merged)


def _account_migration_key(item: object) -> str:
    if not isinstance(item, dict):
        return ""
    email_address = str(item.get("email_address") or "").strip().casefold()
    if email_address:
        return f"email:{email_address}"
    account_id = str(item.get("id") or "").strip()
    return f"id:{account_id}" if account_id else ""


def _copy_legacy_path_if_missing(source: Path, destination: Path) -> None:
    if destination.exists() or not source.exists():
        return
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def accounts_path() -> Path:
    return data_dir() / "accounts.json"


def settings_path() -> Path:
    settings_app_name = os.environ.get("POWER_ACCESSIBLE_MAIL_SETTINGS_APP_NAME", "").strip()
    if not settings_app_name:
        return data_dir() / "settings.json"
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) / settings_app_name if appdata else Path.home() / ".accessible_mail"
    root.mkdir(parents=True, exist_ok=True)
    return root / "settings.json"


def cache_dir() -> Path:
    root = data_dir() / ".mail_store"
    root.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetFileAttributesW(str(root), 0x02)
        except Exception:
            pass
    return root


def message_cache_path() -> Path:
    return cache_dir() / "messages.sqlite3"


def oauth_clients_paths() -> list[Path]:
    configured_path = os.environ.get("POWER_ACCESSIBLE_MAIL_OAUTH_CLIENTS_FILE", "").strip()
    if configured_path:
        paths = [Path(configured_path).expanduser()]
    else:
        paths = [app_dir() / "oauth_clients.json"]
        if getattr(sys, "frozen", False):
            paths.append(Path(sys.executable).resolve().parent / "oauth_clients.json")
    paths.append(data_dir() / "oauth_clients.json")

    unique_paths: list[Path] = []
    for path in paths:
        resolved = path.resolve(strict=False)
        if resolved not in unique_paths:
            unique_paths.append(resolved)
    return unique_paths


def load_oauth_clients() -> dict[str, dict[str, str]]:
    clients: dict[str, dict[str, str]] = {
        "google_gmail_api": {
            "client_id": os.environ.get("ACCESSIBLE_MAIL_GOOGLE_GMAIL_API_CLIENT_ID", ""),
            "client_secret": os.environ.get("ACCESSIBLE_MAIL_GOOGLE_GMAIL_API_CLIENT_SECRET", ""),
        },
        "microsoft": {
            "client_id": os.environ.get("ACCESSIBLE_MAIL_MICROSOFT_CLIENT_ID", ""),
            "client_secret": os.environ.get("ACCESSIBLE_MAIL_MICROSOFT_CLIENT_SECRET", ""),
        },
    }
    for path in oauth_clients_paths():
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for provider_id, values in payload.items():
            if provider_id not in clients or not isinstance(values, dict):
                continue
            current = clients[provider_id]
            for key in ["client_id", "client_secret"]:
                value = values.get(key)
                if isinstance(value, str) and value.strip():
                    current[key] = value.strip()
    return clients


def load_accounts() -> list[Account]:
    path = accounts_path()
    payload = _read_json_with_backup(path)
    if not isinstance(payload, list):
        return []
    accounts: list[Account] = []
    for item in payload:
        if isinstance(item, dict):
            account = Account.from_dict(item)
            protected_password = item.get("password_protected")
            if isinstance(protected_password, str) and protected_password:
                account.password = unprotect_secret(protected_password)
                account.save_password = bool(account.password)
            for field_name in ("oauth_access_token", "oauth_refresh_token"):
                protected_token = item.get(f"{field_name}_protected")
                if isinstance(protected_token, str) and protected_token:
                    token = unprotect_secret(protected_token)
                    if token:
                        setattr(account, field_name, token)
            if account.oauth_provider == "google":
                account.oauth_provider = "google_gmail_api"
                account.oauth_client_id = ""
                account.oauth_client_secret = ""
                account.oauth_access_token = ""
                account.oauth_refresh_token = ""
                account.oauth_token_expiry = 0.0
            accounts.append(account)
    return accounts


def save_accounts(accounts: list[Account]) -> None:
    payload: list[dict[str, object]] = []
    for account in accounts:
        data = account.to_dict()
        if account.auth_method == "password" and account.save_password and account.password:
            protected_password = protect_secret(account.password)
            if protected_password:
                data["password_protected"] = protected_password
                data["save_password"] = True
        if account.save_oauth_tokens:
            for field_name in ("oauth_access_token", "oauth_refresh_token"):
                token = str(getattr(account, field_name, "") or "")
                data[field_name] = ""
                if not token:
                    continue
                protected_token = protect_secret(token)
                if not protected_token:
                    raise RuntimeError("تعذر تشفير رموز تسجيل الدخول قبل حفظ الحساب.")
                data[f"{field_name}_protected"] = protected_token
        payload.append(data)
    _atomic_write_json(accounts_path(), payload)


def load_settings() -> ProgramSettings:
    path = settings_path()
    payload = _read_json_with_backup(path)
    if not isinstance(payload, dict):
        return ProgramSettings()
    return normalize_settings(
        ProgramSettings(
            language=str(payload.get("language", LANGUAGE_ARABIC)),
            message_viewer=str(payload.get("message_viewer", VIEWER_HTML)),
            theme=str(payload.get("theme", THEME_LIGHT)),
            translation_mode=str(payload.get("translation_mode", TRANSLATION_DIALOG)),
        )
    )


def save_settings(settings: ProgramSettings) -> None:
    settings = normalize_settings(settings)
    _atomic_write_json(settings_path(), asdict(settings))


def _read_json_with_backup(path: Path) -> object | None:
    backup_path = path.with_suffix(path.suffix + ".bak")
    for candidate in (path, backup_path):
        if not candidate.exists():
            continue
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return None


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    backup_path = path.with_suffix(path.suffix + ".bak")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    with _CONFIG_WRITE_LOCK:
        try:
            with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            try:
                shutil.copy2(path, backup_path)
            except OSError:
                pass
        finally:
            temporary_path.unlink(missing_ok=True)


def normalize_settings(settings: ProgramSettings) -> ProgramSettings:
    if settings.language not in {LANGUAGE_ARABIC, LANGUAGE_ENGLISH}:
        settings.language = LANGUAGE_ARABIC
    if settings.message_viewer not in {VIEWER_HTML, VIEWER_SIMPLE}:
        settings.message_viewer = VIEWER_HTML
    if settings.theme not in {THEME_LIGHT, THEME_DARK}:
        settings.theme = THEME_LIGHT
    if settings.translation_mode not in {TRANSLATION_INLINE, TRANSLATION_DIALOG}:
        settings.translation_mode = TRANSLATION_DIALOG
    return settings


def protect_secret(secret: str) -> str:
    if not secret:
        return ""
    try:
        from .secure_store import protect_bytes

        encrypted = protect_bytes(secret.encode("utf-8"))
    except Exception:
        return ""
    return PASSWORD_PREFIX + base64.b64encode(encrypted).decode("ascii")


def unprotect_secret(secret: str) -> str:
    if not secret.startswith(PASSWORD_PREFIX):
        return ""
    try:
        from .secure_store import unprotect_bytes

        encrypted = base64.b64decode(secret[len(PASSWORD_PREFIX) :])
        return unprotect_bytes(encrypted).decode("utf-8")
    except Exception:
        return ""
