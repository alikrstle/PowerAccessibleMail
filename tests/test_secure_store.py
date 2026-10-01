from __future__ import annotations

import tempfile
import unittest
import sqlite3
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from accessible_mail.models import Account, LinkItem, MessageContent, MessageSummary
from accessible_mail.folder_store import FOLDER_MESSAGES, FolderStore
from accessible_mail.secure_store import (
    LOCKED_CACHE_PREFIX, MessageCache, _decrypt_summary_json, protect_bytes, unprotect_bytes,
)


class DpapiEntropyTests(unittest.TestCase):
    def test_optional_entropy_is_passed_as_third_dpapi_argument(self) -> None:
        crypt32 = Mock()
        crypt32.CryptProtectData.return_value = 1
        crypt32.CryptUnprotectData.return_value = 1
        with patch("accessible_mail.secure_store.ctypes.windll") as windll:
            windll.crypt32 = crypt32
            self.assertEqual(protect_bytes(b"data", b"secret"), b"")
            self.assertEqual(unprotect_bytes(b"data", b"secret"), b"")
        protect_args = crypt32.CryptProtectData.call_args.args
        unprotect_args = crypt32.CryptUnprotectData.call_args.args
        self.assertIsNone(protect_args[1])
        self.assertEqual(protect_args[2]._obj.cbData, 6)
        self.assertIsNone(unprotect_args[1])
        self.assertEqual(unprotect_args[2]._obj.cbData, 6)

    def test_existing_cache_calls_keep_no_optional_entropy(self) -> None:
        crypt32 = Mock()
        crypt32.CryptProtectData.return_value = 1
        with patch("accessible_mail.secure_store.ctypes.windll") as windll:
            windll.crypt32 = crypt32
            protect_bytes(b"data")
        self.assertIsNone(crypt32.CryptProtectData.call_args.args[2])


@unittest.skipUnless(os.environ.get("PAM_REAL_DPAPI_TEST") == "1", "requires real Windows DPAPI")
class RealLockCacheIntegrationTests(unittest.TestCase):
    def test_password_protects_membership_and_cached_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = FolderStore(Path(directory) / "folders.db")
            cache = MessageCache(Path(directory) / "messages.sqlite3")
            cache.set_lock_store(store)
            account = Account(id="account-a", email_address="user@example.com")
            summary = MessageSummary(uid="42", mailbox="INBOX", subject="Private subject")
            cache.upsert_content(account, MessageContent(summary=summary, text="Private body", links=[]))
            folder = store.create_folder(account.id, FOLDER_MESSAGES, "Private", ['["INBOX","42"]'])
            with cache.lock_guard:
                store.lock_target(account.id, "folder", folder.id, "passphrase-123")
                store.unlock_target(account.id, "folder", folder.id, "passphrase-123")
                keys, entropy = store.open_lock_material("folder", folder.id)
                cache.seal_locked_rows(account.id, keys, entropy)
                store.close_target("folder", folder.id)
            self.assertIsNone(cache.get_content(account.id, "INBOX", "42"))
            with cache._connect() as conn:
                blob = bytes(conn.execute("SELECT body_blob FROM messages WHERE uid = '42'").fetchone()[0])
            self.assertTrue(blob.startswith(LOCKED_CACHE_PREFIX))
            with self.assertRaises(OSError):
                unprotect_bytes(blob[len(LOCKED_CACHE_PREFIX):], b"wrong-key")
            reopened_store = FolderStore(Path(directory) / "folders.db")
            reopened_cache = MessageCache(Path(directory) / "messages.sqlite3")
            reopened_cache.set_lock_store(reopened_store)
            self.assertIsNone(reopened_cache.get_content(account.id, "INBOX", "42"))
            reopened_store.unlock_target(account.id, "folder", folder.id, "passphrase-123")
            self.assertEqual(reopened_cache.get_content(account.id, "INBOX", "42").text, "Private body")
            reopened_store.remove_lock(account.id, "folder", folder.id)
            self.assertFalse(reopened_store.is_locked(account.id, "folder", folder.id))
            self.assertEqual(reopened_cache.get_content(account.id, "INBOX", "42").text, "Private body")
            with reopened_cache._connect() as conn:
                body = bytes(conn.execute("SELECT body_blob FROM messages WHERE uid = '42'").fetchone()[0])
            self.assertFalse(body.startswith(LOCKED_CACHE_PREFIX))


class MessageCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        _decrypt_summary_json.cache_clear()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.cache_path = Path(self.temporary_directory.name) / "messages.sqlite3"
        self.account = Account(id="account", email_address="user@example.com")

    def crypto_patches(self):
        return (
            patch("accessible_mail.secure_store.protect_bytes", side_effect=lambda data: b"encrypted:" + data),
            patch(
                "accessible_mail.secure_store.unprotect_bytes",
                side_effect=lambda data: bytes(data).removeprefix(b"encrypted:"),
            ),
        )

    def test_locked_message_cache_requires_password_and_sync_cannot_downgrade_it(self) -> None:
        class LockStore:
            locked = False
            entropy = None

            def has_any_locks(self):
                return self.locked

            def set_message_cache(self, cache):
                self.cache = cache

            def lock_context_for_message(self, account_id, mailbox, uid):
                return (self.locked, self.entropy) if uid == "42" else (False, None)

        def encrypt(data, entropy=None):
            return (b"password:" if entropy else b"windows:") + bytes(data)

        def decrypt(data, entropy=None):
            prefix = b"password:" if entropy else b"windows:"
            if not bytes(data).startswith(prefix):
                raise ValueError("wrong key")
            return bytes(data)[len(prefix):]

        with (
            patch("accessible_mail.secure_store.protect_bytes", side_effect=encrypt),
            patch("accessible_mail.secure_store.unprotect_bytes", side_effect=decrypt),
        ):
            cache = MessageCache(self.cache_path)
            store = LockStore()
            cache.set_lock_store(store)
            summary = MessageSummary(uid="42", mailbox="INBOX", subject="Secret")
            cache.upsert_content(self.account, MessageContent(summary=summary, text="Private body", links=[]))
            key = '["INBOX","42"]'
            store.locked, store.entropy = True, b"secret"
            cache.seal_locked_rows(self.account.id, [key], b"secret")
            with cache._connect() as conn:
                row = conn.execute("SELECT summary_blob, body_blob FROM messages WHERE uid = '42'").fetchone()
            self.assertTrue(bytes(row["summary_blob"]).startswith(LOCKED_CACHE_PREFIX))
            self.assertTrue(bytes(row["body_blob"]).startswith(LOCKED_CACHE_PREFIX))
            self.assertEqual(cache.get_content(self.account.id, "INBOX", "42").text, "Private body")
            cache.upsert_content(self.account, MessageContent(summary=summary, text="Updated private body", links=[]))
            self.assertEqual(cache.get_content(self.account.id, "INBOX", "42").text, "Updated private body")
            with cache._connect() as conn:
                updated_blob = bytes(conn.execute("SELECT body_blob FROM messages WHERE uid = '42'").fetchone()[0])
            self.assertTrue(updated_blob.startswith(LOCKED_CACHE_PREFIX))
            store.entropy = None
            self.assertIsNone(cache.get_content(self.account.id, "INBOX", "42"))
            cache.upsert_content(self.account, MessageContent(summary=summary, text="Unsafe overwrite", links=[]))
            with cache._connect() as conn:
                current = conn.execute("SELECT body_blob FROM messages WHERE uid = '42'").fetchone()[0]
            self.assertEqual(bytes(current), updated_blob)
            store.entropy = b"secret"
            cache.unseal_locked_rows(self.account.id, [key], b"secret")
            store.locked = False
            self.assertEqual(cache.get_content(self.account.id, "INBOX", "42").text, "Updated private body")

    def test_legacy_unwrapped_cache_row_is_retained_but_inaccessible_when_closed(self) -> None:
        class LockStore:
            def has_any_locks(self):
                return True

            def set_message_cache(self, cache):
                pass

            def lock_context_for_message(self, account_id, mailbox, uid):
                return True, None

        protect_patch, unprotect_patch = self.crypto_patches()
        with protect_patch, unprotect_patch:
            cache = MessageCache(self.cache_path)
            cache.upsert_summaries(self.account, [MessageSummary(uid="42", mailbox="INBOX")])
            cache.set_lock_store(LockStore())
            self.assertEqual(cache.count_summaries(self.account.id, "INBOX"), 1)
            self.assertEqual(cache.list_summaries(self.account.id, "INBOX", 50), [])

    def test_access_error_does_not_move_or_delete_database(self) -> None:
        self.cache_path.write_bytes(b"healthy database placeholder")
        access_error = sqlite3.OperationalError("unable to open database file")

        with (
            patch.object(MessageCache, "_init_db", side_effect=access_error),
            patch.object(MessageCache, "_move_corrupt_database") as move_corrupt,
        ):
            with self.assertRaises(sqlite3.OperationalError):
                MessageCache(self.cache_path)

        move_corrupt.assert_not_called()
        self.assertTrue(self.cache_path.exists())

    def test_lazy_attachment_reference_survives_cache_round_trip(self) -> None:
        protect_patch, unprotect_patch = self.crypto_patches()
        with protect_patch, unprotect_patch:
            cache = MessageCache(self.cache_path)
            summary = MessageSummary(uid="42", mailbox="INBOX", has_attachments=True)
            cache.upsert_summaries(self.account, [summary])
            cache.upsert_content(
                self.account,
                MessageContent(
                    summary=summary,
                    text="Body",
                    links=[
                        LinkItem(
                            text="large.pdf",
                            kind="attachment",
                            filename="large.pdf",
                            size=314572800,
                            remote_source="imap",
                            remote_id="2.1",
                            transfer_encoding="base64",
                        )
                    ],
                ),
            )

            content = cache.get_content(self.account.id, "INBOX", "42")

            self.assertIsNotNone(content)
            attachment = content.links[0]
            self.assertEqual(attachment.remote_source, "imap")
            self.assertEqual(attachment.remote_id, "2.1")
            self.assertEqual(attachment.transfer_encoding, "base64")
            self.assertEqual(attachment.attachment_bytes(), b"")

    def test_confirmed_corrupt_database_is_preserved_before_recreation(self) -> None:
        self.cache_path.write_bytes(b"not a sqlite database")

        MessageCache(self.cache_path)

        preserved = list(self.cache_path.parent.glob("messages.corrupt-*.sqlite3"))
        self.assertEqual(len(preserved), 1)
        self.assertEqual(preserved[0].read_bytes(), b"not a sqlite database")
        self.assertTrue(self.cache_path.exists())

    def test_unchanged_summaries_are_not_encrypted_and_written_again(self) -> None:
        protect_patch, unprotect_patch = self.crypto_patches()
        with protect_patch as protect_mock, unprotect_patch:
            cache = MessageCache(self.cache_path)
            summary = MessageSummary(uid="10", mailbox="INBOX", subject="Same")

            cache.upsert_summaries(self.account, [summary])
            first_call_count = protect_mock.call_count
            cache.upsert_summaries(self.account, [MessageSummary(uid="10", mailbox="INBOX", subject="Same")])

            self.assertEqual(first_call_count, 1)
            self.assertEqual(protect_mock.call_count, first_call_count)

    def test_non_numeric_gmail_ids_are_sorted_by_received_time(self) -> None:
        protect_patch, unprotect_patch = self.crypto_patches()
        with protect_patch, unprotect_patch:
            cache = MessageCache(self.cache_path)
            cache.upsert_summaries(
                self.account,
                [
                    MessageSummary(uid="ffff", mailbox="ALL", received_at=100.0),
                    MessageSummary(uid="aaaa", mailbox="ALL", received_at=200.0),
                ],
            )

            messages = cache.list_summaries(self.account.id, "ALL", 10)

            self.assertEqual([message.uid for message in messages], ["aaaa", "ffff"])

    def test_existing_zero_sort_timestamps_are_backfilled(self) -> None:
        protect_patch, unprotect_patch = self.crypto_patches()
        with protect_patch, unprotect_patch:
            cache = MessageCache(self.cache_path)
            cache.upsert_summaries(
                self.account,
                [MessageSummary(uid="gmail-id", mailbox="INBOX", received_at=200.0)],
            )
            with cache._connect() as conn:
                conn.execute("UPDATE messages SET sort_at = 0")

            MessageCache(self.cache_path)
            with cache._connect() as conn:
                sort_at = conn.execute("SELECT sort_at FROM messages").fetchone()[0]

            self.assertEqual(sort_at, 200.0)

    def test_summaries_by_uids_returns_only_requested_messages(self) -> None:
        protect_patch, unprotect_patch = self.crypto_patches()
        with protect_patch, unprotect_patch:
            cache = MessageCache(self.cache_path)
            cache.upsert_summaries(
                self.account,
                [
                    MessageSummary(uid="a", mailbox="INBOX"),
                    MessageSummary(uid="b", mailbox="INBOX"),
                    MessageSummary(uid="c", mailbox="INBOX"),
                ],
            )

            summaries = cache.summaries_by_uids(self.account.id, "INBOX", ["c", "a"])

            self.assertEqual(list(summaries), ["c", "a"])

    def test_gmail_flags_update_every_cached_mailbox_copy(self) -> None:
        protect_patch, unprotect_patch = self.crypto_patches()
        with protect_patch, unprotect_patch:
            cache = MessageCache(self.cache_path)
            cache.upsert_summaries(
                self.account,
                [
                    MessageSummary(uid="same", mailbox="INBOX"),
                    MessageSummary(uid="same", mailbox="ALL"),
                ],
            )

            cache.update_summary_flags_by_uid(
                self.account,
                "same",
                is_read=True,
                is_starred=True,
            )

            inbox = cache.list_summaries(self.account.id, "INBOX", 1)[0]
            all_mail = cache.list_summaries(self.account.id, "ALL", 1)[0]
            self.assertTrue(inbox.is_read and inbox.is_starred)
            self.assertTrue(all_mail.is_read and all_mail.is_starred)

    def test_local_pin_survives_a_server_summary_refresh(self) -> None:
        protect_patch, unprotect_patch = self.crypto_patches()
        with protect_patch, unprotect_patch:
            cache = MessageCache(self.cache_path)
            cache.upsert_summaries(
                self.account,
                [MessageSummary(uid="1", mailbox="INBOX", subject="Pinned", is_pinned=True)],
            )

            refreshed = MessageSummary(uid="1", mailbox="INBOX", subject="Pinned", is_pinned=False)
            cache.upsert_summaries(self.account, [refreshed])

            self.assertTrue(refreshed.is_pinned)
            self.assertTrue(cache.list_summaries(self.account.id, "INBOX", 10)[0].is_pinned)

    def test_parallel_mailbox_writes_do_not_lose_messages(self) -> None:
        protect_patch, unprotect_patch = self.crypto_patches()
        with protect_patch, unprotect_patch:
            cache = MessageCache(self.cache_path)

            def write_mailbox(mailbox: str) -> None:
                cache.upsert_summaries(
                    self.account,
                    [
                        MessageSummary(uid=str(uid), mailbox=mailbox, received_at=float(uid))
                        for uid in range(1, 21)
                    ],
                )

            mailboxes = ["INBOX", "SENT", "SPAM", "ALL"]
            with ThreadPoolExecutor(max_workers=4) as executor:
                list(executor.map(write_mailbox, mailboxes))

            self.assertEqual(
                [cache.count_summaries(self.account.id, mailbox) for mailbox in mailboxes],
                [20, 20, 20, 20],
            )

    def test_inline_image_content_id_survives_cache_round_trip(self) -> None:
        protect_patch, unprotect_patch = self.crypto_patches()
        with protect_patch, unprotect_patch:
            cache = MessageCache(self.cache_path)
            summary = MessageSummary(uid="image", mailbox="INBOX")
            cache.upsert_content(
                self.account,
                MessageContent(
                    summary=summary,
                    text="Image message",
                    links=[
                        LinkItem(
                            "Company logo",
                            "cid:logo",
                            kind="image",
                            data="aW1hZ2U=",
                            content_id="logo",
                        )
                    ],
                ),
            )

            restored = cache.get_content(self.account.id, "INBOX", "image")

            self.assertIsNotNone(restored)
            self.assertEqual(restored.links[0].content_id, "logo")
            self.assertEqual(restored.links[0].attachment_bytes(), b"image")

    def test_recipient_addresses_survive_cache_round_trip(self) -> None:
        protect_patch, unprotect_patch = self.crypto_patches()
        with protect_patch, unprotect_patch:
            cache = MessageCache(self.cache_path)
            cache.upsert_summaries(
                self.account,
                [
                    MessageSummary(
                        uid="sent",
                        mailbox="SENT",
                        recipient_emails=["friend@example.com", "team@example.com"],
                    )
                ],
            )

            restored = cache.list_summaries(self.account.id, "SENT", 1)[0]

        self.assertEqual(
            restored.recipient_emails,
            ["friend@example.com", "team@example.com"],
        )


if __name__ == "__main__":
    unittest.main()
