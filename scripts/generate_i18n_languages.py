from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from pprint import pformat

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER_PATTERN = re.compile(r"\{\d+\}|\t")
CATALOG_SEPARATOR = "__PAM_CATALOG_SEPARATOR__"
MAX_BATCH_CHARACTERS = 1400
CACHE_DIR = PROJECT_ROOT / "build-i18n-cache"
INSTALLER_INFO_SOURCE = PROJECT_ROOT / "installer_info_en.txt"
INSTALLER_README_SOURCE = PROJECT_ROOT / "installer_readme_en.txt"

sys.path.insert(0, str(PROJECT_ROOT))

from accessible_mail.i18n import ENGLISH_TRANSLATIONS, _DYNAMIC_ENGLISH
from accessible_mail.translation import translate_text_with_google


LANGUAGES = {
    "es": {
        "name": "Spanish",
        "variable": "SPANISH",
        "module": "i18n_es.py",
    },
    "tr": {
        "name": "Turkish",
        "variable": "TURKISH",
        "module": "i18n_tr.py",
    },
    "hi": {
        "name": "Hindi",
        "variable": "HINDI",
        "module": "i18n_hi.py",
    },
}

MANUAL_TRANSLATIONS = {
    "es": {
        "Arabic": "Árabe",
        "English": "Inglés",
        "French": "Francés",
        "Spanish": "Español",
        "Turkish": "Turco",
        "Hindi": "Hindi",
        "Settings": "Configuración",
        "Application language": "Idioma de la aplicación",
        "Application language:": "Idioma de la aplicación:",
        "Inbox": "Bandeja de entrada",
        "Spam": "Correo no deseado",
        "Sent": "Enviados",
        "All Mail": "Todos los mensajes",
        "Trash": "Papelera",
        "Read": "Leído",
        "Unread": "No leído",
        "Mark as read": "Marcar como leído",
        "Mark as unread": "Marcar como no leído",
        "Compose email": "Redactar correo electrónico",
        "Reply": "Responder",
        "Copy": "Copiar",
        "Translate": "Traducir",
        "Cancel": "Cancelar",
        "Close": "Cerrar",
        "Save": "Guardar",
        "Help": "Ayuda",
        "Check for updates": "Buscar actualizaciones",
        "Power Accessible Mail Guide": "Guía de Power Accessible Mail",
    },
    "tr": {
        "Arabic": "Arapça",
        "English": "İngilizce",
        "French": "Fransızca",
        "Spanish": "İspanyolca",
        "Turkish": "Türkçe",
        "Hindi": "Hintçe",
        "Settings": "Ayarlar",
        "Application language": "Uygulama dili",
        "Application language:": "Uygulama dili:",
        "Inbox": "Gelen Kutusu",
        "Spam": "İstenmeyen posta",
        "Sent": "Gönderilenler",
        "All Mail": "Tüm Postalar",
        "Trash": "Çöp Kutusu",
        "Read": "Okundu",
        "Unread": "Okunmadı",
        "Mark as read": "Okundu olarak işaretle",
        "Mark as unread": "Okunmadı olarak işaretle",
        "Compose email": "E-posta oluştur",
        "Reply": "Yanıtla",
        "Copy": "Kopyala",
        "Translate": "Çevir",
        "Cancel": "İptal",
        "Close": "Kapat",
        "Save": "Kaydet",
        "Help": "Yardım",
        "Check for updates": "Güncellemeleri denetle",
        "Power Accessible Mail Guide": "Power Accessible Mail Kılavuzu",
    },
    "hi": {
        "Arabic": "अरबी",
        "English": "अंग्रेज़ी",
        "French": "फ़्रेंच",
        "Spanish": "स्पेनिश",
        "Turkish": "तुर्की",
        "Hindi": "हिन्दी",
        "Settings": "सेटिंग्स",
        "Application language": "एप्लिकेशन की भाषा",
        "Application language:": "एप्लिकेशन की भाषा:",
        "Inbox": "इनबॉक्स",
        "Spam": "स्पैम",
        "Sent": "भेजे गए",
        "All Mail": "सभी मेल",
        "Trash": "ट्रैश",
        "Read": "पढ़ा गया",
        "Unread": "अपठित",
        "Mark as read": "पढ़ा हुआ चिह्नित करें",
        "Mark as unread": "अपठित चिह्नित करें",
        "Compose email": "ईमेल लिखें",
        "Reply": "जवाब दें",
        "Copy": "कॉपी करें",
        "Translate": "अनुवाद करें",
        "Cancel": "रद्द करें",
        "Close": "बंद करें",
        "Save": "सहेजें",
        "Help": "सहायता",
        "Check for updates": "अपडेट जाँचें",
        "Power Accessible Mail Guide": "Power Accessible Mail मार्गदर्शिका",
    },
}


