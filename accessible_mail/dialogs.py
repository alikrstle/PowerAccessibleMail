from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

import wx

from .accessibility import announce_context_menu, announce_to_screen_reader, set_accessible, set_accessible_choice
from .address_book import add_address, load_address_book, normalize_email_address
from .address_book_dialog import AddressPickerDialog, request_custom_address_name
from .config import ProgramSettings, THEME_DARK, THEME_LIGHT
from .i18n import tr
from .notification_preferences import (
    EVENT_ADDRESS_BOOK,
    EVENT_COMPOSE_ATTACHMENTS,
    EVENTS_BY_ID,
    SPOKEN_NOTIFICATION_GROUPS,
    SPOKEN_NOTIFICATION_EVENT_COUNT,
    NOTIFICATION_LEVEL_CUSTOM,
    normalize_event_ids,
    preset_event_ids,
)
from .ui_constants import (
    LANGUAGE_CHOICES,
    MESSAGE_READ_MODE_CHOICES,
    SEARCH_MODE_CHOICES,
    SPOKEN_NOTIFICATION_LEVEL_CHOICES,
    THEME_CHOICES,
    TRANSLATION_MODE_CHOICES,
    VIEWER_CHOICES,
)
from .ui_helpers import apply_layout_direction, localize_window
from .update_checker import UpdateCheckResult
from .compose_translation import ComposeTranslationMixin
from .visual_accessibility import CURSOR_SIZES, FONT_SCALES
from .program_sounds import (
    PROGRAM_SOUNDS,
    normalize_custom_sound_files,
    normalize_sound_event_ids,
    play_program_sound,
    replace_program_sound,
)


def set_scrollable_dialog_content(
    dialog: wx.Dialog,
    content_sizer: wx.Sizer,
) -> wx.ScrolledWindow:
    """Keep enlarged dialog controls reachable on smaller displays."""
    scroller = wx.ScrolledWindow(
        dialog,
        style=wx.HSCROLL | wx.VSCROLL | wx.TAB_TRAVERSAL,
    )
    for child in list(dialog.GetChildren()):
        if child is not scroller:
            child.Reparent(scroller)
    scroller.SetSizer(content_sizer)
    scroll_step = scroller.FromDIP(20)
    scroller.SetScrollRate(scroll_step, scroll_step)
    scroller.FitInside()
    outer = wx.BoxSizer(wx.VERTICAL)
    outer.Add(scroller, 1, wx.EXPAND)
    dialog.SetSizer(outer)
    return scroller


class MessageTranslationLanguageDialog(wx.Dialog):
    """Choose the default message-translation language after first consent."""

    def __init__(self, parent: wx.Window, selected_code: str = "") -> None:
        super().__init__(
            parent,
            title=tr("اختيار لغة ترجمة الرسائل"),
            size=(520, 600),
        )
        from .translation_languages import language_name, message_language_codes

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(
            wx.StaticText(
                self,
                label=tr(
                    "اختر اللغة التي تريد ترجمة الرسائل إليها. "
                    "تظهر اللغات العشرون الأكثر شيوعا أولا، ثم بقية اللغات."
                ),
            ),
            0,
            wx.EXPAND | wx.ALL,
            10,
        )
        self.codes = message_language_codes()
        self.languages = wx.ListBox(
            self,
            choices=[language_name(code) for code in self.codes],
        )
        set_accessible(
            self.languages,
            "قائمة لغات ترجمة الرسائل",
            "استخدم الأسهم ثم اضغط Enter، أو انقر على اللغة بزر الفأرة.",
        )
        root.Add(self.languages, 1, wx.EXPAND | wx.ALL, 10)
        buttons = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        if buttons:
            root.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(root)
        localize_window(self)
        selection = self.codes.index(selected_code) if selected_code in self.codes else 0
        self.languages.SetSelection(selection)
        self.languages.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.languages.Bind(wx.EVT_LEFT_UP, self.on_mouse_select)
        self.CentreOnParent()
        wx.CallAfter(self.languages.SetFocus)

    def on_key(self, event: wx.KeyEvent) -> None:
        if (
            event.GetKeyCode() in {wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER}
            and self.languages.GetSelection() != wx.NOT_FOUND
        ):
            self.EndModal(wx.ID_OK)
            return
        event.Skip()

    def on_mouse_select(self, event: wx.MouseEvent) -> None:
        selection = self.languages.HitTest(event.GetPosition())
        if selection != wx.NOT_FOUND:
            self.languages.SetSelection(selection)
            self.EndModal(wx.ID_OK)
            return
        event.Skip()

    def selected_code(self) -> str:
        selection = self.languages.GetSelection()
        return self.codes[selection] if 0 <= selection < len(self.codes) else ""


