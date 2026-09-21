from __future__ import annotations

import re
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
