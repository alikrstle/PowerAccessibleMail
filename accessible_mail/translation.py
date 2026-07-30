from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .email_service import MailError


def text_chunks(text: str, max_length: int = 4500) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        next_line = line if not current else f"{current}\n{line}"
        if len(next_line) <= max_length:
            current = next_line
            continue
        if current:
            chunks.append(current)
        while len(line) > max_length:
            chunks.append(line[:max_length])
            line = line[max_length:]
        current = line
    if current:
        chunks.append(current)
    return chunks or [text[:max_length]]


def translate_text_with_google(text: str, target_language: str = "ar") -> str:
    text = text.strip()
    if not text:
        return ""
    translated_parts: list[str] = []
    for chunk in text_chunks(text):
        data = urllib.parse.urlencode(
            {
                "client": "gtx",
                "sl": "auto",
                "tl": target_language,
                "dt": "t",
                "q": chunk,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://translate.googleapis.com/translate_a/single",
            data=data,
            headers={"User-Agent": "Power Accessible Mail"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload or not isinstance(payload[0], list):
            continue
        translated_parts.append("".join(str(part[0]) for part in payload[0] if part and part[0]))
    translated = "\n".join(part for part in translated_parts if part.strip()).strip()
    if not translated:
        raise MailError("تعذر الحصول على ترجمة من Google.")
    return translated
