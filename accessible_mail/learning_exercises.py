"""Self-contained practice fixtures: no network, accounts or file access."""
import wx
from .accessibility import set_accessible
from .i18n import tr
from .command_labels import COMMAND_LABELS, COMPOSE_COMMAND_INDEX
from .search_filters import DATE_FILTER_LABELS
from .learning_extended import EXTENDED_LESSONS, ExtendedPractice

EXERCISES = (
    ("إعادة توجيه رسالة", "قف على رسالة التدريب وافتح قائمة السياق، ثم اختر إعادة توجيه. تصفح المستلمين التجريبيين بالأسهم واختر أحدهم، ثم اضغط إعادة التوجيه. في النافذة التالية راجع حقل إلى والموضوع والمحتوى. يمكنك كتابة تعليق في حقل تعليق مع إعادة التوجيه، ثم اضغط تأكيد إعادة التوجيه التجريبي. لا يتم إرسال بريد حقيقي.", "forward", "تتعلم مشاركة الرسالة المختارة مع مستلم آخر وإضافة تعليق اختياري قبل محتواها."),
    ("فلترة عناصر الرسالة", "اختر الروابط فقط، ثم المرفقات فقط، ثم الصور فقط. لاحظ تغير قائمة العناصر مع كل اختيار. يجب تجربة الأنواع الثلاثة لإكمال المهمة.", "filter_types", "تتعلم الوصول إلى الروابط والمرفقات والصور باستخدام فلتر العناصر."),
    ("البحث بالاختصار", "اضغط Ctrl+F لإظهار حقل البحث المؤقت، ثم اكتب اجتماع واضغط Enter للبحث عن رسالة الفريق.\n\nيمكنك اختيار هذا النمط من إعدادات البرنامج ضمن طريقة البحث في الرسائل.", "search_shortcut", "تتدرب على نمط البحث المستدعى بالاختصار دون حقل دائم أو زر بحث ظاهر في البداية."),
    ("البحث بالزر مع الفلاتر", "اضغط زر البحث. اكتب اجتماع في نص البحث، ثم الفريق في فلتر اسم المرسل أو بريده، واختر منذ أسبوع من تاريخ الرسائل. اضغط ابحث للحصول على رسالة اجتماع الفريق المرسلة اليوم.\n\nيمكنك اختيار زر البحث مع الفلاتر من إعدادات البرنامج ضمن طريقة البحث في الرسائل.", "search_button", "تتدرب على فتح البحث بالزر وتطبيق فلتر المرسل والتاريخ قبل عرض النتائج."),
    ("البحث بالحقل الدائم", "انتقل إلى حقل نص البحث الظاهر بجوار قائمة الرسائل واكتب اجتماع. تتغير قائمة النتائج أثناء الكتابة دون الضغط على زر ابحث.\n\nيمكنك اختيار هذا النمط من إعدادات البرنامج ضمن طريقة البحث في الرسائل.", "search_field", "تتدرب على نمط حقل البحث الدائم الذي يفلتر الرسائل أثناء الكتابة."),
    ("الخروج من البحث", "النتائج تم فرزها مسبقاً. انتقل إلى حقل البحث واضغط Escape للخروج من أوضاع البحث والنتائج. لا تكتمل هذه المهمة بضغط Escape من قائمة النتائج أو أي عنصر آخر.", "search_exit", "تتعلم الخروج من البحث بضغط Escape داخل مربع البحث."),
    ("إعداد رسالة جديدة", "بعد الشرح تجد زر نسخ البريد التجريبي، ثم قائمة أوامر مطابقة لقائمة البرنامج. انسخ البريد، ثم انتقل بزر Tab إلى قائمة الأوامر. تصفحها بالأسهم حتى إنشاء بريد إلكتروني، ثم اضغط Enter أو Space.\nlearner@example.invalid\nالصق البريد في حقل إلى، ثم انتقل بزر Tab لكتابة الموضوع والمحتوى، واضغط مراجعة الرسالة.", "compose_review", "تتعلم فتح إنشاء رسالة من قائمة الأوامر وتعبئة الحقول المطلوبة قبل الإرسال."),
    ("التعامل مع ثلاث رسائل", "تصفح رسائل التدريب بالأسهم. على رسالة إعلان قديم افتح قائمة السياق بزر Application أو Shift+F10 واختر حذف، ثم أكد الحذف. افتح رسالة موعد الاجتماع بزر Enter، ومن قائمة سياق المستعرض اختر ترجمة، ثم الإنجليزية. اضغط Escape للعودة للقائمة. افتح رسالة ملاحظة مهمة، ومن قائمة سياق المستعرض اختر نسخ لنسخ نصها. يمكنك تنفيذ الإجراءات بأي ترتيب. الترجمة هنا نموذج محلي للتدريب، ولا تغير لغة الترجمة في إعداداتك.", "message_actions", "تطبق الحذف والترجمة إلى الإنجليزية ونسخ النص في مهمة واحدة بثلاث رسائل، باستخدام قائمة الرسائل ومستعرضها."),
)
EXERCISES += EXTENDED_LESSONS
ITEMS = (("links", "رابط تجريبي"), ("attachments", "مرفق تجريبي"), ("images", "صورة تجريبية"))
MAIL = ("اجتماع فريق العمل", "موعد الرحلة", "دعوة للقراءة")
FORWARD_RECIPIENTS = (
    ("learner@example.invalid", "أحمد — مستلم تجريبي"),
    ("sara@example.invalid", "سارة — مستلمة تجريبية"),
    ("maryam@example.invalid", "مريم — مستلمة تجريبية"),
)


