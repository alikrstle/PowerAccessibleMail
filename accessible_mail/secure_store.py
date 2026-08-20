from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sqlite3
import time
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import message_cache_path
from .models import Account, LinkItem, MessageContent, MessageSummary


CRYPTPROTECT_UI_FORBIDDEN = 0x01


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        result = super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return result


def _blob_from_bytes(data: bytes) -> tuple[DATA_BLOB, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _blob_to_bytes(blob: DATA_BLOB) -> bytes:
    if not blob.pbData:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def protect_bytes(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Encrypted message cache requires Windows DPAPI.")
    in_blob, _buffer = _blob_from_bytes(data)
    out_blob = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return _blob_to_bytes(out_blob)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def unprotect_bytes(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Encrypted message cache requires Windows DPAPI.")
    in_blob, _buffer = _blob_from_bytes(data)
    out_blob = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return _blob_to_bytes(out_blob)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _encrypt_json(payload: dict[str, Any] | list[dict[str, Any]]) -> bytes:
    return protect_bytes(_json_bytes(payload))


def _decrypt_json(blob: bytes) -> Any:
    return json.loads(unprotect_bytes(blob).decode("utf-8"))


def _json_bytes(payload: dict[str, Any] | list[dict[str, Any]]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


@lru_cache(maxsize=4096)
def _decrypt_summary_json(blob: bytes) -> dict[str, Any]:
    payload = _decrypt_json(blob)
    if not isinstance(payload, dict):
        raise ValueError("Invalid cached message summary.")
    return payload


class MessageCache:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or message_cache_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._init_db()
        except sqlite3.DatabaseError:
            self._move_corrupt_database()
            self._init_db()

    def list_summaries(
        self,
        account_id: str,
        mailbox: str,
        limit: int,
    ) -> list[MessageSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT uid, summary_blob
                FROM messages
                WHERE account_id = ? AND mailbox = ?
                ORDER BY sort_at DESC, fetched_at DESC, CAST(uid AS INTEGER) DESC
                LIMIT ?
                """,
                (account_id, mailbox, limit),
            ).fetchall()
        summaries: list[MessageSummary] = []
        for _uid, blob in rows:
            try:
                summaries.append(self._summary_from_blob(blob))
            except Exception:
                continue
        return summaries

    def summaries_by_uids(
        self,
        account_id: str,
        mailbox: str,
        uids: list[str],
    ) -> dict[str, MessageSummary]:
        if not uids:
            return {}
        rows_by_uid: dict[str, bytes] = {}
        with self._connect() as conn:
            for offset in range(0, len(uids), 500):
                chunk = uids[offset : offset + 500]
                placeholders = ",".join("?" for _uid in chunk)
                rows = conn.execute(
                    f"""
                    SELECT uid, summary_blob
                    FROM messages
                    WHERE account_id = ? AND mailbox = ? AND uid IN ({placeholders})
                    """,
                    (account_id, mailbox, *chunk),
                ).fetchall()
                rows_by_uid.update({str(row["uid"]): bytes(row["summary_blob"]) for row in rows})

        summaries: dict[str, MessageSummary] = {}
        for uid in uids:
            blob = rows_by_uid.get(uid)
            if blob is None:
                continue
            try:
                summaries[uid] = self._summary_from_blob(blob)
            except Exception:
                continue
        return summaries

    def count_summaries(self, account_id: str, mailbox: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM messages
                WHERE account_id = ? AND mailbox = ?
                """,
                (account_id, mailbox),
            ).fetchone()
        return int(row[0] or 0) if row else 0

    def oldest_uid(self, account_id: str, mailbox: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT uid
                FROM messages
                WHERE account_id = ? AND mailbox = ?
                ORDER BY CAST(uid AS INTEGER) ASC
                LIMIT 1
                """,
                (account_id, mailbox),
            ).fetchone()
        return str(row["uid"]) if row else ""

    def get_content(
        self,
        account_id: str,
        mailbox: str,
        uid: str,
    ) -> MessageContent | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT summary_blob, body_blob, links_blob
                FROM messages
                WHERE account_id = ? AND mailbox = ? AND uid = ?
                """,
                (account_id, mailbox, uid),
            ).fetchone()
        if not row or row["body_blob"] is None:
            return None
        try:
            summary = self._summary_from_blob(row["summary_blob"])
            text = unprotect_bytes(row["body_blob"]).decode("utf-8")
            link_payload = _decrypt_json(row["links_blob"]) if row["links_blob"] else []
            links = [
                LinkItem(
                    text=str(item.get("text", "")),
                    url=str(item.get("url", "")),
                    kind=str(item.get("kind", "link") or "link"),
                    filename=str(item.get("filename", "")),
                    content_type=str(item.get("content_type", "")),
                    size=int(item.get("size", 0) or 0),
                    data=str(item.get("data", "")),
                    activation_text=str(item.get("activation_text", "")),
                    activation_start=int(item.get("activation_start", -1) or -1),
                    activation_end=int(item.get("activation_end", -1) or -1),
                    content_id=str(item.get("content_id", "")),
                )
                for item in link_payload
                if isinstance(item, dict)
            ]
            return MessageContent(summary=summary, text=text, links=links)
        except Exception:
            return None

    def upsert_summaries(self, account: Account, summaries: list[MessageSummary]) -> None:
        if not summaries:
            return
        now = time.time()
        with self._connect() as conn:
            existing_states = self._existing_summary_states(conn, account.id, summaries)

        prepared: list[tuple[MessageSummary, bytes, str]] = []
        for summary in summaries:
            _existing_hash, existing_pinned = existing_states.get(
                (summary.mailbox, summary.uid),
                ("", False),
            )
            if existing_pinned:
                summary.is_pinned = True
            serialized = _json_bytes(self._summary_payload(summary))
            prepared.append((summary, serialized, hashlib.sha256(serialized).hexdigest()))

        rows = [
            (
                account.id,
                summary.mailbox,
                summary.uid,
                protect_bytes(serialized),
                summary_hash,
                summary.sort_timestamp,
                now,
                int(summary.is_read),
                int(summary.is_pinned),
            )
            for summary, serialized, summary_hash in prepared
            if existing_states.get((summary.mailbox, summary.uid), ("", False))[0]
            != summary_hash
        ]
        if not rows:
            return
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO messages (
                    account_id, mailbox, uid, summary_blob, summary_hash,
                    sort_at, fetched_at, is_read, is_pinned
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, mailbox, uid)
                DO UPDATE SET
                    summary_blob = excluded.summary_blob,
                    summary_hash = excluded.summary_hash,
                    sort_at = excluded.sort_at,
                    fetched_at = excluded.fetched_at,
                    is_read = excluded.is_read,
                    is_pinned = excluded.is_pinned
                """,
                rows,
            )

    def upsert_content(
        self,
        account: Account,
        content: MessageContent,
    ) -> None:
        now = time.time()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT is_pinned, summary_blob
                FROM messages
                WHERE account_id = ? AND mailbox = ? AND uid = ?
                """,
                (account.id, content.summary.mailbox, content.summary.uid),
            ).fetchone()
        if row:
            existing_pinned = bool(row["is_pinned"])
            if not existing_pinned:
                try:
                    existing_pinned = self._summary_from_blob(row["summary_blob"]).is_pinned
                except Exception:
                    pass
            if existing_pinned:
                content.summary.is_pinned = True

        links = [
            {
                "text": link.text,
                "url": link.url,
                "kind": link.kind,
                "filename": link.filename,
                "content_type": link.content_type,
                "size": link.size,
                "data": link.data,
                "activation_text": link.activation_text,
                "activation_start": link.activation_start,
                "activation_end": link.activation_end,
                "content_id": link.content_id,
            }
            for link in content.links
        ]
        summary_blob = self._summary_to_blob(content.summary)
        summary_hash = self._summary_hash(content.summary)
        body_blob = protect_bytes(content.text.encode("utf-8"))
        links_blob = _encrypt_json(links)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    account_id, mailbox, uid, summary_blob, summary_hash,
                    sort_at, body_blob, links_blob, fetched_at,
                    body_fetched_at, is_read, is_pinned
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, mailbox, uid)
                DO UPDATE SET
                    summary_blob = excluded.summary_blob,
                    summary_hash = excluded.summary_hash,
                    sort_at = excluded.sort_at,
                    body_blob = excluded.body_blob,
                    links_blob = excluded.links_blob,
                    fetched_at = excluded.fetched_at,
                    body_fetched_at = excluded.body_fetched_at,
                    is_read = excluded.is_read,
                    is_pinned = excluded.is_pinned
                """,
                (
                    account.id,
                    content.summary.mailbox,
                    content.summary.uid,
                    summary_blob,
                    summary_hash,
                    content.summary.sort_timestamp,
                    body_blob,
                    links_blob,
                    now,
                    now,
                    int(content.summary.is_read),
                    int(content.summary.is_pinned),
                ),
            )

    def mark_read(
        self,
        account: Account,
        mailbox: str,
        uid: str,
        is_read: bool = True,
    ) -> None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT summary_blob
                FROM messages
                WHERE account_id = ? AND mailbox = ? AND uid = ?
                """,
                (account.id, mailbox, uid),
            ).fetchone()
            if not row:
                return
            summary = self._summary_from_blob(row["summary_blob"])
            summary.is_read = is_read
            conn.execute(
                """
                UPDATE messages
                SET summary_blob = ?, summary_hash = ?, sort_at = ?, is_read = ?, is_pinned = ?
                WHERE account_id = ? AND mailbox = ? AND uid = ?
                """,
                (
                    self._summary_to_blob(summary),
                    self._summary_hash(summary),
                    summary.sort_timestamp,
                    int(is_read),
                    int(summary.is_pinned),
                    account.id,
                    mailbox,
                    uid,
                ),
            )

    def update_summary_flags(
        self,
        account: Account,
        mailbox: str,
        uid: str,
        *,
        is_read: bool | None = None,
        is_starred: bool | None = None,
        is_pinned: bool | None = None,
    ) -> None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT summary_blob
                FROM messages
                WHERE account_id = ? AND mailbox = ? AND uid = ?
                """,
                (account.id, mailbox, uid),
            ).fetchone()
            if not row:
                return
            summary = self._summary_from_blob(row["summary_blob"])
            if is_read is not None:
                summary.is_read = is_read
            if is_starred is not None:
                summary.is_starred = is_starred
            if is_pinned is not None:
                summary.is_pinned = is_pinned
            conn.execute(
                """
                UPDATE messages
                SET summary_blob = ?, summary_hash = ?, sort_at = ?, is_read = ?, is_pinned = ?
                WHERE account_id = ? AND mailbox = ? AND uid = ?
                """,
                (
                    self._summary_to_blob(summary),
                    self._summary_hash(summary),
                    summary.sort_timestamp,
                    int(summary.is_read),
                    int(summary.is_pinned),
                    account.id,
                    mailbox,
                    uid,
                ),
            )

    def update_summary_flags_by_uid(
        self,
        account: Account,
        uid: str,
        *,
        is_read: bool | None = None,
        is_starred: bool | None = None,
        is_pinned: bool | None = None,
    ) -> None:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT mailbox, summary_blob
                FROM messages
                WHERE account_id = ? AND uid = ?
                """,
                (account.id, uid),
            ).fetchall()
            updates: list[tuple[bytes, str, float, int, int, str, str, str]] = []
            for row in rows:
                try:
                    summary = self._summary_from_blob(row["summary_blob"])
                except Exception:
                    continue
                if is_read is not None:
                    summary.is_read = is_read
                if is_starred is not None:
                    summary.is_starred = is_starred
                if is_pinned is not None:
                    summary.is_pinned = is_pinned
                updates.append(
                    (
                        self._summary_to_blob(summary),
                        self._summary_hash(summary),
                        summary.sort_timestamp,
                        int(summary.is_read),
                        int(summary.is_pinned),
                        account.id,
                        str(row["mailbox"]),
                        uid,
                    )
                )
            if updates:
                conn.executemany(
                    """
                    UPDATE messages
                    SET summary_blob = ?, summary_hash = ?, sort_at = ?, is_read = ?, is_pinned = ?
                    WHERE account_id = ? AND mailbox = ? AND uid = ?
                    """,
                    updates,
                )

    def delete_message(self, account: Account, mailbox: str, uid: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM messages
                WHERE account_id = ? AND mailbox = ? AND uid = ?
                """,
                (account.id, mailbox, uid),
            )

    def delete_message_by_uid(self, account: Account, uid: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM messages
                WHERE account_id = ? AND uid = ?
                """,
                (account.id, uid),
            )

    def delete_account(self, account_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM messages
                WHERE account_id = ?
                """,
                (account_id,),
            )

    def _summary_to_blob(self, summary: MessageSummary) -> bytes:
        return protect_bytes(_json_bytes(self._summary_payload(summary)))

    def _summary_hash(self, summary: MessageSummary) -> str:
        return hashlib.sha256(_json_bytes(self._summary_payload(summary))).hexdigest()

    def _summary_payload(self, summary: MessageSummary) -> dict[str, Any]:
        return {
            "uid": summary.uid,
            "mailbox": summary.mailbox,
            "sender": summary.sender,
            "sender_email": summary.sender_email,
            "recipient_emails": list(summary.recipient_emails),
            "subject": summary.subject,
            "date": summary.date,
            "received_at": summary.received_at,
            "is_read": summary.is_read,
            "message_id": summary.message_id,
            "references": summary.references,
            "in_reply_to": summary.in_reply_to,
            "has_attachments": summary.has_attachments,
            "is_starred": summary.is_starred,
            "is_pinned": summary.is_pinned,
        }

    def _summary_from_blob(self, blob: bytes) -> MessageSummary:
        payload = _decrypt_summary_json(bytes(blob))
        return MessageSummary(
            uid=str(payload.get("uid", "")),
            mailbox=str(payload.get("mailbox", "")),
            sender=str(payload.get("sender", "")),
            sender_email=str(payload.get("sender_email", "")),
            recipient_emails=[
                str(value)
                for value in payload.get("recipient_emails", [])
                if isinstance(value, str)
            ] if isinstance(payload.get("recipient_emails", []), list) else [],
            subject=str(payload.get("subject", "")),
            date=str(payload.get("date", "")),
            received_at=float(payload.get("received_at", 0.0) or 0.0),
            is_read=bool(payload.get("is_read", False)),
            message_id=str(payload.get("message_id", "")),
            references=str(payload.get("references", "")),
            in_reply_to=str(payload.get("in_reply_to", "")),
            has_attachments=bool(payload.get("has_attachments", False)),
            is_starred=bool(payload.get("is_starred", False)),
            is_pinned=bool(payload.get("is_pinned", False)),
        )

    def _existing_summary_states(
        self,
        conn: sqlite3.Connection,
        account_id: str,
        summaries: list[MessageSummary],
    ) -> dict[tuple[str, str], tuple[str, bool]]:
        states: dict[tuple[str, str], tuple[str, bool]] = {}
        by_mailbox: dict[str, list[str]] = {}
        for summary in summaries:
            by_mailbox.setdefault(summary.mailbox, []).append(summary.uid)
        for mailbox, uids in by_mailbox.items():
            for offset in range(0, len(uids), 500):
                chunk = uids[offset : offset + 500]
                placeholders = ",".join("?" for _uid in chunk)
                rows = conn.execute(
                    f"""
                    SELECT uid, summary_hash, is_pinned, summary_blob
                    FROM messages
                    WHERE account_id = ? AND mailbox = ? AND uid IN ({placeholders})
                    """,
                    (account_id, mailbox, *chunk),
                ).fetchall()
                for row in rows:
                    summary_hash = str(row["summary_hash"] or "")
                    is_pinned = bool(row["is_pinned"])
                    if not summary_hash and not is_pinned:
                        try:
                            is_pinned = self._summary_from_blob(row["summary_blob"]).is_pinned
                        except Exception:
                            pass
                    states[(mailbox, str(row["uid"]))] = (summary_hash, is_pinned)
        return states

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _backfill_missing_sort_timestamps(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT account_id, mailbox, uid, summary_blob
            FROM messages
            WHERE sort_at = 0
            """
        ).fetchall()
        updates: list[tuple[float, str, str, str]] = []
        for row in rows:
            try:
                sort_at = self._summary_from_blob(row["summary_blob"]).sort_timestamp
            except Exception:
                continue
            if sort_at:
                updates.append(
                    (sort_at, str(row["account_id"]), str(row["mailbox"]), str(row["uid"]))
                )
        if updates:
            conn.executemany(
                """
                UPDATE messages
                SET sort_at = ?
                WHERE account_id = ? AND mailbox = ? AND uid = ?
                """,
                updates,
            )

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            integrity = conn.execute("PRAGMA quick_check(1)").fetchone()
            if integrity and str(integrity[0]).lower() != "ok":
                raise sqlite3.DatabaseError(str(integrity[0]))
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    account_id TEXT NOT NULL,
                    mailbox TEXT NOT NULL,
                    uid TEXT NOT NULL,
                    summary_blob BLOB NOT NULL,
                    summary_hash TEXT,
                    sort_at REAL NOT NULL DEFAULT 0,
                    body_blob BLOB,
                    links_blob BLOB,
                    fetched_at REAL NOT NULL,
                    body_fetched_at REAL,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    is_pinned INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (account_id, mailbox, uid)
                )
                """
            )
            columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(messages)")}
            if "summary_hash" not in columns:
                conn.execute("ALTER TABLE messages ADD COLUMN summary_hash TEXT")
            if "sort_at" not in columns:
                conn.execute("ALTER TABLE messages ADD COLUMN sort_at REAL NOT NULL DEFAULT 0")
            if "is_pinned" not in columns:
                conn.execute("ALTER TABLE messages ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0")
            self._backfill_missing_sort_timestamps(conn)
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_mailbox_uid
                ON messages(account_id, mailbox, uid)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_mailbox_uid_integer
                ON messages(account_id, mailbox, CAST(uid AS INTEGER) DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_mailbox_sort
                ON messages(account_id, mailbox, sort_at DESC, fetched_at DESC)
                """
            )

    def _move_corrupt_database(self) -> None:
        if not self.path.exists():
            return
        suffix = time.strftime("%Y%m%d-%H%M%S")
        corrupt_path = self.path.with_name(f"{self.path.stem}.corrupt-{suffix}{self.path.suffix}")
        try:
            self.path.replace(corrupt_path)
        except OSError:
            self.path.unlink(missing_ok=True)
        for suffix_name in ("-wal", "-shm"):
            sidecar = self.path.with_name(self.path.name + suffix_name)
            if sidecar.exists():
                try:
                    sidecar.unlink()
                except OSError:
                    pass
