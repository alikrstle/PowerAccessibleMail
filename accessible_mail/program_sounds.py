from __future__ import annotations

import ctypes
import os
from uuid import uuid4
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import wx
import wx.media

from .config import app_dir, data_dir


SOUND_COMPOSE = "compose"
SOUND_SEND = "send"
SOUND_TRASH = "trash"
SOUND_SETTINGS = "settings"
SOUND_ADDRESS_BOOK = "address_book"
SOUND_ITEM_VIEWER = "item_viewer"
SOUND_LEARNING_OPEN = "learning_open"
SOUND_LEARNING_COMPLETE = "learning_complete"
SOUND_UPDATE_AVAILABLE = "update_available"
SOUND_TASK_COMPLETE = "task_complete"
SOUND_UPDATE_BACKGROUND = "update_background"


@dataclass(frozen=True, slots=True)
class ProgramSound:
    event_id: str
    label: str
    filename: str


PROGRAM_SOUNDS = (
    ProgramSound(SOUND_COMPOSE, "إنشاء رسالة", "أنشاء رسالة .mp3"),
    ProgramSound(SOUND_SEND, "إرسال رسالة", "ارسال رسالة .mp3"),
    ProgramSound(SOUND_TRASH, "الإرسال إلى سلة المحذوفات", "الأرسال الى سلة المحذوفات .mp3"),
    ProgramSound(SOUND_SETTINGS, "فتح الإعدادات", "فتح الأعدادات .mp3"),
    ProgramSound(SOUND_ADDRESS_BOOK, "فتح سجل العناوين", "فتح السجل .mp3"),
    ProgramSound(SOUND_ITEM_VIEWER, "فتح مستعرض العناصر", "فتح مستعرض العناصر .mp3"),
    ProgramSound(SOUND_LEARNING_OPEN, "فتح المرشد التفاعلي", "المرشد التفاعلي .mp3"),
    ProgramSound(SOUND_LEARNING_COMPLETE, "إكمال المرشد التفاعلي", "أكمال المرشد التفاعلي .MP3"),
    ProgramSound(SOUND_UPDATE_AVAILABLE, "وصول تحديث", "وصول تحديث.mp3"),
    ProgramSound(SOUND_TASK_COMPLETE, "إنجاز مهمة في المرشد التفاعلي", "صوت أنجاز المهمة .mp3"),
)
UPDATE_BACKGROUND_SOUND = ProgramSound(
    SOUND_UPDATE_BACKGROUND,
    "موسيقى الخلفية أثناء التحديث",
    "الخلفية الموسيقية .mp3",
)
SOUNDS_BY_ID = {
    sound.event_id: sound
    for sound in (*PROGRAM_SOUNDS, UPDATE_BACKGROUND_SOUND)
}
ALL_SOUND_EVENT_IDS = frozenset(sound.event_id for sound in PROGRAM_SOUNDS)

_MCI_LOCK = threading.RLock()
_MCI_ALIAS = "power_accessible_mail_sound"
_MCI_CLOSE_TIMER: threading.Timer | None = None
_WX_MEDIA_CONTROL: wx.media.MediaCtrl | None = None
_WX_BACKGROUND_CONTROL: wx.media.MediaCtrl | None = None


def sound_directory() -> Path:
    return app_dir() / "sound"


def normalize_sound_event_ids(values: object) -> list[str]:
    if values is None:
        return [sound.event_id for sound in PROGRAM_SOUNDS]
    if not isinstance(values, (list, tuple, set, frozenset)):
        return [sound.event_id for sound in PROGRAM_SOUNDS]
    selected = {value for value in values if isinstance(value, str)}
    return [sound.event_id for sound in PROGRAM_SOUNDS if sound.event_id in selected]


def normalize_custom_sound_files(values: object) -> dict[str, str]:
    if not isinstance(values, dict):
        return {}
    return {
        event_id: path
        for event_id, path in values.items()
        if event_id in ALL_SOUND_EVENT_IDS
        and isinstance(path, str)
        and bool(path.strip())
    }


def sound_path(event_id: str, settings: Any | None = None) -> Path | None:
    sound = SOUNDS_BY_ID.get(event_id)
    if sound is None:
        return None
    custom_files = normalize_custom_sound_files(
        getattr(settings, "program_sound_files", None)
    )
    custom_value = custom_files.get(event_id)
    if custom_value:
        custom_path = Path(custom_value).expanduser().resolve(strict=False)
        if custom_path.suffix.casefold() == ".mp3" and custom_path.is_file():
            return custom_path
    root = sound_directory().resolve(strict=False)
    candidate = (root / sound.filename).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate.suffix.casefold() != ".mp3" or not candidate.is_file():
        return None
    return candidate


def play_program_sound(event_id: str, settings: Any, *, force: bool = False) -> bool:
    if os.name != "nt":
        return False
    if not force:
        if not bool(getattr(settings, "program_sounds_enabled", True)):
            return False
        enabled = normalize_sound_event_ids(
            getattr(settings, "program_sound_events", None)
        )
        if event_id not in enabled:
            return False
    path = sound_path(event_id, settings)
    if path is None:
        return False
    try:
        if _play_mp3_with_mci(path):
            return True
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    try:
        return _play_mp3_with_wx(path)
    except (AttributeError, OSError, RuntimeError):
        return False


