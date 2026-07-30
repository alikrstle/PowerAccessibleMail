from __future__ import annotations

import html
import os
import time
import urllib.parse
import webbrowser
from collections.abc import Callable
from pathlib import Path

import wx
import wx.html2

from .attachment_storage import opened_attachment_session_dir
from .accessibility import (
    announce_to_screen_reader,
    focused_control,
    restore_control_focus,
    set_accessible,
)
from .config import (
    LANGUAGE_ARABIC,
    LANGUAGE_ENGLISH,
    THEME_DARK,
    THEME_LIGHT,
    VIEWER_HTML,
    VIEWER_SIMPLE,
)
from .email_utils import normalize_message_text, safe_external_url
from .i18n import is_rtl, tr
from .models import LinkItem, MessageContent, MessageSummary
from .ui_constants import (
    BULK_ACTION_DELETE,
    BULK_ACTION_MARK_READ,
    BULK_ACTION_MARK_UNREAD,
    BULK_ACTION_PIN,
    BULK_ACTION_STAR,
    BULK_ACTION_UNPIN,
    BULK_ACTION_UNSTAR,
    FILTER_CHOICES,
    INLINE_GENERIC_LINK_TEXTS,
    MULTI_SELECTION_ANNOUNCEMENT_DELAY_MS,
)
from .ui_helpers import localize_window, set_localized_items


