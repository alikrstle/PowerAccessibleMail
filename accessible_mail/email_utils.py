from __future__ import annotations

import base64
import re
import urllib.parse
from dataclasses import replace
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from html.parser import HTMLParser

from .models import LinkItem


URL_PATTERN = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
ACTIVATION_MARKER_PATTERN = re.compile(r"\[\[PAM-ACTION-(\d+)-(START|END)\]\]")
HTML_TAG_PATTERN = re.compile(r"</?(?:html|head|body|style|script|div|table|tr|td|span|p|a)\b", re.IGNORECASE)
CSS_BLOCK_PATTERN = re.compile(r"\b(?:body|img|table|td|tr|p|div|span|a|html)\s*\{", re.IGNORECASE)
CSS_PROPERTY_PATTERN = re.compile(
    r"\b(?:margin|padding|border|outline|font-family|font-size|background|color|width|height|display)\s*:",
    re.IGNORECASE,
)
LIST_LINE_PATTERN = re.compile(r"^\s*(?:[-*+•●○]|\d+[.)]|[اأإآبتثجحخدذرزسشصضطظعغفقكلمنهوي][.)])\s+")
GENERIC_LINK_TITLES = {
    "",
    "click here",
    "here",
    "read more",
    "learn more",
    "open",
    "view",
    "اضغط هنا",
    "هنا",
    "افتح",
    "فتح",
    "المزيد",
    "اقرأ المزيد",
}
SAFE_EXTERNAL_URL_SCHEMES = frozenset({"http", "https", "mailto"})
PLAIN_TEXT_PLACEHOLDER_PHRASES = (
    "لا يوجد نص قابل للعرض داخل هذه الرسالة",
    "plain text version not available",
    "plain-text version not available",
    "this message has no plain text version",
    "this message is only available in html",
    "please view this email in an html capable email client",
    "your email client does not support html messages",
    "your email client cannot display html",
    "your email client can't display html",
    "email client cannot display html",
    "email client can't display html",
    "to view this email, please click the link above",
    "لا يستطيع برنامج البريد الإلكتروني الخاص بك عرض html",
    "لا يستطيع برنامج البريد الالكتروني الخاص بك عرض html",
    "لعرض هذه الرسالة الإلكترونية، يرجى النقر على الرابط أعلاه",
    "لعرض هذه الرسالة الالكترونية، يرجى النقر على الرابط أعلاه",
)
HTML_CLIENT_WARNING_PATTERNS = (
    re.compile(
        r"(?:unfortunately\s*[,،]?\s*)?(?:your\s+)?email client cannot display html"
        r"(?:\s*[,،]?\s*or\s+(?:your\s+)?settings are turned off)?[.!]?\s*"
        r"to view this email\s*[,]?\s*please (?:click|select) the link above\s*[,]?\s*"
        r"or copy and paste it into your browser[.!]?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:لسوء الحظ\s*[،,]?\s*)?لا يستطيع برنامج البريد (?:الإلكتروني|الالكتروني) الخاص بك عرض html"
        r"(?:\s*[،,]?\s*أو تم إيقاف إعداداتك)?[.!؟]?\s*"
        r"لعرض هذه الرسالة (?:الإلكترونية|الالكترونية)\s*[،,]?\s*يرجى النقر على الرابط أعلاه\s*[،,]?\s*"
        r"أو نسخها ولصقها في متصفحك[.!؟]?",
        re.IGNORECASE,
    ),
)


def header_to_text(value: object) -> str:
    if value is None:
        return ""
    try:
        return str(make_header(decode_header(str(value)))).strip()
    except Exception:
        return str(value).strip()


def safe_external_url(value: object) -> str:
    url = str(value or "").strip()
    if not url or any(character.isspace() or ord(character) < 32 for character in url):
        return ""
    try:
        parsed = urllib.parse.urlsplit(url)
        scheme = parsed.scheme.casefold()
        if scheme not in SAFE_EXTERNAL_URL_SCHEMES:
            return ""
        if scheme in {"http", "https"}:
            if not parsed.netloc or not parsed.hostname:
                return ""
        elif not parsed.path:
            return ""
        return url
    except ValueError:
        return ""


