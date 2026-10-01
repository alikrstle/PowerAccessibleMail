from __future__ import annotations

import base64
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CustomCategory:
    id: str
    name: str
    rules: tuple[str, ...] = ()
    email_addresses: tuple[str, ...] = ()


def clean_category_name(name: str) -> str:
    value = name.strip()
    if not value or len(value) > 100 or any(ord(char) < 32 for char in value):
        raise ValueError("اسم التصنيف يجب أن يكون بين حرف واحد و100 حرف دون أسطر جديدة.")
    return value


def encode_imap_mailbox(name: str) -> str:
    """IMAP modified UTF-7, used for non-ASCII mailbox names without UTF8=ACCEPT."""
    result: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        if pending:
            encoded = base64.b64encode("".join(pending).encode("utf-16-be"))
            result.append("&" + encoded.decode("ascii").rstrip("=").replace("/", ",") + "-")
            pending.clear()

    for char in name:
        if 0x20 <= ord(char) <= 0x7e:
            flush()
            result.append("&-" if char == "&" else char)
        else:
            pending.append(char)
    flush()
    return "".join(result)


def decode_imap_mailbox(name: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(name):
        if name[index] != "&":
            result.append(name[index])
            index += 1
            continue
        end = name.find("-", index + 1)
        if end < 0:
            result.append(name[index:])
            break
        encoded = name[index + 1 : end].replace(",", "/")
        if not encoded:
            result.append("&")
        else:
            try:
                data = base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True)
                result.append(data.decode("utf-16-be"))
            except (ValueError, UnicodeError):
                result.append(name[index : end + 1])
        index = end + 1
    return "".join(result)
