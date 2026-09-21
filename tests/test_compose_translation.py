import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from accessible_mail.compose_translation import ComposeTranslationMixin
from accessible_mail.config import ProgramSettings, load_settings, save_settings


class ComposeTranslationTests(unittest.TestCase):
    def test_language_preferences_round_trip_and_validate(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("accessible_mail.config.settings_path", return_value=Path(directory) / "settings.json"):
                save_settings(ProgramSettings(compose_translation_languages=["fr", "ar", "fr", "invalid", 42]))
                self.assertEqual(load_settings().compose_translation_languages, ["fr", "ar"])

    @patch("accessible_mail.compose_translation.announce_to_screen_reader")
    def test_success_uses_undoable_replace(self, announce):
        control = Mock()
        control.GetValue.return_value = "original"
        control.GetLastPosition.return_value = 8
        owner = SimpleNamespace(_translation_closed=False, _translation_pending={control}, _text_revisions={control: 3})
        ComposeTranslationMixin.finish_compose_translation(owner, control, "original", 3, "translated", "")
        control.Replace.assert_called_once_with(0, 8, "translated")
        control.SetFocus.assert_not_called()

    @patch("accessible_mail.compose_translation.announce_to_screen_reader")
    def test_edit_even_if_undone_prevents_late_replacement(self, announce):
        control = Mock()
        control.GetValue.return_value = "original"
        owner = SimpleNamespace(_translation_closed=False, _translation_pending={control}, _text_revisions={control: 4})
        ComposeTranslationMixin.finish_compose_translation(owner, control, "original", 3, "translated", "")
        control.Replace.assert_not_called()

    def test_closed_dialog_does_not_touch_destroyed_controls(self):
        control = Mock()
        ComposeTranslationMixin.finish_compose_translation(SimpleNamespace(_translation_closed=True), control, "text", 1, "translated", "")
        self.assertEqual(control.mock_calls, [])

    @patch("accessible_mail.compose_translation.wx.MessageBox")
    @patch("accessible_mail.compose_translation.announce_to_screen_reader")
    def test_translation_error_preserves_text(self, announce, message_box):
        control = Mock()
        owner = SimpleNamespace(_translation_closed=False, _translation_pending={control})
        ComposeTranslationMixin.finish_compose_translation(owner, control, "original", 1, "", "network error")
        control.Replace.assert_not_called()
        message_box.assert_called_once()

    @patch("accessible_mail.compose_translation.threading.Thread")
    def test_cancelled_consent_does_not_send_text(self, thread):
        control = Mock()
        control.GetValue.return_value = "private draft"
        parent = SimpleNamespace(confirm_translation_data_transfer=lambda: False)
        owner = SimpleNamespace(_translation_closed=False, _translation_pending=set(), GetParent=lambda: parent)
        ComposeTranslationMixin.start_compose_translation(owner, control, "fr")
        thread.assert_not_called()
