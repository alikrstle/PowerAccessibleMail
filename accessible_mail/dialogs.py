from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import wx

from .accessibility import announce_context_menu, announce_to_screen_reader, set_accessible
from .address_book import add_address, load_address_book
from .address_book_dialog import AddressPickerDialog
from .config import ProgramSettings, THEME_DARK, THEME_LIGHT
from .i18n import tr
from .notification_preferences import (
    EVENT_ADDRESS_BOOK,
    EVENT_COMPOSE_ATTACHMENTS,
    EVENTS_BY_ID,
    SPOKEN_NOTIFICATION_GROUPS,
    normalize_event_ids,
    preset_event_ids,
)
from .ui_constants import (
    LANGUAGE_CHOICES,
    MESSAGE_READ_MODE_CHOICES,
    SPOKEN_NOTIFICATION_LEVEL_CHOICES,
    THEME_CHOICES,
    TRANSLATION_MODE_CHOICES,
    VIEWER_CHOICES,
)
from .ui_helpers import apply_layout_direction, localize_window
from .update_checker import UpdateCheckResult


class ComposeDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        title: str = "إنشاء بريد إلكتروني",
        to_address: str = "",
        subject: str = "",
        body: str = "",
    ) -> None:
        super().__init__(parent, title=title, size=(720, 680))
        self.attachment_paths: list[Path] = []
        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.VERTICAL)

        self.to_address = self._recipient_row(panel, root, to_address)
        self.subject = self._row(panel, root, "الموضوع:", subject)

        root.Add(wx.StaticText(panel, label="المحتوى:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.body = wx.TextCtrl(panel, value=body, style=wx.TE_MULTILINE)
        set_accessible(self.body, "محتوى الرسالة", "اكتب محتوى البريد الإلكتروني هنا")
        root.Add(self.body, 1, wx.EXPAND | wx.ALL, 8)

        self.add_attachment_button = wx.Button(panel, label="إضافة مرفق")
        set_accessible(
            self.add_attachment_button,
            "إضافة مرفق إلى الرسالة",
            "يفتح نافذة اختيار الملفات ويمكن تحديد أكثر من ملف.",
        )
        self.add_attachment_button.Bind(wx.EVT_BUTTON, self.on_add_attachments)
        root.Add(
            self.add_attachment_button,
            0,
            wx.ALIGN_LEFT | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            8,
        )

        root.Add(
            wx.StaticText(panel, label="المرفقات المضافة:"),
            0,
            wx.LEFT | wx.RIGHT | wx.TOP,
            8,
        )
        self.attachment_list = wx.ListBox(panel, size=(-1, 110))
        set_accessible(
            self.attachment_list,
            "قائمة المرفقات المضافة",
            (
                "تعرض الملفات التي ستُرسل مع الرسالة. اضغط Delete لإزالة "
                "المرفق المحدد أو زر التطبيقات لفتح قائمة السياق."
            ),
        )
        self.attachment_list.Bind(wx.EVT_CHAR_HOOK, self.on_attachment_key)
        self.attachment_list.Bind(
            wx.EVT_CONTEXT_MENU,
            self.on_attachment_context_menu,
        )
        root.Add(
            self.attachment_list,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            8,
        )

        send_button = wx.Button(panel, id=wx.ID_OK, label="إرسال")
        cancel_button = wx.Button(panel, id=wx.ID_CANCEL, label="إلغاء")
        set_accessible(send_button, "إرسال الرسالة")
        set_accessible(cancel_button, "إلغاء")
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.AddStretchSpacer(1)
        buttons.Add(send_button, 0, wx.ALL, 6)
        buttons.Add(cancel_button, 0, wx.ALL, 6)
        root.Add(buttons, 0, wx.EXPAND)

        panel.SetSizer(root)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(outer)
        localize_window(self)

    def _recipient_row(
        self,
        parent: wx.Window,
        root: wx.BoxSizer,
        value: str,
    ) -> wx.TextCtrl:
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(parent, label="إلى:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 8)
        control = wx.TextCtrl(parent, value=value)
        set_accessible(
            control,
            "إلى",
            "اكتب عنوان المستلم أو اضغط السهم للأسفل لاختيار عنوان من سجل العناوين.",
        )
        control.Bind(wx.EVT_KEY_DOWN, self.on_to_address_key)
        row.Add(control, 1, wx.EXPAND | wx.ALL, 8)
        self.add_address_button = wx.Button(
            parent,
            label="إضافة البريد الإلكتروني إلى سجل العناوين",
        )
        set_accessible(
            self.add_address_button,
            "إضافة البريد الإلكتروني إلى سجل العناوين",
            "يحفظ عنوان المستلم المكتوب في سجل العناوين.",
        )
        self.add_address_button.Bind(wx.EVT_BUTTON, self.on_add_address)
        row.Add(self.add_address_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 8)
        root.Add(row, 0, wx.EXPAND)
        return control

    def _row(
        self,
        parent: wx.Window,
        root: wx.BoxSizer,
        label: str,
        value: str,
    ) -> wx.TextCtrl:
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 8)
        control = wx.TextCtrl(parent, value=value)
        set_accessible(control, label.replace(":", ""))
        row.Add(control, 1, wx.EXPAND | wx.ALL, 8)
        root.Add(row, 0, wx.EXPAND)
        return control

    def values(self) -> tuple[str, str, str, list[Path]]:
        return (
            self.to_address.GetValue().strip(),
            self.subject.GetValue().strip(),
            self.body.GetValue(),
            list(self.attachment_paths),
        )

    def on_add_address(self, _event: wx.Event) -> None:
        value = self.to_address.GetValue().strip()
        if not value:
            wx.MessageBox(
                tr("يرجى كتابة بريد إلكتروني أولاً."),
                tr("عنوان البريد الإلكتروني مطلوب"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self.to_address.SetFocus()
            return
        added, result = add_address(value)
        if added:
            announce_to_screen_reader(
                self.to_address,
                tr("تمت إضافة عنوان البريد الإلكتروني إلى سجل العناوين."),
                EVENT_ADDRESS_BOOK,
            )
            return
        if result == "duplicate":
            message = "عنوان البريد الإلكتروني موجود بالفعل في سجل العناوين."
            title = "العنوان موجود"
        else:
            message = "يرجى كتابة بريد إلكتروني صالح أولاً."
            title = "عنوان غير صالح"
        wx.MessageBox(tr(message), tr(title), wx.OK | wx.ICON_INFORMATION, self)
        self.to_address.SetFocus()

    def on_to_address_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() != wx.WXK_DOWN:
            event.Skip()
            return
        entries = load_address_book()
        if not entries:
            announce_to_screen_reader(
                self.to_address,
                tr("سجل العناوين فارغ. أضف عنوان بريد إلكتروني أولاً."),
                EVENT_ADDRESS_BOOK,
            )
            return
        dialog = AddressPickerDialog(self, entries)
        try:
            if dialog.ShowModal() == wx.ID_OK:
                selected = dialog.selected_email()
                if selected:
                    self.to_address.SetValue(selected)
                    self.to_address.SetInsertionPointEnd()
                    announce_to_screen_reader(
                        self.to_address,
                        tr("تم اختيار {email} من سجل العناوين.").format(
                            email=selected
                        ),
                        EVENT_ADDRESS_BOOK,
                    )
        finally:
            dialog.Destroy()
        self.to_address.SetFocus()

    def on_add_attachments(self, _event: wx.CommandEvent) -> None:
        dialog = wx.FileDialog(
            self,
            tr("اختيار مرفقات الرسالة"),
            wildcard=tr("كل الملفات (*.*)|*.*"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            added_count = self.add_attachment_paths(
                [Path(path) for path in dialog.GetPaths()]
            )
        finally:
            dialog.Destroy()
        if added_count:
            announce_to_screen_reader(
                self.attachment_list,
                tr("تمت إضافة المرفقات إلى الرسالة."),
                EVENT_COMPOSE_ATTACHMENTS,
            )

    def add_attachment_paths(self, paths: list[Path]) -> int:
        known_paths = {
            path.resolve(strict=False)
            for path in self.attachment_paths
        }
        added_count = 0
        for path in paths:
            resolved = path.resolve(strict=False)
            if resolved in known_paths or not path.is_file():
                continue
            self.attachment_paths.append(path)
            known_paths.add(resolved)
            added_count += 1
        self.refresh_attachment_list()
        return added_count

    def refresh_attachment_list(self, selection: int | None = None) -> None:
        self.attachment_list.Set(
            [self.attachment_label(path) for path in self.attachment_paths]
        )
        if not self.attachment_paths:
            return
        target = (
            len(self.attachment_paths) - 1
            if selection is None
            else max(0, min(selection, len(self.attachment_paths) - 1))
        )
        self.attachment_list.SetSelection(target)

    @staticmethod
    def attachment_label(path: Path) -> str:
        try:
            size = path.stat().st_size
        except OSError:
            return path.name
        if size >= 1024 * 1024:
            size_label = f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:
            size_label = f"{size / 1024:.1f} KB"
        else:
            size_label = f"{size} bytes"
        return f"{path.name} - {size_label}"

    def remove_selected_attachment(self) -> None:
        selection = self.attachment_list.GetSelection()
        if not 0 <= selection < len(self.attachment_paths):
            return
        self.attachment_paths.pop(selection)
        self.refresh_attachment_list(selection)
        announce_to_screen_reader(
            self.attachment_list,
            tr("تمت إزالة المرفق من الرسالة."),
            EVENT_COMPOSE_ATTACHMENTS,
        )

    def on_attachment_key(self, event: wx.KeyEvent) -> None:
        key_code = event.GetKeyCode()
        if key_code == wx.WXK_DELETE:
            self.remove_selected_attachment()
            return
        if key_code in {wx.WXK_MENU, wx.WXK_WINDOWS_MENU}:
            self.show_attachment_context_menu()
            return
        event.Skip()

    def on_attachment_context_menu(self, event: wx.ContextMenuEvent) -> None:
        position = event.GetPosition()
        if position != wx.DefaultPosition:
            hit = self.attachment_list.HitTest(
                self.attachment_list.ScreenToClient(position)
            )
            if isinstance(hit, tuple):
                hit = hit[0]
            if hit != wx.NOT_FOUND:
                self.attachment_list.SetSelection(hit)
        self.show_attachment_context_menu()

    def show_attachment_context_menu(self) -> None:
        menu = wx.Menu()
        remove_item = menu.Append(wx.ID_ANY, tr("إزالة المرفق المحدد"))
        remove_item.Enable(self.attachment_list.GetSelection() != wx.NOT_FOUND)
        menu.Bind(
            wx.EVT_MENU,
            lambda _event: self.remove_selected_attachment(),
            remove_item,
        )
        try:
            announce_context_menu(self.attachment_list)
            self.attachment_list.PopupMenu(menu)
        finally:
            menu.Destroy()


class BulkDeleteDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, message_count: int) -> None:
        super().__init__(parent, title=tr("تأكيد حذف الرسائل"), size=(620, 230))
        root = wx.BoxSizer(wx.VERTICAL)
        question = wx.StaticText(
            self,
            label=tr(
                f"هل تريد حذف {message_count} رسالة وإرسالها إلى سلة المحذوفات؟"
            ),
        )
        question.Wrap(580)
        set_accessible(question, f"تأكيد حذف {message_count} رسالة")
        root.Add(question, 1, wx.EXPAND | wx.ALL, 16)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        cancel_button = wx.Button(self, wx.ID_CANCEL, label=tr("إلغاء"))
        delete_button = wx.Button(
            self,
            wx.ID_OK,
            label=tr("حذف وإرسال إلى سلة المحذوفات"),
        )
        set_accessible(cancel_button, "إلغاء حذف الرسائل")
        set_accessible(delete_button, f"حذف {message_count} رسالة وإرسالها إلى سلة المحذوفات")
        cancel_button.SetDefault()
        buttons.Add(cancel_button, 0, wx.ALL, 8)
        buttons.Add(delete_button, 0, wx.ALL, 8)
        root.Add(buttons, 0, wx.ALIGN_CENTER | wx.BOTTOM, 8)

        self.SetSizer(root)
        apply_layout_direction(self)
        self.CentreOnParent()
        wx.CallAfter(cancel_button.SetFocus)


class SpokenNotificationsDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, selected_event_ids: set[str]) -> None:
        super().__init__(parent, title=tr("الإشعارات التي سينطقها البرنامج"), size=(840, 620))
        root = wx.BoxSizer(wx.VERTICAL)
        content = wx.BoxSizer(wx.HORIZONTAL)

        self.category_event_ids = tuple(
            group.event_ids for group in SPOKEN_NOTIFICATION_GROUPS
        )
        self.event_values = {
            event_id: event_id in selected_event_ids for event_id in EVENTS_BY_ID
        }
        self.visible_event_checkboxes: dict[str, wx.CheckBox] = {}
        self.current_category_index: int | None = None

        self.category_list = wx.ListBox(
            self,
            choices=[tr(group.label) for group in SPOKEN_NOTIFICATION_GROUPS],
            style=wx.LB_SINGLE | wx.LB_NEEDED_SB,
            size=(280, -1),
        )
        set_accessible(
            self.category_list,
            "تصنيفات نطق إجراءات البرنامج",
            "اختر تصنيفًا ثم اضغط Tab للانتقال إلى خياراته.",
        )

        self.options_panel = wx.Panel(self, style=wx.TAB_TRAVERSAL)
        set_accessible(
            self.options_panel,
            "خيارات تصنيف نطق الإجراءات",
        )
        self.options_sizer = wx.BoxSizer(wx.VERTICAL)
        self.options_panel.SetSizer(self.options_sizer)

        self.category_list.Bind(wx.EVT_LISTBOX, self.on_category_changed)
        if self.category_list.GetCount():
            self.category_list.SetSelection(0)
            self._show_category(0, remember_current=False)
        content.Add(self.category_list, 0, wx.EXPAND | wx.ALL, 12)
        content.Add(self.options_panel, 1, wx.EXPAND | wx.TOP | wx.RIGHT | wx.BOTTOM, 12)
        root.Add(content, 1, wx.EXPAND)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.AddStretchSpacer(1)
        save_button = wx.Button(self, wx.ID_OK, label=tr("حفظ"))
        cancel_button = wx.Button(self, wx.ID_CANCEL, label=tr("إلغاء"))
        set_accessible(save_button, "حفظ الإشعارات المنطوقة")
        set_accessible(cancel_button, "إلغاء تعديلات الإشعارات")
        save_button.SetDefault()
        buttons.Add(cancel_button, 0, wx.ALL, 8)
        buttons.AddStretchSpacer(1)
        buttons.Add(save_button, 0, wx.ALL, 8)
        root.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.SetSizer(root)
        apply_layout_direction(self)
        localize_window(self)
        self.CentreOnParent()
        wx.CallAfter(self.category_list.SetFocus)

    def on_category_changed(self, _event: wx.CommandEvent) -> None:
        self._show_category(self.category_list.GetSelection())

    def _remember_visible_values(self) -> None:
        for event_id, checkbox in self.visible_event_checkboxes.items():
            self.event_values[event_id] = checkbox.GetValue()

    def _show_category(
        self,
        category_index: int,
        *,
        remember_current: bool = True,
    ) -> None:
        if not 0 <= category_index < len(SPOKEN_NOTIFICATION_GROUPS):
            return
        if remember_current:
            self._remember_visible_values()

        self.options_sizer.Clear(delete_windows=True)
        self.visible_event_checkboxes = {}
        group = SPOKEN_NOTIFICATION_GROUPS[category_index]
        self.options_sizer.Add(
            wx.StaticText(self.options_panel, label=tr(group.label)),
            0,
            wx.EXPAND | wx.ALL,
            10,
        )

        options_grid = wx.FlexGridSizer(cols=2, vgap=10, hgap=18)
        options_grid.AddGrowableCol(0, 1)
        options_grid.AddGrowableCol(1, 1)
        for event_id in self.category_event_ids[category_index]:
            event = EVENTS_BY_ID[event_id]
            checkbox = wx.CheckBox(self.options_panel, label=tr(event.label))
            checkbox.SetValue(self.event_values[event_id])
            set_accessible(
                checkbox,
                event.label,
                "اضغط Space لتحديد نطق هذا الإجراء أو إلغاء تحديده.",
            )
            self.visible_event_checkboxes[event_id] = checkbox
            options_grid.Add(checkbox, 1, wx.EXPAND)

        self.options_sizer.Add(options_grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)
        self.options_sizer.AddStretchSpacer(1)
        self.current_category_index = category_index
        self.options_panel.Layout()
        self.Layout()

    def selected_event_ids(self) -> set[str]:
        self._remember_visible_values()
        return {
            event_id
            for event_id, is_selected in self.event_values.items()
            if is_selected
        }


class SettingsDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, settings: ProgramSettings) -> None:
        super().__init__(parent, title="الإعدادات", size=(680, 700))
        self.settings = replace(settings)
        self.notification_event_ids = set(
            settings.spoken_notification_events
            if settings.spoken_notification_events is not None
            else preset_event_ids(settings.spoken_notification_level)
        )
        self._build()

    def _build(self) -> None:
        apply_layout_direction(self)
        root = wx.BoxSizer(wx.VERTICAL)

        self.focus_intro = wx.TextCtrl(
            self,
            value=tr("لغة البرنامج:"),
            style=wx.TE_READONLY | wx.BORDER_NONE,
        )
        set_accessible(self.focus_intro, "لغة البرنامج")
        root.Add(self.focus_intro, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.language_box = wx.Choice(
            self,
            choices=[tr(label) for label in LANGUAGE_CHOICES],
        )
        self.language_box.SetSelection(self.index_for_value(LANGUAGE_CHOICES, self.settings.language))
        set_accessible(self.language_box, "لغة البرنامج")
        root.Add(self.language_box, 0, wx.EXPAND | wx.ALL, 10)

        root.Add(wx.StaticText(self, label="مستعرض الرسائل:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.viewer_box = wx.Choice(
            self,
            choices=[tr(label) for label in VIEWER_CHOICES],
        )
        self.viewer_box.SetSelection(self.index_for_value(VIEWER_CHOICES, self.settings.message_viewer))
        set_accessible(
            self.viewer_box,
            "نوع مستعرض الرسائل",
            "مستعرض HTML يعطي الروابط والأزرار كعناصر صفحة، والمستعرض السهل يعرض الرسالة كنص عادي.",
        )
        root.Add(self.viewer_box, 0, wx.EXPAND | wx.ALL, 10)

        root.Add(
            wx.StaticText(self, label="طريقة تعليم الرسائل كمقروءة:"),
            0,
            wx.LEFT | wx.RIGHT | wx.TOP,
            10,
        )
        self.message_read_mode_box = wx.Choice(
            self,
            choices=[tr(label) for label in MESSAGE_READ_MODE_CHOICES],
        )
        self.message_read_mode_box.SetSelection(
            self.index_for_value(
                MESSAGE_READ_MODE_CHOICES,
                self.settings.message_read_mode,
            )
        )
        set_accessible(
            self.message_read_mode_box,
            "طريقة قراءة الرسائل",
            (
                "يدوي يبقي الرسالة غير مقروءة حتى تضغط Space أو تستخدم قائمة السياق. "
                "تلقائي يعلم الرسالة كمقروءة عند الدخول إلى مستعرض الرسالة وظهور محتواها الكامل."
            ),
        )
        root.Add(self.message_read_mode_box, 0, wx.EXPAND | wx.ALL, 10)

        root.Add(wx.StaticText(self, label="نمط الترجمة:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.translation_mode_box = wx.Choice(
            self,
            choices=[tr(label) for label in TRANSLATION_MODE_CHOICES],
        )
        self.translation_mode_box.SetSelection(
            self.index_for_value(TRANSLATION_MODE_CHOICES, self.settings.translation_mode)
        )
        set_accessible(self.translation_mode_box, "نمط الترجمة")
        root.Add(self.translation_mode_box, 0, wx.EXPAND | wx.ALL, 10)

        root.Add(
            wx.StaticText(self, label="نطق إجراءات البرنامج:"),
            0,
            wx.LEFT | wx.RIGHT | wx.TOP,
            10,
        )
        notification_row = wx.BoxSizer(wx.HORIZONTAL)
        self.notification_level_box = wx.Choice(
            self,
            choices=[tr(label) for label in SPOKEN_NOTIFICATION_LEVEL_CHOICES],
        )
        self.notification_level_box.SetSelection(
            self.index_for_value(
                SPOKEN_NOTIFICATION_LEVEL_CHOICES,
                self.settings.spoken_notification_level,
            )
        )
        set_accessible(
            self.notification_level_box,
            "مستوى نطق إجراءات البرنامج",
            "اختر مستوى جاهزًا، ثم استخدم زر عرض الإشعارات لتخصيصه.",
        )
        self.notification_level_box.Bind(
            wx.EVT_CHOICE,
            self.on_notification_level_changed,
        )
        notification_row.Add(self.notification_level_box, 1, wx.EXPAND | wx.ALL, 10)
        self.customize_notifications_button = wx.Button(
            self,
            label="تخصيص نطق الإجراءات وإدارتها",
        )
        set_accessible(
            self.customize_notifications_button,
            "تخصيص نطق الإجراءات وإدارتها",
            "يفتح تصنيفات تحتوي مربعات اختيار حقيقية مع زر حفظ.",
        )
        self.customize_notifications_button.Bind(
            wx.EVT_BUTTON,
            self.on_customize_notifications,
        )
        notification_row.Add(
            self.customize_notifications_button,
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.ALL,
            10,
        )
        root.Add(notification_row, 0, wx.EXPAND)

        self.default_mail_button = wx.Button(
            self,
            label="اختيار PowerAccessibleMail كتطبيق البريد الافتراضي",
        )
        set_accessible(
            self.default_mail_button,
            "اختيار PowerAccessibleMail كتطبيق البريد الافتراضي",
            (
                "يفتح إعدادات التطبيقات الافتراضية في Windows. داخل قائمة "
                "التطبيقات المرتبطة اضغط Space لفتح اختيار التطبيق؛ قد لا "
                "يستجيب Enter في Windows 11."
            ),
        )
        self.default_mail_button.Bind(wx.EVT_BUTTON, self.on_default_mail)
        root.Add(self.default_mail_button, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.theme_box = wx.RadioBox(
            self,
            label="الوضع الشكلي",
            choices=[tr(label) for label in THEME_CHOICES],
            majorDimension=1,
            style=wx.RA_SPECIFY_ROWS,
        )
        self.theme_box.SetSelection(1 if self.settings.theme == THEME_DARK else 0)
        set_accessible(self.theme_box, "الوضع الشكلي")
        root.Add(self.theme_box, 0, wx.EXPAND | wx.ALL, 10)

        buttons = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        if buttons:
            root.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(root)
        localize_window(self)
        wx.CallAfter(self.focus_intro.SetFocus)

    def selected_settings(self) -> ProgramSettings:
        selected_events = normalize_event_ids(self.notification_event_ids)
        return ProgramSettings(
            language=self.value_for_index(self.language_box, LANGUAGE_CHOICES, self.settings.language),
            message_viewer=self.value_for_index(self.viewer_box, VIEWER_CHOICES, self.settings.message_viewer),
            message_read_mode=self.value_for_index(
                self.message_read_mode_box,
                MESSAGE_READ_MODE_CHOICES,
                self.settings.message_read_mode,
            ),
            theme=THEME_DARK if self.theme_box.GetSelection() == 1 else THEME_LIGHT,
            translation_mode=self.value_for_index(
                self.translation_mode_box,
                TRANSLATION_MODE_CHOICES,
                self.settings.translation_mode,
            ),
            translation_data_notice_accepted=(
                self.settings.translation_data_notice_accepted
            ),
            spoken_notification_level=self.value_for_index(
                self.notification_level_box,
                SPOKEN_NOTIFICATION_LEVEL_CHOICES,
                self.settings.spoken_notification_level,
            ),
            spoken_notification_events=selected_events or [],
        )

    def on_notification_level_changed(self, _event: wx.Event) -> None:
        level = self.value_for_index(
            self.notification_level_box,
            SPOKEN_NOTIFICATION_LEVEL_CHOICES,
            self.settings.spoken_notification_level,
        )
        self.notification_event_ids = preset_event_ids(level)

    def on_customize_notifications(self, _event: wx.Event) -> None:
        dialog = SpokenNotificationsDialog(self, self.notification_event_ids)
        try:
            if dialog.ShowModal() == wx.ID_OK:
                self.notification_event_ids = dialog.selected_event_ids()
        finally:
            dialog.Destroy()
        self.customize_notifications_button.SetFocus()

    def on_default_mail(self, event: wx.Event) -> None:
        parent = self.GetParent()
        handler = getattr(parent, "on_open_default_apps", None)
        if callable(handler):
            handler(event)

    def value_for_index(self, choice: wx.Choice, mapping: dict[str, str], fallback: str) -> str:
        values = list(mapping.values())
        index = choice.GetSelection()
        return values[index] if 0 <= index < len(values) else fallback

    def index_for_value(self, mapping: dict[str, str], value: str) -> int:
        values = list(mapping.values())
        return values.index(value) if value in values else 0


class UpdateAvailableDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, result: UpdateCheckResult) -> None:
        super().__init__(parent, title=tr("تحديث متاح"), size=(620, 340))
        root = wx.BoxSizer(wx.VERTICAL)
        details = tr(result.message)
        if result.notes:
            details += f"\n\n{tr('ملاحظات الإصدار:')}\n{result.notes}"
        self.details = wx.TextCtrl(
            self,
            value=details,
            style=wx.TE_MULTILINE | wx.TE_READONLY,
        )
        set_accessible(self.details, "تفاصيل التحديث")
        root.Add(self.details, 1, wx.EXPAND | wx.ALL, 12)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.update_button = wx.Button(self, wx.ID_OK, label=tr("تحديث الآن"))
        set_accessible(self.update_button, "تنزيل التحديث وتثبيته")
        self.update_button.SetDefault()
        buttons.Add(self.update_button, 0, wx.ALL, 8)
        self.close_button = wx.Button(self, wx.ID_CANCEL, label=tr("إغلاق"))
        buttons.Add(self.close_button, 0, wx.ALL, 8)
        root.Add(buttons, 0, wx.ALIGN_CENTER | wx.BOTTOM, 8)

        self.SetSizer(root)
        apply_layout_direction(self)
        self.CentreOnParent()
        wx.CallAfter(self.update_button.SetFocus)


class UpdateDownloadDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        version: str,
        release_date: str,
        cancel_callback: Callable[[], None],
    ) -> None:
        super().__init__(parent, title=tr("تحديث البرنامج"), size=(560, 280))
        self.cancel_callback = cancel_callback
        root = wx.BoxSizer(wx.VERTICAL)

        self.version_label = wx.StaticText(
            self,
            label=tr(f"الإصدار الجديد: {version}"),
        )
        set_accessible(self.version_label, f"الإصدار الجديد: {version}")
        root.Add(self.version_label, 0, wx.EXPAND | wx.ALL, 12)

        displayed_date = (
            release_date.split("T", 1)[0]
            if release_date
            else tr("غير متوفر")
        )
        update_summary = tr(
            f"الإصدار الجديد: {version}. تاريخ الإطلاق: {displayed_date}."
        )
        self.release_date_label = wx.StaticText(
            self,
            label=tr(f"تاريخ الإطلاق: {displayed_date}"),
        )
        set_accessible(
            self.release_date_label,
            f"تاريخ إطلاق التحديث: {displayed_date}",
        )
        root.Add(
            self.release_date_label,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            12,
        )

        self.status = wx.StaticText(self, label=tr("جار تنزيل التحديث: 0%."))
        set_accessible(self.status, "حالة تنزيل التحديث")
        root.Add(
            self.status,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            12,
        )

        self.progress = wx.Gauge(self, range=100)
        self.progress.SetValue(0)
        set_accessible(self.progress, "تقدم تنزيل التحديث")
        root.Add(
            self.progress,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            14,
        )

        self.cancel_button = wx.Button(self, label=tr("إلغاء"))
        set_accessible(self.cancel_button, "إلغاء تنزيل التحديث")
        self.cancel_button.Bind(wx.EVT_BUTTON, self.on_cancel)
        root.Add(self.cancel_button, 0, wx.ALIGN_CENTER | wx.BOTTOM, 12)

        self.SetSizer(root)
        apply_layout_direction(self)
        self.CentreOnParent()
        self.Bind(wx.EVT_CLOSE, self.on_cancel)
        wx.CallAfter(announce_to_screen_reader, self, update_summary)
        wx.CallAfter(self.cancel_button.SetFocus)

    def set_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            percent = max(0, min(100, round((downloaded / total) * 100)))
            self.progress.SetValue(percent)
            message = tr(f"جار تنزيل التحديث: {percent}%.")
        else:
            self.progress.Pulse()
            megabytes = downloaded / (1024 * 1024)
            message = tr(f"جار تنزيل التحديث: {megabytes:.1f} ميغابايت.")
        self.status.SetLabel(message)
        self.status.SetName(message)
        self.progress.SetName(message)

    def on_cancel(self, event: wx.Event) -> None:
        self.cancel_callback()
        self.cancel_button.Disable()
        message = tr("جار إلغاء تنزيل التحديث.")
        self.status.SetLabel(message)
        self.status.SetName(message)
        if isinstance(event, wx.CloseEvent) and event.CanVeto():
            event.Veto()
