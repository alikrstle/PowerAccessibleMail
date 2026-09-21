from __future__ import annotations

import ctypes
import os
import struct
import sys
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any


_NVDA_CONTROLLER_NAME = "nvdaControllerClient.dll"
_controller_lock = threading.Lock()


def _controller_candidates() -> list[Path]:
    architecture = "x64" if struct.calcsize("P") == 8 else "x86"
    vendor_path = Path(__file__).resolve().parent / "vendor" / "nvda"
    package_path = vendor_path / architecture / _NVDA_CONTROLLER_NAME
    legacy_package_path = vendor_path / _NVDA_CONTROLLER_NAME
    executable_path = Path(sys.executable).resolve().parent / _NVDA_CONTROLLER_NAME
    configured_path = os.environ.get(
        "POWER_ACCESSIBLE_MAIL_NVDA_CONTROLLER",
        "",
    ).strip()
    candidates = [package_path, legacy_package_path, executable_path]
    if configured_path:
        candidates.insert(0, Path(configured_path).expanduser())
    return candidates


@lru_cache(maxsize=1)
def _load_controller() -> Any | None:
    if os.name != "nt":
        return None
    for path in _controller_candidates():
        if not path.is_file():
            continue
        try:
            controller = ctypes.WinDLL(str(path))
            controller.nvdaController_testIfRunning.argtypes = []
            controller.nvdaController_testIfRunning.restype = ctypes.c_ulong
            controller.nvdaController_cancelSpeech.argtypes = []
            controller.nvdaController_cancelSpeech.restype = ctypes.c_ulong
            controller.nvdaController_speakText.argtypes = [ctypes.c_wchar_p]
            controller.nvdaController_speakText.restype = ctypes.c_ulong
            return controller
        except (AttributeError, OSError):
            continue
    return None


def _is_interactive_desktop() -> bool:
    if os.name != "nt":
        return False
    user32 = ctypes.windll.user32
    user32.OpenInputDesktop.argtypes = [
        ctypes.c_ulong,
        ctypes.c_bool,
        ctypes.c_ulong,
    ]
    user32.OpenInputDesktop.restype = ctypes.c_void_p
    user32.SwitchDesktop.argtypes = [ctypes.c_void_p]
    user32.SwitchDesktop.restype = ctypes.c_bool
    user32.CloseDesktop.argtypes = [ctypes.c_void_p]
    user32.CloseDesktop.restype = ctypes.c_bool
    desktop = user32.OpenInputDesktop(0, False, 0x0100)
    if not desktop:
        return False
    try:
        return bool(user32.SwitchDesktop(desktop))
    finally:
        user32.CloseDesktop(desktop)


def interrupt_and_speak(text: str) -> bool:
    message = str(text).strip()
    if not message or not _is_interactive_desktop():
        return False
    controller = _load_controller()
    if controller is None:
        return False
    try:
        with _controller_lock:
            if controller.nvdaController_testIfRunning() != 0:
                return False
            controller.nvdaController_cancelSpeech()
            return controller.nvdaController_speakText(message) == 0
    except (AttributeError, OSError):
        return False
