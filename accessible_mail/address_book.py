from __future__ import annotations

import re
from dataclasses import dataclass
from email.utils import parseaddr

from .config import data_dir
from .address_book_storage import (
    address_connection, address_hash, entry_payload, prepare_storage,
    public_entries, write_public_entries,
)


EMAIL_PATTERN = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")


@dataclass(slots=True)
class AddressEntry:
    email: str
    pinned: bool = False
    name: str = ""

    @property
    def display_label(self) -> str:
        clean_name = " ".join(self.name.split()).strip()
        return f"{clean_name}: {self.email}" if clean_name else self.email


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
    path = address_book_path().with_name("folders.db")
    prepare_storage(path)
    with address_connection(path) as conn:
        return public_entries(conn)


def save_address_book(entries: list[AddressEntry]) -> None:
    clean_entries = unique_address_entries(entries)
    path = address_book_path().with_name("folders.db")
    prepare_storage(path)
    with address_connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        write_public_entries(conn, clean_entries)


def sort_address_book(entries: list[AddressEntry]) -> list[AddressEntry]:
    return sorted(
        entries,
        key=lambda entry: (
            not entry.pinned,
            (entry.name or entry.email).casefold(),
            entry.email.casefold(),
        ),
    )


def unique_address_entries(entries: list[AddressEntry]) -> list[AddressEntry]:
    result: list[AddressEntry] = []
    known: set[str] = set()
    for entry in entries:
        email = normalize_email_address(entry.email)
        key = email.casefold()
        if not email or key in known:
            continue
        known.add(key)
        name = " ".join(str(entry.name or "").split()).strip()
        result.append(AddressEntry(email=email, pinned=bool(entry.pinned), name=name))
    return sort_address_book(result)


def add_address(email: str, name: str = "") -> tuple[bool, str]:
    normalized = normalize_email_address(email)
    if not normalized:
        return False, "invalid"
    clean_name = " ".join(str(name or "").split()).strip()
    path = address_book_path().with_name("folders.db")
    prepare_storage(path)
    with address_connection(path) as conn:
        inserted = conn.execute("INSERT OR IGNORE INTO address_records(entry_hash, payload) VALUES (?, ?)",
                                (address_hash(normalized), entry_payload(AddressEntry(normalized, name=clean_name)))).rowcount
    if not inserted:
        return False, "duplicate"
    return True, normalized
