"""Additional isolated training tasks. No account or mailbox services are used."""
import wx

from .accessibility import set_accessible
from .address_book import AddressEntry
from .address_book_dialog import AddressPickerDialog, request_custom_address_name
from .command_labels import COMMAND_LABELS
from .config import ProgramSettings, VIEWER_HTML, VIEWER_SIMPLE
from .dialogs import SettingsDialog
from .i18n import get_language, tr
from .mail_page import MailPage
from .models import LinkItem, MessageContent, MessageSummary
from .ui_constants import BULK_ACTION_MARK_READ

EXTENDED_LESSONS = (
    ("الحسابات وأقسام البريد", "يبدأ التركيز على حساب Iris التجريبي. اختر حساب أحمد. انتقل بزر Tab إلى علامات تبويب أقسام البريد، وتصفحها بالأسهم: الرسائل الواردة، والرسائل غير المرغوب بها، والرسائل المرسلة، وكل الرسائل. انتقل إلى قائمة الرسائل في كل قسم.", "practice_sections", "تتعلم تبديل الحساب والانتقال بين أقسام البريد دون تغيير حساباتك الحقيقية."),
    ("التحديد المتعدد", "قف في قائمة الرسائل واضغط Ctrl+Shift+Space لتفعيل التحديد المتعدد. حدد الرسالتين الأولى والثانية بالمسافة، ثم ألغ تحديد الثانية بالمسافة. افتح قائمة السياق واختر تعليم كمقروءة. ثم اضغط Escape للخروج من التحديد المتعدد.", "practice_selection", "تتعلم تحديد عدة رسائل وتغيير المحدد فقط، دون التأثير في بقية الرسائل."),
    ("إضافة عنوان وتثبيته", "اضغط نسخ بريد احمد التجريبي. من قائمة أوامر التدريب اختر سجل العناوين، ثم اختر إضافة عنوان بريد إلكتروني جديد والصق البريد واكتب الاسم احمد. ومن ثم افتح قائمة السياق على عنوان احمد واختر تثبيت بالأعلى.", "practice_contacts", "تتعلم الوصول إلى سجل العناوين من واجهة الأوامر وإضافة عنوان جديد وتثبيته بالأعلى."),
    ("تعديل عنوان واستخدامه", "من قائمة أوامر التدريب اختر سجل العناوين. افتح قائمة السياق على عنوان أحمد المثبت واختر تعديل البريد الإلكتروني، وغيّر الاسم إلى أحمد العمل. ومن ثم اضغط Enter على العنوان لفتح إنشاء رسالة، وتأكد من ملء حقل إلى، ثم اضغط تأكيد اختيار المستلم.", "practice_contacts_edit_use", "تتعلم تعديل عنوان مثبت واستخدامه مباشرة عند إنشاء رسالة."),
    ("اختيار مستعرض الرسائل", "من قائمة أوامر التدريب اختر الإعدادات. اختر المستعرض السهل واضغط موافق؛ سينتقل التركيز إلى قائمة الرسائل. افتح الرسالة بضغط Enter أو انتقل إليها بزر Tab، واقرأ نصها بالأسهم حتى نهايته. ارجع إلى قائمة الأوامر وافتح الإعدادات، ثم اختر مستعرض HTML واضغط موافق. افتح الرسالة مرة أخرى وانتقل إلى الرابط التجريبي وفعّله. لن يفتح التدريب الموقع الخارجي.", "practice_viewers", "تتعلم تغيير مستعرض الرسائل من الإعدادات واستخدام المستعرض السهل ثم مستعرض HTML داخل واجهة بريد مماثلة للبرنامج."),
    ("مرفقات الرسالة الصادرة", "تظهر أمامك واجهة إنشاء الرسالة كما في البرنامج. انتقل إلى زر إضافة مرفق، واختر ملف خطة الاجتماع التجريبي. أضف أيضا ملف جدول المواعيد. من قائمة المرفقات حدد جدول المواعيد واضغط Delete لإزالته من المسودة فقط. أبق خطة الاجتماع ثم اضغط إرسال تجريبي.", "practice_attachments", "تتعلم إضافة المرفقات ومراجعتها وإزالة المرفق من الرسالة دون حذف ملفه الأصلي، داخل واجهة إنشاء مماثلة للبرنامج."),
    ("ترجمة النص أثناء الإنشاء", "في حقل الموضوع اكتب مرحبا. افتح قائمة سياقه واختر تحويل النص إلى لغة أخرى، ثم إضافة لغة للتحويل لها. اختر الإنجليزية واضغط إضافة اللغة. افتح القائمة مرة أخرى واختر الإنجليزية لترجمة الموضوع. كرر ذلك في المحتوى بعد كتابة شكرا.", "practice_compose_translation", "تتعلم إضافة لغة للتحويل وترجمة الموضوع والمحتوى قبل الإرسال. تستخدم المهمة ترجمات تدريبية محلية ولا ترسل النص إلى خدمة خارجية."),
    ("إضافة بريد إلى سجل العناوين عبر واجهة إنشاء الرسائل", "اضغط نسخ بريد سام التجريبي. من قائمة الأوامر اختر إنشاء بريد إلكتروني، والصق البريد في حقل إلى. انتقل بزر Tab إلى إضافة البريد الإلكتروني إلى سجل العناوين واضغطه. اختر وضع اسم مخصص واكتب سام. بعد الحفظ ستعود إلى واجهة الأوامر.", "practice_compose_address_add", "تتعلم إضافة بريد سام إلى سجل العناوين باسم مخصص من واجهة إنشاء الرسالة."),
    ("الوصول إلى الاسم عبر واجهة الإنشاء", "من قائمة الأوامر اختر إنشاء بريد إلكتروني. ضع التركيز في حقل إلى واضغط السهم للأسفل لتظهر أسماء سجل العناوين: أحمد، ثم علي، ثم سام. انتقل إلى سام واضغط Enter ليُكتب بريده في الحقل.", "practice_compose_address_pick", "تتعلم فتح سجل العناوين من حقل إلى واختيار اسم محفوظ لإدخال بريده في الرسالة."),
)