def protected_value(text: str) -> tuple[str, dict[str, str]]:
    tokens: dict[str, str] = {}

    def protect(match: re.Match[str]) -> str:
        token = f"__PAM_TOKEN_{len(tokens)}__"
        tokens[token] = match.group(0)
        return token

    return PLACEHOLDER_PATTERN.sub(protect, text), tokens


def restore_tokens(text: str, tokens: dict[str, str], source: str) -> str:
    translated = text.strip()
    for token, original in tokens.items():
        if token not in translated:
            raise RuntimeError(f"Translation lost placeholder {original!r}: {source!r}")
        translated = translated.replace(token, original)
    return translated


def translate_value(text: str, language: str) -> str:
    manual = MANUAL_TRANSLATIONS[language].get(text)
    if manual is not None:
        return manual
    protected, tokens = protected_value(text)
    translated = translate_text_with_google(protected, target_language=language)
    return restore_tokens(translated, tokens, text)


def cached_translations(language: str) -> tuple[Path, dict[str, str]]:
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"{language}.json"
    if not path.is_file():
        return path, {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return path, {str(key): str(value) for key, value in payload.items()}


def save_cache(path: Path, translations: dict[str, str]) -> None:
    path.write_text(
        json.dumps(translations, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def catalog_batches(values: list[str]) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    current_length = 0
    separator_length = len(CATALOG_SEPARATOR) + 2
    for value in values:
        protected, _tokens = protected_value(value)
        added_length = len(protected) + (separator_length if current else 0)
        if current and (
            len(current) >= 8
            or current_length + added_length > MAX_BATCH_CHARACTERS
        ):
            batches.append(current)
            current = []
            current_length = 0
        current.append(value)
        current_length += len(protected) + (separator_length if len(current) > 1 else 0)
    if current:
        batches.append(current)
    return batches


def translate_batch(language: str, sources: list[str]) -> dict[str, str]:
    protected_sources: list[str] = []
    token_sets: list[dict[str, str]] = []
    for source in sources:
        protected, tokens = protected_value(source)
        protected_sources.append(protected)
        token_sets.append(tokens)
    joined = f"\n{CATALOG_SEPARATOR}\n".join(protected_sources)
    translated = translate_text_with_google(joined, target_language=language)
    translated_values = re.split(
        rf"\s*{re.escape(CATALOG_SEPARATOR)}\s*",
        translated,
    )
    if len(translated_values) != len(sources):
        raise RuntimeError(
            f"Translation batch boundary mismatch: expected {len(sources)}, "
            f"received {len(translated_values)}"
        )
    return {
        source: restore_tokens(value, tokens, source)
        for source, value, tokens in zip(
            sources,
            translated_values,
            token_sets,
            strict=True,
        )
    }


def translate_catalog(
    language: str,
    values: list[str],
    *,
    cache_only: bool = False,
) -> dict[str, str]:
    unique_values = list(dict.fromkeys(values))
    cache_path, translations = cached_translations(language)
    for source in unique_values:
        manual = MANUAL_TRANSLATIONS[language].get(source)
        if manual is not None:
            translations[source] = manual
    pending_values = [value for value in unique_values if value not in translations]
    if cache_only and pending_values:
        raise RuntimeError(
            f"{language} translation cache is missing {len(pending_values)} text(s)."
        )
    batches = catalog_batches(pending_values)
    for batch_index, batch in enumerate(batches, start=1):
        for attempt in range(6):
            try:
                translations.update(translate_batch(language, batch))
                save_cache(cache_path, translations)
                break
            except Exception:
                if attempt == 5:
                    raise
                time.sleep(10 + attempt * 5)
        print(
            f"{language}: completed batch {batch_index}/{len(batches)}; "
            f"{len(translations)}/{len(unique_values)} texts ready",
            flush=True,
        )
        time.sleep(0.8)
    return translations


def catalog_values() -> tuple[list[str], list[str], list[str]]:
    exact_values = list(ENGLISH_TRANSLATIONS.values())
    dynamic_values = [replacement for _pattern, replacement in _DYNAMIC_ENGLISH]
    documents = [
        INSTALLER_INFO_SOURCE.read_text(encoding="utf-8-sig").strip(),
        INSTALLER_README_SOURCE.read_text(encoding="utf-8-sig").strip(),
    ]
    return exact_values, dynamic_values, documents


def prepare_browser_manifest(languages: list[str]) -> Path:
    exact_values, dynamic_values, documents = catalog_values()
    unique_values = list(dict.fromkeys(exact_values + dynamic_values + documents))
    manifest: dict[str, list[dict[str, object]]] = {}
    for language in languages:
        cache_path, translations = cached_translations(language)
        for source in unique_values:
            manual = MANUAL_TRANSLATIONS[language].get(source)
            if manual is not None:
                translations[source] = manual
        save_cache(cache_path, translations)
        pending_values = [value for value in unique_values if value not in translations]
        manifest[language] = []
        for batch in catalog_batches(pending_values):
            protected_sources: list[str] = []
            token_sets: list[dict[str, str]] = []
            for source in batch:
                protected, tokens = protected_value(source)
                protected_sources.append(protected)
                token_sets.append(tokens)
            manifest[language].append(
                {
                    "sources": batch,
                    "text": "\n".join(
                        part
                        for index, protected in enumerate(protected_sources)
                        for part in (
                            protected,
                            (
                                f"__PAM_CATALOG_SEPARATOR_{index:04d}__"
                                if index + 1 < len(protected_sources)
                                else ""
                            ),
                        )
                        if part
                    ),
                    "tokens": token_sets,
                }
            )
    path = CACHE_DIR / "browser_manifest.json"
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {path}")
    return path


def generate_language(language: str, *, cache_only: bool = False) -> None:
    metadata = LANGUAGES[language]
    exact_values, dynamic_values, documents = catalog_values()
    translated = translate_catalog(
        language,
        exact_values + dynamic_values + documents,
        cache_only=cache_only,
    )
    exact_catalog = {
        source: translated[english]
        for source, english in ENGLISH_TRANSLATIONS.items()
    }
    dynamic_catalog = tuple(translated[english] for english in dynamic_values)
    variable = metadata["variable"]
    output = (
        "from __future__ import annotations\n\n"
        "# Generated by scripts/generate_i18n_languages.py and reviewed in source control.\n"
        f"{variable}_TRANSLATIONS: dict[str, str] = "
        f"{pformat(exact_catalog, width=120, sort_dicts=False)}\n\n"
        f"{variable}_DYNAMIC_TEMPLATES: tuple[str, ...] = "
        f"{pformat(dynamic_catalog, width=120)}\n"
    )
    (PROJECT_ROOT / "accessible_mail" / metadata["module"]).write_text(
        output,
        encoding="utf-8",
        newline="\n",
    )
    (PROJECT_ROOT / f"installer_info_{language}.txt").write_text(
        translated[documents[0]] + "\n",
        encoding="utf-8-sig",
        newline="\n",
    )
    (PROJECT_ROOT / f"installer_readme_{language}.txt").write_text(
        translated[documents[1]] + "\n",
        encoding="utf-8-sig",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("languages", nargs="*", choices=tuple(LANGUAGES), default=tuple(LANGUAGES))
    parser.add_argument("--prepare-browser-manifest", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--invalidate-documents", action="store_true")
    parser.add_argument("--invalidate-info", action="store_true")
    arguments = parser.parse_args()
    languages = list(arguments.languages or LANGUAGES)
    if arguments.invalidate_documents:
        documents = catalog_values()[2]
        for language in languages:
            cache_path, translations = cached_translations(language)
            for document in documents:
                translations.pop(document, None)
            save_cache(cache_path, translations)
    if arguments.invalidate_info:
        installer_info = catalog_values()[2][0]
        for language in languages:
            cache_path, translations = cached_translations(language)
            translations.pop(installer_info, None)
            save_cache(cache_path, translations)
    if arguments.prepare_browser_manifest:
        prepare_browser_manifest(languages)
        return
    for language in languages:
        generate_language(language, cache_only=arguments.cache_only)


if __name__ == "__main__":
    main()
