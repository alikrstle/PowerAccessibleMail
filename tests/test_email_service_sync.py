from __future__ import annotations

import imaplib
import unittest

from accessible_mail.email_service import EmailService
from accessible_mail.mail_service_router import MailServiceRouter
from accessible_mail.models import Account, LinkItem, MessageContent, MessageSummary
from accessible_mail.oauth import OAuthError


class FakeCache:
    def __init__(self, initial: list[MessageSummary] | None = None) -> None:
        self.messages: dict[tuple[str, str, str], MessageSummary] = {}
        for summary in initial or []:
            self.messages[("account", summary.mailbox, summary.uid)] = summary

    def list_summaries(
        self,
        account_id: str,
        mailbox: str,
        limit: int,
    ) -> list[MessageSummary]:
        summaries = [
            summary
            for (stored_account_id, stored_mailbox, _uid), summary in self.messages.items()
            if stored_account_id == account_id and stored_mailbox == mailbox
        ]
        summaries.sort(key=lambda summary: int(summary.uid), reverse=True)
        return summaries[:limit]

    def count_summaries(self, account_id: str, mailbox: str) -> int:
        return len(self.list_summaries(account_id, mailbox, 1_000_000))

    def oldest_uid(self, account_id: str, mailbox: str) -> str:
        summaries = self.list_summaries(account_id, mailbox, 1_000_000)
        if not summaries:
            return ""
        return min(summaries, key=lambda summary: int(summary.uid)).uid

    def upsert_summaries(self, account: Account, summaries: list[MessageSummary]) -> None:
        for summary in summaries:
            self.messages[(account.id, summary.mailbox, summary.uid)] = summary

    def mark_read(
        self,
        account: Account,
        mailbox: str,
        uid: str,
        is_read: bool = True,
    ) -> None:
        summary = self.messages.get((account.id, mailbox, uid))
        if summary:
            summary.is_read = is_read

    def delete_account(self, account_id: str) -> None:
        self.messages = {
            key: summary
            for key, summary in self.messages.items()
            if key[0] != account_id
        }


class FailingUpsertCache(FakeCache):
    def upsert_summaries(self, account: Account, summaries: list[MessageSummary]) -> None:
        raise OSError("cache write failed")


class FailingMarkReadCache(FakeCache):
    def mark_read(
        self,
        account: Account,
        mailbox: str,
        uid: str,
        is_read: bool = True,
    ) -> None:
        raise OSError("cache read-state write failed")


class FakeConnection:
    def __init__(self) -> None:
        self.uid_operations: list[tuple[str, str, str, str]] = []

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def uid(self, command: str, uid: str, operation: str, flag: str) -> tuple[str, list[bytes]]:
        self.uid_operations.append((command, uid, operation, flag))
        return "OK", [b"OK"]