class TrainingMailPage(MailPage):
    """The real mail page, with callbacks that observe an isolated lesson."""

    def __init__(self, *args, on_training_selection_changed=None,
                 on_training_exit=None, on_training_open_item=None, **kwargs):
        self.on_training_selection_changed = on_training_selection_changed
        self.on_training_exit = on_training_exit
        self.on_training_open_item = on_training_open_item
        super().__init__(*args, **kwargs)

    def on_item_check_changed(self, index: int, checked: bool) -> None:
        super().on_item_check_changed(index, checked)
        if self.on_training_selection_changed:
            self.on_training_selection_changed(self)

    def exit_multi_selection_mode(self, restore_single_selection: bool = True) -> None:
        was_active = self.multi_select_mode
        super().exit_multi_selection_mode(restore_single_selection)
        if was_active and self.on_training_exit:
            self.on_training_exit(self)

    def open_item(self, item: LinkItem) -> None:
        if self.on_training_open_item:
            self.on_training_open_item(self, item)
            return
        super().open_item(item)

    def on_html_viewer_navigating(self, event) -> None:
        url = event.GetURL() or ""
        if self.on_training_open_item and url.startswith(("https://", "http://")):
            event.Veto()
            self.on_training_open_item(self, LinkItem(text=url, url=url))
            return
        super().on_html_viewer_navigating(event)

    def on_html_viewer_new_window(self, event) -> None:
        url = event.GetURL() or ""
        if self.on_training_open_item and url.startswith(("https://", "http://")):
            event.Veto()
            self.on_training_open_item(self, LinkItem(text=url, url=url))
            return
        super().on_html_viewer_new_window(event)


