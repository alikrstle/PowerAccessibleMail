from __future__ import annotations

import re
from dataclasses import dataclass
from email.utils import parseaddr

from .config import _atomic_write_json, _read_json_with_backup, data_dir


EMAIL_PATTERN = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")


@dataclass(slots=True)
class AddressEntry:
    email: str
    pinned: bool = False


def normalize_email_address(value: str) -> str:
    value = " ".join(str(value or "").split()).strip()
    if not value or "," in value or ";" in value:
        return ""
    display_name, address = parseaddr(value)
    if display_name or address != value:
        value = address.strip()
    if not EMAIL_PATTERN.fullmatch(value):
        return ""
    return value


def address_book_path():
    return data_dir() / "address_book.json"


def load_address_book() -> list[AddressEntry]:
    payload = _read_json_with_backup(address_book_path())
    if not isinstance(payload, list):
        return []
    entries: list[AddressEntry] = []
    known: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        email = normalize_email_address(str(item.get("email", "")))
        key = email.casefold()
        if not email or key in known:
            continue
        known.add(key)
        entries.append(AddressEntry(email=email, pinned=bool(item.get("pinned", False))))
    return sort_address_book(entries)


def save_address_book(entries: list[AddressEntry]) -> None:
    clean_entries = unique_address_entries(entries)
    _atomic_write_json(
        address_book_path(),
        [
            {"email": entry.email, "pinned": entry.pinned}
            for entry in clean_entries
        ],
    )


def sort_address_book(entries: list[AddressEntry]) -> list[AddressEntry]:
    return sorted(entries, key=lambda entry: (not entry.pinned, entry.email.casefold()))


def unique_address_entries(entries: list[AddressEntry]) -> list[AddressEntry]:
    result: list[AddressEntry] = []
    known: set[str] = set()
    for entry in entries:
        email = normalize_email_address(entry.email)
        key = email.casefold()
        if not email or key in known:
            continue
        known.add(key)
        result.append(AddressEntry(email=email, pinned=bool(entry.pinned)))
    return sort_address_book(result)


def add_address(email: str) -> tuple[bool, str]:
    normalized = normalize_email_address(email)
    if not normalized:
        return False, "invalid"
    entries = load_address_book()
    if any(entry.email.casefold() == normalized.casefold() for entry in entries):
        return False, "duplicate"
    entries.append(AddressEntry(normalized))
    save_address_book(entries)
    return True, normalized
