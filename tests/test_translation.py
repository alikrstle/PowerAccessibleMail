from __future__ import annotations

import json
import unittest
import urllib.error
from unittest.mock import Mock, patch

from accessible_mail.email_service import MailError
from accessible_mail.translation import translate_text_with_google


class TranslationTests(unittest.TestCase):
    @staticmethod
    def response_with_translation(text: str) -> Mock:
        response = Mock()
        response.read.return_value = json.dumps([[[text]]]).encode("utf-8")
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    @patch("accessible_mail.translation.time.sleep")
    @patch("accessible_mail.translation.urllib.request.urlopen")
    def test_transient_failure_is_retried(
        self,
        urlopen: Mock,
        sleep: Mock,
    ) -> None:
        urlopen.side_effect = [
            urllib.error.URLError("temporary"),
            self.response_with_translation("مرحبا"),
        ]

        translated = translate_text_with_google("hello", "ar")

        self.assertEqual(translated, "مرحبا")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(0.6)

    @patch("accessible_mail.translation.time.sleep")
    @patch("accessible_mail.translation.urllib.request.urlopen")
    def test_repeated_failure_raises_localized_mail_error(
        self,
        urlopen: Mock,
        sleep: Mock,
    ) -> None:
        urlopen.side_effect = urllib.error.URLError("offline")

        with self.assertRaisesRegex(MailError, "تعذر الحصول على ترجمة"):
            translate_text_with_google("hello", "ar")

        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(0.6)


if __name__ == "__main__":
    unittest.main()