class ExtendedPractice(wx.Panel):
    def __init__(self, parent, action, completed):
        super().__init__(parent)
        self.action, self.completed = action, completed
        self.done = set()
        self.pending = False
        self.menu_open = False
        self.root = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.root)
        getattr(self, "build_" + action.removeprefix("practice_"))()
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)

    def add(self, control, proportion=0):
        self.root.Add(control, proportion, wx.EXPAND | wx.ALL, 4)
        return control

    def field(self, label, value="", multiline=False):
        self.add(wx.StaticText(self, label=tr(label)))
        control = self.add(wx.TextCtrl(self, value=value, style=wx.TE_MULTILINE if multiline else 0,
                                      size=(-1, 65) if multiline else wx.DefaultSize))
        set_accessible(control, label)
        return control

    def choice(self, label, items):
        self.add(wx.StaticText(self, label=tr(label)))
        control = self.add(wx.Choice(self, choices=[tr(item) for item in items]))
        control.SetSelection(0)
        set_accessible(control, label)
        return control

    def button(self, label, callback):
        control = self.add(wx.Button(self, label=tr(label)))
        control.Bind(wx.EVT_BUTTON, callback)
        return control

    def hint(self, text):
        wx.MessageBox(tr(text), tr("المرشد التفاعلي"), wx.OK, self)

    def finish(self):
        if not self.pending:
            self.pending = True
            self.completed()

    def popup(self, control, options):
        if self.pending or self.menu_open:
            return
        menu, selected = wx.Menu(), []
        for label, callback in options:
            item = menu.Append(wx.ID_ANY, tr(label))
            menu.Bind(wx.EVT_MENU, lambda event, callback=callback: selected.append(callback), item)
        self.menu_open = True
        try:
            control.PopupMenu(menu)
        finally:
            menu.Destroy()
            self.menu_open = False
        if selected:
            wx.CallAfter(self.invoke, selected[0])

    def invoke(self, callback):
        if self and not self.IsBeingDeleted() and self.IsShownOnScreen() and not self.pending:
            callback()

    def training_mail_page(self, parent, title, *, selection_changed=None,
                           bulk_action=None, exited=None, selected=None,
                           viewer_entered=None, open_item=None):
        def ignore(*_args, **_kwargs):
            return None

        return TrainingMailPage(
            parent,
            title,
            selected or ignore,
            ignore,
            ignore,
            ignore,
            ignore,
            ignore,
            ignore,
            bulk_action or ignore,
            on_viewer_enter=viewer_entered,
            on_training_selection_changed=selection_changed,
            on_training_exit=exited,
            on_training_open_item=open_item,
        )

    def build_training_commands(self):
        self.add(wx.StaticText(self, label=tr("الأوامر:")))
        self.command_list = self.add(
            wx.ListBox(self, choices=[tr(label) for label in COMMAND_LABELS])
        )
        self.command_list.SetSelection(0)
        self.command_list.SetMinSize((-1, 150))
        set_accessible(
            self.command_list,
            "قائمة أوامر البرنامج",
            "استخدم السهم للأعلى والأسفل ثم Enter أو Space لتنفيذ الأمر المحدد.",
        )
        self.command_list.Bind(wx.EVT_LISTBOX_DCLICK, self.activate_training_command)
        self.command_list.Bind(wx.EVT_CHAR_HOOK, self.on_training_command_key)

    def on_training_command_key(self, event):
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE):
            self.activate_training_command()
            return
        event.Skip()

    def activate_training_command(self, _event=None):
        selection = self.command_list.GetSelection()
        if self.action in {"practice_contacts", "practice_contacts_edit_use"}:
            if selection != COMMAND_LABELS.index("سجل العناوين"):
                return
            self.contacts.Show()
            self.contact_add_button.Show(self.action == "practice_contacts")
            self.Layout()
            if self.contact_name:
                self.contacts.SetFocus()
            else:
                self.contact_add_button.SetFocus()
        elif self.action == "practice_viewers":
            if selection == COMMAND_LABELS.index("الإعدادات"):
                self.show_viewer_settings()
        elif self.action in {"practice_compose_address_add", "practice_compose_address_pick"}:
            if selection == COMMAND_LABELS.index("إنشاء بريد إلكتروني"):
                self.compose_training_panel.Show()
                self.Layout()
                self.compose_to.SetFocus()

    def build_sections(self):
        self.account = self.choice("حساب التدريب", ("أحمد: ahmad@example.invalid", "Iris: iris@example.invalid"))
        self.account.SetSelection(1)
        self.section = self.add(wx.Notebook(self), 1)
        set_accessible(self.section, "أقسام البريد")
        self.message_lists = []
        for label in ("الرسائل الواردة", "الرسائل غير المرغوب بها", "الرسائل المرسلة", "كل الرسائل"):
            page = self.training_mail_page(self.section, label)
            self.section.AddPage(page, tr(label))
            self.message_lists.append(page)
            page.list.Bind(wx.EVT_SET_FOCUS, self.visit_section)
        self.account.Bind(wx.EVT_CHOICE, self.switch_section)
        self.section.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.switch_section)
        self.switch_section()

    def switch_section(self, event=None):
        account = self.account.GetSelection()
        if event is not None and event.GetEventObject() is self.account:
            self.done.add(("account", account))
        samples = ("دعوة للاجتماع", "إعلان غير مرغوب فيه", "رد أرسلته إلى الفريق")
        for index, page in enumerate(self.message_lists):
            rows = samples if index == 3 else (samples[index],)
            sender = tr("أحمد") if account == 0 else "Iris"
            page.set_messages([
                MessageSummary(
                    uid=f"training-{account}-{index}-{row_index}",
                    mailbox=f"training-{index}",
                    sender=sender,
                    sender_email=("ahmad@example.invalid" if account == 0 else "iris@example.invalid"),
                    subject=tr(subject),
                    date="2026-09-15 10:00",
                )
                for row_index, subject in enumerate(rows)
            ])
        if event is not None:
            event.Skip()

    def visit_section(self, event):
        if self.account.GetSelection() == 0 and ("account", 0) in self.done:
            self.done.add(("section", self.section.GetSelection()))
        if {("account", 0), *( ("section", i) for i in range(4))} <= self.done:
            self.finish()
        event.Skip()

    def build_selection(self):
        self.selection_page = self.add(
            self.training_mail_page(
                self,
                "الرسائل الواردة",
                selection_changed=self.selection_changed,
                bulk_action=self.apply_training_bulk_action,
                exited=self.selection_mode_exited,
            ),
            1,
        )
        self.selection_page.set_messages([
            MessageSummary(
                uid=str(index + 1),
                mailbox="training-selection",
                sender=tr("أحمد"),
                sender_email="ahmad@example.invalid",
                subject=tr(subject),
                date=f"2026-09-15 10:0{index}",
            )
            for index, subject in enumerate(
                ("الرسالة الأولى", "الرسالة الثانية", "الرسالة الثالثة")
            )
        ])

    def selection_changed(self, page):
        checked = {summary.uid for summary in page.selected_summaries()}
        if checked == {"1", "2"}:
            self.done.add("two")
        if "two" in self.done and checked == {"1"}:
            self.done.add("deselected")

    def apply_training_bulk_action(self, page, action, summaries):
        if (
            action != BULK_ACTION_MARK_READ
            or not page.multi_select_mode
            or [summary.uid for summary in summaries] != ["1"]
            or "deselected" not in self.done
        ):
            self.hint("حدد الأولى والثانية ثم ألغ تحديد الثانية قبل تطبيق الإجراء.")
            return
        summaries[0].is_read = True
        page.update_message_flags_bulk(summaries)
        self.done.add("applied")

    def selection_mode_exited(self, _page):
        if "applied" in self.done:
            self.finish()

    def build_contacts(self):
        self.build_contact_task(initial=False)

    def build_contacts_edit_use(self):
        self.build_contact_task(initial=True)

    def build_contact_task(self, *, initial):
        if not initial:
            self.copy_ahmad_button = self.button(
                "نسخ بريد احمد التجريبي",
                self.copy_ahmad_email,
            )
        self.build_training_commands()
        self.contact_name = ""
        self.pinned = False
        self.contacts = self.add(wx.ListBox(self))
        set_accessible(self.contacts, "سجل عناوين التدريب")
        self.contact_add_button = self.button(
            "إضافة عنوان بريد إلكتروني جديد",
            lambda event: self.edit_contact(False),
        )
        self.contacts.Bind(wx.EVT_CONTEXT_MENU, lambda event: self.contact_menu())
        self.contacts.Bind(wx.EVT_LISTBOX_DCLICK, lambda event: self.use_contact())
        if initial:
            self.contact_name = "أحمد"
            self.pinned = True
            self.done.add("added")
            self.contacts.Set(["أحمد: ahmad@example.invalid؛ " + tr("مثبت بالأعلى")])
            self.contacts.SetSelection(0)
        self.contacts.Hide()
        self.contact_add_button.Hide()

    def copy_ahmad_email(self, _event=None):
        copied = False
        if wx.TheClipboard.Open():
            try:
                copied = wx.TheClipboard.SetData(
                    wx.TextDataObject("ahmad@example.invalid")
                )
            finally:
                wx.TheClipboard.Close()
        if not copied:
            self.hint("تعذر نسخ البريد. يمكنك نسخه من شرح المهمة.")

    def edit_contact(self, editing):
        dialog = wx.Dialog(self, title=tr("تعديل العنوان" if editing else "إضافة عنوان"))
        root = wx.BoxSizer(wx.VERTICAL)
        fields = []
        for label, value in (("البريد الإلكتروني", "ahmad@example.invalid" if editing else ""), ("الاسم", self.contact_name if editing else "")):
            root.Add(wx.StaticText(dialog, label=tr(label)), 0, wx.ALL, 6)
            field = wx.TextCtrl(dialog, value=value)
            set_accessible(field, label)
            root.Add(field, 0, wx.EXPAND | wx.ALL, 6)
            fields.append(field)
        root.Add(dialog.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALL, 6)
        dialog.SetSizerAndFit(root)
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            email, name = [field.GetValue().strip() for field in fields]
        finally:
            dialog.Destroy()
        if email.casefold() != "ahmad@example.invalid" or name != ("أحمد العمل" if editing else "احمد"):
            self.hint("استخدم البريد والاسم المطلوبين في شرح المهمة.")
            return
        self.contact_name = name
        self.done.add("edited" if editing else "added")
        self.contacts.Set([name + ": ahmad@example.invalid"])
        self.contacts.SetSelection(0)
        self.contacts.SetFocus()

    def contact_menu(self):
        if not self.contact_name:
            return
        options = []
        if self.action == "practice_contacts_edit_use":
            options.append(("تعديل البريد الإلكتروني", lambda: self.edit_contact(True)))
        options.append(("إلغاء التثبيت" if self.pinned else "تثبيت بالأعلى", self.pin_contact))
        self.popup(self.contacts, options)

    def pin_contact(self):
        self.pinned = not self.pinned
        self.contacts.SetString(0, self.contact_name + ": ahmad@example.invalid" + ("؛ " + tr("مثبت بالأعلى") if self.pinned else ""))
        if self.action == "practice_contacts" and self.pinned and "added" in self.done:
            self.finish()

    def use_contact(self):
        if self.action != "practice_contacts_edit_use":
            return
        if "edited" not in self.done or not self.pinned:
            self.hint("عدّل الاسم إلى أحمد العمل مع إبقاء العنوان مثبتا أولا.")
            return
        dialog = wx.Dialog(self, title=tr("إنشاء رسالة تجريبية"))
        root = wx.BoxSizer(wx.VERTICAL)
        for label, value in (("إلى", "ahmad@example.invalid"), ("الموضوع", ""), ("المحتوى", "")):
            root.Add(wx.StaticText(dialog, label=tr(label)), 0, wx.ALL, 4)
            control = wx.TextCtrl(dialog, value=value)
            set_accessible(control, label)
            root.Add(control, 0, wx.EXPAND | wx.ALL, 4)
            if label == "إلى":
                recipient = control
        root.Add(dialog.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALL, 4)
        dialog.SetSizerAndFit(root)
        dialog.FindWindowById(wx.ID_OK).SetLabel(tr("تأكيد اختيار المستلم"))
        try:
            success = dialog.ShowModal() == wx.ID_OK and recipient.GetValue().strip() == "ahmad@example.invalid"
        finally:
            dialog.Destroy()
        if success:
            self.finish()

    def build_attachments(self):
        self.attached = []
        recipient_row = wx.BoxSizer(wx.HORIZONTAL)
        recipient_row.Add(wx.StaticText(self, label=tr("إلى:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 8)
        self.attachment_to = wx.TextCtrl(self, value="learner@example.invalid")
        set_accessible(self.attachment_to, "إلى")
        recipient_row.Add(self.attachment_to, 1, wx.EXPAND | wx.ALL, 8)
        self.attachment_add_address = wx.Button(self, label=tr("إضافة البريد الإلكتروني إلى سجل العناوين"))
        self.attachment_add_address.Disable()
        set_accessible(self.attachment_add_address, "إضافة البريد الإلكتروني إلى سجل العناوين", "هذا الزر ظاهر للتعرف إلى ترتيب نافذة الإنشاء، ولا يلزم في هذه المهمة.")
        recipient_row.Add(self.attachment_add_address, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 8)
        self.root.Add(recipient_row, 0, wx.EXPAND)
        subject_row = wx.BoxSizer(wx.HORIZONTAL)
        subject_row.Add(wx.StaticText(self, label=tr("الموضوع:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 8)
        self.attachment_subject = wx.TextCtrl(self, value=tr("خطة الاجتماع"))
        set_accessible(self.attachment_subject, "الموضوع")
        subject_row.Add(self.attachment_subject, 1, wx.EXPAND | wx.ALL, 8)
        self.root.Add(subject_row, 0, wx.EXPAND)
        self.add(wx.StaticText(self, label=tr("المحتوى:")))
        self.attachment_body = self.add(
            wx.TextCtrl(
                self,
                value=tr("أرفق لك خطة الاجتماع."),
                style=wx.TE_MULTILINE,
            ),
            1,
        )
        set_accessible(self.attachment_body, "محتوى الرسالة")
        self.add_attachment_button = self.button("إضافة مرفق", self.add_attachment)
        self.add(wx.StaticText(self, label=tr("المرفقات المضافة:")))
        self.files = self.add(wx.ListBox(self))
        set_accessible(self.files, "قائمة المرفقات المضافة", "اضغط Delete لإزالة المرفق المحدد أو افتح قائمة السياق.")
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.AddStretchSpacer(1)
        self.attachment_send = wx.Button(self, label=tr("إرسال تجريبي"))
        self.attachment_send.Bind(wx.EVT_BUTTON, self.review_attachments)
        buttons.Add(self.attachment_send, 0, wx.ALL, 6)
        self.attachment_cancel = wx.Button(self, label=tr("إلغاء"))
        self.attachment_cancel.Disable()
        buttons.Add(self.attachment_cancel, 0, wx.ALL, 6)
        self.root.Add(buttons, 0, wx.EXPAND)
        self.files.Bind(wx.EVT_CONTEXT_MENU, lambda event: self.popup(self.files, [("إزالة المرفق", self.remove_attachment)]))

    def add_attachment(self, event=None):
        dialog = wx.SingleChoiceDialog(self, tr("اختر ملفا تدريبيا لإرفاقه"), tr("إضافة مرفق"), [tr("خطة الاجتماع.txt"), tr("جدول المواعيد.txt")])
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            index = dialog.GetSelection()
        finally:
            dialog.Destroy()
        if index not in (0, 1):
            return
        self.done.add(index)
        if index not in self.attached:
            self.attached.append(index)
        self.update_files()

    def update_files(self):
        self.files.Set([tr(("خطة الاجتماع.txt", "جدول المواعيد.txt")[i]) for i in self.attached])
        if self.attached:
            self.files.SetSelection(0)
        self.files.SetFocus()

    def remove_attachment(self):
        index = self.files.GetSelection()
        if 0 <= index < len(self.attached):
            if self.attached.pop(index) == 1:
                self.done.add("removed")
            self.update_files()

    def review_attachments(self, event=None):
        if {0, 1, "removed"} <= self.done and self.attached == [0]:
            self.finish()
        else:
            self.hint("أضف الملفين، ثم أزل جدول المواعيد وأبق خطة الاجتماع.")

    def build_compose_translation(self):
        self.language_added = False
        self.subject = self.field("الموضوع")
        self.body = self.field("المحتوى", multiline=True)
        for control in (self.subject, self.body):
            control.Bind(wx.EVT_CONTEXT_MENU, lambda event, control=control: self.translation_menu(control))

    def build_compose_address_add(self):
        self.sam_email = "sam@example.invalid"
        self.copy_sam_button = self.button(
            "نسخ بريد سام التجريبي",
            self.copy_sam_email,
        )
        self.build_training_commands()
        self.training_entries = [
            AddressEntry("ahmad@example.invalid", name="أحمد"),
            AddressEntry("ali@example.invalid", name="علي"),
        ]

        self.build_training_compose()

    def build_compose_address_pick(self):
        self.sam_email = "sam@example.invalid"
        self.build_training_commands()
        self.training_entries = [
            AddressEntry("ahmad@example.invalid", name="أحمد"),
            AddressEntry("ali@example.invalid", name="علي"),
            AddressEntry(self.sam_email, name="سام"),
        ]
        self.build_training_compose()

    def build_training_compose(self):

        self.compose_training_panel = wx.Panel(self)
        compose_root = wx.BoxSizer(wx.VERTICAL)
        recipient_row = wx.BoxSizer(wx.HORIZONTAL)
        recipient_row.Add(
            wx.StaticText(self.compose_training_panel, label=tr("إلى:")),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.ALL,
            6,
        )
        self.compose_to = wx.TextCtrl(self.compose_training_panel)
        set_accessible(
            self.compose_to,
            "إلى",
            "اكتب عنوان المستلم أو اضغط السهم للأسفل لاختيار عنوان من سجل العناوين.",
        )
        self.compose_to.Bind(wx.EVT_KEY_DOWN, self.on_compose_training_to_key)
        recipient_row.Add(self.compose_to, 1, wx.EXPAND | wx.ALL, 6)
        self.compose_add_address = wx.Button(
            self.compose_training_panel,
            label=tr("إضافة البريد الإلكتروني إلى سجل العناوين"),
        )
        set_accessible(
            self.compose_add_address,
            "إضافة البريد الإلكتروني إلى سجل العناوين",
            "يحفظ عنوان المستلم المكتوب في سجل العناوين.",
        )
        self.compose_add_address.Bind(wx.EVT_BUTTON, self.add_training_recipient)
        if self.action == "practice_compose_address_pick":
            self.compose_add_address.Disable()
        recipient_row.Add(
            self.compose_add_address,
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.ALL,
            6,
        )
        compose_root.Add(recipient_row, 0, wx.EXPAND)
        for label, multiline in (("الموضوع:", False), ("المحتوى:", True)):
            compose_root.Add(
                wx.StaticText(self.compose_training_panel, label=tr(label)),
                0,
                wx.LEFT | wx.RIGHT | wx.TOP,
                6,
            )
            control = wx.TextCtrl(
                self.compose_training_panel,
                style=wx.TE_MULTILINE if multiline else 0,
            )
            set_accessible(control, label.rstrip(":"))
            compose_root.Add(control, 1 if multiline else 0, wx.EXPAND | wx.ALL, 6)
        self.compose_training_panel.SetSizer(compose_root)
        self.add(self.compose_training_panel, 1)
        self.compose_training_panel.Hide()

    def copy_sam_email(self, _event=None):
        copied = False
        if wx.TheClipboard.Open():
            try:
                copied = wx.TheClipboard.SetData(wx.TextDataObject(self.sam_email))
            finally:
                wx.TheClipboard.Close()
        if not copied:
            self.hint("تعذر نسخ البريد. يمكنك نسخه من شرح المهمة.")

    def add_training_recipient(self, _event=None):
        if self.compose_to.GetValue().strip().casefold() != self.sam_email:
            self.hint("الصق بريد سام التجريبي في حقل إلى أولا.")
            self.compose_to.SetFocus()
            return
        name = request_custom_address_name(self, self.sam_email)
        if name != "سام":
            self.hint("اختر وضع اسم مخصص واكتب سام لإكمال المهمة.")
            self.compose_add_address.SetFocus()
            return
        self.training_entries = [
            AddressEntry("ahmad@example.invalid", name="أحمد"),
            AddressEntry("ali@example.invalid", name="علي"),
            AddressEntry(self.sam_email, name="سام"),
        ]
        self.done.add("sam_saved")
        self.compose_training_panel.Hide()
        self.Layout()
        self.command_list.SetFocus()
        self.finish()

    def on_compose_training_to_key(self, event):
        if event.GetKeyCode() != wx.WXK_DOWN:
            event.Skip()
            return
        if self.action != "practice_compose_address_pick":
            self.hint("أضف بريد سام إلى سجل العناوين أولا.")
            return
        dialog = AddressPickerDialog(self, self.training_entries)
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            selected = dialog.selected_email()
        finally:
            dialog.Destroy()
        if selected:
            self.compose_to.SetValue(selected)
            self.compose_to.SetInsertionPointEnd()
        self.compose_to.SetFocus()
        if selected == self.sam_email:
            self.done.add("sam_selected")
            self.finish()

    def translation_menu(self, control):
        if self.pending or self.menu_open:
            return
        menu, languages, selected = wx.Menu(), wx.Menu(), []
        if self.language_added:
            item = languages.Append(wx.ID_ANY, "English — الإنجليزية")
            languages.Bind(wx.EVT_MENU, lambda event: selected.append(lambda: self.translate_control(control)), item)
        item = languages.Append(wx.ID_ANY, tr("إضافة لغة للتحويل لها"))
        languages.Bind(wx.EVT_MENU, lambda event: selected.append(self.add_language), item)
        menu.AppendSubMenu(languages, tr("تحويل النص إلى لغة أخرى"))
        for label, callback in (("نسخ", control.Copy), ("لصق", control.Paste), ("محو المكتوب", lambda: control.ChangeValue(""))):
            item = menu.Append(wx.ID_ANY, tr(label))
            menu.Bind(wx.EVT_MENU, lambda event, callback=callback: selected.append(callback), item)
        self.menu_open = True
        try:
            control.PopupMenu(menu)
        finally:
            menu.Destroy()
            self.menu_open = False
        if selected:
            wx.CallAfter(self.invoke, selected[0])

    def add_language(self):
        dialog = wx.SingleChoiceDialog(self, tr("اختر لغة التحويل في التدريب"), tr("إضافة لغة للتحويل لها"), ["English — الإنجليزية"])
        dialog.FindWindowById(wx.ID_OK).SetLabel(tr("إضافة اللغة"))
        try:
            if dialog.ShowModal() == wx.ID_OK:
                self.language_added = True
        finally:
            dialog.Destroy()

    def translate_control(self, control):
        expected, translated, key = ("مرحبا", "Hello", "subject") if control is self.subject else ("شكرا", "Thank you", "body")
        if not self.language_added or control.GetValue().strip() != expected:
            self.hint("اكتب النص المطلوب في شرح المهمة وأضف الإنجليزية أولا.")
            return
        control.ChangeValue(translated)
        self.done.add(key)
        if {"subject", "body"} <= self.done:
            self.finish()

    def build_viewers(self):
        self.build_training_commands()
        self.viewer_mode = VIEWER_HTML
        self.viewer_summary = MessageSummary(
            uid="viewer-training",
            mailbox="training-viewer",
            sender=tr("أحمد"),
            sender_email="ahmad@example.invalid",
            subject=tr("رسالة تدريب: مرحبا بك"),
            date="2026-09-15 10:00",
        )
        self.viewer_page = self.add(
            self.training_mail_page(
                self,
                "الرسائل الواردة",
                selected=self.load_viewer_training_message,
                viewer_entered=self.viewer_entered,
                open_item=self.viewer_link_requested,
            ),
            1,
        )
        self.viewer_page.set_viewer_mode(self.viewer_mode)
        self.viewer_page.set_messages([self.viewer_summary])
        self.load_viewer_training_message(self.viewer_page, self.viewer_summary)
        self.viewer_page.viewer.Bind(wx.EVT_KEY_UP, self.on_simple_viewer_navigation)
        self.viewer_page.Hide()

    def show_viewer_settings(self):
        settings = ProgramSettings(
            language=get_language(),
            message_viewer=self.viewer_mode,
        )
        dialog = SettingsDialog(self, settings)
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            selected_mode = dialog.selected_settings().message_viewer
        finally:
            dialog.Destroy()
        self.update_simple_read_state()
        if "simple_read" not in self.done and selected_mode != VIEWER_SIMPLE:
            self.hint("اختر المستعرض السهل أولا واقرأ الرسالة بالأسهم حتى نهايتها.")
            return
        if "simple_read" in self.done and selected_mode != VIEWER_HTML:
            self.hint("بعد تجربة المستعرض السهل اختر مستعرض HTML.")
            return
        self.viewer_mode = selected_mode
        self.viewer_page.set_viewer_mode(selected_mode)
        self.done.add("simple_configured" if selected_mode == VIEWER_SIMPLE else "html_configured")
        self.viewer_page.Show()
        self.Layout()
        self.viewer_page.list.SetFocus()

    def load_viewer_training_message(self, page, summary):
        page.show_content(
            MessageContent(
                summary=summary,
                text=(
                    "مرحبا بك.\n\nهذه رسالة تدريب بفقرات واضحة.\n\n"
                    "انتقل إلى الرابط التجريبي بعد اختيار مستعرض HTML."
                ),
                links=[
                    LinkItem(
                        text="الرابط التجريبي",
                        url="https://example.invalid/training",
                    )
                ],
            )
        )

    def viewer_entered(self, page, _summary):
        if page.viewer_mode == VIEWER_SIMPLE and "simple_configured" in self.done:
            self.done.add("simple_opened")
        elif (
            page.viewer_mode == VIEWER_HTML
            and {"simple_read", "html_configured"} <= self.done
        ):
            self.done.add("html_viewed")

    def on_simple_viewer_navigation(self, event):
        self.update_simple_read_state()
        event.Skip()

    def update_simple_read_state(self):
        viewer = self.viewer_page.viewer
        text = viewer.GetValue().rstrip("\r\n")
        last_line_start = max(text.rfind("\n"), text.rfind("\r")) + 1
        required_position = last_line_start if last_line_start else len(text)
        if (
            self.viewer_page.viewer_mode == VIEWER_SIMPLE
            and "simple_configured" in self.done
            and text
            and viewer.GetInsertionPoint() >= required_position
        ):
            self.done.add("simple_read")

    def viewer_link_requested(self, _page, item):
        if (
            item.url == "https://example.invalid/training"
            and {"simple_read", "html_configured", "html_viewed"} <= self.done
        ):
            self.done.add("html_link")
            self.finish()

    def on_key(self, event):
        focus, key = wx.Window.FindFocus(), event.GetKeyCode()
        if isinstance(focus, wx.Window) and wx.GetTopLevelParent(focus) is not wx.GetTopLevelParent(self):
            event.Skip()
            return
        context = key == wx.WXK_MENU or key == wx.WXK_F10 and event.ShiftDown()
        if self.action in {"practice_contacts", "practice_contacts_edit_use"} and focus is self.contacts:
            if context:
                self.contact_menu()
                return
            if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                self.use_contact()
                return
        elif self.action == "practice_attachments" and focus is self.files:
            if key == wx.WXK_DELETE:
                self.remove_attachment()
                return
            if context:
                self.popup(self.files, [("إزالة المرفق", self.remove_attachment)])
                return
        elif self.action == "practice_compose_translation" and focus in (self.subject, self.body) and context:
            self.translation_menu(focus)
            return
        event.Skip()
