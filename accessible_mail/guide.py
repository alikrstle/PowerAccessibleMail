from __future__ import annotations

import re
from pathlib import Path

from .config import (
    LANGUAGE_ARABIC,
    LANGUAGE_ENGLISH,
    LANGUAGE_FRENCH,
    app_dir,
)


GUIDE_FILENAMES = {
    LANGUAGE_ARABIC: "installer_readme_ar.txt",
    LANGUAGE_ENGLISH: "installer_readme_en.txt",
    LANGUAGE_FRENCH: "installer_readme_fr.txt",
}
VERSION_LINE_PATTERN = re.compile(
    r"^(?P<label>Version|الإصدار)\s*:?[ \t]*\d+(?:\.\d+){2}[ \t]*$",
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