class FakeSelectConnection:
    def __init__(
        self,
        responses: list[tuple[str, list[bytes]] | Exception],
    ) -> None:
        self.responses = list(responses)
        self.select_calls: list[tuple[str, bool]] = []

    def select(self, mailbox: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        self.select_calls.append((mailbox, readonly))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeSyncService(EmailService):
    def __init__(
        self,
        message_count: int,
        initial: list[MessageSummary] | None = None,
    ) -> None:
        self.on_account_updated = None
        self.cache = FakeCache(initial)
        self.message_count = message_count
        self.fetch_ranges: list[tuple[int, int]] = []
        self.connection = FakeConnection()

    def _imap(self, account: Account) -> FakeConnection:
        return self.connection

    def _select(self, conn: FakeConnection, mailbox: str, readonly: bool) -> int:
        return self.message_count

    def _sequence_for_uid(self, conn: FakeConnection, uid: str) -> int:
        value = int(uid)
        if 1 <= value <= self.message_count:
            return value
        return 0

    def _fetch_summary_batch(
        self,
        conn: FakeConnection,
        mailbox: str,
        sequence_set: str,
    ) -> list[MessageSummary]:
        start_text, end_text = sequence_set.split(":", 1)
        start = int(start_text)
        end = self.message_count if end_text == "*" else int(end_text)
        self.fetch_ranges.append((start, end))
        return [
            MessageSummary(
                uid=str(uid),
                mailbox=mailbox,
                sender=f"sender {uid}",
                subject=f"message {uid}",
                is_read=uid % 2 == 0,
            )
            for uid in range(end, start - 1, -1)
        ]

    def list_mailboxes(self, conn: FakeConnection):
        from accessible_mail.email_service import MailboxInfo

        return [
            MailboxInfo("INBOX", ("\\Inbox",)),
            MailboxInfo("[Gmail]/All Mail", ("\\All",)),
        ]


class FakeAuthFailService(FakeSyncService):
    def _select(self, conn: FakeConnection, mailbox: str, readonly: bool) -> int:
        raise OAuthError("invalid_grant")


class FakeServerFailService(FakeSyncService):
    def _select(self, conn: FakeConnection, mailbox: str, readonly: bool) -> int:
        raise OSError("server unavailable")


class FakeTransientServerFailService(FakeSyncService):
    def __init__(self, message_count: int) -> None:
        super().__init__(message_count)
        self.receive_retry_delay_seconds = 0
        self.failures_remaining = 1

    def _select(self, conn: FakeConnection, mailbox: str, readonly: bool) -> int:
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise OSError("server unavailable")
        return super()._select(conn, mailbox, readonly)


class EmailServiceSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.account = Account(id="account", email_address="user@example.com")

    def test_list_messages_fetches_latest_inbox_batch(self) -> None:
        service = FakeSyncService(message_count=125)

        messages = service.list_messages(
            self.account,
            "INBOX",
            limit=50,
            batch_size=25,
        )

        self.assertEqual(service.fetch_ranges, [(76, 125)])
        self.assertEqual(messages[0].uid, "125")
        self.assertEqual(messages[-1].uid, "76")

    def test_select_uses_unquoted_inbox_first(self) -> None:
        service = EmailService.__new__(EmailService)
        connection = FakeSelectConnection([("OK", [b"12"])])

        count = service._select(connection, "INBOX", readonly=True)

        self.assertEqual(count, 12)
        self.assertEqual(connection.select_calls, [("INBOX", True)])

    def test_select_falls_back_to_select_when_examine_is_rejected(self) -> None:
        service = EmailService.__new__(EmailService)
        error = imaplib.IMAP4.error("BAD Command Argument Error. 12")
        connection = FakeSelectConnection(
            [
                error,
                error,
                ("OK", [b"8"]),
            ]
        )

        count = service._select(connection, "INBOX", readonly=True)

        self.assertEqual(count, 8)
        self.assertEqual(
            connection.select_calls,
            [
                ("INBOX", True),
                ('"INBOX"', True),
                ("INBOX", False),
            ],
        )

    def test_select_quotes_mailbox_names_with_spaces(self) -> None:
        service = EmailService.__new__(EmailService)
        connection = FakeSelectConnection([("OK", [b"3"])])

        count = service._select(connection, "Junk Email", readonly=True)

        self.assertEqual(count, 3)
        self.assertEqual(connection.select_calls, [('"Junk Email"', True)])

    def test_list_messages_does_not_hide_oauth_failure_behind_cache(self) -> None:
        initial = [MessageSummary(uid="125", mailbox="INBOX")]
        service = FakeAuthFailService(message_count=125, initial=initial)

        with self.assertRaises(OAuthError):
            service.list_messages(self.account, "INBOX")

    def test_list_messages_does_not_hide_server_failure_behind_cache(self) -> None:
        initial = [MessageSummary(uid="125", mailbox="INBOX")]
        service = FakeServerFailService(message_count=125, initial=initial)
        service.receive_retry_delay_seconds = 0

        with self.assertRaisesRegex(Exception, "تعذر استلام رسائل جديدة"):
            service.list_messages(self.account, "INBOX")

    def test_list_messages_retries_transient_server_failure(self) -> None:
        service = FakeTransientServerFailService(message_count=125)

        messages = service.list_messages(self.account, "INBOX", limit=50, batch_size=25)

        self.assertEqual(messages[0].uid, "125")
        self.assertEqual(service.fetch_ranges, [(76, 125)])

    def test_list_messages_returns_fetched_messages_if_cache_write_fails(self) -> None:
        initial = [MessageSummary(uid="75", mailbox="INBOX")]
        service = FakeSyncService(message_count=125, initial=initial)
        service.cache = FailingUpsertCache(initial)

        messages = service.list_messages(self.account, "INBOX", limit=50, batch_size=25)

        self.assertEqual(service.fetch_ranges, [(76, 125)])
        self.assertEqual(messages[0].uid, "125")
        self.assertEqual(messages[-1].uid, "76")

    def test_sync_all_older_messages_fetches_until_first_message(self) -> None:
        service = FakeSyncService(message_count=125)
        progress: list[tuple[int, int, int]] = []

        result = service.sync_all_older_messages(
            self.account,
            "INBOX",
            batch_size=50,
            on_progress=lambda _messages, added, total, cached, _message_count: progress.append(
                (added, total, cached)
            ),
        )

        self.assertEqual(service.fetch_ranges, [(76, 125), (26, 75), (1, 25)])
        self.assertEqual(result.added_count, 125)
        self.assertEqual(result.cached_count, 125)
        self.assertEqual(result.total_count, 125)
        self.assertEqual(len(result.messages), 125)
        self.assertEqual({message.is_read for message in result.messages}, {False, True})
        self.assertEqual(progress[-1], (25, 125, 125))

    def test_resolve_all_mailbox_uses_gmail_all_attribute(self) -> None:
        service = FakeSyncService(message_count=1)

        self.assertEqual(service.resolve_all_mailbox(self.account), "[Gmail]/All Mail")

    def test_sync_all_older_messages_extends_existing_cache_without_duplicates(self) -> None:
        initial = [
            MessageSummary(uid=str(uid), mailbox="INBOX")
            for uid in range(101, 126)
        ]
        service = FakeSyncService(message_count=125, initial=initial)

        result = service.sync_all_older_messages(self.account, "INBOX", batch_size=50)

        self.assertEqual(service.fetch_ranges, [(76, 125), (26, 75), (1, 25)])
        self.assertEqual(result.added_count, 100)
        self.assertEqual(result.cached_count, 125)
        self.assertEqual(len({message.uid for message in result.messages}), 125)

    def test_sync_all_older_messages_fills_cache_gaps_after_latest_batch(self) -> None:
        initial = [
            *[MessageSummary(uid=str(uid), mailbox="INBOX") for uid in range(1, 51)],
            *[MessageSummary(uid=str(uid), mailbox="INBOX") for uid in range(101, 126)],
        ]
        service = FakeSyncService(message_count=125, initial=initial)

        result = service.sync_all_older_messages(self.account, "INBOX", batch_size=50)

        self.assertEqual(service.fetch_ranges, [(76, 125), (26, 75), (1, 25)])
        self.assertEqual(result.added_count, 50)
        self.assertEqual(result.cached_count, 125)
        self.assertEqual(len({message.uid for message in result.messages}), 125)

    def test_delete_cached_account_removes_only_selected_account(self) -> None:
        router = MailServiceRouter.__new__(MailServiceRouter)
        router.imap_service = type("FakeService", (), {"cache": FakeCache()})()
        account = Account(id="account", email_address="user@example.com")
        other_account = Account(id="other", email_address="other@example.com")
        router.imap_service.cache.upsert_summaries(
            account,
            [MessageSummary(uid="1", mailbox="INBOX")],
        )
        router.imap_service.cache.upsert_summaries(
            other_account,
            [MessageSummary(uid="2", mailbox="INBOX")],
        )

        router.delete_cached_account(account)

        self.assertEqual(router.imap_service.cache.list_summaries("account", "INBOX", 10), [])
        self.assertEqual(
            [message.uid for message in router.imap_service.cache.list_summaries("other", "INBOX", 10)],
            ["2"],
        )

    def test_set_message_read_updates_server_and_cache(self) -> None:
        service = FakeSyncService(message_count=1)
        summary = MessageSummary(uid="1", mailbox="INBOX", is_read=False)
        service.cache.upsert_summaries(self.account, [summary])

        service.set_message_read(self.account, summary, True)
        service.set_message_read(self.account, summary, False)

        self.assertEqual(
            service.connection.uid_operations,
            [
                ("store", "1", "+FLAGS", "(\\Seen)"),
                ("store", "1", "-FLAGS", "(\\Seen)"),
            ],
        )
        self.assertFalse(summary.is_read)
        self.assertFalse(service.cache.list_summaries("account", "INBOX", 10)[0].is_read)

    def test_set_message_read_succeeds_when_only_local_cache_write_fails(self) -> None:
        service = FakeSyncService(message_count=1)
        summary = MessageSummary(uid="1", mailbox="INBOX", is_read=False)
        service.cache = FailingMarkReadCache([summary])

        service.set_message_read(self.account, summary, True)

        self.assertTrue(summary.is_read)
        self.assertEqual(service.connection.uid_operations[-1], ("store", "1", "+FLAGS", "(\\Seen)"))

    def test_summary_uses_internaldate_as_received_timestamp(self) -> None:
        service = FakeSyncService(message_count=1)

        summary = service._summary_from_header(
            uid="1",
            mailbox="INBOX",
            flags_blob=b'1 (UID 1 FLAGS (\\Seen) INTERNALDATE "28-May-2026 10:11:12 +0300")',
            header_bytes=(
                b"From: sender@example.com\r\n"
                b"Subject: hello\r\n"
                b"Date: Wed, 27 May 2026 10:00:00 +0000\r\n"
                b"\r\n"
            ),
        )

        self.assertTrue(summary.is_read)
        self.assertGreater(summary.received_at, 0.0)
        self.assertEqual(summary.sort_timestamp, summary.received_at)

    def test_fetch_meta_detects_attachments_from_bodystructure(self) -> None:
        service = FakeSyncService(message_count=1)

        self.assertTrue(
            service._fetch_meta_has_attachments(
                b'1 (UID 1 BODYSTRUCTURE ("APPLICATION" "PDF" ("NAME" "file.pdf") NIL NIL "BASE64" 120 NIL ("ATTACHMENT" ("FILENAME" "file.pdf")) NIL NIL))'
            )
        )
        self.assertFalse(
            service._fetch_meta_has_attachments(
                b'1 (UID 1 BODYSTRUCTURE ("TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "7BIT" 20 1 NIL NIL NIL))'
            )
        )

    def test_cached_content_with_missing_attachment_is_refetched(self) -> None:
        service = FakeSyncService(message_count=1)
        summary = MessageSummary(uid="1", mailbox="INBOX", has_attachments=True)
        cached = MessageContent(
            summary=summary,
            text="cached",
            links=[LinkItem("https://example.com", "https://example.com")],
        )
        fresh = MessageContent(
            summary=summary,
            text="fresh",
            links=[LinkItem("file.pdf", kind="attachment", filename="file.pdf", data="AA==")],
        )

        self.assertTrue(service._cached_content_needs_attachment_refresh(summary, cached))
        self.assertFalse(service._cached_content_needs_attachment_refresh(summary, fresh))

    def test_sort_timestamp_falls_back_to_header_date(self) -> None:
        older = MessageSummary(
            uid="20",
            mailbox="INBOX",
            date="Tue, 26 May 2026 10:00:00 +0000",
        )
        newer = MessageSummary(
            uid="10",
            mailbox="INBOX",
            date="Wed, 27 May 2026 10:00:00 +0000",
        )

        ordered = sorted([older, newer], key=lambda message: message.sort_timestamp, reverse=True)

        self.assertEqual([message.uid for message in ordered], ["10", "20"])


if __name__ == "__main__":
    unittest.main()