def filtered_items(kind):
    return [label for category, label in ITEMS if kind == "all" or category == kind]


def search_mail(query):
    return [subject for subject in MAIL if query.strip().casefold() in subject.casefold()]


def valid_draft(address, subject, body):
    return address.strip().casefold() == "learner@example.invalid" and bool(subject.strip()) and bool(body.strip())


class PracticeExercises(wx.Panel):
    def __init__(self, parent, completed):
        super().__init__(parent)
        self.completed = completed
        self.action = ""
        self.generation = 0
        self.pending = False
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)

    def configure(self, action):
        self.generation += 1
        self.pending = False
        self.action = action
        self.DestroyChildren()
        self.root = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.root)
        if action.startswith("practice_"):
            self.extended = ExtendedPractice(self, action, self.finish)
            self.root.Add(self.extended, 1, wx.EXPAND)
        elif action == "forward":
            self.forward_messages = wx.ListBox(self, choices=[tr("رسالة تدريب: موعد الاجتماع")])
            self.forward_messages.SetSelection(0)
            set_accessible(self.forward_messages, "قائمة رسائل التدريب")
            self.add(self.forward_messages)
            self.forward_messages.Bind(wx.EVT_CONTEXT_MENU, self.on_forward_context)
        elif action == "message_actions":
            from .learning_message_actions import MessageActionsPractice
            self.message_actions = MessageActionsPractice(self, self.finish)
            self.root.Add(self.message_actions, 1, wx.EXPAND)
        elif action.startswith("filter_"):
            self.visited_filters = set()
            self.kinds = ("all", "links", "attachments", "images")
            self.filter = wx.Choice(self, choices=[tr(s) for s in ("كل العناصر", "الروابط فقط", "المرفقات فقط", "الصور فقط")])
            set_accessible(self.filter, "فلتر عناصر التدريب")
            self.add(self.filter)
            self.results = wx.ListBox(self)
            set_accessible(self.results, "نتائج فلترة العناصر")
            self.add(self.results)
            self.filter.MoveAfterInTabOrder(self.results)
            self.filter.SetSelection(1 if action == "filter_all" else 0)
            self.results.Set([tr(s) for s in filtered_items(self.kinds[self.filter.GetSelection()])])
            self.filter.Bind(wx.EVT_CHOICE, self.on_filter)
        elif action.startswith("search_"):
            self.search_revealed = action not in ("search_shortcut", "search_button")
            if action == "search_button":
                self.search_launcher = self.button("البحث", lambda event: self.reveal_search())
            previous = set(self.GetChildren())
            self.query = self.field("نص البحث", "اجتماع" if action == "search_exit" else "")
            if action == "search_button":
                self.sender_filter = self.field("اسم المرسل أو بريده:", "")
                self.add(wx.StaticText(self, label=tr("تاريخ الرسائل:")))
                self.date_filter = wx.Choice(self, choices=[tr(label) for label in DATE_FILTER_LABELS])
                self.date_filter.SetSelection(0)
                set_accessible(self.date_filter, "تاريخ الرسائل")
                self.add(self.date_filter)
            if action != "search_field":
                self.button("ابحث", self.on_search)
            self.search_controls = [child for child in self.GetChildren() if child not in previous]
            for control in self.search_controls:
                control.Show(self.search_revealed)
            if action == "search_field":
                self.query.Bind(wx.EVT_TEXT, self.on_search)
            self.results = wx.ListBox(self, choices=list(search_mail(self.query.GetValue())))
            set_accessible(self.results, "نتائج بحث التدريب")
            self.add(self.results)
        elif action.startswith("compose_"):
            ready = action != "compose_review"
            self.compose_open = ready
            self.copy_address_button = self.button("نسخ البريد التجريبي", self.on_copy_address)
            self.commands = wx.ListBox(self, choices=[tr(label) for label in COMMAND_LABELS],
                                       style=wx.LB_SINGLE, size=(-1, 150))
            self.commands.SetSelection(0)
            set_accessible(self.commands, "قائمة أوامر البرنامج", "استخدم الأسهم ثم Enter أو Space لتنفيذ الأمر المحدد")
            self.commands.Bind(wx.EVT_LISTBOX_DCLICK, self.on_commands)
            self.add(self.commands)
            self.commands.Show(not ready)
            previous = set(self.GetChildren())
            self.address = self.field("إلى:", "learner@example.invalid" if ready else "")
            self.subject = self.field("الموضوع:", tr("رسالة تدريب") if ready else "")
            self.body = self.field("المحتوى:", tr("هذا نص تجريبي.") if ready else "", multiline=True)
            label = {"compose_review": "مراجعة الرسالة", "compose_send": "إرسال تجريبي", "compose_cancel": "إلغاء الرسالة التجريبية"}[action]
            self.button(label, self.on_compose)
            self.sent = []
            self.compose_controls = [child for child in self.GetChildren() if child not in previous]
            for control in self.compose_controls:
                control.Show(ready)
        elif action.startswith("delete_"):
            self.in_trash = False
            self.results = wx.ListBox(self, choices=[tr("رسالة تجريبية في الوارد")])
            self.results.SetSelection(0)
            set_accessible(self.results, "رسالة الحذف التجريبية")
            self.add(self.results)
            self.button("حذف الرسالة التجريبية", self.on_delete)
        self.notice = wx.StaticText(self)
        self.add(self.notice)
        self.Layout()

    def add(self, control):
        self.root.Add(control, 0, wx.EXPAND | wx.ALL, 4)

    def field(self, label, value, multiline=False):
        self.add(wx.StaticText(self, label=tr(label)))
        control = wx.TextCtrl(self, value=value, style=wx.TE_MULTILINE if multiline else 0,
                              size=(-1, 65) if multiline else wx.DefaultSize)
        set_accessible(control, label)
        self.add(control)
        return control

    def button(self, label, handler):
        control = wx.Button(self, label=tr(label))
        control.Bind(wx.EVT_BUTTON, handler)
        self.add(control)
        return control

    def on_commands(self, _event):
        if self.commands.GetSelection() == COMPOSE_COMMAND_INDEX:
            self.open_compose(self.generation)
        else:
            wx.MessageBox(tr("المطلوب في هذه المهمة اختيار إنشاء بريد إلكتروني. بقية الأوامر لا تنفذ أي إجراء في هذا التدريب."),
                          tr("المرشد التفاعلي"), wx.OK, self)
            self.commands.SetFocus()

    def open_compose(self, generation):
        if not self or self.IsBeingDeleted() or not self.IsShownOnScreen() or generation != self.generation:
            return
        self.compose_open = True
        self.commands.Hide()
        for control in self.compose_controls:
            control.Show()
        self.Layout()
        self.GetParent().Layout()
        self.address.SetFocus()

    def on_copy_address(self, _event):
        copied = False
        if wx.TheClipboard.Open():
            try:
                copied = wx.TheClipboard.SetData(wx.TextDataObject("learner@example.invalid"))
            finally:
                wx.TheClipboard.Close()
        wx.MessageBox(tr("تم نسخ البريد التجريبي. الصقه في حقل إلى." if copied else "تعذر النسخ. يمكنك نسخ البريد من شرح المهمة."),
                      tr("المرشد التفاعلي"), wx.OK, self)
        (self.address if self.compose_open else self.copy_address_button).SetFocus()

    def finish(self):
        if self.pending:
            return
        self.pending = True
        wx.CallAfter(self.deliver, self.action, self.generation)

    def deliver(self, action, generation):
        if self and not self.IsBeingDeleted() and self.IsShownOnScreen() and generation == self.generation:
            self.completed(action)

    def on_filter(self, _event):
        kind = self.kinds[self.filter.GetSelection()]
        self.results.Set([tr(s) for s in filtered_items(kind)])
        if self.action == "filter_types":
            if getattr(self.GetParent(), "filter_stage", "list") != "elements":
                return
            self.visited_filters.add(kind)
            if {"links", "attachments", "images"} <= self.visited_filters:
                self.finish()
        elif self.action == "filter_" + kind:
            self.finish()

    def on_forward_context(self, _event=None):
        if self.pending or getattr(self, "forward_menu_open", False):
            return
        menu = wx.Menu()
        item = menu.Append(wx.ID_ANY, tr("إعادة توجيه"))
        selected = []
        menu.Bind(wx.EVT_MENU, lambda event: selected.append(True), item)
        self.forward_menu_open = True
        try:
            self.forward_messages.PopupMenu(menu)
        finally:
            menu.Destroy()
            self.forward_menu_open = False
        if selected:
            wx.CallAfter(self.forward_training, self.generation)

    def forward_training(self, generation):
        if not self or self.IsBeingDeleted() or not self.IsShownOnScreen() or generation != self.generation or self.pending:
            return
        from .address_book import AddressEntry
        from .address_book_dialog import ForwardMessageDialog
        from .models import MessageSummary
        message = MessageSummary(uid="training-forward", mailbox="INBOX", sender=tr("الفريق"),
                                 sender_email="team@example.invalid", subject=tr("موعد الاجتماع"))
        entries = [AddressEntry(email, name=tr(name)) for email, name in FORWARD_RECIPIENTS]
        dialog = ForwardMessageDialog(self, entries, [message], message)
        recipient = ""
        try:
            if dialog.ShowModal() == wx.ID_OK:
                recipient = dialog.recipient_email()
                if dialog.selected_message() is None:
                    recipient = ""
        finally:
            dialog.Destroy()
        if not recipient:
            self.forward_messages.SetFocus()
            return
        if recipient.strip().casefold() not in {email for email, _ in FORWARD_RECIPIENTS}:
            wx.MessageBox(tr("اختر أحد المستلمين التجريبيين من سجل العناوين لإكمال المهمة."), tr("المرشد التفاعلي"), wx.OK, self)
            self.forward_messages.SetFocus()
            return
        from .dialogs import ComposeDialog
        preview = ComposeDialog(self, title="إعادة توجيه تجريبي", to_address=recipient,
                                subject="Fwd: " + tr("موعد الاجتماع"), body=tr("سيبدأ الاجتماع غدا الساعة العاشرة."),
                                forward_comment=True, practice=True)
        try:
            confirmed = preview.ShowModal() == wx.ID_OK
            if confirmed:
                target, subject, body, _attachments = preview.values()
                confirmed = target.strip().casefold() in {email for email, _ in FORWARD_RECIPIENTS} and bool(subject.strip()) and bool(body.strip())
                if not confirmed:
                    wx.MessageBox(tr("راجع المستلم التجريبي والموضوع والمحتوى لإكمال المهمة."), tr("المرشد التفاعلي"), wx.OK, self)
        finally:
            preview.Destroy()
        if confirmed:
            self.finish()
        else:
            self.forward_messages.SetFocus()

    def on_search(self, _event):
        if not getattr(self, "search_revealed", True):
            return
        query = self.query.GetValue().strip()
        results = search_mail(query)
        if self.action == "search_button":
            sender = self.sender_filter.GetValue().strip()
            date = self.date_filter.GetSelection()
            # The matching training message is from the team and dated today.
            if (sender and sender not in "الفريق team@example.invalid") or date == 8:
                results = []
        self.results.Set(list(results))
        self.notice.SetLabel(tr("لا توجد نتائج") if not results else str(len(results)))
        if (self.action in ("search_match", "search_shortcut", "search_field") and query == "اجتماع" and len(results) == 1
                or self.action == "search_button" and query == "اجتماع" and sender in ("الفريق", "فريق") and date == 2 and len(results) == 1
                or self.action == "search_empty" and query and not results):
            self.finish()

    def reveal_search(self):
        if self.action not in ("search_shortcut", "search_button"):
            return
        self.search_revealed = True
        for control in self.search_controls:
            control.Show()
        if self.action == "search_button":
            self.search_launcher.Hide()
        self.Layout()
        self.GetParent().Layout()
        self.query.SetFocus()

    def handle_search_escape(self, focus):
        if focus is not self.query:
            wx.MessageBox(tr("يجب إكمال المهمة عبر ضغط Escape داخل مربع البحث."), tr("المرشد التفاعلي"), wx.OK, self)
            return
        self.query.ChangeValue("")
        self.results.Set(list(MAIL))
        self.finish()

    def on_compose(self, _event):
        if not self.compose_open:
            return
        if self.action == "compose_cancel":
            for control in (self.address, self.subject, self.body):
                control.ChangeValue("")
            self.finish()
        elif valid_draft(self.address.GetValue(), self.subject.GetValue(), self.body.GetValue()):
            if self.action == "compose_send":
                self.sent.append(self.subject.GetValue())
                self.notice.SetLabel(tr("ظهرت الرسالة في المرسل التجريبي."))
            self.finish()
        else:
            wx.MessageBox(tr("استخدم learner@example.invalid واكتب الموضوع والمحتوى."), tr("المرشد التفاعلي"), wx.OK, self)
            self.address.SetFocus()

    def on_delete(self, _event):
        dialog = wx.MessageDialog(self, tr("هل تريد نقل رسالة التدريب إلى السلة التجريبية؟"),
                                  tr("تأكيد الحذف التجريبي"), wx.OK | wx.CANCEL | wx.CANCEL_DEFAULT | wx.ICON_WARNING)
        dialog.SetOKCancelLabels(tr("نقل إلى السلة التجريبية"), tr("إلغاء"))
        try:
            result = dialog.ShowModal()
        finally:
            dialog.Destroy()
        self.in_trash = result == wx.ID_OK
        self.results.Set([tr("رسالة تجريبية في السلة" if self.in_trash else "رسالة تجريبية في الوارد")])
        if (self.action == "delete_confirm" and self.in_trash or self.action == "delete_cancel" and not self.in_trash):
            self.finish()
        else:
            self.notice.SetLabel(tr("راجع المطلوب في المهمة ثم حاول مرة أخرى."))

    def on_key(self, event):
        if (self.action == "forward" and wx.Window.FindFocus() is self.forward_messages
                and (event.GetKeyCode() == wx.WXK_MENU or event.GetKeyCode() == wx.WXK_F10 and event.ShiftDown())):
            self.on_forward_context()
        elif self.action == "search_exit" and event.GetKeyCode() == wx.WXK_ESCAPE:
            self.handle_search_escape(wx.Window.FindFocus())
        elif self.action.startswith("search_") and event.ControlDown() and event.GetKeyCode() in (ord("F"), ord("f"), ord("ب")):
            self.reveal_search()
        elif self.action.startswith("search_") and wx.Window.FindFocus() is self.query and event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.on_search(event)
        elif (self.action.startswith("compose_") and wx.Window.FindFocus() is self.commands
                and event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE)):
            self.on_commands(event)
        elif (event.GetKeyCode() == wx.WXK_ESCAPE and self.action.startswith("search_")
                and wx.Window.FindFocus() in (self.query, self.results)):
            self.query.ChangeValue("")
            self.results.Set(list(MAIL))
            if self.action == "search_exit":
                self.finish()
        else:
            event.Skip()
