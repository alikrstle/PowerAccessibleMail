from __future__ import annotations

import base64
import hashlib
import mimetypes
import re
import urllib.parse
from dataclasses import replace
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from html.parser import HTMLParser

from .models import LinkItem


URL_PATTERN = re.compile(
    r"(?<![\w@])(?:(?:https?://|mailto:)[^\s<>\"']+|www\.[^\s<>\"']+)",
    re.IGNORECASE,
)
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
    "link",
    "open",
    "visit",
    "view",
    "view online",
    "اضغط هنا",
    "هنا",
    "افتح",
    "فتح",
    "المزيد",
    "اقرأ المزيد",
    "الرابط",
    "cliquez ici",
    "ici",
    "en savoir plus",
    "ouvrir",
    "voir",
    "صورة بدون وصف",
    "image without description",
    "image sans description",
}
SAFE_EXTERNAL_URL_SCHEMES = frozenset({"http", "https", "mailto"})
TRACKING_QUERY_PARAMETERS = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "mkt_tok",
    }
)
HIDDEN_IMAGE_STYLE_MARKERS = ("display:none", "visibility:hidden", "opacity:0")
MAX_EMBEDDED_IMAGE_BYTES = 25 * 1024 * 1024
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
        self._current_link_hints: list[str] = []
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
            self._current_link_hints = [
                value
                for value in (
                    attrs_dict.get("aria-label", ""),
                    attrs_dict.get("title", ""),
                )
                if value
            ]
            self._current_link_marker = self._new_activation_marker() if self._current_href else ""
            if self._current_link_marker:
                self.parts.append(_activation_marker(self._current_link_marker, "START"))
        if tag == "img" and self._current_href:
            self._current_link_hints.extend(
                value
                for value in (
                    attrs_dict.get("aria-label", ""),
                    attrs_dict.get("alt", ""),
                    attrs_dict.get("title", ""),
                )
                if value
            )
        if tag == "img" and _is_useful_html_image(attrs_dict):
            source = _html_image_source(attrs_dict)
            description = _best_image_description(attrs_dict, source)
            image_data, content_type, embedded_filename = _embedded_image_data(source)
            self.links.append(
                LinkItem(
                    text=description,
                    url="" if source.casefold().startswith("data:") else source,
                    kind="image",
                    filename=embedded_filename or _image_filename(source),
                    content_type=content_type,
                    size=len(image_data),
                    data=base64.b64encode(image_data).decode("ascii") if image_data else "",
                    content_id=_normalized_content_id(source[4:] if source.casefold().startswith("cid:") else ""),
                )
            )
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
                label = self._best_link_hint() or self._nearby_context_title(label) or label
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
            self._current_link_hints = []
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

    def _best_link_hint(self) -> str:
        hints = [_clean_resource_title(hint) for hint in self._current_link_hints]
        useful_hints = [hint for hint in hints if not _is_generic_title(hint, self._current_href)]
        if not useful_hints:
            return ""
        return useful_hints[0]

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


def _resource_title_score(text: str, url: str = "") -> tuple[int, int]:
    title = _clean_resource_title(text)
    if not title:
        return (0, 0)
    if _is_generic_title(title, url):
        return (1, len(title))
    if canonical_url_key(title) and canonical_url_key(title) == canonical_url_key(url):
        return (1, len(title))
    return (2, min(len(title), 90))


def _html_image_dimension(value: str) -> float | None:
    match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(?:px)?\s*$", value, re.IGNORECASE)
    return float(match.group(1)) if match else None


def _is_useful_html_image(attrs: dict[str, str]) -> bool:
    source = _html_image_source(attrs)
    if not source:
        return False
    compact_style = re.sub(r"\s+", "", attrs.get("style", "").casefold())
    if any(marker in compact_style for marker in HIDDEN_IMAGE_STYLE_MARKERS):
        return False
    style = attrs.get("style", "")
    width = _html_image_dimension(attrs.get("width", ""))
    height = _html_image_dimension(attrs.get("height", ""))
    if width is None:
        width = _html_style_dimension(style, "width")
    if height is None:
        height = _html_style_dimension(style, "height")
    return not (width is not None and height is not None and width <= 1 and height <= 1)


def _html_style_dimension(style: str, property_name: str) -> float | None:
    match = re.search(
        rf"(?:^|;)\s*{re.escape(property_name)}\s*:\s*(\d+(?:\.\d+)?)\s*(?:px)?(?:\s*[;!]|$)",
        style,
        re.IGNORECASE,
    )
    return float(match.group(1)) if match else None


def _html_image_source(attrs: dict[str, str]) -> str:
    source = attrs.get("src", "").strip()
    lazy_sources = (
        attrs.get("data-src", "").strip(),
        attrs.get("data-original", "").strip(),
        attrs.get("data-lazy-src", "").strip(),
    )
    if not source or source.casefold().startswith("data:"):
        source = next((candidate for candidate in lazy_sources if candidate), source)
    if not source:
        first_source = attrs.get("srcset", "").split(",", 1)[0].strip().split()
        source = first_source[0] if first_source else ""
    if source.startswith("//"):
        source = f"https:{source}"
    return source


