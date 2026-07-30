from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import wx

from .accessibility import announce_to_screen_reader, set_accessible
from .config import ProgramSettings, THEME_DARK, THEME_LIGHT
from .i18n import tr
from .ui_constants import (
    LANGUAGE_CHOICES,
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
        super().__init__(parent, title=title, size=(680, 560))
        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.VERTICAL)

        self.to_address = self._row(panel, root, "إلى:", to_address)
        self.subject = self._row(panel, root, "الموضوع:", subject)

        root.Add(wx.StaticText(panel, label="المحتوى:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
        self.body = wx.TextCtrl(panel, value=body, style=wx.TE_MULTILINE)
        set_accessible(self.body, "محتوى الرسالة", "اكتب محتوى البريد الإلكتروني هنا")
        root.Add(self.body, 1, wx.EXPAND | wx.ALL, 8)

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

    def values(self) -> tuple[str, str, str]:
        return (
            self.to_address.GetValue().strip(),
            self.subject.GetValue().strip(),
            self.body.GetValue(),
        )


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


class SettingsDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, settings: ProgramSettings) -> None:
        super().__init__(parent, title="الإعدادات", size=(560, 500))
        self.settings = replace(settings)
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
        return ProgramSettings(
            language=self.value_for_index(self.language_box, LANGUAGE_CHOICES, self.settings.language),
            message_viewer=self.value_for_index(self.viewer_box, VIEWER_CHOICES, self.settings.message_viewer),
            theme=THEME_DARK if self.theme_box.GetSelection() == 1 else THEME_LIGHT,
            translation_mode=self.value_for_index(
                self.translation_mode_box,
                TRANSLATION_MODE_CHOICES,
                self.settings.translation_mode,
            ),
        )

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
