from __future__ import annotations

import unittest
from pathlib import Path

from accessible_mail.guide import load_program_guide
from accessible_mail.i18n import (
    ENGLISH_TRANSLATIONS,
    LANGUAGE_ARABIC,
    LANGUAGE_ENGLISH,
    LANGUAGE_FRENCH,
    _DYNAMIC_ENGLISH,
    set_language,
    tr,
)
from accessible_mail.i18n_fr import (
    FRENCH_DYNAMIC_TEMPLATES,
    FRENCH_TRANSLATIONS,
)


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
        self.assertEqual(
            tr("معمارية مثبت التحديث لا تطابق معمارية البرنامج الحالي."),
            "The update installer architecture does not match the running application.",
        )
        self.assertEqual(tr("صورة 2: Company logo"), "Image 2: Company logo")
        self.assertEqual(tr("تواصل معنا"), "Contact us")
        self.assertEqual(
            tr("إرسال رسالة إلى المطور عبر PowerAccessibleMail"),
            "Email the developer using PowerAccessibleMail",
        )
        self.assertEqual(
            tr(
                "المرفق invoice.exe قد يشغّل أو يحتوي على تعليمات برمجية ضارة.\n\n"
                "هل تريد فتحه رغم ذلك؟"
            ),
            (
                "The attachment invoice.exe may run commands or contain malicious code.\n\n"
                "Do you want to open it anyway?"
            ),
        )

    def test_interface_text_can_switch_back_to_arabic(self) -> None:
        set_language(LANGUAGE_ARABIC)

        self.assertEqual(tr("Settings"), "الإعدادات")
        self.assertEqual(tr("English"), "الإنجليزية")

    def test_static_and_dynamic_interface_text_translates_to_french(self) -> None:
        set_language(LANGUAGE_FRENCH)

        self.assertEqual(tr("الإعدادات"), "Paramètres")
        self.assertEqual(
            tr("وصلت 3 رسائل جديدة إلى الوارد."),
            "3 nouveaux messages sont arrivés dans la boîte de réception.",
        )
        self.assertEqual(
            tr("عدد الرسائل المحددة: 25."),
            "25 message(s) sélectionné(s).",
        )
        self.assertEqual(
            tr("معمارية مثبت التحديث لا تطابق معمارية البرنامج الحالي."),
            (
                "L'architecture du programme d'installation de la mise à jour ne "
                "correspond pas à l'application en cours d'exécution."
            ),
        )
        self.assertEqual(tr("صورة 2: Company logo"), "Image 2\xa0: Company logo")
        self.assertEqual(tr("تواصل معنا"), "Nous contacter")

    def test_interface_can_switch_from_french_to_other_languages(self) -> None:
        set_language(LANGUAGE_ENGLISH)
        self.assertEqual(tr("Paramètres"), "Settings")

        set_language(LANGUAGE_ARABIC)
        self.assertEqual(tr("Paramètres"), "الإعدادات")

    def test_french_catalog_covers_the_full_english_catalog(self) -> None:
        self.assertEqual(set(FRENCH_TRANSLATIONS), set(ENGLISH_TRANSLATIONS))
        self.assertEqual(len(FRENCH_DYNAMIC_TEMPLATES), len(_DYNAMIC_ENGLISH))

    def test_french_program_guide_uses_requested_version(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        guide = load_program_guide(LANGUAGE_FRENCH, "9.8.7", project_root)

        self.assertIn("Version 9.8.7", guide)
        self.assertIn("l'arabe l'anglais ou le français", guide)
        self.assertIn("Utiliser la visionneuse des éléments étape par étape", guide)
        self.assertIn("Ajouter une pièce jointe", guide)
        self.assertNotIn("Version 1.2.14", guide)

    def test_all_program_guides_cover_detailed_attachment_workflows(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        expected_phrases = {
            LANGUAGE_ARABIC: (
                "استخدام مستعرض العناصر خطوة بخطوة",
                "إنشاء رسالة وإضافة مرفقات صادرة",
            ),
            LANGUAGE_ENGLISH: (
                "Use the item viewer step by step",
                "Compose a message and add outgoing attachments",
            ),
            LANGUAGE_FRENCH: (
                "Utiliser la visionneuse des éléments étape par étape",
                "Composer un message et ajouter des pièces jointes sortantes",
            ),
        }

        for language, phrases in expected_phrases.items():
            with self.subTest(language=language):
                guide = load_program_guide(language, "9.8.7", project_root)
                for phrase in phrases:
                    self.assertIn(phrase, guide)
                self.assertNotIn("Manage attachments and links", guide)


if __name__ == "__main__":
    unittest.main()
