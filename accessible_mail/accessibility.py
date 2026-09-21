from __future__ import annotations

import wx

from .i18n import tr
from .notification_preferences import (
    EVENT_CONTEXT_MENUS,
    EVENT_DIALOGS,
    event_is_enabled,
    notification_event_for_message,
)
from .screen_reader import interrupt_and_speak


_native_message_box = wx.MessageBox


def set_accessible(control: wx.Window, name: str, description: str = "") -> None:
    control.SetName(tr(name))
    if description:
        control.SetToolTip(tr(description))


def focused_control() -> wx.Window | None:
    try:
        return wx.Window.FindFocus()
    except Exception:
        return None


def restore_control_focus(control: wx.Window | None) -> None:
    if control is None:
        return
    try:
        if control.IsBeingDeleted() or not control.IsEnabled():
            return
        control.SetFocus()
    except Exception:
        return


def announce_to_screen_reader(
    control: wx.Window,
    message: str,
    event_id: str | None = None,
) -> bool:
    resolved_event_id = event_id or notification_event_for_message(message)
    if not event_is_enabled(resolved_event_id):
        return False
    localized = tr(message)
    if interrupt_and_speak(localized):
        return True
    try:
        wx.Accessible.NotifyEvent(
            wx.ACC_EVENT_SYSTEM_ALERT,
            control,
            wx.OBJID_CLIENT,
            0,
        )
        return True
    except Exception:
        return False


def announce_context_menu(control: wx.Window) -> bool:
    return announce_to_screen_reader(
        control,
        "تم فتح قائمة السياق.",
        EVENT_CONTEXT_MENUS,
    )


def should_announce_status(message: str) -> bool:
    return bool(message and event_is_enabled(notification_event_for_message(message)))


def message_box(
    message: str,
    caption: str,
    style: int = wx.OK,
    parent: wx.Window | None = None,
) -> int:
    localized_message = tr(message)
    if event_is_enabled(EVENT_DIALOGS):
        interrupt_and_speak(localized_message)
    return _native_message_box(localized_message, tr(caption), style, parent)


def install_message_box_translation() -> None:
    wx.MessageBox = message_box
