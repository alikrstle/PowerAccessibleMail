from __future__ import annotations

import unittest

import wx

from accessible_mail.config import ProgramSettings
from accessible_mail.dialogs import LowVisionOptionsDialog, SettingsDialog
from accessible_mail.i18n import tr


class SettingsAccessibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = wx.App.Get() or wx.App(False)
        self.parent = wx.Frame(None)
        self.addCleanup(self.parent.Destroy)

    def assert_choice_announces_own_name_and_value(self, control: wx.Choice, name: str) -> None:
        accessible = control.GetAccessible()
        self.assertEqual(accessible.GetName(0), (wx.ACC_OK, tr(name)))
        self.assertEqual(accessible.GetValue(0), (wx.ACC_OK, control.GetStringSelection()))

    def test_settings_choices_report_matching_names_and_values(self) -> None:
        dialog = SettingsDialog(self.parent, ProgramSettings())
        self.addCleanup(dialog.Destroy)
        choices = (
            (dialog.language_box, "لغة البرنامج"),
            (dialog.viewer_box, "نوع مستعرض الرسائل"),
            (dialog.message_read_mode_box, "طريقة قراءة الرسائل"),
            (dialog.search_mode_box, "طريقة البحث في الرسائل"),
            (dialog.translation_mode_box, "نمط الترجمة"),
            (dialog.message_translation_language_box, "اختر اللغة التي سيتم ترجمة رسائل البريد إليها"),
            (dialog.notification_level_box, "مستوى نطق إجراءات البرنامج"),
        )
        for control, name in choices:
            with self.subTest(name=name):
                self.assert_choice_announces_own_name_and_value(control, name)
        dialog.language_box.SetSelection(1)
        self.assert_choice_announces_own_name_and_value(dialog.language_box, "لغة البرنامج")

    def test_settings_initial_focus_is_language_intro_before_choice(self) -> None:
        from unittest.mock import patch
        with patch("accessible_mail.dialogs.wx.CallAfter") as queued:
            dialog = SettingsDialog(self.parent, ProgramSettings())
        self.addCleanup(dialog.Destroy)
        queued.assert_called_with(dialog.language_intro.SetFocus)
        self.assertFalse(dialog.language_intro.IsEditable())
        self.assertEqual(dialog.language_intro.GetName(), tr("لغة البرنامج"))
        self.assertIs(dialog.language_intro.GetNextSibling(), dialog.language_box)

    def test_low_vision_choices_report_matching_names_and_values(self) -> None:
        dialog = LowVisionOptionsDialog(self.parent, ProgramSettings())
        self.addCleanup(dialog.Destroy)
        self.assert_choice_announces_own_name_and_value(dialog.font_scale_box, "حجم الخط وعناصر الواجهة")
        self.assert_choice_announces_own_name_and_value(dialog.cursor_size_box, "حجم المؤشر داخل البرنامج")
        self.assertEqual(dialog.visual_option_list.GetName(), tr("خيارات العرض"))
        self.assertEqual(dialog.visual_option_list.GetItemCount(), 3)
        self.assertEqual(
            [dialog.visual_option_list.GetItemText(index) for index in range(3)],
            [tr(label) for label in dialog.visual_option_labels],
        )


if __name__ == "__main__":
    unittest.main()
