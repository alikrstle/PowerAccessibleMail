from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from pathlib import Path

from .config import (
    LANGUAGE_ARABIC,
    LANGUAGE_ENGLISH,
    LANGUAGE_FRENCH,
    LANGUAGE_HINDI,
    LANGUAGE_JAPANESE,
    LANGUAGE_GERMAN,
    LANGUAGE_RUSSIAN,
    LANGUAGE_SIMPLIFIED_CHINESE,
    LANGUAGE_SPANISH,
    LANGUAGE_TURKISH,
    app_dir,
)


GUIDE_FILENAMES = {
    LANGUAGE_ARABIC: "installer_readme_ar.txt",
    LANGUAGE_ENGLISH: "installer_readme_en.txt",
    LANGUAGE_FRENCH: "installer_readme_fr.txt",
    LANGUAGE_SPANISH: "installer_readme_es.txt",
    LANGUAGE_TURKISH: "installer_readme_tr.txt",
    LANGUAGE_HINDI: "installer_readme_hi.txt",
    LANGUAGE_SIMPLIFIED_CHINESE: "installer_readme_zh-CN.txt",
    LANGUAGE_RUSSIAN: "installer_readme_ru.txt",
    LANGUAGE_JAPANESE: "installer_readme_ja.txt",
    LANGUAGE_GERMAN: "installer_readme_de.txt",
}
VERSION_LINE_PATTERN = re.compile(
    r"^(?P<label>Version|الإصدار|Versión|Sürüm|संस्करण|वर्जन|版本|Версия|バージョン)\s*:?[ \t]*\d+(?:\.\d+){2}[ \t]*$",
    re.MULTILINE,
)


def guide_heading_ranges(text: str) -> list[tuple[int, int]]:
    """Return selectable heading positions, skipping a numbered contents list."""
    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)

    numbered: list[tuple[int, int, int]] = []
    for index, line in enumerate(lines):
        title = line.strip()
        match = re.fullmatch(r"(\d{1,2})\.\s+(.+)", title)
        if not match or index == 0 or index + 1 >= len(lines):
            continue
        if lines[index - 1].strip() or lines[index + 1].strip():
            continue
        numbered.append((int(match.group(1)), offsets[index], offsets[index] + len(title)))
    if len(numbered) >= 3:
        # The Arabic guide has a compact numbered contents list followed by
        # the actual, blank-line-separated chapter headings.
        return [(start, end) for _number, start, end in numbered]

    headings: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        title = line.strip()
        if index < 4 or index + 1 >= len(lines) or not title:
            continue
        if lines[index - 1].strip() or lines[index + 1].strip():
            continue
        if len(title) > 70 or len(title.split()) > 10:
            continue
        if title.endswith((".", "!", "?", ":", ";", "،", "。", "؟")):
            continue
        following = next(
            (next_line.strip() for next_line in lines[index + 1:] if next_line.strip()),
            "",
        )
        if len(following) < 80:
            continue
        headings.append((offsets[index], offsets[index] + len(title)))
    return headings


def adjacent_guide_heading(
    headings: list[tuple[int, int]], position: int, direction: int,
) -> tuple[int, int] | None:
    if not headings:
        return None
    starts = [start for start, _end in headings]
    if direction > 0:
        return headings[bisect_right(starts, position) % len(headings)]
    return headings[(bisect_left(starts, position) - 1) % len(headings)]


def load_program_guide(
    language: str,
    version: str,
    root: Path | None = None,
) -> str:
    filename = GUIDE_FILENAMES.get(language, GUIDE_FILENAMES[LANGUAGE_ENGLISH])
    guide = ((root or app_dir()) / filename).read_text(encoding="utf-8-sig").strip()

    def replace_version(match: re.Match[str]) -> str:
        return f"{match.group('label')} {version}"

    return VERSION_LINE_PATTERN.sub(replace_version, guide, count=1)
