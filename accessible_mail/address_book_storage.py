"""Address records share the organization DB so password changes are atomic.

Public records are JSON blobs. A protected record is DPAPI ciphertext using the
folder's password-derived entropy; generic address pickers never decrypt it.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .secure_store import ClosingConnection


def address_hash(email: str) -> str:
    return hashlib.sha256(("address\0" + email.casefold()).encode("utf-8")).hexdigest()


def entry_payload(entry) -> bytes:
    return json.dumps({"email": entry.email, "name": entry.name, "pinned": entry.pinned},
                      ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def decode_entry(payload: bytes):
    from .address_book import AddressEntry, normalize_email_address
    item = json.loads(payload.decode("utf-8"))
    if not isinstance(item, dict):
        raise ValueError("بيانات العنوان غير صالحة.")
    email = normalize_email_address(item.get("email", ""))
    if not email:
        raise ValueError("بيانات العنوان غير صالحة.")
    return AddressEntry(email, bool(item.get("pinned", False)),
                        " ".join(str(item.get("name", "")).split()).strip())


@contextmanager
def address_connection(path: Path):
    with sqlite3.connect(path, timeout=30, factory=ClosingConnection) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA synchronous = FULL")
        conn.execute("PRAGMA secure_delete = ON")
        yield conn


def prepare_storage(path: Path) -> None:
    """Import once, commit first, then remove only recognized legacy files.

    Cleanup failure blocks locking, not data recovery. Once the import marker
    exists, stale JSON must never override the DB, even after a failed cleanup.
    No claim is made about forensic erasure on SSDs or external backups.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = path.with_name("address_book.json")
    backup = legacy.with_suffix(".json.bak")
    legacy_files = (legacy, backup, *legacy.parent.glob(".address_book.json.*.tmp"))
    for candidate in legacy_files:
        if candidate.is_symlink():
            raise ValueError("تعذر ترقية سجل العناوين المرتبط بمسار آخر.")
    with address_connection(path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS address_records (
            entry_hash TEXT PRIMARY KEY, payload BLOB NOT NULL,
            lock_account TEXT NOT NULL DEFAULT '', lock_folder TEXT NOT NULL DEFAULT '',
            sealed INTEGER NOT NULL DEFAULT 0
        )""")
        conn.execute("CREATE TABLE IF NOT EXISTS address_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT 1 FROM address_metadata WHERE key = 'json_imported'").fetchone():
            payload = None
            found = False
            for candidate in (legacy, backup):
                if not candidate.exists():
                    continue
                found = True
                try:
                    payload = json.loads(candidate.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(payload, list):
                    break
                payload = None
            if found and payload is None:
                raise ValueError("تعذرت قراءة سجل العناوين القديم؛ لم تُحذف ملفاته.")
            from .address_book import AddressEntry, normalize_email_address, unique_address_entries
            entries = []
            for item in payload or []:
                if isinstance(item, dict):
                    email = normalize_email_address(str(item.get("email", "")))
                    if email:
                        entries.append(AddressEntry(email, bool(item.get("pinned", False)), str(item.get("name", ""))))
            conn.executemany("INSERT OR IGNORE INTO address_records(entry_hash, payload) VALUES (?, ?)",
                             ((address_hash(entry.email), entry_payload(entry)) for entry in unique_address_entries(entries)))
            conn.execute("INSERT INTO address_metadata VALUES ('json_imported', '1')")
            # Old locks only encrypted membership. Hide imported contacts from
            # generic pickers immediately; password verification upgrades their
            # payloads when that folder is first opened. Never discard them.
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'local_lock_hashes'").fetchone():
                locks = conn.execute("""SELECT l.account_id, l.target_id, h.item_hash FROM local_locks l
                    JOIN folders f ON f.id = l.target_id JOIN local_lock_hashes h
                    ON h.target_type = l.target_type AND h.target_id = l.target_id
                    WHERE l.target_type = 'folder' AND f.kind = 'conversations'""").fetchall()
                for record in conn.execute("SELECT entry_hash, payload FROM address_records WHERE lock_folder = ''").fetchall():
                    email = decode_entry(bytes(record["payload"])).email.casefold()
                    for lock in locks:
                        digest = hashlib.sha256((lock["account_id"] + "\0" + email).encode("utf-8")).hexdigest()
                        if digest == lock["item_hash"]:
                            conn.execute("UPDATE address_records SET lock_account = ?, lock_folder = ? WHERE entry_hash = ?",
                                         (lock["account_id"], lock["target_id"], record["entry_hash"]))
                            break
    # Exact known names only; never remove the DB, external backups or directories.
    for candidate in legacy_files:
        if candidate.is_symlink():
            raise ValueError("تعذر ترقية سجل العناوين المرتبط بمسار آخر.")
        candidate.unlink(missing_ok=True)


def public_entries(conn):
    from .address_book import sort_address_book
    return sort_address_book([decode_entry(bytes(row[0])) for row in conn.execute(
        "SELECT payload FROM address_records WHERE lock_folder = ''")])


def write_public_entries(conn, entries) -> None:
    protected = {row[0] for row in conn.execute("SELECT entry_hash FROM address_records WHERE lock_folder != ''")}
    # Stale dialog snapshots cannot write a protected record back in plaintext.
    conn.execute("DELETE FROM address_records WHERE lock_folder = ''")
    conn.executemany("INSERT INTO address_records(entry_hash, payload) VALUES (?, ?)",
                     ((address_hash(entry.email), entry_payload(entry)) for entry in entries
                      if address_hash(entry.email) not in protected))


def seal_addresses(conn, account_id, folder_id, keys, entropy, protect) -> None:
    for key in keys:
        row = conn.execute("SELECT * FROM address_records WHERE entry_hash = ?", (address_hash(key),)).fetchone()
        if row is None:
            continue
        if row["lock_folder"]:
            if (row["lock_account"], row["lock_folder"]) != (account_id, folder_id):
                raise ValueError("العنوان محمي داخل مجلد آخر؛ أزل قفله قبل نقله.")
            if row["sealed"]:
                continue
        if conn.execute("""SELECT 1 FROM folder_items i JOIN folders f ON f.id = i.folder_id
            WHERE f.kind = 'conversations' AND lower(i.item_key) = ? AND f.account_id != ?""",
                        (key.casefold(), account_id)).fetchone():
            raise ValueError("العنوان موجود في مجلد بحساب آخر؛ أزله من ذلك المجلد قبل قفله.")
        blob = protect(bytes(row["payload"]), entropy)
        conn.execute("UPDATE address_records SET payload = ?, lock_account = ?, lock_folder = ?, sealed = 1 WHERE entry_hash = ?",
                     (blob, account_id, folder_id, row["entry_hash"]))


def unseal_addresses(conn, account_id, folder_id, keys, entropy, unprotect) -> None:
    for key in keys:
        row = conn.execute("SELECT payload FROM address_records WHERE entry_hash = ? AND lock_account = ? AND lock_folder = ?",
                           (address_hash(key), account_id, folder_id)).fetchone()
        if row is not None:
            blob = unprotect(bytes(row[0]), entropy)
            if address_hash(decode_entry(blob).email) != address_hash(key):
                raise ValueError("بيانات العنوان المحمي غير صالحة.")
            conn.execute("UPDATE address_records SET payload = ?, lock_account = '', lock_folder = '', sealed = 0 WHERE entry_hash = ?",
                         (blob, address_hash(key)))
