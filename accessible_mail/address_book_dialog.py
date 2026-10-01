from __future__ import annotations

from collections.abc import Callable, Sequence

import wx

from .accessibility import announce_context_menu, announce_to_screen_reader, set_accessible
from .address_book import (
    AddressEntry,
    add_address,
    load_address_book,
    normalize_email_address,
    save_address_book,
    sort_address_book,
)
from .i18n import tr
from .address_book_storage import address_hash
from .folder_store import FOLDER_CONVERSATIONS, Folder, FolderStore
from .models import MessageSummary
from .notification_preferences import EVENT_ADDRESS_BOOK
from .ui_helpers import apply_layout_direction, localize_window


AddressMessageMatch = tuple[str, MessageSummary, str]


def request_custom_address_name(parent: wx.Window, email: str) -> str:
    question = wx.MessageDialog(
        parent,
        tr("هل تريد وضع اسم مخصص لعنوان {email}؟").format(email=email),
        tr("اسم مخصص لعنوان البريد الإلكتروني"),
        wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
    )
    if hasattr(question, "SetYesNoLabels"):
        question.SetYesNoLabels(
            tr("نعم، أريد"),
            tr("كلا، الاستمرار بعنوان البريد"),
        )
    try:
        wants_name = question.ShowModal() == wx.ID_YES
    finally:
        question.Destroy()
    if not wants_name:
        return ""
    name_dialog = wx.TextEntryDialog(
        parent,
        tr("اكتب الاسم المخصص لهذا العنوان:"),
        tr("اسم مخصص لعنوان البريد الإلكتروني"),
    )
    try:
        if name_dialog.ShowModal() != wx.ID_OK:
            return ""
        return " ".join(name_dialog.GetValue().split()).strip()
    finally:
        name_dialog.Destroy()


class AddressPickerDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, entries: Sequence[AddressEntry]) -> None:
        super().__init__(parent, title=tr("اختيار عنوان بريد إلكتروني"), size=(560, 430))
        self.entries = list(entries)
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(
            wx.StaticText(self, label=tr("اختر عنوانًا ثم اضغط Enter.")),
            0,
            wx.EXPAND | wx.ALL,
            10,
        )
        self.address_list = wx.ListBox(
            self,
            choices=[entry.display_label for entry in self.entries],
        )
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
        return self.entries[selection].email if 0 <= selection < len(self.entries) else ""

    def on_activate(self, _event: wx.Event) -> None:
        if self.selected_email():
            self.EndModal(wx.ID_OK)

    def on_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE}:
            self.on_activate(event)
            return
        event.Skip()


class ForwardMessageDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        entries: Sequence[AddressEntry],
        messages: Sequence[MessageSummary],
        initial_message: MessageSummary | None = None,
    ) -> None:
        super().__init__(parent, title=tr("إعادة توجيه رسالة"), size=(780, 620))
        self.entries = list(entries)
        self.messages = [initial_message] if initial_message is not None else list(messages)
        root = wx.BoxSizer(wx.VERTICAL)

        root.Add(
            wx.StaticText(self, label=tr("اختر المستلم من سجل العناوين أو اكتب بريده الإلكتروني:")),
            0,
            wx.EXPAND | wx.ALL,
            10,
        )
        recipient_row = wx.BoxSizer(wx.HORIZONTAL)
        self.address_list = wx.ListBox(
            self,
            choices=[entry.display_label for entry in self.entries],
        )
        set_accessible(
            self.address_list,
            "سجل العناوين لإعادة التوجيه",
            "استخدم الأسهم لاختيار عنوان واضغط Enter أو Space لوضعه في حقل المستلم.",
        )
        self.address_list.Bind(wx.EVT_LISTBOX, self.on_address_selected)
        self.address_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_address_activated)
        self.address_list.Bind(wx.EVT_CHAR_HOOK, self.on_address_key)
        recipient_row.Add(self.address_list, 1, wx.EXPAND | wx.ALL, 8)

        email_column = wx.BoxSizer(wx.VERTICAL)
        email_column.Add(
            wx.StaticText(self, label=tr("البريد الإلكتروني للمستلم:")),
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            8,
        )
        self.recipient = wx.TextCtrl(self)
        set_accessible(
            self.recipient,
            "البريد الإلكتروني للمستلم",
            "اكتب عنوان البريد الإلكتروني الذي ستعاد توجيه الرسالة إليه.",
        )
        email_column.Add(self.recipient, 0, wx.EXPAND | wx.ALL, 8)
        recipient_row.Add(email_column, 1, wx.EXPAND)
        root.Add(recipient_row, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)

        root.Add(
            wx.StaticText(
                self,
                label=tr("الرسائل المختارة لإعادة التوجيه:"),
            ),
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            10,
        )
        self.message_list = wx.ListBox(
            self,
            choices=[self.message_label(message) for message in self.messages],
        )
        set_accessible(
            self.message_list,
            "الرسائل المختارة لإعادة التوجيه",
            "استخدم الأسهم لاختيار الرسالة ثم اضغط Enter أو انتقل إلى زر إعادة التوجيه.",
        )
        self.message_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_confirm)
        self.message_list.Bind(wx.EVT_CHAR_HOOK, self.on_message_key)
        root.Add(self.message_list, 2, wx.EXPAND | wx.ALL, 10)

        buttons = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        if buttons:
            root.Add(buttons, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(root)
        apply_layout_direction(self)
        localize_window(self)
        ok_button = self.FindWindowById(wx.ID_OK)
        if ok_button:
            ok_button.SetLabel(tr("إعادة التوجيه"))
            set_accessible(ok_button, "إعادة توجيه الرسالة المحددة")
            ok_button.Bind(wx.EVT_BUTTON, self.on_confirm)

        if self.entries:
            self.address_list.SetSelection(0)
        selected_index = self.message_index(initial_message)
        if self.messages:
            self.message_list.SetSelection(selected_index)
        wx.CallAfter(
            self.recipient.SetFocus if not self.entries else self.address_list.SetFocus
        )

    @staticmethod
    def message_label(message: MessageSummary) -> str:
        sender = message.sender or message.sender_email or tr("مرسل غير معروف")
        return f"{sender}; {message.display_subject}; {message.display_date}"

    def message_index(self, message: MessageSummary | None) -> int:
        if message is None:
            return 0
        target = (message.mailbox, message.uid)
        return next(
            (
                index
                for index, candidate in enumerate(self.messages)
                if (candidate.mailbox, candidate.uid) == target
            ),
            0,
        )

    def recipient_email(self) -> str:
        return normalize_email_address(self.recipient.GetValue())

    def selected_message(self) -> MessageSummary | None:
        selection = self.message_list.GetSelection()
        return self.messages[selection] if 0 <= selection < len(self.messages) else None

    def on_address_selected(self, _event: wx.Event) -> None:
        selection = self.address_list.GetSelection()
        if 0 <= selection < len(self.entries):
            self.recipient.SetValue(self.entries[selection].email)
            self.recipient.SetInsertionPointEnd()

    def on_address_activated(self, event: wx.Event) -> None:
        self.on_address_selected(event)
        self.recipient.SetFocus()

    def on_address_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE}:
            self.on_address_activated(event)
            return
        event.Skip()

    def on_message_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER}:
            self.on_confirm(event)
            return
        event.Skip()

    def on_confirm(self, _event: wx.Event) -> None:
        if not self.recipient_email():
            wx.MessageBox(
                tr("يرجى كتابة بريد إلكتروني صالح للمستلم أولاً."),
                tr("عنوان غير صالح"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self.recipient.SetFocus()
            return
        if self.selected_message() is None:
            wx.MessageBox(
                tr("يرجى اختيار رسالة لإعادة توجيهها."),
                tr("لا توجد رسالة"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self.message_list.SetFocus()
            return
        self.EndModal(wx.ID_OK)


class AddressBookDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        message_matcher: Callable[[str], list[AddressMessageMatch]] | None = None,
        account_id: str = "",
    ) -> None:
        super().__init__(parent, title=tr("سجل العناوين"), size=(680, 520))
        self.entries = load_address_book()
        self.visible_entries = list(self.entries)
        self.account_id = account_id
        self._folder_store: FolderStore | None = None
        self.Bind(wx.EVT_WINDOW_DESTROY, self.on_destroy_locks)
        self._open_folder_id = ""
        self.visible_folders: list[Folder] = []
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
                "استخدم الأسهم للتصفح واضغط Enter أو Space لفتح المجلد أو إنشاء رسالة. "
                "اضغط Backspace أو Escape للعودة من المجلد، ثم Escape مرة ثانية للعودة إلى الواجهة الرئيسية. "
                "اضغط زر التطبيقات أو Shift+F10 لفتح قائمة السياق."
            ),
        )
        self.address_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_activate)
        self.address_list.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.address_list.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_navigation_key)
        content.Add(self.address_list, 1, wx.EXPAND | wx.ALL, 10)
        self.folder_selection_list = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL,
        )
        self.folder_selection_list.InsertColumn(0, tr("المحادثة"), width=540)
        self.folder_selection_list.EnableCheckBoxes(True)
        set_accessible(
            self.folder_selection_list,
            "تحديد المحادثات للمجلد",
            "وضع التحديد المتعدد. تنقل بالأسهم واضغط Space لتحديد المحادثة أو إلغاء تحديدها. "
            "اضغط Ctrl+A لتحديد الكل، وTab للوصول إلى إنشاء المجلد أو إلغاء، وEscape للخروج.",
        )
        self.folder_selection_list.Bind(wx.EVT_CHAR_HOOK, self.on_folder_selection_key)
        self.folder_selection_list.Bind(wx.EVT_CONTEXT_MENU, self.on_folder_selection_context_menu)
        self.folder_selection_list.Bind(wx.EVT_LIST_ITEM_CHECKED, self.on_folder_selection_changed)
        self.folder_selection_list.Bind(wx.EVT_LIST_ITEM_UNCHECKED, self.on_folder_selection_changed)
        self.folder_selection_list.Hide()
        content.Add(self.folder_selection_list, 1, wx.EXPAND | wx.ALL, 10)
        self.add_button = wx.Button(self, label=tr("إضافة عنوان بريد إلكتروني جديد"))
        set_accessible(self.add_button, "إضافة عنوان بريد إلكتروني جديد")
        self.add_button.Bind(wx.EVT_BUTTON, self.on_add)
        content.Add(self.add_button, 0, wx.ALIGN_TOP | wx.TOP | wx.RIGHT, 10)
        root.Add(content, 1, wx.EXPAND)
        folder_buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.confirm_folder_button = wx.Button(self, label=tr("إنشاء المجلد"))
        self.confirm_folder_button.Bind(wx.EVT_BUTTON, self.on_confirm_conversation_folder)
        folder_buttons.Add(self.confirm_folder_button, 0, wx.ALL, 5)
        self.cancel_folder_button = wx.Button(self, label=tr("إلغاء"))
        self.cancel_folder_button.Bind(wx.EVT_BUTTON, self.on_cancel_conversation_folder)
        folder_buttons.Add(self.cancel_folder_button, 0, wx.ALL, 5)
        self.folder_buttons_item = root.Add(folder_buttons, 0, wx.ALIGN_CENTER | wx.BOTTOM, 6)
        self.folder_buttons_item.Show(False)
        self.folder_selection_status = wx.StaticText(self, label="")
        set_accessible(self.folder_selection_status, "عدد المحادثات المحددة")
        root.Add(self.folder_selection_status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.folder_selection_status.Hide()
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
        wx.CallAfter(self.address_list.SetFocus)

    def refresh_list(self, preferred_email: str = "", preferred_folder_id: str = "") -> None:
        protected = self.folder_store().protected_address_hashes()
        # An unlocked folder is the only scope allowed to display its contacts.
        # Drop previously decrypted objects before reconstructing that scope.
        self.entries = [entry for entry in self.entries if address_hash(entry.email) not in protected]
        if self.selected_folder_id():
            decrypted = self.folder_store().folder_addresses(self.account_id, self.selected_folder_id())
            known = {entry.email.casefold() for entry in self.entries}
            self.entries.extend(entry for entry in decrypted if entry.email.casefold() not in known)
        self.entries = sort_address_book(self.entries)
        folder_id = self.selected_folder_id()
        if folder_id:
            self.visible_folders = []
            try:
                emails = {
                    email.casefold()
                    for email in self.folder_store().list_items(self.account_id, folder_id)
                }
                self.visible_entries = [
                    entry for entry in self.entries if entry.email.casefold() in emails
                ]
            except Exception:
                self.visible_entries = []
        else:
            assigned_emails: set[str] = set()
            locked_hashes = self.folder_store().locked_message_hashes(self.account_id) if self.account_id else set()
            if self.account_id:
                try:
                    assigned_emails = set(self.folder_store().conversation_item_keys(self.account_id))
                except Exception:
                    pass
            self.visible_entries = [
                entry for entry in self.entries
                if entry.email.casefold() not in assigned_emails
                and self.folder_store().locked_key_hash(self.account_id, entry.email.casefold())
                not in locked_hashes
            ]
            try:
                self.visible_folders = (
                    self.folder_store().list_folders(
                        self.account_id, FOLDER_CONVERSATIONS,
                        archived=None,
                    ) if self.account_id else []
                )
            except Exception:
                self.visible_folders = []
        self.address_list.Set(
            [
                (f"{tr('مجلد')}: {folder.name}، {tr('مقفول؛ اضغط Enter لكتابة رمز الدخول')}"
                 if self.folder_store().is_locked(self.account_id, "folder", folder.id)
                 else f"{tr('مجلد')}: {folder.name}، {folder.item_count} {tr('عنوان')}")
                for folder in self.visible_folders
            ] + [
                f"{tr('مثبت')}: {entry.display_label}"
                if entry.pinned
                else entry.display_label
                for entry in self.visible_entries
            ]
        )
        if not self.visible_entries and not self.visible_folders:
            return
        target = next(
            (index for index, folder in enumerate(self.visible_folders) if folder.id == preferred_folder_id),
            None,
        )
        if target is None:
            target = next(
                (
                    len(self.visible_folders) + index
                    for index, entry in enumerate(self.visible_entries)
                    if entry.email.casefold() == preferred_email.casefold()
                ),
                0,
            )
        self.address_list.SetSelection(target)

    def selected_entry(self) -> AddressEntry | None:
        selection = self.address_list.GetSelection() - len(self.visible_folders)
        return self.visible_entries[selection] if 0 <= selection < len(self.visible_entries) else None

    def selected_folder_row(self) -> Folder | None:
        selection = self.address_list.GetSelection()
        return self.visible_folders[selection] if 0 <= selection < len(self.visible_folders) else None

    def folder_store(self) -> FolderStore:
        if self._folder_store is None:
            self._folder_store = FolderStore()
        return self._folder_store

    def selected_folder_id(self) -> str:
        return self._open_folder_id

    def on_folder_context_menu(self, _event: wx.Event | None = None, *, folder_id_override: str = "") -> None:
        selected_folder = self.selected_folder_row()
        folder_id = folder_id_override or (selected_folder.id if selected_folder else self.selected_folder_id())
        if not folder_id:
            return
        try:
            folder = self.folder_store().get_folder(self.account_id, folder_id)
        except Exception as exc:
            self.announce_event(f"تعذر فتح مجلد المحادثات: {exc}")
            return
        menu = wx.Menu()
        pin_item = menu.Append(wx.ID_ANY, tr("إلغاء تثبيت المجلد" if folder.pinned else "تثبيت المجلد في الأعلى"))
        rename_item = menu.Append(wx.ID_ANY, tr("إعادة تسمية المجلد"))
        locked = self.folder_store().is_locked(self.account_id, "folder", folder_id)
        lock_item = menu.Append(wx.ID_ANY, tr("إزالة قفل المجلد" if locked else "قفل المجلد بكلمة مرور"))
        menu.Bind(wx.EVT_MENU, lambda _event: self.toggle_conversation_folder_lock(folder_id), lock_item)
        delete_item = menu.Append(wx.ID_ANY, tr("حذف المجلد دون حذف المحادثات"))

        def update(operation: str) -> None:
            try:
                store = self.folder_store()
                if operation == "rename":
                    dialog = wx.TextEntryDialog(self, tr("اسم المجلد الجديد:"), tr("إعادة تسمية المجلد"), value=folder.name)
                    try:
                        if dialog.ShowModal() != wx.ID_OK:
                            return
                        store.rename_folder(self.account_id, folder_id, dialog.GetValue())
                    finally:
                        dialog.Destroy()
                elif operation == "pin":
                    store.set_pinned(self.account_id, folder_id, not folder.pinned)
                elif operation == "delete":
                    answer = wx.MessageBox(
                        tr("سيُحذف المجلد فقط، وتبقى المحادثات والعناوين. هل تريد المتابعة؟"),
                        tr("حذف المجلد"), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING, self,
                    )
                    if answer != wx.YES:
                        return
                    store.delete_folder(self.account_id, folder_id)
                if operation == "delete" and self._open_folder_id == folder_id:
                    store.close_target("folder", folder_id)
                    self._open_folder_id = ""
                self.refresh_list(preferred_folder_id=folder_id)
            except Exception as exc:
                wx.MessageBox(tr(str(exc)), tr("تعذر تعديل المجلد"), wx.OK | wx.ICON_ERROR, self)

        for item, operation in ((rename_item, "rename"), (pin_item, "pin")):
            menu.Bind(wx.EVT_MENU, lambda _event, action=operation: update(action), item)
        menu.Bind(wx.EVT_MENU, lambda _event: update("delete"), delete_item)
        try:
            announce_context_menu(self.address_list)
            self.address_list.PopupMenu(menu)
        finally:
            menu.Destroy()

    def on_create_conversation_folder(self, _event: wx.Event | None = None) -> None:
        if not self.account_id:
            self.announce_event("اختر حساب بريد لإنشاء مجلد محادثات.")
            return
        # Only offer addresses visible at this level. Root entries already exclude
        # members of every existing folder, including archived folders.
        self.refresh_list()
        self._folder_selection_entries = list(self.visible_entries)
        self.folder_selection_list.DeleteAllItems()
        for index, entry in enumerate(self._folder_selection_entries):
            self.folder_selection_list.InsertItem(index, entry.display_label)
        if self._folder_selection_entries:
            self.folder_selection_list.SetItemState(
                0, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
            )
        self.update_folder_selection_status()
        self.address_list.Hide()
        self.add_button.Hide()
        self.folder_selection_list.Show()
        self.folder_buttons_item.Show(True)
        self.folder_selection_status.Show()
        self.Layout()
        self.folder_selection_list.SetFocus()
        self.announce_event("تم تفعيل التحديد المتعدد للمحادثات. لا توجد محادثات محددة. استخدم Space للتحديد وTab إلى إنشاء المجلد أو إلغاء.")

    def on_folder_selection_key(self, event: wx.KeyEvent) -> None:
        key = event.GetKeyCode()
        if key == wx.WXK_ESCAPE:
            self.on_cancel_conversation_folder()
            self.announce_event("اضغط Escape مرة ثانية للعودة إلى واجهة البرنامج.")
            return
        if key == wx.WXK_BACK:
            self.on_cancel_conversation_folder()
            return
        if event.ControlDown() and not (event.ShiftDown() or event.AltDown()) and key in {1, ord("A"), ord("a"), ord("ش")}:
            for index in range(self.folder_selection_list.GetItemCount()):
                self.folder_selection_list.CheckItem(index, True)
            self.update_folder_selection_status("تم تحديد كل المحادثات الظاهرة.")
            return
        if key == wx.WXK_SPACE and not event.ControlDown() and not event.AltDown():
            index = self.folder_selection_list.GetFocusedItem()
            if index >= 0:
                self.folder_selection_list.CheckItem(index, not self.folder_selection_list.IsItemChecked(index))
                self.update_folder_selection_status()
            return
        if key in {wx.WXK_MENU, wx.WXK_WINDOWS_MENU} or (
            key == wx.WXK_F10 and event.ShiftDown()
        ):
            self.show_folder_selection_context_menu()
            return
        if key == wx.WXK_CONTROL:
            self.update_folder_selection_status()
            return
        if key == wx.WXK_TAB and not event.ShiftDown():
            self.confirm_folder_button.SetFocus()
            return
        event.Skip()

    def on_folder_selection_context_menu(self, _event: wx.ContextMenuEvent) -> None:
        self.show_folder_selection_context_menu()

    def show_folder_selection_context_menu(self) -> None:
        menu = wx.Menu()
        select_all = menu.Append(wx.ID_ANY, tr("تحديد كل المحادثات"))
        create = menu.Append(wx.ID_ANY, tr("إنشاء المجلد"))
        add = menu.Append(wx.ID_ANY, tr("إضافة المحادثات المحددة إلى مجلد موجود"))
        menu.AppendSeparator()
        cancel = menu.Append(wx.ID_ANY, tr("إلغاء التحديد والعودة"))
        has_selection = bool(self.selected_conversation_indices())
        create.Enable(has_selection)
        add.Enable(has_selection and bool(self.account_id))
        menu.Bind(wx.EVT_MENU, self.select_all_conversations, select_all)
        menu.Bind(wx.EVT_MENU, self.on_confirm_conversation_folder, create)
        menu.Bind(wx.EVT_MENU, self.on_add_selected_conversations_to_folder, add)
        menu.Bind(wx.EVT_MENU, self.on_cancel_conversation_folder, cancel)
        try:
            announce_context_menu(self.folder_selection_list)
            self.folder_selection_list.PopupMenu(menu)
        finally:
            menu.Destroy()

    def select_all_conversations(self, _event: wx.Event | None = None) -> None:
        for index in range(self.folder_selection_list.GetItemCount()):
            self.folder_selection_list.CheckItem(index, True)
        self.update_folder_selection_status("تم تحديد كل المحادثات الظاهرة.")

    def on_add_selected_conversations_to_folder(self, _event: wx.Event | None = None) -> None:
        emails = [
            self._folder_selection_entries[index].email.casefold()
            for index in self.selected_conversation_indices()
        ]
        if not emails:
            self.announce_event("حدد محادثة واحدة على الأقل أولاً.")
            return
        self.choose_conversation_folder_for_emails(emails, leave_selection=True)

    def selected_conversation_indices(self) -> list[int]:
        return [
            index for index in range(self.folder_selection_list.GetItemCount())
            if self.folder_selection_list.IsItemChecked(index)
        ]

    def on_folder_selection_changed(self, _event: wx.ListEvent) -> None:
        self.update_folder_selection_status()

    def update_folder_selection_status(self, prefix: str = "") -> None:
        count = len(self.selected_conversation_indices())
        message = tr("عدد المحادثات المحددة: {count}.").format(count=count)
        self.folder_selection_status.SetLabel(message)
        if prefix:
            self.announce_event(prefix + " " + message)

    def on_cancel_conversation_folder(self, _event: wx.Event | None = None) -> None:
        self.folder_selection_list.Hide()
        self.folder_buttons_item.Show(False)
        self.folder_selection_status.Hide()
        self.address_list.Show()
        self.add_button.Show()
        self.Layout()
        self.address_list.SetFocus()

    def on_confirm_conversation_folder(self, _event: wx.Event | None = None) -> None:
        emails = [
            self._folder_selection_entries[index].email.casefold()
            for index in self.selected_conversation_indices()
        ]
        if not emails:
            self.announce_event("حدد محادثة واحدة على الأقل لإنشاء المجلد.")
            self.folder_selection_list.SetFocus()
            return
        name_dialog = wx.TextEntryDialog(
            self, tr("اكتب اسم مجلد المحادثات:"), tr("إنشاء مجلد للمحادثات"),
        )
        try:
            if name_dialog.ShowModal() != wx.ID_OK:
                return
            name = name_dialog.GetValue()
        finally:
            name_dialog.Destroy()
        try:
            folder = self.folder_store().create_folder(
                self.account_id, FOLDER_CONVERSATIONS, name, emails,
            )
        except Exception as exc:
            wx.MessageBox(tr(str(exc)), tr("تعذر إنشاء المجلد"), wx.OK | wx.ICON_ERROR, self)
            return
        if self._open_folder_id:
            self.folder_store().close_target("folder", self._open_folder_id)
        self._open_folder_id = ""
        self.on_cancel_conversation_folder()
        self.refresh_list(preferred_folder_id=folder.id)
        self.address_list.SetFocus()
        self.announce_event(f"تم إنشاء مجلد المحادثات {folder.name} وفيه {len(emails)} عنوان.")

    def on_add_conversation_to_folder(self, _event: wx.Event | None = None) -> None:
        entry = self.selected_entry()
        if not entry or not self.account_id:
            return
        self.choose_conversation_folder_for_emails([entry.email.casefold()])

    def choose_conversation_folder_for_emails(self, emails: list[str], *, leave_selection: bool = False) -> None:
        try:
            folders = self.folder_store().list_folders(self.account_id, FOLDER_CONVERSATIONS, archived=None)
        except Exception as exc:
            self.announce_event(f"تعذر عرض مجلدات المحادثات: {exc}")
            return
        if not folders:
            self.announce_event("أنشئ مجلد محادثات أولا.")
            return
        dialog = wx.SingleChoiceDialog(
            self, tr("اختر مجلد المحادثات:"), tr("إضافة إلى مجلد المحادثات"),
            [folder.name for folder in folders],
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            folder = folders[dialog.GetSelection()]
        finally:
            dialog.Destroy()
        if not self.ensure_conversation_folder_open(folder.id):
            return
        try:
            self.folder_store().add_items(
                self.account_id, folder.id, emails,
            )
        except Exception as exc:
            self.announce_event(f"تعذر إضافة المحادثة إلى المجلد: {exc}")
            return
        if leave_selection:
            self.on_cancel_conversation_folder()
        if self._open_folder_id and self._open_folder_id != folder.id:
            self.folder_store().close_target("folder", self._open_folder_id)
        self._open_folder_id = folder.id
        self.refresh_list(emails[0])
        self.announce_event(f"أُضيفت {len(emails)} محادثة إلى المجلد {folder.name}.")

    def on_remove_conversation_from_folder(self, _event: wx.Event | None = None) -> None:
        entry = self.selected_entry()
        folder_id = self.selected_folder_id()
        if not entry or not folder_id or not self.account_id:
            return
        try:
            self.folder_store().remove_item(
                self.account_id, folder_id, entry.email.casefold(),
            )
        except Exception as exc:
            self.announce_event(f"تعذر إزالة المحادثة من المجلد: {exc}")
            return
        self.refresh_list()
        self.announce_event("أُزيلت المحادثة من المجلد وبقي العنوان في سجل العناوين.")

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
        name = request_custom_address_name(self, email)
        entry = AddressEntry(email, name=name)
        folder_id = self.selected_folder_id()
        try:
            if folder_id:
                self.folder_store().save_folder_address(self.account_id, folder_id, entry)
            else:
                added, _result = add_address(email, name)
                if not added:
                    self.show_duplicate_message()
                    return
        except Exception as exc:
            wx.MessageBox(tr(str(exc)), tr("تعذر حفظ العنوان"), wx.OK | wx.ICON_ERROR, self)
            return
        self.entries.append(entry)
        self.refresh_list(preferred_email=email)
        self.announce_event("تمت إضافة عنوان البريد الإلكتروني.")
        wx.CallAfter(self.address_list.SetFocus)

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
        replacement = AddressEntry(email, pinned=entry.pinned, name=entry.name)
        name_dialog = wx.TextEntryDialog(
            self,
            tr("اكتب الاسم المخصص لهذا العنوان، أو اتركه فارغًا:"),
            tr("تعديل الاسم المخصص"),
            value=entry.name,
        )
        try:
            if name_dialog.ShowModal() == wx.ID_OK:
                replacement.name = " ".join(name_dialog.GetValue().split()).strip()
        finally:
            name_dialog.Destroy()
        if not AddressBookDialog.persist_address_change(self, entry, replacement):
            return
        entry.email, entry.name = replacement.email, replacement.name
        self.refresh_list(email)
        self.announce_event("تم تعديل عنوان البريد الإلكتروني.")

    def on_pin(self, _event: wx.Event | None = None) -> None:
        entry = self.selected_entry()
        if not entry:
            return
        replacement = AddressEntry(entry.email, pinned=not entry.pinned, name=entry.name)
        if not AddressBookDialog.persist_address_change(self, entry, replacement):
            return
        entry.pinned = replacement.pinned
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
        try:
            folder_id = self.selected_folder_id()
            if folder_id:
                self.folder_store().delete_folder_address(self.account_id, folder_id, entry.email)
            else:
                save_address_book([candidate for candidate in self.entries if candidate is not entry])
        except Exception as exc:
            wx.MessageBox(tr(str(exc)), tr("تعذر حفظ العنوان"), wx.OK | wx.ICON_ERROR, self)
            return
        self.entries.remove(entry)
        self.refresh_list()
        self.announce_event("تم حذف عنوان البريد الإلكتروني.")

    def persist_address_change(self, old: AddressEntry, new: AddressEntry) -> bool:
        try:
            folder_id = self.selected_folder_id() if hasattr(self, "selected_folder_id") else ""
            if folder_id:
                self.folder_store().save_folder_address(self.account_id, folder_id, new, previous_email=old.email)
            else:
                save_address_book([new if entry is old else entry for entry in self.entries])
            return True
        except Exception as exc:
            wx.MessageBox(tr(str(exc)), tr("تعذر حفظ العنوان"), wx.OK | wx.ICON_ERROR, self)
            return False

    def on_activate(self, _event: wx.Event) -> None:
        folder = self.selected_folder_row()
        if folder is not None:
            if not self.ensure_conversation_folder_open(folder.id):
                return
            self._open_folder_id = folder.id
            self.refresh_list()
            self.address_list.SetFocus()
            self.announce_event(f"فُتح مجلد {folder.name}. اضغط Backspace للعودة إلى سجل العناوين.")
            return
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
        if key_code == wx.WXK_ESCAPE:
            self.on_escape_navigation()
            return
        if key_code == wx.WXK_BACK:
            if self.selected_folder_id():
                self.on_leave_conversation_folder()
            else:
                self.return_to_main()
            return
        if key_code in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE}:
            self.on_activate(event)
            return
        if key_code in {wx.WXK_MENU, wx.WXK_WINDOWS_MENU} or (
            key_code == wx.WXK_F10 and event.ShiftDown()
        ):
            self.show_context_menu()
            return
        event.Skip()

    def return_to_main(self) -> None:
        parent = self.GetParent()
        go_home = getattr(parent, "on_focus_command_list_shortcut", None)
        if self.IsModal():
            self.EndModal(wx.ID_CANCEL)
        else:
            self.Close()
        if callable(go_home):
            wx.CallAfter(go_home)

    def on_navigation_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_ESCAPE and not (event.ControlDown() or event.AltDown() or event.ShiftDown()):
            self.on_escape_navigation()
            return
        if event.GetKeyCode() == wx.WXK_BACK and not (event.ControlDown() or event.AltDown() or event.ShiftDown()):
            if self.folder_selection_list.IsShown():
                self.on_cancel_conversation_folder()
                return
            if self.selected_folder_id():
                self.on_leave_conversation_folder()
                return
            focus = wx.Window.FindFocus()
            if not isinstance(focus, (wx.TextCtrl, wx.ComboBox)):
                self.return_to_main()
                return
        event.Skip()

    def on_escape_navigation(self) -> None:
        if self.folder_selection_list.IsShown():
            self.on_cancel_conversation_folder()
        elif self.selected_folder_id():
            self.on_leave_conversation_folder()
        else:
            self.return_to_main()
            return
        self.announce_event("اضغط Escape مرة ثانية للعودة إلى واجهة البرنامج.")

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
        folder = self.selected_folder_row()
        if folder is not None:
            self.on_folder_context_menu(folder_id_override=folder.id)
            return
        entry = self.selected_entry()
        menu = wx.Menu()
        edit_item = menu.Append(wx.ID_ANY, tr("تعديل العنوان"))
        pin_label = (
            "إلغاء تثبيت العنوان من الأعلى"
            if entry and entry.pinned
            else "تثبيت العنوان بالأعلى"
        )
        pin_item = menu.Append(wx.ID_ANY, tr(pin_label))
        messages_item = menu.Append(
            wx.ID_ANY,
            tr("عرض الرسائل المرسلة والمستلمة من العنوان"),
        )
        delete_item = menu.Append(wx.ID_ANY, tr("حذف العنوان"))
        menu.AppendSeparator()
        folder_menu = wx.Menu()
        folder_item = folder_menu.Append(wx.ID_ANY, tr("إنشاء مجلد"))
        folder_item.Enable(bool(self.account_id and self.entries))
        add_folder_item = folder_menu.Append(wx.ID_ANY, tr("إضافة المحادثة إلى مجلد موجود"))
        add_folder_item.Enable(bool(entry and self.account_id))
        menu.AppendSubMenu(folder_menu, tr("خيارات المجلد"))
        if self.selected_folder_id():
            remove_folder_item = folder_menu.Append(wx.ID_ANY, tr("إزالة المحادثة من المجلد دون حذفها"))
            remove_folder_item.Enable(entry is not None)
            folder_menu.Bind(wx.EVT_MENU, self.on_remove_conversation_from_folder, remove_folder_item)
        for item in (edit_item, pin_item, messages_item, delete_item):
            item.Enable(entry is not None)
        menu.Bind(wx.EVT_MENU, self.on_edit, edit_item)
        menu.Bind(wx.EVT_MENU, self.on_pin, pin_item)
        menu.Bind(wx.EVT_MENU, self.on_view_messages, messages_item)
        menu.Bind(wx.EVT_MENU, self.on_delete, delete_item)
        folder_menu.Bind(wx.EVT_MENU, self.on_create_conversation_folder, folder_item)
        folder_menu.Bind(wx.EVT_MENU, self.on_add_conversation_to_folder, add_folder_item)
        try:
            announce_context_menu(self.address_list)
            self.address_list.PopupMenu(menu)
        finally:
            menu.Destroy()

    def on_leave_conversation_folder(self) -> None:
        folder_id = self.selected_folder_id()
        self.folder_store().close_target("folder", folder_id)
        self._open_folder_id = ""
        self._folder_selection_entries = []
        self.folder_selection_list.DeleteAllItems()
        self.refresh_list(preferred_folder_id=folder_id)
        self.address_list.SetFocus()
        self.announce_event("تمت العودة إلى سجل العناوين.")

    def ask_local_lock_password(self, message: str) -> str | None:
        dialog = wx.TextEntryDialog(self, tr(message), tr("قفل المجلد بكلمة مرور"),
                                    style=wx.OK | wx.CANCEL | wx.TE_PASSWORD)
        try:
            return dialog.GetValue() if dialog.ShowModal() == wx.ID_OK else None
        finally:
            dialog.Destroy()

    def ensure_conversation_folder_open(self, folder_id: str) -> bool:
        store = self.folder_store()
        if not store.is_locked(self.account_id, "folder", folder_id) or store.is_open(self.account_id, "folder", folder_id):
            return True
        password = self.ask_local_lock_password("أدخل كلمة مرور المجلد لعرض عناوينه:")
        if password is None:
            return False
        try:
            store.unlock_target(self.account_id, "folder", folder_id, password)
            return True
        except Exception as exc:
            wx.MessageBox(tr(str(exc)), tr("تعذر فتح قفل المجلد"), wx.OK | wx.ICON_ERROR, self)
            return False

    def toggle_conversation_folder_lock(self, folder_id: str) -> None:
        from .main_frame import MainFrame
        store = self.folder_store()
        locked = store.is_locked(self.account_id, "folder", folder_id)
        password = (self.ask_local_lock_password("أدخل كلمة المرور لإزالة قفل المجلد:")
                    if locked else MainFrame.new_local_lock_password(self))
        if password is None:
            return
        try:
            if locked:
                store.unlock_target(self.account_id, "folder", folder_id, password)
                store.remove_lock(self.account_id, "folder", folder_id)
            else:
                store.lock_target(self.account_id, "folder", folder_id, password)
            store.close_target("folder", folder_id)
            self._open_folder_id = ""
            self._folder_selection_entries = []
            self.folder_selection_list.DeleteAllItems()
            # Removing a lock restores public records; locking removes them.
            self.entries = load_address_book()
            self.refresh_list(preferred_folder_id=folder_id)
            self.address_list.SetFocus()
        except Exception as exc:
            wx.MessageBox(tr(str(exc)), tr("تعذر تعديل قفل المجلد"), wx.OK | wx.ICON_ERROR, self)

    def on_destroy_locks(self, event: wx.WindowDestroyEvent) -> None:
        if event.GetEventObject() == self and self._folder_store is not None:
            self._folder_store.close_all_locks()
            self.entries = []
            self.visible_entries = []
            self._folder_selection_entries = []
        event.Skip()

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
