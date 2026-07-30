from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .email_service import MailError

TRANSLATION_ATTEMPTS = 2
TRANSIENT_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}


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
        translated_parts.append(translate_chunk_with_google(chunk, target_language))
    translated = "\n".join(part for part in translated_parts if part.strip()).strip()
    if not translated:
        raise MailError("تعذر الحصول على ترجمة من Google.")
    return translated


def translate_chunk_with_google(chunk: str, target_language: str) -> str:
    last_error: Exception | None = None
    for attempt in range(TRANSLATION_ATTEMPTS):
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
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not payload or not isinstance(payload[0], list):
                raise MailError("تعذر الحصول على ترجمة من Google.")
            translated = "".join(
                str(part[0]) for part in payload[0] if part and part[0]
            ).strip()
            if not translated:
                raise MailError("تعذر الحصول على ترجمة من Google.")
            return translated
        except urllib.error.HTTPError as exc:
            if exc.code not in TRANSIENT_HTTP_STATUS_CODES:
                raise MailError("تعذر الحصول على ترجمة من Google.") from exc
            last_error = exc
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            UnicodeDecodeError,
            MailError,
        ) as exc:
            last_error = exc
        if attempt + 1 < TRANSLATION_ATTEMPTS:
            time.sleep(0.6)
    raise MailError("تعذر الحصول على ترجمة من Google.") from last_error
