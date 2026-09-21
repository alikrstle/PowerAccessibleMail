"""Local, modeless practice area; optional user-selected dummy attachment save.

No account, network or mailbox operations.
"""
from __future__ import annotations

import json
import os

import wx

from .accessibility import set_accessible
from .config import data_dir
from .i18n import tr
from .learning_exercises import EXERCISES, PracticeExercises


LESSONS = (
    ("فتح الرسالة وقراءتها", "انتقل بزر Tab إلى قائمة رسائل التدريب، ثم اضغط Enter لفتح الرسالة. اقرأ محتواها بالأسهم، ثم اضغط Ctrl+Enter للانتقال إلى عناصر الرسالة.", "open_elements"),
    ("التعامل مع عناصر الرسالة", "افتح الرسالة بزر Enter، ثم اضغط Ctrl+Enter لعرض عناصرها. قف على الرابط وافتح قائمة السياق بزر Application أو Shift+F10 واختر نسخ الرابط. وبعد ذلك، قف على المرفق وافتح قائمة السياق واختر حفظ المرفق وحدد مكان حفظ الملف التجريبي. تكتمل المهمة تلقائيا بعد نجاح النسخ والحفظ.", "return"),
    ("الرد من قائمة السياق", "انتقل إلى قائمة رسائل التدريب. اضغط زر التطبيقات أو Shift+F10 لفتح قائمة السياق، ثم اختر رد واضغط Enter.", "reply_open"),
    ("كتابة رد تجريبي", "راجع حقل إلى والموضوع المعبأين تلقائيا، ثم اكتب ردك في حقل المحتوى فوق النص المقتبس. تتوفر إضافة مرفق وقائمة المرفقات مثل نافذة الرد في البرنامج. اضغط إرسال تجريبي بعد المراجعة. لن يرسل التدريب رسالة حقيقية.", "reply_complete"),
    ("تغيير حالة القراءة", "توجد رسالتان: الأولى غير مقروءة والثانية مقروءة. علّم الأولى كمقروءة والثانية كغير مقروءة باستخدام Space أو قائمة السياق. يجب تنفيذ التغييرين لإكمال المهمة.", "read_pair"),
    ("إضافة النجمة وإزالتها", "من صندوق التصنيفات اختر كل التصنيفات. قف على الرسالة الأولى، وافتح قائمة السياق واختر تمييز بنجمة. بعد ذلك، انتقل إلى صندوق التصنيفات واختر الرسائل المميزة بنجمة. ستجد الرسالة الأولى ورسالة ثانية عليها نجمة مسبقا. افتح قائمة سياق الرسالة الثانية واختر إزالة النجمة.", "star_pair"),
    ("التثبيت وإلغاؤه", "توجد رسالتان: الأولى غير مثبتة والثانية مثبتة بالأعلى. ثبّت الأولى وألغ تثبيت الثانية من قائمة السياق. اتبع اسم الرسالة لأن ترتيبها قد يتغير.", "pin_pair"),
    ("الأرشفة وإلغاؤها", "اختر رسالة التدريب وافتح قائمة سياقها، ثم اختر أرشفة. من صندوق التصنيفات اختر الرسائل المؤرشفة. افتح قائمة سياق الرسالة واختر استعادة إلى الوارد. أخيرا، من صندوق التصنيفات اختر كل التصنيفات لتجد الرسالة مرة أخرى.", "archive_roundtrip"),
)
IDEAS = (
    "تتعلم اختيار رسالة وفتحها وقراءة محتواها والوصول إلى روابطها ومرفقاتها.",
    "تتعلم نسخ رابط وحفظ مرفق تجريبي من قوائم سياق العناصر والعودة إلى الرسائل.",
    "تتعلم فتح قائمة السياق واختيار إجراء الرد على الرسالة.",
    "تتعلم كتابة محتوى الرد ومراجعته دون إرسال رسالة حقيقية.",
    "تتعلم تحويل رسالة غير مقروءة إلى مقروءة، وإعادة رسالة مقروءة إلى غير مقروءة لمراجعتها لاحقا.",
    "نضع نجمة على الرسالة المهمة ليسهل العثور عليها لاحقا. يجمع تصنيف الرسائل المميزة بنجمة هذه الرسائل في مكان واحد، من دون حذفها أو إنشاء نسخة أخرى منها. وعندما نزيل النجمة تبقى الرسالة في بريدك، لكنها لا تعود ظاهرة في تصنيف الرسائل المميزة بنجمة.",
    "تتعلم إبقاء رسالة في أعلى القائمة بالتثبيت، وإلغاء تثبيت رسالة أخرى لإعادتها إلى ترتيبها المعتاد.",
    "الأرشفة تزيل الرسالة من الوارد دون حذفها أو نقلها إلى سلة المحذوفات. تستطيع قراءتها من الرسائل المؤرشفة وإعادتها إلى الوارد لاحقا. عكس خاصية الحذف فينقل الرسالة إلى سلة المحذوفات، وقد يحذفها مزود البريد نهائيا لاحقا حسب سياسته.",
)
INTRODUCTION = (
    "مرحبا بك في المرشد التفاعلي.\n"
    "يساعدك المرشد على تعلم البرنامج من خلال مهام قصيرة تنفذها بنفسك.\n"
    "تدريب آمن: لا نستخدم حسابك أو رسائلك الحقيقية.\n\n"
    "اقرأ شرح المهمة بالأسهم، ثم انتقل بزر Tab إلى عناصر التدريب ونفذ المطلوب. "
    "عند نجاحك تظهر بطاقة تهنئة، ثم يمكنك متابعة المهمة التالية.\n"
    "يمكنك إعادة الشرح أو تخطي مهمة. يُحفظ تقدمك لتستكمل من حيث توقفت.\n"
    "اضغط Alt+H لفتح المرشد أو إغلاقه. استخدم زر التدريب للبدء، أو لاستكمال تقدمك المحفوظ."
)
LESSONS += tuple((title, instruction, action) for title, instruction, action, _ in EXERCISES)
IDEAS += tuple(idea for _, _, _, idea in EXERCISES)