class ComposeDialog(ComposeTranslationMixin, wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        title: str = "إنشاء بريد إلكتروني",
        to_address: str = "",
        subject: str = "",
        body: str = "",
        attachment_paths: Sequence[Path] = (),
        forward_comment: bool = False,
        practice: bool = False,
    ) -> None:
        super().__init__(parent, title=title, size=(720, 680))
        self.attachment_paths = [
            Path(path)
            for path in attachment_paths
            if Path(path).is_file()
        ]
        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.VERTICAL)

        self.to_address = self._recipient_row(panel, root, to_address)
        self.subject = self._row(panel, root, "الموضوع:", subject)
        self.forward_comment = None
        if forward_comment:
            root.Add(wx.StaticText(panel, label=tr("تعليق مع إعادة التوجيه:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
            self.forward_comment = wx.TextCtrl(panel, style=wx.TE_MULTILINE, size=(-1, 70))
            set_accessible(self.forward_comment, "تعليق مع إعادة التوجيه", "اختياري. يظهر تعليقك قبل محتوى الرسالة المعاد توجيهها.")
            root.Add(self.forward_comment, 0, wx.EXPAND | wx.ALL, 8)

        root.Add(wx.StaticText(panel, label="المحتوى:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.body = wx.TextCtrl(panel, value=body, style=wx.TE_MULTILINE)
        set_accessible(self.body, "محتوى الرسالة", "اكتب محتوى البريد الإلكتروني هنا")
        root.Add(self.body, 1, wx.EXPAND | wx.ALL, 8)
        if not practice:
            self.install_text_translation()

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
        self.refresh_attachment_list()

        send_button = wx.Button(panel, id=wx.ID_OK, label="إرسال")
        cancel_button = wx.Button(panel, id=wx.ID_CANCEL, label="إلغاء")
        if practice:
            send_button.SetLabel(tr("تأكيد إعادة التوجيه التجريبي"))
            self.add_address_button.Disable()
            self.to_address.Unbind(wx.EVT_KEY_DOWN)
            self.add_attachment_button.Disable()
        set_accessible(send_button, "إرسال الرسالة")
        if practice:
            set_accessible(send_button, "تأكيد إعادة التوجيه التجريبي")
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
        body = self.body.GetValue()
        comment_control = getattr(self, "forward_comment", None)
        if comment_control is not None:
            comment = comment_control.GetValue().strip()
            if comment:
                body = comment + "\n\n" + body
        return (
            self.to_address.GetValue().strip(),
            self.subject.GetValue().strip(),
            body,
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
        normalized = normalize_email_address(value)
        if not normalized:
            wx.MessageBox(
                tr("يرجى كتابة بريد إلكتروني صالح أولاً."),
                tr("عنوان غير صالح"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self.to_address.SetFocus()
            return
        if any(entry.email.casefold() == normalized.casefold() for entry in load_address_book()):
            wx.MessageBox(
                tr("عنوان البريد الإلكتروني موجود بالفعل في سجل العناوين."),
                tr("العنوان موجود"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self.to_address.SetFocus()
            return
        name = request_custom_address_name(self, normalized)
        added, result = add_address(normalized, name)
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
        inventory = wx.StaticText(
            self,
            label=tr("تتضمن القائمة {count} نوعاً من إشعارات البرنامج.").format(
                count=SPOKEN_NOTIFICATION_EVENT_COUNT
            ),
        )
        root.Add(inventory, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 12)
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


class ProgramSoundsDialog(wx.Dialog):
    def __init__(
        self,
        parent: wx.Window,
        settings: ProgramSettings,
        selected_event_ids: set[str],
    ) -> None:
        super().__init__(parent, title=tr("تخصيص أصوات البرنامج"), size=(620, 560))
        self.settings = replace(settings)
        self.sound_files = normalize_custom_sound_files(
            self.settings.program_sound_files
        )
        self.sound_checkboxes: dict[str, wx.CheckBox] = {}
        root = wx.BoxSizer(wx.VERTICAL)
        description = wx.StaticText(
            self,
            label=tr(
                "حدد الأصوات التي تريد سماعها. انتقل إلى اسم الصوت واضغط Enter "
                "لتشغيله، أو انقر على اسمه بزر الفأرة."
            ),
        )
        description.Wrap(570)
        root.Add(description, 0, wx.EXPAND | wx.ALL, 12)
        sound_grid = wx.FlexGridSizer(rows=len(PROGRAM_SOUNDS), cols=3, vgap=8, hgap=8)
        sound_grid.AddGrowableCol(1, 1)
        for sound in PROGRAM_SOUNDS:
            enabled_box = wx.CheckBox(self, label=tr("تشغيل"))
            enabled_box.SetValue(sound.event_id in selected_event_ids)
            set_accessible(
                enabled_box,
                tr("تشغيل الصوت: {name}").format(name=tr(sound.label)),
                tr("اضغط Space لتفعيل هذا الصوت أو تعطيله."),
            )
            self.sound_checkboxes[sound.event_id] = enabled_box
            sound_grid.Add(enabled_box, 0, wx.ALIGN_CENTER_VERTICAL)

            sound_button = wx.Button(self, label=tr(sound.label))
            sound_button.Bind(
                wx.EVT_BUTTON,
                lambda _event, event_id=sound.event_id: self.play_sound(event_id),
            )
            set_accessible(
                sound_button,
                sound.label,
                "اضغط Enter لتشغيل الصوت.",
            )
            sound_grid.Add(sound_button, 1, wx.EXPAND)

            replace_button = wx.Button(self, label=tr("استبدال"))
            replace_button.Bind(
                wx.EVT_BUTTON,
                lambda _event, event_id=sound.event_id: self.on_replace(event_id),
            )
            set_accessible(
                replace_button,
                tr("استبدال الصوت: {name}").format(name=tr(sound.label)),
            )
            sound_grid.Add(replace_button, 0, wx.ALIGN_CENTER_VERTICAL)
        root.Add(sound_grid, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        buttons = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        if buttons:
            root.Add(buttons, 0, wx.EXPAND | wx.ALL, 12)
        self.scroller = set_scrollable_dialog_content(self, root)
        localize_window(self)
        self.scroller.FitInside()
        if PROGRAM_SOUNDS:
            wx.CallAfter(
                self.sound_checkboxes[PROGRAM_SOUNDS[0].event_id].SetFocus
            )

    def selected_event_ids(self) -> set[str]:
        return {
            event_id
            for event_id, checkbox in self.sound_checkboxes.items()
            if checkbox.GetValue()
        }

    def selected_sound_files(self) -> dict[str, str]:
        return dict(self.sound_files)

    def play_sound(self, event_id: str) -> None:
        self.settings.program_sound_files = dict(self.sound_files)
        play_program_sound(event_id, self.settings, force=True)

    def on_replace(self, event_id: str) -> None:
        dialog = wx.FileDialog(
            self,
            message=tr("اختر ملف MP3 لاستبدال الصوت"),
            wildcard=tr("ملفات MP3 (*.mp3)|*.mp3"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            destination = replace_program_sound(event_id, Path(dialog.GetPath()))
        except (OSError, ValueError) as exc:
            wx.MessageBox(
                tr("تعذر استبدال الصوت.\n\n{error}").format(error=exc),
                tr("استبدال الصوت"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return
        finally:
            dialog.Destroy()
        self.sound_files[event_id] = str(destination)
        self.settings.program_sound_files = dict(self.sound_files)
        sound = next(item for item in PROGRAM_SOUNDS if item.event_id == event_id)
        announce_to_screen_reader(
            self,
            tr("تم استبدال صوت {name}.").format(name=tr(sound.label)),
        )
        self.play_sound(event_id)


class LowVisionOptionsDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, settings: ProgramSettings) -> None:
        super().__init__(
            parent,
            title=tr("ميزات وخيارات ضعاف البصر"),
            size=(640, 680),
        )
        self.settings = replace(settings)
        root = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            self,
            label=tr(
                "يمكنك تكبير عناصر البرنامج وزيادة وضوحها. تطبق الخيارات داخل "
                "Power Accessible Mail فقط ولا تغيّر إعدادات Windows."
            ),
        )
        intro.Wrap(590)
        root.Add(intro, 0, wx.EXPAND | wx.ALL, 12)

        root.Add(wx.StaticText(self, label=tr("حجم الخط وعناصر الواجهة:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        self.font_scale_box = wx.Choice(
            self,
            choices=[tr(f"{value}%") for value in FONT_SCALES],
        )
        self.font_scale_box.SetSelection(FONT_SCALES.index(self.settings.low_vision_font_scale))
        set_accessible_choice(
            self.font_scale_box,
            "حجم الخط وعناصر الواجهة",
            "اختر نسبة التكبير التي تناسب قدرتك على الرؤية.",
        )
        root.Add(self.font_scale_box, 0, wx.EXPAND | wx.ALL, 12)

        root.Add(wx.StaticText(self, label=tr("حجم المؤشر داخل البرنامج:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        cursor_labels = ("عادي", "كبير", "كبير جداً")
        self.cursor_size_box = wx.Choice(
            self,
            choices=[tr(label) for label in cursor_labels],
        )
        self.cursor_size_box.SetSelection(CURSOR_SIZES.index(self.settings.low_vision_cursor_size))
        set_accessible_choice(
            self.cursor_size_box,
            "حجم المؤشر داخل البرنامج",
            "يكبّر مؤشر الفأرة ومؤشر الكتابة داخل نوافذ البرنامج.",
        )
        root.Add(self.cursor_size_box, 0, wx.EXPAND | wx.ALL, 12)

        root.Add(wx.StaticText(self, label=tr("خيارات العرض:")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
        self.visual_option_list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.visual_option_list.InsertColumn(0, tr("خيارات العرض"), width=540)
        self.visual_option_list.EnableCheckBoxes(True)
        self.visual_option_list.SetMinSize((-1, self.FromDIP(190)))
        self.visual_option_labels = (
            "استخدام تباين عالٍ",
            "تمييز العنصر الذي عليه التركيز",
            "استخدام ألوان مخصصة",
        )
        for index, label in enumerate(self.visual_option_labels):
            self.visual_option_list.InsertItem(index, tr(label))
        for index, checked in enumerate((
            self.settings.low_vision_high_contrast,
            self.settings.low_vision_focus_highlight,
            self.settings.low_vision_custom_colours,
        )):
            self.visual_option_list.CheckItem(index, checked)
        self.visual_option_list.SetItemState(
            0, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
            wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
        )
        set_accessible(
            self.visual_option_list,
            "خيارات العرض",
            "استخدم الأسهم للتنقل وSpace لتفعيل الخيار أو إيقافه. اضغط Tab للانتقال إلى الألوان أو أزرار الحفظ.",
        )
        self.visual_option_list.Bind(wx.EVT_CHAR_HOOK, self.on_visual_option_key)
        self.visual_option_list.Bind(wx.EVT_LIST_ITEM_CHECKED, self.on_colour_mode_changed)
        self.visual_option_list.Bind(wx.EVT_LIST_ITEM_UNCHECKED, self.on_colour_mode_changed)
        root.Add(self.visual_option_list, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.colour_mode_note = wx.StaticText(self, label="")
        set_accessible(self.colour_mode_note, "حالة الألوان المخصصة")
        root.Add(self.colour_mode_note, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        colours = wx.FlexGridSizer(rows=2, cols=2, vgap=10, hgap=12)
        colours.AddGrowableCol(1, 1)
        colours.Add(wx.StaticText(self, label=tr("لون النص:")), 0, wx.ALIGN_CENTER_VERTICAL)
        self.text_colour_picker = wx.ColourPickerCtrl(
            self,
            colour=wx.Colour(self.settings.low_vision_text_colour),
        )
        set_accessible(self.text_colour_picker, "اختيار لون النص")
        self.text_colour_picker.Bind(wx.EVT_COLOURPICKER_CHANGED, self.on_colour_picker_changed)
        colours.Add(self.text_colour_picker, 1, wx.EXPAND)
        colours.Add(wx.StaticText(self, label=tr("لون الخلفية:")), 0, wx.ALIGN_CENTER_VERTICAL)
        self.background_colour_picker = wx.ColourPickerCtrl(
            self,
            colour=wx.Colour(self.settings.low_vision_background_colour),
        )
        set_accessible(self.background_colour_picker, "اختيار لون الخلفية")
        self.background_colour_picker.Bind(wx.EVT_COLOURPICKER_CHANGED, self.on_colour_picker_changed)
        colours.Add(self.background_colour_picker, 1, wx.EXPAND)
        root.Add(colours, 0, wx.EXPAND | wx.ALL, 12)

        buttons = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)
        if buttons:
            root.Add(buttons, 0, wx.EXPAND | wx.ALL, 12)
        self.scroller = set_scrollable_dialog_content(self, root)
        self.on_colour_mode_changed(None)
        localize_window(self)
        self.update_colour_picker_names()
        self.scroller.FitInside()
        wx.CallAfter(self.font_scale_box.SetFocus)

    def on_colour_mode_changed(self, _event: wx.Event | None) -> None:
        enabled = (
            self.visual_option_list.IsItemChecked(2)
            and not self.visual_option_list.IsItemChecked(0)
        )
        self.text_colour_picker.Enable(enabled)
        self.background_colour_picker.Enable(enabled)
        self.colour_mode_note.SetLabel(
            tr("الألوان المخصصة لا تُطبّق أثناء تشغيل التباين العالي.")
            if self.visual_option_list.IsItemChecked(0) and self.visual_option_list.IsItemChecked(2)
            else ""
        )
        if hasattr(self, "scroller"):
            self.scroller.Layout()

    def on_colour_picker_changed(self, _event: wx.Event) -> None:
        self.update_colour_picker_names()

    def update_colour_picker_names(self) -> None:
        for picker, label in (
            (self.text_colour_picker, "اختيار لون النص"),
            (self.background_colour_picker, "اختيار لون الخلفية"),
        ):
            colour = picker.GetColour().GetAsString(wx.C2S_HTML_SYNTAX)
            picker.SetName(f"{tr(label)}: {colour}")
            picker.SetToolTip(f"{tr(label)}: {colour}")

    def on_visual_option_key(self, event: wx.KeyEvent) -> None:
        key = event.GetKeyCode()
        if key == wx.WXK_SPACE and not (event.ControlDown() or event.AltDown() or event.ShiftDown()):
            index = self.visual_option_list.GetFocusedItem()
            if index >= 0:
                self.visual_option_list.CheckItem(index, not self.visual_option_list.IsItemChecked(index))
            return
        if key == wx.WXK_TAB and not event.ControlDown() and not event.AltDown():
            if event.ShiftDown():
                self.cursor_size_box.SetFocus()
            else:
                target = self.text_colour_picker if self.text_colour_picker.IsEnabled() else self.FindWindow(wx.ID_OK)
                if target is not None:
                    target.SetFocus()
            return
        event.Skip()

    def selected_settings(self) -> ProgramSettings:
        return replace(
            self.settings,
            low_vision_font_scale=FONT_SCALES[self.font_scale_box.GetSelection()],
            low_vision_high_contrast=self.visual_option_list.IsItemChecked(0),
            low_vision_cursor_size=CURSOR_SIZES[self.cursor_size_box.GetSelection()],
            low_vision_focus_highlight=self.visual_option_list.IsItemChecked(1),
            low_vision_custom_colours=self.visual_option_list.IsItemChecked(2),
            low_vision_text_colour=self.text_colour_picker.GetColour().GetAsString(wx.C2S_HTML_SYNTAX),
            low_vision_background_colour=self.background_colour_picker.GetColour().GetAsString(wx.C2S_HTML_SYNTAX),
        )


class SettingsDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, settings: ProgramSettings) -> None:
        super().__init__(parent, title="الإعدادات", size=(680, 700))
        self.settings = replace(settings)
        self.notification_event_ids = set(
            settings.spoken_notification_events
            if settings.spoken_notification_events is not None
            else preset_event_ids(settings.spoken_notification_level)
        )
        self.sound_event_ids = set(
            normalize_sound_event_ids(settings.program_sound_events)
        )
        self.sound_files = normalize_custom_sound_files(
            settings.program_sound_files
        )
        self._build()

    def _build(self) -> None:
        apply_layout_direction(self)
        root = wx.BoxSizer(wx.VERTICAL)

        self.language_intro = wx.TextCtrl(self, value=tr("لغة البرنامج:"),
                                         style=wx.TE_READONLY | wx.BORDER_NONE)
        set_accessible(self.language_intro, "لغة البرنامج")
        root.Add(self.language_intro, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.language_box = wx.Choice(
            self,
            choices=[tr(label) for label in LANGUAGE_CHOICES],
        )
        self.language_box.SetSelection(self.index_for_value(LANGUAGE_CHOICES, self.settings.language))
        set_accessible_choice(self.language_box, "لغة البرنامج")
        root.Add(self.language_box, 0, wx.EXPAND | wx.ALL, 10)

        root.Add(wx.StaticText(self, label="مستعرض الرسائل:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.viewer_box = wx.Choice(
            self,
            choices=[tr(label) for label in VIEWER_CHOICES],
        )
        self.viewer_box.SetSelection(self.index_for_value(VIEWER_CHOICES, self.settings.message_viewer))
        set_accessible_choice(
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
        set_accessible_choice(
            self.message_read_mode_box,
            "طريقة قراءة الرسائل",
            (
                "يدوي يبقي الرسالة غير مقروءة حتى تضغط Space أو تستخدم قائمة السياق. "
                "تلقائي يعلم الرسالة كمقروءة عند الدخول إلى مستعرض الرسالة وظهور محتواها الكامل."
            ),
        )
        root.Add(self.message_read_mode_box, 0, wx.EXPAND | wx.ALL, 10)

        root.Add(
            wx.StaticText(self, label="طريقة البحث في الرسائل:"),
            0,
            wx.LEFT | wx.RIGHT | wx.TOP,
            10,
        )
        self.search_mode_box = wx.Choice(
            self,
            choices=[tr(label) for label in SEARCH_MODE_CHOICES],
        )
        self.search_mode_box.SetSelection(
            self.index_for_value(SEARCH_MODE_CHOICES, self.settings.search_mode)
        )
        set_accessible_choice(
            self.search_mode_box,
            "طريقة البحث في الرسائل",
            (
                "اختر استدعاء نافذة البحث بالاختصار، أو إظهار زر البحث، "
                "أو إظهار حقل دائم يفلتر رسائل القسم الحالي أثناء الكتابة."
            ),
        )
        root.Add(self.search_mode_box, 0, wx.EXPAND | wx.ALL, 10)

        root.Add(wx.StaticText(self, label="نمط الترجمة:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.translation_mode_box = wx.Choice(
            self,
            choices=[tr(label) for label in TRANSLATION_MODE_CHOICES],
        )
        self.translation_mode_box.SetSelection(
            self.index_for_value(TRANSLATION_MODE_CHOICES, self.settings.translation_mode)
        )
        set_accessible_choice(self.translation_mode_box, "نمط الترجمة")
        root.Add(self.translation_mode_box, 0, wx.EXPAND | wx.ALL, 10)
        from .translation_languages import message_language_codes, language_name
        self.message_language_codes = message_language_codes()
        translation_label = "اختر اللغة التي سيتم ترجمة رسائل البريد إليها"
        root.Add(wx.StaticText(self, label=tr(translation_label)), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.message_translation_language_box = wx.Choice(
            self, choices=[language_name(code) for code in self.message_language_codes],
        )
        selected_language = self.settings.message_translation_language or self.settings.language
        self.message_translation_language_box.SetSelection(
            self.message_language_codes.index(selected_language)
            if selected_language in self.message_language_codes else 0
        )
        set_accessible_choice(self.message_translation_language_box, translation_label)
        root.Add(self.message_translation_language_box, 0, wx.EXPAND | wx.ALL, 10)

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
        set_accessible_choice(
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

        sound_row = wx.BoxSizer(wx.HORIZONTAL)
        self.program_sounds_box = wx.CheckBox(
            self,
            label=tr("تشغيل أصوات البرنامج"),
        )
        self.program_sounds_box.SetValue(self.settings.program_sounds_enabled)
        set_accessible(
            self.program_sounds_box,
            "تشغيل أصوات البرنامج",
            "يشغّل أصواتاً قصيرة عند تنفيذ أحداث محددة في البرنامج.",
        )
        sound_row.Add(self.program_sounds_box, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 10)
        self.customize_sounds_button = wx.Button(
            self,
            label=tr("تخصيص أصوات البرنامج"),
        )
        self.customize_sounds_button.Bind(wx.EVT_BUTTON, self.on_customize_sounds)
        set_accessible(
            self.customize_sounds_button,
            "تخصيص أصوات البرنامج",
            "يفتح قائمة الأصوات مع إمكانية تشغيل كل صوت للتجربة.",
        )
        sound_row.Add(self.customize_sounds_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 10)
        root.Add(sound_row, 0, wx.EXPAND)

        self.low_vision_options_button = wx.Button(
            self,
            label=tr("ميزات وخيارات ضعاف البصر"),
        )
        set_accessible(
            self.low_vision_options_button,
            "ميزات وخيارات ضعاف البصر",
            "يفتح خيارات تكبير الخط والتباين والمؤشر وتمييز التركيز والألوان.",
        )
        self.low_vision_options_button.Bind(wx.EVT_BUTTON, self.on_low_vision_options)
        root.Add(
            self.low_vision_options_button,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            10,
        )

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

        self.restore_defaults_button = wx.Button(
            self,
            label=tr("إرجاع الإعدادات إلى الوضع الافتراضي"),
        )
        set_accessible(
            self.restore_defaults_button,
            "إرجاع الإعدادات إلى الوضع الافتراضي",
            "يعيد إعدادات البرنامج إلى قيمها الافتراضية مع الاحتفاظ بلغة البرنامج والحسابات.",
        )
        self.restore_defaults_button.Bind(wx.EVT_BUTTON, self.on_restore_defaults)
        root.Add(
            self.restore_defaults_button,
            0,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            10,
        )

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
        self.scroller = set_scrollable_dialog_content(self, root)
        localize_window(self)
        self.scroller.FitInside()
        wx.CallAfter(self.language_intro.SetFocus)

    def selected_message_translation_language(self) -> str:
        selection = self.message_translation_language_box.GetSelection()
        if 0 <= selection < len(self.message_language_codes):
            return self.message_language_codes[selection]
        return self.settings.message_translation_language or self.settings.language

    def selected_settings(self) -> ProgramSettings:
        selected_events = normalize_event_ids(self.notification_event_ids)
        return ProgramSettings(
            message_translation_language=self.selected_message_translation_language(),
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
            search_mode=self.value_for_index(
                getattr(self, "search_mode_box", None),
                SEARCH_MODE_CHOICES,
                self.settings.search_mode,
            ),
            translation_data_notice_accepted=(
                self.settings.translation_data_notice_accepted
            ),
            message_translation_language_selected=True,
            spoken_notification_level=self.value_for_index(
                self.notification_level_box,
                SPOKEN_NOTIFICATION_LEVEL_CHOICES,
                self.settings.spoken_notification_level,
            ),
            spoken_notification_events=selected_events or [],
            last_selected_account_id=self.settings.last_selected_account_id,
            compose_translation_languages=list(self.settings.compose_translation_languages),
            low_vision_font_scale=self.settings.low_vision_font_scale,
            low_vision_high_contrast=self.settings.low_vision_high_contrast,
            low_vision_cursor_size=self.settings.low_vision_cursor_size,
            low_vision_focus_highlight=self.settings.low_vision_focus_highlight,
            low_vision_custom_colours=self.settings.low_vision_custom_colours,
            low_vision_text_colour=self.settings.low_vision_text_colour,
            low_vision_background_colour=self.settings.low_vision_background_colour,
            program_sounds_enabled=(
                self.program_sounds_box.GetValue()
                if hasattr(self, "program_sounds_box")
                else self.settings.program_sounds_enabled
            ),
            program_sound_events=normalize_sound_event_ids(
                getattr(self, "sound_event_ids", self.settings.program_sound_events)
            ),
            program_sound_files=normalize_custom_sound_files(
                getattr(self, "sound_files", self.settings.program_sound_files)
            ),
        )

    def on_customize_sounds(self, _event: wx.Event) -> None:
        sound_settings = replace(
            self.settings,
            program_sound_files=dict(self.sound_files),
        )
        dialog = ProgramSoundsDialog(self, sound_settings, self.sound_event_ids)
        try:
            if dialog.ShowModal() == wx.ID_OK:
                self.sound_event_ids = dialog.selected_event_ids()
                self.sound_files = dialog.selected_sound_files()
        finally:
            dialog.Destroy()
        self.customize_sounds_button.SetFocus()

    def on_low_vision_options(self, _event: wx.Event) -> None:
        dialog = LowVisionOptionsDialog(self, self.settings)
        try:
            if dialog.ShowModal() == wx.ID_OK:
                self.settings = dialog.selected_settings()
        finally:
            dialog.Destroy()
        self.low_vision_options_button.SetFocus()

    def on_notification_level_changed(self, _event: wx.Event) -> None:
        level = self.value_for_index(
            self.notification_level_box,
            SPOKEN_NOTIFICATION_LEVEL_CHOICES,
            self.settings.spoken_notification_level,
        )
        self.notification_event_ids = preset_event_ids(level)
        if level == NOTIFICATION_LEVEL_CUSTOM:
            wx.MessageBox(
                tr(
                    "اخترت المستوى المخصص. جميع إجراءات النطق غير محددة الآن. "
                    "حدد الإجراءات التي تريد أن ينطقها البرنامج ثم اضغط حفظ."
                ),
                tr("تخصيص نطق الإجراءات"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            self.on_customize_notifications(_event)

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

    def on_restore_defaults(self, _event: wx.Event) -> None:
        dialog = wx.MessageDialog(
            self,
            tr(
                "سيتم إرجاع جميع إعدادات البرنامج إلى الوضع الافتراضي مع الاحتفاظ "
                "بلغة البرنامج الحالية وحسابات البريد. هل تريد المتابعة؟"
            ),
            tr("استعادة الإعدادات الافتراضية"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
        )
        if hasattr(dialog, "SetYesNoLabels"):
            dialog.SetYesNoLabels(tr("أوافق"), tr("كلا"))
        try:
            confirmed = dialog.ShowModal() == wx.ID_YES
        finally:
            dialog.Destroy()
        if not confirmed:
            self.restore_defaults_button.SetFocus()
            return

        defaults = ProgramSettings()
        self.viewer_box.SetSelection(
            self.index_for_value(VIEWER_CHOICES, defaults.message_viewer)
        )
        self.message_read_mode_box.SetSelection(
            self.index_for_value(
                MESSAGE_READ_MODE_CHOICES,
                defaults.message_read_mode,
            )
        )
        self.translation_mode_box.SetSelection(
            self.index_for_value(
                TRANSLATION_MODE_CHOICES,
                defaults.translation_mode,
            )
        )
        if hasattr(self, "search_mode_box"):
            self.search_mode_box.SetSelection(
                self.index_for_value(SEARCH_MODE_CHOICES, defaults.search_mode)
            )
        if hasattr(self, "message_translation_language_box"):
            language = self.value_for_index(self.language_box, LANGUAGE_CHOICES, self.settings.language)
            self.message_translation_language_box.SetSelection(self.message_language_codes.index(language))
        self.notification_level_box.SetSelection(
            self.index_for_value(
                SPOKEN_NOTIFICATION_LEVEL_CHOICES,
                defaults.spoken_notification_level,
            )
        )
        self.notification_event_ids = preset_event_ids(
            defaults.spoken_notification_level
        )
        if hasattr(self, "program_sounds_box"):
            self.program_sounds_box.SetValue(defaults.program_sounds_enabled)
        self.sound_event_ids = set(
            normalize_sound_event_ids(defaults.program_sound_events)
        )
        self.sound_files = {}
        self.theme_box.SetSelection(1 if defaults.theme == THEME_DARK else 0)
        self.settings.low_vision_font_scale = defaults.low_vision_font_scale
        self.settings.low_vision_high_contrast = defaults.low_vision_high_contrast
        self.settings.low_vision_cursor_size = defaults.low_vision_cursor_size
        self.settings.low_vision_focus_highlight = defaults.low_vision_focus_highlight
        self.settings.low_vision_custom_colours = defaults.low_vision_custom_colours
        self.settings.low_vision_text_colour = defaults.low_vision_text_colour
        self.settings.low_vision_background_colour = defaults.low_vision_background_colour
        self.settings.translation_data_notice_accepted = (
            defaults.translation_data_notice_accepted
        )
        self.settings.message_translation_language_selected = (
            defaults.message_translation_language_selected
        )
        self.restore_defaults_button.SetFocus()

    def value_for_index(self, choice: wx.Choice | None, mapping: dict[str, str], fallback: str) -> str:
        if choice is None:
            return fallback
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
