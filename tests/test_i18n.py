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
        self.assertEqual(
            tr("لا يوجد إصدار منشور في GitHub Releases حتى الآن."),
            "No release has been published in GitHub Releases yet.",
        )
        self.assertEqual(
            tr("تعذر الاتصال بـ GitHub Releases: HTTP 403"),
            "Unable to contact GitHub Releases: HTTP 403",
        )
        self.assertEqual(
            tr("عدد الرسائل المحددة: 25."),
            "25 message(s) selected.",
        )
        self.assertEqual(
            tr("هل تريد حذف 25 رسالة وإرسالها إلى سلة المحذوفات؟"),
            "Do you want to delete 25 message(s) and send them to Trash?",
        )

    def test_interface_text_can_switch_back_to_arabic(self) -> None:
        set_language(LANGUAGE_ARABIC)

        self.assertEqual(tr("Settings"), "الإعدادات")
        self.assertEqual(tr("English"), "الإنجليزية")


if __name__ == "__main__":
    unittest.main()
