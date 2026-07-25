from __future__ import annotations

import unittest

from accessible_mail.i18n import LANGUAGE_ARABIC, LANGUAGE_ENGLISH, set_language, tr


class TranslationTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_language(LANGUAGE_ARABIC)

    def test_static_and_dynamic_interface_text_translates_to_english(self) -> None:
        set_language(LANGUAGE_ENGLISH)

        self.assertEqual(tr("الإعدادات"), "Settings")
        self.assertEqual(tr("وصلت 3 رسائل جديدة إلى الوارد."), "3 new messages arrived in Inbox.")

    def test_interface_text_can_switch_back_to_arabic(self) -> None:
        set_language(LANGUAGE_ARABIC)

        self.assertEqual(tr("Settings"), "الإعدادات")
        self.assertEqual(tr("English"), "الإنجليزية")


if __name__ == "__main__":
    unittest.main()
