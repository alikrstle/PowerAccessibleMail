from __future__ import annotations

import base64
import io
import json
import unittest
import threading
import time
import urllib.error
import urllib.parse
from unittest.mock import Mock, patch

from accessible_mail.email_service import MailError
from accessible_mail.gmail_api_service import GmailApiService
from accessible_mail.models import Account, MessageContent, MessageSummary
from accessible_mail.oauth import OAuthReauthenticationRequired


class GmailApiServiceTests(unittest.TestCase):
    def test_mailbox_names_map_to_gmail_api_labels(self) -> None:
        service = GmailApiService()

        self.assertEqual(service.mailbox_to_label("INBOX"), "INBOX")
        self.assertEqual(service.mailbox_to_label("SPAM"), "SPAM")
        self.assertEqual(service.mailbox_to_label("SENT"), "SENT")
        self.assertEqual(service.mailbox_to_label("TRASH"), "TRASH")
        self.assertEqual(service.resolve_trash_mailbox(Account(email_address="user@example.com")), "TRASH")

    def test_summary_and_content_from_gmail_api_payload(self) -> None:
        service = GmailApiService()
        message = {
            "id": "abc123",
            "internalDate": "1760000000000",
            "labelIds": ["INBOX", "UNREAD"],
            "payload": {
                "headers": [
                    {"name": "From", "value": "Sender <sender@example.com>"},
                    {"name": "Subject", "value": "Hello"},
                    {"name": "Date", "value": "Sat, 30 May 2026 10:00:00 +0000"},
                ],
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": "SGVsbG8"}},
                    {
                        "filename": "note.txt",
                        "mimeType": "text/plain",
                        "body": {"data": "YXR0YWNobWVudA", "size": 10},
                    },
                ],
            },
        }

        summary = service._summary_from_message("INBOX", message)
        content = service._content_from_message(
            Account(email_address="user@example.com"),
            summary,
            message,
        )

        self.assertEqual(summary.uid, "abc123")
        self.assertEqual(summary.sender_email, "sender@example.com")
        self.assertTrue(summary.has_attachments)
        self.assertFalse(summary.is_read)
        self.assertEqual(content.text, "Hello")
        self.assertEqual(len(content.links), 1)
        self.assertTrue(content.links[0].is_attachment)
        self.assertEqual(content.links[0].filename, "note.txt")
        self.assertEqual(content.links[0].attachment_bytes(), b"attachment")

    def test_summary_page_fetches_lightweight_metadata_in_parallel(self) -> None:
        class FakeGmailApiService(GmailApiService):
            def __init__(self) -> None:
                self.active_requests = 0
                self.max_active_requests = 0
                self.lock = threading.Lock()

            def _request_json(self, account, method, url, body=None):
                return {
                    "messages": [{"id": str(index)} for index in range(6)],
                    "resultSizeEstimate": 6,
                }

            def _get_message(self, account, message_id, message_format):
                self.assert_metadata_format(message_format)
                with self.lock:
                    self.active_requests += 1
                    self.max_active_requests = max(self.max_active_requests, self.active_requests)
                time.sleep(0.01)
                with self.lock:
                    self.active_requests -= 1
                return {
                    "id": message_id,
                    "internalDate": str((int(message_id) + 1) * 1000),
                    "labelIds": ["INBOX"],
                    "payload": {"headers": []},
                }

            def assert_metadata_format(self, message_format: str) -> None:
                if message_format != "metadata":
                    raise AssertionError(message_format)

        service = FakeGmailApiService()

        summaries, _next_token, _estimate = service._list_summary_page(
            Account(email_address="user@example.com"),
            "INBOX",
            6,
        )

        self.assertEqual(len(summaries), 6)
        self.assertGreater(service.max_active_requests, 1)

    def test_summary_page_reuses_cached_metadata_except_recent_messages(self) -> None:
        class FakeCache:
            def summaries_by_uids(self, _account_id, mailbox, uids):
                return {
                    uid: MessageSummary(uid=uid, mailbox=mailbox, received_at=float(uid))
                    for uid in uids
                }

        class FakeGmailApiService(GmailApiService):
            def __init__(self) -> None:
                self.cache = FakeCache()
                self.fetched_ids: list[str] = []

            def _request_json(self, account, method, url, body=None):
                return {"messages": [{"id": str(index)} for index in range(12)]}

            def _get_message(self, account, message_id, message_format):
                self.fetched_ids.append(message_id)
                return {
                    "id": message_id,
                    "internalDate": str((int(message_id) + 1) * 1000),
                    "labelIds": ["INBOX"],
                    "payload": {"headers": []},
                }

        service = FakeGmailApiService()
        summaries, _next_token, _estimate = service._list_summary_page(
            Account(id="account", email_address="user@example.com"),
            "INBOX",
            12,
        )

        self.assertEqual(len(service.fetched_ids), 8)
        self.assertEqual(set(service.fetched_ids), {str(index) for index in range(8)})
        self.assertEqual([summary.uid for summary in summaries], [str(index) for index in range(12)])

    def test_list_messages_does_not_hide_server_failure_behind_cache(self) -> None:
        class FakeCache:
            def list_summaries(self, account_id, mailbox, limit):
                return [MessageSummary(uid="cached", mailbox=mailbox)]

        class FakeGmailApiService(GmailApiService):
            def __init__(self) -> None:
                self.cache = FakeCache()
                self.next_page_tokens = {}
                self.estimated_totals = {}

            def _list_summary_page(self, *args, **kwargs):
                raise MailError("server failed")

        service = FakeGmailApiService()

        with self.assertRaisesRegex(MailError, "server failed"):
            service.list_messages(
                Account(id="account", email_address="user@example.com"),
                "INBOX",
            )

    def test_list_messages_returns_fresh_results_when_cache_write_fails(self) -> None:
        class FakeCache:
            def list_summaries(self, account_id, mailbox, limit):
                return [MessageSummary(uid="cached", mailbox=mailbox, received_at=1.0)]

            def upsert_summaries(self, account, summaries):
                raise OSError("cache unavailable")

        class FakeGmailApiService(GmailApiService):
            def __init__(self) -> None:
                self.cache = FakeCache()
                self.next_page_tokens = {}
                self.estimated_totals = {}

            def _list_summary_page(self, *args, **kwargs):
                return [MessageSummary(uid="fresh", mailbox="INBOX", received_at=2.0)], "", 2

        service = FakeGmailApiService()
        messages = service.list_messages(
            Account(id="account", email_address="user@example.com"),
            "INBOX",
        )

        self.assertEqual([message.uid for message in messages], ["fresh"])

    def test_insufficient_gmail_scope_requests_reauthentication(self) -> None:
        service = GmailApiService()
        account = Account(
            email_address="user@example.com",
            oauth_provider="google_gmail_api",
            oauth_access_token="old-token",
            oauth_token_expiry=time.time() + 3600,
        )
        detail = json.dumps(
            {
                "error": {
                    "code": 403,
                    "message": "Request had insufficient authentication scopes.",
                    "status": "PERMISSION_DENIED",
                    "details": [
                        {
                            "reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT",
                        }
                    ],
                }
            }
        ).encode("utf-8")
        http_error = urllib.error.HTTPError(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            403,
            "Forbidden",
            {},
            io.BytesIO(detail),
        )

        try:
            with patch(
                "accessible_mail.gmail_api_service.urllib.request.urlopen",
                side_effect=http_error,
            ):
                with self.assertRaisesRegex(
                    OAuthReauthenticationRequired,
                    "صلاحية حساب Gmail المحفوظة",
                ):
                    service._request_json(
                        account,
                        "GET",
                        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                    )
        finally:
            http_error.close()

    def test_opening_cached_unread_message_updates_gmail_read_state(self) -> None:
        summary = MessageSummary(uid="message", mailbox="INBOX", is_read=False)
        cached = MessageContent(summary=summary, text="cached body", links=[])

        class FakeCache:
            def get_content(self, *_args):
                return cached

        service = GmailApiService(cache=FakeCache())
        service.set_message_read = Mock()
        account = Account(id="account", oauth_provider="google_gmail_api")

        result = service.fetch_message(account, summary)

        service.set_message_read.assert_called_once_with(account, summary, True)
        self.assertTrue(result.summary.is_read)

    def test_content_uses_html_when_plain_part_is_only_a_placeholder(self) -> None:
        service = GmailApiService()
        message = {
            "id": "html-only",
            "internalDate": "1760000000000",
            "labelIds": ["INBOX"],
            "payload": {
                "headers": [
                    {"name": "From", "value": "Sender <sender@example.com>"},
                    {"name": "Subject", "value": "HTML message"},
                ],
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": "UGxhaW4gdGV4dCB2ZXJzaW9uIG5vdCBhdmFpbGFibGU"},
                    },
                    {
                        "mimeType": "text/html",
                        "body": {"data": "PHA-SGVsbG8gZnJvbSA8c3Ryb25nPkhUTUw8L3N0cm9uPjwvcD4"},
                    },
                ],
            },
        }

        summary = service._summary_from_message("INBOX", message)
        content = service._content_from_message(
            Account(email_address="user@example.com"),
            summary,
            message,
        )

        self.assertEqual(content.text, "Hello from HTML")
        self.assertNotIn("Plain text version not available", content.text)

    def test_content_removes_html_client_warning_from_gmail_html(self) -> None:
        service = GmailApiService()
        warning_html = (
            "<p>Actual Gmail content.</p><p>Email client cannot display HTML, or your settings are turned off. "
            "To view this email, please click the link above, or copy and paste it into your browser.</p>"
        )
        message = {
            "id": "html-warning",
            "internalDate": "1760000000000",
            "labelIds": ["INBOX"],
            "payload": {
                "headers": [],
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": "RW1haWwgY2xpZW50IGNhbm5vdCBkaXNwbGF5IEhUTUw"}},
                    {
                        "mimeType": "text/html",
                        "body": {
                            "data": base64.urlsafe_b64encode(warning_html.encode("utf-8"))
                            .decode("ascii")
                            .rstrip("=")
                        },
                    },
                ],
            },
        }
        summary = service._summary_from_message("INBOX", message)

        content = service._content_from_message(Account(email_address="user@example.com"), summary, message)

        self.assertEqual(content.text, "Actual Gmail content.")

    def test_large_remote_text_part_is_body_not_attachment_and_honours_charset(self) -> None:
        class FakeGmailApiService(GmailApiService):
            def _attachment_bytes(self, account, message_id, attachment_id):
                return "مرحبا من Gmail".encode("windows-1256")

        service = FakeGmailApiService()
        message = {
            "id": "large-body",
            "internalDate": "1760000000000",
            "labelIds": ["INBOX"],
            "payload": {
                "headers": [],
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "headers": [
                            {"name": "Content-Type", "value": "text/plain; charset=windows-1256"}
                        ],
                        "body": {"attachmentId": "remote-body", "size": 20},
                    }
                ],
            },
        }

        summary = service._summary_from_message("INBOX", message)
        content = service._content_from_message(
            Account(email_address="user@example.com"),
            summary,
            message,
        )

        self.assertFalse(summary.has_attachments)
        self.assertEqual(content.text, "مرحبا من Gmail")
        self.assertEqual(content.links, [])

    def test_all_mail_listing_does_not_send_an_invalid_label_id(self) -> None:
        class FakeGmailApiService(GmailApiService):
            def __init__(self) -> None:
                self.requested_url = ""

            def _request_json(self, account, method, url, body=None):
                self.requested_url = url
                return {"messages": []}

        service = FakeGmailApiService()
        service._list_summary_page(Account(email_address="user@example.com"), "ALL", 50)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(service.requested_url).query)

        self.assertNotIn("labelIds", query)

    def test_metadata_get_requests_only_required_headers(self) -> None:
        class FakeGmailApiService(GmailApiService):
            def __init__(self) -> None:
                self.requested_url = ""

            def _request_json(self, account, method, url, body=None):
                self.requested_url = url
                return {}

        service = FakeGmailApiService()
        service._get_message(Account(email_address="user@example.com"), "abc", "metadata")
        query = urllib.parse.parse_qs(urllib.parse.urlparse(service.requested_url).query)

        self.assertEqual(query["format"], ["metadata"])
        self.assertIn("From", query["metadataHeaders"])
        self.assertIn("Subject", query["metadataHeaders"])


if __name__ == "__main__":
    unittest.main()
