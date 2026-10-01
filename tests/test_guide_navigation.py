from __future__ import annotations

import unittest
from pathlib import Path

from accessible_mail.guide import adjacent_guide_heading, guide_heading_ranges


class GuideNavigationTests(unittest.TestCase):
    def test_arabic_guide_uses_chapters_not_table_of_contents(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "installer_readme_ar.txt").read_text(encoding="utf-8-sig")

        headings = guide_heading_ranges(text)

        self.assertEqual(len(headings), 24)
        self.assertEqual(text[slice(*headings[0])], "1. تثبيت البرنامج وفتحه")
        self.assertEqual(text[slice(*headings[-1])], "24. قفل مجلدات سجل العناوين")
        self.assertGreater(headings[0][0], text.index("محتويات الدليل"))

    def test_next_and_previous_headings_wrap(self) -> None:
        headings = [(10, 15), (30, 35), (50, 55)]

        self.assertEqual(adjacent_guide_heading(headings, 0, 1), headings[0])
        self.assertEqual(adjacent_guide_heading(headings, 10, 1), headings[1])
        self.assertEqual(adjacent_guide_heading(headings, 50, 1), headings[0])
        self.assertEqual(adjacent_guide_heading(headings, 0, -1), headings[-1])
        self.assertEqual(adjacent_guide_heading(headings, 30, -1), headings[0])
        self.assertIsNone(adjacent_guide_heading([], 0, 1))


if __name__ == "__main__":
    unittest.main()