def _embedded_image_data(source: str) -> tuple[bytes, str, str]:
    if not source.casefold().startswith("data:image/"):
        return b"", "", ""
    header, separator, payload = source.partition(",")
    if not separator:
        return b"", "", ""
    content_type = header[5:].split(";", 1)[0].casefold()
    try:
        if ";base64" in header.casefold():
            padding = "=" * (-len(payload) % 4)
            data = base64.b64decode(payload + padding, validate=True)
        else:
            data = urllib.parse.unquote_to_bytes(payload)
    except (ValueError, TypeError):
        return b"", "", ""
    if not data or len(data) > MAX_EMBEDDED_IMAGE_BYTES:
        return b"", "", ""
    extension = mimetypes.guess_extension(content_type) or ""
    return data, content_type, f"image{extension}"


def _image_filename(source: str) -> str:
    if not source or source.casefold().startswith(("cid:", "data:")):
        return ""
    try:
        return urllib.parse.unquote(urllib.parse.urlsplit(source).path.rsplit("/", 1)[-1])
    except ValueError:
        return ""


def _normalized_content_id(value: str) -> str:
    return urllib.parse.unquote(str(value or "")).strip().strip("<>").casefold()


def _best_image_description(attrs: dict[str, str], source: str) -> str:
    descriptions = [
        _clean_resource_title(value)
        for value in (
            attrs.get("aria-label", ""),
            attrs.get("alt", ""),
            attrs.get("title", ""),
            _image_filename(source),
        )
    ]
    useful = [description for description in descriptions if description]
    return useful[0] if useful else "صورة بدون وصف"


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


def canonical_url_key(value: object) -> str:
    url = str(value or "").strip()
    if url.lower().startswith("www."):
        url = f"https://{url}"
    try:
        parsed = urllib.parse.urlsplit(url)
        scheme = parsed.scheme.casefold()
        if scheme not in SAFE_EXTERNAL_URL_SCHEMES:
            return url
        if scheme == "mailto":
            return urllib.parse.urlunsplit((scheme, "", parsed.path.casefold(), parsed.query, parsed.fragment))

        hostname = (parsed.hostname or "").casefold()
        if not hostname:
            return url
        try:
            hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError:
            pass
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        port = parsed.port
        if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
            hostname = f"{hostname}:{port}"
        userinfo = parsed.netloc.rpartition("@")[0] if "@" in parsed.netloc else ""
        netloc = f"{userinfo}@{hostname}" if userinfo else hostname
        query_items = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        query = urllib.parse.urlencode(
            [
                (name, value)
                for name, value in query_items
                if not name.casefold().startswith("utm_")
                and name.casefold() not in TRACKING_QUERY_PARAMETERS
            ],
            doseq=True,
        )
        return urllib.parse.urlunsplit((scheme, netloc, parsed.path or "/", query, parsed.fragment))
    except ValueError:
        return url


def _trim_detected_url(value: str) -> str:
    url = value.rstrip(".,;:!?،؛؟»”’]}>")
    while url.endswith(")") and url.count("(") < url.count(")"):
        url = url[:-1]
    return url


def _prepared_link(text: str, link: LinkItem) -> LinkItem:
    title = _clean_resource_title(link.text)
    activation_text = _clean_resource_title(link.activation_text) or title or link.url
    if _is_generic_title(title, link.url):
        title = _title_from_text_context(text, link.url) or title or link.url
    return replace(link, text=title, activation_text=activation_text)


def _merge_duplicate_link(existing: LinkItem, candidate: LinkItem) -> LinkItem:
    title = existing.text
    if _resource_title_score(candidate.text, candidate.url) > _resource_title_score(existing.text, existing.url):
        title = candidate.text
    kind = "button" if existing.is_button or candidate.is_button else existing.kind
    return replace(existing, text=title, kind=kind)


def _attachment_identity(item: LinkItem) -> tuple[object, ...]:
    filename = _clean_resource_title(item.filename or item.text).casefold()
    attachment_bytes = item.attachment_bytes()
    if attachment_bytes:
        return ("content", filename, hashlib.sha256(attachment_bytes).digest())
    return (
        "metadata",
        filename,
        item.content_type.strip().casefold(),
        max(0, int(item.size or 0)),
    )


def _merge_duplicate_attachment(existing: LinkItem, candidate: LinkItem) -> LinkItem:
    return replace(
        existing,
        text=existing.text or candidate.text,
        filename=existing.filename or candidate.filename,
        content_type=existing.content_type or candidate.content_type,
        size=existing.size or candidate.size,
        data=existing.data or candidate.data,
    )


