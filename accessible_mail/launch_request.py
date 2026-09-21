from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote, urlsplit


MAX_MAILTO_LENGTH = 32_768
MAX_MAILTO_QUERY_FIELDS = 100


@dataclass(frozen=True, slots=True)
class MailtoRequest:
    to_address: str = ""
    subject: str = ""
    body: str = ""


def _single_line(value: str) -> str:
    return " ".join(value.replace("\x00", "").splitlines()).strip()


def _body_text(value: str) -> str:
    return value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")


def parse_mailto_uri(uri: str) -> MailtoRequest | None:
    if not isinstance(uri, str) or not uri or len(uri) > MAX_MAILTO_LENGTH:
        return None
    try:
        parsed = urlsplit(uri)
    except ValueError:
        return None
    if parsed.scheme.casefold() != "mailto" or parsed.fragment:
        return None

    recipients: list[str] = []
    path_recipient = _single_line(unquote(parsed.path, encoding="utf-8", errors="replace"))
    if path_recipient:
        recipients.append(path_recipient)

    subject = ""
    body = ""
    try:
        fields = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            encoding="utf-8",
            errors="replace",
            max_num_fields=MAX_MAILTO_QUERY_FIELDS,
        )
    except ValueError:
        return None
    for raw_name, value in fields:
        name = raw_name.casefold()
        if name == "to":
            recipient = _single_line(value)
            if recipient:
                recipients.append(recipient)
        elif name == "subject" and not subject:
            subject = _single_line(value)
        elif name == "body" and not body:
            body = _body_text(value)

    return MailtoRequest(
        to_address=", ".join(recipients),
        subject=subject,
        body=body,
    )


def mailto_request_from_arguments(arguments: Sequence[str]) -> MailtoRequest | None:
    for argument in arguments:
        request = parse_mailto_uri(argument)
        if request is not None:
            return request
    return None
