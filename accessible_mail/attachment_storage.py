from __future__ import annotations

import os
import secrets
import shutil
import tempfile
import time
import threading
import weakref
from pathlib import Path


STALE_ATTACHMENT_AGE_SECONDS = 7 * 24 * 60 * 60
_SESSION_NAME = f"{os.getpid()}-{secrets.token_hex(8)}"
_COMMIT_GUARD = threading.Lock()
_COMMIT_LOCKS = weakref.WeakValueDictionary()


def opened_attachments_root() -> Path:
    return Path(tempfile.gettempdir()) / "PowerAccessibleMail" / "opened_attachments"


def attachment_temporary_path(destination: Path) -> Path:
    """Reserve an independent same-directory file for each atomic download."""
    descriptor, name = tempfile.mkstemp(prefix=".pam-attachment-", suffix=".part", dir=destination.parent)
    os.close(descriptor)
    return Path(name)


def commit_attachment_download(temporary: Path, destination: Path) -> None:
    """Serialize same-path commits without serializing the downloads themselves."""
    key = os.path.normcase(os.path.abspath(destination))
    with _COMMIT_GUARD:
        lock = _COMMIT_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _COMMIT_LOCKS[key] = lock
    with lock:
        os.replace(temporary, destination)


def opened_attachment_session_dir() -> Path:
    root = opened_attachments_root() / _SESSION_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def cleanup_opened_attachment_session() -> None:
    _remove_path(opened_attachments_root() / _SESSION_NAME)
    _remove_empty_root()


def cleanup_stale_opened_attachments(
    *,
    now: float | None = None,
    max_age_seconds: int = STALE_ATTACHMENT_AGE_SECONDS,
) -> None:
    root = opened_attachments_root()
    if not root.is_dir():
        return
    cutoff = (time.time() if now is None else now) - max(0, max_age_seconds)
    for path in root.iterdir():
        if path.name == _SESSION_NAME:
            continue
        try:
            modified_at = path.stat().st_mtime
        except OSError:
            continue
        if modified_at <= cutoff:
            _remove_path(path)
    _remove_empty_root()


def _remove_path(path: Path) -> None:
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    except OSError:
        pass


def _remove_empty_root() -> None:
    root = opened_attachments_root()
    try:
        root.rmdir()
        root.parent.rmdir()
    except OSError:
        pass
