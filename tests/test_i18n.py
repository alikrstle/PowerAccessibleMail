from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from accessible_mail.guide import load_program_guide
from accessible_mail.i18n import (
    ENGLISH_TRANSLATIONS,
    LANGUAGE_ARABIC,
    LANGUAGE_ENGLISH,
    LANGUAGE_FRENCH,
    LANGUAGE_GERMAN,
    LANGUAGE_HINDI,
    LANGUAGE_JAPANESE,
    LANGUAGE_RUSSIAN,
    LANGUAGE_SIMPLIFIED_CHINESE,
    LANGUAGE_SPANISH,
    LANGUAGE_TURKISH,
    _DYNAMIC_ENGLISH,
    set_language,
    tr,
)
from accessible_mail.i18n_fr import (
    FRENCH_DYNAMIC_TEMPLATES,
    FRENCH_TRANSLATIONS,
)
from accessible_mail.i18n_hi import HINDI_DYNAMIC_TEMPLATES, HINDI_TRANSLATIONS
from accessible_mail.i18n_es import SPANISH_DYNAMIC_TEMPLATES, SPANISH_TRANSLATIONS
from accessible_mail.i18n_tr import TURKISH_DYNAMIC_TEMPLATES, TURKISH_TRANSLATIONS
from accessible_mail.i18n_zh_cn import (
    SIMPLIFIED_CHINESE_DYNAMIC_TEMPLATES,
    SIMPLIFIED_CHINESE_TRANSLATIONS,
)
from accessible_mail.i18n_ru import RUSSIAN_DYNAMIC_TEMPLATES, RUSSIAN_TRANSLATIONS
from accessible_mail.i18n_ja import JAPANESE_DYNAMIC_TEMPLATES, JAPANESE_TRANSLATIONS
from accessible_mail.i18n_de import GERMAN_DYNAMIC_TEMPLATES, GERMAN_TRANSLATIONS


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
        self.assertEqual(tr("القناة الدولية"), "International channel")
        self.assertEqual(tr("القناة العربية"), "Arabic channel")
        self.assertEqual(tr("سياسة الخصوصية"), "Privacy policy")
        self.assertEqual(tr("شروط الاستخدام"), "Terms of use")
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
        self.assertEqual(tr("مقروءة"), "Lu")
        self.assertEqual(tr("غير مقروءة"), "Non lu")
        self.assertEqual(tr("تعليم كمقروءة"), "Marquer comme lu")
        self.assertEqual(tr("تواصل معنا"), "Nous contacter")
        self.assertEqual(tr("القناة الدولية"), "Chaîne internationale")
        self.assertEqual(tr("القناة العربية"), "Chaîne arabe")
        self.assertEqual(tr("سياسة الخصوصية"), "Politique de confidentialité")
        self.assertEqual(tr("شروط الاستخدام"), "Conditions d'utilisation")

    def test_interface_can_switch_from_french_to_other_languages(self) -> None:
        set_language(LANGUAGE_ENGLISH)
        self.assertEqual(tr("Paramètres"), "Settings")

        set_language(LANGUAGE_ARABIC)
        self.assertEqual(tr("Paramètres"), "الإعدادات")

    def test_new_interface_languages_translate_static_and_dynamic_text(self) -> None:
        expected = {
            LANGUAGE_SPANISH: (
                "Configuración",
                "3 nuevos mensajes han llegado a la bandeja de entrada.",
                "Marcar como no leído",
            ),
            LANGUAGE_TURKISH: (
                "Ayarlar",
                "3 yeni mesaj Gelen Kutusu'na geldi.",
                "Okunmadı olarak işaretle",
            ),
            LANGUAGE_HINDI: (
                "सेटिंग्स",
                "3 नए मैसेज इनबॉक्स में आए।",
                "अपठित चिह्नित करें",
            ),
            LANGUAGE_SIMPLIFIED_CHINESE: (
                "设置",
                "3 新邮件到达收件箱。",
                "标记为未读",
            ),
            LANGUAGE_RUSSIAN: (
                "Настройки",
                "В папку «Входящие» поступило 3 новых сообщений.",
                "Отметить как непрочитанное",
            ),
            LANGUAGE_JAPANESE: (
                "設定",
                "3 件の新しいメッセージが受信トレイに到着しました。",
                "未読にする",
            ),
            LANGUAGE_GERMAN: (
                "Einstellungen",
                "Im Posteingang sind 3 neue Nachrichten eingegangen.",
                "Als ungelesen markieren",
            ),
        }
        for language, phrases in expected.items():
            with self.subTest(language=language):
                set_language(language)
                self.assertEqual(tr("الإعدادات"), phrases[0])
                self.assertEqual(tr("وصلت 3 رسائل جديدة إلى الوارد."), phrases[1])
                self.assertEqual(tr("تعليم كغير مقروءة"), phrases[2])

    def test_new_language_catalogs_cover_the_full_english_catalog(self) -> None:
        for exact_catalog, dynamic_catalog in (
            (SPANISH_TRANSLATIONS, SPANISH_DYNAMIC_TEMPLATES),
            (TURKISH_TRANSLATIONS, TURKISH_DYNAMIC_TEMPLATES),
            (HINDI_TRANSLATIONS, HINDI_DYNAMIC_TEMPLATES),
            (SIMPLIFIED_CHINESE_TRANSLATIONS, SIMPLIFIED_CHINESE_DYNAMIC_TEMPLATES),
            (RUSSIAN_TRANSLATIONS, RUSSIAN_DYNAMIC_TEMPLATES),
            (JAPANESE_TRANSLATIONS, JAPANESE_DYNAMIC_TEMPLATES),
            (GERMAN_TRANSLATIONS, GERMAN_DYNAMIC_TEMPLATES),
        ):
            self.assertLessEqual(set(exact_catalog), set(ENGLISH_TRANSLATIONS))
            self.assertEqual(len(dynamic_catalog), len(_DYNAMIC_ENGLISH))

    def test_new_language_catalogs_preserve_placeholders_and_have_no_generator_artifacts(self) -> None:
        placeholder_pattern = re.compile(r"\{\d+\}")
        english_dynamic = [replacement for _pattern, replacement in _DYNAMIC_ENGLISH]
        for exact_catalog, dynamic_catalog in (
            (SPANISH_TRANSLATIONS, SPANISH_DYNAMIC_TEMPLATES),
            (TURKISH_TRANSLATIONS, TURKISH_DYNAMIC_TEMPLATES),
            (HINDI_TRANSLATIONS, HINDI_DYNAMIC_TEMPLATES),
            (SIMPLIFIED_CHINESE_TRANSLATIONS, SIMPLIFIED_CHINESE_DYNAMIC_TEMPLATES),
            (RUSSIAN_TRANSLATIONS, RUSSIAN_DYNAMIC_TEMPLATES),
            (JAPANESE_TRANSLATIONS, JAPANESE_DYNAMIC_TEMPLATES),
            (GERMAN_TRANSLATIONS, GERMAN_DYNAMIC_TEMPLATES),
        ):
            for arabic, english in ENGLISH_TRANSLATIONS.items():
                translated = exact_catalog.get(arabic, english)
                self.assertTrue(translated.strip())
                self.assertEqual(
                    sorted(placeholder_pattern.findall(translated)),
                    sorted(placeholder_pattern.findall(english)),
                )
                self.assertNotIn("PAM_CATALOG_SEPARATOR", translated)
                self.assertNotIn("ZXQTOKEN", translated)
                self.assertNotIn("translation reset", translated.lower())
            for english, translated in zip(
                english_dynamic,
                dynamic_catalog,
                strict=True,
            ):
                self.assertEqual(
                    sorted(placeholder_pattern.findall(translated)),
                    sorted(placeholder_pattern.findall(english)),
                )
                self.assertNotIn("PAM_CATALOG_SEPARATOR", translated)

    def test_french_catalog_keys_belong_to_the_english_catalog(self) -> None:
        self.assertLessEqual(set(FRENCH_TRANSLATIONS), set(ENGLISH_TRANSLATIONS))
        self.assertEqual(len(FRENCH_DYNAMIC_TEMPLATES), len(_DYNAMIC_ENGLISH))

    def test_literal_interface_translations_have_an_english_fallback(self) -> None:
        package = Path(__file__).resolve().parents[1] / "accessible_mail"
        missing: list[tuple[str, int, str]] = []
        for path in package.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "tr"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                    and any(
                        "\u0600" <= character <= "\u06ff"
                        for character in node.args[0].value
                    )
                    and node.args[0].value not in ENGLISH_TRANSLATIONS
                ):
                    missing.append((path.name, node.lineno, node.args[0].value))
        self.assertEqual(missing, [])

    def test_french_program_guide_uses_requested_version(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        guide = load_program_guide(LANGUAGE_FRENCH, "9.8.7", project_root)

        self.assertIn("Version 9.8.7", guide)
        self.assertIn(
            "l'arabe l'anglais le français l'espagnol le turc l'hindi "
            "le chinois simplifié le russe le japonais ou l'allemand",
            guide,
        )
        self.assertIn("Utiliser la visionneuse des éléments étape par étape", guide)
        self.assertIn("Ajouter une pièce jointe", guide)
        self.assertNotIn("Version 1.2.14", guide)

    def test_all_program_guides_cover_detailed_attachment_workflows(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        expected_phrases = {
            LANGUAGE_ARABIC: (
                "استخدام مستعرض العناصر خطوة بخطوة",
                "إنشاء رسالة وإضافة مرفقات صادرة",
                "استخدام سجل العناوين",
            ),
            LANGUAGE_ENGLISH: (
                "Use the item viewer step by step",
                "Compose a message and add outgoing attachments",
                "Use the address book",
            ),
            LANGUAGE_FRENCH: (
                "Utiliser la visionneuse des éléments étape par étape",
                "Composer un message et ajouter des pièces jointes sortantes",
                "Utiliser le carnet d'adresses",
            ),
            LANGUAGE_SPANISH: (
                "Utilice el visor de elementos paso a paso",
                "Redacte un mensaje y agregue archivos adjuntos salientes",
                "Usar la libreta de direcciones",
            ),
            LANGUAGE_TURKISH: (
                "Öğe görüntüleyiciyi adım adım kullanma",
                "Bir mesaj oluşturun ve giden ekler ekleyin",
                "Adres Defterini Kullanma",
            ),
            LANGUAGE_HINDI: (
                "आइटम व्यूअर का स्टेप बाय स्टेप इस्तेमाल करें",
                "एक मैसेज लिखें और आउटगोइंग अटैचमेंट जोड़ें",
                "एड्रेस बुक का इस्तेमाल करें",
            ),
            LANGUAGE_SIMPLIFIED_CHINESE: (
                "逐步使用项目查看器",
                "撰写消息并添加传出附件",
                "使用地址簿",
            ),
            LANGUAGE_RUSSIAN: (
                "Используйте средство просмотра элементов шаг за шагом",
                "Напишите сообщение и добавьте исходящие вложения",
                "Используйте адресную книгу",
            ),
            LANGUAGE_JAPANESE: (
                "アイテムビューアを段階的に使用する",
                "メッセージを作成し、送信添付ファイルを追加する",
                "アドレス帳を使用する",
            ),
            LANGUAGE_GERMAN: (
                "Schritt für Schritt zur Verwendung der Elementansicht",
                "E-Mail verfassen und ausgehende Anhänge hinzufügen",
                "Adressbuch verwenden",
            ),
        }

        for language, phrases in expected_phrases.items():
            with self.subTest(language=language):
                guide = load_program_guide(language, "9.8.7", project_root)
                self.assertIn("9.8.7", guide)
                for phrase in phrases:
                    self.assertIn(phrase, guide)
                self.assertNotIn("Manage attachments and links", guide)


if __name__ == "__main__":
    unittest.main()
