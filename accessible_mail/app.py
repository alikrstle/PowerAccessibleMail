from __future__ import annotations

import wx

from .accessibility import (
    announce_to_screen_reader,
    focused_control,
    install_message_box_translation,
    restore_control_focus,
    set_accessible,
)
from .account_dialog import AccountDialog
from .bulk_operations import run_bulk_operations
from .dialogs import (
    BulkDeleteDialog,
    ComposeDialog,
    SettingsDialog,
    UpdateAvailableDialog,
    UpdateDownloadDialog,
)
from .mail_page import MailPage
from .main_frame import MainFrame
from .ui_constants import (
    BULK_ACTION_DELETE,
    BULK_ACTION_MARK_READ,
    BULK_ACTION_MARK_UNREAD,
    BULK_ACTION_PIN,
    BULK_ACTION_STAR,
    BULK_ACTION_UNPIN,
    BULK_ACTION_UNSTAR,
    FILTER_ALL,
    FILTER_CHOICES,
    FILTER_READ,
    FILTER_STARRED,
    FILTER_TRASH,
    FILTER_UNREAD,
    INITIAL_MESSAGE_LIMIT,
    INLINE_GENERIC_LINK_TEXTS,
    LANGUAGE_CHOICES,
    MANUAL_PROVIDER_GOOGLE,
    MANUAL_PROVIDER_MICROSOFT,
    MAX_MEMORY_MESSAGE_CONTENTS,
    MESSAGE_SELECTION_DELAY_MS,
    MULTI_SELECTION_ANNOUNCEMENT_DELAY_MS,
    THEME_CHOICES,
    TRANSLATION_MODE_CHOICES,
    VIEWER_CHOICES,
)


__all__ = (
    "AccountDialog",
    "BULK_ACTION_DELETE",
    "BULK_ACTION_MARK_READ",
    "BULK_ACTION_MARK_UNREAD",
    "BULK_ACTION_PIN",
    "BULK_ACTION_STAR",
    "BULK_ACTION_UNPIN",
    "BULK_ACTION_UNSTAR",
    "BulkDeleteDialog",
    "ComposeDialog",
    "FILTER_ALL",
    "FILTER_CHOICES",
    "FILTER_READ",
    "FILTER_STARRED",
    "FILTER_TRASH",
    "FILTER_UNREAD",
    "INITIAL_MESSAGE_LIMIT",
    "INLINE_GENERIC_LINK_TEXTS",
    "LANGUAGE_CHOICES",
    "MANUAL_PROVIDER_GOOGLE",
    "MANUAL_PROVIDER_MICROSOFT",
    "MAX_MEMORY_MESSAGE_CONTENTS",
    "MESSAGE_SELECTION_DELAY_MS",
    "MULTI_SELECTION_ANNOUNCEMENT_DELAY_MS",
    "MailPage",
    "MainFrame",
    "SettingsDialog",
    "THEME_CHOICES",
    "TRANSLATION_MODE_CHOICES",
    "UpdateAvailableDialog",
    "UpdateDownloadDialog",
    "VIEWER_CHOICES",
    "announce_to_screen_reader",
    "focused_control",
    "restore_control_focus",
    "run",
    "run_bulk_operations",
    "set_accessible",
)


install_message_box_translation()


def run() -> None:
    app = wx.App(False)
    frame = MainFrame()
    frame.Show()
    app.MainLoop()
