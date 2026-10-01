"""Isolated, in-memory practice for local mail organization."""

from __future__ import annotations

import time
from dataclasses import replace

import wx

from .accessibility import announce_context_menu, set_accessible
from .custom_category_dialog import CategoryRulesDialog
from .folder_store import FOLDER_MESSAGES, Folder
from .i18n import tr
from .learning_extended import TrainingMailPage
from .learning_organization_text import APPROVED_SECTION_INSTRUCTION, CLEAR_FOLDER_INSTRUCTION
from .mail_page import FolderRow
from .models import MessageContent, MessageSummary
from .message_destination_dialog import choose_message_destination
from .ui_constants import (
    BULK_ACTION_MARK_READ, BULK_ACTION_PIN, BULK_ACTION_STAR,
)


ORGANIZATION_LESSONS = (
    (
        "قوائم التحديد المتعدد",
        "في قائمة رسائل التدريب، اضغط Ctrl+Shift+Space ثم حدد الرسالتين الأولى والثانية بمفتاح Space. "
        "افتح قائمة السياق، ومن القوائم الفرعية علّمهما كمقروءتين، ثم ميّزهما بنجمة، ثم ثبّتهما في الأعلى. "
        "تأكد من بقاء الرسالة الثالثة دون تغيير.",
        "organize_bulk_submenus",
        "تتعلم تنظيم إجراءات التحديد المتعدد في قوائم فرعية، وتطبيقها على الرسائل المحددة فقط.",
    ),
    (
        "إنشاء مجلد رسائل",
        CLEAR_FOLDER_INSTRUCTION,
        "organize_folder_create",
        "تتعلم إنشاء مجلد محلي من رسالتين والعثور عليه كعنصر بين الرسائل وفتحه والعودة منه.",
    ),
    (
        "إدارة مجلد الرسائل",
        "افتح قائمة السياق على مجلد التدريب: أعد تسميته، وثبّته في الأعلى، وميّزه بنجمة، "
        "ثم أرشفه. من تصنيف الرسائل المؤرشفة أعد المجلد، وارجع إلى كل التصنيفات، "
        "ثم احذف المجلد. ستبقى رسالتاه في القائمة.",
        "organize_folder_management",
        "تتعلم إدارة المجلد وحذفه دون حذف الرسائل التي كان يجمعها.",
    ),
    (
        "مجلدات المحادثات",
        "في سجل العناوين التجريبي افتح قائمة السياق واختر إنشاء مجلد. حدد أحمد وسام بمفتاح Space، "
        "ثم اضغط Tab إلى إنشاء المجلد واكتب له اسماً. افتحه بـ Enter، ثم ارجع بـ Backspace أو Escape.",
        "organize_conversation_folder",
        "تتعلم إنشاء مجلد محادثات داخل قائمة العناوين نفسها والتنقل منه وإليه.",
    ),
    (
        "الأقسام المخصصة",
        APPROVED_SECTION_INSTRUCTION,
        "organize_section",
        "تتعلم أن القسم المخصص مكان محلي للرسائل، وأن نقلها إليه لا يغيّر صندوق البريد لدى المزوّد.",
    ),
    (
        "التصنيفات المخصصة",
        "افتح قائمة السياق على صندوق التصنيفات واختر إنشاء تصنيف جديد. اختر مرشح الرسائل التي تحتوي على مرفقات، "
        "ثم اكتب اسم التصنيف. عد إلى صندوق التصنيفات واختر تصنيفك بالأسهم؛ ستظهر رسالة القسط الشهري للثلاجة "
        "وبها مرفق.",
        "organize_category",
        "تتعلم إنشاء تصنيف بمرشح المرفقات وتسميته والوصول إلى رسائله دون نقلها.",
    ),
)


