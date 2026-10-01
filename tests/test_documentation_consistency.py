from __future__ import annotations

import re
import unittest
from pathlib import Path

from accessible_mail.guide import GUIDE_FILENAMES, guide_heading_ranges, load_program_guide
from accessible_mail.i18n import get_language, set_language, tr
from accessible_mail.interactive_learning import LESSONS


class DocumentationConsistencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.language = get_language()

    def tearDown(self) -> None:
        set_language(self.language)

    def test_all_guide_files_declare_the_current_version(self) -> None:
        from accessible_mail.config import APP_VERSION

        for language, filename in GUIDE_FILENAMES.items():
            with self.subTest(language=language):
                lines = (self.root / filename).read_text(encoding='utf-8-sig').splitlines()
                self.assertIn(APP_VERSION, '\n'.join(lines[:4]))
                self.assertTrue(
                    '1.5.0' not in '\n'.join(lines),
                    f'{language}: obsolete release-specific guide text',
                )

    def test_all_guides_name_actual_settings_and_section_restore_commands(self) -> None:
        for language in GUIDE_FILENAMES:
            with self.subTest(language=language):
                set_language(language)
                guide = load_program_guide(language, '9.8.7', self.root)
                for source in (
                    'Customize application sounds',
                    'Low-vision features and options',
                    'Return to original sections',
                    'Refresh displayed content',
                ):
                    self.assertTrue(tr(source) in guide, f'{language}: missing UI label {tr(source)!r}')

    def test_new_navigation_and_organization_shortcuts_are_in_every_guide(self) -> None:
        shortcuts = (
            'Alt+S', 'Alt+]', 'Alt+[', 'Alt+A', 'Ctrl+A',
            'Alt+Z', 'Alt+X', 'Alt+C',
            'Alt+Ctrl+Z', 'Alt+Ctrl+X', 'Alt+Ctrl+C',
            'Alt+Ctrl+Shift+Z', 'Alt+Ctrl+Shift+X', 'Alt+Ctrl+Shift+C',
            'Alt+D', 'Alt+H',
        )
        for language in GUIDE_FILENAMES:
            with self.subTest(language=language):
                guide = load_program_guide(language, '9.8.7', self.root)
                normalized = (
                    guide.replace('Strg', 'Ctrl').replace('Umschalt', 'Shift')
                    .replace('Maj', 'Shift')
                )
                for shortcut in shortcuts:
                    self.assertTrue(shortcut in normalized, f'{language}: missing shortcut {shortcut}')

    def test_task_counts_match_the_running_guide(self) -> None:
        task_words = {
            'ar': 'مهمة', 'en': 'tasks', 'fr': 'tâches', 'de': 'Aufgaben',
            'es': 'tareas', 'tr': 'görev', 'hi': 'कार्य', 'ru': 'задания',
            'ja': 'の課題', 'zh-CN': '个',
        }
        for language, word in task_words.items():
            with self.subTest(language=language):
                guide = load_program_guide(language, '9.8.7', self.root)
                self.assertTrue(
                    re.search(rf'{len(LESSONS)}\s+{re.escape(word)}', guide),
                    f'{language}: task count must match {len(LESSONS)}',
                )

    def test_all_languages_have_navigable_headings(self) -> None:
        for language in GUIDE_FILENAMES:
            with self.subTest(language=language):
                guide = load_program_guide(language, '9.8.7', self.root)
                self.assertGreaterEqual(len(guide_heading_ranges(guide)), 5)

    def test_obsolete_item_menu_instructions_do_not_return(self) -> None:
        obsolete = {
            'ar': 'لا تحاول فتح قائمة سياق داخل قائمة العناصر',
            'en': 'item list has no context menu',
            'fr': "liste des éléments n'a pas de menu contextuel",
            'de': 'Elementliste verfügt über kein Kontextmenü',
            'es': 'lista de elementos no tiene menú contextual',
            'tr': 'Öğe listesinin bağlam menüsü yoktur',
            'hi': 'आइटम सूची का अपना संदर्भ मेन्यू नहीं है',
            'ru': 'Список элементов не имеет контекстного меню',
            'ja': '項目リストにはコンテキスト メニューがありません',
            'zh-CN': '项目列表没有上下文菜单',
        }
        for language, phrase in obsolete.items():
            with self.subTest(language=language):
                guide = load_program_guide(language, '9.8.7', self.root)
                self.assertNotIn(phrase, guide)


if __name__ == '__main__':
    unittest.main()