def replace_program_sound(event_id: str, source: Path) -> Path:
    if event_id not in ALL_SOUND_EVENT_IDS:
        raise ValueError("Unknown program sound event")
    source = source.expanduser().resolve(strict=True)
    if source.suffix.casefold() != ".mp3" or not source.is_file():
        raise ValueError("The replacement sound must be an MP3 file")
    destination_dir = data_dir() / "custom-sounds"
    destination_dir.mkdir(parents=True, exist_ok=True)
    # Immutable versions: cancelling either dialog must not overwrite the
    # sound referenced by the last saved settings.
    destination = destination_dir / f"{event_id}-{uuid4().hex}.mp3"
    if source != destination.resolve(strict=False):
        temporary = destination.with_suffix(".tmp")
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return destination


def stop_program_sound() -> None:
    global _MCI_CLOSE_TIMER, _WX_MEDIA_CONTROL
    stop_update_background_music()
    if os.name != "nt":
        return
    if _WX_MEDIA_CONTROL is not None:
        try:
            _WX_MEDIA_CONTROL.Stop()
        except RuntimeError:
            pass
        _WX_MEDIA_CONTROL = None
    with _MCI_LOCK:
        if _MCI_CLOSE_TIMER is not None:
            _MCI_CLOSE_TIMER.cancel()
            _MCI_CLOSE_TIMER = None
        _mci_send(f"stop {_MCI_ALIAS}")
        _mci_send(f"close {_MCI_ALIAS}")


def start_update_background_music(settings: Any) -> bool:
    global _WX_BACKGROUND_CONTROL
    if os.name != "nt":
        return False
    if not bool(getattr(settings, "program_sounds_enabled", True)):
        return False
    path = sound_path(SOUND_UPDATE_BACKGROUND, settings)
    app = wx.GetApp()
    parent = app.GetTopWindow() if app else None
    if path is None or parent is None:
        return False
    try:
        if _WX_BACKGROUND_CONTROL is None or _WX_BACKGROUND_CONTROL.IsBeingDeleted():
            _WX_BACKGROUND_CONTROL = wx.media.MediaCtrl(parent)
            _WX_BACKGROUND_CONTROL.Hide()
            _WX_BACKGROUND_CONTROL.Bind(
                wx.media.EVT_MEDIA_FINISHED,
                _restart_update_background_music,
            )
        else:
            _WX_BACKGROUND_CONTROL.Stop()
        _WX_BACKGROUND_CONTROL.SetVolume(0.35)
        if not _WX_BACKGROUND_CONTROL.Load(str(path)):
            return False
        return bool(_WX_BACKGROUND_CONTROL.Play())
    except (AttributeError, OSError, RuntimeError):
        return False


def _restart_update_background_music(event: wx.media.MediaEvent) -> None:
    if _WX_BACKGROUND_CONTROL is not None:
        try:
            _WX_BACKGROUND_CONTROL.Seek(0)
            _WX_BACKGROUND_CONTROL.Play()
        except RuntimeError:
            pass
    event.Skip()


def stop_update_background_music() -> None:
    global _WX_BACKGROUND_CONTROL
    if _WX_BACKGROUND_CONTROL is None:
        return
    try:
        _WX_BACKGROUND_CONTROL.Stop()
    except RuntimeError:
        pass
    _WX_BACKGROUND_CONTROL = None


def _play_mp3_with_wx(path: Path) -> bool:
    global _WX_MEDIA_CONTROL
    app = wx.GetApp()
    parent = app.GetTopWindow() if app else None
    if parent is None:
        return False
    if _WX_MEDIA_CONTROL is None or _WX_MEDIA_CONTROL.IsBeingDeleted():
        _WX_MEDIA_CONTROL = wx.media.MediaCtrl(parent)
        _WX_MEDIA_CONTROL.Hide()
    else:
        _WX_MEDIA_CONTROL.Stop()
    if not _WX_MEDIA_CONTROL.Load(str(path)):
        return False
    return bool(_WX_MEDIA_CONTROL.Play())


def _play_mp3_with_mci(path: Path) -> bool:
    global _MCI_CLOSE_TIMER
    quoted_path = str(path).replace('"', '""')
    with _MCI_LOCK:
        if _MCI_CLOSE_TIMER is not None:
            _MCI_CLOSE_TIMER.cancel()
            _MCI_CLOSE_TIMER = None
        _mci_send(f"close {_MCI_ALIAS}")
        if _mci_send(
            f'open "{quoted_path}" type mpegvideo alias {_MCI_ALIAS}'
        ) != 0:
            return False
        if _mci_send(f"play {_MCI_ALIAS} from 0") != 0:
            _mci_send(f"close {_MCI_ALIAS}")
            return False
        duration_text = _mci_query(f"status {_MCI_ALIAS} length")
        try:
            duration_seconds = max(0.25, min(30.0, int(duration_text) / 1000))
        except (TypeError, ValueError):
            duration_seconds = 8.0
        _MCI_CLOSE_TIMER = threading.Timer(
            duration_seconds + 0.5,
            _close_finished_sound,
        )
        _MCI_CLOSE_TIMER.daemon = True
        _MCI_CLOSE_TIMER.start()
        return True


def _close_finished_sound() -> None:
    global _MCI_CLOSE_TIMER
    with _MCI_LOCK:
        _mci_send(f"close {_MCI_ALIAS}")
        _MCI_CLOSE_TIMER = None


def _mci_send(command: str) -> int:
    return int(ctypes.windll.winmm.mciSendStringW(command, None, 0, None))


def _mci_query(command: str) -> str:
    buffer = ctypes.create_unicode_buffer(64)
    result = int(
        ctypes.windll.winmm.mciSendStringW(
            command,
            buffer,
            len(buffer),
            None,
        )
    )
    return buffer.value.strip() if result == 0 else ""