DANGEROUS_ATTACHMENT_EXTENSIONS = frozenset(
    {
        ".bat",
        ".chm",
        ".cmd",
        ".com",
        ".cpl",
        ".docm",
        ".exe",
        ".hta",
        ".img",
        ".iso",
        ".jar",
        ".js",
        ".jse",
        ".lnk",
        ".msi",
        ".msp",
        ".pif",
        ".pptm",
        ".ps1",
        ".reg",
        ".scr",
        ".url",
        ".vbe",
        ".vbs",
        ".wsf",
        ".xlam",
        ".xlsm",
    }
)
WINDOWS_RESERVED_FILENAMES = frozenset(
    {
        "AUX",
        "CON",
        "NUL",
        "PRN",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)


class MailPage(wx.Panel):
    def __init__(
        self,
        parent: wx.Window,
        title: str,
        on_selected: Callable[["MailPage", MessageSummary], None],
        on_toggle_read: Callable[["MailPage", MessageSummary], None],
        on_translate: Callable[["MailPage"], None],
        on_reply: Callable[[], None],
        on_toggle_star: Callable[["MailPage"], None],
        on_toggle_pin: Callable[["MailPage"], None],
        on_delete: Callable[["MailPage"], None],
        on_bulk_action: Callable[["MailPage", str, list[MessageSummary]], None],
        on_filter_changed: Callable[["MailPage"], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title = title
        self.messages: list[MessageSummary] = []
        self.trash_messages: list[MessageSummary] = []
        self.trash_mailbox = ""
        self.visible_messages: list[MessageSummary] = []
        self.links: list[LinkItem] = []
        self.viewer_text = ""
        self.viewer_mode = VIEWER_HTML
        self.theme = THEME_LIGHT
        self.link_panel_visible_in_html = False
        self.viewer_action_ranges: list[tuple[int, int, LinkItem]] = []
        self.current_viewer_action_range: tuple[int, int, LinkItem] | None = None
        self.current_content_key: tuple[str, str] | None = None
        self._translation_return_control: wx.Window | None = None
        self._last_items_toggle_at = 0.0
        self._last_context_menu_request_at = 0.0
        self._html_focus_call: wx.CallLater | None = None
        self._html_viewer_active = False
        self._html_refresh_pending = True
        self._html_focus_after_load = False
        self._suppress_selection_event = False
        self.multi_select_mode = False
        self._multi_selected_keys: set[tuple[str, str]] = set()
        self._control_pressed_alone = False
        self._selection_count_announce_call: wx.CallLater | None = None
        self._multi_mode_notification_call: wx.CallLater | None = None
        self.on_selected = on_selected
        self.on_toggle_read = on_toggle_read
        self.on_translate = on_translate
        self.on_reply = on_reply
        self.on_toggle_star = on_toggle_star
        self.on_toggle_pin = on_toggle_pin
        self.on_delete = on_delete
        self.on_bulk_action = on_bulk_action
        self.on_filter_changed = on_filter_changed
        self._build()

    def _build(self) -> None:
        root = wx.BoxSizer(wx.VERTICAL)
        filter_row = wx.BoxSizer(wx.HORIZONTAL)
        filter_row.Add(wx.StaticText(self, label="التصنيف:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        self.filter_choice = wx.Choice(self, choices=[tr(label) for label in FILTER_CHOICES])
        self.filter_choice.SetSelection(0)
        set_accessible(self.filter_choice, f"تصنيف {self.title}")
        self.filter_choice.Bind(wx.EVT_CHOICE, self.on_filter)
        filter_row.Add(self.filter_choice, 1, wx.EXPAND | wx.ALL, 6)
        root.Add(filter_row, 0, wx.EXPAND)

        self.list = wx.ListCtrl(self, style=wx.LC_REPORT)
        self.list.EnableCheckBoxes(False)
        self.list.InsertColumn(0, tr("الحالة"), width=120)
        self.list.InsertColumn(1, tr("المرسل"), width=220)
        self.list.InsertColumn(2, tr("الموضوع"), width=300)
        self.list.InsertColumn(3, tr("التاريخ"), width=220)
        set_accessible(
            self.list,
            f"قائمة {self.title}",
            "استخدم الأسهم لاختيار رسالة. اضغط Control وShift وSpace لإظهار مربعات الاختيار وتفعيل التحديد المتعدد.",
        )
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_item_selected)
        self.list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_item_deselected)
        self.list.Bind(wx.EVT_LIST_ITEM_CHECKED, self.on_item_checked)
        self.list.Bind(wx.EVT_LIST_ITEM_UNCHECKED, self.on_item_unchecked)
        self.list.Bind(wx.EVT_CHAR_HOOK, self.on_list_key)
        self.list.Bind(wx.EVT_KEY_DOWN, self.on_list_key_down)
        self.list.Bind(wx.EVT_KEY_UP, self.on_list_key_up)
        self.list.Bind(wx.EVT_SET_FOCUS, self.on_message_list_focus)
        root.Add(self.list, 2, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.selection_status = wx.StaticText(self, label="")
        set_accessible(self.selection_status, "حالة التحديد المتعدد")
        self.selection_status.Hide()
        root.Add(self.selection_status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        root.Add(wx.StaticText(self, label="نص الرسالة:"), 0, wx.LEFT | wx.RIGHT, 8)
        self.viewer = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
        )
        self.viewer.Hide()
        self.html_viewer = wx.html2.WebView.New(self)
        self._html_message_bridge = False
        try:
            self.html_viewer.EnableContextMenu(False)
        except (AttributeError, NotImplementedError):
            pass
        try:
            self._html_message_bridge = bool(
                self.html_viewer.AddScriptMessageHandler("pamBridge")
            )
        except (AttributeError, NotImplementedError):
            pass
        set_accessible(
            self.html_viewer,
            f"مستعرض نص {self.title}",
            "مستعرض HTML للرسالة. استخدم أوامر قارئ الشاشة أو Tab للتنقل بين الروابط والأزرار، وEnter أو Space لفتح العنصر.",
        )
        self.viewer.Bind(wx.EVT_CHAR_HOOK, self.on_viewer_key)
        self.viewer.Bind(wx.EVT_KEY_DOWN, self.on_viewer_key)
        self.viewer.Bind(wx.EVT_CHAR, self.on_viewer_key)
        self.html_viewer.Bind(wx.html2.EVT_WEBVIEW_NAVIGATING, self.on_html_viewer_navigating)
        self.html_viewer.Bind(wx.html2.EVT_WEBVIEW_LOADED, self.on_html_viewer_loaded)
        self.html_viewer.Bind(wx.EVT_LEFT_DOWN, self.on_html_viewer_pointer_focus)
        self.html_viewer.Bind(wx.EVT_CONTEXT_MENU, self.on_html_context_menu)
        if self._html_message_bridge:
            self.html_viewer.Bind(
                wx.html2.EVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED,
                self.on_html_script_message,
            )
        self.viewer.Bind(wx.EVT_CONTEXT_MENU, self.on_message_context_menu)
        self.list.Bind(wx.EVT_CONTEXT_MENU, self.on_message_context_menu)
        self.viewer_sizer_item = root.Add(self.viewer, 3, wx.EXPAND | wx.ALL, 8)
        self.html_viewer_sizer_item = root.Add(self.html_viewer, 3, wx.EXPAND | wx.ALL, 8)

        self.link_panel = wx.Panel(self)
        link_row = wx.BoxSizer(wx.HORIZONTAL)
        link_row.Add(
            wx.StaticText(self.link_panel, label="مستعرض العناصر:"),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.ALL,
            6,
        )
        self.link_list = wx.ListBox(self.link_panel)
        set_accessible(
            self.link_list,
            f"مستعرض العناصر {self.title}",
            "اضغط Enter أو Space لفتح الرابط أو الزر أو فتح المرفق المحدد محليا",
        )
        self.link_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_open_link)
        self.link_list.Bind(wx.EVT_CHAR_HOOK, self.on_link_key)
        self.link_list.Bind(wx.EVT_CONTEXT_MENU, self.on_message_context_menu)
        link_row.Add(self.link_list, 1, wx.EXPAND | wx.ALL, 6)
        self.actions_button = wx.Button(self.link_panel, label="إجراءات الرسالة")
        set_accessible(self.actions_button, f"قائمة إجراءات رسالة {self.title}")
        self.actions_button.Bind(wx.EVT_BUTTON, self.on_actions_button)
        link_row.Add(self.actions_button, 0, wx.ALL, 6)
        self.link_panel.SetSizer(link_row)
        root.Add(self.link_panel, 1, wx.EXPAND)

        self.SetSizer(root)
        self.localize_ui()

    def localize_ui(self) -> None:
        self.title = tr(self.title)
        localize_window(self)
        set_localized_items(self.filter_choice, FILTER_CHOICES)
        for index, label in enumerate(("الحالة", "المرسل", "الموضوع", "التاريخ")):
            column = self.list.GetColumn(index)
            column.SetText(tr(label))
            self.list.SetColumn(index, column)
        self.apply_filter()

    def selected_filter_key(self) -> str:
        keys = ("all", "starred", "unread", "read", "trash")
        selection = self.filter_choice.GetSelection()
        return keys[selection] if 0 <= selection < len(keys) else "all"

    def set_messages(self, messages: list[MessageSummary]) -> None:
        self.messages = self.sort_newest_first(messages)
        self.apply_filter()
        self.set_viewer_text("")
        self.set_links([])
        self.current_content_key = None

    def set_trash_messages(self, messages: list[MessageSummary], mailbox: str = "") -> None:
        self.trash_messages = self.sort_newest_first(messages)
        self.trash_mailbox = mailbox
        self.apply_filter()
        if self.current_content_key and self.current_content_key not in self.all_message_keys():
            self.set_viewer_text("")
            self.set_links([])
            self.current_content_key = None

    def merge_messages(self, messages: list[MessageSummary]) -> bool:
        if not messages and self.messages:
            return False

        selected_key = self.selected_message_key()
        existing_by_key = {self.message_key(message): message for message in self.messages}
        merged: list[MessageSummary] = []
        seen: set[tuple[str, str]] = set()

        for message in messages:
            key = self.message_key(message)
            old = existing_by_key.get(key)
            if old and old.is_pinned:
                message.is_pinned = True
            merged.append(message)
            seen.add(key)

        for message in self.messages:
            key = self.message_key(message)
            if key not in seen:
                merged.append(message)

        self.messages = self.sort_newest_first(merged)
        self.apply_filter(preserve_key=selected_key)
        if self.current_content_key and self.current_content_key not in self.all_message_keys():
            self.set_viewer_text("")
            self.set_links([])
            self.current_content_key = None
        return True

    def reconcile_recent_messages(self, recent_messages: list[MessageSummary]) -> None:
        selected_key = self.selected_message_key()
        incoming_keys = {self.message_key(message) for message in recent_messages}
        if recent_messages:
            oldest_recent = min(message.sort_timestamp for message in recent_messages)
            older_messages = [
                message
                for message in self.messages
                if self.message_key(message) not in incoming_keys
                and message.sort_timestamp < oldest_recent
            ]
        else:
            older_messages = []
        self.messages = self.sort_newest_first([*recent_messages, *older_messages])
        self.apply_filter(preserve_key=selected_key)
        if self.current_content_key and self.current_content_key not in self.all_message_keys():
            self.set_viewer_text("")
            self.set_links([])
            self.current_content_key = None

    def apply_filter(self, preserve_key: tuple[str, str] | None = None) -> None:
        focus_owner = focused_control()
        if preserve_key is None:
            preserve_key = self.focused_message_key() or self.selected_message_key()
        selected_keys = (
            set(self._multi_selected_keys) | self.selected_message_keys()
            if self.multi_select_mode
            else set()
        )
        selected = self.selected_filter_key()
        if selected == "trash":
            self.visible_messages = list(self.trash_messages)
        elif selected == "starred":
            self.visible_messages = [message for message in self.messages if message.is_starred]
        elif selected == "unread":
            self.visible_messages = [message for message in self.messages if not message.is_read]
        elif selected == "read":
            self.visible_messages = [message for message in self.messages if message.is_read]
        else:
            self.visible_messages = list(self.messages)
        self.visible_messages = self.sort_newest_first(self.visible_messages)
        visible_keys = {self.message_key(message) for message in self.visible_messages}
        self._multi_selected_keys = selected_keys & visible_keys

        self._suppress_selection_event = True
        self.list.Freeze()
        try:
            self.list.DeleteAllItems()
            restore_index = -1
            for index, message in enumerate(self.visible_messages):
                row = self.list.InsertItem(index, message.status_label)
                self.list.SetItem(row, 1, message.sender)
                self.list.SetItem(row, 2, message.display_subject)
                self.list.SetItem(row, 3, message.date)
                key = self.message_key(message)
                if self.multi_select_mode and key in self._multi_selected_keys:
                    self.list.CheckItem(row, True)
                if preserve_key == key:
                    restore_index = index
            if restore_index >= 0:
                state = wx.LIST_STATE_FOCUSED | wx.LIST_STATE_SELECTED
                self.list.SetItemState(
                    restore_index,
                    state,
                    wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                )
                self.list.EnsureVisible(restore_index)
            elif self.multi_select_mode and self.visible_messages:
                self.list.SetItemState(
                    0,
                    wx.LIST_STATE_FOCUSED | wx.LIST_STATE_SELECTED,
                    wx.LIST_STATE_FOCUSED | wx.LIST_STATE_SELECTED,
                )
        finally:
            self.list.Thaw()
            self._suppress_selection_event = False
        if getattr(self, "multi_select_mode", False):
            self.update_multi_selection_status()
        restore_control_focus(focus_owner)

    def on_filter(self, _event: wx.CommandEvent) -> None:
        if self.on_filter_changed and self.selected_filter_key() == "trash":
            self.on_filter_changed(self)
            return
        self.apply_filter()

    def on_list_key(self, event: wx.KeyEvent) -> None:
        key_code = event.GetKeyCode()
        if key_code == wx.WXK_CONTROL:
            self._control_pressed_alone = getattr(self, "multi_select_mode", False)
            event.Skip()
            return
        if event.ControlDown():
            self._control_pressed_alone = False

        if (
            key_code == wx.WXK_SPACE
            and event.ControlDown()
            and event.ShiftDown()
        ):
            self.toggle_multi_selection_mode()
            return

        if getattr(self, "multi_select_mode", False):
            if key_code == wx.WXK_ESCAPE:
                self.exit_multi_selection_mode()
                return
            if key_code in {
                wx.WXK_UP,
                wx.WXK_DOWN,
                wx.WXK_HOME,
                wx.WXK_END,
                wx.WXK_PAGEUP,
                wx.WXK_PAGEDOWN,
            }:
                self.move_multi_selection_focus(key_code)
                return
            if (
                key_code == wx.WXK_SPACE
                and not event.ControlDown()
                and not event.AltDown()
            ):
                self.toggle_focused_message_selection()
                return
            if key_code == wx.WXK_DELETE:
                summaries = self.selected_summaries()
                if summaries:
                    self.on_bulk_action(self, BULK_ACTION_DELETE, summaries)
                else:
                    self.announce_selection_count()
                return

        if key_code == wx.WXK_DELETE:
            if self.selected_summary():
                self.on_delete(self)
                return
        if key_code == wx.WXK_TAB:
            if self.viewer_mode == VIEWER_HTML and not event.ShiftDown():
                self.focus_message_viewer()
                return
            event.Skip()
            return
        if (
            key_code == wx.WXK_SPACE
            and not event.ControlDown()
            and not event.ShiftDown()
            and not event.AltDown()
        ):
            summary = self.selected_summary()
            if summary:
                self.on_toggle_read(self, summary)
                return
        event.Skip()

    def on_list_key_down(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_CONTROL:
            self._control_pressed_alone = getattr(self, "multi_select_mode", False)
        else:
            self._control_pressed_alone = False
        event.Skip()

    def on_list_key_up(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_CONTROL:
            should_announce = self._control_pressed_alone and self.multi_select_mode
            self._control_pressed_alone = False
            if should_announce:
                self.schedule_selection_count_announcement()
                return
        event.Skip()

    def on_message_list_focus(self, event: wx.FocusEvent) -> None:
        self.deactivate_html_viewer()
        event.Skip()

    def on_item_selected(self, event: wx.ListEvent) -> None:
        if self._suppress_selection_event:
            return
        index = event.GetIndex()
        if 0 <= index < len(self.visible_messages):
            row_indices = (
                self.row_selected_indices()
                if hasattr(self, "row_selected_indices")
                else [index]
            )
            selected_count = len(row_indices)
            multi_select_mode = getattr(self, "multi_select_mode", False)
            if selected_count > 1 and not multi_select_mode:
                self.multi_select_mode = True
                self.set_multi_selection_checkboxes(True)
                self._suppress_selection_event = True
                try:
                    for row_index in row_indices:
                        self.list.CheckItem(row_index, True)
                finally:
                    self._suppress_selection_event = False
                self._multi_selected_keys = {
                    self.message_key(self.visible_messages[row_index])
                    for row_index in row_indices
                    if 0 <= row_index < len(self.visible_messages)
                }
                self.update_multi_selection_status()
                self.schedule_multi_selection_mode_notification(
                    f"تم تفعيل وضع التحديد المتعدد. عدد الرسائل المحددة: {selected_count}."
                )
            if (
                not getattr(self, "multi_select_mode", False)
                or not hasattr(self, "focused_index")
                or index == self.focused_index()
            ):
                self.on_selected(self, self.visible_messages[index])

    def on_item_deselected(self, event: wx.ListEvent) -> None:
        if not self._suppress_selection_event:
            event.Skip()

    def on_item_checked(self, event: wx.ListEvent) -> None:
        self.on_item_check_changed(event.GetIndex(), True)

    def on_item_unchecked(self, event: wx.ListEvent) -> None:
        self.on_item_check_changed(event.GetIndex(), False)

    def on_item_check_changed(self, index: int, checked: bool) -> None:
        if self._suppress_selection_event:
            return
        if not 0 <= index < len(self.visible_messages):
            return
        if not self.multi_select_mode:
            self.multi_select_mode = True
            self._multi_selected_keys.clear()
            self.set_multi_selection_checkboxes(True)
        key = self.message_key(self.visible_messages[index])
        if checked:
            self._multi_selected_keys.add(key)
            action = "تم تحديد الرسالة."
        else:
            self._multi_selected_keys.discard(key)
            action = "تم إلغاء تحديد الرسالة."
        self.update_multi_selection_status()
        self.announce_accessible(
            f"{action} عدد الرسائل المحددة: {len(self._multi_selected_keys)}."
        )

    def row_selected_indices(self) -> list[int]:
        indices: list[int] = []
        index = self.list.GetFirstSelected()
        while index >= 0:
            indices.append(index)
            index = self.list.GetNextSelected(index)
        return indices

    def checked_indices(self) -> list[int]:
        return [
            index
            for index in range(len(self.visible_messages))
            if self.list.IsItemChecked(index)
        ]

    def selected_indices(self) -> list[int]:
        if self.multi_select_mode:
            return self.checked_indices()
        return self.row_selected_indices()

    def selected_summaries(self) -> list[MessageSummary]:
        return [
            self.visible_messages[index]
            for index in self.selected_indices()
            if 0 <= index < len(self.visible_messages)
        ]

    def selected_count(self) -> int:
        return len(self.selected_indices())

    def selected_message_keys(self) -> set[tuple[str, str]]:
        return {self.message_key(summary) for summary in self.selected_summaries()}

    def focused_index(self) -> int:
        index = self.list.GetFocusedItem()
        return index if 0 <= index < len(self.visible_messages) else -1

    def focused_summary(self) -> MessageSummary | None:
        index = self.focused_index()
        return self.visible_messages[index] if index >= 0 else None

    def focused_message_key(self) -> tuple[str, str] | None:
        summary = self.focused_summary()
        return self.message_key(summary) if summary else None

    def selected_summary(self) -> MessageSummary | None:
        focused_index = self.focused_index()
        if self.multi_select_mode and focused_index >= 0:
            return self.visible_messages[focused_index]
        if focused_index >= 0 and self.list.GetItemState(
            focused_index,
            wx.LIST_STATE_SELECTED,
        ):
            return self.visible_messages[focused_index]
        index = self.list.GetFirstSelected()
        if 0 <= index < len(self.visible_messages):
            return self.visible_messages[index]
        return None

    def toggle_multi_selection_mode(self) -> None:
        if self.multi_select_mode:
            self.exit_multi_selection_mode()
        else:
            self.enter_multi_selection_mode()

    def set_multi_selection_checkboxes(self, enabled: bool) -> None:
        self.list.EnableCheckBoxes(enabled)
        if enabled:
            description = (
                "وضع التحديد المتعدد. تنقل بالأسهم واضغط Space لتحديد مربع "
                "الرسالة أو إلغاء تحديده. اضغط Control وحده لسماع العدد."
            )
        else:
            description = (
                "قائمة الرسائل. استخدم الأسهم لاختيار رسالة. اضغط Control "
                "وShift وSpace لإظهار مربعات الاختيار وتفعيل التحديد المتعدد."
            )
        self.list.SetToolTip(tr(description))

    def enter_multi_selection_mode(self) -> None:
        focused_index = self.focused_index()
        if focused_index < 0:
            focused_index = self.list.GetFirstSelected()
        if focused_index < 0 and self.visible_messages:
            focused_index = 0
        self.multi_select_mode = True
        self._multi_selected_keys.clear()
        self.set_multi_selection_checkboxes(True)
        self._suppress_selection_event = True
        try:
            for index in range(len(self.visible_messages)):
                if self.list.IsItemChecked(index):
                    self.list.CheckItem(index, False)
            self.list.SetItemState(
                -1,
                0,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
            )
            if focused_index >= 0:
                state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
                self.list.SetItemState(
                    focused_index,
                    state,
                    state,
                )
                self.list.EnsureVisible(focused_index)
        finally:
            self._suppress_selection_event = False
        self.update_multi_selection_status()
        self.schedule_multi_selection_mode_notification(
            "تم تفعيل وضع التحديد المتعدد. لا توجد رسائل محددة."
        )

    def exit_multi_selection_mode(self, restore_single_selection: bool = True) -> None:
        focused_index = self.focused_index()
        self.multi_select_mode = False
        self._multi_selected_keys.clear()
        self._control_pressed_alone = False
        if self._selection_count_announce_call is not None:
            self._selection_count_announce_call.Stop()
            self._selection_count_announce_call = None
        self._suppress_selection_event = True
        try:
            for index in range(len(self.visible_messages)):
                if self.list.IsItemChecked(index):
                    self.list.CheckItem(index, False)
            self.set_multi_selection_checkboxes(False)
            self.list.SetItemState(
                -1,
                0,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
            )
            if (
                restore_single_selection
                and 0 <= focused_index < len(self.visible_messages)
            ):
                state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
                self.list.SetItemState(focused_index, state, state)
                self.list.EnsureVisible(focused_index)
        finally:
            self._suppress_selection_event = False
        self.schedule_multi_selection_mode_notification(
            "تم إنهاء وضع التحديد المتعدد."
        )
        if (
            restore_single_selection
            and 0 <= focused_index < len(self.visible_messages)
        ):
            self.on_selected(self, self.visible_messages[focused_index])

    def move_multi_selection_focus(self, key_code: int) -> None:
        item_count = len(self.visible_messages)
        if item_count <= 0:
            return
        current = self.focused_index()
        if current < 0:
            current = 0
        page_size = max(1, self.list.GetCountPerPage())
        if key_code == wx.WXK_UP:
            target = current - 1
        elif key_code == wx.WXK_DOWN:
            target = current + 1
        elif key_code == wx.WXK_HOME:
            target = 0
        elif key_code == wx.WXK_END:
            target = item_count - 1
        elif key_code == wx.WXK_PAGEUP:
            target = current - page_size
        else:
            target = current + page_size
        target = max(0, min(target, item_count - 1))
        if target == current:
            if key_code in {wx.WXK_UP, wx.WXK_HOME, wx.WXK_PAGEUP}:
                self.announce_accessible("بداية قائمة الرسائل.")
            else:
                self.announce_accessible("نهاية قائمة الرسائل.")
            return
        self._suppress_selection_event = True
        try:
            self.list.SetItemState(
                -1,
                0,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
            )
            state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
            self.list.SetItemState(target, state, state)
        finally:
            self._suppress_selection_event = False
        self.list.EnsureVisible(target)
        self.on_selected(self, self.visible_messages[target])

    def toggle_focused_message_selection(self) -> None:
        index = self.focused_index()
        if index < 0:
            self.announce_selection_count()
            return
        summary = self.visible_messages[index]
        key = self.message_key(summary)
        new_state = not self.list.IsItemChecked(index)
        self._suppress_selection_event = True
        try:
            self.list.CheckItem(index, new_state)
        finally:
            self._suppress_selection_event = False
        if new_state:
            self._multi_selected_keys.add(key)
            action = "تم تحديد الرسالة."
        else:
            self._multi_selected_keys.discard(key)
            action = "تم إلغاء تحديد الرسالة."
        self.announce_accessible(
            f"{action} عدد الرسائل المحددة: {len(self._multi_selected_keys)}."
        )

    def update_multi_selection_status(self) -> None:
        if not self.multi_select_mode:
            return
        self._multi_selected_keys = self.selected_message_keys()
        count = len(self._multi_selected_keys)
        message = tr(f"وضع التحديد المتعدد. عدد الرسائل المحددة: {count}.")
        self.selection_status.SetLabel(message)
        self.selection_status.SetName(message)
        if not self.selection_status.IsShown():
            self.selection_status.Show()
            self.Layout()

    def announce_selection_count(self) -> None:
        self._multi_selected_keys = self.selected_message_keys()
        self.announce_accessible(
            f"عدد الرسائل المحددة: {len(self._multi_selected_keys)}."
        )

    def schedule_selection_count_announcement(self) -> None:
        if self._selection_count_announce_call is not None:
            self._selection_count_announce_call.Stop()
        self._selection_count_announce_call = wx.CallLater(
            MULTI_SELECTION_ANNOUNCEMENT_DELAY_MS,
            self._announce_scheduled_selection_count,
        )

    def _announce_scheduled_selection_count(self) -> None:
        self._selection_count_announce_call = None
        if self.multi_select_mode and self.list.HasFocus():
            self.announce_selection_count()

    def schedule_multi_selection_mode_notification(self, message: str) -> None:
        if self._multi_mode_notification_call is not None:
            self._multi_mode_notification_call.Stop()
        self._multi_mode_notification_call = wx.CallLater(
            MULTI_SELECTION_ANNOUNCEMENT_DELAY_MS,
            self._show_multi_selection_mode_notification,
            message,
        )

    def _show_multi_selection_mode_notification(self, message: str) -> None:
        self._multi_mode_notification_call = None
        parent = wx.GetTopLevelParent(self)
        if parent and hasattr(parent, "show_notification"):
            parent.show_notification(message)
        else:
            self.announce_accessible(message)

    def announce_accessible(self, message: str) -> None:
        localized = tr(message)
        self.selection_status.SetLabel(localized)
        self.selection_status.SetName(localized)
        if not self.selection_status.IsShown():
            self.selection_status.Show()
            self.Layout()
        self.set_status(message)
        announce_to_screen_reader(self.selection_status, message)

    def show_content(self, content: MessageContent) -> None:
        self.current_content_key = self.message_key(content.summary)
        body = normalize_message_text(content.text)
        self.set_links(content.links)
        self.set_viewer_action_ranges(body, content.links)
        if self.viewer_mode == VIEWER_HTML:
            self.link_panel_visible_in_html = False
            self.update_link_panel_visibility()
        self.set_viewer_text(body)
        self.update_message_row(content.summary)

    def set_viewer_text(self, text: str) -> None:
        self.viewer_text = text
        try:
            self.viewer.ChangeValue(text)
        except AttributeError:
            self.viewer.SetValue(text)
        if self.viewer_mode == VIEWER_SIMPLE:
            self.show_plain_viewer()
            return
        self._html_refresh_pending = True
        if self._html_viewer_active:
            self.refresh_html_viewer(focus_start=True)
        else:
            self.show_plain_viewer()

    def refresh_html_viewer(self, *, focus_start: bool) -> None:
        self.show_html_viewer()
        self._html_focus_after_load = focus_start
        try:
            self.html_viewer.SetPage(self.message_html(self.viewer_text), "about:blank")
        except Exception:
            self._html_refresh_pending = True
            self._html_viewer_active = False
            self._html_focus_after_load = False
            self.show_plain_viewer()
            return
        self._html_refresh_pending = False

    def activate_html_viewer(self) -> None:
        self._html_viewer_active = True
        if self._html_refresh_pending:
            self.refresh_html_viewer(focus_start=True)
            return
        self.focus_html_document_start()

    def deactivate_html_viewer(self) -> None:
        self._html_viewer_active = False
        self._html_focus_after_load = False
        if self.viewer_mode == VIEWER_HTML:
            self.show_plain_viewer()

    def focus_html_document_start(self) -> None:
        if not self._html_viewer_active:
            return
        self.html_viewer.SetFocus()
        try:
            self.html_viewer.RunScript(
                "var messageElement = document.getElementById('message'); "
                "if (messageElement) { "
                "messageElement.focus(); "
                "if (document.body && document.body.createTextRange) { "
                "var textRange = document.body.createTextRange(); "
                "textRange.moveToElementText(messageElement); "
                "textRange.collapse(true); textRange.select(); "
                "} else if (document.createRange && window.getSelection) { "
                "var textSelection = window.getSelection(); "
                "var textRangeModern = document.createRange(); "
                "textRangeModern.selectNodeContents(messageElement); "
                "textRangeModern.collapse(true); "
                "textSelection.removeAllRanges(); "
                "textSelection.addRange(textRangeModern); "
                "} } window.scrollTo(0, 0);"
            )
        except (AttributeError, RuntimeError):
            pass

    def set_viewer_mode(self, mode: str) -> None:
        self.viewer_mode = VIEWER_SIMPLE if mode == VIEWER_SIMPLE else VIEWER_HTML
        self.deactivate_html_viewer()
        self._html_refresh_pending = True
        self.link_panel_visible_in_html = False
        self.update_link_panel_visibility()
        self.set_viewer_text(self.viewer_text)

    def set_theme(self, theme: str) -> None:
        self.theme = THEME_DARK if theme == THEME_DARK else THEME_LIGHT
        self.apply_viewer_colours()
        self.set_viewer_text(self.viewer_text)

    def apply_viewer_colours(self) -> None:
        if self.theme == THEME_DARK:
            background = wx.Colour(32, 33, 36)
            foreground = wx.Colour(245, 245, 245)
        else:
            background = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
            foreground = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        self.viewer.SetBackgroundColour(background)
        self.viewer.SetForegroundColour(foreground)

    def show_html_viewer(self) -> None:
        self.viewer.Show(False)
        self.html_viewer.Show(True)
        self.viewer_sizer_item.Show(False)
        self.html_viewer_sizer_item.Show(True)
        self.update_link_panel_visibility()
        self.layout_viewer_area()

    def show_plain_viewer(self) -> None:
        self.html_viewer.Show(False)
        self.viewer.Show(True)
        self.html_viewer_sizer_item.Show(False)
        self.viewer_sizer_item.Show(True)
        self.update_link_panel_visibility()
        self.layout_viewer_area()

    def layout_viewer_area(self) -> None:
        self.Layout()
        parent = self.GetParent()
        if parent:
            parent.Layout()

    def update_link_panel_visibility(self) -> None:
        if self.viewer_mode == VIEWER_HTML:
            self.link_panel.Show(bool(self.link_panel_visible_in_html))
        else:
            self.link_panel.Show(True)

    def toggle_link_panel_from_viewer(self) -> None:
        if self.viewer_mode != VIEWER_HTML:
            return
        self.link_panel_visible_in_html = not self.link_panel_visible_in_html
        self.update_link_panel_visibility()
        self.layout_viewer_area()
        if self.link_panel_visible_in_html:
            self.deactivate_html_viewer()
            self.link_list.SetFocus()
            self.set_status("تم إظهار مستعرض العناصر.")
        else:
            self.activate_html_viewer()
            self.set_status("تم إخفاء مستعرض العناصر.")

    def toggle_message_and_link_viewers(self) -> None:
        now = time.monotonic()
        if now - self._last_items_toggle_at < 0.2:
            return
        self._last_items_toggle_at = now
        focus = wx.Window.FindFocus()
        if focus in {self.link_panel, self.link_list, self.actions_button}:
            self.focus_message_viewer()
            return
        self.focus_link_panel()

    def focus_link_panel(self) -> None:
        self.deactivate_html_viewer()
        if self.viewer_mode == VIEWER_HTML and not self.link_panel_visible_in_html:
            self.link_panel_visible_in_html = True
            self.update_link_panel_visibility()
            self.layout_viewer_area()
        self.link_list.SetFocus()
        self.set_status("مستعرض العناصر.")

    def focus_message_viewer(self) -> None:
        if self.viewer_mode == VIEWER_HTML:
            if self.link_panel_visible_in_html:
                self.link_panel_visible_in_html = False
                self.update_link_panel_visibility()
                self.layout_viewer_area()
            self.activate_html_viewer()
        else:
            self.viewer.SetFocus()
        self.set_status("مستعرض الرسالة.")

    def focus_message_list(self) -> None:
        self.deactivate_html_viewer()
        self.list.SetFocus()
        self.set_status("قائمة الرسائل.")

    def focus_list_index(self, index: int) -> None:
        item_count = self.list.GetItemCount()
        if item_count <= 0:
            self.focus_message_list()
            return
        target_index = max(0, min(index, item_count - 1))
        state_mask = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
        self.list.SetItemState(-1, 0, state_mask)
        self.list.SetItemState(target_index, state_mask, state_mask)
        self.list.EnsureVisible(target_index)
        self.focus_message_list()

    @staticmethod
    def previous_message_index(deleted_index: int) -> int:
        return max(0, deleted_index - 1)

    def message_html(self, text: str) -> str:
        content = self.message_html_content(text)
        message_label = html.escape(tr("نص الرسالة"), quote=True)
        if self.theme == THEME_DARK:
            background = "#202124"
            foreground = "#f5f5f5"
            link_colour = "#8ab4f8"
            button_background = "#303134"
            button_foreground = "#f5f5f5"
            button_border = "#8a8a8a"
        else:
            background = "#fff"
            foreground = "#111"
            link_colour = "#0645ad"
            button_background = "#f3f4f6"
            button_foreground = "#111"
            button_border = "#767676"
        return f"""<!doctype html>
<html lang="{LANGUAGE_ENGLISH if not is_rtl() else LANGUAGE_ARABIC}" dir="auto">
<head>
<meta charset="utf-8">
<style>
body {{
    font-family: "Segoe UI", Tahoma, Arial, sans-serif;
    font-size: 18px;
    line-height: 1.65;
    margin: 12px;
    color: {foreground};
    background: {background};
}}
article {{
    white-space: pre-wrap;
}}
a, button {{
    font: inherit;
}}
a {{
    color: {link_colour};
}}
a[role="button"], button {{
    display: inline;
    color: {button_foreground};
    background: {button_background};
    border: 1px solid {button_border};
    padding: 1px 6px;
}}
a:focus, button:focus {{
    outline: 3px solid #005fcc;
    outline-offset: 2px;
}}
</style>
</head>
<body>
<article id="message" tabindex="0" aria-label="{message_label}">{content}</article>
<script>
function pamSend(command) {{
    if (window.pamBridge && typeof window.pamBridge.postMessage === "function") {{
        window.pamBridge.postMessage(command);
        return;
    }}
    window.location.href = "pam:" + command;
}}
document.addEventListener("keydown", function (event) {{
    if (event.ctrlKey && !event.altKey && !event.metaKey && event.code === "Space") {{
        event.preventDefault();
        pamSend("focus-list");
    }} else if (event.ctrlKey && !event.altKey && !event.metaKey && (event.code === "Enter" || event.code === "NumpadEnter")) {{
        event.preventDefault();
        pamSend("toggle-items");
    }} else if ((event.shiftKey && event.code === "F10") || event.key === "ContextMenu") {{
        event.preventDefault();
        pamSend("context-menu:keyboard");
    }}
}});
</script>
</body>
</html>"""

    def message_html_content(self, text: str) -> str:
        pieces: list[str] = []
        position = 0
        for start, end, item in self.viewer_action_ranges:
            if start < position or end > len(text):
                continue
            pieces.append(html.escape(text[position:start]))
            label = html.escape(text[start:end] or item.text or item.url)
            pieces.append(self.message_html_action(label, item))
            position = end
        pieces.append(html.escape(text[position:]))
        return "".join(pieces) or tr("لا يوجد نص قابل للعرض داخل هذه الرسالة.")

    def message_html_action(self, label: str, item: LinkItem) -> str:
        kind = "button" if item.is_button else "link"
        external_url = safe_external_url(item.url)
        if external_url:
            href = html.escape(external_url, quote=True)
            role = ' role="button"' if item.is_button else ""
            css_class = "pam-button" if item.is_button else "pam-link"
            return f'<a class="{css_class}" data-pam-kind="{kind}" href="{href}"{role}>{label}</a>'
        if item.is_button:
            return f'<button type="button" data-pam-kind="button">{label}</button>'
        return label

    def on_html_viewer_navigating(self, event: wx.html2.WebViewEvent) -> None:
        url = event.GetURL()
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme == "pam" and self.handle_html_command(parsed.path):
            event.Veto()
            return
        try:
            navigation_action = event.GetNavigationAction()
        except AttributeError:
            navigation_action = event.GetNavigationType()
        if navigation_action != wx.html2.WEBVIEW_NAV_ACTION_USER:
            return
        external_url = safe_external_url(url)
        if external_url:
            event.Veto()
            webbrowser.open(external_url)
            return
        if parsed.scheme and parsed.scheme not in {"about"}:
            event.Veto()

    def on_html_viewer_loaded(self, _event: wx.html2.WebViewEvent) -> None:
        if not self._html_viewer_active or not self._html_focus_after_load:
            return
        self._html_focus_after_load = False
        wx.CallAfter(self.focus_html_document_start)

    def on_html_viewer_pointer_focus(self, event: wx.MouseEvent) -> None:
        if not self._html_viewer_active:
            self.activate_html_viewer()
        event.Skip()

    def on_html_script_message(self, event: wx.html2.WebViewEvent) -> None:
        if event.GetMessageHandler() != "pamBridge":
            return
        self.handle_html_command(event.GetString())

    def handle_html_command(self, command: str) -> bool:
        action = command.partition(":")[0].partition("?")[0]
        if action == "focus-list":
            self.schedule_html_focus_action(self.focus_message_list)
            return True
        if action == "toggle-items":
            self.schedule_html_focus_action(self.toggle_message_and_link_viewers)
            return True
        if action == "context-menu":
            self.request_html_context_menu()
            return True
        return False

    def schedule_html_focus_action(self, action: Callable[[], None]) -> None:
        if self._html_focus_call and self._html_focus_call.IsRunning():
            self._html_focus_call.Stop()
        self._html_focus_call = wx.CallLater(75, action)

    def on_html_context_menu(self, _event: wx.ContextMenuEvent) -> None:
        self.request_html_context_menu()

    def request_html_context_menu(self) -> None:
        now = time.monotonic()
        if now - self._last_context_menu_request_at < 0.3:
            return
        self._last_context_menu_request_at = now
        wx.CallAfter(
            self.show_message_context_menu,
            self.html_viewer,
            self.has_translatable_content(),
        )

    def begin_message_load(self) -> None:
        self.set_links([])
        self.current_content_key = None
        self.set_viewer_text(tr("جار تحميل الرسالة..."))

    def set_viewer_action_ranges(self, text: str, links: list[LinkItem]) -> None:
        self.viewer_action_ranges = []
        self.current_viewer_action_range = None
        offsets: dict[str, int] = {}
        for link in links:
            if link.is_attachment:
                continue
            if self.link_has_viewer_range(text, link):
                self.viewer_action_ranges.append((link.activation_start, link.activation_end, link))
                continue
            for candidate in self.viewer_activation_candidates(text, link):
                found = self.find_viewer_action_range(text, candidate, offsets)
                if found is None:
                    continue
                start, end = found
                self.viewer_action_ranges.append((start, end, link))
                break
        self.viewer_action_ranges.sort(key=lambda action_range: action_range[0])

    def link_has_viewer_range(self, text: str, link: LinkItem) -> bool:
        return (
            0 <= link.activation_start < link.activation_end <= len(text)
            and bool(text[link.activation_start : link.activation_end].strip())
        )

    def viewer_activation_candidates(self, text: str, link: LinkItem) -> list[str]:
        candidates: list[str] = []
        if link.activation_text:
            candidates.append(link.activation_text)
        else:
            nearby_generic = self.nearby_generic_activation_text(text, link.text)
            if nearby_generic:
                candidates.append(nearby_generic)
        candidates.extend([link.text, link.url])
        unique_candidates: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            candidate = " ".join(candidate.split()).strip()
            if candidate and candidate not in seen:
                seen.add(candidate)
                unique_candidates.append(candidate)
        return unique_candidates

    def nearby_generic_activation_text(self, text: str, title: str) -> str:
        title = " ".join(title.split()).strip()
        if not title:
            return ""
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if title not in line:
                continue
            for neighbor in (index, index + 1, index - 1):
                if 0 <= neighbor < len(lines):
                    candidate_line = lines[neighbor]
                    for generic_text in INLINE_GENERIC_LINK_TEXTS:
                        if generic_text in candidate_line:
                            return generic_text
        return ""

    def find_viewer_action_range(
        self,
        text: str,
        candidate: str,
        offsets: dict[str, int],
    ) -> tuple[int, int] | None:
        start = text.find(candidate, offsets.get(candidate, 0))
        if start == -1:
            start = text.find(candidate)
        if start == -1:
            return None
        end = start + len(candidate)
        offsets[candidate] = end
        return start, end

    def update_message_row(self, summary: MessageSummary) -> None:
        key = self.message_key(summary)
        for messages in (self.messages, self.trash_messages):
            for message in messages:
                if self.message_key(message) == key:
                    message.is_read = summary.is_read
                    message.is_starred = summary.is_starred
                    message.is_pinned = summary.is_pinned
                    break
        for index, message in enumerate(self.visible_messages):
            if self.message_key(message) == key:
                message.is_read = summary.is_read
                message.is_starred = summary.is_starred
                message.is_pinned = summary.is_pinned
                self.list.SetItem(index, 0, message.status_label)
                self.list.SetItem(index, 1, message.sender)
                self.list.SetItem(index, 2, message.display_subject)
                self.list.SetItem(index, 3, message.date)
                break

    def update_message_read_state(self, summary: MessageSummary, is_read: bool) -> None:
        key = self.message_key(summary)
        for messages in (self.messages, self.trash_messages):
            for message in messages:
                if self.message_key(message) == key:
                    message.is_read = is_read
                    summary = message
                    break
        selected_filter = self.selected_filter_key()
        if selected_filter in {"unread", "read"}:
            self.apply_filter(preserve_key=key)
            return
        for index, message in enumerate(self.visible_messages):
            if self.message_key(message) == key:
                self.list.SetItem(index, 0, message.status_label)
                break

    def selected_message_key(self) -> tuple[str, str] | None:
        summary = self.selected_summary()
        return self.message_key(summary) if summary else None

    def message_key(self, summary: MessageSummary) -> tuple[str, str]:
        return summary.mailbox, summary.uid

    def all_message_keys(self) -> set[tuple[str, str]]:
        return {
            self.message_key(message)
            for messages in (self.messages, self.trash_messages)
            for message in messages
        }

    def sort_newest_first(self, messages: list[MessageSummary]) -> list[MessageSummary]:
        return sorted(messages, key=self.message_sort_key, reverse=True)

    def message_sort_key(self, message: MessageSummary) -> tuple[float, float, int, str]:
        try:
            uid_value = int(message.uid)
        except ValueError:
            uid_value = 0
        return float(message.is_pinned), message.sort_timestamp, uid_value, message.date

    def set_links(self, links: list[LinkItem]) -> None:
        self.links = links
        self.link_list.Set(self.resource_labels(links))
        if links:
            self.link_list.SetSelection(0)
        else:
            self.viewer_action_ranges = []
            self.current_viewer_action_range = None

    def update_message_flags(self, summary: MessageSummary) -> None:
        key = self.message_key(summary)
        for messages in (self.messages, self.trash_messages):
            for message in messages:
                if self.message_key(message) == key:
                    message.is_read = summary.is_read
                    message.is_starred = summary.is_starred
                    message.is_pinned = summary.is_pinned
                    break
        self.messages = self.sort_newest_first(self.messages)
        self.trash_messages = self.sort_newest_first(self.trash_messages)
        self.apply_filter(preserve_key=key)

    def update_message_flags_by_uid(self, summary: MessageSummary) -> None:
        selected_key = self.selected_message_key()
        for messages in (self.messages, self.trash_messages):
            for message in messages:
                if message.uid != summary.uid:
                    continue
                message.is_read = summary.is_read
                message.is_starred = summary.is_starred
                message.is_pinned = summary.is_pinned
        self.messages = self.sort_newest_first(self.messages)
        self.trash_messages = self.sort_newest_first(self.trash_messages)
        self.apply_filter(preserve_key=selected_key)

    def update_message_flags_bulk(
        self,
        summaries: list[MessageSummary],
        match_uid: bool = False,
    ) -> None:
        preserve_key = self.focused_message_key() or self.selected_message_key()
        by_key = {self.message_key(summary): summary for summary in summaries}
        by_uid = {summary.uid: summary for summary in summaries}
        for messages in (self.messages, self.trash_messages):
            for message in messages:
                source = (
                    by_uid.get(message.uid)
                    if match_uid
                    else by_key.get(self.message_key(message))
                )
                if not source:
                    continue
                message.is_read = source.is_read
                message.is_starred = source.is_starred
                message.is_pinned = source.is_pinned
        self.messages = self.sort_newest_first(self.messages)
        self.trash_messages = self.sort_newest_first(self.trash_messages)
        self.apply_filter(preserve_key=preserve_key)

    def remove_message(self, summary: MessageSummary) -> None:
        key = self.message_key(summary)
        self.messages = [message for message in self.messages if self.message_key(message) != key]
        self.trash_messages = [message for message in self.trash_messages if self.message_key(message) != key]
        self.visible_messages = [message for message in self.visible_messages if self.message_key(message) != key]
        self.apply_filter()
        if self.current_content_key == key:
            self.set_viewer_text("")
            self.set_links([])
            self.current_content_key = None

    def remove_messages_bulk(
        self,
        summaries: list[MessageSummary],
        match_uid: bool = False,
    ) -> None:
        keys = {self.message_key(summary) for summary in summaries}
        uids = {summary.uid for summary in summaries}

        def keep(message: MessageSummary) -> bool:
            if match_uid:
                return message.uid not in uids
            return self.message_key(message) not in keys

        self.messages = [message for message in self.messages if keep(message)]
        self.trash_messages = [
            message for message in self.trash_messages if keep(message)
        ]
        if match_uid:
            self._multi_selected_keys = {
                key for key in self._multi_selected_keys if key[1] not in uids
            }
        else:
            self._multi_selected_keys.difference_update(keys)
        self.apply_filter()
        if self.current_content_key and (
            self.current_content_key in keys
            or match_uid
            and self.current_content_key[1] in uids
        ):
            self.set_viewer_text("")
            self.set_links([])
            self.current_content_key = None

    def remove_message_by_uid(self, uid: str) -> None:
        self.messages = [message for message in self.messages if message.uid != uid]
        self.trash_messages = [message for message in self.trash_messages if message.uid != uid]
        self.visible_messages = [message for message in self.visible_messages if message.uid != uid]
        self.apply_filter()
        if self.current_content_key and self.current_content_key[1] == uid:
            self.set_viewer_text("")
            self.set_links([])
            self.current_content_key = None

    def on_open_link(self, _event: wx.CommandEvent) -> None:
        link = self.selected_link()
        if not link:
            return
        self.open_item(link)

    def on_viewer_key(self, event: wx.KeyEvent) -> None:
        if self.handle_viewer_key(event):
            return
        event.Skip()

    def handle_viewer_key(self, event: wx.KeyEvent) -> bool:
        if event.GetKeyCode() in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE}:
            item = self.viewer_item_at_caret()
            if item:
                self.open_item(item)
                return True
        return False

    def viewer_shortcut_key(self, event: wx.KeyEvent) -> str:
        if event.ControlDown() or event.AltDown() or event.CmdDown():
            return ""
        key_code = event.GetUnicodeKey()
        if key_code in {wx.WXK_NONE, 0}:
            key_code = event.GetKeyCode()
        try:
            return chr(key_code).lower()
        except (OverflowError, ValueError):
            return ""

    def move_to_viewer_action(self, buttons: bool, direction: int) -> None:
        ranges = [
            action_range
            for action_range in self.viewer_action_ranges
            if action_range[2].is_button == buttons
        ]
        item_name = self.viewer_action_group_name(buttons)
        if not ranges:
            self.set_status(f"لا يوجد {item_name} في الرسالة الحالية.")
            return

        current_index = self.current_viewer_action_index(ranges)
        if current_index is not None:
            target = ranges[(current_index + direction) % len(ranges)]
        elif direction > 0:
            position = self.current_viewer_position()
            target = next((action_range for action_range in ranges if action_range[0] >= position), ranges[0])
        else:
            position = self.current_viewer_position()
            target = next((action_range for action_range in reversed(ranges) if action_range[1] <= position), ranges[-1])
        self.select_viewer_action(target, self.viewer_action_item_name(target[2]))

    def current_viewer_action_index(self, ranges: list[tuple[int, int, LinkItem]]) -> int | None:
        position = self.current_viewer_position()
        for index, (start, end, _item) in enumerate(ranges):
            if start <= position <= end:
                return index
        if self.current_viewer_action_range in ranges:
            return ranges.index(self.current_viewer_action_range)
        return None

    def viewer_action_group_name(self, buttons: bool) -> str:
        return tr("زر") if buttons else tr("رابط")

    def viewer_action_item_name(self, item: LinkItem) -> str:
        return tr("زر") if item.is_button else tr("رابط")

    def select_viewer_action(self, action_range: tuple[int, int, LinkItem], item_name: str) -> None:
        start, end, item = action_range
        self.current_viewer_action_range = action_range
        self.viewer.SetFocus()
        self.viewer.ShowPosition(start)
        self.viewer.SetInsertionPoint(start)
        self.set_status(f"{item_name}: {item.text or item.url}")

    def viewer_item_at_caret(self) -> LinkItem | None:
        position = self.current_viewer_position()
        for start, end, item in self.viewer_action_ranges:
            if start <= position <= end:
                return item

        line_start, line_end = self.current_viewer_line_bounds(position)
        line_items = [
            item
            for start, end, item in self.viewer_action_ranges
            if line_start <= start and end <= line_end
        ]
        if len(line_items) == 1:
            return line_items[0]
        return None

    def current_viewer_position(self) -> int:
        text = self.viewer.GetValue()
        return max(0, min(self.viewer.GetInsertionPoint(), len(text)))

    def current_viewer_line_bounds(self, position: int) -> tuple[int, int]:
        text = self.viewer.GetValue()
        start = text.rfind("\n", 0, position) + 1
        end = text.find("\n", position)
        if end == -1:
            end = len(text)
        return start, end

    def open_item(self, link: LinkItem) -> None:
        if link.is_attachment:
            self.open_attachment(link)
            return
        external_url = safe_external_url(link.url)
        if external_url:
            webbrowser.open(external_url)
            return
        if link.url:
            self.set_status("تم منع فتح رابط غير آمن من الرسالة.")
            return
        if link.is_button:
            self.set_status("هذا الزر لا يحتوي على رابط قابل للفتح.")

    def on_link_key(self, event: wx.KeyEvent) -> None:
        if event.ControlDown() and event.GetKeyCode() == wx.WXK_SPACE:
            self.focus_message_list()
            return
        if event.ControlDown() and event.GetKeyCode() in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER}:
            self.toggle_message_and_link_viewers()
            return
        if event.GetKeyCode() in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE}:
            self.on_open_link(wx.CommandEvent())
            return
        event.Skip()

    def resource_labels(self, links: list[LinkItem]) -> list[str]:
        link_index = 0
        button_index = 0
        attachment_index = 0
        labels: list[str] = []
        for link in links:
            if link.is_attachment:
                attachment_index += 1
                labels.append(tr(f"مرفق {attachment_index}: {link.label}"))
            elif link.is_button:
                button_index += 1
                labels.append(tr(f"زر {button_index}: {link.label}"))
            else:
                link_index += 1
                labels.append(tr(f"رابط {link_index}: {link.label}"))
        return labels

    def open_attachment(self, item: LinkItem) -> None:
        if self.attachment_requires_confirmation(item):
            answer = wx.MessageBox(
                (
                    f"المرفق {self.safe_attachment_filename(item)} قد يشغّل أوامر "
                    "أو يحتوي على تعليمات برمجية ضارة.\n\n"
                    "هل تريد فتحه رغم ذلك؟"
                ),
                "تحذير أمان المرفق",
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
                self,
            )
            if answer != wx.YES:
                self.set_status("تم إلغاء فتح المرفق غير الآمن.")
                return
        try:
            path = self.write_attachment_to_folder(item, self.opened_attachments_dir())
            if hasattr(os, "startfile"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                webbrowser.open(path.as_uri())
        except OSError as exc:
            wx.MessageBox(str(exc), "تعذر فتح المرفق", wx.OK | wx.ICON_ERROR, self)
            return
        except RuntimeError as exc:
            wx.MessageBox(str(exc), "تعذر فتح المرفق", wx.OK | wx.ICON_INFORMATION, self)
            return
        self.set_status(f"تم فتح المرفق محليا: {path.name}")

    def save_attachment(self, item: LinkItem) -> None:
        default_name = Path(item.filename or item.text or "attachment").name or "attachment"
        dialog = wx.FileDialog(
            self,
            tr("حفظ المرفق"),
            defaultFile=default_name,
            wildcard=tr("كل الملفات (*.*)|*.*"),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            self.write_attachment_to_path(item, Path(dialog.GetPath()))
        except (OSError, RuntimeError) as exc:
            wx.MessageBox(str(exc), "خطأ في حفظ المرفق", wx.OK | wx.ICON_ERROR, self)
            return
        finally:
            dialog.Destroy()
        wx.MessageBox("تم حفظ المرفق.", "تم الحفظ", wx.OK | wx.ICON_INFORMATION, self)

    def save_all_attachments(self) -> None:
        attachments = self.attachment_items()
        if not attachments:
            wx.MessageBox("لا توجد مرفقات في الرسالة الحالية.", "حفظ المرفقات", wx.OK | wx.ICON_INFORMATION, self)
            return
        dialog = wx.DirDialog(
            self,
            tr("اختر مجلدا لحفظ المرفقات"),
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            folder = Path(dialog.GetPath())
            saved_count = 0
            for item in attachments:
                self.write_attachment_to_folder(item, folder)
                saved_count += 1
        except (OSError, RuntimeError) as exc:
            wx.MessageBox(str(exc), "خطأ في حفظ المرفقات", wx.OK | wx.ICON_ERROR, self)
            return
        finally:
            dialog.Destroy()
        wx.MessageBox(f"تم حفظ {saved_count} مرفق.", "تم الحفظ", wx.OK | wx.ICON_INFORMATION, self)

    def on_actions_button(self, _event: wx.CommandEvent) -> None:
        self.show_message_context_menu(
            self.actions_button,
            translation_enabled=self.has_translatable_content(),
        )

    def on_message_context_menu(self, event: wx.ContextMenuEvent) -> None:
        source = event.GetEventObject()
        translation_enabled = (
            source in {self.viewer, self.html_viewer}
            and self.has_translatable_content()
        )
        control = source if isinstance(source, wx.Window) else self
        self.show_message_context_menu(control, translation_enabled)

    def has_translatable_content(self) -> bool:
        text = self.viewer_text.strip()
        return bool(
            self.selected_summary()
            and text
            and text
            not in {
                tr("جار تحميل الرسالة..."),
                tr("لا يوجد نص قابل للعرض داخل هذه الرسالة."),
            }
        )

    def show_message_context_menu(self, control: wx.Window, translation_enabled: bool) -> None:
        selected_summaries = self.selected_summaries()
        if self.multi_select_mode or len(selected_summaries) > 1:
            self.show_multi_message_context_menu(control, selected_summaries)
            return
        summary = self.selected_summary()
        menu = wx.Menu()
        action_invoked = False
        return_control = self.context_return_control(control)

        def reply_action(_event: wx.CommandEvent) -> None:
            nonlocal action_invoked
            action_invoked = True
            self.on_reply()
            wx.CallAfter(self.focus_message_list)

        def star_action(_event: wx.CommandEvent) -> None:
            nonlocal action_invoked
            action_invoked = True
            self.on_toggle_star(self)
            wx.CallAfter(self.focus_message_list)

        def translate_action(_event: wx.CommandEvent) -> None:
            nonlocal action_invoked
            action_invoked = True
            self._translation_return_control = return_control
            self.on_translate(self)
            wx.CallAfter(self.restore_context_focus, return_control)

        def pin_action(_event: wx.CommandEvent) -> None:
            nonlocal action_invoked
            action_invoked = True
            self.on_toggle_pin(self)
            wx.CallAfter(self.focus_list_index, 0)

        def delete_action(_event: wx.CommandEvent) -> None:
            nonlocal action_invoked
            action_invoked = True
            self.on_delete(self)
            wx.CallAfter(self.focus_message_list)

        try:
            reply_item = menu.Append(wx.ID_ANY, tr("رد"))
            star_label = "إزالة التمييز بنجمة" if summary and summary.is_starred else "تمييز بنجمة"
            star_item = menu.Append(wx.ID_ANY, tr(star_label))
            translate_item = menu.Append(wx.ID_ANY, tr("ترجمة"))
            pin_label = "إلغاء التثبيت في الأعلى" if summary and summary.is_pinned else "التثبيت في الأعلى"
            pin_item = menu.Append(wx.ID_ANY, tr(pin_label))
            delete_item = menu.Append(wx.ID_ANY, tr("الحذف والنقل إلى سلة المحذوفات"))

            has_message = summary is not None
            reply_item.Enable(has_message)
            star_item.Enable(has_message)
            translate_item.Enable(has_message and translation_enabled)
            pin_item.Enable(has_message)
            delete_item.Enable(has_message)

            menu.Bind(wx.EVT_MENU, reply_action, reply_item)
            menu.Bind(wx.EVT_MENU, star_action, star_item)
            menu.Bind(wx.EVT_MENU, translate_action, translate_item)
            menu.Bind(wx.EVT_MENU, pin_action, pin_item)
            menu.Bind(wx.EVT_MENU, delete_action, delete_item)
            self.context_menu_popup_owner(control).PopupMenu(menu)
        finally:
            menu.Destroy()
        if not action_invoked:
            wx.CallAfter(self.restore_context_focus, return_control)

    def show_multi_message_context_menu(
        self,
        control: wx.Window,
        summaries: list[MessageSummary],
    ) -> None:
        menu = wx.Menu()
        action_invoked = False
        return_control = self.context_return_control(control)

        def invoke(action: str) -> Callable[[wx.CommandEvent], None]:
            def handler(_event: wx.CommandEvent) -> None:
                nonlocal action_invoked
                action_invoked = True
                self.on_bulk_action(self, action, list(summaries))
                wx.CallAfter(self.focus_message_list)

            return handler

        try:
            count_item = menu.Append(
                wx.ID_ANY,
                tr(f"عدد الرسائل المحددة: {len(summaries)}."),
            )
            count_item.Enable(False)
            menu.AppendSeparator()
            read_item = menu.Append(wx.ID_ANY, tr("تعليم كمقروءة"))
            unread_item = menu.Append(wx.ID_ANY, tr("تعليم كغير مقروءة"))
            star_item = menu.Append(wx.ID_ANY, tr("تمييز الرسائل بنجمة"))
            unstar_item = menu.Append(wx.ID_ANY, tr("إزالة النجمة من الرسائل"))
            pin_item = menu.Append(wx.ID_ANY, tr("تثبيت الرسائل في الأعلى"))
            unpin_item = menu.Append(wx.ID_ANY, tr("إلغاء تثبيت الرسائل"))
            menu.AppendSeparator()
            delete_item = menu.Append(
                wx.ID_ANY,
                tr("حذف الرسائل وإرسالها إلى سلة المحذوفات"),
            )

            has_messages = bool(summaries)
            for item in (
                read_item,
                unread_item,
                star_item,
                unstar_item,
                pin_item,
                unpin_item,
            ):
                item.Enable(has_messages)
            delete_item.Enable(
                has_messages and self.selected_filter_key() != "trash"
            )

            menu.Bind(
                wx.EVT_MENU,
                invoke(BULK_ACTION_MARK_READ),
                read_item,
            )
            menu.Bind(
                wx.EVT_MENU,
                invoke(BULK_ACTION_MARK_UNREAD),
                unread_item,
            )
            menu.Bind(wx.EVT_MENU, invoke(BULK_ACTION_STAR), star_item)
            menu.Bind(wx.EVT_MENU, invoke(BULK_ACTION_UNSTAR), unstar_item)
            menu.Bind(wx.EVT_MENU, invoke(BULK_ACTION_PIN), pin_item)
            menu.Bind(wx.EVT_MENU, invoke(BULK_ACTION_UNPIN), unpin_item)
            menu.Bind(wx.EVT_MENU, invoke(BULK_ACTION_DELETE), delete_item)
            self.context_menu_popup_owner(control).PopupMenu(menu)
        finally:
            menu.Destroy()
        if not action_invoked:
            wx.CallAfter(self.restore_context_focus, return_control)

    def context_menu_popup_owner(self, control: wx.Window) -> wx.Window:
        return self if control is self.html_viewer else control

    def context_return_control(self, control: wx.Window) -> wx.Window:
        if control is self.actions_button:
            return self.actions_button
        if control is self.html_viewer:
            return self.html_viewer
        if control is self.viewer:
            return self.viewer
        return control

    def take_translation_return_control(self) -> wx.Window | None:
        control = self._translation_return_control
        self._translation_return_control = None
        return control

    def restore_context_focus(self, control: wx.Window | None) -> None:
        target = control
        if target is self.html_viewer and self.viewer_mode != VIEWER_HTML:
            target = self.viewer
        try:
            if target and target.IsShownOnScreen() and target.IsEnabled():
                target.SetFocus()
                return
        except Exception:
            pass
        self.focus_message_list()

    def selected_link(self) -> LinkItem | None:
        index = self.link_list.GetSelection()
        if 0 <= index < len(self.links):
            return self.links[index]
        return None

    def attachment_items(self) -> list[LinkItem]:
        return [item for item in self.links if item.is_attachment]

    def opened_attachments_dir(self) -> Path:
        return opened_attachment_session_dir()

    def write_attachment_to_folder(self, item: LinkItem, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        filename = self.safe_attachment_filename(item)
        path = self.unique_path(folder / filename)
        self.write_attachment_to_path(item, path)
        return path

    def write_attachment_to_path(self, item: LinkItem, path: Path) -> None:
        data = item.attachment_bytes()
        if not data:
            raise RuntimeError("لا توجد بيانات محفوظة لهذا المرفق.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def safe_attachment_filename(self, item: LinkItem) -> str:
        raw_name = Path(item.filename or item.text or "attachment").name.strip() or "attachment"
        invalid_chars = '<>:"/\\|?*'
        cleaned = "".join("_" if char in invalid_chars or ord(char) < 32 else char for char in raw_name)
        cleaned = cleaned.strip(" .") or "attachment"
        cleaned = cleaned[:180]
        if Path(cleaned).stem.upper() in WINDOWS_RESERVED_FILENAMES:
            cleaned = f"_{cleaned}"
        return cleaned

    @staticmethod
    def attachment_requires_confirmation(item: LinkItem) -> bool:
        filename = item.filename or item.text
        return Path(filename).suffix.casefold() in DANGEROUS_ATTACHMENT_EXTENSIONS

    def unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem or "attachment"
        suffix = path.suffix
        for index in range(2, 1000):
            candidate = path.with_name(f"{stem} ({index}){suffix}")
            if not candidate.exists():
                return candidate
        return path.with_name(f"{stem}-{os.getpid()}{suffix}")

    def set_status(self, message: str) -> None:
        parent = wx.GetTopLevelParent(self)
        if parent and hasattr(parent, "SetStatusText"):
            parent.SetStatusText(tr(message))
