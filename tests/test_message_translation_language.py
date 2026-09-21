import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import wx

from accessible_mail.config import ProgramSettings, normalize_settings
from accessible_mail.dialogs import MessageTranslationLanguageDialog
from accessible_mail.translation_languages import TRANSLATION_LANGUAGES, MESSAGE_PRIORITY_CODES, message_language_codes


class MessageTranslationLanguageTests(unittest.TestCase):
    def test_destination_is_independent_of_interface(self):
        settings = normalize_settings(ProgramSettings(language="en", message_translation_language="bn"))
        self.assertEqual(settings.language, "en")
        self.assertEqual(settings.message_translation_language, "bn")

    def test_old_or_invalid_settings_keep_previous_behavior(self):
        for code in ("", "invalid"):
            settings = normalize_settings(ProgramSettings(language="fr", message_translation_language=code))
            self.assertEqual(settings.message_translation_language, "fr")

    def test_twenty_priority_languages_and_complete_unique_catalog(self):
        codes = message_language_codes()
        self.assertEqual(len(MESSAGE_PRIORITY_CODES), 20)
        self.assertEqual(codes[:20], list(MESSAGE_PRIORITY_CODES))
        self.assertIn("bn", codes[:20])
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(set(codes), set(TRANSLATION_LANGUAGES))

    def test_enter_accepts_the_focused_language(self):
        dialog = SimpleNamespace(
            languages=Mock(),
            EndModal=Mock(),
        )
        dialog.languages.GetSelection.return_value = 2
        event = SimpleNamespace(GetKeyCode=lambda: wx.WXK_RETURN, Skip=Mock())

        MessageTranslationLanguageDialog.on_key(dialog, event)

        dialog.EndModal.assert_called_once_with(wx.ID_OK)
        event.Skip.assert_not_called()

    def test_single_mouse_click_accepts_the_clicked_language(self):
        dialog = SimpleNamespace(
            languages=Mock(),
            EndModal=Mock(),
        )
        dialog.languages.HitTest.return_value = 7
        event = SimpleNamespace(GetPosition=lambda: (4, 8), Skip=Mock())

        MessageTranslationLanguageDialog.on_mouse_select(dialog, event)

        dialog.languages.SetSelection.assert_called_once_with(7)
        dialog.EndModal.assert_called_once_with(wx.ID_OK)
        event.Skip.assert_not_called()