class _HtmlToTextParser(HTMLParser):
    IGNORED_TAGS = {"head", "style", "script", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[LinkItem] = []
        self._form_actions: list[str] = []
        self._current_href = ""
        self._current_kind = "link"
        self._current_text: list[str] = []
        self._current_button_url = ""
        self._current_button_text: list[str] | None = None
        self._current_link_marker = ""
        self._current_button_marker = ""
        self._next_marker_id = 0
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.IGNORED_TAGS:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        if tag == "form":
            self._form_actions.append(attrs_dict.get("action", ""))
        if tag == "a":
            self._current_href = attrs_dict.get("href", "")
            role = attrs_dict.get("role", "").lower()
            style_class = f"{attrs_dict.get('class', '')} {attrs_dict.get('style', '')}".lower()
            self._current_kind = "button" if role == "button" or "button" in style_class else "link"
            self._current_text = []
            self._current_link_marker = self._new_activation_marker() if self._current_href else ""
            if self._current_link_marker:
                self.parts.append(_activation_marker(self._current_link_marker, "START"))
        if tag == "button":
            self._current_button_url = attrs_dict.get("formaction", "") or (self._form_actions[-1] if self._form_actions else "")
            self._current_button_text = []
            self._current_button_marker = self._new_activation_marker()
            self.parts.append(_activation_marker(self._current_button_marker, "START"))
        if tag == "input" and attrs_dict.get("type", "").lower() in {"button", "submit", "reset", "image"}:
            label = _clean_resource_title(
                attrs_dict.get("value", "")
                or attrs_dict.get("aria-label", "")
                or attrs_dict.get("title", "")
                or attrs_dict.get("alt", "")
                or attrs_dict.get("name", "")
                or "زر بدون عنوان"
            )
            url = attrs_dict.get("formaction", "") or (self._form_actions[-1] if self._form_actions else "")
            marker = self._new_activation_marker()
            self.links.append(LinkItem(label, url, kind="button", activation_text=label, activation_marker=marker))
            self.parts.append(f"\n{_activation_marker(marker, 'START')}{label}{_activation_marker(marker, 'END')}\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._ignored_depth:
            if tag in self.IGNORED_TAGS:
                self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if tag == "a" and self._current_href:
            activation_text = _clean_resource_title(" ".join("".join(self._current_text).split()))
            label = activation_text
            if _is_generic_title(label, self._current_href):
                label = self._nearby_context_title(label) or label
            if self._current_link_marker:
                self.parts.append(_activation_marker(self._current_link_marker, "END"))
            self.links.append(
                LinkItem(
                    label or self._current_href,
                    self._current_href,
                    kind=self._current_kind,
                    activation_text=activation_text or label or self._current_href,
                    activation_marker=self._current_link_marker,
                )
            )
            self._current_href = ""
            self._current_kind = "link"
            self._current_text = []
            self._current_link_marker = ""
        if tag == "button" and self._current_button_text is not None:
            label = _clean_resource_title("".join(self._current_button_text)) or "زر بدون عنوان"
            if self._current_button_marker:
                self.parts.append(_activation_marker(self._current_button_marker, "END"))
            self.links.append(
                LinkItem(
                    label,
                    self._current_button_url,
                    kind="button",
                    activation_text=label,
                    activation_marker=self._current_button_marker,
                )
            )
            self._current_button_url = ""
            self._current_button_text = None
            self._current_button_marker = ""
        if tag == "form" and self._form_actions:
            self._form_actions.pop()
        if tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if data:
            self.parts.append(data)
            if self._current_href:
                self._current_text.append(data)
            if self._current_button_text is not None:
                self._current_button_text.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line).strip()

    def _nearby_context_title(self, label: str) -> str:
        text = ACTIVATION_MARKER_PATTERN.sub("", "".join(self.parts))
        lines = [" ".join(line.split()) for line in text.splitlines()]
        normalized_label = _clean_resource_title(label).lower()
        for line in reversed(lines[-5:]):
            title = _clean_resource_title(line)
            if title and title.lower() != normalized_label and not _is_generic_title(title):
                return title
        return ""

    def _new_activation_marker(self) -> str:
        marker = str(self._next_marker_id)
        self._next_marker_id += 1
        return marker


def html_to_text_and_links(html: str) -> tuple[str, list[LinkItem]]:
    parser = _HtmlToTextParser()
    parser.feed(html)
    text_with_markers = normalize_message_text(parser.text())
    text, spans = _strip_activation_markers(text_with_markers)
    cleaned_text = strip_html_client_warning(text)
    warning_removed = cleaned_text != text
    text = cleaned_text
    links: list[LinkItem] = []
    for link in parser.links:
        start, end = (-1, -1) if warning_removed else spans.get(link.activation_marker, (-1, -1))
        links.append(replace(link, activation_start=start, activation_end=end, activation_marker=""))
    return text, links


def _activation_marker(marker: str, side: str) -> str:
    return f"[[PAM-ACTION-{marker}-{side}]]"


def _strip_activation_markers(text: str) -> tuple[str, dict[str, tuple[int, int]]]:
    parts: list[str] = []
    spans: dict[str, tuple[int, int]] = {}
    open_markers: dict[str, int] = {}
    output_length = 0
    position = 0
    for match in ACTIVATION_MARKER_PATTERN.finditer(text):
        segment = text[position : match.start()]
        parts.append(segment)
        output_length += len(segment)
        marker, side = match.groups()
        if side == "START":
            open_markers[marker] = output_length
        else:
            start = open_markers.pop(marker, None)
            if start is not None and output_length >= start:
                spans[marker] = (start, output_length)
        position = match.end()
    tail = text[position:]
    parts.append(tail)
    return "".join(parts), spans


def _clean_resource_title(text: str, limit: int = 90) -> str:
    text = " ".join(text.split()).strip(" \t\r\n-:،,.;")
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _is_generic_title(text: str, url: str = "") -> bool:
    normalized = " ".join(text.split()).strip().lower()
    return not normalized or normalized == url.lower() or normalized in GENERIC_LINK_TITLES


def _title_from_text_context(text: str, url: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines):
        if url not in line:
            continue
        context = _clean_resource_title(line.replace(url, " "))
        if context and not _is_generic_title(context):
            return context
        for neighbor in (index - 1, index + 1):
            if 0 <= neighbor < len(lines):
                title = _clean_resource_title(lines[neighbor])
                if title and not _is_generic_title(title):
                    return title
    return ""


def unique_links(text: str, links: list[LinkItem]) -> list[LinkItem]:
    seen: set[str] = set()
    seen_without_url: set[tuple[str, str]] = set()
    result: list[LinkItem] = []
    for link in links:
        if link.url:
            if link.url in seen:
                continue
            seen.add(link.url)
            title = _clean_resource_title(link.text)
            activation_text = _clean_resource_title(link.activation_text) or title or link.url
            if _is_generic_title(title, link.url):
                title = _title_from_text_context(text, link.url) or title or link.url
            result.append(
                LinkItem(
                    title,
                    link.url,
                    kind=link.kind,
                    filename=link.filename,
                    content_type=link.content_type,
                    size=link.size,
                    data=link.data,
                    activation_text=activation_text,
                    activation_start=link.activation_start,
                    activation_end=link.activation_end,
                )
            )
            continue
        if link.is_button:
            title = _clean_resource_title(link.text) or "زر بدون عنوان"
            key = (link.kind, title)
            if key not in seen_without_url:
                seen_without_url.add(key)
                result.append(
                    LinkItem(
                        title,
                        kind=link.kind,
                        activation_text=_clean_resource_title(link.activation_text) or title,
                        activation_start=link.activation_start,
                        activation_end=link.activation_end,
                    )
                )
    for match in URL_PATTERN.findall(text):
        url = match.rstrip(").,;]")
        if url not in seen:
            seen.add(url)
            start = text.find(url)
            result.append(
                LinkItem(
                    _title_from_text_context(text, url) or url,
                    url,
                    activation_text=url,
                    activation_start=start,
                    activation_end=start + len(url) if start >= 0 else -1,
                )
            )
    return result


def normalize_message_text(text: str) -> str:
    text = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\t", " ")
        .replace("\u200b", "")
        .replace("\ufeff", "")
    )
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw_line in text.split("\n"):
        line = " ".join(raw_line.split())
        if not line:
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(current)

    cleaned_blocks: list[str] = []
    for lines in blocks:
        if any(LIST_LINE_PATTERN.match(line) for line in lines):
            cleaned_blocks.append("\n".join(lines))
        else:
            cleaned_blocks.append(" ".join(lines))
    return "\n".join(block for block in cleaned_blocks if block).strip()


