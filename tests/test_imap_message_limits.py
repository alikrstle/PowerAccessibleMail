from __future__ import annotations

from contextlib import nullcontext
import unittest
from unittest.mock import Mock, patch

from accessible_mail.email_service import EmailService, MailError, MAX_RAW_MESSAGE_BYTES
from accessible_mail.models import Account, MessageSummary


class ImapMessageLimitTests(unittest.TestCase):
    def fetch(self, reply, raw=b"Subject: Test\r\n\r\nSafe text"):
        cache = Mock()
        cache.get_content.return_value = None
        service = EmailService(cache=cache)
        connection = Mock()
        connection.uid.return_value = reply
        fetch_body = Mock(return_value=(b"metadata", raw))
        return service, connection, fetch_body, cache

    def open_message(self, service, connection, fetch_body):
        with patch.object(service, "_imap", return_value=nullcontext(connection)), \
                patch.object(service, "_select"), patch.object(service, "_uid_fetch", fetch_body):
            return service.fetch_message(Account(id="a"), MessageSummary(uid="42", mailbox="INBOX"), mark_read=False)

    def test_large_message_without_structure_never_falls_back_to_whole_body(self):
        fixture = self.fetch(("OK", [f"1 (UID 42 RFC822.SIZE {MAX_RAW_MESSAGE_BYTES + 1})".encode()]))
        service, connection, fetch_body, cache = fixture
        with self.assertRaises(MailError):
            self.open_message(service, connection, fetch_body)
        self.assertEqual(connection.uid.call_args_list[0].args, ("fetch", b"42", "(UID RFC822.SIZE)"))
        self.assertEqual(connection.uid.call_args_list[1].args, ("fetch", b"42", "(UID BODYSTRUCTURE)"))
        fetch_body.assert_not_called()
        cache.upsert_content.assert_not_called()

    def test_small_message_downloads_after_size_check_without_marking_read(self):
        service, connection, fetch_body, cache = self.fetch(("OK", [b"1 (UID 42 RFC822.SIZE 30)"]))
        content = self.open_message(service, connection, fetch_body)
        self.assertEqual(content.text, "Safe text")
        self.assertFalse(content.summary.is_read)
        fetch_body.assert_called_once_with(connection, b"42", "(BODY.PEEK[])")
        cache.upsert_content.assert_called_once()

    def test_invalid_missing_or_other_message_size_never_falls_back_to_body(self):
        for reply in (("NO", [b"gone"]), ("OK", [None]), ("OK", [b"1 (UID 42)"]),
                      ("OK", [b"1 (UID 43 RFC822.SIZE 30)"]),
                      ("OK", [b"1 (UID 42 RFC822.SIZE " + b"9" * 100 + b")"])):
            with self.subTest(reply=reply):
                service, connection, fetch_body, cache = self.fetch(reply)
                with self.assertRaises(MailError):
                    self.open_message(service, connection, fetch_body)
                fetch_body.assert_not_called()
                cache.upsert_content.assert_not_called()

    def test_body_limit_remains_when_server_reports_a_smaller_size(self):
        service, connection, fetch_body, cache = self.fetch(("OK", [b"1 (UID 42 RFC822.SIZE 1)"]))
        with patch("accessible_mail.email_service.MAX_RAW_MESSAGE_BYTES", 10), self.assertRaises(MailError):
            self.open_message(service, connection, fetch_body)
        fetch_body.assert_called_once()
        cache.upsert_content.assert_not_called()


if __name__ == "__main__":
    unittest.main()
