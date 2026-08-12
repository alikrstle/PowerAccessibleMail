from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import sys
import threading
import traceback
from pathlib import Path
from types import TracebackType

from .config import data_dir


LOGGER_NAME = "power_accessible_mail"
LOG_DIRECTORY_NAME = "logs"
LOG_FILE_NAME = "power-accessible-mail.log"
MAX_LOG_BYTES = 512 * 1024
LOG_BACKUP_COUNT = 3
_configured = False


def log_path() -> Path:
    return data_dir() / LOG_DIRECTORY_NAME / LOG_FILE_NAME


def configure_crash_logging() -> Path:
    """Install privacy-preserving handlers for otherwise unhandled exceptions."""
    global _configured
    path = log_path()
    if _configured:
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.info("Application logging started (Python %s).", sys.version.split()[0])

    sys.excepthook = _sys_exception_hook
    if hasattr(threading, "excepthook"):
        threading.excepthook = _thread_exception_hook
    _configured = True
    return path


def record_unhandled_exception(
    exc_type: type[BaseException],
    _exc_value: BaseException,
    exc_traceback: TracebackType | None,
    *,
    origin: str,
) -> None:
    """Record exception type and code locations, deliberately excluding its value."""
    frames = traceback.extract_tb(exc_traceback) if exc_traceback else []
    locations = " > ".join(
        f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
        for frame in frames
    )
    logging.getLogger(LOGGER_NAME).error(
        "Unhandled %s in %s%s",
        exc_type.__name__,
        origin,
        f" at {locations}" if locations else "",
    )


def _sys_exception_hook(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
) -> None:
    record_unhandled_exception(
        exc_type,
        exc_value,
        exc_traceback,
        origin="main thread",
    )


def _thread_exception_hook(args: threading.ExceptHookArgs) -> None:
    thread_name = args.thread.name if args.thread is not None else "unknown thread"
    record_unhandled_exception(
        args.exc_type,
        args.exc_value,
        args.exc_traceback,
        origin=f"worker thread {thread_name}",
    )
