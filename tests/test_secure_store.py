from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from accessible_mail.models import Account, LinkItem, MessageContent, MessageSummary
from accessible_mail.secure_store import MessageCache, _decrypt_summary_json


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
