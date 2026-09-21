import urllib.error
import unittest
from unittest.mock import patch

from accessible_mail import translation


class TranslationRateLimitTests(unittest.TestCase):
    @patch.object(translation, '_rate_limit_until', 0.0)
    @patch.object(translation, 'trusted_https_context')
    @patch.object(translation.urllib.request, 'urlopen')
    def test_429_stops_retries_and_following_requests(self, request, context):
        request.side_effect = urllib.error.HTTPError(
            'https://translate.googleapis.com/', 429, 'Too Many Requests', {'Retry-After': '120'}, None)
        with patch.object(translation.time, 'monotonic', return_value=100.0):
            with self.assertRaisesRegex(translation.TranslationRateLimitError, '429'):
                translation.translate_text_with_google('test')
            with self.assertRaises(translation.TranslationRateLimitError):
                translation.translate_text_with_google('another description')
        request.assert_called_once()
        self.assertEqual(translation._rate_limit_until, 220.0)

    @patch.object(translation, '_rate_limit_until', 100.0)
    def test_cooldown_expires(self):
        with patch.object(translation.time, 'monotonic', return_value=101.0):
            translation.check_translation_rate_limit()


if __name__ == '__main__':
    unittest.main()