def _image_identity(item: LinkItem) -> tuple[object, ...]:
    content_id = _normalized_content_id(item.content_id)
    if not content_id and item.url.casefold().startswith("cid:"):
        content_id = _normalized_content_id(item.url[4:])
    if content_id:
        return ("content-id", content_id)
    if item.url:
        return ("source", canonical_url_key(item.url))
    attachment_bytes = item.attachment_bytes()
    if attachment_bytes:
        return ("content", hashlib.sha256(attachment_bytes).digest())
    return (
        "description",
        _clean_resource_title(item.text).casefold(),
        _clean_resource_title(item.filename).casefold(),
    )


def _merge_duplicate_image(existing: LinkItem, candidate: LinkItem) -> LinkItem:
    description = existing.text
    if _resource_title_score(candidate.text) > _resource_title_score(existing.text):
        description = candidate.text
    return replace(
        existing,
        text=description,
        filename=existing.filename or candidate.filename,
        content_type=existing.content_type or candidate.content_type,
        size=existing.size or candidate.size,
        data=existing.data or candidate.data,
        content_id=existing.content_id or candidate.content_id,
    )


def organize_message_items(
    text: str,
    items: list[LinkItem],
    *,
    discover_text_links: bool = True,
) -> list[LinkItem]:
    links: list[LinkItem] = []
    link_positions: dict[str, int] = {}
    button_positions: dict[tuple[str, str], int] = {}

    def add_link(link: LinkItem) -> None:
        prepared = _prepared_link(text, link)
        if prepared.url:
            key = canonical_url_key(prepared.url)
            if key in link_positions:
                position = link_positions[key]
                links[position] = _merge_duplicate_link(links[position], prepared)
                return
            link_positions[key] = len(links)
            links.append(prepared)
            return
        if prepared.is_button:
            title = prepared.text or "زر بدون عنوان"
            key = (prepared.kind, title.casefold())
            if key not in button_positions:
                button_positions[key] = len(links)
                links.append(replace(prepared, text=title))

    images: list[LinkItem] = []
    image_positions: dict[tuple[object, ...], int] = {}
    attachments: list[LinkItem] = []
    attachment_positions: dict[tuple[object, ...], int] = {}
    for item in items:
        if item.is_image:
            key = _image_identity(item)
            if key in image_positions:
                position = image_positions[key]
                images[position] = _merge_duplicate_image(images[position], item)
            else:
                image_positions[key] = len(images)
                images.append(item)
            continue
        if item.is_attachment:
            key = _attachment_identity(item)
            if key in attachment_positions:
                position = attachment_positions[key]
                attachments[position] = _merge_duplicate_attachment(attachments[position], item)
            else:
                attachment_positions[key] = len(attachments)
                attachments.append(item)
            continue
        add_link(item)

    if discover_text_links:
        for match in URL_PATTERN.finditer(text):
            visible_url = _trim_detected_url(match.group(0))
            if not visible_url:
                continue
            url = f"https://{visible_url}" if visible_url.lower().startswith("www.") else visible_url
            start = match.start()
            add_link(
                LinkItem(
                    _title_from_text_context(text, visible_url) or visible_url,
                    url,
                    activation_text=visible_url,
                    activation_start=start,
                    activation_end=start + len(visible_url),
                )
            )

    return links + images + attachments


def unique_links(text: str, links: list[LinkItem]) -> list[LinkItem]:
    return organize_message_items(text, links)


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


def is_inline_image_part(part: Message | EmailMessage) -> bool:
    disposition = (part.get_content_disposition() or "").lower()
    content_id = _normalized_content_id(header_to_text(part.get("Content-ID")))
    return part.get_content_type().casefold().startswith("image/") and disposition == "inline" and bool(content_id)


def attachment_from_part(part: Message | EmailMessage) -> LinkItem | None:
    content_type = part.get_content_type() or "application/octet-stream"
    content_id = _normalized_content_id(header_to_text(part.get("Content-ID")))
    inline_image = is_inline_image_part(part)
    filename = header_to_text(part.get_filename())
    if not filename and inline_image:
        filename = f"image{mimetypes.guess_extension(content_type) or ''}"
    filename = filename or "مرفق بدون اسم"
    try:
        payload = part.get_payload(decode=True) or b""
    except Exception:
        payload = b""
    return LinkItem(
        text=filename,
        kind="image" if inline_image else "attachment",
        filename=filename,
        content_type=content_type,
        size=len(payload),
        data=base64.b64encode(payload).decode("ascii") if payload else "",
        content_id=content_id,
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
            if is_attachment_part(part) or is_inline_image_part(part):
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
            return html_text, organize_message_items(html_text, html_links + attachments)
        body = text or "لا يوجد نص قابل للعرض داخل هذه الرسالة."
        return body, organize_message_items(body, html_links + attachments)

    body = html_text or "لا يوجد نص قابل للعرض داخل هذه الرسالة."
    return body, organize_message_items(body, html_links + attachments)
