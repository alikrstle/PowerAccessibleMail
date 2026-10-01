from __future__ import annotations

import json
import hashlib
import os
import re
import sqlite3
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .config import data_dir
from .secure_store import ClosingConnection, protect_bytes, unprotect_bytes
from .models import MessageSummary
from .custom_categories import CustomCategory, clean_category_name
from .address_book_storage import (
    address_hash, decode_entry, entry_payload, prepare_storage,
    seal_addresses, unseal_addresses,
)


FOLDER_MESSAGES = "messages"
FOLDER_CONVERSATIONS = "conversations"
FOLDER_KINDS = {FOLDER_MESSAGES, FOLDER_CONVERSATIONS}
CATEGORY_FILTER_RULES = frozenset({
    "recent_read", "attachments", "no_attachments", "promotional",
    "organization", "specific_email", "frequent_sender",
    "locked_messages", "message_folders",
})


class ProtectedAddressBookError(ValueError):
    """Removing the account would orphan password-protected address records."""


@dataclass(frozen=True, slots=True)
class Folder:
    id: str
    account_id: str
    kind: str
    name: str
    pinned: bool = False
    starred: bool = False
    archived: bool = False
    category_id: str | None = None
    section_key: str = ""
    created_at: float = 0.0
    item_count: int = 0
    section_id: str | None = None
    locked: bool = False


@dataclass(frozen=True, slots=True)
class LocalSection:
    id: str
    account_id: str
    name: str
    locked: bool = False


def clean_folder_name(name: str) -> str:
    value = name.strip()
    if not value or len(value) > 100 or any(ord(char) < 32 for char in value):
        raise ValueError("اسم المجلد يجب أن يكون بين حرف واحد و100 حرف دون أسطر جديدة.")
    return value


def message_folder_key(summary: MessageSummary) -> str:
    return json.dumps([summary.mailbox, summary.uid], ensure_ascii=False, separators=(",", ":"))


def parse_message_folder_key(key: str) -> tuple[str, str] | None:
    try:
        value = json.loads(key)
    except (TypeError, ValueError):
        return None
    if (
        isinstance(value, list) and len(value) == 2
        and all(isinstance(part, str) and part for part in value)
    ):
        return value[0], value[1]
    return None


