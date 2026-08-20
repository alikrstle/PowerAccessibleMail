from __future__ import annotations

from collections.abc import Callable, Sequence

import wx

from .accessibility import announce_context_menu, announce_to_screen_reader, set_accessible
from .address_book import (
    AddressEntry,
    load_address_book,
    normalize_email_address,
    save_address_book,
    sort_address_book,
)
from .i18n import tr
from .models import MessageSummary
from .notification_preferences import EVENT_ADDRESS_BOOK
from .ui_helpers import apply_layout_direction, localize_window


AddressMessageMatch = tuple[str, MessageSummary, str]


class AddressPickerDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, entries: Sequence[AddressEntry]) -> None:
        super().__init__(parent, title=tr("اختيار عنوان بريد إلكتروني"), size=(560, 430))
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(
            wx.StaticText(self, label=tr("اختر عنوانًا ثم اضغط Enter.")),
            0,
            wx.EXPAND | wx.ALL,
            10,
        )
        self.address_list = wx.ListBox(self, choices=[entry.email for entry in entries])
        set_accessible(
            self.address_list,
            "عناوين البريد الإلكتروني المحفوظة",
            "استخدم الأسهم لاختيار عنوان ثم اضغط Enter أو Space.",
        )
        self.address_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_activate)
        self.address_list.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        root.Add(self.address_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        buttons = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        if buttons:
            root.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(root)
        apply_layout_direction(self)
        localize_window(self)
        if entries:
            self.address_list.SetSelection(0)
        wx.CallAfter(self.address_list.SetFocus)

    def selected_email(self) -> str:
        selection = self.address_list.GetSelection()
        return self.address_list.GetString(selection) if selection != wx.NOT_FOUND else ""

    def on_activate(self, _event: wx.Event) -> None:
        if self.selected_email():
            self.EndModal(wx.ID_OK)

    def on_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE}:
            self.on_activate(event)
            return
        event.Skip()


class AddressBookDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        message_matcher: Callable[[str], list[AddressMessageMatch]] | None = None,
    ) -> None:
        super().__init__(parent, title=tr("سجل العناوين"), size=(680, 520))
        self.entries = load_address_book()
        self.message_matcher = message_matcher
        self.compose_address = ""
        self.selected_message_match: AddressMessageMatch | None = None
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(
            wx.StaticText(self, label=tr("عناوين البريد الإلكتروني المحفوظة:")),
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            10,
        )
        content = wx.BoxSizer(wx.HORIZONTAL)
        self.address_list = wx.ListBox(self)
        set_accessible(
            self.address_list,
            "سجل عناوين البريد الإلكتروني",
            (
                "استخدم الأسهم للتصفح واضغط Enter أو Space لإنشاء رسالة. "
                "اضغط زر التطبيقات أو Shift+F10 لفتح قائمة العنوان."
            ),
        )
        self.address_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_activate)
        self.address_list.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.address_list.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)
        content.Add(self.address_list, 1, wx.EXPAND | wx.ALL, 10)
        self.add_button = wx.Button(self, label=tr("إضافة عنوان بريد إلكتروني جديد"))
        set_accessible(self.add_button, "إضافة عنوان بريد إلكتروني جديد")
        self.add_button.Bind(wx.EVT_BUTTON, self.on_add)
        content.Add(self.add_button, 0, wx.ALIGN_TOP | wx.TOP | wx.RIGHT, 10)
        root.Add(content, 1, wx.EXPAND)
        self.event_status = wx.StaticText(self, label="")
        set_accessible(
            self.event_status,
            "حالة سجل العناوين",
            "يعرض وينطق نتيجة آخر عملية في سجل العناوين.",
        )
        root.Add(
            self.event_status,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            10,
        )
        close_button = wx.Button(self, wx.ID_CANCEL, label=tr("إغلاق"))
        root.Add(close_button, 0, wx.ALIGN_CENTER | wx.ALL, 8)
        self.SetSizer(root)
        apply_layout_direction(self)
        localize_window(self)
        self.refresh_list()
        wx.CallAfter(
            self.address_list.SetFocus if self.entries else self.add_button.SetFocus
        )

    def refresh_list(self, preferred_email: str = "") -> None:
        self.entries = sort_address_book(self.entries)
        self.address_list.Set(
            [
                f"{tr('مثبت')}: {entry.email}" if entry.pinned else entry.email
                for entry in self.entries
            ]
        )
        if not self.entries:
            return
        target = next(
            (
                index
                for index, entry in enumerate(self.entries)
                if entry.email.casefold() == preferred_email.casefold()
            ),
            0,
        )
        self.address_list.SetSelection(target)

    def selected_entry(self) -> AddressEntry | None:
        selection = self.address_list.GetSelection()
        return self.entries[selection] if 0 <= selection < len(self.entries) else None

    def announce_event(self, message: str) -> None:
        localized = tr(message)
        self.event_status.SetLabel(localized)
        self.Layout()
        announce_to_screen_reader(
            self.event_status,
            message,
            EVENT_ADDRESS_BOOK,
        )

    def request_email(self, title: str, value: str = "") -> str:
        dialog = wx.TextEntryDialog(
            self,
            tr("اكتب عنوان البريد الإلكتروني:"),
            tr(title),
            value=value,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return ""
            entered = normalize_email_address(dialog.GetValue())
        finally:
            dialog.Destroy()
        if not entered:
            wx.MessageBox(
                tr("يرجى كتابة بريد إلكتروني صالح أولاً."),
                tr("عنوان غير صالح"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
        return entered

    def on_add(self, _event: wx.Event) -> None:
        email = self.request_email("إضافة عنوان بريد إلكتروني جديد")
        if not email:
            return
        if any(entry.email.casefold() == email.casefold() for entry in self.entries):
            self.show_duplicate_message()
            return
        self.entries.append(AddressEntry(email))
        save_address_book(self.entries)
        self.refresh_list(email)
        self.announce_event("تمت إضافة عنوان البريد الإلكتروني.")

    def on_edit(self, _event: wx.Event | None = None) -> None:
        entry = self.selected_entry()
        if not entry:
            return
        email = self.request_email("تعديل البريد الإلكتروني", entry.email)
        if not email:
            return
        if any(
            candidate is not entry and candidate.email.casefold() == email.casefold()
            for candidate in self.entries
        ):
            self.show_duplicate_message()
            return
        entry.email = email
        save_address_book(self.entries)
        self.refresh_list(email)
        self.announce_event("تم تعديل عنوان البريد الإلكتروني.")

    def on_pin(self, _event: wx.Event | None = None) -> None:
        entry = self.selected_entry()
        if not entry:
            return
        entry.pinned = not entry.pinned
        save_address_book(self.entries)
        self.refresh_list(entry.email)
        message = (
            "تم تثبيت البريد الإلكتروني بالأعلى."
            if entry.pinned
            else "تم إلغاء تثبيت البريد الإلكتروني من الأعلى."
        )
        self.announce_event(message)

    def on_delete(self, _event: wx.Event | None = None) -> None:
        entry = self.selected_entry()
        if not entry:
            return
        answer = wx.MessageBox(
            tr("هل تريد حذف {email} من سجل العناوين؟").format(email=entry.email),
            tr("تأكيد الحذف"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
            self,
        )
        if answer != wx.YES:
            return
        self.entries.remove(entry)
        save_address_book(self.entries)
        self.refresh_list()
        self.announce_event("تم حذف عنوان البريد الإلكتروني.")

    def on_activate(self, _event: wx.Event) -> None:
        entry = self.selected_entry()
        if entry:
            self.compose_address = entry.email
            self.EndModal(wx.ID_OK)

    def on_view_messages(self, _event: wx.Event | None = None) -> None:
        entry = self.selected_entry()
        if not entry or not self.message_matcher:
            return
        matches = self.message_matcher(entry.email)
        if not matches:
            wx.MessageBox(
                tr("لا توجد محادثات مع هذا العنوان."),
                tr("لا توجد محادثات"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            wx.CallAfter(self.address_list.SetFocus)
            return
        dialog = AddressMessagesDialog(self, entry.email, matches)
        try:
            if dialog.ShowModal() == wx.ID_OK and dialog.selected_match:
                self.selected_message_match = dialog.selected_match
                self.EndModal(wx.ID_OK)
        finally:
            dialog.Destroy()

    def on_key(self, event: wx.KeyEvent) -> None:
        key_code = event.GetKeyCode()
        if key_code in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE}:
            self.on_activate(event)
            return
        if key_code in {wx.WXK_MENU, wx.WXK_WINDOWS_MENU} or (
            key_code == wx.WXK_F10 and event.ShiftDown()
        ):
            self.show_context_menu()
            return
        event.Skip()

    def on_context_menu(self, event: wx.ContextMenuEvent) -> None:
        position = event.GetPosition()
        if position != wx.DefaultPosition:
            hit = self.address_list.HitTest(self.address_list.ScreenToClient(position))
            if isinstance(hit, tuple):
                hit = hit[0]
            if hit != wx.NOT_FOUND:
                self.address_list.SetSelection(hit)
        self.show_context_menu()

    def show_context_menu(self) -> None:
        entry = self.selected_entry()
        menu = wx.Menu()
        edit_item = menu.Append(wx.ID_ANY, tr("تعديل البريد الإلكتروني"))
        pin_label = (
            "إلغاء تثبيت البريد الإلكتروني من الأعلى"
            if entry and entry.pinned
            else "تثبيت البريد الإلكتروني بالأعلى"
        )
        pin_item = menu.Append(wx.ID_ANY, tr(pin_label))
        messages_item = menu.Append(
            wx.ID_ANY,
            tr("عرض الرسائل المرسلة والمستلمة من عنوان البريد الإلكتروني"),
        )
        delete_item = menu.Append(wx.ID_ANY, tr("حذف البريد الإلكتروني"))
        for item in (edit_item, pin_item, messages_item, delete_item):
            item.Enable(entry is not None)
        menu.Bind(wx.EVT_MENU, self.on_edit, edit_item)
        menu.Bind(wx.EVT_MENU, self.on_pin, pin_item)
        menu.Bind(wx.EVT_MENU, self.on_view_messages, messages_item)
        menu.Bind(wx.EVT_MENU, self.on_delete, delete_item)
        try:
            announce_context_menu(self.address_list)
            self.address_list.PopupMenu(menu)
        finally:
            menu.Destroy()

    def show_duplicate_message(self) -> None:
        wx.MessageBox(
            tr("عنوان البريد الإلكتروني موجود بالفعل في سجل العناوين."),
            tr("العنوان موجود"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )


class AddressMessagesDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        email: str,
        matches: Sequence[AddressMessageMatch],
    ) -> None:
        super().__init__(parent, title=tr("رسائل عنوان البريد الإلكتروني"), size=(820, 560))
        self.matches = list(matches)
        self.selected_match: AddressMessageMatch | None = None
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(
            wx.StaticText(
                self,
                label=tr("الرسائل المرتبطة بالعنوان: {email}").format(email=email),
            ),
            0,
            wx.EXPAND | wx.ALL,
            10,
        )
        self.message_list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for index, (label, width) in enumerate(
            (("النوع", 120), ("الطرف الآخر", 220), ("الموضوع", 300), ("التاريخ", 180))
        ):
            self.message_list.InsertColumn(index, tr(label), width=width)
        set_accessible(
            self.message_list,
            "الرسائل المرسلة والمستلمة من عنوان البريد الإلكتروني",
            "استخدم الأسهم للتصفح واضغط Enter أو Space لفتح الرسالة في الواجهة الرئيسية.",
        )
        for index, (_page_key, summary, direction) in enumerate(self.matches):
            row = self.message_list.InsertItem(index, tr(direction))
            other_party = (
                ", ".join(summary.recipient_emails)
                if direction == "مرسلة"
                else summary.sender or summary.sender_email
            )
            self.message_list.SetItem(row, 1, other_party)
            self.message_list.SetItem(row, 2, summary.display_subject)
            self.message_list.SetItem(row, 3, summary.display_date)
        self.message_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_activate)
        self.message_list.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        root.Add(self.message_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        close_button = wx.Button(self, wx.ID_CANCEL, label=tr("إغلاق"))
        root.Add(close_button, 0, wx.ALIGN_CENTER | wx.ALL, 8)
        self.SetSizer(root)
        apply_layout_direction(self)
        localize_window(self)
        if self.matches:
            self.message_list.SetItemState(
                0,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
            )
            wx.CallAfter(self.message_list.SetFocus)
        else:
            wx.CallAfter(close_button.SetFocus)

    def selected_index(self) -> int:
        focused = self.message_list.GetFocusedItem()
        if 0 <= focused < len(self.matches):
            return focused
        selected = self.message_list.GetFirstSelected()
        return selected if 0 <= selected < len(self.matches) else -1

    def on_activate(self, _event: wx.Event) -> None:
        index = self.selected_index()
        if index >= 0:
            self.selected_match = self.matches[index]
            self.EndModal(wx.ID_OK)

    def on_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE}:
            self.on_activate(event)
            return
        event.Skip()