def sample_messages() -> list[MessageSummary]:
    subjects = ("رسالة العمل", "القسط الشهري للثلاجة", "رحلة إلى حديقة الحيوانات")
    return [
        MessageSummary(
            uid=str(index), mailbox="training-inbox",
            sender=tr(("فريق العمل", "متجر الأجهزة المنزلية", "منظم الرحلة")[index - 1]),
            sender_email=("work@example.invalid", "payments@example.invalid", "trip@example.invalid")[index - 1],
            subject=tr(subject), date=f"2026-09-28 10:0{4 - index}",
            received_at=1790589600 + (4 - index) * 60,
            has_attachments=index == 2,
        )
        for index, subject in enumerate(subjects, start=1)
    ]


class OrganizationPractice(wx.Panel):
    def __init__(self, parent: wx.Window, action: str, completed) -> None:
        super().__init__(parent)
        self.action = action
        self.completed = completed
        self.pending = False
        self.done: set[str] = set()
        self.messages = sample_messages()
        self.message_bodies = (
            "مرحباً، سيكون اجتماع العمل يوم الأحد الساعة العاشرة صباحاً. يرجى مراجعة خطة الأسبوع قبل الاجتماع.",
            "القسط الشهري للثلاجة: نذكرك بموعد دفعه يوم الخامس من الشهر. أرفقنا كشف القسط للمراجعة.",
            "ستنطلق رحلتنا إلى حديقة الحيوانات يوم السبت الساعة التاسعة صباحاً. يرجى إحضار الماء ووجبة خفيفة.",
        )
        self.folder: Folder | None = None
        self.folder_items: set[str] = set()
        self.in_folder = False
        self.root = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.root)
        getattr(self, "build_" + action.removeprefix("organize_"))()

    def handle_navigation(self, event: wx.KeyEvent, focus: wx.Window | None) -> bool:
        """Run before the outer guide's Escape hook; never swallow text editing."""
        if event.GetKeyCode() != wx.WXK_ESCAPE or event.AltDown() or event.ControlDown() or event.ShiftDown():
            return False
        page = getattr(self, "page", None)
        if page is None and hasattr(self, "section_pages"):
            page = self.section_pages[self.sections.GetSelection()]
        if page is not None and focus in (page.viewer, page.html_viewer, page.link_list):
            page.focus_message_list()
            return True
        if page is not None and page.multi_select_mode:
            page.exit_multi_selection_mode()
        elif self.in_folder:
            self.leave_folder()
        elif getattr(self, "conversation_selecting", False):
            self.cancel_conversation_selection()
        elif getattr(self, "conversation_open", False):
            self.conversation_open = False
            self.render_contacts()
            if {"created", "opened"} <= self.done:
                self.finish()
        else:
            return False
        self.show_navigation_notice()
        return True

    def show_navigation_notice(self) -> None:
        if not hasattr(self, "navigation_notice"):
            self.navigation_notice = self.add(wx.StaticText(self))
            set_accessible(self.navigation_notice, "حالة التدريب")
        from .accessibility import announce_to_screen_reader
        text = "اضغط Escape مرة ثانية للعودة إلى واجهة البرنامج."
        self.navigation_notice.SetLabel(tr(text))
        announce_to_screen_reader(self.navigation_notice, text)
        self.Layout()

    def add(self, control: wx.Window, proportion: int = 0) -> wx.Window:
        self.root.Add(control, proportion, wx.EXPAND | wx.ALL, 4)
        return control

    def hint(self, message: str) -> None:
        wx.MessageBox(tr(message), tr("المرشد التفاعلي"), wx.OK | wx.ICON_INFORMATION, self)

    def finish(self) -> None:
        if not self.pending:
            self.pending = True
            self.completed()

    def popup(self, owner: wx.Window, options: list[tuple[str, object]]) -> None:
        if self.pending:
            return
        menu = wx.Menu()
        for label, callback in options:
            item = menu.Append(wx.ID_ANY, tr(label))
            menu.Bind(wx.EVT_MENU, lambda _event, action=callback: wx.CallAfter(action), item)
        try:
            announce_context_menu(owner)
            owner.PopupMenu(menu)
        finally:
            menu.Destroy()

    def ask_name(self, title: str, prompt: str, value: str = "") -> str | None:
        dialog = wx.TextEntryDialog(self, tr(prompt), tr(title), value=value)
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return None
            name = dialog.GetValue().strip()
        finally:
            dialog.Destroy()
        if not name:
            self.hint("اكتب اسماً قبل المتابعة.")
            return None
        return name

    def make_mail_page(self, *, bulk=None) -> TrainingMailPage:
        def ignore(*_args, **_kwargs):
            self.hint("راجع المطلوب في المهمة ثم حاول مرة أخرى.")

        page = self.add(
            TrainingMailPage(
                self, "الرسائل الواردة", self.show_training_message, ignore, ignore, ignore,
                ignore, ignore, ignore, bulk or ignore,
                on_forward=ignore, on_archive=ignore,
            ),
            1,
        )
        page.folder_rows = []
        page.on_folder_open = self.open_folder
        page.on_folder_back = self.leave_folder
        page.hide_training_item_viewer = True
        page.set_viewer_mode("simple")
        # The element filter belongs to the item viewer, not the message categories.
        page.link_panel.Hide()
        return page

    def handle_section_tab(self, event: wx.KeyEvent, focus: wx.Window | None,
                           instructions: wx.Window) -> bool:
        if (self.action != "organize_section" or event.GetKeyCode() != wx.WXK_TAB
                or event.ControlDown() or event.AltDown()):
            return False
        page = self.section_pages[self.sections.GetSelection()]
        if focus is instructions and not event.ShiftDown():
            self.sections.SetFocus()
        elif focus is self.sections:
            (instructions if event.ShiftDown() else page.filter_choice).SetFocus()
        elif focus is page.filter_choice and event.ShiftDown():
            self.sections.SetFocus()
        else:
            return False
        return True

    def show_training_message(self, page: TrainingMailPage, summary: MessageSummary) -> None:
        if isinstance(summary, FolderRow):
            return
        page.show_content(MessageContent(summary, tr(self.message_bodies[int(summary.uid) - 1]), []))

    def make_folder(self, name: str, item_keys: set[str]) -> None:
        self.folder_items = set(item_keys)
        self.folder = Folder(
            "training-folder", "training-account", FOLDER_MESSAGES, name,
            created_at=time.time(), item_count=len(item_keys),
        )

    def render_main_folder_page(self) -> None:
        self.in_folder = False
        self.page.is_message_folder_page = False
        self.page.filter_choice.Enable(True)
        if self.folder is None:
            self.page.folder_rows = []
            self.page.archive_messages = []
        else:
            row = FolderRow(replace(self.folder, item_count=len(self.folder_items)))
            self.page.folder_rows = [] if self.folder.archived else [row]
            self.page.archive_messages = [row] if self.folder.archived else []
        self.page.set_messages([
            summary for summary in self.messages if summary.uid not in self.folder_items
        ])
        self.page.apply_filter()

    def open_folder(self, folder_id: str) -> None:
        if self.folder is None or folder_id != self.folder.id:
            return
        self.in_folder = True
        self.page.is_message_folder_page = True
        self.page.filter_choice.Enable(False)
        self.page.folder_rows = []
        self.page.archive_messages = []
        self.page.filter_choice.SetSelection(0)
        self.page.set_messages([
            summary for summary in self.messages if summary.uid in self.folder_items
        ])
        self.page.list.SetFocus()
        self.done.add("opened")

    def leave_folder(self) -> None:
        if not self.in_folder:
            return
        self.page.filter_choice.SetSelection(0)
        self.render_main_folder_page()
        self.page.list.SetFocus()
        if self.action == "organize_folder_create" and {"created", "added", "opened", "removed"} <= self.done:
            self.finish()
        if self.action == "organize_folder_membership" and {"added", "removed"} <= self.done:
            self.finish()

    def build_bulk_submenus(self) -> None:
        self.page = self.make_mail_page(bulk=self.on_bulk_submenus)
        self.page.set_messages(self.messages)

    def on_bulk_submenus(self, page: TrainingMailPage, action: str, summaries: list[MessageSummary]) -> None:
        if not page.multi_select_mode or {summary.uid for summary in summaries} != {"1", "2"}:
            self.hint("حدد الرسالتين الأولى والثانية فقط قبل اختيار الإجراء.")
            return
        expected = (
            (BULK_ACTION_MARK_READ, "read"),
            (BULK_ACTION_STAR, "star"),
            (BULK_ACTION_PIN, "pin"),
        )
        index = len(self.done)
        if index >= len(expected) or action != expected[index][0]:
            self.hint("ابدأ بحالة القراءة، ثم النجمة، ثم التثبيت من القوائم الفرعية.")
            return
        for summary in summaries:
            if action == BULK_ACTION_MARK_READ:
                summary.is_read = True
            elif action == BULK_ACTION_STAR:
                summary.is_starred = True
            else:
                summary.is_pinned = True
        page.update_message_flags_bulk(summaries)
        self.done.add(expected[index][1])
        untouched = self.messages[2]
        if self.done == {"read", "star", "pin"} and not (
            untouched.is_read or untouched.is_starred or untouched.is_pinned
        ):
            self.finish()

    def build_folder_create(self) -> None:
        self.page = self.make_mail_page(bulk=self.on_folder_create_bulk)
        self.page.on_folder_open = self.open_folder
        self.page.on_folder_back = self.leave_folder
        self.page.set_messages(self.messages)

    def on_folder_create_bulk(self, page: TrainingMailPage, action: str, summaries: list[MessageSummary]) -> None:
        if action in {"add_to_folder", "remove_from_folder"}:
            self.on_folder_membership_action(page, action, summaries)
            return
        if action != "create_folder" or {summary.uid for summary in summaries} != {"1", "2"}:
            self.hint("حدد الرسالتين الأولى والثانية، ثم اضغط إنشاء المجلد.")
            return
        name = self.ask_name("إنشاء مجلد للرسائل", "اسم المجلد:")
        if name is None:
            return
        self.make_folder(name, {"1", "2"})
        page.exit_multi_selection_mode()
        self.done.add("created")
        self.render_main_folder_page()
        page.list.SetFocus()

    def build_folder_membership(self) -> None:
        self.make_folder("مجلد التدريب", {"1"})
        self.page = self.make_mail_page(bulk=self.on_folder_membership_action)
        self.page.on_folder_open = self.open_folder
        self.page.on_folder_back = self.leave_folder
        self.render_main_folder_page()

    def on_folder_membership_action(self, page: TrainingMailPage, action: str,
                                    summaries: list[MessageSummary]) -> None:
        target = "3" if self.action == "organize_folder_create" else "2"
        if self.folder is None or len(summaries) != 1 or summaries[0].uid != target:
            self.hint("طبّق الإجراء على رسالة الرحلة التي بقيت خارج المجلد.")
            return
        if action == "add_to_folder" and not self.in_folder and "added" not in self.done:
            if choose_message_destination(self) != "folder":
                return
            dialog = wx.SingleChoiceDialog(self, tr("اختر المجلد الذي ستضاف إليه الرسائل:"), tr("إضافة إلى مجلد"), [self.folder.name])
            try:
                if dialog.ShowModal() != wx.ID_OK or dialog.GetSelection() != 0:
                    return
            finally:
                dialog.Destroy()
            self.folder_items.add(target)
            self.done.add("added")
            self.render_main_folder_page()
        elif action == "remove_from_folder" and self.in_folder and "added" in self.done:
            self.folder_items.discard(target)
            self.done.add("removed")
            self.page.set_messages([summary for summary in self.messages if summary.uid in self.folder_items])
        else:
            self.hint("أضف الرسالة إلى المجلد أولاً، ثم افتح المجلد وأزلها منه.")

    def build_folder_management(self) -> None:
        self.make_folder("مجلد التدريب", {"1", "2"})
        self.page = self.make_mail_page()
        self.page.on_folder_context = self.folder_management_menu
        self.render_main_folder_page()

    def folder_management_menu(self, folder_id: str) -> None:
        if self.folder is None or folder_id != self.folder.id:
            return
        self.popup(self.page.list, [
            ("إعادة تسمية المجلد", lambda: self.manage_folder("rename")),
            ("تثبيت المجلد في الأعلى", lambda: self.manage_folder("pin")),
            ("تمييز المجلد بنجمة", lambda: self.manage_folder("star")),
            ("إعادة المجلد من الأرشيف" if self.folder.archived else "أرشفة المجلد",
             lambda: self.manage_folder("restore" if self.folder.archived else "archive")),
            ("حذف المجلد دون حذف الرسائل", lambda: self.manage_folder("delete")),
        ])

    def manage_folder(self, operation: str) -> None:
        folder = self.folder
        if folder is None:
            return
        if operation == "rename":
            name = self.ask_name("إعادة تسمية المجلد", "اسم المجلد الجديد:", folder.name)
            if name is None or name == folder.name:
                return
            self.folder = replace(folder, name=name)
            self.done.add("rename")
        elif operation == "pin":
            self.folder = replace(folder, pinned=True)
            self.done.add("pin")
        elif operation == "star":
            self.folder = replace(folder, starred=True)
            self.done.add("star")
        elif operation == "archive":
            self.folder = replace(folder, archived=True)
            self.done.add("archive")
        elif operation == "restore" and "archive" in self.done:
            self.folder = replace(folder, archived=False)
            self.done.add("restore")
        elif operation == "delete":
            if {"rename", "pin", "star", "archive", "restore"} - self.done:
                self.hint("أكمل إعادة التسمية والتثبيت والنجمة والأرشفة والاستعادة قبل حذف المجلد.")
                return
            if wx.MessageBox(tr("سيُحذف المجلد فقط وتبقى رسائله. هل تريد المتابعة؟"),
                             tr("حذف المجلد"), wx.YES_NO | wx.NO_DEFAULT, self) != wx.YES:
                return
            self.folder = None
            self.folder_items.clear()
            self.done.add("delete")
        self.render_main_folder_page()
        if operation == "delete" and len(self.page.messages) == 3:
            self.finish()

    def build_conversation_folder(self) -> None:
        self.contacts = ["أحمد: ahmad@example.invalid", "سام: sam@example.invalid", "علي: ali@example.invalid"]
        self.conversation_folder_name = ""
        self.conversation_members: set[int] = set()
        self.conversation_open = False
        self.conversation_selecting = False
        self.contact_list = self.add(wx.ListBox(self))
        set_accessible(self.contact_list, "سجل عناوين التدريب")
        self.contact_list.Bind(wx.EVT_CHAR_HOOK, self.on_contact_key)
        self.contact_list.Bind(wx.EVT_CONTEXT_MENU, lambda _event: self.contact_menu())
        self.contact_list.Bind(wx.EVT_LISTBOX_DCLICK, lambda _event: self.activate_contact())
        self.contact_checks = self.add(wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL))
        self.contact_checks.InsertColumn(0, tr("المحادثة"), width=540)
        self.contact_checks.EnableCheckBoxes(True)
        for index, contact in enumerate(self.contacts):
            self.contact_checks.InsertItem(index, contact)
        self.contact_checks.Bind(wx.EVT_CHAR_HOOK, self.on_contact_selection_key)
        set_accessible(self.contact_checks, "تحديد المحادثات للمجلد")
        self.contact_checks.Hide()
        self.confirm_conversation = self.add(wx.Button(self, label=tr("إنشاء المجلد")))
        self.confirm_conversation.Bind(wx.EVT_BUTTON, self.create_conversation_folder)
        self.confirm_conversation.Hide()
        self.cancel_conversation = self.add(wx.Button(self, label=tr("إلغاء")))
        self.cancel_conversation.Bind(wx.EVT_BUTTON, lambda _event: self.cancel_conversation_selection())
        self.cancel_conversation.Hide()
        self.render_contacts()

    def render_contacts(self) -> None:
        if self.conversation_open:
            rows = [self.contacts[index] for index in sorted(self.conversation_members)]
        else:
            rows = ([f"{tr('مجلد')}: {self.conversation_folder_name}, {len(self.conversation_members)}"]
                    if self.conversation_folder_name else []) + [
                        contact for index, contact in enumerate(self.contacts)
                        if index not in self.conversation_members
                    ]
        self.contact_list.Set(rows)
        if rows:
            self.contact_list.SetSelection(0)

    def contact_menu(self) -> None:
        if not self.conversation_open:
            self.popup(self.contact_list, [("إنشاء مجلد", self.start_conversation_selection)])

    def start_conversation_selection(self) -> None:
        self.conversation_selecting = True
        for index in range(self.contact_checks.GetItemCount()):
            self.contact_checks.CheckItem(index, False)
        self.contact_list.Hide()
        self.contact_checks.Show()
        self.confirm_conversation.Show()
        self.cancel_conversation.Show()
        self.Layout()
        self.contact_checks.SetFocus()
        self.contact_checks.Select(0)
        self.contact_checks.Focus(0)

    def on_contact_selection_key(self, event: wx.KeyEvent) -> None:
        key = event.GetKeyCode()
        if key == wx.WXK_SPACE and not event.ControlDown():
            index = self.contact_checks.GetFocusedItem()
            if index >= 0:
                self.contact_checks.CheckItem(index, not self.contact_checks.IsItemChecked(index))
        elif event.ControlDown() and key in (ord("A"), ord("a"), ord("ش")):
            for index in range(self.contact_checks.GetItemCount()):
                self.contact_checks.CheckItem(index, True)
        elif key == wx.WXK_TAB and not event.ShiftDown():
            self.confirm_conversation.SetFocus()
        elif key == wx.WXK_ESCAPE:
            self.cancel_conversation_selection()
            self.show_navigation_notice()
        else:
            event.Skip()

    def cancel_conversation_selection(self) -> None:
        self.conversation_selecting = False
        self.contact_checks.Hide()
        self.confirm_conversation.Hide()
        self.cancel_conversation.Hide()
        self.contact_list.Show()
        self.Layout()
        self.contact_list.SetFocus()

    def create_conversation_folder(self, _event=None) -> None:
        selected = {index for index in range(self.contact_checks.GetItemCount()) if self.contact_checks.IsItemChecked(index)}
        if selected != {0, 1}:
            self.hint("حدد أحمد وسام فقط لإنشاء مجلد التدريب.")
            return
        name = self.ask_name("إنشاء مجلد للمحادثات", "اكتب اسم مجلد المحادثات:")
        if name is None:
            return
        self.conversation_folder_name = name
        self.conversation_members = selected
        self.done.add("created")
        self.cancel_conversation_selection()
        self.render_contacts()

    def activate_contact(self) -> None:
        if not self.conversation_open and self.conversation_folder_name and self.contact_list.GetSelection() == 0:
            self.conversation_open = True
            self.done.add("opened")
            self.render_contacts()

    def on_contact_key(self, event: wx.KeyEvent) -> None:
        key = event.GetKeyCode()
        if key == wx.WXK_ESCAPE and self.handle_navigation(event, self.contact_list):
            return
        if self.conversation_open and key == wx.WXK_BACK:
            self.conversation_open = False
            self.render_contacts()
            self.contact_list.SetFocus()
            if {"created", "opened"} <= self.done:
                self.finish()
            return
        if key in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER}:
            self.activate_contact()
            return
        if key in {wx.WXK_MENU, wx.WXK_WINDOWS_MENU} or (key == wx.WXK_F10 and event.ShiftDown()):
            self.contact_menu()
            return
        event.Skip()

    def build_section(self) -> None:
        self.section_name = ""
        self.message_section = "inbox"
        self.sections = self.add(wx.Notebook(self), 1)
        self.section_pages = []
        for title in ("الرسائل الواردة", "الرسائل غير المرغوب بها", "الرسائل المرسلة", "كل الرسائل"):
            self.add_section_page(title)
        set_accessible(self.sections, "أقسام بريد التدريب")
        self.sections.SetSelection(0)
        self.sections.Bind(wx.EVT_CONTEXT_MENU, lambda _event: self.section_menu())
        self.sections.Bind(wx.EVT_CHAR_HOOK, self.on_section_key)
        self.sections.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_section_changed)
        self.render_section_messages()

    def add_section_page(self, title: str) -> None:
        def ignore(*_args):
            pass
        page = TrainingMailPage(self.sections, title, self.show_training_message, ignore, ignore,
                                ignore, ignore, ignore, ignore, self.on_section_bulk)
        page.hide_training_item_viewer = True
        page.set_viewer_mode("simple")
        page.link_panel.Hide()
        self.section_pages.append(page)
        self.sections.AddPage(page, tr(title))

    def on_section_changed(self, event) -> None:
        self.render_section_messages()
        event.Skip()

    def on_section_bulk(self, _page, action, summaries) -> None:
        if action == "add_to_folder" and len(summaries) == 1 and summaries[0].uid == "1":
            self.move_training_section_message()

    def return_section_message(self) -> None:
        if self.message_section != "custom" or "visited" not in self.done:
            return
        self.message_section = "inbox"
        self.done.add("returned")
        self.render_section_messages()
        if {"created", "moved", "visited", "returned"} <= self.done:
            self.finish()

    def section_menu(self) -> None:
        self.popup(self.sections, [("إنشاء قسم جديد", self.create_section)])

    def create_section(self) -> None:
        if self.section_name:
            return
        name = self.ask_name("إنشاء قسم جديد", "اسم القسم:")
        if name is None:
            return
        self.section_name = name
        self.add_section_page(name)
        page = self.section_pages[-1]
        page.list.Bind(wx.EVT_CONTEXT_MENU, lambda _event: self.section_message_menu())
        page.list.Bind(wx.EVT_CHAR_HOOK, self.on_section_message_key)
        self.done.add("created")
        self.sections.SetFocus()

    def render_section_messages(self) -> None:
        selected = self.sections.GetSelection()
        if selected < 0:
            return
        if selected == 4 and self.message_section == "custom":
            self.done.add("visited")
        for index, page in enumerate(self.section_pages):
            if index == 4:
                rows = [self.messages[0]] if self.message_section == "custom" else []
            elif index in (0, 3):
                rows = self.messages if self.message_section == "inbox" else self.messages[1:]
            else:
                rows = []
            page.set_messages(rows)
        self.section_messages = self.section_pages[selected].list

    def section_message_menu(self) -> None:
        if self.section_messages.GetFirstSelected() == wx.NOT_FOUND:
            return
        self.popup(self.section_messages, [("إعادة إلى الأقسام الأصلية", self.return_section_message)])

    def move_training_section_message(self) -> None:
        if not self.section_name:
            self.hint("أنشئ قسماً مخصصاً أولاً.")
            return
        if choose_message_destination(self) != "section":
            return
        destinations = [tr("إعادة إلى الأقسام الأصلية"), self.section_name]
        dialog = wx.SingleChoiceDialog(self, tr("اختر القسم الذي ستُنقل إليه الرسائل محلياً:"), tr("نقل الرسائل إلى قسم مخصص"), destinations)
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            destination = dialog.GetSelection()
        finally:
            dialog.Destroy()
        if destination == 1 and self.message_section == "inbox":
            self.message_section = "custom"
            self.done.add("moved")
        self.render_section_messages()
        if {"created", "moved", "visited", "returned"} <= self.done:
            self.finish()

    def on_section_key(self, event: wx.KeyEvent) -> None:
        key = event.GetKeyCode()
        if wx.Window.FindFocus() is not self.sections:
            event.Skip()
            return
        if key in {wx.WXK_LEFT, wx.WXK_RIGHT}:
            step = 1 if key == wx.WXK_RIGHT else -1
            self.sections.SetSelection((self.sections.GetSelection() + step) % self.sections.GetPageCount())
            return
        if key in {wx.WXK_MENU, wx.WXK_WINDOWS_MENU} or (key == wx.WXK_F10 and event.ShiftDown()):
            self.section_menu()
            return
        event.Skip()

    def on_section_message_key(self, event: wx.KeyEvent) -> None:
        key = event.GetKeyCode()
        if key in {wx.WXK_MENU, wx.WXK_WINDOWS_MENU} or (key == wx.WXK_F10 and event.ShiftDown()):
            self.section_message_menu()
            return
        event.Skip()

    def build_category(self) -> None:
        self.category_name = ""
        self.category_rule = ""
        self.category_email = ""
        self.categories = self.add(wx.Choice(self, choices=[tr("كل التصنيفات")]))
        set_accessible(self.categories, "صندوق التصنيفات")
        self.categories.SetSelection(0)
        self.categories.Bind(wx.EVT_CONTEXT_MENU, lambda _event: self.category_menu())
        self.categories.Bind(wx.EVT_CHAR_HOOK, self.on_category_key)
        self.categories.Bind(wx.EVT_CHOICE, lambda _event: self.render_category_messages())
        self.category_messages = self.add(wx.ListBox(self))
        set_accessible(self.category_messages, "رسائل التصنيف")
        self.render_category_messages()

    def category_menu(self) -> None:
        options = [("إنشاء تصنيف جديد", self.create_category)]
        self.popup(self.categories, options)

    def choose_category_rule(self, initial: tuple[str, ...] = ()) -> str | None:
        options = (
            ("recent_read", tr("الرسائل التي قرأتها خلال آخر 7 أيام")),
            ("promotional", tr("الرسائل الترويجية")),
            ("organization", tr("رسائل الشركات والمؤسسات")),
            ("specific_email", tr("الرسائل المرتبطة بعناوين بريد محددة")),
            ("frequent_sender", tr("رسائل المرسلين كثيري الاستلام (5 رسائل أو أكثر)")),
            ("locked_messages", tr("الرسائل المقفولة")),
            ("message_folders", tr("مجلدات الرسائل")),
            ("attachments", tr("الرسائل التي تحتوي على مرفقات")),
            ("no_attachments", tr("الرسائل التي لا تحتوي على مرفقات")),
        )
        dialog = CategoryRulesDialog(self, options, initial)
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return None
            selected = dialog.selected_rules()
        finally:
            dialog.Destroy()
        return selected[0] if selected else None

    def create_category(self) -> None:
        if self.category_name:
            return
        rule = self.choose_category_rule()
        if rule is None:
            return
        if rule != "attachments":
            self.hint("اختر مرشح الرسائل التي تحتوي على مرفقات.")
            return
        name = self.ask_name("إنشاء تصنيف جديد", "اسم التصنيف:")
        if name is None:
            return
        self.category_name = name
        self.category_rule = rule
        self.categories.Append(name)
        self.categories.SetSelection(0)
        self.done.add("created")
        self.render_category_messages()
        self.categories.SetFocus()

    def render_category_messages(self) -> None:
        if self.categories.GetSelection() != 1 or not self.category_name:
            rows = [summary.subject for summary in self.messages]
        elif self.category_rule == "specific_email":
            rows = [self.messages[0].subject]
            self.done.add("specific_viewed")
        elif self.category_rule == "attachments":
            rows = [self.messages[1].subject]
            self.done.add("attachments_viewed")
            if "created" in self.done:
                self.finish()
        else:
            rows = []
        self.category_messages.Set(rows)
        if rows:
            self.category_messages.SetSelection(0)

    def on_category_key(self, event: wx.KeyEvent) -> None:
        key = event.GetKeyCode()
        if key in {wx.WXK_MENU, wx.WXK_WINDOWS_MENU} or (key == wx.WXK_F10 and event.ShiftDown()):
            self.category_menu()
            return
        event.Skip()