def task_description(step: int) -> str:
    if step >= len(LESSONS):
        return tr("وصلت إلى نهاية المهام. يمكنك اختيار مهمة لمراجعتها أو إغلاق المرشد، أو الضغط على زر إجراءات أكثر واختيار بدء التدريب من جديد.")
    title, instruction, _ = LESSONS[step]
    if LESSONS[step][2].startswith("filter_"):
        instruction = ("انتقل إلى قائمة رسائل التدريب وافتح الرسالة بضغط Enter. "
                       "من مستعرض الرسالة اضغط Ctrl+Enter لإظهار مستعرض العناصر، "
                       "ثم انتقل بزر Tab إلى فلتر العناصر. " + instruction)
    return ("\n" + tr("المهمة {0}: {1}").format(step + 1, tr(title)) + "\n\n"
            + tr("فكرة المهمة:") + " " + tr(IDEAS[step]) + "\n\n"
            + tr("المطلوب:") + " " + tr(instruction))


def completion_message(step: int) -> str:
    if step >= len(LESSONS):
        return tr("أحسنت، أكملت التدريب!")
    return tr(("أحسنت، نجحت بالمهمة!", "رائع، قد أنجزت المهمة!")[(step - 1) % 2])


class CompletionCard(wx.StaticText):
    def AcceptsFocus(self):
        return True

    def AcceptsFocusFromKeyboard(self):
        return True


def advance_step(step: int, action: str) -> int:
    if 0 <= step < len(LESSONS) and action == LESSONS[step][2]:
        return step + 1
    return step


MESSAGE_ACTIONS = {
    "read": ("read", True), "unread": ("read", False),
    "star": ("starred", True), "unstar": ("starred", False),
    "pin": ("pinned", True), "unpin": ("pinned", False),
    "archive": ("archived", True), "restore": ("archived", False),
}
PAIR_FIELDS = {"read_pair": "read", "star_pair": "starred", "pin_pair": "pinned"}


def pair_completed(states, action):
    field = PAIR_FIELDS.get(action)
    return bool(field and len(states) == 2 and states[0][field] and not states[1][field])


def initial_message_state(action: str) -> dict[str, bool]:
    return {"read": action == "unread", "starred": action == "unstar",
            "pinned": action == "unpin", "archived": action == "restore"}


def apply_message_action(state: dict[str, bool], action: str) -> bool:
    if action not in MESSAGE_ACTIONS:
        return False
    field, value = MESSAGE_ACTIONS[action]
    if state[field] == value:
        return False
    state[field] = value
    return True