def looks_like_visual_markup_dump(text: str) -> bool:
    sample = text.strip()[:5000]
    if not sample:
        return False
    score = 0
    if HTML_TAG_PATTERN.search(sample):
        score += 3
    if CSS_BLOCK_PATTERN.search(sample):
        score += 3
    score += min(4, len(CSS_PROPERTY_PATTERN.findall(sample)))
    for marker in ["!important", "-webkit-", "-ms-text-size-adjust", "@media", "font-weight:", "line-height:"]:
        if marker in sample:
            score += 1
    return score >= 4


def is_plain_text_placeholder(text: str) -> bool:
    normalized = " ".join(text.lower().split()).strip(" .:-")
    if not normalized or len(normalized) > 500:
        return False
    return any(phrase in normalized for phrase in PLAIN_TEXT_PLACEHOLDER_PHRASES)


def strip_html_client_warning(text: str) -> str:
    cleaned = text
    for pattern in HTML_CLIENT_WARNING_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    kept_lines = []
    for line in cleaned.splitlines():
        visible_line = ACTIVATION_MARKER_PATTERN.sub("", line)
        if is_plain_text_placeholder(visible_line):
            continue
        kept_lines.append(line)
    return normalize_message_text("\n".join(kept_lines))


def is_attachment_part(part: Message | EmailMessage) -> bool:
    disposition = (part.get_content_disposition() or "").lower()
    filename = part.get_filename()
    return disposition == "attachment" or bool(filename and disposition in {"", "inline"})


