from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import wx

from accessible_mail import config
from accessible_mail.dialogs import LowVisionOptionsDialog, SettingsDialog
from accessible_mail.i18n import set_language, tr
from accessible_mail.mail_page import MailPage
from accessible_mail.visual_accessibility import visual_palette


class LowVisionSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = wx.GetApp() or wx.App(False)

    def test_low_vision_options_round_trip(self) -> None:
        settings = config.ProgramSettings(
            low_vision_font_scale=175,
            low_vision_high_contrast=True,
            low_vision_cursor_size="extra_large",
            low_vision_focus_highlight=True,
            low_vision_custom_colours=True,
            low_vision_text_colour="#FFF000",
            low_vision_background_colour="#001122",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            with patch("accessible_mail.config.settings_path", return_value=path):
                config.save_settings(settings)
                loaded = config.load_settings()

        self.assertEqual(loaded.low_vision_font_scale, 175)
        self.assertTrue(loaded.low_vision_high_contrast)
        self.assertEqual(loaded.low_vision_cursor_size, "extra_large")
        self.assertTrue(loaded.low_vision_focus_highlight)
        self.assertTrue(loaded.low_vision_custom_colours)
        self.assertEqual(loaded.low_vision_text_colour, "#FFF000")
        self.assertEqual(loaded.low_vision_background_colour, "#001122")

    def test_invalid_low_vision_values_return_to_safe_defaults(self) -> None:
        settings = config.normalize_settings(
            config.ProgramSettings(
                low_vision_font_scale=999,
                low_vision_cursor_size="huge",
                low_vision_text_colour="invalid",
                low_vision_background_colour="also-invalid",
            )
        )

        self.assertEqual(settings.low_vision_font_scale, 100)
        self.assertEqual(settings.low_vision_cursor_size, "normal")
        self.assertEqual(settings.low_vision_text_colour, "#FFFFFF")
        self.assertEqual(settings.low_vision_background_colour, "#000000")

    def test_high_contrast_takes_priority_over_custom_colours(self) -> None:
        settings = config.ProgramSettings(
            low_vision_high_contrast=True,
            low_vision_custom_colours=True,
            low_vision_text_colour="#112233",
            low_vision_background_colour="#445566",
        )

        background, foreground, surface = visual_palette(settings)

        self.assertEqual(background.GetAsString(wx.C2S_HTML_SYNTAX), "#000000")
        self.assertEqual(foreground.GetAsString(wx.C2S_HTML_SYNTAX), "#FFFFFF")
        self.assertEqual(surface.GetAsString(wx.C2S_HTML_SYNTAX), "#000000")

    def test_custom_colours_are_used_when_high_contrast_is_off(self) -> None:
        settings = config.ProgramSettings(
            low_vision_custom_colours=True,
            low_vision_text_colour="#F0E000",
            low_vision_background_colour="#102030",
        )

        background, foreground, _surface = visual_palette(settings)

        self.assertEqual(background.GetAsString(wx.C2S_HTML_SYNTAX), "#102030")
        self.assertEqual(foreground.GetAsString(wx.C2S_HTML_SYNTAX), "#F0E000")


class LowVisionDialogTests(unittest.TestCase):
    def test_visual_options_use_independent_checkboxes_and_space(self) -> None:
        _app = wx.App.Get() or wx.App(False)
        parent = wx.Frame(None)
        self.addCleanup(parent.Destroy)
        dialog = LowVisionOptionsDialog(parent, config.ProgramSettings())
        self.addCleanup(dialog.Destroy)
        options = dialog.visual_option_list

        self.assertEqual(options.GetItemCount(), 3)
        self.assertFalse(options.IsItemChecked(0))
        self.assertFalse(options.IsItemChecked(2))
        self.assertFalse(dialog.text_colour_picker.IsEnabled())
        options.CheckItem(2, True)
        self.assertTrue(dialog.text_colour_picker.IsEnabled())
        options.CheckItem(0, True)
        self.assertFalse(dialog.text_colour_picker.IsEnabled())
        self.assertTrue(dialog.colour_mode_note.GetLabel())
        tab_event = Mock()
        tab_event.GetKeyCode.return_value = wx.WXK_TAB
        tab_event.ControlDown.return_value = False
        tab_event.AltDown.return_value = False
        tab_event.ShiftDown.return_value = False
        save_button = dialog.FindWindow(wx.ID_OK)
        with patch.object(save_button, "SetFocus") as focus_save:
            dialog.on_visual_option_key(tab_event)
        focus_save.assert_called_once_with()

        options.SetItemState(1, wx.LIST_STATE_FOCUSED, wx.LIST_STATE_FOCUSED)
        event = Mock()
        event.GetKeyCode.return_value = wx.WXK_SPACE
        event.ControlDown.return_value = False
        event.AltDown.return_value = False
        event.ShiftDown.return_value = False
        dialog.on_visual_option_key(event)
        self.assertTrue(options.IsItemChecked(1))
        self.assertTrue(dialog.selected_settings().low_vision_focus_highlight)
        self.assertIn("#", dialog.text_colour_picker.GetName())
        dialog.text_colour_picker.SetColour(wx.Colour("#123456"))
        dialog.update_colour_picker_names()
        self.assertIn("#123456", dialog.text_colour_picker.GetName())

    def test_settings_contains_one_low_vision_options_button(self) -> None:
        source = inspect.getsource(SettingsDialog._build)

        self.assertIn("self.low_vision_options_button = wx.Button", source)
        self.assertIn("ميزات وخيارات ضعاف البصر", source)
        self.assertIn("self.on_low_vision_options", source)

    def test_dialog_returns_every_visual_option(self) -> None:
        def colour(value):
            return SimpleNamespace(GetAsString=lambda _format: value)
        dialog = SimpleNamespace(
            settings=config.ProgramSettings(),
            font_scale_box=SimpleNamespace(GetSelection=lambda: 2),
            cursor_size_box=SimpleNamespace(GetSelection=lambda: 1),
            visual_option_list=SimpleNamespace(IsItemChecked=lambda index: index in {0, 1, 2}),
            text_colour_picker=SimpleNamespace(GetColour=lambda: colour("#ABCDEF")),
            background_colour_picker=SimpleNamespace(GetColour=lambda: colour("#123456")),
        )

        selected = LowVisionOptionsDialog.selected_settings(dialog)

        self.assertEqual(selected.low_vision_font_scale, 150)
        self.assertTrue(selected.low_vision_high_contrast)
        self.assertEqual(selected.low_vision_cursor_size, "large")
        self.assertTrue(selected.low_vision_focus_highlight)
        self.assertTrue(selected.low_vision_custom_colours)
        self.assertEqual(selected.low_vision_text_colour, "#ABCDEF")
        self.assertEqual(selected.low_vision_background_colour, "#123456")

    def test_mail_page_receives_visual_settings(self) -> None:
        page = SimpleNamespace(
            apply_viewer_colours=Mock(),
            set_expanded_viewer=Mock(),
            set_viewer_text=Mock(),
            _expanded_viewer=False,
            viewer_text="message",
        )
        settings = config.ProgramSettings(
            low_vision_font_scale=200,
            low_vision_high_contrast=True,
            low_vision_custom_colours=True,
            low_vision_text_colour="#FFFF00",
            low_vision_background_colour="#000011",
        )

        MailPage.set_visual_accessibility(page, settings)

        self.assertEqual(page.low_vision_font_scale, 200)
        self.assertTrue(page.low_vision_high_contrast)
        self.assertTrue(page.low_vision_custom_colours)
        page.apply_viewer_colours.assert_called_once_with()
        page.set_expanded_viewer.assert_called_once_with(False)
        page.set_viewer_text.assert_called_once_with("message")

    def test_visible_feature_name_is_translated_in_every_program_language(self) -> None:
        languages = ("en", "fr", "es", "tr", "hi", "zh-CN", "ru", "ja", "de")
        try:
            for language in languages:
                set_language(language)
                self.assertNotEqual(
                    tr("ميزات وخيارات ضعاف البصر"),
                    "ميزات وخيارات ضعاف البصر",
                    language,
                )
                self.assertNotEqual(tr("خيارات العرض"), "خيارات العرض", language)
        finally:
            set_language("ar")

    def test_enlarged_settings_dialog_uses_scrollable_content(self) -> None:
        source = inspect.getsource(SettingsDialog._build)
        low_vision_source = inspect.getsource(LowVisionOptionsDialog.__init__)

        self.assertIn("set_scrollable_dialog_content", source)
        self.assertIn("set_scrollable_dialog_content", low_vision_source)


if __name__ == "__main__":
    unittest.main()