class InteractiveLearning(wx.Dialog):
    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, title=tr("المرشد التفاعلي"), size=(760, 650),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.progress_path = data_dir() / "learning-progress.json"
        self.task_states = {}
        self.step = self.load_progress()
        self.in_intro = True
        self.card_timer = None
        outer = wx.BoxSizer(wx.VERTICAL)
        self.intro_panel = wx.Panel(self)
        intro_sizer = wx.BoxSizer(wx.VERTICAL)
        self.intro_text = wx.TextCtrl(self.intro_panel, value=tr(INTRODUCTION),
                                     style=wx.TE_MULTILINE | wx.TE_READONLY)
        set_accessible(self.intro_text, "مقدمة المرشد التفاعلي")
        intro_sizer.Add(self.intro_text, 1, wx.EXPAND | wx.ALL, 12)
        for label, handler in (("أبدأ التدريب مع المرشد التفاعلي", self.begin),
                               ("إغلاق المرشد التفاعلي", self.close)):
            button = wx.Button(self.intro_panel, label=tr(label))
            set_accessible(button, label)
            button.Bind(wx.EVT_BUTTON, handler)
            intro_sizer.Add(button, 0, wx.EXPAND | wx.ALL, 8)
            if handler == self.begin:
                self.begin_button = button
        self.intro_panel.SetSizer(intro_sizer)
        outer.Add(self.intro_panel, 1, wx.EXPAND)
        root = wx.BoxSizer(wx.VERTICAL)
        self.training_sizer = root
        self.completion_card = CompletionCard(self, label="")
        self.completion_card.SetFont(self.completion_card.GetFont().Bold())
        root.Add(self.completion_card, 0, wx.EXPAND | wx.ALL, 12)
        self.task_picker_label = wx.StaticText(
            self,
            label=tr("مستعرض المهام:"),
        )
        root.Add(self.task_picker_label, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 12)
        self.task_picker = wx.Choice(self)
        set_accessible(
            self.task_picker,
            "مستعرض مهام التدريب",
            "اختر مهمة بالأسهم، ثم اضغط Tab لقراءة شرح المهمة المختارة.",
        )
        self.task_picker.Bind(wx.EVT_CHOICE, self.choose_task)
        root.Add(self.task_picker, 0, wx.EXPAND | wx.ALL, 4)
        self.instructions_label = wx.StaticText(
            self,
            label=tr("شرح المهمة المختارة:"),
        )
        root.Add(self.instructions_label, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 12)
        self.instructions = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY,
                                        size=(-1, 130))
        set_accessible(self.instructions, "شرح مهمة التدريب")
        root.Add(self.instructions, 0, wx.EXPAND | wx.ALL, 12)
        self.practice_mailbox = wx.Choice(self, choices=[tr("كل التصنيفات"), tr("الرسائل المؤرشفة"), tr("الرسائل المميزة بنجمة")])
        self.practice_mailbox.SetSelection(0)
        set_accessible(self.practice_mailbox, "قسم التدريب")
        self.practice_mailbox.Bind(wx.EVT_CHOICE, self.update_practice_messages)
        root.Add(self.practice_mailbox, 0, wx.EXPAND | wx.ALL, 8)
        self.messages = wx.ListBox(self, choices=[tr("رسالة تدريب: مرحبا بك")])
        self.messages.SetSelection(0)
        self.messages.Bind(wx.EVT_CONTEXT_MENU, self.on_training_context)
        self.messages.Bind(wx.EVT_LISTBOX, self.select_practice_message)
        set_accessible(self.messages, "قائمة رسائل التدريب")
        root.Add(self.messages, 0, wx.EXPAND | wx.ALL, 8)
        self.body = wx.TextCtrl(self, value=tr(
            "هذه رسالة تدريب وهمية.\nيمكنك قراءة فقراتها دون تغيير بريدك الحقيقي.\n"
            "تحتوي على رابط ومرفق تجريبيين، ولا يتم فتحهما أو تنزيلهما."),
            style=wx.TE_MULTILINE | wx.TE_READONLY)
        set_accessible(self.body, "مستعرض رسالة التدريب")
        root.Add(self.body, 1, wx.EXPAND | wx.ALL, 8)
        self.elements = wx.ListBox(self, choices=[tr("رابط تجريبي"), tr("مرفق تجريبي")])
        self.elements.SetSelection(0)
        self.elements.Bind(wx.EVT_CONTEXT_MENU, self.on_element_context)
        self.elements.SetSelection(0)
        set_accessible(self.elements, "عناصر رسالة التدريب")
        root.Add(self.elements, 0, wx.EXPAND | wx.ALL, 8)
        self.reply_panel = wx.Panel(self)
        reply_sizer = wx.BoxSizer(wx.VERTICAL)
        def reply_field(label, value):
            reply_sizer.Add(wx.StaticText(self.reply_panel, label=tr(label)), 0, wx.ALL, 4)
            control = wx.TextCtrl(self.reply_panel, value=value)
            set_accessible(control, label)
            reply_sizer.Add(control, 0, wx.EXPAND | wx.ALL, 4)
            return control
        self.reply_to = reply_field("إلى:", "sender@example.invalid")
        self.reply_subject = reply_field("الموضوع:", "Re: " + tr("رسالة تدريب"))
        reply_sizer.Add(wx.StaticText(self.reply_panel, label=tr("المحتوى:")), 0, wx.ALL, 4)
        self.reply_text = wx.TextCtrl(self.reply_panel, style=wx.TE_MULTILINE, size=(-1, 90))
        set_accessible(self.reply_text, "محتوى الرسالة")
        reply_sizer.Add(self.reply_text, 1, wx.EXPAND | wx.ALL, 4)
        add_attachment = wx.Button(self.reply_panel, label=tr("إضافة مرفق"))
        add_attachment.Bind(wx.EVT_BUTTON, self.add_reply_attachment)
        reply_sizer.Add(add_attachment, 0, wx.ALL, 4)
        self.reply_attachments = wx.ListBox(self.reply_panel, size=(-1, 55))
        set_accessible(self.reply_attachments, "قائمة المرفقات المضافة")
        reply_sizer.Add(self.reply_attachments, 0, wx.EXPAND | wx.ALL, 4)
        finish_reply = wx.Button(self.reply_panel, label=tr("إرسال تجريبي"))
        finish_reply.Bind(wx.EVT_BUTTON, self.finish_reply_training)
        reply_sizer.Add(finish_reply, 0, wx.ALL, 4)
        cancel_reply = wx.Button(self.reply_panel, label=tr("إلغاء"))
        cancel_reply.Bind(wx.EVT_BUTTON, lambda event: self.reply_text.ChangeValue(""))
        reply_sizer.Add(cancel_reply, 0, wx.ALL, 4)
        self.reply_panel.SetSizer(reply_sizer)
        root.Add(self.reply_panel, 1, wx.EXPAND | wx.ALL, 8)
        self.extra_practice = PracticeExercises(self, self.record)
        root.Add(self.extra_practice, 1, wx.EXPAND | wx.ALL, 8)
        self.status = wx.StaticText(self)
        root.Add(self.status, 0, wx.EXPAND | wx.ALL, 8)
        self.previous_button = wx.Button(self, label=tr("المهمة السابقة"))
        self.previous_button.Bind(wx.EVT_BUTTON, self.previous)
        root.Add(self.previous_button, 0, wx.ALL, 4)
        self.more_button = wx.Button(self, label=tr("إجراءات أكثر"))
        self.more_button.Bind(wx.EVT_BUTTON, self.more_actions)
        root.Add(self.more_button, 0, wx.ALL, 4)
        self.save_close_button = wx.Button(self, label=tr("حفظ وإغلاق"))
        self.save_close_button.Bind(wx.EVT_BUTTON, self.close)
        root.Add(self.save_close_button, 0, wx.ALL, 4)
        outer.Add(root, 1, wx.EXPAND)
        self.SetSizer(outer)
        outer.Hide(root, recursive=True)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_CLOSE, self.close)
        self.refresh()

    def begin(self, _event=None) -> None:
        self.in_intro = False
        self.intro_panel.Hide()
        self.GetSizer().Show(self.training_sizer, recursive=True)
        self.completion_card.Hide()
        self.refresh()
        self.Layout()
        self.explain()

    def load_progress(self) -> int:
        try:
            value = json.loads(self.progress_path.read_text(encoding="utf-8"))
            version = value.get("version")
            if version == 2:
                ids = [lesson[2] for lesson in LESSONS]
                states = value.get("states", {})
                self.task_states = {key: state for key, state in states.items()
                                    if key in ids and state in ("completed", "skipped")} if isinstance(states, dict) else {}
                current = value.get("current")
                if isinstance(states, dict) and states.get(
                    "practice_compose_address_book"
                ) in {"completed", "skipped"}:
                    # The former combined task covered both of the new tasks.
                    old_state = states["practice_compose_address_book"]
                    self.task_states["practice_compose_address_add"] = old_state
                    self.task_states["practice_compose_address_pick"] = old_state
                if current == "practice_compose_address_book":
                    current = "practice_compose_address_add"
                if isinstance(states, dict) and states.get("practice_contacts") in {
                    "completed",
                    "skipped",
                }:
                    # The former contact task already included editing and use.
                    self.task_states["practice_contacts_edit_use"] = states[
                        "practice_contacts"
                    ]
                if (
                    current == "practice_attachments"
                    and "practice_viewers" not in self.task_states
                ):
                    # Viewer training now precedes attachments as task 21.
                    current = "practice_viewers"
                if current == "filter_all":
                    current = "search_shortcut"
                elif current == "search_empty":
                    current = "search_exit"
                elif current in ("compose_send", "compose_cancel", "delete_cancel", "delete_confirm"):
                    current = "message_actions"
                elif current in ("open", "elements"):
                    current = "open_elements"
                elif current in ("archive", "restore"):
                    current = "archive_roundtrip"
                elif current in ("filter_images", "search_match"):
                    current = "search_shortcut"
                elif current in ("filter_links", "filter_attachments"):
                    current = "filter_types"
                merges = {"read_pair": ("read", "unread"), "star_pair": ("star", "unstar"), "pin_pair": ("pin", "unpin"),
                          "open_elements": ("open", "elements"), "archive_roundtrip": ("archive", "restore")}
                for combined, old_ids in merges.items():
                    if current in old_ids:
                        current = combined
                    if isinstance(states, dict) and all(states.get(old) == "completed" for old in old_ids):
                        self.task_states[combined] = "completed"
                if current == "end" and isinstance(states, dict) and states:
                    return next((i for i, lesson_id in enumerate(ids) if lesson_id not in self.task_states), len(LESSONS))
                return ids.index(current) if current in ids else len(LESSONS) if current == "end" else 0
            # Old files contain only the position: do not assume earlier tasks
            # were completed, since they may have been skipped.
            step = value.get("step", 0) if version == 1 else 0
            return step if type(step) is int and 0 <= step <= len(LESSONS) else 0
        except (OSError, ValueError, AttributeError):
            return 0

    def save_progress(self) -> bool:
        temporary = self.progress_path.with_suffix(".tmp")
        try:
            current = LESSONS[self.step][2] if self.step < len(LESSONS) else "end"
            temporary.write_text(json.dumps({"version": 2, "current": current,
                "states": getattr(self, "task_states", {})}), encoding="utf-8")
            os.replace(temporary, self.progress_path)
            return True
        except OSError:
            self.status.SetLabel(tr("تعذر حفظ تقدم التدريب. يمكنك متابعة التدريب الآن."))
            return False

    def refresh(self) -> None:
        label = "أكمل التدريب مع المرشد التفاعلي" if self.step > 0 or self.task_states else "أبدأ التدريب مع المرشد التفاعلي"
        self.begin_button.SetLabel(tr(label))
        set_accessible(self.begin_button, label)
        self._completion_pending = False
        if self.card_timer:
            self.card_timer.Stop()
        self.completion_card.Hide()
        self.completion_card.SetLabel("")
        self.completion_card.SetName("")
        labels = {"completed": "منجزة", "skipped": "متخطاة"}
        task_labels = [
            f"{index + 1}. {tr(lesson[0])} — {tr(labels.get(self.task_states.get(lesson[2]), 'لم تنجز بعد'))}"
            for index, lesson in enumerate(LESSONS)
        ]
        if list(self.task_picker.GetStrings()) != task_labels:
            self.task_picker.SetItems(task_labels)
        self.task_picker.SetSelection(self.step if self.step < len(LESSONS) else wx.NOT_FOUND)
        text = task_description(self.step)
        self.instructions.ChangeValue(text)
        self.instructions.SetInsertionPoint(0)
        action = LESSONS[self.step][2] if self.step < len(LESSONS) else ""
        self._account_focus_pending = action == "practice_sections"
        active = bool(action) and not self.in_intro
        self.status.SetLabel("")
        self.status.Show(active)
        self.filter_training = action.startswith("filter_")
        self.filter_stage = "list"
        self.opened_training_message = False
        self.element_actions = set()
        self.archive_actions = set()
        self.starred_view_visited = False
        extra = any(action == exercise[2] for exercise in EXERCISES)
        self.extra_practice.configure(action if extra else "")
        self.extra_practice.Show(extra and not self.filter_training and active)
        self.messages.Show((not extra or self.filter_training) and active)
        self.practice_mailbox.Show(not extra and active)
        self.practice_message = initial_message_state(action)
        self.practice_messages = [self.practice_message]
        if action in PAIR_FIELDS:
            second = initial_message_state(action)
            second[PAIR_FIELDS[action]] = True
            if action == "star_pair":
                second["starred_only"] = True
            self.practice_messages.append(second)
        self.selected_practice_id = 0
        self.practice_mailbox.SetSelection(0)
        self.update_practice_messages()
        replying = action == "reply_complete" and not self.in_intro
        self.reply_panel.Show(replying)
        if not replying:
            self.reply_text.ChangeValue("")
        else:
            self.reply_to.ChangeValue("sender@example.invalid")
            self.reply_subject.ChangeValue("Re: " + tr("رسالة تدريب"))
            self.reply_quote = "\n\n----- " + tr("الرسالة الأصلية") + " -----\n" + tr("مرحبا، هل يمكنك تأكيد موعد الاجتماع؟")
            self.reply_text.ChangeValue(self.reply_quote)
            self.reply_text.SetInsertionPoint(0)
            self.reply_attachments.Clear()
        # Keep a compact layout while writing the practice reply.
        self.body.Show(active and not replying and not extra)
        self.elements.Show(active and not replying and not extra)
        self.Layout()
        self.Refresh()

    def explain(self, _event=None) -> None:
        if getattr(self, "_completion_pending", False):
            self.refresh()
        if self.in_intro:
            self.intro_text.SetInsertionPoint(0)
            self.intro_text.SetFocus()
            return
        self.instructions.SetInsertionPoint(0)
        if getattr(self, "_account_focus_pending", False):
            self._account_focus_pending = False
            self.extra_practice.extended.account.SetFocus()
            return
        self.instructions.SetFocus()

    def record(self, action: str) -> None:
        if getattr(self, "_completion_pending", False):
            return
        if action.startswith("filter_") and getattr(self, "filter_stage", "list") != "elements":
            return
        next_step = advance_step(self.step, action)
        if next_step != self.step:
            if not hasattr(self, "task_states"):
                self.task_states = {}
            self.task_states[LESSONS[self.step][2]] = "completed"
            self.step = next_step
            self._completion_pending = True
            self.save_progress()
            self.show_completion()

    def show_completion(self) -> None:
        self.status.SetLabel("")
        self.status.Hide()
        if self.card_timer:
            self.card_timer.Stop()
        text = (completion_message(self.step) if all(self.task_states.get(lesson[2]) == "completed" for lesson in LESSONS)
                else tr("أحسنت، نجحت بالمهمة!"))
        self.completion_card.SetLabel(text)
        set_accessible(self.completion_card, text)
        self.completion_card.Show()
        self.Layout()
        self.completion_card.SetFocus()
        self.card_timer = wx.CallLater(4000, self.hide_completion)

    def hide_completion(self) -> None:
        if not self or self.IsBeingDeleted():
            return
        had_focus = wx.Window.FindFocus() is self.completion_card
        if self.card_timer:
            self.card_timer.Stop()
        self.refresh()
        if had_focus and self.IsShown():
            self.explain()

    def more_actions(self, _event=None) -> None:
        menu = wx.Menu()
        selected = None
        def choose(handler):
            nonlocal selected
            selected = handler
        for label, handler in (("بدء التدريب من جديد", self.restart),
                               ("تخطي المهمة", self.skip), ("إعادة الشرح", self.explain)):
            item = menu.Append(wx.ID_ANY, tr(label))
            menu.Bind(wx.EVT_MENU, lambda event, handler=handler: choose(handler), item)
        try:
            self.more_button.PopupMenu(menu)
        finally:
            menu.Destroy()
        if selected:
            wx.CallAfter(selected)

    def skip(self, _event=None) -> None:
        if not hasattr(self, "task_states"):
            self.task_states = {}
        if self.step < len(LESSONS):
            self.task_states.setdefault(LESSONS[self.step][2], "skipped")
        self.step = min(self.step + 1, len(LESSONS))
        self.refresh()
        self.save_progress()
        self.explain()

    def restart(self, _event=None) -> None:
        self.task_states = {}
        self.step = 0
        self.refresh()
        self.save_progress()
        self.explain()

    def choose_task(self, _event=None) -> None:
        selection = self.task_picker.GetSelection()
        if 0 <= selection < len(LESSONS):
            # Arrow navigation must not move focus out of the task picker.
            self.step = selection
            self.refresh()
            self.save_progress()
            self.task_picker.SetFocus()

    def previous(self, _event=None) -> None:
        self.go_to_task(max(0, self.step - 1))

    def go_to_task(self, step: int) -> None:
        if self.card_timer:
            self.card_timer.Stop()
        self.completion_card.Hide()
        self.step = step
        self.refresh()
        self.save_progress()
        self.explain()

    def on_training_context(self, _event=None) -> None:
        if self.in_intro or getattr(self, "_training_menu_open", False):
            return
        menu = wx.Menu()
        if self.messages.GetSelection() == wx.NOT_FOUND:
            menu.Destroy()
            return
        requested = None

        def choose_action(_event, action):
            nonlocal requested
            requested = action

        state = self.practice_message
        actions = [
            ("رد", "reply_open"),
            ("تعليم كغير مقروءة" if state["read"] else "تعليم كمقروءة", "unread" if state["read"] else "read"),
            ("إزالة النجمة" if state["starred"] else "تمييز بنجمة", "unstar" if state["starred"] else "star"),
            ("إلغاء التثبيت" if state["pinned"] else "تثبيت بالأعلى", "unpin" if state["pinned"] else "pin"),
            ("استعادة إلى الوارد" if state["archived"] else "أرشفة", "restore" if state["archived"] else "archive"),
        ]
        for label, action in actions:
            item = menu.Append(wx.ID_ANY, tr(label))
            menu.Bind(wx.EVT_MENU, lambda event, action=action: choose_action(event, action), item)
        self._training_menu_open = True
        try:
            self.messages.PopupMenu(menu)
        finally:
            menu.Destroy()
            self._training_menu_open = False
        # Wait until the native menu has closed before moving focus.
        if requested:
            wx.CallAfter(self.finish_context_action, requested, self.step)

    def update_practice_messages(self, _event=None) -> None:
        view = self.practice_mailbox.GetSelection()
        archived_view = view == 1
        if view == 2:
            self.starred_view_visited = True
        self.visible_practice_ids = sorted(
            [i for i, state in enumerate(self.practice_messages)
             if (state["starred"] if view == 2 else state["archived"] == archived_view and not state.get("starred_only", False))],
            key=lambda i: (not self.practice_messages[i]["pinned"], i))
        rows = []
        for i in self.visible_practice_ids:
            state = self.practice_messages[i]
            labels = [tr("الرسالة الأولى" if i == 0 else "الرسالة الثانية"), tr("مقروءة" if state["read"] else "غير مقروءة")]
            if state["starred"]:
                labels.append(tr("مميزة بنجمة"))
            if state["pinned"]:
                labels.append(tr("مثبتة بالأعلى"))
            rows.append("؛ ".join(labels))
        self.messages.Set(rows)
        if rows:
            chosen = self.selected_practice_id if self.selected_practice_id in self.visible_practice_ids else self.visible_practice_ids[0]
            self.messages.SetSelection(self.visible_practice_ids.index(chosen))
            self.select_practice_message()
        if _event is not None and self.step < len(LESSONS):
            expected = LESSONS[self.step][2]
            if expected == "star_pair" and view == 2 and pair_completed(self.practice_messages, expected):
                self.record(expected)
            elif expected == "archive_roundtrip" and view == 0 and self.archive_actions == {"archive", "restore"}:
                self.record(expected)

    def select_practice_message(self, _event=None):
        index = self.messages.GetSelection()
        if 0 <= index < len(self.visible_practice_ids):
            self.selected_practice_id = self.visible_practice_ids[index]
            self.practice_message = self.practice_messages[self.selected_practice_id]

    def finish_context_action(self, action: str, step: int) -> None:
        if not self or self.IsBeingDeleted() or not self.IsShown() or self.step != step:
            return
        if getattr(self, "_completion_pending", False):
            return
        expected = LESSONS[self.step][2]
        if expected == "star_pair" and action == "unstar" and self.practice_mailbox.GetSelection() != 2:
            wx.MessageBox(tr("انتقل إلى الرسائل المميزة بنجمة، ثم أزل نجمة الرسالة الثانية."), tr("المرشد التفاعلي"), wx.OK, self)
            return
        if action == "reply_open":
            if expected == "reply_open":
                self.record(action)
                self.hide_completion()
                self.reply_to.SetFocus()
            elif expected == "reply_complete":
                self.reply_to.SetFocus()
        elif apply_message_action(self.practice_message, action):
            if action == "unstar":
                self.practice_message.pop("starred_only", None)
            self.update_practice_messages()
            expected = LESSONS[self.step][2]
            if expected in PAIR_FIELDS:
                if pair_completed(self.practice_messages, expected) and (expected != "star_pair" or self.starred_view_visited):
                    self.record(expected)
                else:
                    self.status.SetLabel(tr("أكمل التغيير المطلوب على الرسالتين لإتمام المهمة."))
            elif expected == "archive_roundtrip":
                if action in ("archive", "restore"):
                    self.archive_actions.add(action)
                self.status.SetLabel(tr("بعد الاستعادة اختر كل التصنيفات لإكمال المهمة."))
            else:
                self.record(action)

    def finish_reply_training(self, _event=None) -> None:
        if self.step >= len(LESSONS) or LESSONS[self.step][2] != "reply_complete":
            return
        text = self.reply_text.GetValue().replace(getattr(self, "reply_quote", ""), "").strip()
        if not text:
            wx.MessageBox(tr("اكتب ردا تجريبيا أولا."), tr("المرشد التفاعلي"),
                          wx.OK | wx.ICON_INFORMATION, self)
            self.reply_text.SetFocus()
            return
        if not self.reply_to.GetValue().strip() or not self.reply_subject.GetValue().strip():
            wx.MessageBox(tr("راجع المستلم والموضوع قبل إرسال الرد التجريبي."), tr("المرشد التفاعلي"), wx.OK, self)
            return
        self.record("reply_complete")

    def add_reply_attachment(self, _event=None):
        dialog = wx.FileDialog(self, tr("إضافة مرفق"), style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE)
        try:
            if dialog.ShowModal() == wx.ID_OK:
                self.reply_attachments.AppendItems(dialog.GetPaths())
        finally:
            dialog.Destroy()

    def on_element_context(self, _event=None):
        if getattr(self, "_element_menu_open", False):
            return
        index = self.elements.GetSelection()
        if index not in (0, 1):
            return
        menu = wx.Menu()
        item = menu.Append(wx.ID_ANY, tr("نسخ الرابط" if index == 0 else "حفظ المرفق"))
        selected = []
        menu.Bind(wx.EVT_MENU, lambda event: selected.append(True), item)
        self._element_menu_open = True
        try:
            self.elements.PopupMenu(menu)
        finally:
            menu.Destroy()
            self._element_menu_open = False
        if selected:
            wx.CallAfter(self.apply_element_action, index, self.step)

    def apply_element_action(self, index, step):
        if not self or self.IsBeingDeleted() or not self.IsShown() or self.step != step or self._completion_pending:
            return
        if index == 0:
            copied = False
            if wx.TheClipboard.Open():
                try:
                    copied = wx.TheClipboard.SetData(wx.TextDataObject("https://example.invalid/training"))
                finally:
                    wx.TheClipboard.Close()
            if copied:
                self.element_actions.add("copy")
            else:
                wx.MessageBox(tr("تعذر نسخ الرابط. حاول مرة أخرى."), tr("المرشد التفاعلي"), wx.OK, self)
        else:
            dialog = wx.FileDialog(self, tr("حفظ المرفق التجريبي"), defaultFile="training-attachment.txt", wildcard=tr("ملف نصي (*.txt)|*.txt"),
                                   style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
            self._child_dialog_open = True
            try:
                if dialog.ShowModal() == wx.ID_OK:
                    from pathlib import Path
                    try:
                        Path(dialog.GetPath()).write_text("Power Accessible Mail training attachment.\n", encoding="utf-8")
                        self.element_actions.add("save")
                        wx.MessageBox(tr("تم حفظ المرفق التجريبي."), tr("المرشد التفاعلي"), wx.OK, self)
                    except OSError as error:
                        wx.MessageBox(tr("تعذر حفظ المرفق. اختر مكانا آخر.") + "\n" + str(error), tr("المرشد التفاعلي"), wx.OK, self)
            finally:
                dialog.Destroy()
                self._child_dialog_open = False
        self.elements.SetFocus()
        if self.step == step and LESSONS[step][2] == "return" and self.element_actions == {"copy", "save"}:
            self.messages.SetFocus()
            self.record("return")

    def on_key(self, event: wx.KeyEvent) -> None:
        key, focus = event.GetKeyCode(), wx.Window.FindFocus()
        if getattr(self, "_child_dialog_open", False) or (isinstance(focus, wx.Window) and wx.GetTopLevelParent(focus) is not self):
            event.Skip()
            return
        action = LESSONS[self.step][2] if self.step < len(LESSONS) else ""
        if action == "search_exit" and key == wx.WXK_ESCAPE:
            self.extra_practice.handle_search_escape(focus)
            return
        if action.startswith("search_") and event.ControlDown() and key in (ord("F"), ord("f"), ord("ب")):
            self.extra_practice.reveal_search()
            return
        if focus is self.completion_card and key in (wx.WXK_DOWN, wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.hide_completion()
        elif key == wx.WXK_SPACE and focus is self.messages and self.messages.GetSelection() != wx.NOT_FOUND:
            self.finish_context_action("unread" if self.practice_message["read"] else "read", self.step)
        elif key in (ord("H"), ord("h")) and event.AltDown() and not event.ControlDown() and not event.ShiftDown():
            self.close()
        elif key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and focus is self.messages and self.messages.GetSelection() != wx.NOT_FOUND:
            self.opened_training_message = True
            if getattr(self, "filter_training", False):
                self.filter_stage = "viewer"
                self.body.Show()
                self.Layout()
            self.body.SetFocus()
        elif key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and event.ControlDown() and focus is self.body:
            if getattr(self, "filter_training", False):
                self.filter_stage = "elements"
                self.extra_practice.Show()
                self.Layout()
                self.extra_practice.results.SetFocus()
            else:
                self.elements.SetFocus()
            if self.opened_training_message:
                self.record("open_elements")
        elif focus is self.elements and (key == wx.WXK_MENU or key == wx.WXK_F10 and event.ShiftDown()):
            self.on_element_context()
        elif key == wx.WXK_ESCAPE and focus in (self.body, self.elements):
            if getattr(self, "filter_training", False):
                self.extra_practice.Hide()
                self.body.Hide()
                self.filter_stage = "list"
                self.Layout()
            self.messages.SetFocus()
            if action != "return" or self.element_actions == {"copy", "save"}:
                self.record("return")
            else:
                wx.MessageBox(tr("أكمل نسخ الرابط وحفظ المرفق لإتمام المهمة."), tr("المرشد التفاعلي"), wx.OK, self)
        elif (key == wx.WXK_ESCAPE and getattr(self, "filter_training", False)
              and focus in (self.extra_practice.filter, self.extra_practice.results)):
            self.extra_practice.Hide()
            self.body.Hide()
            self.filter_stage = "list"
            self.Layout()
            self.messages.SetFocus()
        elif key == wx.WXK_ESCAPE:
            self.close()
        else:
            event.Skip()

    def close(self, _event=None) -> None:
        if not self.save_progress():
            wx.MessageBox(
                tr("تعذر حفظ تقدم التدريب. حاول الإغلاق مرة أخرى بعد معالجة مشكلة الحفظ."),
                tr("المرشد التفاعلي"), wx.OK | wx.ICON_WARNING, self,
            )
            return
        if getattr(self, "_completion_pending", False):
            self.refresh()
        if self.card_timer:
            self.card_timer.Stop()
        self.reply_text.ChangeValue("")
        self.completion_card.Hide()
        self.completion_card.SetLabel("")
        self.completion_card.SetName("")
        self.Hide()