class FolderStore:
    """Local grouping only: deleting a folder never touches server messages."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else data_dir() / "folders.db"
        self._unlocked: dict[tuple[str, str], tuple[dict, bytes]] = {}
        self._message_cache = None
        self._global_uid_accounts: set[str] = set()
        self._configured_accounts: set[str] = set()
        self._addresses_ready = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS folders (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK (kind IN ('messages', 'conversations')),
                    name TEXT NOT NULL,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    starred INTEGER NOT NULL DEFAULT 0,
                    archived INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(account_id, kind, name)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS folder_items (
                    folder_id TEXT NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
                    item_key TEXT NOT NULL,
                    PRIMARY KEY (folder_id, item_key)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS category_items (
                    category_id TEXT NOT NULL REFERENCES local_categories(id) ON DELETE CASCADE,
                    item_key TEXT NOT NULL,
                    PRIMARY KEY (category_id, item_key)
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_folders_account_kind "
                "ON folders(account_id, kind, archived, pinned)"
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS local_categories (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    UNIQUE(account_id, name)
                )"""
            )
            category_columns = {row[1] for row in conn.execute("PRAGMA table_info(local_categories)")}
            if "rules_json" not in category_columns:
                conn.execute("ALTER TABLE local_categories ADD COLUMN rules_json TEXT NOT NULL DEFAULT '[]'")
            if "emails_json" not in category_columns:
                conn.execute("ALTER TABLE local_categories ADD COLUMN emails_json TEXT NOT NULL DEFAULT '[]'")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS read_events (
                    account_id TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    read_at REAL NOT NULL,
                    PRIMARY KEY (account_id, item_key)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS local_sections (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    UNIQUE(account_id, name)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS section_items (
                    section_id TEXT NOT NULL REFERENCES local_sections(id) ON DELETE CASCADE,
                    item_key TEXT NOT NULL,
                    PRIMARY KEY (section_id, item_key)
                )"""
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(folders)")}
            if "category_id" not in columns:
                conn.execute("ALTER TABLE folders ADD COLUMN category_id TEXT")
            if "section_key" not in columns:
                conn.execute("ALTER TABLE folders ADD COLUMN section_key TEXT NOT NULL DEFAULT ''")
            if "created_at" not in columns:
                conn.execute("ALTER TABLE folders ADD COLUMN created_at REAL NOT NULL DEFAULT 0")
            if "section_id" not in columns:
                conn.execute("ALTER TABLE folders ADD COLUMN section_id TEXT")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS local_locks (
                    target_type TEXT NOT NULL CHECK (target_type IN ('folder', 'section')),
                    target_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    salt BLOB NOT NULL,
                    payload BLOB NOT NULL,
                    item_count INTEGER NOT NULL,
                    PRIMARY KEY (target_type, target_id)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS local_lock_hashes (
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    item_hash TEXT NOT NULL,
                    PRIMARY KEY (target_type, target_id, item_hash)
                )"""
            )
            conn.execute("CREATE TABLE IF NOT EXISTS global_uid_accounts (account_id TEXT PRIMARY KEY)")
            conn.execute("CREATE TABLE IF NOT EXISTS message_identities (account_id TEXT NOT NULL, mailbox TEXT NOT NULL, uid TEXT NOT NULL, identity_hash TEXT NOT NULL, PRIMARY KEY(account_id, mailbox, uid))")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_message_identities_hash ON message_identities(account_id, identity_hash)")
            if "uid_validity" not in {row[1] for row in conn.execute("PRAGMA table_info(message_identities)")}:
                conn.execute("ALTER TABLE message_identities ADD COLUMN uid_validity TEXT NOT NULL DEFAULT ''")
            self._global_uid_accounts = {row[0] for row in conn.execute("SELECT account_id FROM global_uid_accounts")}

    def configure_account(self, account) -> None:
        global_uid = account.oauth_provider == "google_gmail_api"
        if account.id in self._configured_accounts and global_uid == self.uses_global_uid(account.id):
            return
        with self._connect() as conn:
            if global_uid:
                conn.execute("INSERT OR IGNORE INTO global_uid_accounts VALUES (?)", (account.id,))
                self._global_uid_accounts.add(account.id)
            else:
                conn.execute("DELETE FROM global_uid_accounts WHERE account_id = ?", (account.id,))
                conn.execute("DELETE FROM local_lock_hashes WHERE account_id = ? AND item_hash LIKE 'uid:%'", (account.id,))
                self._global_uid_accounts.discard(account.id)
        self._configured_accounts.add(account.id)

    def uses_global_uid(self, account_id: str) -> bool:
        return account_id in self._global_uid_accounts

    def register_message_identities(self, account_id: str, summaries: list[MessageSummary]) -> set[tuple[str, str]]:
        conflicts = set()
        with self._connect() as conn:
            for summary in summaries:
                if not summary.message_id and not summary.uid_validity:
                    continue
                identity = self.locked_key_hash(account_id, summary.message_id) if summary.message_id else ""
                old = conn.execute("SELECT identity_hash, uid_validity FROM message_identities WHERE account_id = ? AND mailbox = ? AND uid = ?",
                                   (account_id, summary.mailbox, summary.uid)).fetchone()
                exact = self.locked_key_hash(account_id, message_folder_key(summary))
                protected = conn.execute("SELECT 1 FROM local_lock_hashes WHERE account_id = ? AND item_hash IN (?, ?)",
                                         (account_id, exact, "mid:" + str(old[0]) if old else "")).fetchone()
                if old and protected and ((old[0] and identity and old[0] != identity) or (old[1] and summary.uid_validity and old[1] != summary.uid_validity)):
                    conflicts.add((summary.mailbox, summary.uid))
                    continue
                conn.execute("INSERT OR REPLACE INTO message_identities VALUES (?, ?, ?, ?, ?)",
                             (account_id, summary.mailbox, summary.uid, identity or (old[0] if old else ""), summary.uid_validity or (old[1] if old else "")))
        return conflicts

    def message_identity_matches(self, account_id: str, summary: MessageSummary) -> bool:
        if not summary.message_id and not summary.uid_validity:
            return True
        with self._connect() as conn:
            row = conn.execute("SELECT identity_hash, uid_validity FROM message_identities WHERE account_id = ? AND mailbox = ? AND uid = ?",
                               (account_id, summary.mailbox, summary.uid)).fetchone()
        return row is None or (
            (not row[0] or not summary.message_id or row[0] == self.locked_key_hash(account_id, summary.message_id))
            and (not row[1] or not summary.uid_validity or row[1] == summary.uid_validity)
        )

    def message_alias_pairs(self, account_id: str, keys: list[str], connection=None) -> set[tuple[str, str]]:
        pairs = {parsed for key in keys if (parsed := parse_message_folder_key(key)) is not None}
        if not pairs:
            return pairs
        with self._connect() if connection is None else nullcontext(connection) as conn:
            hashes = sorted({str(row["identity_hash"]) for row in self._identity_rows(conn, account_id, pairs)
                             if row["identity_hash"]})
            for offset in range(0, len(hashes), 400):
                chunk = hashes[offset:offset + 400]
                placeholders = ",".join("?" for _value in chunk)
                pairs.update((str(row[0]), str(row[1])) for row in conn.execute(
                    "SELECT mailbox, uid FROM message_identities WHERE account_id = ? "
                    f"AND identity_hash IN ({placeholders})", (account_id, *chunk)))
        return pairs

    @staticmethod
    def _identity_rows(conn, account_id: str, pairs: set[tuple[str, str]]) -> list[sqlite3.Row]:
        """Batch identity lookups; both account scope and user values stay bound."""
        ordered = sorted(pairs)
        result = []
        for offset in range(0, len(ordered), 400):
            chunk = ordered[offset:offset + 400]
            placeholders = ",".join("(?,?)" for _pair in chunk)
            result.extend(conn.execute(
                "SELECT mailbox, uid, identity_hash FROM message_identities WHERE account_id = ? "
                f"AND (mailbox, uid) IN (VALUES {placeholders})",
                (account_id, *(value for pair in chunk for value in pair)),
            ).fetchall())
        return result

    def has_message_reference(self, account_id: str, mailbox: str, uid: str) -> bool:
        key = json.dumps([mailbox, uid], ensure_ascii=False, separators=(",", ":"))
        if self.lock_context_for_message(account_id, mailbox, uid)[0]:
            return True
        return key in self.message_folder_keys(account_id) or key in self.section_message_keys(account_id)

    def migrate_message_reference(self, account_id: str, mailbox: str, uid: str, new_mailbox: str, new_uid: str, uid_validity: str = "") -> None:
        old = json.dumps([mailbox, uid], ensure_ascii=False, separators=(",", ":"))
        new = json.dumps([new_mailbox, new_uid], ensure_ascii=False, separators=(",", ":"))
        sessions = []
        with self._connect() as conn:
            if self._message_cache is not None:
                self._message_cache.relocate_row(conn, account_id, mailbox, uid, new_mailbox, new_uid, uid_validity)
            conn.execute("INSERT OR REPLACE INTO message_identities SELECT account_id, ?, ?, identity_hash, ? "
                         "FROM message_identities WHERE account_id = ? AND mailbox = ? AND uid = ?",
                         (new_mailbox, new_uid, uid_validity, account_id, mailbox, uid))
            conn.execute("DELETE FROM message_identities WHERE account_id = ? AND mailbox = ? AND uid = ?",
                         (account_id, mailbox, uid))
            for table, parent, owner in (("folder_items", "folder_id", "folders"),
                                        ("section_items", "section_id", "local_sections"),
                                        ("category_items", "category_id", "local_categories")):
                conn.execute(f"INSERT OR IGNORE INTO {table}({parent}, item_key) "
                             f"SELECT {parent}, ? FROM {table} WHERE item_key = ? AND {parent} IN "
                             f"(SELECT id FROM {owner} WHERE account_id = ?)", (new, old, account_id))
                conn.execute(f"DELETE FROM {table} WHERE item_key = ? AND {parent} IN "
                             f"(SELECT id FROM {owner} WHERE account_id = ?)", (old, account_id))
            conn.execute("UPDATE OR REPLACE read_events SET item_key = ? WHERE account_id = ? AND item_key = ?", (new, account_id, old))
            for (kind, target_id), (contents, entropy) in list(self._unlocked.items()):
                all_keys = [*contents["keys"], *(key for items in contents["folders"].values() for key in items)]
                if old not in all_keys:
                    continue
                replacement = {"keys": [new if key == old else key for key in contents["keys"]],
                               "folders": {folder: [new if key == old else key for key in items]
                                           for folder, items in contents["folders"].items()}}
                self._write_open_target(conn, account_id, kind, target_id, replacement, entropy)
                sessions.append(((kind, target_id), (replacement, entropy)))
        self._unlocked.update(sessions)

    @staticmethod
    def _lock_entropy(password: str, salt: bytes) -> bytes:
        if len(password) < 8:
            raise ValueError("كلمة مرور القفل يجب أن تتكون من 8 أحرف على الأقل.")
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 300_000)

    @staticmethod
    def locked_key_hash(account_id: str, item_key: str) -> str:
        return hashlib.sha256((account_id + "\0" + item_key).encode("utf-8")).hexdigest()

    def _indexed_hashes(self, account_id: str, keys: list[str], connection=None) -> set[str]:
        result = {self.locked_key_hash(account_id, key) for key in keys}
        pairs = {parsed for key in keys if (parsed := parse_message_folder_key(key)) is not None}
        if self.uses_global_uid(account_id):
            result.update("uid:" + self.locked_key_hash(account_id, uid) for _mailbox, uid in pairs)
        if pairs:
            with self._connect() if connection is None else nullcontext(connection) as conn:
                result.update("mid:" + str(row["identity_hash"]) for row in self._identity_rows(conn, account_id, pairs)
                              if row["identity_hash"])
        return result

    def locked_message_hashes(self, account_id: str) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT item_hash FROM local_lock_hashes WHERE account_id = ?", (account_id,),
            ).fetchall()
        return {str(row[0]) for row in rows}

    def has_any_locks(self) -> bool:
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM local_locks LIMIT 1").fetchone() is not None

    def lock_context_for_message(
        self, account_id: str, mailbox: str, uid: str,
    ) -> tuple[bool, bytes | None]:
        key = json.dumps([mailbox, uid], ensure_ascii=False, separators=(",", ":"))
        hashes = self._indexed_hashes(account_id, [key])
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT target_type, target_id FROM local_lock_hashes "
                f"WHERE account_id = ? AND item_hash IN ({','.join('?' for _ in hashes)})",
                (account_id, *hashes),
            ).fetchall()
        targets = {(str(row["target_type"]), str(row["target_id"])) for row in rows}
        if not targets:
            return False, None
        if len(targets) > 1:
            return True, None
        target = next(iter(targets))
        session = self._unlocked.get(target)
        return True, session[1] if session else None

    def open_lock_material(self, target_type: str, target_id: str) -> tuple[list[str], bytes]:
        session = self._unlocked.get((target_type, target_id))
        if session is None:
            raise ValueError("افتح القفل بكلمة المرور أولاً.")
        contents, entropy = session
        return [*contents["keys"], *(key for items in contents["folders"].values() for key in items)], entropy

    def set_message_cache(self, cache: object) -> None:
        self._message_cache = cache

    def is_locked(self, account_id: str, target_type: str, target_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM local_locks WHERE account_id = ? AND target_type = ? AND target_id = ?",
                (account_id, target_type, target_id),
            ).fetchone()
        return row is not None

    def is_open(self, account_id: str, target_type: str, target_id: str) -> bool:
        return (target_type, target_id) in self._unlocked or not self.is_locked(account_id, target_type, target_id)

    def prepare_address_storage(self) -> None:
        if not self._addresses_ready:
            prepare_storage(self.path)
            self._addresses_ready = True

    def protected_address_hashes(self) -> set[str]:
        self.prepare_address_storage()
        with self._connect() as conn:
            return {str(row[0]) for row in conn.execute("SELECT entry_hash FROM address_records WHERE lock_folder != ''")}

    def folder_addresses(self, account_id: str, folder_id: str) -> list:
        folder = self.get_folder(account_id, folder_id)
        if folder.kind != FOLDER_CONVERSATIONS:
            raise ValueError("هذا المجلد ليس مجلد عناوين.")
        keys = self.list_items(account_id, folder_id)
        self.prepare_address_storage()
        session = self._unlocked.get(("folder", folder_id))
        entries = []
        with self._connect() as conn:
            for key in keys:
                row = conn.execute("SELECT * FROM address_records WHERE entry_hash = ?", (address_hash(key),)).fetchone()
                if row is None:
                    continue
                blob = bytes(row["payload"])
                if row["lock_folder"]:
                    if session is None or (row["lock_account"], row["lock_folder"]) != (account_id, folder_id):
                        raise ValueError("افتح قفل المجلد أولاً.")
                    blob = unprotect_bytes(blob, session[1])
                entry = decode_entry(blob)
                if address_hash(entry.email) != address_hash(key):
                    raise ValueError("بيانات العنوان غير صالحة.")
                entries.append(entry)
        return entries

    def save_folder_address(self, account_id: str, folder_id: str, entry, *, previous_email: str = "") -> None:
        """Add/edit a contact and its membership in one transaction."""
        from .address_book import unique_address_entries
        clean = unique_address_entries([entry])
        if not clean:
            raise ValueError("عنوان البريد الإلكتروني غير صالح.")
        entry = clean[0]
        folder = self.get_folder(account_id, folder_id)
        if folder.kind != FOLDER_CONVERSATIONS:
            raise ValueError("هذا المجلد ليس مجلد عناوين.")
        self.prepare_address_storage()
        old_key, new_key = previous_email.casefold(), entry.email.casefold()
        keys = self.list_items(account_id, folder_id)
        if old_key and old_key not in keys:
            raise ValueError("العنوان غير موجود في هذا المجلد.")
        session = self._unlocked.get(("folder", folder_id)) if folder.locked else None
        contents = {"keys": list(dict.fromkeys([new_key if key == old_key else key for key in keys] + [new_key])), "folders": {}}
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM address_records WHERE entry_hash = ?", (address_hash(new_key),)).fetchone()
            if row is not None and old_key != new_key:
                raise ValueError("عنوان البريد الإلكتروني موجود بالفعل في سجل العناوين.")
            if row is not None and row["lock_folder"] and (row["lock_account"], row["lock_folder"]) != (account_id, folder_id):
                raise ValueError("العنوان محمي داخل مجلد آخر.")
            if session is not None and conn.execute("""SELECT 1 FROM folder_items i JOIN folders f ON f.id = i.folder_id
                WHERE f.kind = 'conversations' AND i.item_key = ? AND f.account_id != ?""", (new_key, account_id)).fetchone():
                raise ValueError("العنوان موجود في مجلد بحساب آخر؛ أزله من ذلك المجلد قبل قفله.")
            if old_key and old_key != new_key:
                conn.execute("DELETE FROM address_records WHERE entry_hash = ?", (address_hash(old_key),))
                conn.execute("DELETE FROM folder_items WHERE item_key = ? AND folder_id IN (SELECT id FROM folders WHERE kind = ?)",
                             (old_key, FOLDER_CONVERSATIONS))
            blob = entry_payload(entry)
            if session is not None:
                blob = protect_bytes(blob, session[1])
            conn.execute("INSERT OR REPLACE INTO address_records VALUES (?, ?, ?, ?, ?)",
                         (address_hash(new_key), blob, account_id if session else '', folder_id if session else '', int(session is not None)))
            if session is not None:
                self._write_open_target(conn, account_id, "folder", folder_id, contents, session[1])
            else:
                self._add_items(conn, folder_id, [new_key])
        if session is not None:
            self._unlocked[("folder", folder_id)] = (contents, session[1])

    def delete_folder_address(self, account_id: str, folder_id: str, email: str) -> None:
        folder = self.get_folder(account_id, folder_id)
        if folder.kind != FOLDER_CONVERSATIONS:
            raise ValueError("هذا المجلد ليس مجلد عناوين.")
        self.prepare_address_storage()
        key = email.casefold()
        keys = self.list_items(account_id, folder_id)
        if key not in keys:
            raise ValueError("العنوان غير موجود في هذا المجلد.")
        session = self._unlocked.get(("folder", folder_id)) if folder.locked else None
        contents = {"keys": [item for item in keys if item != key], "folders": {}}
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT lock_account, lock_folder FROM address_records WHERE entry_hash = ?", (address_hash(key),)).fetchone()
            if row is not None and row["lock_folder"] and (row["lock_account"], row["lock_folder"]) != (account_id, folder_id):
                raise ValueError("العنوان محمي داخل مجلد آخر.")
            conn.execute("DELETE FROM address_records WHERE entry_hash = ?", (address_hash(key),))
            conn.execute("DELETE FROM folder_items WHERE item_key = ? AND folder_id IN (SELECT id FROM folders WHERE kind = ?)",
                         (key, FOLDER_CONVERSATIONS))
            if session is not None:
                self._write_open_target(conn, account_id, "folder", folder_id, contents, session[1])
        if session is not None:
            self._unlocked[("folder", folder_id)] = (contents, session[1])

    def lock_target(self, account_id: str, target_type: str, target_id: str, password: str) -> None:
        if target_type not in {"folder", "section"}:
            raise ValueError("نوع القفل غير صالح.")
        salt = os.urandom(16)
        entropy = self._lock_entropy(password, salt)
        conversation = target_type == "folder" and self.get_folder(account_id, target_id).kind == FOLDER_CONVERSATIONS
        if conversation:
            self.prepare_address_storage()
        if self._message_cache is not None:
            self._message_cache.prime_message_identities(account_id)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            table = "folders" if target_type == "folder" else "local_sections"
            if conn.execute(f"SELECT 1 FROM {table} WHERE account_id = ? AND id = ?", (account_id, target_id)).fetchone() is None:
                raise ValueError("العنصر غير موجود في هذا الحساب.")
            if conn.execute("SELECT 1 FROM local_locks WHERE target_type = ? AND target_id = ?", (target_type, target_id)).fetchone():
                raise ValueError("العنصر مقفول بالفعل.")
            if target_type == "folder":
                folder = conn.execute("SELECT kind, section_id FROM folders WHERE id = ?", (target_id,)).fetchone()
                if folder["section_id"] and self.is_locked(account_id, "section", str(folder["section_id"])):
                    raise ValueError("افتح قفل القسم أولاً.")
                rows = conn.execute("SELECT item_key FROM folder_items WHERE folder_id = ? ORDER BY rowid", (target_id,)).fetchall()
                folder_items: dict[str, list[str]] = {}
            else:
                child = conn.execute(
                    """SELECT 1 FROM local_locks l JOIN folders f ON f.id = l.target_id
                       WHERE l.target_type = 'folder' AND f.account_id = ? AND f.section_id = ?""",
                    (account_id, target_id),
                ).fetchone()
                if child:
                    raise ValueError("افتح أقفال المجلدات داخل القسم قبل قفل القسم.")
                rows = conn.execute("SELECT item_key FROM section_items WHERE section_id = ? ORDER BY rowid", (target_id,)).fetchall()
                folder_items = {
                    str(row["id"]): [str(item[0]) for item in conn.execute(
                        "SELECT item_key FROM folder_items WHERE folder_id = ? ORDER BY rowid", (row["id"],),
                    ).fetchall()]
                    for row in conn.execute(
                        "SELECT id FROM folders WHERE account_id = ? AND kind = ? AND section_id = ?",
                        (account_id, FOLDER_MESSAGES, target_id),
                    ).fetchall()
                }
            keys = [str(row[0]) for row in rows]
            all_keys = [*keys, *(item for items in folder_items.values() for item in items)]
            for item_hash in self._indexed_hashes(account_id, all_keys):
                if conn.execute(
                    "SELECT 1 FROM local_lock_hashes WHERE account_id = ? AND item_hash = ?",
                    (account_id, item_hash),
                ).fetchone():
                    raise ValueError("بعض الرسائل موجودة في قفل آخر؛ أزل تداخل المجلدات أو الأقسام أولاً.")
            contents = {"keys": keys, "folders": folder_items}
            payload = protect_bytes(json.dumps(contents, ensure_ascii=False).encode("utf-8"), entropy)
            if conversation:
                seal_addresses(conn, account_id, target_id, keys, entropy, protect_bytes)
            if self._message_cache is not None:
                self._message_cache.transform_locked_rows(conn, account_id, all_keys, entropy, seal=True)
            conn.execute(
                "INSERT INTO local_locks VALUES (?, ?, ?, ?, ?, ?)",
                (target_type, target_id, account_id, salt, payload,
                 len(keys) + sum(len(items) for items in folder_items.values())),
            )
            conn.executemany(
                "INSERT OR IGNORE INTO local_lock_hashes VALUES (?, ?, ?, ?)",
                ((target_type, target_id, account_id, item_hash)
                 for item_hash in self._indexed_hashes(
                     account_id, [*keys, *(item for items in folder_items.values() for item in items)],
                 )),
            )
            if target_type == "folder":
                conn.execute("DELETE FROM folder_items WHERE folder_id = ?", (target_id,))
            else:
                conn.execute("DELETE FROM section_items WHERE section_id = ?", (target_id,))
                conn.execute(
                    "DELETE FROM folder_items WHERE folder_id IN "
                    "(SELECT id FROM folders WHERE account_id = ? AND section_id = ?)",
                    (account_id, target_id),
                )

    def unlock_target(self, account_id: str, target_type: str, target_id: str, password: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT salt, payload FROM local_locks WHERE account_id = ? AND target_type = ? AND target_id = ?",
                (account_id, target_type, target_id),
            ).fetchone()
        if row is None:
            raise ValueError("العنصر غير مقفول.")
        entropy = self._lock_entropy(password, bytes(row["salt"]))
        try:
            contents = json.loads(unprotect_bytes(bytes(row["payload"]), entropy).decode("utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise ValueError("كلمة مرور القفل غير صحيحة أو تعذر فك البيانات.") from exc
        if (
            not isinstance(contents, dict)
            or not isinstance(contents.get("keys"), list)
            or not isinstance(contents.get("folders"), dict)
            or any(not isinstance(key, str) for key in contents["keys"])
            or any(not isinstance(items, list) or any(not isinstance(key, str) for key in items)
                   for items in contents["folders"].values())
        ):
            raise ValueError("بيانات القفل غير صالحة.")
        conversation = target_type == "folder" and self.get_folder(account_id, target_id).kind == FOLDER_CONVERSATIONS
        if conversation:
            self.prepare_address_storage()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute("SELECT salt, payload FROM local_locks WHERE account_id = ? AND target_type = ? AND target_id = ?",
                                   (account_id, target_type, target_id)).fetchone()
            if current is None or bytes(current["payload"]) != bytes(row["payload"]) or bytes(current["salt"]) != bytes(row["salt"]):
                raise ValueError("تغيّر القفل أثناء فتحه؛ حاول فتحه مجدداً.")
            if conversation:
                seal_addresses(conn, account_id, target_id, contents["keys"], entropy, protect_bytes)
                # Validate every available protected contact before exposing a session.
                for key in contents["keys"]:
                    row = conn.execute("SELECT payload FROM address_records WHERE entry_hash = ? AND lock_account = ? AND lock_folder = ?",
                                       (address_hash(key), account_id, target_id)).fetchone()
                    if row is not None and address_hash(decode_entry(unprotect_bytes(bytes(row[0]), entropy)).email) != address_hash(key):
                        raise ValueError("بيانات العنوان المحمي غير صالحة.")
            # Upgrade only after password verification. A failed upgrade must
            # neither open a session nor partially rewrite contact/cache data.
            if self._message_cache is not None:
                keys = [*contents["keys"], *(key for items in contents["folders"].values() for key in items)]
                self._message_cache.transform_locked_rows(conn, account_id, keys, entropy, seal=True)
                conn.execute("DELETE FROM local_lock_hashes WHERE account_id = ? AND target_type = ? AND target_id = ?",
                             (account_id, target_type, target_id))
                conn.executemany("INSERT INTO local_lock_hashes VALUES (?, ?, ?, ?)",
                                 ((target_type, target_id, account_id, value) for value in self._indexed_hashes(account_id, keys)))
        self._unlocked[(target_type, target_id)] = (contents, entropy)

    def _save_open_target(self, account_id: str, target_type: str, target_id: str, contents: dict) -> None:
        _old_contents, entropy = self._unlocked[(target_type, target_id)]
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._write_open_target(conn, account_id, target_type, target_id, contents, entropy)
        self._unlocked[(target_type, target_id)] = (contents, entropy)

    def _assert_open_target_current(self, conn, account_id, target_type, target_id, entropy) -> None:
        row = conn.execute("SELECT payload FROM local_locks WHERE account_id = ? AND target_type = ? AND target_id = ?",
                           (account_id, target_type, target_id)).fetchone()
        session = self._unlocked.get((target_type, target_id))
        if row is None or session is None or json.loads(unprotect_bytes(bytes(row[0]), entropy).decode("utf-8")) != session[0]:
            raise ValueError("تغيّر محتوى القفل في نافذة أخرى؛ أغلق المجلد أو القسم وافتحه مجدداً.")

    def _write_open_target(
        self, conn: sqlite3.Connection, account_id: str, target_type: str,
        target_id: str, contents: dict, entropy: bytes,
    ) -> None:
        self._assert_open_target_current(conn, account_id, target_type, target_id, entropy)
        all_keys = [*contents["keys"], *(key for keys in contents["folders"].values() for key in keys)]
        previous = self._unlocked.get((target_type, target_id))
        if previous is not None and self._message_cache is not None:
            old_keys = {*previous[0]["keys"], *(key for keys in previous[0]["folders"].values() for key in keys)}
            changed = list(old_keys.symmetric_difference(all_keys))
            if changed:
                for item_hash in self._indexed_hashes(account_id, list(set(all_keys) - old_keys)):
                    if conn.execute(
                        "SELECT 1 FROM local_lock_hashes WHERE account_id = ? AND item_hash = ? "
                        "AND NOT (target_type = ? AND target_id = ?)",
                        (account_id, item_hash, target_type, target_id),
                    ).fetchone():
                        raise ValueError("الرسالة موجودة في قفل آخر.")
                self._message_cache.transform_locked_rows(
                    conn, account_id, list(set(all_keys) - old_keys), entropy, seal=True,
                )
                self._message_cache.transform_locked_rows(
                    conn, account_id, list(old_keys - set(all_keys)), entropy, seal=False,
                    exclude_keys=all_keys,
                )
        payload = protect_bytes(json.dumps(contents, ensure_ascii=False).encode("utf-8"), entropy)
        if target_type == "folder":
            folder = conn.execute("SELECT kind FROM folders WHERE id = ? AND account_id = ?", (target_id, account_id)).fetchone()
            if folder and folder["kind"] == FOLDER_CONVERSATIONS:
                old_keys = set(previous[0]["keys"]) if previous else set()
                seal_addresses(conn, account_id, target_id, all_keys, entropy, protect_bytes)
                unseal_addresses(conn, account_id, target_id, old_keys - set(all_keys), entropy, unprotect_bytes)
                # Moving into an encrypted folder must not retain plaintext membership elsewhere.
                conn.executemany(
                    "DELETE FROM folder_items WHERE item_key = ? AND folder_id IN "
                    "(SELECT id FROM folders WHERE account_id = ? AND kind = ?)",
                    ((key, account_id, FOLDER_CONVERSATIONS) for key in all_keys),
                )
        conn.execute(
            "UPDATE local_locks SET payload = ?, item_count = ? WHERE account_id = ? AND target_type = ? AND target_id = ?",
            (payload, len(all_keys), account_id, target_type, target_id),
        )
        conn.execute("DELETE FROM local_lock_hashes WHERE account_id = ? AND target_type = ? AND target_id = ?",
                     (account_id, target_type, target_id))
        conn.executemany(
            "INSERT OR IGNORE INTO local_lock_hashes VALUES (?, ?, ?, ?)",
            ((target_type, target_id, account_id, item_hash)
             for item_hash in self._indexed_hashes(account_id, all_keys, conn)),
        )

    def close_target(self, target_type: str, target_id: str) -> None:
        self._unlocked.pop((target_type, target_id), None)

    def close_all_locks(self) -> None:
        self._unlocked.clear()

    def remove_lock(self, account_id: str, target_type: str, target_id: str) -> None:
        if not self.is_locked(account_id, target_type, target_id):
            raise ValueError("العنصر غير مقفول في هذا الحساب.")
        session = self._unlocked.get((target_type, target_id))
        if session is None:
            raise ValueError("افتح القفل بكلمة المرور أولاً.")
        keys = session[0]["keys"]
        folders = session[0]["folders"]
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._assert_open_target_current(conn, account_id, target_type, target_id, session[1])
            if target_type == "folder" and self.get_folder(account_id, target_id).kind == FOLDER_CONVERSATIONS:
                unseal_addresses(conn, account_id, target_id, keys, session[1], unprotect_bytes)
            if self._message_cache is not None:
                self._message_cache.transform_locked_rows(
                    conn, account_id, [*keys, *(key for items in folders.values() for key in items)],
                    session[1], seal=False,
                )
            table, field = ("folder_items", "folder_id") if target_type == "folder" else ("section_items", "section_id")
            conn.executemany(
                f"INSERT OR IGNORE INTO {table}({field}, item_key) VALUES (?, ?)",
                ((target_id, key) for key in keys),
            )
            if target_type == "section":
                for folder_id, items in folders.items():
                    conn.executemany(
                        "INSERT OR IGNORE INTO folder_items(folder_id, item_key) VALUES (?, ?)",
                        ((folder_id, key) for key in items),
                    )
            conn.execute("DELETE FROM local_lock_hashes WHERE account_id = ? AND target_type = ? AND target_id = ?", (account_id, target_type, target_id))
            conn.execute("DELETE FROM local_locks WHERE account_id = ? AND target_type = ? AND target_id = ?", (account_id, target_type, target_id))
        self.close_target(target_type, target_id)

    @contextmanager
    def _connect(self):
        # Rollback journals plus SQLite's super-journal make changes to both
        # files atomic. WAL cannot provide this guarantee across ATTACHed DBs.
        cache = self._message_cache
        with cache.lock_guard if cache is not None else nullcontext():
            with sqlite3.connect(self.path, timeout=30, factory=ClosingConnection) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA synchronous = FULL")
                conn.execute("PRAGMA secure_delete = ON")
                if cache is not None:
                    conn.execute("ATTACH DATABASE ? AS message_cache", (str(cache.path),))
                    conn.execute("PRAGMA message_cache.synchronous = FULL")
                    conn.execute("PRAGMA message_cache.secure_delete = ON")
                yield conn

    def delete_account(self, account_id: str) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.require_account_removal(account_id, connection=conn)
            conn.execute("DELETE FROM local_lock_hashes WHERE account_id = ?", (account_id,))
            conn.execute("DELETE FROM local_locks WHERE account_id = ?", (account_id,))
            for table in ("folders", "local_sections", "local_categories", "read_events", "global_uid_accounts", "message_identities"):
                conn.execute(f"DELETE FROM {table} WHERE account_id = ?", (account_id,))
            if self._message_cache is not None:
                conn.execute("DELETE FROM message_cache.messages WHERE account_id = ?", (account_id,))
        self.close_all_locks()
        self._global_uid_accounts.discard(account_id)
        self._configured_accounts.discard(account_id)

    def require_account_removal(self, account_id: str, *, connection=None) -> None:
        with self._connect() if connection is None else nullcontext(connection) as conn:
            if conn.execute("""SELECT 1 FROM local_locks l JOIN folders f ON f.id = l.target_id
                WHERE l.account_id = ? AND l.target_type = 'folder' AND f.kind = 'conversations'""", (account_id,)).fetchone():
                raise ProtectedAddressBookError("أزل أقفال مجلدات سجل العناوين قبل حذف الحساب حتى لا تفقد عناوينها.")

    @staticmethod
    def _check_scope(account_id: str, kind: str) -> None:
        if not account_id or kind not in FOLDER_KINDS:
            raise ValueError("الحساب أو نوع المجلد غير صالح.")

    def list_folders(
        self, account_id: str, kind: str, *, archived: bool | None = False,
        section_id: str | None = None,
    ) -> list[Folder]:
        self._check_scope(account_id, kind)
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT f.*, (SELECT COUNT(*) FROM folder_items i WHERE i.folder_id = f.id) AS item_count
                   FROM folders f WHERE account_id = ? AND kind = ? AND (? IS NULL OR archived = ?)
                   AND (? IS NULL OR (? = '' AND section_id IS NULL) OR section_id = ?)
                   ORDER BY pinned DESC, CASE WHEN kind = 'messages' THEN starred ELSE 0 END DESC, name COLLATE NOCASE""",
                (account_id, kind, None if archived is None else int(archived),
                 None if archived is None else int(archived), section_id, section_id, section_id),
            ).fetchall()
        return [self._folder(row) for row in rows]

    def create_folder(
        self, account_id: str, kind: str, name: str, item_keys: list[str] = (),
        *, section_key: str = "", category_id: str | None = None,
        section_id: str | None = None,
    ) -> Folder:
        self._check_scope(account_id, kind)
        if kind == FOLDER_CONVERSATIONS:
            item_keys = [key.casefold() for key in item_keys if key]
        if section_key not in {"", "inbox", "spam", "sent", "all", "custom"}:
            raise ValueError("قسم المجلد غير صالح.")
        if kind != FOLDER_MESSAGES and (section_key or category_id):
            raise ValueError("قسم الرسائل لا ينطبق على مجلد المحادثات.")
        if section_key == "custom" and category_id is None:
            raise ValueError("اختر تصنيفاً محلياً للمجلد.")
        clean_name = clean_folder_name(name) if name.strip() else ""
        folder_id = str(uuid4())
        created_at = time.time()
        section_session = None
        section_contents = None
        if kind == FOLDER_CONVERSATIONS:
            self.prepare_address_storage()
        if section_id and self.is_locked(account_id, "section", section_id):
            section_session = self._unlocked.get(("section", section_id))
            if section_session is None:
                raise ValueError("افتح قفل القسم أولاً.")
            section_contents = {
                "keys": list(section_session[0]["keys"]),
                "folders": {**section_session[0]["folders"],
                            folder_id: list(dict.fromkeys(key for key in item_keys if key))},
            }
        with self._connect() as conn:
            if kind == FOLDER_CONVERSATIONS:
                for key in item_keys:
                    if conn.execute("SELECT 1 FROM address_records WHERE entry_hash = ? AND lock_folder != ''", (address_hash(key),)).fetchone():
                        raise ValueError("العنوان محمي داخل مجلد آخر؛ أزل قفله قبل نقله.")
                    if conn.execute("SELECT 1 FROM local_lock_hashes WHERE account_id = ? AND item_hash = ?",
                                    (account_id, self.locked_key_hash(account_id, key))).fetchone():
                        raise ValueError("افتح القفل أولاً.")
            if not clean_name:
                base = f"مجلد جديد {time.strftime('%d-%m-%Y')}"
                clean_name = base
                suffix = 2
                while conn.execute(
                    "SELECT 1 FROM folders WHERE account_id = ? AND kind = ? AND name = ?",
                    (account_id, kind, clean_name),
                ).fetchone():
                    clean_name = f"{base} ({suffix})"
                    suffix += 1
            if category_id is not None and conn.execute(
                "SELECT 1 FROM local_categories WHERE account_id = ? AND id = ?",
                (account_id, category_id),
            ).fetchone() is None:
                raise ValueError("التصنيف غير موجود في هذا الحساب.")
            if section_id is not None and conn.execute(
                "SELECT 1 FROM local_sections WHERE account_id = ? AND id = ?",
                (account_id, section_id),
            ).fetchone() is None:
                raise ValueError("القسم غير موجود في هذا الحساب.")
            conn.execute(
                "INSERT INTO folders(id, account_id, kind, name, section_key, category_id, created_at, section_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (folder_id, account_id, kind, clean_name, section_key, category_id, created_at, section_id),
            )
            if kind == FOLDER_CONVERSATIONS:
                conn.executemany(
                    """DELETE FROM folder_items WHERE item_key = ? AND folder_id IN
                       (SELECT id FROM folders WHERE account_id = ? AND kind = ?)""",
                    ((key, account_id, FOLDER_CONVERSATIONS) for key in dict.fromkeys(item_keys) if key),
                )
            if section_session is None:
                self._add_items(conn, folder_id, item_keys)
            else:
                self._write_open_target(
                    conn, account_id, "section", section_id,
                    section_contents, section_session[1],
                )
        if section_session is not None:
            self._unlocked[("section", section_id)] = (section_contents, section_session[1])
        return Folder(folder_id, account_id, kind, clean_name, category_id=category_id,
                      section_key=section_key, created_at=created_at,
                      item_count=len({key for key in item_keys if key}), section_id=section_id)

    def list_section_folders(
        self, account_id: str, section_key: str, *, category_id: str | None = None,
    ) -> list[Folder]:
        if section_key not in {"inbox", "spam", "sent", "all", "custom"}:
            raise ValueError("قسم المجلد غير صالح.")
        with self._connect() as conn:
            if section_key == "custom":
                rows = conn.execute(
                    """SELECT f.*, (SELECT COUNT(*) FROM folder_items i WHERE i.folder_id = f.id) AS item_count
                       FROM folders f WHERE account_id = ? AND kind = ? AND archived = 0
                       AND category_id = ? ORDER BY pinned DESC, starred DESC, name COLLATE NOCASE""",
                    (account_id, FOLDER_MESSAGES, category_id),
                ).fetchall() if category_id else []
            else:
                if section_key == "all":
                    rows = conn.execute(
                        """SELECT f.*, (SELECT COUNT(*) FROM folder_items i WHERE i.folder_id = f.id) AS item_count
                           FROM folders f WHERE account_id = ? AND kind = ?
                           AND ((archived = 0 AND section_key = 'all' AND category_id IS NULL)
                                OR archived = 1)
                           ORDER BY pinned DESC, starred DESC, name COLLATE NOCASE""",
                        (account_id, FOLDER_MESSAGES),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT f.*, (SELECT COUNT(*) FROM folder_items i WHERE i.folder_id = f.id) AS item_count
                           FROM folders f WHERE account_id = ? AND kind = ? AND archived = 0
                           AND section_key = ? AND category_id IS NULL
                           ORDER BY pinned DESC, starred DESC, name COLLATE NOCASE""",
                        (account_id, FOLDER_MESSAGES, section_key),
                    ).fetchall()
        return [self._folder(row) for row in rows]

    def get_folder(self, account_id: str, folder_id: str) -> Folder:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT f.*, (SELECT COUNT(*) FROM folder_items i WHERE i.folder_id = f.id) AS item_count
                   FROM folders f WHERE account_id = ? AND id = ?""",
                (account_id, folder_id),
            ).fetchone()
        if row is None:
            raise ValueError("المجلد غير موجود في هذا الحساب.")
        return self._folder(row)

    def rename_folder(self, account_id: str, folder_id: str, name: str) -> None:
        self._update(account_id, folder_id, "name", clean_folder_name(name))

    def set_pinned(self, account_id: str, folder_id: str, enabled: bool) -> None:
        self._update(account_id, folder_id, "pinned", int(enabled))

    def set_starred(self, account_id: str, folder_id: str, enabled: bool) -> None:
        self._update(account_id, folder_id, "starred", int(enabled))

    def set_archived(self, account_id: str, folder_id: str, enabled: bool) -> None:
        self._update(account_id, folder_id, "archived", int(enabled))

    def list_categories(self, account_id: str) -> list[CustomCategory]:
        if not account_id:
            raise ValueError("الحساب غير صالح.")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, rules_json, emails_json FROM local_categories WHERE account_id = ? ORDER BY name COLLATE NOCASE",
                (account_id,),
            ).fetchall()
        return [CustomCategory(str(row["id"]), str(row["name"]),
                               tuple(json.loads(row["rules_json"])),
                               tuple(json.loads(row["emails_json"]))) for row in rows]

    @staticmethod
    def _clean_category_rules(rules: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        result = tuple(dict.fromkeys(rules))
        if any(rule not in CATEGORY_FILTER_RULES for rule in result) or {"attachments", "no_attachments"} <= set(result):
            raise ValueError("شروط تصفية التصنيف غير صالحة.")
        return result

    @staticmethod
    def _clean_category_emails(rules: tuple[str, ...], emails: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(dict.fromkeys(email.strip().casefold() for email in emails if email.strip()))
        if "specific_email" in rules and not cleaned:
            raise ValueError("أدخل عنوان بريد واحداً على الأقل للتصفية.")
        if any(not re.fullmatch(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+", email) for email in cleaned):
            raise ValueError("أحد عناوين البريد المدخلة غير صالح.")
        return cleaned if "specific_email" in rules else ()

    def create_category(
        self, account_id: str, name: str, rules: tuple[str, ...] = (),
        email_addresses: tuple[str, ...] = (),
    ) -> CustomCategory:
        if not account_id:
            raise ValueError("الحساب غير صالح.")
        cleaned_rules = self._clean_category_rules(rules)
        category = CustomCategory(
            str(uuid4()), clean_category_name(name), cleaned_rules,
            self._clean_category_emails(cleaned_rules, email_addresses),
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO local_categories(id, account_id, name, rules_json, emails_json) VALUES (?, ?, ?, ?, ?)",
                (category.id, account_id, category.name, json.dumps(category.rules), json.dumps(category.email_addresses)),
            )
        return category

    def set_category_rules(
        self, account_id: str, category_id: str, rules: tuple[str, ...],
        email_addresses: tuple[str, ...] = (),
    ) -> None:
        cleaned = self._clean_category_rules(rules)
        emails = self._clean_category_emails(cleaned, email_addresses)
        with self._connect() as conn:
            changed = conn.execute(
                "UPDATE local_categories SET rules_json = ?, emails_json = ? WHERE account_id = ? AND id = ?",
                (json.dumps(cleaned), json.dumps(emails), account_id, category_id),
            ).rowcount
        if not changed:
            raise ValueError("التصنيف غير موجود في هذا الحساب.")

    def record_read_event(self, account_id: str, item_key: str, is_read: bool) -> None:
        if not account_id or not item_key:
            raise ValueError("الحساب أو الرسالة غير صالح.")
        with self._connect() as conn:
            if is_read:
                conn.execute(
                    """INSERT INTO read_events(account_id, item_key, read_at) VALUES (?, ?, ?)
                       ON CONFLICT(account_id, item_key) DO UPDATE SET read_at = excluded.read_at""",
                    (account_id, item_key, time.time()),
                )
            else:
                conn.execute(
                    "DELETE FROM read_events WHERE account_id = ? AND item_key = ?",
                    (account_id, item_key),
                )

    def recent_read_keys(self, account_id: str, *, since: float) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT item_key FROM read_events WHERE account_id = ? AND read_at >= ?",
                (account_id, since),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def rename_category(self, account_id: str, category_id: str, name: str) -> None:
        with self._connect() as conn:
            changed = conn.execute(
                "UPDATE local_categories SET name = ? WHERE account_id = ? AND id = ?",
                (clean_category_name(name), account_id, category_id),
            ).rowcount
        if not changed:
            raise ValueError("التصنيف غير موجود في هذا الحساب.")

    def delete_category(self, account_id: str, category_id: str) -> None:
        with self._connect() as conn:
            changed = conn.execute(
                "DELETE FROM local_categories WHERE account_id = ? AND id = ?",
                (account_id, category_id),
            ).rowcount
            if not changed:
                raise ValueError("التصنيف غير موجود في هذا الحساب.")
            conn.execute(
                """UPDATE folders SET category_id = NULL,
                   section_key = CASE WHEN section_key = 'custom' THEN 'all' ELSE section_key END
                   WHERE account_id = ? AND category_id = ?""",
                (account_id, category_id),
            )

    def set_folder_category(self, account_id: str, folder_id: str, category_id: str | None) -> None:
        with self._connect() as conn:
            if category_id is not None and conn.execute(
                "SELECT 1 FROM local_categories WHERE account_id = ? AND id = ?",
                (account_id, category_id),
            ).fetchone() is None:
                raise ValueError("التصنيف غير موجود في هذا الحساب.")
            changed = conn.execute(
                """UPDATE folders SET category_id = ?,
                   section_key = CASE WHEN ? IS NULL AND section_key = 'custom' THEN 'all' ELSE section_key END
                   WHERE account_id = ? AND id = ? AND kind = ?""",
                (category_id, category_id, account_id, folder_id, FOLDER_MESSAGES),
            ).rowcount
        if not changed:
            raise ValueError("مجلد الرسائل غير موجود في هذا الحساب.")

    def category_message_keys(self, account_id: str, category_id: str | None = None) -> list[str]:
        """Return local message references for categorized folders, never server state."""
        with self._connect() as conn:
            query = (
                "SELECT DISTINCT i.item_key FROM folder_items i "
                "JOIN folders f ON f.id = i.folder_id "
                "WHERE f.account_id = ? AND f.kind = ? AND f.category_id IS NOT NULL"
            )
            args: tuple[str, ...] = (account_id, FOLDER_MESSAGES)
            if category_id is not None:
                query += " AND f.category_id = ?"
                args += (category_id,)
            folder_rows = conn.execute(query, args).fetchall()
            direct_query = (
                "SELECT DISTINCT i.item_key FROM category_items i "
                "JOIN local_categories c ON c.id = i.category_id WHERE c.account_id = ?"
            )
            direct_args: tuple[str, ...] = (account_id,)
            if category_id is not None:
                direct_query += " AND c.id = ?"
                direct_args += (category_id,)
            direct_rows = conn.execute(direct_query, direct_args).fetchall()
        return list(dict.fromkeys(str(row[0]) for row in (*folder_rows, *direct_rows)))

    def direct_category_message_keys(self, account_id: str, category_id: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT i.item_key FROM category_items i JOIN local_categories c ON c.id = i.category_id
                   WHERE c.account_id = ? AND c.id = ? ORDER BY i.rowid""",
                (account_id, category_id),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def add_category_items(self, account_id: str, category_id: str, item_keys: list[str]) -> None:
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM local_categories WHERE account_id = ? AND id = ?",
                            (account_id, category_id)).fetchone() is None:
                raise ValueError("التصنيف غير موجود في هذا الحساب.")
            conn.executemany(
                "INSERT OR IGNORE INTO category_items(category_id, item_key) VALUES (?, ?)",
                ((category_id, key) for key in dict.fromkeys(item_keys) if key),
            )

    def list_sections(self, account_id: str) -> list[LocalSection]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, account_id, name FROM local_sections WHERE account_id = ? ORDER BY name COLLATE NOCASE",
                (account_id,),
            ).fetchall()
        return [LocalSection(str(row["id"]), str(row["account_id"]), str(row["name"]),
                             self.is_locked(account_id, "section", str(row["id"]))) for row in rows]

    def create_section(self, account_id: str, name: str) -> LocalSection:
        if not account_id:
            raise ValueError("الحساب غير صالح.")
        section = LocalSection(str(uuid4()), account_id, clean_category_name(name))
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO local_sections(id, account_id, name) VALUES (?, ?, ?)",
                (section.id, account_id, section.name),
            )
        return section

    def rename_section(self, account_id: str, section_id: str, name: str) -> None:
        with self._connect() as conn:
            changed = conn.execute(
                "UPDATE local_sections SET name = ? WHERE account_id = ? AND id = ?",
                (clean_category_name(name), account_id, section_id),
            ).rowcount
        if not changed:
            raise ValueError("القسم غير موجود في هذا الحساب.")

    def delete_section(self, account_id: str, section_id: str) -> None:
        if self.is_locked(account_id, "section", section_id):
            raise ValueError("افتح القفل وأزله قبل حذف القسم.")
        with self._connect() as conn:
            changed = conn.execute(
                "DELETE FROM local_sections WHERE account_id = ? AND id = ?",
                (account_id, section_id),
            ).rowcount
            if not changed:
                raise ValueError("القسم غير موجود في هذا الحساب.")
            conn.execute(
                "UPDATE folders SET section_id = NULL WHERE account_id = ? AND section_id = ?",
                (account_id, section_id),
            )

    def section_message_keys(self, account_id: str, section_id: str | None = None) -> list[str]:
        with self._connect() as conn:
            owned = {str(row[0]) for row in conn.execute("SELECT id FROM local_sections WHERE account_id = ?", (account_id,))}
            query = (
                "SELECT i.item_key FROM section_items i JOIN local_sections s ON s.id = i.section_id "
                "WHERE s.account_id = ?"
            )
            args: tuple[str, ...] = (account_id,)
            if section_id is not None:
                query += " AND s.id = ?"
                args += (section_id,)
            rows = conn.execute(query + " ORDER BY i.rowid", args).fetchall()
        result = [str(row[0]) for row in rows]
        for (kind, target_id), (contents, _entropy) in self._unlocked.items():
            if kind == "section" and target_id in owned and (section_id is None or section_id == target_id):
                result.extend(contents["keys"])
        return result

    def move_items_to_section(self, account_id: str, section_id: str | None, item_keys: list[str]) -> None:
        keys = list(dict.fromkeys(key for key in item_keys if key))
        with self._connect() as conn:
            for key in keys:
                locked_rows = conn.execute(
                    "SELECT target_id FROM local_lock_hashes WHERE account_id = ? AND target_type = 'section' AND item_hash = ?",
                    (account_id, self.locked_key_hash(account_id, key)),
                ).fetchall()
                if any(str(row[0]) != section_id for row in locked_rows):
                    raise ValueError("أزل قفل القسم قبل نقل رسائله إلى قسم آخر.")
        if section_id is not None and self.is_locked(account_id, "section", section_id):
            session = self._unlocked.get(("section", section_id))
            if session is None:
                raise ValueError("افتح قفل القسم أولاً.")
            contents = {"keys": list(dict.fromkeys([*session[0]["keys"], *keys])),
                        "folders": dict(session[0]["folders"])}
            with self._connect() as conn:
                for key in keys:
                    conn.execute(
                        "DELETE FROM section_items WHERE item_key = ? AND section_id IN "
                        "(SELECT id FROM local_sections WHERE account_id = ?)",
                        (key, account_id),
                    )
                self._write_open_target(conn, account_id, "section", section_id, contents, session[1])
            self._unlocked[("section", section_id)] = (contents, session[1])
            return
        with self._connect() as conn:
            if section_id is not None and conn.execute(
                "SELECT 1 FROM local_sections WHERE account_id = ? AND id = ?", (account_id, section_id),
            ).fetchone() is None:
                raise ValueError("القسم غير موجود في هذا الحساب.")
            for key in keys:
                conn.execute(
                    "DELETE FROM section_items WHERE item_key = ? AND section_id IN "
                    "(SELECT id FROM local_sections WHERE account_id = ?)", (key, account_id),
                )
            if section_id is not None:
                conn.executemany(
                    "INSERT INTO section_items(section_id, item_key) VALUES (?, ?)",
                    ((section_id, key) for key in keys),
                )

    def set_folder_section(self, account_id: str, folder_id: str, section_id: str | None) -> None:
        folder = self.get_folder(account_id, folder_id)
        if self.is_locked(account_id, "folder", folder_id) or (
            folder.section_id and self.is_locked(account_id, "section", folder.section_id)
        ) or (section_id and self.is_locked(account_id, "section", section_id)):
            raise ValueError("افتح القفل وأزله قبل نقل المجلد بين الأقسام.")
        with self._connect() as conn:
            if section_id is not None and conn.execute(
                "SELECT 1 FROM local_sections WHERE account_id = ? AND id = ?", (account_id, section_id),
            ).fetchone() is None:
                raise ValueError("القسم غير موجود في هذا الحساب.")
            changed = conn.execute(
                "UPDATE folders SET section_id = ? WHERE account_id = ? AND id = ? AND kind = ?",
                (section_id, account_id, folder_id, FOLDER_MESSAGES),
            ).rowcount
        if not changed:
            raise ValueError("المجلد غير موجود في هذا الحساب.")

    def message_folder_keys(self, account_id: str) -> list[str]:
        """All locally grouped messages, including folders outside custom categories."""
        with self._connect() as conn:
            owned = {str(row[0]) for row in conn.execute("SELECT id FROM folders WHERE account_id = ? UNION SELECT id FROM local_sections WHERE account_id = ?", (account_id, account_id))}
            rows = conn.execute(
                "SELECT DISTINCT i.item_key FROM folder_items i "
                "JOIN folders f ON f.id = i.folder_id "
                "WHERE f.account_id = ? AND f.kind = ?",
                (account_id, FOLDER_MESSAGES),
            ).fetchall()
        result = [str(row[0]) for row in rows]
        for (kind, _target_id), (contents, _entropy) in self._unlocked.items():
            if _target_id not in owned:
                continue
            if kind == "folder":
                result.extend(contents["keys"])
            elif kind == "section":
                result.extend(key for keys in contents["folders"].values() for key in keys)
        return list(dict.fromkeys(result))

    def _update(self, account_id: str, folder_id: str, field: str, value: str | int) -> None:
        with self._connect() as conn:
            changed = conn.execute(
                f"UPDATE folders SET {field} = ? WHERE account_id = ? AND id = ?",
                (value, account_id, folder_id),
            ).rowcount
        if not changed:
            raise ValueError("المجلد غير موجود في هذا الحساب.")

    def delete_folder(self, account_id: str, folder_id: str) -> None:
        folder = self.get_folder(account_id, folder_id)
        if self.is_locked(account_id, "folder", folder_id) or (
            folder.section_id and self.is_locked(account_id, "section", folder.section_id)
        ):
            raise ValueError("افتح القفل وأزله قبل حذف المجلد.")
        with self._connect() as conn:
            conn.execute("DELETE FROM local_lock_hashes WHERE account_id = ? AND target_type = 'folder' AND target_id = ?", (account_id, folder_id))
            conn.execute("DELETE FROM local_locks WHERE account_id = ? AND target_type = 'folder' AND target_id = ?", (account_id, folder_id))
            changed = conn.execute(
                "DELETE FROM folders WHERE account_id = ? AND id = ?",
                (account_id, folder_id),
            ).rowcount
        if not changed:
            raise ValueError("المجلد غير موجود في هذا الحساب.")
        self.close_target("folder", folder_id)

    def list_items(self, account_id: str, folder_id: str) -> list[str]:
        if self.is_locked(account_id, "folder", folder_id):
            session = self._unlocked.get(("folder", folder_id))
            if session is None:
                raise ValueError("افتح قفل المجلد أولاً.")
            return list(session[0]["keys"])
        folder = self.get_folder(account_id, folder_id)
        if folder.section_id and self.is_locked(account_id, "section", folder.section_id):
            session = self._unlocked.get(("section", folder.section_id))
            if session is None:
                raise ValueError("افتح قفل القسم أولاً.")
            return list(session[0]["folders"].get(folder_id, []))
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT i.item_key FROM folder_items i JOIN folders f ON f.id = i.folder_id
                   WHERE f.account_id = ? AND f.id = ? ORDER BY i.rowid""",
                (account_id, folder_id),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def conversation_item_keys(self, account_id: str) -> set[str]:
        """Addresses assigned to any conversation folder, including archived ones."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT DISTINCT i.item_key FROM folder_items i
                   JOIN folders f ON f.id = i.folder_id
                   WHERE f.account_id = ? AND f.kind = ?""",
                (account_id, FOLDER_CONVERSATIONS),
            ).fetchall()
        return {str(row[0]).casefold() for row in rows}

    def add_items(self, account_id: str, folder_id: str, item_keys: list[str]) -> None:
        folder = self.get_folder(account_id, folder_id)
        if folder.kind == FOLDER_CONVERSATIONS:
            item_keys = [key.casefold() for key in item_keys if key]
            self.prepare_address_storage()
            with self._connect() as conn:
                for key in item_keys:
                    if conn.execute("SELECT 1 FROM address_records WHERE entry_hash = ? AND lock_folder != '' "
                                    "AND NOT (lock_account = ? AND lock_folder = ?)",
                                    (address_hash(key), account_id, folder_id)).fetchone():
                        raise ValueError("العنوان محمي داخل مجلد آخر؛ أزل قفله قبل نقله.")
                    if conn.execute(
                        "SELECT 1 FROM local_lock_hashes WHERE account_id = ? AND item_hash = ? "
                        "AND NOT (target_type = 'folder' AND target_id = ?)",
                        (account_id, self.locked_key_hash(account_id, key), folder_id),
                    ).fetchone():
                        raise ValueError("افتح القفل أولاً.")
        lock_kind, lock_id = ("folder", folder_id) if self.is_locked(account_id, "folder", folder_id) else (
            ("section", folder.section_id) if folder.section_id and self.is_locked(account_id, "section", folder.section_id) else ("", "")
        )
        if lock_kind:
            session = self._unlocked.get((lock_kind, lock_id))
            if session is None:
                raise ValueError("افتح القفل أولاً.")
            contents = {"keys": list(session[0]["keys"]),
                        "folders": {key: list(values) for key, values in session[0]["folders"].items()}}
            key_list = contents["keys"] if lock_kind == "folder" else contents["folders"].setdefault(folder_id, [])
            key_list[:] = list(dict.fromkeys([*key_list, *(key for key in item_keys if key)]))
            self._save_open_target(account_id, lock_kind, lock_id, contents)
            return
        with self._connect() as conn:
            if folder.kind == FOLDER_CONVERSATIONS:
                conn.executemany(
                    """DELETE FROM folder_items WHERE item_key = ? AND folder_id IN
                       (SELECT id FROM folders WHERE account_id = ? AND kind = ?)""",
                    ((key, account_id, FOLDER_CONVERSATIONS) for key in dict.fromkeys(item_keys) if key),
                )
            self._add_items(conn, folder_id, item_keys)

    def remove_item(self, account_id: str, folder_id: str, item_key: str) -> None:
        folder = self.get_folder(account_id, folder_id)
        lock_kind, lock_id = ("folder", folder_id) if self.is_locked(account_id, "folder", folder_id) else (
            ("section", folder.section_id) if folder.section_id and self.is_locked(account_id, "section", folder.section_id) else ("", "")
        )
        if lock_kind:
            session = self._unlocked.get((lock_kind, lock_id))
            if session is None:
                raise ValueError("افتح القفل أولاً.")
            contents = {"keys": list(session[0]["keys"]),
                        "folders": {key: list(values) for key, values in session[0]["folders"].items()}}
            key_list = contents["keys"] if lock_kind == "folder" else contents["folders"].setdefault(folder_id, [])
            if item_key in key_list:
                key_list.remove(item_key)
                self._save_open_target(account_id, lock_kind, lock_id, contents)
            return
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM folder_items WHERE folder_id = ? AND item_key = ?",
                (folder_id, item_key),
            )

    @staticmethod
    def _add_items(conn: sqlite3.Connection, folder_id: str, item_keys: list[str]) -> None:
        conn.executemany(
            "INSERT OR IGNORE INTO folder_items(folder_id, item_key) VALUES (?, ?)",
            ((folder_id, key) for key in dict.fromkeys(item_keys) if key),
        )

    def _folder(self, row: sqlite3.Row) -> Folder:
        account_id, folder_id = str(row["account_id"]), str(row["id"])
        section_id = str(row["section_id"]) if "section_id" in row.keys() and row["section_id"] else None
        own_lock = self.is_locked(account_id, "folder", folder_id)
        section_lock = bool(section_id and self.is_locked(account_id, "section", section_id))
        item_count = int(row["item_count"]) if "item_count" in row.keys() else 0
        if own_lock:
            session = self._unlocked.get(("folder", folder_id))
            item_count = len(session[0]["keys"]) if session else 0
        elif section_lock:
            session = self._unlocked.get(("section", section_id))
            item_count = len(session[0]["folders"].get(folder_id, [])) if session else 0
        return Folder(
            folder_id, account_id, str(row["kind"]), str(row["name"]),
            bool(row["pinned"]), bool(row["starred"]), bool(row["archived"]),
            str(row["category_id"]) if row["category_id"] else None,
            str(row["section_key"]),
            float(row["created_at"]),
            item_count,
            section_id,
            own_lock or section_lock,
        )