def attachment_from_part(part: Message | EmailMessage) -> LinkItem | None:
    filename = header_to_text(part.get_filename()) or "مرفق بدون اسم"
    try:
        payload = part.get_payload(decode=True) or b""
    except Exception:
        payload = b""
    content_type = part.get_content_type() or "application/octet-stream"
    return LinkItem(
        text=filename,
        kind="attachment",
        filename=filename,
        content_type=content_type,
        size=len(payload),
        data=base64.b64encode(payload).decode("ascii") if payload else "",
    )


def extract_body(message: Message | EmailMessage) -> tuple[str, list[LinkItem]]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[LinkItem] = []

    if message.is_multipart():
        for part in message.walk():
            if part.is_multipart():
                continue
            content_type = part.get_content_type()
            if is_attachment_part(part):
                attachment = attachment_from_part(part)
                if attachment:
                    attachments.append(attachment)
                continue
            if content_type not in {"text/plain", "text/html"}:
                continue
            try:
                content = part.get_content()
            except Exception:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                content = payload.decode(charset, errors="replace")
            if content_type == "text/plain":
                text_parts.append(str(content))
            else:
                html_parts.append(str(content))
    else:
        content_type = message.get_content_type()
        try:
            content = message.get_content()
        except Exception:
            payload = message.get_payload(decode=True) or b""
            charset = message.get_content_charset() or "utf-8"
            content = payload.decode(charset, errors="replace")
        if content_type == "text/html":
            html_parts.append(str(content))
        else:
            text_parts.append(str(content))

    html = "\n".join(html_parts)
    html_text = ""
    html_links: list[LinkItem] = []
    if html_parts:
        html_text, html_links = html_to_text_and_links(html)

    if text_parts:
        raw_text = normalize_message_text("\n".join(part.strip() for part in text_parts if part.strip()))
        text = strip_html_client_warning(raw_text)
        if html_text and (not text or looks_like_visual_markup_dump(text) or is_plain_text_placeholder(raw_text)):
            return html_text, unique_links(html_text, html_links) + attachments
        return text or "لا يوجد نص قابل للعرض داخل هذه الرسالة.", unique_links(text, []) + attachments

    return html_text or "لا يوجد نص قابل للعرض داخل هذه الرسالة.", unique_links(html_text, html_links) + attachments
